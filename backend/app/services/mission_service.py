"""
ORBITIQ-X — Mission Intelligence Service
==========================================
Provides programmatic access to the missions table.
Foundation layer for future Knowledge Graph and GraphRAG integration.

The missions table already has a complete schema (created in Alembic
migration 0006_create_missions). This service adds the query layer.

Future integrations (NOT built in Phase 13D)
─────────────────────────────────────────────
  • Neo4j: Mission → [:USES] → LaunchVehicle, [:OPERATES] → Satellite
  • GraphRAG: corpus links to mission documents
  • Mission Dashboard: timeline + conjunction risk overlay
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Sequence

from sqlalchemy import func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.missions import Mission

logger = logging.getLogger(__name__)


def _mission_to_dict(m: Mission) -> dict[str, Any]:
    """Serialise a Mission ORM row to a JSON-safe dict."""
    return {
        "id":                    m.id,
        "mission_id":            m.mission_id,
        "name":                  m.name,
        "short_name":            m.short_name,
        "mission_type":          m.mission_type,
        "status":                m.status,
        "operator_id":           m.operator_id,
        "country_code":          m.country_code,
        "agency":                m.agency,
        "launch_date":           m.launch_date.isoformat() if m.launch_date else None,
        "end_date":              m.end_date.isoformat() if m.end_date else None,
        "design_lifetime_years": m.design_lifetime_years,
        "description":           m.description,
        "objectives":            m.objectives or [],
        "target_orbit":          m.target_orbit,
        "target_altitude_km":    m.target_altitude_km,
        "target_inclination_deg":m.target_inclination_deg,
        "satellite_count":       m.satellite_count,
        "budget_musd":           m.budget_musd,
        "wikipedia_url":         m.wikipedia_url,
        "nasa_url":              m.nasa_url,
        "is_crewed":             m.is_crewed,
        "is_commercial":         m.is_commercial,
        "created_at":            m.created_at.isoformat() if m.created_at else None,
        "updated_at":            m.updated_at.isoformat() if m.updated_at else None,
    }


class MissionService:
    """
    Query service for the missions table.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_missions(
        self,
        status: str | None = None,
        mission_type: str | None = None,
        agency: str | None = None,
        country_code: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """
        Return a paginated list of missions with optional filters.

        Parameters
        ----------
        status : str | None
            Filter by mission status (planned | active | completed | failed | extended | cancelled).
        mission_type : str | None
            Filter by mission type (eo | comms | nav | science | military | demo | weather | crewed).
        agency : str | None
            Filter by agency name (case-insensitive partial match).
        country_code : str | None
            ISO 3166-1 alpha-3 country code.
        page, per_page : int
            Pagination.
        """
        conditions = []
        if status:
            conditions.append(Mission.status == status.lower())
        if mission_type:
            conditions.append(Mission.mission_type == mission_type.lower())
        if agency:
            conditions.append(Mission.agency.ilike(f"%{agency}%"))
        if country_code:
            conditions.append(Mission.country_code == country_code.upper())

        where = and_(*conditions) if conditions else True

        # Total count
        count_result = await self.session.execute(
            select(func.count(Mission.id)).where(where)
        )
        total = count_result.scalar_one_or_none() or 0

        # Paginated rows
        offset = (page - 1) * per_page
        rows_result = await self.session.execute(
            select(Mission)
            .where(where)
            .order_by(Mission.launch_date.desc().nullslast(), Mission.name)
            .limit(per_page)
            .offset(offset)
        )
        missions = rows_result.scalars().all()

        return {
            "total":    total,
            "page":     page,
            "per_page": per_page,
            "has_next": (page * per_page) < total,
            "items":    [_mission_to_dict(m) for m in missions],
        }

    async def get_mission(self, mission_id: str) -> dict[str, Any] | None:
        """
        Return a single mission by mission_id string (e.g. 'MSN-CHANDRAYAAN3').
        Returns None if not found.
        """
        result = await self.session.execute(
            select(Mission).where(Mission.mission_id == mission_id)
        )
        m = result.scalar_one_or_none()
        return _mission_to_dict(m) if m else None

    async def get_missions_by_operator(
        self,
        operator_name: str,
        page: int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """
        Return missions associated with an operator (agency name match).
        Partial, case-insensitive match on agency field.
        """
        where = Mission.agency.ilike(f"%{operator_name}%")

        count_result = await self.session.execute(
            select(func.count(Mission.id)).where(where)
        )
        total = count_result.scalar_one_or_none() or 0

        offset = (page - 1) * per_page
        rows_result = await self.session.execute(
            select(Mission)
            .where(where)
            .order_by(Mission.launch_date.desc().nullslast())
            .limit(per_page)
            .offset(offset)
        )
        missions = rows_result.scalars().all()

        return {
            "operator":  operator_name,
            "total":     total,
            "page":      page,
            "per_page":  per_page,
            "has_next":  (page * per_page) < total,
            "items":     [_mission_to_dict(m) for m in missions],
        }

    async def get_statistics(self) -> dict[str, Any]:
        """
        Return aggregate mission statistics.
        Covers status distribution, type distribution, and agency breakdown.
        """
        total_result = await self.session.execute(select(func.count(Mission.id)))
        total = total_result.scalar_one_or_none() or 0

        # By status
        status_rows = await self.session.execute(
            select(Mission.status, func.count(Mission.id).label("n"))
            .group_by(Mission.status)
            .order_by(func.count(Mission.id).desc())
        )
        by_status = {r.status: r.n for r in status_rows}

        # By type
        type_rows = await self.session.execute(
            select(Mission.mission_type, func.count(Mission.id).label("n"))
            .group_by(Mission.mission_type)
            .order_by(func.count(Mission.id).desc())
        )
        by_type = {r.mission_type: r.n for r in type_rows}

        # Top agencies
        agency_rows = await self.session.execute(
            select(Mission.agency, func.count(Mission.id).label("n"))
            .where(Mission.agency.isnot(None))
            .group_by(Mission.agency)
            .order_by(func.count(Mission.id).desc())
            .limit(10)
        )
        top_agencies = [{"agency": r.agency, "count": r.n} for r in agency_rows]

        # Active crewed missions
        crewed_result = await self.session.execute(
            select(func.count(Mission.id))
            .where(Mission.is_crewed == True, Mission.status == "active")  # noqa: E712
        )
        active_crewed = crewed_result.scalar_one_or_none() or 0

        # Total satellite count across active missions
        sat_result = await self.session.execute(
            select(func.sum(Mission.satellite_count))
            .where(Mission.status.in_(["active", "extended"]))
        )
        active_satellites = sat_result.scalar_one_or_none() or 0

        return {
            "total_missions":          total,
            "by_status":               by_status,
            "by_type":                 by_type,
            "top_agencies":            top_agencies,
            "active_crewed_missions":  active_crewed,
            "active_satellite_count":  active_satellites,
            "generated_at":            datetime.now(timezone.utc).isoformat(),
        }
