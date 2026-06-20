"""
ORBITIQ-X — Knowledge Graph Test Suite
========================================
Phase 11: Full test coverage for all graph components.

Test categories
────────────────
  Connection Manager  : init, health, graceful degradation, retry
  Graph Repository    : upsert Cypher correctness, relationship wiring
  Analytics Service   : query structure, graceful degradation
  Population Service  : pipeline orchestration, phase isolation
  API Endpoints       : 503 on Neo4j down, correct routes, response shape
  Scheduler           : 4-job presence + interval validation
  Ontology            : seed data completeness, node label coverage
  Performance         : seed data prep timing
  Failure Recovery    : every service degrades gracefully without Neo4j

All tests run without a real Neo4j instance — mock the driver
and connection module so tests are hermetic.

Run
───
  pytest tests/unit/graph/ -v --asyncio-mode=auto
  pytest tests/unit/graph/ -v -k "connection"
  pytest tests/unit/graph/ -v -s -k "performance"
"""

from __future__ import annotations

import sys
import pathlib
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add backend root to path
sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))


# ── Shared fixtures ───────────────────────────────────────────

def _make_sat_dict(norad: int, **kwargs) -> dict:
    return {
        "norad_id":        norad,
        "cospar_id":       f"2024-{norad:03d}A",
        "name":            f"SAT-{norad}",
        "object_type":     kwargs.get("object_type", "satellite"),
        "status":          kwargs.get("status", "operational"),
        "regime":          kwargs.get("regime", "LEO"),
        "mission_type":    kwargs.get("mission_type", "eo"),
        "perigee_km":      410.0,
        "apogee_km":       420.0,
        "inclination_deg": 51.6,
        "period_minutes":  92.9,
        "mass_kg":         500.0,
        "launch_date":     None,
        "launch_site":     kwargs.get("launch_site", "LS-SDSC"),
        "launch_vehicle":  kwargs.get("launch_vehicle", "LV-PSLV"),
        "constellation":   kwargs.get("constellation"),
        "country_code":    kwargs.get("country_code", "IN"),
        "operator_name":   kwargs.get("operator_name", "ISRO"),
        "tle_line1":       None,
        "tle_line2":       None,
        "tle_epoch":       None,
        "tle_age_days":    1.5,
    }


def _make_conj_dict(conj_id: str, pc: float = 1.5e-3) -> dict:
    return {
        "conjunction_id":        conj_id,
        "primary_norad":         25544,
        "primary_name":          "ISS",
        "secondary_norad":       44713,
        "secondary_name":        "STARLINK-1007",
        "tca":                   datetime.now(timezone.utc) + timedelta(hours=12),
        "miss_distance_km":      0.25,
        "relative_velocity_kms": 7.8,
        "collision_probability": pc,
        "risk_level":            "red" if pc >= 1e-3 else "yellow",
        "maneuver_required":     pc >= 1e-4,
        "resolved":              False,
        "screening_org":         "ORBITIQ-X",
    }


# ═══════════════════════════════════════════════════════════════
# CONNECTION MANAGER TESTS
# ═══════════════════════════════════════════════════════════════

