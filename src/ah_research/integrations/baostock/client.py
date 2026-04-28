"""Baostock client — A-share prices, constituents, calendar, corporate actions.

Protocol conformance (all return source-native DataFrames; converters in
``data/converters.py`` reshape to domain schemas):

- ``PriceSource.fetch_prices``           ← ``bs.query_history_k_data_plus``
- ``ConstituentsSource.fetch_constituents`` ← ``bs.query_hs300_stocks`` / ``query_zz500_stocks``
- ``CalendarSource.fetch_calendar``       ← ``bs.query_trade_dates``
- ``CorporateActionsSource.fetch_corporate_actions`` ← ``bs.query_dividend_data``
- ``SectorSource.fetch_sectors``          ← ``bs.query_stock_industry``

Baostock handles only SH/SZ; any non-A symbol yields empty output so this
client can be wired alongside an AKShare HK client without raising.

Error remap: Baostock indicates errors via ``rs.error_code`` /
``rs.error_msg`` on the returned ResultData object (never by exception).
We map these codes to our :mod:`ah_research.exceptions` hierarchy so
upstream code never sees baostock-specific errors.

Retry: transient errors (rate limit / network / 5xx) are retried with
exponential backoff via tenacity. Non-retryable (auth, schema drift)
fail fast.
"""

from __future__ import annotations

from datetime import date
from types import TracebackType
from typing import Any, Self

import baostock as bs
import pandas as pd
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ah_research.exceptions import (
    SourceAuthError,
    SourceDataError,
    SourceRateLimit,
    SourceSchemaError,
    SourceUnavailable,
)
from ah_research.logging import get_logger

log = get_logger(__name__)

# The full field list Baostock supports for daily K-line. We ask for a
# superset and trust the converter to subset down to the domain schema.
_PRICE_FIELDS = "date,code,open,high,low,close,volume,amount,turn,tradestatus,isST,pctChg"

# Symbol → Baostock code conversion:
#   600519.SH → sh.600519
#   000001.SZ → sz.000001
#
# Baostock rejects anything else. HK symbols (.HK) return empty output.


def _to_bs_code(symbol: str) -> str | None:
    code, _, exchange = symbol.partition(".")
    if exchange in ("SH", "SZ"):
        return f"{exchange.lower()}.{code}"
    return None


def _to_canonical(bs_code: str) -> str:
    """``sh.600519`` → ``600519.SH``."""
    exchange, _, code = bs_code.partition(".")
    return f"{code}.{exchange.upper()}"


def _check_baostock_error(rs: Any, context: str) -> None:
    """Inspect Baostock's ResultData error fields and raise a remapped
    exception on failure. ``rs.error_code`` is a string; ``"0"`` means OK.

    Error code reference (informal, derived from baostock source):
    - ``10001xx``: auth / login failures (not retryable)
    - ``10002xx``: parameter errors (not retryable; our bug)
    - ``10003xx``: rate limit / throttle (retryable)
    - ``10004xx``: data unavailable (not retryable; no such symbol etc.)
    - ``10005xx``: network / server errors (retryable)
    """
    if rs.error_code == "0":
        return
    code = rs.error_code
    msg = f"[{context}] {code}: {rs.error_msg}"
    if code.startswith("10001"):
        raise SourceAuthError(msg)
    if code.startswith("10003"):
        raise SourceRateLimit(msg)
    if code.startswith("10004"):
        raise SourceDataError(msg)
    if code.startswith("10005"):
        raise SourceUnavailable(msg)
    raise SourceSchemaError(msg)


def _drain(rs: Any) -> list[list[str]]:
    """Pull every row from a Baostock ResultData iterator."""
    rows: list[list[str]] = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    return rows


# ── Retry wrapper: only for transient error types ────────────────────────────

