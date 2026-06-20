"""
ORBITIQ-X Backend — Async Database Engine & Session Factory

Architecture
────────────
  create_async_engine()          → single engine per process
  async_sessionmaker()           → session factory bound to engine
  get_session()                  → FastAPI dependency (request-scoped)
  transactional()                → context manager for unit-of-work
  init_db() / close_db()         → lifespan hooks called by main.py

Connection pool (50K-object SSA at scale)
──────────────────────────────────────────
  pool_size    = 20  (persistent connections per process)
  max_overflow = 10  (burst capacity → 30 total during screening peaks)
  pool_timeout = 30s
  pool_recycle = 1800s (avoid stale TCP after 30 min)
  pool_pre_ping = True (validate before checkout)

  At 4 workers × 20 pool = 80 base connections.
  Set PG max_connections ≥ 200 for headroom.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine(database_url: str, pool_size: int, max_overflow: int) -> AsyncEngine:
    engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False,
        echo_pool=False,
        connect_args={
            "server_settings": {
                "application_name": "orbitiq-x-backend",
                "jit": "off",
            },
            "command_timeout": 60,
        },
    )

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_connection, connection_record):
        logger.debug("db_pool_connect id=%s", id(dbapi_connection))

    return engine


async def init_db() -> None:
    """Initialise engine + session factory. Called once at startup."""
    global _engine, _session_factory

    from app.core.config import get_settings
    settings = get_settings()

    _engine = _build_engine(
        database_url=settings.DATABASE_URL,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with _engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

    logger.info(
        "db_engine_ready host=%s port=%s db=%s pool=%s+%s",
        settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB,
        settings.POSTGRES_POOL_SIZE, settings.POSTGRES_MAX_OVERFLOW,
    )


async def close_db() -> None:
    """Dispose the connection pool. Called at shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("db_engine_disposed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields a request-scoped AsyncSession.

    Auto-commits on clean exit, rolls back on any exception.
    Use transactional() for multi-step atomic operations.
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.error("session_rollback error=%s", exc)
            raise
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def transactional(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """
    Context manager for explicit multi-table atomic transactions.

    Usage::

        async with transactional(session) as txn:
            await satellite_repo.upsert(txn, data)
            await tle_repo.insert(txn, tle)
    """
    async with session.begin():
        try:
            yield session
        except SQLAlchemyError as exc:
            logger.error("transaction_rollback error=%s", exc)
            raise


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return raw factory for background tasks / scheduler jobs."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised.")
    return _session_factory


def get_engine() -> AsyncEngine:
    """Return the engine (for Alembic and health checks)."""
    if _engine is None:
        raise RuntimeError("Database not initialised.")
    return _engine
