"""
ORBITIQ-X — Aerospace Agent Framework API
==========================================
REST API for the LangGraph multi-agent aerospace reasoning system.

Endpoints
─────────
  POST /agents/query          — run full multi-agent query (background)
  POST /agents/research       — research-focused query (aerospace_research agent)
  POST /agents/plan           — plan-only: show routing without executing
  GET  /agents/explain/{task_id} — detailed workflow explanation
  GET  /agents/workflow/{task_id}— agent graph topology + execution trace
  GET  /agents/task/{task_id} — task status + result
  GET  /agents/task/{task_id}/stream — SSE streaming reasoning trace
  GET  /agents/tasks          — recent task list
  GET  /agents/health         — agent system health
  GET  /agents/agents         — list available agents + capabilities
  GET  /agents/examples       — example queries per agent

Agent orchestration
────────────────────
  The graph execution is: START → SupervisorAgent (classify + route)
  → parallel specialist agents → SafetyGate → synthesize → END

  All requests return task_id immediately (202 Accepted).
  Results are polled via GET /agents/task/{id} or streamed via SSE.

Existing code called (not rewritten)
──────────────────────────────────────
  agents/src/graph.py:
    run_aerospace_query() — full LangGraph execution
    stream_aerospace_query() — streaming execution
    AGENT_REGISTRY — {name: AgentClass}
    EXAMPLE_QUERIES — demo query dict
    ROUTING_TABLE — intent → agents mapping
  agents/src/supervisor/supervisor.py:
    ROUTING_TABLE, SupervisorAgent
  agents/src/agents/specialist_agents.py:
    All 7 specialist agents
"""
from __future__ import annotations

import json
import logging
import sys
import pathlib
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse, StreamingResponse

from app.core.config import Settings, get_settings
from app.schemas.agents import (
    AgentPlanResponse,
    AgentTaskResult,
    AgentTaskStatus,
    AgentWorkflowResponse,
    ExplainRequest,
    PlanRequest,
    TaskStatus,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskType,
)
from app.services.agent_service import AgentOrchestrationService

logger = structlog.get_logger(__name__)
router = APIRouter()

# Add agents to path for metadata queries
_AGENTS_ROOT = pathlib.Path(__file__).parents[5] / "agents"
if str(_AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENTS_ROOT))


def get_agent_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentOrchestrationService:
    return AgentOrchestrationService(settings=settings)


# ── POST /agents/query ────────────────────────────────────────

