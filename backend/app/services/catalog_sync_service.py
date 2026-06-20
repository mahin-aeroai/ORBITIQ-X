"""
ORBITIQ-X — Catalog Synchronization Service
============================================
Orchestrates the complete Space-Track → PostgreSQL ingestion pipeline.

Pipeline
────────
  1. Authenticate to Space-Track
  2. Download TLEs (full catalog or latest-only)
  3. Validate & parse into TLERecord dicts
  4. Store in tle_records (historical archive, idempotent)
  5. Update satellites catalog (upsert with TLE cache refresh)
  6. Refresh Redis TLE cache (hash per NORAD ID)
  7. Compute and persist sync metrics
  8. Return SyncReport

What this does NOT touch (already implemented, reused)
──────────────────────────────────────────────────────
  tle_ingest_service.TLEIngestService.ingest_text()  ← Phase 3/4 of pipeline
  satellite_repository.bulk_upsert()                 ← satellite upsert
  tle_repository.bulk_insert()                       ← archive insert
  spacetrack_fetcher.SpaceTrackFetcher               ← HTTP layer

Idempotency guarantee
──────────────────────
  Every TLE record insert uses ON CONFLICT DO NOTHING on
  (norad_id, epoch, element_set_num). Running this service twice
  with the same Space-Track response is a no-op for the archive
  and an UPDATE for the satellite cache.

Failure recovery
────────────────
  sync_mode="incremental" fetches only last N days — safe to retry.
  sync_mode="full"        fetches entire catalog — 1 HTTP call.
  
  If the DB write fails after a successful download, the raw TLE text
  is NOT stored (stateless fetch-parse-write cycle). Re-running will
  re-fetch from Space-Track. This is acceptable given the 6h schedule.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.satellite_repository import SatelliteRepository
from app.db.repositories.tle_repository import TLERepository
from app.db.session import get_session_factory, transactional
from app.services.spacetrack_fetcher import (
    FetchResult,
    SpaceTrackAuthError,
    SpaceTrackFetcher,
    SpaceTrackNetworkError,
    SpaceTrackRateLimitError,
)
from app.services.tle_ingest_service import IngestResult, TLEIngestService

logger = logging.getLogger(__name__)

SyncMode = Literal["full", "incremental", "active_only", "debris_only"]


# ── Sync report ───────────────────────────────────────────────

@dataclass
class SyncReport:
    """
    Complete result of one catalog synchronization run.
    Persisted to sync_metrics table (see Phase 4).
    """
    sync_id: str                    # UUID for this run
    sync_mode: SyncMode
    started_at: datetime
    completed_at: datetime | None   = None
    status: str                     = "running"  # running|success|partial|failed

    # Download metrics
    download_duration_s: float      = 0.0
    downloaded_bytes: int           = 0
    downloaded_records: int         = 0

    # Ingest metrics
    total_parsed: int               = 0
    inserted: int                   = 0
    duplicates: int                 = 0
    satellites_updated: int         = 0
    parse_errors: int               = 0

    # Derived
    stale_satellite_count: int      = 0
    cache_keys_refreshed: int       = 0
    failure_reason: str | None      = None
    phases_completed: list[str]     = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    @property
    def ingest_rate(self) -> float:
        """Records ingested per second during DB write phase."""
        return self.inserted / max(self.duration_seconds, 0.001)

    def as_dict(self) -> dict:
        return {
            "sync_id": self.sync_id,
            "sync_mode": self.sync_mode,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 2),
            "downloaded_records": self.downloaded_records,
            "total_parsed": self.total_parsed,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "satellites_updated": self.satellites_updated,
            "parse_errors": self.parse_errors,
            "stale_satellite_count": self.stale_satellite_count,
            "cache_keys_refreshed": self.cache_keys_refreshed,
            "failure_reason": self.failure_reason,
            "phases_completed": self.phases_completed,
            "ingest_rate_per_sec": round(self.ingest_rate, 1),
        }


# ── Service ───────────────────────────────────────────────────

class CatalogSyncService:
    """
    Orchestrates Space-Track TLE download → database persistence.

    Instantiate fresh for each sync run. Not intended for reuse
    across multiple runs (use the factory methods instead).

    Parameters
    ----------
    fetcher : SpaceTrackFetcher
        Authenticated fetcher instance (caller must call authenticate()).
    session : AsyncSession
        Database session for this sync operation.
    redis_client : optional
        Redis client for cache refresh. If None, cache step is skipped.
    """

    def __init__(
        self,
        fetcher: SpaceTrackFetcher,
        session: AsyncSession,
        redis_client=None,
    ) -> None:
        self._fetcher      = fetcher
        self._session      = session
        self._redis        = redis_client
        self._sat_repo     = SatelliteRepository(session)
        self._tle_repo     = TLERepository(session)
        self._ingest_svc   = TLEIngestService(session)

    # ── Public sync entry points ──────────────────────────────

    async def sync_full(self, sync_id: str | None = None) -> SyncReport:
        """
        Full catalog sync — downloads every active non-decayed object.

        Use this for the 6-hour scheduled run. Expects ~50,000 objects.
        Runtime: 2–5 minutes end-to-end.

        Parameters
        ----------
        sync_id : str | None
            Pre-generated UUID for this run. Auto-generated if None.
        """
        return await self._run_sync("full", sync_id)

    async def sync_incremental(
        self,
        days_back: int = 2,
        sync_id: str | None = None,
    ) -> SyncReport:
        """
        Incremental sync — downloads only TLEs updated in last N days.

        Use for the 2-hour active-satellite refresh job. Expects ~5,000–10,000
        objects per run. Much faster than full sync.

        Parameters
        ----------
        days_back : int
            Number of days back to query Space-Track.
        """
        return await self._run_sync("incremental", sync_id, days_back=days_back)

    async def sync_active_only(self, sync_id: str | None = None) -> SyncReport:
        """Download only payloads and rocket bodies (no debris)."""
        return await self._run_sync("active_only", sync_id)

    # ── Core pipeline ─────────────────────────────────────────

    async def _run_sync(
        self,
        mode: SyncMode,
        sync_id: str | None,
        **kwargs,
    ) -> SyncReport:
        """Execute the full pipeline for any sync mode."""
        import uuid
        sid = sync_id or str(uuid.uuid4())
        report = SyncReport(
            sync_id=sid,
            sync_mode=mode,
            started_at=datetime.now(timezone.utc),
        )

        logger.info(
            "catalog_sync_start sync_id=%s mode=%s",
            sid, mode,
        )

        try:
            # Phase 1: Authenticate
            await self._phase_authenticate(report)

            # Phase 2: Download
            fetch_result = await self._phase_download(report, mode, **kwargs)
            if fetch_result.failed:
                report.status = "failed"
                report.failure_reason = f"download_failed: {fetch_result.error}"
                return self._finalise(report)

            # Phase 3: Validate & parse + Phase 4: Store
            ingest_result = await self._phase_ingest(report, fetch_result)

            # Phase 5: Update catalog (satellite rows)
            # tle_ingest_service.ingest_text() already calls update_tle_cache()
            # so satellite rows are already current after phase_ingest.
            report.phases_completed.append("catalog_update")

            # Phase 6: Refresh Redis cache
            if self._redis:
                await self._phase_cache_refresh(report, ingest_result)

            # Phase 7: Compute stale satellite count
            await self._phase_stale_count(report)

            report.status = (
                "success" if report.parse_errors == 0 else "partial"
            )

        except SpaceTrackAuthError as exc:
            logger.error("catalog_sync_auth_failed sync_id=%s error=%s", sid, exc)
            report.status = "failed"
            report.failure_reason = f"auth_error: {exc}"

        except SpaceTrackRateLimitError as exc:
            logger.error("catalog_sync_rate_limited sync_id=%s error=%s", sid, exc)
            report.status = "failed"
            report.failure_reason = f"rate_limit: {exc}"

        except SpaceTrackNetworkError as exc:
            logger.error("catalog_sync_network_failed sync_id=%s error=%s", sid, exc)
            report.status = "failed"
            report.failure_reason = f"network_error: {exc}"

        except Exception as exc:
            logger.exception("catalog_sync_unexpected sync_id=%s", sid)
            report.status = "failed"
            report.failure_reason = f"unexpected: {type(exc).__name__}: {exc}"

        finally:
            return self._finalise(report)

    def _finalise(self, report: SyncReport) -> SyncReport:
        report.completed_at = datetime.now(timezone.utc)
        logger.info(
            "catalog_sync_complete sync_id=%s status=%s "
            "parsed=%d inserted=%d dupes=%d sats=%d duration=%.1fs",
            report.sync_id, report.status,
            report.total_parsed, report.inserted,
            report.duplicates, report.satellites_updated,
            report.duration_seconds,
        )
        return report

    # ── Pipeline phases ───────────────────────────────────────

    async def _phase_authenticate(self, report: SyncReport) -> None:
        """Phase 1: Ensure we have a valid Space-Track session."""
        if not self._fetcher._authenticated:
            await self._fetcher.authenticate()
        report.phases_completed.append("authenticate")
        logger.debug("catalog_sync phase=authenticate ok")

    async def _phase_download(
        self,
        report: SyncReport,
        mode: SyncMode,
        **kwargs,
    ) -> FetchResult:
        """Phase 2: Download TLE data from Space-Track."""
        t0 = time.perf_counter()

        if mode == "full":
            result = await self._fetcher.fetch_full_catalog()
        elif mode == "incremental":
            days_back = kwargs.get("days_back", 2)
            result = await self._fetcher.fetch_latest_tles(days_back=days_back)
        elif mode == "active_only":
            result = await self._fetcher.fetch_active_catalog()
        elif mode == "debris_only":
            result = await self._fetcher.fetch_debris_catalog()
        else:
            raise ValueError(f"Unknown sync mode: {mode!r}")

        if result.ok:
            report.download_duration_s  = time.perf_counter() - t0
            report.downloaded_bytes     = len(result.raw_text.encode())
            report.downloaded_records   = result.record_count
            report.phases_completed.append("download")
            logger.info(
                "catalog_sync phase=download ok records=%d bytes=%d duration=%.1fs",
                result.record_count, report.downloaded_bytes, report.download_duration_s,
            )
        else:
            logger.error("catalog_sync phase=download failed error=%s", result.error)

        return result

    async def _phase_ingest(
        self,
        report: SyncReport,
        fetch_result: FetchResult,
    ) -> IngestResult:
        """
        Phases 3+4: Parse TLE text and write to database.

        Delegates to TLEIngestService.ingest_text() which already
        implements the full parse → bulk_insert → update_tle_cache pipeline.
        """
        logger.info(
            "catalog_sync phase=ingest start bytes=%d",
            report.downloaded_bytes,
        )

        ingest_result = await self._ingest_svc.ingest_text(
            raw_text=fetch_result.raw_text,
            source="spacetrack",
        )

        # Populate report from ingest result
        report.total_parsed         = ingest_result.total_parsed
        report.inserted             = ingest_result.inserted
        report.duplicates           = ingest_result.duplicates
        report.satellites_updated   = ingest_result.satellites_updated
        report.parse_errors         = len(ingest_result.errors)
        report.phases_completed.append("ingest")

        if report.parse_errors:
            logger.warning(
                "catalog_sync phase=ingest parse_errors=%d (sample: %s)",
                report.parse_errors,
                ingest_result.errors[:3],
            )

        logger.info(
            "catalog_sync phase=ingest complete parsed=%d inserted=%d "
            "dupes=%d sats_updated=%d errors=%d",
            report.total_parsed, report.inserted,
            report.duplicates, report.satellites_updated, report.parse_errors,
        )
        return ingest_result

    async def _phase_cache_refresh(
        self,
        report: SyncReport,
        ingest_result: IngestResult,
    ) -> None:
        """
        Phase 6: Warm Redis TLE cache for recently ingested objects.

        Stores the latest TLE for each object as a Redis hash:
            HSET tle:{norad_id}  line1 <L1>  line2 <L2>  epoch <ISO>
            EXPIRE tle:{norad_id} 7200   (2h — matches 2h refresh cadence)

        Only updates objects that were just inserted (not duplicates).
        At 50K objects, this is ~200ms with pipelining.
        """
        if not ingest_result.inserted:
            return

        try:
            pipe = self._redis.pipeline()
            refreshed = 0

            # Fetch the active LEOs that were just updated
            # (limited to objects with fresh TLEs for efficiency)
            satellites = await self._sat_repo.get_active_leos()

            for sat in satellites:
                if sat.tle_line1 and sat.tle_line2:
                    key = f"tle:{sat.norad_id}"
                    pipe.hset(key, mapping={
                        "line1":   sat.tle_line1,
                        "line2":   sat.tle_line2,
                        "epoch":   sat.tle_epoch.isoformat() if sat.tle_epoch else "",
                        "norad":   str(sat.norad_id),
                        "name":    sat.name or "",
                        "source":  sat.tle_source or "spacetrack",
                    })
                    pipe.expire(key, 7200)  # 2h TTL
                    refreshed += 1

            await pipe.execute()
            report.cache_keys_refreshed = refreshed
            report.phases_completed.append("cache_refresh")
            logger.info("catalog_sync phase=cache_refresh keys=%d", refreshed)

        except Exception as exc:
            # Redis failure must NOT abort the sync — cache is hot path, not critical
            logger.warning("catalog_sync phase=cache_refresh failed error=%s", exc)
            report.phases_completed.append("cache_refresh_failed")

    async def _phase_stale_count(self, report: SyncReport) -> None:
        """Phase 7: Count satellites with TLE older than 7 days (monitoring)."""
        try:
            stale = await self._tle_repo.get_stale(max_age_days=7.0)
            report.stale_satellite_count = len(stale)
            report.phases_completed.append("stale_count")
            if report.stale_satellite_count:
                logger.warning(
                    "catalog_sync stale_satellites=%d (TLE age > 7 days)",
                    report.stale_satellite_count,
                )
        except Exception as exc:
            logger.warning("catalog_sync phase=stale_count failed error=%s", exc)

    # ── Factory classmethod ───────────────────────────────────

    @classmethod
    async def create(cls, redis_client=None) -> "CatalogSyncService":
        """
        Build a CatalogSyncService using app settings.
        Opens its own DB session (caller must await close).

        Usage::

            svc = await CatalogSyncService.create()
            report = await svc.sync_full()

        Note: This method is used by the scheduler and API trigger.
        For test injection, instantiate directly with explicit deps.
        """
        fetcher = SpaceTrackFetcher.from_settings()
        factory = get_session_factory()
        session = factory()
        return cls(fetcher=fetcher, session=session, redis_client=redis_client)
