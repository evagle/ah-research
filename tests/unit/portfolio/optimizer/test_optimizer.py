from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from ah_research.portfolio.constructor import Constraint
from ah_research.portfolio.optimizer import OptimizationResult, Optimizer
from ah_research.portfolio.optimizer.errors import (
    InfeasibleError,
    ValidationError,
)
from ah_research.portfolio.optimizer.estimators.covariance import SampleCovariance
from ah_research.portfolio.optimizer.estimators.returns import UserSuppliedReturns


def _prices_fixture(symbols: list[str], n_days: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    rows = []
    for sym in symbols:
        r = rng.normal(0, 0.01, size=n_days)
        prices = 100 * np.exp(np.cumsum(r))
        for d, p, ret in zip(dates, prices, r, strict=False):
            rows.append({"ds": d, "symbol": sym, "close_hfq": p, "total_return": ret})
    return pd.DataFrame(rows)


def _mock_repo(symbols: list[str]) -> MagicMock:
    repo = MagicMock()
    repo.get_prices.return_value = _prices_fixture(symbols)
    return repo


def test_optimizer_mv_returns_optimization_result():
    symbols = ["A", "B", "C"]
    repo = _mock_repo(symbols)
    mu = pd.Series([0.05, 0.03, 0.01], index=symbols)
    opt = Optimizer(
        objective="mean_variance",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=UserSuppliedReturns(mu),
        constraints=[Constraint.max_weight(0.5)],
        risk_aversion=1.0,
        long_only=True,
        lookback_days=252,
    )
    res = opt.build(symbols, pd.Timestamp("2025-12-31"), repo)
    assert isinstance(res, OptimizationResult)
    assert res.objective == "mean_variance"
    assert res.solver_status == "optimal"
    assert abs(res.weights.sum() - 1.0) < 1e-6
    assert (res.weights <= 0.5 + 1e-6).all()
    assert res.solve_time_ms >= 0


def test_optimizer_risk_parity_produces_equal_contributions():
    symbols = ["A", "B", "C", "D"]
    repo = _mock_repo(symbols)
    opt = Optimizer(
        objective="risk_parity",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=None,
        constraints=[],
        long_only=True,
        lookback_days=252,
    )
    res = opt.build(symbols, pd.Timestamp("2025-12-31"), repo)
    assert res.risk_contributions is not None
    rc = res.risk_contributions
    assert (rc.std() / rc.mean()) < 0.05


def test_optimizer_mv_requires_returns_estimator():
    with pytest.raises(ValidationError, match="returns_estimator"):
        Optimizer(
            objective="mean_variance",
            cov_estimator=SampleCovariance(),
            returns_estimator=None,
        )


def test_optimizer_rejects_cardinality_constraints():
    with pytest.raises(ValidationError, match="min_positions"):
        Optimizer(
            objective="mean_variance",
            cov_estimator=SampleCovariance(),
            returns_estimator=UserSuppliedReturns(pd.Series([0.05], index=["A"])),
            constraints=[Constraint.min_positions(5)],
        )


def test_optimizer_strict_mode_raises_on_infeasible():
    symbols = ["A", "B"]
    repo = _mock_repo(symbols)
    mu = pd.Series([0.05, 0.03], index=symbols)
    opt = Optimizer(
        objective="mean_variance",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=UserSuppliedReturns(mu),
        constraints=[Constraint.max_weight(0.2)],  # max_weight=0.2 with N=2 => sum(w) <= 0.4 < 1
        long_only=True,
        soft=False,
    )
    with pytest.raises(InfeasibleError):
        opt.build(symbols, pd.Timestamp("2025-12-31"), repo)


def test_optimizer_soft_mode_returns_soft_relaxed():
    symbols = ["A", "B"]
    repo = _mock_repo(symbols)
    mu = pd.Series([0.05, 0.03], index=symbols)
    opt = Optimizer(
        objective="mean_variance",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=UserSuppliedReturns(mu),
        constraints=[Constraint.max_weight(0.2)],
        long_only=True,
        soft=True,
    )
    res = opt.build(symbols, pd.Timestamp("2025-12-31"), repo)
    assert res.solver_status == "soft_relaxed"
    assert len(res.slack) > 0


def test_optimizer_inputs_hash_is_deterministic():
    symbols = ["A", "B"]
    repo = _mock_repo(symbols)
    mu = pd.Series([0.05, 0.03], index=symbols)
    opt1 = Optimizer(
        objective="mean_variance",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=UserSuppliedReturns(mu),
        risk_aversion=1.0,
    )
    opt2 = Optimizer(
        objective="mean_variance",
        cov_estimator=SampleCovariance(min_periods=60),
        returns_estimator=UserSuppliedReturns(mu),
        risk_aversion=1.0,
    )
    r1 = opt1.build(symbols, pd.Timestamp("2025-12-31"), repo)
    r2 = opt2.build(symbols, pd.Timestamp("2025-12-31"), repo)
    assert r1.inputs_hash == r2.inputs_hash
    assert len(r1.inputs_hash) == 64
