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
