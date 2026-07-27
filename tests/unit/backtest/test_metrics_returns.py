"""Tests for return-based metric primitives in metrics.py (Task 15)."""

from __future__ import annotations

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

# ── Shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def flat_equity():
    """Callable: build a flat-NAV equity series of length n."""

    def _build(n: int = 252) -> pd.Series:
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        return pd.Series(100.0, index=idx)

    return _build


@pytest.fixture
def rising_equity():
    """Callable: build a linearly-rising equity series."""

    def _build(n: int = 252, start: float = 100.0, end: float = 200.0) -> pd.Series:
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        return pd.Series(np.linspace(start, end, n), index=idx)

    return _build


@pytest.fixture
def random_returns():
    """Callable: build a Gaussian return series with seeded RNG."""

    def _build(seed: int = 42, n: int = 252, mu: float = 0.0, sigma: float = 0.01) -> pd.Series:
        rng = np.random.default_rng(seed)
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        return pd.Series(rng.normal(mu, sigma, n), index=idx)

    return _build


# ── cagr ────────────────────────────────────────────────────────────────────


def _doubling_year() -> pd.Series:
    """NAV doubling exactly over 365 calendar days → CAGR = 100%."""
    idx = pd.date_range("2024-01-01", "2025-01-01", freq="D")
    n = len(idx)
    return pd.Series(100.0 * (2 ** (np.arange(n) / (n - 1))), index=idx)


def _two_year_10pct() -> pd.Series:
    """1.1^2 = 1.21 total return over 2 years → CAGR = 10%."""
    idx = pd.date_range("2022-01-01", periods=504, freq="B")
    return pd.Series(100.0 * (1.1 ** (np.arange(504) / 252)), index=idx)


@pytest.mark.parametrize(
    ("equity_factory", "expected_cagr", "tol"),
    [
        (lambda flat: flat(), 0.0, 1e-9),
        (lambda flat: pd.Series([100.0], index=pd.date_range("2024-01-01", periods=1)), 0.0, 1e-9),
    ],
    ids=["flat-series", "single-point"],
)
def test_cagr_zero_baselines(equity_factory, expected_cagr, tol, flat_equity) -> None:  # type: ignore[no-untyped-def]
    eq = equity_factory(flat_equity)
    assert cagr(eq) == pytest.approx(expected_cagr, abs=tol)


def test_cagr_doubling_over_year_is_100pct() -> None:
    assert cagr(_doubling_year()) == pytest.approx(1.0, abs=0.01)


def test_cagr_two_years_10pct_gain() -> None:
    assert cagr(_two_year_10pct()) == pytest.approx(0.10, abs=0.005)


# ── annualized_vol ───────────────────────────────────────────────────────────


def test_annualized_vol_zero_returns() -> None:
    """All-zero returns → vol is 0."""
    r = pd.Series(np.zeros(252), index=pd.date_range("2024-01-01", periods=252, freq="B"))
    assert annualized_vol(r) == pytest.approx(0.0, abs=1e-12)


def test_annualized_vol_known_std() -> None:
    """Daily std of 0.01 → annualized vol = 0.01 * sqrt(252) ≈ 0.1587."""
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0, 0.01, 10_000))
    assert annualized_vol(r) == pytest.approx(0.01 * np.sqrt(252), rel=0.02)


# ── sharpe ───────────────────────────────────────────────────────────────────


def test_sharpe_zero_variance_returns_zero() -> None:
    """Constant returns → std ≈ 0 → Sharpe = 0 (not NaN or inf)."""
    r = pd.Series(np.full(252, 0.001))
    assert sharpe(r) == pytest.approx(0.0, abs=1e-6)


def test_sharpe_positive_mean_positive_std(random_returns) -> None:  # type: ignore[no-untyped-def]
    r = random_returns(seed=0, mu=0.001, sigma=0.01, n=500)
    assert r.mean() > 0, f"Test precondition failed: mean={r.mean()}"
    assert sharpe(r) > 0


def test_sharpe_with_positive_rf_reduces_metric(random_returns) -> None:  # type: ignore[no-untyped-def]
    """Providing rf reduces Sharpe compared to rf=0 when mean return > 0."""
    r = random_returns(seed=0, mu=0.001, sigma=0.01, n=500)
    assert sharpe(r, rf=0.0) > sharpe(r, rf=0.03)


# ── sortino ──────────────────────────────────────────────────────────────────


def test_sortino_no_downside_returns_zero() -> None:
    """All positive returns → downside std = 0 → Sortino = 0 (not NaN)."""
    r = pd.Series([0.001] * 252)
    assert sortino(r) == 0.0


def test_sortino_greater_than_sharpe_for_mixed(random_returns) -> None:  # type: ignore[no-untyped-def]
    """Sortino ≥ Sharpe when returns have asymmetric downside."""
    r = random_returns(seed=99, mu=0.0005, sigma=0.01, n=1000)
    assert sortino(r) >= sharpe(r) - 1e-10  # floating-point tolerance


# ── max_drawdown ─────────────────────────────────────────────────────────────


def test_max_drawdown_known() -> None:
    """120 → 80 peak-to-trough: MDD = -1/3."""
    eq = pd.Series(
        [100, 120, 80, 100, 110],
        index=pd.date_range("2024-01-01", periods=5),
    )
    dd, duration = max_drawdown(eq)
    assert dd == pytest.approx(-1 / 3, abs=1e-3)
    assert isinstance(duration, int)
    assert duration >= 0


def test_max_drawdown_zero_for_monotonic_equity(rising_equity) -> None:  # type: ignore[no-untyped-def]
    dd, duration = max_drawdown(rising_equity())
    assert dd == pytest.approx(0.0, abs=1e-9)
    assert duration == 0


def test_max_drawdown_returns_tuple_of_correct_types(flat_equity) -> None:  # type: ignore[no-untyped-def]
    dd, dur = max_drawdown(flat_equity())
    assert isinstance(dd, float)
    assert isinstance(dur, int)


# ── calmar ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "equity_factory_name",
    ["rising_equity", "flat_equity"],
    ids=["rising-no-drawdown", "flat-zero-over-zero"],
)
def test_calmar_inf_when_no_drawdown(equity_factory_name: str, request) -> None:  # type: ignore[no-untyped-def]
    """Calmar = inf when MDD is 0 (no drawdown / 0/0 convention)."""
    factory = request.getfixturevalue(equity_factory_name)
    assert calmar(factory()) == float("inf")


def test_calmar_finite_for_positive_cagr_with_drawdown() -> None:
    rng = np.random.default_rng(17)
    daily = rng.normal(0.0005, 0.015, 252)
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    eq = pd.Series(100.0 * np.exp(np.cumsum(daily)), index=idx)
    assert np.isfinite(calmar(eq))