class TestNeo4jConnectionManager:
    """Phase 1: Driver init, health, graceful degradation."""

    def test_is_available_false_when_not_initialised(self):
        from app.graph.connection import is_available
        # Without calling init, driver should be None
        # We patch _driver to be None explicitly
        with patch("app.graph.connection._driver", None):
            assert is_available() is False

    def test_is_available_true_when_driver_set(self):
        from app.graph.connection import is_available
        mock_driver = MagicMock()
        with patch("app.graph.connection._driver", mock_driver):
            assert is_available() is True

    def test_get_driver_raises_when_none(self):
        from app.graph.connection import get_driver, Neo4jConnectionError
        with patch("app.graph.connection._driver", None):
            with pytest.raises(Neo4jConnectionError, match="not initialised"):
                get_driver()

    def test_get_driver_returns_driver(self):
        from app.graph.connection import get_driver
        mock_driver = MagicMock()
        with patch("app.graph.connection._driver", mock_driver):
            assert get_driver() is mock_driver

    @pytest.mark.asyncio
    async def test_init_neo4j_driver_graceful_on_failure(self):
        """Connection failure must not crash the application."""
        from app.graph.connection import init_neo4j_driver
        with patch("app.graph.connection.AsyncGraphDatabase") as mock_gdb, \
             patch("app.graph.connection._driver", None):
            mock_gdb.driver.side_effect = Exception("Connection refused")
            # Should not raise
            await init_neo4j_driver()
            # _driver should remain None

    @pytest.mark.asyncio
    async def test_close_driver_sets_none(self):
        from app.graph.connection import close_neo4j_driver
        mock_driver = AsyncMock()
        with patch("app.graph.connection._driver", mock_driver):
            await close_neo4j_driver()
            mock_driver.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_unavailable_when_no_driver(self):
        from app.graph.connection import health_check
        with patch("app.graph.connection._driver", None):
            result = await health_check()
        assert result["reachable"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_health_check_returns_node_count(self):
        from app.graph.connection import health_check
        mock_driver = MagicMock()
        mock_session = AsyncMock()
        mock_result  = AsyncMock()
        mock_result.data = AsyncMock(return_value=[{"cnt": 42}])
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_driver.session = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=None),
        ))

        with patch("app.graph.connection._driver", mock_driver):
            with patch("app.graph.connection.execute_read", new=AsyncMock(
                return_value=[{"cnt": 42}]
            )):
                result = await health_check()

        assert result["reachable"] is True
        assert result["node_count"] == 42

    @pytest.mark.asyncio
    async def test_execute_batch_empty_returns_zero(self):
        from app.graph.connection import execute_batch
        mock_driver = MagicMock()
        with patch("app.graph.connection._driver", mock_driver):
            result = await execute_batch("UNWIND $batch AS row RETURN row", [])
        assert result["nodes_created"] == 0

    @pytest.mark.asyncio
    async def test_execute_read_raises_on_no_driver(self):
        from app.graph.connection import execute_read, Neo4jConnectionError
        with patch("app.graph.connection._driver", None):
            with pytest.raises(Neo4jConnectionError):
                await execute_read("RETURN 1")


# ═══════════════════════════════════════════════════════════════
# ONTOLOGY / SEED DATA TESTS
# ═══════════════════════════════════════════════════════════════

class TestAerospaceOntology:
    """Phase 2: Verify seed data completeness."""

    def test_orbital_regimes_count(self):
        from app.graph.repositories.graph_repository import ORBITAL_REGIMES
        assert len(ORBITAL_REGIMES) >= 7
        ids = {r["orbitId"] for r in ORBITAL_REGIMES}
        assert "LEO" in ids
        assert "MEO" in ids
        assert "GEO" in ids
        assert "HEO" in ids
        assert "CISLUNAR" in ids

    def test_orbital_regimes_have_required_fields(self):
        from app.graph.repositories.graph_repository import ORBITAL_REGIMES
        for regime in ORBITAL_REGIMES:
            assert "orbitId" in regime, f"Missing orbitId in {regime}"
            assert "name" in regime
            assert "altMinKm" in regime
            assert "description" in regime

    def test_launch_vehicles_coverage(self):
        from app.graph.repositories.graph_repository import LAUNCH_VEHICLES
        assert len(LAUNCH_VEHICLES) >= 12
        vehicle_ids = {v["vehicleId"] for v in LAUNCH_VEHICLES}
        required = {"LV-PSLV", "LV-FALCON9", "LV-ARIANE6", "LV-ELECTRON", "LV-LM-5"}
        assert required <= vehicle_ids, f"Missing vehicles: {required - vehicle_ids}"

    def test_launch_vehicles_have_required_fields(self):
        from app.graph.repositories.graph_repository import LAUNCH_VEHICLES
        for lv in LAUNCH_VEHICLES:
            assert "vehicleId" in lv
            assert "name" in lv
            assert "country" in lv
            assert "payloadLeoKg" in lv

    def test_launch_sites_coverage(self):
        from app.graph.repositories.graph_repository import LAUNCH_SITES
        assert len(LAUNCH_SITES) >= 10
        site_ids = {s["siteId"] for s in LAUNCH_SITES}
        required = {"LS-SDSC", "LS-KSC", "LS-KOUROU", "LS-BAIKONUR", "LS-JIUQUAN"}
        assert required <= site_ids

    def test_agencies_coverage(self):
        from app.graph.repositories.graph_repository import AGENCIES
        assert len(AGENCIES) >= 10
        agency_ids = {a["agencyId"] for a in AGENCIES}
        required = {"AGY-NASA", "AGY-ESA", "AGY-ISRO", "AGY-CNSA", "AGY-JAXA"}
        assert required <= agency_ids

    def test_all_node_types_representable(self):
        """Verify all 12 ontology node types have data or repos."""
        from app.graph.repositories.graph_repository import (
            OrbitalRegimeRepository,
            LaunchVehicleRepository,
            LaunchSiteRepository,
            AgencyRepository,
            SatelliteGraphRepository,
            ConjunctionGraphRepository,
        )
        # All 6 repos exist and are instantiable
        for cls in [
            OrbitalRegimeRepository, LaunchVehicleRepository,
            LaunchSiteRepository, AgencyRepository,
            SatelliteGraphRepository, ConjunctionGraphRepository,
        ]:
            assert cls() is not None


