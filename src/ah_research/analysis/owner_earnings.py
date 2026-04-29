"""Buffett (1986) owner-earnings series from fundamentals."""

from __future__ import annotations

import pandas as pd


def owner_earnings_series(fundamentals: pd.DataFrame) -> pd.Series:
    """Compute annual owner-earnings from a bitemporal fundamentals frame.

    Formula: owner_earnings = net_income + d_and_a - capex - working_capital_change.

    Rows with any NaN in the four input columns are dropped. The returned
    Series is indexed by ``report_date`` (fiscal year end) and sorted ascending.
    """
    required = ["net_income", "d_and_a", "capex", "working_capital_change", "report_date"]
    if fundamentals.empty or any(c not in fundamentals.columns for c in required):
        return pd.Series([], dtype=float, name="owner_earnings")

    f = fundamentals.dropna(subset=required[:4]).copy()
    if f.empty:
        return pd.Series([], dtype=float, name="owner_earnings")

    oe = (
        f["net_income"].astype(float)
        + f["d_and_a"].astype(float)
        - f["capex"].astype(float)
        - f["working_capital_change"].astype(float)
    )
    result = pd.Series(
        oe.to_numpy(),
        index=pd.DatetimeIndex(f["report_date"].to_numpy()),
        name="owner_earnings",
        dtype=float,
    )
    return result.sort_index()
