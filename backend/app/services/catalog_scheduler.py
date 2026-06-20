"""
ORBITIQ-X — Catalog Sync Scheduler
====================================
APScheduler-based job runner with:
  - 6-hour full catalog sync (Space-Track)
  - 2-hour incremental TLE refresh
  - Distributed Redis lock (prevents duplicate runs in multi-process deployments)
  - Metrics persistence to sync_metrics table
  - Manual trigger support via API
  - Failed job recovery (re-queues on next scheduled tick)

Architecture decision: APScheduler vs Celery
─────────────────────────────────────────────
  APScheduler runs in-process with AsyncIOScheduler — no broker
  required, low latency, correct for I/O-bound tasks (HTTP + DB writes).
  Celery is already in requirements for CPU-bound agent tasks.
  Do NOT use Celery for TLE sync — it would add serialization
  overhead for a 50MB TLE payload.

Distributed lock strategy
──────────────────────────
  Redis SET NX EX (set-if-not-exists with TTL) is the canonical
  distributed mutex for asyncio services. The lock key is:
      orbitiq:catalog_sync:lock
  TTL = 20 minutes (sync cannot run longer than this; if it does,
  the lock expires and the next pod can proceed).

  This is correct for single-AZ deployments. For multi-region,
  use Redlock (redis-py-lock) instead.

Phase 4 — Metrics persistence
──────────────────────────────
  Each sync run writes a SyncMetrics row to PostgreSQL.
  The catalog API reads this table for /catalog/metrics and /catalog/status.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.catalog_sync_service import CatalogSyncService, SyncReport

logger = logging.getLogger(__name__)

# ── Redis lock keys and TTLs ──────────────────────────────────
_LOCK_KEY     = "orbitiq:catalog_sync:lock"
_LOCK_TTL_S   = 1200      # 20 minutes — max expected sync duration
_METRICS_KEY  = "orbitiq:catalog_sync:last_report"

# ── Singleton scheduler ───────────────────────────────────────
_scheduler: AsyncIOScheduler | None = None


# ── Distributed lock ──────────────────────────────────────────

@asynccontextmanager
async def _distributed_lock(
    redis_client,
    lock_key: str,
    ttl_seconds: int,
    owner_id: str,
) -> AsyncIterator[bool]:
    """
    Async context manager: acquire a Redis NX lock, yield True if acquired.

    If the lock is already held by another process, yields False immediately
    (non-blocking). The caller should check the yielded value.

    Parameters
    ----------
    redis_client
        An async Redis client (redis.asyncio or aioredis).
    lock_key : str
        Redis key for the lock.
    ttl_seconds : int
        Lock expiry in seconds (auto-releases if process dies).
    owner_id : str
        Unique ID for this process/run (used for safe release).
    """
    acquired = await redis_client.set(
        lock_key,
        owner_id,
        nx=True,       # only set if key does not exist
        ex=ttl_seconds,
    )
    try:
        yield bool(acquired)
    finally:
        if acquired:
            # Only release if we still own the lock (avoids releasing
            # a lock that expired and was re-acquired by another process)
            current = await redis_client.get(lock_key)
            if current and current.decode() == owner_id:
                await redis_client.delete(lock_key)
                logger.debug("catalog_sync_lock released owner=%s", owner_id)


# ── Metrics persistence ───────────────────────────────────────

async def _persist_metrics(report: SyncReport, session) -> None:
    """
    Write SyncReport to the sync_metrics table.

    Table: sync_metrics (created by migration 0009)
    Falls back to Redis-only storage if the table doesn't exist yet.
    """
    try:
        from sqlalchemy import text
        await session.execute(
            text("""
                INSERT INTO sync_metrics (
                    sync_id, sync_mode, status, started_at, completed_at,
                    download_duration_s, downloaded_bytes, downloaded_records,
                    total_parsed, inserted, duplicates, satellites_updated,
                    parse_errors, stale_satellite_count, cache_keys_refreshed,
                    failure_reason, phases_completed
                ) VALUES (
                    :sync_id, :sync_mode, :status, :started_at, :completed_at,
                    :download_duration_s, :downloaded_bytes, :downloaded_records,
                    :total_parsed, :inserted, :duplicates, :satellites_updated,
                    :parse_errors, :stale_satellite_count, :cache_keys_refreshed,
                    :failure_reason, :phases_completed
                )
                ON CONFLICT (sync_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    completed_at = EXCLUDED.completed_at,
                    total_parsed = EXCLUDED.total_parsed,
                    inserted = EXCLUDED.inserted,
                    duplicates = EXCLUDED.duplicates,
                    satellites_updated = EXCLUDED.satellites_updated,
                    parse_errors = EXCLUDED.parse_errors,
                    stale_satellite_count = EXCLUDED.stale_satellite_count,
                    cache_keys_refreshed = EXCLUDED.cache_keys_refreshed,
                    failure_reason = EXCLUDED.failure_reason,
                    phases_completed = EXCLUDED.phases_completed
            """),
            {
                "sync_id":              report.sync_id,
                "sync_mode":            report.sync_mode,
                "status":               report.status,
                "started_at":           report.started_at,
                "completed_at":         report.completed_at,
                "download_duration_s":  report.download_duration_s,
                "downloaded_bytes":     report.downloaded_bytes,
                "downloaded_records":   report.downloaded_records,
                "total_parsed":         report.total_parsed,
                "inserted":             report.inserted,
                "duplicates":           report.duplicates,
                "satellites_updated":   report.satellites_updated,
                "parse_errors":         report.parse_errors,
                "stale_satellite_count": report.stale_satellite_count,
                "cache_keys_refreshed": report.cache_keys_refreshed,
                "failure_reason":       report.failure_reason,
                "phases_completed":     ",".join(report.phases_completed),
            },
        )
        await session.commit()
        logger.info("sync_metrics_persisted sync_id=%s", report.sync_id)

    except Exception as exc:
        # Table may not exist yet if migration 0009 hasn't run
        logger.warning("sync_metrics_persist_failed error=%s", exc)


async def _cache_report(redis_client, report: SyncReport) -> None:
    """Store the latest sync report in Redis for sub-millisecond reads."""
    if not redis_client:
        return
    try:
        import json
        await redis_client.set(
            _METRICS_KEY,
            json.dumps(report.as_dict()),
            ex=86400,  # 24h TTL
        )
    except Exception as exc:
        logger.warning("sync_report_cache_failed error=%s", exc)


# ── Job functions ─────────────────────────────────────────────

async def _run_conjunction_screening() -> None:
    """
    6-hour conjunction screening job.
    Runs AFTER full_catalog_sync completes via event coordination.
    Protected by a separate distributed lock.
    """
    from app.db.redis_session import get_redis
    from app.services.conjunction_analysis_service import ConjunctionAnalysisService
    from app.db.session import get_session_factory

    redis  = get_redis()
    run_id = str(uuid.uuid4())[:8]
    lock   = f"orbitiq:conjunction_screen:lock"

    logger.info("conjunction_screening_job_start run=%s", run_id)

    if redis:
        async with _distributed_lock(redis, lock, 3600, run_id) as acquired:
            if not acquired:
                logger.warning("conjunction_screening_job_skipped reason=lock_held")
                return
            await _execute_conjunction_screening(run_id, redis)
    else:
        await _execute_conjunction_screening(run_id, redis=None)


async def _execute_conjunction_screening(run_id: str, redis) -> None:
    from app.db.session import get_session_factory
    from app.services.conjunction_analysis_service import ConjunctionAnalysisService
    factory = get_session_factory()
    async with factory() as session:
        svc = ConjunctionAnalysisService(session, redis_client=redis)
        report = await svc.run_screening(run_id=run_id)
        logger.info(
            "conjunction_screening_job_complete run=%s status=%s conjunctions=%d",
            run_id, report.status, report.total_conjunctions,
        )


async def _run_graph_population() -> None:
    """Periodic PostgreSQL → Neo4j graph population."""
    from app.db.session import get_session_factory
    from app.graph.services.graph_population_service import GraphPopulationService
    from app.graph.connection import is_available
    import uuid

    if not is_available():
        logger.info("graph_population_job_skipped — Neo4j not available")
        return

    run_id = str(uuid.uuid4())[:8]
    logger.info("graph_population_job_start run=%s", run_id)
    factory = get_session_factory()
    async with factory() as session:
        svc = GraphPopulationService(session)
        report = await svc.populate_all(run_id=run_id)
        logger.info(
            "graph_population_job_complete run=%s status=%s sats=%d",
            run_id, report.status, report.satellites_synced,
        )


async def _run_digital_twin_propagation() -> None:
    """15-minute digital twin propagation — propagate full catalog to current epoch."""
    from app.digital_twin.services.orbital_state_service import OrbitalStateService
    from app.digital_twin.services.twin_services import OrbitalDensityEngine
    from app.digital_twin.repositories.digital_twin_repository import DigitalTwinRepository
    from app.db.session import get_session_factory
    from app.db.redis_session import get_redis
    import uuid
    run_id = str(uuid.uuid4())[:8]
    logger.info("digital_twin_propagation_start run=%s", run_id)
    try:
        factory = get_session_factory()
        redis   = get_redis()
        async with factory() as session:
            svc     = OrbitalStateService(pg_session=session, redis_client=redis)
            summary = await svc.propagate_catalog()
        from app.digital_twin.services.orbital_state_service import get_live_states
        states = get_live_states()
        if states:
            engine  = OrbitalDensityEngine()
            density = engine.compute_density_map(list(states.values()))
            repo    = DigitalTwinRepository(redis_client=redis)
            await repo.save_density_map(density)
            health = engine.compute_regime_health(density)
            await repo.save_health(health)
        logger.info("digital_twin_propagation_complete run=%s objects=%d",
                    run_id, summary.get("objects_propagated", 0))
    except Exception as exc:
        logger.exception("digital_twin_propagation_failed run=%s", run_id)


async def _run_full_catalog_sync() -> SyncReport | None:
    """
    6-hour full catalog sync job.
    Downloads all ~50K active non-decayed objects from Space-Track.
    Protected by distributed Redis lock to prevent duplicate runs.
    """
    from app.db.redis_session import get_redis
    redis = get_redis()

    run_id = str(uuid.uuid4())[:8]
    logger.info("catalog_sync_job_start job=full run=%s", run_id)

    # Acquire distributed lock (skip if Redis unavailable)
    if redis:
        async with _distributed_lock(redis, _LOCK_KEY, _LOCK_TTL_S, run_id) as acquired:
            if not acquired:
                logger.warning(
                    "catalog_sync_job_skipped job=full run=%s "
                    "reason=lock_held_by_another_process",
                    run_id,
                )
                return None
            return await _execute_sync("full", run_id, redis)
    else:
        # No Redis — run without distributed locking (single-process deployments)
        logger.warning("catalog_sync_no_redis run without distributed lock")
        return await _execute_sync("full", run_id, redis=None)


async def _run_incremental_sync() -> SyncReport | None:
    """
    2-hour incremental TLE refresh.
    Downloads only TLEs updated in the last 2 days — much faster.
    Uses a separate lock key to allow concurrent full/incremental runs.
    """
    from app.db.redis_session import get_redis
    redis = get_redis()

    run_id = str(uuid.uuid4())[:8]
    incremental_lock = f"{_LOCK_KEY}:incremental"

    logger.info("catalog_sync_job_start job=incremental run=%s", run_id)

    if redis:
        async with _distributed_lock(
            redis, incremental_lock, 600, run_id  # 10 min TTL for incremental
        ) as acquired:
            if not acquired:
                logger.warning("catalog_sync_job_skipped job=incremental reason=lock_held")
                return None
            return await _execute_sync("incremental", run_id, redis)
    else:
        return await _execute_sync("incremental", run_id, redis=None)


async def _execute_sync(
    mode: str,
    run_id: str,
    redis,
) -> SyncReport:
    """
    Execute sync and persist results regardless of success/failure.
    This is the inner body called by both scheduled jobs and the API trigger.
    """
    from app.db.session import get_session_factory
    factory = get_session_factory()

    async with factory() as session:
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        fetcher = SpaceTrackFetcher.from_settings()

        svc = CatalogSyncService(
            fetcher=fetcher,
            session=session,
            redis_client=redis,
        )

        try:
            if mode == "full":
                report = await svc.sync_full(sync_id=run_id)
            elif mode == "incremental":
                report = await svc.sync_incremental(days_back=2, sync_id=run_id)
            elif mode == "active_only":
                report = await svc.sync_active_only(sync_id=run_id)
            else:
                report = await svc.sync_full(sync_id=run_id)

        except Exception as exc:
            logger.exception("execute_sync_unhandled run=%s mode=%s", run_id, mode)
            from dataclasses import dataclass
            report = SyncReport(
                sync_id=run_id,
                sync_mode=mode,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                status="failed",
                failure_reason=str(exc),
            )
        finally:
            await fetcher.close()

        # Persist metrics
        await _persist_metrics(report, session)
        await _cache_report(redis, report)

        return report


# ── Scheduler lifecycle ───────────────────────────────────────

def build_scheduler() -> AsyncIOScheduler:
    """
    Construct the APScheduler instance with all catalog sync jobs.

    Jobs:
      full_catalog_sync       — every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
      incremental_tle_refresh — every 2 hours

    Both jobs use AsyncIOExecutor (runs in the FastAPI event loop).
    Job state is NOT persisted to DB (no SQLAlchemyJobStore) — this keeps
    the scheduler stateless and avoids lock table conflicts in multi-process.
    """
    scheduler = AsyncIOScheduler(
        executors={"default": AsyncIOExecutor()},
        job_defaults={
            "coalesce":       True,   # merge missed runs into one
            "max_instances":  1,      # never run the same job twice in parallel
            "misfire_grace_time": 300, # tolerate up to 5 min late start
        },
        timezone="UTC",
    )

    # Full catalog sync every 6 hours
    scheduler.add_job(
        func=_run_full_catalog_sync,
        trigger=IntervalTrigger(hours=6),
        id="full_catalog_sync",
        name="Space-Track Full Catalog Sync (6h)",
        replace_existing=True,
    )

    # Incremental refresh every 2 hours (between full syncs)
    scheduler.add_job(
        func=_run_incremental_sync,
        trigger=IntervalTrigger(hours=2),
        id="incremental_tle_refresh",
        name="Space-Track Incremental TLE Refresh (2h)",
        replace_existing=True,
    )

    # Conjunction screening every 6 hours (staggered 30min after catalog sync)
    scheduler.add_job(
        func=_run_conjunction_screening,
        trigger=IntervalTrigger(hours=6, start_date="2000-01-01 00:30:00"),
        id="conjunction_screening",
        name="Full Catalog Conjunction Screening (6h)",
        replace_existing=True,
    )

    # Graph population every 6 hours (staggered 1h after catalog sync)
    scheduler.add_job(
        func=_run_graph_population,
        trigger=IntervalTrigger(hours=6, start_date="2000-01-01 01:00:00"),
        id="graph_population",
        name="PostgreSQL → Neo4j Graph Population (6h)",
        replace_existing=True,
    )

    # Digital twin propagation every 15 minutes
    scheduler.add_job(
        func=_run_digital_twin_propagation,
        trigger=IntervalTrigger(minutes=15),
        id="digital_twin_propagation",
        name="Orbital Digital Twin Propagation (15min)",
        replace_existing=True,
    )

    logger.info("catalog_scheduler_built jobs=%d", len(scheduler.get_jobs()))
    return scheduler


async def init_scheduler() -> None:
    """
    Start the catalog sync scheduler.
    Called from main.py lifespan at application startup.
    """
    global _scheduler
    _scheduler = build_scheduler()
    _scheduler.start()
    logger.info("catalog_scheduler_started")


async def shutdown_scheduler() -> None:
    """Gracefully stop the scheduler. Called at application shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("catalog_scheduler_stopped")


def get_scheduler() -> AsyncIOScheduler | None:
    """Return the running scheduler (for API trigger and job inspection)."""
    return _scheduler


async def trigger_manual_sync(
    mode: str = "full",
    sync_id: str | None = None,
) -> SyncReport:
    """
    Trigger an immediate sync run outside the scheduler.
    Called by POST /catalog/sync API endpoint.

    Parameters
    ----------
    mode : str
        Sync mode: full | incremental | active_only
    sync_id : str | None
        Client-supplied run ID for tracking.

    Returns
    -------
    SyncReport
        Complete result of the triggered sync.
    """
    from app.db.redis_session import get_redis
    redis = get_redis()
    run_id = sync_id or str(uuid.uuid4())

    logger.info("catalog_manual_trigger mode=%s run=%s", mode, run_id)

    # Manual trigger bypasses scheduler but still uses distributed lock
    return await _execute_sync(mode, run_id, redis)


async def get_latest_sync_report() -> dict | None:
    """
    Retrieve the most recent sync report.
    Checks Redis first (fast path), falls back to DB.
    """
    from app.db.redis_session import get_redis
    redis = get_redis()

    if redis:
        try:
            import json
            raw = await redis.get(_METRICS_KEY)
            if raw:
                return json.loads(raw)
        except Exception:
            pass

    # DB fallback
    try:
        from app.db.session import get_session_factory
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("""
                    SELECT sync_id, sync_mode, status, started_at, completed_at,
                           total_parsed, inserted, duplicates, satellites_updated,
                           parse_errors, stale_satellite_count, failure_reason
                    FROM sync_metrics
                    ORDER BY started_at DESC
                    LIMIT 1
                """)
            )
            row = result.mappings().first()
            if row:
                return dict(row)
    except Exception as exc:
        logger.warning("get_latest_sync_report_db_fallback_failed error=%s", exc)

    return None