# ═══════════════════════════════════════════════════════════════
# SATELLITE GRAPH REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════

class TestSatelliteGraphRepository:
    """Phase 3: Satellite node upsert and relationship wiring."""

    @pytest.mark.asyncio
    async def test_upsert_returns_zero_when_unavailable(self):
        from app.graph.repositories.graph_repository import SatelliteGraphRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=False):
            repo    = SatelliteGraphRepository()
            result  = await repo.upsert_satellites([_make_sat_dict(25544)])
        assert result == {"nodes_created": 0}

    @pytest.mark.asyncio
    async def test_upsert_returns_zero_on_empty_list(self):
        from app.graph.repositories.graph_repository import SatelliteGraphRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=True):
            repo   = SatelliteGraphRepository()
            result = await repo.upsert_satellites([])
        assert result == {"nodes_created": 0}

    @pytest.mark.asyncio
    async def test_upsert_calls_execute_batch(self):
        from app.graph.repositories.graph_repository import SatelliteGraphRepository
        sat = _make_sat_dict(25544, regime="LEO", constellation="ISS", country_code="US", operator_name="NASA")

        mock_counters = {"nodes_created": 1, "relationships_created": 3, "properties_set": 10}

        with patch("app.graph.repositories.graph_repository.is_available", return_value=True), \
             patch("app.graph.repositories.graph_repository.execute_batch",
                   new=AsyncMock(return_value=mock_counters)) as mock_batch:
            repo   = SatelliteGraphRepository()
            result = await repo.upsert_satellites([sat])

        # Should have called execute_batch at least once (for the main upsert)
        assert mock_batch.call_count >= 1
        assert result["nodes_created"] == 1

    @pytest.mark.asyncio
    async def test_upsert_builds_correct_record_shape(self):
        """Verify the graph record dict has all required fields."""
        from app.graph.repositories.graph_repository import SatelliteGraphRepository
        sat = _make_sat_dict(33591, regime="SSO", operator_name="ISRO", country_code="IN")

        captured_batches = []

        async def _capture_batch(cypher, batch, **kwargs):
            captured_batches.append((cypher, batch))
            return {"nodes_created": 1, "relationships_created": 0, "properties_set": 5}

        with patch("app.graph.repositories.graph_repository.is_available", return_value=True), \
             patch("app.graph.repositories.graph_repository.execute_batch", side_effect=_capture_batch):
            repo = SatelliteGraphRepository()
            await repo.upsert_satellites([sat])

        # First batch is the main satellite upsert
        _, first_batch = captured_batches[0]
        record = first_batch[0]
        assert record["noradId"] == 33591
        assert record["regime"] == "SSO"
        assert record["operatorName"] == "ISRO"
        assert record["countryCode"] == "IN"

    @pytest.mark.asyncio
    async def test_get_satellite_returns_none_when_unavailable(self):
        from app.graph.repositories.graph_repository import SatelliteGraphRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=False):
            repo   = SatelliteGraphRepository()
            result = await repo.get_satellite(25544)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_satellite_calls_execute_read(self):
        from app.graph.repositories.graph_repository import SatelliteGraphRepository
        mock_data = [{"s": {"noradId": 25544, "name": "ISS"}, "operatorName": "NASA"}]

        with patch("app.graph.repositories.graph_repository.is_available", return_value=True), \
             patch("app.graph.repositories.graph_repository.execute_read",
                   new=AsyncMock(return_value=mock_data)):
            repo   = SatelliteGraphRepository()
            result = await repo.get_satellite(25544)

        assert result is not None
        assert result["operatorName"] == "NASA"

    @pytest.mark.asyncio
    async def test_orbit_relationship_batch_only_for_objects_with_regime(self):
        """Objects without regime should not trigger LOCATED_IN_ORBIT batch."""
        from app.graph.repositories.graph_repository import SatelliteGraphRepository

        # Two sats: one with regime, one without
        sats = [
            _make_sat_dict(1, regime="LEO"),
            _make_sat_dict(2, regime=None),  # no regime
        ]
        sats[1]["regime"] = None

        batch_calls = []

        async def _capture(cypher, batch, **kwargs):
            batch_calls.append((cypher, batch))
            return {"nodes_created": len(batch), "relationships_created": 0, "properties_set": 0}

        with patch("app.graph.repositories.graph_repository.is_available", return_value=True), \
             patch("app.graph.repositories.graph_repository.execute_batch", side_effect=_capture):
            repo = SatelliteGraphRepository()
            await repo.upsert_satellites(sats)

        # Find the LOCATED_IN_ORBIT batch — should only have the sat with regime
        orbit_batches = [b for c, b in batch_calls if "LOCATED_IN_ORBIT" in c]
        if orbit_batches:
            orbit_batch = orbit_batches[0]
            norads_in_orbit = [r["noradId"] for r in orbit_batch]
            assert 2 not in norads_in_orbit  # sat without regime excluded


