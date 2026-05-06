"""Unit tests for ``backtest.corporate_actions.CorporateActionHandler``
(carved out in C1-05).

Pins the contract of step 1 of the daily loop: per-kind dispatch
(cash_dividend with reinvest sentinel, stock_dividend, split,
reverse_split, rights_issue/spin_off, unknown), the parse_symbol
failure branch, and the symbol-not-in-positions skip.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal

import pandas as pd

from ah_research.backtest.corporate_actions import CorporateActionHandler
from ah_research.backtest.types import Order, Position
from ah_research.model.types import Currency, Symbol, parse_symbol

# ─── helpers ────────────────────────────────────────────────────────────────


_SH = parse_symbol("600000.SH")
_TODAY = date(2024, 6, 3)


def _row(*, symbol: str, kind: str, params: dict[str, object]) -> pd.Series:
    return pd.Series(
        {
            "symbol": symbol,
            "kind": kind,
            "params_json": json.dumps(params),
        }
    )


def _handler(
    *,
    positions: dict[Symbol, Position],
    cash: dict[Currency, Decimal],
) -> CorporateActionHandler:
    return CorporateActionHandler(
        positions=positions,
        cash=cash,
        logger=logging.getLogger("test"),
    )


# ─── cash_dividend ─────────────────────────────────────────────────────────


def test_cash_dividend_credits_cash_in_local_currency() -> None:
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    cash = {Currency.CNY: Decimal("0")}
    handler = _handler(positions=positions, cash=cash)
    pending: list[Order] = []

    handler.apply(
        ca_row=_row(symbol="600000.SH", kind="cash_dividend", params={"amount_per_share": "0.5"}),
        dividend_policy="cash",  # not reinvest
        pending_orders=pending,
        d=_TODAY,
    )

    # 1000 * 0.5 = 500 CNY
    assert cash[Currency.CNY] == Decimal("500")
    # No reinvestment order queued under "cash" policy.
    assert pending == []


def test_cash_dividend_reinvest_queues_sentinel_order() -> None:
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    cash = {Currency.CNY: Decimal("0")}
    handler = _handler(positions=positions, cash=cash)
    pending: list[Order] = []

    handler.apply(
        ca_row=_row(symbol="600000.SH", kind="cash_dividend", params={"amount_per_share": "0.5"}),
        dividend_policy="reinvest",
        pending_orders=pending,
        d=_TODAY,
    )

    assert len(pending) == 1
    sentinel = pending[0]
    assert sentinel.symbol == _SH
    assert sentinel.side == "buy"
    assert sentinel.shares == -1  # the reinvestment sentinel
    assert sentinel.ready_date == _TODAY
    # And cash is still credited.
    assert cash[Currency.CNY] == Decimal("500")


def test_cash_dividend_reinvest_skips_when_zero_amount() -> None:
    """Zero dividend amount => no sentinel queued (matches engine guard)."""
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    cash = {Currency.CNY: Decimal("0")}
    handler = _handler(positions=positions, cash=cash)
    pending: list[Order] = []

    handler.apply(
        ca_row=_row(symbol="600000.SH", kind="cash_dividend", params={"amount_per_share": "0"}),
        dividend_policy="reinvest",
        pending_orders=pending,
        d=_TODAY,
    )

    assert pending == []


# ─── stock_dividend / split ────────────────────────────────────────────────


def test_stock_dividend_grows_shares_and_rescales_avg_cost() -> None:
    """ratio=0.1 => 10% bonus shares; cost basis preserved."""
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    cash = {Currency.CNY: Decimal("0")}
    handler = _handler(positions=positions, cash=cash)

    handler.apply(
        ca_row=_row(symbol="600000.SH", kind="stock_dividend", params={"ratio": "0.1"}),
        dividend_policy="cash",
        pending_orders=[],
        d=_TODAY,
    )

    assert positions[_SH].shares == 1100
    # Cost basis preserved: 10 * 1000 = 11000; 11000 / 1100 = 10
    assert positions[_SH].avg_cost == Decimal("10000") / Decimal("1100")


def test_split_2_for_1_doubles_shares_halves_avg_cost() -> None:
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("20"))}
    handler = _handler(positions=positions, cash={Currency.CNY: Decimal("0")})

    handler.apply(
        ca_row=_row(symbol="600000.SH", kind="split", params={"ratio": "2.0"}),
        dividend_policy="cash",
        pending_orders=[],
        d=_TODAY,
    )

    assert positions[_SH].shares == 2000
    assert positions[_SH].avg_cost == Decimal("10")


# ─── reverse_split ────────────────────────────────────────────────────────


def test_reverse_split_1_for_2_halves_shares_doubles_avg_cost() -> None:
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    handler = _handler(positions=positions, cash={Currency.CNY: Decimal("0")})

    handler.apply(
        ca_row=_row(symbol="600000.SH", kind="reverse_split", params={"ratio": "0.5"}),
        dividend_policy="cash",
        pending_orders=[],
        d=_TODAY,
    )

    assert positions[_SH].shares == 500
    assert positions[_SH].avg_cost == Decimal("20")


# ─── rights_issue / spin_off / unknown ──────────────────────────────────────


def test_rights_issue_logs_warning_and_does_not_mutate(caplog) -> None:  # type: ignore[no-untyped-def]
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    cash = {Currency.CNY: Decimal("0")}
    handler = _handler(positions=positions, cash=cash)

    with caplog.at_level(logging.WARNING):
        handler.apply(
            ca_row=_row(symbol="600000.SH", kind="rights_issue", params={}),
            dividend_policy="cash",
            pending_orders=[],
            d=_TODAY,
        )

    assert positions[_SH].shares == 1000
    assert any("rights_issue" in r.message for r in caplog.records)


def test_spin_off_logs_warning_and_does_not_mutate(caplog) -> None:  # type: ignore[no-untyped-def]
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    handler = _handler(positions=positions, cash={Currency.CNY: Decimal("0")})

    with caplog.at_level(logging.WARNING):
        handler.apply(
            ca_row=_row(symbol="600000.SH", kind="spin_off", params={}),
            dividend_policy="cash",
            pending_orders=[],
            d=_TODAY,
        )

    assert positions[_SH].shares == 1000
    assert any("spin_off" in r.message for r in caplog.records)


def test_unknown_kind_logs_warning_and_skips(caplog) -> None:  # type: ignore[no-untyped-def]
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    handler = _handler(positions=positions, cash={Currency.CNY: Decimal("0")})

    with caplog.at_level(logging.WARNING):
        handler.apply(
            ca_row=_row(symbol="600000.SH", kind="something_weird", params={}),
            dividend_policy="cash",
            pending_orders=[],
            d=_TODAY,
        )

    assert positions[_SH].shares == 1000
    assert any("Unknown corporate action kind" in r.message for r in caplog.records)


# ─── parse / lookup failures ────────────────────────────────────────────────


def test_unparseable_symbol_logs_and_skips(caplog) -> None:  # type: ignore[no-untyped-def]
    """Bad symbol string => warning + no-op (no positions touched)."""
    positions = {_SH: Position(symbol=_SH, shares=1000, avg_cost=Decimal("10"))}
    handler = _handler(positions=positions, cash={Currency.CNY: Decimal("0")})

    with caplog.at_level(logging.WARNING):
        handler.apply(
            ca_row=_row(
                symbol="not-a-symbol", kind="cash_dividend", params={"amount_per_share": "1"}
            ),
            dividend_policy="cash",
            pending_orders=[],
            d=_TODAY,
        )

    assert positions[_SH].shares == 1000  # untouched
    assert any("Cannot parse symbol" in r.message for r in caplog.records)


def test_symbol_not_in_positions_silently_skips() -> None:
    """Corp action for a symbol we don't hold => silent skip (no warning)."""
    positions: dict[Symbol, Position] = {}  # empty
    cash = {Currency.CNY: Decimal("100")}
    handler = _handler(positions=positions, cash=cash)
    pending: list[Order] = []

    handler.apply(
        ca_row=_row(symbol="600000.SH", kind="cash_dividend", params={"amount_per_share": "1"}),
        dividend_policy="reinvest",
        pending_orders=pending,
        d=_TODAY,
    )

    # Cash unchanged, no positions added, no order queued.
    assert cash[Currency.CNY] == Decimal("100")
    assert positions == {}
    assert pending == []
