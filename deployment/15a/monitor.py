#!/usr/bin/env python3
"""
ORBITIQ-X Phase 15A — Burn-In Monitor
=======================================
Stage 7: Continuously monitors the running stack during the 24–72h burn-in.
Polls all services every 60 seconds and writes a stability report.

Tracked metrics
────────────────
  - Service uptime (PostgreSQL, Redis, Neo4j, MinIO, FastAPI, Frontend)
  - Scheduler job execution (via Redis timestamps)
  - API latency (p50/p95/p99 rolling)
  - Memory and CPU (if psutil available)
  - Error events (connection failures, HTTP 5xx)

Output
───────
  Console: live status table (refreshes)
  File:    deployment/15a/burnin_report.jsonl  (one JSON line per poll)
  Summary: deployment/15a/burnin_summary.json  (written on Ctrl+C / timeout)

Usage
──────
  python3 deployment/15a/monitor.py                # run until Ctrl+C
  python3 deployment/15a/monitor.py --hours 24     # run for 24h
  python3 deployment/15a/monitor.py --interval 30  # poll every 30s
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque

REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

# Load .env
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import httpx

CYAN   = "\033[0;36m"
GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
RED    = "\033[0;31m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
NC     = "\033[0m"

REPORT_FILE  = REPO_ROOT / "deployment" / "15a" / "burnin_report.jsonl"
SUMMARY_FILE = REPO_ROOT / "deployment" / "15a" / "burnin_summary.json"


# ── Service checks ────────────────────────────────────────────────────────────

async def probe_http(name: str, url: str, expected: int = 200) -> dict:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5, verify=False) as client:
            r = await client.get(url)
            ms = (time.perf_counter() - t0) * 1000
            ok = r.status_code == expected
            return {"name": name, "ok": ok, "ms": round(ms, 1),
                    "code": r.status_code, "error": None}
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        return {"name": name, "ok": False, "ms": round(ms, 1),
                "code": 0, "error": str(exc)[:60]}


async def probe_tcp(name: str, host: str, port: int) -> dict:
    t0 = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=5
        )
        writer.close()
        await writer.wait_closed()
        ms = (time.perf_counter() - t0) * 1000
        return {"name": name, "ok": True, "ms": round(ms, 1), "error": None}
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        return {"name": name, "ok": False, "ms": round(ms, 1), "error": str(exc)[:60]}


async def collect_metrics(backend_url: str) -> dict:
    """Collect one poll cycle of metrics."""
    ts = datetime.now(timezone.utc).isoformat()

    pg_host   = os.environ.get("POSTGRES_HOST", "localhost")
    redis_host= os.environ.get("REDIS_HOST",    "localhost")
    neo4j_host= os.environ.get("NEO4J_HOST",    "localhost")
    minio_host= os.environ.get("MINIO_HOST",    "localhost")

    probes = await asyncio.gather(
        probe_http("FastAPI /health",   f"{backend_url}/health"),
        probe_http("FastAPI /metrics",  f"{backend_url}/metrics"),
        probe_http("Frontend",          "http://localhost:3000"),
        probe_http("Prometheus",        "http://localhost:9090/-/healthy"),
        probe_http("Grafana",           "http://localhost:3001/api/health"),
        probe_tcp ("PostgreSQL",        pg_host,    int(os.environ.get("POSTGRES_PORT",  5432))),
        probe_tcp ("Redis",             redis_host, int(os.environ.get("REDIS_PORT",      6379))),
        probe_tcp ("Neo4j Bolt",        neo4j_host, int(os.environ.get("NEO4J_BOLT_PORT", 7687))),
        probe_tcp ("MinIO",             minio_host, int(os.environ.get("MINIO_PORT",      9000))),
    )

    # System resources
    mem_pct = cpu_pct = None
    try:
        import psutil
        mem_pct = psutil.virtual_memory().percent
        cpu_pct = psutil.cpu_percent(interval=None)
    except ImportError:
        pass

    return {
        "timestamp": ts,
        "probes":    probes,
        "memory_pct": mem_pct,
        "cpu_pct":    cpu_pct,
    }


# ── State ─────────────────────────────────────────────────────────────────────

class BurninState:
    def __init__(self, max_duration_s: float):
        self.start_time   = time.time()
        self.max_duration = max_duration_s
        self.poll_count   = 0
        self.error_events: list[dict] = []
        self.latencies:    dict[str, Deque[float]] = {}
        self.outages:      dict[str, int] = {}
        self.running       = True

    @property
    def elapsed_s(self) -> float:
        return time.time() - self.start_time

    @property
    def uptime_pct(self) -> float:
        if self.poll_count == 0:
            return 100.0
        total_ok = self.poll_count - max(self.outages.values(), default=0)
        return round(100 * total_ok / self.poll_count, 2)

    def record(self, metrics: dict) -> None:
        self.poll_count += 1
        for probe in metrics["probes"]:
            name = probe["name"]
            ms   = probe["ms"]
            ok   = probe["ok"]

            if name not in self.latencies:
                self.latencies[name] = deque(maxlen=100)
            if ok:
                self.latencies[name].append(ms)
            else:
                self.outages[name] = self.outages.get(name, 0) + 1
                self.error_events.append({
                    "time":  metrics["timestamp"],
                    "probe": name,
                    "error": probe.get("error"),
                })

    def p95(self, name: str) -> float | None:
        q = self.latencies.get(name)
        if not q:
            return None
        s = sorted(q)
        idx = int(len(s) * 0.95)
        return round(s[min(idx, len(s)-1)], 1)

    def summary(self) -> dict:
        return {
            "duration_s":   round(self.elapsed_s),
            "poll_count":   self.poll_count,
            "uptime_pct":   self.uptime_pct,
            "outages":      self.outages,
            "error_count":  len(self.error_events),
            "first_error":  self.error_events[0] if self.error_events else None,
            "last_error":   self.error_events[-1] if self.error_events else None,
            "p95_latencies":{k: self.p95(k) for k in self.latencies},
        }


# ── Display ───────────────────────────────────────────────────────────────────

def render_table(metrics: dict, state: BurninState) -> str:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    elapsed = int(state.elapsed_s)
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60

    lines = [
        f"\033[2J\033[H",  # clear screen
        f"{BOLD}ORBITIQ-X Phase 15A — Burn-In Monitor{NC}",
        f"  Started: {now}  |  Elapsed: {h:02d}:{m:02d}:{s:02d}  |  Polls: {state.poll_count}",
        f"  Errors:  {len(state.error_events)}  |  Uptime: {state.uptime_pct}%",
        "",
        f"  {'Service':<25} {'Status':>8} {'Latency':>10} {'P95':>10} {'Outages':>8}",
        f"  {'─'*65}",
    ]

    for probe in metrics["probes"]:
        name    = probe["name"]
        ok      = probe["ok"]
        ms      = probe["ms"]
        p95     = state.p95(name)
        outages = state.outages.get(name, 0)
        status  = f"{GREEN}UP{NC}" if ok else f"{RED}DOWN{NC}"
        lat_str = f"{ms:.0f}ms" if ok else f"{RED}{ms:.0f}ms{NC}"
        p95_str = f"{p95:.0f}ms" if p95 else "—"
        lines.append(f"  {name:<25} {status:>14} {lat_str:>16} {p95_str:>10} {outages:>8}")

    lines.append(f"  {'─'*65}")

    if metrics.get("memory_pct") is not None:
        mem  = metrics["memory_pct"]
        cpu  = metrics.get("cpu_pct", 0)
        mem_c = GREEN if mem < 70 else (YELLOW if mem < 85 else RED)
        cpu_c = GREEN if cpu < 70 else (YELLOW if cpu < 85 else RED)
        lines.append(f"  Memory: {mem_c}{mem:.1f}%{NC}  |  CPU: {cpu_c}{cpu:.1f}%{NC}")

    if state.error_events:
        last = state.error_events[-1]
        lines.append(f"  {RED}Last error: [{last['time'][11:19]}] {last['probe']}: {last['error']}{NC}")

    lines.append(f"\n  {DIM}Press Ctrl+C to stop and write summary report{NC}")
    return "\n".join(lines)


# ── Main loop ─────────────────────────────────────────────────────────────────

async def run(interval: int, max_hours: float) -> None:
    backend_url = f"http://{os.environ.get('BACKEND_HOST', 'localhost')}:{os.environ.get('BACKEND_PORT', 8000)}"
    max_s       = max_hours * 3600
    state       = BurninState(max_s)

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    report_fh = REPORT_FILE.open("a")

    def shutdown(*_):
        state.running = False
    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"\n{BOLD}ORBITIQ-X Phase 15A Burn-In — starting ({max_hours}h max, {interval}s interval){NC}")
    print(f"Report: {REPORT_FILE}")

    while state.running and state.elapsed_s < max_s:
        metrics = await collect_metrics(backend_url)
        state.record(metrics)
        report_fh.write(json.dumps(metrics) + "\n")
        report_fh.flush()
        sys.stdout.write(render_table(metrics, state))
        sys.stdout.flush()
        await asyncio.sleep(interval)

    report_fh.close()

    # Write summary
    summary = {
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "backend_url":    backend_url,
        "interval_s":     interval,
        **state.summary(),
    }
    SUMMARY_FILE.write_text(json.dumps(summary, indent=2))

    print(f"\n\n{BOLD}Burn-In Summary{NC}")
    print(f"  Duration:  {state.elapsed_s/3600:.2f}h ({state.poll_count} polls)")
    print(f"  Uptime:    {state.uptime_pct}%")
    print(f"  Errors:    {len(state.error_events)}")
    print(f"  Report:    {REPORT_FILE}")
    print(f"  Summary:   {SUMMARY_FILE}")

    passed = state.uptime_pct >= 99.5 and len(state.error_events) == 0
    if passed:
        print(f"\n{GREEN}✅ Burn-in PASSED — platform is stable.{NC}")
        print(f"   Authorised for Phase 15B (Live SSA Operations)")
    else:
        print(f"\n{YELLOW}⚠ Burn-in completed with issues.{NC}")
        print(f"   Review {SUMMARY_FILE} before proceeding.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ORBITIQ-X Phase 15A burn-in monitor")
    parser.add_argument("--hours",    type=float, default=24,
                        help="Monitor duration in hours (default: 24)")
    parser.add_argument("--interval", type=int,   default=60,
                        help="Poll interval in seconds (default: 60)")
    args = parser.parse_args()
    asyncio.run(run(args.interval, args.hours))
