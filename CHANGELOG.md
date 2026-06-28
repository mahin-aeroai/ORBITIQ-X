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

## [v0.5.0-dev] — Phase 18 — Redis Activation + Digital Twin

### Added

#### Redis Session (`backend/app/db/redis_session.py`)
- Retry logic with exponential backoff: `MAX_INIT_ATTEMPTS=5`, delay doubles from 2s → 60s cap
- `get_redis_status()`: detailed diagnostics dict (connected, uptime_s, last_error, connection_attempts, impact_if_down, fix instructions)
- `reconnect_redis()`: manual reconnection trigger (ping-first, then re-init)
- `_start_reconnect_monitor()`: background asyncio task that pings every 60s and auto-reconnects on failure
- Explicit `REDIS_URL` env var fallback check with actionable warning log

#### Digital Twin Control API (`backend/app/api/v1/endpoints/digital_twin_control.py`)
- `GET  /digital-twin/redis-status` — Full Redis connection diagnostics with impact list and fix instructions
- `POST /digital-twin/redis-reconnect` — Manual reconnect trigger (no redeployment required)
- `GET  /digital-twin/status` — Digital Twin health: Redis, propagation count, density map, SSE capability flags
- `POST /digital-twin/activate` — Background SGP4 propagation cycle for all tracked objects
- `GET  /digital-twin/live-positions` — Redis/in-memory live propagated positions (regime filter, limit)
- `POST /digital-twin/catalog-sync?mode=full|incremental` — Catalog sync + auto-propagation chain

#### System Improvements
- `main.py`: `/ready` endpoint enhanced — now returns Redis status alongside DB health (Redis down = degraded, not 503)
- `router.py`: Digital Twin Control router wired in

#### Frontend — RedisStatusWidget (`frontend/src/components/ssa/RedisStatusWidget.tsx`)
- Real-time Redis + Digital Twin status panel (30s poll)
- StatusDot with pulse animation when healthy
- Impact list when Redis is unavailable (SSE, Digital Twin, lock, cache)
- Fix instruction display with Railway-specific guidance
- Action buttons: ↻ Reconnect Redis, ▶ Activate Digital Twin, Incremental/Full catalog sync
- Added to System Status page (`/system`)

#### Operations Guide (`docs/OPERATIONS/REDIS_ACTIVATION.md`)
- Railway Redis Plugin setup (Option A) and External Redis setup (Option B)
- Step-by-step: add REDIS_URL → verify connection → activate Digital Twin → catalog sync
- Redis key schema table (twin:state, twin:density, pub/sub channel, scheduler lock)
- Troubleshooting table: REDIS_URL missing, wrong password, timeout, VPC issues

---

## [v0.5.0-dev] — Phase 17.6 — Cross-Entity Navigation

### Added

#### EntityLink (`frontend/src/components/caem/EntityLink.tsx`)
- Universal component that renders any AQID as a navigable link to its Entity Intelligence Page
- Four variants: `inline` (prose link), `badge` (colored pill), `chip` (compact mono), `card` (sidebar card with class + AQID)
- `parseAqid()`: derives entity class and human label from AQID slug (e.g. `AQID-MISSION-ARTEMIS-II` → "Artemis II")
- Class-specific colors + icons for 20+ entity types — consistent with EntityHeader palette
- `AutoLink`: renders a string and converts any `AQID-*` tokens into EntityLink components automatically

#### EntityBreadcrumb (`frontend/src/components/caem/Breadcrumb.tsx`)
- Breadcrumb trail for graph exploration: `Mission Control › Entity Browser › [trail] › Current [Here]`
- `sessionStorage`-backed navigation history — persists across page navigations within a session
- Max 8 history entries; shows last 3 in trail (overflow truncated)
- "Clear trail" button; class icons in trail items
- `StaticBreadcrumb`: simpler static variant for non-entity pages

#### RelatedEntitiesSidebar (`frontend/src/components/caem/RelatedEntitiesSidebar.tsx`)
- 64px sidebar panel alongside entity intelligence page content
- Three contextual sections (all lazy-loaded, non-blocking):
  - **Graph Neighbors**: up to 8 entities from the `/neighborhood` endpoint (EntityLink card variant)
  - **More [Class]**: up to 6 same-class entities (TanStack Query, links to `/entities?class=...`)
  - **Also in [Domain]**: up to 5 cross-class entities sharing the primary domain
- **Quick Jump** panel: Entity Browser, Knowledge Graph, AI Workspace, Satellite Catalog

#### Wired navigation across existing pages
- `/entities/[aqid]/page.tsx` — Breadcrumb added above EntityHeader; sidebar added to right of main content; two-column layout (flex-1 content + 64px sidebar)
- `catalog/page.tsx` — Satellite detail drawer: "◆ Entity Page" button appears when `s.aqid` is present
- `knowledge-graph/page.tsx` — Search result rows: "◆ Entity" link appears on hover (opacity transition); row gets `group` hover border

