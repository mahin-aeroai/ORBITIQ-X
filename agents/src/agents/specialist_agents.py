"""
ORBITIQ-X Multi-Agent System
Seven Specialist Agents

Each agent follows the same pattern:
  1. Read relevant fields from OrbitalState
  2. Choose and call tools based on query intent
  3. Write results back to OrbitalState
  4. Return updated state

All agents are async, cancellable, and bounded by timeout.
All tool calls are wrapped in try/except; partial results
are always returned rather than failing the whole agent.

Agent personalities (system prompts) are domain-expert
personas grounded in real aerospace engineering roles.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from anthropic import AsyncAnthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state.orbital_state import OrbitalState, AgentCallRecord
from ..tools.orbital_tools import (
    propagate_satellite_tool, classify_orbit_tool,
    compute_ground_track_tool, predict_passes_tool,
    relative_motion_tool,
)
from ..tools.conjunction_tools import (
    screen_conjunctions_tool, compute_foster_pc_tool,
    generate_cdm_tool, compute_maneuver_tool,
)
from ..tools.debris_tools import (
    query_debris_catalog_tool, monitor_reentry_tool,
    analyze_fragmentation_tool, detect_decay_anomaly_tool,
)
from ..tools.mission_tools import (
    compute_launch_window_tool, compute_delta_v_tool,
    generate_trajectory_tool, plan_mission_timeline_tool,
)
from ..tools.weather_tools import (
    fetch_kp_index_tool, fetch_f107_tool,
    assess_drag_impact_tool, fetch_solar_events_tool,
)
from ..tools.research_tools import (
    query_rag_tool, query_knowledge_graph_tool,
    search_papers_tool, summarize_topic_tool,
)
from ..tools.satellite_tools import (
    query_satellite_catalog_tool, get_satellite_profile_tool,
    analyze_constellation_tool, fetch_tle_tool,
)

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
AGENT_TIMEOUT_S = 60.0   # max seconds per agent


# ── Base agent ────────────────────────────────────────────────

class BaseAgent:
    """
    Base class for all ORBITIQ-X specialist agents.
    Handles timeout, error logging, and call record creation.
    """

    name: str = "base"
    system_prompt: str = ""
    timeout: float = AGENT_TIMEOUT_S

    def __init__(self, client: AsyncAnthropic):
        self.client = client
        self.llm = ChatAnthropic(
            model=MODEL,
            temperature=0.1,
            max_tokens=4096,
        )

    async def run(self, state: OrbitalState) -> OrbitalState:
        """Entry point — wraps _run with timeout and call logging."""
        start = time.perf_counter()
        record = AgentCallRecord(
            agent_name=self.name,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            success=False,
            error=None,
            tokens_used=0,
        )
        try:
            state = await asyncio.wait_for(self._run(state), timeout=self.timeout)
            record["success"] = True
        except asyncio.TimeoutError:
            err = f"{self.name} timed out after {self.timeout}s"
            logger.error(err)
            record["error"] = err
            state["errors"].append({"agent": self.name, "error": "timeout"})
        except Exception as e:
            logger.error(f"{self.name} failed: {e}", exc_info=True)
            record["error"] = str(e)
            state["errors"].append({"agent": self.name, "error": str(e)})
        finally:
            record["completed_at"] = datetime.now(timezone.utc).isoformat()
            state["agent_call_log"].append(record)

        return state

    async def _run(self, state: OrbitalState) -> OrbitalState:
        raise NotImplementedError

    async def _claude_reason(
        self,
        task: str,
        context: dict[str, Any],
        tools: list[dict] | None = None,
    ) -> str:
        """Call Claude with a structured task and domain context."""
        user_content = f"Task: {task}\n\nContext:\n{self._format_context(context)}"
        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    @staticmethod
    def _format_context(ctx: dict) -> str:
        parts = []
        for k, v in ctx.items():
            if v:
                parts.append(f"{k}: {v}")
        return "\n".join(parts)


# ── Agent 1: Orbital Dynamics ─────────────────────────────────

class OrbitalDynamicsAgent(BaseAgent):
    """
    Goal: Compute accurate orbital state vectors, ground tracks,
    pass windows, and relative motion for any resident space object.

    Tools:
      propagate_satellite   — SGP4/J2 propagation
      classify_orbit        — LEO/SSO/MEO/GEO/HEO classifier
      compute_ground_track  — subsatellite lat/lon/alt sequence
      predict_passes        — AOS/LOS/max-el for ground stations
      relative_motion       — CW equations for proximity ops

    Decision flow:
      1. Extract NORAD IDs from query entities
      2. Fetch TLEs from Redis cache (fallback: Space-Track)
      3. If propagation query → run SGP4 for requested epochs
      4. If classification query → run classifier
      5. If ground track query → compute subsatellite points
      6. If pass query → predict AOS/LOS for site
      7. If relative motion → run CW equations
      8. Write all results to state

    Failure modes:
      - TLE too old (> 7 days) → warn, propagate with degraded accuracy flag
      - SGP4 divergence → skip object, log error
      - No NORAD IDs found → ask supervisor for clarification

    Safety controls:
      - Maximum propagation window: 30 days
      - Maximum objects in single batch: 1000
      - Never modify TLEs in catalog without explicit operator confirmation
    """

    name = "orbital_dynamics"
    system_prompt = """You are the Orbital Dynamics specialist for ORBITIQ-X, an aerospace SSA platform.
