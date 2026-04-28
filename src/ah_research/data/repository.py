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
from ah_research.data.converters import convert_fundamentals, convert_prices
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

    # ── fundamentals ───────────────────────────────────────────────────────

    def get_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
        *,
        asof: date | None = None,
    ) -> pd.DataFrame:
        """Return bitemporal fundamentals, PIT-filtered to ``asof``.

        If ``asof`` is ``None``, defaults to ``end`` (so callers who want
        "everything we know up to the end of the analysis period" get
        that by default). Raises ``LeakageDetected`` if ``asof > end`` —
        that would let a query inject knowledge later than the analysis
        window, which is almost certainly a bug.
        """
        self._validate_date_range(start, end)
        if asof is None:
            asof = end
        elif asof > end:
            from ah_research.exceptions import LeakageDetected

            raise LeakageDetected(f"asof ({asof}) is after end ({end}); that leaks future info")

        if len(symbols) == 0:
            return pd.DataFrame()

        to_fetch = [
            sym
            for sym in symbols
            if not self._cache.has_fundamentals_fetch_covering(sym, start, end)
        ]
        if to_fetch:
            self._fetch_and_cache_fundamentals(to_fetch, start, end)

        return self._cache.read_fundamentals_asof(symbols, asof)

    def _fetch_and_cache_fundamentals(self, symbols: list[str], start: date, end: date) -> None:
        log.info(
            "fetch_fundamentals",
            symbols=symbols,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        raw = self._fundamentals_source.fetch_fundamentals(symbols, start, end)
        if len(raw) > 0:
            converted = convert_fundamentals(raw)
            self._cache.write_fundamentals(converted)
        for sym in symbols:
            self._cache.log_fundamentals_fetch(sym, start, end)

    # ── index constituents ─────────────────────────────────────────────────

    def get_index_constituents(self, index: str, asof: date) -> pd.DataFrame:
        """Return PIT-correct constituents of ``index`` at ``asof``.

        On a cache miss, fetches one snapshot from the constituents source
        and writes it as an open-ended membership anchored at ``asof``.
        Replacing open-ended rows with exact effective_from/to from a
        survivorship-free source is a Phase 2 extension.
        """
        if not self._cache.has_constituents_fetch(index, asof):
            self._fetch_and_cache_constituents(index, asof)
        return self._cache.read_constituents_asof(index, asof)

    def _fetch_and_cache_constituents(self, index: str, asof: date) -> None:
        log.info("fetch_constituents", index=index, asof=asof.isoformat())
        raw = self._constituents_source.fetch_constituents(index, asof)
        if len(raw) > 0:
            cache_rows = pd.DataFrame(
                {
                    "index_name": index,
                    "symbol": raw["symbol"],
                    "weight": raw["weight"],
                    "effective_from": pd.Timestamp(asof),
                    "effective_to": pd.NaT,
                }
            )
            self._cache.write_constituents(cache_rows)
        self._cache.log_constituents_fetch(index, asof)

    # ── universe over time (survivorship-free) ────────────────────────────

    def get_universe_over_time(
        self,
        index: str,
        start: date,
        end: date,
        *,
        freq: str = "ME",
    ) -> pd.DataFrame:
        """Return a long-format DataFrame of ``(date, symbol)`` rows giving
        the PIT-correct members of ``index`` at each sampled date.

        ``freq`` is a pandas offset alias (default month-end ``ME``). Tight
        samplings (daily) are rarely useful — index composition turns over
        slowly, and the fetch cost scales with sample count.

        This is the survivorship-free driver for back-tests: a strategy
        iterating over this frame only sees symbols that were ACTUAL
        members at each rebalance date.
        """
        self._validate_date_range(start, end)
        sample_dates = pd.date_range(start, end, freq=freq)
        rows: list[pd.DataFrame] = []
        for ts in sample_dates:
            asof = ts.date()
            snapshot = self.get_index_constituents(index, asof)
            if len(snapshot) == 0:
                continue
            rows.append(
                pd.DataFrame(
                    {
                        "date": pd.Timestamp(asof),
                        "index_name": index,
                        "symbol": snapshot["symbol"].to_numpy(),
                        "weight": snapshot["weight"].to_numpy(),
                    }
                )
            )
        if not rows:
            return pd.DataFrame(columns=["date", "index_name", "symbol", "weight"])
        return pd.concat(rows, ignore_index=True)

    # ── corporate actions ──────────────────────────────────────────────────

    def get_corporate_actions(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        """Return corporate actions for ``symbols`` within ``[start, end]``.

        Reads from cache (populated as a side-effect of ``get_prices``). If
        the cache has no rows for these symbols, does a direct fetch.
        """
        self._validate_date_range(start, end)
        if len(symbols) == 0:
            return pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
        cached = self._cache.read_corporate_actions(symbols, start, end)
        if len(cached) > 0:
            return cached
        raw = self._corp_actions_source.fetch_corporate_actions(symbols, start, end)
        if len(raw) > 0:
            self._cache.write_corporate_actions(raw)
        return self._cache.read_corporate_actions(symbols, start, end)

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
