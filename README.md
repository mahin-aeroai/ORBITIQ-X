# 🛰️ ORBITIQ-X — Aerospace Foundation Model for Space Intelligence

<div align="center">

![ORBITIQ-X Banner](docs/architecture/banner.svg)

**Production-grade AI platform unifying Space Situational Awareness, Orbital Mechanics,
Satellite Catalog Intelligence, Knowledge Graphs, RAG, and Multi-Agent Reasoning.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://python.org)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-000000?logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docker.com)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://black.readthedocs.io)

</div>

---

## 🌌 Mission Statement

ORBITIQ-X is an **Aerospace Foundation Model** purpose-built for Space Intelligence operations.
It integrates real-time orbital propagation, conjunction risk assessment, satellite catalog
reasoning, retrieval-augmented generation over aerospace knowledge bases, and autonomous
multi-agent mission planning — all exposed through a unified API and a professional-grade
mission control interface.

This platform is designed for:
- **Space Agencies** requiring operational SSA tooling
- **Commercial Satellite Operators** managing constellation health
- **Defense/Intelligence Communities** tracking objects of interest
- **Academic Researchers** needing reproducible orbital mechanics pipelines
- **Aerospace Engineers** building next-generation mission planning systems

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ORBITIQ-X PLATFORM                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              MISSION CONTROL FRONTEND (Next.js 14)           │    │
│  │   3D Globe · TLE Visualizer · SSA Dashboard · Agent Console  │    │
│  └──────────────────────┬──────────────────────────────────────┘    │
│                          │ REST / WebSocket                           │
│  ┌───────────────────────▼──────────────────────────────────────┐   │
│  │                  API GATEWAY (FastAPI)                         │   │
│  │          Auth · Rate-Limit · Versioning · OpenAPI             │   │
│  └──┬──────────────┬──────────────┬──────────────┬─────────────┘   │
│     │              │              │              │                    │
│  ┌──▼───┐  ┌───────▼──┐  ┌───────▼──┐  ┌───────▼──┐              │
│  │Orbit │  │Knowledge  │  │   RAG    │  │  Agent   │              │
│  │Engine│  │  Graph   │  │ Pipeline │  │Orchestrat│              │
│  │(SGP4+│  │(Neo4j +  │  │(FAISS +  │  │(LangGraph│              │
│  │ J2)  │  │ RDF/OWL) │  │Llama-3)  │  │+ Claude) │              │
│  └──┬───┘  └───────┬──┘  └───────┬──┘  └───────┬──┘              │
│     │              │              │              │                    │
│  ┌──▼──────────────▼──────────────▼──────────────▼─────────────┐   │
│  │                      DATA LAYER                               │   │
│  │  PostgreSQL · Redis · Neo4j · MinIO · InfluxDB · Weaviate    │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```
ORBITIQ-X/
├── frontend/              # Next.js 14 Mission Control Interface
│   └── src/
│       ├── app/           # App Router pages & layouts
│       ├── components/    # Domain-segregated React components
│       │   ├── ui/        # Design system primitives
│       │   ├── orbital/   # 3D globe, TLE visualizer, pass predictor
│       │   ├── ssa/       # Conjunction alerts, RSO catalog, debris map
│       │   ├── knowledge/ # Knowledge graph explorer, entity cards
│       │   ├── agents/    # Agent console, reasoning trace viewer
│       │   └── mission/   # Mission planner, maneuver wizard
│       ├── hooks/         # Data-fetching & domain logic hooks
│       ├── lib/           # API client, utility functions
│       └── types/         # TypeScript type definitions
│
├── backend/               # FastAPI application server
│   └── app/
│       ├── api/v1/        # Versioned REST endpoints
│       │   └── endpoints/ # satellite, conjunction, ssa, rag, agents, mission
│       ├── core/          # Config, security, logging, middleware
│       ├── models/        # SQLAlchemy ORM models
│       ├── schemas/       # Pydantic request/response schemas
│       ├── services/      # Business logic layer
│       ├── db/            # Database session, migrations (Alembic)
│       └── utils/         # Shared utilities
│
├── orbital-engine/        # High-fidelity orbital mechanics library
│   └── src/
│       ├── propagator/    # SGP4, J2-perturbed, numerical integrators
│       ├── conjunction/   # CDM generation, Pc computation (Foster, Monte Carlo)
│       ├── maneuver/      # Delta-V optimizer, burn planning, Hohmann
│       ├── catalog/       # RSO catalog ingestion, NORAD ID resolution
│       └── coverage/      # Ground station visibility, access windows
│
├── knowledge-graph/       # Aerospace ontology & graph intelligence
│   └── src/
│       ├── schema/        # OWL ontology, RDF schema, SPARQL queries
│       ├── ingestion/     # Catalog, mission, operator data loaders
│       ├── query/         # Cypher/SPARQL query builders
│       └── reasoning/     # Inference rules, relationship extraction
│
├── rag/                   # Retrieval-Augmented Generation pipeline
│   └── src/
│       ├── indexer/       # Document chunking, embedding, FAISS/Weaviate index
│       ├── retriever/     # Hybrid search (dense + sparse + metadata filter)
│       ├── generator/     # Prompt templates, LLM chain, answer synthesis
│       └── evaluation/    # RAGAs metrics, faithfulness, relevance scoring
│
├── agents/                # Multi-agent reasoning system
│   └── src/
│       ├── orchestrator/  # LangGraph supervisor, task routing
│       ├── ssa_agent/     # RSO tracking, conjunction monitoring agent
│       ├── mission_agent/ # Mission planning & optimization agent
│       ├── catalog_agent/ # Satellite catalog query & enrichment agent
│       ├── knowledge_agent/ # Knowledge graph traversal agent
│       └── comms/         # Inter-agent message bus (Redis Streams)
│
├── datasets/              # Aerospace reference datasets
│   ├── catalogs/          # Satellite catalog snapshots (JSON, CSV)
│   ├── tle/               # TLE archives by epoch
│   ├── space_weather/     # Kp-index, F10.7, solar flux time series
│   ├── missions/          # Mission profiles (ISS, Starlink, NavIC, DRDO)
│   └── schemas/           # Dataset JSON schemas & data dictionaries
│
├── docs/                  # Technical documentation
│   ├── architecture/      # System design docs, C4 diagrams
│   ├── api/               # API reference (auto-generated + curated)
│   ├── user-guide/        # Operator handbook
│   ├── research/          # Algorithm derivations, white papers
│   └── adr/               # Architecture Decision Records
│
└── deployment/            # Infrastructure & DevOps
    ├── docker/            # Per-service Dockerfiles
    ├── k8s/               # Kubernetes manifests (Helm-ready)
    ├── terraform/         # IaC for AWS/GCP/Azure
    ├── scripts/           # Bootstrap, seed, health-check scripts
    └── monitoring/        # Prometheus rules, Grafana dashboards
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker Desktop | 24+ | Container runtime |
| Docker Compose | 2.24+ | Local orchestration |
| Node.js | 20 LTS | Frontend build |
| Python | 3.11+ | Backend & engine |
| Git | 2.40+ | Version control |

### 1. Clone & Configure

```bash
git clone https://github.com/mahin-aeroai/ORBITIQ-X.git
cd ORBITIQ-X

