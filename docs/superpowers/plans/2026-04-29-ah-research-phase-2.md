# Phase 2 — Backtest Engine & Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2 backtest engine, portfolio-construction utilities, three reference strategies, a four-function `verify.py` module, and an acceptance notebook — matching `docs/superpowers/specs/2026-04-29-ah-research-phase-2-backtest-design.md`.

**Architecture:** Event-driven daily-loop engine (not vectorized matrix). Two Strategy Protocols (`SignalStrategy` + `WeightStrategy`) dispatched by `run_backtest`. Per-exchange asymmetric `CostModel`. Rigorous `verify.py` with three-type leakage canary and random-universe survivorship baseline. Results carry a `config_hash` for reproducibility.

**Tech Stack:** Python 3.11, pandas 2.2+, numpy, pyarrow, pandera, duckdb, statsmodels (new), pytest, hypothesis, mypy --strict, ruff.

**Working directory:** `/Users/brian_huang/repos/ah-research`.

---

## How to read this plan

- **TDD throughout**: write failing test → run it → implement minimum → run tests → commit.
- **Each task commits once** at its end. No partial commits inside a task.
- **All commits must pass pre-commit hooks** (ruff, ruff format, mypy). If a hook fails, fix the underlying issue — never use `--no-verify`.
- **Every new module gets a single-line docstring at top** plus individual function docstrings only where behavior is non-obvious.
- **All text is English.** The spec has the authoritative decision rationale; plan tasks just implement.
- **Type everything.** `mypy --strict` must pass. Use `Decimal` for money, `int` for shares, `date` for dates.
- **Before starting a task**, re-read the relevant spec section (cited in each task).

---

## File structure (locked)

New:
```
src/ah_research/
├── backtest/
│   ├── __init__.py          # public re-exports
│   ├── types.py             # Weights, Signals, BacktestConfig, BacktestResult, Order, Trade, Position
│   ├── costs.py             # CostModel, CostModelBundle, DEFAULT_COSTS_2024, compute()
│   ├── metrics.py           # MetricsBundle + compute_metrics(), including Newey-West
│   ├── engine.py            # run_backtest daily loop
│   └── verify.py            # walk_forward, sensitivity, leakage_canary, survivorship_check
├── portfolio/
│   ├── __init__.py
│   └── construction.py      # top_quantile_weights, sector_neutralize, cap_at, signal_to_weights
├── strategies/
│   ├── __init__.py
│   ├── base.py              # SignalStrategy, WeightStrategy Protocols
│   ├── value_factor.py
│   ├── dividend_yield.py
│   └── ah_premium_mr.py
```

Extend existing:
```
src/ah_research/model/types.py     # add Freq, FillPrice, Settlement, DividendPolicy, OrderSide literals
src/ah_research/model/schemas.py   # add SignalsSchema, WeightsSchema
pyproject.toml                     # add statsmodels >= 0.14
CHANGELOG.md                       # Phase 2 entry (or create)
README.md                          # add link to Phase 2 spec & plan (if not present)
```

New test folders:
```
tests/unit/backtest/
tests/unit/portfolio/
tests/unit/strategies/
tests/integration/
tests/property/
tests/fixtures/phase2/             # small Parquet fixtures for integration tests
```

New notebook:
```
notebooks/phase2_acceptance.ipynb
```

---

## Task 0: Create feature branch

**Files:** none (git only).

- [ ] **Step 1: Create and switch to the feature branch**

```bash
cd /Users/brian_huang/repos/ah-research
git checkout -b feat/phase-2-backtest
git status
```

Expected: `On branch feat/phase-2-backtest` with a clean tree.

- [ ] **Step 2: Push branch tracking**

```bash
git push -u origin feat/phase-2-backtest
```

Expected: remote branch created.

---

## Task 1: Add `statsmodels` dependency and skeleton packages

**Spec ref:** §3 (module layout), §2 D9 (statsmodels dep).

**Files:**
- Modify: `pyproject.toml` (add dep)
- Create: `src/ah_research/backtest/__init__.py`
- Create: `src/ah_research/portfolio/__init__.py`
- Create: `src/ah_research/strategies/__init__.py`
- Create: `tests/unit/backtest/__init__.py`
- Create: `tests/unit/portfolio/__init__.py`
- Create: `tests/unit/strategies/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/property/__init__.py`

- [ ] **Step 1: Add statsmodels to pyproject.toml dependencies**

In `pyproject.toml` under `[project].dependencies`, add `"statsmodels>=0.14"` right after `"pandera[pandas]>=0.20"`.

- [ ] **Step 2: Install the new dep**

```bash
uv sync
# or: pip install -e .
python -c "import statsmodels.api as sm; print(sm.__version__)"
```

Expected: prints `0.14.*` or higher.

- [ ] **Step 3: Create empty `__init__.py` files for the new packages**

All files contain just a module docstring and nothing else:

```python
"""Backtest engine, costs, metrics, and verification."""
```

(Vary the docstring per package: `"""Portfolio construction utilities."""`, `"""Reference strategies."""`, etc.)

- [ ] **Step 4: Verify imports work**

```bash
python -c "from ah_research import backtest, portfolio, strategies; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ah_research/{backtest,portfolio,strategies}/__init__.py \
        tests/unit/{backtest,portfolio,strategies}/__init__.py \
        tests/integration/__init__.py tests/property/__init__.py
git commit -m "feat(phase-2): add statsmodels dep and skeleton packages

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Add literal/enum extensions to `model/types.py`

**Spec ref:** §4.1.

**Files:**
- Modify: `src/ah_research/model/types.py`
- Test: `tests/unit/test_model_types.py` (exists; extend)

- [ ] **Step 1: Write failing tests for the new literals**

Append to `tests/unit/test_model_types.py`:

```python
from typing import get_args
from ah_research.model.types import (
    Freq,
    FillPrice,
    Settlement,
    DividendPolicy,
    OrderSide,
)

def test_freq_values():
    assert set(get_args(Freq)) == {"D", "W", "M", "Q"}

def test_fill_price_values():
    assert set(get_args(FillPrice)) == {"next_open", "next_vwap", "next_close"}

def test_settlement_values():
    assert set(get_args(Settlement)) == {"auto", "T+0", "T+1", "T+2"}

def test_dividend_policy_values():
    assert set(get_args(DividendPolicy)) == {"reinvest", "cash"}

def test_order_side_values():
    assert set(get_args(OrderSide)) == {"buy", "sell", "short", "cover"}
```

- [ ] **Step 2: Run tests — confirm ImportError**

```bash
pytest tests/unit/test_model_types.py -x -q
```

Expected: fails with `ImportError: cannot import name 'Freq'`.

- [ ] **Step 3: Add the literals to `model/types.py`**

Append (after existing exports):

```python
from typing import Literal

Freq = Literal["D", "W", "M", "Q"]
FillPrice = Literal["next_open", "next_vwap", "next_close"]
Settlement = Literal["auto", "T+0", "T+1", "T+2"]
DividendPolicy = Literal["reinvest", "cash"]
OrderSide = Literal["buy", "sell", "short", "cover"]

__all__ = [
    # ... (preserve existing), append:
    "Freq", "FillPrice", "Settlement", "DividendPolicy", "OrderSide",
]
```

- [ ] **Step 4: Run tests — confirm pass**

```bash
pytest tests/unit/test_model_types.py -x -q && mypy src/ah_research/model/types.py
```

Expected: all tests pass; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/model/types.py tests/unit/test_model_types.py
git commit -m "feat(phase-2): add Freq/FillPrice/Settlement/DividendPolicy/OrderSide literals

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Add `SignalsSchema` and `WeightsSchema`; define `Signals`/`Weights` wrappers

**Spec ref:** §4.2.

**Files:**
- Modify: `src/ah_research/model/schemas.py`
- Create: `src/ah_research/backtest/types.py`
- Test: `tests/unit/backtest/test_types_signals_weights.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/backtest/test_types_signals_weights.py`:

```python
from datetime import date
import pandas as pd
import pytest
from ah_research.backtest.types import Signals, Weights

def test_signals_accepts_valid_df():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
        "symbol": ["600000.SH", "000001.SZ"],
        "signal": [0.1, -0.2],
    })
    s = Signals.from_dataframe(df)
    assert len(s.df) == 2

def test_signals_rejects_bad_symbol():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02"]),
        "symbol": ["BADSYM"],
        "signal": [0.1],
    })
    with pytest.raises(Exception):  # pandera SchemaError
        Signals.from_dataframe(df)

def test_signals_rejects_dupes():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
        "symbol": ["600000.SH", "600000.SH"],
        "signal": [0.1, 0.2],
    })
    with pytest.raises(Exception):
        Signals.from_dataframe(df)

def test_weights_allows_negative_weight():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
        "symbol": ["600000.SH", "0001.HK"],
        "weight": [0.5, -0.5],
    })
    w = Weights.from_dataframe(df)
    assert w.df["weight"].sum() == 0.0

def test_weights_rejects_nan():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02"]),
        "symbol": ["600000.SH"],
        "weight": [float("nan")],
    })
    with pytest.raises(Exception):
        Weights.from_dataframe(df)
