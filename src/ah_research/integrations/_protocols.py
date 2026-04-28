"""Protocols for integration-layer sources.

Each Protocol is ``runtime_checkable`` so we can ``isinstance``-check a
candidate at the DataRepository boundary when we want to be explicit about
which capabilities a given client supplies (e.g., Baostock provides prices
and constituents; AKshare provides FX and sectors).

All fetch methods return source-native ``pd.DataFrame`` — column names and
dtypes match whatever the upstream library yields. Converters live in
``data/converters.py`` and are responsible for shaping these frames into
the domain-model schemas (``PriceFrameSchema`` etc.).

Method contracts (applies to every Protocol):
    - dates are inclusive on both ends
    - symbols use our canonical ``<code>.<exchange>`` form; clients translate
      to whatever upstream format is required
    - on upstream error, implementations remap to ``SourceError``
      subclasses (never leak baostock/akshare exceptions)
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class PriceSource(Protocol):
    def fetch_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return source-native daily OHLCV + volume/amount/turnover.

        Each row represents one (date, symbol). Missing trading days may be
        absent (not NaN-filled). Callers are responsible for gap-filling via
        the trading calendar.
        """
        ...


@runtime_checkable
class FundamentalsSource(Protocol):
    def fetch_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return source-native fundamentals rows.

        Must preserve ``report_date``, ``publication_date``, and
        ``statement_kind`` (preliminary | audited | restated). If the source
        does not supply a restatement marker, ``statement_kind`` defaults to
        ``audited``.
        """
        ...


@runtime_checkable
class FXSource(Protocol):
    def fetch_fx(self, pair: str, start: date, end: date) -> pd.DataFrame:
        """Return daily FX rates for ``pair`` (e.g., ``CNY_HKD``).

        Rate convention: 1 unit of the left-hand currency = rate units of
        the right-hand currency.
        """
        ...


@runtime_checkable
class CalendarSource(Protocol):
    def fetch_calendar(self, exchange: str, start: date, end: date) -> pd.DataFrame:
        """Return a trading-day flag per (date) for the given exchange."""
        ...


@runtime_checkable
class SectorSource(Protocol):
    def fetch_sectors(self, symbols: list[str]) -> pd.DataFrame:
        """Return (symbol, sector_l1, sector_l2) using SWS classification for
        A-shares; GICS-like for HK."""
        ...


@runtime_checkable
class CorporateActionsSource(Protocol):
    def fetch_corporate_actions(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return dividends / splits / rights issues within [start, end]
        (inclusive). Rows are keyed by (symbol, ex_date, kind)."""
        ...


@runtime_checkable
class ConstituentsSource(Protocol):
    def fetch_constituents(self, index: str, asof: date) -> pd.DataFrame:
        """Return index members that were active AT ``asof``.

        Implementations must be PIT-correct: a query for a historical date
        must not return members that only joined after that date. For
        survivorship-free backtests, the repository composes multiple asof
        calls into ``get_universe_over_time``.
        """
        ...
