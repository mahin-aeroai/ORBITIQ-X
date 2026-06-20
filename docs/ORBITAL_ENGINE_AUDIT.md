# ORBITIQ-X Orbital Engine — Technical Audit Report

**Auditor:** Senior Backend Architect
**Date:** 2026-06-20
**Scope:** orbital-engine/ subsystem | 50,000-object SSA production target

---

## Audit Methodology

Every `.py` file was read in full. Import graphs were traced for broken
references. Public interfaces were compared against their callers.
Data flows were followed from HTTP request to database write.
"Implemented" means runnable without modification. "Partially implemented"
means the logic exists but has a known defect or gap that blocks
production use. "Stub" means the function body is `pass`, `logger.info()`,
or a comment block. "Missing" means no file exists.

---

## Component-by-Component Findings

---

### 1. TLE Ingestion Pipeline

**Status: PARTIALLY IMPLEMENTED — critical data-flow gap**

**What exists (orbital-engine/src/ingest/tle_parser.py — 330 LOC)**

- `parse_tle()`: Fully correct. Checksum validation, field extraction,
  NORAD cross-check, physical range checks, SGP4 exponent notation
  (`_parse_decimal`), epoch conversion. This code is production-grade.
- `parse_tle_file()`: Handles 3-line, 2-line, and mixed formats.
  Correct window/Unix line-ending normalisation.
- `validate_tle_age()`: Present.

**What is broken**

- `orbital-engine/src/ingest/celestrak.py` — **DOES NOT EXIST**.
  The scheduler (`scheduler/jobs.py`) calls `CelesTrakFetcher` at line 57
  but there is no HTTP client, no GP endpoint integration, no backoff,
  no rate-limit handling.
- No Space-Track client anywhere in the orbital-engine package
  (only a reference in the knowledge-graph loader — different service,
  different auth mechanism).
- No normaliser that converts parsed TLE → database row. The `ingest/`
  directory contains only `tle_parser.py`. No `normalizer.py`,
  no `pipeline.py`, no DB writer.
- The scheduler `job_refresh_active_tles()` body is two `logger.info()`
  calls. It does nothing.

**Missing files**

| File | What it needs |
|------|--------------|
| `orbital-engine/src/ingest/celestrak.py` | `httpx.AsyncClient` fetcher for GP endpoint (JSON format, 50K objects), retry with exponential backoff, rate limit handling |
| `orbital-engine/src/ingest/spacetrack.py` | Cookie-based auth login, GP + CDM bulk fetch, session reuse across calls |
| `orbital-engine/src/ingest/normalizer.py` | `ParsedTLE → TLERecord` ORM conversion, upsert strategy (update if epoch newer) |
| `orbital-engine/src/ingest/pipeline.py` | Orchestrates fetch → parse → validate → deduplicate → upsert → cache warm |

**Estimated effort:** 3 days
**Technical priority:** P0 — nothing runs without TLEs in the database

---

### 2. Space-Track Integration

**Status: MISSING**

There is no Space-Track client anywhere in the orbital-engine package.
The knowledge-graph `graph_loader.py` has a `SpaceTrackFetcher` class
but it is in the wrong service layer, uses `httpx` without the correct
cookie-based auth flow, and is not connected to the orbital engine
at all.

Space-Track is the only authoritative source for:
- Full RSO catalog (50K+ objects including classified debris)
- Conjunction Data Messages (CDM)
- Historical TLE archive (for re-analysis)

CelesTrak provides ~30% of the catalog. For 50K-object SSA operations,
Space-Track is mandatory.

**Missing implementation**

| File | What it needs |
|------|--------------|
| `orbital-engine/src/ingest/spacetrack.py` | `POST /ajaxauth/login` → cookie session → `GET /basicspacedata/query/...`, retry 429/503, credential rotation, CDM endpoint |
| `orbital-engine/src/ingest/spacetrack_models.py` | Pydantic models for all Space-Track JSON response schemas |
| `.env` / `Settings` | `SPACETRACK_USER`, `SPACETRACK_PASS` wired through Pydantic `SecretStr` |

**Estimated effort:** 2 days
**Technical priority:** P0 — required for full catalog coverage

---

### 3. SGP4 Propagation Accuracy

**Status: PARTIALLY IMPLEMENTED — two bugs, one critical**

**What exists (orbital-engine/src/propagator/sgp4_propagator.py — 380 LOC)**

The design is sound: WGS-72/84 selection, batch processing via
`ProcessPoolExecutor`, structured output, error isolation per object.

**Bug 1 — CRITICAL: Broken `sgp4_array` Julian Date call**

