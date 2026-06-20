# ADR-0001: Use SGP4/SDP4 as Primary Orbital Propagator

**Date:** 2026-06-20  
**Status:** Accepted  
**Decision Maker:** Mahin Nandipa  
**Stakeholders:** Orbital Engine team, SSA team

---

## Context

ORBITIQ-X requires a reliable, widely-accepted orbital propagator as the
foundation of all position/velocity computations. The choice of propagator
determines:

- **Accuracy**: position error over time relative to truth orbit
- **Input format**: what element sets are accepted
- **Interoperability**: compatibility with external SSA data sources
- **Computational cost**: time to propagate 10,000+ objects

The platform ingests TLE data from Space-Track.org and CelesTrak as its
primary data source. These sources provide Two-Line Element (TLE) sets
encoded for use with the SGP4/SDP4 family of propagators.

---

## Decision

**Use SGP4/SDP4 (implemented via `python-sgp4`) as the primary propagator.**

- SGP4 for near-earth objects (perigee < ~5,877 km)
- SDP4 for deep-space objects (period > 225 minutes)
- WGS-72 Earth gravity model (AFSPC standard for TLE compatibility)
- Optional WGS-84 for modern precision requirements

Add a first-order J2 perturbation correction layer for LEO objects
(altitude < 2,000 km) where atmospheric drag and oblateness errors are
most significant.

For high-fidelity use cases (conjunction analysis, maneuver planning),
provide a secondary numerical integrator (Cowell's method + RK4/RK78)
in `orbital-engine/src/propagator/numerical.py`.

---

## Rationale

| Criterion | SGP4/SDP4 | Keplerian (2-Body) | Numerical (Cowell) |
|-----------|-----------|--------------------|--------------------|
| TLE compatibility | ✅ Native | ❌ Requires conversion | ❌ Requires conversion |
| Accuracy (LEO, 1 orbit) | ~1 km | ~10 km | <100 m |
| Accuracy (LEO, 24h) | ~1-3 km | ~50 km | <1 km |
| Throughput (10k objects) | ~200ms | ~50ms | ~30 min |
| Industry standard | ✅ AFSPC standard | ❌ Research only | ✅ High-fidelity missions |
| External data sources | ✅ All TLE sources | ❌ | ❌ |

SGP4 is the de facto standard for TLE-based SSA operations. All major
SSA providers (Space-Track.org, CelesTrak, LeoLabs) distribute data
in TLE format optimized for SGP4. Using a different propagator with
TLE inputs would introduce systematic errors.

---

## Consequences

**Positive:**
- Full compatibility with Space-Track.org and CelesTrak TLE data
- Well-validated against published position reference data (STK, GMAT)
- `python-sgp4` provides a compiled C extension for throughput
- Industry-standard — operators, analysts, and auditors trust SGP4 outputs

**Negative:**
- SGP4 accuracy degrades over time (few-day TLE age → few-km errors)
- Not suitable for precise maneuver planning (use numerical integrator)
- J2-only perturbation model (no atmospheric drag optimization)

**Mitigations:**
- Propagate only with TLE age < 7 days; flag stale TLEs (>14 days)
- Route conjunction analysis Pc computation through the numerical
  integrator when miss distance < 1 km and Pc > 0.001
- Document accuracy limitations in API response metadata

---

## Alternatives Considered

### Keplerian 2-Body Propagator
Rejected. Too inaccurate for real SSA operations. Suitable only for
educational demonstrations.

### Numerical Integration (Cowell + RK78) as Primary
Rejected. ~10,000× slower than SGP4 for bulk propagation. Cannot accept
TLE inputs directly. Would require acquiring higher-quality state vectors
(SP catalog, radar data), which is not publicly available.

### Astropy `twobody` or Poliastro
Rejected. Neither implements SGP4 natively. Poliastro is research-focused
and does not support the AFSPC TLE format out of the box.

### GMAT (GSFC Mission Analysis Tool)
Rejected. External binary dependency, GPL license incompatibility with
planned commercial use, no Python-native API.

---

## References

- [1] Hoots & Roehrich (1980). Spacetrack Report No. 3.
- [2] Vallado et al. (2006). "Revisiting Spacetrack Report #3." AIAA 2006-6753.
- [3] python-sgp4: https://github.com/brandon-rhodes/python-sgp4
- [4] USSF Space-Track.org TLE format specification.
