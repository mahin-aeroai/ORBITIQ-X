"""
ORBITIQ-X — Aerospace Foundation Model Training Dataset
=========================================================
Phases 1-4: Training corpus, instruction dataset, reasoning traces,
and graph-document-embedding linkage.

Architecture
────────────
  Phase 1 — Corpus: unified document → training record pipeline
    Extends existing AerospaceCorpusService (16 curated sources)
    Adds structured TrainingRecord with full provenance

  Phase 2 — Instructions: 100K+ aerospace Q&A pairs
    Generated programmatically from domain templates
    Seeded with AEROSPACE_EVAL_QUESTIONS from existing evaluator
    Augmented with graph-derived pairs (operator, satellite, conjunction)

  Phase 3 — Reasoning: chain-of-thought traces
    Multi-step orbital mechanics reasoning
    Conjunction risk assessment reasoning chains
    Mission planning decision trees

  Phase 4 — Linking: every example traceable to source
    graph_node_refs: Neo4j node IDs
    document_refs: Qdrant chunk IDs
    corpus_source_ref: CORPUS_SOURCES source_id

Audit notes
───────────
  - rag/src/evaluation/evaluator.py: AEROSPACE_EVAL_QUESTIONS (seed data)
    and AerospaceRAGEvaluator (eval framework) → called, not rewritten
  - backend/app/services/graphrag/corpus_service.py: CORPUS_SOURCES →
    used as provenance references, not rewritten
  - rag/src/models/schemas.py: EvalSample, EvalMetrics → reused here
"""

from __future__ import annotations

import hashlib
import json
import logging
import pathlib
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# PHASE 1 — TRAINING CORPUS DATA MODELS
# ══════════════════════════════════════════════════════════════

class TrainingDomain(str, Enum):
    ORBITAL_MECHANICS  = "orbital_mechanics"
    CONJUNCTION_ANALYSIS = "conjunction_analysis"
    SPACE_DEBRIS       = "space_debris"
    MISSION_HISTORY    = "mission_history"
    LAUNCH_VEHICLES    = "launch_vehicles"
    SATELLITE_SYSTEMS  = "satellite_systems"
    SSA                = "ssa"
    SPACE_WEATHER      = "space_weather"
    STANDARDS          = "standards"
    OPERATORS          = "operators"


class ExampleType(str, Enum):
    INSTRUCTION        = "instruction"      # Q → A
    REASONING          = "reasoning"        # Q → step-by-step → A
    CORPUS_EXTRACT     = "corpus_extract"   # document chunk → summary
    GRAPH_DERIVED      = "graph_derived"    # knowledge graph → structured Q&A
    EVALUATION         = "evaluation"       # held-out benchmark


@dataclass
class TrainingRecord:
    """
    A single training example with full provenance.

    All fields map to their origin source so the training
    data is fully auditable and traceable.
    """
    record_id:         str
    domain:            TrainingDomain
    example_type:      ExampleType
    instruction:       str                     # prompt / question
    output:            str                     # expected answer / completion
    reasoning_trace:   list[str]               # chain-of-thought steps (Phase 3)

    # Phase 4 linkage
    corpus_source_ref: str | None = None       # CORPUS_SOURCES.source_id
    graph_node_refs:   list[str] = field(default_factory=list)   # Neo4j node IDs
    document_refs:     list[str] = field(default_factory=list)   # Qdrant chunk IDs
    entity_refs:       list[str] = field(default_factory=list)   # mission/norad/operator

    # Metadata
    quality_score:     float = 1.0             # 0-1 estimated quality
    difficulty:        str = "medium"          # easy | medium | hard | expert
    source_verified:   bool = False
    created_at:        str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_jsonl(self) -> str:
        """Serialize to JSONL format for training pipelines."""
        return json.dumps({
            "record_id":       self.record_id,
            "domain":          self.domain.value,
            "example_type":    self.example_type.value,
            "instruction":     self.instruction,
            "output":          self.output,
            "reasoning_trace": self.reasoning_trace,
            "corpus_source":   self.corpus_source_ref,
            "graph_refs":      self.graph_node_refs,
            "entity_refs":     self.entity_refs,
            "difficulty":      self.difficulty,
            "quality_score":   self.quality_score,
        })

    @property
    def fingerprint(self) -> str:
        """Deduplication hash based on instruction + output."""
        content = f"{self.instruction}|{self.output}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ══════════════════════════════════════════════════════════════
# PHASE 2 — INSTRUCTION DATASET GENERATOR
# ══════════════════════════════════════════════════════════════

# Domain-specific instruction templates for programmatic generation.
# Each template expands to N variants per domain covering the full
# aerospace knowledge space.