```python
# Line ~208 in sgp4_propagator.py — WRONG
e, r, v = satellite.sgp4_array(
    np.array([epoch_utc.timestamp()]),   # ← Unix timestamp, NOT Julian Date
    np.zeros(1),
)
```

`sgp4_array()` expects `(jd_array, jd_frac_array)` where `jd` is the
Julian Date. Passing a Unix timestamp (seconds since 1970-01-01) gives
wildly incorrect positions — typically placing objects thousands of km
from their actual position. The correct call is:

```python
from sgp4.api import jday
jd, jd_frac = jday(year, mon, day, hr, minute, sec)
e, r, v = satellite.sgp4_array(np.array([jd]), np.array([jd_frac]))
```

This is a silent failure — `error_code` will be 0, the state vector will
contain plausible-looking but entirely wrong values.

**Bug 2 — MEDIUM: J2 correction is physically incorrect**

The `_apply_j2_delta()` method:
1. Computes J2 acceleration (correct formula)
2. Then applies `corrected_velocity = velocity + accel * dt` with
   `dt = 1.0` seconds — but J2 is already embedded inside SGP4.
   Applying it again double-counts the perturbation.
3. Returns the original position unchanged (only velocity is modified)
   — inconsistent.

SGP4 already accounts for secular J2/J3/J4 drift. This "correction"
layer is at best redundant and at worst increases error for long-duration
propagation.

**Bug 3 — LOW: Import chain broken before first run**

```python
# sgp4_propagator.py line 37-38
from orbital_engine.src.propagator.tle_parser import TwoLineElement, parse_tle_pair
from orbital_engine.src.propagator.validators import validate_tle_epoch, validate_state_vector
```

- `validators.py` does not exist — `ImportError` on first import
- The screener creates `PropagationRequest(tle_line1=..., epochs=[epoch])`
  but `PropagationRequest` expects `tle_elements: list[TwoLineElement]`
  and `start_epoch`/`stop_epoch` — a different interface entirely.

**Estimated effort to fix:** 1 day (JD fix is 30 minutes; interface
reconciliation is 4 hours; J2 removal/replacement is 2 hours)
**Technical priority:** P0 — wrong positions invalidate every downstream
computation (conjunction screening, ground track, pass prediction)

---

### 4. Ground Track Generation

**Status: PARTIALLY IMPLEMENTED — math exists, service missing**

**What exists**

`coordinate_transforms.py` implements:
- `gmst_rad()` — IAU 1982 GMST (correct, adequate for SSA)
- `teme_to_eci()` — TEME → ECI rotation (correct matrix)
- `eci_to_ecef()` — ECI → ECEF via GMST (correct)
- `ecef_to_geo()` — Bowring iterative geodetic conversion (3-iteration,
  correct, sub-millimetre accuracy)
- `eci_to_geo()` — convenience composition (correct)

**What is missing**

There is no `GroundTrackService` that:
1. Accepts a TLE + time window + step size
2. Calls `propagate_single()` across the time window
3. Converts each ECI state to geodetic (wrapping `eci_to_geo`)
4. Returns ordered `[{epoch, lat, lon, alt, speed}]` points

The API schema for `GroundTrackRequest` / `GroundTrackPoint` exists in
`api/app.py` (lines 81–95) but the router directory is missing entirely.

**Missing files**

| File | What it needs |
|------|--------------|
| `orbital-engine/src/propagator/ground_track.py` | `GroundTrackService.compute(norad_id, tle, start, end, step_s)` — ~80 LOC |
| `orbital-engine/src/api/routers/groundtrack.py` | FastAPI router wiring GroundTrackService to HTTP |

**Estimated effort:** 1 day
**Technical priority:** P1 — needed for UI globe, depends on SGP4 JD fix

---

### 5. Pass Prediction

**Status: MISSING**

`src/passes/` directory does not exist. No pass prediction logic exists
anywhere in the orbital engine. The API spec in `app.py` documents the
endpoint interface but there is no `pass_predictor.py`, no `PassEvent`
model, no `passes/` router.

Pass prediction requires:
1. AOS/LOS search using elevation mask over a site
2. Az/El time series computation (using `eci_to_azel` from
   `coordinate_transforms.py` — this function IS implemented)
3. Max-elevation epoch finding (ternary search)
4. Event ordering and return

`eci_to_azel()` in `coordinate_transforms.py` is the only building block
that exists and it is correct.

**Missing files**

