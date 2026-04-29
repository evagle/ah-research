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
from ah_research.model.types import AHPair, Freq

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

    # ── trading calendar ───────────────────────────────────────────────────

    def get_trading_calendar(self, exchange: str, start: date, end: date) -> pd.DataFrame:
        """Return trading-day flags for ``exchange`` within ``[start, end]``.

        Cache miss triggers one upstream fetch; result is stored in cache
        and returned on the read-back. ``is_trading_day`` is ``bool``;
        callers typically filter ``df[df.is_trading_day].date``.
        """
        self._validate_date_range(start, end)
        cached = self._cache.read_calendar(exchange, start, end)
        if len(cached) > 0:
            return cached
        raw = self._calendar_source.fetch_calendar(exchange, start, end)
        if len(raw) > 0:
            self._cache.write_calendar(raw)
        return self._cache.read_calendar(exchange, start, end)

    # ── sectors ────────────────────────────────────────────────────────────

    def get_sector(self, symbols: list[str]) -> pd.DataFrame:
        """Return the current SWS / industry classification for ``symbols``.

        Sector tags are effectively static (they change only on reclassification
        events which we don't model), so one fetch per symbol suffices.
        """
        if len(symbols) == 0:
            return pd.DataFrame(columns=["symbol", "sector_l1", "sector_l2"])
        cached = self._cache.read_sectors(symbols)
        cached_set = set(cached["symbol"].tolist()) if len(cached) > 0 else set()
        missing = [s for s in symbols if s not in cached_set]
        if missing:
            raw = self._sector_source.fetch_sectors(missing)
            if len(raw) > 0:
                self._cache.write_sectors(raw)
        return self._cache.read_sectors(symbols)

    # ── AH premium ─────────────────────────────────────────────────────────

    def compute_ah_premium(
        self,
        pair: AHPair,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return the per-day AH premium for ``pair`` within ``[start, end]``.

        Premium definition::

            premium(t) = close_A(t) / (close_H(t) * FX_HKD_to_CNY(t)) - 1

        i.e., how much more expensive the A-share leg is than the H-share
        leg, priced in CNY. Positive premium is the default regime.

        Only dates where BOTH legs trade are kept (inner-join on date). FX
        is asof-filled forward: the most recent known rate on or before
        date t is used. Output columns: ``date``, ``close_a``, ``close_h``,
        ``fx_rate``, ``premium``.
        """
        self._validate_date_range(start, end)

        a_sym = str(pair.a_symbol)
        h_sym = str(pair.h_symbol)

        a_prices = self.get_prices([a_sym], start, end)
        h_prices = self.get_prices([h_sym], start, end)
        fx = self._fetch_fx_cny_hkd(start, end)

        if len(a_prices) == 0 or len(h_prices) == 0 or len(fx) == 0:
            return pd.DataFrame(columns=["date", "close_a", "close_h", "fx_rate", "premium"])

        a_slim = a_prices[["date", "close"]].rename(columns={"close": "close_a"})
        h_slim = h_prices[["date", "close"]].rename(columns={"close": "close_h"})
        fx_slim = fx[["date", "rate"]].rename(columns={"rate": "fx_rate"})

        merged = a_slim.merge(h_slim, on="date", how="inner").sort_values("date")
        merged = pd.merge_asof(merged, fx_slim.sort_values("date"), on="date", direction="backward")
        merged = merged.dropna(subset=["fx_rate"])
        # close_h (HKD) * fx_rate (CNY per HKD) = close_h in CNY
        merged["premium"] = merged["close_a"] / (merged["close_h"] * merged["fx_rate"]) - 1.0
        return merged.reset_index(drop=True)

    def get_fx_series(self, pair: str, start: date, end: date) -> pd.DataFrame:
        """Return daily FX rates for ``pair`` (e.g. ``CNY_HKD``) within
        ``[start, end]``.

        Rate convention: 1 unit of the left-hand currency = rate units of the
        right-hand currency. Currently only ``CNY_HKD`` is supported via the
        underlying FX source; other pairs raise ``UserInputError``.

        Columns: ``date``, ``pair``, ``rate``.
        """
        self._validate_date_range(start, end)
        if pair != "CNY_HKD":
            raise UserInputError(f"unsupported FX pair {pair!r}; only 'CNY_HKD' is available")
        return self._fetch_fx_cny_hkd(start, end)

    def _fetch_fx_cny_hkd(self, start: date, end: date) -> pd.DataFrame:
        """Fetch (and cache) the CNY/HKD rate series for ``[start, end]``.

        The stored table keeps one row per (date, pair); this method is
        the only caller for this specific pair so we treat a non-empty cache
        read as sufficient coverage.
        """
        pair = "CNY_HKD"
        cached = self._cache.read_fx(pair, start, end)
        if len(cached) > 0:
            return cached
        raw = self._fx_source.fetch_fx(pair, start, end)
        if len(raw) > 0:
            self._cache.write_fx(raw)
        return self._cache.read_fx(pair, start, end)

    # ── resample (D → W / M / Q) ───────────────────────────────────────────

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
        # without casts or ignores. Verbose but fully type-safe.
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

    @staticmethod
    def _validate_date_range(start: date, end: date) -> None:
        if start > end:
            raise UserInputError(f"start ({start}) must not be after end ({end})")


_PANDAS_FREQ: dict[str, str] = {
    "D": "D",
    "W": "W-FRI",
    "M": "ME",
    "Q": "QE",
}


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
