from __future__ import annotations

from datetime import date

import pandas as pd

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
