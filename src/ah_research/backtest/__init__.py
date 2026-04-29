"""Backtest engine, costs, metrics, and verification."""

from ah_research.backtest import verify
from ah_research.backtest.costs import DEFAULT_COSTS_2024, CostModel, CostModelBundle
from ah_research.backtest.engine import run_backtest
from ah_research.backtest.metrics import MetricsBundle, compute_metrics
from ah_research.backtest.types import (
    BacktestConfig,
    BacktestResult,
    Order,
    Position,
    Signals,
    Trade,
    Weights,
)

__all__ = [
    "DEFAULT_COSTS_2024",
    "BacktestConfig",
    "BacktestResult",
    "CostModel",
    "CostModelBundle",
    "MetricsBundle",
    "Order",
    "Position",
    "Signals",
    "Trade",
    "Weights",
    "compute_metrics",
    "run_backtest",
    "verify",
]
