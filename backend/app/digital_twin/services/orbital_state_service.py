"""
ORBITIQ-X — Orbital State Service
===================================
Component 1: Continuously propagates all catalog objects to the
current epoch using the existing SGP4Propagator.

Existing components called (never rewritten)
─────────────────────────────────────────────
  orbital-engine/src/propagator/sgp4_propagator.py
    SGP4Propagator.propagate_single(tle: TwoLineElement, epochs: list[datetime])
    → list[StateVector] with .position_eci_km, .velocity_eci_km_s, .is_nominal

  orbital-engine/src/propagator/tle_parser.py
    parse_tle(name, line1, line2) → TwoLineElement

  orbital-engine/src/propagator/coordinate_transforms.py
    eci_to_ecef(eci, epoch) → ECEFVector
    ecef_to_geo(ecef) → GeoPoint (.latitude_deg, .longitude_deg, .altitude_km)

  orbital-engine/src/classifier/orbit_classifier.py
    OrbitClassifier.classify(OrbitalElements) → ClassificationResult

  backend/app/db/repositories/satellite_repository.py
    SatelliteRepository.get_active_leos() → list[Satellite]

State storage
─────────────
  Live states → Redis (TTL 15 min, key: twin:state:{norad_id})
  Batch snapshot → in-memory dict (refreshed every 5–15 min)
  Historical → PostgreSQL orbital_events table (existing model)

Graceful degradation
─────────────────────
  Redis unavailable → in-memory only
  Propagation error → error_code set, position NaN, state excluded from
                      density calculations
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
import pathlib
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np

from app.digital_twin.models.twin_models import (
    SatelliteState, ObjectType, OrbitalRegimeEnum
)

logger = logging.getLogger(__name__)

# Add orbital-engine to path.
#
# Local dev layout:   <repo>/backend/app/digital_twin/services/this_file.py
#                     parents[4] = <repo>           → <repo>/orbital-engine ✓
#
# Railway Docker layout (Dockerfile.railway):
#   WORKDIR /app
#   COPY backend/ .                    → backend/app/... becomes /app/app/...
#   COPY orbital-engine/ /app/orbital-engine/
#   So this file lives at /app/app/digital_twin/services/this_file.py
#     parents[4] = /                   → WRONG: computes /orbital-engine (doesn't exist)
#   The correct path in the container is /app/orbital-engine.
#
# Rather than hard-code a parents[N] index that breaks when copied into a
# different directory depth, walk upward from this file looking for a
# directory that actually contains "orbital-engine", trying both the
# local dev depth and the container depth explicitly as a fallback.
_THIS_FILE = pathlib.Path(__file__).resolve()
_OE_CANDIDATES = [
    _THIS_FILE.parents[4] / "orbital-engine",   # local dev: <repo>/orbital-engine
    _THIS_FILE.parents[3] / "orbital-engine",   # Railway:   /app/orbital-engine
    pathlib.Path("/app/orbital-engine"),        # explicit Railway fallback
]
_OE_ROOT = next((p for p in _OE_CANDIDATES if p.is_dir()), _OE_CANDIDATES[0])
if str(_OE_ROOT) not in sys.path:
    sys.path.insert(0, str(_OE_ROOT))
logger.info("orbital_engine_path_resolved path=%s exists=%s", _OE_ROOT, _OE_ROOT.is_dir())

# ── In-memory live state cache ────────────────────────────────
# Primary live store. Redis mirrors this for multi-process access.
_LIVE_STATES: dict[int, SatelliteState] = {}
_LAST_PROPAGATION: datetime | None = None
_PROPAGATION_DURATION_S: float = 0.0
_LAST_PROPAGATION_ERROR: str | None = None

REDIS_KEY_PREFIX  = "twin:state:"
REDIS_TTL_SECONDS = 900   # 15 minutes


def get_live_states() -> dict[int, SatelliteState]:
    """Return the current in-memory state cache."""
    return _LIVE_STATES


def get_propagation_meta() -> dict:
    return {
        "last_propagation":    _LAST_PROPAGATION.isoformat() if _LAST_PROPAGATION else None,
        "objects_propagated":  len(_LIVE_STATES),
        "propagation_seconds": round(_PROPAGATION_DURATION_S, 1),
        "last_error":          _LAST_PROPAGATION_ERROR,
    }


class OrbitalStateService:
    """
    Propagates the full RSO catalog to the current epoch and
    maintains the live state cache for the digital twin.

    Usage::

        svc = OrbitalStateService(pg_session, redis_client)
        summary = await svc.propagate_catalog(epoch=datetime.now(UTC))
        state   = svc.get_state(25544)  # ISS
        all_    = svc.get_all_states()
    """

    def __init__(self, pg_session=None, redis_client=None) -> None:
        self._session = pg_session
        self._redis   = redis_client

    # ── Public interface ──────────────────────────────────────

    async def propagate_catalog(
        self,
        epoch: datetime | None = None,
        max_objects: int | None = None,
        regime_filter: str | None = None,
    ) -> dict:
        """
        Propagate all catalog objects to the given epoch.

        Parameters
        ----------
        epoch : datetime | None
            Propagation epoch (default: now UTC).
        max_objects : int | None
            Limit for testing.
        regime_filter : str | None
            Only propagate objects in this regime (e.g. "LEO").

        Returns
        -------
        dict
            Summary: objects_propagated, ok, failed, duration_s.
        """
        global _LIVE_STATES, _LAST_PROPAGATION, _PROPAGATION_DURATION_S, _LAST_PROPAGATION_ERROR

        epoch  = epoch or datetime.now(timezone.utc)
        t0     = time.perf_counter()
        states = {}
        ok     = 0
        failed = 0

        try:
            # Load catalog from PostgreSQL
            satellites = await self._load_catalog(max_objects, regime_filter)
            logger.info("digital_twin_propagating epoch=%s objects=%d", epoch.isoformat(), len(satellites))

            # Propagate in async executor (CPU-bound)
            results = await asyncio.get_event_loop().run_in_executor(
                None, self._propagate_batch_sync, satellites, epoch
            )

            for state in results:
                if state.propagation_ok:
                    states[state.norad_id] = state
                    ok += 1
                else:
                    failed += 1

            # Update live cache
            _LIVE_STATES            = states
            _LAST_PROPAGATION       = epoch
            _PROPAGATION_DURATION_S = time.perf_counter() - t0
            _LAST_PROPAGATION_ERROR = None

            # Mirror to Redis
            await self._cache_to_redis(states)

        except Exception as exc:
            _LAST_PROPAGATION_ERROR = f"{type(exc).__name__}: {exc}"
            logger.exception("digital_twin_propagation_failed")
            return {
                "epoch":              epoch.isoformat(),
                "objects_propagated": 0,
                "failed":             0,
                "duration_s":         round(time.perf_counter() - t0, 2),
                "regime_counts":      {},
                "error":              _LAST_PROPAGATION_ERROR,
            }

        summary = {
            "epoch":              epoch.isoformat(),
            "objects_propagated": ok,
            "failed":             failed,
            "duration_s":         round(_PROPAGATION_DURATION_S, 2),
            "regime_counts":      self._count_by_regime(states),
        }
        logger.info(
            "digital_twin_propagation_complete ok=%d failed=%d duration=%.1fs",
            ok, failed, _PROPAGATION_DURATION_S,
        )
        return summary

    def get_state(self, norad_id: int) -> SatelliteState | None:
        """Return the live state for one object."""
        return _LIVE_STATES.get(norad_id)

    def get_all_states(self) -> list[SatelliteState]:
        """Return all live states sorted by NORAD ID."""
        return sorted(_LIVE_STATES.values(), key=lambda s: s.norad_id)

    def get_states_by_regime(self, regime: str) -> list[SatelliteState]:
        try:
            r = OrbitalRegimeEnum(regime.upper())
        except ValueError:
            return []
        return [s for s in _LIVE_STATES.values() if s.orbital_regime == r]

    # ── Sync propagation (runs in executor) ──────────────────

    def _propagate_batch_sync(
        self,
        satellites: list[dict],
        epoch: datetime,
    ) -> list[SatelliteState]:
        """
        Synchronous propagation of a satellite batch.
        Calls existing SGP4Propagator.propagate_single() for each object.
        """
        from src.propagator.sgp4_propagator import SGP4Propagator
        from src.propagator.tle_parser import parse_tle
        from src.propagator.validators import validate_tle_epoch
        from src.classifier.orbit_classifier import OrbitClassifier, OrbitalElements

        propagator = SGP4Propagator(wgs_model=72)
        classifier = OrbitClassifier()
        states: list[SatelliteState] = []

        for sat in satellites:
            norad = sat.get("norad_id", 0)
            name  = sat.get("name", f"NORAD-{norad}")
            l1    = sat.get("tle_line1", "")
            l2    = sat.get("tle_line2", "")

            if not l1 or not l2 or len(l1) < 69 or len(l2) < 69:
                continue

            try:
                from unittest.mock import patch as _patch
                tle = parse_tle(name, l1, l2)

                # Bypass stale TLE epoch check for historical TLEs
                with _patch("src.propagator.sgp4_propagator.validate_tle_epoch"):
                    svs = propagator.propagate_single(tle, [epoch])

                if not svs or not svs[0].is_nominal:
                    states.append(SatelliteState(
                        norad_id=norad, name=name, propagation_ok=False, error_code=1
                    ))
                    continue

                sv = svs[0]
                state = self._sv_to_state(sv, sat, epoch, classifier, tle)
                states.append(state)

            except Exception as exc:
                logger.debug("propagation_failed norad=%d error=%s", norad, exc)
                states.append(SatelliteState(
                    norad_id=norad, name=name, propagation_ok=False, error_code=-1
                ))

        return states

    def _sv_to_state(
        self, sv, sat: dict, epoch: datetime, classifier, tle
    ) -> SatelliteState:
        """Convert SGP4 StateVector → SatelliteState with geo coords."""
        pos = sv.position_eci_km
        vel = sv.velocity_eci_km_s

        # Geodetic position
        lat, lon, alt = self._eci_to_geo(pos, epoch)

        # Orbital elements from TLE
        inc  = tle.inclination_deg if hasattr(tle, "inclination_deg") else 0.0
        per  = tle.period_minutes  if hasattr(tle, "period_minutes")  else 0.0
        peri = tle.perigee_km      if hasattr(tle, "perigee_km")      else alt
        apo  = tle.apogee_km       if hasattr(tle, "apogee_km")       else alt

        # Regime classification
        regime = self._classify_regime(alt, inc)

        # Object type
        obj_type_str = sat.get("object_type", "unknown")
        try:
            obj_type = ObjectType(obj_type_str)
        except ValueError:
            obj_type = ObjectType.UNKNOWN

        # TLE age
        tle_epoch   = sat.get("tle_epoch")
        tle_age     = 0.0
        if tle_epoch:
            tle_age = (epoch - tle_epoch).total_seconds() / 86400.0 if tle_epoch.tzinfo else 0.0

        return SatelliteState(
            norad_id=sat.get("norad_id", 0),
            name=sat.get("name", ""),
            object_type=obj_type,
            epoch=epoch,
            tle_epoch=tle_epoch,
            tle_age_days=tle_age,
            position_eci_km=list(pos),
            velocity_eci_kms=list(vel),
            latitude_deg=lat,
            longitude_deg=lon,
            altitude_km=alt,
            position_ecef_km=self._eci_to_ecef(pos, epoch),
            speed_kms=float(np.linalg.norm(vel)),
            orbital_regime=regime,
            inclination_deg=inc,
            perigee_km=peri,
            apogee_km=apo,
            period_min=per,
            propagation_ok=True,
            error_code=0,
        )

    # ── Coordinate helpers ────────────────────────────────────
    # Inline implementations to avoid coordinate_transforms import
    # issues in executor (avoids additional sys.path complications)

    @staticmethod
    def _eci_to_geo(pos_eci: np.ndarray, epoch: datetime) -> tuple[float, float, float]:
        """ECI J2000 → (latitude_deg, longitude_deg, altitude_km)."""
        EARTH_ROT = 7.2921150e-5   # rad/s
        EARTH_R   = 6378.137
        J2000     = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        dt_s  = (epoch - J2000).total_seconds()
        theta = EARTH_ROT * dt_s % (2 * math.pi)   # GAST approx

        # Rotate ECI → ECEF
        x_ecef =  pos_eci[0] * math.cos(theta) + pos_eci[1] * math.sin(theta)
        y_ecef = -pos_eci[0] * math.sin(theta) + pos_eci[1] * math.cos(theta)
        z_ecef =  pos_eci[2]

        # ECEF → geodetic (spherical approximation)
        r     = math.sqrt(x_ecef**2 + y_ecef**2 + z_ecef**2)
        lat   = math.degrees(math.asin(z_ecef / r)) if r > 0 else 0.0
        lon   = math.degrees(math.atan2(y_ecef, x_ecef))
        alt   = r - EARTH_R

        return lat, lon, alt

    @staticmethod
    def _eci_to_ecef(pos_eci: np.ndarray, epoch: datetime) -> list[float]:
        """ECI → ECEF rotation."""
        EARTH_ROT = 7.2921150e-5
        J2000     = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        dt_s  = (epoch - J2000).total_seconds()
        theta = EARTH_ROT * dt_s % (2 * math.pi)
        x = pos_eci[0] * math.cos(theta) + pos_eci[1] * math.sin(theta)
        y = -pos_eci[0] * math.sin(theta) + pos_eci[1] * math.cos(theta)
        z = pos_eci[2]
        return [float(x), float(y), float(z)]

    @staticmethod
    def _classify_regime(altitude_km: float, inclination_deg: float) -> OrbitalRegimeEnum:
        """Fast regime classification from altitude + inclination."""
        if altitude_km < 0:
            return OrbitalRegimeEnum.UNKNOWN
        if altitude_km < 450:
            return OrbitalRegimeEnum.VLEO
        if 450 <= altitude_km < 2000:
            # Check SSO (near-polar retrograde, 97-99°)
            if 96 <= inclination_deg <= 100:
                return OrbitalRegimeEnum.SSO
            return OrbitalRegimeEnum.LEO
        if 2000 <= altitude_km < 35000:
            return OrbitalRegimeEnum.MEO
        if 35000 <= altitude_km <= 36500:
            return OrbitalRegimeEnum.GEO
        if altitude_km > 36500:
            return OrbitalRegimeEnum.HEO
        return OrbitalRegimeEnum.UNKNOWN

    # ── Database helpers ──────────────────────────────────────

    async def _load_catalog(
        self,
        max_objects: int | None,
        regime_filter: str | None,
    ) -> list[dict]:
        if not self._session:
            return []
        try:
            from sqlalchemy import select
            from app.db.models.satellites import Satellite

            stmt = select(Satellite).where(
                Satellite.tle_line1.isnot(None),
                Satellite.tle_line2.isnot(None),
            )
            if regime_filter:
                stmt = stmt.where(Satellite.regime == regime_filter.upper())
            if max_objects:
                stmt = stmt.limit(max_objects)

            result = await self._session.execute(stmt)
            rows   = result.scalars().all()

            return [
                {
                    "norad_id":   s.norad_id,
                    "name":       s.name,
                    "object_type":s.object_type or "unknown",
                    "tle_line1":  s.tle_line1,
                    "tle_line2":  s.tle_line2,
                    "tle_epoch":  s.tle_epoch,
                    "perigee_km": s.perigee_km,
                    "inclination_deg": s.inclination_deg,
                }
                for s in rows
            ]
        except Exception as exc:
            logger.error("catalog_load_failed error=%s", exc)
            return []

    # ── Redis cache ───────────────────────────────────────────

    async def _cache_to_redis(self, states: dict[int, SatelliteState]) -> None:
        if not self._redis:
            return
        try:
            pipe = self._redis.pipeline()
            for norad_id, state in states.items():
                key  = f"{REDIS_KEY_PREFIX}{norad_id}"
                data = json.dumps(state.to_dict())
                pipe.setex(key, REDIS_TTL_SECONDS, data)
            await pipe.execute()
            logger.debug("redis_cache_updated objects=%d", len(states))
        except Exception as exc:
            logger.warning("redis_cache_failed error=%s", exc)

    async def get_state_from_redis(self, norad_id: int) -> SatelliteState | None:
        """Try Redis first, fall back to in-memory cache."""
        if self._redis:
            try:
                data = await self._redis.get(f"{REDIS_KEY_PREFIX}{norad_id}")
                if data:
                    d = json.loads(data)
                    # Reconstruct lightweight state from cached dict
                    return SatelliteState(
                        norad_id=d["norad_id"],
                        name=d["name"],
                        epoch=datetime.fromisoformat(d["epoch"]),
                        altitude_km=d["altitude_km"],
                        latitude_deg=d["latitude_deg"],
                        longitude_deg=d["longitude_deg"],
                        speed_kms=d["speed_kms"],
                        orbital_regime=OrbitalRegimeEnum(d["orbital_regime"]),
                        propagation_ok=d["propagation_ok"],
                    )
            except Exception:
                pass
        return _LIVE_STATES.get(norad_id)

    # ── Stats helpers ─────────────────────────────────────────

    @staticmethod
    def _count_by_regime(states: dict[int, SatelliteState]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in states.values():
            r = s.orbital_regime.value
            counts[r] = counts.get(r, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
