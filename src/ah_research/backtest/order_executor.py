"""OrderExecutor — first carved-out collaborator from ``run_backtest``.

This module extracts the *pre-execution* concerns from the backtest engine's
order loop:

1. Validation against today's bar (no_price_bar, suspended, limit_up,
   limit_down, T+N lock, A-share short disallowed).
2. Dividend-reinvestment sentinel resolution (``Order(shares=-1)``).
3. Fill-price selection (``next_open`` / ``next_vwap`` / ``next_close``).
4. Slippage application (in basis points, signed by side).
5. Notional + cost computation via the cost model.

The result is a ``FillAttempt`` discriminated union: either ``PricedFill``
(ready to apply to positions + cash) or ``OrderRejection`` (rejection record
plus a ``retry`` flag for transient blockers).

What this module **does not** own (still in engine.py, will move in later
C1-stack PRs):

* The cash-sufficiency check + iterative lot reduction (``CashLedger`` —
  C1-03).
* The position / cash mutation that actually applies the fill.
* The pending-order queue, rejected-order log, and trade log.

Behaviour-preserving extraction. No public API change to ``run_backtest``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from ah_research.backtest.costs import CostModelBundle
from ah_research.backtest.types import BacktestConfig, Order, Position
from ah_research.model.types import Exchange, OrderSide, Symbol

# Lot sizes (shares per board lot). Re-imported from engine.py for the
# dividend-reinvestment sentinel resolution; engine.py keeps its own copy
# until ``CashLedger`` consumes the module-level constants.
_LOT_SIZE: dict[Exchange, int] = {
    Exchange.SH: 100,
    Exchange.SZ: 100,
    Exchange.HK: 100,
}


RejectionReason = Literal[
    "no_price_bar",
    "suspended",
    "limit_up",
    "limit_down",
    "T+N lock",
    "a_share_short_disallowed",
]


@dataclass(frozen=True)
class OrderRejection:
    """A pre-execution rejection. ``retry`` indicates the engine should
    re-queue the order for the next trading day (transient blockers like
    suspension or limit moves)."""

    order: Order
    reason: RejectionReason
    retry: bool


@dataclass(frozen=True)
class PricedFill:
    """A validated + priced fill, ready for the cash-sufficiency / position-
    mutation stage. ``shares`` may differ from ``order.shares`` only via the
    dividend-reinvestment sentinel (``Order(shares=-1)`` resolves to a real
    share count from the earmark)."""

    order: Order
    shares: int
    fill_price: Decimal
    notional_local: Decimal
    cost_total: Decimal
    cost_breakdown: dict[str, Decimal]


FillAttempt = PricedFill | OrderRejection


@dataclass(frozen=True)
class _DividendSkip:
    """Internal sentinel: the dividend-reinvestment order resolves to zero
    shares (no earmark, or zero base price). Engine treats it as a silent
    no-op (``continue``), distinct from a logged rejection."""


def _resolve_dividend_shares(
    order: Order,
    base_price: float,
    dividend_earmarks: dict[Symbol, Decimal],
) -> int | _DividendSkip:
    """Resolve a dividend-reinvestment sentinel order (``shares == -1``)
    into a real share count. Returns ``_DividendSkip`` if there's nothing
    to reinvest."""
    earmarked = dividend_earmarks.pop(order.symbol, Decimal("0"))
    if earmarked <= 0 or base_price <= 0:
        return _DividendSkip()
    lot = _LOT_SIZE[order.symbol.exchange]
    shares = _round_to_lot(float(earmarked) / base_price, lot, is_buy=True)
    if shares <= 0:
        return _DividendSkip()
    return shares


def _round_to_lot(target_shares: float, lot_size: int, is_buy: bool) -> int:
    """Round ``target_shares`` down to a multiple of ``lot_size`` for buys,
    up for sells. Mirrors engine._round_to_lot."""
    if target_shares <= 0:
        return 0
    lots = int(target_shares // lot_size) if is_buy else -(-int(target_shares) // lot_size)
    return lots * lot_size


def _select_base_price(bar: Any, fill_price_mode: str) -> float:
    """Pick the base fill price from the bar according to config.fill_price."""
    open_price = float(bar["open"])
    vwap = float(bar["amount"]) / float(bar["volume"]) if float(bar["volume"]) > 0 else open_price
    close_price = float(bar["close"])
    base_price_map = {
        "next_open": open_price,
        "next_vwap": vwap,
        "next_close": close_price,
    }
    return base_price_map.get(fill_price_mode, open_price)


def _slippage_signed_price(
    base_price: float,
    side: OrderSide,
    cost_model: CostModelBundle,
    exchange: Exchange,
) -> Decimal:
    """Apply directional slippage to the base price."""
    try:
        slippage_bps = cost_model.for_exchange(exchange).slippage_bps
    except (KeyError, AttributeError):
        slippage_bps = 0.0
    slip = slippage_bps / 1e4
    sign = 1 if side in ("buy", "cover") else -1
    return Decimal(str(base_price * (1 + sign * slip)))


def _compute_costs(
    cost_model: CostModelBundle,
    exchange: Exchange,
    side: OrderSide,
    notional_local: Decimal,
) -> tuple[Decimal, dict[str, Decimal]]:
    """Compute total cost + breakdown via the cost model, with the same
    silent-fallback semantics engine.py uses today (missing model =>
    zero cost). Note: this preserves *exact* current behaviour."""
    try:
        breakdown = cost_model.for_exchange(exchange).compute(side, notional_local)
        # Explicit Decimal start so the sum type is Decimal, not Decimal | int.
        total = sum(breakdown.values(), Decimal("0"))
    except (KeyError, AttributeError):
        breakdown = {}
        total = Decimal("0")
    return total, breakdown


class OrderExecutor:
    """Stateless pre-execution decider.

    Owns rules 1-5 (validate, resolve dividend sentinel, price, slip, cost).
    Has no mutable state; all state (positions, cash, dividend earmarks) is
    passed in per call by the engine. This makes it trivially testable in
    isolation in later C1-stack PRs.
    """

    def __init__(self, cost_model: CostModelBundle) -> None:
        self._cost_model = cost_model

    def attempt_fill(
        self,
        *,
        order: Order,
        bar: Any,
        position: Position | None,
        config: BacktestConfig,
        dividend_earmarks: dict[Symbol, Decimal],
        d: date,
    ) -> FillAttempt | None:
        """Return a ``PricedFill`` (proceed) or an ``OrderRejection``.

        Returns ``None`` only for the dividend-reinvestment no-op case
        where the engine should silently ``continue`` the loop without
        logging anything (matches engine.py current behaviour).
        """
        # 1. No price bar today -> reject (no retry; engine drops the order).
        if bar is None:
            return OrderRejection(order=order, reason="no_price_bar", retry=False)

        is_suspended = bool(bar["is_suspended"])
        hit_limit_up = bool(bar["hit_limit_up"])
        hit_limit_down = bool(bar["hit_limit_down"])

        # 2. Suspended -> retry tomorrow.
        if is_suspended:
            return OrderRejection(order=order, reason="suspended", retry=True)

        # 3. Limit-up blocks buys.
        if order.side in ("buy", "cover") and hit_limit_up:
            return OrderRejection(order=order, reason="limit_up", retry=True)

        # 4. Limit-down blocks sells/shorts.
        if order.side in ("sell", "short") and hit_limit_down:
            return OrderRejection(order=order, reason="limit_down", retry=True)

        # 5. T+N lock blocks sells/covers; do NOT re-queue (real constraint).
        if (
            order.side in ("sell", "cover")
            and position is not None
            and position.locked_until is not None
            and d <= position.locked_until
        ):
            return OrderRejection(order=order, reason="T+N lock", retry=False)

        # 6. A-share short disallowed by default.
        if (
            order.side == "short"
            and order.symbol.exchange in (Exchange.SH, Exchange.SZ)
            and not config.a_share_short_allowed
        ):
            return OrderRejection(order=order, reason="a_share_short_disallowed", retry=False)

        # 7. Pricing: base + slip.
        base_price = _select_base_price(bar, config.fill_price)
        fill_price = _slippage_signed_price(
            base_price=base_price,
            side=order.side,
            cost_model=self._cost_model,
            exchange=order.symbol.exchange,
        )

        # 8. Dividend-reinvestment sentinel resolution.
        if order.shares == -1:
            resolved = _resolve_dividend_shares(order, base_price, dividend_earmarks)
            if isinstance(resolved, _DividendSkip):
                return None  # engine silently skips
            shares = resolved
        else:
            shares = order.shares

        # 9. Notional + cost.
        notional_local = fill_price * Decimal(str(shares))
        cost_total, cost_breakdown = _compute_costs(
            cost_model=self._cost_model,
            exchange=order.symbol.exchange,
            side=order.side,
            notional_local=notional_local,
        )

        return PricedFill(
            order=order,
            shares=shares,
            fill_price=fill_price,
            notional_local=notional_local,
            cost_total=cost_total,
            cost_breakdown=cost_breakdown,
        )
