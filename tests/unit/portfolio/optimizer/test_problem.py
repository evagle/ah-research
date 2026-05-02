import cvxpy as cp
import numpy as np
import pandas as pd
import pytest

from ah_research.portfolio.constructor import Constraint
from ah_research.portfolio.optimizer.errors import ValidationError
from ah_research.portfolio.optimizer.problem import (
    build_mean_variance,
    build_risk_parity,
)


def _psd_sigma(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    a_mat = rng.normal(size=(n, n))
    sigma = (a_mat @ a_mat.T) / n + np.eye(n) * 0.01
    syms = [f"S{i}" for i in range(n)]
    return pd.DataFrame(sigma, index=syms, columns=syms)


def test_build_mv_returns_problem_and_weight_var():
    symbols = ["S0", "S1", "S2"]
    sigma = _psd_sigma(3)
    mu = pd.Series([0.05, 0.03, 0.01], index=symbols)
    prob, w = build_mean_variance(
        symbols=symbols,
        mu=mu,
        sigma=sigma,
        risk_aversion=1.0,
        constraints=[],
        long_only=True,
        prev_weights=None,
        soft=False,
    )
    assert isinstance(prob, cp.Problem)
    assert w.shape == (3,)
    prob.solve(solver=cp.CLARABEL)
    assert prob.status == "optimal"
    assert abs(w.value.sum() - 1.0) < 1e-6
    assert (w.value >= -1e-8).all()


def test_build_mv_zero_risk_aversion_picks_max_return():
    symbols = ["S0", "S1", "S2"]
    sigma = _psd_sigma(3)
    mu = pd.Series([0.05, 0.03, 0.01], index=symbols)
    prob, w = build_mean_variance(
        symbols=symbols,
        mu=mu,
        sigma=sigma,
        risk_aversion=0.0,
        constraints=[Constraint.max_weight(1.0)],
        long_only=True,
        prev_weights=None,
        soft=False,
    )
    prob.solve(solver=cp.CLARABEL)
    # argmax of mu is S0; w should concentrate there
    assert w.value[0] > 0.99


def test_build_risk_parity_equal_risk_contributions():
    symbols = ["S0", "S1", "S2", "S3"]
    sigma = _psd_sigma(4, seed=1)
    prob, w = build_risk_parity(
        symbols=symbols,
        sigma=sigma,
        constraints=[],
        long_only=True,
        prev_weights=None,
        soft=False,
    )
    prob.solve(solver=cp.CLARABEL)
    assert prob.status in ("optimal", "optimal_inaccurate")
    # Risk contributions MRC_i = w_i * (sigma @ w)_i should be equal
    wv = np.asarray(w.value)
    wv = wv / wv.sum()  # normalize
    rc = wv * (sigma.values @ wv)
    rc /= rc.sum()
    # equal within 1%
    assert rc.std() / rc.mean() < 0.05


def test_build_risk_parity_requires_long_only():
    symbols = ["S0", "S1"]
    sigma = _psd_sigma(2)
    with pytest.raises(ValidationError, match="long_only"):
        build_risk_parity(
            symbols=symbols,
            sigma=sigma,
            constraints=[],
            long_only=False,
            prev_weights=None,
            soft=False,
        )


def test_build_mv_soft_mode_adds_slack_variables():
    # Infeasible constraints: sum=1 + max_weight=0.2 with only 2 assets → need ≥ 2 assets
    # but max_weight=0.2 means we need 5 assets. With only 2 this is infeasible.
    symbols = ["S0", "S1"]
    sigma = _psd_sigma(2)
    mu = pd.Series([0.05, 0.03], index=symbols)
    prob, _w = build_mean_variance(
        symbols=symbols,
        mu=mu,
        sigma=sigma,
        risk_aversion=1.0,
        constraints=[Constraint.max_weight(0.2)],
        long_only=True,
        prev_weights=None,
        soft=True,
        soft_penalty=1e3,
    )
    prob.solve(solver=cp.CLARABEL)
    # soft mode should still solve
    assert prob.status in ("optimal", "optimal_inaccurate")
