"""Dividend yield strategy with 3-year continuity filter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from ah_research.backtest.types import Signals, Weights
from ah_research.data.repository import DataRepository
from ah_research.portfolio.construction import signal_to_weights

# Minimum number of cash-dividend corporate-action rows required across the
# prior 3 years for a symbol to pass the continuity filter.
_MIN_DIVIDEND_EVENTS = 3
_LOOKBACK_YEARS = 3


@dataclass(frozen=True)
class DividendYieldStrategy:
    """Dividend yield strategy on the CSI 300 universe.

    Signal: trailing 12-month dividend yield (``dividend_yield`` field from
    bitemporal fundamentals), filtered to firms with a demonstrated dividend
    history of at least 3 consecutive years.

    Continuity filter: a symbol qualifies only if ``repo.get_corporate_actions``
    returns >= 3 rows with ``kind="cash_dividend"`` in the 3 years ending at the
    rebalance date. Symbols failing this test receive no signal on that date.

    Recommended engine config: ``rebalance="Q"`` (quarterly). The strategy does
    not enforce the rebalance frequency itself — that is the engine's concern.
    """

    quantile: float = 0.3
    max_weight: float = 0.05
    sector_neutral: bool = False
    name: str = field(default="dividend_yield")

    def generate(self, repo: DataRepository, start: date, end: date) -> Signals:
        """Return quarter-end dividend yield signals for CSI 300 members."""
        universe = repo.get_universe_over_time("CSI300", start, end, freq="ME")
        if universe.empty:
            return _empty_signals()

        rows: list[pd.DataFrame] = []
        for ts in universe["date"].unique():
            grp = universe[universe["date"] == ts]
            symbols: list[str] = grp["symbol"].tolist()
            d_date = ts.date()  # ts is already a pd.Timestamp

            # Fundamentals PIT-filtered to d_date
            funds = repo.get_fundamentals(symbols, start=d_date, end=d_date, asof=d_date)
            if funds.empty:
                continue

            # Latest row per symbol
            latest = funds.sort_values("known_as_of").groupby("symbol", as_index=False).last()

            # Continuity filter: >= _MIN_DIVIDEND_EVENTS cash dividends in prior 3 years
            # Use 365.25 * _LOOKBACK_YEARS days to handle leap years / month-end edges.
            three_years_back = d_date - timedelta(days=int(365.25 * _LOOKBACK_YEARS))
            actions = repo.get_corporate_actions(symbols, three_years_back, d_date)
            dividend_actions = (
                actions[actions["kind"] == "cash_dividend"] if not actions.empty else pd.DataFrame()
            )
            if not dividend_actions.empty:
                qualifying = dividend_actions.groupby("symbol").size() >= _MIN_DIVIDEND_EVENTS
                qualifying_symbols: list[str] = qualifying[qualifying].index.tolist()
            else:
                qualifying_symbols = []

            if not qualifying_symbols:
                continue

            latest = latest[latest["symbol"].isin(qualifying_symbols)].copy()
            if latest.empty:
                continue

            latest["signal"] = latest["dividend_yield"]
            latest = latest.dropna(subset=["signal"])
            if latest.empty:
                continue

            latest["date"] = ts
            rows.append(latest[["date", "symbol", "signal"]].copy())

        if not rows:
            return _empty_signals()

        df = pd.concat(rows, ignore_index=True).dropna(subset=["signal"])
        return Signals.from_dataframe(df)

    def to_weights(self, signals: Signals, repo: DataRepository) -> Weights:
        """Convert signals to weights via top-quantile selection."""
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
