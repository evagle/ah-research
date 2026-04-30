# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Phase 4.6 — Filings + Profile Corpus Summary (2026-04-30)

### Added
- `build_corpus_summary(filings_repo, profiles_repo)` — pure DataFrame builder (10 columns per ticker: filings counts, freshness, profile presence, staleness).
- `ah filings summary [--sort-by COLUMN]` CLI subcommand.

### Design doc
- `docs/superpowers/specs/2026-04-30-ah-research-phase-4-6-corpus-summary-design.md`

## Phase 4.5 — Filings Text Search (2026-04-30)

### Added
- `FilingsRepository.search(query, *, symbols=None, kinds=None, regex=False, max_hits_per_file=None)` — substring / regex search across 年报, 招股说明书, and research reports. Returns `SearchHit` objects with file, line number, matching line, and 3-line context window.
- `ah filings search <query>` CLI subcommand with `--symbols`, `--kinds`, `--regex`, `--max-per-file` flags.
- `SearchHit` frozen dataclass exported from `ah_research.filings`.

### Design doc
- `docs/superpowers/specs/2026-04-30-ah-research-phase-4-5-filings-search-design.md`

 
## Phase 4.1 — Portfolio Optimizer (2026-04-30)

### Added
- `src/ah_research/portfolio/optimizer/` package: `Optimizer`, `OptimizationResult`,
  `CovarianceEstimator` / `ExpectedReturnsEstimator` protocols with 2+3 built-in
  implementations (`SampleCovariance`, `LedoitWolfCovariance`, `UserSuppliedReturns`,
  `HistoricalMeanReturns`, `SignalBasedReturns`).
- Two CVXPY objectives: mean-variance (QP via OSQP) and risk-parity (SOCP via CLARABEL).
- `OptimizedWeightStrategy` — Phase 2 `WeightStrategy` that drives `Optimizer.build()`
  at each rebalance; retains full `OptimizationResult` history.
- Two new `Constraint` kinds: `max_turnover` (L1 anchor to prev weights) and
  `long_only` (explicit form of the default-on kwarg).
- `OptimizationResult.to_dict()` / `.to_markdown()` for serialization and reporting.
- Acceptance notebook `notebooks/phase4_1_optimizer_example.ipynb`.

### Dependencies
- `cvxpy>=1.5,<2.0`
- `clarabel>=0.9,<1.0`
- `scikit-learn` (added as runtime dep for `LedoitWolfCovariance`)

### Design doc
- `docs/superpowers/specs/2026-04-30-ah-research-phase-4-1-optimizer-design.md`


## Phase 4.2 — Filings + Profile Repositories (2026-04-30)

### Added
- `src/ah_research/filings/` package: `Filing` + `Profile` frozen dataclasses,
  `FilingsRepository` (indexes `data/filings/<ticker>/{年报,招股说明书,research}/*.md`),
  `ProfileRepository` (indexes `profiles/<ticker>-<date>.md` with markdown section parser).
- CLI sub-apps: `ah filings list/show`, `ah profile list/show [--section | --list-sections]`.
- Acceptance notebook `notebooks/phase4_2_filings_example.ipynb`.

### Design doc
- `docs/superpowers/specs/2026-04-30-ah-research-phase-4-2-filings-design.md`

## Phase 4.3 — Dossier + Filings/Profile Integration (2026-04-30)

### Added
- `FilingsSection` + `ProfileSection` dataclasses surfaced on `Dossier` — summarize filings inventory (annual count, latest year, IPO flag, research count) and profile metadata (date, section names).
- `build_dossier(symbol, ..., include_qualitative=True, filings_repo=..., profiles_repo=...)` wires Phase 4.2 repositories into the Dossier pipeline.
- `Dossier.to_markdown()` renders "## Filings inventory" and "## Qualitative profile" sections.
- CLI flag `ah dossier <symbol> --qualitative / --no-qualitative` (default: qualitative on).

### Design doc
- `docs/superpowers/specs/2026-04-30-ah-research-phase-4-3-dossier-integration-design.md`


## Phase 4.4 — Screener Filings Enrichment (2026-04-30)

### Added
- `enrich_with_filings(df, filings_repo=..., profiles_repo=...)` — pure function that adds 5 columns (`has_ipo`, `n_annual`, `latest_annual_year`, `n_research`, `has_profile`) to a symbol-indexed DataFrame. Lets Phase 3 Screener users compose qualitative-data filters via standard pandas (e.g. `df[df["has_profile"] & (df["n_annual"] >= 5)]`) without modifying the Screener itself.

### Design doc
- `docs/superpowers/specs/2026-04-30-ah-research-phase-4-4-screener-enrichment-design.md`

### Deferred to future phase
- Structured grading (moat_grade, redflag_count) — requires LLM
- Profile section-presence predicates

## [Unreleased] — Phase 3

### Added

#### Phase 3 — Analysis & Watchlist (Tasks 1-27)

