"""Tests for _block_bootstrap and _sector_neutralize_signals helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ah_research.analysis.factor_study import _block_bootstrap, _sector_neutralize_signals


@pytest.fixture
def synthetic_returns():
    """Callable: build a 200-period synthetic return series with seeded RNG.

    ``scale`` lets tests opt into a small-std variant when CI-width
    stability matters.
    """

    def _build(scale: float = 1.0, seed: int = 1, n: int = 200) -> pd.Series:
        return pd.Series(np.random.RandomState(seed).randn(n) * scale)

    return _build


def test_block_bootstrap_deterministic_with_seed(synthetic_returns) -> None:  # type: ignore[no-untyped-def]
    returns = synthetic_returns()
    r1 = _block_bootstrap(returns, n_resamples=500, block_size=21, random_seed=42)
    r2 = _block_bootstrap(returns, n_resamples=500, block_size=21, random_seed=42)
    assert r1 == r2
    assert {"mean", "ci_low", "ci_high", "p_value"} <= r1.keys()


def test_block_bootstrap_ci_width_stable_across_n_resamples(synthetic_returns) -> None:  # type: ignore[no-untyped-def]
    """CI width should be similar regardless of resample count (stable)."""
    returns = synthetic_returns(scale=0.01)  # small std
    small = _block_bootstrap(returns, n_resamples=100, block_size=21, random_seed=42)
    large = _block_bootstrap(returns, n_resamples=1000, block_size=21, random_seed=42)
    w_small = small["ci_high"] - small["ci_low"]
    w_large = large["ci_high"] - large["ci_low"]
    assert abs(w_large - w_small) / max(abs(w_small), 1e-9) < 0.5


def test_sector_neutralize_removes_sector_mean() -> None:
    signals = pd.Series([1.0, 3.0, 1.0, 3.0], index=["A", "B", "C", "D"])
    sectors = pd.Series(["tech", "tech", "finance", "finance"], index=["A", "B", "C", "D"])
    neutral = _sector_neutralize_signals(signals, sectors)
    # After demean within sector, each sector has mean 0.
    assert neutral.groupby(sectors).mean().abs().max() < 1e-10
