# ORBITIQ-X Migration Guide

## Folder structure

```
backend/
├── alembic/
│   ├── env.py              # DB connection + model import
│   ├── script.py.mako      # Migration file template
│   └── versions/
│       ├── 20260620_0001_init_create_extensions.py
│       ├── 20260620_0002_create_users.py
│       ├── 20260620_0003_create_operators.py
│       ├── 20260620_0004_create_satellites.py
│       ├── 20260620_0005_create_tle_records.py
│       ├── 20260620_0006_create_missions.py
│       ├── 20260620_0007_create_event_tables.py
│       └── 20260620_0008_timescaledb_hypertables.py
├── app/db/
│   ├── base.py             # DeclarativeBase + all model imports
│   └── models/
│       ├── users.py
│       ├── operators.py
│       ├── satellites.py
│       ├── tle_records.py
│       ├── missions.py
│       ├── conjunction_events.py
│       ├── orbital_events.py
│       └── audit_logs.py
├── alembic.ini             # Alembic config
├── migrate.py              # Migration CLI
├── entrypoint.sh           # Docker entrypoint (runs migrations on boot)
└── Makefile                # Developer shortcuts

```

## Local development

```bash
# 1. Start PostgreSQL
make db-up

# 2. Apply all migrations
make migrate

# 3. Verify schema
make migrate-verify

# 4. Check current state
make migrate-status
```

## Adding a new migration

```bash
# After changing a model:
make migrate-new MSG="add antenna_type column to satellites"

# Review the generated file in alembic/versions/
# Always check upgrade() and downgrade() before committing
```

## Deployment workflow

1. Build Docker image — entrypoint.sh automatically runs `migrate upgrade head`
2. Zero-downtime: migrations run before new pods serve traffic
3. Rollback: `make migrate-down` or restore from backup

## Rules for safe migrations

- Never DROP a column without a deprecation migration first (add nullable, then drop)
- Never rename a column in one step (add new, backfill, drop old across three deploys)
- Always write a valid `downgrade()` that reverses exactly what `upgrade()` did
- Never truncate or DELETE data in a migration
- Use `IF NOT EXISTS` / `IF EXISTS` guards wherever possible
