"""Shared validation helpers used by every data sub-repository."""

from __future__ import annotations

from datetime import date

from ah_research.exceptions import UserInputError


def validate_date_range(start: date, end: date) -> None:
    """Raise ``UserInputError`` when ``start > end``."""
    if start > end:
        raise UserInputError(f"start ({start}) must not be after end ({end})")
