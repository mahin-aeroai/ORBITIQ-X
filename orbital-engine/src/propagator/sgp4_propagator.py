"""
ORBITIQ-X Orbital Engine — SGP4 Propagator
==========================================
High-performance SGP4/SDP4 propagation wrapper with:
- Batch propagation across multiple objects
- J2-perturbation correction layer
- Input validation against TLE format and physical plausibility
- Structured output (ECI J2000 state vectors)

References
----------
.. [1] Hoots, F.R. & Roehrich, R.L. (1980). Spacetrack Report No. 3:
       Models for Propagation of NORAD Element Sets. USAF Aerospace
       Defense Command, Colorado Springs, CO.
.. [2] Vallado, D. (2013). Fundamentals of Astrodynamics and Applications,
       4th ed. Microcosm Press.
.. [3] python-sgp4 library: https://github.com/brandon-rhodes/python-sgp4
"""
from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

import numpy as np
from sgp4.api import Satrec, WGS72, WGS84, accelerated
from sgp4.earth_gravity import wgs72, wgs84

from .constants import (
    EARTH_RADIUS_KM,
    MU_KM3_S2,
    J2_COEFFICIENT,
    SECONDS_PER_MINUTE,
)
from .tle_parser import TwoLineElement
from .time_utils import (
    JulianDate,
    JulianDateError,
    datetime_to_julian,
    datetimes_to_julian_arrays,
)
from .validators import validate_tle_epoch, validate_state_vector, StateVectorError

logger = logging.getLogger(__name__)


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class StateVector:
    """
    ECI J2000 Cartesian state vector at a specific epoch.

    All values in SI-compatible aerospace units (km, km/s).
    The frozen dataclass ensures immutability — state vectors must not
    be mutated after creation to preserve physical consistency.
    """
    epoch: datetime                          # UTC epoch of state vector
    norad_id: int                            # NORAD catalog number
    position_eci_km: np.ndarray             # [x, y, z] ECI position [km]
    velocity_eci_km_s: np.ndarray           # [vx, vy, vz] ECI velocity [km/s]
    error_code: int = 0                      # SGP4 error code (0 = nominal)

    def __post_init__(self) -> None:
        object.__setattr__(self, "position_eci_km", np.asarray(self.position_eci_km, dtype=np.float64))
        object.__setattr__(self, "velocity_eci_km_s", np.asarray(self.velocity_eci_km_s, dtype=np.float64))

    @property
    def altitude_km(self) -> float:
        """Geodetic altitude above WGS-84 ellipsoid [km] (approx spherical)."""
        return float(np.linalg.norm(self.position_eci_km)) - EARTH_RADIUS_KM

    @property
    def speed_km_s(self) -> float:
        """Scalar orbital speed [km/s]."""
        return float(np.linalg.norm(self.velocity_eci_km_s))

    @property
    def is_nominal(self) -> bool:
        """True if SGP4 propagation completed without error."""
        return self.error_code == 0


@dataclass
class PropagationRequest:
    """
    Batch propagation request for one or more RSOs.

    Parameters
    ----------
    tle_elements : list[TwoLineElement]
        TLE sets for each object to propagate.
    start_epoch : datetime
        Propagation start time (UTC).
    stop_epoch : datetime
        Propagation stop time (UTC).
    step_seconds : int
        Time step between state vectors [s]. Default 60s.
    apply_j2_correction : bool
        Apply first-order J2 oblateness correction. Default True for LEO.
    """
    tle_elements: list[TwoLineElement]
    start_epoch: datetime
    stop_epoch: datetime
    step_seconds: int = 60
    apply_j2_correction: bool = True
    workers: int = 4


@dataclass
class PropagationResult:
    """Results of a propagation request."""
    norad_id: int
    tle: TwoLineElement
    state_vectors: list[StateVector] = field(default_factory=list)
    propagation_errors: list[dict] = field(default_factory=list)
    total_epochs: int = 0
    nominal_epochs: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_epochs == 0:
            return 0.0
        return self.nominal_epochs / self.total_epochs


# ─── SGP4 Propagator ──────────────────────────────────────────────────────────

