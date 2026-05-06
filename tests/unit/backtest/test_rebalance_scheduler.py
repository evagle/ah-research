"""Unit tests for ``backtest.rebalance_scheduler.RebalanceScheduler``
(carved out in C1-04).

Pins the contract of the *target-weights -> orders* translation step:
NAV computation as the sizing denominator, lot-rounded target shares,
side inference (buy/sell/short/cover), close-positions logic for
symbols dropped from the target set, and the price/fx degenerate
branches.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import pandas as pd

from ah_research.backtest.rebalance_scheduler import (
    RebalanceScheduler,
    compute_rebalance_dates,
    infer_side,
    round_to_lot,
)
from ah_research.backtest.types import BacktestConfig, Position, Weights
from ah_research.model.types import Currency, parse_symbol

# ─── helpers ────────────────────────────────────────────────────────────────


_SH = parse_symbol("600000.SH")
_SH2 = parse_symbol("600519.SH")
_HK = parse_symbol("0700.HK")
_TODAY = date(2024, 6, 28)
_FX_DEFAULT = {_TODAY: 1.0}


def _config(**overrides: object) -> BacktestConfig:
    base = {
        "start": date(2024, 1, 1),
        "end": date(2024, 12, 31),
        "initial_cash": Decimal("1000000"),
    }
    base.update(overrides)  # type: ignore[arg-type]
    return BacktestConfig(**base)  # type: ignore[arg-type]


def _scheduler(*, config: BacktestConfig | None = None) -> RebalanceScheduler:
    return RebalanceScheduler(config=config or _config(), logger=logging.getLogger("test"))


def _weights(rows: list[tuple[date, str, float]]) -> Weights:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime([r[0] for r in rows]),
            "symbol": [r[1] for r in rows],
            "weight": [r[2] for r in rows],
        }
    )
    return Weights(df=df)


def _bar(close: float) -> pd.Series:
    return pd.Series({"close": close})


# ─── pure helpers ───────────────────────────────────────────────────────────


def test_compute_rebalance_dates_picks_last_trading_day_per_period() -> None:
    days = [
        date(2024, 1, 2),
        date(2024, 1, 31),  # last trading day of Jan
        date(2024, 2, 1),
        date(2024, 2, 29),  # last trading day of Feb
    ]
    out = compute_rebalance_dates(days, "M")
    assert out == [date(2024, 1, 31), date(2024, 2, 29)]


def test_compute_rebalance_dates_empty_input() -> None:
    assert compute_rebalance_dates([], "M") == []


def test_round_to_lot_floors_buys_ceils_sells() -> None:
    assert round_to_lot(150.0, 100, is_buy=True) == 100  # floor
    assert round_to_lot(150.0, 100, is_buy=False) == 200  # ceiling


def test_round_to_lot_handles_zero_lot_size() -> None:
    """Defensive: lot_size <= 0 falls back to 1."""
    assert round_to_lot(123.0, 0, is_buy=True) == 123


def test_infer_side_transitions() -> None:
    # bigger long
    assert infer_side(100, 200) == "buy"
    # smaller long
    assert infer_side(200, 100) == "sell"
    # zero -> short
    assert infer_side(0, -100) == "short"
    # less negative (cover)
    assert infer_side(-200, -100) == "cover"
    # more negative
    assert infer_side(-100, -200) == "short"


# ─── scheduler.compute_orders ──────────────────────────────────────────────


def test_empty_weights_for_date_returns_no_orders() -> None:
    """When the weights frame has no rows for d, the scheduler emits nothing."""
    scheduler = _scheduler()
    # Weights for a different date.
    w = _weights([(date(2024, 5, 31), "600000.SH", 1.0)])

    orders = scheduler.compute_orders(
        d=_TODAY,
        weights=w,
        positions={},
        cash={Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")},
        prices_by_date_sym={},
        fx_lookup=_FX_DEFAULT,
    )
    assert orders == []


def test_target_weight_produces_buy_order_for_new_position() -> None:
    """Long 100% on a single symbol => one buy order, lot-rounded."""
    scheduler = _scheduler()
    w = _weights([(_TODAY, "600000.SH", 1.0)])
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    prices = {(_TODAY, "600000.SH"): _bar(close=10.0)}

    orders = scheduler.compute_orders(
        d=_TODAY,
        weights=w,
        positions={},
        cash=cash,
        prices_by_date_sym=prices,
        fx_lookup=_FX_DEFAULT,
    )

    assert len(orders) == 1
    o = orders[0]
    assert o.symbol == _SH
    assert o.side == "buy"
    # NAV = 100000; target = 100000/10 = 10000 shares; lot=100 => 10000.
    assert o.shares == 10000


def test_existing_position_at_target_emits_no_order() -> None:
    """If diff = target - current = 0, no order."""
    scheduler = _scheduler()
    w = _weights([(_TODAY, "600000.SH", 1.0)])
    positions = {_SH: Position(symbol=_SH, shares=10000, avg_cost=Decimal("10"))}
    cash = {Currency.CNY: Decimal("0"), Currency.HKD: Decimal("0")}
    prices = {(_TODAY, "600000.SH"): _bar(close=10.0)}

    orders = scheduler.compute_orders(
        d=_TODAY,
        weights=w,
        positions=positions,
        cash=cash,
        prices_by_date_sym=prices,
        fx_lookup=_FX_DEFAULT,
    )
    assert orders == []


def test_position_dropped_from_target_emits_close_order() -> None:
    """A symbol no longer in the weights gets a closing sell."""
    scheduler = _scheduler()
    # New target: only SH2; existing position in SH must be closed.
    w = _weights([(_TODAY, "600519.SH", 1.0)])
    positions = {
        _SH: Position(symbol=_SH, shares=200, avg_cost=Decimal("8")),
    }
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    prices = {
        (_TODAY, "600000.SH"): _bar(close=10.0),
        (_TODAY, "600519.SH"): _bar(close=20.0),
    }

    orders = scheduler.compute_orders(
        d=_TODAY,
        weights=w,
        positions=positions,
        cash=cash,
        prices_by_date_sym=prices,
        fx_lookup=_FX_DEFAULT,
    )

    syms = {o.symbol for o in orders}
    assert _SH in syms  # close
    assert _SH2 in syms  # open
    # The SH order is a sell (long position closing).
    sh_order = next(o for o in orders if o.symbol == _SH)
    assert sh_order.side == "sell"
    assert sh_order.shares == 200


def test_short_target_weight_produces_short_order() -> None:
    """Negative weight on a brand-new symbol => short order."""
    scheduler = _scheduler(config=_config(base_currency=Currency.HKD))
    w = _weights([(_TODAY, "0700.HK", -0.5)])
    cash = {Currency.CNY: Decimal("0"), Currency.HKD: Decimal("100000")}
    prices = {(_TODAY, "0700.HK"): _bar(close=100.0)}

    orders = scheduler.compute_orders(
        d=_TODAY,
        weights=w,
        positions={},
        cash=cash,
        prices_by_date_sym=prices,
        fx_lookup=_FX_DEFAULT,
    )

    assert len(orders) == 1
    o = orders[0]
    assert o.symbol == _HK
    assert o.side == "short"
    # 0.5 * 100000 / 100 = 500 shares, lot-rounded to 500
    assert o.shares == 500


def test_negative_price_skips_emit_no_order() -> None:
    """Bar close <= 0 is skipped silently (no order, no crash)."""
    scheduler = _scheduler()
    w = _weights([(_TODAY, "600000.SH", 1.0)])
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    prices = {(_TODAY, "600000.SH"): _bar(close=0.0)}

    orders = scheduler.compute_orders(
        d=_TODAY,
        weights=w,
        positions={},
        cash=cash,
        prices_by_date_sym=prices,
        fx_lookup=_FX_DEFAULT,
    )
    assert orders == []


def test_missing_bar_logs_warning_and_skips(caplog) -> None:  # type: ignore[no-untyped-def]
    """Symbol with no bar on rebalance date logs and skips."""
    scheduler = _scheduler()
    w = _weights([(_TODAY, "600000.SH", 1.0)])
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}

    with caplog.at_level(logging.WARNING):
        orders = scheduler.compute_orders(
            d=_TODAY,
            weights=w,
            positions={},
            cash=cash,
            prices_by_date_sym={},  # no bar!
            fx_lookup=_FX_DEFAULT,
        )

    assert orders == []
    assert any("No price bar for" in r.message for r in caplog.records)
