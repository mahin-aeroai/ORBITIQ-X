"""
ORBITIQ-X — Neo4j Connection Manager
======================================
Production-grade Neo4j async driver with:
  - Connection pooling (neo4j driver internal pool)
  - Health checks (ping via lightweight Cypher)
  - Retry logic (tenacity exponential backoff)
  - Transaction management helpers
  - Graceful shutdown

Architecture
─────────────
  This module owns the single AsyncDriver instance per process.
  It is initialised once at application startup (init_neo4j in
  neo4j_session.py → now delegates here) and disposed at shutdown.

  Graph operations MUST use:
    1. get_driver()              → raw driver for complex multi-query transactions
    2. execute_read(cypher, **p) → short-circuit read helper
    3. execute_write(cypher, **p)→ short-circuit write helper (single statement)
    4. execute_batch(cypher, batch) → UNWIND batch upsert helper

  All callers that need the driver must import from this module.
  Do NOT import neo4j.AsyncGraphDatabase anywhere else in the backend.

Audit notes
────────────
  - config.py already has NEO4J_HOST, NEO4J_BOLT_PORT, NEO4J_USER,
    NEO4J_PASSWORD, NEO4J_DATABASE, NEO4J_URI  ← reused
  - neo4j_session.py is a 5-line stub → replaced by delegation here
  - graph_loader.py in knowledge-graph/ creates its own driver ← fine,
    separate process; this file owns the backend runtime driver
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ── Module-level singleton ────────────────────────────────────
_driver: AsyncDriver | None = None
_database: str = "neo4j"


class Neo4jConnectionError(Exception):
    """Raised when Neo4j is unreachable or the driver is not initialised."""


# ── Lifecycle ─────────────────────────────────────────────────

async def init_neo4j_driver() -> None:
    """
    Initialise the global AsyncDriver.

    Called once at application startup. Reads all configuration from
    app.core.config.Settings (already has NEO4J_* fields).

    Graceful degradation: if Neo4j is unavailable, logs a warning and
    continues — the application starts without graph capabilities.
    """
    global _driver, _database

    try:
        from app.core.config import get_settings
        s = get_settings()

        _database = s.NEO4J_DATABASE
        _driver = AsyncGraphDatabase.driver(
            s.NEO4J_URI,
            auth=(s.NEO4J_USER, s.NEO4J_PASSWORD.get_secret_value()),
            max_connection_pool_size=50,
            connection_timeout=10.0,
            max_transaction_retry_time=30.0,
        )

        # Smoke test
        await _verify_connectivity()
        logger.info(
            "neo4j_connected uri=%s database=%s",
            s.NEO4J_URI, _database,
        )

    except Exception as exc:
        logger.warning(
            "neo4j_init_failed error=%s — graph features disabled",
            exc,
        )
        _driver = None


async def close_neo4j_driver() -> None:
    """Dispose the driver and close all pooled connections."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        logger.info("neo4j_driver_closed")


async def _verify_connectivity() -> None:
    """Run a lightweight Cypher query to confirm Neo4j is reachable."""
    if _driver is None:
        return
    async with _driver.session(database=_database) as session:
        result = await session.run("RETURN 1 AS ping")
        record = await result.single()
        assert record["ping"] == 1


# ── Driver accessor ───────────────────────────────────────────

def get_driver() -> AsyncDriver:
    """
    Return the global driver. Raises if not initialised.

    Use this when you need raw session control (multi-statement
    transactions, explicit bookmarks, etc.).
    """
    if _driver is None:
        raise Neo4jConnectionError(
            "Neo4j driver not initialised. "
            "Check NEO4J_* environment variables and Neo4j connectivity."
        )
    return _driver


def is_available() -> bool:
    """Return True if the driver is initialised and likely connected."""
    return _driver is not None


# ── Session context manager ───────────────────────────────────

@asynccontextmanager
async def get_graph_session() -> AsyncIterator[AsyncSession]:
    """
    Async context manager yielding a Neo4j session.

    FastAPI dependency usage::

        from fastapi import Depends

        async def my_endpoint(
            session: AsyncSession = Depends(get_graph_session),
        ):
            ...

    Direct usage::

        async with get_graph_session() as session:
            result = await session.run("MATCH (n) RETURN count(n)")
    """
    driver = get_driver()
    async with driver.session(database=_database) as session:
        yield session


# ── Query helpers ─────────────────────────────────────────────

async def execute_read(cypher: str, **params: Any) -> list[dict]:
    """
    Run a read-only Cypher query with automatic retry.

    Parameters
    ----------
    cypher : str
        The Cypher query. Use $param_name for parameters.
    **params
        Named query parameters.

    Returns
    -------
    list[dict]
        All result rows as dicts.

    Raises
    ------
    Neo4jConnectionError
        If the driver is not initialised.
    """
    driver = get_driver()

    async def _run() -> list[dict]:
        async with driver.session(database=_database) as session:
            result = await session.run(cypher, **params)
            return await result.data()

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(Exception),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            stop=stop_after_attempt(3),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        ):
            with attempt:
                return await _run()
    except RetryError as exc:
        raise Neo4jConnectionError(f"Neo4j read failed after retries: {exc}") from exc
    return []


