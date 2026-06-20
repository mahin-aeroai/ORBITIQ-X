"""
ORBITIQ-X — Aerospace Corpus Service
=====================================
Manages the curated aerospace knowledge corpus.

Sources
───────
  NASA NTRS (Technical Reports Server) — ntrs.nasa.gov
  ESA Technical Notes                  — esamultimedia.esa.int
  ISRO Publications                    — isro.gov.in
  CCSDS Standards                      — ccsds.org
  Celestial Mechanics textbooks        — public domain
  Space debris research                — esa.int/Safety_Security
  Orbital mechanics references         — public domain
  Launch vehicle specifications        — manufacturer press kits

Audit notes
────────────
  - rag/src/ingestion/loaders.py: PDFLoader, HTMLLoader, detect_agency(),
    detect_doc_type() already implement full loading logic → reused here
  - rag/src/pipeline.py: AerospaceRAGPipeline.ingest_document/ingest_url
    already implement the full ingestion pipeline → called from here
  - This service only adds: curated source registry, batch scheduling,
    status tracking. No rewriting of loaders or chunker.

Graceful degradation
────────────────────
  If Qdrant is not running, ingest methods log a warning and return 0.
  The application starts normally without vector search capability.
"""

from __future__ import annotations

import logging
import sys
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Add rag module to path
_RAG_ROOT = pathlib.Path(__file__).parents[4] / "rag"
if str(_RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(_RAG_ROOT))


# ── Curated source catalog ────────────────────────────────────

@dataclass
class CorpusSource:
    """A single document source in the aerospace corpus."""
    source_id:   str
    title:       str
    url:         str
    agency:      str          # NASA | ESA | ISRO | CCSDS | OTHER
    doc_type:    str          # technical_report | research_paper | standards_doc | textbook
    year:        int | None
    description: str
    priority:    int = 1      # 1=high, 2=medium, 3=low — controls ingest order
    tags:        list[str] = field(default_factory=list)


# ── Curated corpus registry ───────────────────────────────────

