#!/bin/bash
# ORBITIQ-X — Docker entrypoint (Railway-compatible)

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "[entrypoint] ORBITIQ-X backend starting..."

# Parse DATABASE_URL and run migrations + start server
exec python3 - "$@" << 'PYEOF'
import os, sys, subprocess, urllib.parse

args = sys.argv[1:]

# Parse DATABASE_URL to set POSTGRES_* env vars for migrations
db_url = os.environ.get("DATABASE_URL", "")
if db_url:
    url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
    p = urllib.parse.urlparse(url)
    os.environ["POSTGRES_HOST"]     = p.hostname or "localhost"
    os.environ["POSTGRES_PORT"]     = str(p.port or 5432)
    os.environ["POSTGRES_DB"]       = p.path.lstrip("/")
    os.environ["POSTGRES_USER"]     = p.username or "orbitiq"
    os.environ["POSTGRES_PASSWORD"] = p.password or ""
    print(f"[entrypoint] DB: {p.hostname}:{p.port}/{p.path.lstrip('/')}", flush=True)

# Run migrations
print("[entrypoint] Running migrations...", flush=True)
r = subprocess.run([sys.executable, "migrate.py", "upgrade", "head"], capture_output=False)
if r.returncode != 0:
    print("[entrypoint] WARNING: Migration failed (non-fatal)", flush=True)

# Start gunicorn
print(f"[entrypoint] Starting gunicorn...", flush=True)
os.execvp(sys.executable, [sys.executable, "-m", "gunicorn"] + args)
PYEOF