| File | What it needs |
|------|--------------|
| `orbital-engine/src/passes/__init__.py` | Package init |
| `orbital-engine/src/passes/pass_predictor.py` | Bisect-based AOS/LOS search, ternary search for max-el, ~150 LOC |
| `orbital-engine/src/passes/ground_station.py` | GroundStation dataclass with geodetic coordinates and elevation mask |
| `orbital-engine/src/api/routers/passes.py` | FastAPI router |

**Estimated effort:** 2 days
**Technical priority:** P1 — needed by mission planning, ground operators

---

### 6. Conjunction Screening

**Status: PARTIALLY IMPLEMENTED — design correct, interface broken**

**What exists**

`conjunction/screener.py` (422 LOC) has the most complete algorithmic
design in the codebase:
- Voxel-hash O(n) spatial filter is correctly designed
- TCA search via 1-minute stepping over 72-hour window is correct
- `ProcessPoolExecutor` fan-out is correctly structured
- `foster_pc.py` (305 LOC) has the Foster 2001 derivation, series
  expansion, scipy 2D numerical integration, and Monte Carlo fallback —
  these are all algorithmically correct

**Interface gap — CRITICAL: will fail on first call**

The screener calls `self.propagator.propagate(requests)` where
`requests` is a list. But `SGP4Propagator.propagate()` accepts a single
`PropagationRequest`, not a list. The screener also constructs:
```python
PropagationRequest(tle_line1=..., tle_line2=..., norad_id=..., epochs=[epoch])
```
but `PropagationRequest` has fields `tle_elements`, `start_epoch`,
`stop_epoch`. The two interfaces are completely mismatched —
this fails with `TypeError` on first run.

Additionally, the screener accesses `result.states` and `sv.x, sv.y, sv.z`
but `PropagationResult` has `state_vectors` and `StateVector` fields are
`position_eci_km[0]`, `position_eci_km[1]`, `position_eci_km[2]`.

**What is missing**

- CDM generator (`conjunction/cdm_generator.py`) — referenced in
  architecture but not implemented
- No Redis pub/sub publication of red/yellow alerts
- No database write path for `ConjunctionEvent` rows

**Estimated effort to fix interface:** 1 day
**Estimated effort for CDM + DB write:** 2 days
**Technical priority:** P0 — conjunction screening is the core SSA product

---

### 7. Relative Motion Analysis

**Status: IMPLEMENTED — best component in the codebase**

`relative_motion/clohessy_wiltshire.py` (307 LOC) is the most complete
and correct module:
- `ClohessyWiltshire.propagate()` — closed-form CW solution (correct)
- `state_transition_matrix()` — 6×6 Φ(t) (correct)
- `drift_ellipse_params()` — Hill ellipse parameters (correct)
- `delta_v_for_drift_nulling()` — velocity correction (correct)
- `two_impulse_rendezvous()` — CW inverse problem via pinv(Φ_rv)
  (mathematically correct but should use `np.linalg.lstsq` not `pinv`
  for numerical stability near coplanar orbits)

One minor issue: `drift_ellipse_params()` has a dead `hasattr(s0, 't')`
check that was meant for a different dataclass signature. Low-severity.

**No gaps for 50K-object production use** — CW is per-pair and called
only for close-approach pairs after conjunction screening.

**Technical priority:** P2 — already correct

---

### 8. Re-entry Prediction

**Status: PARTIALLY IMPLEMENTED — algorithmic gaps**

**What exists** (`reentry/reentry_monitor.py` — 300 LOC)

- King-Hele drag formula is implemented
- NRLMSISE-00 lookup table (simplified altitude-band model) is present
- F10.7 solar flux correction factor is applied
- Alert level classification (WATCH/WARNING/URGENT/CRITICAL/IMMINENT)
  is correct
- `ReentryMonitor.scan_catalog()` architecture is correct

**Bugs and gaps**

1. **Unit conversion error** in `predict_reentry()`:
   ```python
   n_rev_day = sat.no_kozai / (2 * math.pi / 1440.0)
   ```
   `sat.no_kozai` is in radians/minute. The conversion should be:
   `n_rev_day = sat.no_kozai * 1440.0 / (2 * math.pi)` — the current
   code divides instead of multiplying, giving mean motion ~8.7M×
   too small. Derived `a_km` is completely wrong.

2. **1-day integration step** is too coarse for objects with lifetime < 3
   days (IMMINENT/CRITICAL). Need adaptive step: 1h when perigee < 150 km.

3. **No uncertainty propagation** — the ±20% uncertainty factor is
   applied to the total lifetime but there is no Monte Carlo or
   sensitivity analysis to derive it from F10.7 variability.
   For IMMINENT events this is operationally insufficient.

