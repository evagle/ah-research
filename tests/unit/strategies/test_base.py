"""Tests for SignalStrategy and WeightStrategy Protocols."""

from datetime import date

import pandas as pd

from ah_research.backtest.types import Signals, Weights
from ah_research.strategies.base import SignalStrategy, WeightStrategy


class DummySignalStrategy:
    """Minimal SignalStrategy implementation for protocol checks."""

    name = "dummy_signal"

    def generate(
        self,
        repo: object,
        start: date,
        end: date,
    ) -> Signals:
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-31"]),
                "symbol": ["600000.SH"],
                "signal": [1.0],
            }
        )
        return Signals.from_dataframe(df)

    def to_weights(self, signals: Signals) -> Weights:
        df = signals.df.copy()
        df["weight"] = 1.0
        df = df.drop(columns=["signal"])
        return Weights.from_dataframe(df)


class DummyWeightStrategy:
    """Minimal WeightStrategy implementation for protocol checks."""

    name = "dummy_weight"

    def generate(
        self,
        repo: object,
        start: date,
        end: date,
    ) -> Weights:
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-31"]),
                "symbol": ["600000.SH"],
                "weight": [0.5],
            }
        )
        return Weights.from_dataframe(df)


def test_signal_strategy_protocol() -> None:
    s = DummySignalStrategy()
    assert isinstance(s, SignalStrategy)
    assert not isinstance(s, WeightStrategy)


def test_weight_strategy_protocol() -> None:
    w = DummyWeightStrategy()
    assert isinstance(w, WeightStrategy)
    assert not isinstance(w, SignalStrategy)
