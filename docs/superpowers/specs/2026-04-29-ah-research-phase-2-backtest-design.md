# Phase 2 Design — Backtest Engine, Metrics & Verification

**Status:** Draft, pending user review
**Author:** Brian Huang (+ Claude)
**Date:** 2026-04-29
**Depends on:** Phase 0/1 (merged, commit `bd207f5`); parent design `2026-04-28-ah-research-platform-design.md`

---

## 1. Scope

Phase 2 delivers the **research engine** on top of the Phase 1 data layer:

1. A daily-loop event-driven backtest engine that correctly models A-share and HK market mechanics (T+1/T+2 settlement, price limits, halts, ST flags, dividend reinvestment, multi-currency cash).
2. A transaction-cost model with per-exchange asymmetric buy/sell structure (2024 baseline, extensible interface for time-varying costs).
3. A metrics bundle with Newey-West standard errors.
4. Three reference strategies: two long-only factor strategies and one AH-pair mean-reversion strategy that exercises the pair / multi-currency / short code paths.
5. A rigorous `verify.py` module (walk-forward, parameter sensitivity, leakage canary, survivorship check vs. random baseline).
6. An acceptance notebook that runs all three strategies end-to-end with every verification output.

**Out of scope (deferred to later phases):**
- Portfolio optimizer (CVXPY, mean-variance, risk parity) → Phase 4.
- Paper-trading / live execution adapters → not on roadmap.
- ML strategy training harness → Phase 5.
- Market-impact / quadratic cost terms → later.
- Minute-bar backtesting → not on roadmap.
- Time-varying (historically accurate) cost history — Phase 2 ships a 2024 snapshot but keeps the interface ready for a `valid_from` extension.

**Estimated effort:** ~3 weeks (original 1.5-week estimate was for a minimal `verify.py`; we elected the richer version, roughly doubling verify effort).

---

