"""
ORBITIQ-X Orbital Engine — Physical & Mathematical Constants
=============================================================
All constants used throughout the orbital engine are defined here.
Never use magic numbers in orbital calculations.

Units follow the ORBITIQ-X standard:
- Distance: kilometers [km]
- Velocity: km/s
- Time: seconds [s]
- Angles: radians (internal) / degrees (API interface)
- Mass: kilograms [kg]

References
----------
.. [1] Vallado, D. (2013). Fundamentals of Astrodynamics and Applications, 4th ed.
.. [2] WGS-84 standard (NIMA TR8350.2, 3rd edition, 2000)
.. [3] WGS-72 standard (as used in AFSPC SGP4)
"""
from typing import Final

# ─── Earth Gravity Constants (WGS-84) ────────────────────────────────────────
EARTH_RADIUS_KM: Final[float] = 6378.137          # Semi-major axis (equatorial) [km]
EARTH_RADIUS_POLAR_KM: Final[float] = 6356.752    # Semi-minor axis (polar) [km]
EARTH_FLATTENING: Final[float] = 1.0 / 298.257223563
MU_KM3_S2: Final[float] = 398600.4418             # Standard gravitational parameter [km³/s²]
J2_COEFFICIENT: Final[float] = 1.08262668355e-3   # Second zonal harmonic (oblateness)
J3_COEFFICIENT: Final[float] = -2.53265648533e-6  # Third zonal harmonic
J4_COEFFICIENT: Final[float] = -1.61962159137e-6  # Fourth zonal harmonic
EARTH_ROTATION_RATE_RAD_S: Final[float] = 7.2921150e-5   # [rad/s]
EARTH_MASS_KG: Final[float] = 5.972168e24                # [kg]

# ─── Earth Gravity Constants (WGS-72, AFSPC SGP4 standard) ──────────────────
WGS72_EARTH_RADIUS_KM: Final[float] = 6378.135
WGS72_MU_KM3_S2: Final[float] = 398600.8
WGS72_J2: Final[float] = 1.082616e-3
WGS72_J3: Final[float] = -2.53881e-6
WGS72_J4: Final[float] = -1.65597e-6

# ─── Physical Constants ───────────────────────────────────────────────────────
SPEED_OF_LIGHT_KM_S: Final[float] = 299792.458    # Speed of light [km/s]
GRAVITATIONAL_CONSTANT: Final[float] = 6.674e-20  # G [km³/(kg·s²)]
ASTRONOMICAL_UNIT_KM: Final[float] = 149597870.7  # 1 AU [km]
SOLAR_MASS_KG: Final[float] = 1.989e30            # [kg]
SOLAR_RADIUS_KM: Final[float] = 695700.0          # [km]
SOLAR_LUMINOSITY_W: Final[float] = 3.828e26        # [W]
SOLAR_FLUX_CONSTANT_W_M2: Final[float] = 1361.0   # Solar irradiance at 1 AU [W/m²]
BOLTZMANN_CONSTANT: Final[float] = 1.380649e-23   # [J/K]

# ─── Orbital Regime Boundaries ───────────────────────────────────────────────
# Altitude thresholds defining orbital regimes [km]
VLEO_MAX_ALT_KM: Final[float] = 450.0     # Very Low Earth Orbit ceiling
LEO_MAX_ALT_KM: Final[float] = 2000.0     # Low Earth Orbit ceiling
MEO_MIN_ALT_KM: Final[float] = 2000.0     # Medium Earth Orbit floor
MEO_MAX_ALT_KM: Final[float] = 35786.0    # MEO ceiling (GEO altitude)
GEO_ALT_KM: Final[float] = 35786.0        # Geostationary orbit altitude
GEO_ALT_TOLERANCE_KM: Final[float] = 200.0  # GEO classification band ±200 km
HEO_APOGEE_MIN_KM: Final[float] = 35786.0  # HEO minimum apogee

# SSO inclination band
SSO_INCLINATION_MIN_DEG: Final[float] = 96.0
SSO_INCLINATION_MAX_DEG: Final[float] = 100.0

# ─── Time Constants ──────────────────────────────────────────────────────────
SECONDS_PER_MINUTE: Final[float] = 60.0
SECONDS_PER_HOUR: Final[float] = 3600.0
SECONDS_PER_DAY: Final[float] = 86400.0
MINUTES_PER_DAY: Final[float] = 1440.0
JULIAN_CENTURY: Final[float] = 36525.0     # Julian days per Julian century
J2000_EPOCH_JD: Final[float] = 2451545.0   # J2000.0 epoch (Julian Date)

# ─── Mathematical Constants ───────────────────────────────────────────────────
import math
TWO_PI: Final[float] = 2.0 * math.pi
DEG_TO_RAD: Final[float] = math.pi / 180.0
RAD_TO_DEG: Final[float] = 180.0 / math.pi
ARCSEC_TO_RAD: Final[float] = math.pi / 648000.0

# ─── Conjunction Analysis Constants ──────────────────────────────────────────
# Default hard-body radii by object type [km]
HBR_ACTIVE_PAYLOAD_KM: Final[float] = 0.010      # 10 m typical satellite
HBR_ROCKET_BODY_KM: Final[float] = 0.005         # 5 m rocket body
HBR_DEBRIS_KM: Final[float] = 0.001              # 1 m small debris
HBR_CUBESAT_KM: Final[float] = 0.002             # 2 m CubeSat

# Conjunction alert thresholds
PC_RED_THRESHOLD: Final[float] = 1.0e-3          # Probability of Collision: Red
PC_YELLOW_THRESHOLD: Final[float] = 1.0e-4       # Probability of Collision: Yellow
MISS_DISTANCE_RED_KM: Final[float] = 0.5         # Miss distance alert: Red
MISS_DISTANCE_YELLOW_KM: Final[float] = 1.0      # Miss distance alert: Yellow
CONJUNCTION_SCREENING_RANGE_KM: Final[float] = 5.0  # Initial screening radius

# ─── Atmospheric Constants (NRLMSISE-00 / exponential model) ─────────────────
ATMOSPHERIC_SCALE_HEIGHT_KM: Final[float] = 8.5  # Approximate scale height at surface
REFERENCE_DENSITY_KG_M3: Final[float] = 1.225    # Air density at sea level [kg/m³]
STANDARD_DRAG_COEFFICIENT: Final[float] = 2.2     # Typical satellite Cd

# ─── WGS-84 Aliases for coordinate_transforms.py ─────────────────────────────
WGS84_A: Final[float]        = EARTH_RADIUS_KM               # semi-major axis [km]
WGS84_B: Final[float]        = EARTH_RADIUS_POLAR_KM         # semi-minor axis [km]
WGS84_E2: Final[float]       = 2 * EARTH_FLATTENING - EARTH_FLATTENING**2  # e²
EARTH_ROT_RAD_S: Final[float]= EARTH_ROTATION_RATE_RAD_S    # alias
