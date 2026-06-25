#!/usr/bin/env bash
# =============================================================================
# ORBITIQ-X Phase 15A — Interactive Setup Wizard
# =============================================================================
# Stages 1–4: Server preparation, credential collection, .env generation,
#             service deployment and validation.
#
# Run as: bash setup.sh
# Run on: Ubuntu 22.04 LTS with sudo access
# =============================================================================
set -euo pipefail

# ── Terminal colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()     { echo -e "${RED}[ERR ]${NC}  $*"; }
header()  { echo -e "\n${BOLD}══ $* ══${NC}"; }
ask()     { echo -ne "${YELLOW}  → ${NC}$1 "; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
LOG_FILE="${REPO_ROOT}/deployment/15a/setup.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u +%H:%M:%S)] $*" >> "$LOG_FILE"; }

# ── Stage 1: System requirements ─────────────────────────────────────────────
header "Stage 1 — System Requirements"

check_cmd() {
    if command -v "$1" &>/dev/null; then
        ok "$1 found ($(command -v "$1"))"
    else
        err "$1 not found"
        return 1
    fi
}

PREREQS_OK=true
check_cmd docker   || PREREQS_OK=false
check_cmd openssl  || PREREQS_OK=false
check_cmd curl     || PREREQS_OK=false
check_cmd python3  || PREREQS_OK=false

# Docker Compose v2
if docker compose version &>/dev/null 2>&1; then
    ok "Docker Compose v2 found"
else
    err "Docker Compose v2 not found. Install: https://docs.docker.com/compose/install/"
    PREREQS_OK=false
fi

# RAM check
RAM_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)
if [ "$RAM_GB" -ge 14 ]; then
    ok "RAM: ${RAM_GB}GB (minimum 16GB recommended)"
elif [ "$RAM_GB" -ge 7 ]; then
    warn "RAM: ${RAM_GB}GB — minimum for operation; 16GB recommended"
else
    warn "RAM: ${RAM_GB}GB — may be insufficient for full stack"
fi

# Disk space check
DISK_GB=$(df -BG "${REPO_ROOT}" | awk 'NR==2 {gsub(/G/,"",$4); print $4}' 2>/dev/null || echo 0)
if [ "$DISK_GB" -ge 50 ]; then
    ok "Disk: ${DISK_GB}GB free"
else
    warn "Disk: ${DISK_GB}GB free — 250GB recommended for production data"
fi

if [ "$PREREQS_OK" != "true" ]; then
    err "Prerequisites missing. Install them and re-run."
    exit 1
fi

# ── Stage 2: Credential collection ───────────────────────────────────────────
header "Stage 2 — Credentials & Configuration"
echo "  Enter values below. Secrets are not echoed. Press Enter to keep existing."
echo "  All values are written to: ${ENV_FILE}"
echo ""

# Load existing .env if present
if [ -f "$ENV_FILE" ]; then
    info "Found existing .env — loading as defaults"
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
fi

prompt_secret() {
    local var="$1"; local prompt="$2"; local default="${!var:-}"
    local hint="${3:-}"
    if [ -n "$hint" ]; then echo "  Hint: $hint"; fi
    if [ -n "$default" ] && [ "$default" != "CHANGE_ME" ] && [[ "$default" != CHANGE_ME* ]]; then
        ask "${prompt} [existing]:"
        read -rs val
        echo ""
        [ -z "$val" ] && val="$default"
    else
        ask "${prompt}:"
        read -rs val
        echo ""
    fi
    printf -v "$var" '%s' "$val"
}

prompt_plain() {
    local var="$1"; local prompt="$2"; local default="${!var:-$3}"
    ask "${prompt} [${default}]:"
    read -r val
    [ -z "$val" ] && val="$default"
    printf -v "$var" '%s' "$val"
}

echo ""
info "=== Application ==="
prompt_plain  "ORBITIQ_ENV"           "Environment" "production"
ORBITIQ_SECRET_KEY=$(openssl rand -hex 32)
ok "ORBITIQ_SECRET_KEY generated ($(echo "$ORBITIQ_SECRET_KEY" | wc -c) chars)"

info "=== PostgreSQL ==="
prompt_plain  "POSTGRES_HOST"         "PostgreSQL host"     "postgres"
prompt_plain  "POSTGRES_PORT"         "PostgreSQL port"     "5432"
prompt_plain  "POSTGRES_DB"           "Database name"       "orbitiq_db"
prompt_plain  "POSTGRES_USER"         "Database user"       "orbitiq"
prompt_secret "POSTGRES_PASSWORD"     "PostgreSQL password" "min 20 chars"

info "=== Redis ==="
prompt_plain  "REDIS_HOST"            "Redis host"          "redis"
prompt_plain  "REDIS_PORT"            "Redis port"          "6379"
prompt_secret "REDIS_PASSWORD"        "Redis password"      "min 16 chars"

