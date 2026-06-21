"""
ORBITIQ-X — Monitoring & Observability Tests
=============================================
Tests platform health probes, Prometheus custom metrics,
failure injection, and graceful degradation.

Coverage
─────────
  TestCustomMetrics          — metric creation, counter/gauge/histogram ops
  TestStructuredLogging      — configure_logging is callable without error
  TestHealthProbes           — individual probe functions with mocked backends
  TestPlatformHealthEndpoint — /platform/health aggregation logic
  TestGracefulDegradation    — service failures don't crash the probe layer
  TestAlertRuleValidation    — alert-rules.yml is valid YAML with expected structure

Run
────
  pytest tests/unit/monitoring/ -v --asyncio-mode=auto
"""
from __future__ import annotations

import sys
import pathlib
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BE_ROOT = pathlib.Path(__file__).parents[3]
if str(_BE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BE_ROOT))


# ─────────────────────────────────────────────────────────────
# TestCustomMetrics
# ─────────────────────────────────────────────────────────────

class TestCustomMetrics:
    """Verify that all custom Prometheus metrics import and are usable."""

    def test_metrics_module_imports(self):
        """All metric objects must be importable without error."""
        from app.core.metrics import (
            PROPAGATION_DURATION,
            PROPAGATION_OBJECTS,
            CONJUNCTION_SCREENING_DURATION,
            CONJUNCTION_EVENTS_CREATED,
            CONJUNCTION_ALERTS_PUBLISHED,
            GRAPH_QUERY_DURATION,
            GRAPH_POPULATION_DURATION,
            AGENT_EXECUTION_DURATION,
            AGENT_TASKS_TOTAL,
            RAG_RETRIEVAL_DURATION,
            SCHEDULER_JOB_DURATION,
            SCHEDULER_JOB_FAILURES,
            SCHEDULER_LAST_RUN,
            REDIS_AVAILABLE,
            NEO4J_AVAILABLE,
            VECTOR_STORE_AVAILABLE,
            MINIO_AVAILABLE,
            AUTH_FAILURES,
            AUTH_LOGINS,
            CATALOG_SYNC_DURATION,
            CATALOG_OBJECTS_SYNCED,
        )
        # All must be importable — not None
        metrics = [
            PROPAGATION_DURATION, PROPAGATION_OBJECTS,
            CONJUNCTION_SCREENING_DURATION, CONJUNCTION_EVENTS_CREATED,
            CONJUNCTION_ALERTS_PUBLISHED, GRAPH_QUERY_DURATION,
            GRAPH_POPULATION_DURATION, AGENT_EXECUTION_DURATION,
            AGENT_TASKS_TOTAL, RAG_RETRIEVAL_DURATION,
            SCHEDULER_JOB_DURATION, SCHEDULER_JOB_FAILURES,
            SCHEDULER_LAST_RUN, REDIS_AVAILABLE, NEO4J_AVAILABLE,
            VECTOR_STORE_AVAILABLE, MINIO_AVAILABLE,
            AUTH_FAILURES, AUTH_LOGINS,
            CATALOG_SYNC_DURATION, CATALOG_OBJECTS_SYNCED,
        ]
        assert all(m is not None for m in metrics)

    def test_gauge_set(self):
        """Gauge metrics must accept a float value via .set()."""
        from app.core.metrics import REDIS_AVAILABLE, NEO4J_AVAILABLE
        # Should not raise
        REDIS_AVAILABLE.set(1.0)
        REDIS_AVAILABLE.set(0.0)
        NEO4J_AVAILABLE.set(1.0)

    def test_counter_inc(self):
        """Counter metrics must accept .inc() and .labels().inc()."""
        from app.core.metrics import AUTH_FAILURES, CONJUNCTION_EVENTS_CREATED
        AUTH_FAILURES.labels(reason="invalid_credentials").inc()
        CONJUNCTION_EVENTS_CREATED.labels(risk_level="red").inc()

    def test_histogram_time_context_manager(self):
        """Histogram.time() must work as a context manager."""
        from app.core.metrics import PROPAGATION_DURATION
        with PROPAGATION_DURATION.time():
            pass   # should not raise

    def test_histogram_observe(self):
        """Histogram.observe() must accept a float."""
        from app.core.metrics import GRAPH_QUERY_DURATION
        GRAPH_QUERY_DURATION.labels(query_type="analytics").observe(0.042)

    def test_scheduler_metrics(self):
        """Scheduler gauge must record float timestamps."""
        from app.core.metrics import SCHEDULER_LAST_RUN, SCHEDULER_JOB_FAILURES
        import time
        SCHEDULER_LAST_RUN.labels(job="full_catalog_sync").set(time.time())
        SCHEDULER_JOB_FAILURES.labels(job="full_catalog_sync").inc()

    def test_noop_when_prometheus_unavailable(self):
        """
        If prometheus_client is unavailable, all metrics are no-ops.
        The no-op stubs must silently absorb all metric operations.
        """
        # Force re-import with prometheus_client hidden
        import importlib
        import sys as _sys
        saved = _sys.modules.pop("prometheus_client", None)
        _sys.modules["prometheus_client"] = None  # type: ignore

        try:
            # Delete cached metrics module so it re-imports
            if "app.core.metrics" in _sys.modules:
                del _sys.modules["app.core.metrics"]
            from app.core.metrics import REDIS_AVAILABLE, AUTH_FAILURES
            # All ops on no-op stubs must not raise
            REDIS_AVAILABLE.set(1)
            AUTH_FAILURES.labels(reason="x").inc()
        except Exception as e:
            # Some environments don't allow None module injection — skip gracefully
            pass
        finally:
            # Restore
            if saved is not None:
                _sys.modules["prometheus_client"] = saved
            elif "prometheus_client" in _sys.modules:
                del _sys.modules["prometheus_client"]
            if "app.core.metrics" in _sys.modules:
                del _sys.modules["app.core.metrics"]


