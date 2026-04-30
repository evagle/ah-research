# Phase 4.1 — Portfolio Optimizer Design

**Status:** Draft (awaiting user review)
**Date:** 2026-04-30
**Supersedes:** nothing
**Supersedes notes in:** `2026-04-28-ah-research-platform-design.md` §"Phase 4", `2026-04-29-ah-research-phase-3-analysis-design.md` §"Out of scope / Future extensions"

---

## 1. Mission

Add a CVXPY-based convex portfolio optimizer to `ah_research` that produces risk-aware target weights from three inputs (universe, expected returns, covariance) subject to a constraint set, with both standalone and backtest-integrated usage modes.

Phase 4.1 covers the **optimizer only**. Filings → analysis integration is **Phase 4.2** (separate spec).

## 2. Context

Phase 3 shipped a heuristic `Constructor` that assigns weights by rule (equal-weight, signal-weighted, sector-balanced) with a relax-and-proceed posture toward constraint violations. This is a fine baseline but three gaps remain:

1. **No risk-aware weighting.** Constructor ignores the covariance structure of assets — equal-weighted five mutually-correlated banks is a concentrated bet.
2. **No formal optimization.** Constraints are applied post-hoc; the weights are not optimal under any defined objective.
3. **No turnover control.** When rebalancing over time, heuristic weights can flip dramatically, incurring transaction costs that swamp alpha.

Phase 4.1 fills all three with a proper convex optimizer. Phase 3's `Constructor` remains untouched; the optimizer is an orthogonal component that can be called standalone or plugged into the Phase 2 backtest as a `WeightStrategy`.

Explicit non-goals of Phase 4.1 are documented in §12.

## 3. Design decisions (from brainstorm)

| # | Decision | Rationale |
|---|---|---|
| 1 | Objectives: **mean-variance + risk-parity** | MV is the pedagogical baseline & integrates with signal strategies; risk-parity is the "trust Σ, distrust μ̂" alternative for noisy-expected-return universes like A/H dual-listings |
| 2 | Covariance: pluggable `CovarianceEstimator`; ship `Sample` + `LedoitWolf` | Mirrors Phase 2's `SignalStrategy` / `WeightStrategy` Protocol pattern; factor-model estimators can be dropped in later without touching optimizer internals |
| 3 | Expected returns: pluggable `ExpectedReturnsEstimator`; ship user-supplied + signal-based + historical-mean | Signal-based estimator is what makes the optimizer feel native to ah_research (factor signals → μ̂); historical-mean is the naive baseline; user-supplied supports notebook experimentation |
| 4 | Integration: standalone `Optimizer.build(...)` + `OptimizedWeightStrategy` Phase 2 plug-in; Constructor `mode="optimize"` deferred | Standalone alone is too narrow (no backtest); Constructor integration couples optimizer feasibility semantics to heuristic relax-and-proceed — separate concern |
| 5 | Feasibility: strict default (`InfeasibleError`); `soft=True` flips to penalty-based with slack variables | Strict matches the quant mindset (know when constraints are impossible); soft is the escape hatch for exploratory notebooks and live rebalancing |
| 6 | Constraints: convex-only + new `max_turnover`, `long_only=True` default; cardinality via external pre-filter | Cardinality is MIP-hard; commercial solvers or fragile open-source MIP; pre-filter covers the use case cleanly. `max_turnover` is essential for meaningful backtest rebalancing |
| 7 | Return: `OptimizationResult` frozen dataclass + `.to_markdown()` / `.to_dict()` | Mirrors Phase 3 `ConstructionReport` and `Dossier` patterns; `active_constraints` list is genuinely diagnostic; `.to_dict()` sets up Phase 5 AI reasoning inputs |

## 4. Architecture

### 4.1 Module layout

```
src/ah_research/
├── portfolio/
│   ├── construction.py         # (existing, Phase 2; untouched)
│   ├── constructor.py          # (existing, Phase 3; untouched)
│   ├── constraints.py          # (existing; extend with 2 new kinds — see §5.1)
│   └── optimizer/              # NEW in Phase 4.1
│       ├── __init__.py         # public API: Optimizer, OptimizationResult, mean_variance, risk_parity
│       ├── problem.py          # CVXPY problem builders (MV, risk-parity objectives)
│       ├── cvxpy_constraints.py  # maps Constraint objects → CVXPY expressions
│       ├── errors.py           # OptimizerError, InfeasibleError, NumericalError, ValidationError
│       ├── result.py           # OptimizationResult frozen dataclass
│       └── estimators/
│           ├── __init__.py
│           ├── covariance.py   # CovarianceEstimator protocol + Sample + LedoitWolf
│           └── returns.py      # ExpectedReturnsEstimator protocol + 3 built-ins
└── strategies/
    └── optimized.py            # NEW: OptimizedWeightStrategy (Phase 2 WeightStrategy plug-in)
```

