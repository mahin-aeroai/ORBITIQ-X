"""ORBITIQ-X — Redis async session (stub; implement in Phase 2)."""
import logging
logger = logging.getLogger(__name__)

_redis = None

async def init_redis() -> None:
    logger.info("redis_init_skipped (stub)")

async def close_redis() -> None:
    logger.info("redis_close_skipped (stub)")

def get_redis():
    return _redis
