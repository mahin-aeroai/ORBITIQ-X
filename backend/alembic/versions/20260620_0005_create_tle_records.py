"""tle_records: create TLE archive table

Revision ID: 0005_create_tle_records
Revises: 0004_create_satellites
Create Date: 2026-06-20 00:05:00

Notes:
  - norad_id is NOT a FK constraint — satellites can be deleted while
    keeping their TLE history (forensic value)
  - TimescaleDB hypertable conversion is in a separate migration (0008)
    to run only after the extension is available
  - Unique constraint on (norad_id, epoch, element_set_num) prevents
    re-ingesting the same TLE set from different sources
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "0005_create_tle_records"
down_revision = "0004_create_satellites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tle_records",
        sa.Column("id",                    sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("norad_id",              sa.Integer(),    nullable=False),
        sa.Column("satellite_id",          sa.BigInteger(),
                  comment="Soft FK → satellites.id (async backfill)"),
        # TLE content
        sa.Column("name",                  sa.String(256),  nullable=False),
        sa.Column("line1",                 sa.String(70),   nullable=False),
        sa.Column("line2",                 sa.String(70),   nullable=False),
        # Decoded fields
        sa.Column("epoch",                 sa.DateTime(timezone=True), nullable=False),
        sa.Column("epoch_year",            sa.Integer(),    nullable=False),
        sa.Column("epoch_day",             sa.Float(),      nullable=False),
        sa.Column("inclination_deg",       sa.Float(),      nullable=False),
        sa.Column("raan_deg",              sa.Float(),      nullable=False),
        sa.Column("eccentricity",          sa.Float(),      nullable=False),
        sa.Column("arg_perigee_deg",       sa.Float(),      nullable=False),
        sa.Column("mean_anomaly_deg",      sa.Float(),      nullable=False),
        sa.Column("mean_motion_rev_day",   sa.Float(),      nullable=False),
        sa.Column("bstar",                 sa.Float(),      nullable=False),
        sa.Column("n_dot",                 sa.Float(),      nullable=False),
        sa.Column("n_ddot",                sa.Float(),      nullable=False),
        sa.Column("element_set_num",       sa.Integer()),
        sa.Column("rev_number",            sa.Integer()),
        # Derived
        sa.Column("semi_major_axis_km",    sa.Float()),
        sa.Column("perigee_km",            sa.Float()),
        sa.Column("apogee_km",             sa.Float()),
        sa.Column("period_minutes",        sa.Float()),
        # Metadata
        sa.Column("source",                sa.String(32),   nullable=False,
                  server_default="celestrak"),
        sa.Column("checksum_ok",           sa.Boolean(),    nullable=False,
                  server_default="true"),
        sa.Column("age_at_ingest_days",    sa.Float()),
        sa.Column("ingested_at",           sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_unique_constraint(
        "uq_tle_norad_epoch_set", "tle_records",
        ["norad_id", "epoch", "element_set_num"]
    )
    op.create_index("ix_tle_norad_epoch",      "tle_records", ["norad_id", "epoch"])
    op.create_index("ix_tle_epoch",            "tle_records", ["epoch"])
    op.create_index("ix_tle_source_ingested",  "tle_records", ["source", "ingested_at"])


def downgrade() -> None:
    op.drop_table("tle_records")
