"""
ORBITIQ-X — Space Weather Intelligence API
===========================================
Production endpoints for real-time and forecast space weather data.

Endpoints
──────────
  GET /space-weather/current    — Kp, F10.7, storm levels, drag multiplier
  GET /space-weather/forecast   — 24/72h forward projection
  GET /space-weather/alerts     — Active NOAA alerts and warnings
  GET /space-weather/health     — NOAA SWPC connectivity check

Data sources
─────────────
  Primary:  SpaceWeatherBridge → NOAA SWPC via existing agent tools
  Fallback: NOAA SWPC REST direct (no auth required)
  Safety:   Hardened defaults — never fails the caller

Dashboard compatibility
────────────────────────
  SpaceWeatherWidget (frontend) reads /digital-twin/weather.
  These endpoints are additive — they do not replace or modify the
  existing digital twin space weather endpoint.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from app.services.space_weather_service import get_space_weather_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ── GET /space-weather/current ────────────────────────────────

@router.get(
    "/current",
    summary="Current space weather conditions",
    description=(
        "Real-time space weather snapshot including Kp index, F10.7 solar flux, "
        "geomagnetic storm classification (G0–G5), solar radiation storm level (S0–S5), "
        "radio blackout level (R0–R5), atmospheric drag multiplier for LEO operators, "
        "and SSA impact score (0–10). "
        "Cached for 30 minutes — reflects NOAA SWPC update cadence. "
        "Compatible with SpaceWeatherWidget (matches digital-twin/weather field names)."
    ),
)
async def get_current_weather() -> ORJSONResponse:
    from app.db.redis_session import get_redis
    svc  = get_space_weather_service(redis_client=get_redis())
    snap = await svc.get_current()
    d    = snap.to_dict()

    # Alias fields for SpaceWeatherWidget compatibility
    d["kp_index"]                         = snap.kp_index
    d["f107_solar_flux"]                  = snap.f107_solar_flux
    d["ap_index"]                         = snap.ap_index
    d["atmospheric_density_scale_factor"] = snap.atmospheric_density_scale_factor

    return ORJSONResponse(content=d)


# ── GET /space-weather/forecast ───────────────────────────────

@router.get(
    "/forecast",
    summary="Space weather forecast",
    description=(
        "Forward-looking space weather projection for the requested horizon. "
        "Provides per-3-hour Kp projections, storm probabilities, "
        "and atmospheric drag outlook for LEO mission planning. "
        "Horizon: 24h (default) or 72h maximum."
    ),
)
async def get_weather_forecast(
    horizon_hours: Annotated[int, Query(ge=6, le=72)] = 24,
) -> ORJSONResponse:
    from app.db.redis_session import get_redis
    svc      = get_space_weather_service(redis_client=get_redis())
    forecast = await svc.get_forecast(horizon_hours=horizon_hours)
    return ORJSONResponse(content=forecast.to_dict())


# ── GET /space-weather/alerts ─────────────────────────────────

@router.get(
    "/alerts",
    summary="Active space weather alerts",
    description=(
        "Returns active NOAA SWPC space weather alerts, watches, and warnings. "
        "Includes severity classification (MINOR to EXTREME) for each alert. "
        "Empty list returned gracefully when NOAA is unreachable."
    ),
)
async def get_weather_alerts() -> ORJSONResponse:
    from app.db.redis_session import get_redis
    svc    = get_space_weather_service(redis_client=get_redis())
    alerts = await svc.get_alerts()
    return ORJSONResponse(content={
        "count":  len(alerts),
        "alerts": alerts,
        "source": "NOAA-SWPC",
        "note":   "Empty list means no active alerts or NOAA unreachable.",
    })


# ── GET /space-weather/health ─────────────────────────────────

@router.get(
    "/health",
    summary="Space weather subsystem health",
    description=(
        "Checks NOAA SWPC REST API reachability and reports cache age. "
        "This endpoint makes one live HTTP request to NOAA — call sparingly."
    ),
)
async def get_weather_health() -> ORJSONResponse:
    from app.db.redis_session import get_redis
    svc    = get_space_weather_service(redis_client=get_redis())
    health = await svc.health_check()
    return ORJSONResponse(content=health)
