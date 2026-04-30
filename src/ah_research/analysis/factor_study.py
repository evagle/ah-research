"""Factor study: IC, quantile returns, block bootstrap."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ah_research.backtest.types import Signals, Weights
from ah_research.data.repository import DataRepository
from ah_research.strategies.base import SignalStrategy

if TYPE_CHECKING:
    pass


# ── Task 6: IC primitive + _InlineSignalStrategy ──────────────────────────────


@dataclass
class _InlineSignalStrategy:
    """Wraps a DataFrame[date, symbol, signal] as a trivial SignalStrategy."""

    frame: pd.DataFrame
    name: str = field(default="inline")

    def generate(self, repo: DataRepository, start: date, end: date) -> Signals:
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        df = self.frame.copy()
        df["date"] = pd.to_datetime(df["date"])
        mask = (df["date"] >= start_ts) & (df["date"] <= end_ts)
        return Signals.from_dataframe(df[mask].reset_index(drop=True))

    def to_weights(self, signals: Signals, repo: DataRepository) -> Weights:
        df = signals.df.copy()
        n = len(df)
        df["weight"] = 1.0 / n if n > 0 else 0.0
        df = df.drop(columns=["signal"])
        return Weights.from_dataframe(df)


def _compute_ic_one_date(signals: pd.Series, forward_returns: pd.Series) -> float:
    """Spearman rank correlation for one rebalance date."""
    paired = pd.concat([signals, forward_returns], axis=1).dropna()
    if len(paired) < 2:
        return float("nan")
    ic, _ = spearmanr(paired.iloc[:, 0].values, paired.iloc[:, 1].values)
    return float(ic)


# ── Task 7: Quantile returns + IC per horizon ─────────────────────────────────


def _assign_quantiles(signals: pd.Series, n_quantiles: int = 5) -> pd.Series:
    """Return integer quantile label in {1..n_quantiles} per row."""
    try:
        result = pd.qcut(signals.rank(method="first"), q=n_quantiles, labels=False)
        return (result + 1).astype(float)
    except ValueError:
        return pd.Series(np.nan, index=signals.index)


def _compute_quantile_returns(
    enriched: pd.DataFrame,
    n_quantiles: int,
    horizon: int,
) -> pd.DataFrame:
    """Compute equal-weighted quantile returns per rebalance date."""
    fwd_col = f"forward_return_{horizon}"
    rows: list[dict[str, object]] = []
    for d, group in enriched.groupby("date"):
        if len(group) < n_quantiles:
            continue
        group = group.copy()
        group["quantile"] = _assign_quantiles(group["signal"], n_quantiles)
        per_q = group.groupby("quantile")[fwd_col].mean()
        row: dict[str, object] = {
            f"Q{int(q)}": float(per_q.get(q, float("nan"))) for q in range(1, n_quantiles + 1)
        }
        row["date"] = d
        q_top_raw = row.get(f"Q{n_quantiles}", 0.0)
        q_bot_raw = row.get("Q1", 0.0)
        q_top_f = float(q_top_raw) if isinstance(q_top_raw, (int, float)) else 0.0
        q_bot_f = float(q_bot_raw) if isinstance(q_bot_raw, (int, float)) else 0.0
        row["long_short"] = q_top_f - q_bot_f
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("date")


def _ic_table_by_horizon(enriched: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Rows=rebalance dates; columns=horizons; values=Spearman IC."""
    results: list[dict[str, object]] = []
    for d, group in enriched.groupby("date"):
        row: dict[str, object] = {"date": d}
        for h in horizons:
            fwd_col = f"forward_return_{h}"
            if fwd_col in group.columns:
                row[str(h)] = _compute_ic_one_date(group["signal"], group[fwd_col])
            else:
                row[str(h)] = float("nan")
        results.append(row)
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results).set_index("date")


# ── Task 8: Block bootstrap + sector neutralization ───────────────────────────


def _block_bootstrap(
    series: pd.Series[float],
    n_resamples: int,
    block_size: int,
    random_seed: int = 42,
) -> dict[str, float]:
    """Block bootstrap mean + 95% CI + one-sided p-value (H0: mean=0)."""
    arr = series.dropna().to_numpy()
    n = len(arr)
    if n < block_size:
        return {
            "mean": float(arr.mean()) if n > 0 else float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "p_value": float("nan"),
        }

    rng = np.random.default_rng(random_seed)
    means = np.empty(n_resamples)
    n_blocks = (n + block_size - 1) // block_size
    for i in range(n_resamples):
        starts = rng.integers(0, n - block_size + 1, size=n_blocks)
        pieces = [arr[s : s + block_size] for s in starts]
        resample = np.concatenate(pieces)[:n]
        means[i] = resample.mean()

    mean_val = float(means.mean())
    p_value = float((means <= 0).mean()) if mean_val > 0 else float((means >= 0).mean())
    return {
        "mean": mean_val,
        "ci_low": float(np.percentile(means, 2.5)),
        "ci_high": float(np.percentile(means, 97.5)),
        "p_value": p_value,
    }


