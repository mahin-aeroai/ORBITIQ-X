# CLAUDE.md — ORBITIQ-X Working Instructions

This document is the authoritative onboarding reference for AI assistants working on ORBITIQ-X.
Read this before making any changes. Update this file when the engineering focus shifts.

---

## Project Overview

ORBITIQ-X is a private full-stack aerospace intelligence platform.

**Architecture:**
- **Backend:** FastAPI + PostgreSQL (Railway) + Redis + APScheduler
- **Frontend:** Next.js 14 (Vercel) with App Router
- **AI:** LangGraph agents + Claude claude-sonnet-4-6 + RAG pipeline
- **Orbital:** sgp4 propagation, Space-Track TLE ingestion, conjunction CDM screening
- **Graph:** Neo4j knowledge graph (operator/satellite/country relationships)

**Repository:** `mahin-aeroai/ORBITIQ-X`  
**Backend:** https://orbitiq-x-production.up.railway.app  
**Frontend:** https://orbitiq-x.vercel.app  
**API Docs:** https://orbitiq-x-production.up.railway.app/api/v1/docs

---

## Engineering Principles

1. **Evidence-based debugging only.** Never guess. Read logs, run tests, check the actual error before proposing a fix.
2. **No speculative fixes.** If the root cause is not confirmed, say so. Do not apply changes hoping they might work.
3. **Minimal targeted changes.** Fix the specific failure. Do not refactor surrounding code.
4. **Preserve existing architecture.** The database schema, API contracts, and middleware stack are stable. Do not restructure unless a verified defect requires it.
5. **Production quality.** Every commit must work in production, not just locally.
6. **Verify before declaring success.** Run tests, check logs, confirm the fix resolves the reported issue.

---

## Coding Standards

- **Python:** Type hints everywhere, Pydantic v2, async-first, SQLAlchemy 2.x patterns
- **Logging:** structlog with structured JSON fields — never use `print()` in production code
- **Database:** SQLAlchemy async session via `get_session` dependency, Alembic for all schema changes
- **Migrations:** Every schema change needs a numbered migration in `backend/alembic/versions/`
- **API:** FastAPI with Pydantic request/response models, `JSONResponse` (not `ORJSONResponse` — deprecated)
- **Frontend:** TypeScript strict mode, Next.js App Router patterns, TanStack Query for data fetching
- **Relationships:** Do NOT use string `primaryjoin` references across models — causes `InvalidRequestError` at mapper config time

---

## Current Phase

**Phase 15B — Operational Configuration**

Platform is live. Configuring external integrations to activate full capabilities.

## Current Priority

**Space-Track catalog sync** → first satellite data → Digital Twin activation → conjunction screening live

---

## Known Issues (Verified)

| Issue | Root Cause | Status |
|---|---|---|
| Redis UNAVAILABLE | `REDIS_URL` not injecting correctly from Railway plugin | Open |
| Neo4j UNAVAILABLE | Credentials not configured | Open — needs Aura account |
| Digital Twin NOT INIT | No satellites in catalog (Space-Track not synced yet) | Resolves with catalog sync |
| Unit test failures (68) | Test environment mock configuration, not production bugs | Low priority |

---

## Completed Milestones

- **Phases 1–12:** Full backend — auth, SSA, digital twin, conjunction, missions, knowledge graph, RAG, agents
- **Phases 13–14:** Full Next.js frontend — Mission Control dashboard, Cesium globe, SSE alerts
- **Phase 14D:** Release readiness audit — 8 findings resolved, 557 tests passing
- **Phase 15A:** Production deployment — Railway backend, Vercel frontend, full auth flow working

---

## Deployment

**Backend (Railway):**
- Builder: Dockerfile (`backend/Dockerfile.railway`)
- Entrypoint: `backend/entrypoint.sh` — parses `DATABASE_URL`, runs Alembic, starts gunicorn
- Key vars: `DATABASE_URL`, `REDIS_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ORBITIQ_SECRET_KEY`

**Frontend (Vercel):**
- Framework: Next.js 14
- Key var: `NEXT_PUBLIC_API_URL=https://orbitiq-x-production.up.railway.app` (WITHOUT `/api/v1` suffix)
- Auth: HttpOnly cookie (`orbitiq_refresh`) + in-memory access token

**Database:**
- Migrations use `AUTOCOMMIT` isolation level (required — default SQLAlchemy transaction wrapping causes silent rollback on Railway PostgreSQL 18)
- Always run `python migrate.py upgrade head` before starting the server

---

## Testing Policy

1. Run `python -m pytest backend/tests/unit/ --asyncio-mode=auto -q` before any backend commit
2. Run `npm run build` in `frontend/` before any frontend commit — TypeScript errors fail the Vercel build
3. Never claim a fix works without log evidence or test output
4. Integration tests require live DB — use Railway Console for production verification

---

## Commit Policy

Every commit must include:
- **Purpose:** What problem this solves
- **Files changed:** Which files were modified and why
- **Validation:** What test or log confirms the fix works

Example:
```
fix: use COUNT(*) for first-user check instead of fetching all users

COUNT(*) is O(1) on indexed table. Previous implementation fetched all
rows into memory causing timeout on large datasets.

Files: backend/app/api/v1/endpoints/auth.py
Validated: POST /api/v1/auth/register returns 201 in Railway deploy logs
```

---

## Do Not

- Introduce `Math.random()` or non-deterministic values in Next.js server components (causes hydration mismatch)
- Use `ORJSONResponse` — deprecated in FastAPI 0.115+, use `JSONResponse`
- Use string `primaryjoin` in SQLAlchemy relationships without importing all referenced classes
- Wrap Alembic migrations in `context.begin_transaction()` — causes silent DDL rollback on PostgreSQL
- Set `search_path` via asyncpg URL query params — not supported by asyncpg driver
- Import React class `Component` in Next.js server components (`"use server"` or no directive)
- Use `bcrypt>=4.0.0` with `passlib==1.7.4` — incompatible, pin `bcrypt<4.0.0`
- Hardcode `parents[4]` path traversal — breaks in Docker where directory depth differs from local dev
