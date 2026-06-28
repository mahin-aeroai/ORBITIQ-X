"""
ORBITIQ-X — Alembic Migration: Phase 17.4 Knowledge Ingestion Framework
Revision: 20260628_0014_ingestion_framework

Creates:
  1. ingestion_schedule_log  — Per-run log for every adapter execution
  2. ingestion_source_config — Persisted adapter configs with credentials
  3. ingestion_dedup_cache   — Content hash cache to skip unchanged records

Note: Adapter credentials stored in ingestion_source_config are encrypted
at the application layer before insert. Never store plaintext secrets in DB.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision      = '20260628_0014_ingestion_framework'
down_revision = '20260628_0013_provenance_versioning'
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ------------------------------------------------------------------
    # 1. INGESTION SCHEDULE LOG
    # Full audit trail for every adapter run.
    # ------------------------------------------------------------------
    op.create_table(
        'ingestion_schedule_log',
        sa.Column('log_id',             sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('job_id',             sa.String(64),  nullable=False, unique=True),
        sa.Column('adapter_name',       sa.String(80),  nullable=False, index=True),
        sa.Column('started_at',         sa.String(40),  nullable=False),
        sa.Column('completed_at',       sa.String(40),  nullable=False),
        sa.Column('records_fetched',    sa.Integer,     server_default='0'),
        sa.Column('entities_created',   sa.Integer,     server_default='0'),
        sa.Column('entities_updated',   sa.Integer,     server_default='0'),
        sa.Column('relationships_added',sa.Integer,     server_default='0'),
        sa.Column('contradictions',     sa.Integer,     server_default='0'),
        sa.Column('fetch_errors',       JSONB,          server_default='[]'),
        sa.Column('pipeline_errors',    JSONB,          server_default='[]'),
        sa.Column('status',             sa.String(20),  server_default='pending',
                  comment='success / partial / failed / skipped'),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
    )

    op.create_index('ix_isl_adapter',  'ingestion_schedule_log', ['adapter_name'])
    op.create_index('ix_isl_status',   'ingestion_schedule_log', ['status'])
    op.create_index('ix_isl_created',  'ingestion_schedule_log', ['created_at'])

    # ------------------------------------------------------------------
    # 2. INGESTION SOURCE CONFIG
    # Persisted adapter configurations (credentials encrypted at app layer).
    # ------------------------------------------------------------------
    op.create_table(
        'ingestion_source_config',
        sa.Column('adapter_name',       sa.String(80),  primary_key=True),
        sa.Column('source_tier',        sa.Integer,     nullable=False),
        sa.Column('is_enabled',         sa.Boolean,     server_default='true'),
        sa.Column('fetch_interval_s',   sa.Integer,     server_default='86400'),
        sa.Column('max_records_per_run',sa.Integer,     server_default='0',
                  comment='0 = no limit'),
        sa.Column('config_encrypted',   sa.Text,        nullable=True,
                  comment='AES-encrypted JSON config (credentials). NULL = use env vars.'),
        sa.Column('last_run_at',        sa.DateTime,    nullable=True),
        sa.Column('next_run_at',        sa.DateTime,    nullable=True),
        sa.Column('total_runs',         sa.Integer,     server_default='0'),
        sa.Column('total_records',      sa.Integer,     server_default='0'),
        sa.Column('notes',              sa.Text,        nullable=True),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
        sa.Column('updated_at',         sa.DateTime,    server_default=sa.func.now()),
    )

    # Seed registered adapters
    op.execute("""
        INSERT INTO ingestion_source_config
            (adapter_name, source_tier, is_enabled, fetch_interval_s, notes)
        VALUES
            ('space_track',    2, true,  7200,    'Space-Track.org SATCAT + GP data. Set SPACETRACK_IDENTITY and SPACETRACK_PASSWORD env vars.'),
            ('nasa_techport',  1, true,  604800,  'NASA TechPort technology project data. No auth required.'),
            ('nasa_missions',  1, true,  2592000, 'NASA mission curated seed data. No auth required.'),
            ('celestrak',      2, false, 43200,   'Celestrak SATCAT CSV. DISABLED in production — Railway IPs blocked. Use for local dev only.'),
            ('unoosa',         2, true,  2592000, 'UNOOSA registration seed data.')
        ON CONFLICT DO NOTHING
    """)

    # ------------------------------------------------------------------
    # 3. INGESTION DEDUP CACHE
    # Stores content hashes of previously ingested records to skip
    # unchanged data on subsequent runs.
    # ------------------------------------------------------------------
    op.create_table(
        'ingestion_dedup_cache',
        sa.Column('cache_id',           sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('adapter_name',       sa.String(80),  nullable=False),
        sa.Column('source_id',          sa.String(255), nullable=False,
                  comment='Stable ID within the source system'),
        sa.Column('content_hash',       sa.String(32),  nullable=False,
                  comment='SHA-256[:16] of canonical content fields'),
        sa.Column('aqid',               sa.String(120), nullable=True,
                  comment='Resolved AQID after first successful ingestion'),
        sa.Column('first_seen_at',      sa.DateTime,    server_default=sa.func.now()),
        sa.Column('last_seen_at',       sa.DateTime,    server_default=sa.func.now()),
        sa.Column('ingest_count',       sa.Integer,     server_default='1'),

        sa.UniqueConstraint('adapter_name', 'source_id', name='uq_dedup_adapter_source'),
    )

    op.create_index('ix_dc_adapter_source', 'ingestion_dedup_cache', ['adapter_name', 'source_id'])
    op.create_index('ix_dc_hash',           'ingestion_dedup_cache', ['content_hash'])
    op.create_index('ix_dc_aqid',           'ingestion_dedup_cache', ['aqid'])


def downgrade() -> None:
    op.drop_table('ingestion_dedup_cache')
    op.drop_table('ingestion_source_config')
    op.drop_table('ingestion_schedule_log')