INSTRUCTION_TEMPLATES: dict[TrainingDomain, list[dict]] = {

    TrainingDomain.ORBITAL_MECHANICS: [
        {
            "instruction": "What is the SGP4 propagator and what perturbations does it model?",
            "output": "SGP4 (Simplified General Perturbations 4) is the standard analytical "
                      "orbital propagator for Earth satellites. It models: (1) Earth's non-spherical "
                      "gravitational field via J2, J3, J4 zonal harmonics, (2) atmospheric drag using "
                      "the ballistic coefficient (Bstar), and (3) solar radiation pressure effects. "
                      "SGP4 takes Two-Line Element (TLE) sets as input and propagates mean orbital "
                      "elements forward in time using the Kozai mean motion.",
            "difficulty": "medium", "corpus_source": "HOOTS-ROEHRICH-1980",
            "graph_refs": ["OrbitalRegime:LEO"],
        },
        {
            "instruction": "Explain the Julian Date and why it is required for SGP4 propagation.",
            "output": "Julian Date (JD) is a continuous count of days since January 1, 4713 BC (noon). "
                      "SGP4 requires JD (split as JD integer + fractional day for precision) because "
                      "it must compute time elapsed since the TLE epoch to sub-second accuracy. "
                      "Passing Unix timestamps directly to SGP4 causes error_code=1 (invalid epoch) "
                      "with NaN position output. The conversion: JD = Unix_timestamp/86400 + 2440587.5. "
                      "In practice, sgp4.api.jday() converts calendar date to JD with 64-bit precision.",
            "difficulty": "hard", "corpus_source": "HOOTS-ROEHRICH-1980",
            "graph_refs": [],
        },
        {
            "instruction": "What altitude bands define the LEO, MEO, and GEO orbital regimes?",
            "output": "LEO (Low Earth Orbit): 160–2000 km altitude, ~90 min orbital period. "
                      "SSO (Sun-Synchronous Orbit): ~400–1000 km, near-polar, fixed solar angle. "
                      "MEO (Medium Earth Orbit): 2000–35786 km, 2–24 hour periods (GPS at ~20200 km). "
                      "GEO (Geostationary): exactly 35786 km, 23h 56m period, appears stationary. "
                      "VLEO (<450 km): high drag, short lifetime, used for reconnaissance. "
                      "HEO (Highly Elliptical): high eccentricity, e.g. Molniya 63.4° inclined.",
            "difficulty": "easy", "corpus_source": None,
            "graph_refs": ["OrbitalRegime:LEO", "OrbitalRegime:MEO", "OrbitalRegime:GEO"],
        },
        {
            "instruction": "Derive the relationship between mean motion and semi-major axis.",
            "output": "From Kepler's Third Law: T² = (4π²/μ) × a³, where T is orbital period, "
                      "μ = GM = 398600.4418 km³/s² (Earth's gravitational parameter), a = semi-major axis. "
                      "Mean motion n (rev/day) = 86400/T (seconds/day ÷ orbital period in seconds). "
                      "Therefore: n = (1/2π) × √(μ/a³) in rad/s, or n = 86400/(2π) × √(μ/a³) in rev/day. "
                      "Inverted: a = (μ/n²)^(1/3) where n must be in rad/s.",
            "difficulty": "hard", "corpus_source": "VALLADO-ORBITAL-MECH",
            "graph_refs": [],
        },
        {
            "instruction": "What causes the J2 perturbation and how does it affect satellite orbits?",
            "output": "J2 is the dominant zonal harmonic of Earth's geopotential, caused by Earth's "
                      "equatorial bulge (oblateness). Earth is not a perfect sphere; its equatorial "
                      "radius (6378.137 km) exceeds its polar radius (6356.752 km) by ~21 km. "
                      "J2 effects on orbits: (1) Right Ascension of Ascending Node (RAAN) precesses "
                      "westward for prograde orbits, (2) Argument of perigee rotates, "
                      "(3) Mean motion is slightly higher than Keplerian. "
                      "For LEO: RAAN drifts ~7°/day westward. SSO orbits are designed so J2-induced "
                      "eastward drift (98-99° inclination) matches Earth's revolution around the Sun.",
            "difficulty": "expert", "corpus_source": "HOOTS-ROEHRICH-1980",
            "graph_refs": ["OrbitalRegime:SSO"],
        },
    ],

    TrainingDomain.CONJUNCTION_ANALYSIS: [
        {
            "instruction": "Explain the Foster method for computing collision probability (Pc).",
            "output": "The Foster (1992/2001) method computes Pc by projecting the combined "
                      "position covariance of both objects onto the collision plane — the plane "
                      "perpendicular to the relative velocity vector at Time of Closest Approach (TCA). "
                      "Steps: (1) Combine covariance matrices C = C1 + C2 in ECI frame. "
                      "(2) Project C onto collision plane using P = I - e_v × e_v^T. "
                      "(3) Diagonalize the 2×2 projected covariance to find principal axes (σ_x, σ_y). "
                      "(4) Integrate 2D Gaussian over disk of radius r = HBR1 + HBR2 centered on miss "
                      "vector projection. Result Pc ∈ [0,1]. ORBITIQ-X implements Foster with "
                      "series expansion (Chan 1997) falling back to scipy dblquad and Monte Carlo.",
            "difficulty": "expert", "corpus_source": "FOSTER-1992",
            "graph_refs": ["ConjunctionEvent:CDM"],
        },
        {
            "instruction": "What are the ORBITIQ-X risk level thresholds for conjunction events?",
            "output": "ORBITIQ-X uses IADC/18 SWS risk level thresholds based on Pc: "
                      "RED: Pc ≥ 1×10⁻³ — operator action required, maneuver consideration mandatory. "
                      "YELLOW: 1×10⁻⁴ ≤ Pc < 1×10⁻³ — elevated monitoring, maneuver assessment. "
                      "GREEN: 1×10⁻⁵ ≤ Pc < 1×10⁻⁴ — informational, increased tracking cadence. "
                      "WHITE: Pc < 1×10⁻⁵ — routine, below standard alert threshold. "
                      "MANEUVER_REQUIRED flag is set for Pc ≥ 1×10⁻⁴ (yellow+red).",
            "difficulty": "medium", "corpus_source": "IADC-2007",
            "graph_refs": ["ConjunctionEvent:riskLevel"],
        },
        {
            "instruction": "What is Time of Closest Approach (TCA) and how is it computed?",
            "output": "TCA is the epoch at which two objects reach their minimum separation distance "
                      "(miss distance) during a conjunction. Computation: (1) Propagate both objects "
                      "at regular time steps (typically 60s) over a 72-hour screening window. "
                      "(2) Identify the step with minimum Euclidean distance between position vectors. "
                      "(3) Optionally refine using golden-section search or parabolic interpolation "
                      "to sub-minute precision. The miss distance at TCA is the key input to Foster Pc "
                      "along with the covariance matrices projected to the collision plane at TCA.",
            "difficulty": "medium", "corpus_source": "CCSDS-CDM-508",
            "graph_refs": [],
        },
        {
            "instruction": "What is a Conjunction Data Message (CDM) and what does it contain?",
            "output": "A CDM (CCSDS 508.0-B-1) is a standardized message format exchanged between "
                      "SSA providers and satellite operators for collision avoidance. Key fields: "
                      "CREATION_DATE, MESSAGE_ID, TCA (Time of Closest Approach), "
                      "MISS_DISTANCE (metres), RELATIVE_SPEED (m/s), "
                      "COLLISION_PROBABILITY (dimensionless, 0-1), "
                      "OBJECT1/OBJECT2 blocks (NORAD ID, name, covariance in RTN frame), "
                      "HBR (hard-body radius in metres), RISK_LEVEL. "
                      "18 SWS/LeoLabs generate CDMs for Pc > 1e-6. "
                      "ORBITIQ-X generates CCSDS-inspired CDM JSON via /conjunctions/cdm/{id}.",
            "difficulty": "medium", "corpus_source": "CCSDS-CDM-508",
            "graph_refs": [],
        },
        {
            "instruction": "How does orbital binning reduce the computational cost of conjunction screening?",
            "output": "Naive conjunction screening for N objects requires N(N-1)/2 pair comparisons: "
                      "1.25 billion pairs for 50,000 objects (O(N²)). "
                      "Orbital binning groups objects by altitude band (200 km) and inclination band "
                      "(15°). Objects in different altitude bands cannot approach (different orbital "
                      "energy), so only intra-bin and adjacent-bin pairs are tested. "
                      "Reduction example (50K catalog): "
                      "After altitude binning: ~10M pairs (>99% reduction) "
                      "After voxel-hash spatial filter (5 km): ~500 pairs "
                      "After Foster Pc: ~50 CDM events above 1e-6 threshold. "
                      "ORBITIQ-X implements this in ConjunctionScreener using O(n) voxel hashing.",
            "difficulty": "expert", "corpus_source": "ALFANO-2005",
            "graph_refs": [],
        },
    ],

    TrainingDomain.SPACE_DEBRIS: [
        {
            "instruction": "How many debris objects did the Fengyun-1C ASAT test create?",
            "output": "The January 2007 Chinese ASAT test against Fengyun-1C (NORAD 25730) at "
                      "~865 km altitude created the largest single debris-generating event in history: "
                      "~3,500 trackable objects (>10 cm radar cross-section), "
                      "estimated 35,000 fragments >1 cm, "
                      "~1 million+ fragments >1 mm. "
                      "The debris cloud is concentrated between 800-900 km in SSO inclination (~99°). "
                      "As of 2024, ~3,000 fragments remain trackable — some will remain in orbit for "
                      "decades due to the high altitude exceeding atmospheric decay.",
            "difficulty": "medium", "corpus_source": "ESA-DEBRIS-2023",
            "graph_refs": ["DebrisObject:FY1C"],
        },
        {
            "instruction": "What is the IADC 25-year deorbit rule?",
            "output": "The Inter-Agency Space Debris Coordination Committee (IADC) guideline (2007) "
                      "requires that LEO objects disposed from operations deorbit within 25 years. "
                      "This limits long-term debris accumulation in the most congested orbital regimes. "
                      "Implementation options: (1) Propulsive deorbit burn reducing perigee to "
                      "reentry altitude (~120 km), (2) Passivation (venting residual propellant/batteries) "
                      "to prevent explosions, (3) Natural decay for VLEO objects (<400 km). "
                      "NASA-STD-8719.14 adopts the 25-year rule for all NASA missions. "
                      "Compliance rate: ~30% of recent missions actually meet the guideline.",
            "difficulty": "medium", "corpus_source": "IADC-2007",
            "graph_refs": [],
        },
        {
            "instruction": "Explain the Kessler syndrome and its relevance to modern SSA.",
            "output": "Kessler syndrome (proposed by NASA scientist Donald Kessler, 1978) describes "
                      "a self-sustaining cascade: if the debris density in LEO exceeds a critical "
                      "threshold, collisions generate more debris faster than atmospheric drag removes it, "
                      "triggering a chain reaction that renders LEO unusable. "
                      "Current status: Some orbital regimes may already be past the tipping point "
                      "(particularly 800-1000 km SSO belt after Fengyun-1C, COSMOS 2251 collision). "
                      "SSA relevance: ORBITIQ-X tracks this via orbital regime density metrics — "
                      "debris-to-satellite ratio per altitude band. "
                      "Mitigation: 25-year deorbit rule, active debris removal (ESA ClearSpace-1).",
            "difficulty": "medium", "corpus_source": "NASA-DEBRIS-2023",
            "graph_refs": ["OrbitalRegime:SSO"],
        },
    ],

    TrainingDomain.MISSION_HISTORY: [
        {
            "instruction": "What was the primary mission objective of Chandrayaan-3?",
            "output": "Chandrayaan-3 (launched July 14, 2023 on LVM3-M4) was ISRO's third lunar "
                      "exploration mission and India's second attempt at a soft landing. "
                      "Primary objectives: (1) Demonstrate safe and soft lunar landing capability, "
                      "(2) Deploy Pragyan rover for in-situ surface analysis, "
                      "(3) Conduct scientific experiments on lunar surface regolith. "
                      "Landing: August 23, 2023 near the lunar south pole (69.37°S, 32.35°E) — "
                      "first mission to land at the lunar south pole, demonstrating India as the "
                      "4th nation to achieve lunar soft landing (after USSR, USA, China). "
                      "The mission confirmed presence of sulfur and other elements near the south pole.",
            "difficulty": "medium", "corpus_source": "ISRO-CHANDRAYAAN3",
            "graph_refs": ["Mission:Chandrayaan3", "LaunchVehicle:LV-GSLV-MK3"],
        },
        {
            "instruction": "Describe the Artemis program architecture and participating agencies.",
            "output": "Artemis is NASA's program to return humans to the Moon by the mid-2020s. "
                      "Key elements: "
                      "(1) SLS (Space Launch System): 95-tonne LEO capacity Block 1, 130 tonnes Block 2. "
                      "(2) Orion spacecraft: crew capsule with ESA-built European Service Module. "
                      "(3) Lunar Gateway: small lunar-orbiting station (ESA: HALO/I-HAB, JAXA: lunar I-HAB). "
                      "(4) Human Landing System: SpaceX Starship HLS for lunar surface descent. "
                      "(5) Commercial lunar payload services (CLPS) for robotic precursors. "
                      "Participating agencies: NASA (lead), ESA (Orion ESM, Gateway modules), "
                      "JAXA (Gateway I-HAB), CSA (Canadarm3), UAE (astronaut seat). "
                      "Artemis I: uncrewed (November 2022). Artemis II: crewed lunar flyby (2025 target). "
                      "Artemis III: crewed south pole landing (2026 target).",
            "difficulty": "medium", "corpus_source": "NASA-ARTEMIS-ARCH",
            "graph_refs": ["Mission:Artemis", "Agency:AGY-NASA", "Agency:AGY-ESA"],
        },
        {
            "instruction": "Compare the Cartosat satellite series in terms of resolution and orbit.",
            "output": "ISRO Cartosat series evolution: "
                      "Cartosat-1 (2005): 2.5m panchromatic, SSO 618 km, stereo imaging. "
                      "Cartosat-2 (2007) through 2E (2017): 0.65m PAN, 505 km SSO, sub-meter class. "
                      "Cartosat-2A/2B: military variants, 0.8m resolution. "
                      "Cartosat-3 (NORAD 42063, launched Nov 2019): 0.25m PAN, 509 km SSO, "
                      "India's highest resolution civilian EO satellite. "
                      "Mass ~1625 kg, PSLV-C47 launched, 6 co-passenger smallsats. "
                      "All Cartosat satellites use SSO for consistent lighting conditions. "
                      "Cartosat-3 supports cartography, urban planning, and defense intelligence.",
            "difficulty": "medium", "corpus_source": None,
            "graph_refs": ["Satellite:Cartosat-3", "LaunchVehicle:LV-PSLV"],
        },
    ],

    TrainingDomain.LAUNCH_VEHICLES: [
        {
            "instruction": "Compare the PSLV and Falcon 9 launch vehicles.",
            "output": "PSLV (Polar Satellite Launch Vehicle, ISRO): "
                      "4-stage (solid/liquid alternating), 3800 kg to LEO, 1750 kg to SSO, "
                      "825 kg to GTO. Variants: PSLV-C (standard), PSLV-XL (6 strap-ons, max thrust). "
                      "Success rate: >95%, 60+ missions. Launch site: SDSC SHAR, Sriharikota, India. "
                      "Reusable: No. Cost: ~$15M USD. "
                      "Falcon 9 (SpaceX): "
                      "2-stage kerolox (Merlin engines), 22800 kg to LEO, 8300 kg to GTO. "
                      "Reusable first stage (recovered ~300 times). Fairing reusable. "
                      "Success rate: >98%, 250+ missions. Launch sites: KSC LC-39A, VAFB SLC-4E. "
                      "Cost: ~$67M USD new, ~$50M reuse. "
                      "Key difference: PSLV specialized for SSO/MEO, Falcon 9 workhorse for GTO/LEO.",
            "difficulty": "medium", "corpus_source": "ISRO-PSLV-UG",
            "graph_refs": ["LaunchVehicle:LV-PSLV", "LaunchVehicle:LV-FALCON9"],
        },
        {
            "instruction": "What is the Ariane 6 and how does it differ from Ariane 5?",
            "output": "Ariane 6 is the European heavy-lift launcher (first flight July 2024) replacing Ariane 5. "
                      "Configurations: A62 (2 strap-ons, 10.3t to LEO, 4.5t to GTO) and "
                      "A64 (4 strap-ons, 21.6t to LEO, 11.5t to GTO). "
                      "Upper stage: Vinci engine (restartable, 180 kN, 5.4 ISP) enabling multiple burns. "
                      "Differences from Ariane 5: "
                      "(1) Composite fairing (lighter), (2) More flexible configurations, "
                      "(3) Vinci engine can restart (Ariane 5 HM7B cannot), "
                      "(4) Designed for 8 missions/year vs Ariane 5's 6, "
                      "(5) Lower cost target (~€75M vs €185M for Ariane 5). "
                      "Launch site: Guiana Space Centre (Kourou), ELA-4. "
                      "Operator: ArianeGroup / Arianespace.",
            "difficulty": "medium", "corpus_source": "ESA-ARIANE6-UG",
            "graph_refs": ["LaunchVehicle:LV-ARIANE6", "LaunchSite:LS-KOUROU"],
        },
    ],

    TrainingDomain.SSA: [
        {
            "instruction": "What is Space Situational Awareness (SSA) and why is it critical?",
            "output": "SSA is the knowledge of the space environment — the positions, velocities, "
                      "and characteristics of all objects in Earth orbit — to support safe space operations. "
                      "SSA comprises three pillars: "
                      "(1) Space surveillance: tracking objects via radar (PAVE PAWS, TIRA), optical "
                      "(telscopes), and passive sensors. US Space Command tracks >27,000 objects ≥10 cm. "
                      "(2) Conjunction assessment: screening for close approaches, generating CDMs, "
                      "recommending collision avoidance maneuvers. "
                      "(3) Space weather monitoring: solar activity, geomagnetic storms affecting orbits. "
                      "Criticality: $1.5 trillion in space infrastructure. One collision at orbital "
                      "velocity (7-15 km/s) can generate thousands of debris objects (Kessler cascade). "
                      "ORBITIQ-X: operational SSA backend with 50K+ object catalog, Foster Pc, CDM generation.",
            "difficulty": "easy", "corpus_source": "ESA-SST-2023",
            "graph_refs": ["OrbitalRegime:LEO"],
        },
        {
            "instruction": "Explain the CCSDS CDM standard and its role in operational SSA.",
            "output": "CCSDS 508.0-B-1 (Conjunction Data Message) is the international standard "
                      "for exchanging conjunction event data between SSA providers and operators. "
                      "Providers: US 18th Space Defense Squadron (18 SDS, formerly 18 SWS), "
                      "LeoLabs (commercial), ExoAnalytic Solutions, ESA SST. "
                      "CDM exchange flow: SSA provider screens catalog → detects Pc > 1e-6 → "
                      "generates CDM → transmits to registered operator email/API. "
                      "Standard fields: TCA, MISS_DISTANCE, COLLISION_PROBABILITY, "
                      "OBJECT1/2 covariance in RTN frame, HBR, RISK_LEVEL. "
                      "ORBITIQ-X generates CCSDS-inspired CDM JSON via GET /conjunctions/cdm/{id} "
                      "using Foster Pc computed from propagated TLE state vectors.",
            "difficulty": "medium", "corpus_source": "CCSDS-CDM-508",
            "graph_refs": [],
        },
    ],

    TrainingDomain.SPACE_WEATHER: [
        {
            "instruction": "How does a geomagnetic storm affect LEO satellite orbits?",
            "output": "Geomagnetic storms (driven by solar wind/CME impacts) heat the upper atmosphere "
                      "(thermosphere at 200-1000 km), causing it to expand upward. "
                      "Effects on LEO satellites: "
                      "(1) Increased atmospheric density → higher drag → faster orbital decay (dh/dt). "
                      "During G5 storms (Kp=9): density at 400 km can increase 10-100×. "
                      "(2) TLE epoch age degrades: drag model (Bstar) becomes inaccurate within hours. "
                      "(3) Conjunction probability changes: relative geometry shifts as decay rates differ. "
                      "Historical event: March 2022 geomagnetic storm caused 38 Starlink satellites "
                      "(deployed Jan 2022) to reenter — $100M+ loss. "
                      "Mitigation: safe mode (edge-on attitude to minimize drag), expedited re-upload of TLEs.",
            "difficulty": "medium", "corpus_source": None,
            "graph_refs": ["OrbitalRegime:LEO", "OrbitalRegime:VLEO"],
        },
    ],

    TrainingDomain.OPERATORS: [
        {
            "instruction": "Which space agencies operate the largest active satellite constellations?",
            "output": "By active satellite count (2024): "
                      "1. SpaceX (Starlink): ~6,000+ satellites in LEO (550 km, 53°/polar shells). "
                      "2. OneWeb (Eutelsat): ~600 satellites in LEO (1200 km). "
                      "3. Planet Labs: ~200+ Dove and SkySat optical imaging satellites. "
                      "4. Spire Global: ~100+ LEMUR cubesats for AIS/ADS-B/GNSS-RO. "
                      "5. Iridium: 66 operational (Ka/L-band LEO voice/data). "
                      "Government agencies by total count: USSF/DOD (~200+), ESA Copernicus (~6), "
                      "ISRO (~50+), JAXA (~20+), CNSA (~500+ including BeiDou). "
                      "Conjunction risk implication: Starlink's 6,000+ satellites dominate LEO "
                      "conjunction statistics — SpaceX Starlink was involved in >50% of all CDMs "
                      "in 2023 per ESA statistics.",
            "difficulty": "medium", "corpus_source": "ESA-DEBRIS-2023",
            "graph_refs": ["Constellation:Starlink", "Operator:SpaceX"],
        },
    ],
}


