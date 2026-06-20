"""
ORBITIQ-X Multi-Agent System
Supervisor Agent

The supervisor is the orchestrator node in the LangGraph graph.
It runs at three points:
  1. Entry: classify intent, decide which agents to invoke, set requested_agents
  2. After each agent batch: check if more agents needed (conditional edge)
  3. Exit: synthesize all agent outputs into final answer

Intent classification maps queries to agent combinations:
  "collision risk"      → conjunction + debris + orbital + weather
  "orbital decay"       → debris + orbital + weather
  "maneuver"            → conjunction + mission + orbital
  "research / explain"  → research + (domain agents based on topic)
  "satellite profile"   → satellite_intel + orbital
  "launch window"       → mission + weather + orbital

The supervisor uses Claude to classify intent and then applies
deterministic routing rules — not LLM routing — for reliability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from anthropic import AsyncAnthropic

from ..state.orbital_state import OrbitalState

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

INTENT_CLASSIFIER_PROMPT = """You are the intent classifier for ORBITIQ-X, an aerospace SSA system.

Classify the user query into ONE of these intent categories:

  collision_risk       — collision probability, CDM, conjunction events, which satellites at risk
  orbital_decay        — orbital decay, re-entry, atmospheric drag anomalies, decay predictions
  maneuver_planning    — avoidance maneuver, ΔV recommendation, burn planning, avoidance
  mission_planning     — launch window, transfer orbit, mission design, trajectory
  space_weather        — solar activity, Kp index, geomagnetic storm, F10.7, radiation
  satellite_profile    — specific satellite status, TLE, operator, constellation details
  debris_analysis      — debris cloud, fragmentation, catalog, ASAT aftermath
  research_question    — explain a concept, summarize a mission, compare technologies
  pass_prediction      — when will satellite be visible, AOS/LOS, ground contact
  general_ssa          — general SSA / space situational awareness query

Also extract entities: NORAD IDs (5-digit numbers), mission names, satellite names,
launch vehicle names, location names, dates.

Return ONLY a JSON object:
{
  "intent": "<category>",
  "entities": ["<entity1>", "<entity2>"],
  "primary_agents": ["<agent1>", "<agent2>"],
  "secondary_agents": ["<agent3>"],
  "confidence": 0.0,
  "rationale": "<one sentence>"
}

Agent names: orbital_dynamics, conjunction_analysis, space_debris,
mission_planning, space_weather, aerospace_research, satellite_intelligence"""

SYNTHESIS_PROMPT = """You are the ORBITIQ-X mission director synthesizing a multi-agent intelligence briefing.

Multiple specialist agents have run in parallel. Synthesize their findings into a
single authoritative answer. Follow these rules:

1. Structure the answer with clear sections matching what was requested
2. Prioritize safety-critical information first (red conjunction events, re-entry alerts)
3. Include specific numbers: Pc values, miss distances, altitudes, ΔV amounts
4. Cite agent sources: (Orbital Dynamics) / (Conjunction Analysis) / etc.
5. Flag any safety_flags prominently
6. If agents disagree, note the discrepancy and recommend conservative interpretation
7. End with a confidence assessment

Agent outputs available:
{agent_outputs}

Safety flags:
{safety_flags}

Original query: {query}

