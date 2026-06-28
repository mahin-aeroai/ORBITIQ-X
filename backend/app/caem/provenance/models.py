"""
ORBITIQ-X — Provenance & Versioning Models
Phase 17.3

Extends Phase 17.1 base.py ProvenanceRecord with:
  - FactRecord: provenance attached to a single named field on a single entity
  - ContradictionRecord: conflict between two sources on the same fact
  - ReviewQueueItem: human review task for unresolved contradictions
  - SourceTierPolicy: authority rules enforced at ingest time
  - VersionSnapshot: immutable point-in-time copy of an entity's full state

Design rules:
  - Every fact that can vary by source gets a FactRecord
  - No fact is silently overwritten — contradictions are always logged
  - Version history is append-only; snapshots are never mutated
  - Source authority tiers 1–6 map to quantified confidence weights
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


# ---------------------------------------------------------------------------
# SOURCE AUTHORITY TIERS
# ---------------------------------------------------------------------------

class SourceTier(int, Enum):
    """
    Six-tier source authority hierarchy.
    Tier determines default confidence weight at ingest time.
    """
    TIER_1_OFFICIAL         = 1   # Space agency, operator, manufacturer official pubs
    TIER_2_REGISTRY         = 2   # NORAD, COSPAR, UNOOSA, ITU official registries
    TIER_3_PEER_REVIEWED    = 3   # Academic journals, IEEE, AIAA proceedings
    TIER_4_REFERENCE        = 4   # Encyclopedia Astronautica, Wikipedia (aerospace)
    TIER_5_NEWS             = 5   # SpaceNews, NASAspaceflight, Aviation Week
    TIER_6_COMMUNITY        = 6   # Amateur tracking, hobbyist databases


TIER_CONFIDENCE_WEIGHTS: Dict[SourceTier, float] = {
    SourceTier.TIER_1_OFFICIAL:      1.00,
    SourceTier.TIER_2_REGISTRY:      0.95,
    SourceTier.TIER_3_PEER_REVIEWED: 0.85,
    SourceTier.TIER_4_REFERENCE:     0.70,
    SourceTier.TIER_5_NEWS:          0.65,
    SourceTier.TIER_6_COMMUNITY:     0.50,
}

# Known Tier 1 source domains
TIER_1_DOMAINS = {
    "nasa.gov", "esa.int", "spacex.com", "isro.gov.in",
    "roscosmos.ru", "jaxa.jp", "csa-asc.gc.ca", "cnsa.gov.cn",
    "space-track.org", "boeing.com", "lockheedmartin.com",
    "northropgrumman.com", "airbus.com", "thalesaleniaspace.com",
}

# Known Tier 2 registry domains
TIER_2_DOMAINS = {
    "celestrak.org", "unoosa.org", "itu.int",
    "sdo.esoc.esa.int", "nssdc.gsfc.nasa.gov",
}


def infer_source_tier(source_url: Optional[str]) -> SourceTier:
    """
    Infer source authority tier from a URL domain.
    Falls back to TIER_6 when domain is unknown.
    """
    if not source_url:
        return SourceTier.TIER_6_COMMUNITY

    try:
        from urllib.parse import urlparse
        domain = urlparse(source_url).netloc.lower().lstrip("www.")
        if any(domain.endswith(d) for d in TIER_1_DOMAINS):
            return SourceTier.TIER_1_OFFICIAL
        if any(domain.endswith(d) for d in TIER_2_DOMAINS):
            return SourceTier.TIER_2_REGISTRY
        # Academic institution domains and known journal publishers
        academic_domains = ('.edu', '.ac.uk', '.ac.jp', '.ac.in', '.ac.au')
        academic_publishers = ('arxiv.org', 'dl.acm.org', 'ieeexplore.ieee.org',
                               'aiaa.org', 'springer.com', 'elsevier.com',
                               'tandfonline.com', 'nature.com', 'science.org',
                               'researchgate.net', 'semanticscholar.org')
        if domain.endswith(academic_domains) or any(domain.endswith(p) for p in academic_publishers):
            return SourceTier.TIER_3_PEER_REVIEWED
    except Exception:
        pass

    return SourceTier.TIER_6_COMMUNITY


# ---------------------------------------------------------------------------
# FACT RECORD — provenance for a single field value
# ---------------------------------------------------------------------------

class FactRecord(BaseModel):
    """
    Provenance for a single named field on a single entity.

    Stored in the `fact_provenance` table. Every time a field value is
    set or updated, a FactRecord is created linking the value to its source.

    Enables:
      - Field-level source attribution ("this payload_leo_kg comes from SpaceX press kit")
      - Contradiction detection (two sources give different values for same field)
      - Confidence scoring per fact (not just per entity)
    """
    fact_id:            str = Field(default_factory=lambda: uuid.uuid4().hex)
    aqid:               str                         # Entity this fact belongs to
    field_name:         str                         # e.g. "payload_leo_kg", "display_name"
    field_value:        str                         # JSON-serialized value
    field_value_type:   str = "str"                 # Python type name: str, int, float, bool, list

    # Source
    source_url:         Optional[str]   = None
    source_name:        Optional[str]   = None
    source_tier:        SourceTier      = SourceTier.TIER_6_COMMUNITY
    source_type:        str             = "community"
    publisher:          Optional[str]   = None
    author:             Optional[str]   = None
    published_date:     Optional[date]  = None
    retrieved_at:       datetime        = Field(default_factory=datetime.utcnow)

    # Trust
    confidence:         float           = Field(default=0.50, ge=0.0, le=1.0)
    is_primary:         bool            = True      # Is this the authoritative value?
    is_superseded:      bool            = False     # Was this fact overridden by a newer source?
    superseded_by:      Optional[str]   = None      # fact_id of the superseding fact

    # Citation
    citation_text:      Optional[str]   = None
    doi:                Optional[str]   = None
    page_ref:           Optional[str]   = None

    # Audit
    created_at:         datetime        = Field(default_factory=datetime.utcnow)
    created_by:         str             = "system"
    ingest_job_id:      Optional[str]   = None


# ---------------------------------------------------------------------------
# CONTRADICTION RECORD
# ---------------------------------------------------------------------------

class ContradictionResolution(str, Enum):
    OVERRIDE    = "override"    # New value replaces existing (higher confidence)
    DISPUTE     = "dispute"     # Both kept, flagged for human review
    REJECT      = "reject"      # New value rejected (lower confidence)
    MERGED      = "merged"      # Values reconciled by human reviewer


class ContradictionRecord(BaseModel):
    """
    A detected conflict between two sources on the same entity field.

    Created by the ingestion pipeline when incoming value differs from
    the existing primary value for the same (aqid, field_name) pair.

    Lifecycle:
      draft → auto_resolved (if confidence delta is clear) → done
      draft → pending_review (if confidence delta is within threshold) → human_resolved → done
    """
    contradiction_id:   str = Field(default_factory=lambda: uuid.uuid4().hex)
    aqid:               str
    field_name:         str

    # Existing fact
    existing_fact_id:   str
    existing_value:     str
    existing_confidence: float
    existing_source_url: Optional[str]  = None
    existing_tier:      SourceTier      = SourceTier.TIER_6_COMMUNITY

    # Incoming fact
    incoming_fact_id:   str
    incoming_value:     str
    incoming_confidence: float
    incoming_source_url: Optional[str]  = None
    incoming_tier:      SourceTier      = SourceTier.TIER_6_COMMUNITY

    # Resolution
    confidence_delta:   float           = 0.0       # incoming - existing
    resolution:         ContradictionResolution = ContradictionResolution.DISPUTE
    resolution_notes:   Optional[str]   = None
    resolved_by:        Optional[str]   = None      # "system" or username
    resolved_at:        Optional[datetime] = None

    # Lifecycle
    status:             str = "pending_review"      # pending_review / auto_resolved / human_resolved
    ingest_job_id:      Optional[str]   = None
    created_at:         datetime        = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# REVIEW QUEUE ITEM
# ---------------------------------------------------------------------------

class ReviewPriority(str, Enum):
    CRITICAL    = "critical"    # Core identity field (display_name, entity_class)
    HIGH        = "high"        # High-confidence contradiction on important field
    MEDIUM      = "medium"      # Standard field contradiction
    LOW         = "low"         # Minor field, low confidence sources


class ReviewQueueItem(BaseModel):
    """
    A task in the human review queue.

    Created whenever a contradiction cannot be auto-resolved
    (confidence delta within ±0.15 threshold).
    """
    review_id:          str = Field(default_factory=lambda: uuid.uuid4().hex)
    contradiction_id:   str
    aqid:               str
    field_name:         str
    priority:           ReviewPriority  = ReviewPriority.MEDIUM

    # Display context
    entity_display_name: Optional[str] = None
    existing_value:     str
    incoming_value:     str
    existing_source:    Optional[str]   = None
    incoming_source:    Optional[str]   = None
    confidence_delta:   float           = 0.0

    # Assignment
    assigned_to:        Optional[str]   = None
    assigned_at:        Optional[datetime] = None
    due_by:             Optional[datetime] = None

    # Resolution
    status:             str = "open"    # open / in_progress / resolved / dismissed
    resolution:         Optional[ContradictionResolution] = None
    reviewer_notes:     Optional[str]   = None
    resolved_by:        Optional[str]   = None
    resolved_at:        Optional[datetime] = None

    created_at:         datetime        = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# VERSION SNAPSHOT
# ---------------------------------------------------------------------------

class VersionSnapshot(BaseModel):
    """
    Immutable point-in-time copy of an entity's full state.

    Created whenever:
      - An entity is promoted to 'published' status
      - A significant field changes (confidence > 0.10 delta)
      - A human reviewer resolves a contradiction
      - Manually triggered via the API

    Never mutated after creation.
    """
    snapshot_id:        str = Field(default_factory=lambda: uuid.uuid4().hex)
    aqid:               str
    version:            str                         # e.g. "1.3.0"
    snapshot_type:      str = "auto"                # auto / publish / contradiction / manual

    # Full entity state at this point in time
    entity_state:       Dict[str, Any]              # Full serialized entity
    extension_state:    Dict[str, Any] = {}         # extension_data at this point
    confidence_at_snapshot: float      = 0.0
    verification_status_at: str        = "unverified"

    # Change summary
    change_summary:     str            = ""
    fields_changed:     List[str]      = []         # List of changed field names
    field_diffs:        Dict[str, Any] = {}         # {field: {before, after}}

    # Authorship
    created_by:         str            = "system"
    ingest_job_id:      Optional[str]  = None
    created_at:         datetime       = Field(default_factory=datetime.utcnow)
