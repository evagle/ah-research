# ah-research

Personal A-shares + HK stock research platform.

## Overview

`ah-research` is a Python library for systematic research on Chinese A-shares and Hong Kong equities, with a focus on A/H premium strategies.

## Features


### Phase 5 — Research Chat UI

- **Phase 5: Research chat** — `ah chat <ticker>` opens a REPL that reasons over your local Dossier / Profile / Screener / Filings data via Claude tool use. Eight tools wire the chat to the platform; sessions persist at `~/.ah-research/chat/`.
  See [design spec](docs/superpowers/specs/2026-05-01-ah-research-phase-5-research-chat-design.md).


### Phase 4.1 — Portfolio Optimizer

- **Phase 4.1: Portfolio Optimizer** — CVXPY-based mean-variance + risk-parity
  optimization with pluggable covariance / expected-returns estimators, strict
  feasibility (with soft-mode fallback), and a `WeightStrategy` plug-in for
  walk-forward backtests. See
  [design spec](docs/superpowers/specs/2026-04-30-ah-research-phase-4-1-optimizer-design.md).

### Phase 4.8: Constructor Optimize Mode

- **Constructor optimize mode** — `Constructor(optimizer=...).weight_by("optimize")` runs the Phase 4.1 convex optimizer inline; `ConstructionReport.optimization_result` carries the full result (dual prices, active constraints, solver status).


### Phase 4.2: Filings + Profile Repositories

- **Phase 4.2: Filings + Profile Repositories** — `FilingsRepository`
  and `ProfileRepository` surface markdown artifacts (年报, 招股说明书,
  analyst research, value-investing profiles) as typed Python data.
  CLI: `ah filings list/show`, `ah profile list/show`.
  See [design spec](docs/superpowers/specs/2026-04-30-ah-research-phase-4-2-filings-design.md).

### Phase 4.3: Dossier + Filings/Profile Integration

- **Phase 4.3: Dossier + Filings/Profile Integration** — `Dossier` now
  optionally includes `FilingsSection` + `ProfileSection` summaries surfaced
  from Phase 4.2 repositories. CLI flag `ah dossier build --qualitative`
  (default on). See
  [design spec](docs/superpowers/specs/2026-04-30-ah-research-phase-4-3-dossier-integration-design.md).

### Phase 4.7: LLM Profile Grading

- **Phase 4.7: LLM Profile Grading** — `ProfileGrader` grades profiles via
  Claude API with disk caching. CLI: `ah profile grade <symbol>`.

### Phase 4.6: Corpus Summary

- **Phase 4.6: Corpus Summary** — `build_corpus_summary()` + `ah filings
  summary` audit local research coverage at a glance (filings counts,
  freshness, profile presence, staleness).

### Phase 4.5: Filings Text Search

- **Phase 4.5: Filings Text Search** — `FilingsRepository.search()`
  grep across all filings in the corpus (年报, 招股说明书, research).
  CLI: `ah filings search "渠道改革" --symbols 600519.SH --kinds annual`.

### Phase 4.4: Screener Filings Enrichment

- **Phase 4.4: Screener Filings Enrichment** — `enrich_with_filings()`
  adds `has_profile` / `n_annual` / `has_ipo` / `latest_annual_year` /
  `n_research` columns to a symbol-indexed DataFrame. Compose with
  Phase 3 Screener via standard pandas filters.
  
### Phase 3 — Analysis & Watchlist

