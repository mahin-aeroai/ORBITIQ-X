# 🛰️ ORBITIQ-X — The Aerospace Intelligence Platform

<div align="center">

**Production-grade Aerospace Knowledge Universe combining Space Situational Awareness,
Orbital Mechanics, Knowledge Graphs, GraphRAG, Multi-Agent AI, and the
Canonical Aerospace Entity Model.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![Railway](https://img.shields.io/badge/deployed-Railway-purple.svg)](https://railway.app)
[![Version](https://img.shields.io/badge/version-v0.4.0-brightgreen.svg)](CHANGELOG.md)

**[Live Platform](https://orbitiq-x.vercel.app) · [API Docs](https://orbitiq-x-production.up.railway.app/api/v1/docs) · [Portfolio](https://mahin-nandipa.netlify.app)**

</div>

---

## Vision

ORBITIQ-X is evolving into the **"Bloomberg Terminal for Aerospace"** — a platform where users can begin from any aerospace entity (country, agency, company, mission, satellite, launch vehicle, technology, scientist, patent, standard) and seamlessly navigate through technical, operational, scientific, historical, commercial, and organizational relationships.

It is not a satellite tracker. It is not an SSA application. It is an **Aerospace Knowledge Universe (AKU)** built around an enterprise-grade Aerospace Knowledge Graph.

---

## Platform Metrics (v0.4.0)

| Metric | Value |
|---|---|
| Satellites tracked | 29,198 |
| Neo4j nodes | 29,248 |
| Knowledge graph relationships | 118,681 |
| GraphRAG corpus chunks | 185 |
| GraphRAG benchmark | 20/20 (100%) |
| API endpoints | 112 |
| CAEM entity classes | 39 |
| CAEM relationship types | 76 |
| Alembic migrations | 11 |

---

## Core Capabilities

| Capability | Description |
|---|---|
| **Space Situational Awareness** | Real-time RSO catalog (29,198 objects), orbital regime classification, conjunction screening |
| **Digital Twin** | SGP4 propagation, trajectory forecasting, maneuver simulation, delta-V computation |
| **Conjunction Analysis** | CDM generation, probability-of-collision, miss distance computation |
| **Aerospace Knowledge Graph** | Neo4j graph with 29,248 nodes and 118,681 relationships across operators, satellites, countries, constellations |
| **GraphRAG** | `full_graphrag` mode — Neo4j traversal + Qdrant semantic retrieval + Claude synthesis |
| **AI Agents** | LangGraph multi-agent system (7 agents) powered by Claude claude-sonnet-4-6 |
| **Foundation Model** | 3-tier aerospace intelligence: baseline / graphrag / agent, 17 benchmark tasks |
| **CAEM** | Canonical Aerospace Entity Model — universal knowledge architecture for 39+ entity types |
| **Knowledge Ingestion** | 7-stage pipeline with contradiction resolution, provenance tracking, auto-publish |
| **Mission Control** | Next.js dashboard with animated globe, live metrics, space weather, conjunction alerts |

---

## Technology Stack

### Backend
- **FastAPI 0.115** — async REST API, 112 endpoints
- **PostgreSQL 18** — primary data store (Railway), 11 Alembic migrations
- **SQLAlchemy 2.x async** — ORM with asyncpg driver
- **Gunicorn + Uvicorn** — production WSGI/ASGI serving

### AI / Knowledge
- **LangGraph** — multi-agent orchestration (7 specialist agents)
- **Anthropic Claude** — claude-sonnet-4-6, reasoning engine
- **Neo4j Aura** — Aerospace Knowledge Graph (29,248 nodes, 118,681 relationships)
- **Qdrant Cloud** — vector store for GraphRAG (`aerospace_docs` collection)
- **CAEM** — Canonical Aerospace Entity Model (39 entity classes, 76 relationship types)

### Data Infrastructure
- **Space-Track.org** — real-time TLE catalog (29,198 satellites)
- **sgp4** — orbital mechanics propagation
- **Redis** — pub/sub for SSE conjunction alerts (non-critical)
- **APScheduler** — 5-job scheduler (TLE refresh, catalog sync, conjunction screening)

### Observability
- **structlog** — structured JSON logging
- **Prometheus** — metrics collection
- **OpenTelemetry** — distributed tracing
- **Sentry** — error tracking

### Frontend
- **Next.js 14** — App Router, server components
- **React 18** + **TypeScript** — full type safety
- **TanStack Query** — data fetching and caching
- **Tailwind CSS** — deep navy / electric indigo aesthetic

### Deployment
- **Docker** (`Dockerfile.railway`) — containerized backend
- **Railway** — backend + PostgreSQL hosting
- **Vercel** — frontend with edge middleware

---

## Repository Structure

```
ORBITIQ-X/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/     # 112 API endpoints
│   │   ├── caem/                 # ★ Canonical Aerospace Entity Model (Phase 17.1)
│   │   │   ├── base.py           #   BaseAerospaceEntity, AQID, ProvenanceRecord
│   │   │   ├── entities.py       #   31 typed extension schemas
│   │   │   ├── relationships.py  #   76 relationship types + Cypher builder
│   │   │   ├── graph/            #   Neo4j schema initializer + batch upsert
│   │   │   └── ingestion/        #   7-stage ingestion pipeline
│   │   ├── core/                 # config, security, logging, tracing
│   │   ├── db/                   # SQLAlchemy models, session, repositories
│   │   ├── graph/                # Neo4j connection and query layer
│   │   ├── services/             # catalog_scheduler, agent_service, space_weather
│   │   └── main.py               # FastAPI app factory + lifespan
│   ├── alembic/versions/         # 11 database migrations
│   ├── requirements/base.txt     # production dependencies
│   ├── Dockerfile.railway        # production Docker image
│   ├── entrypoint.sh             # Railway startup script
│   └── migrate.py                # Alembic CLI wrapper
├── frontend/
│   ├── src/
│   │   ├── app/                  # Next.js App Router pages
│   │   ├── components/           # React components
│   │   └── lib/                  # API client, auth utilities
│   └── vercel.json               # Vercel deployment config
├── agents/                       # LangGraph agent definitions
├── rag/                          # GraphRAG pipeline (Qdrant + Neo4j)
├── orbital-engine/               # SGP4 propagation utilities
├── knowledge-graph/              # Neo4j population scripts
├── docs/                         # Architecture docs, ADRs, operations
├── railway.toml                  # Railway deployment config
├── README.md
├── PROJECT_STATUS.md
├── ROADMAP.md
├── CHANGELOG.md
└── CLAUDE.md
```

---

## CAEM — Canonical Aerospace Entity Model

Phase 17.1 introduced the foundational knowledge architecture for the Aerospace Knowledge Universe.

```
BaseAerospaceEntity
├── Identity Block      — AQID, display_name, aliases, native_name
├── Metadata Block      — lifecycle_status, schema_version, completeness
├── Taxonomy Block      — tags, domains, regions, time_periods
├── Timeline Block      — timeline_events with date precision
├── Relationship Block  — parent_aqid, related_aqids (Neo4j authoritative)
├── Knowledge Block     — qdrant_chunk_ids, document_refs
├── AI Intelligence     — executive_summary, key_facts, refresh_flag
├── Provenance Block    — ProvenanceRecord, confidence_score, verification_status
├── Audit Block         — change_log, ingest_pipeline, ingest_job_id
├── Version Block       — current_version, version_history
└── Extension Block     — entity-class-specific JSONB fields
```

Every entity receives an immutable **AQID**: `AQID-{CLASS}-{SLUG}`

```
AQID-COUNTRY-USA
AQID-COMPANY-SPACEX
AQID-SATELLITE-STARLINK-1024
AQID-MISSION-ARTEMIS-II
AQID-STANDARD-CCSDS-727-0-B-5
AQID-PATENT-US10392874
```

Every entity exists simultaneously across four layers:

| Layer | System | Purpose |
|---|---|---|
| Master Data | PostgreSQL | Structured facts, audit trail, full entity record |
| Relationships | Neo4j | Graph traversal, multi-hop intelligence, lineage |
| Knowledge | Qdrant | Semantic retrieval, document chunks, embeddings |
| Intelligence | Frontend | Interactive entity pages, AI summaries, graph explorer |

---

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 14+

### Backend Setup

```bash
cd backend
pip install -r requirements/base.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run migrations (includes Phase 17.1 CAEM tables)
python migrate.py upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

---

## Deployment

**Backend** — deployed on Railway via Docker:
- Auto-deploys on push to `main`
- Migrations run automatically in `entrypoint.sh`
- PostgreSQL provisioned as Railway plugin

**Frontend** — deployed on Vercel:
- Auto-deploys on push to `main`
- Edge middleware handles auth routing

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for current deployment status.

---

## Documentation

| Document | Purpose |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Current engineering status, metrics, deployment health |
| [ROADMAP.md](ROADMAP.md) | Phase history and Knowledge Engineering roadmap |
| [CHANGELOG.md](CHANGELOG.md) | Detailed change history per version |
| [CLAUDE.md](CLAUDE.md) | AI assistant working instructions and known pitfalls |

---

## Author

**Mahin Nandipa** — Aerospace × AI/ML Engineer
B.Tech Aerospace Engineering (VIT Bhopal) · PG Certificate AI/ML (IIIT Hyderabad × Accenture)
[Portfolio](https://mahin-nandipa.netlify.app) · [GitHub](https://github.com/mahin-aeroai)
