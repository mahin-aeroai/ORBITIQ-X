"""
ORBITIQ-X — Knowledge Ingestion API
Phase 17.4

REST API for managing the knowledge ingestion framework.

Mounts at: /api/v2/ingestion
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text

from caem.ingestion.orchestrator import ADAPTER_REGISTRY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingestion", tags=["Knowledge Ingestion"])


# ---------------------------------------------------------------------------
# DEPENDENCIES
# ---------------------------------------------------------------------------

async def get_pg_session():
    from app.db.session import get_session
    async for session in get_session():
        yield session


def get_neo4j_driver():
    from app.graph.connection import get_driver
    try:
        return get_driver()
    except Exception:
        return None


def get_qdrant_client():
    try:
        from app.db.qdrant_session import get_qdrant
        return get_qdrant()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------------------------

class AdapterConfigUpdate(BaseModel):
    fetch_interval_s:    Optional[int]  = None
    max_records_per_run: Optional[int]  = None
    is_enabled:          Optional[bool] = None
    notes:               Optional[str]  = None


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@router.get("/adapters")
async def list_adapters(pg=Depends(get_pg_session)):
    """List all registered source adapters with their current schedule state."""
    try:
        rows = (await pg.execute(text("""
            SELECT adapter_name, source_tier, is_enabled, fetch_interval_s,
                   max_records_per_run, last_run_at, next_run_at,
                   total_runs, total_records, notes
            FROM ingestion_source_config
            ORDER BY source_tier, adapter_name
        """))).fetchall()
    except Exception as e:
        logger.warning(f"list_adapters query failed: {e}")
        return {"count": 0, "adapters": []}

    adapters = []
    for row in rows:
        r = dict(row._mapping)
        r["is_in_registry"] = r["adapter_name"] in ADAPTER_REGISTRY
        r["fetch_interval_hours"] = r["fetch_interval_s"] / 3600
        adapters.append(r)

    return {"count": len(adapters), "adapters": adapters}


@router.get("/adapters/{adapter_name}")
async def get_adapter(adapter_name: str, pg=Depends(get_pg_session)):
    """Get detailed status for a single adapter including recent run history."""
    config = (await pg.execute(
        text("SELECT * FROM ingestion_source_config WHERE adapter_name = :name"),
        {"name": adapter_name}
    )).fetchone()

    if not config:
        raise HTTPException(status_code=404, detail=f"Adapter not found: {adapter_name}")

    recent_runs = (await pg.execute(text("""
        SELECT job_id, started_at, completed_at, records_fetched,
               entities_created, entities_updated, contradictions, status
        FROM ingestion_schedule_log
        WHERE adapter_name = :name
        ORDER BY created_at DESC
        LIMIT 10
    """), {"name": adapter_name})).fetchall()

    return {
        "config":       dict(config._mapping),
        "recent_runs":  [dict(r._mapping) for r in recent_runs],
        "in_registry":  adapter_name in ADAPTER_REGISTRY,
    }


@router.post("/adapters/{adapter_name}/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(
    adapter_name: str,
    background:   BackgroundTasks,
    pg=Depends(get_pg_session),
    neo4j=Depends(get_neo4j_driver),
    qdrant=Depends(get_qdrant_client),
):
    """Trigger a manual ingestion run for a specific adapter (background task)."""
    if adapter_name not in ADAPTER_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Adapter not found: {adapter_name}. Available: {list(ADAPTER_REGISTRY.keys())}"
        )

    config = (await pg.execute(
        text("SELECT is_enabled FROM ingestion_source_config WHERE adapter_name = :name"),
        {"name": adapter_name}
    )).fetchone()

    if config and not config[0]:
        raise HTTPException(
            status_code=400,
            detail=f"Adapter {adapter_name} is disabled. Enable it first via PATCH /config.",
        )

    def _run_background():
        # IMPORTANT: do NOT reuse the request-scoped async `pg` session here.
        # FastAPI closes get_pg_session()'s session as soon as this request's
        # response is sent — BackgroundTasks callbacks run AFTER that point,
        # so the outer `pg` would already be closed/invalid by the time this
        # function body actually executes. IngestionOrchestrator also needs
        # a SYNC session (unawaited self.pg.execute() throughout
        # pipeline.py/orchestrator.py/provenance/service.py), not the async
        # one anyway — so this creates its own fresh sync session, exactly
        # like get_sync_pg_session() does for provenance.py, scoped to the
        # lifetime of this background task only.
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.config import get_settings
        from caem.ingestion.orchestrator import IngestionOrchestrator

        settings = get_settings()
        sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        engine = create_engine(sync_url, pool_pre_ping=True, pool_size=1, max_overflow=1)
        SessionLocal = sessionmaker(bind=engine)
        bg_session = SessionLocal()

        try:
            orchestrator = IngestionOrchestrator(bg_session, neo4j, qdrant)
            orchestrator.register_adapter(adapter_name)
            orchestrator.run_adapter(adapter_name)
        except Exception:
            logger.exception("ingestion_background_run_failed adapter=%s", adapter_name)
        finally:
            bg_session.close()
            engine.dispose()

    background.add_task(_run_background)

    return {
        "adapter_name": adapter_name,
        "status":       "queued",
        "message":      f"Ingestion run for {adapter_name} queued in background",
    }


@router.get("/schedule")
async def get_schedule(pg=Depends(get_pg_session)):
    """Return full ingestion schedule status for all adapters."""
    try:
        rows = (await pg.execute(text("""
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
        """))).fetchall()
    except Exception as e:
        logger.warning(f"get_schedule query failed: {e}")
        return {"schedule": [], "due_count": 0}

    return {
        "schedule":  [dict(r._mapping) for r in rows],
        "due_count": sum(1 for r in rows if r._mapping.get("is_due") and r._mapping.get("is_enabled")),
    }


@router.get("/log")
async def get_ingestion_log(
    adapter_name: Optional[str] = Query(None),
    status:       Optional[str] = Query(None),
    limit:        int           = Query(50, ge=1, le=200),
    pg=Depends(get_pg_session),
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

    rows = (await pg.execute(text(f"""
        SELECT job_id, adapter_name, started_at, completed_at,
               records_fetched, entities_created, entities_updated,
               relationships_added, contradictions, status, created_at
        FROM ingestion_schedule_log
        {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit
    """), params)).fetchall()

    return {"count": len(rows), "runs": [dict(r._mapping) for r in rows]}


@router.get("/log/{job_id}")
async def get_job_result(job_id: str, pg=Depends(get_pg_session)):
    """Return the full result for a specific ingestion job."""
    row = (await pg.execute(
        text("SELECT * FROM ingestion_schedule_log WHERE job_id = :job_id"),
        {"job_id": job_id}
    )).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return dict(row._mapping)


@router.patch("/adapters/{adapter_name}/config")
async def update_adapter_config(
    adapter_name: str,
    request:      AdapterConfigUpdate,
    pg=Depends(get_pg_session),
):
    """Update adapter configuration (interval, limits, enabled state)."""
    existing = (await pg.execute(
        text("SELECT adapter_name FROM ingestion_source_config WHERE adapter_name = :name"),
        {"name": adapter_name}
    )).fetchone()

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

    await pg.execute(
        text(f"UPDATE ingestion_source_config SET {', '.join(set_clauses)} WHERE adapter_name = :name"),
        params,
    )
    await pg.commit()

    return {"adapter_name": adapter_name, "status": "updated"}


@router.post("/adapters/{adapter_name}/enable")
async def enable_adapter(adapter_name: str, pg=Depends(get_pg_session)):
    await pg.execute(
        text("UPDATE ingestion_source_config SET is_enabled = true WHERE adapter_name = :name"),
        {"name": adapter_name},
    )
    await pg.commit()
    return {"adapter_name": adapter_name, "is_enabled": True}


@router.post("/adapters/{adapter_name}/disable")
async def disable_adapter(adapter_name: str, pg=Depends(get_pg_session)):
    await pg.execute(
        text("UPDATE ingestion_source_config SET is_enabled = false WHERE adapter_name = :name"),
        {"name": adapter_name},
    )
    await pg.commit()
    return {"adapter_name": adapter_name, "is_enabled": False}
