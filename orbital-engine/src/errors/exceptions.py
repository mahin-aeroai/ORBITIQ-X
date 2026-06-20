"""
ORBITIQ-X Orbital Engine
Error Handling Strategy

Exception Hierarchy:
    OrbitalEngineError (base)
    ├── TLEError
    │   ├── TLEParseError           — malformed TLE format / bad checksum
    │   ├── TLEExpiredError         — TLE too old for reliable propagation
    │   └── TLENotFoundError        — object not in catalog
    ├── PropagationError
    │   ├── PropagationDivergence   — SGP4 numerical failure
    │   ├── PropagationEpochError   — epoch outside TLE validity window
    │   └── DecayedObjectError      — object below re-entry altitude
    ├── ConjunctionError
    │   ├── InsufficientCovarianceError
    │   └── TCANotFoundError
    ├── CoordinateError             — invalid frame / coordinate range
    ├── CatalogError
    │   └── CatalogSyncError        — upstream data source failure
    └── RateLimitError              — API rate limiting

Strategy:
    1. All exceptions carry structured metadata (error_code, context)
    2. FastAPI exception handlers map to HTTP status codes
    3. SGP4 errors are caught and isolated per-object in batch operations
    4. Upstream failures trigger Redis-cached fallback (stale TLE tolerance)
    5. Structured logging on every error with request_id correlation
"""

from __future__ import annotations

import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ── Exception Hierarchy ───────────────────────────────────────

class OrbitalEngineError(Exception):
    """Base exception for all orbital engine errors."""
    error_code: str = "ORBITAL_ENGINE_ERROR"
    http_status: int = 500
    retryable: bool = False

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "retryable": self.retryable,
        }


# TLE errors
class TLEError(OrbitalEngineError):
    error_code = "TLE_ERROR"
    http_status = 422

class TLEParseError(TLEError):
    error_code = "TLE_PARSE_ERROR"

class TLEExpiredError(TLEError):
    error_code = "TLE_EXPIRED"
    http_status = 409

    def __init__(self, norad_id: int, age_days: float, max_age_days: float = 7.0):
        super().__init__(
            f"TLE for NORAD {norad_id} is {age_days:.1f} days old (max: {max_age_days})",
            {"norad_id": norad_id, "age_days": age_days, "max_age_days": max_age_days},
        )

class TLENotFoundError(TLEError):
    error_code = "TLE_NOT_FOUND"
    http_status = 404

    def __init__(self, norad_id: int):
        super().__init__(
            f"No TLE found for NORAD ID {norad_id}",
            {"norad_id": norad_id},
        )


# Propagation errors
class PropagationError(OrbitalEngineError):
    error_code = "PROPAGATION_ERROR"
    http_status = 422

class PropagationDivergence(PropagationError):
    error_code = "PROPAGATION_DIVERGENCE"

    def __init__(self, norad_id: int, epoch: datetime, sgp4_error_code: int = 0):
        super().__init__(
            f"SGP4 propagation diverged for NORAD {norad_id} at {epoch.isoformat()}",
            {"norad_id": norad_id, "epoch": epoch.isoformat(), "sgp4_error_code": sgp4_error_code},
        )

class PropagationEpochError(PropagationError):
    error_code = "PROPAGATION_EPOCH_OUT_OF_RANGE"

    def __init__(self, norad_id: int, requested_epoch: datetime, tle_epoch: datetime):
        days_diff = abs((requested_epoch - tle_epoch).total_seconds() / 86400)
        super().__init__(
            f"Epoch {requested_epoch.isoformat()} is {days_diff:.1f} days from TLE epoch for NORAD {norad_id}",
            {
                "norad_id": norad_id,
                "requested_epoch": requested_epoch.isoformat(),
                "tle_epoch": tle_epoch.isoformat(),
                "days_from_epoch": days_diff,
            },
        )

class DecayedObjectError(PropagationError):
    error_code = "OBJECT_DECAYED"
    http_status = 410

    def __init__(self, norad_id: int):
        super().__init__(
            f"Object NORAD {norad_id} has re-entered or is below minimum propagation altitude",
            {"norad_id": norad_id},
        )


# Conjunction errors
class ConjunctionError(OrbitalEngineError):
    error_code = "CONJUNCTION_ERROR"
    http_status = 422

