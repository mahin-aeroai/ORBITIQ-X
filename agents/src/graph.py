"""
ORBITIQ-X Multi-Agent System
LangGraph Graph Definition

Full graph topology:

  [START]
    │
    ▼
  supervisor.classify_and_route          (entry node)
    │
    ├─ requested_agents contains "orbital_dynamics"    → orbital_dynamics_node
    ├─ requested_agents contains "conjunction_analysis" → conjunction_node
    ├─ requested_agents contains "space_debris"         → debris_node
    ├─ requested_agents contains "mission_planning"     → mission_node
    ├─ requested_agents contains "space_weather"        → weather_node (runs first)
    ├─ requested_agents contains "aerospace_research"   → research_node
    └─ requested_agents contains "satellite_intelligence" → satellite_node

  All selected agent nodes run in PARALLEL (Send API / fan-out).
    │
    ▼
  safety_gate_node                       (sequential — checks all outputs)
    │
    ▼
  supervisor.synthesize                  (sequential — builds final answer)
    │
    ▼
  [END]

Parallel execution strategy:
  LangGraph Send API dispatches each requested agent as a separate
  branch. Branches rejoin at the safety gate node. Total latency =
  max(agent latencies), typically 5–15s for the full ensemble.

State management:
  Uses OrbitalState (TypedDict) with annotated reducers. List fields
  (conjunction_alerts, satellite_profiles, etc.) use _merge_list so
  parallel agent writes don't overwrite each other.

Checkpointing:
  AsyncSqliteSaver (dev) / AsyncPostgresSaver (prod) for conversation
  persistence and multi-turn support.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from anthropic import AsyncAnthropic
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.pregel import Send

from .agents.specialist_agents import (
    OrbitalDynamicsAgent,
    ConjunctionAnalysisAgent,
    SpaceDebrisAgent,
    MissionPlanningAgent,
    SpaceWeatherAgent,
    AerospaceResearchAgent,
    SatelliteIntelligenceAgent,
)
from .supervisor.supervisor import SupervisorAgent
from .safety.safety_gate import safety_gate_node
from .state.orbital_state import OrbitalState, initial_state

logger = logging.getLogger(__name__)

# ── Agent registry ────────────────────────────────────────────

AGENT_REGISTRY: dict[str, type] = {
    "orbital_dynamics":      OrbitalDynamicsAgent,
    "conjunction_analysis":  ConjunctionAnalysisAgent,
    "space_debris":          SpaceDebrisAgent,
    "mission_planning":      MissionPlanningAgent,
    "space_weather":         SpaceWeatherAgent,
    "aerospace_research":    AerospaceResearchAgent,
    "satellite_intelligence": SatelliteIntelligenceAgent,
}

# ── Node factory ──────────────────────────────────────────────

def make_agent_node(agent_class, client: AsyncAnthropic):
    """Create an async LangGraph node for a specialist agent."""
    agent = agent_class(client)

    async def node(state: OrbitalState) -> OrbitalState:
        logger.info(f"Running agent: {agent.name}")
        return await agent.run(state)

    node.__name__ = agent.name
    return node


# ── Routing functions ─────────────────────────────────────────

def route_to_agents(state: OrbitalState) -> list[Send] | str:
    """
    Conditional edge after supervisor.classify_and_route.
    Returns a list of Send objects for parallel fan-out to specialist agents.

    Space weather agent always runs first if in the list, because
    other agents (mission planning, debris) need weather data.
    If no agents selected, go directly to synthesis.
    """
    requested = state.get("requested_agents", [])
    if not requested:
        logger.warning("No agents requested — going straight to synthesis")
        return "safety_gate"

    # Weather agent dispatched as part of the fan-out;
    # mission planning will read weather from state after merge
    sends = [
        Send(agent_name, state)
        for agent_name in requested
        if agent_name in AGENT_REGISTRY
    ]

    logger.info(f"Dispatching {len(sends)} agents in parallel: {requested}")
    return sends


def after_safety_gate(state: OrbitalState) -> Literal["synthesize", END]:
    """
    Conditional edge after safety gate.
    If synthesis_complete is already True (shouldn't happen), go to END.
    Otherwise always go to synthesize.
    """
    if state.get("synthesis_complete"):
        return END
    return "synthesize"


# ── Graph builder ─────────────────────────────────────────────

def build_aerospace_graph(client: AsyncAnthropic) -> StateGraph:
    """
    Build and compile the full ORBITIQ-X LangGraph multi-agent graph.

    Returns a compiled graph ready for invocation:
        graph = build_aerospace_graph(client)
        result = await graph.ainvoke(initial_state("Which satellites have highest collision risk?"))
    """
    supervisor = SupervisorAgent(client)
    graph = StateGraph(OrbitalState)

    # ── Add supervisor nodes ──────────────────────────────────
    graph.add_node("classify_and_route", supervisor.classify_and_route)
    graph.add_node("synthesize", supervisor.synthesize)

    # ── Add specialist agent nodes ────────────────────────────
    for name, agent_class in AGENT_REGISTRY.items():
        graph.add_node(name, make_agent_node(agent_class, client))

    # ── Add safety gate node ──────────────────────────────────
    graph.add_node("safety_gate", safety_gate_node)

    # ── Wire edges ────────────────────────────────────────────

    # Entry: START → supervisor classification
    graph.add_edge(START, "classify_and_route")

    # Fan-out: supervisor → parallel agents (conditional)
    graph.add_conditional_edges(
        "classify_and_route",
        route_to_agents,
        # All possible targets
        path_map={agent: agent for agent in AGENT_REGISTRY},
    )

    # Fan-in: all agents → safety gate (sequential join)
    for name in AGENT_REGISTRY:
        graph.add_edge(name, "safety_gate")

    # Safety gate → synthesis (or END)
    graph.add_conditional_edges(
        "safety_gate",
        after_safety_gate,
        path_map={"synthesize": "synthesize", END: END},
    )

    # Synthesis → END
    graph.add_edge("synthesize", END)

    # Compile with async support
    compiled = graph.compile()
    logger.info("ORBITIQ-X aerospace graph compiled successfully")
    return compiled


# ── Streaming graph for SSE ───────────────────────────────────

async def stream_aerospace_query(
    query: str,
    client: AsyncAnthropic,
    session_id: str | None = None,
) -> Any:
    """
    Execute the graph with streaming output.
    Yields state updates as they arrive from each agent.
    """
    graph = build_aerospace_graph(client)
    state = initial_state(query, session_id)

    async for event in graph.astream(state, stream_mode="updates"):
        node_name = list(event.keys())[0]
        node_output = event[node_name]
        yield {
            "node": node_name,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            "data": {
                k: v for k, v in node_output.items()
                if k in (
                    "collision_risk_summary", "safety_flags", "final_answer",
                    "query_intent", "requested_agents", "reentry_alerts",
                    "maneuver_recommendations", "current_space_weather",
                )
                and v
            },
        }


# ── FastAPI integration ───────────────────────────────────────

async def run_aerospace_query(
    query: str,
    client: AsyncAnthropic,
    session_id: str | None = None,
) -> OrbitalState:
    """
    Run a complete multi-agent query and return the final state.
    """
    import time
    graph = build_aerospace_graph(client)
    state = initial_state(query, session_id)

    t0 = time.perf_counter()
    result = await graph.ainvoke(state)
    latency_ms = (time.perf_counter() - t0) * 1000

    result["total_latency_ms"] = round(latency_ms, 1)
    logger.info(
        f"Query complete in {latency_ms:.0f}ms | "
        f"agents={result.get('requested_agents')} | "
        f"flags={len(result.get('safety_flags', []))}"
    )
    return result


# ── Example query handler (for documentation) ────────────────

EXAMPLE_QUERIES = {
    "collision_risk": "Which satellites have the highest collision risk this week?",
    "orbital_decay":  "Explain orbital decay anomalies detected in the past 30 days.",
    "maneuver":       "Generate a maneuver recommendation for ISS to avoid the debris cloud.",
    "research":       "Summarize the Artemis program architecture and current status.",
    "weather":        "What is the current space weather and how does it affect LEO satellites?",
    "debris":         "How many trackable debris objects exist from the Fengyun-1C ASAT test?",
    "passes":         "When will CARTOSAT-3 be visible from Hyderabad this week?",
}
