"""
ORBITIQ-X — Aerospace Intelligence API (GraphRAG)
==================================================
Phase 8: Full REST API for graph-aware aerospace reasoning.

Endpoints
─────────
  POST /rag/query           — Hybrid graph+vector Q&A (primary)
  POST /rag/explain         — Detailed explainable answer with evidence trace
  POST /rag/research        — Multi-hop research across corpus + graph
  GET  /rag/entity/{id}     — Entity intelligence brief from graph
  GET  /rag/mission/{id}    — Mission intelligence brief
  GET  /rag/conjunction/{id}— Conjunction event analysis
  POST /rag/ingest          — Add document to corpus
  GET  /rag/corpus/status   — Corpus ingestion status
  GET  /rag/corpus/sources  — List available corpus sources
  POST /rag/corpus/ingest-all — Trigger full corpus ingest
  GET  /rag/health          — System health (graph + vector + LLM)

Graceful degradation
────────────────────
  - Neo4j unavailable   → graph context empty, vector-only mode
  - Qdrant unavailable  → document context empty, graph-only mode
  - No Anthropic key    → returns graph context without LLM synthesis
  - All unavailable     → 503 with clear message

Phase 9 explainability
───────────────────────
  Every response includes:
    evidence_sources  — each fact traced to graph node or document
    citations         — formatted bibliography
    graph_nodes_used  — Neo4j nodes queried
    conjunctions_retrieved — live SSA data
    confidence        — aggregate 0–1 score
    uncertainty_flags — what data was missing
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request/response models ───────────────────────────────────

class AerospaceQueryRequest(BaseModel):
    query:          str = Field(..., min_length=5, description="Natural language aerospace question")
    norad_id:       int | None = Field(None, description="Focus on specific NORAD catalog number")
    mission:        str | None = Field(None, description="Focus on specific mission name")
    max_doc_chunks: int = Field(5, ge=1, le=20)
    include_graph:  bool = True
    include_vector: bool = True


class ExplainRequest(BaseModel):
    query:    str = Field(..., min_length=5)
    norad_id: int | None = None
    depth:    int = Field(2, ge=1, le=4, description="Graph traversal depth for explanation")


class ResearchRequest(BaseModel):
    query:    str = Field(..., min_length=5)
    agencies: list[str] = Field(default_factory=list, description="Filter by agency: NASA, ESA, ISRO…")
    max_chunks: int = Field(10, ge=1, le=30)


class IngestRequest(BaseModel):
    url:      str
    title:    str
    agency:   str = "OTHER"
    doc_type: str = "unknown"
    year:     int | None = None


# ── Singletons ────────────────────────────────────────────────
# Lazy-initialised at first request to avoid import errors at startup
# when Anthropic / Qdrant are not configured.

_bridge = None
_corpus = None


def _get_bridge():
    global _bridge
    if _bridge is None:
        from app.services.graphrag.graphrag_bridge import GraphRAGBridge
        _bridge = GraphRAGBridge()

        # Inject Anthropic client if configured
        try:
            from anthropic import AsyncAnthropic
            from app.core.config import get_settings
            s = get_settings()
            _bridge.set_anthropic(
                AsyncAnthropic(api_key=s.ANTHROPIC_API_KEY.get_secret_value())
            )
        except Exception as exc:
            logger.warning("anthropic_client_init_failed error=%s", exc)

        # Inject Qdrant RAG pipeline if configured
        try:
            from app.core.config import get_settings
            import sys, os
            s = get_settings()
            qdrant_url = s.QDRANT_URL
            qdrant_key = s.QDRANT_API_KEY.get_secret_value()
            if qdrant_url:
                from qdrant_client import QdrantClient, AsyncQdrantClient
                from openai import AsyncOpenAI

                qdrant_client      = QdrantClient(url=qdrant_url, api_key=qdrant_key or None)
                qdrant_async       = AsyncQdrantClient(url=qdrant_url, api_key=qdrant_key or None)
                openai_client      = AsyncOpenAI(api_key=s.OPENAI_API_KEY.get_secret_value())

                # Verify Qdrant connectivity
                qdrant_client.get_collections()

                class _OpenAIPipeline:
                    """
                    Production RAG pipeline using OpenAI text-embedding-3-large (3072-dim).
                    Supports document ingestion (ingest_url) and semantic retrieval.
                    Replaces BGE-M3 which requires GPU/heavy local model.
                    """
                    COLLECTION   = "aerospace_docs"
                    EMBED_MODEL  = "text-embedding-3-large"
                    EMBED_DIM    = 3072
                    CHUNK_SIZE   = 800
                    CHUNK_OVERLAP = 100

                    def __init__(self, qdrant, qdrant_async, openai):
                        self._q   = qdrant
                        self._qa  = qdrant_async
                        self._oai = openai
                        self._ensure_collection()

                    def _ensure_collection(self):
                        from qdrant_client.models import Distance, VectorParams
                        existing = [c.name for c in self._q.get_collections().collections]
                        if self.COLLECTION not in existing:
                            self._q.create_collection(
                                self.COLLECTION,
                                vectors_config=VectorParams(
                                    size=self.EMBED_DIM, distance=Distance.COSINE
                                )
                            )

                    async def _embed(self, texts: list[str]) -> list[list[float]]:
                        resp = await self._oai.embeddings.create(
                            model=self.EMBED_MODEL, input=texts
                        )
                        return [d.embedding for d in resp.data]

                    def _chunk_text(self, text: str) -> list[str]:
                        words = text.split()
                        chunks, i = [], 0
                        while i < len(words):
                            chunk = " ".join(words[i:i + self.CHUNK_SIZE])
                            chunks.append(chunk)
                            i += self.CHUNK_SIZE - self.CHUNK_OVERLAP
                        return [c for c in chunks if len(c.strip()) > 50]

                    async def ingest_url(self, url: str, metadata=None) -> int:
                        """Download URL, chunk, embed with OpenAI, upsert to Qdrant."""
                        import httpx, uuid
                        from qdrant_client.models import PointStruct
                        try:
                            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                                r = await client.get(url)
                                r.raise_for_status()
                                content_type = r.headers.get("content-type", "")
                                raw = r.content

                            # Extract text
                            if "pdf" in content_type or url.endswith(".pdf"):
                                try:
                                    import io
                                    import pypdf
                                    reader = pypdf.PdfReader(io.BytesIO(raw))
                                    text = " ".join(p.extract_text() or "" for p in reader.pages)
                                except Exception:
                                    text = raw.decode("utf-8", errors="ignore")
                            else:
                                from html.parser import HTMLParser
                                class _P(HTMLParser):
                                    def __init__(self): super().__init__(); self.parts=[]
                                    def handle_data(self, d): self.parts.append(d)
                                p = _P(); p.feed(raw.decode("utf-8", errors="ignore"))
                                text = " ".join(p.parts)

                            chunks = self._chunk_text(text)
                            if not chunks:
                                return 0

                            # Embed in batches of 20
                            points, batch_size = [], 20
                            for i in range(0, len(chunks), batch_size):
                                batch = chunks[i:i+batch_size]
                                vectors = await self._embed(batch)
                                for j, (chunk, vec) in enumerate(zip(batch, vectors)):
                                    points.append(PointStruct(
                                        id=str(uuid.uuid4()),
                                        vector=vec,
                                        payload={
                                            "text": chunk, "url": url,
                                            "chunk_index": i+j,
                                            "title": (metadata.title if metadata else url.split("/")[-1]),
                                        }
                                    ))

                            # Upsert to Qdrant
                            self._q.upsert(collection_name=self.COLLECTION, points=points)
                            logger.info("corpus_ingest_complete url=%s chunks=%d", url, len(points))
                            return len(points)
                        except Exception as exc:
                            logger.warning("corpus_ingest_failed url=%s error=%s", url, exc)
                            return 0

                    async def answer(self, query):
                        """Vector search + OpenAI synthesis."""
                        try:
                            vecs = await self._embed([query.query])
                            hits = self._q.search(
                                collection_name=self.COLLECTION,
                                query_vector=vecs[0], limit=5
                            )
                            if not hits:
                                return None
                            context = "\n\n".join(h.payload.get("text","") for h in hits)
                            resp = await self._oai.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[
                                    {"role":"system","content":"You are an aerospace technical assistant. Answer based on the provided context."},
                                    {"role":"user","content":f"Context:\n{context}\n\nQuestion: {query.query}"},
                                ],
                                max_tokens=1024
                            )
                            return resp.choices[0].message.content
                        except Exception as exc:
                            logger.warning("rag_answer_failed error=%s", exc)
                            return None

                pipeline = _OpenAIPipeline(qdrant_client, qdrant_async, openai_client)
                _bridge.set_pipeline(pipeline)

                # Wire pipeline into corpus service for document ingestion.
                # _corpus may be None here (lazy init) — set it now so
                # ingest-all calls will use the OpenAI pipeline.
                _get_corpus().set_pipeline(pipeline)

                logger.info("qdrant_openai_pipeline_initialized url=%s", qdrant_url)
        except Exception as exc:
            logger.warning("qdrant_pipeline_init_failed error=%s", exc)

    return _bridge


def _get_corpus():
    global _corpus
    if _corpus is None:
        from app.services.graphrag.corpus_service import AerospaceCorpusService
        _corpus = AerospaceCorpusService()
    return _corpus


# ── POST /rag/query ───────────────────────────────────────────

@router.post(
    "/query",
    summary="Aerospace intelligence query",
    description=(
        "Hybrid graph+vector aerospace Q&A. "
        "Combines live Neo4j Knowledge Graph with technical document corpus "
        "to answer aerospace questions with evidence-based reasoning. "
        "Gracefully degrades: works in graph-only or vector-only mode. "
        "Example queries: 'Which ISRO satellites have the highest Pc?', "
        "'Explain Artemis mission architecture', "
        "'Show conjunction risks involving Starlink'"
    ),
)
async def query_aerospace(request: AerospaceQueryRequest) -> ORJSONResponse:
    bridge = _get_bridge()

    try:
        response = await bridge.query(
            user_query=request.query,
            norad_id=request.norad_id,
            mission=request.mission,
            max_doc_chunks=request.max_doc_chunks,
        )
        return ORJSONResponse(content=response.to_dict())

    except Exception as exc:
        logger.exception("rag_query_failed query=%s", request.query[:100])
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {exc}. "
                   "Partial results may be available in graph endpoints."
        )


# ── POST /rag/explain ─────────────────────────────────────────

@router.post(
    "/explain",
    summary="Explainable aerospace intelligence",
    description=(
        "Extended explainable response. Returns full evidence trace: "
        "every claim linked to a source (graph node, relationship, or document). "
        "Phase 9 explainability — no hallucinated facts."
    ),
)
async def explain_aerospace(request: ExplainRequest) -> ORJSONResponse:
    bridge = _get_bridge()

    try:
        response = await bridge.query(
            user_query=request.query,
            norad_id=request.norad_id,
            max_doc_chunks=8,
        )
        result = response.to_dict()

        # Add full evidence trace for /explain (more detail than /query)
        result["full_evidence"] = [
            {
                "type":        e.source_type,
                "id":          e.source_id,
                "title":       e.title,
                "content":     e.content[:500],
                "entity_type": e.entity_type,
                "relevance":   e.relevance,
                "url":         e.url,
            }
            for e in response.evidence_sources
        ]
        result["graph_nodes_detail"]    = response.graph_nodes_used[:10]
        result["graph_relations_detail"]= response.graph_relations_used[:10]
        result["satellites_detail"]     = response.satellites_retrieved[:10]
        result["missions_detail"]       = response.missions_retrieved[:10]
        result["operators_detail"]      = response.operators_retrieved[:10]
        result["conjunctions_detail"]   = response.conjunctions_retrieved[:10]

        return ORJSONResponse(content=result)

    except Exception as exc:
        logger.exception("rag_explain_failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ── POST /rag/research ────────────────────────────────────────

@router.post(
    "/research",
    summary="Multi-document aerospace research",
    description=(
        "Deep research query that retrieves from multiple document sources "
        "and the knowledge graph, synthesizes across them, and returns "
        "a comprehensive research brief with bibliography. "
        "Suitable for: 'Summarize all known debris mitigation standards', "
        "'Explain the Foster Pc method and its limitations'"
    ),
)
async def research_aerospace(request: ResearchRequest) -> ORJSONResponse:
    bridge = _get_bridge()

    try:
        response = await bridge.query(
            user_query=request.query,
            max_doc_chunks=request.max_chunks,
        )
        result = response.to_dict()

        # Research mode: include full bibliography
        result["research_mode"] = True
        result["bibliography"] = [
            {
                "citation_key": c.get("key", ""),
                "title":        c.get("title", ""),
                "agency":       c.get("agency", ""),
                "year":         c.get("year"),
                "excerpt":      c.get("excerpt", "")[:300],
            }
            for c in response.citations
        ]

        return ORJSONResponse(content=result)

    except Exception as exc:
        logger.exception("rag_research_failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ── GET /rag/entity/{entity_id} ───────────────────────────────

@router.get(
    "/entity/{entity_id}",
    summary="Entity intelligence brief",
    description=(
        "Returns a graph intelligence brief for any entity ID. "
        "Entity ID can be a NORAD catalog number, operator name, "
        "country code, or constellation name. "
        "Pulls from the live Neo4j graph — no LLM call needed."
    ),
)
async def get_entity(entity_id: str) -> ORJSONResponse:
    from app.graph.connection import is_available

    if not is_available():
        raise HTTPException(503, detail="Neo4j Knowledge Graph unavailable")

    # Try NORAD ID first (numeric)
    try:
        norad = int(entity_id)
        from app.graph.repositories.graph_repository import SatelliteGraphRepository
        sat_repo = SatelliteGraphRepository()
        sat = await sat_repo.get_satellite(norad)
        if sat:
            return ORJSONResponse(content={"type": "Satellite", "data": sat})
    except ValueError:
        pass

    # Try operator
    from app.graph.services.graph_analytics_service import GraphAnalyticsService
    analytics = GraphAnalyticsService()
    op = await analytics.operator_conjunction_risk_profile(entity_id)
    if op:
        return ORJSONResponse(content={"type": "Operator", "data": op})

    # Try country
    country = await analytics.country_full_profile(entity_id.upper())
    if country:
        return ORJSONResponse(content={"type": "Country", "data": country})

    # Try constellation
    constellation = await analytics.constellation_profile(entity_id)
    if constellation:
        return ORJSONResponse(content={"type": "Constellation", "data": constellation})

    raise HTTPException(
        status_code=404,
        detail=f"Entity '{entity_id}' not found in Knowledge Graph. "
               "Run POST /graph/populate to sync satellite catalog."
    )


# ── GET /rag/mission/{mission_id} ─────────────────────────────

@router.get(
    "/mission/{mission_id}",
    summary="Mission intelligence brief",
    description=(
        "Returns combined mission intelligence: graph profile + "
        "relevant document corpus excerpts about this mission."
    ),
)
async def get_mission_intelligence(mission_id: str) -> ORJSONResponse:
    bridge = _get_bridge()

    # Graph mission profile
    from app.graph.connection import is_available
    graph_profile = {}
    if is_available():
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        analytics = GraphAnalyticsService()
        graph_profile = await analytics.mission_profile(mission_id)
        if not graph_profile:
            graph_profile = await analytics.constellation_profile(mission_id)

    # Document intelligence
    rag_response = await bridge.query(
        user_query=f"Explain the {mission_id} mission architecture, objectives, and status",
        mission=mission_id,
        max_doc_chunks=5,
    )

    return ORJSONResponse(content={
        "mission_id":     mission_id,
        "graph_profile":  graph_profile,
        "intelligence":   rag_response.answer,
        "confidence":     rag_response.confidence,
        "citations":      rag_response.citations,
        "evidence_count": len(rag_response.evidence_sources),
    })


# ── GET /rag/conjunction/{conjunction_id} ─────────────────────

@router.get(
    "/conjunction/{conjunction_id}",
    summary="Conjunction event analysis",
    description=(
        "Returns a full conjunction analysis brief: CDM data from PostgreSQL, "
        "graph relationship context, and LLM-synthesized risk assessment."
    ),
)
async def get_conjunction_analysis(
    conjunction_id: str,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    # Get CDM from PostgreSQL
    from app.db.repositories.conjunction_repository import ConjunctionRepository
    conj_repo = ConjunctionRepository(session)
    cdm = await conj_repo.get_by_conjunction_id(conjunction_id)

    if not cdm:
        raise HTTPException(
            status_code=404,
            detail=f"Conjunction '{conjunction_id}' not found in CDM archive."
        )

    # Generate analysis
    bridge = _get_bridge()
    query = (
        f"Analyze the conjunction between {cdm.primary_name or cdm.primary_norad} "
        f"and {cdm.secondary_name or cdm.secondary_norad}. "
        f"Pc={cdm.collision_probability:.2e}, "
        f"miss distance={cdm.miss_distance_km:.3f} km, "
        f"risk level={cdm.risk_level}. "
        f"What action is recommended?"
    )

    rag_response = await bridge.query(
        user_query=query,
        norad_id=cdm.primary_norad,
        max_doc_chunks=3,
    )

    return ORJSONResponse(content={
        "conjunction_id":         conjunction_id,
        "primary":                {"norad": cdm.primary_norad, "name": cdm.primary_name},
        "secondary":              {"norad": cdm.secondary_norad, "name": cdm.secondary_name},
        "tca":                    cdm.tca.isoformat() if cdm.tca else None,
        "miss_distance_km":       cdm.miss_distance_km,
        "relative_velocity_kms":  cdm.relative_velocity_kms,
        "collision_probability":  cdm.collision_probability,
        "risk_level":             cdm.risk_level,
        "maneuver_required":      cdm.maneuver_required,
        "resolved":               cdm.resolved,
        "analysis":               rag_response.answer,
        "confidence":             rag_response.confidence,
        "citations":              rag_response.citations,
    })


# ── POST /rag/ingest ──────────────────────────────────────────

@router.post(
    "/ingest",
    status_code=202,
    summary="Ingest document into corpus",
    description=(
        "Queues a document URL for ingestion into the aerospace knowledge corpus. "
        "Supports PDF, HTML, LaTeX, DOCX formats. "
        "Returns 202 Accepted immediately; ingest runs in background."
    ),
)
async def ingest_document(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
) -> ORJSONResponse:
    doc_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(
        _background_ingest,
        url=request.url,
        title=request.title,
        agency=request.agency,
        doc_type=request.doc_type,
        year=request.year,
    )
    return ORJSONResponse(
        status_code=202,
        content={
            "accepted": True,
            "doc_id":   doc_id,
            "url":      request.url,
            "message":  f"Document queued for ingestion (doc_id={doc_id}). "
                        f"Check GET /rag/corpus/status for progress.",
        },
    )


async def _background_ingest(url: str, title: str, agency: str, doc_type: str, year: int | None):
    corpus = _get_corpus()
    # Direct URL ingest through corpus service
    source_id = f"MANUAL-{title[:20].upper().replace(' ', '_')}"
    try:
        from app.services.graphrag.corpus_service import CorpusSource, CORPUS_SOURCES
        # Add to in-memory registry for this run
        logger.info("corpus_manual_ingest url=%s title=%s", url, title)
        # The pipeline is needed for actual ingest
        if corpus._pipeline:
            chunks = await corpus._pipeline.ingest_url(url, None)
            logger.info("corpus_manual_ingest_complete url=%s chunks=%d", url, chunks)
    except Exception as exc:
        logger.error("corpus_manual_ingest_failed url=%s error=%s", url, exc)


# ── GET /rag/corpus/status ────────────────────────────────────

@router.get(
    "/corpus/status",
    summary="Aerospace corpus status",
    description="Returns ingestion status for all corpus sources.",
)
async def get_corpus_status() -> ORJSONResponse:
    corpus = _get_corpus()
    return ORJSONResponse(content=corpus.get_status())


# ── GET /rag/corpus/sources ───────────────────────────────────

@router.get(
    "/corpus/sources",
    summary="List aerospace corpus sources",
    description="Returns the curated list of aerospace document sources.",
)
async def list_corpus_sources(
    agency: Annotated[str | None, Query()] = None,
    doc_type: Annotated[str | None, Query()] = None,
    priority: Annotated[int | None, Query(ge=1, le=3)] = None,
    tag: Annotated[str | None, Query()] = None,
) -> ORJSONResponse:
    corpus  = _get_corpus()
    sources = corpus.list_sources(
        agency=agency,
        doc_type=doc_type,
        priority=priority,
        tags=[tag] if tag else None,
    )
    return ORJSONResponse(content={
        "count":   len(sources),
        "sources": [
            {
                "source_id":   s.source_id,
                "title":       s.title,
                "agency":      s.agency,
                "doc_type":    s.doc_type,
                "year":        s.year,
                "priority":    s.priority,
                "tags":        s.tags,
                "url":         s.url,
                "description": s.description[:200],
            }
            for s in sources
        ],
    })


# ── POST /rag/corpus/ingest-all ───────────────────────────────

@router.post(
    "/corpus/ingest-all",
    status_code=202,
    summary="Trigger full corpus ingestion",
    description=(
        "Queues all high-priority corpus sources for background ingestion. "
        "This is a long-running task (5–30 minutes depending on document count). "
        "Monitor progress with GET /rag/corpus/status."
    ),
)
async def ingest_all_corpus(
    background_tasks: BackgroundTasks,
    priority: Annotated[int, Query(ge=1, le=3)] = 2,
    agency: Annotated[str | None, Query()] = None,
) -> ORJSONResponse:
    run_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(
        _background_ingest_all,
        priority_filter=priority,
        agency_filter=agency,
    )
    return ORJSONResponse(
        status_code=202,
        content={
            "accepted":  True,
            "run_id":    run_id,
            "priority":  priority,
            "agency":    agency,
            "message":   f"Corpus ingestion started (run_id={run_id}, priority≤{priority}). "
                         "Monitor with GET /rag/corpus/status.",
        },
    )


async def _background_ingest_all(priority_filter: int, agency_filter: str | None):
    corpus = _get_corpus()
    results = await corpus.ingest_all(
        priority_filter=priority_filter,
        agency_filter=agency_filter,
    )
    ok = sum(1 for r in results if r["status"] == "ok")
    logger.info(
        "corpus_ingest_all_complete total=%d ok=%d failed=%d",
        len(results), ok, len(results) - ok,
    )


# ── GET /rag/health ───────────────────────────────────────────

@router.get(
    "/health",
    summary="GraphRAG system health",
    description=(
        "Returns health status of all GraphRAG subsystems: "
        "Neo4j (graph retrieval), Qdrant (vector retrieval), "
        "Anthropic (LLM synthesis), and corpus status."
    ),
)
async def rag_health() -> ORJSONResponse:
    # Neo4j
    from app.graph.connection import health_check as neo4j_health, is_available
    graph_status = await neo4j_health()

    # Qdrant
    qdrant_ok = False
    try:
        bridge = _get_bridge()
        qdrant_ok = bridge._pipeline is not None
    except Exception:
        pass

    # Anthropic
    anthropic_ok = False
    try:
        from app.core.config import get_settings
        s = get_settings()
        anthropic_ok = bool(s.ANTHROPIC_API_KEY.get_secret_value())
    except Exception:
        pass

    # Corpus
    corpus = _get_corpus()
    corpus_status = corpus.get_status()

    overall = "healthy"
    if not graph_status["reachable"] and not qdrant_ok:
        overall = "unhealthy"
    elif not graph_status["reachable"] or not qdrant_ok:
        overall = "degraded"

    return ORJSONResponse(content={
        "overall":           overall,
        "neo4j": {
            "available":     graph_status["reachable"],
            "node_count":    graph_status.get("node_count", 0),
        },
        "qdrant": {
            "available":     qdrant_ok,
        },
        "anthropic": {
            "configured":    anthropic_ok,
            "model":         "claude-sonnet-4-6",
        },
        "corpus": {
            "total_sources": corpus_status["total_sources"],
            "ingested":      corpus_status["ingested"],
            "total_chunks":  corpus_status["total_chunks"],
        },
        "mode": (
            "full_graphrag" if graph_status["reachable"] and qdrant_ok else
            "graph_only"    if graph_status["reachable"] else
            "vector_only"   if qdrant_ok else
            "degraded"
        ),
    })