**Analysis helpers** (`src/ah_research/analysis/`)

- `owner_earnings_series()` — Buffett (1986) owner-earnings formula (NI + D&A - CapEx - WC change) from bitemporal fundamentals
- `compute_valuation_bands()` + `ValuationBand` — trailing N-year P/E, P/B, P/S percentile bands with current-percentile readout
- `dividend_consistency_grade()` — A–F grader for dividend consistency over a configurable trailing window
- `run_screen()` + `ScreenResult` — vectorized screener with serializable predicate dict (`<`, `<=`, `>`, `>=`, `==`, `!=`, `between`, `in`, `not_in`), lazy derived-column catalog (`roe_3y_avg`, `revenue_growth_3y_cagr`, `dividend_consistency_grade`, etc.), and typo-suggestion `KeyError`
- `factor_study()` + `FactorReport` — cross-sectional factor study with Spearman IC (Newey-West t-stat), quantile returns, IC decay by horizon, block bootstrap confidence interval for long-short spread, sector neutralization, and `_InlineSignalStrategy` adapter for DataFrame input
- `build_dossier()` + `Dossier` — single-symbol research dossier composing all helpers into sections (OverviewSection, FundamentalsSection, OwnerEarningsSection, ValuationBandsSection, DividendSection, AHPremiumSection, PeersSection, DossierMetadata); `to_markdown(language)` renderer (English + Chinese), `to_html()`, `to_dict()`

**Watchlist** (`src/ah_research/watchlist/`)

- `WatchlistStore` — DuckDB-backed CRUD (create, get, list_all, add_symbol, remove_symbol, delete, export_yaml, import_yaml) over `watchlist_definitions` and `watchlist_snapshots` tables (migration #3)
- `WatchlistSnapshot` — point-in-time metric snapshot per symbol (pe, pb, dividend_yield, roe, market_cap, sector_l1, price); immutability guard unless `force=True`
- `diff_snapshots()` — computes per-metric delta columns between two snapshot dates

**Portfolio Constructor** (`src/ah_research/portfolio/constructor.py`)

- `Constraint` — frozen dataclass with factory classmethods: `max_weight`, `max_gross`, `sector_neutral_to`, `tracking_error`, `min_positions`, `max_positions`
- `Constructor` — fluent builder chain: `.method()` → `.weight_by()` → `.constrain()` → `.build()`; methods: `top_quantile`, `top_n`, `all_positive`; schemes: `equal`, `signal_proportional`, `free_float_mcw`, `mcw`; heuristic constraint relaxation with `ConstraintResult` and `relaxation_notes`
- `ConstructionReport` — full construction output: weights DataFrame, position count, per-constraint results, method/scheme used

**CLI extensions**

- `ah dossier <SYMBOL>` — build and print/save a Dossier as Markdown (`--asof`, `--out`, `--language`)
- `ah watchlist list/create/snapshot/diff/export/import` — full watchlist lifecycle via CLI

**Reference notebooks** (`notebooks/`)

- `phase3_factor_study_value.ipynb` — IC summary + quantile returns + bootstrap on ValueFactorStrategy over synthetic market
- `phase3_screener_workflow.ipynb` — screener → watchlist → snapshot → diff → YAML export flow
- `phase3_dossier_example.ipynb` — full Dossier build + Markdown rendering (en + zh) + to_dict round-trip
- `phase3_portfolio_construction.ipynb` — Constructor chain with all constraint types, shows ConstructionReport

**Tests**

- Unit tests for all new modules (owner_earnings, valuation_bands, dividend_history, screener, factor_study IC/quantile/bootstrap, dossier types/build/render, watchlist store/snapshot, constraint, constructor)
- Integration tests: end-to-end factor study, screener→watchlist, dossier pipelines
- Property tests (Hypothesis): screener idempotence, constructor weights sum to 1, factor study shuffled-signals IC near zero
- Notebook tests: `tests/integration/test_phase3_notebooks_run.py` — `@pytest.mark.slow`, runs all four notebooks via `nbclient`

### Changed

- `src/ah_research/analysis/__init__.py` — public re-exports for `factor_study`, `FactorReport`, `run_screen`, `ScreenResult`, `build_dossier`, `Dossier`, `owner_earnings_series`, `compute_valuation_bands`, `ValuationBand`, `dividend_consistency_grade`
- `src/ah_research/watchlist/__init__.py` — public re-exports for `Watchlist`, `WatchlistStore`, `WatchlistSnapshot`
- `src/ah_research/portfolio/__init__.py` — public re-exports include `Constructor`, `Constraint`, `ConstructionReport`
- `src/ah_research/cli.py` — wired `ah dossier` and `ah watchlist` subcommands

### References

- Spec: `docs/superpowers/specs/2026-04-29-ah-research-phase-3-analysis-design.md`
- Plan: `docs/superpowers/plans/2026-04-29-ah-research-phase-3.md`

---

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
