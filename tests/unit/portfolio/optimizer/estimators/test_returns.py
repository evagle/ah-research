from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from ah_research.portfolio.optimizer.errors import ValidationError
from ah_research.portfolio.optimizer.estimators.returns import (
    ExpectedReturnsEstimator,
    HistoricalMeanReturns,
    SignalBasedReturns,
    UserSuppliedReturns,
)


def _prices_fixture(symbols: list[str], n_days: int = 260, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    rows = []
    for sym in symbols:
        r = rng.normal(0, 0.01, size=n_days)
        prices = 100 * np.exp(np.cumsum(r))
        for d, p, ret in zip(dates, prices, r, strict=True):
            rows.append({"ds": d, "symbol": sym, "close_hfq": p, "total_return": ret})
    return pd.DataFrame(rows)


@pytest.fixture
def prices_repo():
    """Build (symbols, mocked-repo) for HistoricalMeanReturns tests.

    Factored out so the three historical-mean tests below stop duplicating
    the same 4-line setup. Returns a callable so each test picks its own
    symbol list (different cardinality) but shares the repo+fixture wiring.
    """

    def _build(symbols: list[str], seed: int = 0) -> tuple[list[str], MagicMock]:
        prices = _prices_fixture(symbols, seed=seed)
        repo = MagicMock()
        repo.get_prices.return_value = prices
        return symbols, repo

    return _build


def test_user_supplied_returns_passthrough():
    mu = pd.Series({"600519.SH": 0.05, "000858.SZ": 0.03})
    est = UserSuppliedReturns(mu)
    out = est.estimate(["600519.SH", "000858.SZ"], pd.Timestamp("2025-12-31"), MagicMock())
    pd.testing.assert_series_equal(out, mu)


def test_user_supplied_returns_raises_on_index_mismatch():
    mu = pd.Series({"600519.SH": 0.05})
    est = UserSuppliedReturns(mu)
    with pytest.raises(ValidationError, match="missing"):
        est.estimate(["600519.SH", "000858.SZ"], pd.Timestamp("2025-12-31"), MagicMock())


@pytest.mark.parametrize(
    ("shrinkage", "shrink_to"),
    [
        (0.0, "zero"),
        (0.5, "zero"),
        (1.0, "zero"),
        (0.5, "cross_sectional_mean"),
        (1.0, "cross_sectional_mean"),
    ],
    ids=[
        "no-shrinkage",
        "half-toward-zero",
        "full-toward-zero",
        "half-toward-xs-mean",
        "full-toward-xs-mean",
    ],
)
def test_historical_mean_smoke(prices_repo, shrinkage: float, shrink_to: str) -> None:
    """Smoke: across all shrinkage configurations the estimator returns a
    finite float64 Series indexed by the requested symbols."""
    symbols, repo = prices_repo(["600519.SH", "000858.SZ"])
    est = HistoricalMeanReturns(lookback_days=252, shrinkage=shrinkage, shrink_to=shrink_to)
    out = est.estimate(symbols, pd.Timestamp("2025-12-31"), repo)
    assert list(out.index) == symbols
    assert out.dtype == np.float64
    assert np.isfinite(out.values).all()


def test_historical_mean_full_shrinkage_collapses_to_cross_sectional_mean(prices_repo) -> None:
    symbols, repo = prices_repo(["A", "B", "C"])
    est = HistoricalMeanReturns(lookback_days=252, shrinkage=1.0, shrink_to="cross_sectional_mean")
    out = est.estimate(symbols, pd.Timestamp("2025-12-31"), repo)
    # all entries equal (within tol)
    assert out.std() < 1e-10


def test_historical_mean_zero_shrinkage_equals_raw(prices_repo) -> None:
    symbols, repo = prices_repo(["A", "B"])
    est_raw = HistoricalMeanReturns(lookback_days=252, shrinkage=0.0)
    est_half = HistoricalMeanReturns(lookback_days=252, shrinkage=0.5, shrink_to="zero")
    raw = est_raw.estimate(symbols, pd.Timestamp("2025-12-31"), repo)
    half = est_half.estimate(symbols, pd.Timestamp("2025-12-31"), repo)
    np.testing.assert_allclose(half.values, 0.5 * raw.values, atol=1e-12)


def test_signal_based_returns_maps_signal_to_spread():
    """Top-ranked signal maps to +spread, bottom to -spread (long-short scale)."""
    symbols = ["A", "B", "C", "D"]
    prices = _prices_fixture(symbols)

    # fake signal strategy with deterministic signals
    fake_signals = pd.DataFrame(
        {"A": [1.0], "B": [0.5], "C": [-0.5], "D": [-1.0]}, index=[pd.Timestamp("2025-12-31")]
    )
    strat = MagicMock()
    strat.generate.return_value = fake_signals

    repo = MagicMock()
    repo.get_prices.return_value = prices

    est = SignalBasedReturns(strat, spread=0.02, neutralize_sector=False)
    out = est.estimate(symbols, pd.Timestamp("2025-12-31"), repo)

    assert out.loc["A"] == pytest.approx(0.02, abs=1e-10)  # top rank
    assert out.loc["D"] == pytest.approx(-0.02, abs=1e-10)  # bottom rank


def test_all_estimators_satisfy_protocol():
    for est in (
        UserSuppliedReturns(pd.Series()),
        HistoricalMeanReturns(),
        SignalBasedReturns(MagicMock()),
    ):
        assert isinstance(est, ExpectedReturnsEstimator)
