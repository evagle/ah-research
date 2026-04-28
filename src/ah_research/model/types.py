"""Pure domain types. No I/O, no pandas, no integrations.

These types define the vocabulary the rest of the system speaks. They are
deliberately frozen (immutable + hashable) so they can be safely passed
across threads, used as dict keys, and cached.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Literal, get_args

from ah_research.exceptions import UserInputError


class Exchange(StrEnum):
    """Supported listing venues. Unknown exchanges raise at parse time."""

    SH = "SH"  # Shanghai
    SZ = "SZ"  # Shenzhen
    HK = "HK"  # Hong Kong


class Currency(StrEnum):
    """Settlement / price currency for each venue."""

    CNY = "CNY"
    HKD = "HKD"


class Freq(StrEnum):
    """Resampling frequency for price / fundamentals time series."""

    D = "D"  # daily
    W = "W"  # weekly (Friday close)
    M = "M"  # monthly (month-end close)
    Q = "Q"  # quarterly (quarter-end close)


# ── Literal narrow types ─────────────────────────────────────────────────────

Adjust = Literal["hfq", "qfq", "none"]
"""Price-adjustment mode.

- ``hfq``: back-adjusted (historically-adjusted). DEFAULT for research; most
  recent price unchanged, earlier prices scaled down for splits/dividends.
- ``qfq``: forward-adjusted (前复权). Never use for back-testing — introduces
  look-ahead bias as new corporate actions rewrite history.
- ``none``: raw close as printed by the exchange.
"""

PriceKind = Literal["total_return", "price_only"]
"""Whether dividends are reinvested in the returned series."""

StatementKind = Literal["preliminary", "audited", "restated", "auto"]
"""Fundamental report kind. ``auto`` resolves to audited when available,
preliminary otherwise."""

FillPrice = Literal["next_open", "next_vwap", "next_close"]
"""Execution price model for a simulated fill."""

Settlement = Literal["auto", "T+1", "T+2", "T+0"]
"""Settlement convention. ``auto`` picks from venue (A-share T+1, HK T+2)."""

CorporateActionKind = Literal[
    "cash_dividend",
    "stock_dividend",
    "split",
    "reverse_split",
    "rights_issue",
    "spin_off",
]

_CORPORATE_ACTION_KINDS: frozenset[str] = frozenset(get_args(CorporateActionKind))


# ── Symbol parsing ───────────────────────────────────────────────────────────

_SYMBOL_RE = re.compile(r"^([A-Z0-9]+)\.(SH|SZ|HK)$")
_CURRENCY_FOR_EXCHANGE: dict[Exchange, Currency] = {
    Exchange.SH: Currency.CNY,
    Exchange.SZ: Currency.CNY,
    Exchange.HK: Currency.HKD,
}


@dataclass(frozen=True, slots=True)
class Symbol:
    """A single security identifier.

    The canonical string form is ``<code>.<exchange>`` (e.g., ``600519.SH``,
    ``0700.HK``). Construct via ``parse_symbol`` — direct construction
    bypasses venue validation.
    """

    code: str
    exchange: Exchange
    currency: Currency

    def __str__(self) -> str:
        return f"{self.code}.{self.exchange.value}"


def parse_symbol(s: str) -> Symbol:
    """Parse ``<code>.<exchange>`` format.

    Raises:
        UserInputError: if input is empty, malformed, or references an
            unsupported exchange.
    """
    if not s:
        raise UserInputError("empty symbol; expected format like '600519.SH' or '0700.HK'")
    match = _SYMBOL_RE.match(s)
    if not match:
        raise UserInputError(f"invalid symbol {s!r}; expected format like '600519.SH' or '0700.HK'")
    code, exchange_code = match.group(1), match.group(2)
    exchange = Exchange(exchange_code)
    return Symbol(code=code, exchange=exchange, currency=_CURRENCY_FOR_EXCHANGE[exchange])


# ── Composite domain objects ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AHPair:
    """A dual-listing pair: one A-share leg (SH or SZ) and one H-share leg (HK).

    Curated in ``src/ah_research/data/ah_pairs.yaml``. Used by the AH-premium
    module to align trading calendars and FX.
    """

    a_symbol: Symbol
    h_symbol: Symbol
    name_en: str
    name_zh: str

    def __post_init__(self) -> None:
        if self.a_symbol.exchange == Exchange.HK:
            raise UserInputError(f"AHPair.a_symbol must be SH or SZ, got {self.a_symbol}")
        if self.h_symbol.exchange != Exchange.HK:
            raise UserInputError(f"AHPair.h_symbol must be HK, got {self.h_symbol}")


@dataclass(frozen=True, slots=True)
class IndexConstituent:
    """A single point-in-time (PIT) membership row.

    ``effective_to=None`` means the membership is open-ended (current member).
    A PIT query at date ``D`` includes this row iff
    ``effective_from <= D < effective_to`` (open-ended if ``None``).
    """

    index: str
    symbol: Symbol
    weight: float | None
    effective_from: date
    effective_to: date | None

    def __post_init__(self) -> None:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise UserInputError(
                f"IndexConstituent.effective_to ({self.effective_to}) "
                f"must be after effective_from ({self.effective_from})"
            )


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """A single corporate action event, anchored on its ex-date.

    ``params`` holds kind-specific payload:

    - cash_dividend: ``{"amount_per_share": float, "currency": str}``
    - stock_dividend: ``{"ratio": float}`` (e.g., 0.1 = 10-for-100)
    - split: ``{"ratio": float}`` (e.g., 2.0 = 2-for-1)
    - rights_issue: ``{"price": float, "ratio": float}``

    The dict is not frozen because Python's ``dataclass(frozen=True)``
    doesn't recursively freeze values — but the outer object is immutable
    enough for our PIT semantics. Downstream code must not mutate
    ``params`` in place.
    """

    symbol: Symbol
    ex_date: date
    kind: CorporateActionKind
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in _CORPORATE_ACTION_KINDS:
            raise UserInputError(
                f"CorporateAction.kind {self.kind!r} is not one of "
                f"{sorted(_CORPORATE_ACTION_KINDS)}"
            )
