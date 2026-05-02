"""OptimizedWeightStrategy — WeightStrategy implementation backed by Optimizer.

Drives ``Optimizer.build()`` at each rebalance date within ``[start, end]``,
accumulating ``OptimizationResult`` objects in ``history`` and converting the
final set of weights to the ``Weights`` long-form DataFrame expected by the
backtest engine.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from ah_research.backtest.types import Weights
from ah_research.data.repository import DataRepository
from ah_research.portfolio.optimizer import OptimizationResult, Optimizer

if TYPE_CHECKING:
    pass


class OptimizedWeightStrategy:
    """WeightStrategy that calls ``Optimizer.build()`` at each rebalance date.

    Parameters
    ----------
    optimizer:
        A configured ``Optimizer`` instance.
    symbols:
        Universe of symbols to pass to ``optimizer.build()``.
    rebalance_freq:
        Pandas offset alias for rebalance frequency (default ``"ME"`` = month-end).
    name:
        Human-readable strategy name exposed by the WeightStrategy protocol.
    """

    def __init__(
        self,
        *,
        optimizer: Optimizer,
        symbols: list[str],
        rebalance_freq: str = "ME",
        name: str = "optimized",
    ) -> None:
        self.name = name
        self._optimizer = optimizer
        self._symbols = symbols
        self._rebalance_freq = rebalance_freq
        self._history: list[OptimizationResult] = []

    @property
    def history(self) -> list[OptimizationResult]:
        """Ordered list of ``OptimizationResult`` objects from the last ``generate`` call."""
        return list(self._history)

    def generate(self, repo: DataRepository, start: date, end: date) -> Weights:
        """Generate target weights by running the optimizer at each rebalance date.

        The rebalance dates are the ``self._rebalance_freq`` periods within
        ``[start, end]``.  If that produces no dates (e.g., a very short window),
        a single optimization is run at ``end``.

        ``prev_weights`` is ``None`` on the first call and set to the previous
        ``OptimizationResult.weights`` on all subsequent calls.

        Returns
        -------
        Weights
            Long-form ``Weights`` object with columns ``date``, ``symbol``,
            ``weight`` — one row per (rebalance_date, symbol).
        """
        self._history = []

        reb_dates = pd.date_range(start=start, end=end, freq=self._rebalance_freq)
        if len(reb_dates) == 0:
            reb_dates = pd.DatetimeIndex([pd.Timestamp(end)])

        prev_weights: pd.Series | None = None
        rows: list[dict[str, object]] = []

        for reb_date in reb_dates:
            result = self._optimizer.build(
                self._symbols,
                pd.Timestamp(reb_date),
                repo,
                prev_weights=prev_weights,
            )
            self._history.append(result)
            prev_weights = result.weights

            for symbol, weight in result.weights.items():
                rows.append({"date": pd.Timestamp(reb_date), "symbol": symbol, "weight": weight})

        df = pd.DataFrame(rows, columns=["date", "symbol", "weight"])
        return Weights.from_dataframe(df)
