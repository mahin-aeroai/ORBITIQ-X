"""
ORBITIQ-X — Knowledge Ingestion Source Base
Phase 17.4

Every source adapter inherits from SourceAdapter.
A source adapter is responsible for:
  1. Fetching raw data from one external source
  2. Parsing it into SourceRecord objects
  3. Reporting fetch metrics back to the orchestrator

Adapters are stateless. All state lives in PostgreSQL ingestion_log.
Rate limiting, retry logic, and scheduling are handled by the orchestrator.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generator, List, Optional

from pydantic import BaseModel, Field

from caem.base import EntityClass
from caem.provenance.models import SourceTier
from caem.relationships import RelationshipType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SOURCE RECORD — normalized output from every adapter
# ---------------------------------------------------------------------------

class SourceRecord(BaseModel):
    """
    Normalized output produced by a source adapter.
    Every adapter converts its raw data into SourceRecords.
    The ingestion pipeline then processes SourceRecords into entities and relationships.
    """
    # Identity
    source_id:          str                         # Stable ID within source system
    source_system:      str                         # e.g. "space_track", "nasa_jpl"
    source_tier:        SourceTier
    source_url:         Optional[str]   = None
    fetched_at:         datetime        = Field(default_factory=datetime.utcnow)

    # Entity data
    entity_class:       EntityClass
    canonical_name:     str                         # Used for AQID generation
    display_name:       str
    description:        Optional[str]   = None
    fields:             Dict[str, Any]  = {}        # Maps to extension_data fields
    tags:               List[str]       = []
    domains:            List[str]       = []

    # Relationships to other records (resolved to AQIDs during pipeline)
    raw_relationships:  List[Dict[str, Any]] = []   # [{rel_type, target_name, target_class, ...}]

    # Raw payload for audit
    raw_payload:        Optional[Dict[str, Any]] = None

    # Deduplication
    content_hash:       Optional[str]   = None      # SHA-256 of canonical fields

    def compute_hash(self) -> str:
        """Compute a stable content hash for deduplication."""
        key = f"{self.source_system}:{self.source_id}:{self.canonical_name}"
        self.content_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.content_hash


class FetchResult(BaseModel):
    """Metrics returned by a source adapter after a fetch run."""
    source_system:      str
    source_tier:        SourceTier
    started_at:         datetime
    completed_at:       datetime        = Field(default_factory=datetime.utcnow)
    records_fetched:    int             = 0
    records_parsed:     int             = 0
    records_skipped:    int             = 0
    errors:             List[str]       = []
    warnings:           List[str]       = []
    next_fetch_hint:    Optional[str]   = None  # ISO datetime for next recommended fetch

    @property
    def success(self) -> bool:
        return self.records_parsed > 0 and len(self.errors) == 0

    @property
    def duration_s(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()


# ---------------------------------------------------------------------------
# BASE ADAPTER
# ---------------------------------------------------------------------------

class SourceAdapter(ABC):
    """
    Abstract base for all knowledge source adapters.

    Subclasses implement `fetch()` which yields `SourceRecord` objects.
    The orchestrator calls `fetch()` and routes records to the pipeline.
    """

    #: Human-readable name for this source
    source_name: str = "unknown"

    #: Authority tier for all records from this source
    source_tier: SourceTier = SourceTier.TIER_6_COMMUNITY

    #: Default fetch interval in seconds (used by scheduler)
    fetch_interval_s: int = 86400  # 24 hours

    #: Maximum records to fetch in a single run (0 = no limit)
    max_records_per_run: int = 0

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def fetch(self) -> Generator[SourceRecord, None, None]:
        """
        Fetch records from the source.
        Yields SourceRecord objects. Must handle its own pagination and retries.
        """
        ...

    def run(self) -> FetchResult:
        """
        Execute a full fetch run and return metrics.
        Called by the orchestrator.
        """
        started_at = datetime.utcnow()
        result = FetchResult(
            source_system=self.source_name,
            source_tier=self.source_tier,
            started_at=started_at,
        )

        try:
            count = 0
            for record in self.fetch():
                result.records_fetched += 1
                if record.entity_class is not None and record.canonical_name:
                    record.compute_hash()
                    result.records_parsed += 1
                    count += 1
                else:
                    result.records_skipped += 1

                if self.max_records_per_run and count >= self.max_records_per_run:
                    result.warnings.append(
                        f"Stopped at max_records_per_run={self.max_records_per_run}"
                    )
                    break

        except Exception as e:
            result.errors.append(str(e))
            self._logger.error(f"{self.source_name} fetch failed: {e}", exc_info=True)

        return result

    def _safe_get(self, data: Dict, *keys: str, default: Any = None) -> Any:
        """Safe nested dict lookup."""
        for key in keys:
            if not isinstance(data, dict):
                return default
            data = data.get(key, default)
        return data
