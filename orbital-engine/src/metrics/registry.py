"""
ORBITIQ-X Orbital Engine
Prometheus Metrics Registry

All custom metrics for the orbital engine.
Exposed at: GET /api/v1/orbital/health/metrics

Metric naming convention:
  orbitiq_orbital_{subsystem}_{measurement}_{unit}

Subsystems:
  catalog, propagation, conjunction, reentry, ingest, cache, scheduler
"""

from prometheus_client import (
    Counter, Gauge, Histogram, Summary, CollectorRegistry, REGISTRY
)

# ── Catalog metrics ───────────────────────────────────────────

CATALOG_TOTAL = Gauge(
    "orbitiq_orbital_catalog_objects_total",
    "Total resident space objects in catalog",
    ["regime", "status", "object_type"],
)

CATALOG_TLE_AGE = Histogram(
    "orbitiq_orbital_catalog_tle_age_days",
    "Distribution of TLE ages across catalog",
    buckets=[0.5, 1, 2, 3, 5, 7, 14, 30],
)

CATALOG_SYNC_DURATION = Histogram(
    "orbitiq_orbital_catalog_sync_duration_seconds",
    "Time taken to sync catalog from upstream",
    ["source"],
    buckets=[10, 30, 60, 120, 300, 600],
)

CATALOG_SYNC_ERRORS = Counter(
    "orbitiq_orbital_catalog_sync_errors_total",
    "Total catalog sync failures",
    ["source", "error_code"],
)

CATALOG_INGESTED = Counter(
    "orbitiq_orbital_catalog_ingested_total",
    "Total RSOs ingested (new + updated)",
    ["source", "object_type"],
)

# ── Propagation metrics ───────────────────────────────────────

PROPAGATION_REQUESTS = Counter(
    "orbitiq_orbital_propagation_requests_total",
    "Total propagation requests",
    ["mode", "propagator"],   # mode: single|batch; propagator: sgp4|hifi
)

