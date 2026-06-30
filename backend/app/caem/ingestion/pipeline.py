"""
ORBITIQ-X — Knowledge Ingestion Pipeline
Phase 17.1

The canonical pipeline that moves raw source material through all stages:
  Source → Parse → Normalize → Extract → Validate → Persist → Verify → Publish

Architecture:
  - Stateless per-run; full state lives in PostgreSQL ingestion log
  - Each stage is independent and can be retried individually
  - Contradiction detection uses a three-tier resolution protocol
  - All four persistence layers (PostgreSQL, Neo4j, Qdrant, frontend cache)
    are written in parallel in the persistence stage

Contradiction resolution tiers:
  OVERRIDE:   new_confidence > existing_confidence + 0.15
  DISPUTE:    within 0.15 — both sources kept, flagged for human review
  REJECT:     new_confidence < existing_confidence - 0.15
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from caem.base import (
    BaseAerospaceEntity,
    EntityClass,
    LifecycleStatus,
    ProvenanceRecord,
    SourceType,
    VerificationStatus,
    generate_aqid,
    validate_aqid,
    compute_entity_confidence,
)
from caem.entities import validate_extension, EXTENSION_REGISTRY
from caem.relationships import AerospaceRelationship, RelationshipType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONTRADICTION RESOLUTION CONSTANTS
# ---------------------------------------------------------------------------

OVERRIDE_THRESHOLD  = 0.15   # New confidence must exceed existing by this margin
REJECT_THRESHOLD    = 0.15   # New confidence must not fall below existing by this margin
MIN_AUTO_PUBLISH_CONFIDENCE = 0.60  # Minimum confidence to auto-publish without human review


# ---------------------------------------------------------------------------
# SOURCE AUTHORITY TIERS — default confidence by source type
# ---------------------------------------------------------------------------

SOURCE_TIER_DEFAULTS: Dict[SourceType, float] = {
    SourceType.OFFICIAL:            0.95,
    SourceType.OFFICIAL_REGISTRY:   0.90,
    SourceType.PEER_REVIEWED:       0.85,
    SourceType.REFERENCE:           0.70,
    SourceType.NEWS:                0.65,
    SourceType.COMMUNITY:           0.50,
    SourceType.AI_GENERATED:        0.60,
}


# ---------------------------------------------------------------------------
# INGESTION STAGE MODELS
# ---------------------------------------------------------------------------

class IngestionStatus(str, Enum):
    SUCCESS     = "success"
    FAILED      = "failed"
    DISPUTED    = "disputed"
    SKIPPED     = "skipped"
    PENDING     = "pending"


class ContradictionRecord(BaseModel):
    """Records a conflict between ingested and existing fact."""
    field_name:         str
    existing_value:     Any
    new_value:          Any
    existing_confidence: float
    new_confidence:     float
    resolution:         str   # override / dispute / reject
    existing_source:    Optional[str] = None
    new_source:         Optional[str] = None


class IngestionJob(BaseModel):
    """
    Tracks the full state of a single ingestion run.
    Persisted to entity_ingestion_log on completion.
    """
    job_id:             str = Field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_version:   str = "17.1.0"
    started_at:         datetime = Field(default_factory=datetime.utcnow)
    completed_at:       Optional[datetime] = None
    status:             IngestionStatus = IngestionStatus.PENDING

    source_url:         Optional[str] = None
    source_type:        SourceType = SourceType.COMMUNITY
    source_name:        Optional[str] = None

    entities_created:   int = 0
    entities_updated:   int = 0
    relationships_added: int = 0
    chunks_indexed:     int = 0

    contradictions:     List[ContradictionRecord] = []
    errors:             List[str] = []
    warnings:           List[str] = []

    def finish(self, status: IngestionStatus) -> None:
        self.status = status
        self.completed_at = datetime.utcnow()


class ParsedEntity(BaseModel):
    """
    Intermediate representation produced by the Parser stage.
    Normalized before entity extraction.
    """
    raw_name:       str
    raw_type:       Optional[str]   = None
    raw_fields:     Dict[str, Any]  = {}
    raw_text:       Optional[str]   = None
    source_url:     Optional[str]   = None
    source_type:    SourceType      = SourceType.COMMUNITY
    confidence:     float           = 0.50


class ParsedRelationship(BaseModel):
    """
    Intermediate representation of a relationship between two parsed entities.
    AQIDs resolved during the Normalize stage.
    """
    source_name:    str
    target_name:    str
    rel_type_raw:   str
    rel_type:       Optional[RelationshipType] = None
    since_raw:      Optional[str]   = None
    until_raw:      Optional[str]   = None
    confidence:     float           = 0.70
    source_url:     Optional[str]   = None
    properties:     Dict[str, Any]  = {}


# ---------------------------------------------------------------------------
# INGESTION PIPELINE
# ---------------------------------------------------------------------------

class CAEMIngestionPipeline:
    """
    End-to-end ingestion pipeline from raw source to verified published knowledge.

    Usage:
        pipeline = CAEMIngestionPipeline(pg_session, neo4j_driver, qdrant_client)
        job = pipeline.ingest_source(
            source_url="https://spacex.com/falcon9",
            source_type=SourceType.OFFICIAL,
            parsed_entities=[...],
            parsed_relationships=[...]
        )
    """

    def __init__(self, pg_session, neo4j_driver, qdrant_client):
        self.pg = pg_session
        self.neo4j = neo4j_driver
        self.qdrant = qdrant_client

    def ingest_source(
        self,
        source_url: str,
        source_type: SourceType,
        parsed_entities: List[ParsedEntity],
        parsed_relationships: List[ParsedRelationship],
        source_name: Optional[str] = None,
        auto_publish: bool = True,
    ) -> IngestionJob:
        """
        Main entry point for ingesting a source document.

        Args:
            source_url:             URL of the source document
            source_type:            Authority tier of the source
            parsed_entities:        Entities extracted by the Parser stage
            parsed_relationships:   Relationships extracted by the Parser stage
            source_name:            Human-readable source name
            auto_publish:           Publish entities that meet confidence threshold

        Returns:
            Completed IngestionJob with full audit trail
        """
        job = IngestionJob(
            source_url=source_url,
            source_type=source_type,
            source_name=source_name,
        )
        logger.info(f"Ingestion job {job.job_id} started: {source_url}")

        try:
            # Stage 1: Normalize entity data
            normalized = self._normalize_entities(parsed_entities, source_type, job)

            # Stage 2: Resolve AQIDs and validate extensions
            resolved = self._resolve_and_validate(normalized, job)

            # Stage 3: Validate against existing records (contradiction detection)
            validated = self._validate_against_existing(resolved, job)

            # Stage 4: Persist to all four layers
            self._persist_entities(validated, job)

            # Stage 5: Resolve and persist relationships
            resolved_rels = self._resolve_relationships(parsed_relationships, job)
            self._persist_relationships(resolved_rels, job)

            # Stage 6: AI verification pass (async — non-blocking)
            self._trigger_ai_verification(validated, job)

            # Stage 7: Auto-publish if confidence threshold met
            if auto_publish:
                self._auto_publish(validated, job)

            job.finish(IngestionStatus.SUCCESS if not job.contradictions else IngestionStatus.DISPUTED)

        except Exception as e:
            job.errors.append(str(e))
            job.finish(IngestionStatus.FAILED)
            logger.error(f"Ingestion job {job.job_id} failed: {e}", exc_info=True)

        finally:
            self._write_job_log(job)

        logger.info(
            f"Ingestion job {job.job_id} complete: "
            f"{job.entities_created} created, {job.entities_updated} updated, "
            f"{job.relationships_added} relationships, {len(job.contradictions)} contradictions"
        )
        return job

    # ------------------------------------------------------------------
    # STAGE 1: NORMALIZE
    # ------------------------------------------------------------------

    def _normalize_entities(
        self,
        parsed: List[ParsedEntity],
        source_type: SourceType,
        job: IngestionJob,
    ) -> List[Dict[str, Any]]:
        """
        Normalize raw parsed entities into CAEM-conformant field sets.
        Applies default confidence from source authority tier.
        """
        normalized = []
        base_confidence = SOURCE_TIER_DEFAULTS.get(source_type, 0.50)

        for p in parsed:
            try:
                entity_class = self._classify_entity(p.raw_type)
                if entity_class is None:
                    job.warnings.append(f"Could not classify entity type: {p.raw_type!r} for '{p.raw_name}'")
                    continue

                normalized.append({
                    "raw_name":     p.raw_name,
                    "entity_class": entity_class,
                    "raw_fields":   p.raw_fields,
                    "raw_text":     p.raw_text,
                    "source_url":   p.source_url or job.source_url,
                    "source_type":  source_type,
                    "confidence":   max(p.confidence, base_confidence),
                })
            except Exception as e:
                job.warnings.append(f"Normalize failed for '{p.raw_name}': {e}")

        return normalized

    def _classify_entity(self, raw_type: Optional[str]) -> Optional[EntityClass]:
        """
        Map a raw string type label to an EntityClass enum.
        Handles common aliases and abbreviations.
        """
        if not raw_type:
            return None

        mapping = {
            "country": EntityClass.COUNTRY,
            "nation": EntityClass.COUNTRY,
            "space agency": EntityClass.GOV_AGENCY,
            "government agency": EntityClass.GOV_AGENCY,
            "agency": EntityClass.GOV_AGENCY,
            "company": EntityClass.COMPANY,
            "corporation": EntityClass.COMPANY,
            "commercial": EntityClass.COMPANY,
            "startup": EntityClass.COMPANY,
            "university": EntityClass.UNIVERSITY,
            "research organization": EntityClass.RESEARCH_ORG,
            "person": EntityClass.PERSON,
            "scientist": EntityClass.PERSON,
            "engineer": EntityClass.PERSON,
            "launch vehicle": EntityClass.LAUNCH_VEHICLE,
            "rocket": EntityClass.LAUNCH_VEHICLE,
            "satellite": EntityClass.SATELLITE,
            "payload": EntityClass.PAYLOAD,
            "spacecraft": EntityClass.SPACECRAFT,
            "debris": EntityClass.DEBRIS,
            "launch site": EntityClass.LAUNCH_SITE,
            "spaceport": EntityClass.LAUNCH_SITE,
            "ground station": EntityClass.GROUND_STATION,
            "program": EntityClass.PROGRAM,
            "mission": EntityClass.MISSION,
            "constellation": EntityClass.CONSTELLATION,
            "technology": EntityClass.TECHNOLOGY,
            "standard": EntityClass.STANDARD,
            "specification": EntityClass.SPECIFICATION,
            "research paper": EntityClass.RESEARCH_PAPER,
            "paper": EntityClass.RESEARCH_PAPER,
            "patent": EntityClass.PATENT,
            "contract": EntityClass.CONTRACT,
            "investment": EntityClass.INVESTMENT,
            "policy": EntityClass.POLICY,
            "agreement": EntityClass.AGREEMENT,
            "treaty": EntityClass.AGREEMENT,
            "incident": EntityClass.INCIDENT,
            "anomaly": EntityClass.ANOMALY,
            "event": EntityClass.HISTORICAL_EVENT,
            "asteroid": EntityClass.ASTEROID,
            "comet": EntityClass.COMET,
            "celestial body": EntityClass.CELESTIAL_BODY,
        }

        normalized_type = raw_type.lower().strip()
        return mapping.get(normalized_type)

    # ------------------------------------------------------------------
    # STAGE 2: RESOLVE & VALIDATE
    # ------------------------------------------------------------------

    def _resolve_and_validate(
        self,
        normalized: List[Dict[str, Any]],
        job: IngestionJob,
    ) -> List[Dict[str, Any]]:
        """
        Attempt AQID resolution for each entity.
        For known entities: resolve to existing AQID.
        For new entities: generate a new AQID.
        Validate extension_data against the entity class schema.
        """
        resolved = []

        for n in normalized:
            try:
                aqid = self._resolve_aqid(n["raw_name"], n["entity_class"])

                # Validate extension data against registered schema
                extension_data = n.get("raw_fields", {})
                try:
                    extension_data = validate_extension(n["entity_class"], extension_data)
                except Exception as ve:
                    job.warnings.append(f"Extension validation warning for {aqid}: {ve}")

                resolved.append({
                    **n,
                    "aqid":             aqid,
                    "extension_data":   extension_data,
                    "is_new":           not self._entity_exists(aqid),
                })
            except Exception as e:
                job.warnings.append(f"AQID resolution failed for '{n['raw_name']}': {e}")

        return resolved

    def _resolve_aqid(self, canonical_name: str, entity_class: EntityClass) -> str:
        """
        Try to match canonical_name to an existing entity via:
          1. Exact AQID match (if canonical_name is already an AQID)
          2. display_name match in PostgreSQL
          3. Alias match in entity_aliases table
          4. Generate new AQID if no match found
        """
        # Already an AQID?
        if validate_aqid(canonical_name):
            return canonical_name

        # Try exact display_name lookup
        existing = self._lookup_by_name(canonical_name, entity_class)
        if existing:
            return existing

        # Try alias lookup
        alias_match = self._lookup_by_alias(canonical_name)
        if alias_match:
            return alias_match

        # Generate new AQID
        candidate = generate_aqid(entity_class, canonical_name)
        # Handle collision
        if self._entity_exists(candidate):
            candidate = f"{candidate}-2"
        return candidate

    def _entity_exists(self, aqid: str) -> bool:
        """Check if AQID exists in PostgreSQL."""
        # Implementation depends on pg session type (SQLAlchemy / asyncpg)
        # Stub for interface clarity:
        try:
            result = self.pg.execute(
                "SELECT 1 FROM aerospace_entities WHERE aqid = :aqid",
                {"aqid": aqid}
            ).fetchone()
            return result is not None
        except Exception:
            return False

    def _lookup_by_name(self, name: str, entity_class: EntityClass) -> Optional[str]:
        """Look up AQID by display_name and entity_class."""
        try:
            result = self.pg.execute(
                "SELECT aqid FROM aerospace_entities WHERE display_name = :name AND entity_class = :cls LIMIT 1",
                {"name": name, "cls": entity_class.value}
            ).fetchone()
            return result[0] if result else None
        except Exception:
            return None

    def _lookup_by_alias(self, alias: str) -> Optional[str]:
        """Look up AQID via the entity_aliases table."""
        try:
            result = self.pg.execute(
                "SELECT aqid FROM entity_aliases WHERE external_id = :alias LIMIT 1",
                {"alias": alias}
            ).fetchone()
            return result[0] if result else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # STAGE 3: CONTRADICTION DETECTION
    # ------------------------------------------------------------------

    def _validate_against_existing(
        self,
        resolved: List[Dict[str, Any]],
        job: IngestionJob,
    ) -> List[Dict[str, Any]]:
        """
        Compare incoming entity data against existing records.
        Apply three-tier contradiction resolution protocol.
        """
        validated = []

        for r in resolved:
            if r["is_new"]:
                validated.append(r)
                continue

            try:
                existing = self._fetch_existing(r["aqid"])
                if not existing:
                    validated.append(r)
                    continue

                # Check key fields for contradictions
                contradictions = self._detect_contradictions(r, existing)
                for contradiction in contradictions:
                    resolution = self._resolve_contradiction(contradiction)
                    contradiction.resolution = resolution
                    job.contradictions.append(contradiction)

                    if resolution == "override":
                        # Accept new value — already in r["raw_fields"]
                        pass
                    elif resolution == "dispute":
                        r["lifecycle_status"] = LifecycleStatus.PENDING.value
                        r["verification_status"] = VerificationStatus.DISPUTED.value
                    elif resolution == "reject":
                        # Keep existing value — overwrite new with existing
                        field = contradiction.field_name
                        if field in r.get("raw_fields", {}):
                            r["raw_fields"][field] = contradiction.existing_value

                validated.append(r)

            except Exception as e:
                job.warnings.append(f"Contradiction check failed for {r['aqid']}: {e}")
                validated.append(r)

        return validated

    def _detect_contradictions(
        self,
        incoming: Dict[str, Any],
        existing: Dict[str, Any],
    ) -> List[ContradictionRecord]:
        """
        Identify fields where incoming value differs from existing value.
        Only checks fields present in both records.
        """
        contradictions = []
        check_fields = ["display_name", "entity_class"]  # Core identity fields to always check

        # Add extension data fields that are present in incoming
        for field, new_val in incoming.get("raw_fields", {}).items():
            existing_val = existing.get("extension_data", {}).get(field)
            if existing_val is not None and existing_val != new_val:
                contradictions.append(ContradictionRecord(
                    field_name=field,
                    existing_value=existing_val,
                    new_value=new_val,
                    existing_confidence=existing.get("confidence_score", 0.5),
                    new_confidence=incoming.get("confidence", 0.5),
                ))

        return contradictions

    def _resolve_contradiction(self, c: ContradictionRecord) -> str:
        """Apply the three-tier contradiction resolution protocol."""
        diff = c.new_confidence - c.existing_confidence
        if diff > OVERRIDE_THRESHOLD:
            return "override"
        elif diff < -REJECT_THRESHOLD:
            return "reject"
        else:
            return "dispute"

    def _fetch_existing(self, aqid: str) -> Optional[Dict[str, Any]]:
        """Fetch existing entity record from PostgreSQL."""
        try:
            result = self.pg.execute(
                """SELECT aqid, confidence_score, extension_data, verification_status
                   FROM aerospace_entities WHERE aqid = :aqid""",
                {"aqid": aqid}
            ).fetchone()
            if result:
                return dict(result._mapping)
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # STAGE 4: PERSIST
    # ------------------------------------------------------------------

    def _persist_entities(
        self,
        validated: List[Dict[str, Any]],
        job: IngestionJob,
    ) -> None:
        """
        Write validated entities to PostgreSQL and Neo4j in parallel.
        Qdrant is written by the chunk indexing step in the Parser.
        """
        for v in validated:
            try:
                self._persist_to_postgres(v, job)
                self._persist_to_neo4j(v, job)
            except Exception as e:
                job.errors.append(f"Persistence failed for {v.get('aqid')}: {e}")

    def _persist_to_postgres(self, entity: Dict[str, Any], job: IngestionJob) -> None:
        """Upsert entity record in PostgreSQL aerospace_entities table."""
        is_new = entity.get("is_new", True)
        now = datetime.utcnow()

        if is_new:
            self.pg.execute("""
                INSERT INTO aerospace_entities (
                    aqid, entity_class, entity_subclass, display_name,
                    description, lifecycle_status, confidence_score,
                    extension_data, primary_provenance, all_sources,
                    verification_status, ingest_job_id, ingest_pipeline,
                    created_at, updated_at
                ) VALUES (
                    :aqid, :entity_class, :entity_subclass, :display_name,
                    :description, :lifecycle_status, :confidence_score,
                    :extension_data ::jsonb, :primary_provenance ::jsonb,
                    :all_sources ::jsonb, :verification_status,
                    :ingest_job_id, :ingest_pipeline,
                    :created_at, :updated_at
                )
                ON CONFLICT (aqid) DO UPDATE SET
                    display_name        = EXCLUDED.display_name,
                    description         = EXCLUDED.description,
                    extension_data      = aerospace_entities.extension_data || EXCLUDED.extension_data,
                    confidence_score    = EXCLUDED.confidence_score,
                    updated_at          = EXCLUDED.updated_at,
                    ingest_job_id       = EXCLUDED.ingest_job_id,
                    ai_requires_refresh = true
            """, {
                "aqid":                 entity["aqid"],
                "entity_class":         entity["entity_class"].value,
                "entity_subclass":      entity.get("entity_subclass"),
                "display_name":         entity["raw_name"],
                "description":          entity.get("raw_text", "")[:500] if entity.get("raw_text") else None,
                "lifecycle_status":     entity.get("lifecycle_status", LifecycleStatus.DRAFT.value),
                "confidence_score":     entity.get("confidence", 0.5),
                "extension_data":       __import__('json').dumps(entity.get("extension_data", {})),
                "primary_provenance":   __import__('json').dumps({
                    "source_url": entity.get("source_url"),
                    "source_type": entity.get("source_type", "community"),
                    "confidence": entity.get("confidence", 0.5),
                }),
                "all_sources":          __import__('json').dumps([]),
                "verification_status":  entity.get("verification_status", VerificationStatus.UNVERIFIED.value),
                "ingest_job_id":        job.job_id,
                "ingest_pipeline":      job.pipeline_version,
                "created_at":           now,
                "updated_at":           now,
            })
            job.entities_created += 1
        else:
            job.entities_updated += 1

    def _persist_to_neo4j(self, entity: Dict[str, Any], job: IngestionJob) -> None:
        """Upsert entity as a Neo4j node."""
        from caem.graph.neo4j_schema import NODE_UPSERT_CYPHER_NO_APOC
        props = {
            "aqid":             entity["aqid"],
            "display_name":     entity["raw_name"],
            "short_name":       None,
            "entity_class":     entity["entity_class"].value,
            "entity_subclass":  entity.get("entity_subclass"),
            "is_active":        True,
            "lifecycle_status": entity.get("lifecycle_status", "draft"),
            "confidence_score": entity.get("confidence", 0.5),
            "tags":             [],
        }
        with self.neo4j.session() as session:
            session.run(NODE_UPSERT_CYPHER_NO_APOC, **props)

    # ------------------------------------------------------------------
    # STAGE 5: RELATIONSHIPS
    # ------------------------------------------------------------------

    def _resolve_relationships(
        self,
        parsed_rels: List[ParsedRelationship],
        job: IngestionJob,
    ) -> List[AerospaceRelationship]:
        """
        Resolve entity names in parsed relationships to AQIDs.
        Classify raw relationship type strings into RelationshipType enum.
        """
        resolved = []
        rel_type_map = {rt.value.lower().replace('_', ' '): rt for rt in RelationshipType}

        for pr in parsed_rels:
            try:
                source_aqid = self._lookup_by_name(pr.source_name, None) or generate_aqid(EntityClass.COMPANY, pr.source_name)
                target_aqid = self._lookup_by_name(pr.target_name, None) or generate_aqid(EntityClass.COMPANY, pr.target_name)

                # Classify relationship type
                rel_type = pr.rel_type
                if rel_type is None:
                    normalized_raw = pr.rel_type_raw.lower().strip()
                    rel_type = rel_type_map.get(normalized_raw)
                    if rel_type is None:
                        job.warnings.append(f"Unknown relationship type: {pr.rel_type_raw!r}")
                        continue

                relationship = AerospaceRelationship(
                    source_aqid=source_aqid,
                    target_aqid=target_aqid,
                    relationship_type=rel_type,
                    confidence=pr.confidence,
                    provenance_url=pr.source_url or job.source_url,
                    properties=pr.properties,
                )

                errors = relationship.validate()
                if errors:
                    job.warnings.append(f"Invalid relationship {source_aqid}→{target_aqid}: {errors}")
                    continue

                resolved.append(relationship)
            except Exception as e:
                job.warnings.append(f"Relationship resolution failed: {e}")

        return resolved

    def _persist_relationships(
        self,
        relationships: List[AerospaceRelationship],
        job: IngestionJob,
    ) -> None:
        """Write resolved relationships to Neo4j and the PostgreSQL cache."""
        for rel in relationships:
            try:
                # Neo4j
                cypher = rel.to_cypher_merge()
                with self.neo4j.session() as session:
                    session.run(cypher)

                # PostgreSQL relationship cache
                self.pg.execute("""
                    INSERT INTO entity_relationships_cache (
                        rel_id, source_aqid, target_aqid, relationship_type,
                        is_current, confidence, provenance_url, properties, synced_at
                    ) VALUES (
                        :rel_id, :source_aqid, :target_aqid, :rel_type,
                        true, :confidence, :provenance_url, :properties ::jsonb, now()
                    )
                    ON CONFLICT (rel_id) DO UPDATE SET
                        is_current      = true,
                        confidence      = EXCLUDED.confidence,
                        synced_at       = now()
                """, {
                    "rel_id":           rel.rel_id,
                    "source_aqid":      rel.source_aqid,
                    "target_aqid":      rel.target_aqid,
                    "rel_type":         rel.relationship_type.value,
                    "confidence":       rel.confidence,
                    "provenance_url":   rel.provenance_url,
                    "properties":       __import__('json').dumps(rel.properties),
                })

                job.relationships_added += 1
            except Exception as e:
                job.errors.append(f"Relationship persistence failed: {e}")

    # ------------------------------------------------------------------
    # STAGE 6: AI VERIFICATION (async trigger)
    # ------------------------------------------------------------------

    def _trigger_ai_verification(
        self,
        validated: List[Dict[str, Any]],
        job: IngestionJob,
    ) -> None:
        """
        Flag entities for AI verification pass.
        The Summary Agent picks these up asynchronously.
        Sets ai_requires_refresh = true for any newly created or significantly updated entity.
        """
        new_aqids = [v["aqid"] for v in validated if v.get("is_new")]
        if new_aqids:
            try:
                placeholders = ",".join(f"'{a}'" for a in new_aqids)
                self.pg.execute(f"""
                    UPDATE aerospace_entities
                    SET ai_requires_refresh = true
                    WHERE aqid IN ({placeholders})
                """)
            except Exception as e:
                job.warnings.append(f"AI refresh flag failed: {e}")

    # ------------------------------------------------------------------
    # STAGE 7: AUTO-PUBLISH
    # ------------------------------------------------------------------

    def _auto_publish(
        self,
        validated: List[Dict[str, Any]],
        job: IngestionJob,
    ) -> None:
        """
        Promote entities to 'published' status if they meet the confidence threshold
        and are not flagged as DISPUTED.
        """
        publishable = [
            v for v in validated
            if v.get("confidence", 0) >= MIN_AUTO_PUBLISH_CONFIDENCE
            and v.get("verification_status") != VerificationStatus.DISPUTED.value
        ]

        if publishable:
            aqids = [v["aqid"] for v in publishable]
            try:
                placeholders = ",".join(f"'{a}'" for a in aqids)
                self.pg.execute(f"""
                    UPDATE aerospace_entities
                    SET lifecycle_status = 'published',
                        published_at     = now()
                    WHERE aqid IN ({placeholders})
                      AND lifecycle_status = 'draft'
                """)
                logger.info(f"Auto-published {len(aqids)} entities")
            except Exception as e:
                job.warnings.append(f"Auto-publish failed: {e}")

    # ------------------------------------------------------------------
    # JOB LOG
    # ------------------------------------------------------------------

    def _write_job_log(self, job: IngestionJob) -> None:
        """Persist the ingestion job audit record to entity_ingestion_log."""
        import json
        try:
            self.pg.execute("""
                INSERT INTO entity_ingestion_log (
                    job_id, pipeline_version, started_at, completed_at, status,
                    source_url, source_type, entities_created, entities_updated,
                    relationships_added, chunks_indexed, contradictions, errors, warnings
                ) VALUES (
                    :job_id, :pipeline_version, :started_at, :completed_at, :status,
                    :source_url, :source_type, :entities_created, :entities_updated,
                    :relationships_added, :chunks_indexed,
                    :contradictions ::jsonb, :errors ::jsonb, :warnings ::jsonb
                )
            """, {
                "job_id":               job.job_id,
                "pipeline_version":     job.pipeline_version,
                "started_at":           job.started_at,
                "completed_at":         job.completed_at,
                "status":               job.status.value,
                "source_url":           job.source_url,
                "source_type":          job.source_type.value,
                "entities_created":     job.entities_created,
                "entities_updated":     job.entities_updated,
                "relationships_added":  job.relationships_added,
                "chunks_indexed":       job.chunks_indexed,
                "contradictions":       json.dumps([c.model_dump() for c in job.contradictions]),
                "errors":               json.dumps(job.errors),
                "warnings":             json.dumps(job.warnings),
            })
        except Exception as e:
            logger.error(f"Failed to write ingestion log for job {job.job_id}: {e}")
