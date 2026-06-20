"""events: create conjunction_events, orbital_events, audit_logs

Revision ID: 0007_create_event_tables
Revises: 0006_create_missions
Create Date: 2026-06-20 00:07:00

All three tables in one migration because they have no inter-table FKs
and are logically "event/log" tables created together.
"""
from __future__ import annotations
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0007_create_event_tables"
down_revision = "0006_create_missions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── conjunction_events ────────────────────────────────────
    op.create_table(
        "conjunction_events",
        sa.Column("id",                          sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("conjunction_id",              sa.String(64),   nullable=False),
        sa.Column("primary_norad",               sa.Integer(),    nullable=False),
        sa.Column("primary_name",                sa.String(256)),
        sa.Column("primary_type",                sa.String(32)),
        sa.Column("secondary_norad",             sa.Integer(),    nullable=False),
        sa.Column("secondary_name",              sa.String(256)),
        sa.Column("secondary_type",              sa.String(32)),
        sa.Column("tca",                         sa.DateTime(timezone=True), nullable=False),
        sa.Column("miss_distance_km",            sa.Float(),      nullable=False),
        sa.Column("relative_velocity_kms",       sa.Float(),      nullable=False),
        sa.Column("collision_probability",       sa.Float(),      nullable=False),
        sa.Column("collision_probability_method",sa.String(32),   nullable=False,
                  server_default="Foster2001"),
        sa.Column("risk_level",                  sa.String(16),   nullable=False,
                  server_default="white"),
        sa.Column("primary_sigma_r_km",          sa.Float()),
        sa.Column("primary_sigma_t_km",          sa.Float()),
        sa.Column("primary_sigma_n_km",          sa.Float()),
        sa.Column("secondary_sigma_r_km",        sa.Float()),
        sa.Column("secondary_sigma_t_km",        sa.Float()),
        sa.Column("secondary_sigma_n_km",        sa.Float()),
        sa.Column("combined_hbr_km",             sa.Float()),
        sa.Column("sigma_major_km",              sa.Float()),
        sa.Column("sigma_minor_km",              sa.Float()),
        sa.Column("maneuver_required",           sa.Boolean(),    nullable=False,
                  server_default="false"),
        sa.Column("maneuver_window_open",        sa.DateTime(timezone=True)),
        sa.Column("maneuver_window_close",       sa.DateTime(timezone=True)),
        sa.Column("recommended_dv_kms",          sa.Float()),
        sa.Column("resolved",                    sa.Boolean(),    nullable=False,
                  server_default="false"),
        sa.Column("resolution",                  sa.String(32)),
        sa.Column("resolved_at",                 sa.DateTime(timezone=True)),
        sa.Column("resolved_by_user_id",         sa.BigInteger()),
        sa.Column("screening_org",               sa.String(64),   nullable=False,
                  server_default="ORBITIQ-X"),
        sa.Column("data_source",                 sa.String(32)),
        sa.Column("cdm_issued_at",               sa.DateTime(timezone=True)),
        sa.Column("extra",                       JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_conj_id", "conjunction_events", ["conjunction_id"])
    op.create_index("ix_conj_tca_pc",        "conjunction_events", ["tca", "collision_probability"])
    op.create_index("ix_conj_primary_tca",   "conjunction_events", ["primary_norad", "tca"])
    op.create_index("ix_conj_secondary_tca", "conjunction_events", ["secondary_norad", "tca"])
    op.create_index("ix_conj_risk_resolved", "conjunction_events", ["risk_level", "resolved"])
    op.create_index("ix_conj_resolved_at",   "conjunction_events", ["resolved_at"])
    # Partial index: unresolved high-risk events (the hot path for ops)
    op.execute("""
        CREATE INDEX ix_conj_active_red
        ON conjunction_events (tca, collision_probability DESC)
        WHERE resolved = false AND risk_level IN ('red', 'yellow')
    """)
    op.execute("""
        CREATE TRIGGER trg_conjunction_events_updated_at
        BEFORE UPDATE ON conjunction_events
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ── orbital_events ────────────────────────────────────────
    op.create_table(
        "orbital_events",
        sa.Column("id",                    sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("norad_id",              sa.Integer(),    index=True),
        sa.Column("event_type",            sa.String(32),   nullable=False),
        sa.Column("event_time",            sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at",           sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("severity",              sa.String(16),   nullable=False,
                  server_default="info"),
        sa.Column("alert_sent",            sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("acknowledged",          sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("acknowledged_by",       sa.BigInteger()),
        sa.Column("acknowledged_at",       sa.DateTime(timezone=True)),
        # Re-entry fields
        sa.Column("predicted_reentry_at",  sa.DateTime(timezone=True)),
        sa.Column("reentry_uncertainty_hours", sa.Float()),
        sa.Column("reentry_lifetime_days", sa.Float()),
        sa.Column("survival_probability",  sa.Float()),
        # Maneuver fields
        sa.Column("delta_v_kms",           sa.Float()),
        sa.Column("pre_perigee_km",        sa.Float()),
        sa.Column("post_perigee_km",       sa.Float()),
        sa.Column("pre_apogee_km",         sa.Float()),
        sa.Column("post_apogee_km",        sa.Float()),
        # Anomaly fields
        sa.Column("anomaly_parameter",     sa.String(64)),
        sa.Column("anomaly_observed_value",sa.Float()),
        sa.Column("anomaly_expected_value",sa.Float()),
        sa.Column("anomaly_sigma",         sa.Float()),
        # Space weather
        sa.Column("kp_index",              sa.Float()),
        sa.Column("f107_flux",             sa.Float()),
        sa.Column("storm_category",        sa.String(8)),
        # Free-form
        sa.Column("title",                 sa.String(256)),
        sa.Column("description",           sa.Text()),
        sa.Column("extra",                 JSONB()),
        sa.Column("source_agent",          sa.String(64)),
        sa.Column("data_source",           sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_orbital_events_norad_type_time",
                    "orbital_events", ["norad_id", "event_type", "event_time"])
    op.create_index("ix_orbital_events_severity_ack",
                    "orbital_events", ["severity", "acknowledged"])
    op.create_index("ix_orbital_events_event_time", "orbital_events", ["event_time"])
    op.create_index("ix_orbital_events_type_time",  "orbital_events", ["event_type", "event_time"])

    # ── audit_logs ────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id",               sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("logged_at",        sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("user_id",          sa.BigInteger()),
        sa.Column("username",         sa.String(64)),
        sa.Column("session_id",       sa.BigInteger()),
        sa.Column("api_key_prefix",   sa.String(12)),
        sa.Column("ip_address",       sa.String(45)),
        sa.Column("user_agent",       sa.Text()),
        sa.Column("action",           sa.String(64),  nullable=False),
        sa.Column("resource_type",    sa.String(64)),
        sa.Column("resource_id",      sa.String(128)),
        sa.Column("outcome",          sa.String(16),  nullable=False, server_default="success"),
        sa.Column("description",      sa.Text()),
        sa.Column("before_state",     JSONB()),
        sa.Column("after_state",      JSONB()),
        sa.Column("extra",            JSONB()),
        sa.Column("request_id",       sa.String(64)),
        sa.Column("endpoint",         sa.String(256)),
        sa.Column("http_method",      sa.String(8)),
        sa.Column("response_status",  sa.Integer()),
        sa.Column("duration_ms",      sa.Float()),
        sa.Column("agent_name",       sa.String(64)),
        sa.Column("task_id",          sa.String(64)),
    )
    op.create_index("ix_audit_logged_at",    "audit_logs", ["logged_at"])
    op.create_index("ix_audit_user_action",  "audit_logs", ["user_id", "action", "logged_at"])
    op.create_index("ix_audit_resource",     "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_outcome",      "audit_logs", ["outcome", "logged_at"])
    op.create_index("ix_audit_request_id",   "audit_logs", ["request_id"])

    # Soft FK for acknowledged_by on orbital_events → users
    op.create_foreign_key(
        "fk_orbital_events_ack_user",
        "orbital_events", "users",
        ["acknowledged_by"], ["id"],
        ondelete="SET NULL",
    )
    # Soft FK for resolved_by on conjunction_events → users
    op.create_foreign_key(
        "fk_conjunction_resolved_user",
        "conjunction_events", "users",
        ["resolved_by_user_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_conjunction_resolved_user", "conjunction_events", type_="foreignkey")
    op.drop_constraint("fk_orbital_events_ack_user",  "orbital_events",    type_="foreignkey")
    op.execute("DROP TRIGGER IF EXISTS trg_conjunction_events_updated_at ON conjunction_events")
    op.drop_table("audit_logs")
    op.drop_table("orbital_events")
    op.drop_table("conjunction_events")