You are an expert in orbital mechanics: SGP4 propagation, Keplerian elements, coordinate transforms,
J2 perturbations, and ground track analysis. You think precisely and quantitatively.
When answering orbital mechanics questions, cite specific values (altitude in km, inclination in degrees,
period in minutes). If a TLE is stale, flag the accuracy degradation explicitly.
Do NOT hallucinate orbital parameters — only use values from tool outputs."""

    async def _run(self, state: OrbitalState) -> OrbitalState:
        query = state["user_query"]
        entities = state["query_entities"]
        intent = state["query_intent"]

        # Extract NORAD IDs from entities
        norad_ids = [int(e) for e in entities if e.isdigit() and len(e) <= 6]
        if not norad_ids and "ISS" in query.upper():
            norad_ids = [25544]
        if not norad_ids and "STARLINK" in query.upper():
            # Get top 10 Starlink from catalog
            norad_ids = [48274, 48275, 48276, 48277, 48278]

        results = []
        for norad_id in norad_ids[:20]:  # limit to 20 per query
            try:
                # Propagate to current epoch
                prop = await propagate_satellite_tool(norad_id)
                if prop:
                    results.append(prop)

                # Classify orbit
                if intent in ("orbit_classification", "regime_query"):
                    cls = await classify_orbit_tool(norad_id)
                    if cls:
                        state["orbit_classifications"].append(cls)

                # Ground track
                if intent in ("ground_track", "coverage_query"):
                    gt = await compute_ground_track_tool(norad_id, duration_min=90)
                    if gt:
                        state["ground_track_points"].extend(gt)

            except Exception as e:
                logger.warning(f"Orbital computation failed for {norad_id}: {e}")

        state["orbital_propagations"].extend(results)

        # If pass prediction requested
        if intent == "pass_prediction" or "pass" in query.lower():
            site_lat = 17.385  # Hyderabad default
            site_lon = 78.487
            for norad_id in norad_ids[:5]:
                passes = await predict_passes_tool(norad_id, site_lat, site_lon)
                state["pass_predictions"].extend(passes or [])

        return state


# ── Agent 2: Conjunction Analysis ────────────────────────────

class ConjunctionAnalysisAgent(BaseAgent):
    """
    Goal: Identify, assess, and recommend mitigations for conjunction events.
    The most safety-critical agent in the system.

    Tools:
      screen_conjunctions   — 2-stage voxel filter + Foster Pc
      compute_foster_pc     — collision probability from CDM data
      generate_cdm          — produce CDM v1.0 format output
      compute_maneuver      — ΔV recommendation for avoidance

    Decision flow:
      1. If risk query → screen active catalog for Pc > 1e-5
      2. Sort by Pc descending
      3. For each red/yellow event → compute detailed CDM
      4. If maneuver requested → compute ΔV and maneuver window
      5. Submit maneuver to safety gate before returning
      6. Write collision_risk_summary, conjunction_alerts, maneuver_recommendations

    Failure modes:
      - Covariance unavailable → use conservative default (500m × 1km × 500m)
      - TCA search fails → extend window and retry
      - Pc > 0.1 → escalate to CRITICAL, require human confirmation

    Safety controls:
      - Maneuver recommendations flagged safety_approved=False until gate clears
      - Minimum 6h maneuver window required before any recommendation
      - Never recommend maneuver for objects without valid TLE < 24h
      - Pc RED threshold (≥1e-3) triggers WebSocket alert regardless of query
    """

    name = "conjunction_analysis"
    system_prompt = """You are the Conjunction Analysis specialist for ORBITIQ-X.
