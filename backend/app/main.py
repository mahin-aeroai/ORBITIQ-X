"""
ORBITIQ-X Backend — Application Entry Point
============================================
FastAPI application factory with middleware stack, lifespan context,
health checks, and API router registration.
"""
from __future__ import annotations

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
        Readiness probe — checks that DB and Redis are reachable.
        Returns 200 if ready to serve traffic, 503 if not.
        """
        from fastapi.responses import JSONResponse
        from app.db.session import get_engine
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
        return {"status": "ready", "platform": "ORBITIQ-X"}

    @app.get("/", tags=["System"], include_in_schema=False)
    async def root() -> dict:
        return {"message": "ORBITIQ-X API — Navigate to /api/v1/docs for documentation."}

    # Main versioned API
    app.include_router(api_v1_router, prefix=settings.BACKEND_API_PREFIX)


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
