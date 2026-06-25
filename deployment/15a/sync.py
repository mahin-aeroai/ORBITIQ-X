#!/usr/bin/env python3
"""
ORBITIQ-X Phase 15A — Catalog Sync Bootstrap
==============================================
Stage 5: First operational Space-Track sync.
Pulls the full active satellite catalog and populates PostgreSQL.

Modes
──────
  --test-run   Pull 50 ISS-vicinity objects — validates pipeline without
               pulling the full 27K+ catalog
  --full       Full catalog sync (takes 5–15 min on first run)
  --status     Show current catalog status without syncing

Usage
──────
  python3 deployment/15a/sync.py --test-run
  python3 deployment/15a/sync.py --full
  python3 deployment/15a/sync.py --status
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "orbital-engine"))

# Load .env
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

CYAN  = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW= "\033[1;33m"
RED   = "\033[0;31m"
BOLD  = "\033[1m"
NC    = "\033[0m"

def info(m): print(f"{CYAN}[INFO]{NC}  {m}")
def ok(m):   print(f"{GREEN}[ OK ]{NC}  {m}")
def warn(m): print(f"{YELLOW}[WARN]{NC}  {m}")
def err(m):  print(f"{RED}[ERR ]{NC}  {m}")


async def show_status() -> None:
    """Show current catalog status from PostgreSQL."""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", 5432)),
            database=os.environ.get("POSTGRES_DB", "orbitiq_db"),
            user=os.environ.get("POSTGRES_USER", "orbitiq"),
            password=os.environ.get("POSTGRES_PASSWORD", ""),
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM satellites")
        by_type = await conn.fetch(
            "SELECT object_type, COUNT(*) as n FROM satellites GROUP BY object_type ORDER BY n DESC"
        )
        by_regime = await conn.fetch(
            "SELECT regime, COUNT(*) as n FROM satellites WHERE regime IS NOT NULL"
            " GROUP BY regime ORDER BY n DESC LIMIT 8"
        )
        fresh = await conn.fetchval(
            "SELECT COUNT(*) FROM satellites WHERE tle_age_days <= 3"
        )
        stale = await conn.fetchval(
            "SELECT COUNT(*) FROM satellites WHERE tle_age_days > 7"
        )
        await conn.close()

        print(f"\n{BOLD}Catalog Status{NC}")
        print(f"  Total objects:  {total:,}")
        print(f"  Fresh TLEs (≤3d): {fresh:,}")
        print(f"  Stale TLEs (>7d): {stale:,}")
        print(f"\n  By type:")
        for row in by_type:
            print(f"    {row['object_type']:20} {row['n']:>6,}")
        print(f"\n  By regime:")
        for row in by_regime:
            print(f"    {(row['regime'] or 'unknown'):20} {row['n']:>6,}")
    except Exception as exc:
        err(f"Database query failed: {exc}")
        err("Is PostgreSQL running? Did migrations run?")


async def test_run() -> None:
    """
    Pull 10 well-known satellites from Space-Track as pipeline validation.
    Does not attempt a full catalog download.
    """
    info("Test run: pulling 10 well-known objects from Space-Track...")
    identity = os.environ.get("SPACETRACK_IDENTITY", "")
    password = os.environ.get("SPACETRACK_PASSWORD", "")

    if not identity or not password:
        err("Space-Track credentials not configured. Run validate.py first.")
        sys.exit(1)

    # 10 well-known NORADs: ISS, Hubble, 8 Starlinks
    test_ids = [25544, 20580, 44713, 44914, 44915, 44916, 44917, 44918, 44919, 44920]

    import httpx
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        # Authenticate
        r = await client.post(
            "https://www.space-track.org/ajaxauth/login",
            data={"identity": identity, "password": password},
        )
        if r.status_code != 200 or "Failed" in r.text:
            err(f"Space-Track auth failed (HTTP {r.status_code})")
            sys.exit(1)
        ok("Space-Track: authenticated")

        # Pull TLEs
        ids_str = ",".join(str(i) for i in test_ids)
        r = await client.get(
            f"https://www.space-track.org/basicspacedata/query/class/gp/"
            f"NORAD_CAT_ID/{ids_str}/format/json/orderby/NORAD_CAT_ID/",
            timeout=20,
        )
        elapsed = time.perf_counter() - t0
        if r.status_code != 200:
            err(f"TLE download failed: HTTP {r.status_code}")
            sys.exit(1)

        data = r.json()
        ok(f"Space-Track: pulled {len(data)} objects in {elapsed*1000:.0f}ms")

        for obj in data[:3]:
            norad = obj.get("NORAD_CAT_ID")
            name  = obj.get("OBJECT_NAME", "?")
            epoch = obj.get("EPOCH", "?")[:10]
            print(f"    NORAD {norad:>6}  {name:<30}  epoch={epoch}")
        if len(data) > 3:
            print(f"    ... and {len(data)-3} more")

    info("Attempting database write...")
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", 5432)),
            database=os.environ.get("POSTGRES_DB", "orbitiq_db"),
            user=os.environ.get("POSTGRES_USER", "orbitiq"),
            password=os.environ.get("POSTGRES_PASSWORD", ""),
        )
        # Upsert the 10 objects
        inserted = 0
        for obj in data:
            try:
                await conn.execute("""
                    INSERT INTO satellites (norad_id, name, object_type,
                        tle_line1, tle_line2, tle_epoch, status)
                    VALUES ($1, $2, $3, $4, $5, NOW(), 'unknown')
                    ON CONFLICT (norad_id) DO UPDATE
                      SET name=EXCLUDED.name,
                          tle_line1=EXCLUDED.tle_line1,
                          tle_line2=EXCLUDED.tle_line2,
                          tle_epoch=NOW()
                """,
                    int(obj["NORAD_CAT_ID"]),
                    obj.get("OBJECT_NAME", "UNKNOWN"),
                    obj.get("OBJECT_TYPE", "UNKNOWN").lower().replace(" ", "_"),
                    obj.get("TLE_LINE1", ""),
                    obj.get("TLE_LINE2", ""),
                )
                inserted += 1
            except Exception as e:
                warn(f"  Row {obj.get('NORAD_CAT_ID')}: {e}")
        await conn.close()
        ok(f"Database: {inserted}/{len(data)} objects written")
    except Exception as exc:
        warn(f"Database write skipped: {exc}")
        warn("(Run migrations first: python migrate.py upgrade head)")

    print(f"\n{GREEN}✅ Test run complete.{NC}")
    print(f"   Full sync: python3 deployment/15a/sync.py --full")


async def full_sync() -> None:
    """
    Full catalog sync using the CatalogSyncService.
    Delegates entirely to existing application infrastructure.
    """
    info("Starting full catalog sync via CatalogSyncService...")
    info("This will pull ~27,000+ objects from Space-Track.")
    info("Estimated time: 5–15 minutes depending on connection speed.")
    print()

    try:
        from app.services.catalog_sync_service import CatalogSyncService
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            svc = await CatalogSyncService.create(redis_client=None)
            t0  = time.perf_counter()
            report = await svc.sync_full()
            elapsed = time.perf_counter() - t0

        print(f"\n{BOLD}Sync Report{NC}")
        d = report.as_dict()
        for k, v in d.items():
            if v is not None:
                print(f"  {k:<30} {v}")

        if report.status == "success":
            ok(f"Full sync completed in {elapsed:.1f}s — {report.satellites_processed:,} objects")
        else:
            err(f"Sync ended with status: {report.status}")
            if report.failure_reason:
                err(f"Reason: {report.failure_reason}")

    except ImportError as exc:
        err(f"Import error: {exc}")
        err("Ensure you're running from the repository root with the venv active.")
    except Exception as exc:
        err(f"Sync failed: {exc}")
        raise


async def main() -> None:
    parser = argparse.ArgumentParser(description="ORBITIQ-X Phase 15A catalog sync")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--test-run", action="store_true", help="Pull 10 objects to validate pipeline")
    grp.add_argument("--full",     action="store_true", help="Full ~27K object catalog sync")
    grp.add_argument("--status",   action="store_true", help="Show catalog status")
    args = parser.parse_args()

    print(f"\n{BOLD}╔══════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}║  ORBITIQ-X Phase 15A — Catalog Sync          ║{NC}")
    print(f"{BOLD}╚══════════════════════════════════════════════╝{NC}\n")

    if args.status:
        await show_status()
    elif args.test_run:
        await test_run()
    elif args.full:
        await full_sync()


if __name__ == "__main__":
    asyncio.run(main())
