# Phase 4.8 — Constructor `weight_by("optimize")` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Phase 4.1 `Optimizer` into the Phase 3 `Constructor` fluent API via a new `weight_by("optimize")` scheme, with an `optimizer=` kwarg and an `optimization_result` field on `ConstructionReport`.

**Architecture:** Additive only. Existing four weighting schemes (`equal` / `signal_proportional` / `mcw` / `free_float_mcw`) untouched. New `"optimize"` scheme delegates to a user-supplied `Optimizer` instance and attaches the returned `OptimizationResult` to the report. Constructor's post-weighting `.constrain(...)` queue is rejected (as `ValueError`) in `optimize` mode — the optimizer is authoritative.

**Tech Stack:** pandas, numpy, CVXPY (via existing `Optimizer`), Typer (CLI), pytest, Jupyter.

**Reference spec:** `docs/superpowers/specs/2026-05-01-ah-research-phase-4-8-constructor-optimize-design.md`.

**CI-equivalent verification BEFORE every commit (MANDATORY — user explicitly said "you pushed a pr with ut failed"):**
```
uv run pytest -x
uv run mypy src
```

---

### Task 1: Extend `ConstructionReport` with `optimization_result` field

**Files:**
- Modify: `src/ah_research/portfolio/constructor.py` (around line 111–120)
- Test: `tests/unit/portfolio/test_construction_report_optimization_field.py` (new)

- [ ] **Step 1: Write failing test for new field**

```python
# tests/unit/portfolio/test_construction_report_optimization_field.py
from __future__ import annotations

import pandas as pd

from ah_research.portfolio.constructor import ConstructionReport


def test_construction_report_has_optimization_result_field_defaulting_to_none() -> None:
    report = ConstructionReport(
        weights=pd.DataFrame({"symbol": ["600519.SH"], "weight": [1.0]}),
        final_position_count=1,
        constraint_results=[],
        method_used="top_quantile",
        weighting_scheme="equal",
    )
    assert report.optimization_result is None
```

- [ ] **Step 2: Run test — expect AttributeError**

```
uv run pytest tests/unit/portfolio/test_construction_report_optimization_field.py -x
```

Expected: `AttributeError: 'ConstructionReport' object has no attribute 'optimization_result'`

- [ ] **Step 3: Add field**

In `src/ah_research/portfolio/constructor.py`, find the `ConstructionReport` dataclass (around line 111) and add the field as the final field:

```python
# ... existing imports ...
from typing import Any, Literal, TYPE_CHECKING
if TYPE_CHECKING:
    from ah_research.portfolio.optimizer.result import OptimizationResult


@dataclass(frozen=True)
class ConstructionReport:
    """Full output from ``Constructor.build()``."""

    weights: pd.DataFrame  # columns: [symbol, weight]
    final_position_count: int
    constraint_results: list[ConstraintResult]
    method_used: str
    weighting_scheme: str
    relaxation_notes: list[str] = field(default_factory=list)
    optimization_result: "OptimizationResult | None" = None
```

- [ ] **Step 4: Run test — expect PASS**

```
uv run pytest tests/unit/portfolio/test_construction_report_optimization_field.py -x
```

- [ ] **Step 5: Verify mypy**

```
uv run mypy src
```

- [ ] **Step 6: Commit**

```
git add src/ah_research/portfolio/constructor.py tests/unit/portfolio/test_construction_report_optimization_field.py
git commit -m "feat(phase-4.8): add optimization_result field to ConstructionReport"
```

---

### Task 2: Add `optimizer` kwarg to `Constructor.__init__`

**Files:**
- Modify: `src/ah_research/portfolio/constructor.py` (around line 142)
- Test: `tests/unit/portfolio/test_constructor_optimize.py` (new; will grow in Tasks 3–5)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/portfolio/test_constructor_optimize.py
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from ah_research.backtest.types import Signals
from ah_research.portfolio.constructor import Constructor


def _synthetic_signals() -> Signals:
    df = pd.DataFrame(
        {
            "asof": [date(2024, 6, 30)] * 5,
            "symbol": ["600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"],
            "signal": [1.0, 0.5, 0.2, 0.9, 0.1],
        }
    )
    return Signals(df=df, asof=date(2024, 6, 30))


