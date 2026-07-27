"""Tests for run_screen()."""

from __future__ import annotations

from datetime import date

import pytest

from ah_research.analysis.screener import ScreenResult, run_screen
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ── Shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def repo():
    """Default screener repo: two-symbol universe over a 2-year window."""
    return build_synthetic_market(
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH", "000001.SZ"],
    )


@pytest.fixture
def long_history_repo():
    """5-year history for derived metrics (e.g. roe_3y_avg)."""
    return build_synthetic_market(
        start=date(2020, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )


_ASOF = date(2024, 12, 31)
_SECTORS = [
    "Finance",
    "Energy",
    "Tech",
    "Financials",
    "Consumer",
    "Technology",
    "Industrials",
    "Healthcare",
]


# ── happy-path screens ──────────────────────────────────────────────────────


def test_simple_single_condition_lt(repo) -> None:  # type: ignore[no-untyped-def]
    result = run_screen(
        conditions={"pe": ("<", 1_000_000.0)},  # loose predicate -- all pass
        repo=repo,
        asof=_ASOF,
        universe="CSI300",
    )
    assert isinstance(result, ScreenResult)
    assert result.asof == _ASOF
    assert result.n_passed <= result.n_input


def test_between_operator(repo) -> None:  # type: ignore[no-untyped-def]
    result = run_screen(
        conditions={"pe": ("between", 0.1, 100.0)},
        repo=repo,
        asof=_ASOF,
        universe="CSI300",
    )
    assert result.frame["pe"].between(0.1, 100.0).all()


def test_in_operator(repo) -> None:  # type: ignore[no-untyped-def]
    result = run_screen(
        conditions={"sector_l1": ("in", _SECTORS)},
        repo=repo,
        asof=_ASOF,
        universe="CSI300",
    )
    assert all(result.frame["sector_l1"].isin(_SECTORS))


def test_derived_column_computed_when_referenced(long_history_repo) -> None:  # type: ignore[no-untyped-def]
    """A computed derived column (e.g. roe_3y_avg) is materialised in the frame."""
    result = run_screen(
        conditions={"roe_3y_avg": (">", -1.0)},  # loose -- just verify column computed
        repo=long_history_repo,
        asof=_ASOF,
    )
    assert "roe_3y_avg" in result.frame.columns


def test_empty_result_no_error(repo) -> None:  # type: ignore[no-untyped-def]
    """An impossible predicate produces an empty result, not an exception."""
    result = run_screen(
        conditions={"pe": ("<", -999999)},
        repo=repo,
        asof=_ASOF,
    )
    assert result.n_passed == 0


def test_conditions_applied_preserved(repo) -> None:  # type: ignore[no-untyped-def]
    """ScreenResult.conditions_applied echoes the input conditions verbatim."""
    conds = {"pe": ("<", 100.0), "dividend_yield": (">", 0.0)}
    result = run_screen(conditions=conds, repo=repo, asof=_ASOF)
    assert result.conditions_applied == conds


# ── error paths ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("conditions", "expected_exception", "expected_match"),
    [
        # Unknown column -> KeyError mentioning the missing name.
        ({"non_existent": ("<", 10)}, KeyError, "non_existent"),
        # between with lo > hi is invalid.
        ({"pe": ("between", 20.0, 10.0)}, ValueError, None),
    ],
    ids=["unknown-column", "between-lo-gt-hi"],
)
def test_invalid_conditions_raise(
    repo,  # type: ignore[no-untyped-def]
    conditions: dict[str, object],
    expected_exception: type[Exception],
    expected_match: str | None,
) -> None:
    with pytest.raises(expected_exception) as exc:
        run_screen(conditions=conditions, repo=repo, asof=_ASOF)
    if expected_match is not None:
        assert expected_match in str(exc.value)