---

## [v0.5.0-dev] — Phase 17.5 — Reusable Entity Intelligence Pages

### Added

#### CAEM API Client (`frontend/src/lib/caem-api.ts`)
- Typed wrappers for all `/api/v2/*` CAEM endpoints
- Types: `EntitySummary`, `EntityFull`, `TimelineEvent`, `KeyFact`, `ProvenanceRecord`, `RelationshipEntry`, `NeighborhoodGraph`, `GraphNode`, `GraphEdge`
- `caemApi`: `listEntities()`, `getEntity()`, `getRelationships()`, `getNeighborhood()`, `searchEntities()`, `refreshSummary()`, `getOntology()`, `getTemporalSnapshot()`, `getEntityFacts()`, `getSnapshots()`

#### CAEM Components (`frontend/src/components/caem/`)
- `EntityHeader.tsx` — Entity class badge (20+ class types with icon + color), display name, copyable AQID, lifecycle badge, confidence badge (Authoritative/Verified/Confirmed/Unverified/Disputed), aliases, tags, domains. All using existing design tokens.
- `AISummaryCard.tsx` — AI executive summary prose + key facts grid + manual refresh trigger with async queue notification
- `EntityTimeline.tsx` — Horizontally scrollable chronological timeline; color-coded by importance (critical red / major indigo / minor slate); date precision-aware formatting; linked entity chips
- `RelationshipPanel.tsx` — 10-category tab group (All/Org/Ops/Tech/Science/Supply/Commercial/Regulatory/Historical/Knowledge/Geo); search filter; confidence dot; provenance link; direction arrow (→ outbound / ← inbound); each row links to peer entity page
- `QuickFacts.tsx` — Entity-class-aware fact extraction from `extension_data` (satellite orbital params, LV payload capacity, company revenue/employees, mission status/destination, paper DOI/citations, country space budget); mini SVG radial neighborhood graph preview
- `ProvenancePanel.tsx` — Source cards with tier label, confidence %, verification badge, publisher, citation text; show all/collapse; version note

#### Entity Pages (`frontend/src/app/entities/`)
- `page.tsx` — Entity Browser: 24-per-page grid, class filter pills (17 entity classes), full-text search (≥2 chars), TanStack Query with stale time, loading skeleton, entity cards with class badge + description + tags + AI summary snippet + confidence
- `[aqid]/page.tsx` — Universal Entity Intelligence Page: 8-panel canonical layout:
  1. EntityHeader (sticky)
  2. AI Intelligence Summary
  3. Quick Facts + Mini Graph
  4. Timeline
  5. Relationships (tab-grouped)
  6. Technical Details (extension_data flat fields)
  7. Sources & Provenance
  8. Historical Context (long_description)
  Loading skeleton, error state, TanStack Query for entity + relationships + neighborhood in parallel

#### Navigation
- `SideNav.tsx` — Added "Entity Browser" (icon ◆) after Knowledge Graph entry

---

## [v0.5.0-dev] — Phase 17.4 — Knowledge Ingestion Framework

### Added

#### Ingestion Sources (`backend/app/caem/ingestion/sources/`)
- `base.py` — `SourceAdapter` ABC + `SourceRecord` + `FetchResult`:
  - `SourceRecord`: normalized adapter output — source_id, tier, entity_class, canonical_name, fields, raw_relationships, content_hash
  - `FetchResult`: per-run metrics (records_fetched, records_parsed, errors, duration_s)
  - `SourceAdapter.run()`: wraps `fetch()` generator with error handling and max_records enforcement

- `tier1_space_track.py` — `SpaceTrackAdapter` (Tier 2 / Registry):
  - Cookie-based session auth against Space-Track.org REST API
  - SATCAT ingestion with SATCAT_FIELD_MAP → CAEM extension field mapping
  - Batch range splitting (30K records/request to avoid timeouts)
  - OBJECT_TYPE normalization: PAYLOAD → satellite, ROCKET BODY → rocket_body, DEBRIS → debris
  - Rate-limit compliance: 3s sleep between requests (~20 req/min)

- `tier1_nasa.py` — NASA adapters (Tier 1 / Official):
  - `NASATechPortAdapter`: NASA TechPort project API → Technology/Program entities (paginated)
  - `NASAMissionAdapter`: Curated seed of 8 major NASA missions (Artemis, JWST, Perseverance, DART, ISS, Voyager 1, Hubble) with relationships (MANAGED_BY → NASA, LAUNCHED_BY → launch vehicle)

- `tier2_registries.py` — Tier 2 registry adapters:
  - `CelestrakAdapter`: SATCAT CSV parser (disabled in production — Railway IP blocked; use for local dev)
  - `UNOOSAAdapter`: UNOOSA registration seed (3 canonical records; full API integration in Phase 17.4.1)

