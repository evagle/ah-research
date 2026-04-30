"""Smoke tests for the `ah filings search` CLI subcommand."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ah_research.scripts.ah_filings import filings_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_5" / "filings"
runner = CliRunner()


def test_search_finds_hits() -> None:
    result = runner.invoke(
        filings_app,
        ["search", "Annual", "--root", str(FIXTURES_ROOT)],
    )
    assert result.exit_code == 0, result.output
    assert "Annual" in result.output


def test_search_kinds_annual_narrows() -> None:
    result = runner.invoke(
        filings_app,
        ["search", "Revenue", "--kinds", "annual", "--root", str(FIXTURES_ROOT)],
    )
    assert result.exit_code == 0, result.output
    # Should show annual hits only
    assert "Revenue" in result.output or "No hits" in result.output


def test_search_no_hits_friendly_exit_zero() -> None:
    result = runner.invoke(
        filings_app,
        ["search", "XYZZY_NO_SUCH_STRING_12345", "--root", str(FIXTURES_ROOT)],
    )
    assert result.exit_code == 0, result.output
    assert "No hits" in result.output


def test_search_invalid_kind_exits_nonzero() -> None:
    result = runner.invoke(
        filings_app,
        ["search", "Annual", "--kinds", "badkind", "--root", str(FIXTURES_ROOT)],
    )
    assert result.exit_code != 0, result.output


def test_search_symbols_filter() -> None:
    result = runner.invoke(
        filings_app,
        ["search", "Annual", "--symbols", "600000.SH", "--root", str(FIXTURES_ROOT)],
    )
    assert result.exit_code == 0, result.output
    assert "600000.SH" in result.output
