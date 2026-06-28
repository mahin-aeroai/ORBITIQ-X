# CLAUDE.md — ORBITIQ-X Working Instructions

This document is the authoritative onboarding reference for AI assistants working on ORBITIQ-X.
Read this before making any changes. Update this file when the engineering focus shifts.

---

## Project Overview

ORBITIQ-X is a production-grade Aerospace Intelligence Platform evolving into the
**Aerospace Knowledge Universe (AKU)** — the "Bloomberg Terminal for Aerospace."

- **Space Situational Awareness**: 29,198 tracked RSOs with real names
- **Knowledge Graph**: Neo4j with 29,248 nodes · 118,681 relationships
- **GraphRAG**: 185-chunk corpus across 12 aerospace domains · 20/20 benchmark
- **Multi-Agent AI**: 7 specialist agents powered by Claude Sonnet 4.6
- **CAEM**: Canonical Aerospace Entity Model — 39 entity classes, 76 relationship types
- **Mission Control**: Next.js 14 with rotating globe and live data

**Current version:** `v0.4.0`
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
PostgreSQL (Railway)     ← 29,198 satellites, 105,755 TLE records
Neo4j Aura               ← 29,248 nodes, 118,681 relationships
Qdrant Cloud             ← 185 chunks, aerospace_docs, 384-dim
Redis                    ← UNAVAILABLE (fix: add REDIS_URL to Railway)
FastAPI (Railway)        ← 112 endpoints, uvicorn
Next.js (Vercel)         ← 10 pages, TanStack Query
CAEM                     ← backend/app/caem/ — knowledge architecture layer
```

## Service Connections

| Service | Connection | Notes |
|---|---|---|
| PostgreSQL | Railway plugin | `DATABASE_URL` env var, asyncpg driver |
| Neo4j | `neo4j+s://bff8c462.databases.neo4j.io` | DB + User: `bff8c462` |
| Qdrant | `2435500e-...us-west-1-0.aws.cloud.qdrant.io` | Collection: `aerospace_docs`, 384-dim |
| Redis | Railway plugin | UNAVAILABLE — blocks Digital Twin |
| Space-Track | `www.space-track.org` | `SPACETRACK_IDENTITY` + `SPACETRACK_PASSWORD` |
| Anthropic | API | `ANTHROPIC_API_KEY`, model: `claude-sonnet-4-6` |

---

## Current Phase

**Phase 17.3 — Provenance and Versioning** ✅ Complete

**Next: Phase 17.4 — Knowledge Ingestion Framework**

All 76 relationship types formalized. Completed:
- `relationship_ontology` table: 76 types with cardinality, direction, temporal rules
- `relationship_audit_log`: full audit trail for all relationship mutations
- `caem/ontology/relationship_registry.py`: typed `RelationshipDefinition` per type
- `caem/graph/neo4j_relationship_schema.py`: Neo4j constraints, indexes, bulk upsert
- `/api/v2/relationships` endpoints: create, validate, snapshot, traversal, ontology query
- `TRAVERSAL_LIBRARY`: 11 named graph patterns for Graph Agent
- Migration `0012` chained and seeded

---

## Engineering Principles

1. **Evidence-based debugging only.** Read logs, run tests, confirm the error before proposing a fix.
2. **No speculative fixes.** If root cause is not confirmed, say so.
3. **Minimal targeted changes.** Fix the specific failure. Do not refactor surrounding code.
4. **Preserve existing architecture.** Schema, API contracts, middleware stack are stable.
5. **Extension over replacement.** Add to CAEM schemas and Neo4j relationships. Never redesign them.
6. **Production quality.** Every commit must work in production.
7. **Knowledge first.** Every new capability integrates into the Aerospace Knowledge Graph.

---

## CAEM — Critical Architecture (Phase 17.1 Complete)

Lives at `backend/app/caem/`. Read before touching any entity-related code.

### AQID System
Every entity has an immutable AQID: `AQID-{CLASS}-{SLUG}`
```python
from caem import generate_aqid, validate_aqid, EntityClass
aqid = generate_aqid(EntityClass.COMPANY, "SpaceX")  # → "AQID-COMPANY-SPACEX"
```
- AQIDs are **never changed** after creation
- Display names are attributes, not identifiers
- External IDs (NORAD, COSPAR, DOI) live in `entity_aliases` table

### Four-Layer Architecture
| Layer | System | What lives here |
|---|---|---|
| Master Data | PostgreSQL `aerospace_entities` | All fields, `extension_data` JSONB |
| Relationships | Neo4j | Typed directed edges with temporal properties |
| Knowledge | Qdrant `aerospace_docs` | Embedded chunks for semantic retrieval |
| Intelligence | Frontend entity pages | AI summaries, graph explorer, timeline |

### Extension Pattern
Entity-class-specific fields go in `extension_data` JSONB — never add columns to `aerospace_entities`:
```python
from caem.entities import validate_extension
validated = validate_extension(EntityClass.LAUNCH_VEHICLE, {"payload_leo_kg": 22800})
```

