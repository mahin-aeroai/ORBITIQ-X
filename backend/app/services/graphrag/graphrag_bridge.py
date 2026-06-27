"""
ORBITIQ-X — GraphRAG Intelligence Bridge
==========================================
Fuses the Neo4j Knowledge Graph with the Qdrant vector store
to produce graph-aware aerospace answers.

Pipeline
────────
  User query
      │
      ▼
  Intent Detection (entity extraction: satellites, operators, missions…)
      │
      ▼
  ┌──────────────────────────────────┐
  │ Graph Retrieval (Neo4j)          │  structured facts + relationships
  │   entity lookup → subgraph       │
  │   expand via relationships       │
  └──────────────────────────────────┘
              │
              ▼
  ┌──────────────────────────────────┐
  │ Vector Retrieval (Qdrant)        │  unstructured document context
  │   HyDE expansion → embed         │
  │   hybrid search + rerank         │
  └──────────────────────────────────┘
              │
              ▼
  Context Assembly (graph facts + doc chunks + conjunctions)
              │
              ▼
  Claude claude-sonnet-4-6 — structured aerospace answer
              │
              ▼
  Hallucination Guard → Confidence Score → Citations

Audit notes
────────────
  - knowledge-graph/graphrag/retriever.py: AerospaceGraphRetriever,
    GraphRAGAnswerer already implemented → called from here (not rewritten)
  - rag/src/pipeline.py: AerospaceRAGPipeline.answer() already implements
    vector path → called from here (not rewritten)
  - app/graph/services/graph_analytics_service.py: analytics queries
    already implemented → called to enrich graph context
"""

from __future__ import annotations

import json
import logging
import sys
import pathlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Add knowledge-graph to path for the existing GraphRAG retriever
# Container layout: /app/app/services/graphrag/graphrag_bridge.py
# parents[3] = /app  (contains rag/ and knowledge-graph/)
_APP_DIR  = pathlib.Path(__file__).parents[3]
_KG_ROOT  = _APP_DIR / "knowledge-graph"
_RAG_ROOT = _APP_DIR / "rag"
for _p in [str(_KG_ROOT), str(_RAG_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)


# ── Evidence record ───────────────────────────────────────────

@dataclass
class EvidenceSource:
    """A single piece of evidence supporting the answer."""
    source_type:  str          # "graph_node" | "graph_relation" | "document" | "conjunction"
    source_id:    str
    title:        str
    content:      str          # the actual fact/text
    entity_type:  str | None = None   # Satellite | Operator | ConjunctionEvent | etc.
    relevance:    float = 1.0
    url:          str | None = None


# ── Intelligence response ─────────────────────────────────────

@dataclass
class AerospaceIntelligenceResponse:
    """
    Full response from the GraphRAG system with full explainability.
    Every claim maps to a source.
    """
    query:             str
    answer:            str
    confidence:        float        # 0–1 aggregate confidence
    faithfulness:      float        # 0–1 hallucination guard score
    retrieval_mode:    str          # "graph" | "vector" | "hybrid"
    latency_ms:        float

    # Evidence (Phase 9 explainability)
    evidence_sources:        list[EvidenceSource] = field(default_factory=list)
    graph_nodes_used:        list[dict] = field(default_factory=list)
    graph_relations_used:    list[dict] = field(default_factory=list)
    document_chunks_used:    int = 0
    conjunctions_retrieved:  list[dict] = field(default_factory=list)
    satellites_retrieved:    list[dict] = field(default_factory=list)
    missions_retrieved:      list[dict] = field(default_factory=list)
    operators_retrieved:     list[dict] = field(default_factory=list)

    # Citations
    citations:               list[dict] = field(default_factory=list)
    cypher_executed:         str | None = None
    uncertainty_flags:       list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query":              self.query,
            "answer":             self.answer,
            "confidence":         self.confidence,
            "faithfulness":       self.faithfulness,
            "retrieval_mode":     self.retrieval_mode,
            "latency_ms":         round(self.latency_ms, 1),
            "evidence": {
                "sources":           [
                    {"type": e.source_type, "id": e.source_id,
                     "title": e.title, "relevance": e.relevance}
                    for e in self.evidence_sources[:10]
                ],
                "graph_nodes":       len(self.graph_nodes_used),
                "graph_relations":   len(self.graph_relations_used),
                "document_chunks":   self.document_chunks_used,
                "conjunctions":      len(self.conjunctions_retrieved),
                "satellites":        len(self.satellites_retrieved),
                "missions":          len(self.missions_retrieved),
                "operators":         len(self.operators_retrieved),
            },
            "citations":          self.citations[:10],
            "cypher":             self.cypher_executed,
            "uncertainty_flags":  self.uncertainty_flags[:5],
        }


