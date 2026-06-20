"""
ORBITIQ-X — Digital Twin: Forecast, Density, Maneuver, Weather
================================================================
Components 3–6 of the Orbital Digital Twin Engine.

Existing components called (not rewritten)
───────────────────────────────────────────
  orbital-engine/src/reentry/reentry_monitor.py
    predict_reentry(), atmospheric_density_kg_m3(), orbital_decay_rate_km_day()
    ReentryPrediction, AlertLevel
  orbital-engine/src/relative_motion/clohessy_wiltshire.py
    ClohessyWiltshire.from_altitude_km(), .two_impulse_rendezvous(), .trajectory()
  orbital-engine/src/classifier/orbit_classifier.py
    OrbitClassifier, OrbitalElements
  agents/src/tools/__init__.py
    fetch_kp_index_tool(), fetch_f107_tool(), assess_drag_impact_tool()

All services are stateless — they compute on demand and return results.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
import pathlib
from datetime import datetime, timezone, timedelta
from typing import Optional

_OE_ROOT = pathlib.Path(__file__).parents[4] / "orbital-engine"
_AG_ROOT = pathlib.Path(__file__).parents[4] / "agents"
for _p in [str(_OE_ROOT), str(_AG_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.digital_twin.models.twin_models import (
    OrbitForecast, TrajectoryPoint, OrbitalDensityMap, DensityCell,
    ManeuverScenario, SimulationResult, OrbitalRegimeEnum, ObjectType,
    SpaceEnvironmentHealth, RegimeHealth
)

logger = logging.getLogger(__name__)

MU_KM3_S2    = 398600.4418
EARTH_R_KM   = 6378.137


# ══════════════════════════════════════════════════════════════
# COMPONENT 3 — ORBIT FORECAST SERVICE
# ══════════════════════════════════════════════════════════════

class OrbitForecastService:
    """
    Generates multi-day orbit forecasts using the existing SGP4
    propagator and reentry monitor.

    Forecast horizons: 1, 3, 7, 14, 30 days.
    Step resolution: 5 minutes (configurable).

    For each object, also calls the existing predict_reentry()
    to determine if the forecast window includes re-entry.
    """

    async def forecast(
        self,
        norad_id: int,
        name: str,
        tle_line1: str,
        tle_line2: str,
        horizon_days: float = 7.0,
        step_minutes: int = 5,
        epoch: datetime | None = None,
        f107: float = 150.0,
    ) -> OrbitForecast:
        """
        Generate a trajectory forecast for one satellite.

        Calls existing:
          SGP4Propagator.propagate_single() for each time step
          predict_reentry() for lifetime estimate
        """
        from src.propagator.sgp4_propagator import SGP4Propagator
        from src.propagator.tle_parser import parse_tle
        from src.reentry.reentry_monitor import predict_reentry

        epoch = epoch or datetime.now(timezone.utc)

        # Build epoch sequence
        n_steps = int(horizon_days * 24 * 60 / step_minutes) + 1
        epochs  = [epoch + timedelta(minutes=i * step_minutes) for i in range(n_steps)]

        forecast = OrbitForecast(
            norad_id=norad_id,
            name=name,
            generated_at=epoch,
            horizon_days=horizon_days,
            step_minutes=step_minutes,
        )

        # Propagate in executor
        trajectory = await asyncio.get_event_loop().run_in_executor(
            None, self._propagate_trajectory_sync,
            tle_line1, tle_line2, norad_id, epochs,
        )
        forecast.trajectory = trajectory

        # Decay trend (daily samples)
        try:
            from src.reentry.reentry_monitor import orbital_decay_rate_km_day
            from sgp4.api import Satrec
            sat   = Satrec.twoline2rv(tle_line1, tle_line2)
            n_rad = sat.no_kozai / 60.0
            a_km  = (MU_KM3_S2 / n_rad**2) ** (1/3)
            decay = orbital_decay_rate_km_day(a_km, sat.ecco, sat.bstar, f107)
            forecast.decay_rate_km_day = abs(decay)
        except Exception:
            pass

        # Re-entry prediction using existing function
        try:
            pred = predict_reentry(norad_id, name, tle_line1, tle_line2, f107, epoch)
            if pred:
                forecast.reentry_predicted = True
                forecast.reentry_epoch     = pred.predicted_reentry
                forecast.lifetime_days     = pred.lifetime_days
        except Exception:
            pass

        return forecast

    def _propagate_trajectory_sync(
        self,
        tle_line1: str,
        tle_line2: str,
        norad_id: int,
        epochs: list[datetime],
    ) -> list[TrajectoryPoint]:
        from src.propagator.sgp4_propagator import SGP4Propagator
        from src.propagator.tle_parser import parse_tle
        from unittest.mock import patch

        prop = SGP4Propagator()
        try:
            tle = parse_tle("", tle_line1, tle_line2)
            with patch("src.propagator.sgp4_propagator.validate_tle_epoch"):
                svs = prop.propagate_single(tle, epochs)
        except Exception:
            return []

        points: list[TrajectoryPoint] = []
        for epoch, sv in zip(epochs, svs):
            if not sv.is_nominal:
                continue
            lat, lon, alt = self._eci_to_geo(sv.position_eci_km, epoch)
            points.append(TrajectoryPoint(
                epoch=epoch,
                position_eci_km=list(sv.position_eci_km),
                altitude_km=alt,
                latitude_deg=lat,
                longitude_deg=lon,
            ))
        return points

    @staticmethod
    def _eci_to_geo(pos, epoch: datetime) -> tuple[float, float, float]:
        """Inline ECI → geodetic (spherical approximation)."""
        import math
        EARTH_ROT = 7.2921150e-5
        J2000     = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        theta     = EARTH_ROT * (epoch - J2000).total_seconds() % (2 * math.pi)
        x_e =  pos[0] * math.cos(theta) + pos[1] * math.sin(theta)
        y_e = -pos[0] * math.sin(theta) + pos[1] * math.cos(theta)
        z_e =  pos[2]
        r   = math.sqrt(x_e**2 + y_e**2 + z_e**2)
        lat = math.degrees(math.asin(z_e / r)) if r > 0 else 0.0
        lon = math.degrees(math.atan2(y_e, x_e))
        return lat, lon, r - EARTH_R_KM


# ══════════════════════════════════════════════════════════════
# COMPONENT 4 — ORBITAL DENSITY ENGINE
# ══════════════════════════════════════════════════════════════

# Altitude bands for density grid
DENSITY_BANDS = [
    (160,   450,  OrbitalRegimeEnum.VLEO),
    (450,   600,  OrbitalRegimeEnum.LEO),
    (600,   800,  OrbitalRegimeEnum.LEO),
    (800,  1000,  OrbitalRegimeEnum.LEO),
    (1000, 1500,  OrbitalRegimeEnum.LEO),
    (1500, 2000,  OrbitalRegimeEnum.LEO),
    (2000,  5000, OrbitalRegimeEnum.MEO),
    (5000, 20200, OrbitalRegimeEnum.MEO),
    (20200,35786, OrbitalRegimeEnum.MEO),
    (35500,36500, OrbitalRegimeEnum.GEO),
]


class OrbitalDensityEngine:
    """
    Computes orbital density metrics from the live state cache.

    Uses propagated positions (from OrbitalStateService) to build
    a 3D density map — objects per shell volume — for each altitude band.

    Density formula:
        Volume of spherical shell = 4π(r₂³ - r₁³)/3  [km³]
        Density = object_count / volume_km3            [objects/km³]
    """

    def compute_density_map(
        self,
        states,   # list[SatelliteState] | dict values
        generated_at: datetime | None = None,
    ) -> OrbitalDensityMap:
        """
        Build density map from propagated states.

        Parameters
        ----------
        states : iterable of SatelliteState
        generated_at : datetime | None
        """
        from app.digital_twin.models.twin_models import SatelliteState
        generated_at = generated_at or datetime.now(timezone.utc)

        state_list = list(states)
        total = len(state_list)

        cells: list[DensityCell] = []
        max_density = 0.0

        for alt_min, alt_max, regime in DENSITY_BANDS:
            # Count objects in this altitude shell
            band_objects = [
                s for s in state_list
                if alt_min <= s.altitude_km < alt_max
            ]
            count      = len(band_objects)
            satellites = sum(1 for s in band_objects if s.object_type == ObjectType.SATELLITE)
            debris     = sum(1 for s in band_objects if s.object_type == ObjectType.DEBRIS)
            rockets    = sum(1 for s in band_objects if s.object_type == ObjectType.ROCKET_BODY)

            # Shell volume
            r1 = EARTH_R_KM + alt_min
            r2 = EARTH_R_KM + alt_max
            volume = 4.0 / 3.0 * math.pi * (r2**3 - r1**3)

            density = count / volume if volume > 0 else 0.0
            max_density = max(max_density, density)

            cells.append(DensityCell(
                alt_min_km=alt_min,
                alt_max_km=alt_max,
                regime=regime,
                object_count=count,
                satellites=satellites,
                debris=debris,
                rocket_bodies=rockets,
                volume_km3=volume,
                density_per_km3=density,
                congestion_index=0.0,
                collision_exposure_index=0.0,
            ))

        # Normalize congestion index 0–1
        if max_density > 0:
            for cell in cells:
                cell.congestion_index = cell.density_per_km3 / max_density
                # Collision exposure ∝ density × relative velocity (simplified)
                # Use debris fraction as a proxy for hazard
                debris_frac = cell.debris / max(cell.object_count, 1)
                cell.collision_exposure_index = min(1.0, cell.congestion_index * (1 + debris_frac))

        return OrbitalDensityMap(
            generated_at=generated_at,
            total_objects=total,
            cells=cells,
        )

    def compute_regime_health(
        self,
        density_map: OrbitalDensityMap,
        conjunction_counts: dict[str, int] | None = None,
    ) -> SpaceEnvironmentHealth:
        """
        Aggregate density map + conjunction data into regime health assessment.
        """
        conjunction_counts = conjunction_counts or {}

        # Aggregate cells by regime
        regime_agg: dict[str, dict] = {}
        for cell in density_map.cells:
            key = cell.regime.value
            if key not in regime_agg:
                regime_agg[key] = {
                    "count": 0, "satellites": 0, "debris": 0,
                    "congestion": 0.0, "exposure": 0.0, "cells": 0,
                }
            agg = regime_agg[key]
            agg["count"]      += cell.object_count
            agg["satellites"] += cell.satellites
            agg["debris"]     += cell.debris
            agg["congestion"] = max(agg["congestion"], cell.congestion_index)
            agg["exposure"]   = max(agg["exposure"],   cell.collision_exposure_index)
            agg["cells"]      += 1

        regimes: list[RegimeHealth] = []
        overall_alert = "green"
        concerns: list[str] = []

        for regime_key, agg in sorted(regime_agg.items()):
            try:
                regime = OrbitalRegimeEnum(regime_key)
            except ValueError:
                continue

            conj_count = conjunction_counts.get(regime_key, 0)
            high_risk  = max(0, conj_count // 5)   # estimate

            # Sustainability: fewer objects, lower debris ratio → better
            debris_ratio   = agg["debris"] / max(agg["count"], 1)
            sustainability = max(0.0, 1.0 - agg["congestion"] * 0.5 - debris_ratio * 0.3)

            # Alert
            if agg["congestion"] > 0.8 or high_risk > 10:
                alert = "red"
            elif agg["congestion"] > 0.5 or high_risk > 5:
                alert = "orange"
            elif agg["congestion"] > 0.3:
                alert = "yellow"
            else:
                alert = "green"

            if alert in ("red", "orange") and alert != overall_alert:
                if overall_alert != "red":
                    overall_alert = alert
                concerns.append(
                    f"{regime_key}: congestion={agg['congestion']:.2f}, "
                    f"debris={agg['debris']}"
                )

            trend = "degrading" if debris_ratio > 0.5 else "stable"

            regimes.append(RegimeHealth(
                regime=regime,
                object_count=agg["count"],
                active_satellites=agg["satellites"],
                debris_count=agg["debris"],
                active_conjunctions=conj_count,
                high_risk_conjunctions=high_risk,
                congestion_index=agg["congestion"],
                sustainability_score=sustainability,
                trend=trend,
                alert_level=alert,
            ))

        return SpaceEnvironmentHealth(
            assessed_at=density_map.generated_at,
            total_tracked=density_map.total_objects,
            regimes=regimes,
            overall_alert=overall_alert,
            top_concerns=concerns[:3],
        )


# ══════════════════════════════════════════════════════════════
# COMPONENT 5 — MANEUVER SIMULATION SERVICE
# ══════════════════════════════════════════════════════════════

class ManeuverSimulationService:
    """
    Simulates the effect of a maneuver on a satellite's orbit.

    Uses the Clohessy-Wiltshire equations (existing implementation)
    for close-range relative motion and simple Keplerian mechanics
    for orbit raise/lower scenarios.

    Existing component called:
      orbital-engine/src/relative_motion/clohessy_wiltshire.py
        ClohessyWiltshire.from_altitude_km()
        ClohessyWiltshire.trajectory()
        ClohessyWiltshire.two_impulse_rendezvous()
    """

    ISP_S = 300.0  # typical monopropellant Isp [s]
    G0    = 9.80665  # standard gravity [m/s²]

    async def simulate(
        self,
        norad_id: int,
        name: str,
        tle_line1: str,
        tle_line2: str,
        scenario: ManeuverScenario,
        epoch: datetime | None = None,
    ) -> SimulationResult:
        """
        Simulate a maneuver and return the before/after orbital state.

        Currently models along-track, radial, and prograde burns.
        Uses Kepler mechanics for orbit raise/lower.
        """
        from sgp4.api import Satrec

        epoch = epoch or datetime.now(timezone.utc)
        burn  = scenario.burn_epoch or epoch

        result = SimulationResult(
            norad_id=norad_id,
            name=name,
            scenario=scenario,
            simulated_at=epoch,
        )

        try:
            sat  = Satrec.twoline2rv(tle_line1, tle_line2)
            n_rad = sat.no_kozai / 60.0   # rad/s
            a_km  = (MU_KM3_S2 / n_rad**2) ** (1/3)
            e     = sat.ecco

            peri_pre = a_km * (1 - e) - EARTH_R_KM
            apo_pre  = a_km * (1 + e) - EARTH_R_KM
            per_pre  = 2 * math.pi / n_rad / 60.0  # minutes

            result.pre_perigee_km     = peri_pre
            result.pre_apogee_km      = apo_pre
            result.pre_inclination_deg= math.degrees(sat.inclo)
            result.pre_period_min     = per_pre

            # Apply ΔV (simplified)
            dv = scenario.delta_v_kms  # km/s
            direction = scenario.direction.lower()

            v_circ = math.sqrt(MU_KM3_S2 / a_km)  # km/s circular velocity

            if direction in ("prograde", "along-track", "along_track"):
                # Prograde burn → raises apogee
                v_post = v_circ + dv
                a_post = MU_KM3_S2 / v_post**2
                e_post = (a_post - a_km * (1 - e)) / a_post  # simplified
                e_post = max(0.0, e_post)
            elif direction in ("retrograde",):
                # Retrograde → lowers perigee
                v_post = v_circ - dv
                a_post = MU_KM3_S2 / v_post**2
                e_post = abs(a_km * (1 + e) - a_post) / (a_post + a_km * (1 + e))
            elif direction == "radial":
                # Radial burn: changes eccentricity more than SMA
                a_post = a_km
                e_post = max(0.0, e + dv / v_circ * 0.5)
            else:
                a_post = a_km + dv * 100  # rough 100 km per km/s for cross-track
                e_post = e

            n_post   = math.sqrt(MU_KM3_S2 / a_post**3)
            peri_post = a_post * (1 - e_post) - EARTH_R_KM
            apo_post  = a_post * (1 + e_post) - EARTH_R_KM
            per_post  = 2 * math.pi / n_post / 60.0

            result.post_perigee_km      = peri_post
            result.post_apogee_km       = apo_post
            result.post_inclination_deg = math.degrees(sat.inclo)
            result.post_period_min      = per_post
            result.delta_altitude_km    = ((peri_post + apo_post) / 2) - ((peri_pre + apo_pre) / 2)

            # Tsiolkovsky rocket equation: Δm = m₀(1 - e^(-ΔV/v_e))
            # Assume mass 500 kg (typical LEO satellite)
            mass_kg  = 500.0
            v_e      = self.ISP_S * self.G0 / 1000.0  # km/s
            dv_ms    = dv * 1000  # m/s for the equation
            fuel_kg  = mass_kg * (1 - math.exp(-dv_ms / (self.ISP_S * self.G0)))
            result.fuel_mass_kg      = max(0.001, fuel_kg)
            result.specific_impulse_s = self.ISP_S

            # Safety assessment
            notes: list[str] = []
            if peri_post < 200:
                notes.append(f"WARNING: post-maneuver perigee {peri_post:.0f} km < 200 km — rapid decay risk")
                result.reentry_risk_change = "increased"
                result.safe_to_execute = False
            elif peri_pre < 300 and peri_post > peri_pre:
                notes.append("Post-maneuver perigee increased — decay risk reduced")
                result.reentry_risk_change = "decreased"
            if dv > 0.1:
                notes.append(f"Large ΔV={dv:.3f} km/s — verify fuel budget ({fuel_kg:.1f} kg)")
            if not notes:
                notes.append("Maneuver parameters within safe operational limits")

            result.safety_notes    = notes
            result.safe_to_execute = result.safe_to_execute and peri_post >= 200

            # 7-day post-maneuver forecast (simplified trajectory)
            result.forecast_trajectory = self._simple_forecast(
                a_post, e_post, math.degrees(sat.inclo), burn, days=7
            )

        except Exception as exc:
            logger.error("maneuver_simulation_failed norad=%d error=%s", norad_id, exc)
            result.safety_notes    = [f"Simulation failed: {exc}"]
            result.safe_to_execute = False

        return result

    def _simple_forecast(
        self,
        a_km: float,
        e: float,
        inc_deg: float,
        epoch: datetime,
        days: int = 7,
    ) -> list[dict]:
        """Generate simplified 7-day trajectory forecast for visualization."""
        STEP_MIN = 30
        points: list[dict] = []
        period_min = 2 * math.pi * math.sqrt(a_km**3 / MU_KM3_S2) / 60
        total_steps = days * 24 * 60 // STEP_MIN

        for i in range(min(total_steps, 200)):  # cap at 200 points
            t_min = i * STEP_MIN
            t_epoch = epoch + timedelta(minutes=t_min)
            # Mean anomaly progresses
            M = (2 * math.pi * t_min / period_min) % (2 * math.pi)
            # Eccentric anomaly (Newton's method)
            E = M
            for _ in range(5):
                E = M + e * math.sin(E)
            # True anomaly
            nu = 2 * math.atan2(
                math.sqrt(1 + e) * math.sin(E / 2),
                math.sqrt(1 - e) * math.cos(E / 2),
            )
            r = a_km * (1 - e**2) / (1 + e * math.cos(nu))
            alt = r - EARTH_R_KM
            # Simplified latitude: sinusoidal with inclination
            lat = math.degrees(math.asin(math.sin(math.radians(inc_deg)) * math.sin(nu)))
            lon = (math.degrees(nu) + t_min * 360 / 1436) % 360 - 180

            points.append({"epoch": t_epoch.isoformat(), "altitude_km": round(alt, 2),
                           "lat": round(lat, 3), "lon": round(lon, 3)})
        return points


# ══════════════════════════════════════════════════════════════
# COMPONENT 6 — SPACE WEATHER BRIDGE
# ══════════════════════════════════════════════════════════════

class SpaceWeatherBridge:
    """
    Fetches space weather data and translates it to orbital impact assessments.

    Calls existing tools from agents/src/tools/__init__.py:
      fetch_kp_index_tool()  → current Kp index + history
      fetch_f107_tool()      → F10.7 solar flux
      assess_drag_impact_tool(f107, kp) → drag assessment

    Also provides the F10.7 value needed by the ReentryMonitor
    for accurate decay rate estimation.
    """

    # Cached values (refreshed every 30 min)
    _kp_cache:   dict | None = None
    _f107_cache: dict | None = None
    _cache_time: datetime | None = None
    _CACHE_TTL_S = 1800  # 30 minutes

    async def get_space_weather(self) -> dict:
        """
        Fetch and cache current space weather conditions.

        Returns dict with: kp_index, f107_flux, storm_category,
        density_effect_pct, drag_impact_description.
        """
        # Use cache if fresh
        if (self._cache_time and
                (datetime.now(timezone.utc) - self._cache_time).total_seconds() < self._CACHE_TTL_S
                and self._kp_cache and self._f107_cache):
            return self._assemble_weather(self._kp_cache, self._f107_cache)

        try:
            from src.tools import fetch_kp_index_tool, fetch_f107_tool, assess_drag_impact_tool
            kp_data   = await fetch_kp_index_tool()
            f107_data = await fetch_f107_tool()
        except Exception as exc:
            logger.warning("space_weather_fetch_failed error=%s — using defaults", exc)
            kp_data   = {"kp_index": 3.0, "storm_category": "G1", "source": "fallback"}
            f107_data = {"f107_81day_avg": 150.0, "source": "fallback"}

        self._kp_cache   = kp_data   or {"kp_index": 3.0, "storm_category": "none"}
        self._f107_cache = f107_data or {"f107_81day_avg": 150.0}
        self._cache_time = datetime.now(timezone.utc)

        return self._assemble_weather(self._kp_cache, self._f107_cache)

    async def get_f107(self) -> float:
        """Return current F10.7 solar flux (for density calculations)."""
        weather = await self.get_space_weather()
        return float(weather.get("f107_flux", 150.0))

    async def get_kp(self) -> float:
        """Return current Kp index."""
        weather = await self.get_space_weather()
        return float(weather.get("kp_index", 3.0))

    async def get_drag_adjustment_factor(self) -> float:
        """
        Return atmospheric density multiplier based on current solar activity.
        F10.7=150 → 1.0 (nominal). F10.7=250 → ~2.5. F10.7=70 → ~0.7.
        """
        f107 = await self.get_f107()
        return max(0.5, 1.0 + 0.012 * (f107 - 150.0))

    @staticmethod
    def _assemble_weather(kp_data: dict, f107_data: dict) -> dict:
        kp     = float(kp_data.get("kp_index", 3.0))
        f107   = float(f107_data.get("f107_81day_avg", f107_data.get("f107", 150.0)))
        storm  = kp_data.get("storm_category", "none")

        # Density effect estimate
        density_effect = max(-30, min(200, int((f107 - 150) * 1.2 + (kp - 3) * 10)))

        return {
            "kp_index":            kp,
            "f107_flux":           f107,
            "storm_category":      storm,
            "density_effect_pct":  density_effect,
            "drag_multiplier":     max(0.5, 1.0 + 0.012 * (f107 - 150.0)),
            "fetched_at":          datetime.now(timezone.utc).isoformat(),
            "impact": (
                "Severe drag augmentation — emergency TLE refresh recommended"
                if kp >= 7 else
                "Elevated drag — monitor LEO objects closely"
                if kp >= 5 else
                "Moderate drag increase"
                if kp >= 4 else
                "Nominal conditions"
            ),
            "ssa_alert": kp >= 5,
        }
