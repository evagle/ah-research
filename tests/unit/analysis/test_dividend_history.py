"""Tests for dividend_consistency_grade()."""

from datetime import date

import pandas as pd
import pytest

from ah_research.analysis.dividend_history import dividend_consistency_grade


def _cash_div_actions(
    years: list[int], amounts: list[float], symbol: str = "600000.SH"
) -> pd.DataFrame:
    rows = [
        {
            "symbol": symbol,
            "ex_date": pd.Timestamp(year=y, month=6, day=30),
            "kind": "cash_dividend",
            "params_json": f'{{"amount_per_share": {a}}}',
        }
        for y, a in zip(years, amounts, strict=True)
    ]
    return pd.DataFrame(rows)


# Grade ladder is A (best) → F (worst). Each scenario pins one rung
# of the ladder by varying the years/amounts pair.
@pytest.mark.parametrize(
    ("years", "amounts", "expected_grade"),
    [
        # A: 10 consecutive years, ≥8% CAGR, no cuts.
        (list(range(2015, 2025)), [1.0 * (1.10**i) for i in range(10)], "A"),
        # B: 10 consecutive years, flat (0% CAGR), no cuts.
        (list(range(2015, 2025)), [1.0] * 10, "B"),
        # C: 8 of 10 years; last 5 non-decreasing.
        (
            [2015, 2017, 2019, 2020, 2021, 2022, 2023, 2024],
            [1.0, 1.1, 1.2, 1.2, 1.3, 1.3, 1.4, 1.5],
            "C",
        ),
        # D: 5 of 10 years.
        ([2015, 2017, 2019, 2021, 2023], [1.0] * 5, "D"),
        # E: 3 of 10 years.
        ([2020, 2022, 2024], [1.0] * 3, "E"),
    ],
    ids=["A-10y-8pct-cagr", "B-10y-flat", "C-8-of-10", "D-5-of-10", "E-3-of-10"],
)
def test_grade_ladder(years: list[int], amounts: list[float], expected_grade: str) -> None:
    df = _cash_div_actions(years, amounts)
    assert (
        dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == expected_grade
    )


def test_grade_f_when_no_history() -> None:
    df = pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "F"


def test_recent_cut_demotes_from_a_to_c() -> None:
    """A 10-year history with a single cut in the last 5 years rules out
    A/B (which require non-decreasing) and demotes to C."""
    years = list(range(2015, 2025))
    amounts = [1.0, 1.1, 1.2, 1.3, 1.4, 1.3, 1.4, 1.5, 1.6, 1.7]  # cut in 2020
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "C"
