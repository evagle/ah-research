"""Integration test: screener → WatchlistStore.create → snapshot → diff flow."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from ah_research.analysis.screener import ScreenResult, run_screen
from ah_research.watchlist.snapshot import WatchlistSnapshot
from ah_research.watchlist.store import WatchlistStore
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

_SYMBOLS = ["600000.SH", "000001.SZ", "600519.SH", "600036.SH"]
_START = date(2023, 1, 1)
_END = date(2024, 12, 31)


@pytest.fixture(scope="module")
def market_repo():
    return build_synthetic_market(start=_START, end=_END, symbols=_SYMBOLS)


@pytest.fixture()
def store():
    tmpdir = Path(tempfile.mkdtemp())
    return WatchlistStore(cache_path=tmpdir / "cache.duckdb")


def test_screener_to_watchlist_create(market_repo, store):
    """run_screen → create a WatchlistStore entry from the passed symbols."""
    result = run_screen(
        conditions={"pe": (">", 0.0)},
        repo=market_repo,
        asof=date(2024, 12, 31),
    )
    assert isinstance(result, ScreenResult)
    assert result.n_input > 0

    # Persist the passed symbols into a watchlist
    symbols = result.frame["symbol"].tolist() if not result.frame.empty else _SYMBOLS[:2]
    wl = store.create("value_screen", symbols=symbols, description="PE > 0 screen")
    assert wl.name == "value_screen"
    assert len(wl.symbols) == len(symbols)


def test_screener_result_asof_matches(market_repo):
    """ScreenResult.asof matches the requested date."""
    asof = date(2024, 12, 31)
    result = run_screen(
        conditions={"pe": (">", 0.0)},
        repo=market_repo,
        asof=asof,
    )
    assert result.asof == asof
    assert result.n_passed <= result.n_input


def test_watchlist_snapshot_and_diff(market_repo, store):
    """Create watchlist → take two snapshots → diff returns a DataFrame."""
    store.create("picks", symbols=_SYMBOLS[:2])

    snap1 = store.snapshot("picks", market_repo, asof=date(2024, 6, 30))
    assert isinstance(snap1, WatchlistSnapshot)
    assert len(snap1.rows) == 2

    snap2 = store.snapshot("picks", market_repo, asof=date(2024, 12, 31))
    assert isinstance(snap2, WatchlistSnapshot)
    assert len(snap2.rows) == 2

    diff = store.diff_snapshots("picks", earlier=date(2024, 6, 30), later=date(2024, 12, 31))
    assert diff is not None
    assert hasattr(diff, "columns")
    # diff should have a numeric delta column for at least one metric
    delta_cols = [c for c in diff.columns if "delta" in c.lower() or c.endswith("_change")]
    assert len(delta_cols) > 0


def test_watchlist_conditions_preserved(market_repo, store):
    """Conditions dict is preserved on ScreenResult and stored as metadata."""
    conds = {"pe": ("<", 50.0)}
    result = run_screen(conditions=conds, repo=market_repo, asof=date(2024, 12, 31))
    assert result.conditions_applied == conds

    # Can also store screen_conditions on a watchlist
    syms = result.frame["symbol"].tolist() or _SYMBOLS[:1]
    wl = store.create("pe_screen", symbols=syms, screen_conditions={"pe": ["<", 50.0]})
    assert wl.screen_conditions is not None
