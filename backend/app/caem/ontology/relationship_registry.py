"""
ORBITIQ-X — Universal Relationship Ontology Registry
Phase 17.2

This module is the authoritative source of truth for every relationship
type in the Aerospace Knowledge Universe. It extends Phase 17.1's
RelationshipType enum with:

  1. Formal cardinality rules (ONE_TO_ONE, ONE_TO_MANY, MANY_TO_MANY)
  2. Direction semantics (which entity class is source vs target)
  3. Allowed entity class pairs (enforced at ingestion and API layer)
  4. Temporal semantics (is `since`/`until` meaningful for this type?)
  5. Confidence floor per relationship category
  6. Human-readable descriptions for the frontend relationship panels

Usage:
    from caem.ontology.relationship_registry import (
        RELATIONSHIP_REGISTRY,
        get_definition,
        validate_relationship_classes,
        get_relationships_for_class,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from caem.base import EntityClass
from caem.relationships import RelationshipType, RELATIONSHIP_CATEGORIES


# ---------------------------------------------------------------------------
# CARDINALITY ENUM
# ---------------------------------------------------------------------------

class Cardinality(str, Enum):
    ONE_TO_ONE   = "ONE_TO_ONE"    # At most one of this relationship per source
    ONE_TO_MANY  = "ONE_TO_MANY"   # Source can have many targets; target has one source
    MANY_TO_ONE  = "MANY_TO_ONE"   # Many sources share one target
    MANY_TO_MANY = "MANY_TO_MANY"  # Unconstrained


# ---------------------------------------------------------------------------
# RELATIONSHIP DEFINITION
# ---------------------------------------------------------------------------

@dataclass
class RelationshipDefinition:
    """
    Formal specification for a single relationship type.
    Enforced by the ingestion pipeline and relationship validation API.
    """
    rel_type:           RelationshipType
    category:           str                         # from RELATIONSHIP_CATEGORIES keys
    description:        str                         # Human-readable purpose
    direction_note:     str                         # "Source → Target" description
    cardinality:        Cardinality

    # Allowed source entity classes (empty set = any class allowed)
    allowed_sources:    Set[EntityClass]            = field(default_factory=set)
    # Allowed target entity classes (empty set = any class allowed)
    allowed_targets:    Set[EntityClass]            = field(default_factory=set)

    # Temporal semantics
    temporal:           bool = False                # True if since/until is meaningful
    temporal_note:      str  = ""                   # Explanation of what since/until mean

    # Trust
    confidence_floor:   float = 0.50               # Minimum acceptable confidence
    is_bidirectional:   bool  = False               # Store inverse automatically?

    # Frontend display
    display_label:      str   = ""                  # Short label for graph edges
    inverse_label:      str   = ""                  # Label when traversed in reverse


# ---------------------------------------------------------------------------
# ENTITY CLASS SHORTHAND SETS (for readability in registry below)
# ---------------------------------------------------------------------------

_ACTORS = {
    EntityClass.COUNTRY, EntityClass.GOV_AGENCY, EntityClass.COMPANY,
    EntityClass.UNIVERSITY, EntityClass.RESEARCH_ORG,
}
_ORGS = _ACTORS  # Alias

_HARDWARE = {
    EntityClass.LAUNCH_VEHICLE, EntityClass.SATELLITE, EntityClass.PAYLOAD,
    EntityClass.SPACECRAFT, EntityClass.DEBRIS, EntityClass.COMPONENT,
    EntityClass.SENSOR, EntityClass.INSTRUMENT,
}

_PROGRAMS = {
    EntityClass.PROGRAM, EntityClass.MISSION, EntityClass.CONSTELLATION,
}

_KNOWLEDGE = {
    EntityClass.TECHNOLOGY, EntityClass.STANDARD, EntityClass.SPECIFICATION,
    EntityClass.RESEARCH_PAPER, EntityClass.PATENT,
}

_COMMERCIAL = {
    EntityClass.CONTRACT, EntityClass.INVESTMENT,
    EntityClass.PRODUCT, EntityClass.SERVICE,
}

_EVENTS = {
    EntityClass.HISTORICAL_EVENT, EntityClass.INCIDENT,
    EntityClass.ANOMALY, EntityClass.NEWS,
}

_PLACES = {
    EntityClass.LAUNCH_SITE, EntityClass.GROUND_STATION,
    EntityClass.TRACKING_NETWORK,
}

_CELESTIAL = {
    EntityClass.ASTEROID, EntityClass.COMET, EntityClass.CELESTIAL_BODY,
}

_ALL = set(EntityClass)


# ---------------------------------------------------------------------------
# RELATIONSHIP REGISTRY
# 76 entries — one per RelationshipType
# ---------------------------------------------------------------------------

RELATIONSHIP_REGISTRY: Dict[RelationshipType, RelationshipDefinition] = {

    # =========================================================================
    # ORGANIZATIONAL
    # =========================================================================

    RelationshipType.PART_OF: RelationshipDefinition(
        rel_type        = RelationshipType.PART_OF,
        category        = "organizational",
        description     = "Entity is a structural part of a larger entity.",
        direction_note  = "Child → Parent",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _ALL - _CELESTIAL,
        allowed_targets = _ALL - _CELESTIAL,
        temporal        = True,
        temporal_note   = "Marks when the entity became/stopped being part of the parent.",
        confidence_floor= 0.70,
        display_label   = "part of",
        inverse_label   = "contains",
    ),

    RelationshipType.SUBSIDIARY_OF: RelationshipDefinition(
        rel_type        = RelationshipType.SUBSIDIARY_OF,
        category        = "organizational",
        description     = "Commercial company is wholly or partially owned by a parent company.",
        direction_note  = "Subsidiary → Parent Company",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.COMPANY},
        allowed_targets = {EntityClass.COMPANY},
        temporal        = True,
        temporal_note   = "Acquisition date (since) and divestiture date (until).",
        confidence_floor= 0.75,
        display_label   = "subsidiary of",
        inverse_label   = "owns",
    ),

    RelationshipType.DEPARTMENT_OF: RelationshipDefinition(
        rel_type        = RelationshipType.DEPARTMENT_OF,
        category        = "organizational",
        description     = "Division or department within an organization.",
        direction_note  = "Division → Organization",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _ACTORS,
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "department of",
        inverse_label   = "has department",
    ),

    RelationshipType.MEMBER_OF: RelationshipDefinition(
        rel_type        = RelationshipType.MEMBER_OF,
        category        = "organizational",
        description     = "Entity is a member of an alliance, consortium, or treaty body.",
        direction_note  = "Member → Alliance/Treaty",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ACTORS,
        allowed_targets = _ACTORS | {EntityClass.AGREEMENT},
        temporal        = True,
        temporal_note   = "Membership start (since) and end/withdrawal (until).",
        confidence_floor= 0.70,
        display_label   = "member of",
        inverse_label   = "has member",
    ),

    RelationshipType.ESTABLISHED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.ESTABLISHED_BY,
        category        = "organizational",
        description     = "Agency or organization was established/founded by a country or governing body.",
        direction_note  = "Agency → Founding Country/Authority",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.GOV_AGENCY, EntityClass.COMPANY, EntityClass.UNIVERSITY},
        allowed_targets = {EntityClass.COUNTRY, EntityClass.GOV_AGENCY},
        temporal        = True,
        temporal_note   = "Founding date stored in `since`.",
        confidence_floor= 0.75,
        display_label   = "established by",
        inverse_label   = "established",
    ),

    RelationshipType.GOVERNED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.GOVERNED_BY,
        category        = "organizational",
        description     = "Program or mission is governed/overseen by an agency.",
        direction_note  = "Program/Mission → Governing Agency",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _PROGRAMS,
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.70,
        display_label   = "governed by",
        inverse_label   = "governs",
    ),

    RelationshipType.FUNDED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.FUNDED_BY,
        category        = "organizational",
        description     = "Mission, program, or company receives funding from an organization or investment.",
        direction_note  = "Recipient → Funder",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _PROGRAMS | _ACTORS | _HARDWARE,
        allowed_targets = _ACTORS | {EntityClass.INVESTMENT},
        temporal        = True,
        temporal_note   = "Funding period start (since) and end (until).",
        confidence_floor= 0.65,
        display_label   = "funded by",
        inverse_label   = "funds",
    ),

    RelationshipType.ACQUIRED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.ACQUIRED_BY,
        category        = "organizational",
        description     = "Company was acquired by another company.",
        direction_note  = "Acquired Company → Acquirer",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.COMPANY},
        allowed_targets = {EntityClass.COMPANY},
        temporal        = True,
        temporal_note   = "Acquisition date stored in `since`.",
        confidence_floor= 0.80,
        display_label   = "acquired by",
        inverse_label   = "acquired",
    ),

    RelationshipType.COLLABORATES_WITH: RelationshipDefinition(
        rel_type        = RelationshipType.COLLABORATES_WITH,
        category        = "organizational",
        description     = "Organizations actively collaborate on a project or program.",
        direction_note  = "Organization ↔ Organization (bidirectional — store both directions)",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ACTORS,
        allowed_targets = _ACTORS,
        temporal        = True,
        is_bidirectional= True,
        confidence_floor= 0.60,
        display_label   = "collaborates with",
        inverse_label   = "collaborates with",
    ),

    RelationshipType.COMPETES_WITH: RelationshipDefinition(
        rel_type        = RelationshipType.COMPETES_WITH,
        category        = "organizational",
        description     = "Commercial companies compete in the same market segment.",
        direction_note  = "Company ↔ Company (bidirectional)",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.COMPANY},
        allowed_targets = {EntityClass.COMPANY},
        temporal        = True,
        is_bidirectional= True,
        confidence_floor= 0.55,
        display_label   = "competes with",
        inverse_label   = "competes with",
    ),

    # =========================================================================
    # OPERATIONAL
    # =========================================================================

    RelationshipType.OPERATED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.OPERATED_BY,
        category        = "operational",
        description     = "Satellite or spacecraft is operated by an organization.",
        direction_note  = "Satellite/Spacecraft → Operator Organization",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {
            EntityClass.SATELLITE, EntityClass.PAYLOAD,
            EntityClass.SPACECRAFT, EntityClass.GROUND_STATION,
        },
        allowed_targets = _ACTORS,
        temporal        = True,
        temporal_note   = "Operational period. `until` null if still active.",
        confidence_floor= 0.70,
        display_label   = "operated by",
        inverse_label   = "operates",
    ),

    RelationshipType.MANAGED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.MANAGED_BY,
        category        = "operational",
        description     = "Mission is managed by an agency or company.",
        direction_note  = "Mission → Managing Organization",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _PROGRAMS,
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.70,
        display_label   = "managed by",
        inverse_label   = "manages",
    ),

    RelationshipType.CONTROLLED_FROM: RelationshipDefinition(
        rel_type        = RelationshipType.CONTROLLED_FROM,
        category        = "operational",
        description     = "Satellite is commanded and controlled from a ground station.",
        direction_note  = "Satellite → Ground Station",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.SATELLITE, EntityClass.SPACECRAFT},
        allowed_targets = {EntityClass.GROUND_STATION, EntityClass.TRACKING_NETWORK},
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "controlled from",
        inverse_label   = "controls",
    ),

    RelationshipType.LAUNCHED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.LAUNCHED_BY,
        category        = "operational",
        description     = "Payload or satellite was launched by a specific launch vehicle.",
        direction_note  = "Payload/Satellite → Launch Vehicle",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {
            EntityClass.SATELLITE, EntityClass.PAYLOAD,
            EntityClass.SPACECRAFT, EntityClass.MISSION,
        },
        allowed_targets = {EntityClass.LAUNCH_VEHICLE},
        temporal        = True,
        temporal_note   = "`since` = launch date.",
        confidence_floor= 0.75,
        display_label   = "launched by",
        inverse_label   = "launched",
    ),

    RelationshipType.LAUNCHED_FROM: RelationshipDefinition(
        rel_type        = RelationshipType.LAUNCHED_FROM,
        category        = "operational",
        description     = "Launch vehicle or mission launched from a specific launch site.",
        direction_note  = "Launch Vehicle/Mission → Launch Site",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.LAUNCH_VEHICLE, EntityClass.MISSION},
        allowed_targets = {EntityClass.LAUNCH_SITE},
        temporal        = True,
        temporal_note   = "`since` = launch date.",
        confidence_floor= 0.75,
        display_label   = "launched from",
        inverse_label   = "launch site for",
    ),

    RelationshipType.TRACKED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.TRACKED_BY,
        category        = "operational",
        description     = "Satellite is tracked by a ground station or tracking network.",
        direction_note  = "Satellite → Tracking Network/Ground Station",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.SATELLITE, EntityClass.DEBRIS},
        allowed_targets = {EntityClass.GROUND_STATION, EntityClass.TRACKING_NETWORK},
        temporal        = False,
        confidence_floor= 0.60,
        display_label   = "tracked by",
        inverse_label   = "tracks",
    ),

    RelationshipType.SERVICED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.SERVICED_BY,
        category        = "operational",
        description     = "Satellite was serviced, repaired, or refueled by a service mission.",
        direction_note  = "Satellite → Service Mission",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.SATELLITE, EntityClass.SPACECRAFT},
        allowed_targets = {EntityClass.MISSION},
        temporal        = True,
        confidence_floor= 0.75,
        display_label   = "serviced by",
        inverse_label   = "serviced",
    ),

    RelationshipType.DEPLOYED_FROM: RelationshipDefinition(
        rel_type        = RelationshipType.DEPLOYED_FROM,
        category        = "operational",
        description     = "Payload was deployed from a spacecraft or upper stage.",
        direction_note  = "Payload → Deploying Spacecraft/Stage",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.SATELLITE, EntityClass.PAYLOAD},
        allowed_targets = {EntityClass.SPACECRAFT, EntityClass.LAUNCH_VEHICLE, EntityClass.MISSION},
        temporal        = True,
        temporal_note   = "`since` = deployment date.",
        confidence_floor= 0.75,
        display_label   = "deployed from",
        inverse_label   = "deployed",
    ),

    RelationshipType.LANDED_ON: RelationshipDefinition(
        rel_type        = RelationshipType.LANDED_ON,
        category        = "operational",
        description     = "Spacecraft or lander successfully landed on a celestial body.",
        direction_note  = "Spacecraft/Mission → Celestial Body",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.SPACECRAFT, EntityClass.MISSION},
        allowed_targets = _CELESTIAL,
        temporal        = True,
        temporal_note   = "`since` = landing date.",
        confidence_floor= 0.85,
        display_label   = "landed on",
        inverse_label   = "landing site for",
    ),

    RelationshipType.ORBITS: RelationshipDefinition(
        rel_type        = RelationshipType.ORBITS,
        category        = "operational",
        description     = "Satellite or spacecraft orbits a celestial body.",
        direction_note  = "Satellite/Spacecraft → Celestial Body",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {
            EntityClass.SATELLITE, EntityClass.SPACECRAFT,
            EntityClass.PAYLOAD, EntityClass.DEBRIS,
        },
        allowed_targets = _CELESTIAL,
        temporal        = True,
        confidence_floor= 0.70,
        display_label   = "orbits",
        inverse_label   = "orbited by",
    ),

    RelationshipType.RENDEZVOUSED_WITH: RelationshipDefinition(
        rel_type        = RelationshipType.RENDEZVOUSED_WITH,
        category        = "operational",
        description     = "Spacecraft rendezvoused or docked with another spacecraft or station.",
        direction_note  = "Spacecraft ↔ Spacecraft/Station",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.SPACECRAFT, EntityClass.MISSION},
        allowed_targets = {EntityClass.SPACECRAFT, EntityClass.SATELLITE},
        temporal        = True,
        is_bidirectional= True,
        confidence_floor= 0.80,
        display_label   = "rendezvoused with",
        inverse_label   = "rendezvoused with",
    ),

    # =========================================================================
    # SUPPLY CHAIN
    # =========================================================================

    RelationshipType.MANUFACTURED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.MANUFACTURED_BY,
        category        = "supply_chain",
        description     = "Hardware was manufactured by an organization.",
        direction_note  = "Hardware → Manufacturer",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _HARDWARE | _PLACES,
        allowed_targets = _ACTORS,
        temporal        = False,
        confidence_floor= 0.75,
        display_label   = "manufactured by",
        inverse_label   = "manufactured",
    ),

    RelationshipType.DESIGNED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.DESIGNED_BY,
        category        = "supply_chain",
        description     = "System or hardware was designed by an organization.",
        direction_note  = "Hardware/Software → Designer",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE | _KNOWLEDGE,
        allowed_targets = _ACTORS,
        temporal        = False,
        confidence_floor= 0.65,
        display_label   = "designed by",
        inverse_label   = "designed",
    ),

    RelationshipType.SUPPLIED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.SUPPLIED_BY,
        category        = "supply_chain",
        description     = "Component or subsystem is supplied by a vendor.",
        direction_note  = "Component → Supplier",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.COMPONENT, EntityClass.SENSOR, EntityClass.INSTRUMENT},
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "supplied by",
        inverse_label   = "supplies",
    ),

    RelationshipType.COMPONENT_OF: RelationshipDefinition(
        rel_type        = RelationshipType.COMPONENT_OF,
        category        = "supply_chain",
        description     = "Component is part of a larger system.",
        direction_note  = "Component → Parent System",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.COMPONENT, EntityClass.SENSOR, EntityClass.INSTRUMENT},
        allowed_targets = _HARDWARE,
        temporal        = False,
        confidence_floor= 0.70,
        display_label   = "component of",
        inverse_label   = "has component",
    ),

    RelationshipType.USES_COMPONENT: RelationshipDefinition(
        rel_type        = RelationshipType.USES_COMPONENT,
        category        = "supply_chain",
        description     = "System incorporates a specific component.",
        direction_note  = "System → Component",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE,
        allowed_targets = {EntityClass.COMPONENT, EntityClass.SENSOR, EntityClass.INSTRUMENT},
        temporal        = False,
        confidence_floor= 0.65,
        display_label   = "uses component",
        inverse_label   = "used in",
    ),

    RelationshipType.USES_MATERIAL: RelationshipDefinition(
        rel_type        = RelationshipType.USES_MATERIAL,
        category        = "supply_chain",
        description     = "Hardware uses a specific material in its construction.",
        direction_note  = "Hardware → Material",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE,
        allowed_targets = {EntityClass.MATERIAL},
        temporal        = False,
        confidence_floor= 0.60,
        display_label   = "uses material",
        inverse_label   = "used in",
    ),

    RelationshipType.PRODUCED_UNDER: RelationshipDefinition(
        rel_type        = RelationshipType.PRODUCED_UNDER,
        category        = "supply_chain",
        description     = "Hardware was produced under a specific contract.",
        direction_note  = "Hardware → Contract",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _HARDWARE,
        allowed_targets = {EntityClass.CONTRACT},
        temporal        = False,
        confidence_floor= 0.70,
        display_label   = "produced under",
        inverse_label   = "covers production of",
    ),

    RelationshipType.LICENSED_FROM: RelationshipDefinition(
        rel_type        = RelationshipType.LICENSED_FROM,
        category        = "supply_chain",
        description     = "Technology or product is licensed from another organization.",
        direction_note  = "Technology/Product → License Holder",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _KNOWLEDGE | {EntityClass.PRODUCT},
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.70,
        display_label   = "licensed from",
        inverse_label   = "licensed to",
    ),

    # =========================================================================
    # TECHNICAL
    # =========================================================================

    RelationshipType.USES_TECHNOLOGY: RelationshipDefinition(
        rel_type        = RelationshipType.USES_TECHNOLOGY,
        category        = "technical",
        description     = "Mission, hardware, or program employs a specific technology.",
        direction_note  = "Mission/Hardware → Technology",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE | _PROGRAMS | _ACTORS,
        allowed_targets = {EntityClass.TECHNOLOGY},
        temporal        = False,
        confidence_floor= 0.60,
        display_label   = "uses technology",
        inverse_label   = "used in",
    ),

    RelationshipType.IMPLEMENTS: RelationshipDefinition(
        rel_type        = RelationshipType.IMPLEMENTS,
        category        = "technical",
        description     = "Hardware or process implements a standard or specification.",
        direction_note  = "Hardware/Process → Standard",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE | _PROGRAMS | _ACTORS,
        allowed_targets = {EntityClass.STANDARD, EntityClass.SPECIFICATION},
        temporal        = True,
        confidence_floor= 0.70,
        display_label   = "implements",
        inverse_label   = "implemented by",
    ),

    RelationshipType.CERTIFIED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.CERTIFIED_BY,
        category        = "technical",
        description     = "Hardware or process is certified by a standards body or agency.",
        direction_note  = "Hardware/Process → Certifying Body",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE | _PROGRAMS,
        allowed_targets = _ACTORS,
        temporal        = True,
        temporal_note   = "Certification issue date (since) and expiry (until).",
        confidence_floor= 0.80,
        display_label   = "certified by",
        inverse_label   = "certified",
    ),

    RelationshipType.REQUIRES: RelationshipDefinition(
        rel_type        = RelationshipType.REQUIRES,
        category        = "technical",
        description     = "System has a hard dependency on another system or technology.",
        direction_note  = "System → Dependency",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE | _KNOWLEDGE | _PROGRAMS,
        allowed_targets = _HARDWARE | _KNOWLEDGE,
        temporal        = False,
        confidence_floor= 0.65,
        display_label   = "requires",
        inverse_label   = "required by",
    ),

    RelationshipType.ENABLES: RelationshipDefinition(
        rel_type        = RelationshipType.ENABLES,
        category        = "technical",
        description     = "Technology enables a capability or another technology.",
        direction_note  = "Technology → Capability/Technology",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.TECHNOLOGY},
        allowed_targets = {EntityClass.TECHNOLOGY, EntityClass.MISSION, EntityClass.PROGRAM},
        temporal        = False,
        confidence_floor= 0.60,
        display_label   = "enables",
        inverse_label   = "enabled by",
    ),

    RelationshipType.DERIVED_FROM: RelationshipDefinition(
        rel_type        = RelationshipType.DERIVED_FROM,
        category        = "technical",
        description     = "Technology or hardware design is derived from a predecessor.",
        direction_note  = "Derived → Predecessor",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _HARDWARE | _KNOWLEDGE,
        allowed_targets = _HARDWARE | _KNOWLEDGE,
        temporal        = False,
        confidence_floor= 0.65,
        display_label   = "derived from",
        inverse_label   = "basis for",
    ),

    RelationshipType.SUCCESSOR_OF: RelationshipDefinition(
        rel_type        = RelationshipType.SUCCESSOR_OF,
        category        = "technical",
        description     = "System is the direct successor of an older system.",
        direction_note  = "New System → Predecessor System",
        cardinality     = Cardinality.ONE_TO_ONE,
        allowed_sources = _HARDWARE | _PROGRAMS | _KNOWLEDGE,
        allowed_targets = _HARDWARE | _PROGRAMS | _KNOWLEDGE,
        temporal        = True,
        temporal_note   = "`since` = when successor became operational.",
        confidence_floor= 0.75,
        display_label   = "successor of",
        inverse_label   = "preceded by",
    ),

    RelationshipType.REPLACED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.REPLACED_BY,
        category        = "technical",
        description     = "System was superseded and replaced by a newer system.",
        direction_note  = "Old System → Replacement System",
        cardinality     = Cardinality.ONE_TO_ONE,
        allowed_sources = _HARDWARE | _PROGRAMS | _KNOWLEDGE,
        allowed_targets = _HARDWARE | _PROGRAMS | _KNOWLEDGE,
        temporal        = True,
        confidence_floor= 0.75,
        display_label   = "replaced by",
        inverse_label   = "replaces",
    ),

    RelationshipType.COMPATIBLE_WITH: RelationshipDefinition(
        rel_type        = RelationshipType.COMPATIBLE_WITH,
        category        = "technical",
        description     = "Hardware or interface is compatible with another system.",
        direction_note  = "Hardware ↔ Hardware",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE | _KNOWLEDGE,
        allowed_targets = _HARDWARE | _KNOWLEDGE,
        temporal        = False,
        is_bidirectional= True,
        confidence_floor= 0.65,
        display_label   = "compatible with",
        inverse_label   = "compatible with",
    ),

    RelationshipType.INTERFERES_WITH: RelationshipDefinition(
        rel_type        = RelationshipType.INTERFERES_WITH,
        category        = "technical",
        description     = "Satellite causes RF or orbital interference with another satellite.",
        direction_note  = "Satellite ↔ Satellite",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.SATELLITE},
        allowed_targets = {EntityClass.SATELLITE},
        temporal        = True,
        is_bidirectional= True,
        confidence_floor= 0.55,
        display_label   = "interferes with",
        inverse_label   = "interferes with",
    ),

    # =========================================================================
    # SCIENTIFIC
    # =========================================================================

    RelationshipType.DISCOVERED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.DISCOVERED_BY,
        category        = "scientific",
        description     = "Celestial body or phenomenon was discovered by a person or mission.",
        direction_note  = "Celestial Body → Discoverer (Person/Mission)",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _CELESTIAL | _EVENTS,
        allowed_targets = {EntityClass.PERSON, EntityClass.MISSION},
        temporal        = True,
        temporal_note   = "`since` = discovery date.",
        confidence_floor= 0.80,
        display_label   = "discovered by",
        inverse_label   = "discovered",
    ),

    RelationshipType.STUDIED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.STUDIED_BY,
        category        = "scientific",
        description     = "Celestial body is actively studied by a mission.",
        direction_note  = "Celestial Body → Mission",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _CELESTIAL,
        allowed_targets = {EntityClass.MISSION},
        temporal        = True,
        confidence_floor= 0.70,
        display_label   = "studied by",
        inverse_label   = "studies",
    ),

    RelationshipType.INSTRUMENTS_ON: RelationshipDefinition(
        rel_type        = RelationshipType.INSTRUMENTS_ON,
        category        = "scientific",
        description     = "Scientific instrument is mounted on a spacecraft.",
        direction_note  = "Instrument → Spacecraft",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.INSTRUMENT, EntityClass.SENSOR},
        allowed_targets = {EntityClass.SPACECRAFT, EntityClass.SATELLITE},
        temporal        = False,
        confidence_floor= 0.75,
        display_label   = "instrument on",
        inverse_label   = "carries instrument",
    ),

    RelationshipType.MEASURES: RelationshipDefinition(
        rel_type        = RelationshipType.MEASURES,
        category        = "scientific",
        description     = "Instrument measures a physical phenomenon or parameter.",
        direction_note  = "Instrument → Phenomenon/Parameter",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.INSTRUMENT, EntityClass.SENSOR},
        allowed_targets = _ALL,
        temporal        = False,
        confidence_floor= 0.65,
        display_label   = "measures",
        inverse_label   = "measured by",
    ),

    RelationshipType.AUTHORED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.AUTHORED_BY,
        category        = "scientific",
        description     = "Research paper or patent was authored by a person.",
        direction_note  = "Paper/Patent → Author (Person)",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.RESEARCH_PAPER, EntityClass.PATENT},
        allowed_targets = {EntityClass.PERSON},
        temporal        = True,
        temporal_note   = "`since` = publication date.",
        confidence_floor= 0.80,
        display_label   = "authored by",
        inverse_label   = "authored",
    ),

    RelationshipType.PUBLISHED_IN: RelationshipDefinition(
        rel_type        = RelationshipType.PUBLISHED_IN,
        category        = "scientific",
        description     = "Research paper was published in a journal or conference.",
        direction_note  = "Paper → Journal/Conference Entity",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.RESEARCH_PAPER},
        allowed_targets = _ACTORS | {EntityClass.HISTORICAL_EVENT},
        temporal        = True,
        confidence_floor= 0.80,
        display_label   = "published in",
        inverse_label   = "published",
    ),

    RelationshipType.CITES: RelationshipDefinition(
        rel_type        = RelationshipType.CITES,
        category        = "scientific",
        description     = "Research paper cites another paper or standard.",
        direction_note  = "Citing Paper → Cited Paper/Standard",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.RESEARCH_PAPER},
        allowed_targets = {EntityClass.RESEARCH_PAPER, EntityClass.STANDARD, EntityClass.PATENT},
        temporal        = False,
        confidence_floor= 0.75,
        display_label   = "cites",
        inverse_label   = "cited by",
    ),

    RelationshipType.REFERENCES: RelationshipDefinition(
        rel_type        = RelationshipType.REFERENCES,
        category        = "scientific",
        description     = "Document references a standard, policy, or other document.",
        direction_note  = "Document → Referenced Document",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _KNOWLEDGE | _COMMERCIAL,
        allowed_targets = _KNOWLEDGE | {EntityClass.POLICY},
        temporal        = False,
        confidence_floor= 0.65,
        display_label   = "references",
        inverse_label   = "referenced by",
    ),

    RelationshipType.VALIDATES: RelationshipDefinition(
        rel_type        = RelationshipType.VALIDATES,
        category        = "scientific",
        description     = "Mission or experiment validates a scientific theory or model.",
        direction_note  = "Mission/Experiment → Theory/Model",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.MISSION},
        allowed_targets = {EntityClass.TECHNOLOGY, EntityClass.RESEARCH_PAPER},
        temporal        = True,
        confidence_floor= 0.70,
        display_label   = "validates",
        inverse_label   = "validated by",
    ),

    RelationshipType.MODELS: RelationshipDefinition(
        rel_type        = RelationshipType.MODELS,
        category        = "scientific",
        description     = "Software or model represents a physical system.",
        direction_note  = "Software/Model → Physical System",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.TECHNOLOGY},
        allowed_targets = _HARDWARE | _CELESTIAL,
        temporal        = False,
        confidence_floor= 0.60,
        display_label   = "models",
        inverse_label   = "modeled by",
    ),

    # =========================================================================
    # GEOGRAPHIC
    # =========================================================================

    RelationshipType.LOCATED_IN: RelationshipDefinition(
        rel_type        = RelationshipType.LOCATED_IN,
        category        = "geographic",
        description     = "Entity is physically located in a country or region.",
        direction_note  = "Organization/Site → Country/Region",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _ACTORS | _PLACES,
        allowed_targets = {EntityClass.COUNTRY},
        temporal        = True,
        temporal_note   = "Relocation: old location gets `until`, new gets new `since`.",
        confidence_floor= 0.75,
        display_label   = "located in",
        inverse_label   = "hosts",
    ),

    RelationshipType.OPERATES_IN: RelationshipDefinition(
        rel_type        = RelationshipType.OPERATES_IN,
        category        = "geographic",
        description     = "Organization has operational presence in a country or region.",
        direction_note  = "Organization → Country/Region",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ACTORS,
        allowed_targets = {EntityClass.COUNTRY},
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "operates in",
        inverse_label   = "hosts operations of",
    ),

    RelationshipType.COVERS: RelationshipDefinition(
        rel_type        = RelationshipType.COVERS,
        category        = "geographic",
        description     = "Satellite provides coverage over a geographic region.",
        direction_note  = "Satellite → Country/Region",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.SATELLITE, EntityClass.CONSTELLATION},
        allowed_targets = {EntityClass.COUNTRY},
        temporal        = False,
        confidence_floor= 0.60,
        display_label   = "covers",
        inverse_label   = "covered by",
    ),

    RelationshipType.LAUNCHES_TO: RelationshipDefinition(
        rel_type        = RelationshipType.LAUNCHES_TO,
        category        = "geographic",
        description     = "Launch site supports launches to specific orbital regimes.",
        direction_note  = "Launch Site → Orbital Regime (conceptual node)",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.LAUNCH_SITE},
        allowed_targets = _ALL,
        temporal        = False,
        confidence_floor= 0.60,
        display_label   = "launches to",
        inverse_label   = "reachable from",
    ),

    # =========================================================================
    # COMMERCIAL
    # =========================================================================

    RelationshipType.AWARDED_TO: RelationshipDefinition(
        rel_type        = RelationshipType.AWARDED_TO,
        category        = "commercial",
        description     = "Contract was awarded to a company or organization.",
        direction_note  = "Contract → Recipient",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.CONTRACT},
        allowed_targets = _ACTORS,
        temporal        = True,
        temporal_note   = "`since` = award date, `until` = contract end.",
        confidence_floor= 0.80,
        display_label   = "awarded to",
        inverse_label   = "recipient of",
    ),

    RelationshipType.AWARDED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.AWARDED_BY,
        category        = "commercial",
        description     = "Contract was awarded by a client organization.",
        direction_note  = "Contract → Client/Awarding Body",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.CONTRACT},
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.80,
        display_label   = "awarded by",
        inverse_label   = "awarded contract",
    ),

    RelationshipType.INVESTED_IN: RelationshipDefinition(
        rel_type        = RelationshipType.INVESTED_IN,
        category        = "commercial",
        description     = "Investment was made into a company or program.",
        direction_note  = "Investment → Recipient Company/Program",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = {EntityClass.INVESTMENT},
        allowed_targets = _ACTORS | _PROGRAMS,
        temporal        = True,
        temporal_note   = "`since` = investment close date.",
        confidence_floor= 0.75,
        display_label   = "invested in",
        inverse_label   = "received investment",
    ),

    RelationshipType.INSURED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.INSURED_BY,
        category        = "commercial",
        description     = "Mission or hardware is insured by an insurance provider.",
        direction_note  = "Mission/Hardware → Insurer",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _HARDWARE | _PROGRAMS,
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "insured by",
        inverse_label   = "insures",
    ),

    RelationshipType.PROVIDES_SERVICE_TO: RelationshipDefinition(
        rel_type        = RelationshipType.PROVIDES_SERVICE_TO,
        category        = "commercial",
        description     = "Organization provides a service to a client organization.",
        direction_note  = "Service Provider → Client",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ACTORS,
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "provides service to",
        inverse_label   = "receives service from",
    ),

    RelationshipType.COMPETES_FOR: RelationshipDefinition(
        rel_type        = RelationshipType.COMPETES_FOR,
        category        = "commercial",
        description     = "Company is competing for a contract or program.",
        direction_note  = "Company → Contract/Program",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.COMPANY},
        allowed_targets = {EntityClass.CONTRACT, EntityClass.PROGRAM},
        temporal        = True,
        confidence_floor= 0.55,
        display_label   = "competes for",
        inverse_label   = "competed for by",
    ),

    # =========================================================================
    # REGULATORY
    # =========================================================================

    RelationshipType.REGULATED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.REGULATED_BY,
        category        = "regulatory",
        description     = "Company or mission is regulated by a government agency.",
        direction_note  = "Company/Mission → Regulatory Agency",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ACTORS | _PROGRAMS | _HARDWARE,
        allowed_targets = {EntityClass.GOV_AGENCY},
        temporal        = True,
        confidence_floor= 0.70,
        display_label   = "regulated by",
        inverse_label   = "regulates",
    ),

    RelationshipType.LICENSED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.LICENSED_BY,
        category        = "regulatory",
        description     = "Satellite operator holds a license from a regulatory body.",
        direction_note  = "Operator → Regulatory Body",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ACTORS,
        allowed_targets = {EntityClass.GOV_AGENCY},
        temporal        = True,
        temporal_note   = "License validity period.",
        confidence_floor= 0.75,
        display_label   = "licensed by",
        inverse_label   = "issued license to",
    ),

    RelationshipType.COMPLIES_WITH: RelationshipDefinition(
        rel_type        = RelationshipType.COMPLIES_WITH,
        category        = "regulatory",
        description     = "Hardware, process, or organization complies with a standard or policy.",
        direction_note  = "Entity → Standard/Policy",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _HARDWARE | _ACTORS | _PROGRAMS,
        allowed_targets = {EntityClass.STANDARD, EntityClass.SPECIFICATION, EntityClass.POLICY},
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "complies with",
        inverse_label   = "required of",
    ),

    RelationshipType.PROHIBITED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.PROHIBITED_BY,
        category        = "regulatory",
        description     = "Activity or entity is prohibited by a policy or treaty.",
        direction_note  = "Activity/Entity → Prohibiting Policy/Treaty",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ALL,
        allowed_targets = {EntityClass.POLICY, EntityClass.AGREEMENT},
        temporal        = True,
        confidence_floor= 0.75,
        display_label   = "prohibited by",
        inverse_label   = "prohibits",
    ),

    RelationshipType.RATIFIED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.RATIFIED_BY,
        category        = "regulatory",
        description     = "Treaty or international agreement was ratified by a country.",
        direction_note  = "Treaty/Agreement → Ratifying Country",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.AGREEMENT, EntityClass.POLICY},
        allowed_targets = {EntityClass.COUNTRY},
        temporal        = True,
        temporal_note   = "`since` = ratification date.",
        confidence_floor= 0.85,
        display_label   = "ratified by",
        inverse_label   = "ratified",
    ),

    RelationshipType.SANCTIONS: RelationshipDefinition(
        rel_type        = RelationshipType.SANCTIONS,
        category        = "regulatory",
        description     = "Policy or country imposes sanctions on an entity.",
        direction_note  = "Policy/Country → Sanctioned Entity",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.POLICY, EntityClass.COUNTRY},
        allowed_targets = _ACTORS,
        temporal        = True,
        confidence_floor= 0.80,
        display_label   = "sanctions",
        inverse_label   = "sanctioned by",
    ),

    # =========================================================================
    # HISTORICAL / TEMPORAL
    # =========================================================================

    RelationshipType.PRECEDED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.PRECEDED_BY,
        category        = "historical",
        description     = "Event or program was preceded by an earlier event or program.",
        direction_note  = "Later Event → Earlier Event",
        cardinality     = Cardinality.MANY_TO_ONE,
        allowed_sources = _EVENTS | _PROGRAMS,
        allowed_targets = _EVENTS | _PROGRAMS,
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "preceded by",
        inverse_label   = "followed by",
    ),

    RelationshipType.CAUSED: RelationshipDefinition(
        rel_type        = RelationshipType.CAUSED,
        category        = "historical",
        description     = "Event caused a consequence event.",
        direction_note  = "Cause Event → Consequence Event",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _EVENTS | _PROGRAMS,
        allowed_targets = _EVENTS | _PROGRAMS | {EntityClass.POLICY},
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "caused",
        inverse_label   = "caused by",
    ),

    RelationshipType.TRIGGERED: RelationshipDefinition(
        rel_type        = RelationshipType.TRIGGERED,
        category        = "historical",
        description     = "Incident or event triggered a policy change or technical response.",
        direction_note  = "Incident → Policy/Technical Change",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _EVENTS,
        allowed_targets = {EntityClass.POLICY, EntityClass.STANDARD, EntityClass.TECHNOLOGY},
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "triggered",
        inverse_label   = "triggered by",
    ),

    RelationshipType.EVOLVED_INTO: RelationshipDefinition(
        rel_type        = RelationshipType.EVOLVED_INTO,
        category        = "historical",
        description     = "Program or technology evolved into a successor program.",
        direction_note  = "Earlier Program/Tech → Successor",
        cardinality     = Cardinality.ONE_TO_ONE,
        allowed_sources = _PROGRAMS | _KNOWLEDGE,
        allowed_targets = _PROGRAMS | _KNOWLEDGE,
        temporal        = True,
        confidence_floor= 0.65,
        display_label   = "evolved into",
        inverse_label   = "evolved from",
    ),

    RelationshipType.BASED_ON: RelationshipDefinition(
        rel_type        = RelationshipType.BASED_ON,
        category        = "historical",
        description     = "Mission or design is based on a prior mission or design heritage.",
        direction_note  = "New Mission/Design → Prior Mission/Design",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _PROGRAMS | _HARDWARE,
        allowed_targets = _PROGRAMS | _HARDWARE,
        temporal        = False,
        confidence_floor= 0.60,
        display_label   = "based on",
        inverse_label   = "heritage for",
    ),

    RelationshipType.COMMEMORATES: RelationshipDefinition(
        rel_type        = RelationshipType.COMMEMORATES,
        category        = "historical",
        description     = "Event or mission commemorates a historical entity or event.",
        direction_note  = "Commemorating Event → Historical Entity",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _EVENTS | _PROGRAMS,
        allowed_targets = _EVENTS | {EntityClass.PERSON},
        temporal        = True,
        confidence_floor= 0.55,
        display_label   = "commemorates",
        inverse_label   = "commemorated by",
    ),

    # =========================================================================
    # KNOWLEDGE GRAPH
    # =========================================================================

    RelationshipType.MENTIONED_IN: RelationshipDefinition(
        rel_type        = RelationshipType.MENTIONED_IN,
        category        = "knowledge",
        description     = "Entity is mentioned in a document or publication.",
        direction_note  = "Entity → Document",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ALL,
        allowed_targets = _KNOWLEDGE | _EVENTS,
        temporal        = False,
        confidence_floor= 0.55,
        display_label   = "mentioned in",
        inverse_label   = "mentions",
    ),

    RelationshipType.DESCRIBED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.DESCRIBED_BY,
        category        = "knowledge",
        description     = "Entity is formally described by a research paper or report.",
        direction_note  = "Entity → Research Paper",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = _ALL,
        allowed_targets = {EntityClass.RESEARCH_PAPER},
        temporal        = False,
        confidence_floor= 0.65,
        display_label   = "described by",
        inverse_label   = "describes",
    ),

    RelationshipType.STANDARDIZED_IN: RelationshipDefinition(
        rel_type        = RelationshipType.STANDARDIZED_IN,
        category        = "knowledge",
        description     = "Technology or interface is standardized in a formal standard.",
        direction_note  = "Technology → Standard",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.TECHNOLOGY},
        allowed_targets = {EntityClass.STANDARD, EntityClass.SPECIFICATION},
        temporal        = False,
        confidence_floor= 0.75,
        display_label   = "standardized in",
        inverse_label   = "standardizes",
    ),

    RelationshipType.PATENTED_BY: RelationshipDefinition(
        rel_type        = RelationshipType.PATENTED_BY,
        category        = "knowledge",
        description     = "Technology is protected by a patent.",
        direction_note  = "Technology → Patent",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.TECHNOLOGY},
        allowed_targets = {EntityClass.PATENT},
        temporal        = True,
        temporal_note   = "`since` = patent filing date.",
        confidence_floor= 0.80,
        display_label   = "patented by",
        inverse_label   = "covers technology",
    ),

    RelationshipType.INSPIRED: RelationshipDefinition(
        rel_type        = RelationshipType.INSPIRED,
        category        = "knowledge",
        description     = "Research or mission inspired the development of a technology.",
        direction_note  = "Research/Mission → Technology",
        cardinality     = Cardinality.MANY_TO_MANY,
        allowed_sources = {EntityClass.RESEARCH_PAPER, EntityClass.MISSION},
        allowed_targets = {EntityClass.TECHNOLOGY},
        temporal        = False,
        confidence_floor= 0.55,
        display_label   = "inspired",
        inverse_label   = "inspired by",
    ),
}


# ---------------------------------------------------------------------------
# LOOKUP HELPERS
# ---------------------------------------------------------------------------

def get_definition(rel_type: RelationshipType) -> RelationshipDefinition:
    """Return the formal definition for a relationship type. Raises KeyError if not found."""
    return RELATIONSHIP_REGISTRY[rel_type]


def validate_relationship_classes(
    rel_type: RelationshipType,
    source_class: EntityClass,
    target_class: EntityClass,
) -> Tuple[bool, str]:
    """
    Validate that source and target entity classes are allowed for the given
    relationship type.

    Returns:
        (True, "") if valid
        (False, reason) if invalid
    """
    defn = RELATIONSHIP_REGISTRY.get(rel_type)
    if defn is None:
        return False, f"Unknown relationship type: {rel_type}"

    if defn.allowed_sources and source_class not in defn.allowed_sources:
        return False, (
            f"{rel_type.value} does not allow source class {source_class.value}. "
            f"Allowed: {[c.value for c in defn.allowed_sources]}"
        )

    if defn.allowed_targets and target_class not in defn.allowed_targets:
        return False, (
            f"{rel_type.value} does not allow target class {target_class.value}. "
            f"Allowed: {[c.value for c in defn.allowed_targets]}"
        )

    return True, ""


def get_relationships_for_class(
    entity_class: EntityClass,
    as_source: bool = True,
) -> List[RelationshipDefinition]:
    """
    Return all relationship definitions where the given entity class is
    an allowed source (as_source=True) or target (as_source=False).
    """
    results = []
    for defn in RELATIONSHIP_REGISTRY.values():
        pool = defn.allowed_sources if as_source else defn.allowed_targets
        if not pool or entity_class in pool:
            results.append(defn)
    return results


def get_category_relationships(category: str) -> List[RelationshipDefinition]:
    """Return all relationship definitions for a given category."""
    return [d for d in RELATIONSHIP_REGISTRY.values() if d.category == category]


def get_temporal_relationships() -> List[RelationshipDefinition]:
    """Return all relationship types where since/until is semantically meaningful."""
    return [d for d in RELATIONSHIP_REGISTRY.values() if d.temporal]


def get_bidirectional_relationships() -> List[RelationshipDefinition]:
    """Return all relationship types that should be stored in both directions."""
    return [d for d in RELATIONSHIP_REGISTRY.values() if d.is_bidirectional]


# Coverage check — every RelationshipType must have a registry entry
_unregistered = set(RelationshipType) - set(RELATIONSHIP_REGISTRY.keys())
if _unregistered:
    raise RuntimeError(
        f"RelationshipType values missing from RELATIONSHIP_REGISTRY: "
        f"{[r.value for r in _unregistered]}"
    )
