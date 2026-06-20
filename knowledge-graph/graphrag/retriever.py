"""
ORBITIQ-X Aerospace Knowledge Graph
GraphRAG Integration Strategy

Architecture:
    User Query → Intent Classifier → Graph Retriever → Context Builder
              → Anthropic Claude → Grounded Response

Two retrieval modes:
    1. Structured   : Cypher query generation from NL → execute → format
    2. Vector       : Embed query → ANN search → graph traversal → context
    3. Hybrid       : Vector seeds → Cypher expansion → re-rank

All responses are grounded in KG facts — hallucination risk minimized.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic
from langchain_community.graphs import Neo4jGraph
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


# ── Context Objects ──────────────────────────────────────────

@dataclass
class GraphContext:
    """Structured context retrieved from Neo4j for a given query."""
    query: str
    retrieval_mode: str          # 'cypher' | 'vector' | 'hybrid'
    nodes: list[dict[str, Any]]
    relationships: list[dict]
    cypher_executed: str | None
    vector_hits: list[dict] | None
    raw_neo4j_results: list[dict]
    token_estimate: int = 0

    def to_prompt_block(self) -> str:
        """Render context as a structured block for the LLM prompt."""
        lines = [
            f"## Knowledge Graph Context",
            f"Query: {self.query}",
            f"Retrieval mode: {self.retrieval_mode}",
            "",
            "### Retrieved nodes",
        ]
        for node in self.nodes[:20]:
            lines.append(f"- [{node.get('labels', ['?'])[0]}] {json.dumps(node.get('props', {}), default=str)}")

        if self.relationships:
            lines += ["", "### Relationships"]
            for rel in self.relationships[:20]:
                lines.append(f"- ({rel['from']}) -[{rel['type']}]-> ({rel['to']})")

        if self.cypher_executed:
            lines += ["", f"### Cypher executed", f"```cypher\n{self.cypher_executed}\n```"]

        return "\n".join(lines)


# ── Query Classifier ─────────────────────────────────────────

INTENT_CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an aerospace query intent classifier for a Neo4j knowledge graph.
Classify the user query into one of these intent categories and output ONLY a JSON object.

Categories:
  satellite_lookup   : finding specific satellites by name/NORAD/operator/country/type
  conjunction_risk   : CDM events, collision probability, miss distance queries
  debris_analysis    : debris cloud, fragmentation events, orbital congestion
  launch_lineage     : launch vehicle → satellite → operator tracing
  space_weather      : Kp index, geomagnetic storm impact on orbits
  mission_search     : finding missions by type, status, organization
  research_discovery : paper lookup, citation networks
  graph_analytics    : PageRank, community detection, path queries
  general            : fallback for conversational / unclear queries

Output format:
{{
  "intent": "<category>",
  "entities": {{
    "satellite_name": null,
    "norad_id": null,
    "country_iso2": null,
    "operator": null,
    "constellation": null,
    "orbit_regime": null,
    "launch_vehicle": null,
    "time_range_hours": null
  }},
  "retrieval_mode": "cypher | vector | hybrid",
  "confidence": 0.0
}}"""),
    ("human", "{query}"),
])


# ── Cypher Generator ─────────────────────────────────────────

CYPHER_GENERATOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a Neo4j Cypher expert for an aerospace knowledge graph.

Graph schema summary:
  Nodes: Satellite, Constellation, Operator, Country, Organization, Mission,
         Orbit, LaunchVehicle, LaunchSite, DebrisObject, ConjunctionEvent,
         SpaceWeatherEvent, ResearchPaper

Key properties:
  Satellite: noradId (int), name, status, missionType, launchDate, altitudeKm
  ConjunctionEvent: tca (datetime), missDistanceKm, collisionProbability, riskLevel
  DebrisObject: noradId, regime, radarCrossSection, fragmentationEvent, riskCategory
  Country: iso2 (2-char code), name
  LaunchVehicle: vehicleId, name, family

Key relationships:
  (Satellite)-[:REGISTERED_IN]->(Country)
  (Satellite)-[:LAUNCHED_BY]->(LaunchVehicle)
  (Satellite)-[:OCCUPIES]->(Orbit)
  (Satellite)-[:MEMBER_OF]->(Constellation)
  (Satellite)-[:PRIMARY_IN]->(ConjunctionEvent)
  (DebrisObject)-[:SECONDARY_IN]->(ConjunctionEvent)
  (DebrisObject)-[:ORIGINATED_FROM]->(Satellite)
  (SpaceWeatherEvent)-[:AFFECTS]->(Orbit)
  (LaunchVehicle)-[:LAUNCHES_FROM]->(LaunchSite)

