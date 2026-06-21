"""
ORBITIQ-X — SSA Conjunction & Maneuver Assessment API
=======================================================
Phase 12 endpoints under the /ssa prefix.

Endpoints (from Phase 12 spec)
──────────────────────────────
  GET  /ssa/conjunctions            — list with filters
  GET  /ssa/conjunctions/high-risk  — red + yellow ops dashboard
  GET  /ssa/conjunctions/{id}       — single CDM detail + maneuver options
  POST /ssa/cdm/generate            — generate CCSDS CDM for any conjunction
  POST /ssa/maneuver/recommend      — compute avoidance maneuvers
  GET  /ssa/statistics              — risk distribution + catalog coverage

Relationship to existing conjunction endpoints
───────────────────────────────────────────────
  The existing /conjunctions/* routes (fully implemented in Phase 11)
  handle the persistence layer. These /ssa/* routes delegate to the same
  repositories but add maneuver recommendation, CDM generation, and
  Neo4j graph enrichment via the ManeuverRecommendationEngine.

  Every ConjunctionRepository call is the same existing implementation.
  No database code is duplicated.

Performance targets
────────────────────
  CDM generation:         < 100 ms (in-memory computation)
  Maneuver recommendation:< 500 ms (CW equations, no SGP4 calls)
  High-risk extraction:   < 2s    (indexed DB query)
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request/response models ───────────────────────────────────

class CDMGenerateRequest(BaseModel):
    conjunction_id: str = Field(..., description="Conjunction ID from CDM archive")

class ManeuverRecommendRequest(BaseModel):
    conjunction_id:     str   = Field(..., description="Conjunction ID from CDM archive")
    primary_altitude_km:float = Field(420.0, ge=160, le=36000,
                                     description="Primary satellite altitude [km]")
    satellite_mass_kg:  float = Field(500.0, ge=1, le=10000,
                                     description="Primary satellite mass [kg]")
    burn_lead_time_h:   float = Field(24.0, ge=1, le=72,
                                     description="Hours before TCA to execute maneuver")
    persist_to_graph:   bool  = Field(True,
                                     description="Persist ManeuverOptions to Neo4j")


# ── GET /ssa/conjunctions ─────────────────────────────────────

@router.get(
    "/conjunctions",
    summary="List conjunction events (SSA view)",
    description=(
        "Paginated CDM archive with risk-level, NORAD, and date filters. "
        "Returns ConjunctionEvent records sorted by Pc descending. "
        "Same data as /conjunctions but enriched with SSA context fields."
    ),
)
async def list_ssa_conjunctions(
    page:       Annotated[int, Query(ge=1)] = 1,
    per_page:   Annotated[int, Query(ge=1, le=200)] = 50,
    risk_level: Annotated[str | None, Query(description="red|yellow|green|white")] = None,
    resolved:   Annotated[bool | None, Query()] = None,
    norad_id:   Annotated[int | None, Query()] = None,
    min_pc:     Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from sqlalchemy import select, func, and_
    from app.db.models.conjunction_events import ConjunctionEvent

    offset     = (page - 1) * per_page
    conditions = []

    if risk_level:
        conditions.append(ConjunctionEvent.risk_level == risk_level.lower())
    if resolved is not None:
        conditions.append(ConjunctionEvent.resolved == resolved)
    if norad_id:
        conditions.append(
            (ConjunctionEvent.primary_norad == norad_id) |
            (ConjunctionEvent.secondary_norad == norad_id)
        )
    if min_pc is not None:
        conditions.append(ConjunctionEvent.collision_probability >= min_pc)

    where = and_(*conditions) if conditions else True

    result = await session.execute(
        select(ConjunctionEvent)
        .where(where)
        .order_by(ConjunctionEvent.collision_probability.desc())
        .limit(per_page).offset(offset)
    )
    events = result.scalars().all()

    total_result = await session.execute(
        select(func.count(ConjunctionEvent.id)).where(where)
    )
    total = total_result.scalar_one_or_none() or 0

    return ORJSONResponse(content={
        "items": [_event_to_dict(e) for e in events],
        "total": total, "page": page, "per_page": per_page,
        "filters": {"risk_level": risk_level, "resolved": resolved,
                    "norad_id": norad_id, "min_pc": min_pc},
    })


# ── GET /ssa/conjunctions/high-risk ──────────────────────────

@router.get(
    "/conjunctions/high-risk",
    summary="High-risk conjunction ops dashboard",
    description=(
        "Returns all unresolved RED and YELLOW conjunction events sorted by Pc. "
        "Optimised for the SSA operator dashboard — uses the partial index "
        "ix_conj_active_red for sub-2s response at 1M rows. "
        "Includes maneuver window status for each event."
    ),
)
async def get_high_risk_conjunctions(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from app.db.repositories.conjunction_repository import ConjunctionRepository

    repo   = ConjunctionRepository(session)
    events = await repo.get_unresolved_red_yellow(limit=limit)

    items = []
    now   = datetime.now(timezone.utc)
    for e in events:
        d = _event_to_dict(e)
        # Add maneuver window urgency
        if e.maneuver_window_close:
            hours_to_window = (e.maneuver_window_close - now).total_seconds() / 3600
            d["maneuver_window_hours_remaining"] = round(hours_to_window, 1)
            d["maneuver_urgency"] = (
                "CRITICAL" if hours_to_window < 6 else
                "HIGH"     if hours_to_window < 24 else
                "ELEVATED"
            )
        else:
            d["maneuver_window_hours_remaining"] = None
            d["maneuver_urgency"] = "MONITOR"

        items.append(d)

    return ORJSONResponse(content={
        "count": len(items),
        "items": items,
        "note": "Sorted by collision probability descending. "
                "maneuver_urgency: CRITICAL=<6h window, HIGH=<24h, ELEVATED=<72h."
    })


# ── GET /ssa/conjunctions/{id} ────────────────────────────────

@router.get(
    "/conjunctions/{conjunction_id}",
    summary="Single conjunction CDM with maneuver graph",
    description=(
        "Returns full CDM detail for one conjunction event, enriched with: "
        "• CCSDS CDM document fields "
        "• ManeuverOption recommendations from Neo4j (if available) "
        "• Conjunction network neighbours from graph "
    ),
)
async def get_conjunction_detail(
    conjunction_id: str,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from app.db.repositories.conjunction_repository import ConjunctionRepository
    from app.services.maneuver_recommendation import ManeuverRecommendationEngine

    repo  = ConjunctionRepository(session)
    event = await repo.get_by_conjunction_id(conjunction_id)
    if not event:
        raise HTTPException(404, detail=f"Conjunction '{conjunction_id}' not found.")

    detail = _event_to_dict(event)

    # Enrich with maneuver options from Neo4j graph
    try:
        engine  = ManeuverRecommendationEngine()
        options = await engine.get_recommendations_for_conjunction(conjunction_id)
        detail["maneuver_options_graph"] = options
    except Exception:
        detail["maneuver_options_graph"] = []

    return ORJSONResponse(content=detail)


# ── POST /ssa/cdm/generate ────────────────────────────────────

@router.post(
    "/cdm/generate",
    summary="Generate CCSDS CDM document",
    description=(
        "Generates a CCSDS 508.0-B-1 Conjunction Data Message document "
        "for the specified conjunction event. "
        "The document follows CCSDS CDM naming conventions (MESSAGE_ID, TCA, "
        "MISS_DISTANCE in metres, COLLISION_PROBABILITY, RELATIVE_SPEED in m/s, "
        "OBJECT1/OBJECT2 blocks, RELATIVE_STATE in ECI J2000). "
        "Performance target: < 100 ms."
    ),
)
async def generate_cdm(
    request: CDMGenerateRequest,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from app.services.conjunction_analysis_service import ConjunctionAnalysisService
    from app.db.redis_session import get_redis

    svc = ConjunctionAnalysisService(session, redis_client=get_redis())
    cdm = await svc.get_cdm(request.conjunction_id)

    if not cdm:
        raise HTTPException(
            404,
            detail=f"Conjunction '{request.conjunction_id}' not found in CDM archive.",
        )
    return ORJSONResponse(content=cdm)


# ── POST /ssa/maneuver/recommend ──────────────────────────────

@router.post(
    "/maneuver/recommend",
    summary="Compute collision avoidance maneuver options",
    description=(
        "Evaluates three maneuver strategies (along-track, radial, cross-track) "
        "for a conjunction event and returns ranked options sorted by ΔV cost. "
        "Uses the Clohessy-Wiltshire equations for relative motion analysis. "
        "The minimum-ΔV option that achieves Pc < 1e-5 (GREEN) is marked as recommended. "
        "Optionally persists ManeuverOption nodes to Neo4j as [:RECOMMENDS] relationships. "
        "Performance target: < 500 ms."
    ),
)
async def recommend_maneuver(
    request: ManeuverRecommendRequest,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from app.db.repositories.conjunction_repository import ConjunctionRepository
    from app.services.maneuver_recommendation import ManeuverRecommendationEngine

    # Load the conjunction from CDM archive
    repo  = ConjunctionRepository(session)
    event = await repo.get_by_conjunction_id(request.conjunction_id)
    if not event:
        raise HTTPException(
            404,
            detail=f"Conjunction '{request.conjunction_id}' not found.",
        )

    # Evaluate maneuver options
    engine = ManeuverRecommendationEngine(
        satellite_mass_kg=request.satellite_mass_kg,
        burn_lead_time_h=request.burn_lead_time_h,
    )

    rec = engine.evaluate(
        conjunction_id=event.conjunction_id,
        primary_norad=event.primary_norad,
        primary_name=event.primary_name or f"NORAD-{event.primary_norad}",
        secondary_norad=event.secondary_norad,
        secondary_name=event.secondary_name or f"NORAD-{event.secondary_norad}",
        tca=event.tca,
        miss_distance_km=event.miss_distance_km,
        relative_velocity_kms=event.relative_velocity_kms,
        collision_probability=event.collision_probability,
        primary_altitude_km=request.primary_altitude_km,
        risk_level=event.risk_level,
    )

    # Persist to Neo4j if requested
    if request.persist_to_graph:
        try:
            nodes_created = await engine.persist_to_graph(rec)
            logger.info(
                "maneuver_graph_persisted conjunction=%s nodes=%d",
                request.conjunction_id, nodes_created,
            )
        except Exception as exc:
            logger.warning("maneuver_graph_persist_failed error=%s", exc)

    return ORJSONResponse(content=rec.to_dict())


# ── GET /ssa/statistics ───────────────────────────────────────

@router.get(
    "/statistics",
    summary="SSA conjunction statistics",
    description=(
        "Risk distribution, catalog coverage, maneuver requirements, "
        "and SSA system health metrics. Aggregates the full CDM archive."
    ),
)
async def get_ssa_statistics(
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from sqlalchemy import select, func
    from app.db.models.conjunction_events import ConjunctionEvent
    from app.db.repositories.conjunction_repository import ConjunctionRepository

    repo        = ConjunctionRepository(session)
    risk_counts = await repo.stats_by_risk_level()

    total       = (await session.execute(
        select(func.count(ConjunctionEvent.id))
    )).scalar_one_or_none() or 0

    unresolved  = (await session.execute(
        select(func.count(ConjunctionEvent.id))
        .where(ConjunctionEvent.resolved == False)  # noqa
    )).scalar_one_or_none() or 0

    maneuver_req = (await session.execute(
        select(func.count(ConjunctionEvent.id))
        .where(
            ConjunctionEvent.maneuver_required == True,  # noqa
            ConjunctionEvent.resolved == False,          # noqa
        )
    )).scalar_one_or_none() or 0

    avg_miss = (await session.execute(
        select(func.avg(ConjunctionEvent.miss_distance_km))
        .where(ConjunctionEvent.resolved == False)  # noqa
    )).scalar_one_or_none()

    max_pc = (await session.execute(
        select(func.max(ConjunctionEvent.collision_probability))
    )).scalar_one_or_none()

    # Graph stats
    graph_conj_count = 0
    try:
        from app.graph.connection import is_available
        if is_available():
            from app.graph.connection import execute_read
            rows = await execute_read(
                "MATCH (ce:ConjunctionEvent) RETURN count(ce) AS n"
            )
            graph_conj_count = rows[0].get("n", 0) if rows else 0
    except Exception:
        pass

    return ORJSONResponse(content={
        "total_events":            total,
        "unresolved_total":        unresolved,
        "by_risk":                 risk_counts,
        "maneuver_required_count": maneuver_req,
        "avg_miss_distance_km":    round(float(avg_miss), 3) if avg_miss else None,
        "max_pc":                  max_pc,
        "screening_coverage":      "Full LEO catalog (active satellites)",
        "graph_conjunctions":      graph_conj_count,
        "risk_thresholds": {
            "red":    "Pc >= 1e-3 (mandatory maneuver consideration)",
            "yellow": "Pc >= 1e-4 (elevated monitoring)",
            "green":  "Pc >= 1e-5 (trackable, routine monitoring)",
            "white":  "Pc <  1e-5 (below alert threshold)",
        },
        "pc_method":    "Foster (2001) — 2D Gaussian projection onto collision plane",
        "ccsds_standard": "CCSDS 508.0-B-1",
    })


# ── Helper ────────────────────────────────────────────────────

def _event_to_dict(ev) -> dict:
    return {
        "id":                     ev.id,
        "conjunction_id":         ev.conjunction_id,
        "primary": {
            "norad":  ev.primary_norad,
            "name":   ev.primary_name,
            "type":   ev.primary_type,
        },
        "secondary": {
            "norad":  ev.secondary_norad,
            "name":   ev.secondary_name,
            "type":   ev.secondary_type,
        },
        "tca":                    ev.tca.isoformat() if ev.tca else None,
        "miss_distance_km":       ev.miss_distance_km,
        "miss_distance_m":        ev.miss_distance_km * 1000,
        "relative_velocity_kms":  ev.relative_velocity_kms,
        "relative_velocity_mps":  ev.relative_velocity_kms * 1000,
        "collision_probability":  ev.collision_probability,
        "risk_level":             ev.risk_level,
        "combined_hbr_km":        ev.combined_hbr_km,
        "sigma_major_km":         ev.sigma_major_km,
        "sigma_minor_km":         ev.sigma_minor_km,
        "maneuver_required":      ev.maneuver_required,
        "maneuver_window_close":  ev.maneuver_window_close.isoformat()
                                  if ev.maneuver_window_close else None,
        "recommended_dv_kms":     ev.recommended_dv_kms,
        "resolved":               ev.resolved,
        "resolution":             ev.resolution,
        "screening_org":          ev.screening_org,
        "created_at":             ev.created_at.isoformat() if ev.created_at else None,
    }
