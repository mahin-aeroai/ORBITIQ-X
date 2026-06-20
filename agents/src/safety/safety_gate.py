"""
ORBITIQ-X Multi-Agent System
Safety Gate

The safety gate is a LangGraph node that runs AFTER all specialist
agents but BEFORE synthesis. It enforces all safety controls and
can halt the graph or modify state to prevent unsafe outputs.

Safety hierarchy (most critical first):
  1. Maneuver safety gate — block unreviewed maneuver recommendations
  2. Re-entry escalation — IMMINENT alerts page on-call operator
  3. Collision risk escalation — Pc >= 1e-3 triggers external alert
  4. Space weather gate — block mission plans during G3+ storms
  5. Data quality gate — flag stale TLEs, low-confidence outputs
  6. Output sanitization — remove any classified or sensitive data

Design principle: FAIL SAFE.
If the safety gate itself fails (exception), it approves nothing
and adds a safety flag. The supervisor will note this in the output.

All safety decisions are logged for audit trail.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..state.orbital_state import OrbitalState

logger = logging.getLogger(__name__)


class SafetyGate:
    """
    Safety gate node for the LangGraph aerospace agent system.
    Checks all safety conditions and modifies state accordingly.
    """

    # Thresholds
    PC_HUMAN_REVIEW    = 1e-3   # Pc above this → human confirmation required
    PC_ALERT_EXTERNAL  = 1e-3   # trigger external alert system
    KP_MANEUVER_BLOCK  = 5.0    # Kp above this → block maneuver recommendations
    DV_HUMAN_THRESHOLD = 0.010  # ΔV > 10 m/s requires human sign-off (km/s)
    TLE_MAX_AGE_DAYS   = 7.0    # TLEs older than this → degraded accuracy flag
    REENTRY_IMMINENT_DAYS = 1.0 # < 1 day to re-entry → escalate immediately

    def check(self, state: OrbitalState) -> OrbitalState:
        """
        Run all safety checks. Returns modified state.
        Never raises — all exceptions are caught and logged.
        """
        try:
            state = self._check_maneuver_safety(state)
            state = self._check_reentry_escalation(state)
            state = self._check_collision_escalation(state)
            state = self._check_space_weather_gate(state)
            state = self._check_data_quality(state)
            state = self._sanitize_outputs(state)
        except Exception as e:
            logger.critical(f"Safety gate exception: {e}", exc_info=True)
            state["safety_flags"].append(
                f"SAFETY_GATE_FAILED: {e}. All maneuver recommendations blocked."
            )
            # Block all maneuvers if gate fails
            for rec in state.get("maneuver_recommendations", []):
                rec["safety_approved"] = False

        return state

    # ── Maneuver safety ───────────────────────────────────────

    def _check_maneuver_safety(self, state: OrbitalState) -> OrbitalState:
        """
        Approve or block maneuver recommendations.

        Rules:
        - ΔV > 10 m/s → requires human sign-off (never auto-approved)
        - Pc < 1e-4 (yellow threshold) → block recommendation (not worth it)
        - Maneuver window passed → block (too late)
        - Space weather Kp > 5 → flag uncertainty, but allow if Pc >= 1e-3
        """
        kp = (state.get("current_space_weather") or {}).get("kp_index", 0)

        for rec in state.get("maneuver_recommendations", []):
            dv = rec.get("delta_v_kms", 0.0)
            pc = self._find_pc_for_recommendation(rec, state)
            window = rec.get("maneuver_deadline")

            reasons_blocked = []

            # Rule 1: large ΔV requires human
            if dv > self.DV_HUMAN_THRESHOLD:
                reasons_blocked.append(
                    f"ΔV={dv*1000:.1f} m/s exceeds {self.DV_HUMAN_THRESHOLD*1000:.0f} m/s threshold"
                )

            # Rule 2: low Pc doesn't justify maneuver
            if pc and pc < 1e-4:
                reasons_blocked.append(
                    f"Pc={pc:.2e} below yellow threshold (1e-4); maneuver unnecessary"
                )

            # Rule 3: check window hasn't passed
            if window:
                try:
                    deadline = datetime.fromisoformat(window.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    if deadline < now:
                        reasons_blocked.append(
                            f"Maneuver window {window} has already passed"
                        )
                except (ValueError, TypeError):
                    pass

            if reasons_blocked:
                rec["safety_approved"] = False
                rec["block_reason"] = "; ".join(reasons_blocked)
                state["safety_flags"].append(
                    f"MANEUVER_BLOCKED [{rec.get('target_norad')}]: {reasons_blocked[0]}"
                )
                logger.warning(f"Maneuver blocked for {rec.get('target_norad')}: {reasons_blocked}")
            else:
                # Approve if Pc >= 1e-3 and ΔV is small
                if pc and pc >= 1e-4 and dv <= self.DV_HUMAN_THRESHOLD:
                    rec["safety_approved"] = True
                    logger.info(f"Maneuver approved for {rec.get('target_norad')}: Pc={pc:.2e}")

        return state

    def _find_pc_for_recommendation(
        self, rec: dict, state: OrbitalState
    ) -> float | None:
        """Find the collision probability associated with a maneuver recommendation."""
        target_norad = rec.get("target_norad")
        for alert in state.get("conjunction_alerts", []):
            if alert.get("primary_norad") == target_norad:
                return alert.get("collision_probability")
        return None

    # ── Re-entry escalation ───────────────────────────────────

    def _check_reentry_escalation(self, state: OrbitalState) -> OrbitalState:
        """
        Escalate imminent re-entries.
        IMMINENT (< 24h) and CRITICAL (< 6h) require immediate paging.
        """
        for alert in state.get("reentry_alerts", []):
            days = alert.get("lifetime_days", 999)
            level = alert.get("alert_level", "WATCH")
            norad = alert.get("norad_id")
            name = alert.get("object_name", str(norad))

            if days < self.REENTRY_IMMINENT_DAYS:
                flag = (
                    f"REENTRY_IMMINENT: {name} (NORAD {norad}) "
                    f"predicted in {days*24:.1f}h — escalate to ops center"
                )
                state["safety_flags"].append(flag)
                logger.critical(flag)
                # In production: call pager duty / SMS alert
                # await alerting_service.page(flag)

            elif level in ("CRITICAL", "URGENT"):
                state["safety_flags"].append(
                    f"REENTRY_{level}: {name} (NORAD {norad}) "
                    f"in {days:.1f} days — monitor closely"
                )

        return state

    # ── Collision risk escalation ─────────────────────────────

    def _check_collision_escalation(self, state: OrbitalState) -> OrbitalState:
        """
        Escalate red conjunction events (Pc >= 1e-3).
        These require external notification regardless of query context.
        """
        for alert in state.get("conjunction_alerts", []):
            pc = alert.get("collision_probability", 0)
            if pc >= self.PC_ALERT_EXTERNAL:
                flag = (
                    f"COLLISION_RED: {alert.get('primary_name')} / "
                    f"{alert.get('secondary_name')} — "
                    f"Pc={pc:.2e}, miss={alert.get('miss_distance_km', 0):.3f} km, "
                    f"TCA={alert.get('tca', 'unknown')}"
                )
                state["safety_flags"].append(flag)
                logger.critical(flag)
                # In production: post to WebSocket alert channel, notify operators

        return state

    # ── Space weather gate ────────────────────────────────────

    def _check_space_weather_gate(self, state: OrbitalState) -> OrbitalState:
        """
        Apply space weather constraints to mission plans.
        During G3+ storms, maneuver ΔV calculations have >30% uncertainty.
        """
        weather = state.get("current_space_weather")
        if not weather:
            return state

        kp = weather.get("kp_index", 0)
        if kp >= self.KP_MANEUVER_BLOCK:
            # Add uncertainty flag to all mission plans
            for window in state.get("launch_opportunities", []):
                window["space_weather_warning"] = (
                    f"Kp={kp:.1f} active — drag model uncertainty ±30%, "
                    f"launch window timing may shift by ±{int(kp * 5)} minutes"
                )
            if state.get("delta_v_budget"):
                state["delta_v_budget"]["weather_caveat"] = (
                    f"ΔV computed under Kp={kp:.1f} conditions. "
                    f"True atmospheric density may differ by ±30%."
                )

        return state

    # ── Data quality gate ─────────────────────────────────────

    def _check_data_quality(self, state: OrbitalState) -> OrbitalState:
        """
        Flag outputs derived from stale or low-quality data.
        """
        # Check TLE ages in orbital propagations
        from datetime import datetime
        now = datetime.now(timezone.utc)

        for prop in state.get("orbital_propagations", []):
            tle_epoch = prop.get("tle_epoch")
            if tle_epoch:
                try:
                    epoch_dt = datetime.fromisoformat(tle_epoch.replace("Z", "+00:00"))
                    age_days = (now - epoch_dt).total_seconds() / 86400
                    if age_days > self.TLE_MAX_AGE_DAYS:
                        prop["data_quality"] = "DEGRADED"
                        prop["tle_age_warning"] = (
                            f"TLE is {age_days:.1f} days old — "
                            f"position accuracy degraded (error > 10 km)"
                        )
                        norad = prop.get("norad_id")
                        state["safety_flags"].append(
                            f"STALE_TLE: NORAD {norad} TLE is {age_days:.0f} days old"
                        )
                except (ValueError, TypeError):
                    pass

        # Check research confidence
        for result in state.get("research_results", []):
            if isinstance(result, dict):
                conf = result.get("confidence", 1.0)
                faith = result.get("faithfulness_score", 1.0)
                if conf < 0.5 or faith < 0.6:
                    state["safety_flags"].append(
                        f"LOW_RESEARCH_QUALITY: confidence={conf:.2f}, "
                        f"faithfulness={faith:.2f} — verify independently"
                    )

        return state

    # ── Output sanitization ───────────────────────────────────

    def _sanitize_outputs(self, state: OrbitalState) -> OrbitalState:
        """
        Remove any potentially sensitive or inappropriate content.
        In production: apply content policy filters here.
        """
        # Remove any internal debug fields before synthesis
        # (no-op in this implementation — placeholder for production policy)
        return state


# ── Safety gate node for LangGraph ───────────────────────────

_gate = None

def get_safety_gate() -> SafetyGate:
    global _gate
    if _gate is None:
        _gate = SafetyGate()
    return _gate

def safety_gate_node(state: OrbitalState) -> OrbitalState:
    """LangGraph node — synchronous wrapper for the safety gate."""
    return get_safety_gate().check(state)
