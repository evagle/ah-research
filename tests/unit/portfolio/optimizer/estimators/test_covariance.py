import numpy as np
import pandas as pd
import pytest

from ah_research.portfolio.optimizer.errors import ValidationError
from ah_research.portfolio.optimizer.estimators.covariance import (
    CovarianceEstimator,
    LedoitWolfCovariance,
    SampleCovariance,
)


def _returns(n_assets: int = 5, n_periods: int = 120, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    tickers = [f"SYM{i:02d}" for i in range(n_assets)]
    return pd.DataFrame(
        rng.normal(0, 0.01, size=(n_periods, n_assets)),
        columns=tickers,
    )


def test_sample_covariance_shape_and_symmetry():
    est = SampleCovariance(min_periods=60)
    r = _returns()
    sigma = est.estimate(r)
    assert sigma.shape == (5, 5)
    assert list(sigma.index) == list(r.columns)
    np.testing.assert_allclose(sigma.values, sigma.values.T, atol=1e-12)


def test_sample_covariance_rejects_short_history():
    est = SampleCovariance(min_periods=60)
    r = _returns(n_periods=30)
    with pytest.raises(ValidationError, match="min_periods"):
        est.estimate(r)


def test_sample_covariance_rejects_all_nan_column():
    est = SampleCovariance()
    r = _returns()
    r["SYM02"] = float("nan")
    with pytest.raises(ValidationError, match="NaN"):
        est.estimate(r)


def test_ledoit_wolf_shape_and_shrinkage_recorded():
    est = LedoitWolfCovariance()
    r = _returns()
    sigma = est.estimate(r)
    assert sigma.shape == (5, 5)
    assert 0.0 <= est.last_shrinkage_ <= 1.0


def test_ledoit_wolf_is_psd():
    est = LedoitWolfCovariance()
    r = _returns(n_assets=10, n_periods=200)
    sigma = est.estimate(r)
    eigs = np.linalg.eigvalsh(sigma.values)
    assert eigs.min() >= -1e-10


def test_both_satisfy_protocol():
    for est in (SampleCovariance(), LedoitWolfCovariance()):
        assert isinstance(est, CovarianceEstimator)
