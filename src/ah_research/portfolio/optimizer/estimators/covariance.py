"""Covariance estimators: Protocol + Sample + LedoitWolf built-ins."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd
from sklearn.covariance import LedoitWolf

from ah_research.portfolio.optimizer.errors import ValidationError


@runtime_checkable
class CovarianceEstimator(Protocol):
    """Protocol for estimating Sigma (NxN covariance) from TxN returns."""

    def estimate(self, returns: pd.DataFrame) -> pd.DataFrame: ...


class SampleCovariance:
    """Unshrunk sample covariance via pandas DataFrame.cov()."""

    def __init__(self, min_periods: int = 60) -> None:
        self.min_periods = min_periods

    def estimate(self, returns: pd.DataFrame) -> pd.DataFrame:
        if len(returns) < self.min_periods:
            raise ValidationError(
                f"SampleCovariance needs min_periods={self.min_periods} rows; got {len(returns)}"
            )
        if returns.isna().all(axis=0).any():
            bad = returns.columns[returns.isna().all(axis=0)].tolist()
            raise ValidationError(f"Columns entirely NaN: {bad}")
        return returns.cov()


class LedoitWolfCovariance:
    """Ledoit-Wolf shrunk covariance via sklearn.covariance.LedoitWolf.

    `last_shrinkage_` is populated after each .estimate() call.
    """

    def __init__(self) -> None:
        self._last_shrinkage: float | None = None

    def estimate(self, returns: pd.DataFrame) -> pd.DataFrame:
        if returns.isna().any().any():
            returns = returns.dropna()
        if len(returns) < 2:
            raise ValidationError("LedoitWolfCovariance needs at least 2 rows after dropna")
        lw = LedoitWolf(store_precision=False)
        lw.fit(returns.values)
        self._last_shrinkage = float(lw.shrinkage_)
        return pd.DataFrame(lw.covariance_, index=returns.columns, columns=returns.columns)

    @property
    def last_shrinkage_(self) -> float:
        if self._last_shrinkage is None:
            raise RuntimeError("estimate() must be called before reading last_shrinkage_")
        return self._last_shrinkage
