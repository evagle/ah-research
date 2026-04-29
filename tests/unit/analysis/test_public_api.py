"""Tests that the analysis package public API re-exports are importable."""

from __future__ import annotations


def test_factor_study_importable():
    from ah_research.analysis import FactorReport, factor_study

    assert callable(factor_study)
    assert FactorReport is not None


def test_screener_importable():
    from ah_research.analysis import ScreenResult, run_screen

    assert callable(run_screen)
    assert ScreenResult is not None


def test_dossier_importable():
    from ah_research.analysis import Dossier, build_dossier

    assert callable(build_dossier)
    assert Dossier is not None


def test_owner_earnings_importable():
    from ah_research.analysis import owner_earnings_series

    assert callable(owner_earnings_series)


def test_valuation_bands_importable():
    from ah_research.analysis import ValuationBand, compute_valuation_bands

    assert callable(compute_valuation_bands)
    assert ValuationBand is not None


def test_dividend_consistency_grade_importable():
    from ah_research.analysis import dividend_consistency_grade

    assert callable(dividend_consistency_grade)


def test_all_names_in_dunder_all():
    import ah_research.analysis as pkg

    expected = {
        "factor_study",
        "FactorReport",
        "run_screen",
        "ScreenResult",
        "build_dossier",
        "Dossier",
        "owner_earnings_series",
        "compute_valuation_bands",
        "ValuationBand",
        "dividend_consistency_grade",
    }
    assert expected.issubset(set(pkg.__all__))
