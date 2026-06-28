"""
ORBITIQ-X — Knowledge Ingestion Orchestrator
Phase 17.4

The orchestrator manages the full ingestion lifecycle:
  1. Loads registered source adapters
  2. Determines which adapters are due to run (based on schedule)
  3. Runs each adapter and routes SourceRecords to the ingestion pipeline
  4. Writes job results to entity_ingestion_log
  5. Integrates provenance recording via ProvenanceService
  6. Triggers AI summary refresh for updated entities

The orchestrator is called by APScheduler (existing ORBITIQ-X scheduler).
It is stateless — all schedule state lives in ingestion_schedule table.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Type

from caem.base import EntityClass, generate_aqid, validate_aqid, LifecycleStatus
from caem.provenance.models import SourceTier, TIER_CONFIDENCE_WEIGHTS
from caem.provenance.service import ProvenanceService
from caem.ingestion.pipeline import CAEMIngestionPipeline, ParsedEntity, IngestionJob, IngestionStatus
from caem.ingestion.sources.base import SourceAdapter, SourceRecord, FetchResult
from caem.ingestion.sources.tier1_space_track import SpaceTrackAdapter
from caem.ingestion.sources.tier1_nasa import NASATechPortAdapter, NASAMissionAdapter
from caem.ingestion.sources.tier2_registries import CelestrakAdapter, UNOOSAAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ADAPTER REGISTRY
# Maps adapter name → class for dynamic loading
# ---------------------------------------------------------------------------

ADAPTER_REGISTRY: Dict[str, Type[SourceAdapter]] = {
    "space_track":          SpaceTrackAdapter,
    "nasa_techport":        NASATechPortAdapter,
    "nasa_missions":        NASAMissionAdapter,
    "celestrak":            CelestrakAdapter,
    "unoosa":               UNOOSAAdapter,
}


# ---------------------------------------------------------------------------
# INGESTION SCHEDULE ENTRY
# ---------------------------------------------------------------------------

class ScheduleEntry:
    """Tracks when a source adapter last ran and when it should run next."""

    def __init__(self, adapter_name: str, interval_s: int):
        self.adapter_name   = adapter_name
        self.interval_s     = interval_s
        self.last_run_at:   Optional[datetime] = None
        self.next_run_at:   datetime = datetime.utcnow()
        self.total_runs:    int = 0
        self.total_records: int = 0
        self.last_status:   str = "never_run"

    def is_due(self) -> bool:
        return datetime.utcnow() >= self.next_run_at

    def mark_complete(self, records_ingested: int, status: str = "success") -> None:
        now = datetime.utcnow()
        self.last_run_at    = now
        self.next_run_at    = now + timedelta(seconds=self.interval_s)
        self.total_runs     += 1
        self.total_records  += records_ingested
        self.last_status    = status


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# ---------------------------------------------------------------------------

class IngestionOrchestrator:
    """
    Manages the full ingestion lifecycle across all registered source adapters.

    Usage (from APScheduler job or direct call):
        orchestrator = IngestionOrchestrator(pg_session, neo4j_driver, qdrant_client)
        orchestrator.register_adapter("space_track", {"identity": ..., "password": ...})
        orchestrator.register_adapter("nasa_missions", {})
        results = orchestrator.run_due()
    """

    def __init__(self, pg_session, neo4j_driver, qdrant_client):
        self.pg         = pg_session
        self.neo4j      = neo4j_driver
        self.qdrant     = qdrant_client
        self.provenance = ProvenanceService(pg_session)
        self.pipeline   = CAEMIngestionPipeline(pg_session, neo4j_driver, qdrant_client)
        self._adapters:  Dict[str, SourceAdapter]   = {}
        self._schedule:  Dict[str, ScheduleEntry]   = {}
        self._results:   List[Dict[str, Any]]        = []

    def register_adapter(
        self,
        adapter_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a source adapter by name.
        Adapter must be in ADAPTER_REGISTRY.
        """
        adapter_class = ADAPTER_REGISTRY.get(adapter_name)
        if not adapter_class:
            raise ValueError(
                f"Unknown adapter: {adapter_name}. "
                f"Available: {list(ADAPTER_REGISTRY.keys())}"
            )
        adapter = adapter_class(config or {})
        self._adapters[adapter_name] = adapter
        self._schedule[adapter_name] = ScheduleEntry(
            adapter_name=adapter_name,
            interval_s=adapter.fetch_interval_s,
        )
        logger.info(f"Adapter registered: {adapter_name} (interval={adapter.fetch_interval_s}s)")

    def register_all(self, configs: Optional[Dict[str, Dict]] = None) -> None:
        """Register all adapters in ADAPTER_REGISTRY with optional per-adapter configs."""
        configs = configs or {}
        for name in ADAPTER_REGISTRY:
            self.register_adapter(name, configs.get(name, {}))

    def run_due(self) -> List[Dict[str, Any]]:
        """
        Run all adapters that are due for a fetch.
        Returns list of result dicts.
        """
        run_results = []
        for adapter_name, schedule in self._schedule.items():
            if schedule.is_due():
                result = self._run_adapter(adapter_name)
                run_results.append(result)
                self._results.append(result)
        return run_results

    def run_adapter(self, adapter_name: str) -> Dict[str, Any]:
        """Force-run a specific adapter regardless of schedule."""
        if adapter_name not in self._adapters:
            raise ValueError(f"Adapter not registered: {adapter_name}")
        return self._run_adapter(adapter_name)

    def _run_adapter(self, adapter_name: str) -> Dict[str, Any]:
        """Execute one adapter and route its records through the ingestion pipeline."""
        adapter     = self._adapters[adapter_name]
        schedule    = self._schedule[adapter_name]
        job_id      = uuid.uuid4().hex
        started_at  = datetime.utcnow()

        logger.info(f"[{job_id}] Starting adapter: {adapter_name}")

        # Collect records from adapter
        records: List[SourceRecord] = []
        fetch_errors: List[str] = []
        try:
            for record in adapter.fetch():
                records.append(record)
        except Exception as e:
            fetch_errors.append(str(e))
            logger.error(f"[{job_id}] Adapter {adapter_name} fetch error: {e}", exc_info=True)

        logger.info(f"[{job_id}] {adapter_name}: fetched {len(records)} records")

        # Convert SourceRecords → ParsedEntities for the pipeline
        parsed_entities = [self._source_record_to_parsed(r) for r in records]
        parsed_rels     = self._extract_relationships(records)

        # Run through ingestion pipeline
        job: Optional[IngestionJob] = None
        pipeline_errors: List[str] = []
        try:
            job = self.pipeline.ingest_source(
                source_url=f"adapter://{adapter_name}",
                source_type=adapter.source_tier,
                parsed_entities=parsed_entities,
                parsed_relationships=parsed_rels,
                source_name=adapter.source_name,
                auto_publish=True,
            )
        except Exception as e:
            pipeline_errors.append(str(e))
            logger.error(f"[{job_id}] Pipeline error for {adapter_name}: {e}", exc_info=True)

        # Record provenance for each ingested entity field
        for record in records:
            try:
                self._record_fact_provenance(record, adapter.source_tier, job_id)
            except Exception as e:
                logger.debug(f"Provenance recording failed for {record.source_id}: {e}")

        # Update schedule
        ingested = job.entities_created + job.entities_updated if job else 0
        status   = "success" if not fetch_errors and not pipeline_errors else "partial"
        schedule.mark_complete(ingested, status)

        result = {
            "job_id":           job_id,
            "adapter_name":     adapter_name,
            "started_at":       started_at.isoformat(),
            "completed_at":     datetime.utcnow().isoformat(),
            "records_fetched":  len(records),
            "entities_created": job.entities_created if job else 0,
            "entities_updated": job.entities_updated if job else 0,
            "relationships_added": job.relationships_added if job else 0,
            "contradictions":   len(job.contradictions) if job else 0,
            "fetch_errors":     fetch_errors,
            "pipeline_errors":  pipeline_errors,
            "status":           status,
        }

        self._write_job_log(result, job)
        logger.info(
            f"[{job_id}] {adapter_name} complete: "
            f"{ingested} ingested, {len(records)} fetched, status={status}"
        )
        return result

    def _source_record_to_parsed(self, record: SourceRecord) -> ParsedEntity:
        """Convert SourceRecord → ParsedEntity for the ingestion pipeline."""
        from caem.ingestion.pipeline import ParsedEntity
        return ParsedEntity(
            raw_name=record.canonical_name,
            raw_type=record.entity_class.value.lower().replace("_", " "),
            raw_fields=record.fields,
            raw_text=record.description,
            source_url=record.source_url,
            source_type=record.source_tier,
            confidence=TIER_CONFIDENCE_WEIGHTS.get(record.source_tier, 0.50),
        )

    def _extract_relationships(self, records: List[SourceRecord]):
        """Extract ParsedRelationship objects from raw_relationships on each record."""
        from caem.ingestion.pipeline import ParsedRelationship
        parsed_rels = []
        for record in records:
            for rel in record.raw_relationships:
                try:
                    parsed_rels.append(ParsedRelationship(
                        source_name=record.canonical_name,
                        target_name=rel.get("target_name", ""),
                        rel_type_raw=rel.get("rel_type", ""),
                        confidence=rel.get("confidence", 0.70),
                        source_url=record.source_url,
                        properties=rel.get("properties", {}),
                    ))
                except Exception:
                    pass
        return parsed_rels

    def _record_fact_provenance(
        self,
        record: SourceRecord,
        tier: SourceTier,
        job_id: str,
    ) -> None:
        """Record field-level provenance for high-value fields on ingested entities."""
        # Determine the entity's AQID
        aqid = generate_aqid(record.entity_class, record.canonical_name)

        high_value_fields = {
            "payload_leo_kg", "norad_id", "cospar_id", "orbit_regime",
            "launch_date", "total_launches", "success_rate_pct",
            "altitude_km", "inclination_deg", "period_min",
        }

        for field_name, field_value in record.fields.items():
            if field_name in high_value_fields and field_value is not None:
                fact = self.provenance.record_fact(
                    aqid=aqid,
                    field_name=field_name,
                    field_value=field_value,
                    source_url=record.source_url,
                    source_tier=tier,
                    ingest_job_id=job_id,
                )
                self.provenance.detect_contradiction(
                    aqid=aqid,
                    field_name=field_name,
                    incoming_value=field_value,
                    incoming_confidence=fact.confidence,
                    incoming_fact_id=fact.fact_id,
                    incoming_source_url=record.source_url,
                    incoming_tier=tier,
                    ingest_job_id=job_id,
                )

    def _write_job_log(self, result: Dict, job: Optional[Any]) -> None:
        """Write ingestion run result to PostgreSQL ingestion_schedule_log."""
        try:
            self.pg.execute("""
                INSERT INTO ingestion_schedule_log (
                    job_id, adapter_name, started_at, completed_at,
                    records_fetched, entities_created, entities_updated,
                    relationships_added, contradictions,
                    fetch_errors, pipeline_errors, status
                ) VALUES (
                    :job_id, :adapter_name, :started_at, :completed_at,
                    :records_fetched, :entities_created, :entities_updated,
                    :relationships_added, :contradictions,
                    :fetch_errors::jsonb, :pipeline_errors::jsonb, :status
                )
            """, {
                "job_id":              result["job_id"],
                "adapter_name":        result["adapter_name"],
                "started_at":          result["started_at"],
                "completed_at":        result["completed_at"],
                "records_fetched":     result["records_fetched"],
                "entities_created":    result["entities_created"],
                "entities_updated":    result["entities_updated"],
                "relationships_added": result["relationships_added"],
                "contradictions":      result["contradictions"],
                "fetch_errors":        json.dumps(result["fetch_errors"]),
                "pipeline_errors":     json.dumps(result["pipeline_errors"]),
                "status":              result["status"],
            })
        except Exception as e:
            logger.error(f"Failed to write job log for {result['job_id']}: {e}")

    def get_schedule_status(self) -> List[Dict[str, Any]]:
        """Return current schedule state for all registered adapters."""
        return [
            {
                "adapter_name":     name,
                "last_run_at":      s.last_run_at.isoformat() if s.last_run_at else None,
                "next_run_at":      s.next_run_at.isoformat(),
                "is_due":           s.is_due(),
                "total_runs":       s.total_runs,
                "total_records":    s.total_records,
                "last_status":      s.last_status,
                "interval_hours":   s.interval_s / 3600,
            }
            for name, s in self._schedule.items()
        ]
