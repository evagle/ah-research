"""Unit tests for ``backtest.backtest_loop.BacktestLoop`` (carved out in C1-06).

Pins the contract of the public façade: phase wiring, the
``run_backtest`` delegation contract, and the error paths surfaced by
the orchestrator (empty trading days, NaN weights, leverage cap).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from ah_research.backtest.backtest_loop import BacktestLoop
from ah_research.backtest.engine import run_backtest
from ah_research.backtest.types import BacktestConfig, BacktestResult, Weights
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ─── helpers ────────────────────────────────────────────────────────────────


class _FixedLongStrategy:
    """100% weight in 600000.SH at each month-end."""

    name = "fixed_long"

    def generate(self, repo: object, start: date, end: date) -> Weights:
        eom = pd.date_range(start, end, freq="ME")
        df = pd.DataFrame(
            {
                "date": eom,
                "symbol": ["600000.SH"] * len(eom),
                "weight": [1.0] * len(eom),
            }
        )
        return Weights.from_dataframe(df)


class _NaNWeightStrategy:
    """Emits a NaN weight; the loop should re-raise as ValueError."""

    name = "nan_weight"

    def generate(self, repo: object, start: date, end: date) -> Weights:
        eom = pd.date_range(start, end, freq="ME")
        df = pd.DataFrame(
            {
                "date": eom,
                "symbol": ["600000.SH"] * len(eom),
                "weight": [float("nan")] * len(eom),
            }
        )
        # Bypass schema validation by constructing directly; we want the
        # engine's belt-and-suspenders NaN check to fire.
        return Weights(df=df)


class _OverleveragedStrategy:
    """Emits abs(weight).sum() > 1; with allow_leverage=False this should raise."""

    name = "leveraged"

    def generate(self, repo: object, start: date, end: date) -> Weights:
        eom = pd.date_range(start, end, freq="ME")
        rows = []
        for d in eom:
            rows.append({"date": d, "symbol": "600000.SH", "weight": 0.8})
            rows.append({"date": d, "symbol": "600519.SH", "weight": 0.8})
        return Weights.from_dataframe(pd.DataFrame(rows))


# ─── façade delegation ────────────────────────────────────────────────────


def test_run_backtest_delegates_to_backtest_loop_run() -> None:
    """``run_backtest`` is a thin wrapper; ``BacktestLoop(...).run()``
    must produce an equivalent result."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 3, 31), symbols=["600000.SH"]
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
    )

    via_function = run_backtest(_FixedLongStrategy(), repo, cfg)
    via_class = BacktestLoop(strategy=_FixedLongStrategy(), repo=repo, config=cfg).run()

    assert isinstance(via_function, BacktestResult)
    assert isinstance(via_class, BacktestResult)
    # Same equity curve to the cent.
    pd.testing.assert_series_equal(
        via_function.equity_curve, via_class.equity_curve, check_exact=True
    )
    # Same trade log.
    pd.testing.assert_frame_equal(via_function.trades, via_class.trades)


def test_run_returns_populated_result() -> None:
    """Smoke test that all four phases run and BacktestResult fields populate."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 3, 31), symbols=["600000.SH"]
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
    )
    result = BacktestLoop(strategy=_FixedLongStrategy(), repo=repo, config=cfg).run()

    assert len(result.equity_curve) > 30
    assert result.equity_curve.notna().all()
    assert len(result.trades) >= 1
    assert result.config_hash != ""
    assert result.code_version != ""
    # Cash history was populated by MTMAccumulator.
    assert len(result.cash_history) == len(result.equity_curve)


# ─── error paths ──────────────────────────────────────────────────────────


def test_empty_trading_days_raises_value_error() -> None:
    """A date window with no trading days surfaces as ValueError from setup."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 1, 5), symbols=["600000.SH"]
    )
    # Pick a window that spans only a weekend.
    cfg = BacktestConfig(
        start=date(2024, 1, 6),
        end=date(2024, 1, 7),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
    )
    with pytest.raises(ValueError, match="No trading days"):
        run_backtest(_FixedLongStrategy(), repo, cfg)


def test_nan_weights_raise_value_error() -> None:
    """Belt-and-suspenders NaN check fires even if pandera missed it."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 3, 31), symbols=["600000.SH"]
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
    )
    with pytest.raises(ValueError, match="NaN weights"):
        run_backtest(_NaNWeightStrategy(), repo, cfg)


def test_overleveraged_weights_raise_when_allow_leverage_false() -> None:
    """abs(weight).sum() > 1 is rejected when allow_leverage=False."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH", "600519.SH"],
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        allow_leverage=False,
    )
    with pytest.raises(ValueError, match="Weight sum"):
        run_backtest(_OverleveragedStrategy(), repo, cfg)


def test_overleveraged_weights_accepted_when_allow_leverage_true() -> None:
    """The leverage check is gated on allow_leverage=False."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH", "600519.SH"],
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        allow_leverage=True,
    )
    # No raise.
    result = run_backtest(_OverleveragedStrategy(), repo, cfg)
    assert len(result.equity_curve) > 0
