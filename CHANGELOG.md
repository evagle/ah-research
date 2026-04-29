# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Phase 2 — Backtest Engine & Strategies (Tasks 14-31)

**Core engine** (`src/ah_research/backtest/`)

- `BacktestConfig`, `Order`, `Trade`, `Position`, `BacktestResult`, `Signals`, `Weights` types with pandera schema validation and `hash_config()` for reproducibility
- `CostModel`, `CostModelBundle`, `DEFAULT_COSTS_2024` (A-share stamp duty + bilateral commission)
- `Freq`, `FillPrice`, `Settlement`, `DividendPolicy`, `OrderSide` literal types
- `run_backtest()` engine: daily simulation loop with MTM, multi-currency cash, FX mark-to-market, HK lot-size rounding, T+N settlement lock, limit-up/down and suspension rejection with retry, corporate actions (cash dividends, splits, stock dividends), A-share short blocking, `resolve_benchmark()`, code version tagging
- `MetricsBundle` with full spec fields: CAGR, volatility, Sharpe, Sortino, max drawdown, Calmar, benchmark-relative alpha/beta (Newey-West HAC), activity metrics (turnover, avg positions, holding period, dividend yield), `compute_metrics()`

**Strategy Protocols & implementations** (`src/ah_research/strategies/`)

- `SignalStrategy` and `WeightStrategy` `@runtime_checkable` Protocol definitions
- `ValueFactorStrategy` — composite value score (P/E, P/B, P/S, EV/EBITDA) with PIT fundamentals, top-quantile long-only weights
- `DividendYieldStrategy` — high-yield long-only with 3-year continuity filter
- `AHPremiumMeanReversionStrategy` — rolling z-score of A/H premium with entry/exit thresholds and short-selling on H leg

**Portfolio construction** (`src/ah_research/portfolio/`)

- `top_quantile_weights()`, `cap_at()`, `sector_neutralize()`, `signal_to_weights()`

**Verification utilities** (`src/ah_research/backtest/verify/`)

- `walk_forward()` — expanding and rolling OOS splits with `WalkForwardReport`
- `sensitivity()` — parameter-grid sweep with `SensitivityReport`
- `leakage_canary()` — three canary types (future-data, reversed-date, ahead-of-publication) with `LeakageReport`
- `survivorship_check()` — PIT vs static-universe vs random-universe comparison with `SurvivorshipReport`

**Public API**

- Re-exports from `ah_research.backtest`, `ah_research.portfolio`, `ah_research.strategies` with `__all__` lists

**Testing**

- Synthetic market fixture (`tests/fixtures/phase2/synthetic_market.py`): deterministic in-memory `DataRepository`-compatible object, no network or DuckDB required
- Property-based tests for engine invariants (hypothesis)
- Unit tests for all strategies, metrics, portfolio construction, and verify utilities
- `tests/integration/test_acceptance_notebook_runs.py` (`@pytest.mark.slow`): executes `notebooks/phase2_acceptance.ipynb` end-to-end via nbclient

**Notebook**

- `notebooks/phase2_acceptance.ipynb`: 9-section acceptance notebook demonstrating all three strategies, equity curves, drawdown, leakage canary, survivorship check, walk-forward OOS table, sensitivity sweep, AH pair case study, and reproducibility block — fully runnable on the synthetic fixture with no network access

#### Phase 0/1 — Data Layer (Tasks 1-13)

- `BaostockClient` — A-shares (daily OHLCV, fundamentals, corporate actions, index constituents)
- `AKShareClient` — HK equities + CNY/HKD FX
- `DataRepository` — DuckDB-backed local cache with PIT-correct fundamentals, schema validation via pandera, `resample()`, `compute_ah_premium()`
- `ah warmup` CLI command with `sample`, `csi300`, and `hsi` universe presets
- Hypothesis property tests: symbol roundtrip, PIT monotonicity, adjust idempotence

### Fixed

- `Freq` type is `Literal["D","W","M","Q"]` (not an enum) — replaced `Freq.M`/`Freq.W` attribute access with string literals in test suite
- Engine strategy dispatch: `SignalStrategy` (has `to_weights`) is now checked before `WeightStrategy` so strategies implementing both protocols are routed correctly
- Engine empty-weights guard: `Weights` object with no `weight` column no longer causes `KeyError`
- `SyntheticMarket.compute_ah_premium`: normalise `date` columns to `datetime64[us]` before `pd.merge_asof` to eliminate dtype-resolution mismatch

[Unreleased]: https://github.com/evagle/ah-research/compare/HEAD...HEAD
