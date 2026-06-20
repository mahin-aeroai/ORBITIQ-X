"""
ORBITIQ-X Multi-Agent System
FastAPI Application

Endpoints:
  POST /api/v1/agents/query          — run full multi-agent query
  POST /api/v1/agents/query/stream   — SSE streaming agent execution
  GET  /api/v1/agents/graph          — graph topology description
  GET  /api/v1/agents/health         — system health
  GET  /api/v1/agents/examples       — example queries

Production deployment:
  Gunicorn + UvicornWorker, 4 workers
  Redis checkpointing for conversation history
  Prometheus metrics at /metrics
  Structured logging (structlog)
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, Optional

from anthropic import AsyncAnthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .graph import (
    run_aerospace_query,
    stream_aerospace_query,
    EXAMPLE_QUERIES,
    AGENT_REGISTRY,
    ROUTING_TABLE,
)
from .state.orbital_state import initial_state

logger = logging.getLogger(__name__)


# ── Pydantic request/response ─────────────────────────────────

class AgentQueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=2000)
    session_id: Optional[str] = None
    max_agents: int = Field(4, ge=1, le=7)
    stream: bool = False


class AgentQueryResponse(BaseModel):
    session_id: str
    query: str
    intent: Optional[str]
    agents_invoked: list[str]
    final_answer: str
    confidence: Optional[float]
    safety_flags: list[str]
    maneuver_recommendations: list[dict]
    conjunction_alerts: list[dict]
    reentry_alerts: list[dict]
    cited_sources: list[dict]
    latency_ms: Optional[float]
    errors: list[dict]


# ── Lifespan ──────────────────────────────────────────────────

_anthropic_client: Optional[AsyncAnthropic] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _anthropic_client
    api_key = os.getenv("ANTHROPIC_API_KEY")
    _anthropic_client = AsyncAnthropic(api_key=api_key)
    logger.info("ORBITIQ-X Multi-Agent System started")
    yield
    logger.info("ORBITIQ-X Multi-Agent System stopped")


# ── App ───────────────────────────────────────────────────────

def create_agents_app() -> FastAPI:
    app = FastAPI(
        title="ORBITIQ-X Aerospace Multi-Agent System",
        version="1.0.0",
        description="7-agent LangGraph aerospace intelligence system",
        lifespan=lifespan,
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.post("/api/v1/agents/query", response_model=AgentQueryResponse)
    async def agent_query(req: AgentQueryRequest):
        if not _anthropic_client:
            raise HTTPException(503, "Agent system not initialized")

        state = await run_aerospace_query(
            query=req.query,
            client=_anthropic_client,
            session_id=req.session_id,
        )

        return AgentQueryResponse(
            session_id=state.get("session_id", ""),
            query=req.query,
            intent=state.get("query_intent"),
            agents_invoked=state.get("requested_agents", []),
            final_answer=state.get("final_answer", "No answer generated"),
            confidence=state.get("final_confidence"),
            safety_flags=state.get("safety_flags", []),
            maneuver_recommendations=state.get("maneuver_recommendations", []),
            conjunction_alerts=[
                a for a in state.get("conjunction_alerts", [])
                if a.get("risk_level") in ("red", "yellow")
            ],
            reentry_alerts=state.get("reentry_alerts", []),
            cited_sources=state.get("cited_sources", [])[:10],
            latency_ms=state.get("total_latency_ms"),
            errors=state.get("errors", []),
        )

    @app.post("/api/v1/agents/query/stream")
    async def agent_query_stream(req: AgentQueryRequest):
        if not _anthropic_client:
            raise HTTPException(503, "Agent system not initialized")

        async def event_generator():
            yield f"data: {json.dumps({'event': 'start', 'query': req.query})}\n\n"
            async for update in stream_aerospace_query(
                req.query, _anthropic_client, req.session_id
            ):
                yield f"data: {json.dumps(update)}\n\n"
            yield f"data: {json.dumps({'event': 'done'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/agents/graph")
    async def get_graph_topology():
        return {
            "agents": list(AGENT_REGISTRY.keys()),
            "routing_table": ROUTING_TABLE,
            "example_queries": EXAMPLE_QUERIES,
            "graph_type": "supervisor-parallel-safety-synthesis",
        }

    @app.get("/api/v1/agents/examples")
    async def get_examples():
        return EXAMPLE_QUERIES

    @app.get("/api/v1/agents/health")
    async def health():
        return {
            "status": "healthy",
            "agents": len(AGENT_REGISTRY),
            "timestamp": datetime.utcnow().isoformat(),
        }

    return app


app = create_agents_app()
