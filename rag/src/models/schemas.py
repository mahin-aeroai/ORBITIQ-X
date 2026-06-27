"""
ORBITIQ-X Aerospace RAG — Data Schemas
=======================================
Shared dataclasses and enums used across the RAG pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class AgencyType(str, Enum):
    NASA      = "NASA"
    ESA       = "ESA"
    ISRO      = "ISRO"
    JAXA      = "JAXA"
    ROSCOSMOS = "ROSCOSMOS"
    SPACEX    = "SpaceX"
    CNSA      = "CNSA"
    OTHER     = "OTHER"


class DocumentType(str, Enum):
    TECHNICAL_REPORT  = "technical_report"
    JOURNAL_ARTICLE   = "journal_article"
    CONFERENCE_PAPER  = "conference_paper"
    STANDARD          = "standard"
    STANDARDS_DOC     = "standards_doc"
    HANDBOOK          = "handbook"
    RESEARCH_PAPER    = "research_paper"
    MISSION_REPORT    = "mission_report"
    OPERATOR_MANUAL   = "operator_manual"
    TEXTBOOK          = "textbook"
    DEBRIS_STUDY      = "debris_study"
    UNKNOWN           = "unknown"
    OTHER             = "other"


class ContentType(str, Enum):
    TEXT       = "text"
    TABLE      = "table"
    EQUATION   = "equation"
    FIGURE     = "figure"
    CODE       = "code"
    ABSTRACT   = "abstract"
    CONCLUSION = "conclusion"


class SearchMode(str, Enum):
    DENSE   = "dense"
    SPARSE  = "sparse"
    HYBRID  = "hybrid"


# ── Document metadata ─────────────────────────────────────────────────────────

@dataclass
class DocumentMetadata:
    title:            str             = ""
    agency:           AgencyType      = AgencyType.OTHER
    doc_type:         DocumentType    = DocumentType.OTHER
    publication_year: Optional[int]   = None
    source_url:       Optional[str]   = None
    doc_id:           Optional[str]   = None
    report_number:    Optional[str]   = None
    topic_tags:       list[str]       = field(default_factory=list)
    peer_reviewed:    bool            = False
    has_equations:    bool            = False


# ── Chunk types ───────────────────────────────────────────────────────────────

@dataclass
class ChunkMetadata:
    doc_id:           str
    chunk_index:      int
    section_title:    str             = ""
    content_type:     ContentType     = ContentType.TEXT
    agency:           AgencyType      = AgencyType.OTHER
    doc_type:         DocumentType    = DocumentType.OTHER
    publication_year: Optional[int]   = None
    topic_tags:       list[str]       = field(default_factory=list)
    peer_reviewed:    bool            = False
    has_equations:    bool            = False
    source_url:       Optional[str]   = None
    doc_title:        str             = ""
    authors:          list[str]       = field(default_factory=list)
    page_start:       Optional[int]   = None
    page_end:         Optional[int]   = None


@dataclass
class DocumentChunk:
    chunk_id:     str
    text:         str
    metadata:     ChunkMetadata
    dense_vector: Optional[list[float]] = None
    sparse_vector: Optional[dict]       = None


@dataclass
class RetrievedChunk:
    chunk_id:      str
    text:          str
    metadata:      ChunkMetadata
    dense_score:   float         = 0.0
    sparse_score:  float         = 0.0
    final_score:   float         = 0.0
    citation_key:  str           = ""


# ── Query / Response ──────────────────────────────────────────────────────────

@dataclass
class RAGQuery:
    query:       str
    top_k:       int         = 10
    min_score:   float       = 0.65
    search_mode: SearchMode  = SearchMode.HYBRID
    filters:     dict        = field(default_factory=dict)


@dataclass
class CitationRecord:
    citation_key:      str
    doc_title:         str           = ""
    chunk_id:          str           = ""
    agency:            str           = ""
    doc_type:          str           = ""
    publication_year:  Optional[int] = None
    source_url:        Optional[str] = None
    relevance_score:   float         = 0.0
    excerpt:           str           = ""
    authors:           list[str]     = field(default_factory=list)
    title:             str           = ""
    doc_id:            str           = ""
    year:              Optional[int] = None


@dataclass
class RAGResponse:
    query:                str
    answer:               str
    confidence:           float             = 0.0
    faithfulness_score:   float             = 1.0
    sources:              list[CitationRecord] = field(default_factory=list)
    retrieved_chunks:     list[RetrievedChunk] = field(default_factory=list)
    hallucination_flags:  list[str]         = field(default_factory=list)
    uncertain_claims:     list[str]         = field(default_factory=list)
    search_mode_used:     str               = "hybrid"
    chunks_retrieved:     int               = 0
    chunks_after_rerank:  int               = 0
    latency_ms:           float             = 0.0


# ── Evaluation ────────────────────────────────────────────────────────────────

@dataclass
class EvalSample:
    query:          str
    expected:       str
    response:       Optional[RAGResponse] = None


@dataclass
class EvalMetrics:
    faithfulness:   float = 0.0
    relevance:      float = 0.0
    completeness:   float = 0.0
    latency_ms:     float = 0.0
    n_samples:      int   = 0
