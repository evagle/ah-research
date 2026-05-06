"""Daily-loop backtest engine for A-share and HK markets.

Public entry point ``run_backtest(strategy, repo, config) -> BacktestResult``.
The implementation lives in ``backtest_loop.BacktestLoop``; this module is
the public façade.

The engine follows the spec §5 pseudocode:
  1. Corporate actions applied at open (before order execution).
  2. Pending orders executed at the configured fill price.
  3. On rebalance dates, new target orders are queued for next trading day.
  4. End-of-day MTM: equity = cash_in_base + sum(position.mtm_base).
  5. T+N lock expiry.

Concerns are split across collaborators (carved out across the C1 stack):

* ``OrderExecutor`` -- validation + dividend-sentinel resolution + fill
  price + slippage + cost (C1-02).
* ``CashLedger`` -- cash-sufficiency back-solve + position/cash mutation
  (C1-03).
* ``RebalanceScheduler`` -- target-weights -> orders translation (C1-04).
* ``CorporateActionHandler`` -- dividends/splits/etc. at the open (C1-05).
* ``MTMAccumulator`` -- EOD NAV recording, lock expiry, final positions
  snapshot (C1-05).
* ``BacktestLoop`` -- orchestrates the four phases (setup, init state,
  daily loop, finalize). This PR (C1-06).

``resolve_benchmark`` is re-exported here for backward compatibility
with existing callers; the implementation is in ``backtest_loop``.
"""

from __future__ import annotations

from typing import Any

from ah_research.backtest.backtest_loop import BacktestLoop, resolve_benchmark
from ah_research.backtest.types import BacktestConfig, BacktestResult

__all__ = ["resolve_benchmark", "run_backtest"]


def run_backtest(
    strategy: Any,
    repo: Any,
    config: BacktestConfig,
) -> BacktestResult:
    """Run a daily-loop event-driven backtest.

    Parameters
    ----------
    strategy:
        An object implementing either ``WeightStrategy`` or ``SignalStrategy``
        protocol.
    repo:
        A ``DataRepository``-compatible object.
    config:
        Immutable backtest configuration.

    Returns
    -------
    BacktestResult
        Fully populated result with equity curve, trades, rejected orders,
        and metrics.
    """
    return BacktestLoop(strategy=strategy, repo=repo, config=config).run()
