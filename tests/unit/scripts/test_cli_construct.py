from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
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


@pytest.fixture
def universe_json(tmp_path: Path) -> Path:
    """Write a tiny universe file so CLI has something to act on."""
    path = tmp_path / "universe.json"
    path.write_text(
        json.dumps({"600519.SH": 0.9, "000858.SZ": 0.6, "0700.HK": 0.3, "9988.HK": 0.1})
    )
    return path


def test_ah_construct_equal_weight_prints_table(universe_json: Path) -> None:
    """End-to-end: equal-weighted construction runs and emits a weights table.

    Options precede the positional ``UNIVERSE`` arg because
    ``construct_app`` uses ``invoke_without_command=True``; the click parser
    then treats the universe path as the last positional before COMMAND.
    """
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["construct", "--asof", "2025-12-31", "--weight-by", "equal", str(universe_json)],
    )
    assert result.exit_code == 0, result.stdout
    plain = _plain(result.stdout)
    assert "equal weights" in plain
    assert "600519.SH" in plain
    # Weights formatted to 4 decimal places.
    assert re.search(r"\d+\.\d{4}", plain) is not None


def test_ah_construct_unknown_objective_rejected(universe_json: Path) -> None:
    """Optimize mode with an unknown objective must exit non-zero."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "construct",
            "--asof",
            "2025-12-31",
            "--weight-by",
            "optimize",
            "--objective",
            "bogus_objective",
            str(universe_json),
        ],
    )
    assert result.exit_code != 0
