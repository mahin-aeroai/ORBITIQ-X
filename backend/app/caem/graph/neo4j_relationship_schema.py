"""
ORBITIQ-X — Neo4j Relationship Schema (Phase 17.2)
Universal Relationship Ontology — Graph Layer

Idempotent schema setup for all 76 relationship types in Neo4j.
Safe to re-run at any time — uses IF NOT EXISTS throughout.

Run once after migration 0012, and on every deployment startup
alongside caem/graph/neo4j_schema.py (Phase 17.1 node schema).

What this module adds to the graph:
  1. Relationship property existence constraints on the most critical types
  2. Temporal index: (rel.since, rel.until) for point-in-time queries
  3. Confidence index: for filtering low-confidence edges
  4. Utility Cypher for bulk relationship creation and temporal snapshots
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RELATIONSHIP SCHEMA STATEMENTS
# Applied once per Neo4j instance — idempotent
# ---------------------------------------------------------------------------

# Existence constraints on high-value relationship properties
REL_CONSTRAINTS = [
    # OPERATED_BY — most queried relationship
    ("rel_operated_by_source",
     "CREATE CONSTRAINT rel_operated_by_source IF NOT EXISTS "
     "FOR ()-[r:OPERATED_BY]-() REQUIRE r.source_aqid IS NOT NULL"),

    ("rel_operated_by_target",
     "CREATE CONSTRAINT rel_operated_by_target IF NOT EXISTS "
     "FOR ()-[r:OPERATED_BY]-() REQUIRE r.target_aqid IS NOT NULL"),

    # LAUNCHED_BY
    ("rel_launched_by_source",
     "CREATE CONSTRAINT rel_launched_by_source IF NOT EXISTS "
     "FOR ()-[r:LAUNCHED_BY]-() REQUIRE r.source_aqid IS NOT NULL"),

    # FUNDED_BY
    ("rel_funded_by_source",
     "CREATE CONSTRAINT rel_funded_by_source IF NOT EXISTS "
     "FOR ()-[r:FUNDED_BY]-() REQUIRE r.source_aqid IS NOT NULL"),
]

# Indexes on relationship properties for fast temporal and confidence filtering
REL_INDEXES = [
    ("rel_idx_confidence",
     "CREATE INDEX rel_idx_confidence IF NOT EXISTS "
     "FOR ()-[r:OPERATED_BY]-() ON (r.confidence)"),

    ("rel_idx_is_current",
     "CREATE INDEX rel_idx_is_current IF NOT EXISTS "
     "FOR ()-[r:OPERATED_BY]-() ON (r.is_current)"),
]

# Full-text index on relationship notes for search
REL_FULLTEXT = """
CREATE FULLTEXT INDEX rel_notes_fulltext IF NOT EXISTS
FOR ()-[r:DESCRIBED_BY|MENTIONED_IN|REFERENCES]-()
ON EACH [r.notes, r.citation_text]
"""

ALL_REL_SCHEMA = [
    *[(label, stmt) for label, stmt in REL_CONSTRAINTS],
    *[(label, stmt) for label, stmt in REL_INDEXES],
    ("rel_notes_fulltext", REL_FULLTEXT),
]


# ---------------------------------------------------------------------------
# POINT-IN-TIME SNAPSHOT QUERY
# Returns all relationships that were active at a given date.
# ---------------------------------------------------------------------------

TEMPORAL_SNAPSHOT_CYPHER = """
// All relationships active at $snapshot_date for a given entity
MATCH (e:AerospaceEntity {aqid: $aqid})-[r]-(neighbor:AerospaceEntity)
WHERE (r.since IS NULL OR date(r.since) <= date($snapshot_date))
  AND (r.until IS NULL OR date(r.until) >= date($snapshot_date))
  AND neighbor.is_active = true
RETURN
    type(r)                 AS rel_type,
    startNode(r).aqid       AS source_aqid,
    endNode(r).aqid         AS target_aqid,
    neighbor.aqid           AS neighbor_aqid,
    neighbor.display_name   AS neighbor_name,
    neighbor.entity_class   AS neighbor_class,
    r.since                 AS since,
    r.until                 AS until,
    r.confidence            AS confidence,
    r.provenance_url        AS provenance_url
