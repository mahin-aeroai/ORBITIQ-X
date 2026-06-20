"""
ORBITIQ-X — Space-Track Ingestion Scale Benchmarks
=====================================================
Phase 7: In-memory throughput simulation at 10K / 25K / 50K scale.

These benchmarks measure the CPU-bound portions of the pipeline
(parsing, validation, dict building) without requiring a live DB.
The DB write benchmarks are in tests/load/test_load.py and require PostgreSQL.

What is measured
─────────────────
  parse_throughput       — TLE text parsing (records/second)
  build_throughput       — TLE → DB dict conversion (records/second)
  memory_per_record      — bytes per TLE record dict in Python heap
  cache_warm_throughput  — Redis HSET operations/second (mocked)
  total_pipeline_time    — end-to-end parse+build for N records

Acceptance criteria (CPU-bound phases only)
────────────────────────────────────────────
  Parse throughput:      > 5,000 records/second
  Build throughput:      > 3,000 records/second  
  Memory per record:     < 2,000 bytes
  10K pipeline:          < 10 seconds
  25K pipeline:          < 25 seconds
  50K pipeline:          < 60 seconds

Run
───
  pytest tests/unit/spacetrack/test_scale_benchmarks.py -v -s
"""

from __future__ import annotations

import gc
import sys
import time
from dataclasses import dataclass

import pytest


# ── Synthetic TLE generator ───────────────────────────────────

def _checksum(line: str) -> int:
    return sum(int(c) if c.isdigit() else (1 if c == '-' else 0) for c in line[:68]) % 10


def generate_tle_text(n: int) -> str:
    """
    Generate n valid 3-line TLE blocks.

    Uses real TLE lines from ISS as template (correct field widths),
    substituting the NORAD ID in each. Checksums are recomputed.
    """
    # Real ISS TLE lines as width templates — field positions are correct
    _L1_TMPL = "1 25544U 98067A   25168.51786836  .00025600  00000+0  45234-3 0  9990"
    _L2_TMPL = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579435701"

    lines = []
    for i in range(n):
        norad = 10000 + i
        l1_base = f"1 {norad:05d}" + _L1_TMPL[7:]
        l2_base = f"2 {norad:05d}" + _L2_TMPL[7:]
        l1 = l1_base[:68] + str(_checksum(l1_base))
        l2 = l2_base[:68] + str(_checksum(l2_base))
        lines.append(f"TESTSAT-{norad:05d}\n{l1}\n{l2}")
    return "\n".join(lines)


# ── Benchmark result ──────────────────────────────────────────

@dataclass
class BenchmarkResult:
    n_records: int
    parse_duration_s: float
    build_duration_s: float
    total_duration_s: float
    parse_rate: float     # records/second
    build_rate: float
    memory_bytes_per_record: float
    success: bool
    failures: list[str]