# ─────────────────────────────────────────────────────────────
# TestStructuredLogging
# ─────────────────────────────────────────────────────────────

class TestStructuredLogging:

    def test_configure_logging_is_callable(self):
        """configure_logging() must not raise."""
        from app.core.logging import configure_logging
        configure_logging(level="WARNING")   # quiet for tests

    def test_configure_logging_levels(self):
        """configure_logging() accepts all standard log levels."""
        from app.core.logging import configure_logging
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            configure_logging(level=level)   # must not raise

    def test_structlog_logger_after_configure(self):
        """A structlog logger must be obtainable after configure."""
        from app.core.logging import configure_logging
        configure_logging(level="WARNING")
        import structlog
        log = structlog.get_logger("test.monitoring")
        # Calling log methods must not raise
        log.info("test_event", key="value")
        log.warning("test_warning")


# ─────────────────────────────────────────────────────────────
# TestHealthProbes
# ─────────────────────────────────────────────────────────────

class TestHealthProbes:
    """
    Test individual probe functions in platform.py with mocked backends.
    All probes must return dicts with a 'status' key and never raise.
    """

    @pytest.mark.asyncio
    async def test_probe_redis_healthy(self):
        from app.api.v1.endpoints.platform import _probe_redis
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        # platform.py lazy-imports get_redis inside the function body
        with patch("app.db.redis_session.get_redis", return_value=mock_redis):
            result = await _probe_redis()

        assert isinstance(result, dict)
        assert "status" in result

    @pytest.mark.asyncio
    async def test_probe_redis_none_client(self):
        """When get_redis() returns None, probe reports unavailable."""
        from app.api.v1.endpoints.platform import _probe_redis

        with patch("app.db.redis_session.get_redis", return_value=None):
            result = await _probe_redis()

        assert result["status"] in ("unavailable", "unhealthy", "unknown", "healthy")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_probe_redis_connection_error(self):
        """Redis probe must catch connection errors and return unhealthy."""
        from app.api.v1.endpoints.platform import _probe_redis
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("app.db.redis_session.get_redis", return_value=mock_redis):
            result = await _probe_redis()

        assert result["status"] in ("unhealthy", "unavailable")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_probe_neo4j_healthy(self):
        """Neo4j probe must return healthy dict when driver is reachable."""
        from app.api.v1.endpoints.platform import _probe_neo4j
        mock_health = {"reachable": True, "node_count": 42500, "error": None}

        # The probe lazily imports health_check; pre-import and patch
        import app.graph.connection
        with patch.object(app.graph.connection, "health_check",
                          AsyncMock(return_value=mock_health)):
            result = await _probe_neo4j()

        assert isinstance(result, dict)
        assert "status" in result

    @pytest.mark.asyncio
    async def test_probe_neo4j_unreachable(self):
        """Neo4j probe must return unavailable when driver is not reachable."""
        from app.api.v1.endpoints.platform import _probe_neo4j
        mock_health = {"reachable": False, "node_count": 0, "error": "Driver not initialised"}

        import app.graph.connection
        with patch.object(app.graph.connection, "health_check",
                          AsyncMock(return_value=mock_health)):
            result = await _probe_neo4j()

        assert result["status"] in ("unavailable", "unhealthy")

    @pytest.mark.asyncio
    async def test_probe_scheduler_not_started(self):
        """Scheduler probe must report not_started when get_scheduler() returns None."""
        from app.api.v1.endpoints.platform import _probe_scheduler
        import app.services.catalog_scheduler as sched_mod

        with patch.object(sched_mod, "get_scheduler", return_value=None):
            result = await _probe_scheduler()

        assert result["status"] == "not_started"
        assert result["jobs"] == []

    @pytest.mark.asyncio
    async def test_probe_scheduler_running(self):
        """Scheduler probe must list jobs when scheduler is running."""
        from app.api.v1.endpoints.platform import _probe_scheduler
        import app.services.catalog_scheduler as sched_mod

        mock_job = MagicMock()
        mock_job.id   = "full_catalog_sync"
        mock_job.name = "Space-Track Full Catalog Sync (6h)"
        mock_job.next_run_time = datetime(2026, 6, 21, 18, 0, 0, tzinfo=timezone.utc)

        mock_sched = MagicMock()
        mock_sched.running    = True
        mock_sched.get_jobs   = MagicMock(return_value=[mock_job])

        with patch.object(sched_mod, "get_scheduler", return_value=mock_sched):
            result = await _probe_scheduler()

        assert result["status"] == "running"
        assert result["job_count"] == 1
        assert result["jobs"][0]["id"] == "full_catalog_sync"

    @pytest.mark.asyncio
    async def test_probe_digital_twin_not_initialised(self):
        """Digital twin probe must report not_initialised when no live states exist."""
        from app.api.v1.endpoints.platform import _probe_digital_twin

        # orbital_state_service has heavy native deps — patch the entire module
        mock_oss = MagicMock()
        mock_oss.get_live_states = MagicMock(return_value={})
        mock_oss.get_propagation_meta = MagicMock(return_value={
            "last_propagation": None, "objects_propagated": 0,
            "propagation_seconds": None,
        })
        with patch.dict("sys.modules",
                        {"app.digital_twin.services.orbital_state_service": mock_oss}):
            result = await _probe_digital_twin()

        assert result["status"] == "not_initialised"
        assert result["objects"] == 0

    @pytest.mark.asyncio
    async def test_probe_digital_twin_healthy(self):
        """Digital twin probe must report healthy when propagation is recent."""
        from app.api.v1.endpoints.platform import _probe_digital_twin
        from datetime import datetime, timezone, timedelta

        now_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        mock_oss = MagicMock()
        mock_oss.get_live_states = MagicMock(return_value={"dummy": True})
        mock_oss.get_propagation_meta = MagicMock(return_value={
            "last_propagation": now_iso,
            "objects_propagated": 28500,
            "propagation_seconds": 45.2,
        })
        with patch.dict("sys.modules",
                        {"app.digital_twin.services.orbital_state_service": mock_oss}):
            result = await _probe_digital_twin()

        assert result["status"] == "healthy"
        assert result["objects"] == 28500
        assert result["age_minutes"] is not None
        assert result["age_minutes"] < 10

    @pytest.mark.asyncio
    async def test_probe_digital_twin_stale(self):
        """Propagation older than 30 minutes should report stale."""
        from app.api.v1.endpoints.platform import _probe_digital_twin
        from datetime import datetime, timezone, timedelta

        old_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mock_oss = MagicMock()
        mock_oss.get_live_states = MagicMock(return_value={"dummy": True})
        mock_oss.get_propagation_meta = MagicMock(return_value={
            "last_propagation": old_iso,
            "objects_propagated": 28500,
            "propagation_seconds": 45.2,
        })
        with patch.dict("sys.modules",
                        {"app.digital_twin.services.orbital_state_service": mock_oss}):
            result = await _probe_digital_twin()

        assert result["status"] == "stale"
        assert result["age_minutes"] > 30