_retry_transient = retry(
    retry=retry_if_exception_type((SourceRateLimit, SourceUnavailable)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)


class BaostockClient:
    """Concrete integration for Baostock.

    Usage::

        with BaostockClient() as bao:
            df = bao.fetch_prices(["600519.SH"], date(2024, 1, 1), date(2024, 6, 30))
    """

    def __init__(self) -> None:
        rs = bs.login()
        _check_baostock_error(rs, "login")
        log.info("baostock_login_ok")

    def close(self) -> None:
        bs.logout()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ── prices ─────────────────────────────────────────────────────────────

    @_retry_transient
    def fetch_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return source-native daily K-line for A-share symbols.

        Shape: one row per (date, symbol). Non-A symbols are silently
        skipped (useful when wired behind a composite router).

        Columns (source-native, string-typed):
            date, code, open, high, low, close, volume, amount, turn,
            tradestatus, isST, pctChg, symbol

        ``symbol`` is the canonical form (e.g. ``600519.SH``); ``code``
        keeps the baostock form (``sh.600519``) in case downstream wants it.

        Uses ``adjustflag='3'`` (no adjustment) — we back-adjust ourselves
        in the converter so the same logic applies to both A and HK.
        """
        frames: list[pd.DataFrame] = []
        for symbol in symbols:
            bs_code = _to_bs_code(symbol)
            if bs_code is None:
                continue
            rs = bs.query_history_k_data_plus(
                bs_code,
                _PRICE_FIELDS,
                start_date=str(start),
                end_date=str(end),
                frequency="d",
                adjustflag="3",
            )
            _check_baostock_error(rs, f"query_history_k_data_plus({symbol})")
            rows = _drain(rs)
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=rs.fields)
            df["symbol"] = symbol
            frames.append(df)
        if not frames:
            return pd.DataFrame(columns=[*_PRICE_FIELDS.split(","), "symbol"])
        return pd.concat(frames, ignore_index=True)

    # ── index constituents ─────────────────────────────────────────────────

    @_retry_transient
    def fetch_constituents(self, index: str, asof: date) -> pd.DataFrame:
        """Return constituents of ``index`` at ``asof``.

        Supported indices: ``CSI300`` → HS300, ``CSI500`` → ZZ500. Other
        names raise ``SourceDataError`` (Baostock doesn't cover them).
        """
        query = {
            "CSI300": bs.query_hs300_stocks,
            "CSI500": bs.query_zz500_stocks,
        }.get(index.upper())
        if query is None:
            raise SourceDataError(f"Baostock does not supply constituents for index={index!r}")
        rs = query(date=str(asof))
        _check_baostock_error(rs, f"constituents({index})")
        rows = _drain(rs)
        if not rows:
            return pd.DataFrame(columns=["updateDate", "symbol", "code_name", "weight"])
        df = pd.DataFrame(rows, columns=rs.fields)
        df["symbol"] = df["code"].map(_to_canonical)
        # Baostock doesn't supply weights for these index queries; emit
        # 1/N placeholder so downstream schema is satisfied. Real weights
        # require paid data sources — Phase 2.
        n = len(df)
        df["weight"] = 1.0 / n if n > 0 else 0.0
        return df[["updateDate", "symbol", "code_name", "weight"]]

    # ── trading calendar ───────────────────────────────────────────────────

    @_retry_transient
    def fetch_calendar(
        self,
        exchange: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Baostock exposes one A-share calendar (SSE + SZSE align). We
        return the same frame for SH and SZ, tagged with ``exchange``."""
        rs = bs.query_trade_dates(start_date=str(start), end_date=str(end))
        _check_baostock_error(rs, "query_trade_dates")
        rows = _drain(rs)
        if not rows:
            return pd.DataFrame(columns=["exchange", "date", "is_trading_day"])
        df = pd.DataFrame(rows, columns=rs.fields)
        df = df.rename(columns={"calendar_date": "date"})
        df["date"] = pd.to_datetime(df["date"])
        df["is_trading_day"] = df["is_trading_day"].astype(str) == "1"
        df["exchange"] = exchange
        return df[["exchange", "date", "is_trading_day"]]

    # ── corporate actions (dividends) ──────────────────────────────────────

    @_retry_transient
    def fetch_corporate_actions(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return cash dividends + stock dividends within ``[start, end]``.

        Baostock's dividend query is per (code, year, yearType). We
        enumerate years in the range and filter by ex-date afterward.
        Splits / rights-issues are not covered by this API — deferred
        to Phase 2 (requires a different source).
        """
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            bs_code = _to_bs_code(symbol)
            if bs_code is None:
                continue
            for year in range(start.year, end.year + 1):
                rs = bs.query_dividend_data(code=bs_code, year=str(year), yearType="operate")
                _check_baostock_error(rs, f"dividend({symbol},{year})")
                data = _drain(rs)
                for r in data:
                    record = dict(zip(rs.fields, r, strict=True))
                    ex_date_str = record.get("dividOperateDate") or ""
                    if not ex_date_str:
                        continue
                    ex_date = pd.Timestamp(ex_date_str)
                    if not (pd.Timestamp(start) <= ex_date <= pd.Timestamp(end)):
                        continue
                    cash = record.get("dividCashPsBeforeTax") or ""
                    try:
                        amount = float(cash) if cash else 0.0
                    except ValueError:
                        amount = 0.0
                    if amount <= 0:
                        continue
                    rows.append(
                        {
                            "symbol": symbol,
                            "ex_date": ex_date,
                            "kind": "cash_dividend",
                            "params_json": f'{{"amount_per_share": {amount}, "currency": "CNY"}}',
                        }
                    )
        if not rows:
            return pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
        return pd.DataFrame(rows)

    # ── sectors ────────────────────────────────────────────────────────────

    @_retry_transient
    def fetch_sectors(self, symbols: list[str]) -> pd.DataFrame:
        """Return SWS-style industry classification.

        Baostock exposes ``industry`` and ``industry_classification`` fields.
        We map industry → sector_l1 and store the full classification as
        sector_l2 (closest approximation without a richer source).
        """
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            bs_code = _to_bs_code(symbol)
            if bs_code is None:
                continue
            rs = bs.query_stock_industry(code=bs_code)
            _check_baostock_error(rs, f"industry({symbol})")
            data = _drain(rs)
            if not data:
                continue
            record = dict(zip(rs.fields, data[0], strict=True))
            rows.append(
                {
                    "symbol": symbol,
                    "sector_l1": record.get("industry", "Unknown"),
                    "sector_l2": record.get("industryClassification", "Unknown"),
                }
            )
        if not rows:
            return pd.DataFrame(columns=["symbol", "sector_l1", "sector_l2"])
        return pd.DataFrame(rows)
