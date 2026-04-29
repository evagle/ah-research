"""Data carriers for the backtest engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import TYPE_CHECKING

import pandas as pd

from ah_research.model.schemas import SignalsSchema, WeightsSchema
from ah_research.model.types import Currency, FillPrice, Freq, OrderSide, Settlement, Symbol

if TYPE_CHECKING:
    from ah_research.backtest.costs import CostModelBundle
    from ah_research.backtest.metrics import MetricsBundle

# BenchmarkSpec: a named index string ("CSI300_TR", "HSI_TR", "zero") or an
# explicit pd.Series of cumulative returns.
BenchmarkSpec = "str | pd.Series"  # runtime string avoids circular import


@dataclass(frozen=True)
class Signals:
    """Validated per-symbol signal frame."""

    df: pd.DataFrame

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> Signals:
        """Validate ``df`` against SignalsSchema and wrap it."""
        validated = SignalsSchema.validate(df)
        return cls(df=validated)


@dataclass(frozen=True)
class Weights:
    """Validated per-symbol target-weight frame."""

    df: pd.DataFrame

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> Weights:
        """Validate ``df`` against WeightsSchema and wrap it."""
        validated = WeightsSchema.validate(df)
        return cls(df=validated)


@dataclass(frozen=True)
class BacktestConfig:
    """Immutable configuration for a single backtest run."""

    start: date
    end: date
    initial_cash: Decimal
    base_currency: Currency = Currency.CNY
    rebalance: Freq = "M"
    fill_price: FillPrice = "next_open"
    settlement: Settlement = "auto"
    dividend_policy: str = "reinvest"  # DividendPolicy
    benchmark: str = "CSI300_TR"  # BenchmarkSpec (str form only at config time)
    cost_model: CostModelBundle | None = None
    allow_leverage: bool = False
    allow_short: bool = True
    a_share_short_allowed: bool = False
    random_seed: int = 42


@dataclass(frozen=True)
class Order:
    """An unexecuted order queued for the next trading day."""

    ready_date: date
    symbol: Symbol
    side: OrderSide
    shares: int


@dataclass(frozen=True)
class Trade:
    """A filled order with cost breakdown."""

    exec_date: date
    symbol: Symbol
    side: OrderSide
    shares: int
    fill_price: Decimal
    notional: Decimal
    cost_total: Decimal
    cost_breakdown: dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    """Current holding in a single security."""

    symbol: Symbol
    shares: int
    avg_cost: Decimal
    locked_until: date | None = None


@dataclass(frozen=True)
class BacktestResult:
    """Output of a completed backtest run."""

    config: BacktestConfig
    config_hash: str
    code_version: str
    equity_curve: pd.Series
    benchmark_curve: pd.Series
    returns: pd.Series
    positions_history: pd.DataFrame
    trades: pd.DataFrame
    rejected_orders: pd.DataFrame
    cash_history: pd.DataFrame
    metrics: MetricsBundle


def hash_config(cfg: BacktestConfig) -> str:
    """Return SHA-256 hex digest of canonical JSON representation of ``cfg``."""
    payload = {
        "start": cfg.start.isoformat(),
        "end": cfg.end.isoformat(),
        "initial_cash": str(cfg.initial_cash),
        "base_currency": str(cfg.base_currency),
        "rebalance": cfg.rebalance,
        "fill_price": cfg.fill_price,
        "settlement": cfg.settlement,
        "dividend_policy": cfg.dividend_policy,
        "benchmark": cfg.benchmark if isinstance(cfg.benchmark, str) else "<Series>",
        "allow_leverage": cfg.allow_leverage,
        "allow_short": cfg.allow_short,
        "a_share_short_allowed": cfg.a_share_short_allowed,
        "random_seed": cfg.random_seed,
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
