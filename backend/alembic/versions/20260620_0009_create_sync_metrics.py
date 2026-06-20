"""sync_metrics: create catalog synchronization metrics table

Revision ID: 0009_create_sync_metrics
Revises: 0008_timescaledb_hypertables
Create Date: 2026-06-20 00:09:00

Records every Space-Track catalog synchronization run.
Used by /catalog/status, /catalog/health, /catalog/metrics endpoints.

Design:
  - One row per sync run (append-only for audit trail)
  - sync_id is the PK (UUID supplied by the scheduler)
  - status: running | success | partial | failed
  - phases_completed: comma-delimited phase names
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "0009_create_sync_metrics"
down_revision = "0008_timescaledb_hypertables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_metrics",
        sa.Column("sync_id",               sa.String(64),   primary_key=True),
        sa.Column("sync_mode",             sa.String(32),   nullable=False,
                  comment="full | incremental | active_only | debris_only"),
        sa.Column("status",                sa.String(16),   nullable=False,
                  server_default="running",
                  comment="running | success | partial | failed"),
        sa.Column("started_at",            sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("completed_at",          sa.DateTime(timezone=True)),

        # Download metrics
        sa.Column("download_duration_s",   sa.Float(), server_default="0"),
        sa.Column("downloaded_bytes",      sa.BigInteger(), server_default="0"),
        sa.Column("downloaded_records",    sa.Integer(), server_default="0"),

        # Ingest metrics
        sa.Column("total_parsed",          sa.Integer(), server_default="0"),
        sa.Column("inserted",              sa.Integer(), server_default="0"),
        sa.Column("duplicates",            sa.Integer(), server_default="0"),
        sa.Column("satellites_updated",    sa.Integer(), server_default="0"),
        sa.Column("parse_errors",          sa.Integer(), server_default="0"),

        # Health metrics
        sa.Column("stale_satellite_count", sa.Integer(), server_default="0"),
        sa.Column("cache_keys_refreshed",  sa.Integer(), server_default="0"),

        # Failure detail
        sa.Column("failure_reason",        sa.Text()),
        sa.Column("phases_completed",      sa.Text(),
                  comment="comma-delimited list of completed phase names"),
    )

    op.create_index("ix_sync_metrics_started_at",  "sync_metrics", ["started_at"])
    op.create_index("ix_sync_metrics_status",       "sync_metrics", ["status"])


def downgrade() -> None:
    op.drop_table("sync_metrics")
