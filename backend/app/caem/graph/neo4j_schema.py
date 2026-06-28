"""
ORBITIQ-X — Neo4j CAEM Schema Initializer
Phase 17.1

Run this module once after the Alembic migration to configure Neo4j
constraints and indexes for the CAEM graph layer.

Idempotent: all operations use CREATE CONSTRAINT IF NOT EXISTS
and CREATE INDEX IF NOT EXISTS, safe to re-run.

Graph design principles:
  1. Every entity has the :AerospaceEntity base label + its class label
  2. Nodes store only graph-traversal properties (not the full entity record)
  3. Full entity data lives in PostgreSQL — authoritative
  4. All relationship types use the RelationshipType enum from relationships.py
"""

from __future__ import annotations

from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SCHEMA SETUP QUERIES
# ---------------------------------------------------------------------------

# Unique constraint on AQID across all entity nodes
CONSTRAINT_AQID_UNIQUE = """
CREATE CONSTRAINT ae_aqid_unique IF NOT EXISTS
FOR (e:AerospaceEntity)
REQUIRE e.aqid IS UNIQUE
"""

# Required property existence constraints
CONSTRAINT_AQID_EXISTS = """
CREATE CONSTRAINT ae_aqid_exists IF NOT EXISTS
FOR (e:AerospaceEntity)
REQUIRE e.aqid IS NOT NULL
"""

CONSTRAINT_CLASS_EXISTS = """
CREATE CONSTRAINT ae_class_exists IF NOT EXISTS
FOR (e:AerospaceEntity)
REQUIRE e.entity_class IS NOT NULL
"""

CONSTRAINT_NAME_EXISTS = """
CREATE CONSTRAINT ae_name_exists IF NOT EXISTS
FOR (e:AerospaceEntity)
REQUIRE e.display_name IS NOT NULL
"""

# Property indexes for graph traversal
INDEX_ENTITY_CLASS = """
CREATE INDEX ae_entity_class IF NOT EXISTS
FOR (e:AerospaceEntity) ON (e.entity_class)
"""

INDEX_DISPLAY_NAME = """
CREATE INDEX ae_display_name IF NOT EXISTS
FOR (e:AerospaceEntity) ON (e.display_name)
"""

INDEX_IS_ACTIVE = """
CREATE INDEX ae_is_active IF NOT EXISTS
FOR (e:AerospaceEntity) ON (e.is_active)
"""

INDEX_LIFECYCLE_STATUS = """
CREATE INDEX ae_lifecycle_status IF NOT EXISTS
FOR (e:AerospaceEntity) ON (e.lifecycle_status)
"""

INDEX_CONFIDENCE = """
CREATE INDEX ae_confidence IF NOT EXISTS
FOR (e:AerospaceEntity) ON (e.confidence_score)
"""

# Full-text index for entity name search within Neo4j
# (Supplements PostgreSQL full-text; useful for graph-context name lookup)
FULLTEXT_INDEX_NAMES = """
CREATE FULLTEXT INDEX ae_names_fulltext IF NOT EXISTS
FOR (e:AerospaceEntity)
ON EACH [e.display_name, e.short_name]
"""

# Relationship property indexes for temporal queries
REL_INDEX_SINCE = """
CREATE INDEX rel_since IF NOT EXISTS
FOR ()-[r:OPERATED_BY]-() ON (r.since)
"""

# Relationship unique constraint to prevent duplicates
# (source_aqid + target_aqid used as dedup key in MERGE statements)
REL_CONSTRAINT_REL_ID = """
CREATE CONSTRAINT rel_id_unique IF NOT EXISTS
FOR ()-[r:OPERATED_BY]-()
REQUIRE r.rel_id IS UNIQUE
"""


# All schema statements in execution order
SCHEMA_STATEMENTS = [
    ("Unique AQID constraint",          CONSTRAINT_AQID_UNIQUE),
    ("AQID existence constraint",       CONSTRAINT_AQID_EXISTS),
    ("Entity class existence",          CONSTRAINT_CLASS_EXISTS),
    ("Display name existence",          CONSTRAINT_NAME_EXISTS),
    ("Index: entity_class",             INDEX_ENTITY_CLASS),
    ("Index: display_name",             INDEX_DISPLAY_NAME),
    ("Index: is_active",                INDEX_IS_ACTIVE),
    ("Index: lifecycle_status",         INDEX_LIFECYCLE_STATUS),
    ("Index: confidence_score",         INDEX_CONFIDENCE),
    ("Full-text: names",                FULLTEXT_INDEX_NAMES),
]