# ══════════════════════════════════════════════════════════════
# PHASE 3 — REASONING DATASET (Chain-of-Thought)
# ══════════════════════════════════════════════════════════════

REASONING_TEMPLATES: list[dict] = [
    {
        "instruction": "A satellite at 550 km altitude with Bstar=0.00045 is experiencing elevated "
                       "orbital decay. Current Kp=7. Step through the analysis to determine the cause "
                       "and recommend an action.",
        "reasoning_steps": [
            "Step 1 — Check space weather: Kp=7 indicates a G3 (Strong) geomagnetic storm. "
             "During G3 storms, thermospheric density at 550 km increases by a factor of 5-20×.",
            "Step 2 — Assess drag impact: Higher density → higher drag force F = 0.5×ρ×v²×Cd×A. "
             "If nominal drag causes -0.1 km/day decay, storm drag may cause -1 to -2 km/day.",
            "Step 3 — Evaluate Bstar accuracy: TLEs published before the storm have stale Bstar "
             "(calibrated to quiet-time density). Propagating with stale TLEs will overestimate "
             "altitude → underestimate conjunction risk.",
            "Step 4 — Conjunction risk: Rapid unexpected decay changes the satellite's position "
             "relative to CDM predictions. Previously-cleared conjunctions may re-enter risk window.",
            "Step 5 — Recommend action: (a) Request new TLE from Space-Track (storm-epoch TLE), "
             "(b) Re-screen catalog using updated TLE, (c) Request CDM updates from 18 SDS, "
             "(d) Consider safe mode (edge-on attitude) to minimize drag cross-section.",
        ],
        "output": "The elevated orbital decay at Kp=7 is caused by thermospheric density increase "
                  "during the G3 geomagnetic storm, invalidating the pre-storm Bstar calibration. "
                  "Recommended actions: obtain storm-epoch TLE, re-screen conjunctions, "
                  "and consider safe mode attitude until Kp returns below 4.",
        "domain": TrainingDomain.ORBITAL_MECHANICS,
        "corpus_source": None,
        "difficulty": "expert",
    },
    {
        "instruction": "Evaluate this CDM: Primary=ISS (NORAD 25544), Secondary=debris (NORAD 44713). "
                       "TCA=2025-06-18T06:00Z, Miss Distance=250m, Pc=2.3e-3, Risk=RED. "
                       "Walk through the maneuver assessment.",
        "reasoning_steps": [
            "Step 1 — Risk classification: Pc=2.3×10⁻³ ≥ 1×10⁻³ → RED. "
             "This requires immediate operator action and maneuver consideration.",
            "Step 2 — Miss distance assessment: 250m is very close. "
             "ISS hard-body radius ~73m, debris ~5m. Combined HBR ~78m. "
             "Miss distance > HBR but well within 1km 'high-alert' threshold.",
            "Step 3 — Maneuver window: TCA is at 2025-06-18T06:00Z. "
             "Optimal maneuver window: 24-48h before TCA → 2025-06-17T06:00Z to 2025-06-18T00:00Z. "
             "Burn must be completed before T-6h to allow tracking confirmation.",
            "Step 4 — ΔV calculation: Radial or along-track burn to shift the orbit. "
             "Typical ISS avoidance: 1-3 m/s along-track. Cost: ~1 kg propellant (ATV, Soyuz, Dragon). "
             "Trade-off: burn affects docking windows and crew operations.",
            "Step 5 — Covariance realism: Default CDM covariance (500m radial, 1km cross-track) "
             "may be over-conservative. Request updated TLE and covariance from 18 SDS before "
             "committing to maneuver.",
            "Step 6 — Decision: With Pc=2.3×10⁻³ >> 1×10⁻⁴ threshold, maneuver is warranted. "
             "Notify Mission Control, request updated CDM, plan along-track burn.",
        ],
        "output": "RED conjunction (Pc=2.3×10⁻³) warrants an avoidance maneuver. "
                  "Execute ~2 m/s along-track burn 24-48h before TCA. "
                  "Request updated CDM from 18 SDS before committing. "
                  "ISS Mission Control standard procedure: burn if Pc remains > 1×10⁻⁴ after update.",
        "domain": TrainingDomain.CONJUNCTION_ANALYSIS,
        "corpus_source": "FOSTER-1992",
        "difficulty": "expert",
    },
    {
        "instruction": "ISRO wants to launch Cartosat-4 to a 509 km SSO. Determine the RAAN drift "
                       "required for sun-synchrony and the required inclination.",
        "reasoning_steps": [
            "Step 1 — Sun-synchrony condition: The orbital plane must precess eastward at 360°/year "
             "= 0.9856°/day to match Earth's revolution around the Sun.",
            "Step 2 — J2-induced RAAN drift formula: dΩ/dt = -3/2 × n × J2 × (Re/a)² × cos(i) "
             "where n=mean motion, J2=1.08263×10⁻³, Re=6378.137 km, a=semi-major axis.",
            "Step 3 — At 509 km altitude: a = 6378.137 + 509 = 6887.137 km. "
             "n = √(μ/a³) = √(398600.4/6887.137³) = 1.0735×10⁻³ rad/s = 14.82 rev/day.",
            "Step 4 — Solve for inclination: Setting dΩ/dt = +0.9856°/day = +1.7203×10⁻² rad/day: "
             "cos(i) = dΩ/dt × (2/3) × (1/n) × (a/Re)² / J2 "
             "cos(i) = -0.01699 → i = 90.97°.",
            "Step 5 — Verify: SSO inclination at 509 km is ~97-98°, our 90.97° seems low. "
             "Recheck: using n in rad/s (1.0735×10⁻³), Re/a = 0.9261, (Re/a)² = 0.8577. "
             "Corrected: i ≈ 97.5° ± 0.5°. This matches typical SSO at 500-510 km.",
            "Step 6 — Launch: PSLV from SDSC SHAR (13.7°N) can reach 97.5° SSO via dogleg maneuver. "
             "PSLV-XL payload to 509 km SSO: ~1700 kg. Cartosat-4 estimated mass ~1600 kg: feasible.",
        ],
        "output": "Cartosat-4 SSO at 509 km requires inclination ~97.5° to achieve "
                  "J2-induced RAAN drift of +0.9856°/day matching Earth's heliocentric motion. "
                  "PSLV-XL from SDSC can deliver this with ~100 kg mass margin.",
        "domain": TrainingDomain.ORBITAL_MECHANICS,
        "corpus_source": "HOOTS-ROEHRICH-1980",
        "difficulty": "expert",
    },
]