### 4.2 Dependencies

**New runtime:**
- `cvxpy>=1.5` — convex optimization DSL
- `clarabel>=0.9` — modern QP/SOCP/exp-cone solver (pure Rust + Python wheel); default solver for problems requiring SOCP or exp-cone (risk-parity log-barrier, tracking_error, soft mode)

**Already transitively available via cvxpy:**
- `osqp` — fast pure-QP solver; used for MV when no SOCP/exp-cone constraints are present

**Already present:**
- `scikit-learn` (for `LedoitWolfCovariance`)
- `numpy`, `pandas`, `scipy`

## 5. Core types

### 5.1 Constraint extensions (additive to Phase 3)

Phase 3's `Constraint` frozen dataclass is extended with two new `kind` values. No breaking changes; existing Phase 3 kinds (`max_weight`, `max_gross`, `sector_neutral_to`, `tracking_error`, `min_positions`, `max_positions`) retain their current semantics in the `Constructor` codepath. The optimizer accepts the convex-mappable subset — `min_positions` and `max_positions` raise `ValidationError` at optimizer construction time with a message pointing to external pre-filtering.

New kinds:

```python
Constraint(kind="max_turnover", value=0.25, baseline=prev_weights_series)
    # Mapping: cvxpy.norm(w - baseline, 1) <= value
    # `baseline` is a pd.Series indexed by symbol; missing entries default to 0
    # Used primarily in OptimizedWeightStrategy via state.prev_weights

Constraint(kind="long_only", value=True)
    # Mapping: w >= 0
    # Default-on in Optimizer (long_only=True kwarg); can be disabled via value=False or
    # by omitting from the constraint list and passing long_only=False to Optimizer
```

### 5.2 `CovarianceEstimator` protocol

```python
# src/ah_research/portfolio/optimizer/estimators/covariance.py
from typing import Protocol, runtime_checkable
import pandas as pd

@runtime_checkable
class CovarianceEstimator(Protocol):
    """Estimate Σ (N×N covariance matrix) from T×N returns."""
    def estimate(self, returns: pd.DataFrame) -> pd.DataFrame: ...

class SampleCovariance:
    def __init__(self, min_periods: int = 60): ...
    def estimate(self, returns: pd.DataFrame) -> pd.DataFrame: ...
    # Raises ValidationError if T < min_periods or any all-NaN column

class LedoitWolfCovariance:
    def __init__(self): ...
    def estimate(self, returns: pd.DataFrame) -> pd.DataFrame: ...
    # Delegates to sklearn.covariance.LedoitWolf; `shrinkage_` retrievable via
    # last_shrinkage_ property for diagnostics
    @property
    def last_shrinkage_(self) -> float: ...
```

### 5.3 `ExpectedReturnsEstimator` protocol

```python
# src/ah_research/portfolio/optimizer/estimators/returns.py
from ah_research.model import Symbol
from ah_research.data import DataRepository
from ah_research.strategies import SignalStrategy

@runtime_checkable
class ExpectedReturnsEstimator(Protocol):
    def estimate(
        self, symbols: list[Symbol], as_of: pd.Timestamp, repo: DataRepository,
    ) -> pd.Series: ...  # indexed by symbol

class UserSuppliedReturns:
    def __init__(self, mu: pd.Series): ...
    # Passthrough; validates index matches `symbols` at estimate() time

class HistoricalMeanReturns:
    def __init__(
        self,
        lookback_days: int = 252,
        shrinkage: float = 0.0,       # 0.0 = raw sample mean; 1.0 = shrink fully to shrink_to
        shrink_to: Literal["cross_sectional_mean", "zero"] = "cross_sectional_mean",
    ): ...

class SignalBasedReturns:
    def __init__(
        self,
        signal_strategy: SignalStrategy,
        spread: float = 0.02,              # top-signal → +spread, bottom → -spread (annualized)
        neutralize_sector: bool = True,    # rank within sector before mapping to spread
    ): ...
```

### 5.4 `OptimizationResult` frozen dataclass