- **Factor study** (`ah_research.analysis.factor_study`): `factor_study()` — cross-sectional Spearman IC, quantile returns, IC decay, block bootstrap CI for long-short spread, sector neutralization
- **Screener** (`ah_research.analysis.screener`): `run_screen()` — vectorized predicate dict (`<`, `>`, `between`, `in`, …), lazy derived-column catalog (ROE averages, revenue CAGR, dividend grades, etc.)
- **Dossier** (`ah_research.analysis.dossier`): `build_dossier()` — single-symbol research report with overview, 10-year fundamentals, owner earnings, valuation bands, dividend history, AH premium; `to_markdown(language)` in English and Chinese
- **Analysis helpers**: `owner_earnings_series()`, `compute_valuation_bands()`, `dividend_consistency_grade()`
- **Watchlist** (`ah_research.watchlist`): `WatchlistStore` — DuckDB-backed CRUD, point-in-time snapshots, metric diffs, YAML import/export
- **Portfolio Constructor** (`ah_research.portfolio.constructor`): `Constructor` fluent chain — `.method()` → `.weight_by()` → `.constrain()` → `.build()`; full `ConstructionReport` with per-constraint status and relaxation notes
- **CLI**: `ah dossier`, `ah watchlist list/create/snapshot/diff/export/import`
- **Reference notebooks** (`notebooks/`):
  - [`phase3_factor_study_value.ipynb`](notebooks/phase3_factor_study_value.ipynb) — IC summary + quantile returns + bootstrap on ValueFactorStrategy
  - [`phase3_screener_workflow.ipynb`](notebooks/phase3_screener_workflow.ipynb) — screener → watchlist → snapshot → diff flow
  - [`phase3_dossier_example.ipynb`](notebooks/phase3_dossier_example.ipynb) — full dossier build + Markdown rendering (en + zh)
  - [`phase3_portfolio_construction.ipynb`](notebooks/phase3_portfolio_construction.ipynb) — Constructor chain with all constraint types

See [`docs/superpowers/specs/2026-04-29-ah-research-phase-3-analysis-design.md`](docs/superpowers/specs/2026-04-29-ah-research-phase-3-analysis-design.md) for the spec and [`docs/superpowers/plans/2026-04-29-ah-research-phase-3.md`](docs/superpowers/plans/2026-04-29-ah-research-phase-3.md) for the implementation plan.

### Phase 2 — Backtest Engine & Strategies

- **Backtest engine** (`ah_research.backtest`): event-driven daily simulation with multi-currency cash, FX mark-to-market, HK lot-size rounding, T+N settlement, limit-up/down and suspension handling, corporate action processing, and full `MetricsBundle` (CAGR, Sharpe, Sortino, max drawdown, Newey-West alpha/beta)
- **Three reference strategies** (`ah_research.strategies`):
  - `ValueFactorStrategy` — composite P/E + P/B + P/S + EV/EBITDA score, PIT fundamentals
  - `DividendYieldStrategy` — high-yield long-only with 3-year continuity filter
  - `AHPremiumMeanReversionStrategy` — rolling z-score of A/H premium, long A + short H
- **Portfolio construction** (`ah_research.portfolio`): `top_quantile_weights`, `cap_at`, `sector_neutralize`, `signal_to_weights`
- **Verification utilities** (`ah_research.backtest.verify`): `walk_forward`, `sensitivity`, `leakage_canary`, `survivorship_check`
- **Acceptance notebook**: `notebooks/phase2_acceptance.ipynb` — runs end-to-end on the synthetic fixture (no network required)

### Phase 0/1 — Data Layer

- `BaostockClient` — A-shares daily OHLCV, fundamentals, corporate actions, index constituents
- `AKShareClient` — HK equities + CNY/HKD FX
- `DataRepository` — DuckDB-backed local cache with PIT-correct fundamentals and pandera schema validation
- `ah warmup` CLI command with `sample`, `csi300`, and `hsi` universe presets

## Quick Start

```bash
# Install (uv is the project's package manager; uv.lock is committed)
uv sync --extra dev
# or: pip install -e ".[dev]"

# Warm up local cache (A-shares sample)
uv run ah warmup sample

# Run unit + property tests
uv run pytest tests/unit tests/property -q

# Run acceptance notebook (slow)
uv run pytest tests/integration/test_acceptance_notebook_runs.py -m slow -v
```

## Development

```bash
# Lint
ruff check src/ tests/

# Type-check
mypy src/

# Tests with coverage
pytest --cov=src/ah_research --cov-report=term-missing
```

See [CHANGELOG.md](CHANGELOG.md) for a full history of changes.

> **DISCLAIMER:** All backtest results are historical and not investment advice.
