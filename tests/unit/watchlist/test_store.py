"""Unit tests for WatchlistStore CRUD and YAML interop."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ah_research.watchlist.store import WatchlistStore


def _fresh_store() -> WatchlistStore:
    tmpdir = Path(tempfile.mkdtemp())
    return WatchlistStore(cache_path=tmpdir / "cache.duckdb")


def test_create_get_list() -> None:
    store = _fresh_store()
    wl = store.create("my_picks", symbols=["600000.SH", "000001.SZ"], description="Test")
    assert wl.name == "my_picks"
    assert len(wl.symbols) == 2

    got = store.get("my_picks")
    assert got.name == "my_picks"

    all_wls = store.list_all()
    assert any(x.name == "my_picks" for x in all_wls)


def test_add_remove_symbol() -> None:
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH"])
    wl = store.add_symbol("my_picks", "000001.SZ")
    assert len(wl.symbols) == 2
    wl = store.remove_symbol("my_picks", "600000.SH")
    assert len(wl.symbols) == 1
    # remaining symbol is 000001.SZ → code keeps leading zeros
    assert wl.symbols[0].code == "000001"


def test_duplicate_create_raises() -> None:
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH"])
    with pytest.raises(ValueError, match="already exists"):
        store.create("my_picks", symbols=["000001.SZ"])


def test_delete_removes_definition_and_snapshots() -> None:
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH"])
    store.delete("my_picks")
    with pytest.raises(KeyError):
        store.get("my_picks")


def test_yaml_export_import_roundtrip(tmp_path: Path) -> None:
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH", "000001.SZ"], description="Test")
    path = tmp_path / "wl.yaml"
    store.export_yaml("my_picks", path)
    assert path.exists()

    store2 = _fresh_store()
    imported = store2.import_yaml(path)
    assert imported.name == "my_picks"
    assert len(imported.symbols) == 2


def test_yaml_roundtrip_unicode(tmp_path: Path) -> None:
    store = _fresh_store()
    store.create("chinese_name", symbols=["600000.SH"], description="测试描述")
    path = tmp_path / "wl_zh.yaml"
    store.export_yaml("chinese_name", path)
    raw = path.read_text()
    # Unicode characters should be preserved (not escaped) thanks to allow_unicode=True
    assert "测试描述" in raw

    store2 = _fresh_store()
    imported = store2.import_yaml(path)
    assert imported.description == "测试描述"


def test_update_description() -> None:
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH"], description="old")
    updated = store.update("my_picks", description="new desc")
    assert updated.description == "new desc"
    assert len(updated.symbols) == 1


def test_get_missing_raises_key_error() -> None:
    store = _fresh_store()
    with pytest.raises(KeyError):
        store.get("nonexistent")


def test_add_symbol_idempotent() -> None:
    store = _fresh_store()
    store.create("my_picks", symbols=["600000.SH"])
    store.add_symbol("my_picks", "600000.SH")  # duplicate
    wl = store.get("my_picks")
    assert len(wl.symbols) == 1


def test_list_all_empty() -> None:
    store = _fresh_store()
    assert store.list_all() == []


def test_multiple_watchlists() -> None:
    store = _fresh_store()
    store.create("value", symbols=["600000.SH"])
    store.create("growth", symbols=["000001.SZ"])
    all_wls = store.list_all()
    names = [w.name for w in all_wls]
    assert "value" in names
    assert "growth" in names
    assert len(names) == 2