#### Ingestion Orchestrator (`backend/app/caem/ingestion/orchestrator.py`)
- `ADAPTER_REGISTRY`: maps 5 adapter names → classes for dynamic loading
- `ScheduleEntry`: tracks last_run_at, next_run_at, total_runs, is_due()
- `IngestionOrchestrator`:
  - `register_adapter()` / `register_all()`: dynamic adapter registration with config
  - `run_due()`: runs all adapters that have passed their interval
  - `run_adapter()`: force-run a single adapter
  - `_source_record_to_parsed()`: SourceRecord → ParsedEntity (pipeline bridge)
  - `_extract_relationships()`: raw_relationships → ParsedRelationship list
  - `_record_fact_provenance()`: field-level provenance via ProvenanceService for high-value fields
  - `get_schedule_status()`: current schedule state for monitoring

#### New API (`backend/app/api/v1/endpoints/ingestion.py`)
9 endpoints at `/api/v2/ingestion`:
- `GET  /adapters` — All registered adapters with schedule state
- `GET  /adapters/{name}` — Adapter status + last 10 runs
- `POST /adapters/{name}/run` — Manual trigger (background task)
- `GET  /schedule` — Full schedule with is_due flags
- `GET  /log` — Run history (filter by adapter/status)
- `GET  /log/{job_id}` — Single job result
- `PATCH /adapters/{name}/config` — Update interval, limits, enabled
- `POST /adapters/{name}/enable` — Enable adapter
- `POST /adapters/{name}/disable` — Disable adapter

#### New Migration (`20260628_0014_ingestion_framework.py`)
3 new tables:
- `ingestion_schedule_log` — Per-run audit trail for every adapter execution
- `ingestion_source_config` — Persisted adapter configs; seeded with 5 adapters (celestrak disabled by default)
- `ingestion_dedup_cache` — Content hash deduplication to skip unchanged records on re-run

### Validation
- 5 adapters in registry: space_track, nasa_techport, nasa_missions, celestrak, unoosa
- NASA Mission adapter: 8 records with correct MISSION entity class, Tier 1 provenance
- UNOOSA adapter: 3 seed records with correct COSPAR IDs
- Content hash: 16-char stable identifier per record
- Space-Track range split: 1--99999 → 4 batches of 30K correctly

---

## [v0.5.0-dev] — Phase 17.3 — Provenance & Versioning

### Added

#### Provenance Package (`backend/app/caem/provenance/`)
- `models.py` — Core data models:
  - `SourceTier` (6-tier authority hierarchy) + `TIER_CONFIDENCE_WEIGHTS`
  - `infer_source_tier()`: auto-classify source URL → tier (NASA/ESA/SpaceX → Tier 1; NORAD/COSPAR → Tier 2; IEEE/arXiv/ACM → Tier 3)
  - `FactRecord`: field-level provenance — source, tier, confidence, citation, DOI, is_primary, is_superseded chain
  - `ContradictionRecord`: conflict between two sources on the same fact — with three-tier resolution (override/dispute/reject)
  - `ReviewQueueItem`: human review task with priority (critical/high/medium/low), assignment, and resolution tracking
  - `VersionSnapshot`: immutable point-in-time entity state copy with field_diffs and change_summary

- `service.py` — `ProvenanceService`:
  - `record_fact()`: store field provenance with auto tier inference and confidence defaulting
  - `detect_contradiction()`: compare incoming vs existing primary fact — applies three-tier resolution protocol
  - `resolve_review()`: apply human reviewer decision — updates fact_provenance, contradiction_log, review_queue atomically
  - `create_snapshot()`: serialize full entity state to version_snapshots (triggered on publish or manually)
  - `get_fact_history()`, `get_entity_facts()`, `get_contradictions()`, `get_review_queue()`, `get_snapshots()`

#### New API (`backend/app/api/v1/endpoints/provenance.py`)
9 endpoints at `/api/v2/provenance`:
- `GET  /tiers` — Source authority tier reference with confidence weights
- `GET  /{aqid}/facts` — All provenance facts grouped by field
- `GET  /{aqid}/facts/{field}` — Full history for one field (all sources, primary flag, superseded chain)
- `POST /{aqid}/facts` — Record a fact + auto-detect contradiction
- `GET  /{aqid}/snapshots` — Version snapshots list (newest first)
- `GET  /snapshots/{snapshot_id}` — Full snapshot with complete entity_state
- `POST /{aqid}/snapshots` — Manual snapshot trigger
- `GET  /contradictions` — Query contradiction log (filter by aqid/status)
- `GET  /review` — Human review queue (sorted by priority then age)
- `POST /review/{review_id}/resolve` — Human resolver applies override/reject/merge