CORPUS_SOURCES: list[CorpusSource] = [

    # ── Orbital Mechanics & SSA ───────────────────────────────
    CorpusSource(
        source_id="HOOTS-ROEHRICH-1980",
        title="Spacetrack Report No. 3 — Models for Propagation of NORAD Element Sets",
        url="https://celestrak.org/SPACETRACK/P3Doc.pdf",
        agency="OTHER",
        doc_type="technical_report",
        year=1980,
        description="The definitive reference for SGP4/SDP4 orbital propagation. "
                    "Covers mathematical derivation of the simplified perturbation models.",
        priority=1,
        tags=["sgp4", "orbital_mechanics", "tle", "propagation"],
    ),
    CorpusSource(
        source_id="NASA-STD-8719",
        title="NASA-STD-8719.14 — Process for Limiting Orbital Debris",
        url="https://nodis3.gsfc.nasa.gov/npg_img/N_ST_8719-14A_/N_ST_8719-14A_.pdf",
        agency="NASA",
        doc_type="standards_doc",
        year=2012,
        description="NASA standard for orbital debris mitigation including post-mission "
                    "disposal, passivation, and deorbit requirements.",
        priority=1,
        tags=["debris_mitigation", "orbital_debris", "post_mission_disposal"],
    ),
    CorpusSource(
        source_id="IADC-2007",
        title="IADC Space Debris Mitigation Guidelines",
        url="https://orbitaldebris.jsc.nasa.gov/library/iadc-space-debris-guidelines-revision-2.pdf",
        agency="OTHER",
        doc_type="standards_doc",
        year=2007,
        description="Inter-Agency Space Debris Coordination Committee guidelines "
                    "adopted by ESA, NASA, JAXA, ISRO, Roscosmos, CNSA. "
                    "25-year deorbit rule, protected regions, passivation.",
        priority=1,
        tags=["iadc", "debris_mitigation", "25_year_rule", "deorbit"],
    ),

    # ── Conjunction Analysis ──────────────────────────────────
    CorpusSource(
        source_id="FOSTER-1992",
        title="A Parametric Analysis of Orbital Debris Collision Probability",
        url="https://ntrs.nasa.gov/api/citations/19930016347/downloads/19930016347.pdf",
        agency="NASA",
        doc_type="technical_report",
        year=1992,
        description="Foster & Estes (1992) original paper defining the 2D Gaussian "
                    "collision probability integral implemented in ORBITIQ-X Foster Pc. "
                    "NASA/JSC-25898 — basis for all operational CDM Pc calculations.",
        priority=1,
        tags=["conjunction", "collision_probability", "foster", "cdm", "pc"],
    ),
    CorpusSource(
        source_id="CHAN-1997",
        title="Spacecraft Collision Probability — Chan Series Expansion",
        url="https://ntrs.nasa.gov/api/citations/19980004538/downloads/19980004538.pdf",
        agency="NASA",
        doc_type="technical_report",
        year=1997,
        description="Chan (1997) series expansion for fast collision probability "
                    "computation. Alternative to numerical integration for typical Pc < 0.1.",
        priority=1,
        tags=["conjunction", "collision_probability", "chan", "series_expansion"],
    ),
    CorpusSource(
        source_id="ALFANO-2005",
        title="Relating Position Uncertainty to Maximum Conjunction Probability",
        url="https://ntrs.nasa.gov/api/citations/20060004905/downloads/20060004905.pdf",
        agency="NASA",
        doc_type="research_paper",
        year=2005,
        description="Alfano (2005) analysis of covariance realism and its effect on "
                    "computed Pc. Key reference for understanding when default covariance "
                    "assumptions lead to overestimated or underestimated Pc.",
        priority=1,
        tags=["conjunction", "covariance", "alfano", "pc_uncertainty"],
    ),

    # ── Space Debris ──────────────────────────────────────────
    CorpusSource(
        source_id="ESA-DEBRIS-2023",
        title="ESA Space Debris Environment Report 2023",
        url="https://www.esa.int/Space_Safety/Space_Debris/ESA_s_Annual_Space_Environment_Report",
        agency="ESA",
        doc_type="technical_report",
        year=2023,
        description="Annual ESA assessment of the orbital debris population. "
                    "Covers LEO/MEO/GEO debris counts, trackable objects, "
                    "untrackable population models, Kessler syndrome risk.",
        priority=1,
        tags=["debris", "leo", "kessler", "esa", "annual_report"],
    ),
    CorpusSource(
        source_id="NASA-DEBRIS-2023",
        title="NASA Orbital Debris Quarterly News — 2023 Compilation",
        url="https://orbitaldebris.jsc.nasa.gov/quarterly-news/pdfs/odqnv27i4.pdf",
        agency="NASA",
        doc_type="technical_report",
        year=2023,
        description="NASA Orbital Debris Program Office quarterly news covering "
                    "recent fragmentation events, new tracking data, and debris environment updates.",
        priority=2,
        tags=["debris", "nasa", "fragmentation", "tracking"],
    ),

    # ── Launch Vehicles ───────────────────────────────────────
    CorpusSource(
        source_id="ISRO-PSLV-UG",
        title="ISRO PSLV User's Guide",
        url="https://www.isro.gov.in/media_isro/pdf/PSLVUsersManual.pdf",
        agency="ISRO",
        doc_type="operator_manual",
        year=2019,
        description="PSLV launch vehicle user guide covering payload interfaces, "
                    "performance envelopes (PSLV-C, PSLV-XL, PSLV-DL, PSLV-QL), "
                    "SDSC SHAR launch facilities, and mission planning.",
        priority=2,
        tags=["pslv", "isro", "launch_vehicle", "sdsc", "payload"],
    ),
    CorpusSource(
        source_id="ESA-ARIANE6-UG",
        title="Ariane 6 User's Manual",
        url="https://www.arianespace.com/wp-content/uploads/2021/03/Mua-6_Issue-2_Revision-0_March-2021.pdf",
        agency="ESA",
        doc_type="operator_manual",
        year=2021,
        description="Ariane 6 launch vehicle user manual. Covers A62/A64 configurations, "
                    "Vinci upper stage, performance envelopes, Kourou launch complex ELA-4.",
        priority=2,
        tags=["ariane6", "esa", "launch_vehicle", "kourou", "vinci"],
    ),

    # ── Missions ──────────────────────────────────────────────
    CorpusSource(
        source_id="NASA-ARTEMIS-ARCH",
        title="NASA Artemis Plan — Moon to Mars Architecture",
        url="https://www.nasa.gov/wp-content/uploads/2020/12/artemis_plan-20200921.pdf",
        agency="NASA",
        doc_type="mission_report",
        year=2020,
        description="NASA Artemis program architecture including SLS, Orion, "
                    "Gateway, HLS, and Commercial Crew/Cargo elements. "
                    "Participating agencies: ESA, JAXA, CSA, UAE.",
        priority=1,
        tags=["artemis", "moon", "sls", "orion", "gateway", "nasa", "crewed"],
    ),
    CorpusSource(
        source_id="ISRO-CHANDRAYAAN3",
        title="Chandrayaan-3 Mission Overview",
        url="https://www.isro.gov.in/Chandrayaan3.html",
        agency="ISRO",
        doc_type="mission_report",
        year=2023,
        description="ISRO Chandrayaan-3 lunar mission: Vikram lander, Pragyan rover. "
                    "First soft landing near lunar south pole (August 2023). "
                    "LVM3 launch vehicle, Vikram-S propulsion.",
        priority=1,
        tags=["chandrayaan3", "isro", "moon", "lander", "rover", "lvm3"],
    ),
    CorpusSource(
        source_id="STARLINK-ARCH",
        title="SpaceX Starlink Constellation Architecture",
        url="https://www.spacex.com/media/starlink-press-kit-2020.pdf",
        agency="OTHER",
        doc_type="technical_report",
        year=2020,
        description="SpaceX Starlink LEO constellation architecture. "
                    "Gen 1: 550km, 53° inclined, Ku/Ka-band. "
                    "Gen 2: 530km-604km, higher capacity. Laser ISLs. "
                    "Conjunction avoidance: autonomous maneuver via Startracker.",
        priority=1,
        tags=["starlink", "spacex", "constellation", "leo", "conjunction", "broadband"],
    ),

    # ── CCSDS Standards ──────────────────────────────────────
    CorpusSource(
        source_id="CCSDS-CDM-508",
        title="CCSDS 508.0-B-1 — Conjunction Data Message (CDM)",
        url="https://public.ccsds.org/Pubs/508x0b1e2c1.pdf",
        agency="CCSDS",
        doc_type="standards_doc",
        year=2013,
        description="CCSDS Conjunction Data Message standard. Defines the "
                    "CDM format exchanged between SSA providers (18 SWS, LeoLabs, ExoAnalytic) "
                    "and satellite operators for collision avoidance planning.",
        priority=1,
        tags=["ccsds", "cdm", "conjunction", "standard", "ssn", "18sws"],
    ),
    CorpusSource(
        source_id="CCSDS-TM-131",
        title="CCSDS 131.0-B-5 — TM Synchronization and Channel Coding",
        url="https://public.ccsds.org/Pubs/131x0b5.pdf",
        agency="CCSDS",
        doc_type="standards_doc",
        year=2023,
        description="CCSDS telemetry synchronization standard used by all major "
                    "space agencies for satellite downlink data formatting.",
        priority=3,
        tags=["ccsds", "telemetry", "channel_coding", "standard"],
    ),

    # ── Orbital Mechanics References ──────────────────────────
    CorpusSource(
        source_id="VALLADO-ORBITAL-MECH",
        title="Fundamentals of Astrodynamics and Applications (Vallado) — Selected Chapters",
        url="https://celestrak.org/publications/AAS/07-127/AAS-07-127.pdf",
        agency="OTHER",
        doc_type="technical_report",
        year=2007,
        description="Vallado AAS-07-127: Revisiting Spacetrack Report #3. "
                    "Covers SGP4 implementation corrections, epoch handling, "
                    "and validation against precision ephemeris.",
        priority=1,
        tags=["sgp4", "astrodynamics", "vallado", "orbital_mechanics", "tle"],
    ),
    CorpusSource(
        source_id="ESA-SST-2023",
        title="ESA Space Surveillance and Tracking Programme Overview",
        url="https://www.esa.int/Space_Safety/Space_Debris/Types_of_orbits",
        agency="ESA",
        doc_type="technical_report",
        year=2023,
        description="ESA SST programme covering European sensor network, "
                    "conjunction screening, re-entry predictions, "
                    "and fragmentation event monitoring.",
        priority=2,
        tags=["esa", "sst", "ssa", "surveillance", "tracking"],
    ),
]


