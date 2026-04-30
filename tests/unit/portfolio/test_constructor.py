"""Tests for Constructor + ConstructionReport (Task 16)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from ah_research.backtest.types import Signals
from ah_research.portfolio.constructor import Constraint, ConstructionReport, Constructor
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def _make_signals(symbols: list[str], date_str: str = "2024-06-30") -> Signals:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime([date_str] * len(symbols)),
            "symbol": symbols,
            "signal": [float(i) for i in range(len(symbols))],
        }
    )
    return Signals.from_dataframe(df)


def test_constructor_chain_builds_report() -> None:
    symbols = [f"60000{i}.SH" for i in range(10)]
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        symbols=symbols,
    )
    signals = _make_signals(symbols)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("top_quantile", quantile=0.2)
        .weight_by("equal")
        .constrain(Constraint.max_weight(0.5))
        .build()
    )
    assert isinstance(report, ConstructionReport)
    assert report.final_position_count == 2  # top 20% of 10
    assert len(report.constraint_results) == 1


def test_constructor_max_weight_relaxes_and_reports() -> None:
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        symbols=["600001.SH", "600002.SH"],
    )
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-06-30", "2024-06-30"]),
            "symbol": ["600001.SH", "600002.SH"],
            "signal": [1.0, 1.0],
        }
    )
    signals = Signals.from_dataframe(df)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("all_positive")
        .weight_by("equal")  # 0.5 each
        .constrain(Constraint.max_weight(0.3))  # forces relaxation
        .build()
    )
    assert report.constraint_results[0].status in ("bound", "infeasible_relaxed")


def test_weights_sum_to_one_no_constraints() -> None:
    symbols = ["600001.SH", "600002.SH", "600003.SH", "600004.SH", "600005.SH"]
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        symbols=symbols,
    )
    signals = _make_signals(symbols)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("top_quantile", quantile=1.0)
        .weight_by("equal")
        .build()
    )
    assert abs(report.weights["weight"].sum() - 1.0) < 1e-9


def test_all_positive_selection() -> None:
    symbols = ["600010.SH", "600020.SH", "600030.SH"]
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        symbols=symbols,
    )
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-06-30"] * 3),
            "symbol": symbols,
            "signal": [1.0, 2.0, -1.0],
        }
    )
    signals = Signals.from_dataframe(df)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("all_positive")
        .weight_by("equal")
        .build()
    )
    assert report.final_position_count == 2
    selected = set(report.weights[report.weights["weight"] > 0]["symbol"].tolist())
    assert "600030.SH" not in selected


def test_max_positions_constraint() -> None:
    symbols = ["600011.SH", "600012.SH", "600013.SH", "600014.SH", "600015.SH", "600016.SH"]
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        symbols=symbols,
    )
    signals = _make_signals(symbols)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("top_quantile", quantile=1.0)
        .weight_by("equal")
        .constrain(Constraint.max_positions(3))
        .build()
    )
    assert report.final_position_count <= 3


def test_min_positions_infeasible_relaxed() -> None:
    symbols = ["600021.SH", "600022.SH"]
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        symbols=symbols,
    )
    signals = _make_signals(symbols)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("top_quantile", quantile=1.0)
        .weight_by("equal")
        .constrain(Constraint.min_positions(100))  # impossible
        .build()
    )
    assert report.constraint_results[0].status == "infeasible_relaxed"


def test_signal_proportional_weighting() -> None:
    symbols = ["600031.SH", "600032.SH", "600033.SH", "600034.SH"]
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        symbols=symbols,
    )
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-06-30"] * 4),
            "symbol": symbols,
            "signal": [1.0, 2.0, 3.0, 4.0],
        }
    )
    signals = Signals.from_dataframe(df)
    report = (
        Constructor(signals, repo=repo, asof=date(2024, 6, 30))
        .method("top_quantile", quantile=1.0)
        .weight_by("signal_proportional")
        .build()
    )
    assert abs(report.weights["weight"].sum() - 1.0) < 1e-9
    # Higher signal → higher weight
    w = report.weights.set_index("symbol")["weight"]
    assert w["600034.SH"] > w["600031.SH"]
