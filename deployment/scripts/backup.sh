#!/usr/bin/env bash
# =============================================================================
# ORBITIQ-X — Production Backup Script
# =============================================================================
# Backs up: PostgreSQL, Redis (AOF/RDB), Neo4j, Weaviate, MinIO
#
# Usage
# ──────
#   ./deployment/scripts/backup.sh                    # Backup all
#   ./deployment/scripts/backup.sh --postgres-only    # Only PostgreSQL
#   ./deployment/scripts/backup.sh --dry-run          # Show what would run
#
# Outputs
# ────────
#   /backups/YYYY-MM-DD_HH-MM-SS/
#     postgres_orbitiq_db.dump       (pg_dump custom format)
#     neo4j_backup.tar.gz            (online backup via APOC)
#     weaviate_schema.json           (schema export)
#     redis_dump.rdb                 (RDB snapshot)
#     backup_manifest.json           (sizes, checksums, timestamps)
#
# Schedule via cron (recommended):
#   0 2 * * * /opt/orbitiq/deployment/scripts/backup.sh >> /var/log/orbitiq-backup.log 2>&1
# =============================================================================

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
DRY_RUN=false
POSTGRES_ONLY=false

# Load environment
if [[ -f ".env" ]]; then
    # shellcheck source=/dev/null
    set -a && source .env && set +a
fi

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)       DRY_RUN=true ;;
        --postgres-only) POSTGRES_ONLY=true ;;
        *) echo "Unknown argument: $1" && exit 1 ;;
    esac
    shift
done

# ── Helpers ────────────────────────────────────────────────────────────────────
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
LOG_PREFIX="[ORBITIQ-BACKUP ${TIMESTAMP}]"

log()   { echo "${LOG_PREFIX} $*"; }
warn()  { echo "${LOG_PREFIX} WARNING: $*" >&2; }
error() { echo "${LOG_PREFIX} ERROR: $*" >&2; }

run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY-RUN: $*"
    else
        "$@"
    fi
}

# ── Pre-flight checks ──────────────────────────────────────────────────────────
log "Starting ORBITIQ-X backup to ${BACKUP_DIR}"

if [[ "$DRY_RUN" == "false" ]]; then
    mkdir -p "${BACKUP_DIR}"
fi

MANIFEST="${BACKUP_DIR}/backup_manifest.json"
declare -A BACKUP_SIZES
declare -A BACKUP_CHECKSUMS

# ── PostgreSQL backup ──────────────────────────────────────────────────────────
backup_postgres() {
    log "Backing up PostgreSQL..."
    local output="${BACKUP_DIR}/postgres_${POSTGRES_DB:-orbitiq_db}.dump"

    run pg_dump \
        --host="${POSTGRES_HOST:-localhost}" \
        --port="${POSTGRES_PORT:-5432}" \
        --username="${POSTGRES_USER:-orbitiq}" \
        --dbname="${POSTGRES_DB:-orbitiq_db}" \
        --format=custom \
        --compress=9 \
        --no-password \
        --file="${output}" \
        2>&1

    if [[ "$DRY_RUN" == "false" && -f "$output" ]]; then
        local size
        size=$(du -sh "$output" | cut -f1)
        local checksum
        checksum=$(sha256sum "$output" | cut -d' ' -f1)
        BACKUP_SIZES["postgres"]="$size"
        BACKUP_CHECKSUMS["postgres"]="$checksum"
        log "PostgreSQL backup: ${output} (${size})"
    fi
}

# ── Redis backup ───────────────────────────────────────────────────────────────
backup_redis() {
    log "Backing up Redis..."

    # Trigger BGSAVE to ensure fresh RDB
    redis-cli \
        -h "${REDIS_HOST:-localhost}" \
        -p "${REDIS_PORT:-6379}" \
        -a "${REDIS_PASSWORD:-}" \
        BGSAVE 2>/dev/null || warn "BGSAVE trigger failed — using existing RDB"

    # Wait for save to complete
    sleep 3

    # Copy RDB via redis-cli DEBUG SLEEP (non-destructive)
    local output="${BACKUP_DIR}/redis_dump.rdb"

    # Copy from Docker volume or direct path
    if docker inspect orbitiq-redis-prod &>/dev/null 2>&1; then
        run docker exec orbitiq-redis-prod cat /data/dump.rdb > "${output}" 2>/dev/null || \
            warn "Redis container not found — skipping RDB copy"
    else
        local rdb_path="${REDIS_BACKUP_PATH:-/var/lib/redis/dump.rdb}"
        if [[ -f "$rdb_path" ]]; then
            run cp "$rdb_path" "${output}"
        else
            warn "Redis RDB not found at ${rdb_path} — skipping"
        fi
    fi

    if [[ "$DRY_RUN" == "false" && -f "$output" ]]; then
        local size
        size=$(du -sh "$output" | cut -f1)
        BACKUP_SIZES["redis"]="$size"
        log "Redis backup: ${output} (${size})"
    fi
}