# ── Corpus status tracker ─────────────────────────────────────

@dataclass
class CorpusStatus:
    total_sources:   int = 0
    ingested:        int = 0
    failed:          int = 0
    pending:         int = 0
    total_chunks:    int = 0
    last_updated:    datetime | None = None
    source_statuses: dict[str, str] = field(default_factory=dict)  # id → ok|failed|pending


# ── Service ───────────────────────────────────────────────────

class AerospaceCorpusService:
    """
    Manages the aerospace knowledge corpus.

    Responsibilities
    ────────────────
    - Curates the source registry (CORPUS_SOURCES)
    - Drives AerospaceRAGPipeline.ingest_url() for each source
    - Tracks ingest status per source
    - Returns corpus statistics

    What this does NOT do
    ──────────────────────
    - Does not implement loading/chunking/embedding — that is in
      rag/src/ingestion, rag/src/chunking, rag/src/embedding (intact)
    - Does not manage the Qdrant store — that is in rag/src/store

    Parameters
    ----------
    pipeline : AerospaceRAGPipeline | None
        Injected at runtime. If None (no Qdrant), all ingest methods
        return 0 gracefully.
    """

    def __init__(self, pipeline=None) -> None:
        self._pipeline = pipeline
        self._status   = CorpusStatus(
            total_sources=len(CORPUS_SOURCES),
            pending=len(CORPUS_SOURCES),
            source_statuses={s.source_id: "pending" for s in CORPUS_SOURCES},
        )

    # ── Pipeline setter (allows lazy injection) ───────────────

    def set_pipeline(self, pipeline) -> None:
        self._pipeline = pipeline

    # ── Source catalog access ─────────────────────────────────

    def list_sources(
        self,
        agency: str | None = None,
        doc_type: str | None = None,
        priority: int | None = None,
        tags: list[str] | None = None,
    ) -> list[CorpusSource]:
        """Return filtered list of corpus sources."""
        sources = list(CORPUS_SOURCES)
        if agency:
            sources = [s for s in sources if s.agency.upper() == agency.upper()]
        if doc_type:
            sources = [s for s in sources if s.doc_type == doc_type]
        if priority:
            sources = [s for s in sources if s.priority <= priority]
        if tags:
            sources = [s for s in sources if any(t in s.tags for t in tags)]
        return sorted(sources, key=lambda s: (s.priority, s.source_id))

    def get_source(self, source_id: str) -> CorpusSource | None:
        return next((s for s in CORPUS_SOURCES if s.source_id == source_id), None)

    # ── Ingestion ─────────────────────────────────────────────

    async def ingest_source(self, source_id: str) -> dict:
        """
        Ingest a single corpus source by ID.

        Delegates to AerospaceRAGPipeline.ingest_url() which implements
        the full load → chunk → embed → upsert pipeline.

        Returns
        -------
        dict
            {source_id, chunks_indexed, status, error}
        """
        source = self.get_source(source_id)
        if not source:
            return {"source_id": source_id, "chunks_indexed": 0,
                    "status": "error", "error": "source_not_found"}

        if not self._pipeline:
            logger.warning("corpus_ingest_skipped source=%s — pipeline not initialised", source_id)
            return {"source_id": source_id, "chunks_indexed": 0,
                    "status": "skipped", "error": "pipeline_not_available"}

        try:
            # Import here so missing rag deps don't break the backend at import time
            meta = self._build_metadata(source)
            chunks = await self._pipeline.ingest_url(source.url, meta)
            self._status.source_statuses[source_id] = "ok"
            self._status.ingested   += 1
            self._status.pending    -= 1
            self._status.total_chunks += chunks
            self._status.last_updated = datetime.now(timezone.utc)
            logger.info("corpus_ingested source=%s chunks=%d", source_id, chunks)
            return {"source_id": source_id, "chunks_indexed": chunks,
                    "status": "ok", "error": None}

        except Exception as exc:
            self._status.source_statuses[source_id] = "failed"
            self._status.failed  += 1
            self._status.pending -= 1
            logger.error("corpus_ingest_failed source=%s error=%s", source_id, exc)
            return {"source_id": source_id, "chunks_indexed": 0,
                    "status": "failed", "error": str(exc)}

    async def ingest_all(
        self,
        priority_filter: int | None = None,
        agency_filter: str | None = None,
    ) -> list[dict]:
        """
        Ingest all sources matching the given filters.

        Parameters
        ----------
        priority_filter : int | None
            Maximum priority level to ingest (1=high, 2=medium, 3=low).
            None = ingest all.
        agency_filter : str | None
            Only ingest sources from this agency.

        Returns
        -------
        list[dict]
            One result dict per source attempted.
        """
        sources = self.list_sources(
            agency=agency_filter,
            priority=priority_filter,
        )
        results = []
        for source in sources:
            result = await self.ingest_source(source.source_id)
            results.append(result)
        return results

    # ── Statistics ────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return corpus ingestion status."""
        return {
            "total_sources":   self._status.total_sources,
            "ingested":        self._status.ingested,
            "failed":          self._status.failed,
            "pending":         self._status.pending,
            "total_chunks":    self._status.total_chunks,
            "last_updated":    self._status.last_updated.isoformat()
                               if self._status.last_updated else None,
            "source_statuses": self._status.source_statuses,
            "pipeline_ready":  self._pipeline is not None,
        }

    def get_sources_by_topic(self, topic: str) -> list[CorpusSource]:
        """Find sources relevant to an aerospace topic keyword."""
        topic_lower = topic.lower()
        return [
            s for s in CORPUS_SOURCES
            if topic_lower in s.description.lower()
            or topic_lower in " ".join(s.tags)
            or topic_lower in s.title.lower()
        ]

    # ── Helpers ───────────────────────────────────────────────

    def _build_metadata(self, source: CorpusSource):
        """Build a DocumentMetadata object from a CorpusSource."""
        # Import lazily so missing rag deps don't crash the backend
        from src.models.schemas import DocumentMetadata, AgencyType, DocumentType

        agency_map = {
            "NASA": AgencyType.NASA, "ESA": AgencyType.ESA,
            "ISRO": AgencyType.ISRO, "JAXA": AgencyType.JAXA,
            "CNSA": AgencyType.CNSA, "CCSDS": AgencyType.OTHER,
        }
        type_map = {
            "technical_report": DocumentType.TECHNICAL_REPORT,
            "research_paper":   DocumentType.RESEARCH_PAPER,
            "standards_doc":    DocumentType.STANDARDS_DOC,
            "operator_manual":  DocumentType.OPERATOR_MANUAL,
            "mission_report":   DocumentType.MISSION_REPORT,
            "textbook":         DocumentType.TEXTBOOK,
        }
        return DocumentMetadata(
            title=source.title,
            agency=agency_map.get(source.agency, AgencyType.OTHER),
            doc_type=type_map.get(source.doc_type, DocumentType.UNKNOWN),
            publication_year=source.year,
            source_url=source.url,
            report_number=source.source_id,
        )
