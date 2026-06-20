"""
ORBITIQ-X — Neo4j session module (delegates to app.graph.connection)

This module preserves the import path that main.py expects:
    from app.db.neo4j_session import init_neo4j, close_neo4j

All real implementation lives in app.graph.connection.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)


async def init_neo4j() -> None:
    """Initialise Neo4j driver and apply schema. Called at app startup."""
    from app.graph.connection import init_neo4j_driver, init_schema
    await init_neo4j_driver()
    await init_schema()


async def close_neo4j() -> None:
    """Dispose Neo4j driver. Called at app shutdown."""
    from app.graph.connection import close_neo4j_driver
    await close_neo4j_driver()
