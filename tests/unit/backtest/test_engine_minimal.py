"""Tests for the engine skeleton — buy next open, mark-to-market, no rules."""

from datetime import date
from decimal import Decimal

import pandas as pd

from ah_research.backtest.costs import CostModelBundle
from ah_research.backtest.types import BacktestConfig, Weights
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


class FixedLongStrategy:
    """Strategy that always holds 100% weight in one symbol, rebalancing monthly."""

    name = "fixed_long"

    def generate(self, repo: object, start: date, end: date) -> Weights:
        """Emit 100% weight in 600000.SH at each month-end."""
        eom = pd.date_range(start, end, freq="ME")
        df = pd.DataFrame(
            {
                "date": eom,
                "symbol": ["600000.SH"] * len(eom),
                "weight": [1.0] * len(eom),
            }
        )
        return Weights.from_dataframe(df)


def test_minimal_run_produces_equity_curve() -> None:
    """Engine runs and produces a valid daily equity curve with at least one trade."""
    from ah_research.backtest.engine import run_backtest

    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH"],
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),  # zero costs
    )
    result = run_backtest(FixedLongStrategy(), repo, cfg)

    assert len(result.equity_curve) > 30
    assert result.equity_curve.iloc[0] > 0
    # NAV must be finite and non-NaN
    assert result.equity_curve.notna().all()
    assert result.equity_curve.isna().sum() == 0
    # At least one trade executed
    assert len(result.trades) >= 1
    # The curve should not be negative
    assert all(v > 0 for v in result.equity_curve)


def test_minimal_run_has_config_hash() -> None:
    """BacktestResult carries a 64-char config_hash and non-empty code_version."""
    from ah_research.backtest.engine import run_backtest

    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH"],
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 1, 31),
        initial_cash=Decimal("100000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
    )
    result = run_backtest(FixedLongStrategy(), repo, cfg)

    assert len(result.config_hash) == 64
    assert result.code_version  # non-empty string


def test_benchmark_zero_is_constant_one() -> None:
    """When benchmark='zero', benchmark_curve is constant 1.0 on all equity_curve dates."""
    from ah_research.backtest.engine import run_backtest

    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        symbols=["600000.SH"],
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 1, 31),
        initial_cash=Decimal("100000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
    )
    result = run_backtest(FixedLongStrategy(), repo, cfg)

    assert (result.benchmark_curve == 1.0).all()
    assert list(result.benchmark_curve.index) == list(result.equity_curve.index)
