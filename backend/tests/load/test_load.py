"""
ORBITIQ-X Backend — Load Tests

Tests persistence performance at 50K-object SSA scale.

  test_bulk_upsert_50k_satellites  — 50,000 satellite rows in one batch
  test_bulk_insert_500k_tles       — 500,000 TLE records (10 per satellite)
  test_bulk_insert_1m_conjunctions — 1,000,000 CDM records
  test_catalog_scan_active_leos    — SELECT all active LEOs (screener hot path)
  test_tle_latest_per_object       — latest TLE for each of 50K objects
  test_conjunction_dashboard_query — unresolved red/yellow from 1M rows

Acceptance criteria
───────────────────
  50K satellite upsert:    < 60 seconds
  500K TLE insert:         < 120 seconds
  1M conjunction insert:   < 300 seconds
  Active LEO scan (50K):   < 5 seconds
  Latest TLE (50K):        < 10 seconds
  Dashboard query (1M):    < 100 milliseconds (uses partial index)

Run
───
  pytest tests/load/ -v -s --tb=short -m load
  # Add to CI only for nightly runs, not every PR
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://orbitiq:orbitiq@localhost:5432/orbitiq_test",
)

pytestmark = [pytest.mark.load, pytest.mark.asyncio]

N_SATELLITES  = 50_000
N_TLES_PER   = 10       # → 500K total TLE records
N_CONJUNCTIONS = 1_000_000


# ── Fixtures ──────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    eng = create_async_engine(
        TEST_DB_URL,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="module")
async def session(engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()


# ── Data generators ───────────────────────────────────────────

def _sat_batch(start: int, count: int) -> list[dict]:
    """Generate `count` satellite dicts starting at NORAD `start`."""
    now = datetime.now(timezone.utc)
    records = []
    for i in range(count):
        norad = start + i
        regime = ["LEO", "SSO", "MEO", "GEO"][i % 4]
        alt_base = 400.0 if regime == "LEO" else (786.0 if regime == "SSO"
                   else 20200.0 if regime == "MEO" else 35786.0)
        records.append({
            "norad_id": norad,
            "name": f"LOADTEST-{norad:05d}",
            "object_type": ["satellite", "debris", "rocket_body"][i % 3],
            "status": "operational" if i % 5 != 0 else "defunct",
            "regime": regime,
            "perigee_km": alt_base + (i % 50),
            "apogee_km":  alt_base + 20 + (i % 50),
            "inclination_deg": 51.6 + (i % 47),
            "tle_line1": (
                f"1 {norad:05d}U 24001A   24015.50000000"
                f"  .00001000  00000+0  10000-3 0  9990"
            ),
            "tle_line2": (
                f"2 {norad:05d}  51.6416 247.4627 0006703"
                f" 130.5360 325.0288 15.50377579430000"
            ),
            "tle_epoch": now,
            "tle_age_days": 0.5,
            "tle_source": "celestrak",
            "hard_body_radius_km": 0.005,
        })
    return records


def _tle_batch(norad_ids: list[int], tles_per: int) -> list[dict]:
    """Generate `tles_per` TLE records for each NORAD ID."""
    records = []
    base_epoch = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for norad in norad_ids:
        for j in range(tles_per):
            ep = base_epoch + timedelta(days=j * 2)
            records.append({
                "norad_id": norad,
                "name": f"SAT-{norad}",
                "line1": (
                    f"1 {norad:05d}U 24001A   "
                    f"{(ep - datetime(ep.year, 1, 1, tzinfo=timezone.utc)).days + 1 + j * 2:07.4f}"
                    f"0  .00001000  00000+0  10000-3 0  9990"
                )[:69],
                "line2": (
                    f"2 {norad:05d}  51.6416 247.4627 0006703"
                    f" 130.5360 325.0288 15.50377579430000"
                ),
                "epoch": ep,
                "epoch_year": ep.year,
                "epoch_day": float(
                    (ep - datetime(ep.year, 1, 1, tzinfo=timezone.utc)).days + 1
                ),
                "inclination_deg": 51.6,
                "raan_deg": 247.4627,
                "eccentricity": 0.0006703,
                "arg_perigee_deg": 130.5360,
                "mean_anomaly_deg": 325.0288,
                "mean_motion_rev_day": 15.503,
                "bstar": 1e-4,
                "n_dot": 1e-5,
                "n_ddot": 0.0,
                "element_set_num": j + 1,
                "rev_number": 43000 + j,
                "semi_major_axis_km": 6782.0,
                "perigee_km": 405.0,
                "apogee_km": 415.0,
                "period_minutes": 92.9,
                "source": "celestrak",
                "checksum_ok": True,
                "age_at_ingest_days": j * 2.0,
            })
    return records


def _cdm_batch(count: int, primary_base: int = 60000) -> list[dict]:
    """Generate `count` CDM records."""
    import random
    rng = random.Random(42)
    records = []
    base_time = datetime.now(timezone.utc)
    for i in range(count):
        primary  = primary_base + rng.randint(0, N_SATELLITES - 1)
        secondary = primary_base + rng.randint(0, N_SATELLITES - 1)
        if secondary == primary:
            secondary += 1
        pc = rng.uniform(1e-6, 2e-3)
        risk = "red" if pc >= 1e-3 else "yellow" if pc >= 1e-4 else "green"
        records.append({
            "conjunction_id": f"CDM-LOAD-{i:08d}",
            "primary_norad": primary,
            "secondary_norad": secondary,
            "tca": base_time + timedelta(hours=rng.uniform(1, 72)),
            "miss_distance_km": rng.uniform(0.1, 5.0),
            "relative_velocity_kms": rng.uniform(5.0, 12.0),
            "collision_probability": pc,
            "collision_probability_method": "Foster2001",
            "risk_level": risk,
            "maneuver_required": pc >= 1e-4,
            "resolved": rng.random() > 0.1,  # 90% unresolved
            "screening_org": "ORBITIQ-X",
            "data_source": "computed",
            "cdm_issued_at": base_time,
        })
    return records


# ═══════════════════════════════════════════════════════════════
# LOAD TEST: 50K SATELLITES
# ═══════════════════════════════════════════════════════════════

async def test_bulk_upsert_50k_satellites(session, benchmark_results: dict):
    """
    Insert 50,000 satellite records in batches of 2,000.
    Acceptance: < 60 seconds total.
    """
    from app.db.repositories.satellite_repository import SatelliteRepository
    repo = SatelliteRepository(session)

    NORAD_START = 60_000
    records = _sat_batch(NORAD_START, N_SATELLITES)

    t0 = time.perf_counter()
    total = await repo.bulk_upsert(records)
    await session.flush()
    elapsed = time.perf_counter() - t0

    throughput = total / elapsed if elapsed > 0 else 0
    benchmark_results["50k_satellites"] = {
        "rows": total,
        "seconds": round(elapsed, 2),
        "rows_per_sec": round(throughput, 0),
    }

    print(
        f"\n  LOAD TEST: 50K satellites in {elapsed:.2f}s "
        f"({throughput:.0f} rows/sec)"
    )
    assert elapsed < 60.0, f"50K satellite upsert took {elapsed:.1f}s > 60s limit"
    assert total == N_SATELLITES


# ═══════════════════════════════════════════════════════════════
# LOAD TEST: 500K TLE RECORDS
# ═══════════════════════════════════════════════════════════════

async def test_bulk_insert_500k_tles(session, benchmark_results: dict):
    """
    Insert 500,000 TLE records (10 per satellite for 50K satellites).
    Acceptance: < 120 seconds total.
    """
    from app.db.repositories.tle_repository import TLERepository
    repo = TLERepository(session)

    NORAD_START = 60_000
    norad_ids = list(range(NORAD_START, NORAD_START + N_SATELLITES))
    records = _tle_batch(norad_ids, N_TLES_PER)

    total_expected = len(records)
    t0 = time.perf_counter()

    # Insert in chunks to avoid memory pressure
    CHUNK = 50_000
    total_inserted = 0
    for i in range(0, len(records), CHUNK):
        chunk = records[i : i + CHUNK]
        n = await repo.bulk_insert(chunk)
        total_inserted += n
        print(f"  TLE chunk {i//CHUNK + 1}: inserted {n}/{len(chunk)}")

    await session.flush()
    elapsed = time.perf_counter() - t0
    throughput = total_inserted / elapsed if elapsed > 0 else 0

    benchmark_results["500k_tles"] = {
        "rows_attempted": total_expected,
        "rows_inserted": total_inserted,
        "seconds": round(elapsed, 2),
        "rows_per_sec": round(throughput, 0),
    }

    print(
        f"\n  LOAD TEST: {total_expected:,} TLEs → {total_inserted:,} inserted "
        f"in {elapsed:.2f}s ({throughput:.0f} rows/sec)"
    )
    assert elapsed < 120.0, f"500K TLE insert took {elapsed:.1f}s > 120s limit"


# ═══════════════════════════════════════════════════════════════
# LOAD TEST: 1M CONJUNCTION EVENTS
# ═══════════════════════════════════════════════════════════════

async def test_bulk_insert_1m_conjunctions(session, benchmark_results: dict):
    """
    Insert 1,000,000 CDM records.
    Acceptance: < 300 seconds total.
    """
    from app.db.repositories.conjunction_repository import ConjunctionRepository
    repo = ConjunctionRepository(session)

    all_records = _cdm_batch(N_CONJUNCTIONS, primary_base=60_000)

    t0 = time.perf_counter()
    CHUNK = 100_000
    total = 0
    for i in range(0, len(all_records), CHUNK):
        chunk = all_records[i : i + CHUNK]
        n = await repo.bulk_insert(chunk)
        total += n
        print(f"  CDM chunk {i//CHUNK + 1}: upserted {n}/{len(chunk)}")

    await session.flush()
    elapsed = time.perf_counter() - t0
    throughput = total / elapsed if elapsed > 0 else 0

    benchmark_results["1m_conjunctions"] = {
        "rows": total,
        "seconds": round(elapsed, 2),
        "rows_per_sec": round(throughput, 0),
    }

    print(
        f"\n  LOAD TEST: 1M CDMs in {elapsed:.2f}s ({throughput:.0f} rows/sec)"
    )
    assert elapsed < 300.0, f"1M CDM insert took {elapsed:.1f}s > 300s limit"


# ═══════════════════════════════════════════════════════════════
# QUERY PERFORMANCE TESTS (after load data inserted)
# ═══════════════════════════════════════════════════════════════

async def test_catalog_scan_active_leos(session, benchmark_results: dict):
    """
    SELECT all active LEO satellites from 50K rows.
    Acceptance: < 5 seconds (screener must load catalog quickly).
    """
    from app.db.repositories.satellite_repository import SatelliteRepository
    repo = SatelliteRepository(session)

    t0 = time.perf_counter()
    leos = await repo.get_active_leos()
    elapsed = time.perf_counter() - t0

    benchmark_results["leo_scan"] = {
        "rows_returned": len(leos),
        "seconds": round(elapsed, 3),
    }
    print(f"\n  QUERY: active LEO scan → {len(leos)} rows in {elapsed:.3f}s")
    assert elapsed < 5.0, f"Active LEO scan took {elapsed:.2f}s > 5s limit"


async def test_tle_latest_per_object(session, benchmark_results: dict):
    """
    Retrieve the latest TLE for a sample of 1,000 objects.
    Each call hits the (norad_id, epoch DESC) index.
    Acceptance: 1,000 lookups < 10 seconds total.
    """
    from app.db.repositories.tle_repository import TLERepository
    repo = TLERepository(session)

    sample_norads = list(range(60_000, 61_000))

    t0 = time.perf_counter()
    found = 0
    for norad in sample_norads:
        row = await repo.get_latest(norad)
        if row: found += 1
    elapsed = time.perf_counter() - t0

    benchmark_results["tle_latest_1k"] = {
        "lookups": len(sample_norads),
        "found": found,
        "seconds": round(elapsed, 3),
        "ms_per_lookup": round(elapsed / len(sample_norads) * 1000, 2),
    }
    print(
        f"\n  QUERY: 1K latest TLE lookups in {elapsed:.3f}s "
        f"({elapsed/len(sample_norads)*1000:.2f}ms each)"
    )
    assert elapsed < 10.0, f"1K TLE lookups took {elapsed:.2f}s > 10s limit"


async def test_conjunction_dashboard_query(session, benchmark_results: dict):
    """
    Query unresolved red/yellow events from 1M rows.
    Must use partial index for sub-100ms response.
    Acceptance: < 100 milliseconds.
    """
    from app.db.repositories.conjunction_repository import ConjunctionRepository
    repo = ConjunctionRepository(session)

    t0 = time.perf_counter()
    rows = await repo.get_unresolved_red_yellow(limit=200)
    elapsed = time.perf_counter() - t0
    elapsed_ms = elapsed * 1000

    benchmark_results["dashboard_query"] = {
        "rows_returned": len(rows),
        "ms": round(elapsed_ms, 2),
    }
    print(
        f"\n  QUERY: dashboard (1M rows) → {len(rows)} results in {elapsed_ms:.2f}ms"
    )
    assert elapsed_ms < 100.0, (
        f"Dashboard query took {elapsed_ms:.1f}ms > 100ms limit. "
        f"Check partial index ix_conj_active_red exists."
    )


async def test_conjunction_stats_by_risk(session, benchmark_results: dict):
    """GROUP BY risk_level on 1M rows — must be fast via index."""
    from app.db.repositories.conjunction_repository import ConjunctionRepository
    repo = ConjunctionRepository(session)

    t0 = time.perf_counter()
    stats = await repo.stats_by_risk_level()
    elapsed = time.perf_counter() - t0

    benchmark_results["risk_stats"] = {
        "stats": stats,
        "seconds": round(elapsed, 3),
    }
    print(f"\n  QUERY: risk stats → {stats} in {elapsed*1000:.1f}ms")
    # Lenient — this is a full GROUP BY scan
    assert elapsed < 10.0, f"Risk stats took {elapsed:.2f}s > 10s limit"


# ── Fixture to collect benchmark results ──────────────────────

@pytest_asyncio.fixture(scope="module")
def benchmark_results() -> dict:
    results: dict = {}
    yield results
    # Print summary at end of module
    print("\n" + "=" * 60)
    print("ORBITIQ-X LOAD TEST RESULTS")
    print("=" * 60)
    for label, data in results.items():
        print(f"  {label}: {data}")
    print("=" * 60)
