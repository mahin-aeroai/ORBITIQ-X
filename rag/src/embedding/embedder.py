"""
ORBITIQ-X Aerospace RAG
Embedding Strategy — BGE-M3 + Aerospace NER

BGE-M3 (BAAI/bge-m3) is the backbone embedding model:
  - 1024-dim dense vectors (cosine similarity)
  - Native sparse vector output (BM25-like SPLADE weights)
  - 8192 token context window — handles long aerospace passages
  - Multilingual: English + French/German ESA docs
  - Outperforms OpenAI text-embedding-3 on technical retrieval (BEIR)

Embedding Pipeline:
  text → BGE-M3 → { dense_vector[1024], sparse_vector{token_id: weight} }

Aerospace NER extracts structured entities for metadata filtering:
  - Satellite names:    ISS, CARTOSAT-3, Starlink-2145
  - Mission names:      Apollo 11, Chandrayaan-3, Mars Science Laboratory
  - Launch vehicles:    PSLV-C50, Falcon 9, Ariane 5
  - Orbit descriptors:  LEO 550km 53°, SSO 509km
  - Numeric values:     408 km, Pc = 1.2×10⁻³, Isp = 311 s

Batch strategy:
  - GPU: batch_size=64 (A100), 32 (T4)
  - CPU: batch_size=8, normalize_embeddings=True
  - Async ingestion: embed while chunking via asyncio.Queue
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..models.schemas import DocumentChunk

logger = logging.getLogger(__name__)

# ── BGE-M3 Embedder ───────────────────────────────────────────

class BGEM3Embedder:
    """
    Wrapper around BAAI/bge-m3 for dual dense+sparse embedding.

    Install: pip install FlagEmbedding sentence-transformers

    BGE-M3 outputs three types via FlagModel:
      dense_vecs:   L2-normalized 1024-dim float32
      sparse_vecs:  dict {token_id: weight} (SPLADE-like)
      colbert_vecs: late interaction (not used in this pipeline)
    """

    MODEL_ID   = "BAAI/bge-m3"
    DENSE_DIM  = 1024
    MAX_TOKENS = 8192

    def __init__(
        self,
        device: str = "cpu",
        batch_size: int = 8,
        use_fp16: bool = False,
    ):
        self.device = device
        self.batch_size = batch_size
        self.use_fp16 = use_fp16
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from FlagEmbedding import BGEM3FlagModel
            self._model = BGEM3FlagModel(
                self.MODEL_ID,
                use_fp16=self.use_fp16,
            )
            logger.info(f"BGE-M3 loaded on {self.device}")
        except ImportError:
            raise ImportError(
                "Install FlagEmbedding: pip install FlagEmbedding"
            )

    def embed_texts(
        self,
        texts: list[str],
        return_sparse: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Embed a list of texts. Returns list of:
          { 'dense': np.ndarray[1024], 'sparse': dict[int, float] }
        """
        self._load_model()
        results = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            # Truncate to max tokens
            batch = [t[:self.MAX_TOKENS * 4] for t in batch]  # char approx

            output = self._model.encode(
                batch,
                batch_size=len(batch),
                max_length=self.MAX_TOKENS,
                return_dense=True,
                return_sparse=return_sparse,
                return_colbert_vecs=False,
            )

            for j in range(len(batch)):
                dense = output["dense_vecs"][j]
                sparse = {}
                if return_sparse and "lexical_weights" in output:
                    raw_sparse = output["lexical_weights"][j]
                    # Normalize sparse weights to [0, 1]
                    if raw_sparse:
                        max_w = max(raw_sparse.values())
                        if max_w > 0:
                            sparse = {int(k): float(v / max_w)
                                      for k, v in raw_sparse.items()}

                results.append({
                    "dense": np.array(dense, dtype=np.float32),
                    "sparse": sparse,
                })

            logger.debug(f"Embedded batch {i//self.batch_size + 1}: {len(batch)} texts")

        return results

    def embed_query(self, query: str) -> dict[str, Any]:
        """
        Embed a single query with BGE-M3 query prefix.
        BGE-M3 uses "Represent this sentence for searching relevant passages: "
        prefix for queries vs documents — important for retrieval quality.
        """
        prefixed = f"Represent this sentence for searching relevant passages: {query}"
        return self.embed_texts([prefixed], return_sparse=True)[0]

    def embed_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """
        Embed all chunks, attaching dense + sparse vectors.
        Returns enriched chunks ready for Qdrant upsert.
        """
        texts = [c.text for c in chunks]
        embeddings = self.embed_texts(texts, return_sparse=True)

        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb["dense"].tolist()
            chunk.sparse_embedding = emb["sparse"]

        return chunks


