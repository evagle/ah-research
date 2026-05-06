"""Unit tests for ``backtest.order_executor.OrderExecutor`` (carved out in C1-02).

Pins the contract of the pre-execution stage in isolation: the 6-clause
validation tower, dividend-sentinel resolution, fill-price selection,
slippage application, and cost computation. Complements the 3
end-to-end characterization fixtures with focused per-branch coverage.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from ah_research.backtest.costs import DEFAULT_COSTS_2024, CostModelBundle
from ah_research.backtest.order_executor import (
    OrderExecutor,
    OrderRejection,
    PricedFill,
)
from ah_research.backtest.types import BacktestConfig, Order, Position
from ah_research.model.types import parse_symbol

# ─── helpers ────────────────────────────────────────────────────────────────


def _config(**overrides: object) -> BacktestConfig:
    """Build a minimally-valid BacktestConfig; overrides selectively."""
    base = {
        "start": date(2024, 1, 1),
        "end": date(2024, 12, 31),
        "initial_cash": Decimal("1000000"),
        "fill_price": "next_open",
        "a_share_short_allowed": False,
    }
    base.update(overrides)  # type: ignore[arg-type]
    return BacktestConfig(**base)  # type: ignore[arg-type]


def _bar(
    *,
    open_: float = 10.0,
    close: float = 10.0,
    volume: float = 1_000_000.0,
    amount: float = 10_000_000.0,
    is_suspended: bool = False,
    hit_limit_up: bool = False,
    hit_limit_down: bool = False,
) -> pd.Series:
    return pd.Series(
        {
            "open": open_,
            "close": close,
            "volume": volume,
            "amount": amount,
            "is_suspended": is_suspended,
            "hit_limit_up": hit_limit_up,
            "hit_limit_down": hit_limit_down,
        }
    )


def _executor() -> OrderExecutor:
    return OrderExecutor(cost_model=DEFAULT_COSTS_2024)


_SH = parse_symbol("600000.SH")
_HK = parse_symbol("0700.HK")
_TODAY = date(2024, 6, 3)


# ─── 6-clause validation tower ──────────────────────────────────────────────


def test_no_price_bar_rejects_no_retry() -> None:
    rej = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=100),
        bar=None,
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(rej, OrderRejection)
    assert rej.reason == "no_price_bar"
    assert rej.retry is False


def test_suspended_rejects_with_retry() -> None:
    rej = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=100),
        bar=_bar(is_suspended=True),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(rej, OrderRejection)
    assert rej.reason == "suspended"
    assert rej.retry is True


def test_limit_up_blocks_buys() -> None:
    rej = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=100),
        bar=_bar(hit_limit_up=True),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(rej, OrderRejection)
    assert rej.reason == "limit_up"
    assert rej.retry is True


def test_limit_up_does_not_block_sells() -> None:
    """Limit-up only blocks the buy side."""
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="sell", shares=100),
        bar=_bar(hit_limit_up=True),
        position=Position(symbol=_SH, shares=100, avg_cost=Decimal("9")),
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)


def test_limit_down_blocks_sells() -> None:
    rej = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="sell", shares=100),
        bar=_bar(hit_limit_down=True),
        position=Position(symbol=_SH, shares=100, avg_cost=Decimal("9")),
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(rej, OrderRejection)
    assert rej.reason == "limit_down"
    assert rej.retry is True


def test_limit_down_blocks_shorts() -> None:
    rej = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_HK, side="short", shares=100),
        bar=_bar(hit_limit_down=True),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(rej, OrderRejection)
    assert rej.reason == "limit_down"


def test_t_n_lock_blocks_sell_no_retry() -> None:
    """T+N lock blocks sells and is *not* a retryable transient state."""
    locked = Position(
        symbol=_SH,
        shares=100,
        avg_cost=Decimal("9"),
        locked_until=date(2024, 6, 5),  # > _TODAY
    )
    rej = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="sell", shares=100),
        bar=_bar(),
        position=locked,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(rej, OrderRejection)
    assert rej.reason == "T+N lock"
    assert rej.retry is False


def test_t_n_lock_expired_allows_sell() -> None:
    """When ``locked_until <= d`` the sell goes through."""
    expired = Position(
        symbol=_SH,
        shares=100,
        avg_cost=Decimal("9"),
        locked_until=date(2024, 6, 2),  # <= _TODAY
    )
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="sell", shares=100),
        bar=_bar(),
        position=expired,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)


def test_a_share_short_disallowed_by_default() -> None:
    rej = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="short", shares=100),
        bar=_bar(),
        position=None,
        config=_config(a_share_short_allowed=False),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(rej, OrderRejection)
    assert rej.reason == "a_share_short_disallowed"
    assert rej.retry is False


def test_a_share_short_allowed_when_flag_set() -> None:
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="short", shares=100),
        bar=_bar(),
        position=None,
        config=_config(a_share_short_allowed=True),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)


def test_hk_short_not_subject_to_a_share_rule() -> None:
    """The A-share short ban applies only to SH/SZ symbols."""
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_HK, side="short", shares=100),
        bar=_bar(),
        position=None,
        config=_config(a_share_short_allowed=False),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)


# ─── fill-price selection ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("mode", "expected_base"),
    [
        ("next_open", 10.0),
        ("next_close", 12.0),
        # vwap = amount / volume
        ("next_vwap", 11.0),
    ],
)
def test_fill_price_mode_selects_correct_base(mode: str, expected_base: float) -> None:
    bar = _bar(open_=10.0, close=12.0, volume=1_000.0, amount=11_000.0)
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=100),
        bar=bar,
        position=None,
        config=_config(fill_price=mode),  # type: ignore[arg-type]
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)
    # Slippage is +5 bps for buys on SH (DEFAULT_COSTS_2024).
    expected = Decimal(str(expected_base * (1 + 5 / 1e4)))
    assert res.fill_price == expected


def test_vwap_falls_back_to_open_when_volume_zero() -> None:
    """Division by zero protection: vwap defaults to open_ when volume == 0."""
    bar = _bar(open_=10.0, close=12.0, volume=0.0, amount=0.0)
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=100),
        bar=bar,
        position=None,
        config=_config(fill_price="next_vwap"),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)
    assert res.fill_price == Decimal(str(10.0 * (1 + 5 / 1e4)))


# ─── slippage signing ──────────────────────────────────────────────────────


def test_slippage_positive_for_buys_negative_for_sells() -> None:
    """Buy slippage costs you (price up); sell slippage hurts (price down)."""
    bar = _bar(open_=10.0)
    buy = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=100),
        bar=bar,
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    sell = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="sell", shares=100),
        bar=bar,
        position=Position(symbol=_SH, shares=100, avg_cost=Decimal("9")),
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(buy, PricedFill)
    assert isinstance(sell, PricedFill)
    assert buy.fill_price > Decimal("10")
    assert sell.fill_price < Decimal("10")


def test_slippage_zero_when_no_cost_model_for_exchange() -> None:
    """Missing cost model => zero slippage (silent fallback)."""
    empty_bundle = CostModelBundle(models={})
    executor = OrderExecutor(cost_model=empty_bundle)
    res = executor.attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=100),
        bar=_bar(open_=10.0),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)
    assert res.fill_price == Decimal("10")
    # And cost is zero
    assert res.cost_total == Decimal("0")


# ─── notional & cost ────────────────────────────────────────────────────────


def test_notional_matches_fill_price_times_shares() -> None:
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=300),
        bar=_bar(open_=20.0),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)
    assert res.notional_local == res.fill_price * Decimal("300")


def test_cost_total_equals_sum_of_breakdown() -> None:
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=300),
        bar=_bar(open_=20.0),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)
    assert res.cost_total == sum(res.cost_breakdown.values(), Decimal("0"))


def test_a_share_commission_minimum_floor() -> None:
    """Tiny notional on SH still incurs the 5 CNY commission floor."""
    # 100 shares * 1.0 = 100 CNY notional; commission_bps=2.5 => 0.025 CNY
    # but commission_min_local=5 CNY kicks in.
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=100),
        bar=_bar(open_=1.0),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)
    assert res.cost_breakdown["commission"] == Decimal("5")


# ─── dividend-reinvestment sentinel ─────────────────────────────────────────


def test_dividend_sentinel_resolves_to_lot_rounded_shares() -> None:
    """Order(shares=-1) consumes the earmark and produces real shares."""
    earmarks = {_SH: Decimal("2500")}  # enough to buy 200 shares at base 10
    bar = _bar(open_=10.0)
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=-1),
        bar=bar,
        position=None,
        config=_config(),
        dividend_earmarks=earmarks,
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)
    # 2500 / 10 = 250 shares; lot_size=100 => floor to 200
    assert res.shares == 200
    # Earmark consumed (popped) regardless of resolved share count
    assert _SH not in earmarks


def test_dividend_sentinel_skip_when_no_earmark() -> None:
    """No earmark => silent no-op (returns None, distinct from rejection)."""
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=-1),
        bar=_bar(open_=10.0),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert res is None


def test_dividend_sentinel_skip_when_below_one_lot() -> None:
    """Earmark < one lot's worth: no order placed."""
    earmarks = {_SH: Decimal("500")}  # only buys 50 shares at 10, < 100 lot
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=-1),
        bar=_bar(open_=10.0),
        position=None,
        config=_config(),
        dividend_earmarks=earmarks,
        d=_TODAY,
    )
    assert res is None


def test_dividend_sentinel_skip_when_zero_base_price() -> None:
    """Zero base price defends against div-by-zero; silent skip."""
    earmarks = {_SH: Decimal("1000")}
    res = _executor().attempt_fill(
        order=Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=-1),
        bar=_bar(open_=0.0, volume=0.0, amount=0.0),
        position=None,
        config=_config(),
        dividend_earmarks=earmarks,
        d=_TODAY,
    )
    assert res is None


# ─── happy path snapshot ───────────────────────────────────────────────────


def test_priced_fill_carries_through_order_unmodified() -> None:
    """The PricedFill exposes the original order verbatim."""
    order = Order(ready_date=_TODAY, symbol=_SH, side="buy", shares=200)
    res = _executor().attempt_fill(
        order=order,
        bar=_bar(open_=10.0),
        position=None,
        config=_config(),
        dividend_earmarks={},
        d=_TODAY,
    )
    assert isinstance(res, PricedFill)
    assert res.order is order
    assert res.shares == 200