async def execute_write(cypher: str, **params: Any) -> dict:
    """
    Run a write Cypher query in an explicit write transaction.

    Returns summary counters dict: nodes_created, relationships_created, etc.
    """
    driver = get_driver()

    async def _tx(tx) -> dict:
        result = await tx.run(cypher, **params)
        summary = await result.consume()
        return {
            "nodes_created":         summary.counters.nodes_created,
            "nodes_deleted":         summary.counters.nodes_deleted,
            "relationships_created": summary.counters.relationships_created,
            "properties_set":        summary.counters.properties_set,
        }

    async with driver.session(database=_database) as session:
        return await session.execute_write(_tx)


async def execute_batch(
    cypher: str,
    batch: list[dict],
    batch_size: int = 500,
) -> dict:
    """
    Run a UNWIND batch upsert.

    The Cypher must accept `$batch` as a list parameter::

        UNWIND $batch AS row
        MERGE (s:Satellite {noradId: row.noradId})
        SET s += row

    Parameters
    ----------
    cypher : str
        UNWIND Cypher with $batch parameter.
    batch : list[dict]
        Records to upsert.
    batch_size : int
        Records per transaction (default 500).

    Returns
    -------
    dict
        Accumulated summary counters.
    """
    if not batch:
        return {"nodes_created": 0, "relationships_created": 0}

    driver = get_driver()
    total_counters: dict[str, int] = {
        "nodes_created": 0,
        "relationships_created": 0,
        "properties_set": 0,
    }

    for i in range(0, len(batch), batch_size):
        chunk = batch[i : i + batch_size]

        async def _tx(tx, _chunk=chunk) -> dict:
            result = await tx.run(cypher, batch=_chunk)
            summary = await result.consume()
            return {
                "nodes_created":         summary.counters.nodes_created,
                "relationships_created": summary.counters.relationships_created,
                "properties_set":        summary.counters.properties_set,
            }

        async with driver.session(database=_database) as session:
            counters = await session.execute_write(_tx)
            for k in total_counters:
                total_counters[k] += counters.get(k, 0)

        logger.debug(
            "neo4j_batch_chunk batch=%d/%d nodes=%d rels=%d",
            i // batch_size + 1,
            (len(batch) - 1) // batch_size + 1,
            counters["nodes_created"],
            counters["relationships_created"],
        )

    return total_counters


# ── Health check ──────────────────────────────────────────────

async def health_check() -> dict:
    """
    Return Neo4j health status for the /catalog/health and monitoring endpoints.

    Returns
    -------
    dict
        Keys: reachable (bool), database (str), node_count (int), error (str|None)
    """
    if not is_available():
        return {
            "reachable":  False,
            "database":   _database,
            "node_count": 0,
            "error":      "Driver not initialised",
        }

    try:
        rows = await execute_read("MATCH (n) RETURN count(n) AS cnt LIMIT 1")
        cnt  = rows[0]["cnt"] if rows else 0
        return {
            "reachable":  True,
            "database":   _database,
            "node_count": cnt,
            "error":      None,
        }
    except Exception as exc:
        return {
            "reachable":  False,
            "database":   _database,
            "node_count": 0,
            "error":      str(exc),
        }


# ── Schema initialiser ────────────────────────────────────────

async def init_schema() -> None:
    """
    Apply all Cypher schema files from knowledge-graph/schema/.
    Safe to call on every startup (IF NOT EXISTS guards).

    Calls the existing initialize_schema() function from graph_loader.py
    which already reads and applies 01_constraints.cypher → 04_queries.cypher.
    """
    if not is_available():
        logger.warning("neo4j_schema_init_skipped — driver not available")
        return

    try:
        driver = get_driver()

        import pathlib
        schema_dir = (
            pathlib.Path(__file__).parents[4]
            / "knowledge-graph" / "schema"
        )
        if not schema_dir.exists():
            logger.warning("neo4j_schema_dir_not_found path=%s", schema_dir)
            return

        for cypher_file in sorted(schema_dir.glob("0*.cypher")):
            logger.info("neo4j_schema_apply file=%s", cypher_file.name)
            statements = cypher_file.read_text().split(";")
            async with driver.session(database=_database) as session:
                for stmt in statements:
                    stmt = stmt.strip()
                    if stmt and not stmt.startswith("//"):
                        try:
                            await session.run(stmt)
                        except Exception as exc:
                            logger.debug(
                                "neo4j_schema_stmt_skipped file=%s error=%s",
                                cypher_file.name, exc,
                            )

        logger.info("neo4j_schema_init_complete")

    except Exception as exc:
        logger.warning("neo4j_schema_init_failed error=%s", exc)
