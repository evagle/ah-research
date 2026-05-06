"""Tests for Constraint dataclass and factory classmethods (Task 15)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from ah_research.portfolio.constructor import Constraint


@pytest.mark.parametrize(
    ("factory", "args", "expected_kind", "expected_params", "expected_priority"),
    [
        (Constraint.max_weight, (0.05,), "max_weight", {"w": 0.05}, 50),
        (
            Constraint.sector_neutral_to,
            ("CSI300",),
            "sector_neutral_to",
            {"benchmark": "CSI300"},
            60,
        ),
        (Constraint.tracking_error, (300,), "tracking_error", {"bps": 300}, 70),
        (Constraint.max_gross, (0.50,), "max_gross", {"gross": 0.50}, 40),
        (Constraint.min_positions, (10,), "min_positions", {"n": 10}, 10),
        (Constraint.max_positions, (50,), "max_positions", {"n": 50}, 20),
    ],
    ids=[
        "max_weight",
        "sector_neutral_to",
        "tracking_error",
        "max_gross",
        "min_positions",
        "max_positions",
    ],
)
def test_factory_produces_constraint_with_expected_kind_params_priority(
    factory,  # type: ignore[no-untyped-def]
    args: tuple[object, ...],
    expected_kind: str,
    expected_params: dict[str, object],
    expected_priority: int,
) -> None:
    """Each factory yields a frozen ``Constraint`` with matching kind /
    params / priority."""
    c = factory(*args)
    assert isinstance(c, Constraint)
    assert c.kind == expected_kind
    assert c.params == expected_params
    # Some factories don't pin priority in the original tests -- only check
    # priority when the original test explicitly asserted it.
    if expected_kind in {
        "max_weight",
        "tracking_error",
        "max_gross",
        "min_positions",
        "max_positions",
    }:
        assert c.priority == expected_priority


def test_constraint_frozen() -> None:
    c = Constraint.max_weight(0.05)
    with pytest.raises(FrozenInstanceError):
        c.kind = "other"  # type: ignore[misc]


# ── long_only ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("enabled", "expected_params"),
    [
        # Default behaviour: enabled=True.
        (None, {"enabled": True}),
        (True, {"enabled": True}),
        (False, {"enabled": False}),
    ],
    ids=["default", "enabled-true", "enabled-false"],
)
def test_long_only_factory(enabled: bool | None, expected_params: dict[str, bool]) -> None:
    c = Constraint.long_only() if enabled is None else Constraint.long_only(enabled=enabled)
    assert c.kind == "long_only"
    assert c.params == expected_params


# ── max_turnover ─────────────────────────────────────────────────────────────


def test_max_turnover_without_baseline() -> None:
    c = Constraint.max_turnover(0.25)
    assert c.kind == "max_turnover"
    assert c.params == {"value": 0.25, "baseline": None}


def test_max_turnover_with_baseline() -> None:
    base = pd.Series({"600519.SH": 0.5, "000858.SZ": 0.5})
    c = Constraint.max_turnover(0.1, baseline=base)
    assert c.params["value"] == 0.1
    pd.testing.assert_series_equal(c.params["baseline"], base)


@pytest.mark.parametrize("bad_value", [-0.1, 2.1], ids=["below-zero", "above-two"])
def test_max_turnover_value_must_be_in_zero_two(bad_value: float) -> None:
    with pytest.raises(ValueError, match="value"):
        Constraint.max_turnover(bad_value)
