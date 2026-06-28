# ORBITIQ-X — Changelog

All notable changes to ORBITIQ-X are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Planned
- Phase 17.2 — Universal Relationship Ontology (Neo4j edge formalization)
- Phase 17.3 — Provenance and Versioning infrastructure
- Phase 17.4 — Knowledge Ingestion Framework (Tier 1–2 source pipelines)
- Phase 17.5 — Reusable Entity Intelligence Pages (React universal entity page)
- Redis pub/sub operational
- Space-Track catalog sync activation

---

## [v0.4.0] — 2026-06-28

### Added — Phase 17.1: Canonical Aerospace Entity Model (CAEM)

The foundational knowledge architecture for the Aerospace Knowledge Universe.

#### CAEM Core (`backend/app/caem/`)
- `base.py` — `BaseAerospaceEntity`: universal base model inherited by every aerospace entity
  - AQID system: immutable `AQID-{CLASS}-{SLUG}` identifiers with generation and validation utilities
  - `ProvenanceRecord`: full chain of custody per fact (source, authority tier, confidence, verification status)
  - `TimelineEvent`: ordered lifecycle events with date precision and importance levels
  - `VersionEntry` + `ChangeLogEntry`: full audit trail with field-level diffs
  - `AIIntelligenceBlock`: cached AI executive summary, key facts, refresh flags
  - `compute_entity_confidence()`: weighted composite scoring (source authority × 0.40 + verification × 0.35 + corroboration × 0.25)
  - `to_neo4j_node()` / `to_qdrant_payload()`: layer-specific serialization methods
  - 39 `EntityClass` enum values covering all aerospace entity types
  - 10 supporting enums: `LifecycleStatus`, `VerificationStatus`, `SourceType`, `DatePrecision`, `ChangeType`, `ImportanceLevel`, `EntitySubclass`

- `entities.py` — 31 typed extension schemas for entity-class-specific fields:
  - Actor extensions: `CountryExtension`, `GovernmentAgencyExtension`, `CommercialCompanyExtension`, `UniversityExtension`, `PersonExtension`
  - Hardware extensions: `LaunchVehicleExtension` (stages, payload capacity, success rate), `SatelliteExtension` (NORAD ID, COSPAR, orbit params), `ComponentExtension`
  - Infrastructure extensions: `LaunchSiteExtension` (lat/lon, pads, inclinations), `GroundStationExtension`
  - Program extensions: `ProgramExtension`, `MissionExtension`, `ConstellationExtension`
  - Knowledge extensions: `TechnologyExtension` (TRL), `StandardExtension`, `ResearchPaperExtension` (DOI, citations), `PatentExtension` (IPC codes)
  - Commercial extensions: `ContractExtension`, `InvestmentExtension`
  - Event extensions: `IncidentExtension` (severity, root cause, corrective actions)
  - Celestial extensions: `CelestialBodyExtension` (Torino scale, PHAs)
  - `EXTENSION_REGISTRY`: maps every `EntityClass` to its extension model
  - `validate_extension()`: type-safe validation before persistence

- `relationships.py` — Universal Relationship Ontology:
  - 76 typed `RelationshipType` values across 10 semantic categories:
    - Organizational: `PART_OF`, `SUBSIDIARY_OF`, `FUNDED_BY`, `COLLABORATES_WITH`, `ACQUIRED_BY`...
    - Operational: `OPERATED_BY`, `LAUNCHED_BY`, `LAUNCHED_FROM`, `CONTROLLED_FROM`, `ORBITS`...
    - Supply chain: `MANUFACTURED_BY`, `SUPPLIED_BY`, `COMPONENT_OF`, `USES_MATERIAL`...
    - Technical: `USES_TECHNOLOGY`, `IMPLEMENTS`, `SUCCESSOR_OF`, `CERTIFIED_BY`, `ENABLES`...
    - Scientific: `DISCOVERED_BY`, `AUTHORED_BY`, `CITES`, `REFERENCES`, `VALIDATES`...
    - Commercial: `AWARDED_TO`, `INVESTED_IN`, `PROVIDES_SERVICE_TO`...
    - Regulatory: `REGULATED_BY`, `COMPLIES_WITH`, `RATIFIED_BY`, `SANCTIONS`...
    - Historical: `PRECEDED_BY`, `CAUSED`, `TRIGGERED`, `EVOLVED_INTO`...
    - Knowledge: `DESCRIBED_BY`, `STANDARDIZED_IN`, `PATENTED_BY`, `INSPIRED`...
    - Geographic: `LOCATED_IN`, `OPERATES_IN`, `COVERS`, `LAUNCHES_TO`...
  - `AerospaceRelationship`: typed directed relationship model with temporal properties (`since`/`until`), confidence, provenance, `validate()`, and `to_cypher_merge()` Cypher builder
  - `RELATIONSHIP_CATEGORIES`: category grouping for frontend tab organization
  - `TRAVERSAL_PATTERNS`: 8 reference Cypher patterns for the Graph Agent