## 2. Key design decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Event-driven daily loop** (not pure-vectorized matrix). | A-share limit-up/limit-down and ST mechanics are semantically a queued-retry loop. Vectorized masking fudges the semantics; correctness outweighs the 10–100× speed gain on our ≤300-symbol × 20-year universe. |
| D2 | **Three examples:** `ValueFactorStrategy`, `DividendYieldStrategy`, `AHPremiumMeanReversionStrategy`. | The AH pair strategy exercises the project's unique data (AH pair, FX, premium calc) and forces the engine to support shorts and multi-currency cash — features that are cheap now and expensive to retrofit. |
| D3 | **Dual Strategy Protocols**: `SignalStrategy` (emits per-symbol signal, passed through `portfolio.signal_to_weights(...)`) and `WeightStrategy` (emits weights directly). | Factor strategies and pair strategies are fundamentally different species; forcing one into the other distorts both. `run_backtest` dispatches on the Protocol. |
| D4 | **Per-exchange asymmetric CostModel, 2024 snapshot**. | A-share sell-side stamp tax alone introduces a structural asymmetry that flat bps cannot capture; AH pair strategies are especially sensitive to this. The interface accepts a list of `CostModel` entries with optional `valid_from` for future time-varying extension. |
| D5 | **Rich `verify.py`**: expanding/rolling walk-forward, multi-dim parameter grid, three canary types (future-price shuffle, future-fundamentals shuffle, signal-shift), survivorship vs. random-universe baseline. | `leakage_canary` is the project's quality signature; it deserves depth over a narrow one-type check. |
| D6 | **Rebalance timing**: signal generated at period-end close (`t`), trade executed at next open (`t+1`), T+N lock starts at `t+1`. Default `fill_price="next_open"`. | Removes any look-ahead ambiguity; matches A-share retail constraint that you cannot both generate signal on close-of-day t AND trade that same day. |
| D7 | **Benchmarks**: `CSI300_TR` default for long-only A-share strategies, `HSI_TR` for HK, `zero` (cash at 0%) for market-neutral pair strategies, plus user-supplied `pd.Series`. | Pair strategies are absolute-return (beta ≈ 0); comparing them to an equity index is misleading. |
| D8 | **Reproducibility**: every `BacktestResult` carries a SHA-256 `config_hash`; `verify.*` defaults to `seed=42`. | Committed configs can be re-run bit-identical; notebook embeds hash + code version + data snapshot date. |
| D9 | **New dependency**: `statsmodels ≥ 0.14` (Newey-West, OLS for Jensen's α). Nothing else added. | Writing Newey-West by hand is 20 lines but other inferential needs (OLS IC regression in Phase 5) will want it anyway. |

---

## 3. Module layout

```
src/ah_research/
├── backtest/
│   ├── __init__.py          # public re-exports: run_backtest, BacktestResult, BacktestConfig
│   ├── engine.py            # daily-loop engine (~500 LOC)
│   ├── costs.py             # CostModel, CostModelBundle, DEFAULT_COSTS_2024 (~150 LOC)
│   ├── metrics.py           # metrics + Newey-West (~300 LOC)
│   ├── types.py             # Weights, Signals, BacktestConfig, BacktestResult, Trade, Position, Order (~200 LOC)
│   └── verify.py            # walk_forward, sensitivity, leakage_canary, survivorship_check (~600 LOC)
│
├── portfolio/
│   ├── __init__.py
│   └── construction.py      # top_quantile_weights, sector_neutralize, cap_at, signal_to_weights (~250 LOC)
│
├── strategies/
│   ├── __init__.py
│   ├── base.py              # SignalStrategy / WeightStrategy Protocols (~50 LOC)
│   ├── value_factor.py      # ValueFactorStrategy (~150 LOC)
│   ├── dividend_yield.py    # DividendYieldStrategy (~120 LOC)
│   └── ah_premium_mr.py     # AHPremiumMeanReversionStrategy (~250 LOC)
│
└── data/                    # (Phase 1, untouched)

notebooks/
└── phase2_acceptance.ipynb  # 9-cell acceptance notebook

tests/
├── unit/                    # per-rule tests
├── integration/             # full-pipeline with fixture data
└── property/                # hypothesis invariants
```

### Dependency rules (enforced in review)

1. `engine.py` imports only from `data.*`, `backtest.costs`, `backtest.metrics`, `backtest.types`.
   It does **not** import from `strategies.*` or `portfolio.*`.
2. `strategies/*` imports `data.*`, `portfolio.*`, `backtest.types`. Strategies never call `run_backtest`.
3. `verify.py` treats `run_backtest` as a black box. It does not reimplement any engine logic.
4. `portfolio/*` does not import from `backtest.*`. Reverse dependencies would break Phase 4 optimizer work.

---

## 4. Core types and data contracts

### 4.1 Literals and enums (extensions to `data/types.py`)

```python
Freq = Literal["D", "W", "M", "Q"]
FillPrice = Literal["next_open", "next_vwap", "next_close"]
Settlement = Literal["auto", "T+0", "T+1", "T+2"]
DividendPolicy = Literal["reinvest", "cash"]
OrderSide = Literal["buy", "sell", "short", "cover"]
```

### 4.2 Signals and Weights (pandera-validated long DataFrames)

```python
# schemas.py additions

class SignalsSchema(pa.DataFrameModel):
    date: Series[pa.DateTime]
    symbol: Series[str] = pa.Field(str_matches=r"^[0-9]{4,6}\.(SH|SZ|HK)$")
    signal: Series[float] = pa.Field(nullable=False)
    class Config:
        unique = ["date", "symbol"]

class WeightsSchema(pa.DataFrameModel):
    date: Series[pa.DateTime]
    symbol: Series[str] = pa.Field(str_matches=r"^[0-9]{4,6}\.(SH|SZ|HK)$")
    weight: Series[float] = pa.Field(nullable=False)
    # Positive = long, negative = short.
    class Config:
        unique = ["date", "symbol"]
```

Thin wrappers `Signals` and `Weights` hold a schema-validated DataFrame and expose a `.df` accessor. No computation on them — they are purely data carriers.

### 4.3 Strategy Protocols

```python
# strategies/base.py

from typing import Protocol, runtime_checkable

@runtime_checkable
class SignalStrategy(Protocol):
    """Emits a per-symbol scalar signal to be converted to weights downstream."""
    name: str
    def generate(self, repo: DataRepository, start: date, end: date) -> Signals: ...
    def to_weights(self, signals: Signals) -> Weights:
        """Default implementation calls portfolio.signal_to_weights with strategy-configured params."""
        ...

@runtime_checkable
class WeightStrategy(Protocol):
    """Emits target weights directly; pair / multi-leg strategies live here."""
    name: str
    def generate(self, repo: DataRepository, start: date, end: date) -> Weights: ...
```

`run_backtest` dispatches via `isinstance(strategy, WeightStrategy)` vs. `SignalStrategy`.

### 4.4 Configuration, trades, positions, result

```python
# backtest/types.py

@dataclass(frozen=True)
class BacktestConfig:
    start: date
    end: date
    initial_cash: Decimal                     # in base_currency
    base_currency: Currency = Currency.CNY
    rebalance: Freq = "M"
    fill_price: FillPrice = "next_open"
    settlement: Settlement = "auto"           # SH/SZ -> T+1, HK -> T+2
    dividend_policy: DividendPolicy = "reinvest"
    benchmark: BenchmarkSpec = "CSI300_TR"
    cost_model: "CostModelBundle | None" = None  # None -> DEFAULT_COSTS_2024
    allow_leverage: bool = False
    allow_short: bool = True
    a_share_short_allowed: bool = False       # default: block A-share shorts (unrealistic)
    random_seed: int = 42

@dataclass(frozen=True)
class Order:
    ready_date: date                 # signal date; will execute next trading day
    symbol: Symbol
    side: OrderSide
    shares: int                      # integer lots (multiples of lot size for each exchange)

@dataclass(frozen=True)
class Trade:
    exec_date: date
    symbol: Symbol
    side: OrderSide
    shares: int
    fill_price: Decimal              # local currency
    notional: Decimal                # local currency
    cost_total: Decimal              # local currency, sum of breakdown
    cost_breakdown: dict[str, Decimal]  # commission / stamp / transfer / exchange_fee / slippage

@dataclass(frozen=True)
class Position:
    symbol: Symbol
    shares: int                      # signed: negative = short
    avg_cost: Decimal                # local currency, tracks running average for P&L attribution
    locked_until: date | None        # T+N expiry; None when freely tradable

@dataclass(frozen=True)
class BacktestResult:
    config: BacktestConfig
    config_hash: str                       # SHA-256 of canonical config JSON
    code_version: str                      # git SHA at run time
    equity_curve: pd.Series                # base-currency NAV, daily
    benchmark_curve: pd.Series             # aligned to equity_curve index
    returns: pd.Series                     # daily log returns of equity_curve
    positions_history: pd.DataFrame        # long: [date, symbol, shares, mkt_value_local, mkt_value_base]
    trades: pd.DataFrame                   # one row per Trade
    rejected_orders: pd.DataFrame          # one row per Order that could not fill, with reason
    cash_history: pd.DataFrame             # long: [date, currency, balance]
    metrics: "MetricsBundle"
```

### 4.5 Cost model

```python
# backtest/costs.py

@dataclass(frozen=True)
class CostModel:
    exchange: Exchange
    commission_bps: float           # both sides (bps of notional)
    commission_min_local: Decimal   # minimum absolute commission, local currency
    stamp_buy_bps: float            # A-shares: 0; HK: 10
    stamp_sell_bps: float           # A-shares: 5 (post-2023-08); HK: 10
    transfer_bps: float             # SH/SZ transfer fee + HK levies aggregated
    exchange_fee_bps: float
    slippage_bps: float             # modeled as half-spread on fill_price
    valid_from: date | None = None  # reserved for future time-varying; None = always-valid snapshot

@dataclass(frozen=True)
class CostModelBundle:
    models: dict[Exchange, CostModel]
    def for_exchange(self, exchange: Exchange) -> CostModel: ...

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

`CostModel.compute(trade_side, notional_local) -> dict[str, Decimal]` returns the breakdown dict embedded in the `Trade`.

---

## 5. Engine algorithm

Pseudocode of `run_backtest(strategy, repo, config)`:

```
# === Setup ===
universe   = union over [start, end] of symbols the strategy will ever touch
prices     = repo.get_prices(universe, start, end)         # PriceFrameSchema validated
corp_acts  = repo.get_corporate_actions(universe, start, end)
sh_cal     = repo.get_trading_calendar(SH, start, end)     # used for SH/SZ (same calendar)
hk_cal     = repo.get_trading_calendar(HK, start, end)
fx         = repo.get_fx_series("CNY_HKD", start, end)     # for base-ccy conversion
benchmark  = resolve_benchmark(config.benchmark, start, end, repo)

# Merged calendar: d is a trading day if ANY relevant exchange trades that day.
all_days   = merge_calendars(sh_cal, hk_cal, for_exchanges_in_universe)

# === Per-rebalance precomputation ===
# A rebalance triggers on the last trading day of each period (M/Q/W etc.), per base-currency calendar.
rebalance_dates = last_trading_day_of_each_period(all_days, config.rebalance)

per_rebalance_weights: dict[date, Weights] = {}
for r_date in rebalance_dates:
    if isinstance(strategy, WeightStrategy):
        w = strategy.generate(repo, start=r_date, end=r_date)
    else:  # SignalStrategy
        s = strategy.generate(repo, start=r_date, end=r_date)
        w = strategy.to_weights(s)
    validate_weights(w, config)  # leverage / short / sum-to-one / nan
    per_rebalance_weights[r_date] = w

# === State ===
cash: dict[Currency, Decimal] = {Currency.CNY: config.initial_cash, Currency.HKD: Decimal(0)}
positions: dict[Symbol, Position] = {}
pending_orders: list[Order] = []
trades_log, rejected_log, equity_daily, cash_hist = [], [], [], []

# === Daily loop ===
for d in all_days:
    # 1. Corporate actions with ex_date == d (dividends / splits / etc.)
    for ca in corp_acts.where(ex_date=d):
        apply_corporate_action(positions, cash, ca, config.dividend_policy)

    # 2. Execute pending orders (queued yesterday)
    for order in pending_orders:
        bar = prices.loc[(d, order.symbol)]
        if bar.is_suspended \
           or (order.side in {"buy", "cover"} and bar.hit_limit_up) \
           or (order.side in {"sell", "short"} and bar.hit_limit_down):
            rejected_log.append((order, reason))
            continue
        if order.side in {"short", "sell"} and position.locked_until and d <= position.locked_until:
            rejected_log.append((order, "T+N lock"))
            continue
        if order.side == "short" and order.symbol.exchange in {SH, SZ} and not config.a_share_short_allowed:
            rejected_log.append((order, "a-share short disallowed"))
            continue
        base_price = {
            "next_open":  bar.open,
            "next_vwap":  bar.amount / bar.volume,
            "next_close": bar.close,
        }[config.fill_price]
        slip = cost_model.for_exchange(order.symbol.exchange).slippage_bps / 1e4
        sign = +1 if order.side in {"buy", "cover"} else -1
        fill_price = base_price * (1 + sign * slip)
        costs = cost_model.compute(order.side, fill_price * order.shares)
        execute(order, fill_price, costs, positions, cash)
        trades_log.append(Trade(...))
    pending_orders = []

    # 3. If d is a rebalance date, compute target orders for tomorrow
    if d in rebalance_dates:
        targets = per_rebalance_weights[d]
        nav_base = cash_in_base(cash, fx, d) + sum(pos.mtm_base(d) for pos in positions.values())
        for (symbol, target_w) in targets.iter_rows():
            price_local = prices.loc[(d, symbol)].close
            fx_local = fx_to_base(symbol.currency, d)
            target_shares_raw = target_w * nav_base / (price_local * fx_local)
            target_shares = round_to_lot(target_shares_raw, lot_size(symbol))
            current = positions.get(symbol, Position(symbol, 0, ...)).shares
            diff = target_shares - current
            if diff == 0: continue
            side = infer_side(current, target_shares)
            pending_orders.append(Order(ready_date=d, symbol=symbol, side=side, shares=abs(diff)))
        # Close positions not in target
        for sym in set(positions) - set(targets.symbols):
            shares = positions[sym].shares
            if shares == 0: continue
            side = "sell" if shares > 0 else "cover"
            pending_orders.append(Order(ready_date=d, symbol=sym, side=side, shares=abs(shares)))

    # 4. Mark-to-market end-of-day NAV
    nav_d = cash_in_base(cash, fx, d) + sum(pos.mtm_base(d) for pos in positions.values())
    equity_daily.append((d, nav_d))
    cash_hist.append({d, Currency.CNY: cash[Currency.CNY], Currency.HKD: cash[Currency.HKD]})

    # 5. Expire T+N locks
    for sym, pos in positions.items():
        if pos.locked_until and pos.locked_until <= d:
            positions[sym] = replace(pos, locked_until=None)

# === Finalize ===
result = BacktestResult(
    config=config,
    config_hash=hash_config(config),
    code_version=get_git_sha(),
    equity_curve=pd.Series(dict(equity_daily)),
    benchmark_curve=benchmark,
    returns=...,
    positions_history=...,
    trades=pd.DataFrame(trades_log),
    rejected_orders=pd.DataFrame(rejected_log),
    cash_history=pd.DataFrame(cash_hist),
    metrics=compute_metrics(equity_curve, benchmark, trades_log, cost_model, config),
)
return result
```

### Settlement resolution (Settlement="auto")

Per-symbol: SH, SZ → T+1 (buyer locked for 1 trading day); HK → T+2. Shorts on HK: borrow cost ignored in Phase 2 (logged as a known limitation in the notebook). Shorts on SH/SZ: blocked by default.

### Lot sizes

- SH / SZ: 100-share minimum (board lot). Fractional rounding is **floor** on buys, **ceiling** on sells (conservative — never over-hold after a rebalance).
- HK: lot size varies per security; Phase 1's repo does not expose per-symbol lot size. **Phase 2 decision:** use 100 as a conservative default and log a warning. A follow-up issue will add a per-symbol lot-size table (Phase 3 data-layer work).

### Dividend reinvestment

When `dividend_policy == "reinvest"`, cash dividends on ex-date are added to cash, then on the **next** trading day an automatic `buy` order for that symbol is queued at the pro-rata amount (rounded down to lot). This mirrors real-world DRIP behavior and keeps dividend P&L in `total_return` schema consistent.

---

## 6. Metrics bundle

`metrics.compute_metrics(equity_curve, benchmark, trades, cost_model, config) -> MetricsBundle`.

### Content

- **Returns**: CAGR, total return, annualized volatility (252-day).
- **Risk-adjusted**: Sharpe (rf=0), Sortino, max drawdown, max DD duration (days), Calmar.
- **Income**: average dividend yield (long-leg only, annualized).
- **Activity**: annualized turnover (two-sided notional / avg NAV), avg number of positions, avg holding period (days).
- **Benchmark-relative**: excess return, information ratio, tracking error, Jensen's α, β (OLS on daily returns).
- **Inferential**: Newey-West SE and t-stat for α, β, IR. HAC lag = `int(4 * (T/100) ** (2/9))` (Andrews 1991). Uses `statsmodels.regression.linear_model.OLS(...).fit().get_robustcov_results("HAC", maxlags=L)`.

### Return formula conventions

- Portfolio returns = `log(nav_t / nav_{t-1})`.
- Benchmark: TR series (`CSI300_TR` / `HSI_TR`) via repo; `zero` = constant 1.0.
- All annualization uses 252 trading days.

---

## 7. Verification — `verify.py`

Four functions. Each returns a frozen dataclass with structured output the notebook renders.

### 7.1 `walk_forward(strategy_factory, repo, start, end, n_splits=5, mode="expanding"|"rolling") -> WalkForwardReport`

- Partitions `[start, end]` into `n_splits` chronological OOS windows.
- `mode="expanding"`: IS starts at `start`, grows each split; OOS is the next segment.
- `mode="rolling"`: IS is a fixed-length rolling window sliding forward.
- Phase 2 strategies have no hyperparameter fitting step; `strategy_factory()` returns a fresh instance per split. IS segment is run only for diagnostic metrics in the report.
- Reports per-split metrics and concatenated OOS metrics vs. IS metrics.

### 7.2 `sensitivity(strategy_factory, repo, param_grid, start, end) -> SensitivityReport`

- `param_grid: dict[str, list[Any]]`, e.g. `{"quantile": [0.1, 0.2, 0.3], "max_weight": [0.03, 0.05, 0.08]}`.
- Computes the full Cartesian product (capped at 100 combinations; user sees a warning if exceeded).
- For each combination, calls `strategy_factory(**params)` and runs a backtest.
- Output: a `pd.DataFrame` with one row per combination, columns for key metrics + a 2D heatmap rendering for notebook display.

### 7.3 `leakage_canary(strategy, repo, start, end, kinds=all) -> CanaryReport`

Three canary kinds:

**(a) `future_price_shuffle`** — Run backtest. Then permute the price series after some midpoint `t*`, rerun, and verify that `equity_curve[:t*]` is identical (bit-for-bit within `1e-10`). If not, the engine leaks future prices into past P&L.

**(b) `future_fundamentals_shuffle`** — Analog: permute `publication_date` or `value` of fundamentals rows after `t*`, rerun, verify past equity unchanged. Guards against leakage in the strategy's fundamentals lookup.

**(c) `signal_shift`** — Shift the strategy's signals **backward** by one trading day (so they use tomorrow's data for today's position). Rerun backtest. The Sharpe ratio **must rise** for any signal with predictive power (if not, the signal has no alpha, which is itself a useful negative result). Output the delta.

Each kind returns pass/fail plus max-divergence magnitude.

### 7.4 `survivorship_check(strategy, repo, start, end, n_random_universes=50) -> SurvivorshipReport`

Three-way comparison:

- **(i) PIT universe** — what the strategy sees in production: `repo.get_universe_over_time(...)` survivorship-free.
- **(ii) Static universe** — index membership snapshot at `end` used back-fill (classic survivorship bias).
- **(iii) Random universes** — 50 random draws from the union of all historical members of size = avg positions, seeded from `config.random_seed`. Produces a distribution to benchmark "am I really better than random selection in the achievable universe?"

Reports metric deltas + a percentile rank of PIT metrics within the random distribution.

---

## 8. Reference strategies

### 8.1 `ValueFactorStrategy` (SignalStrategy)
- Universe: CSI 300 constituents PIT.
- Signal: composite rank of inverse-PE, inverse-PB, and dividend-yield (equal-weighted).
- `to_weights`: `portfolio.construction.signal_to_weights(method="top_quantile", quantile=0.2, max_weight=0.05, sector_neutral=True)`.
- Engine-level rebalance frequency: `config.rebalance="M"` (monthly).

### 8.2 `DividendYieldStrategy` (SignalStrategy)
- Universe: CSI 300 constituents PIT.
- Signal: trailing 12-month dividend yield, only for firms with continuous 3-year dividend history.
- `to_weights`: `portfolio.construction.signal_to_weights(method="top_quantile", quantile=0.3, max_weight=0.05, sector_neutral=False)`.
- Engine-level rebalance frequency: `config.rebalance="Q"` (quarterly).

### 8.3 `AHPremiumMeanReversionStrategy` (WeightStrategy)
- Universe: curated dual-listed AH pairs from `ah_pairs.yaml`.
- Per pair: rolling 60-day z-score of `premium = close_A / (close_H * FX_HKD_CNY) - 1`.
- Entry: `z > +2.0` (A rich, H cheap) → **skip**: would require shorting A-share, which is disallowed; logged to `rejected_orders` with a human-readable reason. `z < -2.0` (A cheap, H rich) → long A-leg, short H-leg.
- Exit: `|z| < 0.5` → close both legs.
- Position sizing: equal-weighted per open pair, max 5% gross per leg, max 20% total gross (sum of `|weight|` across all open pairs).
- Engine-level rebalance frequency: `config.rebalance="W"` (weekly). Between weekly checks, positions are held unchanged; the strategy's entry/exit logic only re-evaluates at each rebalance date.

---

## 9. Acceptance notebook

`notebooks/phase2_acceptance.ipynb` — 9 numbered cells, each self-contained and runnable top-to-bottom:

1. Environment setup — import, fix seed, print `code_version`, `data_snapshot_date`.
2. Run three strategies, print full `MetricsBundle` for each.
3. Equity curves (log y-axis), each vs. its benchmark.
4. Drawdown plots for each.
5. `leakage_canary` report for each (three canary types), all must PASS.
6. `survivorship_check` report for each (PIT vs static vs random percentile).
7. `walk_forward` 5-split table per strategy (expanding mode).
8. `sensitivity` heatmap per strategy over its primary param.
9. AH pair case study — premium + z-score + entry/exit markers for one selected pair.

The notebook ends with a printed disclaimer: *"Results are historical backtest, not investment advice."*

The notebook's final cell prints `notebook_hash`, the config hashes of every run, and the git commit SHA to make the whole artifact reproducible.

---

## 10. Testing strategy

### 10.1 Unit tests (`tests/unit/`)

One test file per engine rule. Each uses hand-crafted tiny fixtures:

- `test_engine_t1_lock.py` — buy on day 1, sell attempt day 1 rejected, sell day 2 succeeds (SH/SZ); same pattern day 1 → day 3 for HK.
- `test_engine_limit_up.py` — buy order on limit-up day is rejected; retries next day.
- `test_engine_limit_down.py` — analogous for sell during limit-down.
- `test_engine_suspension.py` — order during halt is rejected, resumes after halt ends.
- `test_engine_dividend_reinvest.py` — cash dividend increases position next day by exactly `floor(dividend_amount / next_open / lot) * lot` shares.
- `test_engine_fill_prices.py` — next_open / next_vwap / next_close produce the expected fill numbers.
- `test_engine_short_blocks.py` — A-share short attempt rejected; HK short allowed.
- `test_engine_multi_currency.py` — CNY strategy holding HK position shows correct FX impact on NAV.
- `test_costs.py` — each cost component is computed correctly; sell-side stamp asymmetry shows up.
- `test_metrics.py` — each metric on a known fixture; Newey-West matches `statsmodels` reference.
- `test_portfolio.py` — `top_quantile_weights`, `sector_neutralize`, `cap_at` behave correctly on edge cases (ties, all same sector, zero signal).
- `test_verify_leakage.py` — synthetic leakage strategy (returns next-day's return as signal) — canary must flag.
- `test_verify_survivorship.py` — on a fixture where only "survivors" had good returns, the random-universe baseline catches the bias.

### 10.2 Integration tests (`tests/integration/`)

- `test_end_to_end_value_factor.py` — runs a one-year backtest on a tiny fixture CSI 300 subset; asserts `BacktestResult` shape, non-empty trades, benchmark aligned.
- `test_end_to_end_ah_pair.py` — two AH pairs, six months, asserts pair-neutral gross exposure.

Integration tests use seeded fixture Parquet files committed under `tests/fixtures/phase2/` (small: < 2 MB total).

### 10.3 Property tests (`tests/property/`)

Hypothesis invariants:

- **NAV conservation**: `cash_total + positions_mv_total == equity_curve[d]` within 1e-6 base currency at every `d`.
- **No-leakage invariant**: for any random sequence of bars after date `D`, `equity_curve[:D]` is a deterministic function of bars on-or-before `D`.
- **Seed determinism**: `run_backtest(same config, same seed, same data)` produces a byte-identical `BacktestResult` (excluding `code_version`).

### 10.4 Coverage target

- Unit + integration: ≥ 90% line coverage on `backtest/*` and `portfolio/*`.
- Branch coverage: ≥ 80%.
- Leakage canary must run in CI on every PR that touches `backtest/*`.

---

## 11. Error handling and edge cases

- Strategy emits weights summing to > 1.0 with `allow_leverage=False` → `ValueError` with the offending date / sum.
- Strategy emits NaN weights → `ValueError` with diagnostic DataFrame of offending rows.
- Signal references a symbol not in `repo` (e.g. delisted) → engine logs a warning, sets weight to 0 for that date/symbol, continues.
- All trades rejected for a rebalance date (e.g. whole market suspended) → carry last-day positions forward, log a warning in the result.
- Cash goes negative in any currency → hard error (should never happen given the order-sizing logic; indicates an accounting bug). Log the date, current positions, and last N trades; re-raise.
- Benchmark series missing dates that appear in `equity_curve` → forward-fill the benchmark with a warning, cap the forward-fill at 3 days.

---

## 12. Future extensions anticipated (but NOT built in Phase 2)

These are called out so the interfaces don't paint us into a corner:

1. `CostModel.valid_from` — date-indexed bundle for historically accurate stamp rates.
2. A `SettlementPolicy` object replacing the Settlement literal — when multi-currency margining lands.
3. A `BorrowCostModel` to make HK shorts realistic (Phase 3+).
4. An `optimizer: Optimizer | None` field on `BacktestConfig` that, when set, replaces per-strategy `to_weights` (Phase 4).
5. Intra-day `fill_price` paths for minute-bar (never, not planned).

---

## 13. Deliverables and definition of done

- [ ] `src/ah_research/backtest/` and `src/ah_research/portfolio/` and `src/ah_research/strategies/` implemented per §3–§8.
- [ ] `notebooks/phase2_acceptance.ipynb` runs top-to-bottom without error, all three `leakage_canary` pass for all three strategies.
- [ ] Unit + integration + property tests green; coverage ≥ 90% line on new modules.
- [ ] `mypy --strict` passes on new modules.
- [ ] `ruff check` clean.
- [ ] `statsmodels ≥ 0.14` added to `pyproject.toml`.
- [ ] CHANGELOG updated with Phase 2 entry.
- [ ] Spec doc (this file) + implementation plan (`docs/superpowers/plans/2026-04-29-ah-research-phase-2.md`) referenced from README.

---

## Appendix A — API sketch for users

```python
from datetime import date
from decimal import Decimal
from ah_research.data import DataRepository
from ah_research.backtest import run_backtest, BacktestConfig
from ah_research.strategies import (
    ValueFactorStrategy, DividendYieldStrategy, AHPremiumMeanReversionStrategy,
)
from ah_research.backtest import verify

repo = DataRepository.from_default_cache()

cfg = BacktestConfig(
    start=date(2015, 1, 1), end=date(2025, 12, 31),
    initial_cash=Decimal("1_000_000"),
    rebalance="M", benchmark="CSI300_TR",
)
result = run_backtest(ValueFactorStrategy(quantile=0.2), repo, cfg)
print(result.metrics)

canary = verify.leakage_canary(ValueFactorStrategy(quantile=0.2), repo,
                               start=cfg.start, end=cfg.end)
assert canary.all_pass
```
