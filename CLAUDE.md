# CLAUDE.md — ORBITIQ-X Working Instructions

This document is the authoritative onboarding reference for AI assistants working on ORBITIQ-X.
Read this before making any changes. Update this file when the engineering focus shifts.

---

## Project Overview

ORBITIQ-X is a production-grade Aerospace Intelligence Platform evolving into the
**Aerospace Knowledge Universe (AKU)** — the "Bloomberg Terminal for Aerospace."

**Architecture:**
- **Backend:** FastAPI + PostgreSQL (Railway) + Redis + APScheduler
- **Frontend:** Next.js 14 (Vercel) with App Router
- **AI:** LangGraph agents (7) + Claude claude-sonnet-4-6 + GraphRAG pipeline
- **Orbital:** sgp4 propagation, Space-Track TLE ingestion, conjunction CDM screening
- **Graph:** Neo4j Aura knowledge graph (29,248 nodes, 118,681 relationships)
- **Vector:** Qdrant Cloud (`aerospace_docs` collection, 185 chunks)
- **Knowledge:** CAEM — Canonical Aerospace Entity Model (`backend/app/caem/`)

**Repository:** `mahin-aeroai/ORBITIQ-X`
**Backend:** https://orbitiq-x-production.up.railway.app
**Frontend:** https://orbitiq-x.vercel.app
**API Docs:** https://orbitiq-x-production.up.railway.app/api/v1/docs

---

## Current Phase

**Phase 17 — Knowledge Engineering**

Platform infrastructure is complete and stable. All future work expands the
Aerospace Knowledge Universe. Do not redesign stable infrastructure.

**Completed:** Phase 17.1 — Canonical Aerospace Entity Model (CAEM)
**Active:** Phase 17.2 — Universal Relationship Ontology
**Next:** Phase 17.3 — Provenance and Versioning

---

## Engineering Principles

1. **Evidence-based debugging only.** Never guess. Read logs, run tests, check the actual error before proposing a fix.
2. **No speculative fixes.** If the root cause is not confirmed, say so.
3. **Minimal targeted changes.** Fix the specific failure. Do not refactor surrounding code.
4. **Preserve existing architecture.** The database schema, API contracts, and middleware stack are stable.
5. **Extension over replacement.** Add to CAEM entity schemas and Neo4j relationships. Never redesign them.
6. **Production quality.** Every commit must work in production.
7. **Verify before declaring success.** Run tests, check logs, confirm resolution.
8. **Knowledge first.** Every new capability must integrate into the Aerospace Knowledge Graph.

---

## CAEM — Critical Architecture (Phase 17.1)

The Canonical Aerospace Entity Model lives at `backend/app/caem/`. Read this before touching any entity-related code.

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
Every entity exists across four layers simultaneously:
| Layer | System | What lives here |
|---|---|---|
| Master Data | PostgreSQL `aerospace_entities` | All entity fields, extension_data JSONB |
| Relationships | Neo4j | Typed directed edges with temporal properties |
| Knowledge | Qdrant `aerospace_docs` | Embedded chunks for semantic retrieval |
| Intelligence | Frontend entity pages | AI summaries, graph explorer, timeline |

### Extension Pattern
Entity-class-specific fields go in `extension_data` JSONB, validated by Pydantic extension models:
```python
from caem.entities import validate_extension
validated = validate_extension(EntityClass.LAUNCH_VEHICLE, {"payload_leo_kg": 22800, ...})
```
Never add entity-class columns to `aerospace_entities`. Always use `extension_data`.

### Relationship Types
All 76 relationship types are in `caem.relationships.RelationshipType`.
Never invent new relationship type strings. Use the enum.
```python
from caem.relationships import RelationshipType, AerospaceRelationship
rel = AerospaceRelationship(
    source_aqid="AQID-SATELLITE-ISS",
    target_aqid="AQID-GOV-AGENCY-NASA",
    relationship_type=RelationshipType.OPERATED_BY,
    confidence=0.99,
)
```

---

## Coding Standards

- **Python:** Type hints everywhere, Pydantic v2, async-first, SQLAlchemy 2.x patterns
- **Logging:** structlog with structured JSON fields — never use `print()` in production code
- **Database:** SQLAlchemy async session via `get_session` dependency, Alembic for all schema changes
- **Migrations:** Every schema change needs a numbered migration in `backend/alembic/versions/`
  - Naming: `YYYYMMDD_NNNN_description.py`
  - Always set `down_revision` to the previous migration's revision ID
  - Always use `AUTOCOMMIT` for Railway PostgreSQL (see Known Pitfalls)