```

- [ ] **Step 2: Run — confirm fail**

```bash
pytest tests/unit/backtest/test_types_signals_weights.py -x -q
```

Expected: fails (module missing).

- [ ] **Step 3: Add schemas in `model/schemas.py`**

Append:

```python
class SignalsSchema(pa.DataFrameModel):
    date: Series[pa.DateTime]
    symbol: Series[str] = pa.Field(str_matches=r"^[0-9]{4,6}\.(SH|SZ|HK)$")
    signal: Series[float] = pa.Field(nullable=False)

    class Config:
        strict = True
        unique = ["date", "symbol"]

class WeightsSchema(pa.DataFrameModel):
    date: Series[pa.DateTime]
    symbol: Series[str] = pa.Field(str_matches=r"^[0-9]{4,6}\.(SH|SZ|HK)$")
    weight: Series[float] = pa.Field(nullable=False)

    class Config:
        strict = True
        unique = ["date", "symbol"]
```

- [ ] **Step 4: Create `backtest/types.py` with wrappers**

```python
"""Data carriers for the backtest engine."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from ah_research.model.schemas import SignalsSchema, WeightsSchema


@dataclass(frozen=True)
class Signals:
    df: pd.DataFrame

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "Signals":
        validated = SignalsSchema.validate(df)
        return cls(df=validated)


@dataclass(frozen=True)
class Weights:
    df: pd.DataFrame

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "Weights":
        validated = WeightsSchema.validate(df)
        return cls(df=validated)
```

- [ ] **Step 5: Run — confirm pass**

```bash
pytest tests/unit/backtest/test_types_signals_weights.py -x -q && \
mypy src/ah_research/backtest/types.py src/ah_research/model/schemas.py
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/ah_research/backtest/types.py src/ah_research/model/schemas.py \
        tests/unit/backtest/test_types_signals_weights.py
git commit -m "feat(phase-2): add Signals/Weights wrappers with pandera schemas

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Add `BacktestConfig`, `Order`, `Trade`, `Position`, `BacktestResult` dataclasses

**Spec ref:** §4.4.

**Files:**
- Modify: `src/ah_research/backtest/types.py`
- Test: `tests/unit/backtest/test_types_dataclasses.py`

- [ ] **Step 1: Failing test — config and hash are deterministic**

```python
# tests/unit/backtest/test_types_dataclasses.py
from datetime import date
from decimal import Decimal
import pandas as pd
import pytest
from ah_research.backtest.types import (
    BacktestConfig, Order, Trade, Position, BacktestResult, Signals, Weights,
)
from ah_research.model.types import Currency, Exchange, OrderSide, Symbol


def _symbol(code: str = "600000.SH") -> Symbol:
    from ah_research.model.types import parse_symbol
    return parse_symbol(code)


def test_config_is_frozen():
    cfg = BacktestConfig(
        start=date(2020, 1, 1),
        end=date(2020, 12, 31),
        initial_cash=Decimal("100000"),
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        cfg.start = date(2019, 1, 1)  # type: ignore[misc]


def test_config_hash_is_stable():
    cfg1 = BacktestConfig(
        start=date(2020, 1, 1), end=date(2020, 12, 31),
        initial_cash=Decimal("100000"),
    )
    cfg2 = BacktestConfig(
        start=date(2020, 1, 1), end=date(2020, 12, 31),
        initial_cash=Decimal("100000"),
    )
    from ah_research.backtest.types import hash_config
    assert hash_config(cfg1) == hash_config(cfg2)


def test_config_hash_changes_with_input():
    cfg1 = BacktestConfig(
        start=date(2020, 1, 1), end=date(2020, 12, 31),
        initial_cash=Decimal("100000"),
    )
    cfg2 = BacktestConfig(
        start=date(2020, 1, 1), end=date(2020, 12, 31),
        initial_cash=Decimal("200000"),  # different
    )
    from ah_research.backtest.types import hash_config
    assert hash_config(cfg1) != hash_config(cfg2)


def test_order_and_trade_dataclasses_instantiate():
    o = Order(ready_date=date(2024, 1, 2), symbol=_symbol(), side="buy", shares=100)
    t = Trade(
        exec_date=date(2024, 1, 3), symbol=_symbol(), side="buy", shares=100,
        fill_price=Decimal("10.50"), notional=Decimal("1050.00"),
        cost_total=Decimal("1.05"), cost_breakdown={"commission": Decimal("1.05")},
    )
    assert o.shares == 100
    assert t.cost_breakdown["commission"] == Decimal("1.05")


def test_position_has_lock():
    p = Position(symbol=_symbol(), shares=100, avg_cost=Decimal("10.00"),
                 locked_until=date(2024, 1, 3))
    assert p.locked_until == date(2024, 1, 3)
```

- [ ] **Step 2: Run — confirm fail**

```bash
pytest tests/unit/backtest/test_types_dataclasses.py -x -q
```

- [ ] **Step 3: Implement the dataclasses**

Append to `src/ah_research/backtest/types.py`:

```python
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
import pandas as pd
from ah_research.model.types import (
    Currency, Exchange, Freq, FillPrice, Settlement, DividendPolicy,
    OrderSide, Symbol,
)


BenchmarkSpec = str | pd.Series  # "CSI300_TR" | "HSI_TR" | "zero" | pd.Series


@dataclass(frozen=True)
class BacktestConfig:
    start: date
    end: date
    initial_cash: Decimal
    base_currency: Currency = Currency.CNY
    rebalance: Freq = "M"
    fill_price: FillPrice = "next_open"
    settlement: Settlement = "auto"
    dividend_policy: DividendPolicy = "reinvest"
    benchmark: BenchmarkSpec = "CSI300_TR"
    cost_model: "CostModelBundle | None" = None
    allow_leverage: bool = False
    allow_short: bool = True
    a_share_short_allowed: bool = False
    random_seed: int = 42


@dataclass(frozen=True)
class Order:
    ready_date: date
    symbol: Symbol
    side: OrderSide
    shares: int


@dataclass(frozen=True)
class Trade:
    exec_date: date
    symbol: Symbol
    side: OrderSide
    shares: int
    fill_price: Decimal
    notional: Decimal
    cost_total: Decimal
    cost_breakdown: dict[str, Decimal]


@dataclass(frozen=True)
class Position:
    symbol: Symbol
    shares: int
    avg_cost: Decimal
    locked_until: date | None = None


@dataclass(frozen=True)
class BacktestResult:
    config: BacktestConfig
    config_hash: str
    code_version: str
    equity_curve: pd.Series
    benchmark_curve: pd.Series
    returns: pd.Series
    positions_history: pd.DataFrame
    trades: pd.DataFrame
    rejected_orders: pd.DataFrame
    cash_history: pd.DataFrame
    metrics: "MetricsBundle"  # forward ref; defined in metrics.py


def hash_config(cfg: BacktestConfig) -> str:
    """SHA-256 of canonical JSON of the config (excludes pd.Series benchmark)."""
    payload = {
        "start": cfg.start.isoformat(),
        "end": cfg.end.isoformat(),
        "initial_cash": str(cfg.initial_cash),
        "base_currency": str(cfg.base_currency),
        "rebalance": cfg.rebalance,
        "fill_price": cfg.fill_price,
        "settlement": cfg.settlement,
        "dividend_policy": cfg.dividend_policy,
        "benchmark": cfg.benchmark if isinstance(cfg.benchmark, str) else "<Series>",
        "allow_leverage": cfg.allow_leverage,
        "allow_short": cfg.allow_short,
        "a_share_short_allowed": cfg.a_share_short_allowed,
        "random_seed": cfg.random_seed,
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
```

Note: `CostModelBundle` and `MetricsBundle` are forward refs resolved later. Use `from __future__ import annotations` at top of file to allow string-form annotations.

- [ ] **Step 4: Run — confirm pass**

```bash
pytest tests/unit/backtest/test_types_dataclasses.py -x -q
mypy src/ah_research/backtest/types.py
```

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/backtest/types.py tests/unit/backtest/test_types_dataclasses.py
git commit -m "feat(phase-2): add BacktestConfig/Order/Trade/Position/BacktestResult + hash_config

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Implement `CostModel`, `CostModelBundle`, and `DEFAULT_COSTS_2024`

**Spec ref:** §4.5.

**Files:**
- Create: `src/ah_research/backtest/costs.py`
- Test: `tests/unit/backtest/test_costs.py`

- [ ] **Step 1: Failing tests — asymmetric stamp tax for SH vs HK**

```python
# tests/unit/backtest/test_costs.py
from decimal import Decimal
from ah_research.backtest.costs import (
    CostModel, CostModelBundle, DEFAULT_COSTS_2024,
)
from ah_research.model.types import Exchange


def test_default_sh_buy_has_no_stamp():
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.SH)
    breakdown = cm.compute(side="buy", notional_local=Decimal("10000"))
    assert breakdown["stamp"] == Decimal("0")

def test_default_sh_sell_has_stamp():
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.SH)
    breakdown = cm.compute(side="sell", notional_local=Decimal("10000"))
    # stamp_sell_bps=5 → 10000 * 5 / 10000 = 5
    assert breakdown["stamp"] == Decimal("5")

def test_default_hk_buy_and_sell_both_have_stamp():
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.HK)
    for side in ("buy", "sell"):
        b = cm.compute(side=side, notional_local=Decimal("10000"))
        assert b["stamp"] > Decimal("0")

def test_commission_min_clamp():
    # A tiny trade should clamp to commission_min, not compute as bps
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.SH)
    b = cm.compute(side="buy", notional_local=Decimal("100"))
    # bps commission on 100 @ 2.5bp = 0.025, but min is 5
    assert b["commission"] == Decimal("5")

def test_cost_total_is_sum_of_breakdown():
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.HK)
    b = cm.compute(side="sell", notional_local=Decimal("10000"))
    assert sum(b.values()) == b["commission"] + b["stamp"] + b["transfer"] + b["exchange_fee"]
```

- [ ] **Step 2: Run — confirm fail**

```bash
pytest tests/unit/backtest/test_costs.py -x -q
```

- [ ] **Step 3: Implement `costs.py`**

```python
"""Transaction-cost model: per-exchange, asymmetric, 2024 baseline."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from ah_research.model.types import Exchange, OrderSide