def _sector_neutralize_signals(signals: pd.Series, sectors: pd.Series) -> pd.Series:
    """Demean signal within each sector group."""
    aligned_sectors = sectors.reindex(signals.index)
    group_means = signals.groupby(aligned_sectors).transform("mean")
    return signals - group_means


# ── Task 9: Full factor_study() + FactorReport ────────────────────────────────


@dataclass(frozen=True)
class FactorReport:
    """Results of a cross-sectional factor study."""

    ic_by_horizon: pd.DataFrame
    ic_summary: pd.DataFrame
    ic_decay: pd.Series
    quantile_returns: pd.DataFrame
    quantile_summary: pd.DataFrame
    bootstrap_q5_minus_q1: dict[str, float]
    sector_neutralized: bool
    n_rebalance_dates: int
    universe_summary: dict[str, int]


def _compute_forward_returns(prices: pd.DataFrame, horizon: int) -> pd.Series:
    """Return Series indexed by symbol giving horizon-day forward log return from first date."""
    if prices.empty:
        return pd.Series(dtype=float)
    wide = prices.pivot_table(index="date", columns="symbol", values="close_hfq")
    if len(wide) <= horizon:
        return pd.Series(dtype=float)
    start_prices = wide.iloc[0]
    end_prices = wide.iloc[horizon]
    valid = (start_prices > 0) & (end_prices > 0)
    return pd.Series(
        np.log(end_prices[valid] / start_prices[valid]),
        index=end_prices[valid].index,
        dtype=float,
    )


