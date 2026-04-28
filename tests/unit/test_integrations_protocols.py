from datetime import date

import pandas as pd

from ah_research.integrations import (
    CalendarSource,
    ConstituentsSource,
    CorporateActionsSource,
    FundamentalsSource,
    FXSource,
    PriceSource,
    SectorSource,
)


class _FakePriceSource:
    def fetch_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        return pd.DataFrame()


class _FakeFundamentals:
    def fetch_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        return pd.DataFrame()


class _FakeFX:
    def fetch_fx(self, pair: str, start: date, end: date) -> pd.DataFrame:
        return pd.DataFrame()


class _FakeCalendar:
    def fetch_calendar(self, exchange: str, start: date, end: date) -> pd.DataFrame:
        return pd.DataFrame()


class _FakeSectors:
    def fetch_sectors(self, symbols: list[str]) -> pd.DataFrame:
        return pd.DataFrame()


class _FakeCorporateActions:
    def fetch_corporate_actions(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        return pd.DataFrame()


class _FakeConstituents:
    def fetch_constituents(self, index: str, asof: date) -> pd.DataFrame:
        return pd.DataFrame()


def test_price_source_protocol_is_structural():
    src: PriceSource = _FakePriceSource()
    result = src.fetch_prices(["600519.SH"], date(2024, 1, 1), date(2024, 6, 30))
    assert isinstance(result, pd.DataFrame)


def test_all_protocols_runtime_checkable():
    assert isinstance(_FakePriceSource(), PriceSource)
    assert isinstance(_FakeFundamentals(), FundamentalsSource)
    assert isinstance(_FakeFX(), FXSource)
    assert isinstance(_FakeCalendar(), CalendarSource)
    assert isinstance(_FakeSectors(), SectorSource)
    assert isinstance(_FakeCorporateActions(), CorporateActionsSource)
    assert isinstance(_FakeConstituents(), ConstituentsSource)


def test_non_conforming_type_is_not_a_price_source():
    class NotASource:
        pass

    assert not isinstance(NotASource(), PriceSource)