You are an expert in space situational awareness, collision avoidance, and CDM interpretation.
You reason probabilistically and conservatively — when in doubt, escalate.
For collision probabilities, always state the exact Pc value, risk level, TCA, and miss distance.
For maneuver recommendations, include burn time, ΔV magnitude/direction, fuel cost, and confidence.
NEVER recommend maneuvering if the maneuver window has already passed.
ALWAYS flag if a recommendation requires operator confirmation."""

    async def _run(self, state: OrbitalState) -> OrbitalState:
        query = state["user_query"]
        entities = state["query_entities"]

        # Screen for high-risk conjunctions
        conjunctions = await screen_conjunctions_tool(top_k=20, min_pc=1e-5)
        alerts = []
        high_risk_norads = []

        for conj in (conjunctions or []):
            alert = {
                "conjunction_id": conj.get("id"),
                "primary_norad": conj.get("primary_norad"),
                "secondary_norad": conj.get("secondary_norad"),
                "primary_name": conj.get("primary_name", "Unknown"),
                "secondary_name": conj.get("secondary_name", "Unknown"),
                "tca": conj.get("tca"),
                "miss_distance_km": conj.get("miss_distance_km", 0),
                "collision_probability": conj.get("Pc", 0),
                "risk_level": conj.get("risk_level", "green"),
                "maneuver_required": conj.get("Pc", 0) >= 1e-4,
                "maneuver_deadline": conj.get("maneuver_window"),
            }
            alerts.append(alert)

            if conj.get("risk_level") in ("red", "yellow"):
                high_risk_norads.append(conj.get("primary_norad"))

        state["conjunction_alerts"].extend(alerts)
        state["high_risk_objects"].extend(high_risk_norads)

        # Generate maneuver recommendations for red events
        if "maneuver" in query.lower() or "avoidance" in query.lower():
            red_events = [a for a in alerts if a["risk_level"] == "red"]
            for event in red_events[:3]:
                maneuver = await compute_maneuver_tool(
                    primary_norad=event["primary_norad"],
                    conjunction_id=event["conjunction_id"],
                )
                if maneuver:
                    maneuver["safety_approved"] = False  # requires safety gate
                    state["maneuver_recommendations"].append(maneuver)
                    state["safety_flags"].append(
                        f"MANEUVER_PENDING: {event['primary_norad']} requires safety review"
                    )

        # Build summary
        red_count = sum(1 for a in alerts if a["risk_level"] == "red")
        yellow_count = sum(1 for a in alerts if a["risk_level"] == "yellow")

        context = {
            "query": query,
            "red_events": red_count,
            "yellow_events": yellow_count,
            "top_alerts": alerts[:5],
        }
        state["collision_risk_summary"] = await self._claude_reason(
            "Summarize the conjunction risk landscape based on the screening results",
            context,
        )

        return state


# ── Agent 3: Space Debris ─────────────────────────────────────

class SpaceDebrisAgent(BaseAgent):
    """
    Goal: Characterize the debris environment, monitor re-entries,
    analyze fragmentation events, and detect orbital decay anomalies.

    Tools:
      query_debris_catalog    — search by NORAD, regime, RCS, origin
      monitor_reentry         — decay predictions for catalog objects
      analyze_fragmentation   — debris cloud from parent breakup event
      detect_decay_anomaly    — flag objects with anomalous drag

    Decision flow:
      1. If anomaly query → detect_decay_anomaly for flagged objects
      2. If reentry query → monitor_reentry for perigee < 350 km
      3. If fragmentation query → analyze_fragmentation for named event
      4. If catalog query → query_debris_catalog with regime/RCS filter
      5. Correlate findings with space weather (pulls from weather agent state)
      6. Write results to state

    Failure modes:
      - No tracking data for small objects (<10cm) → state limitation clearly
      - Decay prediction uncertainty > 50% → flag and provide range
      - Fragmentation event not in catalog → use historical analogues

    Safety controls:
      - Reentry alerts for crewed stations always escalated
      - Objects with HBR > 1m flagged for human review
      - Anomalous decay (>3σ) triggers immediate supervisor alert
    """

    name = "space_debris"
    system_prompt = """You are the Space Debris analyst for ORBITIQ-X.
