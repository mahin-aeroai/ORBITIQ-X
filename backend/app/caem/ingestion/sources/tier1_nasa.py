"""
ORBITIQ-X — NASA Open APIs Source Adapter (Tier 1)
Phase 17.4

Fetches from NASA public APIs and data portals:
  - NASA TechPort: technology and project data
  - NASA Mission pages (structured JSON where available)
  - NSSDCA (National Space Science Data Center) catalog

All NASA data is Tier 1 (official government source).
NASA APIs are public and do not require authentication for most endpoints.
API key optional for higher rate limits.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

from caem.base import EntityClass
from caem.provenance.models import SourceTier
from caem.relationships import RelationshipType
from caem.ingestion.sources.base import SourceAdapter, SourceRecord

logger = logging.getLogger(__name__)

NASA_API_BASE   = "https://api.nasa.gov"
NASA_TECHPORT   = "https://techport.nasa.gov/api"
NSSDCA_BASE     = "https://nssdc.gsfc.nasa.gov"


class NASATechPortAdapter(SourceAdapter):
    """
    Adapter for NASA TechPort — technology project data.

    Yields Technology and Program SourceRecords.
    No authentication required; optional API key for rate-limit headroom.

    Config keys:
      api_key:    NASA API key (optional; uses DEMO_KEY if absent)
      max_pages:  Maximum pages to fetch (default: all)
    """
    source_name = "nasa_techport"
    source_tier = SourceTier.TIER_1_OFFICIAL
    fetch_interval_s = 86400 * 7  # Weekly (technology data changes slowly)

    # TechPort project status → lifecycle mapping
    STATUS_MAP = {
        "Active":       "operational",
        "Completed":    "archived",
        "Cancelled":    "deprecated",
        "Planned":      "planned",
    }

    def fetch(self) -> Generator[SourceRecord, None, None]:
        api_key = self.config.get("api_key", "DEMO_KEY")
        max_pages = self.config.get("max_pages", 999)

        page = 1
        while page <= max_pages:
            url = (
                f"{NASA_TECHPORT}/projects"
                f"?updatedSince=2010-01-01"
                f"&page={page}"
                f"&apiKey={api_key}"
            )
            data = self._fetch_json(url)
            if not data:
                break

            projects = data.get("projects", [])
            if not projects:
                break

            for proj in projects:
                record = self._parse_project(proj)
                if record:
                    yield record

            # Check if more pages exist
            total_pages = data.get("totalPages", 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(1)

    def _parse_project(self, proj: Dict) -> Optional[SourceRecord]:
        try:
            proj_id = str(proj.get("projectId", ""))
            title = proj.get("title", "").strip()
            if not title:
                return None

            # Technology or Program?
            if proj.get("programId"):
                entity_class = EntityClass.PROGRAM
            else:
                entity_class = EntityClass.TECHNOLOGY

            trl = proj.get("trlCurrent")
            fields: Dict[str, Any] = {
                "trl":          int(trl) if trl else None,
                "domain":       proj.get("primaryTaxonomyNodes", [{}])[0].get("title") if proj.get("primaryTaxonomyNodes") else None,
                "status":       self.STATUS_MAP.get(proj.get("statusDescription", ""), "unknown"),
                "developer_org": proj.get("responsibleMd", {}).get("acronym") if proj.get("responsibleMd") else None,
            }

            raw_rels = []
            if proj.get("responsibleMd", {}).get("acronym"):
                raw_rels.append({
                    "rel_type":     RelationshipType.GOVERNED_BY.value,
                    "target_name":  proj["responsibleMd"]["acronym"],
                    "target_class": EntityClass.GOV_AGENCY.value,
                    "confidence":   0.90,
                })

            return SourceRecord(
                source_id=f"techport-{proj_id}",
                source_system="nasa_techport",
                source_tier=SourceTier.TIER_1_OFFICIAL,
                source_url=f"{NASA_TECHPORT}/projects/{proj_id}",
                entity_class=entity_class,
                canonical_name=title,
                display_name=title,
                description=proj.get("description", "")[:500] if proj.get("description") else None,
                fields={k: v for k, v in fields.items() if v is not None},
                tags=["nasa", "technology"],
                domains=["technology"],
                raw_relationships=raw_rels,
            )
        except Exception as e:
            logger.warning(f"NASATechPort parse failed: {e}")
            return None

    def _fetch_json(self, url: str) -> Optional[Dict]:
        try:
            time.sleep(0.5)
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error(f"NASA fetch failed [{url[:80]}]: {e}")
            return None


class NASAMissionAdapter(SourceAdapter):
    """
    Adapter for curated NASA mission data.

    Since NASA does not have a single unified mission API, this adapter
    uses a curated list of well-known missions with structured data
    from public sources. Intended to seed the initial mission knowledge base
    before Tier 4 (Wikipedia/Encyclopedia Astronautica) ingestion runs.
    """
    source_name = "nasa_missions_curated"
    source_tier = SourceTier.TIER_1_OFFICIAL
    fetch_interval_s = 86400 * 30  # Monthly (mission list is stable)

    # Curated seed missions — extended by ingestion team over time
    SEED_MISSIONS: List[Dict[str, Any]] = [
        {
            "id": "artemis-i",
            "name": "Artemis I",
            "type": "crewed",
            "destination": "Moon",
            "agency": "NASA",
            "launch_date": "2022-11-16",
            "status": "complete",
            "description": "First integrated test of the Space Launch System and Orion spacecraft on an uncrewed lunar flyby.",
            "launch_vehicle": "Space Launch System",
            "domains": ["human_spaceflight", "lunar_exploration"],
        },
        {
            "id": "artemis-ii",
            "name": "Artemis II",
            "type": "crewed",
            "destination": "Moon",
            "agency": "NASA",
            "launch_date": None,
            "status": "planned",
            "description": "First crewed Artemis mission — lunar flyby with four crew members.",
            "launch_vehicle": "Space Launch System",
            "domains": ["human_spaceflight", "lunar_exploration"],
        },
        {
            "id": "jwst",
            "name": "James Webb Space Telescope",
            "type": "robotic",
            "destination": "L2",
            "agency": "NASA",
            "launch_date": "2021-12-25",
            "status": "operational",
            "description": "Infrared space observatory at the Sun-Earth L2 point. Joint NASA/ESA/CSA mission.",
            "launch_vehicle": "Ariane 5",
            "domains": ["space_science", "astrophysics"],
        },
        {
            "id": "perseverance",
            "name": "Mars 2020 Perseverance",
            "type": "robotic",
            "destination": "Mars",
            "agency": "NASA",
            "launch_date": "2020-07-30",
            "status": "operational",
            "description": "Mars rover seeking signs of ancient microbial life and collecting samples for future return.",
            "launch_vehicle": "Atlas V 541",
            "domains": ["space_science", "planetary_science"],
        },
        {
            "id": "dart",
            "name": "Double Asteroid Redirection Test",
            "type": "robotic",
            "destination": "Dimorphos",
            "agency": "NASA",
            "launch_date": "2021-11-24",
            "status": "complete",
            "description": "First planetary defense test mission. Successfully deflected asteroid Dimorphos on 2022-09-26.",
            "launch_vehicle": "Falcon 9",
            "domains": ["planetary_defense", "space_science"],
        },
        {
            "id": "iss",
            "name": "International Space Station",
            "type": "crewed",
            "destination": "LEO",
            "agency": "NASA",
            "launch_date": "1998-11-20",
            "status": "operational",
            "description": "Modular space station in low Earth orbit; international partnership of NASA, Roscosmos, ESA, JAXA, CSA.",
            "domains": ["human_spaceflight", "space_science"],
        },
        {
            "id": "voyager-1",
            "name": "Voyager 1",
            "type": "robotic",
            "destination": "Interstellar",
            "agency": "NASA",
            "launch_date": "1977-09-05",
            "status": "operational",
            "description": "Farthest human-made object from Earth. Entered interstellar space in 2012. Still transmitting.",
            "launch_vehicle": "Titan IIIE",
            "domains": ["space_science", "planetary_science"],
        },
        {
            "id": "hubble",
            "name": "Hubble Space Telescope",
            "type": "robotic",
            "destination": "LEO",
            "agency": "NASA",
            "launch_date": "1990-04-24",
            "status": "operational",
            "description": "Optical/UV/near-IR space telescope in low Earth orbit. Serviced five times by Space Shuttle crews.",
            "launch_vehicle": "Space Shuttle Discovery",
            "domains": ["space_science", "astrophysics"],
        },
    ]

    def fetch(self) -> Generator[SourceRecord, None, None]:
        for mission in self.SEED_MISSIONS:
            record = self._parse_mission(mission)
            if record:
                yield record

    def _parse_mission(self, m: Dict) -> Optional[SourceRecord]:
        try:
            raw_rels = []
            if m.get("agency"):
                raw_rels.append({
                    "rel_type":     RelationshipType.MANAGED_BY.value,
                    "target_name":  m["agency"],
                    "target_class": EntityClass.GOV_AGENCY.value,
                    "confidence":   0.95,
                })
            if m.get("launch_vehicle"):
                raw_rels.append({
                    "rel_type":     RelationshipType.LAUNCHED_BY.value,
                    "target_name":  m["launch_vehicle"],
                    "target_class": EntityClass.LAUNCH_VEHICLE.value,
                    "confidence":   0.90,
                })

            return SourceRecord(
                source_id=f"nasa-mission-{m['id']}",
                source_system="nasa_missions_curated",
                source_tier=SourceTier.TIER_1_OFFICIAL,
                source_url=f"https://www.nasa.gov/mission/{m['id']}",
                entity_class=EntityClass.MISSION,
                canonical_name=m["name"],
                display_name=m["name"],
                description=m.get("description"),
                fields={
                    "mission_type":     m.get("type"),
                    "destination":      m.get("destination"),
                    "lead_agency_aqid": None,  # Resolved during pipeline
                    "mission_status":   m.get("status", "unknown"),
                    "launch_date":      m.get("launch_date"),
                },
                tags=["nasa", m.get("status", "unknown")],
                domains=m.get("domains", ["space_science"]),
                raw_relationships=raw_rels,
            )
        except Exception as e:
            logger.warning(f"NASA mission parse failed for {m.get('id')}: {e}")
            return None
