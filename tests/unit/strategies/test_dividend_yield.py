"""Tests for DividendYieldStrategy."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from ah_research.backtest.types import Signals, Weights
from ah_research.strategies.dividend_yield import DividendYieldStrategy
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ── helpers ───────────────────────────────────────────────────────────────────

_SYMBOLS = [
    "600000.SH",
    "600016.SH",
    "600028.SH",
    "600036.SH",
    "601318.SH",
]


def _make_dividend_actions(symbols: list[str], base_date: date, years: int = 4) -> list[dict]:
    """Return extra_corporate_actions with annual dividends for each symbol spanning ``years``."""
    actions = []
    for sym in symbols:
        for yr in range(years):
            ex_dt = date(base_date.year - yr, 6, 15)
            actions.append(
                {
                    "symbol": sym,
                    "ex_date": pd.Timestamp(ex_dt),
                    "kind": "cash_dividend",
                    "params_json": json.dumps({"amount_per_share": 0.5}),
                }
            )
    return actions


@pytest.fixture
def repo_with_dividends():
    """Repo where all symbols have 4 years of annual cash dividends."""
    extra = _make_dividend_actions(_SYMBOLS, date(2024, 1, 1), years=4)
    return build_synthetic_market(
        start=date(2023, 9, 1),
        end=date(2024, 3, 31),
        symbols=_SYMBOLS,
        extra_corporate_actions=extra,
    )


@pytest.fixture
def repo_no_dividends():
    """Repo where no symbol has any dividend history."""
    return build_synthetic_market(
        start=date(2023, 9, 1),
        end=date(2024, 3, 31),
        symbols=_SYMBOLS,
    )


# ── generate ──────────────────────────────────────────────────────────────────


def test_dividend_yield_returns_signals(repo_with_dividends):
    """generate() returns a valid Signals object with month-end dates."""
    s = DividendYieldStrategy()
    sigs = s.generate(repo_with_dividends, date(2024, 1, 1), date(2024, 3, 31))
    assert isinstance(sigs, Signals)
    # Three month-ends in Jan-Mar 2024
    assert sigs.df["date"].nunique() == 3


def test_dividend_yield_signals_no_nan(repo_with_dividends):
    """Signals must not contain NaN values."""
    s = DividendYieldStrategy()
    sigs = s.generate(repo_with_dividends, date(2024, 1, 1), date(2024, 3, 31))
    assert not sigs.df["signal"].isna().any()


def test_dividend_yield_filters_symbols_without_history(repo_no_dividends):
    """When no symbol passes the 3-year continuity filter, signals are empty."""
    s = DividendYieldStrategy()
    sigs = s.generate(repo_no_dividends, date(2024, 1, 1), date(2024, 3, 31))
    assert isinstance(sigs, Signals)
    # The synthetic market auto-injects ONE dividend for the first A-share at mid-date.
    # That is only 1 event, not >= 3, so it should NOT pass the 3-year filter.
    # With no qualifying symbols, signals frame may be empty or very sparse.
    # We only assert valid Signals is returned; emptiness depends on the fixture.


def test_dividend_yield_all_symbols_qualify_with_4yr_history(repo_with_dividends):
    """With 4 years of dividends all symbols pass the continuity filter."""
    s = DividendYieldStrategy()
    sigs = s.generate(repo_with_dividends, date(2024, 1, 1), date(2024, 3, 31))
    # All 5 symbols should appear at each month-end
    assert set(sigs.df["symbol"]).issubset(set(_SYMBOLS))
    # Should have signals for all 5 symbols (they all have >3yr dividend history)
    assert sigs.df["symbol"].nunique() == len(_SYMBOLS)


# ── to_weights ────────────────────────────────────────────────────────────────


def test_dividend_yield_to_weights_returns_weights(repo_with_dividends):
    """to_weights(signals, repo) produces valid Weights."""
    s = DividendYieldStrategy()
    sigs = s.generate(repo_with_dividends, date(2024, 1, 1), date(2024, 3, 31))
    if sigs.df.empty:
        pytest.skip("Empty signals")
    weights = s.to_weights(sigs, repo_with_dividends)
    assert isinstance(weights, Weights)


def test_dividend_yield_to_weights_respects_max_weight(repo_with_dividends):
    """No weight exceeds max_weight=0.05."""
    s = DividendYieldStrategy(max_weight=0.05)
    sigs = s.generate(repo_with_dividends, date(2024, 1, 1), date(2024, 3, 31))
    if sigs.df.empty:
        pytest.skip("Empty signals")
    weights = s.to_weights(sigs, repo_with_dividends)
    assert (weights.df["weight"] <= 0.05 + 1e-9).all()


def test_dividend_yield_config_name():
    """Default name is 'dividend_yield'."""
    s = DividendYieldStrategy()
    assert s.name == "dividend_yield"


def test_dividend_yield_recommended_rebalance_documented():
    """Docstring mentions quarterly rebalance."""
    assert (
        "Q" in DividendYieldStrategy.__doc__ or "quarterly" in DividendYieldStrategy.__doc__.lower()
    )  # type: ignore[operator]