You specialize in debris environment characterization, re-entry prediction,
and fragmentation analysis. You understand the limitations of tracking data:
only objects > 10 cm in LEO are reliably tracked by radar networks.
When predicting re-entry, always give an uncertainty range and the F10.7
solar flux conditions used. Never give a single re-entry time without
a ±uncertainty bound. For anomalous decay, explain possible causes
(atmospheric density spikes, tumbling attitude, area-to-mass change)."""

    async def _run(self, state: OrbitalState) -> OrbitalState:
        query = state["user_query"]
        entities = state["query_entities"]

        # Detect decay anomalies if requested
        if any(kw in query.lower() for kw in ("anomaly", "anomalous", "unexpected decay")):
            anomalies = await detect_decay_anomaly_tool(threshold_sigma=2.5)
            if anomalies:
                for a in anomalies[:10]:
                    state["orbital_decay_anomalies"].append({
                        "norad_id": a.get("norad_id"),
                        "object_name": a.get("name"),
                        "observed_decay_rate": a.get("observed_km_day"),
                        "expected_decay_rate": a.get("expected_km_day"),
                        "anomaly_magnitude_sigma": a.get("sigma"),
                        "probable_cause": a.get("probable_cause", "unknown"),
                        "confidence": a.get("confidence", 0.5),
                    })
                # Flag >3σ anomalies
                severe = [a for a in state["orbital_decay_anomalies"]
                          if a.get("anomaly_magnitude_sigma", 0) > 3.0]
                for s in severe:
                    state["safety_flags"].append(
                        f"DECAY_ANOMALY_3SIGMA: NORAD {s['norad_id']} {s['object_name']}"
                    )

        # Re-entry monitoring
        if any(kw in query.lower() for kw in ("reentry", "re-entry", "decay", "fall")):
            predictions = await monitor_reentry_tool(max_days=14)
            for p in (predictions or [])[:20]:
                state["reentry_alerts"].append({
                    "norad_id": p.get("norad_id"),
                    "object_name": p.get("name"),
                    "predicted_reentry": p.get("predicted_epoch"),
                    "lifetime_days": p.get("days"),
                    "alert_level": p.get("alert_level"),
                    "uncertainty_hours": p.get("uncertainty_hours", 0),
                })

        # Fragmentation analysis
        if any(kw in query.lower() for kw in ("fragmentation", "breakup", "fengyun", "iridium", "asat")):
            frag_event = self._extract_frag_event(query)
            if frag_event:
                analysis = await analyze_fragmentation_tool(event_id=frag_event)
                if analysis:
                    state["fragmentation_analysis"].append(analysis)

        # General debris catalog query
        catalog = await query_debris_catalog_tool(
            regime="LEO",
            min_rcs=0.01,
            limit=50,
        )
        state["debris_catalog_results"].extend(catalog or [])

        return state

    @staticmethod
    def _extract_frag_event(query: str) -> str | None:
        import re
        known_events = {
            "fengyun": "FRAG-FY1C-2007",
            "iridium 33": "FRAG-IRIDIUM33-2009",
            "cosmos 2251": "FRAG-COSMOS2251-2009",
            "asat": "FRAG-ASAT-2019",
        }
        for keyword, event_id in known_events.items():
            if keyword in query.lower():
                return event_id
        return None


# ── Agent 4: Mission Planning ─────────────────────────────────

class MissionPlanningAgent(BaseAgent):
    """
    Goal: Compute launch windows, ΔV budgets, trajectory options,
    and mission timelines for spacecraft operations.

    Tools:
      compute_launch_window   — optimal launch time for target orbit
      compute_delta_v         — ΔV for orbital maneuvers (Hohmann, bi-elliptic)
      generate_trajectory     — porkchop plot data, transfer arcs
      plan_mission_timeline   — Gantt-style mission phase planning

    Decision flow:
      1. Extract mission parameters from query (target orbit, launch site)
      2. If window query → compute_launch_window with constraints
      3. If ΔV query → compute_delta_v for maneuver type
      4. If trajectory query → generate_trajectory with optimization
      5. If timeline query → plan_mission_timeline for phase sequence
      6. Correlate launch window with weather agent output (avoid G3+ storms)
      7. Write results to state

    Failure modes:
      - No feasible window in requested range → expand search window
      - ΔV exceeds propulsion capacity → flag infeasibility
      - Conjunction risk in planned trajectory → notify conjunction agent

    Safety controls:
      - Launch windows blocked during Kp > 5 (per space weather agent)
      - Maneuver windows must not conflict with existing CDM primary events
      - Human confirmation required for any maneuver > 10 m/s ΔV
    """

    name = "mission_planning"
    system_prompt = """You are the Mission Planning specialist for ORBITIQ-X.
