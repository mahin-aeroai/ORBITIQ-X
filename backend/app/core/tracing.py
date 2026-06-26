"""
ORBITIQ-X — OpenTelemetry Distributed Tracing
===============================================
Fully optional. The application starts normally whether or not
any OpenTelemetry package is installed.

All imports are guarded with try/except. No import failure can
crash the application or cause logging exceptions.

Environment control:
  ENABLE_OTEL=false  — explicitly disable tracing (default: false in production
                       unless OTEL_EXPORTER_OTLP_ENDPOINT is set)
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

# Use stdlib logging only — structlog may not be configured yet when
# this module is imported. Never use structlog here directly.
logger = logging.getLogger(__name__)

# Module-level tracer — None until init_tracing() succeeds
_tracer = None


def init_tracing(app=None) -> None:
    """
    Initialise OpenTelemetry SDK. Called from main.py lifespan.

    Completely optional — any ImportError or runtime error is caught
    and logged at INFO level. The application continues normally.
    """
    global _tracer

    # ── Explicit opt-out via environment variable ──────────────
    if os.environ.get("ENABLE_OTEL", "").lower() in ("false", "0", "no", "off"):
        logger.info("otel_disabled: ENABLE_OTEL=false — tracing skipped")
        return

    # ── Check if OpenTelemetry SDK is available ────────────────
    try:
        import opentelemetry  # noqa: F401
    except ImportError:
        logger.info("otel_sdk_not_installed — tracing skipped (install opentelemetry-sdk to enable)")
        return

    # ── Full initialisation (all failures are non-fatal) ───────
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        try:
            from app.core.config import get_settings
            settings = get_settings()
            service_name = settings.OTEL_SERVICE_NAME
            service_version = settings.ORBITIQ_VERSION
            env = settings.ORBITIQ_ENV
            otlp_endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
        except Exception:
            service_name = "orbitiq-x-backend"
            service_version = "0.1.0"
            env = os.environ.get("ORBITIQ_ENV", "production")
            otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")

        resource = Resource.create({
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": env,
        })
        provider = TracerProvider(resource=resource)

        # ── Exporter ───────────────────────────────────────────
        exporter_configured = False

        if env == "development":
            try:
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                exporter_configured = True
                logger.info("otel_console_exporter_configured")
            except Exception as exc:
                logger.debug("otel_console_exporter_failed: %s", exc)
        elif otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                otlp = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp))
                exporter_configured = True
                logger.info("otel_otlp_exporter_configured endpoint=%s", otlp_endpoint)
            except ImportError:
                logger.info(
                    "otel_otlp_exporter_not_installed — install opentelemetry-exporter-otlp-proto-grpc "
                    "to enable OTLP export. Tracing continues without export."
                )
            except Exception as exc:
                logger.info("otel_otlp_exporter_failed: %s — tracing without export", exc)
        else:
            logger.info("otel_no_endpoint_configured — tracing initialised without exporter")

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)

        # ── FastAPI instrumentation ────────────────────────────
        if app is not None:
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/metrics")
                logger.info("otel_fastapi_instrumented")
            except Exception as exc:
                logger.debug("otel_fastapi_instrument_failed: %s", exc)

        # ── SQLAlchemy instrumentation ─────────────────────────
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument()
            logger.info("otel_sqlalchemy_instrumented")
        except Exception as exc:
            logger.debug("otel_sqlalchemy_instrument_failed: %s", exc)

        logger.info("otel_tracing_initialised service=%s exporter=%s", service_name, exporter_configured)

    except Exception as exc:
        # Catch-all — tracing must never crash the application
        logger.info("otel_init_skipped: %s — application continues normally", exc)
        _tracer = None


@contextmanager
def trace_span(name: str, attributes: dict | None = None) -> Generator:
    """
    Context manager for manual spans. No-ops if tracing not initialised.

    Usage::

        with trace_span("conjunction_screening", {"object_count": len(catalog)}):
            ...
    """
    if _tracer is None:
        yield
        return

    try:
        from opentelemetry import trace
        with _tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception:
                        pass
            yield span
    except Exception:
        yield


def get_tracer():
    """Return the configured tracer, or None if tracing is not initialised."""
    return _tracer
