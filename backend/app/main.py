"""
ORBITIQ-X Backend — Application Entry Point
============================================
FastAPI application factory with middleware stack, lifespan context,
health checks, and API router registration.
"""
from __future__ import annotations

import sys
import os as _os
# Ensure backend/app is in sys.path so 'caem', 'app' subpackages are importable
_APP_DIR = _os.path.dirname(_os.path.abspath(__file__))
_BACKEND_DIR = _os.path.dirname(_APP_DIR)
for _p in [_APP_DIR, _BACKEND_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
del _APP_DIR, _BACKEND_DIR, _p

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
import uvicorn.middleware.proxy_headers
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.tracing import init_tracing
from app.db.session import close_db, init_db
from app.db.neo4j_session import close_neo4j, init_neo4j
from app.db.redis_session import close_redis, init_redis

logger = structlog.get_logger(__name__)
settings = get_settings()


# ─── Lifespan Context (startup / shutdown) ────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application lifespan: initialize all data stores on startup,
    gracefully close connections on shutdown.
    """
    configure_logging(level=settings.ORBITIQ_LOG_LEVEL)
    init_tracing(app=app)   # OpenTelemetry — no-op if SDK unavailable
    logger.info(
        "orbitiq_x_starting",
        version=settings.ORBITIQ_VERSION,
        environment=settings.ORBITIQ_ENV,
    )

    # Initialize data stores
    await init_db()
    await init_redis()
    await init_neo4j()

    # Start catalog sync scheduler (after DB + Redis ready)
    from app.services.catalog_scheduler import init_scheduler
    await init_scheduler()

    logger.info("orbitiq_x_ready", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT)

    yield  # Application runs here

    # Graceful shutdown
    logger.info("orbitiq_x_shutting_down")
    from app.services.catalog_scheduler import shutdown_scheduler
    await shutdown_scheduler()
    await close_db()
    await close_redis()
    await close_neo4j()
    logger.info("orbitiq_x_shutdown_complete")


# ─── Application Factory ──────────────────────────────────────────────────────

def create_application() -> FastAPI:
    """
    Construct and configure the FastAPI application.

    Returns
    -------
    FastAPI
        Fully configured application instance.
    """
    app = FastAPI(
        title="ORBITIQ-X API",
        description=(
            "Aerospace Foundation Model for Space Intelligence — "
            "SSA, Orbital Mechanics, Knowledge Graphs, RAG, and Multi-Agent Reasoning."
        ),
        version=settings.ORBITIQ_VERSION,
        openapi_url=f"{settings.BACKEND_API_PREFIX}/openapi.json",
        docs_url=f"{settings.BACKEND_API_PREFIX}/docs",
        redoc_url=f"{settings.BACKEND_API_PREFIX}/redoc",
        # default_response_class uses JSONResponse (ORJSONResponse deprecated)
        lifespan=lifespan,
        contact={
            "name": "Mahin Nandipa",
            "url": "https://mahin-nandipa.netlify.app",
            "email": "mahin@orbitiq-x.dev",
        },
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    )

    _register_middleware(app)
    _register_exception_handlers(app)
    _register_routers(app)
    _register_prometheus(app)

    return app


def _register_middleware(app: FastAPI) -> None:
    """Register all middleware in correct order (outer-to-inner)."""

    # ProxyHeaders — trust Railway's load balancer X-Forwarded-* headers
    app.add_middleware(
        uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware,
        trusted_hosts="*",
    )
    # TrustedHostMiddleware — allow wildcard so Railway internal health checks pass
    trusted = list(settings.TRUSTED_HOSTS) + ["*"]
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=trusted,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    )

    # GZip compression for large orbital datasets
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Security headers — applied to every response
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # XSS protection for older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permissions policy — restrict powerful browser APIs
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        # HSTS — only in production over HTTPS
        if settings.ORBITIQ_ENV == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        # CSP — restrictive policy for API; frontend has its own CSP
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "frame-ancestors 'none'"
        )
        return response

    # Request timing & request-ID injection
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next) -> Response:
        import uuid
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        with structlog.contextvars.bound_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        ):
            response: Response = await call_next(request)
            process_ms = round((time.perf_counter() - start_time) * 1000, 2)

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = str(process_ms)

            logger.info(
                "http_request",
                status_code=response.status_code,
                process_ms=process_ms,
            )
            return response


def _register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from fastapi.exceptions import RequestValidationError
    import traceback

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        tb = traceback.format_exc()
        logger.error("unhandled_exception path=%s error=%s trace=%s",
                     request.url.path, str(exc), tb[:500])
        return JSONResponse(
            status_code=500,
            content={"status": "error", "code": 500,
                     "message": str(exc)[:200], "type": type(exc).__name__},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"status": "error", "code": 422, "detail": exc.errors()},
        )


def _register_routers(app: FastAPI) -> None:
    """Mount versioned API routers."""

    # Health check (unauthenticated, no prefix)
    @app.get("/health", tags=["System"], summary="Platform liveness probe")
    async def health_check() -> dict:
        """
        Liveness probe — returns 200 immediately if the process is alive.
        Used by Railway healthcheck, Docker health checks, and monitoring.
        No authentication required. No database calls.
        """
        import time
        return {
            "status": "ok",
            "version": settings.ORBITIQ_VERSION,
            "environment": settings.ORBITIQ_ENV,
            "platform": "ORBITIQ-X",
            "timestamp": time.time(),
        }

    @app.get("/ready", tags=["System"], summary="Platform readiness probe")
    async def readiness_check() -> dict:
        """
        Readiness probe — checks that DB is reachable.
        Redis unavailability is non-fatal (degraded, not down).
        Returns 200 if ready to serve traffic, 503 only if DB is down.
        """
        from fastapi.responses import JSONResponse
        from app.db.session import get_engine
        from app.db.redis_session import get_redis_status
        issues = []
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        except Exception as exc:
            issues.append(f"database: {exc}")
        if issues:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "issues": issues}
            )
        redis_status = get_redis_status()
        return {
            "status":   "ready",
            "platform": "ORBITIQ-X",
            "database": "healthy",
            "redis":    redis_status["status"],
            "redis_details": redis_status if not redis_status["connected"] else None,
        }

    @app.get("/", tags=["System"], include_in_schema=False)
    async def root() -> dict:
        return {"message": "ORBITIQ-X API — Navigate to /api/v1/docs for documentation."}

    # Main versioned API
    app.include_router(api_v1_router, prefix=settings.BACKEND_API_PREFIX)

    # ─── API v2 — CAEM Knowledge Layer ────────────────────────────────────────
    # Mounts the same CAEM routers under /api/v2 prefix.
    # Vercel rewrites /api/v2/* → Railway /api/v2/* so this must be present.
    from fastapi import APIRouter as _APIRouter
    _api_v2 = _APIRouter()

    from app.api.v1.endpoints.entities import router as _entities_r
    from app.api.v1.endpoints.relationships import router as _relationships_r
    from app.api.v1.endpoints.provenance import router as _provenance_r
    from app.api.v1.endpoints.ingestion import router as _ingestion_r
    from app.api.v1.endpoints.knowledge_intelligence import router as _intelligence_r
    from app.api.v1.endpoints.digital_twin_control import router as _dt_control_r

    _api_v2.include_router(_entities_r,      tags=["CAEM v2 — Entities"])
    _api_v2.include_router(_relationships_r, tags=["CAEM v2 — Relationships"])
    _api_v2.include_router(_provenance_r,    tags=["CAEM v2 — Provenance"])
    _api_v2.include_router(_ingestion_r,     tags=["CAEM v2 — Ingestion"])
    _api_v2.include_router(_intelligence_r,  tags=["CAEM v2 — Intelligence"])
    _api_v2.include_router(_dt_control_r,    tags=["CAEM v2 — Digital Twin"])

    app.include_router(_api_v2, prefix="/api/v2")


def _register_prometheus(app: FastAPI) -> None:
    """Configure Prometheus metrics instrumentation."""
    Instrumentator(
        should_group_status_codes=False,
        should_respect_env_var=True,
        env_var_name="ENABLE_METRICS",
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", tags=["System"])


# ─── Application Instance ─────────────────────────────────────────────────────
app = create_application()
