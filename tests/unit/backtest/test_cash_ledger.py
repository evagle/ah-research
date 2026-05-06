"""Unit tests for ``backtest.cash_ledger.CashLedger`` (carved out in C1-03).

Pins the contract of the post-validation stage in isolation: the cash-
sufficiency back-solve, position/cash mutation rules (weighted-average
cost on buys, share-decrement on sells, short-open path), cross-currency
shortfall conversion, and the T+N lock stamp.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from ah_research.backtest.cash_ledger import (
    CashLedger,
    cash_in_base,
    fx_to_base,
    next_n_trading_days,
)
from ah_research.backtest.costs import DEFAULT_COSTS_2024, CostModelBundle
from ah_research.backtest.order_executor import PricedFill
from ah_research.backtest.types import BacktestConfig, Order, Position
from ah_research.model.types import Currency, Symbol, parse_symbol

# ─── helpers ────────────────────────────────────────────────────────────────


_SH = parse_symbol("600000.SH")
_HK = parse_symbol("0700.HK")
_TODAY = date(2024, 6, 3)

# Default FX map covering _TODAY so cross-currency dict iteration in
# ``cash_in_base`` works even when a test only cares about one ccy.
_FX_DEFAULT: dict[date, float] = {_TODAY: 1.0}


def _config(**overrides: object) -> BacktestConfig:
    base = {
        "start": date(2024, 1, 1),
        "end": date(2024, 12, 31),
        "initial_cash": Decimal("1000000"),
        "settlement": "auto",
    }
    base.update(overrides)  # type: ignore[arg-type]
    return BacktestConfig(**base)  # type: ignore[arg-type]


def _ledger(
    *,
    positions: dict[Symbol, Position],
    cash: dict[Currency, Decimal],
    config: BacktestConfig | None = None,
    cost_model: CostModelBundle = DEFAULT_COSTS_2024,
) -> CashLedger:
    cfg = config or _config()
    sh_days = [
        date(2024, 6, 1),
        date(2024, 6, 2),
        date(2024, 6, 3),
        date(2024, 6, 4),
        date(2024, 6, 5),
    ]
    hk_days = sh_days
    return CashLedger(
        positions=positions,
        cash=cash,
        cost_model=cost_model,
        config=cfg,
        sh_days=sh_days,
        hk_days=hk_days,
        logger=logging.getLogger("test"),
    )


def _priced_fill(
    *,
    symbol: Symbol = _SH,
    side: str = "buy",
    shares: int = 100,
    fill_price: Decimal = Decimal("10"),
    cost_total: Decimal = Decimal("5"),
) -> PricedFill:
    notional = fill_price * Decimal(str(shares))
    return PricedFill(
        order=Order(ready_date=_TODAY, symbol=symbol, side=side, shares=shares),  # type: ignore[arg-type]
        shares=shares,
        fill_price=fill_price,
        notional_local=notional,
        cost_total=cost_total,
        cost_breakdown={"commission": cost_total},
    )


# ─── helper functions ──────────────────────────────────────────────────────


def test_fx_to_base_identity() -> None:
    assert fx_to_base(Currency.CNY, Currency.CNY, _TODAY, {}) == Decimal("1")


def test_fx_to_base_hkd_to_cny_inverts_rate() -> None:
    """If 1 CNY = 1.1 HKD, then 1 HKD = 1/1.1 CNY."""
    fx = {_TODAY: 1.1}
    rate = fx_to_base(Currency.HKD, Currency.CNY, _TODAY, fx)
    assert rate == Decimal("1") / Decimal("1.1")


def test_fx_to_base_falls_back_to_nearest_past_date() -> None:
    fx = {date(2024, 6, 1): 1.2}  # earlier date only
    rate = fx_to_base(Currency.HKD, Currency.CNY, _TODAY, fx)
    assert rate == Decimal("1") / Decimal("1.2")


def test_cash_in_base_sums_across_currencies() -> None:
    """Cash totals are converted to base currency before summation."""
    cash = {Currency.CNY: Decimal("1000"), Currency.HKD: Decimal("550")}
    fx = {_TODAY: 1.1}  # 1 CNY = 1.1 HKD => 1 HKD = 1/1.1 CNY
    total = cash_in_base(cash, Currency.CNY, _TODAY, fx)
    expected = Decimal("1000") + Decimal("550") / Decimal("1.1")
    assert total == expected


def test_next_n_trading_days_picks_correct_offset() -> None:
    days = [date(2024, 6, 3), date(2024, 6, 4), date(2024, 6, 5), date(2024, 6, 6)]
    assert next_n_trading_days(days, date(2024, 6, 3), 1) == date(2024, 6, 4)
    assert next_n_trading_days(days, date(2024, 6, 3), 2) == date(2024, 6, 5)


# ─── buy / cover branch ───────────────────────────────────────────────────


def test_buy_creates_new_position_with_fill_price_avg_cost() -> None:
    positions: dict[Symbol, Position] = {}
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    ledger = _ledger(positions=positions, cash=cash)

    fill = _priced_fill(shares=100, fill_price=Decimal("10"), cost_total=Decimal("5"))
    res = ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert res.skipped is False
    assert res.shares == 100
    assert _SH in positions
    assert positions[_SH].shares == 100
    assert positions[_SH].avg_cost == Decimal("10")
    # Cash debited by notional + cost.
    assert cash[Currency.CNY] == Decimal("100000") - Decimal("1000") - Decimal("5")


def test_buy_into_existing_position_updates_avg_cost_weighted() -> None:
    """Avg cost = (existing_basis + new_notional) / new_shares."""
    positions = {_SH: Position(symbol=_SH, shares=100, avg_cost=Decimal("8"))}
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    ledger = _ledger(positions=positions, cash=cash)

    fill = _priced_fill(shares=100, fill_price=Decimal("12"), cost_total=Decimal("5"))
    ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    # (8*100 + 12*100) / 200 = 10
    assert positions[_SH].shares == 200
    assert positions[_SH].avg_cost == Decimal("10")


def test_buy_stamps_locked_until_per_settlement_auto() -> None:
    """SH default is T+1; with settlement=auto, locked_until = next trading day."""
    positions: dict[Symbol, Position] = {}
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    ledger = _ledger(positions=positions, cash=cash)

    fill = _priced_fill(shares=100, fill_price=Decimal("10"), cost_total=Decimal("5"))
    ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert positions[_SH].locked_until == date(2024, 6, 4)


def test_buy_t_plus_zero_does_not_lock() -> None:
    """settlement="T+0" produces no lock."""
    positions: dict[Symbol, Position] = {}
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    ledger = _ledger(positions=positions, cash=cash, config=_config(settlement="T+0"))

    fill = _priced_fill(shares=100, fill_price=Decimal("10"), cost_total=Decimal("5"))
    ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert positions[_SH].locked_until is None


def test_hk_buy_settlement_is_two_trading_days() -> None:
    """HK auto settlement is T+2."""
    positions: dict[Symbol, Position] = {}
    cash = {Currency.CNY: Decimal("0"), Currency.HKD: Decimal("100000")}
    ledger = _ledger(positions=positions, cash=cash, config=_config(base_currency=Currency.HKD))

    fill = _priced_fill(symbol=_HK, shares=100, fill_price=Decimal("100"), cost_total=Decimal("50"))
    ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert positions[_HK].locked_until == date(2024, 6, 5)


# ─── cash back-solve ──────────────────────────────────────────────────────


def test_back_solve_reduces_to_affordable_lots_when_cash_short() -> None:
    """Asks for 1000 shares but only has cash for ~500; ledger reduces to 500."""
    positions: dict[Symbol, Position] = {}
    # 1000 shares * 10 = 10000 notional; have 5500 cash => can afford 500 shares
    cash = {Currency.CNY: Decimal("5500"), Currency.HKD: Decimal("0")}
    ledger = _ledger(positions=positions, cash=cash)

    fill = _priced_fill(shares=1000, fill_price=Decimal("10"), cost_total=Decimal("100"))
    res = ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert res.skipped is False
    assert res.shares < 1000
    # Whatever it bought must be lot-aligned (100 increments).
    assert res.shares % 100 == 0
    # Cash never goes negative on the local currency.
    assert cash[Currency.CNY] >= Decimal("0")


def test_back_solve_skips_order_when_one_lot_unaffordable() -> None:
    """500 cash can't buy a single 100-share lot at 10 plus min commission."""
    positions: dict[Symbol, Position] = {}
    cash = {Currency.CNY: Decimal("100"), Currency.HKD: Decimal("0")}  # too low for any lot
    ledger = _ledger(positions=positions, cash=cash)

    fill = _priced_fill(shares=1000, fill_price=Decimal("10"), cost_total=Decimal("100"))
    res = ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert res.skipped is True
    # No position created.
    assert _SH not in positions
    # Cash untouched.
    assert cash[Currency.CNY] == Decimal("100")


