from pathlib import Path

from typer.testing import CliRunner

from ah_research.scripts.ah_profile import profile_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"
runner = CliRunner()


def test_list_all():
    result = runner.invoke(profile_app, ["list", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0, result.output
    assert "600000.SH" in result.output


def test_show_latest():
    result = runner.invoke(profile_app, ["show", "600000.SH", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0
    assert "§1 能力圈" in result.output


def test_show_list_sections():
    result = runner.invoke(
        profile_app, ["show", "600000.SH", "--list-sections", "--root", str(FIXTURES_ROOT)]
    )
    assert result.exit_code == 0
    assert "§1 能力圈" in result.output
    assert "§2 护城河" in result.output


def test_show_single_section():
    result = runner.invoke(
        profile_app, ["show", "600000.SH", "--section", "§1 能力圈", "--root", str(FIXTURES_ROOT)]
    )
    assert result.exit_code == 0
    assert "圈内判断" in result.output


def test_show_unknown_symbol_nonzero():
    result = runner.invoke(profile_app, ["show", "999999.SH", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code != 0
