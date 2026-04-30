# Phase 3 Design — Factor + Portfolio + Value Analysis

**Status:** Draft, pending user review
**Author:** Brian Huang (+ Claude)
**Date:** 2026-04-29
**Depends on:** Phase 0/1/2 (Phase 2 PR #2 pending merge); parent design `2026-04-28-ah-research-platform-design.md`

---

## 1. Scope

Phase 3 delivers the **analyst-facing research layer** on top of the Phase 2 engine:

1. **Factor study** — Spearman IC, IC decay, quantile returns, Newey-West t-stats, block-bootstrap Q5−Q1 significance.
2. **Screener** — vectorized fundamental/flag filtering with a serializable predicate dict.
3. **Portfolio constructor** — chainable `Constructor` API over Phase 2 weights with `Constraint` classes (free-float MCW, hard sector-neutral, tracking-error, max-weight) and a `ConstructionReport` that audits which constraints bound vs. slacked.
4. **Dossier** — structured company profile dataclass + `.to_markdown()` / `.to_html()` renderers, absorbing owner-earnings, valuation bands, dividend-consistency, and AH premium as embedded sections.
5. **Owner-earnings** — Buffett 1986 formula as a reusable series computation (`net_income + d_and_a − capex − working_capital_change`).
6. **Valuation bands** — trailing 10-year P/E / P/B / P/S percentile bands with current-percentile marker.
7. **Dividend consistency grading** — A–F letter grade over 10-year history.
8. **Watchlist** — DuckDB-backed named lists with snapshot-over-time history, plus YAML import/export helper.
9. **Value notebooks** — four reference notebooks (factor study, screener workflow, dossier example, portfolio construction).

**Estimated effort:** ~2 weeks (honest estimate; design doc's 1 week covered only the factor study + portfolio constructors, not the full feature list).

**Out of scope (deferred):**
- Portfolio optimizer (CVXPY mean-variance, risk parity) → Phase 4.
- LLM-generated narrative in dossier → Phase 5 chat UI.
- Automated watchlist alerting (cron / email) → not on roadmap.
- Forward-looking (NTM) valuation bands — requires analyst estimate data not in Phase 1.
- Standalone AH-pair dossier module — AH premium is a section inside the regular dossier.

---

## 2. Key design decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Factor study accepts `SignalStrategy | pd.DataFrame`** (Q2 option C) | Notebook ergonomics + strategy equivalence — same signal drives factor research and backtest. Inline DataFrame adapter wraps ad-hoc signals in a trivial `_InlineSignalStrategy`. |
| D2 | **Screener uses a serializable predicate dict** (Q3 option B): `{"pe": ("<", 15), "dividend_yield": (">", 0.03), ...}` | Vectorized pandas mask is fast; serialization lets `Watchlist` persist its screen condition; operator set is fixed (`<, <=, >, >=, ==, !=, between, in, not_in`). |
| D3 | **`Dossier` is a frozen dataclass with `.to_markdown()` and `.to_html()` renderers** (Q4 option C) | Structured form serves Phase 5 (chat UI reasons over structured data); renderers are thin f-strings over fields. Default language = English, overridable via `language="zh"`. |
| D4 | **Watchlist lives in DuckDB cache** (Q5 option B) as two new tables, with YAML export helper | Same connection as data layer; queryable history of snapshots over time; watchlist tables have separate lifecycle (not blown away by `ah init --reset-cache`). |
| D5 | **Portfolio `Constructor` chains `Constraint` objects** (Q6 option B), produces `Weights` + `ConstructionReport` | Audit-friendly; constraints compose explicitly; sets up Phase 4 optimizer branch cleanly (heuristic path in Phase 3, QP path in Phase 4). Phase 2's `signal_to_weights` stays untouched. |
| D6 | **Owner-earnings, valuation bands, dividend consistency are top-level functions** (Phase 3 D7(b,c,d)) **AND also composed into `Dossier`** | Single source of truth; dossier calls these helpers rather than reimplementing. Each is independently testable. |
| D7 | **Sector-neutral default ON in factor study**; uses `repo.get_sector().sector_l1` for A-shares, HSI industry for HK, `"Unknown"` fallback with warning. | Standard academic practice; sector exposure dominates most factor IC if left untreated. Warning on Unknown prevents silent data loss. |
| D8 | **Default benchmark auto-selected from universe exchange** (CSI300_TR for A-shares, HSI_TR for HK); overrideable via `benchmark=...` | Sensible defaults reduce ceremony for common cases. |
| D9 | **New CLI command `ah dossier <symbol>`** | Matches existing `ah init / warmup / doctor` pattern; one-liner access to the dossier renderer. |

---

## 3. Module layout

```
src/ah_research/
├── analysis/
│   ├── __init__.py                # public re-exports
│   ├── factor_study.py            # factor_study() + FactorReport + bootstrap (~400 LOC)
│   ├── screener.py                # run_screen() + derived-column catalog (~250 LOC)
│   ├── dossier.py                 # Dossier dataclass + section dataclasses + renderers (~500 LOC)
│   ├── owner_earnings.py          # owner_earnings_series() (~80 LOC)
│   ├── valuation_bands.py         # compute_valuation_bands() (~100 LOC)
│   └── dividend_history.py        # dividend_consistency_grade() (~120 LOC)
│
├── watchlist/
│   ├── __init__.py
│   ├── store.py                   # CRUD over DuckDB cache (~200 LOC)
│   ├── snapshot.py                # snapshot build + diff (~150 LOC)
│   └── migrations.py              # two-table DDL (~50 LOC)
│
├── portfolio/
│   ├── construction.py            # (Phase 2, untouched)
│   └── constructor.py             # new: Constructor + Constraint (~400 LOC)
│
├── scripts/
│   └── ah_dossier.py              # new CLI entry (~60 LOC)
│
└── data/                          # (unchanged; dossier reads via DataRepository only)
```

New notebooks:
```
notebooks/
├── phase3_factor_study_value.ipynb
├── phase3_screener_workflow.ipynb
├── phase3_dossier_example.ipynb
└── phase3_portfolio_construction.ipynb
```

Tests mirror source layout under `tests/unit/analysis/`, `tests/unit/watchlist/`, `tests/unit/portfolio/test_constructor.py`.

### Dependency rules (enforced in review)

1. `analysis/*` depends only on `data.repository`, `model.schemas`, `model.types`, `backtest.metrics`. It does **not** depend on `backtest.engine`, `portfolio.*`, or `strategies.*` — analysis is decoupled from execution.
2. `watchlist/*` depends on `data.cache` (DuckDB connection) and `analysis/screener` (for stored screens) and `analysis/dossier` (for snapshot metrics).
3. `portfolio/constructor.py` depends on `portfolio/construction.py` (reuses `top_quantile_weights`, `cap_at`), `data.repository` (for free-float and sector lookup), but NOT on any `analysis/*` module.
4. `dossier.py` composes `owner_earnings`, `valuation_bands`, `dividend_history` — those three helpers have no dependency on dossier.
5. `strategies/*` from Phase 2 remains unchanged.

---

## 4. Core APIs

### 4.1 Factor study

```python
# analysis/factor_study.py

from dataclasses import dataclass
from datetime import date
from typing import Literal
import pandas as pd
from ah_research.data.repository import DataRepository
from ah_research.strategies.base import SignalStrategy
from ah_research.backtest.types import Signals


@dataclass(frozen=True)
class FactorReport:
    ic_by_horizon: pd.DataFrame        # index=rebalance_date, columns=[1,5,10,20,60], values=Spearman IC
    ic_summary: pd.DataFrame           # rows=horizons, columns=[mean_ic, nw_t_stat, nw_p_value, ir]
    ic_decay: pd.Series                # mean IC by horizon — shows when alpha fades
    quantile_returns: pd.DataFrame     # index=date, columns=[Q1..Q5, long_short]
    quantile_summary: pd.DataFrame     # rows=[Q1..Q5, long_short], columns=[cagr, sharpe, max_dd]
    bootstrap_q5_minus_q1: dict        # {"mean": float, "ci_low": float, "ci_high": float, "p_value": float}
    sector_neutralized: bool
    n_rebalance_dates: int
    universe_summary: dict             # {"avg_n_names": int, "min_n_names": int}


def factor_study(
    strategy: SignalStrategy | pd.DataFrame,
    repo: DataRepository,
    start: date,
    end: date,
    n_quantiles: int = 5,
    ic_horizons: list[int] = [1, 5, 10, 20, 60],
    sector_neutral: bool = True,
    bootstrap_n_resamples: int = 1000,
    bootstrap_block_size: int = 21,
    benchmark: Literal["CSI300_TR", "HSI_TR", "auto"] | pd.Series = "auto",
    rebalance: Literal["W", "M", "Q"] = "M",
    random_seed: int = 42,
) -> FactorReport: ...
```

**Algorithm sketch:**
1. Coerce input: if `pd.DataFrame`, wrap in `_InlineSignalStrategy(df)` which implements `SignalStrategy`.
2. Derive rebalance dates from `repo.get_trading_calendar(...)` and `rebalance`.
3. For each rebalance date `d`: call `strategy.generate(repo, d, d)` → `Signals`. Merge against PIT universe.
4. If `sector_neutral=True`: demean signal within sector_l1 groups at each date.
5. Assign quantiles per date (`pd.qcut`); compute forward returns at each horizon from `repo.get_prices`.
6. IC: Spearman correlation between signal and each forward-return horizon, one value per rebalance date.
7. IC summary: for each horizon, `mean_ic`, Newey-West t-stat with Andrews lag (reuse `backtest.metrics.alpha_beta_newey_west` helper), IR = `mean_ic / std_ic`.
8. Quantile returns: equal-weighted portfolio returns per quantile per period; long-short = Q5 − Q1.
9. Block bootstrap on `long_short` returns: resample contiguous blocks with replacement, compute mean per resample, report 95% CI + p-value against null `mean=0`.

### 4.2 Screener

```python
# analysis/screener.py

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
import pandas as pd

Op = Literal["<", "<=", ">", ">=", "==", "!=", "between", "in", "not_in"]
Condition = tuple[Op, Any] | tuple[Op, Any, Any]  # ("between", lo, hi)


@dataclass(frozen=True)
class ScreenResult:
    asof: date
    universe: str
    n_input: int
    n_passed: int
    frame: pd.DataFrame            # columns=[symbol, sector_l1, ...all filter inputs..., market_cap]
    conditions_applied: dict[str, Condition]


def run_screen(
    conditions: dict[str, Condition],
    repo: DataRepository,
    asof: date,
    universe: str = "CSI300",
) -> ScreenResult: ...
```

**Supported columns (derived-column catalog — implemented in `_enrich_screen_frame()`):**

Raw (from Phase 1 fundamentals):
- `pe`, `pb`, `ps`, `ev_ebitda`, `dividend_yield`, `market_cap`, `market_cap_free_float`
- `roe`, `roic`, `roa`, `gross_margin`, `net_margin`
- `is_soe`, `is_stock_connect_eligible`
- `is_st` (from current-bar flags)

Derived (Phase 3 adds):
- `roe_3y_avg`, `roe_5y_avg` — arithmetic mean over rolling period
- `dividend_growth_5y_cagr` — CAGR of annual cash dividends per share
- `dividend_consistency_grade` — A-F letter (see §4.7)
- `revenue_growth_3y_cagr`, `net_income_growth_3y_cagr`
- `debt_to_equity` — `total_debt / total_equity`
- `free_cash_flow_yield` — `(operating_cash_flow - capex) / market_cap`, using latest PIT fiscal-year values (not TTM — fundamentals are annual)
- `owner_earnings_yield` — `owner_earnings_latest_fy / market_cap`, using the latest fiscal year's owner earnings per §4.4

Derived columns are computed lazily — only if referenced in `conditions`.

### 4.3 Dossier

```python
# analysis/dossier.py

from dataclasses import dataclass
from datetime import date
from typing import Literal
import pandas as pd
from ah_research.model.types import Symbol


@dataclass(frozen=True)
class OverviewSection:
    symbol: Symbol
    name_en: str | None
    name_zh: str | None
    sector_l1: str
    sector_l2: str | None
    market_cap: float
    market_cap_free_float: float
    is_soe: bool
    is_stock_connect_eligible: bool
    listing_date: date | None


@dataclass(frozen=True)
class FundamentalsSection:
    # 10-year trailing trajectory
    revenue_series: pd.Series          # index=fiscal_year_end, values in local currency
    net_income_series: pd.Series
    operating_cash_flow_series: pd.Series
    capex_series: pd.Series
    roe_series: pd.Series
    roic_series: pd.Series
    gross_margin_series: pd.Series
    net_margin_series: pd.Series
    latest_fiscal_year: int


@dataclass(frozen=True)
class OwnerEarningsSection:
    series: pd.Series                  # 10y annual, indexed by fiscal_year_end
    latest_fy: float                   # most recent fiscal year value (NOT TTM — fundamentals are annual)
    avg_10y: float
    cv_10y: float                      # coefficient of variation; volatility of owner earnings


@dataclass(frozen=True)
class ValuationBandsSection:
    pe_bands: dict                     # {"p10": float, "p25": float, "p50": float, "p75": float, "p90": float}
    pe_current: float
    pe_current_percentile: float       # where current stands vs 10y distribution, 0-100
    pb_bands: dict
    pb_current: float
    pb_current_percentile: float
    ps_bands: dict
    ps_current: float
    ps_current_percentile: float
    window_years: int                  # = 10


@dataclass(frozen=True)
class DividendSection:
    history: pd.DataFrame              # [ex_date, amount_per_share, yield_at_ex_date]
    ttm_yield: float
    cagr_5y: float
    cagr_10y: float
    n_consecutive_years: int
    consistency_grade: str             # "A".."F"


@dataclass(frozen=True)
class AHPremiumSection:
    paired_symbol: Symbol              # the other leg
    pair_name_en: str
    current_premium: float             # A/(H*fx) - 1
    current_z_score: float             # vs 60d rolling window
    premium_2y_series: pd.DataFrame    # [date, premium, fx_rate]
    historical_max: dict               # {"value": float, "date": date}
    historical_min: dict


@dataclass(frozen=True)
class PeersSection:
    peer_symbols: list[Symbol]
    peer_table: pd.DataFrame           # [symbol, name, market_cap, pe, pb, roe, dividend_yield]


@dataclass(frozen=True)
class DossierMetadata:
    asof: date
    repo_snapshot_date: date
    code_version: str
    warnings: list[str]


@dataclass(frozen=True)
class Dossier:
    symbol: Symbol
    asof: date
    overview: OverviewSection
    fundamentals: FundamentalsSection
    owner_earnings: OwnerEarningsSection
    valuation_bands: ValuationBandsSection
    dividend_history: DividendSection
    ah_premium: AHPremiumSection | None
    peers: PeersSection
    metadata: DossierMetadata

    def to_markdown(self, language: Literal["en", "zh"] = "en") -> str: ...
    def to_html(self, language: Literal["en", "zh"] = "en") -> str: ...
    def to_dict(self) -> dict: ...  # for JSON serialization / Phase 5 chat UI


def build_dossier(
    symbol: Symbol | str,
    repo: DataRepository,
    asof: date | None = None,
    peers_n: int = 5,
) -> Dossier: ...
```

### 4.4 Owner-earnings helper (reusable)

```python
# analysis/owner_earnings.py

def owner_earnings_series(
    fundamentals: pd.DataFrame,  # bitemporal, filtered PIT, one symbol
) -> pd.Series:
    """
    Buffett 1986 formula:
        owner_earnings = net_income + d_and_a - capex - working_capital_change

    Returns a pd.Series indexed by fiscal_year_end (last known publication_date).
    """
```

### 4.5 Valuation bands helper (reusable)

```python
# analysis/valuation_bands.py

@dataclass(frozen=True)
class ValuationBand:
    metric: Literal["pe", "pb", "ps"]
    bands: dict[str, float]             # {"p10", "p25", "p50", "p75", "p90"}
    current: float
    current_percentile: float
    window_years: int


def compute_valuation_bands(
    symbol: Symbol | str,
    repo: DataRepository,
    asof: date,
    metric: Literal["pe", "pb", "ps"],
    window_years: int = 10,
) -> ValuationBand: ...
```

### 4.6 Dividend consistency grade (reusable)

```python
# analysis/dividend_history.py

def dividend_consistency_grade(
    corporate_actions: pd.DataFrame,  # filtered to one symbol, kind="cash_dividend"
    asof: date,
    window_years: int = 10,
) -> str:
    """
    Grade per §2 D7(d):
        A: 10 consecutive years of dividends, CAGR ≥ 8%, no cuts
        B: 10 consecutive years of dividends, CAGR ≥ 0%, no cuts
        C: ≥ 7/10 years with dividend, no cuts in last 5
        D: ≥ 5/10 years with dividend
        E: ≥ 3/10 years with dividend
        F: < 3/10 years with dividend
    """
```

### 4.7 Watchlist

```python
# watchlist/store.py

from dataclasses import dataclass
from datetime import date
import pandas as pd
from ah_research.model.types import Symbol


@dataclass(frozen=True)
class Watchlist:
    name: str
    description: str | None
    symbols: list[Symbol]
    screen_conditions: dict | None          # predicate dict for auto-refresh via screener
    created_at: pd.Timestamp
    updated_at: pd.Timestamp


class WatchlistStore:
    """CRUD over the DuckDB cache. Two tables: `watchlist_definitions`, `watchlist_snapshots`."""

    def __init__(self, cache_path: Path | None = None): ...

    def create(self, name: str, symbols: list[Symbol], description: str = "",
               screen_conditions: dict | None = None) -> Watchlist: ...
    def get(self, name: str) -> Watchlist: ...
    def list_all(self) -> list[Watchlist]: ...
    def update(self, name: str, *, symbols=None, description=None,
               screen_conditions=None) -> Watchlist: ...
    def delete(self, name: str) -> None: ...

    def add_symbol(self, name: str, symbol: Symbol) -> Watchlist: ...
    def remove_symbol(self, name: str, symbol: Symbol) -> Watchlist: ...

    # Snapshot API
    def snapshot(self, name: str, repo: DataRepository,
                 asof: date | None = None) -> WatchlistSnapshot: ...
    def list_snapshots(self, name: str) -> list[date]: ...
    def get_snapshot(self, name: str, snapshot_date: date) -> WatchlistSnapshot: ...
    def diff_snapshots(self, name: str, earlier: date, later: date) -> pd.DataFrame: ...

    # YAML interop
    def export_yaml(self, name: str, path: Path) -> None: ...
    def import_yaml(self, path: Path, overwrite: bool = False) -> Watchlist: ...
```

```python
# watchlist/snapshot.py

@dataclass(frozen=True)
class WatchlistSnapshot:
    watchlist_name: str
    snapshot_date: date
    rows: pd.DataFrame   # [symbol, name, price, pe, pb, dividend_yield, roe, market_cap, sector_l1]
                         # plus derived columns if screen_conditions references them
```

**DuckDB tables (added to Phase 1's migration chain as migration #4):**

```sql
CREATE TABLE IF NOT EXISTS watchlist_definitions (
    name VARCHAR PRIMARY KEY,
    description VARCHAR,
    symbols JSON NOT NULL,                -- JSON array of symbol strings
    screen_conditions JSON,               -- predicate dict or NULL
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_snapshots (
    watchlist_name VARCHAR NOT NULL,
    snapshot_date DATE NOT NULL,
    symbol VARCHAR NOT NULL,
    metrics JSON NOT NULL,                -- {pe, pb, dividend_yield, roe, market_cap, sector_l1, price}
    PRIMARY KEY (watchlist_name, snapshot_date, symbol),
    FOREIGN KEY (watchlist_name) REFERENCES watchlist_definitions(name) ON DELETE CASCADE
);
```

**Reset semantics:** `ah init --reset-cache` (Phase 1 CLI) must NOT drop these tables. Instead, the reset helper's table-drop allowlist explicitly excludes tables prefixed `watchlist_`. Add a regression test for this.

### 4.8 Portfolio `Constructor` + `Constraint`

```python
# portfolio/constructor.py

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Callable
import pandas as pd
from ah_research.backtest.types import Signals, Weights
from ah_research.data.repository import DataRepository


@dataclass(frozen=True)
class Constraint:
    """
    A constraint is a post-processing step on weights.
    Constraints are applied in a deterministic order inside Constructor.build().
    Each constraint reports whether it bound, slacked, or was infeasible.
    """
    kind: Literal["max_weight", "min_weight", "sector_neutral_to", "tracking_error", "max_gross", "min_positions", "max_positions"]
    params: dict
    priority: int = 100  # smaller runs first; ties broken by kind order

    @classmethod
    def max_weight(cls, w: float) -> "Constraint": return cls(kind="max_weight", params={"w": w}, priority=50)

    @classmethod
    def sector_neutral_to(cls, benchmark: Literal["CSI300", "HSI"]) -> "Constraint":
        return cls(kind="sector_neutral_to", params={"benchmark": benchmark}, priority=20)

    @classmethod
    def tracking_error(cls, max_bps: int) -> "Constraint":
        return cls(kind="tracking_error", params={"max_bps": max_bps}, priority=30)

    @classmethod
    def max_gross(cls, w: float) -> "Constraint": return cls(kind="max_gross", params={"w": w}, priority=80)

    @classmethod
    def min_positions(cls, n: int) -> "Constraint": return cls(kind="min_positions", params={"n": n}, priority=90)

    @classmethod
    def max_positions(cls, n: int) -> "Constraint": return cls(kind="max_positions", params={"n": n}, priority=90)


@dataclass(frozen=True)
class ConstraintResult:
    constraint: Constraint
    status: Literal["bound", "slack", "infeasible_relaxed"]
    detail: str              # e.g. "max_weight=0.05: 3 positions capped, excess redistributed"
    relaxation: float | None  # only populated if status="infeasible_relaxed"


@dataclass(frozen=True)
class ConstructionReport:
    weights: Weights
    constraint_results: list[ConstraintResult]
    feasibility_warnings: list[str]
    input_signal_count: int
    final_position_count: int


class Constructor:
    def __init__(self, signals: Signals, repo: DataRepository, asof: date): ...

    def method(self, name: Literal["top_quantile", "top_n", "all_positive"], **kwargs) -> "Constructor": ...
    def weight_by(self, scheme: Literal["equal", "signal_proportional", "free_float_mcw", "mcw"]) -> "Constructor": ...
    def constrain(self, c: Constraint) -> "Constructor": ...
    def build(self) -> ConstructionReport: ...
```

**Execution order inside `.build()`:**
1. Apply `.method()` to select symbols.
2. Apply `.weight_by()` to assign initial weights.
3. Sort constraints by `priority` ascending; apply in order.
4. Each constraint returns a `ConstraintResult`; aggregate into `ConstructionReport`.
5. If any constraint returns `infeasible_relaxed`, emit a warning (not an error — default Phase 3 behavior is relax-and-proceed with a clear report; Phase 4 optimizer will do hard feasibility).

**Relaxation rules (heuristic, NOT optimization):**
- `max_weight` breach → floor excess, redistribute pro-rata to unbounded names.
- `sector_neutral_to` infeasible (universe misses a benchmark sector) → match each present sector to benchmark weight of that sector; absent sectors get weight 0; emit relaxation = total weight of missing sectors.
- `tracking_error` breach → shrink weights toward benchmark weights proportionally until TE ≤ target.
- `min_positions` / `max_positions` breach → tighten or loosen the selection method's count parameter and re-run. If impossible (universe smaller than `min_positions`), mark `infeasible_relaxed`.

---

## 5. Data flow

```
                    ┌──────────────────┐
                    │ DataRepository   │
                    │ (Phase 1)        │
                    └────────┬─────────┘
                             │
        ┌────────────────────┼───────────────────────┐
        │                    │                       │
        ▼                    ▼                       ▼
  ┌──────────┐         ┌────────────┐         ┌──────────────┐
  │ screener │         │ dossier    │         │ factor_study │
  │ returns  │         │ (composes  │         │ uses Signals │
  │ ScreenR. │         │  owner_e., │         │ or DataFrame │
  └────┬─────┘         │  val_bands,│         └──────┬───────┘
       │               │  div_hist) │                │
       │               └──────┬─────┘                │
       │                      │                      │
       ▼                      ▼                      ▼
  ┌────────────────────────────────────────────────────┐
  │                   Watchlist                         │
  │  store.snapshot() → WatchlistSnapshot              │
  │  uses screener for auto-refresh, dossier for rows  │
  └────────────────────────────────────────────────────┘

                  (separate pipeline)

  ┌──────────┐      ┌─────────────┐       ┌────────────────────┐
  │ Signals  │─────▶│ Constructor │──────▶│ Weights +          │
  │ (Phase 2)│      │ .method()   │       │ ConstructionReport │
  └──────────┘      │ .weight_by()│       └──────────┬─────────┘
                    │ .constrain()│                   │
                    │ .build()    │                   ▼
                    └─────────────┘          ┌────────────────┐
                                             │ run_backtest   │
                                             │ (Phase 2)      │
                                             └────────────────┘
```

---

## 6. Reproducibility

- Every `FactorReport`, `Dossier`, `WatchlistSnapshot`, and `ConstructionReport` carries a `metadata` field with `asof`, `repo_snapshot_date`, `code_version`.
- Bootstrap in factor study uses `config.random_seed` (default 42) for determinism.
- Watchlist snapshots are immutable once written; re-snapshotting at the same date raises unless `force=True`.

---

## 7. Testing strategy

### 7.1 Unit tests (one file per source module)

Each module gets a dedicated test file with the following coverage model:

- **factor_study** (`test_factor_study.py`)
  - IC computation matches scipy.stats.spearmanr on fixtures
  - Quantile returns sum correctly (Q1..Q5 = universe return when value-weighted)
  - NW t-stat matches statsmodels reference (reuse `backtest.metrics` helper)
  - Block bootstrap: CI width shrinks as `n_resamples` grows; seed determinism holds
  - Sector-neutralization removes industry IC from a sector-only signal (idempotence)
  - Inline DataFrame adapter: `factor_study(df, ...)` ≡ `factor_study(_InlineSignalStrategy(df), ...)`

- **screener** (`test_screener.py`)
  - Each operator produces correct boolean mask
  - `between` edge cases (lo==hi, lo>hi raises)
  - `in` / `not_in` with list vs. set
  - Derived columns computed only when referenced
  - Empty result handling (n_passed=0 returns empty frame, no error)
  - Schema validation: non-existent column name raises `KeyError` with suggestions

- **dossier** (`test_dossier.py`)
  - `build_dossier("600519.SH", ...)` on synthetic market returns valid `Dossier`
  - AH premium section is `None` for non-dual-listed, populated for dual-listed
  - `.to_markdown()` produces non-empty string; sections are visually separated; language="zh" uses Chinese headers
  - `.to_html()` produces valid HTML (parse with html.parser)
  - `.to_dict()` is JSON-serializable

- **owner_earnings, valuation_bands, dividend_history**: one unit test file each, fixture-driven assertions.

- **watchlist** (`test_store.py`, `test_snapshot.py`)
  - CRUD lifecycle
  - YAML export round-trip: `export → import → equal`
  - Snapshot immutability: re-snapshot same date without force raises
  - Diff across dates returns correct per-symbol deltas
  - `ah init --reset-cache` preserves watchlist tables (regression test)

- **portfolio.constructor** (`test_constructor.py`)
  - Each `Constraint.xxx(...)` factory produces correct params
  - Priority ordering drives deterministic application
  - `infeasible_relaxed` reported correctly (test with max_weight=0.001 forcing relaxation)
  - `ConstructionReport.final_position_count` correct under min_positions/max_positions constraints

### 7.2 Integration tests

- `test_end_to_end_factor_study.py` — runs full factor study on ValueFactorStrategy from Phase 2 over synthetic market, asserts FactorReport shape + non-trivial values
- `test_end_to_end_screener_to_watchlist.py` — screener → watchlist.create → snapshot → diff → asserts flow works
- `test_end_to_end_dossier.py` — build dossier on one A-share + one HK symbol + one AH pair leg, check all sections populate

### 7.3 Property tests (hypothesis)

- Screener: mask idempotence (`run_screen` twice with same inputs → equal results)
- Constructor: if all constraints slack, output weights sum to 1.0 within 1e-6
- Factor study: shuffling signal ranks should zero IC (within bootstrap noise band)

### 7.4 Coverage target

- `analysis/`: ≥ 90% line coverage
- `watchlist/`: ≥ 90%
- `portfolio/constructor.py`: ≥ 90%
- `mypy --strict` clean on all new modules
- `ruff check` clean

---

## 8. Error handling and edge cases

- **Symbol not in repo / delisted before `asof`** → `build_dossier` raises `ValueError` with suggestion ("Symbol 600000.SH was delisted on 2021-04-15; try asof on or before that date").
- **Insufficient valuation-band history** (< `window_years` of data) → `ValuationBand.window_years` reports actual window; emit warning in `Dossier.metadata.warnings`.
- **Zero-dividend history** in dividend_consistency → grade "F" with detail "no cash dividends in window".
- **Factor study with < 10 rebalance dates** → raise, NW t-stats unreliable below that count.
- **Constructor with empty signals** → `ConstructionReport.final_position_count == 0`, empty Weights, warning.
- **Watchlist name collision on create** → raise `ValueError`; `update()` is explicit.
- **Missing sector for HK symbol** → fallback `"Unknown"`, warn once per backtest, don't error.
- **Screener condition referencing nonexistent column** → `KeyError` listing available columns, close matches.
- **DuckDB concurrency on watchlist**: use DuckDB's single-writer model; if lock contention, retry 3× with exponential backoff, then raise.

---

## 9. CLI extension

```
ah dossier <symbol> [--asof YYYY-MM-DD] [--out path.md] [--language en|zh]
ah watchlist list
ah watchlist create <name> --symbols 600000.SH,000001.SZ [--from-screen screen.yaml]
ah watchlist snapshot <name> [--asof YYYY-MM-DD]
ah watchlist diff <name> --earlier YYYY-MM-DD --later YYYY-MM-DD
ah watchlist export <name> --to path.yaml
ah watchlist import path.yaml [--overwrite]
```

All commands delegate to the underlying Python API; CLI is a thin wrapper.

---

## 10. Deliverables and definition of done

- [ ] `src/ah_research/analysis/` (6 modules + `__init__.py`)
- [ ] `src/ah_research/watchlist/` (3 modules + `__init__.py`)
- [ ] `src/ah_research/portfolio/constructor.py` (new)
- [ ] `src/ah_research/scripts/ah_dossier.py` + CLI entry points for watchlist sub-commands
- [ ] DuckDB migration #4 (watchlist tables) added to Phase 1 chain
- [ ] 4 reference notebooks in `notebooks/`
- [ ] Unit + integration + property tests green; coverage ≥ 90% on new modules
- [ ] `mypy --strict` clean on new modules
- [ ] `ruff check` clean
- [ ] No new runtime dependencies (all implementable with existing: pandas, numpy, scipy, statsmodels, duckdb, pyyaml, typer)
- [ ] CHANGELOG updated with Phase 3 entry
- [ ] README updated with Phase 3 section + notebook links
- [ ] Spec file (this doc) + plan file referenced from README

---

## 11. Future extensions anticipated

Called out so interfaces don't paint us into a corner:

1. **Phase 4 optimizer integration** — `Constructor.build()` will branch on a new `mode="optimize"` parameter, routing to a CVXPY-based solver that respects the same `Constraint` objects.
2. **Multi-factor combination** — `factor_study` accepting a list of signals for orthogonalized multi-factor studies (Fama-MacBeth regression). Reserve a `signals: SignalStrategy | list[SignalStrategy] | pd.DataFrame` type but only implement single-signal in Phase 3.
3. **Watchlist change alerts** — Phase 5+ will add a daemon that diffs snapshots and emits notifications. Schema already supports this via the snapshot history.
4. **Forward-looking valuation bands** — requires analyst-estimate data source; add `pe_forward_ntm` field to `ValuationBandsSection` in Phase 3 as optional (None) for future population.
5. **`ah ask` natural-language query** (Phase 4–5) — reads Dossier.to_dict() / WatchlistStore programmatically.

---

## Appendix A — API sketch for users

```python
from datetime import date
from ah_research.data import DataRepository
from ah_research.analysis import factor_study, run_screen, build_dossier
from ah_research.portfolio import Constructor, Constraint
from ah_research.strategies import ValueFactorStrategy
from ah_research.watchlist import WatchlistStore

repo = DataRepository.from_default_cache()

# 1. Factor study
fr = factor_study(
    ValueFactorStrategy(), repo,
    start=date(2016, 1, 1), end=date(2025, 12, 31),
)
print(fr.ic_summary)
print(fr.bootstrap_q5_minus_q1)

# 2. Screener
result = run_screen(
    conditions={
        "pe": ("<", 15),
        "dividend_yield": (">", 0.03),
        "roe_3y_avg": (">", 0.10),
        "is_stock_connect_eligible": ("==", True),
    },
    repo=repo,
    asof=date(2025, 6, 30),
    universe="CSI300",
)
print(f"{result.n_passed}/{result.n_input} names passed")

# 3. Dossier
d = build_dossier("601318.SH", repo, asof=date(2025, 6, 30))
print(d.to_markdown(language="zh"))
print(d.valuation_bands.pe_current_percentile)  # structured access

# 4. Watchlist
store = WatchlistStore()
wl = store.create("high_dividend_value", symbols=result.frame["symbol"].tolist(),
                  screen_conditions=result.conditions_applied)
snap = store.snapshot("high_dividend_value", repo, asof=date(2025, 6, 30))
print(snap.rows)

# 5. Portfolio construction
signals = ValueFactorStrategy().generate(repo, date(2025, 6, 30), date(2025, 6, 30))
report = (
    Constructor(signals, repo=repo, asof=date(2025, 6, 30))
    .method("top_quantile", quantile=0.2)
    .weight_by("free_float_mcw")
    .constrain(Constraint.max_weight(0.05))
    .constrain(Constraint.sector_neutral_to("CSI300"))
    .build()
)
print(report.weights.df)
for cr in report.constraint_results:
    print(f"{cr.constraint.kind}: {cr.status} — {cr.detail}")
```
