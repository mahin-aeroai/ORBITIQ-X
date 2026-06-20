"""ORBITIQ-X — Conjunction event (CDM) archive model."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_model import Base


class ConjunctionEvent(Base):
    """
    Conjunction Data Message (CDM) archive.

    One row = one conjunction screening result.
    Multiple CDM updates for the same event are new rows
    (append-only) to preserve the decision audit trail.

    Risk level thresholds:
      RED    : Pc >= 1e-3
      YELLOW : Pc >= 1e-4
      GREEN  : Pc >= 1e-5
      WHITE  : Pc <  1e-5
    """
    __tablename__ = "conjunction_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conjunction_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True,
        comment="Unique CDM identifier e.g. CDM-20240315-025544-029777")

    # ── Primary object ────────────────────────────────────────
    primary_norad: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    primary_name: Mapped[Optional[str]] = mapped_column(String(256))
    primary_type: Mapped[Optional[str]] = mapped_column(String(32),
        comment="satellite | debris | rocket_body")

    # ── Secondary object ──────────────────────────────────────
    secondary_norad: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    secondary_name: Mapped[Optional[str]] = mapped_column(String(256))
    secondary_type: Mapped[Optional[str]] = mapped_column(String(32))

    # ── TCA and geometry ──────────────────────────────────────
    tca: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, index=True,
        comment="Time of Closest Approach (UTC)")
    miss_distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    relative_velocity_kms: Mapped[float] = mapped_column(Float, nullable=False,
        comment="Relative speed at TCA (km/s)")

    # ── Collision probability ─────────────────────────────────
    collision_probability: Mapped[float] = mapped_column(Float, nullable=False,
        comment="Foster (2001) Pc")
    collision_probability_method: Mapped[str] = mapped_column(String(32),
        nullable=False, default="Foster2001")
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, index=True,
        comment="red | yellow | green | white")

    # ── Covariance ────────────────────────────────────────────
    primary_sigma_r_km: Mapped[Optional[float]] = mapped_column(Float,
        comment="Primary position uncertainty radial (km)")
    primary_sigma_t_km: Mapped[Optional[float]] = mapped_column(Float,
        comment="Primary position uncertainty transverse (km)")
    primary_sigma_n_km: Mapped[Optional[float]] = mapped_column(Float,
        comment="Primary position uncertainty normal (km)")
    secondary_sigma_r_km: Mapped[Optional[float]] = mapped_column(Float)
    secondary_sigma_t_km: Mapped[Optional[float]] = mapped_column(Float)
    secondary_sigma_n_km: Mapped[Optional[float]] = mapped_column(Float)
    combined_hbr_km: Mapped[Optional[float]] = mapped_column(Float,
        comment="Combined hard-body radius (km)")

    # ── B-plane parameters ────────────────────────────────────
    sigma_major_km: Mapped[Optional[float]] = mapped_column(Float,
        comment="Collision plane covariance major axis (km)")
    sigma_minor_km: Mapped[Optional[float]] = mapped_column(Float,
        comment="Collision plane covariance minor axis (km)")

    # ── Maneuver decision ─────────────────────────────────────
    maneuver_required: Mapped[bool] = mapped_column(Boolean,
        nullable=False, default=False)
    maneuver_window_open: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True))
    maneuver_window_close: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Latest time to maneuver before TCA")
    recommended_dv_kms: Mapped[Optional[float]] = mapped_column(Float,
        comment="Recommended ΔV magnitude (km/s)")

    # ── Resolution ────────────────────────────────────────────
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution: Mapped[Optional[str]] = mapped_column(String(32),
        comment="maneuver | natural_miss | conjunction_occurred | expired")
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger,
        comment="FK → users.id — operator who closed the event")

    # ── Screening metadata ────────────────────────────────────
    screening_org: Mapped[str] = mapped_column(String(64),
        nullable=False, default="ORBITIQ-X")
    data_source: Mapped[Optional[str]] = mapped_column(String(32),
        comment="spacetrack | leolabs | manual")
    cdm_issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────
    primary_satellite: Mapped[Optional["Satellite"]] = relationship(  # type: ignore[name-defined]
        back_populates="conjunction_events_primary",
        primaryjoin="ConjunctionEvent.primary_norad == foreign(Satellite.norad_id)",
        foreign_keys=[primary_norad],
    )

    __table_args__ = (
        Index("ix_conj_tca_pc", "tca", "collision_probability"),
        Index("ix_conj_primary_tca", "primary_norad", "tca"),
        Index("ix_conj_secondary_tca", "secondary_norad", "tca"),
        Index("ix_conj_risk_resolved", "risk_level", "resolved"),
        Index("ix_conj_resolved_at", "resolved_at"),
    )
