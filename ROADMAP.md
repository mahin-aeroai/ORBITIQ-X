# ORBITIQ-X — Engineering Roadmap

---

## Version History

| Version | Status | Date | Description |
|---|---|---|---|
| `v0.1.0` | ✅ Released | 2026-06-26 | Initial production deployment |
| `v0.2.0` | ✅ Released | 2026-06-26 | SGP4 propagation · SATCAT enrichment · GraphRAG v1 |
| `v0.3.0` | ✅ Released | 2026-06-27 | GraphRAG benchmark · 9/9 queries · 100% retrieval |
| `v0.4.0` | ✅ Released | 2026-06-28 | Full platform activation · 185 corpus chunks · 20/20 benchmark |

---

## Completed Phases

### Phase 1–12: Foundation → AI Agents ✅
- FastAPI backend · 103 endpoints · 12 routers
- PostgreSQL schema · 10 Alembic migrations
- JWT auth · RBAC · bcrypt passlib
- Space-Track TLE ingestion · APScheduler (5 jobs)
- SGP4 propagation · orbital regime classification
- Neo4j knowledge graph · Qdrant vector store
- LangGraph multi-agent orchestration · 7 specialist agents
- Claude-powered conjunction analysis · maneuver planning · anomaly detection

### Phase 13–14: Mission Control Frontend ✅
- Next.js 14 App Router · TanStack Query
- Cesium.js 3D orbital globe
- Real-time SSE conjunction alerts
- Space weather widget · dashboard metrics bar
- Knowledge Graph explorer · agent activity feed

### Phase 15A: Production Deployment ✅
- Railway backend · Vercel frontend
- Docker builder · Nixpacks glibc/greenlet fixes
- Full auth flow · all SQLAlchemy relationships fixed
- Alembic AUTOCOMMIT isolation level fix

### Phase 15B: Operational Configuration ✅
- Space-Track catalog sync: 29,198 satellites ingested
- TLE records: 105,755
- Conjunction engine: operational
- Digital Twin: architecture complete (pending Redis)
- Redis pub/sub: deployed (connectivity issue)

### Phase 16: GraphRAG Corpus + Benchmark (v0.3.0) ✅
- Corpus: 185 chunks across 12 aerospace domains
- Benchmark: 9/9 queries, 100% corpus retrieval (v0.3.0)
- Benchmark: 20/20 queries, 100% corpus retrieval (v0.4.0)
- Average latency: 27,921ms
- Schema: ChunkMetadata + CitationRecord all fields verified

### Phase 17: Full Platform Activation (v0.4.0) ✅
- **Satellite names**: 28,684 real names from Space-Track SATCAT (99.5%)
- **Object types**: satellite 17,946 · debris 8,392 · rocket_body 2,091
- **Catalog filters**: regime + type + search all working server-side
- **Satellite detail drawer**: country, operator, orbital params, TLE
- **Neo4j enrichment**:
  - 11 Constellation nodes (Starlink 8,917 · OneWeb 452 · Iridium 134)
  - 6 Country nodes (US 9,394 · CN 2,559 · RU 2,244)
  - 118,681 relationships (ORBITS · LAUNCHED_BY · BELONGS_TO · PART_OF)
- **4 live pages**: Conjunctions · Agents · Knowledge Graph · Foundation
- **Rotating globe**: animated Earth with LEO/MEO/GEO/SSO satellites
- **AI Workspace**: GraphRAG pipeline visible to all users
- **Space weather**: live Kp/F10.7/storm data from /space-weather/current
- **ignoreBuildErrors**: fixed Vercel build failures (was blocking page deploys)

### Phase 17.1: CAEM — Canonical Aerospace Entity Model ✅
- **39 entity types** across 7 domains: actors, hardware, operations, places, knowledge, transactions, phenomena
- **76 RelationshipType** values across 10 semantic categories
- **BaseAerospaceEntity**: AQID identifier system, ProvenanceRecord, confidence scoring, versioning
- **7-stage CAEMIngestionPipeline**: extract → validate → deduplicate → enrich → embed → graph → index
- **4-layer persistence**: PostgreSQL (JSONB) → Neo4j (graph) → Qdrant (vectors) → frontend (intelligence)
- **Idempotent Neo4j schema**: constraints, GDS named graph projections, batch upsert utilities
- 45+ entity type taxonomy defined
- 4-layer persistence: PostgreSQL · Neo4j · Qdrant · frontend intelligence
- Phase 17.2: Universal Relationship Ontology (next)

---

## Current Focus

### Phase 17.2: Universal Relationship Ontology
- Define all relationship types between CAEM entities
- Implement OPERATED_BY (satellite → operator) in Neo4j
- Populate operator_name field in PostgreSQL from Space-Track
- Add operator nodes linked to country nodes

---

## Planned Phases — Knowledge Engineering

### Phase 18: Redis Activation + Digital Twin
**Objectives:**
- Fix Redis connectivity (add Railway Redis addon or REDIS_URL)
- Activate Digital Twin propagation for all 29,198 objects
- Real-time satellite positions on globe
- SSE conjunction alert streaming

**Exit Criteria:**
- Globe shows live propagated positions
- Digital Twin status = operational
- Redis pub/sub active

### Phase 19: Corpus Expansion (500+ chunks)
**Objectives:**
- Expand from 185 → 500+ chunks (50 chunks/domain)
- Add primary sources: Spacetrack Report No.3, IADC, CCSDS full standards
- Local download → Railway upload (bypasses IP restrictions)
- Reranking with cross-encoder for precision improvement

**Exit Criteria:**
- 500+ chunks in Qdrant
- Average latency < 20s (with reranking + streaming)
- Retrieval accuracy ≥ 100% on 20-query benchmark

### Phase 20: Operator Intelligence
**Objectives:**
- Populate operator_name in PostgreSQL from Space-Track ownership data
- Create Operator nodes in Neo4j with OPERATED_BY relationships
- Operator risk profiles with conjunction exposure metrics
- Operator page in frontend

### Phase 21: Streaming + Latency
**Objectives:**
- RAG streaming endpoint (/rag/stream) for first-token < 2s
- Embedding model upgrade (BGE-M3 or E5-large-v2, 1024-dim)
- Response caching in Redis (repeat queries < 100ms)
- Parallel graph + vector retrieval

### Phase 22: Predictive Analytics
**Objectives:**
- 7-day conjunction lookahead prediction
- Orbital decay modeling for LEO objects
- Space weather impact on drag/decay rates
- Historical trend analysis

### Phase 23: Foundation Model Fine-tuning
**Objectives:**
- LoRA fine-tuning on aerospace domain data
- Satellite behavior prediction model
- Anomaly detection via learned orbital baselines
- Benchmark suite for orbital prediction accuracy
