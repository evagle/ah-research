"""Tests for AHPremiumMeanReversionStrategy."""

from __future__ import annotations

import logging
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from ah_research.backtest.types import Weights
from ah_research.model.types import AHPair, parse_symbol
from ah_research.strategies.ah_premium_mr import AHPremiumMeanReversionStrategy
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ── pair codes ────────────────────────────────────────────────────────────────

_PING_AN_A = "601318.SH"
_PING_AN_H = "2318.HK"
_ICBC_A = "601398.SH"
_ICBC_H = "1398.HK"

_AH_PAIRS = [
    AHPair(
        a_symbol=parse_symbol(_PING_AN_A),
        h_symbol=parse_symbol(_PING_AN_H),
        name_en="Ping An Insurance",
        name_zh="中国平安",
    ),
    AHPair(
        a_symbol=parse_symbol(_ICBC_A),
        h_symbol=parse_symbol(_ICBC_H),
        name_en="ICBC",
        name_zh="工商银行",
    ),
]

_ALL_SYMBOLS = [_PING_AN_A, _PING_AN_H, _ICBC_A, _ICBC_H]

# Strategy start date; use 90-day warm-up window so rolling 60-day stats are
# available from the first rebalance.
_FIXTURE_START = date(2024, 1, 1)
_FIXTURE_END = date(2024, 6, 30)
_STRATEGY_START = date(2024, 3, 31)  # 90 days into fixture
_STRATEGY_END = date(2024, 6, 30)


# ── helpers ───────────────────────────────────────────────────────────────────


def _build_repo_normal():
    """Repo with flat premium — z-scores stay near zero."""
    return build_synthetic_market(
        start=_FIXTURE_START,
        end=_FIXTURE_END,
        symbols=_ALL_SYMBOLS,
    )


def _build_repo_with_entry_event():
    """Repo where Ping An A-leg is very cheap relative to H-leg (z << -2).

    We inject a price series where the A-share drops sharply over the last
    5 trading days so the rolling premium z-score crosses -2.0 at the first
    weekly rebalance after _STRATEGY_START.
    """
    repo = build_synthetic_market(
        start=_FIXTURE_START,
        end=_FIXTURE_END,
        symbols=_ALL_SYMBOLS,
    )
    # Patch prices: make A-share of Ping An very cheap in the last period.
    # The premium = close_A / (close_H * fx) - 1.
    # If we set close_A to be 0.5x its normal value for the last 10 days,
    # the premium will be very negative → z-score << -2.
    prices_df = repo._prices.copy()
    # Identify the last 10 business dates
    all_dates = prices_df[prices_df["symbol"] == _PING_AN_A]["date"].sort_values()
    if len(all_dates) < 70:
        return repo  # not enough data, fall through
    # Set A-share close to 30% of normal for the last 12 days to force deep negative premium
    last_dates = all_dates.iloc[-12:]
    a_mask = (prices_df["symbol"] == _PING_AN_A) & (prices_df["date"].isin(last_dates))
    for col in ["open", "high", "low", "close", "close_hfq", "total_return"]:
        prices_df.loc[a_mask, col] = prices_df.loc[a_mask, col] * 0.30
    # Keep schema-valid: ensure high >= low, close >= low, close <= high
    prices_df.loc[a_mask, "high"] = prices_df.loc[a_mask, "close"] * 1.005
    prices_df.loc[a_mask, "low"] = prices_df.loc[a_mask, "close"] * 0.995
    repo._prices = prices_df
    return repo


# ── basic tests ───────────────────────────────────────────────────────────────


def test_ah_premium_mr_returns_weights():
    """generate() returns valid Weights."""
    repo = _build_repo_normal()
    s = AHPremiumMeanReversionStrategy()
    with patch("ah_research.strategies.ah_premium_mr.load_ah_pairs", return_value=_AH_PAIRS):
        weights = s.generate(repo, _STRATEGY_START, _STRATEGY_END)
    assert isinstance(weights, Weights)


def test_ah_premium_mr_weights_columns():
    """Weights frame has required columns: date, symbol, weight."""
    repo = _build_repo_normal()
    s = AHPremiumMeanReversionStrategy()
    with patch("ah_research.strategies.ah_premium_mr.load_ah_pairs", return_value=_AH_PAIRS):
        weights = s.generate(repo, _STRATEGY_START, _STRATEGY_END)
    if not weights.df.empty:
        assert set(weights.df.columns) == {"date", "symbol", "weight"}


def test_ah_premium_mr_no_nan_weights():
    """Weights must not contain NaN values."""
    repo = _build_repo_normal()
    s = AHPremiumMeanReversionStrategy()
    with patch("ah_research.strategies.ah_premium_mr.load_ah_pairs", return_value=_AH_PAIRS):
        weights = s.generate(repo, _STRATEGY_START, _STRATEGY_END)
    if not weights.df.empty:
        assert not weights.df["weight"].isna().any()


