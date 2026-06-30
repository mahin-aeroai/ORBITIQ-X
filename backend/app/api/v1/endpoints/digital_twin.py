"""
ORBITIQ-X — Orbital Digital Twin API
======================================
REST API for the real-time orbital digital twin engine.

Endpoints
─────────
  GET  /digital-twin/state/{norad_id}      — live propagated state
  GET  /digital-twin/forecast/{norad_id}   — orbit forecast (1–30 days)
  GET  /digital-twin/density               — orbital density heatmap
  GET  /digital-twin/conjunctions/future   — predicted conjunction graph
  POST /digital-twin/simulate-maneuver     — maneuver simulation
  GET  /digital-twin/regime-health         — space environment health
  GET  /digital-twin/status                — twin engine status + last propagation
  POST /digital-twin/propagate             — trigger manual catalog propagation
  GET  /digital-twin/cesium/states         — Cesium-ready satellite positions
  GET  /digital-twin/weather               — current space weather conditions

Graceful degradation
─────────────────────
  If propagation has not run yet, endpoints return 503 with a clear message.
  Individual state lookups return 404 if the object is not in the live cache.

CesiumJS Integration (Component 10)
──────────────────────────────────────
  GET /digital-twin/cesium/states returns CZML-compatible position data
  for all live satellites, ready for Cesium.js rendering.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request models ────────────────────────────────────────────

class ManeuverRequest(BaseModel):
    norad_id:    int    = Field(..., description="NORAD catalog number")
    delta_v_kms: float  = Field(..., gt=0, le=2.0, description="ΔV magnitude in km/s")
    direction:   str    = Field("prograde",
                                description="prograde | retrograde | radial | along-track | cross-track")
    description: str    = Field("", description="Human-readable scenario description")


class PropagateRequest(BaseModel):
    max_objects:   int | None = Field(None, ge=1, le=100_000)
    regime_filter: str | None = Field(None, description="Filter by regime: LEO | MEO | GEO")


# ── Service accessors ─────────────────────────────────────────

def _get_state_svc():
    from app.digital_twin.services.orbital_state_service import OrbitalStateService
    return OrbitalStateService()


def _get_forecast_svc():
    from app.digital_twin.services.twin_services import OrbitForecastService
    return OrbitForecastService()


def _get_density_engine():
    from app.digital_twin.services.twin_services import OrbitalDensityEngine
    return OrbitalDensityEngine()


def _get_maneuver_svc():
    from app.digital_twin.services.twin_services import ManeuverSimulationService
    return ManeuverSimulationService()


def _get_weather_bridge():
    from app.digital_twin.services.twin_services import SpaceWeatherBridge
    return SpaceWeatherBridge()


def _get_twin_repo():
    from app.digital_twin.repositories.digital_twin_repository import DigitalTwinRepository
    from app.db.redis_session import get_redis
    return DigitalTwinRepository(redis_client=get_redis())


def _require_live_states():
    """Raise 503 if no propagation has run yet."""
    from app.digital_twin.services.orbital_state_service import get_live_states, get_propagation_meta
    states = get_live_states()
    if not states:
        meta = get_propagation_meta()
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Digital twin not yet initialised. "
                           "Run POST /digital-twin/propagate or wait for scheduled propagation.",
                "last_propagation": meta["last_propagation"],
                "hint": "The digital twin propagates the full catalog on startup and every 5–15 minutes.",
            },
        )
    return states


# ── GET /digital-twin/state/{norad_id} ───────────────────────

@router.get(
    "/state/{norad_id}",
    summary="Live satellite state vector",
    description=(
        "Returns the current propagated state vector for one satellite: "
        "ECI position/velocity, ECEF position, geodetic coordinates (lat/lon/alt), "
        "orbital regime, and derived elements. "
        "Sourced from the last catalog propagation (refreshed every 5–15 min). "
        "Example: GET /digital-twin/state/25544 → ISS"
    ),
)
async def get_satellite_state(norad_id: int) -> ORJSONResponse:
    states = _require_live_states()
    state  = states.get(norad_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"NORAD {norad_id} not found in live twin. "
                   f"May be decayed, untracked, or outside current propagation scope.",
        )
    return ORJSONResponse(content=state.to_dict())


# ── GET /digital-twin/forecast/{norad_id} ────────────────────

@router.get(
    "/forecast/{norad_id}",
    summary="Orbit forecast trajectory",
    description=(
        "Generates a multi-day orbit forecast for one satellite. "
        "Returns future trajectory points, decay rate, and reentry prediction. "
        "Uses the existing SGP4 propagator + reentry monitor. "
        "Forecast horizons: 1, 3, 7, 14, 30 days."
    ),
)
async def get_orbit_forecast(
    norad_id: int,
    days:     Annotated[float, Query(ge=0.5, le=30)] = 7.0,
    step_min: Annotated[int,   Query(ge=1,   le=60)]  = 5,
) -> ORJSONResponse:
    # Get TLE from live state or catalog
    states = _require_live_states()
    state  = states.get(norad_id)

    # Try to get TLE from PostgreSQL
    tle1 = tle2 = name = None
    try:
        from app.db.session import get_session_factory
        from app.db.models.satellites import Satellite
        from sqlalchemy import select

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(Satellite).where(Satellite.norad_id == norad_id)
            )
            sat = result.scalar_one_or_none()
            if sat:
                tle1 = sat.tle_line1
                tle2 = sat.tle_line2
                name = sat.name
    except Exception:
        pass

    if not tle1 or not tle2:
        if state:
            raise HTTPException(
                status_code=503,
                detail=f"NORAD {norad_id}: TLE not available in database. "
                       "Run catalog sync first.",
            )
        raise HTTPException(status_code=404, detail=f"NORAD {norad_id} not found.")

    # Get space weather for decay rate
    weather_bridge = _get_weather_bridge()
    f107 = await weather_bridge.get_f107()

    svc      = _get_forecast_svc()
    forecast = await svc.forecast(
        norad_id=norad_id,
        name=name or f"NORAD-{norad_id}",
        tle_line1=tle1,
        tle_line2=tle2,
        horizon_days=days,
        step_minutes=step_min,
        f107=f107,
    )

    # Cache in repository
    repo = _get_twin_repo()
    await repo.save_forecast(forecast)

    return ORJSONResponse(content=forecast.to_dict())


# ── GET /digital-twin/density ─────────────────────────────────

@router.get(
    "/density",
    summary="Orbital density heatmap",
    description=(
        "Returns the orbital density map: object counts, volume, density (objects/km³), "
        "and congestion/collision-exposure indices for each altitude band from VLEO to GEO. "
        "Computed from the last propagation cycle."
    ),
)
async def get_density_map() -> ORJSONResponse:
    states = _require_live_states()
    repo   = _get_twin_repo()

    # Try cached map
    density = await repo.get_density_map()
    if not density:
        # Compute from live states
        engine  = _get_density_engine()
        density = engine.compute_density_map(list(states.values()))
        await repo.save_density_map(density)

    return ORJSONResponse(content=density.to_dict())


# ── GET /digital-twin/conjunctions/future ────────────────────

@router.get(
    "/conjunctions/future",
    summary="Predicted future conjunctions",
    description=(
        "Returns the predictive conjunction graph: FutureConjunction nodes from Neo4j. "
        "These are conjunction events that have been forecast but not yet occurred, "
        "generated by propagating catalog orbits forward and applying early-warning "
        "screening. Requires Neo4j to be connected."
    ),
)
async def get_future_conjunctions(
    norad_id: Annotated[int | None, Query()] = None,
    min_pc:   Annotated[float, Query(ge=1e-8, le=1.0)] = 1e-6,
    limit:    Annotated[int, Query(ge=1, le=500)] = 50,
) -> ORJSONResponse:
    repo   = _get_twin_repo()
    events = await repo.get_future_conjunctions(
        norad_id=norad_id, min_pc=min_pc, limit=limit,
    )
    return ORJSONResponse(content={
        "count":  len(events),
        "min_pc": min_pc,
        "events": events,
        "graph_note": "Future conjunctions are stored in Neo4j as FutureConjunction nodes "
                      "with PREDICTED_CONJUNCTION relationships to Satellite nodes.",
    })


# ── POST /digital-twin/simulate-maneuver ─────────────────────

@router.post(
    "/simulate-maneuver",
    summary="Maneuver simulation",
    description=(
        "Simulates the effect of a propulsive maneuver on a satellite's orbit. "
        "Returns before/after orbital elements, fuel cost estimate, "
        "conjunction delta, re-entry risk change, and 7-day post-maneuver trajectory. "
        "Example: ISS raising orbit by 5 km to avoid conjunction."
    ),
)
async def simulate_maneuver(request: ManeuverRequest) -> ORJSONResponse:
    from app.digital_twin.models.twin_models import ManeuverScenario

    # Get TLE
    tle1 = tle2 = name = None
    try:
        from app.db.session import get_session_factory
        from app.db.models.satellites import Satellite
        from sqlalchemy import select

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(Satellite).where(Satellite.norad_id == request.norad_id)
            )
            sat = result.scalar_one_or_none()
            if sat:
                tle1 = sat.tle_line1
                tle2 = sat.tle_line2
                name = sat.name
    except Exception:
        pass

    if not tle1 or not tle2:
        raise HTTPException(
            status_code=404,
            detail=f"NORAD {request.norad_id} TLE not found. Run catalog sync first."
        )

    scenario = ManeuverScenario(
        norad_id=request.norad_id,
        delta_v_kms=request.delta_v_kms,
        direction=request.direction,
        description=request.description or f"{request.direction} burn ΔV={request.delta_v_kms} km/s",
    )

    svc    = _get_maneuver_svc()
    result = await svc.simulate(
        norad_id=request.norad_id,
        name=name or f"NORAD-{request.norad_id}",
        tle_line1=tle1,
        tle_line2=tle2,
        scenario=scenario,
    )
    return ORJSONResponse(content=result.to_dict())


# ── GET /digital-twin/regime-health ──────────────────────────

@router.get(
    "/regime-health",
    summary="Orbital environment health by regime",
    description=(
        "Returns the health assessment for each orbital regime: "
        "congestion index, sustainability score, active conjunctions, "
        "debris count, alert level (green/yellow/orange/red), "
        "and trend (stable/degrading/improving)."
    ),
)
async def get_regime_health() -> ORJSONResponse:
    states = _require_live_states()
    repo   = _get_twin_repo()

    # Get cached health or recompute
    health = await repo.get_health()
    if not health:
        density = await repo.get_density_map()
        if not density:
            engine  = _get_density_engine()
            density = engine.compute_density_map(list(states.values()))

        engine = _get_density_engine()
        health = engine.compute_regime_health(density)
        await repo.save_health(health)

    return ORJSONResponse(content=health.to_dict())


# ── GET /digital-twin/status ──────────────────────────────────

@router.get(
    "/status",
    summary="Digital twin engine status",
    description=(
        "Returns the current status of the Orbital Digital Twin Engine: "
        "last propagation time, objects in cache, propagation duration, "
        "regime distribution, and readiness for queries."
    ),
)
async def get_twin_status() -> ORJSONResponse:
    from app.digital_twin.services.orbital_state_service import (
        get_live_states, get_propagation_meta_shared
    )
    from app.digital_twin.repositories.digital_twin_repository import _FORECAST_CACHE

    states = get_live_states()
    meta   = await get_propagation_meta_shared()

    # Regime counts — only reflects this worker's local state (regime
    # breakdown isn't cached to Redis, just the summary count). If this
    # worker hasn't propagated locally, this will be empty even though
    # objects_propagated above correctly reflects another worker's run.
    regime_counts: dict[str, int] = {}
    for s in states.values():
        r = s.orbital_regime.value
        regime_counts[r] = regime_counts.get(r, 0) + 1

    return ORJSONResponse(content={
        "status":             "operational" if meta["objects_propagated"] > 0 else "not_initialised",
        "last_propagation":   meta["last_propagation"],
        "objects_propagated": meta["objects_propagated"],
        "propagation_seconds":meta["propagation_seconds"],
        "last_error":         meta.get("last_error"),
        "regime_distribution":regime_counts,
        "cached_forecasts":   len(_FORECAST_CACHE),
        "components": {
            "orbital_state_service":     "✓ active",
            "orbit_forecast_service":    "✓ active",
            "orbital_density_engine":    "✓ active",
            "maneuver_simulation":       "✓ active",
            "space_weather_bridge":      "✓ active",
            "conjunction_forecast_graph":"✓ active",
        },
        "refresh_interval_min": 15,
        "cesium_endpoint":     "/api/v1/digital-twin/cesium/states",
    })


# ── POST /digital-twin/propagate ──────────────────────────────

@router.post(
    "/propagate",
    status_code=202,
    summary="Trigger manual catalog propagation",
    description=(
        "Triggers immediate propagation of the full satellite catalog to the current epoch. "
        "Normally runs on the 15-minute scheduler; use this to force a refresh. "
        "Returns 202 immediately; propagation runs in background."
    ),
)
async def trigger_propagation(
    request: PropagateRequest,
    background_tasks: BackgroundTasks,
) -> ORJSONResponse:
    run_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(
        _run_propagation_background,
        run_id=run_id,
        max_objects=request.max_objects,
        regime_filter=request.regime_filter,
    )
    return ORJSONResponse(
        status_code=202,
        content={
            "accepted":    True,
            "run_id":      run_id,
            "message":     f"Catalog propagation triggered (run_id={run_id}). "
                           "Poll GET /digital-twin/status for progress.",
            "max_objects": request.max_objects,
        },
    )


async def _run_propagation_background(
    run_id: str,
    max_objects: int | None,
    regime_filter: str | None,
) -> None:
    """Background task for catalog propagation."""
    try:
        from app.db.session import get_session_factory
        from app.db.redis_session import get_redis
        from app.digital_twin.services.orbital_state_service import OrbitalStateService
        from app.digital_twin.services.twin_services import OrbitalDensityEngine
        from app.digital_twin.repositories.digital_twin_repository import DigitalTwinRepository

        factory = get_session_factory()
        redis   = get_redis()

        async with factory() as session:
            svc    = OrbitalStateService(pg_session=session, redis_client=redis)
            summary = await svc.propagate_catalog(
                max_objects=max_objects,
                regime_filter=regime_filter,
            )

        # Update density after propagation
        from app.digital_twin.services.orbital_state_service import get_live_states
        states = get_live_states()
        if states:
            engine  = OrbitalDensityEngine()
            density = engine.compute_density_map(list(states.values()))
            repo    = DigitalTwinRepository(redis_client=redis)
            await repo.save_density_map(density)

            health = engine.compute_regime_health(density)
            await repo.save_health(health)

        logger.info(
            "background_propagation_complete run=%s objects=%d",
            run_id, summary.get("objects_propagated", 0),
        )
    except Exception as exc:
        logger.exception("background_propagation_failed run=%s", run_id)


# ── GET /digital-twin/cesium/states ──────────────────────────

@router.get(
    "/cesium/states",
    summary="CesiumJS-ready satellite positions",
    description=(
        "Returns satellite positions in a format directly consumable by CesiumJS. "
        "Each record contains NORAD ID, name, latitude, longitude, altitude, "
        "orbital regime, and object type for real-time 3D globe rendering. "
        "Refresh cycle: 5–15 minutes matching propagation cadence."
    ),
)
async def get_cesium_states(
    regime: Annotated[str | None, Query(description="Filter: LEO | MEO | GEO | SSO | VLEO")] = None,
    limit:  Annotated[int, Query(ge=1, le=60_000)] = 10_000,
) -> ORJSONResponse:
    from app.digital_twin.services.orbital_state_service import get_live_states
    states = get_live_states()

    if not states:
        raise HTTPException(503, detail="Digital twin not yet initialised.")

    all_states = list(states.values())
    if regime:
        all_states = [s for s in all_states if s.orbital_regime.value == regime.upper()]

    # Build Cesium-optimised payload
    cesium_objects = [
        {
            "id":      s.norad_id,
            "name":    s.name,
            "type":    s.object_type.value,
            "regime":  s.orbital_regime.value,
            "lat":     round(s.latitude_deg, 4),
            "lon":     round(s.longitude_deg, 4),
            "alt_km":  round(s.altitude_km, 2),
            "speed":   round(s.speed_kms, 3),
            "pos_eci": [round(x, 1) for x in s.position_eci_km],
        }
        for s in sorted(all_states, key=lambda s: s.norad_id)[:limit]
    ]

    epoch_str = all_states[0].epoch.isoformat() if all_states else None

    return ORJSONResponse(content={
        "epoch":         epoch_str,
        "count":         len(cesium_objects),
        "regime_filter": regime,
        "objects":       cesium_objects,
        "cesium_note":   "Feed this to Cesium.Viewer.entities for real-time satellite tracking.",
        "refresh_ms":    60_000,  # suggest 1-minute client refresh
    })


# ── GET /digital-twin/weather ─────────────────────────────────

@router.get(
    "/weather",
    summary="Space weather conditions affecting orbital environment",
    description=(
        "Returns current Kp index, F10.7 solar flux, geomagnetic storm category, "
        "atmospheric density multiplier, and SSA impact assessment. "
        "Cached for 30 minutes; data from NOAA SWPC."
    ),
)
async def get_space_weather() -> ORJSONResponse:
    bridge  = _get_weather_bridge()
    weather = await bridge.get_space_weather()
    return ORJSONResponse(content=weather)


# ── Redis diagnostics (Phase 18) ─────────────────────────────
# These endpoints live here (not in a separate control file) to avoid
# prefix conflicts. Both use the same /digital-twin prefix.

@router.get(
    "/redis-status",
    summary="Redis connection diagnostics",
    tags=["Digital Twin — Redis"],
)
async def get_redis_status_endpoint():
    """
    Detailed Redis connection diagnostics.
    Shows connection state, uptime, last error, and fix instructions.
    No auth required beyond the router-level dependency.
    """
    from app.db.redis_session import get_redis_status
    return get_redis_status()


@router.post(
    "/redis-reconnect",
    summary="Trigger manual Redis reconnect",
    tags=["Digital Twin — Redis"],
)
async def trigger_redis_reconnect_endpoint():
    """
    Manually trigger a Redis reconnection attempt.
    Use this after adding REDIS_URL to Railway Variables without redeploying.
    """
    from app.db.redis_session import reconnect_redis, get_redis_status

    success = await reconnect_redis()
    status  = get_redis_status()

    return {
        "reconnect_attempted": True,
        "success":             success,
        "redis_status":        status,
        "message": (
            "Redis connected. Digital Twin caching now active."
            if success else
            "Reconnect failed. Check REDIS_URL in Railway Variables."
        ),
    }
