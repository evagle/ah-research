from __future__ import annotations

from typer.testing import CliRunner

from ah_research.cli import app


def test_ah_construct_help_works() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["construct", "--help"])
    assert result.exit_code == 0
    assert "weight-by" in result.stdout or "weight_by" in result.stdout
