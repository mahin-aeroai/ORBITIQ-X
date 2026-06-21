"""
ORBITIQ-X — SSA Conjunction Alert SSE Bridge
==============================================
Streams Redis pub/sub conjunction alert events to the frontend
via Server-Sent Events (text/event-stream).

Endpoint: GET /api/v1/ssa/alerts/stream

Redis channel: orbitiq:conjunction:alerts
Event format:
    event: conjunction_alert
    data:  {"conjunction_id": "...", "risk_level": "red", "pc": 0.003, ...}

Behaviour:
  • When Redis is available: streams real-time push events from the channel.
  • When Redis is unavailable: streams a heartbeat every 30s so the frontend
    EventSource stays connected and falls back to polling gracefully.
  • Heartbeat keep-alives every 15 seconds prevent proxy timeouts.
  • Max connection duration: 10 minutes (EventSource auto-reconnects).

This endpoint is registered on the existing /ssa router prefix so it appears
as /api/v1/ssa/alerts/stream without touching any other router.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()

REDIS_CHANNEL      = "orbitiq:conjunction:alerts"
HEARTBEAT_INTERVAL = 15     # seconds — prevents proxy/CDN timeout
MAX_DURATION       = 600    # seconds — 10 min max per connection


# ── SSE helpers ───────────────────────────────────────────────

def _sse_comment(msg: str = "") -> str:
    """SSE keepalive comment line."""
    return f": {msg}\n\n"


def _sse_event(event_name: str, data: dict | str) -> str:
    """Format a named SSE event frame."""
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event_name}\ndata: {payload}\n\n"


# ── Generator — Redis live stream ─────────────────────────────

async def _redis_sse_generator(
    redis,
) -> AsyncGenerator[str, None]:
    """Stream events from Redis pub/sub channel."""
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(REDIS_CHANNEL)
        logger.info("sse_bridge_subscribed channel=%s", REDIS_CHANNEL)

        deadline = time.monotonic() + MAX_DURATION
        last_heartbeat = time.monotonic()

        while time.monotonic() < deadline:
            # Non-blocking message check
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )

            if message and message.get("type") == "message":
                raw = message.get("data", b"")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"raw": raw}

                yield _sse_event("conjunction_alert", payload)
                logger.debug(
                    "sse_bridge_event conjunction_id=%s",
                    payload.get("conjunction_id", "?"),
                )

            # Heartbeat
            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield _sse_comment("heartbeat")
                last_heartbeat = now

            # Small sleep to avoid busy-wait
            await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        logger.info("sse_bridge_client_disconnected")
    except Exception as exc:
        logger.warning("sse_bridge_error error=%s", exc)
        yield _sse_event("error", {"message": "Stream error — client should reconnect"})
    finally:
        try:
            await pubsub.unsubscribe(REDIS_CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass
        logger.info("sse_bridge_closed")


# ── Generator — heartbeat-only (no Redis) ─────────────────────

async def _heartbeat_only_generator() -> AsyncGenerator[str, None]:
    """Fallback: just keep the connection alive when Redis is absent."""
    deadline = time.monotonic() + MAX_DURATION
    while time.monotonic() < deadline:
        yield _sse_comment("no-redis-heartbeat")
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except asyncio.CancelledError:
            break


# ── Endpoint ──────────────────────────────────────────────────

@router.get(
    "/alerts/stream",
    summary="Conjunction alert SSE stream",
    description=(
        "Server-Sent Events stream of real-time conjunction alerts. "
        "Events are published to Redis channel 'orbitiq:conjunction:alerts' "
        "by the ConjunctionPersistenceService when a RED or YELLOW event is created. "
        "The frontend EventSource uses this to invalidate the high-risk query cache "
        "and increment the new-alert badge. "
        "When Redis is unavailable, emits heartbeat comments so the EventSource "
        "stays open and the client falls back to polling gracefully. "
        "Max connection duration: 10 minutes (EventSource auto-reconnects)."
    ),
    response_class=StreamingResponse,
)
async def conjunction_alert_stream() -> StreamingResponse:
    from app.db.redis_session import get_redis

    redis = get_redis()

    generator = (
        _redis_sse_generator(redis)
        if redis
        else _heartbeat_only_generator()
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering":"no",
            "Connection":       "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
