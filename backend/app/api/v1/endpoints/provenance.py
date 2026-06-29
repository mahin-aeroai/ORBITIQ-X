"""
ORBITIQ-X — Provenance & Versioning API
Phase 17.3

REST API for fact-level provenance, contradiction management,
human review queue, and version snapshots.

Mounts at: /api/v2/provenance

Endpoints:
  GET  /api/v2/provenance/{aqid}/facts              — All facts for an entity
  GET  /api/v2/provenance/{aqid}/facts/{field}      — Full history for one field
  POST /api/v2/provenance/{aqid}/facts              — Record a provenance fact
  GET  /api/v2/provenance/{aqid}/snapshots          — Version snapshots for entity
  GET  /api/v2/provenance/snapshots/{snapshot_id}   — Single snapshot (full state)
  POST /api/v2/provenance/{aqid}/snapshots          — Create manual snapshot
  GET  /api/v2/provenance/contradictions            — Query contradiction log
  GET  /api/v2/provenance/review                    — Review queue
  POST /api/v2/provenance/review/{review_id}/resolve — Human resolve contradiction
  GET  /api/v2/provenance/tiers                     — Source authority tier reference
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from caem.provenance.models import (
    ContradictionResolution,
    ReviewPriority,
    SourceTier,
    TIER_CONFIDENCE_WEIGHTS,
    infer_source_tier,
)
from caem.provenance.service import ProvenanceService
from caem.base import validate_aqid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/provenance", tags=["Provenance & Versioning"])



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


@router.get("/tiers")
async def get_source_tiers():
    """Return the source authority tier reference table."""
    return {
        "tiers": [
            {
                "tier": tier.value,
                "name": tier.name,
                "confidence_weight": TIER_CONFIDENCE_WEIGHTS[tier],
                "description": {
                    1: "Official space agency, operator, or manufacturer publications",
                    2: "Official registries: NORAD, COSPAR, UNOOSA, ITU",
                    3: "Peer-reviewed: academic journals, IEEE, AIAA proceedings",
                    4: "Reference: Encyclopedia Astronautica, Wikipedia (aerospace)",
                    5: "News: SpaceNews, NASAspaceflight, Aviation Week",
                    6: "Community: amateur tracking, hobbyist databases",
                }[tier.value],
            }
            for tier in SourceTier
        ],
        "resolution_thresholds": {
            "override": "new_confidence > existing_confidence + 0.15",
            "dispute":  "within 0.15 of each other → queued for human review",
            "reject":   "new_confidence < existing_confidence - 0.15",
        },
    }


# ---------------------------------------------------------------------------
# FACT PROVENANCE
# ---------------------------------------------------------------------------

@router.get("/{aqid}/facts")
async def get_entity_facts(
    aqid:   str,
):
    """Return all provenance facts for an entity, grouped by field name."""
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID: {aqid}")
    svc = ProvenanceService(pg)
    return {"aqid": aqid, "facts": svc.get_entity_facts(aqid)}


@router.get("/{aqid}/facts/{field_name}")
async def get_field_history(
    aqid:       str,
    field_name: str,
):
    """Return the full provenance history for a single field on an entity."""
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID: {aqid}")
    svc = ProvenanceService(pg)
    history = svc.get_fact_history(aqid, field_name)
    return {
        "aqid":         aqid,
        "field_name":   field_name,
        "fact_count":   len(history),
        "facts":        history,
    }


@router.post("/{aqid}/facts", status_code=status.HTTP_201_CREATED)
async def record_fact(
    aqid:       str,
    request:    FactCreateRequest,
):
    """
    Record provenance for a single field value on an entity.
    Automatically detects contradictions against existing primary fact.
    """
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID: {aqid}")

    tier = SourceTier(request.source_tier) if request.source_tier else None
    svc = ProvenanceService(pg)

    fact = svc.record_fact(
        aqid=aqid,
        field_name=request.field_name,
        field_value=request.field_value,
        source_url=request.source_url,
        source_name=request.source_name,
        source_tier=tier,
        publisher=request.publisher,
        confidence=request.confidence,
        ingest_job_id=request.ingest_job_id,
    )

    # Check for contradiction with existing primary fact
    contradiction = svc.detect_contradiction(
        aqid=aqid,
        field_name=request.field_name,
        incoming_value=request.field_value,
        incoming_confidence=fact.confidence,
        incoming_fact_id=fact.fact_id,
        incoming_source_url=request.source_url,
        incoming_tier=fact.source_tier,
        ingest_job_id=request.ingest_job_id,
    )

    return {
        "fact_id":              fact.fact_id,
        "status":               "recorded",
        "confidence":           fact.confidence,
        "source_tier":          fact.source_tier.value,
        "contradiction":        contradiction.model_dump() if contradiction else None,
        "contradiction_status": contradiction.status if contradiction else None,
    }


# ---------------------------------------------------------------------------
# VERSION SNAPSHOTS
# ---------------------------------------------------------------------------

@router.get("/{aqid}/snapshots")
async def get_snapshots(
    aqid:   str,
):
    """Return all version snapshots for an entity (newest first)."""
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID: {aqid}")
    svc = ProvenanceService(pg)
    snapshots = svc.get_snapshots(aqid)
    return {"aqid": aqid, "snapshot_count": len(snapshots), "snapshots": snapshots}


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id:    str,
):
    """Return a single full snapshot including complete entity_state."""
    svc = ProvenanceService(pg)
    snapshot = svc.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {snapshot_id}")
    return snapshot


@router.post("/{aqid}/snapshots", status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    aqid:       str,
    request:    SnapshotCreateRequest,
):
    """Manually trigger a version snapshot for an entity."""
    if not validate_aqid(aqid):
        raise HTTPException(status_code=400, detail=f"Invalid AQID: {aqid}")
    svc = ProvenanceService(pg)
    snapshot = svc.create_snapshot(
        aqid=aqid,
        snapshot_type=request.snapshot_type,
        change_summary=request.change_summary,
        fields_changed=request.fields_changed,
        created_by="api",
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Entity not found: {aqid}")
    return {"snapshot_id": snapshot.snapshot_id, "version": snapshot.version, "status": "created"}


# ---------------------------------------------------------------------------
# CONTRADICTION LOG
# ---------------------------------------------------------------------------

@router.get("/contradictions")
async def get_contradictions(
    aqid:       Optional[str]   = Query(None),
    status:     Optional[str]   = Query(None, description="pending_review / auto_resolved / human_resolved"),
    limit:      int             = Query(50, ge=1, le=200),
):
    """Query the contradiction log with optional filters."""
    svc = ProvenanceService(pg)
    contradictions = svc.get_contradictions(aqid=aqid, status=status, limit=limit)
    return {"count": len(contradictions), "contradictions": contradictions}


# ---------------------------------------------------------------------------
# HUMAN REVIEW QUEUE
# ---------------------------------------------------------------------------

@router.get("/review")
async def get_review_queue(
    status:         str             = Query("open"),
    priority:       Optional[str]   = Query(None, description="critical / high / medium / low"),
    assigned_to:    Optional[str]   = Query(None),
    limit:          int             = Query(50, ge=1, le=200),
):
    """Return review queue items sorted by priority then age."""
    svc = ProvenanceService(pg)
    items = svc.get_review_queue(
        status=status, priority=priority,
        assigned_to=assigned_to, limit=limit,
    )
    return {"count": len(items), "items": items}


@router.post("/review/{review_id}/resolve")
async def resolve_review(
    review_id:  str,
    request:    ReviewResolveRequest,
):
    """Apply a human reviewer's resolution to a review queue item."""
    svc = ProvenanceService(pg)
    success = svc.resolve_review(
        review_id=review_id,
        resolution=request.resolution,
        resolved_by=request.resolved_by,
        notes=request.notes,
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Review item not found or already resolved: {review_id}"
        )
    return {"review_id": review_id, "status": "resolved", "resolution": request.resolution.value}
