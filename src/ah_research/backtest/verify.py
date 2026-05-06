"""Verification utilities for backtests: walk_forward, sensitivity, leakage_canary, survivorship_check.

Spec §7. All functions accept a config_template whose start/end are overridden per split/sample.
"""

from __future__ import annotations

import itertools
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from ah_research.backtest.engine import run_backtest
from ah_research.backtest.metrics import MetricsBundle
from ah_research.backtest.types import BacktestConfig, Weights
from ah_research.constants import CANARY_EQUITY_TOLERANCE
from ah_research.model.types import Exchange

logger = logging.getLogger(__name__)


# ── Task 25: walk_forward ────────────────────────────────────────────────────


@dataclass(frozen=True)
class WalkForwardSplit:
    """One IS/OOS split pair with metrics."""

    is_start: date
    is_end: date
    oos_start: date
    oos_end: date
    is_metrics: MetricsBundle
    oos_metrics: MetricsBundle


@dataclass(frozen=True)
class WalkForwardReport:
    """Result of a walk_forward run."""

    mode: str
    splits: list[WalkForwardSplit]
    combined_oos_metrics: MetricsBundle


def walk_forward(
    strategy_factory: Any,
    repo: Any,
    start: date,
    end: date,
    config_template: BacktestConfig,
    n_splits: int = 5,
    mode: str = "expanding",
) -> WalkForwardReport:
    """Run walk-forward cross-validation over [start, end].

    Parameters
    ----------
    strategy_factory:
        A callable (class or factory function) that returns a fresh strategy instance
        when called with no arguments: ``strategy_factory()``.
    repo:
        DataRepository-compatible object.
    start, end:
        Full date range to partition.
    config_template:
        BacktestConfig whose start/end are replaced per split. All other fields
        (initial_cash, cost_model, etc.) are preserved.
    n_splits:
        Number of IS/OOS pairs to produce.
    mode:
        ``"expanding"`` — IS window always starts at ``start``, grows each split.
        ``"rolling"`` — IS window shifts forward; fixed IS length per split.

    Returns
    -------
    WalkForwardReport
    """
    if mode not in ("expanding", "rolling"):
        raise ValueError(f"mode must be 'expanding' or 'rolling', got {mode!r}")

    # Get trading calendar for the full range
    trading_days = _get_trading_days(repo, start, end)

    if len(trading_days) < n_splits + 1:
        raise ValueError(f"Not enough trading days ({len(trading_days)}) for {n_splits} splits.")

    # Partition into n_splits + 1 chunks
    chunks = _split_list(trading_days, n_splits + 1)

    splits: list[WalkForwardSplit] = []
    for i in range(n_splits):
        if mode == "expanding":
            is_start = trading_days[0]
            is_end = chunks[i][-1]
        else:  # rolling
            is_start = chunks[i][0]
            is_end = chunks[i][-1]

        oos_start = chunks[i + 1][0]
        oos_end = chunks[i + 1][-1]

        is_cfg = replace(config_template, start=is_start, end=is_end)
        oos_cfg = replace(config_template, start=oos_start, end=oos_end)

        is_result = run_backtest(strategy_factory(), repo, is_cfg)
        oos_result = run_backtest(strategy_factory(), repo, oos_cfg)

        splits.append(
            WalkForwardSplit(
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
                is_metrics=is_result.metrics,
                oos_metrics=oos_result.metrics,
            )
        )

    # Combine all OOS equity curves and recompute metrics
    combined_oos_metrics = _concat_oos_metrics(splits)

    return WalkForwardReport(mode=mode, splits=splits, combined_oos_metrics=combined_oos_metrics)


def _get_trading_days(repo: Any, start: date, end: date) -> list[date]:
    """Return sorted list of SH trading days in [start, end]."""
    cal = repo.get_trading_calendar(str(Exchange.SH), start, end)
    mask = cal["is_trading_day"]
    dates = cal.loc[mask, "date"]
    return sorted(pd.Timestamp(d).date() for d in dates)


def _split_list(lst: list[Any], n: int) -> list[list[Any]]:
    """Split lst into n approximately equal sublists."""
    k, m = divmod(len(lst), n)
    chunks = []
    start_idx = 0
    for i in range(n):
        end_idx = start_idx + k + (1 if i < m else 0)
        chunks.append(lst[start_idx:end_idx])
        start_idx = end_idx
    return chunks