info "=== Neo4j ==="
prompt_plain  "NEO4J_HOST"            "Neo4j host"          "neo4j"
prompt_plain  "NEO4J_BOLT_PORT"       "Neo4j Bolt port"     "7687"
prompt_plain  "NEO4J_USER"            "Neo4j user"          "neo4j"
prompt_secret "NEO4J_PASSWORD"        "Neo4j password"      "min 8 chars"

info "=== MinIO ==="
prompt_plain  "MINIO_HOST"            "MinIO host"          "minio"
MINIO_ROOT_PASSWORD=$(openssl rand -hex 24)
ok "MINIO_ROOT_PASSWORD generated"

info "=== Weaviate ==="
WEAVIATE_API_KEY=$(openssl rand -hex 32)
ok "WEAVIATE_API_KEY generated"

info "=== Grafana ==="
prompt_secret "GRAFANA_ADMIN_PASSWORD" "Grafana admin password"

info "=== AI / LLM ==="
prompt_secret "ANTHROPIC_API_KEY"     "Anthropic API key" "sk-ant-... from console.anthropic.com"
prompt_plain  "ANTHROPIC_MODEL"       "Anthropic model"  "claude-sonnet-4-6"
prompt_secret "OPENAI_API_KEY"        "OpenAI API key (for embeddings)" "sk-... from platform.openai.com"

info "=== Space-Track.org ==="
echo "  Register free at: https://www.space-track.org/auth/createAccount"
prompt_plain  "SPACETRACK_IDENTITY"   "Space-Track email"
prompt_secret "SPACETRACK_PASSWORD"   "Space-Track password"

info "=== Networking ==="
prompt_plain  "DOMAIN"                "Your domain or IP" "localhost"
prompt_plain  "BACKEND_CORS_ORIGINS"  "CORS origin (frontend URL)" "https://${DOMAIN:-localhost}"

# SSL
if [ "${DOMAIN:-localhost}" != "localhost" ]; then
    prompt_plain "USE_LETSENCRYPT" "Use Let's Encrypt? (y/n)" "y"
else
    USE_LETSENCRYPT="n"
fi

# ── Write .env ────────────────────────────────────────────────────────────────
header "Writing .env"

cat > "$ENV_FILE" << EOF
# ORBITIQ-X Production Environment
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# DO NOT COMMIT THIS FILE

# ─── Application ──────────────────────────────────────────────────────────────
ORBITIQ_ENV=${ORBITIQ_ENV}
ORBITIQ_VERSION=0.1.0
ORBITIQ_LOG_LEVEL=INFO
ORBITIQ_SECRET_KEY=${ORBITIQ_SECRET_KEY}

# ─── Backend ──────────────────────────────────────────────────────────────────
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
BACKEND_WORKERS=4
BACKEND_RELOAD=false
BACKEND_CORS_ORIGINS=${BACKEND_CORS_ORIGINS:-https://localhost}
BACKEND_API_PREFIX=/api/v1
BACKEND_RATE_LIMIT_REQUESTS=100
BACKEND_JWT_ALGORITHM=HS256
BACKEND_JWT_EXPIRE_MINUTES=60
BACKEND_JWT_REFRESH_EXPIRE_DAYS=7
TRUSTED_HOSTS=${DOMAIN:-localhost},www.${DOMAIN:-localhost}

# ─── PostgreSQL ───────────────────────────────────────────────────────────────
POSTGRES_HOST=${POSTGRES_HOST}
POSTGRES_PORT=${POSTGRES_PORT}
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_POOL_SIZE=20
POSTGRES_MAX_OVERFLOW=10
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}

# ─── Redis ────────────────────────────────────────────────────────────────────
REDIS_HOST=${REDIS_HOST}
REDIS_PORT=${REDIS_PORT}
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_DB=0
REDIS_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/0

# ─── Neo4j ────────────────────────────────────────────────────────────────────
NEO4J_HOST=${NEO4J_HOST}
NEO4J_BOLT_PORT=${NEO4J_BOLT_PORT}
NEO4J_HTTP_PORT=7474
NEO4J_USER=${NEO4J_USER}
NEO4J_PASSWORD=${NEO4J_PASSWORD}
NEO4J_DATABASE=orbitiq
NEO4J_URI=bolt://${NEO4J_HOST}:${NEO4J_BOLT_PORT}

# ─── Weaviate ─────────────────────────────────────────────────────────────────
WEAVIATE_HOST=weaviate
WEAVIATE_PORT=8080
WEAVIATE_GRPC_PORT=50051
WEAVIATE_API_KEY=${WEAVIATE_API_KEY}

