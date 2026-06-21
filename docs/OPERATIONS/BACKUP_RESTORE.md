# ORBITIQ-X — Backup & Restore Procedures

## Automated Backup

```bash
# Run backup (all components)
./deployment/scripts/backup.sh

# PostgreSQL only
./deployment/scripts/backup.sh --postgres-only

# Dry run (see what would happen)
./deployment/scripts/backup.sh --dry-run

# Schedule via cron (2 AM daily)
echo "0 2 * * * /opt/orbitiq/deployment/scripts/backup.sh >> /var/log/orbitiq-backup.log 2>&1" | crontab -
```

Backups are stored in `/backups/YYYY-MM-DD_HH-MM-SS/` with a 30-day retention window.

## PostgreSQL Restore

```bash
# List available backups
ls /backups/

# Restore from backup
BACKUP_DIR=/backups/2026-06-21_02-00-00
pg_restore \
  --host=localhost --port=5432 \
  --username=orbitiq --dbname=orbitiq_db \
  --clean --if-exists \
  "${BACKUP_DIR}/postgres_orbitiq_db.dump"

# Verify restore
python migrate.py status
```

## Neo4j Restore

```bash
# Stop Neo4j
docker compose stop neo4j

# Restore from tar.gz
BACKUP_FILE=/backups/2026-06-21_02-00-00/neo4j_backup.tar.gz
docker exec orbitiq-neo4j-prod \
  neo4j-admin database restore \
  --from-path=/backups \
  --database=orbitiq \
  --overwrite-destination=true

# Restart
docker compose start neo4j
```

## Redis Restore

Redis uses AOF + RDB. On catastrophic failure:
1. Stop Redis: `docker compose stop redis`
2. Copy RDB: `cp /backups/YYYY-MM-DD/redis_dump.rdb /var/lib/docker/volumes/orbitiq_prod_redis_data/_data/dump.rdb`
3. Start Redis: `docker compose start redis`

## Recovery Time Estimates

| Scenario | Estimate |
|---|---|
| PostgreSQL restore (full 50K catalog) | ~10 min |
| Neo4j graph restore | ~15 min |
| Redis restore | < 2 min |
| Full stack rebuild | ~30 min |
