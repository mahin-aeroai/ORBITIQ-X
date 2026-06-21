"""
ORBITIQ-X — Custom Prometheus Metrics
=======================================
Domain-specific metrics beyond the HTTP-level instrumentation
provided by prometheus-fastapi-instrumentator.

All metrics are registered in a single module to avoid duplicate
registration errors in multi-worker deployments.

Metric naming follows Prometheus conventions:
  orbitiq_{subsystem}_{name}_{unit}

Usage
──────
  from app.core.metrics import (
      PROPAGATION_DURATION,
      CONJUNCTION_SCREENING_DURATION,
      GRAPH_QUERY_DURATION,
      AGENT_EXECUTION_DURATION,
      RAG_RETRIEVAL_DURATION,
      SCHEDULER_JOB_DURATION,
      SCHEDULER_JOB_FAILURES,
      REDIS_AVAILABLE,
      NEO4J_AVAILABLE,
      AUTH_FAILURES,
  )

  # Record a propagation run
  with PROPAGATION_DURATION.time():
      await propagate_catalog()

  # Record a failure
  SCHEDULER_JOB_FAILURES.labels(job="full_catalog_sync").inc()
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Safe import — metrics are optional (no prometheus = no-op) ────────────────

try:
    from prometheus_client import Counter, Gauge, Histogram, Summary

    # ── Digital Twin ─────────────────────────────────────────────────────────

    PROPAGATION_DURATION = Histogram(
        "orbitiq_propagation_duration_seconds",
        "Time to propagate the full orbital catalog",
        buckets=[1, 5, 10, 30, 60, 120, 300, 600],
    )

    PROPAGATION_OBJECTS = Gauge(
        "orbitiq_propagation_objects_total",
        "Number of objects in the last propagation run",
    )

    # ── Conjunction Engine ───────────────────────────────────────────────────

    CONJUNCTION_SCREENING_DURATION = Histogram(
        "orbitiq_conjunction_screening_duration_seconds",
        "Time to complete a full conjunction screening run",
        buckets=[1, 5, 15, 30, 60, 120, 300],
    )

    CONJUNCTION_EVENTS_CREATED = Counter(
        "orbitiq_conjunction_events_created_total",
        "Total conjunction events persisted",
        ["risk_level"],
    )

    CONJUNCTION_ALERTS_PUBLISHED = Counter(
        "orbitiq_conjunction_alerts_published_total",
        "Total conjunction alerts published to Redis",
        ["risk_level"],
    )

    # ── Knowledge Graph ───────────────────────────────────────────────────────

    GRAPH_QUERY_DURATION = Histogram(
        "orbitiq_graph_query_duration_seconds",
        "Neo4j Cypher query execution time",
        ["query_type"],
        buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10],
    )

    GRAPH_POPULATION_DURATION = Histogram(
        "orbitiq_graph_population_duration_seconds",
        "Time to sync PostgreSQL catalog into Neo4j",
        buckets=[10, 30, 60, 120, 300, 600, 1200],
    )

    # ── Agent System ──────────────────────────────────────────────────────────

    AGENT_EXECUTION_DURATION = Histogram(
        "orbitiq_agent_execution_duration_seconds",
        "Multi-agent task total execution time",
        ["task_type"],
        buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
    )

    AGENT_TASKS_TOTAL = Counter(
        "orbitiq_agent_tasks_total",
        "Agent tasks submitted",
        ["status"],
    )

    # ── RAG / GraphRAG ───────────────────────────────────────────────────────

    RAG_RETRIEVAL_DURATION = Histogram(
        "orbitiq_rag_retrieval_duration_seconds",
        "GraphRAG retrieval and synthesis time",
        buckets=[0.05, 0.1, 0.5, 1, 2, 5, 10],
    )

    # ── Scheduler ────────────────────────────────────────────────────────────

    SCHEDULER_JOB_DURATION = Histogram(
        "orbitiq_scheduler_job_duration_seconds",
        "Scheduled job execution time",
        ["job"],
        buckets=[1, 5, 15, 60, 120, 300, 600, 1800],
    )

    SCHEDULER_JOB_FAILURES = Counter(
        "orbitiq_scheduler_job_failures_total",
        "Scheduled job failure count",
        ["job"],
    )

    SCHEDULER_LAST_RUN = Gauge(
        "orbitiq_scheduler_last_run_timestamp_seconds",
        "Unix timestamp of the last successful job run",
        ["job"],
    )

    # ── Infrastructure availability ───────────────────────────────────────────

    REDIS_AVAILABLE = Gauge(
        "orbitiq_redis_available",
        "1 if Redis is connected, 0 otherwise",
    )

    NEO4J_AVAILABLE = Gauge(
        "orbitiq_neo4j_available",
        "1 if Neo4j is connected, 0 otherwise",
    )

    VECTOR_STORE_AVAILABLE = Gauge(
        "orbitiq_vector_store_available",
        "1 if the vector store (Qdrant/Weaviate) is available",
    )

    MINIO_AVAILABLE = Gauge(
        "orbitiq_minio_available",
        "1 if MinIO is reachable, 0 otherwise",
    )

    # ── Authentication ────────────────────────────────────────────────────────

    AUTH_FAILURES = Counter(
        "orbitiq_auth_failures_total",
        "Failed authentication attempts",
        ["reason"],  # invalid_credentials | locked | disabled | expired_token
    )

    AUTH_LOGINS = Counter(
        "orbitiq_auth_logins_total",
        "Successful login events",
        ["role"],
    )

    # ── Catalog sync ─────────────────────────────────────────────────────────

    CATALOG_SYNC_DURATION = Histogram(
        "orbitiq_catalog_sync_duration_seconds",
        "Space-Track catalog sync duration",
        ["mode"],   # full | incremental
        buckets=[5, 15, 30, 60, 120, 300, 600, 1200, 1800],
    )

    CATALOG_OBJECTS_SYNCED = Gauge(
        "orbitiq_catalog_objects_synced_total",
        "Number of satellite objects in the last sync",
    )

    logger.info("prometheus_metrics_registered")

except ImportError:
    # prometheus_client not installed — create no-op stubs
    logger.info("prometheus_client_unavailable — metrics disabled")

    class _NoOp:
        """No-op metric that absorbs all calls."""
        def labels(self, **_): return self
        def inc(self, *_, **__): pass
        def dec(self, *_, **__): pass
        def set(self, *_, **__): pass
        def observe(self, *_, **__): pass
        def time(self): return _NoOpCtx()

    class _NoOpCtx:
        def __enter__(self): return self
        def __exit__(self, *_): pass

    _noop = _NoOp()
    PROPAGATION_DURATION         = _noop  # type: ignore[assignment]
    PROPAGATION_OBJECTS          = _noop  # type: ignore[assignment]
    CONJUNCTION_SCREENING_DURATION= _noop  # type: ignore[assignment]
    CONJUNCTION_EVENTS_CREATED   = _noop  # type: ignore[assignment]
    CONJUNCTION_ALERTS_PUBLISHED  = _noop  # type: ignore[assignment]
    GRAPH_QUERY_DURATION         = _noop  # type: ignore[assignment]
    GRAPH_POPULATION_DURATION    = _noop  # type: ignore[assignment]
    AGENT_EXECUTION_DURATION     = _noop  # type: ignore[assignment]
    AGENT_TASKS_TOTAL            = _noop  # type: ignore[assignment]
    RAG_RETRIEVAL_DURATION       = _noop  # type: ignore[assignment]
    SCHEDULER_JOB_DURATION       = _noop  # type: ignore[assignment]
    SCHEDULER_JOB_FAILURES       = _noop  # type: ignore[assignment]
    SCHEDULER_LAST_RUN           = _noop  # type: ignore[assignment]
    REDIS_AVAILABLE              = _noop  # type: ignore[assignment]
    NEO4J_AVAILABLE              = _noop  # type: ignore[assignment]
    VECTOR_STORE_AVAILABLE       = _noop  # type: ignore[assignment]
    MINIO_AVAILABLE              = _noop  # type: ignore[assignment]
    AUTH_FAILURES                = _noop  # type: ignore[assignment]
    AUTH_LOGINS                  = _noop  # type: ignore[assignment]
    CATALOG_SYNC_DURATION        = _noop  # type: ignore[assignment]
    CATALOG_OBJECTS_SYNCED       = _noop  # type: ignore[assignment]
