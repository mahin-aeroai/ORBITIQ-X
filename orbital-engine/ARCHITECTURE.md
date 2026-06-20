
ORBITIQ-X Orbital Engine — Complete Architecture
=================================================

Senior Orbital Mechanics Engineer Design Document
Target: 50,000+ tracked objects, <5s batch propagation, real-time conjunction alerts

FOLDER STRUCTURE
────────────────
orbital-engine/
├── pyproject.toml                     # installable package: orbitiq-orbital-engine
├── src/
│   ├── __init__.py
│   │
│   ├── propagator/                    # Core SGP4 + high-fidelity propagation
│   │   ├── __init__.py
│   │   ├── constants.py               # WGS-84, J2-J4, CDM thresholds, regime bounds
│   │   ├── sgp4_propagator.py         # DONE (session 1) — batch SGP4, J2 correction
│   │   ├── hifi_integrator.py         # NEW — Poliastro RK78 for high-fidelity
│   │   ├── covariance.py              # NEW — covariance propagation (STM, Monte Carlo)
│   │   └── coordinate_transforms.py  # NEW — ECI↔ECEF↔GEO↔LVLH transforms
│   │
│   ├── classifier/                    # Orbit regime classification
│   │   ├── __init__.py
│   │   └── orbit_classifier.py        # NEW — LEO/MEO/GEO/HEO/SSO/GTO/TLI/VLEO
│   │
│   ├── groundtrack/                   # Ground track computation
│   │   ├── __init__.py
│   │   └── ground_track.py            # NEW — Skyfield ECEF→GEO, subsatellite points
│   │
│   ├── passes/                        # Pass prediction
│   │   ├── __init__.py
│   │   └── pass_predictor.py          # NEW — AOS/LOS/max-el, site visibility
│   │
│   ├── conjunction/                   # Conjunction screening
│   │   ├── __init__.py
│   │   ├── screener.py                # NEW — spatial filter + Pc computation
│   │   ├── foster_pc.py               # NEW — Foster (2001) collision probability
│   │   └── cdm_generator.py           # NEW — CDM v1.0 format output
│   │
│   ├── reentry/                       # Re-entry monitoring
│   │   ├── __init__.py
│   │   └── reentry_monitor.py         # NEW — decay prediction, NRLMSISE-00, alerts
│   │
│   ├── relative_motion/               # Relative motion analysis
│   │   ├── __init__.py
│   │   └── clohessy_wiltshire.py      # NEW — CW/HCW equations, LVLH frame
│   │
│   ├── ingest/                        # Data ingestion pipeline
│   │   ├── __init__.py
│   │   ├── celestrak.py               # NEW — TLE/GP fetcher, format parsing
│   │   ├── spacetrack.py              # NEW — authenticated GP + CDM fetcher
│   │   ├── tle_parser.py              # NEW — TLE validator, checksum, epoch
│   │   └── normalizer.py              # NEW — source → canonical RSO schema
│   │
│   ├── scheduler/                     # APScheduler job definitions
│   │   ├── __init__.py
│   │   └── jobs.py                    # NEW — all scheduled refresh jobs
│   │
│   ├── api/                           # FastAPI application + routers
│   │   ├── __init__.py
│   │   ├── app.py                     # NEW — FastAPI factory, lifespan
│   │   ├── deps.py                    # NEW — DB/cache/pool dependencies
│   │   └── routers/
│   │       ├── catalog.py             # NEW — catalog CRUD + search
│   │       ├── propagate.py           # NEW — single + batch propagation
│   │       ├── groundtrack.py         # NEW — ground track endpoint
│   │       ├── passes.py              # NEW — pass prediction endpoint
│   │       ├── conjunction.py         # NEW — CDM list + stream
│   │       ├── reentry.py             # NEW — decay monitoring
│   │       └── health.py              # NEW — liveness + readiness
│   │
│   ├── db/                            # Database access layer
│   │   ├── __init__.py
│   │   ├── session.py                 # NEW — async SQLAlchemy engine
│   │   └── models.py                  # NEW — all ORM models
│   │
│   ├── models/                        # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── tle.py                     # NEW — TLE request/response
│   │   ├── state.py                   # NEW — StateVector, EphemerisPoint
│   │   ├── conjunction.py             # NEW — CDM, ConjunctionAlert
│   │   ├── groundtrack.py             # NEW — GroundTrackPoint, GroundTrackResponse
│   │   ├── passes.py                  # NEW — PassEvent, PassWindow
│   │   └── reentry.py                 # NEW — DecayPrediction, ReentryAlert
│   │
│   ├── cache/                         # Redis caching layer
│   │   ├── __init__.py
│   │   └── state_cache.py             # NEW — state vector cache, TTL strategy
│   │
│   ├── metrics/                       # Prometheus instrumentation
│   │   ├── __init__.py
│   │   └── registry.py                # NEW — all custom metrics
│   │
│   ├── utils/                         # Shared utilities
│   │   ├── __init__.py
│   │   ├── time_utils.py              # NEW — UTC/TT/GPS conversions, JD
│   │   └── math_utils.py              # NEW — rotation matrices, vector ops
│   │
│   └── errors/                        # Error hierarchy
│       ├── __init__.py
│       └── exceptions.py              # NEW — all custom exceptions
│
└── tests/
    ├── unit/
    │   ├── test_sgp4_propagator.py
    │   ├── test_orbit_classifier.py
    │   ├── test_foster_pc.py
    │   ├── test_tle_parser.py
    │   └── test_coordinate_transforms.py
    ├── integration/
    │   ├── test_batch_propagation.py
    │   ├── test_conjunction_pipeline.py
    │   └── test_api_endpoints.py
    └── benchmark/
        ├── bench_sgp4_50k.py
        └── bench_conjunction_screen.py

IMPLEMENTATION ROADMAP
──────────────────────

Phase 1 — Foundation (Week 1)     COMPLETE (session 1)
  ✓ constants.py
  ✓ sgp4_propagator.py (batch SGP4, J2, ProcessPoolExecutor)
  ✓ pyproject.toml

Phase 2 — Physics Layer (Week 2)  THIS SESSION
  ✓ coordinate_transforms.py      ECI/ECEF/GEO/LVLH
  ✓ orbit_classifier.py           regime + SSO detection
  ✓ hifi_integrator.py            Poliastro RK78
  ✓ covariance.py                 STM + Monte Carlo
  ✓ foster_pc.py                  collision probability
  ✓ clohessy_wiltshire.py         relative motion
  ✓ reentry_monitor.py            decay prediction
  ✓ ground_track.py               subsatellite points
  ✓ pass_predictor.py             AOS/LOS/elevation

Phase 3 — Ingestion (Week 3)
  ✓ tle_parser.py                 TLE validation
  ✓ celestrak.py                  GP data
  ✓ spacetrack.py                 auth + CDM
  ✓ normalizer.py                 canonical RSO

Phase 4 — API + Storage (Week 4)
  ✓ db/models.py                  ORM
  ✓ api/app.py                    FastAPI
  ✓ api/routers/*.py              all 7 routers
  ✓ cache/state_cache.py          Redis TTL

Phase 5 — Scale + Alerting (Week 5)
  ✓ scheduler/jobs.py             APScheduler
  ✓ conjunction/screener.py       50K object filter
  ✓ metrics/registry.py           Prometheus
  ✓ CI pipeline + benchmarks
