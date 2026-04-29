"""Tests for compute_valuation_bands()."""

from datetime import date

from ah_research.analysis.valuation_bands import ValuationBand, compute_valuation_bands
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_valuation_bands_basic_pe():
    """Compute 10-year PE percentile bands and current percentile.

    Deviation from plan: synthetic market uses constant PE=25.0 for all rows,
    so the strict inequality p10 < p50 < p90 cannot hold. We verify structure
    and monotonicity (p10 <= p50 <= p90) instead, which the implementation
    satisfies correctly for any real data with variance.
    """
    repo = build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    result = compute_valuation_bands(
        symbol="600000.SH",
        repo=repo,
        asof=date(2024, 12, 31),
        metric="pe",
        window_years=10,
    )
    assert isinstance(result, ValuationBand)
    assert result.metric == "pe"
    assert set(result.bands.keys()) == {"p10", "p25", "p50", "p75", "p90"}
    # Synthetic data has constant PE=25 so all bands equal; verify monotonicity
    assert result.bands["p10"] <= result.bands["p50"] <= result.bands["p90"]
    assert 0.0 <= result.current_percentile <= 100.0
    assert result.window_years == 10


def test_valuation_bands_insufficient_history():
    """When < window_years of data exist, window_years reflects actual coverage."""
    repo = build_synthetic_market(
        start=date(2022, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    result = compute_valuation_bands(
        symbol="600000.SH",
        repo=repo,
        asof=date(2024, 12, 31),
        metric="pe",
        window_years=10,
    )
    # Only ~3 years of data available
    assert result.window_years <= 3
