"""CLI smoke tests for `ah profile grade` — no real API calls."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ah_research.filings.grading import GradedProfile
from ah_research.filings.types import Profile
from ah_research.scripts.ah_profile import profile_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"
runner = CliRunner()

_FAKE_PROFILE = Profile(
    symbol="600000.SH",
    date=date(2026, 4, 28),
    path=Path("profiles/600000.SH-2026-04-28.md"),
    text="Sample profile text.",
)

_FAKE_GRADE = GradedProfile(
    profile=_FAKE_PROFILE,
    moat_grade="A",
    mgmt_grade="B",
    redflag_count=1,
    confidence=0.75,
    rationale="Strong brand. Competent management. One minor red flag. Solid overall.",
    model="claude-sonnet-4-6",
    content_hash="abc123" * 10 + "abcd",
)


def _mock_grader_grade(profile: Profile, *, force: bool = False) -> GradedProfile:
    return _FAKE_GRADE


# ---------------------------------------------------------------------------
# Test 1: basic grade call succeeds and shows grade fields
# ---------------------------------------------------------------------------


def test_grade_basic() -> None:
    with (
        patch("anthropic.Anthropic") as mock_anthropic_cls,
        patch("ah_research.filings.grading.ProfileGrader") as mock_grader_cls,
    ):
        mock_grader_instance = MagicMock()
        mock_grader_instance.grade.side_effect = _mock_grader_grade
        mock_grader_cls.return_value = mock_grader_instance
        mock_anthropic_cls.return_value = MagicMock()

        result = runner.invoke(
            profile_app,
            ["grade", "600000.SH", "--root", str(FIXTURES_ROOT)],
        )

    assert result.exit_code == 0, result.output
    assert "moat_grade" in result.output
    assert "A" in result.output
    assert "Rationale" in result.output


# ---------------------------------------------------------------------------
# Test 2: --force flag is passed through to grader
# ---------------------------------------------------------------------------


def test_grade_force_flag() -> None:
    with (
        patch("anthropic.Anthropic") as mock_anthropic_cls,
        patch("ah_research.filings.grading.ProfileGrader") as mock_grader_cls,
    ):
        mock_grader_instance = MagicMock()
        mock_grader_instance.grade.side_effect = _mock_grader_grade
        mock_grader_cls.return_value = mock_grader_instance
        mock_anthropic_cls.return_value = MagicMock()

        result = runner.invoke(
            profile_app,
            ["grade", "600000.SH", "--force", "--root", str(FIXTURES_ROOT)],
        )

    assert result.exit_code == 0, result.output
    # Verify grade was called with force=True
    call_kwargs = mock_grader_instance.grade.call_args
    assert call_kwargs.kwargs.get("force") is True


# ---------------------------------------------------------------------------
# Test 3: missing symbol exits with code 1
# ---------------------------------------------------------------------------


def test_grade_missing_symbol_exits_1() -> None:
    with (
        patch("anthropic.Anthropic") as mock_anthropic_cls,
        patch("ah_research.filings.grading.ProfileGrader") as mock_grader_cls,
    ):
        mock_grader_instance = MagicMock()
        mock_grader_cls.return_value = mock_grader_instance
        mock_anthropic_cls.return_value = MagicMock()

        result = runner.invoke(
            profile_app,
            ["grade", "999999.XX", "--root", str(FIXTURES_ROOT)],
        )

    assert result.exit_code != 0
    # ProfileGrader.grade should never have been called
    mock_grader_instance.grade.assert_not_called()