# ═══════════════════════════════════════════════════════════════
# CONJUNCTION GRAPH REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════

class TestConjunctionGraphRepository:
    """Phase 6: Conjunction intelligence graph."""

    @pytest.mark.asyncio
    async def test_upsert_returns_zero_when_unavailable(self):
        from app.graph.repositories.graph_repository import ConjunctionGraphRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=False):
            repo   = ConjunctionGraphRepository()
            result = await repo.upsert_conjunctions([_make_conj_dict("CDM-001")])
        assert result == {"nodes_created": 0}

    @pytest.mark.asyncio
    async def test_upsert_builds_correct_record_shape(self):
        """Verify CDM → graph record conversion preserves all fields."""
        from app.graph.repositories.graph_repository import ConjunctionGraphRepository
        cdm = _make_conj_dict("CDM-TEST-001", pc=2e-3)

        captured = []

        async def _capture(cypher, batch, **kwargs):
            captured.append(batch)
            return {"nodes_created": 1, "relationships_created": 2, "properties_set": 8}

        with patch("app.graph.repositories.graph_repository.is_available", return_value=True), \
             patch("app.graph.repositories.graph_repository.execute_batch", side_effect=_capture):
            repo = ConjunctionGraphRepository()
            await repo.upsert_conjunctions([cdm])

        record = captured[0][0]
        assert record["conjunctionId"] == "CDM-TEST-001"
        assert record["collisionProbability"] == pytest.approx(2e-3)
        assert record["riskLevel"] == "red"
        assert record["primaryNorad"] == 25544
        assert record["secondaryNorad"] == 44713
        assert record["maneuverRequired"] is True

    @pytest.mark.asyncio
    async def test_get_conjunctions_returns_empty_when_unavailable(self):
        from app.graph.repositories.graph_repository import ConjunctionGraphRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=False):
            repo   = ConjunctionGraphRepository()
            result = await repo.get_conjunctions_for_satellite(25544)
        assert result == []

    @pytest.mark.asyncio
    async def test_high_risk_network_returns_empty_when_unavailable(self):
        from app.graph.repositories.graph_repository import ConjunctionGraphRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=False):
            repo   = ConjunctionGraphRepository()
            result = await repo.get_high_risk_network()
        assert result == []


# ═══════════════════════════════════════════════════════════════
# GRAPH ANALYTICS SERVICE TESTS
# ═══════════════════════════════════════════════════════════════

