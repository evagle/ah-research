"""Tests for CostModel, CostModelBundle, and DEFAULT_COSTS_2024."""

from decimal import Decimal

from ah_research.backtest.costs import (
    DEFAULT_COSTS_2024,
)
from ah_research.model.types import Exchange


def test_default_sh_buy_has_no_stamp() -> None:
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.SH)
    breakdown = cm.compute(side="buy", notional_local=Decimal("10000"))
    assert breakdown["stamp"] == Decimal("0")


def test_default_sh_sell_has_stamp() -> None:
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.SH)
    breakdown = cm.compute(side="sell", notional_local=Decimal("10000"))
    # stamp_sell_bps=5 -> 10000 * 5 / 10000 = 5
    assert breakdown["stamp"] == Decimal("5")


def test_default_hk_buy_and_sell_both_have_stamp() -> None:
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.HK)
    for side in ("buy", "sell"):
        b = cm.compute(side=side, notional_local=Decimal("10000"))  # type: ignore[arg-type]
        assert b["stamp"] > Decimal("0")


def test_commission_min_clamp() -> None:
    # A tiny trade should clamp to commission_min, not compute as bps
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.SH)
    b = cm.compute(side="buy", notional_local=Decimal("100"))
    # bps commission on 100 @ 2.5bp = 0.025, but min is 5
    assert b["commission"] == Decimal("5")


def test_cost_total_is_sum_of_breakdown() -> None:
    cm = DEFAULT_COSTS_2024.for_exchange(Exchange.HK)
    b = cm.compute(side="sell", notional_local=Decimal("10000"))
    assert sum(b.values()) == b["commission"] + b["stamp"] + b["transfer"] + b["exchange_fee"]
