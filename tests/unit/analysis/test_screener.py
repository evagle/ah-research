"""Tests for run_screen()."""

from datetime import date

import pytest

from ah_research.analysis.screener import ScreenResult, run_screen
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_simple_single_condition_lt():
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    result = run_screen(
        conditions={"pe": ("<", 1_000_000.0)},  # loose predicate -- all pass
        repo=repo,
        asof=date(2024, 12, 31),
        universe="CSI300",
    )
    assert isinstance(result, ScreenResult)
    assert result.asof == date(2024, 12, 31)
    assert result.n_passed <= result.n_input


def test_between_operator():
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    result = run_screen(
        conditions={"pe": ("between", 0.1, 100.0)},
        repo=repo,
        asof=date(2024, 12, 31),
        universe="CSI300",
    )
    assert result.frame["pe"].between(0.1, 100.0).all()


def test_in_operator():
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )
    result = run_screen(
        conditions={
            "sector_l1": (
                "in",
                [
                    "Finance",
                    "Energy",
                    "Tech",
                    "Financials",
                    "Consumer",
                    "Technology",
                    "Industrials",
                    "Healthcare",
                ],
            )
        },
        repo=repo,
        asof=date(2024, 12, 31),
        universe="CSI300",
    )
    assert all(
        result.frame["sector_l1"].isin(
            [
                "Finance",
                "Energy",
                "Tech",
                "Financials",
                "Consumer",
                "Technology",
                "Industrials",
                "Healthcare",
            ]
        )
    )


def test_unknown_column_raises_with_suggestions():
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    with pytest.raises(KeyError) as exc:
        run_screen(
            conditions={"non_existent": ("<", 10)},
            repo=repo,
            asof=date(2024, 12, 31),
        )
    assert "non_existent" in str(exc.value)


def test_derived_column_computed_when_referenced():
    repo = build_synthetic_market(
        start=date(2020, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    result = run_screen(
        conditions={"roe_3y_avg": (">", -1.0)},  # loose -- just verify column computed
        repo=repo,
        asof=date(2024, 12, 31),
    )
    assert "roe_3y_avg" in result.frame.columns


def test_between_lo_gt_hi_raises():
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    with pytest.raises(ValueError):
        run_screen(
            conditions={"pe": ("between", 20.0, 10.0)},  # lo > hi
            repo=repo,
            asof=date(2024, 12, 31),
        )


def test_empty_result_no_error():
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    result = run_screen(
        conditions={"pe": ("<", -999999)},  # impossible
        repo=repo,
        asof=date(2024, 12, 31),
    )
    assert result.n_passed == 0


def test_conditions_applied_preserved():
    repo = build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    conds = {"pe": ("<", 100.0), "dividend_yield": (">", 0.0)}
    result = run_screen(conditions=conds, repo=repo, asof=date(2024, 12, 31))
    assert result.conditions_applied == conds
