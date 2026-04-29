# ah-research

Personal A-shares + HK stock research platform.

## Overview

`ah-research` is a Python library for systematic research on Chinese A-shares and Hong Kong equities, with a focus on A/H premium strategies.

## Features

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
# Install
pip install -e ".[dev]"

# Warm up local cache (A-shares sample)
ah warmup sample

# Run unit tests
pytest -q

# Run acceptance notebook (slow)
pytest tests/integration/test_acceptance_notebook_runs.py -m slow -v
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
