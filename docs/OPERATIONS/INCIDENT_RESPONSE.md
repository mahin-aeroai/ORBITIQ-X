# ORBITIQ-X — Incident Response Runbook

## Severity Levels

| Severity | Condition | Response Time |
|---|---|---|
| P1 | PostgreSQL down, platform inaccessible | Immediate |
| P2 | Redis down (SSE/cache degraded) | 30 min |
| P3 | Neo4j down (graph features degraded) | 2 hours |
| P4 | Scheduler stalled, sync delayed | Next business day |

## Common Incidents

### 1. Backend Returns 500s

```bash
# Check logs
docker logs orbitiq-backend-prod --tail=100

# Check health
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/platform/health | jq .

# Check platform health details
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/platform/health | jq .services
```

### 2. Conjunction Alerts Not Firing

```bash
# Check Redis pub/sub
redis-cli -a "$REDIS_PASSWORD" subscribe orbitiq:conjunction:alerts

# Check scheduler jobs
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/platform/status | jq .scheduler

# Check conjunction engine logs
docker logs orbitiq-backend-prod | grep "conjunction"
```

### 3. Digital Twin Propagation Stalled

```bash
# Check last propagation
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/digital-twin/status | jq .last_propagation

# Trigger manual propagation (via scheduler)
# The scheduler runs every 15 min — check if it's running

# Check Prometheus alert
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname == "DigitalTwinPropagationStalled")'
```

### 4. Database Connection Exhausted

```bash
# Check PostgreSQL connections
psql -h localhost -U orbitiq -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Check pool settings in .env
grep POSTGRES_POOL_SIZE .env

# Restart backend to recycle connections
docker compose restart backend
```

### 5. Authentication Spike / Possible Attack

```bash
# Check auth failure rate in Prometheus
curl 'http://localhost:9090/api/v1/query?query=rate(orbitiq_auth_failures_total[5m])'

# Check audit logs (requires DB access)
psql -h localhost -U orbitiq -c \
  "SELECT ip_address, count(*), min(logged_at) FROM audit_logs 
   WHERE action='login_failed' AND logged_at > NOW() - INTERVAL '15 minutes'
   GROUP BY ip_address ORDER BY count DESC LIMIT 20;"

# Block suspicious IP (if needed)
iptables -A INPUT -s <IP> -j DROP
```

## Escalation

1. Check `/system` dashboard for overall platform status
2. Review Grafana alerts: `http://localhost:3001`
3. Review structured logs in Grafana Loki (if configured)
4. If data corruption suspected: **do not restart** — snapshot first