Rules:
- Use MERGE, not CREATE, for lookups
- Always add LIMIT (default 25)
- Use OPTIONAL MATCH for nullable relationships
- Return human-readable properties, not IDs
- Sort by most relevant field (date DESC, Pc DESC, etc.)
- Never use DETACH DELETE

Generate ONLY the Cypher query, no explanation."""),
    ("human", "Intent: {intent}\nEntities: {entities}\nUser query: {query}"),
])


# ── Graph Retriever ──────────────────────────────────────────

class AerospaceGraphRetriever:
    """
    Three-mode retriever:
      1. Cypher  : NL → Cypher → execute → results
      2. Vector  : embed query → ANN → expand subgraph
      3. Hybrid  : vector seeds + cypher traversal
    """

    def __init__(
        self,
        neo4j_driver: AsyncDriver,
        anthropic_client: AsyncAnthropic,
        openai_client=None,
    ):
        self.driver = neo4j_driver
        self.anthropic = anthropic_client
        self.openai = openai_client

        llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
        self.classifier = INTENT_CLASSIFIER_PROMPT | llm | StrOutputParser()
        self.cypher_gen = CYPHER_GENERATOR_PROMPT | llm | StrOutputParser()

    async def retrieve(self, query: str) -> GraphContext:
        """Main entry point — classify intent then route to retrieval mode."""
        # Step 1: classify
        raw_intent = await self.classifier.ainvoke({"query": query})
        try:
            intent_data = json.loads(raw_intent)
        except json.JSONDecodeError:
            intent_data = {"intent": "general", "retrieval_mode": "vector", "confidence": 0.3}

        mode = intent_data.get("retrieval_mode", "cypher")

        if mode == "cypher":
            return await self._cypher_retrieve(query, intent_data)
        elif mode == "vector":
            return await self._vector_retrieve(query)
        else:
            return await self._hybrid_retrieve(query, intent_data)

    async def _cypher_retrieve(self, query: str, intent: dict) -> GraphContext:
        """Generate and execute a Cypher query."""
        cypher = await self.cypher_gen.ainvoke({
            "intent": intent.get("intent"),
            "entities": json.dumps(intent.get("entities", {})),
            "query": query,
        })
        cypher = cypher.strip().strip("```cypher").strip("```").strip()

        async with self.driver.session() as session:
            result = await session.run(cypher)
            records = await result.data()

        nodes, rels = self._extract_nodes_rels(records)
        return GraphContext(
            query=query,
            retrieval_mode="cypher",
            nodes=nodes,
            relationships=rels,
            cypher_executed=cypher,
            vector_hits=None,
            raw_neo4j_results=records,
        )

    async def _vector_retrieve(self, query: str) -> GraphContext:
        """ANN vector search + 2-hop subgraph expansion."""
        embedding = await self._embed(query)

        vector_cypher = """
        CALL db.index.vector.queryNodes('satellite_embedding', 8, $embedding)
        YIELD node AS s, score
        MATCH (s)-[r]-(neighbor)
        WHERE score > 0.75
        RETURN s, r, neighbor, score
        ORDER BY score DESC
        """
        async with self.driver.session() as session:
            result = await session.run(vector_cypher, embedding=embedding)
            records = await result.data()

        nodes, rels = self._extract_nodes_rels(records)
        return GraphContext(
            query=query,
            retrieval_mode="vector",
            nodes=nodes,
            relationships=rels,
            cypher_executed=vector_cypher,
            vector_hits=[r for r in records if "score" in r],
            raw_neo4j_results=records,
        )

    async def _hybrid_retrieve(self, query: str, intent: dict) -> GraphContext:
        """
        1. Vector search to find seed nodes
        2. Extract NORADs / IDs from seed results
        3. Cypher traversal from those seeds
        """
        vector_ctx = await self._vector_retrieve(query)
        seed_norads = [
            n["props"].get("noradId")
            for n in vector_ctx.nodes
            if n["props"].get("noradId")
        ][:5]

        if not seed_norads:
            return vector_ctx

        expansion_cypher = """
        UNWIND $norads AS norad
        MATCH (s:Satellite {noradId: norad})
        OPTIONAL MATCH (s)-[:PRIMARY_IN]->(ce:ConjunctionEvent)
        OPTIONAL MATCH (s)-[:OCCUPIES]->(o:Orbit)
        OPTIONAL MATCH (s)-[:MEMBER_OF]->(c:Constellation)
        RETURN s, ce, o, c
        ORDER BY ce.collisionProbability DESC
        LIMIT 25
        """
        async with self.driver.session() as session:
            result = await session.run(expansion_cypher, norads=seed_norads)
            expansion = await result.data()

        all_records = vector_ctx.raw_neo4j_results + expansion
        nodes, rels = self._extract_nodes_rels(all_records)
        return GraphContext(
            query=query,
            retrieval_mode="hybrid",
            nodes=nodes,
            relationships=rels,
            cypher_executed=expansion_cypher,
            vector_hits=vector_ctx.vector_hits,
            raw_neo4j_results=all_records,
        )

    async def _embed(self, text: str) -> list[float]:
        if self.openai:
            resp = await self.openai.embeddings.create(
                model="text-embedding-3-large",
                input=text,
                dimensions=1536,
            )
            return resp.data[0].embedding
        return [0.0] * 1536  # fallback (no-op)

    @staticmethod
    def _extract_nodes_rels(records: list[dict]) -> tuple[list, list]:
        """Extract unique nodes and relationships from Neo4j result dicts."""
        seen_nodes: dict[str, dict] = {}
        rels = []
        for record in records:
            for key, val in record.items():
                if hasattr(val, "labels"):  # Neo4j Node
                    node_id = str(val.element_id)
                    if node_id not in seen_nodes:
                        seen_nodes[node_id] = {
                            "labels": list(val.labels),
                            "props": dict(val),
                        }
                elif hasattr(val, "type"):  # Neo4j Relationship
                    rels.append({
                        "type": val.type,
                        "from": str(val.start_node.element_id),
                        "to": str(val.end_node.element_id),
                        "props": dict(val),
                    })
        return list(seen_nodes.values()), rels


# ── Answer Synthesizer ────────────────────────────────────────

ANSWER_PROMPT = """You are ORBITIQ-X, an advanced aerospace intelligence assistant.
You have access to a real-time aerospace knowledge graph containing satellite catalogs,
orbital data, conjunction events, debris tracking, and space weather data.

