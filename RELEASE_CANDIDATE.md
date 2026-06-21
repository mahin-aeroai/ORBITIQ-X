# ORBITIQ-X Release Candidate — v0.1.0

**Aerospace Foundation Model for Space Intelligence**

> Production readiness checklist. All items must be ✅ before deployment.

---

## Platform Status

| Domain | Status | Tests |
|---|---|---|
| Infrastructure & APIs | ✅ 100% | — |
| SSA Backend | ✅ 100% | Covered |
| Orbital Digital Twin | ✅ 100% | Covered |
| Conjunction Engine | ✅ 100% | Covered |
| Mission Control Dashboard | ✅ 99% | — |
| Authentication & RBAC | ✅ 100% | 46 tests |
| Observability & Monitoring | ✅ 100% | 36 tests |
| Failure Resilience | ✅ 100% | 23 tests |
| Alert Publishing Pipeline | ✅ 100% | 13 tests |
| **Total** | **99%** | **118/118 passing** |

---

## Pre-Deployment Checklist

### 🔐 Security

- [ ] `ORBITIQ_SECRET_KEY` set to 64-char random (never `CHANGE_ME`)
  ```bash
  openssl rand -hex 32
  ```
- [ ] All `CHANGE_ME` values in `.env` replaced with production secrets
- [ ] `POSTGRES_PASSWORD` ≥ 20 chars, not shared with any other service
- [ ] `REDIS_PASSWORD` set and TLS configured if over network
- [ ] `NEO4J_PASSWORD` changed from default
- [ ] `GRAFANA_ADMIN_PASSWORD` changed from default
- [ ] `WEAVIATE_API_KEY` set (not empty)
- [ ] `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are valid and rate-limited
- [ ] `BACKEND_CORS_ORIGINS` set to exact production frontend domain
- [ ] JWT `BACKEND_JWT_EXPIRE_MINUTES` ≤ 60 (do not increase for prod)
- [ ] TLS certificate installed and valid (check expiry)
- [ ] `ORBITIQ_ENV=production` in `.env` (enables HSTS, TrustedHost middleware)
- [ ] `BACKEND_RELOAD=false` in production
- [ ] `.env` file not committed to git (`git status` shows no .env)
- [ ] `TRUSTED_HOSTS` set to actual production hostname

### 🗄️ Database

- [ ] PostgreSQL migrations applied: `python migrate.py upgrade head`
- [ ] Migration status verified: `python migrate.py status`
- [ ] PostgreSQL `max_connections` ≥ 200 (4 workers × 20 pool + headroom)
- [ ] PostgreSQL WAL archiving enabled for PITR
- [ ] Redis `appendonly yes` and `appendfsync everysec` in redis.conf
- [ ] Neo4j backup plugin configured
- [ ] First backup completed and restore tested

### 🏗️ Infrastructure

- [ ] Docker resource limits set in `docker-compose.prod.yml`
- [ ] All health checks passing: `./deployment/scripts/health-check.sh`
- [ ] `GET /health` returns `{"status": "operational"}`
- [ ] `GET /api/v1/platform/health` returns `{"overall": "healthy"}`
- [ ] Prometheus scraping metrics: `http://localhost:9090/targets`
- [ ] Grafana dashboard visible and showing data
- [ ] Alert rules loaded: `http://localhost:9090/rules`

### 🔄 CI/CD

- [ ] GitHub Actions CI passes on `main` branch
- [ ] Docker image builds succeed
- [ ] Security scan shows no HIGH/CRITICAL CVEs in direct dependencies
- [ ] TypeScript: 0 errors
- [ ] Next.js build: ✓ 9/9 pages

### 📊 Observability

- [ ] Structured logs emitting JSON in production
- [ ] OpenTelemetry traces visible in collector (or console in dev)
- [ ] Prometheus metrics exposed at `/metrics`
- [ ] Alert rules loaded (15 rules across 4 groups)
- [ ] PagerDuty / Slack alertmanager integration configured (if applicable)
- [ ] `/api/v1/platform/health` endpoint accessible
- [ ] System Status page loads (`/system`)

### 🛡️ Auth & RBAC

- [ ] First admin user created via bootstrap: `POST /api/v1/auth/register`
- [ ] Login tested end-to-end from browser
- [ ] Role-based nav working (analyst cannot see Foundation)
- [ ] JWT refresh working (check browser 401 → auto-refresh → retry)
- [ ] Account lockout after 5 failed logins tested
- [ ] Logout revokes refresh token (POST /api/v1/auth/logout)

### 💾 Backup & Recovery

- [ ] Backup script executable: `chmod +x deployment/scripts/backup.sh`
- [ ] Test backup runs: `./deployment/scripts/backup.sh --dry-run`
- [ ] Production backup verified: `./deployment/scripts/backup.sh`
- [ ] Restore procedure tested from backup (see `docs/OPERATIONS/BACKUP_RESTORE.md`)
- [ ] Cron job configured: `0 2 * * * /opt/orbitiq/deployment/scripts/backup.sh`
- [ ] Backup storage is offsite (S3, GCS, or external NAS)
- [ ] Retention policy: 30-day rolling window

### 📡 External API Integrations

- [ ] Space-Track credentials configured (`SPACETRACK_IDENTITY`, `SPACETRACK_PASSWORD`)
- [ ] Initial catalog sync successful: `POST /api/v1/catalog/sync/trigger`
- [ ] TLE data visible: `GET /api/v1/catalog/health`
- [ ] Digital twin propagation running: `GET /api/v1/digital-twin/status`
- [ ] NOAA SWPC reachable: `GET /api/v1/space-weather/health`
- [ ] NASA API key set (optional: `NASA_API_KEY`)

### 📖 Documentation

- [ ] `docs/OPERATIONS/DEPLOYMENT.md` reviewed
- [ ] `docs/OPERATIONS/RUNBOOK.md` accessible to ops team
- [ ] `docs/OPERATIONS/INCIDENT_RESPONSE.md` shared with on-call
- [ ] Admin user credentials stored in team password manager
- [ ] On-call rotation configured

---

## Recovery Time Objectives

| Scenario | RTO | Procedure |
|---|---|---|
| Backend pod crash | < 30s | Docker restart=always |
| Redis unavailable | < 2min | Graceful degradation; no data loss |
| Neo4j unavailable | < 5min | Graph features degrade; SSA continues |
| PostgreSQL unavailable | ~10min | Restore from backup |
| Full host failure | ~30min | Restore from backup + re-deploy |

---

## Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Lead Engineer | Mahin Nandipa | | |
| Security Review | | | |
| Ops Lead | | | |

---

*Generated: Phase 14C — Deployment Hardening & Release Candidate*
*Platform: ORBITIQ-X v0.1.0 | Build: d099ec1*
