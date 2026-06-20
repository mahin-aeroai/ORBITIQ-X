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
