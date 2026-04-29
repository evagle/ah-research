"""Transaction-cost model: per-exchange, asymmetric, 2024 baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ah_research.model.types import Exchange, OrderSide


@dataclass(frozen=True)
class CostModel:
    """Per-exchange transaction cost parameters."""

    exchange: Exchange
    commission_bps: float
    commission_min_local: Decimal
    stamp_buy_bps: float
    stamp_sell_bps: float
    transfer_bps: float
    exchange_fee_bps: float
    slippage_bps: float
    valid_from: date | None = None

    def compute(self, side: OrderSide, notional_local: Decimal) -> dict[str, Decimal]:
        """Compute cost breakdown for a trade of ``notional_local`` on ``side``."""
        bps = Decimal("10000")
        commission_raw = notional_local * Decimal(str(self.commission_bps)) / bps
        commission = max(commission_raw, self.commission_min_local)
        if side in ("buy", "cover"):
            stamp = notional_local * Decimal(str(self.stamp_buy_bps)) / bps
        else:
            stamp = notional_local * Decimal(str(self.stamp_sell_bps)) / bps
        transfer = notional_local * Decimal(str(self.transfer_bps)) / bps
        exchange_fee = notional_local * Decimal(str(self.exchange_fee_bps)) / bps
        return {
            "commission": commission,
            "stamp": stamp,
            "transfer": transfer,
            "exchange_fee": exchange_fee,
        }


@dataclass(frozen=True)
class CostModelBundle:
    """Collection of per-exchange cost models."""

    models: dict[Exchange, CostModel]

    def for_exchange(self, exchange: Exchange) -> CostModel:
        """Return the CostModel for ``exchange``."""
        return self.models[exchange]


DEFAULT_COSTS_2024 = CostModelBundle(
    models={
        Exchange.SH: CostModel(
            exchange=Exchange.SH,
            commission_bps=2.5,
            commission_min_local=Decimal("5"),
            stamp_buy_bps=0,
            stamp_sell_bps=5,
            transfer_bps=0.1,
            exchange_fee_bps=0.341,
            slippage_bps=5,
        ),
        Exchange.SZ: CostModel(
            exchange=Exchange.SZ,
            commission_bps=2.5,
            commission_min_local=Decimal("5"),
            stamp_buy_bps=0,
            stamp_sell_bps=5,
            transfer_bps=0.1,
            exchange_fee_bps=0.341,
            slippage_bps=5,
        ),
        Exchange.HK: CostModel(
            exchange=Exchange.HK,
            commission_bps=20,
            commission_min_local=Decimal("50"),
            stamp_buy_bps=10,
            stamp_sell_bps=10,
            transfer_bps=2.65,
            exchange_fee_bps=0.565,
            slippage_bps=10,
        ),
    }
)
