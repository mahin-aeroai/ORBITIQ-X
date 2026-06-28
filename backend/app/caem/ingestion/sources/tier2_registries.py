"""
ORBITIQ-X — Tier 2 Registry Source Adapters
Phase 17.4

Official registries that provide authoritative structured data:
  - CelestrakAdapter: SATCAT CSV, active satellite list, debris catalog
  - COSPARAdapter:    COSPAR international designator lookups
  - UNOOSAAdapter:    UN OOSA Online Index of Objects Launched into Outer Space

All Tier 2 data (confidence weight: 0.95).

Important: Celestrak blocks Railway IPs. Use Space-Track for production.
Celestrak is available for local development and testing.
"""

from __future__ import annotations

import csv
import io
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


class CelestrakAdapter(SourceAdapter):
    """
    Adapter for Celestrak supplemental/curated data.
    
    Use for local dev and testing. In production, use SpaceTrackAdapter.
    Railway IPs may be blocked by Celestrak (403).
    
    Fetches:
      - Active satellite catalog (CSV)
      - Station-keeping satellite names
      - Launch vehicle reference data
    """
    source_name = "celestrak"
    source_tier = SourceTier.TIER_2_REGISTRY
    fetch_interval_s = 43200  # 12 hours

    ACTIVE_URL  = "https://celestrak.org/pub/satcat.csv"
    GROUPS_URL  = "https://celestrak.org/SOCRATES/query.php"

    # CSV column → CAEM field mapping
    CSV_FIELD_MAP = {
        "NORAD_CAT_ID":  "norad_id",
        "INTLDES":       "cospar_id",
        "OBJECT_TYPE":   "object_type",
        "SATNAME":       "display_name",
        "COUNTRY":       "country_code",
        "LAUNCH":        "launch_date",
        "DECAY":         "decay_date",
        "PERIOD":        "period_min",
        "INCLINATION":   "inclination_deg",
        "APOGEE":        "altitude_km",
        "PERIGEE":       "altitude_perigee_km",
        "RCS_SIZE":      "rcs_size",
    }

    def fetch(self) -> Generator[SourceRecord, None, None]:
        url = self.config.get("url", self.ACTIVE_URL)
        logger.info(f"Celestrak fetch: {url}")

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ORBITIQ-X/0.4 (research; contact@orbitiq-x.ai)"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Celestrak fetch failed: {e}")
            return

        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            record = self._parse_row(row)
            if record:
                yield record

    def _parse_row(self, row: Dict[str, str]) -> Optional[SourceRecord]:
        try:
            norad_id = row.get("NORAD_CAT_ID", "").strip()
            if not norad_id:
                return None

            sat_name = row.get("SATNAME", row.get("OBJECT_NAME", f"OBJECT-{norad_id}")).strip()
            obj_type = row.get("OBJECT_TYPE", "PAYLOAD").strip()

            if obj_type == "DEBRIS":
                entity_class = EntityClass.DEBRIS
            else:
                entity_class = EntityClass.SATELLITE

            fields: Dict[str, Any] = {}
            for csv_key, caem_key in self.CSV_FIELD_MAP.items():
                val = row.get(csv_key, "").strip()
                if val and val not in ("N/A", "", "0000-000"):
                    if caem_key == "norad_id":
                        try: val = int(val)
                        except ValueError: pass
                    elif caem_key in ("period_min", "inclination_deg", "altitude_km", "altitude_perigee_km"):
                        try: val = float(val)
                        except ValueError: pass
                    fields[caem_key] = val

            return SourceRecord(
                source_id=f"celestrak-{norad_id}",
                source_system="celestrak",
                source_tier=SourceTier.TIER_2_REGISTRY,
                source_url=f"https://celestrak.org/pub/satcat.csv",
                entity_class=entity_class,
                canonical_name=sat_name,
                display_name=sat_name,
                fields=fields,
                tags=["celestrak", obj_type.lower().replace(" ", "_")],
                domains=["space_situational_awareness"],
            )
        except Exception as e:
            logger.warning(f"Celestrak row parse failed: {e}")
            return None


class UNOOSAAdapter(SourceAdapter):
    """
    Adapter for UNOOSA Online Index of Objects Launched into Outer Space.

    The UNOOSA register provides treaty-mandated registration data including
    launch state, general function, and orbital parameters.

    Note: UNOOSA data is available as XML/JSON via their API.
    This adapter uses the public UNOOSA API endpoint.
    """
    source_name = "unoosa_oosa"
    source_tier = SourceTier.TIER_2_REGISTRY
    fetch_interval_s = 86400 * 30   # Monthly (registration data is slow-changing)

    UNOOSA_API = "https://www.unoosa.org/oosa/en/ourwork/spacelaw/outerspace/index.html"

    # UNOOSA orbital regime codes
    REGIME_MAP = {
        "LEO": "LEO",
        "MEO": "MEO",
        "GEO": "GEO",
        "HEO": "HEO",
        "L2":  "L2",
    }

    def fetch(self) -> Generator[SourceRecord, None, None]:
        """
        UNOOSA data is parsed from their structured dataset.
        In production this should use the UNOOSA API when a JSON endpoint is available.
        For now yields curated registration examples as seed data.
        """
        seed = self.config.get("seed_records", self._default_seed())
        for rec in seed:
            record = self._parse_registration(rec)
            if record:
                yield record

    def _parse_registration(self, reg: Dict) -> Optional[SourceRecord]:
        try:
            return SourceRecord(
                source_id=f"unoosa-{reg['cospar_id']}",
                source_system="unoosa_oosa",
                source_tier=SourceTier.TIER_2_REGISTRY,
                source_url="https://www.unoosa.org/oosa/osoindex/search-ng.jspx",
                entity_class=EntityClass.SATELLITE,
                canonical_name=reg["name"],
                display_name=reg["name"],
                fields={
                    "cospar_id":        reg["cospar_id"],
                    "orbit_regime":     reg.get("regime"),
                    "launch_date":      reg.get("launch_date"),
                    "country_code":     reg.get("state"),
                    "mission_type":     reg.get("function"),
                },
                tags=["unoosa", "registered"],
                domains=["space_situational_awareness"],
                raw_relationships=[{
                    "rel_type":     RelationshipType.LAUNCHED_BY.value,
                    "target_name":  reg.get("state", ""),
                    "target_class": EntityClass.COUNTRY.value,
                    "confidence":   0.90,
                }] if reg.get("state") else [],
            )
        except Exception as e:
            logger.warning(f"UNOOSA parse failed: {e}")
            return None

    @staticmethod
    def _default_seed() -> List[Dict]:
        """Minimal curated seed to bootstrap UNOOSA data before full API integration."""
        return [
            {"cospar_id": "1998-067A", "name": "International Space Station",
             "regime": "LEO", "launch_date": "1998-11-20", "state": "US",
             "function": "Crewed space station"},
            {"cospar_id": "1957-001B", "name": "Sputnik 1",
             "regime": "LEO", "launch_date": "1957-10-04", "state": "SU",
             "function": "Technology demonstration"},
            {"cospar_id": "2021-130A", "name": "James Webb Space Telescope",
             "regime": "L2",  "launch_date": "2021-12-25", "state": "US",
             "function": "Space observatory"},
        ]
