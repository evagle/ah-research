"""Tests for owner_earnings_series()."""

from __future__ import annotations

import pandas as pd
import pytest

from ah_research.analysis.owner_earnings import owner_earnings_series


@pytest.fixture
def fundamentals_row():
    """Callable: build a fundamentals row dict with keyword overrides.

    Returns a complete, valid row by default; pass kwargs to override
    specific fields (e.g., set ``d_and_a=None`` to test missing-input skip).
    """

    def _build(**overrides: object) -> dict:
        base: dict = {
            "symbol": "600000.SH",
            "report_date": pd.Timestamp("2023-12-31"),
            "publication_date": pd.Timestamp("2024-03-30"),
            "known_as_of": pd.Timestamp("2024-03-30"),
            "statement_kind": "audited",
            "net_income": 100.0,
            "d_and_a": 20.0,
            "capex": 30.0,
            "working_capital_change": 10.0,
        }
        base.update(overrides)
        return base

    return _build


def test_owner_earnings_basic_formula(fundamentals_row) -> None:  # type: ignore[no-untyped-def]
    """OE = NI + D&A - CapEx - WC change."""
    fundamentals = pd.DataFrame([fundamentals_row()])
    result = owner_earnings_series(fundamentals)
    # OE = 100 + 20 - 30 - 10 = 80
    assert result.iloc[0] == pytest.approx(80.0)
    assert result.index[0] == pd.Timestamp("2023-12-31")


def test_owner_earnings_empty_frame_returns_empty_series() -> None:
    """Empty fundamentals → empty series (no astype crash on no-row frames)."""
    empty = pd.DataFrame(
        columns=[
            "symbol",
            "report_date",
            "net_income",
            "d_and_a",
            "capex",
            "working_capital_change",
        ]
    )
    result = owner_earnings_series(empty)
    assert len(result) == 0


def test_owner_earnings_skips_rows_with_missing_inputs(fundamentals_row) -> None:  # type: ignore[no-untyped-def]
    """A row with any missing input field is dropped from the output series."""
    fundamentals = pd.DataFrame(
        [
            fundamentals_row(
                report_date=pd.Timestamp("2022-12-31"),
                publication_date=pd.Timestamp("2023-03-30"),
                known_as_of=pd.Timestamp("2023-03-30"),
                d_and_a=None,  # missing -> row dropped
            ),
            fundamentals_row(
                net_income=120.0,
                d_and_a=25.0,
                capex=35.0,
                working_capital_change=12.0,
            ),
        ]
    )
    result = owner_earnings_series(fundamentals)
    # Only 2023-12-31 row has all fields → 120 + 25 - 35 - 12 = 98
    assert len(result) == 1
    assert result.iloc[0] == pytest.approx(98.0)
    assert result.index[0] == pd.Timestamp("2023-12-31")