- **API:** FastAPI with Pydantic request/response models, `JSONResponse` (not `ORJSONResponse`)
- **Frontend:** TypeScript strict mode, Next.js App Router patterns, TanStack Query

---

## Known Pitfalls (Verified Production Failures)

These have caused real production outages. Do not repeat them.

| Pitfall | Consequence | Rule |
|---|---|---|
| String `primaryjoin` across models | `InvalidRequestError` on every request | Never use string cross-model `primaryjoin` |
| Alembic without AUTOCOMMIT on Railway | Silent DDL rollback — tables never created | Always use `AUTOCOMMIT` isolation level in migrations |
| `parents[4]` in Docker path | `IndexError` in agent service | Docker has 3 parent levels, not 4 |
| `ORJSONResponse` | Deprecated, causes import errors | Use `JSONResponse` |
| `bcrypt>=4.0.0` with passlib 1.7.4 | `AttributeError: __about__` | Pin `bcrypt<4.0.0` |
| Cesium + webpack Terser | Build failure | Cesium replaced with pure SVG globe |
| Cross-model string FK reference | Mapper config crash | Always import model classes directly |
| Neo4j default database `orbitiq` | Connection failure on Aura | Aura uses instance ID as database name |
| `parents[5]` in graphrag_bridge | `IndexError` | Use `parents[3]` in Docker environment |

---

## Database Migration Rules

```python
# ALWAYS in Railway migrations:
from alembic import op

def upgrade():
    # Get connection with AUTOCOMMIT
    connection = op.get_bind()
    connection.execute(sa.text("SET LOCAL synchronous_commit = ON"))
    
    # GIN indexes MUST use op.execute(), NOT op.create_index()
    op.execute("CREATE INDEX ix_ae_tags ON aerospace_entities USING GIN (tags)")
    
    # Never use op.create_index() for GIN — it wraps in transaction
```

---

## Infrastructure Details

| Service | Connection | Notes |
|---|---|---|
| PostgreSQL | Railway plugin | `DATABASE_URL` env var, asyncpg driver |
| Neo4j | `bff8c462.databases.neo4j.io` | Database: `bff8c462`, User: `bff8c462` |
| Qdrant | `2435500e-...aws.cloud.qdrant.io` | Collection: `aerospace_docs` |
| Redis | Railway plugin | Non-critical — platform degrades gracefully |
| Space-Track | `www.space-track.org` | `SPACETRACK_IDENTITY` + `SPACETRACK_PASSWORD` |
| Anthropic | API | `ANTHROPIC_API_KEY`, model: `claude-sonnet-4-6` |

---

## Current Platform Metrics

| Metric | Value |
|---|---|
| Satellites | 29,198 |
| Neo4j nodes | 29,248 |
| Neo4j relationships | 118,681 |
| Qdrant chunks | 185 |
| API endpoints | 112 |
| Alembic migrations | 11 (head: `20260628_0011`) |
| CAEM entity classes | 39 |
| CAEM relationship types | 76 |

---

## Phase 17 Roadmap

| Sub-Phase | Scope | Status |
|---|---|---|
| 17.1 | Canonical Aerospace Entity Model | ✅ Complete |
| 17.2 | Universal Relationship Ontology | 🔄 Next |
| 17.3 | Provenance and Versioning | Planned |
| 17.4 | Knowledge Ingestion Framework | Planned |
| 17.5 | Reusable Entity Intelligence Pages | Planned |
| 17.6 | Cross-Entity Navigation | Planned |
| 17.7 | Business Intelligence Layer | Planned |
| 17.8 | Historical Intelligence Layer | Planned |
| 17.9 | Scientific Knowledge Layer | Planned |
| 17.10 | Aerospace Knowledge Universe v1 | Planned |

---

## What NOT to Do

- Do not redesign PostgreSQL schema, FastAPI routers, or Neo4j connection layer
- Do not add entity-class-specific columns to `aerospace_entities` — use `extension_data` JSONB
- Do not create new relationship type strings — use `RelationshipType` enum
- Do not store full entity data in Neo4j nodes — only graph traversal properties
- Do not bypass AQID validation — every AQID must pass `validate_aqid()`
- Do not build isolated pages — every new page integrates into the Knowledge Graph
- Do not ignore provenance — every fact needs a `ProvenanceRecord`
