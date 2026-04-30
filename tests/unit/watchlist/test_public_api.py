"""Tests that the watchlist package public API re-exports are importable."""

from __future__ import annotations


def test_watchlist_store_importable():
    from ah_research.watchlist import WatchlistStore

    assert WatchlistStore is not None


def test_watchlist_importable():
    from ah_research.watchlist import Watchlist

    assert Watchlist is not None


def test_watchlist_snapshot_importable():
    from ah_research.watchlist import WatchlistSnapshot

    assert WatchlistSnapshot is not None


def test_all_names_in_dunder_all():
    import ah_research.watchlist as pkg

    expected = {"WatchlistStore", "Watchlist", "WatchlistSnapshot"}
    assert expected.issubset(set(pkg.__all__))


def test_portfolio_phase3_api_importable():
    """portfolio/__init__.py exports both Phase 2 and Phase 3 names."""
    from ah_research.portfolio import (
        Constraint,
        ConstraintResult,
        ConstructionReport,
        Constructor,
        cap_at,
        sector_neutralize,
        signal_to_weights,
        top_quantile_weights,
    )

    for obj in (
        Constraint,
        ConstraintResult,
        ConstructionReport,
        Constructor,
        cap_at,
        sector_neutralize,
        signal_to_weights,
        top_quantile_weights,
    ):
        assert obj is not None
