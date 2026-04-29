"""Tests for suspension (halt) rejection with retry.

- Any order on a suspended day is rejected and re-queued for next day.
- Orders resume filling after the halt ends.
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


def test_order_rejected_on_suspended_day() -> None:
    """An order on a suspended (halt) day is rejected with reason='suspended'."""
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
    day1 = trading_days[1]  # buy would fill here — suspend it

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        halt_days={"600000.SH": [day1]},
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
    suspended_rejects = result.rejected_orders[result.rejected_orders["reason"] == "suspended"]
    assert len(suspended_rejects) >= 1, (
        f"Expected at least one 'suspended' rejection; reasons: "
        f"{result.rejected_orders['reason'].unique()}"
    )


def test_order_fills_after_halt_ends() -> None:
    """After suspension ends, re-queued order fills successfully."""
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
    day1 = trading_days[1]  # suspended — buy rejected + re-queued
    # day2 is clear — buy should fill

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        halt_days={"600000.SH": [day1]},
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

    # After halt ends, the buy should fill
    assert not result.trades.empty, "Expected buy to fill after halt ends"
    assert "buy" in result.trades["side"].tolist()


def test_suspension_requeue_multi_day() -> None:
    """Multi-day suspension: order re-queued each day until halt ends."""
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
    day1 = trading_days[1]
    day2 = trading_days[2]
    day3 = trading_days[3]  # suspended on day1-3, fill on day4

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        halt_days={"600000.SH": [day1, day2, day3]},
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

    # 3 suspension rejections
    suspended_rejects = result.rejected_orders[result.rejected_orders["reason"] == "suspended"]
    assert len(suspended_rejects) >= 3, (
        f"Expected 3 suspension rejections; got {len(suspended_rejects)}"
    )
    # Trade eventually fills
    assert not result.trades.empty, "Expected buy to fill after multi-day halt"
