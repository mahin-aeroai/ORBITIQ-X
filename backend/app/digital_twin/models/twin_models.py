"""
ORBITIQ-X — Digital Twin Data Models
======================================
Pure Python dataclasses for the Digital Twin subsystem.
No SQLAlchemy, no FastAPI, no external dependencies.

These classes are the canonical data structures shared across:
  • OrbitalStateService   (propagation output)
  • OrbitForecastService  (forecast output)
  • OrbitalDensityEngine  (density map output)
  • ManeuverSimulationService (simulation output)
  • DigitalTwinRepository (persistence / retrieval)
  • digital_twin.py API endpoints (response serialisation)

All classes implement to_dict() for JSON serialisation.
All fields that are Optional default to None so callers can
construct instances with only the fields they know.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ─── Enumerations ────────────────────────────────────────────────────────────

class OrbitalRegimeEnum(str, Enum):
    """Orbital regime classification used throughout the Digital Twin."""
    VLEO     = "VLEO"       # Very Low Earth Orbit  <450 km
    LEO      = "LEO"        # Low Earth Orbit  450–2 000 km
    SSO      = "SSO"        # Sun-Synchronous Orbit (LEO subset, ~97–98°)
    MEO      = "MEO"        # Medium Earth Orbit  2 000–35 000 km
    GEO      = "GEO"        # Geostationary / Geosynchronous  ~35 786 km
    GTO      = "GTO"        # Geostationary Transfer Orbit
    HEO      = "HEO"        # Highly Elliptical Orbit
    CISLUNAR = "CISLUNAR"   # Beyond GEO / cislunar space
    UNKNOWN  = "UNKNOWN"


class ObjectType(str, Enum):
    """RSO object classification."""
    SATELLITE    = "SATELLITE"
    DEBRIS       = "DEBRIS"
    ROCKET_BODY  = "ROCKET_BODY"
    UNKNOWN      = "UNKNOWN"


# ─── SatelliteState ───────────────────────────────────────────────────────────

@dataclass
class SatelliteState:
    """
    Single-epoch propagated state for one Resident Space Object.

    Produced by OrbitalStateService._propagate_batch_sync() and stored
    in the in-memory live-state cache (_LIVE_STATES dict).
    """
    norad_id:             int
    name:                 str                         = "UNKNOWN"
    object_type:          ObjectType                  = ObjectType.UNKNOWN
    epoch:                datetime | None             = None
    # ECI position/velocity (J2000 frame, km and km/s)
    position_eci_km:      list[float]                 = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity_eci_kms:     list[float]                 = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # Geodetic coordinates
    latitude_deg:         float                       = 0.0
    longitude_deg:        float                       = 0.0
    altitude_km:          float                       = 0.0
    speed_kms:            float                       = 0.0
    # Orbital elements (Keplerian)
    orbital_regime:       OrbitalRegimeEnum           = OrbitalRegimeEnum.UNKNOWN
    inclination_deg:      float | None                = None
    perigee_km:           float | None                = None
    apogee_km:            float | None                = None
    period_min:           float | None                = None
    raan_deg:             float | None                = None
    eccentricity:         float | None                = None
    # Propagation quality
    propagation_ok:       bool                        = True
    propagation_error:    str | None                  = None
    error_code:           int | None                  = None   # SGP4 error code (0=ok)
    # Additional computed state
    position_ecef_km:     list[float] | None          = None   # ECEF frame
    tle_epoch:            datetime | None             = None   # Epoch of the TLE used
    tle_age_days:         float | None                = None   # Age of TLE at propagation
    # Decay / reentry
    decay_rate_km_day:    float | None                = None
    reentry_predicted:    bool                        = False
    reentry_epoch:        datetime | None             = None
    lifetime_days:        float | None                = None

    @property
    def position_magnitude_km(self) -> float:
        """Euclidean magnitude of the ECI position vector."""
        return math.sqrt(sum(x * x for x in self.position_eci_km))

    def to_dict(self) -> dict[str, Any]:
        return {
            "norad_id":          self.norad_id,
            "name":              self.name,
            "object_type":       self.object_type.value if self.object_type else None,
            "epoch":             self.epoch.isoformat() if self.epoch else None,
            "position_eci_km":   self.position_eci_km,
            "velocity_eci_kms":  self.velocity_eci_kms,
            "latitude_deg":      self.latitude_deg,
            "longitude_deg":     self.longitude_deg,
            "altitude_km":       self.altitude_km,
            "speed_kms":         self.speed_kms,
            "orbital_regime":    self.orbital_regime.value if self.orbital_regime else None,
            "inclination_deg":   self.inclination_deg,
            "perigee_km":        self.perigee_km,
            "apogee_km":         self.apogee_km,
            "period_min":        self.period_min,
            "raan_deg":          self.raan_deg,
            "eccentricity":      self.eccentricity,
            "propagation_ok":    self.propagation_ok,
            "propagation_error": self.propagation_error,
            "error_code":        self.error_code,
            "position_ecef_km":  self.position_ecef_km,
            "tle_epoch":         self.tle_epoch.isoformat() if self.tle_epoch else None,
            "tle_age_days":      self.tle_age_days,
            "decay_rate_km_day": self.decay_rate_km_day,
            "reentry_predicted": self.reentry_predicted,
            "reentry_epoch":     self.reentry_epoch.isoformat() if self.reentry_epoch else None,
            "lifetime_days":     self.lifetime_days,
        }


# ─── TrajectoryPoint ──────────────────────────────────────────────────────────

@dataclass
class TrajectoryPoint:
    """
    Single time-step in an orbital forecast trajectory.
    Produced by OrbitForecastService._propagate_trajectory_sync().
    """
    epoch:            str              # ISO 8601 UTC string
    position_eci_km:  list[float]      # [x, y, z] km
    altitude_km:      float
    latitude_deg:     float
    longitude_deg:    float


# ─── OrbitForecast ────────────────────────────────────────────────────────────

@dataclass
class OrbitForecast:
    """
    Multi-step orbital forecast produced by OrbitForecastService.
    Returned by GET /digital-twin/forecast/{norad_id}.
    """
    norad_id:          int
    name:              str
    generated_at:      datetime
    horizon_days:      float                       = 1.0
    step_minutes:      int                         = 5
    trajectory:        list[TrajectoryPoint]       = field(default_factory=list)
    reentry_predicted: bool                        = False
    reentry_epoch:     datetime | None             = None
    lifetime_days:     float | None                = None
    decay_rate_km_day: float | None                = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "norad_id":          self.norad_id,
            "name":              self.name,
            "generated_at":      self.generated_at.isoformat(),
            "horizon_days":      self.horizon_days,
            "step_minutes":      self.step_minutes,
            "trajectory": [
                {
                    "epoch":           pt.epoch,
                    "position_eci_km": pt.position_eci_km,
                    "altitude_km":     pt.altitude_km,
                    "latitude_deg":    pt.latitude_deg,
                    "longitude_deg":   pt.longitude_deg,
                }
                for pt in self.trajectory
            ],
            "reentry_predicted": self.reentry_predicted,
            "reentry_epoch":     self.reentry_epoch.isoformat() if self.reentry_epoch else None,
            "lifetime_days":     self.lifetime_days,
            "decay_rate_km_day": self.decay_rate_km_day,
        }


# ─── DensityCell ─────────────────────────────────────────────────────────────

@dataclass
class DensityCell:
    """
    One altitude band in the orbital density map.
    Produced by OrbitalDensityEngine.compute_density_map().
    """
    alt_min_km:               float
    alt_max_km:               float
    regime:                   OrbitalRegimeEnum
    object_count:             int               = 0
    satellites:               int               = 0
    debris:                   int               = 0
    rocket_bodies:            int               = 0
    volume_km3:               float             = 0.0
    density_per_km3:          float             = 0.0
    congestion_index:         float             = 0.0
    collision_exposure_index: float             = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "alt_min_km":               self.alt_min_km,
            "alt_max_km":               self.alt_max_km,
            "regime":                   self.regime.value,
            "object_count":             self.object_count,
            "satellites":               self.satellites,
            "debris":                   self.debris,
            "rocket_bodies":            self.rocket_bodies,
            "volume_km3":               self.volume_km3,
            "density_per_km3":          self.density_per_km3,
            "congestion_index":         self.congestion_index,
            "collision_exposure_index": self.collision_exposure_index,
        }


# ─── OrbitalDensityMap ────────────────────────────────────────────────────────

@dataclass
class OrbitalDensityMap:
    """
    Complete orbital density snapshot across all altitude bands.
    Produced by OrbitalDensityEngine.compute_density_map().
    Stored in _DENSITY_SNAPSHOT.
    """
    generated_at:   datetime
    total_objects:  int                 = 0
    cells:          list[DensityCell]   = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at":  self.generated_at.isoformat(),
            "total_objects": self.total_objects,
            "cells":         [c.to_dict() for c in self.cells],
        }


# ─── RegimeHealth ─────────────────────────────────────────────────────────────

@dataclass
class RegimeHealth:
    """Health assessment for a single orbital regime."""
    regime:                   OrbitalRegimeEnum
    object_count:             int               = 0
    active_satellites:        int               = 0
    debris_count:             int               = 0
    active_conjunctions:      int               = 0
    high_risk_conjunctions:   int               = 0
    congestion_index:         float             = 0.0
    collision_exposure_index: float             = 0.0
    sustainability_score:     float             = 1.0
    trend:                    str               = "stable"   # stable|degrading|improving
    alert_level:              str               = "green"    # green|yellow|orange|red

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime":                   self.regime.value,
            "object_count":             self.object_count,
            "active_satellites":        self.active_satellites,
            "debris_count":             self.debris_count,
            "active_conjunctions":      self.active_conjunctions,
            "high_risk_conjunctions":   self.high_risk_conjunctions,
            "congestion_index":         self.congestion_index,
            "collision_exposure_index": self.collision_exposure_index,
            "sustainability_score":     self.sustainability_score,
            "trend":                    self.trend,
            "alert_level":              self.alert_level,
        }


# ─── SpaceEnvironmentHealth ───────────────────────────────────────────────────

@dataclass
class SpaceEnvironmentHealth:
    """
    Aggregate space environment health assessment.
    Produced by OrbitalDensityEngine.compute_regime_health().
    Stored in _HEALTH_SNAPSHOT.
    """
    # Both assessed_at and generated_at are accepted (aliases for the same concept)
    assessed_at:    datetime | None     = None
    generated_at:   datetime | None     = None
    total_tracked:  int                 = 0
    overall_alert:  str                 = "green"  # green|yellow|orange|red
    regimes:        list[RegimeHealth]  = field(default_factory=list)
    top_concerns:   list[str]           = field(default_factory=list)

    def __post_init__(self):
        # Normalize: whichever is set becomes the canonical timestamp
        if self.assessed_at and not self.generated_at:
            self.generated_at = self.assessed_at
        elif self.generated_at and not self.assessed_at:
            self.assessed_at = self.generated_at
        elif not self.assessed_at:
            from datetime import datetime, timezone
            self.assessed_at = self.generated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        ts = (self.assessed_at or self.generated_at)
        return {
            "assessed_at":   ts.isoformat() if ts else None,
            "generated_at":  ts.isoformat() if ts else None,
            "total_tracked": self.total_tracked,
            "overall_alert": self.overall_alert,
            "regimes":       [r.to_dict() for r in self.regimes],
            "top_concerns":  self.top_concerns,
        }


# ─── ManeuverScenario ─────────────────────────────────────────────────────────

@dataclass
class ManeuverScenario:
    """
    Input parameters for a maneuver simulation.
    POST /digital-twin/maneuver request body.
    """
    norad_id:    int
    delta_v_kms: float                 = 0.0
    direction:   str                   = "prograde"  # prograde|retrograde|radial|normal
    description: str                   = ""
    burn_epoch:  "datetime | None"     = None   # If None, defaults to current epoch

    def to_dict(self) -> dict[str, Any]:
        return {
            "norad_id":    self.norad_id,
            "delta_v_kms": self.delta_v_kms,
            "direction":   self.direction,
            "description": self.description,
            "burn_epoch":  self.burn_epoch.isoformat() if self.burn_epoch else None,
        }


# ─── SimulationResult ────────────────────────────────────────────────────────

@dataclass
class SimulationResult:
    """
    Output of ManeuverSimulationService.simulate().
    Returned by POST /digital-twin/maneuver.
    """
    norad_id:          int
    name:              str
    scenario:          ManeuverScenario
    simulated_at:      datetime
    # Pre-maneuver orbital elements
    pre_perigee_km:    float                    = 0.0
    pre_apogee_km:     float                    = 0.0
    pre_period_min:    float                    = 0.0
    # Post-maneuver orbital elements
    post_perigee_km:   float                    = 0.0
    post_apogee_km:    float                    = 0.0
    post_period_min:   float                    = 0.0
    # Summary
    delta_altitude_km: float                    = 0.0
    fuel_mass_kg:      float                    = 0.0
    safe_to_execute:   bool                     = True
    safety_notes:      list[str]                = field(default_factory=list)
    post_trajectory:   list[dict[str, Any]]     = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "norad_id":         self.norad_id,
            "name":             self.name,
            "scenario":         self.scenario.to_dict(),
            "simulated_at":     self.simulated_at.isoformat(),
            "before": {
                "perigee_km":   self.pre_perigee_km,
                "apogee_km":    self.pre_apogee_km,
                "period_min":   self.pre_period_min,
            },
            "after": {
                "perigee_km":   self.post_perigee_km,
                "apogee_km":    self.post_apogee_km,
                "period_min":   self.post_period_min,
            },
            "delta_altitude_km": self.delta_altitude_km,
            "fuel_mass_kg":      self.fuel_mass_kg,
            "safe_to_execute":   self.safe_to_execute,
            "safety_notes":      self.safety_notes,
            "post_trajectory":   self.post_trajectory,
        }
