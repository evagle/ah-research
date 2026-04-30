"""Live integration test for ProfileGrader — skipped unless AH_RESEARCH_LIVE=1."""

from __future__ import annotations

import os

import pytest

from ah_research.filings.grading import GradedProfile, ProfileGrader
from ah_research.filings.profile_repository import ProfileRepository

PROFILES_ROOT_ENV = os.environ.get("AH_RESEARCH_PROFILES_ROOT", "profiles")


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("AH_RESEARCH_LIVE") != "1",
    reason="Set AH_RESEARCH_LIVE=1 to run live API tests",
)
def test_grade_live() -> None:
    """Grade a real profile via Claude API — requires ANTHROPIC_API_KEY and profiles/ dir."""
    from pathlib import Path

    from anthropic import Anthropic

    repo = ProfileRepository(root=Path(PROFILES_ROOT_ENV))
    profiles = repo.list_profiles()
    if not profiles:
        pytest.skip("No profiles found in profiles/ directory")

    profile = profiles[0]
    client = Anthropic()
    grader = ProfileGrader(client)

    result = grader.grade(profile)

    assert isinstance(result, GradedProfile)
    assert result.moat_grade in {"A", "B", "C", "D", "F"}
    assert result.mgmt_grade in {"A", "B", "C", "D", "F"}
    assert result.redflag_count >= 0
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.rationale) > 10
    assert len(result.content_hash) == 64
