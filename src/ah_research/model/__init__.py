"""Pure domain types and validation schemas.

This package is the *contract* for the rest of the system. Everything below
the integration boundary (converters, cache, repository) must produce objects
whose shape is defined here. Nothing in this package performs I/O, imports
pandas (except schemas.py, which requires it for DataFrame validation), or
depends on a data source.
"""

from ah_research.model.types import (
    Adjust,
    AHPair,
    CorporateAction,
    CorporateActionKind,
    Currency,
    Exchange,
    FillPrice,
    Freq,
    IndexConstituent,
    PriceKind,
    Settlement,
    StatementKind,
    Symbol,
    parse_symbol,
)

__all__ = [
    "AHPair",
    "Adjust",
    "CorporateAction",
    "CorporateActionKind",
    "Currency",
    "Exchange",
    "FillPrice",
    "Freq",
    "IndexConstituent",
    "PriceKind",
    "Settlement",
    "StatementKind",
    "Symbol",
    "parse_symbol",
]
