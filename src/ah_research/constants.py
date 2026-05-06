"""Numerical and financial constants used across the package.

Promoted from inline literals so meaning is explicit and values can be
changed in one place. Keep this file small and dependency-free.
"""

from __future__ import annotations

TRADING_DAYS_PER_YEAR: int = 252
"""Standard equity-market convention for annualizing daily stats."""

BPS_PER_UNIT: int = 10_000
"""Basis-points per 1.0 (100% = 10,000 bps)."""

LEVERAGE_SUM_TOLERANCE: float = 1e-6
"""Floating-point tolerance when checking that |weights| ≤ 1.0."""

CANARY_EQUITY_TOLERANCE: float = 1e-6
"""Floating-point tolerance for leakage / canary equity checks."""
