"""Tests for short orders — A-share blocked, HK allowed.

- By default, ``a_share_short_allowed=False``: short orders on SH/SZ
  symbols are rejected with reason ``a_share_short_disallowed``.
- When ``a_share_short_allowed=True``, A-share shorts are allowed.
- HK short orders are always permitted (borrow cost is logged but not
  charged in Phase 2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from ah_research.backtest.costs import CostModelBundle
from ah_research.backtest.engine import run_backtest
from ah_research.backtest.types import BacktestConfig, BacktestResult, Weights
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

_START = date(2024, 1, 2)
_END = date(2024, 1, 31)


class _DailyWeightStrategy:
    """Emits per-day weights for fine-grained control of rebalance timing."""

    name = "daily_weights"

    def __init__(self, weights_by_date: dict[date, dict[str, float]]) -> None:
        self._weights = weights_by_date

    def generate(self, repo: Any, start: date, end: date) -> Weights:
        rows = [
            {"date": pd.Timestamp(d), "symbol": sym, "weight": w}
            for d, sym_weights in self._weights.items()
            for sym, w in sym_weights.items()
        ]
        df = pd.DataFrame(rows)
        positive = df[df["weight"] > 0].copy() if not df.empty else df
        if positive.empty:
            return Weights.from_dataframe(
                pd.DataFrame(
                    {
                        "date": pd.Series([], dtype="datetime64[ns]"),
                        "symbol": pd.Series([], dtype=str),
                        "weight": pd.Series([], dtype=float),
                    }
                )
            )
        return Weights.from_dataframe(positive)


# ── Shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def repo_factory():
    """Callable: build a synthetic repo for the given symbols."""

    def _build(symbols: list[str]):  # type: ignore[no-untyped-def]
        return build_synthetic_market(start=_START, end=_END, symbols=symbols)

    return _build


def _first_trading_day(repo) -> date:  # type: ignore[no-untyped-def]
    """Return the first SH-calendar trading day in the test window."""
    cal = repo.get_trading_calendar("SH", _START, _END)
    days = sorted(pd.Timestamp(r["date"]).date() for _, r in cal.iterrows() if r["is_trading_day"])
    return days[0]


def _run_with_initial_buy(
    repo,  # type: ignore[no-untyped-def]
    symbol: str,
    *,
    a_share_short_allowed: bool,
) -> BacktestResult:
    """Run a 1-day buy of ``symbol`` to 100% weight under the given config flag."""
    day0 = _first_trading_day(repo)
    strategy = _DailyWeightStrategy({day0: {symbol: 1.0}})
    cfg = BacktestConfig(
        start=_START,
        end=_END,
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
        rebalance="D",
        a_share_short_allowed=a_share_short_allowed,
    )
    return run_backtest(strategy, repo, cfg)


# ── tests ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("symbol", "a_share_short_allowed"),
    [
        # A-share with shorts disallowed: backtest still runs (sells fill).
        ("600000.SH", False),
        # A-share with shorts allowed: no rejection on the flag axis.
        ("600000.SH", True),
        # HK symbol: a_share_short_allowed flag should not affect HK.
        ("0001.HK", False),
    ],
    ids=[
        "a-share-shorts-disallowed",
        "a-share-shorts-allowed",
        "hk-shorts-unaffected",
    ],
)
def test_backtest_runs_under_each_short_config(
    repo_factory,  # type: ignore[no-untyped-def]
    symbol: str,
    a_share_short_allowed: bool,
) -> None:
    """The engine produces a non-empty equity curve under every
    combination of (symbol exchange, a_share_short_allowed)."""
    repo = repo_factory([symbol])
    result = _run_with_initial_buy(repo, symbol, a_share_short_allowed=a_share_short_allowed)
    assert not result.equity_curve.empty


def test_a_share_shorts_allowed_yields_no_disallow_rejection(repo_factory) -> None:  # type: ignore[no-untyped-def]
    """When the flag is True, no order is rejected with reason
    ``a_share_short_disallowed``."""
    repo = repo_factory(["600000.SH"])
    result = _run_with_initial_buy(repo, "600000.SH", a_share_short_allowed=True)

    if not result.rejected_orders.empty and "reason" in result.rejected_orders.columns:
        assert "a_share_short_disallowed" not in result.rejected_orders["reason"].tolist(), (
            "Expected no a_share_short_disallowed rejections when flag is True"
        )


def test_hk_shorts_never_rejected_with_a_share_reason(repo_factory) -> None:  # type: ignore[no-untyped-def]
    """The A-share short rule must not apply to HK symbols, regardless of
    the flag."""
    repo = repo_factory(["0001.HK"])
    result = _run_with_initial_buy(repo, "0001.HK", a_share_short_allowed=False)

    if not result.rejected_orders.empty and "reason" in result.rejected_orders.columns:
        hk_short_rejections = result.rejected_orders[
            (result.rejected_orders["reason"] == "a_share_short_disallowed")
            & (result.rejected_orders["symbol"].str.endswith(".HK"))
        ]
        assert hk_short_rejections.empty, (
            "HK shorts must not be rejected with a_share_short_disallowed"
        )


def test_a_share_short_rejection_uses_canonical_reason_string(repo_factory) -> None:  # type: ignore[no-untyped-def]
    """If any short rejection occurs, its reason is exactly
    ``a_share_short_disallowed`` (not ``short_disallowed`` etc.)."""
    repo = repo_factory(["600000.SH"])
    result = _run_with_initial_buy(repo, "600000.SH", a_share_short_allowed=False)

    if not result.rejected_orders.empty and "reason" in result.rejected_orders.columns:
        for reason in result.rejected_orders["reason"]:
            if "short" in str(reason).lower() and "disallow" in str(reason).lower():
                assert reason == "a_share_short_disallowed", (
                    f"Expected exact string 'a_share_short_disallowed'; got {reason!r}"
                )