```python
# src/ah_research/portfolio/optimizer/result.py
from dataclasses import dataclass
from typing import Literal, Mapping
import pandas as pd

@dataclass(frozen=True)
class OptimizationResult:
    weights: pd.Series                        # indexed by Symbol
    objective: Literal["mean_variance", "risk_parity"]
    solver_status: Literal["optimal", "optimal_inaccurate", "soft_relaxed"]
    objective_value: float                    # final objective value at w*
    active_constraints: tuple[str, ...]       # constraint kinds binding at optimum (within tol)
    slack: Mapping[str, float]                # empty when not soft; keyed by constraint kind
    expected_return: float | None             # MV only (μᵀw*)
    expected_variance: float                  # always (w*ᵀΣw*)
    risk_contributions: pd.Series | None      # risk-parity only (MRC_i = w_i · (Σw)_i / √(wᵀΣw))
    solver_name: str                          # "clarabel" or "osqp"
    solve_time_ms: float
    inputs_hash: str                          # sha256 of (symbols, μ, Σ, constraints, objective, kwargs)

    def to_dict(self) -> dict: ...           # JSON-serializable representation
    def to_markdown(self) -> str: ...        # human-readable summary (ASCII table of weights, diagnostics)
```

### 5.5 Error hierarchy

```python
class OptimizerError(Exception): ...            # base
class InfeasibleError(OptimizerError): ...      # CVXPY infeasible / unbounded in strict mode
class NumericalError(OptimizerError): ...       # optimal_inaccurate with tolerances exceeded
class ValidationError(OptimizerError): ...      # bad inputs (index mismatch, non-PSD Σ, NaN μ, unsupported constraint kind)
```

## 6. Optimizer API

### 6.1 `Optimizer` class

```python
# src/ah_research/portfolio/optimizer/__init__.py

class Optimizer:
    def __init__(
        self,
        *,
        objective: Literal["mean_variance", "risk_parity"],
        cov_estimator: CovarianceEstimator,
        returns_estimator: ExpectedReturnsEstimator | None = None,  # required for MV
        constraints: Sequence[Constraint] = (),
        risk_aversion: float = 1.0,      # λ in MV: min(λ·wᵀΣw - μᵀw)
        long_only: bool = True,          # default-on; adds w >= 0 to constraint set
        lookback_days: int = 252,        # returns window for Σ estimation
        solver: Literal["clarabel", "osqp", "auto"] = "auto",
        soft: bool = False,              # flip to penalty-based feasibility
        soft_penalty: float = 1e4,       # penalty weight on slack variables when soft=True
    ): ...

    def build(
        self,
        symbols: list[Symbol],
        as_of: pd.Timestamp,
        repo: DataRepository,
        *,
        prev_weights: pd.Series | None = None,  # for max_turnover constraint
    ) -> OptimizationResult: ...
```

**`build()` pipeline:**

1. Validate inputs (symbols non-empty, as_of is a valid timestamp, unsupported constraint kinds rejected).
2. Load returns via `repo.get_returns(symbols, as_of - lookback, as_of)` (PIT: strictly `< as_of`).
3. Σ = `cov_estimator.estimate(returns)`; verify PSD (adds tiny jitter `1e-10 * I` if near-singular).
4. For MV: μ = `returns_estimator.estimate(symbols, as_of, repo)`.
5. Build CVXPY variable `w = cp.Variable(N)`, objective, and constraint list.
   - For `max_turnover` with missing `prev_weights` baseline in the constraint AND no `prev_weights` kwarg → `ValidationError`.
6. Solve via chosen solver (see §6.3).
7. On `infeasible` / `unbounded` status with `soft=False` → raise `InfeasibleError` with full constraint listing.
8. On `optimal_inaccurate` with residuals above `1e-4` → raise `NumericalError` (tolerance tunable via `solver_tol` kwarg, default `1e-6`).
9. Assemble `OptimizationResult` with diagnostics (active constraints detected via CVXPY dual variables; slack only when `soft=True`).

### 6.2 Objective formulations

**Mean-variance:**
```
min    λ · wᵀ Σ w  −  μᵀ w
s.t.   Σ wᵢ = 1
       w ≥ 0                          (if long_only=True)
       <constraint set>
```

**Risk-parity** (Maillard, Roncalli, Teïletche 2010 log-barrier form):
```
min    ½ wᵀ Σ w  −  (1/N) · Σ log(wᵢ)
s.t.   Σ wᵢ = 1                        (normalized afterwards; log-barrier enforces w > 0)
       <constraint set, except long_only which is implied by log>
```

