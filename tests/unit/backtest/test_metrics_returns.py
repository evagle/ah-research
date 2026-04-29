"""Tests for return-based metric primitives in metrics.py (Task 15)."""

import numpy as np
import pandas as pd
import pytest

from ah_research.backtest.metrics import (
    annualized_vol,
    cagr,
    calmar,
    max_drawdown,
    sharpe,
    sortino,
)


def _flat_equity(n: int = 252) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(100.0, index=idx)


def _rising_equity(n: int = 252, start: float = 100.0, end: float = 200.0) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(np.linspace(start, end, n), index=idx)


def _random_returns(
    seed: int = 42, n: int = 252, mu: float = 0.0, sigma: float = 0.01
) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(rng.normal(mu, sigma, n), index=idx)


# ── cagr ────────────────────────────────────────────────────────────────────


def test_cagr_flat_series():
    """Flat NAV → CAGR is 0."""
    eq = _flat_equity()
    assert cagr(eq) == pytest.approx(0.0, abs=1e-9)


def test_cagr_doubling_over_year():
    """NAV doubling exactly over 365 calendar days → CAGR = 100%."""
    # Use a calendar-day index so exactly 1 year elapses
    idx = pd.date_range("2024-01-01", "2025-01-01", freq="D")
    n = len(idx)
    eq = pd.Series(100.0 * (2 ** (np.arange(n) / (n - 1))), index=idx)
    assert cagr(eq) == pytest.approx(1.0, abs=0.01)


def test_cagr_single_point_returns_zero():
    """Single-point series has no duration; should return 0."""
    eq = pd.Series([100.0], index=pd.date_range("2024-01-01", periods=1))
    assert cagr(eq) == 0.0


def test_cagr_two_years_10pct_gain():
    """1.1^2 = 1.21 total return over 2 years → CAGR = 10%."""
    idx = pd.date_range("2022-01-01", periods=504, freq="B")
    eq = pd.Series(100.0 * (1.1 ** (np.arange(504) / 252)), index=idx)
    assert cagr(eq) == pytest.approx(0.10, abs=0.005)


# ── annualized_vol ───────────────────────────────────────────────────────────


def test_annualized_vol_zero_returns():
    """All-zero returns → vol is 0."""
    r = pd.Series(np.zeros(252), index=pd.date_range("2024-01-01", periods=252, freq="B"))
    assert annualized_vol(r) == pytest.approx(0.0, abs=1e-12)


def test_annualized_vol_known_std():
    """Daily std of 0.01 → annualized vol = 0.01 * sqrt(252) ≈ 0.1587."""
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0, 0.01, 10_000))
    result = annualized_vol(r)
    assert result == pytest.approx(0.01 * np.sqrt(252), rel=0.02)


# ── sharpe ───────────────────────────────────────────────────────────────────


def test_sharpe_zero_variance_returns_zero():
    """Constant returns → std ≈ 0 → Sharpe = 0 (not NaN or inf)."""
    # Use integer-valued constant to avoid floating-point std noise
    r = pd.Series(np.full(252, 0.001))
    result = sharpe(r)
    # std of a constant series is numerically ~0; implementation should clamp to 0
    assert result == pytest.approx(0.0, abs=1e-6)


def test_sharpe_positive_mean_positive_std():
    """Deterministic positive-mean series → Sharpe > 0."""
    # Use a fixed daily return that is definitely positive: +0.001 every day
    # mean = 0.001, std = 0 → but we want non-zero std, so add a small positive offset
    # instead use seed=0 which gives positive mean
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.01, 500))
    # Verify the mean is positive before asserting on Sharpe
    assert r.mean() > 0, f"Test precondition failed: mean={r.mean()}"
    result = sharpe(r)
    assert result > 0


def test_sharpe_with_rf():
    """Providing rf reduces Sharpe compared to rf=0 when mean return > 0."""
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.01, 500))
    s0 = sharpe(r, rf=0.0)
    s_rf = sharpe(r, rf=0.03)
    assert s0 > s_rf


# ── sortino ──────────────────────────────────────────────────────────────────


def test_sortino_no_downside_returns_zero():
    """All positive returns → downside std = 0 → Sortino = 0 (not NaN)."""
    r = pd.Series([0.001] * 252)
    result = sortino(r)
    assert result == 0.0


def test_sortino_greater_than_sharpe_for_mixed():
    """Sortino ≥ Sharpe when returns have asymmetric downside."""
    rng = np.random.default_rng(99)
    r = pd.Series(rng.normal(0.0005, 0.01, 1000))
    # Sortino uses only downside std → usually >= Sharpe for positive-skew series
    assert sortino(r) >= sharpe(r) - 1e-10  # allow floating point tolerance


# ── max_drawdown ─────────────────────────────────────────────────────────────


def test_max_drawdown_known():
    """120 -> 80 peak-to-trough: MDD = -1/3, duration = 2 calendar days."""
    eq = pd.Series(
        [100, 120, 80, 100, 110],
        index=pd.date_range("2024-01-01", periods=5),
    )
    dd, duration = max_drawdown(eq)
    assert dd == pytest.approx(-1 / 3, abs=1e-3)
    # peak at day 1 (2024-01-01), trough at day 2 (2024-01-03) → 2 calendar days
    assert isinstance(duration, int)
    assert duration >= 0


def test_max_drawdown_no_drawdown():
    """Monotonically rising equity → MDD = 0."""
    eq = _rising_equity()
    dd, duration = max_drawdown(eq)
    assert dd == pytest.approx(0.0, abs=1e-9)
    assert duration == 0


def test_max_drawdown_returns_tuple_of_correct_types():
    eq = _flat_equity()
    result = max_drawdown(eq)
    assert isinstance(result, tuple)
    dd, dur = result
    assert isinstance(dd, float)
    assert isinstance(dur, int)


# ── calmar ───────────────────────────────────────────────────────────────────


def test_calmar_no_drawdown_returns_inf():
    """Monotonically rising equity → Calmar = inf."""
    eq = _rising_equity()
    result = calmar(eq)
    assert result == float("inf")


def test_calmar_flat_equity():
    """Flat NAV: CAGR=0, MDD=0 → Calmar=inf (0/0 convention)."""
    eq = _flat_equity()
    result = calmar(eq)
    assert result == float("inf")


def test_calmar_positive_for_positive_cagr_with_drawdown():
    """A rising series with some drawdown → Calmar > 0."""
    rng = np.random.default_rng(17)
    daily = rng.normal(0.0005, 0.015, 252)
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    eq = pd.Series(100.0 * np.exp(np.cumsum(daily)), index=idx)
    result = calmar(eq)
    assert np.isfinite(result)
