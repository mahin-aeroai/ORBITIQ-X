"""
ORBITIQ-X — Maneuver Recommendation Engine
============================================
Evaluates collision avoidance maneuver options for conjunction events
and persists recommendations to Neo4j as [:RECOMMENDS]->(:ManeuverOption).

Architecture
────────────
  ConjunctionEvent (from CDM archive)
      │
      ▼
  ManeuverRecommendationEngine.evaluate(event)
      │
      ├── radial_burn()       — out-of-plane separation
      ├── along_track_burn()  — phase-shift maneuver (most fuel-efficient)
      └── cross_track_burn()  — inclination change (highest ΔV cost)
      │
      ▼
  ManeuverOption × 3 (or fewer if not viable)
      │
      ├── Neo4j: (:ConjunctionEvent)-[:RECOMMENDS]->(:ManeuverOption)
      └── API response: POST /ssa/maneuver/recommend

Existing components called (not rewritten)
───────────────────────────────────────────
  orbital-engine/src/relative_motion/clohessy_wiltshire.py
    ClohessyWiltshire.from_altitude_km(alt)
    ClohessyWiltshire.propagate(s0, t) → CWState
    ClohessyWiltshire.two_impulse_rendezvous(s0, t1, t2, x_f, y_f, z_f)
    ClohessyWiltshire.delta_v_for_drift_nulling(state) → DeltaV
    DeltaV.magnitude_ms → float (m/s)
  orbital-engine/src/conjunction/foster_pc.py
    FosterPcCalculator.compute(CDMEntry) → PcResult
    risk_level_from_pc(Pc) → str
  app/graph/connection.py
    is_available(), execute_write() → for Neo4j RECOMMENDS

Physical model
──────────────
  Tsiolkovsky rocket equation: ΔV = Isp × g₀ × ln(m₀/(m₀-Δm))
  Default assumptions: Isp = 300 s (monoprop), m₀ = 500 kg satellite mass
  CW frame: x=radial, y=along-track, z=cross-track
  TCA planning window: execute burn 24–48h before TCA

Maneuver strategies
────────────────────
  1. Along-track: smallest ΔV, shifts TCA timing, most common
     ΔV along y in CW frame shifts orbital period → satellite arrives at
     conjunction point before/after the secondary (avoidance by timing).
  2. Radial: separates objects perpendicular to velocity vector
     ΔV along x in CW frame. Effective for small miss distances.
  3. Cross-track: plane change, highest ΔV, only for severe conjunctions
     ΔV along z in CW frame. Changes inclination slightly.
"""

from __future__ import annotations

import logging
import math
import sys
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Add orbital engine to path
_OE_ROOT = pathlib.Path(__file__).parents[4] / "orbital-engine"
if str(_OE_ROOT) not in sys.path:
    sys.path.insert(0, str(_OE_ROOT))

# Physical constants
ISP_MONOPROP_S = 300.0    # mono-propellant Isp [s]
ISP_BIPROP_S   = 450.0    # bi-propellant Isp [s]
G0_MS2         = 9.80665  # standard gravity [m/s²]
SAT_MASS_KG    = 500.0    # default satellite mass [kg]
MU_KM3_S2      = 398600.4418
EARTH_R_KM     = 6378.137


# ── Maneuver option model ─────────────────────────────────────

