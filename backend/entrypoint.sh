#!/usr/bin/env python3
"""
ORBITIQ-X — Production Entrypoint (Railway-compatible)
Parses DATABASE_URL, runs migrations, starts gunicorn.
"""
import os, sys, subprocess, urllib.parse

# ── Parse DATABASE_URL → POSTGRES_* env vars ─────────────────
# Try multiple sources for DATABASE_URL
db_url = (
    os.environ.get("DATABASE_URL") or
    os.environ.get("ORBITIQ_DATABASE_URL") or
    os.environ.get("POSTGRES_URL") or
    ""
)
print(f"[entrypoint] Env DATABASE_URL present: {bool(os.environ.get('DATABASE_URL'))}", flush=True)
print(f"[entrypoint] All env keys with DB/POSTGRES: {[k for k in os.environ if 'DB' in k or 'POSTGRES' in k or 'DATABASE' in k]}", flush=True)
if db_url:
    url = db_url
    for old, new in [("postgresql+asyncpg://","postgresql://"),("postgres://","postgresql://")]:
        if url.startswith(old):
            url = new + url[len(old):]
    try:
        p = urllib.parse.urlparse(url)
        os.environ["POSTGRES_HOST"]     = str(p.hostname or "localhost")
        os.environ["POSTGRES_PORT"]     = str(p.port or 5432)
        os.environ["POSTGRES_DB"]       = str(p.path or "/railway").lstrip("/")
        os.environ["POSTGRES_USER"]     = str(p.username or "postgres")
        os.environ["POSTGRES_PASSWORD"] = str(p.password or "")
        # Set ORBITIQ_DATABASE_URL so alembic env.py uses it directly (Option 1)
        os.environ["ORBITIQ_DATABASE_URL"] = db_url
        print(f"[entrypoint] DB: {p.hostname}:{p.port}{p.path}", flush=True)
    except Exception as e:
        print(f"[entrypoint] WARNING: URL parse error: {e}", flush=True)

# ── Pre-migration: widen alembic_version.version_num ─────────
# Railway PostgreSQL default is VARCHAR(32). Our revision IDs are up to 35 chars.
# Run the ALTER outside of Alembic so it commits before any migration runs.
print("[entrypoint] Widening alembic_version.version_num to VARCHAR(64)...", flush=True)
try:
    import psycopg2
    _conn = psycopg2.connect(db_url)
    _conn.autocommit = True
    _cur = _conn.cursor()
    # Widen the column (idempotent — no-op if already wide enough)
    _cur.execute("ALTER TABLE IF EXISTS alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    _cur.close()
    _conn.close()
    print("[entrypoint] alembic_version.version_num widened OK", flush=True)
except Exception as _e:
    # Table may not exist yet on first deploy — that's fine, Alembic will create it
    print(f"[entrypoint] version_num widen skipped: {_e}", flush=True)

# ── Run migrations ────────────────────────────────────────────
print("[entrypoint] Running migrations...", flush=True)
print(f"[entrypoint] DATABASE_URL = {db_url[:60]}..." if db_url else "[entrypoint] DATABASE_URL not set!", flush=True)

# Build psycopg2 URL for alembic (must be sync driver)
sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
# Convert to psycopg2
sync_url_pg2 = sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)
print(f"[entrypoint] Alembic sync URL: {sync_url_pg2[:60]}...", flush=True)

env = os.environ.copy()
env["ORBITIQ_DATABASE_URL"] = db_url  # alembic env.py reads this
env["DATABASE_URL"] = db_url

# Run alembic directly with explicit URL
r = subprocess.run(
    [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
    env=env,
    cwd=os.path.dirname(os.path.abspath(__file__))
)
if r.returncode != 0:
    print("[entrypoint] ERROR: Migration failed!", flush=True)
    sys.exit(1)
print("[entrypoint] Migrations complete.", flush=True)

# ── Start gunicorn ────────────────────────────────────────────
port = os.environ.get("PORT", "8000")
cmd  = [
    sys.executable, "-m", "gunicorn", "app.main:app",
    "--worker-class", "uvicorn.workers.UvicornWorker",
    "--workers",      "2",
    "--bind",         f"0.0.0.0:{port}",
    "--timeout",      "120",
    "--graceful-timeout", "30",
    "--access-logfile", "-",
    "--error-logfile",  "-",
    "--log-level",    "warning",
]
print(f"[entrypoint] Starting gunicorn on port {port}", flush=True)
os.execvp(sys.executable, cmd)
