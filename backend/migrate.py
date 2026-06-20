#!/usr/bin/env python3
"""
ORBITIQ-X — Migration CLI

Wraps Alembic with environment validation, pre-flight checks,
dry-run capability, and rollback procedures.

Usage:
    python migrate.py upgrade          # apply all pending migrations
    python migrate.py upgrade --head   # same as above
    python migrate.py downgrade -1     # roll back one migration
    python migrate.py downgrade base   # roll back ALL (dev only)
    python migrate.py status           # show current revision + pending
    python migrate.py history          # full migration history
    python migrate.py revision "add index on satellites.regime"
    python migrate.py sql-preview      # emit SQL without applying
    python migrate.py verify           # check schema matches models
    python migrate.py stamp head       # mark head without running
"""

from __future__ import annotations

import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orbitiq.migrate")

BACKEND_DIR = Path(__file__).parent
ALEMBIC_CFG  = BACKEND_DIR / "alembic.ini"


# ── Environment validation ─────────────────────────────────────

def check_env() -> dict[str, str]:
    """Validate all required environment variables are present."""
    required = {
        "POSTGRES_HOST":     os.getenv("POSTGRES_HOST",     "localhost"),
        "POSTGRES_PORT":     os.getenv("POSTGRES_PORT",     "5432"),
        "POSTGRES_DB":       os.getenv("POSTGRES_DB",       "orbitiq_db"),
        "POSTGRES_USER":     os.getenv("POSTGRES_USER",     "orbitiq"),
        "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
    }

    if not required["POSTGRES_PASSWORD"]:
        log.warning(
            "POSTGRES_PASSWORD is not set — using empty string. "
            "Set POSTGRES_PASSWORD in .env or environment."
        )

    dsn = (
        f"postgresql://{required['POSTGRES_USER']}:{required['POSTGRES_PASSWORD']}"
        f"@{required['POSTGRES_HOST']}:{required['POSTGRES_PORT']}/{required['POSTGRES_DB']}"
    )
    log.info(f"Target database: {required['POSTGRES_HOST']}:{required['POSTGRES_PORT']}"
             f"/{required['POSTGRES_DB']} (user={required['POSTGRES_USER']})")
    return required


def check_db_reachable() -> bool:
    """Quick connectivity check before running migrations."""
    try:
        import psycopg2
        env = check_env()
        conn = psycopg2.connect(
            host=env["POSTGRES_HOST"],
            port=int(env["POSTGRES_PORT"]),
            dbname=env["POSTGRES_DB"],
            user=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
            connect_timeout=5,
        )
        conn.close()
        log.info("Database connection: OK")
        return True
    except Exception as e:
        log.error(f"Database connection failed: {e}")
        return False


# ── Alembic wrapper ────────────────────────────────────────────

def alembic(*args: str) -> int:
    """Run alembic with given arguments, returning exit code."""
    cmd = [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_CFG)] + list(args)
    log.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(BACKEND_DIR))
    return result.returncode


# ── Commands ───────────────────────────────────────────────────

def cmd_upgrade(target: str = "head", dry_run: bool = False) -> int:
    """Apply migrations up to `target` (default: head)."""
    if not check_db_reachable():
        return 1

    if dry_run:
        log.info(f"DRY RUN — SQL preview for upgrade to {target}:")
        return alembic("upgrade", target, "--sql")

    log.info(f"Applying migrations → {target}")
    rc = alembic("upgrade", target)
    if rc == 0:
        log.info("Upgrade complete")
        cmd_status()
    return rc


def cmd_downgrade(target: str, dry_run: bool = False, force: bool = False) -> int:
    """Roll back migrations to `target`."""
    if target == "base" and not force:
        answer = input(
            "WARNING: downgrade to base will DROP ALL TABLES. "
            "Type 'yes-i-am-sure' to continue: "
        )
        if answer.strip() != "yes-i-am-sure":
            log.info("Downgrade cancelled")
            return 0

    if not check_db_reachable():
        return 1

    if dry_run:
        log.info(f"DRY RUN — SQL preview for downgrade to {target}:")
        return alembic("downgrade", target, "--sql")

    log.info(f"Rolling back migrations → {target}")
    rc = alembic("downgrade", target)
    if rc == 0:
        log.info("Downgrade complete")
        cmd_status()
    return rc


def cmd_status() -> int:
    """Show current migration state."""
    log.info("Current migration state:")
    rc = alembic("current")
    log.info("Pending migrations:")
    alembic("heads")
    return rc


def cmd_history() -> int:
    """Show full migration history."""
    return alembic("history", "--verbose")


