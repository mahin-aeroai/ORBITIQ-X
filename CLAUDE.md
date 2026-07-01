# CLAUDE.md — ORBITIQ-X Working Instructions

This document is the authoritative onboarding reference for AI assistants working on ORBITIQ-X.
Read this before making any changes. Update this file when the engineering focus shifts.

---

## Project Overview

ORBITIQ-X is a production-grade Aerospace Intelligence Platform —
the **"Bloomberg Terminal for Aerospace"** / Aerospace Knowledge Universe (AKU).

- **Space Situational Awareness**: 29,198 tracked RSOs with real names
- **Knowledge Graph**: Neo4j with 29,266 nodes · 118,681 relationships
- **GraphRAG**: 252-chunk corpus across 16 aerospace domains · 20/20 benchmark
- **Multi-Agent AI**: 7 specialist agents powered by Claude Sonnet 4.6
- **CAEM**: Canonical Aerospace Entity Model — 39 entity classes, 76 relationship types
- **Entity Browser**: 18 flagship entities live (NASA, SpaceX, ESA, ISRO, ISS, JWST…)
- **Digital Twin**: 29,184 objects propagated via SGP4, Redis-backed, multi-worker aware
- **Mission Control**: Next.js 14 with animated globe and live data

**Current version:** `v0.5.0`
**Backend:** https://orbitiq-x-production.up.railway.app
**Frontend:** https://orbitiq-x.vercel.app
**API Docs:** https://orbitiq-x-production.up.railway.app/api/v1/docs
**GitHub:** https://github.com/mahin-aeroai/ORBITIQ-X

---

## Admin Credentials

- **Username:** `admin3`
- **Password:** `OrbitIQ2026!`

---

## Architecture

```
PostgreSQL (Railway)     ← 29,198 satellites, 105,755 TLE records, aerospace_entities
Neo4j Aura               ← 29,266 nodes, 118,681 relationships
Qdrant Cloud             ← 252 chunks, aerospace_docs, 384-dim
Redis (Railway)          ← CONNECTED — Digital Twin state, SSE pub/sub
FastAPI (Railway)        ← ~160 endpoints, gunicorn 2 workers, uvicorn worker class
Next.js (Vercel)         ← 12 pages, TanStack Query
CAEM                     ← backend/app/caem/ — knowledge architecture layer
orbital-engine           ← /app/orbital-engine/ — SGP4 propagation library
```

## Service Connections

| Service | Connection | Notes |
|---|---|---|
| PostgreSQL | Railway plugin | `DATABASE_URL` env var, asyncpg driver |
| Neo4j | `neo4j+s://bff8c462.databases.neo4j.io` | DB + User: `bff8c462` |
| Qdrant | `2435500e-...us-west-1-0.aws.cloud.qdrant.io` | Collection: `aerospace_docs`, 384-dim |
| Redis | Railway plugin | REDIS_URL set and working |
| Space-Track | `www.space-track.org` | Account SUSPENDED as of 2026-06-30 — awaiting reinstatement |
| Anthropic | API | `ANTHROPIC_API_KEY`, model: `claude-sonnet-4-6` |

---

## Current Phase

**Phase 20 — Entity Knowledge Enrichment** (ready to begin)

18 flagship entities are live in the Entity Browser. The next phase:
1. Trigger live ingestion pipeline (once Space-Track reinstated)
2. Schedule periodic ingestion
3. Neo4j relationship enrichment for the 18 seeded entities
4. Fix provenance panel (merge `primary_provenance` into `all_sources` in GET `/entities/{aqid}`)
5. Expand Knowledge Universe seed data

See ROADMAP.md for the full plan.

---

## Engineering Principles

1. **Evidence-based debugging only.** Read the actual error before proposing a fix.
2. **No speculative fixes.** If root cause is not confirmed, say so.
3. **Minimal targeted changes.** Fix the specific failure. Do not refactor surrounding code.
4. **Preserve existing architecture.** Schema, API contracts, middleware stack are stable.
5. **Extension over replacement.** Add to CAEM schemas and Neo4j relationships. Never redesign.
6. **Production quality.** Every commit must work in production.
7. **Knowledge first.** Every new capability integrates into the Aerospace Knowledge Graph.

---

## CRITICAL PITFALLS — READ BEFORE TOUCHING

### 1. SQLAlchemy `text()` bind params + PostgreSQL type casts
**`:param::jsonb` (no space) breaks SQLAlchemy's bind parameter parser.**
The parser stops scanning the parameter name one character early, leaving
literal `:name::jsonb` uncompiled text in the SQL, which asyncpg rejects as
"syntax error at or near `:`". Always use `:param ::jsonb` (with a space before `::`).