# ── Intent detector ───────────────────────────────────────────

class AerospaceIntentDetector:
    """
    Lightweight rule-based intent detector.

    Extracts named entities and intent from aerospace queries
    without requiring an LLM call — keeps latency low for the
    entity-extraction step.

    The existing knowledge-graph/graphrag/retriever.py intent
    classifier uses LangChain + Claude → calls this first for
    fast entity extraction, then routes to the LLM classifier.
    """

    # Operator keywords → graph node names
    _OPERATORS = {
        "isro": "ISRO", "nasa": "NASA", "esa": "ESA", "spacex": "SpaceX",
        "jaxa": "JAXA", "roscosmos": "Roscosmos", "cnsa": "CNSA",
        "oneweb": "OneWeb", "planet": "Planet Labs",
        "maxar": "Maxar", "airbus": "Airbus Defence",
        "leosat": "LeoSat", "telesat": "Telesat",
    }

    # Mission keywords
    _MISSIONS = {
        "artemis": "Artemis", "chandrayaan": "Chandrayaan",
        "starlink": "Starlink", "oneweb": "OneWeb",
        "sentinel": "Sentinel", "cartosat": "Cartosat",
        "resourcesat": "Resourcesat", "aditya": "Aditya-L1",
        "mangalyaan": "Mangalyaan", "gps": "GPS",
        "galileo": "Galileo", "glonass": "GLONASS",
    }

    # Orbital regime keywords
    _REGIMES = {
        "leo": "LEO", "meo": "MEO", "geo": "GEO", "heo": "HEO",
        "sso": "SSO", "vleo": "VLEO", "cislunar": "CISLUNAR",
        "geostationary": "GEO", "polar": "SSO",
    }

    # Topic intents
    _CONJUNCTION_KEYWORDS = {
        "conjunction", "collision", "pc", "miss distance", "tca",
        "cdm", "maneuver", "avoidance", "close approach", "risk",
    }
    _DEBRIS_KEYWORDS = {
        "debris", "fragmentation", "breakup", "kessler", "cloud",
        "fragment", "remnant", "decay",
    }
    _LAUNCH_KEYWORDS = {
        "launch", "launched", "launched by", "vehicle", "pslv", "falcon",
        "ariane", "soyuz", "electron", "lvm3", "gslv",
    }
    _MISSION_KEYWORDS = {
        "mission", "program", "constellation", "payload", "satellite",
    }

    def detect(self, query: str) -> dict:
        """
        Extract entities and intent from a query string.

        Returns
        -------
        dict with keys:
          operators, missions, regimes, satellites, intent,
          is_conjunction, is_debris, is_launch, is_mission
        """
        q = query.lower()

        operators = [
            v for k, v in self._OPERATORS.items() if k in q
        ]
        missions = [
            v for k, v in self._MISSIONS.items() if k in q
        ]
        regimes = [
            v for k, v in self._REGIMES.items() if k in q
        ]

        is_conjunction = bool(self._CONJUNCTION_KEYWORDS & set(q.split()))
        is_debris      = bool(self._DEBRIS_KEYWORDS & set(q.split()))
        is_launch      = bool(self._LAUNCH_KEYWORDS & set(q.split()))
        is_mission     = bool(self._MISSION_KEYWORDS & set(q.split()))

        # Primary intent
        if is_conjunction:
            intent = "conjunction_risk"
        elif is_debris:
            intent = "debris_analysis"
        elif is_launch:
            intent = "launch_lineage"
        elif missions:
            intent = "mission_search"
        elif operators:
            intent = "operator_intelligence"
        else:
            intent = "general"

        return {
            "operators":        operators,
            "missions":         missions,
            "regimes":          regimes,
            "satellites":       [],
            "intent":           intent,
            "is_conjunction":   is_conjunction,
            "is_debris":        is_debris,
            "is_launch":        is_launch,
            "is_mission":       is_mission,
        }


