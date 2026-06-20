"""ORBITIQ-X — Satellite operator model."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_model import Base


class Operator(Base):
    """Satellite operator — government agency, commercial company, or military."""
    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operator_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True,
        comment="e.g. OP-ISRO, OP-SPACEX")
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(String(64))
    operator_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="commercial",
        comment="government | commercial | military | academic | igo"
    )
    country_code: Mapped[Optional[str]] = mapped_column(String(3), index=True,
        comment="ISO-3166-1 alpha-3")
    country_name: Mapped[Optional[str]] = mapped_column(String(128))
    website: Mapped[Optional[str]] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(Text)
    founding_year: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    satellite_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
        comment="Denormalised — refreshed by scheduler")
    primary_mission_type: Mapped[Optional[str]] = mapped_column(String(64),
        comment="EO | comms | nav | science | military")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )

    satellites: Mapped[list["Satellite"]] = relationship(  # type: ignore[name-defined]
        back_populates="operator_rel", foreign_keys="Satellite.operator_id"
    )
    missions: Mapped[list["Mission"]] = relationship(  # type: ignore[name-defined]
        back_populates="operator_rel"
    )

    __table_args__ = (
        Index("ix_operators_country_type", "country_code", "operator_type"),
        Index("ix_operators_name", "name"),
    )
