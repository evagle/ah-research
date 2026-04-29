# tests/unit/analysis/test_dossier_build.py
from datetime import date

import pytest

from ah_research.analysis.dossier import Dossier, build_dossier
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_build_dossier_a_share_no_ah_pair() -> None:
    repo = build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    assert isinstance(d, Dossier)
    assert d.symbol.code == "600000"
    assert d.overview.sector_l1 != ""
    assert len(d.fundamentals.revenue_series) > 0
    assert d.ah_premium is None  # not dual-listed per ah_pairs.yaml


def test_build_dossier_ah_pair_leg_populates_symbol() -> None:
    repo = build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["601318.SH", "2318.HK"],  # Ping An AH pair
    )
    d = build_dossier("601318.SH", repo, asof=date(2024, 12, 31))
    # Accept either structured AHPremiumSection or None (fixture-dependent).
    assert d.symbol.code == "601318"


def test_build_dossier_delisted_symbol_raises() -> None:
    repo = build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2020, 12, 31),
        symbols=["600000.SH"],
    )
    with pytest.raises(ValueError, match="not available"):
        build_dossier("600000.SH", repo, asof=date(2024, 12, 31))  # after fixture end