### Relationship Types
Use `RelationshipType` enum from `caem.relationships` — never invent raw strings:
```python
from caem.relationships import RelationshipType, AerospaceRelationship
rel = AerospaceRelationship(
    source_aqid="AQID-SATELLITE-ISS",
    target_aqid="AQID-GOV-AGENCY-NASA",
    relationship_type=RelationshipType.OPERATED_BY,
    confidence=0.99,
)
```

### Key CAEM Files
| File | Purpose |
|---|---|
| `backend/app/caem/base.py` | `BaseAerospaceEntity`, AQID, `ProvenanceRecord`, confidence scoring |
| `backend/app/caem/entities.py` | 31 Pydantic extension schemas + `EXTENSION_REGISTRY` |
| `backend/app/caem/relationships.py` | 76 `RelationshipType` values, Cypher builder, traversal patterns |
| `backend/app/caem/graph/neo4j_schema.py` | Idempotent Neo4j schema, GDS projections, batch upsert |
| `backend/app/caem/ingestion/pipeline.py` | 7-stage ingestion pipeline |

---

## CRITICAL PITFALLS — READ BEFORE TOUCHING

### 1. Schema persistence (MOST COMMON BUG)
`rag/src/models/schemas.py` manual patches in Railway shell **DO NOT persist across deploys**.
The repo version is authoritative. Required fields verified against `hallucination/guard.py`:
- **CitationRecord**: citation_key, doc_title, chunk_id, agency, doc_type, publication_year, source_url, relevance_score, excerpt, authors, title, doc_id, year, doi, report_number, page_ref, section_ref
- **ChunkMetadata**: doc_id, chunk_index, section_title, content_type, agency, doc_type, publication_year, topic_tags, peer_reviewed, has_equations, source_url, doc_title, authors, page_start, page_end, report_number, doi

### 2. Alembic on Railway PostgreSQL 18
Always use `AUTOCOMMIT` isolation level. GIN indexes must use `op.execute()`, not `op.create_index()`.

### 3. Never use string `primaryjoin` across models
Causes `InvalidRequestError` on import. Use `back_populates` with proper imports.

### 4. Vercel build failures
`ignoreBuildErrors: true` in `next.config.js` **must stay true**. If false, TS errors block builds and Vercel serves stale cached pages silently.

### 5. Railway IP blocks
Celestrak blocks Railway IPs (403). Use Space-Track API instead.

### 6. Catalog regime/type
- `regime` column NULL for most rows — computed from perigee/apogee at query time
- `object_type` stored lowercase: `satellite`, `debris`, `rocket_body` — normalize in endpoint

### 7. Space weather endpoint
Correct path: `/api/v1/space-weather/current` (NOT `/digital-twin/weather`)

### 8. Neo4j property naming
Neo4j uses camelCase: `noradId`, `perigeeKm`, `apogeeKm`, `inclinationDeg`, `periodMinutes`
PostgreSQL uses snake_case: `norad_id`, `perigee_km`, `apogee_km`, `inclination_deg`, `period_minutes`

### 9. Neo4j relationship schema (current)
- `(Satellite)-[:ORBITS]->(CelestialBody {name:'Earth'})` — 58,396
- `(Satellite)-[:LAUNCHED_BY]->(Country)` — 14,407
- `(Satellite)-[:BELONGS_TO]->(Constellation)` — 9,823
- `(Satellite)-[:PART_OF]->(OrbitalRegime)` — 36,055
- OrbitalRegime names: "Low Earth Orbit", "Geostationary Orbit", "Medium Earth Orbit", "Sun-Synchronous Orbit", "Highly Elliptical Orbit"

### 10. CAEM extension data
Never add entity-class columns to `aerospace_entities`. Always use `extension_data` JSONB.
Never use raw relationship type strings. Always use `RelationshipType` enum.

---

## Key File Locations

| File | Purpose |
|---|---|
| `backend/app/api/v1/endpoints/catalog.py` | `/catalog/satellites` with regime compute + type normalization |
| `backend/app/api/v1/endpoints/knowledge_graph.py` | KG analytics using BELONGS_TO/LAUNCHED_BY/PART_OF |
| `backend/app/api/v1/endpoints/rag.py` | `_get_bridge()` with `_OpenAIPipeline` |
| `backend/app/api/v1/endpoints/entities.py` | 9 CAEM REST endpoints at `/api/v2/entities` |
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

## Phase 17 Roadmap

| Sub-Phase | Scope | Status |
|---|---|---|
| 17.1 | Canonical Aerospace Entity Model | ✅ Complete |
| 17.2 | Universal Relationship Ontology | ✅ Complete |
| 17.3 | Provenance and Versioning | ✅ Complete |
| 17.4 | Knowledge Ingestion Framework | Planned |
| 17.5 | Reusable Entity Intelligence Pages | Planned |
| 17.6 | Cross-Entity Navigation | Planned |

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