# ---------------------------------------------------------------------------
# NODE UPSERT TEMPLATE
# Used by the ingestion pipeline to sync PostgreSQL entities → Neo4j nodes.
# ---------------------------------------------------------------------------

NODE_UPSERT_CYPHER = """
MERGE (e:AerospaceEntity {aqid: $aqid})
  ON CREATE SET
    e.display_name      = $display_name,
    e.short_name        = $short_name,
    e.entity_class      = $entity_class,
    e.entity_subclass   = $entity_subclass,
    e.is_active         = $is_active,
    e.lifecycle_status  = $lifecycle_status,
    e.confidence_score  = $confidence_score,
    e.tags              = $tags,
    e.updated_at        = datetime()
  ON MATCH SET
    e.display_name      = $display_name,
    e.short_name        = $short_name,
    e.is_active         = $is_active,
    e.lifecycle_status  = $lifecycle_status,
    e.confidence_score  = $confidence_score,
    e.tags              = $tags,
    e.updated_at        = datetime()
WITH e
// Apply entity-class-specific label (idempotent in Neo4j 5+)
CALL apoc.create.addLabels(e, [$entity_class]) YIELD node
RETURN node.aqid as aqid
"""

# Fallback without APOC (Neo4j Community or non-APOC deployments)
NODE_UPSERT_CYPHER_NO_APOC = """
MERGE (e:AerospaceEntity {aqid: $aqid})
  ON CREATE SET
    e.display_name      = $display_name,
    e.short_name        = $short_name,
    e.entity_class      = $entity_class,
    e.entity_subclass   = $entity_subclass,
    e.is_active         = $is_active,
    e.lifecycle_status  = $lifecycle_status,
    e.confidence_score  = $confidence_score,
    e.tags              = $tags,
    e.updated_at        = datetime()
  ON MATCH SET
    e.display_name      = $display_name,
    e.short_name        = $short_name,
    e.is_active         = $is_active,
    e.lifecycle_status  = $lifecycle_status,
    e.confidence_score  = $confidence_score,
    e.tags              = $tags,
    e.updated_at        = datetime()
RETURN e.aqid as aqid
"""


# ---------------------------------------------------------------------------
# GRAPH ANALYTICS NAMED PROJECTIONS
# Pre-built projections for Neo4j GDS (Graph Data Science) analytics.
# ---------------------------------------------------------------------------

NAMED_GRAPH_PROJECTIONS = {

    "full_aerospace_graph": {
        "description": "All active entities and all relationships",
        "cypher": """
            CALL gds.graph.project(
                'full_aerospace_graph',
                {AerospaceEntity: {properties: ['confidence_score']}},
                '*'
            )
        """
    },

    "supply_chain_graph": {
        "description": "Hardware entities and supply chain relationships",
        "cypher": """
            CALL gds.graph.project.cypher(
                'supply_chain_graph',
                'MATCH (n:AerospaceEntity) WHERE n.entity_class IN
                 ["LAUNCH_VEHICLE","SATELLITE","COMPONENT","MATERIAL","COMPANY"]
                 AND n.is_active = true RETURN id(n) AS id',
                'MATCH (a)-[r:MANUFACTURED_BY|SUPPLIED_BY|COMPONENT_OF|USES_COMPONENT]->(b)
                 RETURN id(a) AS source, id(b) AS target, type(r) AS type'
            )
        """
    },

    "organizational_graph": {
        "description": "Organizations and organizational relationships",
        "cypher": """
            CALL gds.graph.project.cypher(
                'organizational_graph',
                'MATCH (n:AerospaceEntity) WHERE n.entity_class IN
                 ["COUNTRY","GOV_AGENCY","COMPANY","UNIVERSITY","RESEARCH_ORG"]
                 AND n.is_active = true RETURN id(n) AS id',
                'MATCH (a)-[r:PART_OF|SUBSIDIARY_OF|COLLABORATES_WITH|FUNDED_BY|MEMBER_OF]->(b)
                 RETURN id(a) AS source, id(b) AS target, type(r) AS type'
            )
        """
    },

    "scientific_graph": {
        "description": "Knowledge entities and scientific relationships",
        "cypher": """
            CALL gds.graph.project.cypher(
                'scientific_graph',
                'MATCH (n:AerospaceEntity) WHERE n.entity_class IN
                 ["RESEARCH_PAPER","PATENT","STANDARD","TECHNOLOGY","PERSON"]
                 AND n.is_active = true RETURN id(n) AS id',
                'MATCH (a)-[r:CITES|AUTHORED_BY|REFERENCES|STANDARDIZED_IN|PATENTED_BY]->(b)
                 RETURN id(a) AS source, id(b) AS target, type(r) AS type'
            )
        """
    },

}


