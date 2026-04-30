import dataclasses
from datetime import date
from pathlib import Path

import pytest

from ah_research.filings.types import Filing, Profile


def test_filing_is_frozen():
    f = Filing(symbol="600519.SH", kind="annual", path=Path("x.md"), text="body", year=2024)
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.symbol = "other"  # type: ignore[misc]


def test_filing_defaults():
    f = Filing(symbol="600519.SH", kind="ipo", path=Path("x.md"), text="body")
    assert f.year is None
    assert f.title is None
    assert f.date is None


def test_profile_frozen_with_sections():
    p = Profile(
        symbol="600519.SH",
        date=date(2026, 4, 28),
        path=Path("x.md"),
        text="# Header\n\n## Sec 1\nbody",
        sections={"Sec 1": "body"},
    )
    assert p.sections["Sec 1"] == "body"
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.text = "other"  # type: ignore[misc]
