"""Tests for verify.survivorship_check — PIT vs static vs random-universe baselines."""

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
    random_seed=42,
)


class SimpleWeightStrategy:
    """Equal-weight monthly rebalance."""

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


# ── tests ─────────────────────────────────────────────────────────────────────


def test_survivorship_report_structure():
    repo = _repo()
    strategy = SimpleWeightStrategy()
    report = verify.survivorship_check(strategy, repo, _BASE_CONFIG, n_random_universes=5)

    assert report.pit_metrics is not None
    assert report.static_metrics is not None
    assert isinstance(report.random_metrics_distribution, pd.DataFrame)
    assert isinstance(report.pit_sharpe_percentile, float)
    assert isinstance(report.pit_vs_static_delta, dict)


def test_survivorship_random_dist_has_correct_rows():
    repo = _repo()
    strategy = SimpleWeightStrategy()
    report = verify.survivorship_check(strategy, repo, _BASE_CONFIG, n_random_universes=10)

    # Should have up to n_random_universes rows (some may fail gracefully)
    assert len(report.random_metrics_distribution) <= 10
    assert len(report.random_metrics_distribution) > 0


def test_survivorship_pit_sharpe_percentile_in_range():
    repo = _repo()
    strategy = SimpleWeightStrategy()
    report = verify.survivorship_check(strategy, repo, _BASE_CONFIG, n_random_universes=10)

    assert 0.0 <= report.pit_sharpe_percentile <= 100.0


def test_survivorship_pit_vs_static_delta_keys():
    repo = _repo()
    strategy = SimpleWeightStrategy()
    report = verify.survivorship_check(strategy, repo, _BASE_CONFIG, n_random_universes=5)

    delta = report.pit_vs_static_delta
    assert "sharpe" in delta
    assert "cagr" in delta
    # Delta values are floats
    for v in delta.values():
        assert isinstance(v, float)


def test_survivorship_random_dist_has_metric_columns():
    repo = _repo()
    strategy = SimpleWeightStrategy()
    report = verify.survivorship_check(strategy, repo, _BASE_CONFIG, n_random_universes=5)

    df = report.random_metrics_distribution
    assert "sharpe" in df.columns
    assert "cagr" in df.columns


def test_survivorship_all_three_runs_complete():
    """All three run types (PIT, static, random) should complete without error."""
    repo = _repo()
    strategy = SimpleWeightStrategy()
    report = verify.survivorship_check(strategy, repo, _BASE_CONFIG, n_random_universes=3)

    # PIT metrics
    assert report.pit_metrics.cagr is not None
    # Static metrics
    assert report.static_metrics.cagr is not None
    # Random distribution
    assert not report.random_metrics_distribution.empty


def test_survivorship_seeded_reproducible():
    """Same seed produces same random distribution."""
    repo = _repo()
    strategy = SimpleWeightStrategy()
    report1 = verify.survivorship_check(strategy, repo, _BASE_CONFIG, n_random_universes=5)
    report2 = verify.survivorship_check(strategy, repo, _BASE_CONFIG, n_random_universes=5)

    sharpes1 = report1.random_metrics_distribution["sharpe"].tolist()
    sharpes2 = report2.random_metrics_distribution["sharpe"].tolist()
    assert sharpes1 == pytest.approx(sharpes2, abs=1e-9)


def test_survivorship_default_50_random_universes():
    """Default n_random_universes=50 produces a 50-row distribution."""
    repo = _repo()
    strategy = SimpleWeightStrategy()
    report = verify.survivorship_check(strategy, repo, _BASE_CONFIG)

    # Allow for a small number of failures, but expect close to 50
    assert len(report.random_metrics_distribution) >= 45
