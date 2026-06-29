"""
ORBITIQ-X — Alembic Migration: Phase 17.1 CAEM
Revision: 017_01

CRITICAL Railway/PostgreSQL notes from CLAUDE.md:
  - Always use AUTOCOMMIT mode for Alembic on Railway PostgreSQL 18
  - Never use string primaryjoin cross-model in SQLAlchemy
  - GIN indexes must be created via op.execute(), not op.create_index()

This migration creates:
  1. aerospace_entities      — Single-table inheritance master entity table
  2. entity_aliases          — Cross-system external ID mappings
  3. entity_relationships_cache — Denormalized relationship cache for fast API
  4. entity_ingestion_log    — Full audit log per ingestion job per entity
  5. knowledge_domains       — Domain taxonomy reference
  6. relationship_type_registry — Relationship type taxonomy reference
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid


# Set this to your current migration head
revision = '20260628_0011_caem_base_entities'
down_revision = '0010_add_fk_user_sessions'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------
    # 1. KNOWLEDGE DOMAINS — reference table
    # ------------------------------------------------------------------
    op.create_table(
        'knowledge_domains',
        sa.Column('domain_id',      sa.String(60),  primary_key=True),
        sa.Column('display_name',   sa.String(120), nullable=False),
        sa.Column('description',    sa.Text),
        sa.Column('parent_domain',  sa.String(60),  sa.ForeignKey('knowledge_domains.domain_id'), nullable=True),
        sa.Column('created_at',     sa.DateTime,    server_default=sa.func.now()),
    )

    # Seed core domains
    op.execute("""
        INSERT INTO knowledge_domains (domain_id, display_name, description) VALUES
        ('propulsion',          'Propulsion Systems',       'Rocket engines, thrusters, fuels'),
        ('orbital_mechanics',   'Orbital Mechanics',        'Astrodynamics, trajectory, maneuvers'),
        ('communications',      'Space Communications',     'RF, optical, protocols'),
        ('structures',          'Structures & Materials',   'Spacecraft structures, thermal, materials'),
        ('power_systems',       'Power Systems',            'Solar, batteries, RTG'),
        ('guidance_nav',        'GN&C',                     'Guidance, Navigation & Control'),
        ('earth_observation',   'Earth Observation',        'Remote sensing, imaging, SAR'),
        ('space_science',       'Space Science',            'Astrophysics, planetary science, heliophysics'),
        ('human_spaceflight',   'Human Spaceflight',        'Life support, crew systems, EVA'),
        ('launch_systems',      'Launch Systems',           'Launch vehicles, range, integration'),
        ('ground_systems',      'Ground Systems',           'Mission control, TT&C, ground networks'),
        ('policy_law',          'Space Policy & Law',       'Treaties, regulations, debris mitigation'),
        ('business_commercial', 'Commercial Space',         'Business models, markets, investment'),
        ('ai_autonomy',         'AI & Autonomy',            'Autonomous systems, ML in aerospace'),
        ('ssa',                 'Space Situational Awareness', 'Conjunction, tracking, debris'),
        ('defence_security',    'Defence & Security',       'Military space, dual-use, cyber')
        ON CONFLICT DO NOTHING;
    """)

    # ------------------------------------------------------------------
    # 2. RELATIONSHIP TYPE REGISTRY — reference table
    # ------------------------------------------------------------------
    op.create_table(
        'relationship_type_registry',
        sa.Column('rel_type',       sa.String(60),  primary_key=True),
        sa.Column('category',       sa.String(40),  nullable=False),
        sa.Column('description',    sa.Text),
        sa.Column('direction_note', sa.String(255)),
        sa.Column('is_bidirectional', sa.Boolean,   server_default='false'),
    )

    op.execute("""
        INSERT INTO relationship_type_registry (rel_type, category, description, direction_note) VALUES
        ('OPERATED_BY',     'operational',      'Satellite/system operated by organization', 'Hardware → Operator'),
        ('LAUNCHED_BY',     'operational',      'Entity launched by vehicle',               'Payload → Launch Vehicle'),
        ('LAUNCHED_FROM',   'operational',      'Vehicle launched from site',               'Launch Vehicle → Site'),
        ('MANUFACTURED_BY', 'supply_chain',     'Hardware made by manufacturer',            'Hardware → Manufacturer'),
        ('DESIGNED_BY',     'supply_chain',     'Entity designed by organization',          'Hardware → Designer'),
        ('FUNDED_BY',       'organizational',   'Mission/program funded by organization',   'Program/Mission → Funder'),
        ('PART_OF',         'organizational',   'Entity is part of larger entity',          'Child → Parent'),
        ('SUBSIDIARY_OF',   'organizational',   'Company is subsidiary of another',         'Subsidiary → Parent'),
        ('LOCATED_IN',      'geographic',       'Entity is located in country/region',      'Org/Site → Country'),
        ('USES_TECHNOLOGY', 'technical',        'Mission/hardware uses technology',         'User → Technology'),
        ('COLLABORATES_WITH', 'organizational', 'Organizations actively collaborate',       'Bidirectional'),
        ('CITES',           'scientific',       'Paper cites another paper',                'Paper → Cited Paper'),
        ('AUTHORED_BY',     'scientific',       'Document authored by person',              'Document → Author'),
        ('SUCCESSOR_OF',    'technical',        'System is successor of another',           'New → Old'),
        ('INVESTED_IN',     'commercial',       'Investment targets entity',                'Investment → Recipient')
        ON CONFLICT DO NOTHING;
    """)

    # ------------------------------------------------------------------
    # 3. AEROSPACE ENTITIES — master table (single-table inheritance)
    # ------------------------------------------------------------------
    op.create_table(
        'aerospace_entities',

        # --- IDENTITY ---
        sa.Column('aqid',               sa.String(120),     primary_key=True,
                  comment='Immutable Aerospace Knowledge Identifier'),
        sa.Column('entity_class',       sa.String(30),      nullable=False,
                  comment='EntityClass enum value'),
        sa.Column('entity_subclass',    sa.String(40),      nullable=True),
        sa.Column('display_name',       sa.String(255),     nullable=False),
        sa.Column('short_name',         sa.String(80),      nullable=True),
        sa.Column('aliases',            JSONB,              server_default='[]',
                  comment='Historical names and alternate spellings'),
        sa.Column('native_name',        sa.String(255),     nullable=True),
        sa.Column('description',        sa.Text,            nullable=True),
        sa.Column('long_description',   sa.Text,            nullable=True),

        # --- METADATA ---
        sa.Column('created_at',         sa.DateTime,        server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at',         sa.DateTime,        server_default=sa.func.now(), nullable=False),
        sa.Column('published_at',       sa.DateTime,        nullable=True),
        sa.Column('schema_version',     sa.String(20),      server_default='17.1.0'),
        sa.Column('is_active',          sa.Boolean,         server_default='true', nullable=False),
        sa.Column('lifecycle_status',   sa.String(20),      server_default='draft', nullable=False),
        sa.Column('record_completeness', sa.Float,          server_default='0.0'),
        sa.Column('primary_language',   sa.String(10),      server_default='en'),

        # --- TAXONOMY ---
        sa.Column('tags',               JSONB,              server_default='[]'),
        sa.Column('domains',            JSONB,              server_default='[]'),
        sa.Column('regions',            JSONB,              server_default='[]'),
        sa.Column('time_periods',       JSONB,              server_default='[]'),
        sa.Column('knowledge_domains',  JSONB,              server_default='[]'),

        # --- TIMELINE ---
        sa.Column('founded_or_created', sa.Date,            nullable=True),
        sa.Column('operational_start',  sa.Date,            nullable=True),
        sa.Column('operational_end',    sa.Date,            nullable=True),
        sa.Column('timeline_events',    JSONB,              server_default='[]'),

        # --- RELATIONSHIPS (AQID references only; graph lives in Neo4j) ---
        sa.Column('parent_aqid',        sa.String(120),     nullable=True),
        sa.Column('child_aqids',        JSONB,              server_default='[]'),
        sa.Column('related_aqids',      JSONB,              server_default='[]'),

        # --- KNOWLEDGE (Qdrant references) ---
        sa.Column('qdrant_chunk_ids',   JSONB,              server_default='[]'),
        sa.Column('document_refs',      JSONB,              server_default='[]'),

        # --- AI INTELLIGENCE ---
        sa.Column('ai_executive_summary',   sa.Text,        nullable=True),
        sa.Column('ai_extended_analysis',   sa.Text,        nullable=True),
        sa.Column('ai_key_facts',           JSONB,          server_default='[]'),
        sa.Column('ai_generated_at',        sa.DateTime,    nullable=True),
        sa.Column('ai_model_version',       sa.String(40),  nullable=True),
        sa.Column('ai_requires_refresh',    sa.Boolean,     server_default='false'),

        # --- PROVENANCE ---
        sa.Column('primary_provenance',     JSONB,          nullable=True,
                  comment='Primary ProvenanceRecord JSON'),
        sa.Column('all_sources',            JSONB,          server_default='[]'),
        sa.Column('verification_status',    sa.String(30),  server_default='unverified'),
        sa.Column('confidence_score',       sa.Float,       server_default='0.5'),

        # --- AUDIT ---
        sa.Column('created_by',         sa.String(120),     server_default='system'),
        sa.Column('updated_by',         sa.String(120),     server_default='system'),
        sa.Column('ingest_pipeline',    sa.String(80),      nullable=True),
        sa.Column('ingest_job_id',      sa.String(80),      nullable=True),
        sa.Column('change_log',         JSONB,              server_default='[]'),

        # --- VERSION ---
        sa.Column('current_version',    sa.String(20),      server_default='1.0.0'),
        sa.Column('version_history',    JSONB,              server_default='[]'),

        # --- EXTENSION (entity-class-specific typed fields) ---
        sa.Column('extension_data',     JSONB,              server_default='{}',
                  comment='Entity-class-specific fields; GIN-indexed'),
    )

    # Standard B-tree indexes
    op.create_index('ix_ae_entity_class',       'aerospace_entities', ['entity_class'])
    op.create_index('ix_ae_lifecycle_status',   'aerospace_entities', ['lifecycle_status'])
    op.create_index('ix_ae_is_active',          'aerospace_entities', ['is_active'])
    op.create_index('ix_ae_updated_at',         'aerospace_entities', ['updated_at'])
    op.create_index('ix_ae_confidence',         'aerospace_entities', ['confidence_score'])
    op.create_index('ix_ae_class_status',       'aerospace_entities', ['entity_class', 'lifecycle_status'])
    op.create_index('ix_ae_class_updated',      'aerospace_entities', ['entity_class', 'updated_at'])

    # GIN indexes for JSONB and full-text search (must use op.execute on Railway)
    op.execute("CREATE INDEX ix_ae_tags        ON aerospace_entities USING GIN (tags)")
    op.execute("CREATE INDEX ix_ae_domains     ON aerospace_entities USING GIN (domains)")
    op.execute("CREATE INDEX ix_ae_aliases     ON aerospace_entities USING GIN (aliases)")
    op.execute("CREATE INDEX ix_ae_extension   ON aerospace_entities USING GIN (extension_data)")
    op.execute("CREATE INDEX ix_ae_all_sources ON aerospace_entities USING GIN (all_sources)")

    # Full-text search index
    op.execute("""
        CREATE INDEX ix_ae_fts ON aerospace_entities
        USING GIN (
            to_tsvector('english',
                coalesce(display_name, '') || ' ' ||
                coalesce(short_name, '')   || ' ' ||
                coalesce(description, '')
            )
        )
    """)

    # Updated_at auto-update trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION update_ae_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_ae_updated_at
        BEFORE UPDATE ON aerospace_entities
        FOR EACH ROW EXECUTE FUNCTION update_ae_updated_at();
    """)

    # ------------------------------------------------------------------
    # 4. ENTITY ALIASES — cross-system external ID mappings
    # ------------------------------------------------------------------
    op.create_table(
        'entity_aliases',
        sa.Column('alias_id',           sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('aqid',               sa.String(120),
                  sa.ForeignKey('aerospace_entities.aqid', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('external_system',    sa.String(60),  nullable=False,
                  comment='NORAD / COSPAR / DOI / ISO / CIK / ITU / ISSN etc.'),
        sa.Column('external_id',        sa.String(255), nullable=False),
        sa.Column('is_primary',         sa.Boolean,     server_default='true'),
        sa.Column('notes',              sa.Text,        nullable=True),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),

        sa.UniqueConstraint('external_system', 'external_id', name='uq_alias_system_id'),
    )
    op.create_index('ix_alias_aqid',    'entity_aliases', ['aqid'])
    op.create_index('ix_alias_system',  'entity_aliases', ['external_system', 'external_id'])

    # ------------------------------------------------------------------
    # 5. ENTITY RELATIONSHIPS CACHE
    # Denormalized copy of Neo4j edges for fast REST API responses.
    # Written by the ingestion pipeline; authoritative copy is in Neo4j.
    # ------------------------------------------------------------------
    op.create_table(
        'entity_relationships_cache',
        sa.Column('rel_id',             sa.String(80),  primary_key=True),
        sa.Column('source_aqid',        sa.String(120), nullable=False, index=True),
        sa.Column('target_aqid',        sa.String(120), nullable=False, index=True),
        sa.Column('relationship_type',  sa.String(60),  nullable=False, index=True),
        sa.Column('category',           sa.String(40),  nullable=True),
        sa.Column('since',              sa.Date,        nullable=True),
        sa.Column('until',              sa.Date,        nullable=True),
        sa.Column('is_current',         sa.Boolean,     server_default='true'),
        sa.Column('is_primary',         sa.Boolean,     server_default='true'),
        sa.Column('confidence',         sa.Float,       server_default='0.8'),
        sa.Column('provenance_url',     sa.Text,        nullable=True),
        sa.Column('properties',         JSONB,          server_default='{}'),
        sa.Column('notes',              sa.Text,        nullable=True),
        sa.Column('synced_at',          sa.DateTime,    server_default=sa.func.now()),
    )
    op.create_index('ix_rel_source',    'entity_relationships_cache', ['source_aqid', 'relationship_type'])
    op.create_index('ix_rel_target',    'entity_relationships_cache', ['target_aqid', 'relationship_type'])
    op.create_index('ix_rel_current',   'entity_relationships_cache', ['is_current'])

    # ------------------------------------------------------------------
    # 6. ENTITY INGESTION LOG — full audit per entity per pipeline run
    # ------------------------------------------------------------------
    op.create_table(
        'entity_ingestion_log',
        sa.Column('log_id',             sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('aqid',               sa.String(120), nullable=False, index=True),
        sa.Column('job_id',             sa.String(80),  nullable=False, index=True),
        sa.Column('pipeline_version',   sa.String(40),  nullable=False),
        sa.Column('started_at',         sa.DateTime,    nullable=False),
        sa.Column('completed_at',       sa.DateTime,    nullable=True),
        sa.Column('status',             sa.String(20),  nullable=False,
                  comment='success / failed / disputed / skipped'),
        sa.Column('source_url',         sa.Text,        nullable=True),
        sa.Column('source_type',        sa.String(40),  nullable=True),
        sa.Column('entities_created',   sa.Integer,     server_default='0'),
        sa.Column('entities_updated',   sa.Integer,     server_default='0'),
        sa.Column('relationships_added', sa.Integer,    server_default='0'),
        sa.Column('chunks_indexed',     sa.Integer,     server_default='0'),
        sa.Column('contradictions',     JSONB,          server_default='[]'),
        sa.Column('errors',             JSONB,          server_default='[]'),
        sa.Column('warnings',           JSONB,          server_default='[]'),
        sa.Column('raw_payload',        JSONB,          nullable=True),
    )
    op.create_index('ix_log_aqid',      'entity_ingestion_log', ['aqid'])
    op.create_index('ix_log_job',       'entity_ingestion_log', ['job_id'])
    op.create_index('ix_log_status',    'entity_ingestion_log', ['status'])
    op.create_index('ix_log_started',   'entity_ingestion_log', ['started_at'])


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ae_updated_at ON aerospace_entities")
    op.execute("DROP FUNCTION IF EXISTS update_ae_updated_at()")
    op.drop_table('entity_ingestion_log')
    op.drop_table('entity_relationships_cache')
    op.drop_table('entity_aliases')
    op.drop_table('aerospace_entities')
    op.drop_table('relationship_type_registry')
    op.drop_table('knowledge_domains')
