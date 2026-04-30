"""Trailing N-year percentile bands for P/E, P/B, P/S."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from ah_research.data.repository import DataRepository

ValuationMetric = Literal["pe", "pb", "ps"]


@dataclass(frozen=True)
class ValuationBand:
    """Percentile band summary for a single valuation metric."""

    metric: ValuationMetric
    bands: dict[str, float]
    current: float
    current_percentile: float
    window_years: int


def compute_valuation_bands(
    symbol: str,
    repo: DataRepository,
    asof: date,
    metric: ValuationMetric = "pe",
    window_years: int = 10,
) -> ValuationBand:
    """Compute trailing ``window_years``-year percentile bands for ``metric``.

    Returns a :class:`ValuationBand` with p10/p25/p50/p75/p90 cut-points,
    the most-recent value, and the current percentile rank (0-100).
    ``window_years`` on the returned object reflects actual data coverage when
    less than ``window_years`` of history is available.
    """
    start = date(asof.year - window_years, asof.month, asof.day)
    fundamentals = repo.get_fundamentals([symbol], start=start, end=asof, asof=asof)

    _empty_bands: dict[str, float] = {
        "p10": 0.0,
        "p25": 0.0,
        "p50": 0.0,
        "p75": 0.0,
        "p90": 0.0,
    }

    if fundamentals.empty or metric not in fundamentals.columns:
        return ValuationBand(
            metric=metric,
            bands=_empty_bands,
            current=0.0,
            current_percentile=0.0,
            window_years=0,
        )

    series = fundamentals[metric].dropna().astype(float)
    if series.empty:
        return ValuationBand(
            metric=metric,
            bands=_empty_bands,
            current=0.0,
            current_percentile=0.0,
            window_years=0,
        )

    bands: dict[str, float] = {
        f"p{int(q * 100)}": float(series.quantile(q)) for q in (0.10, 0.25, 0.50, 0.75, 0.90)
    }
    current = float(series.iloc[-1])
    current_percentile = float((series <= current).mean() * 100)

    # Compute actual year span from report_date column when available
    if "report_date" in fundamentals.columns:
        dates = pd.to_datetime(fundamentals["report_date"].dropna())
        if len(dates) >= 2:
            span_days = int((dates.max() - dates.min()).days)
            actual_years = min(window_years, max(1, round(span_days / 365.25)))
        else:
            actual_years = 1
    else:
        actual_years = window_years

    return ValuationBand(
        metric=metric,
        bands=bands,
        current=current,
        current_percentile=current_percentile,
        window_years=actual_years,
    )
