"""
ORBITIQ-X — Mission Intelligence API
======================================
REST API for the mission intelligence layer.

Endpoints
──────────
  GET /mission/list                — paginated mission list with filters
  GET /mission/statistics          — aggregate status / type / agency stats
  GET /mission/{mission_id}        — single mission detail
  GET /mission/operator/{name}     — missions by operator/agency name

Data model
───────────
  Reads the missions table (Alembic migration 0006_create_missions).
  Schema: mission_id, name, status, mission_type, agency, country_code,
          launch_date, target_orbit, satellite_count, is_crewed, etc.

Future integration (NOT in Phase 13D)
───────────────────────────────────────
  • Neo4j Knowledge Graph: Mission nodes with [:OPERATES] → Satellite
  • GraphRAG: document corpus retrieval by mission context
  • Mission Dashboard: timeline + conjunction risk overlay
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.mission_service import MissionService

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Dependency ────────────────────────────────────────────────

def _svc(session: AsyncSession = Depends(get_session)) -> MissionService:
    return MissionService(session=session)


# ── GET /mission/list ─────────────────────────────────────────

@router.get(
    "/list",
    summary="List missions",
    description=(
        "Paginated mission catalog with optional filters for status, type, agency, "
        "and country code. Sorted by launch date (most recent first). "
        "Returns an empty list gracefully when the table is not yet seeded."
    ),
)
async def list_missions(
    status:       Annotated[str | None, Query(description="planned|active|completed|failed|extended|cancelled")] = None,
    mission_type: Annotated[str | None, Query(description="eo|comms|nav|science|military|demo|weather|crewed")]  = None,
    agency:       Annotated[str | None, Query(description="Agency name (partial, case-insensitive)")] = None,
    country_code: Annotated[str | None, Query(description="ISO 3166-1 alpha-3 (e.g. IND, USA, CHN)")] = None,
    page:         Annotated[int, Query(ge=1)]         = 1,
    per_page:     Annotated[int, Query(ge=1, le=200)] = 50,
    svc: MissionService = Depends(_svc),
) -> ORJSONResponse:
    try:
        result = await svc.list_missions(
            status=status,
            mission_type=mission_type,
            agency=agency,
            country_code=country_code,
            page=page,
            per_page=per_page,
        )
        return ORJSONResponse(content=result)
    except Exception as exc:
        logger.error("mission_list_error error=%s", exc)
        # Graceful degradation — table may not exist yet on fresh install
        return ORJSONResponse(content={
            "total": 0, "page": page, "per_page": per_page,
            "has_next": False, "items": [],
            "note": "Mission catalog not yet seeded. Run catalog import to populate.",
        })


# ── GET /mission/statistics ───────────────────────────────────

@router.get(
    "/statistics",
    summary="Mission aggregate statistics",
    description=(
        "Returns mission count by status, type distribution, "
        "top 10 agencies by mission count, active crewed mission count, "
        "and estimated total active satellite count."
    ),
)
async def get_mission_statistics(
    svc: MissionService = Depends(_svc),
) -> ORJSONResponse:
    try:
        stats = await svc.get_statistics()
        return ORJSONResponse(content=stats)
    except Exception as exc:
        logger.error("mission_stats_error error=%s", exc)
        return ORJSONResponse(content={
            "total_missions": 0,
            "by_status": {}, "by_type": {}, "top_agencies": [],
            "active_crewed_missions": 0, "active_satellite_count": 0,
            "note": "Statistics unavailable — catalog not yet seeded.",
        })


# ── GET /mission/operator/{name} ──────────────────────────────

@router.get(
    "/operator/{operator_name}",
    summary="Missions by operator",
    description=(
        "Returns all missions associated with an operator or agency. "
        "Uses partial, case-insensitive match on the agency field "
        "(e.g. 'ISRO' matches 'Indian Space Research Organisation (ISRO)'). "
        "Sorted by launch date (most recent first)."
    ),
)
async def get_missions_by_operator(
    operator_name: str,
    page:          Annotated[int, Query(ge=1)]         = 1,
    per_page:      Annotated[int, Query(ge=1, le=200)] = 50,
    svc: MissionService = Depends(_svc),
) -> ORJSONResponse:
    try:
        result = await svc.get_missions_by_operator(
            operator_name=operator_name,
            page=page,
            per_page=per_page,
        )
        return ORJSONResponse(content=result)
    except Exception as exc:
        logger.error("mission_operator_error operator=%s error=%s", operator_name, exc)
        return ORJSONResponse(content={
            "operator": operator_name,
            "total": 0, "page": page, "per_page": per_page,
            "has_next": False, "items": [],
        })


# ── GET /mission/{mission_id} ─────────────────────────────────

@router.get(
    "/{mission_id}",
    summary="Mission detail",
    description=(
        "Returns full detail for a single mission identified by its mission_id "
        "(e.g. 'MSN-CHANDRAYAAN3', 'MSN-STARLINK-G6-29'). "
        "Returns 404 if the mission_id is not in the catalog."
    ),
)
async def get_mission(
    mission_id: str,
    svc: MissionService = Depends(_svc),
) -> ORJSONResponse:
    try:
        mission = await svc.get_mission(mission_id=mission_id)
    except Exception as exc:
        logger.error("mission_detail_error mission_id=%s error=%s", mission_id, exc)
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")

    if mission is None:
        raise HTTPException(
            status_code=404,
            detail=f"Mission '{mission_id}' not found. "
                   f"Check the mission_id format (e.g. MSN-CHANDRAYAAN3).",
        )
    return ORJSONResponse(content=mission)
