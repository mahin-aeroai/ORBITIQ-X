# Orbital Engine — Folder Structure

```
orbital-engine/
├── src/
│   ├── propagator/          # SGP4/J2 propagation core
│   │   ├── sgp4_propagator.py     # Batch SGP4, J2 correction, ProcessPool
│   │   ├── state_vector.py        # ECI/ECEF/LLA dataclasses
│   │   ├── tle_parser.py          # TLE line validator + parser
│   │   └── constants.py           # WGS-84/72, J2-J4, orbital constants
│   │
│   ├── classifier/          # Orbit regime classification
│   │   └── orbit_classifier.py    # LEO/MEO/GEO/SSO/HEO/VLEO/GTO
│   │
│   ├── groundtrack/         # Ground track + pass prediction
│   │   ├── ground_track.py        # WGS-84 lat/lon, ECEF→LLA
│   │   └── pass_predictor.py      # AOS/TCA/LOS, elevation mask
│   │
│   ├── conjunction/         # Conjunction screening + Pc
│   │   ├── screener.py            # Cube algorithm, O(N log N)
│   │   ├── pc_calculator.py       # Foster method collision probability
│   │   └── cdm_builder.py         # CDM format output
│   │
│   ├── reentry/             # Atmospheric decay + re-entry
│   │   ├── decay_estimator.py     # NRLMSISE-00 drag model
│   │   └── reentry_monitor.py     # B* tracking, perigee alerts
│   │
│   ├── relative_motion/     # CW / Hill-Clohessy-Wiltshire
│   │   └── cw_equations.py        # Relative position/velocity in RTN
│   │
│   ├── ingestion/           # Data source clients
│   │   ├── celestrak.py           # GP catalog, TLE files
│   │   ├── spacetrack.py          # Authenticated catalog + CDMs
│   │   ├── noaa_swpc.py           # Space weather (Kp, F10.7, Dst)
│   │   └── pipeline.py            # Orchestrated ETL
│   │
│   ├── scheduler/           # APScheduler + Celery tasks
│   │   ├── jobs.py                # All scheduled job definitions
│   │   └── celery_tasks.py        # Celery worker tasks
│   │
│   ├── api/                 # FastAPI routers
│   │   ├── router.py              # Aggregate router
│   │   ├── propagate.py           # POST /propagate
│   │   ├── passes.py              # POST /passes
│   │   ├── catalog.py             # GET /catalog
│   │   ├── conjunctions.py        # GET /conjunctions
│   │   ├── reentry.py             # GET /reentry
│   │   ├── groundtrack.py         # POST /groundtrack
│   │   └── relative_motion.py     # POST /relative-motion
│   │
│   ├── db/                  # Database sessions + models
│   │   ├── models.py              # SQLAlchemy ORM models
│   │   ├── timescale.py           # TimescaleDB async session
│   │   ├── redis_client.py        # Redis TLE/result cache
│   │   └── migrations/            # Alembic migration scripts
│   │
│   ├── errors/              # Error handling strategy
│   │   ├── exceptions.py          # Domain exception hierarchy
│   │   ├── circuit_breaker.py     # Per-source circuit breaker
│   │   └── dead_letter.py         # DLQ for failed propagations
│   │
│   └── utils/
│       ├── time_utils.py          # UTC/TDB/GMST conversions
│       ├── coord_transforms.py    # ECI↔ECEF↔LLA
│       └── math_utils.py          # Rotation matrices, quaternions
│
├── tests/
│   ├── unit/                # Per-module unit tests
│   ├── integration/         # End-to-end API tests
│   └── benchmarks/          # Performance benchmarks (pytest-benchmark)
│
├── configs/
│   └── engine.yaml          # All tunable parameters
│
├── data/
│   ├── tle/                 # Cached TLE files
│   ├── cdm/                 # CDM output archive
│   └── weather/             # Space weather snapshots
│
└── pyproject.toml           # Package config + coverage thresholds
```
