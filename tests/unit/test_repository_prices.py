"""Tests for DataRepository.get_prices — cache-aware fetching, PIT schema,
and upstream call minimisation."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from ah_research.data.repository import DataRepository
from ah_research.integrations.fake import FakeSources
from ah_research.model.schemas import PriceFrameSchema


def test_get_prices_returns_schema_valid_frame(repo: DataRepository):
    df = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 6, 30))
    PriceFrameSchema.validate(df)
    assert len(df) > 0


def test_get_prices_respects_date_range(repo: DataRepository):
    df = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 31))
    assert df["date"].min() >= pd.Timestamp("2024-01-01")
    assert df["date"].max() <= pd.Timestamp("2024-01-31")


def test_get_prices_returns_requested_symbols_only(repo: DataRepository):
    df = repo.get_prices(["600519.SH", "0700.HK"], date(2024, 1, 1), date(2024, 1, 31))
    assert set(df["symbol"].unique()) == {"600519.SH", "0700.HK"}


def test_get_prices_second_call_hits_cache(repo: DataRepository, monkeypatch):
    """Second call over a fully-covered range must not touch the source."""
    spy = MagicMock(wraps=repo._prices._price_source.fetch_prices)
    monkeypatch.setattr(repo._prices._price_source, "fetch_prices", spy)

    _ = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert spy.call_count == 1

    _ = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert spy.call_count == 1  # no additional fetch


def test_get_prices_fetches_only_missing_symbols(repo: DataRepository, monkeypatch):
    """After priming the cache for 600519.SH, a multi-symbol query should
    only fetch the uncached symbol."""
    # Prime cache for 600519.SH
    _ = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))

    spy = MagicMock(wraps=repo._prices._price_source.fetch_prices)
    monkeypatch.setattr(repo._prices._price_source, "fetch_prices", spy)

    _ = repo.get_prices(["600519.SH", "0700.HK"], date(2024, 1, 1), date(2024, 3, 31))
    # Only 0700.HK should be fetched from upstream
    assert spy.call_count == 1
    call = spy.call_args
    fetched_symbols = call.args[0] if call.args else call.kwargs["symbols"]
    assert fetched_symbols == ["0700.HK"]


def test_get_prices_empty_input_returns_empty_frame(repo: DataRepository):
    df = repo.get_prices([], date(2024, 1, 1), date(2024, 3, 31))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_get_prices_raises_on_reversed_dates(repo: DataRepository):
    import pytest

    from ah_research.exceptions import UserInputError

    with pytest.raises(UserInputError):
        repo.get_prices(["600519.SH"], date(2024, 6, 30), date(2024, 1, 1))


def test_get_prices_is_order_deterministic(repo: DataRepository):
    """Same input ⇒ same output order (symbol ASC, date ASC)."""
    df1 = repo.get_prices(["0700.HK", "600519.SH"], date(2024, 1, 1), date(2024, 1, 31))
    df2 = repo.get_prices(["600519.SH", "0700.HK"], date(2024, 1, 1), date(2024, 1, 31))
    # Both should be ordered by (symbol, date)
    assert (df1["symbol"].values == df2["symbol"].values).all()
    assert (df1["date"].values == df2["date"].values).all()


def test_get_prices_applies_corporate_actions(cache, fake_sources: FakeSources, tmp_path):
    """When the corp-actions source reports a dividend, close_hfq must
    differ from close for dates before the ex-date."""
    # Build a fake with a preset dividend
    actions = pd.DataFrame(
        [
            {
                "symbol": "600519.SH",
                "ex_date": pd.Timestamp("2024-06-15"),
                "kind": "cash_dividend",
                "params_json": '{"amount_per_share": 30.0}',
            }
        ]
    )
    fake_with_action = FakeSources(seed=42, preset_actions=actions)
    repo = DataRepository(
        price_source=fake_with_action.prices,
        fundamentals_source=fake_with_action.fundamentals,
        fx_source=fake_with_action.fx,
        calendar_source=fake_with_action.calendar,
        sector_source=fake_with_action.sectors,
        corp_actions_source=fake_with_action.corporate_actions,
        constituents_source=fake_with_action.constituents,
        cache=cache,
    )

    df = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    pre = df[df["date"] < pd.Timestamp("2024-06-15")]
    post = df[df["date"] >= pd.Timestamp("2024-06-15")]
    # Before ex-date, close_hfq should be scaled DOWN
    assert (pre["close_hfq"] < pre["close"]).all()
    # On/after ex-date, close_hfq equals close
    assert (post["close_hfq"] == post["close"]).all()
