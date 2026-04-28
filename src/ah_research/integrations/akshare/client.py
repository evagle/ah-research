"""AKShare client — HK prices and CNY/HKD FX.

Protocol conformance:

- ``PriceSource.fetch_prices``  ← ``ak.stock_hk_hist``
- ``FXSource.fetch_fx``         ← ``ak.currency_boc_sina``

This client handles ONLY HK symbols. Non-HK symbols are silently skipped
so it can be composed with ``BaostockClient`` via a router.

Calendar, constituents, sectors, and corporate-actions for HK are
Phase 2 work — AKShare has functions for those but their field layouts
differ enough that a live-tested implementation is a larger commit.

Error remap: AKShare raises plain exceptions on HTTP / parsing errors.
We catch those at the boundary and remap to our ``SourceError``
hierarchy. No error-code field to check.

Retry: transient network errors (``ConnectionError``, ``Timeout``) are
retried via tenacity with exponential backoff.
"""

from __future__ import annotations

from datetime import date

import akshare as ak
import pandas as pd
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ah_research.exceptions import (
    SourceDataError,
    SourceSchemaError,
    SourceUnavailable,
)
from ah_research.logging import get_logger

log = get_logger(__name__)

# AKShare HK hist uses zero-padded numeric-only codes: 0700.HK → "00700"
# We zero-pad to 5 chars (which matches what stock_hk_hist expects
# according to its default symbol "00593").


def _to_ak_hk_code(symbol: str) -> str | None:
    code, _, exchange = symbol.partition(".")
    if exchange != "HK":
        return None
    return code.zfill(5)


# FX currency label AKShare recognises — "港币" is the Chinese name used
# as the dict key inside the library; requests with other names raise
# KeyError.
_HKD_LABEL = "港币"


_retry_transient = retry(
    retry=retry_if_exception_type(SourceUnavailable),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)


def _remap_akshare_exception(exc: BaseException, context: str) -> BaseException:
    """Map an AKShare-raised exception to our SourceError hierarchy."""
    if isinstance(exc, KeyError):
        return SourceSchemaError(
            f"[{context}] AKShare returned unexpected shape or unknown key: {exc}"
        )
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name or "network" in name:
        return SourceUnavailable(f"[{context}] {type(exc).__name__}: {exc}")
    return SourceDataError(f"[{context}] {type(exc).__name__}: {exc}")


class AKShareClient:
    """Concrete integration for AKShare (HK + FX)."""

    # ── prices ─────────────────────────────────────────────────────────────

    @_retry_transient
    def fetch_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return source-native daily prices for HK symbols.

        AKShare's ``stock_hk_hist`` returns one-symbol frames with Chinese
        column names. We rename to English and stack per symbol.

        Columns produced (source-native-ish, after renaming):
            date, symbol, open, close, high, low, volume, amount,
            amplitude, pct_change, change, turnover

        ``amplitude`` is ``(high - low) / prev_close``; we pass through
        as-is. ``pct_change`` is same-day percent change in close.
        """
        frames: list[pd.DataFrame] = []
        for symbol in symbols:
            ak_code = _to_ak_hk_code(symbol)
            if ak_code is None:
                continue
            try:
                raw = ak.stock_hk_hist(
                    symbol=ak_code,
                    period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="",
                )
            except Exception as exc:  # remap at boundary
                raise _remap_akshare_exception(exc, f"stock_hk_hist({symbol})") from exc
            if len(raw) == 0:
                continue
            df = raw.rename(
                columns={
                    "日期": "date",
                    "开盘": "open",
                    "收盘": "close",
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume",
                    "成交额": "amount",
                    "振幅": "amplitude",
                    "涨跌幅": "pct_change",
                    "涨跌额": "change",
                    "换手率": "turnover",
                }
            )
            df["date"] = pd.to_datetime(df["date"])
            df["symbol"] = symbol
            # HK has no halt/ST flag in this source; default to False.
            df["is_suspended"] = False
            df["is_st"] = False
            frames.append(df)
        if not frames:
            return pd.DataFrame(
                columns=[
                    "date",
                    "symbol",
                    "open",
                    "close",
                    "high",
                    "low",
                    "volume",
                    "amount",
                    "turnover",
                    "is_suspended",
                    "is_st",
                ]
            )
        return pd.concat(frames, ignore_index=True)

    # ── FX ─────────────────────────────────────────────────────────────────

    @_retry_transient
    def fetch_fx(
        self,
        pair: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return daily CNY/HKD rates.

        ``pair`` is the canonical label; we only support ``CNY_HKD`` /
        ``HKD_CNY`` (same series, inverted at the converter if needed).
        Non-supported pairs raise ``SourceDataError``.

        Rate convention: AKShare's BoC fix publishes per-100 HKD in CNY
        (中行中间价 ~ 91 CNY per 100 HKD on 2024-06-03). We normalise to
        **CNY per 1 HKD** by dividing the published rate by 100.
        """
        if pair.upper() not in ("CNY_HKD", "HKD_CNY"):
            raise SourceDataError(f"AKShareClient only supports CNY_HKD / HKD_CNY, got {pair!r}")
        try:
            raw = ak.currency_boc_sina(
                symbol=_HKD_LABEL,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        except Exception as exc:
            raise _remap_akshare_exception(exc, "currency_boc_sina") from exc
        if len(raw) == 0:
            return pd.DataFrame(columns=["date", "pair", "rate"])
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(raw["日期"]),
                "pair": "CNY_HKD",
                "rate": raw["央行中间价"].astype(float) / 100.0,
            }
        )
        return df