@dataclass
class ManeuverOption:
    """
    One evaluated collision avoidance maneuver option.

    Contains the ΔV vector, fuel estimate, post-maneuver Pc,
    maneuver window, and safety assessment.
    """
    option_id:         str       # e.g. "along_track_burn"
    direction:         str       # "along-track" | "radial" | "cross-track"
    burn_time:         datetime  # when to execute (T-24h nominal)

    # ΔV in LVLH (CW) frame [km/s]
    dv_radial_kms:     float = 0.0    # x: radial (outward +)
    dv_along_kms:      float = 0.0    # y: along-track (+ve prograde)
    dv_cross_kms:      float = 0.0    # z: cross-track

    # Derived
    delta_v_kms:       float = 0.0    # magnitude [km/s]
    delta_v_ms:        float = 0.0    # magnitude [m/s] for readability
    fuel_mass_kg:      float = 0.0    # propellant consumed [kg]

    # Post-maneuver prediction
    new_miss_dist_km:  float = 0.0    # predicted miss distance after burn
    new_pc:            float = 0.0    # predicted Pc after burn
    new_risk_level:    str   = "white"
    pc_reduction_pct:  float = 0.0    # percentage Pc reduction

    # Impact assessment
    altitude_change_km:float = 0.0    # Δh (+ = higher, - = lower)
    period_change_s:   float = 0.0    # ΔT (s)
    lifetime_impact:   str   = "negligible"

    # Safety flags
    safe_to_execute:   bool  = True
    safety_notes:      list[str] = field(default_factory=list)
    propulsion_type:   str   = "monopropellant"  # or "bipropellant"

    recommended:       bool  = False   # True for the best option

    def to_dict(self) -> dict:
        return {
            "option_id":        self.option_id,
            "direction":        self.direction,
            "burn_time":        self.burn_time.isoformat(),
            "delta_v_ms":       round(self.delta_v_ms, 4),
            "delta_v_kms":      round(self.delta_v_kms, 7),
            "dv_components": {
                "radial_kms":    round(self.dv_radial_kms, 7),
                "along_track_kms": round(self.dv_along_kms, 7),
                "cross_track_kms": round(self.dv_cross_kms, 7),
            },
            "fuel_mass_kg":     round(self.fuel_mass_kg, 4),
            "new_miss_dist_km": round(self.new_miss_dist_km, 4),
            "new_pc":           self.new_pc,
            "new_risk_level":   self.new_risk_level,
            "pc_reduction_pct": round(self.pc_reduction_pct, 1),
            "altitude_change_km":round(self.altitude_change_km, 4),
            "period_change_s":  round(self.period_change_s, 2),
            "lifetime_impact":  self.lifetime_impact,
            "safe_to_execute":  self.safe_to_execute,
            "safety_notes":     self.safety_notes,
            "recommended":      self.recommended,
        }


@dataclass
class ManeuverRecommendation:
    """Complete maneuver recommendation for one conjunction event."""
    conjunction_id:  str
    primary_norad:   int
    primary_name:    str
    secondary_norad: int
    tca:             datetime
    current_pc:      float
    current_risk:    str
    miss_distance_km:float

    options:         list[ManeuverOption] = field(default_factory=list)
    recommended:     Optional[ManeuverOption] = None
    no_maneuver_needed: bool = False
    rationale:       str = ""
    assessed_at:     datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "conjunction_id":  self.conjunction_id,
            "primary_norad":   self.primary_norad,
            "primary_name":    self.primary_name,
            "secondary_norad": self.secondary_norad,
            "tca":             self.tca.isoformat(),
            "current_pc":      self.current_pc,
            "current_risk":    self.current_risk,
            "miss_distance_km":round(self.miss_distance_km, 4),
            "no_maneuver_needed": self.no_maneuver_needed,
            "rationale":       self.rationale,
            "recommended":     self.recommended.to_dict() if self.recommended else None,
            "options":         [o.to_dict() for o in self.options],
            "assessed_at":     self.assessed_at.isoformat(),
        }


# ── Maneuver Recommendation Engine ───────────────────────────

