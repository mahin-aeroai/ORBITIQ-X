"""
ORBITIQ-X Orbital Engine
TLE Parser and Validator

Validates TLE format per USSPACECOM specification:
  https://celestrak.org/columns/v04n03/

Two-Line Element Set format:
  Line 0: Object name (optional, 24 chars)
  Line 1: Catalog number, epoch, mean motion derivatives, drag, etc.
  Line 2: Inclination, RAAN, eccentricity, arg. perigee, mean anomaly, mean motion
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NamedTuple


# ── TLE field positions (0-indexed, inclusive) ────────────────
# Line 1:
# Col  1     : Line number ('1')
# Col  3-7   : Satellite catalog number (5 digits)
# Col  8     : Classification (U/C/S)
# Col  10-17 : International Designator
# Col  19-32 : Epoch (YYddd.dddddddd)
# Col  34-43 : First derivative of mean motion (rev/day²)
# Col  45-52 : Second derivative of mean motion (rev/day³)
# Col  54-61 : BSTAR drag term (1/R_E)
# Col  63    : Element set type
# Col  65-68 : Element set number
# Col  69    : Checksum

# Line 2:
# Col  1     : Line number ('2')
# Col  3-7   : Satellite catalog number
# Col  9-16  : Inclination (deg)
# Col  18-25 : RAAN (deg)
# Col  27-33 : Eccentricity (assumed decimal point before digits)
# Col  35-42 : Argument of perigee (deg)
# Col  44-51 : Mean anomaly (deg)
# Col  53-63 : Mean motion (rev/day)
# Col  64-68 : Revolution number at epoch
# Col  69    : Checksum


class TLEParseError(ValueError):
    """Raised when TLE data is malformed or fails checksum."""
    pass


@dataclass(frozen=True)
class ParsedTLE:
    # Line 0 (name)
    name: str

    # Line 1 fields
    norad_id: int
    classification: str
    intl_designator: str
    epoch_year: int           # 2-digit year (0-99)
    epoch_day_of_year: float  # day + fraction
    epoch: datetime           # resolved UTC datetime
    n_dot: float              # first derivative of mean motion (rev/day²)
    n_ddot: float             # second derivative (rev/day³)
    bstar: float              # drag term (1/R_E)
    element_set_num: int
    checksum_1: int

    # Line 2 fields
    inclination: float        # degrees
    raan: float               # degrees
    eccentricity: float       # dimensionless (0.0 to 1.0)
    arg_perigee: float        # degrees
    mean_anomaly: float       # degrees
    mean_motion: float        # revolutions per day
    rev_number: int
    checksum_2: int

    # Derived
    semi_major_axis_km: float
    perigee_km: float
    apogee_km: float
    period_min: float

    # Raw lines (for SGP4 consumption)
    line1: str
    line2: str


def _tle_checksum(line: str) -> int:
    """
    Compute TLE line checksum.
    Sum of all numeric digits + 1 for each '-', modulo 10.
    """
    total = 0
    for c in line[:68]:
        if c.isdigit():
            total += int(c)
        elif c == '-':
            total += 1
    return total % 10


def _parse_decimal(field: str) -> float:
    """
    Parse SGP4 exponent notation: ' 12345-3' → 0.00012345
    Format: [+/-]ddddd[+-]e → [+/-]0.ddddd × 10^e
    """
    field = field.strip()
    if not field or field == '00000-0' or field == ' 00000+0':
        return 0.0

    sign = -1.0 if field[0] == '-' else 1.0
    field = field.lstrip('+-')

    # Find exponent marker
    match = re.match(r'^(\d+)([+-]\d+)$', field)
    if not match:
        return 0.0

    mantissa = float('0.' + match.group(1))
    exponent = int(match.group(2))
    return sign * mantissa * (10.0 ** exponent)


def _epoch_to_datetime(year2: int, day_of_year: float) -> datetime:
    """Convert TLE epoch (2-digit year + day) to UTC datetime."""
    year = 2000 + year2 if year2 < 57 else 1900 + year2  # USSPACECOM convention
    day_int = int(day_of_year)
    frac    = day_of_year - day_int
    seconds = frac * 86400.0

    try:
        base = datetime(year, 1, 1, tzinfo=timezone.utc)
        from datetime import timedelta
        epoch = base + timedelta(days=day_int - 1, seconds=seconds)
    except ValueError:
        epoch = datetime(year, 1, 1, tzinfo=timezone.utc)

    return epoch


def parse_tle(name: str, line1: str, line2: str) -> ParsedTLE:
    """
    Parse and validate a Two-Line Element Set.

    Parameters
    ----------
    name  : Object name (line 0, may be empty)
    line1 : TLE line 1 (69 chars)
    line2 : TLE line 2 (69 chars)

    Returns
    -------
    ParsedTLE with all fields extracted and derived orbital elements.

    Raises
    ------
    TLEParseError on any format or checksum violation.
    """
    line1 = line1.strip()
    line2 = line2.strip()

    # Length check
    if len(line1) < 69:
        raise TLEParseError(f"Line 1 too short: {len(line1)} chars (expected 69)")
    if len(line2) < 69:
        raise TLEParseError(f"Line 2 too short: {len(line2)} chars (expected 69)")

    # Line number check
    if line1[0] != '1':
        raise TLEParseError(f"Line 1 must start with '1', got '{line1[0]}'")
    if line2[0] != '2':
        raise TLEParseError(f"Line 2 must start with '2', got '{line2[0]}'")

    # Checksum validation
    computed_1 = _tle_checksum(line1)
    stored_1   = int(line1[68])
    if computed_1 != stored_1:
        raise TLEParseError(f"Line 1 checksum mismatch: computed {computed_1}, stored {stored_1}")

    computed_2 = _tle_checksum(line2)
    stored_2   = int(line2[68])
    if computed_2 != stored_2:
        raise TLEParseError(f"Line 2 checksum mismatch: computed {computed_2}, stored {stored_2}")

    # Parse line 1
    try:
        norad_id        = int(line1[2:7].strip())
        classification  = line1[7]
        intl_designator = line1[9:17].strip()
        epoch_year      = int(line1[18:20])
        epoch_day       = float(line1[20:32])
        n_dot           = float(line1[33:43])
        n_ddot          = _parse_decimal(line1[44:52])
        bstar           = _parse_decimal(line1[53:61])
        elem_set_num    = int(line1[64:68].strip() or '0')
        checksum_1      = stored_1
    except (ValueError, IndexError) as e:
        raise TLEParseError(f"Line 1 parse error: {e}") from e

    # Parse line 2
    try:
        norad_id_2  = int(line2[2:7].strip())
        inclination = float(line2[8:16])
        raan        = float(line2[17:25])
        ecc_str     = line2[26:33].strip()
        eccentricity = float('0.' + ecc_str)
        arg_perigee = float(line2[34:42])
        mean_anomaly = float(line2[43:51])
        mean_motion  = float(line2[52:63])
        rev_number   = int(line2[63:68].strip() or '0')
        checksum_2   = stored_2
    except (ValueError, IndexError) as e:
        raise TLEParseError(f"Line 2 parse error: {e}") from e

    # Cross-validate NORAD IDs
    if norad_id != norad_id_2:
        raise TLEParseError(
            f"NORAD ID mismatch between lines: L1={norad_id}, L2={norad_id_2}"
        )

    # Validate physical ranges
    if not (0 <= inclination <= 180):
        raise TLEParseError(f"Inclination out of range: {inclination}")
    if not (0 <= eccentricity < 1):
        raise TLEParseError(f"Eccentricity out of range: {eccentricity}")
    if mean_motion <= 0:
        raise TLEParseError(f"Mean motion must be positive: {mean_motion}")

    # Derived elements
    MU = 398600.4418   # km³/s²
    R_E = 6378.137     # km

    n_rad_s = mean_motion * 2 * math.pi / 86400.0
    a_km    = (MU / n_rad_s**2) ** (1/3)
    perigee = a_km * (1 - eccentricity) - R_E
    apogee  = a_km * (1 + eccentricity) - R_E
    period  = 1440.0 / mean_motion

    epoch = _epoch_to_datetime(epoch_year, epoch_day)

    return ParsedTLE(
        name=name.strip(),
        norad_id=norad_id,
        classification=classification,
        intl_designator=intl_designator,
        epoch_year=epoch_year,
        epoch_day_of_year=epoch_day,
        epoch=epoch,
        n_dot=n_dot,
        n_ddot=n_ddot,
        bstar=bstar,
        element_set_num=elem_set_num,
        checksum_1=checksum_1,
        inclination=inclination,
        raan=raan,
        eccentricity=eccentricity,
        arg_perigee=arg_perigee,
        mean_anomaly=mean_anomaly,
        mean_motion=mean_motion,
        rev_number=rev_number,
        checksum_2=checksum_2,
        semi_major_axis_km=a_km,
        perigee_km=perigee,
        apogee_km=apogee,
        period_min=period,
        line1=line1,
        line2=line2,
    )


def parse_tle_file(content: str) -> list[ParsedTLE]:
    """
    Parse a multi-TLE text file (3-line or 2-line format).

    Handles:
    - 3-line format: name, L1, L2 (CelesTrak default)
    - 2-line format: L1, L2 only (name set to NORAD ID)
    - Mixed formats in same file
    - Windows/Unix line endings
    - Comment lines (starting with '#')
    """
    lines = [l.rstrip() for l in content.replace('\r\n', '\n').split('\n')]
    lines = [l for l in lines if l and not l.startswith('#')]

    results = []
    i = 0
    errors = []

    while i < len(lines):
        # 3-line format: name doesn't start with '1' or '2'
        if i + 2 < len(lines) and not lines[i].startswith(('1 ', '2 ')):
            name = lines[i]
            l1, l2 = lines[i+1], lines[i+2]
            step = 3
        elif i + 1 < len(lines) and lines[i].startswith('1 '):
            name = f"NORAD-{lines[i][2:7].strip()}"
            l1, l2 = lines[i], lines[i+1]
            step = 2
        else:
            i += 1
            continue

        try:
            parsed = parse_tle(name, l1, l2)
            results.append(parsed)
        except TLEParseError as e:
            errors.append(str(e))

        i += step

    if errors:
        import logging
        logging.getLogger(__name__).warning(
            f"TLE parse: {len(results)} OK, {len(errors)} errors"
        )

    return results


def validate_tle_age(tle: ParsedTLE, max_age_days: float = 7.0) -> bool:
    """Return True if TLE is fresh enough for reliable propagation."""
    now = datetime.now(timezone.utc)
    age = (now - tle.epoch).total_seconds() / 86400.0
    return age <= max_age_days
