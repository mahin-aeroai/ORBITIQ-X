"""
ORBITIQ-X — Foundation Model Service
======================================
Phase 8: FoundationModelService — routes queries to the appropriate
model tier and enforces graph grounding + citation requirements.

Model tiers
────────────
  Tier 1 — Baseline:    Claude API without augmentation (no graph/RAG)
  Tier 2 — GraphRAG:    Claude + Neo4j graph + Qdrant corpus (existing system)
  Tier 3 — Agent:       Full 7-agent LangGraph system (existing system)
  Tier 4 — Fine-tuned:  Future aerospace-specific fine-tuned model

Routing logic
─────────────
  Simple factual queries  → Tier 1 (fast, low cost)
  Graph-requiring queries → Tier 2 (GraphRAG, grounded)
  Multi-domain queries    → Tier 3 (agents, complex reasoning)
  Custom model endpoint   → Tier 4 (when deployed)

Audit notes
───────────
  - Calls existing GraphRAGBridge.query() for Tier 2
  - Calls existing AgentOrchestrationService for Tier 3
  - Does NOT rewrite any existing service
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    BASELINE = "baseline"     # Tier 1: LLM only
    GRAPHRAG = "graphrag"     # Tier 2: GraphRAG (existing)
    AGENT    = "agent"        # Tier 3: Multi-agent (existing)
    CUSTOM   = "custom"       # Tier 4: Fine-tuned endpoint


@dataclass
class FoundationModelResponse:
    """Unified response from any model tier."""
    query:            str
    answer:           str
    model_tier:       ModelTier
    model_id:         str
    confidence:       float = 0.0
    faithfulness:     float = 0.0
    latency_ms:       float = 0.0

    # Grounding evidence
    graph_nodes_used: int = 0
    doc_chunks_used:  int = 0
    citations:        list[dict] = field(default_factory=list)
    evidence_sources: list[dict] = field(default_factory=list)
    safety_flags:     list[str] = field(default_factory=list)

    # Routing metadata
    agents_invoked:   list[str] = field(default_factory=list)
    reasoning_trace:  list[str] = field(default_factory=list)
    retrieval_mode:   str = "none"

    def to_dict(self) -> dict:
        return {
            "query":           self.query,
            "answer":          self.answer,
            "model_tier":      self.model_tier.value,
            "model_id":        self.model_id,
            "confidence":      round(self.confidence, 4),
            "faithfulness":    round(self.faithfulness, 4),
            "latency_ms":      round(self.latency_ms, 1),
            "grounding": {
                "graph_nodes":  self.graph_nodes_used,
                "doc_chunks":   self.doc_chunks_used,
                "citations":    len(self.citations),
            },
            "citations":       self.citations[:5],
            "safety_flags":    self.safety_flags,
            "agents_invoked":  self.agents_invoked,
            "retrieval_mode":  self.retrieval_mode,
        }


class FoundationModelService:
    """
    Unified inference service routing queries to the appropriate model tier.

    Existing services called (not rewritten):
      Tier 2: app.services.graphrag.graphrag_bridge.GraphRAGBridge
      Tier 3: app.services.agent_service.AgentOrchestrationService

    Parameters
    ----------
    anthropic_client : optional
        AsyncAnthropic client for Tier 1 and Tier 2.
    graphrag_bridge : optional
        Injected GraphRAGBridge for Tier 2.
    agent_service : optional
        Injected AgentOrchestrationService for Tier 3.
    custom_endpoint : str | None
        HTTP endpoint for Tier 4 fine-tuned model.
    """

    def __init__(
        self,
        anthropic_client=None,
        graphrag_bridge=None,
        agent_service=None,
        custom_endpoint: str | None = None,
    ) -> None:
        self._client    = anthropic_client
        self._graphrag  = graphrag_bridge
        self._agents    = agent_service
        self._custom    = custom_endpoint

    # ── Tier routing ──────────────────────────────────────────

    def select_tier(self, query: str, preferred_tier: ModelTier | None = None) -> ModelTier:
        """
        Auto-select the appropriate model tier for a query.

        Logic:
          - If preferred_tier is set, use it
          - Queries needing real-time data → Tier 2 or 3
          - Multi-domain complex queries → Tier 3
          - Simple factual queries → Tier 1
        """
        if preferred_tier:
            return preferred_tier

        q = query.lower()

        # Multi-domain or complex reasoning → agents
        if any(w in q for w in ("which satellites", "compare", "all operators", "risk ranking")):
            return ModelTier.AGENT

        # Graph-requiring queries → GraphRAG
        if any(w in q for w in ("conjunction", "cdm", "norad", "operator", "constellation",
                                 "starlink", "isro", "esa", "nasa", "pslv")):
            return ModelTier.GRAPHRAG

        # Research / document queries → GraphRAG (has corpus)
        if any(w in q for w in ("explain", "summarize", "describe", "standard", "method")):
            return ModelTier.GRAPHRAG

        return ModelTier.BASELINE

    # ── Main inference ────────────────────────────────────────

    async def query(
        self,
        question: str,
        tier: ModelTier | None = None,
        model_id: str | None = None,
    ) -> FoundationModelResponse:
        """
        Route and execute an aerospace intelligence query.

        Parameters
        ----------
        question : str
            Natural language aerospace question.
        tier : ModelTier | None
            Force a specific tier. Auto-selects if None.
        model_id : str | None
            Specific model ID to use (for Tier 4).
        """
        selected_tier = self.select_tier(question, tier)
        t0 = time.perf_counter()

        if selected_tier == ModelTier.AGENT and self._agents:
            resp = await self._query_agents(question)
        elif selected_tier in (ModelTier.GRAPHRAG, ModelTier.AGENT) and self._graphrag:
            resp = await self._query_graphrag(question)
        elif selected_tier == ModelTier.CUSTOM and self._custom:
            resp = await self._query_custom(question, model_id)
        else:
            resp = await self._query_baseline(question)

        resp.latency_ms = (time.perf_counter() - t0) * 1000
        return resp

    async def _query_baseline(self, question: str) -> FoundationModelResponse:
        """Tier 1: Direct LLM query without augmentation."""
        if not self._client:
            return FoundationModelResponse(
                query=question, answer="Anthropic API key not configured.",
                model_tier=ModelTier.BASELINE, model_id="claude-sonnet-4-6",
                confidence=0.0,
            )
        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": question}],
            )
            return FoundationModelResponse(
                query=question,
                answer=response.content[0].text,
                model_tier=ModelTier.BASELINE,
                model_id="claude-sonnet-4-6",
                confidence=0.6,  # no grounding → lower confidence
                retrieval_mode="none",
            )
        except Exception as exc:
            logger.error("baseline_query_failed error=%s", exc)
            return FoundationModelResponse(
                query=question, answer=f"Query failed: {exc}",
                model_tier=ModelTier.BASELINE, model_id="claude-sonnet-4-6",
            )

    async def _query_graphrag(self, question: str) -> FoundationModelResponse:
        """Tier 2: GraphRAG — graph + vector + LLM."""
        try:
            bridge_response = await self._graphrag.query(question)
            return FoundationModelResponse(
                query=question,
                answer=bridge_response.answer,
                model_tier=ModelTier.GRAPHRAG,
                model_id="claude-sonnet-4-6+graphrag",
                confidence=bridge_response.confidence,
                faithfulness=bridge_response.faithfulness,
                graph_nodes_used=len(bridge_response.graph_nodes_used),
                doc_chunks_used=bridge_response.document_chunks_used,
                citations=bridge_response.citations,
                evidence_sources=[
                    {"type": e.source_type, "title": e.title, "relevance": e.relevance}
                    for e in bridge_response.evidence_sources[:5]
                ],
                retrieval_mode=bridge_response.retrieval_mode,
            )
        except Exception as exc:
            logger.error("graphrag_query_failed error=%s", exc)
            return await self._query_baseline(question)

    async def _query_agents(self, question: str) -> FoundationModelResponse:
        """Tier 3: Full multi-agent system."""
        try:
            from app.schemas.agents import TaskSubmitRequest, TaskType
            import asyncio, uuid as _uuid

            req     = TaskSubmitRequest(query=question, task_type=TaskType.QUERY)
            task_id = await self._agents.submit_task(req)

            # Poll for completion (max 60s)
            for _ in range(120):
                task = await self._agents.get_task(task_id)
                if task and task.status.value in ("complete", "failed"):
                    break
                await asyncio.sleep(0.5)

            if task and task.final_answer:
                return FoundationModelResponse(
                    query=question,
                    answer=task.final_answer,
                    model_tier=ModelTier.AGENT,
                    model_id="claude-sonnet-4-6+agents",
                    confidence=task.confidence or 0.0,
                    agents_invoked=task.agents_invoked,
                    safety_flags=task.safety_flags,
                    citations=[
                        {"title": e.title, "type": e.source_type}
                        for e in task.cited_sources[:5]
                    ],
                    retrieval_mode="multi-agent",
                )
        except Exception as exc:
            logger.error("agent_query_failed error=%s", exc)

        return await self._query_graphrag(question)

    async def _query_custom(self, question: str, model_id: str | None) -> FoundationModelResponse:
        """Tier 4: Custom fine-tuned model endpoint."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self._custom + "/generate",
                    json={"prompt": question, "max_tokens": 2048},
                )
                resp.raise_for_status()
                data = resp.json()
                return FoundationModelResponse(
                    query=question,
                    answer=data.get("text", data.get("output", "")),
                    model_tier=ModelTier.CUSTOM,
                    model_id=model_id or "custom-aerospace-model",
                    confidence=data.get("confidence", 0.8),
                    retrieval_mode="custom",
                )
        except Exception as exc:
            logger.error("custom_model_query_failed error=%s", exc)
            return await self._query_graphrag(question)
