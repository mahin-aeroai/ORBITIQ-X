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
