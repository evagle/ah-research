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
    # Slack of 5e-5 reflects realistic OSQP boundary residuals; the
    # default ``solver_tol=1e-6`` does not bound boundary violations
    # exactly. Hypothesis surfaced a 1.2e-5 violation under the old 1e-5
    # slack at seed=80, n_assets=5, max_w≈0.2043.
    assert (res.weights <= max_w + 5e-5).all()


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


@given(
    n_assets=st.integers(min_value=4, max_value=8),
    turnover_budget=st.floats(min_value=0.10, max_value=0.40),
    seed=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=15, deadline=None)
def test_max_turnover_respected(n_assets: int, turnover_budget: float, seed: int):
    """When ``Constraint.max_turnover`` is set with an anchor, the L1 distance
    between solution weights and the anchor must not exceed the budget.
    Anchor is equal-weight (a representative prior portfolio)."""
    prices, symbols = _prices_fixture(n_assets, seed=seed)
    repo = MagicMock()
    repo.get_prices.return_value = prices
    mu = pd.Series(np.zeros(n_assets), index=symbols)
    anchor = pd.Series(1.0 / n_assets, index=symbols)
    opt = Optimizer(
        objective="mean_variance",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=UserSuppliedReturns(mu),
        constraints=[Constraint.max_turnover(turnover_budget, baseline=anchor)],
        long_only=True,
    )
    # max_turnover is skipped on the first rebalance unless prev_weights is
    # passed; pass the anchor so the constraint actually binds.
    res = opt.build(symbols, pd.Timestamp("2025-12-31"), repo, prev_weights=anchor)
    l1_diff = float((res.weights - anchor).abs().sum())
    # 1e-4 slack for solver tolerance; turnover constraint uses CVXPY's solver_tol.
    assert l1_diff <= turnover_budget + 1e-4, (
        f"L1 turnover {l1_diff:.6f} exceeds budget {turnover_budget:.6f}"
    )


@given(
    n_assets=st.integers(min_value=3, max_value=6),
    seed=st.integers(min_value=0, max_value=30),
)
@settings(max_examples=10, deadline=None)
def test_mv_variance_monotonic_in_risk_aversion(n_assets: int, seed: int):
    """Mean-variance with the same μ and Σ but a *higher* risk-aversion
    coefficient should yield a portfolio with weakly *lower* expected
    variance. This is a textbook MV property and is the cleanest single
    invariant exposing whether the objective is wired correctly.

    We use random nonzero μ so the optimizer actually trades return for risk;
    with μ=0 every RA produces the same min-variance portfolio.
    """
    rng = np.random.default_rng(seed)
    prices, symbols = _prices_fixture(n_assets, seed=seed)
    mu = pd.Series(rng.uniform(0.0, 0.10, size=n_assets), index=symbols)

    repo = MagicMock()
    repo.get_prices.return_value = prices

    def _solve(ra: float) -> float:
        opt = Optimizer(
            objective="mean_variance",
            cov_estimator=SampleCovariance(min_periods=60),
            returns_estimator=UserSuppliedReturns(mu),
            risk_aversion=ra,
            long_only=True,
        )
        return opt.build(symbols, pd.Timestamp("2025-12-31"), repo).expected_variance

    var_low = _solve(ra=0.5)
    var_high = _solve(ra=10.0)
    # 1e-6 slack for solver noise; we want monotonic-or-equal, not strict.
    assert var_high <= var_low + 1e-6, (
        f"Higher RA should yield ≤ variance: var(RA=10)={var_high:.6e} > var(RA=0.5)={var_low:.6e}"
    )
