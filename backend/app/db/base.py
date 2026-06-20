"""
ORBITIQ-X — SQLAlchemy declarative base + all model imports for Alembic.

Models import Base from app.db.base_model (no circular dependency).
This file imports Base from base_model and then imports all models,
giving Alembic a single import point.
"""
from __future__ import annotations

# Re-export Base so existing code that imports from here still works
from app.db.base_model import Base  # noqa: F401

# Import all models so Alembic autogenerate sees them
from app.db.models.users            import User, UserSession         # noqa: F401, E402
from app.db.models.operators        import Operator                   # noqa: F401, E402
from app.db.models.satellites       import Satellite                  # noqa: F401, E402
from app.db.models.tle_records      import TLERecord                  # noqa: F401, E402
from app.db.models.missions         import Mission                    # noqa: F401, E402
from app.db.models.conjunction_events import ConjunctionEvent         # noqa: F401, E402
from app.db.models.orbital_events   import OrbitalEvent               # noqa: F401, E402
from app.db.models.audit_logs       import AuditLog                   # noqa: F401, E402

__all__ = ["Base"]
