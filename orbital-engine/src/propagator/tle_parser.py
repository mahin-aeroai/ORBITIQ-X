"""
TLE Parser and Validator
Parses and validates Two-Line Element sets per NORAD/NASA format spec.
Reference: https://celestrak.org/columns/v04n03/

Format:
  Line 0: Name (optional, 24 chars)
  Line 1: Checksum-validated, epoch, Bstar, mean motion derivatives
  Line 2: Checksum-validated, inclination, RAAN, e, argp, M, n, rev#
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator


# ── Data Models ───────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class TwoLineElement:
    """Immutable, validated Two-Line Element set."""
    name: str
    norad_id: int
    cospar_id: str
    epoch: datetime          # UTC
    epoch_year: int
    epoch_day: float
    # Line 1 fields
    mean_motion_dot: float   # rev/day²  (first derivative / 2)
    mean_motion_ddot: float  # rev/day³  (second derivative / 6)
    bstar: float             # drag term (1/earth_radii)
    element_set_number: int
    # Line 2 fields
    inclination_deg: float
    raan_deg: float
    eccentricity: float
    arg_perigee_deg: float
    mean_anomaly_deg: float
    mean_motion_rpm: float   # rev/day
    rev_at_epoch: int
    # Raw strings (needed by python-sgp4)
    line1: str
    line2: str

    @property
    def semi_major_axis_km(self) -> float:
        """Compute SMA from mean motion (km). Earth GM = 398600.4418 km³/s²."""
        import math
        GM = 398600.4418
        n_rads_per_sec = self.mean_motion_rpm * 2 * math.pi / 86400
        return (GM / n_rads_per_sec ** 2) ** (1/3)

    @property
    def period_minutes(self) -> float:
        return 1440.0 / self.mean_motion_rpm

    @property
    def apogee_km(self) -> float:
        a = self.semi_major_axis_km
        return a * (1 + self.eccentricity) - 6371.0

    @property
    def perigee_km(self) -> float:
        a = self.semi_major_axis_km
        return a * (1 - self.eccentricity) - 6371.0


@dataclass(frozen=True, slots=True)
class TLEParseError:
    line: int
    reason: str
    raw: str


# ── Checksum ─────────────────────────────────────────────────

def _compute_checksum(line: str) -> int:
    total = 0
    for ch in line[:-1]:
        if ch.isdigit():
            total += int(ch)
        elif ch == '-':
            total += 1
    return total % 10


def _validate_checksum(line: str, line_num: int) -> TLEParseError | None:
    if len(line) < 69:
        return TLEParseError(line_num, f"Line too short: {len(line)} chars", line)
    expected = _compute_checksum(line)
    actual = int(line[68])
    if expected != actual:
        return TLEParseError(
            line_num,
            f"Checksum mismatch: expected {expected}, got {actual}",
            line,
        )
    return None


# ── Decimal parsing for TLE packed floats ───────────────────

def _parse_decimal(s: str) -> float:
    """
    Parse TLE 'packed decimal' format.
    e.g. ' 00000-0' → 0.0
         '-11606-4' → -0.11606e-4 = -1.1606e-5
         ' 68719-1' → 0.68719e-1  =  0.068719
    """
    s = s.strip()
    if not s or s == '00000-0' or s == '+00000-0':
        return 0.0
    sign = -1.0 if s.startswith('-') else 1.0
    s = s.lstrip('+-')
    if '-' in s:
        mantissa, exp_str = s.rsplit('-', 1)
        exp = -int(exp_str)
    elif '+' in s:
        mantissa, exp_str = s.rsplit('+', 1)
        exp = int(exp_str)
    else:
        return float(s)
    return sign * float('0.' + mantissa) * 10 ** exp


# ── Epoch parsing ─────────────────────────────────────────────

def _parse_epoch(year2: int, day: float) -> datetime:
    """
    Convert TLE epoch (2-digit year + day-of-year fraction) to UTC datetime.
    Year 57-99 = 1957-1999, 00-56 = 2000-2056 (per NORAD convention).
    """
    from datetime import timedelta
    year = (1900 + year2) if year2 >= 57 else (2000 + year2)
    jan1 = datetime(year, 1, 1, tzinfo=timezone.utc)
    return jan1 + timedelta(days=day - 1)


# ── Core Parser ───────────────────────────────────────────────

class TLEParser:
    """
    Parse raw TLE text into TwoLineElement objects.
    Supports 2-line and 3-line (with name) formats.
    Validates checksums, field ranges, and eccentricity.
    """

    LINE1_RE = re.compile(
        r'^1 '
        r'(\d{5})[A-Z] '          # NORAD ID
        r'(\S{1,8})\s+'           # COSPAR ID
        r'(\d{2})(\d{3}\.\d+) '  # epoch year + day
        r'([+\- ]\d{8}) '        # dn/dt/2
        r'([\+ \-]\d{5}[-+]\d) ' # d²n/dt²/6
        r'([\+ \-]\d{5}[-+]\d) ' # Bstar
        r'\d '                    # ephemeris type
        r'(\d{4})\d'             # element set #
        r'\d$',                   # checksum
        re.ASCII,
    )

    LINE2_RE = re.compile(
        r'^2 '
        r'(\d{5}) '              # NORAD
        r'(\d{3}\.\d+) '        # inclination
        r'(\d{3}\.\d+) '        # RAAN
        r'(\d{7}) '             # eccentricity (decimal assumed)
        r'(\d{3}\.\d+) '        # arg perigee
        r'(\d{3}\.\d+) '        # mean anomaly
        r'(\d{2}\.\d+)'         # mean motion
        r'(\d{5})\d$',          # rev at epoch + checksum
        re.ASCII,
    )

    def parse_file(self, text: str) -> tuple[list[TwoLineElement], list[TLEParseError]]:
        """Parse multi-TLE text block. Returns (successful, errors)."""
        tle_list: list[TwoLineElement] = []
        errors: list[TLEParseError] = []
        for tle, err in self._iter_raw_blocks(text):
            if err:
                errors.extend(err)
            elif tle:
                tle_list.append(tle)
        return tle_list, errors

    def parse_single(self, name: str, line1: str, line2: str) -> TwoLineElement:
        """Parse a single TLE, raise ValueError on failure."""
        result, errs = self._parse_block(name.strip(), line1.strip(), line2.strip())
        if errs:
            raise ValueError(f"TLE parse errors: {[e.reason for e in errs]}")
        return result

    def _iter_raw_blocks(
        self, text: str
    ) -> Iterator[tuple[TwoLineElement | None, list[TLEParseError] | None]]:
        lines = [l.rstrip() for l in text.splitlines() if l.strip()]
        i = 0
        while i < len(lines):
            # Detect 3-line block (name + L1 + L2)
            if (
                i + 2 < len(lines)
                and not lines[i].startswith('1 ')
                and not lines[i].startswith('2 ')
                and lines[i+1].startswith('1 ')
                and lines[i+2].startswith('2 ')
            ):
                name = lines[i]
                l1, l2 = lines[i+1], lines[i+2]
                i += 3
            elif (
                i + 1 < len(lines)
                and lines[i].startswith('1 ')
                and lines[i+1].startswith('2 ')
            ):
                name = f"OBJ-{lines[i][2:7].strip()}"
                l1, l2 = lines[i], lines[i+1]
                i += 2
            else:
                i += 1
                continue
            result, errs = self._parse_block(name, l1, l2)
            yield result, errs

    def _parse_block(
        self, name: str, l1: str, l2: str
    ) -> tuple[TwoLineElement | None, list[TLEParseError] | None]:
        errors = []

        # Checksum
        err1 = _validate_checksum(l1, 1)
        err2 = _validate_checksum(l2, 2)
        if err1: errors.append(err1)
        if err2: errors.append(err2)
        if errors:
            return None, errors

        # Extract line 1 fields
        norad_id = int(l1[2:7])
        cospar_id = l1[9:17].strip()
        epoch_year = int(l1[18:20])
        epoch_day = float(l1[20:32])
        mean_motion_dot = float(l1[33:43].replace(' ', ''))
        mean_motion_ddot = _parse_decimal(l1[44:52])
        bstar = _parse_decimal(l1[53:61])
        element_set_number = int(l1[64:68].strip())
        epoch = _parse_epoch(epoch_year, epoch_day)

        # Extract line 2 fields
        norad_l2 = int(l2[2:7])
        if norad_id != norad_l2:
            errors.append(TLEParseError(2, f"NORAD ID mismatch: {norad_id} vs {norad_l2}", l2))
            return None, errors

        inclination = float(l2[8:16])
        raan = float(l2[17:25])
        eccentricity = float('0.' + l2[26:33])
        arg_perigee = float(l2[34:42])
        mean_anomaly = float(l2[43:51])
        mean_motion = float(l2[52:63])
        rev_at_epoch = int(l2[63:68])

        # Range validation
        if not (0.0 <= inclination <= 180.0):
            errors.append(TLEParseError(2, f"Inclination out of range: {inclination}", l2))
        if not (0.0 <= eccentricity < 1.0):
            errors.append(TLEParseError(2, f"Eccentricity out of range: {eccentricity}", l2))
        if not (0.0 <= mean_motion <= 20.0):
            errors.append(TLEParseError(2, f"Mean motion out of range: {mean_motion}", l2))
        if errors:
            return None, errors

        return TwoLineElement(
            name=name[:24].strip(),
            norad_id=norad_id,
            cospar_id=cospar_id,
            epoch=epoch,
            epoch_year=epoch_year,
            epoch_day=epoch_day,
            mean_motion_dot=mean_motion_dot,
            mean_motion_ddot=mean_motion_ddot,
            bstar=bstar,
            element_set_number=element_set_number,
            inclination_deg=inclination,
            raan_deg=raan,
            eccentricity=eccentricity,
            arg_perigee_deg=arg_perigee,
            mean_anomaly_deg=mean_anomaly,
            mean_motion_rpm=mean_motion,
            rev_at_epoch=rev_at_epoch,
            line1=l1,
            line2=l2,
        ), None


# ── Convenience function ──────────────────────────────────────

_PARSER = TLEParser()


def parse_tle_file(text: str) -> list[TwoLineElement]:
    tles, errors = _PARSER.parse_file(text)
    if errors:
        import logging
        logging.getLogger(__name__).warning(
            f"TLE parse: {len(tles)} ok, {len(errors)} errors"
        )
    return tles


def parse_tle(name: str, line1: str, line2: str) -> TwoLineElement:
    return _PARSER.parse_single(name, line1, line2)
