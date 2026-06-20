"""
ORBITIQ-X — Digital Twin Repository
=====================================
Component 2: Storage layer for the digital twin state.

Primary stores
──────────────
  Redis     — live states (TTL 15 min), forecast cache, density snapshot
  Neo4j     — predictive conjunction graph (Component 7)
  In-memory — density map, regime health (single-process; use Redis for HA)

Component 7 — ConjunctionForecastGraph
────────────────────────────────────────
New Neo4j nodes/relationships added by this module:

  (:FutureConjunction {
      conjunctionId:   str,   # CDM-forecast-{norad1}-{norad2}-{epoch}
      primaryNorad:    int,
      secondaryNorad:  int,
      forecastEpoch:   datetime,
      missDistanceKm:  float,
      estimatedPc:     float,
      riskLevel:       str,
      confidence:      float,
      generatedAt:     datetime,
  })

  (:Satellite)-[:PREDICTED_CONJUNCTION {role: 'PRIMARY'}]->(:FutureConjunction)
  (:Satellite)-[:PREDICTED_CONJUNCTION {role: 'SECONDARY'}]->(:FutureConjunction)
  (:FutureConjunction)-[:IN_ORBITAL_REGIME]->(:OrbitalRegime)
  (:FutureConjunction)-[:AFFECTS]->(:Satellite)

Audit notes
────────────
  app/graph/connection.py: execute_batch(), is_available() → used here
  Neo4j connection already initialised by neo4j_session.py at startup
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.digital_twin.models.twin_models import (
    OrbitalDensityMap, SpaceEnvironmentHealth, OrbitForecast
)

logger = logging.getLogger(__name__)

# In-memory snapshots (refreshed with each propagation cycle)
_DENSITY_SNAPSHOT:    OrbitalDensityMap | None = None
_HEALTH_SNAPSHOT:     SpaceEnvironmentHealth | None = None
_FORECAST_CACHE:      dict[int, OrbitForecast] = {}

REDIS_DENSITY_KEY = "twin:density:current"
REDIS_HEALTH_KEY  = "twin:health:current"
REDIS_FORECAST_PFX = "twin:forecast:"
REDIS_TTL_SHORT   = 900   # 15 min for live states
REDIS_TTL_MEDIUM  = 3600  # 1 hour for density/health


class DigitalTwinRepository:
    """
    Persists and retrieves digital twin state across Redis and Neo4j.

    Graceful degradation:
      Redis unavailable  → in-memory snapshots only
      Neo4j unavailable  → graph updates silently skipped
    """

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client

    # ── Density map ───────────────────────────────────────────

    async def save_density_map(self, density: OrbitalDensityMap) -> None:
        global _DENSITY_SNAPSHOT
        _DENSITY_SNAPSHOT = density
        if self._redis:
            try:
                await self._redis.setex(
                    REDIS_DENSITY_KEY,
                    REDIS_TTL_MEDIUM,
                    json.dumps(density.to_dict(), default=str),
                )
            except Exception as exc:
                logger.warning("redis_density_save_failed error=%s", exc)

    async def get_density_map(self) -> OrbitalDensityMap | None:
        if _DENSITY_SNAPSHOT:
            return _DENSITY_SNAPSHOT
        if self._redis:
            try:
                data = await self._redis.get(REDIS_DENSITY_KEY)
                if data:
                    logger.debug("density_map_from_redis")
            except Exception:
                pass
        return None

    # ── Regime health ─────────────────────────────────────────

    async def save_health(self, health: SpaceEnvironmentHealth) -> None:
        global _HEALTH_SNAPSHOT
        _HEALTH_SNAPSHOT = health
        if self._redis:
            try:
                await self._redis.setex(
                    REDIS_HEALTH_KEY,
                    REDIS_TTL_MEDIUM,
                    json.dumps(health.to_dict(), default=str),
                )
            except Exception as exc:
                logger.warning("redis_health_save_failed error=%s", exc)

    async def get_health(self) -> SpaceEnvironmentHealth | None:
        return _HEALTH_SNAPSHOT

    # ── Orbit forecasts ───────────────────────────────────────

    async def save_forecast(self, forecast: OrbitForecast) -> None:
        _FORECAST_CACHE[forecast.norad_id] = forecast
        if self._redis:
            try:
                key = f"{REDIS_FORECAST_PFX}{forecast.norad_id}"
                await self._redis.setex(
                    key, REDIS_TTL_MEDIUM,
                    json.dumps(forecast.to_dict(), default=str),
                )
            except Exception as exc:
                logger.warning("redis_forecast_save_failed error=%s", exc)

    async def get_forecast(self, norad_id: int) -> OrbitForecast | None:
        return _FORECAST_CACHE.get(norad_id)

    async def list_cached_forecasts(self) -> list[int]:
        return list(_FORECAST_CACHE.keys())

    # ── Component 7: Predictive conjunction graph ─────────────

    async def upsert_future_conjunctions(
        self,
        future_conjunctions: list[dict],
    ) -> int:
        """
        Upsert FutureConjunction nodes into Neo4j.

        Each dict must have:
          conjunction_id, primary_norad, secondary_norad,
          forecast_epoch (datetime), miss_distance_km, estimated_pc,
          risk_level, confidence.
        """
        from app.graph.connection import is_available, execute_batch

        if not is_available() or not future_conjunctions:
            return 0

        CYPHER = """
        UNWIND $batch AS row
        MERGE (fc:FutureConjunction {conjunctionId: row.conjunctionId})
        SET fc.primaryNorad    = row.primaryNorad,
            fc.secondaryNorad  = row.secondaryNorad,
            fc.forecastEpoch   = datetime(row.forecastEpoch),
            fc.missDistanceKm  = row.missDistanceKm,
            fc.estimatedPc     = row.estimatedPc,
            fc.riskLevel       = row.riskLevel,
            fc.confidence      = row.confidence,
            fc.generatedAt     = datetime(row.generatedAt),
            fc.updatedAt       = datetime()
        WITH fc, row
        OPTIONAL MATCH (p:Satellite {noradId: row.primaryNorad})
        FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
            MERGE (p)-[:PREDICTED_CONJUNCTION {role: 'PRIMARY'}]->(fc)
        )
        WITH fc, row
        OPTIONAL MATCH (s:Satellite {noradId: row.secondaryNorad})
        FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
            MERGE (s)-[:PREDICTED_CONJUNCTION {role: 'SECONDARY'}]->(fc)
        )
        """

        now = datetime.now(timezone.utc).isoformat()
        batch = [
            {
                "conjunctionId":   c.get("conjunction_id"),
                "primaryNorad":    c.get("primary_norad"),
                "secondaryNorad":  c.get("secondary_norad"),
                "forecastEpoch":   c.get("forecast_epoch").isoformat() if hasattr(c.get("forecast_epoch"), "isoformat") else str(c.get("forecast_epoch")),
                "missDistanceKm":  c.get("miss_distance_km", 0),
                "estimatedPc":     c.get("estimated_pc", 0),
                "riskLevel":       c.get("risk_level", "white"),
                "confidence":      c.get("confidence", 0.5),
                "generatedAt":     now,
            }
            for c in future_conjunctions
        ]

        try:
            counters = await execute_batch(CYPHER, batch)
            logger.info(
                "future_conjunctions_upserted count=%d nodes_created=%d",
                len(batch), counters.get("nodes_created", 0),
            )
            return counters.get("nodes_created", 0)
        except Exception as exc:
            logger.error("future_conjunction_graph_failed error=%s", exc)
            return 0

    async def get_future_conjunctions(
        self,
        norad_id: int | None = None,
        min_pc: float = 1e-6,
        limit: int = 50,
    ) -> list[dict]:
        """Query future conjunction graph."""
        from app.graph.connection import is_available, execute_read

        if not is_available():
            return []

        if norad_id:
            cypher = """
            MATCH (s:Satellite {noradId: $norad})-[:PREDICTED_CONJUNCTION]->(fc:FutureConjunction)
            WHERE fc.estimatedPc >= $minPc
            RETURN fc ORDER BY fc.estimatedPc DESC LIMIT $limit
            """
            params = {"norad": norad_id, "minPc": min_pc, "limit": limit}
        else:
            cypher = """
            MATCH (fc:FutureConjunction)
            WHERE fc.estimatedPc >= $minPc
            RETURN fc ORDER BY fc.estimatedPc DESC LIMIT $limit
            """
            params = {"minPc": min_pc, "limit": limit}

        try:
            rows = await execute_read(cypher, **params)
            return [r.get("fc", {}) for r in rows]
        except Exception as exc:
            logger.error("future_conjunction_query_failed error=%s", exc)
            return []

    async def cleanup_old_forecasts(self, older_than_days: int = 7) -> int:
        """Remove stale FutureConjunction nodes from graph."""
        from app.graph.connection import is_available, execute_write

        if not is_available():
            return 0
        try:
            counters = await execute_write(
                """
                MATCH (fc:FutureConjunction)
                WHERE fc.forecastEpoch < datetime() - duration({days: $days})
                DETACH DELETE fc
                """,
                days=older_than_days,
            )
            deleted = counters.get("nodes_deleted", 0)
            logger.info("future_conjunctions_cleaned deleted=%d", deleted)
            return deleted
        except Exception as exc:
            logger.warning("cleanup_failed error=%s", exc)
            return 0
