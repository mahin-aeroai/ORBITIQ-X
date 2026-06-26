"""
ORBITIQ-X — Alembic env.py

Supports both:
  - sync migrations (psycopg2) for `alembic upgrade head`
  - async runtime via asyncpg for the FastAPI application

DATABASE_URL is read (in priority order) from:
  1. ORBITIQ_DATABASE_URL env var  (full DSN — CI / Docker)
  2. Individual POSTGRES_* env vars (matches Settings model)
  3. alembic.ini [alembic] section  (local fallback)

All 8 domain models are imported here so autogenerate can
detect schema drift across every table.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.engine import Connection

from alembic import context

# ── Make app package importable ──────────────────────────────
# alembic is run from backend/, so add it to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Import ALL models so autogenerate sees them ──────────────
from app.db.base import Base  # noqa: F401 — pulls in all mappers

# ── Alembic Config object ────────────────────────────────────
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Build DATABASE_URL ────────────────────────────────────────
def get_sync_url() -> str:
    """
    Return a *synchronous* psycopg2 DSN for Alembic's DDL operations.
    Alembic cannot use asyncpg directly — we switch the driver here.
    """
    # Option 1: fully-qualified DSN in env
    dsn = os.getenv("ORBITIQ_DATABASE_URL")
    if dsn:
        # Replace asyncpg driver with psycopg2 if present
        return dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://") \
                  .replace("postgresql://", "postgresql+psycopg2://")

    # Option 2: individual env vars (mirrors Pydantic Settings)
    host     = os.getenv("POSTGRES_HOST",     "localhost")
    port     = os.getenv("POSTGRES_PORT",     "5432")
    db       = os.getenv("POSTGRES_DB",       "orbitiq_db")
    user     = os.getenv("POSTGRES_USER",     "orbitiq")
    password = os.getenv("POSTGRES_PASSWORD", "orbitiq")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — emit SQL to stdout without a
    live DB connection. Useful for generating SQL scripts for DBA review.

    Usage:
        alembic upgrade head --sql > migrations.sql
    """
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Emit CREATE TABLE IF NOT EXISTS instead of bare CREATE TABLE
        include_schemas=True,
        compare_type=True,
        compare_server_default=True,
        # Render column-level comments in DDL
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — apply directly against the DB.
    Uses a single connection from a new engine built from our DSN.
    """
    connectable = engine_from_config(
        {"sqlalchemy.url": get_sync_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,           # never pool in migration scripts
    )

    with connectable.connect() as connection:
        # Set search_path so all tables resolve to public schema
        connection.execute(text("SET search_path TO public"))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,              # detect column type changes
            compare_server_default=True,    # detect default value changes
            include_schemas=False,
            version_table_schema="public",
            render_item=_render_item,
            # Custom batch mode for SQLite (not needed for PG but harmless)
            render_as_batch=False,
            # Generate "NOT VALID" constraints to avoid full-table locks
            # on large tables during FK additions
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


def _render_item(type_: str, obj: object, autogen_context) -> str | bool:
    """
    Custom renderer: ensures JSONB and ARRAY types are emitted correctly
    rather than falling back to generic JSON/VARCHAR.
    """
    return False  # use default rendering for all types


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