@dataclass(frozen=True)
class CostModel:
    exchange: Exchange
    commission_bps: float
    commission_min_local: Decimal
    stamp_buy_bps: float
    stamp_sell_bps: float
    transfer_bps: float
    exchange_fee_bps: float
    slippage_bps: float
    valid_from: date | None = None

    def compute(self, side: OrderSide, notional_local: Decimal) -> dict[str, Decimal]:
        bps = Decimal("10000")
        commission_raw = notional_local * Decimal(str(self.commission_bps)) / bps
        commission = max(commission_raw, self.commission_min_local)
        if side in ("buy", "cover"):
            stamp = notional_local * Decimal(str(self.stamp_buy_bps)) / bps
        else:
            stamp = notional_local * Decimal(str(self.stamp_sell_bps)) / bps
        transfer = notional_local * Decimal(str(self.transfer_bps)) / bps
        exchange_fee = notional_local * Decimal(str(self.exchange_fee_bps)) / bps
        return {
            "commission": commission,
            "stamp": stamp,
            "transfer": transfer,
            "exchange_fee": exchange_fee,
        }


@dataclass(frozen=True)
class CostModelBundle:
    models: dict[Exchange, CostModel]

    def for_exchange(self, exchange: Exchange) -> CostModel:
        return self.models[exchange]


DEFAULT_COSTS_2024 = CostModelBundle(
    models={
        Exchange.SH: CostModel(
            exchange=Exchange.SH, commission_bps=2.5, commission_min_local=Decimal("5"),
            stamp_buy_bps=0, stamp_sell_bps=5, transfer_bps=0.1,
            exchange_fee_bps=0.341, slippage_bps=5,
        ),
        Exchange.SZ: CostModel(
            exchange=Exchange.SZ, commission_bps=2.5, commission_min_local=Decimal("5"),
            stamp_buy_bps=0, stamp_sell_bps=5, transfer_bps=0.1,
            exchange_fee_bps=0.341, slippage_bps=5,
        ),
        Exchange.HK: CostModel(
            exchange=Exchange.HK, commission_bps=20, commission_min_local=Decimal("50"),
            stamp_buy_bps=10, stamp_sell_bps=10, transfer_bps=2.65,
            exchange_fee_bps=0.565, slippage_bps=10,
        ),
    }
)
```

- [ ] **Step 4: Run — confirm pass**

```bash
pytest tests/unit/backtest/test_costs.py -x -q && mypy src/ah_research/backtest/costs.py
```

- [ ] **Step 5: Wire `CostModelBundle` into `BacktestConfig` forward ref**

In `backtest/types.py`, change the top-level `from __future__ import annotations` (already present) to guarantee the forward reference resolves, and add at bottom of `backtest/types.py`:

```python
from ah_research.backtest.costs import CostModel, CostModelBundle  # noqa: E402,F401
```

- [ ] **Step 6: Commit**

```bash
git add src/ah_research/backtest/costs.py src/ah_research/backtest/types.py \
        tests/unit/backtest/test_costs.py
git commit -m "feat(phase-2): add CostModel, CostModelBundle, DEFAULT_COSTS_2024

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: `portfolio/construction.py` — `top_quantile_weights`, `cap_at`, `sector_neutralize`, `signal_to_weights`

**Spec ref:** §3 (portfolio module), §8 (use by ValueFactor, DividendYield).

**Files:**
- Create: `src/ah_research/portfolio/construction.py`
- Test: `tests/unit/portfolio/test_construction.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/portfolio/test_construction.py
import pandas as pd
import numpy as np
import pytest
from ah_research.portfolio.construction import (
    top_quantile_weights, cap_at, sector_neutralize, signal_to_weights,
)


def _signals(values: dict[str, float], d="2024-01-31") -> pd.DataFrame:
    rows = [{"date": pd.Timestamp(d), "symbol": s, "signal": v} for s, v in values.items()]
    return pd.DataFrame(rows)


def test_top_quantile_selects_top_20pct():
    sig = _signals({f"60000{i}.SH": float(i) for i in range(10)})
    out = top_quantile_weights(sig, quantile=0.2)
    # top 2 of 10 = symbols with signals 8 and 9
    assert set(out["symbol"]) == {"600008.SH", "600009.SH"}
    # equal weight
    assert np.allclose(out["weight"].to_numpy(), 0.5)


def test_cap_at_caps_and_redistributes():
    # sum to 1 but single weight > cap
    w = pd.DataFrame({
        "date": pd.Timestamp("2024-01-31"),
        "symbol": ["a", "b", "c"],
        "weight": [0.6, 0.3, 0.1],
    })
    out = cap_at(w, max_weight=0.4)
    # a capped at 0.4, residue 0.2 redistributed pro-rata to b and c
    assert out.loc[out.symbol == "a", "weight"].item() == pytest.approx(0.4)
    assert out["weight"].sum() == pytest.approx(1.0)


def test_sector_neutralize_equalizes_sector_exposure():
    w = pd.DataFrame({
        "date": pd.Timestamp("2024-01-31"),
        "symbol": ["a", "b", "c", "d"],
        "weight": [0.5, 0.3, 0.1, 0.1],
    })
    sectors = pd.DataFrame({
        "symbol": ["a", "b", "c", "d"],
        "sector_l1": ["tech", "tech", "finance", "finance"],
    })
    out = sector_neutralize(w, sectors)
    # after neutralization, each sector has equal total weight = 0.5
    merged = out.merge(sectors, on="symbol")
    sector_sums = merged.groupby("sector_l1")["weight"].sum()
    assert np.allclose(sector_sums["tech"], sector_sums["finance"])


def test_signal_to_weights_top_quantile_composite():
    sig = _signals({f"60000{i}.SH": float(i) for i in range(10)})
    out = signal_to_weights(sig, method="top_quantile", quantile=0.2, max_weight=0.6)
    # 2 names, equal weight 0.5 each, both below cap 0.6 — untouched
    assert len(out) == 2
    assert all(out["weight"] == 0.5)
```

- [ ] **Step 2: Run — confirm fail**

```bash
pytest tests/unit/portfolio/test_construction.py -x -q
```

- [ ] **Step 3: Implement the four functions**

```python
"""Portfolio construction primitives used by SignalStrategy.to_weights()."""
from __future__ import annotations
from typing import Literal
import pandas as pd
import numpy as np


def top_quantile_weights(
    signals: pd.DataFrame,
    quantile: float,
    long_only: bool = True,
) -> pd.DataFrame:
    """Select top `quantile` by signal per date; equal-weight."""
    if not 0 < quantile <= 1.0:
        raise ValueError(f"quantile must be in (0, 1], got {quantile}")
    out_rows: list[pd.DataFrame] = []
    for d, grp in signals.groupby("date"):
        n = len(grp)
        k = max(1, int(round(n * quantile)))
        top = grp.nlargest(k, "signal").copy()
        top["weight"] = 1.0 / k
        out_rows.append(top[["date", "symbol", "weight"]])
    return pd.concat(out_rows, ignore_index=True)


def cap_at(weights: pd.DataFrame, max_weight: float) -> pd.DataFrame:
    """Cap each weight at `max_weight`; redistribute excess pro-rata to uncapped names."""
    result: list[pd.DataFrame] = []
    for d, grp in weights.groupby("date"):
        w = grp["weight"].to_numpy().copy()
        while True:
            over = w > max_weight
            if not over.any():
                break
            excess = (w[over] - max_weight).sum()
            w[over] = max_weight
            under_mask = (w < max_weight) & (w > 0)
            if not under_mask.any():
                # nothing to distribute into; break
                break
            under_sum = w[under_mask].sum()
            if under_sum == 0:
                break
            w[under_mask] += excess * (w[under_mask] / under_sum)
        new = grp.copy()
        new["weight"] = w
        result.append(new)
    return pd.concat(result, ignore_index=True)


def sector_neutralize(weights: pd.DataFrame, sectors: pd.DataFrame) -> pd.DataFrame:
    """Rescale weights within each sector to equal-sector totals."""
    merged = weights.merge(sectors[["symbol", "sector_l1"]], on="symbol", how="left")
    results = []
    for d, grp in merged.groupby("date"):
        sector_counts = grp.groupby("sector_l1")["weight"].transform("sum")
        n_sectors = grp["sector_l1"].nunique()
        target_sector_weight = 1.0 / n_sectors
        grp = grp.copy()
        grp["weight"] = grp["weight"] / sector_counts * target_sector_weight
        results.append(grp[["date", "symbol", "weight"]])
    return pd.concat(results, ignore_index=True)


def signal_to_weights(
    signals: pd.DataFrame,
    method: Literal["top_quantile"],
    quantile: float = 0.2,
    max_weight: float = 0.05,
    sector_neutral: bool = False,
    sectors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compose: top_quantile → sector_neutralize? → cap_at."""
    if method != "top_quantile":
        raise NotImplementedError(f"method={method}")
    w = top_quantile_weights(signals, quantile=quantile)
    if sector_neutral:
        if sectors is None:
            raise ValueError("sector_neutral=True requires sectors DataFrame")
        w = sector_neutralize(w, sectors)
    w = cap_at(w, max_weight=max_weight)
    return w
```

