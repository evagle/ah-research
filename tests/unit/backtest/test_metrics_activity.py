"""Tests for activity metrics in metrics.py (Task 16)."""

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from ah_research.backtest.metrics import (
    annualized_turnover,
    avg_dividend_yield,
    avg_holding_period,
    avg_positions,
)

# ── annualized_turnover ───────────────────────────────────────────────────────


def test_turnover_one_year_at_avg_nav():
    """Two trades of 500 each over 1 year with avg_nav=1000 → turnover = 1.0."""
    trades = pd.DataFrame(
        {
            "exec_date": pd.to_datetime(["2024-01-02", "2024-06-01"]),
            "notional": [500.0, 500.0],
            "side": ["buy", "sell"],
        }
    )
    t = annualized_turnover(trades, avg_nav=1000.0, start=date(2024, 1, 1), end=date(2024, 12, 31))
    # 1000 notional / 1000 avg_nav / ~1 year ≈ 1.0
    assert t == pytest.approx(1.0, rel=0.05)


def test_turnover_empty_trades_returns_zero():
    trades = pd.DataFrame(columns=["exec_date", "notional", "side"])
    t = annualized_turnover(trades, avg_nav=1000.0, start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert t == 0.0


def test_turnover_zero_avg_nav_returns_zero():
    trades = pd.DataFrame({"exec_date": ["2024-01-02"], "notional": [500.0], "side": ["buy"]})
    t = annualized_turnover(trades, avg_nav=0.0, start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert t == 0.0


def test_turnover_scales_with_period():
    """Same trades over 2 years → turnover is halved versus 1 year."""
    trades = pd.DataFrame({"notional": [500.0, 500.0], "side": ["buy", "sell"]})
    t1 = annualized_turnover(trades, avg_nav=1000.0, start=date(2023, 1, 1), end=date(2023, 12, 31))
    t2 = annualized_turnover(trades, avg_nav=1000.0, start=date(2022, 1, 1), end=date(2023, 12, 31))
    assert t1 == pytest.approx(t2 * 2, rel=0.05)


def test_turnover_with_decimal_notional():
    """Decimal notional values are accepted (converted to float)."""
    trades = pd.DataFrame(
        {
            "notional": [Decimal("500"), Decimal("500")],
            "side": ["buy", "sell"],
        }
    )
    t = annualized_turnover(trades, avg_nav=1000.0, start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert t == pytest.approx(1.0, rel=0.05)


# ── avg_positions ─────────────────────────────────────────────────────────────


def _make_positions_history(dates: list[str], symbols_per_date: list[list[str]]) -> pd.DataFrame:
    rows = []
    for d, syms in zip(dates, symbols_per_date, strict=True):
        for s in syms:
            rows.append({"date": pd.Timestamp(d), "symbol": s, "shares": 100})
    return pd.DataFrame(rows)


def test_avg_positions_single_day():
    ph = _make_positions_history(["2024-01-02"], [["600000.SH", "000001.SZ"]])
    result = avg_positions(ph)
    assert result == pytest.approx(2.0)


def test_avg_positions_varying():
    """Average across days with different position counts."""
    ph = _make_positions_history(
        ["2024-01-02", "2024-01-03", "2024-01-04"],
        [["A"], ["A", "B"], ["A", "B", "C"]],
    )
    result = avg_positions(ph)
    assert result == pytest.approx(2.0)  # (1 + 2 + 3) / 3


def test_avg_positions_empty_returns_zero():
    ph = pd.DataFrame(columns=["date", "symbol", "shares"])
    result = avg_positions(ph)
    assert result == 0.0


# ── avg_holding_period ────────────────────────────────────────────────────────


def test_avg_holding_period_simple():
    """Buy on Jan 2, sell on Jan 12 → 10 calendar days."""
    trades = pd.DataFrame(
        {
            "exec_date": pd.to_datetime(["2024-01-02", "2024-01-12"]),
            "symbol": ["600000.SH", "600000.SH"],
            "side": ["buy", "sell"],
            "shares": [100, 100],
        }
    )
    ph = pd.DataFrame(columns=["date", "symbol"])
    result = avg_holding_period(ph, trades)
    assert result == pytest.approx(10.0)


def test_avg_holding_period_multiple_symbols():
    """Each symbol has a different holding period; average is returned."""
    trades = pd.DataFrame(
        {
            "exec_date": pd.to_datetime(["2024-01-02", "2024-01-12", "2024-01-03", "2024-01-23"]),
            "symbol": ["AAA.SH", "AAA.SH", "BBB.SH", "BBB.SH"],
            "side": ["buy", "sell", "buy", "sell"],
            "shares": [100, 100, 100, 100],
        }
    )
    ph = pd.DataFrame(columns=["date", "symbol"])
    result = avg_holding_period(ph, trades)
    # AAA: 10 days, BBB: 20 days → avg = 15
    assert result == pytest.approx(15.0)


def test_avg_holding_period_no_sells_returns_zero():
    """No sells → no completed round-trips → 0."""
    trades = pd.DataFrame(
        {
            "exec_date": pd.to_datetime(["2024-01-02"]),
            "symbol": ["600000.SH"],
            "side": ["buy"],
            "shares": [100],
        }
    )
    ph = pd.DataFrame(columns=["date", "symbol"])
    result = avg_holding_period(ph, trades)
    assert result == 0.0


def test_avg_holding_period_empty_trades_returns_zero():
    ph = pd.DataFrame(columns=["date", "symbol"])
    trades = pd.DataFrame(columns=["exec_date", "symbol", "side", "shares"])
    result = avg_holding_period(ph, trades)
    assert result == 0.0


# ── avg_dividend_yield ────────────────────────────────────────────────────────


def test_avg_dividend_yield_no_column_returns_zero():
    """When trades lacks 'dividend_income', result is 0."""
    trades = pd.DataFrame({"exec_date": ["2024-01-02"], "notional": [500.0]})
    ph = pd.DataFrame(columns=["date", "symbol"])
    equity = pd.Series(
        np.linspace(1000, 1100, 252),
        index=pd.date_range("2024-01-01", periods=252, freq="B"),
    )
    result = avg_dividend_yield(ph, trades, equity)
    assert result == 0.0


def test_avg_dividend_yield_with_income():
    """Known dividend income with known NAV → correct yield."""
    trades = pd.DataFrame(
        {
            "exec_date": ["2024-06-01"],
            "notional": [0.0],
            "dividend_income": [10.0],  # 10 CNY total dividends
        }
    )
    ph = pd.DataFrame(columns=["date", "symbol"])
    # 252-day equity with avg NAV = 1000, so annual yield ≈ 10/1000/1 = 1%
    equity = pd.Series(
        np.full(252, 1000.0),
        index=pd.date_range("2024-01-01", periods=252, freq="B"),
    )
    result = avg_dividend_yield(ph, trades, equity)
    assert result == pytest.approx(0.01, rel=0.05)