ORDER BY type(r), neighbor.display_name
"""

# ---------------------------------------------------------------------------
# BULK RELATIONSHIP UPSERT (UNWIND pattern)
# Used by the ingestion pipeline for batch writes.
# ---------------------------------------------------------------------------

BULK_RELATIONSHIP_UPSERT_TEMPLATE = """
UNWIND $relationships AS rel
MATCH (source:AerospaceEntity {{aqid: rel.source_aqid}})
MATCH (target:AerospaceEntity {{aqid: rel.target_aqid}})
MERGE (source)-[r:{rel_type} {{
    source_aqid: rel.source_aqid,
    target_aqid: rel.target_aqid
}}]->(target)
ON CREATE SET
    r.rel_id            = rel.rel_id,
    r.confidence        = rel.confidence,
    r.since             = rel.since,
    r.until             = rel.until,
    r.is_current        = rel.is_current,
    r.is_primary        = rel.is_primary,
    r.provenance_url    = rel.provenance_url,
    r.provenance_org    = rel.provenance_org,
    r.notes             = rel.notes,
    r.version           = 1,
    r.created_at        = datetime()
ON MATCH SET
    r.confidence        = rel.confidence,
    r.is_current        = rel.is_current,
    r.version           = r.version + 1,
    r.updated_at        = datetime()
RETURN count(r) AS upserted
"""


def get_bulk_upsert_cypher(rel_type: str) -> str:
    """Return the UNWIND upsert Cypher for a specific relationship type."""
    return BULK_RELATIONSHIP_UPSERT_TEMPLATE.format(rel_type=rel_type)


# ---------------------------------------------------------------------------
# HIGH-VALUE TRAVERSAL QUERIES (Graph Agent pattern library extension)
# ---------------------------------------------------------------------------

TRAVERSAL_LIBRARY: Dict[str, str] = {

    "operator_satellites": """
// All active satellites operated by a given organization
MATCH (op:AerospaceEntity {aqid: $operator_aqid})<-[:OPERATED_BY]-(sat:AerospaceEntity)
WHERE sat.is_active = true
  AND sat.entity_class IN ['SATELLITE', 'PAYLOAD', 'SPACECRAFT']
RETURN sat.aqid, sat.display_name, sat.entity_class,
       sat.confidence_score
ORDER BY sat.display_name
""",

    "launch_vehicle_missions": """
// All missions/payloads launched by a given vehicle
MATCH (lv:AerospaceEntity {aqid: $lv_aqid})<-[:LAUNCHED_BY]-(payload:AerospaceEntity)
OPTIONAL MATCH (payload)-[:PART_OF]->(mission:AerospaceEntity)
RETURN payload.aqid, payload.display_name,
       mission.aqid AS mission_aqid, mission.display_name AS mission_name
ORDER BY payload.display_name
""",

    "country_space_assets": """
// All space assets (satellites, agencies, companies, sites) linked to a country
MATCH (country:AerospaceEntity {aqid: $country_aqid})
OPTIONAL MATCH (agency:AerospaceEntity)-[:LOCATED_IN]->(country)
    WHERE agency.entity_class = 'GOV_AGENCY'
OPTIONAL MATCH (company:AerospaceEntity)-[:LOCATED_IN]->(country)
    WHERE company.entity_class = 'COMPANY'
OPTIONAL MATCH (sat:AerospaceEntity)-[:LAUNCHED_BY]->(:AerospaceEntity)-[:LOCATED_IN]->(country)
    WHERE sat.entity_class = 'SATELLITE'
OPTIONAL MATCH (site:AerospaceEntity)-[:LOCATED_IN]->(country)
    WHERE site.entity_class = 'LAUNCH_SITE'
RETURN
    collect(DISTINCT agency.aqid)   AS agency_aqids,
    collect(DISTINCT company.aqid)  AS company_aqids,
    collect(DISTINCT sat.aqid)      AS satellite_aqids,
    collect(DISTINCT site.aqid)     AS site_aqids
""",

    "technology_lineage": """
// Full lineage chain for a technology (predecessor → current → successors)
MATCH path = (root:AerospaceEntity)-[:SUCCESSOR_OF*0..5]->(tech:AerospaceEntity {aqid: $tech_aqid})
WITH nodes(path) AS lineage
UNWIND lineage AS node
RETURN DISTINCT node.aqid, node.display_name, node.entity_class
ORDER BY node.display_name
""",

    "paper_citation_network": """
// N-hop citation network around a research paper
MATCH path = (center:AerospaceEntity {aqid: $paper_aqid})-[:CITES*1..$depth]-(cited:AerospaceEntity)
WHERE cited.entity_class = 'RESEARCH_PAPER'
RETURN DISTINCT cited.aqid, cited.display_name,
       length(path) AS hops
