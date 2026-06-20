# ORBITIQ-X Development Roadmap

> Last updated: 2026-06-20 | Version: 0.1.0

---

## Vision

ORBITIQ-X v1.0 will be the first open-source aerospace foundation model
capable of answering natural-language queries about the space environment,
generating maneuver plans, monitoring conjunctions, and reasoning over a
comprehensive aerospace knowledge graph — all in a single unified platform.

---

## Phase 0 — Foundation & DevOps (Month 1)
**Goal:** Every developer can clone → run → develop in <15 minutes.

- [x] Repository structure & monorepo setup
- [x] Docker Compose dev stack (all datastores)
- [x] Environment variable strategy & `.env.example`
- [x] CI/CD pipeline skeleton (GitHub Actions)
- [x] Pre-commit hooks (Black, Ruff, ESLint, mypy)
- [x] ADR framework initialized
- [ ] Health check endpoints for all services
- [ ] Seed scripts for reference datasets
- [ ] Developer documentation site (MkDocs)
- [ ] GitHub Actions: lint, typecheck, test, build

**Exit Criteria:** `docker compose up` → all green health checks.

---

## Phase 1 — Orbital Engine & SSA API (Month 2)
**Goal:** Production-grade orbital propagation and SSA REST API.

### Orbital Engine
- [ ] SGP4/SDP4 propagator (via python-sgp4, validated against STK)
- [ ] J2-perturbed analytical propagator for LEO
- [ ] TLE parser & validator (format compliance + epoch sanity checks)
- [ ] Batch propagation engine (>10,000 objects, parallel)
- [ ] Orbital element conversions (Cartesian ↔ Keplerian ↔ TLE)
- [ ] Ground station pass predictor (elevation mask, access windows)
- [ ] Coverage analysis (single satellite + constellation)

### SSA API (FastAPI)
- [ ] `/ssa/catalog` — RSO catalog (Space-Track integration)
- [ ] `/ssa/tle/{norad_id}` — Current TLE fetch & cache
- [ ] `/ssa/propagate` — Ephemeris generation endpoint
- [ ] `/ssa/conjunctions` — Active CDM listing
- [ ] `/ssa/conjunctions/{id}` — CDM detail (Pc, miss distance, covariance)
- [ ] `/ssa/passes` — Ground station pass predictions
- [ ] WebSocket `/ws/ssa/live` — Real-time RSO position stream

### Conjunction Analysis
- [ ] Foster method Pc computation
- [ ] Short-encounter check (Patera 2001)
- [ ] Monte Carlo Pc (fallback for high-eccentricity)
- [ ] CDM generation (CCSDS 508.0-B-1 compliant)
- [ ] Alert threshold configuration per operator

**Exit Criteria:** Propagate ISS TLE to sub-km accuracy over 24h vs STK reference.

---

## Phase 2 — Knowledge Graph (Month 3)
**Goal:** Queryable aerospace ontology with 500k+ entities.

- [ ] OWL 2 aerospace ontology design
  - Entities: Satellite, Launch Vehicle, Operator, Orbit, Payload,
    GroundStation, Maneuver, Mission, Debris, Country
  - Properties: `hasMass`, `inOrbit`, `operatedBy`, `launchedBy`,
    `conjunctsWith`, `isDebrisOf`, `successorOf`
