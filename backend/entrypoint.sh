#!/usr/bin/env python3
"""
ORBITIQ-X — Production Entrypoint (Railway-compatible)
Parses DATABASE_URL, runs migrations, starts gunicorn.
"""
import os, sys, subprocess, urllib.parse

# ── Parse DATABASE_URL → POSTGRES_* env vars ─────────────────
db_url = os.environ.get("DATABASE_URL", "")
if db_url:
    url = db_url
    for old, new in [("postgresql+asyncpg://","postgresql://"),("postgres://","postgresql://")]:
        if url.startswith(old):
            url = new + url[len(old):]
    try:
        p = urllib.parse.urlparse(url)
        os.environ["POSTGRES_HOST"]     = str(p.hostname or "localhost")
        os.environ["POSTGRES_PORT"]     = str(p.port or 5432)
        os.environ["POSTGRES_DB"]       = str(p.path or "/orbitiq_db").lstrip("/")
        os.environ["POSTGRES_USER"]     = str(p.username or "postgres")
        os.environ["POSTGRES_PASSWORD"] = str(p.password or "")
        print(f"[entrypoint] DB: {p.hostname}:{p.port}{p.path}", flush=True)
    except Exception as e:
        print(f"[entrypoint] WARNING: URL parse error: {e}", flush=True)

# ── Run migrations ────────────────────────────────────────────
print("[entrypoint] Running migrations...", flush=True)
r = subprocess.run([sys.executable, "migrate.py", "upgrade", "head"])
if r.returncode != 0:
    print("[entrypoint] WARNING: Migration failed (non-fatal)", flush=True)

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
