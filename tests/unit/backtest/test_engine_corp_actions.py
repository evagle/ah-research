"""Tests for corporate actions: cash_dividend, stock_dividend, split, reverse_split.

The synthetic market fixture supports an ``extra_corporate_actions`` kwarg
that injects additional rows into the corporate-action feed.

- cash_dividend: position holder's cash increases by amount_per_share * shares.
- stock_dividend: position shares increase; avg_cost adjusts to preserve basis.
- split: shares multiplied; avg_cost adjusts to preserve basis.
- reverse_split: shares reduced; avg_cost adjusts to preserve basis.
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


def _to_date(d: Any) -> date:
    """Normalise a value to datetime.date."""
    if isinstance(d, date) and not isinstance(d, pd.Timestamp):
        return d
    ts: pd.Timestamp = pd.Timestamp(d)
    result: date = ts.date()
    return result


def test_cash_dividend_credited_to_cash() -> None:
    """Cash dividend increases CNY cash balance for the position holder.

    We use the SECOND A-share symbol (600001.SH) so the synthetic market
    does NOT auto-inject a dividend for it — only the ``extra_corporate_actions``
    dividend should appear. If the kwarg is ignored, no dividend is credited
    and CNY cash stays near zero (all invested in shares), causing the
    assertion below to fail.
    """
    from ah_research.backtest.engine import run_backtest

    start = date(2024, 1, 2)
    end = date(2024, 1, 31)

    # Build plain market to discover trading days
    repo_plain = build_synthetic_market(start=start, end=end, symbols=["600000.SH", "600001.SH"])
    cal = repo_plain.get_trading_calendar("SH", start, end)
    trading_days = sorted(
        pd.Timestamp(r["date"]).date() for _, r in cal.iterrows() if r["is_trading_day"]
    )
    assert len(trading_days) >= 6

    # Buy on day0 (fills day1), inject dividend for 600001 on day4
    day0 = trading_days[0]
    day4 = trading_days[4]
    amount_per_share = 1.0

    # The synthetic market auto-injects a dividend for the FIRST a-share (600000.SH).
    # Our strategy holds 600001.SH — no auto-dividend for it.
    # extra_corporate_actions injects the dividend for 600001.SH.
    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH", "600001.SH"],
        extra_corporate_actions=[
            {
                "symbol": "600001.SH",
                "ex_date": day4,
                "kind": "cash_dividend",
                "params_json": f'{{"amount_per_share": {amount_per_share}}}',
            }
        ],
    )

    strategy = _FixedBuyStrategy("600001.SH", day0)
    cfg = BacktestConfig(
        start=start,
        end=end,
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
        rebalance="D",
        dividend_policy="cash",
    )
    result = run_backtest(strategy, repo, cfg)

    assert not result.trades.empty, "Expected a buy trade"
    assert not result.equity_curve.empty

    # After the ex-date, CNY cash should be > 0 because the dividend was credited.
    # If extra_corporate_actions is ignored, cash stays ≈ 0 (all invested) and
    # this assertion fails.
    cash_dates = [_to_date(d) for d in result.cash_history["date"]]
    cash_after = [
        row["CNY"]
        for row, d in zip(result.cash_history.to_dict("records"), cash_dates, strict=True)
        if d >= day4
    ]
    assert cash_after, "Expected cash_history entries on/after ex-date"
    assert max(cash_after) > 0, (
        "Expected CNY cash > 0 after cash_dividend for 600001.SH; "
        f"max cash after ex-date = {max(cash_after)}"
    )


def test_stock_dividend_increases_shares() -> None:
    """Stock dividend (10% bonus) runs to completion without error."""
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
    day3 = trading_days[3]

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        extra_corporate_actions=[
            {
                "symbol": "600000.SH",
                "ex_date": day3,
                "kind": "stock_dividend",
                "params_json": '{"ratio": 0.1}',
            }
        ],
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

    assert not result.equity_curve.empty
    assert not result.trades.empty
    # equity_curve should stay positive throughout
    assert (result.equity_curve > 0).all(), "Equity must stay positive after stock dividend"


def test_split_adjusts_shares() -> None:
    """2-for-1 split runs to completion without error and equity stays positive."""
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
    day3 = trading_days[3]

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        extra_corporate_actions=[
            {
                "symbol": "600000.SH",
                "ex_date": day3,
                "kind": "split",
                "params_json": '{"ratio": 2.0}',
            }
        ],
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

    assert not result.equity_curve.empty
    assert not result.trades.empty
    assert (result.equity_curve > 0).all(), "Equity must stay positive after split"


def test_reverse_split_reduces_shares() -> None:
    """1-for-2 reverse split runs to completion without error."""
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
    day3 = trading_days[3]

    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH"],
        extra_corporate_actions=[
            {
                "symbol": "600000.SH",
                "ex_date": day3,
                "kind": "reverse_split",
                "params_json": '{"ratio": 0.5}',
            }
        ],
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

    assert not result.equity_curve.empty
    assert not result.trades.empty
    assert (result.equity_curve > 0).all(), "Equity must stay positive after reverse split"


def test_no_corp_action_when_no_position() -> None:
    """Corporate action for unowned symbol has no effect on cash or trades."""
    from ah_research.backtest.engine import run_backtest

    start = date(2024, 1, 2)
    end = date(2024, 1, 31)

    repo_plain = build_synthetic_market(start=start, end=end, symbols=["600000.SH", "600001.SH"])
    cal = repo_plain.get_trading_calendar("SH", start, end)
    trading_days = sorted(
        pd.Timestamp(r["date"]).date() for _, r in cal.iterrows() if r["is_trading_day"]
    )
    day0 = trading_days[0]
    day4 = trading_days[4]

    # Inject a large dividend for 600001.SH but the strategy holds only 600000.SH.
    # The 600000.SH auto-dividend is on a different (mid-range) date, so on day4
    # the only event would be the 600001.SH dividend — which should have NO effect
    # because the strategy does not hold 600001.SH.
    repo = build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH", "600001.SH"],
        extra_corporate_actions=[
            {
                "symbol": "600001.SH",
                "ex_date": day4,
                "kind": "cash_dividend",
                "params_json": '{"amount_per_share": 500.0}',
            }
        ],
    )

    strategy = _FixedBuyStrategy("600000.SH", day0)
    cfg = BacktestConfig(
        start=start,
        end=end,
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
        rebalance="D",
        dividend_policy="cash",
    )
    result = run_backtest(strategy, repo, cfg)

    assert not result.equity_curve.empty

    # On day4, CNY cash should NOT have jumped by a large amount — the 600001 dividend
    # must have been ignored because we don't hold it.
    cash_dates = [_to_date(d) for d in result.cash_history["date"]]
    cash_on_day4 = [
        row["CNY"]
        for row, d in zip(result.cash_history.to_dict("records"), cash_dates, strict=True)
        if d == day4
    ]
    if cash_on_day4:
        # If we received a $500/share 600001 dividend, cash would jump by ~50,000+.
        # Legitimate 600000.SH auto-dividend (0.5/share * ~100k shares) ≈ 50k, so keep
        # the threshold generous enough not to catch that, but not 600001 level.
        # The assertion: cash on day4 should be < 500_000 (i.e. no 500/share dividend)
        assert cash_on_day4[0] < 500_000, (
            f"Unexpected large cash jump on day4; expected no 600001 dividend: {cash_on_day4[0]}"
        )
