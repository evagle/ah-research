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
