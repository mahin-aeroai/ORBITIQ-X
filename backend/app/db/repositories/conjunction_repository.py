"""
ORBITIQ-X Backend — Conjunction Events Repository

Handles the CDM (Conjunction Data Message) archive.

The conjunction_events table is append-only by policy — every update
to a conjunction's Pc or miss distance creates a new row, preserving
the full decision audit trail. Resolution is tracked as a column on
the most recent row for that conjunction_id.

Query patterns (in priority order)
────────────────────────────────────
  1. get_unresolved_red_yellow() — ops dashboard hot path (< 10ms)
  2. get_for_object()            — object history page
  3. get_by_id()                 — CDM detail view
  4. bulk_insert()               — post-screening ingest (100s of CDMs)
  5. resolve()                   — operator closes an event

Index coverage (from migration 0007)
─────────────────────────────────────
  ix_conj_tca_pc         — for risk-sorted dashboards
  ix_conj_primary_tca    — for object history
  ix_conj_risk_resolved  — for unresolved red/yellow filter (hot path)
  ix_conj_active_red     — partial index, unresolved red+yellow only
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, update, desc, and_, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conjunction_events import ConjunctionEvent
from .base import BaseRepository

logger = logging.getLogger(__name__)

_BULK_BATCH = 500


class ConjunctionRepository(BaseRepository[ConjunctionEvent]):
    """Repository for the ``conjunction_events`` CDM archive."""

    model = ConjunctionEvent

    async def insert_cdm(self, data: dict) -> ConjunctionEvent:
        """
        Insert a new CDM record. Each screening produces a new row —
        even if this is an update to an existing conjunction_id.

        The unique constraint is on conjunction_id only for the
        first CDM per event. Subsequent screenings for the same
        pair use different conjunction_ids with timestamp suffix.
        """
        stmt = (
            insert(ConjunctionEvent)
            .values(**data)
            .on_conflict_do_update(
                index_elements=["conjunction_id"],
                set_={
                    k: text(f"EXCLUDED.{k}")
                    for k in data.keys()
                    if k not in ("id", "conjunction_id", "created_at")
                },
            )
            .returning(ConjunctionEvent)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        row = result.scalar_one()
        logger.debug(
            "cdm_inserted id=%s risk=%s Pc=%.2e",
            row.conjunction_id, row.risk_level, row.collision_probability,
        )
        return row

    async def bulk_insert(self, records: list[dict]) -> int:
        """
        Batch insert CDMs after a full conjunction screening run.

        On conflict (same conjunction_id), updates the Pc, miss distance,
        and risk level — CDMs can be re-screened with updated covariance.

        Parameters
        ----------
        records : list[dict]
            CDM field dicts.

        Returns
        -------
        int
            Rows upserted.
        """
        if not records:
            return 0

        total = 0
        for i in range(0, len(records), _BULK_BATCH):
            batch = records[i : i + _BULK_BATCH]
            stmt = (
                insert(ConjunctionEvent)
                .values(batch)
                .on_conflict_do_update(
                    index_elements=["conjunction_id"],
                    set_={
                        "collision_probability": text("EXCLUDED.collision_probability"),
                        "miss_distance_km": text("EXCLUDED.miss_distance_km"),
                        "risk_level": text("EXCLUDED.risk_level"),
                        "maneuver_required": text("EXCLUDED.maneuver_required"),
                        "maneuver_window_close": text("EXCLUDED.maneuver_window_close"),
                        "recommended_dv_kms": text("EXCLUDED.recommended_dv_kms"),
                        "updated_at": text("NOW()"),
                    },
                )
            )
            result = await self.session.execute(stmt)
            total += result.rowcount

        await self.session.flush()
        logger.info("cdm_bulk_insert_complete total=%d", total)
        return total

    async def get_unresolved_red_yellow(
        self,
        limit: int = 200,
    ) -> Sequence[ConjunctionEvent]:
        """
        Return all unresolved red and yellow conjunction events sorted
        by Pc descending. This is the ops dashboard hot path.

        Uses the partial index ``ix_conj_active_red`` for sub-5ms performance
        at 1M rows.

        Parameters
        ----------
        limit : int
            Maximum rows (default 200 — enough for a full ops shift).
        """
        result = await self.session.execute(
            select(ConjunctionEvent)
            .where(
                ConjunctionEvent.resolved == False,  # noqa: E712
                ConjunctionEvent.risk_level.in_(["red", "yellow"]),
            )
            .order_by(desc(ConjunctionEvent.collision_probability))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_for_object(
        self,
        norad_id: int,
        limit: int = 100,
        include_resolved: bool = False,
    ) -> Sequence[ConjunctionEvent]:
        """
        Return conjunction events where norad_id is either primary or secondary.
        """
        stmt = select(ConjunctionEvent).where(
            (ConjunctionEvent.primary_norad == norad_id)
            | (ConjunctionEvent.secondary_norad == norad_id)
        )
        if not include_resolved:
            stmt = stmt.where(ConjunctionEvent.resolved == False)  # noqa: E712
        result = await self.session.execute(
            stmt.order_by(desc(ConjunctionEvent.tca)).limit(limit)
        )
        return result.scalars().all()

    async def get_by_conjunction_id(
        self, conjunction_id: str
    ) -> ConjunctionEvent | None:
        """Fetch a CDM by its unique string ID."""
        result = await self.session.execute(
            select(ConjunctionEvent).where(
                ConjunctionEvent.conjunction_id == conjunction_id
            )
        )
        return result.scalar_one_or_none()

    async def resolve(
        self,
        conjunction_id: str,
        resolution: str,
        resolved_by_user_id: int | None = None,
    ) -> bool:
        """
        Mark a conjunction event as resolved.

        Parameters
        ----------
        conjunction_id : str
            The conjunction event's unique ID.
        resolution : str
            One of: maneuver | natural_miss | conjunction_occurred | expired
        resolved_by_user_id : int | None
            The operator who resolved it (None for automated resolution).

        Returns
        -------
        bool
            True if the row was updated, False if not found.
        """
        result = await self.session.execute(
            update(ConjunctionEvent)
            .where(ConjunctionEvent.conjunction_id == conjunction_id)
            .values(
                resolved=True,
                resolution=resolution,
                resolved_at=datetime.utcnow(),
                resolved_by_user_id=resolved_by_user_id,
            )
        )
        await self.session.flush()
        if result.rowcount:
            logger.info(
                "cdm_resolved id=%s resolution=%s by=%s",
                conjunction_id, resolution, resolved_by_user_id,
            )
        return result.rowcount > 0

    async def get_approaching_tca(
        self,
        within_hours: float = 72.0,
        min_pc: float = 1e-5,
    ) -> Sequence[ConjunctionEvent]:
        """
        Return unresolved events with TCA within the next N hours above min_pc.

        Used by the scheduler to generate approaching-TCA alerts.
        """
        result = await self.session.execute(
            select(ConjunctionEvent)
            .where(
                ConjunctionEvent.resolved == False,  # noqa: E712
                ConjunctionEvent.tca > text("NOW()"),
                ConjunctionEvent.tca < text(f"NOW() + INTERVAL '{within_hours} hours'"),
                ConjunctionEvent.collision_probability >= min_pc,
            )
            .order_by(ConjunctionEvent.tca)
        )
        return result.scalars().all()

    async def stats_by_risk_level(self) -> dict[str, int]:
        """Return count of unresolved events per risk level."""
        from sqlalchemy import func as sqlfunc
        result = await self.session.execute(
            select(
                ConjunctionEvent.risk_level,
                sqlfunc.count(ConjunctionEvent.id),
            )
            .where(ConjunctionEvent.resolved == False)  # noqa: E712
            .group_by(ConjunctionEvent.risk_level)
        )
        return {row[0]: row[1] for row in result.all()}
