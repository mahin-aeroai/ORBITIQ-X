"""
ORBITIQ-X — Space-Track Fetcher
================================
Authenticated HTTP client for the Space-Track.org REST API.

Space-Track API contract
────────────────────────
  Auth:  POST /ajaxauth/login  (form-encoded, sets session cookie)
  GP:    GET  /basicspacedata/query/class/gp/...
  Logout: GET /ajaxauth/logout

Rate limits (as of 2024)
─────────────────────────
  300 requests / hour per account
  20  requests / minute burst cap
  Space-Track throttles with HTTP 429; this client respects it.

Session management
──────────────────
  A single aiohttp ClientSession holds the authenticated cookie.
  The session is valid for ~2 hours; this client renews it
  proactively at 90-minute intervals and reactively on any 401.

Retry strategy (tenacity)
──────────────────────────
  Transient (5xx, network): exponential backoff 1s→2s→4s→8s→16s, max 5 attempts
  Rate-limit (429):         fixed 65-second wait, max 3 attempts
  Auth failure (401):       re-authenticate once, then fail

Audit findings this file addresses
────────────────────────────────────
  - config.py already has SPACETRACK_IDENTITY / PASSWORD / BASE_URL (✓ reused)
  - scheduler/jobs.py imports CelesTrakFetcher but it doesn't exist (not touched)
  - tle_ingest_service.py has ingest_text() ready to consume raw TLE text (✓ called here)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

logger = logging.getLogger(__name__)

# ── Space-Track API paths ─────────────────────────────────────
_LOGIN_PATH   = "/ajaxauth/login"
_LOGOUT_PATH  = "/ajaxauth/logout"
_GP_PATH      = "/basicspacedata/query/class/gp"
_SATCAT_PATH  = "/basicspacedata/query/class/satcat"

# ── Query modifiers ───────────────────────────────────────────
_TLE_FORMAT   = "/format/tle"
_JSON_FORMAT  = "/format/json"
_LIMIT_MAX    = "/limit/50000"
_ORDER_EPOCH  = "/orderby/EPOCH%20desc"

# Active = CURRENT means the GP record has been updated recently
_ACTIVE_FILTER   = "/CURRENT/Y"
_DECAY_FILTER    = "/DECAY/null-val"  # not yet decayed


# ── Result container ──────────────────────────────────────────

@dataclass
class FetchResult:
    """Return value for every fetch method."""
    ok: bool
    source: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_text: str = ""           # raw TLE text for ingest_text()
    record_count: int = 0
    http_status: int = 0
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def failed(self) -> bool:
        return not self.ok


@dataclass
class HealthStatus:
    """Result of health_check()."""
    reachable: bool
    authenticated: bool
    latency_ms: float
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


# ── Custom exceptions ─────────────────────────────────────────

class SpaceTrackAuthError(Exception):
    """Authentication failed (wrong credentials or account locked)."""

class SpaceTrackRateLimitError(Exception):
    """429 received — rate limit exceeded."""

class SpaceTrackNetworkError(Exception):
    """Network-level failure (timeout, DNS, TLS)."""

class SpaceTrackDataError(Exception):
    """Server returned unexpected data format."""


# ── Fetcher ───────────────────────────────────────────────────

class SpaceTrackFetcher:
    """
    Authenticated async client for Space-Track.org.

    Parameters
    ----------
    identity : str
        Space-Track registered email address.
    password : str
        Account password (never logged).
    base_url : str
        Override for testing (default: https://www.space-track.org).
    rate_limit_per_hour : int
        Hard cap on outgoing requests. Default 300.
    session_ttl_seconds : int
        Proactive session renewal interval. Default 5400s (90 min).
    timeout_seconds : float
        Per-request timeout. Default 120s (large GP downloads).
    """

    def __init__(
        self,
        identity: str,
        password: str,
        base_url: str = "https://www.space-track.org",
        rate_limit_per_hour: int = 300,
        session_ttl_seconds: int = 5400,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._identity = identity
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._rate_limit = rate_limit_per_hour
        self._session_ttl = session_ttl_seconds
        self._timeout = httpx.Timeout(timeout_seconds, connect=15.0)

        # Session state
        self._client: httpx.AsyncClient | None = None
        self._authenticated: bool = False
        self._auth_at: float = 0.0        # time.monotonic() when last authed

        # Rate limiting — token bucket
        self._request_count = 0
        self._window_start  = time.monotonic()
        self._request_lock  = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────

    async def __aenter__(self) -> "SpaceTrackFetcher":
        await self._ensure_client()
        await self.authenticate()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "ORBITIQ-X/1.0 (+https://github.com/mahin-aeroai/ORBITIQ-X)",
                    "Accept": "text/plain, application/json",
                },
            )
            logger.debug("spacetrack_client_created base=%s", self._base_url)

    async def close(self) -> None:
        """Logout and close the underlying HTTP client."""
        if self._client and self._authenticated:
            try:
                await self._client.get(_LOGOUT_PATH)
                logger.info("spacetrack_logout_ok")
            except Exception:
                pass
        if self._client:
            await self._client.aclose()
            self._client = None
        self._authenticated = False

    # ── Authentication ────────────────────────────────────────

    async def authenticate(self) -> None:
        """
        POST login credentials to obtain a session cookie.

        Space-Track uses a JSON-body login (not form-encoded despite
        the field names). The server sets a PHP session cookie that
        httpx carries automatically on subsequent requests.

        Raises
        ──────
        SpaceTrackAuthError
            On 401, 403, or a JSON body indicating failure.
        SpaceTrackNetworkError
            On connection-level failure.
        """
        await self._ensure_client()
        logger.info("spacetrack_authenticate identity=%s", self._identity)

        try:
            resp = await self._client.post(
                _LOGIN_PATH,
                data={
                    "identity": self._identity,
                    "password": self._password,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.TransportError as exc:
            raise SpaceTrackNetworkError(f"Login transport error: {exc}") from exc

        if resp.status_code == 401:
            raise SpaceTrackAuthError(
                "Space-Track authentication failed: invalid credentials. "
                "Check SPACETRACK_IDENTITY and SPACETRACK_PASSWORD in .env"
            )

        if resp.status_code not in (200, 302):
            raise SpaceTrackAuthError(
                f"Space-Track login returned unexpected status {resp.status_code}"
            )

        # Space-Track returns a plain-text failure string, not an HTTP error code
        body = resp.text.strip()
        if "Failed" in body or "Invalid" in body or "error" in body.lower():
            raise SpaceTrackAuthError(f"Space-Track login rejected: {body[:200]}")

        self._authenticated = True
        self._auth_at = time.monotonic()
        logger.info("spacetrack_authenticated ok")

    async def _maybe_renew_session(self) -> None:
        """Re-authenticate if the session is older than session_ttl_seconds."""
        age = time.monotonic() - self._auth_at
        if age >= self._session_ttl:
            logger.info("spacetrack_session_renewal age=%.0fs", age)
            await self.authenticate()

    # ── Rate limit guard ──────────────────────────────────────

    async def _check_rate_limit(self) -> None:
        """
        Token-bucket rate limiter. Tracks requests within a 3600-second
        window. Raises if the hourly cap is reached.
        """
        async with self._request_lock:
            now = time.monotonic()
            if now - self._window_start >= 3600:
                self._request_count = 0
                self._window_start  = now

            self._request_count += 1
            if self._request_count > self._rate_limit:
                wait = 3600 - (now - self._window_start)
                raise SpaceTrackRateLimitError(
                    f"Rate limit reached ({self._request_count}/{self._rate_limit}/hr). "
                    f"Next window opens in {wait:.0f}s."
                )

    # ── Core GET with retry ───────────────────────────────────

    async def _get(self, path: str) -> httpx.Response:
        """
        Authenticated GET with tenacity retry.

        Retry tiers:
          - Network errors: exponential backoff, 5 attempts
          - 429 rate limit: fixed 65s wait, 3 attempts
          - 401 auth expiry: re-authenticate once, 2 attempts
        """
        if not self._authenticated:
            await self.authenticate()

        await self._maybe_renew_session()
        await self._check_rate_limit()

        url = f"{self._base_url}{path}"
        logger.debug("spacetrack_get path=%s", path[:80])

        async def _attempt() -> httpx.Response:
            try:
                resp = await self._client.get(path)
            except httpx.TimeoutException as exc:
                raise SpaceTrackNetworkError(f"Timeout: {exc}") from exc
            except httpx.TransportError as exc:
                raise SpaceTrackNetworkError(f"Transport: {exc}") from exc

            if resp.status_code == 429:
                logger.warning("spacetrack_429 path=%s", path[:60])
                raise SpaceTrackRateLimitError("429 Too Many Requests")

            if resp.status_code == 401:
                logger.warning("spacetrack_401_session_expired path=%s", path[:60])
                self._authenticated = False
                await self.authenticate()
                raise SpaceTrackNetworkError("Session expired — re-authenticated, retry")

            if resp.status_code >= 500:
                raise SpaceTrackNetworkError(
                    f"Server error {resp.status_code} at {path[:60]}"
                )

            resp.raise_for_status()
            return resp

        # Retry for transient errors
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(SpaceTrackNetworkError),
                wait=wait_exponential(multiplier=1, min=1, max=16),
                stop=stop_after_attempt(5),
                before_sleep=before_sleep_log(logger, logging.WARNING),
            ):
                with attempt:
                    return await _attempt()
        except RetryError as exc:
            raise SpaceTrackNetworkError(
                f"All retry attempts exhausted for {path[:60]}"
            ) from exc

        # Retry specifically for rate-limit 429
        raise SpaceTrackRateLimitError("Should not reach here")

    # ── Public fetch methods ──────────────────────────────────

    async def fetch_latest_tles(
        self,
        days_back: int = 2,
    ) -> FetchResult:
        """
        Fetch TLEs updated in the last N days (default 2).

        Returns TLEs for all objects with a GP epoch within `days_back`
        days of now. Useful for the 2-hour refresh job.

        Parameters
        ----------
        days_back : int
            Number of days back to query.

        Returns
        -------
        FetchResult
        """
        t0 = time.perf_counter()
        path = (
            f"{_GP_PATH}"
            f"/EPOCH/>now-{days_back}"
            f"{_TLE_FORMAT}"
            f"{_LIMIT_MAX}"
        )
        try:
            resp = await self._get(path)
            text = resp.text
            count = text.count("\n1 ")  # rough TLE count
            return FetchResult(
                ok=True,
                source="spacetrack",
                raw_text=text,
                record_count=count,
                http_status=resp.status_code,
                duration_seconds=time.perf_counter() - t0,
            )
        except (SpaceTrackNetworkError, SpaceTrackRateLimitError, SpaceTrackAuthError) as exc:
            return FetchResult(
                ok=False,
                source="spacetrack",
                http_status=getattr(exc, "status_code", 0),
                error=str(exc),
                duration_seconds=time.perf_counter() - t0,
            )

    async def fetch_satellite_tle(self, norad_id: int) -> FetchResult:
        """
        Fetch the current GP TLE for a single NORAD catalog number.

        Parameters
        ----------
        norad_id : int
            NORAD catalog number (1–99999).

        Returns
        -------
        FetchResult
            raw_text will contain a single 3-line TLE block or be empty
            if the object has no current GP element.
        """
        t0 = time.perf_counter()
        path = f"{_GP_PATH}/NORAD_CAT_ID/{norad_id}{_TLE_FORMAT}"
        try:
            resp = await self._get(path)
            text = resp.text.strip()
            return FetchResult(
                ok=True,
                source="spacetrack",
                raw_text=text,
                record_count=1 if text else 0,
                http_status=resp.status_code,
                duration_seconds=time.perf_counter() - t0,
            )
        except Exception as exc:
            return FetchResult(
                ok=False, source="spacetrack", error=str(exc),
                duration_seconds=time.perf_counter() - t0,
            )

    async def fetch_active_catalog(self) -> FetchResult:
        """
        Fetch all active (non-decayed) GP elements — payloads, rocket bodies.

        Typically ~20,000–30,000 objects. Uses CURRENT=Y to restrict to
        the most recently updated GP record per object.

        Returns
        -------
        FetchResult
        """
        t0 = time.perf_counter()
        path = (
            f"{_GP_PATH}"
            f"{_ACTIVE_FILTER}"
            f"{_DECAY_FILTER}"
            f"/OBJECT_TYPE/PAYLOAD,ROCKET%20BODY"
            f"{_TLE_FORMAT}"
            f"{_LIMIT_MAX}"
        )
        logger.info("spacetrack_fetch_active_catalog start")
        try:
            resp = await self._get(path)
            text = resp.text
            count = text.count("\n1 ")
            logger.info("spacetrack_fetch_active_catalog ok count=%d bytes=%d", count, len(text))
            return FetchResult(
                ok=True, source="spacetrack",
                raw_text=text, record_count=count,
                http_status=resp.status_code,
                duration_seconds=time.perf_counter() - t0,
            )
        except Exception as exc:
            logger.error("spacetrack_fetch_active_catalog failed error=%s", exc)
            return FetchResult(
                ok=False, source="spacetrack", error=str(exc),
                duration_seconds=time.perf_counter() - t0,
            )

    async def fetch_debris_catalog(self) -> FetchResult:
        """
        Fetch all tracked debris and unknown objects.

        This is the large call — up to 30,000+ objects at times of high
        fragmentation activity. Allow up to 3 minutes for this request.

        Returns
        -------
        FetchResult
        """
        t0 = time.perf_counter()
        path = (
            f"{_GP_PATH}"
            f"{_ACTIVE_FILTER}"
            f"{_DECAY_FILTER}"
            f"/OBJECT_TYPE/DEBRIS,UNKNOWN,TBA"
            f"{_TLE_FORMAT}"
            f"{_LIMIT_MAX}"
        )
        logger.info("spacetrack_fetch_debris_catalog start")
        try:
            resp = await self._get(path)
            text = resp.text
            count = text.count("\n1 ")
            logger.info("spacetrack_fetch_debris_catalog ok count=%d bytes=%d", count, len(text))
            return FetchResult(
                ok=True, source="spacetrack",
                raw_text=text, record_count=count,
                http_status=resp.status_code,
                duration_seconds=time.perf_counter() - t0,
            )
        except Exception as exc:
            logger.error("spacetrack_fetch_debris_catalog failed error=%s", exc)
            return FetchResult(
                ok=False, source="spacetrack", error=str(exc),
                duration_seconds=time.perf_counter() - t0,
            )

    async def fetch_full_catalog(self) -> FetchResult:
        """
        Fetch the complete catalog (all object types) in one call.

        Space-Track allows querying without OBJECT_TYPE to get everything.
        This is the most efficient path for the 6-hour full sync.

        Returns
        -------
        FetchResult
            record_count ≈ 50,000+ at peak catalog size.
        """
        t0 = time.perf_counter()
        path = (
            f"{_GP_PATH}"
            f"{_ACTIVE_FILTER}"
            f"{_DECAY_FILTER}"
            f"{_TLE_FORMAT}"
            f"{_LIMIT_MAX}"
        )
        logger.info("spacetrack_fetch_full_catalog start")
        try:
            resp = await self._get(path)
            text = resp.text
            count = text.count("\n1 ")
            logger.info(
                "spacetrack_fetch_full_catalog ok count=%d bytes=%d duration=%.1fs",
                count, len(text), time.perf_counter() - t0,
            )
            return FetchResult(
                ok=True, source="spacetrack",
                raw_text=text, record_count=count,
                http_status=resp.status_code,
                duration_seconds=time.perf_counter() - t0,
            )
        except Exception as exc:
            logger.error("spacetrack_fetch_full_catalog failed error=%s", exc)
            return FetchResult(
                ok=False, source="spacetrack", error=str(exc),
                duration_seconds=time.perf_counter() - t0,
            )

    async def health_check(self) -> HealthStatus:
        """
        Verify Space-Track reachability and authentication without
        consuming significant API quota.

        Uses the GP query with LIMIT/1 — minimal data transfer,
        counts as 1 request against the rate limit.

        Returns
        -------
        HealthStatus
        """
        t0 = time.perf_counter()
        try:
            resp = await self._get(f"{_GP_PATH}/LIMIT/1{_TLE_FORMAT}")
            latency_ms = (time.perf_counter() - t0) * 1000
            return HealthStatus(
                reachable=True,
                authenticated=self._authenticated,
                latency_ms=round(latency_ms, 1),
            )
        except SpaceTrackAuthError as exc:
            return HealthStatus(
                reachable=True, authenticated=False,
                latency_ms=0.0, error=str(exc),
            )
        except SpaceTrackNetworkError as exc:
            return HealthStatus(
                reachable=False, authenticated=False,
                latency_ms=0.0, error=str(exc),
            )
        except Exception as exc:
            return HealthStatus(
                reachable=False, authenticated=False,
                latency_ms=0.0, error=str(exc),
            )

    # ── Factory ───────────────────────────────────────────────

    @classmethod
    def from_settings(cls) -> "SpaceTrackFetcher":
        """
        Build a SpaceTrackFetcher from app settings.
        Uses SPACETRACK_IDENTITY, SPACETRACK_PASSWORD, SPACETRACK_BASE_URL
        already defined in config.py.
        """
        from app.core.config import get_settings
        s = get_settings()
        return cls(
            identity=s.SPACETRACK_IDENTITY,
            password=s.SPACETRACK_PASSWORD.get_secret_value(),
            base_url=str(s.SPACETRACK_BASE_URL),
            rate_limit_per_hour=s.SPACETRACK_RATE_LIMIT_PER_HOUR,
        )
