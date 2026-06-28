"""
ORBITIQ-X — CAEM Entity API Router
Phase 17.1

FastAPI router providing the REST API surface for CAEM entities.
Mounts at: /api/v2/entities

Endpoints:
  GET    /api/v2/entities                     — Search and list entities
  POST   /api/v2/entities                     — Create entity
  GET    /api/v2/entities/{aqid}              — Get full entity record
  PATCH  /api/v2/entities/{aqid}              — Update entity fields
  GET    /api/v2/entities/{aqid}/relationships — Get all relationships
  GET    /api/v2/entities/{aqid}/neighborhood  — Get Neo4j neighborhood
  GET    /api/v2/entities/{aqid}/timeline      — Get timeline events
  GET    /api/v2/entities/{aqid}/documents     — Get linked documents
  POST   /api/v2/entities/{aqid}/sources       — Add provenance source
  POST   /api/v2/entities/{aqid}/refresh-summary — Trigger AI summary refresh
  GET    /api/v2/entities/search/fulltext       — Full-text search

Design notes:
  - All endpoints require JWT auth (reusing existing ORBITIQ-X auth middleware)
  - Write operations require 'knowledge_editor' role
  - Read operations require 'viewer' role
  - Pagination uses cursor-based approach (updated_at + aqid)
  - Response envelopes include confidence scores and provenance for every entity
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from caem.base import (
    BaseAerospaceEntity,
    EntityClass,
    LifecycleStatus,
    ProvenanceRecord,
    SourceType,
    VerificationStatus,
    generate_aqid,
    validate_aqid,
)
from caem.entities import validate_extension

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/entities", tags=["CAEM Entities"])


# ---------------------------------------------------------------------------
# REQUEST / RESPONSE MODELS
# ---------------------------------------------------------------------------

class EntityCreateRequest(BaseModel):
    entity_class:   EntityClass
    display_name:   str
    short_name:     Optional[str]   = None
    description:    Optional[str]   = None
    tags:           List[str]       = []
    domains:        List[str]       = []
    extension_data: Dict[str, Any]  = {}
    source_url:     Optional[str]   = None
    source_type:    SourceType      = SourceType.COMMUNITY

    def to_aqid(self) -> str:
        return generate_aqid(self.entity_class, self.display_name)


class EntityUpdateRequest(BaseModel):
    display_name:       Optional[str]           = None
    short_name:         Optional[str]           = None
    description:        Optional[str]           = None
    long_description:   Optional[str]           = None
    tags:               Optional[List[str]]     = None
    domains:            Optional[List[str]]     = None
    extension_data:     Optional[Dict[str, Any]] = None
    lifecycle_status:   Optional[LifecycleStatus] = None


class EntitySummaryResponse(BaseModel):
    """Lightweight response for list endpoints."""
    aqid:               str
    entity_class:       str
    display_name:       str
    short_name:         Optional[str]
    description:        Optional[str]
    lifecycle_status:   str
    confidence_score:   float
    tags:               List[str]
    updated_at:         datetime
    ai_executive_summary: Optional[str]


class RelationshipResponse(BaseModel):
    rel_id:             str
    source_aqid:        str
    target_aqid:        str
    relationship_type:  str
    category:           Optional[str]
    since:              Optional[str]
    until:              Optional[str]
    is_current:         bool
    confidence:         float
    provenance_url:     Optional[str]
    properties:         Dict[str, Any]


class EntityListResponse(BaseModel):
    entities:       List[EntitySummaryResponse]
    total:          int
    page:           int
    page_size:      int
    next_cursor:    Optional[str]


class SourceAddRequest(BaseModel):
    source_url:         str
    source_name:        str
    source_type:        SourceType
    publisher:          Optional[str] = None
    author:             Optional[str] = None
    confidence:         float = 0.70
    notes:              Optional[str] = None


# ---------------------------------------------------------------------------
# DEPENDENCY INJECTION STUBS
# Replace with actual ORBITIQ-X dependency injection
# ---------------------------------------------------------------------------

def get_pg_session():
    """Yield PostgreSQL session. Replace with actual session factory."""
    raise NotImplementedError("Replace with ORBITIQ-X PostgreSQL session dependency")

def get_neo4j_driver():
    """Yield Neo4j driver. Replace with actual driver dependency."""
    raise NotImplementedError("Replace with ORBITIQ-X Neo4j driver dependency")

def require_viewer():
    """JWT auth dependency — viewer role."""
    pass  # Replace with actual ORBITIQ-X JWT dependency

def require_editor():
    """JWT auth dependency — knowledge_editor role."""
    pass  # Replace with actual ORBITIQ-X JWT dependency


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@router.get("", response_model=EntityListResponse)
async def list_entities(
    entity_class:       Optional[str]   = Query(None, description="Filter by EntityClass"),
    lifecycle_status:   str             = Query("published", description="Filter by lifecycle status"),
    domain:             Optional[str]   = Query(None, description="Filter by knowledge domain"),
    region:             Optional[str]   = Query(None, description="Filter by region"),
    min_confidence:     float           = Query(0.0, description="Minimum confidence score"),
    page:               int             = Query(1, ge=1),
    page_size:          int             = Query(20, ge=1, le=100),
    _auth                               = Depends(require_viewer),
    pg                                  = Depends(get_pg_session),
):
    """
    List and filter aerospace entities.
    Supports filtering by class, domain, region, lifecycle status, and confidence.
    """
    offset = (page - 1) * page_size

    where_clauses = ["is_active = true"]
    params: Dict[str, Any] = {
        "lifecycle_status": lifecycle_status,
        "min_confidence": min_confidence,
        "limit": page_size,
        "offset": offset,
    }

    where_clauses.append("lifecycle_status = :lifecycle_status")
    where_clauses.append("confidence_score >= :min_confidence")

    if entity_class:
        where_clauses.append("entity_class = :entity_class")
        params["entity_class"] = entity_class.upper()

    if domain:
        where_clauses.append("domains @> :domain::jsonb")
        params["domain"] = json.dumps([domain])

    if region:
        where_clauses.append("regions @> :region::jsonb")
        params["region"] = json.dumps([region])

    where_sql = " AND ".join(where_clauses)

    count_result = pg.execute(
        f"SELECT COUNT(*) FROM aerospace_entities WHERE {where_sql}",
        params
    ).scalar()

    results = pg.execute(
        f"""
        SELECT aqid, entity_class, display_name, short_name, description,
               lifecycle_status, confidence_score, tags, updated_at, ai_executive_summary
        FROM aerospace_entities
        WHERE {where_sql}
        ORDER BY updated_at DESC, aqid
        LIMIT :limit OFFSET :offset
        """,
        params
    ).fetchall()

    entities = [
        EntitySummaryResponse(
            aqid=row[0], entity_class=row[1], display_name=row[2],
            short_name=row[3], description=row[4], lifecycle_status=row[5],
            confidence_score=row[6], tags=row[7] or [],
            updated_at=row[8], ai_executive_summary=row[9],
        )
        for row in results
    ]

    return EntityListResponse(
        entities=entities,
        total=count_result or 0,
        page=page,
        page_size=page_size,
        next_cursor=entities[-1].aqid if len(entities) == page_size else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_entity(
    request:    EntityCreateRequest,
    _auth       = Depends(require_editor),
    pg          = Depends(get_pg_session),
    neo4j       = Depends(get_neo4j_driver),
):
    """
    Create a new aerospace entity.
    Generates AQID, validates extension_data, and persists to PostgreSQL + Neo4j.
    """
    aqid = request.to_aqid()

    # Check duplicate
    existing = pg.execute(
        "SELECT aqid FROM aerospace_entities WHERE aqid = :aqid",
        {"aqid": aqid}
    ).fetchone()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Entity already exists with AQID: {aqid}. Use PATCH to update."
        )

    # Validate extension
    try:
        validated_ext = validate_extension(request.entity_class, request.extension_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Extension data validation failed: {e}"
        )

    now = datetime.utcnow()
    pg.execute("""
        INSERT INTO aerospace_entities (
            aqid, entity_class, display_name, short_name, description,
            tags, domains, extension_data, lifecycle_status, confidence_score,
            primary_provenance, verification_status, created_by, updated_by,
            created_at, updated_at
        ) VALUES (
            :aqid, :entity_class, :display_name, :short_name, :description,
            :tags::jsonb, :domains::jsonb, :extension_data::jsonb,
            'draft', 0.50,
            :primary_provenance::jsonb, 'unverified',
            'api', 'api', :now, :now
        )
    """, {
        "aqid":             aqid,
        "entity_class":     request.entity_class.value,
        "display_name":     request.display_name,
        "short_name":       request.short_name,
        "description":      request.description,
        "tags":             json.dumps(request.tags),
        "domains":          json.dumps(request.domains),
        "extension_data":   json.dumps(validated_ext),
        "primary_provenance": json.dumps({
            "source_url":   request.source_url,
            "source_type":  request.source_type.value,
            "confidence":   0.50,
        }),
        "now": now,
    })

    # Neo4j node
    from caem.graph.neo4j_schema import NODE_UPSERT_CYPHER_NO_APOC
    with neo4j.session() as session:
        session.run(NODE_UPSERT_CYPHER_NO_APOC, **{
            "aqid":             aqid,
            "display_name":     request.display_name,
            "short_name":       request.short_name,
            "entity_class":     request.entity_class.value,
            "entity_subclass":  None,
            "is_active":        True,
            "lifecycle_status": "draft",
            "confidence_score": 0.50,
            "tags":             request.tags,
        })

    logger.info(f"Entity created: {aqid}")
    return {"aqid": aqid, "status": "created"}


@router.get("/{aqid}")
async def get_entity(
    aqid:   str,
    _auth   = Depends(require_viewer),
    pg      = Depends(get_pg_session),
):
    """
    Retrieve the full entity record by AQID.
    Returns all fields including extension_data, AI summary, and provenance.
    """
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID format: {aqid}")

    result = pg.execute(
        "SELECT * FROM aerospace_entities WHERE aqid = :aqid AND is_active = true",
        {"aqid": aqid}
    ).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail=f"Entity not found: {aqid}")

    return dict(result._mapping)


@router.patch("/{aqid}")
async def update_entity(
    aqid:       str,
    request:    EntityUpdateRequest,
    _auth       = Depends(require_editor),
    pg          = Depends(get_pg_session),
    neo4j       = Depends(get_neo4j_driver),
):
    """
    Partially update an entity's fields.
    Only provided fields are updated. Extension data is merged (not replaced).
    Triggers AI summary refresh.
    """
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID format: {aqid}")

    existing = pg.execute(
        "SELECT aqid, entity_class, extension_data FROM aerospace_entities WHERE aqid = :aqid",
        {"aqid": aqid}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail=f"Entity not found: {aqid}")

    set_clauses = ["updated_at = now()", "ai_requires_refresh = true"]
    params: Dict[str, Any] = {"aqid": aqid}

    if request.display_name is not None:
        set_clauses.append("display_name = :display_name")
        params["display_name"] = request.display_name

    if request.description is not None:
        set_clauses.append("description = :description")
        params["description"] = request.description

    if request.long_description is not None:
        set_clauses.append("long_description = :long_description")
        params["long_description"] = request.long_description

    if request.tags is not None:
        set_clauses.append("tags = :tags::jsonb")
        params["tags"] = json.dumps(request.tags)

    if request.domains is not None:
        set_clauses.append("domains = :domains::jsonb")
        params["domains"] = json.dumps(request.domains)

    if request.lifecycle_status is not None:
        set_clauses.append("lifecycle_status = :lifecycle_status")
        params["lifecycle_status"] = request.lifecycle_status.value

    if request.extension_data is not None:
        # Merge incoming extension data with existing
        set_clauses.append("extension_data = extension_data || :extension_data::jsonb")
        params["extension_data"] = json.dumps(request.extension_data)

    if len(set_clauses) == 2:  # Only the defaults — nothing to update
        return {"aqid": aqid, "status": "no_changes"}

    pg.execute(
        f"UPDATE aerospace_entities SET {', '.join(set_clauses)} WHERE aqid = :aqid",
        params
    )

    return {"aqid": aqid, "status": "updated"}


@router.get("/{aqid}/relationships", response_model=List[RelationshipResponse])
async def get_relationships(
    aqid:       str,
    category:   Optional[str]  = Query(None, description="Filter by relationship category"),
    direction:  str             = Query("both", description="outbound / inbound / both"),
    is_current: bool            = Query(True),
    _auth       = Depends(require_viewer),
    pg          = Depends(get_pg_session),
):
    """
    Get all relationships for an entity from the denormalized cache.
    For graph traversal queries, use the /neighborhood endpoint.
    """
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID format: {aqid}")

    where_parts = ["is_current = :is_current"]
    params: Dict[str, Any] = {"aqid": aqid, "is_current": is_current}

    if direction == "outbound":
        where_parts.append("source_aqid = :aqid")
    elif direction == "inbound":
        where_parts.append("target_aqid = :aqid")
    else:
        where_parts.append("(source_aqid = :aqid OR target_aqid = :aqid)")

    if category:
        where_parts.append("category = :category")
        params["category"] = category

    results = pg.execute(
        f"""
        SELECT rel_id, source_aqid, target_aqid, relationship_type,
               category, since::text, until::text, is_current, confidence,
               provenance_url, properties
        FROM entity_relationships_cache
        WHERE {' AND '.join(where_parts)}
        ORDER BY relationship_type, source_aqid
        LIMIT 500
        """,
        params
    ).fetchall()

    return [
        RelationshipResponse(
            rel_id=row[0], source_aqid=row[1], target_aqid=row[2],
            relationship_type=row[3], category=row[4],
            since=row[5], until=row[6], is_current=row[7],
            confidence=row[8], provenance_url=row[9],
            properties=row[10] or {},
        )
        for row in results
    ]


@router.get("/{aqid}/neighborhood")
async def get_neighborhood(
    aqid:   str,
    depth:  int             = Query(2, ge=1, le=4, description="Graph traversal depth"),
    limit:  int             = Query(50, ge=1, le=200),
    _auth   = Depends(require_viewer),
    neo4j   = Depends(get_neo4j_driver),
):
    """
    Return the Neo4j neighborhood for a given entity.
    Used to power the Knowledge Graph Viewer panel on entity pages.
    """
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID format: {aqid}")

    cypher = """
    MATCH path = (e:AerospaceEntity {aqid: $aqid})-[*1..$depth]-(neighbor:AerospaceEntity)
    WHERE neighbor.is_active = true
    WITH nodes(path) AS ns, relationships(path) AS rs
    UNWIND ns AS n
    WITH collect(DISTINCT {
        aqid:           n.aqid,
        display_name:   n.display_name,
        entity_class:   n.entity_class,
        confidence:     n.confidence_score
    }) AS nodes_data,
    rs
    UNWIND rs AS r
    RETURN nodes_data,
           collect(DISTINCT {
               rel_id:    r.rel_id,
               source:    startNode(r).aqid,
               target:    endNode(r).aqid,
               type:      type(r),
               since:     r.since,
               confidence: r.confidence
           }) AS edges_data
    LIMIT $limit
    """

    try:
        with neo4j.session() as session:
            result = session.run(cypher, aqid=aqid, depth=depth, limit=limit)
            record = result.single()
            if not record:
                return {"nodes": [], "edges": []}
            return {
                "center_aqid":  aqid,
                "depth":        depth,
                "nodes":        record["nodes_data"],
                "edges":        record["edges_data"],
            }
    except Exception as e:
        logger.error(f"Neighborhood query failed for {aqid}: {e}")
        raise HTTPException(status_code=500, detail="Graph query failed")


@router.post("/{aqid}/sources", status_code=status.HTTP_201_CREATED)
async def add_source(
    aqid:       str,
    request:    SourceAddRequest,
    _auth       = Depends(require_editor),
    pg          = Depends(get_pg_session),
):
    """
    Add a provenance source to an entity's all_sources array.
    Recomputes confidence score after addition.
    """
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID format: {aqid}")

    new_source = {
        "source_url":   request.source_url,
        "source_name":  request.source_name,
        "source_type":  request.source_type.value,
        "publisher":    request.publisher,
        "author":       request.author,
        "confidence":   request.confidence,
        "retrieved_date": datetime.utcnow().isoformat(),
        "notes":        request.notes,
    }

    pg.execute("""
        UPDATE aerospace_entities
        SET all_sources         = all_sources || :source::jsonb,
            ai_requires_refresh = true,
            updated_at          = now()
        WHERE aqid = :aqid
    """, {"aqid": aqid, "source": json.dumps([new_source])})

    return {"aqid": aqid, "status": "source_added"}


@router.post("/{aqid}/refresh-summary", status_code=status.HTTP_202_ACCEPTED)
async def refresh_ai_summary(
    aqid:   str,
    _auth   = Depends(require_editor),
    pg      = Depends(get_pg_session),
):
    """
    Flag an entity for immediate AI summary regeneration.
    The Summary Agent processes the queue asynchronously.
    """
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID format: {aqid}")

    pg.execute(
        "UPDATE aerospace_entities SET ai_requires_refresh = true WHERE aqid = :aqid",
        {"aqid": aqid}
    )
    return {"aqid": aqid, "status": "refresh_queued"}


@router.get("/search/fulltext")
async def fulltext_search(
    q:              str             = Query(..., min_length=2, description="Search query"),
    entity_class:   Optional[str]   = Query(None),
    limit:          int             = Query(20, ge=1, le=100),
    _auth           = Depends(require_viewer),
    pg              = Depends(get_pg_session),
):
    """
    Full-text search across entity names, descriptions, and AI summaries.
    Uses PostgreSQL GIN tsvector index.
    """
    params: Dict[str, Any] = {"query": q, "limit": limit}
    class_filter = ""

    if entity_class:
        class_filter = "AND entity_class = :entity_class"
        params["entity_class"] = entity_class.upper()

    results = pg.execute(
        f"""
        SELECT aqid, entity_class, display_name, description,
               lifecycle_status, confidence_score,
               ts_rank(
                   to_tsvector('english',
                       coalesce(display_name, '') || ' ' ||
                       coalesce(description, '')
                   ),
                   plainto_tsquery('english', :query)
               ) AS rank
        FROM aerospace_entities
        WHERE to_tsvector('english',
                  coalesce(display_name, '') || ' ' ||
                  coalesce(description, '')
              ) @@ plainto_tsquery('english', :query)
          AND is_active = true
          AND lifecycle_status = 'published'
          {class_filter}
        ORDER BY rank DESC, confidence_score DESC
        LIMIT :limit
        """,
        params
    ).fetchall()

    return {
        "query":    q,
        "count":    len(results),
        "results":  [
            {
                "aqid":             row[0],
                "entity_class":     row[1],
                "display_name":     row[2],
                "description":      row[3],
                "lifecycle_status": row[4],
                "confidence_score": row[5],
                "relevance_rank":   float(row[6]),
            }
            for row in results
        ]
    }
