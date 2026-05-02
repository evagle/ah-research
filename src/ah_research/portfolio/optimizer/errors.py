"""Exception hierarchy for the Phase 4.1 portfolio optimizer."""

from __future__ import annotations

from ah_research.exceptions import ResearchError


class OptimizerError(ResearchError):
    """Base class for all optimizer errors.

    Inherits from ResearchError so optimizer exceptions share the package-wide
    ``AHResearchError`` root — ``except AHResearchError`` catches them too.
    """


class InfeasibleError(OptimizerError):
    """Raised when the CVXPY problem returns `infeasible` or `unbounded`
    in strict mode (soft=False)."""

    def __init__(self, message: str, *, constraints_summary: str | None = None) -> None:
        super().__init__(message)
        self.constraints_summary = constraints_summary


class NumericalError(OptimizerError):
    """Raised when the solver returns `optimal_inaccurate` with residuals
    exceeding the configured tolerance."""


class ValidationError(OptimizerError):
    """Raised when optimizer inputs are malformed (index mismatch, NaN μ,
    non-PSD Σ that cannot be regularized, unsupported constraint kind, etc.)."""