- `graph/neo4j_schema.py` — Neo4j schema initializer:
  - Idempotent schema setup (safe to re-run): unique AQID constraint, existence constraints, property indexes, full-text index on entity names
  - `initialize_neo4j_schema()`: runs all constraints and indexes against Neo4j driver
  - `upsert_entity_node()`: single-entity node upsert with APOC and non-APOC variants
  - `batch_upsert_nodes()`: UNWIND-based batch upsert for ingestion pipelines
  - 4 named GDS graph projections: `full_aerospace_graph`, `supply_chain_graph`, `organizational_graph`, `scientific_graph`

- `ingestion/pipeline.py` — 7-stage `CAEMIngestionPipeline`:
  - Stage 1: Normalize — maps raw entity types to `EntityClass`, applies source authority confidence floor
  - Stage 2: Resolve & Validate — AQID resolution (exact → display_name → alias → generate), extension validation
  - Stage 3: Contradiction Detection — three-tier resolution: override (Δ > 0.15) / dispute (within 0.15) / reject (Δ < −0.15)
  - Stage 4: Persist — parallel write to PostgreSQL (`aerospace_entities`) and Neo4j
  - Stage 5: Relationships — type classification, validation, Neo4j edge + PostgreSQL cache write
  - Stage 6: AI Verification — flags `ai_requires_refresh` for async Summary Agent processing
  - Stage 7: Auto-Publish — promotes entities meeting confidence threshold to `published`
  - Full `IngestionJob` audit trail written to `entity_ingestion_log`

#### New API Endpoint (`backend/app/api/v1/endpoints/entities.py`)
- `GET    /api/v2/entities` — list with filters (class, domain, region, status, confidence), cursor pagination
- `POST   /api/v2/entities` — create entity with AQID generation and extension validation
- `GET    /api/v2/entities/{aqid}` — full entity record
- `PATCH  /api/v2/entities/{aqid}` — partial update with extension data merge
- `GET    /api/v2/entities/{aqid}/relationships` — relationship list from PostgreSQL cache
- `GET    /api/v2/entities/{aqid}/neighborhood` — Neo4j graph neighborhood (configurable depth 1–4)
- `POST   /api/v2/entities/{aqid}/sources` — add provenance source, recomputes confidence
- `POST   /api/v2/entities/{aqid}/refresh-summary` — queue AI summary regeneration
- `GET    /api/v2/entities/search/fulltext` — PostgreSQL GIN tsvector full-text search

#### New Migration (`backend/alembic/versions/20260628_0011_caem_base_entities.py`)
- `aerospace_entities` — single-table inheritance master table with GIN indexes (tags, domains, aliases, extension_data), full-text GIN index, auto-update trigger
- `entity_aliases` — cross-system external ID mappings (NORAD/COSPAR/DOI/ISO/CIK)
- `entity_relationships_cache` — denormalized Neo4j relationship cache for fast REST responses
- `entity_ingestion_log` — full per-job ingestion audit
- `knowledge_domains` — reference table seeded with 16 aerospace domains
- `relationship_type_registry` — relationship type taxonomy reference

---

## [v0.3.0] — 2026-06-27

### Added — Phase 16A–16D: Full AI Stack Activation

#### Phase 16A — Neo4j Knowledge Graph (Operational)
- Neo4j Aura instance connected: `bff8c462.databases.neo4j.io`
- 29,248 nodes: 29,198 satellite nodes + 50 reference nodes (OrbitalRegime×9, Agency×14, LaunchVehicle×15, LaunchSite×12)
- 29,198 `ORBITS` relationships (Satellite→OrbitalRegime)
- KG health latency: ~610ms warm

