"""Tests for BacktestConfig, Order, Trade, Position, BacktestResult dataclasses."""

from datetime import date
from decimal import Decimal

import pytest

from ah_research.backtest.types import (
    BacktestConfig,
    Order,
    Position,
    Trade,
    hash_config,
)
from ah_research.model.types import Symbol, parse_symbol


def _symbol(code: str = "600000.SH") -> Symbol:
    return parse_symbol(code)


def test_config_is_frozen() -> None:
    cfg = BacktestConfig(
        start=date(2020, 1, 1),
        end=date(2020, 12, 31),
        initial_cash=Decimal("100000"),
    )
    with pytest.raises(Exception):  # FrozenInstanceError  # noqa: B017
        cfg.start = date(2019, 1, 1)  # type: ignore[misc]


def test_config_hash_is_stable() -> None:
    cfg1 = BacktestConfig(
        start=date(2020, 1, 1),
        end=date(2020, 12, 31),
        initial_cash=Decimal("100000"),
    )
    cfg2 = BacktestConfig(
        start=date(2020, 1, 1),
        end=date(2020, 12, 31),
        initial_cash=Decimal("100000"),
    )
    assert hash_config(cfg1) == hash_config(cfg2)


def test_config_hash_changes_with_input() -> None:
    cfg1 = BacktestConfig(
        start=date(2020, 1, 1),
        end=date(2020, 12, 31),
        initial_cash=Decimal("100000"),
    )
    cfg2 = BacktestConfig(
        start=date(2020, 1, 1),
        end=date(2020, 12, 31),
        initial_cash=Decimal("200000"),  # different
    )
    assert hash_config(cfg1) != hash_config(cfg2)


def test_order_and_trade_dataclasses_instantiate() -> None:
    o = Order(ready_date=date(2024, 1, 2), symbol=_symbol(), side="buy", shares=100)
    t = Trade(
        exec_date=date(2024, 1, 3),
        symbol=_symbol(),
        side="buy",
        shares=100,
        fill_price=Decimal("10.50"),
        notional=Decimal("1050.00"),
        cost_total=Decimal("1.05"),
        cost_breakdown={"commission": Decimal("1.05")},
    )
    assert o.shares == 100
    assert t.cost_breakdown["commission"] == Decimal("1.05")


def test_position_has_lock() -> None:
    p = Position(
        symbol=_symbol(),
        shares=100,
        avg_cost=Decimal("10.00"),
        locked_until=date(2024, 1, 3),
    )
    assert p.locked_until == date(2024, 1, 3)
