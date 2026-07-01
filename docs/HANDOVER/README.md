# ORBITIQ-X — Session Handover Brief
**Date:** 2026-07-01  
**Handover from:** Session `2026-06-30` — Platform Stabilisation + Entity Browser Activation  
**Status:** Platform healthy. Space-Track account suspended, awaiting reinstatement. Ingestion pipeline audited and ready.

---

## What is ORBITIQ-X

A production-grade **Aerospace Intelligence Platform** — "Bloomberg Terminal for Aerospace" / Aerospace Knowledge Universe (AKU).

- **Backend:** FastAPI on Railway → https://orbitiq-x-production.up.railway.app  
- **Frontend:** Next.js 14 on Vercel → https://orbitiq-x.vercel.app  
- **Repo:** https://github.com/mahin-aeroai/ORBITIQ-X  
- **Admin:** `admin3` / `OrbitIQ2026!`  
- **Current version:** `v0.5.1`  
- **API Docs:** https://orbitiq-x-production.up.railway.app/api/v1/docs  

---

## Platform State Right Now

| Service | Status | Notes |
|---|---|---|
| PostgreSQL | ✅ HEALTHY | 29,198 satellites · 15 Alembic migrations applied |
| Redis | ✅ HEALTHY | Connected · Digital Twin meta cache active |
| Neo4j Aura | ✅ HEALTHY | 29,266 nodes · 118,681 relationships |
| Qdrant | ✅ HEALTHY | 252 chunks · aerospace_docs · 384-dim |
| Digital Twin | ✅ OPERATIONAL | 29,184 objects propagated via SGP4 |
| GraphRAG | ✅ HEALTHY | 20/20 benchmark (100%) |
| Agent System | ✅ HEALTHY | 7 specialists · Claude Sonnet 4.6 |
| Scheduler | ✅ RUNNING | 5 jobs: 15min DT · 2h incremental · 6h full sync · 6h conjunctions · 6h graph |
| MinIO | ⚠️ UNAVAILABLE | Not provisioned, not load-bearing, excluded from health rollup |
| Space-Track | ⚠️ SUSPENDED | Account suspended 2026-06-30 — email sent — awaiting reinstatement |

---

## Immediate Blockers

### 1. Space-Track Account Suspended (CRITICAL)
**What happened:** `GET /api/v1/catalog/health` was calling `fetcher.health_check()` which hit `/basicspacedata/query/class/gp/LIMIT/1` on every request. Three frontend components poll this every 60s. Space-Track allows GP access once per hour. Account suspended at 5:10 AM 2026-06-30.  
**Fixed:** The live GP probe was removed from the health endpoint (commit `8d9838d`). Health now reports based on credentials presence only.  
**Action needed:** Reply received from Space-Track is pending. Email was sent to admin@space-track.org acknowledging the violation and stating the fix. Reinstatement expected on next business day.  
**Impact:** No TLE updates until reinstated. The 29,198 satellites already in PostgreSQL are valid, and the Digital Twin propagates from that local data — so the platform is otherwise fully functional.

---

## Roadmap — Where We Are

The Entity Browser activation plan (agreed roadmap):

| Step | Status | Notes |
|---|---|---|
| 1. Verify Contracts & Investments | ✅ Done | Working in Knowledge Universe page |
| 2. Confirm Entity Browser backend + UI | ✅ Done | "No entities found" rendered correctly |
| 3. Seed 18 flagship entities | ✅ Done | NASA · ESA · ISRO · SpaceX · Blue Origin · Rocket Lab · ULA · Falcon 9/Heavy/Starship/SLS/Ariane 6 · Artemis II · JWST · ISS · USA/India/France |
| 4. Execute live ingestion pipeline | ⏳ Blocked | Space-Track suspended. Ingestion code fully audited and fixed — ready to run |
| 5. Schedule periodic ingestion | ⏳ Pending | APScheduler already configured with 5 jobs |
| 6. Neo4j relationship enrichment | ⏳ Pending | Write Cypher using extension_data AQIDs |

