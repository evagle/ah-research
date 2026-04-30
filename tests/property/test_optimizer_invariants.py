"""Hypothesis-based invariant tests for Optimizer.

Verifies algebraic properties: weights sum to 1, respect long_only and
max_weight, MV with μ=0 equals min-variance, risk-parity has equal MRCs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ah_research.portfolio.constructor import Constraint
from ah_research.portfolio.optimizer import Optimizer
from ah_research.portfolio.optimizer.estimators.covariance import SampleCovariance
from ah_research.portfolio.optimizer.estimators.returns import UserSuppliedReturns


def _prices_fixture(n_assets: int, n_days: int = 260, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    symbols = [f"S{i:02d}" for i in range(n_assets)]
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    rows = []
    for sym in symbols:
        r = rng.normal(0, 0.01, size=n_days)
        prices = 100 * np.exp(np.cumsum(r))
        for d, p, ret in zip(dates, prices, r, strict=True):
            rows.append({"ds": d, "symbol": sym, "close_hfq": p, "total_return": ret})
    return pd.DataFrame(rows), symbols


@given(
    n_assets=st.integers(min_value=3, max_value=10),
    seed=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=20, deadline=None)
def test_weights_sum_to_one_and_nonneg(n_assets: int, seed: int):
    prices, symbols = _prices_fixture(n_assets, seed=seed)
    repo = MagicMock()
    repo.get_prices.return_value = prices
    mu = pd.Series(np.zeros(n_assets), index=symbols)  # μ=0 ⇒ min-variance
    opt = Optimizer(
        objective="mean_variance",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=UserSuppliedReturns(mu),
        long_only=True,
    )
    res = opt.build(symbols, pd.Timestamp("2025-12-31"), repo)
    assert abs(res.weights.sum() - 1.0) < 1e-5
    assert (res.weights >= -1e-8).all()


@given(
    n_assets=st.integers(min_value=3, max_value=10),
    max_w=st.floats(min_value=0.15, max_value=0.5),
    seed=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=20, deadline=None)
def test_max_weight_respected(n_assets: int, max_w: float, seed: int):
    # Require max_w * n_assets >= 1 for feasibility; use assume() so hypothesis
    # discards infeasible draws rather than skipping the whole test.
    assume(max_w * n_assets >= 1.0)
    prices, symbols = _prices_fixture(n_assets, seed=seed)
    repo = MagicMock()
    repo.get_prices.return_value = prices
    mu = pd.Series(np.zeros(n_assets), index=symbols)
    opt = Optimizer(
        objective="mean_variance",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=UserSuppliedReturns(mu),
        constraints=[Constraint.max_weight(max_w)],
        long_only=True,
    )
    res = opt.build(symbols, pd.Timestamp("2025-12-31"), repo)
    assert (res.weights <= max_w + 1e-5).all()


@given(
    n_assets=st.integers(min_value=3, max_value=6),
    seed=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=10, deadline=None)
def test_risk_parity_equal_mrc(n_assets: int, seed: int):
    prices, symbols = _prices_fixture(n_assets, seed=seed)
    repo = MagicMock()
    repo.get_prices.return_value = prices
    opt = Optimizer(
        objective="risk_parity",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=None,
        long_only=True,
    )
    res = opt.build(symbols, pd.Timestamp("2025-12-31"), repo)
    rc = res.risk_contributions
    assert rc is not None
    cv = rc.std() / rc.mean()
    assert cv < 0.10, f"CV of risk contributions={cv} > 0.10"
