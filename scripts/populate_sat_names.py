"""
Populate satellite names and object types from Celestrak GP JSON.
Run in Railway shell: python3 scripts/populate_sat_names.py
"""
import urllib.request, json, asyncio, sys, os, time

sys.path.insert(0, '/app')
os.environ.setdefault('NEO4J_USER', 'bff8c462')

CELESTRAK_URL = "https://celestrak.org/SOCRATES/query.php"
GP_URL = "https://celestrak.org/SATCAT/satcat.json"

async def main():
    from app.db.session import get_session, engine
    from sqlalchemy import text, update
    from app.db.models.satellites import Satellite
    from sqlalchemy.ext.asyncio import AsyncSession

    print("Fetching Celestrak SATCAT JSON...")
    t0 = time.time()
    try:
        req = urllib.request.Request(
            "https://celestrak.org/pub/satcat.json",
            headers={"User-Agent": "ORBITIQ-X/0.4.0"}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=60).read())
        print(f"Fetched {len(data)} records in {time.time()-t0:.1f}s")
    except Exception as e:
        print(f"Celestrak SATCAT failed: {e}")
        # Try alternate endpoint
        try:
            req2 = urllib.request.Request(
                "https://celestrak.org/SATCAT/satcat.json",
                headers={"User-Agent": "ORBITIQ-X/0.4.0"}
            )
            data = json.loads(urllib.request.urlopen(req2, timeout=60).read())
            print(f"Alternate: {len(data)} records")
        except Exception as e2:
            print(f"Both endpoints failed: {e2}")
            return

    # Build lookup: NORAD_CAT_ID → {name, object_type}
    TYPE_MAP = {
        "PAY": "satellite",
        "R/B": "rocket_body",
        "DEB": "debris",
        "UNK": "unknown",
        "TBA": "unknown",
    }

    lookup = {}
    for sat in data:
        norad = sat.get("NORAD_CAT_ID") or sat.get("noradCatId")
        name  = sat.get("SATNAME") or sat.get("satname") or sat.get("OBJECT_NAME")
        otype = sat.get("OBJECT_TYPE") or sat.get("objectType") or ""
        if norad and name:
            lookup[int(norad)] = {
                "name":        name.strip(),
                "object_type": TYPE_MAP.get(otype.strip(), "unknown"),
            }

    print(f"Lookup built: {len(lookup)} entries")

    async with engine.begin() as conn:
        updated = 0
        batch = []
        for norad_id, vals in lookup.items():
            batch.append({"norad_id": norad_id, "name": vals["name"], "object_type": vals["object_type"]})
            if len(batch) >= 500:
                await conn.execute(
                    text("UPDATE satellites SET name=:name, object_type=:object_type WHERE norad_id=:norad_id"),
                    batch
                )
                updated += len(batch)
                batch = []
                print(f"  Updated {updated}...")
        if batch:
            await conn.execute(
                text("UPDATE satellites SET name=:name, object_type=:object_type WHERE norad_id=:norad_id"),
                batch
            )
            updated += len(batch)

    print(f"\nDone: {updated} satellites updated with real names and types")

asyncio.run(main())