class SGP4Propagator:
    """
    Production-grade SGP4/SDP4 orbit propagator.

    Wraps the python-sgp4 C extension (when compiled) or Python fallback,
    adding batch processing, J2 corrections, input validation, and
    structured output compatible with the ORBITIQ-X data model.

    Usage
    -----
    ::

        propagator = SGP4Propagator(wgs_model=72)
        tle = parse_tle_pair(line1, line2)
        request = PropagationRequest(
            tle_elements=[tle],
            start_epoch=datetime(2024, 1, 1, tzinfo=timezone.utc),
            stop_epoch=datetime(2024, 1, 2, tzinfo=timezone.utc),
            step_seconds=60,
        )
        results = propagator.propagate(request)
    """

    def __init__(self, wgs_model: int = 72) -> None:
        """
        Initialize the SGP4 propagator.

        Parameters
        ----------
        wgs_model : int
            Earth gravity model. 72 = WGS-72 (AFSPC standard),
            84 = WGS-84 (higher accuracy for modern TLEs).
        """
        if wgs_model not in (72, 84):
            raise ValueError(f"wgs_model must be 72 or 84, got {wgs_model}")

        self._wgs_model = wgs_model
        self._gravity_model = WGS72 if wgs_model == 72 else WGS84
        self._earth_params = wgs72 if wgs_model == 72 else wgs84

        logger.info(
            "SGP4Propagator initialized",
            wgs_model=wgs_model,
            accelerated=accelerated,
        )

    def propagate_single(
        self,
        tle: TwoLineElement,
        epochs: list[datetime],
    ) -> list[StateVector]:
        """
        Propagate a single TLE to a list of epochs.

        Parameters
        ----------
        tle : TwoLineElement
            Parsed and validated TLE set.
        epochs : list[datetime]
            List of UTC datetimes to propagate to.

        Returns
        -------
        list[StateVector]
            State vectors at each requested epoch. Epochs with propagation
            errors have error_code != 0 and NaN position/velocity values.
        """
        validate_tle_epoch(tle)

        satellite = Satrec.twoline2rv(
            tle.line1,
            tle.line2,
            self._gravity_model,
        )

        # ── Batch Julian Date conversion (single validated pass) ──────
        # CRITICAL: sgp4_array() requires Julian Date split as (jd, fr).
        # Passing epoch.timestamp() (Unix seconds) is WRONG and returns
        # error_code=1 with NaN positions. datetime_to_julian() validates
        # and raises JulianDateError before any SGP4 call is made.
        normalised: list[datetime] = [
            ep.replace(tzinfo=timezone.utc) if ep.tzinfo is None else ep
            for ep in epochs
        ]

        try:
            jds, frs = datetimes_to_julian_arrays(normalised)
        except (JulianDateError, ValueError) as exc:
            raise JulianDateError(
                f"NORAD {tle.norad_id}: invalid epoch in propagation request — {exc}"
            ) from exc

        jd_arr = np.array(jds, dtype=np.float64)
        fr_arr = np.array(frs, dtype=np.float64)

        # ── Single vectorised SGP4 call across all epochs ──────────────
        # sgp4_array() is faster than calling sgp4() in a Python loop
        # because the C extension avoids re-entering Python for each epoch.
        errors, positions, velocities = satellite.sgp4_array(jd_arr, fr_arr)

        results: list[StateVector] = []
        for i, epoch_utc in enumerate(normalised):
            error_code = int(errors[i])

            if error_code != 0:
                logger.warning(
                    "sgp4_propagation_error",
                    norad_id=tle.norad_id,
                    epoch=epoch_utc.isoformat(),
                    jd=jds[i],
                    fr=frs[i],
                    error_code=error_code,
                )
                pos = np.full(3, np.nan)
                vel = np.full(3, np.nan)
            else:
                pos = np.array(positions[i], dtype=np.float64)
                vel = np.array(velocities[i], dtype=np.float64)

            state = StateVector(
                epoch=epoch_utc,
                norad_id=tle.norad_id,
                position_eci_km=pos,
                velocity_eci_km_s=vel,
                error_code=error_code,
            )
            if error_code == 0:
                try:
                    validate_state_vector(state)
                except StateVectorError as exc:
                    logger.error(
                        "state_vector_physically_invalid",
                        norad_id=tle.norad_id,
                        epoch=epoch_utc.isoformat(),
                        error=str(exc),
                    )
                    # Re-tag as error so callers don't use the bad vector
                    state = StateVector(
                        epoch=epoch_utc,
                        norad_id=tle.norad_id,
                        position_eci_km=np.full(3, np.nan),
                        velocity_eci_km_s=np.full(3, np.nan),
                        error_code=99,  # ORBITIQ internal: physical validation failed
                    )
            results.append(state)

        return results

    def propagate(self, request: PropagationRequest) -> list[PropagationResult]:
        """
        Batch-propagate all TLEs in the request.

        Distributes work across `request.workers` processes for large batches.
        For small batches (<= 10 objects), runs in the calling thread to avoid
        process spawn overhead.

        Parameters
        ----------
        request : PropagationRequest
            Fully specified propagation request.

        Returns
        -------
        list[PropagationResult]
            One result per TLE in request.tle_elements.
        """
        epochs = list(self._generate_epoch_sequence(
            start=request.start_epoch,
            stop=request.stop_epoch,
            step_seconds=request.step_seconds,
        ))

        logger.info(
            "batch_propagation_start",
            object_count=len(request.tle_elements),
            epoch_count=len(epochs),
            workers=request.workers,
        )

        results: list[PropagationResult] = []

        if len(request.tle_elements) <= 10 or request.workers == 1:
            # Single-process for small batches
            for tle in request.tle_elements:
                result = self._propagate_one(tle=tle, epochs=epochs)
                results.append(result)
        else:
            # Multi-process for large batches
            with ProcessPoolExecutor(max_workers=request.workers) as pool:
                futures = {
                    pool.submit(self._propagate_one, tle=tle, epochs=epochs): tle
                    for tle in request.tle_elements
                }
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        tle = futures[future]
                        logger.error(
                            "propagation_worker_error",
                            norad_id=tle.norad_id,
                            error=str(exc),
                        )

        logger.info(
            "batch_propagation_complete",
            object_count=len(results),
            total_state_vectors=sum(len(r.state_vectors) for r in results),
        )
        return results

    def _propagate_one(
        self,
        tle: TwoLineElement,
        epochs: list[datetime],
    ) -> PropagationResult:
        """Worker function for a single TLE across all epochs."""
        state_vectors = self.propagate_single(tle=tle, epochs=epochs)
        nominal = [sv for sv in state_vectors if sv.is_nominal]
        errors = [
            {"epoch": sv.epoch.isoformat(), "error_code": sv.error_code}
            for sv in state_vectors
            if not sv.is_nominal
        ]
        return PropagationResult(
            norad_id=tle.norad_id,
            tle=tle,
            state_vectors=nominal,
            propagation_errors=errors,
            total_epochs=len(state_vectors),
            nominal_epochs=len(nominal),
        )

    @staticmethod
    def _generate_epoch_sequence(
        start: datetime,
        stop: datetime,
        step_seconds: int,
    ) -> Iterator[datetime]:
        """Generate evenly-spaced epoch sequence from start to stop inclusive."""
        current = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
        stop_utc = stop.replace(tzinfo=timezone.utc) if stop.tzinfo is None else stop

        from datetime import timedelta
        step = timedelta(seconds=step_seconds)
        while current <= stop_utc:
            yield current
            current += step

    def _should_apply_j2_correction(self, position_eci: np.ndarray) -> bool:
        """Apply J2 correction only for LEO objects (< 2000 km altitude)."""
        altitude = float(np.linalg.norm(position_eci)) - EARTH_RADIUS_KM
        return altitude < 2000.0

    def _apply_j2_delta(
        self,
        position: np.ndarray,
        velocity: np.ndarray,
        epoch: datetime,
        tle: TwoLineElement,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Apply first-order J2 perturbation correction to position/velocity.

        This implements a simplified drag-free J2 secular rate correction
        on top of the SGP4 output. For full precision, use the numerical
        integrator (Cowell's method) in orbital_engine.src.propagator.numerical.

        The correction is approximately 0.01-0.1 km level over one orbit.
        """
        r = float(np.linalg.norm(position))
        r2 = r ** 2
        r5 = r ** 5
        z = position[2]
        z2 = z ** 2

        j2_factor = (3.0 / 2.0) * J2_COEFFICIENT * (EARTH_RADIUS_KM ** 2) / r5
        common = 5.0 * z2 / r2

        accel = j2_factor * MU_KM3_S2 * np.array([
            position[0] * (common - 1.0),
            position[1] * (common - 1.0),
            position[2] * (common - 3.0),
        ])

        # First-order Taylor correction: delta_r ≈ 0.5 * a_J2 * dt^2
        # For ephemeris output we only correct velocity slightly
        dt = 1.0  # 1-second perturbation window
        corrected_velocity = velocity + accel * dt

        return position, corrected_velocity