class InsufficientCovarianceError(ConjunctionError):
    error_code = "INSUFFICIENT_COVARIANCE"

class TCANotFoundError(ConjunctionError):
    error_code = "TCA_NOT_FOUND"

    def __init__(self, norad_1: int, norad_2: int, window_hours: int):
        super().__init__(
            f"No TCA found for {norad_1}/{norad_2} within {window_hours}h window",
            {"norad_1": norad_1, "norad_2": norad_2, "window_hours": window_hours},
        )


# Coordinate errors
class CoordinateError(OrbitalEngineError):
    error_code = "COORDINATE_ERROR"
    http_status = 422

    def __init__(self, message: str, frame: str | None = None):
        super().__init__(message, {"frame": frame})


# Catalog errors
class CatalogError(OrbitalEngineError):
    error_code = "CATALOG_ERROR"
    http_status = 503

class CatalogSyncError(CatalogError):
    error_code = "CATALOG_SYNC_FAILED"
    retryable = True

    def __init__(self, source: str, reason: str):
        super().__init__(
            f"Failed to sync catalog from {source}: {reason}",
            {"source": source, "reason": reason},
        )


# Rate limiting
class RateLimitError(OrbitalEngineError):
    error_code = "RATE_LIMIT_EXCEEDED"
    http_status = 429
    retryable = True

    def __init__(self, limit: int, window_seconds: int):
        super().__init__(
            f"Rate limit exceeded: {limit} requests per {window_seconds}s",
            {"limit": limit, "window_seconds": window_seconds},
        )


# ── FastAPI Exception Handlers ────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI application."""

    @app.exception_handler(OrbitalEngineError)
    async def orbital_engine_error_handler(
        request: Request, exc: OrbitalEngineError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        error_data = exc.to_dict()
        error_data["request_id"] = request_id

        logger.error(
            f"OrbitalEngineError: {exc.error_code}",
            extra={
                "request_id": request_id,
                "error_code": exc.error_code,
                "context": exc.context,
                "path": request.url.path,
            }
        )

        return JSONResponse(
            status_code=exc.http_status,
            content=error_data,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error_code": "VALIDATION_ERROR", "message": str(exc)},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.critical(
            f"Unhandled exception: {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            extra={"request_id": request_id, "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "request_id": request_id,
            },
        )


# ── Batch Operation Error Handling ────────────────────────────

class BatchPropagationResult:
    """
    Container for batch propagation results with per-object error isolation.

    Design principle: one failed object MUST NOT fail the entire batch.
    Each object gets its own try/except; errors are collected and returned
    alongside successful results.
    """

    def __init__(self):
        self.successes: list[dict] = []
        self.errors: list[dict] = []

    def add_success(self, norad_id: int, result: Any) -> None:
        self.successes.append({"norad_id": norad_id, "result": result})

    def add_error(self, norad_id: int, error: Exception) -> None:
        if isinstance(error, OrbitalEngineError):
            self.errors.append({
                "norad_id": norad_id,
                **error.to_dict(),
            })
        else:
            self.errors.append({
                "norad_id": norad_id,
                "error_code": "PROPAGATION_ERROR",
                "message": str(error),
            })

    @property
    def success_rate(self) -> float:
        total = len(self.successes) + len(self.errors)
        return len(self.successes) / total if total > 0 else 0.0

    def to_response(self) -> dict:
        return {
            "total": len(self.successes) + len(self.errors),
            "successful": len(self.successes),
            "failed": len(self.errors),
            "success_rate": round(self.success_rate, 4),
            "results": self.successes,
            "errors": self.errors,
        }


# ── Retry Decorator ───────────────────────────────────────────

def with_retry(
    max_attempts: int = 3,
    backoff_seconds: float = 2.0,
    retryable_exceptions: tuple = (CatalogSyncError, RateLimitError),
):
    """
    Decorator for retrying retryable operations with exponential backoff.

    Usage:
        @with_retry(max_attempts=3)
        async def fetch_catalog():
            ...
    """
    import asyncio
    import functools

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        wait = backoff_seconds * (2 ** (attempt - 1))
                        logger.warning(
                            f"{func.__name__} attempt {attempt} failed ({exc}), "
                            f"retrying in {wait:.1f}s"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts"
                        )
            raise last_exc
        return wrapper
    return decorator