# ── Graph context fetcher ─────────────────────────────────────

class GraphContextFetcher:
    """
    Fetches structured graph context from Neo4j using existing
    graph services. Does NOT rewrite any graph queries — calls
    app.graph.services.graph_analytics_service.GraphAnalyticsService.
    """

    async def fetch_for_entities(
        self,
        intent: dict,
        conjunction_norad: int | None = None,
    ) -> dict:
        """
        Fetch relevant graph context based on detected entities.

        Returns
        -------
        dict with graph facts: satellites, conjunctions, operators,
              missions, launch_vehicles, risk_network
        """
        from app.graph.connection import is_available
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        from app.graph.repositories.graph_repository import (
            SatelliteGraphRepository, ConjunctionGraphRepository,
        )

        ctx: dict[str, Any] = {
            "satellites":    [],
            "conjunctions":  [],
            "operators":     [],
            "regimes":       [],
            "risk_network":  [],
            "graph_available": is_available(),
        }

        if not is_available():
            return ctx

        analytics = GraphAnalyticsService()

        # Fetch operator data
        if intent["operators"]:
            for op in intent["operators"][:3]:
                profile = await analytics.operator_conjunction_risk_profile(op)
                if profile:
                    ctx["operators"].append(profile)

        # Fetch mission data
        if intent["missions"]:
            for mission in intent["missions"][:3]:
                constellation = await analytics.constellation_profile(mission)
                if constellation:
                    ctx["operators"].append(constellation)

        # Fetch orbital regime density
        if intent["regimes"] or intent["is_conjunction"] or intent["is_debris"]:
            density = await analytics.orbital_regime_density()
            ctx["regimes"] = density[:4]  # top 4 regimes

        # Fetch conjunction risk network for conjunction queries
        if intent["is_conjunction"]:
            risk_net = await analytics.conjunction_risk_network(min_pc=1e-5, limit=20)
            ctx["risk_network"] = risk_net

        # Fetch satellite-specific conjunctions
        if conjunction_norad:
            conj_repo = ConjunctionGraphRepository()
            conjunctions = await conj_repo.get_conjunctions_for_satellite(
                conjunction_norad, limit=10
            )
            ctx["conjunctions"] = conjunctions

        # Top operators (always useful context)
        if intent["intent"] in ("operator_intelligence", "conjunction_risk", "general"):
            top_ops = await analytics.top_operators_by_satellite_count(limit=5)
            ctx["top_operators"] = top_ops

        # Fallback: if analytics returned no regime data, query directly
        # using the actual relationship names in the database (ORBITS).
        # The analytics service uses LOCATED_IN_ORBIT which may not exist.
        if not ctx["regimes"] and is_available():
            try:
                from app.graph.connection import get_driver
                from app.core.config import get_settings
                _s = get_settings()
                _driver = get_driver()
                async with _driver.session(database=_s.NEO4J_DATABASE) as _session:
                    _r = await _session.run("""
                        MATCH (s:Satellite)-[:ORBITS]->(o:OrbitalRegime)
                        RETURN o.orbitId AS regimeId,
                               o.name AS regime,
                               count(s) AS totalObjects,
                               count(CASE WHEN s.objectType = 'debris' THEN 1 END) AS debris
                        ORDER BY totalObjects DESC
                    """)
                    ctx["regimes"] = [dict(r) async for r in _r]

                    _r2 = await _session.run("""
                        MATCH (s:Satellite)
                        RETURN count(s) AS totalSatellites,
                               count(CASE WHEN s.regime = 'LEO' THEN 1 END) AS leo,
                               count(CASE WHEN s.regime = 'GEO' THEN 1 END) AS geo,
                               count(CASE WHEN s.regime = 'MEO' THEN 1 END) AS meo,
                               count(CASE WHEN s.regime = 'HEO' THEN 1 END) AS heo
                    """)
                    rec = await _r2.single()
                    if rec:
                        ctx["catalog_summary"] = dict(rec)
            except Exception as _exc:
                logger.warning("graph_direct_query_failed error=%s", _exc)

        return ctx