Answer the user's question using ONLY the graph context provided below.
If the context doesn't contain enough information, say so clearly.
Always cite specific data (NORAD IDs, Pc values, dates, orbits) when available.
Be precise and technical — your audience is aerospace engineers and SSA professionals.

{graph_context}

User question: {query}"""


class GraphRAGAnswerer:
    """Synthesize answers from GraphContext using Claude."""

    def __init__(self, anthropic_client: AsyncAnthropic):
        self.client = anthropic_client

    async def answer(self, query: str, context: GraphContext) -> str:
        prompt = ANSWER_PROMPT.format(
            graph_context=context.to_prompt_block(),
            query=query,
        )
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def stream_answer(self, query: str, context: GraphContext):
        """Streaming version for real-time SSE delivery."""
        prompt = ANSWER_PROMPT.format(
            graph_context=context.to_prompt_block(),
            query=query,
        )
        async with self.client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text


# ── FastAPI Integration ───────────────────────────────────────

# Wired into backend/app/api/v1/endpoints/rag.py:
#
# @router.post("/query")
# async def graph_rag_query(req: GraphRAGRequest, ...):
#     retriever = AerospaceGraphRetriever(neo4j_driver, anthropic, openai)
#     context = await retriever.retrieve(req.query)
#     answerer = GraphRAGAnswerer(anthropic)
#     answer = await answerer.answer(req.query, context)
#     return {
#         "answer": answer,
#         "context_nodes": len(context.nodes),
#         "retrieval_mode": context.retrieval_mode,
#         "cypher": context.cypher_executed,
#     }
#
# @router.get("/query/stream")  (SSE)
# async def graph_rag_stream(query: str, ...):
#     retriever = AerospaceGraphRetriever(neo4j_driver, anthropic, openai)
#     context = await retriever.retrieve(query)
#     answerer = GraphRAGAnswerer(anthropic)
#     async def event_gen():
#         async for chunk in answerer.stream_answer(query, context):
#             yield f"data: {json.dumps({'chunk': chunk})}\n\n"
#     return EventSourceResponse(event_gen())
