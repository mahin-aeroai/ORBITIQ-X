# ORBITIQ-X — Engineering Roadmap

---

## Version History

| Version | Description | Date |
|---|---|---|
| `v0.1.0` | Initial production deployment — full backend + frontend live | 2026-06-26 |

---

## Completed Phases

### Phase 1–3: Foundation
- Core FastAPI application factory with lifespan management
- PostgreSQL schema — users, sessions, satellites, TLE records, missions, events
- JWT authentication — register, login, refresh, logout, RBAC
- Alembic migration chain (10 migrations)

### Phase 4–6: SSA Core
- Space-Track TLE ingestion with APScheduler (2h incremental, 6h full sync)
- SGP4 propagation via `sgp4` library
- RSO catalog with orbital regime classification (LEO/MEO/GEO/HEO/SSO/VLEO)
- Conjunction event detection and CDM generation

### Phase 7–8: Digital Twin
- Real-time orbital state propagation for all catalog objects
- Trajectory forecasting with uncertainty bounds
- Maneuver simulation and delta-V computation
- Orbital regime health monitoring

### Phase 9–10: Knowledge Graph + RAG
- Neo4j graph — operator profiles, country intelligence, constellation topology
- Weaviate vector store — aerospace knowledge embeddings
- LangChain RAG pipeline — query, explain, research endpoints
- GraphRAG fusion — graph + vector retrieval

### Phase 11–12: AI Agents
- LangGraph multi-agent orchestration
- Claude-powered conjunction analysis agent
- Maneuver planning agent
- Anomaly detection agent
- Agent task queue and status tracking

### Phase 13A–C: Mission Control Frontend
- Next.js 14 App Router application
- Cesium.js 3D orbital globe (50K+ objects via GPU instancing)
- Real-time SSE conjunction alert streaming
- Space weather widget (NOAA integration)

### Phase 13D–14: Dashboard Completion
- TanStack Query data fetching layer
- Ground track and trajectory playback
- KnowledgeGraphExplorer with vis-network
- Mission status cards and agent activity feed
- DashboardMetricsBar with conjunction statistics

### Phase 14D: Release Readiness Audit
- 8 critical findings identified and resolved
- FastAPI deprecation warnings eliminated
- Authentication bypass patched
- Startup-blocking defects fixed

### Phase 15A: Production Deployment
- Railway backend — Docker builder, Nixpacks glibc/greenlet issues resolved
- Vercel frontend — Next.js build pipeline, auth middleware
- Full auth flow: register → login → JWT → refresh → logout
- All SQLAlchemy model relationships fixed
- Alembic AUTOCOMMIT isolation level fix

---

## Current Phase

### Phase 15B: Operational Configuration *(In Progress)*

**Objective:** Activate all platform capabilities with real data.

**Deliverables:**
- [ ] Space-Track catalog sync producing TLE data
- [ ] Digital Twin propagating orbital states for all tracked objects
- [ ] Conjunction engine producing real CDM events
- [ ] Redis pub/sub operational for SSE alerts
- [ ] Dashboard showing live tracked objects, conjunctions, space weather

**Exit Criteria:**
- Dashboard shows >1000 tracked objects
- At least one conjunction event detected and displayed
- System Status shows all core services HEALTHY

---

## Planned Phases

### Phase 16: Operational AI Mission Intelligence
**Objectives:**
- Activate Claude agents with real satellite data
- Conjunction analysis agent producing actionable insights
- Maneuver recommendation agent with delta-V calculations
- Natural language query interface for operators

**Deliverables:**
- Agents page with live task queue and results
- Real conjunction alerts triggering agent analysis
- Maneuver simulation API integrated with agents

**Exit Criteria:**
- At least one end-to-end agent workflow: conjunction detected → agent analyzes → recommendation produced

---

### Phase 17: Predictive Orbital Analytics
**Objectives:**
- Long-horizon conjunction prediction (7-day lookahead)
- Orbital decay modeling for LEO objects
- Space weather impact on drag and decay rates
- Historical conjunction trend analysis

**Deliverables:**
- Predictive conjunction dashboard
- Decay timeline visualization
- Space weather correlation reports

---

### Phase 18: Autonomous Maneuver Recommendations
**Objectives:**
- Automated maneuver planning for collision avoidance
- Multi-constraint optimization (fuel, time, collision probability)
- Operator approval workflow with audit trail
- Post-maneuver verification

**Deliverables:**
- Maneuver recommendation engine
- Approval workflow UI
- Maneuver audit log

---

### Phase 19: Aerospace Foundation Model
**Objectives:**
- Fine-tuned LLM on aerospace domain data
- Satellite behavior prediction model
- Anomaly detection via learned orbital baselines
- Knowledge distillation from operational data

**Deliverables:**
- Foundation model training pipeline
- Benchmark suite (orbital prediction accuracy)
- Model registry and versioning

---

### Phase 20: Enterprise Multi-User Operations
**Objectives:**
- Multi-tenant architecture with organization isolation
- Role-based access control for satellite operators
- API key management for programmatic access
- SLA monitoring and alerting

**Deliverables:**
- Organization management UI
- API key portal
- Usage dashboards and billing hooks