def test_back_solve_no_op_when_cash_sufficient() -> None:
    """Sufficient cash => no reduction, original shares persist."""
    positions: dict[Symbol, Position] = {}
    cash = {Currency.CNY: Decimal("1000000"), Currency.HKD: Decimal("0")}
    ledger = _ledger(positions=positions, cash=cash)

    fill = _priced_fill(shares=200, fill_price=Decimal("10"), cost_total=Decimal("5"))
    res = ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert res.skipped is False
    assert res.shares == 200
    assert res.notional_local == Decimal("2000")


# ─── sell branch ──────────────────────────────────────────────────────────


def test_sell_decrements_shares() -> None:
    positions = {_SH: Position(symbol=_SH, shares=300, avg_cost=Decimal("10"))}
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    ledger = _ledger(positions=positions, cash=cash)

    fill = _priced_fill(side="sell", shares=100, fill_price=Decimal("12"), cost_total=Decimal("5"))
    res = ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert res.skipped is False
    assert positions[_SH].shares == 200
    # Cash credited by notional - cost.
    assert cash[Currency.CNY] == Decimal("100000") + Decimal("1200") - Decimal("5")


def test_sell_pops_position_when_shares_zero() -> None:
    positions = {_SH: Position(symbol=_SH, shares=100, avg_cost=Decimal("10"))}
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    ledger = _ledger(positions=positions, cash=cash)

    fill = _priced_fill(side="sell", shares=100, fill_price=Decimal("12"), cost_total=Decimal("5"))
    ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert _SH not in positions