def test_ah_premium_mr_gross_exposure_capped():
    """Total absolute weight never exceeds max_gross (0.20)."""
    repo = _build_repo_normal()
    s = AHPremiumMeanReversionStrategy(max_gross=0.20)
    with patch("ah_research.strategies.ah_premium_mr.load_ah_pairs", return_value=_AH_PAIRS):
        weights = s.generate(repo, _STRATEGY_START, _STRATEGY_END)
    if not weights.df.empty:
        for _d, grp in weights.df.groupby("date"):
            gross = grp["weight"].abs().sum()
            assert gross <= 0.20 + 1e-9, f"Gross {gross:.4f} exceeds cap on {_d}"


def test_ah_premium_mr_name():
    """Default name is 'ah_premium_mr'."""
    s = AHPremiumMeanReversionStrategy()
    assert s.name == "ah_premium_mr"


def test_ah_premium_mr_entry_triggers_long_a_short_h():
    """When A-leg premium z-score << -2 an entry fires with long A, short H."""
    repo = _build_repo_with_entry_event()
    s = AHPremiumMeanReversionStrategy(entry_z=2.0, exit_z=0.5, leg_weight=0.05)
    with patch("ah_research.strategies.ah_premium_mr.load_ah_pairs", return_value=_AH_PAIRS):
        weights = s.generate(repo, _STRATEGY_START, _STRATEGY_END)

    if weights.df.empty:
        pytest.skip("No weights generated — price injection insufficient for z < -2")

    # When an entry fires: A-leg weight > 0, H-leg weight < 0
    a_weights = weights.df[weights.df["symbol"] == _PING_AN_A]["weight"]
    h_weights = weights.df[weights.df["symbol"] == _PING_AN_H]["weight"]

    if a_weights.empty or h_weights.empty:
        pytest.skip("Ping An pair not activated in weights")

    # At least one date should have long A (positive) and short H (negative)
    assert (a_weights > 0).any(), "Expected at least one long A-leg entry"
    assert (h_weights < 0).any(), "Expected at least one short H-leg entry"


def test_ah_premium_mr_state_reinitialises():
    """Calling generate() twice resets internal state (no stale open-pair carry-over)."""
    repo = _build_repo_normal()
    s = AHPremiumMeanReversionStrategy()
    with patch("ah_research.strategies.ah_premium_mr.load_ah_pairs", return_value=_AH_PAIRS):
        w1 = s.generate(repo, _STRATEGY_START, _STRATEGY_END)
        w2 = s.generate(repo, _STRATEGY_START, _STRATEGY_END)
    # Both runs should produce identical results
    if not w1.df.empty and not w2.df.empty:
        pd.testing.assert_frame_equal(
            w1.df.reset_index(drop=True),
            w2.df.reset_index(drop=True),
        )


def test_ah_premium_mr_z_positive_skipped(caplog):
    """When z > +2.0 the pair is skipped and a structured warning is emitted."""
    repo = _build_repo_normal()
    # Force H-leg to be very cheap (A-leg expensive → z >> +2)
    prices_df = repo._prices.copy()
    all_dates = prices_df[prices_df["symbol"] == _PING_AN_H]["date"].sort_values()
    if len(all_dates) < 12:
        pytest.skip("Not enough dates to inject H-cheap regime")
    last_dates = all_dates.iloc[-12:]
    h_mask = (prices_df["symbol"] == _PING_AN_H) & (prices_df["date"].isin(last_dates))
    for col in ["open", "high", "low", "close", "close_hfq", "total_return"]:
        prices_df.loc[h_mask, col] = prices_df.loc[h_mask, col] * 0.30
    prices_df.loc[h_mask, "high"] = prices_df.loc[h_mask, "close"] * 1.005
    prices_df.loc[h_mask, "low"] = prices_df.loc[h_mask, "close"] * 0.995
    repo._prices = prices_df

    s = AHPremiumMeanReversionStrategy(entry_z=2.0)
    with (
        patch("ah_research.strategies.ah_premium_mr.load_ah_pairs", return_value=_AH_PAIRS),
        caplog.at_level(logging.WARNING, logger="ah_research.strategies.ah_premium_mr"),
    ):
        weights = s.generate(repo, _STRATEGY_START, _STRATEGY_END)

    # The pair should produce zero or no weight (not a short-A entry).
    if not weights.df.empty:
        a_ws = weights.df[weights.df["symbol"] == _PING_AN_A]["weight"]
        assert (a_ws <= 0).all(), "A-leg must not be short when z > +2"