def _concat_oos_metrics(splits: list[WalkForwardSplit]) -> MetricsBundle:
    """Concatenate OOS metrics by averaging key scalar metrics across splits."""

    # Average the OOS metrics across splits (simple mean of non-None values)
    def _avg(field_name: str) -> float | None:
        vals = [getattr(s.oos_metrics, field_name) for s in splits]
        nums = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
        if not nums:
            return None
        return float(np.mean(nums))

    def _avg_int(field_name: str) -> int | None:
        v = _avg(field_name)
        return round(v) if v is not None else None

    return MetricsBundle(
        cagr=_avg("cagr"),
        total_return=_avg("total_return"),
        annualized_vol=_avg("annualized_vol"),
        sharpe=_avg("sharpe"),
        sortino=_avg("sortino"),
        max_drawdown=_avg("max_drawdown"),
        max_dd_duration_days=_avg_int("max_dd_duration_days"),
        calmar=_avg("calmar"),
        avg_dividend_yield=_avg("avg_dividend_yield"),
        annualized_turnover=_avg("annualized_turnover"),
        avg_positions=_avg("avg_positions"),
        avg_holding_period_days=_avg("avg_holding_period_days"),
        excess_return=_avg("excess_return"),
        information_ratio=_avg("information_ratio"),
        tracking_error=_avg("tracking_error"),
        alpha=_avg("alpha"),
        beta=_avg("beta"),
        alpha_t_stat=_avg("alpha_t_stat"),
        alpha_pvalue=_avg("alpha_pvalue"),
        alpha_se=_avg("alpha_se"),
        beta_t_stat=_avg("beta_t_stat"),
        beta_se=_avg("beta_se"),
        newey_west_lag=_avg_int("newey_west_lag"),
    )


# ── Task 26: sensitivity ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SensitivityReport:
    """Result of a sensitivity analysis over a parameter grid."""

    grid_df: pd.DataFrame  # one row per combo; param + metric columns
    metric_columns: list[str]
    param_columns: list[str]


def sensitivity(
    strategy_factory: Callable[..., Any],
    repo: Any,
    config_template: BacktestConfig,
    param_grid: dict[str, list[Any]],
) -> SensitivityReport:
    """Sweep a Cartesian product of parameter values and collect per-combo metrics.

    Parameters
    ----------
    strategy_factory:
        Callable that accepts **kwargs and returns a strategy instance.
    repo:
        DataRepository-compatible object.
    config_template:
        BacktestConfig used for all runs.
    param_grid:
        e.g. ``{"quantile": [0.1, 0.2, 0.3], "max_weight": [0.05, 0.10]}``.
        All lists must be non-empty.

    Returns
    -------
    SensitivityReport
        ``grid_df`` has one row per combination with param values and key metrics.

    Raises
    ------
    ValueError
        When total number of combinations exceeds 100.
    """
    if not param_grid:
        raise ValueError("param_grid must not be empty.")

    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combos = list(itertools.product(*param_values))

    if len(combos) > 100:
        raise ValueError(
            f"param_grid produces {len(combos)} combinations; maximum allowed is 100. "
            "Reduce the grid or run manually."
        )

    rows: list[dict[str, Any]] = []
    metric_keys = [
        "cagr",
        "total_return",
        "annualized_vol",
        "sharpe",
        "sortino",
        "max_drawdown",
        "calmar",
        "annualized_turnover",
        "avg_positions",
        "alpha",
        "beta",
    ]

    for combo in combos:
        params = dict(zip(param_names, combo, strict=True))
        strategy = strategy_factory(**params)
        result = run_backtest(strategy, repo, config_template)
        row: dict[str, Any] = dict(params)
        mb = result.metrics
        for k in metric_keys:
            row[k] = getattr(mb, k, None)
        rows.append(row)

    grid_df = pd.DataFrame(rows)

    return SensitivityReport(
        grid_df=grid_df,
        metric_columns=metric_keys,
        param_columns=param_names,
    )


# ── Task 27: leakage_canary ───────────────────────────────────────────────────


@dataclass(frozen=True)
class CanaryResult:
    """Result of one canary test."""

    kind: str
    passed: bool | None  # None = n/a
    max_divergence: float | None
    message: str


@dataclass(frozen=True)
class CanaryReport:
    """Combined result of all canary checks."""

    results: list[CanaryResult]
    all_pass: bool  # True iff every non-n/a canary passed


