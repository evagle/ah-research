"""Frozen dataclasses for filings and profiles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Literal

FilingKind = Literal["annual", "ipo", "research"]


@dataclass(frozen=True)
class Filing:
    symbol: str
    kind: FilingKind
    path: Path
    text: str
    year: int | None = None
    title: str | None = None
    date: _date | None = None


@dataclass(frozen=True)
class Profile:
    symbol: str
    date: _date
    path: Path
    text: str
    sections: Mapping[str, str] = field(default_factory=dict)
