"""ORBITIQ-X — TLE archive model."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger, DateTime, Float, Index, Integer,
    String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_model import Base


class TLERecord(Base):
    """
    Historical TLE archive — every TLE set ever received per object.

    Retention: unlimited (TimescaleDB compression after 30 days).
    Primary query patterns:
      - Latest TLE for a NORAD ID
      - TLE at a specific epoch (for historical propagation)
      - All TLEs for an object in a date range
    """
    __tablename__ = "tle_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True,
        comment="FK → satellites.norad_id (non-enforced for performance)")
    satellite_id: Mapped[Optional[int]] = mapped_column(BigInteger,
        comment="FK → satellites.id (populated async after ingest)")

    # ── TLE content ───────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    line1: Mapped[str] = mapped_column(String(70), nullable=False)
    line2: Mapped[str] = mapped_column(String(70), nullable=False)

    # ── Decoded fields (parsed once at ingest, indexed) ───────
    epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, index=True,
        comment="TLE epoch in UTC")
    epoch_year: Mapped[int] = mapped_column(Integer, nullable=False)
    epoch_day: Mapped[float] = mapped_column(Float, nullable=False)
    inclination_deg: Mapped[float] = mapped_column(Float, nullable=False)
    raan_deg: Mapped[float] = mapped_column(Float, nullable=False)
    eccentricity: Mapped[float] = mapped_column(Float, nullable=False)
    arg_perigee_deg: Mapped[float] = mapped_column(Float, nullable=False)
    mean_anomaly_deg: Mapped[float] = mapped_column(Float, nullable=False)
    mean_motion_rev_day: Mapped[float] = mapped_column(Float, nullable=False)
    bstar: Mapped[float] = mapped_column(Float, nullable=False,
        comment="SGP4 drag term (1/R_E)")
    n_dot: Mapped[float] = mapped_column(Float, nullable=False,
        comment="First derivative of mean motion (rev/day²)")
    n_ddot: Mapped[float] = mapped_column(Float, nullable=False,
        comment="Second derivative of mean motion (rev/day³)")
    element_set_num: Mapped[Optional[int]] = mapped_column(Integer)
    rev_number: Mapped[Optional[int]] = mapped_column(Integer)

    # ── Derived orbital elements ──────────────────────────────
    semi_major_axis_km: Mapped[Optional[float]] = mapped_column(Float)
    perigee_km: Mapped[Optional[float]] = mapped_column(Float)
    apogee_km: Mapped[Optional[float]] = mapped_column(Float)
    period_minutes: Mapped[Optional[float]] = mapped_column(Float)

    # ── Source & quality ──────────────────────────────────────
    source: Mapped[str] = mapped_column(String(32), nullable=False,
        default="celestrak",
        comment="celestrak | spacetrack | manual | sensor")
    checksum_ok: Mapped[bool] = mapped_column(
        nullable=False, default=True,
        comment="TLE line checksum validation result"
    )
    age_at_ingest_days: Mapped[Optional[float]] = mapped_column(Float,
        comment="TLE age (days) at time of ingestion")

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # relationship removed — cross-model string ref not resolvable at mapper config

    __table_args__ = (
        UniqueConstraint("norad_id", "epoch", "element_set_num",
                         name="uq_tle_norad_epoch_set"),
        Index("ix_tle_norad_epoch", "norad_id", "epoch"),
        Index("ix_tle_epoch", "epoch"),
        Index("ix_tle_source_ingested", "source", "ingested_at"),
        # NOTE: convert to TimescaleDB hypertable after creation:
        # SELECT create_hypertable('tle_records', 'epoch', chunk_time_interval => INTERVAL '30 days');
        # SELECT add_compression_policy('tle_records', INTERVAL '30 days');
    )
