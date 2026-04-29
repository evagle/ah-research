"""Verify all documented public names are importable from the package root."""

from __future__ import annotations


def test_backtest_public_exports() -> None:
    from ah_research.backtest import (  # noqa: F401
        DEFAULT_COSTS_2024,
        BacktestConfig,
        BacktestResult,
        CostModel,
        CostModelBundle,
        MetricsBundle,
        Order,
        Position,
        Signals,
        Trade,
        Weights,
        compute_metrics,
        run_backtest,
        verify,
    )

    assert callable(run_backtest)
    assert callable(compute_metrics)
    assert verify is not None


def test_portfolio_public_exports() -> None:
    from ah_research.portfolio import (
        cap_at,
        sector_neutralize,
        signal_to_weights,
        top_quantile_weights,
    )

    assert callable(top_quantile_weights)
    assert callable(cap_at)
    assert callable(sector_neutralize)
    assert callable(signal_to_weights)


def test_strategies_public_exports() -> None:
    from ah_research.strategies import (  # noqa: F401
        AHPremiumMeanReversionStrategy,
        DividendYieldStrategy,
        SignalStrategy,
        ValueFactorStrategy,
        WeightStrategy,
    )

    assert AHPremiumMeanReversionStrategy is not None
    assert DividendYieldStrategy is not None
    assert ValueFactorStrategy is not None
