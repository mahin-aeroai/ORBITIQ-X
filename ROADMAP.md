# ORBITIQ-X — Engineering Roadmap

---

## Version History

| Version | Description | Date |
|---|---|---|
| `v0.1.0` | Initial production deployment — full backend + frontend live | 2026-06-26 |
| `v0.3.0` | Full AI stack — Neo4j, Qdrant, GraphRAG, LangGraph agents, Foundation Model | 2026-06-27 |
| `v0.4.0` | Phase 17.1 — Canonical Aerospace Entity Model (CAEM) | 2026-06-28 |

---

## Strategic Direction

ORBITIQ-X has completed its platform engineering phase. The infrastructure is stable and operational. Development focus has shifted permanently to **Knowledge Engineering** — expanding the Aerospace Knowledge Universe (AKU) rather than redesigning infrastructure.

**Long-term objective:** The "Bloomberg Terminal for Aerospace" — a platform that allows users to begin from any aerospace entity and seamlessly navigate through technical, operational, scientific, historical, commercial, and organizational relationships.

---

## Completed Phases

### Phase 1–3: Foundation
- Core FastAPI application factory with lifespan management
- PostgreSQL schema — users, sessions, satellites, TLE records, missions, events
- JWT authentication — register, login, refresh, logout, RBAC
- Alembic migration chain (10 migrations)

### Phase 4–6: SSA Core
- Space-Track TLE ingestion with APScheduler (2h incremental, 6h full sync)
- SGP4 propagation via `sgp4` library
- RSO catalog with orbital regime classification (LEO/MEO/GEO/HEO/SSO/VLEO)
- Conjunction event detection and CDM generation

### Phase 7–8: Digital Twin
- Real-time orbital state propagation for all catalog objects
- Trajectory forecasting with uncertainty bounds
- Maneuver simulation and delta-V computation

### Phase 9–10: Knowledge Graph + RAG
- Neo4j graph — operator profiles, country intelligence, constellation topology
- Weaviate vector store — aerospace knowledge embeddings
- LangChain RAG pipeline — query, explain, research endpoints
- GraphRAG fusion — graph + vector retrieval

### Phase 11–12: AI Agents
- LangGraph multi-agent orchestration
- Claude-powered conjunction analysis, maneuver planning, anomaly detection agents
- Agent task queue and status tracking

### Phase 13A–14: Mission Control Frontend
- Next.js 14 App Router application
- Animated globe dashboard, full UI redesign
- Real-time SSE conjunction alert streaming
- Space weather widget (NOAA integration)
- Satellite Catalog with real names via Space-Track SATCAT API

### Phase 14D: Release Readiness Audit
- 8 critical findings identified and resolved
- FastAPI deprecation warnings eliminated

### Phase 15A: Production Deployment
- Railway backend — Docker builder, all production defects resolved
- Vercel frontend — Next.js build pipeline, auth middleware
- Full auth flow operational

### Phase 15B: Operational Configuration
- Space-Track sync: 29,198 satellites ingested
- Digital Twin propagating orbital states
- Conjunction engine producing CDM events

### Phase 16A: Neo4j Knowledge Graph (Operational)
- Neo4j Aura: 29,248 nodes, 29,198 `ORBITS` relationships
- Satellite → OrbitalRegime graph active
- KG health latency: ~610ms warm

### Phase 16B: GraphRAG / Qdrant (Operational)
- Qdrant `aerospace_docs` collection live
- `full_graphrag` mode: Neo4j + Qdrant + Claude
- 185-chunk corpus, 20/20 benchmark queries passed

### Phase 16C: AI Mission Intelligence (Operational)
- 4 parallel LangGraph agents via Send API
- End-to-end mission briefing: ~96 seconds

### Phase 16D: Aerospace Foundation Model (Operational)
- 3-tier model: baseline / graphrag / agent
- 17 benchmark tasks registered

