"""Pure functions: source-native DataFrame → domain PriceFrame / FundamentalsFrame.

The integration layer produces source-shaped data (column names and dtypes
from Baostock / AKshare). Converters normalise to the domain schema AND
compute derived columns that no source provides directly:

- ``close_hfq``: back-adjusted close (historical prices scaled DOWN by
  cumulative corporate-action factors, so the most recent close is
  unchanged and historical discontinuities disappear). This is the
  industry-standard series for back-testing.
- ``total_return``: dividends reinvested at ex-date, splits don't create
  a return event. Same scale as close.
- ``limit_up`` / ``limit_down`` / ``hit_limit_*``: venue-aware daily
  price-limit bands, computed from previous close and security type.

All adjustment math lives in ``compute_adjusted_prices``. Limit detection
lives in ``_compute_limits``. Both are pure — they do not mutate inputs
and produce deterministic output.

Output is pandera-validated before return.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import pandera.pandas as pa

from ah_research.model.schemas import FundamentalsFrameSchema, PriceFrameSchema

# ── adjustment factors ───────────────────────────────────────────────────────

# Price-limit sentinels for HK, which has no daily ±pct limit. We use values
# that hit_limit_* comparisons will never trigger under any realistic close.
_HK_SENTINEL_UP = 1e9
_HK_SENTINEL_DOWN = 0.0


def _action_factors(
    kind: str, params: dict[str, Any], prev_close: float
) -> tuple[float, float] | None:
    """Return ``(hfq_factor, tr_factor)`` for a corporate action, or ``None``
    if the action is unsupported.

    - ``hfq_factor`` multiplies pre-ex-date ``close_hfq``.
    - ``tr_factor`` multiplies post-ex-date (inclusive) ``total_return``.

    Supported kinds (Phase 1):
    - ``cash_dividend``: hfq = (prev-div)/prev, tr = 1 + div/prev.
    - ``split``: ``ratio = shares_after/shares_before``. hfq = 1/ratio, tr = 1.
    - ``reverse_split``: ``ratio = shares_before/shares_after`` (i.e., > 1).
      hfq = ratio, tr = 1.

    ``stock_dividend``, ``rights_issue``, ``spin_off`` are recognised but
    deferred to Phase 2 (more modelling is needed for rights-issue economics).
    """
    if prev_close <= 0:
        return None
    if kind == "cash_dividend":
        div = float(params["amount_per_share"])
        hfq = (prev_close - div) / prev_close
        tr = 1.0 + div / prev_close
        return hfq, tr
    if kind == "split":
        ratio = float(params["ratio"])
        if ratio <= 0:
            return None
        return 1.0 / ratio, 1.0
    if kind == "reverse_split":
        ratio = float(params["ratio"])
        if ratio <= 0:
            return None
        return ratio, 1.0
    return None


def compute_adjusted_prices(
    raw: pd.DataFrame,
    corporate_actions: pd.DataFrame,
) -> pd.DataFrame:
    """Apply corporate actions to produce ``close_hfq`` and ``total_return``.

    The input ``raw`` must have columns ``date``, ``symbol``, ``close``.
    Other columns pass through untouched. Output preserves input row order
    and adds two columns.
    """
    df = raw.copy()
    df["close_hfq"] = df["close"].astype(float)
    df["total_return"] = df["close"].astype(float)

    if len(corporate_actions) == 0:
        return df

    for symbol, actions_for_symbol in corporate_actions.groupby("symbol"):
        symbol_mask = df["symbol"] == symbol
        if not symbol_mask.any():
            continue

        symbol_prices = df[symbol_mask].sort_values("date")

        # Process actions oldest-first. Each action's factor multiplies
        # through all close_hfq rows BEFORE its ex-date, so processing in
        # ex-date order gives the correct cumulative back-adjustment.
        for _, action in actions_for_symbol.sort_values("ex_date").iterrows():
            ex_date = pd.Timestamp(action["ex_date"])
            pre_prices = symbol_prices[symbol_prices["date"] < ex_date]
            if len(pre_prices) == 0:
                # No prior close available; skip rather than divide by zero
                continue
            prev_close = float(pre_prices.iloc[-1]["close"])
            params = json.loads(action["params_json"])
            factors = _action_factors(action["kind"], params, prev_close)
            if factors is None:
                continue
            hfq_factor, tr_factor = factors

            pre_idx = df.index[symbol_mask & (df["date"] < ex_date)]
            df.loc[pre_idx, "close_hfq"] = df.loc[pre_idx, "close_hfq"] * hfq_factor

            post_idx = df.index[symbol_mask & (df["date"] >= ex_date)]
            df.loc[post_idx, "total_return"] = df.loc[post_idx, "total_return"] * tr_factor

    return df


# ── price limits ─────────────────────────────────────────────────────────────


def _limit_pct_for_symbol(symbol: str, is_st: bool) -> float | None:
    """Return the ``±pct`` daily price limit for ``symbol``.

    Returns ``None`` for venues without a daily limit (HK). ChiNext (300xxx)
    and STAR (688xxx) use ±20%; ST names use ±5%; everything else ±10%.
    """
    code, _, exchange = symbol.partition(".")
    if exchange == "HK":
        return None
    if code.startswith("300") or code.startswith("688"):
        return 0.20
    if is_st:
        return 0.05
    return 0.10


def _compute_limits_for_row(prev_close: float, symbol: str, is_st: bool) -> tuple[float, float]:
    pct = _limit_pct_for_symbol(symbol, is_st)
    if pct is None:
        return _HK_SENTINEL_UP, _HK_SENTINEL_DOWN
    return (
        round(prev_close * (1 + pct), 2),
        round(prev_close * (1 - pct), 2),
    )


def convert_prices(
    raw: pd.DataFrame,
    corporate_actions: pd.DataFrame,
) -> pd.DataFrame:
    """Full conversion: source-native prices + actions → domain PriceFrame.

    Output is ``PriceFrameSchema``-validated. Does not mutate ``raw``.
    """
    df = compute_adjusted_prices(raw, corporate_actions)
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    # prev_close within each symbol. First row of each group has no prev,
    # so we compute limits against the current close (limits will never be
    # exactly equal to high/low on a freshly-observed day, so hit flags
    # remain False) AND we force hit_limit_* = False for first rows below.
    prev_close = df.groupby("symbol")["close"].shift(1)
    prev_close_filled = prev_close.fillna(df["close"])

    limits = [
        _compute_limits_for_row(pc, sym, st)
        for pc, sym, st in zip(prev_close_filled, df["symbol"], df["is_st"], strict=True)
    ]
    df["limit_up"] = [lim[0] for lim in limits]
    df["limit_down"] = [lim[1] for lim in limits]

    # hit_limit: high reaches limit_up (with a small epsilon for float math)
    # OR low reaches limit_down. First row (no prev_close) is never a hit.
    has_prev = ~prev_close.isna()
    df["hit_limit_up"] = has_prev & (df["high"] >= df["limit_up"] - 0.01)
    df["hit_limit_down"] = has_prev & (df["low"] <= df["limit_down"] + 0.01)

    return _validate(PriceFrameSchema, df)


# ── fundamentals ─────────────────────────────────────────────────────────────


def convert_fundamentals(raw: pd.DataFrame) -> pd.DataFrame:
    """Domain FundamentalsFrame.

    Fills defaults the source may not provide:
    - ``known_as_of`` defaults to ``publication_date`` (i.e., this row has
      been knowable since it was published; restatements override).
    - ``statement_kind`` defaults to ``audited`` when the source supplies
      no restatement/prelim marker.
    - ``roic`` is approximated as ``net_income / (total_equity + total_debt)``
      when missing.
    """
    df = raw.copy()
    if "known_as_of" not in df.columns:
        df["known_as_of"] = df["publication_date"]
    if "statement_kind" not in df.columns:
        df["statement_kind"] = "audited"
    if "roic" not in df.columns:
        invested = df["total_equity"] + df["total_debt"]
        df["roic"] = np.where(invested > 0, df["net_income"] / invested, np.nan)
    return _validate(FundamentalsFrameSchema, df)


# ── internal ─────────────────────────────────────────────────────────────────


def _validate(schema: type[pa.DataFrameModel], df: pd.DataFrame) -> pd.DataFrame:
    """Run a pandera schema and return the (possibly coerced) DataFrame.

    The indirection is only to make call-sites short; pandera raises
    ``SchemaError`` / ``SchemaErrors`` directly on failure.
    """
    validated: pd.DataFrame = schema.validate(df)
    return validated.reset_index(drop=True)