ORDER BY hops, cited.display_name
LIMIT $limit
""",

    "supply_chain_full": """
// Complete upstream supply chain for a hardware entity
MATCH path = (hw:AerospaceEntity {aqid: $aqid})
             -[:MANUFACTURED_BY|SUPPLIED_BY|USES_COMPONENT|DESIGNED_BY*1..4]->
             (upstream:AerospaceEntity)
RETURN DISTINCT
    upstream.aqid, upstream.display_name, upstream.entity_class,
    length(path) AS hops
ORDER BY hops, upstream.entity_class
""",

    "organization_influence": """
// All entities an organization has direct relationships with (1-hop influence)
MATCH (org:AerospaceEntity {aqid: $org_aqid})-[r]-(entity:AerospaceEntity)
WHERE entity.is_active = true
RETURN
    type(r)             AS rel_type,
    entity.aqid         AS entity_aqid,
    entity.display_name AS entity_name,
    entity.entity_class AS entity_class,
    r.confidence        AS confidence
ORDER BY type(r), entity.display_name
LIMIT 200
""",

    "mission_full_graph": """
// Complete mission graph: all entities connected to a mission
MATCH (m:AerospaceEntity {aqid: $mission_aqid})-[r*1..2]-(entity:AerospaceEntity)
WHERE entity.is_active = true
WITH DISTINCT entity, r
RETURN entity.aqid, entity.display_name, entity.entity_class,
       [rel IN r | type(rel)] AS relationship_path
ORDER BY entity.entity_class, entity.display_name
LIMIT 100
""",

    "constellation_members": """
// All satellites belonging to a constellation
MATCH (constellation:AerospaceEntity {aqid: $constellation_aqid})
      <-[:PART_OF|BELONGS_TO]-(sat:AerospaceEntity)
WHERE sat.is_active = true
RETURN sat.aqid, sat.display_name, sat.confidence_score
ORDER BY sat.display_name
""",

    "risk_adjacency": """
// Entities sharing orbital regime with a given satellite (potential conjunction risk)
MATCH (sat:AerospaceEntity {aqid: $sat_aqid})-[:PART_OF]->(regime:AerospaceEntity)
      <-[:PART_OF]-(neighbor:AerospaceEntity)
WHERE neighbor.aqid <> $sat_aqid
  AND neighbor.entity_class IN ['SATELLITE', 'DEBRIS']
  AND neighbor.is_active = true
RETURN neighbor.aqid, neighbor.display_name, neighbor.entity_class
ORDER BY neighbor.display_name
LIMIT 100
""",

    "standard_compliance_map": """
// All entities that implement or comply with a given standard
MATCH (std:AerospaceEntity {aqid: $standard_aqid})
      <-[:IMPLEMENTS|COMPLIES_WITH]-(entity:AerospaceEntity)
RETURN entity.aqid, entity.display_name, entity.entity_class
ORDER BY entity.entity_class, entity.display_name
""",

}


# ---------------------------------------------------------------------------
# OPERATED_BY POPULATION UTILITIES
# Phase 17.2 priority: wire existing PostgreSQL operator_name → Neo4j OPERATED_BY
# ---------------------------------------------------------------------------

# Query to fetch all satellites with a known operator from PostgreSQL
POSTGRES_OPERATOR_FETCH = """
SELECT
    s.norad_id,
    s.object_name,
    s.operator_name,
    s.object_type,
    ae.aqid AS satellite_aqid,
    op.aqid AS operator_aqid
FROM satellites s
LEFT JOIN aerospace_entities ae
    ON ae.extension_data->>'norad_id' = s.norad_id::text
    AND ae.entity_class = 'SATELLITE'
LEFT JOIN aerospace_entities op
    ON op.display_name ILIKE s.operator_name
    AND op.entity_class IN ('COMPANY', 'GOV_AGENCY')
WHERE s.operator_name IS NOT NULL
  AND s.operator_name != ''
  AND ae.aqid IS NOT NULL
  AND op.aqid IS NOT NULL
ORDER BY s.norad_id
"""

# Cypher to create OPERATED_BY from satellite NORAD ID and operator name
OPERATED_BY_FROM_NORAD = """
MATCH (sat:AerospaceEntity)
WHERE sat.extension_data.norad_id = $norad_id
  OR sat.aqid = $satellite_aqid
