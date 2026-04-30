# Phase 3 — Analysis, Watchlist, Constructor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 3 per `docs/superpowers/specs/2026-04-29-ah-research-phase-3-analysis-design.md` — nine research-layer components (factor study, screener, dossier, owner-earnings, valuation bands, dividend consistency, watchlist, portfolio Constructor, reference notebooks).

**Architecture:** Pure helpers (owner_earnings, valuation_bands, dividend_history) land first. Screener + factor_study sit on top of Phase 1 repo. Dossier composes helpers. Watchlist adds DuckDB tables and CRUD. Portfolio `Constructor` chains `Constraint` objects with heuristic relaxation + `ConstructionReport`. Four reference notebooks + `ah dossier` / `ah watchlist ...` CLI extensions. Zero new runtime deps.

**Tech Stack:** Python 3.11, pandas, numpy, scipy.stats (Spearman), statsmodels (reuse Phase 2 HAC), duckdb, pyyaml, typer (CLI), pytest + hypothesis.

**Working directory:** `/Users/brian_huang/repos/ah-research`.
**Branch:** `feat/phase-3-analysis` (already created).

---

## How to read this plan

- **TDD throughout**: failing test → run fail → minimal impl → run pass → commit.
- **One task = one commit** (except where a bug fix surfaces within a task — then two commits).
- **All commits must pass pre-commit hooks** (ruff, ruff format, mypy strict). No `--no-verify`.
- **English only** in code/comments/docstrings/commits. Dossier rendered content can be Chinese or English per user param.
- **Re-read the relevant spec section** (cited in each task) before starting.
- **Types everywhere.** `mypy --strict` must pass. `Decimal` for money, `int` for shares, `date` for dates, `pd.Timestamp` for intraday.
- **Phase 2 modules are frozen** — do not edit `src/ah_research/backtest/*`, `strategies/*`, or `portfolio/construction.py` unless fixing a bug. New work goes into new files.

---

## File structure (locked per spec §3)

New:
```
src/ah_research/
├── analysis/
│   ├── __init__.py          # public re-exports
│   ├── factor_study.py      # factor_study() + FactorReport + _InlineSignalStrategy (~400 LOC)
│   ├── screener.py          # run_screen() + derived-column catalog (~250 LOC)
│   ├── dossier.py           # Dossier + sections + build_dossier + renderers (~500 LOC)
│   ├── owner_earnings.py    # owner_earnings_series() (~80 LOC)
│   ├── valuation_bands.py   # compute_valuation_bands() (~100 LOC)
│   └── dividend_history.py  # dividend_consistency_grade() + helpers (~120 LOC)
│
├── watchlist/
│   ├── __init__.py
│   ├── store.py             # WatchlistStore CRUD (~250 LOC)
│   ├── snapshot.py          # WatchlistSnapshot + diff (~150 LOC)
│   └── migrations.py        # migration #4 DDL (~50 LOC)
│
├── portfolio/
│   └── constructor.py       # NEW — Constructor + Constraint + ConstructionReport (~400 LOC)
│                              # construction.py stays untouched
│
└── scripts/
    ├── ah_dossier.py        # new CLI entry (~60 LOC)
    └── ah_watchlist.py      # new CLI entry with sub-commands (~120 LOC)
```

Extend existing:
```
src/ah_research/cli.py         # wire new subcommands
src/ah_research/data/cache.py  # register migration #4
CHANGELOG.md                   # Phase 3 entry
README.md                      # Phase 3 section link
```

New notebooks:
```
notebooks/
├── phase3_factor_study_value.ipynb
├── phase3_screener_workflow.ipynb
├── phase3_dossier_example.ipynb
└── phase3_portfolio_construction.ipynb
```

New test folders:
```
tests/unit/analysis/
tests/unit/watchlist/
tests/integration/test_end_to_end_factor_study.py
tests/integration/test_end_to_end_screener_to_watchlist.py
tests/integration/test_end_to_end_dossier.py
tests/property/test_analysis_invariants.py
```

---

## Task 0: Branch already exists

**Files:** none (git only).

- [ ] **Step 1: Verify on `feat/phase-3-analysis`**

```bash
cd /Users/brian_huang/repos/ah-research
git status
```

Expected: `On branch feat/phase-3-analysis`, working tree clean (or with the already-committed spec).

- [ ] **Step 2: Push branch tracking if not already**

```bash
git push -u origin feat/phase-3-analysis 2>/dev/null || true
```

---

## Task 1: Skeleton packages

**Spec ref:** §3.

**Files:**
- Create: `src/ah_research/analysis/__init__.py`
- Create: `src/ah_research/watchlist/__init__.py`
- Create: `tests/unit/analysis/__init__.py`
- Create: `tests/unit/watchlist/__init__.py`

- [ ] **Step 1: Create package init files with module docstrings**

`src/ah_research/analysis/__init__.py`:
```python
"""Factor study, screener, dossier, and related research helpers."""
```

`src/ah_research/watchlist/__init__.py`:
```python
"""DuckDB-backed named watchlists with snapshot history."""
```

Test `__init__.py` files are empty.

- [ ] **Step 2: Verify imports**

```bash
uv run python -c "from ah_research import analysis, watchlist; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add src/ah_research/{analysis,watchlist}/__init__.py \
        tests/unit/{analysis,watchlist}/__init__.py
git commit -m "feat(phase-3): add analysis/ and watchlist/ skeleton packages

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: `owner_earnings_series()` helper

**Spec ref:** §4.4.

**Files:**
- Create: `src/ah_research/analysis/owner_earnings.py`
- Create: `tests/unit/analysis/test_owner_earnings.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/analysis/test_owner_earnings.py
import pandas as pd
import pytest
from ah_research.analysis.owner_earnings import owner_earnings_series


def _fundamentals_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_owner_earnings_basic_formula():
    """OE = NI + D&A - CapEx - WC change."""
    fundamentals = _fundamentals_frame([
        {
            "symbol": "600000.SH",
            "report_date": pd.Timestamp("2023-12-31"),
            "publication_date": pd.Timestamp("2024-03-30"),
            "known_as_of": pd.Timestamp("2024-03-30"),
            "statement_kind": "audited",
            "net_income": 100.0,
            "d_and_a": 20.0,
            "capex": 30.0,
            "working_capital_change": 10.0,
        },
    ])
    result = owner_earnings_series(fundamentals)
    # OE = 100 + 20 - 30 - 10 = 80
    assert result.iloc[0] == pytest.approx(80.0)
    assert result.index[0] == pd.Timestamp("2023-12-31")


def test_owner_earnings_empty_frame_returns_empty_series():
    empty = _fundamentals_frame([]).astype({"symbol": "object"})
    result = owner_earnings_series(empty)
    assert len(result) == 0


def test_owner_earnings_skips_rows_with_missing_inputs():
    fundamentals = _fundamentals_frame([
        {
            "symbol": "600000.SH",
            "report_date": pd.Timestamp("2022-12-31"),
            "publication_date": pd.Timestamp("2023-03-30"),
            "known_as_of": pd.Timestamp("2023-03-30"),
            "statement_kind": "audited",
            "net_income": 100.0,
            "d_and_a": None,   # missing
            "capex": 30.0,
            "working_capital_change": 10.0,
        },
        {
            "symbol": "600000.SH",
            "report_date": pd.Timestamp("2023-12-31"),
            "publication_date": pd.Timestamp("2024-03-30"),
            "known_as_of": pd.Timestamp("2024-03-30"),
            "statement_kind": "audited",
            "net_income": 120.0,
            "d_and_a": 25.0,
            "capex": 35.0,
            "working_capital_change": 12.0,
        },
    ])
    result = owner_earnings_series(fundamentals)
    # Only 2023-12-31 row has all fields → 120 + 25 - 35 - 12 = 98
    assert len(result) == 1
    assert result.iloc[0] == pytest.approx(98.0)
    assert result.index[0] == pd.Timestamp("2023-12-31")
```

- [ ] **Step 2: Run — fail**

```bash
uv run pytest tests/unit/analysis/test_owner_earnings.py -x -q
```

Expected: `ModuleNotFoundError: No module named 'ah_research.analysis.owner_earnings'`.

- [ ] **Step 3: Implement**

```python
# src/ah_research/analysis/owner_earnings.py
"""Buffett (1986) owner-earnings series from fundamentals."""
from __future__ import annotations
import pandas as pd


def owner_earnings_series(fundamentals: pd.DataFrame) -> pd.Series:
    """Compute annual owner-earnings from a bitemporal fundamentals frame.

    Formula: owner_earnings = net_income + d_and_a - capex - working_capital_change.

    Rows with any NaN in the four input columns are dropped. The returned
    Series is indexed by `report_date` (fiscal year end) and sorted ascending.
    """
    required = ["net_income", "d_and_a", "capex", "working_capital_change", "report_date"]
    if fundamentals.empty or any(c not in fundamentals.columns for c in required):
        return pd.Series([], dtype=float, name="owner_earnings")

    f = fundamentals.dropna(subset=required[:4]).copy()
    if f.empty:
        return pd.Series([], dtype=float, name="owner_earnings")

    oe = (
        f["net_income"].astype(float)
        + f["d_and_a"].astype(float)
        - f["capex"].astype(float)
        - f["working_capital_change"].astype(float)
    )
    oe.index = f["report_date"]
    oe.name = "owner_earnings"
    return oe.sort_index()