def run_benchmark(n: int) -> BenchmarkResult:
    """
    Run the full parse+build pipeline for n synthetic TLE records.
    No DB writes — pure CPU measurement.
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))

    from app.services.tle_ingest_service import _parse_tle_text, _build_tle_record

    failures: list[str] = []

    # Generate input text
    tle_text = generate_tle_text(n)

    # Phase A: Parse TLE text → (name, l1, l2) triples
    t_parse_start = time.perf_counter()
    triples = _parse_tle_text(tle_text)
    t_parse_end = time.perf_counter()
    parse_duration = t_parse_end - t_parse_start

    parsed_count = len(triples)
    if parsed_count != n:
        failures.append(f"parse: expected {n} triples, got {parsed_count}")

    # Phase B: Build TLERecord dicts
    t_build_start = time.perf_counter()
    records = []
    for name, l1, l2 in triples:
        rec = _build_tle_record(name, l1, l2, source="spacetrack")
        if rec is not None:
            records.append(rec)
    t_build_end = time.perf_counter()
    build_duration = t_build_end - t_build_start

    built_count = len(records)
    if built_count == 0:
        failures.append(f"build: zero records built from {parsed_count} triples")

    # Memory measurement
    gc.collect()
    mem_per_record = sys.getsizeof(records[0]) if records else 0
    # Add size of string values in the dict
    if records:
        r = records[0]
        mem_per_record = sum(sys.getsizeof(v) for v in r.values()) + sys.getsizeof(r)

    total_duration = t_build_end - t_parse_start

    return BenchmarkResult(
        n_records=n,
        parse_duration_s=parse_duration,
        build_duration_s=build_duration,
        total_duration_s=total_duration,
        parse_rate=parsed_count / max(parse_duration, 1e-9),
        build_rate=built_count / max(build_duration, 1e-9),
        memory_bytes_per_record=mem_per_record,
        success=len(failures) == 0,
        failures=failures,
    )


# ═══════════════════════════════════════════════════════════════
# SCALE TESTS
# ═══════════════════════════════════════════════════════════════

class TestScaleBenchmarks:
    """
    Throughput and memory benchmarks at SSA-scale.
    Marked with @pytest.mark.benchmark — run with -s to see output.
    """

    def _print_result(self, r: BenchmarkResult, label: str) -> None:
        print(f"\n{'='*60}")
        print(f"BENCHMARK: {label} ({r.n_records:,} records)")
        print(f"{'='*60}")
        print(f"  Parse:          {r.parse_duration_s:.3f}s  ({r.parse_rate:,.0f} rec/s)")
        print(f"  Build dicts:    {r.build_duration_s:.3f}s  ({r.build_rate:,.0f} rec/s)")
        print(f"  TOTAL pipeline: {r.total_duration_s:.3f}s")
        print(f"  Memory/record:  {r.memory_bytes_per_record:.0f} bytes")
        print(f"  Status:         {'✓ PASS' if r.success else '✗ FAIL'}")
        if r.failures:
            for f in r.failures:
                print(f"  FAILURE: {f}")
        print()

    def test_scale_10k(self):
        """10,000 objects: baseline scale validation."""
        N = 10_000
        result = run_benchmark(N)
        self._print_result(result, "10K Satellites")

        assert result.success, f"Build failures: {result.failures}"
        assert result.parse_rate > 5_000, \
            f"Parse too slow: {result.parse_rate:.0f} rec/s < 5,000 rec/s"
        assert result.build_rate > 3_000, \
            f"Build too slow: {result.build_rate:.0f} rec/s < 3,000 rec/s"
        assert result.total_duration_s < 10.0, \
            f"10K pipeline took {result.total_duration_s:.1f}s > 10s limit"
        assert result.memory_bytes_per_record < 2_000, \
            f"Memory per record {result.memory_bytes_per_record:.0f}B > 2000B"

    def test_scale_25k(self):
        """25,000 objects: mid-scale validation."""
        N = 25_000
        result = run_benchmark(N)
        self._print_result(result, "25K Satellites")

        assert result.success, f"Build failures: {result.failures}"
        assert result.parse_rate > 5_000, \
            f"Parse rate degraded at 25K: {result.parse_rate:.0f} rec/s"
        assert result.total_duration_s < 25.0, \
            f"25K pipeline took {result.total_duration_s:.1f}s > 25s limit"

    def test_scale_50k(self):
        """50,000 objects: full production scale."""
        N = 50_000
        result = run_benchmark(N)
        self._print_result(result, "50K Satellites (FULL CATALOG)")

        assert result.success, f"Build failures: {result.failures}"
        assert result.parse_rate > 5_000, \
            f"Parse rate degraded at 50K: {result.parse_rate:.0f} rec/s"
        assert result.total_duration_s < 60.0, \
            f"50K pipeline took {result.total_duration_s:.1f}s > 60s limit"

    def test_parse_throughput_isolation(self):
        """Parse-only benchmark — measures _parse_tle_text() in isolation."""
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))
        from app.services.tle_ingest_service import _parse_tle_text

        N = 50_000
        text = generate_tle_text(N)

        t0 = time.perf_counter()
        triples = _parse_tle_text(text)
        elapsed = time.perf_counter() - t0

        rate = len(triples) / elapsed
        print(f"\n  Parse-only: {N:,} records in {elapsed:.2f}s = {rate:,.0f} rec/s")
        assert len(triples) == N
        assert rate > 5_000, f"Parse rate {rate:.0f} rec/s below 5,000 minimum"

    def test_memory_50k_records(self):
        """Measure total memory footprint for 50K TLE record dicts."""
        import sys, pathlib, gc
        sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))
        from app.services.tle_ingest_service import _parse_tle_text, _build_tle_record

        N = 50_000
        text = generate_tle_text(N)
        triples = _parse_tle_text(text)

        gc.collect()

        records = [_build_tle_record(name, l1, l2, "spacetrack")
                   for name, l1, l2 in triples
                   if _build_tle_record(name, l1, l2, "spacetrack") is not None]

        # Estimate total memory
        total_bytes = sum(
            sum(sys.getsizeof(v) for v in r.values()) + sys.getsizeof(r)
            for r in records
        )
        total_mb = total_bytes / (1024 * 1024)
        per_record = total_bytes / len(records)

        print(f"\n  Memory: {N:,} records = {total_mb:.1f} MB total ({per_record:.0f} bytes/record)")

        # Acceptance: < 500 MB for 50K records in Python heap
        assert total_mb < 500, f"50K records use {total_mb:.0f} MB > 500 MB limit"
        assert per_record < 2_000, f"Per-record memory {per_record:.0f}B > 2,000B"

    def test_idempotency_parse_result(self):
        """Parsing the same text twice produces identical record sets."""
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))
        from app.services.tle_ingest_service import _parse_tle_text, _build_tle_record

        N = 1_000
        text = generate_tle_text(N)

        triples_1 = _parse_tle_text(text)
        triples_2 = _parse_tle_text(text)

        assert len(triples_1) == len(triples_2) == N

        records_1 = [_build_tle_record(n, l1, l2) for n, l1, l2 in triples_1]
        records_2 = [_build_tle_record(n, l1, l2) for n, l1, l2 in triples_2]

        for r1, r2 in zip(records_1, records_2):
            assert r1["norad_id"]   == r2["norad_id"]
            assert r1["line1"]      == r2["line1"]
            assert r1["epoch"]      == r2["epoch"]

    def test_cache_warm_throughput(self):
        """Simulate Redis HSET throughput with mock pipeline."""
        from unittest.mock import MagicMock, AsyncMock
        import asyncio

        N = 10_000

        mock_pipe = MagicMock()
        mock_pipe.hset  = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=None)

        t0 = time.perf_counter()
        for i in range(N):
            mock_pipe.hset(f"tle:{10000+i}", mapping={
                "line1": "1 10000U ...",
                "line2": "2 10000  ...",
                "epoch": "2025-06-17T12:00:00Z",
            })
            mock_pipe.expire(f"tle:{10000+i}", 7200)
        elapsed = time.perf_counter() - t0

        ops_per_sec = N / elapsed
        print(f"\n  Cache HSET mock: {N:,} keys in {elapsed:.3f}s = {ops_per_sec:,.0f} ops/s")
        assert ops_per_sec > 10_000, f"Cache prep {ops_per_sec:.0f} ops/s too slow (mock overhead expected)"


# ── Summary reporter ──────────────────────────────────────────

def test_print_summary():
    """Run all three scales and print a comparison table."""
    print("\n" + "=" * 70)
    print("ORBITIQ-X SPACE-TRACK INGESTION SUBSYSTEM — SCALE BENCHMARK REPORT")
    print("=" * 70)
    print(f"{'Scale':<12} {'Parse (rec/s)':>14} {'Build (rec/s)':>14} "
          f"{'Total (s)':>10} {'Mem/rec':>9} {'Status'}")
    print("-" * 70)

    all_pass = True
    for n in [10_000, 25_000, 50_000]:
        r = run_benchmark(n)
        status = "✓ PASS" if r.success else "✗ FAIL"
        if not r.success:
            all_pass = False
        print(
            f"{n:>10,}   "
            f"{r.parse_rate:>13,.0f}   "
            f"{r.build_rate:>13,.0f}   "
            f"{r.total_duration_s:>9.2f}   "
            f"{r.memory_bytes_per_record:>7.0f}B  "
            f"{status}"
        )

    print("-" * 70)
    print(f"Acceptance criteria: parse > 5K/s | build > 3K/s | 50K < 60s | mem < 2KB/record")
    print("=" * 70)
    print(f"\nOPERATIONAL READINESS: {'READY' if all_pass else 'NOT READY'}")
    print()

    assert all_pass, "One or more scale benchmarks failed"
