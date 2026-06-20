"""
ORBITIQ-X Orbital Engine
Propagation Validators

All public functions in this module are called at the boundary of
every SGP4 propagation call. Failures raise immediately — no silent
degraded-accuracy propagation is permitted.

This module was identified as completely missing in the June 2026 audit
(causing ImportError on the first import of sgp4_propagator.py).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

from .time_utils import JulianDateError, datetime_to_julian, JD_MIN, JD_MAX


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum TLE age beyond which accuracy is considered degraded.
#: SGP4 positional error grows approximately linearly: ~1 km/day for LEO.
_MAX_TLE_AGE_WARN_DAYS: float = 7.0
_MAX_TLE_AGE_ERROR_DAYS: float = 30.0

#: Physically plausible altitude bounds for an Earth-orbiting object.
_MIN_ALTITUDE_KM: float = 80.0    # below this = re-entry interface
_MAX_ALTITUDE_KM: float = 400_000.0  # beyond GEO + margin

#: Speed bounds for an Earth-orbiting object (km/s).
#: Escape velocity from Earth surface ~11.2 km/s; circular LEO ~7.8 km/s.
_MIN_SPEED_KMS: float = 0.5    # sub-orbital debris
_MAX_SPEED_KMS: float = 12.0   # above escape velocity = error


# ---------------------------------------------------------------------------
# TLE epoch validator
# ---------------------------------------------------------------------------

class TLEEpochError(ValueError):
    """Raised when a TLE's epoch is stale or malformed."""
    pass


def validate_tle_epoch(tle: object, max_age_days: float = _MAX_TLE_AGE_ERROR_DAYS) -> None:
    """
    Validate that a TLE's epoch is recent enough for accurate propagation.

    Parameters
    ----------
    tle : TwoLineElement
        Any object with an ``epoch`` attribute of type ``datetime``.
    max_age_days : float
        Maximum acceptable age in days. Default 30 days.
        Propagation accuracy degrades ~1 km/day for LEO objects.

    Raises
    ------
    TLEEpochError
        If the TLE epoch is more than ``max_age_days`` old,
        is in the future (corrupt TLE), or is not UTC-aware.
    """
    epoch: datetime = getattr(tle, "epoch", None)

    if epoch is None:
        raise TLEEpochError(
            f"TLE object {tle!r} has no 'epoch' attribute. "
            "Ensure you are passing a parsed TwoLineElement, not raw strings."
        )

    if not isinstance(epoch, datetime):
        raise TLEEpochError(
            f"TLE epoch must be a datetime, got {type(epoch).__name__!r}"
        )

    if epoch.tzinfo is None:
        raise TLEEpochError(
            "TLE epoch is timezone-naive. Attach timezone.utc during TLE parsing."
        )

    now = datetime.now(timezone.utc)
    age_days = (now - epoch).total_seconds() / 86400.0

    if age_days < -1.0:
        # Future TLE epoch > 1 day ahead — almost always a parsing error
        raise TLEEpochError(
            f"TLE epoch {epoch.isoformat()} is {-age_days:.1f} days in the future. "
            f"This indicates a TLE parsing error or corrupt data. "
            f"Current UTC: {now.isoformat()}"
        )

    if age_days > max_age_days:
        raise TLEEpochError(
            f"TLE epoch {epoch.isoformat()} is {age_days:.1f} days old "
            f"(limit: {max_age_days:.0f} days). "
            f"Fetch a fresh TLE from CelesTrak or Space-Track before propagating. "
            f"SGP4 positional error at this age: ~{age_days:.0f} km for LEO objects."
        )

    # Validate the epoch produces a valid Julian Date (catches garbled data)
    try:
        datetime_to_julian(epoch)
    except (JulianDateError, ValueError) as exc:
        raise TLEEpochError(
            f"TLE epoch {epoch.isoformat()} does not convert to a valid Julian Date: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# State vector validator
# ---------------------------------------------------------------------------

class StateVectorError(ValueError):
    """Raised when a propagated state vector is physically implausible."""
    pass


def validate_state_vector(sv: object) -> None:
    """
    Validate a propagated ECI state vector for physical plausibility.

    Catches:
    - NaN / Inf components (SGP4 divergence with error_code=0)
    - Altitude outside Earth-orbit regime
    - Speed above escape velocity or below plausible debris speed

    Parameters
    ----------
    sv : StateVector
        Object with ``position_eci_km`` and ``velocity_eci_km_s`` array
        attributes, and a ``norad_id`` integer attribute.

    Raises
    ------
    StateVectorError
        On any physically implausible value.
    """
    pos = getattr(sv, "position_eci_km", None)
    vel = getattr(sv, "velocity_eci_km_s", None)
    norad = getattr(sv, "norad_id", "unknown")

    if pos is None or vel is None:
        raise StateVectorError(
            f"StateVector for NORAD {norad} is missing position or velocity arrays."
        )

    # NaN / Inf check — can happen even when error_code=0 in some SGP4 edge cases
    for i, component in enumerate(pos):
        if not math.isfinite(float(component)):
            raise StateVectorError(
                f"NORAD {norad}: position component [{i}] = {component} is not finite. "
                f"Check for corrupt TLE data or a near-zero mean motion."
            )

    for i, component in enumerate(vel):
        if not math.isfinite(float(component)):
            raise StateVectorError(
                f"NORAD {norad}: velocity component [{i}] = {component} is not finite."
            )

    # Altitude check
    r_mag = float(sum(float(p)**2 for p in pos) ** 0.5)
    alt_km = r_mag - 6378.137  # WGS-84 equatorial radius

    if alt_km < _MIN_ALTITUDE_KM:
        raise StateVectorError(
            f"NORAD {norad}: altitude {alt_km:.1f} km is below the re-entry interface "
            f"({_MIN_ALTITUDE_KM:.0f} km). Object has likely decayed."
        )

    if alt_km > _MAX_ALTITUDE_KM:
        raise StateVectorError(
            f"NORAD {norad}: altitude {alt_km:.1f} km is above the maximum "
            f"({_MAX_ALTITUDE_KM:.0f} km). This indicates a propagation error."
        )

    # Speed check
    v_mag = float(sum(float(v)**2 for v in vel) ** 0.5)

    if v_mag < _MIN_SPEED_KMS:
        raise StateVectorError(
            f"NORAD {norad}: speed {v_mag:.3f} km/s is below minimum "
            f"({_MIN_SPEED_KMS} km/s). Physically implausible for orbital object."
        )

    if v_mag > _MAX_SPEED_KMS:
        raise StateVectorError(
            f"NORAD {norad}: speed {v_mag:.3f} km/s exceeds escape velocity "
            f"({_MAX_SPEED_KMS} km/s). Likely propagation error."
        )
