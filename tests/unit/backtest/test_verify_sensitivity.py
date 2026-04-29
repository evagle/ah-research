"""Tests for verify.sensitivity — parameter grid sweep."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from ah_research.backtest import verify
from ah_research.backtest.types import BacktestConfig, Weights
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ── shared fixture ────────────────────────────────────────────────────────────

SYMBOLS = ["600000.SH", "000001.SZ"]
START = date(2023, 1, 1)
END = date(2023, 6, 30)


def _repo():
    return build_synthetic_market(start=START, end=END, symbols=SYMBOLS)


_BASE_CONFIG = BacktestConfig(
    start=START,
    end=END,
    initial_cash=Decimal("1_000_000"),
    benchmark="zero",
    cost_model=None,
)


class ParameterisedWeightStrategy:
    """Strategy that accepts a `tilt` parameter; emits equal weights with a tilt adjustment."""

    def __init__(self, tilt: float = 0.0, max_weight: float = 0.5) -> None:
        self.tilt = tilt
        self.max_weight = max_weight
        self.name = f"parameterised_tilt={tilt}"

    def generate(self, repo, start, end):
        eom = pd.date_range(start, end, freq="ME")
        if len(eom) == 0:
            return Weights.from_dataframe(
                pd.DataFrame(
                    {
                        "date": pd.Series([], dtype="datetime64[ns]"),
                        "symbol": pd.Series([], dtype=str),
                        "weight": pd.Series([], dtype=float),
                    }
                )
            )
        rows = []
        # Distribute weights using the tilt to differentiate performance across combos
        for ts in eom:
            base = 0.5
            rows.append(
                {"date": ts, "symbol": SYMBOLS[0], "weight": min(base + self.tilt, self.max_weight)}
            )
            rows.append({"date": ts, "symbol": SYMBOLS[1], "weight": max(base - self.tilt, 0.0)})
        return Weights.from_dataframe(pd.DataFrame(rows))


# ── tests ─────────────────────────────────────────────────────────────────────


def test_sensitivity_single_param_returns_grid_df():
    repo = _repo()
    report = verify.sensitivity(
        ParameterisedWeightStrategy,
        repo,
        _BASE_CONFIG,
        param_grid={"tilt": [0.0, 0.1, 0.2]},
    )
    assert len(report.grid_df) == 3
    assert "tilt" in report.grid_df.columns
    assert "sharpe" in report.grid_df.columns
    assert report.param_columns == ["tilt"]
    assert "sharpe" in report.metric_columns


def test_sensitivity_multi_param_cartesian_product():
    repo = _repo()
    report = verify.sensitivity(
        ParameterisedWeightStrategy,
        repo,
        _BASE_CONFIG,
        param_grid={"tilt": [0.0, 0.1], "max_weight": [0.4, 0.5]},
    )
    # 2 x 2 = 4 combinations
    assert len(report.grid_df) == 4
    assert set(report.param_columns) == {"tilt", "max_weight"}


def test_sensitivity_metrics_are_populated():
    repo = _repo()
    report = verify.sensitivity(
        ParameterisedWeightStrategy,
        repo,
        _BASE_CONFIG,
        param_grid={"tilt": [0.0, 0.1]},
    )
    assert report.grid_df["cagr"].notna().any()


def test_sensitivity_exceeds_100_raises():
    repo = _repo()
    with pytest.raises(ValueError, match="100"):
        verify.sensitivity(
            ParameterisedWeightStrategy,
            repo,
            _BASE_CONFIG,
            param_grid={
                "tilt": [i * 0.01 for i in range(11)],
                "max_weight": [0.4 + i * 0.01 for i in range(11)],
            },
        )


def test_sensitivity_empty_param_grid_raises():
    repo = _repo()
    with pytest.raises(ValueError):
        verify.sensitivity(
            ParameterisedWeightStrategy,
            repo,
            _BASE_CONFIG,
            param_grid={},
        )


def test_sensitivity_report_dataclass_fields():
    repo = _repo()
    report = verify.sensitivity(
        ParameterisedWeightStrategy,
        repo,
        _BASE_CONFIG,
        param_grid={"tilt": [0.0]},
    )
    assert isinstance(report.grid_df, pd.DataFrame)
    assert isinstance(report.metric_columns, list)
    assert isinstance(report.param_columns, list)
    assert len(report.grid_df) == 1
