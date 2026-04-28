"""Exception hierarchy for ah-research.

See docs/superpowers/specs/2026-04-28-ah-research-platform-design.md §10.
Source errors are remapped at the integration boundary; upper layers never see
baostock.* or akshare.* exceptions.
"""

from __future__ import annotations


class AHResearchError(Exception):
    """Base class for every exception raised by this package."""


class SourceError(AHResearchError):
    """Raised at the integration boundary. Upstream errors are remapped here."""

    retryable: bool = False


class SourceRateLimit(SourceError):
    """Upstream signalled rate-limit. Retryable with exponential backoff."""

    retryable: bool = True


class SourceUnavailable(SourceError):
    """Transient upstream failure (network, 5xx). Retryable with longer backoff."""

    retryable: bool = True


class SourceSchemaError(SourceError):
    """Upstream response shape changed. NOT retryable; indicates drift."""

    retryable: bool = False


class SourceAuthError(SourceError):
    """Authentication failure. NOT retryable; indicates misconfiguration."""

    retryable: bool = False


class SourceDataError(SourceError):
    """Empty / malformed data from upstream. NOT retryable."""

    retryable: bool = False


class DataIntegrityError(AHResearchError):
    """Cache corruption, schema mismatch, pandera validation failure."""


class UserInputError(AHResearchError):
    """Bad symbol, invalid date range, unknown index, conflicting params."""


class ResearchError(AHResearchError):
    """Base for strategy / factor / backtest logic errors."""


class LeakageDetected(ResearchError):
    """Point-in-time violation or look-ahead bias detected."""


class UnsupportedOperation(ResearchError):
    """E.g., A-share short via retail."""


class InsufficientData(ResearchError):
    """Not enough history to compute the requested metric."""
