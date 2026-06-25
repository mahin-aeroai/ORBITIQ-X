"""
ORBITIQ-X — Space Situational Awareness Endpoints
==================================================
REST API for RSO catalog, TLE management, ephemeris propagation,
ground station passes, and live RSO state vectors.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.schemas.ssa import (
    EphemerisRequest,
    EphemerisResponse,
    GroundPassRequest,
    GroundPassResponse,
    RSOCatalogResponse,
    RSODetailResponse,
    TLEResponse,
)
from app.services.ssa_service import SSAService

logger = structlog.get_logger(__name__)
router = APIRouter()


# ─── Dependency ───────────────────────────────────────────────────────────────

def get_ssa_service(settings: Annotated[Settings, Depends(get_settings)]) -> SSAService:
    return SSAService(settings=settings)


# ─── RSO Catalog ──────────────────────────────────────────────────────────────

@router.get(
    "/catalog",
    response_model=RSOCatalogResponse,
    summary="List Resident Space Objects",
    description=(
        "Returns a paginated list of Resident Space Objects (RSOs) from the "
        "integrated satellite catalog. Supports filtering by orbital regime, "
        "operator country, object type, and launch epoch range."
    ),
)
async def list_rso_catalog(
    orbit_class: str | None = Query(
        default=None,
        description="Filter by orbital regime: LEO | MEO | GEO | HEO | SSO | VLEO",
        pattern=r"^(LEO|MEO|GEO|HEO|SSO|VLEO)$",
    ),
    country_code: str | None = Query(
        default=None,
        description="ISO 3166-1 alpha-2 country code of operating nation (e.g. US, IN, CN)",
        min_length=2,
        max_length=3,
    ),
    object_type: str | None = Query(
        default=None,
        description="Object classification: PAYLOAD | ROCKET_BODY | DEBRIS | UNKNOWN",
    ),
    launched_after: datetime | None = Query(
        default=None,
        description="Filter to objects launched after this UTC datetime (ISO 8601)",
    ),
    launched_before: datetime | None = Query(
        default=None,
        description="Filter to objects launched before this UTC datetime (ISO 8601)",
    ),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        default=50, ge=1, le=500,
        description="Results per page (max 500 for bulk operations)",
    ),
    service: SSAService = Depends(get_ssa_service),
) -> RSOCatalogResponse:
    logger.info(
        "ssa.catalog.list",
        orbit_class=orbit_class,
        country_code=country_code,
        page=page,
        page_size=page_size,
    )
    return await service.list_catalog(
        orbit_class=orbit_class,
        country_code=country_code,
        object_type=object_type,
        launched_after=launched_after,
        launched_before=launched_before,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/catalog/{norad_id}",
    response_model=RSODetailResponse,
    summary="Get RSO detail",
    description="Returns full detail for a single RSO identified by NORAD Catalog Number.",
)
async def get_rso_detail(
    norad_id: int,
    service: SSAService = Depends(get_ssa_service),
) -> RSODetailResponse:
    result = await service.get_rso(norad_id=norad_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RSO with NORAD ID {norad_id} not found in catalog.",
        )
    return result


# ─── TLE Management ───────────────────────────────────────────────────────────

@router.get(
    "/tle/{norad_id}",
    response_model=TLEResponse,
    summary="Get current TLE for RSO",
    description=(
        "Returns the most recent Two-Line Element set for the specified object. "
        "Data is cached for 30 minutes and refreshed from Space-Track.org on expiry."
    ),
)
async def get_current_tle(
    norad_id: int,
    epoch: datetime | None = Query(
        default=None,
        description="Request TLE closest to this epoch (UTC). Defaults to latest available.",
    ),
    service: SSAService = Depends(get_ssa_service),
) -> TLEResponse:
    result = await service.get_tle(norad_id=norad_id, epoch=epoch)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No TLE found for NORAD ID {norad_id}.",
        )
    return result


# ─── Ephemeris Propagation ────────────────────────────────────────────────────

@router.post(
    "/propagate",
    response_model=EphemerisResponse,
    summary="Propagate satellite ephemeris",
    description=(
        "Generate state vectors (position + velocity in ECI J2000 frame) for one "
        "or more objects over a specified time window. Uses SGP4 propagation with "
        "optional J2-perturbation correction for LEO objects."
    ),
)
async def propagate_ephemeris(
    request: EphemerisRequest,
    service: SSAService = Depends(get_ssa_service),
) -> EphemerisResponse:
    logger.info(
        "ssa.propagate.request",
        object_count=len(request.norad_ids),
        start=request.start_epoch.isoformat(),
        stop=request.stop_epoch.isoformat(),
        step_seconds=request.step_seconds,
    )

    if request.start_epoch >= request.stop_epoch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_epoch must be before stop_epoch.",
        )

    return await service.propagate(request=request)


# ─── Ground Station Passes ────────────────────────────────────────────────────

@router.post(
    "/passes",
    response_model=GroundPassResponse,
    summary="Predict ground station passes",
    description=(
        "Compute access windows for a satellite over one or more ground stations "
        "within the specified time window. Returns AOS, LOS, max elevation, and "
        "azimuth/elevation profiles."
    ),
)
async def predict_passes(
    request: GroundPassRequest,
    service: SSAService = Depends(get_ssa_service),
) -> GroundPassResponse:
    return await service.predict_passes(request=request)


# ─── Live RSO Stream (WebSocket) ──────────────────────────────────────────────

@router.get(
    "/live/positions",
    summary="Stream live RSO positions (SSE)",
    description=(
        "Server-Sent Events stream of current RSO positions, updated every 30 seconds. "
        "Returns ECI position and ground track (latitude, longitude, altitude) for "
        "all tracked objects or a filtered subset."
    ),
    response_class=StreamingResponse,
)
async def stream_live_positions(
    norad_ids: list[int] | None = Query(
        default=None,
        description="Comma-separated NORAD IDs to stream. Empty = all tracked objects.",
    ),
    service: SSAService = Depends(get_ssa_service),
) -> StreamingResponse:
    async def sse_generator():
        async for position_update in service.stream_positions(norad_ids=norad_ids):
            yield f"data: {position_update}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
