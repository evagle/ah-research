"""Portfolio Constructor: Constraint + ConstructionReport + execution chain.

Phase 3 Task 15-16. ``construction.py`` (Phase 2) is left untouched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
from pandera.errors import SchemaError

from ah_research.backtest.types import Signals
from ah_research.constants import BPS_PER_UNIT, TRADING_DAYS_PER_YEAR
from ah_research.exceptions import DataIntegrityError, SourceError
from ah_research.portfolio.construction import top_quantile_weights

if TYPE_CHECKING:
    from ah_research.portfolio.optimizer import Optimizer
    from ah_research.portfolio.optimizer.result import OptimizationResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constraint
# ---------------------------------------------------------------------------

ConstraintKind = Literal[
    "max_weight",
    "sector_neutral_to",
    "tracking_error",
    "max_gross",
    "min_positions",
    "max_positions",
    "max_turnover",
    "long_only",
]


@dataclass(frozen=True)
class Constraint:
    """Immutable constraint specification with factory classmethods."""

    kind: ConstraintKind
    params: dict[str, Any]
    priority: int  # lower = applied first

    # ── factories ─────────────────────────────────────────────────────────

    @classmethod
    def max_weight(cls, w: float) -> Constraint:
        """Cap each position weight at *w* (0, 1]."""
        return cls(kind="max_weight", params={"w": w}, priority=50)

    @classmethod
    def sector_neutral_to(cls, benchmark: str) -> Constraint:
        """Match sector weights to benchmark sector composition."""
        return cls(kind="sector_neutral_to", params={"benchmark": benchmark}, priority=60)

    @classmethod
    def tracking_error(cls, bps: int) -> Constraint:
        """Shrink toward benchmark until TE <= *bps* basis points."""
        return cls(kind="tracking_error", params={"bps": bps}, priority=70)

    @classmethod
    def max_gross(cls, gross: float) -> Constraint:
        """Cap the gross exposure (sum of absolute weights) at *gross*."""
        return cls(kind="max_gross", params={"gross": gross}, priority=40)

    @classmethod
    def min_positions(cls, n: int) -> Constraint:
        """Require at least *n* positions after selection."""
        return cls(kind="min_positions", params={"n": n}, priority=10)

    @classmethod
    def max_positions(cls, n: int) -> Constraint:
        """Allow at most *n* positions."""
        return cls(kind="max_positions", params={"n": n}, priority=20)

    @classmethod
    def max_turnover(
        cls, value: float, *, baseline: pd.Series | None = None, priority: int = 0
    ) -> Constraint:
        """Constrain |w - baseline|_1 <= value. `baseline` is an L1 anchor
        series indexed by ticker string; missing entries default to 0."""
        if not (0.0 <= value <= 2.0):
            raise ValueError(
                f"max_turnover value must be in [0, 2] (|w - base|_1 ranges "
                f"over [0, 2] for long-only sum-to-1); got {value}"
            )
        return cls(
            kind="max_turnover", params={"value": value, "baseline": baseline}, priority=priority
        )

    @classmethod
    def long_only(cls, enabled: bool = True, *, priority: int = 0) -> Constraint:
        """Constrain w >= 0 when enabled."""
        return cls(kind="long_only", params={"enabled": enabled}, priority=priority)


# ---------------------------------------------------------------------------
# ConstraintResult + ConstructionReport
# ---------------------------------------------------------------------------

ConstraintStatus = Literal["slack", "bound", "infeasible_relaxed"]


@dataclass(frozen=True)
class ConstraintResult:
    """Per-constraint outcome from the heuristic relaxation pass."""

    constraint: Constraint
    status: ConstraintStatus
    detail: str = ""


@dataclass(frozen=True)
class ConstructionReport:
    """Full output from ``Constructor.build()``.

    ``weights`` is deep-copied in ``__post_init__`` so callers cannot
    retroactively mutate the frame under the (otherwise-frozen) container.
    """

    weights: pd.DataFrame  # columns: [symbol, weight]
    final_position_count: int
    constraint_results: list[ConstraintResult]
    method_used: str
    weighting_scheme: str
    relaxation_notes: list[str] = field(default_factory=list)
    optimization_result: OptimizationResult | None = None

    def __post_init__(self) -> None:
        # Defensive copy: frozen=True only blocks attribute reassignment,
        # not mutation of the referenced DataFrame.
        object.__setattr__(self, "weights", self.weights.copy(deep=True))


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class Constructor:
    """Fluent builder for constructing a portfolio from a ``Signals`` snapshot.

    Usage::

        report = (
            Constructor(signals, repo=repo, asof=date(2024, 6, 30))
            .method("top_quantile", quantile=0.2)
            .weight_by("equal")
            .constrain(Constraint.max_weight(0.05))
            .build()
        )
    """

    def __init__(
        self,
        signals: Signals,
        *,
        repo: Any | None = None,
        asof: date | None = None,
        optimizer: Optimizer | None = None,
    ) -> None:
        self._signals = signals
        self._repo = repo
        self._asof = asof
        self._optimizer = optimizer
        self._method: str = "top_quantile"
        self._method_kwargs: dict[str, Any] = {"quantile": 0.2}
        self._weighting: str = "equal"
        self._constraints: list[Constraint] = []

    # ── chain methods ──────────────────────────────────────────────────────

    def method(
        self,
        name: Literal["top_quantile", "top_n", "all_positive"],
        **kwargs: Any,
    ) -> Constructor:
        """Select symbol-selection method."""
        self._method = name
        self._method_kwargs = dict(kwargs)
        return self

    def weight_by(
        self,
        scheme: Literal[
            "equal",
            "signal_proportional",
            "free_float_mcw",
            "mcw",
            "optimize",
        ],
    ) -> Constructor:
        """Set the weighting scheme."""
        self._weighting = scheme
        return self

    def constrain(self, *constraints: Constraint) -> Constructor:
        """Add one or more constraints to the queue."""
        self._constraints.extend(constraints)
        return self

    # ── build ──────────────────────────────────────────────────────────────

    def build(self) -> ConstructionReport:
        """Execute the full construction pipeline and return a report."""
        # Optimize-mode preconditions
        if self._weighting == "optimize":
            if self._optimizer is None:
                raise ValueError("weight_by('optimize') requires Constructor(optimizer=...)")
            if self._repo is None:
                raise ValueError("weight_by('optimize') requires Constructor(repo=...)")
            if self._asof is None:
                raise ValueError("weight_by('optimize') requires Constructor(asof=...)")
            if self._constraints:
                raise ValueError(
                    "weight_by('optimize') is incompatible with .constrain(...); "
                    "set constraints on Optimizer instead"
                )

        sig_df = self._signals.df.copy()

        # 1. Selection
        selected = self._apply_method(sig_df)

        # 2. Weighting
        opt_result: OptimizationResult | None = None
        if self._weighting == "optimize":
            assert self._optimizer is not None
            assert self._repo is not None
            assert self._asof is not None

            symbols_selected = selected["symbol"].tolist()
            if not symbols_selected:
                raise ValueError("nothing selected — cannot optimize empty universe")

            opt_result = self._optimizer.build(
                symbols=symbols_selected,
                as_of=pd.Timestamp(self._asof),
                repo=self._repo,
                prev_weights=None,
            )
            weights_series = opt_result.weights.copy()
        else:
            weights_series = self._apply_weighting(selected)

        # 3. Constraints — skipped entirely in optimize mode
        constraint_results: list[ConstraintResult] = []
        relaxation_notes: list[str] = []

        if self._weighting != "optimize":
            sorted_constraints = sorted(self._constraints, key=lambda c: c.priority)
            for c in sorted_constraints:
                weights_series, result, notes = self._apply_constraint(c, weights_series, selected)
                constraint_results.append(result)
                relaxation_notes.extend(notes)

            # Normalise to sum=1 after all constraints (not needed in optimize mode)
            total = weights_series.sum()
            if total > 0:
                weights_series = weights_series / total

        weights_df = pd.DataFrame({"symbol": weights_series.index, "weight": weights_series.values})

        return ConstructionReport(
            weights=weights_df,
            final_position_count=int((weights_series > 0).sum()),
            constraint_results=constraint_results,
            method_used=self._method,
            weighting_scheme=self._weighting,
            relaxation_notes=relaxation_notes,
            optimization_result=opt_result,
        )

    # ── internal helpers ───────────────────────────────────────────────────

    def _apply_method(self, sig_df: pd.DataFrame) -> pd.DataFrame:
        """Return a filtered signals DataFrame (subset of rows)."""
        if self._method == "top_quantile":
            quantile = float(self._method_kwargs.get("quantile", 0.2))
            w_df = top_quantile_weights(sig_df, quantile=quantile)
            # Return the *signals* rows that survived selection
            symbols_selected: set[str] = set(w_df["symbol"].tolist())
            return sig_df[sig_df["symbol"].isin(symbols_selected)].copy()

        if self._method == "top_n":
            n = int(self._method_kwargs.get("n", 10))
            result = sig_df.copy()
            result = result.nlargest(n, "signal")
            return result

        if self._method == "all_positive":
            return sig_df[sig_df["signal"] > 0].copy()

        # Fallback: use all
        return sig_df.copy()

    def _apply_weighting(self, selected: pd.DataFrame) -> pd.Series:
        """Return a Series indexed by symbol with raw (unnormalized) weights."""
        if selected.empty:
            return pd.Series(dtype=float)

        symbols = selected["symbol"].tolist()

        if self._weighting == "equal":
            n = len(symbols)
            return pd.Series(1.0 / n, index=symbols)

        if self._weighting == "signal_proportional":
            signals = selected.set_index("symbol")["signal"].astype(float)
            signals = signals - signals.min()  # shift to non-negative
            total = signals.sum()
            if total == 0:
                return pd.Series(1.0 / len(symbols), index=symbols)
            return signals / total

        if self._weighting in ("free_float_mcw", "mcw"):
            # Attempt to fetch market cap from repo; fall back to equal weight
            # ONLY on expected data-availability failures. Unexpected exceptions
            # propagate so a real bug does not masquerade as a valid MCW
            # portfolio.
            if self._repo is not None and self._asof is not None:
                try:
                    funds = self._repo.get_fundamentals(
                        symbols,
                        start=self._asof,
                        end=self._asof,
                        asof=self._asof,
                    )
                    col = (
                        "market_cap_free_float"
                        if self._weighting == "free_float_mcw"
                        else "market_cap"
                    )
                    if not funds.empty and col in funds.columns:
                        mc = (
                            funds.groupby("symbol")[col]
                            .last()
                            .reindex(symbols)
                            .fillna(0.0)
                            .astype(float)
                        )
                        total_mc = float(mc.sum())
                        if total_mc > 0:
                            result_series: pd.Series = mc / total_mc
                            return result_series
                except (SourceError, DataIntegrityError, SchemaError, KeyError) as exc:
                    logger.warning(
                        "MCW fallback to equal-weight: fundamentals unavailable "
                        "(weighting=%s, asof=%s, n_symbols=%d): %s",
                        self._weighting,
                        self._asof,
                        len(symbols),
                        exc,
                    )
            # Fall back to equal weight
            n = len(symbols)
            return pd.Series(1.0 / n, index=symbols)

        # Default
        n = len(symbols)
        return pd.Series(1.0 / n, index=symbols)

    def _apply_constraint(
        self,
        constraint: Constraint,
        weights: pd.Series,
        selected: pd.DataFrame,
    ) -> tuple[pd.Series, ConstraintResult, list[str]]:
        """Apply one constraint with heuristic relaxation.

        Returns (new_weights, ConstraintResult, relaxation_notes).
        """
        notes: list[str] = []
        kind = constraint.kind

        if kind == "max_weight":
            w = float(constraint.params["w"])
            new_w = _cap_series(weights, w)
            breached = (weights > w).any()
            status: ConstraintStatus = "bound" if breached else "slack"
            if breached:
                notes.append(f"max_weight={w}: floored excess and redistributed pro-rata")
            return new_w, ConstraintResult(constraint=constraint, status=status), notes

        if kind == "max_gross":
            gross_limit = float(constraint.params["gross"])
            current_gross = float(weights.abs().sum())
            if current_gross <= gross_limit:
                return weights, ConstraintResult(constraint=constraint, status="slack"), notes
            new_w = weights * (gross_limit / current_gross)
            notes.append(
                f"max_gross={gross_limit}: scaled weights by {gross_limit / current_gross:.4f}"
            )
            return new_w, ConstraintResult(constraint=constraint, status="bound"), notes

        if kind == "min_positions":
            n_required = int(constraint.params["n"])
            n_active = int((weights > 0).sum())
            if n_active >= n_required:
                return weights, ConstraintResult(constraint=constraint, status="slack"), notes
            # Infeasible — can't add positions we don't have
            msg = f"min_positions={n_required}: only {n_active} available"
            notes.append(msg)
            return (
                weights,
                ConstraintResult(constraint=constraint, status="infeasible_relaxed", detail=msg),
                notes,
            )

        if kind == "max_positions":
            n_allowed = int(constraint.params["n"])
            n_active = int((weights > 0).sum())
            if n_active <= n_allowed:
                return weights, ConstraintResult(constraint=constraint, status="slack"), notes
            # Keep top-n by weight; zero out the rest
            top_symbols = weights.nlargest(n_allowed).index
            new_w = weights.copy()
            new_w[~new_w.index.isin(top_symbols)] = 0.0
            notes.append(
                f"max_positions={n_allowed}: dropped {n_active - n_allowed} smallest positions"
            )
            return new_w, ConstraintResult(constraint=constraint, status="bound"), notes

        if kind == "sector_neutral_to":
            # Heuristic: match present sectors to benchmark sector weights;
            # emit relaxation note for missing benchmark sectors
            if self._repo is None or self._asof is None:
                notes.append("sector_neutral_to: no repo/asof; skipping")
                return (
                    weights,
                    ConstraintResult(
                        constraint=constraint, status="infeasible_relaxed", detail="no repo"
                    ),
                    notes,
                )
            benchmark = str(constraint.params["benchmark"])
            symbols = weights[weights > 0].index.tolist()
            try:
                sectors = self._repo.get_sector(symbols)
                sector_map = sectors.set_index("symbol")["sector_l1"]
                # Get benchmark sector weights
                asof_d: date = self._asof
                bench_df = self._repo.get_universe_over_time(benchmark, asof_d, asof_d, freq="D")
                bench_syms = bench_df["symbol"].tolist() if not bench_df.empty else symbols
                bench_sectors = self._repo.get_sector(bench_syms)
                bench_sector_counts = bench_sectors["sector_l1"].value_counts(normalize=True)

                # Present sectors in portfolio
                portfolio_sectors = sector_map.reindex(symbols)
                missing = set(bench_sector_counts.index) - set(portfolio_sectors.dropna().unique())
                if missing:
                    notes.append(
                        f"sector_neutral_to: benchmark sectors missing in universe: {missing}"
                    )

                # Rescale weights within each sector
                new_w = weights.copy()
                for sector, bench_wt in bench_sector_counts.items():
                    sec_syms = [s for s in symbols if portfolio_sectors.get(s) == sector]
                    if not sec_syms:
                        continue
                    current_sec_wt = float(new_w[sec_syms].sum())
                    if current_sec_wt == 0:
                        continue
                    scale = float(bench_wt) / current_sec_wt
                    new_w[sec_syms] = new_w[sec_syms] * scale

                status_sn: ConstraintStatus = "infeasible_relaxed" if missing else "bound"
                return new_w, ConstraintResult(constraint=constraint, status=status_sn), notes
            except (SourceError, DataIntegrityError, SchemaError, KeyError) as e:
                # Expected failure modes: benchmark not cached, sector data
                # missing, or column-name drift. Anything else (TypeError,
                # ArithmeticError) is a bug and should propagate.
                logger.warning(
                    "sector_neutral_to relaxed: data unavailable (benchmark=%s, asof=%s): %s",
                    benchmark,
                    self._asof,
                    e,
                )
                notes.append(f"sector_neutral_to: error {e}; skipping")
                return (
                    weights,
                    ConstraintResult(
                        constraint=constraint, status="infeasible_relaxed", detail=str(e)
                    ),
                    notes,
                )

        if kind == "tracking_error":
            # Heuristic: shrink toward equal weight (benchmark proxy)
            bps = int(constraint.params["bps"])
            # Simple proxy: blend toward equal-weight until TE budget is met
            # We approximate TE as stddev(w - bm_w) * sqrt(252) * 10000 bps
            n = len(weights)
            if n == 0:
                return weights, ConstraintResult(constraint=constraint, status="slack"), notes
            bm_w = pd.Series(1.0 / n, index=weights.index)
            active = weights - bm_w
            active_arr = active.to_numpy(dtype=float)
            te_bps = float(np.std(active_arr) * np.sqrt(TRADING_DAYS_PER_YEAR) * BPS_PER_UNIT)
            if te_bps <= bps:
                return weights, ConstraintResult(constraint=constraint, status="slack"), notes
            # Shrink: w_new = alpha*w + (1-alpha)*bm_w; solve for alpha
            target = bps / BPS_PER_UNIT  # as fraction
            current_te_frac = float(np.std(active_arr) * np.sqrt(TRADING_DAYS_PER_YEAR))
            if current_te_frac == 0:
                return weights, ConstraintResult(constraint=constraint, status="slack"), notes
            alpha = target / current_te_frac
            alpha = min(1.0, max(0.0, alpha))
            new_w = alpha * weights + (1 - alpha) * bm_w
            notes.append(
                f"tracking_error={bps}bps: blended alpha={alpha:.4f} toward equal-weight benchmark"
            )
            return (
                new_w,
                ConstraintResult(constraint=constraint, status="bound"),
                notes,
            )

        # Unknown constraint kind — pass through
        notes.append(f"Unknown constraint kind {kind!r}; skipped")
        return (
            weights,
            ConstraintResult(
                constraint=constraint, status="infeasible_relaxed", detail=f"unknown kind {kind!r}"
            ),
            notes,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _cap_series(weights: pd.Series, max_w: float) -> pd.Series:
    """Cap-and-redistribute (heuristic), mirroring portfolio/construction.cap_at."""
    w = weights.to_numpy().copy().astype(float)
    while True:
        over = w > max_w
        if not over.any():
            break
        excess = float((w[over] - max_w).sum())
        w[over] = max_w
        under_mask = (w < max_w) & (w > 0)
        if not under_mask.any():
            break
        under_sum = float(w[under_mask].sum())
        if under_sum == 0:
            break
        w[under_mask] += excess * (w[under_mask] / under_sum)
    return pd.Series(w, index=weights.index)


__all__ = [
    "Constraint",
    "ConstraintResult",
    "ConstructionReport",
    "Constructor",
]
