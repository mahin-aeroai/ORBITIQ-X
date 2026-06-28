# ORBITIQ-X CAEM Package
# Phase 17.1 — Canonical Aerospace Entity Model

from caem.base import (
    BaseAerospaceEntity,
    EntityClass,
    EntitySubclass,
    LifecycleStatus,
    VerificationStatus,
    SourceType,
    DatePrecision,
    ChangeType,
    ImportanceLevel,
    ProvenanceRecord,
    TimelineEvent,
    VersionEntry,
    ChangeLogEntry,
    ExternalIdRecord,
    DocumentRef,
    AIIntelligenceBlock,
    generate_aqid,
    validate_aqid,
    aqid_entity_class,
    compute_entity_confidence,
    SOURCE_AUTHORITY_WEIGHT,
    VERIFICATION_STATUS_WEIGHT,
)

from caem.entities import (
    EXTENSION_REGISTRY,
    validate_extension,
    # Actor extensions
    CountryExtension,
    GovernmentAgencyExtension,
    CommercialCompanyExtension,
    UniversityExtension,
    PersonExtension,
    # Hardware extensions
    LaunchVehicleExtension,
    SatelliteExtension,
    ComponentExtension,
    # Infrastructure extensions
    LaunchSiteExtension,
    GroundStationExtension,
    # Program & mission extensions
    ProgramExtension,
    MissionExtension,
    ConstellationExtension,
    # Knowledge extensions
    TechnologyExtension,
    StandardExtension,
    ResearchPaperExtension,
    PatentExtension,
    # Commercial extensions
    ContractExtension,
    InvestmentExtension,
    # Event extensions
    IncidentExtension,
    # Celestial extensions
    CelestialBodyExtension,
)

from caem.relationships import (
    RelationshipType,
    AerospaceRelationship,
    RELATIONSHIP_CATEGORIES,
    TRAVERSAL_PATTERNS,
)

__all__ = [
    "BaseAerospaceEntity",
    "EntityClass",
    "EntitySubclass",
    "LifecycleStatus",
    "VerificationStatus",
    "SourceType",
    "DatePrecision",
    "ChangeType",
    "ImportanceLevel",
    "ProvenanceRecord",
    "TimelineEvent",
    "VersionEntry",
    "ChangeLogEntry",
    "ExternalIdRecord",
    "DocumentRef",
    "AIIntelligenceBlock",
    "generate_aqid",
    "validate_aqid",
    "aqid_entity_class",
    "compute_entity_confidence",
    "SOURCE_AUTHORITY_WEIGHT",
    "VERIFICATION_STATUS_WEIGHT",
    "EXTENSION_REGISTRY",
    "validate_extension",
    "RelationshipType",
    "AerospaceRelationship",
    "RELATIONSHIP_CATEGORIES",
    "TRAVERSAL_PATTERNS",
]

CAEM_VERSION = "17.1.0"