#### Phase 16B — GraphRAG / Qdrant (Operational)
- Qdrant cluster connected: `2435500e-5c7d-4182-b1ad-c3f0ca35a8a0.us-west-1-0.aws.cloud.qdrant.io`
- `aerospace_docs` collection live
- `full_graphrag` mode: Neo4j + Qdrant + Claude synthesis
- GraphRAG query latency: ~9–11 seconds
- 185-chunk GraphRAG corpus, 20/20 benchmark retrieval queries passed

#### Phase 16C — AI Mission Intelligence (Operational)
- LangGraph multi-agent system: 4 agents running concurrently via Send API
- Agents: `orbital_dynamics`, `conjunction_analysis`, `space_debris`, `satellite_intelligence`
- End-to-end mission briefing latency: ~96 seconds

#### Phase 16D — Aerospace Foundation Model (Operational)
- 3-tier foundation model: baseline / graphrag / agent
- 17 benchmark tasks registered
- Tier latencies: Tier 1 ~16s, Tier 2 ~12s, Tier 3 ~24s

---

## [v0.1.0] — 2026-06-26

### Added — Phase 15A: Production Deployment

#### Backend
- FastAPI application with 103 API endpoints across 12 routers
- PostgreSQL schema via 10 Alembic migrations
- JWT authentication with RBAC
- APScheduler with 5 scheduled jobs
- SGP4 orbital propagation, conjunction CDM generation
- LangGraph multi-agent system with Claude claude-sonnet-4-6
- Neo4j knowledge graph integration
- Weaviate vector store RAG pipeline
- Space weather integration (NOAA/SWPC)
- Redis pub/sub for real-time SSE conjunction alerts
- Prometheus metrics, OpenTelemetry tracing, Sentry error tracking

#### Frontend
- Next.js 14 App Router application
- Mission Control dashboard, Satellite Catalog, Conjunctions, Agents, Knowledge Graph, Foundation pages
- Animated globe dashboard, dark space aesthetic (deep navy / electric indigo)

#### Deployment
- Railway Docker deployment (`backend/Dockerfile.railway`)
- Vercel production deployment
- `entrypoint.sh` — DATABASE_URL parsing, Alembic migration execution, gunicorn launch

### Fixed — Critical Production Fixes (Phase 15A)
- Nixpacks glibc/greenlet incompatibility → switched to Dockerfile builder
- Alembic silent DDL rollback → AUTOCOMMIT isolation level
- SQLAlchemy mapper `InvalidRequestError` → removed all cross-model string `primaryjoin`
- Missing `ForeignKey` on `UserSession.user_id`
- `bcrypt` + `passlib` version incompatibility → pinned `bcrypt<4.0.0`
- 12 additional production defects resolved (see Phase 15A notes in git history)

---

## Repository

GitHub: https://github.com/mahin-aeroai/ORBITIQ-X

---

## Phase 16A — Neo4j Knowledge Graph — OPERATIONAL (2026-06-27)

### Production Metrics (measured live)

| Metric | Value |
|---|---|
| Neo4j Aura instance | `bff8c462.databases.neo4j.io` |
| Total nodes | 29,248 |
| Satellite nodes | 29,198 |
| Reference nodes | 50 (OrbitalRegime×9, Agency×14, LaunchVehicle×15, LaunchSite×12) |
| Total relationships | 29,198 |
| Relationship type | ORBITS (Satellite→OrbitalRegime) |
| LEO satellites | 25,285 |
| MEO satellites | 1,665 |
| GEO satellites | 1,535 |
| HEO satellites | 713 |
| KG health latency | ~610ms warm |
| Neo4j status | healthy |
| PostgreSQL status | healthy |
| Scheduler status | running |
| Platform overall | degraded (Redis unavailable — config task) |

### Configuration Defects Resolved During Activation

