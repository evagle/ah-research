"""Tests for the ``ah dossier`` CLI command (Task 17)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ah_research.cli import app

runner = CliRunner()


def _make_mock_dossier(language: str = "en") -> MagicMock:
    """Return a minimal mock Dossier that satisfies the CLI code path."""
    dossier = MagicMock()
    dossier.to_markdown.return_value = f"# Dossier\n\nOverview section ({language})\n"
    return dossier


def test_dossier_prints_markdown(tmp_path: Path) -> None:
    """``ah dossier 600000.SH`` prints markdown to stdout."""
    with (
        patch("ah_research.scripts.ah_dossier.build_dossier") as mock_build,
        patch("ah_research.scripts.ah_dossier._make_repo") as mock_make_repo,
    ):
        mock_make_repo.return_value = MagicMock()
        mock_build.return_value = _make_mock_dossier()

        result = runner.invoke(app, ["dossier", "600000.SH"])

    assert result.exit_code == 0
    assert "# Dossier" in result.output


def test_dossier_writes_file(tmp_path: Path) -> None:
    """``ah dossier --out path.md`` writes markdown to file."""
    out_path = tmp_path / "output.md"
    with (
        patch("ah_research.scripts.ah_dossier.build_dossier") as mock_build,
        patch("ah_research.scripts.ah_dossier._make_repo") as mock_make_repo,
    ):
        mock_make_repo.return_value = MagicMock()
        mock_build.return_value = _make_mock_dossier()

        result = runner.invoke(app, ["dossier", "600000.SH", "--out", str(out_path)])

    assert result.exit_code == 0
    assert out_path.exists()
    assert "# Dossier" in out_path.read_text()


def test_dossier_asof_flag(tmp_path: Path) -> None:
    """``ah dossier --asof 2023-12-31`` passes the parsed date to build_dossier."""
    with (
        patch("ah_research.scripts.ah_dossier.build_dossier") as mock_build,
        patch("ah_research.scripts.ah_dossier._make_repo") as mock_make_repo,
    ):
        mock_make_repo.return_value = MagicMock()
        mock_build.return_value = _make_mock_dossier()

        result = runner.invoke(app, ["dossier", "600000.SH", "--asof", "2023-12-31"])

    assert result.exit_code == 0
    call_kwargs = mock_build.call_args
    assert call_kwargs is not None
    assert call_kwargs.kwargs.get("asof") == date(2023, 12, 31) or (
        len(call_kwargs.args) > 2 and call_kwargs.args[2] == date(2023, 12, 31)
    )


def test_dossier_language_flag(tmp_path: Path) -> None:
    """``ah dossier --language zh`` passes language to to_markdown."""
    with (
        patch("ah_research.scripts.ah_dossier.build_dossier") as mock_build,
        patch("ah_research.scripts.ah_dossier._make_repo") as mock_make_repo,
    ):
        mock_make_repo.return_value = MagicMock()
        dossier_mock = _make_mock_dossier(language="zh")
        mock_build.return_value = dossier_mock

        result = runner.invoke(app, ["dossier", "600000.SH", "--language", "zh"])

    assert result.exit_code == 0
    dossier_mock.to_markdown.assert_called_once_with(language="zh")
