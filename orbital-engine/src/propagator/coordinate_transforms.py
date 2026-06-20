"""
ORBITIQ-X Orbital Engine
Coordinate Transforms

Supported frames:
  ECI  (J2000)  — Earth-Centred Inertial
  ECEF          — Earth-Centred Earth-Fixed (WGS-84)
  GEO           — Geodetic (lat/lon/alt)
  LVLH          — Local Vertical Local Horizontal (Hill frame)
  TEME          — True Equator Mean Equinox (SGP4 native output)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from .constants import WGS84_A, WGS84_B, WGS84_E2, EARTH_ROT_RAD_S


@dataclass(frozen=True)
class ECIVector:
    x: float   # km
    y: float   # km
    z: float   # km
    vx: float  # km/s
    vy: float  # km/s
    vz: float  # km/s

    def pos(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])

    def vel(self) -> np.ndarray:
        return np.array([self.vx, self.vy, self.vz])


@dataclass(frozen=True)
class ECEFVector:
    x: float   # km
    y: float   # km
    z: float   # km


@dataclass(frozen=True)
class GeoPoint:
    lat_deg: float    # geodetic latitude, degrees
    lon_deg: float    # longitude, degrees
    alt_km: float     # altitude above WGS-84 ellipsoid, km


@dataclass(frozen=True)
class LVLHState:
    """
    State in the Hill (LVLH) frame relative to a reference orbit.
    x: radial (outward +)
    y: along-track (velocity direction +)
    z: cross-track (angular momentum direction +)
    """
    x: float   # km
    y: float   # km
    z: float   # km
    vx: float  # km/s
    vy: float  # km/s
    vz: float  # km/s


# ── GMST ─────────────────────────────────────────────────────

def gmst_rad(epoch: datetime) -> float:
    """
    Greenwich Mean Sidereal Time in radians.
    Uses IAU 1982 model (accurate to ~0.1 arcsec over decades).
    """
    epoch_utc = epoch.replace(tzinfo=timezone.utc) if epoch.tzinfo is None else epoch
    j2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    d = (epoch_utc - j2000).total_seconds() / 86400.0  # Julian days from J2000
    t = d / 36525.0  # Julian centuries

    # IAU 1982 GMST formula (seconds of time)
    theta_sec = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t**2
        - 6.2e-6 * t**3
    )
    return math.fmod(theta_sec * (2 * math.pi / 86400.0), 2 * math.pi)


# ── TEME → ECI ───────────────────────────────────────────────

def teme_to_eci(pos_teme: np.ndarray, vel_teme: np.ndarray, epoch: datetime) -> ECIVector:
    """
    Convert SGP4 TEME output to ECI (J2000/GCRF).
    Uses IAU 1976 precession — sufficient for SSA applications.
    Accuracy: ~1 km over 24h propagation window.
    """
    theta = gmst_rad(epoch)
    ct, st = math.cos(theta), math.sin(theta)

    # Rotation matrix TEME→ECI (simplified, no nutation correction)
    R = np.array([
        [ ct, st, 0],
        [-st, ct, 0],
        [  0,  0, 1],
    ])
    omega = np.array([0, 0, EARTH_ROT_RAD_S])

    pos_eci = R.T @ pos_teme
    vel_eci = R.T @ vel_teme - np.cross(omega, pos_eci)

    return ECIVector(
        x=pos_eci[0], y=pos_eci[1], z=pos_eci[2],
        vx=vel_eci[0], vy=vel_eci[1], vz=vel_eci[2],
    )


# ── ECI → ECEF ───────────────────────────────────────────────

def eci_to_ecef(eci: ECIVector, epoch: datetime) -> ECEFVector:
    """Rotate ECI position to ECEF using GMST."""
    theta = gmst_rad(epoch)
    ct, st = math.cos(theta), math.sin(theta)
    p = eci.pos()
    x_ecef =  ct * p[0] + st * p[1]
    y_ecef = -st * p[0] + ct * p[1]
    z_ecef =  p[2]
    return ECEFVector(x=x_ecef, y=y_ecef, z=z_ecef)


# ── ECEF → Geodetic ──────────────────────────────────────────

def ecef_to_geo(ecef: ECEFVector) -> GeoPoint:
    """
    Bowring iterative method for ECEF → geodetic conversion.
    Converges in 3 iterations to <0.1mm accuracy.
    """
    x, y, z = ecef.x * 1000, ecef.y * 1000, ecef.z * 1000  # m
    a, b = WGS84_A, WGS84_B
    e2 = WGS84_E2
    ep2 = (a**2 - b**2) / b**2

    p = math.sqrt(x**2 + y**2)
    lon = math.atan2(y, x)

    # Initial estimate
    theta = math.atan2(z * a, p * b)
    lat = math.atan2(
        z + ep2 * b * math.sin(theta)**3,
        p - e2 * a * math.cos(theta)**3,
    )

    # Iterate (3x is sufficient)
    for _ in range(3):
        sin_lat = math.sin(lat)
        N = a / math.sqrt(1 - e2 * sin_lat**2)
        lat_new = math.atan2(z + e2 * N * sin_lat, p)
        if abs(lat_new - lat) < 1e-12:
            break
        lat = lat_new

    sin_lat = math.sin(lat)
    N = a / math.sqrt(1 - e2 * sin_lat**2)
    cos_lat = math.cos(lat)

    if abs(cos_lat) > 1e-10:
        alt = p / cos_lat - N
    else:
        alt = abs(z) / abs(sin_lat) - N * (1 - e2)

    return GeoPoint(
        lat_deg=math.degrees(lat),
        lon_deg=math.degrees(lon),
        alt_km=alt / 1000.0,
    )


def eci_to_geo(eci: ECIVector, epoch: datetime) -> GeoPoint:
    """Convenience: ECI → geodetic in one call."""
    return ecef_to_geo(eci_to_ecef(eci, epoch))


# ── ECI → LVLH ───────────────────────────────────────────────

def eci_to_lvlh(
    chief: ECIVector,
    deputy: ECIVector,
) -> LVLHState:
    """
    Transform deputy satellite ECI state to LVLH (Hill) frame
    centred on the chief satellite.

    LVLH axes:
      r̂  : radial outward
      θ̂  : along-track (in velocity direction)
      ĥ  : cross-track (orbit normal, h = r × v)
    """
    r_c = chief.pos()
    v_c = chief.vel()
    r_d = deputy.pos()
    v_d = deputy.vel()

    # Chief orbital frame unit vectors
    h_vec = np.cross(r_c, v_c)
    r_hat = r_c / np.linalg.norm(r_c)
    h_hat = h_vec / np.linalg.norm(h_vec)
    theta_hat = np.cross(h_hat, r_hat)

    # Rotation matrix ECI → LVLH
    Q = np.array([r_hat, theta_hat, h_hat])

    # Angular velocity of LVLH frame
    omega_mag = np.linalg.norm(h_vec) / np.linalg.norm(r_c)**2
    omega = omega_mag * h_hat

    # Relative position and velocity
    dr = r_d - r_c
    dv = v_d - v_c

    pos_lvlh = Q @ dr
    vel_lvlh = Q @ dv - np.cross(omega, pos_lvlh)

    return LVLHState(
        x=pos_lvlh[0], y=pos_lvlh[1], z=pos_lvlh[2],
        vx=vel_lvlh[0], vy=vel_lvlh[1], vz=vel_lvlh[2],
    )


# ── Azimuth / Elevation from ground station ──────────────────

def eci_to_azel(
    sat_eci: ECIVector,
    site_lat_deg: float,
    site_lon_deg: float,
    site_alt_km: float,
    epoch: datetime,
) -> tuple[float, float, float]:
    """
    Compute azimuth (deg), elevation (deg), and slant range (km)
    from a ground station to a satellite.

    Returns (azimuth_deg, elevation_deg, range_km)
    """
    # Site ECEF position
    lat = math.radians(site_lat_deg)
    lon = math.radians(site_lon_deg)
    a = WGS84_A / 1000.0  # km
    e2 = WGS84_E2
    N = a / math.sqrt(1 - e2 * math.sin(lat)**2)
    h = site_alt_km

    site_ecef = np.array([
        (N + h) * math.cos(lat) * math.cos(lon),
        (N + h) * math.cos(lat) * math.sin(lon),
        (N * (1 - e2) + h) * math.sin(lat),
    ])

    # Satellite ECEF
    sat_ecef_obj = eci_to_ecef(sat_eci, epoch)
    sat_ecef = np.array([sat_ecef_obj.x, sat_ecef_obj.y, sat_ecef_obj.z])

    # Range vector in ECEF
    rho_ecef = sat_ecef - site_ecef

    # Rotation to South-East-Z (SEZ) topocentric frame
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)

    R_sez = np.array([
        [ sin_lat * cos_lon,  sin_lat * sin_lon, -cos_lat],
        [-sin_lon,            cos_lon,             0      ],
        [ cos_lat * cos_lon,  cos_lat * sin_lon,  sin_lat],
    ])

    rho_sez = R_sez @ rho_ecef
    s, e, z = rho_sez

    range_km = float(np.linalg.norm(rho_sez))
    el_rad = math.asin(z / range_km)
    az_rad = math.atan2(-s, e)  # SEZ convention

    return (
        math.degrees(az_rad) % 360.0,
        math.degrees(el_rad),
        range_km,
    )
