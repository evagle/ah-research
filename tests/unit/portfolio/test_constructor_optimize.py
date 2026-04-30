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
