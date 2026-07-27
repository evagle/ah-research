"""Unit tests for SampleCovariance + LedoitWolfCovariance estimators."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ah_research.portfolio.optimizer.errors import ValidationError
from ah_research.portfolio.optimizer.estimators.covariance import (
    CovarianceEstimator,
    LedoitWolfCovariance,
    SampleCovariance,
)


@pytest.fixture
def returns_factory():
    """Callable factory: build a (n_periods, n_assets) Gaussian-returns frame
    with seeded RNG."""

    def _build(n_assets: int = 5, n_periods: int = 120, seed: int = 0) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        tickers = [f"SYM{i:02d}" for i in range(n_assets)]
        return pd.DataFrame(
            rng.normal(0, 0.01, size=(n_periods, n_assets)),
            columns=tickers,
        )

    return _build


# ── SampleCovariance ───────────────────────────────────────────────────────


def test_sample_covariance_shape_and_symmetry(returns_factory) -> None:  # type: ignore[no-untyped-def]
    est = SampleCovariance(min_periods=60)
    r = returns_factory()
    sigma = est.estimate(r)
    assert sigma.shape == (5, 5)
    assert list(sigma.index) == list(r.columns)
    np.testing.assert_allclose(sigma.values, sigma.values.T, atol=1e-12)


def test_sample_covariance_rejects_short_history(returns_factory) -> None:  # type: ignore[no-untyped-def]
    est = SampleCovariance(min_periods=60)
    with pytest.raises(ValidationError, match="min_periods"):
        est.estimate(returns_factory(n_periods=30))


def test_sample_covariance_rejects_all_nan_column(returns_factory) -> None:  # type: ignore[no-untyped-def]
    est = SampleCovariance()
    r = returns_factory()
    r["SYM02"] = float("nan")
    with pytest.raises(ValidationError, match="NaN"):
        est.estimate(r)


# ── LedoitWolfCovariance ───────────────────────────────────────────────────


def test_ledoit_wolf_shape_and_shrinkage_recorded(returns_factory) -> None:  # type: ignore[no-untyped-def]
    est = LedoitWolfCovariance()
    sigma = est.estimate(returns_factory())
    assert sigma.shape == (5, 5)
    assert 0.0 <= est.last_shrinkage_ <= 1.0


def test_ledoit_wolf_is_psd(returns_factory) -> None:  # type: ignore[no-untyped-def]
    est = LedoitWolfCovariance()
    sigma = est.estimate(returns_factory(n_assets=10, n_periods=200))
    eigs = np.linalg.eigvalsh(sigma.values)
    assert eigs.min() >= -1e-10


@pytest.mark.parametrize(
    "estimator",
    [SampleCovariance(), LedoitWolfCovariance()],
    ids=["sample", "ledoit-wolf"],
)
def test_estimators_satisfy_protocol(estimator: CovarianceEstimator) -> None:
    assert isinstance(estimator, CovarianceEstimator)
