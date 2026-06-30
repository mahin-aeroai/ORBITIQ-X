"""
ORBITIQ-X — Provenance & Versioning Service
Phase 17.3

The ProvenanceService is the single point of entry for all fact-level
provenance operations:

  record_fact()          — Store provenance for a single field value
  detect_contradiction() — Compare incoming vs existing for same field
  resolve_contradiction()— Apply three-tier resolution protocol
  create_snapshot()      — Persist immutable version snapshot
  get_fact_history()     — Full provenance history for a field
  get_review_queue()     — Pending human review items
  resolve_review()       — Human reviewer resolves a contradiction

Design:
  - All writes are append-only (no deletes, ever)
  - Contradiction resolution follows the three-tier protocol from CAEM design doc
  - Snapshots are triggered automatically on publish and on contradiction resolution
  - All operations return structured results for logging and API responses
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from caem.provenance.models import (
    FactRecord,
    ContradictionRecord,
    ContradictionResolution,
    ReviewQueueItem,
    ReviewPriority,
    VersionSnapshot,
    SourceTier,
    TIER_CONFIDENCE_WEIGHTS,
    infer_source_tier,
)

logger = logging.getLogger(__name__)

# Contradiction resolution thresholds (from CAEM design doc §13.3)
OVERRIDE_THRESHOLD  = 0.15   # New must exceed existing by this margin
REJECT_THRESHOLD    = 0.15   # New must not fall below existing by this margin

# Fields that automatically get HIGH priority in review queue
HIGH_PRIORITY_FIELDS = {
    "display_name", "entity_class", "entity_subclass",
    "norad_id", "cospar_id", "payload_leo_kg", "orbit_regime",
    "operator_aqid", "launch_date", "manufacturer_aqid",
}

# Fields whose contradictions are always auto-resolved (never queued for review)
AUTO_RESOLVE_FIELDS = {
    "ai_executive_summary", "ai_extended_analysis",
    "record_completeness", "updated_at",
}


class ProvenanceService:
    """
    Service layer for all provenance and versioning operations.

    Args:
        pg: SQLAlchemy session (sync or async)
    """

    def __init__(self, pg):
        self.pg = pg

    # ------------------------------------------------------------------
    # FACT RECORDING
    # ------------------------------------------------------------------

    def record_fact(
        self,
        aqid: str,
        field_name: str,
        field_value: Any,
        source_url: Optional[str] = None,
        source_name: Optional[str] = None,
        source_tier: Optional[SourceTier] = None,
        publisher: Optional[str] = None,
        confidence: Optional[float] = None,
        ingest_job_id: Optional[str] = None,
        created_by: str = "system",
    ) -> FactRecord:
        """
        Record provenance for a single field value on an entity.

        If source_tier is not provided, it is inferred from source_url domain.
        If confidence is not provided, it defaults to the tier's weight.

        Returns the created FactRecord.
        """
        tier = source_tier or infer_source_tier(source_url)
        conf = confidence if confidence is not None else TIER_CONFIDENCE_WEIGHTS[tier]

        fact = FactRecord(
            aqid=aqid,
            field_name=field_name,
            field_value=json.dumps(field_value, default=str),
            field_value_type=type(field_value).__name__,
            source_url=source_url,
            source_name=source_name,
            source_tier=tier,
            publisher=publisher,
            confidence=conf,
            ingest_job_id=ingest_job_id,
            created_by=created_by,
        )

        self._insert_fact(fact)
        return fact

    def _insert_fact(self, fact: FactRecord) -> None:
        self.pg.execute("""
            INSERT INTO fact_provenance (
                fact_id, aqid, field_name, field_value, field_value_type,
                source_url, source_name, source_tier, source_type, publisher,
                author, published_date, retrieved_at, confidence,
                is_primary, is_superseded, superseded_by,
                citation_text, doi, page_ref,
                created_at, created_by, ingest_job_id
            ) VALUES (
                :fact_id, :aqid, :field_name, :field_value, :field_value_type,
                :source_url, :source_name, :source_tier, :source_type, :publisher,
                :author, :published_date, :retrieved_at, :confidence,
                :is_primary, :is_superseded, :superseded_by,
                :citation_text, :doi, :page_ref,
                :created_at, :created_by, :ingest_job_id
            )
        """, {
            "fact_id":          fact.fact_id,
            "aqid":             fact.aqid,
            "field_name":       fact.field_name,
            "field_value":      fact.field_value,
            "field_value_type": fact.field_value_type,
            "source_url":       fact.source_url,
            "source_name":      fact.source_name,
            "source_tier":      fact.source_tier.value,
            "source_type":      fact.source_type,
            "publisher":        fact.publisher,
            "author":           fact.author,
            "published_date":   fact.published_date,
            "retrieved_at":     fact.retrieved_at,
            "confidence":       fact.confidence,
            "is_primary":       fact.is_primary,
            "is_superseded":    fact.is_superseded,
            "superseded_by":    fact.superseded_by,
            "citation_text":    fact.citation_text,
            "doi":              fact.doi,
            "page_ref":         fact.page_ref,
            "created_at":       fact.created_at,
            "created_by":       fact.created_by,
            "ingest_job_id":    fact.ingest_job_id,
        })

    # ------------------------------------------------------------------
    # CONTRADICTION DETECTION & RESOLUTION
    # ------------------------------------------------------------------

    def detect_contradiction(
        self,
        aqid: str,
        field_name: str,
        incoming_value: Any,
        incoming_confidence: float,
        incoming_fact_id: str,
        incoming_source_url: Optional[str] = None,
        incoming_tier: SourceTier = SourceTier.TIER_6_COMMUNITY,
        ingest_job_id: Optional[str] = None,
    ) -> Optional[ContradictionRecord]:
        """
        Compare an incoming fact against the current primary fact for the same field.

        Returns a ContradictionRecord if a conflict is detected, None otherwise.
        No contradiction if:
          - No existing primary fact for this field
          - Values are equal (within tolerance for numeric types)
          - Field is in AUTO_RESOLVE_FIELDS
        """
        if field_name in AUTO_RESOLVE_FIELDS:
            return None

        existing = self._get_primary_fact(aqid, field_name)
        if not existing:
            return None

        existing_val = existing["field_value"]
        incoming_val = json.dumps(incoming_value, default=str)

        # No conflict if values are the same
        if existing_val == incoming_val:
            return None

        # Numeric tolerance check (0.1% relative tolerance)
        try:
            ev = float(json.loads(existing_val))
            iv = float(incoming_val)
            if abs(ev - iv) / max(abs(ev), 1e-9) < 0.001:
                return None
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

        delta = incoming_confidence - float(existing["confidence"])
        resolution = self._resolve_tier(delta)

        contradiction = ContradictionRecord(
            aqid=aqid,
            field_name=field_name,
            existing_fact_id=existing["fact_id"],
            existing_value=existing_val,
            existing_confidence=float(existing["confidence"]),
            existing_source_url=existing.get("source_url"),
            existing_tier=SourceTier(existing.get("source_tier", 6)),
            incoming_fact_id=incoming_fact_id,
            incoming_value=incoming_val,
            incoming_confidence=incoming_confidence,
            incoming_source_url=incoming_source_url,
            incoming_tier=incoming_tier,
            confidence_delta=round(delta, 4),
            resolution=resolution,
            status="auto_resolved" if resolution != ContradictionResolution.DISPUTE else "pending_review",
            resolved_by="system" if resolution != ContradictionResolution.DISPUTE else None,
            resolved_at=datetime.utcnow() if resolution != ContradictionResolution.DISPUTE else None,
            ingest_job_id=ingest_job_id,
        )

        self._insert_contradiction(contradiction)

        # Auto-apply override or reject without queuing for review
        if resolution == ContradictionResolution.OVERRIDE:
            self._supersede_fact(existing["fact_id"], incoming_fact_id)
        elif resolution == ContradictionResolution.REJECT:
            self._mark_fact_superseded(incoming_fact_id, existing["fact_id"])
        elif resolution == ContradictionResolution.DISPUTE:
            # Queue for human review
            priority = (
                ReviewPriority.HIGH if field_name in HIGH_PRIORITY_FIELDS
                else ReviewPriority.MEDIUM
            )
            self._enqueue_review(contradiction, priority)

        return contradiction

    def _resolve_tier(self, delta: float) -> ContradictionResolution:
        """Three-tier contradiction resolution protocol."""
        if delta > OVERRIDE_THRESHOLD:
            return ContradictionResolution.OVERRIDE
        elif delta < -REJECT_THRESHOLD:
            return ContradictionResolution.REJECT
        else:
            return ContradictionResolution.DISPUTE

    def _get_primary_fact(self, aqid: str, field_name: str) -> Optional[Dict]:
        try:
            row = self.pg.execute("""
                SELECT fact_id, field_value, confidence, source_url, source_tier
                FROM fact_provenance
                WHERE aqid = :aqid
                  AND field_name = :field_name
                  AND is_primary = true
                  AND is_superseded = false
                ORDER BY confidence DESC, created_at DESC
                LIMIT 1
            """, {"aqid": aqid, "field_name": field_name}).fetchone()
            return dict(row._mapping) if row else None
        except Exception as e:
            logger.warning(f"Primary fact lookup failed for {aqid}.{field_name}: {e}")
            return None

    def _insert_contradiction(self, c: ContradictionRecord) -> None:
        self.pg.execute("""
            INSERT INTO contradiction_log (
                contradiction_id, aqid, field_name,
                existing_fact_id, existing_value, existing_confidence,
                existing_source_url, existing_tier,
                incoming_fact_id, incoming_value, incoming_confidence,
                incoming_source_url, incoming_tier,
                confidence_delta, resolution, resolution_notes,
                resolved_by, resolved_at, status, ingest_job_id, created_at
            ) VALUES (
                :contradiction_id, :aqid, :field_name,
                :existing_fact_id, :existing_value, :existing_confidence,
                :existing_source_url, :existing_tier,
                :incoming_fact_id, :incoming_value, :incoming_confidence,
                :incoming_source_url, :incoming_tier,
                :confidence_delta, :resolution, :resolution_notes,
                :resolved_by, :resolved_at, :status, :ingest_job_id, :created_at
            )
        """, {
            "contradiction_id":    c.contradiction_id,
            "aqid":                c.aqid,
            "field_name":          c.field_name,
            "existing_fact_id":    c.existing_fact_id,
            "existing_value":      c.existing_value,
            "existing_confidence": c.existing_confidence,
            "existing_source_url": c.existing_source_url,
            "existing_tier":       c.existing_tier.value,
            "incoming_fact_id":    c.incoming_fact_id,
            "incoming_value":      c.incoming_value,
            "incoming_confidence": c.incoming_confidence,
            "incoming_source_url": c.incoming_source_url,
            "incoming_tier":       c.incoming_tier.value,
            "confidence_delta":    c.confidence_delta,
            "resolution":          c.resolution.value,
            "resolution_notes":    c.resolution_notes,
            "resolved_by":         c.resolved_by,
            "resolved_at":         c.resolved_at,
            "status":              c.status,
            "ingest_job_id":       c.ingest_job_id,
            "created_at":          c.created_at,
        })

    def _supersede_fact(self, old_fact_id: str, new_fact_id: str) -> None:
        """Mark old fact as superseded by new fact (override resolution)."""
        self.pg.execute("""
            UPDATE fact_provenance
            SET is_superseded = true,
                is_primary    = false,
                superseded_by = :new_fact_id
            WHERE fact_id = :old_fact_id
        """, {"old_fact_id": old_fact_id, "new_fact_id": new_fact_id})

    def _mark_fact_superseded(self, fact_id: str, kept_by: str) -> None:
        """Mark an incoming fact as superseded by the existing one (reject resolution)."""
        self.pg.execute("""
            UPDATE fact_provenance
            SET is_superseded = true,
                is_primary    = false,
                superseded_by = :kept_by
            WHERE fact_id = :fact_id
        """, {"fact_id": fact_id, "kept_by": kept_by})

    def _enqueue_review(
        self,
        contradiction: ContradictionRecord,
        priority: ReviewPriority,
    ) -> None:
        item = ReviewQueueItem(
            contradiction_id=contradiction.contradiction_id,
            aqid=contradiction.aqid,
            field_name=contradiction.field_name,
            priority=priority,
            existing_value=contradiction.existing_value,
            incoming_value=contradiction.incoming_value,
            existing_source=contradiction.existing_source_url,
            incoming_source=contradiction.incoming_source_url,
            confidence_delta=contradiction.confidence_delta,
        )
        self.pg.execute("""
            INSERT INTO review_queue (
                review_id, contradiction_id, aqid, field_name, priority,
                entity_display_name, existing_value, incoming_value,
                existing_source, incoming_source, confidence_delta,
                status, created_at
            ) VALUES (
                :review_id, :contradiction_id, :aqid, :field_name, :priority,
                (SELECT display_name FROM aerospace_entities WHERE aqid = :aqid2),
                :existing_value, :incoming_value,
                :existing_source, :incoming_source, :confidence_delta,
                'open', :created_at
            )
        """, {
            "review_id":          item.review_id,
            "contradiction_id":   item.contradiction_id,
            "aqid":               item.aqid,
            "aqid2":              item.aqid,
            "field_name":         item.field_name,
            "priority":           item.priority.value,
            "existing_value":     item.existing_value,
            "incoming_value":     item.incoming_value,
            "existing_source":    item.existing_source,
            "incoming_source":    item.incoming_source,
            "confidence_delta":   item.confidence_delta,
            "created_at":         item.created_at,
        })

    # ------------------------------------------------------------------
    # HUMAN REVIEW RESOLUTION
    # ------------------------------------------------------------------

    def resolve_review(
        self,
        review_id: str,
        resolution: ContradictionResolution,
        resolved_by: str,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Apply a human reviewer's decision to a review queue item.

        Updates:
          - review_queue row (status → resolved)
          - contradiction_log row (status → human_resolved)
          - fact_provenance rows (apply override/reject/merge)
        """
        review = self.pg.execute(
            "SELECT * FROM review_queue WHERE review_id = :id AND status = 'open'",
            {"id": review_id}
        ).fetchone()

        if not review:
            return False

        review = dict(review._mapping)

        # Get contradiction details
        contradiction = self.pg.execute(
            "SELECT * FROM contradiction_log WHERE contradiction_id = :id",
            {"id": review["contradiction_id"]}
        ).fetchone()

        if not contradiction:
            return False

        contradiction = dict(contradiction._mapping)
        now = datetime.utcnow()

        # Apply resolution to facts
        if resolution == ContradictionResolution.OVERRIDE:
            self._supersede_fact(
                contradiction["existing_fact_id"],
                contradiction["incoming_fact_id"],
            )
        elif resolution == ContradictionResolution.REJECT:
            self._mark_fact_superseded(
                contradiction["incoming_fact_id"],
                contradiction["existing_fact_id"],
            )

        # Update review queue
        self.pg.execute("""
            UPDATE review_queue
            SET status       = 'resolved',
                resolution   = :resolution,
                reviewer_notes = :notes,
                resolved_by  = :resolved_by,
                resolved_at  = :now
            WHERE review_id = :review_id
        """, {
            "resolution":   resolution.value,
            "notes":        notes,
            "resolved_by":  resolved_by,
            "now":          now,
            "review_id":    review_id,
        })

        # Update contradiction log
        self.pg.execute("""
            UPDATE contradiction_log
            SET status          = 'human_resolved',
                resolution      = :resolution,
                resolution_notes = :notes,
                resolved_by     = :resolved_by,
                resolved_at     = :now
            WHERE contradiction_id = :contradiction_id
        """, {
            "resolution":       resolution.value,
            "notes":            notes,
            "resolved_by":      resolved_by,
            "now":              now,
            "contradiction_id": review["contradiction_id"],
        })

        logger.info(
            f"Review {review_id} resolved: {resolution.value} by {resolved_by} "
            f"for {review['aqid']}.{review['field_name']}"
        )
        return True

    # ------------------------------------------------------------------
    # VERSION SNAPSHOTS
    # ------------------------------------------------------------------

    def create_snapshot(
        self,
        aqid: str,
        snapshot_type: str = "auto",
        change_summary: str = "",
        fields_changed: Optional[List[str]] = None,
        field_diffs: Optional[Dict[str, Any]] = None,
        created_by: str = "system",
        ingest_job_id: Optional[str] = None,
    ) -> Optional[VersionSnapshot]:
        """
        Create an immutable version snapshot of the current entity state.

        Fetches the full entity record from PostgreSQL and persists it
        as a snapshot. Never mutated after creation.
        """
        try:
            row = self.pg.execute(
                "SELECT * FROM aerospace_entities WHERE aqid = :aqid",
                {"aqid": aqid}
            ).fetchone()

            if not row:
                logger.warning(f"Snapshot attempted for non-existent entity: {aqid}")
                return None

            entity = dict(row._mapping)
            version = entity.get("current_version", "1.0.0")
            confidence = float(entity.get("confidence_score", 0.0))
            verification = entity.get("verification_status", "unverified")
            extension = entity.get("extension_data", {})
            if isinstance(extension, str):
                extension = json.loads(extension)

            snapshot = VersionSnapshot(
                aqid=aqid,
                version=version,
                snapshot_type=snapshot_type,
                entity_state={k: v for k, v in entity.items()
                              if k not in ("extension_data",)},
                extension_state=extension,
                confidence_at_snapshot=confidence,
                verification_status_at=verification,
                change_summary=change_summary,
                fields_changed=fields_changed or [],
                field_diffs=field_diffs or {},
                created_by=created_by,
                ingest_job_id=ingest_job_id,
            )

            self.pg.execute("""
                INSERT INTO version_snapshots (
                    snapshot_id, aqid, version, snapshot_type,
                    entity_state, extension_state,
                    confidence_at_snapshot, verification_status_at,
                    change_summary, fields_changed, field_diffs,
                    created_by, ingest_job_id, created_at
                ) VALUES (
                    :snapshot_id, :aqid, :version, :snapshot_type,
                    :entity_state ::jsonb, :extension_state ::jsonb,
                    :confidence, :verification,
                    :change_summary, :fields_changed ::jsonb, :field_diffs ::jsonb,
                    :created_by, :ingest_job_id, :created_at
                )
            """, {
                "snapshot_id":    snapshot.snapshot_id,
                "aqid":           aqid,
                "version":        version,
                "snapshot_type":  snapshot_type,
                "entity_state":   json.dumps(snapshot.entity_state, default=str),
                "extension_state": json.dumps(extension, default=str),
                "confidence":     confidence,
                "verification":   verification,
                "change_summary": change_summary,
                "fields_changed": json.dumps(fields_changed or []),
                "field_diffs":    json.dumps(field_diffs or {}, default=str),
                "created_by":     created_by,
                "ingest_job_id":  ingest_job_id,
                "created_at":     snapshot.created_at,
            })

            logger.info(f"Snapshot created: {snapshot.snapshot_id} for {aqid} v{version}")
            return snapshot

        except Exception as e:
            logger.error(f"Snapshot creation failed for {aqid}: {e}")
            return None

    # ------------------------------------------------------------------
    # READ QUERIES
    # ------------------------------------------------------------------

    def get_fact_history(
        self,
        aqid: str,
        field_name: str,
    ) -> List[Dict]:
        """Return full provenance history for a specific field on an entity."""
        rows = self.pg.execute("""
            SELECT fact_id, field_name, field_value, field_value_type,
                   source_url, source_name, source_tier, confidence,
                   is_primary, is_superseded, superseded_by,
                   citation_text, created_at, created_by
            FROM fact_provenance
            WHERE aqid = :aqid AND field_name = :field_name
            ORDER BY created_at DESC
        """, {"aqid": aqid, "field_name": field_name}).fetchall()

        return [dict(r._mapping) for r in rows]

    def get_entity_facts(self, aqid: str) -> Dict[str, List[Dict]]:
        """Return all provenance facts for an entity, grouped by field name."""
        rows = self.pg.execute("""
            SELECT field_name, fact_id, field_value, source_url,
                   source_tier, confidence, is_primary, is_superseded, created_at
            FROM fact_provenance
            WHERE aqid = :aqid
            ORDER BY field_name, confidence DESC, created_at DESC
        """, {"aqid": aqid}).fetchall()

        result: Dict[str, List[Dict]] = {}
        for row in rows:
            r = dict(row._mapping)
            field = r["field_name"]
            result.setdefault(field, []).append(r)
        return result

    def get_contradictions(
        self,
        aqid: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Query contradiction log with optional filters."""
        where = []
        params: Dict[str, Any] = {"limit": limit}

        if aqid:
            where.append("aqid = :aqid")
            params["aqid"] = aqid
        if status:
            where.append("status = :status")
            params["status"] = status

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        rows = self.pg.execute(f"""
            SELECT contradiction_id, aqid, field_name,
                   existing_value, incoming_value, confidence_delta,
                   resolution, status, created_at, resolved_by, resolved_at
            FROM contradiction_log
            {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit
        """, params).fetchall()

        return [dict(r._mapping) for r in rows]

    def get_review_queue(
        self,
        status: str = "open",
        priority: Optional[str] = None,
        assigned_to: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Return review queue items."""
        where = ["status = :status"]
        params: Dict[str, Any] = {"status": status, "limit": limit}

        if priority:
            where.append("priority = :priority")
            params["priority"] = priority
        if assigned_to:
            where.append("assigned_to = :assigned_to")
            params["assigned_to"] = assigned_to

        rows = self.pg.execute(f"""
            SELECT review_id, contradiction_id, aqid, field_name, priority,
                   entity_display_name, existing_value, incoming_value,
                   existing_source, incoming_source, confidence_delta,
                   status, assigned_to, created_at
            FROM review_queue
            WHERE {' AND '.join(where)}
            ORDER BY
                CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                              WHEN 'medium' THEN 3 ELSE 4 END,
                created_at ASC
            LIMIT :limit
        """, params).fetchall()

        return [dict(r._mapping) for r in rows]

    def get_snapshots(self, aqid: str) -> List[Dict]:
        """Return all version snapshots for an entity, newest first."""
        rows = self.pg.execute("""
            SELECT snapshot_id, aqid, version, snapshot_type,
                   confidence_at_snapshot, verification_status_at,
                   change_summary, fields_changed, created_by, created_at
            FROM version_snapshots
            WHERE aqid = :aqid
            ORDER BY created_at DESC
        """, {"aqid": aqid}).fetchall()

        return [dict(r._mapping) for r in rows]

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict]:
        """Return a single full snapshot including entity_state."""
        row = self.pg.execute(
            "SELECT * FROM version_snapshots WHERE snapshot_id = :id",
            {"id": snapshot_id}
        ).fetchone()
        return dict(row._mapping) if row else None
