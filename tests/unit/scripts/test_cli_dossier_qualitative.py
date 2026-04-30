"""Tests for the --qualitative / --no-qualitative flag on ``ah dossier``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ah_research.cli import app

runner = CliRunner()


def _make_mock_dossier() -> MagicMock:
    dossier = MagicMock()
    dossier.to_markdown.return_value = "# Dossier\n\nok\n"
    return dossier


def test_qualitative_flag_default_on() -> None:
    """With no flag (default), include_qualitative=True is passed to build_dossier."""
    with (
        patch("ah_research.scripts.ah_dossier.build_dossier") as mock_build,
        patch("ah_research.scripts.ah_dossier._make_repo") as mock_repo,
    ):
        mock_repo.return_value = MagicMock()
        mock_build.return_value = _make_mock_dossier()

        result = runner.invoke(app, ["dossier", "600000.SH"])

    assert result.exit_code == 0
    assert mock_build.called
    _, kwargs = mock_build.call_args
    assert kwargs.get("include_qualitative", True) is True


def test_no_qualitative_flag() -> None:
    """--no-qualitative passes include_qualitative=False to build_dossier."""
    with (
        patch("ah_research.scripts.ah_dossier.build_dossier") as mock_build,
        patch("ah_research.scripts.ah_dossier._make_repo") as mock_repo,
    ):
        mock_repo.return_value = MagicMock()
        mock_build.return_value = _make_mock_dossier()

        result = runner.invoke(app, ["dossier", "600000.SH", "--no-qualitative"])

    assert result.exit_code == 0
    assert mock_build.called
    _, kwargs = mock_build.call_args
    assert kwargs.get("include_qualitative") is False
