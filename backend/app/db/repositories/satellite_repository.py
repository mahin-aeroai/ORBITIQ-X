"""
ORBITIQ-X Backend — Satellite Repository

Handles all reads and writes to the ``satellites`` table.

Key operations for 50K-object SSA
───────────────────────────────────
  upsert()           — insert-or-update one satellite by NORAD ID
  bulk_upsert()      — batch upsert for CelesTrak full catalog ingest
  update_tle_cache() — update the cached TLE fields after fresh TLE ingest
  get_by_norad()     — primary lookup path for most callers
  get_active_leos()  — conjunction screener's catalog load
  search_by_name()   — operator name search (uses pg_trgm index)

Performance notes
─────────────────
  bulk_upsert() uses PostgreSQL INSERT ... ON CONFLICT DO UPDATE
  with a single statement for up to 5,000 rows per batch.
  At 50,000 objects: 10 batches × ~200ms each ≈ 2s per full catalog refresh.

  get_active_leos() selects only the columns needed by the voxel-hash
  screener (norad_id, tle_line1, tle_line2, hard_body_radius_km) to
  minimise row size for the 50K-row scan.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.satellites import Satellite
from .base import BaseRepository

logger = logging.getLogger(__name__)

# ── Batch size for bulk upsert ────────────────────────────────
# PostgreSQL bind-parameter limit is 32767.
# Satellite has 41 insertable columns → max safe rows = 32767 // 41 = 799.
# Using 500 for a safe margin.
_BULK_BATCH = 500


class SatelliteRepository(BaseRepository[Satellite]):
    """Repository for the ``satellites`` RSO catalog table."""

    model = Satellite

    async def get_by_norad(self, norad_id: int) -> Satellite | None:
        """Primary lookup — most SSA queries start with a NORAD ID."""
        result = await self.session.execute(
            select(Satellite).where(Satellite.norad_id == norad_id)
        )
        return result.scalar_one_or_none()

    async def get_by_cospar(self, cospar_id: str) -> Satellite | None:
        result = await self.session.execute(
            select(Satellite).where(Satellite.cospar_id == cospar_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, data: dict) -> Satellite:
        """
        Insert or update a satellite record by NORAD ID.

        If the satellite already exists, all provided fields are updated.
        The ``updated_at`` column is refreshed automatically by the
        database trigger.

        Parameters
        ----------
        data : dict
            Column-value mapping. Must include ``norad_id``.

        Returns
        -------
        Satellite
            The persisted row with ``id`` populated.
        """
        stmt = (
            insert(Satellite)
            .values(**data)
            .on_conflict_do_update(
                index_elements=["norad_id"],
                set_={k: v for k, v in data.items() if k != "norad_id"},
            )
            .returning(Satellite)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        row = result.scalar_one()
        logger.debug("satellite_upserted norad=%s name=%s", row.norad_id, row.name)
        return row

    async def bulk_upsert(self, records: list[dict]) -> int:
        """
        Batch upsert for full CelesTrak / Space-Track catalog ingest.

        Processes records in batches of ``_BULK_BATCH`` to stay within
        PostgreSQL parameter limits. Conflict resolution: update all
        non-key fields when a row already exists.

        Parameters
        ----------
        records : list[dict]
            List of column-value dicts. Each must include ``norad_id``.

        Returns
        -------
        int
            Total number of rows processed (inserted + updated).
        """
        if not records:
            return 0

        total = 0
        for i in range(0, len(records), _BULK_BATCH):
            batch = records[i : i + _BULK_BATCH]

            stmt = (
                insert(Satellite)
                .values(batch)
                .on_conflict_do_update(
                    index_elements=["norad_id"],
                    set_={
                        col: text(f"EXCLUDED.{col}")
                        for col in batch[0].keys()
                        if col not in ("id", "norad_id", "created_at")
                    },
                )
            )
            result = await self.session.execute(stmt)
            total += result.rowcount
            logger.debug(
                "satellite_bulk_batch batch=%d/%d rows=%d",
                i // _BULK_BATCH + 1,
                (len(records) - 1) // _BULK_BATCH + 1,
                result.rowcount,
            )

        await self.session.flush()
        logger.info("satellite_bulk_upsert_complete total=%d", total)
        return total

    async def update_tle_cache(
        self,
        norad_id: int,
        tle_line1: str,
        tle_line2: str,
        epoch: datetime,
        bstar: float,
        perigee_km: float,
        apogee_km: float,
        inclination_deg: float,
        period_minutes: float,
        mean_motion_rev_day: float,
        source: str = "celestrak",
    ) -> int:
        """
        Update the denormalised TLE cache on the satellites row.

        Called after every successful TLE ingest to keep the satellites
        table current without requiring a join to tle_records on every
        propagation request.

        Returns
        -------
        int
            Number of rows updated (0 if NORAD not in catalog).
        """
        age_days = (
            datetime.now(timezone.utc) - epoch
        ).total_seconds() / 86400.0

        result = await self.session.execute(
            update(Satellite)
            .where(Satellite.norad_id == norad_id)
            .values(
                tle_line1=tle_line1,
                tle_line2=tle_line2,
                tle_epoch=epoch,
                tle_age_days=age_days,
                tle_source=source,
                bstar=bstar,
                perigee_km=perigee_km,
                apogee_km=apogee_km,
                inclination_deg=inclination_deg,
                period_minutes=period_minutes,
                mean_motion_rev_day=mean_motion_rev_day,
            )
        )
        await self.session.flush()
        return result.rowcount

    async def get_active_leos(
        self,
        max_altitude_km: float = 2000.0,
        min_altitude_km: float = 150.0,
    ) -> Sequence[Satellite]:
        """
        Return all active LEO objects with fresh TLEs for conjunction screening.

        Deliberately restricts columns to what the screener needs —
        avoids fetching large JSONB payload fields for 50K rows.

        Parameters
        ----------
        max_altitude_km : float
            Upper altitude cutoff (default 2000 km = LEO/MEO boundary).
        min_altitude_km : float
            Lower cutoff (below 150 km → reentry imminent, skip).
        """
        result = await self.session.execute(
            select(Satellite).where(
                Satellite.perigee_km.isnot(None),
                Satellite.perigee_km >= min_altitude_km,
                Satellite.apogee_km <= max_altitude_km,
                Satellite.tle_line1.isnot(None),
                Satellite.tle_line2.isnot(None),
                Satellite.tle_age_days <= 7.0,
            )
        )
        return result.scalars().all()

    async def search_by_name(
        self,
        query: str,
        limit: int = 20,
    ) -> Sequence[Satellite]:
        """
        Fuzzy name search using the pg_trgm GIN index.

        The ``%`` operator uses trigram similarity — no LIKE needed.
        Requires pg_trgm extension (installed by migration 0001).
        """
        result = await self.session.execute(
            select(Satellite)
            .where(Satellite.name.op("%")(query))
            .order_by(
                text(f"similarity(name, '{query}') DESC")
            )
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_constellation(
        self,
        constellation: str,
        limit: int = 1000,
    ) -> Sequence[Satellite]:
        """Fetch all members of a constellation (e.g. 'STARLINK')."""
        result = await self.session.execute(
            select(Satellite)
            .where(Satellite.constellation == constellation.upper())
            .limit(limit)
        )
        return result.scalars().all()

    async def count_by_regime(self) -> dict[str, int]:
        """Return object counts per orbital regime (LEO/MEO/GEO/etc.)."""
        from sqlalchemy import func as sqlfunc
        result = await self.session.execute(
            select(Satellite.regime, sqlfunc.count(Satellite.id))
            .group_by(Satellite.regime)
        )
        return {row[0] or "unknown": row[1] for row in result.all()}
