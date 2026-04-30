"""Walk-forward test: OptimizedWeightStrategy running inside a 1-year backtest."""

from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from ah_research.portfolio.constructor import Constraint
from ah_research.portfolio.optimizer import Optimizer
from ah_research.portfolio.optimizer.estimators.covariance import LedoitWolfCovariance
from ah_research.portfolio.optimizer.estimators.returns import HistoricalMeanReturns
from ah_research.strategies.optimized import OptimizedWeightStrategy


def _synthetic_prices(symbols: list[str], n_days: int = 800) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2023-06-01", periods=n_days)
    rows = []
    for sym in symbols:
        r = rng.normal(0, 0.012, size=n_days)
        prices = 100 * np.exp(np.cumsum(r))
        for d, p, ret in zip(dates, prices, r, strict=True):
            rows.append({"ds": d, "symbol": sym, "close_hfq": p, "total_return": ret})
    return pd.DataFrame(rows)


@pytest.mark.slow
def test_walkforward_1year_monthly_rebalance():
    symbols = [
        "600519.SH",
        "000858.SZ",
        "601318.SH",
        "000333.SZ",
        "600036.SH",
        "601166.SH",
        "000651.SZ",
        "600276.SH",
    ]
    prices = _synthetic_prices(symbols)
    repo = MagicMock()
    repo.get_prices.return_value = prices

    opt = Optimizer(
        objective="mean_variance",
        cov_estimator=LedoitWolfCovariance(),
        returns_estimator=HistoricalMeanReturns(lookback_days=252),
        constraints=[
            Constraint.max_weight(0.25),
            Constraint.max_turnover(0.30),
        ],
        long_only=True,
        lookback_days=252,
    )
    strat = OptimizedWeightStrategy(
        optimizer=opt,
        symbols=symbols,
        rebalance_freq="ME",
    )
    strat.generate(repo, date(2025, 1, 1), date(2025, 12, 31))

    # Should have ~12 monthly rebalances
    assert 10 <= len(strat.history) <= 13
    # All feasible
    assert all(r.solver_status in ("optimal", "optimal_inaccurate") for r in strat.history)
    # Turnover per rebalance bounded
    for i in range(1, len(strat.history)):
        prev = strat.history[i - 1].weights
        cur = strat.history[i].weights
        turnover = (cur - prev.reindex(cur.index).fillna(0)).abs().sum()
        assert turnover <= 0.30 + 5e-4, (
            f"Turnover={turnover} exceeds max_turnover=0.30 (solver residual)"
        )