This affects: `entities.py`, `relationships.py`, `ingestion/pipeline.py`,
`ingestion/orchestrator.py`, `provenance/service.py` — all already fixed.
The rule: any `text()` SQL with a PostgreSQL cast must have a space: `:col ::jsonb`, `:val ::text`.

### 2. Datetime: always timezone-naive for `sa.DateTime` columns
`aerospace_entities.created_at/updated_at/published_at` are `sa.DateTime` (no timezone).
Always use `datetime.utcnow()` — never `datetime.now(timezone.utc)`.
asyncpg cannot bind timezone-aware datetimes to `TIMESTAMP WITHOUT TIME ZONE` columns.

### 3. Async session vs sync session — KNOW WHICH ONE YOU NEED
- **Async session** (`get_pg_session`, `AsyncSession`): for FastAPI `async def` endpoints that use `await pg.execute()`
- **Sync session** (`get_sync_pg_session`, plain `Session`): required by `ProvenanceService`, `CAEMIngestionPipeline`, `IngestionOrchestrator` — all use unawaited `self.pg.execute()` internally

Passing an async session to sync code (or vice versa) produces silent failures or confusing errors.
Background tasks must create their own fresh sync session inline — they cannot reuse a FastAPI-injected session because FastAPI closes it when the HTTP response is sent, before the background task runs.

### 4. Gunicorn multi-worker state — use Redis for shared state
`--workers 2` means two separate OS processes, each with its own Python memory.
Module-level variables (like `_LIVE_STATES` in `orbital_state_service.py`) are per-process.
Any state that needs to be visible across workers (Digital Twin propagation counts, scheduler locks)
must go through Redis. Use `get_propagation_meta_shared()` not `get_propagation_meta()` in status endpoints.

### 5. railway.toml watchPatterns must cover ALL Dockerfile COPY sources
`Dockerfile.railway` COPYs: `backend/`, `orbital-engine/`, `agents/`, `rag/`, `scripts/`.
If `watchPatterns` omits any of these, commits touching only that directory trigger NO redeploy.
Current correct watchPatterns: `backend/**`, `orbital-engine/**`, `agents/**`, `rag/**`, `scripts/**`, `railway.toml`.

### 6. orbital-engine / agents / rag — namespace collision on `src`
These sibling directories each define their own top-level package named `src`. Multiple services insert their directory at `sys.path[0]`. Use `_load_orbital_engine_module()` in `orbital_state_service.py` and `conjunction_analysis_service.py` — never import orbital-engine via `from src.X import Y`.

### 7. Space-Track API usage policy
**DO NOT poll Space-Track from health checks or frontend-triggered endpoints.**
The GP endpoint (`/basicspacedata/query/class/gp`) may only be queried **once per hour**.
Only the scheduled sync jobs (6h full, 2h incremental) may call Space-Track.
The account was suspended on 2026-06-30 for health-check polling every 60 seconds.

### 8. Vercel build failures
`ignoreBuildErrors: true` in `next.config.js` **must stay true**.

### 9. Alembic on Railway PostgreSQL 18
Always use `AUTOCOMMIT` isolation level. GIN indexes must use `op.execute()`, not `op.create_index()`.
Widen `alembic_version` to `VARCHAR(64)` BEFORE running alembic (`entrypoint.sh` does this).

### 10. CAEM extension data
Never add entity-class columns to `aerospace_entities`. Always use `extension_data` JSONB.
Never use raw relationship type strings. Always use `RelationshipType` enum.

### 11. Neo4j property naming
Neo4j uses camelCase: `noradId`, `perigeeKm`, `apogeeKm`
PostgreSQL uses snake_case: `norad_id`, `perigee_km`, `apogee_km`

### 12. Schema persistence
`rag/src/models/schemas.py` manual patches in Railway shell **DO NOT persist across deploys**.
The repo version is authoritative.

---

## CAEM — Critical Architecture

Lives at `backend/app/caem/`. Read before touching any entity-related code.

### AQID System
Every entity has an immutable AQID: `AQID-{CLASS}-{SLUG}`
```python
from caem import generate_aqid, validate_aqid, EntityClass
aqid = generate_aqid(EntityClass.COMPANY, "SpaceX")  # → "AQID-COMPANY-SPACEX"
```

### Four-Layer Architecture
| Layer | System | What lives here |
|---|---|---|
| Master Data | PostgreSQL `aerospace_entities` | All fields, `extension_data` JSONB |
| Relationships | Neo4j | Typed directed edges with temporal properties |
| Knowledge | Qdrant `aerospace_docs` | Embedded chunks for semantic retrieval |
| Intelligence | Frontend entity pages | AI summaries, graph explorer, timeline |

