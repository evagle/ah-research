"""Integration test: full factor study pipeline on ValueFactorStrategy over synthetic market."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from ah_research.analysis.factor_study import FactorReport, factor_study
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ---------------------------------------------------------------------------
# Symbols used across tests
# ---------------------------------------------------------------------------
_SYMBOLS = ["600000.SH", "000001.SZ", "600519.SH", "600036.SH", "601318.SH"]
_START = date(2022, 1, 1)
_END = date(2023, 12, 31)


@pytest.fixture(scope="module")
def market_repo():
    return build_synthetic_market(start=_START, end=_END, symbols=_SYMBOLS)


# ---------------------------------------------------------------------------
# Helper: build a DataFrame of random signals (one per symbol per month end)
# ---------------------------------------------------------------------------


def _make_signals_df(symbols: list[str], start: date, end: date, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    eoms = pd.date_range(str(start), str(end), freq="ME")
    rows = []
    for d in eoms:
        for sym in symbols:
            rows.append({"date": d, "symbol": sym, "signal": rng.standard_normal()})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_factor_study_report_shape(market_repo):
    """FactorReport has expected shape for 2 IC horizons and n_quantiles=5."""
    signals_df = _make_signals_df(_SYMBOLS, _START, _END)
    report = factor_study(
        signals_df,
        market_repo,
        start=_START,
        end=_END,
        n_quantiles=5,
        ic_horizons=[5, 20],
        sector_neutral=False,
        bootstrap_n_resamples=50,
    )
    assert isinstance(report, FactorReport)
    # ic_summary must have one row per horizon
    assert report.ic_summary.shape[0] == 2
    assert "mean_ic" in report.ic_summary.columns
    # quantile_returns must have Q1..Q5 + long_short columns
    q_cols = [f"Q{i}" for i in range(1, 6)]
    for col in q_cols:
        assert col in report.quantile_returns.columns
    assert "long_short" in report.quantile_returns.columns


def test_factor_study_non_trivial_values(market_repo):
    """IC summary contains finite (non-NaN) mean values for at least one horizon."""
    signals_df = _make_signals_df(_SYMBOLS, _START, _END)
    report = factor_study(
        signals_df,
        market_repo,
        start=_START,
        end=_END,
        n_quantiles=5,
        ic_horizons=[20],
        sector_neutral=False,
        bootstrap_n_resamples=50,
    )
    # At least the mean_ic column must be populated (not all NaN)
    assert report.ic_summary["mean_ic"].notna().any()
    assert report.n_rebalance_dates > 0
    assert report.bootstrap_q5_minus_q1.get("mean") is not None


def test_factor_study_with_value_strategy(market_repo):
    """factor_study() also accepts a SignalStrategy (ValueFactorStrategy)."""
    from ah_research.strategies import ValueFactorStrategy

    strategy = ValueFactorStrategy()
    report = factor_study(
        strategy,
        market_repo,
        start=_START,
        end=_END,
        ic_horizons=[20],
        bootstrap_n_resamples=50,
    )
    assert isinstance(report, FactorReport)
    assert report.n_rebalance_dates > 0
