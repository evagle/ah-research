"""Phase 4.1 portfolio optimizer package — public API."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from datetime import timedelta
from typing import Any, Literal

import cvxpy as cp
import numpy as np
import pandas as pd

from ah_research.data.repository import DataRepository
from ah_research.portfolio.constructor import Constraint
from ah_research.portfolio.optimizer.cvxpy_constraints import (
    detect_active,
    reject_unsupported,
)
from ah_research.portfolio.optimizer.errors import (
    InfeasibleError,
    NumericalError,
    OptimizerError,
    ValidationError,
)
from ah_research.portfolio.optimizer.estimators.covariance import CovarianceEstimator
from ah_research.portfolio.optimizer.estimators.returns import ExpectedReturnsEstimator
from ah_research.portfolio.optimizer.problem import (
    build_mean_variance,
    build_risk_parity,
)
from ah_research.portfolio.optimizer.result import OptimizationResult

__all__ = [
    "InfeasibleError",
    "NumericalError",
    "OptimizationResult",
    "Optimizer",
    "OptimizerError",
    "ValidationError",
    "mean_variance",
    "risk_parity",
]

_SOCP_CONSTRAINT_KINDS = {"tracking_error"}


class Optimizer:
    """Convex portfolio optimizer. See
    docs/superpowers/specs/2026-04-30-ah-research-phase-4-1-optimizer-design.md §6.
    """

    def __init__(
        self,
        *,
        objective: Literal["mean_variance", "risk_parity"],
        cov_estimator: CovarianceEstimator,
        returns_estimator: ExpectedReturnsEstimator | None = None,
        constraints: Sequence[Constraint] = (),
        risk_aversion: float = 1.0,
        long_only: bool = True,
        lookback_days: int = 252,
        solver: Literal["clarabel", "osqp", "auto"] = "auto",
        soft: bool = False,
        soft_penalty: float = 1e4,
        solver_tol: float = 1e-6,
    ) -> None:
        if objective == "mean_variance" and returns_estimator is None:
            raise ValidationError("mean_variance objective requires a returns_estimator")
        reject_unsupported(constraints)

        self.objective = objective
        self.cov_estimator = cov_estimator
        self.returns_estimator = returns_estimator
        self.constraints = list(constraints)
        self.risk_aversion = risk_aversion
        self.long_only = long_only
        self.lookback_days = lookback_days
        self.solver = solver
        self.soft = soft
        self.soft_penalty = soft_penalty
        self.solver_tol = solver_tol

    def build(
        self,
        symbols: list[str],
        as_of: pd.Timestamp,
        repo: DataRepository,
        *,
        prev_weights: pd.Series | None = None,
    ) -> OptimizationResult:
        """Orchestrates load -> estimate -> build -> solve -> result.

        Behavioural invariant: identical to the pre-refactor monolith.
        Each step is extracted into a named helper so failures point at the
        right phase and each step can be tested in isolation.
        """
        if not symbols:
            raise ValidationError("symbols must be non-empty")

        returns = self._load_returns(symbols, as_of, repo)
        sigma, mu = self._estimate_inputs(returns, symbols, as_of, repo)
        prob, w = self._build_problem(symbols, mu, sigma, prev_weights)

        solver_name = self._choose_solver()
        status, solve_ms = self._solve(prob, solver_name)
        self._check_status(status, prob)

        return self._build_result(
            prob=prob,
            w=w,
            symbols=symbols,
            mu=mu,
            sigma=sigma,
            prev_weights=prev_weights,
            status=status,
            solver_name=solver_name,
            solve_ms=solve_ms,
        )

    # -- build() sub-steps ---------------------------------------------------

    def _load_returns(
        self, symbols: list[str], as_of: pd.Timestamp, repo: DataRepository
    ) -> pd.DataFrame:
        """Step 1: fetch PIT-safe returns (strictly < as_of) for `lookback_days`."""
        start = (as_of - timedelta(days=int(self.lookback_days * 1.6))).date()
        end = as_of.date()
        prices = repo.get_prices(symbols, start, end)
        wide = prices.pivot(index="ds", columns="symbol", values="total_return").sort_index()
        wide = wide[wide.index < pd.Timestamp(as_of)].tail(self.lookback_days)
        return wide.reindex(columns=symbols)

    def _estimate_inputs(
        self,
        returns: pd.DataFrame,
        symbols: list[str],
        as_of: pd.Timestamp,
        repo: DataRepository,
    ) -> tuple[pd.DataFrame, pd.Series | None]:
        """Steps 2+3: covariance (all modes), expected returns (MV only)."""
        sigma = self.cov_estimator.estimate(returns)
        mu: pd.Series | None
        if self.objective == "mean_variance":
            assert self.returns_estimator is not None  # validated in __init__
            mu = self.returns_estimator.estimate(symbols, as_of, repo)
            if mu.isna().any():
                raise ValidationError("mu contains NaN")
        else:
            mu = None
        return sigma, mu

    def _build_problem(
        self,
        symbols: list[str],
        mu: pd.Series | None,
        sigma: pd.DataFrame,
        prev_weights: pd.Series | None,
    ) -> tuple[cp.Problem, cp.Variable]:
        """Step 4: dispatch to MV or RP problem builder.

        On the first rebalance `prev_weights is None`; max_turnover is skipped
        because turnover is undefined without a prior portfolio.
        """
        effective_constraints = (
            [c for c in self.constraints if c.kind != "max_turnover"]
            if prev_weights is None
            else self.constraints
        )
        if self.objective == "mean_variance":
            assert mu is not None
            return build_mean_variance(
                symbols=symbols,
                mu=mu,
                sigma=sigma,
                risk_aversion=self.risk_aversion,
                constraints=effective_constraints,
                long_only=self.long_only,
                prev_weights=prev_weights,
                soft=self.soft,
                soft_penalty=self.soft_penalty,
            )
        return build_risk_parity(
            symbols=symbols,
            sigma=sigma,
            constraints=effective_constraints,
            long_only=self.long_only,
            prev_weights=prev_weights,
            soft=self.soft,
            soft_penalty=self.soft_penalty,
        )

    def _solve(self, prob: cp.Problem, solver_name: str) -> tuple[str, float]:
        """Step 6: solve and time."""
        t0 = time.perf_counter()
        prob.solve(solver=solver_name.upper())
        solve_ms = (time.perf_counter() - t0) * 1000
        return prob.status, solve_ms

    def _check_status(self, status: str, prob: cp.Problem) -> None:
        """Step 7: raise InfeasibleError / NumericalError on bad status."""
        if status in ("infeasible", "unbounded") and not self.soft:
            raise InfeasibleError(
                f"Problem is {status}. Use soft=True for best-effort.",
                constraints_summary=self._summarize_constraints(),
            )
        if status == "optimal_inaccurate":
            residual = self._max_residual(prob)
            if residual > self.solver_tol * 100:  # 100x tolerance cliff
                raise NumericalError(
                    f"optimal_inaccurate with residual {residual:.2e} > {self.solver_tol * 100:.2e}"
                )

    def _build_result(
        self,
        *,
        prob: cp.Problem,
        w: cp.Variable,
        symbols: list[str],
        mu: pd.Series | None,
        sigma: pd.DataFrame,
        prev_weights: pd.Series | None,
        status: str,
        solver_name: str,
        solve_ms: float,
    ) -> OptimizationResult:
        """Post-process solver output into an OptimizationResult."""
        w_value = np.asarray(w.value)
        if self.objective == "risk_parity":
            # log-barrier formulation needs post-hoc normalization
            w_value = w_value / w_value.sum()
        weights = pd.Series(w_value, index=symbols)

        solver_status: Literal["optimal", "optimal_inaccurate", "soft_relaxed"]
        if self.soft and status in ("optimal", "optimal_inaccurate"):
            solver_status = "soft_relaxed"
        elif status == "optimal_inaccurate":
            solver_status = "optimal_inaccurate"
        else:
            solver_status = "optimal"

        active_tuple = detect_active(
            constraints=self.constraints,
            w_value=weights,
            prev_weights=prev_weights,
            long_only=self.long_only,
            tol=1e-4,
        )

        w_np = np.asarray(weights.values, dtype=float)
        sigma_np_aligned = sigma.reindex(index=symbols, columns=symbols).to_numpy(dtype=float)
        exp_var = float(w_np @ sigma_np_aligned @ w_np)
        if self.objective == "mean_variance":
            assert mu is not None
            mu_np = np.asarray(mu.reindex(symbols).values, dtype=float)
            exp_ret = float(mu_np @ w_np)
            rc: pd.Series | None = None
        else:
            exp_ret = None
            raw_rc = w_np * (sigma_np_aligned @ w_np)
            rc = pd.Series(raw_rc / raw_rc.sum(), index=symbols)

        slack: dict[str, float] = {}
        if self.soft:
            for v in prob.variables():
                if v.name().startswith("slack") or v.name().startswith("rp_slack"):
                    val = v.value
                    if val is not None and float(val) > 1e-8:
                        slack[v.name()] = float(val)

        return OptimizationResult(
            weights=weights,
            objective=self.objective,
            solver_status=solver_status,
            objective_value=float(prob.value),
            active_constraints=active_tuple,
            slack=slack,
            expected_return=exp_ret,
            expected_variance=exp_var,
            risk_contributions=rc,
            solver_name=solver_name,
            solve_time_ms=solve_ms,
            inputs_hash=self._hash_inputs(symbols, mu, sigma),
        )

    # -- helpers -------------------------------------------------------------

    def _choose_solver(self) -> str:
        if self.solver != "auto":
            return self.solver
        needs_socp = (
            self.objective == "risk_parity"
            or self.soft
            or any(c.kind in _SOCP_CONSTRAINT_KINDS for c in self.constraints)
        )
        return "clarabel" if needs_socp else "osqp"

    def _max_residual(self, prob: cp.Problem) -> float:
        residuals = [float(c.violation()) for c in prob.constraints if hasattr(c, "violation")]
        return max(residuals) if residuals else 0.0

    def _summarize_constraints(self) -> str:
        bits = [f"long_only={self.long_only}"]
        for c in self.constraints:
            bits.append(f"{c.kind}={c.params}")
        return "; ".join(bits)

    def _hash_inputs(self, symbols: list[str], mu: pd.Series | None, sigma: pd.DataFrame) -> str:
        h = hashlib.sha256()
        h.update(",".join(sorted(symbols)).encode())
        if mu is not None:
            h.update(np.asarray(mu.reindex(sorted(symbols)).values, dtype=float).tobytes())
        h.update(
            np.asarray(
                sigma.reindex(index=sorted(symbols), columns=sorted(symbols)).values, dtype=float
            ).tobytes()
        )
        for c in self.constraints:
            h.update(f"{c.kind}:{sorted(c.params.items(), key=lambda kv: kv[0])}".encode())
        h.update(f"{self.objective}|{self.risk_aversion}|{self.long_only}|{self.soft}".encode())
        return h.hexdigest()


def mean_variance(
    symbols: list[str],
    as_of: pd.Timestamp,
    repo: DataRepository,
    *,
    cov_estimator: CovarianceEstimator | None = None,
    returns_estimator: ExpectedReturnsEstimator | None = None,
    constraints: Sequence[Constraint] = (),
    risk_aversion: float = 1.0,
    **kwargs: Any,
) -> OptimizationResult:
    """Convenience helper for MV optimization."""
    from ah_research.portfolio.optimizer.estimators.covariance import LedoitWolfCovariance
    from ah_research.portfolio.optimizer.estimators.returns import HistoricalMeanReturns

    return Optimizer(
        objective="mean_variance",
        cov_estimator=cov_estimator or LedoitWolfCovariance(),
        returns_estimator=returns_estimator or HistoricalMeanReturns(),
        constraints=constraints,
        risk_aversion=risk_aversion,
        **kwargs,
    ).build(symbols, as_of, repo)


def risk_parity(
    symbols: list[str],
    as_of: pd.Timestamp,
    repo: DataRepository,
    *,
    cov_estimator: CovarianceEstimator | None = None,
    constraints: Sequence[Constraint] = (),
    **kwargs: Any,
) -> OptimizationResult:
    """Convenience helper for risk-parity optimization."""
    from ah_research.portfolio.optimizer.estimators.covariance import LedoitWolfCovariance

    return Optimizer(
        objective="risk_parity",
        cov_estimator=cov_estimator or LedoitWolfCovariance(),
        returns_estimator=None,
        constraints=constraints,
        **kwargs,
    ).build(symbols, as_of, repo)
