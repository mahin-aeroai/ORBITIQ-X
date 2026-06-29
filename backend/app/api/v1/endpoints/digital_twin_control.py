"""
ORBITIQ-X — Digital Twin Control API
Phase 18 — Redis Activation + Digital Twin

Endpoints for monitoring and controlling the Digital Twin:
  GET  /api/v1/digital-twin/redis-status    — Redis connection diagnostics
  POST /api/v1/digital-twin/redis-reconnect — Trigger manual Redis reconnect
  GET  /api/v1/digital-twin/status          — Full Digital Twin health
  POST /api/v1/digital-twin/activate        — Trigger Digital Twin propagation
  GET  /api/v1/digital-twin/live-positions  — Current propagated positions (sample)
  POST /api/v1/digital-twin/catalog-sync    — Trigger catalog sync + propagation
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/digital-twin", tags=["Digital Twin"])


def require_operator():
    pass  # Replace with existing JWT operator dependency


# ─── Redis diagnostics ────────────────────────────────────────────────────────

@router.get("/redis-status")
async def get_redis_status():
    """
    Detailed Redis connection diagnostics.
    Shows connection state, uptime, last error, and fix instructions.
    """
    from app.db.redis_session import get_redis_status
    return get_redis_status()


@router.post("/redis-reconnect")
async def trigger_redis_reconnect():
    """
    Manually trigger a Redis reconnection attempt.
    Useful after adding REDIS_URL to Railway Variables.
    """
    from app.db.redis_session import reconnect_redis, get_redis_status

    logger.info("Manual Redis reconnect triggered")
    success = await reconnect_redis()
    status  = get_redis_status()

    return {
        "reconnect_attempted": True,
        "success":             success,
        "redis_status":        status,
        "message": (
            "Redis connected successfully. Digital Twin caching is now active."
            if success else
            "Reconnect failed. Check REDIS_URL in Railway Variables."
        ),
    }


# ─── Digital Twin status ──────────────────────────────────────────────────────

@router.get("/status")
async def get_digital_twin_status():
    """
    Full Digital Twin health: Redis, propagation, satellite count,
    last run timestamp, and next scheduled run.
    """
    from app.db.redis_session import get_redis, get_redis_status

    redis        = get_redis()
    redis_status = get_redis_status()

    # Check in-memory propagation state
    twin_initialized = False
    propagated_count = 0
    last_propagation = None
    density_available = False

    try:
        from app.digital_twin.repositories.digital_twin_repository import (
            _DENSITY_SNAPSHOT, _HEALTH_SNAPSHOT
        )
        density_available = _DENSITY_SNAPSHOT is not None
        twin_initialized  = _HEALTH_SNAPSHOT is not None

        if twin_initialized and _HEALTH_SNAPSHOT:
            last_propagation = getattr(_HEALTH_SNAPSHOT, "timestamp", None)
    except Exception:
        pass

    # Check Redis for cached propagation data
    if redis:
        try:
            keys = await redis.keys("twin:state:*")
            propagated_count = len(keys)
            if propagated_count > 0:
                twin_initialized = True
        except Exception:
            pass

    # Determine overall status
    if twin_initialized and redis:
        dt_status = "operational"
    elif twin_initialized:
        dt_status = "degraded"  # Running but no Redis
    else:
        dt_status = "not_initialised"

    return {
        "status":               dt_status,
        "twin_initialized":     twin_initialized,
        "propagated_objects":   propagated_count,
        "density_map_ready":    density_available,
        "last_propagation_at":  str(last_propagation) if last_propagation else None,
        "redis":                redis_status,
        "capabilities": {
            "live_positions":   twin_initialized,
            "density_map":      density_available,
            "conjunction_sse":  redis is not None,
            "distributed_lock": redis is not None,
            "forecast_cache":   redis is not None,
        },
        "fix_if_not_initialised": (
            "POST /api/v1/digital-twin/activate to run the first propagation cycle."
        ) if not twin_initialized else None,
    }


# ─── Activation trigger ───────────────────────────────────────────────────────

@router.post("/activate")
async def activate_digital_twin(
    background: BackgroundTasks,
):
    """
    Trigger an immediate Digital Twin propagation cycle.

    Runs the orbital propagation in the background:
      1. Fetches active TLEs from PostgreSQL
      2. Propagates all objects using SGP4 to current epoch
      3. Stores live states in Redis (TTL 15 min) + in-memory
      4. Updates orbital density map
      5. Computes space environment health metrics

    Typically completes in 30–120 seconds for 29,198 objects.
    """
    from app.db.redis_session import get_redis

    async def _run_propagation():
        try:
            from app.db.session import get_async_session
            from app.digital_twin.services.orbital_state_service import OrbitalStateService
            from app.digital_twin.repositories.digital_twin_repository import DigitalTwinRepository
            from app.db.redis_session import get_redis as _get_redis

            redis = _get_redis()
            logger.info("Digital Twin activation started redis_available=%s", redis is not None)

            async for session in get_async_session():
                svc  = OrbitalStateService(pg_session=session, redis_client=redis)
                repo = DigitalTwinRepository(redis_client=redis)

                # Run propagation cycle
                result = await svc.propagate_all()
                logger.info(
                    "Digital Twin propagation complete objects=%s",
                    getattr(result, "propagated_count", "?"),
                )

        except Exception as exc:
            logger.error("Digital Twin activation failed: %s", exc, exc_info=True)

    background.add_task(_run_propagation)

    return {
        "status":   "activation_queued",
        "message":  "Digital Twin propagation cycle started in background. "
                    "Check /digital-twin/status for progress.",
        "redis_available": get_redis() is not None,
    }


# ─── Live positions sample ────────────────────────────────────────────────────

@router.get("/live-positions")
async def get_live_positions(
    regime: Optional[str] = Query(None, description="Filter by orbital regime: LEO/MEO/GEO/HEO/SSO"),
    limit:  int           = Query(100, ge=1, le=1000),
):
    """
    Return a sample of currently propagated satellite positions.

    Data comes from Redis (live, TTL 15 min) or in-memory snapshot.
    Returns propagated ECI/GEO positions for globe rendering.
    """
    from app.db.redis_session import get_redis

    redis   = get_redis()
    results: List[Dict[str, Any]] = []

    if redis:
        try:
            # Scan Redis for twin:state:* keys
            pattern = f"twin:state:*"
            keys    = await redis.keys(pattern)

            if regime:
                # Filter regime after fetch — or use a Redis set per regime
                count = 0
                for key in keys:
                    if count >= limit:
                        break
                    raw = await redis.get(key)
                    if not raw:
                        continue
                    import json
                    data = json.loads(raw)
                    if data.get("orbital_regime", "").upper() == regime.upper():
                        results.append(data)
                        count += 1
            else:
                # Return a sample up to limit
                import json
                for key in keys[:limit]:
                    raw = await redis.get(key)
                    if raw:
                        try:
                            results.append(json.loads(raw))
                        except Exception:
                            pass
        except Exception as exc:
            logger.warning("Redis position fetch failed: %s", exc)

    # Fall back to in-memory snapshot
    if not results:
        try:
            from app.digital_twin.repositories.digital_twin_repository import _DENSITY_SNAPSHOT
            if _DENSITY_SNAPSHOT:
                return {
                    "source":   "density_snapshot",
                    "count":    0,
                    "positions": [],
                    "note": "Live positions not available. Run /activate to propagate.",
                }
        except Exception:
            pass

    return {
        "source":           "redis_live" if redis else "in_memory",
        "count":            len(results),
        "regime_filter":    regime,
        "positions":        results[:limit],
        "redis_available":  redis is not None,
    }


# ─── Catalog sync trigger ─────────────────────────────────────────────────────

@router.post("/catalog-sync")
async def trigger_catalog_sync(
    background: BackgroundTasks,
    mode:       str = Query("incremental", description="full or incremental"),
):
    """
    Trigger a catalog sync (TLE refresh from Space-Track) followed by
    a Digital Twin propagation cycle.

    Modes:
      incremental — fetch TLEs updated in last 24 hours (fast, ~2 min)
      full        — fetch all active TLEs (slow, ~15 min, 29,198 objects)
    """
    if mode not in ("full", "incremental"):
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'incremental'")

    async def _run_sync_and_propagate():
        try:
            from app.services.catalog_scheduler import run_catalog_sync
            logger.info("Catalog sync triggered mode=%s", mode)
            await run_catalog_sync(mode=mode)
            logger.info("Catalog sync complete — triggering Digital Twin activation")

            # Chain Digital Twin activation
            from app.db.session import get_async_session
            from app.digital_twin.services.orbital_state_service import OrbitalStateService
            from app.db.redis_session import get_redis as _get_redis

            redis = _get_redis()
            async for session in get_async_session():
                svc = OrbitalStateService(pg_session=session, redis_client=redis)
                await svc.propagate_all()
                logger.info("Digital Twin propagation complete after catalog sync")
        except Exception as exc:
            logger.error("Catalog sync + propagation failed: %s", exc, exc_info=True)

    background.add_task(_run_sync_and_propagate)

    return {
        "status":   "sync_queued",
        "mode":     mode,
        "message": (
            f"{'Full' if mode == 'full' else 'Incremental'} catalog sync started. "
            "Digital Twin propagation will follow automatically."
        ),
    }