- [ ] Neo4j schema & constraints
- [ ] Data ingestion pipelines:
  - [ ] UCS Satellite Database → graph
  - [ ] COSPAR International Designator → graph
  - [ ] CelesTrak active satellites → graph
  - [ ] Launch history (Gunter's Space Page scraper) → graph
- [ ] Cypher query library (50+ parameterized queries)
- [ ] SPARQL-over-Neo4j interface
- [ ] Knowledge Graph API endpoints
  - `GET /kg/entity/{id}` — Entity detail + neighborhood
  - `GET /kg/path` — Shortest path between entities
  - `POST /kg/query` — Raw Cypher execution (admin only)
  - `GET /kg/stats` — Graph statistics
- [ ] Automated entity resolution (NORAD ID ↔ COSPAR ID ↔ name)
- [ ] Relationship extraction from unstructured mission documents

**Exit Criteria:** Answer "Which LEO satellites are operated by ISRO and launched after 2020?" in <200ms.

---

## Phase 3 — RAG Pipeline (Month 4)
**Goal:** Faithfulness-scored Q&A over aerospace knowledge corpus.

### Corpus Ingestion
- [ ] CCSDS standards (PDF → chunks)
- [ ] NASA technical reports (NTRS)
- [ ] ESA technical notes
- [ ] FAA AST licensing documents
- [ ] USSF SSA reports
- [ ] arXiv aerospace papers (automated scraper)
- [ ] Space-Track CDM history

### Indexing
- [ ] Text chunking pipeline (size=512, overlap=64, sentence-aware)
- [ ] Embedding generation (text-embedding-3-large, batch=32)
- [ ] FAISS IVFFlat index (primary, offline)
- [ ] Weaviate vector index (production, metadata-filtered)
- [ ] BM25 sparse index (Elasticsearch / OpenSearch)
- [ ] Hybrid retrieval fusion (RRF algorithm)

### Generation
- [ ] Prompt templates for aerospace domain queries
- [ ] Cross-encoder reranking (ms-marco-MiniLM-L-6-v2)
- [ ] Answer synthesis with citation attribution
- [ ] Hallucination detection (NLI-based faithfulness check)
- [ ] Streaming response support (SSE)

### Evaluation
- [ ] RAGAs metrics integration (faithfulness, relevance, recall)
- [ ] Aerospace QA benchmark dataset (100 curated questions)
- [ ] Automated evaluation pipeline (post-indexing)

**Exit Criteria:** RAGAs faithfulness > 0.85 on aerospace benchmark.

---

## Phase 4 — Multi-Agent System (Month 5)
**Goal:** Autonomous multi-agent reasoning for SSA & mission tasks.

### Agent Architecture
- [ ] LangGraph supervisor orchestrator
- [ ] Tool registry & dynamic tool loading
- [ ] Agent message bus (Redis Streams)
- [ ] Reasoning trace persistence (PostgreSQL)
- [ ] Human-in-the-loop checkpoints for maneuver approval

### Agents
- [ ] **SSA Agent**
  - Monitor conjunction alerts (>Pc threshold)
  - Generate natural-language collision risk reports
  - Suggest avoidance maneuver windows
- [ ] **Mission Agent**
  - Parse natural-language mission requirements
  - Generate trajectory options (Hohmann, bi-elliptic, low-thrust)
  - Compute delta-V budgets
- [ ] **Catalog Agent**
  - Identify RSOs from partial descriptors
  - Enrich catalog entries from multiple sources
  - Detect catalog discrepancies (NORAD vs COSPAR vs operator)
- [ ] **Knowledge Agent**
  - Traverse knowledge graph to answer entity queries
  - Infer relationships not explicitly stored
  - Cross-reference with RAG for document support

### API
- [ ] `POST /agents/task` — Submit async task to orchestrator
- [ ] `GET /agents/task/{id}` — Task status & reasoning trace
- [ ] `WebSocket /ws/agents/{id}` — Live agent reasoning stream

**Exit Criteria:** Agent correctly identifies top-3 conjunction risk objects for a given RSO, with cited reasoning steps.

---

## Phase 5 — Mission Control UI (Month 6)
**Goal:** Production mission control interface.

### 3D Globe & Orbital Visualization
- [ ] CesiumJS integration (3D globe, TLE rendering)
- [ ] Real-time satellite position updates (30s tick)
- [ ] Ground track visualization
- [ ] Coverage footprint overlay
- [ ] Conjunction approach visualization (relative motion)

### SSA Dashboard
- [ ] Conjunction alert table (sortable by Pc, time-to-TCA)
- [ ] CDM detail drawer (miss distance, covariance ellipsoid)
- [ ] RSO catalog search & filter
- [ ] Space weather panel (Kp index, solar flux, geomagnetic storm alerts)
- [ ] Debris cloud evolution timeline

### Knowledge Graph Explorer
- [ ] Force-directed graph visualization (vis.js / D3)
- [ ] Entity search with type filtering
- [ ] Path exploration between entities
- [ ] Entity detail cards with source citations

### Agent Console
- [ ] Natural-language task input
- [ ] Streaming reasoning trace display
- [ ] Tool call inspector
- [ ] Task history with replay

### Mission Planner
- [ ] Mission requirement form (orbit type, payload, constraints)
- [ ] Trajectory comparison view (multiple options)
- [ ] Delta-V budget breakdown
- [ ] Timeline Gantt chart

**Exit Criteria:** End-to-end mission planning flow completable by non-specialist operator.

---

## Phase 6 — Production Hardening (Month 7)
**Goal:** Deployment-ready with SLA-grade reliability.

- [ ] Kubernetes manifests (all services)
- [ ] Horizontal Pod Autoscaling (backend, agents)
- [ ] Helm chart packaging
- [ ] Terraform IaC (AWS EKS + RDS + ElastiCache + S3)
- [ ] Zero-downtime deployment (blue/green)
- [ ] Database migration CI gate (Alembic)
- [ ] API rate limiting (Redis-backed)
- [ ] Authentication hardening (OAuth2 + PKCE)
- [ ] RBAC (admin, operator, analyst, viewer)
- [ ] Audit logging (all data mutations)
- [ ] Prometheus metrics (custom aerospace SLIs)
- [ ] Grafana dashboards (system + domain: conjunction count/hr, propagation latency)
- [ ] PagerDuty alerting for Pc threshold breaches
- [ ] Load testing (k6: 1000 concurrent propagation requests)
- [ ] OWASP security review
- [ ] Penetration test (Space-Track credential handling)

**Exit Criteria:** 99.5% uptime over 30-day soak test. P99 propagation API < 100ms.

---

## Phase 7 — External Integrations (Month 8)
**Goal:** Production data feeds from authoritative space sources.

- [ ] Space-Track.org full integration (TLE, CDM, conjunction screening)
- [ ] CelesTrak real-time feeds
- [ ] NOAA Space Weather APIs (automated ingestion → InfluxDB)
- [ ] ESA DISCOS (European Space Agency satellite database)
- [ ] LeoLabs API (optional commercial SSA data)
- [ ] AWS Ground Station API (future: direct telemetry)
- [ ] CCSDS standardized message exchange (CDM, OEM, OMM)
- [ ] Webhook system for operator alert delivery

---

## Backlog / Future Phases

| Feature | Priority |
|---------|---------|
| On-board autonomy simulation (FDIR) | High |
| Maneuver optimization (NLP trajectory solvers) | High |
| Foundation model fine-tuning on aerospace corpus | High |
| Multi-constellation coverage optimizer | Medium |
| Spectrum / RF interference analysis | Medium |
| ITAR-compliance mode (access controls) | Medium |
| Mobile mission control app (React Native) | Low |
| AR visualization (satellite passes via phone camera) | Low |

---

## Version Milestones

| Version | Description | Target Date |
|---------|-------------|-------------|
| v0.1.0 | Foundation scaffold | 2026-06 |
| v0.2.0 | Orbital Engine + SSA API | 2026-07 |
| v0.3.0 | Knowledge Graph | 2026-08 |
| v0.4.0 | RAG Pipeline | 2026-09 |
| v0.5.0 | Multi-Agent System | 2026-10 |
| v0.8.0 | Mission Control UI | 2026-11 |
| v1.0.0 | Production Release | 2026-12 |
