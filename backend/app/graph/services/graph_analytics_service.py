"""
ORBITIQ-X — Graph Analytics Service
=====================================
Cypher-powered analytics queries for aerospace intelligence.

All queries return plain dicts — no ORM, no Pydantic at this layer.
The API layer converts results to response models.

Analytics categories
─────────────────────
  Operator intelligence:  top operators, risk profiles, fleet sizes
  Country intelligence:   active spacecraft by nation
  Constellation analysis: size, orbit, operator breakdown
  Conjunction risk:       high-risk networks, operator-level risk
  Launch vehicle stats:   payload history, success rates
  Orbital regime density: objects per regime
  Debris attribution:     generation chains

Performance notes
─────────────────
  All queries are read-only (execute_read).
  Indexes in 01_constraints.cypher cover all WHERE/ORDER BY fields.
  Queries that scan >10K nodes use LIMIT for safety.
  All are safe to run from the API — no write side-effects.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.graph.connection import execute_read, is_available

logger = logging.getLogger(__name__)


class GraphAnalyticsService:
    """
    Cypher-powered aerospace intelligence analytics.

    Usage::

        svc = GraphAnalyticsService()

        # Top 10 operators
        top_ops = await svc.top_operators_by_satellite_count(limit=10)

        # High-risk conjunction network
        network = await svc.conjunction_risk_network(min_pc=1e-4)
    """

    # ── Operator intelligence (Phase 9) ───────────────────────

    async def top_operators_by_satellite_count(
        self,
        limit: int = 20,
        status_filter: str | None = None,
    ) -> list[dict]:
        """
        Top operators by number of satellites they operate.

        Parameters
        ----------
        limit : int
            Maximum number of operators to return.
        status_filter : str | None
            If set, count only satellites with this status (e.g. 'operational').
        """
        if not is_available():
            return []

        where = "WHERE s.status = $status" if status_filter else ""
        params = {"limit": limit}
        if status_filter:
            params["status"] = status_filter

        return await execute_read(
            f"""
            MATCH (s:Satellite)-[:OPERATED_BY]->(op:Operator)
            {where}
            RETURN op.name AS operator,
                   count(s) AS satelliteCount,
                   collect(DISTINCT s.regime)[..3] AS regimes,
                   collect(DISTINCT s.countryCode)[0] AS countryCode
            ORDER BY satelliteCount DESC
            LIMIT $limit
            """,
            **params,
        )

    async def operator_conjunction_risk_profile(
        self,
        operator_name: str,
    ) -> dict:
        """
        Return the conjunction risk profile for a single operator.

        Aggregates Pc, miss distance, and risk level distribution
        for all satellites operated by this operator.
        """
        if not is_available():
            return {}

        rows = await execute_read(
            """
            MATCH (op:Operator {name: $name})<-[:OPERATED_BY]-(s:Satellite)
                  -[:INVOLVED_IN_CONJUNCTION]->(ce:ConjunctionEvent)
            WHERE ce.resolved = false
            RETURN op.name AS operator,
                   count(DISTINCT s) AS satellitesWithConjunctions,
                   count(ce) AS totalConjunctions,
                   max(ce.collisionProbability) AS maxPc,
                   avg(ce.missDistanceKm) AS avgMissKm,
                   count(CASE WHEN ce.riskLevel = 'red' THEN 1 END) AS redCount,
                   count(CASE WHEN ce.riskLevel = 'yellow' THEN 1 END) AS yellowCount,
                   count(CASE WHEN ce.maneuverRequired = true THEN 1 END) AS maneuverCount
            """,
            name=operator_name,
        )
        return rows[0] if rows else {}

    # ── Country intelligence ───────────────────────────────────

    async def top_countries_by_active_spacecraft(
        self,
        limit: int = 20,
    ) -> list[dict]:
        """
        Countries ranked by number of active operational spacecraft.
        """
        if not is_available():
            return []

        return await execute_read(
            """
            MATCH (s:Satellite)-[:REGISTERED_IN]->(c:Country)
            WHERE s.status = 'operational'
            RETURN c.iso2 AS countryCode,
                   c.name AS countryName,
                   count(s) AS activeSatellites,
                   collect(DISTINCT s.regime)[..4] AS regimes
            ORDER BY activeSatellites DESC
            LIMIT $limit
            """,
            limit=limit,
        )

    async def country_full_profile(self, country_code: str) -> dict:
        """
        Complete country space profile: satellites, operators,
        launch vehicles, conjunction events.
        """
        if not is_available():
            return {}

        rows = await execute_read(
            """
            MATCH (c:Country {iso2: $code})
            OPTIONAL MATCH (s:Satellite)-[:REGISTERED_IN]->(c)
            OPTIONAL MATCH (op:Operator)-[:BELONGS_TO_COUNTRY]->(c)
            OPTIONAL MATCH (ls:LaunchSite {country: $code})
            RETURN c.iso2 AS code,
                   c.name AS name,
                   count(DISTINCT s) AS totalSatellites,
                   count(DISTINCT CASE WHEN s.status='operational' THEN s END) AS activeSatellites,
                   count(DISTINCT op) AS operators,
                   count(DISTINCT ls) AS launchSites
            """,
            code=country_code,
        )
        return rows[0] if rows else {}

    # ── Constellation analysis ─────────────────────────────────

    async def largest_constellations(self, limit: int = 15) -> list[dict]:
        """
        Constellations ranked by member count, with regime and operator.
        """
        if not is_available():
            return []

        return await execute_read(
            """
            MATCH (s:Satellite)-[:MEMBER_OF_CONSTELLATION]->(c:Constellation)
            OPTIONAL MATCH (s)-[:OPERATED_BY]->(op:Operator)
            RETURN c.name AS constellation,
                   count(DISTINCT s) AS memberCount,
                   collect(DISTINCT s.regime)[0] AS primaryRegime,
                   collect(DISTINCT op.name)[0] AS operator
            ORDER BY memberCount DESC
            LIMIT $limit
            """,
            limit=limit,
        )

    async def constellation_profile(self, name: str) -> dict:
        """
        Full profile of a constellation: members, operator, orbits,
        conjunction exposure.
        """
        if not is_available():
            return {}

        rows = await execute_read(
            """
            MATCH (s:Satellite)-[:MEMBER_OF_CONSTELLATION]->(c:Constellation {name: $name})
            OPTIONAL MATCH (s)-[:OPERATED_BY]->(op:Operator)
            OPTIONAL MATCH (s)-[:LOCATED_IN_ORBIT]->(r:OrbitalRegime)
            OPTIONAL MATCH (s)-[:INVOLVED_IN_CONJUNCTION]->(ce:ConjunctionEvent)
            RETURN c.name AS constellation,
                   count(DISTINCT s) AS memberCount,
                   collect(DISTINCT op.name)[0] AS operator,
                   collect(DISTINCT r.name) AS orbits,
                   count(ce) AS totalConjunctions,
                   count(CASE WHEN ce.riskLevel IN ['red','yellow'] THEN 1 END) AS highRiskConjunctions
            """,
            name=name,
        )
        return rows[0] if rows else {}

    # ── Conjunction risk network (Phase 6) ────────────────────

    async def conjunction_risk_network(
        self,
        min_pc: float = 1e-5,
        limit: int = 200,
    ) -> list[dict]:
        """
        Return graph-ready conjunction network for visualisation.

        Each row represents one edge: (satellite1)──[conjunction]──(satellite2)
        with Pc, miss distance, and risk level on the edge.
        """
        if not is_available():
            return []

        return await execute_read(
            """
            MATCH (s1:Satellite)-[:INVOLVED_IN_CONJUNCTION {role:'PRIMARY'}]
                  ->(ce:ConjunctionEvent)
                  <-[:INVOLVED_IN_CONJUNCTION {role:'SECONDARY'}]-(s2:Satellite)
            WHERE ce.collisionProbability >= $minPc
            RETURN s1.noradId AS norad1, s1.name AS name1,
                   s2.noradId AS norad2, s2.name AS name2,
                   ce.conjunctionId AS conjunctionId,
                   ce.collisionProbability AS Pc,
                   ce.missDistanceKm AS missKm,
                   ce.riskLevel AS riskLevel,
                   ce.tca AS tca,
                   ce.resolved AS resolved
            ORDER BY ce.collisionProbability DESC
            LIMIT $limit
            """,
            minPc=min_pc,
            limit=limit,
        )

    async def top_operators_by_conjunction_risk(
        self, limit: int = 10
    ) -> list[dict]:
        """
        Rank operators by their total unresolved conjunction exposure.
        """
        if not is_available():
            return []

        return await execute_read(
            """
            MATCH (op:Operator)<-[:OPERATED_BY]-(s:Satellite)
                  -[:INVOLVED_IN_CONJUNCTION]->(ce:ConjunctionEvent)
            WHERE ce.resolved = false
            RETURN op.name AS operator,
                   count(DISTINCT ce) AS unresolved,
                   max(ce.collisionProbability) AS maxPc,
                   count(CASE WHEN ce.riskLevel = 'red' THEN 1 END) AS redEvents
            ORDER BY maxPc DESC
            LIMIT $limit
            """,
            limit=limit,
        )

    # ── Launch vehicle analytics (Phase 5) ────────────────────

    async def launch_vehicle_payload_history(
        self, vehicle_id: str
    ) -> list[dict]:
        """
        All satellites launched by a specific vehicle.
        """
        if not is_available():
            return []

        return await execute_read(
            """
            MATCH (s:Satellite)-[:LAUNCHED_BY]->(lv:LaunchVehicle {vehicleId: $vid})
            OPTIONAL MATCH (lv)-[:LAUNCHES_FROM]->(ls:LaunchSite)
            RETURN s.noradId AS noradId, s.name AS name,
                   s.launchDate AS launchDate, s.status AS status,
                   s.regime AS regime, ls.name AS launchSite
            ORDER BY s.launchDate DESC
            LIMIT 500
            """,
            vid=vehicle_id,
        )

    # ── Orbital regime density (Phase 7) ──────────────────────

    async def orbital_regime_density(self) -> list[dict]:
        """
        Count of objects per orbital regime, broken down by type.
        """
        if not is_available():
            return []

        return await execute_read(
            """
            MATCH (s:Satellite)-[:LOCATED_IN_ORBIT]->(r:OrbitalRegime)
            RETURN r.orbitId AS regimeId,
                   r.name AS regime,
                   r.altMinKm AS altMinKm,
                   r.altMaxKm AS altMaxKm,
                   count(s) AS totalObjects,
                   count(CASE WHEN s.objectType = 'satellite' THEN 1 END) AS satellites,
                   count(CASE WHEN s.objectType = 'debris' THEN 1 END) AS debris,
                   count(CASE WHEN s.objectType = 'rocket_body' THEN 1 END) AS rocketBodies
            ORDER BY r.altMinKm
            """
        )

    # ── Graph summary (for dashboards) ───────────────────────

    async def graph_summary(self) -> dict:
        """
        High-level node/relationship counts for the graph overview dashboard.
        """
        if not is_available():
            return {"available": False}

        rows = await execute_read(
            """
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS cnt
            ORDER BY cnt DESC
            """
        )
        counts = {r["label"]: r["cnt"] for r in rows if r["label"]}

        rel_rows = await execute_read(
            """
            MATCH ()-[r]->()
            RETURN type(r) AS relType, count(r) AS cnt
            ORDER BY cnt DESC
            LIMIT 20
            """
        )
        rels = {r["relType"]: r["cnt"] for r in rel_rows}

        return {
            "available":     True,
            "node_counts":   counts,
            "rel_counts":    rels,
            "total_nodes":   sum(counts.values()),
            "total_rels":    sum(rels.values()),
            "checked_at":    datetime.now(timezone.utc).isoformat(),
        }

    # ── Mission dependency chain (Phase 4) ────────────────────

    async def mission_profile(self, mission_id: str) -> dict:
        """
        Full mission profile: satellites, agency, launch vehicles, sites.
        """
        if not is_available():
            return {}

        rows = await execute_read(
            """
            MATCH (m:Mission {missionId: $mid})
            OPTIONAL MATCH (s:Satellite)-[:PART_OF_MISSION]->(m)
            OPTIONAL MATCH (m)-[:ASSOCIATED_WITH]->(a:Agency)
            OPTIONAL MATCH (s)-[:LAUNCHED_BY]->(lv:LaunchVehicle)
            OPTIONAL MATCH (lv)-[:LAUNCHES_FROM]->(ls:LaunchSite)
            RETURN m.missionId AS missionId,
                   m.name AS name,
                   m.status AS status,
                   m.missionType AS type,
                   collect(DISTINCT s.name) AS satellites,
                   collect(DISTINCT a.name) AS agencies,
                   collect(DISTINCT lv.name) AS launchVehicles,
                   collect(DISTINCT ls.name) AS launchSites
            """,
            mid=mission_id,
        )
        return rows[0] if rows else {}