# ─── short-open branch ────────────────────────────────────────────────────


def test_short_creates_negative_position() -> None:
    """Shorting an unheld symbol creates a negative-shares position."""
    positions: dict[Symbol, Position] = {}
    cash = {Currency.CNY: Decimal("0"), Currency.HKD: Decimal("100000")}
    ledger = _ledger(positions=positions, cash=cash, config=_config(base_currency=Currency.HKD))

    fill = _priced_fill(
        symbol=_HK, side="short", shares=100, fill_price=Decimal("100"), cost_total=Decimal("50")
    )
    res = ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=_FX_DEFAULT)

    assert res.skipped is False
    assert positions[_HK].shares == -100
    assert positions[_HK].avg_cost == Decimal("100")
    # Cash credited (short proceeds).
    assert cash[Currency.HKD] == Decimal("100000") + Decimal("10000") - Decimal("50")


# ─── cross-currency shortfall ─────────────────────────────────────────────


def test_buy_cross_currency_shortfall_converts_to_base() -> None:
    """Buying HK with empty HKD wallet drains base CNY by the converted shortfall."""
    positions: dict[Symbol, Position] = {}
    cash = {
        Currency.CNY: Decimal("100000"),  # base
        Currency.HKD: Decimal("0"),
    }
    cfg = _config(base_currency=Currency.CNY)
    ledger = _ledger(positions=positions, cash=cash, config=cfg)

    fx_lookup = {_TODAY: 1.1}  # 1 CNY = 1.1 HKD
    fill = _priced_fill(symbol=_HK, shares=100, fill_price=Decimal("100"), cost_total=Decimal("50"))
    res = ledger.apply_fill(fill=fill, d=_TODAY, fx_lookup=fx_lookup)

    assert res.skipped is False
    # Shortfall = 100 * 100 + 50 = 10050 HKD
    # In CNY: 10050 / 1.1 = 9136.3636...
    expected_cny = Decimal("100000") - Decimal("10050") / Decimal("1.1")
    assert cash[Currency.CNY] == expected_cny
    # HKD wallet reset to zero (was overdrawn, now backfilled).
    assert cash[Currency.HKD] == Decimal("0")