### Key CAEM Files
| File | Purpose |
|---|---|
| `backend/app/caem/base.py` | `BaseAerospaceEntity`, AQID, `ProvenanceRecord`, confidence scoring |
| `backend/app/caem/entities.py` | 31 Pydantic extension schemas + `EXTENSION_REGISTRY` |
| `backend/app/caem/relationships.py` | 76 `RelationshipType` values, Cypher builder |
| `backend/app/caem/graph/neo4j_schema.py` | Idempotent Neo4j schema, GDS projections, batch upsert |
| `backend/app/caem/ingestion/pipeline.py` | 7-stage ingestion pipeline (sync session) |
| `backend/app/caem/ingestion/orchestrator.py` | Adapter registry, schedule, pipeline bridge (sync session) |
| `backend/app/caem/provenance/service.py` | ProvenanceService (sync session) |

---

## Key File Locations

| File | Purpose |
|---|---|
| `backend/app/api/v1/endpoints/catalog.py` | `/catalog/satellites` with regime compute + type normalization |
| `backend/app/api/v1/endpoints/entities.py` | CAEM entity CRUD + `seed-flagship` endpoint |
| `backend/app/api/v1/endpoints/ingestion.py` | `/api/v2/ingestion` — manual trigger (background sync session) |
| `backend/app/api/v1/endpoints/platform.py` | Platform health rollup (MinIO excluded) |
| `backend/app/api/v1/endpoints/digital_twin.py` | Digital Twin status, propagation, Redis (api/v1) |
| `backend/app/digital_twin/services/orbital_state_service.py` | SGP4 propagation, `_load_orbital_engine_module()`, Redis meta cache |
| `backend/app/services/catalog_scheduler.py` | APScheduler jobs — 15min DT, 2h incremental, 6h full sync |
| `backend/app/services/spacetrack_fetcher.py` | Space-Track HTTP client — DO NOT call from health endpoints |
| `scripts/seed_flagship_entities.py` | 18 flagship entity seed records |
| `frontend/src/lib/api.ts` | All API functions + `getApiAccessToken()` (in-memory JWT store) |
| `frontend/src/lib/caem-api.ts` | CAEM API client (uses `getApiAccessToken()`) |
| `frontend/src/app/entities/page.tsx` | Entity Browser + SeedFlagshipButton |
| `frontend/src/components/ssa/RedisStatusWidget.tsx` | System Status bottom panel + Digital Twin activation |
| `railway.toml` | watchPatterns — must cover all Dockerfile COPY sources |

---

## Auth Token Pattern

The frontend stores the JWT in memory only (not localStorage). Always use:
```typescript
import { getApiAccessToken } from "@/lib/api";
const token = getApiAccessToken();
headers: token ? { Authorization: `Bearer ${token}` } : {}
```
Never use `localStorage.getItem('orbitiq_token')` — that key is never written.

---

## Railway Shell — Python Helper

```python
import sys, os, asyncio
sys.path.insert(0, '/app/app')
os.environ.setdefault('NEO4J_USER', 'bff8c462')

async def main():
    from app.db.session import init_db, get_engine
    from app.graph.connection import init_neo4j_driver, execute_read, execute_write
    from sqlalchemy import text
    await init_db()
    engine = get_engine()
    await init_neo4j_driver()
    # ... your code

asyncio.run(main())
```

---

## Phase 17 Roadmap Status

| Sub-Phase | Scope | Status |
|---|---|---|
| 17.1 | Canonical Aerospace Entity Model | ✅ Complete |
| 17.2 | Universal Relationship Ontology | ✅ Complete |
| 17.3 | Provenance and Versioning | ✅ Complete |
| 17.4 | Knowledge Ingestion Framework | ✅ Complete |
| 17.5 | Reusable Entity Intelligence Pages | ✅ Complete |
| 17.6 | Cross-Entity Navigation | ✅ Complete |
| 17.7 | Business Intelligence Layer | ✅ Complete |
| 17.8 | Historical Intelligence Layer | ✅ Complete |
| 17.9 | Scientific Knowledge Layer | ✅ Complete |
| 17.10 | Aerospace Knowledge Universe v1 | ✅ Complete |

---

## v0.4.0 Benchmark Baseline

| Metric | Value |
|---|---|
| Queries | 20 |
| Success | 20/20 (100%) |
| Corpus retrieval | 20/20 (100%) |
| Avg latency | 27,921ms |
| Min latency | 17,801ms (Conjunction Pc) |
| Max latency | 46,533ms (SGP4) |

**Standard:** Future releases must maintain ≥95% retrieval accuracy and ≤60s average latency.
