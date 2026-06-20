"""init: create PostgreSQL extensions

Revision ID: 0001_init_extensions
Revises: None
Create Date: 2026-06-20 00:01:00
"""
from __future__ import annotations
from alembic import op

revision = "0001_init_extensions"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Enable required PostgreSQL extensions."""
    # UUID generation in SQL
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    # pg_stat_statements for query monitoring
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_stat_statements"')
    # btree_gin for composite GIN indexes on regular columns
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin"')
    # pg_trgm for fuzzy text search on satellite names
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')


def downgrade() -> None:
    """Drop extensions — only if no objects depend on them."""
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "btree_gin"')
    # Do NOT drop pg_stat_statements in production — loses monitoring data
    # Do NOT drop uuid-ossp — may be used by other schemas
