"""
ORBITIQ-X Multi-Agent System
Shared Agent State — LangGraph TypedDict

The state is the single source of truth shared across all agents
in the LangGraph graph. Every agent reads from and writes to this
structure. LangGraph handles state merging via the reducer pattern.

Design:
  - Immutable input fields (query, session_id) set at graph entry
  - Mutable output fields filled by each specialist agent
  - Supervisor reads all output fields to synthesize final response
  - Safety fields halt graph execution if red conditions met
  - Message history for multi-turn conversation context
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import uuid4

from langgraph.graph import MessagesState
from typing_extensions import TypedDict


def _merge_list(a: list, b: list) -> list:
    """Reducer: extend lists from multiple agents."""
    return a + b


def _merge_dict(a: dict, b: dict) -> dict:
    """Reducer: merge dicts, later agent wins on key conflict."""
    return {**a, **b}


def _keep_last(a: Any, b: Any) -> Any:
    """Reducer: keep the latest value."""
    return b if b is not None else a


class AgentCallRecord(TypedDict):
    agent_name: str
    started_at: str
    completed_at: Optional[str]
    success: bool
    error: Optional[str]
    tokens_used: int


class ConjunctionAlert(TypedDict):
    conjunction_id: str
    primary_norad: int
    secondary_norad: int
    primary_name: str
    secondary_name: str
    tca: str
    miss_distance_km: float
    collision_probability: float
    risk_level: str            # red | yellow | green
    maneuver_required: bool
    maneuver_deadline: Optional[str]


class ManeuverRecommendation(TypedDict):
    target_norad: int
    recommended_at: str
    burn_time: str             # ISO datetime
    delta_v_kms: float
    delta_v_direction: str     # radial | along-track | cross-track
    new_perigee_km: float
    new_apogee_km: float
    fuel_cost_kg: float
    confidence: float
    rationale: str
    safety_approved: bool


class ReentryAlert(TypedDict):
    norad_id: int
    object_name: str
    predicted_reentry: str
    lifetime_days: float
    alert_level: str           # IMMINENT | CRITICAL | URGENT | WARNING | WATCH
    uncertainty_hours: float


class SpaceWeatherCondition(TypedDict):
    kp_index: float
    f107_flux: float
    storm_category: str        # G1-G5 | none
    density_effect_pct: float
    recommended_action: str


class OrbitalDecayAnomaly(TypedDict):
    norad_id: int
    object_name: str
    observed_decay_rate: float  # km/day
    expected_decay_rate: float
    anomaly_magnitude_sigma: float
    probable_cause: str
    confidence: float


class AerospaceKnowledge(TypedDict):
    query: str
    answer: str
    sources: list[dict]
    confidence: float
    faithfulness_score: float


class OrbitalState(TypedDict):
    """Full LangGraph state shared across all agents."""

    # ── Immutable inputs ──────────────────────────────────────
    # session_id is written once by supervisor and read-only by agents.
    # Annotated with last-write-wins to avoid InvalidUpdateError when
    # agents run in parallel and all emit the same session_id value.
    session_id: Annotated[str, lambda a, b: b]
    user_query: Annotated[str, lambda a, b: b]
    query_intent: Annotated[Optional[str], lambda a, b: b if b is not None else a]
    query_entities: Annotated[list[str], lambda a, b: b if b else a]
    conversation_history: Annotated[list[dict], lambda a, b: b if b else a]
    requested_agents: Annotated[list[str], lambda a, b: b if b else a]

    # ── Supervisor fields ─────────────────────────────────────
    routing_decision: Optional[dict]  # {agent: reason}
    final_answer: Optional[str]
    final_confidence: Optional[float]
    synthesis_complete: bool

    # ── Orbital Dynamics Agent output ─────────────────────────
    orbital_propagations: Annotated[list[dict], _merge_list]
    orbit_classifications: Annotated[list[dict], _merge_list]
    ground_track_points: Annotated[list[dict], _merge_list]
    pass_predictions: Annotated[list[dict], _merge_list]
    relative_motion_analysis: Annotated[list[dict], _merge_list]

    # ── Conjunction Analysis Agent output ─────────────────────
    conjunction_alerts: Annotated[list[ConjunctionAlert], _merge_list]
    maneuver_recommendations: Annotated[list[ManeuverRecommendation], _merge_list]
    collision_risk_summary: Optional[str]
    high_risk_objects: Annotated[list[int], _merge_list]  # NORAD IDs

    # ── Space Debris Agent output ─────────────────────────────
    debris_catalog_results: Annotated[list[dict], _merge_list]
    reentry_alerts: Annotated[list[ReentryAlert], _merge_list]
    fragmentation_analysis: Annotated[list[dict], _merge_list]
    orbital_decay_anomalies: Annotated[list[OrbitalDecayAnomaly], _merge_list]

    # ── Mission Planning Agent output ─────────────────────────
    mission_windows: Annotated[list[dict], _merge_list]
    delta_v_budget: Optional[dict]
    trajectory_options: Annotated[list[dict], _merge_list]
    launch_opportunities: Annotated[list[dict], _merge_list]
    mission_timeline: Optional[dict]

    # ── Space Weather Agent output ────────────────────────────
    current_space_weather: Optional[SpaceWeatherCondition]
    weather_forecast: Annotated[list[dict], _merge_list]
    atmospheric_density_model: Optional[dict]
    drag_impact_assessment: Optional[str]
    radiation_alerts: Annotated[list[dict], _merge_list]

    # ── Aerospace Research Agent output ───────────────────────
    research_results: Annotated[list[AerospaceKnowledge], _merge_list]
    knowledge_graph_results: Annotated[list[dict], _merge_list]
    cited_sources: Annotated[list[dict], _merge_list]
    topic_summary: Optional[str]

    # ── Satellite Intelligence Agent output ───────────────────
    satellite_profiles: Annotated[list[dict], _merge_list]
    operator_intel: Annotated[list[dict], _merge_list]
    catalog_search_results: Annotated[list[dict], _merge_list]
    constellation_analysis: Optional[dict]
    satellite_health: Annotated[list[dict], _merge_list]

    # ── Safety and monitoring ─────────────────────────────────
    safety_approved: bool
    safety_flags: Annotated[list[str], _merge_list]
    safety_override_reason: Optional[str]
    agent_call_log: Annotated[list[AgentCallRecord], _merge_list]
    errors: Annotated[list[dict], _merge_list]

    # ── Timing and metadata ───────────────────────────────────
    started_at: str
    completed_at: Optional[str]
    total_latency_ms: Optional[float]
    tokens_total: int
    graph_iteration: int


def initial_state(query: str, session_id: Optional[str] = None) -> OrbitalState:
    """Create a fresh OrbitalState for a new query."""
    return OrbitalState(
        session_id=session_id or str(uuid4()),
        user_query=query,
        query_intent=None,
        query_entities=[],
        conversation_history=[],
        requested_agents=[],
        routing_decision=None,
        final_answer=None,
        final_confidence=None,
        synthesis_complete=False,
        orbital_propagations=[],
        orbit_classifications=[],
        ground_track_points=[],
        pass_predictions=[],
        relative_motion_analysis=[],
        conjunction_alerts=[],
        maneuver_recommendations=[],
        collision_risk_summary=None,
        high_risk_objects=[],
        debris_catalog_results=[],
        reentry_alerts=[],
        fragmentation_analysis=[],
        orbital_decay_anomalies=[],
        mission_windows=[],
        delta_v_budget=None,
        trajectory_options=[],
        launch_opportunities=[],
        mission_timeline=None,
        current_space_weather=None,
        weather_forecast=[],
        atmospheric_density_model=None,
        drag_impact_assessment=None,
        radiation_alerts=[],
        research_results=[],
        knowledge_graph_results=[],
        cited_sources=[],
        topic_summary=None,
        satellite_profiles=[],
        operator_intel=[],
        catalog_search_results=[],
        constellation_analysis=None,
        satellite_health=[],
        safety_approved=True,
        safety_flags=[],
        safety_override_reason=None,
        agent_call_log=[],
        errors=[],
        started_at=datetime.utcnow().isoformat(),
        completed_at=None,
        total_latency_ms=None,
        tokens_total=0,
        graph_iteration=0,
    )
