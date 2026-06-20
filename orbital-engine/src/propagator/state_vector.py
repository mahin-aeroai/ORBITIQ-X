"""
State Vector dataclasses — ECI, ECEF, Geodetic (LLA)
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime

EARTH_RADIUS_KM = 6371.0088
EARTH_A_KM = 6378.137       # WGS-84 semi-major axis
EARTH_F = 1 / 298.257223563 # WGS-84 flattening
EARTH_B_KM = EARTH_A_KM * (1 - EARTH_F)
EARTH_E2 = 1 - (EARTH_B_KM / EARTH_A_KM) ** 2


@dataclass(slots=True)
class StateVector:
    """ECI J2000 state vector (km, km/s)."""
    norad_id: int
    epoch: datetime
    x_km: float
    y_km: float
    z_km: float
    vx_kms: float
    vy_kms: float
    vz_kms: float

    @property
    def position(self) -> tuple[float, float, float]:
        return (self.x_km, self.y_km, self.z_km)

    @property
    def velocity(self) -> tuple[float, float, float]:
        return (self.vx_kms, self.vy_kms, self.vz_kms)

    @property
    def range_km(self) -> float:
        return math.sqrt(self.x_km**2 + self.y_km**2 + self.z_km**2)

    @property
    def altitude_km(self) -> float:
        return self.range_km - EARTH_RADIUS_KM

    @property
    def speed_kms(self) -> float:
        return math.sqrt(self.vx_kms**2 + self.vy_kms**2 + self.vz_kms**2)


@dataclass(slots=True)
class StateVectorECEF:
    """ECEF state vector (km, km/s)."""
    norad_id: int
    epoch: datetime
    x_km: float
    y_km: float
    z_km: float
    vx_kms: float
    vy_kms: float
    vz_kms: float


@dataclass(slots=True, frozen=True)
class GeodeticPoint:
    """WGS-84 geodetic coordinates."""
    latitude_deg: float   # -90 to +90
    longitude_deg: float  # -180 to +180
    altitude_km: float
    epoch: datetime | None = None
    norad_id: int | None = None