def test_constructor_accepts_optimizer_kwarg() -> None:
    c = Constructor(_synthetic_signals(), optimizer=None)
    # No exception means kwarg is accepted.
    assert c is not None
```

- [ ] **Step 2: Run — expect TypeError (unexpected keyword)**

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py::test_constructor_accepts_optimizer_kwarg -x
```

Expected: `TypeError: __init__() got an unexpected keyword argument 'optimizer'`

- [ ] **Step 3: Add kwarg**

In `Constructor.__init__` (around line 142):

```python
def __init__(
    self,
    signals: Signals,
    *,
    repo: Any | None = None,
    asof: date | None = None,
    optimizer: "Optimizer | None" = None,
) -> None:
    self._signals = signals
    self._repo = repo
    self._asof = asof
    self._optimizer = optimizer
    self._method: str = "top_quantile"
    self._method_kwargs: dict[str, Any] = {"quantile": 0.2}
    self._weighting: str = "equal"
    self._constraints: list[Constraint] = []
```

Add the import under `TYPE_CHECKING`:

```python
if TYPE_CHECKING:
    from ah_research.portfolio.optimizer import Optimizer
    from ah_research.portfolio.optimizer.result import OptimizationResult
```

- [ ] **Step 4: Run — expect PASS**

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py -x
uv run mypy src
```

- [ ] **Step 5: Commit**

```
git add src/ah_research/portfolio/constructor.py tests/unit/portfolio/test_constructor_optimize.py
git commit -m "feat(phase-4.8): add optimizer kwarg to Constructor.__init__"
```

---

### Task 3: Accept `"optimize"` in `weight_by` literal

**Files:**
- Modify: `src/ah_research/portfolio/constructor.py` `weight_by` method
- Test: `tests/unit/portfolio/test_constructor_optimize.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/portfolio/test_constructor_optimize.py`:

```python
def test_weight_by_optimize_is_accepted_literal() -> None:
    c = Constructor(_synthetic_signals())
    returned = c.weight_by("optimize")
    assert returned is c
    assert c._weighting == "optimize"  # type: ignore[attr-defined]
```

- [ ] **Step 2: Run — expect pass (Literal is runtime-unchecked) or typing error**

The test will PASS at runtime because Python does not enforce Literal at runtime. The CHANGE is to the type annotation so mypy flags misuse. Run mypy to confirm current state rejects the literal:

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py::test_weight_by_optimize_is_accepted_literal -x
```

Expected: PASS at runtime. Then:

```
uv run mypy src/ah_research/portfolio/constructor.py
```

Expected: PASS (no change yet).

- [ ] **Step 3: Add `"optimize"` to Literal**

In `weight_by` method signature (around line 169):

```python
def weight_by(
    self,
    scheme: Literal[
        "equal",
        "signal_proportional",
        "free_float_mcw",
        "mcw",
        "optimize",
    ],
) -> Constructor:
    """Set the weighting scheme."""
    self._weighting = scheme
    return self
```

- [ ] **Step 4: Run**

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py -x
uv run mypy src
```

- [ ] **Step 5: Commit**

```
git add src/ah_research/portfolio/constructor.py tests/unit/portfolio/test_constructor_optimize.py
git commit -m "feat(phase-4.8): accept weight_by('optimize') literal"
```

---

### Task 4: Implement validation errors for `optimize` mode

**Files:**
- Modify: `src/ah_research/portfolio/constructor.py` `build` method
- Test: `tests/unit/portfolio/test_constructor_optimize.py`

Target behavior: when `_weighting == "optimize"`, `build()` must validate:
1. `_optimizer is not None` — else `ValueError("weight_by('optimize') requires Constructor(optimizer=...)")`
2. `_repo is not None` — else `ValueError("weight_by('optimize') requires Constructor(repo=...)")`
3. `_asof is not None` — else `ValueError("weight_by('optimize') requires Constructor(asof=...)")`
4. `not _constraints` — else `ValueError("weight_by('optimize') is incompatible with .constrain(...); set constraints on Optimizer instead")`

- [ ] **Step 1: Write 4 failing tests**

```python
def test_optimize_without_optimizer_raises() -> None:
    c = Constructor(_synthetic_signals()).weight_by("optimize")
    with pytest.raises(ValueError, match=r"requires Constructor\(optimizer="):
        c.build()


