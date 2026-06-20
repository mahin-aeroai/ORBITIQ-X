"""
ORBITIQ-X — Redis async session
================================
Initialises a redis.asyncio client from app settings.
Used by:
  - catalog_scheduler.py (distributed lock + metrics cache)
  - conjunction_service.py (alert pub/sub)
  - catalog endpoints (TLE hot cache)

Graceful degradation: if Redis is unreachable at startup, the app
starts without caching. All callers check get_redis() for None.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

_redis = None


async def init_redis() -> None:
    """Connect to Redis using REDIS_URL from settings. Non-fatal on failure."""
    global _redis
    try:
        import redis.asyncio as aioredis
        from app.core.config import get_settings
        s = get_settings()
        _redis = aioredis.from_url(
            s.REDIS_URL,
            encoding="utf-8",
            decode_responses=False,   # raw bytes — callers decode as needed
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        # Smoke test
        await _redis.ping()
        logger.info("redis_connected url=%s", s.REDIS_URL.split("@")[-1])
    except Exception as exc:
        logger.warning(
            "redis_init_failed error=%s — continuing without cache/pub-sub",
            exc,
        )
        _redis = None


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("redis_closed")


def get_redis():
    """Return the Redis client or None if not connected."""
    return _redis
