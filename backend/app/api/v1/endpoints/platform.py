"""
ORBITIQ-X — Platform Health API
=================================
Unified deep health check aggregating all platform subsystems.

Endpoint
─────────
  GET /platform/health    — deep health (all services, slow: ~2-5s)
  GET /platform/status    — scheduler + sync status (fast: <100ms)
  GET /platform/metrics   — Prometheus metric summary (fast)

Service health matrix
──────────────────────
  postgres        — pool connectivity (SELECT 1)
  redis           — ping roundtrip
  neo4j           — MATCH (n) RETURN count(n)
  vector_store    — pipeline availability (Qdrant/Weaviate bridge)
  minio           — HTTP HEAD on bucket endpoint
  digital_twin    — propagation recency check
  conjunction_engine — last screening time
  agents          — LangGraph + Anthropic config
  graphrag        — corpus + graph availability
  scheduler       — job registry + last run times
  catalog         — Space-Track reachability + object count

Overall status
───────────────
  healthy   — all core services reachable
  degraded  — 1+ non-core services down (platform still operational)
  unhealthy — postgres or digital_twin unavailable

Core services (outage → unhealthy): postgres
Non-core (outage → degraded):       redis, neo4j, vector_store, minio

This endpoint requires authentication (any role).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Individual subsystem probes ───────────────────────────────

async def _probe_postgres() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        from app.db.session import get_session_factory
        from sqlalchemy import text
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "healthy", "latency_ms": round((time.perf_counter()-t0)*1000, 1)}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)[:120]}


async def _probe_redis() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        from app.db.redis_session import get_redis
        redis = get_redis()
        if redis is None:
            return {"status": "unavailable", "error": "Redis client not initialised"}
        await redis.ping()
        return {"status": "healthy", "latency_ms": round((time.perf_counter()-t0)*1000, 1)}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)[:120]}


async def _probe_neo4j() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        from app.graph.connection import health_check
        result = await health_check()
        status = "healthy" if result.get("reachable") else "unavailable"
        return {
            "status":      status,
            "node_count":  result.get("node_count", 0),
            "latency_ms":  round((time.perf_counter()-t0)*1000, 1),
            "error":       result.get("error"),
        }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)[:120]}


async def _probe_vector_store() -> dict[str, Any]:
    """Probe vector store (Qdrant/Weaviate) via the GraphRAG bridge pipeline."""
    try:
        # Import the bridge using the same lazy-init pattern as rag.py
        from app.api.v1.endpoints.rag import _get_bridge
        bridge = _get_bridge()
        available = bridge._pipeline is not None
        return {
            "status":   "healthy" if available else "unavailable",
            "pipeline": available,
            "note":     "Qdrant/Weaviate via GraphRAG bridge",
        }
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)[:120]}


async def _probe_minio() -> dict[str, Any]:
    """Probe MinIO via an HTTP HEAD to the health endpoint."""
    t0 = time.perf_counter()
    try:
        import httpx
        from app.core.config import get_settings
        s = get_settings()
        url = f"http://{s.MINIO_HOST}:{s.MINIO_PORT}/minio/health/live"
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.head(url)
        ok = r.status_code in (200, 204)
        return {
            "status":     "healthy" if ok else "degraded",
            "latency_ms": round((time.perf_counter()-t0)*1000, 1),
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)[:120]}


async def _probe_digital_twin() -> dict[str, Any]:
    try:
        from app.digital_twin.services.orbital_state_service import (
            get_propagation_meta_shared,
        )
        meta = await get_propagation_meta_shared()
        last = meta.get("last_propagation")
        objects_propagated = meta.get("objects_propagated", 0)

        age_minutes = None
        if last:
            try:
                dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                age_minutes = round(
                    (datetime.now(timezone.utc) - dt).total_seconds() / 60, 1
                )
            except Exception:
                pass

        status = "healthy"
        if objects_propagated == 0:
            status = "not_initialised"
        elif age_minutes is not None and age_minutes > 30:
            status = "stale"

        return {
            "status":             status,
            "objects":            objects_propagated,
            "last_propagation":   last,
            "age_minutes":        age_minutes,
            "propagation_seconds":meta.get("propagation_seconds"),
        }
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)[:120]}


async def _probe_conjunction_engine() -> dict[str, Any]:
    try:
        from app.db.redis_session import get_redis
        redis = get_redis()
        last_screening = None
        if redis:
            try:
                raw = await redis.get("orbitiq:conjunction_screening:last_run")
                last_screening = raw.decode() if raw else None
            except Exception:
                pass
        return {
            "status":        "operational",
            "last_screening":last_screening,
        }
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)[:120]}


async def _probe_agents() -> dict[str, Any]:
    try:
        langgraph_ok = False
        try:
            from langgraph.graph import StateGraph  # noqa: F401
            langgraph_ok = True
        except ImportError:
            pass

        anthropic_ok = False
        try:
            from app.core.config import get_settings
            anthropic_ok = bool(get_settings().ANTHROPIC_API_KEY.get_secret_value())
        except Exception:
            pass

        from app.services.agent_service import _TASK_STORE
        active = sum(1 for t in _TASK_STORE.values() if t.status.value == "running")

        status = "healthy" if (langgraph_ok and anthropic_ok) else "degraded"
        return {
            "status":        status,
            "langgraph":     langgraph_ok,
            "anthropic":     anthropic_ok,
            "active_tasks":  active,
            "total_tasks":   len(_TASK_STORE),
        }
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)[:120]}


async def _probe_graphrag() -> dict[str, Any]:
    try:
        from app.graph.connection import is_available
        neo4j_ok = is_available()
        return {
            "status":         "healthy" if neo4j_ok else "degraded",
            "neo4j_available":neo4j_ok,
        }
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)[:120]}


async def _probe_scheduler() -> dict[str, Any]:
    try:
        from app.services.catalog_scheduler import get_scheduler
        scheduler = get_scheduler()
        if scheduler is None:
            return {"status": "not_started", "jobs": []}

        jobs = []
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id":           job.id,
                "name":         job.name,
                "next_run_utc": next_run.isoformat() if next_run else None,
            })

        return {
            "status": "running" if scheduler.running else "stopped",
            "job_count": len(jobs),
            "jobs": jobs,
        }
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)[:120]}


# ── GET /platform/health ─────────────────────────────────────

@router.get(
    "/health",
    summary="Unified platform deep health check",
    description=(
        "Aggregates health status from all platform subsystems. "
        "Runs all probes in parallel — typical response time 2–5 seconds. "
        "Returns overall status: healthy | degraded | unhealthy. "
        "Core services (postgres) outage → unhealthy. "
        "Non-core outage (redis, neo4j, minio) → degraded. "
        "Requires authentication."
    ),
)
async def platform_health() -> ORJSONResponse:
    t0 = time.perf_counter()

    # Run all probes in parallel
    (
        postgres, redis, neo4j, vector_store, minio,
        digital_twin, conjunction_engine, agents, graphrag, scheduler
    ) = await asyncio.gather(
        _probe_postgres(),
        _probe_redis(),
        _probe_neo4j(),
        _probe_vector_store(),
        _probe_minio(),
        _probe_digital_twin(),
        _probe_conjunction_engine(),
        _probe_agents(),
        _probe_graphrag(),
        _probe_scheduler(),
        return_exceptions=True,  # never let a probe crash the endpoint
    )

    # Convert exceptions to error dicts
    def _safe(result) -> dict:
        if isinstance(result, Exception):
            return {"status": "error", "error": str(result)[:120]}
        return result  # type: ignore[return-value]

    services = {
        "postgres":          _safe(postgres),
        "redis":             _safe(redis),
        "neo4j":             _safe(neo4j),
        "vector_store":      _safe(vector_store),
        "minio":             _safe(minio),
        "digital_twin":      _safe(digital_twin),
        "conjunction_engine":_safe(conjunction_engine),
        "agents":            _safe(agents),
        "graphrag":          _safe(graphrag),
        "scheduler":         _safe(scheduler),
    }

    # Update Prometheus gauges
    try:
        from app.core.metrics import REDIS_AVAILABLE, NEO4J_AVAILABLE, MINIO_AVAILABLE, VECTOR_STORE_AVAILABLE
        REDIS_AVAILABLE.set(1 if services["redis"].get("status") == "healthy" else 0)
        NEO4J_AVAILABLE.set(1 if services["neo4j"].get("status") == "healthy" else 0)
        MINIO_AVAILABLE.set(1 if services["minio"].get("status") == "healthy" else 0)
        VECTOR_STORE_AVAILABLE.set(1 if services["vector_store"].get("status") == "healthy" else 0)
    except Exception:
        pass

    # Determine overall status
    core_healthy = services["postgres"].get("status") == "healthy"
    non_core_unhealthy = any(
        services[svc].get("status") not in ("healthy", "operational", "running", "not_initialised", "unknown")
        for svc in ("redis", "neo4j", "vector_store", "minio")
    )

    if not core_healthy:
        overall = "unhealthy"
    elif non_core_unhealthy:
        overall = "degraded"
    else:
        overall = "healthy"

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    return ORJSONResponse(
        content={
            "overall":      overall,
            "checked_at":   datetime.now(timezone.utc).isoformat(),
            "elapsed_ms":   elapsed_ms,
            "services":     services,
        },
        status_code=200 if overall != "unhealthy" else 503,
    )


# ── GET /platform/status ─────────────────────────────────────

@router.get(
    "/status",
    summary="Scheduler and sync status (fast)",
    description=(
        "Returns scheduler job status and last successful sync times. "
        "Fast endpoint (<100ms) — does not probe external services. "
        "Suitable for dashboard polling."
    ),
)
async def platform_status() -> ORJSONResponse:
    from datetime import datetime, timezone

    # Scheduler
    scheduler_info = await _probe_scheduler()

    # Catalog sync
    catalog_status: dict = {}
    try:
        from app.services.catalog_scheduler import get_latest_sync_report
        report = await get_latest_sync_report()
        if report:
            catalog_status = {
                "status":          report.get("status"),
                "last_sync":       str(report.get("completed_at", "")),
                "satellites":      report.get("satellites_updated", 0),
                "sync_mode":       report.get("sync_mode"),
                "failure_reason":  report.get("failure_reason"),
            }
    except Exception as exc:
        catalog_status = {"error": str(exc)[:80]}

    # Digital twin propagation
    twin_info: dict = {}
    try:
        from app.digital_twin.services.orbital_state_service import (
            get_propagation_meta_shared,
        )
        meta = await get_propagation_meta_shared()
        twin_info = {
            "objects_propagated":  meta.get("objects_propagated", 0),
            "last_propagation":    meta.get("last_propagation"),
            "propagation_seconds": meta.get("propagation_seconds"),
            "live_objects":        meta.get("objects_propagated", 0),
        }
    except Exception as exc:
        twin_info = {"error": str(exc)[:80]}

    return ORJSONResponse(content={
        "checked_at":  datetime.now(timezone.utc).isoformat(),
        "scheduler":   scheduler_info,
        "catalog":     catalog_status,
        "digital_twin":twin_info,
    })
