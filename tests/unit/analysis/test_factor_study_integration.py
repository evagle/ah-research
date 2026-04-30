# tests/unit/analysis/test_factor_study_integration.py
from datetime import date

import numpy as np
import pandas as pd

from ah_research.analysis.factor_study import FactorReport, factor_study
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_factor_study_returns_valid_report_from_dataframe() -> None:
    repo = build_synthetic_market(
        start=date(2022, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ", "600519.SH", "600036.SH", "601318.SH"],
    )
    rng = np.random.default_rng(42)
    eoms = pd.date_range("2022-01-31", "2024-12-31", freq="ME")
    rows = []
    for d in eoms:
        for s in ["600000.SH", "000001.SZ", "600519.SH", "600036.SH", "601318.SH"]:
            rows.append({"date": d, "symbol": s, "signal": rng.standard_normal()})
    signals_df = pd.DataFrame(rows)

    report = factor_study(
        signals_df,
        repo,
        start=date(2022, 1, 1),
        end=date(2024, 12, 31),
        n_quantiles=5,
        ic_horizons=[5, 20],
        sector_neutral=True,
        bootstrap_n_resamples=200,
    )
    assert isinstance(report, FactorReport)
    assert report.n_rebalance_dates > 0
    assert report.ic_summary.shape[0] == 2  # 2 horizons
    assert "mean_ic" in report.ic_summary.columns
    assert report.sector_neutralized is True


def test_factor_study_accepts_strategy() -> None:
    from ah_research.strategies import ValueFactorStrategy

    repo = build_synthetic_market(
        start=date(2022, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ", "600519.SH", "600036.SH", "601318.SH"],
    )
    strategy = ValueFactorStrategy()
    report = factor_study(
        strategy,
        repo,
        start=date(2022, 1, 1),
        end=date(2024, 12, 31),
        ic_horizons=[20],
        bootstrap_n_resamples=100,
    )
    assert isinstance(report, FactorReport)
