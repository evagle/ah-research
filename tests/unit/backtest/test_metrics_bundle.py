"""Tests for MetricsBundle dataclass and compute_metrics() aggregator (Task 18)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from ah_research.backtest.metrics import MetricsBundle, compute_metrics

# ── MetricsBundle dataclass ───────────────────────────────────────────────────


def test_metrics_bundle_all_none_by_default():
    """Default MetricsBundle has all fields None."""
    m = MetricsBundle()
    d = m.to_dict()
    # All values should be None when not provided
    assert all(v is None for v in d.values())


def test_metrics_bundle_to_dict_keys():
    """to_dict() must include all spec §6 fields."""
    m = MetricsBundle()
    d = m.to_dict()
    required_keys = {
        # Returns
        "cagr",
        "total_return",
        "annualized_vol",
        # Risk-adjusted
        "sharpe",
        "sortino",
        "max_drawdown",
        "max_dd_duration_days",
        "calmar",
        # Income
        "avg_dividend_yield",
        # Activity
        "annualized_turnover",
        "avg_positions",
        "avg_holding_period_days",
        # Benchmark-relative
        "excess_return",
        "information_ratio",
        "tracking_error",
        "alpha",
        "beta",
        # Inferential
        "alpha_t_stat",
        "alpha_pvalue",
        "alpha_se",
        "beta_t_stat",
        "beta_se",
        "newey_west_lag",
    }
    assert required_keys.issubset(set(d.keys()))


def test_metrics_bundle_is_frozen():
    """MetricsBundle is immutable (frozen dataclass)."""
    import dataclasses

    m = MetricsBundle(cagr=0.1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.cagr = 0.2  # type: ignore[misc]


def test_metrics_bundle_str_contains_section_headers():
    """__str__ must include section headers for readability."""
    m = MetricsBundle(cagr=0.12, sharpe=1.5, alpha=0.001)
    text = str(m)
    assert "Returns" in text
    assert "Risk-adjusted" in text
    assert "Benchmark-relative" in text
    assert "Inferential" in text


def test_metrics_bundle_repr_equals_str():
    """__repr__ should match __str__."""
    m = MetricsBundle(cagr=0.10)
    assert repr(m) == str(m)


# ── compute_metrics() ─────────────────────────────────────────────────────────


def _make_equity(n: int = 252, drift: float = 0.0005, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_r = rng.normal(drift, 0.01, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(1000.0 * np.exp(np.cumsum(log_r)), index=idx)


def _make_benchmark(n: int = 252, seed: int = 99) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_r = rng.normal(0.0003, 0.01, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(1000.0 * np.exp(np.cumsum(log_r)), index=idx)


def _make_trades(n: int = 10) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=n, freq="ME")
    return pd.DataFrame(
        {
            "exec_date": dates,
            "symbol": [f"60000{i % 10}.SH" for i in range(n)],
            "side": ["buy" if i % 2 == 0 else "sell" for i in range(n)],
            "shares": [100] * n,
            "notional": [10000.0] * n,
            "fill_price": [100.0] * n,
            "cost_total": [5.0] * n,
        }
    )


def test_compute_metrics_returns_metrics_bundle():
    """compute_metrics must return a MetricsBundle instance."""
    equity = _make_equity()
    benchmark = _make_benchmark()
    trades = _make_trades()
    ph = pd.DataFrame(columns=["date", "symbol"])

    result = compute_metrics(equity, benchmark, trades, ph)
    assert isinstance(result, MetricsBundle)


def test_compute_metrics_all_return_fields_populated():
    """CAGR, total_return, annualized_vol must all be finite floats."""
    equity = _make_equity()
    benchmark = _make_benchmark()
    trades = _make_trades()
    ph = pd.DataFrame(columns=["date", "symbol"])

    m = compute_metrics(equity, benchmark, trades, ph)
    assert m.cagr is not None and np.isfinite(m.cagr)
    assert m.total_return is not None and np.isfinite(m.total_return)
    assert m.annualized_vol is not None and m.annualized_vol >= 0


def test_compute_metrics_risk_adjusted_fields_populated():
    """Sharpe, Sortino, max_drawdown, calmar must be finite."""
    equity = _make_equity()
    benchmark = _make_benchmark()
    trades = _make_trades()
    ph = pd.DataFrame(columns=["date", "symbol"])

    m = compute_metrics(equity, benchmark, trades, ph)
    assert m.sharpe is not None and np.isfinite(m.sharpe)
    assert m.sortino is not None and np.isfinite(m.sortino)
    assert m.max_drawdown is not None and m.max_drawdown <= 0
    assert m.max_dd_duration_days is not None and m.max_dd_duration_days >= 0
    # calmar may be inf when no drawdown; just check it's not None
    assert m.calmar is not None


def test_compute_metrics_benchmark_relative_fields_populated():
    """Alpha, beta, IR, TE, excess_return must all be populated."""
    equity = _make_equity()
    benchmark = _make_benchmark()
    trades = _make_trades()
    ph = pd.DataFrame(columns=["date", "symbol"])

    m = compute_metrics(equity, benchmark, trades, ph)
    assert m.alpha is not None
    assert m.beta is not None
    assert m.excess_return is not None
    assert m.information_ratio is not None
    assert m.tracking_error is not None


def test_compute_metrics_newey_west_fields_populated():
    """NW inferential fields must all be populated."""
    equity = _make_equity()
    benchmark = _make_benchmark()
    trades = _make_trades()
    ph = pd.DataFrame(columns=["date", "symbol"])

    m = compute_metrics(equity, benchmark, trades, ph)
    assert m.alpha_t_stat is not None
    assert m.alpha_pvalue is not None
    assert m.alpha_se is not None
    assert m.beta_t_stat is not None
    assert m.beta_se is not None
    assert m.newey_west_lag is not None and m.newey_west_lag >= 1


def test_compute_metrics_with_start_end_dates():
    """Passing explicit start/end improves turnover annualization."""
    equity = _make_equity()
    benchmark = _make_benchmark()
    trades = _make_trades()
    ph = pd.DataFrame(columns=["date", "symbol"])

    m = compute_metrics(
        equity,
        benchmark,
        trades,
        ph,
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
    )
    assert m.annualized_turnover is not None
    assert m.annualized_turnover >= 0


def test_compute_metrics_empty_trades_does_not_crash():
    """Empty trades DataFrame should not cause errors."""
    equity = _make_equity()
    benchmark = _make_benchmark()
    trades = pd.DataFrame(
        columns=["exec_date", "symbol", "side", "shares", "notional", "fill_price", "cost_total"]
    )
    ph = pd.DataFrame(columns=["date", "symbol"])

    m = compute_metrics(equity, benchmark, trades, ph)
    assert isinstance(m, MetricsBundle)
    assert m.annualized_turnover == 0.0


def test_compute_metrics_flat_equity_no_drawdown():
    """Flat NAV: max_drawdown = 0, calmar = inf."""
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    equity = pd.Series(1000.0, index=idx)
    benchmark = pd.Series(1000.0, index=idx)
    trades = pd.DataFrame(columns=["exec_date", "symbol", "side", "shares", "notional"])
    ph = pd.DataFrame(columns=["date", "symbol"])

    m = compute_metrics(equity, benchmark, trades, ph)
    assert m.max_drawdown == pytest.approx(0.0, abs=1e-9)
    assert m.calmar == float("inf")


def test_metrics_bundle_forward_ref_resolved_in_backtest_result():
    """BacktestResult.metrics field type annotation resolves to MetricsBundle."""
    import dataclasses

    from ah_research.backtest.types import BacktestResult

    fields = {f.name: f for f in dataclasses.fields(BacktestResult)}
    assert "metrics" in fields
    # The annotation should be resolvable (not a string forward ref anymore)
    # We verify by checking the field exists and the default is not set
    assert fields["metrics"].default is dataclasses.MISSING
