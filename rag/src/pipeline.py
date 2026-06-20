"""
ORBITIQ-X Aerospace RAG
Pipeline Orchestrator + FastAPI Endpoints

Wires together:
  ingestion → chunking → embedding → Qdrant → retrieval → synthesis

API:
  POST /api/v1/rag/query          — synchronous aerospace Q&A
  POST /api/v1/rag/query/stream   — SSE streaming answer
  POST /api/v1/rag/ingest         — ingest a document
  POST /api/v1/rag/ingest/batch   — batch ingest from URLs
  GET  /api/v1/rag/sources        — list indexed documents
  GET  /api/v1/rag/stats          — corpus statistics
  POST /api/v1/rag/eval           — run evaluation suite
  DELETE /api/v1/rag/doc/{doc_id} — remove document
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from anthropic import AsyncAnthropic
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from .ingestion.loaders import load_document, detect_agency, detect_doc_type
from .chunking.chunker import AerospaceChunker, QualityFilter
from .embedding.embedder import BGEM3Embedder, AerospaceNER, HyDEQueryExpander
from .store.qdrant_store import AerospaceQdrantStore
from .retrieval.pipeline import RetrievalPipeline, CrossEncoderReranker, MMRDiversitySelector
from .hallucination.guard import HallucinationGuard, ContextBuilder, CitationFormatter
from .models.schemas import (
    DocumentMetadata, AgencyType, DocumentType,
    RAGQuery, RAGResponse, CitationRecord,
)

logger = logging.getLogger(__name__)


# ── Pipeline orchestrator ─────────────────────────────────────

class AerospaceRAGPipeline:
    """
    End-to-end RAG pipeline for aerospace technical documents.

    Initialization order:
    1. Connect to Qdrant, ensure collection exists
    2. Load BGE-M3 embedder (CPU or GPU)
    3. Load BGE-Reranker cross-encoder
    4. Connect Anthropic client for answer synthesis
    """

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        anthropic_api_key: str | None = None,
        device: str = "cpu",
    ):
        self.store    = AerospaceQdrantStore(host=qdrant_host, port=qdrant_port)
        self.embedder = BGEM3Embedder(device=device)
        self.ner      = AerospaceNER()
        self.chunker  = AerospaceChunker()
        self.filter   = QualityFilter()
        self.reranker = CrossEncoderReranker()
        self.mmr      = MMRDiversitySelector()
        self.client   = AsyncAnthropic(api_key=anthropic_api_key)
        self.hyde     = HyDEQueryExpander(self.client, self.embedder)
        self.retrieval = RetrievalPipeline(
            store=self.store,
            embedder=self.embedder,
            hyde_expander=self.hyde,
            reranker=self.reranker,
            mmr=self.mmr,
        )
        self.ctx_builder   = ContextBuilder()
        self.guard         = HallucinationGuard(self.client)
        self.citation_fmt  = CitationFormatter()

    def initialize(self) -> None:
        """Create Qdrant collection if not exists."""
        self.store.create_collection(recreate=False)
        logger.info("AerospaceRAGPipeline initialized")

    # ── Ingestion ─────────────────────────────────────────────

    def ingest_document(
        self,
        path: str,
        metadata: DocumentMetadata | None = None,
    ) -> int:
        """
        Full ingestion pipeline for a single document.
        Returns number of chunks indexed.
        """
        # Build metadata if not provided
        if metadata is None:
            from pathlib import Path
            title = Path(path).stem.replace("_", " ").replace("-", " ").title()
            metadata = DocumentMetadata(title=title)

        # Load document
        raw_doc = load_document(path, metadata)
        if raw_doc is None:
            raise ValueError(f"Failed to load document: {path}")

        # Auto-detect agency and doc type if not set
        if metadata.agency == AgencyType.OTHER:
            metadata.agency = detect_agency(raw_doc.content, metadata.title)
        if metadata.doc_type == DocumentType.UNKNOWN:
            metadata.doc_type = detect_doc_type(raw_doc.content, metadata.title)

        # Chunk
        chunks = self.chunker.chunk(raw_doc)
        logger.info(f"Chunked into {len(chunks)} chunks")

        # Quality filter
        chunks = self.filter.filter(chunks)
        logger.info(f"After quality filter: {len(chunks)} chunks")

        # NER enrichment
        chunks = [self.ner.enrich_chunk(c) for c in chunks]

        # Embed (dense + sparse)
        chunks = self.embedder.embed_chunks(chunks)

        # Upsert to Qdrant
        count = self.store.upsert_chunks(chunks)
        logger.info(f"Indexed {count} chunks from: {metadata.title}")
        return count

    async def ingest_url(self, url: str, metadata: DocumentMetadata | None = None) -> int:
        """Download and ingest a document from URL."""
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            # Save to temp file
            import tempfile
            suffix = ".pdf" if "pdf" in response.headers.get("content-type", "") else ".html"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(response.content)
                tmp_path = f.name

        if metadata is None:
            metadata = DocumentMetadata(title=url.split("/")[-1], source_url=url)
        return self.ingest_document(tmp_path, metadata)

    # ── Answer synthesis ──────────────────────────────────────

    async def answer(self, query: RAGQuery) -> RAGResponse:
        """
        Full RAG pipeline: retrieve → build context → generate → guard → cite.
        """
        t0 = time.perf_counter()

        # 1. Retrieve
        chunks = await self.retrieval.retrieve(query)
        if not chunks:
            return self._empty_response(query.query, t0)

        # 2. Build context + citations
        context, citations = self.ctx_builder.build(chunks, query.query)
        prompt = self.ctx_builder.build_prompt(query.query, context)

        # 3. Generate answer
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        answer_text = response.content[0].text

        # 4. Hallucination guard
        source_texts = [c.text for c in chunks]
        faithfulness, unsupported = self.guard.check_faithfulness(answer_text, source_texts)
        numeric_issues = self.guard.verify_numerics(answer_text, source_texts)
        uncertainty_flags = self.guard.extract_uncertainty_flags(answer_text)

        # 5. Confidence score
        avg_score = sum(c.final_score for c in chunks) / len(chunks)
        confidence = self.guard.compute_confidence(
            faithfulness=faithfulness,
            unsupported_count=len(unsupported),
            total_sentences=len(answer_text.split(".")),
            numeric_issues=len(numeric_issues),
            avg_retrieval_score=avg_score,
        )

        # 6. Attach bibliography
        final_answer = self.citation_fmt.attach_citations_to_answer(answer_text, citations)

        latency = (time.perf_counter() - t0) * 1000

        return RAGResponse(
            query=query.query,
            answer=final_answer,
            confidence=confidence,
            faithfulness_score=faithfulness,
            sources=citations,
            retrieved_chunks=chunks,
            hallucination_flags=unsupported[:5],
            uncertain_claims=uncertainty_flags[:5],
            search_mode_used=query.search_mode.value,
            chunks_retrieved=len(chunks),
            chunks_after_rerank=len(chunks),
            latency_ms=round(latency, 1),
        )

    async def stream_answer(self, query: RAGQuery):
        """SSE streaming version of answer()."""
        # Stream retrieval status
        yield f"data: {json.dumps({'event': 'retrieving', 'chunks': 0})}\n\n"

        chunks = await self.retrieval.retrieve(query)
        yield f"data: {json.dumps({'event': 'retrieved', 'chunks': len(chunks)})}\n\n"

        context, citations = self.ctx_builder.build(chunks, query.query)
        prompt = self.ctx_builder.build_prompt(query.query, context)

        yield f"data: {json.dumps({'event': 'generating'})}\n\n"

        # Stream answer tokens
        async with self.client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'event': 'token', 'text': text})}\n\n"

        # Stream citations
        cit_data = [c.model_dump() for c in citations]
        yield f"data: {json.dumps({'event': 'citations', 'sources': cit_data})}\n\n"
        yield f"data: {json.dumps({'event': 'done'})}\n\n"

    def _empty_response(self, query: str, t0: float) -> RAGResponse:
        return RAGResponse(
            query=query,
            answer="I could not find relevant information in the aerospace document corpus for this query. Please try rephrasing or check if the relevant documents have been ingested.",
            confidence=0.0,
            faithfulness_score=1.0,
            sources=[],
            retrieved_chunks=[],
            hallucination_flags=[],
            uncertain_claims=["No relevant sources found"],
            search_mode_used="hybrid",
            chunks_retrieved=0,
            chunks_after_rerank=0,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )


# ── FastAPI app ───────────────────────────────────────────────

_pipeline: AerospaceRAGPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    _pipeline = AerospaceRAGPipeline()
    _pipeline.initialize()
    yield
    logger.info("RAG pipeline shutdown")


def create_rag_app() -> FastAPI:
    app = FastAPI(
        title="ORBITIQ-X Aerospace RAG",
        version="1.0.0",
        description="Aerospace engineering RAG with BGE-M3 + Qdrant + Claude",
        lifespan=lifespan,
    )

    @app.post("/api/v1/rag/query", response_model=RAGResponse)
    async def rag_query(query: RAGQuery):
        if not _pipeline:
            raise HTTPException(503, "Pipeline not initialized")
        return await _pipeline.answer(query)

    @app.post("/api/v1/rag/query/stream")
    async def rag_stream(query: RAGQuery):
        if not _pipeline:
            raise HTTPException(503, "Pipeline not initialized")
        return StreamingResponse(
            _pipeline.stream_answer(query),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/rag/ingest")
    async def ingest(
        url: str,
        title: str,
        agency: AgencyType = AgencyType.OTHER,
        doc_type: DocumentType = DocumentType.UNKNOWN,
        year: int | None = None,
        background_tasks: BackgroundTasks = None,
    ):
        meta = DocumentMetadata(
            title=title, agency=agency, doc_type=doc_type,
            publication_year=year, source_url=url,
        )
        background_tasks.add_task(_pipeline.ingest_url, url, meta)
        return {"status": "ingestion_queued", "url": url}

    @app.get("/api/v1/rag/stats")
    async def rag_stats():
        if not _pipeline:
            raise HTTPException(503)
        return _pipeline.store.collection_stats()

    @app.post("/api/v1/rag/eval")
    async def run_eval(max_samples: int = 50):
        from .evaluation.evaluator import AerospaceRAGEvaluator
        evaluator = AerospaceRAGEvaluator(_pipeline, _pipeline.embedder)
        metrics = await evaluator.evaluate(max_samples=max_samples)
        return metrics.model_dump()

    return app
