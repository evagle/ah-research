"""Value factor strategy: composite rank of 1/PE, 1/PB, and dividend yield."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from ah_research.backtest.types import Signals, Weights
from ah_research.data.repository import DataRepository
from ah_research.portfolio.construction import signal_to_weights


@dataclass(frozen=True)
class ValueFactorStrategy:
    """Composite value-factor strategy on the CSI 300 universe.

    Signal construction (per month-end rebalance date ``d``):

    1. Universe: PIT-correct CSI 300 members at ``d``.
    2. Fundamentals: bitemporal PIT-filtered to ``asof=d``.
    3. Composite signal = equal-weighted mean of:
       - rank(1 / PE)
       - rank(1 / PB)
       - rank(dividend_yield)

    Rows with any NaN in the three inputs are dropped before ranking.

    Weight construction delegates to ``portfolio.construction.signal_to_weights``
    with optional sector neutralisation (requires ``repo.get_sector``).

    Recommended engine config: ``rebalance="M"`` (monthly).
    """

    quantile: float = 0.2
    max_weight: float = 0.05
    sector_neutral: bool = True
    name: str = field(default="value_factor")

    def generate(self, repo: DataRepository, start: date, end: date) -> Signals:
        """Return month-end composite value signals for CSI 300 members."""
        universe = repo.get_universe_over_time("CSI300", start, end, freq="ME")
        if universe.empty:
            return _empty_signals()

        rows: list[pd.DataFrame] = []
        for ts in universe["date"].unique():
            grp = universe[universe["date"] == ts]
            symbols: list[str] = grp["symbol"].tolist()
            d_date = ts.date()  # ts is already a pd.Timestamp
            funds = repo.get_fundamentals(symbols, start=d_date, end=d_date, asof=d_date)
            if funds.empty:
                continue
            # Keep the most recent row per symbol (highest known_as_of)
            latest = funds.sort_values("known_as_of").groupby("symbol", as_index=False).last()
            latest = latest.copy()
            # Guard against zero / negative multiples before inversion
            latest["inv_pe"] = latest["pe"].where(latest["pe"] > 0).rdiv(1.0)
            latest["inv_pb"] = latest["pb"].where(latest["pb"] > 0).rdiv(1.0)
            latest["div_yield_col"] = latest["dividend_yield"]
            # Drop rows missing any of the three inputs
            latest = latest.dropna(subset=["inv_pe", "inv_pb", "div_yield_col"])
            if latest.empty:
                continue
            # Rank each factor independently then average
            latest["r_inv_pe"] = latest["inv_pe"].rank()
            latest["r_inv_pb"] = latest["inv_pb"].rank()
            latest["r_div_yield"] = latest["div_yield_col"].rank()
            latest["signal"] = latest[["r_inv_pe", "r_inv_pb", "r_div_yield"]].mean(axis=1)
            latest["date"] = ts
            rows.append(latest[["date", "symbol", "signal"]].copy())

        if not rows:
            return _empty_signals()

        df = pd.concat(rows, ignore_index=True).dropna(subset=["signal"])
        return Signals.from_dataframe(df)

    def to_weights(self, signals: Signals, repo: DataRepository) -> Weights:
        """Convert signals to weights via top-quantile selection.

        When ``sector_neutral=True``, fetches live sector classifications from
        ``repo`` and equalises sector exposures before capping.
        """
        if signals.df.empty:
            return _empty_weights()

        sectors: pd.DataFrame | None = None
        if self.sector_neutral:
            all_symbols = signals.df["symbol"].unique().tolist()
            sectors = repo.get_sector(all_symbols)

        df = signal_to_weights(
            signals.df,
            method="top_quantile",
            quantile=self.quantile,
            max_weight=self.max_weight,
            sector_neutral=self.sector_neutral,
            sectors=sectors,
        )
        return Weights.from_dataframe(df)


# ── helpers ───────────────────────────────────────────────────────────────────


def _empty_signals() -> Signals:
    return Signals.from_dataframe(
        pd.DataFrame(
            {
                "date": pd.Series([], dtype="datetime64[ns]"),
                "symbol": pd.Series([], dtype=str),
                "signal": pd.Series([], dtype=float),
            }
        )
    )


def _empty_weights() -> Weights:
    return Weights.from_dataframe(
        pd.DataFrame(
            {
                "date": pd.Series([], dtype="datetime64[ns]"),
                "symbol": pd.Series([], dtype=str),
                "weight": pd.Series([], dtype=float),
            }
        )
    )
