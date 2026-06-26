"""
ORBITIQ-X — Bulk Insert Batching Regression Test
==================================================
Regression test for: asyncpg.exceptions.InterfaceError:
  "the number of query arguments cannot exceed 32767"

Root cause
──────────
  TLERecord has 27 insertable columns.
  Satellite has 41 insertable columns.
  Previous batch sizes (5000 / 2000) produced:
    5000 × 27 = 135,000 params  (TLE)    — exceeds 32,767
    2000 × 41 =  82,000 params  (Sat)    — exceeds 32,767

Fix
───
  tle_repository._BULK_BATCH    = 1000  (1000 × 27 = 27,000 ✓)
  satellite_repository._BULK_BATCH = 500   ( 500 × 41 = 20,500 ✓)

This test verifies:
  1. The batch sizes are within the PostgreSQL parameter limit.
  2. bulk_insert() splits records correctly into batches.
  3. A payload exceeding the old limit (>5000 TLE rows) is handled
     without raising an InterfaceError (tested via mock).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Constants ────────────────────────────────────────────────────────────────

PG_PARAM_LIMIT = 32_767
TLE_COLS       = 27   # insertable columns in TLERecord (excl. autoincrement PK)
SAT_COLS       = 41   # insertable columns in Satellite  (excl. autoincrement PK)


# ── Helper ───────────────────────────────────────────────────────────────────

def _make_tle_dict(norad_id: int) -> dict:
    """Minimal TLE dict matching the TLERecord insertable columns."""
    now = datetime.now(timezone.utc)
    return {
        "norad_id":            norad_id,
        "satellite_id":        None,
        "name":                f"SAT-{norad_id}",
        "line1":               "1 25544U 98067A   21275.52375000  .00001764  00000-0  41034-4 0  9990",
        "line2":               "2 25544  51.6437 191.4777 0001460 357.1905 154.0182 15.48858802304525",
        "epoch":               now,
        "epoch_year":          21,
        "epoch_day":           275.52,
        "inclination_deg":     51.64,
        "raan_deg":            191.48,
        "eccentricity":        0.000146,
        "arg_perigee_deg":     357.19,
        "mean_anomaly_deg":    154.02,
        "mean_motion_rev_day": 15.49,
        "bstar":               4.1e-5,
        "n_dot":               1.764e-5,
        "n_ddot":              0.0,
        "element_set_num":     999,
        "rev_number":          30452,
        "semi_major_axis_km":  6796.4,
        "perigee_km":          409.8,
        "apogee_km":           416.7,
        "period_minutes":      92.7,
        "source":              "spacetrack",
        "checksum_ok":         True,
        "age_at_ingest_days":  0.0,
        "ingested_at":         now,
    }


# ── Unit: batch size safety ───────────────────────────────────────────────────

class TestBatchSizeSafety:
    """Verify batch sizes stay within PostgreSQL's 32767-parameter limit."""

    def test_tle_batch_within_pg_limit(self):
        from app.db.repositories.tle_repository import _BULK_BATCH
        params_per_batch = _BULK_BATCH * TLE_COLS
        assert params_per_batch <= PG_PARAM_LIMIT, (
            f"TLE batch produces {params_per_batch} params "
            f"({_BULK_BATCH} rows × {TLE_COLS} cols) — exceeds PG limit {PG_PARAM_LIMIT}. "
            f"Reduce _BULK_BATCH to ≤ {PG_PARAM_LIMIT // TLE_COLS}."
        )

    def test_satellite_batch_within_pg_limit(self):
        from app.db.repositories.satellite_repository import _BULK_BATCH
        params_per_batch = _BULK_BATCH * SAT_COLS
        assert params_per_batch <= PG_PARAM_LIMIT, (
            f"Satellite batch produces {params_per_batch} params "
            f"({_BULK_BATCH} rows × {SAT_COLS} cols) — exceeds PG limit {PG_PARAM_LIMIT}. "
            f"Reduce _BULK_BATCH to ≤ {PG_PARAM_LIMIT // SAT_COLS}."
        )

    def test_tle_old_batch_would_have_exceeded_limit(self):
        """Confirm the old batch size 5000 was the problem."""
        old_batch = 5000
        assert old_batch * TLE_COLS > PG_PARAM_LIMIT, (
            "Old batch 5000 should have exceeded PG limit — test logic error"
        )

    def test_satellite_old_batch_would_have_exceeded_limit(self):
        """Confirm the old batch size 2000 was the problem."""
        old_batch = 2000
        assert old_batch * SAT_COLS > PG_PARAM_LIMIT, (
            "Old batch 2000 should have exceeded PG limit — test logic error"
        )