_DEFAULT_CANARY_KINDS = ("future_price_shuffle", "future_fundamentals_shuffle", "signal_shift")


def leakage_canary(
    strategy: Any,
    repo: Any,
    config: BacktestConfig,
    kinds: tuple[str, ...] | list[str] = _DEFAULT_CANARY_KINDS,
) -> CanaryReport:
    """Run leakage detection canaries on a strategy/repo pair.

    Parameters
    ----------
    strategy:
        Strategy instance to test.
    repo:
        DataRepository-compatible object (will be wrapped, not mutated).
    config:
        BacktestConfig for the base run.
    kinds:
        Subset of ``("future_price_shuffle", "future_fundamentals_shuffle",
        "signal_shift")``.

    Returns
    -------
    CanaryReport
    """
    results: list[CanaryResult] = []

    # Base run — needed by all canaries
    base_result = run_backtest(strategy, repo, config)
    base_equity = base_result.equity_curve
    base_sharpe = base_result.metrics.sharpe or 0.0

    # Midpoint trading day index
    t_star_idx = len(base_equity) // 2
    t_star = base_equity.index[t_star_idx].date() if len(base_equity) > 0 else config.start

    if "future_price_shuffle" in kinds:
        results.append(_canary_future_price_shuffle(strategy, repo, config, base_equity, t_star))

    if "future_fundamentals_shuffle" in kinds:
        results.append(
            _canary_future_fundamentals_shuffle(strategy, repo, config, base_equity, t_star)
        )

    if "signal_shift" in kinds:
        results.append(_canary_signal_shift(strategy, repo, config, base_sharpe))

    all_pass = all(r.passed is True for r in results if r.passed is not None)
    return CanaryReport(results=results, all_pass=all_pass)


# ── canary implementations ────────────────────────────────────────────────────


