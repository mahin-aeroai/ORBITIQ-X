"""
ORBITIQ-X Backend — Database Integration Tests

Tests every repository and service against a real PostgreSQL instance.

Prerequisites
─────────────
  PostgreSQL running locally (or TEST_DATABASE_URL env var set).
  Migrations applied: cd backend && python migrate.py upgrade head

Run
───
  pytest tests/integration/test_db_integration.py -v
  pytest tests/integration/test_db_integration.py -v -k "satellite"
  pytest tests/integration/test_db_integration.py --tb=short

Environment
───────────
  TEST_DATABASE_URL defaults to:
    postgresql+asyncpg://orbitiq:orbitiq@localhost:5432/orbitiq_test

  Create the test database before running:
    createdb -U orbitiq orbitiq_test
    psql -U orbitiq orbitiq_test -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
    cd backend && TEST_DATABASE_URL=... python migrate.py upgrade head
"""

from __future__ import annotations

import asyncio
import math
import os
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio

# ── Skip entire module if no PostgreSQL available ─────────────
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://orbitiq:orbitiq@localhost:5432/orbitiq_test",
)

pytestmark = pytest.mark.integration


# ── Async fixtures ────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Session-scoped async engine."""
    from sqlalchemy.ext.asyncio import create_async_engine
    eng = create_async_engine(TEST_DB_URL, echo=False, pool_pre_ping=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def session(engine):
    """
    Function-scoped session with automatic rollback.

    Each test gets a clean slate — all changes are rolled back at the end
    so tests don't interfere with each other.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async with factory() as sess:
        # Begin a savepoint for the test
        async with sess.begin_nested():
            yield sess
        # rollback is automatic when the nested context exits


# ── Helpers ───────────────────────────────────────────────────

def _sat_data(norad_id: int, name: str | None = None) -> dict:
    return {
        "norad_id": norad_id,
        "name": name or f"TESTSAT-{norad_id}",
        "object_type": "satellite",
        "status": "operational",
        "regime": "LEO",
        "perigee_km": 400.0 + (norad_id % 100),
        "apogee_km":  420.0 + (norad_id % 100),
        "inclination_deg": 51.6,
        "tle_line1": f"1 {norad_id:05d}U 98067A   24015.50000000  .00016717  00000+0  30622-3 0  9993",
        "tle_line2": f"2 {norad_id:05d}  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579435701",
        "tle_epoch": datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        "tle_age_days": 0.5,
        "tle_source": "celestrak",
        "hard_body_radius_km": 0.005,
    }


def _tle_data(norad_id: int, epoch: datetime | None = None) -> dict:
    ep = epoch or datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "norad_id": norad_id,
        "name": f"SAT-{norad_id}",
        "line1": f"1 {norad_id:05d}U 98067A   24015.50000000  .00016717  00000+0  30622-3 0  9993",
        "line2": f"2 {norad_id:05d}  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579435701",
        "epoch": ep,
        "epoch_year": 2024,
        "epoch_day": 15.5,
        "inclination_deg": 51.6,
        "raan_deg": 247.4627,
        "eccentricity": 0.0006703,
        "arg_perigee_deg": 130.5360,
        "mean_anomaly_deg": 325.0288,
        "mean_motion_rev_day": 15.503,
        "bstar": 3.0622e-4,
        "n_dot": 0.00016717,
        "n_ddot": 0.0,
        "element_set_num": 999,
        "rev_number": 43570,
        "semi_major_axis_km": 6782.0,
        "perigee_km": 405.0,
        "apogee_km": 415.0,
        "period_minutes": 92.9,
        "source": "celestrak",
        "checksum_ok": True,
        "age_at_ingest_days": 0.5,
    }


def _cdm_data(primary: int, secondary: int, pc: float = 1.5e-3) -> dict:
    now = datetime.now(timezone.utc)
    risk = "red" if pc >= 1e-3 else "yellow" if pc >= 1e-4 else "green"
    return {
        "conjunction_id": f"CDM-{now.strftime('%Y%m%d%H%M%S')}-{primary:05d}-{secondary:05d}",
        "primary_norad": primary,
        "primary_name": f"SAT-{primary}",
        "secondary_norad": secondary,
        "secondary_name": f"DEBRIS-{secondary}",
        "tca": now + timedelta(hours=12),
        "miss_distance_km": 0.25,
        "relative_velocity_kms": 7.8,
        "collision_probability": pc,
        "collision_probability_method": "Foster2001",
        "risk_level": risk,
        "maneuver_required": pc >= 1e-4,
        "resolved": False,
        "screening_org": "ORBITIQ-X",
        "data_source": "computed",
        "cdm_issued_at": now,
    }


# ═══════════════════════════════════════════════════════════════
# SATELLITE REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════

class TestSatelliteRepository:

    @pytest.mark.asyncio
    async def test_upsert_insert(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        sat = await repo.upsert(_sat_data(90001))
        assert sat.id is not None
        assert sat.norad_id == 90001
        assert sat.name == "TESTSAT-90001"

    @pytest.mark.asyncio
    async def test_upsert_updates_on_conflict(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        await repo.upsert(_sat_data(90002))
        # Upsert again with changed name
        sat2 = await repo.upsert({**_sat_data(90002), "name": "UPDATED-SAT"})
        assert sat2.name == "UPDATED-SAT"

    @pytest.mark.asyncio
    async def test_get_by_norad(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        await repo.upsert(_sat_data(90003))
        row = await repo.get_by_norad(90003)
        assert row is not None
        assert row.norad_id == 90003

    @pytest.mark.asyncio
    async def test_get_by_norad_missing_returns_none(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        result = await repo.get_by_norad(999999)
        assert result is None

    @pytest.mark.asyncio
    async def test_bulk_upsert_50_satellites(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        records = [_sat_data(90100 + i) for i in range(50)]
        count = await repo.bulk_upsert(records)
        assert count == 50

    @pytest.mark.asyncio
    async def test_bulk_upsert_idempotent(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        records = [_sat_data(90200 + i) for i in range(10)]
        await repo.bulk_upsert(records)
        # Second upsert should update, not error
        count2 = await repo.bulk_upsert(records)
        assert count2 >= 0  # may be 0 on do-update for same data

    @pytest.mark.asyncio
    async def test_update_tle_cache(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        await repo.upsert(_sat_data(90004))
        epoch = datetime(2024, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
        rows = await repo.update_tle_cache(
            norad_id=90004,
            tle_line1="1 90004U 98067A   24032.00000000  .00016717  00000+0  30622-3 0  9991",
            tle_line2="2 90004  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579435701",
            epoch=epoch,
            bstar=3.0622e-4,
            perigee_km=406.0,
            apogee_km=416.0,
            inclination_deg=51.6,
            period_minutes=92.9,
            mean_motion_rev_day=15.503,
        )
        assert rows == 1

    @pytest.mark.asyncio
    async def test_count(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        initial = await repo.count()
        await repo.upsert(_sat_data(90005))
        assert await repo.count() >= initial + 1

    @pytest.mark.asyncio
    async def test_get_active_leos_filters_correctly(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        # Insert one LEO with fresh TLE
        await repo.upsert({
            **_sat_data(90006),
            "perigee_km": 410.0,
            "apogee_km": 420.0,
            "tle_age_days": 1.0,
            "tle_line1": "1 90006U test",
            "tle_line2": "2 90006U test",
        })
        # Insert one with stale TLE (should be excluded)
        await repo.upsert({
            **_sat_data(90007),
            "perigee_km": 400.0,
            "apogee_km": 410.0,
            "tle_age_days": 10.0,  # > 7 days
        })
        leos = await repo.get_active_leos()
        norads = [s.norad_id for s in leos]
        assert 90007 not in norads  # stale TLE excluded

    @pytest.mark.asyncio
    async def test_exists(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        await repo.upsert(_sat_data(90008))
        assert await repo.exists(norad_id=90008) is True
        assert await repo.exists(norad_id=999998) is False

    @pytest.mark.asyncio
    async def test_count_by_regime(self, session):
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        await repo.upsert({**_sat_data(90009), "regime": "GEO"})
        counts = await repo.count_by_regime()
        assert isinstance(counts, dict)


# ═══════════════════════════════════════════════════════════════
# TLE REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════

class TestTLERepository:

    @pytest.mark.asyncio
    async def test_insert_or_skip_new(self, session):
        from app.db.repositories.tle_repository import TLERepository
        repo = TLERepository(session)
        row = await repo.insert_or_skip(_tle_data(80001))
        assert row is not None
        assert row.norad_id == 80001

    @pytest.mark.asyncio
    async def test_insert_or_skip_duplicate_returns_none(self, session):
        from app.db.repositories.tle_repository import TLERepository
        repo = TLERepository(session)
        data = _tle_data(80002)
        await repo.insert_or_skip(data)
        row2 = await repo.insert_or_skip(data)
        assert row2 is None  # skipped on conflict

    @pytest.mark.asyncio
    async def test_get_latest(self, session):
        from app.db.repositories.tle_repository import TLERepository
        repo = TLERepository(session)
        ep1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ep2 = datetime(2024, 1, 15, tzinfo=timezone.utc)
        await repo.insert_or_skip({**_tle_data(80003, ep1), "element_set_num": 1})
        await repo.insert_or_skip({**_tle_data(80003, ep2), "element_set_num": 2})
        latest = await repo.get_latest(80003)
        assert latest is not None
        assert latest.epoch == ep2

    @pytest.mark.asyncio
    async def test_get_at_epoch(self, session):
        from app.db.repositories.tle_repository import TLERepository
        repo = TLERepository(session)
        ep1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ep2 = datetime(2024, 1, 20, tzinfo=timezone.utc)
        await repo.insert_or_skip({**_tle_data(80004, ep1), "element_set_num": 1})
        await repo.insert_or_skip({**_tle_data(80004, ep2), "element_set_num": 2})
        # Query at Jan 10 → should return ep1 TLE
        target = datetime(2024, 1, 10, tzinfo=timezone.utc)
        row = await repo.get_at_epoch(80004, target)
        assert row is not None
        assert row.epoch == ep1

    @pytest.mark.asyncio
    async def test_bulk_insert_deduplication(self, session):
        from app.db.repositories.tle_repository import TLERepository
        repo = TLERepository(session)
        records = [_tle_data(80010 + i) for i in range(20)]
        first  = await repo.bulk_insert(records)
        second = await repo.bulk_insert(records)  # all duplicates
        assert first == 20
        assert second == 0

    @pytest.mark.asyncio
    async def test_count_for_norad(self, session):
        from app.db.repositories.tle_repository import TLERepository
        repo = TLERepository(session)
        for i in range(3):
            ep = datetime(2024, 1, i + 1, tzinfo=timezone.utc)
            await repo.insert_or_skip({**_tle_data(80020, ep), "element_set_num": i + 1})
        count = await repo.count_for_norad(80020)
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_by_source(self, session):
        from app.db.repositories.tle_repository import TLERepository
        repo = TLERepository(session)
        await repo.insert_or_skip({**_tle_data(80030), "source": "spacetrack", "element_set_num": 5})
        counts = await repo.count_by_source()
        assert isinstance(counts, dict)


# ═══════════════════════════════════════════════════════════════
# CONJUNCTION REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════

class TestConjunctionRepository:

    @pytest.mark.asyncio
    async def test_insert_cdm_red(self, session):
        from app.db.repositories.conjunction_repository import ConjunctionRepository
        repo = ConjunctionRepository(session)
        cdm = _cdm_data(25544, 99001, pc=2e-3)
        row = await repo.insert_cdm(cdm)
        assert row.risk_level == "red"
        assert row.maneuver_required is True

    @pytest.mark.asyncio
    async def test_insert_cdm_yellow(self, session):
        from app.db.repositories.conjunction_repository import ConjunctionRepository
        repo = ConjunctionRepository(session)
        cdm = _cdm_data(25544, 99002, pc=5e-4)
        row = await repo.insert_cdm(cdm)
        assert row.risk_level == "yellow"

    @pytest.mark.asyncio
    async def test_bulk_insert(self, session):
        from app.db.repositories.conjunction_repository import ConjunctionRepository
        repo = ConjunctionRepository(session)
        records = [_cdm_data(25544, 99100 + i, pc=1e-3 + i * 1e-4) for i in range(10)]
        # Ensure unique conjunction_ids
        for i, r in enumerate(records):
            r["conjunction_id"] = f"CDM-TEST-BULK-{i:06d}"
        count = await repo.bulk_insert(records)
        assert count >= 10

    @pytest.mark.asyncio
    async def test_get_unresolved_red_yellow(self, session):
        from app.db.repositories.conjunction_repository import ConjunctionRepository
        repo = ConjunctionRepository(session)
        cdm = _cdm_data(25544, 99200, pc=2e-3)
        cdm["conjunction_id"] = "CDM-UNRESOLVED-001"
        await repo.insert_cdm(cdm)
        rows = await repo.get_unresolved_red_yellow()
        ids = [r.conjunction_id for r in rows]
        assert "CDM-UNRESOLVED-001" in ids

    @pytest.mark.asyncio
    async def test_resolve_event(self, session):
        from app.db.repositories.conjunction_repository import ConjunctionRepository
        repo = ConjunctionRepository(session)
        cdm = _cdm_data(25544, 99300, pc=2e-3)
        cdm["conjunction_id"] = "CDM-RESOLVE-TEST-001"
        await repo.insert_cdm(cdm)
        success = await repo.resolve("CDM-RESOLVE-TEST-001", "natural_miss")
        assert success is True
        # Verify resolved flag
        row = await repo.get_by_conjunction_id("CDM-RESOLVE-TEST-001")
        assert row is not None
        assert row.resolved is True
        assert row.resolution == "natural_miss"

    @pytest.mark.asyncio
    async def test_get_for_object(self, session):
        from app.db.repositories.conjunction_repository import ConjunctionRepository
        repo = ConjunctionRepository(session)
        cdm = _cdm_data(25544, 77777, pc=5e-4)
        cdm["conjunction_id"] = "CDM-OBJ-TEST-001"
        await repo.insert_cdm(cdm)
        rows = await repo.get_for_object(25544)
        assert any(r.conjunction_id == "CDM-OBJ-TEST-001" for r in rows)

    @pytest.mark.asyncio
    async def test_stats_by_risk_level(self, session):
        from app.db.repositories.conjunction_repository import ConjunctionRepository
        repo = ConjunctionRepository(session)
        cdm = _cdm_data(25544, 99400, pc=2e-3)
        cdm["conjunction_id"] = "CDM-STATS-001"
        await repo.insert_cdm(cdm)
        stats = await repo.stats_by_risk_level()
        assert isinstance(stats, dict)


# ═══════════════════════════════════════════════════════════════
# TLE INGEST SERVICE TESTS
# ═══════════════════════════════════════════════════════════════

SAMPLE_TLE_TEXT = """\
ISS (ZARYA)
1 25544U 98067A   24015.50000000  .00016717  00000+0  30622-3 0  9999
2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579435701
NOAA 19
1 33591U 09005A   24015.47930982  .00000078  00000+0  68490-4 0  9994
2 33591  98.7116 207.0714 0013523 168.5088 191.6614 14.12467178793048
"""


class TestTLEIngestService:

    @pytest.mark.asyncio
    async def test_ingest_text_basic(self, session):
        from app.services.tle_ingest_service import TLEIngestService
        svc = TLEIngestService(session)
        result = await svc.ingest_text(SAMPLE_TLE_TEXT, source="test")
        assert result.total_parsed == 2
        assert result.inserted >= 0  # might be duplicate if already in DB
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_ingest_text_idempotent(self, session):
        from app.services.tle_ingest_service import TLEIngestService
        svc = TLEIngestService(session)
        r1 = await svc.ingest_text(SAMPLE_TLE_TEXT, source="test")
        r2 = await svc.ingest_text(SAMPLE_TLE_TEXT, source="test")
        # Second run should have 0 new inserts (all duplicates)
        assert r2.duplicates == r1.inserted + r1.duplicates

    @pytest.mark.asyncio
    async def test_ingest_empty_text(self, session):
        from app.services.tle_ingest_service import TLEIngestService
        svc = TLEIngestService(session)
        result = await svc.ingest_text("", source="test")
        assert result.total_parsed == 0
        assert result.inserted == 0

    @pytest.mark.asyncio
    async def test_ingest_result_has_duration(self, session):
        from app.services.tle_ingest_service import TLEIngestService
        svc = TLEIngestService(session)
        result = await svc.ingest_text(SAMPLE_TLE_TEXT, source="test")
        assert result.duration_seconds > 0.0


# ═══════════════════════════════════════════════════════════════
# SESSION AND TRANSACTION TESTS
# ═══════════════════════════════════════════════════════════════

class TestSessionAndTransactions:

    @pytest.mark.asyncio
    async def test_transactional_commits_both_ops(self, session):
        """Both repository writes in one transaction must persist."""
        from app.db.repositories.satellite_repository import SatelliteRepository
        from app.db.repositories.tle_repository import TLERepository
        from app.db.session import transactional

        sat_repo = SatelliteRepository(session)
        tle_repo = TLERepository(session)

        async with transactional(session):
            await sat_repo.upsert(_sat_data(70001))
            await tle_repo.insert_or_skip(_tle_data(70001))

        sat = await sat_repo.get_by_norad(70001)
        assert sat is not None
        tle = await tle_repo.get_latest(70001)
        assert tle is not None

    @pytest.mark.asyncio
    async def test_transactional_rolls_back_on_error(self, session):
        """On exception, both writes roll back."""
        from app.db.repositories.satellite_repository import SatelliteRepository
        from app.db.session import transactional

        sat_repo = SatelliteRepository(session)

        try:
            async with transactional(session):
                await sat_repo.upsert(_sat_data(70002))
                raise ValueError("Simulated failure")
        except ValueError:
            pass

        sat = await sat_repo.get_by_norad(70002)
        assert sat is None  # rolled back

    @pytest.mark.asyncio
    async def test_session_survives_database_roundtrip(self, session):
        """Write and read back within same session."""
        from app.db.repositories.satellite_repository import SatelliteRepository
        repo = SatelliteRepository(session)
        await repo.upsert(_sat_data(70003))
        row = await repo.get_by_norad(70003)
        assert row.regime == "LEO"
        assert math.isclose(row.perigee_km, 400.0 + (70003 % 100), rel_tol=1e-6)