PROPAGATION_DURATION = Histogram(
    "orbitiq_orbital_propagation_duration_seconds",
    "Propagation time per object",
    ["propagator"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

PROPAGATION_BATCH_SIZE = Histogram(
    "orbitiq_orbital_propagation_batch_size",
    "Number of objects per batch propagation request",
    buckets=[1, 10, 100, 1000, 5000, 10000, 50000],
)

PROPAGATION_ERRORS = Counter(
    "orbitiq_orbital_propagation_errors_total",
    "Propagation failures",
    ["error_code"],
)

PROPAGATION_DIVERGENCE = Counter(
    "orbitiq_orbital_propagation_divergence_total",
    "SGP4 divergence events (satellite below horizon or error code > 0)",
    ["regime"],
)

# ── Conjunction metrics ───────────────────────────────────────

CONJUNCTION_SCREEN_DURATION = Histogram(
    "orbitiq_orbital_conjunction_screen_duration_seconds",
    "End-to-end conjunction screening time",
    ["mode"],    # mode: priority|full
    buckets=[5, 15, 30, 60, 120, 300],
)

CONJUNCTION_PAIRS_SCREENED = Counter(
    "orbitiq_orbital_conjunction_pairs_screened_total",
    "Total object pairs evaluated in spatial filter",
)

CONJUNCTION_CDM_GENERATED = Counter(
    "orbitiq_orbital_conjunction_cdm_generated_total",
    "CDMs generated above Pc threshold",
    ["risk_level"],
)

CONJUNCTION_ACTIVE = Gauge(
    "orbitiq_orbital_conjunction_active",
    "Currently active (unresolved) conjunction events by risk level",
    ["risk_level"],
)

CONJUNCTION_MAX_PC = Gauge(
    "orbitiq_orbital_conjunction_max_pc",
    "Maximum collision probability across all active CDMs",
)

CONJUNCTION_ALERTS_STREAMED = Counter(
    "orbitiq_orbital_conjunction_alerts_streamed_total",
    "Total CDM alerts sent via SSE/WebSocket",
    ["risk_level"],
)

# ── Re-entry metrics ──────────────────────────────────────────

REENTRY_CANDIDATES = Gauge(
    "orbitiq_orbital_reentry_candidates",
    "Objects currently in re-entry monitoring",
    ["alert_level"],
)

REENTRY_PREDICTED_7DAY = Gauge(
    "orbitiq_orbital_reentry_predicted_7day",
    "Objects predicted to re-enter within 7 days",
)

REENTRY_ALERTS_ISSUED = Counter(
    "orbitiq_orbital_reentry_alerts_total",
    "Total re-entry alerts issued",
    ["alert_level"],
)

# ── Redis cache metrics ───────────────────────────────────────

CACHE_HIT_RATE = Gauge(
    "orbitiq_orbital_cache_hit_rate",
    "Redis cache hit rate for TLE and state lookups",
    ["cache_type"],   # tle|state|catalog
)

CACHE_TLE_ENTRIES = Gauge(
    "orbitiq_orbital_cache_tle_entries",
    "Number of TLE entries currently in Redis cache",
)

CACHE_OPERATIONS = Counter(
    "orbitiq_orbital_cache_operations_total",
    "Redis cache operations",
    ["operation", "cache_type", "result"],   # result: hit|miss|error
)

# ── Scheduler metrics ─────────────────────────────────────────

SCHEDULER_JOB_DURATION = Histogram(
    "orbitiq_orbital_scheduler_job_duration_seconds",
    "Scheduler job execution time",
    ["job_id"],
    buckets=[5, 15, 30, 60, 120, 300, 600],
)

SCHEDULER_JOB_ERRORS = Counter(
    "orbitiq_orbital_scheduler_job_errors_total",
    "Scheduler job failures",
    ["job_id"],
)

SCHEDULER_JOB_MISSED = Counter(
    "orbitiq_orbital_scheduler_job_missed_total",
    "Scheduler jobs that missed their execution window",
    ["job_id"],
)

# ── API metrics (custom, beyond prometheus-fastapi-instrumentator) ────────────

API_ACTIVE_SSE_CONNECTIONS = Gauge(
    "orbitiq_orbital_api_sse_connections_active",
    "Active SSE connections for live streaming",
    ["stream_type"],   # positions|conjunctions|reentry
)

API_BATCH_QUEUE_DEPTH = Gauge(
    "orbitiq_orbital_api_batch_queue_depth",
    "Pending batch propagation tasks in Celery queue",
)


# ── Metric update helpers ─────────────────────────────────────

def update_catalog_totals(counts_by_regime_status: dict) -> None:
    """Called after each catalog sync to update regime/status gauges."""
    CATALOG_TOTAL._metrics.clear()  # Reset before re-setting
    for (regime, status, obj_type), count in counts_by_regime_status.items():
        CATALOG_TOTAL.labels(regime=regime, status=status, object_type=obj_type).set(count)


def record_propagation(norad_id: int, duration_s: float, propagator: str = "sgp4") -> None:
    """Record a single propagation call."""
    PROPAGATION_REQUESTS.labels(mode="single", propagator=propagator).inc()
    PROPAGATION_DURATION.labels(propagator=propagator).observe(duration_s)


def record_conjunction_screen(
    mode: str,
    duration_s: float,
    pairs_checked: int,
    cdm_count: int,
    red_count: int,
    yellow_count: int,
) -> None:
    """Record a conjunction screening run."""
    CONJUNCTION_SCREEN_DURATION.labels(mode=mode).observe(duration_s)
    CONJUNCTION_PAIRS_SCREENED.inc(pairs_checked)
    CONJUNCTION_CDM_GENERATED.labels(risk_level="red").inc(red_count)
    CONJUNCTION_CDM_GENERATED.labels(risk_level="yellow").inc(yellow_count)
    CONJUNCTION_CDM_GENERATED.labels(risk_level="green").inc(max(0, cdm_count - red_count - yellow_count))
