#!/bin/bash
# ORBITIQ-X — Docker entrypoint (Railway-compatible)
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "[entrypoint] ORBITIQ-X backend starting..."
echo "[entrypoint] DATABASE_URL set: ${DATABASE_URL:+yes}"

# Override POSTGRES_HOST with the Railway DATABASE_URL host
# so migrate.py uses the right host
if [ -n "${DATABASE_URL:-}" ]; then
    # Strip protocol prefix
    _url="${DATABASE_URL#*://}"          # user:pass@host:port/db
    _hostpart="${_url#*@}"               # host:port/db
    _host="${_hostpart%%:*}"             # host
    _portdb="${_hostpart#*:}"            # port/db
    _port="${_portdb%%/*}"               # port
    _db="${_portdb#*/}"                  # db
    _db="${_db%%\?*}"                    # strip query params
    _userpass="${_url%%@*}"              # user:pass
    _user="${_userpass%%:*}"             # user
    _pass="${_userpass#*:}"              # pass

    export POSTGRES_HOST="$_host"
    export POSTGRES_PORT="$_port"
    export POSTGRES_DB="$_db"
    export POSTGRES_USER="$_user"
    export POSTGRES_PASSWORD="$_pass"
    echo "[entrypoint] Resolved DB host: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
fi

# Run migrations (non-fatal on failure)
echo "[entrypoint] Running database migrations..."
python3 migrate.py upgrade head 2>&1 || echo "[entrypoint] WARNING: Migration failed"

# Find gunicorn
GUNICORN=$(python3 -c "import shutil; print(shutil.which('gunicorn') or '')" 2>/dev/null)
if [ -z "$GUNICORN" ]; then
    GUNICORN=$(find /usr /root /.local -name gunicorn -type f 2>/dev/null | head -1)
fi
if [ -z "$GUNICORN" ]; then
    echo "[entrypoint] gunicorn not found in PATH, installing..."
    pip install --break-system-packages gunicorn uvicorn 2>/dev/null || true
    GUNICORN="gunicorn"
fi

echo "[entrypoint] Starting: $GUNICORN $*"
exec "$GUNICORN" "$@"
