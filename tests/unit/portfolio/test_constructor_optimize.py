from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from ah_research.backtest.types import Signals
from ah_research.portfolio.constructor import Constructor


def _synthetic_signals() -> Signals:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime([date(2024, 6, 30)] * 5),
            "symbol": ["600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"],
            "signal": [1.0, 0.5, 0.2, 0.9, 0.1],
        }
    )
    return Signals.from_dataframe(df)


def test_constructor_accepts_optimizer_kwarg() -> None:
    c = Constructor(_synthetic_signals(), optimizer=None)
    # No exception means kwarg is accepted.
    assert c is not None


def test_weight_by_optimize_is_accepted_literal() -> None:
    c = Constructor(_synthetic_signals())
    returned = c.weight_by("optimize")
    assert returned is c
    assert c._weighting == "optimize"  # type: ignore[attr-defined]


def test_optimize_without_optimizer_raises() -> None:
    c = Constructor(_synthetic_signals()).weight_by("optimize")
    with pytest.raises(ValueError, match=r"requires Constructor\(optimizer="):
        c.build()


def test_optimize_without_repo_raises() -> None:
    fake_opt = object()
    c = Constructor(
        _synthetic_signals(),
        asof=date(2024, 6, 30),
        optimizer=fake_opt,  # type: ignore[arg-type]
    ).weight_by("optimize")
    with pytest.raises(ValueError, match=r"requires Constructor\(repo="):
        c.build()


def test_optimize_without_asof_raises() -> None:
    fake_opt = object()
    fake_repo = object()
    c = Constructor(
        _synthetic_signals(),
        repo=fake_repo,
        optimizer=fake_opt,  # type: ignore[arg-type]
    ).weight_by("optimize")
    with pytest.raises(ValueError, match=r"requires Constructor\(asof="):
        c.build()


def test_optimize_with_constrain_queue_raises() -> None:
    from ah_research.portfolio.constructor import Constraint

    fake_opt = object()
    fake_repo = object()
    c = (
        Constructor(
            _synthetic_signals(),
            repo=fake_repo,
            asof=date(2024, 6, 30),
            optimizer=fake_opt,  # type: ignore[arg-type]
        )
        .weight_by("optimize")
        .constrain(Constraint.max_weight(0.3))
    )
    with pytest.raises(ValueError, match=r"incompatible with \.constrain"):
        c.build()


def test_optimize_mode_happy_path() -> None:
    """End-to-end MV optimization through Constructor."""
    import numpy as np

    from ah_research.portfolio.optimizer import Optimizer
    from ah_research.portfolio.optimizer.estimators.covariance import LedoitWolfCovariance
    from ah_research.portfolio.optimizer.estimators.returns import UserSuppliedReturns

    # Build a tiny fake repo that returns synthetic returns
    symbols = ["600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"]
    n_days = 300
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")

    rng = np.random.default_rng(42)
    ret_matrix = rng.normal(0.0005, 0.015, size=(n_days, len(symbols)))

    rows = []
    for i, d in enumerate(dates):
        for j, s in enumerate(symbols):
            rows.append({"ds": d, "symbol": s, "total_return": ret_matrix[i, j]})
    prices_df = pd.DataFrame(rows)

    class FakeRepo:
        def get_prices(
            self,
            symbols: list[str],
            start,  # type: ignore[no-untyped-def]
            end,  # type: ignore[no-untyped-def]
        ) -> pd.DataFrame:
            return prices_df[
                (prices_df["ds"] >= pd.Timestamp(start)) & (prices_df["ds"] <= pd.Timestamp(end))
            ].copy()

    mu = pd.Series([0.01, 0.008, 0.006, 0.012, 0.005], index=symbols)
    optimizer = Optimizer(
        objective="mean_variance",
        cov_estimator=LedoitWolfCovariance(),
        returns_estimator=UserSuppliedReturns(mu),
        risk_aversion=1.0,
    )

    signals_df = pd.DataFrame(
        {
            "date": pd.to_datetime([date(2024, 6, 30)] * 5),
            "symbol": symbols,
            "signal": [1.0, 0.5, 0.2, 0.9, 0.1],
        }
    )
    signals = Signals.from_dataframe(signals_df)

    report = (
        Constructor(signals, repo=FakeRepo(), asof=date(2024, 6, 30), optimizer=optimizer)
        .method("all_positive")
        .weight_by("optimize")
        .build()
    )

    # Contract checks
    assert report.weighting_scheme == "optimize"
    assert report.final_position_count > 0
    assert abs(report.weights["weight"].sum() - 1.0) < 1e-4
    assert (report.weights["weight"] >= -1e-8).all()
    assert report.optimization_result is not None
    assert report.optimization_result.solver_status in ("optimal", "optimal_inaccurate")


def test_optimize_empty_selection_raises() -> None:
    from ah_research.portfolio.optimizer import Optimizer
    from ah_research.portfolio.optimizer.estimators.covariance import LedoitWolfCovariance

    class EmptyRepo:
        def get_prices(self, *a, **kw):  # type: ignore[no-untyped-def]
            return pd.DataFrame(columns=["ds", "symbol", "total_return"])

    signals_df = pd.DataFrame(
        {
            "date": pd.to_datetime([date(2024, 6, 30)] * 2),
            "symbol": ["600000.SH", "600001.SH"],
            "signal": [-1.0, -2.0],  # all negative → all_positive selects nothing
        }
    )
    signals = Signals.from_dataframe(signals_df)
    opt = Optimizer(
        objective="risk_parity",
        cov_estimator=LedoitWolfCovariance(),
    )
    c = (
        Constructor(signals, repo=EmptyRepo(), asof=date(2024, 6, 30), optimizer=opt)
        .method("all_positive")
        .weight_by("optimize")
    )
    with pytest.raises(ValueError, match=r"nothing selected"):
        c.build()


def test_optimize_risk_parity_runs() -> None:
    import numpy as np

    from ah_research.portfolio.optimizer import Optimizer
    from ah_research.portfolio.optimizer.estimators.covariance import LedoitWolfCovariance

    symbols = ["600000.SH", "600001.SH", "600002.SH"]
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    rng = np.random.default_rng(7)
    ret_matrix = rng.normal(0.0005, 0.015, size=(len(dates), len(symbols)))
    rows = []
    for i, d in enumerate(dates):
        for j, s in enumerate(symbols):
            rows.append({"ds": d, "symbol": s, "total_return": ret_matrix[i, j]})
    prices_df = pd.DataFrame(rows)

    class FakeRepo:
        def get_prices(self, symbols, start, end):  # type: ignore[no-untyped-def]
            return prices_df[
                (prices_df["ds"] >= pd.Timestamp(start)) & (prices_df["ds"] <= pd.Timestamp(end))
            ].copy()

    signals_df = pd.DataFrame(
        {
            "date": pd.to_datetime([date(2024, 6, 30)] * 3),
            "symbol": symbols,
            "signal": [1.0, 0.5, 0.3],
        }
    )
    signals = Signals.from_dataframe(signals_df)
    opt = Optimizer(objective="risk_parity", cov_estimator=LedoitWolfCovariance())

    report = (
        Constructor(signals, repo=FakeRepo(), asof=date(2024, 6, 30), optimizer=opt)
        .method("all_positive")
        .weight_by("optimize")
        .build()
    )
    assert abs(report.weights["weight"].sum() - 1.0) < 1e-4
    assert report.optimization_result is not None
