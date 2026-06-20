"""
ORBITIQ-X Backend — Orbital Events Repository

Handles the ``orbital_events`` time-series event log.

This table is a catch-all for everything that happens to or around
a satellite: re-entry alerts, manoeuvre detections, anomalies,
fragmentation events, and space weather impacts.

TimescaleDB note
────────────────
  If TimescaleDB is installed (migration 0008), this table is a
  hypertable partitioned by ``event_time`` in 7-day chunks.
  Queries that filter on ``event_time`` will use chunk exclusion
  for sub-millisecond response on billion-row archives.

  If plain PostgreSQL is used, the ix_orbital_events_event_time
  B-tree index covers the same query patterns at smaller scale.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, update, desc, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.orbital_events import OrbitalEvent
from .base import BaseRepository

logger = logging.getLogger(__name__)

_BULK_BATCH = 1000


class OrbitalEventRepository(BaseRepository[OrbitalEvent]):
    """Repository for the ``orbital_events`` time-series table."""

    model = OrbitalEvent

    async def log_event(self, data: dict) -> OrbitalEvent:
        """
        Insert a new orbital event. Events are append-only.

        Parameters
        ----------
        data : dict
            Field dict. Must include ``norad_id``, ``event_type``,
            ``event_time``, and ``severity``.
        """
        instance = OrbitalEvent(**data)
        return await self.add(instance)

    async def bulk_log(self, events: list[dict]) -> int:
        """Batch insert multiple events. Used after screening runs."""
        if not events:
            return 0
        for i in range(0, len(events), _BULK_BATCH):
            batch = events[i : i + _BULK_BATCH]
            await self.session.execute(
                insert(OrbitalEvent).values(batch).on_conflict_do_nothing()
            )
        await self.session.flush()
        logger.info("orbital_events_bulk_log count=%d", len(events))
        return len(events)

    async def get_for_object(
        self,
        norad_id: int,
        event_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> Sequence[OrbitalEvent]:
        """
        Return events for a specific satellite, optionally filtered
        by type and time range.
        """
        stmt = (
            select(OrbitalEvent)
            .where(OrbitalEvent.norad_id == norad_id)
            .order_by(desc(OrbitalEvent.event_time))
        )
        if event_type:
            stmt = stmt.where(OrbitalEvent.event_type == event_type)
        if start:
            stmt = stmt.where(OrbitalEvent.event_time >= start)
        if end:
            stmt = stmt.where(OrbitalEvent.event_time <= end)
        result = await self.session.execute(stmt.limit(limit))
        return result.scalars().all()

    async def get_unacknowledged(
        self,
        severity: str | None = None,
        limit: int = 100,
    ) -> Sequence[OrbitalEvent]:
        """Return events not yet acknowledged by an operator."""
        stmt = select(OrbitalEvent).where(
            OrbitalEvent.acknowledged == False  # noqa: E712
        )
        if severity:
            stmt = stmt.where(OrbitalEvent.severity == severity)
        result = await self.session.execute(
            stmt.order_by(desc(OrbitalEvent.event_time)).limit(limit)
        )
        return result.scalars().all()

    async def get_reentry_alerts(
        self,
        within_days: float = 14.0,
    ) -> Sequence[OrbitalEvent]:
        """Return active re-entry alerts within the next N days."""
        result = await self.session.execute(
            select(OrbitalEvent)
            .where(
                OrbitalEvent.event_type == "reentry_alert",
                OrbitalEvent.predicted_reentry_at.isnot(None),
                OrbitalEvent.predicted_reentry_at > text("NOW()"),
                OrbitalEvent.predicted_reentry_at
                < text(f"NOW() + INTERVAL '{within_days} days'"),
            )
            .order_by(OrbitalEvent.predicted_reentry_at)
        )
        return result.scalars().all()

    async def acknowledge(
        self,
        event_id: int,
        user_id: int,
    ) -> bool:
        """Mark an event as acknowledged by an operator."""
        result = await self.session.execute(
            update(OrbitalEvent)
            .where(OrbitalEvent.id == event_id)
            .values(acknowledged=True, acknowledged_by=user_id,
                    acknowledged_at=datetime.utcnow())
        )
        await self.session.flush()
        return result.rowcount > 0

    async def count_by_type_last_24h(self) -> dict[str, int]:
        """Diagnostic: event type distribution over the last 24h."""
        from sqlalchemy import func as sqlfunc
        result = await self.session.execute(
            select(OrbitalEvent.event_type, sqlfunc.count(OrbitalEvent.id))
            .where(OrbitalEvent.event_time > text("NOW() - INTERVAL '24 hours'"))
            .group_by(OrbitalEvent.event_type)
        )
        return {row[0]: row[1] for row in result.all()}