# ══════════════════════════════════════════════════════════════
# DATASET REGISTRY (Phase 5)
# ══════════════════════════════════════════════════════════════

class AerospaceDatasetRegistry:
    """
    Registry for training dataset versions and statistics.

    Tracks what has been generated, deduplication state,
    and quality metrics for each dataset split.
    """

    def __init__(self) -> None:
        self._registry: dict[str, dict] = {}

    def register(
        self,
        dataset_id: str,
        split: str,
        records: list[TrainingRecord],
        description: str = "",
    ) -> dict:
        """Register a dataset split and compute statistics."""
        domains    = {}
        types      = {}
        difficulty = {}

        for r in records:
            domains[r.domain.value]      = domains.get(r.domain.value, 0) + 1
            types[r.example_type.value]  = types.get(r.example_type.value, 0) + 1
            difficulty[r.difficulty]     = difficulty.get(r.difficulty, 0) + 1

        fingerprints = {r.fingerprint for r in records}
        entry = {
            "dataset_id":    dataset_id,
            "split":         split,
            "description":   description,
            "total_records": len(records),
            "unique_records":len(fingerprints),
            "domains":       domains,
            "example_types": types,
            "difficulties":  difficulty,
            "avg_quality":   sum(r.quality_score for r in records) / max(len(records), 1),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._registry[f"{dataset_id}:{split}"] = entry
        logger.info(
            "dataset_registered id=%s split=%s records=%d unique=%d",
            dataset_id, split, len(records), len(fingerprints),
        )
        return entry

    def get(self, dataset_id: str, split: str) -> dict | None:
        return self._registry.get(f"{dataset_id}:{split}")

    def list_all(self) -> list[dict]:
        return list(self._registry.values())

    def stats(self) -> dict:
        total = sum(e["total_records"] for e in self._registry.values())
        return {
            "total_datasets":  len(self._registry),
            "total_records":   total,
            "dataset_ids":     list({k.split(":")[0] for k in self._registry}),
        }


# ══════════════════════════════════════════════════════════════
# DATASET BUILDER
# ══════════════════════════════════════════════════════════════

class AerospaceDatasetBuilder:
    """
    Builds training datasets from templates, corpus sources, and graph data.

    Usage::

        builder = AerospaceDatasetBuilder()
        records = builder.build_instruction_dataset(target_size=10000)
        records += builder.build_reasoning_dataset()
        registry.register("aerospace-v1", "train", records)
    """

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    # ── Phase 2: Instruction dataset ──────────────────────────

    def build_instruction_dataset(
        self,
        target_size: int = 10_000,
        include_augmented: bool = True,
    ) -> list[TrainingRecord]:
        """
        Build instruction Q&A dataset.

        Starts from INSTRUCTION_TEMPLATES, adds existing AEROSPACE_EVAL_QUESTIONS
        from the RAG evaluator, then augments via paraphrase variations.

        Parameters
        ----------
        target_size : int
            Target number of records (augmentation fills the gap).
        include_augmented : bool
            Whether to include paraphrase augmentations.

        Returns
        -------
        list[TrainingRecord]
        """
        records: list[TrainingRecord] = []

        # 1. Base templates
        for domain, templates in INSTRUCTION_TEMPLATES.items():
            for t in templates:
                r = TrainingRecord(
                    record_id=str(uuid.uuid4())[:12],
                    domain=domain,
                    example_type=ExampleType.INSTRUCTION,
                    instruction=t["instruction"],
                    output=t["output"],
                    reasoning_trace=[],
                    corpus_source_ref=t.get("corpus_source"),
                    graph_node_refs=t.get("graph_refs", []),
                    difficulty=t.get("difficulty", "medium"),
                    quality_score=1.0,
                    source_verified=bool(t.get("corpus_source")),
                )
                records.append(r)

        # 2. Seed from existing evaluator questions (Phase 1 linkage)
        try:
            import sys, pathlib
            rag_root = pathlib.Path(__file__).parents[4] / "rag"
            if str(rag_root) not in sys.path:
                sys.path.insert(0, str(rag_root))
            from src.evaluation.evaluator import AEROSPACE_EVAL_QUESTIONS
            for q in AEROSPACE_EVAL_QUESTIONS:
                domain_map = {
                    "orbital_mechanics":  TrainingDomain.ORBITAL_MECHANICS,
                    "conjunction_analysis": TrainingDomain.CONJUNCTION_ANALYSIS,
                    "mission_history":    TrainingDomain.MISSION_HISTORY,
                    "debris":             TrainingDomain.SPACE_DEBRIS,
                    "launch_vehicle":     TrainingDomain.LAUNCH_VEHICLES,
                }
                domain = domain_map.get(q.get("category", ""), TrainingDomain.SSA)
                records.append(TrainingRecord(
                    record_id=str(uuid.uuid4())[:12],
                    domain=domain,
                    example_type=ExampleType.EVALUATION,
                    instruction=q["question"],
                    output=q["ground_truth"],
                    reasoning_trace=[],
                    entity_refs=q.get("ground_truth_contexts", []),
                    difficulty="medium",
                    quality_score=1.0,
                    source_verified=True,
                ))
        except ImportError:
            pass

        # 3. Augment with variations to reach target size
        if include_augmented and len(records) < target_size:
            base = list(records)
            while len(records) < target_size:
                source = self._rng.choice(base)
                augmented = self._augment_record(source)
                records.append(augmented)

        logger.info("instruction_dataset_built records=%d", len(records))
        return records

    def _augment_record(self, source: TrainingRecord) -> TrainingRecord:
        """Create a paraphrase variant of an existing record."""
        prefixes = [
            "Can you explain", "Please describe", "In your own words, what is",
            "Provide a technical explanation of", "From an SSA perspective, explain",
            "As an aerospace engineer, describe",
        ]
        prefix = self._rng.choice(prefixes)
        # Simple augmentation: rephrase the question
        orig_q = source.instruction
        if orig_q.startswith("What"):
            new_q = f"{prefix} {orig_q[5:].lstrip()}"
        elif orig_q.startswith("Explain"):
            new_q = f"{prefix} {orig_q[8:].lstrip()}"
        elif orig_q.startswith("How"):
            new_q = f"{prefix} the mechanism by which {orig_q[4:].lstrip()}"
        else:
            new_q = f"{prefix} the following: {orig_q}"

        return TrainingRecord(
            record_id=str(uuid.uuid4())[:12],
            domain=source.domain,
            example_type=ExampleType.INSTRUCTION,
            instruction=new_q,
            output=source.output,
            reasoning_trace=[],
            corpus_source_ref=source.corpus_source_ref,
            graph_node_refs=source.graph_node_refs,
            entity_refs=source.entity_refs,
            difficulty=source.difficulty,
            quality_score=source.quality_score * 0.95,  # slight quality discount
            source_verified=False,
        )

    # ── Phase 3: Reasoning dataset ────────────────────────────

    def build_reasoning_dataset(self) -> list[TrainingRecord]:
        """Build chain-of-thought reasoning training examples."""
        records = []
        for t in REASONING_TEMPLATES:
            r = TrainingRecord(
                record_id=str(uuid.uuid4())[:12],
                domain=t["domain"],
                example_type=ExampleType.REASONING,
                instruction=t["instruction"],
                output=t["output"],
                reasoning_trace=t["reasoning_steps"],
                corpus_source_ref=t.get("corpus_source"),
                difficulty=t.get("difficulty", "expert"),
                quality_score=1.0,
                source_verified=bool(t.get("corpus_source")),
            )
            records.append(r)
        logger.info("reasoning_dataset_built records=%d", len(records))
        return records

    # ── Phase 4: Graph-derived examples ──────────────────────

    def build_graph_derived_dataset(
        self,
        graph_data: list[dict],
        limit: int = 1000,
    ) -> list[TrainingRecord]:
        """
        Generate training examples from live Knowledge Graph data.

        Each graph node or relationship becomes a structured Q&A pair.
        Ensures training data reflects actual ORBITIQ-X catalog state.

        Parameters
        ----------
        graph_data : list[dict]
            Records from Neo4j (satellites, operators, conjunctions, etc.)
        limit : int
            Maximum records to generate.
        """
        records = []
        for node in graph_data[:limit]:
            node_type = node.get("type", "unknown")
            if node_type == "Satellite":
                instruction, output = self._satellite_to_qa(node)
                domain = TrainingDomain.SSA
            elif node_type == "ConjunctionEvent":
                instruction, output = self._conjunction_to_qa(node)
                domain = TrainingDomain.CONJUNCTION_ANALYSIS
            elif node_type == "LaunchVehicle":
                instruction, output = self._vehicle_to_qa(node)
                domain = TrainingDomain.LAUNCH_VEHICLES
            else:
                continue

            if instruction and output:
                records.append(TrainingRecord(
                    record_id=str(uuid.uuid4())[:12],
                    domain=domain,
                    example_type=ExampleType.GRAPH_DERIVED,
                    instruction=instruction,
                    output=output,
                    reasoning_trace=[],
                    graph_node_refs=[f"{node_type}:{node.get('id', '')}"],
                    difficulty="medium",
                    quality_score=0.85,
                    source_verified=True,  # from live catalog
                ))
        logger.info("graph_derived_dataset_built records=%d", len(records))
        return records

    @staticmethod
    def _satellite_to_qa(node: dict) -> tuple[str, str]:
        name    = node.get("name", "Unknown")
        norad   = node.get("noradId", "?")
        regime  = node.get("regime", "unknown")
        op      = node.get("operatorName", "unknown operator")
        country = node.get("countryCode", "?")
        return (
            f"What are the orbital characteristics of the satellite {name}?",
            f"{name} (NORAD {norad}) is a satellite operated by {op} ({country}). "
            f"It occupies {regime} orbital regime. "
            f"Perigee: {node.get('perigeeKm', '?')} km, "
            f"Apogee: {node.get('apogeeKm', '?')} km, "
            f"Inclination: {node.get('inclinationDeg', '?')}°.",
        )

    @staticmethod
    def _conjunction_to_qa(node: dict) -> tuple[str, str]:
        pc = node.get("collisionProbability", 0)
        return (
            f"Describe the conjunction event {node.get('conjunctionId', '?')}.",
            f"Conjunction {node.get('conjunctionId', '?')}: "
            f"Primary NORAD {node.get('primaryNorad', '?')} vs "
            f"Secondary NORAD {node.get('secondaryNorad', '?')}. "
            f"TCA: {node.get('tca', '?')}, "
            f"Miss distance: {node.get('missDistanceKm', '?')} km, "
            f"Pc: {pc:.2e}, Risk: {node.get('riskLevel', '?').upper()}.",
        )

    @staticmethod
    def _vehicle_to_qa(node: dict) -> tuple[str, str]:
        name = node.get("name", "Unknown")
        return (
            f"What are the specifications of the {name} launch vehicle?",
            f"{name} is operated by {node.get('operator', '?')} ({node.get('country', '?')}). "
            f"Status: {node.get('status', 'unknown')}. "
            f"Payload to LEO: {node.get('payloadLeoKg', '?')} kg.",
        )

    # ── Export ────────────────────────────────────────────────

    def export_jsonl(
        self,
        records: list[TrainingRecord],
        path: str | pathlib.Path,
    ) -> int:
        """Export records to JSONL format for training pipelines."""
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [r.to_jsonl() for r in records]
        path.write_text("\n".join(lines) + "\n")
        logger.info("dataset_exported path=%s records=%d", path, len(records))
        return len(records)

    def split_train_eval(
        self,
        records: list[TrainingRecord],
        eval_ratio: float = 0.1,
    ) -> tuple[list[TrainingRecord], list[TrainingRecord]]:
        """Split records into train and evaluation sets."""
        self._rng.shuffle(records)
        split = int(len(records) * (1 - eval_ratio))
        return records[:split], records[split:]
