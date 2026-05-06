"""RebalanceScheduler — third carved-out collaborator from ``run_backtest``.

This module owns the *target-weights → orders* translation step of the
engine's daily loop:

1. Compute the rebalance-date schedule from the trading calendar
   (``compute_rebalance_dates``: keep the spec's last-day-of-period rule).
2. On a rebalance date, given today's target weights and the current
   positions/cash books, emit the list of new ``Order`` objects to queue
   for the next trading day's execution.

The translation has three pieces:

* NAV computation in base currency (cash_in_base + sum of MTM positions).
* Per-symbol target-share calculation (lot-rounded, signed by sign of
  weight; floor on buys, ceiling on sells).
* Diff vs current shares -> infer side (buy / sell / short / cover) and
  build the order; close any position not in the new target set.

What this module does *not* own:

* The ``run_backtest`` per-day dispatch (still in engine.py — it decides
  *whether* today is a rebalance date and calls into the scheduler).
* Cash mutation, position mutation, fill validation -- those are the
  ``CashLedger`` / ``OrderExecutor`` collaborators.

Behaviour-preserving extraction. Module-level helpers
(``_compute_rebalance_dates``, ``_round_to_lot``, ``_infer_side``) move
out of engine.py and are re-exported from this module so engine still
imports them by their original names.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any, Literal

import pandas as pd

from ah_research.backtest.cash_ledger import (
    _LOT_SIZE,
    cash_in_base,
    fx_to_base,
)
from ah_research.backtest.types import BacktestConfig, Order, Position, Weights
from ah_research.exceptions import UserInputError
from ah_research.model.types import Currency, Symbol, parse_symbol

# ---------------------------------------------------------------------------
# Pure helpers (used by engine.py too)
# ---------------------------------------------------------------------------


def compute_rebalance_dates(all_days: list[date], freq: str) -> list[date]:
    """Return the last trading day of each period (M/Q/W/D) in ``all_days``.

    Uses pandas Grouper with the equivalent end-of-period frequency
    ("ME"/"QE"/"W-FRI"/"D"). The last day of each non-empty group is
    selected. Falls back to "ME" for unknown freqs (preserves engine
    behaviour).
    """
    if not all_days:
        return []
    ts_index = pd.DatetimeIndex([pd.Timestamp(d) for d in all_days])
    s = pd.Series(ts_index, index=ts_index)

    pandas_freq = {"M": "ME", "Q": "QE", "W": "W-FRI", "D": "D"}.get(freq, "ME")

    rebalance_ts: list[date] = []
    for _period, group in s.groupby(pd.Grouper(freq=pandas_freq)):
        if len(group) > 0:
            last_day = group.index[-1].date()
            rebalance_ts.append(last_day)
    return rebalance_ts


def round_to_lot(target_shares: float, lot_size: int, is_buy: bool) -> int:
    """Round shares to the nearest lot. Floor on buys, ceiling on sells."""
    if lot_size <= 0:
        lot_size = 1
    lots = Decimal(str(target_shares)) / Decimal(str(lot_size))
    if is_buy:
        rounded_lots = int(lots.to_integral_value(rounding=ROUND_FLOOR))
    else:
        rounded_lots = int(lots.to_integral_value(rounding=ROUND_CEILING))
    return rounded_lots * lot_size


def infer_side(current_shares: int, target_shares: int) -> Literal["buy", "sell", "short", "cover"]:
    """Infer order side from the (current, target) share pair.

    The four legal transitions:
      * non-negative -> bigger non-negative -> buy
      * positive    -> smaller positive    -> sell
      * zero        -> negative           -> short
      * negative    -> less negative      -> cover
      * negative    -> more negative      -> short
    Anything else falls through to ``"sell"`` (preserves engine fallback).
    """
    if current_shares >= 0 and target_shares > current_shares:
        return "buy"
    if current_shares > 0 and target_shares < current_shares:
        return "sell"
    if current_shares == 0 and target_shares < 0:
        return "short"
    if current_shares < 0 and target_shares > current_shares:
        return "cover"
    if current_shares < 0 and target_shares < current_shares:
        return "short"
    return "sell"


# ---------------------------------------------------------------------------
# RebalanceScheduler
# ---------------------------------------------------------------------------


class RebalanceScheduler:
    """Translates a per-rebalance-date ``Weights`` frame into a list of
    ``Order`` objects, given the current books.

    Stateless beyond the immutable ``config`` reference — the engine
    still owns the *when* (``d in rebalance_dates``); this class owns the
    *what* (target weights -> diffs -> orders).
    """

    def __init__(self, *, config: BacktestConfig, logger: Any) -> None:
        self._config = config
        self._logger = logger

    # -- public API -------------------------------------------------------

    def compute_orders(
        self,
        *,
        d: date,
        weights: Weights,
        positions: dict[Symbol, Position],
        cash: dict[Currency, Decimal],
        prices_by_date_sym: dict[tuple[date, str], pd.Series],
        fx_lookup: dict[date, float],
    ) -> list[Order]:
        """Return the list of ``Order`` objects to queue on rebalance date ``d``.

        ``weights`` is the full ``Weights`` object emitted by the strategy
        for this rebalance date. The method:

        1. Filters to the rows for ``d`` (no-op if already filtered).
        2. Computes total NAV in base currency (cash + MTM positions).
        3. For each target symbol: computes lot-rounded target shares,
           diffs against current shares, infers side, appends an order.
        4. For each currently-held symbol *not* in the target set: emits
           a closing order (sell or cover).
        """
        date_mask = weights.df["date"].dt.date == d
        day_weights = weights.df[date_mask]
        if day_weights.empty:
            return []

        nav_base = self._compute_nav_base(
            d=d,
            positions=positions,
            cash=cash,
            prices_by_date_sym=prices_by_date_sym,
            fx_lookup=fx_lookup,
        )

        new_orders: list[Order] = []
        target_symbols: set[Symbol] = set()

        for _, wrow in day_weights.iterrows():
            sym_str = str(wrow["symbol"])
            target_w = float(wrow["weight"])

            try:
                sym_w = parse_symbol(sym_str)
            except UserInputError:
                self._logger.warning("Cannot parse symbol %r; skipping.", sym_str)
                continue

            target_symbols.add(sym_w)
            bar_data = prices_by_date_sym.get((d, sym_str))
            if bar_data is None:
                self._logger.warning(
                    "No price bar for %s on rebalance date %s; skipping.",
                    sym_str,
                    d,
                )
                continue

            price_local_f = float(bar_data["close"])
            if price_local_f <= 0:
                continue

            fx_rate_f = float(fx_to_base(sym_w.currency, self._config.base_currency, d, fx_lookup))
            if fx_rate_f <= 0:
                fx_rate_f = 1.0

            target_shares_raw = float(nav_base) * target_w / (price_local_f * fx_rate_f)
            lot = _LOT_SIZE[sym_w.exchange]
            is_buy = target_shares_raw >= 0
            target_shares = round_to_lot(abs(target_shares_raw), lot, is_buy=is_buy)
            if target_w < 0:
                target_shares = -target_shares

            current_pos = positions.get(sym_w)
            current_shares_val = current_pos.shares if current_pos is not None else 0
            diff = target_shares - current_shares_val

            if diff == 0:
                continue

            side = infer_side(current_shares_val, target_shares)
            new_orders.append(
                Order(
                    ready_date=d,
                    symbol=sym_w,
                    side=side,
                    shares=abs(diff),
                )
            )

        # Close positions not in the new target set.
        for sym_close in set(positions.keys()) - target_symbols:
            pos_close = positions[sym_close]
            if pos_close.shares == 0:
                continue
            close_side: Literal["sell", "cover"] = "sell" if pos_close.shares > 0 else "cover"
            new_orders.append(
                Order(
                    ready_date=d,
                    symbol=sym_close,
                    side=close_side,
                    shares=abs(pos_close.shares),
                )
            )

        return new_orders

    # -- helpers ----------------------------------------------------------

    def _compute_nav_base(
        self,
        *,
        d: date,
        positions: dict[Symbol, Position],
        cash: dict[Currency, Decimal],
        prices_by_date_sym: dict[tuple[date, str], pd.Series],
        fx_lookup: dict[date, float],
    ) -> Decimal:
        """Total portfolio value in base ccy, used as denominator for
        target-shares = NAV * weight / price.

        Uses ``abs(shares)`` for the position contribution, matching the
        original engine's computation here -- shorts are marked at gross
        notional for sizing purposes; the signed MTM happens later.
        """
        nav = cash_in_base(cash, self._config.base_currency, d, fx_lookup)
        for sym_s, pos in positions.items():
            bar_data = prices_by_date_sym.get((d, str(sym_s)))
            if bar_data is None:
                continue
            price_local = Decimal(str(float(bar_data["close"])))
            fx_rate = fx_to_base(sym_s.currency, self._config.base_currency, d, fx_lookup)
            nav += Decimal(str(abs(pos.shares))) * price_local * fx_rate
        return nav
