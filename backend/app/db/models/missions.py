"""ORBITIQ-X — Mission model."""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_model import Base


class Mission(Base):
    """
    Aerospace mission — the programmatic unit linking an operator
    to one or more satellites launched for a common purpose.
    """
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mission_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True,
        comment="e.g. MSN-CHANDRAYAAN3, MSN-STARLINK-G6-29")
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(String(64))

    # ── Classification ────────────────────────────────────────
    mission_type: Mapped[str] = mapped_column(String(32), nullable=False,
        default="unknown",
        comment="eo | comms | nav | science | military | demo | weather | crewed")
    status: Mapped[str] = mapped_column(String(32), nullable=False,
        default="planned", index=True,
        comment="planned | active | completed | failed | extended | cancelled")

    # ── Ownership ─────────────────────────────────────────────
    operator_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True,
        comment="FK → operators.id")
    country_code: Mapped[Optional[str]] = mapped_column(String(3), index=True)
    agency: Mapped[Optional[str]] = mapped_column(String(64),
        comment="NASA | ESA | ISRO | JAXA | SpaceX | etc.")

    # ── Timeline ──────────────────────────────────────────────
    launch_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    design_lifetime_years: Mapped[Optional[float]] = mapped_column(Float)

    # ── Scope ─────────────────────────────────────────────────
    description: Mapped[Optional[str]] = mapped_column(Text)
    objectives: Mapped[Optional[list]] = mapped_column(ARRAY(Text),
        comment="List of mission objectives")
    target_orbit: Mapped[Optional[str]] = mapped_column(String(16),
        comment="LEO | SSO | MEO | GEO | HEO | Lunar | Mars")
    target_altitude_km: Mapped[Optional[float]] = mapped_column(Float)
    target_inclination_deg: Mapped[Optional[float]] = mapped_column(Float)
    satellite_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Budget ────────────────────────────────────────────────
    budget_musd: Mapped[Optional[float]] = mapped_column(Float,
        comment="Budget in millions of USD")

    # ── Links and metadata ────────────────────────────────────
    wikipedia_url: Mapped[Optional[str]] = mapped_column(String(512))
    nasa_url: Mapped[Optional[str]] = mapped_column(String(512))
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    is_crewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_commercial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )

    operator_rel: Mapped[Optional["Operator"]] = relationship(  # type: ignore[name-defined]
        back_populates="missions",
        primaryjoin="Mission.operator_id == Operator.id",
        foreign_keys=[operator_id],
    )

    __table_args__ = (
        UniqueConstraint("mission_id", name="uq_missions_mission_id"),
        Index("ix_missions_status_type", "status", "mission_type"),
        Index("ix_missions_launch_date", "launch_date"),
        Index("ix_missions_agency", "agency"),
    )
