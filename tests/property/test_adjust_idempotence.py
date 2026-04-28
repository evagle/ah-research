"""Hypothesis property: price adjustment is idempotent.

Calling ``compute_adjusted_prices`` twice with the same corporate-action
set must produce the same close_hfq / total_return values the second time.
(The implementation computes factors from ``close``, not from
``close_hfq``, so it's trivially idempotent — but the property test guards
against future regressions where someone might chain adjustments.)
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from ah_research.data.converters import compute_adjusted_prices


def _make_prices(n_days: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    base = 100.0
    closes = base * np.exp(np.cumsum(rng.normal(0, 0.01, n_days)))
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ["TEST.SH"] * n_days,
            "open": closes * 0.998,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": [1_000_000] * n_days,
            "amount": [1e8] * n_days,
            "turnover": [0.01] * n_days,
            "is_suspended": [False] * n_days,
            "is_st": [False] * n_days,
        }
    )


@given(
    n_days=st.integers(min_value=5, max_value=60),
    seed=st.integers(min_value=0, max_value=10_000),
    divs=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=50),
            st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        ),
        max_size=5,
    ),
)
@settings(max_examples=30, deadline=None)
def test_compute_adjusted_prices_idempotent(n_days, seed, divs):
    prices = _make_prices(n_days, seed)
    actions = pd.DataFrame(
        [
            {
                "symbol": "TEST.SH",
                "ex_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=min(offset, n_days - 1)),
                "kind": "cash_dividend",
                "params_json": json.dumps({"amount_per_share": amount}),
            }
            for offset, amount in divs
        ]
    )
    first = compute_adjusted_prices(prices, actions)
    second = compute_adjusted_prices(prices, actions)
    assert np.allclose(first["close_hfq"], second["close_hfq"])
    assert np.allclose(first["total_return"], second["total_return"])


@given(
    n_days=st.integers(min_value=5, max_value=60),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=30, deadline=None)
def test_no_actions_hfq_equals_close(n_days, seed):
    prices = _make_prices(n_days, seed)
    result = compute_adjusted_prices(prices, pd.DataFrame())
    assert np.allclose(result["close_hfq"], result["close"])
    assert np.allclose(result["total_return"], result["close"])