def factor_study(
    strategy: SignalStrategy | pd.DataFrame,
    repo: DataRepository,
    start: date,
    end: date,
    n_quantiles: int = 5,
    ic_horizons: list[int] | None = None,
    sector_neutral: bool = True,
    bootstrap_n_resamples: int = 1000,
    bootstrap_block_size: int = 21,
    benchmark: str | pd.Series = "auto",
    rebalance: Literal["W", "M", "Q"] = "M",
    random_seed: int = 42,
) -> FactorReport:
    """Run a cross-sectional factor study and return a FactorReport.

    Parameters
    ----------
    strategy:
        A SignalStrategy or a DataFrame with columns [date, symbol, signal].
    repo:
        DataRepository (or SyntheticMarket) providing market data.
    start, end:
        Study window (inclusive).
    n_quantiles:
        Number of quantile buckets for the long-short spread.
    ic_horizons:
        Forward-return horizons in trading days. Default: [1, 5, 10, 20, 60].
    sector_neutral:
        If True, demean signals within sector before IC/quantile analysis.
    bootstrap_n_resamples:
        Number of block-bootstrap resamples for the long-short CI.
    bootstrap_block_size:
        Block length (trading days) for the block bootstrap.
    benchmark:
        Ignored in current implementation (reserved for future use).
    rebalance:
        Period frequency: "W" (weekly), "M" (monthly), "Q" (quarterly).
    random_seed:
        RNG seed for block bootstrap reproducibility.
    """
    if ic_horizons is None:
        ic_horizons = [1, 5, 10, 20, 60]

    # 1. Adapt input
    strat: SignalStrategy = (
        _InlineSignalStrategy(strategy) if isinstance(strategy, pd.DataFrame) else strategy
    )

    # 2. Rebalance dates (last trading day of each period)
    calendar = repo.get_trading_calendar("SH", start, end)
    trading_days = pd.to_datetime(calendar[calendar["is_trading_day"]]["date"])
    period_ends = trading_days.groupby(trading_days.dt.to_period(rebalance)).max().values
    rebalance_dates = [pd.Timestamp(d).date() for d in period_ends]

    if len(rebalance_dates) < 3:
        raise ValueError(
            f"factor_study needs >= 3 rebalance dates; got {len(rebalance_dates)} "
            f"for rebalance={rebalance} from {start} to {end}"
        )

    # 3. Per-rebalance signal + sector + forward returns
    max_horizon = max(ic_horizons)
    all_rows: list[pd.DataFrame] = []
    universe_sizes: list[int] = []

    for d in rebalance_dates:
        signals_obj = strat.generate(repo, d, d)
        if signals_obj.df.empty:
            continue
        sig_df = signals_obj.df.copy()
        sig_df["date"] = pd.to_datetime(d)

        if sector_neutral:
            sectors_df = repo.get_sector(sig_df["symbol"].tolist())
            sector_map = sectors_df.set_index("symbol")["sector_l1"]
            sig_indexed = sig_df.set_index("symbol")["signal"]
            neutralized = _sector_neutralize_signals(sig_indexed, sector_map)
            sig_df = sig_df.copy()
            sig_df["signal"] = neutralized.values

        # Fetch forward prices for all horizons
        fwd_end = (pd.Timestamp(d) + pd.Timedelta(days=max_horizon + 45)).date()
        prices = repo.get_prices(sig_df["symbol"].tolist(), start=d, end=fwd_end)

        for h in ic_horizons:
            fwd = _compute_forward_returns(prices, h)
            col = f"forward_return_{h}"
            fwd_aligned = fwd.reindex(sig_df["symbol"].values)
            sig_df = sig_df.copy()
            sig_df[col] = fwd_aligned.values

        all_rows.append(sig_df)
        universe_sizes.append(len(sig_df))

    if not all_rows:
        raise ValueError("No signal data produced for any rebalance date.")

    enriched = pd.concat(all_rows, ignore_index=True)

    # 4. IC table
    ic_by_horizon = _ic_table_by_horizon(enriched, ic_horizons)

    # 5. IC summary (mean + NW t-stat + IR)
    import statsmodels.api as sm

    from ah_research.backtest.metrics import _andrews_lag

    ic_summary_rows: list[dict[str, object]] = []
    for h in ic_horizons:
        col = str(h)
        if ic_by_horizon.empty or col not in ic_by_horizon.columns:
            ic_summary_rows.append(
                {
                    "horizon": h,
                    "mean_ic": float("nan"),
                    "nw_t_stat": float("nan"),
                    "nw_p_value": float("nan"),
                    "ir": float("nan"),
                }
            )
            continue
        ic_series = ic_by_horizon[col].dropna()
        if len(ic_series) < 2:
            ic_summary_rows.append(
                {
                    "horizon": h,
                    "mean_ic": float("nan"),
                    "nw_t_stat": float("nan"),
                    "nw_p_value": float("nan"),
                    "ir": float("nan"),
                }
            )
            continue
        n = len(ic_series)
        lag = _andrews_lag(n)
        x_mat = np.ones((n, 1))
        fit = sm.OLS(ic_series.values, x_mat).fit(cov_type="HAC", cov_kwds={"maxlags": lag})
        std_val = float(ic_series.std())
        ic_summary_rows.append(
            {
                "horizon": h,
                "mean_ic": float(ic_series.mean()),
                "nw_t_stat": float(fit.tvalues[0]),
                "nw_p_value": float(fit.pvalues[0]),
                "ir": float(ic_series.mean() / std_val) if std_val > 0 else 0.0,
            }
        )
    ic_summary = pd.DataFrame(ic_summary_rows).set_index("horizon")

    # 6. IC decay
    ic_decay = ic_summary["mean_ic"]

    # 7. Quantile returns (use longest horizon for quantile calc)
    primary_horizon = max(ic_horizons)
    quantile_returns = _compute_quantile_returns(enriched, n_quantiles, primary_horizon)

    # 8. Quantile summary (CAGR, Sharpe, max DD per quantile)
    from ah_research.backtest.metrics import cagr, max_drawdown, sharpe

    quantile_summary_rows: list[dict[str, object]] = []
    if not quantile_returns.empty:
        for col in quantile_returns.columns:
            returns_s = quantile_returns[col].dropna()
            if returns_s.empty:
                continue
            equity = (1 + returns_s).cumprod() * 100
            # equity needs a DatetimeIndex for cagr()
            equity.index = pd.to_datetime(equity.index)
            mdd, _ = max_drawdown(equity)
            quantile_summary_rows.append(
                {
                    "quantile": col,
                    "cagr": cagr(equity),
                    "sharpe": sharpe(returns_s),
                    "max_drawdown": mdd,
                }
            )
    quantile_summary = (
        pd.DataFrame(quantile_summary_rows).set_index("quantile")
        if quantile_summary_rows
        else pd.DataFrame()
    )

    # 9. Block bootstrap on long_short
    if not quantile_returns.empty and "long_short" in quantile_returns.columns:
        bootstrap = _block_bootstrap(
            quantile_returns["long_short"].dropna(),
            n_resamples=bootstrap_n_resamples,
            block_size=bootstrap_block_size,
            random_seed=random_seed,
        )
    else:
        bootstrap = {
            "mean": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "p_value": float("nan"),
        }

    return FactorReport(
        ic_by_horizon=ic_by_horizon,
        ic_summary=ic_summary,
        ic_decay=ic_decay,
        quantile_returns=quantile_returns,
        quantile_summary=quantile_summary,
        bootstrap_q5_minus_q1=bootstrap,
        sector_neutralized=sector_neutral,
        n_rebalance_dates=len(rebalance_dates),
        universe_summary={
            "avg_n_names": int(np.mean(universe_sizes)) if universe_sizes else 0,
            "min_n_names": int(np.min(universe_sizes)) if universe_sizes else 0,
        },
    )
