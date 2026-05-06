"""Unit tests for ``backtest.mtm_accumulator.MTMAccumulator``
(carved out in C1-05).

Pins the contract of the EOD state machine: signed NAV recording (long
positive, short negative), per-currency cash history, T+N lock expiry,
and the final positions snapshot built at finalize time.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from ah_research.backtest.mtm_accumulator import MTMAccumulator
from ah_research.backtest.types import BacktestConfig, Position
from ah_research.model.types import Currency, Symbol, parse_symbol

# ─── helpers ────────────────────────────────────────────────────────────────


_SH = parse_symbol("600000.SH")
_HK = parse_symbol("0700.HK")
_DAY1 = date(2024, 6, 3)
_DAY2 = date(2024, 6, 4)
_DAY3 = date(2024, 6, 5)
_FX_DEFAULT = {_DAY1: 1.0, _DAY2: 1.0, _DAY3: 1.0}


def _config(**overrides: object) -> BacktestConfig:
    base = {
        "start": date(2024, 1, 1),
        "end": date(2024, 12, 31),
        "initial_cash": Decimal("1000000"),
    }
    base.update(overrides)  # type: ignore[arg-type]
    return BacktestConfig(**base)  # type: ignore[arg-type]


def _bar(close: float) -> pd.Series:
    return pd.Series({"close": close})


def _accumulator(
    *,
    positions: dict[Symbol, Position],
    cash: dict[Currency, Decimal],
    prices: dict[tuple[date, str], pd.Series],
    config: BacktestConfig | None = None,
) -> MTMAccumulator:
    return MTMAccumulator(
        positions=positions,
        cash=cash,
        prices_by_date_sym=prices,
        config=config or _config(),
    )


# ─── record_eod ────────────────────────────────────────────────────────────


def test_record_eod_with_only_cash_returns_cash_balance() -> None:
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    mtm = _accumulator(positions={}, cash=cash, prices={})

    mtm.record_eod(d=_DAY1, fx_lookup=_FX_DEFAULT)

    assert mtm.equity_daily == [(_DAY1, Decimal("100000"))]
    assert mtm.cash_history == [{"date": _DAY1, "CNY": 100000.0, "HKD": 0.0}]


def test_record_eod_includes_long_position_mtm() -> None:
    """NAV = cash + sum(shares * close * fx)."""
    cash = {Currency.CNY: Decimal("50000"), Currency.HKD: Decimal("0")}
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    prices = {(_DAY1, "600000.SH"): _bar(close=12.0)}
    mtm = _accumulator(positions=positions, cash=cash, prices=prices)

    mtm.record_eod(d=_DAY1, fx_lookup=_FX_DEFAULT)

    # 50000 + 1000 * 12 = 62000
    assert mtm.equity_daily[0][1] == Decimal("62000")


def test_record_eod_signs_short_negatively() -> None:
    """Short position contributes negative MTM."""
    cash = {Currency.CNY: Decimal("0"), Currency.HKD: Decimal("100000")}
    positions = {_HK: Position(symbol=_HK, shares=-100, avg_cost=Decimal("100"))}
    prices = {(_DAY1, "0700.HK"): _bar(close=110.0)}
    mtm = _accumulator(
        positions=positions,
        cash=cash,
        prices=prices,
        config=_config(base_currency=Currency.HKD),
    )

    mtm.record_eod(d=_DAY1, fx_lookup=_FX_DEFAULT)

    # 100000 + (-100) * 110 = 89000
    assert mtm.equity_daily[0][1] == Decimal("89000")


def test_record_eod_skips_position_with_no_bar() -> None:
    """A symbol with no bar on day d is silently skipped (no MTM contribution)."""
    cash = {Currency.CNY: Decimal("50000"), Currency.HKD: Decimal("0")}
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    mtm = _accumulator(positions=positions, cash=cash, prices={})  # no bars

    mtm.record_eod(d=_DAY1, fx_lookup=_FX_DEFAULT)

    # NAV is just cash; position contribution skipped.
    assert mtm.equity_daily[0][1] == Decimal("50000")


def test_record_eod_appends_per_day() -> None:
    """Multiple days produce multiple equity points."""
    cash = {Currency.CNY: Decimal("100000"), Currency.HKD: Decimal("0")}
    mtm = _accumulator(positions={}, cash=cash, prices={})

    mtm.record_eod(d=_DAY1, fx_lookup=_FX_DEFAULT)
    cash[Currency.CNY] = Decimal("99000")  # simulate cash change between days
    mtm.record_eod(d=_DAY2, fx_lookup=_FX_DEFAULT)

    assert [d for d, _ in mtm.equity_daily] == [_DAY1, _DAY2]
    assert [v for _, v in mtm.equity_daily] == [Decimal("100000"), Decimal("99000")]


# ─── expire_locks ─────────────────────────────────────────────────────────


def test_expire_locks_clears_when_d_at_or_past_lock_date() -> None:
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"), locked_until=_DAY1)}
    mtm = _accumulator(positions=positions, cash={Currency.CNY: Decimal("0")}, prices={})

    mtm.expire_locks(_DAY1)

    assert positions[_SH].locked_until is None


def test_expire_locks_keeps_lock_when_d_before_expiry() -> None:
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"), locked_until=_DAY3)}
    mtm = _accumulator(positions=positions, cash={Currency.CNY: Decimal("0")}, prices={})

    mtm.expire_locks(_DAY1)  # before _DAY3

    assert positions[_SH].locked_until == _DAY3


def test_expire_locks_skips_already_unlocked_positions() -> None:
    """Unlocked positions are left alone; idempotent."""
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"), locked_until=None)}
    mtm = _accumulator(positions=positions, cash={Currency.CNY: Decimal("0")}, prices={})

    mtm.expire_locks(_DAY1)

    assert positions[_SH].locked_until is None


# ─── build_positions_history ───────────────────────────────────────────────


def test_build_positions_history_uses_last_recorded_eod_date() -> None:
    cash = {Currency.CNY: Decimal("0"), Currency.HKD: Decimal("0")}
    positions = {_SH: Position(symbol=_SH, shares=200, avg_cost=Decimal("10"))}
    prices = {
        (_DAY1, "600000.SH"): _bar(close=10.0),
        (_DAY2, "600000.SH"): _bar(close=15.0),  # final-day price used
    }
    mtm = _accumulator(positions=positions, cash=cash, prices=prices)
    mtm.record_eod(d=_DAY1, fx_lookup=_FX_DEFAULT)
    mtm.record_eod(d=_DAY2, fx_lookup=_FX_DEFAULT)

    rows = mtm.build_positions_history(_FX_DEFAULT)

    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == _DAY2
    assert row["symbol"] == "600000.SH"
    assert row["shares"] == 200
    assert row["mkt_value_local"] == 200 * 15.0
    assert row["mkt_value_base"] == 200 * 15.0  # fx=1.0


def test_build_positions_history_returns_empty_when_no_eod_recorded() -> None:
    """Defensive: empty equity_daily => empty rows."""
    mtm = _accumulator(
        positions={_SH: Position(symbol=_SH, shares=100, avg_cost=Decimal("10"))},
        cash={Currency.CNY: Decimal("0")},
        prices={},
    )

    assert mtm.build_positions_history(_FX_DEFAULT) == []


def test_build_positions_history_zero_price_when_bar_missing() -> None:
    """Missing bar on the final day => mkt values = 0 (matches engine behaviour)."""
    cash = {Currency.CNY: Decimal("0"), Currency.HKD: Decimal("0")}
    positions = {_SH: Position(symbol=_SH, shares=200, avg_cost=Decimal("10"))}
    mtm = _accumulator(positions=positions, cash=cash, prices={})  # no bar!
    mtm.record_eod(d=_DAY1, fx_lookup=_FX_DEFAULT)

    rows = mtm.build_positions_history(_FX_DEFAULT)

    assert len(rows) == 1
    assert rows[0]["mkt_value_local"] == 0.0
    assert rows[0]["mkt_value_base"] == 0.0
