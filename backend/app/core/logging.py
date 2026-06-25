"""
ORBITIQ-X — Structured Logging Configuration
=============================================
Configures structlog with JSON output in production and
human-readable console output in development.

Every log event includes:
  timestamp   — ISO 8601 UTC
  level       — DEBUG / INFO / WARNING / ERROR / CRITICAL
  service     — "orbitiq-x-backend"
  logger      — calling module name
  request_id  — injected by middleware via contextvars
  message     — event string

In production (ORBITIQ_ENV=production):
  Output: JSON on stdout — ingested by Grafana Loki / CloudWatch / Datadog.

In development:
  Output: coloured console with timestamps.
"""
from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """
    Configure structlog + stdlib logging.
    Call once at startup from main.py lifespan.
    """
    import structlog

    log_level = getattr(logging, level.upper(), logging.INFO)

    # ── stdlib root logger ────────────────────────────────────
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    # Quiet noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── Detect environment ─────────────────────────────────────
    try:
        from app.core.config import get_settings
        env = get_settings().ORBITIQ_ENV
    except Exception:
        env = "development"

    # ── Shared processors ──────────────────────────────────────
    def _safe_add_logger_name(logger, method_name, event_dict):
        """Safe version of add_logger_name that handles None logger."""
        try:
            if logger is not None and hasattr(logger, "name"):
                event_dict["logger"] = logger.name
            else:
                event_dict["logger"] = "unknown"
        except Exception:
            event_dict["logger"] = "unknown"
        return event_dict

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _safe_add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if env == "production":
        # JSON — machine-readable, ingested by log aggregators
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable for dev
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Wire stdlib → structlog so libraries that use logging.getLogger also go through
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *shared_processors,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)
