from pathlib import Path

from typer.testing import CliRunner

from ah_research.scripts.ah_filings import filings_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "filings"
runner = CliRunner()


def test_list_all():
    result = runner.invoke(filings_app, ["list", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0, result.output
    assert "600000.SH" in result.output
    assert "000001.SZ" in result.output


def test_list_for_symbol():
    result = runner.invoke(filings_app, ["list", "600000.SH", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0
    assert "annual" in result.output.lower()
    assert "ipo" in result.output.lower()
    assert "research" in result.output.lower()


def test_show_annual():
    result = runner.invoke(
        filings_app, ["show", "600000.SH", "annual", "--year", "2024", "--root", str(FIXTURES_ROOT)]
    )
    assert result.exit_code == 0
    assert "Annual 2024" in result.output


def test_show_missing_annual_exits_nonzero():
    result = runner.invoke(
        filings_app, ["show", "600000.SH", "annual", "--year", "1999", "--root", str(FIXTURES_ROOT)]
    )
    assert result.exit_code != 0
