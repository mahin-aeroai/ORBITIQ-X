"""
ORBITIQ-X Orbital Engine
Clohessy-Wiltshire (CW) Relative Motion

The Hill-Clohessy-Wiltshire equations describe the motion of a deputy
satellite relative to a chief satellite in a circular reference orbit,
in the LVLH (Hill) frame.

Axes (CW convention):
  x : radial (outward positive)
  y : along-track (velocity direction positive)
  z : cross-track (orbital angular momentum positive)

Valid assumptions:
  - Chief orbit is circular (or nearly circular, e < 0.05)
  - Deputy remains within ~50 km of chief
  - No perturbations (drag, J2) — for short-duration proximity operations

For elliptical reference orbits, use the Tschauner-Hempel (TH) equations
implemented in hifi_integrator.py.

Applications in ORBITIQ-X:
  - Relative motion analysis for conjunction events
  - Formation flying geometry checks
  - Debris field relative motion
  - Maneuver targeting (impulsive ΔV for rendezvous)

Reference:
  Clohessy, W. and Wiltshire, R. (1960). "Terminal guidance system
  for satellite rendezvous." Journal of the Aerospace Sciences 27(9).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CWInitialState:
    """Initial relative state in LVLH (Hill) frame, km and km/s."""
    x0: float   # radial (km)
    y0: float   # along-track (km)
    z0: float   # cross-track (km)
    xd0: float  # radial velocity (km/s)
    yd0: float  # along-track velocity (km/s)
    zd0: float  # cross-track velocity (km/s)


@dataclass(frozen=True)
class CWState:
    """Relative state at time t in LVLH frame."""
    t: float    # seconds from epoch
    x: float    # km
    y: float    # km
    z: float    # km
    xd: float   # km/s
    yd: float   # km/s
    zd: float   # km/s

    @property
    def position(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])

    @property
    def velocity(self) -> np.ndarray:
        return np.array([self.xd, self.yd, self.zd])

    @property
    def range_km(self) -> float:
        return float(np.linalg.norm(self.position))


@dataclass(frozen=True)
class DeltaV:
    """Impulsive maneuver in LVLH frame."""
    t: float    # seconds from epoch
    dvx: float  # km/s (radial)
    dvy: float  # km/s (along-track)
    dvz: float  # km/s (cross-track)

    @property
    def magnitude_ms(self) -> float:
        return math.sqrt(self.dvx**2 + self.dvy**2 + self.dvz**2) * 1000.0  # m/s


class ClohessyWiltshire:
    """
    Analytical solution to the CW equations.

    Provides:
    - Propagation of relative state to arbitrary time t
    - State transition matrix Φ(t)
    - Natural drift trajectory (free-drift ellipse)
    - Impulsive ΔV for drift correction and rendezvous
    """

    def __init__(self, n: float):
        """
        Parameters
        ----------
        n : float
            Mean motion of the chief orbit [rad/s].
            For a 400 km circular orbit: n ≈ 0.00113 rad/s
        """
        self.n = n

    @classmethod
    def from_altitude_km(cls, altitude_km: float) -> "ClohessyWiltshire":
        """Convenience constructor from circular orbit altitude."""
        MU = 398600.4418  # km³/s²
        R_E = 6378.137    # km
        a = R_E + altitude_km
        n = math.sqrt(MU / a**3)
        return cls(n=n)

    def propagate(self, s0: CWInitialState, t: float) -> CWState:
        """
        Analytical solution of CW equations at time t [seconds].

        x(t) = (4-3cos(nt))x₀ + sin(nt)ẋ₀/n + 2(1-cos(nt))ẏ₀/n
        y(t) = 6(sin(nt)-nt)x₀ + y₀ - 2(1-cos(nt))ẋ₀/n + (4sin(nt)-3nt)ẏ₀/n
        z(t) = z₀cos(nt) + ż₀sin(nt)/n
        ẋ(t) = 3n sin(nt)x₀ + cos(nt)ẋ₀ + 2sin(nt)ẏ₀
        ẏ(t) = 6n(cos(nt)-1)x₀ - 2sin(nt)ẋ₀ + (4cos(nt)-3)ẏ₀
        ż(t) = -nz₀sin(nt) + ż₀cos(nt)
        """
        n  = self.n
        nt = n * t
        cn = math.cos(nt)
        sn = math.sin(nt)

        x0, y0, z0   = s0.x0, s0.y0, s0.z0
        xd0, yd0, zd0 = s0.xd0, s0.yd0, s0.zd0

        x  = (4 - 3*cn)*x0 + sn*xd0/n + 2*(1-cn)*yd0/n
        y  = 6*(sn - nt)*x0 + y0 - 2*(1-cn)*xd0/n + (4*sn - 3*nt)*yd0/n
        z  = z0*cn + zd0*sn/n

        xd = 3*n*sn*x0 + cn*xd0 + 2*sn*yd0
        yd = 6*n*(cn - 1)*x0 - 2*sn*xd0 + (4*cn - 3)*yd0
        zd = -n*z0*sn + zd0*cn

        return CWState(t=t, x=x, y=y, z=z, xd=xd, yd=yd, zd=zd)

    def state_transition_matrix(self, t: float) -> np.ndarray:
        """
        6×6 CW state transition matrix Φ(t).
        Maps [x,y,z,ẋ,ẏ,ż]₀ → [x,y,z,ẋ,ẏ,ż](t).
        """
        n  = self.n
        nt = n * t
        cn = math.cos(nt)
        sn = math.sin(nt)

        Phi = np.array([
            # x    y    z     xd       yd          zd
            [4-3*cn,  0,  0,  sn/n,    2*(1-cn)/n,  0    ],  # x
            [6*(sn-nt), 1, 0, -2*(1-cn)/n, (4*sn-3*nt)/n, 0],  # y
            [0,       0, cn,  0,       0,           sn/n  ],  # z
            [3*n*sn,  0,  0,  cn,      2*sn,        0     ],  # xd
            [6*n*(cn-1), 0, 0, -2*sn,  4*cn-3,      0     ],  # yd
            [0,       0, -n*sn, 0,     0,           cn    ],  # zd
        ])
        return Phi

    def trajectory(
        self,
        s0: CWInitialState,
        duration_s: float,
        dt_s: float = 60.0,
    ) -> list[CWState]:
        """
        Generate trajectory of deputy relative to chief.
        Returns list of CWState at each time step.
        """
        t = 0.0
        states = []
        while t <= duration_s:
            states.append(self.propagate(s0, t))
            t += dt_s
        return states

    def drift_ellipse_params(self, s0: CWInitialState) -> dict[str, float]:
        """
        Determine the natural drift ellipse (free-drift trajectory).

        For a general initial state, the in-plane motion traces an
        ellipse with semi-axes:
          a_radial    = |ẋ₀/n - 2ẏ₀/n + ...|
          a_along     = 2 * a_radial (2:1 ratio)
        The z-component is independent (simple harmonic oscillator).

        Returns parameters of the natural drift ellipse.
        """
        n = self.n
        x0, xd0, yd0 = s0.x0, s0.xd0, s0.yd0

        # Centre of the natural drift ellipse
        x_c = 0.0   # ellipse centre radial offset from chief
        y_c = s0.y0 - 2*xd0/n + 6*(n*s0.x0 - s0.yd0)*s0.t if hasattr(s0, 't') else s0.y0 - 2*xd0/n

        # Semi-axes (Hill 1878 result)
        a_x = math.sqrt((xd0/n)**2 + (x0 + 2*yd0/n)**2 * 0.0 + (2*yd0/n)**2)
        a_y = 2.0 * math.sqrt((xd0/n)**2 + (2*yd0/n - x0)**2 / 4)

        a_z = math.sqrt(s0.z0**2 + (s0.zd0/n)**2)

        return {
            "semi_axis_radial_km": a_x,
            "semi_axis_along_track_km": a_y,
            "semi_axis_cross_track_km": a_z,
            "ellipse_centre_y_km": y_c,
            "out_of_plane_amplitude_km": a_z,
        }

    def delta_v_for_drift_nulling(self, s: CWState) -> DeltaV:
        """
        Compute impulsive ΔV at the current state to null relative drift.
        Targets a stationary (or bounded) relative position.
        """
        n = self.n
        x, xd, yd = s.x, s.xd, s.yd

        # Required velocities for bounded (non-drifting) motion:
        # yd_req = -2*n*x (keeps y-drift = 0 for bounded orbit)
        # xd_req can remain unchanged for a passive safety ellipse
        xd_req = xd
        yd_req = -2.0 * n * x

        return DeltaV(
            t=s.t,
            dvx=xd_req - xd,
            dvy=yd_req - yd,
            dvz=0.0,
        )

    def two_impulse_rendezvous(
        self,
        s0: CWInitialState,
        t_maneuver: float,
        t_final: float,
        x_f: float = 0.0,
        y_f: float = 0.0,
        z_f: float = 0.0,
    ) -> tuple[DeltaV, DeltaV]:
        """
        Two-impulse rendezvous:
        - ΔV₁ at t_maneuver to target [x_f, y_f, z_f] at t_final
        - ΔV₂ at t_final to null relative velocity

        Returns (dv1, dv2) in LVLH frame.
        """
        # Propagate free drift to maneuver time
        s_m = self.propagate(s0, t_maneuver)

        dt = t_final - t_maneuver
        n, nt = self.n, self.n * dt
        cn, sn = math.cos(nt), math.sin(nt)

        # CW inverse problem: given initial pos and desired final pos,
        # solve for required velocities at t_maneuver.
        # Solve: [x_f; y_f; z_f] = Phi_rr * r_m + Phi_rv * v_req
        # → v_req = Phi_rv⁻¹ * (r_f - Phi_rr * r_m)

        Phi_rr = np.array([
            [4-3*cn, 0,  0 ],
            [6*(sn-nt), 1, 0],
            [0,      0, cn],
        ])
        Phi_rv = np.array([
            [sn/n,    2*(1-cn)/n, 0   ],
            [-2*(1-cn)/n, (4*sn-3*nt)/n, 0],
            [0,       0,          sn/n],
        ])

        r_m = np.array([s_m.x, s_m.y, s_m.z])
        r_f = np.array([x_f, y_f, z_f])

        Phi_rv_inv = np.linalg.pinv(Phi_rv)
        v_req = Phi_rv_inv @ (r_f - Phi_rr @ r_m)

        dv1 = DeltaV(
            t=t_maneuver,
            dvx=v_req[0] - s_m.xd,
            dvy=v_req[1] - s_m.yd,
            dvz=v_req[2] - s_m.zd,
        )

        # Apply ΔV₁ and propagate to final time
        s_after_dv1 = CWInitialState(
            x0=s_m.x, y0=s_m.y, z0=s_m.z,
            xd0=v_req[0], yd0=v_req[1], zd0=v_req[2],
        )
        s_f = self.propagate(s_after_dv1, dt)

        # ΔV₂ nulls residual velocity at rendezvous point
        dv2 = DeltaV(
            t=t_final,
            dvx=-s_f.xd,
            dvy=-s_f.yd,
            dvz=-s_f.zd,
        )

        return dv1, dv2
