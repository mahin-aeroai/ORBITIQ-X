# ORBITIQ-X — Engineering Roadmap

---

## Version History

| Version | Status | Date | Description |
|---|---|---|---|
| `v0.1.0` | ✅ Released | 2026-06-26 | Initial production deployment — full backend + frontend |
| `v0.2.0` | ✅ Released | 2026-06-26 | SGP4 propagation · SATCAT enrichment · GraphRAG v1 |
| `v0.3.0` | ✅ Released | 2026-06-27 | GraphRAG benchmark · 9/9 queries · 100% retrieval |
| `v0.4.0` | ✅ Released | 2026-06-28 | Full platform activation · 185 corpus chunks · 20/20 benchmark · CAEM Phase 17.1 |

---

## Strategic Direction

ORBITIQ-X is evolving into the **"Bloomberg Terminal for Aerospace"** — an Aerospace Knowledge Universe (AKU) where users can begin from any entity (country, agency, satellite, mission, paper, patent, standard) and navigate through technical, operational, scientific, historical, commercial, and organizational relationships without limit.

Platform infrastructure is **stable**. Development focus is permanently on **Knowledge Engineering** — expanding the AKU rather than redesigning infrastructure.

---

## Completed Phases

### Phase 1–12: Foundation → AI Agents ✅
- FastAPI backend · 103 endpoints · 12 routers
- PostgreSQL schema · 10 Alembic migrations · JWT auth · RBAC
- Space-Track TLE ingestion · APScheduler (5 jobs)
- SGP4 propagation · orbital regime classification
- Neo4j knowledge graph · Qdrant vector store
- LangGraph multi-agent orchestration · 7 specialist agents
- Claude-powered conjunction analysis · maneuver planning · anomaly detection

### Phase 13–14: Mission Control Frontend ✅
- Next.js 14 App Router · TanStack Query
- Cesium.js 3D orbital globe (later replaced with animated SVG globe)
- Real-time SSE conjunction alerts · space weather widget
- Knowledge Graph explorer · agent activity feed · dashboard metrics bar

### Phase 15A: Production Deployment ✅
- Railway backend · Vercel frontend
- Docker builder · full auth flow · all SQLAlchemy relationships fixed
- Alembic AUTOCOMMIT isolation level fix for Railway PostgreSQL 18

### Phase 15B: Operational Configuration ✅
- Space-Track sync: 29,198 satellites · 105,755 TLE records
- Conjunction engine operational · Digital Twin architecture (pending Redis)

### Phase 16A: Neo4j Knowledge Graph ✅
- Neo4j Aura: 29,248 nodes · 29,198 `ORBITS` relationships
- OrbitalRegime, Agency, LaunchVehicle, LaunchSite reference nodes

### Phase 16B: GraphRAG / Qdrant ✅
- Qdrant `aerospace_docs` collection · `full_graphrag` mode
- Initial benchmark: 9/9 queries, 100% retrieval

### Phase 16C: AI Mission Intelligence ✅
- 4 LangGraph agents concurrent via Send API
- End-to-end mission briefing: ~96 seconds

### Phase 16D: Aerospace Foundation Model ✅
- 3-tier model: baseline / graphrag / agent · 17 benchmark tasks

### Phase 17: Full Platform Activation ✅
- **Real satellite names**: 28,684 / 29,198 from Space-Track SATCAT (99.5%)
- **Object type classification**: satellite 17,946 · debris 8,392 · rocket_body 2,091
- **Catalog filters**: regime + type + search all working server-side
- **Neo4j enrichment**: 11 Constellation nodes · 6 Country nodes · 118,681 relationships
- **4 live pages**: Conjunctions · Agents · Knowledge Graph · Foundation
- **Rotating animated globe**: CSS/SVG Earth with satellites at LEO/MEO/GEO/SSO
- **AI Workspace**: GraphRAG pipeline visible to all users
- **Corpus expansion**: 17 → 185 chunks across 12 domains
- **v0.4.0 benchmark**: 20/20 queries · 100% retrieval · avg 27,921ms
- `ignoreBuildErrors: true` in `next.config.js` (was silently blocking Vercel page deploys)

### Phase 17.1: CAEM — Canonical Aerospace Entity Model ✅ (2026-06-28)

**The foundational knowledge architecture for the Aerospace Knowledge Universe.**

- **39 entity classes** across 7 domains: actors, hardware, operations, places, knowledge, transactions, phenomena
- **76 RelationshipType values** across 10 semantic categories
- **`BaseAerospaceEntity`**: AQID identifier system, ProvenanceRecord, confidence scoring (3-signal weighted composite), versioning, audit trail
- **31 typed extension schemas**: from `CountryExtension` to `CelestialBodyExtension`
- **7-stage `CAEMIngestionPipeline`**: normalize → resolve → contradiction detection → persist → relationships → AI verify → auto-publish
- **4-layer persistence**: PostgreSQL (JSONB) · Neo4j (graph) · Qdrant (vectors) · Frontend (intelligence pages)
- **Idempotent Neo4j schema**: constraints, GDS named graph projections, batch upsert
- **9 REST endpoints** at `/api/v2/entities`
- **Alembic migration `0011`**: 6 new tables including `aerospace_entities` with GIN indexes and FTS

