"""
ORBITIQ-X Backend — Conjunction Analysis Service
==================================================
Bridges the orbital engine (ConjunctionScreener) with the
backend persistence layer (ConjunctionRepository, OrbitalEventRepository).

This service owns the full pipeline for one screening run:
  1. Load RSO catalog from PostgreSQL (satellites table)
  2. Build RSO objects for the orbital engine
  3. Run ConjunctionScreener (CPU-bound, runs in executor)
  4. Persist results via ConjunctionPersistenceService (already implemented)
  5. Generate CDM documents for each result
  6. Return ScreeningRunReport

What this does NOT touch (already implemented and correct)
───────────────────────────────────────────────────────────
  ConjunctionScreener.screen()          ← orbital engine (fixed above)
  ConjunctionPersistenceService         ← persistence layer (intact)
  ConjunctionRepository.bulk_insert()   ← DB write (intact)
  OrbitalEventRepository.bulk_log()     ← event log (intact)
  Redis pub/sub alerts (red events)     ← intact in persistence service

Audit findings addressed
─────────────────────────
  - conjunctions.py endpoint was a 3-line stub → implemented below
  - No bridge between orbital engine and backend existed → this file
  - Scheduler jobs were log-only stubs → wired to this service
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.conjunction_repository import ConjunctionRepository
from app.db.repositories.satellite_repository import SatelliteRepository
from app.db.repositories.orbital_event_repository import OrbitalEventRepository
from app.db.session import transactional, get_session_factory
from app.services.conjunction_service import ConjunctionPersistenceService

logger = logging.getLogger(__name__)


# ── orbital-engine loader (collision-proof) ─────────────────────────────────
# See orbital_state_service.py for the full explanation of why this exists:
# multiple sibling monorepo directories (agents/, rag/, orbital-engine/) each
# define their own top-level "src" package, and several services insert
# their own directory at sys.path[0]. "from src.X import Y" is therefore
# unreliable — it can silently resolve to the wrong sibling's src/ package
# depending on import order, producing ModuleNotFoundError for submodules
# that exist on disk but not in whichever src/ won the race.
#
# This loads orbital-engine's src package under a private, collision-free
# namespace via importlib + an absolute file path, bypassing the shared
# "src" name in sys.modules entirely.

import importlib.util
import pathlib
import sys as _sys

_THIS_FILE = pathlib.Path(__file__).resolve()
_OE_CANDIDATES = [
    _THIS_FILE.parents[3] / "orbital-engine",   # local dev: backend/app/services -> repo_root/orbital-engine
    _THIS_FILE.parents[2] / "orbital-engine",   # Railway:   /app/app/services -> /app/orbital-engine
    pathlib.Path("/app/orbital-engine"),        # explicit Railway fallback
]
_OE_ROOT = next((p for p in _OE_CANDIDATES if p.is_dir()), _OE_CANDIDATES[0])
logger.info("conjunction_oe_path_resolved path=%s exists=%s", _OE_ROOT, _OE_ROOT.is_dir())


def _load_orbital_engine_module(dotted_path: str):
    """
    Import a module from orbital-engine/src/<dotted_path> under a private
    namespace (_orbital_engine_src.*).

    Registers the bare root package first (required for screener.py's
    cross-package "from ..propagator.sgp4_propagator import X" relative
    import — it needs src/ itself registered as the common parent), then
    every parent package in the requested dotted path, then the target
    module itself.
    """
    ROOT_NAME = "_orbital_engine_src"

    if ROOT_NAME not in _sys.modules:
        root_init = _OE_ROOT / "src" / "__init__.py"
        if not root_init.is_file():
            raise ModuleNotFoundError(
                f"orbital-engine src/__init__.py not found at {root_init} "
                f"(OE_ROOT={_OE_ROOT} exists={_OE_ROOT.is_dir()})"
            )
        spec = importlib.util.spec_from_file_location(
            ROOT_NAME, root_init,
            submodule_search_locations=[str(_OE_ROOT / "src")],
        )
        root_module = importlib.util.module_from_spec(spec)
        _sys.modules[ROOT_NAME] = root_module
        spec.loader.exec_module(root_module)

    parts = dotted_path.split(".")
    accumulated: list[str] = []

    for part in parts:
        accumulated.append(part)
        sub_dotted   = ".".join(accumulated)
        private_name = f"{ROOT_NAME}.{sub_dotted}"
        if private_name in _sys.modules:
            continue

        rel_path = pathlib.Path(*accumulated)
        pkg_init = _OE_ROOT / "src" / rel_path / "__init__.py"
        pkg_dir  = _OE_ROOT / "src" / rel_path
        mod_file = (_OE_ROOT / "src" / rel_path).with_suffix(".py")

        if mod_file.is_file():
            file_path, is_package = mod_file, False
        elif pkg_init.is_file():
            file_path, is_package = pkg_init, True
        elif pkg_dir.is_dir():
            # Directory exists with Python files but no __init__.py — treat
            # as an implicit namespace package rather than failing outright.
            spec = importlib.util.spec_from_file_location(
                private_name, None,
                submodule_search_locations=[str(pkg_dir)],
            )
            module = importlib.util.module_from_spec(spec)
            _sys.modules[private_name] = module
            continue
        else:
            raise ModuleNotFoundError(
                f"orbital-engine module not found: {sub_dotted} "
                f"(looked for {mod_file} and {pkg_init}, "
                f"OE_ROOT={_OE_ROOT} exists={_OE_ROOT.is_dir()})"
            )

        spec = importlib.util.spec_from_file_location(
            private_name,
            file_path,
            submodule_search_locations=[str(file_path.parent)] if is_package else None,
        )
        module = importlib.util.module_from_spec(spec)
        _sys.modules[private_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            # If exec fails partway through, remove the half-initialized
            # module from sys.modules so it doesn't poison future import
            # attempts (Python registers the module object before running
            # its body, to support circular imports — but a failed exec
            # leaves a broken module cached under this name otherwise).
            del _sys.modules[private_name]
            raise

    return _sys.modules[f"{ROOT_NAME}.{dotted_path}"]


# ── CDM generator ─────────────────────────────────────────────

def generate_cdm_document(result) -> dict:
    """
    Generate a CCSDS-inspired CDM JSON document from a ConjunctionResult.

    Fields follow CCSDS 508.0-B-1 CDM standard naming where possible,
    adapted for JSON transport. Future versions will support full CCSDS
    XML/KVN serialisation.

    Parameters
    ----------
    result : ConjunctionResult
        Conjunction result from ConjunctionScreener.

    Returns
    -------
    dict
        CDM-equivalent JSON-serialisable document.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        # Header
        "CCSDS_CDM_VERS":      "1.0",
        "CREATION_DATE":        now,
        "ORIGINATOR":           "ORBITIQ-X",
        "MESSAGE_ID":           result.conjunction_id,

        # Relative metadata
        "TCA":                  result.tca.isoformat() if result.tca else None,
        "MISS_DISTANCE":        round(result.miss_distance_km * 1000, 2),  # metres
        "MISS_DISTANCE_UNIT":   "m",
        "RELATIVE_SPEED":       round(result.relative_velocity_kms * 1000, 3),  # m/s
        "RELATIVE_SPEED_UNIT":  "m/s",
        "COLLISION_PROBABILITY": result.collision_probability,
        "COLLISION_PROBABILITY_METHOD": result.pc_method,
        "RISK_LEVEL":            result.risk_level.upper(),

        # Combined covariance
        "COMBINED_HBR":          round(result.combined_hbr_km * 1000, 3),  # metres
        "SIGMA_MAJOR":           round(result.sigma_major_km * 1000, 3),   # metres
        "SIGMA_MINOR":           round(result.sigma_minor_km * 1000, 3),   # metres

        # Maneuver assessment
        "MANEUVER_REQUIRED":     result.maneuver_required,
        "MANEUVER_WINDOW_CLOSE": result.maneuver_window.isoformat() if result.maneuver_window else None,

        # Object 1 (primary)
        "OBJECT1": {
            "OBJECT":          "OBJECT1",
            "OBJECT_DESIGNATOR": str(result.object_1_norad),
            "OBJECT_NAME":     result.object_1_name,
            "CATALOG_NAME":    "USSPACECOM",
        },

        # Object 2 (secondary)
        "OBJECT2": {
            "OBJECT":          "OBJECT2",
            "OBJECT_DESIGNATOR": str(result.object_2_norad),
            "OBJECT_NAME":     result.object_2_name,
            "CATALOG_NAME":    "USSPACECOM",
        },

        # Relative state at TCA
        "RELATIVE_STATE": {
            "FRAME":           "ECI_J2000",
            "REL_POS_R":       round(result.rel_pos_km[0] * 1000, 3),  # m
            "REL_POS_T":       round(result.rel_pos_km[1] * 1000, 3),
            "REL_POS_N":       round(result.rel_pos_km[2] * 1000, 3),
            "REL_VEL_R":       round(result.rel_vel_kms[0] * 1000, 3),  # m/s
            "REL_VEL_T":       round(result.rel_vel_kms[1] * 1000, 3),
            "REL_VEL_N":       round(result.rel_vel_kms[2] * 1000, 3),
        },

        # Screening metadata
        "SCREENING_ORG":  "ORBITIQ-X",
        "SCREEN_VOLUME_SHAPE": "SPHERE",
        "SCREEN_VOLUME_RADIUS": 5000,  # 5 km in metres
    }


