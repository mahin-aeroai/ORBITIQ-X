"""
ORBITIQ-X — API v1 Router
==========================
Aggregates all domain-specific routers under the /api/v1 prefix.
Each domain router handles its own sub-prefix and authentication.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    satellites,
    ssa,
    conjunctions,
    knowledge_graph,
    rag,
    agents,
    mission,
    space_weather,
    auth,
)

api_v1_router = APIRouter()

# ─── Auth ─────────────────────────────────────────────────────────────────────
api_v1_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)

# ─── Satellite Catalog ────────────────────────────────────────────────────────
api_v1_router.include_router(
    satellites.router,
    prefix="/satellites",
    tags=["Satellite Catalog"],
)

# ─── Space Situational Awareness ──────────────────────────────────────────────
api_v1_router.include_router(
    ssa.router,
    prefix="/ssa",
    tags=["Space Situational Awareness"],
)

# ─── Conjunctions & Collision Avoidance ───────────────────────────────────────
api_v1_router.include_router(
    conjunctions.router,
    prefix="/conjunctions",
    tags=["Conjunction Analysis"],
)

# ─── Space Weather ────────────────────────────────────────────────────────────
api_v1_router.include_router(
    space_weather.router,
    prefix="/space-weather",
    tags=["Space Weather"],
)

# ─── Knowledge Graph ──────────────────────────────────────────────────────────
api_v1_router.include_router(
    knowledge_graph.router,
    prefix="/knowledge-graph",
    tags=["Knowledge Graph"],
)

# ─── RAG / AI Q&A ─────────────────────────────────────────────────────────────
api_v1_router.include_router(
    rag.router,
    prefix="/rag",
    tags=["RAG — Aerospace Q&A"],
)

# ─── Multi-Agent System ───────────────────────────────────────────────────────
api_v1_router.include_router(
    agents.router,
    prefix="/agents",
    tags=["Multi-Agent Reasoning"],
)

# ─── Mission Planning ─────────────────────────────────────────────────────────
api_v1_router.include_router(
    mission.router,
    prefix="/mission",
    tags=["Mission Planning"],
)

# ─── SSA Conjunction Assessment (Phase 12) ────────────────────────────────────
from app.api.v1.endpoints import ssa_conjunctions  # noqa: E402
api_v1_router.include_router(
    ssa_conjunctions.router,
    prefix="/ssa",
    tags=["SSA — Conjunction Assessment"],
)

# ─── Orbital Digital Twin Engine ─────────────────────────────────────────────
from app.api.v1.endpoints import digital_twin  # noqa: E402
api_v1_router.include_router(
    digital_twin.router,
    prefix="/digital-twin",
    tags=["Orbital Digital Twin"],
)

# ─── Foundation Model Platform ───────────────────────────────────────────────
from app.api.v1.endpoints import foundation  # noqa: E402
api_v1_router.include_router(
    foundation.router,
    prefix="/foundation",
    tags=["Foundation Model Platform"],
)

# ─── Catalog / Space-Track Ingestion ──────────────────────────────────────────
from app.api.v1.endpoints import catalog  # noqa: E402

api_v1_router.include_router(
    catalog.router,
    prefix="/catalog",
    tags=["Catalog — Space-Track Ingestion"],
)

# ─── CDM Document (separate path) ────────────────────────────────────────────
# CDM endpoint is under /conjunctions/cdm/{id} but also exposed at /cdm/{id}
# for direct document retrieval by external tools
from app.api.v1.endpoints.conjunctions import router as _conj_router
api_v1_router.include_router(
    _conj_router,
    prefix="/cdm",
    tags=["CDM Documents"],
    include_in_schema=False,  # avoid duplicate docs, real route is on /conjunctions
)
