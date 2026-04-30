"""Real-data integration tests for FilingsRepository.search().

These tests are skipped when data/filings/600519.SH is absent.
Run with: uv run pytest tests/integration/test_filings_search_real_data.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ah_research.filings.filings_repository import FilingsRepository

FILINGS_ROOT = Path("data/filings")
MOUTAI = "600519.SH"


@pytest.fixture(scope="module")
def repo() -> FilingsRepository:
    return FilingsRepository(root=FILINGS_ROOT)


pytestmark = pytest.mark.skipif(
    not (FILINGS_ROOT / MOUTAI).exists(),
    reason=f"Real filings data not present at {FILINGS_ROOT / MOUTAI}",
)


def test_search_moutai_returns_hits(repo: FilingsRepository) -> None:
    hits = repo.search("茅台", symbols=[MOUTAI])
    assert len(hits) > 0, "Expected at least one hit for '茅台' in Moutai filings"


def test_search_gongsi_annual_returns_hits(repo: FilingsRepository) -> None:
    hits = repo.search("公司", symbols=[MOUTAI], kinds=["annual"])
    assert len(hits) > 0, "Expected at least one hit for '公司' in Moutai annual reports"
    assert all(h.filing.kind == "annual" for h in hits)