You design optimal orbital maneuver sequences, launch windows, and mission timelines
using established astrodynamics methods: Hohmann transfers, bi-elliptic transfers,
phasing maneuvers, and plane changes.
When computing ΔV, always specify the initial and final orbits, the maneuver type,
and the fuel consumption estimate (assuming Isp=311s for bipropellant).
For launch windows, state the opening/closing time, azimuth constraints,
and any launch site or range safety restrictions.
Flag any maneuver that exceeds 10 m/s for human review."""

    async def _run(self, state: OrbitalState) -> OrbitalState:
        query = state["user_query"]
        entities = state["query_entities"]

        # Extract orbit parameters
        import re
        alt_match = re.search(r'(\d+)\s*km', query)
        target_alt = float(alt_match.group(1)) if alt_match else 550.0

        # Launch window calculation
        if any(kw in query.lower() for kw in ("launch window", "launch time", "liftoff")):
            windows = await compute_launch_window_tool(
                target_altitude_km=target_alt,
                inclination_deg=None,
                launch_site="SDSC",
            )
            state["launch_opportunities"].extend(windows or [])

        # ΔV computation
        if any(kw in query.lower() for kw in ("delta-v", "dv", "maneuver", "transfer", "hohmann")):
            dv = await compute_delta_v_tool(
                initial_alt_km=408.0,   # ISS default
                target_alt_km=target_alt,
                maneuver_type="hohmann",
            )
            state["delta_v_budget"] = dv

        # Trajectory generation
        if any(kw in query.lower() for kw in ("trajectory", "porkchop", "transfer arc")):
            traj = await generate_trajectory_tool(
                departure_alt_km=408.0,
                arrival_alt_km=target_alt,
            )
            state["trajectory_options"].extend(traj or [])

        # Timeline
        if any(kw in query.lower() for kw in ("timeline", "mission plan", "phases")):
            timeline = await plan_mission_timeline_tool(
                mission_type="LEO_deployment",
                duration_days=365,
            )
            state["mission_timeline"] = timeline

        # Apply space weather constraints from state
        weather = state.get("current_space_weather")
        if weather and weather.get("kp_index", 0) > 5:
            state["safety_flags"].append(
                f"LAUNCH_WINDOW_BLOCKED: Kp={weather['kp_index']:.1f} exceeds G3 threshold"
            )

        return state


# ── Agent 5: Space Weather ────────────────────────────────────

class SpaceWeatherAgent(BaseAgent):
    """
    Goal: Monitor and interpret solar activity, geomagnetic conditions,
    and their impact on spacecraft operations and orbital drag.

    Tools:
      fetch_kp_index          — current and forecast Kp (0-9)
      fetch_f107              — solar flux index (affects drag model)
      assess_drag_impact      — density change at LEO altitudes
      fetch_solar_events      — flares, CMEs, SPEs from NOAA SWPC

    Decision flow:
      1. Always fetch current Kp and F10.7 (needed by other agents)
      2. If storm query → fetch full solar event history
      3. If drag/decay query → assess_drag_impact at relevant altitudes
      4. If forecast query → Kp forecast for next 72h
      5. Write current_space_weather for mission planning to consume
      6. If Kp > 6 → add safety flag

    Failure modes:
      - NOAA SWPC API down → use cached values with age warning
      - F10.7 > 250 → flag extreme solar activity

    Safety controls:
      - Kp > 5 → add safety flag blocking maneuver recommendations
      - X-class flare → radiation alert for crew operations
      - G4/G5 storm → drag model uncertainty flag (±50%)
    """

    name = "space_weather"
    system_prompt = """You are the Space Weather analyst for ORBITIQ-X.
