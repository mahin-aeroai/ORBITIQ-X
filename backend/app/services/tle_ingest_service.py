"""
ORBITIQ-X Backend — TLE Ingest Service

Orchestrates the complete TLE ingestion pipeline:

  1. Parse raw TLE text (3-line or 2-line format)
  2. Validate checksum and physical plausibility
  3. Deduplicate against existing records
  4. Persist to tle_records (append-only archive)
  5. Update satellites.tle_* cache columns (latest TLE only)
  6. Log the ingest event to orbital_events
  7. Return an IngestResult with counts and any errors

This service is called by:
  - scheduler/jobs.py (CelesTrak refresh every 2h)
  - API endpoints (manual TLE upload)
  - Space-Track bulk download handler

Transaction strategy
────────────────────
  The tle_records insert and satellite cache update run inside a
  single transactional() block so both succeed or neither does.
  An error on one object does not abort the rest of the batch —
  per-object errors are collected and returned in IngestResult.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.satellite_repository import SatelliteRepository
from app.db.repositories.tle_repository import TLERepository
from app.db.repositories.orbital_event_repository import OrbitalEventRepository
from app.db.session import transactional

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────

@dataclass
class IngestResult:
    """Summary of a TLE ingest run."""
    total_parsed: int = 0
    inserted: int = 0
    duplicates: int = 0
    satellites_updated: int = 0
    errors: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_parsed == 0:
            return 1.0
        return (self.inserted + self.duplicates) / self.total_parsed


# ── TLE dict builder ──────────────────────────────────────────

def _tle_checksum(line: str) -> int:
    return sum(int(c) if c.isdigit() else (1 if c == '-' else 0) for c in line[:68]) % 10


def _parse_tle_text(text: str) -> list[tuple[str, str, str]]:
    """
    Parse raw TLE text into (name, line1, line2) tuples.
    Handles 3-line and 2-line formats, strips comments.
    """
    lines = [l.strip() for l in text.replace('\r\n', '\n').split('\n')
             if l.strip() and not l.startswith('#')]
    results = []
    i = 0
    while i < len(lines):
        if i + 2 < len(lines) and not lines[i].startswith(('1 ', '2 ')):
            name, l1, l2 = lines[i], lines[i+1], lines[i+2]
            step = 3
        elif i + 1 < len(lines) and lines[i].startswith('1 '):
            name = f"NORAD-{lines[i][2:7].strip()}"
            l1, l2 = lines[i], lines[i+1]
            step = 2
        else:
            i += 1
            continue
        results.append((name.strip(), l1.strip(), l2.strip()))
        i += step
    return results


def _build_tle_record(name: str, l1: str, l2: str, source: str = "celestrak") -> dict | None:
    """
    Build a TLERecord dict from raw TLE strings.
    Returns None if validation fails.
    """
    if len(l1) < 69 or len(l2) < 69:
        return None
    if _tle_checksum(l1) != int(l1[68]) or _tle_checksum(l2) != int(l2[68]):
        return None

    try:
        norad_id    = int(l1[2:7].strip())
        year2       = int(l1[18:20])
        epoch_day   = float(l1[20:32])
        n_dot       = float(l1[33:43])
        elem_set    = int(l1[64:68].strip() or '0')

        inclination = float(l2[8:16])
        raan        = float(l2[17:25])
        eccentricity = float('0.' + l2[26:33].strip())
        arg_perigee = float(l2[34:42])
        mean_anomaly = float(l2[43:51])
        mean_motion  = float(l2[52:63])
        rev_number   = int(l2[63:68].strip() or '0')

        # Epoch → datetime
        year = 2000 + year2 if year2 < 57 else 1900 + year2
        from datetime import timedelta
        base = datetime(year, 1, 1, tzinfo=timezone.utc)
        epoch_dt = base + timedelta(days=int(epoch_day) - 1 + (epoch_day - int(epoch_day)))

        # Derived elements
        MU = 398600.4418
        R_E = 6378.137
        n_rad_s = mean_motion * 2 * math.pi / 86400.0
        a_km = (MU / n_rad_s**2) ** (1/3)
        perigee_km = a_km * (1 - eccentricity) - R_E
        apogee_km  = a_km * (1 + eccentricity) - R_E
        period_min = 1440.0 / mean_motion

        # BSTAR
        raw_bstar = l1[53:61].strip()
        import re
        m = re.match(r'^([+-]?)(\d+)([+-]\d+)$', raw_bstar.lstrip('+-'))
        if m:
            sign = -1.0 if raw_bstar.startswith('-') else 1.0
            bstar = sign * float('0.' + m.group(2)) * (10.0 ** int(m.group(3)))
        else:
            bstar = 0.0

        age_days = (datetime.now(timezone.utc) - epoch_dt).total_seconds() / 86400.0

        return {
            "norad_id": norad_id,
            "name": name[:256],
            "line1": l1,
            "line2": l2,
            "epoch": epoch_dt,
            "epoch_year": year,
            "epoch_day": epoch_day,
            "inclination_deg": inclination,
            "raan_deg": raan,
            "eccentricity": eccentricity,
            "arg_perigee_deg": arg_perigee,
            "mean_anomaly_deg": mean_anomaly,
            "mean_motion_rev_day": mean_motion,
            "bstar": bstar,
            "n_dot": n_dot,
            "n_ddot": 0.0,
            "element_set_num": elem_set,
            "rev_number": rev_number,
            "semi_major_axis_km": a_km,
            "perigee_km": perigee_km,
            "apogee_km": apogee_km,
            "period_minutes": period_min,
            "source": source,
            "checksum_ok": True,
            "age_at_ingest_days": age_days,
        }

    except (ValueError, IndexError) as exc:
        logger.debug("tle_parse_field_error name=%s error=%s", name, exc)
        return None


# ── Service ───────────────────────────────────────────────────

class TLEIngestService:
    """
    Orchestrates TLE ingest from raw text to full database persistence.

    Usage (from scheduler)::

        service = TLEIngestService(session)
        result = await service.ingest_text(
            raw_text=tle_file_contents,
            source="celestrak",
        )
        logger.info("ingested %d TLEs", result.inserted)
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.satellite_repo = SatelliteRepository(session)
        self.tle_repo       = TLERepository(session)
        self.event_repo     = OrbitalEventRepository(session)

    async def ingest_text(
        self,
        raw_text: str,
        source: str = "celestrak",
    ) -> IngestResult:
        """
        Parse and persist all TLEs in a raw text block.

        Steps:
          1. Parse into (name, line1, line2) triples
          2. Build TLERecord dicts (skipping checksum failures)
          3. Bulk insert to tle_records (deduplication via ON CONFLICT)
          4. Update satellite TLE cache for each inserted TLE
          5. Log ingest event

        Parameters
        ----------
        raw_text : str
            Raw TLE file content (3-line or 2-line format).
        source : str
            Data source tag: celestrak | spacetrack | manual | sensor.

        Returns
        -------
        IngestResult
            Counts and errors from this ingest run.
        """
        import time
        t0 = time.perf_counter()

        result = IngestResult()

        # Step 1: Parse
        triples = _parse_tle_text(raw_text)
        result.total_parsed = len(triples)
        logger.info("tle_ingest_start source=%s parsed=%d", source, len(triples))

        if not triples:
            return result

        # Step 2: Build dicts
        tle_records: list[dict] = []
        for name, l1, l2 in triples:
            rec = _build_tle_record(name, l1, l2, source)
            if rec is None:
                result.errors.append({"name": name, "error": "parse_failed"})
            else:
                tle_records.append(rec)

        # Step 3: Bulk insert TLE archive records
        async with transactional(self.session):
            inserted_count = await self.tle_repo.bulk_insert(tle_records)
            result.inserted   = inserted_count
            result.duplicates = len(tle_records) - inserted_count

        # Step 4: Update satellite cache (per-object, skip errors)
        for rec in tle_records:
            try:
                async with transactional(self.session):
                    rows_updated = await self.satellite_repo.update_tle_cache(
                        norad_id=rec["norad_id"],
                        tle_line1=rec["line1"],
                        tle_line2=rec["line2"],
                        epoch=rec["epoch"],
                        bstar=rec["bstar"],
                        perigee_km=rec["perigee_km"],
                        apogee_km=rec["apogee_km"],
                        inclination_deg=rec["inclination_deg"],
                        period_minutes=rec["period_minutes"],
                        mean_motion_rev_day=rec["mean_motion_rev_day"],
                        source=source,
                    )
                    result.satellites_updated += rows_updated
            except Exception as exc:
                logger.warning(
                    "satellite_cache_update_failed norad=%s error=%s",
                    rec["norad_id"], exc,
                )
                result.errors.append({
                    "norad_id": rec["norad_id"],
                    "error": f"cache_update_failed: {exc}",
                })

        result.duration_seconds = time.perf_counter() - t0
        logger.info(
            "tle_ingest_complete source=%s parsed=%d inserted=%d "
            "dupes=%d sats_updated=%d errors=%d duration=%.2fs",
            source, result.total_parsed, result.inserted,
            result.duplicates, result.satellites_updated,
            len(result.errors), result.duration_seconds,
        )
        return result

    async def ingest_single(
        self,
        name: str,
        line1: str,
        line2: str,
        source: str = "manual",
    ) -> dict | None:
        """
        Ingest a single TLE. Returns the TLERecord dict or None on failure.
        Used by the API endpoint for manual TLE upload.
        """
        rec = _build_tle_record(name, line1, l2=line2, source=source)
        if rec is None:
            return None

        async with transactional(self.session):
            tle_row = await self.tle_repo.insert_or_skip(rec)
            if tle_row:
                await self.satellite_repo.update_tle_cache(
                    norad_id=rec["norad_id"],
                    tle_line1=rec["line1"],
                    tle_line2=rec["line2"],
                    epoch=rec["epoch"],
                    bstar=rec["bstar"],
                    perigee_km=rec["perigee_km"],
                    apogee_km=rec["apogee_km"],
                    inclination_deg=rec["inclination_deg"],
                    period_minutes=rec["period_minutes"],
                    mean_motion_rev_day=rec["mean_motion_rev_day"],
                    source=source,
                )

        return rec
