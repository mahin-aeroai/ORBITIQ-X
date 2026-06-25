#!/bin/bash
# ORBITIQ-X — Docker entrypoint (Railway-compatible)

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "[entrypoint] ORBITIQ-X backend starting..."

python3 << 'PYEOF'
import os, sys, subprocess, urllib.parse

# Parse DATABASE_URL — ignore any broken POSTGRES_* template vars
db_url = os.environ.get("DATABASE_URL", "")
if db_url:
    url = db_url
    for prefix in ("postgresql+asyncpg://", "postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql://" + url[len(prefix):]
            break
    try:
        p = urllib.parse.urlparse(url)
        os.environ["POSTGRES_HOST"]     = str(p.hostname or "localhost")
        os.environ["POSTGRES_PORT"]     = str(p.port or 5432)
        os.environ["POSTGRES_DB"]       = str(p.path or "/orbitiq_db").lstrip("/")
        os.environ["POSTGRES_USER"]     = str(p.username or "orbitiq")
        os.environ["POSTGRES_PASSWORD"] = str(p.password or "")
        print(f"[entrypoint] DB: {p.hostname}:{p.port}{p.path}", flush=True)
    except Exception as e:
        print(f"[entrypoint] WARNING: URL parse error: {e}", flush=True)
else:
    print("[entrypoint] WARNING: DATABASE_URL not set", flush=True)

# Run migrations
print("[entrypoint] Running migrations...", flush=True)
result = subprocess.run(
    [sys.executable, "migrate.py", "upgrade", "head"],
    env=os.environ.copy()
)
if result.returncode != 0:
    print("[entrypoint] WARNING: Migration failed (non-fatal)", flush=True)

# Start gunicorn
port = os.environ.get("PORT", "8000")
cmd = [
    sys.executable, "-m", "gunicorn", "app.main:app",
    "--worker-class", "uvicorn.workers.UvicornWorker",
    "--workers", "2",
    "--bind", f"0.0.0.0:{port}",
    "--timeout", "120",
    "--graceful-timeout", "30",
    "--access-logfile", "-",
    "--error-logfile", "-",
]
print(f"[entrypoint] Starting: {' '.join(cmd)}", flush=True)
os.execvp(sys.executable, cmd)
PYEOF