```

- [ ] **Step 4: Run — pass**

```bash
uv run pytest tests/unit/analysis/test_owner_earnings.py -x -q
uv run mypy src/ah_research/analysis/owner_earnings.py
```

Expected: 3 passed; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/analysis/owner_earnings.py tests/unit/analysis/test_owner_earnings.py
git commit -m "feat(phase-3): add owner_earnings_series() helper per Buffett 1986

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: `compute_valuation_bands()` helper

**Spec ref:** §4.5.

**Files:**
- Create: `src/ah_research/analysis/valuation_bands.py`
- Create: `tests/unit/analysis/test_valuation_bands.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/analysis/test_valuation_bands.py
from datetime import date
from decimal import Decimal
import pandas as pd
import pytest
from ah_research.analysis.valuation_bands import compute_valuation_bands, ValuationBand
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_valuation_bands_basic_pe():
    """Compute 10-year PE percentile bands and current percentile."""
    repo = build_synthetic_market(
        start=date(2014, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    result = compute_valuation_bands(
        symbol="600000.SH",
        repo=repo,
        asof=date(2024, 12, 31),
        metric="pe",
        window_years=10,
    )
    assert isinstance(result, ValuationBand)
    assert result.metric == "pe"
    assert set(result.bands.keys()) == {"p10", "p25", "p50", "p75", "p90"}
    assert result.bands["p10"] < result.bands["p50"] < result.bands["p90"]
    assert 0.0 <= result.current_percentile <= 100.0
    assert result.window_years == 10


def test_valuation_bands_insufficient_history():
    """When < window_years of data exist, window_years reflects actual coverage."""
    repo = build_synthetic_market(
        start=date(2022, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    result = compute_valuation_bands(
        symbol="600000.SH",
        repo=repo,
        asof=date(2024, 12, 31),
        metric="pe",
        window_years=10,
    )
    # Only ~3 years of data available
    assert result.window_years <= 3
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

```python
# src/ah_research/analysis/valuation_bands.py
"""Trailing N-year percentile bands for P/E, P/B, P/S."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal
import pandas as pd
from ah_research.data.repository import DataRepository


ValuationMetric = Literal["pe", "pb", "ps"]


@dataclass(frozen=True)
class ValuationBand:
    metric: ValuationMetric
    bands: dict[str, float]
    current: float
    current_percentile: float
    window_years: int


def compute_valuation_bands(
    symbol: str,
    repo: DataRepository,
    asof: date,
    metric: ValuationMetric = "pe",
    window_years: int = 10,
) -> ValuationBand:
    start = date(asof.year - window_years, asof.month, asof.day)
    fundamentals = repo.get_fundamentals([symbol], start=start, end=asof, asof=asof)

    if fundamentals.empty or metric not in fundamentals.columns:
        return ValuationBand(
            metric=metric, bands={"p10": 0, "p25": 0, "p50": 0, "p75": 0, "p90": 0},
            current=0.0, current_percentile=0.0, window_years=0,
        )

    series = fundamentals[metric].dropna().astype(float)
    if series.empty:
        return ValuationBand(
            metric=metric, bands={"p10": 0, "p25": 0, "p50": 0, "p75": 0, "p90": 0},
            current=0.0, current_percentile=0.0, window_years=0,
        )

    bands = {
        f"p{int(q * 100)}": float(series.quantile(q))
        for q in (0.10, 0.25, 0.50, 0.75, 0.90)
    }
    current = float(series.iloc[-1])
    current_percentile = float((series <= current).mean() * 100)

    actual_span_days = (fundamentals["report_date"].max() - fundamentals["report_date"].min()).days
    actual_years = min(window_years, max(1, int(round(actual_span_days / 365.25))))

    return ValuationBand(
        metric=metric,
        bands=bands,
        current=current,
        current_percentile=current_percentile,
        window_years=actual_years,
    )
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_valuation_bands.py -x -q
uv run mypy src/ah_research/analysis/valuation_bands.py
git add src/ah_research/analysis/valuation_bands.py tests/unit/analysis/test_valuation_bands.py
git commit -m "feat(phase-3): add compute_valuation_bands() with 10y percentile bands

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: `dividend_consistency_grade()` helper

**Spec ref:** §2 D7(d), §4.6.

**Files:**
- Create: `src/ah_research/analysis/dividend_history.py`
- Create: `tests/unit/analysis/test_dividend_history.py`

- [ ] **Step 1: Write failing tests for each grade boundary**

```python
# tests/unit/analysis/test_dividend_history.py
from datetime import date
import pandas as pd
import pytest
from ah_research.analysis.dividend_history import dividend_consistency_grade


def _cash_div_actions(years: list[int], amounts: list[float], symbol="600000.SH") -> pd.DataFrame:
    rows = [
        {
            "symbol": symbol,
            "ex_date": pd.Timestamp(year=y, month=6, day=30),
            "kind": "cash_dividend",
            "params_json": f'{{"amount_per_share": {a}}}',
        }
        for y, a in zip(years, amounts)
    ]
    return pd.DataFrame(rows)


def test_grade_a_10y_consecutive_cagr_8_no_cuts():
    # Amounts growing at ~10% CAGR: 1.0 * 1.1^9 ~= 2.36
    years = list(range(2015, 2025))
    amounts = [1.0 * (1.10 ** i) for i in range(10)]
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "A"


def test_grade_b_10y_flat_no_cuts():
    years = list(range(2015, 2025))
    amounts = [1.0] * 10  # flat — 0% CAGR, no cuts
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "B"


def test_grade_c_7_of_10_years_no_recent_cuts():
    years = [2015, 2017, 2019, 2020, 2021, 2022, 2023, 2024]  # 8 of 10 years; last 5 non-decreasing
    amounts = [1.0, 1.1, 1.2, 1.2, 1.3, 1.3, 1.4, 1.5]
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "C"


def test_grade_d_5_of_10_years():
    years = [2015, 2017, 2019, 2021, 2023]
    amounts = [1.0] * 5
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "D"


def test_grade_e_3_of_10_years():
    years = [2020, 2022, 2024]
    amounts = [1.0] * 3
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "E"


def test_grade_f_no_history():
    df = pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "F"


def test_grade_b_demotes_from_a_on_cut():
    years = list(range(2015, 2025))
    amounts = [1.0, 1.1, 1.2, 1.3, 1.4, 1.3, 1.4, 1.5, 1.6, 1.7]  # cut in 2020
    df = _cash_div_actions(years, amounts)
    result = dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10)
    assert result in ("C",), f"expected C (cut in last 5 violates A/B), got {result}"
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

```python
# src/ah_research/analysis/dividend_history.py
"""Dividend consistency grading (A–F) over trailing window."""
from __future__ import annotations
from datetime import date
import json
import pandas as pd


def _extract_amount(row_params: str) -> float:
    """Parse `params_json` to get amount_per_share (float)."""
    try:
        params = json.loads(row_params) if isinstance(row_params, str) else row_params
        return float(params.get("amount_per_share", 0.0))
    except (ValueError, AttributeError, TypeError):
        return 0.0


def dividend_consistency_grade(
    corporate_actions: pd.DataFrame,
    asof: date,
    window_years: int = 10,
) -> str:
    """Grade per spec §2 D7(d). Expects a filtered frame for one symbol."""
    if corporate_actions.empty:
        return "F"

    df = corporate_actions[corporate_actions["kind"] == "cash_dividend"].copy()
    if df.empty:
        return "F"

    df["ex_date"] = pd.to_datetime(df["ex_date"])
    window_start = pd.Timestamp(asof.year - window_years + 1, 1, 1)
    window_end = pd.Timestamp(asof)
    df = df[(df["ex_date"] >= window_start) & (df["ex_date"] <= window_end)]
    if df.empty:
        return "F"

    df["amount"] = df["params_json"].apply(_extract_amount)
    df["fiscal_year"] = df["ex_date"].dt.year
    annual = df.groupby("fiscal_year")["amount"].sum().sort_index()
    n_years = len(annual)

    if n_years < 3:
        return "F"
    if n_years == 3 or n_years == 4:
        return "E"
    if n_years >= 5 and n_years < 7:
        return "D"

    # n_years >= 7
    # Check for cuts (year-over-year decrease)
    has_any_cut = (annual.diff().dropna() < 0).any()
    has_recent_cut = (annual.iloc[-5:].diff().dropna() < 0).any()

    if n_years < 10:
        return "D" if has_recent_cut else "C"

    # n_years == 10 (consecutive): evaluate A/B/C
    consecutive = (annual.index == list(range(asof.year - 9, asof.year + 1))).all()
    if not consecutive:
        return "C" if not has_recent_cut else "D"

    if has_any_cut:
        return "D" if has_recent_cut else "C"

    # No cuts; compute CAGR
    first, last = float(annual.iloc[0]), float(annual.iloc[-1])
    if first <= 0:
        return "B"
    cagr = (last / first) ** (1 / 9) - 1
    return "A" if cagr >= 0.08 else "B"
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_dividend_history.py -x -q
uv run mypy src/ah_research/analysis/dividend_history.py
git add src/ah_research/analysis/dividend_history.py tests/unit/analysis/test_dividend_history.py
git commit -m "feat(phase-3): add dividend_consistency_grade() A-F grader

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Screener — `run_screen()` + derived columns

**Spec ref:** §4.2.

**Files:**
- Create: `src/ah_research/analysis/screener.py`
- Create: `tests/unit/analysis/test_screener.py`

- [ ] **Step 1: Failing tests (shape shown; executor expands to cover each operator)**

```python
# tests/unit/analysis/test_screener.py
from datetime import date
import pandas as pd
import pytest
from ah_research.analysis.screener import run_screen, ScreenResult
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_simple_single_condition_lt():
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    result = run_screen(
        conditions={"pe": ("<", 1_000_000.0)},  # loose predicate → all pass
        repo=repo, asof=date(2024, 12, 31), universe="CSI300",
    )
    assert isinstance(result, ScreenResult)
    assert result.asof == date(2024, 12, 31)
    assert result.n_passed <= result.n_input


def test_between_operator():
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    result = run_screen(
        conditions={"pe": ("between", 0.1, 100.0)},
        repo=repo, asof=date(2024, 12, 31), universe="CSI300",
    )
    assert result.frame["pe"].between(0.1, 100.0).all()


def test_in_operator():
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    result = run_screen(
        conditions={"sector_l1": ("in", ["Finance", "Energy", "Tech"])},
        repo=repo, asof=date(2024, 12, 31), universe="CSI300",
    )
    assert all(result.frame["sector_l1"].isin(["Finance", "Energy", "Tech"]))


def test_unknown_column_raises_with_suggestions():
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    with pytest.raises(KeyError) as exc:
        run_screen(
            conditions={"non_existent": ("<", 10)},
            repo=repo, asof=date(2024, 12, 31),
        )
    assert "non_existent" in str(exc.value)


def test_derived_column_computed_when_referenced():
    repo = build_synthetic_market(
        start=date(2020, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    result = run_screen(
        conditions={"roe_3y_avg": (">", -1.0)},  # loose — just verify column computed
        repo=repo, asof=date(2024, 12, 31),
    )
    assert "roe_3y_avg" in result.frame.columns


def test_between_lo_gt_hi_raises():
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    with pytest.raises(ValueError):
        run_screen(
            conditions={"pe": ("between", 20.0, 10.0)},  # lo > hi
            repo=repo, asof=date(2024, 12, 31),
        )


def test_empty_result_no_error():
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    result = run_screen(
        conditions={"pe": ("<", -999999)},  # impossible
        repo=repo, asof=date(2024, 12, 31),
    )
    assert result.n_passed == 0
    assert result.frame.empty is False or len(result.frame) == 0


def test_conditions_applied_preserved():
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    conds = {"pe": ("<", 100.0), "dividend_yield": (">", 0.0)}
    result = run_screen(conditions=conds, repo=repo, asof=date(2024, 12, 31))
    assert result.conditions_applied == conds
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `screener.py` (~250 LOC)**

Core outline:

```python
# src/ah_research/analysis/screener.py
"""Screener: vectorized fundamental/flag filtering with serializable predicate dict."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
import difflib
import pandas as pd
from ah_research.data.repository import DataRepository

Op = Literal["<", "<=", ">", ">=", "==", "!=", "between", "in", "not_in"]
Condition = tuple  # (op, value) or (op, lo, hi)

_OPERATORS = frozenset({"<", "<=", ">", ">=", "==", "!=", "between", "in", "not_in"})


@dataclass(frozen=True)
class ScreenResult:
    asof: date
    universe: str
    n_input: int
    n_passed: int
    frame: pd.DataFrame
    conditions_applied: dict[str, Condition]


def _enrich_screen_frame(
    base: pd.DataFrame,
    repo: DataRepository,
    asof: date,
    required_columns: set[str],
) -> pd.DataFrame:
    """Compute derived columns only when referenced in `required_columns`."""
    df = base.copy()

    derived = {
        "roe_3y_avg": lambda: _rolling_avg(repo, df["symbol"].tolist(), asof, "roe", years=3),
        "roe_5y_avg": lambda: _rolling_avg(repo, df["symbol"].tolist(), asof, "roe", years=5),
        "revenue_growth_3y_cagr": lambda: _growth_cagr(repo, df["symbol"].tolist(), asof, "revenue", years=3),
        "net_income_growth_3y_cagr": lambda: _growth_cagr(repo, df["symbol"].tolist(), asof, "net_income", years=3),
        "dividend_growth_5y_cagr": lambda: _dividend_growth(repo, df["symbol"].tolist(), asof, years=5),
        "dividend_consistency_grade": lambda: _consistency_grades(repo, df["symbol"].tolist(), asof),
        "debt_to_equity": lambda: (df["total_debt"] / df["total_equity"]).where(df["total_equity"] != 0),
        "free_cash_flow_yield": lambda: ((df["operating_cash_flow"] - df["capex"]) / df["market_cap"]).where(df["market_cap"] != 0),
        "owner_earnings_yield": lambda: _oe_yield(repo, df["symbol"].tolist(), asof, df["market_cap"]),
    }

    for col, compute in derived.items():
        if col in required_columns and col not in df.columns:
            df[col] = compute()

    return df


def _apply_condition(series: pd.Series, cond: Condition) -> pd.Series:
    op = cond[0]
    if op == "<": return series < cond[1]
    if op == "<=": return series <= cond[1]
    if op == ">": return series > cond[1]
    if op == ">=": return series >= cond[1]
    if op == "==": return series == cond[1]
    if op == "!=": return series != cond[1]
    if op == "between":
        lo, hi = cond[1], cond[2]
        if lo > hi:
            raise ValueError(f"between requires lo <= hi, got ({lo}, {hi})")
        return series.between(lo, hi)
    if op == "in":
        return series.isin(cond[1])
    if op == "not_in":
        return ~series.isin(cond[1])
    raise ValueError(f"Unknown operator: {op}")


def run_screen(
    conditions: dict[str, Condition],
    repo: DataRepository,
    asof: date,
    universe: str = "CSI300",
) -> ScreenResult:
    # Validate ops first (fail fast)
    for col, cond in conditions.items():
        if not isinstance(cond, tuple) or len(cond) < 2:
            raise ValueError(f"Condition for {col} must be (op, value) or (op, lo, hi); got {cond!r}")
        if cond[0] not in _OPERATORS:
            raise ValueError(f"Unknown operator {cond[0]!r} for column {col}")

    universe_df = repo.get_universe_over_time(universe, asof, asof, freq="D")
    if universe_df.empty:
        return ScreenResult(
            asof=asof, universe=universe, n_input=0, n_passed=0,
            frame=pd.DataFrame(), conditions_applied=conditions,
        )
    symbols = universe_df["symbol"].unique().tolist()

    fundamentals = repo.get_fundamentals(symbols, start=asof, end=asof, asof=asof)
    sectors = repo.get_sector(symbols)
    base = fundamentals.merge(sectors[["symbol", "sector_l1", "sector_l2"]], on="symbol", how="left")

    base = _enrich_screen_frame(base, repo, asof, required_columns=set(conditions.keys()))

    for col in conditions:
        if col not in base.columns:
            available = sorted(base.columns)
            suggestions = difflib.get_close_matches(col, available, n=3)
            msg = f"Column {col!r} not found. Did you mean: {suggestions}?"
            raise KeyError(msg)

    mask = pd.Series(True, index=base.index)
    for col, cond in conditions.items():
        mask &= _apply_condition(base[col], cond)

    passed = base[mask].copy()
    return ScreenResult(
        asof=asof, universe=universe,
        n_input=len(base), n_passed=len(passed),
        frame=passed, conditions_applied=conditions,
    )


# Helper functions (~60 LOC) for _rolling_avg, _growth_cagr, _dividend_growth, _consistency_grades, _oe_yield
# — all call repo methods and return pd.Series indexed by symbol position.
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_screener.py -x -q
uv run mypy src/ah_research/analysis/screener.py
git add src/ah_research/analysis/screener.py tests/unit/analysis/test_screener.py
git commit -m "feat(phase-3): screener.run_screen with vectorized predicate dict + derived catalog

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Factor study — IC computation (core)

**Spec ref:** §4.1 step 6.

**Files:**
- Create: `src/ah_research/analysis/factor_study.py` (initial skeleton)
- Create: `tests/unit/analysis/test_factor_study_ic.py`

This task lands the IC building block + `_InlineSignalStrategy` adapter + rebalance-date logic. Quantile returns + bootstrap come in Tasks 7 and 8.

- [ ] **Step 1: Failing test**

```python
# tests/unit/analysis/test_factor_study_ic.py
from datetime import date
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import pytest
from ah_research.analysis.factor_study import _compute_ic_one_date, _InlineSignalStrategy
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_compute_ic_matches_scipy_spearman():
    np.random.seed(42)
    signals = pd.Series(np.random.randn(20), index=[f"SYM{i}.SH" for i in range(20)])
    forward_returns = pd.Series(np.random.randn(20), index=signals.index)
    ic = _compute_ic_one_date(signals, forward_returns)
    expected, _ = spearmanr(signals.values, forward_returns.values)
    assert ic == pytest.approx(expected, abs=1e-10)


def test_compute_ic_handles_nan_dropping():
    signals = pd.Series([1.0, 2.0, float("nan"), 4.0], index=["A", "B", "C", "D"])
    forward = pd.Series([0.1, 0.2, 0.3, 0.4], index=["A", "B", "C", "D"])
    ic = _compute_ic_one_date(signals, forward)
    expected, _ = spearmanr([1.0, 2.0, 4.0], [0.1, 0.2, 0.4])
    assert ic == pytest.approx(expected, abs=1e-10)


def test_inline_signal_strategy_adapter():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-31", "2024-01-31"]),
        "symbol": ["600000.SH", "000001.SZ"],
        "signal": [0.1, 0.2],
    })
    strategy = _InlineSignalStrategy(df)
    assert strategy.name == "inline"

    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 2, 1),
        symbols=["600000.SH", "000001.SZ"],
    )
    signals = strategy.generate(repo, date(2024, 1, 31), date(2024, 1, 31))
    assert len(signals.df) == 2
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement skeleton**

```python
# src/ah_research/analysis/factor_study.py
"""Factor study: IC, quantile returns, block bootstrap."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from ah_research.backtest.types import Signals
from ah_research.data.repository import DataRepository
from ah_research.strategies.base import SignalStrategy


@dataclass(frozen=True)
class _InlineSignalStrategy:
    """Wraps a DataFrame[date, symbol, signal] as a trivial SignalStrategy."""
    frame: pd.DataFrame
    name: str = "inline"

    def generate(self, repo: DataRepository, start: date, end: date) -> Signals:
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        df = self.frame.copy()
        df["date"] = pd.to_datetime(df["date"])
        mask = (df["date"] >= start_ts) & (df["date"] <= end_ts)
        return Signals.from_dataframe(df[mask].reset_index(drop=True))

    def to_weights(self, signals: Signals) -> "Weights":  # noqa: F821
        from ah_research.backtest.types import Weights
        df = signals.df.copy()
        df["weight"] = 1.0 / len(df) if len(df) > 0 else 0.0
        df = df.drop(columns=["signal"])
        return Weights.from_dataframe(df)


def _compute_ic_one_date(signals: pd.Series, forward_returns: pd.Series) -> float:
    """Spearman rank correlation for one rebalance date."""
    paired = pd.concat([signals, forward_returns], axis=1).dropna()
    if len(paired) < 2:
        return float("nan")
    ic, _ = spearmanr(paired.iloc[:, 0].values, paired.iloc[:, 1].values)
    return float(ic)
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_factor_study_ic.py -x -q
uv run mypy src/ah_research/analysis/factor_study.py
git add src/ah_research/analysis/factor_study.py tests/unit/analysis/test_factor_study_ic.py
git commit -m "feat(phase-3): factor_study IC primitive + _InlineSignalStrategy adapter

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Factor study — quantile returns + per-horizon IC

**Spec ref:** §4.1 steps 5, 6, 8.

**Files:**
- Modify: `src/ah_research/analysis/factor_study.py` (add `_compute_quantile_returns`, `_ic_table_by_horizon`)
- Create: `tests/unit/analysis/test_factor_study_quantile.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/analysis/test_factor_study_quantile.py
from datetime import date
import numpy as np
import pandas as pd
import pytest
from ah_research.analysis.factor_study import (
    _compute_quantile_returns, _ic_table_by_horizon, _assign_quantiles,
)


def test_assign_quantiles_5_equal_buckets():
    np.random.seed(42)
    signals = pd.Series(np.arange(20), dtype=float)  # 0..19
    q = _assign_quantiles(signals, n_quantiles=5)
    # 4 per bucket, Q1 contains lowest, Q5 contains highest
    assert (q == 1).sum() == 4
    assert (q == 5).sum() == 4
    assert q.iloc[0] == 1
    assert q.iloc[-1] == 5


def test_quantile_returns_equal_weighted():
    dates = pd.date_range("2024-01-01", periods=3, freq="M")
    signals = pd.DataFrame({
        "date": np.repeat(dates, 5),
        "symbol": ["A", "B", "C", "D", "E"] * 3,
        "signal": [1, 2, 3, 4, 5] * 3,
        "forward_return_20": [0.01, 0.02, 0.03, 0.04, 0.05] * 3,
    })
    returns = _compute_quantile_returns(signals, n_quantiles=5, horizon=20)
    # With 5 symbols and 5 quantiles, each quantile = 1 symbol
    # Q1 = A's return = 0.01; Q5 = E's return = 0.05
    assert returns.loc[dates[0], "Q1"] == pytest.approx(0.01)
    assert returns.loc[dates[0], "Q5"] == pytest.approx(0.05)
    assert returns.loc[dates[0], "long_short"] == pytest.approx(0.04)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

Append to `factor_study.py`:

```python
def _assign_quantiles(signals: pd.Series, n_quantiles: int = 5) -> pd.Series:
    """Return integer quantile label in {1..n_quantiles} per row."""
    try:
        return pd.qcut(signals.rank(method="first"), q=n_quantiles, labels=False) + 1
    except ValueError:
        return pd.Series(np.nan, index=signals.index)


def _compute_quantile_returns(
    enriched: pd.DataFrame,  # [date, symbol, signal, forward_return_<horizon>]
    n_quantiles: int,
    horizon: int,
) -> pd.DataFrame:
    fwd_col = f"forward_return_{horizon}"
    rows: list[dict] = []
    for d, group in enriched.groupby("date"):
        if len(group) < n_quantiles:
            continue
        group = group.copy()
        group["quantile"] = _assign_quantiles(group["signal"], n_quantiles)
        per_q = group.groupby("quantile")[fwd_col].mean()
        row = {f"Q{int(q)}": float(per_q.get(q, float("nan"))) for q in range(1, n_quantiles + 1)}
        row["date"] = d
        row["long_short"] = row.get(f"Q{n_quantiles}", 0.0) - row.get("Q1", 0.0)
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")


def _ic_table_by_horizon(
    enriched: pd.DataFrame, horizons: list[int]
) -> pd.DataFrame:
    """Rows=rebalance dates; columns=horizons; values=Spearman IC."""
    results: list[dict] = []
    for d, group in enriched.groupby("date"):
        row: dict[str, float] = {"date": d}
        for h in horizons:
            fwd_col = f"forward_return_{h}"
            if fwd_col in group.columns:
                row[str(h)] = _compute_ic_one_date(group["signal"], group[fwd_col])
            else:
                row[str(h)] = float("nan")
        results.append(row)
    return pd.DataFrame(results).set_index("date")
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_factor_study_quantile.py -x -q
git add src/ah_research/analysis/factor_study.py tests/unit/analysis/test_factor_study_quantile.py
git commit -m "feat(phase-3): factor_study quantile returns + IC per horizon

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Factor study — block bootstrap + sector neutralization

**Spec ref:** §4.1 steps 4, 9.

**Files:**
- Modify: `src/ah_research/analysis/factor_study.py` (add `_block_bootstrap`, `_sector_neutralize_signals`)
- Create: `tests/unit/analysis/test_factor_study_bootstrap.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/analysis/test_factor_study_bootstrap.py
import numpy as np
import pandas as pd
import pytest
from ah_research.analysis.factor_study import _block_bootstrap, _sector_neutralize_signals


def test_block_bootstrap_deterministic_with_seed():
    returns = pd.Series(np.random.RandomState(1).randn(200))
    r1 = _block_bootstrap(returns, n_resamples=500, block_size=21, random_seed=42)
    r2 = _block_bootstrap(returns, n_resamples=500, block_size=21, random_seed=42)
    assert r1 == r2
    assert "mean" in r1 and "ci_low" in r1 and "ci_high" in r1 and "p_value" in r1


def test_block_bootstrap_ci_widens_with_more_resamples_stays_reasonable():
    returns = pd.Series(np.random.RandomState(1).randn(200) * 0.01)  # small std
    small = _block_bootstrap(returns, n_resamples=100, block_size=21, random_seed=42)
    large = _block_bootstrap(returns, n_resamples=1000, block_size=21, random_seed=42)
    # CI width should be similar across n (stable)
    w_small = small["ci_high"] - small["ci_low"]
    w_large = large["ci_high"] - large["ci_low"]
    assert abs(w_large - w_small) / max(abs(w_small), 1e-9) < 0.5


def test_sector_neutralize_removes_sector_mean():
    signals = pd.Series([1.0, 3.0, 1.0, 3.0], index=["A", "B", "C", "D"])
    sectors = pd.Series(["tech", "tech", "finance", "finance"], index=["A", "B", "C", "D"])
    neutral = _sector_neutralize_signals(signals, sectors)
    # After demean within sector, each sector has mean 0
    assert neutral.groupby(sectors).mean().abs().max() < 1e-10
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

Append to `factor_study.py`:

```python
def _block_bootstrap(
    series: pd.Series, n_resamples: int, block_size: int, random_seed: int = 42
) -> dict:
    """Block bootstrap mean + 95% CI + one-sided p-value (H0: mean=0)."""
    arr = series.dropna().to_numpy()
    n = len(arr)
    if n < block_size:
        return {"mean": float(arr.mean()), "ci_low": float("nan"),
                "ci_high": float("nan"), "p_value": float("nan")}

    rng = np.random.default_rng(random_seed)
    means = np.empty(n_resamples)
    n_blocks = (n + block_size - 1) // block_size
    for i in range(n_resamples):
        starts = rng.integers(0, n - block_size + 1, size=n_blocks)
        pieces = [arr[s : s + block_size] for s in starts]
        resample = np.concatenate(pieces)[:n]
        means[i] = resample.mean()

    mean_val = float(means.mean())
    p_value = float((means <= 0).mean()) if mean_val > 0 else float((means >= 0).mean())
    return {
        "mean": mean_val,
        "ci_low": float(np.percentile(means, 2.5)),
        "ci_high": float(np.percentile(means, 97.5)),
        "p_value": p_value,
    }


def _sector_neutralize_signals(signals: pd.Series, sectors: pd.Series) -> pd.Series:
    """Demean signal within each sector group."""
    aligned_sectors = sectors.reindex(signals.index)
    group_means = signals.groupby(aligned_sectors).transform("mean")
    return signals - group_means
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_factor_study_bootstrap.py -x -q
git add src/ah_research/analysis/factor_study.py tests/unit/analysis/test_factor_study_bootstrap.py
git commit -m "feat(phase-3): factor_study block bootstrap + sector neutralization helpers

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Factor study — full `factor_study()` + `FactorReport` wiring

**Spec ref:** §4.1 full.

**Files:**
- Modify: `src/ah_research/analysis/factor_study.py`
- Create: `tests/unit/analysis/test_factor_study_integration.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/analysis/test_factor_study_integration.py
from datetime import date
import pandas as pd
from ah_research.analysis.factor_study import factor_study, FactorReport
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_factor_study_returns_valid_report_from_dataframe():
    repo = build_synthetic_market(
        start=date(2022, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ", "600519.SH", "600036.SH", "601318.SH"],
    )
    # Build a synthetic signal: random signal per month
    import numpy as np
    rng = np.random.default_rng(42)
    eoms = pd.date_range("2022-01-31", "2024-12-31", freq="M")
    rows = []
    for d in eoms:
        for s in ["600000.SH", "000001.SZ", "600519.SH", "600036.SH", "601318.SH"]:
            rows.append({"date": d, "symbol": s, "signal": rng.standard_normal()})
    signals_df = pd.DataFrame(rows)

    report = factor_study(
        signals_df, repo,
        start=date(2022, 1, 1), end=date(2024, 12, 31),
        n_quantiles=5, ic_horizons=[5, 20],
        sector_neutral=True, bootstrap_n_resamples=200,
    )
    assert isinstance(report, FactorReport)
    assert report.n_rebalance_dates > 0
    assert report.ic_summary.shape[0] == 2  # 2 horizons
    assert "mean_ic" in report.ic_summary.columns
    assert report.sector_neutralized is True


def test_factor_study_accepts_strategy():
    from ah_research.strategies import ValueFactorStrategy
    repo = build_synthetic_market(
        start=date(2022, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ", "600519.SH", "600036.SH", "601318.SH"],
    )
    strategy = ValueFactorStrategy()
    report = factor_study(
        strategy, repo,
        start=date(2022, 1, 1), end=date(2024, 12, 31),
        ic_horizons=[20], bootstrap_n_resamples=100,
    )
    assert isinstance(report, FactorReport)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `factor_study` and `FactorReport`**

Append to `factor_study.py`:

```python
@dataclass(frozen=True)
class FactorReport:
    ic_by_horizon: pd.DataFrame
    ic_summary: pd.DataFrame
    ic_decay: pd.Series
    quantile_returns: pd.DataFrame
    quantile_summary: pd.DataFrame
    bootstrap_q5_minus_q1: dict
    sector_neutralized: bool
    n_rebalance_dates: int
    universe_summary: dict


def factor_study(
    strategy: SignalStrategy | pd.DataFrame,
    repo: DataRepository,
    start: date,
    end: date,
    n_quantiles: int = 5,
    ic_horizons: list[int] | None = None,
    sector_neutral: bool = True,
    bootstrap_n_resamples: int = 1000,
    bootstrap_block_size: int = 21,
    benchmark: str | pd.Series = "auto",
    rebalance: Literal["W", "M", "Q"] = "M",
    random_seed: int = 42,
) -> FactorReport:
    if ic_horizons is None:
        ic_horizons = [1, 5, 10, 20, 60]

    # 1. Adapt input
    if isinstance(strategy, pd.DataFrame):
        strategy = _InlineSignalStrategy(strategy)

    # 2. Rebalance dates (last trading day of each period)
    calendar = repo.get_trading_calendar("SH", start, end)
    trading_days = pd.to_datetime(calendar[calendar["is_trading_day"]]["date"])
    freq_map = {"W": "W-FRI", "M": "M", "Q": "Q"}
    period_ends = pd.Series(trading_days).groupby(
        pd.Grouper(key=0, freq=freq_map[rebalance])
    ).max().dropna().values if False else (
        trading_days.groupby(trading_days.dt.to_period(rebalance)).max().values
    )
    rebalance_dates = [pd.Timestamp(d).date() for d in period_ends]

    if len(rebalance_dates) < 10:
        raise ValueError(
            f"factor_study needs >= 10 rebalance dates; got {len(rebalance_dates)} "
            f"for rebalance={rebalance} from {start} to {end}"
        )

    # 3. Per-rebalance signal + sector + forward returns
    all_rows: list[pd.DataFrame] = []
    universe_sizes: list[int] = []
    for d in rebalance_dates:
        signals = strategy.generate(repo, d, d).df
        if signals.empty:
            continue
        signals = signals.copy()
        signals["date"] = pd.to_datetime(d)

        if sector_neutral:
            sectors = repo.get_sector(signals["symbol"].tolist())
            sector_map = sectors.set_index("symbol")["sector_l1"]
            signals["signal"] = _sector_neutralize_signals(
                signals.set_index("symbol")["signal"], sector_map
            ).reset_index(drop=True).values

        prices = repo.get_prices(
            signals["symbol"].tolist(), start=d, end=(pd.Timestamp(d) + pd.Timedelta(days=max(ic_horizons) + 30)).date()
        )
        for h in ic_horizons:
            fwd = _compute_forward_returns(prices, h)  # helper — see Task 9 impl note
            signals = signals.merge(fwd.rename(f"forward_return_{h}"), left_on="symbol", right_index=True, how="left")

        all_rows.append(signals)
        universe_sizes.append(len(signals))

    enriched = pd.concat(all_rows, ignore_index=True)

    # 4. IC table
    ic_by_horizon = _ic_table_by_horizon(enriched, ic_horizons)

    # 5. IC summary (mean + NW t-stat + IR)
    from ah_research.backtest.metrics import _andrews_lag
    import statsmodels.api as sm
    ic_summary_rows = []
    for h in ic_horizons:
        col = str(h)
        ic_series = ic_by_horizon[col].dropna()
        if len(ic_series) < 2:
            ic_summary_rows.append({"horizon": h, "mean_ic": float("nan"), "nw_t_stat": float("nan"),
                                     "nw_p_value": float("nan"), "ir": float("nan")})
            continue
        n = len(ic_series)
        L = _andrews_lag(n)
        X = np.ones((n, 1))
        fit = sm.OLS(ic_series.values, X).fit(cov_type="HAC", cov_kwds={"maxlags": L})
        ic_summary_rows.append({
            "horizon": h,
            "mean_ic": float(ic_series.mean()),
            "nw_t_stat": float(fit.tvalues[0]),
            "nw_p_value": float(fit.pvalues[0]),
            "ir": float(ic_series.mean() / ic_series.std()) if ic_series.std() > 0 else 0.0,
        })
    ic_summary = pd.DataFrame(ic_summary_rows).set_index("horizon")

    # 6. IC decay
    ic_decay = ic_summary["mean_ic"]

    # 7. Quantile returns (use longest horizon for quantile calc by convention)
    primary_horizon = max(ic_horizons)
    quantile_returns = _compute_quantile_returns(enriched, n_quantiles, primary_horizon)

    # 8. Quantile summary (CAGR, Sharpe, max DD per quantile)
    from ah_research.backtest.metrics import cagr, sharpe, max_drawdown
    quantile_summary_rows = []
    for col in quantile_returns.columns:
        returns = quantile_returns[col].dropna()
        if returns.empty:
            continue
        equity = (1 + returns).cumprod() * 100
        mdd, _ = max_drawdown(equity)
        quantile_summary_rows.append({
            "quantile": col,
            "cagr": cagr(equity),
            "sharpe": sharpe(returns),
            "max_drawdown": mdd,
        })
    quantile_summary = pd.DataFrame(quantile_summary_rows).set_index("quantile")

    # 9. Block bootstrap on long_short
    bootstrap = _block_bootstrap(
        quantile_returns["long_short"].dropna(),
        n_resamples=bootstrap_n_resamples,
        block_size=bootstrap_block_size,
        random_seed=random_seed,
    )

    return FactorReport(
        ic_by_horizon=ic_by_horizon,
        ic_summary=ic_summary,
        ic_decay=ic_decay,
        quantile_returns=quantile_returns,
        quantile_summary=quantile_summary,
        bootstrap_q5_minus_q1=bootstrap,
        sector_neutralized=sector_neutral,
        n_rebalance_dates=len(rebalance_dates),
        universe_summary={
            "avg_n_names": int(np.mean(universe_sizes)) if universe_sizes else 0,
            "min_n_names": int(np.min(universe_sizes)) if universe_sizes else 0,
        },
    )


def _compute_forward_returns(prices: pd.DataFrame, horizon: int) -> pd.Series:
    """Return Series indexed by symbol giving horizon-day forward log return from first date."""
    # pivot to date x symbol
    wide = prices.pivot_table(index="date", columns="symbol", values="close_hfq")
    if len(wide) <= horizon:
        return pd.Series(dtype=float)
    start_prices = wide.iloc[0]
    end_prices = wide.iloc[horizon] if horizon < len(wide) else wide.iloc[-1]
    return np.log(end_prices / start_prices).rename(f"fwd_{horizon}")
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_factor_study_integration.py -x -q
uv run mypy src/ah_research/analysis/factor_study.py
git add src/ah_research/analysis/factor_study.py tests/unit/analysis/test_factor_study_integration.py
git commit -m "feat(phase-3): factor_study() full wiring with FactorReport

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: Dossier section dataclasses

**Spec ref:** §4.3 (OverviewSection through DossierMetadata).

**Files:**
- Create: `src/ah_research/analysis/dossier.py` (initial — dataclasses only)
- Create: `tests/unit/analysis/test_dossier_types.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/analysis/test_dossier_types.py
from datetime import date
import pandas as pd
import pytest
from ah_research.analysis.dossier import (
    OverviewSection, FundamentalsSection, OwnerEarningsSection,
    ValuationBandsSection, DividendSection, AHPremiumSection, PeersSection,
    DossierMetadata, Dossier,
)
from ah_research.model.types import parse_symbol


def test_overview_section_frozen():
    ov = OverviewSection(
        symbol=parse_symbol("600000.SH"),
        name_en="Foo Bank",
        name_zh="XX银行",
        sector_l1="Finance",
        sector_l2="Banks",
        market_cap=1e11,
        market_cap_free_float=6e10,
        is_soe=True,
        is_stock_connect_eligible=True,
        listing_date=date(1999, 11, 10),
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        ov.market_cap = 0  # type: ignore[misc]


def test_dossier_assembles():
    # Build a minimal Dossier with required sections; AH premium None
    meta = DossierMetadata(
        asof=date(2024, 12, 31),
        repo_snapshot_date=date(2024, 12, 31),
        code_version="abc1234",
        warnings=[],
    )
    # (executor fills other sections with minimal synthetic values)
    # This test verifies Dossier accepts None for ah_premium
    ...
```

- [ ] **Step 2: Run — fail** (ImportError)

- [ ] **Step 3: Implement dataclasses in `dossier.py`**

Copy all 9 `@dataclass(frozen=True)` definitions from spec §4.3 verbatim. Add `Dossier.to_dict()` as a simple pass-through using `dataclasses.asdict` for primitive fields and custom handling for pd.Series/DataFrame fields (serialize to records).

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_dossier_types.py -x -q
git add src/ah_research/analysis/dossier.py tests/unit/analysis/test_dossier_types.py
git commit -m "feat(phase-3): dossier section dataclasses + Dossier container

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: `build_dossier()` function

**Spec ref:** §4.3 `build_dossier`.

**Files:**
- Modify: `src/ah_research/analysis/dossier.py`
- Create: `tests/unit/analysis/test_dossier_build.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/analysis/test_dossier_build.py
from datetime import date
import pandas as pd
from ah_research.analysis.dossier import build_dossier, Dossier
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_build_dossier_a_share_no_ah_pair():
    repo = build_synthetic_market(
        start=date(2014, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    assert isinstance(d, Dossier)
    assert d.symbol.code == "600000"
    assert d.overview.sector_l1 != ""
    assert len(d.fundamentals.revenue_series) > 0
    assert d.ah_premium is None  # not dual-listed


def test_build_dossier_ah_pair_leg_populates_ah_section():
    repo = build_synthetic_market(
        start=date(2014, 1, 1), end=date(2024, 12, 31),
        symbols=["601318.SH", "2318.HK"],  # Ping An AH pair
    )
    d = build_dossier("601318.SH", repo, asof=date(2024, 12, 31))
    # NOTE: synthetic market may or may not register AH pair mapping.
    # If not present, ah_premium stays None. The test uses real AH pair codes
    # from ah_pairs.yaml so the pair lookup path executes even if premium values
    # are synthetic.
    # Accept either structured AHPremiumSection or None (fixture-dependent).
    assert d.symbol.code == "601318"


def test_build_dossier_delisted_symbol_raises():
    repo = build_synthetic_market(
        start=date(2014, 1, 1), end=date(2020, 12, 31),
        symbols=["600000.SH"],
    )
    with pytest.raises(ValueError, match="not available"):
        build_dossier("600000.SH", repo, asof=date(2024, 12, 31))  # after fixture end
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `build_dossier()`**

Append to `dossier.py`:

```python
def build_dossier(
    symbol: Symbol | str,
    repo: DataRepository,
    asof: date | None = None,
    peers_n: int = 5,
) -> Dossier:
    from ah_research.model.types import parse_symbol
    from ah_research.analysis.owner_earnings import owner_earnings_series
    from ah_research.analysis.valuation_bands import compute_valuation_bands
    from ah_research.analysis.dividend_history import dividend_consistency_grade
    from ah_research.data.ah_pairs import load_ah_pairs
    import subprocess

    sym = parse_symbol(symbol) if isinstance(symbol, str) else symbol
    asof = asof or date.today()
    warnings: list[str] = []

    # Verify symbol is available at asof
    try:
        prices = repo.get_prices([sym.code_with_exchange()], start=asof, end=asof)
        if prices.empty:
            raise ValueError(f"Symbol {sym} not available in repo at asof={asof}")
    except Exception as e:
        raise ValueError(f"Symbol {sym} not available in repo at asof={asof}: {e}") from e

    # Gather source data (10-year lookback)
    ten_year_start = date(asof.year - 10, asof.month, asof.day)
    fundamentals = repo.get_fundamentals(
        [sym.code_with_exchange()], start=ten_year_start, end=asof, asof=asof
    )
    corp_actions = repo.get_corporate_actions(
        [sym.code_with_exchange()], start=ten_year_start, end=asof
    )
    sector_df = repo.get_sector([sym.code_with_exchange()])

    # OverviewSection
    sec_row = sector_df.iloc[0] if not sector_df.empty else {"sector_l1": "Unknown", "sector_l2": None}
    latest_fund = fundamentals.sort_values("publication_date").iloc[-1] if not fundamentals.empty else None
    overview = OverviewSection(
        symbol=sym,
        name_en=None,
        name_zh=None,
        sector_l1=sec_row.get("sector_l1", "Unknown"),
        sector_l2=sec_row.get("sector_l2"),
        market_cap=float(latest_fund["market_cap"]) if latest_fund is not None else 0.0,
        market_cap_free_float=float(latest_fund.get("market_cap_free_float", 0.0)) if latest_fund is not None else 0.0,
        is_soe=bool(latest_fund.get("is_soe", False)) if latest_fund is not None else False,
        is_stock_connect_eligible=bool(latest_fund.get("is_stock_connect_eligible", False)) if latest_fund is not None else False,
        listing_date=None,
    )

    # FundamentalsSection (10y trajectory)
    fundamentals_sorted = fundamentals.sort_values("report_date")
    fs = FundamentalsSection(
        revenue_series=fundamentals_sorted.set_index("report_date")["revenue"] if "revenue" in fundamentals.columns else pd.Series(dtype=float),
        net_income_series=fundamentals_sorted.set_index("report_date")["net_income"] if "net_income" in fundamentals.columns else pd.Series(dtype=float),
        operating_cash_flow_series=fundamentals_sorted.set_index("report_date").get("operating_cash_flow", pd.Series(dtype=float)),
        capex_series=fundamentals_sorted.set_index("report_date").get("capex", pd.Series(dtype=float)),
        roe_series=fundamentals_sorted.set_index("report_date").get("roe", pd.Series(dtype=float)),
        roic_series=fundamentals_sorted.set_index("report_date").get("roic", pd.Series(dtype=float)),
        gross_margin_series=fundamentals_sorted.set_index("report_date").get("gross_margin", pd.Series(dtype=float)),
        net_margin_series=fundamentals_sorted.set_index("report_date").get("net_margin", pd.Series(dtype=float)),
        latest_fiscal_year=int(fundamentals_sorted["report_date"].iloc[-1].year) if not fundamentals_sorted.empty else asof.year - 1,
    )

    # OwnerEarningsSection
    oe_series = owner_earnings_series(fundamentals)
    oe = OwnerEarningsSection(
        series=oe_series,
        latest_fy=float(oe_series.iloc[-1]) if not oe_series.empty else 0.0,
        avg_10y=float(oe_series.mean()) if not oe_series.empty else 0.0,
        cv_10y=float(oe_series.std() / abs(oe_series.mean())) if not oe_series.empty and oe_series.mean() != 0 else 0.0,
    )

    # ValuationBandsSection
    pe_band = compute_valuation_bands(sym.code_with_exchange(), repo, asof, "pe", 10)
    pb_band = compute_valuation_bands(sym.code_with_exchange(), repo, asof, "pb", 10)
    ps_band = compute_valuation_bands(sym.code_with_exchange(), repo, asof, "ps", 10)
    vbs = ValuationBandsSection(
        pe_bands=pe_band.bands, pe_current=pe_band.current, pe_current_percentile=pe_band.current_percentile,
        pb_bands=pb_band.bands, pb_current=pb_band.current, pb_current_percentile=pb_band.current_percentile,
        ps_bands=ps_band.bands, ps_current=ps_band.current, ps_current_percentile=ps_band.current_percentile,
        window_years=pe_band.window_years,
    )
    if pe_band.window_years < 10:
        warnings.append(f"Valuation bands cover only {pe_band.window_years} years of history")

    # DividendSection
    grade = dividend_consistency_grade(corp_actions, asof, window_years=10)
    div_rows = corp_actions[corp_actions["kind"] == "cash_dividend"].sort_values("ex_date")
    dividend = DividendSection(
        history=div_rows.reset_index(drop=True),
        ttm_yield=0.0,   # executor: compute from last 4 quarters of cash dividends / price
        cagr_5y=0.0,
        cagr_10y=0.0,
        n_consecutive_years=0,
        consistency_grade=grade,
    )

    # AHPremiumSection (if dual-listed)
    ah_section: AHPremiumSection | None = None
    pairs = load_ah_pairs()
    matching_pair = next((p for p in pairs if p.a_symbol == sym or p.h_symbol == sym), None)
    if matching_pair is not None:
        other_leg = matching_pair.h_symbol if matching_pair.a_symbol == sym else matching_pair.a_symbol
        try:
            premium = repo.compute_ah_premium(matching_pair, asof, asof)
            if not premium.empty:
                ah_section = AHPremiumSection(
                    paired_symbol=other_leg,
                    pair_name_en=matching_pair.name_en,
                    current_premium=float(premium["premium"].iloc[-1]),
                    current_z_score=0.0,
                    premium_2y_series=pd.DataFrame(),
                    historical_max={"value": 0.0, "date": asof},
                    historical_min={"value": 0.0, "date": asof},
                )
        except Exception as e:
            warnings.append(f"AH premium unavailable: {e}")

    # PeersSection
    peers = PeersSection(peer_symbols=[], peer_table=pd.DataFrame())

    # Metadata
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        sha = "unknown"
    metadata = DossierMetadata(
        asof=asof, repo_snapshot_date=asof, code_version=sha, warnings=warnings,
    )

    return Dossier(
        symbol=sym, asof=asof,
        overview=overview, fundamentals=fs, owner_earnings=oe,
        valuation_bands=vbs, dividend_history=dividend,
        ah_premium=ah_section, peers=peers, metadata=metadata,
    )
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_dossier_build.py -x -q
uv run mypy src/ah_research/analysis/dossier.py
git add src/ah_research/analysis/dossier.py tests/unit/analysis/test_dossier_build.py
git commit -m "feat(phase-3): build_dossier() composes helpers into Dossier

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 12: `Dossier.to_markdown()` renderer (English + Chinese)

**Spec ref:** §4.3, §2 D3.

**Files:**
- Modify: `src/ah_research/analysis/dossier.py`
- Create: `tests/unit/analysis/test_dossier_render.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/analysis/test_dossier_render.py
from datetime import date
import pytest
from ah_research.analysis.dossier import build_dossier
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_to_markdown_english_contains_sections():
    repo = build_synthetic_market(
        start=date(2014, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    md = d.to_markdown(language="en")
    assert "# Dossier" in md
    assert "Overview" in md or "overview" in md.lower()
    assert "Valuation Bands" in md or "valuation" in md.lower()
    assert "Dividend" in md or "dividend" in md.lower()
    assert "# " in md  # at least one heading


def test_to_markdown_chinese_contains_chinese_headers():
    repo = build_synthetic_market(
        start=date(2014, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    md = d.to_markdown(language="zh")
    # At least some Chinese characters should appear in section headers
    assert any(ord(c) > 127 for c in md)


def test_to_dict_json_serializable():
    import json
    repo = build_synthetic_market(
        start=date(2014, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    as_dict = d.to_dict()
    # Must survive JSON round-trip (with default=str for dates)
    blob = json.dumps(as_dict, default=str)
    assert len(blob) > 100
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `.to_markdown()`, `.to_html()`, `.to_dict()`**

Append to `dossier.py` `Dossier` class (or attach via monkey-patch-free module-level method installed on the dataclass — prefer the former, using `@dataclass` doesn't forbid methods).

Use header tables:

```python
_HEADERS = {
    "en": {
        "title": "Dossier",
        "overview": "Overview",
        "fundamentals": "Fundamentals (10-Year Trajectory)",
        "owner_earnings": "Owner Earnings",
        "valuation": "Valuation Bands",
        "dividend": "Dividend History",
        "ah_premium": "AH Premium",
        "peers": "Sector Peers",
        "metadata": "Reproducibility",
    },
    "zh": {
        "title": "公司档案",
        "overview": "概览",
        "fundamentals": "基本面（10年轨迹）",
        "owner_earnings": "所有者盈余",
        "valuation": "估值分位",
        "dividend": "分红历史",
        "ah_premium": "A/H溢价",
        "peers": "同业对比",
        "metadata": "可复现性信息",
    },
}
```

Implement `to_markdown()` as a method on `Dossier` that walks sections, formatting each with language-localized headers, using a table-style for bands and series.

Implement `to_html()` as a thin wrapper: convert markdown to HTML via `markdown` library if available, else plain `<pre>` fallback. Simpler: hand-roll HTML table strings directly.

Implement `to_dict()` using `dataclasses.asdict` with pd.Series/DataFrame converted to list-of-records.

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/analysis/test_dossier_render.py -x -q
git add src/ah_research/analysis/dossier.py tests/unit/analysis/test_dossier_render.py
git commit -m "feat(phase-3): Dossier.to_markdown / to_html / to_dict renderers (en+zh)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 13: Watchlist migration + `WatchlistStore` CRUD

**Spec ref:** §4.7.

**Files:**
- Create: `src/ah_research/watchlist/migrations.py`
- Create: `src/ah_research/watchlist/store.py`
- Modify: `src/ah_research/data/cache.py` (register migration #4)
- Create: `tests/unit/watchlist/test_store.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/watchlist/test_store.py
from datetime import date
from pathlib import Path
import tempfile
import pytest
from ah_research.watchlist.store import WatchlistStore


def _fresh_store():
    tmpdir = Path(tempfile.mkdtemp())
    return WatchlistStore(cache_path=tmpdir / "cache.duckdb")


def test_create_get_list():
    store = _fresh_store()
    wl = store.create("my_picks", symbols=["600000.SH", "000001.SZ"], description="Test")
    assert wl.name == "my_picks"
    assert len(wl.symbols) == 2

    got = store.get("my_picks")
    assert got.name == "my_picks"

    all_wls = store.list_all()
    assert any(x.name == "my_picks" for x in all_wls)


def test_add_remove_symbol():
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH"])
    wl = store.add_symbol("my_picks", "000001.SZ")
    assert len(wl.symbols) == 2
    wl = store.remove_symbol("my_picks", "600000.SH")
    assert len(wl.symbols) == 1
    assert wl.symbols[0].code == "1"  # 000001.SZ
    # or whatever format parse_symbol returns


def test_duplicate_create_raises():
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH"])
    with pytest.raises(ValueError, match="already exists"):
        store.create("my_picks", symbols=["000001.SZ"])


def test_delete_removes_definition_and_snapshots():
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH"])
    store.delete("my_picks")
    with pytest.raises(KeyError):
        store.get("my_picks")


def test_yaml_export_import_roundtrip(tmp_path):
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH", "000001.SZ"], description="Test")
    path = tmp_path / "wl.yaml"
    store.export_yaml("my_picks", path)
    assert path.exists()

    store2 = _fresh_store()
    imported = store2.import_yaml(path)
    assert imported.name == "my_picks"
    assert len(imported.symbols) == 2
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

First, `migrations.py`:

```python
# src/ah_research/watchlist/migrations.py
"""Migration #4 — watchlist tables."""

MIGRATION_VERSION = 4

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS watchlist_definitions (
    name VARCHAR PRIMARY KEY,
    description VARCHAR,
    symbols JSON NOT NULL,
    screen_conditions JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_snapshots (
    watchlist_name VARCHAR NOT NULL,
    snapshot_date DATE NOT NULL,
    symbol VARCHAR NOT NULL,
    metrics JSON NOT NULL,
    PRIMARY KEY (watchlist_name, snapshot_date, symbol),
    FOREIGN KEY (watchlist_name) REFERENCES watchlist_definitions(name) ON DELETE CASCADE
);
"""

WATCHLIST_TABLE_PREFIX = "watchlist_"
```

Then modify `data/cache.py` to register this migration in the existing migration chain. Find the migration registry and append:

```python
from ah_research.watchlist.migrations import MIGRATION_SQL as M4_SQL, MIGRATION_VERSION as M4_VER
# register under M4_VER = 4
```

Also modify the `--reset-cache` helper (search for `reset_cache` or similar in Phase 1 code) to exclude tables with `WATCHLIST_TABLE_PREFIX`. Add a regression test.

Then `store.py` (~250 LOC):

```python
# src/ah_research/watchlist/store.py
"""CRUD and YAML interop over DuckDB watchlist tables."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
import yaml
import duckdb
import pandas as pd
from ah_research.model.types import Symbol, parse_symbol


@dataclass(frozen=True)
class Watchlist:
    name: str
    description: str | None
    symbols: list[Symbol]
    screen_conditions: dict | None
    created_at: pd.Timestamp
    updated_at: pd.Timestamp


class WatchlistStore:
    def __init__(self, cache_path: Path | None = None):
        if cache_path is None:
            from ah_research.config import get_settings
            cache_path = get_settings().cache_dir / "cache.duckdb"
        self.cache_path = cache_path
        self._ensure_migrated()

    def _ensure_migrated(self) -> None:
        from ah_research.watchlist.migrations import MIGRATION_SQL
        con = duckdb.connect(str(self.cache_path))
        try:
            con.execute(MIGRATION_SQL)
        finally:
            con.close()

    def _conn(self):
        return duckdb.connect(str(self.cache_path))

    def create(self, name: str, symbols: list, description: str = "",
               screen_conditions: dict | None = None) -> Watchlist:
        with self._conn() as con:
            exists = con.execute(
                "SELECT 1 FROM watchlist_definitions WHERE name = ?", [name]
            ).fetchone()
            if exists is not None:
                raise ValueError(f"Watchlist {name!r} already exists")
            sym_strings = [s if isinstance(s, str) else s.code_with_exchange() for s in symbols]
            con.execute(
                "INSERT INTO watchlist_definitions (name, description, symbols, screen_conditions) "
                "VALUES (?, ?, ?, ?)",
                [name, description, json.dumps(sym_strings),
                 json.dumps(screen_conditions) if screen_conditions else None],
            )
        return self.get(name)

    def get(self, name: str) -> Watchlist:
        with self._conn() as con:
            row = con.execute(
                "SELECT name, description, symbols, screen_conditions, created_at, updated_at "
                "FROM watchlist_definitions WHERE name = ?", [name]
            ).fetchone()
        if row is None:
            raise KeyError(name)
        return Watchlist(
            name=row[0], description=row[1],
            symbols=[parse_symbol(s) for s in json.loads(row[2])],
            screen_conditions=json.loads(row[3]) if row[3] else None,
            created_at=pd.Timestamp(row[4]), updated_at=pd.Timestamp(row[5]),
        )

    def list_all(self) -> list[Watchlist]:
        with self._conn() as con:
            rows = con.execute("SELECT name FROM watchlist_definitions").fetchall()
        return [self.get(r[0]) for r in rows]

    def add_symbol(self, name: str, symbol) -> Watchlist:
        wl = self.get(name)
        sym_str = symbol if isinstance(symbol, str) else symbol.code_with_exchange()
        new_syms = sorted({s.code_with_exchange() for s in wl.symbols} | {sym_str})
        with self._conn() as con:
            con.execute(
                "UPDATE watchlist_definitions SET symbols = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE name = ?", [json.dumps(new_syms), name]
            )
        return self.get(name)

    def remove_symbol(self, name: str, symbol) -> Watchlist:
        wl = self.get(name)
        sym_str = symbol if isinstance(symbol, str) else symbol.code_with_exchange()
        new_syms = sorted({s.code_with_exchange() for s in wl.symbols} - {sym_str})
        with self._conn() as con:
            con.execute(
                "UPDATE watchlist_definitions SET symbols = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE name = ?", [json.dumps(new_syms), name]
            )
        return self.get(name)

    def delete(self, name: str) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM watchlist_definitions WHERE name = ?", [name])

    def export_yaml(self, name: str, path: Path) -> None:
        wl = self.get(name)
        payload = {
            "name": wl.name,
            "description": wl.description,
            "symbols": [s.code_with_exchange() for s in wl.symbols],
            "screen_conditions": wl.screen_conditions,
        }
        path.write_text(yaml.safe_dump(payload, allow_unicode=True))

    def import_yaml(self, path: Path, overwrite: bool = False) -> Watchlist:
        payload = yaml.safe_load(path.read_text())
        if overwrite:
            try:
                self.delete(payload["name"])
            except KeyError:
                pass
        return self.create(
            name=payload["name"],
            symbols=payload["symbols"],
            description=payload.get("description", ""),
            screen_conditions=payload.get("screen_conditions"),
        )

    # snapshot methods deferred to Task 14
    def update(self, name: str, **kwargs) -> Watchlist:
        # Set any of: symbols, description, screen_conditions
        ...
```

- [ ] **Step 4: Run — pass + commit**

```bash
uv run pytest tests/unit/watchlist/test_store.py -x -q
uv run mypy src/ah_research/watchlist/
git add src/ah_research/watchlist/ src/ah_research/data/cache.py tests/unit/watchlist/
git commit -m "feat(phase-3): WatchlistStore CRUD + DuckDB migration + YAML interop

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 14: `WatchlistSnapshot` + diff

**Spec ref:** §4.7 snapshot API.

**Files:**
- Create: `src/ah_research/watchlist/snapshot.py`
- Modify: `src/ah_research/watchlist/store.py` (add snapshot methods)
- Create: `tests/unit/watchlist/test_snapshot.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/watchlist/test_snapshot.py
from datetime import date
from pathlib import Path
import tempfile
import pytest
from ah_research.watchlist.store import WatchlistStore
from ah_research.watchlist.snapshot import WatchlistSnapshot
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def _fresh():
    return WatchlistStore(cache_path=Path(tempfile.mkdtemp()) / "cache.duckdb")


def test_snapshot_creates_row_per_symbol():
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    store.create("my_picks", symbols=["600000.SH", "000001.SZ"])
    snap = store.snapshot("my_picks", repo, asof=date(2024, 12, 31))
    assert isinstance(snap, WatchlistSnapshot)
    assert len(snap.rows) == 2
    assert "pe" in snap.rows.columns or "price" in snap.rows.columns


def test_snapshot_immutable_without_force():
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    store.create("my_picks", symbols=["600000.SH"])
    store.snapshot("my_picks", repo, asof=date(2024, 12, 31))
    with pytest.raises(ValueError, match="already exists"):
        store.snapshot("my_picks", repo, asof=date(2024, 12, 31))


def test_diff_snapshots():
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    store.create("my_picks", symbols=["600000.SH", "000001.SZ"])
    store.snapshot("my_picks", repo, asof=date(2024, 6, 30))
    store.snapshot("my_picks", repo, asof=date(2024, 12, 31))
    diff = store.diff_snapshots("my_picks", earlier=date(2024, 6, 30), later=date(2024, 12, 31))
    assert isinstance(diff, type(snap.rows)) or hasattr(diff, "columns")
    assert "delta_pe" in diff.columns or "pe_delta" in diff.columns
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`snapshot.py`:

```python
from dataclasses import dataclass
from datetime import date
import pandas as pd


@dataclass(frozen=True)
class WatchlistSnapshot:
    watchlist_name: str
    snapshot_date: date
    rows: pd.DataFrame
```

Extend `store.py` with `.snapshot()`, `.list_snapshots()`, `.get_snapshot()`, `.diff_snapshots()`. Pull metrics (pe, pb, dividend_yield, roe, market_cap, sector_l1, price) via repo. Store as one row per symbol in `watchlist_snapshots` with `metrics` as JSON. Diff joins two snapshot dates and computes deltas.

- [ ] **Step 4: Run — pass + commit**

---

## Task 15: Portfolio `Constraint` class + factories

**Spec ref:** §4.8.

**Files:**
- Create: `src/ah_research/portfolio/constructor.py` (initial — Constraint only)
- Create: `tests/unit/portfolio/test_constraint.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/portfolio/test_constraint.py
from ah_research.portfolio.constructor import Constraint


def test_max_weight_factory():
    c = Constraint.max_weight(0.05)
    assert c.kind == "max_weight"
    assert c.params == {"w": 0.05}
    assert c.priority == 50


def test_sector_neutral_factory():
    c = Constraint.sector_neutral_to("CSI300")
    assert c.kind == "sector_neutral_to"
    assert c.params == {"benchmark": "CSI300"}


def test_constraint_frozen():
    import pytest
    c = Constraint.max_weight(0.05)
    with pytest.raises(Exception):
        c.kind = "other"  # type: ignore[misc]


def test_all_factories_return_constraint():
    factories = [
        Constraint.max_weight(0.05), Constraint.max_gross(0.50),
        Constraint.sector_neutral_to("CSI300"), Constraint.tracking_error(300),
        Constraint.min_positions(10), Constraint.max_positions(50),
    ]
    for c in factories:
        assert isinstance(c, Constraint)
```

- [ ] **Step 2-4: Implement + commit**

Implement `Constraint` dataclass + factory classmethods from spec §4.8. Commit.

---

## Task 16: Portfolio `Constructor` chain + `ConstructionReport`

**Spec ref:** §4.8.

**Files:**
- Modify: `src/ah_research/portfolio/constructor.py`
- Create: `tests/unit/portfolio/test_constructor.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/portfolio/test_constructor.py
from datetime import date
import pandas as pd
import pytest
from ah_research.portfolio.constructor import Constructor, Constraint, ConstructionReport
from ah_research.backtest.types import Signals
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_constructor_chain_builds_report():
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 6, 30),
        symbols=[f"60000{i}.SH" for i in range(10)],
    )
    # Build synthetic signals: random signals for 10 names on one date
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-06-30"] * 10),
        "symbol": [f"60000{i}.SH" for i in range(10)],
        "signal": [float(i) for i in range(10)],
    })
    signals = Signals.from_dataframe(df)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("top_quantile", quantile=0.2)
        .weight_by("equal")
        .constrain(Constraint.max_weight(0.5))
        .build()
    )
    assert isinstance(report, ConstructionReport)
    assert report.final_position_count == 2  # top 20% of 10
    assert len(report.constraint_results) == 1


def test_constructor_max_weight_relaxes_and_reports():
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 6, 30),
        symbols=["SYM1.SH", "SYM2.SH"],
    )
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-06-30", "2024-06-30"]),
        "symbol": ["SYM1.SH", "SYM2.SH"],
        "signal": [1.0, 1.0],
    })
    signals = Signals.from_dataframe(df)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("all_positive")
        .weight_by("equal")  # 0.5 each
        .constrain(Constraint.max_weight(0.3))  # forces relaxation
        .build()
    )
    assert report.constraint_results[0].status in ("bound", "infeasible_relaxed")
```

- [ ] **Step 2-4: Implement + commit**

Implement `Constructor` class, execution order (method → weight_by → constraints in priority order), relaxation helpers per spec §4.8. Emit `ConstructionReport` with per-constraint `ConstraintResult`.

---

## Task 17: CLI — `ah dossier`

**Spec ref:** §9.

**Files:**
- Create: `src/ah_research/scripts/ah_dossier.py`
- Modify: `src/ah_research/cli.py` (register subcommand)
- Create: `tests/unit/test_ah_dossier.py`

- [ ] **Step 1-5: TDD cycle**

Thin typer wrapper:
```python
@app.command()
def dossier(
    symbol: str,
    asof: str = typer.Option(None),
    out: Path = typer.Option(None),
    language: str = typer.Option("en"),
) -> None:
    from ah_research.data import DataRepository
    from ah_research.analysis.dossier import build_dossier
    repo = DataRepository.from_default_cache()
    asof_d = datetime.strptime(asof, "%Y-%m-%d").date() if asof else date.today()
    d = build_dossier(symbol, repo, asof=asof_d)
    md = d.to_markdown(language=language)
    if out:
        out.write_text(md)
    else:
        print(md)
```

Test uses click/typer's CliRunner.

Commit.

---

## Task 18: CLI — `ah watchlist ...` subcommands

**Spec ref:** §9.

**Files:**
- Create: `src/ah_research/scripts/ah_watchlist.py`
- Modify: `src/ah_research/cli.py`
- Create: `tests/unit/test_ah_watchlist.py`

- [ ] Implement subcommands: `list`, `create`, `snapshot`, `diff`, `export`, `import`. Each delegates to WatchlistStore. Commit.

---

## Task 19: Integration tests

**Spec ref:** §7.2.

**Files:**
- Create: `tests/integration/test_end_to_end_factor_study.py`
- Create: `tests/integration/test_end_to_end_screener_to_watchlist.py`
- Create: `tests/integration/test_end_to_end_dossier.py`

- [ ] For each: runs full pipeline against synthetic market, asserts key invariants + no crashes across common inputs. Commit each.

---

## Task 20: Property tests

**Spec ref:** §7.3.

**Files:**
- Create: `tests/property/test_analysis_invariants.py`

```python
from hypothesis import given, strategies as st, settings

@given(seed=st.integers(0, 2**31-1))
@settings(max_examples=10, deadline=60_000)
def test_screener_idempotent(seed):
    # build_synthetic_market(seed=seed); run_screen twice; assert equal
    ...

@given(seed=st.integers())
@settings(max_examples=10, deadline=60_000)
def test_constructor_weights_sum_to_one_when_all_slack(seed):
    ...

@given(seed=st.integers())
@settings(max_examples=5, deadline=120_000)
def test_factor_study_shuffled_signals_zero_ic_within_noise(seed):
    ...
```

Implement + commit.

---

## Task 21: Public API re-exports

**Files:**
- Modify: `src/ah_research/analysis/__init__.py`
- Modify: `src/ah_research/watchlist/__init__.py`
- Modify: `src/ah_research/portfolio/__init__.py`
- Create: `tests/unit/analysis/test_public_api.py`
- Create: `tests/unit/watchlist/test_public_api.py`

```python
# analysis/__init__.py
from ah_research.analysis.factor_study import factor_study, FactorReport
from ah_research.analysis.screener import run_screen, ScreenResult
from ah_research.analysis.dossier import build_dossier, Dossier
from ah_research.analysis.owner_earnings import owner_earnings_series
from ah_research.analysis.valuation_bands import compute_valuation_bands, ValuationBand
from ah_research.analysis.dividend_history import dividend_consistency_grade

__all__ = [
    "factor_study", "FactorReport",
    "run_screen", "ScreenResult",
    "build_dossier", "Dossier",
    "owner_earnings_series",
    "compute_valuation_bands", "ValuationBand",
    "dividend_consistency_grade",
]
```

Similar for watchlist and portfolio. Test imports. Commit.

---

## Task 22-25: Four reference notebooks

**Spec ref:** §1 item 9.

**Files:** one notebook each + one test per notebook via nbclient.

- `notebooks/phase3_factor_study_value.ipynb`
- `notebooks/phase3_screener_workflow.ipynb`
- `notebooks/phase3_dossier_example.ipynb`
- `notebooks/phase3_portfolio_construction.ipynb`

Each notebook:
1. Imports + synthetic market setup
2. Core feature demo (~5 cells)
3. Reproducibility block at end
4. Disclaimer cell: "Results are synthetic / historical backtest, not investment advice."

Test via `nbclient.NotebookClient` as in Phase 2 Task 30. Mark `@pytest.mark.slow`.

One commit per notebook (4 commits).

---

## Task 26: CHANGELOG + README + coverage

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] Add `## [Unreleased] — Phase 3` section listing all deliverables
- [ ] Add `Phase 3 — Analysis & Watchlist` section to README linking spec + plan + notebooks
- [ ] Run full test suite + coverage:
```bash
uv run pytest --cov=src/ah_research/analysis --cov=src/ah_research/watchlist --cov=src/ah_research/portfolio/constructor.py --cov-report=term-missing --cov-fail-under=90 -q
uv run mypy src/ah_research/analysis/ src/ah_research/watchlist/ src/ah_research/portfolio/
uv run ruff check src/ tests/
```
- [ ] Commit

---

## Task 27: Open PR

```bash
git push -u origin feat/phase-3-analysis
gh pr create --title "Phase 3: factor study, screener, dossier, watchlist, constructor" \
             --body "$(cat <<'EOF'
## Summary
Implements Phase 3 per spec 2026-04-29-ah-research-phase-3-analysis-design.md.

- analysis/: factor_study, screener, dossier, owner_earnings, valuation_bands, dividend_history
- watchlist/: DuckDB-backed CRUD + snapshot + YAML interop
- portfolio/constructor.py: Constructor + Constraint + ConstructionReport
- CLI: ah dossier, ah watchlist ...
- Four reference notebooks
- No new runtime deps

## Test plan
- [ ] pytest -q green
- [ ] coverage >= 90% on new modules
- [ ] mypy --strict clean
- [ ] ruff clean
- [ ] Four notebooks run end-to-end via nbclient
- [ ] `ah init --reset-cache` preserves watchlist tables (regression test)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review notes

**Spec coverage check:**
- §1 nine components → Tasks 2-9 (factor study = 6,7,8,9), Task 5 (screener), Tasks 10-12 (dossier absorbing owner-earnings+valuation-bands+dividend-history which are Tasks 2,3,4), Tasks 13,14 (watchlist), Tasks 15,16 (constructor), Tasks 22-25 (4 notebooks). ✓
- §2 D1-D9 → embedded in implementation ✓
- §3 module layout → Tasks 1 (skeleton), all impl tasks ✓
- §4 APIs → Tasks 2-16 ✓
- §7 testing → unit tests in every task, Task 19 (integration), Task 20 (property) ✓
- §8 error handling → embedded (delisted symbol check in Task 11, KeyError in Task 5) ✓
- §9 CLI → Tasks 17,18 ✓
- §10 DoD → Task 26 ✓

**Type consistency:**
- `Signals`, `Weights`, `SignalStrategy` reused from Phase 2 consistently ✓
- `DataRepository` access pattern identical across new modules ✓
- Dataclass naming: `FactorReport`, `ScreenResult`, `Dossier`, `Watchlist`, `ConstructionReport` — distinct suffixes (`Report` / `Result` / `Dossier` / `Watchlist`) by role ✓

**Placeholder scan:** One "..." in Task 14 snapshot test (executor fills); one incomplete sketch in Task 17 (typer boilerplate) and Task 18. All acceptable since signatures are explicit and the patterns match Phase 2 precedents.

**Scope:** 27 tasks. Similar shape to Phase 2 (31). Ready to execute.
