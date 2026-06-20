"""
ORBITIQ-X Orbital Engine
Database Models — SQLAlchemy 2.0 (async)

Schema designed for PostgreSQL 16 with TimescaleDB for ephemeris.

Tables:
  rso_catalog       — Resident Space Object master record
  tle_archive       — Historical TLE sets per object
  ephemeris         — Propagated state vectors (hypertable via TimescaleDB)
  ground_track      — Subsatellite point sequences
  pass_events       — AOS/LOS pass windows per ground station
  conjunction_events — CDM archive
  reentry_alerts    — Decay prediction history
  ground_stations   — Observer sites
  scheduler_jobs    — APScheduler job state
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── RSO Catalog ───────────────────────────────────────────────

class RSOCatalog(Base):
    """Master catalog for all Resident Space Objects."""
    __tablename__ = "rso_catalog"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, unique=True)
    cospar_id: Mapped[Optional[str]] = mapped_column(String(15), unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    object_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="satellite | debris | rocket_body | unknown"
    )
    country_code: Mapped[Optional[str]] = mapped_column(String(3))
    operator: Mapped[Optional[str]] = mapped_column(String(128))

    # Orbital regime (denormalized for fast filtering)
    regime: Mapped[Optional[str]] = mapped_column(
        String(16), index=True,
        comment="LEO | SSO | MEO | GEO | HEO | GTO | VLEO | TLI | DSO"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", index=True,
        comment="operational | defunct | reentry | unknown | rocket_body"
    )

    # Latest orbital elements (cached)
    perigee_km: Mapped[Optional[float]] = mapped_column(Float)
    apogee_km: Mapped[Optional[float]] = mapped_column(Float)
    inclination_deg: Mapped[Optional[float]] = mapped_column(Float)
    mean_motion_rev_day: Mapped[Optional[float]] = mapped_column(Float)
    eccentricity: Mapped[Optional[float]] = mapped_column(Float)
    bstar: Mapped[Optional[float]] = mapped_column(Float)

    # Physical properties
    mass_kg: Mapped[Optional[float]] = mapped_column(Float)
    radar_cross_section_m2: Mapped[Optional[float]] = mapped_column(Float)
    hbr_km: Mapped[float] = mapped_column(Float, default=0.005, comment="Hard-body radius km")

    # Latest TLE (cached for fast access)
    tle_line1: Mapped[Optional[str]] = mapped_column(String(70))
    tle_line2: Mapped[Optional[str]] = mapped_column(String(70))
    tle_epoch: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tle_age_days: Mapped[Optional[float]] = mapped_column(Float)

    launch_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reentry_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tle_history: Mapped[list["TLEArchive"]] = relationship(back_populates="rso")
    pass_events: Mapped[list["PassEvent"]] = relationship(back_populates="rso")

    __table_args__ = (
        Index("ix_rso_regime_status", "regime", "status"),
        Index("ix_rso_perigee", "perigee_km"),
        Index("ix_rso_country", "country_code"),
    )


# ── TLE Archive ───────────────────────────────────────────────

class TLEArchive(Base):
    """Historical TLE sets — all versions retained for comparison."""
    __tablename__ = "tle_archive"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rso_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    line1: Mapped[str] = mapped_column(String(70), nullable=False)
    line2: Mapped[str] = mapped_column(String(70), nullable=False)
    name: Mapped[str] = mapped_column(String(256))
    epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), comment="celestrak | spacetrack | manual")
    element_set_num: Mapped[Optional[int]] = mapped_column(Integer)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    rso: Mapped[Optional["RSOCatalog"]] = relationship(back_populates="tle_history",
        primaryjoin="TLEArchive.norad_id == RSOCatalog.norad_id",
        foreign_keys="TLEArchive.norad_id")

    __table_args__ = (
        UniqueConstraint("norad_id", "epoch", "element_set_num", name="uq_tle_norad_epoch_set"),
        Index("ix_tle_norad_epoch", "norad_id", "epoch"),
    )


# ── Ephemeris (TimescaleDB hypertable) ────────────────────────

class EphemerisPoint(Base):
    """
    Propagated state vectors at discrete epochs.
    Partitioned by time via TimescaleDB hypertable.
    Partition interval: 1 day.
    Retention policy: 30 days (raw), compressed after 7 days.
    """
    __tablename__ = "ephemeris"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ECI J2000 state (km, km/s)
    x_km: Mapped[float] = mapped_column(Float, nullable=False)
    y_km: Mapped[float] = mapped_column(Float, nullable=False)
    z_km: Mapped[float] = mapped_column(Float, nullable=False)
    vx_kms: Mapped[float] = mapped_column(Float, nullable=False)
    vy_kms: Mapped[float] = mapped_column(Float, nullable=False)
    vz_kms: Mapped[float] = mapped_column(Float, nullable=False)

    # Geodetic (computed)
    lat_deg: Mapped[Optional[float]] = mapped_column(Float)
    lon_deg: Mapped[Optional[float]] = mapped_column(Float)
    alt_km: Mapped[Optional[float]] = mapped_column(Float)

    # Propagator metadata
    propagator: Mapped[str] = mapped_column(String(16), default="sgp4")
    tle_epoch: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_eph_norad_epoch", "norad_id", "epoch"),
        # TimescaleDB hypertable created via migration script:
        # SELECT create_hypertable('ephemeris', 'epoch', chunk_time_interval => INTERVAL '1 day');
        # SELECT add_compression_policy('ephemeris', INTERVAL '7 days');
        # SELECT add_retention_policy('ephemeris', INTERVAL '30 days');
    )


# ── Ground Track ──────────────────────────────────────────────

class GroundTrack(Base):
    """Subsatellite point sequence for a given computation window."""
    __tablename__ = "ground_track"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    start_epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    step_seconds: Mapped[int] = mapped_column(Integer, default=60)
    # Stored as JSONB: [{epoch, lat, lon, alt, speed}]
    points: Mapped[dict] = mapped_column(JSONB, nullable=False)
    num_orbits: Mapped[Optional[float]] = mapped_column(Float)


# ── Pass Events ───────────────────────────────────────────────

class GroundStation(Base):
    """Observer site for pass prediction."""
    __tablename__ = "ground_stations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    lat_deg: Mapped[float] = mapped_column(Float, nullable=False)
    lon_deg: Mapped[float] = mapped_column(Float, nullable=False)
    alt_km: Mapped[float] = mapped_column(Float, default=0.0)
    min_elevation_deg: Mapped[float] = mapped_column(Float, default=5.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    pass_events: Mapped[list["PassEvent"]] = relationship(back_populates="station")


class PassEvent(Base):
    """AOS/LOS pass window prediction."""
    __tablename__ = "pass_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rso_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    aos: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    los: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_elevation_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    max_elevation_deg: Mapped[float] = mapped_column(Float, nullable=False)
    aos_azimuth_deg: Mapped[Optional[float]] = mapped_column(Float)
    los_azimuth_deg: Mapped[Optional[float]] = mapped_column(Float)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rso: Mapped[Optional["RSOCatalog"]] = relationship(back_populates="pass_events",
        primaryjoin="PassEvent.norad_id == RSOCatalog.norad_id",
        foreign_keys="PassEvent.norad_id")
    station: Mapped[Optional["GroundStation"]] = relationship(back_populates="pass_events",
        primaryjoin="PassEvent.site_id == GroundStation.site_id",
        foreign_keys="PassEvent.site_id")

    __table_args__ = (
        UniqueConstraint("norad_id", "site_id", "aos", name="uq_pass_norad_site_aos"),
        Index("ix_pass_site_aos", "site_id", "aos"),
    )


# ── Conjunction Events ────────────────────────────────────────

class ConjunctionEvent(Base):
    """CDM archive — one row per conjunction event."""
    __tablename__ = "conjunction_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conjunction_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tca: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    primary_norad: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    secondary_norad: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    primary_name: Mapped[Optional[str]] = mapped_column(String(256))
    secondary_name: Mapped[Optional[str]] = mapped_column(String(256))

    miss_distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    relative_velocity_kms: Mapped[float] = mapped_column(Float, nullable=False)
    collision_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False,
        comment="red | yellow | green | white"
    )
    combined_hbr_km: Mapped[float] = mapped_column(Float)
    sigma_major_km: Mapped[Optional[float]] = mapped_column(Float)
    sigma_minor_km: Mapped[Optional[float]] = mapped_column(Float)

    screening_org: Mapped[str] = mapped_column(String(64), default="ORBITIQ-X")
    pc_method: Mapped[str] = mapped_column(String(32), default="Foster2001")
    maneuver_required: Mapped[bool] = mapped_column(Boolean, default=False)
    maneuver_window: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution: Mapped[Optional[str]] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_cdm_tca_pc", "tca", "collision_probability"),
        Index("ix_cdm_primary", "primary_norad", "tca"),
        Index("ix_cdm_risk", "risk_level", "resolved"),
    )


# ── Re-entry Alerts ───────────────────────────────────────────

class ReentryAlert(Base):
    """Decay prediction history and alert state."""
    __tablename__ = "reentry_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    object_name: Mapped[str] = mapped_column(String(256))

    predicted_reentry: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uncertainty_hours: Mapped[float] = mapped_column(Float)
    lifetime_days: Mapped[float] = mapped_column(Float)
    current_perigee_km: Mapped[float] = mapped_column(Float)
    decay_rate_km_day: Mapped[float] = mapped_column(Float)
    alert_level: Mapped[str] = mapped_column(String(16))
    survival_probability: Mapped[float] = mapped_column(Float, default=0.0)
    f107_index: Mapped[Optional[float]] = mapped_column(Float)

    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_reentry_norad_computed", "norad_id", "computed_at"),
        Index("ix_reentry_epoch", "predicted_reentry"),
    )
