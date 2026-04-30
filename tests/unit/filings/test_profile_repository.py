from datetime import date
from pathlib import Path

import pytest

from ah_research.filings.profile_repository import ProfileRepository, parse_sections

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"


@pytest.fixture
def repo() -> ProfileRepository:
    return ProfileRepository(root=FIXTURES)


def test_list_symbols_excludes_evaluation(repo: ProfileRepository):
    syms = repo.list_symbols()
    assert set(syms) == {"600000.SH", "000001.SZ"}


def test_list_profiles_all(repo: ProfileRepository):
    assert len(repo.list_profiles()) == 2


def test_list_profiles_filtered(repo: ProfileRepository):
    assert len(repo.list_profiles("600000.SH")) == 1


def test_latest_returns_profile(repo: ProfileRepository):
    p = repo.latest("600000.SH")
    assert p is not None
    assert p.date == date(2026, 4, 28)


def test_get_raises_when_missing(repo: ProfileRepository):
    with pytest.raises(FileNotFoundError):
        repo.get("600000.SH", date(1999, 1, 1))


def test_sections_parsed(repo: ProfileRepository):
    p = repo.latest("600000.SH")
    assert p is not None
    assert "§1 能力圈" in p.sections
    assert "§2 护城河" in p.sections
    assert "§2 护城河 / §2.1 子章节" in p.sections
    assert "§3 管理层" in p.sections


def test_sections_preserve_body(repo: ProfileRepository):
    p = repo.latest("600000.SH")
    assert p is not None
    assert "圈内判断" in p.sections["§1 能力圈"]


def test_parse_sections_empty_when_no_h2():
    md = "# Only H1\n\nbody without sections"
    assert parse_sections(md) == {}


def test_parse_sections_chinese_headers():
    md = "## §A 标题\n体\n## §B 另一个\n内"
    sections = parse_sections(md)
    assert sections["§A 标题"].strip() == "体"
    assert sections["§B 另一个"].strip() == "内"


def test_evaluation_file_excluded(repo: ProfileRepository):
    for p in repo.list_profiles("600000.SH"):
        assert "evaluation" not in p.path.name
