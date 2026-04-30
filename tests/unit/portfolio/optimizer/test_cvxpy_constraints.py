import cvxpy as cp
import numpy as np
import pandas as pd
import pytest

from ah_research.portfolio.constructor import Constraint
from ah_research.portfolio.optimizer.cvxpy_constraints import (
    build_cvxpy_constraints,
    reject_unsupported,
)
from ah_research.portfolio.optimizer.errors import ValidationError


def _solve(objective_sense, constraints, w):
    prob = cp.Problem(cp.Minimize(0), constraints)
    prob.solve(solver=cp.CLARABEL)
    return prob.status, w.value


def test_max_weight_maps_to_upper_bound():
    w = cp.Variable(3, name="w")
    symbols = ["A", "B", "C"]
    cons, _active_names = build_cvxpy_constraints(
        w=w,
        symbols=symbols,
        constraints=[Constraint.max_weight(0.4)],
        long_only=True,
        prev_weights=None,
    )
    cons.append(cp.sum(w) == 1)
    _status, wv = _solve(cp.Minimize, cons, w)
    assert _status == "optimal"
    assert (wv <= 0.4 + 1e-6).all()


def test_long_only_kwarg_adds_nonneg():
    w = cp.Variable(3)
    cons, _ = build_cvxpy_constraints(
        w=w,
        symbols=["A", "B", "C"],
        constraints=[],
        long_only=True,
        prev_weights=None,
    )
    cons.append(cp.sum(w) == 1)
    _, wv = _solve(cp.Minimize, cons, w)
    assert (wv >= -1e-9).all()


def test_max_gross_maps_to_l1_bound():
    w = cp.Variable(3)
    cons, _ = build_cvxpy_constraints(
        w=w,
        symbols=["A", "B", "C"],
        constraints=[Constraint.max_gross(1.5)],
        long_only=False,
        prev_weights=None,
    )
    cons.append(cp.sum(w) == 1)
    _, wv = _solve(cp.Minimize, cons, w)
    assert np.abs(wv).sum() <= 1.5 + 1e-5


def test_max_turnover_uses_kwarg_baseline():
    w = cp.Variable(2)
    prev = pd.Series({"A": 0.5, "B": 0.5})
    cons, _ = build_cvxpy_constraints(
        w=w,
        symbols=["A", "B"],
        constraints=[Constraint.max_turnover(0.1)],  # baseline=None in Constraint
        long_only=True,
        prev_weights=prev,
    )
    cons.append(cp.sum(w) == 1)
    _, wv = _solve(cp.Minimize, cons, w)
    assert np.abs(wv - np.array([0.5, 0.5])).sum() <= 0.1 + 1e-6


def test_max_turnover_raises_when_baseline_missing():
    w = cp.Variable(2)
    with pytest.raises(ValidationError, match="baseline"):
        build_cvxpy_constraints(
            w=w,
            symbols=["A", "B"],
            constraints=[Constraint.max_turnover(0.1)],
            long_only=True,
            prev_weights=None,
        )


def test_reject_unsupported_raises_on_cardinality():
    with pytest.raises(ValidationError, match="min_positions"):
        reject_unsupported([Constraint.min_positions(5)])
    with pytest.raises(ValidationError, match="max_positions"):
        reject_unsupported([Constraint.max_positions(10)])


def test_active_constraint_detection_after_solve():
    """After solving, active_names should flag constraints that bind at optimum."""
    # Maximize w[0] (Minimize -w[0]) s.t. sum=1, max_weight=0.4 → w[0]=0.4; max_weight binds
    w = cp.Variable(3)
    cons_list, _active_names = build_cvxpy_constraints(
        w=w,
        symbols=["A", "B", "C"],
        constraints=[Constraint.max_weight(0.4)],
        long_only=True,
        prev_weights=None,
    )
    cons_list.append(cp.sum(w) == 1)
    prob = cp.Problem(cp.Minimize(-w[0]), cons_list)
    prob.solve(solver=cp.CLARABEL)

    # Read back active: pass solved w.value into the detector
    from ah_research.portfolio.optimizer.cvxpy_constraints import detect_active

    active = detect_active(
        constraints=[Constraint.max_weight(0.4)],
        w_value=pd.Series(w.value, index=["A", "B", "C"]),
        prev_weights=None,
        long_only=True,
        tol=1e-4,
    )
    assert "max_weight" in active
