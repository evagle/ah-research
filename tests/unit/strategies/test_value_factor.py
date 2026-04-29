"""Tests for ValueFactorStrategy."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from ah_research.backtest.types import Signals, Weights
from ah_research.strategies.value_factor import ValueFactorStrategy
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ── fixtures ──────────────────────────────────────────────────────────────────

_SYMBOLS = [
    "600000.SH",
    "600016.SH",
    "600028.SH",
    "600036.SH",
    "601318.SH",
]


@pytest.fixture
def repo():
    # Start 120 days before strategy window to ensure fundamentals are available.
    return build_synthetic_market(
        start=date(2023, 9, 1),
        end=date(2024, 3, 31),
        symbols=_SYMBOLS,
    )


# ── generate ──────────────────────────────────────────────────────────────────


def test_value_factor_returns_signals(repo):
    """generate() returns a valid Signals object with month-end dates."""
    s = ValueFactorStrategy()
    sigs = s.generate(repo, date(2024, 1, 1), date(2024, 3, 31))
    assert isinstance(sigs, Signals)
    # Three month-ends in Jan-Mar 2024
    assert sigs.df["date"].nunique() == 3


def test_value_factor_signals_have_valid_symbols(repo):
    """All symbols in the signal frame are present in the fixture universe."""
    s = ValueFactorStrategy()
    sigs = s.generate(repo, date(2024, 1, 1), date(2024, 3, 31))
    assert sigs.df["symbol"].isin(_SYMBOLS).all()


def test_value_factor_signals_no_nan(repo):
    """Signals must not contain NaN values."""
    s = ValueFactorStrategy()
    sigs = s.generate(repo, date(2024, 1, 1), date(2024, 3, 31))
    assert not sigs.df["signal"].isna().any()


def test_value_factor_degenerate_empty_universe(repo):
    """When universe returns no rows, generate() returns empty Signals.

    We monkey-patch get_universe_over_time to return an empty frame to simulate
    a universe with no CSI300 members (e.g. before the index was constructed).
    """
    import pandas as pd

    original = repo.get_universe_over_time

    def _empty_universe(index, start, end, *, freq="ME"):
        return pd.DataFrame(columns=["date", "index_name", "symbol", "weight"])

    repo.get_universe_over_time = _empty_universe  # type: ignore[method-assign]
    try:
        s = ValueFactorStrategy()
        sigs = s.generate(repo, date(2024, 1, 1), date(2024, 3, 31))
        assert isinstance(sigs, Signals)
        assert len(sigs.df) == 0
    finally:
        repo.get_universe_over_time = original  # type: ignore[method-assign]


# ── to_weights ────────────────────────────────────────────────────────────────


def test_value_factor_to_weights_returns_weights(repo):
    """to_weights(signals, repo) produces valid Weights."""
    s = ValueFactorStrategy()
    sigs = s.generate(repo, date(2024, 1, 1), date(2024, 3, 31))
    if sigs.df.empty:
        pytest.skip("Empty signals - degenerate path tested elsewhere")
    weights = s.to_weights(sigs, repo)
    assert isinstance(weights, Weights)


def test_value_factor_to_weights_respects_max_weight(repo):
    """No weight exceeds max_weight."""
    s = ValueFactorStrategy(max_weight=0.05)
    sigs = s.generate(repo, date(2024, 1, 1), date(2024, 3, 31))
    if sigs.df.empty:
        pytest.skip("Empty signals")
    weights = s.to_weights(sigs, repo)
    assert (weights.df["weight"] <= 0.05 + 1e-9).all()


def test_value_factor_to_weights_empty_signals_ok(repo):
    """to_weights with empty signals returns empty Weights without error."""
    s = ValueFactorStrategy()
    empty_sigs = Signals.from_dataframe(
        pd.DataFrame(
            {
                "date": pd.Series([], dtype="datetime64[ns]"),
                "symbol": pd.Series([], dtype=str),
                "signal": pd.Series([], dtype=float),
            }
        )
    )
    weights = s.to_weights(empty_sigs, repo)
    assert isinstance(weights, Weights)
    assert len(weights.df) == 0


# ── mock-repo test for sharper assertion ─────────────────────────────────────


def _make_fundamentals_row(
    sym: str,
    pe: float,
    pb: float,
    dy: float,
) -> dict:
    report_d = pd.Timestamp("2023-12-31")
    pub_d = pd.Timestamp("2024-01-15")
    return {
        "symbol": sym,
        "report_date": report_d,
        "publication_date": pub_d,
        "known_as_of": pub_d,
        "statement_kind": "audited",
        "revenue": 1e10,
        "net_income": 3e9,
        "net_income_ex_nonrecurring": 2.95e9,
        "operating_cash_flow": 3.5e9,
        "capex": 2e8,
        "total_assets": 8e10,
        "total_equity": 5e10,
        "total_debt": 1e10,
        "goodwill": 0.0,
        "minority_interest": 1e8,
        "d_and_a": 3e8,
        "working_capital_change": 1e8,
        "pe": pe,
        "pb": pb,
        "ps": 10.0,
        "ev_ebitda": 15.0,
        "roe": 0.25,
        "roic": 0.22,
        "roa": 0.15,
        "gross_margin": 0.92,
        "net_margin": 0.30,
        "dividend_yield": dy,
        "market_cap": 2e12,
        "market_cap_free_float": 1.5e12,
        "is_soe": True,
        "is_stock_connect_eligible": True,
    }


def test_value_factor_ranks_by_composite_score():
    """Mock repo: symbol with low PE/PB and high div_yield ranks highest."""
    from ah_research.model.schemas import FundamentalsFrameSchema

    cheap_sym = "600001.SH"
    mid_sym = "600002.SH"
    exp_sym = "600003.SH"

    repo = build_synthetic_market(
        start=date(2023, 9, 1),
        end=date(2024, 1, 31),
        symbols=[cheap_sym, mid_sym, exp_sym],
    )

    custom_funds = FundamentalsFrameSchema.validate(
        pd.DataFrame(
            [
                _make_fundamentals_row(cheap_sym, pe=5.0, pb=0.5, dy=0.08),
                _make_fundamentals_row(mid_sym, pe=15.0, pb=1.5, dy=0.03),
                _make_fundamentals_row(exp_sym, pe=50.0, pb=8.0, dy=0.005),
            ]
        )
    )
    repo._fundamentals = custom_funds  # type: ignore[attr-defined]

    s = ValueFactorStrategy(quantile=0.5, sector_neutral=False)
    sigs = s.generate(repo, date(2024, 1, 1), date(2024, 1, 31))

    if sigs.df.empty:
        pytest.skip("No signals generated with custom fundamentals")

    # The cheapest symbol should have the highest composite score
    top_sym = sigs.df.loc[sigs.df["signal"].idxmax(), "symbol"]
    assert top_sym == cheap_sym, f"Expected {cheap_sym} to have highest signal, got {top_sym}"
