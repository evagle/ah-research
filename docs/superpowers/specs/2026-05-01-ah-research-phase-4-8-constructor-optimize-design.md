# Phase 4.8 — Constructor `weight_by("optimize")`

**Date:** 2026-05-01
**Depends on:** Phase 4.1 (`Optimizer`, `OptimizationResult`) — merged. Phase 3 (`Constructor`, `ConstructionReport`) — merged.

## Mission

Make the Phase 4.1 convex optimizer reachable via the top-level `Constructor` fluent API, so the same pipeline that today picks `equal` / `signal_proportional` / `mcw` weights can now pick **optimizer-chosen** weights with one call.

Before:

```python
report = (
    Constructor(signals, repo=repo, asof=date(2024, 6, 30))
    .method("top_quantile", quantile=0.2)
    .weight_by("equal")
    .build()
)
```

After (new):

```python
optimizer = Optimizer(
    objective="mean_variance",
    cov_estimator=LedoitWolfCovariance(),
    returns_estimator=SignalBasedReturns(),
    constraints=[Constraint.max_turnover(0.3)],
)

report = (
    Constructor(signals, repo=repo, asof=date(2024, 6, 30), optimizer=optimizer)
    .method("top_quantile", quantile=0.2)
    .weight_by("optimize")
    .build()
)

result: OptimizationResult | None = report.optimization_result
```

## Scope

**In scope:**

- `Constructor.__init__` gains an `optimizer: Optimizer | None = None` kwarg.
- `weight_by` accepts a new literal `"optimize"`.
- `build()` dispatches to `self._optimizer.build(symbols=selected, as_of=pd.Timestamp(self._asof), repo=self._repo, prev_weights=None)` when scheme is `"optimize"`.
- `ConstructionReport` gains `optimization_result: OptimizationResult | None = None`.
- CLI: `ah construct <universe> --weight-by optimize [--objective mean_variance|risk_parity] [--max-turnover X]`.
- Unit tests + acceptance notebook + CHANGELOG/README.

**Out of scope:**

- No `prev_weights` plumbing through Constructor (rebalancing loops keep using `OptimizedWeightStrategy` from Phase 4.1 — Constructor is a single-asof builder, not a time-series driver).
- Constructor's own `.constrain()` queue is **ignored** when `weight_by("optimize")` — the optimizer's internal constraints are authoritative. Validated and raised as `ValueError` if user calls both.
- No change to `top_quantile_weights` or any Phase 2 path.

## API additions

```python
# src/ah_research/portfolio/constructor.py

class Constructor:
    def __init__(
        self,
        signals: Signals,
        *,
        repo: Any | None = None,
        asof: date | None = None,
        optimizer: "Optimizer | None" = None,   # NEW
    ) -> None: ...

    def weight_by(
        self,
        scheme: Literal[
            "equal", "signal_proportional", "free_float_mcw", "mcw",
            "optimize",                                             # NEW
        ],
    ) -> Constructor: ...
```

```python
@dataclass(frozen=True)
class ConstructionReport:
    weights: pd.DataFrame
    final_position_count: int
    constraint_results: list[ConstraintResult]
    method_used: str
    weighting_scheme: str
    relaxation_notes: list[str] = field(default_factory=list)
    optimization_result: "OptimizationResult | None" = None   # NEW
```

## Behavior contract

| Scheme         | Requires `optimizer` | Applies `.constrain()` queue | Sets `optimization_result` |
|----------------|:-------------------:|:---------------------------:|:--------------------------:|
| `equal`        | no                  | yes                         | None                       |
| `signal_proportional` | no           | yes                         | None                       |
| `mcw` / `free_float_mcw` | no        | yes                         | None                       |
| `optimize`     | **yes**             | **no** (error if nonempty)  | yes                        |

### Error cases

| Input | Behavior |
|---|---|
| `weight_by("optimize")` with `optimizer=None` | `ValueError("weight_by('optimize') requires Constructor(optimizer=...)")` |
| `weight_by("optimize")` + `repo=None` | `ValueError("weight_by('optimize') requires Constructor(repo=...)")` |
| `weight_by("optimize")` + `asof=None` | `ValueError("weight_by('optimize') requires Constructor(asof=...)")` |
| `weight_by("optimize")` + `.constrain(...)` calls | `ValueError("weight_by('optimize') is incompatible with .constrain(...); set constraints on Optimizer instead")` |
| `Optimizer.build` raises `InfeasibleError` | bubble up unchanged |
| Selection produces 0 symbols | `ValueError("nothing selected — cannot optimize empty universe")` (same as current empty-selection path) |

## CLI

`ah construct` does not yet exist in the repo — creating a full construct CLI is larger than this phase. Instead ship a minimal new script:

```
ah construct <universe-json> --asof YYYY-MM-DD --weight-by optimize \
    --objective mean_variance|risk_parity \
    [--risk-aversion 1.0] [--max-turnover 0.3] [--lookback-days 252]
```

`<universe-json>` is a path to a JSON file `{"symbol": signal, ...}` or a newline-separated symbol list; signal defaults to 1.0 when missing. Prints the weight table + a summary of the `OptimizationResult`. This is a thin demo surface, not the full analysis-side CLI (deferred).

## Tests

- `tests/unit/portfolio/test_constructor_optimize.py` (~8 tests):
  1. `weight_by("optimize")` without `optimizer` kwarg raises `ValueError`
  2. without `repo` or `asof` raises `ValueError`
  3. with `.constrain(...)` raises `ValueError`
  4. happy path: 5-symbol synthetic fixture, MV objective, weights sum to 1, all positive
  5. `optimization_result` is populated and has the expected `solver_status="optimal"`
  6. risk_parity path runs with no returns_estimator
  7. infeasible `max_weight` constraint on optimizer raises `InfeasibleError`
  8. empty selection raises `ValueError`
- `tests/unit/scripts/test_cli_construct_optimize.py` — Typer CliRunner smoke test for `--weight-by optimize`.
- `tests/integration/test_phase4_8_notebook_runs.py` — notebook headless.
- `notebooks/phase4_8_constructor_optimize_example.ipynb` — ~20 cells end-to-end.

## File inventory

**New:**
```
docs/superpowers/specs/2026-05-01-ah-research-phase-4-8-constructor-optimize-design.md
tests/unit/portfolio/test_constructor_optimize.py
tests/unit/scripts/test_cli_construct_optimize.py
tests/integration/test_phase4_8_notebook_runs.py
notebooks/phase4_8_constructor_optimize_example.ipynb
```

**Modified:**
```
src/ah_research/portfolio/constructor.py  # add optimizer kwarg, "optimize" scheme, optimization_result field
src/ah_research/portfolio/__init__.py     # re-export Optimizer from constructor namespace (convenience)
src/ah_research/scripts/ah_construct.py   # (if exists) add --weight-by optimize + --objective flags; otherwise add new CLI subcommand under existing registrar
CHANGELOG.md
README.md
```

## Acceptance

- Unit + CLI + notebook tests pass.
- `uv run pytest` + `uv run mypy src` green.
- Acceptance notebook demonstrates equal-weight vs. optimize side-by-side on the same selection.
