"""Tests for Constraint dataclass and factory classmethods (Task 15)."""

from __future__ import annotations

import pytest

from ah_research.portfolio.constructor import Constraint


def test_max_weight_factory() -> None:
    c = Constraint.max_weight(0.05)
    assert c.kind == "max_weight"
    assert c.params == {"w": 0.05}
    assert c.priority == 50


def test_sector_neutral_factory() -> None:
    c = Constraint.sector_neutral_to("CSI300")
    assert c.kind == "sector_neutral_to"
    assert c.params == {"benchmark": "CSI300"}


def test_tracking_error_factory() -> None:
    c = Constraint.tracking_error(300)
    assert c.kind == "tracking_error"
    assert c.params == {"bps": 300}
    assert c.priority == 70


def test_max_gross_factory() -> None:
    c = Constraint.max_gross(0.50)
    assert c.kind == "max_gross"
    assert c.params == {"gross": 0.50}
    assert c.priority == 40


def test_min_positions_factory() -> None:
    c = Constraint.min_positions(10)
    assert c.kind == "min_positions"
    assert c.params == {"n": 10}
    assert c.priority == 10


def test_max_positions_factory() -> None:
    c = Constraint.max_positions(50)
    assert c.kind == "max_positions"
    assert c.params == {"n": 50}
    assert c.priority == 20


def test_constraint_frozen() -> None:
    from dataclasses import FrozenInstanceError

    c = Constraint.max_weight(0.05)
    with pytest.raises(FrozenInstanceError):
        c.kind = "other"  # type: ignore[misc]


def test_all_factories_return_constraint() -> None:
    factories = [
        Constraint.max_weight(0.05),
        Constraint.max_gross(0.50),
        Constraint.sector_neutral_to("CSI300"),
        Constraint.tracking_error(300),
        Constraint.min_positions(10),
        Constraint.max_positions(50),
    ]
    for c in factories:
        assert isinstance(c, Constraint)


def test_long_only_factory_default_enabled():
    c = Constraint.long_only()
    assert c.kind == "long_only"
    assert c.params == {"enabled": True}


def test_long_only_factory_disabled():
    c = Constraint.long_only(enabled=False)
    assert c.params == {"enabled": False}


def test_max_turnover_factory_without_baseline():
    c = Constraint.max_turnover(0.25)
    assert c.kind == "max_turnover"
    assert c.params == {"value": 0.25, "baseline": None}


def test_max_turnover_factory_with_baseline():
    import pandas as pd

    base = pd.Series({"600519.SH": 0.5, "000858.SZ": 0.5})
    c = Constraint.max_turnover(0.1, baseline=base)
    assert c.params["value"] == 0.1
    pd.testing.assert_series_equal(c.params["baseline"], base)


def test_max_turnover_value_must_be_in_zero_two():
    import pytest

    with pytest.raises(ValueError, match="value"):
        Constraint.max_turnover(-0.1)
    with pytest.raises(ValueError, match="value"):
        Constraint.max_turnover(2.1)
