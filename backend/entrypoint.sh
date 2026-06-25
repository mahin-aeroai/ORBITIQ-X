#!/bin/bash
# ORBITIQ-X — Docker entrypoint (Railway-compatible)
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "[entrypoint] ORBITIQ-X backend starting..."

# Parse DATABASE_URL in Python (more reliable than bash string manipulation)
if [ -n "${DATABASE_URL:-}" ]; then
    eval $(python3 - << 'PYEOF'
import os, urllib.parse
url = os.environ.get("DATABASE_URL", "")
# Handle postgres:// and postgresql+asyncpg:// formats
url = url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
try:
    p = urllib.parse.urlparse(url)
    print(f'export POSTGRES_HOST="{p.hostname}"')
    print(f'export POSTGRES_PORT="{p.port or 5432}"')
    print(f'export POSTGRES_DB="{p.path.lstrip("/")}"')
    print(f'export POSTGRES_USER="{p.username}"')
    print(f'export POSTGRES_PASSWORD="{p.password}"')
except Exception as e:
    print(f'echo "[entrypoint] WARNING: Could not parse DATABASE_URL: {e}"')
PYEOF
)
    echo "[entrypoint] DB host: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
fi

# Run migrations (non-fatal)
echo "[entrypoint] Running migrations..."
python3 migrate.py upgrade head 2>&1 || echo "[entrypoint] WARNING: Migration failed (non-fatal)"

# Start gunicorn
echo "[entrypoint] Starting gunicorn..."
exec python3 -m gunicorn "$@"
