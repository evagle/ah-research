"""MTMAccumulator — fifth carved-out collaborator from ``run_backtest``.

This module owns the *end-of-day* concerns of the engine's daily loop:

1. ``record_eod`` -- compute the end-of-day NAV in base currency
   (cash_in_base + signed sum of MTM positions), append to the equity
   series, and snapshot per-currency cash balances.
2. ``expire_locks`` -- drop the ``locked_until`` stamp on positions
   whose T+N lock window has elapsed.
3. ``build_positions_history`` -- snapshot the final-day positions in
   the format ``BacktestResult.positions_history`` expects (one row
   per symbol with shares + mkt_value_local + mkt_value_base).

Holds ``positions`` and ``cash`` dicts by reference -- mutating them
in place preserves today's invariant where the rest of the daily loop
sees the EOD state. Owns its own append-only buffers (``equity_daily``
and ``cash_history``) so the engine no longer needs to track them.

Behaviour-preserving extraction. No public API change to ``run_backtest``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from ah_research.backtest.cash_ledger import cash_in_base, fx_to_base
from ah_research.backtest.types import BacktestConfig, Position
from ah_research.model.types import Currency, Symbol


class MTMAccumulator:
    """End-of-day state machine: NAV recording, lock expiry, and final
    positions snapshot.

    Holds the live ``positions`` and ``cash`` dicts by reference; all
    other state (equity_daily, cash_history) is owned internally and
    exposed via read-only accessors.
    """

    def __init__(
        self,
        *,
        positions: dict[Symbol, Position],
        cash: dict[Currency, Decimal],
        prices_by_date_sym: dict[tuple[date, str], pd.Series],
        config: BacktestConfig,
    ) -> None:
        self._positions = positions
        self._cash = cash
        self._prices = prices_by_date_sym
        self._config = config
        self._equity_daily: list[tuple[date, Decimal]] = []
        self._cash_history: list[dict[str, Any]] = []

    # -- daily-loop API ---------------------------------------------------

    def record_eod(self, *, d: date, fx_lookup: dict[date, float]) -> None:
        """Append today's NAV (cash + signed MTM) to ``equity_daily`` and
        snapshot per-currency cash balances into ``cash_history``."""
        nav_d = cash_in_base(self._cash, self._config.base_currency, d, fx_lookup)
        for sym_s, pos in self._positions.items():
            bar_data = self._prices.get((d, str(sym_s)))
            if bar_data is None:
                continue
            price_local = Decimal(str(float(bar_data["close"])))
            fx_rate = fx_to_base(sym_s.currency, self._config.base_currency, d, fx_lookup)
            # Signed: short positions contribute negative MV.
            nav_d += Decimal(str(pos.shares)) * price_local * fx_rate
        self._equity_daily.append((d, nav_d))

        self._cash_history.append(
            {
                "date": d,
                "CNY": float(self._cash.get(Currency.CNY, Decimal("0"))),
                "HKD": float(self._cash.get(Currency.HKD, Decimal("0"))),
            }
        )

    def expire_locks(self, d: date) -> None:
        """Clear ``locked_until`` on any position whose T+N window has
        elapsed (``locked_until <= d``)."""
        for sym_lock, pos_lock in list(self._positions.items()):
            if pos_lock.locked_until is not None and pos_lock.locked_until <= d:
                self._positions[sym_lock] = replace(pos_lock, locked_until=None)

    # -- finalize accessors ----------------------------------------------

    @property
    def equity_daily(self) -> list[tuple[date, Decimal]]:
        return self._equity_daily

    @property
    def cash_history(self) -> list[dict[str, Any]]:
        return self._cash_history

    def build_positions_history(self, fx_lookup: dict[date, float]) -> list[dict[str, Any]]:
        """End-of-run positions snapshot at the last recorded EOD date.

        Returns ``[]`` when no EOD has been recorded -- the engine
        constructs the empty DataFrame in that case.
        """
        if not self._equity_daily:
            return []
        last_d = self._equity_daily[-1][0]
        rows: list[dict[str, Any]] = []
        for sym_s, pos in self._positions.items():
            bar_data = self._prices.get((last_d, str(sym_s)))
            price_f = float(bar_data["close"]) if bar_data is not None else 0.0
            fx_rate_f = float(
                fx_to_base(sym_s.currency, self._config.base_currency, last_d, fx_lookup)
            )
            rows.append(
                {
                    "date": last_d,
                    "symbol": str(sym_s),
                    "shares": pos.shares,
                    "mkt_value_local": pos.shares * price_f,
                    "mkt_value_base": pos.shares * price_f * fx_rate_f,
                }
            )
        return rows