**Step 4 trigger (once reinstated):**
```bash
# Small bounded test first — nasa_missions adapter (smallest dataset)
curl -X POST https://orbitiq-x-production.up.railway.app/api/v2/ingestion/adapters/nasa_missions/run \
  -H "Authorization: Bearer YOUR_JWT"

# Check result
GET /api/v2/ingestion/adapters/nasa_missions
```

**Step 6 — Neo4j enrichment example Cypher:**
```cypher
MATCH (a:AerospaceEntity {aqid: 'AQID-COMPANY-SPACEX'})
MATCH (b:AerospaceEntity {aqid: 'AQID-LAUNCH_VEHICLE-FALCON-9'})
MERGE (a)-[:MANUFACTURES {since: '2010-06-04', confidence: 0.95}]->(b)
```
Run via `POST /api/v1/knowledge-graph/execute` (admin only).

**Minor pending fix:**
`ProvenancePanel` in the entity detail page reads `entity.all_sources[]` but the seed only writes `primary_provenance`. Fix: in `GET /api/v2/entities/{aqid}`, merge `primary_provenance` into the `all_sources` array in the response serializer.

---

## Critical Engineering Rules (hard-won this session — read before touching anything)

### 1. SQLAlchemy `text()` + PostgreSQL JSONB casts need a SPACE
```python
# WRONG — SQLAlchemy's bind-param parser truncates the name at '::',
# leaves ':tags::jsonb' as literal text, asyncpg gets syntax error
text("INSERT ... VALUES (:tags::jsonb)")

# CORRECT — space before '::' is required
text("INSERT ... VALUES (:tags ::jsonb)")
```
Already fixed in: `entities.py`, `relationships.py`, `ingestion/orchestrator.py`, `ingestion/pipeline.py`, `provenance/service.py`.

### 2. Async/sync session separation
- **`entities.py`, `catalog.py`, `digital_twin.py`** etc. → use `AsyncSession` with `await pg.execute()`
- **`ProvenanceService`, `CAEMIngestionPipeline`, `IngestionOrchestrator`** → use **sync** psycopg2 session (unawaited `.execute()` throughout)
- **Background tasks** (`BackgroundTasks.add_task()`) run after the HTTP response — FastAPI closes the injected session before the callback runs. Always create a **fresh sync session inline** inside the background task, never reuse the request-scoped one.

### 3. `sa.DateTime` columns are timezone-naive
`aerospace_entities.created_at/updated_at/published_at` are `sa.DateTime` (no `timezone=True`).  
Always use `datetime.utcnow()` (naive), never `datetime.now(timezone.utc)` (aware).

### 4. The `src` namespace collision in orbital-engine
Five sibling directories (`agents/src`, `rag/src`, `orbital-engine/src`, etc.) all define a top-level package named `src`. Never use `from src.propagator import X` — it resolves to whichever sibling won the `sys.path` race.  
Use `_load_orbital_engine_module("propagator.sgp4_propagator")` from `orbital_state_service.py` or `conjunction_analysis_service.py` — this loads under the private `_orbital_engine_src.*` namespace via `importlib.util.spec_from_file_location`.

### 5. railway.toml watchPatterns must cover ALL Dockerfile COPY sources
The Dockerfile copies `backend/`, `orbital-engine/`, `agents/`, `rag/`, `scripts/`. All five must be in `watchPatterns` or commits touching only one of them silently never trigger a Railway redeploy.  
Current correct config:
```toml
watchPatterns = ["backend/**", "orbital-engine/**", "agents/**", "rag/**", "scripts/**", "railway.toml"]
```
This caused 3 wasted deploy cycles this session when a fix to `scripts/seed_flagship_entities.py` simply didn't deploy.

### 6. Space-Track API — NEVER call from health endpoints
`/basicspacedata/query/class/gp` may only be accessed once per hour per account.  
The `health_check()` method on `SpaceTrackFetcher` makes a live GP request — **do not call it from any endpoint that the frontend polls**. Only the scheduled sync jobs may call Space-Track.

