"""Pandera schemas — runtime-validated at every layer boundary.

These are the binding contract for the DataFrames that flow between layers
(converters → cache → repository → research). Every converter validates its
output; every repository method validates on return.

Each schema is ``strict=True`` and ``coerce=True``:
 - strict: unexpected columns are a schema error (catches drift early).
 - coerce: pandera will cast types at validation time (e.g., int64 → int).

Design:
- "Source" schemas live alongside their integration client (one per source).
- "Domain" schemas live here and describe what the rest of the system sees.
- "Cache" rows on disk mirror the domain schemas exactly (see data/cache.py).

See spec §3 for field-by-field rationale.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series


class PriceFrameSchema(pa.DataFrameModel):
    """Daily OHLCV + adjustment + trading-state flags.

    ``close_hfq`` and ``total_return`` are DERIVED by the converter, not
    sourced directly — we back-adjust ourselves so the same logic applies
    to Baostock (A-shares) and AKshare (HK).
    """

    date: Series[pa.DateTime]
    symbol: Series[str]
    open: Series[float]
    high: Series[float]
    low: Series[float]
    close: Series[float]
    close_hfq: Series[float]  # back-adjusted; DEFAULT for research
    total_return: Series[float]  # cum-dividend-reinvested; same scale as close
    volume: Series[int] = pa.Field(ge=0)
    amount: Series[float] = pa.Field(ge=0)
    turnover: Series[float]
    is_suspended: Series[bool]
    is_st: Series[bool]
    limit_up: Series[float]
    limit_down: Series[float]
    hit_limit_up: Series[bool]
    hit_limit_down: Series[bool]

    class Config:
        strict = True
        coerce = True


class FundamentalsFrameSchema(pa.DataFrameModel):
    """Bitemporal fundamentals row.

    Three time dimensions are all mandatory:

    - ``report_date``: the fiscal period the row describes.
    - ``publication_date``: when this number was first made public.
    - ``known_as_of``: the earliest date on which this exact value was
      knowable (differs from ``publication_date`` only for restatements,
      which carry the restatement-announcement date).

    A PIT query at date ``D`` filters to rows where
    ``publication_date <= D AND known_as_of <= D``.
    """

    symbol: Series[str]
    report_date: Series[pa.DateTime]
    publication_date: Series[pa.DateTime]
    known_as_of: Series[pa.DateTime]
    statement_kind: Series[str] = pa.Field(isin=["preliminary", "audited", "restated"])

    # Raw line items (CNY / HKD, not FX-adjusted).
    revenue: Series[float]
    net_income: Series[float]
    net_income_ex_nonrecurring: Series[float]
    operating_cash_flow: Series[float]
    capex: Series[float]
    total_assets: Series[float]
    total_equity: Series[float]
    total_debt: Series[float]
    goodwill: Series[float]
    minority_interest: Series[float]
    d_and_a: Series[float]
    working_capital_change: Series[float]

    # Derived ratios.
    pe: Series[float]
    pb: Series[float]
    ps: Series[float]
    ev_ebitda: Series[float]
    roe: Series[float]
    roic: Series[float]
    roa: Series[float]
    gross_margin: Series[float]
    net_margin: Series[float]
    dividend_yield: Series[float]
    market_cap: Series[float]
    market_cap_free_float: Series[float]

    # Flags.
    is_soe: Series[bool]
    is_stock_connect_eligible: Series[bool]

    class Config:
        strict = True
        coerce = True


class TradingCalendarSchema(pa.DataFrameModel):
    """Per-venue trading-day flags."""

    exchange: Series[str] = pa.Field(isin=["SH", "SZ", "HK"])
    date: Series[pa.DateTime]
    is_trading_day: Series[bool]

    class Config:
        strict = True
        coerce = True


class CorporateActionSchema(pa.DataFrameModel):
    """One event per (symbol, ex_date, kind).

    ``params_json`` holds the kind-specific payload as a serialised JSON
    string — storing a ``dict`` column in DuckDB is painful and unnecessary
    here. Repository code decodes with ``json.loads`` at the boundary.
    """

    symbol: Series[str]
    ex_date: Series[pa.DateTime]
    kind: Series[str] = pa.Field(
        isin=[
            "cash_dividend",
            "stock_dividend",
            "split",
            "reverse_split",
            "rights_issue",
            "spin_off",
        ]
    )
    params_json: Series[str]

    class Config:
        strict = True
        coerce = True
