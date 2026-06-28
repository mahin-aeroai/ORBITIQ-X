"""
ORBITIQ-X — Universal Relationship Ontology
Phase 17.1

Defines every relationship type in the Aerospace Knowledge Universe:
  - Type taxonomy organized by category
  - Cardinality and direction rules
  - Standard property set for every relationship
  - Neo4j Cypher generation helpers
  - Relationship validation

Design rules (enforced here):
  1. Every relationship is directed (source → target)
  2. Relationships flow from more specific to more general entities
  3. Every relationship carries at minimum: since, confidence, provenance_url
  4. Temporal properties (since/until) support point-in-time graph queries
  5. Relationship types use SCREAMING_SNAKE_CASE
  6. No relationship type encodes time — use temporal properties instead
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from caem.base import validate_aqid, VerificationStatus


# ---------------------------------------------------------------------------
# RELATIONSHIP TYPE TAXONOMY
# ---------------------------------------------------------------------------

class RelationshipType(str, Enum):
    """
    Complete set of typed relationships in the Aerospace Knowledge Universe.
    Organized by semantic category. All types are direction-sensitive.
    """

    # --- ORGANIZATIONAL ---
    PART_OF             = "PART_OF"             # Entity → Parent entity
    SUBSIDIARY_OF       = "SUBSIDIARY_OF"       # Subsidiary Company → Parent Company
    DEPARTMENT_OF       = "DEPARTMENT_OF"       # Division → Organization
    MEMBER_OF           = "MEMBER_OF"           # Agency → Alliance / Treaty
    ESTABLISHED_BY      = "ESTABLISHED_BY"      # Agency → Country
    GOVERNED_BY         = "GOVERNED_BY"         # Program → Governing Agency
    FUNDED_BY           = "FUNDED_BY"           # Mission/Program → Funding Source
    ACQUIRED_BY         = "ACQUIRED_BY"         # Company → Acquirer
    COLLABORATES_WITH   = "COLLABORATES_WITH"   # Organization ↔ Organization (bidirectional stored twice)
    COMPETES_WITH       = "COMPETES_WITH"       # Company ↔ Company

    # --- OPERATIONAL ---
    OPERATED_BY         = "OPERATED_BY"         # Satellite → Operator
    MANAGED_BY          = "MANAGED_BY"          # Mission → Managing Agency
    CONTROLLED_FROM     = "CONTROLLED_FROM"     # Satellite → Ground Station
    LAUNCHED_BY         = "LAUNCHED_BY"         # Satellite → Launch Vehicle
    LAUNCHED_FROM       = "LAUNCHED_FROM"       # Launch Vehicle instance → Launch Site
    TRACKED_BY          = "TRACKED_BY"          # Satellite → Tracking Network
    SERVICED_BY         = "SERVICED_BY"         # Satellite → Service Mission
    DEPLOYED_FROM       = "DEPLOYED_FROM"       # Payload → Spacecraft / LV upper stage
    LANDED_ON           = "LANDED_ON"           # Spacecraft → Celestial Body
    ORBITS              = "ORBITS"              # Satellite/Spacecraft → Celestial Body
    RENDEZVOUSED_WITH   = "RENDEZVOUSED_WITH"   # Spacecraft ↔ Spacecraft / Station

    # --- MANUFACTURING & SUPPLY CHAIN ---
    MANUFACTURED_BY     = "MANUFACTURED_BY"     # Hardware → Manufacturer
    DESIGNED_BY         = "DESIGNED_BY"         # Hardware → Designing Organization
    SUPPLIED_BY         = "SUPPLIED_BY"         # Component → Supplier
    COMPONENT_OF        = "COMPONENT_OF"        # Component → System
    USES_COMPONENT      = "USES_COMPONENT"      # System → Component
    USES_MATERIAL       = "USES_MATERIAL"       # Hardware → Material
    PRODUCED_UNDER      = "PRODUCED_UNDER"      # Hardware → Contract
    LICENSED_FROM       = "LICENSED_FROM"       # Technology → License Holder

    # --- TECHNICAL ---
    USES_TECHNOLOGY     = "USES_TECHNOLOGY"     # Mission/Hardware → Technology
    IMPLEMENTS          = "IMPLEMENTS"          # Hardware/Process → Standard
    CERTIFIED_BY        = "CERTIFIED_BY"        # Hardware/Process → Certifying Body
    REQUIRES            = "REQUIRES"            # System → Dependency
    ENABLES             = "ENABLES"             # Technology → Capability
    DERIVED_FROM        = "DERIVED_FROM"        # Technology/Hardware → Predecessor
    SUCCESSOR_OF        = "SUCCESSOR_OF"        # System/Version → Predecessor
    REPLACED_BY         = "REPLACED_BY"         # Old System → New System
    COMPATIBLE_WITH     = "COMPATIBLE_WITH"     # Hardware ↔ Hardware
    INTERFERES_WITH     = "INTERFERES_WITH"     # Satellite ↔ Satellite (spectrum/orbital)

    # --- SCIENTIFIC ---
    DISCOVERED_BY       = "DISCOVERED_BY"       # CelestialBody/Phenomenon → Discoverer
    STUDIED_BY          = "STUDIED_BY"          # CelestialBody → Mission
    INSTRUMENTS_ON      = "INSTRUMENTS_ON"      # Instrument → Spacecraft
    MEASURES            = "MEASURES"            # Instrument → Phenomenon
    AUTHORED_BY         = "AUTHORED_BY"         # Paper/Patent → Person
    PUBLISHED_IN        = "PUBLISHED_IN"        # Paper → Journal/Conference Entity
    CITES               = "CITES"              # Paper → Paper
    REFERENCES          = "REFERENCES"          # Document → Standard/Policy/Paper
    VALIDATES           = "VALIDATES"           # Mission → Theory/Hypothesis
    MODELS              = "MODELS"              # Software → Physical System

    # --- GEOGRAPHIC ---
    LOCATED_IN          = "LOCATED_IN"          # Organization/Site → Country/Region
    OPERATES_IN         = "OPERATES_IN"         # Organization → Country/Region
    COVERS              = "COVERS"              # Satellite → Geographic Region (conceptual)
    LAUNCHES_TO         = "LAUNCHES_TO"         # Launch Site → Orbit type (conceptual)

    # --- COMMERCIAL ---
    AWARDED_TO          = "AWARDED_TO"          # Contract → Recipient
    AWARDED_BY          = "AWARDED_BY"          # Contract → Client
    INVESTED_IN         = "INVESTED_IN"         # Investment → Company/Program
    INSURED_BY          = "INSURED_BY"          # Mission/Hardware → Insurer
    PROVIDES_SERVICE_TO = "PROVIDES_SERVICE_TO" # Company → Client
    COMPETES_FOR        = "COMPETES_FOR"        # Company → Contract/Program

    # --- REGULATORY ---
    REGULATED_BY        = "REGULATED_BY"        # Company/Mission → Regulatory Agency
    LICENSED_BY         = "LICENSED_BY"         # Operator → Regulatory Body
    COMPLIES_WITH       = "COMPLIES_WITH"       # Hardware/Process → Standard/Policy
    PROHIBITED_BY       = "PROHIBITED_BY"       # Activity → Policy/Treaty
    RATIFIED_BY         = "RATIFIED_BY"         # Treaty/Agreement → Country
    SANCTIONS           = "SANCTIONS"           # Policy → Entity

    # --- TEMPORAL / LINEAGE ---
    PRECEDED_BY         = "PRECEDED_BY"         # Event → Prior Event
    CAUSED              = "CAUSED"              # Event → Consequence Event
    TRIGGERED           = "TRIGGERED"           # Incident → Policy/Technical Change
    EVOLVED_INTO        = "EVOLVED_INTO"        # Program → Successor Program
    BASED_ON            = "BASED_ON"            # Mission/Design → Prior Mission/Design
    COMMEMORATES        = "COMMEMORATES"        # Event → Historical Entity

    # --- KNOWLEDGE GRAPH ---
    MENTIONED_IN        = "MENTIONED_IN"        # Entity → Document
    DESCRIBED_BY        = "DESCRIBED_BY"        # Entity → Research Paper
    STANDARDIZED_IN     = "STANDARDIZED_IN"     # Technology → Standard
    PATENTED_BY         = "PATENTED_BY"         # Technology → Patent
    INSPIRED            = "INSPIRED"            # Research → Technology


# ---------------------------------------------------------------------------
# RELATIONSHIP CATEGORY GROUPING
# Used for frontend tab group organization.
# ---------------------------------------------------------------------------

RELATIONSHIP_CATEGORIES: Dict[str, List[RelationshipType]] = {
    "organizational": [
        RelationshipType.PART_OF, RelationshipType.SUBSIDIARY_OF,
        RelationshipType.DEPARTMENT_OF, RelationshipType.MEMBER_OF,
        RelationshipType.ESTABLISHED_BY, RelationshipType.GOVERNED_BY,
        RelationshipType.FUNDED_BY, RelationshipType.ACQUIRED_BY,
        RelationshipType.COLLABORATES_WITH, RelationshipType.COMPETES_WITH,
    ],
    "operational": [
        RelationshipType.OPERATED_BY, RelationshipType.MANAGED_BY,
        RelationshipType.CONTROLLED_FROM, RelationshipType.LAUNCHED_BY,
        RelationshipType.LAUNCHED_FROM, RelationshipType.TRACKED_BY,
        RelationshipType.SERVICED_BY, RelationshipType.DEPLOYED_FROM,
        RelationshipType.LANDED_ON, RelationshipType.ORBITS,
        RelationshipType.RENDEZVOUSED_WITH,
    ],
    "supply_chain": [
        RelationshipType.MANUFACTURED_BY, RelationshipType.DESIGNED_BY,
        RelationshipType.SUPPLIED_BY, RelationshipType.COMPONENT_OF,
        RelationshipType.USES_COMPONENT, RelationshipType.USES_MATERIAL,
        RelationshipType.PRODUCED_UNDER, RelationshipType.LICENSED_FROM,
    ],
    "technical": [
        RelationshipType.USES_TECHNOLOGY, RelationshipType.IMPLEMENTS,
        RelationshipType.CERTIFIED_BY, RelationshipType.REQUIRES,
        RelationshipType.ENABLES, RelationshipType.DERIVED_FROM,
        RelationshipType.SUCCESSOR_OF, RelationshipType.REPLACED_BY,
        RelationshipType.COMPATIBLE_WITH, RelationshipType.INTERFERES_WITH,
    ],
    "scientific": [
        RelationshipType.DISCOVERED_BY, RelationshipType.STUDIED_BY,
        RelationshipType.INSTRUMENTS_ON, RelationshipType.MEASURES,
        RelationshipType.AUTHORED_BY, RelationshipType.PUBLISHED_IN,
        RelationshipType.CITES, RelationshipType.REFERENCES,
        RelationshipType.VALIDATES, RelationshipType.MODELS,
    ],
    "commercial": [
        RelationshipType.AWARDED_TO, RelationshipType.AWARDED_BY,
        RelationshipType.INVESTED_IN, RelationshipType.INSURED_BY,
        RelationshipType.PROVIDES_SERVICE_TO, RelationshipType.COMPETES_FOR,
    ],
    "regulatory": [
        RelationshipType.REGULATED_BY, RelationshipType.LICENSED_BY,
        RelationshipType.COMPLIES_WITH, RelationshipType.PROHIBITED_BY,
        RelationshipType.RATIFIED_BY, RelationshipType.SANCTIONS,
    ],
    "historical": [
        RelationshipType.PRECEDED_BY, RelationshipType.CAUSED,
        RelationshipType.TRIGGERED, RelationshipType.EVOLVED_INTO,
        RelationshipType.BASED_ON, RelationshipType.COMMEMORATES,
    ],
    "knowledge": [
        RelationshipType.MENTIONED_IN, RelationshipType.DESCRIBED_BY,
        RelationshipType.STANDARDIZED_IN, RelationshipType.PATENTED_BY,
        RelationshipType.INSPIRED,
    ],
    "geographic": [
        RelationshipType.LOCATED_IN, RelationshipType.OPERATES_IN,
        RelationshipType.COVERS, RelationshipType.LAUNCHES_TO,
    ],
}


# ---------------------------------------------------------------------------
# RELATIONSHIP PROPERTY MODEL
# ---------------------------------------------------------------------------

class AerospaceRelationship(BaseModel):
    """
    A typed, directed, timestamped relationship between two aerospace entities.

    Every relationship in the Aerospace Knowledge Universe is an instance
    of this model. Stored in Neo4j as a typed edge; the `rel_id` provides
    a stable reference for updates and deduplication.

    Direction convention:
      source_aqid → [relationship_type] → target_aqid
      e.g.  AQID-SAT-STARLINK-1024  →  [OPERATED_BY]  →  AQID-COMPANY-SPACEX
    """

    rel_id:             str     = Field(default_factory=lambda: __import__('uuid').uuid4().hex)
    source_aqid:        str
    target_aqid:        str
    relationship_type:  RelationshipType

    # Temporal properties
    since:              Optional[date]  = None    # When relationship became active
    until:              Optional[date]  = None    # When relationship ended (null = ongoing)
    is_current:         bool            = True    # Derived: since ≤ today AND (until is null OR until ≥ today)

    # Trust properties
    is_primary:         bool    = True            # Primary vs secondary/historical relationship
    confidence:         float   = Field(default=0.80, ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED

    # Provenance
    provenance_url:     Optional[str]   = None
    provenance_org:     Optional[str]   = None
    citation_text:      Optional[str]   = None

    # Semantic properties (type-specific values stored as freeform dict)
    properties:         Dict[str, Any]  = {}      # e.g. {amount_musd: 2600} for FUNDED_BY

    # Metadata
    notes:              Optional[str]   = None
    version:            int             = 1
    created_at:         str             = Field(
        default_factory=lambda: __import__('datetime').datetime.utcnow().isoformat()
    )

    def validate(self) -> List[str]:
        """Return list of validation errors. Empty list = valid."""
        errors = []
        if not validate_aqid(self.source_aqid):
            errors.append(f"Invalid source AQID: {self.source_aqid}")
        if not validate_aqid(self.target_aqid):
            errors.append(f"Invalid target AQID: {self.target_aqid}")
        if self.source_aqid == self.target_aqid:
            errors.append("Self-referential relationship not permitted")
        if self.since and self.until and self.until < self.since:
            errors.append(f"'until' ({self.until}) is before 'since' ({self.since})")
        if self.confidence < 0 or self.confidence > 1:
            errors.append(f"Confidence out of range: {self.confidence}")
        return errors

    def to_cypher_merge(self) -> str:
        """
        Generate a Cypher MERGE statement to upsert this relationship in Neo4j.

        Uses MERGE on (source_aqid, target_aqid, relationship_type) as the
        deduplication key. All other properties are set via ON CREATE / ON MATCH.
        """
        props = {
            "rel_id":       self.rel_id,
            "is_primary":   self.is_primary,
            "is_current":   self.is_current,
            "confidence":   self.confidence,
            "provenance_url": self.provenance_url,
            "provenance_org": self.provenance_org,
            "notes":        self.notes,
            "version":      self.version,
            "created_at":   self.created_at,
        }
        if self.since:
            props["since"] = self.since.isoformat()
        if self.until:
            props["until"] = self.until.isoformat()
        if self.properties:
            props.update({f"prop_{k}": v for k, v in self.properties.items()})

        set_clauses = ", ".join(f"r.{k} = {_cypher_val(v)}" for k, v in props.items())
        rel_type = self.relationship_type.value

        return f"""