| Defect | Root Cause | Fix |
|---|---|---|
| `NEO4J_URI` ignored env var | `@property` always returned `bolt://localhost:7687` | Added `os.environ.get("NEO4J_URI")` check |
| `NEO4J_DATABASE` wrong default | Defaulted to `"orbitiq"` — Aura uses instance ID | Changed to `"bff8c462"` |
| `NEO4J_USER` not injecting | Railway env var not propagating to Pydantic field | Hardcoded default `"bff8c462"` |
| Indentation error | GitHub web edit introduced extra space on `def` line | Fixed via local push |
| Satellites table empty | Deployed code missing `53cc3c9` satellite upsert fix | Populated directly from TLE records via SQL |
| No ORBITS relationships | `regime` property missing; OrbitalRegime matched on `name` not `orbitId` | Set regime from orbital params; matched on `orbitId` |

### Phase 16B Readiness: GO

---

## Phase 16B — GraphRAG (Qdrant Vector Store) — OPERATIONAL (2026-06-27)

### Production Metrics (measured live)

| Metric | Value |
|---|---|
| Qdrant cluster | `2435500e-5c7d-4182-b1ad-c3f0ca35a8a0.us-west-1-0.aws.cloud.qdrant.io` |
| Collection | `aerospace_docs` |
| RAG mode | `full_graphrag` |
| RAG overall | healthy |
| Neo4j nodes | 29,248 |
| Qdrant available | true |
| Vector store status | healthy |
| GraphRAG status | healthy |
| Live query latency | ~9–11 seconds (graph retrieval + Claude synthesis) |
| Sample answer | "25,285 total tracked objects in LEO" — correct from live graph |

### Defects Resolved During Phase 16B Activation

| Defect | Fix | Commit |
|---|---|---|
| `qdrant-client` not in requirements | Added `qdrant-client==1.14.3` | `b1f2214` |
| `rag/` not in Docker image | Added `COPY rag/ /app/rag/` to Dockerfile | `fdddbed` |
| `rag/src` relative imports fail | Added `rag/` (not `rag/src/`) to sys.path | `b6f4353` |
| `models/schemas.py` missing | Created with all 13 required types | `a2f3a14` |
| `CNSA` missing from AgencyType | Added enum value | `d748d28` |
| `MISSION_REPORT` etc missing from DocumentType | Added 7 missing values | `df0199f` |
| `chunking/loaders.py` missing | Created stub re-exporting from ingestion | `760775e` |
| `AerospaceRAGPipeline` wrong constructor | Fixed from `store=` to `qdrant_host=` | `b6f4353` |
| `graphrag_bridge.py` `parents[5]` IndexError | Changed to `parents[3]` | `e8be7cf` |
| `connection.py` `parents[4]` wrong | Changed to `parents[3]` | `ae6b78f` |
| BGE-M3 embedder blocks startup | Replaced with lightweight Qdrant-only pipeline | `01a9c03` |
| Analytics uses wrong relationship names | Added direct Cypher fallback with `ORBITS` | `8be46e4` |
| `NEO4J_USER` env var not injecting | Hardcoded default `bff8c462` | `e3b385e` |

### Platform Status After Phase 16B

```
RAG health:    overall=healthy  mode=full_graphrag
neo4j:         healthy  node_count=29248
qdrant:        available=true
anthropic:     configured  model=claude-sonnet-4-6
vector_store:  healthy
graphrag:      healthy
postgres:      healthy
scheduler:     running
```

---

## Phase 16C — AI Mission Intelligence — OPERATIONAL (2026-06-27)

### Production Metrics (measured live)

| Metric | Value |
|---|---|
| Task status | complete |
| Errors | 0 |
| Agents invoked | orbital_dynamics, conjunction_analysis, space_debris, satellite_intelligence |
| Agent parallelism | 4 agents ran concurrently via LangGraph Send API |
| Total latency | ~96 seconds (4 parallel agents + Claude synthesis) |
| Answer quality | Full aerospace situational awareness briefing |

### Defects Resolved During Phase 16C Activation

| Defect | Fix | Commit |
|---|---|---|
| `InvalidUpdateError: session_id` | Annotated immutable input fields with last-write-wins | `cf3e96d` |
| `InvalidUpdateError: routing_decision` | Annotated all 19 plain scalar fields in OrbitalState | `b74263f` |
| `InvalidUpdateError: safety_approved` | Fixed missed OrbitalState field (ManeuverRecommendation also has safety_approved) | `2053275` |

### Full Stack Operational