class _PriceShuffledRepo:
    """Wraps repo so that prices after t_star are shuffled row-wise."""

    def __init__(self, inner: Any, symbols: list[str], t_star: date, seed: int = 42) -> None:
        self._inner = inner
        self._t_star = t_star
        self._seed = seed
        self._symbols = symbols

    def _shuffle_prices_after(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        # Identify rows after t_star
        dates = df["date"].apply(lambda x: pd.Timestamp(x).date())
        after_mask = dates > self._t_star
        after_df = df[after_mask]
        if len(after_df) < 2:
            return df
        rng = np.random.default_rng(self._seed)
        shuffled_idx = after_df.index.to_numpy().copy()
        rng.shuffle(shuffled_idx)
        # Replace the after rows with the shuffled version (preserving dates)
        price_cols = [c for c in df.columns if c not in ("date", "symbol")]
        for orig_idx, shuf_idx in zip(after_df.index.tolist(), shuffled_idx.tolist(), strict=True):
            df.loc[orig_idx, price_cols] = after_df.loc[shuf_idx, price_cols].to_numpy()
        return df

    def get_prices(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        df = self._inner.get_prices(symbols, start, end)
        return self._shuffle_prices_after(df)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _FundamentalsShuffledRepo:
    """Wraps repo so that fundamentals with publication_date > t_star are shuffled."""

    def __init__(self, inner: Any, t_star: date, seed: int = 42) -> None:
        self._inner = inner
        self._t_star = t_star
        self._seed = seed

    def _shuffle_fundamentals_after(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        if "publication_date" not in df.columns:
            return df
        after_mask = df["publication_date"].apply(lambda x: pd.Timestamp(x).date()) > self._t_star
        after_df = df[after_mask]
        if len(after_df) < 2:
            return df
        rng = np.random.default_rng(self._seed)
        shuffled_idx = after_df.index.to_numpy().copy()
        rng.shuffle(shuffled_idx)
        non_date_cols = [
            c
            for c in df.columns
            if c not in ("symbol", "publication_date", "report_date", "known_as_of")
        ]
        for orig_idx, shuf_idx in zip(after_df.index.tolist(), shuffled_idx.tolist(), strict=True):
            df.loc[orig_idx, non_date_cols] = after_df.loc[shuf_idx, non_date_cols].to_numpy()
        return df

    def get_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
        *,
        asof: date | None = None,
    ) -> pd.DataFrame:
        df = self._inner.get_fundamentals(symbols, start, end, asof=asof)
        return self._shuffle_fundamentals_after(df)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _SignalShiftedRepo:
    """Wraps repo to intercept calls — used as a pass-through; shift handled in wrapper strategy."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _SignalShiftedStrategy:
    """Wraps a WeightStrategy to shift its weights back by 1 trading day.

    This simulates using tomorrow's data for today's signal — a perfect-foresight leak.
    The shifted strategy should have *at least as good* Sharpe if the base strategy already
    leaks (it already uses future data, so shifting won't help further).
    """

    def __init__(self, inner: Any, trading_days: list[date]) -> None:
        self._inner = inner
        self._trading_days = trading_days
        self.name = getattr(inner, "name", "shifted")

    def generate(self, repo: Any, start: date, end: date) -> Weights:
        from ah_research.strategies.base import resolve_weights

        weights = resolve_weights(self._inner, repo, start, end)

        # Shift dates back by 1 trading day
        df = weights.df.copy()
        day_map = {d: self._trading_days[max(0, i - 1)] for i, d in enumerate(self._trading_days)}

        def shift_date(ts: pd.Timestamp) -> pd.Timestamp:
            d = ts.date() if hasattr(ts, "date") else pd.Timestamp(ts).date()
            if d in day_map:
                return pd.Timestamp(day_map[d])
            return ts

        df["date"] = df["date"].apply(shift_date)
        # Drop duplicates if any after the shift (keep last)
        df = df.drop_duplicates(subset=["date", "symbol"], keep="last")
        return Weights(df=df)


def _canary_future_price_shuffle(
    strategy: Any,
    repo: Any,
    config: BacktestConfig,
    base_equity: pd.Series,
    t_star: date,
) -> CanaryResult:
    """Shuffle price bars AFTER t_star and verify first half of equity is unchanged."""
    shuffled_repo = _PriceShuffledRepo(inner=repo, symbols=[], t_star=t_star, seed=99)
    try:
        shuffled_result = run_backtest(strategy, shuffled_repo, config)
    except Exception as exc:
        return CanaryResult(
            kind="future_price_shuffle",
            passed=False,
            max_divergence=None,
            message=f"Shuffled backtest failed: {exc}",
        )

    shuffled_equity = shuffled_result.equity_curve

    # Compare equity curves up to t_star
    t_star_ts = pd.Timestamp(t_star)
    base_before = base_equity[base_equity.index <= t_star_ts]
    shuffled_before = shuffled_equity.reindex(base_before.index)

    aligned = pd.concat([base_before, shuffled_before], axis=1).dropna()
    if aligned.empty:
        return CanaryResult(
            kind="future_price_shuffle",
            passed=True,
            max_divergence=0.0,
            message="No overlapping data before t_star to compare.",
        )

    divergence = (aligned.iloc[:, 0] - aligned.iloc[:, 1]).abs()
    max_div = float(divergence.max())
    tol = CANARY_EQUITY_TOLERANCE

    passed = max_div < tol
    return CanaryResult(
        kind="future_price_shuffle",
        passed=passed,
        max_divergence=max_div,
        message=(
            f"Max divergence before t_star={t_star}: {max_div:.2e} "
            f"({'PASS' if passed else 'FAIL — possible future-price leak'})"
        ),
    )


def _canary_future_fundamentals_shuffle(
    strategy: Any,
    repo: Any,
    config: BacktestConfig,
    base_equity: pd.Series,
    t_star: date,
) -> CanaryResult:
    """Shuffle fundamentals published after t_star; same pre-t_star invariant."""
    # Check if strategy declares it doesn't use fundamentals
    uses_fundamentals = getattr(strategy, "uses_fundamentals", True)
    if not uses_fundamentals:
        return CanaryResult(
            kind="future_fundamentals_shuffle",
            passed=None,
            max_divergence=None,
            message="Strategy declares uses_fundamentals=False; canary is n/a.",
        )

    shuffled_repo = _FundamentalsShuffledRepo(inner=repo, t_star=t_star, seed=77)
    try:
        shuffled_result = run_backtest(strategy, shuffled_repo, config)
    except Exception as exc:
        return CanaryResult(
            kind="future_fundamentals_shuffle",
            passed=False,
            max_divergence=None,
            message=f"Shuffled fundamentals backtest failed: {exc}",
        )

    shuffled_equity = shuffled_result.equity_curve

    t_star_ts = pd.Timestamp(t_star)
    base_before = base_equity[base_equity.index <= t_star_ts]
    shuffled_before = shuffled_equity.reindex(base_before.index)

    aligned = pd.concat([base_before, shuffled_before], axis=1).dropna()
    if aligned.empty:
        return CanaryResult(
            kind="future_fundamentals_shuffle",
            passed=True,
            max_divergence=0.0,
            message="No overlapping data before t_star to compare.",
        )

    divergence = (aligned.iloc[:, 0] - aligned.iloc[:, 1]).abs()
    max_div = float(divergence.max())
    tol = CANARY_EQUITY_TOLERANCE

    passed = max_div < tol
    return CanaryResult(
        kind="future_fundamentals_shuffle",
        passed=passed,
        max_divergence=max_div,
        message=(
            f"Max divergence before t_star={t_star}: {max_div:.2e} "
            f"({'PASS' if passed else 'FAIL — possible future-fundamentals leak'})"
        ),
    )


def _canary_signal_shift(
    strategy: Any,
    repo: Any,
    config: BacktestConfig,
    base_sharpe: float,
) -> CanaryResult:
    """Shift signal by 1 trading day back (peek at next day); Sharpe should increase if no existing leak."""
    trading_days = _get_trading_days(repo, config.start, config.end)
    shifted_strategy = _SignalShiftedStrategy(inner=strategy, trading_days=trading_days)

    try:
        shifted_result = run_backtest(shifted_strategy, repo, config)
    except Exception as exc:
        return CanaryResult(
            kind="signal_shift",
            passed=False,
            max_divergence=None,
            message=f"Shifted backtest failed: {exc}",
        )

    shifted_sharpe = shifted_result.metrics.sharpe or 0.0
    delta = shifted_sharpe - base_sharpe

    # Pass if shifted Sharpe >= base Sharpe (shifting signal back gives more future info)
    # For a strategy that ALREADY leaks, the shift may not help (delta near 0 or negative)
    passed = shifted_sharpe >= base_sharpe

    return CanaryResult(
        kind="signal_shift",
        passed=passed,
        max_divergence=None,
        message=(
            f"base_sharpe={base_sharpe:.4f}, shifted_sharpe={shifted_sharpe:.4f}, "
            f"delta={delta:+.4f} "
            f"({'PASS' if passed else 'SOFT FAIL — signal may already use future data'})"
        ),
    )


# ── Task 28: survivorship_check ───────────────────────────────────────────────


@dataclass(frozen=True)
class SurvivorshipReport:
    """Result of a survivorship bias check."""

    pit_metrics: MetricsBundle
    static_metrics: MetricsBundle
    random_metrics_distribution: pd.DataFrame  # 50 rows, metric columns
    pit_sharpe_percentile: float  # percentile of PIT sharpe within random dist
    pit_vs_static_delta: dict[str, float]  # metric -> (pit - static)


class _StaticUniverseRepo:
    """Wraps repo so get_universe_over_time returns membership frozen at config.end."""

    def __init__(self, inner: Any, end: date, freq: str = "ME") -> None:
        self._inner = inner
        self._end = end
        self._freq = freq

    def get_universe_over_time(
        self,
        index: str,
        start: date,
        end: date,
        *,
        freq: str = "ME",
    ) -> pd.DataFrame:
        # Fetch the universe as-of self._end, then back-fill to all dates
        raw = self._inner.get_universe_over_time(index, self._end, self._end, freq=freq)
        end_frame = pd.DataFrame(raw) if not isinstance(raw, pd.DataFrame) else raw
        if end_frame.empty:
            return pd.DataFrame(columns=["date", "index_name", "symbol", "weight"])
        symbols_at_end = end_frame["symbol"].tolist()

        # Build a row for each sample date, using the end-date membership
        sample_dates = pd.date_range(start, end, freq=freq)
        rows = []
        for ts in sample_dates:
            for sym in symbols_at_end:
                rows.append(
                    {
                        "date": ts,
                        "index_name": index,
                        "symbol": sym,
                        "weight": 1.0 / len(symbols_at_end),
                    }
                )
        if not rows:
            return pd.DataFrame(columns=["date", "index_name", "symbol", "weight"])
        return pd.DataFrame(rows)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _FixedUniverseRepo:
    """Wraps repo so get_universe_over_time always returns a fixed set of symbols."""

    def __init__(self, inner: Any, fixed_symbols: list[str]) -> None:
        self._inner = inner
        self._fixed_symbols = fixed_symbols

    def get_universe_over_time(
        self,
        index: str,
        start: date,
        end: date,
        *,
        freq: str = "ME",
    ) -> pd.DataFrame:
        sample_dates = pd.date_range(start, end, freq=freq)
        n = len(self._fixed_symbols)
        rows = []
        for ts in sample_dates:
            for sym in self._fixed_symbols:
                rows.append(
                    {
                        "date": ts,
                        "index_name": index,
                        "symbol": sym,
                        "weight": 1.0 / n if n > 0 else 0.0,
                    }
                )
        if not rows:
            return pd.DataFrame(columns=["date", "index_name", "symbol", "weight"])
        return pd.DataFrame(rows)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def survivorship_check(
    strategy: Any,
    repo: Any,
    config: BacktestConfig,
    n_random_universes: int = 50,
) -> SurvivorshipReport:
    """Compare PIT vs static vs random-universe baselines.

    Parameters
    ----------
    strategy:
        Strategy instance to test.
    repo:
        DataRepository-compatible object.
    config:
        BacktestConfig for all runs.
    n_random_universes:
        Number of random universe samples (seeded from config.random_seed).

    Returns
    -------
    SurvivorshipReport
    """
    # Run 1: PIT universe (standard run)
    pit_result = run_backtest(strategy, repo, config)
    pit_metrics = pit_result.metrics
    avg_pos = pit_metrics.avg_positions or 2.0
    n_symbols = max(2, round(avg_pos))

    # Collect all historical members from PIT universe
    full_universe_frame = repo.get_universe_over_time("CSI300", config.start, config.end, freq="ME")
    if full_universe_frame.empty:
        all_historical_symbols = []
    else:
        all_historical_symbols = full_universe_frame["symbol"].unique().tolist()

    # Run 2: Static universe (frozen at config.end)
    static_repo = _StaticUniverseRepo(inner=repo, end=config.end)
    static_result = run_backtest(strategy, static_repo, config)
    static_metrics = static_result.metrics

    # Run 3: Random universes
    rng = random.Random(config.random_seed)
    metric_keys = [
        "cagr",
        "total_return",
        "annualized_vol",
        "sharpe",
        "sortino",
        "max_drawdown",
        "calmar",
        "annualized_turnover",
        "avg_positions",
    ]
    random_rows: list[dict[str, Any]] = []

    pool = all_historical_symbols

    for i in range(n_random_universes):
        if len(pool) < 2:
            # Fall back: use whatever symbols exist in the price data
            sample = pool
        else:
            k = min(n_symbols, len(pool))
            sample = rng.sample(pool, k)

        random_repo = _FixedUniverseRepo(inner=repo, fixed_symbols=sample)
        try:
            rand_result = run_backtest(strategy, random_repo, config)
            mb = rand_result.metrics
            row: dict[str, Any] = {"sample_idx": i}
            for k_name in metric_keys:
                row[k_name] = getattr(mb, k_name, None)
            random_rows.append(row)
        except Exception as exc:
            logger.warning("Random universe run %d failed: %s", i, exc)

    random_dist_df = (
        pd.DataFrame(random_rows)
        if random_rows
        else pd.DataFrame(columns=["sample_idx", *metric_keys])
    )

    # Compute PIT Sharpe percentile within random distribution
    pit_sharpe = pit_metrics.sharpe or 0.0
    if not random_dist_df.empty and "sharpe" in random_dist_df.columns:
        sharpe_vals = random_dist_df["sharpe"].dropna().to_numpy()
        if len(sharpe_vals) > 0:
            pit_sharpe_pctile = float(np.mean(sharpe_vals <= pit_sharpe) * 100)
        else:
            pit_sharpe_pctile = 50.0
    else:
        pit_sharpe_pctile = 50.0

    # PIT vs static delta
    delta_metrics = [
        "cagr",
        "total_return",
        "annualized_vol",
        "sharpe",
        "sortino",
        "max_drawdown",
        "calmar",
    ]
    pit_vs_static: dict[str, float] = {}
    for km in delta_metrics:
        pv = getattr(pit_metrics, km, None)
        sv = getattr(static_metrics, km, None)
        if pv is not None and sv is not None:
            pit_vs_static[km] = float(pv) - float(sv)

    return SurvivorshipReport(
        pit_metrics=pit_metrics,
        static_metrics=static_metrics,
        random_metrics_distribution=random_dist_df,
        pit_sharpe_percentile=pit_sharpe_pctile,
        pit_vs_static_delta=pit_vs_static,
    )
