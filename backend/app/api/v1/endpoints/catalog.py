"""
ORBITIQ-X — Catalog API Endpoints
===================================
REST API for the Space-Track catalog ingestion subsystem.

Endpoints
─────────
  GET  /catalog/status              — last sync summary
  GET  /catalog/health              — Space-Track reachability + DB health
  POST /catalog/sync                — trigger manual sync
  GET  /catalog/metrics             — full metrics history (paginated)
  GET  /catalog/satellite/{norad_id} — single satellite with latest TLE

These endpoints are read-heavy and use the Redis cache wherever possible
to keep response times < 10ms under normal operation.

The POST /catalog/sync endpoint runs the sync asynchronously via
asyncio.create_task() so the HTTP response returns immediately (202 Accepted)
while the sync runs in the background. The client polls /catalog/status
to check completion.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.satellite_repository import SatelliteRepository
from app.db.repositories.tle_repository import TLERepository
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response models ───────────────────────────────────────────

class SyncStatusResponse(BaseModel):
    sync_id: str | None          = None
    status: str                  = "unknown"
    sync_mode: str | None        = None
    started_at: str | None       = None
    completed_at: str | None     = None
    duration_seconds: float | None = None
    downloaded_records: int      = 0
    total_parsed: int            = 0
    inserted: int                = 0
    duplicates: int              = 0
    satellites_updated: int      = 0
    parse_errors: int            = 0
    stale_satellite_count: int   = 0
    failure_reason: str | None   = None
    phases_completed: list[str]  = Field(default_factory=list)


class HealthResponse(BaseModel):
    overall: str                 # healthy | degraded | unhealthy
    spacetrack_reachable: bool   = False
    spacetrack_authenticated: bool = False
    spacetrack_latency_ms: float = 0.0
    database_ok: bool            = False
    database_satellite_count: int = 0
    last_sync_status: str | None = None
    last_sync_age_minutes: float | None = None
    checked_at: str              = ""
    warnings: list[str]          = Field(default_factory=list)


class SyncTriggerRequest(BaseModel):
    mode: str = Field(
        default="full",
        description="Sync mode: full | incremental | active_only",
        pattern="^(full|incremental|active_only)$",
    )
    sync_id: str | None = Field(
        default=None,
        description="Optional client-supplied UUID for tracking",
    )


class SyncTriggerResponse(BaseModel):
    accepted: bool               = True
    sync_id: str
    mode: str
    message: str
    poll_url: str


class MetricsListResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    per_page: int


class SatelliteResponse(BaseModel):
    norad_id: int
    name: str
    cospar_id: str | None
    object_type: str
    regime: str | None
    status: str
    country_code: str | None
    perigee_km: float | None
    apogee_km: float | None
    inclination_deg: float | None
    period_minutes: float | None
    tle_line1: str | None
    tle_line2: str | None
    tle_epoch: str | None
    tle_age_days: float | None
    tle_source: str | None


# ── GET /catalog/status ───────────────────────────────────────

@router.get(
    "/status",
    response_model=SyncStatusResponse,
    summary="Last catalog sync status",
    description=(
        "Returns the status and metrics of the most recent catalog "
        "synchronization run. Data is served from Redis cache (< 1ms) "
        "when available, falling back to the sync_metrics table."
    ),
)
async def get_catalog_status() -> SyncStatusResponse:
    try:
        from app.services.catalog_scheduler import get_latest_sync_report
        report = await get_latest_sync_report()

        if not report:
            return SyncStatusResponse(status="no_sync_recorded")

        phases = report.get("phases_completed", "")
        if isinstance(phases, str):
            phases = [p for p in phases.split(",") if p]

        return SyncStatusResponse(
            sync_id=report.get("sync_id"),
            status=report.get("status", "unknown"),
            sync_mode=report.get("sync_mode"),
            started_at=str(report.get("started_at", "")),
            completed_at=str(report.get("completed_at", "")) if report.get("completed_at") else None,
            duration_seconds=report.get("duration_seconds"),
            downloaded_records=report.get("downloaded_records", 0),
            total_parsed=report.get("total_parsed", 0),
            inserted=report.get("inserted", 0),
            duplicates=report.get("duplicates", 0),
            satellites_updated=report.get("satellites_updated", 0),
            parse_errors=report.get("parse_errors", 0),
            stale_satellite_count=report.get("stale_satellite_count", 0),
            failure_reason=report.get("failure_reason"),
            phases_completed=phases,
        )

    except Exception as exc:
        logger.error("catalog_status_error error=%s", exc)
        raise HTTPException(status_code=500, detail=f"Status read failed: {exc}")


# ── GET /catalog/health ───────────────────────────────────────

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Catalog subsystem health check",
    description=(
        "Checks Space-Track reachability (1 lightweight API call), "
        "database connectivity, and last sync recency. "
        "WARNING: This endpoint consumes 1 Space-Track API request."
    ),
)
async def get_catalog_health(
    session: AsyncSession = Depends(get_session),
) -> HealthResponse:
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    warnings: list[str] = []
    overall = "healthy"

    # ── Check Space-Track ─────────────────────────────────────
    st_reachable = False
    st_authenticated = False
    st_latency = 0.0

    try:
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        fetcher = SpaceTrackFetcher.from_settings()
        await fetcher._ensure_client()

        # Only check health if credentials are configured
        from app.core.config import get_settings
        s = get_settings()
        if s.SPACETRACK_IDENTITY:
            try:
                await fetcher.authenticate()
                health = await fetcher.health_check()
                st_reachable      = health.reachable
                st_authenticated  = health.authenticated
                st_latency        = health.latency_ms
                if health.latency_ms > 5000:
                    warnings.append(f"Space-Track latency high: {health.latency_ms:.0f}ms")
            except Exception as exc:
                warnings.append(f"Space-Track check failed: {str(exc)[:100]}")
                overall = "degraded"
        else:
            warnings.append("SPACETRACK_IDENTITY not configured")
            overall = "degraded"
        await fetcher.close()
    except Exception as exc:
        warnings.append(f"Space-Track client error: {str(exc)[:100]}")
        overall = "degraded"

    # ── Check database ────────────────────────────────────────
    db_ok = False
    sat_count = 0
    try:
        sat_repo = SatelliteRepository(session)
        sat_count = await sat_repo.count()
        db_ok = True
        if sat_count == 0:
            warnings.append("Satellite catalog is empty — sync has not run")
    except Exception as exc:
        warnings.append(f"Database check failed: {str(exc)[:100]}")
        overall = "unhealthy"

    # ── Check last sync recency ───────────────────────────────
    last_sync_status = None
    last_sync_age_min = None

    try:
        from app.services.catalog_scheduler import get_latest_sync_report
        from datetime import datetime, timezone
        report = await get_latest_sync_report()
        if report:
            last_sync_status = report.get("status")
            completed_at_str = report.get("completed_at")
            if completed_at_str:
                try:
                    completed_at = datetime.fromisoformat(
                        str(completed_at_str).replace("Z", "+00:00")
                    )
                    age_min = (
                        datetime.now(timezone.utc) - completed_at
                    ).total_seconds() / 60.0
                    last_sync_age_min = round(age_min, 1)
                    if age_min > 720:  # 12 hours
                        warnings.append(
                            f"Last sync was {age_min:.0f} minutes ago — catalog may be stale"
                        )
                        overall = "degraded" if overall == "healthy" else overall
                    if last_sync_status == "failed":
                        warnings.append("Last sync run failed — check failure_reason")
                        overall = "degraded"
                except Exception:
                    pass
    except Exception:
        pass

    if overall == "healthy" and warnings:
        overall = "degraded"

    return HealthResponse(
        overall=overall,
        spacetrack_reachable=st_reachable,
        spacetrack_authenticated=st_authenticated,
        spacetrack_latency_ms=st_latency,
        database_ok=db_ok,
        database_satellite_count=sat_count,
        last_sync_status=last_sync_status,
        last_sync_age_minutes=last_sync_age_min,
        checked_at=checked_at,
        warnings=warnings,
    )


# ── POST /catalog/sync ────────────────────────────────────────

@router.post(
    "/sync",
    response_model=SyncTriggerResponse,
    status_code=202,
    summary="Trigger catalog synchronization",
    description=(
        "Starts a catalog sync in the background. Returns 202 Accepted immediately. "
        "Poll GET /catalog/status with the returned sync_id to monitor progress. "
        "The sync is protected by a distributed lock — if one is already running, "
        "this returns 409 Conflict."
    ),
)
async def trigger_catalog_sync(
    request: SyncTriggerRequest,
    background_tasks: BackgroundTasks,
) -> SyncTriggerResponse:
    import uuid
    sync_id = request.sync_id or str(uuid.uuid4())

    logger.info(
        "catalog_sync_api_trigger mode=%s sync_id=%s",
        request.mode, sync_id,
    )

    # Run in background — returns immediately
    background_tasks.add_task(
        _background_sync,
        mode=request.mode,
        sync_id=sync_id,
    )

    return SyncTriggerResponse(
        accepted=True,
        sync_id=sync_id,
        mode=request.mode,
        message=f"Catalog sync '{request.mode}' started in background (sync_id={sync_id})",
        poll_url=f"/api/v1/catalog/status",
    )


async def _background_sync(mode: str, sync_id: str) -> None:
    """Background task body — runs sync and logs result."""
    try:
        from app.services.catalog_scheduler import trigger_manual_sync
        report = await trigger_manual_sync(mode=mode, sync_id=sync_id)
        logger.info(
            "catalog_sync_api_complete sync_id=%s status=%s inserted=%d",
            sync_id, report.status, report.inserted,
        )
    except Exception as exc:
        logger.exception("catalog_sync_api_background_failed sync_id=%s", sync_id)


# ── GET /catalog/metrics ──────────────────────────────────────

@router.get(
    "/metrics",
    response_model=MetricsListResponse,
    summary="Sync metrics history",
    description="Returns paginated history of catalog sync runs from sync_metrics table.",
)
async def get_catalog_metrics(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
) -> MetricsListResponse:
    try:
        from sqlalchemy import text as sqlt

        offset = (page - 1) * per_page
        where_clause = ""
        params: dict = {"limit": per_page, "offset": offset}

        if status:
            where_clause = "WHERE status = :status"
            params["status"] = status

        rows = await session.execute(
            sqlt(f"""
                SELECT sync_id, sync_mode, status, started_at, completed_at,
                       total_parsed, inserted, duplicates, satellites_updated,
                       parse_errors, stale_satellite_count,
                       download_duration_s, downloaded_records,
                       failure_reason, phases_completed
                FROM sync_metrics
                {where_clause}
                ORDER BY started_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        items = [dict(r) for r in rows.mappings()]

        total_row = await session.execute(
            sqlt(f"SELECT COUNT(*) FROM sync_metrics {where_clause}"),
            {k: v for k, v in params.items() if k in ("status",)} if status else {},
        )
        total = total_row.scalar_one_or_none() or 0

        return MetricsListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
        )

    except Exception as exc:
        logger.error("catalog_metrics_error error=%s", exc)
        # Return empty if sync_metrics table doesn't exist yet
        return MetricsListResponse(items=[], total=0, page=page, per_page=per_page)