Synthesized answer:"""


# ── Intent classification ─────────────────────────────────────

ROUTING_TABLE: dict[str, list[str]] = {
    "collision_risk":    ["conjunction_analysis", "space_debris", "orbital_dynamics", "space_weather"],
    "orbital_decay":     ["space_debris", "orbital_dynamics", "space_weather"],
    "maneuver_planning": ["conjunction_analysis", "mission_planning", "orbital_dynamics"],
    "mission_planning":  ["mission_planning", "orbital_dynamics", "space_weather"],
    "space_weather":     ["space_weather", "orbital_dynamics"],
    "satellite_profile": ["satellite_intelligence", "orbital_dynamics"],
    "debris_analysis":   ["space_debris", "orbital_dynamics", "space_weather"],
    "research_question": ["aerospace_research"],
    "pass_prediction":   ["orbital_dynamics", "satellite_intelligence"],
    "general_ssa":       ["orbital_dynamics", "conjunction_analysis", "space_debris", "satellite_intelligence"],
}


class SupervisorAgent:
    """
    LangGraph supervisor — runs as the first and last node in the graph.
    """

    def __init__(self, client: AsyncAnthropic):
        self.client = client

    async def classify_and_route(self, state: OrbitalState) -> OrbitalState:
        """
        Node: entry point of the graph.
        Classify intent, extract entities, decide which agents to run.
        """
        query = state["user_query"]
        logger.info(f"Supervisor: classifying query: {query[:80]}")

        try:
            response = await self.client.messages.create(
                model=MODEL,
                max_tokens=512,
                system=INTENT_CLASSIFIER_PROMPT,
                messages=[{"role": "user", "content": query}],
            )
            import json, re
            text = response.content[0].text
            # Extract JSON from response
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                classification = json.loads(match.group(0))
            else:
                classification = {
                    "intent": "general_ssa",
                    "entities": [],
                    "primary_agents": ["orbital_dynamics", "conjunction_analysis"],
                    "secondary_agents": [],
                    "confidence": 0.5,
                }
        except Exception as e:
            logger.warning(f"Supervisor classification failed: {e}; defaulting to general_ssa")
            classification = {
                "intent": "general_ssa",
                "entities": [],
                "primary_agents": ["orbital_dynamics", "conjunction_analysis"],
                "secondary_agents": [],
                "confidence": 0.3,
            }

        intent = classification.get("intent", "general_ssa")
        entities = classification.get("entities", [])

        # Look up routing table
        agents = ROUTING_TABLE.get(intent, ROUTING_TABLE["general_ssa"])

        # Merge with any LLM-suggested secondary agents
        secondary = classification.get("secondary_agents", [])
        for a in secondary:
            if a not in agents:
                agents.append(a)

        state["query_intent"] = intent
        state["query_entities"] = entities
        state["requested_agents"] = agents
        state["routing_decision"] = {
            "intent": intent,
            "agents": agents,
            "confidence": classification.get("confidence", 0.5),
            "rationale": classification.get("rationale", ""),
        }

        logger.info(f"Supervisor routing → intent={intent} agents={agents}")
        return state

    async def synthesize(self, state: OrbitalState) -> OrbitalState:
        """
        Node: final synthesis of all agent outputs.
        """
        query = state["user_query"]
        safety_flags = state.get("safety_flags", [])

        # Collect all non-empty agent outputs
        agent_outputs = {}

        if state.get("collision_risk_summary"):
            agent_outputs["conjunction_analysis"] = {
                "summary": state["collision_risk_summary"],
                "red_events": [a for a in state.get("conjunction_alerts", [])
                               if a.get("risk_level") == "red"],
                "yellow_events": [a for a in state.get("conjunction_alerts", [])
                                  if a.get("risk_level") == "yellow"],
                "maneuvers": state.get("maneuver_recommendations", []),
            }

        if state.get("orbital_propagations"):
            agent_outputs["orbital_dynamics"] = {
                "propagations": state["orbital_propagations"][:5],
                "classifications": state.get("orbit_classifications", [])[:5],
            }

        if state.get("reentry_alerts"):
            agent_outputs["space_debris"] = {
                "reentry_alerts": state["reentry_alerts"][:5],
                "decay_anomalies": state.get("orbital_decay_anomalies", [])[:5],
                "fragmentation": state.get("fragmentation_analysis", [])[:3],
            }

        if state.get("current_space_weather"):
            agent_outputs["space_weather"] = state["current_space_weather"]

        if state.get("topic_summary"):
            agent_outputs["aerospace_research"] = {
                "summary": state["topic_summary"],
                "sources": state.get("cited_sources", [])[:5],
            }

        if state.get("satellite_profiles"):
            agent_outputs["satellite_intelligence"] = {
                "profiles": state["satellite_profiles"][:5],
                "constellation": state.get("constellation_analysis"),
            }

        if state.get("mission_timeline") or state.get("delta_v_budget"):
            agent_outputs["mission_planning"] = {
                "timeline": state.get("mission_timeline"),
                "dv_budget": state.get("delta_v_budget"),
                "windows": state.get("launch_opportunities", [])[:3],
            }

        # Build synthesis prompt
        import json
        prompt = SYNTHESIS_PROMPT.format(
            agent_outputs=json.dumps(agent_outputs, default=str, indent=2)[:8000],
            safety_flags="\n".join(safety_flags) if safety_flags else "None",
            query=query,
        )

        try:
            response = await self.client.messages.create(
                model=MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            final_answer = response.content[0].text
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            final_answer = self._fallback_synthesis(state)

        # Compute aggregate confidence
        confidences = []
        for r in state.get("research_results", []):
            if isinstance(r, dict) and "confidence" in r:
                confidences.append(r["confidence"])
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.7

        state["final_answer"] = final_answer
        state["final_confidence"] = avg_confidence
        state["synthesis_complete"] = True
        state["completed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"Supervisor: synthesis complete (confidence={avg_confidence:.2f})")
        return state

    @staticmethod
    def _fallback_synthesis(state: OrbitalState) -> str:
        """Emergency fallback if Claude synthesis fails."""
        parts = ["**ORBITIQ-X Multi-Agent Response**\n"]
        if state.get("collision_risk_summary"):
            parts.append(f"\n**Conjunction Analysis**\n{state['collision_risk_summary']}")
        if state.get("topic_summary"):
            parts.append(f"\n**Research**\n{state['topic_summary']}")
        if state.get("safety_flags"):
            parts.append(f"\n**Safety Flags**\n" + "\n".join(state["safety_flags"]))
        return "\n".join(parts) or "No results available."