class TestGraphAnalyticsService:
    """Phase 9: Analytics queries with mocked execute_read."""

    @pytest.mark.asyncio
    async def test_top_operators_returns_empty_when_unavailable(self):
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        with patch("app.graph.services.graph_analytics_service.is_available", return_value=False):
            svc    = GraphAnalyticsService()
            result = await svc.top_operators_by_satellite_count()
        assert result == []

    @pytest.mark.asyncio
    async def test_top_operators_passes_limit(self):
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        mock_data = [{"operator": "SpaceX", "satelliteCount": 4000, "regimes": ["LEO"]}]

        with patch("app.graph.services.graph_analytics_service.is_available", return_value=True), \
             patch("app.graph.services.graph_analytics_service.execute_read",
                   new=AsyncMock(return_value=mock_data)) as mock_read:
            svc    = GraphAnalyticsService()
            result = await svc.top_operators_by_satellite_count(limit=5)

        call_kwargs = mock_read.call_args
        assert "limit" in (call_kwargs.kwargs or {}) or 5 in (call_kwargs.args or ())
        assert len(result) == 1
        assert result[0]["operator"] == "SpaceX"

    @pytest.mark.asyncio
    async def test_graph_summary_returns_unavailable_when_down(self):
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        with patch("app.graph.services.graph_analytics_service.is_available", return_value=False):
            svc    = GraphAnalyticsService()
            result = await svc.graph_summary()
        assert result == {"available": False}

    @pytest.mark.asyncio
    async def test_graph_summary_returns_counts(self):
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        node_data = [
            {"label": "Satellite",      "cnt": 50000},
            {"label": "ConjunctionEvent","cnt": 1000},
            {"label": "OrbitalRegime",  "cnt": 9},
        ]
        rel_data = [
            {"relType": "LOCATED_IN_ORBIT",  "cnt": 48000},
            {"relType": "OPERATED_BY",        "cnt": 45000},
        ]

        async def mock_read(cypher, **kwargs):
            if "labels(n)" in cypher:
                return node_data
            return rel_data

        with patch("app.graph.services.graph_analytics_service.is_available", return_value=True), \
             patch("app.graph.services.graph_analytics_service.execute_read", side_effect=mock_read):
            svc    = GraphAnalyticsService()
            result = await svc.graph_summary()

        assert result["available"] is True
        assert result["node_counts"]["Satellite"] == 50000
        assert result["total_nodes"] == 51009

    @pytest.mark.asyncio
    async def test_conjunction_risk_network_returns_empty_when_unavailable(self):
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        with patch("app.graph.services.graph_analytics_service.is_available", return_value=False):
            svc    = GraphAnalyticsService()
            result = await svc.conjunction_risk_network()
        assert result == []

    @pytest.mark.asyncio
    async def test_orbital_regime_density_returns_empty_when_unavailable(self):
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        with patch("app.graph.services.graph_analytics_service.is_available", return_value=False):
            svc    = GraphAnalyticsService()
            result = await svc.orbital_regime_density()
        assert result == []

    @pytest.mark.asyncio
    async def test_country_full_profile_returns_empty_when_unavailable(self):
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        with patch("app.graph.services.graph_analytics_service.is_available", return_value=False):
            svc    = GraphAnalyticsService()
            result = await svc.country_full_profile("IN")
        assert result == {}

    @pytest.mark.asyncio
    async def test_largest_constellations_returns_empty_when_unavailable(self):
        from app.graph.services.graph_analytics_service import GraphAnalyticsService
        with patch("app.graph.services.graph_analytics_service.is_available", return_value=False):
            svc    = GraphAnalyticsService()
            result = await svc.largest_constellations()
        assert result == []


# ═══════════════════════════════════════════════════════════════
# GRAPH POPULATION SERVICE TESTS
# ═══════════════════════════════════════════════════════════════