# ─── MinIO ────────────────────────────────────────────────────────────────────
MINIO_HOST=minio
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
MINIO_BUCKET_TLE=orbitiq-tle
MINIO_BUCKET_DOCS=orbitiq-docs
MINIO_BUCKET_MODELS=orbitiq-models
MINIO_URL=http://minio:9000

# ─── AI / LLM ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ANTHROPIC_MODEL=${ANTHROPIC_MODEL}
ANTHROPIC_MAX_TOKENS=4096
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_DIMENSIONS=3072

# ─── Space-Track ──────────────────────────────────────────────────────────────
SPACETRACK_IDENTITY=${SPACETRACK_IDENTITY}
SPACETRACK_PASSWORD=${SPACETRACK_PASSWORD}
SPACETRACK_BASE_URL=https://www.space-track.org
SPACETRACK_RATE_LIMIT_PER_HOUR=300

# ─── External APIs ────────────────────────────────────────────────────────────
CELESTRAK_BASE_URL=https://celestrak.org
NOAA_SPACE_WEATHER_URL=https://services.swpc.noaa.gov
NASA_API_KEY=DEMO_KEY

# ─── Orbital Engine ───────────────────────────────────────────────────────────
ORBITAL_PROPAGATION_STEP_SECONDS=60
ORBITAL_MAX_PROPAGATION_DAYS=30
ORBITAL_SGP4_WGS=72
ORBITAL_CONJUNCTION_SCREENING_RANGE_KM=5.0
ORBITAL_CONJUNCTION_PC_THRESHOLD=0.0001
ORBITAL_BATCH_PROPAGATION_WORKERS=8

# ─── Monitoring ───────────────────────────────────────────────────────────────
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001
GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=orbitiq-x-backend

# ─── SSL ──────────────────────────────────────────────────────────────────────
DOMAIN=${DOMAIN:-localhost}
SSL_CERT_PATH=/etc/ssl/certs/orbitiq.crt
SSL_KEY_PATH=/etc/ssl/private/orbitiq.key
EOF

chmod 600 "$ENV_FILE"
ok ".env written (chmod 600)"

# ── Stage 3: SSL ──────────────────────────────────────────────────────────────
header "Stage 3 — SSL / TLS"

if [ "${USE_LETSENCRYPT:-n}" = "y" ] && [ "${DOMAIN:-localhost}" != "localhost" ]; then
    info "Obtaining Let's Encrypt certificate for ${DOMAIN}..."
    if command -v certbot &>/dev/null; then
        certbot certonly --standalone -d "$DOMAIN" --agree-tos --non-interactive \
            --email "admin@${DOMAIN}" 2>&1 | tee -a "$LOG_FILE" || warn "certbot failed — check DNS"
        SSL_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
        SSL_KEY="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
        if [ -f "$SSL_CERT" ]; then
            echo "" >> "$ENV_FILE"
            echo "SSL_CERT_PATH=${SSL_CERT}" >> "$ENV_FILE"
            echo "SSL_KEY_PATH=${SSL_KEY}" >> "$ENV_FILE"
            ok "Let's Encrypt certificate obtained: $SSL_CERT"
        else
            warn "Let's Encrypt failed — falling back to self-signed"
            USE_LETSENCRYPT="n"
        fi
    else
        warn "certbot not installed — install with: apt-get install certbot"
        USE_LETSENCRYPT="n"
    fi
fi

if [ "${USE_LETSENCRYPT:-n}" != "y" ]; then
    info "Generating self-signed certificate..."
    CERT_DIR="${REPO_ROOT}/deployment/docker/ssl"
    mkdir -p "$CERT_DIR"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "${CERT_DIR}/orbitiq.key" \
        -out "${CERT_DIR}/orbitiq.crt" \
        -subj "/CN=${DOMAIN:-localhost}/O=ORBITIQ-X/C=IN" \
        2>/dev/null
    echo "" >> "$ENV_FILE"
    echo "SSL_CERT_PATH=${CERT_DIR}/orbitiq.crt" >> "$ENV_FILE"
    echo "SSL_KEY_PATH=${CERT_DIR}/orbitiq.key" >> "$ENV_FILE"
    ok "Self-signed certificate created"
fi

# ── Stage 4: Deploy ───────────────────────────────────────────────────────────
header "Stage 4 — Deploying Docker Stack"
info "Starting all services..."

cd "$REPO_ROOT"
docker compose -f deployment/docker/docker-compose.prod.yml up -d 2>&1 | tee -a "$LOG_FILE"

info "Waiting 30s for services to initialise..."
sleep 30

info "Running health check..."
bash deployment/scripts/health-check.sh || warn "Some services not yet healthy — check logs"

echo ""
ok "Setup complete. Log: $LOG_FILE"
echo ""
echo -e "${BOLD}Next step: run the credential validator${NC}"
echo "  python3 deployment/15a/validate.py"
echo ""