def test_optimize_without_repo_raises() -> None:
    # Make a fake optimizer
    fake_opt = object()
    c = Constructor(
        _synthetic_signals(),
        asof=date(2024, 6, 30),
        optimizer=fake_opt,  # type: ignore[arg-type]
    ).weight_by("optimize")
    with pytest.raises(ValueError, match=r"requires Constructor\(repo="):
        c.build()


def test_optimize_without_asof_raises() -> None:
    fake_opt = object()
    fake_repo = object()
    c = Constructor(
        _synthetic_signals(),
        repo=fake_repo,
        optimizer=fake_opt,  # type: ignore[arg-type]
    ).weight_by("optimize")
    with pytest.raises(ValueError, match=r"requires Constructor\(asof="):
        c.build()


def test_optimize_with_constrain_queue_raises() -> None:
    from ah_research.portfolio.constructor import Constraint

    fake_opt = object()
    fake_repo = object()
    c = (
        Constructor(
            _synthetic_signals(),
            repo=fake_repo,
            asof=date(2024, 6, 30),
            optimizer=fake_opt,  # type: ignore[arg-type]
        )
        .weight_by("optimize")
        .constrain(Constraint.max_weight(0.3))
    )
    with pytest.raises(ValueError, match=r"incompatible with \.constrain"):
        c.build()
```

- [ ] **Step 2: Run — expect 4 FAILs**

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py -x
```

- [ ] **Step 3: Add validation to `build`**

In `build` method, add at the very top (before any other work):

```python
def build(self) -> ConstructionReport:
    """Execute the full construction pipeline and return a report."""
    # Optimize-mode preconditions
    if self._weighting == "optimize":
        if self._optimizer is None:
            raise ValueError(
                "weight_by('optimize') requires Constructor(optimizer=...)"
            )
        if self._repo is None:
            raise ValueError("weight_by('optimize') requires Constructor(repo=...)")
        if self._asof is None:
            raise ValueError("weight_by('optimize') requires Constructor(asof=...)")
        if self._constraints:
            raise ValueError(
                "weight_by('optimize') is incompatible with .constrain(...); "
                "set constraints on Optimizer instead"
            )

    sig_df = self._signals.df.copy()
    # ... rest unchanged for now ...
```

