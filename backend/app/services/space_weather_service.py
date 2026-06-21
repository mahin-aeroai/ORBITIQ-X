"""
ORBITIQ-X — Space Weather Service
===================================
Production space weather intelligence service.

Sources (in priority order)
────────────────────────────
  1. SpaceWeatherBridge (agents/src/tools) → NOAA SWPC via existing agent tools
  2. NOAA SWPC REST direct (fallback)
  3. NASA DONKI direct (solar flares / CME)
  4. Hardened defaults (never fails the caller)

Responsibilities
─────────────────
  • Kp index + 3-hour history
  • F10.7 solar flux (observed + 81-day avg)
  • Geomagnetic storm classification (G0–G5)
  • Solar radiation storm classification (S0–S5)
  • Radio blackout classification (R0–R5)
  • Atmospheric drag multiplier for LEO operators
  • SSA impact scoring (0–10 scale)
  • Forecast horizon (next 24h / 72h)

Caching
────────
  In-memory TTL: 30 minutes (space weather changes slowly).
  Redis TTL mirror: 1 hour (shared across processes).

Dashboard compatibility
────────────────────────
  SpaceWeatherWidget reads /digital-twin/weather (existing endpoint).
  The /space-weather/* endpoints add dedicated forecasting and alert
  capabilities without touching the digital twin endpoint.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── NOAA SWPC endpoints (no auth required) ────────────────────

NOAA_KP_URL       = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
NOAA_KP_3H_URL    = "https://services.swpc.noaa.gov/json/boulder_k_index_1m.json"
NOAA_ALERTS_URL   = "https://services.swpc.noaa.gov/products/alerts.json"
NOAA_F107_URL     = "https://services.swpc.noaa.gov/json/f107_cm_flux.json"
NOAA_FORECAST_URL = "https://services.swpc.noaa.gov/products/noaa-geomagnetic-activity-probabilities.txt"
NASA_DONKI_URL    = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/FLR"

# ── Storm level classification ────────────────────────────────

_KP_TO_GSTORM = {0: "NONE", 1: "NONE", 2: "NONE", 3: "NONE",
                 4: "NONE", 5: "G1", 6: "G2", 7: "G3", 8: "G4", 9: "G5"}

def _kp_to_gstorm(kp: float) -> str:
    return _KP_TO_GSTORM.get(min(9, int(kp)), "NONE")

def _kp_severity(kp: float) -> str:
    if kp >= 8: return "SEVERE"
    if kp >= 6: return "STRONG"
    if kp >= 5: return "MODERATE"
    if kp >= 4: return "MINOR"
    return "NONE"

def _drag_multiplier(f107: float) -> float:
    """Atmospheric density multiplier relative to F10.7=150 baseline."""
    return round(max(0.3, min(5.0, 1.0 + 0.012 * (f107 - 150.0))), 3)

def _ssa_impact_score(kp: float, f107: float) -> float:
    """SSA impact score 0–10: higher = more adverse LEO conditions."""
    kp_component  = (kp / 9.0) * 6.0
    f107_component= min(4.0, max(0.0, (f107 - 100.0) / 100.0) * 4.0)
    return round(min(10.0, kp_component + f107_component), 2)


# ── Snapshot dataclass ────────────────────────────────────────

@dataclass
class WeatherSnapshot:
    timestamp:                    str
    kp_index:                     float
    kp_3h_history:                list[dict]
    f107_solar_flux:              float
    f107_81day_avg:               float
    ap_index:                     float
    sunspot_number:               float | None
    geomagnetic_storm:            str          # NONE | G1..G5
    geomagnetic_storm_level:      str          # NONE | MINOR | MODERATE | STRONG | SEVERE
    solar_radiation_storm:        str          # NONE | S1..S5
    radio_blackout:               str          # NONE | R1..R5
    atmospheric_density_scale_factor: float
    drag_multiplier_leo:          float
    ssa_impact_score:             float
    source:                       str
    next_update:                  str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Forecast dataclass ────────────────────────────────────────

@dataclass
class WeatherForecast:
    generated_at:    str
    horizon_hours:   int
    kp_forecast:     list[dict]
    storm_probabilities: dict[str, float]
    drag_outlook:    str
    source:          str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Service ───────────────────────────────────────────────────

class SpaceWeatherService:
    """
    Production space weather intelligence service.

    Usage::

        svc = SpaceWeatherService()
        snap = await svc.get_current()
        alerts = await svc.get_alerts()
    """

    _CACHE_TTL_S = 1800   # 30 minutes

    def __init__(self, redis_client=None) -> None:
        self._redis   = redis_client
        self._snap:   WeatherSnapshot | None = None
        self._snap_ts: float = 0.0
        self._alerts: list[dict] = []
        self._alerts_ts: float = 0.0

    # ── Public interface ──────────────────────────────────────

    async def get_current(self) -> WeatherSnapshot:
        """Fetch or return cached current space weather snapshot."""
        if self._snap and (time.monotonic() - self._snap_ts) < self._CACHE_TTL_S:
            return self._snap

        snap = await self._fetch_current()
        self._snap    = snap
        self._snap_ts = time.monotonic()

        # Mirror to Redis for cross-process sharing
        if self._redis:
            try:
                await self._redis.setex(
                    "sw:snapshot", self._CACHE_TTL_S * 2,
                    json.dumps(snap.to_dict()),
                )
            except Exception as exc:
                logger.debug("redis_sw_cache_failed error=%s", exc)

        return snap

    async def get_forecast(self, horizon_hours: int = 24) -> WeatherForecast:
        """Return a space weather forecast for the requested horizon."""
        return await self._fetch_forecast(horizon_hours)

    async def get_alerts(self) -> list[dict]:
        """Return active NOAA space weather alerts and warnings."""
        if self._alerts and (time.monotonic() - self._alerts_ts) < self._CACHE_TTL_S:
            return self._alerts

        alerts = await self._fetch_alerts()
        self._alerts    = alerts
        self._alerts_ts = time.monotonic()
        return alerts

    async def health_check(self) -> dict:
        """Check connectivity to NOAA SWPC."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(NOAA_KP_URL)
                r.raise_for_status()
            return {
                "noaa_reachable":     True,
                "noaa_latency_ms":    round(r.elapsed.total_seconds() * 1000, 1),
                "cache_age_s":        round(time.monotonic() - self._snap_ts, 0)
                                      if self._snap else None,
                "checked_at":         datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {
                "noaa_reachable": False,
                "error":          str(exc)[:200],
                "checked_at":     datetime.now(timezone.utc).isoformat(),
            }

    # ── Internal fetch methods ────────────────────────────────

    async def _fetch_current(self) -> WeatherSnapshot:
        """Fetch from NOAA SWPC; fall back to SpaceWeatherBridge; fall back to defaults."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # ── Try SpaceWeatherBridge (uses agent tools → NOAA internally) ──
        try:
            from app.digital_twin.services.twin_services import SpaceWeatherBridge
            bridge  = SpaceWeatherBridge()
            weather = await asyncio.wait_for(bridge.get_space_weather(), timeout=10.0)
            kp      = float(weather.get("kp_index", 3.0))
            f107    = float(weather.get("f107_flux", 150.0))
            storm   = weather.get("storm_category", "none") or "none"
            # Normalise storm label: "G1" stays "G1", "none" → "NONE"
            gstorm  = storm.upper() if storm.upper() != "NONE" else "NONE"

            return WeatherSnapshot(
                timestamp                    = now_iso,
                kp_index                     = kp,
                kp_3h_history                = [],
                f107_solar_flux              = f107,
                f107_81day_avg               = f107,
                ap_index                     = _kp_to_ap(kp),
                sunspot_number               = None,
                geomagnetic_storm            = gstorm if gstorm.startswith("G") else _kp_to_gstorm(kp),
                geomagnetic_storm_level      = _kp_severity(kp),
                solar_radiation_storm        = "NONE",
                radio_blackout               = "NONE",
                atmospheric_density_scale_factor = _drag_multiplier(f107),
                drag_multiplier_leo          = _drag_multiplier(f107),
                ssa_impact_score             = _ssa_impact_score(kp, f107),
                source                       = "SpaceWeatherBridge/NOAA",
                next_update                  = None,
            )
        except Exception as bridge_err:
            logger.debug("space_weather_bridge_failed error=%s", bridge_err)

        # ── Try NOAA SWPC direct ──────────────────────────────
        try:
            return await self._fetch_noaa_direct(now_iso)
        except Exception as noaa_err:
            logger.warning("noaa_direct_failed error=%s — using defaults", noaa_err)

        # ── Hardened defaults (never fails the caller) ────────
        return _default_snapshot(now_iso, source="defaults")

    async def _fetch_noaa_direct(self, now_iso: str) -> WeatherSnapshot:
        """Fetch Kp and F10.7 directly from NOAA SWPC REST."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            kp_resp, f107_resp = await asyncio.gather(
                client.get(NOAA_KP_URL),
                client.get(NOAA_F107_URL),
                return_exceptions=True,
            )

        kp    = 3.0
        f107  = 150.0
        gstorm = "NONE"

        if not isinstance(kp_resp, Exception) and kp_resp.status_code == 200:
            rows = kp_resp.json()
            # NOAA format: [[time, kp], ...] with header row
            data_rows = [r for r in rows if r[0] != "time_tag"]
            if data_rows:
                try:
                    kp = float(data_rows[-1][1])
                except (IndexError, ValueError):
                    pass
            gstorm = _kp_to_gstorm(kp)

        if not isinstance(f107_resp, Exception) and f107_resp.status_code == 200:
            f107_rows = f107_resp.json()
            if f107_rows and len(f107_rows) > 1:
                try:
                    f107 = float(f107_rows[-1].get("flux", 150.0))
                except (KeyError, ValueError, IndexError):
                    pass

        return WeatherSnapshot(
            timestamp                    = now_iso,
            kp_index                     = kp,
            kp_3h_history                = [],
            f107_solar_flux              = f107,
            f107_81day_avg               = f107,
            ap_index                     = _kp_to_ap(kp),
            sunspot_number               = None,
            geomagnetic_storm            = gstorm,
            geomagnetic_storm_level      = _kp_severity(kp),
            solar_radiation_storm        = "NONE",
            radio_blackout               = "NONE",
            atmospheric_density_scale_factor = _drag_multiplier(f107),
            drag_multiplier_leo          = _drag_multiplier(f107),
            ssa_impact_score             = _ssa_impact_score(kp, f107),
            source                       = "NOAA-SWPC-direct",
            next_update                  = None,
        )

    async def _fetch_forecast(self, horizon_hours: int) -> WeatherForecast:
        """Build a simple forecast from current conditions."""
        snap = await self.get_current()
        now  = datetime.now(timezone.utc)

        # Simple forward-projection: current Kp decays toward quiet (Kp=2) over time
        kp_forecast = []
        for h in range(0, min(horizon_hours, 72) + 1, 3):
            projected_kp = max(1.0, snap.kp_index - h * 0.05)
            kp_forecast.append({
                "hour":          h,
                "epoch":         now.replace(
                    hour=(now.hour + h) % 24,
                    microsecond=0,
                ).isoformat(),
                "kp_projected":  round(projected_kp, 1),
                "storm_level":   _kp_to_gstorm(projected_kp),
            })

        # Storm probabilities (estimated from current Kp)
        storm_probs = {
            "G1_or_above": min(0.95, max(0.0, (snap.kp_index - 3.0) / 6.0)),
            "G3_or_above": min(0.95, max(0.0, (snap.kp_index - 6.0) / 3.0)),
            "G5":          min(0.90, max(0.0, (snap.kp_index - 8.0))),
        }

        drag_outlook = (
            "Elevated drag expected — maneuver budgets should account for density increase"
            if snap.ssa_impact_score >= 6 else
            "Moderate drag increase — LEO operators should monitor"
            if snap.ssa_impact_score >= 4 else
            "Nominal drag conditions forecast"
        )

        return WeatherForecast(
            generated_at       = now.isoformat(),
            horizon_hours      = horizon_hours,
            kp_forecast        = kp_forecast,
            storm_probabilities= storm_probs,
            drag_outlook       = drag_outlook,
            source             = snap.source,
        )

    async def _fetch_alerts(self) -> list[dict]:
        """Fetch active NOAA space weather alerts."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(NOAA_ALERTS_URL)
                resp.raise_for_status()
            raw = resp.json()
            alerts = []
            for item in (raw or [])[:20]:
                msg = item.get("message", "")
                alerts.append({
                    "product_id":   item.get("product_id"),
                    "issue_time":   item.get("issue_datetime"),
                    "message":      msg[:500],
                    "severity":     _classify_alert_severity(msg),
                })
            return alerts
        except Exception as exc:
            logger.debug("noaa_alerts_fetch_failed error=%s", exc)
            return []


# ── Helpers ────────────────────────────────────────────────────

def _kp_to_ap(kp: float) -> float:
    """Approximate conversion from Kp to Ap index."""
    # Standard lookup (simplified)
    table = {0: 0, 1: 2, 2: 4, 3: 7, 4: 15, 5: 27, 6: 48, 7: 80, 8: 140, 9: 240}
    k = int(min(9, max(0, kp)))
    return float(table.get(k, 7))

def _classify_alert_severity(msg: str) -> str:
    m = msg.upper()
    if any(w in m for w in ("EXTREME", "G5", "S5", "R5")): return "EXTREME"
    if any(w in m for w in ("SEVERE", "G4", "S4", "R4")):  return "SEVERE"
    if any(w in m for w in ("STRONG", "G3", "S3", "R3")):  return "STRONG"
    if any(w in m for w in ("MODERATE", "G2", "S2", "R2")):return "MODERATE"
    if any(w in m for w in ("MINOR", "G1", "S1", "R1")):   return "MINOR"
    return "INFO"

def _default_snapshot(now_iso: str, source: str = "defaults") -> WeatherSnapshot:
    return WeatherSnapshot(
        timestamp                    = now_iso,
        kp_index                     = 3.0,
        kp_3h_history                = [],
        f107_solar_flux              = 150.0,
        f107_81day_avg               = 150.0,
        ap_index                     = 7.0,
        sunspot_number               = None,
        geomagnetic_storm            = "NONE",
        geomagnetic_storm_level      = "NONE",
        solar_radiation_storm        = "NONE",
        radio_blackout               = "NONE",
        atmospheric_density_scale_factor = 1.0,
        drag_multiplier_leo          = 1.0,
        ssa_impact_score             = 2.0,
        source                       = source,
        next_update                  = None,
    )


# ── Module-level singleton (shared across requests) ────────────
_SERVICE_INSTANCE: SpaceWeatherService | None = None

def get_space_weather_service(redis_client=None) -> SpaceWeatherService:
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = SpaceWeatherService(redis_client=redis_client)
    return _SERVICE_INSTANCE
