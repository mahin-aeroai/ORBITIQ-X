#!/bin/bash
# ============================================================
# ORBITIQ-X — Docker entrypoint
#
# Runs database migrations before starting the FastAPI server.
# If migrations fail, the container exits (fail-fast).
#
# Usage (in Dockerfile):
#   ENTRYPOINT ["/entrypoint.sh"]
#   CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker"]
# ============================================================

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "[entrypoint] ORBITIQ-X backend starting..."
echo "[entrypoint] PostgreSQL: ${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-orbitiq_db}"

# ── Wait for PostgreSQL to be ready ───────────────────────────
MAX_WAIT=60
WAITED=0
echo "[entrypoint] Waiting for PostgreSQL..."

until python3 -c "
import psycopg2, os, sys
try:
    conn = psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=int(os.environ.get('POSTGRES_PORT', 5432)),
        dbname=os.environ.get('POSTGRES_DB', 'orbitiq_db'),
        user=os.environ.get('POSTGRES_USER', 'orbitiq'),
        password=os.environ.get('POSTGRES_PASSWORD', ''),
        connect_timeout=2
    )
    conn.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "[entrypoint] ERROR: PostgreSQL did not become ready within ${MAX_WAIT}s"
        exit 1
    fi
    echo "[entrypoint] Waiting for PostgreSQL... (${WAITED}s)"
    sleep 2
    WAITED=$((WAITED + 2))
done

echo "[entrypoint] PostgreSQL is ready."

# ── Run migrations ─────────────────────────────────────────────
echo "[entrypoint] Running database migrations..."
python3 migrate.py upgrade head

if [ $? -ne 0 ]; then
    echo "[entrypoint] ERROR: Migration failed — aborting startup"
    exit 1
fi

echo "[entrypoint] Migrations complete."

# ── Verify schema ──────────────────────────────────────────────
echo "[entrypoint] Verifying schema..."
python3 migrate.py verify || echo "[entrypoint] WARNING: Schema verification failed (non-fatal in dev)"

# ── Start application ─────────────────────────────────────────
echo "[entrypoint] Starting application: $*"
exec "$@"
