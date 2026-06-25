#!/bin/bash
# ============================================================
# ORBITIQ-X — Docker entrypoint
# Runs database migrations before starting the FastAPI server.
# ============================================================

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "[entrypoint] ORBITIQ-X backend starting..."

# ── Parse DATABASE_URL if individual vars point to localhost ──
# Railway injects DATABASE_URL directly — extract components from it
if [ -n "${DATABASE_URL:-}" ]; then
    echo "[entrypoint] Using DATABASE_URL from environment"
    # Extract host from DATABASE_URL for the readiness check
    # Format: postgresql+asyncpg://user:pass@host:port/db or postgres://...
    DB_URL="${DATABASE_URL}"
    # Strip protocol
    DB_URL_NO_PROTO="${DB_URL#*://}"
    # Extract host:port/db part
    DB_HOSTPART="${DB_URL_NO_PROTO#*@}"
    DB_HOST_PORT="${DB_HOSTPART%%/*}"
    RESOLVED_HOST="${DB_HOST_PORT%%:*}"
    RESOLVED_PORT="${DB_HOST_PORT##*:}"
    RESOLVED_PORT="${RESOLVED_PORT%%/*}"
    RESOLVED_DB="${DB_HOSTPART##*/}"
    RESOLVED_DB="${RESOLVED_DB%%\?*}"
    # Extract user:pass
    DB_USERPART="${DB_URL_NO_PROTO%%@*}"
    RESOLVED_USER="${DB_USERPART%%:*}"
    RESOLVED_PASS="${DB_USERPART#*:}"

    export POSTGRES_HOST="${RESOLVED_HOST}"
    export POSTGRES_PORT="${RESOLVED_PORT:-5432}"
    export POSTGRES_DB="${RESOLVED_DB}"
    export POSTGRES_USER="${RESOLVED_USER}"
    export POSTGRES_PASSWORD="${RESOLVED_PASS}"
    echo "[entrypoint] PostgreSQL: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
else
    echo "[entrypoint] PostgreSQL: ${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-orbitiq_db}"
fi

# ── Wait for PostgreSQL to be ready ──────────────────────────
MAX_WAIT=120
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
        connect_timeout=3
    )
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f'  {e}', file=sys.stderr)
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

echo "[entrypoint] Migrations complete."

# ── Start application ─────────────────────────────────────────
echo "[entrypoint] Starting application: $*"
exec "$@"
