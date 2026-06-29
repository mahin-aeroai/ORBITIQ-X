"""
ORBITIQ-X — Alembic Migration: Phase 17.7 Business Intelligence Layer
Revision: 20260628_0015_business_intelligence

Creates:
  1. bi_contracts      — Contract tracking (NASA, DoD, commercial)
  2. bi_investments    — Investment and funding rounds
  3. bi_market_context — Revenue and market share per entity per year
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision      = '20260628_0015_business_intelligence'
down_revision = '20260628_0014_ingestion_framework'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Idempotent guard: skip if tables already exist from a previous partial run
    from sqlalchemy import text as _sql_text
    _bind = op.get_bind()
    _exists = _bind.execute(_sql_text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='bi_contracts')"
    )).scalar()
    if _exists:
        return  # Tables already created, let Alembic update version


    # ── Contracts ──────────────────────────────────────────────────────────────
    op.create_table(
        'bi_contracts',
        sa.Column('contract_id',    sa.String(64),  primary_key=True),
        sa.Column('aqid',           sa.String(120), nullable=True, index=True,
                  comment='Linked CONTRACT entity AQID'),
        sa.Column('contract_number',sa.String(120), nullable=True),
        sa.Column('title',          sa.Text,        nullable=False),
        sa.Column('contract_type',  sa.String(20),  server_default='FFP'),
        sa.Column('client_name',    sa.String(255), nullable=False),
        sa.Column('client_aqid',    sa.String(120), nullable=True, index=True),
        sa.Column('recipient_name', sa.String(255), nullable=False),
        sa.Column('recipient_aqid', sa.String(120), nullable=True, index=True),
        sa.Column('subcontractors', JSONB,          server_default='[]'),
        sa.Column('value_musd',     sa.Float,       nullable=True),
        sa.Column('ceiling_musd',   sa.Float,       nullable=True),
        sa.Column('award_date',     sa.Date,        nullable=True),
        sa.Column('start_date',     sa.Date,        nullable=True),
        sa.Column('end_date',       sa.Date,        nullable=True),
        sa.Column('status',         sa.String(20),  server_default='active'),
        sa.Column('scope',          sa.Text,        nullable=True),
        sa.Column('program_aqid',   sa.String(120), nullable=True),
        sa.Column('mission_aqids',  JSONB,          server_default='[]'),
        sa.Column('source_url',     sa.Text,        nullable=True),
        sa.Column('confidence',     sa.Float,       server_default='0.8'),
        sa.Column('created_at',     sa.DateTime,    server_default=sa.func.now()),
    )
    op.create_index('ix_bic_client',    'bi_contracts', ['client_aqid'])
    op.create_index('ix_bic_recipient', 'bi_contracts', ['recipient_aqid'])
    op.create_index('ix_bic_status',    'bi_contracts', ['status'])
    op.create_index('ix_bic_value',     'bi_contracts', ['value_musd'])
    op.create_index('ix_bic_award',     'bi_contracts', ['award_date'])

    # ── Investments ────────────────────────────────────────────────────────────
    op.create_table(
        'bi_investments',
        sa.Column('investment_id',          sa.String(64),  primary_key=True),
        sa.Column('aqid',                   sa.String(120), nullable=True, index=True),
        sa.Column('investment_type',        sa.String(20),  nullable=False),
        sa.Column('recipient_name',         sa.String(255), nullable=False),
        sa.Column('recipient_aqid',         sa.String(120), nullable=True, index=True),
        sa.Column('investor_names',         JSONB,          server_default='[]'),
        sa.Column('investor_aqids',         JSONB,          server_default='[]'),
        sa.Column('amount_musd',            sa.Float,       nullable=True),
        sa.Column('pre_money_valuation',    sa.Float,       nullable=True),
        sa.Column('post_money_valuation',   sa.Float,       nullable=True),
        sa.Column('announcement_date',      sa.Date,        nullable=True),
        sa.Column('close_date',             sa.Date,        nullable=True),
        sa.Column('round_label',            sa.String(80),  nullable=True),
        sa.Column('lead_investor',          sa.String(255), nullable=True),
        sa.Column('source_url',             sa.Text,        nullable=True),
        sa.Column('confidence',             sa.Float,       server_default='0.8'),
        sa.Column('created_at',             sa.DateTime,    server_default=sa.func.now()),
    )
    op.create_index('ix_bii_recipient',  'bi_investments', ['recipient_aqid'])
    op.create_index('ix_bii_type',       'bi_investments', ['investment_type'])
    op.create_index('ix_bii_amount',     'bi_investments', ['amount_musd'])
    op.create_index('ix_bii_date',       'bi_investments', ['announcement_date'])
    op.execute("CREATE INDEX ix_bii_investors ON bi_investments USING GIN (investor_aqids)")

    # ── Market context ─────────────────────────────────────────────────────────
    op.create_table(
        'bi_market_context',
        sa.Column('context_id',         sa.String(64),  primary_key=True),
        sa.Column('entity_aqid',        sa.String(120), nullable=False, index=True),
        sa.Column('segment',            sa.String(40),  nullable=False),
        sa.Column('year',               sa.Integer,     nullable=False),
        sa.Column('revenue_musd',       sa.Float,       nullable=True),
        sa.Column('market_share_pct',   sa.Float,       nullable=True),
        sa.Column('employees',          sa.Integer,     nullable=True),
        sa.Column('backlog_musd',       sa.Float,       nullable=True),
        sa.Column('notes',              sa.Text,        nullable=True),
        sa.Column('source_url',         sa.Text,        nullable=True),
        sa.Column('confidence',         sa.Float,       server_default='0.7'),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
        sa.UniqueConstraint('entity_aqid', 'segment', 'year', name='uq_bmc_entity_segment_year'),
    )
    op.create_index('ix_bmc_aqid',    'bi_market_context', ['entity_aqid'])
    op.create_index('ix_bmc_segment', 'bi_market_context', ['segment', 'year'])


def downgrade() -> None:
    op.drop_table('bi_market_context')
    op.drop_table('bi_investments')
    op.drop_table('bi_contracts')
