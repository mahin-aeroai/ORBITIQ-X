"""
ORBITIQ-X — SQLAlchemy declarative base + all model imports.

This module is the SINGLE import point for Alembic autogenerate.
Every ORM model must be imported here — if it is not imported,
Alembic will not detect schema changes for that table.

Import order follows FK dependency graph:
  users → operators → missions → satellites → tle_records
        ↘ audit_logs (references all)
  conjunction_events (references satellites)
  orbital_events (references satellites)
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORBITIQ-X ORM models."""


# ── Import every model module so SQLAlchemy registers them ───
# The imports below cause the mappers to register against Base.metadata.
# They are not unused — removing any one breaks autogenerate.

from app.db.models.users            import User, UserSession         # noqa: F401, E402
from app.db.models.operators        import Operator                   # noqa: F401, E402
from app.db.models.satellites       import Satellite                  # noqa: F401, E402
from app.db.models.tle_records      import TLERecord                  # noqa: F401, E402
from app.db.models.missions         import Mission                    # noqa: F401, E402
from app.db.models.conjunction_events import ConjunctionEvent         # noqa: F401, E402
from app.db.models.orbital_events   import OrbitalEvent               # noqa: F401, E402
from app.db.models.audit_logs       import AuditLog                   # noqa: F401, E402

__all__ = ["Base"]
