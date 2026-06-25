"""
ORBITIQ-X — SSA Service
==========================
Implements the Space Situational Awareness business logic.
Delegates to SatelliteRepository for catalog access and
OrbitForecastService for propagation.

Methods
────────
  list_catalog()    — paginated RSO catalog with filters
  get_rso()         — single RSO detail lookup
  get_tle()         — current TLE for an object
  propagate()       — SGP4 ephemeris over a time window
  predict_passes()  — ground station pass prediction
  stream_positions()— async generator for SSE live positions
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.satellites import Satellite
from app.db.repositories.satellite_repository import SatelliteRepository
from app.schemas.ssa import (
    EphemerisRequest, EphemerisResponse,
    GroundPassRequest, GroundPassResponse,
    RSOCatalogResponse, RSODetailResponse, RSODetail, RSOSummary,
    TLEResponse, PassWindow, StateVector,
)

logger = logging.getLogger(__name__)


def _sat_to_summary(sat: Satellite) -> RSOSummary:
    return RSOSummary(
        norad_id       = sat.norad_id,
        name           = sat.name,
        cospar_id      = sat.cospar_id,
        object_type    = sat.object_type,
        regime         = sat.regime,
        status         = sat.status,
        country_code   = sat.country_code,
        operator_name  = sat.operator_name,
        altitude_km    = sat.altitude_km,
        inclination_deg= sat.inclination_deg,
        launch_date    = datetime.combine(sat.launch_date, datetime.min.time())
                         .replace(tzinfo=timezone.utc) if sat.launch_date else None,
        tle_age_days   = sat.tle_age_days,
    )


def _sat_to_detail(sat: Satellite) -> RSODetail:
    base = _sat_to_summary(sat)
    return RSODetail(
        **base.model_dump(),
        international_designator = sat.international_designator,
        mission_type    = sat.mission_type,
        launch_site     = sat.launch_site,
        launch_vehicle  = sat.launch_vehicle,
        decay_date      = datetime.combine(sat.decay_date, datetime.min.time())
                          .replace(tzinfo=timezone.utc) if sat.decay_date else None,
        expected_eol    = datetime.combine(sat.expected_eol, datetime.min.time())
                          .replace(tzinfo=timezone.utc) if sat.expected_eol else None,
        mass_kg         = sat.mass_kg,
        span_m          = sat.span_m,
        radar_cross_section_m2 = sat.radar_cross_section_m2,
        hard_body_radius_km    = sat.hard_body_radius_km,
        perigee_km      = sat.perigee_km,
        apogee_km       = sat.apogee_km,
        raan_deg        = sat.raan_deg,
        eccentricity    = sat.eccentricity,
        mean_motion_rev_day = sat.mean_motion_rev_day,
        period_minutes  = sat.period_minutes,
        tle_line1       = sat.tle_line1,
        tle_line2       = sat.tle_line2,
        tle_epoch       = sat.tle_epoch,
    )


class SSAService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo    = SatelliteRepository(session=session)

    # ── Catalog ───────────────────────────────────────────────

    async def list_catalog(
        self,
        orbit_class:     str | None = None,
        country_code:    str | None = None,
        object_type:     str | None = None,
        launched_after:  datetime | None = None,
        launched_before: datetime | None = None,
        page:     int = 1,
        page_size:int = 50,
    ) -> RSOCatalogResponse:
        conditions = []
        if orbit_class:
            conditions.append(Satellite.regime == orbit_class)
        if country_code:
            conditions.append(Satellite.country_code == country_code.upper())
        if object_type:
            conditions.append(Satellite.object_type == object_type.lower())
        if launched_after:
            conditions.append(Satellite.launch_date >= launched_after.date())
        if launched_before:
            conditions.append(Satellite.launch_date <= launched_before.date())

        where = and_(*conditions) if conditions else True

        count_result = await self._session.execute(
            select(func.count(Satellite.id)).where(where)
        )
        total = count_result.scalar_one_or_none() or 0

        offset = (page - 1) * page_size
        rows = await self._session.execute(
            select(Satellite).where(where)
            .order_by(Satellite.norad_id)
            .limit(page_size).offset(offset)
        )
        sats = rows.scalars().all()

        return RSOCatalogResponse(
            total    = total,
            page     = page,
            page_size= page_size,
            has_next = (page * page_size) < total,
            items    = [_sat_to_summary(s) for s in sats],
        )

    async def get_rso(self, norad_id: int) -> RSODetailResponse | None:
        sat = await self._repo.get_by_norad(norad_id)
        if sat is None:
            return None
        return RSODetailResponse(rso=_sat_to_detail(sat))

    async def get_tle(
        self, norad_id: int, epoch: datetime | None = None
    ) -> TLEResponse | None:
        sat = await self._repo.get_by_norad(norad_id)
        if sat is None or not sat.tle_line1:
            return None
        return TLEResponse(
            norad_id = sat.norad_id,
            name     = sat.name,
            tle_line1= sat.tle_line1,
            tle_line2= sat.tle_line2,
            epoch    = sat.tle_epoch,
            age_days = sat.tle_age_days,
        )

    # ── Propagation ───────────────────────────────────────────

    async def propagate(self, request: EphemerisRequest) -> EphemerisResponse:
        """
        SGP4 ephemeris generation delegated to OrbitForecastService.
        Falls back to empty vectors if TLE is unavailable.
        """
        objects = []
        for norad_id in request.norad_ids:
            sat = await self._repo.get_by_norad(norad_id)
            if not sat or not sat.tle_line1:
                objects.append({"norad_id": norad_id, "name": "UNKNOWN", "vectors": [],
                                "error": "TLE not available"})
                continue

            vectors = await asyncio.get_event_loop().run_in_executor(
                None,
                _sgp4_propagate_window,
                sat.tle_line1, sat.tle_line2, sat.name,
                request.start_epoch, request.stop_epoch, request.step_seconds,
            )
            objects.append({"norad_id": norad_id, "name": sat.name, "vectors": vectors})

        return EphemerisResponse(
            generated_at    = datetime.now(timezone.utc),
            reference_frame = request.reference_frame,
            objects         = objects,
        )

    async def predict_passes(self, request: GroundPassRequest) -> GroundPassResponse:
        """Ground station pass prediction (analytical horizon model)."""
        sat = await self._repo.get_by_norad(request.norad_id)
        name = sat.name if sat else f"NORAD-{request.norad_id}"

        passes = await asyncio.get_event_loop().run_in_executor(
            None,
            _compute_passes,
            request.norad_id, sat.tle_line1 if sat else None,
            sat.tle_line2 if sat else None,
            request.stations, request.start_epoch, request.stop_epoch,
            request.min_elevation_deg,
        )

        return GroundPassResponse(
            norad_id     = request.norad_id,
            name         = name,
            passes       = passes,
            total        = len(passes),
            generated_at = datetime.now(timezone.utc),
        )

    async def stream_positions(
        self, norad_ids: list[int] | None = None
    ) -> AsyncIterator[dict]:
        """
        Async generator for SSE live RSO position stream.
        Reads from in-memory live states, refreshed by the scheduler.
        """
        try:
            from app.digital_twin.services.orbital_state_service import get_live_states
            while True:
                states = get_live_states()
                target_ids = set(norad_ids) if norad_ids else None
                for norad_id, state in states.items():
                    if target_ids and norad_id not in target_ids:
                        continue
                    yield {
                        "norad_id":    state.norad_id,
                        "name":        state.name,
                        "latitude":    state.latitude_deg,
                        "longitude":   state.longitude_deg,
                        "altitude_km": state.altitude_km,
                        "epoch":       state.epoch.isoformat() if state.epoch else None,
                    }
                await asyncio.sleep(30)
        except Exception as exc:
            logger.warning("stream_positions_error error=%s", exc)


# ── SGP4 helpers ──────────────────────────────────────────────

def _sgp4_propagate_window(
    tle1: str, tle2: str, name: str,
    start: datetime, stop: datetime, step_s: int,
) -> list[dict]:
    """
    Synchronous SGP4 propagation over [start, stop] with step_s cadence.
    Uses sgp4 library (already in requirements). Returns list of state vector dicts.
    Gracefully returns [] if sgp4 fails.
    """
    try:
        from sgp4.api import Satrec, WGS84
        from sgp4.earth_gravity import wgs84

        sat = Satrec.twoline2rv(tle1, tle2)
        vectors = []
        current = start
        while current <= stop:
            jd = _datetime_to_jd(current)
            e, r, v = sat.sgp4(jd, 0.0)
            if e == 0:
                vectors.append({
                    "epoch":           current.isoformat(),
                    "position_eci_km": list(r),
                    "velocity_eci_kms":list(v),
                })
            current += timedelta(seconds=step_s)
        return vectors
    except Exception:
        return []


def _datetime_to_jd(dt: datetime) -> float:
    """Convert a UTC datetime to Julian Date (JD)."""
    # Julian Date of J2000.0 epoch
    jd_j2000 = 2451545.0
    delta = dt - datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return jd_j2000 + delta.total_seconds() / 86400.0


def _compute_passes(
    norad_id: int, tle1: str | None, tle2: str | None,
    stations: list, start: datetime, stop: datetime,
    min_el: float,
) -> list[PassWindow]:
    """
    Simplified analytical pass prediction using SGP4.
    Returns access windows where satellite exceeds min_elevation_deg.
    """
    if not tle1 or not tle2:
        return []
    try:
        from sgp4.api import Satrec
        sat = Satrec.twoline2rv(tle1, tle2)
        passes = []
        step = timedelta(seconds=30)
        for station in stations:
            in_pass = False
            pass_start = pass_tca = None
            max_el = 0.0
            current = start
            while current <= stop:
                jd = _datetime_to_jd(current)
                e, r, v = sat.sgp4(jd, 0.0)
                if e != 0:
                    current += step
                    continue
                el = _elevation_deg(r, station.latitude_deg,
                                    station.longitude_deg, station.altitude_m / 1000.0,
                                    current)
                if el >= min_el:
                    if not in_pass:
                        in_pass = True
                        pass_start = current
                        max_el = el
                    elif el > max_el:
                        max_el = el
                        pass_tca = current
                elif in_pass:
                    in_pass = False
                    passes.append(PassWindow(
                        station_name      = station.name,
                        aos               = pass_start,
                        los               = current,
                        tca               = pass_tca or pass_start,
                        max_elevation_deg = max_el,
                        duration_seconds  = (current - pass_start).total_seconds(),
                    ))
                current += step
        return passes
    except Exception:
        return []


def _elevation_deg(r_eci: list, lat_deg: float, lon_deg: float,
                   alt_km: float, epoch: datetime) -> float:
    """Approximate satellite elevation above a ground station (degrees)."""
    try:
        lat  = math.radians(lat_deg)
        lon  = math.radians(lon_deg)
        re   = 6378.137
        r_gs = [
            (re + alt_km) * math.cos(lat) * math.cos(lon),
            (re + alt_km) * math.cos(lat) * math.sin(lon),
            (re + alt_km) * math.sin(lat),
        ]
        dr = [r_eci[i] - r_gs[i] for i in range(3)]
        mag_dr = math.sqrt(sum(x*x for x in dr))
        if mag_dr < 1e-6:
            return -90.0
        mag_gs = math.sqrt(sum(x*x for x in r_gs))
        dot = sum(r_gs[i] * dr[i] for i in range(3))
        cos_angle = dot / (mag_gs * mag_dr)
        cos_angle = max(-1.0, min(1.0, cos_angle))
        el = math.degrees(math.asin(cos_angle)) - 90.0 + math.degrees(math.acos(cos_angle))
        return el
    except Exception:
        return -90.0
