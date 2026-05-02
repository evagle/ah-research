"""Strategy Protocols — SignalStrategy (factor) and WeightStrategy (pair/direct)."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from ah_research.backtest.types import Signals, Weights
from ah_research.data.repository import DataRepository


@runtime_checkable
class SignalStrategy(Protocol):
    """Emits a per-symbol scalar signal; converted to weights via ``to_weights``.

    ``to_weights`` accepts an optional ``repo`` argument so implementations can
    fetch sector classifications (or other repo data) at weight-construction time.
    The engine always passes ``repo``; callers that do not need it may ignore the
    argument by accepting ``**kwargs`` or an explicit ``repo`` parameter.
    """

    name: str

    def generate(self, repo: DataRepository, start: date, end: date) -> Signals:
        """Generate signals for all universe members over ``[start, end]``."""
        ...

    def to_weights(self, signals: Signals, repo: DataRepository) -> Weights:
        """Convert signals to target portfolio weights.

        Args:
            signals: The signal frame produced by ``generate``.
            repo: The data repository; available for sector lookups etc.
        """
        ...


@runtime_checkable
class WeightStrategy(Protocol):
    """Emits target weights directly, without an intermediate signal step."""

    name: str

    def generate(self, repo: DataRepository, start: date, end: date) -> Weights:
        """Generate target weights for all universe members over ``[start, end]``."""
        ...


def resolve_weights(
    strategy: Any,
    repo: DataRepository,
    start: date,
    end: date,
) -> Weights:
    """Drive any strategy to a ``Weights`` frame, regardless of Protocol.

    Centralises the dispatch cascade previously duplicated in
    ``backtest/engine.py`` and ``backtest/verify.py``. Callers remain
    responsible for exception handling (validation errors, NaN weights).

    SignalStrategy is checked before WeightStrategy because a class may
    satisfy both Protocols at runtime; ``to_weights`` should win in that
    case.
    """
    if isinstance(strategy, SignalStrategy) and hasattr(strategy, "to_weights"):
        sigs = strategy.generate(repo, start, end)
        return strategy.to_weights(sigs, repo)
    if isinstance(strategy, WeightStrategy):
        return strategy.generate(repo, start, end)
    # Duck-typed fallback: generate() returns either Weights or Signals;
    # if the returned object already carries a weight column, treat it as
    # Weights, else feed it through to_weights().
    result_obj = strategy.generate(repo, start, end)
    if hasattr(result_obj, "df") and "weight" in result_obj.df.columns:
        return result_obj  # type: ignore[no-any-return]
    return strategy.to_weights(result_obj, repo)  # type: ignore[no-any-return]
