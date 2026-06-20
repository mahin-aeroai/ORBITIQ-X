"""
ORBITIQ-X — Aerospace Knowledge Graph Repository
==================================================
Graph repository layer for node and relationship CRUD.

Aerospace Ontology (Phases 2–7)
─────────────────────────────────
Node labels:
  Satellite        — RSO (payload, debris, rocket body)
  Operator         — Commercial / government / military operator
  Country          — Nation-state (ISO codes)
  Agency           — Space agency (NASA, ESA, ISRO, JAXA, CNSA…)
  Mission          — Programmatic mission entity
  LaunchVehicle    — Rocket / launch system
  LaunchSite       — Ground facility
  Constellation    — Satellite constellation (Starlink, OneWeb, GPS…)
  DebrisObject     — Catalogued debris / fragmentation event product
  ConjunctionEvent — SSA conjunction CDM record
  OrbitalRegime    — Orbital regime (LEO/MEO/GEO/HEO/Cislunar/DSO)
  SpacecraftClass  — Spacecraft bus/platform class

Relationship types:
  OPERATED_BY            Satellite → Operator
  OWNED_BY               Satellite → Country (launch country)
  BELONGS_TO_COUNTRY     Operator  → Country
  PART_OF_MISSION        Satellite → Mission
  LAUNCHED_BY            Satellite → LaunchVehicle
  LAUNCHED_FROM          LaunchVehicle → LaunchSite
  MEMBER_OF_CONSTELLATION Satellite → Constellation
  INVOLVED_IN_CONJUNCTION Satellite → ConjunctionEvent (PRIMARY/SECONDARY)
  GENERATED_DEBRIS       Satellite → DebrisObject
  LOCATED_IN_ORBIT       Satellite → OrbitalRegime
  ASSOCIATED_WITH        Mission → Agency

Audit notes
────────────
  - graph_loader.py writes Satellite, Country, ConjunctionEvent nodes
    using MERGE — idempotent. This repository adds the full ontology.
  - execute_batch() from connection.py handles all UNWIND batching.
  - All Cypher uses MERGE (not CREATE) to be idempotent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.graph.connection import (
    execute_batch,
    execute_read,
    execute_write,
    is_available,
)

logger = logging.getLogger(__name__)


# ── Orbital regime seed data ──────────────────────────────────

ORBITAL_REGIMES = [
    {
        "orbitId":       "LEO",
        "name":          "Low Earth Orbit",
        "altMinKm":      160,
        "altMaxKm":      2000,
        "description":   "160–2000 km. High atmospheric drag. ISS, Starlink, Sentinel.",
        "periodMinutes": 90,
    },
    {
        "orbitId":       "SSO",
        "name":          "Sun-Synchronous Orbit",
        "altMinKm":      400,
        "altMaxKm":      1000,
        "description":   "Near-polar LEO with fixed solar angle. Remote sensing.",
        "periodMinutes": 100,
    },
    {
        "orbitId":       "MEO",
        "name":          "Medium Earth Orbit",
        "altMinKm":      2000,
        "altMaxKm":      35786,
        "description":   "2000–35786 km. GPS, GLONASS, Galileo, BeiDou.",
        "periodMinutes": 720,
    },
    {
        "orbitId":       "GEO",
        "name":          "Geostationary Orbit",
        "altMinKm":      35786,
        "altMaxKm":      35786,
        "description":   "35786 km. Fixed apparent position. Comms, weather.",
        "periodMinutes": 1436,
    },
    {
        "orbitId":       "HEO",
        "name":          "Highly Elliptical Orbit",
        "altMinKm":      500,
        "altMaxKm":      50000,
        "description":   "High eccentricity. Molniya, Tundra. Arctic comms.",
        "periodMinutes": 720,
    },
    {
        "orbitId":       "GTO",
        "name":          "Geostationary Transfer Orbit",
        "altMinKm":      200,
        "altMaxKm":      35786,
        "description":   "Elliptical transfer orbit to GEO.",
        "periodMinutes": 630,
    },
    {
        "orbitId":       "VLEO",
        "name":          "Very Low Earth Orbit",
        "altMinKm":      160,
        "altMaxKm":      450,
        "description":   "<450 km. High drag, short lifetime. SpaceX VLEO research.",
        "periodMinutes": 90,
    },
    {
        "orbitId":       "CISLUNAR",
        "name":          "Cislunar Space",
        "altMinKm":      384000,
        "altMaxKm":      400000,
        "description":   "Earth-Moon system. Artemis Gateway. Lunar orbit.",
        "periodMinutes": 39600,
    },
    {
        "orbitId":       "DSO",
        "name":          "Deep Space Orbit",
        "altMinKm":      400000,
        "altMaxKm":      999999999,
        "description":   "Beyond Earth-Moon system. Mars, asteroid missions.",
        "periodMinutes": -1,
    },
]


# ── Seed data: launch vehicles ────────────────────────────────

LAUNCH_VEHICLES = [
    {"vehicleId": "LV-PSLV",        "name": "PSLV",              "operator": "ISRO",        "country": "IN", "status": "active",  "payloadLeoKg": 3800},
    {"vehicleId": "LV-GSLV-MK3",    "name": "GSLV Mk III (LVM3)","operator": "ISRO",        "country": "IN", "status": "active",  "payloadLeoKg": 10000},
    {"vehicleId": "LV-FALCON9",      "name": "Falcon 9",          "operator": "SpaceX",      "country": "US", "status": "active",  "payloadLeoKg": 22800},
    {"vehicleId": "LV-FALCON-HEAVY", "name": "Falcon Heavy",      "operator": "SpaceX",      "country": "US", "status": "active",  "payloadLeoKg": 63800},
    {"vehicleId": "LV-STARSHIP",     "name": "Starship",          "operator": "SpaceX",      "country": "US", "status": "active",  "payloadLeoKg": 150000},
    {"vehicleId": "LV-ARIANE5",      "name": "Ariane 5",          "operator": "ArianeGroup", "country": "FR", "status": "retired", "payloadLeoKg": 21000},
    {"vehicleId": "LV-ARIANE6",      "name": "Ariane 6",          "operator": "ArianeGroup", "country": "FR", "status": "active",  "payloadLeoKg": 21650},
    {"vehicleId": "LV-SOYUZ",        "name": "Soyuz",             "operator": "Roscosmos",   "country": "RU", "status": "active",  "payloadLeoKg": 7000},
    {"vehicleId": "LV-LM-2C",        "name": "Long March 2C",     "operator": "CASC",        "country": "CN", "status": "active",  "payloadLeoKg": 3850},
    {"vehicleId": "LV-LM-5",         "name": "Long March 5",      "operator": "CASC",        "country": "CN", "status": "active",  "payloadLeoKg": 25000},
    {"vehicleId": "LV-ELECTRON",     "name": "Electron",          "operator": "RocketLab",   "country": "NZ", "status": "active",  "payloadLeoKg": 300},
    {"vehicleId": "LV-VEGA",         "name": "Vega-C",            "operator": "ArianeGroup", "country": "IT", "status": "active",  "payloadLeoKg": 2300},
    {"vehicleId": "LV-VULCAN",       "name": "Vulcan Centaur",    "operator": "ULA",         "country": "US", "status": "active",  "payloadLeoKg": 27200},
    {"vehicleId": "LV-H3",           "name": "H3",                "operator": "JAXA",        "country": "JP", "status": "active",  "payloadLeoKg": 6500},
    {"vehicleId": "LV-NEWGLENN",     "name": "New Glenn",         "operator": "BlueOrigin",  "country": "US", "status": "active",  "payloadLeoKg": 45000},
]


# ── Seed data: launch sites ───────────────────────────────────

LAUNCH_SITES = [
    {"siteId": "LS-SDSC",    "name": "Satish Dhawan Space Centre", "country": "IN", "lat":  13.733, "lon":  80.235},
    {"siteId": "LS-KSC",     "name": "Kennedy Space Center",       "country": "US", "lat":  28.524, "lon": -80.651},
    {"siteId": "LS-VAFB",    "name": "Vandenberg SFB",             "country": "US", "lat":  34.753, "lon": -120.524},
    {"siteId": "LS-CANAVERAL","name": "Cape Canaveral SFS",        "country": "US", "lat":  28.474, "lon": -80.577},
    {"siteId": "LS-KOUROU",  "name": "Guiana Space Centre (Kourou)","country": "FR","lat":   5.239, "lon": -52.769},
    {"siteId": "LS-BAIKONUR","name": "Baikonur Cosmodrome",        "country": "KZ", "lat":  45.920, "lon":  63.342},
    {"siteId": "LS-PLESETSK","name": "Plesetsk Cosmodrome",        "country": "RU", "lat":  62.927, "lon":  40.577},
    {"siteId": "LS-JIUQUAN", "name": "Jiuquan Satellite Launch Center","country":"CN","lat":  40.958,"lon": 100.291},
    {"siteId": "LS-XICHANG", "name": "Xichang Satellite Launch Center","country":"CN","lat": 28.246,"lon": 102.027},
    {"siteId": "LS-TANEGASHIMA","name":"Tanegashima Space Center", "country": "JP", "lat":  30.400, "lon": 130.975},
    {"siteId": "LS-MAHIA",   "name": "Mahia Launch Complex",       "country": "NZ", "lat": -39.262, "lon": 177.864},
    {"siteId": "LS-WALLOPS", "name": "Wallops Flight Facility",    "country": "US", "lat":  37.940, "lon": -75.466},
]


# ── Seed data: agencies ───────────────────────────────────────

AGENCIES = [
    {"agencyId": "AGY-NASA",       "name": "NASA",   "fullName": "National Aeronautics and Space Administration", "country": "US", "type": "civil"},
    {"agencyId": "AGY-ESA",        "name": "ESA",    "fullName": "European Space Agency",                         "country": "EU", "type": "civil"},
    {"agencyId": "AGY-ISRO",       "name": "ISRO",   "fullName": "Indian Space Research Organisation",            "country": "IN", "type": "civil"},
    {"agencyId": "AGY-ROSCOSMOS",  "name": "Roscosmos","fullName": "State Space Corporation Roscosmos",          "country": "RU", "type": "civil"},
    {"agencyId": "AGY-CNSA",       "name": "CNSA",   "fullName": "China National Space Administration",           "country": "CN", "type": "civil"},
    {"agencyId": "AGY-JAXA",       "name": "JAXA",   "fullName": "Japan Aerospace Exploration Agency",            "country": "JP", "type": "civil"},
    {"agencyId": "AGY-CNES",       "name": "CNES",   "fullName": "Centre National d'Études Spatiales",           "country": "FR", "type": "civil"},
    {"agencyId": "AGY-DLR",        "name": "DLR",    "fullName": "Deutsches Zentrum für Luft- und Raumfahrt",    "country": "DE", "type": "civil"},
    {"agencyId": "AGY-ASI",        "name": "ASI",    "fullName": "Agenzia Spaziale Italiana",                    "country": "IT", "type": "civil"},
    {"agencyId": "AGY-UKSA",       "name": "UKSA",   "fullName": "UK Space Agency",                              "country": "GB", "type": "civil"},
    {"agencyId": "AGY-USSPACECOM", "name": "USSPACECOM","fullName": "United States Space Command",               "country": "US", "type": "military"},
    {"agencyId": "AGY-KARI",       "name": "KARI",   "fullName": "Korea Aerospace Research Institute",           "country": "KR", "type": "civil"},
    {"agencyId": "AGY-UAE-SA",     "name": "UAESA",  "fullName": "UAE Space Agency",                             "country": "AE", "type": "civil"},
    {"agencyId": "AGY-ISRAE",      "name": "ISA",    "fullName": "Israel Space Agency",                          "country": "IL", "type": "civil"},
]


# ── Node repositories ─────────────────────────────────────────

class OrbitalRegimeRepository:
    """Manage OrbitalRegime nodes — Phase 7."""

    UPSERT_CYPHER = """
    UNWIND $batch AS row
    MERGE (r:OrbitalRegime {orbitId: row.orbitId})
    SET r.name          = row.name,
        r.altMinKm      = row.altMinKm,
        r.altMaxKm      = row.altMaxKm,
        r.description   = row.description,
        r.periodMinutes = row.periodMinutes,
        r.updatedAt     = datetime()
    """

    async def seed(self) -> int:
        if not is_available():
            return 0
        counters = await execute_batch(self.UPSERT_CYPHER, ORBITAL_REGIMES)
        logger.info("orbital_regime_seed nodes=%d", counters["nodes_created"])
        return counters["nodes_created"]

    async def get_all(self) -> list[dict]:
        if not is_available():
            return []
        return await execute_read("MATCH (r:OrbitalRegime) RETURN r ORDER BY r.altMinKm")

    async def get_by_id(self, orbit_id: str) -> dict | None:
        if not is_available():
            return None
        rows = await execute_read(
            "MATCH (r:OrbitalRegime {orbitId: $orbitId}) RETURN r",
            orbitId=orbit_id,
        )
        return rows[0]["r"] if rows else None


class LaunchVehicleRepository:
    """Manage LaunchVehicle nodes — Phase 5."""

    UPSERT_CYPHER = """
    UNWIND $batch AS row
    MERGE (lv:LaunchVehicle {vehicleId: row.vehicleId})
    SET lv.name          = row.name,
        lv.operator      = row.operator,
        lv.country       = row.country,
        lv.status        = row.status,
        lv.payloadLeoKg  = row.payloadLeoKg,
        lv.updatedAt     = datetime()
    """

    SITE_LINK_CYPHER = """
    UNWIND $batch AS row
    MATCH (lv:LaunchVehicle {vehicleId: row.vehicleId})
    MATCH (ls:LaunchSite {siteId: row.siteId})
    MERGE (lv)-[:LAUNCHES_FROM]->(ls)
    """

    async def seed(self) -> int:
        if not is_available():
            return 0
        counters = await execute_batch(self.UPSERT_CYPHER, LAUNCH_VEHICLES)
        logger.info("launch_vehicle_seed nodes=%d", counters["nodes_created"])
        return counters["nodes_created"]

    async def get_by_id(self, vehicle_id: str) -> dict | None:
        if not is_available():
            return None
        rows = await execute_read(
            """
            MATCH (lv:LaunchVehicle {vehicleId: $vid})
            OPTIONAL MATCH (lv)-[:LAUNCHES_FROM]->(ls:LaunchSite)
            RETURN lv, collect(ls) AS sites
            """,
            vid=vehicle_id,
        )
        return rows[0] if rows else None

    async def get_all(self) -> list[dict]:
        if not is_available():
            return []
        return await execute_read("MATCH (lv:LaunchVehicle) RETURN lv ORDER BY lv.name")


class LaunchSiteRepository:
    """Manage LaunchSite nodes."""

    UPSERT_CYPHER = """
    UNWIND $batch AS row
    MERGE (ls:LaunchSite {siteId: row.siteId})
    SET ls.name      = row.name,
        ls.country   = row.country,
        ls.latitude  = row.lat,
        ls.longitude = row.lon,
        ls.updatedAt = datetime()
    """

    async def seed(self) -> int:
        if not is_available():
            return 0
        counters = await execute_batch(self.UPSERT_CYPHER, LAUNCH_SITES)
        return counters["nodes_created"]


class AgencyRepository:
    """Manage Agency nodes."""

    UPSERT_CYPHER = """
    UNWIND $batch AS row
    MERGE (a:Agency {agencyId: row.agencyId})
    SET a.name      = row.name,
        a.fullName  = row.fullName,
        a.country   = row.country,
        a.type      = row.type,
        a.updatedAt = datetime()
    """

    async def seed(self) -> int:
        if not is_available():
            return 0
        counters = await execute_batch(self.UPSERT_CYPHER, AGENCIES)
        return counters["nodes_created"]

    async def get_by_name(self, name: str) -> list[dict]:
        if not is_available():
            return []
        return await execute_read(
            """
            MATCH (a:Agency)
            WHERE toLower(a.name) CONTAINS toLower($name)
               OR toLower(a.fullName) CONTAINS toLower($name)
            RETURN a LIMIT 10
            """,
            name=name,
        )


class SatelliteGraphRepository:
    """
    Satellite graph node management — Phase 3.

    Bridges the PostgreSQL satellites table → Neo4j :Satellite nodes.
    Uses execute_batch() for efficient UNWIND upserts.
    Relationship creation is separate from node creation.
    """

    UPSERT_CYPHER = """
    UNWIND $batch AS row
    MERGE (s:Satellite {noradId: row.noradId})
    SET s.cosparId      = row.cosparId,
        s.name          = row.name,
        s.objectType    = row.objectType,
        s.status        = row.status,
        s.regime        = row.regime,
        s.missionType   = row.missionType,
        s.perigeeKm     = row.perigeeKm,
        s.apogeeKm      = row.apogeeKm,
        s.inclinationDeg= row.inclinationDeg,
        s.periodMinutes = row.periodMinutes,
        s.massKg        = row.massKg,
        s.launchDate    = CASE WHEN row.launchDate IS NOT NULL THEN date(row.launchDate) ELSE null END,
        s.launchSite    = row.launchSite,
        s.launchVehicle = row.launchVehicle,
        s.constellation = row.constellation,
        s.countryCode   = row.countryCode,
        s.operatorName  = row.operatorName,
        s.tleLine1      = row.tleLine1,
        s.tleLine2      = row.tleLine2,
        s.tleEpoch      = CASE WHEN row.tleEpoch IS NOT NULL THEN datetime(row.tleEpoch) ELSE null END,
        s.tleAgeDays    = row.tleAgeDays,
        s.updatedAt     = datetime()
    """

    ORBIT_REL_CYPHER = """
    UNWIND $batch AS row
    MATCH (s:Satellite {noradId: row.noradId})
    WHERE row.regime IS NOT NULL
    MATCH (r:OrbitalRegime {orbitId: row.regime})
    MERGE (s)-[:LOCATED_IN_ORBIT]->(r)
    """

    CONSTELLATION_CYPHER = """
    UNWIND $batch AS row
    MATCH (s:Satellite {noradId: row.noradId})
    WHERE row.constellation IS NOT NULL AND row.constellation <> ''
    MERGE (c:Constellation {constellationId: row.constellation})
    ON CREATE SET c.name = row.constellation, c.createdAt = datetime()
    MERGE (s)-[:MEMBER_OF_CONSTELLATION]->(c)
    """

    COUNTRY_REL_CYPHER = """
    UNWIND $batch AS row
    MATCH (s:Satellite {noradId: row.noradId})
    WHERE row.countryCode IS NOT NULL
    MERGE (c:Country {iso2: row.countryCode})
    ON CREATE SET c.name = row.countryCode
    MERGE (s)-[:REGISTERED_IN]->(c)
    """

    OPERATOR_REL_CYPHER = """
    UNWIND $batch AS row
    MATCH (s:Satellite {noradId: row.noradId})
    WHERE row.operatorName IS NOT NULL AND row.operatorName <> ''
    MERGE (op:Operator {name: row.operatorName})
    ON CREATE SET op.createdAt = datetime()
    MERGE (s)-[:OPERATED_BY]->(op)
    """

    async def upsert_satellites(self, satellites: list[dict]) -> dict:
        """Upsert satellite nodes from PostgreSQL satellite records."""
        if not is_available() or not satellites:
            return {"nodes_created": 0}

        # Build graph-compatible records
        graph_records = []
        for sat in satellites:
            tca_epoch = sat.get("tle_epoch")
            graph_records.append({
                "noradId":       sat.get("norad_id"),
                "cosparId":      sat.get("cospar_id"),
                "name":          sat.get("name", "UNKNOWN"),
                "objectType":    sat.get("object_type", "unknown"),
                "status":        sat.get("status", "unknown"),
                "regime":        sat.get("regime"),
                "missionType":   sat.get("mission_type"),
                "perigeeKm":     sat.get("perigee_km"),
                "apogeeKm":      sat.get("apogee_km"),
                "inclinationDeg":sat.get("inclination_deg"),
                "periodMinutes": sat.get("period_minutes"),
                "massKg":        sat.get("mass_kg"),
                "launchDate":    sat.get("launch_date").isoformat() if sat.get("launch_date") else None,
                "launchSite":    sat.get("launch_site"),
                "launchVehicle": sat.get("launch_vehicle"),
                "constellation": sat.get("constellation"),
                "countryCode":   sat.get("country_code"),
                "operatorName":  sat.get("operator_name"),
                "tleLine1":      sat.get("tle_line1"),
                "tleLine2":      sat.get("tle_line2"),
                "tleEpoch":      tca_epoch.isoformat() if tca_epoch else None,
                "tleAgeDays":    sat.get("tle_age_days"),
            })

        counters = await execute_batch(self.UPSERT_CYPHER, graph_records)
        logger.info(
            "satellite_graph_upsert count=%d nodes_created=%d",
            len(satellites), counters["nodes_created"],
        )

        # Wire relationships in parallel batches
        orbit_batch = [r for r in graph_records if r.get("regime")]
        if orbit_batch:
            await execute_batch(self.ORBIT_REL_CYPHER, orbit_batch)

        constellation_batch = [r for r in graph_records if r.get("constellation")]
        if constellation_batch:
            await execute_batch(self.CONSTELLATION_CYPHER, constellation_batch)

        country_batch = [r for r in graph_records if r.get("countryCode")]
        if country_batch:
            await execute_batch(self.COUNTRY_REL_CYPHER, country_batch)

        operator_batch = [r for r in graph_records if r.get("operatorName")]
        if operator_batch:
            await execute_batch(self.OPERATOR_REL_CYPHER, operator_batch)

        return counters

    async def get_satellite(self, norad_id: int) -> dict | None:
        """Fetch full satellite subgraph: node + all immediate relationships."""
        if not is_available():
            return None
        rows = await execute_read(
            """
            MATCH (s:Satellite {noradId: $noradId})
            OPTIONAL MATCH (s)-[:OPERATED_BY]->(op:Operator)
            OPTIONAL MATCH (s)-[:REGISTERED_IN]->(c:Country)
            OPTIONAL MATCH (s)-[:LOCATED_IN_ORBIT]->(r:OrbitalRegime)
            OPTIONAL MATCH (s)-[:MEMBER_OF_CONSTELLATION]->(con:Constellation)
            OPTIONAL MATCH (s)-[:LAUNCHED_BY]->(lv:LaunchVehicle)
            OPTIONAL MATCH (s)-[rel:INVOLVED_IN_CONJUNCTION]->(ce:ConjunctionEvent)
            RETURN s,
                   op.name        AS operatorName,
                   c.name         AS countryName,
                   r.name         AS orbitName,
                   con.name       AS constellation,
                   lv.name        AS launchVehicle,
                   count(ce)      AS conjunctionCount
            """,
            noradId=norad_id,
        )
        return rows[0] if rows else None

    async def search_satellites(
        self,
        query: str,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search across satellite names."""
        if not is_available():
            return []
        return await execute_read(
            """
            CALL db.index.fulltext.queryNodes('satellite_fulltext', $query)
            YIELD node, score
            RETURN node AS s, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            query=query,
            limit=limit,
        )


class ConjunctionGraphRepository:
    """
    Conjunction intelligence graph — Phase 6.

    Syncs ConjunctionEvent nodes from PostgreSQL to Neo4j and
    wires them to the primary and secondary Satellite nodes.
    """

    UPSERT_CYPHER = """
    UNWIND $batch AS row
    MERGE (ce:ConjunctionEvent {conjunctionId: row.conjunctionId})
    SET ce.tca                  = datetime(row.tca),
        ce.missDistanceKm       = row.missDistanceKm,
        ce.missDistanceM        = row.missDistanceKm * 1000,
        ce.collisionProbability = row.collisionProbability,
        ce.relativeVelocityKms  = row.relativeVelocityKms,
        ce.riskLevel            = row.riskLevel,
        ce.maneuverRequired     = row.maneuverRequired,
        ce.resolved             = row.resolved,
        ce.screeningOrg         = row.screeningOrg,
        ce.updatedAt            = datetime()
    WITH ce, row
    OPTIONAL MATCH (primary:Satellite {noradId: row.primaryNorad})
    FOREACH (s IN CASE WHEN primary IS NOT NULL THEN [primary] ELSE [] END |
      MERGE (s)-[:INVOLVED_IN_CONJUNCTION {role: 'PRIMARY'}]->(ce)
    )
    WITH ce, row
    OPTIONAL MATCH (secondary:Satellite {noradId: row.secondaryNorad})
    FOREACH (s IN CASE WHEN secondary IS NOT NULL THEN [secondary] ELSE [] END |
      MERGE (s)-[:INVOLVED_IN_CONJUNCTION {role: 'SECONDARY'}]->(ce)
    )
    """

    async def upsert_conjunctions(self, conjunctions: list[dict]) -> dict:
        """Sync conjunction events from PostgreSQL CDM archive to graph."""
        if not is_available() or not conjunctions:
            return {"nodes_created": 0}

        graph_records = []
        for c in conjunctions:
            tca = c.get("tca")
            graph_records.append({
                "conjunctionId":       c.get("conjunction_id"),
                "tca":                 tca.isoformat() if tca else None,
                "missDistanceKm":      c.get("miss_distance_km", 0),
                "collisionProbability":c.get("collision_probability", 0),
                "relativeVelocityKms": c.get("relative_velocity_kms", 0),
                "riskLevel":           c.get("risk_level", "white"),
                "maneuverRequired":    c.get("maneuver_required", False),
                "resolved":            c.get("resolved", False),
                "screeningOrg":        c.get("screening_org", "ORBITIQ-X"),
                "primaryNorad":        c.get("primary_norad"),
                "secondaryNorad":      c.get("secondary_norad"),
            })

        counters = await execute_batch(self.UPSERT_CYPHER, graph_records)
        logger.info(
            "conjunction_graph_upsert count=%d nodes_created=%d",
            len(conjunctions), counters["nodes_created"],
        )
        return counters

    async def get_conjunctions_for_satellite(
        self,
        norad_id: int,
        limit: int = 50,
    ) -> list[dict]:
        """Return all conjunction events involving a satellite."""
        if not is_available():
            return []
        return await execute_read(
            """
            MATCH (s:Satellite {noradId: $noradId})-[rel:INVOLVED_IN_CONJUNCTION]->(ce:ConjunctionEvent)
            OPTIONAL MATCH (other:Satellite)-[:INVOLVED_IN_CONJUNCTION]->(ce)
            WHERE other.noradId <> $noradId
            RETURN ce, rel.role AS role, other.name AS counterpartName,
                   other.noradId AS counterpartNorad
            ORDER BY ce.tca DESC
            LIMIT $limit
            """,
            noradId=norad_id,
            limit=limit,
        )

    async def get_high_risk_network(self, min_pc: float = 1e-4) -> list[dict]:
        """Return the high-risk conjunction network for graph visualisation."""
        if not is_available():
            return []
        return await execute_read(
            """
            MATCH (s1:Satellite)-[:INVOLVED_IN_CONJUNCTION {role:'PRIMARY'}]->(ce:ConjunctionEvent)
                  <-[:INVOLVED_IN_CONJUNCTION {role:'SECONDARY'}]-(s2:Satellite)
            WHERE ce.collisionProbability >= $minPc AND ce.resolved = false
            RETURN s1.noradId AS norad1, s1.name AS name1,
                   s2.noradId AS norad2, s2.name AS name2,
                   ce.conjunctionId, ce.collisionProbability AS Pc,
                   ce.missDistanceKm AS missKm, ce.riskLevel, ce.tca
            ORDER BY ce.collisionProbability DESC
            LIMIT 100
            """,
            minPc=min_pc,
        )
