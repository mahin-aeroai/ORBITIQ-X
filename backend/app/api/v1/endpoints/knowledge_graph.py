"""
ORBITIQ-X — Knowledge Graph API Endpoints
==========================================
Phase 8: Full REST API for the Aerospace Knowledge Graph.

Endpoints
─────────
  GET /graph/satellite/{norad_id}       — satellite subgraph
  GET /graph/operator/{name}            — operator profile + fleet
  GET /graph/country/{code}             — country space intelligence
  GET /graph/conjunctions/{norad_id}    — conjunction history for object
  GET /graph/mission/{mission_id}       — mission profile
  GET /graph/constellation/{name}       — constellation profile
  GET /graph/launch-vehicle/{vehicle_id}— launch vehicle + payload history
  GET /graph/search                     — full-text satellite search
  GET /graph/analytics/operators        — top operators by satellite count
  GET /graph/analytics/countries        — top countries by spacecraft
  GET /graph/analytics/conjunctions     — risk network
  GET /graph/analytics/constellations   — largest constellations
  GET /graph/analytics/regimes          — orbital regime density
  GET /graph/analytics/summary          — graph node/relationship counts
  POST /graph/populate                  — trigger PostgreSQL → Neo4j sync
  GET /graph/health                     — Neo4j connectivity check

Graceful degradation
────────────────────
  All endpoints return a 503 with a clear message when Neo4j is
  unavailable rather than crashing. This keeps the rest of the API
  (TLE ingest, conjunction screening) operational.

Phase 10: Visualization
────────────────────────
  The conjunction risk network endpoint (/graph/analytics/conjunctions)
  returns a graph-JSON format with nodes and edges arrays, directly
  consumable by D3.js, Sigma.js, or Neo4j Bloom.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.graph.connection import health_check as neo4j_health, is_available

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Guard decorator ───────────────────────────────────────────

def _require_neo4j():
    """Raise 503 if Neo4j is not available."""
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Neo4j Knowledge Graph is not available. "
                "Check NEO4J_* environment variables and Neo4j connectivity. "
                "All other API features remain operational."
            ),
        )


# ── Response models ───────────────────────────────────────────

class PopulateRequest(BaseModel):
    max_satellites:   int | None = Field(None, ge=1, le=100_000)
    max_conjunctions: int | None = Field(None, ge=1, le=50_000)


class PopulateTriggerResponse(BaseModel):
    accepted: bool = True
    run_id:   str
    message:  str


class GraphNetworkResponse(BaseModel):
    """Graph-JSON: nodes + edges for visualization."""
    nodes: list[dict]
    edges: list[dict]
    meta:  dict


# ── Phase 8: Satellite endpoints ──────────────────────────────

@router.get(
    "/satellite/{norad_id}",
    summary="Satellite knowledge graph subgraph",
    description=(
        "Returns the satellite node with all immediate relationships: "
        "operator, country, orbital regime, constellation, launch vehicle, "
        "and conjunction event count."
    ),
)
async def get_satellite_graph(norad_id: int) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.repositories.graph_repository import SatelliteGraphRepository
    repo   = SatelliteGraphRepository()
    result = await repo.get_satellite(norad_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Satellite NORAD {norad_id} not found in knowledge graph. "
                   f"Run POST /graph/populate to sync the catalog.",
        )
    return ORJSONResponse(content=result)


@router.get(
    "/search",
    summary="Full-text satellite search",
    description="Search satellite names, designators, and purposes using Neo4j full-text index.",
)
async def search_graph(
    q: Annotated[str, Query(min_length=2, description="Search query")],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.repositories.graph_repository import SatelliteGraphRepository
    repo    = SatelliteGraphRepository()
    results = await repo.search_satellites(q, limit=limit)
    return ORJSONResponse(content={"query": q, "count": len(results), "results": results})


# ── Phase 8: Operator endpoints ───────────────────────────────

@router.get(
    "/operator/{name}",
    summary="Operator intelligence profile",
    description=(
        "Returns an operator's fleet size, orbital regimes, constellation memberships, "
        "and unresolved conjunction risk summary."
    ),
)
async def get_operator_profile(name: str) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc     = GraphAnalyticsService()
    profile = await svc.operator_conjunction_risk_profile(name)
    if not profile:
        # Try to find the operator by name match
        from app.graph.connection import execute_read
        rows = await execute_read(
            """
            MATCH (op:Operator)
            WHERE toLower(op.name) CONTAINS toLower($name)
            OPTIONAL MATCH (op)<-[:OPERATED_BY]-(s:Satellite)
            RETURN op.name AS operator,
                   count(s) AS satelliteCount,
                   collect(DISTINCT s.regime)[..4] AS regimes
            LIMIT 10
            """,
            name=name,
        )
        return ORJSONResponse(content={"operator": name, "matches": rows, "conjunctions": {}})
    return ORJSONResponse(content=profile)


# ── Phase 8: Country endpoints ────────────────────────────────

@router.get(
    "/country/{code}",
    summary="Country space intelligence profile",
    description=(
        "Returns total/active spacecraft, operators, and launch sites "
        "for a country identified by ISO-3166-1 alpha-2 code."
    ),
)
async def get_country_profile(code: str) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc     = GraphAnalyticsService()
    profile = await svc.country_full_profile(code.upper())
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Country '{code}' not found. Use ISO-3166-1 alpha-2 code (e.g. IN, US, CN).",
        )
    return ORJSONResponse(content=profile)


# ── Phase 8: Conjunction graph endpoints ──────────────────────

@router.get(
    "/conjunctions/{norad_id}",
    summary="Conjunction history for a satellite",
    description="Returns all conjunction events involving this satellite, sorted by TCA descending.",
)
async def get_satellite_conjunctions(
    norad_id: int,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.repositories.graph_repository import ConjunctionGraphRepository
    repo    = ConjunctionGraphRepository()
    results = await repo.get_conjunctions_for_satellite(norad_id, limit=limit)
    return ORJSONResponse(content={
        "norad_id": norad_id,
        "count":    len(results),
        "events":   results,
    })


# ── Phase 8: Mission endpoints ────────────────────────────────

@router.get(
    "/mission/{mission_id}",
    summary="Mission profile",
    description="Returns mission metadata with linked satellites, agencies, and launch vehicles.",
)
async def get_mission_profile(mission_id: str) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc     = GraphAnalyticsService()
    profile = await svc.mission_profile(mission_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Mission '{mission_id}' not found in knowledge graph.",
        )
    return ORJSONResponse(content=profile)


# ── Phase 8: Constellation endpoints ─────────────────────────

@router.get(
    "/constellation/{name}",
    summary="Constellation profile",
    description=(
        "Returns constellation member count, operator, orbital regimes, "
        "and conjunction exposure summary."
    ),
)
async def get_constellation_profile(name: str) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc     = GraphAnalyticsService()
    profile = await svc.constellation_profile(name)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Constellation '{name}' not found in knowledge graph.",
        )
    return ORJSONResponse(content=profile)


# ── Phase 8: Launch vehicle endpoints ────────────────────────

@router.get(
    "/launch-vehicle/{vehicle_id}",
    summary="Launch vehicle profile with payload history",
    description="Returns launch vehicle details and list of all satellites launched by it.",
)
async def get_launch_vehicle_profile(vehicle_id: str) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.repositories.graph_repository import LaunchVehicleRepository
    from app.graph.services.graph_analytics_service import GraphAnalyticsService

    repo    = LaunchVehicleRepository()
    vehicle = await repo.get_by_id(vehicle_id)
    if not vehicle:
        raise HTTPException(
            status_code=404,
            detail=f"Launch vehicle '{vehicle_id}' not found. Try vehicle IDs like LV-FALCON9, LV-PSLV.",
        )

    svc     = GraphAnalyticsService()
    payloads = await svc.launch_vehicle_payload_history(vehicle_id)
    return ORJSONResponse(content={
        "vehicle":  vehicle,
        "payloads": payloads,
        "count":    len(payloads),
    })


# ── Phase 9: Analytics endpoints ─────────────────────────────

@router.get(
    "/analytics/operators",
    summary="Top operators by satellite count",
    description="Ranked list of satellite operators with fleet size and orbital regimes.",
)
async def analytics_top_operators(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[str | None, Query()] = None,
) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc    = GraphAnalyticsService()
    result = await svc.top_operators_by_satellite_count(limit=limit, status_filter=status)
    return ORJSONResponse(content={"count": len(result), "operators": result})


@router.get(
    "/analytics/countries",
    summary="Top countries by active spacecraft",
    description="Nations ranked by number of operational satellites.",
)
async def analytics_top_countries(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc    = GraphAnalyticsService()
    result = await svc.top_countries_by_active_spacecraft(limit=limit)
    return ORJSONResponse(content={"count": len(result), "countries": result})


@router.get(
    "/analytics/conjunctions",
    summary="Conjunction risk network (graph-JSON)",
    description=(
        "Returns a graph-JSON object (nodes + edges) representing the "
        "conjunction risk network. Directly consumable by D3.js, Sigma.js, "
        "Cytoscape.js, and Neo4j Bloom. "
        "Edges carry Pc, miss distance, and risk level."
    ),
    response_model=GraphNetworkResponse,
)
async def analytics_conjunction_network(
    min_pc: Annotated[float, Query(ge=1e-7, le=1.0)] = 1e-5,
    limit:  Annotated[int, Query(ge=1, le=1000)] = 200,
) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc   = GraphAnalyticsService()
    edges = await svc.conjunction_risk_network(min_pc=min_pc, limit=limit)

    # Build graph-JSON
    node_map: dict[int, dict] = {}
    edge_list = []

    for row in edges:
        for norad, name in ((row["norad1"], row["name1"]), (row["norad2"], row["name2"])):
            if norad not in node_map:
                node_map[norad] = {"id": str(norad), "label": name or str(norad), "type": "Satellite"}

        edge_list.append({
            "source":         str(row["norad1"]),
            "target":         str(row["norad2"]),
            "conjunctionId":  row["conjunctionId"],
            "Pc":             row["Pc"],
            "missKm":         row["missKm"],
            "riskLevel":      row["riskLevel"],
            "resolved":       row.get("resolved", False),
        })

    # Risk-color the nodes
    node_risk: dict[str, str] = {}
    for e in edge_list:
        risk = e["riskLevel"]
        for nid in (e["source"], e["target"]):
            if risk == "red" or (risk == "yellow" and node_risk.get(nid) != "red"):
                node_risk[nid] = risk
            elif nid not in node_risk:
                node_risk[nid] = risk or "green"

    for nid, node in node_map.items():
        node["riskLevel"] = node_risk.get(str(nid), "green")

    return ORJSONResponse(content={
        "nodes": list(node_map.values()),
        "edges": edge_list,
        "meta":  {
            "minPc":     min_pc,
            "nodeCount": len(node_map),
            "edgeCount": len(edge_list),
            "format":    "graph-json-v1",
        },
    })


@router.get(
    "/analytics/constellations",
    summary="Largest constellations",
    description="Constellations ranked by member count with orbital regime breakdown.",
)
async def analytics_constellations(
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc    = GraphAnalyticsService()
    result = await svc.largest_constellations(limit=limit)
    return ORJSONResponse(content={"count": len(result), "constellations": result})


@router.get(
    "/analytics/regimes",
    summary="Orbital regime density",
    description="Number of satellites, debris, and rocket bodies per orbital regime.",
)
async def analytics_regimes() -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc    = GraphAnalyticsService()
    result = await svc.orbital_regime_density()
    return ORJSONResponse(content={"regimes": result})


@router.get(
    "/analytics/risk-operators",
    summary="Top operators by conjunction risk",
    description="Operators ranked by unresolved conjunction exposure (max Pc).",
)
async def analytics_risk_operators(
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc    = GraphAnalyticsService()
    result = await svc.top_operators_by_conjunction_risk(limit=limit)
    return ORJSONResponse(content={"count": len(result), "operators": result})


@router.get(
    "/analytics/summary",
    summary="Graph node and relationship summary",
    description=(
        "Returns total node and relationship counts per label/type. "
        "Suitable for graph dashboard overview widgets."
    ),
)
async def analytics_summary() -> ORJSONResponse:
    _require_neo4j()
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    svc    = GraphAnalyticsService()
    result = await svc.graph_summary()
    return ORJSONResponse(content=result)


# ── Graph population trigger ──────────────────────────────────

@router.post(
    "/populate",
    status_code=202,
    summary="Trigger PostgreSQL → Neo4j graph population",
    description=(
        "Starts a background sync from the PostgreSQL satellite catalog "
        "and conjunction archive into the Neo4j Knowledge Graph. "
        "Returns 202 Accepted immediately. The run may take 2–10 minutes "
        "for a full 50K-object catalog."
    ),
)
async def trigger_graph_population(
    request: PopulateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> PopulateTriggerResponse:
    _require_neo4j()
    run_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(
        _run_graph_population,
        run_id=run_id,
        max_satellites=request.max_satellites,
        max_conjunctions=request.max_conjunctions,
    )
    return PopulateTriggerResponse(
        accepted=True,
        run_id=run_id,
        message=(
            f"Graph population started (run_id={run_id}). "
            f"Satellite nodes will appear in GET /graph/satellite/{{norad_id}} "
            f"as they are synced from PostgreSQL."
        ),
    )


async def _run_graph_population(
    run_id: str,
    max_satellites: int | None,
    max_conjunctions: int | None,
) -> None:
    """Background task body for API-triggered graph population."""
    try:
        from app.db.session import get_session_factory
        from app.graph.services.graph_population_service import GraphPopulationService
        factory = get_session_factory()
        async with factory() as session:
            svc    = GraphPopulationService(session)
            report = await svc.populate_all(
                run_id=run_id,
                max_satellites=max_satellites,
                max_conjunctions=max_conjunctions,
            )
            logger.info(
                "graph_population_api_complete run=%s status=%s sats=%d conj=%d",
                run_id, report.status,
                report.satellites_synced, report.conjunctions_synced,
            )
    except Exception:
        logger.exception("graph_population_background_failed run=%s", run_id)


# ── Health check ──────────────────────────────────────────────

@router.get(
    "/health",
    summary="Neo4j Knowledge Graph health check",
    description="Verifies Neo4j connectivity and returns node count.",
)
async def graph_health() -> ORJSONResponse:
    status = await neo4j_health()
    code   = 200 if status["reachable"] else 503
    return ORJSONResponse(content=status, status_code=code)