# ── HyDE (Hypothetical Document Embedding) ───────────────────

class HyDEQueryExpander:
    """
    Generate a hypothetical answer to improve retrieval recall.

    Instead of embedding the raw query "What is the Foster Pc formula?",
    we first ask Claude to generate a short hypothetical paragraph that
    an aerospace paper might contain, then embed THAT paragraph.

    This bridges the vocabulary gap between question phrasing and
    technical document language.

    Reference:
      Gao et al. (2022). "Precise Zero-Shot Dense Retrieval without
      Relevance Labels." arXiv:2212.10496
    """

    SYSTEM_PROMPT = """You are an aerospace engineering document writer.
Given a question, write a 2-3 sentence technical passage that would appear
in a NASA/ESA technical report answering that question. Use precise
aerospace terminology, include relevant formulas or parameter names
where appropriate. Write as if excerpted from the document itself,
not as a direct answer.

Question: {query}

Write the technical passage (no preamble, just the passage):"""

    def __init__(self, anthropic_client, embedder: BGEM3Embedder):
        self.client = anthropic_client
        self.embedder = embedder

    async def expand(self, query: str) -> tuple[dict, str]:
        """
        Returns (embedding_of_hypothesis, hypothetical_text).
        Falls back to direct query embedding on error.
        """
        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": self.SYSTEM_PROMPT.format(query=query),
                }],
            )
            hypothesis = response.content[0].text.strip()
            embedding = self.embedder.embed_query(hypothesis)
            logger.debug(f"HyDE hypothesis: {hypothesis[:100]}...")
            return embedding, hypothesis
        except Exception as e:
            logger.warning(f"HyDE expansion failed ({e}), using direct query")
            return self.embedder.embed_query(query), query


# ── Aerospace NER ─────────────────────────────────────────────

@dataclass
class AerospaceEntities:
    satellites: list[str]
    missions: list[str]
    launch_vehicles: list[str]
    orbit_descriptors: list[str]
    numeric_values: list[str]
    organizations: list[str]
    topic_tags: list[str]


