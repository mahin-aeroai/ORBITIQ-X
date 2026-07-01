# ORBITIQ-X — Engineering Roadmap

---

## Version History

| Version | Status | Date | Description |
|---|---|---|---|
| `v0.1.0` | ✅ Released | 2026-06-26 | Initial production deployment — full backend + frontend |
| `v0.2.0` | ✅ Released | 2026-06-26 | SGP4 propagation · SATCAT enrichment · GraphRAG v1 |
| `v0.3.0` | ✅ Released | 2026-06-27 | GraphRAG benchmark · 9/9 queries · 100% retrieval |
| `v0.4.0` | ✅ Released | 2026-06-28 | Full platform activation · 252 corpus chunks · 20/20 benchmark · CAEM Phase 17.1 |
| `v0.5.0` | ✅ Released | 2026-06-28 | Phases 17.2–17.10 + 18 + 19 — Knowledge Intelligence + Corpus Expansion |
| `v0.5.1` | ✅ Released | 2026-06-30 | Platform Stabilisation — 28 production bugs fixed · Digital Twin active · 18 flagship entities seeded |

---

## Strategic Direction

ORBITIQ-X is evolving into the **"Bloomberg Terminal for Aerospace"** — an Aerospace Knowledge Universe (AKU) where users can begin from any entity (country, agency, satellite, mission, paper, patent, standard) and navigate through technical, operational, scientific, historical, commercial, and organizational relationships without limit.

Platform infrastructure is **stable**. Development focus is permanently on **Knowledge Engineering** — expanding the AKU rather than redesigning infrastructure.

---

## Immediate Next Actions (post-v0.5.1)

The Entity Browser Roadmap, per the agreed plan:

| Step | Action | Status |
|---|---|---|
| 1 | Verify Contracts and Investments working | ✅ Done |
| 2 | Confirm Entity Browser backend + UI functioning | ✅ Done |
| 3 | Seed curated flagship entities (18 entities) | ✅ Done |
| 4 | Execute live ingestion pipeline | ⏳ Blocked — Space-Track account suspended |
| 5 | Schedule periodic ingestion | ⏳ Pending |
| 6 | Neo4j relationship enrichment for seeded entities | ⏳ Pending |

**Blocker:** Space-Track account suspended 2026-06-30 for API policy violation (health check polling GP endpoint every 60s). Email sent. Awaiting reinstatement.

**Once reinstated — Step 4 trigger:**
```bash
# Small bounded test first (NASA missions adapter — smallest dataset)
curl -X POST https://orbitiq-x-production.up.railway.app/api/v2/ingestion/adapters/nasa_missions/run \
  -H "Authorization: Bearer YOUR_JWT"

# Check result
GET /api/v2/ingestion/adapters/nasa_missions
```

**Step 6 — Neo4j enrichment:** Run Cypher using `extension_data` AQIDs (`lead_agency_aqid`, `headquarters_country`, `launch_vehicle_aqid`) to create typed edges between the 18 seeded entities.

**Minor fix pending:** `ProvenancePanel` reads `entity.all_sources[]` but seed only writes `primary_provenance`. Fix: merge `primary_provenance` into `all_sources` in the GET `/entities/{aqid}` endpoint response.

---

## Completed Phases

### Phase 1–12: Foundation → AI Agents ✅
- FastAPI backend · 103 endpoints · 12 routers
- PostgreSQL schema · 15 Alembic migrations · JWT auth · RBAC
- Space-Track TLE ingestion · APScheduler (5 jobs)
- SGP4 propagation · orbital regime classification
- Neo4j knowledge graph · Qdrant vector store
- LangGraph multi-agent orchestration · 7 specialist agents
- Claude-powered conjunction analysis · maneuver planning · anomaly detection

### Phase 13–14: Mission Control Frontend ✅
- Next.js 14 App Router · TanStack Query
- Real-time SSE conjunction alerts · space weather widget
- Knowledge Graph explorer · agent activity feed
- Animated SVG globe dashboard

### Phase 15A: Production Deployment ✅
### Phase 15B: Operational Configuration ✅
### Phase 16A: Neo4j Knowledge Graph ✅
### Phase 16B: GraphRAG / Qdrant ✅
### Phase 16C: AI Mission Intelligence ✅
### Phase 16D: Aerospace Foundation Model ✅
### Phase 17: Full Platform Activation ✅
### Phase 17.1–17.10: CAEM + AKU v1 ✅
### Phase 18: Redis Activation + Digital Twin ✅

- Redis: connected, stable
- Digital Twin: 29,184 objects propagated via SGP4
- Cross-worker state sharing via Redis propagation meta blob

### Phase 19: Corpus Expansion ✅

- 67 new chunks across 4 new domains
- Total: 252 chunks, 16 domains

### Platform Stabilisation (v0.5.1) ✅

28 production bugs resolved including:
- orbital-engine namespace collision (5 `src` packages colliding in sys.path)
- SQLAlchemy `:param::jsonb` bind parser truncation bug (14 occurrences across 5 files)
- Digital Twin multi-worker state gap (gunicorn 2 workers, in-memory state per process)
- Space-Track API rate limit violation removed from health check
- railway.toml watchPatterns missing 4 of 5 Dockerfile COPY sources
- All frontend auth headers fixed (3 files using bare fetch with no token)

---

## Planned Phases

### Phase 20: Operator Intelligence
- Populate `operator_name` from Space-Track ownership data
- Create Operator nodes in Neo4j with OPERATED_BY relationships for ~5,000+ satellites
- Operator risk profiles with conjunction exposure metrics
- Operator intelligence page in frontend

### Phase 21: Entity Knowledge Expansion
- Run live ingestion: Space-Track, NASA, UNOOSA adapters
- Expand flagship entities to 100+ curated records
- AI-generated summaries for all entities
- Provenance panel fix (merge `primary_provenance` into `all_sources`)

### Phase 22: Streaming + Latency
- RAG streaming endpoint (`/rag/stream`) for first-token < 2s
- Response caching in Redis (repeat queries < 100ms)
- Parallel graph + vector retrieval

### Phase 23: Predictive Analytics
- 7-day conjunction lookahead prediction
- Orbital decay modeling for LEO objects
- Space weather impact on drag/decay rates

### Phase 24: Aerospace Knowledge Universe v1
- First public knowledge corpus release
- 10,000+ entities across all 39 entity classes
- 100,000+ relationships in Neo4j
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
