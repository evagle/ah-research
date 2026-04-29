"""Data carriers for the backtest engine."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ah_research.model.schemas import SignalsSchema, WeightsSchema


@dataclass(frozen=True)
class Signals:
    """Validated per-symbol signal frame."""

    df: pd.DataFrame

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> Signals:
        """Validate ``df`` against SignalsSchema and wrap it."""
        validated = SignalsSchema.validate(df)
        return cls(df=validated)


@dataclass(frozen=True)
class Weights:
    """Validated per-symbol target-weight frame."""

    df: pd.DataFrame

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> Weights:
        """Validate ``df`` against WeightsSchema and wrap it."""
        validated = WeightsSchema.validate(df)
        return cls(df=validated)
