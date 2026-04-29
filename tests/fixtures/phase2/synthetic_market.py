"""Synthetic market fixture builder for engine integration and rule tests.

Returns a SyntheticMarket instance (subclass of DataRepository) populated
entirely from deterministic in-memory data — no DuckDB cache, no upstream
calls. All data is schema-valid per PriceFrameSchema / FundamentalsFrameSchema.

Usage::

    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH", "0001.HK"],
    )
    prices = repo.get_prices(["600000.SH"], date(2024, 1, 1), date(2024, 3, 31))

Optional kwargs (for engine rule tests):
    halt_days:     dict[str, list[date]]  -- symbol -> dates to mark is_suspended=True
    limit_up_days: dict[str, list[date]]  -- symbol -> dates to mark hit_limit_up=True
    limit_down_days: dict[str, list[date]] -- symbol -> dates to mark hit_limit_down=True
    seed:          int  -- RNG seed (default 42)
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ah_research.data.repository import DataRepository
from ah_research.exceptions import UserInputError
from ah_research.model.schemas import (
    CorporateActionSchema,
    FundamentalsFrameSchema,
    PriceFrameSchema,
    TradingCalendarSchema,
)

# Starting price for the random walk (all symbols).
_START_PRICE = 10.0
# Daily log-return standard deviation.
_LOG_RETURN_STD = 0.02
# Cash dividend amount per share injected for the first A-share symbol.
_DIVIDEND_AMOUNT = 0.5
# Sectors cycled across symbols.
_SECTORS = ["Financials", "Consumer", "Technology", "Industrials", "Energy", "Healthcare"]


# ── helpers ──────────────────────────────────────────────────────────────────


def _business_dates(start: date, end: date) -> pd.DatetimeIndex:
    """Return Mon-Fri dates in [start, end] — 5-day business calendar."""
    return pd.bdate_range(start, end)


def _exchange_for(symbol: str) -> str:
    _, _, exchange = symbol.partition(".")
    return exchange


def _limit_pct(symbol: str, is_st: bool) -> float | None:
    """Return ±pct daily limit or None for HK."""
    code, _, exchange = symbol.partition(".")
    if exchange == "HK":
        return None
    if code.startswith("300") or code.startswith("688"):
        return 0.20
    if is_st:
        return 0.05
    return 0.10


def _build_prices(
    symbols: list[str],
    start: date,
    end: date,
    seed: int,
    halt_days: dict[str, list[date]],
    limit_up_days: dict[str, list[date]],
    limit_down_days: dict[str, list[date]],
    dividend_ex_dates: dict[str, date],
) -> pd.DataFrame:
    """Build a PriceFrameSchema-valid DataFrame for all symbols."""
    bdates = _business_dates(start, end)
    rows: list[dict[str, Any]] = []

    for sym in symbols:
        rng = np.random.default_rng(seed + hash(sym) % 2**32)
        log_returns = rng.normal(0.0, _LOG_RETURN_STD, len(bdates))
        closes = _START_PRICE * np.exp(np.cumsum(log_returns))

        _halt = set(halt_days.get(sym, []))
        _lup = set(limit_up_days.get(sym, []))
        _ldown = set(limit_down_days.get(sym, []))

        # Dividend ex-date: on and after ex-date, close_hfq is back-adjusted
        ex_date = dividend_ex_dates.get(sym)

        for i, (ts, close) in enumerate(zip(bdates, closes, strict=True)):
            d = ts.date()
            is_st = False
            is_suspended = d in _halt

            # OHLC from close with simple spreads
            open_p = close * 0.999
            high_p = close * 1.005
            low_p = close * 0.995

            # Limit bands from previous close (use current if no prev)
            prev_close = float(closes[i - 1]) if i > 0 else close
            pct = _limit_pct(sym, is_st)
            if pct is None:
                limit_up_price = 1e9
                limit_down_price = 0.0
            else:
                limit_up_price = round(prev_close * (1 + pct), 2)
                limit_down_price = round(prev_close * (1 - pct), 2)

            # For injected limit-up days, clamp high to limit_up and set hit
            hit_lu = (i > 0) and (d in _lup)
            hit_ld = (i > 0) and (d in _ldown)
            if hit_lu:
                high_p = limit_up_price
                close = limit_up_price
            if hit_ld:
                low_p = limit_down_price
                close = limit_down_price

            # close_hfq: back-adjust prices before the ex-date for the dividend
            close_hfq = close
            if ex_date is not None and d < ex_date and prev_close > 0:
                # On the ex-date the dividend is paid; adjust historical prices
                # by factor = (prev_close_on_ex_eve - dividend) / prev_close_on_ex_eve
                # We approximate with a fixed factor using _DIVIDEND_AMOUNT / _START_PRICE
                adj_factor = (_START_PRICE - _DIVIDEND_AMOUNT) / _START_PRICE
                close_hfq = close * adj_factor

            # total_return: post-ex-date prices are scaled by reinvestment factor
            total_return = close
            if ex_date is not None and d >= ex_date:
                tr_factor = 1.0 + _DIVIDEND_AMOUNT / _START_PRICE
                total_return = close * tr_factor

            rows.append(
                {
                    "date": ts,
                    "symbol": sym,
                    "open": float(open_p),
                    "high": float(high_p),
                    "low": float(low_p),
                    "close": float(close),
                    "close_hfq": float(close_hfq),
                    "total_return": float(total_return),
                    "volume": 1_000_000,
                    "amount": float(close * 1_000_000),
                    "turnover": 0.01,
                    "is_suspended": bool(is_suspended),
                    "is_st": bool(is_st),
                    "limit_up": float(limit_up_price),
                    "limit_down": float(limit_down_price),
                    "hit_limit_up": bool(hit_lu),
                    "hit_limit_down": bool(hit_ld),
                }
            )

    df = pd.DataFrame(rows)
    return PriceFrameSchema.validate(df)


def _build_corporate_actions(
    symbols: list[str],
    dividend_ex_dates: dict[str, date],
) -> pd.DataFrame:
    """Build a CorporateActionSchema-valid DataFrame with the injected dividends."""
    rows = []
    for sym, ex_dt in dividend_ex_dates.items():
        if sym in symbols:
            rows.append(
                {
                    "symbol": sym,
                    "ex_date": pd.Timestamp(ex_dt),
                    "kind": "cash_dividend",
                    "params_json": json.dumps({"amount_per_share": _DIVIDEND_AMOUNT}),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
    df = pd.DataFrame(rows)
    return CorporateActionSchema.validate(df)


def _build_calendar(symbols: list[str], start: date, end: date) -> pd.DataFrame:
    """Build a TradingCalendarSchema-valid 5-day-week calendar for all exchanges."""
    exchanges = {_exchange_for(s) for s in symbols} | {"SH"}
    rows = []
    all_dates = pd.date_range(start, end)
    for exch in exchanges:
        for ts in all_dates:
            rows.append(
                {
                    "exchange": exch,
                    "date": ts,
                    "is_trading_day": ts.weekday() < 5,
                }
            )
    df = pd.DataFrame(rows)
    return TradingCalendarSchema.validate(df)


def _build_fx(start: date, end: date, seed: int) -> pd.DataFrame:
    """Build a daily CNY_HKD FX series for [start, end]."""
    rng = np.random.default_rng(seed + 9999)
    bdates = _business_dates(start, end)
    rates = 0.91 + np.cumsum(rng.normal(0.0, 0.001, len(bdates)))
    return pd.DataFrame(
        {
            "date": bdates,
            "pair": "CNY_HKD",
            "rate": rates.clip(min=0.80, max=1.05),
        }
    )


def _build_fundamentals(symbols: list[str], start: date, end: date) -> pd.DataFrame:
    """Build placeholder bitemporal fundamentals for each symbol.

    Looks back one full quarter before start so that quarterly reports
    published within the window (start, end) are always available even when
    no quarter-end falls in the query range.
    """
    rows: list[dict[str, Any]] = []
    # Extend lookback so publication_date can land inside the range
    lookback_start = date(
        start.year - 1 if start.month <= 3 else start.year,
        (start.month - 4) % 12 + 1 if start.month > 3 else 10,
        1,
    )
    # Simpler: go back 120 days to ensure at least one quarter end is included
    lookback_start = start - timedelta(days=120)
    for sym in symbols:
        # One preliminary + one audited row per quarter-end in extended range
        for report_dt in _quarter_ends(lookback_start, end):
            for kind, lag in [("preliminary", 30), ("audited", 60)]:
                pub = report_dt + timedelta(days=lag)
                rows.append(
                    {
                        "symbol": sym,
                        "report_date": pd.Timestamp(report_dt),
                        "publication_date": pd.Timestamp(pub),
                        "known_as_of": pd.Timestamp(pub),
                        "statement_kind": kind,
                        "revenue": 1e10,
                        "net_income": 3e9,
                        "net_income_ex_nonrecurring": 2.95e9,
                        "operating_cash_flow": 3.5e9,
                        "capex": 2e8,
                        "total_assets": 8e10,
                        "total_equity": 5e10,
                        "total_debt": 1e10,
                        "goodwill": 0.0,
                        "minority_interest": 1e8,
                        "d_and_a": 3e8,
                        "working_capital_change": 1e8,
                        "pe": 25.0,
                        "pb": 8.0,
                        "ps": 10.0,
                        "ev_ebitda": 15.0,
                        "roe": 0.25,
                        "roic": 0.22,
                        "roa": 0.15,
                        "gross_margin": 0.92,
                        "net_margin": 0.30,
                        "dividend_yield": 0.02,
                        "market_cap": 2e12,
                        "market_cap_free_float": 1.5e12,
                        "is_soe": sym.endswith(".SH"),
                        "is_stock_connect_eligible": True,
                    }
                )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return FundamentalsFrameSchema.validate(df)


def _build_sectors(symbols: list[str]) -> pd.DataFrame:
    """Return a sector table for all symbols."""
    rows = []
    for i, sym in enumerate(symbols):
        sector = _SECTORS[i % len(_SECTORS)]
        rows.append({"symbol": sym, "sector_l1": sector, "sector_l2": f"{sector}-A"})
    return pd.DataFrame(rows)


def _quarter_ends(start: date, end: date) -> list[date]:
    """Enumerate calendar quarter ends within [start, end]."""
    ends = [(3, 31), (6, 30), (9, 30), (12, 31)]
    out: list[date] = []
    for year in range(start.year, end.year + 1):
        for month, day in ends:
            d = date(year, month, day)
            if start <= d <= end:
                out.append(d)
    return out


# ── SyntheticMarket ────────────────────────────────────────────────────────


class SyntheticMarket:
    """In-memory DataRepository-compatible object for engine tests.

    Exposes the same public API as DataRepository (get_prices,
    get_fundamentals, get_trading_calendar, get_corporate_actions,
    get_sector, get_universe_over_time, get_fx_series) backed by
    deterministic pre-built DataFrames. No DuckDB cache; no upstream calls.
    """

    def __init__(
        self,
        symbols: list[str],
        start: date,
        end: date,
        prices: pd.DataFrame,
        fundamentals: pd.DataFrame,
        corporate_actions: pd.DataFrame,
        calendar: pd.DataFrame,
        fx: pd.DataFrame,
        sectors: pd.DataFrame,
    ) -> None:
        self._symbols = symbols
        self._start = start
        self._end = end
        self._prices = prices
        self._fundamentals = fundamentals
        self._corporate_actions = corporate_actions
        self._calendar = calendar
        self._fx = fx
        self._sectors = sectors

    # ── prices ─────────────────────────────────────────────────────────────

    def get_prices(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        """Return schema-valid prices for symbols within [start, end]."""
        if len(symbols) == 0:
            return PriceFrameSchema.validate(_empty_price_frame())
        mask = (
            self._prices["symbol"].isin(symbols)
            & (self._prices["date"] >= pd.Timestamp(start))
            & (self._prices["date"] <= pd.Timestamp(end))
        )
        return self._prices[mask].reset_index(drop=True)

    # ── fundamentals ───────────────────────────────────────────────────────

    def get_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
        *,
        asof: date | None = None,
    ) -> pd.DataFrame:
        """Return PIT-filtered fundamentals for symbols."""
        if len(symbols) == 0:
            return pd.DataFrame()
        cutoff = pd.Timestamp(asof if asof is not None else end)
        mask = self._fundamentals["symbol"].isin(symbols) & (
            self._fundamentals["known_as_of"] <= cutoff
        )
        return self._fundamentals[mask].reset_index(drop=True)

    # ── corporate actions ──────────────────────────────────────────────────

    def get_corporate_actions(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        """Return corporate actions for symbols within [start, end]."""
        if len(symbols) == 0:
            return pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
        mask = (
            self._corporate_actions["symbol"].isin(symbols)
            & (self._corporate_actions["ex_date"] >= pd.Timestamp(start))
            & (self._corporate_actions["ex_date"] <= pd.Timestamp(end))
        )
        return self._corporate_actions[mask].reset_index(drop=True)

    # ── trading calendar ───────────────────────────────────────────────────

    def get_trading_calendar(self, exchange: str, start: date, end: date) -> pd.DataFrame:
        """Return 5-day-week calendar for exchange within [start, end]."""
        mask = (
            (self._calendar["exchange"] == exchange)
            & (self._calendar["date"] >= pd.Timestamp(start))
            & (self._calendar["date"] <= pd.Timestamp(end))
        )
        result = self._calendar[mask].reset_index(drop=True)
        if result.empty:
            # Build on-the-fly for any exchange not pre-built
            all_dates = pd.date_range(start, end)
            result = pd.DataFrame(
                {
                    "exchange": exchange,
                    "date": all_dates,
                    "is_trading_day": [d.weekday() < 5 for d in all_dates],
                }
            )
        return result

    # ── sectors ────────────────────────────────────────────────────────────

    def get_sector(self, symbols: list[str]) -> pd.DataFrame:
        """Return sector classification for symbols."""
        if len(symbols) == 0:
            return pd.DataFrame(columns=["symbol", "sector_l1", "sector_l2"])
        return self._sectors[self._sectors["symbol"].isin(symbols)].reset_index(drop=True)

    # ── universe over time ─────────────────────────────────────────────────

    def get_universe_over_time(
        self,
        index: str,
        start: date,
        end: date,
        *,
        freq: str = "ME",
    ) -> pd.DataFrame:
        """Return (date, symbol) frame of A-share symbols at each sampled date."""
        a_symbols = [s for s in self._symbols if s.endswith(".SH") or s.endswith(".SZ")]
        if not a_symbols:
            return pd.DataFrame(columns=["date", "index_name", "symbol", "weight"])
        sample_dates = pd.date_range(start, end, freq=freq)
        n = len(a_symbols)
        rows = []
        for ts in sample_dates:
            for sym in a_symbols:
                rows.append(
                    {
                        "date": ts,
                        "index_name": index,
                        "symbol": sym,
                        "weight": 1.0 / n,
                    }
                )
        if not rows:
            return pd.DataFrame(columns=["date", "index_name", "symbol", "weight"])
        return pd.DataFrame(rows)

    # ── FX ─────────────────────────────────────────────────────────────────

    def get_fx_series(self, pair: str, start: date, end: date) -> pd.DataFrame:
        """Return daily FX rates for pair within [start, end].

        Only CNY_HKD is supported; other pairs raise UserInputError.
        Columns: date, pair, rate.
        """
        if pair != "CNY_HKD":
            raise UserInputError(f"unsupported FX pair {pair!r}; only 'CNY_HKD' is available")
        mask = (
            (self._fx["pair"] == pair)
            & (self._fx["date"] >= pd.Timestamp(start))
            & (self._fx["date"] <= pd.Timestamp(end))
        )
        return self._fx[mask].reset_index(drop=True)

    # ── AH premium ─────────────────────────────────────────────────────────

    def compute_ah_premium(
        self,
        pair: Any,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Delegate to the same logic as DataRepository.compute_ah_premium."""
        a_sym = str(pair.a_symbol)
        h_sym = str(pair.h_symbol)
        a_prices = self.get_prices([a_sym], start, end)
        h_prices = self.get_prices([h_sym], start, end)
        fx = self.get_fx_series("CNY_HKD", start, end)
        if a_prices.empty or h_prices.empty or fx.empty:
            return pd.DataFrame(columns=["date", "close_a", "close_h", "fx_rate", "premium"])
        a_slim = a_prices[["date", "close"]].rename(columns={"close": "close_a"})
        h_slim = h_prices[["date", "close"]].rename(columns={"close": "close_h"})
        fx_slim = fx[["date", "rate"]].rename(columns={"rate": "fx_rate"})
        # Normalise all date columns to the same datetime64 resolution before
        # pd.merge_asof, which requires identical key dtypes.
        for _df in (a_slim, h_slim, fx_slim):
            _df["date"] = _df["date"].astype("datetime64[us]")
        merged = a_slim.merge(h_slim, on="date", how="inner").sort_values("date")
        merged = pd.merge_asof(merged, fx_slim.sort_values("date"), on="date", direction="backward")
        merged = merged.dropna(subset=["fx_rate"])
        merged["premium"] = merged["close_a"] / (merged["close_h"] * merged["fx_rate"]) - 1.0
        return merged.reset_index(drop=True)

    # ── resample (pass-through from DataRepository static method) ──────────

    @staticmethod
    def resample(frame: pd.DataFrame, freq: str) -> pd.DataFrame:
        """Delegate to DataRepository.resample."""
        return DataRepository.resample(frame, freq)


