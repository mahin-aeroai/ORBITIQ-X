# ORBITIQ-X — Redis Activation Guide
## Phase 18 — Digital Twin Activation

This guide walks through enabling Redis on Railway and activating the Digital Twin.

---

## Why Redis Matters

| Feature | Without Redis | With Redis |
|---|---|---|
| Conjunction SSE alerts | Polling fallback (15s) | Real-time push |
| Digital Twin positions | Not initialised | Live TTL cache (15min) |
| Scheduler coordination | APScheduler memory | Distributed NX lock |
| TLE hot cache | PostgreSQL queries | Sub-millisecond reads |
| Density map | In-memory only | Shared across workers |

---

## Step 1 — Add Redis to Railway

### Option A — Railway Redis Plugin (Recommended)
1. Open your ORBITIQ-X Railway project
2. Click **+ New** → **Database** → **Add Redis**
3. Railway automatically sets `REDIS_URL` in your service's env vars
4. Redeploy the backend service

### Option B — External Redis (Redis Cloud, Upstash, etc.)
1. Create a Redis instance at [Redis Cloud](https://redis.com/try-free/) or [Upstash](https://upstash.com/)
2. Copy the connection URL (format: `redis://default:<password>@<host>:<port>`)
3. In Railway: **Variables** → Add `REDIS_URL` = your connection URL
4. Redeploy the backend service

---

## Step 2 — Verify Connection

After redeployment, check connection status:

```bash
curl https://orbitiq-x-production.up.railway.app/api/v1/digital-twin/redis-status
```

Expected response when connected:
```json
{
  "connected": true,
  "status": "healthy",
  "uptime_s": 42.3,
  "last_error": null,
  "connection_attempts": 1,
  "impact_if_down": []
}
```

---

## Step 3 — Activate Digital Twin

Once Redis is connected, trigger the first propagation cycle:

```bash
curl -X POST https://orbitiq-x-production.up.railway.app/api/v1/digital-twin/activate \
  -H "Authorization: Bearer <your-jwt-token>"
```

This propagates all 29,198 tracked objects to the current epoch using SGP4.
Expected duration: 30–120 seconds.

Monitor progress:
```bash
curl https://orbitiq-x-production.up.railway.app/api/v1/digital-twin/status
```

---

## Step 4 — Trigger Catalog Sync

For fresh TLE data followed by automatic propagation:

```bash
# Incremental (last 24h changes, ~2 min)
curl -X POST "https://orbitiq-x-production.up.railway.app/api/v1/digital-twin/catalog-sync?mode=incremental" \
  -H "Authorization: Bearer <token>"

# Full sync (all 29,198 objects, ~15 min)
curl -X POST "https://orbitiq-x-production.up.railway.app/api/v1/digital-twin/catalog-sync?mode=full" \
  -H "Authorization: Bearer <token>"
```

---

## Manual Reconnect (Without Redeployment)

If Redis becomes temporarily unavailable and reconnects:

```bash
curl -X POST https://orbitiq-x-production.up.railway.app/api/v1/digital-twin/redis-reconnect \
  -H "Authorization: Bearer <token>"
```

Or use the **↻ Reconnect Redis** button in the System Status page (`/system`).

---

## Redis Key Schema

| Key Pattern | Content | TTL |
|---|---|---|
| `twin:state:{norad_id}` | Live propagated satellite state (JSON) | 15 min |
| `twin:density:current` | Orbital density map snapshot | 1 hour |
| `twin:health:current` | Space environment health metrics | 1 hour |
| `twin:forecast:{norad_id}` | Orbit forecast cache | 1 hour |
| `orbitiq:sync:lock` | Distributed scheduler lock (NX) | Per job |
| `orbitiq:conjunction:alerts` | Pub/Sub channel for SSE alerts | N/A |
| `orbitiq:sync:last_report` | Last catalog sync report | 24 hours |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `REDIS_URL not configured` | Env var missing | Add `REDIS_URL` to Railway Variables |
| `Connection refused` | Wrong host/port | Verify URL format: `redis://default:<pass>@<host>:<port>` |
| `WRONGPASS` | Wrong password | Regenerate Redis credentials |
| `Connection timeout` | Firewall/VPC | Use Railway Redis plugin (same VPC) |
| Reconnects every 60s | Network instability | Check Railway Redis plugin status |

---

## Platform Status After Redis Activation

```
redis:          healthy    connected
digital_twin:   operational  29,198 objects propagated
sse_alerts:     active     real-time push enabled
scheduler_lock: distributed  NX lock operational
tle_cache:      hot        sub-ms reads
```