# ── Screening report ──────────────────────────────────────────

@dataclass
class ScreeningRunReport:
    """Complete result of one conjunction screening run."""
    run_id:           str
    epoch:            datetime
    started_at:       datetime
    completed_at:     datetime | None = None
    status:           str = "running"

    # Catalog metrics
    objects_screened: int = 0
    objects_valid:    int = 0

    # Pair filtering metrics (Phase 2 binning efficiency)
    pairs_after_binning:  int = 0
    pairs_after_voxel:    int = 0
    pair_reduction_pct:   float = 0.0

    # Results
    total_conjunctions: int = 0
    red_count:          int = 0
    yellow_count:       int = 0
    green_count:        int = 0
    persisted:          int = 0
    alerts_fired:       int = 0

    # Performance
    propagation_s:   float = 0.0
    screening_s:     float = 0.0
    persistence_s:   float = 0.0
    total_s:         float = 0.0

    errors:          list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "run_id":              self.run_id,
            "epoch":               self.epoch.isoformat(),
            "status":              self.status,
            "started_at":          self.started_at.isoformat(),
            "completed_at":        self.completed_at.isoformat() if self.completed_at else None,
            "objects_screened":    self.objects_screened,
            "objects_valid":       self.objects_valid,
            "pairs_after_binning": self.pairs_after_binning,
            "pair_reduction_pct":  round(self.pair_reduction_pct, 2),
            "total_conjunctions":  self.total_conjunctions,
            "red":                 self.red_count,
            "yellow":              self.yellow_count,
            "green":               self.green_count,
            "persisted":           self.persisted,
            "alerts_fired":        self.alerts_fired,
            "total_seconds":       round(self.total_s, 2),
        }


