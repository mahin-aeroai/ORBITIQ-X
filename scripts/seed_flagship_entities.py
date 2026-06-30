"""
ORBITIQ-X — Flagship Aerospace Entity Seed
===========================================
Phase 17 supplemental: seeds a small curated set of well-known,
high-confidence aerospace entities directly into PostgreSQL's
aerospace_entities table.

Purpose: give the Entity Browser an immediate, polished baseline
experience before the full ingestion pipeline (Space-Track, NASA,
Celestrak, UNOOSA adapters) has been run against production data.

Run with:
    PYTHONPATH=backend/app python3 scripts/seed_flagship_entities.py

Requires DATABASE_URL env var pointing at the production PostgreSQL
instance (same one Railway uses), OR run this against a local/staging
DB first to verify correctness before pointing at production.

All entities use Tier 1 (official) provenance — Wikipedia/agency
websites cross-referenced — confidence_score 0.90, lifecycle_status
'published' so they appear immediately in the live Entity Browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, date, timezone

# Ensure 'caem' is importable whether this script is run standalone from the
# CLI (python3 scripts/seed_flagship_entities.py) or imported as a module
# from within the running FastAPI process (entities.py's /seed-flagship
# endpoint), where PYTHONPATH=/app/app is already set by entrypoint.sh and
# 'caem' may already be importable without any extra path manipulation.
try:
    from caem.base import EntityClass, generate_aqid
    from caem.entities import validate_extension
except ImportError:
    # Standalone CLI invocation — locate backend/app relative to this
    # script's own location (scripts/ and backend/ are repo-root siblings).
    _backend_app = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "app")
    if _backend_app not in sys.path:
        sys.path.insert(0, _backend_app)
    from caem.base import EntityClass, generate_aqid
    from caem.entities import validate_extension


# ---------------------------------------------------------------------------
# SEED DEFINITIONS
# ---------------------------------------------------------------------------

FLAGSHIP_ENTITIES = [
    # ── COUNTRIES ──────────────────────────────────────────────────────────
    {
        "entity_class": EntityClass.COUNTRY,
        "display_name": "United States",
        "short_name": "USA",
        "description": "Leading spacefaring nation; home to NASA, SpaceX, Blue Origin, ULA, and the majority of active commercial satellite operators.",
        "tags": ["spacefaring", "g7", "permanent_un_security_council"],
        "domains": ["space_policy", "launch_systems"],
        "founded_or_created": date(1776, 7, 4),
        "extension_data": {
            "iso_code_alpha2": "US", "iso_code_alpha3": "USA",
            "capital_city": "Washington, D.C.", "continent": "North America",
            "space_budget_musd": 73200.0, "space_budget_year": 2023,
            "active_satellites": 4500, "launch_capability": True,
            "un_registry_member": True, "outer_space_treaty": True,
        },
    },
    {
        "entity_class": EntityClass.COUNTRY,
        "display_name": "India",
        "short_name": "India",
        "description": "Major emerging spacefaring nation; home to ISRO, known for cost-efficient launch vehicles and the Chandrayaan and Mangalyaan missions.",
        "tags": ["spacefaring", "emerging_space_power"],
        "domains": ["space_policy", "launch_systems"],
        "founded_or_created": date(1947, 8, 15),
        "extension_data": {
            "iso_code_alpha2": "IN", "iso_code_alpha3": "IND",
            "capital_city": "New Delhi", "continent": "Asia",
            "space_budget_musd": 1960.0, "space_budget_year": 2023,
            "active_satellites": 60, "launch_capability": True,
            "un_registry_member": True, "outer_space_treaty": True,
        },
    },
    {
        "entity_class": EntityClass.COUNTRY,
        "display_name": "France",
        "short_name": "France",
        "description": "Leading European spacefaring nation; home to CNES and Arianespace, hosts the Guiana Space Centre launch site.",
        "tags": ["spacefaring", "eu_member", "g7"],
        "domains": ["space_policy", "launch_systems"],
        "extension_data": {
            "iso_code_alpha2": "FR", "iso_code_alpha3": "FRA",
            "capital_city": "Paris", "continent": "Europe",
            "space_budget_musd": 3700.0, "space_budget_year": 2023,
            "active_satellites": 70, "launch_capability": True,
            "un_registry_member": True, "outer_space_treaty": True,
        },
    },

    # ── GOVERNMENT AGENCIES ────────────────────────────────────────────────
    {
        "entity_class": EntityClass.GOV_AGENCY,
        "display_name": "National Aeronautics and Space Administration",
        "short_name": "NASA",
        "aliases": ["NASA"],
        "description": "United States federal agency responsible for civilian space program, aeronautics, and aerospace research. Operates the ISS US segment and leads the Artemis lunar program.",
        "tags": ["civil_space_agency", "human_spaceflight", "science"],
        "domains": ["human_spaceflight", "space_science", "lunar_exploration"],
        "founded_or_created": date(1958, 10, 1),
        "extension_data": {
            "agency_type": "civil", "established_year": 1958,
            "annual_budget_musd": 25400.0, "budget_year": 2024,
            "headquarters_city": "Washington, D.C.",
            "administrator": "Bill Nelson", "employee_count": 17373,
            "website": "https://www.nasa.gov",
        },
    },
    {
        "entity_class": EntityClass.GOV_AGENCY,
        "display_name": "European Space Agency",
        "short_name": "ESA",
        "aliases": ["ESA"],
        "description": "Intergovernmental organization of 22 member states dedicated to space exploration. Operates the Guiana Space Centre and develops the Ariane launch vehicle family.",
        "tags": ["civil_space_agency", "intergovernmental", "science"],
        "domains": ["launch_systems", "space_science"],
        "founded_or_created": date(1975, 5, 30),
        "extension_data": {
            "agency_type": "civil", "established_year": 1975,
            "annual_budget_musd": 7800.0, "budget_year": 2024,
            "headquarters_city": "Paris", "administrator": "Josef Aschbacher",
            "employee_count": 2500, "website": "https://www.esa.int",
        },
    },
    {
        "entity_class": EntityClass.GOV_AGENCY,
        "display_name": "Indian Space Research Organisation",
        "short_name": "ISRO",
        "aliases": ["ISRO"],
        "description": "India's national space agency, known for cost-efficient missions including Chandrayaan-3 (2023 lunar south pole landing) and Mangalyaan Mars orbiter.",
        "tags": ["civil_space_agency", "lunar_exploration", "science"],
        "domains": ["launch_systems", "space_science", "lunar_exploration"],
        "founded_or_created": date(1969, 8, 15),
        "extension_data": {
            "agency_type": "civil", "established_year": 1969,
            "annual_budget_musd": 1960.0, "budget_year": 2023,
            "headquarters_city": "Bengaluru", "administrator": "S. Somanath",
            "website": "https://www.isro.gov.in",
        },
    },

    # ── COMMERCIAL COMPANIES ───────────────────────────────────────────────
    {
        "entity_class": EntityClass.COMPANY,
        "display_name": "SpaceX",
        "short_name": "SpaceX",
        "aliases": ["Space Exploration Technologies Corp."],
        "description": "Private aerospace manufacturer and launch provider. Operates the Falcon 9, Falcon Heavy, and Starship launch vehicles, and the Starlink satellite constellation. First company to achieve orbital-class rocket reusability.",
        "tags": ["launch_provider", "reusability", "constellation_operator"],
        "domains": ["launch_systems", "commercial", "satellite_constellations"],
        "founded_or_created": date(2002, 3, 14),
        "extension_data": {
            "founded_year": 2002, "headquarters_city": "Hawthorne, California",
            "headquarters_country": "AQID-COUNTRY-UNITED-STATES",
            "ceo": "Elon Musk", "employee_count": 13000,
            "valuation_musd": 150000.0, "publicly_traded": False,
            "website": "https://www.spacex.com",
            "primary_domain": "launch_services",
            "active_satellites": 5000,
        },
    },
    {
        "entity_class": EntityClass.COMPANY,
        "display_name": "Blue Origin",
        "short_name": "Blue Origin",
        "description": "Private aerospace manufacturer founded by Jeff Bezos. Develops the New Shepard suborbital vehicle and New Glenn orbital launch vehicle, and the BE-4 rocket engine.",
        "tags": ["launch_provider", "reusability", "suborbital"],
        "domains": ["launch_systems", "commercial"],
        "founded_or_created": date(2000, 9, 8),
        "extension_data": {
            "founded_year": 2000, "headquarters_city": "Kent, Washington",
            "headquarters_country": "AQID-COUNTRY-UNITED-STATES",
            "ceo": "Dave Limp", "employee_count": 11000,
            "publicly_traded": False, "website": "https://www.blueorigin.com",
            "primary_domain": "launch_services",
        },
    },
    {
        "entity_class": EntityClass.COMPANY,
        "display_name": "Rocket Lab",
        "short_name": "Rocket Lab",
        "description": "Aerospace manufacturer and small satellite launch provider, known for the Electron launch vehicle and Photon satellite bus. Publicly traded on NASDAQ.",
        "tags": ["launch_provider", "small_satellite", "publicly_traded"],
        "domains": ["launch_systems", "commercial"],
        "founded_or_created": date(2006, 6, 1),
        "extension_data": {
            "ticker": "RKLB", "exchange": "NASDAQ", "founded_year": 2006,
            "headquarters_city": "Long Beach, California",
            "headquarters_country": "AQID-COUNTRY-UNITED-STATES",
            "ceo": "Peter Beck", "publicly_traded": True,
            "website": "https://www.rocketlabusa.com",
            "primary_domain": "launch_services",
        },
    },
    {
        "entity_class": EntityClass.COMPANY,
        "display_name": "United Launch Alliance",
        "short_name": "ULA",
        "aliases": ["ULA"],
        "description": "Joint venture between Boeing and Lockheed Martin providing launch services for US government and commercial payloads. Operates the Atlas V, Delta IV, and Vulcan Centaur launch vehicles.",
        "tags": ["launch_provider", "government_contractor"],
        "domains": ["launch_systems", "defence_security"],
        "founded_or_created": date(2006, 12, 1),
        "extension_data": {
            "founded_year": 2006, "headquarters_city": "Centennial, Colorado",
            "headquarters_country": "AQID-COUNTRY-UNITED-STATES",
            "publicly_traded": False, "website": "https://www.ulalaunch.com",
            "primary_domain": "launch_services",
        },
    },

    # ── LAUNCH VEHICLES ────────────────────────────────────────────────────
    {
        "entity_class": EntityClass.LAUNCH_VEHICLE,
        "display_name": "Falcon 9",
        "description": "Two-stage, partially reusable medium-lift launch vehicle developed by SpaceX. The world's first orbital-class reusable rocket, with first stage boosters routinely flown 10+ times.",
        "tags": ["reusable", "medium_lift", "operational"],
        "domains": ["launch_systems"],
        "founded_or_created": date(2010, 6, 4),
        "operational_start": date(2010, 6, 4),
        "extension_data": {
            "family": "Falcon", "variant": "Block 5", "status": "active",
            "stage_count": 2, "payload_leo_kg": 22800.0, "payload_gto_kg": 8300.0,
            "height_m": 70.0,
        },
    },
    {
        "entity_class": EntityClass.LAUNCH_VEHICLE,
        "display_name": "Falcon Heavy",
        "description": "Heavy-lift launch vehicle by SpaceX, composed of three Falcon 9 first-stage cores. Currently the most powerful operational rocket by payload capacity until Starship reaches operational status.",
        "tags": ["reusable", "heavy_lift", "operational"],
        "domains": ["launch_systems"],
        "founded_or_created": date(2018, 2, 6),
        "operational_start": date(2018, 2, 6),
        "extension_data": {
            "family": "Falcon", "status": "active", "stage_count": 2,
            "payload_leo_kg": 63800.0, "payload_gto_kg": 26700.0,
            "height_m": 70.0,
        },
    },
    {
        "entity_class": EntityClass.LAUNCH_VEHICLE,
        "display_name": "Starship",
        "description": "Fully reusable super heavy-lift launch vehicle by SpaceX, designed for missions to the Moon, Mars, and beyond. Powered by Raptor engines burning liquid methane and oxygen.",
        "tags": ["reusable", "super_heavy_lift", "development"],
        "domains": ["launch_systems"],
        "extension_data": {
            "family": "Starship", "status": "development", "stage_count": 2,
            "payload_leo_kg": 150000.0,
        },
    },
    {
        "entity_class": EntityClass.LAUNCH_VEHICLE,
        "display_name": "Space Launch System",
        "short_name": "SLS",
        "description": "NASA's super heavy-lift expendable launch vehicle developed for the Artemis lunar program, succeeding the Space Shuttle and Saturn V architectures.",
        "tags": ["expendable", "super_heavy_lift", "operational"],
        "domains": ["launch_systems", "human_spaceflight", "lunar_exploration"],
        "founded_or_created": date(2022, 11, 16),
        "operational_start": date(2022, 11, 16),
        "extension_data": {
            "family": "SLS", "status": "active", "stage_count": 2,
            "payload_leo_kg": 95000.0, "payload_tli_kg": 27000.0,
        },
    },
    {
        "entity_class": EntityClass.LAUNCH_VEHICLE,
        "display_name": "Ariane 6",
        "description": "European heavy-lift launch vehicle developed by ArianeGroup for ESA, succeeding Ariane 5. Designed for institutional and commercial payloads to GTO and LEO.",
        "tags": ["expendable", "heavy_lift", "operational"],
        "domains": ["launch_systems"],
        "founded_or_created": date(2024, 7, 9),
        "operational_start": date(2024, 7, 9),
        "extension_data": {
            "family": "Ariane", "variant": "A64", "status": "active",
            "stage_count": 2, "payload_leo_kg": 21650.0, "payload_gto_kg": 11500.0,
        },
    },

    # ── MISSIONS ───────────────────────────────────────────────────────────
    {
        "entity_class": EntityClass.MISSION,
        "display_name": "Artemis II",
        "description": "First crewed mission of NASA's Artemis program — a lunar flyby carrying four astronauts, paving the way for Artemis III's planned lunar surface landing.",
        "tags": ["crewed", "lunar", "artemis_program"],
        "domains": ["human_spaceflight", "lunar_exploration"],
        "extension_data": {
            "mission_type": "crewed", "destination": "Moon",
            "lead_agency_aqid": "AQID-GOV_AGENCY-NATIONAL-AERONAUTICS-AND-SPACE-ADMINISTRATION",
            "crew_size": 4,
            "launch_vehicle_aqid": "AQID-LAUNCH_VEHICLE-SPACE-LAUNCH-SYSTEM",
        },
    },
    {
        "entity_class": EntityClass.MISSION,
        "display_name": "James Webb Space Telescope",
        "short_name": "JWST",
        "description": "Infrared space observatory and the successor to the Hubble Space Telescope, operating at the Sun-Earth L2 Lagrange point. Joint mission between NASA, ESA, and CSA.",
        "tags": ["space_telescope", "infrared", "astrophysics"],
        "domains": ["space_science"],
        "founded_or_created": date(2021, 12, 25),
        "operational_start": date(2022, 7, 12),
        "extension_data": {
            "mission_type": "robotic", "destination": "Sun-Earth L2",
            "lead_agency_aqid": "AQID-GOV_AGENCY-NATIONAL-AERONAUTICS-AND-SPACE-ADMINISTRATION",
        },
    },
    {
        "entity_class": EntityClass.MISSION,
        "display_name": "International Space Station",
        "short_name": "ISS",
        "description": "Modular space station in low Earth orbit, the largest human-made object in space and a multinational collaborative program involving NASA, Roscosmos, ESA, JAXA, and CSA.",
        "tags": ["human_spaceflight", "leo", "international"],
        "domains": ["human_spaceflight"],
        "founded_or_created": date(1998, 11, 20),
        "operational_start": date(2000, 11, 2),
        "extension_data": {
            "mission_type": "crewed", "destination": "LEO",
            "lead_agency_aqid": "AQID-GOV_AGENCY-NATIONAL-AERONAUTICS-AND-SPACE-ADMINISTRATION",
        },
    },
]


def build_entity_record(spec: dict) -> dict:
    """Convert a seed spec dict into a full aerospace_entities row dict."""
    entity_class = spec["entity_class"]
    aqid = generate_aqid(entity_class, spec["display_name"])

    extension_data = validate_extension(entity_class, spec.get("extension_data", {}))

    # aerospace_entities.created_at/updated_at/published_at are
    # sa.DateTime WITHOUT timezone (TIMESTAMP WITHOUT TIME ZONE in
    # PostgreSQL) — must use a naive datetime here, matching the
    # convention used everywhere else in this codebase (entities.py's
    # create_entity uses datetime.utcnow() for the same reason). A
    # timezone-aware datetime.now(timezone.utc) causes asyncpg to reject
    # the value outright: "can't subtract offset-naive and offset-aware
    # datetimes".
    now = datetime.utcnow()
    return {
        "aqid": aqid,
        "entity_class": entity_class.value,
        "display_name": spec["display_name"],
        "short_name": spec.get("short_name"),
        "aliases": json.dumps(spec.get("aliases", [])),
        "description": spec.get("description"),
        "tags": json.dumps(spec.get("tags", [])),
        "domains": json.dumps(spec.get("domains", [])),
        "founded_or_created": spec.get("founded_or_created"),
        "operational_start": spec.get("operational_start"),
        "extension_data": json.dumps(extension_data),
        "lifecycle_status": "published",
        "is_active": True,
        "verification_status": "human_verified",
        "confidence_score": 0.90,
        "primary_provenance": json.dumps({
            "source_url": None,
            "source_type": "official",
            "confidence": 0.90,
            "notes": "Flagship curated seed — cross-referenced from official agency/company sources",
        }),
        "created_by": "flagship_seed_script",
        "updated_by": "flagship_seed_script",
        "ingest_pipeline": "flagship_seed",
        "created_at": now,
        "updated_at": now,
        "published_at": now,
    }


async def main():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    dry_run = "--dry-run" in sys.argv

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set.")
        print("Set it to the Railway PostgreSQL connection string before running.")
        sys.exit(1)

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)

    inserted, skipped, failed = 0, 0, 0

    if dry_run:
        print("=== DRY RUN — no writes will be made ===\n")

    async with engine.begin() as conn:
        for spec in FLAGSHIP_ENTITIES:
            try:
                record = build_entity_record(spec)
            except Exception as e:
                print(f"  ✗ VALIDATION FAILED: {spec['display_name']}: {e}")
                failed += 1
                continue

            existing = await conn.execute(
                text("SELECT aqid FROM aerospace_entities WHERE aqid = :aqid"),
                {"aqid": record["aqid"]},
            )
            if existing.fetchone():
                print(f"  - SKIP (exists): {record['aqid']}")
                skipped += 1
                continue

            if dry_run:
                print(f"  [DRY RUN] Would insert: {record['aqid']}")
                inserted += 1
                continue

            columns = ", ".join(record.keys())
            placeholders = ", ".join(f":{k}" for k in record.keys())
            await conn.execute(
                text(f"INSERT INTO aerospace_entities ({columns}) VALUES ({placeholders})"),
                record,
            )
            print(f"  ✓ Inserted: {record['aqid']}")
            inserted += 1

        if dry_run:
            # Roll back even though nothing was written, for clarity/symmetry
            await conn.rollback()

    await engine.dispose()

    print()
    verb = "would be inserted" if dry_run else "inserted"
    print(f"Flagship seed {'(dry run) ' if dry_run else ''}complete: "
          f"{inserted} {verb}, {skipped} skipped (already exist), {failed} failed validation")


if __name__ == "__main__":
    asyncio.run(main())
