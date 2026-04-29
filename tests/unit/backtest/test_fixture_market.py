"""Tests for the synthetic market fixture builder.

Validates that build_synthetic_market returns a DataRepository-compatible
object with the correct data shape, schema-valid prices, FX data, corporate
actions, and injectable halt/limit days for engine rule tests.
"""

from datetime import date

import pandas as pd

from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_synthetic_market_returns_repo() -> None:
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH", "0001.HK"],
    )
    prices = repo.get_prices(["600000.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert not prices.empty
    assert "close_hfq" in prices.columns
    assert "hit_limit_up" in prices.columns


def test_fixture_market_has_fx() -> None:
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH", "0001.HK"],
    )
    fx = repo.get_fx_series("CNY_HKD", date(2024, 1, 1), date(2024, 1, 31))
    assert len(fx) > 15


def test_price_schema_valid() -> None:
    """All required PriceFrameSchema columns are present and non-null."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 2, 29),
        symbols=["000001.SZ"],
    )
    prices = repo.get_prices(["000001.SZ"], date(2024, 1, 1), date(2024, 2, 29))
    required = [
        "date",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "close_hfq",
        "total_return",
        "volume",
        "amount",
        "turnover",
        "is_suspended",
        "is_st",
        "limit_up",
        "limit_down",
        "hit_limit_up",
        "hit_limit_down",
    ]
    for col in required:
        assert col in prices.columns, f"Missing column: {col}"
    # No NaN in core price columns
    for col in ("open", "high", "low", "close", "close_hfq", "total_return"):
        assert prices[col].notna().all(), f"NaN in column: {col}"


def test_prices_are_deterministic() -> None:
    """Two calls with the same seed produce identical prices."""
    repo1 = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH"],
        seed=42,
    )
    repo2 = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH"],
        seed=42,
    )
    p1 = repo1.get_prices(["600000.SH"], date(2024, 1, 1), date(2024, 1, 31))
    p2 = repo2.get_prices(["600000.SH"], date(2024, 1, 1), date(2024, 1, 31))
    pd.testing.assert_frame_equal(p1.reset_index(drop=True), p2.reset_index(drop=True))


def test_dividend_corporate_action_present() -> None:
    """Fixture injects a cash dividend for the first A-share symbol."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH", "0001.HK"],
    )
    actions = repo.get_corporate_actions(["600000.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert not actions.empty
    assert "cash_dividend" in actions["kind"].values


def test_trading_calendar_is_5day_week() -> None:
    """Calendar returns weekday-only trading days."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH"],
    )
    cal = repo.get_trading_calendar("SH", date(2024, 1, 1), date(2024, 1, 31))
    trading_days = cal[cal["is_trading_day"]]
    # All trading days are Mon-Fri (weekday < 5)
    for ts in trading_days["date"]:
        assert ts.weekday() < 5, f"Weekend trading day: {ts}"


def test_fundamentals_placeholder() -> None:
    """Fundamentals returns non-empty rows for A-share symbols."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH"],
    )
    funds = repo.get_fundamentals(["600000.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert not funds.empty
    assert "pe" in funds.columns
    assert "dividend_yield" in funds.columns


def test_sector_table_populated() -> None:
    """get_sector returns sector_l1 and sector_l2 for provided symbols."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH", "0001.HK"],
    )
    sectors = repo.get_sector(["600000.SH", "0001.HK"])
    assert len(sectors) == 2
    assert "sector_l1" in sectors.columns


def test_universe_over_time() -> None:
    """PIT universe returns a (date, symbol) frame for supplied symbols."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH", "000001.SZ", "0001.HK"],
    )
    univ = repo.get_universe_over_time("CSI300", date(2024, 1, 1), date(2024, 3, 31), freq="ME")
    assert not univ.empty
    assert "symbol" in univ.columns
    assert "date" in univ.columns


def test_halt_days_injection() -> None:
    """Injected halt days are reflected as is_suspended=True in prices."""
    halt_days = {"600000.SH": [date(2024, 1, 10)]}
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH"],
        halt_days=halt_days,
    )
    prices = repo.get_prices(["600000.SH"], date(2024, 1, 1), date(2024, 1, 31))
    suspended_dates = prices[prices["is_suspended"]]["date"].dt.date.tolist()
    assert date(2024, 1, 10) in suspended_dates


def test_limit_up_injection() -> None:
    """Injected limit-up days are reflected as hit_limit_up=True in prices."""
    limit_up_days = {"600000.SH": [date(2024, 1, 15)]}
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH"],
        limit_up_days=limit_up_days,
    )
    prices = repo.get_prices(["600000.SH"], date(2024, 1, 1), date(2024, 1, 31))
    hit_up_dates = prices[prices["hit_limit_up"]]["date"].dt.date.tolist()
    assert date(2024, 1, 15) in hit_up_dates
