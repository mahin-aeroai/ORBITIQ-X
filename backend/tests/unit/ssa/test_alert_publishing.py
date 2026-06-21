"""
ORBITIQ-X — Alert Publishing Tests
=====================================
Verifies that ConjunctionPersistenceService correctly publishes
RED and YELLOW conjunction events to the Redis alert channel,
and that GREEN / WHITE events are NOT published.

Coverage
─────────
  TestAlertPublishing
    test_red_event_publishes_to_redis
    test_yellow_event_publishes_to_redis
    test_green_event_does_not_publish
    test_white_event_does_not_publish
    test_alert_payload_schema
    test_hours_remaining_in_payload
    test_multiple_events_all_published
    test_redis_unavailable_does_not_raise
    test_risk_level_in_payload

  TestRiskClassification
    test_classify_risk_thresholds
    test_maneuver_required_thresholds

Run
────
  pytest tests/unit/ssa/test_alert_publishing.py -v
  pytest tests/unit/ssa/ -v --asyncio-mode=auto
"""
from __future__ import annotations

import json
import sys
import pathlib
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Add backend root to path
_BE_ROOT = pathlib.Path(__file__).parents[3]
if str(_BE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BE_ROOT))


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _make_session() -> MagicMock:
    """Return a minimal mock AsyncSession."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [])))
    return session


def _make_redis() -> AsyncMock:
    """Return a mock Redis client that records publish calls."""
    redis = AsyncMock()
    redis.publish = AsyncMock(return_value=1)
    return redis


def _cdm(
    primary_norad: int = 25544,
    secondary_norad: int = 44713,
    pc: float = 1e-3,
    miss_km: float = 0.5,
    tca_hours_ahead: float = 24.0,
    primary_name: str = "ISS",
    secondary_name: str = "STARLINK-1234",
) -> dict:
    tca = datetime.now(timezone.utc) + timedelta(hours=tca_hours_ahead)
    return {
        "primary_norad":        primary_norad,
        "primary_name":         primary_name,
        "primary_type":         "satellite",
        "secondary_norad":      secondary_norad,
        "secondary_name":       secondary_name,
        "secondary_type":       "satellite",
        "tca":                  tca,
        "miss_distance_km":     miss_km,
        "collision_probability":pc,
        "relative_velocity_kms":14.2,
        "method":               "Foster2001",
    }


async def _persist(service, cdms: list[dict], persist_white: bool = False):
    """
    Call persist_screening_results with all DB/repo operations mocked.
    Injects mock repos directly on the service instance so flush() etc
    never touches a real database.
    """
    # Mock repos directly on the service instance
    service.conj_repo  = MagicMock(
        bulk_insert=AsyncMock(return_value=len(cdms)),
        get_unresolved_red_yellow=AsyncMock(return_value=[]),
    )
    service.event_repo = MagicMock(
        bulk_log=AsyncMock(return_value=None),
    )

    # transactional is used as "async with transactional(session)"
    # Patch it so it's a no-op async context manager
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__  = AsyncMock(return_value=False)

    with patch("app.services.conjunction_service.transactional", return_value=ctx):
        return await service.persist_screening_results(
            cdms=cdms, persist_white=persist_white
        )


# ─────────────────────────────────────────────────────────────
# TestRiskClassification
# ─────────────────────────────────────────────────────────────

class TestRiskClassification:

    def test_classify_risk_thresholds(self):
        from app.services.conjunction_service import classify_risk
        assert classify_risk(1e-2)  == "red"
        assert classify_risk(1e-3)  == "red"    # boundary inclusive
        assert classify_risk(9.9e-4)== "yellow"
        assert classify_risk(1e-4)  == "yellow" # boundary inclusive
        assert classify_risk(9.9e-5)== "green"
        assert classify_risk(1e-5)  == "green"  # boundary inclusive
        assert classify_risk(9.9e-6)== "white"
        assert classify_risk(0.0)   == "white"

    def test_maneuver_required_thresholds(self):
        from app.services.conjunction_service import maneuver_required
        assert maneuver_required(1e-3)   is True   # RED
        assert maneuver_required(1e-4)   is True   # YELLOW boundary
        assert maneuver_required(9.9e-5) is False  # GREEN
        assert maneuver_required(0.0)    is False


# ─────────────────────────────────────────────────────────────
# TestAlertPublishing
# ─────────────────────────────────────────────────────────────

class TestAlertPublishing:

    def _make_service(self, redis="DEFAULT"):
        """Pass redis=None explicitly to test no-Redis behaviour."""
        from app.services.conjunction_service import ConjunctionPersistenceService
        redis_client = _make_redis() if redis == "DEFAULT" else redis
        return ConjunctionPersistenceService(
            session=_make_session(),
            redis_client=redis_client,
        )

    # ── Core publish behaviour ────────────────────────────────

    @pytest.mark.asyncio
    async def test_red_event_publishes_to_redis(self):
        """RED conjunction events must publish to the alert channel."""
        redis = _make_redis()
        svc   = self._make_service(redis=redis)

        result = await _persist(svc, [_cdm(pc=5e-3)])  # RED

        assert result.red_count    == 1
        assert result.alerts_fired == 1
        redis.publish.assert_awaited_once()
        channel, payload = redis.publish.await_args.args
        assert channel == "orbitiq:conjunction:alerts"
        data = json.loads(payload)
        assert data["risk_level"] == "red"

    @pytest.mark.asyncio
    async def test_yellow_event_publishes_to_redis(self):
        """YELLOW conjunction events must also publish to the alert channel."""
        redis = _make_redis()
        svc   = self._make_service(redis=redis)

        result = await _persist(svc, [_cdm(pc=5e-4)])  # YELLOW

        assert result.yellow_count == 1
        assert result.alerts_fired == 1
        redis.publish.assert_awaited_once()
        _, payload = redis.publish.await_args.args
        data = json.loads(payload)
        assert data["risk_level"] == "yellow"

    @pytest.mark.asyncio
    async def test_green_event_does_not_publish(self):
        """GREEN events must NOT publish to the alert channel."""
        redis = _make_redis()
        svc   = self._make_service(redis=redis)

        result = await _persist(svc, [_cdm(pc=5e-5)])  # GREEN

        assert result.green_count  == 1
        assert result.alerts_fired == 0
        redis.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_white_event_does_not_publish(self):
        """WHITE events (Pc < 1e-5) are skipped entirely — no publish."""
        redis = _make_redis()
        svc   = self._make_service(redis=redis)

        result = await _persist(svc, [_cdm(pc=1e-7)])  # WHITE

        assert result.skipped_white == 1
        assert result.alerts_fired  == 0
        redis.publish.assert_not_awaited()

    # ── Payload schema ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_alert_payload_schema(self):
        """Alert payload must contain all required fields."""
        redis = _make_redis()
        svc   = self._make_service(redis=redis)

        await _persist(svc, [_cdm(pc=1e-3, primary_norad=25544, secondary_norad=44713)])

        _, payload_str = redis.publish.await_args.args
        payload = json.loads(payload_str)

        required_fields = {
            "event_id", "conjunction_id", "risk_level",
            "probability_of_collision", "primary_norad", "secondary_norad",
            "miss_distance_km", "tca", "maneuver_required",
        }
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"

        assert payload["primary_norad"]   == 25544
        assert payload["secondary_norad"] == 44713
        assert payload["risk_level"]      == "red"
        assert isinstance(payload["probability_of_collision"], float)
        assert isinstance(payload["maneuver_required"], bool)

    @pytest.mark.asyncio
    async def test_hours_remaining_in_payload(self):
        """hours_remaining must be present and approximately correct."""
        redis = _make_redis()
        svc   = self._make_service(redis=redis)

        await _persist(svc, [_cdm(pc=1e-3, tca_hours_ahead=12.0)])

        _, payload_str = redis.publish.await_args.args
        payload = json.loads(payload_str)

        assert "hours_remaining" in payload
        # Should be within 1 hour of expected 12h due to test execution time
        assert payload["hours_remaining"] is not None
        assert 10.0 < payload["hours_remaining"] < 14.0

    # ── Multi-event batches ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_multiple_events_all_published(self):
        """Mixed batch: RED and YELLOW both publish, GREEN does not."""
        redis = _make_redis()
        svc   = self._make_service(redis=redis)

        cdms = [
            _cdm(pc=5e-3, primary_norad=25544, secondary_norad=10001),  # RED
            _cdm(pc=5e-4, primary_norad=25544, secondary_norad=10002),  # YELLOW
            _cdm(pc=5e-5, primary_norad=25544, secondary_norad=10003),  # GREEN
        ]
        result = await _persist(svc, cdms)

        assert result.red_count    == 1
        assert result.yellow_count == 1
        assert result.green_count  == 1
        assert result.alerts_fired == 2  # RED + YELLOW only
        assert redis.publish.await_count == 2

        # Verify both calls went to the correct channel
        for c in redis.publish.await_args_list:
            channel, _ = c.args
            assert channel == "orbitiq:conjunction:alerts"

    @pytest.mark.asyncio
    async def test_risk_level_in_payload(self):
        """risk_level field must accurately reflect the event classification."""
        redis = _make_redis()
        svc   = self._make_service(redis=redis)

        # RED event
        await _persist(svc, [_cdm(pc=2e-3)])
        _, payload_str = redis.publish.await_args_list[0].args
        assert json.loads(payload_str)["risk_level"] == "red"

    # ── Resilience ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_redis_unavailable_does_not_raise(self):
        """Service must not raise when Redis publish fails."""
        redis = _make_redis()
        redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))
        svc   = self._make_service(redis=redis)

        # Should complete without raising
        result = await _persist(svc, [_cdm(pc=1e-3)])

        assert result.red_count == 1
        # alerts_fired should be 0 because publish failed
        assert result.alerts_fired == 0

    @pytest.mark.asyncio
    async def test_no_redis_graceful(self):
        """Service must work correctly when redis_client is None."""
        svc = self._make_service(redis=None)

        result = await _persist(svc, [_cdm(pc=1e-3)])

        assert result.red_count    == 1
        assert result.alerts_fired == 0  # No Redis → no alerts fired

    # ── Channel constant ──────────────────────────────────────

    def test_alert_channel_constant(self):
        """ALERT_CHANNEL must match the SSE bridge subscription channel."""
        from app.services.conjunction_service import ConjunctionPersistenceService
        assert ConjunctionPersistenceService.ALERT_CHANNEL == "orbitiq:conjunction:alerts"
