"""ORBITIQ-X — Immutable audit log model."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_model import Base


class AuditLog(Base):
    """
    Immutable audit trail for all security-relevant and
    operational actions in ORBITIQ-X.

    Design: append-only. No UPDATE or DELETE ever touches this table.
    Retention: minimum 2 years (regulatory). Archive to cold storage after 90 days.

    Captures:
      - Auth events (login, logout, failed login, API key use)
      - Data mutations (satellite edits, conjunction resolutions)
      - Agent actions (maneuver recommendations, safety gate decisions)
      - Admin actions (user role changes, system config)
      - API access (rate limit hits, unusual query patterns)
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), index=True,
        comment="Immutable timestamp — never the application clock"
    )

    # ── Who ───────────────────────────────────────────────────
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True,
        comment="FK → users.id — NULL for system/agent actions")
    username: Mapped[Optional[str]] = mapped_column(String(64),
        comment="Denormalised snapshot in case user is later deleted")
    session_id: Mapped[Optional[int]] = mapped_column(BigInteger,
        comment="FK → user_sessions.id")
    api_key_prefix: Mapped[Optional[str]] = mapped_column(String(12),
        comment="First 12 chars of API key used (never the full key)")
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    # ── What ──────────────────────────────────────────────────
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True,
        comment="login | logout | login_failed | satellite_update | "
                "conjunction_resolve | maneuver_approve | user_role_change | ...")
    resource_type: Mapped[Optional[str]] = mapped_column(String(64),
        comment="satellite | conjunction_event | user | mission | agent_task")
    resource_id: Mapped[Optional[str]] = mapped_column(String(128),
        comment="PK of the affected resource (string for cross-type)")

    # ── Detail ────────────────────────────────────────────────
    outcome: Mapped[str] = mapped_column(String(16), nullable=False,
        default="success",
        comment="success | failure | error | blocked")
    description: Mapped[Optional[str]] = mapped_column(Text)
    before_state: Mapped[Optional[dict]] = mapped_column(JSONB,
        comment="Snapshot of resource before mutation (redacted)")
    after_state: Mapped[Optional[dict]] = mapped_column(JSONB,
        comment="Snapshot of resource after mutation (redacted)")
    extra: Mapped[Optional[dict]] = mapped_column(JSONB,
        comment="Additional structured context")

    # ── Request context ───────────────────────────────────────
    request_id: Mapped[Optional[str]] = mapped_column(String(64),
        comment="X-Request-ID header value for correlation")
    endpoint: Mapped[Optional[str]] = mapped_column(String(256),
        comment="HTTP path e.g. /api/v1/conjunction/{id}/resolve")
    http_method: Mapped[Optional[str]] = mapped_column(String(8))
    response_status: Mapped[Optional[int]] = mapped_column(Integer)
    duration_ms: Mapped[Optional[float]] = mapped_column(
        comment="Request duration in milliseconds")

    # ── Agent context (for agentic actions) ──────────────────
    agent_name: Mapped[Optional[str]] = mapped_column(String(64),
        comment="Which ORBITIQ-X agent triggered this (if applicable)")
    task_id: Mapped[Optional[str]] = mapped_column(String(64),
        comment="Agent task UUID")

    user: Mapped[Optional["User"]] = relationship(  # type: ignore[name-defined]
        primaryjoin="AuditLog.user_id == User.id",
        foreign_keys=[user_id],
    )

    __table_args__ = (
        # Primary query patterns
        Index("ix_audit_logged_at", "logged_at"),
        Index("ix_audit_user_action", "user_id", "action", "logged_at"),
        Index("ix_audit_resource", "resource_type", "resource_id"),
        Index("ix_audit_outcome", "outcome", "logged_at"),
        Index("ix_audit_request_id", "request_id"),
        # TimescaleDB candidate — very high write volume:
        # SELECT create_hypertable('audit_logs', 'logged_at');
        # SELECT add_retention_policy('audit_logs', INTERVAL '2 years');
    )