4. **`scan_catalog()` is never called** — nothing invokes it on a
   schedule. The scheduler job body is two log lines.

**Estimated effort to fix:** 1.5 days
**Technical priority:** P1 — wrong unit conversion means all predictions
are wildly incorrect

---

### 9. Database Persistence Strategy

**Status: STUB — nothing persists to database**

**What exists**

`orbital-engine/src/db/models.py` (310 LOC) has well-designed
SQLAlchemy 2.0 async models: `RSOCatalog`, `TLEArchive`, `EphemerisPoint`
(with TimescaleDB hypertable comments), `GroundTrack`, `PassEvent`,
`ConjunctionEvent`, `ReentryAlert`, `GroundStation`.

**What is missing — every single write path**

```python
# backend/app/db/session.py — complete stub
"""session stub."""
async def init_session(): pass
async def close_session(): pass
```

There is no:
- `create_async_engine()` call with the PostgreSQL DSN
- `async_sessionmaker` factory
- `AsyncSession` dependency for FastAPI
- Any `session.add()` / `session.commit()` call in any service
- TLE upsert logic (check epoch before overwriting)
- Conjunction event insert with deduplication
- Re-entry alert upsert

The Alembic migration system (new — created in this session) provides
the schema, but nothing writes to it.

**Missing files**

| File | What it needs |
|------|--------------|
| `backend/app/db/session.py` | `create_async_engine`, `async_sessionmaker`, `get_session` FastAPI dep |
| `orbital-engine/src/db/repository.py` | `TLERepository.upsert()`, `ConjunctionRepository.insert()`, `EphemerisRepository.bulk_insert()` |
| `orbital-engine/src/db/ephemeris_writer.py` | Batch insert to TimescaleDB hypertable, 1000-row chunks |

**Estimated effort:** 2 days
**Technical priority:** P0 — without persistence, every restart loses all
computed data; no historical analysis possible

---

### 10. API Performance

**Status: STUB — routers directory does not exist**

**What exists**

`orbital-engine/src/api/app.py` (337 LOC) documents all 7 routers and
their complete endpoint contracts — excellent specification. The FastAPI
app factory is correctly structured with lifespan, CORS, GZip middleware.
Pydantic request/response models for propagate, ground track, passes,
catalog are well-defined.

**What is missing**

```
orbital-engine/src/api/routers/   ← DIRECTORY DOES NOT EXIST
```

All 7 routers are referenced in `app.include_router(...)` but the
directory they are imported from does not exist. The application will
raise `ModuleNotFoundError` on startup.

- `routers/health.py` — missing
- `routers/catalog.py` — missing
- `routers/propagate.py` — missing
- `routers/groundtrack.py` — missing
- `routers/passes.py` — missing
- `routers/conjunction.py` — missing
- `routers/reentry.py` — missing

**Performance gaps for 50K-object production**

- No Redis TLE cache layer (cold propagation from DB is too slow at scale)
- No request coalescing for `GET /catalog` (N+1 problem without it)
- No response caching for ground tracks (expensive recompute on every call)
- No connection pool configuration on the async engine
- No rate limiting on the propagation endpoint (trivial to DoS)
- SSE live-stream endpoint references a placeholder `# In production`
  comment — not implemented

**Estimated effort (routers only):** 3 days
**Technical priority:** P0 — the application cannot start

---

## Summary Table

| # | Component | Status | Blocking bugs | Missing files |
|---|-----------|--------|---------------|---------------|
| 1 | TLE ingestion pipeline | Partial | No fetcher, no writer | `celestrak.py`, `spacetrack.py`, `normalizer.py`, `pipeline.py` |
| 2 | Space-Track integration | **Missing** | — | `spacetrack.py`, models |
| 3 | SGP4 propagation accuracy | Partial | **JD bug (silent wrong positions)**, validators.py missing, broken J2, interface mismatch | `validators.py` |
| 4 | Ground track generation | Partial | Depends on SGP4 JD fix | `ground_track.py`, router |
| 5 | Pass prediction | **Missing** | — | `passes/` entire directory |
| 6 | Conjunction screening | Partial | **Interface mismatch (TypeError on first call)**, no DB write | `cdm_generator.py`, router impl |
| 7 | Relative motion | **Implemented** | Minor: pinv stability | — |
| 8 | Re-entry prediction | Partial | **Unit conversion bug (mean motion ×8.7M wrong)** | Adaptive step, MC uncertainty |
| 9 | Database persistence | **Stub** | No write path exists | `session.py`, `repository.py` |
| 10 | API performance | **Stub** | `ModuleNotFoundError` on startup | All 7 router files |

---

## Scoring