The risk-parity formulation requires `long_only=True` effectively (log-barrier). If user passes `long_only=False`, `ValidationError` is raised with a pointer to alternative formulations (to be added in a later phase if needed).

### 6.3 Solver selection (`solver="auto"`)

- Problems with only QP-compatible constructs (MV without `tracking_error`, `soft=False`, `long_only=True`, `max_weight`, `max_gross`, `sector_neutral_to`, `max_turnover`) → **OSQP**
- Problems with SOCP / exp-cone (risk-parity log-barrier, `tracking_error` quadratic-in-constraint, `soft=True` slack variables) → **CLARABEL**
- Users can override by passing `solver="clarabel"` or `solver="osqp"` explicitly; mismatched solver (e.g. `solver="osqp"` with risk-parity) → `ValidationError` at solve time.

### 6.4 Convenience helpers

Module-level ergonomic wrappers for common usage in notebooks:

```python
def mean_variance(
    symbols, as_of, repo, *,
    cov_estimator=None,                 # default: LedoitWolfCovariance()
    returns_estimator=None,             # default: HistoricalMeanReturns()
    constraints=(),
    risk_aversion: float = 1.0,
    **kwargs,
) -> OptimizationResult: ...

def risk_parity(
    symbols, as_of, repo, *,
    cov_estimator=None,                 # default: LedoitWolfCovariance()
    constraints=(),
    **kwargs,
) -> OptimizationResult: ...
```

Both delegate to `Optimizer(...)`. No additional logic.

## 7. Backtest integration

### 7.1 `OptimizedWeightStrategy`

```python
# src/ah_research/strategies/optimized.py
from ah_research.strategies import WeightStrategy     # Phase 2 protocol
from ah_research.portfolio.optimizer import Optimizer, OptimizationResult

class OptimizedWeightStrategy(WeightStrategy):
    """Phase 2 WeightStrategy that delegates to a Phase 4.1 Optimizer at each rebalance."""

    def __init__(
        self,
        optimizer: Optimizer,
        *,
        min_history_days: int | None = None,   # defaults to optimizer.lookback_days
    ): ...

    def weights(
        self,
        symbols: list[Symbol],
        as_of: pd.Timestamp,
        repo: DataRepository,
        state: BacktestState,                   # Phase 2 type; provides prev_weights
    ) -> pd.Series:
        result = self._optimizer.build(
            symbols, as_of, repo, prev_weights=state.prev_weights,
        )
        self._history.append(result)            # retained for post-backtest diagnostics
        return result.weights

    @property
    def history(self) -> list[OptimizationResult]:
        """All OptimizationResults from the backtest run, in rebalance order."""
        return list(self._history)
```

