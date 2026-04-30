"""CVXPY problem builders for mean-variance and risk-parity objectives."""

from __future__ import annotations

from collections.abc import Sequence

import cvxpy as cp
import numpy as np
import pandas as pd

from ah_research.portfolio.constructor import Constraint
from ah_research.portfolio.optimizer.cvxpy_constraints import build_cvxpy_constraints
from ah_research.portfolio.optimizer.errors import ValidationError


def _regularize_sigma(sigma: pd.DataFrame, jitter: float = 1e-10) -> np.ndarray:
    """Ensure Σ is symmetric PSD; add small jitter if near-singular."""
    s = sigma.values
    s = 0.5 * (s + s.T)  # symmetrize
    eigs = np.linalg.eigvalsh(s)
    if eigs.min() < 0:
        s = s + (abs(eigs.min()) + jitter) * np.eye(s.shape[0])
    return np.asarray(s, dtype=float)


def build_mean_variance(
    *,
    symbols: list[str],
    mu: pd.Series,
    sigma: pd.DataFrame,
    risk_aversion: float,
    constraints: Sequence[Constraint],
    long_only: bool,
    prev_weights: pd.Series | None,
    soft: bool,
    soft_penalty: float = 1e4,
) -> tuple[cp.Problem, cp.Variable]:
    """Build MV: min lambda*w'Sigma*w - mu'w  s.t.  sum(w) = 1, constraints."""
    n = len(symbols)
    w = cp.Variable(n, name="w")
    sigma_np = _regularize_sigma(sigma.reindex(index=symbols, columns=symbols))
    mu_np = mu.reindex(symbols).values
    if np.isnan(mu_np).any():
        raise ValidationError("mu contains NaN after reindex to symbols")

    objective = risk_aversion * cp.quad_form(w, sigma_np) - mu_np @ w
    cons, _ = build_cvxpy_constraints(
        w=w,
        symbols=symbols,
        constraints=constraints,
        long_only=long_only,
        prev_weights=prev_weights,
    )
    cons.append(cp.sum(w) == 1)

    if soft:
        # Introduce slack for inequality constraints by relaxing to inf-norm-penalized
        # form. For 4.1 we implement a simple approach: add a single scalar slack
        # variable that relaxes the sum-to-1 constraint symmetrically; per-constraint
        # slack is a future extension.
        slack = cp.Variable(nonneg=True, name="slack_sum")
        cons = [c for c in cons if not (isinstance(c, cp.constraints.Equality))]
        cons.append(cp.sum(w) + slack >= 1)
        cons.append(cp.sum(w) - slack <= 1)
        objective = objective + soft_penalty * slack

    return cp.Problem(cp.Minimize(objective), cons), w


def build_risk_parity(
    *,
    symbols: list[str],
    sigma: pd.DataFrame,
    constraints: Sequence[Constraint],
    long_only: bool,
    prev_weights: pd.Series | None,
    soft: bool,
    soft_penalty: float = 1e4,
) -> tuple[cp.Problem, cp.Variable]:
    """Build risk-parity (Maillard log-barrier):
      min  0.5 * w'Sigma*w - (1/N) * sum(log(w))
      s.t. <constraints>
    Note: Σ wᵢ = 1 is enforced post-hoc by rescaling; log-barrier
    only produces w > 0 solutions. The relationship:
    rp-optimal w* ∝ argmin of the log-barrier objective.
    """
    if not long_only:
        raise ValidationError(
            "risk_parity requires long_only=True (log-barrier formulation "
            "requires w > 0). For long-short risk-parity see future-phase roadmap."
        )
    n = len(symbols)
    w = cp.Variable(n, nonneg=True, name="w")
    sigma_np = _regularize_sigma(sigma.reindex(index=symbols, columns=symbols))

    objective = 0.5 * cp.quad_form(w, sigma_np) - (1.0 / n) * cp.sum(cp.log(w))
    cons, _ = build_cvxpy_constraints(
        w=w,
        symbols=symbols,
        constraints=constraints,
        long_only=True,
        prev_weights=prev_weights,
    )
    # Note: we do NOT add Σw=1 inside the problem — log-barrier is unbounded at w=0
    # and scale-invariant; caller normalizes post-solve.

    if soft:
        slack = cp.Variable(nonneg=True, name="rp_slack")
        objective = objective + soft_penalty * slack

    return cp.Problem(cp.Minimize(objective), cons), w
