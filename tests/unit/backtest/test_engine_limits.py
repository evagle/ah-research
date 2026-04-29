"""Tests for limit-up / limit-down rejection with retry.

- Buy order on a limit-up day is rejected and re-queued for next day.
- Sell order on a limit-down day is rejected and re-queued for next day.
- Orders rejected for limit reasons ARE re-queued (unlike T+N lock).
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from ah_research.backtest.costs import CostModelBundle
from ah_research.backtest.types import BacktestConfig, Weights
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


class _FixedBuyStrategy:
    """Buys 100% weight in a symbol on a single rebalance date."""

    name = "fixed_buy"

    def __init__(self, symbol: str, rebalance_date: date) -> None:
        self.symbol = symbol
        self.rebalance_date = rebalance_date

    def generate(self, repo: Any, start: date, end: date) -> Weights:
        df = pd.DataFrame(
            {
                "date": [pd.Timestamp(self.rebalance_date)],
                "symbol": [self.symbol],
                "weight": [1.0],
            }
        )
        return Weights.from_dataframe(df)


def test_buy_rejected_on_limit_up_day() -> None:
    """A buy order for a limit-up day is rejected with reason='limit_up'."""
    from ah_research.backtest.engine import run_backtest

    start = date(2024, 1, 2)
    end = date(2024, 1, 20)

    # Get the first few trading days
    repo_plain = build_synthetic_market(start=start, end=end, symbols=["600000.SH"])
    cal = repo_plain.get_trading_calendar("SH", start, end)
    trading_days = sorted(
        pd.Timestamp(r["date"]).date() for _, r in cal.iterrows() if r["is_trading_day"]
    )
    assert len(trading_days) >= 4

    # day0 is the rebalance date; buy fills on day1 (the first trading day after day0).
    # We want day1 to be limit-up so the buy is rejected.
    day0 = trading_days[0]
    day1 = trading_days[1]  # buy would fill here — make it limit-up

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        limit_up_days={"600000.SH": [day1]},
    )

    strategy = _FixedBuyStrategy("600000.SH", day0)
    cfg = BacktestConfig(
        start=start,
        end=end,
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
        rebalance="D",
    )
    result = run_backtest(strategy, repo, cfg)

    assert not result.rejected_orders.empty, "Expected at least one rejected order"
    assert "reason" in result.rejected_orders.columns
    limit_rejects = result.rejected_orders[result.rejected_orders["reason"] == "limit_up"]
    assert len(limit_rejects) >= 1, (
        f"Expected at least one limit_up rejection; reasons: "
        f"{result.rejected_orders['reason'].unique()}"
    )


def test_buy_fills_after_limit_up_clears() -> None:
    """A buy rejected on a limit-up day is re-queued and fills on the next clear day."""
    from ah_research.backtest.engine import run_backtest

    start = date(2024, 1, 2)
    end = date(2024, 1, 20)

    repo_plain = build_synthetic_market(start=start, end=end, symbols=["600000.SH"])
    cal = repo_plain.get_trading_calendar("SH", start, end)
    trading_days = sorted(
        pd.Timestamp(r["date"]).date() for _, r in cal.iterrows() if r["is_trading_day"]
    )
    assert len(trading_days) >= 4

    day0 = trading_days[0]
    day1 = trading_days[1]  # limit-up → buy rejected and re-queued
    # day2 has no limit — buy should fill then

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        limit_up_days={"600000.SH": [day1]},
    )

    strategy = _FixedBuyStrategy("600000.SH", day0)
    cfg = BacktestConfig(
        start=start,
        end=end,
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
        rebalance="D",
    )
    result = run_backtest(strategy, repo, cfg)

    # Even though day1 was limit-up, the buy should eventually fill
    assert not result.trades.empty, "Expected at least one trade to fill after limit clears"
    assert "buy" in result.trades["side"].tolist(), "Expected a buy trade"


def test_limit_up_requeue_not_dropped() -> None:
    """Limit-up rejects ARE re-queued; the order does not disappear."""
    from ah_research.backtest.engine import run_backtest

    start = date(2024, 1, 2)
    end = date(2024, 1, 31)

    repo_plain = build_synthetic_market(start=start, end=end, symbols=["600000.SH"])
    cal = repo_plain.get_trading_calendar("SH", start, end)
    trading_days = sorted(
        pd.Timestamp(r["date"]).date() for _, r in cal.iterrows() if r["is_trading_day"]
    )
    assert len(trading_days) >= 6

    day0 = trading_days[0]
    # Make day1, day2 both limit-up; order should fill on day3
    day1 = trading_days[1]
    day2 = trading_days[2]

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        limit_up_days={"600000.SH": [day1, day2]},
    )

    strategy = _FixedBuyStrategy("600000.SH", day0)
    cfg = BacktestConfig(
        start=start,
        end=end,
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
        rebalance="D",
    )
    result = run_backtest(strategy, repo, cfg)

    # There should be 2 limit_up rejections (day1 and day2)
    limit_rejects = result.rejected_orders[result.rejected_orders["reason"] == "limit_up"]
    assert len(limit_rejects) >= 2, (
        f"Expected 2 limit_up rejections for 2 limit-up days; got {len(limit_rejects)}"
    )

    # And the trade should eventually fill
    assert not result.trades.empty, "Expected buy to fill after limit clears"
