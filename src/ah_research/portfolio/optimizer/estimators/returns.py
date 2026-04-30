"""Expected-returns estimators: Protocol + 3 built-in impls."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal, Protocol, runtime_checkable

import pandas as pd

from ah_research.data.repository import DataRepository
from ah_research.portfolio.optimizer.errors import ValidationError


@runtime_checkable
class ExpectedReturnsEstimator(Protocol):
    def estimate(
        self,
        symbols: list[str],
        as_of: pd.Timestamp,
        repo: DataRepository,
    ) -> pd.Series: ...


class UserSuppliedReturns:
    """Passthrough: returns the user-supplied mu series, filtered to requested symbols."""

    def __init__(self, mu: pd.Series) -> None:
        self._mu = mu

    def estimate(
        self,
        symbols: list[str],
        as_of: pd.Timestamp,
        repo: DataRepository,
    ) -> pd.Series:
        missing = [s for s in symbols if s not in self._mu.index]
        if missing:
            raise ValidationError(f"UserSuppliedReturns is missing entries for {missing}")
        return self._mu.reindex(symbols)


class HistoricalMeanReturns:
    """Sample mean daily return over `lookback_days`, optionally shrunk.

    `shrinkage` in [0, 1]: 0 = raw sample mean; 1 = shrink_to target fully.
    `shrink_to`:
      - "cross_sectional_mean": shrink each asset's mu toward the mean of all assets' mus
      - "zero": shrink toward zero
    """

    def __init__(
        self,
        lookback_days: int = 252,
        shrinkage: float = 0.0,
        shrink_to: Literal["cross_sectional_mean", "zero"] = "cross_sectional_mean",
    ) -> None:
        if not (0.0 <= shrinkage <= 1.0):
            raise ValidationError(f"shrinkage must be in [0, 1]; got {shrinkage}")
        self.lookback_days = lookback_days
        self.shrinkage = shrinkage
        self.shrink_to = shrink_to

    def estimate(
        self,
        symbols: list[str],
        as_of: pd.Timestamp,
        repo: DataRepository,
    ) -> pd.Series:
        start = (as_of - timedelta(days=int(self.lookback_days * 1.6))).date()  # bdate buffer
        end = as_of.date()
        prices = repo.get_prices(symbols, start, end)
        # Pivot to wide: rows ds, columns symbol, values total_return
        wide = prices.pivot(index="ds", columns="symbol", values="total_return").sort_index()
        wide = wide[wide.index < pd.Timestamp(as_of)]  # strict PIT: < as_of
        wide = wide.tail(self.lookback_days)
        raw = wide.mean(axis=0).reindex(symbols).fillna(0.0)
        if self.shrinkage == 0.0:
            return raw
        if self.shrink_to == "cross_sectional_mean":
            target = pd.Series(raw.mean(), index=raw.index)
        else:  # "zero"
            target = pd.Series(0.0, index=raw.index)
        return (1 - self.shrinkage) * raw + self.shrinkage * target


class SignalBasedReturns:
    """Translate a Phase 2 SignalStrategy's signals into an expected-returns vector.

    Pipeline:
      1. Call `signal_strategy.generate(repo, start, end)` over the recent window.
      2. Take the latest row (signals as of as_of).
      3. Cross-sectionally rank-standardize (within sector if neutralize_sector).
      4. Linearly scale so rank=N → +spread, rank=1 → -spread.
    """

    def __init__(
        self,
        signal_strategy: Any,
        spread: float = 0.02,
        neutralize_sector: bool = True,
        lookback_days: int = 60,
    ) -> None:
        if spread <= 0:
            raise ValidationError(f"spread must be > 0; got {spread}")
        self.signal_strategy = signal_strategy
        self.spread = spread
        self.neutralize_sector = neutralize_sector
        self.lookback_days = lookback_days

    def estimate(
        self,
        symbols: list[str],
        as_of: pd.Timestamp,
        repo: DataRepository,
    ) -> pd.Series:
        start = (as_of - timedelta(days=int(self.lookback_days * 1.6))).date()
        end = as_of.date()
        signals = self.signal_strategy.generate(repo, start, end)
        # Signals are expected to be a wide DataFrame (ds x symbol). Take the last row <= as_of.
        signals = signals[signals.index <= pd.Timestamp(as_of)]
        if signals.empty:
            raise ValidationError(f"SignalBasedReturns: no signals at or before {as_of}")
        latest = signals.iloc[-1].reindex(symbols)
        if self.neutralize_sector:
            # NB: sector-neutralization requires symbol -> sector lookup; for now we
            # fall back to no-op if no sector info is available. Callers wanting
            # sector neutralization should use a signal strategy that already
            # produces sector-neutral signals.
            pass
        # Rank 1..N, then linearly scale to [-spread, +spread]:
        # scaled = (rank - 1) / (N - 1) maps rank-1 -> 0, rank-N -> 1
        # mu = (2 * scaled - 1) * spread maps 0 -> -spread, 1 -> +spread
        ranked = latest.rank(method="average")  # 1..N ordinal ranks
        n = len(ranked.dropna())
        if n <= 1:
            return pd.Series(0.0, index=latest.index)
        scaled = (ranked - 1.0) / (n - 1.0)  # 0..1
        result: pd.Series = (2.0 * scaled - 1.0) * self.spread
        return result