# ── public factory ────────────────────────────────────────────────────────────


def build_synthetic_market(
    start: date,
    end: date,
    symbols: list[str],
    seed: int = 42,
    **kwargs: Any,
) -> SyntheticMarket:
    """Build a deterministic in-memory SyntheticMarket for engine tests.

    Parameters
    ----------
    start, end:
        Inclusive date range for all generated data.
    symbols:
        List of symbols in canonical ``<code>.<exchange>`` form.
    seed:
        RNG seed (default 42); same seed always produces identical data.
    **kwargs:
        halt_days: dict[str, list[date]]   -- is_suspended=True on these dates
        limit_up_days: dict[str, list[date]] -- hit_limit_up=True on these dates
        limit_down_days: dict[str, list[date]] -- hit_limit_down=True on these dates
        extra_corporate_actions: list[dict] -- additional corporate-action rows
            Each dict must have keys: symbol, ex_date, kind, params_json.
            These are appended to the auto-generated corporate actions and
            must be CorporateActionSchema-valid.
    """
    halt_days: dict[str, list[date]] = kwargs.get("halt_days", {})
    limit_up_days: dict[str, list[date]] = kwargs.get("limit_up_days", {})
    limit_down_days: dict[str, list[date]] = kwargs.get("limit_down_days", {})
    extra_corporate_actions: list[dict[str, Any]] = kwargs.get("extra_corporate_actions", [])

    # Pick the first A-share for the dividend injection
    a_symbols = [s for s in symbols if s.endswith(".SH") or s.endswith(".SZ")]
    dividend_ex_dates: dict[str, date] = {}
    if a_symbols:
        # Place ex-date roughly in the middle of the range
        mid = start + (end - start) // 2
        # Round to next Monday if on a weekend
        while mid.weekday() >= 5:
            mid = mid + timedelta(days=1)
        dividend_ex_dates[a_symbols[0]] = mid

    prices = _build_prices(
        symbols,
        start,
        end,
        seed,
        halt_days,
        limit_up_days,
        limit_down_days,
        dividend_ex_dates,
    )
    corporate_actions = _build_corporate_actions(symbols, dividend_ex_dates)

    # Append any caller-supplied extra corporate actions
    if extra_corporate_actions:
        extra_rows = []
        for ca in extra_corporate_actions:
            extra_rows.append(
                {
                    "symbol": str(ca["symbol"]),
                    "ex_date": pd.Timestamp(ca["ex_date"]),
                    "kind": str(ca["kind"]),
                    "params_json": str(ca["params_json"]),
                }
            )
        extra_df = CorporateActionSchema.validate(pd.DataFrame(extra_rows))
        corporate_actions = pd.concat([corporate_actions, extra_df], ignore_index=True)

    calendar = _build_calendar(symbols, start, end)
    fx = _build_fx(start, end, seed)
    fundamentals = _build_fundamentals(symbols, start, end)
    sectors = _build_sectors(symbols)

    return SyntheticMarket(
        symbols=symbols,
        start=start,
        end=end,
        prices=prices,
        fundamentals=fundamentals,
        corporate_actions=corporate_actions,
        calendar=calendar,
        fx=fx,
        sectors=sectors,
    )


# ── helpers ───────────────────────────────────────────────────────────────────


def _empty_price_frame() -> pd.DataFrame:
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
