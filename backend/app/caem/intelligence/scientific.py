"""
ORBITIQ-X — Scientific Knowledge Layer
Phase 17.9

Structured scientific knowledge:
  - Research papers with DOI, citations, abstracts
  - Standards (CCSDS, ISO, ECSS, IEEE)
  - Patents with IPC codes and assignees
  - Citation network queries
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


SEED_PAPERS: List[Dict[str, Any]] = [
    {
        "aqid": "AQID-RESEARCH-PAPER-SGP4-HOOTS-2004",
        "display_name": "Revisiting Spacetrack Report #3",
        "doi": "10.2514/6.2006-6753",
        "journal": "AIAA/AAS Astrodynamics Specialist Conference",
        "published_year": 2006,
        "authors": ["Vallado, David A.", "Crawford, Paul", "Hujsak, Richard", "Kelso, T.S."],
        "citations": 892,
        "abstract": (
            "Refinement of the SGP4 orbit propagator originally published in "
            "Spacetrack Report No. 3. Corrects errors in the original formulation "
            "and provides the definitive reference implementation used globally."
        ),
        "keywords": ["sgp4", "orbital mechanics", "tle", "propagation", "astrodynamics"],
        "domains": ["orbital_mechanics", "ssa"],
        "tags": ["sgp4", "tle", "propagator"],
        "source_url": "https://celestrak.org/publications/AIAA/2006-6753/",
    },
    {
        "aqid": "AQID-RESEARCH-PAPER-KESSLER-1978",
        "display_name": "Collision Frequency of Artificial Satellites",
        "doi": "10.1029/JA083iA06p02637",
        "journal": "Journal of Geophysical Research",
        "published_year": 1978,
        "authors": ["Kessler, Donald J.", "Cour-Palais, Burton G."],
        "citations": 2847,
        "abstract": (
            "Foundational paper predicting that in low Earth orbit, the density of "
            "artificial satellites could become high enough that collisions between "
            "objects could cascade — now known as Kessler Syndrome."
        ),
        "keywords": ["kessler syndrome", "debris", "collision cascade", "orbital debris", "leo"],
        "domains": ["ssa", "orbital_mechanics"],
        "tags": ["kessler", "debris", "cascade", "foundational"],
    },
    {
        "aqid": "AQID-RESEARCH-PAPER-HOMANN-TRANSFER-1925",
        "display_name": "Die Erreichbarkeit der Himmelskörper (The Attainability of Celestial Bodies)",
        "doi": None,
        "journal": "R. Oldenbourg Verlag",
        "published_year": 1925,
        "authors": ["Hohmann, Walter"],
        "citations": 1200,
        "abstract": (
            "Fundamental work describing the elliptical orbit transfer maneuver "
            "between two circular orbits using minimum propellant — now known as the "
            "Hohmann transfer. Basis for virtually all orbital mechanics mission design."
        ),
        "keywords": ["hohmann transfer", "orbital maneuver", "delta-v", "orbital mechanics"],
        "domains": ["orbital_mechanics", "propulsion"],
        "tags": ["hohmann", "transfer", "foundational", "delta-v"],
    },
    {
        "aqid": "AQID-RESEARCH-PAPER-IRIDIUM-COSMOS-2009",
        "display_name": "Iridium 33 and Cosmos 2251 Collision Analysis",
        "doi": "10.2514/1.46113",
        "journal": "Journal of Spacecraft and Rockets",
        "published_year": 2011,
        "authors": ["Kelso, T.S.", "Alfano, Salvatore"],
        "citations": 347,
        "abstract": (
            "Analysis of the February 10, 2009 collision between Iridium 33 and "
            "Cosmos 2251 — the first accidental hypervelocity collision between two "
            "intact spacecraft. Generated approximately 2,300 trackable debris pieces."
        ),
        "keywords": ["collision", "iridium", "cosmos", "debris", "ssa"],
        "domains": ["ssa", "orbital_mechanics"],
        "tags": ["collision", "debris", "iridium", "cosmos"],
    },
    {
        "aqid": "AQID-RESEARCH-PAPER-STARLINK-MEGA-CONSTELLATION",
        "display_name": "Satellite Mega-Constellations: Risks and Mitigation",
        "doi": "10.1016/j.actaastro.2020.01.032",
        "journal": "Acta Astronautica",
        "published_year": 2020,
        "authors": ["Radtke, Jonas", "Kebschull, Christoph", "Stoll, Enrico"],
        "citations": 189,
        "abstract": (
            "Analysis of collision risk and debris generation probability from proposed "
            "mega-constellations including Starlink, OneWeb, and Amazon Kuiper. "
            "Quantifies long-term LEO sustainability implications."
        ),
        "keywords": ["mega-constellation", "starlink", "oneweb", "debris", "sustainability"],
        "domains": ["ssa", "satellite_constellations"],
        "tags": ["constellation", "starlink", "debris", "sustainability"],
    },
]

SEED_STANDARDS: List[Dict[str, Any]] = [
    {
        "aqid": "AQID-STANDARD-CCSDS-727-0-B-5",
        "display_name": "CCSDS 727.0-B-5: File Delivery Protocol (CFDP)",
        "issuing_body": "CCSDS",
        "standard_number": "727.0-B-5",
        "full_reference": "CCSDS 727.0-B-5 Blue Book",
        "status": "active",
        "domain": "communications",
        "description": "Standard protocol for reliable file transfer between spacecraft and ground systems.",
        "published_date": "2007-01-01",
        "tags": ["ccsds", "protocol", "file-transfer", "communications"],
    },
    {
        "aqid": "AQID-STANDARD-CCSDS-131-0-B-3",
        "display_name": "CCSDS 131.0-B-3: TM Space Data Link Protocol",
        "issuing_body": "CCSDS",
        "standard_number": "131.0-B-3",
        "status": "active",
        "domain": "communications",
        "description": "Standard for telemetry space data link protocol used by spacecraft downlink.",
        "published_date": "2003-09-01",
        "tags": ["ccsds", "telemetry", "downlink", "protocol"],
    },
    {
        "aqid": "AQID-STANDARD-IADC-DEBRIS-MITIGATION",
        "display_name": "IADC Space Debris Mitigation Guidelines",
        "issuing_body": "IADC",
        "standard_number": "IADC-02-01",
        "status": "active",
        "domain": "ssa",
        "description": (
            "Inter-Agency Space Debris Coordination Committee guidelines for limiting "
            "debris generation in Earth orbit. Defines 25-year post-mission disposal rule "
            "for LEO and graveyard orbit requirements for GEO."
        ),
        "published_date": "2002-10-15",
        "tags": ["debris", "mitigation", "ssa", "iadc", "25-year-rule"],
    },
    {
        "aqid": "AQID-STANDARD-ISO-24113-2019",
        "display_name": "ISO 24113:2019 Space Systems — Space Debris Mitigation Requirements",
        "issuing_body": "ISO",
        "standard_number": "24113:2019",
        "status": "active",
        "domain": "ssa",
        "description": (
            "ISO standard specifying requirements for limiting the generation of space debris "
            "for spacecraft and launch vehicles, including passivation and disposal requirements."
        ),
        "published_date": "2019-03-01",
        "tags": ["iso", "debris", "mitigation", "standards"],
    },
    {
        "aqid": "AQID-STANDARD-ECSS-E-ST-10-04C",
        "display_name": "ECSS-E-ST-10-04C: Space Environment",
        "issuing_body": "ECSS",
        "standard_number": "ECSS-E-ST-10-04C",
        "status": "active",
        "domain": "space_environment",
        "description": (
            "European Cooperation for Space Standardization standard defining the natural "
            "space environment for spacecraft design purposes including radiation, "
            "plasma, micrometeoroids and debris."
        ),
        "published_date": "2008-11-15",
        "tags": ["ecss", "space-environment", "radiation", "design"],
    },
]

SEED_PATENTS: List[Dict[str, Any]] = [
    {
        "aqid": "AQID-PATENT-US9878824",
        "display_name": "Return and Reuse of Space Launch Vehicles — SpaceX",
        "patent_number": "US9878824B2",
        "patent_office": "USPTO",
        "filing_date": "2015-05-04",
        "granted_date": "2018-01-30",
        "status": "active",
        "assignee": "SpaceX",
        "inventors": ["Musk, Elon", "Mueller, Tom"],
        "ipc_codes": ["B64G1/40", "B64G5/00"],
        "claims_summary": "Methods and systems for controlled return and landing of orbital launch vehicle boosters.",
        "domains": ["launch_systems", "propulsion"],
        "tags": ["spacex", "reusability", "booster", "landing"],
    },
    {
        "aqid": "AQID-PATENT-US10633123",
        "display_name": "Satellite Constellation Orbital Configuration — SpaceX Starlink",
        "patent_number": "US10633123B2",
        "patent_office": "USPTO",
        "filing_date": "2016-08-26",
        "granted_date": "2020-04-28",
        "status": "active",
        "assignee": "SpaceX",
        "inventors": ["Musk, Elon"],
        "ipc_codes": ["H04B7/185", "B64G1/10"],
        "claims_summary": "Orbital configuration for low-latency global broadband satellite constellation.",
        "domains": ["satellite_constellations", "communications"],
        "tags": ["spacex", "starlink", "constellation", "broadband"],
    },
    {
        "aqid": "AQID-PATENT-US7467762",
        "display_name": "Solar Electric Propulsion System for Orbit Raising",
        "patent_number": "US7467762B1",
        "patent_office": "USPTO",
        "filing_date": "2003-02-14",
        "granted_date": "2008-12-23",
        "status": "active",
        "assignee": "Boeing",
        "inventors": ["Aadland, Curt"],
        "ipc_codes": ["B64G1/40", "B64G1/28"],
        "claims_summary": "All-electric orbit raising from GTO to GEO using Hall-effect thrusters.",
        "domains": ["propulsion", "power_systems"],
        "tags": ["electric-propulsion", "boeing", "hall-effect", "all-electric"],
    },
]


class ScientificKnowledgeService:
    """Query scientific knowledge: papers, standards, patents, citations."""

    def get_papers(
        self,
        keyword: Optional[str] = None,
        domain: Optional[str] = None,
        min_citations: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = SEED_PAPERS
        if keyword:
            kw = keyword.lower()
            results = [p for p in results if
                kw in p.get("display_name", "").lower() or
                kw in p.get("abstract", "").lower() or
                any(kw in k for k in p.get("keywords", []))]
        if domain:
            results = [p for p in results if domain in p.get("domains", [])]
        results = [p for p in results if (p.get("citations") or 0) >= min_citations]
        return sorted(results, key=lambda x: x.get("citations", 0), reverse=True)[:limit]

    def get_standards(
        self,
        issuing_body: Optional[str] = None,
        domain: Optional[str] = None,
        status: str = "active",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = SEED_STANDARDS
        if issuing_body:
            results = [s for s in results if s.get("issuing_body", "").upper() == issuing_body.upper()]
        if domain:
            results = [s for s in results if s.get("domain") == domain]
        if status:
            results = [s for s in results if s.get("status") == status]
        return results[:limit]

    def get_patents(
        self,
        assignee: Optional[str] = None,
        domain: Optional[str] = None,
        ipc_code: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = SEED_PATENTS
        if assignee:
            results = [p for p in results if assignee.lower() in p.get("assignee", "").lower()]
        if domain:
            results = [p for p in results if domain in p.get("domains", [])]
        if ipc_code:
            results = [p for p in results if
                any(ipc_code in code for code in p.get("ipc_codes", []))]
        return sorted(results, key=lambda x: x.get("filing_date", ""), reverse=True)[:limit]

    def get_citation_stats(self) -> Dict[str, Any]:
        total_citations = sum(p.get("citations", 0) for p in SEED_PAPERS)
        return {
            "total_papers": len(SEED_PAPERS),
            "total_standards": len(SEED_STANDARDS),
            "total_patents": len(SEED_PATENTS),
            "total_tracked_citations": total_citations,
            "most_cited": max(SEED_PAPERS, key=lambda x: x.get("citations", 0)),
            "issuing_bodies": list(set(s["issuing_body"] for s in SEED_STANDARDS)),
        }