- [ ] **Step 4: Run — confirm pass**

```bash
pytest tests/unit/portfolio/test_construction.py -x -q && mypy src/ah_research/portfolio/construction.py
```

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/portfolio/construction.py tests/unit/portfolio/test_construction.py
git commit -m "feat(phase-2): portfolio.construction with top_quantile/cap/neutralize/signal_to_weights

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Strategy Protocols in `strategies/base.py`

**Spec ref:** §4.3.

**Files:**
- Create: `src/ah_research/strategies/base.py`
- Test: `tests/unit/strategies/test_base.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/strategies/test_base.py
from datetime import date
import pandas as pd
from ah_research.strategies.base import SignalStrategy, WeightStrategy
from ah_research.backtest.types import Signals, Weights


class DummySignalStrategy:
    name = "dummy_signal"
    def generate(self, repo, start, end):
        df = pd.DataFrame({"date": pd.to_datetime(["2024-01-31"]),
                           "symbol": ["600000.SH"], "signal": [1.0]})
        return Signals.from_dataframe(df)
    def to_weights(self, signals):
        df = signals.df.copy()
        df["weight"] = 1.0
        df = df.drop(columns=["signal"])
        return Weights.from_dataframe(df)


class DummyWeightStrategy:
    name = "dummy_weight"
    def generate(self, repo, start, end):
        df = pd.DataFrame({"date": pd.to_datetime(["2024-01-31"]),
                           "symbol": ["600000.SH"], "weight": [0.5]})
        return Weights.from_dataframe(df)


def test_signal_strategy_protocol():
    s = DummySignalStrategy()
    assert isinstance(s, SignalStrategy)
    assert not isinstance(s, WeightStrategy)


def test_weight_strategy_protocol():
    w = DummyWeightStrategy()
    assert isinstance(w, WeightStrategy)
    assert not isinstance(w, SignalStrategy)
```

- [ ] **Step 2: Run — fail**

```bash
pytest tests/unit/strategies/test_base.py -x -q
```

- [ ] **Step 3: Implement**

```python
"""Strategy Protocols — SignalStrategy (factor) and WeightStrategy (pair/direct)."""
from __future__ import annotations
from datetime import date
from typing import Protocol, runtime_checkable
from ah_research.data.repository import DataRepository
from ah_research.backtest.types import Signals, Weights


@runtime_checkable
class SignalStrategy(Protocol):
    """Emits a per-symbol scalar signal; converted to weights via `to_weights`."""
    name: str

    def generate(self, repo: DataRepository, start: date, end: date) -> Signals: ...

    def to_weights(self, signals: Signals) -> Weights: ...


@runtime_checkable
class WeightStrategy(Protocol):
    """Emits target weights directly."""
    name: str

    def generate(self, repo: DataRepository, start: date, end: date) -> Weights: ...
```

- [ ] **Step 4: Run — pass**

```bash
pytest tests/unit/strategies/test_base.py -x -q
```

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/strategies/base.py tests/unit/strategies/test_base.py
git commit -m "feat(phase-2): Strategy Protocols (SignalStrategy + WeightStrategy)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Fixture builder for synthetic market data

**Purpose:** Integration and engine-rule tests need a deterministic tiny market. Build a helper that returns a `DataRepository`-compatible in-memory dataset plus PIT constituents, calendar, corporate actions, and FX.

**Files:**
- Create: `tests/fixtures/phase2/__init__.py`
- Create: `tests/fixtures/phase2/synthetic_market.py`
- Test: `tests/unit/backtest/test_fixture_market.py`

- [ ] **Step 1: Failing test — builder returns a repo-like object with expected methods**

```python
# tests/unit/backtest/test_fixture_market.py
from datetime import date
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_synthetic_market_returns_repo():
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 3, 31),
        symbols=["600000.SH", "0001.HK"],
    )
    prices = repo.get_prices(["600000.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert not prices.empty
    assert "close_hfq" in prices.columns
    assert "hit_limit_up" in prices.columns


def test_fixture_market_has_fx():
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 1, 31),
        symbols=["600000.SH", "0001.HK"],
    )
    fx = repo.get_fx_series("CNY_HKD", date(2024, 1, 1), date(2024, 1, 31))
    assert len(fx) > 15
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `synthetic_market.py`**

Approximately 200 lines. Build an in-memory `DataRepository` by using the existing fake-integrations layer (`integrations/fake/client.py`) if it can be configured to return synthetic data, otherwise subclass `DataRepository` with overridden `get_prices`, `get_fundamentals`, `get_universe_over_time`, `get_corporate_actions`, `get_trading_calendar`, `get_fx_series`, `get_sector`.

Deterministic random walk with seed=42: start price 10.0, daily log-return ~ Normal(0, 0.02). No halts or limits unless requested via kwargs. Schema-valid per `PriceFrameSchema`. 5-day week calendar for all exchanges. Cash dividend of 0.5/share on one chosen ex-date for one symbol.

(Executor: implement reading the `PriceFrameSchema` spec in `model/schemas.py` and producing valid rows. A 200-line fixture is acceptable; it's one-time infrastructure.)

- [ ] **Step 4: Run — pass; commit**

```bash
pytest tests/unit/backtest/test_fixture_market.py -x -q
git add tests/fixtures/phase2/ tests/unit/backtest/test_fixture_market.py
git commit -m "test(phase-2): synthetic market fixture builder

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Engine skeleton — buy next open, mark-to-market, no rules

**Spec ref:** §5.

**Files:**
- Create: `src/ah_research/backtest/engine.py`
- Test: `tests/unit/backtest/test_engine_minimal.py`

Goal: A one-symbol, single-rebalance backtest with all rules disabled (no costs, no locks, no limits). Establish the loop's bones before adding rules.

- [ ] **Step 1: Failing test**

```python
# tests/unit/backtest/test_engine_minimal.py
from datetime import date
from decimal import Decimal
import pandas as pd
from ah_research.backtest.engine import run_backtest
from ah_research.backtest.types import BacktestConfig, Weights
from ah_research.backtest.costs import CostModelBundle
from ah_research.model.types import Exchange
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


class FixedLongStrategy:
    name = "fixed_long"
    def generate(self, repo, start, end):
        # at each month-end, emit 100% weight in one symbol
        eom = pd.date_range(start, end, freq="ME")
        df = pd.DataFrame({
            "date": eom, "symbol": ["600000.SH"] * len(eom), "weight": [1.0] * len(eom),
        })
        return Weights.from_dataframe(df)


def test_minimal_run_produces_equity_curve():
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 3, 31), symbols=["600000.SH"],
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2), end=date(2024, 3, 29),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),  # empty = zero costs
    )
    result = run_backtest(FixedLongStrategy(), repo, cfg)
    assert len(result.equity_curve) > 30
    assert result.equity_curve.iloc[0] > 0
    # NAV must be finite
    assert result.equity_curve.notna().all()
    assert len(result.trades) >= 1
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `engine.py` skeleton**

This is the largest single implementation of the plan. Aim for ~300 LOC in this step. Follow the pseudocode in spec §5, but in this step:

- Skip T+N locking (implement Task 10).
- Skip limit/halt checks (implement Task 11).
- Skip dividend handling (implement Task 12).
- Skip multi-currency FX (single-exchange A-share only for this task; add HK/FX in Task 13).
- Costs respected only if `cost_model` has models; otherwise zero.

Key helper signatures:
```python
def run_backtest(strategy, repo, config) -> BacktestResult: ...
def _compute_rebalance_dates(calendar: pd.DataFrame, rebalance: Freq) -> list[date]: ...
def _round_to_lot(target_shares: float, lot_size: int) -> int: ...  # floor on buy, ceil on sell
def _get_code_version() -> str: ...  # subprocess `git rev-parse --short HEAD`
```

Use `repo.get_trading_calendar(Exchange.SH, start, end)` to drive the daily loop. For this task, assume all target symbols are SH; multi-exchange comes in Task 13.

- [ ] **Step 4: Run — pass**

```bash
pytest tests/unit/backtest/test_engine_minimal.py -x -q
mypy src/ah_research/backtest/engine.py
```

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/backtest/engine.py tests/unit/backtest/test_engine_minimal.py
git commit -m "feat(phase-2): engine skeleton — minimal daily loop with MTM

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: Engine rule — T+1 settlement lock (SH/SZ) and T+2 (HK)

**Spec ref:** §5 'Settlement resolution', §10.1 test_engine_t1_lock.

**Files:**
- Modify: `src/ah_research/backtest/engine.py`
- Test: `tests/unit/backtest/test_engine_t1_lock.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/backtest/test_engine_t1_lock.py
# Strategy: on day 1 buy 100 shares; on day 2 attempt to sell; on day 3 attempt to sell.
# Expected: day-2 sell rejected with reason="T+N lock", day-3 sell fills.

