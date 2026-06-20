"""
ORBITIQ-X — SQLAlchemy DeclarativeBase (standalone, no model imports).

All ORM models import Base from HERE.
app.db.base imports Base from here AND then imports all models for Alembic.
This breaks the circular: models -> base_model (no reimport), not models -> base -> models.
"""
from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORBITIQ-X ORM models."""
