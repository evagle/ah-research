"""Integration test: build_dossier on one A-share + one HK symbol."""

from __future__ import annotations

from datetime import date

import pytest

from ah_research.analysis.dossier import Dossier, build_dossier
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

_START = date(2014, 1, 1)
_END = date(2024, 12, 31)


@pytest.fixture(scope="module")
def a_share_repo():
    return build_synthetic_market(start=_START, end=_END, symbols=["600000.SH"])


@pytest.fixture(scope="module")
def hk_share_repo():
    return build_synthetic_market(start=_START, end=_END, symbols=["2318.HK"])


def test_dossier_a_share_sections_populate(a_share_repo):
    """build_dossier on an A-share populates all main sections."""
    d = build_dossier("600000.SH", a_share_repo, asof=date(2024, 12, 31))
    assert isinstance(d, Dossier)
    assert d.symbol.code == "600000"

    # Overview
    assert d.overview.sector_l1 != ""

    # Fundamentals — must have some revenue data points
    assert len(d.fundamentals.revenue_series) > 0

    # Owner earnings — must have at least one entry
    assert len(d.owner_earnings.series) > 0

    # Valuation bands — all percentile keys present
    assert set(d.valuation_bands.pe_bands.keys()) == {"p10", "p25", "p50", "p75", "p90"}

    # Metadata
    assert d.metadata.asof == date(2024, 12, 31)
    assert isinstance(d.metadata.warnings, list)


def test_dossier_a_share_no_ah_premium(a_share_repo):
    """An A-share without an HK pair has ah_premium=None."""
    d = build_dossier("600000.SH", a_share_repo, asof=date(2024, 12, 31))
    # 600000.SH is not a dual-listed stock, so ah_premium should be None
    assert d.ah_premium is None


def test_dossier_hk_share_sections_populate(hk_share_repo):
    """build_dossier on an HK symbol populates all main sections."""
    d = build_dossier("2318.HK", hk_share_repo, asof=date(2024, 12, 31))
    assert isinstance(d, Dossier)
    assert d.symbol.code == "2318"
    assert d.overview.sector_l1 != ""
    assert len(d.fundamentals.revenue_series) > 0


def test_dossier_to_markdown_roundtrip(a_share_repo):
    """Dossier.to_markdown produces non-empty markdown with key headings."""
    d = build_dossier("600000.SH", a_share_repo, asof=date(2024, 12, 31))
    md = d.to_markdown(language="en")
    assert "# " in md
    assert len(md) > 200


def test_dossier_to_dict_json_serializable(a_share_repo):
    """Dossier.to_dict() is JSON-serializable."""
    import json

    d = build_dossier("600000.SH", a_share_repo, asof=date(2024, 12, 31))
    as_dict = d.to_dict()
    blob = json.dumps(as_dict, default=str)
    assert len(blob) > 100
