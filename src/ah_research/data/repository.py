"""DataRepository — the façade every research function calls.

Delegates the domain methods to three sub-repositories carved out for
single-responsibility (H4 in 2026-05-02 code review):

* :class:`PriceRepository` -- prices, corporate actions, calendar, FX,
  AH premium.
* :class:`FundamentalsRepository` -- bitemporal fundamentals with PIT
  filtering.
* :class:`ConfigRepository` -- index constituents, universe-over-time,
  sectors.

The façade is preserved so that ~50 existing call sites of the form
``repo.get_prices(...)`` / ``repo.get_fundamentals(...)`` keep working
unchanged. Internal delegation is the only difference.

Responsibilities (unchanged at this layer):

* **Compose** integration sources + the DuckDB cache behind a single
  method-per-entity API.
* **Enforce PIT semantics** at every read: fundamentals filter
  ``known_as_of <= asof``, constituents filter the half-open membership
  interval, corporate actions are fetched lazily alongside prices.
* **Minimise upstream calls** by checking cache coverage before fetching.
* **Validate every return value** against pandera so drift surfaces as an
  exception, not a silent data-quality bug.

The repository accepts Protocols in its constructor, never concrete
Baostock/AKshare clients. Tests pass ``FakeSources.*``; production wires
real clients in ``ah doctor`` / ``ah warmup``.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from ah_research.data.cache import DuckDBCache
from ah_research.data.config_repository import ConfigRepository
from ah_research.data.fundamentals_repository import FundamentalsRepository
from ah_research.data.price_repository import PriceRepository
from ah_research.exceptions import UserInputError
from ah_research.integrations import (
    CalendarSource,
    ConstituentsSource,
    CorporateActionsSource,
    FundamentalsSource,
    FXSource,
    PriceSource,
    SectorSource,
)
from ah_research.model.types import AHPair, Freq


class DataRepository:
    """Façade over the three domain sub-repositories.

    Constructor signature is unchanged from pre-H4 code so existing
    wire-up sites (``ah doctor``, ``ah warmup``, tests) keep working.
    Internally builds a :class:`PriceRepository`, a
    :class:`FundamentalsRepository`, and a :class:`ConfigRepository`,
    each given the source(s) it needs plus the shared cache. All ten
    public methods delegate by domain.
    """

    def __init__(
        self,
        *,
        price_source: PriceSource,
        fundamentals_source: FundamentalsSource,
        fx_source: FXSource,
        calendar_source: CalendarSource,
        sector_source: SectorSource,
        corp_actions_source: CorporateActionsSource,
        constituents_source: ConstituentsSource,
        cache: DuckDBCache,
    ) -> None:
        self._cache = cache
        self._prices = PriceRepository(
            price_source=price_source,
            fx_source=fx_source,
            calendar_source=calendar_source,
            corp_actions_source=corp_actions_source,
            cache=cache,
        )
        self._fundamentals = FundamentalsRepository(
            fundamentals_source=fundamentals_source,
            cache=cache,
        )
        self._config = ConfigRepository(
            constituents_source=constituents_source,
            sector_source=sector_source,
            cache=cache,
        )

    # ── price-domain delegates ────────────────────────────────────────────

    def get_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Delegate to :meth:`PriceRepository.get_prices`."""
        return self._prices.get_prices(symbols, start, end)

    def get_corporate_actions(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        """Delegate to :meth:`PriceRepository.get_corporate_actions`."""
        return self._prices.get_corporate_actions(symbols, start, end)

    def get_trading_calendar(self, exchange: str, start: date, end: date) -> pd.DataFrame:
        """Delegate to :meth:`PriceRepository.get_trading_calendar`."""
        return self._prices.get_trading_calendar(exchange, start, end)

    def get_fx_series(self, pair: str, start: date, end: date) -> pd.DataFrame:
        """Delegate to :meth:`PriceRepository.get_fx_series`."""
        return self._prices.get_fx_series(pair, start, end)

    def compute_ah_premium(
        self,
        pair: AHPair,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Delegate to :meth:`PriceRepository.compute_ah_premium`."""
        return self._prices.compute_ah_premium(pair, start, end)

    # ── fundamentals-domain delegate ──────────────────────────────────────

    def get_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
        *,
        asof: date | None = None,
    ) -> pd.DataFrame:
        """Delegate to :meth:`FundamentalsRepository.get_fundamentals`."""
        return self._fundamentals.get_fundamentals(symbols, start, end, asof=asof)

    # ── config-domain delegates ───────────────────────────────────────────

    def get_index_constituents(self, index: str, asof: date) -> pd.DataFrame:
        """Delegate to :meth:`ConfigRepository.get_index_constituents`."""
        return self._config.get_index_constituents(index, asof)

    def get_universe_over_time(
        self,
        index: str,
        start: date,
        end: date,
        *,
        freq: str = "ME",
    ) -> pd.DataFrame:
        """Delegate to :meth:`ConfigRepository.get_universe_over_time`."""
        return self._config.get_universe_over_time(index, start, end, freq=freq)

    def get_sector(self, symbols: list[str]) -> pd.DataFrame:
        """Delegate to :meth:`ConfigRepository.get_sector`."""
        return self._config.get_sector(symbols)

    # ── direct sub-repository access (read-only, for callers that want
    #    to depend on a narrower contract than the full façade) ────────────

    @property
    def prices(self) -> PriceRepository:
        return self._prices

    @property
    def fundamentals(self) -> FundamentalsRepository:
        return self._fundamentals

    @property
    def config(self) -> ConfigRepository:
        return self._config

    # ── resample (D → W / M / Q): stays on the façade as a stateless
    #    static utility used directly via ``DataRepository.resample(...)``
    #    in some tests. ──────────────────────────────────────────────────

    @staticmethod
    def resample(frame: pd.DataFrame, freq: Freq | str) -> pd.DataFrame:
        """Resample a daily ``PriceFrameSchema``-valid frame to a lower
        frequency.

        Aggregation rules (per symbol, per period):
            close, close_hfq, total_return, limit_up, limit_down → last
            open                                                 → first
            high                                                 → max
            low                                                  → min
            volume, amount                                       → sum
            turnover                                             → mean
            is_suspended, is_st, hit_limit_up, hit_limit_down    → any

        The period label is the period *end* (e.g., Friday for W, month-end
        for M, quarter-end for Q).
        """
        freq_str = str(freq)
        pandas_freq = _PANDAS_FREQ.get(freq_str)
        if pandas_freq is None:
            raise UserInputError(f"unsupported resample freq {freq_str!r}; expected D|W|M|Q")
        if len(frame) == 0:
            return frame.copy()

        # Per-symbol, per-column aggregation. Each call is a typed Series
        # method (.first / .max / .any / ...), so mypy checks everything
        # without casts or ignores.
        parts: list[pd.DataFrame] = []
        for sym, group in frame.groupby("symbol"):
            g = group.set_index("date").drop(columns=["symbol"])
            rs = g.resample(pandas_freq)
            columns: dict[str, pd.Series] = {}

            if "open" in g.columns:
                columns["open"] = rs["open"].first()
            if "high" in g.columns:
                columns["high"] = rs["high"].max()
            if "low" in g.columns:
                columns["low"] = rs["low"].min()
            if "close" in g.columns:
                columns["close"] = rs["close"].last()
            if "close_hfq" in g.columns:
                columns["close_hfq"] = rs["close_hfq"].last()
            if "total_return" in g.columns:
                columns["total_return"] = rs["total_return"].last()
            if "volume" in g.columns:
                columns["volume"] = rs["volume"].sum()
            if "amount" in g.columns:
                columns["amount"] = rs["amount"].sum()
            if "turnover" in g.columns:
                columns["turnover"] = rs["turnover"].mean()
            if "is_suspended" in g.columns:
                columns["is_suspended"] = rs["is_suspended"].any()
            if "is_st" in g.columns:
                columns["is_st"] = rs["is_st"].any()
            if "limit_up" in g.columns:
                columns["limit_up"] = rs["limit_up"].last()
            if "limit_down" in g.columns:
                columns["limit_down"] = rs["limit_down"].last()
            if "hit_limit_up" in g.columns:
                columns["hit_limit_up"] = rs["hit_limit_up"].any()
            if "hit_limit_down" in g.columns:
                columns["hit_limit_down"] = rs["hit_limit_down"].any()

            resampled = pd.DataFrame(columns).reset_index()
            resampled.insert(1, "symbol", sym)
            parts.append(resampled)
        return pd.concat(parts, ignore_index=True)


_PANDAS_FREQ: dict[str, str] = {
    "D": "D",
    "W": "W-FRI",
    "M": "ME",
    "Q": "QE",
}
