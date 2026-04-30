"""Tests for OptimizedWeightStrategy."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from ah_research.strategies.base import WeightStrategy
from ah_research.strategies.optimized import OptimizedWeightStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SYMBOLS = ["000001.SZ", "000002.SZ", "600000.SH"]


def _prices_fixture(symbols: list[str], n_days: int = 400) -> pd.DataFrame:
    """Generate synthetic prices with ``ds``, ``symbol``, ``close_hfq``, ``total_return``."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    rows = []
    for sym in symbols:
        r = rng.normal(0.0002, 0.01, size=n_days)
        prices = 100.0 * np.exp(np.cumsum(r))
        for d, p, ret in zip(dates, prices, r, strict=False):
            rows.append({"ds": d, "symbol": sym, "close_hfq": p, "total_return": ret})
    return pd.DataFrame(rows)


@pytest.fixture()
def prices():
    return _prices_fixture(SYMBOLS)


@pytest.fixture()
def mock_repo(prices):
    repo = MagicMock()
    repo.get_prices.return_value = prices
    return repo


@pytest.fixture()
def mock_optimizer():
    """A mock Optimizer whose build() returns a realistic OptimizationResult."""
    from ah_research.portfolio.optimizer.result import OptimizationResult

    def _build(symbols, as_of, repo, *, prev_weights=None):
        n = len(symbols)
        w = pd.Series([1.0 / n] * n, index=symbols)
        return OptimizationResult(
            weights=w,
            objective="risk_parity",
            solver_status="optimal",
            objective_value=0.0,
            active_constraints=(),
            slack={},
            expected_return=None,
            expected_variance=1e-4,
            risk_contributions=w.copy(),
            solver_name="osqp",
            solve_time_ms=1.0,
            inputs_hash="abc123",
        )

    opt = MagicMock()
    opt.build.side_effect = _build
    return opt


# ---------------------------------------------------------------------------
# Test 1: satisfies WeightStrategy protocol
# ---------------------------------------------------------------------------


def test_strategy_satisfies_protocol(mock_optimizer):
    strategy = OptimizedWeightStrategy(
        optimizer=mock_optimizer,
        symbols=SYMBOLS,
        rebalance_freq="ME",
        name="test_opt",
    )
    assert isinstance(strategy, WeightStrategy), (
        "OptimizedWeightStrategy must satisfy the WeightStrategy protocol"
    )


# ---------------------------------------------------------------------------
# Test 2: generate produces weights at each rebalance date
# ---------------------------------------------------------------------------


def test_generate_produces_weights_at_each_rebalance(mock_optimizer, mock_repo):
    strategy = OptimizedWeightStrategy(
        optimizer=mock_optimizer,
        symbols=SYMBOLS,
        rebalance_freq="ME",
        name="test_opt",
    )

    start = date(2023, 6, 1)
    end = date(2023, 12, 31)

    weights = strategy.generate(mock_repo, start, end)

    # history must have at least one entry (7 month-end dates between Jun-Dec)
    assert len(strategy.history) >= 1

    # The returned Weights.df must have date, symbol, weight columns
    df = weights.df
    assert set(df.columns) >= {"date", "symbol", "weight"}

    # For each rebalance result, the weights (from OptimizationResult) sum to ~1
    for result in strategy.history:
        assert abs(result.weights.sum() - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Test 3: prev_weights is None on first call, non-None on subsequent calls
# ---------------------------------------------------------------------------


def test_prev_weights_passed_on_subsequent_rebalances(mock_optimizer, mock_repo):
    strategy = OptimizedWeightStrategy(
        optimizer=mock_optimizer,
        symbols=SYMBOLS,
        rebalance_freq="ME",
        name="test_opt",
    )

    # Use a 3-month window to guarantee at least 3 rebalance dates
    start = date(2023, 9, 1)
    end = date(2023, 12, 31)

    strategy.generate(mock_repo, start, end)

    calls = mock_optimizer.build.call_args_list
    assert len(calls) >= 2, "Expected at least 2 rebalance calls for 3-month window"

    # First call: prev_weights must be None
    first_kwargs = calls[0].kwargs if calls[0].kwargs else {}
    assert first_kwargs.get("prev_weights") is None, (
        f"First call prev_weights should be None, got {first_kwargs.get('prev_weights')}"
    )

    # All subsequent calls: prev_weights must be a pd.Series (not None)
    for i, c in enumerate(calls[1:], start=2):
        kwargs = c.kwargs if c.kwargs else {}
        prev = kwargs.get("prev_weights")
        assert isinstance(prev, pd.Series), (
            f"Call #{i} prev_weights should be pd.Series, got {type(prev)}"
        )
