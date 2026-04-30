"""Map Phase 3 `Constraint` dataclass objects → CVXPY expressions.

For every new `ConstraintKind`, add:
  (1) a clause in `build_cvxpy_constraints` that appends the CVXPY expression.
  (2) a detector in `detect_active` that tests bindness at a solved w.

Unsupported kinds (min_positions, max_positions — cardinality) are rejected
in `reject_unsupported` with a pointer to external universe pre-filtering.

NOTE: Phase 3 `Constraint.max_weight` stores params["w"] (not params["value"]).
All param key names here match the actual Phase 3 factory implementations.
"""

from __future__ import annotations

from collections.abc import Sequence

import cvxpy as cp
import numpy as np
import pandas as pd

from ah_research.portfolio.constructor import Constraint
from ah_research.portfolio.optimizer.errors import ValidationError

_UNSUPPORTED: set[str] = {"min_positions", "max_positions"}


def reject_unsupported(constraints: Sequence[Constraint]) -> None:
    """Raise ValidationError if any constraint kind is unsupported by the optimizer."""
    for c in constraints:
        if c.kind in _UNSUPPORTED:
            raise ValidationError(
                f"Optimizer does not support Constraint(kind={c.kind!r}); this is a "
                f"cardinality constraint requiring MIP solvers. Pre-filter the "
                f"universe to N symbols before calling Optimizer.build() instead."
            )


def build_cvxpy_constraints(
    *,
    w: cp.Variable,
    symbols: list[str],
    constraints: Sequence[Constraint],
    long_only: bool,
    prev_weights: pd.Series | None,
) -> tuple[list[cp.Constraint], list[str]]:
    """Build the CVXPY constraint list + the list of constraint kind names (for reporting)."""
    reject_unsupported(constraints)

    cvx_cons: list[cp.Constraint] = []
    names: list[str] = []

    if long_only:
        cvx_cons.append(w >= 0)
        names.append("long_only")

    for c in constraints:
        if c.kind == "max_weight":
            # Phase 3 Constraint.max_weight stores params["w"] (not "value")
            cvx_cons.append(w <= c.params["w"])
            names.append("max_weight")
        elif c.kind == "max_gross":
            cvx_cons.append(cp.norm(w, 1) <= c.params["gross"])
            names.append("max_gross")
        elif c.kind == "sector_neutral_to":
            # Phase 3 shape: params = {"benchmark": str} — only benchmark name is stored.
            # Full sector_map/target dicts are NOT stored in the Constraint; they would need
            # to be resolved at build-time via repo. For now, require pre-resolved params.
            sector_map = c.params.get("sector_map")
            target = c.params.get("target")
            if sector_map is None or target is None:
                raise ValidationError(
                    "sector_neutral_to requires params['sector_map'] and params['target']"
                )
            for sector, tgt_weight in target.items():
                mask = np.array([1.0 if sector_map.get(s) == sector else 0.0 for s in symbols])
                cvx_cons.append(mask @ w == tgt_weight)
            names.append("sector_neutral_to")
        elif c.kind == "tracking_error":
            # Phase 3 shape: params = {"bps": int} — solver-ready te_sq/sigma are NOT stored.
            # Require pre-resolved params for optimizer use.
            te_sq = c.params.get("te_sq")
            sigma = c.params.get("sigma")
            benchmark_weights = c.params.get("benchmark_weights", np.zeros(len(symbols)))
            if te_sq is None or sigma is None:
                raise ValidationError("tracking_error requires params['te_sq'] and params['sigma']")
            diff = w - benchmark_weights
            cvx_cons.append(cp.quad_form(diff, sigma) <= te_sq)
            names.append("tracking_error")
        elif c.kind == "max_turnover":
            base = c.params.get("baseline")
            if base is None:
                base = prev_weights
            if base is None:
                raise ValidationError(
                    "max_turnover requires a baseline: either set via "
                    "Constraint.max_turnover(value, baseline=series) or pass "
                    "prev_weights= to Optimizer.build()"
                )
            base_aligned = pd.Series(base).reindex(symbols).fillna(0.0).values
            cvx_cons.append(cp.norm(w - base_aligned, 1) <= c.params["value"])
            names.append("max_turnover")
        elif c.kind == "long_only":
            if c.params.get("enabled", True):
                cvx_cons.append(w >= 0)
                if "long_only" not in names:
                    names.append("long_only")
        else:
            # Already filtered by reject_unsupported; this is defensive
            raise ValidationError(f"Unknown constraint kind: {c.kind}")

    return cvx_cons, names


def detect_active(
    *,
    constraints: Sequence[Constraint],
    w_value: pd.Series,
    prev_weights: pd.Series | None,
    long_only: bool,
    tol: float = 1e-4,
) -> tuple[str, ...]:
    """Given a solved weight vector, return the subset of constraint kinds
    that bind at the solution within `tol`."""
    active: list[str] = []

    if long_only and np.any(np.abs(w_value.values) < tol):
        active.append("long_only")

    for c in constraints:
        if c.kind == "max_weight":
            # Phase 3 stores params["w"]
            if np.any(np.abs(w_value.values - c.params["w"]) < tol):
                active.append("max_weight")
        elif c.kind == "max_gross":
            if abs(np.abs(w_value.values).sum() - c.params["gross"]) < tol:
                active.append("max_gross")
        elif c.kind == "max_turnover":
            base = c.params.get("baseline")
            if base is None:
                base = prev_weights
            if base is None:
                continue
            base_aligned = pd.Series(base).reindex(w_value.index).fillna(0.0).to_numpy()
            w_arr = np.asarray(w_value.values, dtype=float)
            l1 = float(np.abs(w_arr - base_aligned).sum())
            if abs(l1 - c.params["value"]) < tol:
                active.append("max_turnover")
        elif c.kind == "sector_neutral_to":
            # Equality constraint — always "active" if present
            active.append("sector_neutral_to")
        elif c.kind == "tracking_error":
            # Could add a residual check; for 4.1 mark active when present
            active.append("tracking_error")
        elif (
            c.kind == "long_only"
            and c.params.get("enabled", True)
            and np.any(np.abs(w_value.values) < tol)
            and "long_only" not in active
        ):
            active.append("long_only")

    return tuple(active)