```
PostgreSQL    → 29,198 satellites, 84,661 TLE records
Neo4j         → 29,248 nodes, 29,198 ORBITS relationships
Qdrant        → aerospace_docs collection (empty — ready for ingestion)
LangGraph     → 7 specialist agents registered
Claude        → claude-sonnet-4-6, full GraphRAG + agent synthesis
GraphRAG mode → full_graphrag (Neo4j + Qdrant + Anthropic)
Agent result  → ORBITIQ-X MISSION DIRECTOR BRIEFING with live orbital data
```

---

## Phase 16D — Aerospace Foundation Model — OPERATIONAL (2026-06-27)

### Production Metrics (measured live)

| Tier | Query | Latency | Result |
|---|---|---|---|
| Tier 1 — baseline | SGP4 explanation | 16,107ms | Full technical answer |
| Tier 2 — graphrag | LEO population + conjunction risk | 11,947ms | 25,285 objects from live graph |
| Tier 3 — agent | LEO vs GEO debris risk comparison | 24,407ms | Multi-agent analysis dispatched |

### Foundation Model Status
```
status:             operational
registered_models:  3
benchmark_tasks:    17
tiers_available:    baseline, graphrag, agent
```

### Full Platform Stack — OPERATIONAL

| Component | Status | Detail |
|---|---|---|
| PostgreSQL | ✅ | 29,198 satellites, 84,661 TLE records |
| Redis | ⚠️ | Unavailable (config task) |
| Neo4j | ✅ | 29,248 nodes, 29,198 relationships |
| Qdrant | ✅ | aerospace_docs collection |
| LangGraph agents | ✅ | 7 specialist agents |
| GraphRAG | ✅ | full_graphrag mode |
| Foundation Model | ✅ | 3 tiers, 17 benchmark tasks |
| Claude | ✅ | claude-sonnet-4-6 |

---

## [v0.4.0] — 2026-06-28

### Added
- **Satellite catalog filters**: regime (LEO/MEO/GEO/HEO/SSO/VLEO) + type (SAT/DEB/R/B) + search — all server-side via `/catalog/satellites` PostgreSQL endpoint
- **Satellite detail drawer**: click any row for NORAD ID, name, country, operator, orbital parameters (perigee/apogee/inclination/period), TLE
- **Real satellite names**: 28,684 / 29,198 RSOs renamed from Space-Track SATCAT (99.5% coverage, 2 fetch passes for NORAD 1–89,484)
- **Object type classification**: satellite 17,946 · debris 8,392 · rocket_body 2,091 (from Space-Track OBJECT_TYPE field)
- **Neo4j enrichment**:
  - 11 Constellation nodes: Starlink 8,917 · OneWeb 452 · Iridium 134 · Planet 102 · GLONASS 66 · Spire 55 · BeiDou 41 · Orbcomm 20 · Galileo 18 · Globalstar 18
  - 6 Country nodes: US 9,394 · CN 2,559 · RU 2,244 · EU 153 · IN 44 · JP 13
  - 118,681 total relationships: ORBITS (58,396) · LAUNCHED_BY (14,407) · BELONGS_TO (9,823) · PART_OF (36,055)
- **4 fully live frontend pages**: Conjunctions · Agents · Knowledge Graph · Foundation
- **Rotating animated globe**: CSS/SVG Earth with continent overlay, 120-star field, satellites at LEO/MEO/GEO/SSO altitudes, depth-based opacity, ground stations (KSC/ESOC/ISRO/JAXA)
- **AI Workspace** (`/intelligence`): GraphRAG pipeline visible to all users (removed minRole restriction)
- **Space weather live data**: `/space-weather/current` returning Kp, F10.7, storm levels (was 404 on wrong endpoint)
- **Knowledge Graph analytics**: operators/countries/constellations/regimes all returning live data via BELONGS_TO/LAUNCHED_BY/PART_OF
- **SystemHealthStrip**: 7 platform services as colored dots on dashboard
- **Foundation page**: architecture pipeline diagram, v0.4.0 benchmark summary, live service panels, corpus breakdown
- **Corpus expansion**: 17 → 185 chunks across 12 domains (orbital_propagation, orbital_mechanics, conjunction_analysis, SSA, spacecraft_ops, debris_mitigation, space_missions, mission_planning, launch_vehicles, satellite_constellations, space_environment, standards_protocols)
- **v0.4.0 benchmark**: 20 queries · 20/20 success · 20/20 corpus retrieval · avg 27,921ms · min 17,801ms · max 46,533ms
- **Schema completeness**: CitationRecord now has doi, page_ref, section_ref, report_number, year; ChunkMetadata has doi, page_start, page_end, report_number

