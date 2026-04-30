"""OptimizationResult — structured output of Optimizer.build()."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import pandas as pd

ObjectiveName = Literal["mean_variance", "risk_parity"]
SolverStatus = Literal["optimal", "optimal_inaccurate", "soft_relaxed"]


@dataclass(frozen=True)
class OptimizationResult:
    """Frozen container for optimizer output + diagnostics.

    See docs/superpowers/specs/2026-04-30-ah-research-phase-4-1-optimizer-design.md §5.4.
    """

    weights: pd.Series
    objective: ObjectiveName
    solver_status: SolverStatus
    objective_value: float
    active_constraints: tuple[str, ...]
    slack: Mapping[str, float]
    expected_return: float | None
    expected_variance: float
    risk_contributions: pd.Series | None
    solver_name: str
    solve_time_ms: float
    inputs_hash: str

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable dict representation."""
        return {
            "weights": self.weights.to_dict(),
            "objective": self.objective,
            "solver_status": self.solver_status,
            "objective_value": self.objective_value,
            "active_constraints": list(self.active_constraints),
            "slack": dict(self.slack),
            "expected_return": self.expected_return,
            "expected_variance": self.expected_variance,
            "risk_contributions": (
                self.risk_contributions.to_dict() if self.risk_contributions is not None else None
            ),
            "solver_name": self.solver_name,
            "solve_time_ms": self.solve_time_ms,
            "inputs_hash": self.inputs_hash,
        }

    def to_markdown(self) -> str:
        """Human-readable summary."""
        lines: list[str] = []
        lines.append(f"# Optimization Result ({self.objective})")
        lines.append("")
        lines.append(f"- **Solver:** {self.solver_name} ({self.solver_status})")
        lines.append(f"- **Objective value:** {self.objective_value:.6g}")
        lines.append(f"- **Expected variance:** {self.expected_variance:.6g}")
        if self.expected_return is not None:
            lines.append(f"- **Expected return:** {self.expected_return:.6g}")
        if self.active_constraints:
            lines.append(f"- **Active constraints:** {', '.join(self.active_constraints)}")
        if self.slack:
            lines.append(f"- **Slack (nonzero):** {dict(self.slack)}")
        lines.append(f"- **Solve time:** {self.solve_time_ms:.1f} ms")
        lines.append(f"- **Inputs hash:** `{self.inputs_hash[:12]}…`")
        lines.append("")
        lines.append("## Weights")
        lines.append("")
        lines.append("| Symbol | Weight |")
        lines.append("|---|---|")
        for sym, w in self.weights.sort_values(ascending=False).items():
            lines.append(f"| {sym} | {w:.4f} |")
        if self.risk_contributions is not None:
            lines.append("")
            lines.append("## Risk contributions")
            lines.append("")
            lines.append("| Symbol | Contribution |")
            lines.append("|---|---|")
            for sym, rc in self.risk_contributions.sort_values(ascending=False).items():
                lines.append(f"| {sym} | {rc:.4f} |")
        return "\n".join(lines)
