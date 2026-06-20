"""
ORBITIQ-X Orbital Engine
Re-entry Monitor

Predicts atmospheric re-entry for objects with decaying orbits.

Approach:
  1. Identify candidates: perigee < 300 km OR decay rate > threshold
  2. Estimate decay using exponential atmosphere model (NRLMSISE-00 lookup table)
  3. Refine with ballistic coefficient and solar flux F10.7
  4. Issue alerts at: 7-day, 72-hour, 24-hour, 6-hour, 1-hour windows

Accuracy:
  ±20% decay lifetime for LEO (<400 km) with known Bstar
  ±50% for sparse tracking / unknown area-to-mass ratio
  DO NOT use for life safety decisions — use USSPACECOM TIP messages.

References:
  NRLMSISE-00: Picone et al. (2002), JGR Space Physics 107(A12)
  Drag model: King-Hele (1987) "Satellite Orbits in an Atmosphere"
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6378.137
EARTH_MU        = 398600.4418   # km³/s²

# NRLMSISE-00 approximate scale heights (km) by altitude band
# Format: (alt_km_lo, alt_km_hi, H_km, rho_0_kg_m3)
_DENSITY_TABLE = [
    (0,    100,  8.5,   1.225),
    (100,  200,  6.0,   5.6e-7),
    (200,  300,  7.0,   2.5e-10),
    (300,  400,  8.0,   1.9e-11),
    (400,  500,  8.5,   6.0e-12),
    (500,  600,  9.5,   1.6e-12),
    (600,  700,  10.0,  4.5e-13),
    (700,  800,  10.5,  1.3e-13),
    (800,  900,  11.0,  3.9e-14),
    (900,  1000, 11.5,  1.2e-14),
    (1000, 2000, 14.0,  3.5e-15),
]


class AlertLevel(str, Enum):
    WATCH   = "WATCH"     # 7 days
    WARNING = "WARNING"   # 72 hours
    URGENT  = "URGENT"    # 24 hours
    CRITICAL = "CRITICAL" # 6 hours
    IMMINENT = "IMMINENT" # 1 hour


@dataclass
class ReentryPrediction:
    norad_id: int
    object_name: str
    current_perigee_km: float
    current_apogee_km: float
    bstar: float                        # SGP4 drag term (1/R_E)
    area_to_mass_m2_kg: float | None    # if known
    predicted_reentry: datetime
    uncertainty_hours: float            # ±uncertainty
    lifetime_days: float
    decay_rate_km_per_day: float
    alert_level: AlertLevel
    survival_probability: float         # fraction that may reach surface
    geographic_uncertainty_km: float    # footprint uncertainty
    f107_index: float                   # solar flux used
    computed_at: datetime = None

    def __post_init__(self):
        if self.computed_at is None:
            self.computed_at = datetime.now(timezone.utc)


def atmospheric_density_kg_m3(alt_km: float, f107: float = 150.0) -> float:
    """
    Approximate atmospheric density using exponential model with
    F10.7 solar flux correction.

    F10.7 = 70  → quiet sun (solar minimum)
    F10.7 = 150 → moderate activity
    F10.7 = 250 → high activity (density can be 5-10× quiet sun)
    """
    if alt_km <= 0:
        return 1.225  # sea level

    # Find altitude band
    rho_0 = 3.5e-15
    H_km  = 14.0

    for lo, hi, H, r0 in _DENSITY_TABLE:
        if lo <= alt_km < hi:
            H_km  = H
            rho_0 = r0
            ref_alt = (lo + hi) / 2.0
            rho = r0 * math.exp(-(alt_km - ref_alt) / H_km)
            # Solar activity correction (Bowman 2008 simplified)
            f107_correction = 1.0 + 0.012 * (f107 - 150.0)
            return rho * max(0.5, f107_correction)

    return 3.5e-15  # above 1000 km


def orbital_decay_rate_km_day(
    semi_major_axis_km: float,
    eccentricity: float,
    bstar: float,
    f107: float = 150.0,
) -> float:
    """
    Estimate semi-major axis decay rate using the King-Hele formula.

    da/dt = -ρ * Cd * A/m * v² * (1 + e²/2)  [approximate]

    For quick estimates, uses Bstar (SGP4 drag term) which absorbs
    the Cd * A/m / (2 * ρ₀) term.

    Returns: decay rate in km/day (negative = decaying)
    """
    alt_km = semi_major_axis_km - EARTH_RADIUS_KM
    rho = atmospheric_density_kg_m3(alt_km, f107)  # kg/m³

    n = math.sqrt(EARTH_MU / semi_major_axis_km**3)  # rad/s
    v = n * semi_major_axis_km  # circular velocity approx (km/s)
    v_m_s = v * 1000.0  # m/s

    # SGP4 Bstar = Cd*A/(2m) * rho_0 / (2 * R_E)  [1/R_E]
    # Convert: Bstar [1/R_E] → Cd*A/m [m²/kg]
    # rho_0 in SGP4 = 2.461e-5 kg/m² (unit sphere drag) — historical constant
    RHO_0_SGP4 = 2.461e-5  # kg/m² (SGP4 historical)
    R_E_M = EARTH_RADIUS_KM * 1000.0  # m
    cd_a_m = (2.0 * bstar * R_E_M) / RHO_0_SGP4 if abs(bstar) > 1e-10 else 2.2e-3

    # King-Hele drag
    da_dt_m_s2 = -rho * cd_a_m * v_m_s**2 * (1 + 1.5 * eccentricity**2)  # m/s²
    da_dt_km_s = da_dt_m_s2 / 1000.0  # km/s²
    da_dt_km_day = da_dt_km_s * 86400.0  # km/day

    return da_dt_km_day


def predict_reentry(
    norad_id: int,
    name: str,
    tle_line1: str,
    tle_line2: str,
    f107: float = 150.0,
    epoch: datetime | None = None,
) -> ReentryPrediction | None:
    """
    Predict re-entry date for an object.

    Uses a simple energy dissipation model, integrating the decay rate
    from current altitude to 80 km (conventional re-entry interface).
    Step size: 1 day.

    Returns None if object is not decaying (lifetime > 200 years).
    """
    from sgp4.api import Satrec
    from sgp4.conveniences import sat_epoch_datetime

    epoch = epoch or datetime.now(timezone.utc)

    try:
        sat = Satrec.twoline2rv(tle_line1, tle_line2)
    except Exception as e:
        logger.warning(f"TLE parse failed for {norad_id}: {e}")
        return None

    # Extract elements
    # sat.no_kozai is in rad/min (SGP4 internal unit).
    # Correct conversion to rev/day: multiply by (1440 min/day / 2π rad/rev)
    # BUG FIX: previous code divided instead of multiplied, giving a value
    # ~8.77 million times too small, making a_km wildly incorrect.
    n_rev_day = sat.no_kozai * (1440.0 / (2 * math.pi))   # rad/min → rev/day
    n_rad_s   = sat.no_kozai / 60.0                        # rad/min → rad/s
    a_km      = (EARTH_MU / n_rad_s**2) ** (1.0 / 3.0)    # km
    e         = sat.ecco
    bstar     = sat.bstar

    perigee = a_km * (1 - e) - EARTH_RADIUS_KM
    apogee  = a_km * (1 + e) - EARTH_RADIUS_KM

    # Quick check: if perigee > 600 km, skip (lifetime > decades)
    if perigee > 600.0:
        return None

    # Integrate decay
    REENTRY_ALT = 80.0  # km — conventional re-entry interface
    DT_DAYS     = 1.0   # integration step

    current_a = a_km
    days = 0
    MAX_DAYS = 365 * 50  # don't integrate beyond 50 years

    while days < MAX_DAYS:
        alt = current_a - EARTH_RADIUS_KM
        if alt <= REENTRY_ALT:
            break
        da = orbital_decay_rate_km_day(current_a, e, bstar, f107)
        if da >= 0:
            # No decay (thrust or numerical issue)
            return None
        current_a += da * DT_DAYS  # decay reduces semi-major axis
        days += DT_DAYS

    if days >= MAX_DAYS:
        return None  # effectively stable orbit

    # Uncertainty: ±20% of lifetime for tracked objects, ±50% for untracked
    uncertainty_factor = 0.20 if perigee > 100 else 0.40
    uncertainty_hours = days * 24 * uncertainty_factor

    reentry_epoch = epoch + timedelta(days=days)

    # Alert level
    if days < 1/24:
        alert = AlertLevel.IMMINENT
    elif days < 0.25:
        alert = AlertLevel.CRITICAL
    elif days < 1.0:
        alert = AlertLevel.URGENT
    elif days < 3.0:
        alert = AlertLevel.WARNING
    elif days < 7.0:
        alert = AlertLevel.WATCH
    else:
        return None  # beyond alert threshold, monitor only

    # Survival probability (fraction of mass reaching ground)
    # Objects < 500 kg typically fully ablate. Larger objects may survive.
    survival_prob = min(1.0, max(0.0, (perigee - 100.0) / 200.0 * 0.3))

    # Geographic footprint uncertainty (grows with lead time)
    geo_uncertainty = min(40_000.0, days * 24.0 * 100.0)  # km

    return ReentryPrediction(
        norad_id=norad_id,
        object_name=name,
        current_perigee_km=perigee,
        current_apogee_km=apogee,
        bstar=bstar,
        area_to_mass_m2_kg=None,
        predicted_reentry=reentry_epoch,
        uncertainty_hours=uncertainty_hours,
        lifetime_days=days,
        decay_rate_km_per_day=abs(orbital_decay_rate_km_day(a_km, e, bstar, f107)),
        alert_level=alert,
        survival_probability=survival_prob,
        geographic_uncertainty_km=geo_uncertainty,
        f107_index=f107,
    )


class ReentryMonitor:
    """
    Monitors an RSO catalog for imminent re-entries.
    Called by the scheduler every 6 hours.
    """

    def __init__(self, f107: float = 150.0):
        self.f107 = f107

    def scan_catalog(
        self,
        catalog: list[dict],  # {norad_id, name, tle_line1, tle_line2, perigee_km}
        epoch: datetime | None = None,
    ) -> list[ReentryPrediction]:
        """
        Scan catalog and return all objects with imminent re-entry alerts.
        Pre-filters on perigee < 350 km before running full prediction.
        """
        epoch = epoch or datetime.now(timezone.utc)
        predictions = []

        candidates = [obj for obj in catalog if obj.get("perigee_km", 999) < 350.0]
        logger.info(f"Re-entry scan: {len(candidates)} candidates from {len(catalog)} objects")

        for obj in candidates:
            try:
                pred = predict_reentry(
                    norad_id=obj["norad_id"],
                    name=obj["name"],
                    tle_line1=obj["tle_line1"],
                    tle_line2=obj["tle_line2"],
                    f107=self.f107,
                    epoch=epoch,
                )
                if pred is not None:
                    predictions.append(pred)
            except Exception as e:
                logger.warning(f"Re-entry prediction failed for {obj.get('norad_id')}: {e}")

        return sorted(predictions, key=lambda p: p.lifetime_days)