from datetime import date
# ... (full test setup; use custom strategy that emits per-day Weights flipping 1 -> 0 on day 2 vs day 3)
```

(Executor: write a weights-per-day test strategy; assert `result.rejected_orders` has one entry with `reason == "T+N lock"`.)

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement the lock rule in `engine.py`**

On fill of a buy/cover, set `position.locked_until = exec_date + settlement_days` where `settlement_days` is 1 for SH/SZ and 2 for HK (when `settlement="auto"`). Before executing a sell/short order, check `d <= position.locked_until`; if so, append to `rejected_orders` with `reason="T+N lock"`.

Use business-day arithmetic via the exchange's calendar — not calendar-day — by looking up "next N trading days from exec_date" from `repo.get_trading_calendar(exchange, ...)`.

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/unit/backtest/test_engine_t1_lock.py -x -q
git add src/ah_research/backtest/engine.py tests/unit/backtest/test_engine_t1_lock.py
git commit -m "feat(phase-2): engine — T+N settlement lock per exchange

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: Engine rules — limit-up/limit-down rejection + suspension handling

**Spec ref:** §5, §10.1.

**Files:**
- Modify: `src/ah_research/backtest/engine.py`
- Test: `tests/unit/backtest/test_engine_limits.py`, `tests/unit/backtest/test_engine_suspension.py`

- [ ] **Step 1: Failing tests**

Two tests:
1. Buy order on a day with `hit_limit_up=True` is rejected; re-queued for next day; fills when limit clears.
2. Any order on a day with `is_suspended=True` is rejected; resumes after halt ends.

(Executor: extend the fixture builder to accept injected limit/halt days.)

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement; re-queue on rejection**

After a reject for `hit_limit_up/down` or `is_suspended`, do **not** just log the reject — re-append the order to `pending_orders` so it retries next day. (For `T+N lock` rejects, do not re-queue: the lock represents a real constraint the strategy cannot override.)

Add the reason strings exactly: `"limit_up"`, `"limit_down"`, `"suspended"`, `"T+N lock"`, `"a_share_short_disallowed"`.

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/unit/backtest/test_engine_limits.py tests/unit/backtest/test_engine_suspension.py -x -q
git add src/ah_research/backtest/engine.py tests/unit/backtest/
git commit -m "feat(phase-2): engine — limit-up/down + suspension rejection with retry

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 12: Engine rule — dividend reinvestment + splits + rights

**Spec ref:** §5 'Dividend reinvestment'.

**Files:**
- Modify: `src/ah_research/backtest/engine.py`
- Test: `tests/unit/backtest/test_engine_corp_actions.py`

- [ ] **Step 1: Failing tests**

Three tests, one per action kind:
1. Cash dividend: on ex-date, `cash[symbol.currency] += shares * amount_per_share`. On next trading day, a buy order for `floor((cash_credit) / next_open / lot) * lot` is queued.
2. Split 2-for-1: on ex-date, shares double, price halves (already reflected in price data because Phase 1 repos `close_hfq`; but non-adjusted shares in `Position` need updating).
3. Rights issue: Phase 2 decision — treat as cash-dividend-equivalent and log a warning; do not exercise the right. (Spec leaves rights ambiguous; this keeps scope tight.)

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `apply_corporate_action`**

Open `repo.get_corporate_actions(universe, start, end)`; iterate by ex-date; branch on `kind`. For `cash_dividend`, credit cash; for `stock_dividend`/`split`, adjust share count; for `reverse_split`, same; for `rights_issue`/`spin_off`, log a warning.

When `config.dividend_policy == "reinvest"`: after crediting cash from a dividend, queue a buy order at tomorrow's open for all of the cash credited for that position. When `"cash"`, leave in cash.

- [ ] **Step 4: Pass + commit**

---

## Task 13: Engine — multi-currency cash, FX mark-to-market, HK lot size

**Spec ref:** §5 'Lot sizes', §8.3 AH pair needs CNY+HKD cash.

**Files:**
- Modify: `src/ah_research/backtest/engine.py`
- Test: `tests/unit/backtest/test_engine_multi_currency.py`

- [ ] **Step 1: Failing test**

```python
# A strategy holds one HK and one A-share. Base currency = CNY.
# After FX moves, the NAV changes even when local prices are constant.
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

- `cash: dict[Currency, Decimal]` tracks balance per currency. Buys debit the currency of the symbol's exchange; sells credit likewise.
- `Position.mtm_local(d) = shares * price_local[d]`. `mtm_base(d) = mtm_local(d) * fx_to_base(ccy, d)`.
- `cash_in_base(d) = sum(bal * fx_to_base(ccy, d) for ccy, bal in cash.items())`.
- Lot size: SH/SZ = 100; HK = 100 (Phase 2 simplification with warning logged once at backtest start about HK lot assumption).
- Benchmark is in base currency by construction.

- [ ] **Step 4: Pass + commit**

---

## Task 14: Engine — shorts: allow on HK, block on A-shares by default

**Spec ref:** §8.3 AH pair needs HK shorts.

**Files:**
- Modify: `src/ah_research/backtest/engine.py`
- Test: `tests/unit/backtest/test_engine_shorts.py`

- [ ] **Step 1: Failing tests**

Three tests:
1. HK short with `allow_short=True` succeeds; proceeds credited to HKD cash; `Position.shares` negative.
2. A-share short with `a_share_short_allowed=False` rejected with `reason="a_share_short_disallowed"`.
3. A-share short with `a_share_short_allowed=True` succeeds (feature-flagged for research curiosity).

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

In the order-dispatch pre-check, add the A-share short guard. For HK shorts, simply proceed; Phase 2 does **not** model borrow cost (log once per backtest run per symbol: `"HK short borrow cost ignored in Phase 2"`).

When computing NAV, a short position contributes `-shares * price * fx` to position MV and `+short_proceeds * fx` to cash (already credited at execution).

- [ ] **Step 4: Pass + commit**

---

## Task 15: Metrics — CAGR, Sharpe, Sortino, drawdown, Calmar, vol

**Spec ref:** §6 'Content'.

**Files:**
- Create: `src/ah_research/backtest/metrics.py`
- Test: `tests/unit/backtest/test_metrics_returns.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/backtest/test_metrics_returns.py
import numpy as np
import pandas as pd
from ah_research.backtest.metrics import (
    cagr, annualized_vol, sharpe, sortino, max_drawdown, calmar,
)

def test_cagr_on_flat_series():
    eq = pd.Series([100.0] * 252, index=pd.date_range("2024-01-01", periods=252, freq="B"))
    assert cagr(eq) == pytest.approx(0.0, abs=1e-9)

def test_cagr_on_doubling_over_year():
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    eq = pd.Series(100.0 * (2 ** (np.arange(252) / 252)), index=idx)
    assert cagr(eq) == pytest.approx(1.0, abs=0.01)  # 100% annualized

def test_max_drawdown():
    eq = pd.Series([100, 120, 80, 100, 110], index=pd.date_range("2024-01-01", periods=5))
    dd, duration = max_drawdown(eq)
    assert dd == pytest.approx(-0.3333, abs=1e-3)  # 120 -> 80 = -33%
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement primitives**

```python
def cagr(equity: pd.Series) -> float:
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0: return 0.0
    return (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1

def annualized_vol(returns: pd.Series, periods: int = 252) -> float:
    return float(returns.std() * np.sqrt(periods))

def sharpe(returns: pd.Series, rf: float = 0.0, periods: int = 252) -> float:
    excess = returns - rf / periods
    if excess.std() == 0: return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(periods))

def sortino(returns: pd.Series, rf: float = 0.0, periods: int = 252) -> float:
    excess = returns - rf / periods
    downside = excess[excess < 0].std()
    if downside == 0: return 0.0
    return float(excess.mean() / downside * np.sqrt(periods))