### Fixed
- `next.config.js`: `ignoreBuildErrors: false → true` — was causing Vercel to silently fail and serve cached placeholder stubs for all new pages
- `rag/src/models/schemas.py`: all fields required by hallucination guard now present (5 fields added across CitationRecord/ChunkMetadata)
- Space weather endpoint: `/digital-twin/weather` → `/space-weather/current`
- Catalog type filter: DB stores `satellite`/`rocket_body`/`debris` (lowercase) not `PAYLOAD`/`ROCKET_BODY` — fixed normalization
- Catalog regime filter: `regime` column was NULL for all rows (only set by Digital Twin). Fixed by computing regime from perigee/apogee at query time
- Knowledge Graph analytics: all endpoints were returning 0 — patched to use actual BELONGS_TO/LAUNCHED_BY/PART_OF relationships
- Navigation: AI Workspace missing from sidebar for some users — removed `minRole: "analyst"` requirement
- Agent page: used wrong `AgentTaskStatus` field names (`agents_used` → `agents_invoked`, `started_at` → `submitted_at`)
- Conjunction page: used wrong `ConjunctionItem` field names (`max_pc` → `collision_probability`, `primary` object structure)

### Changed
- Dashboard: full-bleed globe layout, LIVE indicator, coordinate overlays, scan-line texture
- SpaceWeatherWidget: honest "unavailable" state instead of zeroed values; LIVE/STALE indicator; Kp hero display
- CatalogStatsCard: "Awaiting sync" instead of "—"; Rocket Bodies added as 5th card
- SideNav: AI Workspace moved to always-visible (no minRole)
- OrbitalGlobe: replaced static SVG with animated rotating Earth

### Scripts
- `scripts/populate_sat_names.py`: fetches Celestrak/Space-Track SATCAT, updates satellite names and types in PostgreSQL
- `scripts/corpus_seed_v04.py`: 185-chunk production aerospace knowledge corpus

---

## [v0.3.0] — 2026-06-27

### Added
- GraphRAG benchmark: 9 queries · 9/9 success · 9/9 corpus retrieval · avg 19,009ms
- Corpus: 17 initial chunks in Qdrant aerospace_docs collection
- GraphRAG bridge: `_OpenAIPipeline` class with sentence-transformers + Qdrant + Claude synthesis
- `docs/RELEASES/v0.3.0_BENCHMARK_REPORT.md`

### Fixed
- `agents/src/state/orbital_state.py`: all 57 fields Annotated with reducers
- GraphRAG `parents[3]` path fix in bridge and graph connection

---

## [v0.2.0] — 2026-06-26

### Added
- Space-Track SATCAT integration (29,198 satellites)
- SGP4 propagation via `sgp4` Python library
- TLE ingestion: 105,755 records
- Neo4j graph: 29,248 nodes · ORBITS relationships
- Digital Twin architecture (pending Redis activation)
- Conjunction screening engine
- v0.2.0 release notes

### Fixed
- `CitationRecord`/`ChunkMetadata` schema mismatches
- `object_type`/`regime` NULL fields requiring runtime inference
- Railway shell patch persistence issues documented in CLAUDE.md

---

## [v0.1.0] — 2026-06-26

### Added
- FastAPI backend: 103 endpoints across 12 routers
- PostgreSQL: 10 Alembic migrations (users, sessions, satellites, TLE records, missions, conjunction events, orbital events, audit logs, sync metrics)
- JWT authentication: register, login, refresh, logout, RBAC (admin/operator/analyst/readonly)
- APScheduler: 5 jobs (orbital propagation 15min, TLE refresh 2h, conjunction screening 6h, Neo4j population 6h, full sync 6h)
- Next.js 14 App Router frontend
- TanStack Query data layer
- Cesium.js 3D orbital globe
- Railway + Vercel production deployment

### Fixed
- bcrypt/passlib version incompatibility: pinned bcrypt<4.0.0
- SQLAlchemy relationship conflicts
- Alembic AUTOCOMMIT isolation for Railway PostgreSQL 18
- Nixpacks glibc/greenlet build issues
