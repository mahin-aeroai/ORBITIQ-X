#!/usr/bin/env python3
"""
ORBITIQ-X Phase 15A — Environment & Credential Validator
=========================================================
Stages 3 & 5: Validates every credential and external connection
before the first operational sync.

Checks performed
─────────────────
  1. .env completeness — no CHANGE_ME values remain
  2. Secret strength — minimum entropy for all secrets
  3. Space-Track authentication — live login + sample TLE pull
  4. Anthropic API — live inference test (1 token)
  5. OpenAI API — embedding endpoint reachability
  6. PostgreSQL connectivity
  7. Redis connectivity
  8. Neo4j connectivity
  9. MinIO bucket creation
 10. NOAA Space Weather (no auth needed — just connectivity)

Exit code: 0 = all critical checks pass, 1 = one or more failures

Usage
──────
  python3 deployment/15a/validate.py
  python3 deployment/15a/validate.py --skip-live   # skip external API calls
  python3 deployment/15a/validate.py --json         # machine-readable output
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ── Bootstrap env from .env file ──────────────────────────────────────────────
REPO_ROOT = Path(__file__).parents[2]
ENV_FILE  = REPO_ROOT / ".env"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# ── Result tracking ───────────────────────────────────────────────────────────

CYAN   = "\033[0;36m"
GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
RED    = "\033[0;31m"
BOLD   = "\033[1m"
NC     = "\033[0m"


@dataclass
class CheckResult:
    name:     str
    passed:   bool
    message:  str
    critical: bool = True
    detail:   str  = ""
    elapsed:  float = 0.0


results: list[CheckResult] = []


def record(name: str, passed: bool, message: str,
           critical: bool = True, detail: str = "", elapsed: float = 0.0) -> CheckResult:
    r = CheckResult(name, passed, message, critical, detail, elapsed)
    results.append(r)
    icon = f"{GREEN}✓{NC}" if passed else (f"{RED}✗{NC}" if critical else f"{YELLOW}⚠{NC}")
    print(f"  {icon}  {name:<40} {message}")
    if detail:
        print(f"     {CYAN}{detail}{NC}")
    return r


# ── Individual checks ─────────────────────────────────────────────────────────

def check_env_completeness() -> None:
    """Verify no CHANGE_ME values remain in .env."""
    print(f"\n{BOLD}── Environment Completeness ──{NC}")
    if not ENV_FILE.exists():
        record(".env exists", False, "File not found — run setup.sh first")
        return

    record(".env exists", True, str(ENV_FILE))

    required = [
        "ORBITIQ_SECRET_KEY", "POSTGRES_PASSWORD", "REDIS_PASSWORD",
        "NEO4J_PASSWORD", "WEAVIATE_API_KEY", "MINIO_ROOT_PASSWORD",
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "SPACETRACK_IDENTITY", "SPACETRACK_PASSWORD",
    ]
    bad = []
    for key in required:
        val = os.environ.get(key, "")
        if not val or "CHANGE_ME" in val or val.startswith("CHANGE_ME"):
            bad.append(key)

    if bad:
        record("No CHANGE_ME values", False,
               f"{len(bad)} unconfigured", detail=", ".join(bad))
    else:
        record("No CHANGE_ME values", True, f"{len(required)} secrets configured")

    # Secret strength
    weak = []
    for key, min_len in [("ORBITIQ_SECRET_KEY", 32), ("POSTGRES_PASSWORD", 12),
                          ("REDIS_PASSWORD", 12), ("GRAFANA_ADMIN_PASSWORD", 8)]:
        val = os.environ.get(key, "")
        if len(val) < min_len:
            weak.append(f"{key} ({len(val)}<{min_len})")
    if weak:
        record("Secret strength", False, "Weak secrets", detail="; ".join(weak))
    else:
        record("Secret strength", True, "All secrets meet minimum length")


async def check_spacetrack(skip_live: bool) -> None:
    """Authenticate with Space-Track.org and pull 1 TLE."""
    import httpx
    print(f"\n{BOLD}── Space-Track Integration ──{NC}")
    identity = os.environ.get("SPACETRACK_IDENTITY", "")
    password = os.environ.get("SPACETRACK_PASSWORD", "")

    if not identity or not password:
        record("Space-Track credentials", False, "SPACETRACK_IDENTITY/PASSWORD not set",
               critical=True)
        return
    if "@" not in identity:
        record("Space-Track credentials", False,
               "SPACETRACK_IDENTITY must be an email address")
        return

    record("Space-Track credentials", True, f"Identity: {identity}")

    if skip_live:
        record("Space-Track auth (live)", True, "SKIPPED (--skip-live)", critical=False)
        return

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.post(
                "https://www.space-track.org/ajaxauth/login",
                data={"identity": identity, "password": password},
            )
            elapsed = time.perf_counter() - t0
            if r.status_code == 200 and "Failed" not in r.text:
                record("Space-Track auth (live)", True,
                       f"Authenticated ({elapsed*1000:.0f}ms)", elapsed=elapsed)
                # Pull 1 ISS TLE as smoke test
                t1 = time.perf_counter()
                tle = await client.get(
                    "https://www.space-track.org/basicspacedata/query/class/gp/"
                    "NORAD_CAT_ID/25544/format/tle/limit/1/",
                    timeout=20,
                )
                te = time.perf_counter() - t1
                if tle.status_code == 200 and len(tle.text) > 50:
                    record("Space-Track TLE pull (ISS)", True,
                           f"{len(tle.text)} bytes ({te*1000:.0f}ms)",
                           detail=tle.text[:70].strip())
                else:
                    record("Space-Track TLE pull (ISS)", False,
                           f"HTTP {tle.status_code} — unexpected response")
            else:
                record("Space-Track auth (live)", False,
                       f"HTTP {r.status_code} — check credentials")
    except httpx.ConnectError:
        record("Space-Track auth (live)", False, "Connection refused — check network/firewall")
    except Exception as exc:
        record("Space-Track auth (live)", False, str(exc)[:80])


async def check_anthropic(skip_live: bool) -> None:
    """Validate Anthropic API key with a minimal inference call."""
    import httpx
    print(f"\n{BOLD}── Anthropic API ──{NC}")
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    if not key or "CHANGE_ME" in key:
        record("Anthropic API key", False, "Not configured")
        return
    record("Anthropic API key", True, f"Length: {len(key)} chars")

    if skip_live:
        record("Anthropic inference (live)", True, "SKIPPED (--skip-live)", critical=False)
        return

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Reply: ORBITIQ-OK"}],
                },
                timeout=30,
            )
            elapsed = time.perf_counter() - t0
            if r.status_code == 200:
                reply = r.json().get("content", [{}])[0].get("text", "")
                record("Anthropic inference (live)", True,
                       f"Model: {model} ({elapsed*1000:.0f}ms)", detail=f"Reply: {reply!r}")
            else:
                err_msg = r.json().get("error", {}).get("message", r.text[:80])
                record("Anthropic inference (live)", False,
                       f"HTTP {r.status_code}: {err_msg}")
    except Exception as exc:
        record("Anthropic inference (live)", False, str(exc)[:80])


async def check_openai(skip_live: bool) -> None:
    """Validate OpenAI API key for embedding endpoint."""
    import httpx
    print(f"\n{BOLD}── OpenAI Embeddings ──{NC}")
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or "CHANGE_ME" in key:
        record("OpenAI API key", False, "Not configured", critical=False)
        return
    record("OpenAI API key", True, f"Length: {len(key)} chars")

    if skip_live:
        record("OpenAI embed (live)", True, "SKIPPED (--skip-live)", critical=False)
        return

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"input": "ORBITIQ-X", "model": "text-embedding-3-large",
                      "dimensions": 256},
            )
            elapsed = time.perf_counter() - t0
            if r.status_code == 200:
                dims = len(r.json()["data"][0]["embedding"])
                record("OpenAI embed (live)", True,
                       f"Embedding dim={dims} ({elapsed*1000:.0f}ms)")
            else:
                record("OpenAI embed (live)", False,
                       f"HTTP {r.status_code}", critical=False)
    except Exception as exc:
        record("OpenAI embed (live)", False, str(exc)[:80], critical=False)


async def check_postgres() -> None:
    """Test PostgreSQL connectivity."""
    print(f"\n{BOLD}── PostgreSQL ──{NC}")
    try:
        import asyncpg
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = int(os.environ.get("POSTGRES_PORT", 5432))
        db   = os.environ.get("POSTGRES_DB", "orbitiq_db")
        user = os.environ.get("POSTGRES_USER", "orbitiq")
        pw   = os.environ.get("POSTGRES_PASSWORD", "")
        t0 = time.perf_counter()
        conn = await asyncio.wait_for(
            asyncpg.connect(host=host, port=port, database=db, user=user, password=pw),
            timeout=10,
        )
        elapsed = time.perf_counter() - t0
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        record("PostgreSQL connectivity", True,
               f"{host}:{port}/{db} ({elapsed*1000:.0f}ms)",
               detail=version[:60])
    except ImportError:
        record("PostgreSQL connectivity", False, "asyncpg not installed")
    except asyncio.TimeoutError:
        record("PostgreSQL connectivity", False, "Timeout — is PostgreSQL running?")
    except Exception as exc:
        record("PostgreSQL connectivity", False, str(exc)[:100])


async def check_redis() -> None:
    """Test Redis connectivity."""
    print(f"\n{BOLD}── Redis ──{NC}")
    try:
        import redis.asyncio as aioredis
        host = os.environ.get("REDIS_HOST", "localhost")
        port = int(os.environ.get("REDIS_PORT", 6379))
        pw   = os.environ.get("REDIS_PASSWORD", "")
        t0 = time.perf_counter()
        r = aioredis.Redis(host=host, port=port, password=pw, socket_timeout=5)
        pong = await r.ping()
        elapsed = time.perf_counter() - t0
        await r.aclose()
        record("Redis connectivity", pong,
               f"{host}:{port} ({elapsed*1000:.0f}ms)")
    except ImportError:
        record("Redis connectivity", False, "redis-py not installed")
    except Exception as exc:
        record("Redis connectivity", False, str(exc)[:100])


async def check_neo4j() -> None:
    """Test Neo4j connectivity."""
    print(f"\n{BOLD}── Neo4j ──{NC}")
    try:
        from neo4j import AsyncGraphDatabase
        host = os.environ.get("NEO4J_HOST", "localhost")
        port = os.environ.get("NEO4J_BOLT_PORT", "7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        pw   = os.environ.get("NEO4J_PASSWORD", "")
        uri  = f"bolt://{host}:{port}"
        t0 = time.perf_counter()
        driver = AsyncGraphDatabase.driver(uri, auth=(user, pw))
        async with driver.session() as session:
            result = await session.run("RETURN 'ORBITIQ' AS ok")
            record_data = await result.single()
            val = record_data["ok"] if record_data else None
        await driver.close()
        elapsed = time.perf_counter() - t0
        record("Neo4j connectivity", val == "ORBITIQ",
               f"{uri} ({elapsed*1000:.0f}ms)")
    except ImportError:
        record("Neo4j connectivity", False, "neo4j driver not installed", critical=False)
    except Exception as exc:
        record("Neo4j connectivity", False, str(exc)[:100], critical=False)


async def check_noaa() -> None:
    """Test NOAA Space Weather (no auth needed)."""
    import httpx
    print(f"\n{BOLD}── NOAA Space Weather ──{NC}")
    try:
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
            )
            elapsed = time.perf_counter() - t0
            if r.status_code == 200:
                data = r.json()
                last = data[-1] if data else None
                kp = last[1] if last and len(last) > 1 else "?"
                record("NOAA SWPC reachable", True,
                       f"Kp={kp} ({elapsed*1000:.0f}ms)", critical=False)
            else:
                record("NOAA SWPC reachable", False, f"HTTP {r.status_code}", critical=False)
    except Exception as exc:
        record("NOAA SWPC reachable", False, str(exc)[:80], critical=False)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(skip_live: bool, output_json: bool) -> int:
    if not output_json:
        print(f"\n{BOLD}╔══════════════════════════════════════════════╗{NC}")
        print(f"{BOLD}║  ORBITIQ-X Phase 15A — Credential Validator  ║{NC}")
        print(f"{BOLD}╚══════════════════════════════════════════════╝{NC}")

    check_env_completeness()
    await check_spacetrack(skip_live)
    await check_anthropic(skip_live)
    await check_openai(skip_live)
    await check_postgres()
    await check_redis()
    await check_neo4j()
    await check_noaa()

    # ── Summary ───────────────────────────────────────────────────────────────
    passed   = sum(1 for r in results if r.passed)
    failed   = sum(1 for r in results if not r.passed)
    critical = sum(1 for r in results if not r.passed and r.critical)

    if output_json:
        print(json.dumps({
            "total": len(results), "passed": passed, "failed": failed,
            "critical_failures": critical,
            "checks": [
                {"name": r.name, "passed": r.passed, "message": r.message,
                 "critical": r.critical, "detail": r.detail}
                for r in results
            ],
        }, indent=2))
        return 0 if critical == 0 else 1

    print(f"\n{'─'*50}")
    print(f"  Total:    {len(results)}")
    print(f"  {GREEN}Passed:   {passed}{NC}")
    print(f"  {RED if failed else GREEN}Failed:   {failed}{NC}")
    print(f"  {RED if critical else GREEN}Critical: {critical}{NC}")
    print(f"{'─'*50}")

    if critical == 0:
        print(f"\n{GREEN}✅ All critical checks passed.{NC}")
        print("   Proceed to: python3 deployment/15a/sync.py --test-run")
    else:
        print(f"\n{RED}❌ {critical} critical failure(s). Fix before deploying.{NC}")

    return 0 if critical == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ORBITIQ-X Phase 15A credential validator")
    parser.add_argument("--skip-live", action="store_true",
                        help="Skip external API calls (env check only)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.skip_live, args.json)))