def max_drawdown(equity: pd.Series) -> tuple[float, int]:
    peak = equity.cummax()
    dd_series = (equity - peak) / peak
    trough_idx = dd_series.idxmin()
    peak_idx = equity[:trough_idx].idxmax()
    return float(dd_series.min()), int((trough_idx - peak_idx).days)

def calmar(equity: pd.Series) -> float:
    mdd, _ = max_drawdown(equity)
    if mdd == 0: return float("inf")
    return cagr(equity) / abs(mdd)
```

- [ ] **Step 4: Pass + commit**

---

## Task 16: Metrics — turnover, holdings, dividend yield, holding period

**Spec ref:** §6 'Activity' + 'Income'.

**Files:**
- Modify: `src/ah_research/backtest/metrics.py`
- Test: `tests/unit/backtest/test_metrics_activity.py`

- [ ] **Step 1: Failing tests + Step 2: fail**

```python
def test_turnover_annualized():
    trades = pd.DataFrame({
        "exec_date": pd.to_datetime(["2024-01-02", "2024-02-01"]),
        "notional": [Decimal("500"), Decimal("500")],
    })
    avg_nav = 1000.0
    t = annualized_turnover(trades, avg_nav, start=date(2024,1,1), end=date(2024,12,31))
    # Two trades @ 500 each = 1000 notional; avg NAV 1000 -> 1.0 turnover in 1 year
    assert t == pytest.approx(1.0, abs=0.05)
```

- [ ] **Step 3: Implement `annualized_turnover`, `avg_positions`, `avg_holding_period`, `avg_dividend_yield`**

- [ ] **Step 4: Pass + commit**

---

## Task 17: Metrics — benchmark-relative (α, β, excess, IR, TE) with Newey-West

**Spec ref:** §6 'Benchmark-relative' + 'Inferential'.

**Files:**
- Modify: `src/ah_research/backtest/metrics.py`
- Test: `tests/unit/backtest/test_metrics_newey_west.py`

- [ ] **Step 1: Failing test — t-stats match statsmodels reference**

```python
# Generate synthetic OLS data with known relationships; verify our wrapper matches statsmodels
import numpy as np
import statsmodels.api as sm

def test_alpha_beta_t_stats_match_statsmodels():
    rng = np.random.default_rng(42)
    rb = rng.normal(0.0005, 0.01, 1000)
    rp = 0.0002 + 1.3 * rb + rng.normal(0, 0.005, 1000)
    from ah_research.backtest.metrics import alpha_beta_newey_west

    result = alpha_beta_newey_west(
        portfolio_returns=pd.Series(rp),
        benchmark_returns=pd.Series(rb),
    )
    # Reference
    X = sm.add_constant(rb)
    ref = sm.OLS(rp, X).fit(cov_type="HAC", cov_kwds={"maxlags": int(4 * (1000/100)**(2/9))})
    assert result.alpha == pytest.approx(ref.params[0], abs=1e-10)
    assert result.beta == pytest.approx(ref.params[1], abs=1e-10)
    assert result.alpha_t_stat == pytest.approx(ref.tvalues[0], abs=1e-8)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `alpha_beta_newey_west`, `information_ratio`, `tracking_error`, `excess_return`**

```python
from dataclasses import dataclass
import statsmodels.api as sm

@dataclass(frozen=True)
class AlphaBetaNW:
    alpha: float
    beta: float
    alpha_t_stat: float
    alpha_pvalue: float
    alpha_se: float
    beta_t_stat: float
    beta_se: float

def _andrews_lag(n: int) -> int:
    return max(1, int(4 * (n / 100) ** (2 / 9)))

def alpha_beta_newey_west(portfolio_returns: pd.Series, benchmark_returns: pd.Series) -> AlphaBetaNW:
    rp, rb = portfolio_returns.align(benchmark_returns, join="inner")
    X = sm.add_constant(rb.to_numpy())
    n = len(rp)
    fit = sm.OLS(rp.to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": _andrews_lag(n)})
    return AlphaBetaNW(
        alpha=float(fit.params[0]), beta=float(fit.params[1]),
        alpha_t_stat=float(fit.tvalues[0]), alpha_pvalue=float(fit.pvalues[0]),
        alpha_se=float(fit.bse[0]),
        beta_t_stat=float(fit.tvalues[1]), beta_se=float(fit.bse[1]),
    )
```

Plus simpler helpers for IR, TE, excess_return.

- [ ] **Step 4: Pass + commit**

---

## Task 18: `MetricsBundle` + `compute_metrics(...)` aggregator

**Spec ref:** §6.

**Files:**
- Modify: `src/ah_research/backtest/metrics.py`
- Test: `tests/unit/backtest/test_metrics_bundle.py`

- [ ] **Step 1: Failing test**

```python
def test_metrics_bundle_has_all_fields():
    # Run a tiny backtest, compute metrics, assert all documented fields are present and finite.
    ...
```

- [ ] **Step 2: Implement**

Define `@dataclass(frozen=True) class MetricsBundle` with all §6 fields plus a `.to_dict()` and a `.__str__` pretty-printer. `compute_metrics(equity, benchmark, trades, cost_model, config, positions_history) -> MetricsBundle`.

Resolve the forward ref in `backtest/types.py` (`BacktestResult.metrics: "MetricsBundle"`).

- [ ] **Step 3: Pass + commit**

---

## Task 19: Engine — benchmark resolution + config_hash + code_version

**Spec ref:** §2 D8.

**Files:**
- Modify: `src/ah_research/backtest/engine.py`
- Test: `tests/unit/backtest/test_engine_result_metadata.py`

- [ ] **Step 1: Failing test — result contains populated metadata**

```python
def test_result_has_config_hash():
    result = ...  # run simple backtest
    assert len(result.config_hash) == 64
    assert result.code_version  # non-empty
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `resolve_benchmark(spec, start, end, repo) -> pd.Series`**

Branch on `spec`:
- `"CSI300_TR"` → `repo.get_prices(["000300.SH"], start, end)` (total-return version if Phase 1 exposes; else raw close with a logged warning).
- `"HSI_TR"` → `repo.get_prices(["HSI.HK"], start, end)` or equivalent.
- `"zero"` → `pd.Series(1.0, index=trading_days)`.
- `pd.Series` → use as-is (reindex to `equity_curve.index`).

Hook `config_hash` and `_get_code_version()` into `BacktestResult` at return time.

- [ ] **Step 4: Pass + commit**

---

## Task 20: Engine — error/warning paths + integration test

**Spec ref:** §11.

**Files:**
- Modify: `src/ah_research/backtest/engine.py`
- Test: `tests/integration/test_end_to_end_value_factor.py`

- [ ] **Step 1: Failing integration test — ValueFactor-like test on synthetic market produces sensible metrics**

(Use a placeholder `ValueFactorStrategy` stub that emits random weights to exercise the whole pipeline; the real strategy comes in Task 22.)

```python
def test_end_to_end_pipeline():
    repo = build_synthetic_market(start=date(2023,1,1), end=date(2024,12,31),
                                   symbols=["600000.SH", "000001.SZ"])
    class RandomWeightStrategy:
        name = "random"
        def generate(self, repo, start, end):
            ...  # emit random weights per month-end
    cfg = BacktestConfig(start=date(2023,1,1), end=date(2024,12,31),
                         initial_cash=Decimal("1000000"))
    result = run_backtest(RandomWeightStrategy(), repo, cfg)
    assert len(result.equity_curve) > 400
    assert result.metrics.cagr is not None
    assert len(result.trades) > 0
    # NAV conservation invariant holds
    ...
```

- [ ] **Step 2: Implement error paths**

Per spec §11: validate weights sum on input; raise on NaN weights; handle negative cash by raising; forward-fill benchmark gaps ≤ 3 days; warn-and-zero on delisted symbols.

- [ ] **Step 3: Pass + commit**

---

## Task 21: Property tests — NAV conservation, no-leakage, seed determinism

**Spec ref:** §10.3.

**Files:**
- Create: `tests/property/test_engine_invariants.py`

- [ ] **Step 1: Write three hypothesis tests**

```python
import pytest
from hypothesis import given, strategies as st, settings

@given(seed=st.integers(min_value=0, max_value=2**31-1),
       n_days=st.integers(min_value=20, max_value=200))
@settings(max_examples=10, deadline=30_000)
def test_nav_conservation(seed, n_days):
    # Build a random market with the seed, run a backtest, check
    # abs(cash_in_base + position_mv - equity_curve_d) < 1e-6 for every d
    ...

@given(seed=st.integers())
def test_no_leakage_shuffle_after_midpoint(seed):
    # Build market; run backtest; shuffle bars after midpoint; rerun;
    # compare equity_curve[:midpoint] byte-for-byte.
    ...

@given(seed=st.integers())
def test_determinism_same_seed_same_result(seed):
    # Run twice with same seed; assert result.equity_curve.equals(other.equity_curve)
    ...