class AerospaceNER:
    """
    Rule-based + pattern-matching Named Entity Recognition
    for aerospace technical documents.

    Extracts entities used to populate ChunkMetadata for
    precise metadata filtering during retrieval.

    In production, augment with a fine-tuned SpaCy model
    trained on aerospace corpora.
    """

    # Satellite/spacecraft name patterns
    SATELLITE_RE = re.compile(
        r'\b(?:'
        r'ISS|Starlink-\d+|OneWeb-\d+'
        r'|CARTOSAT-\d+|RESOURCESAT-\d+|RISAT-\d+'
        r'|Sentinel-\d+[A-Z]?|MetOp-[A-C]'
        r'|GPS\s+(?:IIF|IIIA?)-\d+'
        r'|Inmarsat-\d+[A-Z]?|Iridium-\d+'
        r'|Hubble Space Telescope|HST'
        r'|James Webb Space Telescope|JWST'
        r'|[A-Z]{2,6}-\d{1,2}[A-Z]?'  # generic pattern: ABC-12
        r')',
        re.IGNORECASE,
    )

    # Mission name patterns
    MISSION_RE = re.compile(
        r'\b(?:'
        r'Apollo\s+\d+|Artemis\s+(?:I{1,3}|\d+)'
        r'|Mars\s+(?:Science Laboratory|Perseverance|Curiosity|Ingenuity)'
        r'|Chandrayaan-\d+|Mangalyaan|Gaganyaan'
        r'|Rosetta|BepiColombo|Solar Orbiter|Parker Solar Probe'
        r'|Voyager\s+[12]|Pioneer\s+(?:10|11)'
        r'|New Horizons|Cassini|Juno|Dawn'
        r'|(?:PSLV|GSLV|Ariane|Falcon|Atlas|Delta|Vulcan|SLS)-C?\d+'
        r')',
        re.IGNORECASE,
    )

    # Launch vehicle patterns
    LV_RE = re.compile(
        r'\b(?:'
        r'PSLV(?:-C\d+|-XL|-G|-CA)?'
        r'|GSLV(?:\s+Mk\s*(?:II|III))?'
        r'|LVM3|SLV|ASLV'
        r'|Falcon\s+(?:9|Heavy|1)'
        r'|Starship|New\s+Shepard|New\s+Glenn'
        r'|Ariane\s+(?:5|6|62|64)'
        r'|Atlas\s+V|Delta\s+IV(?:\s+Heavy)?|Vulcan'
        r'|Space\s+Launch\s+System|SLS'
        r'|Soyuz-\d+\.\d+|Proton-[MK]'
        r'|H-II[AB]?|Epsilon|H3'
        r'|Long\s+March\s*-?\d+'
        r')',
        re.IGNORECASE,
    )

    # Orbit descriptors: "550 km SSO", "408 km ISS orbit", "GEO belt"
    ORBIT_RE = re.compile(
        r'\b(?:'
        r'\d+(?:\.\d+)?\s*km\s+(?:LEO|MEO|GEO|SSO|HEO|VLEO)'
        r'|(?:LEO|MEO|GEO|SSO|HEO|VLEO|GTO|TLI)\s+orbit'
        r'|\d+(?:\.\d+)?°?\s+inclination'
        r'|geostationary(?:\s+orbit)?'
        r'|sun-synchronous(?:\s+orbit)?'
        r'|Molniya\s+orbit|Tundra\s+orbit'
        r')',
        re.IGNORECASE,
    )

    # Numeric aerospace values
    NUMERIC_RE = re.compile(
        r'\b(?:'
        r'\d+(?:\.\d+)?\s*(?:km|km/s|m/s|deg|°|kg|kN|kW|MHz|GHz|yr|days?)'
        r'|Isp\s*=\s*\d+\s*s'
        r'|Pc\s*[=≈]\s*[\d.]+(?:×10[⁻-]\d+)?'
        r'|ΔV\s*=\s*[\d.]+\s*m/s'
        r'|e\s*=\s*[\d.]{3,}'      # eccentricity
        r'|i\s*=\s*[\d.]+°'        # inclination
        r')',
    )

    # Topic tags — keywords mapped to domain tags
    TOPIC_KEYWORDS = {
        "orbital_mechanics":    ["sgp4", "kepler", "propagat", "mean motion",
                                  "eccentricity", "inclination", "RAAN"],
        "conjunction_analysis": ["conjunction", "collision probab", "Foster",
                                  "miss distance", "TCA", "CDM", "Pc"],
        "debris_mitigation":    ["debris", "deorbit", "mitigation", "IADC",
                                  "end-of-life", "passivation", "fragmentation"],
        "propulsion":           ["thrust", "Isp", "propellant", "delta-v",
                                  "specific impulse", "burn"],
        "attitude_control":     ["attitude", "ADCS", "reaction wheel", "momentum",
                                  "pointing", "star tracker"],
        "thermal_control":      ["thermal", "heat pipe", "radiator", "MLI",
                                  "temperature", "thermal control"],
        "launch_vehicle":       ["launch vehicle", "rocket", "stage", "fairing",
                                  "payload adapter", "trajectory"],
        "ground_segment":       ["ground station", "telemetry", "command",
                                  "LEOP", "pass", "AOS", "LOS"],
        "space_weather":        ["solar flare", "geomagnetic", "Kp index",
                                  "F10.7", "radiation", "storm"],
        "reentry":              ["reentry", "decay", "atmospheric drag",
                                  "deorbit", "fragmentation event"],
    }

    def extract(self, text: str) -> AerospaceEntities:
        """Extract all aerospace entities from chunk text."""
        satellites     = list(set(self.SATELLITE_RE.findall(text)))[:10]
        missions       = list(set(self.MISSION_RE.findall(text)))[:10]
        launch_vehicles = list(set(self.LV_RE.findall(text)))[:5]
        orbit_descs    = list(set(self.ORBIT_RE.findall(text)))[:5]
        numeric_vals   = list(set(self.NUMERIC_RE.findall(text)))[:15]

        # Organizations: simple acronym detection
        org_re = re.compile(r'\b(NASA|ESA|ISRO|JAXA|CNSA|ROSCOSMOS|SpaceX|Boeing|'
                             r'Airbus Defence|Northrop Grumman|Lockheed Martin|'
                             r'18 SWS|CARA|USSPACECOM)\b')
        organizations = list(set(org_re.findall(text)))[:8]

        # Topic tags
        text_lower = text.lower()
        topic_tags = [
            tag for tag, keywords in self.TOPIC_KEYWORDS.items()
            if any(kw in text_lower for kw in keywords)
        ]

        return AerospaceEntities(
            satellites=satellites,
            missions=missions,
            launch_vehicles=launch_vehicles,
            orbit_descriptors=orbit_descs,
            numeric_values=numeric_vals,
            organizations=organizations,
            topic_tags=topic_tags,
        )

    def enrich_chunk(self, chunk: DocumentChunk) -> DocumentChunk:
        """Attach extracted entities to chunk metadata."""
        entities = self.extract(chunk.text)
        chunk.metadata.entities_satellite  = entities.satellites
        chunk.metadata.entities_mission    = entities.missions
        chunk.metadata.entities_vehicle    = entities.launch_vehicles
        chunk.metadata.entities_orbit      = entities.orbit_descriptors
        chunk.metadata.entities_numeric    = entities.numeric_values
        chunk.metadata.topic_tags          = list(set(
            chunk.metadata.topic_tags + entities.topic_tags
        ))
        return chunk


