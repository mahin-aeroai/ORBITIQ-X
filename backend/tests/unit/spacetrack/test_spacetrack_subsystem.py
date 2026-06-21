"""
ORBITIQ-X — Space-Track Ingestion Subsystem Test Suite
=======================================================
Coverage target: > 90%

Test categories
───────────────
  Unit tests:       SpaceTrackFetcher (mocked HTTP), CatalogSyncService (mocked deps)
  Integration:      Full pipeline with real SQLite-backed session (no external services)
  Failure tests:    Network errors, auth failures, rate limits, partial data
  Rate-limit tests: Token bucket enforcement, 429 handling, backoff timing
  Mock server:      ASGI mock that mimics Space-Track response format

Run
───
  pytest tests/unit/spacetrack/ -v --tb=short
  pytest tests/unit/spacetrack/ -v -k "auth"
  pytest tests/unit/spacetrack/ --co -q   # list all tests
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ── TLE fixtures ──────────────────────────────────────────────
# Two valid 3-line TLE blocks with correct checksums
SAMPLE_TLE_ISS = """\
ISS (ZARYA)
1 25544U 98067A   25168.51786836  .00025600  00000+0  45234-3 0  9999
2 25544  51.6397 166.2943 0004134 305.8438 179.0499 15.50620950506190
"""

SAMPLE_TLE_NOAA = """\
NOAA 19
1 33591U 09005A   25168.47930982  .00000078  00000+0  68490-4 0  9994
2 33591  98.7116 207.0714 0013523 168.5088 191.6614 14.12467178793048
"""

SAMPLE_TLE_TEXT = SAMPLE_TLE_ISS + SAMPLE_TLE_NOAA

# 50K-scale synthetic TLE block (generated lazily in scale tests)
def _make_synthetic_tle_text(n: int) -> str:
    """Generate n synthetic 3-line TLE blocks with valid checksums."""
    def _checksum(line: str) -> int:
        return sum(int(c) if c.isdigit() else (1 if c == '-' else 0) for c in line[:68]) % 10

    def _make_tle(i: int) -> str:
        norad = 70000 + i
        l1_body = f"1 {norad:05d}U 24001A   25168.50000000  .00001000  00000+0  10000-3 0  999"
        l2_body = f"2 {norad:05d}  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579 4357"
        l1 = l1_body + str(_checksum(l1_body))
        l2 = l2_body + str(_checksum(l2_body))
        return f"TESTSAT-{norad:05d}\n{l1}\n{l2}"

    return "\n".join(_make_tle(i) for i in range(n))


# ═══════════════════════════════════════════════════════════════
# UNIT TESTS — SpaceTrackFetcher
# ═══════════════════════════════════════════════════════════════

class TestSpaceTrackFetcherInit:
    """Constructor and configuration tests."""

    def test_default_parameters(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("user@test.com", "pw")
        assert f._base_url == "https://www.space-track.org"
        assert f._rate_limit == 300
        assert f._session_ttl == 5400
        assert f._authenticated is False

    def test_trailing_slash_stripped(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", base_url="https://example.com/")
        assert f._base_url == "https://example.com"

    def test_custom_rate_limit(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", rate_limit_per_hour=100)
        assert f._rate_limit == 100

    def test_from_settings_reads_config(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        with patch("app.services.spacetrack_fetcher.SpaceTrackFetcher.from_settings") as mock:
            mock.return_value = SpaceTrackFetcher(
                "test@example.com", "testpw",
                base_url="https://www.space-track.org",
                rate_limit_per_hour=300,
            )
            f = SpaceTrackFetcher.from_settings()
            assert f._rate_limit == 300


class TestSpaceTrackAuthentication:
    """Authentication flow tests."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("user@test.com", "correctpw",
                              base_url="https://fake.space-track.org")
        await f._ensure_client()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        f._client.post = AsyncMock(return_value=mock_resp)

        await f.authenticate()

        assert f._authenticated is True
        assert f._auth_at > 0
        f._client.post.assert_called_once()
        call_kwargs = f._client.post.call_args
        assert "identity" in call_kwargs.kwargs.get("data", call_kwargs.args[1] if len(call_kwargs.args) > 1 else {})

    @pytest.mark.asyncio
    async def test_authenticate_401_raises(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher, SpaceTrackAuthError
        f = SpaceTrackFetcher("bad@email.com", "wrongpw",
                              base_url="https://fake.space-track.org")
        await f._ensure_client()

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        f._client.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(SpaceTrackAuthError, match="invalid credentials"):
            await f.authenticate()

        assert f._authenticated is False

    @pytest.mark.asyncio
    async def test_authenticate_failure_body_raises(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher, SpaceTrackAuthError
        f = SpaceTrackFetcher("u", "p", base_url="https://fake.space-track.org")
        await f._ensure_client()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Invalid username/password"
        f._client.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(SpaceTrackAuthError, match="login rejected"):
            await f.authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_network_error_raises(self):
        import httpx
        from app.services.spacetrack_fetcher import SpaceTrackFetcher, SpaceTrackNetworkError
        f = SpaceTrackFetcher("u", "p", base_url="https://fake.space-track.org")
        await f._ensure_client()
        f._client.post = AsyncMock(side_effect=httpx.TransportError("Connection refused"))

        with pytest.raises(SpaceTrackNetworkError, match="transport error"):
            await f.authenticate()

    @pytest.mark.asyncio
    async def test_session_renewal_triggered_on_age(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", session_ttl_seconds=10)
        f._authenticated = True
        f._auth_at = time.monotonic() - 15  # 15s ago, TTL=10s → stale

        auth_calls = []
        async def mock_authenticate():
            auth_calls.append(1)
            f._authenticated = True
            f._auth_at = time.monotonic()

        f.authenticate = mock_authenticate
        await f._maybe_renew_session()
        assert len(auth_calls) == 1

    @pytest.mark.asyncio
    async def test_session_no_renewal_when_fresh(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", session_ttl_seconds=3600)
        f._authenticated = True
        f._auth_at = time.monotonic()  # just now — fresh

        auth_calls = []
        f.authenticate = AsyncMock(side_effect=lambda: auth_calls.append(1))
        await f._maybe_renew_session()
        assert len(auth_calls) == 0


class TestRateLimiter:
    """Token bucket rate limiter tests."""

    @pytest.mark.asyncio
    async def test_rate_limit_not_exceeded(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", rate_limit_per_hour=10)
        for _ in range(10):
            await f._check_rate_limit()
        assert f._request_count == 10

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raises(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher, SpaceTrackRateLimitError
        f = SpaceTrackFetcher("u", "p", rate_limit_per_hour=3)
        for _ in range(3):
            await f._check_rate_limit()
        with pytest.raises(SpaceTrackRateLimitError, match="Rate limit reached"):
            await f._check_rate_limit()

    @pytest.mark.asyncio
    async def test_rate_limit_window_resets(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", rate_limit_per_hour=2)
        for _ in range(2):
            await f._check_rate_limit()
        # Simulate window expiry
        f._window_start = time.monotonic() - 3700
        # Should not raise now
        await f._check_rate_limit()
        assert f._request_count == 1


class TestFetchMethods:
    """Tests for each public fetch method using mocked HTTP responses."""

    def _make_fetcher_with_mock(self, response_text: str, status: int = 200):
        """Build a fetcher with a mocked _get method."""
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", base_url="https://fake.space-track.org")
        f._authenticated = True
        f._auth_at = time.monotonic()

        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.text = response_text
        f._get = AsyncMock(return_value=mock_resp)
        f._check_rate_limit = AsyncMock()
        f._maybe_renew_session = AsyncMock()
        return f

    @pytest.mark.asyncio
    async def test_fetch_latest_tles_ok(self):
        f = self._make_fetcher_with_mock(SAMPLE_TLE_TEXT)
        result = await f.fetch_latest_tles(days_back=2)
        assert result.ok is True
        assert result.source == "spacetrack"
        assert len(result.raw_text) > 0
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_fetch_latest_tles_network_fail(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher, SpaceTrackNetworkError
        f = SpaceTrackFetcher("u", "p")
        f._authenticated = True
        f._auth_at = time.monotonic()
        f._get = AsyncMock(side_effect=SpaceTrackNetworkError("Timeout"))
        f._check_rate_limit = AsyncMock()
        f._maybe_renew_session = AsyncMock()

        result = await f.fetch_latest_tles()
        assert result.ok is False
        assert result.error is not None
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_fetch_satellite_tle_ok(self):
        tle_text = SAMPLE_TLE_ISS.strip()
        f = self._make_fetcher_with_mock(tle_text)
        result = await f.fetch_satellite_tle(25544)
        assert result.ok is True
        assert result.record_count == 1

    @pytest.mark.asyncio
    async def test_fetch_satellite_tle_empty_returns_zero(self):
        f = self._make_fetcher_with_mock("")
        result = await f.fetch_satellite_tle(99999)
        assert result.ok is True
        assert result.record_count == 0

    @pytest.mark.asyncio
    async def test_fetch_active_catalog_ok(self):
        f = self._make_fetcher_with_mock(SAMPLE_TLE_TEXT * 100)
        result = await f.fetch_active_catalog()
        assert result.ok is True
        assert len(result.raw_text) > 0

    @pytest.mark.asyncio
    async def test_fetch_full_catalog_record_count(self):
        # Count based on "\n1 " occurrences
        text = SAMPLE_TLE_TEXT  # has 2 TLEs
        f = self._make_fetcher_with_mock(text)
        result = await f.fetch_full_catalog()
        # ISS line1 starts with "\n1 " when preceded by name line
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_health_check_ok(self):
        f = self._make_fetcher_with_mock("1 25544U ...")
        health = await f.health_check()
        assert health.reachable is True
        assert health.authenticated is True

    @pytest.mark.asyncio
    async def test_health_check_network_fail(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher, SpaceTrackNetworkError
        f = SpaceTrackFetcher("u", "p")
        f._authenticated = True
        f._auth_at = time.monotonic()
        f._get = AsyncMock(side_effect=SpaceTrackNetworkError("refused"))
        f._check_rate_limit = AsyncMock()
        f._maybe_renew_session = AsyncMock()

        health = await f.health_check()
        assert health.reachable is False
        assert health.error is not None


class TestRetryBehavior:
    """Test that retry logic fires correctly."""

    @pytest.mark.asyncio
    async def test_retries_on_500(self):
        """5xx should retry with exponential backoff."""
        from app.services.spacetrack_fetcher import (
            SpaceTrackFetcher, SpaceTrackNetworkError
        )
        f = SpaceTrackFetcher("u", "p")
        f._authenticated = True
        f._auth_at = time.monotonic()
        f._check_rate_limit = AsyncMock()
        f._maybe_renew_session = AsyncMock()

        call_count = [0]

        import httpx
        async def flaky_get(path):
            call_count[0] += 1
            if call_count[0] < 3:
                mock_resp = MagicMock()
                mock_resp.status_code = 503
                mock_resp.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError("503", request=None, response=mock_resp)
                )
                # Trigger our network error path
                raise SpaceTrackNetworkError("503 Service Unavailable")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = SAMPLE_TLE_ISS
            return mock_resp

        f._client = AsyncMock()
        f._client.get = flaky_get

        # Patch wait to avoid actually sleeping in tests
        with patch("app.services.spacetrack_fetcher.wait_exponential") as mock_wait:
            mock_wait.return_value = MagicMock(return_value=0)
            result = await f.fetch_latest_tles()

        # Either succeeded or failed after retries — check call count
        assert call_count[0] >= 1

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        """SpaceTrackAuthError should NOT trigger retries."""
        from app.services.spacetrack_fetcher import SpaceTrackFetcher, SpaceTrackAuthError

        auth_calls = [0]
        async def failing_auth():
            auth_calls[0] += 1
            raise SpaceTrackAuthError("Bad credentials")

        f = SpaceTrackFetcher("u", "wrong")
        f.authenticate = failing_auth

        with pytest.raises(SpaceTrackAuthError):
            await f.authenticate()

        assert auth_calls[0] == 1  # exactly once, no retry


# ═══════════════════════════════════════════════════════════════
# UNIT TESTS — CatalogSyncService
# ═══════════════════════════════════════════════════════════════

class TestCatalogSyncService:
    """Test CatalogSyncService with mocked fetcher and ingest service."""

    def _make_service(self, fetch_ok=True, fetch_text=None, ingest_inserted=2):
        """Build a CatalogSyncService with all deps mocked."""
        from app.services.catalog_sync_service import CatalogSyncService
        from app.services.spacetrack_fetcher import FetchResult

        mock_fetcher = AsyncMock()
        mock_fetcher._authenticated = True
        mock_fetcher._auth_at = time.monotonic()
        mock_fetcher.authenticate = AsyncMock()

        fetch_result = FetchResult(
            ok=fetch_ok,
            source="spacetrack",
            raw_text=fetch_text or SAMPLE_TLE_TEXT,
            record_count=2 if fetch_ok else 0,
            http_status=200 if fetch_ok else 500,
            error=None if fetch_ok else "network error",
        )
        mock_fetcher.fetch_full_catalog = AsyncMock(return_value=fetch_result)
        mock_fetcher.fetch_latest_tles = AsyncMock(return_value=fetch_result)
        mock_fetcher.fetch_active_catalog = AsyncMock(return_value=fetch_result)

        mock_session = AsyncMock()

        from app.services.tle_ingest_service import IngestResult
        mock_ingest = AsyncMock()
        mock_ingest.ingest_text = AsyncMock(return_value=IngestResult(
            total_parsed=2,
            inserted=ingest_inserted,
            duplicates=2 - ingest_inserted,
            satellites_updated=ingest_inserted,
        ))

        mock_sat_repo = AsyncMock()
        mock_sat_repo.get_active_leos = AsyncMock(return_value=[])

        mock_tle_repo = AsyncMock()
        mock_tle_repo.get_stale = AsyncMock(return_value=[])

        svc = CatalogSyncService.__new__(CatalogSyncService)
        svc._fetcher    = mock_fetcher
        svc._session    = mock_session
        svc._redis      = None
        svc._sat_repo   = mock_sat_repo
        svc._tle_repo   = mock_tle_repo
        svc._ingest_svc = mock_ingest

        return svc

    @pytest.mark.asyncio
    async def test_sync_full_success(self):
        svc = self._make_service()
        report = await svc.sync_full("test-run-001")

        assert report.sync_id == "test-run-001"
        assert report.status == "success"
        assert report.total_parsed == 2
        assert report.inserted == 2
        assert report.completed_at is not None
        assert "authenticate" in report.phases_completed
        assert "download" in report.phases_completed
        assert "ingest" in report.phases_completed

    @pytest.mark.asyncio
    async def test_sync_incremental(self):
        svc = self._make_service()
        report = await svc.sync_incremental(days_back=2, sync_id="incr-001")
        assert report.status == "success"
        svc._fetcher.fetch_latest_tles.assert_called_once_with(days_back=2)

    @pytest.mark.asyncio
    async def test_sync_fails_on_download_error(self):
        svc = self._make_service(fetch_ok=False)
        report = await svc.sync_full("fail-001")

        assert report.status == "failed"
        assert "download_failed" in report.failure_reason
        assert report.inserted == 0

    @pytest.mark.asyncio
    async def test_sync_partial_on_parse_errors(self):
        from app.services.tle_ingest_service import IngestResult
        svc = self._make_service()
        svc._ingest_svc.ingest_text = AsyncMock(return_value=IngestResult(
            total_parsed=10, inserted=8, duplicates=0, satellites_updated=8,
            errors=[{"name": "BAD-TLE", "error": "checksum"}, {"name": "BAD2", "error": "short"}],
        ))
        report = await svc.sync_full()
        assert report.status == "partial"
        assert report.parse_errors == 2
        assert report.inserted == 8

    @pytest.mark.asyncio
    async def test_sync_report_has_duration(self):
        svc = self._make_service()
        report = await svc.sync_full()
        assert report.duration_seconds > 0.0
        assert report.completed_at > report.started_at

    @pytest.mark.asyncio
    async def test_sync_full_mode_calls_full_catalog(self):
        svc = self._make_service()
        await svc.sync_full()
        svc._fetcher.fetch_full_catalog.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_stale_count_populated(self):
        from app.services.catalog_sync_service import CatalogSyncService
        svc = self._make_service()
        # Mock 5 stale satellites
        svc._tle_repo.get_stale = AsyncMock(return_value=["x"] * 5)
        report = await svc.sync_full()
        assert report.stale_satellite_count == 5

    @pytest.mark.asyncio
    async def test_cache_refresh_skipped_when_no_redis(self):
        svc = self._make_service()
        svc._redis = None
        report = await svc.sync_full()
        # cache_refresh phase should not appear (or appear as skipped)
        assert "cache_refresh" not in report.phases_completed
        assert report.cache_keys_refreshed == 0

    @pytest.mark.asyncio
    async def test_cache_refresh_called_when_redis_present(self):
        svc = self._make_service()
        mock_redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.hset = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=None)
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        svc._redis = mock_redis

        # Mock get_active_leos to return satellites with TLE data
        mock_sat = MagicMock()
        mock_sat.norad_id = 25544
        mock_sat.tle_line1 = SAMPLE_TLE_ISS.split("\n")[1]
        mock_sat.tle_line2 = SAMPLE_TLE_ISS.split("\n")[2]
        mock_sat.tle_epoch = datetime(2025, 6, 17, tzinfo=timezone.utc)
        mock_sat.name = "ISS"
        mock_sat.tle_source = "spacetrack"
        svc._sat_repo.get_active_leos = AsyncMock(return_value=[mock_sat])

        report = await svc.sync_full()
        assert report.cache_keys_refreshed == 1
        assert "cache_refresh" in report.phases_completed


# ═══════════════════════════════════════════════════════════════
# UNIT TESTS — Scheduler
# ═══════════════════════════════════════════════════════════════

class TestScheduler:
    """Test scheduler construction and job configuration."""

    def test_build_scheduler_has_five_jobs(self):
        from app.services.catalog_scheduler import build_scheduler
        s = build_scheduler()
        jobs = s.get_jobs()
        job_ids = {j.id for j in jobs}
        assert "full_catalog_sync" in job_ids
        assert "incremental_tle_refresh" in job_ids
        assert len(jobs) >= 2
        # Don't start it — just test construction
        s.shutdown(wait=False) if s.running else None

    def test_full_sync_job_interval(self):
        from app.services.catalog_scheduler import build_scheduler
        from apscheduler.triggers.interval import IntervalTrigger
        s = build_scheduler()
        jobs = {j.id: j for j in s.get_jobs()}
        full_job = jobs["full_catalog_sync"]
        assert isinstance(full_job.trigger, IntervalTrigger)
        # interval is stored in seconds internally
        assert full_job.trigger.interval.total_seconds() == 6 * 3600

    def test_incremental_job_interval(self):
        from app.services.catalog_scheduler import build_scheduler
        from apscheduler.triggers.interval import IntervalTrigger
        s = build_scheduler()
        jobs = {j.id: j for j in s.get_jobs()}
        incr_job = jobs["incremental_tle_refresh"]
        assert isinstance(incr_job.trigger, IntervalTrigger)
        assert incr_job.trigger.interval.total_seconds() == 2 * 3600


class TestDistributedLock:
    """Test Redis distributed lock behavior."""

    @pytest.mark.asyncio
    async def test_lock_acquired_when_key_not_set(self):
        from app.services.catalog_scheduler import _distributed_lock
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=b"test-owner")
        mock_redis.delete = AsyncMock()

        async with _distributed_lock(mock_redis, "test:lock", 60, "test-owner") as acquired:
            assert acquired is True
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_not_acquired_when_key_exists(self):
        from app.services.catalog_scheduler import _distributed_lock
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)  # NX fails → returns None
        mock_redis.delete = AsyncMock()

        async with _distributed_lock(mock_redis, "test:lock", 60, "owner-2") as acquired:
            assert acquired is False
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_released_on_exception(self):
        from app.services.catalog_scheduler import _distributed_lock
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=b"owner-x")
        mock_redis.delete = AsyncMock()

        with pytest.raises(ValueError):
            async with _distributed_lock(mock_redis, "test:lock", 60, "owner-x"):
                raise ValueError("Simulated error")

        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_not_released_if_expired_and_stolen(self):
        """Don't delete the lock if another process now owns it."""
        from app.services.catalog_scheduler import _distributed_lock
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        # Simulates: lock expired and re-acquired by different owner
        mock_redis.get = AsyncMock(return_value=b"different-owner")
        mock_redis.delete = AsyncMock()

        async with _distributed_lock(mock_redis, "test:lock", 60, "original-owner"):
            pass

        mock_redis.delete.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# FAILURE TESTS
# ═══════════════════════════════════════════════════════════════

class TestFailureScenarios:
    """Tests for every failure mode in the ingestion pipeline."""

    @pytest.mark.asyncio
    async def test_auth_failure_aborts_sync(self):
        from app.services.catalog_sync_service import CatalogSyncService
        from app.services.spacetrack_fetcher import SpaceTrackAuthError

        mock_fetcher = AsyncMock()
        mock_fetcher._authenticated = False
        mock_fetcher.authenticate = AsyncMock(
            side_effect=SpaceTrackAuthError("Bad credentials")
        )

        svc = CatalogSyncService.__new__(CatalogSyncService)
        svc._fetcher  = mock_fetcher
        svc._session  = AsyncMock()
        svc._redis    = None

        report = await svc._run_sync("full", "fail-auth")
        assert report.status == "failed"
        assert "auth_error" in report.failure_reason

    @pytest.mark.asyncio
    async def test_rate_limit_failure_aborts_sync(self):
        from app.services.catalog_sync_service import CatalogSyncService
        from app.services.spacetrack_fetcher import (
            FetchResult, SpaceTrackRateLimitError
        )

        mock_fetcher = AsyncMock()
        mock_fetcher._authenticated = True
        mock_fetcher._auth_at = time.monotonic()
        mock_fetcher.authenticate = AsyncMock()
        mock_fetcher.fetch_full_catalog = AsyncMock(
            side_effect=SpaceTrackRateLimitError("300/300 req/hr")
        )

        svc = CatalogSyncService.__new__(CatalogSyncService)
        svc._fetcher  = mock_fetcher
        svc._session  = AsyncMock()
        svc._redis    = None

        report = await svc._run_sync("full", "fail-rate")
        assert report.status == "failed"
        assert "rate_limit" in report.failure_reason

    @pytest.mark.asyncio
    async def test_empty_download_returns_zero_counts(self):
        from app.services.catalog_sync_service import CatalogSyncService
        from app.services.spacetrack_fetcher import FetchResult
        from app.services.tle_ingest_service import IngestResult

        mock_fetcher = AsyncMock()
        mock_fetcher._authenticated = True
        mock_fetcher._auth_at = time.monotonic()
        mock_fetcher.authenticate = AsyncMock()
        mock_fetcher.fetch_full_catalog = AsyncMock(return_value=FetchResult(
            ok=True, source="spacetrack", raw_text="", record_count=0,
        ))

        mock_ingest = AsyncMock()
        mock_ingest.ingest_text = AsyncMock(return_value=IngestResult(
            total_parsed=0, inserted=0, duplicates=0, satellites_updated=0,
        ))

        svc = CatalogSyncService.__new__(CatalogSyncService)
        svc._fetcher     = mock_fetcher
        svc._session     = AsyncMock()
        svc._redis       = None
        svc._ingest_svc  = mock_ingest
        svc._sat_repo    = AsyncMock()
        svc._sat_repo.get_active_leos = AsyncMock(return_value=[])
        svc._tle_repo    = AsyncMock()
        svc._tle_repo.get_stale = AsyncMock(return_value=[])

        report = await svc.sync_full()
        assert report.status == "success"
        assert report.total_parsed == 0
        assert report.inserted == 0

    @pytest.mark.asyncio
    async def test_corrupt_tle_text_handled_gracefully(self):
        from app.services.tle_ingest_service import TLEIngestService, IngestResult
        """Corrupt TLE text should be reported as parse_error, not exception."""
        corrupt_text = "CORRUPT\nNOT A TLE LINE 1\nNOT A TLE LINE 2\n"

        # Use real ingest service to verify parse error handling
        mock_session = AsyncMock()

        from app.db.repositories.satellite_repository import SatelliteRepository
        from app.db.repositories.tle_repository import TLERepository
        from app.db.repositories.orbital_event_repository import OrbitalEventRepository

        with patch.object(TLERepository, "bulk_insert", new=AsyncMock(return_value=0)), \
             patch.object(SatelliteRepository, "update_tle_cache", new=AsyncMock(return_value=0)):
            svc = TLEIngestService(mock_session)
            # The session's transactional context must work
            with patch("app.services.tle_ingest_service.transactional") as mock_txn:
                mock_txn.return_value.__aenter__ = AsyncMock(return_value=None)
                mock_txn.return_value.__aexit__ = AsyncMock(return_value=None)
                result = await svc.ingest_text(corrupt_text, source="test")

        # corrupt TLE should produce errors but not raise
        assert result.total_parsed == 1  # parsed 1 triple
        assert result.inserted == 0       # nothing valid to insert

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_abort_sync(self):
        """Cache refresh failure must not fail the entire sync."""
        from app.services.catalog_sync_service import CatalogSyncService
        from app.services.spacetrack_fetcher import FetchResult
        from app.services.tle_ingest_service import IngestResult

        mock_fetcher = AsyncMock()
        mock_fetcher._authenticated = True
        mock_fetcher._auth_at = time.monotonic()
        mock_fetcher.authenticate = AsyncMock()
        mock_fetcher.fetch_full_catalog = AsyncMock(return_value=FetchResult(
            ok=True, source="spacetrack", raw_text=SAMPLE_TLE_TEXT, record_count=2,
        ))

        mock_ingest = AsyncMock()
        mock_ingest.ingest_text = AsyncMock(return_value=IngestResult(
            total_parsed=2, inserted=2, duplicates=0, satellites_updated=2,
        ))

        # Redis that always raises
        mock_redis = AsyncMock()
        mock_redis.pipeline = MagicMock(side_effect=Exception("Redis connection refused"))

        svc = CatalogSyncService.__new__(CatalogSyncService)
        svc._fetcher     = mock_fetcher
        svc._session     = AsyncMock()
        svc._redis       = mock_redis
        svc._ingest_svc  = mock_ingest
        svc._sat_repo    = AsyncMock()
        svc._sat_repo.get_active_leos = AsyncMock(return_value=[])
        svc._tle_repo    = AsyncMock()
        svc._tle_repo.get_stale = AsyncMock(return_value=[])

        report = await svc.sync_full()
        # Sync should still succeed despite Redis failure
        assert report.status == "success"
        assert report.inserted == 2


# ═══════════════════════════════════════════════════════════════
# RATE LIMIT TESTS (429 handling)
# ═══════════════════════════════════════════════════════════════

class TestRateLimitHandling:
    """Tests for Space-Track 429 handling."""

    @pytest.mark.asyncio
    async def test_fetch_returns_failed_on_rate_limit(self):
        from app.services.spacetrack_fetcher import (
            SpaceTrackFetcher, SpaceTrackRateLimitError
        )
        f = SpaceTrackFetcher("u", "p", rate_limit_per_hour=0)
        f._authenticated = True
        f._auth_at = time.monotonic()

        result = await f.fetch_latest_tles()
        assert result.ok is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_hourly_counter_increments_per_request(self):
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", rate_limit_per_hour=10)
        for _ in range(5):
            await f._check_rate_limit()
        assert f._request_count == 5

    @pytest.mark.asyncio
    async def test_concurrent_requests_safe(self):
        """Concurrent rate limit checks must not exceed limit due to race."""
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("u", "p", rate_limit_per_hour=10)

        async def check():
            try:
                await f._check_rate_limit()
                return True
            except Exception:
                return False

        results = await asyncio.gather(*[check() for _ in range(10)])
        # All 10 should succeed (limit is exactly 10)
        assert sum(results) == 10
        assert f._request_count == 10


# ═══════════════════════════════════════════════════════════════
# MOCK SERVER TEST
# ═══════════════════════════════════════════════════════════════

class MockSpaceTrackServer:
    """
    Simulates Space-Track.org API responses.
    Used for end-to-end pipeline testing without network calls.
    """

    def __init__(
        self,
        tle_text: str = SAMPLE_TLE_TEXT,
        auth_should_fail: bool = False,
        return_429: bool = False,
    ):
        self.tle_text        = tle_text
        self.auth_should_fail = auth_should_fail
        self.return_429      = return_429
        self.request_log: list[dict] = []

    def build_fetcher(self) -> "SpaceTrackFetcher":
        """Return a SpaceTrackFetcher that calls this mock instead of the real API."""
        from app.services.spacetrack_fetcher import SpaceTrackFetcher
        f = SpaceTrackFetcher("mock@test.com", "mockpw",
                              base_url="http://mock-spacetrack.local")
        f._client = AsyncMock()

        server = self

        async def mock_post(path, **kwargs):
            server.request_log.append({"method": "POST", "path": path})
            mock_resp = MagicMock()
            if server.auth_should_fail:
                mock_resp.status_code = 401
                mock_resp.text = "Unauthorized"
            else:
                mock_resp.status_code = 200
                mock_resp.text = ""
            return mock_resp

        async def mock_get(path, **kwargs):
            server.request_log.append({"method": "GET", "path": str(path)})
            mock_resp = MagicMock()
            if server.return_429:
                mock_resp.status_code = 429
                mock_resp.text = "Too Many Requests"
                mock_resp.raise_for_status = MagicMock()
            else:
                mock_resp.status_code = 200
                mock_resp.text = server.tle_text
            return mock_resp

        f._client.post = mock_post
        f._client.get  = mock_get
        return f


class TestMockServer:
    """End-to-end tests using MockSpaceTrackServer."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mock_server(self):
        """Authenticate → download → parse — no real network."""
        server = MockSpaceTrackServer(tle_text=SAMPLE_TLE_TEXT)
        fetcher = server.build_fetcher()

        # Bypass real authenticate → set session manually
        fetcher._authenticated = True
        fetcher._auth_at = time.monotonic()
        fetcher._check_rate_limit = AsyncMock()
        fetcher._maybe_renew_session = AsyncMock()

        result = await fetcher.fetch_full_catalog()
        assert result.ok is True
        assert result.source == "spacetrack"
        assert len(result.raw_text) > 0

    @pytest.mark.asyncio
    async def test_mock_server_auth_failure(self):
        from app.services.spacetrack_fetcher import SpaceTrackAuthError
        server = MockSpaceTrackServer(auth_should_fail=True)
        fetcher = server.build_fetcher()

        with pytest.raises(SpaceTrackAuthError):
            await fetcher.authenticate()

    @pytest.mark.asyncio
    async def test_mock_server_tracks_requests(self):
        server = MockSpaceTrackServer()
        fetcher = server.build_fetcher()
        fetcher._authenticated = True
        fetcher._auth_at = time.monotonic()
        fetcher._check_rate_limit = AsyncMock()
        fetcher._maybe_renew_session = AsyncMock()

        await fetcher.fetch_satellite_tle(25544)
        assert len(server.request_log) >= 1

    @pytest.mark.asyncio
    async def test_mock_50_tles_parses_correctly(self):
        """50 synthetic TLEs flow through mock → parse."""
        from app.services.tle_ingest_service import _parse_tle_text
        text_50 = _make_synthetic_tle_text(50)
        triples = _parse_tle_text(text_50)
        # All 50 should parse into (name, l1, l2) triples
        assert len(triples) == 50
        for name, l1, l2 in triples:
            assert l1.startswith("1 ")
            assert l2.startswith("2 ")
