"""CorporateActionHandler — fourth carved-out collaborator from ``run_backtest``.

This module owns step 1 of the engine's daily loop: applying corporate
actions at the open, before order execution. The supported kinds are:

* ``cash_dividend`` -- credits the position's local-currency cash by
  ``amount_per_share * shares``. If ``dividend_policy="reinvest"`` the
  handler also queues a sentinel ``Order(shares=-1)`` for the next
  trading day; ``OrderExecutor`` resolves it to a real share count.
* ``stock_dividend`` / ``split`` -- multiplies shares; rescales avg cost
  so total cost basis is preserved.
* ``reverse_split`` -- same shape, ratio < 1.
* ``rights_issue`` / ``spin_off`` -- logged as cash-equivalent in
  Phase 2 (no shares issued; manual adjustment expected).
* Anything else -- logged as unknown and skipped.

Holds ``positions`` and ``cash`` dicts by reference -- mutating them
in place preserves today's invariant where the rest of the daily loop
sees corp-action effects.

Behaviour-preserving extraction. No public API change to ``run_backtest``.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from ah_research.backtest.types import Order, Position
from ah_research.exceptions import UserInputError
from ah_research.model.types import Currency, Symbol, parse_symbol


class CorporateActionHandler:
    """Applies a single corporate-action row to the live ``positions`` and
    ``cash`` books. Holds both by reference so the daily loop and the
    handler always observe the same state.
    """

    def __init__(
        self,
        *,
        positions: dict[Symbol, Position],
        cash: dict[Currency, Decimal],
        logger: Any,
    ) -> None:
        self._positions = positions
        self._cash = cash
        self._logger = logger

    def apply(
        self,
        *,
        ca_row: pd.Series,
        dividend_policy: str,
        pending_orders: list[Order],
        d: date,
    ) -> None:
        """Apply one corporate-action row.

        Mutates ``self._positions`` and ``self._cash`` in place; may
        append a dividend-reinvestment sentinel to ``pending_orders``
        (not held by reference -- the engine still owns the queue).
        """
        sym_str = str(ca_row["symbol"])
        kind = str(ca_row["kind"])
        params = json.loads(str(ca_row["params_json"]))

        try:
            symbol = parse_symbol(sym_str)
        except UserInputError:
            self._logger.warning("Cannot parse symbol %r in corporate action; skipping.", sym_str)
            return

        if symbol not in self._positions:
            return

        pos = self._positions[symbol]

        if kind == "cash_dividend":
            self._apply_cash_dividend(
                symbol=symbol,
                pos=pos,
                params=params,
                dividend_policy=dividend_policy,
                pending_orders=pending_orders,
                d=d,
                sym_str=sym_str,
            )
        elif kind in ("stock_dividend", "split"):
            self._apply_stock_dividend_or_split(
                symbol=symbol, pos=pos, kind=kind, params=params, sym_str=sym_str
            )
        elif kind == "reverse_split":
            self._apply_reverse_split(symbol=symbol, pos=pos, params=params, sym_str=sym_str)
        elif kind in ("rights_issue", "spin_off"):
            self._logger.warning(
                "Corporate action %r for %s treated as cash-equivalent in Phase 2; "
                "no shares issued. Adjust manually if needed.",
                kind,
                sym_str,
            )
        else:
            self._logger.warning(
                "Unknown corporate action kind %r for %s; skipping.", kind, sym_str
            )

    # -- per-kind handlers ------------------------------------------------

    def _apply_cash_dividend(
        self,
        *,
        symbol: Symbol,
        pos: Position,
        params: dict[str, Any],
        dividend_policy: str,
        pending_orders: list[Order],
        d: date,
        sym_str: str,
    ) -> None:
        amount_per_share = Decimal(str(params.get("amount_per_share", 0)))
        dividend_cash = amount_per_share * pos.shares
        ccy = symbol.currency
        self._cash[ccy] = self._cash.get(ccy, Decimal("0")) + dividend_cash
        self._logger.debug(
            "Cash dividend %s %s per share for %s; credited %s %s",
            amount_per_share,
            ccy,
            sym_str,
            dividend_cash,
            ccy,
        )
        if dividend_policy == "reinvest" and dividend_cash > 0:
            # Sentinel order: shares=-1 means "reinvest the earmarked dividend
            # cash"; OrderExecutor resolves to a real share count.
            pending_orders.append(
                Order(
                    ready_date=d,
                    symbol=symbol,
                    side="buy",
                    shares=-1,
                )
            )

    def _apply_stock_dividend_or_split(
        self,
        *,
        symbol: Symbol,
        pos: Position,
        kind: str,
        params: dict[str, Any],
        sym_str: str,
    ) -> None:
        ratio = Decimal(str(params.get("ratio", 1)))
        # stock_dividend: ratio=0.1 means 10 extra shares per 100 held
        # split: ratio=2.0 means 2-for-1
        if kind == "stock_dividend":
            new_shares = int(pos.shares * (1 + float(ratio)))
        else:
            new_shares = int(pos.shares * float(ratio))
        new_avg_cost = self._rescale_avg_cost(pos, new_shares)
        self._positions[symbol] = replace(pos, shares=new_shares, avg_cost=new_avg_cost)
        self._logger.info(
            "Corporate action %s for %s: shares %d -> %d",
            kind,
            sym_str,
            pos.shares,
            new_shares,
        )

    def _apply_reverse_split(
        self,
        *,
        symbol: Symbol,
        pos: Position,
        params: dict[str, Any],
        sym_str: str,
    ) -> None:
        ratio = Decimal(str(params.get("ratio", 1)))
        # reverse_split: ratio=0.5 means 1-for-2
        new_shares = int(pos.shares * float(ratio))
        new_avg_cost = self._rescale_avg_cost(pos, new_shares)
        self._positions[symbol] = replace(pos, shares=new_shares, avg_cost=new_avg_cost)
        self._logger.info(
            "Reverse split for %s: shares %d -> %d",
            sym_str,
            pos.shares,
            new_shares,
        )

    @staticmethod
    def _rescale_avg_cost(pos: Position, new_shares: int) -> Decimal:
        """Rescale avg_cost so total cost basis (avg * shares) is preserved."""
        if new_shares > 0 and pos.shares > 0:
            return pos.avg_cost * Decimal(str(pos.shares)) / Decimal(str(new_shares))
        return pos.avg_cost