MATCH (source:AerospaceEntity {{aqid: "{self.source_aqid}"}})
MATCH (target:AerospaceEntity {{aqid: "{self.target_aqid}"}})
MERGE (source)-[r:{rel_type} {{
    source_aqid: "{self.source_aqid}",
    target_aqid: "{self.target_aqid}"
}}]->(target)
ON CREATE SET {set_clauses}
ON MATCH SET r.version = r.version + 1,
             r.confidence = {self.confidence},
             r.is_current = {str(self.is_current).lower()},
             r.updated_at = datetime()
RETURN r
""".strip()


def _cypher_val(v: Any) -> str:
    """Format a Python value for inclusion in a Cypher statement."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{str(v)}"'


# ---------------------------------------------------------------------------
# COMMON TRAVERSAL PATTERNS
# Reference Cypher for the Graph Agent.
# ---------------------------------------------------------------------------

TRAVERSAL_PATTERNS = {

    "entity_neighborhood": """
// Return all entities within N hops of a given AQID
MATCH path = (e:AerospaceEntity {aqid: $aqid})-[*1..$depth]-(neighbor:AerospaceEntity)
WHERE neighbor.is_active = true
RETURN path
LIMIT $limit
""",

    "path_between_entities": """
// Shortest path between two entities
MATCH path = shortestPath(
    (a:AerospaceEntity {aqid: $source_aqid})-[*1..6]-(b:AerospaceEntity {aqid: $target_aqid})
)
RETURN path
""",

    "satellites_by_operator": """
// All satellites operated by a given organization
MATCH (op:AerospaceEntity {aqid: $operator_aqid})<-[:OPERATED_BY]-(sat:Satellite)
WHERE sat.is_active = true
RETURN sat.aqid, sat.display_name, sat.entity_subclass
ORDER BY sat.display_name
""",

    "supply_chain_upstream": """
// Full upstream supply chain for a hardware entity
MATCH path = (hw:AerospaceEntity {aqid: $aqid})
             -[:MANUFACTURED_BY|SUPPLIED_BY|USES_COMPONENT|DESIGNED_BY*1..4]->
             (upstream:AerospaceEntity)
RETURN DISTINCT upstream.aqid, upstream.display_name, upstream.entity_class
""",

    "countries_involved_in_mission": """
// All countries connected to a mission through any 3-hop path
MATCH (m:Mission {aqid: $mission_aqid})
      -[:OPERATED_BY|MANUFACTURED_BY|FUNDED_BY|MANAGED_BY*1..3]->(org:AerospaceEntity)
      -[:LOCATED_IN]->(country:Country)
RETURN DISTINCT country.display_name
""",

    "papers_citing_standard": """
// Research papers that reference a given standard
MATCH (std:Standard {aqid: $standard_aqid})<-[:REFERENCES]-(paper:ResearchPaper)
OPTIONAL MATCH (paper)<-[:AUTHORED_BY]-(person:Person)
RETURN paper.aqid, paper.display_name, collect(person.display_name) as authors
ORDER BY paper.display_name
""",

    "temporal_snapshot": """
// Relationships active at a specific point in time
MATCH (e:AerospaceEntity {aqid: $aqid})-[r]-(neighbor)
WHERE (r.since IS NULL OR r.since <= date($snapshot_date))
  AND (r.until IS NULL OR r.until >= date($snapshot_date))
RETURN type(r), neighbor.aqid, neighbor.display_name, r.since, r.until
""",

    "investment_flow": """
// Investment flow into a company and its subsidiaries
MATCH (inv:Investment)-[:INVESTED_IN]->(company:AerospaceEntity {aqid: $company_aqid})
OPTIONAL MATCH (sub:AerospaceEntity)-[:SUBSIDIARY_OF]->(company)
OPTIONAL MATCH (inv2:Investment)-[:INVESTED_IN]->(sub)
RETURN inv.display_name, inv.prop_amount_musd as amount_musd, 'direct' as type
UNION
RETURN inv2.display_name, inv2.prop_amount_musd as amount_musd, 'subsidiary' as type
ORDER BY amount_musd DESC
""",

}
