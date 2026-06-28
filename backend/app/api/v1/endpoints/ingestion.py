"""
ORBITIQ-X — Knowledge Ingestion API
Phase 17.4

REST API for managing the knowledge ingestion framework.

Mounts at: /api/v2/ingestion

Endpoints:
  GET    /api/v2/ingestion/adapters                  — List all registered adapters
  GET    /api/v2/ingestion/adapters/{name}            — Adapter status and config
  POST   /api/v2/ingestion/adapters/{name}/run        — Trigger a manual run
  GET    /api/v2/ingestion/schedule                   — Full schedule status
  GET    /api/v2/ingestion/log                        — Recent run history
  GET    /api/v2/ingestion/log/{job_id}               — Single job result
  PATCH  /api/v2/ingestion/adapters/{name}/config     — Update adapter config
  POST   /api/v2/ingestion/adapters/{name}/enable     — Enable adapter
  POST   /api/v2/ingestion/adapters/{name}/disable    — Disable adapter
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel

from caem.ingestion.orchestrator import ADAPTER_REGISTRY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/ingestion", tags=["Knowledge Ingestion"])


# ---------------------------------------------------------------------------
# DEPENDENCY STUBS
# ---------------------------------------------------------------------------

def get_pg_session():
    raise NotImplementedError("Wire to ORBITIQ-X PostgreSQL session dependency")

def get_neo4j_driver():
    raise NotImplementedError("Wire to ORBITIQ-X Neo4j driver dependency")

def get_qdrant_client():
    raise NotImplementedError("Wire to ORBITIQ-X Qdrant client dependency")

def require_admin():
    pass  # Replace with admin JWT dependency


# ---------------------------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------------------------

class AdapterConfigUpdate(BaseModel):
    fetch_interval_s:    Optional[int]              = None
    max_records_per_run: Optional[int]              = None
    is_enabled:          Optional[bool]             = None
    notes:               Optional[str]              = None


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@router.get("/adapters")
async def list_adapters(
    _auth   = Depends(require_admin),
    pg      = Depends(get_pg_session),
):
    """List all registered source adapters with their current schedule state."""
    rows = pg.execute("""
        SELECT adapter_name, source_tier, is_enabled, fetch_interval_s,
               max_records_per_run, last_run_at, next_run_at,
               total_runs, total_records, notes
        FROM ingestion_source_config
        ORDER BY source_tier, adapter_name
    """).fetchall()

    adapters = []
    for row in rows:
        r = dict(row._mapping)
        r["is_in_registry"] = r["adapter_name"] in ADAPTER_REGISTRY
        r["fetch_interval_hours"] = r["fetch_interval_s"] / 3600
        adapters.append(r)

    return {"count": len(adapters), "adapters": adapters}


@router.get("/adapters/{adapter_name}")
async def get_adapter(
    adapter_name:   str,
    _auth           = Depends(require_admin),
    pg              = Depends(get_pg_session),
):
    """Get detailed status for a single adapter including recent run history."""
    config = pg.execute(
        "SELECT * FROM ingestion_source_config WHERE adapter_name = :name",
        {"name": adapter_name}
    ).fetchone()

    if not config:
        raise HTTPException(status_code=404, detail=f"Adapter not found: {adapter_name}")

    recent_runs = pg.execute("""
        SELECT job_id, started_at, completed_at, records_fetched,
               entities_created, entities_updated, contradictions, status
        FROM ingestion_schedule_log
        WHERE adapter_name = :name
        ORDER BY created_at DESC
        LIMIT 10
    """, {"name": adapter_name}).fetchall()

    return {
        "config":       dict(config._mapping),
        "recent_runs":  [dict(r._mapping) for r in recent_runs],
        "in_registry":  adapter_name in ADAPTER_REGISTRY,
    }


@router.post("/adapters/{adapter_name}/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(
    adapter_name:   str,
    background:     BackgroundTasks,
    _auth           = Depends(require_admin),
    pg              = Depends(get_pg_session),
    neo4j           = Depends(get_neo4j_driver),
    qdrant          = Depends(get_qdrant_client),
):
    """
    Trigger a manual ingestion run for a specific adapter.
    Runs asynchronously in the background.
    """
    if adapter_name not in ADAPTER_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Adapter not found: {adapter_name}. Available: {list(ADAPTER_REGISTRY.keys())}"
        )

    # Check adapter is enabled
    config = pg.execute(
        "SELECT is_enabled FROM ingestion_source_config WHERE adapter_name = :name",
        {"name": adapter_name}
    ).fetchone()

    if config and not config[0]:
        raise HTTPException(
            status_code=400,
            detail=f"Adapter {adapter_name} is disabled. Enable it first via PATCH /config."
        )

    def _run_background():
        from caem.ingestion.orchestrator import IngestionOrchestrator
        orchestrator = IngestionOrchestrator(pg, neo4j, qdrant)
        orchestrator.register_adapter(adapter_name)
        orchestrator.run_adapter(adapter_name)

    background.add_task(_run_background)

    return {
        "adapter_name":     adapter_name,
        "status":           "queued",
        "message":          f"Ingestion run for {adapter_name} queued in background",
    }


@router.get("/schedule")
async def get_schedule(
    _auth   = Depends(require_admin),
    pg      = Depends(get_pg_session),
):
    """Return full ingestion schedule status for all adapters."""
    rows = pg.execute("""
        SELECT
            isc.adapter_name,
            isc.source_tier,
            isc.is_enabled,
            isc.fetch_interval_s,
            isc.last_run_at,
            isc.next_run_at,
            isc.total_runs,
            isc.total_records,
            CASE WHEN isc.next_run_at <= now() THEN true ELSE false END AS is_due,
            last_log.status AS last_status
        FROM ingestion_source_config isc
        LEFT JOIN LATERAL (
            SELECT status FROM ingestion_schedule_log
            WHERE adapter_name = isc.adapter_name
            ORDER BY created_at DESC LIMIT 1
        ) last_log ON true
        ORDER BY isc.source_tier, isc.adapter_name
    """).fetchall()

    return {
        "schedule": [dict(r._mapping) for r in rows],
        "due_count": sum(1 for r in rows if r._mapping.get("is_due") and r._mapping.get("is_enabled")),
    }


@router.get("/log")
async def get_ingestion_log(
    adapter_name:   Optional[str]   = Query(None),
    status:         Optional[str]   = Query(None),
    limit:          int             = Query(50, ge=1, le=200),
    _auth           = Depends(require_admin),
    pg              = Depends(get_pg_session),
):
    """Return recent ingestion run history."""
    where = []
    params: Dict[str, Any] = {"limit": limit}

    if adapter_name:
        where.append("adapter_name = :adapter_name")
        params["adapter_name"] = adapter_name
    if status:
        where.append("status = :status")
        params["status"] = status

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = pg.execute(f"""
        SELECT job_id, adapter_name, started_at, completed_at,
               records_fetched, entities_created, entities_updated,
               relationships_added, contradictions, status, created_at
        FROM ingestion_schedule_log
        {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit
    """, params).fetchall()

    return {"count": len(rows), "runs": [dict(r._mapping) for r in rows]}


@router.get("/log/{job_id}")
async def get_job_result(
    job_id: str,
    _auth   = Depends(require_admin),
    pg      = Depends(get_pg_session),
):
    """Return the full result for a specific ingestion job."""
    row = pg.execute(
        "SELECT * FROM ingestion_schedule_log WHERE job_id = :job_id",
        {"job_id": job_id}
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return dict(row._mapping)


@router.patch("/adapters/{adapter_name}/config")
async def update_adapter_config(
    adapter_name:   str,
    request:        AdapterConfigUpdate,
    _auth           = Depends(require_admin),
    pg              = Depends(get_pg_session),
):
    """Update adapter configuration (interval, limits, enabled state)."""
    existing = pg.execute(
        "SELECT adapter_name FROM ingestion_source_config WHERE adapter_name = :name",
        {"name": adapter_name}
    ).fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail=f"Adapter not found: {adapter_name}")

    set_clauses = ["updated_at = now()"]
    params: Dict[str, Any] = {"name": adapter_name}

    if request.fetch_interval_s is not None:
        set_clauses.append("fetch_interval_s = :interval")
        params["interval"] = request.fetch_interval_s
    if request.max_records_per_run is not None:
        set_clauses.append("max_records_per_run = :max_records")
        params["max_records"] = request.max_records_per_run
    if request.is_enabled is not None:
        set_clauses.append("is_enabled = :is_enabled")
        params["is_enabled"] = request.is_enabled
    if request.notes is not None:
        set_clauses.append("notes = :notes")
        params["notes"] = request.notes

    pg.execute(
        f"UPDATE ingestion_source_config SET {', '.join(set_clauses)} WHERE adapter_name = :name",
        params
    )

    return {"adapter_name": adapter_name, "status": "updated"}


@router.post("/adapters/{adapter_name}/enable")
async def enable_adapter(
    adapter_name:   str,
    _auth           = Depends(require_admin),
    pg              = Depends(get_pg_session),
):
    pg.execute(
        "UPDATE ingestion_source_config SET is_enabled = true WHERE adapter_name = :name",
        {"name": adapter_name}
    )
    return {"adapter_name": adapter_name, "is_enabled": True}


@router.post("/adapters/{adapter_name}/disable")
async def disable_adapter(
    adapter_name:   str,
    _auth           = Depends(require_admin),
    pg              = Depends(get_pg_session),
):
    pg.execute(
        "UPDATE ingestion_source_config SET is_enabled = false WHERE adapter_name = :name",
        {"name": adapter_name}
    )
    return {"adapter_name": adapter_name, "is_enabled": False}
