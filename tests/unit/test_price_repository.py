"""Unit tests for ``data.price_repository.PriceRepository`` (carved out in H4).

Pins the contract of the price-domain sub-repository in isolation,
without going through the ``DataRepository`` façade. Complements the
existing end-to-end tests in ``test_repository_prices.py`` /
``test_repository_misc.py``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from ah_research.data.cache import DuckDBCache
from ah_research.data.price_repository import PriceRepository, empty_price_frame
from ah_research.exceptions import UserInputError
from ah_research.integrations.fake import FakeSources
from ah_research.model.schemas import PriceFrameSchema
from ah_research.model.types import AHPair, parse_symbol

# ── Shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def fake_sources() -> FakeSources:
    return FakeSources(seed=42)


@pytest.fixture
def cache(tmp_path: Path):
    c = DuckDBCache(tmp_path / "cache.duckdb")
    yield c
    c.close()


@pytest.fixture
def price_repo(fake_sources: FakeSources, cache: DuckDBCache) -> PriceRepository:
    """Bare PriceRepository — no fundamentals / sectors / constituents
    plumbing needed for these tests."""
    return PriceRepository(
        price_source=fake_sources.prices,
        fx_source=fake_sources.fx,
        calendar_source=fake_sources.calendar,
        corp_actions_source=fake_sources.corporate_actions,
        cache=cache,
    )


# ── get_prices ─────────────────────────────────────────────────────────────


def test_get_prices_returns_schema_valid_frame(price_repo: PriceRepository) -> None:
    df = price_repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 6, 30))
    PriceFrameSchema.validate(df)
    assert len(df) > 0


def test_get_prices_empty_input_returns_empty_frame(price_repo: PriceRepository) -> None:
    df = price_repo.get_prices([], date(2024, 1, 1), date(2024, 3, 31))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    PriceFrameSchema.validate(df)  # still schema-valid


def test_get_prices_raises_on_reversed_dates(price_repo: PriceRepository) -> None:
    with pytest.raises(UserInputError):
        price_repo.get_prices(["600519.SH"], date(2024, 6, 30), date(2024, 1, 1))


def test_get_prices_second_call_hits_cache(
    price_repo: PriceRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache coverage check: second call over the same range must not
    re-fetch from the underlying source."""
    spy = MagicMock(wraps=price_repo._price_source.fetch_prices)
    monkeypatch.setattr(price_repo._price_source, "fetch_prices", spy)

    _ = price_repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert spy.call_count == 1

    _ = price_repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert spy.call_count == 1  # no additional fetch


def test_get_prices_fetches_only_missing_symbols(
    price_repo: PriceRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After priming the cache for one symbol, a multi-symbol query must
    only fetch the new one."""
    _ = price_repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))

    spy = MagicMock(wraps=price_repo._price_source.fetch_prices)
    monkeypatch.setattr(price_repo._price_source, "fetch_prices", spy)

    _ = price_repo.get_prices(["600519.SH", "0700.HK"], date(2024, 1, 1), date(2024, 3, 31))
    assert spy.call_count == 1
    fetched = spy.call_args.args[0] if spy.call_args.args else spy.call_args.kwargs["symbols"]
    assert fetched == ["0700.HK"]


# ── get_corporate_actions ──────────────────────────────────────────────────


def test_get_corporate_actions_empty_when_source_empty(price_repo: PriceRepository) -> None:
    df = price_repo.get_corporate_actions(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_get_corporate_actions_returns_preset_dividend(
    cache: DuckDBCache,
) -> None:
    """Inject a preset cash dividend and verify it round-trips through
    the source -> cache -> read pipeline."""
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
    fake = FakeSources(seed=42, preset_actions=actions)
    repo = PriceRepository(
        price_source=fake.prices,
        fx_source=fake.fx,
        calendar_source=fake.calendar,
        corp_actions_source=fake.corporate_actions,
        cache=cache,
    )

    df = repo.get_corporate_actions(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert len(df) == 1
    assert df["kind"].iloc[0] == "cash_dividend"


def test_get_corporate_actions_empty_symbols_list(price_repo: PriceRepository) -> None:
    df = price_repo.get_corporate_actions([], date(2024, 1, 1), date(2024, 12, 31))
    assert len(df) == 0
    # Schema-shape preserved even when empty
    assert {"symbol", "ex_date", "kind", "params_json"} <= set(df.columns)


# ── get_trading_calendar ───────────────────────────────────────────────────


def test_get_trading_calendar_returns_rows(price_repo: PriceRepository) -> None:
    df = price_repo.get_trading_calendar("SH", date(2024, 1, 1), date(2024, 1, 10))
    assert len(df) > 0
    assert {"exchange", "date", "is_trading_day"} <= set(df.columns)


def test_get_trading_calendar_flags_weekends(price_repo: PriceRepository) -> None:
    df = price_repo.get_trading_calendar("SH", date(2024, 1, 1), date(2024, 1, 14))
    sat = df[df["date"] == pd.Timestamp("2024-01-06")]["is_trading_day"].iloc[0]
    assert bool(sat) is False


# ── get_fx_series ──────────────────────────────────────────────────────────


def test_get_fx_series_cny_hkd_returns_rows(price_repo: PriceRepository) -> None:
    df = price_repo.get_fx_series("CNY_HKD", date(2024, 1, 1), date(2024, 1, 31))
    assert len(df) > 0
    assert {"date", "pair", "rate"} <= set(df.columns)


def test_get_fx_series_unknown_pair_raises(price_repo: PriceRepository) -> None:
    with pytest.raises(UserInputError, match="unsupported FX pair"):
        price_repo.get_fx_series("USD_EUR", date(2024, 1, 1), date(2024, 1, 31))


# ── compute_ah_premium ─────────────────────────────────────────────────────


def test_compute_ah_premium_columns(price_repo: PriceRepository) -> None:
    pair = AHPair(
        a_symbol=parse_symbol("601318.SH"),
        h_symbol=parse_symbol("2318.HK"),
        name_en="Ping An",
        name_zh="中国平安",
    )
    df = price_repo.compute_ah_premium(pair, date(2024, 1, 1), date(2024, 1, 31))
    assert {"date", "close_a", "close_h", "fx_rate", "premium"} <= set(df.columns)


def test_compute_ah_premium_premium_is_finite(price_repo: PriceRepository) -> None:
    import numpy as np

    pair = AHPair(
        a_symbol=parse_symbol("601318.SH"),
        h_symbol=parse_symbol("2318.HK"),
        name_en="Ping An",
        name_zh="中国平安",
    )
    df = price_repo.compute_ah_premium(pair, date(2024, 1, 1), date(2024, 1, 31))
    assert np.isfinite(df["premium"]).all()


# ── module-level helper ────────────────────────────────────────────────────


def test_empty_price_frame_has_schema_columns() -> None:
    df = empty_price_frame()
    assert len(df) == 0
    PriceFrameSchema.validate(df)
