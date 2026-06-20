"""operators: create operators table

Revision ID: 0003_create_operators
Revises: 0002_create_users
Create Date: 2026-06-20 00:03:00
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "0003_create_operators"
down_revision = "0002_create_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id",                   sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("operator_id",          sa.String(32),   nullable=False,
                  comment="e.g. OP-ISRO, OP-SPACEX"),
        sa.Column("name",                 sa.String(256),  nullable=False),
        sa.Column("short_name",           sa.String(64)),
        sa.Column("operator_type",        sa.String(32),   nullable=False,
                  server_default="commercial",
                  comment="government | commercial | military | academic | igo"),
        sa.Column("country_code",         sa.String(3),
                  comment="ISO-3166-1 alpha-3"),
        sa.Column("country_name",         sa.String(128)),
        sa.Column("website",              sa.String(512)),
        sa.Column("description",          sa.Text()),
        sa.Column("founding_year",        sa.Integer()),
        sa.Column("is_active",            sa.Boolean(),    nullable=False, server_default="true"),
        sa.Column("satellite_count",      sa.Integer(),    nullable=False, server_default="0",
                  comment="Denormalised — refreshed by scheduler"),
        sa.Column("primary_mission_type", sa.String(64),
                  comment="EO | comms | nav | science | military"),
        sa.Column("created_at",           sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_operators_id",   "operators", ["operator_id"])
    op.create_index("ix_operators_country_type", "operators", ["country_code", "operator_type"])
    op.create_index("ix_operators_name",         "operators", ["name"])

    # Trigram index for fuzzy name search
    op.execute("""
        CREATE INDEX ix_operators_name_trgm
        ON operators USING gin (name gin_trgm_ops)
    """)

    op.execute("""
        CREATE TRIGGER trg_operators_updated_at
        BEFORE UPDATE ON operators
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_operators_updated_at ON operators")
    op.drop_table("operators")