### 7. Multi-worker Digital Twin state
`gunicorn --workers 2` means two separate Python processes with independent `_LIVE_STATES` dicts. After propagation, read `get_propagation_meta_shared()` (which falls back to Redis `twin:propagation_meta`) rather than checking local in-memory state only.

### 8. Frontend auth — always `getApiAccessToken()`
JWT lives in memory only (not localStorage). Key `orbitiq_token` is **never written to localStorage**. Always:
```typescript
import { getApiAccessToken } from "@/lib/api";
const token = getApiAccessToken();
headers: token ? { Authorization: `Bearer ${token}` } : {}
```

---

## Key Files Changed This Session

```
backend/app/api/v1/endpoints/entities.py          # CAEM CRUD + seed-flagship endpoint + JSONB fix
backend/app/api/v1/endpoints/relationships.py      # JSONB cast fix
backend/app/api/v1/endpoints/ingestion.py          # Background task: fresh sync session inline
backend/app/api/v1/endpoints/catalog.py            # Removed live Space-Track GP health probe
backend/app/api/v1/endpoints/platform.py           # MinIO excluded · shared DT meta · /status fix
backend/app/api/v1/endpoints/digital_twin.py       # get_twin_status uses get_propagation_meta_shared()
backend/app/api/v1/endpoints/infrastructure.py     # rootFetch() for /health and /ready
backend/app/caem/ingestion/orchestrator.py         # JSONB cast fix
backend/app/caem/ingestion/pipeline.py             # JSONB cast fix
backend/app/caem/provenance/service.py             # JSONB cast fix
backend/app/digital_twin/services/orbital_state_service.py  # Collision-proof loader · Redis meta cache
backend/app/services/conjunction_analysis_service.py         # Collision-proof loader
backend/app/db/redis_session.py                    # get_redis_status()
scripts/seed_flagship_entities.py                  # 18 flagship entities · datetime.utcnow() fix
railway.toml                                       # watchPatterns expanded to cover all 5 COPY dirs
frontend/src/lib/api.ts                            # getApiAccessToken() (was localStorage)
frontend/src/lib/caem-api.ts                       # getApiAccessToken() (was localStorage)
frontend/src/components/ssa/RedisStatusWidget.tsx  # /propagate endpoint · field names · error display
frontend/src/app/entities/page.tsx                 # SeedFlagshipButton · full error detail display
frontend/src/app/infrastructure/page.tsx           # rootFetch() · correct status mapping
frontend/src/app/intelligence-hub/page.tsx         # getApiAccessToken()
orbital-engine/src/{api,classifier,db,errors,ingest,metrics,reentry,relative_motion,scheduler}/__init__.py  # Added (were missing)
```

---

## Session Commit Log (2026-06-30)

| Commit | Description |
|---|---|
| `8d9838d` | URGENT: remove Space-Track GP probe from health endpoint |
| `4cded15` | Fix ingestion trigger: fresh sync session + exception logging |
| `402c5f8` | CRITICAL: railway.toml watchPatterns blocked timezone fix deploy |
| `8383755` | Seed script: datetime.utcnow() not datetime.now(timezone.utc) |
| `99596b4` | Root cause: :param::jsonb (no space) breaks SQLAlchemy bind parser |
| `67b1d9e` | Seed button: surface per-record error details in UI |
| `7e0f20d` | Seed endpoint: add exception handling + rollback + diagnostics |
| `f872b5c` | Add ::jsonb casts to INSERT statements |
| `a533236` | Seed Flagship Entities button in Entity Browser |
| `d4f94f3` | 18 flagship entities seed script + backend endpoint |
| `e4ffa8d` | MinIO excluded from platform health rollup |
| `0a7cd21` | Digital Twin: multi-worker status via Redis meta cache |
| `c7b86d6` | RedisStatusWidget: click-path error visibility |
| `705b9a7` | Root cause of src.propagator collision + 9 missing __init__.py |
| `f6e52b4` | Digital Twin: broken sys.path in Docker container |
| `7fbcf41` | Activate button called /activate not /propagate |
| `ac501f3` | Infrastructure page: rootFetch() for /health and /ready |
| `5a126f0` | Missing auth headers on 3 frontend components + caem-api.ts |
