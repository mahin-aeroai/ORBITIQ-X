# Contributing to ORBITIQ-X

Thank you for investing time in ORBITIQ-X. This document defines the
development workflow, coding standards, and architectural process
contributors must follow to maintain production quality.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Development Workflow](#development-workflow)
3. [Branch Strategy](#branch-strategy)
4. [Commit Standards](#commit-standards)
5. [Python Standards](#python-standards)
6. [TypeScript / Next.js Standards](#typescript--nextjs-standards)
7. [Testing Requirements](#testing-requirements)
8. [Architecture Decision Records](#architecture-decision-records)
9. [Pull Request Process](#pull-request-process)
10. [Documentation Standards](#documentation-standards)
11. [Security Policy](#security-policy)

---

## Code of Conduct

All contributors must adhere to professional aerospace engineering
standards: precision, traceability, and zero-tolerance for unverified
assumptions in safety-critical orbital mechanics code.

---

## Development Workflow

### 1. Fork & Clone

```bash
git clone https://github.com/mahin-aeroai/ORBITIQ-X.git
cd ORBITIQ-X
git remote add upstream https://github.com/mahin-aeroai/ORBITIQ-X.git
```

### 2. Set Up Environment

```bash
# Python backend & engines
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt
pre-commit install

# Frontend
cd frontend && npm install && cd ..

# Launch dev stack
docker compose -f deployment/docker/docker-compose.dev.yml up -d
```

### 3. Create Feature Branch

```bash
git checkout main
git pull upstream main
git checkout -b feat/orbital-conjunction-montecarlo
```

---

## Branch Strategy

| Branch Pattern | Purpose |
|---------------|---------|
| `main` | Production-ready code, protected |
| `develop` | Integration branch for next release |
| `feat/<scope>/<description>` | New features |
| `fix/<scope>/<description>` | Bug fixes |
| `refactor/<scope>/<description>` | Refactoring without behavior change |
| `docs/<description>` | Documentation only |
| `chore/<description>` | Build, CI, dependencies |
| `adr/<number>-<title>` | Architecture decisions |

Scopes: `orbital`, `ssa`, `rag`, `agents`, `kg`, `frontend`, `backend`, `deploy`

---

## Commit Standards

ORBITIQ-X follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short imperative summary>

[Optional body: explain WHY, not WHAT]

[Optional footer: BREAKING CHANGE: ..., Refs: #issue]
```

**Types:** `feat` | `fix` | `refactor` | `perf` | `test` | `docs` | `chore` | `ci`

**Examples:**

```
feat(orbital): add J2-perturbation to SGP4 propagator

Implements first-order J2 oblateness correction to improve LEO
position accuracy from ~1km to ~100m over 24h propagation.

Refs: #42
```

```
fix(ssa): correct Pc computation for near-circular relative motion

The Foster method implementation assumed linear relative motion
for all encounter geometries. Added short-encounter check per
Patera (2001) and switched to Monte Carlo fallback for high-eccentricity
approaches. BREAKING CHANGE: CDM Pc field now returns float instead of str.
```

---

## Python Standards

### Style & Formatting

- **Formatter:** Black (line-length=88)
- **Linter:** Ruff (replaces flake8 + isort + pyupgrade)
- **Type checker:** mypy (strict mode for `orbital-engine/`, `backend/`)
- **Docstrings:** NumPy style (mandatory for all public functions)

```python
def compute_probability_of_collision(
    relative_position: np.ndarray,
    relative_velocity: np.ndarray,
    combined_covariance: np.ndarray,
    combined_hbr: float,
) -> float:
    """
    Compute probability of collision using the Foster (1992) method.

    Parameters
    ----------
    relative_position : np.ndarray
        Relative position vector in RTN frame [km], shape (3,).
    relative_velocity : np.ndarray
        Relative velocity vector in RTN frame [km/s], shape (3,).
    combined_covariance : np.ndarray
        Combined 3x3 position covariance matrix in RTN frame [km²].
    combined_hbr : float
        Combined hard-body radius (sum of individual object radii) [km].

    Returns
    -------
    float
        Probability of collision in [0, 1].

    Raises
    ------
    ValueError
        If covariance matrix is not positive semi-definite.

    References
    ----------
    .. [1] Foster, J.L. & Estes, H.S. (1992). A parametric analysis of
           orbital debris collision probability and maneuver rate for space
           vehicles. NASA/JSC-25898.

    Examples
    --------
    >>> Pc = compute_probability_of_collision(
    ...     relative_position=np.array([0.1, 0.0, 0.0]),
    ...     relative_velocity=np.array([0.0, 0.5, 0.0]),
    ...     combined_covariance=np.eye(3) * 0.01,
    ...     combined_hbr=0.02,
    ... )
    >>> assert 0.0 <= Pc <= 1.0
    """
```

### Aerospace Conventions

- SI units throughout (km, km/s, seconds, radians) unless explicitly documented
- All orbital element sets must carry epoch as `datetime` with UTC tzinfo
- Functions must validate input dimensionality and physical plausibility
- No magic numbers — define named constants in `orbital-engine/src/constants.py`

```python
# ✅ Correct
WGS84_EARTH_RADIUS_KM: Final[float] = 6378.137
WGS84_MU_KM3_S2: Final[float] = 398600.4418

# ❌ Wrong
radius = 6378.137
mu = 398600.4418
```

---

## TypeScript / Next.js Standards

- **Strict TypeScript** — `strict: true` in tsconfig, no `any` types
- **ESLint** — next/core-web-vitals + custom aerospace rules
- **Prettier** — consistent formatting
- **Component pattern:** Functional components + React Query for server state
- **Naming:** PascalCase components, camelCase hooks (`useConjunctionAlerts`)

```tsx
// Domain types must be explicit — no Record<string, any>
interface ResidentSpaceObject {
  readonly noradId: number;
  readonly satName: string;
  readonly intlDesignator: string;
  readonly orbitClass: OrbitalRegime;
  readonly tle: TwoLineElement;
  readonly rcs: RadarCrossSection | null;
  readonly launchEpoch: Date;
}

// Data-fetching hook pattern
function useConjunctionAlerts(objectId: number) {
  return useQuery({
    queryKey: ['conjunctions', objectId],
    queryFn: () => apiClient.get<ConjunctionAlert[]>(`/ssa/conjunctions/${objectId}`),
    refetchInterval: 30_000,   // 30s polling — SSA data is time-critical
    staleTime: 15_000,
  });
}
```

---

## Testing Requirements

### Coverage Thresholds (enforced in CI)

| Module | Min Coverage |
|--------|-------------|
| `orbital-engine/` | 90% |
| `backend/app/services/` | 85% |
| `rag/src/` | 80% |
| `agents/src/` | 75% |
| `frontend/src/` | 70% |

### Test File Naming

```
orbital-engine/tests/propagator/test_sgp4_propagator.py
orbital-engine/tests/conjunction/test_foster_pc.py
backend/tests/api/test_satellite_endpoints.py
agents/tests/test_ssa_agent.py
```

### Required Test Categories

Every PR touching `orbital-engine/` MUST include:
1. **Unit test** for the pure function/algorithm
2. **Regression test** against published numerical reference (cite source)
3. **Edge case test** (zero eccentricity, polar orbit, GEO)

---

## Architecture Decision Records

Major architectural decisions are documented as ADRs in `docs/adr/`.

**Format:** `ADR-NNNN-<kebab-title>.md`

Template:
```markdown
# ADR-0001: Use SGP4 as Primary Propagator

**Date:** YYYY-MM-DD
**Status:** Accepted | Proposed | Deprecated | Superseded

## Context
[Why is this decision needed?]

## Decision
[What was decided?]

## Consequences
[What are the tradeoffs?]

## Alternatives Considered
[What else was evaluated?]
```

---

## Pull Request Process

1. **Self-review** — run `./deployment/scripts/lint-check.sh` before opening PR
2. **PR title** must follow Conventional Commits format
3. **Description** must include: summary, testing done, breaking changes
4. **Required checks** (all must pass):
   - `ci/lint` — Black, Ruff, ESLint, Prettier
   - `ci/typecheck` — mypy strict, tsc --noEmit
   - `ci/test` — pytest + Playwright with coverage thresholds
   - `ci/docker-build` — all service images build successfully
5. **Minimum reviewers:** 1 (aerospace domain + software quality)
6. **Squash merge** to main with conventional commit message

---

## Documentation Standards

- **API docs:** Auto-generated from FastAPI type annotations + Pydantic schemas
- **Algorithm docs:** LaTeX equations in docstrings, rendered in MkDocs
- **ADR:** Required for every choice of: DB, LLM, vector store, propagator, framework
- **Changelogs:** Auto-generated from conventional commits via `git-cliff`

---

## Security Policy

- **Secrets:** Never hardcode. Use `.env` locally, secret manager in prod.
- **Dependencies:** Dependabot PRs merged weekly.
- **SAST:** Bandit runs on every PR for Python code.
- **CVE tracking:** `safety check` runs in CI against Python deps.
- **Space-Track credentials:** Never logged, never stored in DB, rotated monthly.

Report vulnerabilities privately to: **security@orbitiq-x.dev**
