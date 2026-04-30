"""Smoke tests for the `ah filings summary` CLI subcommand."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ah_research.scripts.ah_filings import filings_app

PHASE4_2_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2"
FILINGS_ROOT = PHASE4_2_ROOT / "filings"
PROFILES_ROOT = PHASE4_2_ROOT / "profiles"

runner = CliRunner()


def test_summary_with_fixtures_exits_zero_and_shows_symbol() -> None:
    result = runner.invoke(
        filings_app,
        [
            "summary",
            "--root-filings",
            str(FILINGS_ROOT),
            "--root-profiles",
            str(PROFILES_ROOT),
        ],
    )
    assert result.exit_code == 0, result.output
    # Rich may truncate wide rows in a narrow terminal; check for the prefix that
    # is always present whether the cell is "600000.SH" or "6000…"
    assert "6000" in result.output


def test_summary_empty_roots_exits_one_with_message(tmp_path: Path) -> None:
    result = runner.invoke(
        filings_app,
        [
            "summary",
            "--root-filings",
            str(tmp_path / "filings"),
            "--root-profiles",
            str(tmp_path / "profiles"),
        ],
    )
    assert result.exit_code == 1, result.output
    assert "No symbols" in result.output


def test_summary_sort_by_symbol_exits_zero() -> None:
    result = runner.invoke(
        filings_app,
        [
            "summary",
            "--sort-by",
            "symbol",
            "--root-filings",
            str(FILINGS_ROOT),
            "--root-profiles",
            str(PROFILES_ROOT),
        ],
    )
    assert result.exit_code == 0, result.output
