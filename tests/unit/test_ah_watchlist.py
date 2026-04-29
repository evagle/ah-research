"""Tests for the ``ah watchlist`` CLI subcommands (Task 18)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from typer.testing import CliRunner

from ah_research.cli import app

runner = CliRunner()

_PATCH_STORE = "ah_research.scripts.ah_watchlist.WatchlistStore"


def _mock_watchlist(name: str = "test_wl", symbols: list[str] | None = None) -> MagicMock:
    wl = MagicMock()
    wl.name = name
    wl.description = "Test watchlist"
    wl.symbols = [MagicMock(__str__=lambda s, _sym=sym: _sym) for sym in (symbols or ["600000.SH"])]
    wl.created_at = pd.Timestamp("2024-01-01")
    wl.updated_at = pd.Timestamp("2024-01-01")
    return wl


def test_watchlist_list_empty() -> None:
    with patch(_PATCH_STORE) as mock_cls:
        mock_cls.return_value.list_all.return_value = []
        result = runner.invoke(app, ["watchlist", "list"])
    assert result.exit_code == 0
    assert "No watchlists" in result.output or result.output.strip() == "" or "0" in result.output


def test_watchlist_list_shows_names() -> None:
    with patch(_PATCH_STORE) as mock_cls:
        mock_cls.return_value.list_all.return_value = [
            _mock_watchlist("alpha"),
            _mock_watchlist("beta"),
        ]
        result = runner.invoke(app, ["watchlist", "list"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output


def test_watchlist_create() -> None:
    with patch(_PATCH_STORE) as mock_cls:
        mock_cls.return_value.create.return_value = _mock_watchlist("my_picks")
        result = runner.invoke(
            app,
            ["watchlist", "create", "my_picks", "--symbols", "600000.SH,000001.SZ"],
        )
    assert result.exit_code == 0
    mock_cls.return_value.create.assert_called_once()
    call_args = mock_cls.return_value.create.call_args
    assert call_args.kwargs.get("name") == "my_picks" or call_args.args[0] == "my_picks"


def test_watchlist_create_with_description() -> None:
    with patch(_PATCH_STORE) as mock_cls:
        mock_cls.return_value.create.return_value = _mock_watchlist("my_picks")
        result = runner.invoke(
            app,
            [
                "watchlist",
                "create",
                "my_picks",
                "--symbols",
                "600000.SH",
                "--description",
                "My test picks",
            ],
        )
    assert result.exit_code == 0


def test_watchlist_snapshot() -> None:
    snap = MagicMock()
    snap.rows = pd.DataFrame({"symbol": ["600000.SH"], "price": [10.0]})
    with patch(_PATCH_STORE) as mock_cls:
        mock_cls.return_value.snapshot.return_value = snap
        result = runner.invoke(app, ["watchlist", "snapshot", "my_picks", "--asof", "2024-06-30"])
    assert result.exit_code == 0


def test_watchlist_diff() -> None:
    diff_df = pd.DataFrame({"symbol": ["600000.SH"], "price_delta": [1.5]})
    with patch(_PATCH_STORE) as mock_cls:
        mock_cls.return_value.diff_snapshots.return_value = diff_df
        result = runner.invoke(
            app,
            [
                "watchlist",
                "diff",
                "my_picks",
                "--earlier",
                "2024-01-01",
                "--later",
                "2024-06-30",
            ],
        )
    assert result.exit_code == 0


def test_watchlist_export(tmp_path: Path) -> None:
    out_path = tmp_path / "wl.yaml"
    with patch(_PATCH_STORE) as mock_cls:
        mock_cls.return_value.export_yaml.return_value = None
        result = runner.invoke(app, ["watchlist", "export", "my_picks", "--out", str(out_path)])
    assert result.exit_code == 0
    mock_cls.return_value.export_yaml.assert_called_once()


def test_watchlist_import(tmp_path: Path) -> None:
    yaml_path = tmp_path / "wl.yaml"
    yaml_path.write_text("name: my_picks\nsymbols: [600000.SH]\n")
    with patch(_PATCH_STORE) as mock_cls:
        mock_cls.return_value.import_yaml.return_value = _mock_watchlist("my_picks")
        result = runner.invoke(app, ["watchlist", "import", str(yaml_path)])
    assert result.exit_code == 0
    mock_cls.return_value.import_yaml.assert_called_once()
