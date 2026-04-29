"""Unit tests for WatchlistSnapshot and snapshot methods on WatchlistStore."""

from __future__ import annotations

import tempfile
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from ah_research.watchlist.snapshot import WatchlistSnapshot
from ah_research.watchlist.store import WatchlistStore
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def _fresh() -> WatchlistStore:
    return WatchlistStore(cache_path=Path(tempfile.mkdtemp()) / "cache.duckdb")


# ── WatchlistSnapshot dataclass ───────────────────────────────────────────────


def test_snapshot_dataclass_frozen() -> None:
    import pandas as pd

    snap = WatchlistSnapshot(
        watchlist_name="test",
        snapshot_date=date(2024, 12, 31),
        rows=pd.DataFrame({"symbol": ["600000.SH"]}),
    )
    with pytest.raises(FrozenInstanceError):
        snap.watchlist_name = "other"  # type: ignore[misc]


# ── snapshot() ────────────────────────────────────────────────────────────────


def test_snapshot_creates_row_per_symbol() -> None:
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    store.create("my_picks", symbols=["600000.SH", "000001.SZ"])
    snap = store.snapshot("my_picks", repo, asof=date(2024, 12, 31))
    assert isinstance(snap, WatchlistSnapshot)
    assert len(snap.rows) == 2
    assert "symbol" in snap.rows.columns
    # At least one metric column should be present
    assert any(col in snap.rows.columns for col in ("price", "pe", "pb", "roe", "market_cap"))


def test_snapshot_returns_correct_watchlist_name_and_date() -> None:
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    store.create("my_picks", symbols=["600000.SH"])
    snap = store.snapshot("my_picks", repo, asof=date(2024, 6, 30))
    assert snap.watchlist_name == "my_picks"
    assert snap.snapshot_date == date(2024, 6, 30)


def test_snapshot_persisted_and_retrievable() -> None:
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    store.create("my_picks", symbols=["600000.SH"])
    store.snapshot("my_picks", repo, asof=date(2024, 12, 31))

    retrieved = store.get_snapshot("my_picks", date(2024, 12, 31))
    assert isinstance(retrieved, WatchlistSnapshot)
    assert len(retrieved.rows) == 1
    assert retrieved.rows["symbol"].iloc[0] == "600000.SH"


# ── immutability ──────────────────────────────────────────────────────────────


def test_snapshot_immutable_without_force() -> None:
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    store.create("my_picks", symbols=["600000.SH"])
    store.snapshot("my_picks", repo, asof=date(2024, 12, 31))
    with pytest.raises(ValueError, match="already exists"):
        store.snapshot("my_picks", repo, asof=date(2024, 12, 31))


def test_snapshot_force_overwrites() -> None:
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    store.create("my_picks", symbols=["600000.SH"])
    store.snapshot("my_picks", repo, asof=date(2024, 12, 31))
    # Should not raise
    snap2 = store.snapshot("my_picks", repo, asof=date(2024, 12, 31), force=True)
    assert isinstance(snap2, WatchlistSnapshot)


# ── list_snapshots ────────────────────────────────────────────────────────────


def test_list_snapshots_returns_sorted_dates() -> None:
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    store.create("my_picks", symbols=["600000.SH"])
    store.snapshot("my_picks", repo, asof=date(2024, 6, 30))
    store.snapshot("my_picks", repo, asof=date(2024, 12, 31))

    dates = store.list_snapshots("my_picks")
    assert len(dates) == 2
    assert dates[0] <= dates[1]


def test_list_snapshots_empty_before_any_snapshot() -> None:
    store = _fresh()
    store.create("my_picks", symbols=["600000.SH"])
    assert store.list_snapshots("my_picks") == []


# ── get_snapshot ──────────────────────────────────────────────────────────────


def test_get_snapshot_missing_raises_key_error() -> None:
    store = _fresh()
    store.create("my_picks", symbols=["600000.SH"])
    with pytest.raises(KeyError):
        store.get_snapshot("my_picks", date(2024, 12, 31))


# ── diff_snapshots ────────────────────────────────────────────────────────────


def test_diff_snapshots() -> None:
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    store.create("my_picks", symbols=["600000.SH", "000001.SZ"])
    store.snapshot("my_picks", repo, asof=date(2024, 6, 30))
    store.snapshot("my_picks", repo, asof=date(2024, 12, 31))

    diff = store.diff_snapshots("my_picks", earlier=date(2024, 6, 30), later=date(2024, 12, 31))
    assert hasattr(diff, "columns")
    assert "symbol" in diff.columns
    # At least one delta column must exist (e.g. pe_delta or price_delta)
    delta_cols = [c for c in diff.columns if c.endswith("_delta")]
    assert len(delta_cols) >= 1


def test_diff_snapshots_symbols_aligned() -> None:
    store = _fresh()
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    store.create("my_picks", symbols=["600000.SH", "000001.SZ"])
    store.snapshot("my_picks", repo, asof=date(2024, 6, 30))
    store.snapshot("my_picks", repo, asof=date(2024, 12, 31))

    diff = store.diff_snapshots("my_picks", earlier=date(2024, 6, 30), later=date(2024, 12, 31))
    assert set(diff["symbol"]) == {"600000.SH", "000001.SZ"}
