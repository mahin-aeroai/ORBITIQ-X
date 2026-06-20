"""
ORBITIQ-X Orbital Engine
Time Utilities — Julian Date Enforcement Layer

Every SGP4 call in this codebase MUST pass through this module.
No orbital calculation can execute with an invalid time representation.

Background
----------
SGP4 (python-sgp4 / Vallado C++ port) expects time as a Julian Date
split into two floats to preserve double-precision accuracy:

    jd   : integer part of Julian Date (e.g. 2460324.0)
    fr   : fractional part [0.0, 1.0)  (e.g. 0.5 = noon UTC)

The split matters because JD values near 2460000 and fractional
parts near 1e-6 (sub-second) cannot both fit in a single float64
without catastrophic cancellation:

    2460324.5000014 – 2460324.5 = 1.4e-6  (OK when split)
    1705320000.5000014 – 1705320000.5 = ...irrelevant (wrong epoch)

A Unix timestamp (seconds since 1970-01-01T00:00:00Z) for the same
epoch is ~1705320000. That value is ~693× larger than a JD and will
cause sgp4_array() to return error_code=1 (propagation diverged) or,
worse, silently incorrect positions outside the valid satellite orbit
regime check range.

Tested against python-sgp4 >= 2.23 with the C-accelerated extension.

Reference Epochs
----------------
JD 2435839.584  — 1957-10-04T02:00:00Z  (Sputnik-1 launch)
JD 2451545.0    — 2000-01-01T12:00:00Z  (J2000 standard epoch)
JD 2460324.5    — 2024-01-15T00:00:00Z  (arbitrary reference)
JD 2488070.0    — 2100-01-01T12:00:00Z  (upper operational limit)

Author: ORBITIQ-X Engineering
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import NamedTuple

from sgp4.api import jday as _sgp4_jday


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Julian Date of the Unix epoch (1970-01-01T00:00:00Z)
_JD_UNIX_EPOCH: float = 2440587.5

#: Julian Date of J2000 (2000-01-01T12:00:00 TT ≈ UTC for our purposes)
JD_J2000: float = 2451545.0

#: Earliest valid JD for SGP4 — Sputnik-1 launch date
JD_MIN: float = 2435839.0  # 1957-10-04

#: Latest valid JD for orbital operations in this system
JD_MAX: float = 2488070.0  # 2100-01-01

#: Upper bound that definitively identifies a Unix timestamp (not a JD)
#: The largest possible JD in our valid range is ~2488070; any value
#: larger than this is almost certainly a Unix timestamp.
_UNIX_TIMESTAMP_THRESHOLD: float = 2_500_000.0

#: Seconds per day (exact)
SECONDS_PER_DAY: float = 86400.0


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class JulianDate(NamedTuple):
    """
    A Julian Date split into integer and fractional parts.

    The split preserves double-precision accuracy for sub-second
    epochs. Both parts together represent a single instant in time:

        full_jd = jd + fr

    where ``fr`` is always in ``[0.0, 1.0)``.

    Parameters
    ----------
    jd : float
        Integer-aligned Julian Date (the whole-day part).
        Always satisfies ``JD_MIN <= jd <= JD_MAX``.
    fr : float
        Fractional day offset within ``jd``. Range ``[0.0, 1.0)``.
    """
    jd: float
    fr: float

    @property
    def full(self) -> float:
        """Full Julian Date as a single float (reduced precision)."""
        return self.jd + self.fr

    def __repr__(self) -> str:
        return f"JulianDate(jd={self.jd}, fr={self.fr:.10f}  [{self.full:.6f}])"


# ---------------------------------------------------------------------------
# Core conversion: datetime → JulianDate
# ---------------------------------------------------------------------------

def datetime_to_julian(dt: datetime) -> JulianDate:
    """
    Convert a timezone-aware UTC ``datetime`` to a split Julian Date.

    Parameters
    ----------
    dt : datetime
        Must be timezone-aware (``tzinfo`` must not be ``None``).
        Naive datetimes are rejected to prevent silent UTC assumption
        errors — always attach ``timezone.utc`` explicitly.

    Returns
    -------
    JulianDate
        Named tuple ``(jd, fr)`` ready for direct use with
        ``Satrec.sgp4(jd, fr)`` and ``Satrec.sgp4_array(jds, frs)``.

    Raises
    ------
    TypeError
        If ``dt`` is not a ``datetime`` instance.
    ValueError
        If ``dt`` is timezone-naive.
        If the resulting Julian Date is outside ``[JD_MIN, JD_MAX]``.

    Examples
    --------
    >>> from datetime import datetime, timezone
    >>> dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    >>> jd_pair = datetime_to_julian(dt)
    >>> jd_pair.jd, jd_pair.fr
    (2460324.5, 0.5)
    """
    if not isinstance(dt, datetime):
        raise TypeError(
            f"datetime_to_julian() requires a datetime instance, "
            f"got {type(dt).__name__!r}. "
            f"Did you accidentally pass a Unix timestamp (float)?"
        )
    if dt.tzinfo is None:
        raise ValueError(
            "datetime_to_julian() requires a timezone-aware datetime. "
            "Attach timezone.utc explicitly: "
            "datetime(..., tzinfo=timezone.utc). "
            "Naive datetimes are rejected to prevent silent UTC errors."
        )

    # Convert to UTC if not already
    dt_utc = dt.astimezone(timezone.utc)

    # Include sub-second precision in the seconds argument.
    # sgp4.api.jday() accepts fractional seconds.
    seconds_with_fraction = dt_utc.second + dt_utc.microsecond / 1_000_000.0

    jd, fr = _sgp4_jday(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour,
        dt_utc.minute,
        seconds_with_fraction,
    )

    result = JulianDate(jd=jd, fr=fr)
    validate_julian_date(result)
    return result


# ---------------------------------------------------------------------------
# Core conversion: JulianDate → datetime
# ---------------------------------------------------------------------------

def julian_to_datetime(jd_pair: JulianDate) -> datetime:
    """
    Convert a split Julian Date back to a UTC ``datetime``.

    Parameters
    ----------
    jd_pair : JulianDate
        Named tuple ``(jd, fr)`` as returned by ``datetime_to_julian()``.
        Both components are validated before conversion.

    Returns
    -------
    datetime
        UTC datetime with microsecond precision.
        Always timezone-aware (``tzinfo=timezone.utc``).

    Raises
    ------
    ValueError
        If ``jd_pair`` fails ``validate_julian_date()``.

    Examples
    --------
    >>> jd = JulianDate(jd=2460324.5, fr=0.5)
    >>> julian_to_datetime(jd)
    datetime.datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    """
    validate_julian_date(jd_pair)

    # Convert JD to days since Unix epoch
    jd_full = jd_pair.jd + jd_pair.fr
    days_since_unix = jd_full - _JD_UNIX_EPOCH
    total_seconds = days_since_unix * SECONDS_PER_DAY

    # Split into whole seconds and microseconds
    whole_seconds = math.floor(total_seconds)
    microseconds  = round((total_seconds - whole_seconds) * 1_000_000)

    # Handle microsecond overflow
    if microseconds >= 1_000_000:
        whole_seconds += 1
        microseconds  -= 1_000_000

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return epoch + timedelta(seconds=whole_seconds, microseconds=microseconds)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_julian_date(jd_pair: JulianDate) -> None:
    """
    Validate a ``JulianDate`` pair before any SGP4 call.

    Checks performed (in order):

    1. Type check — both components must be ``float`` or ``int``.
    2. Unix timestamp guard — reject values larger than any plausible JD.
    3. Lower bound — reject dates before Sputnik-1 (1957-10-04).
    4. Upper bound — reject dates beyond year 2100.
    5. Fractional day range — ``fr`` must be in ``[0.0, 1.0)``.
    6. NaN / Inf guard — reject non-finite values.

    Parameters
    ----------
    jd_pair : JulianDate
        The ``(jd, fr)`` pair to validate.

    Raises
    ------
    JulianDateError
        On any validation failure. The message identifies the exact
        violation so callers can surface it in structured logs.

    Examples
    --------
    >>> validate_julian_date(JulianDate(2460324.5, 0.5))  # OK — ISS epoch
    >>> validate_julian_date(JulianDate(1705320000.0, 0.0))  # RAISES — Unix ts
    """
    jd = jd_pair.jd
    fr = jd_pair.fr

    # 1. Type check
    if not isinstance(jd, (int, float)):
        raise JulianDateError(
            f"jd must be a numeric type, got {type(jd).__name__!r}"
        )
    if not isinstance(fr, (int, float)):
        raise JulianDateError(
            f"fr must be a numeric type, got {type(fr).__name__!r}"
        )

    # 2. NaN / Inf guard
    if not math.isfinite(jd):
        raise JulianDateError(
            f"jd is not finite: {jd!r}. Check for NaN/Inf in propagation inputs."
        )
    if not math.isfinite(fr):
        raise JulianDateError(
            f"fr is not finite: {fr!r}. Check for NaN/Inf in propagation inputs."
        )

    # 3. Unix timestamp guard
    # A Unix timestamp for dates in the satellite era (1957–2100) ranges from
    # -387849600 to 4102444800. A valid JD for the same period is 2435839–2488070.
    # Any value >= _UNIX_TIMESTAMP_THRESHOLD is almost certainly a Unix timestamp.
    if jd >= _UNIX_TIMESTAMP_THRESHOLD:
        raise JulianDateError(
            f"jd={jd:.1f} looks like a Unix timestamp, not a Julian Date. "
            f"Unix timestamps for the satellite era are ~946728000–4102444800. "
            f"Valid JDs are in the range {JD_MIN:.0f}–{JD_MAX:.0f}. "
            f"Use datetime_to_julian(dt) to convert a datetime to JD."
        )

    # 4. Lower bound — before Sputnik is meaningless for SGP4
    if jd < JD_MIN:
        raise JulianDateError(
            f"jd={jd:.3f} is before the Sputnik-1 era (JD {JD_MIN:.1f} = 1957-10-04). "
            f"SGP4 TLEs cannot be propagated before the space age."
        )

    # 5. Upper bound
    if jd > JD_MAX:
        raise JulianDateError(
            f"jd={jd:.3f} is beyond the year-2100 operational limit (JD {JD_MAX:.1f}). "
            f"SGP4 accuracy degrades significantly beyond ~7 days from TLE epoch; "
            f"propagation beyond 2100 is not physically meaningful."
        )

    # 6. Fractional day range
    if not (0.0 <= fr < 1.0):
        raise JulianDateError(
            f"fr={fr!r} is outside the valid range [0.0, 1.0). "
            f"The fractional day must satisfy 0.0 ≤ fr < 1.0. "
            f"fr=0.0 → midnight UTC; fr=0.5 → noon UTC."
        )


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------

def datetimes_to_julian_arrays(
    epochs: list[datetime],
) -> tuple[list[float], list[float]]:
    """
    Convert a list of datetimes to parallel ``jd`` and ``fr`` arrays.

    This is the correct input for ``Satrec.sgp4_array()``.

    Parameters
    ----------
    epochs : list[datetime]
        List of timezone-aware UTC datetimes. Validated individually.

    Returns
    -------
    tuple[list[float], list[float]]
        ``(jds, frs)`` — parallel lists of the same length as ``epochs``.
        Pass directly to ``np.array(jds)`` and ``np.array(frs)``.

    Raises
    ------
    ValueError
        If ``epochs`` is empty.
    JulianDateError
        If any epoch fails ``validate_julian_date()``.

    Examples
    --------
    >>> from datetime import datetime, timezone, timedelta
    >>> start = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    >>> epochs = [start + timedelta(minutes=i*10) for i in range(6)]
    >>> jds, frs = datetimes_to_julian_arrays(epochs)
    """
    if not epochs:
        raise ValueError("epochs list must not be empty")

    jds: list[float] = []
    frs: list[float] = []

    for i, dt in enumerate(epochs):
        try:
            pair = datetime_to_julian(dt)
        except (TypeError, ValueError, JulianDateError) as exc:
            raise JulianDateError(
                f"Invalid epoch at index {i} ({dt!r}): {exc}"
            ) from exc
        jds.append(pair.jd)
        frs.append(pair.fr)

    return jds, frs


def unix_to_julian(unix_ts: float) -> JulianDate:
    """
    Convert a Unix timestamp (seconds since 1970-01-01T00:00:00Z) to JD.

    This function exists for migration compatibility only — to bridge
    legacy code that already has a Unix timestamp in hand.

    Prefer ``datetime_to_julian(datetime.fromtimestamp(ts, tz=timezone.utc))``
    at the boundary where timestamps enter the system.

    Parameters
    ----------
    unix_ts : float
        Seconds since Unix epoch (1970-01-01T00:00:00 UTC).
        May be negative (for dates before 1970).

    Returns
    -------
    JulianDate
        Validated ``(jd, fr)`` pair.

    Raises
    ------
    TypeError
        If ``unix_ts`` is not numeric.
    JulianDateError
        If the resulting JD is outside the valid range.

    Examples
    --------
    >>> unix_to_julian(1705320000.0)
    JulianDate(jd=2460324.5, fr=0.5)
    """
    if not isinstance(unix_ts, (int, float)):
        raise TypeError(
            f"unix_ts must be a numeric type, got {type(unix_ts).__name__!r}"
        )
    if not math.isfinite(unix_ts):
        raise JulianDateError(f"unix_ts is not finite: {unix_ts!r}")

    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return datetime_to_julian(dt)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class JulianDateError(ValueError):
    """
    Raised when an invalid time representation is detected.

    This is a subclass of ``ValueError`` so existing ``except ValueError``
    handlers catch it, while allowing specific ``except JulianDateError``
    handlers to distinguish time-representation errors from other
    value errors.
    """
    pass
