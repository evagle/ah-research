"""Tests for dividend_consistency_grade()."""

from datetime import date

import pandas as pd

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


def test_grade_a_10y_consecutive_cagr_8_no_cuts():
    # Amounts growing at ~10% CAGR: 1.0 * 1.1^9 ~= 2.36
    years = list(range(2015, 2025))
    amounts = [1.0 * (1.10**i) for i in range(10)]
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "A"


def test_grade_b_10y_flat_no_cuts():
    years = list(range(2015, 2025))
    amounts = [1.0] * 10  # flat -- 0% CAGR, no cuts
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "B"


def test_grade_c_7_of_10_years_no_recent_cuts():
    years = [2015, 2017, 2019, 2020, 2021, 2022, 2023, 2024]  # 8 of 10 years; last 5 non-decreasing
    amounts = [1.0, 1.1, 1.2, 1.2, 1.3, 1.3, 1.4, 1.5]
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "C"


def test_grade_d_5_of_10_years():
    years = [2015, 2017, 2019, 2021, 2023]
    amounts = [1.0] * 5
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "D"


def test_grade_e_3_of_10_years():
    years = [2020, 2022, 2024]
    amounts = [1.0] * 3
    df = _cash_div_actions(years, amounts)
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "E"


def test_grade_f_no_history():
    df = pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
    assert dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10) == "F"


def test_grade_b_demotes_from_a_on_cut():
    years = list(range(2015, 2025))
    amounts = [1.0, 1.1, 1.2, 1.3, 1.4, 1.3, 1.4, 1.5, 1.6, 1.7]  # cut in 2020
    df = _cash_div_actions(years, amounts)
    result = dividend_consistency_grade(df, asof=date(2024, 12, 31), window_years=10)
    assert result in ("C",), f"expected C (cut in last 5 violates A/B), got {result}"