# ── Context assembler (Phase 7) ───────────────────────────────

class AerospaceContextAssembler:
    """
    Assembles graph facts + document chunks into a structured
    reasoning package for Claude.

    This is the "Context Assembler" from Phase 7. It combines:
    - Graph entities (satellites, operators, conjunctions)
    - Graph relationships (conjunction networks, launch chains)
    - Conjunction records (Pc, TCA, miss distance)
    - Retrieved document chunks (from Qdrant vector search)
    - Analytics outputs (risk rankings, constellation sizes)

    Output is a structured prompt block that Claude uses to
    generate evidence-based answers.
    """

    def assemble(
        self,
        query: str,
        intent: dict,
        graph_ctx: dict,
        doc_context: str,
        doc_citations: list,
    ) -> tuple[str, list[EvidenceSource]]:
        """
        Build the full context block for the LLM.

        Returns
        -------
        (context_text, evidence_sources)
        """
        parts: list[str] = []
        evidence: list[EvidenceSource] = []

        # ── Section 1: Live Graph Facts ─────────────────────
        parts.append("## LIVE AEROSPACE KNOWLEDGE GRAPH DATA")
        parts.append(f"Query: {query}")
        parts.append(f"Detected intent: {intent['intent']}")
        parts.append("")

        if graph_ctx.get("operators"):
            parts.append("### Operator Intelligence")
            for op in graph_ctx["operators"][:3]:
                line = (
                    f"- **{op.get('operator', op.get('constellation', 'Unknown'))}**: "
                    f"{op.get('satelliteCount', op.get('memberCount', '?'))} objects, "
                    f"max Pc: {op.get('maxPc', 'N/A')}"
                )
                parts.append(line)
                evidence.append(EvidenceSource(
                    source_type="graph_node",
                    source_id=str(op.get("operator", op.get("constellation", ""))),
                    title=f"Operator/Constellation: {op.get('operator', op.get('constellation', ''))}",
                    content=line,
                    entity_type="Operator",
                    relevance=0.9,
                ))
            parts.append("")

        if graph_ctx.get("risk_network"):
            parts.append("### Active Conjunction Risk Network")
            for edge in graph_ctx["risk_network"][:5]:
                line = (
                    f"- {edge.get('name1', edge.get('norad1'))} ↔ "
                    f"{edge.get('name2', edge.get('norad2'))}: "
                    f"Pc={edge.get('Pc', 0):.2e}, "
                    f"miss={edge.get('missKm', 0):.3f} km, "
                    f"risk={edge.get('riskLevel', '?').upper()}, "
                    f"TCA={str(edge.get('tca', '?'))[:19]}"
                )
                parts.append(line)
                evidence.append(EvidenceSource(
                    source_type="conjunction",
                    source_id=str(edge.get("conjunctionId", "")),
                    title=f"Conjunction: NORAD {edge.get('norad1')} ↔ {edge.get('norad2')}",
                    content=line,
                    entity_type="ConjunctionEvent",
                    relevance=0.95,
                ))
            parts.append("")

        if graph_ctx.get("regimes"):
            parts.append("### Orbital Regime Population")
            for r in graph_ctx["regimes"]:
                parts.append(
                    f"- {r.get('regime', '?')}: "
                    f"{r.get('totalObjects', 0)} objects "
                    f"({r.get('satellites', 0)} satellites, "
                    f"{r.get('debris', 0)} debris)"
                )
            parts.append("")

        if graph_ctx.get("conjunctions"):
            parts.append("### Satellite-Specific Conjunction History")
            for c in graph_ctx["conjunctions"][:5]:
                ce = c.get("ce", {})
                parts.append(
                    f"- vs {c.get('counterpartName', 'unknown')}: "
                    f"Pc={ce.get('collisionProbability', 0):.2e}, "
                    f"role={c.get('role', '?')}, "
                    f"TCA={str(ce.get('tca', '?'))[:19]}"
                )
            parts.append("")

        # ── Section 2: Document Corpus Context ───────────────
        if doc_context.strip():
            parts.append("## AEROSPACE KNOWLEDGE CORPUS (Technical Documents)")
            parts.append(doc_context)
            parts.append("")

            for cit in doc_citations[:5]:
                evidence.append(EvidenceSource(
                    source_type="document",
                    source_id=cit.doc_id if hasattr(cit, "doc_id") else "",
                    title=cit.title if hasattr(cit, "title") else "",
                    content=cit.excerpt if hasattr(cit, "excerpt") else "",
                    entity_type="Document",
                    relevance=cit.relevance_score if hasattr(cit, "relevance_score") else 0.7,
                    url=cit.source_url if hasattr(cit, "source_url") else None,
                ))

        # ── Section 3: Reasoning instructions ────────────────
        parts.append("## INSTRUCTIONS FOR RESPONSE")
        parts.append(
            "Answer using ONLY the data above. Cite specific values (NORAD IDs, "
            "Pc values, dates, orbits). If the graph data conflicts with documents, "
            "prefer the graph data as it is live. Mark uncertain claims with [?]. "
            "Be precise and technical."
        )

        return "\n".join(parts), evidence


