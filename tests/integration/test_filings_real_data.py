"""Sanity checks against the real data/filings/ + profiles/ on disk."""

from pathlib import Path

import pytest

from ah_research.filings import FilingsRepository, ProfileRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_filings_repository_finds_600519():
    repo = FilingsRepository(root=REPO_ROOT / "data" / "filings")
    syms = repo.list_symbols()
    if "600519.SH" not in syms:
        pytest.skip("600519.SH not present locally")
    filings = repo.list_filings("600519.SH")
    assert sum(1 for f in filings if f.kind == "annual") >= 5
    assert any(f.kind == "ipo" for f in filings)


def test_profile_repository_finds_600519():
    repo = ProfileRepository(root=REPO_ROOT / "profiles")
    syms = repo.list_symbols()
    if "600519.SH" not in syms:
        pytest.skip("600519.SH profile not present locally")
    latest = repo.latest("600519.SH")
    assert latest is not None
    assert len(latest.sections) > 0