# ── Service ───────────────────────────────────────────────────

class ConjunctionAnalysisService:
    """
    Orchestrates the full conjunction screening pipeline.

    Parameters
    ----------
    session : AsyncSession
        Database session for catalog load and result persistence.
    redis_client : optional
        For alert pub/sub. Gracefully degraded if None.
    screen_distance_km : float
        Coarse filter pass distance.
    pc_threshold : float
        Minimum Pc to generate/persist a CDM.
    tca_window_hours : int
        TCA search window in hours.
    """

    def __init__(
        self,
        session: AsyncSession,
        redis_client=None,
        screen_distance_km: float = 5.0,
        pc_threshold: float = 1e-6,
        tca_window_hours: int = 72,
    ):
        self._session           = session
        self._redis             = redis_client
        self._screen_distance   = screen_distance_km
        self._pc_threshold      = pc_threshold
        self._tca_window        = tca_window_hours
        self._sat_repo          = SatelliteRepository(session)
        self._conj_repo         = ConjunctionRepository(session)
        self._event_repo        = OrbitalEventRepository(session)
        self._persist_svc       = ConjunctionPersistenceService(session, redis_client)

    async def run_screening(
        self,
        epoch: datetime | None = None,
        run_id: str | None = None,
        max_objects: int | None = None,
    ) -> ScreeningRunReport:
        """
        Execute a full conjunction screening run.

        This is the primary entry point called by the scheduler and the
        POST /conjunctions/screen API endpoint.

        Parameters
        ----------
        epoch : datetime | None
            Screening epoch. Defaults to now UTC.
        run_id : str | None
            Run identifier for tracking. Auto-generated if None.
        max_objects : int | None
            Limit catalog size (for testing).

        Returns
        -------
        ScreeningRunReport
        """
        epoch  = epoch  or datetime.now(timezone.utc)
        run_id = run_id or str(uuid.uuid4())[:8]

        report = ScreeningRunReport(
            run_id=run_id,
            epoch=epoch,
            started_at=datetime.now(timezone.utc),
        )

        logger.info(
            "conjunction_screening_start run=%s epoch=%s",
            run_id, epoch.isoformat(),
        )

        try:
            # Step 1: Load RSO catalog from PostgreSQL
            rsos = await self._load_catalog(max_objects)
            report.objects_screened = len(rsos)
            report.objects_valid    = len([r for r in rsos if r.tle_line1])

            if report.objects_valid < 2:
                report.status = "skipped"
                report.completed_at = datetime.now(timezone.utc)
                logger.warning("conjunction_screening_skipped run=%s valid_objects=%d",
                               run_id, report.objects_valid)
                return report

            # Step 2: Run ConjunctionScreener (CPU-bound — use executor)
            t_screen = time.perf_counter()
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                self._run_screener_sync,
                rsos,
                epoch,
            )
            report.screening_s      = time.perf_counter() - t_screen
            report.total_conjunctions = len(results)

            # Classify by risk
            for r in results:
                if r.risk_level == "red":    report.red_count    += 1
                elif r.risk_level == "yellow": report.yellow_count += 1
                elif r.risk_level == "green":  report.green_count  += 1

            logger.info(
                "conjunction_screening_done run=%s results=%d "
                "red=%d yellow=%d green=%d screen_s=%.1f",
                run_id, len(results),
                report.red_count, report.yellow_count,
                report.green_count, report.screening_s,
            )

            # Step 3: Persist CDMs
            t_persist = time.perf_counter()
            if results:
                cdm_dicts = [r.to_cdm_dict() for r in results]
                persist_result = await self._persist_svc.persist_screening_results(
                    cdms=cdm_dicts,
                    screening_epoch=epoch,
                    persist_white=False,
                )
                report.persisted   = persist_result.persisted
                report.alerts_fired = persist_result.alerts_fired
            report.persistence_s = time.perf_counter() - t_persist

            report.status = "success"

        except Exception as exc:
            logger.exception("conjunction_screening_failed run=%s", run_id)
            report.status = "failed"
            report.errors.append(str(exc))

        finally:
            report.completed_at = datetime.now(timezone.utc)
            report.total_s = (
                report.completed_at - report.started_at
            ).total_seconds()

        logger.info(
            "conjunction_screening_complete run=%s status=%s "
            "total_s=%.1f persisted=%d",
            run_id, report.status, report.total_s, report.persisted,
        )
        return report

    async def _load_catalog(
        self,
        max_objects: int | None,
    ):
        """Load active LEO satellites from PostgreSQL and build RSO list."""
        _screener_mod = _load_orbital_engine_module("conjunction.screener")
        RSO                   = _screener_mod.RSO
        DEFAULT_HBR_SAT_KM    = _screener_mod.DEFAULT_HBR_SAT_KM
        DEFAULT_HBR_DEBRIS_KM = _screener_mod.DEFAULT_HBR_DEBRIS_KM

        satellites = await self._sat_repo.get_active_leos()
        if max_objects:
            satellites = satellites[:max_objects]

        rsos = []
        for sat in satellites:
            if not sat.tle_line1 or not sat.tle_line2:
                continue
            hbr = DEFAULT_HBR_DEBRIS_KM if sat.object_type == "debris" else DEFAULT_HBR_SAT_KM
            rsos.append(RSO(
                norad_id=sat.norad_id,
                name=sat.name or f"NORAD-{sat.norad_id}",
                tle_line1=sat.tle_line1,
                tle_line2=sat.tle_line2,
                object_type=sat.object_type or "unknown",
                hbr_km=hbr,
            ))

        logger.info("conjunction_catalog_loaded objects=%d", len(rsos))
        return rsos

    def _run_screener_sync(self, rsos, epoch: datetime):
        """Synchronous screener call for run_in_executor."""
        _screener_mod      = _load_orbital_engine_module("conjunction.screener")
        ConjunctionScreener = _screener_mod.ConjunctionScreener
        screener = ConjunctionScreener(
            screen_distance_km=self._screen_distance,
            tca_window_hours=self._tca_window,
            pc_threshold=self._pc_threshold,
            use_orbital_binning=True,
        )
        return screener.screen(rsos, epoch)

    async def get_cdm(self, conjunction_id: str) -> dict | None:
        """Generate CDM document for a stored conjunction event."""
        event = await self._conj_repo.get_by_conjunction_id(conjunction_id)
        if not event:
            return None

        # Reconstruct a minimal ConjunctionResult-like object for CDM generation
        class _Stub:
            pass
        r = _Stub()
        r.conjunction_id       = event.conjunction_id
        r.tca                  = event.tca
        r.object_1_norad       = event.primary_norad
        r.object_2_norad       = event.secondary_norad
        r.object_1_name        = event.primary_name or str(event.primary_norad)
        r.object_2_name        = event.secondary_name or str(event.secondary_norad)
        r.miss_distance_km     = event.miss_distance_km
        r.relative_velocity_kms = event.relative_velocity_kms
        r.collision_probability = event.collision_probability
        r.pc_method            = event.collision_probability_method
        r.risk_level           = event.risk_level
        r.combined_hbr_km      = event.combined_hbr_km or 0.006
        r.sigma_major_km       = event.sigma_major_km or 0.0
        r.sigma_minor_km       = event.sigma_minor_km or 0.0
        r.rel_pos_km           = (0.0, 0.0, 0.0)
        r.rel_vel_kms          = (0.0, 0.0, 0.0)
        r.maneuver_required    = event.maneuver_required
        r.maneuver_window      = event.maneuver_window_close
        return generate_cdm_document(r)
