"""
ORBITIQ-X — API v1 Router
==========================
Aggregates all domain-specific routers under the /api/v1 prefix.
RBAC protection is applied at the router level via FastAPI dependencies.

Access matrix (Phase 14A)
──────────────────────────
  /auth/*          public
  /satellites/*    any authenticated user
  /space-weather/* any authenticated user
  /mission/*       analyst | operator | admin
  /ssa/*           operator | admin
  /conjunctions/*  operator | admin
  /digital-twin/*  operator | admin
  /agents/*        analyst | admin
  /knowledge-graph/* analyst | admin
  /rag/*           analyst | admin
  /catalog/*       operator | admin
  /foundation/*    admin only
"""
from fastapi import APIRouter, Depends

from app.api.v1.endpoints.knowledge_intelligence import router as knowledge_intelligence_router
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
from app.core.security.deps import (
    require_min_role,
    require_roles,
    get_current_user,
)

# Pre-built dependency shortcuts
_any_auth    = Depends(get_current_user)
_analyst     = Depends(require_min_role("analyst"))
_operator    = Depends(require_min_role("operator"))
_admin       = Depends(require_roles("admin"))

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
    dependencies=[_any_auth],
)

# ─── Space Situational Awareness ──────────────────────────────────────────────
api_v1_router.include_router(
    ssa.router,
    prefix="/ssa",
    tags=["Space Situational Awareness"],
    dependencies=[_operator],
)

# ─── Conjunctions & Collision Avoidance ───────────────────────────────────────
api_v1_router.include_router(
    conjunctions.router,
    prefix="/conjunctions",
    tags=["Conjunction Analysis"],
    dependencies=[_operator],
)

# ─── Space Weather ────────────────────────────────────────────────────────────
api_v1_router.include_router(
    space_weather.router,
    prefix="/space-weather",
    tags=["Space Weather"],
    dependencies=[_any_auth],
)

# ─── Knowledge Graph ──────────────────────────────────────────────────────────
api_v1_router.include_router(
    knowledge_graph.router,
    prefix="/knowledge-graph",
    tags=["Knowledge Graph"],
    dependencies=[_analyst],
)

# ─── RAG / AI Q&A ─────────────────────────────────────────────────────────────
api_v1_router.include_router(
    rag.router,
    prefix="/rag",
    tags=["RAG — Aerospace Q&A"],
    dependencies=[_analyst],
)

# ─── Multi-Agent System ───────────────────────────────────────────────────────
api_v1_router.include_router(
    agents.router,
    prefix="/agents",
    tags=["Multi-Agent Reasoning"],
    dependencies=[_analyst],
)

# ─── Mission Planning ─────────────────────────────────────────────────────────
api_v1_router.include_router(
    mission.router,
    prefix="/mission",
    tags=["Mission Planning"],
    dependencies=[_analyst],
)

# ─── SSA Conjunction Assessment (Phase 12) ────────────────────────────────────
from app.api.v1.endpoints import ssa_conjunctions  # noqa: E402
api_v1_router.include_router(
    ssa_conjunctions.router,
    prefix="/ssa",
    tags=["SSA — Conjunction Assessment"],
    dependencies=[_operator],
)

# ─── SSA Alert SSE Bridge (Phase 13B) ─────────────────────────────────────────
from app.api.v1.endpoints import ssa_alerts  # noqa: E402
api_v1_router.include_router(
    ssa_alerts.router,
    prefix="/ssa",
    tags=["SSA — Alert Stream"],
    dependencies=[_operator],
)

# ─── Orbital Digital Twin Engine ─────────────────────────────────────────────
from app.api.v1.endpoints import digital_twin  # noqa: E402
api_v1_router.include_router(
    digital_twin.router,
    prefix="/digital-twin",
    tags=["Orbital Digital Twin"],
    dependencies=[_operator],
)

# ─── Foundation Model Platform ───────────────────────────────────────────────
from app.api.v1.endpoints import foundation  # noqa: E402
api_v1_router.include_router(
    foundation.router,
    prefix="/foundation",
    tags=["Foundation Model Platform"],
    dependencies=[_admin],
)

# ─── Catalog / Space-Track Ingestion ──────────────────────────────────────────
from app.api.v1.endpoints import catalog  # noqa: E402

api_v1_router.include_router(
    catalog.router,
    prefix="/catalog",
    tags=["Catalog — Space-Track Ingestion"],
    dependencies=[_operator],
)

# ─── Platform Observability ───────────────────────────────────────────────────
from app.api.v1.endpoints import platform  # noqa: E402
api_v1_router.include_router(
    platform.router,
    prefix="/platform",
    tags=["Platform Observability"],
    dependencies=[_any_auth],
)

# ─── CAEM Relationships (Phase 17.2)
from app.api.v1.endpoints import relationships  # noqa: E402
api_v1_router.include_router(
    relationships.router,
    tags=["CAEM — Relationships"],
    dependencies=[_analyst],
)

# ─── CAEM Entities (Phase 17.1 / 17.5) ──────────────────────────────────────
from app.api.v1.endpoints.entities import router as entities_router  # noqa: E402
api_v1_router.include_router(
    entities_router,
    tags=["CAEM — Entities"],
    dependencies=[_analyst],
)

# ─── CAEM Provenance (Phase 17.3) ────────────────────────────────────────────
from app.api.v1.endpoints.provenance import router as provenance_router  # noqa: E402
api_v1_router.include_router(
    provenance_router,
    tags=["CAEM — Provenance"],
    dependencies=[_analyst],
)

# ─── CAEM Ingestion (Phase 17.4) ─────────────────────────────────────────────
from app.api.v1.endpoints.ingestion import router as ingestion_router  # noqa: E402
api_v1_router.include_router(
    ingestion_router,
    tags=["CAEM — Ingestion"],
    dependencies=[_admin],
)

# ─── CDM Document (separate path) ────────────────────────────────────────────
# CDM endpoint is under /conjunctions/cdm/{id} but also exposed at /cdm/{id}
# for direct document retrieval by external tools.
# Auth: operator+ — same as /conjunctions (H-01 fix: add missing dependencies=)
from app.api.v1.endpoints.conjunctions import router as _conj_router
api_v1_router.include_router(
    _conj_router,
    prefix="/cdm",
    tags=["CDM Documents"],
    dependencies=[_operator],        # FIX H-01: was missing, exposed /cdm unauthenticated
    include_in_schema=False,         # avoid duplicate docs, real route is on /conjunctions
)
# ─── Knowledge Intelligence (Phases 17.7-17.10) ──────────────────────────────
api_v1_router.include_router(
    knowledge_intelligence_router,
    tags=["Knowledge Intelligence"],
    dependencies=[_analyst],
)