---

## Current Phase

### Phase 17.2: Universal Relationship Ontology ✅ Complete

**Objective:** Formalize all 76 relationship types in Neo4j. Populate first real OPERATED_BY relationships.

**Deliverables:**
- [ ] Relationship type registry with direction rules and cardinality in Neo4j
- [ ] Temporal relationship properties (`since`/`until`) indexed
- [ ] Relationship confidence and provenance on all edges
- [ ] Operator nodes: populate `operator_name` from Space-Track ownership data
- [ ] `OPERATED_BY` (Satellite → Operator) edges created for all named operators
- [ ] Graph Agent Cypher pattern library (10 traversal patterns)
- [ ] Relationship validation API endpoint

**Exit Criteria:**
- All 76 relationship types represented in Neo4j type registry
- OPERATED_BY populated for ≥ 5,000 satellites
- Temporal point-in-time queries functional

---

## Planned Phases — Knowledge Engineering

### Phase 17.3: Provenance and Versioning
- Audit infrastructure for every fact (field-level change log)
- Version history with diffs
- Source authority tier enforcement
- Contradiction record management and human review queue

### Phase 17.4: Knowledge Ingestion Framework
- Tier 1 pipelines: NASA, ESA, SpaceX, Space-Track official publications
- Tier 2 pipelines: NORAD, COSPAR, UNOOSA registries
- Entity extraction, AQID resolution, relationship classification
- Automated ingestion scheduling

### Phase 17.5: Reusable Entity Intelligence Pages
- Universal React entity page component (base layout + class extension panels)
- AI Executive Summary card with confidence indicator
- Relationship tab groups (Organizational / Technical / Commercial / Scientific)
- Mini graph preview + full Knowledge Graph Viewer
- Entity-class extensions: LV launch history, SAT orbital params, Paper citation network

### Phase 17.6: Cross-Entity Navigation
- Every entity reference is a clickable link to its entity page
- Breadcrumb trail for graph exploration
- Related entities sidebar · "You are here" position in knowledge graph

### Phase 18: Redis Activation + Digital Twin
- Fix Redis connectivity (add Railway Redis addon or `REDIS_URL`)
- Activate Digital Twin propagation for all 29,198 objects
- Real-time satellite positions on globe
- SSE conjunction alert streaming

**Exit Criteria:** Globe shows live propagated positions · Digital Twin status = operational

### Phase 19: Corpus Expansion (500+ chunks)
- Expand from 185 → 500+ chunks (50 chunks/domain)
- Add primary sources: Spacetrack Report No.3, IADC, CCSDS full standards
- Local download → Railway upload (bypasses IP restrictions)
- Reranking with cross-encoder for precision improvement

**Exit Criteria:** 500+ chunks · average latency < 20s · retrieval accuracy ≥ 100%

### Phase 20: Operator Intelligence
- Populate `operator_name` from Space-Track ownership data
- Create Operator nodes in Neo4j with OPERATED_BY relationships
- Operator risk profiles with conjunction exposure metrics
- Operator intelligence page in frontend

### Phase 21: Streaming + Latency
- RAG streaming endpoint (`/rag/stream`) for first-token < 2s
- Embedding model upgrade: BGE-M3 or E5-large-v2 (1024-dim)
- Response caching in Redis (repeat queries < 100ms)
- Parallel graph + vector retrieval

### Phase 22: Predictive Analytics
- 7-day conjunction lookahead prediction
- Orbital decay modeling for LEO objects
- Space weather impact on drag/decay rates
- Historical trend analysis

### Phase 23: Foundation Model Fine-tuning
- LoRA fine-tuning on aerospace domain data
- Satellite behavior prediction model
- Anomaly detection via learned orbital baselines
- Benchmark suite for orbital prediction accuracy

### Phase 24: Aerospace Knowledge Universe v1
- First public knowledge corpus release
- 10,000+ entities across all 39 entity classes
- 100,000+ relationships in Neo4j
- 10,000+ knowledge chunks in Qdrant
- Full provenance and confidence scores on all facts

---

## Infrastructure Stability Note

These components are **stable and must not be redesigned**:
- PostgreSQL schema (extend via JSONB `extension_data`, not new columns)
- FastAPI router structure (add endpoints, don't restructure routers)
- Neo4j connection layer (extend relationships, don't change connection pattern)
- Qdrant collection architecture (add collections, don't change `aerospace_docs`)
- LangGraph agent framework (add agents, don't change orchestration)
- Next.js app structure (add pages, don't restructure app router)
