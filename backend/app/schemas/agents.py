"""
ORBITIQ-X — Agent System Pydantic Schemas
==========================================
Request / response models for the multi-agent REST API.

These schemas bridge the backend REST layer and the existing
agents/ LangGraph system. They serialise OrbitalState fields
into clean API responses without exposing internal state complexity.

Audit note
──────────
  agents/src/api/app.py already defines AgentQueryRequest +
  AgentQueryResponse for the standalone agents FastAPI app.
  These backend schemas provide the same contract but integrated
  into the main backend's DI / auth / routing system.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────

class TaskType(str, Enum):
    QUERY           = "query"
    RESEARCH        = "research"
    PLAN            = "plan"
    EXPLAIN         = "explain"
    CONJUNCTION     = "conjunction"
    ORBIT           = "orbit"
    DEBRIS          = "debris"
    MISSION         = "mission"
    LAUNCH          = "launch"
    OPERATOR        = "operator"

class TaskStatus(str, Enum):
    QUEUED      = "queued"
    RUNNING     = "running"
    COMPLETE    = "complete"
    FAILED      = "failed"
    TIMEOUT     = "timeout"


# ── Request models ────────────────────────────────────────────

class TaskSubmitRequest(BaseModel):
    query:      str = Field(..., min_length=5, max_length=2000,
                            description="Natural language aerospace question")
    task_type:  TaskType = TaskType.QUERY
    session_id: Optional[str] = Field(None, description="For multi-turn conversations")
    max_agents: int = Field(4, ge=1, le=7,
                            description="Maximum number of specialist agents to invoke")
    norad_ids:  list[int] = Field(default_factory=list,
                                  description="Specific NORAD IDs to focus on")
    stream:     bool = Field(False, description="Enable SSE streaming")


class PlanRequest(BaseModel):
    query:      str = Field(..., min_length=5)
    explain:    bool = Field(True, description="Include planner rationale")
    max_agents: int = Field(4, ge=1, le=7)


class ExplainRequest(BaseModel):
    query:      str = Field(..., min_length=5)
    depth:      int = Field(2, ge=1, le=4, description="Reasoning depth")
    include_tools: bool = True


# ── Response sub-models ───────────────────────────────────────

class AgentCallSummary(BaseModel):
    agent_name:   str
    started_at:   str
    completed_at: Optional[str]  = None
    success:      bool
    error:        Optional[str]  = None
    tokens_used:  int            = 0


class ConjunctionAlertSummary(BaseModel):
    conjunction_id:      str
    primary_norad:       int
    secondary_norad:     int
    primary_name:        str
    secondary_name:      str
    tca:                 str
    miss_distance_km:    float
    collision_probability: float
    risk_level:          str
    maneuver_required:   bool


class ManeuverRecommendationSummary(BaseModel):
    target_norad:     int
    delta_v_kms:      float
    delta_v_direction: str
    confidence:        float
    rationale:         str
    safety_approved:   bool


class ReentryAlertSummary(BaseModel):
    norad_id:      int
    object_name:   str
    predicted_reentry: str
    alert_level:   str
    lifetime_days: float


class AgentWorkflowNode(BaseModel):
    """One node in the agent execution graph for workflow visualisation."""
    node_id:      str
    agent_name:   str
    status:       str       # pending | running | complete | skipped
    started_at:   Optional[str] = None
    duration_ms:  Optional[float] = None
    output_keys:  list[str] = Field(default_factory=list)


class EvidenceSummary(BaseModel):
    source_type:  str       # graph_node | document | tool_result | conjunction
    source_id:    str
    title:        str
    excerpt:      str
    relevance:    float = 1.0


# ── Main response models ──────────────────────────────────────

class TaskSubmitResponse(BaseModel):
    task_id:    str = Field(default_factory=lambda: str(uuid4()))
    status:     str = "queued"
    message:    str
    session_id: Optional[str] = None


class AgentTaskResult(BaseModel):
    task_id:         str
    session_id:      str
    status:          TaskStatus
    query:           str
    task_type:       str

    # Core answer
    final_answer:    Optional[str]  = None
    confidence:      Optional[float]= None
    query_intent:    Optional[str]  = None

    # Agent execution trace (Phase explainability)
    agents_invoked:  list[str]               = Field(default_factory=list)
    agent_call_log:  list[AgentCallSummary]  = Field(default_factory=list)
    workflow:        list[AgentWorkflowNode] = Field(default_factory=list)

    # Domain-specific outputs
    conjunction_alerts:       list[ConjunctionAlertSummary]         = Field(default_factory=list)
    maneuver_recommendations: list[ManeuverRecommendationSummary]   = Field(default_factory=list)
    reentry_alerts:           list[ReentryAlertSummary]             = Field(default_factory=list)

    # Evidence and safety
    cited_sources:   list[EvidenceSummary] = Field(default_factory=list)
    safety_flags:    list[str]             = Field(default_factory=list)
    errors:          list[dict]            = Field(default_factory=list)

    # Timing
    started_at:      Optional[str]  = None
    completed_at:    Optional[str]  = None
    latency_ms:      Optional[float]= None

    # Raw state (for debugging — omitted in production)
    raw_state:       Optional[dict] = Field(None, exclude=True)


class AgentTaskStatus(BaseModel):
    task_id:      str
    status:       TaskStatus
    query:        str
    task_type:    str
    agents_invoked: list[str] = Field(default_factory=list)
    started_at:   Optional[str] = None
    completed_at: Optional[str] = None
    latency_ms:   Optional[float] = None
    has_flags:    bool = False


class AgentPlanResponse(BaseModel):
    query:           str
    intent:          str
    agents_selected: list[str]
    rationale:       dict[str, str]    # agent → reason
    execution_order: str               # "parallel" | "sequential"
    estimated_agents: int
    routing_confidence: float
    example_tools:   dict[str, list[str]]  # agent → tool names


class AgentWorkflowResponse(BaseModel):
    task_id:    str
    query:      str
    workflow:   list[AgentWorkflowNode]
    graph_topology: dict               # for visualisation
    final_answer: Optional[str] = None


# ── Legacy alias (for agents.py endpoint that imports these) ──
AgentTask = AgentTaskResult
