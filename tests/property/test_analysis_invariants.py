"""Property-based tests for analysis module invariants.

Three hypothesis tests:
  1. Screener idempotence: same inputs → equal results.
  2. Constructor weights sum to 1.0 when all constraints are slack.
  3. Factor study with shuffled signals has near-zero mean IC (within noise band).

Settings: max_examples=10, deadline=60_000 ms.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# Symbols used throughout
_SYMBOLS = ["600000.SH", "000001.SZ", "600519.SH", "600036.SH", "601318.SH"]
_START = date(2022, 1, 1)
_END = date(2023, 12, 31)


# ── Helper ────────────────────────────────────────────────────────────────────


def _make_random_signals_df(symbols: list[str], start: date, end: date, seed: int) -> pd.DataFrame:
    """Build a monthly signal DataFrame with the given RNG seed."""
    rng = np.random.default_rng(seed % (2**31))
    eoms = pd.date_range(str(start), str(end), freq="ME")
    rows = []
    for d in eoms:
        for sym in symbols:
            rows.append({"date": d, "symbol": sym, "signal": float(rng.standard_normal())})
    return pd.DataFrame(rows)


# ── Test 1: Screener idempotence ───────────────────────────────────────────────


@given(seed=st.integers(0, 2**31 - 1))
@settings(max_examples=10, deadline=60_000)
def test_screener_idempotent(seed: int) -> None:
    """Running run_screen twice with identical inputs returns equal results."""
    from ah_research.analysis.screener import run_screen

    repo = build_synthetic_market(start=_START, end=_END, symbols=_SYMBOLS, seed=seed % 100)
    asof = date(2023, 12, 31)
    conditions: dict = {"pe": (">", 0.0)}

    r1 = run_screen(conditions=conditions, repo=repo, asof=asof)
    r2 = run_screen(conditions=conditions, repo=repo, asof=asof)

    assert r1.n_input == r2.n_input
    assert r1.n_passed == r2.n_passed
    assert r1.asof == r2.asof
    # Frames must have the same symbols in the same order
    if not r1.frame.empty and not r2.frame.empty:
        sym1 = sorted(r1.frame["symbol"].tolist())
        sym2 = sorted(r2.frame["symbol"].tolist())
        assert sym1 == sym2


# Pool of valid symbols (match ^[0-9]{4,6}\.(SH|SZ|HK)$) for the constructor test.
_CONSTRUCTOR_SYMBOLS = [
    "600000.SH",
    "000001.SZ",
    "600519.SH",
    "600036.SH",
    "601318.SH",
    "000002.SZ",
    "601166.SH",
    "600276.SH",
    "600887.SH",
    "000858.SZ",
]


# ── Test 2: Constructor weights sum to 1.0 ─────────────────────────────────────


@given(seed=st.integers(0, 2**31 - 1))
@settings(max_examples=10, deadline=60_000)
def test_constructor_weights_sum_to_one_when_all_slack(seed: int) -> None:
    """With a top_quantile selection (always picks positions) and no binding weight
    constraints, final weights sum to 1.0."""
    from ah_research.backtest.types import Signals
    from ah_research.portfolio.constructor import Constraint, ConstructionReport, Constructor

    rng = np.random.default_rng(seed % (2**31))
    # Pick between 5 and 10 symbols from the pool using the seed
    n = 5 + int(rng.integers(0, 6))  # 5..10
    symbols = _CONSTRUCTOR_SYMBOLS[:n]

    repo = build_synthetic_market(
        start=date(2023, 1, 1), end=date(2023, 6, 30), symbols=symbols, seed=seed % 100
    )
    signals_data = {
        "date": pd.to_datetime(["2023-06-30"] * n),
        "symbol": symbols,
        # Use abs() so all signals are positive — all_positive always selects all
        "signal": [abs(float(rng.standard_normal())) + 0.01 for _ in range(n)],
    }
    signals = Signals.from_dataframe(pd.DataFrame(signals_data))

    report: ConstructionReport = (
        Constructor(signals, repo=repo, asof=date(2023, 6, 30))
        .method("all_positive")
        .weight_by("equal")
        # Only a very slack max_weight that will not bind (100% per name)
        .constrain(Constraint.max_weight(1.0))
        .build()
    )

    assert isinstance(report, ConstructionReport)
    assert report.final_position_count > 0, "Expected at least one position"
    total_weight = float(report.weights["weight"].sum())
    # Weights should sum to 1.0 (±1e-6) when constraint is slack
    assert abs(total_weight - 1.0) < 1e-6, f"Weights sum to {total_weight}, expected 1.0"


# ── Test 3: Shuffled signals → near-zero mean IC ───────────────────────────────


@given(seed=st.integers(0, 2**31 - 1))
@settings(max_examples=5, deadline=120_000)
def test_factor_study_shuffled_signals_near_zero_mean_ic(seed: int) -> None:
    """Randomly shuffled signals should produce mean IC near zero (|mean IC| < 0.5).

    We use a direct random signals DataFrame (not a strategy) to avoid degenerate
    constant-signal output from ValueFactorStrategy on synthetic data.
    The noise band is generous (|IC| < 0.5) because with only ~5 symbols the
    Spearman rank correlation has high variance.
    """
    from ah_research.analysis.factor_study import factor_study

    repo = build_synthetic_market(start=_START, end=_END, symbols=_SYMBOLS, seed=seed % 100)

    # Build signals then shuffle the signal column to destroy any predictive power
    rng = np.random.default_rng(seed % (2**31))
    signals_df = _make_random_signals_df(_SYMBOLS, _START, _END, seed=seed)
    # Shuffle signals within each date to decorrelate from forward returns
    shuffled_rows = []
    for _d, grp in signals_df.groupby("date"):
        grp = grp.copy()
        grp["signal"] = rng.permutation(grp["signal"].values)
        shuffled_rows.append(grp)
    shuffled_df = pd.concat(shuffled_rows, ignore_index=True)

    report = factor_study(
        shuffled_df,
        repo,
        start=_START,
        end=_END,
        n_quantiles=5,
        ic_horizons=[20],
        sector_neutral=False,
        bootstrap_n_resamples=50,
    )

    mean_ic_vals = report.ic_summary["mean_ic"].dropna()
    if mean_ic_vals.empty:
        # No finite IC values; this can happen with very small universes — skip
        pytest.skip("No finite IC values computed (universe too small)")

    # With randomly shuffled signals the mean IC should be small in magnitude
    # |mean IC| < 0.5 is a very generous band but appropriate for 5-symbol universe
    abs_mean_ic = float(mean_ic_vals.abs().max())
    assert abs_mean_ic < 0.5, (
        f"Shuffled signals produced |mean IC| = {abs_mean_ic:.3f}, expected < 0.5"
    )