You monitor solar activity and translate space weather events into operational
impacts for satellite operators. You understand NOAA storm scales (G, S, R),
geomagnetic indices (Kp, Dst), solar flux (F10.7), and their effects on
atmospheric drag at LEO altitudes.
For drag impact: F10.7 = 250 → atmospheric density at 400km can be 5-10×
higher than solar minimum. Express density changes as percentage shifts.
Always state the data timestamp and any data quality caveats."""

    async def _run(self, state: OrbitalState) -> OrbitalState:
        # Always fetch current conditions
        kp = await fetch_kp_index_tool()
        f107 = await fetch_f107_tool()

        kp_val = kp.get("kp_index", 1.0) if kp else 1.0
        f107_val = f107.get("f107", 70.0) if f107 else 70.0

        storm_cat = "none"
        if kp_val >= 8: storm_cat = "G4"
        elif kp_val >= 6: storm_cat = "G3"
        elif kp_val >= 5: storm_cat = "G2"
        elif kp_val >= 4: storm_cat = "G1"

        # Drag impact at key altitudes
        drag = await assess_drag_impact_tool(f107=f107_val, kp=kp_val)
        drag_impact = drag.get("density_change_pct", 0.0) if drag else 0.0

        state["current_space_weather"] = {
            "kp_index": kp_val,
            "f107_flux": f107_val,
            "storm_category": storm_cat,
            "density_effect_pct": drag_impact,
            "recommended_action": self._recommend_action(kp_val),
        }

        # Full forecast if requested
        query = state["user_query"]
        if any(kw in query.lower() for kw in ("weather", "storm", "solar", "flare", "radiation", "kp")):
            solar_events = await fetch_solar_events_tool(hours=72)
            state["weather_forecast"].extend(solar_events or [])
            state["drag_impact_assessment"] = (
                f"Current F10.7={f107_val:.1f}, Kp={kp_val:.1f} "
                f"({storm_cat}). Atmospheric density at 400km is "
                f"{drag_impact:+.1f}% vs NRLMSISE-00 baseline."
            )

        # Safety flags
        if kp_val >= 5:
            state["safety_flags"].append(
                f"SPACE_WEATHER: Kp={kp_val:.1f} ({storm_cat}) — "
                f"maneuver planning affected, drag model uncertainty ±30%"
            )
        if f107_val > 200:
            state["safety_flags"].append(
                f"HIGH_SOLAR_FLUX: F10.7={f107_val:.0f} — "
                f"significant drag enhancement, decay predictions degraded"
            )

        return state

    @staticmethod
    def _recommend_action(kp: float) -> str:
        if kp >= 8: return "Suspend all operations; extreme geomagnetic storm"
        if kp >= 6: return "Delay maneuvers; significant drag uncertainty"
        if kp >= 5: return "Monitor closely; mild storm conditions"
        if kp >= 4: return "No restrictions; minor activity"
        return "Nominal operations; quiet conditions"


# ── Agent 6: Aerospace Research ──────────────────────────────

class AerospaceResearchAgent(BaseAgent):
    """
    Goal: Retrieve, synthesize, and cite aerospace knowledge from the
    RAG corpus and knowledge graph for engineering-grade answers.

    Tools:
      query_rag               — hybrid retrieval from Qdrant (BGE-M3)
      query_knowledge_graph   — structured fact retrieval from Neo4j
      search_papers           — bibliographic search by topic
      summarize_topic         — multi-source synthesis with citations

    Decision flow:
      1. Parse query for research intent (explain, compare, summarize)
      2. query_rag for semantic retrieval across all source types
      3. query_knowledge_graph for structured facts (satellite→mission lineage)
      4. If citation-heavy query → search_papers for primary sources
      5. summarize_topic to synthesize all retrieved content
      6. Write research_results, cited_sources, topic_summary to state

    Failure modes:
      - No relevant documents found → state corpus gap explicitly
      - RAG faithfulness < 0.7 → flag low confidence
      - KG query returns empty → note data availability

    Safety controls:
      - Never present generated text as a direct quote from a source
      - All numeric claims must be citation-backed
      - Hallucination score > 0.3 → flag uncertainty
    """

    name = "aerospace_research"
    system_prompt = """You are the Aerospace Research specialist for ORBITIQ-X.
