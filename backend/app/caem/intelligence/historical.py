"""
ORBITIQ-X — Historical Intelligence Layer
Phase 17.8

Structured historical knowledge for aerospace:
  - Space race and key era events
  - Major incidents and anomalies with root cause + lineage
  - Program and technology lineage chains (predecessor → successor)
  - Causal chains (incident → policy change)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


SEED_HISTORICAL_EVENTS: List[Dict[str, Any]] = [
    {
        "aqid": "AQID-HISTORICAL-EVENT-SPUTNIK-1957",
        "display_name": "Sputnik 1 Launch — Dawn of the Space Age",
        "date": "1957-10-04",
        "importance": "critical",
        "era": "SPACE_RACE",
        "description": (
            "The Soviet Union launched Sputnik 1, the first artificial Earth satellite. "
            "The 83.6 kg satellite transmitted a radio signal for 21 days, demonstrating "
            "Soviet launch capability and triggering the space race."
        ),
        "tags": ["space-race", "soviet", "satellite", "first"],
        "domains": ["orbital_mechanics", "ssa"],
        "linked_entities": ["AQID-SATELLITE-SPUTNIK-1", "AQID-COUNTRY-SU"],
        "caused_events": ["AQID-HISTORICAL-EVENT-NASA-FOUNDING-1958"],
    },
    {
        "aqid": "AQID-HISTORICAL-EVENT-NASA-FOUNDING-1958",
        "display_name": "NASA Founded",
        "date": "1958-10-01",
        "importance": "critical",
        "era": "SPACE_RACE",
        "description": (
            "The National Aeronautics and Space Administration was established by the "
            "National Aeronautics and Space Act, replacing NACA. Directly triggered by "
            "the Sputnik launch and growing Cold War tensions."
        ),
        "tags": ["nasa", "founding", "usa", "space-race"],
        "domains": ["human_spaceflight", "space_science"],
        "linked_entities": ["AQID-GOV-AGENCY-NASA"],
        "preceded_by": ["AQID-HISTORICAL-EVENT-SPUTNIK-1957"],
    },
    {
        "aqid": "AQID-HISTORICAL-EVENT-APOLLO-11-1969",
        "display_name": "Apollo 11 — First Crewed Lunar Landing",
        "date": "1969-07-20",
        "importance": "critical",
        "era": "SPACE_RACE",
        "description": (
            "Apollo 11 astronauts Neil Armstrong and Buzz Aldrin became the first humans "
            "to land on the Moon. Armstrong's first step at 02:56 UTC was watched live "
            "by approximately 600 million people worldwide."
        ),
        "tags": ["apollo", "moon", "nasa", "crewed", "first"],
        "domains": ["human_spaceflight", "lunar_exploration"],
        "linked_entities": ["AQID-MISSION-APOLLO-11", "AQID-GOV-AGENCY-NASA"],
    },
    {
        "aqid": "AQID-HISTORICAL-EVENT-CHALLENGER-1986",
        "display_name": "Space Shuttle Challenger Disaster",
        "date": "1986-01-28",
        "importance": "critical",
        "era": "SHUTTLE_ERA",
        "description": (
            "Space Shuttle Challenger broke apart 73 seconds after launch, killing all "
            "seven crew members. Root cause: O-ring failure in the right solid rocket "
            "booster, exacerbated by cold temperatures. Led to 32-month shuttle standdown "
            "and the Rogers Commission investigation."
        ),
        "tags": ["challenger", "shuttle", "disaster", "nasa"],
        "domains": ["human_spaceflight", "launch_systems"],
        "linked_entities": ["AQID-MISSION-STS-51-L", "AQID-GOV-AGENCY-NASA"],
        "caused_events": ["AQID-HISTORICAL-EVENT-ROGERS-COMMISSION-1986"],
        "root_cause": "O-ring failure in SRB joint at low temperature",
    },
    {
        "aqid": "AQID-HISTORICAL-EVENT-COLUMBIA-2003",
        "display_name": "Space Shuttle Columbia Disaster",
        "date": "2003-02-01",
        "importance": "critical",
        "era": "SHUTTLE_ERA",
        "description": (
            "Space Shuttle Columbia disintegrated during atmospheric re-entry, killing "
            "all seven crew members. Root cause: foam debris strike on leading edge of "
            "left wing during launch, causing thermal protection system breach. "
            "Resulted in the Columbia Accident Investigation Board (CAIB) report."
        ),
        "tags": ["columbia", "shuttle", "disaster", "nasa", "reentry"],
        "domains": ["human_spaceflight", "launch_systems"],
        "linked_entities": ["AQID-MISSION-STS-107", "AQID-GOV-AGENCY-NASA"],
        "root_cause": "Foam debris strike causing TPS breach on re-entry",
    },
    {
        "aqid": "AQID-HISTORICAL-EVENT-ISS-ASSEMBLY-1998",
        "display_name": "ISS Assembly Begins — Zarya Launch",
        "date": "1998-11-20",
        "importance": "major",
        "era": "POST_COLD_WAR",
        "description": (
            "Russia launched Zarya (FGB), the first module of the International Space "
            "Station. The ISS represents the largest peacetime international scientific "
            "collaboration, involving NASA, Roscosmos, ESA, JAXA, and CSA."
        ),
        "tags": ["iss", "zarya", "international", "assembly"],
        "domains": ["human_spaceflight"],
        "linked_entities": ["AQID-SATELLITE-ISS", "AQID-GOV-AGENCY-NASA", "AQID-GOV-AGENCY-ROSCOSMOS"],
    },
    {
        "aqid": "AQID-HISTORICAL-EVENT-COMMERCIAL-CREW-2020",
        "display_name": "First Commercial Crew Mission — SpaceX Demo-2",
        "date": "2020-05-30",
        "importance": "major",
        "era": "COMMERCIAL_ERA",
        "description": (
            "SpaceX Crew Dragon flew NASA astronauts Bob Behnken and Doug Hurley to the "
            "ISS — the first crewed orbital launch from US soil since the Space Shuttle "
            "retired in 2011 and the first by a commercial provider."
        ),
        "tags": ["spacex", "crew-dragon", "nasa", "commercial", "first"],
        "domains": ["human_spaceflight", "commercial"],
        "linked_entities": ["AQID-MISSION-DEMO-2", "AQID-COMPANY-SPACEX", "AQID-GOV-AGENCY-NASA"],
    },
]

SEED_INCIDENTS: List[Dict[str, Any]] = [
    {
        "aqid": "AQID-INCIDENT-ARIANE-5-FLIGHT-501",
        "display_name": "Ariane 5 Flight 501 — Software Failure",
        "date": "1996-06-04",
        "severity": "critical",
        "incident_type": "launch_failure",
        "description": (
            "Ariane 5 Flight 501 self-destructed 37 seconds after launch due to a software "
            "exception in the inertial reference system. Root cause: 64-bit floating-point "
            "to 16-bit integer conversion overflow — code reused unchanged from Ariane 4 "
            "without re-validation for the different trajectory."
        ),
        "root_cause": "Unhandled floating-point overflow in reused Ariane 4 software",
        "corrective_actions": [
            "Complete software re-validation for Ariane 5 trajectory",
            "Exception handling added to all inertial system paths",
            "Independent verification of software reuse assumptions",
        ],
        "financial_loss_musd": 370.0,
        "domains": ["launch_systems"],
        "tags": ["ariane", "software", "esa", "failure"],
    },
    {
        "aqid": "AQID-INCIDENT-MARS-CLIMATE-ORBITER-1999",
        "display_name": "Mars Climate Orbiter Loss — Units Mismatch",
        "date": "1999-09-23",
        "severity": "critical",
        "incident_type": "mission_failure",
        "description": (
            "NASA's Mars Climate Orbiter was lost on orbital insertion due to a units "
            "mismatch: Lockheed Martin's ground software output thrust data in pound-force "
            "seconds while the flight software expected newton-seconds. Cost: $327.6M."
        ),
        "root_cause": "Imperial vs SI units mismatch between ground and flight software",
        "corrective_actions": [
            "Mandatory SI units across all JPL mission software interfaces",
            "Interface requirements verification process enhanced",
            "Third-party code integration audit procedures mandated",
        ],
        "financial_loss_musd": 327.6,
        "domains": ["space_science", "guidance_nav"],
        "tags": ["nasa", "mars", "software", "units", "failure"],
    },
    {
        "aqid": "AQID-INCIDENT-FALCON-9-CRS-7-2015",
        "display_name": "Falcon 9 CRS-7 In-Flight Breakup",
        "date": "2015-06-28",
        "severity": "major",
        "incident_type": "launch_failure",
        "description": (
            "Falcon 9 carrying Dragon CRS-7 broke up 139 seconds after launch. "
            "Root cause: faulty 2-inch strut in the second stage liquid oxygen pressure "
            "vessel support structure that failed at 20% of rated load. "
            "Led to 6-month standdown and enhanced strut testing."
        ),
        "root_cause": "Defective strut supporting LOX pressurant vessel in second stage",
        "corrective_actions": [
            "All struts individually tested before flight",
            "Supplier quality audit",
            "Dual-redundant helium pressurant system",
        ],
        "financial_loss_musd": 260.0,
        "domains": ["launch_systems", "propulsion"],
        "tags": ["spacex", "falcon-9", "failure", "strut"],
    },
]

LINEAGE_CHAINS: List[Dict[str, Any]] = [
    {
        "id": "saturn-v-to-sls",
        "title": "Saturn V → SLS Lineage",
        "description": "Launch vehicle lineage from Apollo-era Saturn V to modern Space Launch System",
        "nodes": [
            {"aqid": "AQID-LAUNCH-VEHICLE-SATURN-V", "era": "1960s", "status": "retired"},
            {"aqid": "AQID-LAUNCH-VEHICLE-SPACE-SHUTTLE", "era": "1980-2011", "status": "retired"},
            {"aqid": "AQID-LAUNCH-VEHICLE-SLS", "era": "2022-present", "status": "active"},
        ],
        "relationship": "SUCCESSOR_OF",
    },
    {
        "id": "falcon1-to-starship",
        "title": "Falcon 1 → Falcon 9 → Starship Lineage",
        "description": "SpaceX launch vehicle evolution from Falcon 1 to Starship",
        "nodes": [
            {"aqid": "AQID-LAUNCH-VEHICLE-FALCON-1", "era": "2006-2009", "status": "retired"},
            {"aqid": "AQID-LAUNCH-VEHICLE-FALCON-9", "era": "2010-present", "status": "active"},
            {"aqid": "AQID-LAUNCH-VEHICLE-STARSHIP", "era": "2023-present", "status": "development"},
        ],
        "relationship": "EVOLVED_INTO",
    },
]


class HistoricalIntelligenceService:
    """Query and aggregate historical aerospace knowledge."""

    def get_events(
        self,
        era: Optional[str] = None,
        importance: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = SEED_HISTORICAL_EVENTS
        if era:
            results = [e for e in results if e.get("era") == era]
        if importance:
            results = [e for e in results if e.get("importance") == importance]
        if domain:
            results = [e for e in results if domain in e.get("domains", [])]
        return sorted(results, key=lambda x: x.get("date", ""), reverse=True)[:limit]

    def get_incidents(
        self,
        severity: Optional[str] = None,
        incident_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = SEED_INCIDENTS
        if severity:
            results = [i for i in results if i.get("severity") == severity]
        if incident_type:
            results = [i for i in results if i.get("incident_type") == incident_type]
        return sorted(results, key=lambda x: x.get("date", ""), reverse=True)[:limit]

    def get_lineage_chains(self) -> List[Dict[str, Any]]:
        return LINEAGE_CHAINS

    def get_eras(self) -> List[Dict[str, Any]]:
        return [
            {"era": "SPACE_RACE",       "period": "1957–1975", "description": "Soviet-US competition: Sputnik to Apollo"},
            {"era": "POST_APOLLO",      "period": "1975–1980", "description": "Apollo-Soyuz, Skylab, transition"},
            {"era": "SHUTTLE_ERA",      "period": "1981–2011", "description": "Space Shuttle operations"},
            {"era": "POST_COLD_WAR",    "period": "1990–2010", "description": "ISS construction, international cooperation"},
            {"era": "COMMERCIAL_ERA",   "period": "2010–present", "description": "Commercial crew, constellations, reusability"},
        ]