Each component scored out of 10 weighted by production-readiness impact
for a 50,000-object real-time SSA platform.

| Component | Weight | Raw score | Weighted |
|-----------|--------|-----------|----------|
| TLE ingestion (1) | 1.5× | 3/10 | 4.5 |
| Space-Track integration (2) | 1.5× | 0/10 | 0 |
| SGP4 propagation (3) | 2.0× | 2/10 | 4 |
| Ground track (4) | 1.0× | 4/10 | 4 |
| Pass prediction (5) | 1.0× | 0/10 | 0 |
| Conjunction screening (6) | 2.0× | 4/10 | 8 |
| Relative motion (7) | 0.5× | 8/10 | 4 |
| Re-entry prediction (8) | 1.0× | 3/10 | 3 |
| Database persistence (9) | 1.5× | 1/10 | 1.5 |
| API / performance (10) | 1.0× | 1/10 | 1 |

**Weighted total: 30 / (10 × 13 = 130 max)**
**Normalised to 100: 30/130 × 100 = 23**

---

```
╔══════════════════════════════════════════════════════╗
║                                                      ║
║   ORBITAL ENGINE READINESS SCORE:   23 / 100         ║
║                                                      ║
║   Architecture:  ████████████████░░░░░░  80/100      ║
║   Implementation: ████░░░░░░░░░░░░░░░░░  23/100      ║
║   Production:    ██░░░░░░░░░░░░░░░░░░░░  12/100      ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
```

The architecture score is genuinely high — the design decisions
(voxel-hash screener, Foster Pc, CW equations, async batch propagation,
structured error isolation) are production-calibre. The gap is entirely
in implementation depth and inter-module wiring.

---

## The Single Highest-Impact Component to Implement Next

### Fix the SGP4 Julian Date bug and reconcile the PropagationRequest interface

**Why this one**

The `sgp4_array()` Julian Date call bug is the root cause of failure for
6 of the 10 components:

```
SGP4 JD bug
    → SGP4 returns wrong positions
        → Conjunction screener's voxel filter places objects wrong
            → All spatial pairs are wrong
                → Foster Pc computed for wrong pairs → garbage CDMs
        → Ground track points are wrong (wrong lat/lon/alt)
        → Pass predictions are wrong (wrong elevation calculations)
        → Re-entry monitor's propagator is wrong (validates against bad positions)
        → All API responses return wrong data silently (error_code = 0)
```

A silent correctness failure is worse than a crash because it produces
plausible-looking output that will be trusted. A conjunction alert for
the wrong pair of objects is not just useless — it is actively harmful
in a real SSA context.

**The fix is under 30 minutes of coding:**

```python
# In sgp4_propagator.py propagate_single() — replace the sgp4_array call:
from sgp4.api import jday

epoch_utc = epoch.replace(tzinfo=timezone.utc) if epoch.tzinfo is None else epoch
jd = epoch_utc.timestamp() / 86400.0 + 2440587.5  # Unix → JD
jd_whole = int(jd)
jd_frac  = jd - jd_whole

e, r, v = satellite.sgp4_array(
    np.array([float(jd_whole)]),
    np.array([jd_frac]),
)
```

**Then in the same sitting, fix the interface mismatch** between
`ConjunctionScreener._propagate_all()` and `SGP4Propagator`:

1. Define a unified `PropagationRequest` with both the batch interface
   (the propagator's current design) and the per-object interface
   (what the screener needs), OR
2. Add a `SGP4Propagator.propagate_at_epoch(tle_line1, tle_line2,
   norad_id, epoch)` thin wrapper that the screener can call directly.

Option 2 is faster. The screener needs exactly one epoch per object;
the full batch interface adds unnecessary complexity at this layer.

**Estimated total effort:** 1 day
**Unblocks:** SGP4 accuracy, ground track, conjunction screening,
pass prediction, re-entry monitor, and all 7 API routers (which depend
on correct propagated positions to return meaningful responses)

---

## Recommended Sequence After the SGP4 Fix

1. **Day 1** — Fix SGP4 JD bug + reconcile PropagationRequest interface
2. **Day 2** — Wire `backend/app/db/session.py` (async engine, session factory)
3. **Day 3** — Implement `CelesTrakFetcher` + `SpaceTrackFetcher` (TLE ingest)
4. **Day 4** — Implement all 7 FastAPI routers (application can now start)
5. **Day 5** — Fix re-entry unit conversion + implement `pass_predictor.py`
6. **Day 6** — CDM generator + Redis pub/sub for conjunction alerts
7. **Day 7** — Load 50K TLEs, run first full conjunction screen, benchmark