```

- [ ] **Step 2: Run — identify any engine bugs they catch, fix, re-run**

- [ ] **Step 3: Commit**

---

## Task 22: `ValueFactorStrategy`

**Spec ref:** §8.1.

**Files:**
- Create: `src/ah_research/strategies/value_factor.py`
- Test: `tests/unit/strategies/test_value_factor.py`

- [ ] **Step 1: Failing test — strategy instantiable + returns valid Signals**

```python
def test_value_factor_returns_signals():
    repo = build_synthetic_market(...)
    s = ValueFactorStrategy(quantile=0.2)
    sigs = s.generate(repo, date(2024,1,1), date(2024,3,31))
    assert isinstance(sigs, Signals)
    # three month-ends
    assert sigs.df["date"].nunique() == 3
```

- [ ] **Step 2: Implement**

```python
"""Value factor strategy: composite rank of 1/PE, 1/PB, dividend_yield."""
from dataclasses import dataclass
from datetime import date
import pandas as pd
from ah_research.backtest.types import Signals, Weights
from ah_research.data.repository import DataRepository
from ah_research.portfolio.construction import signal_to_weights


@dataclass(frozen=True)
class ValueFactorStrategy:
    quantile: float = 0.2
    max_weight: float = 0.05
    sector_neutral: bool = True
    name: str = "value_factor"

    def generate(self, repo: DataRepository, start: date, end: date) -> Signals:
        # 1. Universe: CSI 300 PIT membership at each month-end in [start, end]
        universe = repo.get_universe_over_time("CSI300", start, end, freq="ME")
        # 2. Fundamentals as of each month-end (bitemporal PIT)
        # 3. Composite rank
        rows = []
        for d, grp in universe.groupby("date"):
            symbols = grp["symbol"].tolist()
            funds = repo.get_fundamentals(symbols, start=d, end=d, asof=d)
            if funds.empty:
                continue
            funds = funds.copy()
            funds["inv_pe"] = 1.0 / funds["pe"].replace(0, pd.NA)
            funds["inv_pb"] = 1.0 / funds["pb"].replace(0, pd.NA)
            funds["div_yield"] = funds["dividend_yield"]
            # Rank each feature, sum ranks
            funds["rank_inv_pe"] = funds["inv_pe"].rank()
            funds["rank_inv_pb"] = funds["inv_pb"].rank()
            funds["rank_div_yield"] = funds["div_yield"].rank()
            funds["signal"] = funds[["rank_inv_pe", "rank_inv_pb", "rank_div_yield"]].mean(axis=1)
            funds["date"] = d
            rows.append(funds[["date", "symbol", "signal"]])
        df = pd.concat(rows, ignore_index=True).dropna(subset=["signal"])
        return Signals.from_dataframe(df)

    def to_weights(self, signals: Signals) -> Weights:
        # Fetch sectors lazily; require a sector table injected elsewhere
        # Phase 2 decision: sector_neutralize requires explicit sectors passed via config
        df = signal_to_weights(
            signals.df, method="top_quantile",
            quantile=self.quantile, max_weight=self.max_weight,
            sector_neutral=False,  # sector neutralization applied downstream by engine pipeline
        )
        return Weights.from_dataframe(df)
```

(Executor: if spec-level sector_neutral=True is important, refactor `to_weights` to accept `repo` as an argument so sectors can be fetched. The cleanest way is to widen the Protocol: `to_weights(self, signals, repo) -> Weights`. Make this change now and update `engine.py` to pass `repo` into `to_weights`.)

- [ ] **Step 3: Pass + commit**

---

## Task 23: `DividendYieldStrategy`

**Spec ref:** §8.2.

**Files:**
- Create: `src/ah_research/strategies/dividend_yield.py`
- Test: `tests/unit/strategies/test_dividend_yield.py`

Similar structure to Task 22, but signal = TTM dividend yield with a 3-year-continuity filter.

- [ ] **Step 1–5: TDD cycle, commit**

---

## Task 24: `AHPremiumMeanReversionStrategy`

**Spec ref:** §8.3.

**Files:**
- Create: `src/ah_research/strategies/ah_premium_mr.py`
- Test: `tests/unit/strategies/test_ah_premium_mr.py`

Implements the full pair-strategy logic:
- Loads AH pairs from `data.ah_pairs.load_ah_pairs()`.
- For each weekly rebalance: compute per-pair rolling-60d z-score of `premium = close_A / (close_H * fx) - 1`.
- Entry rules (spec §8.3): `z < -2.0` → long A, short H (0.05 gross each leg).
- Exit rules: `|z| < 0.5` → unwind.
- Aggregate per-pair decisions into a `Weights` DataFrame with positive (A) and negative (H) weights.
- Enforce 20% total gross cap by shrinking pair weights uniformly if needed.
- Skip `z > +2.0` pairs (would require shorting A-shares); log to stdout or warning.

- [ ] **Step 1: Write test that forces an entry, holds, then unwinds**
- [ ] **Step 2: Run — fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Pass + commit**

---

## Task 25: `verify.walk_forward` — expanding + rolling

**Spec ref:** §7.1.

**Files:**
- Create: `src/ah_research/backtest/verify.py`
- Test: `tests/unit/backtest/test_verify_walk_forward.py`

- [ ] **Step 1: Failing tests**

```python
def test_walk_forward_expanding_produces_5_splits():
    factory = lambda: ValueFactorStrategy()
    report = verify.walk_forward(factory, repo, start, end, n_splits=5, mode="expanding")
    assert len(report.splits) == 5
    assert report.mode == "expanding"

def test_walk_forward_rolling_produces_5_splits():
    ...
```

- [ ] **Step 2: Implement `walk_forward`**

```python
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class WalkForwardSplit:
    is_start: date; is_end: date; oos_start: date; oos_end: date
    is_metrics: "MetricsBundle"
    oos_metrics: "MetricsBundle"

@dataclass(frozen=True)
class WalkForwardReport:
    mode: str
    splits: list[WalkForwardSplit]
    combined_oos_metrics: "MetricsBundle"

def walk_forward(strategy_factory, repo, start, end, n_splits=5, mode="expanding") -> WalkForwardReport:
    trading_days = ...  # from calendar
    split_boundaries = np.array_split(trading_days, n_splits + 1)
    splits = []
    for i in range(n_splits):
        if mode == "expanding":
            is_start = trading_days[0]
            is_end = split_boundaries[i][-1]
        else:  # rolling
            is_start = split_boundaries[i][0]
            is_end = split_boundaries[i][-1]
        oos_start = split_boundaries[i + 1][0]
        oos_end = split_boundaries[i + 1][-1]

        is_result = run_backtest(strategy_factory(), repo,
                                 BacktestConfig(start=is_start, end=is_end, ...))
        oos_result = run_backtest(strategy_factory(), repo,
                                  BacktestConfig(start=oos_start, end=oos_end, ...))
        splits.append(WalkForwardSplit(is_start, is_end, oos_start, oos_end,
                                       is_result.metrics, oos_result.metrics))

    combined = _concat_metrics([s.oos_metrics for s in splits])
    return WalkForwardReport(mode=mode, splits=splits, combined_oos_metrics=combined)
```

- [ ] **Step 3: Pass + commit**

---

## Task 26: `verify.sensitivity` — parameter grid

**Spec ref:** §7.2.

**Files:**
- Modify: `src/ah_research/backtest/verify.py`
- Test: `tests/unit/backtest/test_verify_sensitivity.py`

- [ ] **Step 1-5: TDD cycle**

Implement Cartesian product, 100-combination cap with warning, per-combo backtest, return `SensitivityReport` with a `grid_df: pd.DataFrame` (one row per combo, columns for params + key metrics).

---

## Task 27: `verify.leakage_canary` — three canary types

**Spec ref:** §7.3.

**Files:**
- Modify: `src/ah_research/backtest/verify.py`
- Test: `tests/unit/backtest/test_verify_leakage.py`

- [ ] **Step 1: Failing tests — a deliberately-leaky strategy is flagged**

```python
class LeakyStrategy:
    """Uses NEXT day's return as today's signal — should be flagged."""
    name = "leaky"
    def generate(self, repo, start, end):
        prices = repo.get_prices(["600000.SH"], start, end)
        prices["future_return"] = prices["close"].pct_change().shift(-1)
        ...

def test_signal_shift_canary_flags_leaky_strategy():
    report = verify.leakage_canary(LeakyStrategy(), repo, start, end,
                                    kinds=["signal_shift"])
    # Shifting back by 1 should NOT raise Sharpe (already using future data)
    # Actually, for LeakyStrategy, shifting signal further back should degrade it
    # — our canary expects Sharpe rise under shift. Here we validate the canary
    # correctly detects already-leaked signals via near-zero delta.
    ...
