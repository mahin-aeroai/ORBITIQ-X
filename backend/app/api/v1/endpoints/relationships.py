"""
ORBITIQ-X — CAEM Relationship API (Phase 17.2)
FastAPI router for relationship operations.

Mounts at: /api/v2/relationships

Endpoints:
  GET    /api/v2/relationships/ontology              — Full relationship type registry
  GET    /api/v2/relationships/ontology/{rel_type}   — Single relationship type definition
  GET    /api/v2/relationships/ontology/category/{cat} — All types in a category
  POST   /api/v2/relationships/validate              — Validate a relationship before creation
  POST   /api/v2/relationships                       — Create relationship in Neo4j + cache
  GET    /api/v2/relationships/temporal/{aqid}       — Point-in-time snapshot for an entity
  GET    /api/v2/relationships/traversal/{pattern}   — Execute a named traversal pattern
  DELETE /api/v2/relationships/{rel_id}              — Soft-delete (sets is_current=False)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from caem.base import EntityClass, VerificationStatus
from caem.relationships import RelationshipType, AerospaceRelationship
from caem.ontology.relationship_registry import (
    RELATIONSHIP_REGISTRY,
    RelationshipDefinition,
    get_definition,
    validate_relationship_classes,
    get_relationships_for_class,
    get_category_relationships,
    get_temporal_relationships,
)
from caem.graph.neo4j_relationship_schema import (
    TRAVERSAL_LIBRARY,
    bulk_upsert_relationships,
    get_temporal_snapshot,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/relationships", tags=["CAEM Relationships"])


# ---------------------------------------------------------------------------
# REQUEST / RESPONSE MODELS
# ---------------------------------------------------------------------------

class RelationshipDefinitionResponse(BaseModel):
    rel_type:           str
    category:           str
    description:        str
    direction_note:     str
    cardinality:        str
    allowed_sources:    List[str]
    allowed_targets:    List[str]
    temporal:           bool
    temporal_note:      str
    confidence_floor:   float
    is_bidirectional:   bool
    display_label:      str
    inverse_label:      str


class RelationshipCreateRequest(BaseModel):
    source_aqid:        str
    target_aqid:        str
    relationship_type:  RelationshipType
    since:              Optional[date]   = None
    until:              Optional[date]   = None
    confidence:         float            = Field(default=0.75, ge=0.0, le=1.0)
    provenance_url:     Optional[str]    = None
    provenance_org:     Optional[str]    = None
    notes:              Optional[str]    = None
    properties:         Dict[str, Any]   = {}
    source_entity_class: Optional[EntityClass] = None
    target_entity_class: Optional[EntityClass] = None


class RelationshipValidateRequest(BaseModel):
    source_aqid:            str
    target_aqid:            str
    relationship_type:      RelationshipType
    source_entity_class:    Optional[EntityClass] = None
    target_entity_class:    Optional[EntityClass] = None
    confidence:             float = 0.75


class RelationshipValidateResponse(BaseModel):
    valid:              bool
    errors:             List[str]
    warnings:           List[str]
    definition:         Optional[RelationshipDefinitionResponse]
    confidence_floor:   Optional[float]



async def get_pg_session():
    from app.db.session import get_session
    async for session in get_session():
        yield session

def get_neo4j_driver():
    from app.graph.connection import get_driver
    try:
        return get_driver()
    except Exception:
        return None

def get_qdrant_client():
    try:
        from app.db.qdrant_session import get_qdrant
        return get_qdrant()
    except Exception:
        return None

def require_viewer(): pass
def require_editor(): pass
def require_admin(): pass


@router.get("/ontology", response_model=List[RelationshipDefinitionResponse])
async def list_ontology(
    category:   Optional[str] = Query(None, description="Filter by category"),
    temporal:   Optional[bool] = Query(None, description="Filter to temporal relationships only"),
):
    """
    Return the complete Universal Relationship Ontology.
    Optionally filter by category or temporal flag.
    """
    defns = list(RELATIONSHIP_REGISTRY.values())

    if category:
        defns = [d for d in defns if d.category == category]
    if temporal is not None:
        defns = [d for d in defns if d.temporal == temporal]

    return [_defn_to_response(d) for d in defns]


@router.get("/ontology/categories")
async def list_categories():
    """Return all relationship categories with counts."""
    from collections import Counter
    cats = Counter(d.category for d in RELATIONSHIP_REGISTRY.values())
    return {
        "categories": [
            {"category": cat, "count": count}
            for cat, count in sorted(cats.items())
        ],
        "total": len(RELATIONSHIP_REGISTRY),
    }


@router.get("/ontology/{rel_type}", response_model=RelationshipDefinitionResponse)
async def get_ontology_entry(
    rel_type:   str,
):
    """Return the formal definition for a single relationship type."""
    try:
        rt = RelationshipType(rel_type.upper())
        defn = get_definition(rt)
        return _defn_to_response(defn)
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=404,
            detail=f"Relationship type not found: {rel_type}"
        )


@router.get("/ontology/for-class/{entity_class}")
async def get_ontology_for_class(
    entity_class:   str,
    as_source:      bool = Query(True, description="As source (True) or target (False)"),
):
    """Return all valid relationship types for a given entity class."""
    try:
        ec = EntityClass(entity_class.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown entity class: {entity_class}")

    defns = get_relationships_for_class(ec, as_source=as_source)
    return {
        "entity_class": entity_class.upper(),
        "as_source": as_source,
        "count": len(defns),
        "relationships": [_defn_to_response(d) for d in defns],
    }


@router.post("/validate", response_model=RelationshipValidateResponse)
async def validate_relationship(
    request: RelationshipValidateRequest,
):
    """
    Validate a proposed relationship before creation.
    Checks AQID format, entity class compatibility, cardinality rules,
    and confidence floor.
    """
    from caem.base import validate_aqid

    errors: List[str] = []
    warnings: List[str] = []

    # AQID format
    if not validate_aqid(request.source_aqid):
        errors.append(f"Invalid source AQID format: {request.source_aqid}")
    if not validate_aqid(request.target_aqid):
        errors.append(f"Invalid target AQID format: {request.target_aqid}")
    if request.source_aqid == request.target_aqid:
        errors.append("Self-referential relationship not permitted")

    # Entity class validation (if classes provided)
    defn = RELATIONSHIP_REGISTRY.get(request.relationship_type)
    if defn is None:
        errors.append(f"Unknown relationship type: {request.relationship_type}")
        return RelationshipValidateResponse(
            valid=False, errors=errors, warnings=warnings,
            definition=None, confidence_floor=None,
        )

    if request.source_entity_class and request.target_entity_class:
        valid, reason = validate_relationship_classes(
            request.relationship_type,
            request.source_entity_class,
            request.target_entity_class,
        )
        if not valid:
            errors.append(reason)

    # Confidence floor check
    if request.confidence < defn.confidence_floor:
        warnings.append(
            f"Confidence {request.confidence} is below the floor "
            f"{defn.confidence_floor} for {request.relationship_type.value}. "
            f"Consider improving source quality before ingesting."
        )

    return RelationshipValidateResponse(
        valid           = len(errors) == 0,
        errors          = errors,
        warnings        = warnings,
        definition      = _defn_to_response(defn),
        confidence_floor= defn.confidence_floor,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_relationship(
    request: RelationshipCreateRequest,
    pg=Depends(get_pg_session),
    neo4j=Depends(get_neo4j_driver),
):
    """
    Create a relationship between two entities.
    Writes to Neo4j (authoritative) and PostgreSQL cache.
    Validates entity class compatibility if classes are provided.
    """
    from caem.base import validate_aqid

    errors = []
    if not validate_aqid(request.source_aqid):
        errors.append(f"Invalid source AQID: {request.source_aqid}")
    if not validate_aqid(request.target_aqid):
        errors.append(f"Invalid target AQID: {request.target_aqid}")
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Class validation
    if request.source_entity_class and request.target_entity_class:
        valid, reason = validate_relationship_classes(
            request.relationship_type,
            request.source_entity_class,
            request.target_entity_class,
        )
        if not valid:
            raise HTTPException(status_code=422, detail=reason)

    rel = AerospaceRelationship(
        rel_id              = uuid.uuid4().hex,
        source_aqid         = request.source_aqid,
        target_aqid         = request.target_aqid,
        relationship_type   = request.relationship_type,
        since               = request.since,
        until               = request.until,
        confidence          = request.confidence,
        provenance_url      = request.provenance_url,
        provenance_org      = request.provenance_org,
        notes               = request.notes,
        properties          = request.properties,
    )

    val_errors = rel.validate()
    if val_errors:
        raise HTTPException(status_code=422, detail="; ".join(val_errors))

    # Write to Neo4j
    try:
        cypher = rel.to_cypher_merge()
        with neo4j.session() as session:
            session.run(cypher)
    except Exception as e:
        logger.error(f"Neo4j write failed: {e}")
        raise HTTPException(status_code=500, detail=f"Neo4j write failed: {e}")

    # Write to PostgreSQL cache
    defn = RELATIONSHIP_REGISTRY.get(request.relationship_type)
    try:
        await pg.execute(text("""
            INSERT INTO entity_relationships_cache (
                rel_id, source_aqid, target_aqid, relationship_type,
                category, since, until, is_current, confidence,
                provenance_url, properties, synced_at
            ) VALUES (
                :rel_id, :source_aqid, :target_aqid, :rel_type,
                :category, :since, :until, true, :confidence,
                :provenance_url, :properties::jsonb, now()
            )
            ON CONFLICT (rel_id) DO UPDATE SET
                confidence  = EXCLUDED.confidence,
                is_current  = true,
                synced_at   = now()
        """), {
            "rel_id":           rel.rel_id,
            "source_aqid":      rel.source_aqid,
            "target_aqid":      rel.target_aqid,
            "rel_type":         rel.relationship_type.value,
            "category":         defn.category if defn else None,
            "since":            rel.since,
            "until":            rel.until,
            "confidence":       rel.confidence,
            "provenance_url":   rel.provenance_url,
            "properties":       json.dumps(rel.properties),
        })
        await pg.commit()
    except Exception as e:
        logger.warning(f"PostgreSQL relationship cache write failed (non-blocking): {e}")

    return {
        "rel_id":           rel.rel_id,
        "source_aqid":      rel.source_aqid,
        "target_aqid":      rel.target_aqid,
        "relationship_type": rel.relationship_type.value,
        "status":           "created",
    }


@router.get("/temporal/{aqid}")
async def get_temporal_snapshot_endpoint(
    aqid:           str,
    snapshot_date:  str = Query(..., description="ISO date: YYYY-MM-DD"),
    neo4j=Depends(get_neo4j_driver),
):
    """
    Return all relationships that were active for an entity at a specific date.
    Uses the since/until temporal properties on Neo4j relationships.
    """
    from caem.base import validate_aqid
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID: {aqid}")

    try:
        date.fromisoformat(snapshot_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {snapshot_date}")

    relationships = get_temporal_snapshot(neo4j, aqid, snapshot_date)
    return {
        "aqid":             aqid,
        "snapshot_date":    snapshot_date,
        "relationship_count": len(relationships),
        "relationships":    relationships,
    }


@router.get("/traversal/{pattern}")
async def execute_traversal(
    pattern:    str,
    aqid:       str = Query(..., description="Center entity AQID"),
    depth:      int = Query(2, ge=1, le=4),
    limit:      int = Query(100, ge=1, le=500),
    neo4j=Depends(get_neo4j_driver),
):
    """
    Execute a named traversal pattern from the CAEM traversal library.
    Available patterns are documented in the ontology traversal library.
    """
    if pattern not in TRAVERSAL_LIBRARY:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown traversal pattern: {pattern}. "
                   f"Available: {list(TRAVERSAL_LIBRARY.keys())}"
        )

    from caem.base import validate_aqid
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID: {aqid}")

    cypher = TRAVERSAL_LIBRARY[pattern]
    try:
        with neo4j.session() as session:
            result = session.run(
                cypher,
                aqid=aqid,
                operator_aqid=aqid,
                lv_aqid=aqid,
                country_aqid=aqid,
                tech_aqid=aqid,
                paper_aqid=aqid,
                mission_aqid=aqid,
                constellation_aqid=aqid,
                sat_aqid=aqid,
                standard_aqid=aqid,
                org_aqid=aqid,
                depth=depth,
                limit=limit,
            )
            records = [dict(r) for r in result]
    except Exception as e:
        logger.error(f"Traversal {pattern} failed for {aqid}: {e}")
        raise HTTPException(status_code=500, detail=f"Graph traversal failed: {e}")

    return {
        "pattern":  pattern,
        "aqid":     aqid,
        "count":    len(records),
        "results":  records,
    }


@router.get("/traversal")
async def list_traversal_patterns():
    """Return all available named traversal patterns."""
    return {
        "patterns": list(TRAVERSAL_LIBRARY.keys()),
        "count": len(TRAVERSAL_LIBRARY),
    }


@router.delete("/{rel_id}", status_code=status.HTTP_200_OK)
async def soft_delete_relationship(
    rel_id:     str,
    reason:     Optional[str] = Query(None),
    pg=Depends(get_pg_session),
    neo4j=Depends(get_neo4j_driver),
):
    """
    Soft-delete a relationship by setting is_current=False in Neo4j and the cache.
    The relationship is retained for audit and historical queries.
    """
    # Update PostgreSQL cache
    try:
        await pg.execute(text("""
            UPDATE entity_relationships_cache
            SET is_current = false
            WHERE rel_id = :rel_id
        """), {"rel_id": rel_id})
        await pg.commit()
    except Exception as e:
        logger.warning(f"Cache soft-delete failed for {rel_id}: {e}")

    # Update Neo4j (match on rel_id property — set across all relationship types)
    cypher = """
    MATCH ()-[r {rel_id: $rel_id}]->()
    SET r.is_current = false,
        r.deleted_at = datetime()
    RETURN count(r) AS updated
    """
    try:
        with neo4j.session() as session:
            result = session.run(cypher, rel_id=rel_id)
            record = result.single()
            updated = record["updated"] if record else 0
    except Exception as e:
        logger.error(f"Neo4j soft-delete failed for {rel_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Neo4j update failed: {e}")

    if updated == 0:
        raise HTTPException(status_code=404, detail=f"Relationship not found: {rel_id}")

    return {"rel_id": rel_id, "status": "deactivated", "reason": reason}
