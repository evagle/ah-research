"""Tests for benchmark-relative metrics and Newey-West alpha/beta (Task 17)."""

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from ah_research.backtest.metrics import (
    AlphaBetaNW,
    _andrews_lag,
    alpha_beta_newey_west,
    excess_return,
    information_ratio,
    tracking_error,
)

# ── _andrews_lag ──────────────────────────────────────────────────────────────


def test_andrews_lag_minimum_is_1():
    """For n=1 the formula gives < 1 but must be clamped to 1."""
    assert _andrews_lag(1) == 1
    # n=5: 4 * (5/100)^(2/9) ≈ 2.06 → lag = 2 (formula, not clamped)
    assert _andrews_lag(5) == 2


def test_andrews_lag_n100():
    """For n=100: 4 * (100/100)^(2/9) = 4 → lag = 4."""
    assert _andrews_lag(100) == 4


def test_andrews_lag_n1000():
    """For n=1000 the formula gives a larger lag."""
    lag = _andrews_lag(1000)
    assert lag > 4
    assert isinstance(lag, int)


# ── alpha_beta_newey_west ─────────────────────────────────────────────────────


def _synthetic_data(
    n: int = 1000,
    true_alpha: float = 0.0002,
    true_beta: float = 1.3,
    seed: int = 42,
) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    rb = rng.normal(0.0005, 0.01, n)
    rp = true_alpha + true_beta * rb + rng.normal(0, 0.005, n)
    return pd.Series(rp), pd.Series(rb)


def test_alpha_beta_t_stats_match_statsmodels():
    """alpha, beta and NW t-stats must match statsmodels reference to 1e-8."""
    rp, rb = _synthetic_data()
    n = len(rp)

    result = alpha_beta_newey_west(rp, rb)

    # Reference: raw statsmodels call
    x_ref = sm.add_constant(rb.to_numpy())
    lag_ref = int(4 * (n / 100) ** (2 / 9))
    ref = sm.OLS(rp.to_numpy(), x_ref).fit(cov_type="HAC", cov_kwds={"maxlags": lag_ref})

    assert result.alpha == pytest.approx(float(ref.params[0]), abs=1e-10)
    assert result.beta == pytest.approx(float(ref.params[1]), abs=1e-10)
    assert result.alpha_t_stat == pytest.approx(float(ref.tvalues[0]), abs=1e-8)
    assert result.beta_t_stat == pytest.approx(float(ref.tvalues[1]), abs=1e-8)


def test_alpha_beta_se_match_statsmodels():
    """Standard errors must also match statsmodels to 1e-10."""
    rp, rb = _synthetic_data()
    n = len(rp)

    result = alpha_beta_newey_west(rp, rb)

    x_ref = sm.add_constant(rb.to_numpy())
    lag_ref = int(4 * (n / 100) ** (2 / 9))
    ref = sm.OLS(rp.to_numpy(), x_ref).fit(cov_type="HAC", cov_kwds={"maxlags": lag_ref})

    assert result.alpha_se == pytest.approx(float(ref.bse[0]), abs=1e-10)
    assert result.beta_se == pytest.approx(float(ref.bse[1]), abs=1e-10)


def test_alpha_beta_pvalue_match_statsmodels():
    """p-values must match statsmodels to 1e-8."""
    rp, rb = _synthetic_data()
    n = len(rp)
    result = alpha_beta_newey_west(rp, rb)

    x_ref = sm.add_constant(rb.to_numpy())
    lag_ref = int(4 * (n / 100) ** (2 / 9))
    ref = sm.OLS(rp.to_numpy(), x_ref).fit(cov_type="HAC", cov_kwds={"maxlags": lag_ref})

    assert result.alpha_pvalue == pytest.approx(float(ref.pvalues[0]), abs=1e-8)


def test_alpha_beta_newey_west_returns_dataclass():
    """Return type must be AlphaBetaNW (frozen dataclass)."""
    rp, rb = _synthetic_data(n=200)
    result = alpha_beta_newey_west(rp, rb)
    assert isinstance(result, AlphaBetaNW)


def test_alpha_beta_newey_west_lag_stored():
    """newey_west_lag field must equal the formula value."""
    rp, rb = _synthetic_data(n=500)
    result = alpha_beta_newey_west(rp, rb)
    expected_lag = _andrews_lag(500)
    assert result.newey_west_lag == expected_lag


def test_alpha_beta_aligned_on_inner_join():
    """Series of different length: only overlapping index is used."""
    rng = np.random.default_rng(0)
    idx_full = pd.date_range("2024-01-01", periods=300, freq="B")
    idx_short = idx_full[:200]
    rp = pd.Series(rng.normal(0, 0.01, 300), index=idx_full)
    rb = pd.Series(rng.normal(0, 0.01, 200), index=idx_short)

    result = alpha_beta_newey_west(rp, rb)
    # Should succeed with n=200 rows (the intersection)
    assert result.newey_west_lag == _andrews_lag(200)


# ── excess_return ─────────────────────────────────────────────────────────────


def test_excess_return_zero_when_equal():
    """Portfolio == benchmark → excess return = 0."""
    r = pd.Series(np.random.default_rng(0).normal(0, 0.01, 252))
    assert excess_return(r, r) == pytest.approx(0.0, abs=1e-12)


def test_excess_return_positive_when_portfolio_better():
    """Portfolio that outperforms benchmark daily → positive excess return."""
    rng = np.random.default_rng(1)
    rb = pd.Series(rng.normal(0, 0.01, 252))
    rp = rb + 0.001  # 10 bps per day outperformance
    er = excess_return(rp, rb)
    assert er > 0


def test_excess_return_annualized():
    """Mean daily excess of 0.001 * 252 ~ 0.252 annualized."""
    rng = np.random.default_rng(2)
    rb = pd.Series(rng.normal(0, 0.01, 1000))
    rp = rb + 0.001
    er = excess_return(rp, rb)
    assert er == pytest.approx(0.001 * 252, rel=0.01)


# ── tracking_error ────────────────────────────────────────────────────────────


def test_tracking_error_zero_when_equal():
    r = pd.Series(np.random.default_rng(3).normal(0, 0.01, 252))
    assert tracking_error(r, r) == pytest.approx(0.0, abs=1e-12)


def test_tracking_error_positive_when_different():
    rng = np.random.default_rng(4)
    rp = pd.Series(rng.normal(0, 0.01, 252))
    rb = pd.Series(rng.normal(0, 0.01, 252))
    assert tracking_error(rp, rb) > 0


# ── information_ratio ─────────────────────────────────────────────────────────


def test_information_ratio_zero_te_returns_zero():
    """Zero tracking error → IR = 0 (not NaN or inf)."""
    r = pd.Series(np.random.default_rng(5).normal(0, 0.01, 252))
    result = information_ratio(r, r)
    assert result == pytest.approx(0.0, abs=1e-12)


def test_information_ratio_positive_for_outperforming_portfolio():
    rng = np.random.default_rng(6)
    rb = pd.Series(rng.normal(0, 0.01, 500))
    rp = rb + 0.001
    ir = information_ratio(rp, rb)
    assert ir > 0