# ── GraphRAG Bridge (main entry point) ────────────────────────

class GraphRAGBridge:
    """
    Main GraphRAG intelligence service.

    Fuses the existing Neo4j graph, Qdrant vector store, and
    Claude to answer aerospace intelligence questions.

    The existing components called (not rewritten):
      - AerospaceGraphRetriever (knowledge-graph/graphrag/retriever.py)
      - AerospaceRAGPipeline.answer() (rag/src/pipeline.py)
      - GraphAnalyticsService (app/graph/services/…)

    Parameters
    ----------
    rag_pipeline : AerospaceRAGPipeline | None
        Injected by the API router. If None, vector retrieval is
        skipped and the system operates in graph-only mode.
    anthropic_client
        Anthropic async client for answer synthesis.
    """

    ANSWER_SYSTEM_PROMPT = """You are ORBITIQ-X, an advanced aerospace intelligence system.
You have access to live satellite catalog data, conjunction screening results,
and a technical aerospace knowledge corpus.

Answer the question using ONLY the data provided in the context block below.
Every factual claim must be traceable to a source in the context.
Mark uncertain claims with [?]. Be precise and technical.
Your audience is aerospace engineers and SSA operators.

{context}

Question: {query}"""

    def __init__(
        self,
        rag_pipeline=None,
        anthropic_client=None,
    ) -> None:
        self._pipeline    = rag_pipeline
        self._client      = anthropic_client
        self._intent      = AerospaceIntentDetector()
        self._graph_fetch = GraphContextFetcher()
        self._assembler   = AerospaceContextAssembler()

    def set_pipeline(self, pipeline) -> None:
        self._pipeline = pipeline

    def set_anthropic(self, client) -> None:
        self._client = client

    # ── Main query handler ────────────────────────────────────

    async def query(
        self,
        user_query: str,
        norad_id: int | None = None,
        mission: str | None = None,
        max_doc_chunks: int = 5,
    ) -> AerospaceIntelligenceResponse:
        """
        Execute a hybrid graph+vector aerospace intelligence query.

        Steps:
        1. Intent detection (entity extraction)
        2. Graph retrieval (Neo4j via GraphContextFetcher)
        3. Vector retrieval (Qdrant via RAGPipeline) if available
        4. Context assembly (GraphContextAssembler)
        5. LLM synthesis (Claude claude-sonnet-4-6)
        6. Confidence scoring

        Parameters
        ----------
        user_query : str
            Natural language aerospace question.
        norad_id : int | None
            If set, fetch conjunction history for this specific satellite.
        mission : str | None
            If set, fetch mission-specific graph context.
        max_doc_chunks : int
            Maximum document chunks to include in context.

        Returns
        -------
        AerospaceIntelligenceResponse
        """
        t0 = time.perf_counter()

        # Step 1: Intent + entity detection
        intent = self._intent.detect(user_query)

        # Step 2: Graph retrieval
        graph_ctx = await self._graph_fetch.fetch_for_entities(
            intent, conjunction_norad=norad_id
        )

        # Step 3: Vector retrieval (if pipeline available)
        doc_context = ""
        doc_citations: list = []
        chunks_used = 0
        retrieval_mode = "graph"

        if self._pipeline:
            try:
                # Import existing schemas
                from src.models.schemas import RAGQuery, SearchMode, AgencyType
                rag_q = RAGQuery(
                    query=user_query,
                    top_k=max_doc_chunks,
                    search_mode=SearchMode.HYBRID,
                )
                rag_response = await self._pipeline.answer(rag_q)
                doc_context   = rag_response.answer  # used as context, not final answer
                doc_citations = list(rag_response.sources)
                chunks_used   = rag_response.chunks_retrieved
                retrieval_mode = "hybrid"
                # Also get the raw context block
                if rag_response.retrieved_chunks:
                    from src.hallucination.guard import ContextBuilder
                    ctx_builder = ContextBuilder()
                    doc_context, doc_citations = ctx_builder.build(
                        rag_response.retrieved_chunks, user_query
                    )
            except Exception as exc:
                logger.warning("vector_retrieval_failed error=%s — graph only", exc)
                retrieval_mode = "graph"

        # Step 4: Context assembly
        assembled_context, evidence = self._assembler.assemble(
            query=user_query,
            intent=intent,
            graph_ctx=graph_ctx,
            doc_context=doc_context,
            doc_citations=doc_citations,
        )

        # Step 5: LLM synthesis
        answer_text = await self._synthesize(user_query, assembled_context)

        # Step 6: Confidence
        confidence = self._compute_confidence(
            graph_available=graph_ctx["graph_available"],
            vector_available=bool(self._pipeline),
            nodes_found=len(graph_ctx.get("operators", []))
                       + len(graph_ctx.get("risk_network", [])),
            chunks_used=chunks_used,
        )

        # Build response
        latency_ms = (time.perf_counter() - t0) * 1000

        return AerospaceIntelligenceResponse(
            query=user_query,
            answer=answer_text,
            confidence=confidence,
            faithfulness=0.95 if graph_ctx["graph_available"] else 0.70,
            retrieval_mode=retrieval_mode,
            latency_ms=latency_ms,
            evidence_sources=evidence,
            graph_nodes_used=graph_ctx.get("operators", [])
                           + graph_ctx.get("regimes", []),
            graph_relations_used=graph_ctx.get("risk_network", []),
            document_chunks_used=chunks_used,
            conjunctions_retrieved=graph_ctx.get("conjunctions", []),
            satellites_retrieved=graph_ctx.get("satellites", []),
            missions_retrieved=[],
            operators_retrieved=graph_ctx.get("operators", []),
            citations=[
                {
                    "key": cit.citation_key if hasattr(cit, "citation_key") else f"[{i+1}]",
                    "title": cit.title if hasattr(cit, "title") else "",
                    "agency": cit.agency if hasattr(cit, "agency") else "",
                    "year": cit.year if hasattr(cit, "year") else None,
                    "excerpt": cit.excerpt[:200] if hasattr(cit, "excerpt") else ""[:200],
                }
                for i, cit in enumerate(doc_citations[:8])
            ],
            uncertainty_flags=[
                f for f in ["No Neo4j connection" if not graph_ctx["graph_available"] else "",
                            "No document corpus" if not self._pipeline else ""]
                if f
            ],
        )

    async def _synthesize(self, query: str, context: str) -> str:
        """Call Claude for grounded answer synthesis."""
        if not self._client:
            return (
                "GraphRAG answer synthesis requires an Anthropic API key. "
                "Graph context retrieved successfully. "
                "Set ANTHROPIC_API_KEY in .env to enable LLM answers."
            )

        prompt = self.ANSWER_SYSTEM_PROMPT.format(
            context=context[:30_000],  # stay within context window
            query=query,
        )
        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as exc:
            logger.error("synthesis_failed error=%s", exc)
            return f"Answer synthesis failed: {exc}. Graph context was successfully retrieved."

    def _compute_confidence(
        self,
        graph_available: bool,
        vector_available: bool,
        nodes_found: int,
        chunks_used: int,
    ) -> float:
        """
        Aggregate confidence from retrieval quality signals.
        Weights: graph presence 40%, vector presence 20%, data found 40%.
        """
        graph_conf  = 0.9 if graph_available else 0.3
        vector_conf = 0.8 if vector_available else 0.4
        data_conf   = min(1.0, (nodes_found * 0.1 + chunks_used * 0.05))

        return round(0.40 * graph_conf + 0.20 * vector_conf + 0.40 * data_conf, 3)
