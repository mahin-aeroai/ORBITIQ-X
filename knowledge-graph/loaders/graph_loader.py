"""
ORBITIQ-X Aerospace Knowledge Graph
Graph Loading Architecture

Pipeline:
    Source APIs → Normalization → Batch MERGE → Index Warm-up

Sources:
    - Space-Track.org   : Satellite catalog + TLE
    - CelesTrak          : Supplemental catalog, active sats
    - 18 SWS / LeoLabs  : CDM conjunction events
    - NASA NeoWS         : Near-Earth objects (optional)
    - ESA DISCOS         : Launch vehicle + site registry
    - arXiv / NASA ADS   : Research papers
    - NOAA SWPC          : Space weather events
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any

import httpx
from neo4j import AsyncGraphDatabase, AsyncDriver
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "orbitiq"

CELESTRAK_ACTIVE = "https://celestrak.org/SOCRATES/query.php?CATALOG=active&FORMAT=json"
CELESTRAK_DEBRIS  = "https://celestrak.org/SOCRATES/query.php?CATALOG=debris&FORMAT=json"
SPACETRACK_BASE   = "https://www.space-track.org"


# ── Data Models ───────────────────────────────────────────────

@dataclass
class SatelliteRecord:
    norad_id: int
    cospar_id: str
    name: str
    object_type: str
    launch_date: date | None
    country_code: str
    status: str
    purpose: str | None = None
    mass_kg: float | None = None
    altitude_km: float | None = None
    inclination: float | None = None
    tle_line1: str | None = None
    tle_line2: str | None = None


@dataclass
class ConjunctionRecord:
    conjunction_id: str
    tca: datetime
    miss_distance_km: float
    collision_probability: float
    relative_velocity_kms: float
    primary_norad: int
    secondary_norad: int
    screening_org: str = "18 SWS"
    risk_level: str = "green"
    maneuver_required: bool = False


# ── Batch Writer ──────────────────────────────────────────────

class Neo4jBatchWriter:
    """
    Writes nodes and relationships in batches.
    Uses MERGE + SET for idempotent upserts.
    Batch size of 500-1000 balances tx overhead vs memory.
    """

    BATCH_SIZE = 500

    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    async def write_satellites(self, records: list[SatelliteRecord]) -> int:
        """MERGE satellite nodes. Returns count written."""
        written = 0
        for chunk in self._chunks(records):
            params = [self._sat_to_params(r) for r in chunk]
            cypher = """
            UNWIND $batch AS row
            MERGE (s:Satellite {noradId: row.noradId})
            SET s.cosparId             = row.cosparId,
                s.name                 = row.name,
                s.status               = row.status,
                s.launchDate           = date(row.launchDate),
                s.altitudeKm           = row.altitudeKm,
                s.inclination          = row.inclination,
                s.massKg               = row.massKg,
                s.tle_line1            = row.tleLine1,
                s.tle_line2            = row.tleLine2,
                s.tle_epoch            = datetime(),
                s.updatedAt            = datetime()
            WITH s, row
            MERGE (c:Country {iso2: row.countryCode})
            MERGE (s)-[:REGISTERED_IN]->(c)
            """
            async with self.driver.session() as session:
                result = await session.run(cypher, batch=params)
                summary = await result.consume()
                written += summary.counters.nodes_created
        return written

    async def write_conjunctions(self, records: list[ConjunctionRecord]) -> int:
        """MERGE conjunction events and link to primary/secondary objects."""
        written = 0
        for chunk in self._chunks(records):
            params = [self._cdm_to_params(r) for r in chunk]
            cypher = """
            UNWIND $batch AS row
            MERGE (ce:ConjunctionEvent {conjunctionId: row.conjunctionId})
            SET ce.tca                  = datetime(row.tca),
                ce.missDistanceKm       = row.missDistanceKm,
                ce.collisionProbability = row.collisionProbability,
                ce.relativeVelocityKms  = row.relativeVelocityKms,
                ce.riskLevel            = row.riskLevel,
                ce.screeningOrg         = row.screeningOrg,
                ce.maneuverRequired     = row.maneuverRequired,
                ce.resolved             = false,
                ce.updatedAt            = datetime()
            WITH ce, row
            MATCH (primary {noradId: row.primaryNorad})
            MERGE (primary)-[:PRIMARY_IN]->(ce)
            WITH ce, row
            OPTIONAL MATCH (secondary {noradId: row.secondaryNorad})
            FOREACH (s IN CASE WHEN secondary IS NOT NULL THEN [secondary] ELSE [] END |
              MERGE (s)-[:SECONDARY_IN]->(ce)
            )
            """
            async with self.driver.session() as session:
                result = await session.run(cypher, batch=params)
                summary = await result.consume()
                written += summary.counters.nodes_created
        return written

    async def write_launch_links(
        self,
        links: list[dict[str, Any]]
    ) -> int:
        """Link satellites to launch vehicles and sites."""
        cypher = """
        UNWIND $batch AS row
        MATCH (s:Satellite {noradId: row.noradId})
        MERGE (lv:LaunchVehicle {vehicleId: row.vehicleId})
        ON CREATE SET lv.name = row.vehicleName
        MERGE (s)-[:LAUNCHED_BY {
          launchDate: date(row.launchDate),
          missionSuccess: row.success
        }]->(lv)
        WITH s, lv, row
        MERGE (ls:LaunchSite {siteId: row.siteId})
        ON CREATE SET ls.name = row.siteName
        MERGE (lv)-[:LAUNCHES_FROM]->(ls)
        """
        async with self.driver.session() as session:
            for chunk in self._chunks(links):
                await session.run(cypher, batch=chunk)
        return len(links)

    def _chunks(self, lst: list, size: int | None = None):
        n = size or self.BATCH_SIZE
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    @staticmethod
    def _sat_to_params(r: SatelliteRecord) -> dict:
        return {
            "noradId": r.norad_id,
            "cosparId": r.cospar_id,
            "name": r.name,
            "status": r.status,
            "launchDate": r.launch_date.isoformat() if r.launch_date else None,
            "altitudeKm": r.altitude_km,
            "inclination": r.inclination,
            "massKg": r.mass_kg,
            "tleLine1": r.tle_line1,
            "tleLine2": r.tle_line2,
            "countryCode": r.country_code or "XX",
        }

    @staticmethod
    def _cdm_to_params(r: ConjunctionRecord) -> dict:
        return {
            "conjunctionId": r.conjunction_id,
            "tca": r.tca.isoformat(),
            "missDistanceKm": r.miss_distance_km,
            "collisionProbability": r.collision_probability,
            "relativeVelocityKms": r.relative_velocity_kms,
            "riskLevel": r.risk_level,
            "screeningOrg": r.screening_org,
            "maneuverRequired": r.maneuver_required,
            "primaryNorad": r.primary_norad,
            "secondaryNorad": r.secondary_norad,
        }


# ── Source Fetchers ──────────────────────────────────────────

class CelesTrakFetcher:
    """Fetch active satellite catalog from CelesTrak GP endpoint."""

    GP_URL = "https://celestrak.org/SOCRATES/query.php"
    GP_ALL  = "https://celestrak.org/pub/TLE/catalog.txt"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def fetch_active_catalog(self) -> list[SatelliteRecord]:
        """Returns active satellite records from CelesTrak GP data."""
        url = "https://celestrak.org/pub/satcat.csv"
        resp = await self.client.get(url, timeout=60)
        resp.raise_for_status()
        return self._parse_satcat_csv(resp.text)

    def _parse_satcat_csv(self, csv_text: str) -> list[SatelliteRecord]:
        """Parse CelesTrak satcat.csv into SatelliteRecords."""
        import csv
        import io
        records = []
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            try:
                rec = SatelliteRecord(
                    norad_id=int(row.get("NORAD_CAT_ID", 0)),
                    cospar_id=row.get("OBJECT_ID", ""),
                    name=row.get("OBJECT_NAME", ""),
                    object_type=row.get("OBJECT_TYPE", "UNKNOWN"),
                    launch_date=self._parse_date(row.get("LAUNCH_DATE")),
                    country_code=row.get("COUNTRY", "XX")[:2],
                    status="operational" if row.get("OPS_STATUS") == "+" else "defunct",
                    altitude_km=float(row["APOGEE"]) if row.get("APOGEE") else None,
                    inclination=float(row["INCLINATION"]) if row.get("INCLINATION") else None,
                )
                if rec.norad_id > 0:
                    records.append(rec)
            except (ValueError, KeyError):
                continue
        logger.info(f"Parsed {len(records)} satellite records from CelesTrak")
        return records

    @staticmethod
    def _parse_date(s: str | None) -> date | None:
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None


class SpaceTrackFetcher:
    """Authenticated fetcher for Space-Track.org (CDM + TLE)."""

    LOGIN_URL = f"{SPACETRACK_BASE}/ajaxauth/login"
    CDM_URL   = f"{SPACETRACK_BASE}/basicspacedata/query/class/cdm_public/RISK/>=1e-6/orderby/TCA desc/limit/1000/format/json"

    def __init__(self, client: httpx.AsyncClient, username: str, password: str):
        self.client = client
        self.username = username
        self.password = password
        self._logged_in = False

    async def login(self):
        resp = await self.client.post(
            self.LOGIN_URL,
            data={"identity": self.username, "password": self.password},
        )
        resp.raise_for_status()
        self._logged_in = True
        logger.info("Authenticated with Space-Track.org")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=5, max=60))
    async def fetch_conjunctions(self) -> list[ConjunctionRecord]:
        if not self._logged_in:
            await self.login()
        resp = await self.client.get(self.CDM_URL, timeout=90)
        resp.raise_for_status()
        raw = resp.json()
        return self._parse_cdms(raw)

    def _parse_cdms(self, raw: list[dict]) -> list[ConjunctionRecord]:
        records = []
        for row in raw:
            try:
                pc = float(row.get("COLLISION_PROBABILITY", 0))
                miss = float(row.get("MISS_DISTANCE", 999))
                risk = (
                    "red" if pc >= 1e-3 else
                    "yellow" if pc >= 1e-4 else
                    "green"
                )
                rec = ConjunctionRecord(
                    conjunction_id=row["CDM_ID"],
                    tca=datetime.fromisoformat(row["TCA"].replace("Z", "+00:00")),
                    miss_distance_km=miss / 1000,
                    collision_probability=pc,
                    relative_velocity_kms=float(row.get("RELATIVE_VELOCITY", 0)),
                    primary_norad=int(row["SAT_1_ID"]),
                    secondary_norad=int(row["SAT_2_ID"]),
                    risk_level=risk,
                    maneuver_required=pc >= 1e-4,
                )
                records.append(rec)
            except (KeyError, ValueError):
                continue
        logger.info(f"Parsed {len(records)} CDM records from Space-Track")
        return records


# ── Embedding Pipeline ────────────────────────────────────────

class EmbeddingPipeline:
    """
    Generate embeddings for GraphRAG:
    - Satellite: name + purpose + missionType + operator
    - Mission: name + description + objectives
    - ResearchPaper: title + abstract + keywords

    Uses Anthropic voyage-3-large or OpenAI text-embedding-3-large
    """

    MODEL = "text-embedding-3-large"
    DIMENSIONS = 1536
    BATCH_SIZE = 100

    def __init__(self, openai_client):
        self.client = openai_client

    async def embed_satellites(self, driver: AsyncDriver):
        """Embed all satellites missing an embedding vector."""
        fetch_q = """
        MATCH (s:Satellite)
        WHERE s.embedding IS NULL AND s.name IS NOT NULL
        RETURN s.noradId AS noradId,
               s.name + ' ' + coalesce(s.purpose, '') + ' ' +
               coalesce(s.missionType, '') AS text
        LIMIT 1000
        """
        update_q = """
        UNWIND $batch AS row
        MATCH (s:Satellite {noradId: row.noradId})
        CALL db.create.setNodeVectorProperty(s, 'embedding', row.embedding)
        """
        async with driver.session() as session:
            result = await session.run(fetch_q)
            rows = await result.data()

        batches = [rows[i:i+self.BATCH_SIZE] for i in range(0, len(rows), self.BATCH_SIZE)]
        for batch in batches:
            texts = [r["text"] for r in batch]
            response = await self.client.embeddings.create(
                model=self.MODEL,
                input=texts,
                dimensions=self.DIMENSIONS,
            )
            embeddings = [e.embedding for e in response.data]
            update_batch = [
                {"noradId": batch[i]["noradId"], "embedding": embeddings[i]}
                for i in range(len(batch))
            ]
            async with driver.session() as session:
                await session.run(update_q, batch=update_batch)
            logger.info(f"Embedded {len(update_batch)} satellites")


# ── Orchestrator ──────────────────────────────────────────────

class GraphLoader:
    """
    Main ETL orchestrator.
    Run on schedule:
      - Satellite catalog: every 6h
      - TLE updates: every 2h
      - CDM events: every 15min
      - Space weather: every 30min
      - Embeddings: nightly
    """

    def __init__(
        self,
        neo4j_uri: str = NEO4J_URI,
        neo4j_user: str = NEO4J_USER,
        neo4j_password: str = NEO4J_PASSWORD,
    ):
        self.driver = AsyncGraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password)
        )

    async def run_full_load(self):
        logger.info("Starting full graph load")
        async with httpx.AsyncClient() as http:
            celestrak = CelesTrakFetcher(http)
            writer = Neo4jBatchWriter(self.driver)

            # Load satellite catalog
            sats = await celestrak.fetch_active_catalog()
            n = await writer.write_satellites(sats)
            logger.info(f"Wrote {n} satellite nodes")

        logger.info("Full graph load complete")

    async def run_cdm_refresh(self, st_user: str, st_pass: str):
        logger.info("Refreshing CDM conjunction events")
        async with httpx.AsyncClient() as http:
            st = SpaceTrackFetcher(http, st_user, st_pass)
            cdms = await st.fetch_conjunctions()
            writer = Neo4jBatchWriter(self.driver)
            n = await writer.write_conjunctions(cdms)
            logger.info(f"Wrote {n} conjunction events")

    async def close(self):
        await self.driver.close()


# ── Schema Initialization ─────────────────────────────────────

async def initialize_schema(driver: AsyncDriver):
    """
    Run all constraint and index DDL.
    Safe to call on every startup (IF NOT EXISTS guards).
    """
    import pathlib
    schema_dir = pathlib.Path(__file__).parent / "schema"
    for cypher_file in sorted(schema_dir.glob("0*.cypher")):
        logger.info(f"Running schema file: {cypher_file.name}")
        statements = cypher_file.read_text().split(";")
        async with driver.session() as session:
            for stmt in statements:
                stmt = stmt.strip()
                if stmt and not stmt.startswith("//"):
                    try:
                        await session.run(stmt)
                    except Exception as e:
                        logger.warning(f"Schema statement skipped: {e}")
    logger.info("Schema initialization complete")


# ── Entry Point ───────────────────────────────────────────────

if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)

    async def main():
        driver = AsyncGraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        await initialize_schema(driver)

        loader = GraphLoader()
        await loader.run_full_load()

        st_user = os.getenv("SPACETRACK_USER")
        st_pass = os.getenv("SPACETRACK_PASS")
        if st_user and st_pass:
            await loader.run_cdm_refresh(st_user, st_pass)

        await loader.close()
        await driver.close()

    asyncio.run(main())
