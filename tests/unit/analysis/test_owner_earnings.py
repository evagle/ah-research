"""Tests for owner_earnings_series()."""

import pandas as pd
import pytest

from ah_research.analysis.owner_earnings import owner_earnings_series


def _fundamentals_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_owner_earnings_basic_formula():
    """OE = NI + D&A - CapEx - WC change."""
    fundamentals = _fundamentals_frame(
        [
            {
                "symbol": "600000.SH",
                "report_date": pd.Timestamp("2023-12-31"),
                "publication_date": pd.Timestamp("2024-03-30"),
                "known_as_of": pd.Timestamp("2024-03-30"),
                "statement_kind": "audited",
                "net_income": 100.0,
                "d_and_a": 20.0,
                "capex": 30.0,
                "working_capital_change": 10.0,
            },
        ]
    )
    result = owner_earnings_series(fundamentals)
    # OE = 100 + 20 - 30 - 10 = 80
    assert result.iloc[0] == pytest.approx(80.0)
    assert result.index[0] == pd.Timestamp("2023-12-31")


def test_owner_earnings_empty_frame_returns_empty_series():
    # Deviation from plan: empty DataFrame with no columns cannot be astype'd;
    # use a properly-shaped empty frame instead.
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


def test_owner_earnings_skips_rows_with_missing_inputs():
    fundamentals = _fundamentals_frame(
        [
            {
                "symbol": "600000.SH",
                "report_date": pd.Timestamp("2022-12-31"),
                "publication_date": pd.Timestamp("2023-03-30"),
                "known_as_of": pd.Timestamp("2023-03-30"),
                "statement_kind": "audited",
                "net_income": 100.0,
                "d_and_a": None,  # missing
                "capex": 30.0,
                "working_capital_change": 10.0,
            },
            {
                "symbol": "600000.SH",
                "report_date": pd.Timestamp("2023-12-31"),
                "publication_date": pd.Timestamp("2024-03-30"),
                "known_as_of": pd.Timestamp("2024-03-30"),
                "statement_kind": "audited",
                "net_income": 120.0,
                "d_and_a": 25.0,
                "capex": 35.0,
                "working_capital_change": 12.0,
            },
        ]
    )
    result = owner_earnings_series(fundamentals)
    # Only 2023-12-31 row has all fields → 120 + 25 - 35 - 12 = 98
    assert len(result) == 1
    assert result.iloc[0] == pytest.approx(98.0)
    assert result.index[0] == pd.Timestamp("2023-12-31")
