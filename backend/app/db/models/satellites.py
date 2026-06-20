"""ORBITIQ-X — Satellite / RSO catalog model."""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_model import Base


class Satellite(Base):
    """
    Master catalog for all Resident Space Objects.
    Covers active satellites, defunct payloads, debris, and rocket bodies.
    """
    __tablename__ = "satellites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── Primary identifiers ───────────────────────────────────
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True,
        comment="USSPACECOM catalog number")
    cospar_id: Mapped[Optional[str]] = mapped_column(String(15), unique=True,
        comment="COSPAR international designator e.g. 1998-067A")
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    international_designator: Mapped[Optional[str]] = mapped_column(String(15))

    # ── Classification ────────────────────────────────────────
    object_type: Mapped[str] = mapped_column(String(32), nullable=False,
        comment="satellite | debris | rocket_body | unknown")
    mission_type: Mapped[Optional[str]] = mapped_column(String(32),
        comment="eo | comms | nav | science | weather | military | other")
    regime: Mapped[Optional[str]] = mapped_column(String(16), index=True,
        comment="VLEO | LEO | SSO | MEO | GEO | HEO | GTO | TLI | DSO")
    status: Mapped[str] = mapped_column(String(32), nullable=False,
        default="unknown", index=True,
        comment="operational | defunct | reentry | decayed | unknown")

    # ── Ownership ─────────────────────────────────────────────
    operator_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True,
        comment="FK → operators.id")
    country_code: Mapped[Optional[str]] = mapped_column(String(3), index=True)
    operator_name: Mapped[Optional[str]] = mapped_column(String(256),
        comment="Denormalised for fast display")

    # ── Launch metadata ───────────────────────────────────────
    launch_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    launch_site: Mapped[Optional[str]] = mapped_column(String(128))
    launch_vehicle: Mapped[Optional[str]] = mapped_column(String(128))
    decay_date: Mapped[Optional[date]] = mapped_column(Date)
    expected_eol: Mapped[Optional[date]] = mapped_column(Date)

    # ── Physical properties ───────────────────────────────────
    mass_kg: Mapped[Optional[float]] = mapped_column(Float)
    span_m: Mapped[Optional[float]] = mapped_column(Float,
        comment="Physical span metres")
    radar_cross_section_m2: Mapped[Optional[float]] = mapped_column(Float)
    hard_body_radius_km: Mapped[float] = mapped_column(Float,
        nullable=False, default=0.005,
        comment="HBR for conjunction screening (km)")

    # ── Latest orbital elements (cached, refreshed with TLE) ─
    perigee_km: Mapped[Optional[float]] = mapped_column(Float)
    apogee_km: Mapped[Optional[float]] = mapped_column(Float)
    inclination_deg: Mapped[Optional[float]] = mapped_column(Float)
    raan_deg: Mapped[Optional[float]] = mapped_column(Float)
    eccentricity: Mapped[Optional[float]] = mapped_column(Float)
    mean_motion_rev_day: Mapped[Optional[float]] = mapped_column(Float)
    period_minutes: Mapped[Optional[float]] = mapped_column(Float)
    altitude_km: Mapped[Optional[float]] = mapped_column(Float,
        comment="Mean altitude (km)")

    # ── Latest TLE (cached) ───────────────────────────────────
    tle_line1: Mapped[Optional[str]] = mapped_column(String(70))
    tle_line2: Mapped[Optional[str]] = mapped_column(String(70))
    tle_epoch: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tle_age_days: Mapped[Optional[float]] = mapped_column(Float)
    tle_source: Mapped[Optional[str]] = mapped_column(String(32),
        comment="celestrak | spacetrack | manual")
    bstar: Mapped[Optional[float]] = mapped_column(Float,
        comment="SGP4 drag coefficient (1/R_E)")

    # ── Constellation membership ──────────────────────────────
    constellation: Mapped[Optional[str]] = mapped_column(String(64), index=True,
        comment="STARLINK | ONEWEB | GPS | GALILEO | etc.")
    constellation_shell: Mapped[Optional[int]] = mapped_column(Integer)
    constellation_plane: Mapped[Optional[int]] = mapped_column(Integer)
    constellation_slot: Mapped[Optional[int]] = mapped_column(Integer)

    # ── Metadata ──────────────────────────────────────────────
    extra: Mapped[Optional[dict]] = mapped_column(JSONB,
        comment="Flexible payload for non-schema fields")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────
    operator_rel: Mapped[Optional["Operator"]] = relationship(  # type: ignore[name-defined]
        back_populates="satellites",
        primaryjoin="Satellite.operator_id == Operator.id",
        foreign_keys=[operator_id],
    )
    tle_records: Mapped[list["TLERecord"]] = relationship(  # type: ignore[name-defined]
        back_populates="satellite", cascade="all, delete-orphan",
        primaryjoin="Satellite.norad_id == foreign(TLERecord.norad_id)",
    )
    conjunction_events_primary: Mapped[list["ConjunctionEvent"]] = relationship(  # type: ignore[name-defined]
        back_populates="primary_satellite",
        primaryjoin="Satellite.norad_id == foreign(ConjunctionEvent.primary_norad)",
        foreign_keys="ConjunctionEvent.primary_norad",
    )
    orbital_events: Mapped[list["OrbitalEvent"]] = relationship(  # type: ignore[name-defined]
        back_populates="satellite",
        primaryjoin="Satellite.norad_id == foreign(OrbitalEvent.norad_id)",
    )

    __table_args__ = (
        UniqueConstraint("norad_id", name="uq_satellites_norad"),
        Index("ix_satellites_regime_status", "regime", "status"),
        Index("ix_satellites_constellation", "constellation"),
        Index("ix_satellites_launch_date", "launch_date"),
        Index("ix_satellites_perigee", "perigee_km"),
        Index("ix_satellites_country", "country_code"),
        Index("ix_satellites_updated", "updated_at"),
    )
