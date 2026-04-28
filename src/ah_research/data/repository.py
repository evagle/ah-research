"""DataRepository — the façade every research function calls.

Responsibilities:

- **Compose** integration sources + the DuckDB cache behind a single
  method-per-entity API.
- **Enforce PIT semantics** at every read: fundamentals filter
  ``known_as_of <= asof``, constituents filter the half-open membership
  interval, corporate actions are fetched lazily alongside prices.
- **Minimise upstream calls** by checking cache coverage before fetching.
- **Validate every return value** against pandera so drift surfaces as an
  exception, not a silent data-quality bug.

The repository accepts Protocols in its constructor, never concrete
Baostock/AKshare clients. Tests pass ``FakeSources.*``; production wires
real clients in ``ah doctor`` / ``ah warmup``.

Phase 1 scope: prices (1.12), fundamentals (1.13), constituents (1.14),
universe-over-time (1.15), corporate actions (1.16), calendar + sector
(1.17), AH premium (1.18), resample (1.19). This file starts with 1.11+1.12;
other methods land in subsequent commits.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from ah_research.data.cache import DuckDBCache
from ah_research.data.converters import convert_prices
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
from ah_research.logging import get_logger
from ah_research.model.schemas import PriceFrameSchema

log = get_logger(__name__)


class DataRepository:
    """Façade over integration sources + cache. Every research-facing read
    goes through here so PIT and schema contracts are centrally enforced."""

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
        self._price_source = price_source
        self._fundamentals_source = fundamentals_source
        self._fx_source = fx_source
        self._calendar_source = calendar_source
        self._sector_source = sector_source
        self._corp_actions_source = corp_actions_source
        self._constituents_source = constituents_source
        self._cache = cache

    # ── prices ─────────────────────────────────────────────────────────────

    def get_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return ``PriceFrameSchema``-valid prices for ``symbols`` within
        ``[start, end]`` inclusive.

        Fetching strategy (v1): for each symbol whose cache coverage does not
        fully span the requested range, fetch ``[start, end]`` from upstream
        (along with corporate actions over the same window), convert to the
        domain schema, and upsert into the cache. Then read from cache.

        Corporate-action-driven hfq/total_return are recomputed over the
        fetched window; older already-cached rows are not retroactively
        rewritten. For typical "always fetch up to today" usage this is
        correct; callers wanting a full historical rewrite should widen
        the request window.
        """
        self._validate_date_range(start, end)
        if len(symbols) == 0:
            return PriceFrameSchema.validate(_empty_price_frame())

        symbols_to_fetch = [
            sym for sym in symbols if not self._price_range_fully_cached(sym, start, end)
        ]
        if symbols_to_fetch:
            self._fetch_and_cache_prices(symbols_to_fetch, start, end)

        return self._cache.read_prices(symbols, start, end)

    # ── internal helpers ───────────────────────────────────────────────────

    def _price_range_fully_cached(self, symbol: str, start: date, end: date) -> bool:
        # Use the fetch log (request-range) not the data coverage
        # (trading-day range) so calendar/trading-day mismatches don't
        # trigger spurious refetches.
        return self._cache.has_price_fetch_covering(symbol, start, end)

    def _fetch_and_cache_prices(self, symbols: list[str], start: date, end: date) -> None:
        log.info(
            "fetch_prices",
            symbols=symbols,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        raw = self._price_source.fetch_prices(symbols, start, end)
        actions = self._corp_actions_source.fetch_corporate_actions(symbols, start, end)
        if len(raw) > 0:
            converted = convert_prices(raw, actions)
            self._cache.write_prices(converted)
        # Log the fetch even if it returned no rows, so we don't retry forever
        # against a symbol that has no data.
        for sym in symbols:
            self._cache.log_price_fetch(sym, start, end)

    @staticmethod
    def _validate_date_range(start: date, end: date) -> None:
        if start > end:
            raise UserInputError(f"start ({start}) must not be after end ({end})")


def _empty_price_frame() -> pd.DataFrame:
    """Build a zero-row DataFrame with columns matching PriceFrameSchema."""
    return pd.DataFrame(
        {
            "date": pd.Series([], dtype="datetime64[ns]"),
            "symbol": pd.Series([], dtype=str),
            "open": pd.Series([], dtype=float),
            "high": pd.Series([], dtype=float),
            "low": pd.Series([], dtype=float),
            "close": pd.Series([], dtype=float),
            "close_hfq": pd.Series([], dtype=float),
            "total_return": pd.Series([], dtype=float),
            "volume": pd.Series([], dtype="int64"),
            "amount": pd.Series([], dtype=float),
            "turnover": pd.Series([], dtype=float),
            "is_suspended": pd.Series([], dtype=bool),
            "is_st": pd.Series([], dtype=bool),
            "limit_up": pd.Series([], dtype=float),
            "limit_down": pd.Series([], dtype=float),
            "hit_limit_up": pd.Series([], dtype=bool),
            "hit_limit_down": pd.Series([], dtype=bool),
        }
    )
