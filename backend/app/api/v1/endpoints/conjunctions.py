"""
ORBITIQ-X — Conjunction Analysis API Endpoints
================================================
Implements all 6 conjunction endpoints as specified.

  GET  /conjunctions             — paginated CDM list with filters
  GET  /conjunctions/high-risk   — red + yellow events (dashboard)
  GET  /conjunctions/statistics  — risk distribution and counts
  POST /conjunctions/screen      — trigger immediate screening run
  GET  /conjunctions/{id}        — single CDM detail
  GET  /cdm/{event_id}           — downloadable CDM document

The POST /conjunctions/screen endpoint runs the full screening pipeline
as a background task, returning 202 immediately with a tracking ID.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.conjunction_repository import ConjunctionRepository
from app.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response models ───────────────────────────────────────────

class ConjunctionSummary(BaseModel):
    id:                    int
    conjunction_id:        str
    primary_norad:         int
    primary_name:          str | None
    secondary_norad:       int
    secondary_name:        str | None
    tca:                   str
    miss_distance_km:      float
    miss_distance_m:       float
    relative_velocity_kms: float
    relative_velocity_mps: float
    collision_probability: float
    risk_level:            str
    maneuver_required:     bool
    resolved:              bool
    created_at:            str | None


class ConjunctionDetail(ConjunctionSummary):
    primary_type:              str | None = None
    secondary_type:            str | None = None
    collision_probability_method: str | None = None
    combined_hbr_km:           float | None = None
    sigma_major_km:            float | None = None
    sigma_minor_km:            float | None = None
    maneuver_window_close:     str | None = None
    resolution:                str | None = None
    resolved_at:               str | None = None
    screening_org:             str | None = None


class ConjunctionListResponse(BaseModel):
    items:    list[ConjunctionSummary]
    total:    int
    page:     int
    per_page: int
    filters:  dict


class StatisticsResponse(BaseModel):
    total_events:           int
    unresolved_total:       int
    by_risk:                dict[str, int]
    maneuver_required_count: int
    avg_miss_distance_km:   float | None
    max_pc:                 float | None
    screening_coverage:     str


class ScreeningRequest(BaseModel):
    epoch:      str | None = Field(None, description="ISO UTC epoch (default: now)")
    max_objects: int | None = Field(None, ge=1, le=60000)


class ScreeningTriggerResponse(BaseModel):
    accepted:  bool = True
    run_id:    str
    message:   str
    poll_url:  str


# ── Helpers ───────────────────────────────────────────────────

def _event_to_summary(ev) -> ConjunctionSummary:
    return ConjunctionSummary(
        id=ev.id,
        conjunction_id=ev.conjunction_id,
        primary_norad=ev.primary_norad,
        primary_name=ev.primary_name,
        secondary_norad=ev.secondary_norad,
        secondary_name=ev.secondary_name,
        tca=ev.tca.isoformat() if ev.tca else "",
        miss_distance_km=ev.miss_distance_km,
        miss_distance_m=ev.miss_distance_km * 1000,
        relative_velocity_kms=ev.relative_velocity_kms,
        relative_velocity_mps=ev.relative_velocity_kms * 1000,
        collision_probability=ev.collision_probability,
        risk_level=ev.risk_level,
        maneuver_required=ev.maneuver_required,
        resolved=ev.resolved,
        created_at=ev.created_at.isoformat() if ev.created_at else None,
    )


def _event_to_detail(ev) -> ConjunctionDetail:
    s = _event_to_summary(ev)
    return ConjunctionDetail(
        **s.model_dump(),
        primary_type=ev.primary_type,
        secondary_type=ev.secondary_type,
        collision_probability_method=ev.collision_probability_method,
        combined_hbr_km=ev.combined_hbr_km,
        sigma_major_km=ev.sigma_major_km,
        sigma_minor_km=ev.sigma_minor_km,
        maneuver_window_close=ev.maneuver_window_close.isoformat() if ev.maneuver_window_close else None,
        resolution=ev.resolution,
        resolved_at=ev.resolved_at.isoformat() if ev.resolved_at else None,
        screening_org=ev.screening_org,
    )


# ── GET /conjunctions ─────────────────────────────────────────

@router.get(
    "",
    response_model=ConjunctionListResponse,
    summary="List conjunction events",
    description=(
        "Paginated list of conjunction CDM records. "
        "Filter by risk_level (red|yellow|green|white), resolved status, and NORAD ID."
    ),
)
async def list_conjunctions(
    page:       Annotated[int, Query(ge=1)] = 1,
    per_page:   Annotated[int, Query(ge=1, le=200)] = 50,
    risk_level: Annotated[str | None, Query()] = None,
    resolved:   Annotated[bool | None, Query()] = None,
    norad_id:   Annotated[int | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
) -> ConjunctionListResponse:
    from sqlalchemy import select, func, and_
    from app.db.models.conjunction_events import ConjunctionEvent

    offset = (page - 1) * per_page
    conditions = []

    if risk_level:
        conditions.append(ConjunctionEvent.risk_level == risk_level)
    if resolved is not None:
        conditions.append(ConjunctionEvent.resolved == resolved)
    if norad_id:
        conditions.append(
            (ConjunctionEvent.primary_norad == norad_id) |
            (ConjunctionEvent.secondary_norad == norad_id)
        )

    where = and_(*conditions) if conditions else True

    result = await session.execute(
        select(ConjunctionEvent)
        .where(where)
        .order_by(ConjunctionEvent.collision_probability.desc())
        .limit(per_page)
        .offset(offset)
    )
    events = result.scalars().all()

    total_result = await session.execute(
        select(func.count(ConjunctionEvent.id)).where(where)
    )
    total = total_result.scalar_one_or_none() or 0

    return ConjunctionListResponse(
        items=[_event_to_summary(e) for e in events],
        total=total,
        page=page,
        per_page=per_page,
        filters={
            "risk_level": risk_level,
            "resolved": resolved,
            "norad_id": norad_id,
        },
    )


# ── GET /conjunctions/high-risk ───────────────────────────────

@router.get(
    "/high-risk",
    response_model=list[ConjunctionSummary],
    summary="High-risk unresolved conjunctions",
    description="Returns all unresolved red and yellow conjunction events sorted by Pc.",
)
async def get_high_risk(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: AsyncSession = Depends(get_session),
) -> list[ConjunctionSummary]:
    repo   = ConjunctionRepository(session)
    events = await repo.get_unresolved_red_yellow(limit=limit)
    return [_event_to_summary(e) for e in events]


# ── GET /conjunctions/statistics ─────────────────────────────

@router.get(
    "/statistics",
    response_model=StatisticsResponse,
    summary="Conjunction statistics",
    description="Risk distribution, maneuver counts, and catalog coverage statistics.",
)
async def get_statistics(
    session: AsyncSession = Depends(get_session),
) -> StatisticsResponse:
    from sqlalchemy import select, func
    from app.db.models.conjunction_events import ConjunctionEvent

    repo        = ConjunctionRepository(session)
    risk_counts = await repo.stats_by_risk_level()

    total_result = await session.execute(
        select(func.count(ConjunctionEvent.id))
    )
    total = total_result.scalar_one_or_none() or 0

    unresolved_result = await session.execute(
        select(func.count(ConjunctionEvent.id))
        .where(ConjunctionEvent.resolved == False)  # noqa
    )
    unresolved = unresolved_result.scalar_one_or_none() or 0

    maneuver_result = await session.execute(
        select(func.count(ConjunctionEvent.id))
        .where(
            ConjunctionEvent.maneuver_required == True,  # noqa
            ConjunctionEvent.resolved == False,          # noqa
        )
    )
    maneuver_count = maneuver_result.scalar_one_or_none() or 0

    avg_miss_result = await session.execute(
        select(func.avg(ConjunctionEvent.miss_distance_km))
        .where(ConjunctionEvent.resolved == False)  # noqa
    )
    avg_miss = avg_miss_result.scalar_one_or_none()

    max_pc_result = await session.execute(
        select(func.max(ConjunctionEvent.collision_probability))
    )
    max_pc = max_pc_result.scalar_one_or_none()

    sat_result = await session.execute(
        select(func.count()).select_from(
            __import__("app.db.models.satellites", fromlist=["Satellite"]).Satellite
        )
    )

    return StatisticsResponse(
        total_events=total,
        unresolved_total=unresolved,
        by_risk=risk_counts,
        maneuver_required_count=maneuver_count,
        avg_miss_distance_km=round(float(avg_miss), 3) if avg_miss else None,
        max_pc=max_pc,
        screening_coverage="Full LEO catalog",
    )


# ── POST /conjunctions/screen ─────────────────────────────────

@router.post(
    "/screen",
    response_model=ScreeningTriggerResponse,
    status_code=202,
    summary="Trigger conjunction screening",
    description=(
        "Starts a full conjunction screening run in the background. "
        "Returns 202 Accepted immediately. Poll GET /conjunctions to "
        "see new events as they are persisted."
    ),
)
async def trigger_screening(
    request: ScreeningRequest,
    background_tasks: BackgroundTasks,
) -> ScreeningTriggerResponse:
    from datetime import datetime as dt
    run_id = str(uuid.uuid4())[:8]

    epoch = None
    if request.epoch:
        try:
            from datetime import timezone
            epoch = dt.fromisoformat(request.epoch.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid epoch format (use ISO UTC)")

    background_tasks.add_task(
        _run_background_screening,
        run_id=run_id,
        epoch=epoch,
        max_objects=request.max_objects,
    )

    return ScreeningTriggerResponse(
        accepted=True,
        run_id=run_id,
        message=f"Conjunction screening started (run_id={run_id}). "
                f"New CDMs will appear in GET /conjunctions as they are computed.",
        poll_url="/api/v1/conjunctions?resolved=false",
    )


async def _run_background_screening(
    run_id: str,
    epoch,
    max_objects: int | None,
) -> None:
    """Background task body for the API-triggered screening."""
    try:
        from app.db.redis_session import get_redis
        from app.services.conjunction_analysis_service import ConjunctionAnalysisService
        from app.db.session import get_session_factory

        factory = get_session_factory()
        redis   = get_redis()

        async with factory() as session:
            svc    = ConjunctionAnalysisService(session, redis_client=redis)
            report = await svc.run_screening(epoch=epoch, run_id=run_id, max_objects=max_objects)
            logger.info(
                "api_screening_complete run=%s status=%s conjunctions=%d",
                run_id, report.status, report.total_conjunctions,
            )
    except Exception as exc:
        logger.exception("api_screening_background_failed run=%s", run_id)


# ── GET /conjunctions/{conjunction_id} ────────────────────────

@router.get(
    "/{conjunction_id}",
    response_model=ConjunctionDetail,
    summary="Get conjunction event detail",
)
async def get_conjunction(
    conjunction_id: str,
    session: AsyncSession = Depends(get_session),
) -> ConjunctionDetail:
    repo  = ConjunctionRepository(session)
    event = await repo.get_by_conjunction_id(conjunction_id)
    if not event:
        # Try by numeric ID
        try:
            from sqlalchemy import select
            from app.db.models.conjunction_events import ConjunctionEvent
            result = await session.execute(
                select(ConjunctionEvent).where(ConjunctionEvent.id == int(conjunction_id))
            )
            event = result.scalar_one_or_none()
        except (ValueError, Exception):
            pass

    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Conjunction event '{conjunction_id}' not found.",
        )
    return _event_to_detail(event)


# ── GET /cdm/{event_id} ───────────────────────────────────────

@router.get(
    "/cdm/{event_id}",
    summary="Get CDM document",
    description=(
        "Returns a CCSDS-inspired CDM JSON document for the specified event. "
        "Suitable for export, downstream processing, and mission planning tools."
    ),
)
async def get_cdm_document(
    event_id: str,
    session: AsyncSession = Depends(get_session),
):
    from fastapi.responses import ORJSONResponse
    from app.services.conjunction_analysis_service import ConjunctionAnalysisService
    from app.db.redis_session import get_redis

    svc = ConjunctionAnalysisService(session, redis_client=get_redis())
    cdm = await svc.get_cdm(event_id)

    if not cdm:
        raise HTTPException(
            status_code=404,
            detail=f"CDM for event '{event_id}' not found.",
        )
    return ORJSONResponse(content=cdm)
