# tests/unit/analysis/test_factor_study_bootstrap.py

import numpy as np
import pandas as pd

from ah_research.analysis.factor_study import _block_bootstrap, _sector_neutralize_signals


def test_block_bootstrap_deterministic_with_seed() -> None:
    returns = pd.Series(np.random.RandomState(1).randn(200))
    r1 = _block_bootstrap(returns, n_resamples=500, block_size=21, random_seed=42)
    r2 = _block_bootstrap(returns, n_resamples=500, block_size=21, random_seed=42)
    assert r1 == r2
    assert "mean" in r1 and "ci_low" in r1 and "ci_high" in r1 and "p_value" in r1


def test_block_bootstrap_ci_widens_with_more_resamples_stays_reasonable() -> None:
    returns = pd.Series(np.random.RandomState(1).randn(200) * 0.01)  # small std
    small = _block_bootstrap(returns, n_resamples=100, block_size=21, random_seed=42)
    large = _block_bootstrap(returns, n_resamples=1000, block_size=21, random_seed=42)
    # CI width should be similar across n (stable)
    w_small = small["ci_high"] - small["ci_low"]
    w_large = large["ci_high"] - large["ci_low"]
    assert abs(w_large - w_small) / max(abs(w_small), 1e-9) < 0.5


def test_sector_neutralize_removes_sector_mean() -> None:
    signals = pd.Series([1.0, 3.0, 1.0, 3.0], index=["A", "B", "C", "D"])
    sectors = pd.Series(["tech", "tech", "finance", "finance"], index=["A", "B", "C", "D"])
    neutral = _sector_neutralize_signals(signals, sectors)
    # After demean within sector, each sector has mean 0
    assert neutral.groupby(sectors).mean().abs().max() < 1e-10
