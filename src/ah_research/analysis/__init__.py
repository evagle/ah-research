"""Factor study, screener, dossier, and related research helpers."""

from ah_research.analysis.dividend_history import dividend_consistency_grade
from ah_research.analysis.dossier import Dossier, build_dossier
from ah_research.analysis.factor_study import FactorReport, factor_study
from ah_research.analysis.owner_earnings import owner_earnings_series
from ah_research.analysis.screener import ScreenResult, run_screen
from ah_research.analysis.valuation_bands import ValuationBand, compute_valuation_bands

__all__ = [
    "Dossier",
    "FactorReport",
    "ScreenResult",
    "ValuationBand",
    "build_dossier",
    "compute_valuation_bands",
    "dividend_consistency_grade",
    "factor_study",
    "owner_earnings_series",
    "run_screen",
]