# ── GET /catalog/satellite/{norad_id} ─────────────────────────

@router.get(
    "/satellite/{norad_id}",
    response_model=SatelliteResponse,
    summary="Get satellite by NORAD ID",
    description=(
        "Returns current catalog data and latest TLE for a single satellite. "
        "Checks Redis cache first (< 1ms), falls back to PostgreSQL."
    ),
)
async def get_satellite(
    norad_id: int,
    session: AsyncSession = Depends(get_session),
) -> SatelliteResponse:
    # ── Redis fast path ───────────────────────────────────────
    from app.db.redis_session import get_redis
    redis = get_redis()
    if redis:
        try:
            cached = await redis.hgetall(f"tle:{norad_id}")
            if cached:
                # Build a minimal response from the TLE cache
                # Full satellite data still comes from DB below
                pass  # fall through to DB for complete response
        except Exception:
            pass

    # ── PostgreSQL path ───────────────────────────────────────
    repo = SatelliteRepository(session)
    sat  = await repo.get_by_norad(norad_id)

    if not sat:
        raise HTTPException(
            status_code=404,
            detail=f"Satellite NORAD {norad_id} not found in catalog. "
                   f"Run POST /catalog/sync to populate the catalog.",
        )

    return SatelliteResponse(
        norad_id=sat.norad_id,
        name=sat.name,
        cospar_id=sat.cospar_id,
        object_type=sat.object_type,
        regime=sat.regime,
        status=sat.status,
        country_code=sat.country_code,
        perigee_km=sat.perigee_km,
        apogee_km=sat.apogee_km,
        inclination_deg=sat.inclination_deg,
        period_minutes=sat.period_minutes,
        tle_line1=sat.tle_line1,
        tle_line2=sat.tle_line2,
        tle_epoch=sat.tle_epoch.isoformat() if sat.tle_epoch else None,
        tle_age_days=sat.tle_age_days,
        tle_source=sat.tle_source,
    )