### ✅ Phase 17.1: Canonical Aerospace Entity Model (COMPLETE — 2026-06-28)

**Deliverables:**
- `BaseAerospaceEntity` — universal base model for every aerospace entity
- AQID system — immutable `AQID-{CLASS}-{SLUG}` identifiers
- `ProvenanceRecord` — fact-level chain of custody with confidence scoring
- 39 `EntityClass` values + 31 typed extension schemas
- 76 `RelationshipType` values across 10 semantic categories
- `AerospaceRelationship` model with Cypher builder
- Neo4j schema initializer with constraints, indexes, GDS projections
- 7-stage `CAEMIngestionPipeline` with contradiction resolution
- 9 REST endpoints at `/api/v2/entities`
- Alembic migration: `aerospace_entities` + 5 supporting tables

---

## Current Phase

### Phase 17.2: Universal Relationship Ontology *(Next)*

**Objective:** Formalize all 76 relationship types in Neo4j with full property schemas, cardinality rules, and temporal support.

**Deliverables:**
- [ ] Relationship type registry with direction rules and cardinality
- [ ] Temporal relationship properties (since/until) indexed in Neo4j
- [ ] Relationship confidence and provenance on all edges
- [ ] Neo4j migration for relationship property indexes
- [ ] Relationship validation API endpoint
- [ ] Graph Agent Cypher pattern library (10 traversal patterns)

**Exit Criteria:**
- All 76 relationship types represented in Neo4j
- Temporal point-in-time queries functional
- Relationship confidence filtering operational

---

## Planned Phases — Knowledge Engineering

### Phase 17.3: Provenance and Versioning
- PostgreSQL audit infrastructure for every fact
- Version history with field-level diffs
- Source authority tier implementation
- Contradiction record management and human review queue

### Phase 17.4: Knowledge Ingestion Framework
- Tier 1 source pipelines: NASA, ESA, SpaceX, Space-Track official publications
- Tier 2 source pipelines: NORAD, COSPAR, UNOOSA registries
- Entity extraction and AQID resolution
- Relationship extraction and classification
- Automated ingestion scheduling

### Phase 17.5: Reusable Entity Intelligence Pages
- Universal React entity page component
- Entity-class extension panels (LV launch history, SAT orbital params, etc.)
- AI Executive Summary card with confidence indicator
- Interactive relationship tab groups (Organizational / Technical / Commercial / Scientific)
- Mini graph preview + full Knowledge Graph Viewer

### Phase 17.6: Cross-Entity Navigation
- Every entity reference is a clickable link to that entity's page
- Breadcrumb trail for graph exploration
- Related entities sidebar
- "You are here" position in the knowledge graph

### Phase 17.7: Business Intelligence Layer
- Contract intelligence (value, parties, timeline, status)
- Investment flow visualization
- Market context for commercial entities
- Program budget tracking

### Phase 17.8: Historical Intelligence Layer
- Incident and anomaly records with causal chains
- Historical event timeline navigation
- Predecessor/successor lineage visualization
- Era-based filtering (Space Race / Post-Apollo / Commercial Era)

### Phase 17.9: Scientific Knowledge Layer
- Research paper ingestion and citation network
- Patent landscape per technology domain
- Standards compliance mapping
- Author and institution profiles

### Phase 17.10: Aerospace Knowledge Universe v1
- First public knowledge corpus release
- 10,000+ entities across all 39 entity classes
- 100,000+ relationships in Neo4j
- 10,000+ knowledge chunks in Qdrant
- Full provenance and confidence scores on all facts

---

## Infrastructure Stability Note

The platform infrastructure is considered stable. Future work should extend capabilities without redesigning existing systems.

**Do not redesign:** PostgreSQL schema, FastAPI router structure, Neo4j connection layer, Qdrant collection architecture, LangGraph agent framework, Next.js app structure.

**Do extend:** CAEM entity schemas, Neo4j relationship types, Qdrant collections, AI agent capabilities, React entity page components.