# Copy environment templates
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local

# Edit secrets (see ENVIRONMENT VARIABLES section)
nano .env
```

### 2. Launch Development Stack

```bash
# Start all services (first run pulls ~3GB images)
docker compose -f deployment/docker/docker-compose.dev.yml up -d

# Verify all services are healthy
./deployment/scripts/health-check.sh

# Seed reference datasets
./deployment/scripts/seed-datasets.sh
```

### 3. Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Mission Control UI | http://localhost:3000 | — |
| API Gateway | http://localhost:8000 | — |
| API Docs (Swagger) | http://localhost:8000/docs | — |
| API Docs (ReDoc) | http://localhost:8000/redoc | — |
| Neo4j Browser | http://localhost:7474 | neo4j / orbitiq-dev |
| Weaviate Console | http://localhost:8080 | — |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Grafana | http://localhost:3001 | admin / orbitiq-dev |
| Prometheus | http://localhost:9090 | — |

---

## 🔧 Development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Orbital Engine

```bash
cd orbital-engine
pip install -e ".[dev]"
pytest tests/ -v --benchmark-skip
```

### Running the Agent Orchestrator

```bash
cd agents
python -m src.orchestrator.main --mode development
```

---

## 🧪 Testing Strategy

```
Unit Tests      → pytest (orbital-engine, rag, agents)
Integration     → pytest + Docker services (backend API)
E2E             → Playwright (frontend mission flows)
Performance     → pytest-benchmark (propagator throughput)
RAG Evaluation  → RAGAs framework (retrieval quality)
```

```bash
# Run full test suite
./deployment/scripts/run-tests.sh