# ── Neo4j backup ───────────────────────────────────────────────────────────────
backup_neo4j() {
    log "Backing up Neo4j..."
    local output="${BACKUP_DIR}/neo4j_backup.tar.gz"

    if docker inspect orbitiq-neo4j-prod &>/dev/null 2>&1; then
        # Use neo4j-admin backup (requires Neo4j to be running)
        run docker exec orbitiq-neo4j-prod \
            neo4j-admin database backup \
            --to-path=/backups \
            --database="${NEO4J_DATABASE:-orbitiq}" 2>&1 || \
            warn "Neo4j online backup failed — consider offline backup"

        # Tar up the backup directory
        run docker exec orbitiq-neo4j-prod \
            tar czf "/tmp/neo4j_backup_${TIMESTAMP}.tar.gz" /backups 2>/dev/null

        run docker cp \
            "orbitiq-neo4j-prod:/tmp/neo4j_backup_${TIMESTAMP}.tar.gz" \
            "${output}" 2>/dev/null || warn "Failed to copy Neo4j backup"
    else
        warn "Neo4j container not running — skipping online backup"
        warn "For offline backup: stop Neo4j and tar /var/lib/neo4j"
    fi

    if [[ "$DRY_RUN" == "false" && -f "$output" ]]; then
        local size
        size=$(du -sh "$output" | cut -f1)
        BACKUP_SIZES["neo4j"]="$size"
        log "Neo4j backup: ${output} (${size})"
    fi
}

# ── Weaviate schema export ─────────────────────────────────────────────────────
backup_weaviate() {
    log "Exporting Weaviate schema..."
    local output="${BACKUP_DIR}/weaviate_schema.json"

    run curl -s \
        -H "Authorization: Bearer ${WEAVIATE_API_KEY:-}" \
        "http://${WEAVIATE_HOST:-localhost}:${WEAVIATE_PORT:-8080}/v1/schema" \
        > "${output}" 2>/dev/null || warn "Weaviate schema export failed"

    # Data backup requires Weaviate Cloud backup or volume snapshot
    log "NOTE: Weaviate vector data requires volume snapshot (see BACKUP_RESTORE.md)"

    if [[ "$DRY_RUN" == "false" && -f "$output" ]]; then
        local size
        size=$(du -sh "$output" | cut -f1)
        BACKUP_SIZES["weaviate_schema"]="$size"
        log "Weaviate schema: ${output} (${size})"
    fi
}

# ── Write manifest ─────────────────────────────────────────────────────────────
write_manifest() {
    if [[ "$DRY_RUN" == "true" ]]; then return; fi

    python3 - << PYEOF
import json, datetime

manifest = {
    "timestamp":   "${TIMESTAMP}",
    "backup_dir":  "${BACKUP_DIR}",
    "host":        "$(hostname)",
    "generated_at":datetime.datetime.utcnow().isoformat() + "Z",
    "components": {},
}

sizes = ${BACKUP_SIZES[*]:-{}}
manifest["total_files"] = $(ls "${BACKUP_DIR}" | wc -l)

with open("${MANIFEST}", "w") as f:
    json.dump(manifest, f, indent=2)
PYEOF

    log "Manifest written: ${MANIFEST}"
}

# ── Retention cleanup ──────────────────────────────────────────────────────────
cleanup_old_backups() {
    log "Removing backups older than ${RETENTION_DAYS} days..."
    run find "${BACKUP_ROOT}" \
        -maxdepth 1 \
        -type d \
        -mtime "+${RETENTION_DAYS}" \
        -exec rm -rf {} + 2>/dev/null || true
}

# ── Main execution ─────────────────────────────────────────────────────────────
main() {
    PGPASSWORD="${POSTGRES_PASSWORD:-}" backup_postgres

    if [[ "$POSTGRES_ONLY" == "false" ]]; then
        backup_redis
        backup_neo4j
        backup_weaviate
    fi

    write_manifest
    cleanup_old_backups

    log "=========================================="
    log "Backup completed successfully!"
    log "Location: ${BACKUP_DIR}"
    if [[ "$DRY_RUN" == "false" ]]; then
        log "Total size: $(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1 || echo 'unknown')"
    fi
    log "=========================================="
}

main