#### New Migration (`20260628_0013_provenance_versioning.py`)
5 new tables:
- `fact_provenance` — field-level provenance; GIN-indexed; tracks is_primary/is_superseded chain
- `contradiction_log` — immutable conflict record; resolution + audit trail
- `review_queue` — human review tasks with priority, assignment, resolution
- `version_snapshots` — immutable entity state snapshots; GIN-indexed entity_state JSONB
- `snapshot_trigger_log` — queue for publish-triggered snapshots (PostgreSQL trigger)
- PostgreSQL trigger `trg_entity_publish_snapshot`: auto-queues snapshot when `lifecycle_status → 'published'`

### Fixed
- `infer_source_tier()`: added IEEE, arXiv, ACM, Springer, Elsevier to Tier 3 domain list

---

## [v0.5.0-dev] — Phase 17.2 — Universal Relationship Ontology

### Added

#### Relationship Ontology (`backend/app/caem/ontology/`)
- `relationship_registry.py` — `RelationshipDefinition` dataclass with formal specification for all 76 relationship types:
  - Cardinality rules: `ONE_TO_ONE` / `ONE_TO_MANY` / `MANY_TO_ONE` / `MANY_TO_MANY`
  - Allowed source and target entity class sets (enforced at ingestion + API)
  - Temporal semantics: 52 of 76 types carry meaningful `since`/`until` properties
  - Bidirectional flag: 5 relationship types stored in both directions automatically
  - Confidence floor per type (0.50–0.85 range by category)
  - Display and inverse labels for frontend graph edges
  - Full lookup helpers: `get_definition()`, `validate_relationship_classes()`, `get_relationships_for_class()`, `get_category_relationships()`, `get_temporal_relationships()`, `get_bidirectional_relationships()`
  - Runtime coverage check: raises `RuntimeError` if any `RelationshipType` is unregistered

#### Neo4j Graph Schema (`backend/app/caem/graph/neo4j_relationship_schema.py`)
- Relationship property constraints on `OPERATED_BY`, `LAUNCHED_BY`, `FUNDED_BY`
- Confidence and `is_current` indexes on `OPERATED_BY` for fast filtering
- Full-text index on relationship `notes` and `citation_text`
- `TEMPORAL_SNAPSHOT_CYPHER`: point-in-time relationship query (since/until filtering)
- `BULK_RELATIONSHIP_UPSERT_TEMPLATE`: UNWIND-based batch upsert per relationship type
- `TRAVERSAL_LIBRARY`: 11 named graph traversal patterns for the Graph Agent:
  `operator_satellites`, `launch_vehicle_missions`, `country_space_assets`,
  `technology_lineage`, `paper_citation_network`, `supply_chain_full`,
  `organization_influence`, `mission_full_graph`, `constellation_members`,
  `risk_adjacency`, `standard_compliance_map`
- `OPERATED_BY` population utilities: `POSTGRES_OPERATOR_FETCH`, `OPERATED_BY_FROM_NORAD`, `OPERATED_BY_BATCH_FROM_SATCAT` (ready for Phase 17.3 data population)
- `initialize_relationship_schema()`, `get_temporal_snapshot()`, `bulk_upsert_relationships()`

#### New API Endpoints (`backend/app/api/v1/endpoints/relationships.py`)
- `GET    /api/v2/relationships/ontology` — Full registry (76 types), filterable by category/temporal
- `GET    /api/v2/relationships/ontology/categories` — Category summary with counts
- `GET    /api/v2/relationships/ontology/{rel_type}` — Single type formal definition
- `POST   /api/v2/relationships/validate` — Validate entity class compatibility before creating
- `POST   /api/v2/relationships` — Create relationship (Neo4j + PostgreSQL cache + audit log)
- `GET    /api/v2/relationships/{source_aqid}` — Entity relationships (filterable by direction/category/type/confidence)
- `DELETE /api/v2/relationships/{rel_id}` — Soft-delete (is_current=False; never hard-deleted)
- `GET    /api/v2/relationships/snapshot/{aqid}` — Point-in-time temporal snapshot
- `GET    /api/v2/relationships/traversal/{pattern}` — Execute named traversal pattern
- `GET    /api/v2/relationships/for-class/{entity_class}` — All valid relationship types for an entity class

#### New Migration (`20260628_0012_relationship_ontology.py`)
- `relationship_ontology` — Formal registry table: all 76 types seeded with cardinality, direction, temporal, confidence floor, display labels; GIN indexes on `allowed_sources`/`allowed_targets`
- `relationship_audit_log` — Audit trail for every relationship create/update/delete

### Fixed
- Migration chain: `0012` `down_revision` corrected to `20260628_0011_caem_base_entities`
- Migration `0011` stale comment removed from `down_revision` line

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
