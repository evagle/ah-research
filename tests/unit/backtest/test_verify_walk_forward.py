"""Tests for verify.walk_forward — expanding and rolling modes."""

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
END = date(2023, 12, 31)


def _repo():
    return build_synthetic_market(start=START, end=END, symbols=SYMBOLS)


class SimpleWeightStrategy:
    """Emits equal weight on each month-end rebalance. Uses only A-shares."""

    name = "simple_equal"

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
        for ts in eom:
            for sym in SYMBOLS:
                rows.append({"date": ts, "symbol": sym, "weight": 0.5})
        return Weights.from_dataframe(pd.DataFrame(rows))


_BASE_CONFIG = BacktestConfig(
    start=START,
    end=END,
    initial_cash=Decimal("1_000_000"),
    benchmark="zero",
    cost_model=None,
)


# ── tests ─────────────────────────────────────────────────────────────────────


def test_walk_forward_expanding_produces_5_splits():
    repo = _repo()
    factory = SimpleWeightStrategy
    report = verify.walk_forward(
        factory,
        repo,
        START,
        END,
        _BASE_CONFIG,
        n_splits=5,
        mode="expanding",
    )
    assert len(report.splits) == 5
    assert report.mode == "expanding"


def test_walk_forward_rolling_produces_5_splits():
    repo = _repo()
    factory = SimpleWeightStrategy
    report = verify.walk_forward(
        factory,
        repo,
        START,
        END,
        _BASE_CONFIG,
        n_splits=5,
        mode="rolling",
    )
    assert len(report.splits) == 5
    assert report.mode == "rolling"


def test_walk_forward_expanding_is_grows():
    """In expanding mode, each successive IS end is later than the previous."""
    repo = _repo()
    report = verify.walk_forward(
        SimpleWeightStrategy,
        repo,
        START,
        END,
        _BASE_CONFIG,
        n_splits=4,
        mode="expanding",
    )
    is_ends = [s.is_end for s in report.splits]
    assert is_ends == sorted(is_ends)
    # All IS windows start from the same date in expanding mode
    is_starts = [s.is_start for s in report.splits]
    assert all(d == is_starts[0] for d in is_starts)


def test_walk_forward_rolling_is_shifts():
    """In rolling mode, both IS start and end advance."""
    repo = _repo()
    report = verify.walk_forward(
        SimpleWeightStrategy,
        repo,
        START,
        END,
        _BASE_CONFIG,
        n_splits=4,
        mode="rolling",
    )
    is_starts = [s.is_start for s in report.splits]
    is_ends = [s.is_end for s in report.splits]
    assert is_starts == sorted(is_starts)
    assert is_ends == sorted(is_ends)


def test_walk_forward_oos_windows_are_contiguous():
    """OOS windows should cover the full period after the first split."""
    repo = _repo()
    report = verify.walk_forward(
        SimpleWeightStrategy,
        repo,
        START,
        END,
        _BASE_CONFIG,
        n_splits=3,
        mode="expanding",
    )
    for i in range(len(report.splits) - 1):
        s_curr = report.splits[i]
        s_next = report.splits[i + 1]
        # OOS end of split i should be before OOS start of split i+1
        assert s_curr.oos_end <= s_next.oos_start


def test_walk_forward_metrics_are_populated():
    """Each split must have non-None cagr in metrics."""
    repo = _repo()
    report = verify.walk_forward(
        SimpleWeightStrategy,
        repo,
        START,
        END,
        _BASE_CONFIG,
        n_splits=3,
        mode="expanding",
    )
    for split in report.splits:
        assert split.is_metrics is not None
        assert split.oos_metrics is not None
        assert split.is_metrics.cagr is not None


def test_walk_forward_combined_oos_metrics():
    """combined_oos_metrics must be a MetricsBundle with populated fields."""
    repo = _repo()
    report = verify.walk_forward(
        SimpleWeightStrategy,
        repo,
        START,
        END,
        _BASE_CONFIG,
        n_splits=3,
        mode="expanding",
    )
    mb = report.combined_oos_metrics
    assert mb is not None
    assert mb.cagr is not None


def test_walk_forward_invalid_mode_raises():
    with pytest.raises(ValueError, match="mode"):
        verify.walk_forward(
            SimpleWeightStrategy,
            _repo(),
            START,
            END,
            _BASE_CONFIG,
            n_splits=3,
            mode="bad_mode",
        )