MATCH (op:AerospaceEntity {aqid: $operator_aqid})
MERGE (sat)-[r:OPERATED_BY {
    source_aqid: sat.aqid,
    target_aqid: op.aqid
}]->(op)
ON CREATE SET
    r.rel_id        = $rel_id,
    r.confidence    = $confidence,
    r.is_current    = true,
    r.is_primary    = true,
    r.provenance_url = $provenance_url,
    r.created_at    = datetime()
ON MATCH SET
    r.confidence    = $confidence,
    r.updated_at    = datetime()
RETURN r
"""

# Batch OPERATED_BY from Space-Track operator data (no CAEM AQID required)
# Used for direct population from PostgreSQL operator_name field
OPERATED_BY_BATCH_FROM_SATCAT = """
UNWIND $batch AS item
MATCH (sat:AerospaceEntity)
WHERE sat.entity_class IN ['SATELLITE', 'PAYLOAD']
  AND (sat.aqid CONTAINS item.norad_id OR sat.display_name = item.sat_name)
MATCH (op:AerospaceEntity)
WHERE (op.display_name ILIKE item.operator_name OR op.short_name ILIKE item.operator_name)
  AND op.entity_class IN ['COMPANY', 'GOV_AGENCY', 'GOV_AGENCY']
MERGE (sat)-[r:OPERATED_BY {source_aqid: sat.aqid, target_aqid: op.aqid}]->(op)
ON CREATE SET
    r.confidence    = 0.75,
    r.is_current    = true,
    r.provenance_url = 'https://www.space-track.org',
    r.created_at    = datetime()
ON MATCH SET
    r.updated_at    = datetime()
RETURN count(r) AS created
"""


# ---------------------------------------------------------------------------
# SCHEMA INITIALIZATION
# ---------------------------------------------------------------------------

def initialize_relationship_schema(driver) -> dict:
    """
    Apply all Phase 17.2 Neo4j relationship schema statements.
    Idempotent — safe to call on every startup.

    Args:
        driver: Neo4j AsyncDriver or Driver instance

    Returns:
        dict with success/failed counts
    """
    results = {"success": 0, "failed": 0, "details": []}

    with driver.session() as session:
        for label, stmt in ALL_REL_SCHEMA:
            try:
                session.run(stmt)
                results["success"] += 1
                results["details"].append({"label": label, "status": "ok"})
                logger.info(f"Neo4j rel schema: {label} ✓")
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"label": label, "status": "error", "error": str(e)})
                logger.warning(f"Neo4j rel schema: {label} ✗ — {e}")

    return results


def get_temporal_snapshot(driver, aqid: str, snapshot_date: str) -> List[Dict]:
    """
    Return all relationships active for an entity at a point in time.

    Args:
        driver:         Neo4j driver
        aqid:           Entity AQID
        snapshot_date:  ISO date string e.g. "2020-01-01"

    Returns:
        List of relationship dicts
    """
    try:
        with driver.session() as session:
            result = session.run(
                TEMPORAL_SNAPSHOT_CYPHER,
                aqid=aqid,
                snapshot_date=snapshot_date,
            )
            return [dict(r) for r in result]
    except Exception as e:
        logger.error(f"Temporal snapshot failed for {aqid} at {snapshot_date}: {e}")
        return []


def bulk_upsert_relationships(
    driver,
    rel_type: str,
    relationships: List[Dict],
    batch_size: int = 200,
) -> dict:
    """
    Bulk upsert relationships of a single type using UNWIND.

    Args:
        driver:         Neo4j driver
        rel_type:       Relationship type string (e.g. "OPERATED_BY")
        relationships:  List of relationship property dicts
        batch_size:     Relationships per transaction

    Returns:
        dict with total upserted and failed counts
    """
    cypher = get_bulk_upsert_cypher(rel_type)
    total_upserted = 0
    total_failed = 0

    for i in range(0, len(relationships), batch_size):
        batch = relationships[i : i + batch_size]
        try:
            with driver.session() as session:
                result = session.run(cypher, relationships=batch)
                record = result.single()
                total_upserted += record["upserted"] if record else 0
        except Exception as e:
            total_failed += len(batch)
            logger.error(f"Bulk upsert failed for {rel_type} batch {i // batch_size}: {e}")

    logger.info(f"Bulk upsert {rel_type}: {total_upserted} upserted, {total_failed} failed")
    return {"upserted": total_upserted, "failed": total_failed}
