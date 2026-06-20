"""ORBITIQ-X — Orbital events model (re-entry, manoeuvres, anomalies, space weather)."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_model import Base


class OrbitalEvent(Base):
    """
    Catch-all time-series event log for everything that happens to
    or around a satellite that isn't a conjunction.

    Event types:
      reentry_alert      — decay prediction / re-entry warning
      maneuver_detected  — observed ΔV from TLE delta analysis
      anomaly_detected   — unexpected orbital parameter change
      tle_gap            — tracking data gap > threshold
      space_weather      — Kp/F10.7 event affecting object
      launch             — new object detected in catalog
      fragmentation      — breakup event detected
      status_change      — operational status change
      pass_prediction    — scheduled AOS/LOS window
    """
    __tablename__ = "orbital_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── What and when ─────────────────────────────────────────
    norad_id: Mapped[Optional[int]] = mapped_column(Integer, index=True,
        comment="NORAD ID — NULL for system-level events (e.g. space weather)")
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, index=True,
        comment="When the event occurred or is predicted")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, server_default=func.now(),
        comment="When ORBITIQ-X first detected/computed this event")

    # ── Severity ──────────────────────────────────────────────
    severity: Mapped[str] = mapped_column(String(16), nullable=False,
        default="info", index=True,
        comment="critical | high | medium | low | info")
    alert_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by: Mapped[Optional[int]] = mapped_column(BigInteger,
        comment="FK → users.id")
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ── Re-entry specific fields ──────────────────────────────
    predicted_reentry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True))
    reentry_uncertainty_hours: Mapped[Optional[float]] = mapped_column(Float)
    reentry_lifetime_days: Mapped[Optional[float]] = mapped_column(Float)
    survival_probability: Mapped[Optional[float]] = mapped_column(Float,
        comment="Fraction of mass surviving atmospheric entry")

    # ── Maneuver specific fields ──────────────────────────────
    delta_v_kms: Mapped[Optional[float]] = mapped_column(Float,
        comment="Inferred ΔV magnitude (km/s)")
    pre_perigee_km: Mapped[Optional[float]] = mapped_column(Float)
    post_perigee_km: Mapped[Optional[float]] = mapped_column(Float)
    pre_apogee_km: Mapped[Optional[float]] = mapped_column(Float)
    post_apogee_km: Mapped[Optional[float]] = mapped_column(Float)

    # ── Anomaly specific fields ───────────────────────────────
    anomaly_parameter: Mapped[Optional[str]] = mapped_column(String(64),
        comment="Which parameter is anomalous e.g. bstar, decay_rate")
    anomaly_observed_value: Mapped[Optional[float]] = mapped_column(Float)
    anomaly_expected_value: Mapped[Optional[float]] = mapped_column(Float)
    anomaly_sigma: Mapped[Optional[float]] = mapped_column(Float,
        comment="Standard deviations from expected")

    # ── Space weather linkage ─────────────────────────────────
    kp_index: Mapped[Optional[float]] = mapped_column(Float)
    f107_flux: Mapped[Optional[float]] = mapped_column(Float)
    storm_category: Mapped[Optional[str]] = mapped_column(String(8),
        comment="G1 | G2 | G3 | G4 | G5 | none")

    # ── Free-form detail ──────────────────────────────────────
    title: Mapped[Optional[str]] = mapped_column(String(256))
    description: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB,
        comment="Type-specific structured payload")

    # ── Source ────────────────────────────────────────────────
    source_agent: Mapped[Optional[str]] = mapped_column(String(64),
        comment="Which ORBITIQ-X agent generated this event")
    data_source: Mapped[Optional[str]] = mapped_column(String(32),
        comment="spacetrack | celestrak | noaa | computed")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    satellite: Mapped[Optional["Satellite"]] = relationship(  # type: ignore[name-defined]
        back_populates="orbital_events",
        primaryjoin="OrbitalEvent.norad_id == foreign(Satellite.norad_id)",
        foreign_keys=[norad_id],
    )

    __table_args__ = (
        Index("ix_orbital_events_norad_type_time", "norad_id", "event_type", "event_time"),
        Index("ix_orbital_events_severity_ack", "severity", "acknowledged"),
        Index("ix_orbital_events_event_time", "event_time"),
        Index("ix_orbital_events_type_time", "event_type", "event_time"),
        # TimescaleDB hypertable candidate:
        # SELECT create_hypertable('orbital_events', 'event_time');
    )