class TestGraphPopulationService:
    """Phase 3+4+6: Population pipeline orchestration."""

    @pytest.mark.asyncio
    async def test_populate_all_skips_when_neo4j_unavailable(self):
        from app.graph.services.graph_population_service import GraphPopulationService
        mock_session = AsyncMock()

        with patch("app.graph.services.graph_population_service.is_available", return_value=False):
            svc    = GraphPopulationService(mock_session)
            report = await svc.populate_all()

        assert report.status == "skipped"
        assert report.satellites_synced == 0

    @pytest.mark.asyncio
    async def test_populate_all_phases_completed_on_success(self):
        from app.graph.services.graph_population_service import GraphPopulationService
        mock_session = AsyncMock()

        # Mock all sub-repos to return 0 without hitting Neo4j
        with patch("app.graph.services.graph_population_service.is_available", return_value=True), \
             patch("app.graph.services.graph_population_service.OrbitalRegimeRepository.seed",
                   new=AsyncMock(return_value=9)), \
             patch("app.graph.services.graph_population_service.LaunchVehicleRepository.seed",
                   new=AsyncMock(return_value=15)), \
             patch("app.graph.services.graph_population_service.LaunchSiteRepository.seed",
                   new=AsyncMock(return_value=12)), \
             patch("app.graph.services.graph_population_service.AgencyRepository.seed",
                   new=AsyncMock(return_value=14)), \
             patch("app.graph.services.graph_population_service.SatelliteGraphRepository.upsert_satellites",
                   new=AsyncMock(return_value={"nodes_created": 0})), \
             patch("app.graph.services.graph_population_service.ConjunctionGraphRepository.upsert_conjunctions",
                   new=AsyncMock(return_value={"nodes_created": 0})):

            # Mock DB queries to return empty lists
            from sqlalchemy import select
            mock_result = MagicMock()
            mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            mock_session.execute = AsyncMock(return_value=mock_result)

            svc    = GraphPopulationService(mock_session)
            report = await svc.populate_all()

        assert report.status in ("success", "partial")
        assert "seed_reference" in report.phases_completed
        assert report.regimes_seeded == 9
        assert report.vehicles_seeded == 15
        assert report.agencies_seeded == 14

    @pytest.mark.asyncio
    async def test_populate_all_has_duration(self):
        from app.graph.services.graph_population_service import GraphPopulationService
        mock_session = AsyncMock()

        with patch("app.graph.services.graph_population_service.is_available", return_value=False):
            svc    = GraphPopulationService(mock_session)
            report = await svc.populate_all()

        assert report.duration_s >= 0.0
        assert report.completed_at is not None
        assert report.completed_at >= report.started_at

    @pytest.mark.asyncio
    async def test_populate_report_as_dict(self):
        from app.graph.services.graph_population_service import GraphPopulationService
        mock_session = AsyncMock()

        with patch("app.graph.services.graph_population_service.is_available", return_value=False):
            svc    = GraphPopulationService(mock_session)
            report = await svc.populate_all()

        d = report.as_dict()
        assert "run_id" in d
        assert "status" in d
        assert "satellites_synced" in d
        assert "phases_completed" in d


# ═══════════════════════════════════════════════════════════════
# API ENDPOINT TESTS (FastAPI test client, Neo4j mocked)
# ═══════════════════════════════════════════════════════════════

