"""
ORBITIQ-X — SSA API Schemas
=============================
Pydantic v2 request / response models for the Space Situational
Awareness endpoints (app/api/v1/endpoints/ssa.py).

These are the *wire* types — they define what the API accepts and
returns. They are deliberately separate from the DB model (Satellite)
so the API contract can evolve independently.

Classes
────────
  Request bodies:
    EphemerisRequest  — SGP4 propagation over a time window
    GroundPassRequest — ground station pass prediction

  Response envelopes:
    RSOCatalogResponse  — paginated RSO list
    RSODetailResponse   — single RSO full detail
    TLEResponse         — current TLE for one object
    EphemerisResponse   — time-series state vectors
    GroundPassResponse  — pass access windows
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, Field, model_validator


# ─── Shared sub-types ─────────────────────────────────────────────────────────

class StateVector(BaseModel):
    """ECI J2000 position + velocity at one epoch."""
    epoch:           datetime
    position_eci_km: list[float] = Field(..., min_length=3, max_length=3)
    velocity_eci_kms:list[float] = Field(..., min_length=3, max_length=3)
    latitude_deg:    float | None = None
    longitude_deg:   float | None = None
    altitude_km:     float | None = None


class GroundStation(BaseModel):
    """Ground station definition for pass prediction."""
    name:         str
    latitude_deg: Annotated[float, Field(ge=-90, le=90)]
    longitude_deg:Annotated[float, Field(ge=-180, le=180)]
    altitude_m:   float = 0.0
    min_elevation_deg: float = 5.0


class PassWindow(BaseModel):
    """Single pass access window over one ground station."""
    station_name:      str
    aos:               datetime   # Acquisition of Signal
    los:               datetime   # Loss of Signal
    tca:               datetime   # Time of Closest Approach
    max_elevation_deg: float
    duration_seconds:  float
    aos_azimuth_deg:   float | None = None
    los_azimuth_deg:   float | None = None


class RSOSummary(BaseModel):
    """Compact RSO representation for catalog listings."""
    norad_id:       int
    name:           str
    cospar_id:      str | None = None
    object_type:    str
    regime:         str | None = None
    status:         str
    country_code:   str | None = None
    operator_name:  str | None = None
    altitude_km:    float | None = None
    inclination_deg:float | None = None
    launch_date:    datetime | None = None
    tle_age_days:   float | None = None


class RSODetail(RSOSummary):
    """Full RSO detail including TLE and physical properties."""
    international_designator: str | None = None
    mission_type:    str | None = None
    launch_site:     str | None = None
    launch_vehicle:  str | None = None
    decay_date:      datetime | None = None
    expected_eol:    datetime | None = None
    mass_kg:         float | None = None
    span_m:          float | None = None
    radar_cross_section_m2: float | None = None
    hard_body_radius_km: float = 0.005
    perigee_km:      float | None = None
    apogee_km:       float | None = None
    raan_deg:        float | None = None
    eccentricity:    float | None = None
    mean_motion_rev_day: float | None = None
    period_minutes:  float | None = None
    tle_line1:       str | None = None
    tle_line2:       str | None = None
    tle_epoch:       datetime | None = None


# ─── Request bodies ───────────────────────────────────────────────────────────

class EphemerisRequest(BaseModel):
    """
    Request body for POST /ssa/propagate.
    Generates SGP4 state vectors over [start_epoch, stop_epoch].
    """
    norad_ids:    Annotated[list[int], Field(min_length=1, max_length=100)]
    start_epoch:  datetime
    stop_epoch:   datetime
    step_seconds: Annotated[int, Field(ge=10, le=86400)] = 60
    reference_frame: str = "ECI_J2000"

    @model_validator(mode="after")
    def stop_after_start(self) -> "EphemerisRequest":
        if self.start_epoch >= self.stop_epoch:
            raise ValueError("start_epoch must be before stop_epoch")
        return self


class GroundPassRequest(BaseModel):
    """
    Request body for POST /ssa/passes.
    Predicts satellite visibility over ground stations.
    """
    norad_id:       int
    stations:       Annotated[list[GroundStation], Field(min_length=1, max_length=50)]
    start_epoch:    datetime
    stop_epoch:     datetime
    min_elevation_deg: Annotated[float, Field(ge=0, le=90)] = 5.0

    @model_validator(mode="after")
    def stop_after_start(self) -> "GroundPassRequest":
        if self.start_epoch >= self.stop_epoch:
            raise ValueError("start_epoch must be before stop_epoch")
        return self


# ─── Response envelopes ───────────────────────────────────────────────────────

class RSOCatalogResponse(BaseModel):
    """Paginated RSO catalog listing."""
    total:     int
    page:      int
    page_size: int
    has_next:  bool
    items:     list[RSOSummary]


class RSODetailResponse(BaseModel):
    """Full detail for one RSO."""
    rso: RSODetail


class TLEResponse(BaseModel):
    """Current TLE for one RSO."""
    norad_id:   int
    name:       str
    tle_line1:  str
    tle_line2:  str
    epoch:      datetime | None = None
    age_days:   float | None   = None
    source:     str            = "space-track"


class EphemerisResponse(BaseModel):
    """Time-series state vectors for one or more RSOs."""
    generated_at:  datetime
    reference_frame: str = "ECI_J2000"
    objects: list[dict[str, Any]]   # {norad_id, name, vectors: [StateVector]}


class GroundPassResponse(BaseModel):
    """Pass windows for one RSO over the requested ground stations."""
    norad_id:  int
    name:      str
    passes:    list[PassWindow]
    total:     int
    generated_at: datetime
