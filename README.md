# 🛰️ ORBITIQ-X — Aerospace Foundation Model for Space Intelligence

<div align="center">

**Production-grade AI platform unifying Space Situational Awareness, Orbital Mechanics,
Satellite Catalog Intelligence, Knowledge Graphs, RAG, and Multi-Agent Reasoning.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![Railway](https://img.shields.io/badge/deployed-Railway-purple.svg)](https://railway.app)

**[Live Platform](https://orbitiq-x.vercel.app) · [API Docs](https://orbitiq-x-production.up.railway.app/api/v1/docs) · [Portfolio](https://mahin-nandipa.netlify.app)**

</div>

---

## Project Overview

ORBITIQ-X is a private full-stack aerospace intelligence platform built to demonstrate production-grade AI/ML engineering at the intersection of orbital mechanics and autonomous systems. It ingests real-time satellite catalog data from Space-Track.org, propagates orbital states using SGP4, screens for conjunction events, and exposes every capability through a FastAPI backend and a Next.js Mission Control dashboard.

The platform is designed as a proof-of-concept Aerospace Foundation Model — combining domain-specific knowledge (TLE propagation, CDM screening, orbital regime classification) with modern AI (LangGraph agents, RAG pipelines, Claude-powered reasoning).

---

## Core Capabilities

| Capability | Description |
|---|---|
| **Space Situational Awareness (SSA)** | Real-time RSO catalog, orbital regime classification, conjunction screening |
| **Digital Twin** | SGP4 propagation, trajectory forecasting, maneuver simulation |
| **Conjunction Analysis** | CDM generation, probability of collision, miss distance computation |
| **Mission Intelligence** | Mission planning, status tracking, maneuver approval workflows |
| **Knowledge Graph** | Neo4j operator profiles, constellation topology, country intelligence |
| **GraphRAG** | Aerospace knowledge retrieval, entity resolution, mission intelligence |
| **AI Agents** | LangGraph multi-agent system powered by Claude — analysis, planning, anomaly detection |
| **Mission Control** | Next.js dashboard with live metrics, space weather, conjunction alerts |
| **Foundation Models** | Model benchmarking, RAG pipeline management, LoRA fine-tuning control |

---

## Technology Stack

### Backend
- **FastAPI 0.115** — async REST API, 103 endpoints across 12 routers
- **PostgreSQL 18** — primary data store via Railway
- **SQLAlchemy 2.x async** — ORM with asyncpg driver
- **Alembic** — 10-migration schema evolution chain
- **Gunicorn + Uvicorn** — production WSGI/ASGI serving

### AI / ML
- **LangChain + LangGraph** — multi-agent orchestration
- **Anthropic Claude** — reasoning engine for agents
- **OpenAI** — embeddings
- **Weaviate** — vector store for RAG
- **sgp4** — orbital mechanics propagation

### Data Infrastructure
- **Redis** — pub/sub for SSE conjunction alerts, session caching
- **Neo4j** — knowledge graph (operator/satellite/country relationships)
- **MinIO** — object storage for CDM files and TLE archives
- **APScheduler** — 5-job scheduler (TLE refresh, catalog sync, conjunction screening)

### Observability
- **structlog** — structured JSON logging
- **Prometheus** — metrics collection
- **OpenTelemetry** — distributed tracing
- **Sentry** — error tracking

### Frontend
- **Next.js 14** — App Router, server components, ISR
- **React 18** — client-side interactivity
- **TypeScript** — full type safety
- **TanStack Query** — data fetching and caching
- **Tailwind CSS** — utility-first styling

### Deployment
- **Docker** (Dockerfile.railway) — containerized backend
- **Railway** — backend + PostgreSQL + Redis hosting
- **Vercel** — frontend hosting with edge middleware

---

## Repository Structure

```
ORBITIQ-X/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/     # 103 API endpoints (auth, ssa, catalog, agents...)
│   │   ├── core/                 # config, security, logging, tracing
│   │   ├── db/                   # SQLAlchemy models, session, repositories
│   │   ├── services/             # catalog_scheduler, agent_service, space_weather...
│   │   └── main.py               # FastAPI app factory + lifespan
│   ├── alembic/                  # 10 database migrations
│   ├── requirements/base.txt     # production dependencies
│   ├── Dockerfile.railway        # production Docker image
│   ├── entrypoint.sh             # Railway startup script
│   └── migrate.py                # Alembic CLI wrapper
├── frontend/
│   ├── src/
│   │   ├── app/                  # Next.js App Router pages
│   │   ├── components/           # React components (orbital, ssa, agents...)
│   │   └── lib/                  # API client, auth utilities
│   └── vercel.json               # Vercel deployment config
├── agents/                       # LangGraph agent definitions
├── orbital-engine/               # SGP4 propagation utilities
├── deployment/                   # Phase 15A deployment toolkit
├── railway.toml                  # Railway deployment config
├── README.md
├── PROJECT_STATUS.md
├── ROADMAP.md
├── CHANGELOG.md
└── CLAUDE.md
```

---

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 14+
- Redis 7+

### Backend Setup

```bash
cd backend
pip install -r requirements/base.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run migrations
python migrate.py upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install

# Configure environment
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start development server
npm run dev
```

---

## Deployment

**Backend** — deployed on Railway via Docker:
- Auto-deploys on push to `main`
- Migrations run automatically in `entrypoint.sh`
- PostgreSQL and Redis provisioned as Railway plugins

**Frontend** — deployed on Vercel:
- Auto-deploys on push to `main`
- Edge middleware handles auth routing
- `NEXT_PUBLIC_API_URL` points to Railway backend

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for current deployment status.

---

## Documentation

| Document | Purpose |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Current engineering status and deployment health |
| [ROADMAP.md](ROADMAP.md) | Phase history and future milestones |
| [CHANGELOG.md](CHANGELOG.md) | Detailed change history |
| [CLAUDE.md](CLAUDE.md) | AI assistant working instructions |

---

## Author

**Mahin Nandipa** — Aerospace × AI/ML Engineer  
B.Tech Aerospace Engineering (VIT Bhopal) · PG Certificate AI/ML (IIIT Hyderabad × Accenture)  
[Portfolio](https://mahin-nandipa.netlify.app) · [GitHub](https://github.com/mahin-aeroai)
