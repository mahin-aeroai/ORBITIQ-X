"""
ORBITIQ-X — Canonical Aerospace Entity Model (CAEM)
Phase 17.1 — Base Entity Architecture

This module defines the universal base from which every aerospace entity
in the Aerospace Knowledge Universe inherits. No entity bypasses this model.

Design principles:
  - AQID is the only permanent identifier; all display names are attributes
  - Every field carries optional provenance; no fact is provenance-free
  - Extension data is typed per entity class but stored in a single JSONB column
  - This module has zero dependencies on entity-class-specific code
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# TAXONOMY ENUMS
# ---------------------------------------------------------------------------

class EntityClass(str, Enum):
    """
    Canonical entity class taxonomy for the Aerospace Knowledge Universe.
    Every class maps to one Neo4j label and one Pydantic extension model.
    """
    # Actors
    COUNTRY             = "COUNTRY"
    GOV_AGENCY          = "GOV_AGENCY"
    COMPANY             = "COMPANY"
    UNIVERSITY          = "UNIVERSITY"
    RESEARCH_ORG        = "RESEARCH_ORG"

    # People
    PERSON              = "PERSON"

    # Hardware
    LAUNCH_VEHICLE      = "LAUNCH_VEHICLE"
    SATELLITE           = "SATELLITE"
    PAYLOAD             = "PAYLOAD"
    SPACECRAFT          = "SPACECRAFT"
    DEBRIS              = "DEBRIS"
    COMPONENT           = "COMPONENT"
    SENSOR              = "SENSOR"
    INSTRUMENT          = "INSTRUMENT"
    MATERIAL            = "MATERIAL"

    # Infrastructure
    LAUNCH_SITE         = "LAUNCH_SITE"
    GROUND_STATION      = "GROUND_STATION"
    TRACKING_NETWORK    = "TRACKING_NETWORK"

    # Programs & Missions
    PROGRAM             = "PROGRAM"
    MISSION             = "MISSION"
    CONSTELLATION       = "CONSTELLATION"

    # Knowledge
    TECHNOLOGY          = "TECHNOLOGY"
    STANDARD            = "STANDARD"
    SPECIFICATION       = "SPECIFICATION"
    RESEARCH_PAPER      = "RESEARCH_PAPER"
    PATENT              = "PATENT"

    # Commercial
    PRODUCT             = "PRODUCT"
    SERVICE             = "SERVICE"
    CONTRACT            = "CONTRACT"
    INVESTMENT          = "INVESTMENT"

    # Regulatory
    POLICY              = "POLICY"
    AGREEMENT           = "AGREEMENT"

    # Events
    HISTORICAL_EVENT    = "HISTORICAL_EVENT"
    INCIDENT            = "INCIDENT"
    ANOMALY             = "ANOMALY"
    NEWS                = "NEWS"

    # Celestial
    ASTEROID            = "ASTEROID"
    COMET               = "COMET"
    CELESTIAL_BODY      = "CELESTIAL_BODY"


class EntitySubclass(str, Enum):
    """
    Secondary classification layer within entity classes.
    Used for more granular taxonomy without proliferating top-level classes.
    """
    # Satellite subclasses
    EARTH_OBS       = "EARTH_OBS"
    COMMUNICATIONS  = "COMMUNICATIONS"
    NAVIGATION      = "NAVIGATION"
    SCIENTIFIC      = "SCIENTIFIC"
    MILITARY        = "MILITARY"
    WEATHER         = "WEATHER"
    TECHNOLOGY_DEMO = "TECHNOLOGY_DEMO"

    # Launch vehicle subclasses
    SMALL_LIFT      = "SMALL_LIFT"       # < 2,000 kg to LEO
    MEDIUM_LIFT     = "MEDIUM_LIFT"      # 2,000–20,000 kg to LEO
    HEAVY_LIFT      = "HEAVY_LIFT"       # 20,000–50,000 kg to LEO
    SUPER_HEAVY     = "SUPER_HEAVY"      # > 50,000 kg to LEO

    # Mission subclasses
    CREWED          = "CREWED"
    ROBOTIC         = "ROBOTIC"
    CARGO           = "CARGO"
    FLYBY           = "FLYBY"
    ORBITER         = "ORBITER"
    LANDER          = "LANDER"
    SAMPLE_RETURN   = "SAMPLE_RETURN"

    # Company subclasses
    PRIME           = "PRIME"
    INTEGRATOR      = "INTEGRATOR"
    MANUFACTURER    = "MANUFACTURER"
    OPERATOR        = "OPERATOR"
    SUPPLIER        = "SUPPLIER"
    STARTUP         = "STARTUP"


class LifecycleStatus(str, Enum):
    """Record lifecycle within the knowledge pipeline."""
    DRAFT       = "draft"        # Ingested but not validated
    PENDING     = "pending"      # Awaiting verification
    PUBLISHED   = "published"    # Verified and live
    DEPRECATED  = "deprecated"   # Superseded but retained
    ARCHIVED    = "archived"     # Removed from active queries


class VerificationStatus(str, Enum):
    """Trust level of a specific fact or entire entity record."""
    UNVERIFIED      = "unverified"
    AI_VERIFIED     = "ai_verified"
    HUMAN_VERIFIED  = "human_verified"
    AUTHORITATIVE   = "authoritative"
    DISPUTED        = "disputed"


class SourceType(str, Enum):
    """Classification of knowledge source by authority type."""
    OFFICIAL        = "official"        # Space agency, operator, manufacturer
    OFFICIAL_REGISTRY = "official_registry"  # NORAD, COSPAR, UNOOSA
    PEER_REVIEWED   = "peer_reviewed"   # Academic journals, IEEE, AIAA
    REFERENCE       = "reference"       # Encyclopedia Astronautica, Wikipedia
    NEWS            = "news"            # SpaceNews, NASAspaceflight
    COMMUNITY       = "community"       # Amateur, hobbyist databases
    AI_GENERATED    = "ai_generated"    # Claude-synthesized summary


class DatePrecision(str, Enum):
    """Granularity of a historical date."""
    CENTURY = "century"
    DECADE  = "decade"
    YEAR    = "year"
    MONTH   = "month"
    DAY     = "day"
    HOUR    = "hour"


class ChangeType(str, Enum):
    """Type of change in version history."""
    CREATED     = "created"
    UPDATED     = "updated"
    VERIFIED    = "verified"
    DISPUTED    = "disputed"
    DEPRECATED  = "deprecated"
    RESTORED    = "restored"


class ImportanceLevel(str, Enum):
    """Importance of a timeline event."""
    CRITICAL    = "critical"
    MAJOR       = "major"
    MINOR       = "minor"


# ---------------------------------------------------------------------------
# SOURCE AUTHORITY TIERS
# Weights used in confidence score composition.
# ---------------------------------------------------------------------------

SOURCE_AUTHORITY_WEIGHT: Dict[SourceType, float] = {
    SourceType.OFFICIAL:            1.00,
    SourceType.OFFICIAL_REGISTRY:   0.95,
    SourceType.PEER_REVIEWED:       0.85,
    SourceType.REFERENCE:           0.70,
    SourceType.NEWS:                0.65,
    SourceType.COMMUNITY:           0.50,
    SourceType.AI_GENERATED:        0.60,
}

VERIFICATION_STATUS_WEIGHT: Dict[VerificationStatus, float] = {
    VerificationStatus.AUTHORITATIVE:   1.00,
    VerificationStatus.HUMAN_VERIFIED:  0.90,
    VerificationStatus.AI_VERIFIED:     0.75,
    VerificationStatus.UNVERIFIED:      0.50,
    VerificationStatus.DISPUTED:        0.30,
}


# ---------------------------------------------------------------------------
# AQID UTILITIES
# ---------------------------------------------------------------------------

_SLUG_PATTERN = re.compile(r'[^A-Z0-9]+')

def generate_aqid(entity_class: EntityClass, canonical_name: str) -> str:
    """
    Derive an AQID from entity class and canonical name.

    generate_aqid(EntityClass.COMPANY, "SpaceX")
        → "AQID-COMPANY-SPACEX"
    generate_aqid(EntityClass.SATELLITE, "Starlink-1024")
        → "AQID-SATELLITE-STARLINK-1024"
    generate_aqid(EntityClass.STANDARD, "CCSDS 727.0-B-5")
        → "AQID-STANDARD-CCSDS-727-0-B-5"

    Slug rules:
      - Uppercase entire name
      - Replace any non-alphanumeric run with a single hyphen
      - Strip leading/trailing hyphens
    """
    slug = _SLUG_PATTERN.sub('-', canonical_name.upper()).strip('-')
    return f"AQID-{entity_class.value}-{slug}"


def validate_aqid(aqid: str) -> bool:
    """Return True if the string conforms to the AQID format."""
    return bool(re.match(r'^AQID-[A-Z_]+-[A-Z0-9\-]+$', aqid))


def aqid_entity_class(aqid: str) -> Optional[str]:
    """
    Extract the entity class segment from an AQID.
    "AQID-COMPANY-SPACEX" → "COMPANY"
    Returns None if the format is invalid.
    """
    parts = aqid.split('-', 2)
    return parts[1] if len(parts) >= 3 and parts[0] == 'AQID' else None


# ---------------------------------------------------------------------------
# PROVENANCE MODELS
# ---------------------------------------------------------------------------

class ProvenanceRecord(BaseModel):
    """
    Complete chain of custody for a single fact.
    Every fact that can be independently sourced should carry one of these.
    """
    source_url:     Optional[str]         = None
    source_name:    Optional[str]         = None
    source_type:    SourceType            = SourceType.COMMUNITY
    publisher:      Optional[str]         = None
    author:         Optional[str]         = None
    published_date: Optional[date]        = None
    retrieved_date: datetime              = Field(default_factory=datetime.utcnow)

    # Trust signals
    confidence:             float               = Field(default=0.50, ge=0.0, le=1.0)
    verification_status:    VerificationStatus  = VerificationStatus.UNVERIFIED

    # Citation
    citation_text:  Optional[str]   = None   # Formatted citation string
    doi:            Optional[str]   = None
    isbn:           Optional[str]   = None
    notes:          Optional[str]   = None

    def composite_confidence(self) -> float:
        """
        Compute composite confidence from source authority and verification status.
        Corroboration component requires the parent entity to supply source count;
        this method returns the two-signal composite.
        """
        authority = SOURCE_AUTHORITY_WEIGHT.get(self.source_type, 0.50)
        verification = VERIFICATION_STATUS_WEIGHT.get(self.verification_status, 0.50)
        return round((authority * 0.40) + (verification * 0.35) + (self.confidence * 0.25), 4)


def compute_entity_confidence(
    sources: List[ProvenanceRecord],
    primary_verification: VerificationStatus,
) -> float:
    """
    Composite entity-level confidence score.

    confidence = (source_authority × 0.40)
               + (verification_status × 0.35)
               + (corroboration × 0.25)
    """
    if not sources:
        return 0.30

    # Best single-source authority
    authority = max(
        SOURCE_AUTHORITY_WEIGHT.get(s.source_type, 0.50) for s in sources
    )

    # Verification weight
    verification = VERIFICATION_STATUS_WEIGHT.get(primary_verification, 0.50)

    # Corroboration score (distinct sources)
    n = len(set(s.source_url for s in sources if s.source_url))
    corroboration = 0.50 if n == 1 else 0.70 if n == 2 else 0.90

    return round((authority * 0.40) + (verification * 0.35) + (corroboration * 0.25), 4)


# ---------------------------------------------------------------------------
# TIMELINE MODELS
# ---------------------------------------------------------------------------

class TimelineEvent(BaseModel):
    """
    A discrete event in an entity's lifecycle history.
    Events are ordered chronologically and surfaced on the entity page timeline.
    """
    event_id:           str                     = Field(default_factory=lambda: str(uuid.uuid4()))
    label:              str                     # Short human-readable label
    description:        Optional[str]           = None
    date:               Optional[date]          = None
    date_precision:     DatePrecision           = DatePrecision.DAY
    date_is_approximate: bool                   = False
    importance:         ImportanceLevel         = ImportanceLevel.MINOR
    linked_aqids:       List[str]               = []   # Other entities involved
    provenance:         Optional[ProvenanceRecord] = None
    tags:               List[str]               = []

    @field_validator('linked_aqids', mode='before')
    @classmethod
    def validate_aqids(cls, v: List[str]) -> List[str]:
        for aqid in v:
            if not validate_aqid(aqid):
                raise ValueError(f"Invalid AQID in timeline event: {aqid}")
        return v


# ---------------------------------------------------------------------------
# VERSION & AUDIT MODELS
# ---------------------------------------------------------------------------

class VersionEntry(BaseModel):
    """
    Immutable record of a state transition in an entity's version history.
    Never deleted; always appended.
    """
    version:        str
    effective_at:   datetime    = Field(default_factory=datetime.utcnow)
    changed_by:     str         = "system"
    change_type:    ChangeType  = ChangeType.UPDATED
    summary:        str
    field_diff:     Optional[Dict[str, Any]] = None   # {field: {before, after}}
    provenance:     Optional[ProvenanceRecord] = None


class ChangeLogEntry(BaseModel):
    """
    Granular field-level change record for audit compliance.
    """
    entry_id:       str         = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:      datetime    = Field(default_factory=datetime.utcnow)
    changed_by:     str
    field_name:     str
    old_value:      Optional[str] = None
    new_value:      Optional[str] = None
    change_reason:  Optional[str] = None
    provenance:     Optional[ProvenanceRecord] = None


class ExternalIdRecord(BaseModel):
    """
    Mapping from AQID to an external identifier system.
    Stored in the entity_aliases table for bidirectional lookup.
    """
    external_system:    str   # NORAD / COSPAR / DOI / ISO / CIK / ITU / etc.
    external_id:        str
    is_primary:         bool  = True   # Primary ID within that system
    notes:              Optional[str] = None


# ---------------------------------------------------------------------------
# DOCUMENT REFERENCE
# ---------------------------------------------------------------------------

class DocumentRef(BaseModel):
    """
    Reference to an external or ingested document linked to an entity.
    The document itself lives in Qdrant; this is the metadata link.
    """
    doc_id:         str                     = Field(default_factory=lambda: str(uuid.uuid4()))
    title:          str
    document_type:  str                     # research_paper / standard / report / manual / news
    source_url:     Optional[str]           = None
    publisher:      Optional[str]           = None
    published_date: Optional[date]          = None
    authors:        List[str]               = []
    doi:            Optional[str]           = None
    qdrant_chunk_ids: List[str]             = []
    relevance_score: float                  = Field(default=0.5, ge=0.0, le=1.0)
    provenance:     Optional[ProvenanceRecord] = None


# ---------------------------------------------------------------------------
# AI INTELLIGENCE BLOCK
# ---------------------------------------------------------------------------

class AIIntelligenceBlock(BaseModel):
    """
    Cached AI-generated intelligence for an entity.
    Refreshed by the Summary Agent on entity update or scheduled cadence.
    """
    executive_summary:      Optional[str]       = None    # 2-3 sentence summary
    extended_analysis:      Optional[str]       = None    # Deeper analytical paragraph
    key_facts:              List[Dict[str, str]] = []     # [{label, value, unit}]
    generated_at:           Optional[datetime]  = None
    model_version:          Optional[str]       = None
    generation_confidence:  float               = Field(default=0.0, ge=0.0, le=1.0)
    requires_refresh:       bool                = False   # Flagged when entity data changes significantly


# ---------------------------------------------------------------------------
# CANONICAL BASE ENTITY
# ---------------------------------------------------------------------------

class BaseAerospaceEntity(BaseModel):
    """
    The universal base model for every aerospace entity in ORBITIQ-X.

    Architecture:
      - Stored in PostgreSQL table `aerospace_entities` (single-table inheritance)
      - Mirrored as a node in Neo4j (minimal property set for graph traversal)
      - AI summary cached in PostgreSQL text column for fast page render
      - Entity-class-specific fields live in `extension_data` JSONB column

    Immutability contract:
      - `aqid` is set once at creation and never modified
      - `created_at` is set once at creation and never modified
      - `entity_class` is set once and never modified
      - All other fields are mutable via the ingestion pipeline
    """

    # ------------------------------------------------------------------
    # IDENTITY BLOCK
    # ------------------------------------------------------------------
    aqid:               str                         # AQID-CLASS-SLUG, immutable PK
    entity_class:       EntityClass
    entity_subclass:    Optional[EntitySubclass]    = None
    display_name:       str                         = Field(max_length=255)
    short_name:         Optional[str]               = Field(default=None, max_length=80)
    aliases:            List[str]                   = []
    native_name:        Optional[str]               = None  # Name in native language
    description:        Optional[str]               = None  # 1-3 sentence factual summary
    long_description:   Optional[str]               = None  # Full encyclopedic description

    # ------------------------------------------------------------------
    # METADATA BLOCK
    # ------------------------------------------------------------------
    created_at:             datetime    = Field(default_factory=datetime.utcnow)
    updated_at:             datetime    = Field(default_factory=datetime.utcnow)
    published_at:           Optional[datetime]  = None
    schema_version:         str         = "17.1.0"   # CAEM version this record conforms to
    is_active:              bool        = True
    lifecycle_status:       LifecycleStatus = LifecycleStatus.DRAFT
    record_completeness:    float       = Field(default=0.0, ge=0.0, le=1.0)
    primary_language:       str         = "en"

    # ------------------------------------------------------------------
    # TAXONOMY BLOCK
    # ------------------------------------------------------------------
    tags:           List[str]   = []
    domains:        List[str]   = []    # propulsion / orbital_mechanics / comms / etc.
    regions:        List[str]   = []    # NORTH_AMERICA / EUROPE / ASIA_PACIFIC / etc.
    time_periods:   List[str]   = []    # SPACE_RACE / POST_APOLLO / COMMERCIAL_ERA / etc.

    # ------------------------------------------------------------------
    # TIMELINE BLOCK
    # ------------------------------------------------------------------
    founded_or_created:     Optional[date]  = None
    operational_start:      Optional[date]  = None
    operational_end:        Optional[date]  = None
    timeline_events:        List[TimelineEvent] = []

    # ------------------------------------------------------------------
    # RELATIONSHIP BLOCK
    # (AQIDs only — actual relationship objects live in Neo4j)
    # ------------------------------------------------------------------
    parent_aqid:    Optional[str]   = None
    child_aqids:    List[str]       = []
    related_aqids:  List[str]       = []

    # ------------------------------------------------------------------
    # KNOWLEDGE BLOCK (Qdrant references)
    # ------------------------------------------------------------------
    qdrant_chunk_ids:   List[str]           = []
    document_refs:      List[DocumentRef]   = []
    knowledge_domains:  List[str]           = []

    # ------------------------------------------------------------------
    # EXTERNAL IDENTIFIERS
    # ------------------------------------------------------------------
    external_ids:   List[ExternalIdRecord]  = []

    # ------------------------------------------------------------------
    # AI INTELLIGENCE BLOCK
    # ------------------------------------------------------------------
    ai_intelligence:    AIIntelligenceBlock = Field(default_factory=AIIntelligenceBlock)

    # ------------------------------------------------------------------
    # PROVENANCE BLOCK
    # ------------------------------------------------------------------
    primary_provenance:     Optional[ProvenanceRecord]  = None
    all_sources:            List[ProvenanceRecord]      = []
    verification_status:    VerificationStatus          = VerificationStatus.UNVERIFIED
    confidence_score:       float = Field(default=0.50, ge=0.0, le=1.0)

    # ------------------------------------------------------------------
    # AUDIT BLOCK
    # ------------------------------------------------------------------
    created_by:         str             = "system"
    updated_by:         str             = "system"
    ingest_pipeline:    Optional[str]   = None
    ingest_job_id:      Optional[str]   = None
    change_log:         List[ChangeLogEntry] = []

    # ------------------------------------------------------------------
    # VERSION BLOCK
    # ------------------------------------------------------------------
    current_version:    str                 = "1.0.0"
    version_history:    List[VersionEntry]  = []

    # ------------------------------------------------------------------
    # EXTENSION BLOCK (entity-class-specific fields)
    # Typed by entity class at API layer; stored as JSONB in PostgreSQL.
    # ------------------------------------------------------------------
    extension_data: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # VALIDATORS
    # ------------------------------------------------------------------

    @field_validator('aqid')
    @classmethod
    def aqid_must_be_valid(cls, v: str) -> str:
        if not validate_aqid(v):
            raise ValueError(
                f"Invalid AQID format: '{v}'. "
                f"Expected format: AQID-{{CLASS}}-{{SLUG}}"
            )
        return v

    @field_validator('confidence_score')
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 4)

    @field_validator('record_completeness')
    @classmethod
    def completeness_in_range(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 4)

    @field_validator('parent_aqid', mode='before')
    @classmethod
    def validate_parent_aqid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not validate_aqid(v):
            raise ValueError(f"Invalid parent AQID: '{v}'")
        return v

    # ------------------------------------------------------------------
    # COMPUTED PROPERTIES
    # ------------------------------------------------------------------

    def compute_confidence(self) -> float:
        """Recompute and update confidence_score from current sources."""
        score = compute_entity_confidence(self.all_sources, self.verification_status)
        self.confidence_score = score
        return score

    def compute_completeness(self) -> float:
        """
        Score record completeness as fraction of non-None core fields.
        Extension data completeness is class-specific and computed separately.
        """
        core_fields = [
            self.display_name,
            self.description,
            self.long_description,
            self.founded_or_created,
            self.primary_provenance,
            self.tags,
            self.domains,
            self.timeline_events,
            self.qdrant_chunk_ids,
        ]
        populated = sum(1 for f in core_fields if f not in (None, [], {}, ""))
        score = round(populated / len(core_fields), 4)
        self.record_completeness = score
        return score

    def add_timeline_event(self, event: TimelineEvent) -> None:
        """Append a timeline event and maintain chronological order."""
        self.timeline_events.append(event)
        self.timeline_events.sort(key=lambda e: e.date or date.min)

    def add_source(self, source: ProvenanceRecord, recompute: bool = True) -> None:
        """Add a provenance source and optionally recompute confidence."""
        self.all_sources.append(source)
        if recompute:
            self.compute_confidence()

    def add_change_log_entry(
        self,
        field_name: str,
        old_value: Any,
        new_value: Any,
        changed_by: str = "system",
        reason: Optional[str] = None,
    ) -> None:
        """Record a field-level change for audit trail."""
        entry = ChangeLogEntry(
            changed_by=changed_by,
            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            change_reason=reason,
        )
        self.change_log.append(entry)
        self.updated_at = datetime.utcnow()
        self.updated_by = changed_by

    def push_version(
        self,
        summary: str,
        changed_by: str = "system",
        change_type: ChangeType = ChangeType.UPDATED,
        field_diff: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Increment version and record history entry."""
        parts = self.current_version.split('.')
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = '.'.join(parts)
        self.version_history.append(VersionEntry(
            version=new_version,
            changed_by=changed_by,
            change_type=change_type,
            summary=summary,
            field_diff=field_diff,
        ))
        self.current_version = new_version
        self.updated_at = datetime.utcnow()

    def to_neo4j_node(self) -> Dict[str, Any]:
        """
        Return the minimal property set for Neo4j node creation/update.
        Neo4j nodes carry only what graph traversal requires.
        Full entity data remains authoritative in PostgreSQL.
        """
        return {
            "aqid":             self.aqid,
            "display_name":     self.display_name,
            "short_name":       self.short_name,
            "entity_class":     self.entity_class.value,
            "entity_subclass":  self.entity_subclass.value if self.entity_subclass else None,
            "is_active":        self.is_active,
            "lifecycle_status": self.lifecycle_status.value,
            "confidence_score": self.confidence_score,
            "tags":             self.tags,
            "updated_at":       self.updated_at.isoformat(),
        }

    def to_qdrant_payload(self) -> Dict[str, Any]:
        """
        Return metadata payload for Qdrant point storage.
        Stored alongside embedding vectors for filtered retrieval.
        """
        return {
            "aqid":             self.aqid,
            "entity_class":     self.entity_class.value,
            "display_name":     self.display_name,
            "description":      self.description,
            "domains":          self.domains,
            "tags":             self.tags,
            "regions":          self.regions,
            "lifecycle_status": self.lifecycle_status.value,
            "confidence_score": self.confidence_score,
            "updated_at":       self.updated_at.isoformat(),
        }

    class Config:
        use_enum_values = False
        validate_assignment = True
