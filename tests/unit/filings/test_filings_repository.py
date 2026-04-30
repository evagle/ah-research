from pathlib import Path

import pytest

from ah_research.exceptions import UserInputError
from ah_research.filings.filings_repository import FilingsRepository

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "filings"


@pytest.fixture
def repo() -> FilingsRepository:
    return FilingsRepository(root=FIXTURES)


def test_list_symbols(repo: FilingsRepository):
    syms = repo.list_symbols()
    assert set(syms) == {"600000.SH", "000001.SZ"}


def test_list_filings_contains_all_kinds(repo: FilingsRepository):
    filings = repo.list_filings("600000.SH")
    kinds = [f.kind for f in filings]
    assert kinds.count("annual") == 2
    assert kinds.count("ipo") == 1
    assert kinds.count("research") == 1


def test_list_filings_empty_for_unknown_symbol(repo: FilingsRepository):
    assert repo.list_filings("999999.SH") == []


def test_get_annual_returns_filing(repo: FilingsRepository):
    f = repo.get_annual("600000.SH", 2024)
    assert f.year == 2024
    assert f.text.startswith("# Annual 2024")


def test_get_annual_raises_when_year_missing(repo: FilingsRepository):
    with pytest.raises(FileNotFoundError):
        repo.get_annual("600000.SH", 1999)


def test_latest_annual_returns_highest_year(repo: FilingsRepository):
    f = repo.latest_annual("600000.SH")
    assert f is not None
    assert f.year == 2024


def test_latest_annual_none_for_empty(repo: FilingsRepository):
    assert repo.latest_annual("999999.SH") is None


def test_get_ipo_returns_ipo(repo: FilingsRepository):
    f = repo.get_ipo("600000.SH")
    assert f is not None
    assert f.kind == "ipo"


def test_get_ipo_none_when_missing(repo: FilingsRepository):
    assert repo.get_ipo("000001.SZ") is None


def test_get_research_returns_list(repo: FilingsRepository):
    rs = repo.get_research("600000.SH")
    assert len(rs) == 1
    assert rs[0].title is not None or rs[0].path.name.startswith("broker-a")


def test_get_research_empty_when_dir_missing(repo: FilingsRepository):
    assert repo.get_research("000001.SZ") == []


def test_invalid_symbol_raises(repo: FilingsRepository):
    with pytest.raises(UserInputError):
        repo.list_filings("not-a-symbol")
