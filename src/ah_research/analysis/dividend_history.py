"""Dividend consistency grading (A-F) over trailing window."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd


def _extract_amount(row_params: str | dict[str, object]) -> float:
    """Parse ``params_json`` to get amount_per_share (float)."""
    try:
        params: dict[str, object] = (
            json.loads(row_params) if isinstance(row_params, str) else row_params
        )
        val = params.get("amount_per_share", 0.0)
        return float(val)  # type: ignore[arg-type]
    except (ValueError, AttributeError, TypeError):
        return 0.0


def dividend_consistency_grade(
    corporate_actions: pd.DataFrame,
    asof: date,
    window_years: int = 10,
) -> str:
    """Grade dividend consistency per spec section 2 D7(d).

    Expects a DataFrame (optionally pre-filtered to one symbol) with columns:
    ``symbol``, ``ex_date``, ``kind``, ``params_json``.

    Grade rules (applied in order):
    - F: no cash dividend history in window
    - E: fewer than 5 years with dividends
    - D: 5-6 years, or 7-9 years with recent cut (last 5y)
    - C: 7-9 years without recent cut, or 10 consecutive with any cut
    - B: 10 consecutive, no cuts, CAGR < 8%
    - A: 10 consecutive, no cuts, CAGR >= 8%
    """
    if corporate_actions.empty:
        return "F"

    df = corporate_actions[corporate_actions["kind"] == "cash_dividend"].copy()
    if df.empty:
        return "F"

    df["ex_date"] = pd.to_datetime(df["ex_date"])
    window_start = pd.Timestamp(asof.year - window_years + 1, 1, 1)
    window_end = pd.Timestamp(asof)
    df = df[(df["ex_date"] >= window_start) & (df["ex_date"] <= window_end)]
    if df.empty:
        return "F"

    df["amount"] = df["params_json"].apply(_extract_amount)
    df["fiscal_year"] = df["ex_date"].dt.year
    annual = df.groupby("fiscal_year")["amount"].sum().sort_index()
    n_years = len(annual)

    if n_years < 3:
        return "F"
    if n_years <= 4:
        return "E"
    if n_years <= 6:
        return "D"

    # n_years >= 7
    has_recent_cut = bool((annual.iloc[-5:].diff().dropna() < 0).any())

    if n_years < 10:
        return "D" if has_recent_cut else "C"

    # n_years == 10: check consecutiveness
    expected_years = list(range(asof.year - 9, asof.year + 1))
    consecutive = list(annual.index) == expected_years

    has_any_cut = bool((annual.diff().dropna() < 0).any())

    if not consecutive:
        return "D" if has_recent_cut else "C"

    if has_any_cut:
        return "D" if has_recent_cut else "C"

    # Consecutive 10 years, no cuts: compute CAGR
    first_val = float(annual.iloc[0])
    last_val = float(annual.iloc[-1])
    if first_val <= 0:
        return "B"
    cagr = (last_val / first_val) ** (1.0 / 9.0) - 1.0
    return "A" if cagr >= 0.08 else "B"
