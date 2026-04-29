"""Tests for DataRepository.get_trading_calendar, get_sector, compute_ah_premium,
and resample."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from ah_research.data.repository import DataRepository
from ah_research.exceptions import UserInputError
from ah_research.model.types import AHPair, parse_symbol

# ── get_trading_calendar ─────────────────────────────────────────────────────


def test_get_trading_calendar_returns_rows(repo: DataRepository):
    df = repo.get_trading_calendar("SH", date(2024, 1, 1), date(2024, 1, 10))
    assert len(df) > 0
    assert {"exchange", "date", "is_trading_day"} <= set(df.columns)


def test_get_trading_calendar_flags_weekends(repo: DataRepository):
    df = repo.get_trading_calendar("SH", date(2024, 1, 1), date(2024, 1, 14))
    sat = df[df["date"] == pd.Timestamp("2024-01-06")]["is_trading_day"].iloc[0]
    assert bool(sat) is False


# ── get_sector ───────────────────────────────────────────────────────────────


def test_get_sector_returns_one_row_per_symbol(repo: DataRepository):
    df = repo.get_sector(["600519.SH", "0700.HK"])
    assert len(df) == 2


def test_get_sector_empty_input(repo: DataRepository):
    df = repo.get_sector([])
    assert len(df) == 0


def test_get_sector_second_call_does_not_refetch(repo: DataRepository, monkeypatch):
    from unittest.mock import MagicMock

    _ = repo.get_sector(["600519.SH"])
    spy = MagicMock(wraps=repo._sector_source.fetch_sectors)
    monkeypatch.setattr(repo._sector_source, "fetch_sectors", spy)

    _ = repo.get_sector(["600519.SH"])
    assert spy.call_count == 0


# ── compute_ah_premium ───────────────────────────────────────────────────────


def test_compute_ah_premium_columns(repo: DataRepository):
    pair = AHPair(
        a_symbol=parse_symbol("601318.SH"),
        h_symbol=parse_symbol("2318.HK"),
        name_en="Ping An",
        name_zh="中国平安",
    )
    df = repo.compute_ah_premium(pair, date(2024, 1, 1), date(2024, 1, 31))
    assert {"date", "close_a", "close_h", "fx_rate", "premium"} <= set(df.columns)


def test_compute_ah_premium_premium_is_finite(repo: DataRepository):
    pair = AHPair(
        a_symbol=parse_symbol("601318.SH"),
        h_symbol=parse_symbol("2318.HK"),
        name_en="Ping An",
        name_zh="中国平安",
    )
    df = repo.compute_ah_premium(pair, date(2024, 1, 1), date(2024, 1, 31))
    import numpy as np

    assert np.isfinite(df["premium"]).all()


def test_compute_ah_premium_intersects_trading_days(repo: DataRepository):
    """The result should have no more rows than min(A-trading-days, H-trading-days)
    over the requested period."""
    pair = AHPair(
        a_symbol=parse_symbol("601318.SH"),
        h_symbol=parse_symbol("2318.HK"),
        name_en="Ping An",
        name_zh="中国平安",
    )
    df = repo.compute_ah_premium(pair, date(2024, 1, 1), date(2024, 1, 31))
    a_days = len(repo.get_prices(["601318.SH"], date(2024, 1, 1), date(2024, 1, 31)))
    h_days = len(repo.get_prices(["2318.HK"], date(2024, 1, 1), date(2024, 1, 31)))
    assert len(df) <= min(a_days, h_days)


# ── resample ─────────────────────────────────────────────────────────────────


def test_resample_monthly_collapses_daily_rows(repo: DataRepository):
    daily = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))
    monthly = DataRepository.resample(daily, "M")
    # 2024-01, 2024-02, 2024-03 = 3 month-ends
    assert len(monthly) == 3


def test_resample_preserves_symbol_column(repo: DataRepository):
    daily = repo.get_prices(["600519.SH", "0700.HK"], date(2024, 1, 1), date(2024, 3, 31))
    monthly = DataRepository.resample(daily, "M")
    assert set(monthly["symbol"].unique()) == {"600519.SH", "0700.HK"}


def test_resample_weekly_uses_last_close(repo: DataRepository):
    daily = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 31))
    weekly = DataRepository.resample(daily, "W")
    # Week labels should be Fridays
    for ts in weekly["date"]:
        # weekday() == 4 means Friday (0=Monday).
        assert pd.Timestamp(ts).weekday() == 4


def test_resample_volume_summed(repo: DataRepository):
    daily = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 31))
    monthly = DataRepository.resample(daily, "M")
    daily_total_volume = int(daily["volume"].sum())
    monthly_total_volume = int(monthly["volume"].sum())
    assert daily_total_volume == monthly_total_volume


def test_resample_rejects_unknown_freq(repo: DataRepository):
    daily = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 31))
    with pytest.raises(UserInputError):
        DataRepository.resample(daily, "X")  # type: ignore[arg-type]


def test_resample_handles_empty_frame():
    empty = pd.DataFrame(columns=["date", "symbol", "close", "volume"])
    result = DataRepository.resample(empty, "M")
    assert len(result) == 0
