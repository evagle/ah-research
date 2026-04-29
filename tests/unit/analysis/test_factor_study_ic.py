# tests/unit/analysis/test_factor_study_ic.py
from datetime import date

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from ah_research.analysis.factor_study import _compute_ic_one_date, _InlineSignalStrategy
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_compute_ic_matches_scipy_spearman() -> None:
    np.random.seed(42)
    signals = pd.Series(np.random.randn(20), index=[f"SYM{i}.SH" for i in range(20)])
    forward_returns = pd.Series(np.random.randn(20), index=signals.index)
    ic = _compute_ic_one_date(signals, forward_returns)
    expected, _ = spearmanr(signals.values, forward_returns.values)
    assert ic == pytest.approx(expected, abs=1e-10)


def test_compute_ic_handles_nan_dropping() -> None:
    signals = pd.Series([1.0, 2.0, float("nan"), 4.0], index=["A", "B", "C", "D"])
    forward = pd.Series([0.1, 0.2, 0.3, 0.4], index=["A", "B", "C", "D"])
    ic = _compute_ic_one_date(signals, forward)
    expected, _ = spearmanr([1.0, 2.0, 4.0], [0.1, 0.2, 0.4])
    assert ic == pytest.approx(expected, abs=1e-10)


def test_inline_signal_strategy_adapter() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-31", "2024-01-31"]),
            "symbol": ["600000.SH", "000001.SZ"],
            "signal": [0.1, 0.2],
        }
    )
    strategy = _InlineSignalStrategy(df)
    assert strategy.name == "inline"

    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 2, 1),
        symbols=["600000.SH", "000001.SZ"],
    )
    signals = strategy.generate(repo, date(2024, 1, 31), date(2024, 1, 31))
    assert len(signals.df) == 2
