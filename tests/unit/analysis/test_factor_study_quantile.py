# tests/unit/analysis/test_factor_study_quantile.py

import numpy as np
import pandas as pd
import pytest

from ah_research.analysis.factor_study import (
    _assign_quantiles,
    _compute_quantile_returns,
    _ic_table_by_horizon,
)


def test_assign_quantiles_5_equal_buckets() -> None:
    np.random.seed(42)
    signals = pd.Series(np.arange(20), dtype=float)  # 0..19
    q = _assign_quantiles(signals, n_quantiles=5)
    # 4 per bucket, Q1 contains lowest, Q5 contains highest
    assert (q == 1).sum() == 4
    assert (q == 5).sum() == 4
    assert q.iloc[0] == 1
    assert q.iloc[-1] == 5


def test_quantile_returns_equal_weighted() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="ME")
    signals = pd.DataFrame(
        {
            "date": np.repeat(dates, 5),
            "symbol": ["A", "B", "C", "D", "E"] * 3,
            "signal": [1.0, 2.0, 3.0, 4.0, 5.0] * 3,
            "forward_return_20": [0.01, 0.02, 0.03, 0.04, 0.05] * 3,
        }
    )
    returns = _compute_quantile_returns(signals, n_quantiles=5, horizon=20)
    # With 5 symbols and 5 quantiles, each quantile = 1 symbol
    # Q1 = A's return = 0.01; Q5 = E's return = 0.05
    assert returns.loc[dates[0], "Q1"] == pytest.approx(0.01)
    assert returns.loc[dates[0], "Q5"] == pytest.approx(0.05)
    assert returns.loc[dates[0], "long_short"] == pytest.approx(0.04)


def test_ic_table_by_horizon_shape() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="ME")
    rng = np.random.default_rng(0)
    signals = pd.DataFrame(
        {
            "date": np.repeat(dates, 10),
            "symbol": [f"S{i}" for i in range(10)] * 3,
            "signal": rng.standard_normal(30),
            "forward_return_5": rng.standard_normal(30),
            "forward_return_20": rng.standard_normal(30),
        }
    )
    table = _ic_table_by_horizon(signals, horizons=[5, 20])
    assert table.shape == (3, 2)
    assert "5" in table.columns
    assert "20" in table.columns