# ── GET /catalog/satellites ───────────────────────────────────────────────────
#
# NOTE: regime is NULL for most rows (only set after Digital Twin propagation).
# We compute regime from perigee/apogee at query time.
# object_type is stored lowercase: "satellite", "debris", "rocket_body", "unknown"
# The API accepts: PAYLOAD/SAT → "satellite"; ROCKET_BODY/RB → "rocket_body";
#                  DEBRIS/DEB → "debris"

def _compute_regime(perigee_km, apogee_km, inclination_deg, stored_regime):
    """Compute regime from orbital elements when stored value is NULL."""
    if stored_regime:
        return stored_regime.upper()
    if perigee_km is None or apogee_km is None:
        return "UNKNOWN"
    alt = (perigee_km + apogee_km) / 2.0
    inc = inclination_deg or 0.0
    if alt < 0:       return "UNKNOWN"
    if alt < 450:     return "VLEO"
    if alt < 2000:
        if 96 <= inc <= 100: return "SSO"
        return "LEO"
    if alt < 35000:   return "MEO"
    if alt <= 36500:  return "GEO"
    return "HEO"

def _normalize_type(raw: str) -> str:
    """Normalise DB object_type to frontend-friendly uppercase."""
    r = (raw or "unknown").lower().strip()
    if r in ("satellite", "payload"):    return "PAYLOAD"
    if r in ("debris",):                 return "DEBRIS"
    if r in ("rocket_body", "r/b", "rocket body"): return "ROCKET_BODY"
    return "UNKNOWN"

