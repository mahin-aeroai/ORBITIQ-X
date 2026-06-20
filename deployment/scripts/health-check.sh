#!/usr/bin/env bash
# =============================================================================
# ORBITIQ-X — Health Check Script
# =============================================================================
# Verifies all services in the dev stack are healthy.
# Usage: ./deployment/scripts/health-check.sh
# =============================================================================
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0

log_info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $*"; PASS=$((PASS+1)); }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_fail()    { echo -e "${RED}[FAIL]${NC}  $*"; FAIL=$((FAIL+1)); }

check_http() {
  local name="$1"
  local url="$2"
  local expected_code="${3:-200}"

  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")

  if [[ "$code" == "$expected_code" ]]; then
    log_success "$name ($url) → HTTP $code"
  else
    log_fail "$name ($url) → HTTP $code (expected $expected_code)"
  fi
}

check_tcp() {
  local name="$1"
  local host="$2"
  local port="$3"

  if nc -z -w3 "$host" "$port" 2>/dev/null; then
    log_success "$name ($host:$port) → TCP open"
  else
    log_fail "$name ($host:$port) → TCP refused/timeout"
  fi
}

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  ORBITIQ-X Service Health Check              ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ─── Infrastructure ────────────────────────────────────────────────────────────
log_info "Checking infrastructure services..."
check_tcp  "PostgreSQL"    "localhost" "5432"
check_tcp  "Redis"         "localhost" "6379"
check_http "Neo4j Browser" "http://localhost:7474" "200"
check_tcp  "Neo4j Bolt"    "localhost" "7687"
check_http "Weaviate"      "http://localhost:8080/v1/.well-known/ready" "200"
check_http "InfluxDB"      "http://localhost:8086/health" "200"
check_http "MinIO API"     "http://localhost:9000/minio/health/live" "200"

# ─── Monitoring ───────────────────────────────────────────────────────────────
log_info "Checking monitoring services..."
check_http "Prometheus"    "http://localhost:9090/-/healthy" "200"
check_http "Grafana"       "http://localhost:3001/api/health" "200"

# ─── Application ──────────────────────────────────────────────────────────────
log_info "Checking application services..."
check_http "Backend API"   "http://localhost:8000/health" "200"
check_http "Frontend"      "http://localhost:3000" "200"

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}─────────────────────────────────────────────${NC}"
echo -e "${GREEN}Passed: $PASS${NC}  ${RED}Failed: $FAIL${NC}"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo -e "${RED}❌ Some services are not healthy. Check docker compose logs.${NC}"
  echo -e "   Run: docker compose -f deployment/docker/docker-compose.dev.yml logs --tail=50"
  exit 1
else
  echo -e "${GREEN}✅ All services are healthy. ORBITIQ-X is operational.${NC}"
  exit 0
fi
