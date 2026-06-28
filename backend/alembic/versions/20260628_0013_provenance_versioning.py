"""
ORBITIQ-X — Alembic Migration: Phase 17.3 Provenance & Versioning
Revision: 20260628_0013_provenance_versioning

Creates:
  1. fact_provenance        — Field-level provenance for every entity fact
  2. contradiction_log      — Conflicts between sources on the same fact
  3. review_queue           — Human review tasks for disputed contradictions
  4. version_snapshots      — Immutable point-in-time entity state copies

Notes (Railway PostgreSQL 18):
  - All GIN indexes via op.execute() — never op.create_index() for GIN
  - AUTOCOMMIT already handled by entrypoint migration wrapper
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision      = '20260628_0013_provenance_versioning'
down_revision = '20260628_0012_relationship_ontology'
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ------------------------------------------------------------------
    # 1. FACT PROVENANCE
    # Every field value on every entity has a provenance record.
    # ------------------------------------------------------------------
    op.create_table(
        'fact_provenance',
        sa.Column('fact_id',            sa.String(64),  primary_key=True),
        sa.Column('aqid',               sa.String(120), nullable=False,
                  comment='Entity this fact belongs to'),
        sa.Column('field_name',         sa.String(120), nullable=False,
                  comment='Name of the entity field e.g. payload_leo_kg'),
        sa.Column('field_value',        sa.Text,        nullable=False,
                  comment='JSON-serialized field value'),
        sa.Column('field_value_type',   sa.String(40),  server_default='str'),

        # Source
        sa.Column('source_url',         sa.Text,        nullable=True),
        sa.Column('source_name',        sa.String(255), nullable=True),
        sa.Column('source_tier',        sa.Integer,     server_default='6',
                  comment='1=Official 2=Registry 3=PeerReviewed 4=Reference 5=News 6=Community'),
        sa.Column('source_type',        sa.String(40),  server_default='community'),
        sa.Column('publisher',          sa.String(255), nullable=True),
        sa.Column('author',             sa.String(255), nullable=True),
        sa.Column('published_date',     sa.Date,        nullable=True),
        sa.Column('retrieved_at',       sa.DateTime,    server_default=sa.func.now()),

        # Trust
        sa.Column('confidence',         sa.Float,       server_default='0.5', nullable=False),
        sa.Column('is_primary',         sa.Boolean,     server_default='true'),
        sa.Column('is_superseded',      sa.Boolean,     server_default='false'),
        sa.Column('superseded_by',      sa.String(64),  nullable=True,
                  comment='fact_id of the superseding fact'),

        # Citation
        sa.Column('citation_text',      sa.Text,        nullable=True),
        sa.Column('doi',                sa.String(255), nullable=True),
        sa.Column('page_ref',           sa.String(80),  nullable=True),

        # Audit
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
        sa.Column('created_by',         sa.String(120), server_default='system'),
        sa.Column('ingest_job_id',      sa.String(80),  nullable=True),
    )

    op.create_index('ix_fp_aqid',       'fact_provenance', ['aqid'])
    op.create_index('ix_fp_field',      'fact_provenance', ['aqid', 'field_name'])
    op.create_index('ix_fp_primary',    'fact_provenance', ['aqid', 'field_name', 'is_primary'])
    op.create_index('ix_fp_tier',       'fact_provenance', ['source_tier'])
    op.create_index('ix_fp_confidence', 'fact_provenance', ['confidence'])
    op.create_index('ix_fp_superseded', 'fact_provenance', ['is_superseded'])
    op.create_index('ix_fp_created',    'fact_provenance', ['created_at'])

    # ------------------------------------------------------------------
    # 2. CONTRADICTION LOG
    # Immutable record of every detected conflict between sources.
    # ------------------------------------------------------------------
    op.create_table(
        'contradiction_log',
        sa.Column('contradiction_id',   sa.String(64),  primary_key=True),
        sa.Column('aqid',               sa.String(120), nullable=False, index=True),
        sa.Column('field_name',         sa.String(120), nullable=False),

        # Existing fact
        sa.Column('existing_fact_id',   sa.String(64),  nullable=False),
        sa.Column('existing_value',     sa.Text,        nullable=False),
        sa.Column('existing_confidence',sa.Float,       nullable=False),
        sa.Column('existing_source_url',sa.Text,        nullable=True),
        sa.Column('existing_tier',      sa.Integer,     server_default='6'),

        # Incoming fact
        sa.Column('incoming_fact_id',   sa.String(64),  nullable=False),
        sa.Column('incoming_value',     sa.Text,        nullable=False),
        sa.Column('incoming_confidence',sa.Float,       nullable=False),
        sa.Column('incoming_source_url',sa.Text,        nullable=True),
        sa.Column('incoming_tier',      sa.Integer,     server_default='6'),

        # Resolution
        sa.Column('confidence_delta',   sa.Float,       server_default='0.0'),
        sa.Column('resolution',         sa.String(20),  server_default='dispute',
                  comment='override / dispute / reject / merged'),
        sa.Column('resolution_notes',   sa.Text,        nullable=True),
        sa.Column('resolved_by',        sa.String(120), nullable=True),
        sa.Column('resolved_at',        sa.DateTime,    nullable=True),
        sa.Column('status',             sa.String(30),  server_default='pending_review',
                  comment='pending_review / auto_resolved / human_resolved'),

        # Audit
        sa.Column('ingest_job_id',      sa.String(80),  nullable=True),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
    )

    op.create_index('ix_cl_aqid',       'contradiction_log', ['aqid'])
    op.create_index('ix_cl_field',      'contradiction_log', ['aqid', 'field_name'])
    op.create_index('ix_cl_status',     'contradiction_log', ['status'])
    op.create_index('ix_cl_resolution', 'contradiction_log', ['resolution'])
    op.create_index('ix_cl_created',    'contradiction_log', ['created_at'])

    # ------------------------------------------------------------------
    # 3. REVIEW QUEUE
    # Human review tasks for disputed contradictions.
    # ------------------------------------------------------------------
    op.create_table(
        'review_queue',
        sa.Column('review_id',          sa.String(64),  primary_key=True),
        sa.Column('contradiction_id',   sa.String(64),  nullable=False, index=True),
        sa.Column('aqid',               sa.String(120), nullable=False, index=True),
        sa.Column('field_name',         sa.String(120), nullable=False),
        sa.Column('priority',           sa.String(20),  server_default='medium',
                  comment='critical / high / medium / low'),
        sa.Column('entity_display_name',sa.String(255), nullable=True),

        # Context for reviewer
        sa.Column('existing_value',     sa.Text,        nullable=False),
        sa.Column('incoming_value',     sa.Text,        nullable=False),
        sa.Column('existing_source',    sa.Text,        nullable=True),
        sa.Column('incoming_source',    sa.Text,        nullable=True),
        sa.Column('confidence_delta',   sa.Float,       server_default='0.0'),

        # Assignment
        sa.Column('assigned_to',        sa.String(120), nullable=True),
        sa.Column('assigned_at',        sa.DateTime,    nullable=True),
        sa.Column('due_by',             sa.DateTime,    nullable=True),

        # Resolution
        sa.Column('status',             sa.String(20),  server_default='open',
                  comment='open / in_progress / resolved / dismissed'),
        sa.Column('resolution',         sa.String(20),  nullable=True),
        sa.Column('reviewer_notes',     sa.Text,        nullable=True),
        sa.Column('resolved_by',        sa.String(120), nullable=True),
        sa.Column('resolved_at',        sa.DateTime,    nullable=True),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
    )

    op.create_index('ix_rq_aqid',      'review_queue', ['aqid'])
    op.create_index('ix_rq_status',    'review_queue', ['status'])
    op.create_index('ix_rq_priority',  'review_queue', ['priority'])
    op.create_index('ix_rq_assigned',  'review_queue', ['assigned_to'])
    op.create_index('ix_rq_created',   'review_queue', ['created_at'])

    # ------------------------------------------------------------------
    # 4. VERSION SNAPSHOTS
    # Immutable point-in-time entity state copies. Never updated.
    # ------------------------------------------------------------------
    op.create_table(
        'version_snapshots',
        sa.Column('snapshot_id',        sa.String(64),  primary_key=True),
        sa.Column('aqid',               sa.String(120), nullable=False, index=True),
        sa.Column('version',            sa.String(20),  nullable=False),
        sa.Column('snapshot_type',      sa.String(20),  server_default='auto',
                  comment='auto / publish / contradiction / manual'),

        # Full entity state at snapshot time
        sa.Column('entity_state',       JSONB,          nullable=False),
        sa.Column('extension_state',    JSONB,          server_default='{}'),
        sa.Column('confidence_at_snapshot', sa.Float,   server_default='0.0'),
        sa.Column('verification_status_at', sa.String(30), server_default='unverified'),

        # What changed
        sa.Column('change_summary',     sa.Text,        nullable=True),
        sa.Column('fields_changed',     JSONB,          server_default='[]'),
        sa.Column('field_diffs',        JSONB,          server_default='{}'),

        # Audit
        sa.Column('created_by',         sa.String(120), server_default='system'),
        sa.Column('ingest_job_id',      sa.String(80),  nullable=True),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
    )

    op.create_index('ix_vs_aqid',      'version_snapshots', ['aqid'])
    op.create_index('ix_vs_version',   'version_snapshots', ['aqid', 'version'])
    op.create_index('ix_vs_type',      'version_snapshots', ['snapshot_type'])
    op.create_index('ix_vs_created',   'version_snapshots', ['created_at'])
    op.execute(
        "CREATE INDEX ix_vs_entity_state ON version_snapshots USING GIN (entity_state)"
    )

    # ------------------------------------------------------------------
    # 5. TRIGGER: auto-snapshot on entity publish
    # When an entity's lifecycle_status changes to 'published',
    # a publish-type snapshot is automatically queued.
    # (Actual snapshot creation is done by the service layer on startup
    #  via the snapshot_trigger_log table below.)
    # ------------------------------------------------------------------
    op.create_table(
        'snapshot_trigger_log',
        sa.Column('trigger_id',     sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('aqid',           sa.String(120), nullable=False),
        sa.Column('trigger_reason', sa.String(60),  nullable=False),
        sa.Column('processed',      sa.Boolean,     server_default='false'),
        sa.Column('created_at',     sa.DateTime,    server_default=sa.func.now()),
    )
    op.create_index('ix_stl_aqid',      'snapshot_trigger_log', ['aqid'])
    op.create_index('ix_stl_processed', 'snapshot_trigger_log', ['processed'])

    op.execute("""
        CREATE OR REPLACE FUNCTION queue_publish_snapshot()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.lifecycle_status = 'published'
               AND (OLD.lifecycle_status IS DISTINCT FROM 'published') THEN
                INSERT INTO snapshot_trigger_log (aqid, trigger_reason)
                VALUES (NEW.aqid, 'publish');
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_entity_publish_snapshot
        AFTER UPDATE ON aerospace_entities
        FOR EACH ROW EXECUTE FUNCTION queue_publish_snapshot();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_entity_publish_snapshot ON aerospace_entities")
    op.execute("DROP FUNCTION IF EXISTS queue_publish_snapshot()")
    op.drop_table('snapshot_trigger_log')
    op.drop_table('version_snapshots')
    op.drop_table('review_queue')
    op.drop_table('contradiction_log')
    op.drop_table('fact_provenance')
