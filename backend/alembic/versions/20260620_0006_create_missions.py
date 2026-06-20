"""missions: create missions table

Revision ID: 0006_create_missions
Revises: 0005_create_tle_records
Create Date: 2026-06-20 00:06:00
"""
from __future__ import annotations
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from alembic import op

revision = "0006_create_missions"
down_revision = "0005_create_tle_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id",                      sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mission_id",              sa.String(64),   nullable=False),
        sa.Column("name",                    sa.String(256),  nullable=False),
        sa.Column("short_name",              sa.String(64)),
        sa.Column("mission_type",            sa.String(32),   nullable=False,
                  server_default="unknown"),
        sa.Column("status",                  sa.String(32),   nullable=False,
                  server_default="planned"),
        sa.Column("operator_id",             sa.BigInteger()),
        sa.Column("country_code",            sa.String(3)),
        sa.Column("agency",                  sa.String(64)),
        sa.Column("launch_date",             sa.Date()),
        sa.Column("end_date",                sa.Date()),
        sa.Column("design_lifetime_years",   sa.Float()),
        sa.Column("description",             sa.Text()),
        sa.Column("objectives",              ARRAY(sa.Text())),
        sa.Column("target_orbit",            sa.String(16)),
        sa.Column("target_altitude_km",      sa.Float()),
        sa.Column("target_inclination_deg",  sa.Float()),
        sa.Column("satellite_count",         sa.Integer(),    nullable=False, server_default="1"),
        sa.Column("budget_musd",             sa.Float()),
        sa.Column("wikipedia_url",           sa.String(512)),
        sa.Column("nasa_url",                sa.String(512)),
        sa.Column("extra",                   JSONB()),
        sa.Column("is_crewed",               sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("is_commercial",           sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_missions_mission_id", "missions", ["mission_id"])
    op.create_index("ix_missions_status_type", "missions", ["status", "mission_type"])
    op.create_index("ix_missions_launch_date", "missions", ["launch_date"])
    op.create_index("ix_missions_agency",      "missions", ["agency"])
    op.execute("""
        CREATE TRIGGER trg_missions_updated_at
        BEFORE UPDATE ON missions
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_missions_updated_at ON missions")
    op.drop_table("missions")
