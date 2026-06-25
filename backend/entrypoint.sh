#!/bin/bash
# ORBITIQ-X — Docker entrypoint (Railway-compatible)
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "[entrypoint] ORBITIQ-X backend starting..."
echo "[entrypoint] DATABASE_URL set: ${DATABASE_URL:+yes}"
echo "[entrypoint] Skipping PG wait — Railway manages DB readiness"

# Run migrations
echo "[entrypoint] Running database migrations..."
python3 migrate.py upgrade head || echo "[entrypoint] WARNING: Migration failed (non-fatal, DB may not be ready yet)"

echo "[entrypoint] Starting application: $*"
exec "$@"