```

- [ ] **Step 2–4: Implement three canary kinds**

(a) `future_price_shuffle`: run base backtest; deep-copy price DataFrame; shuffle rows after `t*`; rerun; assert `equity_curve_base[:t*] ≈ equity_curve_shuffled[:t*]`. Report max divergence; fail if > 1e-10.

(b) `future_fundamentals_shuffle`: analog on fundamentals. (If strategy doesn't use fundamentals — e.g. AH pair — this canary auto-passes with reason="n/a".)

(c) `signal_shift`: rerun backtest with strategy's signals shifted back 1 day (using tomorrow's data for today); compare Sharpe. Pass if `sharpe_shifted > sharpe_base` (signal has predictive power); fail otherwise with a warning, not a hard stop.

- [ ] **Step 5: Commit**

---

## Task 28: `verify.survivorship_check` — PIT vs static vs random

**Spec ref:** §7.4.

**Files:**
- Modify: `src/ah_research/backtest/verify.py`
- Test: `tests/unit/backtest/test_verify_survivorship.py`

- [ ] **Step 1: Failing test — strategy on survivorship-biased universe outperforms PIT**

- [ ] **Step 2: Implement**

Run strategy three ways:
1. With standard PIT universe (via `repo.get_universe_over_time(...)`).
2. With static universe frozen at `end` and back-fill (simulated by overriding `get_universe_over_time` wrapper).
3. 50 random-universe runs (seeded from `config.random_seed`): sample `avg_positions` symbols from the set-of-all-historical-members.

Return a `SurvivorshipReport` with per-run metrics and the percentile of PIT Sharpe within the 50-random distribution.

- [ ] **Step 3: Pass + commit**

---

## Task 29: `src/ah_research/backtest/__init__.py` public API

**Files:**
- Modify: `src/ah_research/backtest/__init__.py`
- Test: `tests/unit/backtest/test_public_api.py`

- [ ] **Step 1: Failing test — all named exports are importable**

```python
def test_public_exports():
    from ah_research.backtest import (
        run_backtest, BacktestConfig, BacktestResult, verify,
        Signals, Weights, CostModelBundle, DEFAULT_COSTS_2024, MetricsBundle,
    )
```

- [ ] **Step 2: Re-export**

```python
# src/ah_research/backtest/__init__.py
"""Backtest engine, costs, metrics, and verification."""
from ah_research.backtest.engine import run_backtest
from ah_research.backtest.types import (
    BacktestConfig, BacktestResult, Signals, Weights,
    Order, Trade, Position,
)
from ah_research.backtest.costs import CostModel, CostModelBundle, DEFAULT_COSTS_2024
from ah_research.backtest.metrics import MetricsBundle, compute_metrics
from ah_research.backtest import verify

__all__ = [
    "run_backtest", "BacktestConfig", "BacktestResult",
    "Signals", "Weights", "Order", "Trade", "Position",
    "CostModel", "CostModelBundle", "DEFAULT_COSTS_2024",
    "MetricsBundle", "compute_metrics", "verify",
]
```

Same treatment for `portfolio/__init__.py` and `strategies/__init__.py`.

- [ ] **Step 3: Pass + commit**

---

## Task 30: Acceptance notebook

**Spec ref:** §9.

**Files:**
- Create: `notebooks/phase2_acceptance.ipynb`
- Test: `tests/integration/test_acceptance_notebook_runs.py`

- [ ] **Step 1: Failing test — notebook executes top-to-bottom without error**

```python
# tests/integration/test_acceptance_notebook_runs.py
import nbformat
from nbclient import NotebookClient

def test_notebook_runs():
    nb = nbformat.read("notebooks/phase2_acceptance.ipynb", as_version=4)
    client = NotebookClient(nb, timeout=600)
    client.execute()
    # Check that no cell has an error output
    for cell in nb.cells:
        if cell.cell_type == "code":
            for output in cell.get("outputs", []):
                assert output.get("output_type") != "error", \
                    f"Cell failed: {cell.source[:100]}"
```

This test is slow (runs the real 9-cell notebook). Mark with `@pytest.mark.slow`.

- [ ] **Step 2: Write the 9-cell notebook**

Each cell named and numbered per spec §9. Use the synthetic-market fixture for any test runs inside the notebook to avoid requiring live data; document at top that switching to real data is one variable change.

- [ ] **Step 3: Execute notebook manually once; commit outputs**

```bash
jupyter nbconvert --to notebook --execute notebooks/phase2_acceptance.ipynb --inplace
git add notebooks/phase2_acceptance.ipynb tests/integration/test_acceptance_notebook_runs.py
git commit -m "feat(phase-2): acceptance notebook with all three strategies + verify outputs

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 31: CHANGELOG, README reference, CI verification

**Files:**
- Create/Modify: `CHANGELOG.md`
- Modify: `README.md`
- No tests.

- [ ] **Step 1: Add CHANGELOG entry**

```markdown
## [Unreleased] — Phase 2

### Added
- Daily-loop backtest engine with T+1/T+2 settlement, price-limit/halt/ST handling, dividend reinvestment, multi-currency cash, per-exchange asymmetric CostModel.
- Three reference strategies: ValueFactorStrategy, DividendYieldStrategy, AHPremiumMeanReversionStrategy.
- `verify` module: walk_forward (expanding/rolling), sensitivity, three-type leakage canary, survivorship vs random-universe baseline.
- Metrics bundle with Newey-West HAC standard errors on α/β/IR.
- `notebooks/phase2_acceptance.ipynb` — runnable acceptance artifact.

### Changed
- `statsmodels >= 0.14` added as a new runtime dependency.

### References
- [Phase 2 spec](docs/superpowers/specs/2026-04-29-ah-research-phase-2-backtest-design.md)
- [Phase 2 plan](docs/superpowers/plans/2026-04-29-ah-research-phase-2.md)
```

- [ ] **Step 2: Add reference to README**

Append a "Phase 2 — Backtest engine" section linking to the spec and the acceptance notebook.

- [ ] **Step 3: Full test run + coverage**

```bash
pytest --cov=src/ah_research/backtest --cov=src/ah_research/portfolio --cov=src/ah_research/strategies \
       --cov-report=term-missing --cov-fail-under=90 -q
mypy src/ah_research/backtest/ src/ah_research/portfolio/ src/ah_research/strategies/
ruff check src/ tests/
```

All three must be green with coverage ≥ 90%.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md
git commit -m "docs(phase-2): changelog + README references to spec and plan

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

- [ ] **Step 5: Open PR**

```bash
git push
gh pr create --title "Phase 2: backtest engine, verify, 3 reference strategies" \
             --body "$(cat <<'EOF'
## Summary

Implements Phase 2 per `docs/superpowers/specs/2026-04-29-ah-research-phase-2-backtest-design.md`:

- Event-driven daily-loop engine (T+1/T+2, limits, halts, dividends, multi-ccy).
- Per-exchange asymmetric CostModel with 2024 baseline.
- Three reference strategies exercising long-only factor + AH pair.
- `verify.py` with rich leakage canary.
- Acceptance notebook.

## Test plan

- [ ] `pytest -q` green
- [ ] `pytest --cov=src/ah_research/backtest --cov-fail-under=90` green
- [ ] `mypy --strict` clean on new modules
- [ ] `ruff check` clean
- [ ] `notebooks/phase2_acceptance.ipynb` runs top-to-bottom without error
- [ ] All three strategies pass `leakage_canary` and `survivorship_check`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Plan self-review notes

**Spec coverage:** Each spec section is covered by explicit tasks:
- §1 Scope → captured in Task 0–1 setup + all subsequent
- §2 Key decisions → embedded throughout (engine in Tasks 9–14 for D1; protocols Task 7 for D3; costs Task 5 for D4; verify Tasks 25–28 for D5; timing T9 for D6; benchmarks Task 19 for D7; hash Task 4 for D8; statsmodels Task 1 for D9)
- §3 Module layout → Tasks 1, 2, 3, 5, 6, 7, 9, 15–18, 25, 29
- §4 Types → Tasks 2, 3, 4, 5
- §5 Engine algorithm → Tasks 9, 10, 11, 12, 13, 14, 19, 20
- §6 Metrics → Tasks 15, 16, 17, 18
- §7 verify → Tasks 25, 26, 27, 28
- §8 Strategies → Tasks 22, 23, 24
- §9 Notebook → Task 30
- §10 Testing → unit tests in every task; integration in Tasks 20 and 30; property in Task 21
- §11 Error handling → Task 20
- §12 Future extensions → documented in spec; no plan tasks needed (by design)
- §13 Definition of done → Task 31

**Type consistency:** Reviewed naming:
- `SignalStrategy` / `WeightStrategy` used consistently.
- `BacktestConfig` / `BacktestResult` / `Signals` / `Weights` / `Order` / `Trade` / `Position` consistent.
- `CostModel.compute(side, notional_local)` uniformly.
- `hash_config(cfg)` uniformly.
- `verify.walk_forward / sensitivity / leakage_canary / survivorship_check` uniform.

**Placeholder scan:** No "TBD/TODO/implement later" remain. Task 8 (synthetic market fixture) and Task 24 (AH pair strategy) delegate some implementation detail to the executor; this is necessary because those units are large (200-300 LOC) and laying out every line would bloat this doc beyond usefulness. Concrete signatures, test shapes, and acceptance criteria are given.

**Scope:** ~31 tasks, ~3 weeks. One plan. Single feature branch. Ready to execute.
