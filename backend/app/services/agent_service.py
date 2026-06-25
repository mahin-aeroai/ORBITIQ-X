"""
ORBITIQ-X — Agent Orchestration Service
=========================================
Backend bridge between the FastAPI REST layer and the existing
LangGraph multi-agent system in agents/src/.

Architecture
────────────
  Backend REST endpoint (agents.py)
      ↓
  AgentOrchestrationService  ← this file
      ↓
  agents/src/graph.py → run_aerospace_query()
      ↓
  LangGraph: START → SupervisorAgent → [7 specialist agents in parallel]
           → SafetyGate → synthesize → END

What this service does NOT rewrite
────────────────────────────────────
  - agents/src/graph.py          → build_aerospace_graph(), run_aerospace_query()
  - agents/src/agents/*.py       → all 7 specialist agents (823 LOC)
  - agents/src/supervisor/       → SupervisorAgent + routing table
  - agents/src/safety/           → SafetyGate with fail-safe logic
  - agents/src/tools/            → all tool stubs with real signatures
  - agents/src/state/orbital_state.py → OrbitalState TypedDict + reducers

This service adds:
  - Task ID generation and in-memory task store
  - OrbitalState → AgentTaskResult serialisation
  - Graceful degradation (no Anthropic key → degraded mode)
  - Streaming SSE generator
  - Plan-only mode (supervisor classify without execution)

In-memory task store
─────────────────────
  For production, replace _TASK_STORE with Redis (ttl=24h).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import os
import pathlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

# Add agents package to path
# Locate agents/ directory — works in both local dev and Docker deployments
# In Docker: /app/app/services/... so parent[2] = /app = WORKDIR
# In local dev: backend/app/services/... so parent[3] = repo root
_this_file = pathlib.Path(__file__).resolve()
_agents_root_candidates = [
    _this_file.parents[3] / "agents",  # local: backend/app/services -> repo_root/agents
    _this_file.parents[2] / "agents",  # docker: /app/app/services -> /app/agents
    pathlib.Path(os.environ.get("AGENTS_ROOT", "")) if os.environ.get("AGENTS_ROOT") else None,
]
_AGENTS_ROOT = next((p for p in _agents_root_candidates if p and p.exists()), _this_file.parents[2] / "agents")
if str(_AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENTS_ROOT))

from app.schemas.agents import (
    AgentCallSummary, AgentPlanResponse, AgentTaskResult, AgentTaskStatus,
    AgentWorkflowNode, ConjunctionAlertSummary, EvidenceSummary,
    ManeuverRecommendationSummary, ReentryAlertSummary,
    TaskStatus, TaskSubmitRequest, TaskType,
)

logger = logging.getLogger(__name__)

_TASK_STORE: dict[str, AgentTaskResult] = {}
_MAX_TASKS = 1000


def _get_anthropic_client():
    try:
        from anthropic import AsyncAnthropic
        from app.core.config import get_settings
        s = get_settings()
        key = s.ANTHROPIC_API_KEY.get_secret_value()
        if not key:
            return None
        return AsyncAnthropic(api_key=key)
    except Exception as exc:
        logger.warning("anthropic_client_init_failed error=%s", exc)
        return None


class AgentOrchestrationService:
    """Orchestrates multi-agent aerospace reasoning queries."""

    def __init__(self, settings=None) -> None:
        self._settings = settings
        self._client   = None

    def _ensure_client(self):
        if self._client is None:
            self._client = _get_anthropic_client()
        return self._client

    # ── Task submission ───────────────────────────────────────

    async def submit_task(self, request: TaskSubmitRequest) -> str:
        task_id    = str(uuid.uuid4())
        session_id = request.session_id or str(uuid.uuid4())[:8]
        started_at = datetime.now(timezone.utc).isoformat()

        task = AgentTaskResult(
            task_id=task_id,
            session_id=session_id,
            status=TaskStatus.RUNNING,
            query=request.query,
            task_type=request.task_type.value,
            started_at=started_at,
        )
        _TASK_STORE[task_id] = task

        if len(_TASK_STORE) > _MAX_TASKS:
            oldest = sorted(_TASK_STORE.keys())[:100]
            for k in oldest:
                del _TASK_STORE[k]

        asyncio.create_task(
            self._execute_task(task_id, request, session_id)
        )
        logger.info(
            "agent_task_submitted task_id=%s type=%s query=%s",
            task_id, request.task_type, request.query[:60],
        )
        return task_id

    async def _execute_task(
        self, task_id: str, request: TaskSubmitRequest, session_id: str,
    ) -> None:
        t0   = time.perf_counter()
        task = _TASK_STORE.get(task_id)
        if not task:
            return

        client = self._ensure_client()
        if not client:
            task.status       = TaskStatus.COMPLETE
            task.final_answer = (
                "Multi-agent reasoning requires an Anthropic API key. "
                f"Set ANTHROPIC_API_KEY in .env. Query received: {request.query}"
            )
            task.confidence   = 0.0
            task.safety_flags = ["ANTHROPIC_API_KEY not configured"]
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.latency_ms   = round((time.perf_counter() - t0) * 1000, 1)
            return

        try:
            from src.graph import run_aerospace_query
            result_state = await run_aerospace_query(request.query, client, session_id)
            updated = self._state_to_result(task_id, session_id, request, result_state, t0)
            _TASK_STORE[task_id] = updated
        except Exception as exc:
            logger.exception("agent_task_execution_failed task_id=%s", task_id)
            task.status       = TaskStatus.FAILED
            task.errors       = [{"type": type(exc).__name__, "message": str(exc)}]
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.latency_ms   = round((time.perf_counter() - t0) * 1000, 1)

    # ── Task retrieval ────────────────────────────────────────

    async def get_task(self, task_id) -> AgentTaskResult | None:
        return _TASK_STORE.get(str(task_id))

    async def list_tasks(self, limit: int = 20) -> list[AgentTaskStatus]:
        tasks = sorted(_TASK_STORE.values(), key=lambda t: t.started_at or "", reverse=True)
        return [
            AgentTaskStatus(
                task_id=t.task_id, status=t.status, query=t.query[:100],
                task_type=t.task_type, agents_invoked=t.agents_invoked,
                started_at=t.started_at, completed_at=t.completed_at,
                latency_ms=t.latency_ms, has_flags=bool(t.safety_flags),
            )
            for t in tasks[:limit]
        ]

    # ── Streaming ─────────────────────────────────────────────

    async def stream_task(self, task_id) -> AsyncIterator[str]:
        tid  = str(task_id)
        task = _TASK_STORE.get(tid)
        if not task:
            yield json.dumps({"event": "error", "message": "task_not_found"})
            return

        for _ in range(120):
            task = _TASK_STORE.get(tid)
            if not task:
                break
            yield json.dumps({
                "event": "status", "status": task.status.value,
                "agents_invoked": task.agents_invoked,
                "safety_flags":   task.safety_flags,
            })
            if task.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.TIMEOUT):
                break
            await asyncio.sleep(0.5)

        task = _TASK_STORE.get(tid)
        if task:
            yield json.dumps({
                "event": "complete", "final_answer": task.final_answer,
                "confidence": task.confidence, "agents": task.agents_invoked,
                "flags": task.safety_flags, "latency_ms": task.latency_ms,
            })

    # ── Plan-only mode ────────────────────────────────────────

    async def plan_query(self, query: str, max_agents: int = 4) -> AgentPlanResponse:
        try:
            from src.supervisor.supervisor import ROUTING_TABLE
        except ImportError:
            ROUTING_TABLE = {}

        intent = self._fast_intent_classify(query)
        agents = ROUTING_TABLE.get(intent, ["aerospace_research"])[:max_agents]
        client = self._ensure_client()

        AGENT_TOOLS = {
            "orbital_dynamics":      ["propagate_satellite_tool", "classify_orbit_tool", "compute_ground_track_tool"],
            "conjunction_analysis":  ["screen_conjunctions_tool", "compute_foster_pc_tool", "generate_cdm_tool", "compute_maneuver_tool"],
            "space_debris":          ["query_debris_catalog_tool", "monitor_reentry_tool", "analyze_fragmentation_tool"],
            "mission_planning":      ["compute_launch_window_tool", "compute_delta_v_tool", "generate_trajectory_tool"],
            "space_weather":         ["fetch_kp_index_tool", "fetch_f107_tool", "assess_drag_impact_tool"],
            "aerospace_research":    ["query_rag_tool", "query_knowledge_graph_tool", "summarize_topic_tool"],
            "satellite_intelligence":["query_satellite_catalog_tool", "get_satellite_profile_tool", "analyze_constellation_tool"],
        }
        return AgentPlanResponse(
            query=query, intent=intent, agents_selected=agents,
            rationale={a: self._agent_rationale(a, query, intent) for a in agents},
            execution_order="parallel", estimated_agents=len(agents),
            routing_confidence=0.85 if client else 0.60,
            example_tools={a: AGENT_TOOLS.get(a, []) for a in agents},
        )

    # ── OrbitalState → AgentTaskResult ───────────────────────

    def _state_to_result(
        self, task_id: str, session_id: str, request: TaskSubmitRequest,
        state: dict, t0: float,
    ) -> AgentTaskResult:
        call_log = [
            AgentCallSummary(
                agent_name=rec.get("agent_name", "?"),
                started_at=rec.get("started_at", ""),
                completed_at=rec.get("completed_at"),
                success=rec.get("success", True),
                error=rec.get("error"),
                tokens_used=rec.get("tokens_used", 0),
            )
            for rec in state.get("agent_call_log", [])
        ]
        conj_alerts = [
            ConjunctionAlertSummary(
                conjunction_id=c.get("conjunction_id", ""),
                primary_norad=c.get("primary_norad", 0),
                secondary_norad=c.get("secondary_norad", 0),
                primary_name=c.get("primary_name", ""),
                secondary_name=c.get("secondary_name", ""),
                tca=c.get("tca", ""),
                miss_distance_km=float(c.get("miss_distance_km", 0)),
                collision_probability=float(c.get("collision_probability", 0)),
                risk_level=c.get("risk_level", "unknown"),
                maneuver_required=bool(c.get("maneuver_required", False)),
            )
            for c in state.get("conjunction_alerts", [])
        ]
        maneuver_recs = [
            ManeuverRecommendationSummary(
                target_norad=m.get("target_norad", 0),
                delta_v_kms=float(m.get("delta_v_kms", 0)),
                delta_v_direction=m.get("delta_v_direction", "along-track"),
                confidence=float(m.get("confidence", 0)),
                rationale=m.get("rationale", ""),
                safety_approved=bool(m.get("safety_approved", False)),
            )
            for m in state.get("maneuver_recommendations", [])
        ]
        reentry_alerts = [
            ReentryAlertSummary(
                norad_id=r.get("norad_id", 0),
                object_name=r.get("object_name", ""),
                predicted_reentry=r.get("predicted_reentry", ""),
                alert_level=r.get("alert_level", "WATCH"),
                lifetime_days=float(r.get("lifetime_days", 0)),
            )
            for r in state.get("reentry_alerts", [])
        ]
        evidence = [
            EvidenceSummary(
                source_type=s.get("source_type", "document"),
                source_id=s.get("doc_id", s.get("source_id", "")),
                title=s.get("title", ""),
                excerpt=str(s.get("excerpt", s.get("answer", "")))[:300],
                relevance=float(s.get("relevance_score", s.get("relevance", 0.7))),
            )
            for s in state.get("cited_sources", [])
        ]
        requested = state.get("requested_agents", [])
        workflow  = [
            AgentWorkflowNode(
                node_id=name, agent_name=name,
                status="complete" if any(r.agent_name == name and r.success for r in call_log)
                       else "skipped",
                started_at=next((r.started_at for r in call_log if r.agent_name == name), None),
                output_keys=self._agent_output_keys(name),
            )
            for name in requested
        ]
        return AgentTaskResult(
            task_id=task_id, session_id=session_id, status=TaskStatus.COMPLETE,
            query=request.query, task_type=request.task_type.value,
            final_answer=state.get("final_answer") or
                         "Agent analysis complete. See agent outputs above.",
            confidence=state.get("final_confidence"),
            query_intent=state.get("query_intent"),
            agents_invoked=requested, agent_call_log=call_log, workflow=workflow,
            conjunction_alerts=conj_alerts, maneuver_recommendations=maneuver_recs,
            reentry_alerts=reentry_alerts, cited_sources=evidence,
            safety_flags=state.get("safety_flags", []),
            errors=state.get("errors", []),
            started_at=state.get("started_at"),
            completed_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _fast_intent_classify(query: str) -> str:
        q = query.lower()
        if any(w in q for w in ("collision", "conjunction", "pc", "cdm", "risk")):
            return "collision_risk"
        if any(w in q for w in ("debris", "fragment", "breakup", "kessler")):
            return "debris_analysis"
        if any(w in q for w in ("decay", "reentry", "re-entry", "deorbit")):
            return "orbital_decay"
        if any(w in q for w in ("maneuver", "delta-v", "burn", "avoid")):
            return "maneuver_planning"
        if any(w in q for w in ("weather", "storm", "kp", "f10.7", "solar")):
            return "space_weather"
        if any(w in q for w in ("operator", "isro", "nasa", "esa", "spacex")):
            return "satellite_profile"
        if any(w in q for w in ("explain", "summarize", "what is", "describe")):
            return "research_question"
        if any(w in q for w in ("mission", "artemis", "chandrayaan", "launch")):
            return "research_question"
        return "general_ssa"

    @staticmethod
    def _agent_rationale(agent: str, query: str, intent: str) -> str:
        RATIONALE = {
            "orbital_dynamics":      "Orbital propagation and regime analysis needed",
            "conjunction_analysis":  "Pc computation and CDM interpretation required",
            "space_debris":          "Debris catalog and fragmentation analysis needed",
            "mission_planning":      "Mission architecture and trajectory analysis required",
            "space_weather":         "Current Kp/F10.7 needed to assess drag and radiation",
            "aerospace_research":    "GraphRAG corpus retrieval for grounded knowledge",
            "satellite_intelligence":"Satellite catalog and operator profile lookup",
        }
        return RATIONALE.get(agent, "Domain expert analysis required")

    @staticmethod
    def _agent_output_keys(agent: str) -> list[str]:
        KEYS = {
            "orbital_dynamics":      ["orbital_propagations", "orbit_classifications"],
            "conjunction_analysis":  ["conjunction_alerts", "maneuver_recommendations", "collision_risk_summary"],
            "space_debris":          ["debris_catalog_results", "reentry_alerts", "fragmentation_analysis"],
            "mission_planning":      ["mission_windows", "trajectory_options", "delta_v_budget"],
            "space_weather":         ["current_space_weather", "drag_impact_assessment"],
            "aerospace_research":    ["research_results", "cited_sources", "topic_summary"],
            "satellite_intelligence":["satellite_profiles", "operator_intel", "constellation_analysis"],
        }
        return KEYS.get(agent, [])
