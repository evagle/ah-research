from __future__ import annotations

import re

from typer.testing import CliRunner

from ah_research.cli import app

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI escape sequences and collapse whitespace.

    CI terminals have a narrower COLUMNS than local runs, so Rich wraps long
    option names (``--weight-by``) across lines and injects ANSI color codes
    between fragments. Both effects break naïve substring assertions.
    """
    return re.sub(r"\s+", " ", _ANSI.sub("", text))


def test_ah_construct_help_works() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["construct", "--help"])
    assert result.exit_code == 0
    plain = _plain(result.stdout)
    assert "--weight-by" in plain or "--weight_by" in plain
    assert "--asof" in plain
