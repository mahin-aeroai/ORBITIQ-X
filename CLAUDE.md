# CLAUDE.md — ORBITIQ-X Working Instructions

This document is the authoritative onboarding reference for AI assistants working on ORBITIQ-X.
Read this before making any changes. Update this file when the engineering focus shifts.

---

## Project Overview

ORBITIQ-X is a production-grade aerospace intelligence platform combining:
- **Space Situational Awareness (SSA)**: 29,198 tracked RSOs with real names
- **Knowledge Graph**: Neo4j with 29,248 nodes · 118,681 relationships
- **GraphRAG**: 185-chunk corpus across 12 aerospace domains
- **Multi-Agent AI**: 7 specialist agents powered by Claude Sonnet 4.6
- **Mission Control UI**: Next.js 14 with rotating globe and live data

**Current version:** `v0.4.0`  
**Backend:** https://orbitiq-x-production.up.railway.app  
**Frontend:** https://orbitiq-x.vercel.app  
**GitHub:** https://github.com/mahin-aeroai/ORBITIQ-X  

---

## Admin Credentials

- **Username:** `admin3`
- **Password:** `OrbitIQ2026!`

---

## Architecture

```
PostgreSQL (Railway)     ← 29,198 satellites, 105,755 TLE records
Neo4j Aura               ← 29,248 nodes, 118,681 relationships
Qdrant Cloud             ← 185 chunks, aerospace_docs, 384-dim
Redis                    ← UNAVAILABLE (fix: add REDIS_URL to Railway)
FastAPI (Railway)        ← 103 endpoints, uvicorn
Next.js (Vercel)         ← 10 pages, TanStack Query
```

## Service Status

| Service | Status | Note |
|---|---|---|
| PostgreSQL | ✅ healthy | 29,198 sats, real names 99.5% |
| Neo4j | ✅ healthy | 118,681 relationships |
| Qdrant | ✅ healthy | 185 chunks |
| GraphRAG | ✅ operational | 100% retrieval |
| Agents | ✅ healthy | 7 specialists |
| Scheduler | ✅ running | 5 jobs |
| Redis | ⚠️ unavailable | Blocks Digital Twin |
| Digital Twin | ⚠️ not_initialised | Needs Redis |

---

## CRITICAL PITFALLS — READ BEFORE TOUCHING

### 1. Schema persistence (MOST COMMON BUG)
`rag/src/models/schemas.py` manual patches in Railway shell DO NOT persist across deploys.
The repo version is authoritative. Required fields verified against `hallucination/guard.py`:
- **CitationRecord**: citation_key, doc_title, chunk_id, agency, doc_type, publication_year, source_url, relevance_score, excerpt, authors, title, doc_id, year, doi, report_number, page_ref, section_ref
- **ChunkMetadata**: doc_id, chunk_index, section_title, content_type, agency, doc_type, publication_year, topic_tags, peer_reviewed, has_equations, source_url, doc_title, authors, page_start, page_end, report_number, doi

### 2. Alembic on Railway PostgreSQL 18
Always use `AUTOCOMMIT` isolation level:
```python
async with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
```

### 3. Never use string `primaryjoin` across models
SQLAlchemy cross-model string references break on import. Use `back_populates` with proper imports.

### 4. Vercel build failures
`ignoreBuildErrors` in `next.config.js` must be `true`. If false, TS errors silently block builds and Vercel serves stale cached pages.

### 5. Railway IP blocks
Celestrak blocks Railway IPs (403). Use Space-Track API for satellite data instead.

### 6. Catalog regime/type
- `regime` column is NULL for most rows — computed from perigee/apogee in Python at query time
- `object_type` stored lowercase: `satellite`, `debris`, `rocket_body` — normalize in endpoint

### 7. Space weather endpoint
Correct path: `/api/v1/space-weather/current` (NOT `/digital-twin/weather`)

### 8. Neo4j property names
Neo4j satellite nodes use camelCase: `noradId`, `perigeeKm`, `apogeeKm`, `inclinationDeg`, `periodMinutes`
PostgreSQL uses snake_case: `norad_id`, `perigee_km`, `apogee_km`, `inclination_deg`, `period_minutes`

