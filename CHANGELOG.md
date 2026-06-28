# ORBITIQ-X — Changelog

All notable changes to ORBITIQ-X are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Planned
- Phase 17.2 — Universal Relationship Ontology (Neo4j edge formalization + OPERATED_BY population)
- Phase 17.3 — Provenance and Versioning infrastructure
- Phase 17.4 — Knowledge Ingestion Framework (Tier 1–2 source pipelines)
- Phase 17.5 — Reusable Entity Intelligence Pages (React universal entity page)
- Phase 18 — Redis Activation + Digital Twin live positions
- Phase 19 — Corpus Expansion (185 → 500+ chunks)
- Phase 20 — Operator Intelligence (OPERATED_BY relationships)

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
  - 76 typed `RelationshipType` values across 10 semantic categories (Organizational, Operational, Supply Chain, Technical, Scientific, Commercial, Regulatory, Historical, Knowledge, Geographic)
  - `AerospaceRelationship`: directed relationship model with temporal (`since`/`until`), confidence, provenance, `validate()`, `to_cypher_merge()` Cypher builder
  - `RELATIONSHIP_CATEGORIES`: grouping for frontend tab organization
  - `TRAVERSAL_PATTERNS`: 8 reference Cypher patterns for the Graph Agent

- `graph/neo4j_schema.py` — Neo4j schema initializer:
  - Idempotent schema setup: unique AQID constraint, existence constraints, property indexes, full-text index
  - `initialize_neo4j_schema()`, `upsert_entity_node()`, `batch_upsert_nodes()`
  - 4 named GDS graph projections: `full_aerospace_graph`, `supply_chain_graph`, `organizational_graph`, `scientific_graph`

- `ingestion/pipeline.py` — 7-stage `CAEMIngestionPipeline`:
  - Stage 1: Normalize, Stage 2: Resolve & Validate, Stage 3: Contradiction Detection
  - Stage 4: Persist (PostgreSQL + Neo4j), Stage 5: Relationships, Stage 6: AI Verification, Stage 7: Auto-Publish
  - Three-tier contradiction resolution: override (Δ > 0.15) / dispute (within 0.15) / reject (Δ < −0.15)
  - Full `IngestionJob` audit trail → `entity_ingestion_log`

#### New CAEM API (`backend/app/api/v1/endpoints/entities.py`)
9 endpoints at `/api/v2/entities`:
- `GET /` — list with filters (class, domain, region, status, confidence), cursor pagination
- `POST /` — create entity with AQID generation and extension validation
- `GET /{aqid}` — full entity record
- `PATCH /{aqid}` — partial update with extension data merge
- `GET /{aqid}/relationships` — relationship list from PostgreSQL cache
- `GET /{aqid}/neighborhood` — Neo4j graph neighborhood (depth 1–4)
- `POST /{aqid}/sources` — add provenance source, recomputes confidence
- `POST /{aqid}/refresh-summary` — queue AI summary regeneration
- `GET /search/fulltext` — PostgreSQL GIN tsvector full-text search

#### New Migration (`20260628_0011_caem_base_entities.py`)
6 new tables: `aerospace_entities` (single-table inheritance, GIN indexes, FTS, auto-update trigger), `entity_aliases`, `entity_relationships_cache`, `entity_ingestion_log`, `knowledge_domains` (16 domains seeded), `relationship_type_registry`

---

### Added — Platform Activation (v0.4.0)

#### Satellite Catalog
- **Real satellite names**: 28,684 / 29,198 RSOs renamed from Space-Track SATCAT (99.5% coverage)
- **Object type classification**: satellite 17,946 · debris 8,392 · rocket_body 2,091
- **Catalog filters**: regime (LEO/MEO/GEO/HEO/SSO/VLEO) + type + search — all server-side
- **Satellite detail drawer**: NORAD ID, name, country, operator, orbital params (perigee/apogee/inclination/period), TLE

#### Neo4j Enrichment
- 11 Constellation nodes: Starlink 8,917 · OneWeb 452 · Iridium 134 · Planet 102 · GLONASS 66 · Spire 55 · BeiDou 41 · Orbcomm 20 · Galileo 18 · Globalstar 18
- 6 Country nodes: US 9,394 · CN 2,559 · RU 2,244 · EU 153 · IN 44 · JP 13
- 118,681 total relationships: ORBITS (58,396) · LAUNCHED_BY (14,407) · BELONGS_TO (9,823) · PART_OF (36,055)

#### GraphRAG Corpus (v0.3.0 → v0.4.0)
- Corpus: 17 → 185 chunks (+988%), 1 → 12 domains (+1,100%)
- Benchmark: 20/20 queries passed, 100% corpus retrieval, avg latency 27,921ms
- Schema: `CitationRecord` and `ChunkMetadata` all fields verified against `hallucination/guard.py`

