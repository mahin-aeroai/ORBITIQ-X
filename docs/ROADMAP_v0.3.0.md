# ORBITIQ-X v0.3.0 — Roadmap

**Current baseline:** v0.2.0 (2026-06-27)  
**Target:** v0.3.0  
**Focus:** Operational stability, knowledge enrichment, observability, quality

---

## Priority 1 — Redis Activation

Redis is configured and the fix is deployed (`5287e5a`). Requires Railway redeploy.

**Unlocks:**
- SSE real-time conjunction alerts to frontend
- Agent event streaming via `GET /agents/task/{id}/stream`
- Scheduler distributed locking without Redis fallback
- Digital Twin state caching and pub/sub

**Effort:** Railway redeploy + smoke test (30 minutes)

---

## Priority 2 — Digital Twin Population

After Redis is healthy, trigger a full catalog sync:

```bash
POST /api/v1/catalog/sync  {"mode": "full"}
```

Then verify:
- `satellites > 0` in PostgreSQL
- `digital_twin.objects_propagated > 0`
- Conjunction screening runs automatically (6h scheduler)
- Dashboard shows live tracked objects

**Effort:** One triggered sync + 15 min wait

---

## Priority 3 — Aerospace Knowledge Corpus Ingestion

17 authoritative sources are pre-configured in `corpus_service.py`. Trigger batch ingestion:

```bash
POST /api/v1/rag/corpus/ingest-all
```

**Sources include:**
- Spacetrack Report No. 3 (SGP4 model)
- NASA-STD-8719.14 (orbital debris standard)
- IADC Space Debris Mitigation Guidelines
- 3× NASA NTRS collision probability papers
- ESA Space Debris Environment Report 2023
- NASA Orbital Debris Quarterly News
- ISRO PSLV User's Guide
- Ariane 6 User's Manual
- NASA Artemis Plan
- Chandrayaan-3 Mission Overview
- SpaceX Starlink Architecture
- CCSDS CDM Standard (508.0-B-1)
- CCSDS TM Standard (131.0-B-5)
- Vallado Astrodynamics (selected chapters)
- ESA SST Programme Overview

**Expected output:** 500–2,000 chunks, 500–2,000 embeddings in Qdrant  
**Effect:** RAG queries gain document-grounded citations alongside graph data

---

## Priority 4 — SATCAT Enrichment

Current satellite nodes have `objectType = 'unknown'` because TLE data carries no operator metadata.
Space-Track SATCAT API provides: country code, launch date, object type, RCS size.

**Implementation:**
1. Extend `catalog_sync_service.py` to fetch SATCAT data alongside TLE data
2. Add `operator_name`, `country_code`, `launch_year`, `object_type_satcat` to `satellites` table
3. Graph population service creates `Operator` nodes and `OPERATED_BY` relationships
4. Analytics endpoints (`/analytics/operators`) become functional

**Effect:** Top operators by satellite count, country-level intelligence, constellation mapping

---

## Priority 5 — Benchmark Suite

Run the Foundation Model benchmark against the 17 configured tasks:

```bash
POST /api/v1/foundation/benchmark  {"model_id": "orbitiq-graphrag-v1", "dry_run": false}
```

**Measures:**
- Graph traversal latency (Neo4j Cypher queries)
- Vector retrieval latency (Qdrant similarity search)
- Hybrid retrieval latency (graph + vector fusion)
- Agent orchestration latency (LangGraph round-trip)
- End-to-end response time per tier

**Establishes:** v0.3.0 performance baseline for regression detection

---

## Priority 6 — Observability

**Missing from v0.2.0:**
- No external log aggregation (OPS-1 from readiness report)
- Sentry initialized but no DSN set
- No Prometheus scraping configured

**Actions:**
1. Configure Papertrail log drain in Railway (15 min — see `docs/OPERATIONS/LOG_AGGREGATION.md`)
2. Set `SENTRY_DSN` in Railway Variables (Sentry init is already wired)
3. Verify `/metrics` is scraped or export to Datadog

---

## Priority 7 — Agent Quality

Current agent responses include caveats about missing data (operator info, object type breakdown).
After SATCAT enrichment and corpus ingestion:

1. Re-run the LEO population / debris risk query
2. Compare answer quality (specificity, citations, operator data)
3. Tune agent prompts based on measured output quality

---

## v0.3.0 Definition of Done

- [ ] Redis healthy in platform health
- [ ] Digital Twin objects > 0
- [ ] Corpus ingested (>500 chunks in Qdrant)
- [ ] SATCAT enrichment (operator nodes in Neo4j)
- [ ] Benchmark suite completed with measured latencies
- [ ] Log drain configured (Papertrail or Datadog)
- [ ] Sentry DSN set and receiving events

---

## Non-Goals for v0.3.0

- No new agent types
- No new API endpoints
- No frontend changes
- No architecture modifications
- No fine-tuning or custom model training