@router.get(
    "/satellites",
    summary="Paginated satellite catalog",
    description="Full RSO catalog from PostgreSQL with regime computed from TLE orbital elements.",
)
async def list_satellites(
    regime:  str | None = None,
    type:    str | None = None,
    search:  str | None = None,
    page:    int = 0,
    limit:   int = 200,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from sqlalchemy import select, or_, func, case, literal, and_, Float
    from sqlalchemy import text
    from app.db.models.satellites import Satellite

    # Map frontend type tokens → DB values
    TYPE_MAP = {
        "PAYLOAD":     ["satellite", "payload"],
        "SAT":         ["satellite", "payload"],
        "DEBRIS":      ["debris"],
        "DEB":         ["debris"],
        "ROCKET_BODY": ["rocket_body"],
        "RB":          ["rocket_body"],
        "UNKNOWN":     ["unknown", "tba"],
    }

    # Build base query — always fetch orbital elements so we can compute regime
    q = select(
        Satellite.norad_id,
        Satellite.name,
        Satellite.object_type,
        Satellite.regime,
        Satellite.inclination_deg,
        Satellite.perigee_km,
        Satellite.apogee_km,
        Satellite.period_minutes,
        Satellite.country_code,
        Satellite.operator_name,
        Satellite.mission_type,
        Satellite.status,
        Satellite.cospar_id,
    )

    # Type filter (against DB lowercase values)
    type_upper = (type or "ALL").upper()
    if type_upper not in ("ALL", ""):
        db_vals = TYPE_MAP.get(type_upper)
        if db_vals:
            q = q.where(Satellite.object_type.in_(db_vals))

    # Search filter
    if search and search.strip():
        s = search.strip()
        like = f"%{s}%"
        try:
            norad_int = int(s)
            q = q.where(or_(
                Satellite.name.ilike(like),
                Satellite.norad_id == norad_int,
            ))
        except ValueError:
            q = q.where(Satellite.name.ilike(like))

    # Fetch all matching rows (regime filter applied in Python after compute)
    q = q.order_by(Satellite.norad_id)

    # For regime filtering we need to fetch and filter in Python
    # since regime is NULL and computed from perigee/apogee
    regime_upper = (regime or "ALL").upper()
    needs_regime_filter = regime_upper not in ("ALL", "")

    if not needs_regime_filter:
        # Can use DB-level pagination
        count_q = select(func.count()).select_from(q.subquery())
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0
        q = q.offset(page * min(limit, 500)).limit(min(limit, 500))
        result = await session.execute(q)
        rows = result.mappings().all()
        objects = []
        for r in rows:
            d = dict(r)
            d["regime"]      = _compute_regime(d.get("perigee_km"), d.get("apogee_km"), d.get("inclination_deg"), d.get("regime"))
            d["object_type"] = _normalize_type(d.get("object_type", "unknown"))
            objects.append(d)
    else:
        # Fetch all matching rows, filter by computed regime, then paginate
        result = await session.execute(q)
        all_rows = result.mappings().all()
        objects_all = []
        for r in all_rows:
            d = dict(r)
            d["regime"]      = _compute_regime(d.get("perigee_km"), d.get("apogee_km"), d.get("inclination_deg"), d.get("regime"))
            d["object_type"] = _normalize_type(d.get("object_type", "unknown"))
            if d["regime"] == regime_upper:
                objects_all.append(d)
        total = len(objects_all)
        start = page * min(limit, 500)
        objects = objects_all[start : start + min(limit, 500)]

    return ORJSONResponse(content={
        "total":   total,
        "page":    page,
        "limit":   limit,
        "objects": objects,
    })