@router.post(
    "/query",
    response_model=TaskSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit multi-agent aerospace query",
    description=(
        "Submits a natural language aerospace question to the LangGraph "
        "multi-agent system. The Supervisor classifies intent and dispatches "
        "the appropriate specialist agents in parallel. "
        "Returns task_id immediately. Poll GET /agents/task/{task_id} for result. "
        "Example: 'Which ISRO satellites have the highest collision risk this week?'"
    ),
)
async def query_aerospace_agents(
    request: TaskSubmitRequest,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> TaskSubmitResponse:
    logger.info("agents.query.submitted", query=request.query[:60], type=request.task_type)
    task_id = await service.submit_task(request=request)
    return TaskSubmitResponse(
        task_id=task_id,
        status="queued",
        message=(
            f"Multi-agent query submitted (task_id={task_id}). "
            "The Supervisor will classify intent and dispatch specialist agents. "
            "Poll GET /agents/task/{task_id} or stream GET /agents/task/{task_id}/stream."
        ),
        session_id=request.session_id,
    )


# ── POST /agents/research ─────────────────────────────────────

@router.post(
    "/research",
    response_model=TaskSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit aerospace research query",
    description=(
        "Research-focused query that prioritises the AerospaceResearchAgent "
        "(GraphRAG + knowledge graph) alongside domain-specific agents. "
        "Suited for: 'Explain the Foster Pc method', "
        "'Summarize Artemis architecture', 'What debris events generated the Fengyun cloud?'"
    ),
)
async def research_aerospace(
    request: TaskSubmitRequest,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> TaskSubmitResponse:
    # Force research task type so service routes to research agent
    request.task_type = TaskType.RESEARCH
    task_id = await service.submit_task(request=request)
    return TaskSubmitResponse(
        task_id=task_id,
        status="queued",
        message=(
            f"Research query submitted (task_id={task_id}). "
            "AerospaceResearchAgent will lead with GraphRAG retrieval. "
            "Poll GET /agents/task/{task_id} for result."
        ),
    )


# ── POST /agents/plan ─────────────────────────────────────────

@router.post(
    "/plan",
    response_model=AgentPlanResponse,
    summary="Plan agent routing without executing",
    description=(
        "Classifies the query intent and returns the planned agent routing "
        "without executing the agents. Shows which agents would be invoked, "
        "why, what tools they would call, and estimated execution order. "
        "Zero LLM token cost — uses rule-based classification."
    ),
)
async def plan_agent_query(
    request: PlanRequest,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> AgentPlanResponse:
    return await service.plan_query(
        query=request.query,
        max_agents=request.max_agents,
    )


# ── GET /agents/explain/{task_id} ─────────────────────────────

@router.get(
    "/explain/{task_id}",
    summary="Explainable agent workflow trace",
    description=(
        "Returns a detailed explanation of how the agent system processed "
        "the query: which agents ran, what tools were called, what evidence "
        "was gathered, and how the final answer was synthesized. "
        "Phase 9 explainability — no unsupported conclusions."
    ),
)
async def explain_agent_task(
    task_id: str,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> ORJSONResponse:
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

    # Build full explanation
    explanation = {
        "task_id":       task_id,
        "query":         task.query,
        "query_intent":  task.query_intent,
        "status":        task.status.value,
        "final_answer":  task.final_answer,
        "confidence":    task.confidence,

        "reasoning_trace": {
            "step_1_classification": {
                "intent":             task.query_intent,
                "agents_selected":    task.agents_invoked,
                "description":        "Supervisor classified query intent and selected agents",
            },
            "step_2_parallel_execution": [
                {
                    "agent":         log.agent_name,
                    "started_at":    log.started_at,
                    "completed_at":  log.completed_at,
                    "success":       log.success,
                    "error":         log.error,
                    "output_keys":   service._agent_output_keys(log.agent_name),
                }
                for log in task.agent_call_log
            ],
            "step_3_safety_gate": {
                "flags":           task.safety_flags,
                "safety_approved": len(task.safety_flags) == 0,
            },
            "step_4_synthesis": {
                "sources_used":    len(task.cited_sources),
                "conjunctions":    len(task.conjunction_alerts),
                "maneuvers":       len(task.maneuver_recommendations),
                "reentry_alerts":  len(task.reentry_alerts),
            },
        },

        "evidence": [
            {
                "type":      e.source_type,
                "id":        e.source_id,
                "title":     e.title,
                "excerpt":   e.excerpt[:200],
                "relevance": e.relevance,
            }
            for e in task.cited_sources
        ],

        "safety_flags": task.safety_flags,
        "latency_ms":   task.latency_ms,
    }
    return ORJSONResponse(content=explanation)


# ── GET /agents/workflow/{task_id} ────────────────────────────

@router.get(
    "/workflow/{task_id}",
    summary="Agent graph topology and execution trace",
    description=(
        "Returns the LangGraph workflow topology and execution trace for a task. "
        "Includes node status (pending/running/complete/skipped), timing, "
        "and output keys for each agent node. "
        "Consumable by graph visualisation tools."
    ),
)
async def get_agent_workflow(
    task_id: str,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> ORJSONResponse:
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

    # Graph topology (matches agents/src/graph.py build_aerospace_graph)
    try:
        from src.graph import AGENT_REGISTRY, ROUTING_TABLE
        all_agents = list(AGENT_REGISTRY.keys())
    except ImportError:
        all_agents = [
            "orbital_dynamics", "conjunction_analysis", "space_debris",
            "mission_planning", "space_weather", "aerospace_research",
            "satellite_intelligence",
        ]

    topology = {
        "nodes": [
            {"id": "START",                "type": "control"},
            {"id": "classify_and_route",   "type": "supervisor"},
            *[{"id": a, "type": "specialist"} for a in all_agents],
            {"id": "safety_gate",          "type": "safety"},
            {"id": "synthesize",           "type": "supervisor"},
            {"id": "END",                  "type": "control"},
        ],
        "edges": (
            [{"from": "START", "to": "classify_and_route"}]
            + [{"from": "classify_and_route", "to": a, "conditional": True} for a in all_agents]
            + [{"from": a, "to": "safety_gate"} for a in all_agents]
            + [{"from": "safety_gate", "to": "synthesize"}, {"from": "synthesize", "to": "END"}]
        ),
        "parallel_agents": all_agents,
        "routing_strategy": "fan-out (Send API)",
    }

    return ORJSONResponse(content={
        "task_id":       task_id,
        "query":         task.query,
        "workflow":      [w.model_dump() for w in task.workflow],
        "graph_topology":topology,
        "final_answer":  task.final_answer,
        "status":        task.status.value,
    })


# ── GET /agents/task/{task_id} ────────────────────────────────

@router.get(
    "/task/{task_id}",
    response_model=AgentTaskResult,
    summary="Get agent task result",
    description=(
        "Returns the full result for a completed agent task, including: "
        "final answer, agent invocations, conjunction alerts, maneuver "
        "recommendations, safety flags, and cited sources."
    ),
)
async def get_task_result(
    task_id: str,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> AgentTaskResult:
    result = await service.get_task(task_id=task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return result


# ── GET /agents/task/{task_id}/stream ─────────────────────────

@router.get(
    "/task/{task_id}/stream",
    summary="Stream agent reasoning trace (SSE)",
    description=(
        "Server-Sent Events stream of real-time agent execution status. "
        "Emits status updates every 500ms until the task completes. "
        "Final event contains the complete answer and metadata."
    ),
)
async def stream_task_reasoning(
    task_id: str,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> StreamingResponse:
    async def sse_generator():
        async for event in service.stream_task(task_id=task_id):
            yield f"data: {event}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── GET /agents/tasks ─────────────────────────────────────────

@router.get(
    "/tasks",
    response_model=list[AgentTaskStatus],
    summary="List recent agent tasks",
    description="Returns the most recent agent tasks with status and metadata.",
)
async def list_recent_tasks(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> list[AgentTaskStatus]:
    return await service.list_tasks(limit=limit)


# ── GET /agents/health ────────────────────────────────────────

@router.get(
    "/health",
    summary="Agent system health",
    description=(
        "Returns health status of the agent framework: "
        "LangGraph availability, Anthropic connectivity, "
        "agent registry, and task store statistics."
    ),
)
async def agent_health() -> ORJSONResponse:
    # Check LangGraph
    langgraph_ok = False
    try:
        from langgraph.graph import StateGraph
        langgraph_ok = True
    except ImportError:
        pass

    # Check Anthropic
    anthropic_ok = False
    try:
        from app.core.config import get_settings
        s = get_settings()
        anthropic_ok = bool(s.ANTHROPIC_API_KEY.get_secret_value())
    except Exception:
        pass

    # Check agent registry
    agent_count = 0
    try:
        from src.graph import AGENT_REGISTRY
        agent_count = len(AGENT_REGISTRY)
    except ImportError:
        agent_count = 7  # known from audit

    from app.services.agent_service import _TASK_STORE
    task_counts = {s.value: 0 for s in TaskStatus}
    for t in _TASK_STORE.values():
        task_counts[t.status.value] = task_counts.get(t.status.value, 0) + 1

    overall = (
        "healthy"   if langgraph_ok and anthropic_ok else
        "degraded"  if langgraph_ok or anthropic_ok else
        "unhealthy"
    )

    return ORJSONResponse(content={
        "overall":       overall,
        "langgraph":     {"available": langgraph_ok},
        "anthropic":     {"configured": anthropic_ok, "model": "claude-sonnet-4-6"},
        "agents":        {"registered": agent_count, "all_agents": [
            "orbital_dynamics", "conjunction_analysis", "space_debris",
            "mission_planning", "space_weather", "aerospace_research",
            "satellite_intelligence",
        ]},
        "task_store":    {"total": len(_TASK_STORE), "by_status": task_counts},
        "graph_topology": "START → supervisor → [7 agents parallel] → safety_gate → synthesize → END",
    })


# ── GET /agents/agents ────────────────────────────────────────

@router.get(
    "/agents",
    summary="List available aerospace agents",
    description="Returns all registered specialist agents with their capabilities and tools.",
)
async def list_agents() -> ORJSONResponse:
    agents = [
        {
            "id":           "orbital_dynamics",
            "name":         "Orbital Dynamics Agent",
            "domain":       "Orbital mechanics, propagation, regime classification",
            "example_queries": [
                "Why did orbital decay increase?",
                "Explain LEO congestion patterns",
                "Show orbital regime transitions for Starlink",
            ],
            "tools": ["propagate_satellite_tool", "classify_orbit_tool",
                      "compute_ground_track_tool", "predict_passes_tool", "relative_motion_tool"],
        },
        {
            "id":           "conjunction_analysis",
            "name":         "Conjunction Intelligence Agent",
            "domain":       "Conjunction analysis, Pc computation, CDM interpretation, maneuver planning",
            "example_queries": [
                "Which satellites have the highest collision probability?",
                "Explain the CDM for NORAD 25544",
                "Generate a maneuver recommendation to avoid the Fengyun debris",
            ],
            "tools": ["screen_conjunctions_tool", "compute_foster_pc_tool",
                      "generate_cdm_tool", "compute_maneuver_tool"],
        },
        {
            "id":           "space_debris",
            "name":         "Space Debris Agent",
            "domain":       "Debris catalog, fragmentation events, re-entry predictions, decay anomalies",
            "example_queries": [
                "Which debris clouds are most hazardous to LEO operations?",
                "Explain the Cosmos 2251 / Iridium 33 collision aftermath",
                "Predict re-entries in the next 14 days",
            ],
            "tools": ["query_debris_catalog_tool", "monitor_reentry_tool",
                      "analyze_fragmentation_tool", "detect_decay_anomaly_tool"],
        },
        {
            "id":           "mission_planning",
            "name":         "Mission Intelligence Agent",
            "domain":       "Mission architecture, spacecraft relationships, launch windows, ΔV budgets",
            "example_queries": [
                "Explain Chandrayaan-3 architecture",
                "Summarize Artemis and participating agencies",
                "Compare Cartosat mission generations",
            ],
            "tools": ["compute_launch_window_tool", "compute_delta_v_tool",
                      "generate_trajectory_tool", "plan_mission_timeline_tool"],
        },
        {
            "id":           "space_weather",
            "name":         "Space Weather Agent",
            "domain":       "Kp index, F10.7 flux, geomagnetic storms, drag impact, radiation alerts",
            "example_queries": [
                "What is the current space weather and its effect on LEO?",
                "Is there a geomagnetic storm affecting satellite operations?",
            ],
            "tools": ["fetch_kp_index_tool", "fetch_f107_tool",
                      "assess_drag_impact_tool", "fetch_solar_events_tool"],
        },
        {
            "id":           "aerospace_research",
            "name":         "Aerospace Research Agent",
            "domain":       "GraphRAG corpus retrieval, knowledge graph queries, literature synthesis",
            "example_queries": [
                "Find literature supporting Foster Pc method limitations",
                "Summarize IADC debris mitigation guidelines",
                "Explain the 25-year deorbit rule and its exceptions",
            ],
            "tools": ["query_rag_tool", "query_knowledge_graph_tool",
                      "search_papers_tool", "summarize_topic_tool"],
        },
        {
            "id":           "satellite_intelligence",
            "name":         "Satellite Intelligence Agent",
            "domain":       "Fleet analysis, country intelligence, operator profiles, constellation analysis",
            "example_queries": [
                "Which operators have the highest conjunction density?",
                "Show all ISRO satellites currently in LEO",
                "Analyze the Starlink constellation orbital distribution",
            ],
            "tools": ["query_satellite_catalog_tool", "get_satellite_profile_tool",
                      "analyze_constellation_tool", "fetch_tle_tool"],
        },
    ]
    return ORJSONResponse(content={"count": len(agents), "agents": agents})


# ── GET /agents/examples ──────────────────────────────────────

@router.get(
    "/examples",
    summary="Example aerospace agent queries",
    description=(
        "Returns example queries demonstrating single-agent, multi-agent, "
        "and cross-domain reasoning capabilities."
    ),
)
async def get_example_queries() -> ORJSONResponse:
    try:
        from src.graph import EXAMPLE_QUERIES, ROUTING_TABLE
        base_examples = EXAMPLE_QUERIES
        routing = ROUTING_TABLE
    except ImportError:
        base_examples = {}
        routing = {}

    examples = {
        "single_agent": {
            "orbital_dynamics":      "Explain why orbital decay increased for Starlink satellites in 2024.",
            "conjunction_analysis":  "What is the current Pc for ISS conjunction CDM-20250617-120000-25544-44713?",
            "space_debris":          "How many trackable debris objects exist from the Fengyun-1C ASAT test?",
            "mission_planning":      "Summarize Artemis mission architecture and participating agencies.",
            "space_weather":         "What is the current Kp index and how does it affect LEO drag?",
            "aerospace_research":    "Explain the Foster (2001) probability of collision method.",
            "satellite_intelligence":"Which ISRO satellites are currently operational in SSO?",
        },
        "multi_agent": {
            "collision_risk":   "Which ISRO satellites have the highest collision probability and why?",
            "orbital_decay":    "Explain recent orbital decay anomalies and their causes.",
            "maneuver_planning":"Generate a maneuver recommendation for ISS to avoid the debris cloud.",
            "debris_analysis":  "Analyze the Cosmos 1408 ASAT test debris cloud and its risk profile.",
        },
        "cross_domain": {
            "operator_risk":    "Identify operators with the highest conjunction density and explain contributing factors.",
            "debris_chain":     "Which historical breakup events generated the largest high-risk debris chains?",
            "mission_conj":     "Show all PSLV-launched satellites currently involved in active conjunction events.",
            "weather_decay":    "How does the current solar cycle affect debris re-entry predictions?",
        },
        "routing_table": routing,
    }
    return ORJSONResponse(content=examples)