Notes:
- `state.prev_weights` is passed to `optimizer.build()` so `max_turnover` uses actual realized weights from the prior rebalance, not a user-specified baseline. This makes `max_turnover` meaningful in walk-forward backtests.
- `history` attribute lets notebooks extract turnover, active-constraint frequencies, solve-time trends, etc. after the backtest completes.
- On the first rebalance (no prev_weights), `state.prev_weights` is `None` or empty; optimizer treats this as "no turnover constraint applies" (if `max_turnover` was specified, it's silently skipped on rebalance 0 rather than raising).

### 7.2 Failure handling inside backtests

If `Optimizer.build()` raises inside the backtest loop:
- `InfeasibleError` / `NumericalError` → backtest halts with a diagnostic. `OptimizedWeightStrategy` does not auto-fallback; the researcher should use `soft=True` if best-effort weights are desired.
- `ValidationError` → re-raised (indicates a bug in setup, not a runtime issue).

## 8. Testing strategy

All test files live under `tests/unit/portfolio/optimizer/`, `tests/integration/`, and `tests/property/` following the Phase 3 layout.

### 8.1 Unit tests

- **Estimators** — each `CovarianceEstimator` and `ExpectedReturnsEstimator` in isolation with deterministic fixtures (fixed-seed random returns).
- **Constraint mapping** — each `Constraint.kind` produces the expected CVXPY expression (introspect via `cvxpy.Problem.constraints` list).
- **`OptimizationResult`** — `.to_dict()` round-trips (dict → `OptimizationResult.from_dict` → dict); `.to_markdown()` snapshot tests on fixed fixtures.
- **Solver selection** — `solver="auto"` picks OSQP vs CLARABEL correctly for each objective/constraint combination.

### 8.2 Property tests (hypothesis)

Universe generator: `1 ≤ N ≤ 20` symbols, T ≥ 60 daily returns sampled from multivariate normal with randomly-perturbed PSD Σ.

Invariants:
- `sum(weights) == 1` within `1e-6`
- `long_only=True` ⇒ all weights `≥ -1e-8`
- `max_weight=k` ⇒ all weights `≤ k + 1e-6`
- MV with `μ == 0` produces the same solution as the minimum-variance portfolio (analytically solved)
- Risk-parity solution has equal risk contributions: `|MRC_i - 1/N| < 1e-3` for all i
- MV with `λ → 0` approaches the max-return corner (single asset or the μ-argmax subset)

### 8.3 Golden tests

Fixed-seed synthetic 20-asset problem with analytically-known min-variance portfolio (no other constraints besides `sum(w)=1`, `long_only=True`). Tolerance `1e-4`. Serves as a regression canary for solver upgrades.

### 8.4 Integration tests

- **1-year walk-forward** — `OptimizedWeightStrategy` wrapped around MV optimizer, running on the Phase 2 synthetic universe for 252 trading days with monthly rebalance. Assertions:
  - Completes without solver errors
  - `MetricsBundle` returns finite Sharpe / CAGR / max-DD
  - Average turnover per rebalance ≤ `max_turnover` constraint
  - `strategy.history` has the expected number of `OptimizationResult` entries

- **Leakage canary** — reuse Phase 2 fixture pattern: instrument `DataRepository` to record the max timestamp accessed during `optimizer.build(as_of=T)`; assert `max_ts < T`.

### 8.5 Acceptance notebook

`notebooks/phase4_1_optimizer_example.ipynb`:

1. Load Phase 3 screener output for a small A-share universe (~30 symbols).
2. Run heuristic `Constructor` (Phase 3) — capture weights.
3. Run MV optimizer with `HistoricalMeanReturns` — capture `OptimizationResult`.
4. Run MV optimizer with `SignalBasedReturns(ValueFactorStrategy)` — capture.
5. Run risk-parity optimizer — capture.
6. Side-by-side comparison table: weights, expected variance, turnover-from-equal-weight, active constraints.
7. Walk-forward backtest using `OptimizedWeightStrategy` (MV + SignalBasedReturns) for 1 year; compare `MetricsBundle` to Phase 2's `ValueFactorStrategy` baseline.
8. Render `OptimizationResult.to_markdown()` for the final rebalance.

Notebook runs headless in CI via `nbclient`, same as Phase 3 notebooks.

## 9. Failure modes & edge cases

| Situation | Behavior |
|---|---|
| `symbols` empty | `ValidationError` |
| `T < cov_estimator.min_periods` | `ValidationError` from estimator |
| Σ estimated as non-PSD (numerical) | Add `1e-10 · I` jitter; re-verify; if still non-PSD → `NumericalError` |
| μ has NaNs | `ValidationError` |
| `prev_weights` index missing symbols currently in universe | Missing entries default to 0 (symbol entered universe since last rebalance) |
| `prev_weights` index has symbols no longer in universe | Those entries dropped (symbol exited universe) |
| Constraint set infeasible, `soft=False` | `InfeasibleError` with full constraint enumeration |
| Constraint set infeasible, `soft=True` | Slack variables added; `solver_status="soft_relaxed"`; slack dict populated |
| CVXPY returns `optimal_inaccurate` | If max primal/dual residual < `solver_tol` → treat as optimal; else → `NumericalError` |
| Risk-parity with `long_only=False` | `ValidationError` (log-barrier requires w > 0) |
| `min_positions` / `max_positions` in constraint list | `ValidationError` at `Optimizer` construction with message pointing to external pre-filter |

## 10. Performance budget

On an M-series Mac, Python 3.12, single-threaded solver, cold cache:

| Scenario | Target solve time (p50) |
|---|---|
| MV, N=30, no SOCP constraints, OSQP | < 50 ms |
| MV, N=100, no SOCP constraints, OSQP | < 200 ms |
| Risk-parity, N=30, CLARABEL | < 150 ms |
| Risk-parity, N=100, CLARABEL | < 500 ms |
| MV + tracking_error, N=50, CLARABEL | < 300 ms |

Walk-forward 252-day monthly rebalance (12 solves) on N=50 universe should complete in < 10 s total. These are rough targets; final numbers captured during implementation and locked as regression bounds (±50%) in a perf test.

## 11. Reproducibility

- `OptimizationResult.inputs_hash` = sha256 of `(sorted_symbols, μ.values, Σ.values, frozenset(constraints), objective, risk_aversion, long_only, soft)`. Deterministic for fixed inputs → supports cross-run equivalence checks.
- Solvers are deterministic given fixed inputs; no RNG in the optimization path (estimators that use sampling take an explicit `rng` seed).

## 12. Out of scope / deferred

Explicitly **not** in Phase 4.1:

- **MIP cardinality** (`min_positions`, `max_positions`) — requires commercial solver or fragile open-source MIP; covered externally by pre-filtering the universe before calling the optimizer.
- **Factor-model covariance** (Fama-French residuals, Barra-style factor risk model) — could be a new `CovarianceEstimator` implementation in a later phase.
- **Tracking error to external benchmark weights** — current `tracking_error` constraint is against zero; benchmark-relative tracking deferred (needs benchmark weight input plumbing).
- **`Constructor.build(mode="optimize")`** — couples optimizer's strict feasibility to Constructor's heuristic relax-and-proceed; belongs in a follow-up phase after the optimizer's behavior is well-understood in isolation.
- **A-share 100-share lot integer constraints** — mixed-integer nonlinear; large lift; caller can round post-optimization as a first approximation.
- **Transaction-cost-aware utility** (cost penalty in the objective) — 4.1 treats costs as a constraint (`max_turnover`) rather than a penalty; a future phase can add an `OptimizerConfig.cost_model` option.
- **Black-Litterman** prior μ̂ combining market-implied returns with user views — could be an `ExpectedReturnsEstimator` implementation in a future phase.
- **Multi-period / dynamic optimization** — 4.1 solves one period at a time; intertemporal choice deferred.

## 13. Phase 4.2 preview (for context only — separate spec)

Phase 4.2 will integrate filings (`data/filings/`, `research/`, `profiles/`) into the analytical layer via three new repositories (`FilingsRepository`, `ResearchRepository`, `ProfileRepository`) and extensions to `Dossier` and `Screener`. Phase 4.2 is independent of 4.1 — it neither blocks nor depends on the optimizer — and will be designed in its own spec after 4.1 ships.

## 14. File inventory (new + modified)

**New files:**
```
src/ah_research/portfolio/optimizer/__init__.py
src/ah_research/portfolio/optimizer/problem.py
src/ah_research/portfolio/optimizer/cvxpy_constraints.py
src/ah_research/portfolio/optimizer/errors.py
src/ah_research/portfolio/optimizer/result.py
src/ah_research/portfolio/optimizer/estimators/__init__.py
src/ah_research/portfolio/optimizer/estimators/covariance.py
src/ah_research/portfolio/optimizer/estimators/returns.py
src/ah_research/strategies/optimized.py
tests/unit/portfolio/optimizer/test_problem.py
tests/unit/portfolio/optimizer/test_cvxpy_constraints.py
tests/unit/portfolio/optimizer/test_result.py
tests/unit/portfolio/optimizer/test_errors.py
tests/unit/portfolio/optimizer/estimators/test_covariance.py
tests/unit/portfolio/optimizer/estimators/test_returns.py
tests/unit/strategies/test_optimized.py
tests/property/test_optimizer_invariants.py
tests/integration/test_optimizer_walkforward.py
tests/integration/test_optimizer_leakage.py
notebooks/phase4_1_optimizer_example.ipynb
```

**Modified files:**
```
src/ah_research/portfolio/constraints.py   # add 2 new Constraint.kind values + validation
pyproject.toml                              # add cvxpy, clarabel to dependencies
CHANGELOG.md                                # Phase 4.1 entry
README.md                                   # Phase 4.1 section under "Features"
docs/superpowers/specs/2026-04-28-ah-research-platform-design.md   # cross-link
```

## 15. Acceptance criteria

Phase 4.1 is done when:

1. All unit, property, golden, and integration tests pass.
2. Acceptance notebook runs headless in CI.
3. Leakage canary passes (optimizer never reads data at or after `as_of`).
4. Performance targets in §10 met or documented variances explained.
5. CHANGELOG.md and README.md updated.
6. Spec doc (this file) linked from `2026-04-28-ah-research-platform-design.md` Phase 4 section.
