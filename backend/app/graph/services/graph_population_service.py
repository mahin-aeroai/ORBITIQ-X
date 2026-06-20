"""
ORBITIQ-X — Graph Population Service
======================================
Orchestrates the complete PostgreSQL → Neo4j sync pipeline.

Pipeline
────────
  1. Seed reference data (OrbitalRegimes, LaunchVehicles, LaunchSites, Agencies)
  2. Pull satellite catalog from PostgreSQL (SatelliteRepository.get_all)
  3. Upsert Satellite nodes + relationships (OPERATED_BY, LOCATED_IN_ORBIT, etc.)
  4. Pull conjunction events from PostgreSQL (ConjunctionRepository)
  5. Upsert ConjunctionEvent nodes + INVOLVED_IN_CONJUNCTION relationships
  6. Return GraphPopulationReport

What this does NOT touch
─────────────────────────
  - knowledge-graph/loaders/graph_loader.py  ← standalone ETL, not modified
  - graph_repository.py repositories         ← called from here, not rewritten
  - connection.py execute_batch()            ← called from repositories

Idempotency
────────────
  All Cypher uses MERGE — safe to run multiple times per day.
  Running this service twice with the same PostgreSQL state is a no-op.

Graceful degradation
────────────────────
  If Neo4j is unavailable, every method returns a partial report
  with status='skipped'. The application continues without graph features.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.graph.connection import is_available
from app.graph.repositories.graph_repository import (
    AgencyRepository,
    ConjunctionGraphRepository,
    LaunchSiteRepository,
    LaunchVehicleRepository,
    OrbitalRegimeRepository,
    SatelliteGraphRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class GraphPopulationReport:
    """Summary of one graph population run."""
    run_id:              str
    started_at:          datetime
    completed_at:        datetime | None = None
    status:              str = "running"

    # Counts
    regimes_seeded:      int = 0
    vehicles_seeded:     int = 0
    sites_seeded:        int = 0
    agencies_seeded:     int = 0
    satellites_synced:   int = 0
    sat_nodes_created:   int = 0
    conjunctions_synced: int = 0
    conj_nodes_created:  int = 0

    errors:              list[str] = field(default_factory=list)
    phases_completed:    list[str] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    def as_dict(self) -> dict:
        return {
            "run_id":              self.run_id,
            "status":              self.status,
            "started_at":          self.started_at.isoformat(),
            "completed_at":        self.completed_at.isoformat() if self.completed_at else None,
            "duration_s":          round(self.duration_s, 2),
            "regimes_seeded":      self.regimes_seeded,
            "vehicles_seeded":     self.vehicles_seeded,
            "sites_seeded":        self.sites_seeded,
            "agencies_seeded":     self.agencies_seeded,
            "satellites_synced":   self.satellites_synced,
            "sat_nodes_created":   self.sat_nodes_created,
            "conjunctions_synced": self.conjunctions_synced,
            "conj_nodes_created":  self.conj_nodes_created,
            "phases_completed":    self.phases_completed,
            "errors":              self.errors,
        }


class GraphPopulationService:
    """
    Orchestrates PostgreSQL → Neo4j graph population.

    Parameters
    ----------
    pg_session : AsyncSession
        PostgreSQL session for reading catalog + conjunction data.
    """

    def __init__(self, pg_session) -> None:
        self._session = pg_session
        self._regime_repo  = OrbitalRegimeRepository()
        self._vehicle_repo = LaunchVehicleRepository()
        self._site_repo    = LaunchSiteRepository()
        self._agency_repo  = AgencyRepository()
        self._sat_repo     = SatelliteGraphRepository()
        self._conj_repo    = ConjunctionGraphRepository()

    async def populate_all(
        self,
        run_id: str | None = None,
        max_satellites: int | None = None,
        max_conjunctions: int | None = None,
    ) -> GraphPopulationReport:
        """
        Run the full population pipeline.

        Parameters
        ----------
        run_id : str | None
        max_satellites : int | None
            Limit for testing (None = all).
        max_conjunctions : int | None
            Limit for testing (None = all).
        """
        import uuid
        rid = run_id or str(uuid.uuid4())[:8]
        report = GraphPopulationReport(
            run_id=rid,
            started_at=datetime.now(timezone.utc),
        )

        if not is_available():
            report.status = "skipped"
            report.completed_at = datetime.now(timezone.utc)
            logger.warning("graph_population_skipped — Neo4j not available")
            return report

        logger.info("graph_population_start run=%s", rid)

        try:
            await self._phase_seed_reference(report)
            await self._phase_sync_satellites(report, max_satellites)
            await self._phase_sync_conjunctions(report, max_conjunctions)
            report.status = "success" if not report.errors else "partial"

        except Exception as exc:
            logger.exception("graph_population_failed run=%s", rid)
            report.status = "failed"
            report.errors.append(str(exc))
        finally:
            report.completed_at = datetime.now(timezone.utc)

        logger.info(
            "graph_population_complete run=%s status=%s duration=%.1fs "
            "sats=%d conj=%d",
            rid, report.status, report.duration_s,
            report.satellites_synced, report.conjunctions_synced,
        )
        return report

    # ── Phase helpers ─────────────────────────────────────────

    async def _phase_seed_reference(self, report: GraphPopulationReport) -> None:
        """Seed static reference data: regimes, vehicles, sites, agencies."""
        try:
            report.regimes_seeded  = await self._regime_repo.seed()
            report.vehicles_seeded = await self._vehicle_repo.seed()
            report.sites_seeded    = await self._site_repo.seed()
            report.agencies_seeded = await self._agency_repo.seed()
            report.phases_completed.append("seed_reference")
            logger.info(
                "graph_seed_reference regimes=%d vehicles=%d sites=%d agencies=%d",
                report.regimes_seeded, report.vehicles_seeded,
                report.sites_seeded, report.agencies_seeded,
            )
        except Exception as exc:
            logger.error("graph_seed_reference_failed error=%s", exc)
            report.errors.append(f"seed_reference: {exc}")

    async def _phase_sync_satellites(
        self,
        report: GraphPopulationReport,
        max_objects: int | None,
    ) -> None:
        """Pull satellites from PostgreSQL and upsert to graph."""
        try:
            from app.db.repositories.satellite_repository import SatelliteRepository
            from sqlalchemy import select
            from app.db.models.satellites import Satellite

            sat_repo = SatelliteRepository(self._session)
            # Use count-based fetch to avoid loading 50K full ORM objects at once
            result = await self._session.execute(
                select(Satellite).limit(max_objects or 100_000)
            )
            rows = result.scalars().all()

            # Convert ORM rows to plain dicts for graph layer
            sat_dicts = []
            for sat in rows:
                sat_dicts.append({
                    "norad_id":        sat.norad_id,
                    "cospar_id":       sat.cospar_id,
                    "name":            sat.name,
                    "object_type":     sat.object_type,
                    "status":          sat.status,
                    "regime":          sat.regime,
                    "mission_type":    sat.mission_type,
                    "perigee_km":      sat.perigee_km,
                    "apogee_km":       sat.apogee_km,
                    "inclination_deg": sat.inclination_deg,
                    "period_minutes":  sat.period_minutes,
                    "mass_kg":         sat.mass_kg,
                    "launch_date":     sat.launch_date,
                    "launch_site":     sat.launch_site,
                    "launch_vehicle":  sat.launch_vehicle,
                    "constellation":   sat.constellation,
                    "country_code":    sat.country_code,
                    "operator_name":   sat.operator_name,
                    "tle_line1":       sat.tle_line1,
                    "tle_line2":       sat.tle_line2,
                    "tle_epoch":       sat.tle_epoch,
                    "tle_age_days":    sat.tle_age_days,
                })

            report.satellites_synced = len(sat_dicts)
            counters = await self._sat_repo.upsert_satellites(sat_dicts)
            report.sat_nodes_created = counters.get("nodes_created", 0)
            report.phases_completed.append("sync_satellites")
            logger.info(
                "graph_sync_satellites total=%d nodes_created=%d",
                report.satellites_synced, report.sat_nodes_created,
            )

        except Exception as exc:
            logger.error("graph_sync_satellites_failed error=%s", exc)
            report.errors.append(f"sync_satellites: {exc}")

    async def _phase_sync_conjunctions(
        self,
        report: GraphPopulationReport,
        max_objects: int | None,
    ) -> None:
        """Pull conjunction events from PostgreSQL and upsert to graph."""
        try:
            from sqlalchemy import select
            from app.db.models.conjunction_events import ConjunctionEvent

            result = await self._session.execute(
                select(ConjunctionEvent)
                .order_by(ConjunctionEvent.tca.desc())
                .limit(max_objects or 10_000)
            )
            rows = result.scalars().all()

            conj_dicts = [
                {
                    "conjunction_id":       c.conjunction_id,
                    "primary_norad":        c.primary_norad,
                    "primary_name":         c.primary_name,
                    "secondary_norad":      c.secondary_norad,
                    "secondary_name":       c.secondary_name,
                    "tca":                  c.tca,
                    "miss_distance_km":     c.miss_distance_km,
                    "relative_velocity_kms":c.relative_velocity_kms,
                    "collision_probability":c.collision_probability,
                    "risk_level":           c.risk_level,
                    "maneuver_required":    c.maneuver_required,
                    "resolved":             c.resolved,
                    "screening_org":        c.screening_org,
                }
                for c in rows
            ]

            report.conjunctions_synced = len(conj_dicts)
            if conj_dicts:
                counters = await self._conj_repo.upsert_conjunctions(conj_dicts)
                report.conj_nodes_created = counters.get("nodes_created", 0)
            report.phases_completed.append("sync_conjunctions")
            logger.info(
                "graph_sync_conjunctions total=%d nodes_created=%d",
                report.conjunctions_synced, report.conj_nodes_created,
            )

        except Exception as exc:
            logger.error("graph_sync_conjunctions_failed error=%s", exc)
            report.errors.append(f"sync_conjunctions: {exc}")
