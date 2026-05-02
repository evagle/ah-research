"""Unit tests for ah_research.filings.grading — no real API calls."""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ah_research.filings.grading import GradedProfile, ProfileGrader, ValidationError
from ah_research.filings.types import Profile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"


def _make_profile(text: str = "Test profile text about a company.") -> Profile:
    return Profile(
        symbol="600000.SH",
        date=date(2026, 4, 28),
        path=Path("profiles/600000.SH-2026-04-28.md"),
        text=text,
    )


def _make_mock_client(response_text: str) -> MagicMock:
    """Return a MagicMock Anthropic client with a canned response."""
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = response_text
    mock_response.content = [mock_block]
    client = MagicMock()
    client.messages.create.return_value = mock_response
    return client


_VALID_JSON = json.dumps(
    {
        "moat_grade": "A",
        "mgmt_grade": "B",
        "redflag_count": 2,
        "confidence": 0.8,
        "rationale": "The company has a strong brand. Management is competent. Minimal red flags. Overall solid.",
    }
)


# ---------------------------------------------------------------------------
# Test 1: grade() returns GradedProfile with correct fields
# ---------------------------------------------------------------------------


def test_grade_returns_correct_fields() -> None:
    client = _make_mock_client(_VALID_JSON)
    profile = _make_profile()
    with tempfile.TemporaryDirectory() as tmpdir:
        grader = ProfileGrader(client, cache_dir=Path(tmpdir) / "cache")
        result = grader.grade(profile)

    assert isinstance(result, GradedProfile)
    assert result.moat_grade == "A"
    assert result.mgmt_grade == "B"
    assert result.redflag_count == 2
    assert abs(result.confidence - 0.8) < 1e-9
    assert "brand" in result.rationale
    assert result.model == "claude-sonnet-4-6"
    assert len(result.content_hash) == 64  # sha256 hex


# ---------------------------------------------------------------------------
# Test 2: cache hit returns without invoking client
# ---------------------------------------------------------------------------


def test_cache_hit_no_api_call() -> None:
    client = _make_mock_client(_VALID_JSON)
    profile = _make_profile()
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        grader = ProfileGrader(client, cache_dir=cache_dir)
        # First call populates cache
        grader.grade(profile)
        assert client.messages.create.call_count == 1

        # Second call should hit cache — zero additional API calls
        result2 = grader.grade(profile)
        assert client.messages.create.call_count == 1  # still 1

    assert result2.moat_grade == "A"


# ---------------------------------------------------------------------------
# Test 3: cache miss invokes client exactly once
# ---------------------------------------------------------------------------


def test_cache_miss_invokes_client_once() -> None:
    client = _make_mock_client(_VALID_JSON)
    profile = _make_profile("A unique profile text that has never been graded before.")
    with tempfile.TemporaryDirectory() as tmpdir:
        grader = ProfileGrader(client, cache_dir=Path(tmpdir) / "cache")
        grader.grade(profile)

    assert client.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Test 4: malformed JSON raises ValidationError
# ---------------------------------------------------------------------------


def test_malformed_json_raises_validation_error() -> None:
    client = _make_mock_client("This is not JSON at all.")
    profile = _make_profile()
    with tempfile.TemporaryDirectory() as tmpdir:
        grader = ProfileGrader(client, cache_dir=Path(tmpdir) / "cache")
        with pytest.raises(ValidationError):
            grader.grade(profile)


# ---------------------------------------------------------------------------
# Test 5: invalid grade letter raises ValidationError
# ---------------------------------------------------------------------------


def test_invalid_grade_letter_raises_validation_error() -> None:
    bad_json = json.dumps(
        {
            "moat_grade": "Z",  # invalid
            "mgmt_grade": "B",
            "redflag_count": 0,
            "confidence": 0.5,
            "rationale": "Some rationale here.",
        }
    )
    client = _make_mock_client(bad_json)
    profile = _make_profile()
    with tempfile.TemporaryDirectory() as tmpdir:
        grader = ProfileGrader(client, cache_dir=Path(tmpdir) / "cache")
        with pytest.raises(ValidationError, match="moat_grade"):
            grader.grade(profile)


# ---------------------------------------------------------------------------
# Test 6: --force bypasses cache
# ---------------------------------------------------------------------------


def test_force_bypasses_cache() -> None:
    client = _make_mock_client(_VALID_JSON)
    profile = _make_profile()
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        grader = ProfileGrader(client, cache_dir=cache_dir)
        grader.grade(profile)
        assert client.messages.create.call_count == 1

        # Force re-grade even though cache exists
        grader.grade(profile, force=True)
        assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Test 7: content hash is stable across identical profiles
# ---------------------------------------------------------------------------


def test_content_hash_stable() -> None:
    text = "Identical profile text."
    p1 = _make_profile(text)
    p2 = Profile(
        symbol="000001.SZ",
        date=date(2026, 1, 1),
        path=Path("other.md"),
        text=text,
    )
    client = _make_mock_client(_VALID_JSON)
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        grader = ProfileGrader(client, cache_dir=cache_dir)
        r1 = grader.grade(p1)
        # p2 has same text — should hit cache written by p1
        r2 = grader.grade(p2)

    assert r1.content_hash == r2.content_hash
    # Only one API call because second hit cache
    assert client.messages.create.call_count == 1
