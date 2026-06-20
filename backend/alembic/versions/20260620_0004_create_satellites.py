"""satellites: create satellites table

Revision ID: 0004_create_satellites
Revises: 0003_create_operators
Create Date: 2026-06-20 00:04:00

Schema notes:
  - norad_id is the canonical external key (used in all inter-table refs)
  - FK to operators is soft (operator_id nullable + no FK constraint)
    because debris objects often have no operator and we ingest before
    the operator record may exist
  - extra JSONB column absorbs schema-free fields without migrations
  - pg_trgm trigram index enables fast fuzzy name search
"""
from __future__ import annotations
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0004_create_satellites"
down_revision = "0003_create_operators"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "satellites",
        # ── Identifiers ──────────────────────────────────────
        sa.Column("id",                    sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("norad_id",              sa.Integer(),    nullable=False),
        sa.Column("cospar_id",             sa.String(15)),
        sa.Column("name",                  sa.String(256),  nullable=False),
        sa.Column("international_designator", sa.String(15)),

        # ── Classification ────────────────────────────────────
        sa.Column("object_type",           sa.String(32),   nullable=False,
                  comment="satellite | debris | rocket_body | unknown"),
        sa.Column("mission_type",          sa.String(32),
                  comment="eo | comms | nav | science | weather | military | other"),
        sa.Column("regime",                sa.String(16),
                  comment="VLEO | LEO | SSO | MEO | GEO | HEO | GTO | TLI | DSO"),
        sa.Column("status",                sa.String(32),   nullable=False,
                  server_default="unknown",
                  comment="operational | defunct | reentry | decayed | unknown"),

        # ── Ownership ─────────────────────────────────────────
        sa.Column("operator_id",           sa.BigInteger(),
                  comment="Soft FK → operators.id"),
        sa.Column("country_code",          sa.String(3)),
        sa.Column("operator_name",         sa.String(256)),

        # ── Launch ────────────────────────────────────────────
        sa.Column("launch_date",           sa.Date()),
        sa.Column("launch_site",           sa.String(128)),
        sa.Column("launch_vehicle",        sa.String(128)),
        sa.Column("decay_date",            sa.Date()),
        sa.Column("expected_eol",          sa.Date()),

        # ── Physical ──────────────────────────────────────────
        sa.Column("mass_kg",               sa.Float()),
        sa.Column("span_m",                sa.Float()),
        sa.Column("radar_cross_section_m2",sa.Float()),
        sa.Column("hard_body_radius_km",   sa.Float(),      nullable=False,
                  server_default="0.005"),

        # ── Orbital elements (cached) ─────────────────────────
        sa.Column("perigee_km",            sa.Float()),
        sa.Column("apogee_km",             sa.Float()),
        sa.Column("inclination_deg",       sa.Float()),
        sa.Column("raan_deg",              sa.Float()),
        sa.Column("eccentricity",          sa.Float()),
        sa.Column("mean_motion_rev_day",   sa.Float()),
        sa.Column("period_minutes",        sa.Float()),
        sa.Column("altitude_km",           sa.Float()),

        # ── TLE cache ─────────────────────────────────────────
        sa.Column("tle_line1",             sa.String(70)),
        sa.Column("tle_line2",             sa.String(70)),
        sa.Column("tle_epoch",             sa.DateTime(timezone=True)),
        sa.Column("tle_age_days",          sa.Float()),
        sa.Column("tle_source",            sa.String(32)),
        sa.Column("bstar",                 sa.Float()),

        # ── Constellation ─────────────────────────────────────
        sa.Column("constellation",         sa.String(64)),
        sa.Column("constellation_shell",   sa.Integer()),
        sa.Column("constellation_plane",   sa.Integer()),
        sa.Column("constellation_slot",    sa.Integer()),

        # ── Flexible payload ──────────────────────────────────
        sa.Column("extra",                 JSONB()),

        # ── Timestamps ────────────────────────────────────────
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Constraints
    op.create_unique_constraint("uq_satellites_norad",  "satellites", ["norad_id"])
    op.create_unique_constraint("uq_satellites_cospar", "satellites", ["cospar_id"])

    # B-tree indexes (high-selectivity filters)
    op.create_index("ix_satellites_norad",         "satellites", ["norad_id"])
    op.create_index("ix_satellites_regime_status", "satellites", ["regime", "status"])
    op.create_index("ix_satellites_constellation", "satellites", ["constellation"])
    op.create_index("ix_satellites_launch_date",   "satellites", ["launch_date"])
    op.create_index("ix_satellites_perigee",       "satellites", ["perigee_km"])
    op.create_index("ix_satellites_country",       "satellites", ["country_code"])
    op.create_index("ix_satellites_updated",       "satellites", ["updated_at"])

    # Trigram index for name search
    op.execute("""
        CREATE INDEX ix_satellites_name_trgm
        ON satellites USING gin (name gin_trgm_ops)
    """)

    # Partial index: active satellites only (speeds up most ops queries)
    op.execute("""
        CREATE INDEX ix_satellites_active_regime
        ON satellites (regime, perigee_km, inclination_deg)
        WHERE status = 'operational'
    """)

    # Updated_at trigger
    op.execute("""
        CREATE TRIGGER trg_satellites_updated_at
        BEFORE UPDATE ON satellites
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_satellites_updated_at ON satellites")
    op.drop_table("satellites")