# ── Acronym expander ──────────────────────────────────────────

AEROSPACE_ACRONYMS: dict[str, str] = {
    "LEO":  "Low Earth Orbit",
    "GEO":  "Geostationary Orbit",
    "MEO":  "Medium Earth Orbit",
    "SSO":  "Sun-Synchronous Orbit",
    "HEO":  "Highly Elliptical Orbit",
    "GTO":  "Geostationary Transfer Orbit",
    "TLI":  "Trans-Lunar Injection",
    "TCA":  "Time of Closest Approach",
    "CDM":  "Conjunction Data Message",
    "NORAD": "North American Aerospace Defense Command",
    "TLE":  "Two-Line Element Set",
    "RAAN": "Right Ascension of Ascending Node",
    "SGP4": "Simplified General Perturbations 4",
    "ADCS": "Attitude Determination and Control System",
    "EPS":  "Electrical Power System",
    "OBC":  "On-Board Computer",
    "LEOP": "Launch and Early Orbit Phase",
    "AOS":  "Acquisition of Signal",
    "LOS":  "Loss of Signal",
    "NTRS": "NASA Technical Reports Server",
    "IADC": "Inter-Agency Space Debris Coordination Committee",
    "ECSS": "European Cooperation for Space Standardization",
    "BSTAR": "Drag Term in SGP4 (ballistic coefficient)",
    "Pc":   "Collision Probability",
    "HBR":  "Hard Body Radius",
    "RTN":  "Radial-Transverse-Normal frame",
    "LVLH": "Local Vertical Local Horizontal frame",
}


def expand_query_acronyms(query: str) -> str:
    """
    Expand aerospace acronyms in query to improve BM25 sparse recall.
    "What is the Pc for LEO conjunction?" →
    "What is the Collision Probability for Low Earth Orbit conjunction?"
    """
    expanded = query
    for acronym, expansion in AEROSPACE_ACRONYMS.items():
        pattern = r'\b' + re.escape(acronym) + r'\b'
        if re.search(pattern, expanded):
            expanded = re.sub(pattern, f"{acronym} ({expansion})", expanded, count=1)
    return expanded
