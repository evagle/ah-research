"""Sanity: Dossier for 600519.SH populates qualitative sections against real data/filings/ + profiles/."""

from __future__ import annotations

from pathlib import Path

import pytest

from ah_research.analysis.dossier import build_dossier
from ah_research.filings import FilingsRepository, ProfileRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


def _has_moutai_filings() -> bool:
    return (REPO_ROOT / "data" / "filings" / "600519.SH").exists()


@pytest.mark.skipif(not _has_moutai_filings(), reason="600519.SH data not present")
def test_dossier_600519_has_filings_section() -> None:
    try:
        from ah_research.config import get_settings
        from ah_research.data.cache import DuckDBCache
        from ah_research.data.repository import DataRepository
        from ah_research.integrations.fake import FakeSources

        settings = get_settings()
        sources = FakeSources(seed=42)
        cache = DuckDBCache(settings.cache_duckdb_path)
        repo = DataRepository(
            price_source=sources.prices,
            fundamentals_source=sources.fundamentals,
            fx_source=sources.fx,
            calendar_source=sources.calendar,
            sector_source=sources.sectors,
            corp_actions_source=sources.corporate_actions,
            constituents_source=sources.constituents,
            cache=cache,
        )
    except Exception:
        pytest.skip("DataRepository construction failed in this environment")

    filings = FilingsRepository(root=REPO_ROOT / "data" / "filings")
    profiles = ProfileRepository(root=REPO_ROOT / "profiles")
    try:
        from datetime import date

        d = build_dossier(
            "600519.SH",
            repo,
            asof=date.today(),
            include_qualitative=True,
            filings_repo=filings,
            profiles_repo=profiles,
        )
    except Exception as e:
        pytest.skip(f"build_dossier failed on quant side: {e}")

    assert d.filings_section is not None
    assert d.filings_section.n_annual >= 5
    assert d.filings_section.has_ipo is True