### 9. Neo4j relationship schema (as enriched)
- `(Satellite)-[:ORBITS]->(CelestialBody {name:'Earth'})` — 58,396
- `(Satellite)-[:LAUNCHED_BY]->(Country)` — 14,407
- `(Satellite)-[:BELONGS_TO]->(Constellation)` — 9,823
- `(Satellite)-[:PART_OF]->(OrbitalRegime)` — 36,055
- OrbitalRegime names: "Low Earth Orbit", "Geostationary Orbit", "Medium Earth Orbit", "Sun-Synchronous Orbit", "Highly Elliptical Orbit"

---

## Railway Shell — Python Helper

```python
import sys, os, asyncio
sys.path.insert(0, '/app')
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

## Space-Track API (from Railway shell)

```python
import urllib.request, urllib.parse, json, http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open("https://www.space-track.org/ajaxauth/login",
    urllib.parse.urlencode({"identity": IDENTITY, "password": PASSWORD}).encode(), timeout=30)
url = "https://www.space-track.org/basicspacedata/query/class/satcat/NORAD_CAT_ID/1--34999/format/json/limit/30000"
data = json.loads(opener.open(url, timeout=120).read())
```

---

## Key File Locations

| File | Purpose |
|---|---|
| `backend/app/api/v1/endpoints/catalog.py` | `/catalog/satellites` with regime compute + type normalization |
| `backend/app/api/v1/endpoints/knowledge_graph.py` | KG analytics using BELONGS_TO/LAUNCHED_BY/PART_OF |
| `backend/app/api/v1/endpoints/rag.py` | `_get_bridge()` with `_OpenAIPipeline` (line ~128) |
| `backend/app/services/graphrag/graphrag_bridge.py` | GraphContextFetcher, `parents[3]` path fix |
| `backend/app/graph/connection.py` | `init_schema()`, `execute_read()`, `execute_write()` |
| `rag/src/models/schemas.py` | Complete schema — all fields required by hallucination guard |
| `rag/src/hallucination/guard.py` | Accesses: doi, page_ref, section_ref, report_number, year, authors |
| `frontend/src/lib/api.ts` | All API functions + types |
| `frontend/src/app/catalog/page.tsx` | Satellite catalog with detail drawer |
| `frontend/src/app/intelligence/page.tsx` | AI Workspace — GraphRAG Q&A |
| `frontend/next.config.js` | `ignoreBuildErrors: true` — MUST stay true |
| `scripts/populate_sat_names.py` | Populate satellite names/types from Space-Track |
| `scripts/corpus_seed_v04.py` | 185-chunk corpus seeding script |

---

## Neo4j Connection

- URI: `neo4j+s://bff8c462.databases.neo4j.io`
- User: `bff8c462`
- DB: `bff8c462`

## Qdrant Connection

- URL: `https://2435500e-5c7d-4182-b1ad-c3f0ca35a8a0.us-west-1-0.aws.cloud.qdrant.io`
- Collection: `aerospace_docs`
- Points: 185
- Dimensions: 384
- Model: `all-MiniLM-L6-v2`

---

## Current Engineering Focus (Phase 17.2)

### Immediate (Redis + Digital Twin)
1. Add `REDIS_URL` Railway env var → Redis reconnects
2. POST `/api/v1/catalog/sync {"mode":"full"}` → Digital Twin initialises
3. Globe shows live propagated satellite positions

### Next (Corpus Expansion)
- Target: 500+ chunks (50/domain)
- Method: local download → Railway shell `exec(open(...).read())`
- Embedding model upgrade: BGE-M3 (1024-dim) for better precision

### Next (Operator Intelligence)
- Populate `operator_name` in PostgreSQL from Space-Track ownership data
- Create Operator nodes in Neo4j with OPERATED_BY relationships
- Operator risk profiles with conjunction exposure metrics

---

## v0.4.0 Benchmark Baseline

| Metric | Value |
|---|---|
| Queries | 20 |
| Success rate | 20/20 (100%) |
| Corpus retrieval | 20/20 (100%) |
| Avg latency | 27,921ms |
| Min latency | 17,801ms (Conjunction Pc) |
| Max latency | 46,533ms (SGP4) |

Future releases must maintain ≥95% retrieval accuracy and ≤60s average latency.
