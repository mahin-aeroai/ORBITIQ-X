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
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging
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
    logger.info(
        "orbitiq_x_starting",
        version=settings.ORBITIQ_VERSION,
        environment=settings.ORBITIQ_ENV,
    )

    # Initialize data stores
    await init_db()
    await init_redis()
    await init_neo4j()

    logger.info("orbitiq_x_ready", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT)

    yield  # Application runs here

    # Graceful shutdown
    logger.info("orbitiq_x_shutting_down")
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
        default_response_class=ORJSONResponse,
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

    # Trusted hosts (outermost — blocks spoofed Host headers)
    if settings.ORBITIQ_ENV == "production":
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.TRUSTED_HOSTS,
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
    @app.get("/health", tags=["System"], summary="Platform health check")
    async def health_check() -> dict:
        """
        Returns platform health status.
        Used by Docker health checks, Kubernetes liveness probes,
        and the deployment/scripts/health-check.sh script.
        """
        return {
            "status": "operational",
            "version": settings.ORBITIQ_VERSION,
            "environment": settings.ORBITIQ_ENV,
            "platform": "ORBITIQ-X",
        }

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
