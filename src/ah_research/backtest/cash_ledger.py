"""CashLedger — second carved-out collaborator from ``run_backtest``.

This module owns the *post-validation* concerns of the engine's order loop
(everything that needs the live cash + positions books):

1. The cash-sufficiency check + iterative lot reduction (back-solve).
   The cost model is not flat-rate (commission has a fixed minimum), so a
   pure ``cash / price`` division can still overdraw once costs are added
   back in -- requires walking lot-by-lot until ``notional + cost <= cash``.
2. The position dict mutation (avg-cost weighted update for buys, share
   decrement for sells, short-open path with no-prior-position).
3. The cash dict mutation (debit/credit + cross-currency shortfall
   conversion when a buy in a non-base currency drains the local balance).
4. The T+N settlement-day stamp on freshly-opened long positions.

What this module does *not* own (still in engine.py for now):

* The trade-log append + cash-negative guard. Those are integration-level
  concerns that move alongside ``MTMAccumulator`` later in the C1 stack.
* The pending-order queue, rebalance scheduling, corporate actions.

Behaviour-preserving extraction. No public API change to ``run_backtest``;
characterization fixtures pinned in #22 must remain byte-identical.

Shared helpers (``_LOT_SIZE``, ``_SETTLEMENT_DAYS``, ``next_n_trading_days``,
``cash_in_base``, ``fx_to_base``) live here too -- engine.py imports them
back. This is a one-direction dependency (engine -> cash_ledger), no cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any

from ah_research.backtest.costs import CostModelBundle
from ah_research.backtest.order_executor import PricedFill
from ah_research.backtest.types import BacktestConfig, Position
from ah_research.model.types import Currency, Exchange, OrderSide, Symbol

# ---------------------------------------------------------------------------
# Constants (single source of truth for engine.py + this module)
# ---------------------------------------------------------------------------

_LOT_SIZE: dict[Exchange, int] = {
    Exchange.SH: 100,
    Exchange.SZ: 100,
    Exchange.HK: 100,  # Phase 2 simplification; warning logged at engine start
}

_SETTLEMENT_DAYS: dict[Exchange, int] = {
    Exchange.SH: 1,
    Exchange.SZ: 1,
    Exchange.HK: 2,
}


# ---------------------------------------------------------------------------
# Pure helpers (used by engine.py too)
# ---------------------------------------------------------------------------


def fx_to_base(
    ccy: Currency,
    base_ccy: Currency,
    d: date,
    fx_lookup: dict[date, float],
) -> Decimal:
    """Return exchange rate to convert ``ccy`` -> ``base_ccy`` on date ``d``.

    ``fx_lookup`` is the engine's CNY_HKD rate map (1 CNY = X HKD). The
    function inverts it for HKD -> CNY conversion. Falls back to the nearest
    available past date if ``d`` itself is missing from the map.
    """
    if ccy == base_ccy:
        return Decimal("1")
    if ccy == Currency.HKD and base_ccy == Currency.CNY:
        rate = fx_lookup.get(d)
        if rate is None:
            dates = sorted(fx_lookup.keys())
            past = [x for x in dates if x <= d]
            rate = fx_lookup[past[-1]] if past else next(iter(fx_lookup.values()))
        return Decimal("1") / Decimal(str(rate))
    if ccy == Currency.CNY and base_ccy == Currency.HKD:
        rate = fx_lookup.get(d)
        if rate is None:
            dates = sorted(fx_lookup.keys())
            past = [x for x in dates if x <= d]
            rate = fx_lookup[past[-1]] if past else next(iter(fx_lookup.values()))
        return Decimal(str(rate))
    return Decimal("1")


def cash_in_base(
    cash: dict[Currency, Decimal],
    base_ccy: Currency,
    d: date,
    fx_lookup: dict[date, float],
) -> Decimal:
    """Convert all cash balances to base currency."""
    total = Decimal("0")
    for ccy, bal in cash.items():
        total += bal * fx_to_base(ccy, base_ccy, d, fx_lookup)
    return total


def next_n_trading_days(trading_days: list[date], from_date: date, n: int) -> date:
    """Return the date that is ``n`` trading days after ``from_date``."""
    future = [d for d in trading_days if d > from_date]
    if len(future) >= n:
        return future[n - 1]
    return future[-1] if future else from_date


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FillApplication:
    """The values the engine needs for the trade log after the ledger has
    applied a fill.

    ``shares`` / ``notional_local`` / ``cost_total`` may differ from the
    incoming ``PricedFill`` if the cash-back-solve had to reduce the order;
    ``fill_price`` does not change.

    ``skipped`` is ``True`` only when the back-solve determined that even
    one lot is unaffordable (the engine ``continue``s the loop without
    recording a trade).
    """

    shares: int
    fill_price: Decimal
    notional_local: Decimal
    cost_total: Decimal
    skipped: bool


# ---------------------------------------------------------------------------
# CashLedger
# ---------------------------------------------------------------------------


class CashLedger:
    """Owns the live ``positions`` and ``cash`` dicts and the rules that
    mutate them after a ``PricedFill`` has been validated.

    Holds the dicts by reference so engine.py and the ledger always observe
    the same state -- this preserves today's invariant where MTM and the
    cash-negative guard see whatever the most recent fill did.
    """

    def __init__(
        self,
        *,
        positions: dict[Symbol, Position],
        cash: dict[Currency, Decimal],
        cost_model: CostModelBundle,
        config: BacktestConfig,
        sh_days: list[date],
        hk_days: list[date],
        logger: Any,
    ) -> None:
        self._positions = positions
        self._cash = cash
        self._cost_model = cost_model
        self._config = config
        self._sh_days = sh_days
        self._hk_days = hk_days
        self._logger = logger

    # -- public API ---------------------------------------------------------

    def apply_fill(
        self,
        *,
        fill: PricedFill,
        d: date,
        fx_lookup: dict[date, float],
    ) -> FillApplication:
        """Apply a validated fill to the books.

        Branches on order side (buy/cover vs sell/short) since the cash-
        check + position-mutation rules differ. For buys, may reduce
        ``shares`` via the iterative lot back-solve.
        """
        order = fill.order
        sym = order.symbol
        ccy = sym.currency

        if order.side in ("buy", "cover"):
            return self._apply_buy_or_cover(fill=fill, d=d, ccy=ccy, fx_lookup=fx_lookup)
        # ``sell`` or ``short``
        return self._apply_sell_or_short(fill=fill, ccy=ccy)

    # -- buy / cover -------------------------------------------------------

    def _apply_buy_or_cover(
        self,
        *,
        fill: PricedFill,
        d: date,
        ccy: Currency,
        fx_lookup: dict[date, float],
    ) -> FillApplication:
        order = fill.order
        sym = order.symbol
        exchange_obj = sym.exchange

        # 1. Cash-sufficiency check (with iterative back-solve if short).
        check = self._check_cash_or_reduce(
            fill=fill,
            d=d,
            ccy=ccy,
            fx_lookup=fx_lookup,
        )
        if check is None:
            # Cannot afford even one lot.
            return FillApplication(
                shares=0,
                fill_price=fill.fill_price,
                notional_local=Decimal("0"),
                cost_total=Decimal("0"),
                skipped=True,
            )
        shares, notional_local, cost_total = check

        # 2. Position update with weighted-average cost.
        pos = self._positions.get(sym)
        current_shares = pos.shares if pos is not None else 0
        new_shares = current_shares + shares
        if pos is not None:
            total_cost_basis = pos.avg_cost * Decimal(str(current_shares))
            new_avg_cost = (total_cost_basis + notional_local) / Decimal(str(new_shares))
        else:
            new_avg_cost = fill.fill_price

        locked_until = self._resolve_locked_until(exchange_obj, d)

        self._positions[sym] = Position(
            symbol=sym,
            shares=new_shares,
            avg_cost=new_avg_cost,
            locked_until=locked_until,
        )

        # 3. Debit cash; convert any non-base shortfall back to base.
        self._cash[ccy] = self._cash.get(ccy, Decimal("0")) - notional_local - cost_total
        if self._cash[ccy] < Decimal("0") and ccy != self._config.base_currency:
            shortfall_local = -self._cash[ccy]
            shortfall_base = shortfall_local * fx_to_base(
                ccy, self._config.base_currency, d, fx_lookup
            )
            base = self._config.base_currency
            self._cash[base] = self._cash.get(base, Decimal("0")) - shortfall_base
            self._cash[ccy] = Decimal("0")

        return FillApplication(
            shares=shares,
            fill_price=fill.fill_price,
            notional_local=notional_local,
            cost_total=cost_total,
            skipped=False,
        )

    # -- sell / short ------------------------------------------------------

    def _apply_sell_or_short(
        self,
        *,
        fill: PricedFill,
        ccy: Currency,
    ) -> FillApplication:
        order = fill.order
        sym = order.symbol
        shares = fill.shares
        pos = self._positions.get(sym)
        current_shares = pos.shares if pos is not None else 0
        new_shares = current_shares - shares
        if new_shares == 0:
            self._positions.pop(sym, None)
        elif pos is not None:
            self._positions[sym] = replace(pos, shares=new_shares)
        else:
            # Short opening: no prior position
            self._positions[sym] = Position(
                symbol=sym,
                shares=-shares,
                avg_cost=fill.fill_price,
                locked_until=None,
            )
        # Credit cash: notional - costs
        self._cash[ccy] = self._cash.get(ccy, Decimal("0")) + fill.notional_local - fill.cost_total
        return FillApplication(
            shares=shares,
            fill_price=fill.fill_price,
            notional_local=fill.notional_local,
            cost_total=fill.cost_total,
            skipped=False,
        )

    # -- cash back-solve ---------------------------------------------------

    def _check_cash_or_reduce(
        self,
        *,
        fill: PricedFill,
        d: date,
        ccy: Currency,
        fx_lookup: dict[date, float],
    ) -> tuple[int, Decimal, Decimal] | None:
        """Return ``(shares, notional_local, cost_total)`` after applying
        the cash-sufficiency rule. Returns ``None`` if even one lot is
        unaffordable.

        The iterative reduction is necessary because the cost model is not
        flat-rate -- A-share commission has a 5 CNY minimum, so a pure
        ``cash / price`` division can overdraw once costs are re-added.
        """
        order = fill.order
        sym = order.symbol
        sym_str = str(sym)
        exchange_obj = sym.exchange
        shares = fill.shares
        notional_local = fill.notional_local
        cost_total = fill.cost_total
        fill_price = fill.fill_price

        total_cash_base = cash_in_base(self._cash, self._config.base_currency, d, fx_lookup)
        fx_rate_local_to_base = fx_to_base(ccy, self._config.base_currency, d, fx_lookup)
        notional_base = notional_local * fx_rate_local_to_base
        cost_base = cost_total * fx_rate_local_to_base

        if notional_base + cost_base <= total_cash_base:
            return shares, notional_local, cost_total

        # Reduce.
        lot = _LOT_SIZE[exchange_obj]
        price_base = fill_price * fx_rate_local_to_base
        if not (price_base > Decimal("0") and total_cash_base > Decimal("0")):
            return None

        max_affordable_base = int(float(total_cash_base) / float(price_base))
        max_lots = (max_affordable_base // lot) * lot
        trial_notional_local = fill_price * Decimal(str(max_lots))
        trial_cost_total = self._compute_cost_total(exchange_obj, order.side, trial_notional_local)
        while max_lots > 0:
            trial_notional_base = trial_notional_local * fx_rate_local_to_base
            trial_cost_base = trial_cost_total * fx_rate_local_to_base
            if trial_notional_base + trial_cost_base <= total_cash_base:
                break
            max_lots -= lot
            if max_lots <= 0:
                break
            trial_notional_local = fill_price * Decimal(str(max_lots))
            trial_cost_total = self._compute_cost_total(
                exchange_obj, order.side, trial_notional_local
            )

        if max_lots <= 0:
            self._logger.warning(
                "Insufficient cash (%.2f base) to buy any lots of %s at %.4f; skipping order.",
                float(total_cash_base),
                sym_str,
                float(fill_price),
            )
            return None

        self._logger.warning(
            "Insufficient cash (%.2f base) for %d shares of %s at %.4f; reducing to %d shares.",
            float(total_cash_base),
            shares,
            sym_str,
            float(fill_price),
            max_lots,
        )
        return max_lots, trial_notional_local, trial_cost_total

    def _compute_cost_total(
        self, exchange: Exchange, side: OrderSide, notional_local: Decimal
    ) -> Decimal:
        """Same silent-fallback semantics engine.py + OrderExecutor use:
        missing model => zero cost. Preserves exact current behaviour."""
        try:
            breakdown = self._cost_model.for_exchange(exchange).compute(side, notional_local)
            return sum(breakdown.values(), Decimal("0"))
        except (KeyError, AttributeError):
            return Decimal("0")

    # -- T+N -------------------------------------------------------------

    def _resolve_locked_until(self, exchange: Exchange, d: date) -> date | None:
        """Return the lock-expiry date for a freshly-opened long, per the
        configured settlement convention."""
        settlement = self._config.settlement
        if settlement == "auto":
            n_days = _SETTLEMENT_DAYS[exchange]
        elif settlement == "T+1":
            n_days = 1
        elif settlement == "T+2":
            n_days = 2
        else:
            n_days = 0

        if n_days <= 0:
            return None
        exch_days = self._sh_days if exchange in (Exchange.SH, Exchange.SZ) else self._hk_days
        return next_n_trading_days(exch_days, d, n_days)