# ---------------------------------------------------------------------------
# SCHEMA INITIALIZATION FUNCTION
# ---------------------------------------------------------------------------

def initialize_neo4j_schema(driver) -> dict:
    """
    Run all schema setup statements against Neo4j.
    Idempotent — safe to call on a schema that already exists.

    Args:
        driver: Neo4j Driver instance (from neo4j package)

    Returns:
        dict with 'success', 'applied', 'failed' counts
    """
    results = {"success": 0, "failed": 0, "details": []}

    with driver.session() as session:
        for label, query in SCHEMA_STATEMENTS:
            try:
                session.run(query)
                results["success"] += 1
                results["details"].append({"label": label, "status": "ok"})
                logger.info(f"Neo4j schema: {label} ✓")
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"label": label, "status": "error", "error": str(e)})
                logger.error(f"Neo4j schema: {label} ✗ — {e}")

    return results


def upsert_entity_node(driver, entity_props: dict, use_apoc: bool = False) -> Optional[str]:
    """
    Upsert a single entity as a Neo4j node.

    Args:
        driver:         Neo4j Driver instance
        entity_props:   Dict matching the NODE_UPSERT_CYPHER parameters
                        (output of BaseAerospaceEntity.to_neo4j_node())
        use_apoc:       Whether APOC is available for dynamic label assignment

    Returns:
        AQID of the upserted node, or None on failure
    """
    query = NODE_UPSERT_CYPHER if use_apoc else NODE_UPSERT_CYPHER_NO_APOC
    try:
        with driver.session() as session:
            result = session.run(query, **entity_props)
            record = result.single()
            return record["aqid"] if record else None
    except Exception as e:
        logger.error(f"Failed to upsert node {entity_props.get('aqid')}: {e}")
        return None


def batch_upsert_nodes(driver, entities: list[dict], batch_size: int = 100) -> dict:
    """
    Upsert a batch of entity nodes using UNWIND for efficiency.

    Args:
        driver:     Neo4j Driver instance
        entities:   List of entity property dicts
        batch_size: Number of nodes per transaction

    Returns:
        dict with success and failure counts
    """
    batch_cypher = """
    UNWIND $batch AS props
    MERGE (e:AerospaceEntity {aqid: props.aqid})
    ON CREATE SET
        e.display_name      = props.display_name,
        e.short_name        = props.short_name,
        e.entity_class      = props.entity_class,
        e.entity_subclass   = props.entity_subclass,
        e.is_active         = props.is_active,
        e.lifecycle_status  = props.lifecycle_status,
        e.confidence_score  = props.confidence_score,
        e.tags              = props.tags,
        e.updated_at        = datetime()
    ON MATCH SET
        e.display_name      = props.display_name,
        e.is_active         = props.is_active,
        e.lifecycle_status  = props.lifecycle_status,
        e.confidence_score  = props.confidence_score,
        e.updated_at        = datetime()
    RETURN count(e) AS count
    """

    total_success = 0
    total_failed = 0

    for i in range(0, len(entities), batch_size):
        batch = entities[i : i + batch_size]
        try:
            with driver.session() as session:
                result = session.run(batch_cypher, batch=batch)
                record = result.single()
                total_success += record["count"] if record else 0
        except Exception as e:
            total_failed += len(batch)
            logger.error(f"Batch upsert failed for batch {i//batch_size}: {e}")

    return {"success": total_success, "failed": total_failed}
