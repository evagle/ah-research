"""Strategy Protocols — SignalStrategy (factor) and WeightStrategy (pair/direct)."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ah_research.backtest.types import Signals, Weights
from ah_research.data.repository import DataRepository


@runtime_checkable
class SignalStrategy(Protocol):
    """Emits a per-symbol scalar signal; converted to weights via ``to_weights``."""

    name: str

    def generate(self, repo: DataRepository, start: date, end: date) -> Signals:
        """Generate signals for all universe members over ``[start, end]``."""
        ...

    def to_weights(self, signals: Signals) -> Weights:
        """Convert signals to target portfolio weights."""
        ...


@runtime_checkable
class WeightStrategy(Protocol):
    """Emits target weights directly, without an intermediate signal step."""

    name: str

    def generate(self, repo: DataRepository, start: date, end: date) -> Weights:
        """Generate target weights for all universe members over ``[start, end]``."""
        ...
