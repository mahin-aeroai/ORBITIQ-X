"""
ORBITIQ-X — Redis Async Session
Phase 18 — Redis Activation + Digital Twin

Manages the Redis connection with:
  - Retry logic with exponential backoff on initial connect
  - Background reconnection task when connection drops
  - Diagnostic detail for health endpoint
  - Graceful degradation — all callers check get_redis() for None

Used by:
  - catalog_scheduler.py  (distributed lock + metrics cache)
  - conjunction_service.py (alert pub/sub → SSE)
  - digital_twin_repository.py (live state TTL cache)
  - catalog endpoints (TLE hot cache)

Railway note:
  Set REDIS_URL in Railway Variables.
  Format: redis://default:<password>@<host>:<port>
  Railway Redis plugin injects this automatically when provisioned.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_redis = None
_last_error: Optional[str]  = None
_connected_at: Optional[float] = None
_connection_attempts: int   = 0
_reconnect_task: Optional[asyncio.Task] = None

# Retry configuration
INITIAL_RETRY_DELAY_S   = 2
MAX_RETRY_DELAY_S       = 60
MAX_INIT_ATTEMPTS       = 5


async def init_redis(max_attempts: int = MAX_INIT_ATTEMPTS) -> bool:
    """
    Connect to Redis with retry + exponential backoff.

    Returns True if connected, False if all attempts failed.
    Never raises — failure is non-fatal.
    """
    global _redis, _last_error, _connected_at, _connection_attempts

    import redis.asyncio as aioredis
    from app.core.config import get_settings

    settings = get_settings()
    url = settings.REDIS_URL

    if not url or url.startswith("redis://:@"):
        # No credentials configured — check for bare REDIS_URL env var
        env_url = os.environ.get("REDIS_URL", "")
        if env_url:
            url = env_url
        else:
            logger.warning(
                "redis_no_url — REDIS_URL not set. "
                "Add REDIS_URL to Railway Variables to enable Redis."
            )
            _last_error = "REDIS_URL not configured"
            return False

    delay = INITIAL_RETRY_DELAY_S

    for attempt in range(1, max_attempts + 1):
        _connection_attempts += 1
        try:
            client = aioredis.from_url(
                url,
                encoding="utf-8",
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            await client.ping()
            _redis           = client
            _last_error      = None
            _connected_at    = time.time()
            logger.info(
                "redis_connected attempt=%d url=%s",
                attempt,
                url.split("@")[-1] if "@" in url else url[-20:],
            )
            # Start background reconnection monitor
            _start_reconnect_monitor()
            return True

        except Exception as exc:
            _last_error = str(exc)
            logger.warning(
                "redis_connect_failed attempt=%d/%d error=%s retrying_in=%ds",
                attempt, max_attempts, exc, delay,
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY_S)

    logger.warning(
        "redis_unavailable — all %d connection attempts failed. "
        "Platform starts without Redis. "
        "Set REDIS_URL in Railway Variables to enable caching and pub/sub.",
        max_attempts,
    )
    return False


async def close_redis() -> None:
    """Close the Redis connection and cancel the reconnect monitor."""
    global _redis, _reconnect_task
    if _reconnect_task and not _reconnect_task.done():
        _reconnect_task.cancel()
        _reconnect_task = None
    if _redis:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None
        logger.info("redis_closed")


def get_redis():
    """Return the active Redis client, or None if not connected."""
    return _redis


def get_redis_status() -> dict:
    """
    Return a detailed Redis connection status dict for the health endpoint.
    """
    global _redis, _last_error, _connected_at, _connection_attempts
    connected = _redis is not None
    return {
        "connected":            connected,
        "status":               "healthy" if connected else "unavailable",
        "last_error":           _last_error,
        "connected_at":         _connected_at,
        "uptime_s":             round(time.time() - _connected_at, 1) if _connected_at else None,
        "connection_attempts":  _connection_attempts,
        "impact_if_down": [
            "SSE conjunction alerts disabled (frontend polling fallback active)",
            "Digital Twin live state uses in-memory only (no TTL eviction)",
            "Distributed scheduler lock unavailable (APScheduler memory fallback)",
            "TLE hot cache disabled (DB queries used instead)",
        ] if not connected else [],
        "fix": (
            "Add REDIS_URL to Railway Variables. "
            "Format: redis://default:<password>@<host>:<port>"
        ) if not connected else None,
    }


async def reconnect_redis() -> bool:
    """
    Attempt to reconnect to Redis.
    Called manually from the health endpoint or the reconnect monitor.
    """
    global _redis
    if _redis:
        try:
            await _redis.ping()
            return True  # Already connected
        except Exception:
            _redis = None

    return await init_redis(max_attempts=3)


def _start_reconnect_monitor() -> None:
    """Start a background task that pings Redis and reconnects on failure."""
    global _reconnect_task

    async def _monitor():
        while True:
            await asyncio.sleep(60)  # Check every 60s
            global _redis
            if _redis:
                try:
                    await _redis.ping()
                except Exception as exc:
                    logger.warning("redis_ping_failed error=%s — attempting reconnect", exc)
                    _redis = None
                    await reconnect_redis()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _reconnect_task = loop.create_task(_monitor())
    except RuntimeError:
        pass
