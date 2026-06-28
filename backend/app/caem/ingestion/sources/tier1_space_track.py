"""
ORBITIQ-X — Space-Track.org Source Adapter (Tier 1)
Phase 17.4

Fetches from Space-Track.org REST API:
  - SATCAT (satellite catalog with names, types, operators, countries)
  - GP (general perturbations — TLE data for active objects)

Space-Track is classified as Tier 2 (official registry) for catalog data,
and Tier 1 (official) for TLE/GP data since it is the US DoD authoritative source.

Rate limit: Space-Track enforces a limit of 20 requests/minute and
1,000 requests/day. The adapter spaces requests accordingly.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import datetime, timedelta
from typing import Any, Dict, Generator, List, Optional

from caem.base import EntityClass
from caem.provenance.models import SourceTier
from caem.relationships import RelationshipType
from caem.ingestion.sources.base import SourceAdapter, SourceRecord

logger = logging.getLogger(__name__)

SPACE_TRACK_BASE = "https://www.space-track.org"
SPACE_TRACK_LOGIN = f"{SPACE_TRACK_BASE}/ajaxauth/login"

# SATCAT field mapping → CAEM extension fields
SATCAT_FIELD_MAP = {
    "NORAD_CAT_ID":     "norad_id",
    "INTLDES":          "cospar_id",
    "OBJECT_TYPE":      "object_type",
    "SATNAME":          "display_name",
    "COUNTRY":          "country_code",
    "LAUNCH":           "launch_date",
    "SITE":             "launch_site_code",
    "DECAY":            "decay_date",
    "PERIOD":           "period_min",
    "INCLINATION":      "inclination_deg",
    "APOGEE":           "altitude_km",
    "PERIGEE":          "altitude_perigee_km",
    "RCS_SIZE":         "rcs_size",
    "LAUNCH_YEAR":      "launch_year",
    "LAUNCH_NUM":       "launch_num",
    "LAUNCH_PIECE":     "launch_piece",
    "CURRENT":          "is_current",
    "OBJECT_NAME":      "object_name",
    "OBJECT_ID":        "object_id",
    "OBJECT_NUMBER":    "object_number",
}

OBJECT_TYPE_MAP = {
    "PAYLOAD":      "satellite",
    "ROCKET BODY":  "rocket_body",
    "DEBRIS":       "debris",
    "UNKNOWN":      "unknown",
    "TBA":          "tba",
}


class SpaceTrackAdapter(SourceAdapter):
    """
    Adapter for Space-Track.org SATCAT and GP data.

    Config keys:
      identity:   Space-Track login email
      password:   Space-Track password
      mode:       'satcat' | 'gp' | 'both' (default: 'satcat')
      norad_range: '1--99999' style range string (default: all)
      max_age_days: skip objects with decay older than N days (default: 0 = include all)
    """
    source_name = "space_track"
    source_tier = SourceTier.TIER_2_REGISTRY
    fetch_interval_s = 7200  # 2 hours

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._opener: Optional[urllib.request.OpenerDirector] = None
        self._session_valid = False

    def _login(self) -> bool:
        identity = self.config.get("identity", "")
        password = self.config.get("password", "")
        if not identity or not password:
            logger.error("SpaceTrackAdapter: identity and password required in config")
            return False

        cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj)
        )
        try:
            payload = urllib.parse.urlencode(
                {"identity": identity, "password": password}
            ).encode()
            self._opener.open(SPACE_TRACK_LOGIN, payload, timeout=30)
            self._session_valid = True
            logger.info("SpaceTrack login successful")
            return True
        except Exception as e:
            logger.error(f"SpaceTrack login failed: {e}")
            return False

    def _fetch_url(self, url: str, timeout: int = 120) -> Optional[List[Dict]]:
        if not self._session_valid:
            if not self._login():
                return None
        try:
            time.sleep(3)  # Respect rate limit: ~20 req/min
            resp = self._opener.open(url, timeout=timeout)
            return json.loads(resp.read())
        except Exception as e:
            logger.error(f"SpaceTrack fetch failed [{url[:80]}]: {e}")
            return None

    def _build_satcat_url(self, norad_range: str = "1--99999") -> str:
        return (
            f"{SPACE_TRACK_BASE}/basicspacedata/query/class/satcat"
            f"/NORAD_CAT_ID/{norad_range}/format/json"
            f"/orderby/NORAD_CAT_ID asc"
        )

    def _parse_satcat_record(self, raw: Dict) -> Optional[SourceRecord]:
        """Convert a SATCAT row into a SourceRecord."""
        try:
            norad_id = raw.get("NORAD_CAT_ID", "").strip()
            sat_name = (raw.get("SATNAME") or raw.get("OBJECT_NAME") or f"OBJECT-{norad_id}").strip()
            object_type_raw = raw.get("OBJECT_TYPE", "PAYLOAD")
            object_type = OBJECT_TYPE_MAP.get(object_type_raw, "unknown")

            # Determine entity class
            if object_type == "satellite":
                entity_class = EntityClass.SATELLITE
            elif object_type == "debris":
                entity_class = EntityClass.DEBRIS
            else:
                entity_class = EntityClass.SATELLITE  # Rocket bodies also modeled as satellites

            # Build extension fields
            fields: Dict[str, Any] = {}
            for raw_key, caem_key in SATCAT_FIELD_MAP.items():
                val = raw.get(raw_key)
                if val not in (None, "", "N/A"):
                    # Type coercion
                    if caem_key in ("norad_id", "launch_year", "launch_num"):
                        try: val = int(val)
                        except (ValueError, TypeError): pass
                    elif caem_key in ("period_min", "inclination_deg", "altitude_km", "altitude_perigee_km"):
                        try: val = float(val)
                        except (ValueError, TypeError): pass
                    fields[caem_key] = val

            # Raw relationships
            raw_relationships = []
            country_code = raw.get("COUNTRY", "").strip()
            if country_code:
                raw_relationships.append({
                    "rel_type":     RelationshipType.LAUNCHED_BY.value,
                    "target_name":  country_code,
                    "target_class": EntityClass.COUNTRY.value,
                    "confidence":   0.80,
                })

            return SourceRecord(
                source_id=f"satcat-{norad_id}",
                source_system="space_track",
                source_tier=SourceTier.TIER_2_REGISTRY,
                source_url=f"{SPACE_TRACK_BASE}/basicspacedata/query/class/satcat/NORAD_CAT_ID/{norad_id}",
                entity_class=entity_class,
                canonical_name=sat_name,
                display_name=sat_name,
                fields=fields,
                tags=[object_type, country_code.lower()] if country_code else [object_type],
                domains=["space_situational_awareness", "orbital_mechanics"],
                raw_relationships=raw_relationships,
            )
        except Exception as e:
            logger.warning(f"SATCAT parse failed for record {raw.get('NORAD_CAT_ID')}: {e}")
            return None

    def fetch(self) -> Generator[SourceRecord, None, None]:
        mode = self.config.get("mode", "satcat")
        norad_range = self.config.get("norad_range", "1--99999")

        if not self._login():
            return

        if mode in ("satcat", "both"):
            # Fetch in batches of 30,000 to avoid timeouts
            batch_ranges = self._split_range(norad_range, batch_size=30000)
            for batch_range in batch_ranges:
                url = self._build_satcat_url(batch_range)
                logger.info(f"Fetching SATCAT range {batch_range}")
                data = self._fetch_url(url)
                if not data:
                    continue
                for row in data:
                    record = self._parse_satcat_record(row)
                    if record:
                        yield record

    @staticmethod
    def _split_range(norad_range: str, batch_size: int = 30000) -> List[str]:
        """Split 'start--end' into multiple batch ranges."""
        try:
            parts = norad_range.split("--")
            start, end = int(parts[0]), int(parts[1])
            ranges = []
            current = start
            while current <= end:
                batch_end = min(current + batch_size - 1, end)
                ranges.append(f"{current}--{batch_end}")
                current = batch_end + 1
            return ranges
        except Exception:
            return [norad_range]
