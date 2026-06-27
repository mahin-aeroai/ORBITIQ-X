# ORBITIQ-X — Changelog

All notable changes to ORBITIQ-X are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Planned
- Space-Track catalog sync activation
- Redis pub/sub operational
- Neo4j Aura integration

---

## [v0.1.0] — 2026-06-26

First production release. Full-stack aerospace intelligence platform deployed on Railway (backend) and Vercel (frontend).

### Added

#### Backend
- FastAPI application with 103 API endpoints across 12 routers: auth, ssa, catalog, digital-twin, conjunctions, knowledge-graph, agents, foundation, rag, space-weather, mission, platform
- PostgreSQL schema via 10 Alembic migrations: users, user_sessions, operators, satellites, tle_records, missions, conjunction_events, orbital_events, audit_logs, sync_metrics
- JWT authentication with RBAC — register, login, refresh, logout, role guard (admin/operator/analyst/readonly)
- APScheduler with 5 scheduled jobs: orbital propagation (15min), TLE refresh (2h), conjunction screening (6h), Neo4j population (6h), full catalog sync (daily)
- SGP4 orbital propagation via `sgp4` library
- Conjunction CDM generation and probability-of-collision computation
- LangGraph multi-agent system with Claude claude-sonnet-4-6
- Neo4j knowledge graph integration (operator/satellite/country/constellation)
- Weaviate vector store RAG pipeline
- Space weather integration (NOAA/SWPC)
- Redis pub/sub for real-time SSE conjunction alerts
- Prometheus metrics via `prometheus-fastapi-instrumentator`
- OpenTelemetry distributed tracing
- Sentry error tracking
- structlog structured JSON logging
- Global exception handler with full traceback in JSON response
- `/health` liveness probe + `/ready` readiness probe

#### Frontend
- Next.js 14 App Router application
- Mission Control dashboard with live UTC clock, metrics bar, orbital visualization
- Static SVG orbital surveillance visualization (Cesium temporarily disabled — WebGL incompatibility)
- Space weather panel (Kp index, solar flux, geomagnetic status)
- Active conjunction alerts panel with real-time polling
- Agent activity feed
- System Status page with full service health matrix
- Catalog, Conjunctions, Agents, Knowledge Graph, Foundation placeholder pages
- Edge middleware auth guard with HttpOnly refresh cookie
- TanStack Query data fetching layer
- Responsive dark space aesthetic (deep navy / electric indigo palette)

#### Deployment
- Railway Docker deployment (`backend/Dockerfile.railway`) — `python:3.11-slim-bookworm`
- Vercel production deployment with Next.js 14
- `entrypoint.sh` — DATABASE_URL parsing, Alembic migration execution, gunicorn launch
- `railway.toml` — healthcheck, restart policy, build configuration

### Fixed

#### Critical Production Fixes (Phase 15A)
- **Nixpacks glibc/greenlet incompatibility** — switched from Nixpacks to Dockerfile builder; `python:3.11-slim-bookworm` resolves `GLIBC_2.38` mismatch (`5dbb94e`)
- **Alembic silent DDL rollback** — added `AUTOCOMMIT` isolation level; SQLAlchemy's default transaction wrapping caused all `CREATE TABLE` statements to roll back silently on Railway PostgreSQL 18 (`85be9bf`)
- **SQLAlchemy mapper `InvalidRequestError`** — removed all cross-model string `primaryjoin` relationships (`type: ignore[name-defined]`) across 7 model files; caused crash on every request (`80c8408`)
- **Missing `ForeignKey` on `UserSession.user_id`** — column had comment `"FK → users.id"` but no actual `ForeignKey()` constraint; caused `NoForeignKeysError` on every `User` instantiation (`5054932`)
- **`AuditLog` relationship `back_populates` broken** — `User.audit_logs` removed but `AuditLog.user` still referenced it; caused `InvalidRequestError` (`db0c5ec`)
- **`bcrypt` + `passlib` version incompatibility** — pinned `bcrypt<4.0.0`; `passlib 1.7.4` uses `bcrypt.__about__.__version__` which doesn't exist in bcrypt 4.x (`4ecca4b`)
- **`agent_service.py` `parents[4]` IndexError** — Docker path `/app/app/services/` only has 3 parent levels; fixed with candidate path list (`bf70e98`)
- **DATABASE_URL not reaching Alembic** — `ORBITIQ_DATABASE_URL` now set in entrypoint before migration subprocess (`b423aaa`)
- **`ORJSONResponse` deprecated** — replaced with `JSONResponse` throughout auth endpoints and removed as `default_response_class` (`4b75f56`, `10a0104`)
- **React `Component` class in server component** — removed `GlobeErrorBoundary` from `page.tsx` (server component cannot use React class) (`efe3147`)
- **Next.js build `SyntaxError: Octal escape sequences`** — replaced Cesium `OrbitalGlobe` with pure static SVG component (`593cad9`)
- **Double `/api/v1/` in frontend API URLs** — `NEXT_PUBLIC_API_URL` set with `/api/v1` suffix but code also appended it; fixed with `.split('/api/v1')[0]` (`6cab2c4`)
- **`count_result.scalars().all()` first-user check** — replaced with `COUNT(*)` query (`4276aa7`)
- **Login session state conflict** — `_create_session()` committed shared session, making subsequent `update(User)` fail; reordered operations (`8f9de14`)
- **`BACKEND_CORS_ORIGINS` JSON parsing** — pydantic-settings list field needed JSON array format; added validator for both comma-separated and JSON formats
- **TrustedHostMiddleware blocking Railway health checks** — added wildcard to `allowed_hosts` (`8b7d1e3`)
- **`search_path` asyncpg parameter** — removed `?options=-csearch_path` (not supported by asyncpg); used `server_settings` instead then removed when not needed
- **`transaction_per_migration=True` conflicting with `begin_transaction()`** — removed; caused nested transaction conflict

### Security
- JWT access tokens stored in-memory only (never localStorage)
- Refresh tokens stored as HttpOnly cookies (XSS-resistant)
- Refresh tokens hashed in database (bcrypt)
- `TrustedHostMiddleware` for host header validation
- CORS restricted to `orbitiq-x.vercel.app`
- Rate limiting: 100 req/min per client
- All auth events logged to `audit_logs` table
- `STRICT-TRANSPORT-SECURITY` header in production
- `Content-Security-Policy: default-src 'none'` for API responses

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