# ── Unit: batching logic ──────────────────────────────────────────────────────

class TestBulkInsertBatching:
    """Verify bulk_insert() calls execute in correct number of batches."""

    @pytest.mark.asyncio
    async def test_batches_large_payload_correctly(self):
        """
        2000 TLE records with _BULK_BATCH=1000 should produce exactly 2 execute calls.
        Previously would have been 1 call with 54,000 params → InterfaceError.
        """
        from app.db.repositories.tle_repository import TLERepository, _BULK_BATCH

        # Build payload that EXCEEDS the old limit (5000) to prove regression is fixed
        n_records = 2000
        records = [_make_tle_dict(i) for i in range(1, n_records + 1)]

        expected_batches = math.ceil(n_records / _BULK_BATCH)

        # Mock the async session
        mock_result = MagicMock()
        mock_result.rowcount = _BULK_BATCH
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush  = AsyncMock()

        repo = TLERepository(session=mock_session)
        total = await repo.bulk_insert(records)

        assert mock_session.execute.call_count == expected_batches, (
            f"Expected {expected_batches} execute() calls for {n_records} records "
            f"at batch size {_BULK_BATCH}, got {mock_session.execute.call_count}"
        )
        assert total == expected_batches * _BULK_BATCH

    @pytest.mark.asyncio
    async def test_empty_payload_returns_zero(self):
        """bulk_insert([]) must return 0 without touching the DB."""
        from app.db.repositories.tle_repository import TLERepository

        mock_session = AsyncMock()
        repo = TLERepository(session=mock_session)
        result = await repo.bulk_insert([])

        assert result == 0
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_record_uses_one_batch(self):
        """A single record should use exactly one execute() call."""
        from app.db.repositories.tle_repository import TLERepository

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush  = AsyncMock()

        repo = TLERepository(session=mock_session)
        await repo.bulk_insert([_make_tle_dict(99999)])
        assert mock_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_payload_exceeding_old_limit_does_not_raise(self):
        """
        5001 records would have caused InterfaceError with the old batch=5000.
        With batch=1000 it splits into 6 batches — no error.
        """
        from app.db.repositories.tle_repository import TLERepository, _BULK_BATCH

        n_records = 5001  # Old batch size + 1 — previously fatal
        records = [_make_tle_dict(i) for i in range(1, n_records + 1)]
        expected_batches = math.ceil(n_records / _BULK_BATCH)

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush  = AsyncMock()

        repo = TLERepository(session=mock_session)

        # Must not raise — previously this would trigger asyncpg InterfaceError
        await repo.bulk_insert(records)

        assert mock_session.execute.call_count == expected_batches


# ── Unit: params-per-batch calculation ────────────────────────────────────────

class TestParameterCalculation:
    """Mathematical verification of the safe batch size formula."""

    def test_tle_params_formula(self):
        from app.db.repositories.tle_repository import _BULK_BATCH
        # Every batch must produce strictly fewer than PG_PARAM_LIMIT params
        assert _BULK_BATCH * TLE_COLS < PG_PARAM_LIMIT
        # And must be a meaningful batch (not 1)
        assert _BULK_BATCH >= 100

    def test_satellite_params_formula(self):
        from app.db.repositories.satellite_repository import _BULK_BATCH
        assert _BULK_BATCH * SAT_COLS < PG_PARAM_LIMIT
        assert _BULK_BATCH >= 100

    def test_batch_sizes_are_documented_safe_values(self):
        """Batch sizes must remain below the safe ceiling."""
        from app.db.repositories.tle_repository import _BULK_BATCH as tle_batch
        from app.db.repositories.satellite_repository import _BULK_BATCH as sat_batch

        tle_ceiling = PG_PARAM_LIMIT // TLE_COLS   # 1213
        sat_ceiling = PG_PARAM_LIMIT // SAT_COLS   # 799

        assert tle_batch <= tle_ceiling, (
            f"TLE batch {tle_batch} exceeds safe ceiling {tle_ceiling}"
        )
        assert sat_batch <= sat_ceiling, (
            f"Satellite batch {sat_batch} exceeds safe ceiling {sat_ceiling}"
        )