# Unit tests only
pytest orbital-engine/tests/ rag/tests/ agents/tests/ -v

# Backend integration tests
pytest backend/tests/ --integration -v
```

---

## 📡 Core Capabilities

### 1. Orbital Propagation Engine
- **SGP4/SDP4** two-line element propagation (AFSPC standard)
- **J2-perturbed** analytical orbit model for LEO precision
- **Cowell's method** numerical integration for high-fidelity propagation
- Batch propagation: >10,000 objects in <500ms

### 2. Space Situational Awareness
- **Conjunction Data Message (CDM)** generation per CCSDS 508.0-B-1
- **Probability of Collision** (Pc) via Foster method & Monte Carlo
- Real-time **RSO catalog** tracking against Space-Track.org
- **Space Weather** correlation (Kp, F10.7 → atmospheric density)

### 3. Knowledge Graph Engine
- **Aerospace Ontology** (OWL 2) covering: satellites, operators,
  orbits, maneuvers, payloads, launch vehicles, ground stations
- Neo4j property graph with ~1M+ entity relationships
- SPARQL + Cypher dual-query interface
- Automated **entity extraction** from COSPAR, NORAD, UCS catalogs

### 4. RAG Pipeline
- Corpus: CCSDS standards, FAA AST documents, ESA technical notes,
  NASA SPD-41, USSF SSA reports, aerospace white papers
- Hybrid retrieval: dense (text-embedding-3-large) + BM25
- **Cross-encoder reranking** for precision
- Faithfulness-scored answer generation

### 5. Multi-Agent System
- **SSA Agent**: monitors conjunction alerts, flags high-Pc events
- **Mission Agent**: trajectory design, maneuver optimization
- **Catalog Agent**: RSO identification, orbit determination queries
- **Knowledge Agent**: ontology reasoning, cross-entity inference
- **Orchestrator**: LangGraph supervisor with tool-call routing

---

## 🛣️ Development Roadmap

See [`docs/architecture/ROADMAP.md`](docs/architecture/ROADMAP.md) for the full phased roadmap.

| Phase | Milestone | Target |
|-------|-----------|--------|
| **P0** | Foundation & DevOps scaffolding | Month 1 |
| **P1** | Orbital Engine + SSA API | Month 2 |
| **P2** | Knowledge Graph + Ingestion | Month 3 |
| **P3** | RAG Pipeline + Evaluation | Month 4 |
| **P4** | Multi-Agent System | Month 5 |
| **P5** | Mission Control UI (full) | Month 6 |
| **P6** | Production Hardening + K8s | Month 7 |
| **P7** | External Integrations (Space-Track, CelesTrak) | Month 8 |

---

## 🤝 Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development workflow,
coding standards, and ADR process.

---

## 📜 License

MIT License — see [`LICENSE`](LICENSE) for details.

---

## 👤 Author

**Mahin Nandipa** — AI/ML Engineer · Aerospace Systems
- GitHub: [@mahin-aeroai](https://github.com/mahin-aeroai)
- Portfolio: [mahin-nandipa.netlify.app](https://mahin-nandipa.netlify.app)

---

<div align="center">
<sub>Built with precision for the space domain. ORBITIQ-X is open-source infrastructure for the next generation of space intelligence systems.</sub>
</div>
