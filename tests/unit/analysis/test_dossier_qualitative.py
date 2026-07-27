"""Tests for FilingsSection, ProfileSection, and qualitative Dossier integration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from ah_research.analysis.dossier import FilingsSection, ProfileSection, build_dossier
from ah_research.filings import FilingsRepository, ProfileRepository
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ── Fixture paths ───────────────────────────────────────────────────────────

_FIXTURES_FILINGS = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "filings"
)
_FIXTURES_PROFILES = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"
)
_ASOF = date(2024, 12, 31)


# ── Shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def repo():
    """Synthetic 10-year repo for build_dossier."""
    return build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )


@pytest.fixture
def filings_repo() -> FilingsRepository:
    return FilingsRepository(root=_FIXTURES_FILINGS)


@pytest.fixture
def profiles_repo() -> ProfileRepository:
    return ProfileRepository(root=_FIXTURES_PROFILES)


@pytest.fixture
def qualitative_dossier(repo, filings_repo, profiles_repo):  # type: ignore[no-untyped-def]
    """A fully-populated qualitative dossier; reused across to_dict/markdown
    assertions so we don't rebuild it in every test."""
    return build_dossier(
        "600000.SH",
        repo,
        asof=_ASOF,
        include_qualitative=True,
        filings_repo=filings_repo,
        profiles_repo=profiles_repo,
    )


# ── frozen dataclass invariants ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("section_factory", "field_to_mutate", "new_value"),
    [
        (
            lambda: FilingsSection(
                n_annual=3,
                latest_annual_year=2024,
                has_ipo=True,
                n_research=2,
                latest_research_date=date(2024, 3, 15),
                latest_annual_path="data/filings/X/年报-2024.md",
            ),
            "n_annual",
            99,
        ),
        (
            lambda: ProfileSection(
                has_profile=True,
                latest_profile_date=date(2026, 4, 28),
                section_names=("§1", "§2"),
                latest_profile_path="profiles/X-2026-04-28.md",
            ),
            "has_profile",
            False,
        ),
    ],
    ids=["filings-section", "profile-section"],
)
def test_section_dataclass_is_frozen(
    section_factory,  # type: ignore[no-untyped-def]
    field_to_mutate: str,
    new_value: object,
) -> None:
    section = section_factory()
    with pytest.raises(FrozenInstanceError):
        setattr(section, field_to_mutate, new_value)


def test_filings_section_defaults_for_empty() -> None:
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


def test_profile_section_empty() -> None:
    s = ProfileSection(
        has_profile=False,
        latest_profile_date=None,
        section_names=(),
        latest_profile_path=None,
    )
    assert s.has_profile is False
    assert s.section_names == ()


# ── build_dossier with qualitative enabled ──────────────────────────────────


def test_qualitative_populates_both_sections(qualitative_dossier) -> None:  # type: ignore[no-untyped-def]
    d = qualitative_dossier
    assert d.filings_section is not None
    assert d.filings_section.n_annual == 2  # fixture has 2 annuals
    assert d.filings_section.has_ipo is True
    assert d.profile_section is not None
    assert d.profile_section.has_profile is True
    assert "§1 能力圈" in d.profile_section.section_names


def test_qualitative_off_leaves_sections_none(repo) -> None:  # type: ignore[no-untyped-def]
    d = build_dossier("600000.SH", repo, asof=_ASOF, include_qualitative=False)
    assert d.filings_section is None
    assert d.profile_section is None


def test_empty_symbol_returns_populated_but_empty_sections(
    repo, filings_repo, profiles_repo
) -> None:  # type: ignore[no-untyped-def]
    """A symbol with no filings/profile on disk yields populated-but-empty
    sections, not None (the contract for include_qualitative=True)."""
    d = build_dossier(
        "600000.SH",
        repo,
        asof=_ASOF,
        include_qualitative=True,
        filings_repo=filings_repo,
        profiles_repo=profiles_repo,
        _qualitative_symbol_override="999999.SH",
    )
    assert d.filings_section is not None
    assert d.filings_section.n_annual == 0
    assert d.filings_section.has_ipo is False
    assert d.profile_section is not None
    assert d.profile_section.has_profile is False


# ── markdown / dict serialisation ───────────────────────────────────────────


def test_to_markdown_includes_qualitative_headers(qualitative_dossier) -> None:  # type: ignore[no-untyped-def]
    md = qualitative_dossier.to_markdown()
    assert "## Filings inventory" in md
    assert "## Qualitative profile" in md
    assert "Annual reports: 2" in md or "Annual: 2" in md  # either style


def test_to_markdown_omits_headers_when_qualitative_off(repo) -> None:  # type: ignore[no-untyped-def]
    d = build_dossier("600000.SH", repo, asof=_ASOF, include_qualitative=False)
    md = d.to_markdown()
    assert "## Filings inventory" not in md
    assert "## Qualitative profile" not in md


def test_to_dict_includes_qualitative_fields(qualitative_dossier) -> None:  # type: ignore[no-untyped-def]
    dct = qualitative_dossier.to_dict()
    assert "filings_section" in dct
    assert dct["filings_section"]["n_annual"] == 2
    assert "profile_section" in dct
    assert dct["profile_section"]["has_profile"] is True
