"""Metrics bundle — stub for Tasks 9-14; full implementation in Task 15-18."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricsBundle:
    """Placeholder metrics bundle. Full implementation in Task 15."""

    cagr: float | None = None
    total_return: float | None = None
    annualized_vol: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown: float | None = None
    calmar: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        """Return metrics as a plain dict."""
        return {
            "cagr": self.cagr,
            "total_return": self.total_return,
            "annualized_vol": self.annualized_vol,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown": self.max_drawdown,
            "calmar": self.calmar,
        }