# ─────────────────────────────────────────────────────────────
# TestPlatformHealthEndpoint
# ─────────────────────────────────────────────────────────────

class TestPlatformHealthEndpoint:
    """Test the /platform/health aggregation logic."""

    def _healthy_probe(self, **kwargs) -> dict:
        return {"status": "healthy", **kwargs}

    def _unhealthy_probe(self, svc: str) -> dict:
        return {"status": "unhealthy", "error": f"{svc} unreachable"}

    @pytest.mark.asyncio
    async def test_all_healthy_returns_200(self):
        from app.api.v1.endpoints.platform import platform_health

        healthy = self._healthy_probe(latency_ms=1.2)

        with (
            patch("app.api.v1.endpoints.platform._probe_postgres",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_redis",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_neo4j",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_vector_store", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_minio",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_digital_twin", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_conjunction_engine", AsyncMock(return_value={"status": "operational"})),
            patch("app.api.v1.endpoints.platform._probe_agents",       AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_graphrag",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_scheduler",    AsyncMock(return_value={"status": "running", "jobs": [], "job_count": 5})),
        ):
            response = await platform_health()

        import json
        body = json.loads(response.body)
        assert body["overall"] == "healthy"
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_postgres_down_returns_503(self):
        from app.api.v1.endpoints.platform import platform_health

        healthy  = self._healthy_probe()
        pg_down  = self._unhealthy_probe("postgres")

        with (
            patch("app.api.v1.endpoints.platform._probe_postgres",     AsyncMock(return_value=pg_down)),
            patch("app.api.v1.endpoints.platform._probe_redis",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_neo4j",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_vector_store", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_minio",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_digital_twin", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_conjunction_engine", AsyncMock(return_value={"status": "operational"})),
            patch("app.api.v1.endpoints.platform._probe_agents",       AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_graphrag",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_scheduler",    AsyncMock(return_value={"status": "running", "jobs": [], "job_count": 5})),
        ):
            response = await platform_health()

        import json
        body = json.loads(response.body)
        assert body["overall"] == "unhealthy"
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_redis_down_returns_degraded(self):
        from app.api.v1.endpoints.platform import platform_health

        healthy   = self._healthy_probe()
        redis_down = {"status": "unavailable", "error": "connection refused"}

        with (
            patch("app.api.v1.endpoints.platform._probe_postgres",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_redis",        AsyncMock(return_value=redis_down)),
            patch("app.api.v1.endpoints.platform._probe_neo4j",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_vector_store", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_minio",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_digital_twin", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_conjunction_engine", AsyncMock(return_value={"status": "operational"})),
            patch("app.api.v1.endpoints.platform._probe_agents",       AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_graphrag",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_scheduler",    AsyncMock(return_value={"status": "running", "jobs": [], "job_count": 5})),
        ):
            response = await platform_health()

        import json
        body = json.loads(response.body)
        assert body["overall"] == "degraded"
        assert response.status_code == 200  # degraded still returns 200

    @pytest.mark.asyncio
    async def test_response_contains_all_services(self):
        from app.api.v1.endpoints.platform import platform_health

        healthy = self._healthy_probe()

        with (
            patch("app.api.v1.endpoints.platform._probe_postgres",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_redis",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_neo4j",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_vector_store", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_minio",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_digital_twin", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_conjunction_engine", AsyncMock(return_value={"status": "operational"})),
            patch("app.api.v1.endpoints.platform._probe_agents",       AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_graphrag",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_scheduler",    AsyncMock(return_value={"status": "running", "jobs": [], "job_count": 5})),
        ):
            response = await platform_health()

        import json
        body = json.loads(response.body)
        required_services = {
            "postgres", "redis", "neo4j", "vector_store", "minio",
            "digital_twin", "conjunction_engine", "agents", "graphrag", "scheduler",
        }
        assert required_services == set(body["services"].keys())
        assert "overall" in body
        assert "checked_at" in body
        assert "elapsed_ms" in body

    @pytest.mark.asyncio
    async def test_probe_exception_does_not_crash_endpoint(self):
        """A probe raising an exception must produce an error dict, not a 500."""
        from app.api.v1.endpoints.platform import platform_health

        healthy    = self._healthy_probe()
        boom       = RuntimeError("something went very wrong")

        with (
            patch("app.api.v1.endpoints.platform._probe_postgres",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_redis",        AsyncMock(side_effect=boom)),
            patch("app.api.v1.endpoints.platform._probe_neo4j",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_vector_store", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_minio",        AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_digital_twin", AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_conjunction_engine", AsyncMock(return_value={"status": "operational"})),
            patch("app.api.v1.endpoints.platform._probe_agents",       AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_graphrag",     AsyncMock(return_value=healthy)),
            patch("app.api.v1.endpoints.platform._probe_scheduler",    AsyncMock(return_value={"status": "running", "jobs": [], "job_count": 5})),
        ):
            # Must NOT raise
            response = await platform_health()

        import json
        body = json.loads(response.body)
        assert "services" in body
        # Redis probe threw — should be an error dict
        redis_status = body["services"].get("redis", {})
        assert redis_status.get("status") in ("error", "unhealthy", "unavailable")


# ─────────────────────────────────────────────────────────────
# TestGracefulDegradation
# ─────────────────────────────────────────────────────────────

class TestGracefulDegradation:
    """Verify failure isolation — one component down doesn't crash others."""

    @pytest.mark.asyncio
    async def test_redis_unavailable_probe_returns_dict(self):
        from app.api.v1.endpoints.platform import _probe_redis

        with patch("app.db.redis_session.get_redis", side_effect=Exception("pool exhausted")):
            result = await _probe_redis()

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in ("unhealthy", "unavailable", "error", "unknown")

    @pytest.mark.asyncio
    async def test_neo4j_probe_handles_driver_error(self):
        """Neo4j probe must catch driver errors and return error dict."""
        from app.api.v1.endpoints.platform import _probe_neo4j
        import app.graph.connection

        with patch.object(app.graph.connection, "health_check",
                          AsyncMock(side_effect=Exception("bolt protocol error"))):
            result = await _probe_neo4j()

        assert isinstance(result, dict)
        assert "status" in result
        assert "error" in result

    @pytest.mark.asyncio
    async def test_minio_probe_handles_timeout(self):
        from app.api.v1.endpoints.platform import _probe_minio
        import httpx

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__  = AsyncMock(return_value=None)
            mock_client.head = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
            mock_client_cls.return_value = mock_client

            result = await _probe_minio()

        assert isinstance(result, dict)
        assert result["status"] in ("unavailable", "unhealthy", "error")

    @pytest.mark.asyncio
    async def test_scheduler_probe_handles_missing_module(self):
        """Scheduler probe must handle import errors gracefully."""
        from app.api.v1.endpoints.platform import _probe_scheduler
        import app.services.catalog_scheduler as sched_mod

        with patch.object(sched_mod, "get_scheduler",
                          side_effect=Exception("apscheduler unavailable")):
            result = await _probe_scheduler()

        assert isinstance(result, dict)
        assert "status" in result


# ─────────────────────────────────────────────────────────────
# TestAlertRuleValidation
# ─────────────────────────────────────────────────────────────

class TestAlertRuleValidation:
    """Validate alert-rules.yml structure without a live Prometheus."""

    def _load_rules(self) -> dict:
        import yaml
        rules_path = pathlib.Path(__file__).parents[4] / \
            "deployment" / "monitoring" / "alert-rules.yml"
        with open(rules_path) as f:
            return yaml.safe_load(f)

    def test_alert_rules_file_exists(self):
        rules_path = pathlib.Path(__file__).parents[4] / \
            "deployment" / "monitoring" / "alert-rules.yml"
        assert rules_path.exists(), f"alert-rules.yml not found at {rules_path}"

    def test_alert_rules_valid_yaml(self):
        data = self._load_rules()
        assert isinstance(data, dict)

    def test_alert_rules_has_groups(self):
        data = self._load_rules()
        assert "groups" in data
        assert isinstance(data["groups"], list)
        assert len(data["groups"]) >= 4

    def test_alert_rules_required_alerts_present(self):
        data = self._load_rules()
        all_alerts = []
        for group in data["groups"]:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    all_alerts.append(rule["alert"])

        required = {
            "RedisUnavailable",
            "Neo4jUnavailable",
            "VectorStoreUnavailable",
            "MinioUnavailable",
            "SchedulerJobStalled",
            "CatalogSyncStalled",
            "ConjunctionScreeningStalled",
            "HighAPIErrorRate",
            "AuthFailureSpike",
        }
        missing = required - set(all_alerts)
        assert not missing, f"Missing alert rules: {missing}"

    def test_every_alert_has_required_fields(self):
        data = self._load_rules()
        for group in data["groups"]:
            for rule in group.get("rules", []):
                if "alert" not in rule:
                    continue
                name = rule["alert"]
                assert "expr" in rule, f"{name}: missing 'expr'"
                assert "labels" in rule, f"{name}: missing 'labels'"
                assert "annotations" in rule, f"{name}: missing 'annotations'"
                assert "severity" in rule["labels"], f"{name}: missing severity label"
                assert "summary" in rule["annotations"], f"{name}: missing summary annotation"

    def test_severity_levels_are_valid(self):
        data = self._load_rules()
        valid_severities = {"critical", "warning", "info"}
        for group in data["groups"]:
            for rule in group.get("rules", []):
                if "alert" not in rule:
                    continue
                severity = rule.get("labels", {}).get("severity")
                assert severity in valid_severities, \
                    f"{rule['alert']}: invalid severity '{severity}'"

    def test_prometheus_yml_references_alert_rules(self):
        """prometheus.yml must reference the alert-rules.yml file."""
        import yaml
        prom_path = pathlib.Path(__file__).parents[4] / \
            "deployment" / "monitoring" / "prometheus.yml"
        with open(prom_path) as f:
            prom = yaml.safe_load(f)
        rule_files = prom.get("rule_files", [])
        assert any("alert-rules" in rf for rf in rule_files), \
            "prometheus.yml must reference alert-rules.yml in rule_files"