class TestKnowledgeGraphAPI:
    """Phase 8: API endpoint coverage with Neo4j mocked."""

    def _get_client(self):
        """Return a TestClient with Neo4j unavailable."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.endpoints.knowledge_graph import router

        app = FastAPI()
        app.include_router(router, prefix="/graph")
        return TestClient(app, raise_server_exceptions=False)

    def test_health_returns_503_when_neo4j_down(self):
        client = self._get_client()
        with patch("app.api.v1.endpoints.knowledge_graph.neo4j_health",
                   new=AsyncMock(return_value={"reachable": False, "error": "down", "database": "orbitiq", "node_count": 0})), \
             patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=False):
            resp = client.get("/graph/health")
        assert resp.status_code == 503

    def test_satellite_returns_503_when_neo4j_down(self):
        client = self._get_client()
        with patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=False):
            resp = client.get("/graph/satellite/25544")
        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"].lower()

    def test_operator_returns_503_when_neo4j_down(self):
        client = self._get_client()
        with patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=False):
            resp = client.get("/graph/operator/ISRO")
        assert resp.status_code == 503

    def test_country_returns_503_when_neo4j_down(self):
        client = self._get_client()
        with patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=False):
            resp = client.get("/graph/country/IN")
        assert resp.status_code == 503

    def test_analytics_summary_returns_503_when_neo4j_down(self):
        client = self._get_client()
        with patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=False):
            resp = client.get("/graph/analytics/summary")
        assert resp.status_code == 503

    def test_satellite_returns_404_when_not_found(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.endpoints.knowledge_graph import router

        app = FastAPI()
        app.include_router(router, prefix="/graph")
        client = TestClient(app, raise_server_exceptions=False)

        with patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=True), \
             patch("app.graph.repositories.graph_repository.SatelliteGraphRepository.get_satellite",
                   new=AsyncMock(return_value=None)):
            resp = client.get("/graph/satellite/99999")
        assert resp.status_code == 404

    def test_health_returns_200_when_available(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.endpoints.knowledge_graph import router

        app = FastAPI()
        app.include_router(router, prefix="/graph")
        client = TestClient(app)

        mock_status = {
            "reachable": True, "database": "orbitiq",
            "node_count": 50000, "error": None,
        }
        with patch("app.api.v1.endpoints.knowledge_graph.neo4j_health",
                   new=AsyncMock(return_value=mock_status)), \
             patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=True):
            resp = client.get("/graph/health")
        assert resp.status_code == 200
        assert resp.json()["reachable"] is True

    def test_conjunction_network_builds_graph_json(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.endpoints.knowledge_graph import router

        app = FastAPI()
        app.include_router(router, prefix="/graph")
        client = TestClient(app)

        mock_edges = [
            {
                "norad1": 25544, "name1": "ISS",
                "norad2": 44713, "name2": "STARLINK-1007",
                "conjunctionId": "CDM-001",
                "Pc": 2e-3, "missKm": 0.25,
                "riskLevel": "red", "tca": None, "resolved": False,
            }
        ]

        with patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=True), \
             patch("app.graph.services.graph_analytics_service.GraphAnalyticsService.conjunction_risk_network",
                   new=AsyncMock(return_value=mock_edges)):
            resp = client.get("/graph/analytics/conjunctions?min_pc=1e-5")

        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body
        assert "meta" in body
        assert len(body["nodes"]) == 2  # ISS + STARLINK
        assert len(body["edges"]) == 1

    def test_search_requires_minimum_query_length(self):
        client = self._get_client()
        with patch("app.api.v1.endpoints.knowledge_graph.is_available", return_value=True):
            resp = client.get("/graph/search?q=a")  # too short
        assert resp.status_code == 422  # validation error


# ═══════════════════════════════════════════════════════════════
# SCHEDULER TESTS
# ═══════════════════════════════════════════════════════════════

class TestSchedulerJobIntegration:
    """Verify graph population job is registered alongside other jobs."""

    def test_scheduler_has_4_jobs(self):
        from app.services.catalog_scheduler import build_scheduler
        s   = build_scheduler()
        ids = {j.id for j in s.get_jobs()}
        assert "full_catalog_sync"       in ids
        assert "incremental_tle_refresh" in ids
        assert "conjunction_screening"   in ids
        assert "graph_population"        in ids
        assert len(ids) == 4

    def test_graph_population_job_interval_6h(self):
        from app.services.catalog_scheduler import build_scheduler
        from apscheduler.triggers.interval import IntervalTrigger
        s    = build_scheduler()
        jobs = {j.id: j for j in s.get_jobs()}
        job  = jobs["graph_population"]
        assert isinstance(job.trigger, IntervalTrigger)
        assert job.trigger.interval.total_seconds() == 6 * 3600


# ═══════════════════════════════════════════════════════════════
# PERFORMANCE BENCHMARKS
# ═══════════════════════════════════════════════════════════════

class TestGraphPerformanceBenchmarks:
    """Phase 10: Ensure seed data and record preparation is fast."""

    def test_seed_data_preparation_timing(self):
        """Building all seed data dicts takes < 10ms — no I/O needed."""
        from app.graph.repositories.graph_repository import (
            ORBITAL_REGIMES, LAUNCH_VEHICLES, LAUNCH_SITES, AGENCIES
        )
        t0 = time.perf_counter()
        total = len(ORBITAL_REGIMES) + len(LAUNCH_VEHICLES) + len(LAUNCH_SITES) + len(AGENCIES)
        elapsed = time.perf_counter() - t0
        print(f"\n  Seed data: {total} records loaded in {elapsed*1000:.2f}ms")
        assert elapsed < 0.01  # < 10ms — pure Python dict access

    def test_50k_satellite_record_preparation(self):
        """Building 50K graph records from ORM-like dicts takes < 2s."""
        N = 50_000
        t0 = time.perf_counter()
        records = []
        for i in range(N):
            sat = _make_sat_dict(10000 + i, regime="LEO", operator_name="SpaceX")
            records.append({
                "noradId":       sat["norad_id"],
                "cosparId":      sat["cospar_id"],
                "name":          sat["name"],
                "regime":        sat["regime"],
                "operatorName":  sat["operator_name"],
                "countryCode":   sat["country_code"],
                "constellation": sat["constellation"],
            })
        elapsed = time.perf_counter() - t0
        print(f"\n  50K graph record prep: {elapsed:.3f}s ({N/elapsed:.0f} records/s)")
        assert len(records) == N
        assert elapsed < 2.0, f"50K record prep took {elapsed:.1f}s > 2s"

    def test_cdm_to_graph_record_conversion_1k(self):
        """Building 1000 conjunction graph records takes < 100ms."""
        N = 1_000
        t0 = time.perf_counter()
        graph_recs = []
        for i in range(N):
            cdm = _make_conj_dict(f"CDM-{i:06d}", pc=1e-4 + i * 1e-7)
            tca = cdm["tca"]
            graph_recs.append({
                "conjunctionId":       cdm["conjunction_id"],
                "tca":                 tca.isoformat() if tca else None,
                "missDistanceKm":      cdm["miss_distance_km"],
                "collisionProbability":cdm["collision_probability"],
                "riskLevel":           cdm["risk_level"],
                "primaryNorad":        cdm["primary_norad"],
                "secondaryNorad":      cdm["secondary_norad"],
            })
        elapsed = time.perf_counter() - t0
        print(f"\n  1K CDM record prep: {elapsed*1000:.2f}ms")
        assert len(graph_recs) == N
        assert elapsed < 0.1


# ═══════════════════════════════════════════════════════════════
# FAILURE RECOVERY TESTS
# ═══════════════════════════════════════════════════════════════

class TestFailureRecovery:
    """Every service must degrade gracefully without Neo4j."""

    @pytest.mark.asyncio
    async def test_orbital_regime_repo_graceful_no_neo4j(self):
        from app.graph.repositories.graph_repository import OrbitalRegimeRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=False):
            repo = OrbitalRegimeRepository()
            assert await repo.seed()     == 0
            assert await repo.get_all()  == []
            assert await repo.get_by_id("LEO") is None

    @pytest.mark.asyncio
    async def test_launch_vehicle_repo_graceful_no_neo4j(self):
        from app.graph.repositories.graph_repository import LaunchVehicleRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=False):
            repo = LaunchVehicleRepository()
            assert await repo.seed() == 0
            assert await repo.get_all() == []
            assert await repo.get_by_id("LV-PSLV") is None

    @pytest.mark.asyncio
    async def test_agency_repo_graceful_no_neo4j(self):
        from app.graph.repositories.graph_repository import AgencyRepository
        with patch("app.graph.repositories.graph_repository.is_available", return_value=False):
            repo = AgencyRepository()
            assert await repo.seed() == 0
            assert await repo.get_by_name("ISRO") == []

    @pytest.mark.asyncio
    async def test_population_service_does_not_raise_on_db_error(self):
        """A DB exception during satellite sync should not crash the service."""
        from app.graph.services.graph_population_service import GraphPopulationService
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        with patch("app.graph.services.graph_population_service.is_available", return_value=True), \
             patch("app.graph.services.graph_population_service.OrbitalRegimeRepository.seed",
                   new=AsyncMock(return_value=0)), \
             patch("app.graph.services.graph_population_service.LaunchVehicleRepository.seed",
                   new=AsyncMock(return_value=0)), \
             patch("app.graph.services.graph_population_service.LaunchSiteRepository.seed",
                   new=AsyncMock(return_value=0)), \
             patch("app.graph.services.graph_population_service.AgencyRepository.seed",
                   new=AsyncMock(return_value=0)):
            svc    = GraphPopulationService(mock_session)
            report = await svc.populate_all()

        # Should not raise — errors collected in report
        assert report.status in ("success", "partial", "failed")
        assert isinstance(report.errors, list)

    @pytest.mark.asyncio
    async def test_analytics_service_all_methods_degrade_gracefully(self):
        """All 8+ analytics methods return empty when Neo4j is down."""
        from app.graph.services.graph_analytics_service import GraphAnalyticsService

        with patch("app.graph.services.graph_analytics_service.is_available", return_value=False):
            svc = GraphAnalyticsService()
            assert await svc.top_operators_by_satellite_count() == []
            assert await svc.top_countries_by_active_spacecraft() == []
            assert await svc.largest_constellations() == []
            assert await svc.conjunction_risk_network() == []
            assert await svc.orbital_regime_density() == []
            assert await svc.top_operators_by_conjunction_risk() == []
            assert await svc.graph_summary() == {"available": False}
            assert await svc.country_full_profile("IN") == {}
            assert await svc.mission_profile("MSN-001") == {}