def cmd_revision(message: str, autogenerate: bool = False) -> int:
    """Generate a new migration file."""
    args = ["revision", "-m", message]
    if autogenerate:
        if not check_db_reachable():
            return 1
        args.append("--autogenerate")
        log.info(
            "Autogenerating migration by comparing models to database schema. "
            "ALWAYS review the generated file before committing."
        )
    return alembic(*args)


def cmd_sql_preview(target: str = "head") -> int:
    """Emit SQL for all pending migrations without applying."""
    log.info(f"SQL preview — migrations to {target}:")
    return alembic("upgrade", target, "--sql")


def cmd_verify() -> int:
    """Check that database schema matches Alembic head."""
    log.info("Verifying schema consistency...")
    # `alembic check` exits non-zero if schema drift is detected
    rc = alembic("check")
    if rc == 0:
        log.info("Schema is up to date — no drift detected")
    else:
        log.error(
            "Schema drift detected — run `python migrate.py upgrade` "
            "or `python migrate.py revision --autogenerate` to fix"
        )
    return rc


def cmd_stamp(target: str = "head") -> int:
    """Mark a revision as applied without running it (use after manual SQL)."""
    log.warning(f"Stamping revision to {target} without running migrations")
    return alembic("stamp", target)


# ── Rollback procedures ────────────────────────────────────────

ROLLBACK_PROCEDURES = """
ORBITIQ-X Migration Rollback Procedures
========================================

SCENARIO 1: Roll back one failed migration
─────────────────────────────────────────
  python migrate.py downgrade -1

SCENARIO 2: Roll back to a specific revision
────────────────────────────────────────────
  python migrate.py history          # find the target revision ID
  python migrate.py downgrade <rev>  # e.g. 0005_create_tle_records

SCENARIO 3: Emergency — production schema is broken
────────────────────────────────────────────────────
  1. Restore from last backup FIRST:
       pg_restore -U orbitiq -d orbitiq_db backup_YYYYMMDD.dump
  2. Mark Alembic state to match the restored backup:
       python migrate.py stamp <rev_at_backup_time>
  3. Verify:
       python migrate.py status

SCENARIO 4: Dev reset — wipe everything and start fresh
────────────────────────────────────────────────────────
  python migrate.py downgrade base --force
  python migrate.py upgrade

ZERO-DATA-LOSS GUARANTEE
─────────────────────────
Every downgrade() function:
  - Drops only tables/columns created in its upgrade()
  - Never truncates data that existed before this migration
  - Uses DROP TABLE CASCADE only for the table it created
  - Uses ALTER TABLE DROP COLUMN only for columns it added
  - Never removes constraints that pre-date the migration
"""


# ── Entry point ────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="ORBITIQ-X migration management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_up = sub.add_parser("upgrade", help="Apply pending migrations")
    p_up.add_argument("target", nargs="?", default="head")
    p_up.add_argument("--dry-run", action="store_true")

    p_down = sub.add_parser("downgrade", help="Roll back migrations")
    p_down.add_argument("target", default="-1")
    p_down.add_argument("--dry-run", action="store_true")
    p_down.add_argument("--force", action="store_true",
                        help="Skip confirmation for downgrade base")

    sub.add_parser("status",  help="Show current migration state")
    sub.add_parser("history", help="Show full migration history")

    p_rev = sub.add_parser("revision", help="Generate new migration file")
    p_rev.add_argument("message")
    p_rev.add_argument("--autogenerate", action="store_true")

    p_sql = sub.add_parser("sql-preview", help="Emit SQL without applying")
    p_sql.add_argument("target", nargs="?", default="head")

    sub.add_parser("verify", help="Check schema matches models")

    p_stamp = sub.add_parser("stamp", help="Mark revision applied without running")
    p_stamp.add_argument("target", default="head")

    sub.add_parser("rollback-help", help="Print rollback procedures")

    args = parser.parse_args()

    if args.command == "upgrade":
        return cmd_upgrade(args.target, args.dry_run)
    elif args.command == "downgrade":
        return cmd_downgrade(args.target, args.dry_run, getattr(args, "force", False))
    elif args.command == "status":
        return cmd_status()
    elif args.command == "history":
        return cmd_history()
    elif args.command == "revision":
        return cmd_revision(args.message, args.autogenerate)
    elif args.command == "sql-preview":
        return cmd_sql_preview(args.target)
    elif args.command == "verify":
        return cmd_verify()
    elif args.command == "stamp":
        return cmd_stamp(args.target)
    elif args.command == "rollback-help":
        print(ROLLBACK_PROCEDURES)
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
