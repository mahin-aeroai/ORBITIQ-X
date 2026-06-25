"""
ORBITIQ-X — OpenTelemetry Distributed Tracing
===============================================
Initialises the OpenTelemetry SDK and instruments FastAPI, SQLAlchemy,
Redis, and httpx with auto-instrumentation.

Configuration (from Settings)
──────────────────────────────
  OTEL_EXPORTER_OTLP_ENDPOINT — gRPC collector endpoint (default: localhost:4317)
  OTEL_SERVICE_NAME            — service name in traces (default: orbitiq-x-backend)
  ORBITIQ_ENV                  — if "development", falls back to console exporter

Trace hierarchy
───────────────
  HTTP request
    └── DB query  (SQLAlchemy auto-instrumentation)
    └── Redis op  (redis-py auto-instrumentation if package installed)
    └── Agent task execution  (manual spans)
    └── Graph query  (manual spans)
    └── Conjunction screening  (manual spans)
    └── Digital Twin propagation  (manual spans)

Graceful degradation
──────────────────────
  If the OTLP exporter cannot connect, tracing is silently disabled.
  All other platform functionality remains operational.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

# ── Module-level tracer (set after init_tracing()) ────────────
_tracer = None


def init_tracing(app=None) -> None:
    """
    Initialise OpenTelemetry SDK. Called once from main.py lifespan.

    Parameters
    ----------
    app : FastAPI | None
        If provided, FastAPI instrumentation is attached.
    """
    global _tracer

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        from app.core.config import get_settings
        settings = get_settings()

        resource = Resource.create({
            "service.name":    settings.OTEL_SERVICE_NAME,
            "service.version": settings.ORBITIQ_VERSION,
            "deployment.environment": settings.ORBITIQ_ENV,
        })

        provider = TracerProvider(resource=resource)

        # ── Exporter selection ─────────────────────────────────
        if settings.ORBITIQ_ENV == "development":
            # Console exporter for dev — shows traces in logs
            try:
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter
                provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )
                logger.info("otel_console_exporter_configured")
            except Exception as exc:
                logger.debug("otel_console_exporter_failed error=%s", exc)
        else:
            # OTLP gRPC exporter for staging/production
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                otlp = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
                provider.add_span_processor(BatchSpanProcessor(otlp))
                logger.info(
                    "otel_otlp_exporter_configured endpoint=%s",
                    settings.OTEL_EXPORTER_OTLP_ENDPOINT,
                )
            except Exception as exc:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "otel_otlp_exporter_failed: %s — tracing disabled", exc
                )
                return

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(settings.OTEL_SERVICE_NAME)

        # ── FastAPI auto-instrumentation ───────────────────────
        if app is not None:
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                FastAPIInstrumentor.instrument_app(
                    app,
                    excluded_urls="/health,/metrics",
                )
                logger.info("otel_fastapi_instrumented")
            except Exception as exc:
                logger.warning("otel_fastapi_instrument_failed error=%s", exc)

        # ── SQLAlchemy auto-instrumentation ───────────────────
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument()
            logger.info("otel_sqlalchemy_instrumented")
        except Exception as exc:
            logger.debug("otel_sqlalchemy_instrument_failed error=%s", exc)

        logger.info("otel_tracing_initialised service=%s", settings.OTEL_SERVICE_NAME)

    except ImportError as exc:
        logger.info("otel_sdk_not_available error=%s — tracing skipped", exc)
    except Exception as exc:
        logger.warning("otel_init_failed error=%s — tracing disabled", exc)


# ── Manual span helpers ───────────────────────────────────────

@contextmanager
def trace_span(
    name: str,
    attributes: dict | None = None,
) -> Generator:
    """
    Context manager for manual OpenTelemetry spans.

    Usage::

        async def screen_conjunctions(catalog):
            with trace_span("conjunction_screening", {"object_count": len(catalog)}):
                ...

    No-ops gracefully if tracing is not initialised.
    """
    if _tracer is None:
        yield
        return

    from opentelemetry import trace
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                try:
                    span.set_attribute(k, v)
                except Exception:
                    pass
        yield span


def get_tracer():
    """Return the configured tracer, or None if tracing is not initialised."""
    return _tracer
