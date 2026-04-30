"""Tests for FilingsSection, ProfileSection, and qualitative Dossier integration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from ah_research.analysis.dossier import FilingsSection, ProfileSection

# Fixture paths — relative to repo root
FIXTURES_FILINGS = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "filings"
)
FIXTURES_PROFILES = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"
)


# ── Task 2 tests ──────────────────────────────────────────────────────────────


def test_filings_section_is_frozen():
    s = FilingsSection(
        n_annual=3,
        latest_annual_year=2024,
        has_ipo=True,
        n_research=2,
        latest_research_date=date(2024, 3, 15),
        latest_annual_path="data/filings/X/年报-2024.md",
    )
    with pytest.raises(FrozenInstanceError):
        s.n_annual = 99  # type: ignore[misc]


def test_profile_section_is_frozen():
    s = ProfileSection(
        has_profile=True,
        latest_profile_date=date(2026, 4, 28),
        section_names=("§1", "§2"),
        latest_profile_path="profiles/X-2026-04-28.md",
    )
    with pytest.raises(FrozenInstanceError):
        s.has_profile = False  # type: ignore[misc]


def test_filings_section_defaults_for_empty():
    s = FilingsSection(
        n_annual=0,
        latest_annual_year=None,
        has_ipo=False,
        n_research=0,
        latest_research_date=None,
        latest_annual_path=None,
    )
    assert s.n_annual == 0
    assert s.latest_annual_year is None


def test_profile_section_empty():
    s = ProfileSection(
        has_profile=False,
        latest_profile_date=None,
        section_names=(),
        latest_profile_path=None,
    )
    assert s.has_profile is False
    assert s.section_names == ()


# ── Task 3 tests ──────────────────────────────────────────────────────────────

from ah_research.analysis.dossier import build_dossier  # noqa: E402
from ah_research.filings import FilingsRepository, ProfileRepository  # noqa: E402
from tests.fixtures.phase2.synthetic_market import build_synthetic_market  # noqa: E402


def _make_repo():
    """Return a synthetic DataRepository that build_dossier can use."""
    return build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )


def test_dossier_qualitative_populates_both_sections():
    repo = _make_repo()
    filings = FilingsRepository(root=FIXTURES_FILINGS)
    profiles = ProfileRepository(root=FIXTURES_PROFILES)
    d = build_dossier(
        "600000.SH",
        repo,
        asof=date(2024, 12, 31),
        include_qualitative=True,
        filings_repo=filings,
        profiles_repo=profiles,
    )
    assert d.filings_section is not None
    assert d.filings_section.n_annual == 2  # fixture has 2 annuals
    assert d.filings_section.has_ipo is True
    assert d.profile_section is not None
    assert d.profile_section.has_profile is True
    assert "§1 能力圈" in d.profile_section.section_names


def test_dossier_qualitative_off_leaves_sections_none():
    repo = _make_repo()
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31), include_qualitative=False)
    assert d.filings_section is None
    assert d.profile_section is None


def test_dossier_qualitative_empty_symbol_returns_empty_sections():
    """A symbol with no filings/profile on disk should yield populated-but-empty sections, not None."""
    repo = _make_repo()
    filings = FilingsRepository(root=FIXTURES_FILINGS)
    profiles = ProfileRepository(root=FIXTURES_PROFILES)
    d = build_dossier(
        "600000.SH",
        repo,
        asof=date(2024, 12, 31),
        include_qualitative=True,
        filings_repo=filings,
        profiles_repo=profiles,
        _qualitative_symbol_override="999999.SH",
    )
    assert d.filings_section is not None
    assert d.filings_section.n_annual == 0
    assert d.filings_section.has_ipo is False
    assert d.profile_section is not None
    assert d.profile_section.has_profile is False


# ── Task 4 tests ──────────────────────────────────────────────────────────────


def test_dossier_to_markdown_includes_qualitative_headers():
    repo = _make_repo()
    filings = FilingsRepository(root=FIXTURES_FILINGS)
    profiles = ProfileRepository(root=FIXTURES_PROFILES)
    d = build_dossier(
        "600000.SH",
        repo,
        asof=date(2024, 12, 31),
        include_qualitative=True,
        filings_repo=filings,
        profiles_repo=profiles,
    )
    md = d.to_markdown()
    assert "## Filings inventory" in md
    assert "## Qualitative profile" in md
    assert "Annual reports: 2" in md or "Annual: 2" in md  # either style


def test_dossier_to_markdown_omits_headers_when_sections_none():
    repo = _make_repo()
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31), include_qualitative=False)
    md = d.to_markdown()
    assert "## Filings inventory" not in md
    assert "## Qualitative profile" not in md


def test_dossier_to_dict_includes_qualitative_fields():
    repo = _make_repo()
    filings = FilingsRepository(root=FIXTURES_FILINGS)
    profiles = ProfileRepository(root=FIXTURES_PROFILES)
    d = build_dossier(
        "600000.SH",
        repo,
        asof=date(2024, 12, 31),
        include_qualitative=True,
        filings_repo=filings,
        profiles_repo=profiles,
    )
    dct = d.to_dict()
    assert "filings_section" in dct
    assert dct["filings_section"]["n_annual"] == 2
    assert "profile_section" in dct
    assert dct["profile_section"]["has_profile"] is True