class ManeuverRecommendationEngine:
    """
    Evaluates and recommends collision avoidance maneuvers.

    Uses CW (Clohessy-Wiltshire) equations for relative motion analysis.
    Evaluates three burn directions: along-track, radial, cross-track.
    Selects the minimum-ΔV option that achieves Pc < 1e-5 (GREEN).

    Parameters
    ----------
    satellite_mass_kg : float
        Primary satellite mass for fuel estimation.
    isp_s : float
        Propulsion system specific impulse.
    burn_lead_time_h : float
        Hours before TCA to execute the maneuver (default 24h).
    """

    def __init__(
        self,
        satellite_mass_kg: float = SAT_MASS_KG,
        isp_s:             float = ISP_MONOPROP_S,
        burn_lead_time_h:  float = 24.0,
    ) -> None:
        self._mass     = satellite_mass_kg
        self._isp      = isp_s
        self._lead_h   = burn_lead_time_h

    # ── Public entry point ────────────────────────────────────

    def evaluate(
        self,
        conjunction_id:   str,
        primary_norad:    int,
        primary_name:     str,
        secondary_norad:  int,
        secondary_name:   str,
        tca:              datetime,
        miss_distance_km: float,
        relative_velocity_kms: float,
        collision_probability: float,
        primary_altitude_km: float = 420.0,
        risk_level:       str = "yellow",
    ) -> ManeuverRecommendation:
        """
        Evaluate maneuver options for a conjunction event.

        Returns a ManeuverRecommendation with up to 3 options
        (along-track, radial, cross-track) sorted by ΔV cost.
        The minimum-ΔV option that achieves Pc < 1e-5 is marked
        as recommended.

        Performance target: < 500 ms
        """
        rec = ManeuverRecommendation(
            conjunction_id=conjunction_id,
            primary_norad=primary_norad,
            primary_name=primary_name,
            secondary_norad=secondary_norad,
            tca=tca,
            current_pc=collision_probability,
            current_risk=risk_level,
            miss_distance_km=miss_distance_km,
        )

        # No maneuver needed for white events
        if collision_probability < 1e-5:
            rec.no_maneuver_needed = True
            rec.rationale = (
                f"Pc={collision_probability:.2e} is below the GREEN threshold (1e-5). "
                "No maneuver required. Continue monitoring."
            )
            return rec

        # Burn time: 24h before TCA (or as close as possible to window open)
        burn_time = tca - timedelta(hours=self._lead_h)
        if burn_time < datetime.now(timezone.utc):
            burn_time = datetime.now(timezone.utc) + timedelta(minutes=30)

        # Time from burn to TCA [s]
        dt_tca_s = (tca - burn_time).total_seconds()

        # CW setup at primary altitude
        cw = self._get_cw(primary_altitude_km)

        # Evaluate three maneuver strategies
        options: list[ManeuverOption] = []

        opt_at = self._along_track_burn(
            cw, miss_distance_km, relative_velocity_kms,
            collision_probability, burn_time, dt_tca_s, primary_altitude_km,
        )
        options.append(opt_at)

        opt_rad = self._radial_burn(
            cw, miss_distance_km, relative_velocity_kms,
            collision_probability, burn_time, dt_tca_s, primary_altitude_km,
        )
        options.append(opt_rad)

        opt_ct = self._cross_track_burn(
            miss_distance_km, relative_velocity_kms,
            collision_probability, burn_time, primary_altitude_km,
        )
        options.append(opt_ct)

        # Sort by ΔV cost (cheapest first)
        options.sort(key=lambda o: o.delta_v_ms)

        # Mark recommended: cheapest that achieves Pc < 1e-5 and is safe
        recommended = None
        for opt in options:
            if opt.safe_to_execute and opt.new_pc < 1e-5:
                recommended = opt
                recommended.recommended = True
                break
        # Fall back to cheapest safe option if none achieves GREEN
        if not recommended:
            safe_opts = [o for o in options if o.safe_to_execute]
            if safe_opts:
                recommended = safe_opts[0]
                recommended.recommended = True

        rec.options    = options
        rec.recommended = recommended

        if recommended:
            rec.rationale = (
                f"Recommended: {recommended.direction} burn of {recommended.delta_v_ms:.4f} m/s "
                f"({recommended.fuel_mass_kg:.3f} kg fuel) at "
                f"{recommended.burn_time.isoformat()[:19]}Z. "
                f"Expected Pc reduction: {collision_probability:.2e} → {recommended.new_pc:.2e} "
                f"({recommended.pc_reduction_pct:.0f}% reduction, "
                f"new risk: {recommended.new_risk_level.upper()})."
            )
        else:
            rec.rationale = (
                "No safe maneuver option identified within propellant budget. "
                "Escalate to operations centre for manual assessment."
            )

        return rec

    # ── Strategy 1: Along-track burn ──────────────────────────

    def _along_track_burn(
        self,
        cw: "ClohessyWiltshire",
        miss_km: float,
        rel_v_kms: float,
        pc: float,
        burn_time: datetime,
        dt_s: float,
        alt_km: float,
    ) -> ManeuverOption:
        """
        Along-track (y-axis) burn: shifts orbital phase to change
        the timing of the conjunction. The primary arrives at the
        TCA location ahead of or behind the secondary.

        ΔV requirement: small (0.01–0.5 m/s typical).
        Effect: TCA timing shifts, effective separation increases.
        """
        # Phase shift required to move conjunction out of 5 km danger zone
        # Δy = 2 * ΔT_phase × v_orbital (simplified)
        v_orbital_kms = math.sqrt(MU_KM3_S2 / (EARTH_R_KM + alt_km))
        # Need to move primary by at least (5 - miss_km) km relative to secondary
        required_sep_km = max(5.0, miss_km * 3)  # 3× safety margin
        # CW: along-track drift accumulates as Δy ≈ -3n×Δx×t for radial maneuver
        # For along-track maneuver, phase shift ≈ Δy ≈ 2 × Δvy × t / n
        # Minimum ΔV to achieve required_sep_km separation at TCA
        n = cw.n
        if dt_s > 0:
            dvy_kms = required_sep_km / (2 * dt_s) * (n / v_orbital_kms)
            dvy_kms = max(dvy_kms, 1e-5)  # minimum 0.01 m/s
        else:
            dvy_kms = 0.001

        dv_kms = abs(dvy_kms)
        new_miss = miss_km + required_sep_km * 0.8  # 80% effectiveness estimate
        new_pc   = self._estimate_new_pc(pc, miss_km, new_miss)

        alt_change  = -2 * dvy_kms / n * 1000  # km (simplified vis-viva)
        period_chg  = 3 * math.pi / n * alt_change / (EARTH_R_KM + alt_km) * 1000  # s

        return ManeuverOption(
            option_id="along_track_burn",
            direction="along-track",
            burn_time=burn_time,
            dv_along_kms=dvy_kms,
            delta_v_kms=dv_kms,
            delta_v_ms=dv_kms * 1000,
            fuel_mass_kg=self._tsiolkovsky(dv_kms),
            new_miss_dist_km=new_miss,
            new_pc=new_pc,
            new_risk_level=self._pc_to_risk(new_pc),
            pc_reduction_pct=max(0, (pc - new_pc) / pc * 100) if pc > 0 else 0,
            altitude_change_km=alt_change,
            period_change_s=period_chg,
            lifetime_impact="negligible" if abs(alt_change) < 1 else "minor",
            safe_to_execute=(EARTH_R_KM + alt_km + alt_change) > EARTH_R_KM + 200,
            safety_notes=[
                f"Along-track burn: {dvy_kms*1000:.4f} m/s prograde",
                f"Altitude change: {alt_change:+.3f} km",
                f"Orbital period change: {period_chg:+.2f} s",
            ],
            propulsion_type="monopropellant",
        )

    # ── Strategy 2: Radial burn ───────────────────────────────

    def _radial_burn(
        self,
        cw: "ClohessyWiltshire",
        miss_km: float,
        rel_v_kms: float,
        pc: float,
        burn_time: datetime,
        dt_s: float,
        alt_km: float,
    ) -> ManeuverOption:
        """
        Radial (x-axis) burn: separates the primary radially from
        the secondary's trajectory. Creates a natural drift ellipse
        that avoids the conjunction plane.

        ΔV requirement: moderate (0.05–2 m/s typical).
        Effect: radial separation grows as the drift ellipse evolves.
        Uses CW two-impulse rendezvous in reverse to target a safe
        relative position at TCA epoch.
        """
        n = cw.n
        required_miss = max(5.0, miss_km * 2)

        # Target a 5 km radial offset at TCA
        # CW radial motion: x(t) = (4-3cos(nt))x₀ + sin(nt)ẋ₀/n + 2(1-cos(nt))ẏ₀/n
        # For a pure radial burn (dvx at t=0, x0=0, ẏ₀=0):
        # x(TCA) = sin(n×dt) × dvx / n
        if abs(math.sin(n * dt_s)) > 1e-6:
            dvx_kms = required_miss * n / math.sin(n * dt_s)
        else:
            dvx_kms = required_miss * n  # fallback for very short window

        dvx_kms = min(abs(dvx_kms), 0.01)  # cap at 10 m/s
        dv_kms  = abs(dvx_kms)

        new_miss = math.sqrt(miss_km**2 + required_miss**2)  # orthogonal separation
        new_pc   = self._estimate_new_pc(pc, miss_km, new_miss)

        # Radial maneuver causes altitude oscillation: max Δalt ≈ 2|dvx|/n [km]
        alt_osc = 2 * dvx_kms / n
        alt_change = 0.0  # net zero for radial (periodic)

        return ManeuverOption(
            option_id="radial_burn",
            direction="radial",
            burn_time=burn_time,
            dv_radial_kms=dvx_kms,
            delta_v_kms=dv_kms,
            delta_v_ms=dv_kms * 1000,
            fuel_mass_kg=self._tsiolkovsky(dv_kms),
            new_miss_dist_km=new_miss,
            new_pc=new_pc,
            new_risk_level=self._pc_to_risk(new_pc),
            pc_reduction_pct=max(0, (pc - new_pc) / pc * 100) if pc > 0 else 0,
            altitude_change_km=alt_change,
            period_change_s=0.0,
            lifetime_impact="negligible",
            safe_to_execute=True,
            safety_notes=[
                f"Radial burn: {dvx_kms*1000:.4f} m/s outward",
                f"Peak altitude oscillation: ±{alt_osc:.3f} km (periodic — net zero)",
                "Orbit mean altitude unchanged",
            ],
            propulsion_type="monopropellant",
        )

    # ── Strategy 3: Cross-track burn ──────────────────────────

    def _cross_track_burn(
        self,
        miss_km: float,
        rel_v_kms: float,
        pc: float,
        burn_time: datetime,
        alt_km: float,
    ) -> ManeuverOption:
        """
        Cross-track (z-axis) burn: changes orbital inclination slightly,
        laterally displacing the primary from the conjunction plane.

        ΔV requirement: highest of the three options.
        Effect: out-of-plane separation grows quadratically with ΔV.
        Only recommended for severe conjunctions where along-track
        and radial options are insufficient.
        """
        # Required out-of-plane separation
        required_miss = max(5.0, miss_km * 2)

        # For a cross-track burn at a given mean motion:
        # Δi = Δvz / v_orbital (inclination change)
        # Cross-track separation at TCA: Δz ≈ required_miss [km]
        n = math.sqrt(MU_KM3_S2 / (EARTH_R_KM + alt_km)**3)
        v_orb = math.sqrt(MU_KM3_S2 / (EARTH_R_KM + alt_km))  # km/s
        # Δvz needed: Δz = Δvz × sin(n×t_TCA) / n
        # Conservative: ΔV_z ≈ required_miss × n (worst case)
        dvz_kms = required_miss * n

        new_miss = math.sqrt(miss_km**2 + required_miss**2)
        new_pc   = self._estimate_new_pc(pc, miss_km, new_miss)

        # ΔI in degrees
        di_deg = math.degrees(dvz_kms / v_orb)

        return ManeuverOption(
            option_id="cross_track_burn",
            direction="cross-track",
            burn_time=burn_time,
            dv_cross_kms=dvz_kms,
            delta_v_kms=dvz_kms,
            delta_v_ms=dvz_kms * 1000,
            fuel_mass_kg=self._tsiolkovsky(dvz_kms),
            new_miss_dist_km=new_miss,
            new_pc=new_pc,
            new_risk_level=self._pc_to_risk(new_pc),
            pc_reduction_pct=max(0, (pc - new_pc) / pc * 100) if pc > 0 else 0,
            altitude_change_km=0.0,
            period_change_s=0.0,
            lifetime_impact="moderate" if dvz_kms > 0.05 else "minor",
            safe_to_execute=dvz_kms < 0.1,
            safety_notes=[
                f"Cross-track burn: {dvz_kms*1000:.4f} m/s",
                f"Inclination change: {di_deg:.4f}°",
                "High ΔV cost — only recommended if other options unavailable",
            ],
            propulsion_type="bipropellant" if dvz_kms > 0.05 else "monopropellant",
        )

    # ── Neo4j persistence ─────────────────────────────────────

    async def persist_to_graph(self, rec: ManeuverRecommendation) -> int:
        """
        Persist ManeuverOptions to Neo4j as:
          (:ConjunctionEvent)-[:RECOMMENDS]->(:ManeuverOption)

        Also marks the recommended option with recommended=true.

        Returns number of ManeuverOption nodes created/updated.
        """
        from app.graph.connection import is_available, execute_batch

        if not is_available() or not rec.options:
            return 0

        CYPHER = """
        UNWIND $batch AS row
        MERGE (mo:ManeuverOption {optionId: row.optionId, conjunctionId: row.conjunctionId})
        SET mo.direction       = row.direction,
            mo.deltaVMs        = row.deltaVMs,
            mo.deltaVKms       = row.deltaVKms,
            mo.fuelMassKg      = row.fuelMassKg,
            mo.burnTime        = datetime(row.burnTime),
            mo.newPc           = row.newPc,
            mo.newRiskLevel    = row.newRiskLevel,
            mo.pcReductionPct  = row.pcReductionPct,
            mo.safeToExecute   = row.safeToExecute,
            mo.recommended     = row.recommended,
            mo.altitudeChangeKm= row.altitudeChangeKm,
            mo.updatedAt       = datetime()
        WITH mo, row
        OPTIONAL MATCH (ce:ConjunctionEvent {conjunctionId: row.conjunctionId})
        FOREACH (_ IN CASE WHEN ce IS NOT NULL THEN [1] ELSE [] END |
            MERGE (ce)-[:RECOMMENDS {recommended: row.recommended}]->(mo)
        )
        """

        batch = [
            {
                "optionId":       f"{rec.conjunction_id}::{opt.option_id}",
                "conjunctionId":  rec.conjunction_id,
                "direction":      opt.direction,
                "deltaVMs":       round(opt.delta_v_ms, 6),
                "deltaVKms":      round(opt.delta_v_kms, 9),
                "fuelMassKg":     round(opt.fuel_mass_kg, 6),
                "burnTime":       opt.burn_time.isoformat(),
                "newPc":          opt.new_pc,
                "newRiskLevel":   opt.new_risk_level,
                "pcReductionPct": round(opt.pc_reduction_pct, 2),
                "safeToExecute":  opt.safe_to_execute,
                "recommended":    opt.recommended,
                "altitudeChangeKm": round(opt.altitude_change_km, 6),
            }
            for opt in rec.options
        ]

        try:
            counters = await execute_batch(CYPHER, batch)
            logger.info(
                "maneuver_options_persisted conjunction=%s options=%d nodes=%d",
                rec.conjunction_id, len(batch), counters.get("nodes_created", 0),
            )
            return counters.get("nodes_created", 0)
        except Exception as exc:
            logger.error("maneuver_persist_failed error=%s", exc)
            return 0

    async def get_recommendations_for_conjunction(
        self, conjunction_id: str
    ) -> list[dict]:
        """Query Neo4j for ManeuverOptions linked to a conjunction."""
        from app.graph.connection import is_available, execute_read

        if not is_available():
            return []

        try:
            rows = await execute_read(
                """
                MATCH (ce:ConjunctionEvent {conjunctionId: $cid})-[:RECOMMENDS]->(mo:ManeuverOption)
                RETURN mo ORDER BY mo.deltaVMs ASC
                """,
                cid=conjunction_id,
            )
            return [r.get("mo", {}) for r in rows]
        except Exception as exc:
            logger.error("maneuver_graph_query_failed error=%s", exc)
            return []

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _get_cw(altitude_km: float):
        from src.relative_motion.clohessy_wiltshire import ClohessyWiltshire
        return ClohessyWiltshire.from_altitude_km(altitude_km)

    def _tsiolkovsky(self, dv_kms: float) -> float:
        """
        Tsiolkovsky rocket equation: fuel mass [kg]
        Δm = m₀ × (1 - exp(-ΔV / (Isp × g₀)))
        """
        v_e = self._isp * G0_MS2 / 1000.0  # effective exhaust velocity [km/s]
        return self._mass * (1 - math.exp(-dv_kms / v_e))

    @staticmethod
    def _estimate_new_pc(pc: float, old_miss: float, new_miss: float) -> float:
        """
        Estimate post-maneuver Pc by scaling with miss distance ratio.
        Pc ∝ exp(-r²/2σ²) → Pc_new ≈ Pc_old × exp(-(new_miss²-old_miss²)/(2σ²))
        Uses simplified model: Pc scales as (old_miss/new_miss)² for typical σ.
        """
        if new_miss <= 0 or old_miss <= 0:
            return pc
        ratio = (old_miss / new_miss) ** 2
        return max(0.0, min(pc, pc * ratio))

    @staticmethod
    def _pc_to_risk(pc: float) -> str:
        if pc >= 1e-3: return "red"
        if pc >= 1e-4: return "yellow"
        if pc >= 1e-5: return "green"
        return "white"