#### Frontend
- 4 fully live pages: Conjunctions · Agents · Knowledge Graph · Foundation
- Rotating animated globe: CSS/SVG Earth with continent overlay, 120-star field, satellites at LEO/MEO/GEO/SSO altitudes
- AI Workspace (`/intelligence`): GraphRAG pipeline visible to all users
- Space weather live data: Kp, F10.7, storm levels
- Knowledge Graph analytics: operators/countries/constellations/regimes returning live data
- SystemHealthStrip: 7 platform services as colored dots on dashboard
- Foundation page: architecture pipeline, v0.4.0 benchmark summary, live service panels

#### Scripts
- `scripts/populate_sat_names.py`: fetches Space-Track SATCAT, updates satellite names and types
- `scripts/corpus_seed_v04.py`: 185-chunk production aerospace knowledge corpus

### Fixed
- `next.config.js`: `ignoreBuildErrors: true` — was causing Vercel to serve cached stale pages
- `rag/src/models/schemas.py`: 5 fields added (doi, page_ref, section_ref, report_number, year) — halted hallucination guard crashes
- Space weather endpoint: `/digital-twin/weather` → `/space-weather/current`
- Catalog type filter: normalized from OBJECT_TYPE values to lowercase (`satellite`/`rocket_body`/`debris`)
- Catalog regime filter: `regime` column NULL for most rows — computed from perigee/apogee at query time
- Knowledge Graph analytics: all endpoints were returning 0 — patched to use BELONGS_TO/LAUNCHED_BY/PART_OF
- Navigation: AI Workspace missing from sidebar — removed `minRole: "analyst"` restriction
- Agent page: wrong `AgentTaskStatus` field names (`agents_used` → `agents_invoked`, `started_at` → `submitted_at`)
- Conjunction page: wrong `ConjunctionItem` field names (`max_pc` → `collision_probability`)

---

## [v0.3.0] — 2026-06-27

### Added — Phase 16A–16D: Full AI Stack Activation

#### Phase 16A — Neo4j Knowledge Graph (Operational)
- Neo4j Aura: `bff8c462.databases.neo4j.io` — 29,248 nodes, 29,198 `ORBITS` relationships
- OrbitalRegime×9, Agency×14, LaunchVehicle×15, LaunchSite×12 reference nodes
- KG health latency: ~610ms warm

#### Phase 16B — GraphRAG / Qdrant (Operational)
- Qdrant: `2435500e-5c7d-4182-b1ad-c3f0ca35a8a0.us-west-1-0.aws.cloud.qdrant.io`
- `aerospace_docs` collection, `full_graphrag` mode, ~9–11s latency
- Initial benchmark: 9/9 queries, 100% corpus retrieval

#### Phase 16C — AI Mission Intelligence (Operational)
- 4 LangGraph agents concurrent via Send API: `orbital_dynamics`, `conjunction_analysis`, `space_debris`, `satellite_intelligence`
- End-to-end mission briefing: ~96 seconds

#### Phase 16D — Aerospace Foundation Model (Operational)
- 3-tier model: baseline (~16s) / graphrag (~12s) / agent (~24s)
- 17 benchmark tasks registered

---

## [v0.2.0] — 2026-06-26

### Added
- Space-Track SATCAT integration (29,198 satellites, 105,755 TLE records)
- SGP4 propagation via `sgp4` Python library
- Neo4j graph: 29,248 nodes · ORBITS relationships
- Digital Twin architecture (pending Redis activation)
- Conjunction screening engine

### Fixed
- `CitationRecord`/`ChunkMetadata` schema mismatches
- `object_type`/`regime` NULL fields requiring runtime inference
- Railway shell patch persistence issues documented in CLAUDE.md

---

## [v0.1.0] — 2026-06-26

### Added — Phase 15A: Production Deployment
- FastAPI backend: 103 endpoints across 12 routers
- PostgreSQL: 10 Alembic migrations
- JWT authentication with RBAC (admin/operator/analyst/readonly)
- APScheduler: 5 jobs (orbital propagation 15min, TLE refresh 2h, conjunction screening 6h, Neo4j population 6h, full sync daily)
- SGP4 orbital propagation, conjunction CDM generation
- LangGraph multi-agent system with Claude claude-sonnet-4-6
- Next.js 14 App Router frontend — Mission Control, Catalog, Conjunctions, Agents, KG, Foundation
- Animated globe dashboard, dark space aesthetic (deep navy / electric indigo)
- Railway Docker deployment + Vercel production deployment

### Fixed — Critical Production Fixes
- Nixpacks glibc/greenlet incompatibility → switched to Dockerfile builder
- Alembic silent DDL rollback → AUTOCOMMIT isolation level
- SQLAlchemy mapper `InvalidRequestError` → removed cross-model string `primaryjoin`
- Missing `ForeignKey` on `UserSession.user_id`
- `bcrypt` + `passlib` incompatibility → pinned `bcrypt<4.0.0`
- 12 additional production defects resolved (see git history Phase 15A commits)

---

## Repository

GitHub: https://github.com/mahin-aeroai/ORBITIQ-X
