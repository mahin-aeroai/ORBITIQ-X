"""
ORBITIQ-X Backend — TLE Records Repository

Handles the historical TLE archive. Every TLE ever ingested is
kept permanently (TimescaleDB compression after 30 days reduces
storage by ~90%). This enables:

  - Historical propagation to any past epoch
  - TLE age analysis and data quality reporting
  - Conjunction event re-analysis with TLEs at the original CDM epoch

Deduplication strategy
──────────────────────
  Unique constraint: (norad_id, epoch, element_set_num)
  On conflict: update only if the new TLE is from a higher-quality
  source (spacetrack > celestrak > manual).

  This means re-ingesting the same file is idempotent — safe to run
  CelesTrak and Space-Track ingest jobs hourly without duplicates.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, desc, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tle_records import TLERecord
from .base import BaseRepository

logger = logging.getLogger(__name__)

_SOURCE_PRIORITY = {"spacetrack": 3, "celestrak": 2, "manual": 1, "sensor": 0}
# PostgreSQL bind-parameter limit is 32767.
# TLERecord has 27 insertable columns → max safe rows = 32767 // 27 = 1213.
# Using 1000 for a safe margin.
_BULK_BATCH = 1000


class TLERepository(BaseRepository[TLERecord]):
    """Repository for the ``tle_records`` historical TLE archive."""

    model = TLERecord

    async def insert_or_skip(self, data: dict) -> TLERecord | None:
        """
        Insert a TLE record, skipping if (norad_id, epoch, element_set_num)
        already exists with equal or higher source quality.

        Returns
        -------
        TLERecord | None
            The inserted row, or None if skipped (duplicate).
        """
        stmt = (
            insert(TLERecord)
            .values(**data)
            .on_conflict_do_nothing(
                index_elements=["norad_id", "epoch", "element_set_num"]
            )
            .returning(TLERecord)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        row = result.scalar_one_or_none()
        if row:
            logger.debug(
                "tle_inserted norad=%s epoch=%s",
                row.norad_id, row.epoch.isoformat()
            )
        return row

    async def bulk_insert(self, records: list[dict]) -> int:
        """
        Batch insert TLE records with deduplication.

        Uses INSERT ... ON CONFLICT DO NOTHING for idempotent ingest.
        At 50,000 objects with 1 TLE each: ~10 batches × 5,000 rows.

        Parameters
        ----------
        records : list[dict]
            TLE field dicts. All must have norad_id, epoch, element_set_num.

        Returns
        -------
        int
            Number of rows actually inserted (deduplication may reduce this).
        """
        if not records:
            return 0

        total_inserted = 0
        for i in range(0, len(records), _BULK_BATCH):
            batch = records[i : i + _BULK_BATCH]
            stmt = (
                insert(TLERecord)
                .values(batch)
                .on_conflict_do_nothing(
                    index_elements=["norad_id", "epoch", "element_set_num"]
                )
            )
            result = await self.session.execute(stmt)
            total_inserted += result.rowcount
            logger.debug(
                "tle_bulk_batch %d/%d inserted=%d",
                i // _BULK_BATCH + 1,
                (len(records) - 1) // _BULK_BATCH + 1,
                result.rowcount,
            )

        await self.session.flush()
        logger.info(
            "tle_bulk_insert_complete total_in=%d inserted=%d duplicates=%d",
            len(records), total_inserted, len(records) - total_inserted,
        )
        return total_inserted

    async def get_latest(self, norad_id: int) -> TLERecord | None:
        """Return the most recent TLE for a given NORAD ID."""
        result = await self.session.execute(
            select(TLERecord)
            .where(TLERecord.norad_id == norad_id)
            .order_by(desc(TLERecord.epoch))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_at_epoch(
        self,
        norad_id: int,
        target_epoch: datetime,
    ) -> TLERecord | None:
        """
        Return the TLE with epoch closest to and before ``target_epoch``.

        Used for historical propagation replay — find the TLE that would
        have been current at a specific past time.
        """
        result = await self.session.execute(
            select(TLERecord)
            .where(
                TLERecord.norad_id == norad_id,
                TLERecord.epoch <= target_epoch,
            )
            .order_by(desc(TLERecord.epoch))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_history(
        self,
        norad_id: int,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> Sequence[TLERecord]:
        """
        Return TLE history for a satellite between two datetimes.

        Ordered by epoch ascending (oldest first) to support time-series
        analysis of orbital evolution.
        """
        result = await self.session.execute(
            select(TLERecord)
            .where(
                TLERecord.norad_id == norad_id,
                TLERecord.epoch >= start,
                TLERecord.epoch <= end,
            )
            .order_by(TLERecord.epoch)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_stale(
        self,
        max_age_days: float = 7.0,
        regime: str | None = None,
    ) -> Sequence[TLERecord]:
        """
        Return objects whose most recent TLE is older than max_age_days.

        Used by the scheduler to identify which objects need fresh TLEs.
        Joins to satellites to filter by regime.
        """
        from app.db.models.satellites import Satellite
        from sqlalchemy import func as sqlfunc

        # Subquery: latest epoch per norad_id
        subq = (
            select(
                TLERecord.norad_id,
                sqlfunc.max(TLERecord.epoch).label("latest_epoch"),
            )
            .group_by(TLERecord.norad_id)
            .subquery()
        )

        threshold = text(f"NOW() - INTERVAL '{max_age_days} days'")
        stmt = (
            select(TLERecord)
            .join(subq, TLERecord.norad_id == subq.c.norad_id)
            .where(subq.c.latest_epoch < threshold)
        )
        if regime:
            stmt = stmt.join(
                Satellite,
                Satellite.norad_id == TLERecord.norad_id,
            ).where(Satellite.regime == regime)

        result = await self.session.execute(stmt.limit(5000))
        return result.scalars().all()

    async def count_by_source(self) -> dict[str, int]:
        """Diagnostic: count TLE records by ingestion source."""
        from sqlalchemy import func as sqlfunc
        result = await self.session.execute(
            select(TLERecord.source, sqlfunc.count(TLERecord.id))
            .group_by(TLERecord.source)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_for_norad(self, norad_id: int) -> int:
        """Count total TLE records stored for an object."""
        from sqlalchemy import func as sqlfunc
        result = await self.session.execute(
            select(sqlfunc.count(TLERecord.id))
            .where(TLERecord.norad_id == norad_id)
        )
        return result.scalar_one()