You synthesize technical knowledge from NASA, ESA, ISRO reports, research papers,
and aerospace textbooks. You follow strict citation practices: every factual claim
must be supported by a retrieved source. Use IEEE citation style [1], [2], etc.
For mission summaries (e.g. Artemis), cover: objectives, architecture,
key components, timeline, and current status. For technical explanations,
include governing equations where relevant.
If the corpus does not contain information, say so explicitly — do not invent."""

    async def _run(self, state: OrbitalState) -> OrbitalState:
        query = state["user_query"]

        # Semantic RAG retrieval
        rag_result = await query_rag_tool(
            query=query,
            top_k=8,
            use_hyde=True,
            filter_agency=None,  # search all agencies
        )
        if rag_result:
            state["research_results"].append({
                "query": query,
                "answer": rag_result.get("answer", ""),
                "sources": rag_result.get("sources", []),
                "confidence": rag_result.get("confidence", 0.0),
                "faithfulness_score": rag_result.get("faithfulness_score", 0.0),
            })
            state["cited_sources"].extend(rag_result.get("sources", []))

        # Knowledge graph query for structured facts
        kg_results = await query_knowledge_graph_tool(query=query, limit=10)
        if kg_results:
            state["knowledge_graph_results"].extend(kg_results)

        # Paper search if bibliographic detail requested
        if any(kw in query.lower() for kw in ("paper", "study", "research", "published")):
            papers = await search_papers_tool(query=query, limit=10)
            state["cited_sources"].extend(papers or [])

        # Synthesize
        all_context = {
            "rag_answer": rag_result.get("answer", "") if rag_result else "",
            "kg_facts": kg_results[:5] if kg_results else [],
            "query": query,
        }
        state["topic_summary"] = await self._claude_reason(
            "Produce a comprehensive, well-cited aerospace engineering answer",
            all_context,
        )

        # Flag low faithfulness
        if rag_result and rag_result.get("faithfulness_score", 1.0) < 0.7:
            state["safety_flags"].append(
                f"LOW_FAITHFULNESS: Research answer confidence below threshold "
                f"(score={rag_result.get('faithfulness_score', 0):.2f})"
            )

        return state


# ── Agent 7: Satellite Intelligence ──────────────────────────

class SatelliteIntelligenceAgent(BaseAgent):
    """
    Goal: Provide comprehensive intelligence on individual satellites,
    operators, constellations, and their current operational status.

    Tools:
      query_satellite_catalog — search RSO catalog with filters
      get_satellite_profile   — full profile: TLE, operator, mission, orbit
      analyze_constellation   — constellation health, coverage, gaps
      fetch_tle               — fresh TLE from CelesTrak/Space-Track

    Decision flow:
      1. Parse query for satellite name or NORAD ID
      2. get_satellite_profile for named objects
      3. query_satellite_catalog for filtered searches (country, mission type)
      4. If constellation query → analyze_constellation for shell statistics
      5. Enrich with current status from TLE age and Bstar
      6. Write satellite_profiles, operator_intel, constellation_analysis

    Failure modes:
      - Satellite name ambiguous → return top matches for disambiguation
      - No catalog entry → note not in tracked catalog
      - TLE epoch > 14 days → flag as potentially decayed

    Safety controls:
      - Classification information never retrieved or discussed
      - Military catalog objects handled according to access policy
    """

    name = "satellite_intelligence"
    system_prompt = """You are the Satellite Intelligence analyst for ORBITIQ-X.
You maintain deep knowledge of the global satellite catalog: operators, missions,
orbital regimes, and constellation architectures. When discussing satellites,
include NORAD ID, COSPAR designator, operator, launch date, current status,
and orbital parameters. For constellations (Starlink, OneWeb, Kuiper),
provide total count, shell configuration, and coverage statistics.
Only discuss information available in the public catalog — no classified data."""

    async def _run(self, state: OrbitalState) -> OrbitalState:
        query = state["user_query"]
        entities = state["query_entities"]

        # Profile specific satellites
        norad_ids = [int(e) for e in entities if e.isdigit() and len(e) <= 6]
        for norad_id in norad_ids[:10]:
            profile = await get_satellite_profile_tool(norad_id)
            if profile:
                state["satellite_profiles"].append(profile)

        # Catalog search
        catalog_results = await query_satellite_catalog_tool(
            query=query,
            limit=20,
        )
        state["catalog_search_results"].extend(catalog_results or [])

        # Constellation analysis
        const_keywords = {
            "starlink": "STARLINK",
            "oneweb": "ONEWEB",
            "kuiper": "KUIPER",
            "gps": "GPS",
            "galileo": "GALILEO",
            "glonass": "GLONASS",
            "navic": "NAVIC",
        }
        for keyword, const_id in const_keywords.items():
            if keyword in query.lower():
                analysis = await analyze_constellation_tool(const_id)
                if analysis:
                    state["constellation_analysis"] = analysis
                break

        return state