- [ ] **Step 4: Run — expect 4 PASSes**

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py -x
uv run mypy src
```

- [ ] **Step 5: Commit**

```
git add src/ah_research/portfolio/constructor.py tests/unit/portfolio/test_constructor_optimize.py
git commit -m "feat(phase-4.8): validate optimize-mode preconditions in build()"
```

---

### Task 5: Dispatch to `Optimizer.build` in `optimize` mode — happy path

**Files:**
- Modify: `src/ah_research/portfolio/constructor.py` `build` method
- Test: `tests/unit/portfolio/test_constructor_optimize.py`

- [ ] **Step 1: Write failing happy-path test**

```python
def test_optimize_mode_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end MV optimization through Constructor."""
    from ah_research.portfolio.optimizer import Optimizer
    from ah_research.portfolio.optimizer.estimators import (
        LedoitWolfCovariance,
        UserSuppliedReturns,
    )

    # Build a tiny fake repo that returns synthetic returns & mu
    symbols = ["600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"]
    n_days = 300
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")

    import numpy as np

    rng = np.random.default_rng(42)
    ret_matrix = rng.normal(0.0005, 0.015, size=(n_days, len(symbols)))

    rows = []
    for i, d in enumerate(dates):
        for j, s in enumerate(symbols):
            rows.append({"ds": d, "symbol": s, "total_return": ret_matrix[i, j]})
    prices_df = pd.DataFrame(rows)

    class FakeRepo:
        def get_prices(
            self,
            symbols: list[str],
            start,  # type: ignore[no-untyped-def]
            end,  # type: ignore[no-untyped-def]
        ) -> pd.DataFrame:
            return prices_df[
                (prices_df["ds"] >= pd.Timestamp(start))
                & (prices_df["ds"] <= pd.Timestamp(end))
            ].copy()

    mu = pd.Series([0.01, 0.008, 0.006, 0.012, 0.005], index=symbols)
    optimizer = Optimizer(
        objective="mean_variance",
        cov_estimator=LedoitWolfCovariance(),
        returns_estimator=UserSuppliedReturns(mu),
        risk_aversion=1.0,
    )

    signals_df = pd.DataFrame(
        {
            "asof": [date(2024, 6, 30)] * 5,
            "symbol": symbols,
            "signal": [1.0, 0.5, 0.2, 0.9, 0.1],
        }
    )
    signals = Signals(df=signals_df, asof=date(2024, 6, 30))

    report = (
        Constructor(signals, repo=FakeRepo(), asof=date(2024, 6, 30), optimizer=optimizer)
        .method("all_positive")
        .weight_by("optimize")
        .build()
    )

    # Contract checks
    assert report.weighting_scheme == "optimize"
    assert report.final_position_count > 0
    assert abs(report.weights["weight"].sum() - 1.0) < 1e-4
    assert (report.weights["weight"] >= -1e-8).all()
    assert report.optimization_result is not None
    assert report.optimization_result.solver_status in ("optimal", "optimal_inaccurate")
```

- [ ] **Step 2: Run — expect failure (build still does equal-weight path for `optimize`)**

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py::test_optimize_mode_happy_path -x
```

- [ ] **Step 3: Wire dispatch**

In `build`, after the precondition block and the selection step (`selected = self._apply_method(sig_df)`), branch on `_weighting`:

```python
        # 2. Weighting
        if self._weighting == "optimize":
            assert self._optimizer is not None
            assert self._repo is not None
            assert self._asof is not None

            symbols_selected = selected["symbol"].tolist()
            if not symbols_selected:
                raise ValueError(
                    "nothing selected — cannot optimize empty universe"
                )

            opt_result = self._optimizer.build(
                symbols=symbols_selected,
                as_of=pd.Timestamp(self._asof),
                repo=self._repo,
                prev_weights=None,
            )
            weights_series = opt_result.weights.copy()
        else:
            weights_series = self._apply_weighting(selected)
            opt_result = None
```

Then in the final return, include `optimization_result=opt_result` and skip the `sorted_constraints` loop entirely when `_weighting == "optimize"`:

```python
        # 3. Constraints — skipped entirely in optimize mode
        constraint_results: list[ConstraintResult] = []
        relaxation_notes: list[str] = []

        if self._weighting != "optimize":
            sorted_constraints = sorted(self._constraints, key=lambda c: c.priority)
            for c in sorted_constraints:
                weights_series, result, notes = self._apply_constraint(
                    c, weights_series, selected
                )
                constraint_results.append(result)
                relaxation_notes.extend(notes)

            # Normalise to sum=1 after all constraints (not needed in optimize mode)
            total = weights_series.sum()
            if total > 0:
                weights_series = weights_series / total

        weights_df = pd.DataFrame(
            {"symbol": weights_series.index, "weight": weights_series.values}
        )

        return ConstructionReport(
            weights=weights_df,
            final_position_count=int((weights_series > 0).sum()),
            constraint_results=constraint_results,
            method_used=self._method,
            weighting_scheme=self._weighting,
            relaxation_notes=relaxation_notes,
            optimization_result=opt_result,
        )
```

- [ ] **Step 4: Run — expect PASS**

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py -x
uv run mypy src
```

- [ ] **Step 5: Commit**

```
git add src/ah_research/portfolio/constructor.py tests/unit/portfolio/test_constructor_optimize.py
git commit -m "feat(phase-4.8): dispatch to Optimizer.build when weight_by('optimize')"
```

---

### Task 6: Empty-selection guard test + risk_parity happy path

**Files:**
- Modify: `tests/unit/portfolio/test_constructor_optimize.py`

- [ ] **Step 1: Add empty-selection test**

```python
def test_optimize_empty_selection_raises() -> None:
    from ah_research.portfolio.optimizer import Optimizer
    from ah_research.portfolio.optimizer.estimators import LedoitWolfCovariance

    class EmptyRepo:
        def get_prices(self, *a, **kw):  # type: ignore[no-untyped-def]
            return pd.DataFrame(columns=["ds", "symbol", "total_return"])

    signals_df = pd.DataFrame(
        {
            "asof": [date(2024, 6, 30)] * 2,
            "symbol": ["600000.SH", "600001.SH"],
            "signal": [-1.0, -2.0],  # all negative → all_positive selects nothing
        }
    )
    signals = Signals(df=signals_df, asof=date(2024, 6, 30))
    opt = Optimizer(
        objective="risk_parity",
        cov_estimator=LedoitWolfCovariance(),
    )
    c = (
        Constructor(signals, repo=EmptyRepo(), asof=date(2024, 6, 30), optimizer=opt)
        .method("all_positive")
        .weight_by("optimize")
    )
    with pytest.raises(ValueError, match=r"nothing selected"):
        c.build()
```

- [ ] **Step 2: Add risk_parity happy-path test**

```python
def test_optimize_risk_parity_runs() -> None:
    from ah_research.portfolio.optimizer import Optimizer
    from ah_research.portfolio.optimizer.estimators import LedoitWolfCovariance

    import numpy as np

    symbols = ["600000.SH", "600001.SH", "600002.SH"]
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    rng = np.random.default_rng(7)
    ret_matrix = rng.normal(0.0005, 0.015, size=(len(dates), len(symbols)))
    rows = []
    for i, d in enumerate(dates):
        for j, s in enumerate(symbols):
            rows.append({"ds": d, "symbol": s, "total_return": ret_matrix[i, j]})
    prices_df = pd.DataFrame(rows)

    class FakeRepo:
        def get_prices(self, symbols, start, end):  # type: ignore[no-untyped-def]
            return prices_df[
                (prices_df["ds"] >= pd.Timestamp(start))
                & (prices_df["ds"] <= pd.Timestamp(end))
            ].copy()

    signals_df = pd.DataFrame(
        {
            "asof": [date(2024, 6, 30)] * 3,
            "symbol": symbols,
            "signal": [1.0, 0.5, 0.3],
        }
    )
    signals = Signals(df=signals_df, asof=date(2024, 6, 30))
    opt = Optimizer(objective="risk_parity", cov_estimator=LedoitWolfCovariance())

    report = (
        Constructor(signals, repo=FakeRepo(), asof=date(2024, 6, 30), optimizer=opt)
        .method("all_positive")
        .weight_by("optimize")
        .build()
    )
    assert abs(report.weights["weight"].sum() - 1.0) < 1e-4
    assert report.optimization_result is not None
```

- [ ] **Step 3: Run — expect both PASS**

```
uv run pytest tests/unit/portfolio/test_constructor_optimize.py -x
uv run mypy src
```

- [ ] **Step 4: Commit**

```
git add tests/unit/portfolio/test_constructor_optimize.py
git commit -m "test(phase-4.8): empty-selection + risk_parity coverage"
```

---

### Task 7: Minimal CLI `ah construct`

**Files:**
- Create: `src/ah_research/scripts/ah_construct.py`
- Modify: `src/ah_research/cli.py`
- Create: `tests/unit/scripts/test_cli_construct.py`

- [ ] **Step 1: Write failing CLI smoke test**

```python
# tests/unit/scripts/test_cli_construct.py
from __future__ import annotations

from typer.testing import CliRunner

from ah_research.cli import app


def test_ah_construct_help_works() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["construct", "--help"])
    assert result.exit_code == 0
    assert "weight-by" in result.stdout or "weight_by" in result.stdout
```

- [ ] **Step 2: Run — expect FAIL (no `construct` subcommand)**

```
uv run pytest tests/unit/scripts/test_cli_construct.py -x
```

- [ ] **Step 3: Write the CLI script**

```python
# src/ah_research/scripts/ah_construct.py
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from ah_research.backtest.types import Signals
from ah_research.data import DataRepository
from ah_research.portfolio.constructor import Constructor
from ah_research.portfolio.optimizer import Optimizer
from ah_research.portfolio.optimizer.estimators import (
    LedoitWolfCovariance,
    SignalBasedReturns,
)

app = typer.Typer(help="Portfolio construction CLI.")
console = Console()


def _parse_universe(path: Path) -> dict[str, float]:
    text = path.read_text()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
        if isinstance(data, list):
            return {str(s): 1.0 for s in data}
    except json.JSONDecodeError:
        pass
    return {line.strip(): 1.0 for line in text.splitlines() if line.strip()}


@app.callback(invoke_without_command=True)
def construct(
    universe: Annotated[Path, typer.Argument(help="Path to universe JSON or newline list.")],
    asof: Annotated[str, typer.Option("--asof", help="YYYY-MM-DD")],
    weight_by: Annotated[str, typer.Option("--weight-by", help="Weighting scheme.")] = "equal",
    objective: Annotated[
        str, typer.Option("--objective", help="mean_variance or risk_parity")
    ] = "mean_variance",
    risk_aversion: Annotated[float, typer.Option("--risk-aversion")] = 1.0,
    max_turnover: Annotated[float | None, typer.Option("--max-turnover")] = None,
    lookback_days: Annotated[int, typer.Option("--lookback-days")] = 252,
) -> None:
    """Build a portfolio for <universe> at --asof using the given weighting."""
    symbols_signals = _parse_universe(universe)
    asof_date = datetime.strptime(asof, "%Y-%m-%d").date()

    sig_df = pd.DataFrame(
        {
            "asof": [asof_date] * len(symbols_signals),
            "symbol": list(symbols_signals.keys()),
            "signal": list(symbols_signals.values()),
        }
    )
    signals = Signals(df=sig_df, asof=asof_date)
    repo = DataRepository()

    optimizer: Optimizer | None = None
    if weight_by == "optimize":
        from ah_research.portfolio.constructor import Constraint as _C

        cons: list = []
        if max_turnover is not None:
            cons.append(_C.max_turnover(max_turnover))
        if objective == "mean_variance":
            optimizer = Optimizer(
                objective="mean_variance",
                cov_estimator=LedoitWolfCovariance(),
                returns_estimator=SignalBasedReturns(),
                constraints=cons,
                risk_aversion=risk_aversion,
                lookback_days=lookback_days,
            )
        elif objective == "risk_parity":
            optimizer = Optimizer(
                objective="risk_parity",
                cov_estimator=LedoitWolfCovariance(),
                constraints=cons,
                lookback_days=lookback_days,
            )
        else:
            raise typer.BadParameter(f"unknown objective: {objective}")

    builder = Constructor(signals, repo=repo, asof=asof_date, optimizer=optimizer)
    builder = builder.method("all_positive")
    builder = builder.weight_by(weight_by)  # type: ignore[arg-type]
    report = builder.build()

    tbl = Table(title=f"{weight_by} weights @ {asof}")
    tbl.add_column("symbol")
    tbl.add_column("weight", justify="right")
    for _, row in report.weights.iterrows():
        tbl.add_row(str(row["symbol"]), f"{float(row['weight']):.4f}")
    console.print(tbl)

    if report.optimization_result is not None:
        console.print(f"[bold]solver:[/bold] {report.optimization_result.solver_status}")
```

- [ ] **Step 4: Register in `cli.py`**

Find the registration block (around line 54–62 in `cli.py`) and add:

```python
from ah_research.scripts.ah_construct import app as construct_app
# ... existing ...
app.add_typer(construct_app, name="construct")
```

- [ ] **Step 5: Run — expect PASS**

```
uv run pytest tests/unit/scripts/test_cli_construct.py -x
uv run mypy src
```

- [ ] **Step 6: Commit**

```
git add src/ah_research/scripts/ah_construct.py src/ah_research/cli.py tests/unit/scripts/test_cli_construct.py
git commit -m "feat(phase-4.8): ah construct CLI subcommand"
```

---

### Task 8: Acceptance notebook + headless integration test

**Files:**
- Create: `notebooks/phase4_8_constructor_optimize_example.ipynb`
- Create: `tests/integration/test_phase4_8_notebook_runs.py`

- [ ] **Step 1: Create the notebook**

~15–20 cells. Follow the pattern of `notebooks/phase4_4_screener_enrichment_example.ipynb` / `notebooks/phase4_6_corpus_summary_example.ipynb`:

1. Imports (`Constructor`, `Optimizer`, estimators, `Signals`, `DataRepository`)
2. Markdown: "Phase 4.8 — Constructor optimize mode"
3. Build or load a 5–8 symbol universe (use whatever exists in the default DuckDB cache; skip with a friendly message if empty)
4. Show `weight_by("equal")` result
5. Show `weight_by("optimize")` result (MV)
6. Side-by-side comparison: DataFrame of equal vs. optimize
7. Print `report.optimization_result.to_markdown()`
8. Demonstrate the infeasible path (very tight `max_weight`)

Use `pd.DataFrame.style` for comparison display. Keep cell outputs present — ExecutePreprocessor will re-execute.

- [ ] **Step 2: Create headless test**

```python
# tests/integration/test_phase4_8_notebook_runs.py
from __future__ import annotations

import pytest
from pathlib import Path
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError
import nbformat

NOTEBOOK = Path(__file__).parents[2] / "notebooks" / "phase4_8_constructor_optimize_example.ipynb"


def test_phase4_8_notebook_runs_headless() -> None:
    if not NOTEBOOK.exists():
        pytest.skip("notebook not present")
    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(nb, timeout=300)
    try:
        client.execute()
    except CellExecutionError as e:
        pytest.fail(f"notebook execution failed: {e}")
```

- [ ] **Step 3: Run notebook manually first, save with outputs**

```
uv run jupyter nbconvert --to notebook --execute \
    notebooks/phase4_8_constructor_optimize_example.ipynb \
    --output notebooks/phase4_8_constructor_optimize_example.ipynb
```

- [ ] **Step 4: Run headless test**

```
uv run pytest tests/integration/test_phase4_8_notebook_runs.py -x
```

- [ ] **Step 5: Commit**

```
git add notebooks/phase4_8_constructor_optimize_example.ipynb tests/integration/test_phase4_8_notebook_runs.py
git commit -m "feat(phase-4.8): acceptance notebook + headless test"
```

---

### Task 9: CHANGELOG + README

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Add Phase 4.8 CHANGELOG entry** at the top, before the Phase 4.7 entry:

```markdown
## Phase 4.8 — Constructor Optimize Mode (2026-05-01)

### Added
- `Constructor.weight_by("optimize")` — delegates portfolio weighting to Phase 4.1 `Optimizer` when an `optimizer=` is supplied to `Constructor(...)`.
- `ConstructionReport.optimization_result` — the full `OptimizationResult` attached when optimize mode is used.
- `ah construct <universe> --weight-by optimize --objective [mean_variance|risk_parity] [--max-turnover]` CLI subcommand.

### Design doc
- `docs/superpowers/specs/2026-05-01-ah-research-phase-4-8-constructor-optimize-design.md`
```

- [ ] **Step 2: Add README bullet** to the Features section:

```markdown
- **Constructor optimize mode** — `Constructor(optimizer=...).weight_by("optimize")` runs the Phase 4.1 convex optimizer inline; `ConstructionReport.optimization_result` carries the full result (dual prices, active constraints, solver status).
```

- [ ] **Step 3: Full CI-equivalent sweep**

```
uv run pytest
uv run mypy src
```

- [ ] **Step 4: Commit**

```
git add CHANGELOG.md README.md
git commit -m "docs(phase-4.8): CHANGELOG + README"
```

---

### Task 10: Finalize

- [ ] Push branch: `git push -u origin feat/phase-4.8`
- [ ] Verify no stray files: `git status`
- [ ] Full sweep one more time: `uv run pytest && uv run mypy src`
- [ ] Open PR with gh: title `feat(phase-4.8): Constructor optimize mode`, body summarizing spec
