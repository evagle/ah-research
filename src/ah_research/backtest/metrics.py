"""Metrics bundle — return primitives, activity metrics, Newey-West alpha/beta, and MetricsBundle.

Tasks 15-18 of Phase 2.  All annualization uses 252 trading days per spec §6.
Log returns convention: r_t = log(nav_t / nav_{t-1}).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

# ── Return-based primitives (Task 15) ────────────────────────────────────────

_TRADING_DAYS_PER_YEAR: int = 252


def cagr(equity: pd.Series) -> float:
    """Compound annual growth rate from an equity (NAV) series.

    Uses calendar days / 365.25 for the period length so it works even when the
    index is not uniformly spaced.  Returns 0.0 for a single-point series.
    """
    if len(equity) < 2:
        return 0.0
    start_val = float(equity.iloc[0])
    end_val = float(equity.iloc[-1])
    if start_val <= 0:
        return 0.0
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return float((end_val / start_val) ** (1.0 / years) - 1.0)


def annualized_vol(returns: pd.Series, periods: int = _TRADING_DAYS_PER_YEAR) -> float:
    """Annualized volatility of a daily return series (std * sqrt(periods))."""
    std = float(returns.std(ddof=1))
    return std * math.sqrt(periods)


def sharpe(returns: pd.Series, rf: float = 0.0, periods: int = _TRADING_DAYS_PER_YEAR) -> float:
    """Annualized Sharpe ratio.

    rf is annualized; it is converted to per-period before computing excess returns.
    Returns 0.0 when the excess-return std is zero (flat equity / constant returns).
    """
    excess = returns - rf / periods
    std = float(excess.std(ddof=1))
    if std < 1e-12:
        return 0.0
    return float(excess.mean() / std * math.sqrt(periods))


def sortino(returns: pd.Series, rf: float = 0.0, periods: int = _TRADING_DAYS_PER_YEAR) -> float:
    """Annualized Sortino ratio (downside deviation in denominator).

    Returns 0.0 when there are no negative excess returns.
    """
    excess = returns - rf / periods
    downside = excess[excess < 0]
    downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    if downside_std == 0:
        return 0.0
    return float(excess.mean() / downside_std * math.sqrt(periods))


def max_drawdown(equity: pd.Series) -> tuple[float, int]:
    """Maximum drawdown of an equity series.

    Returns
    -------
    (max_dd, duration_days) where
        max_dd        : float ≤ 0, peak-to-trough fractional drawdown.
        duration_days : int, calendar days from peak to trough (0 when no drawdown).
    """
    peak = equity.cummax()
    dd_series = (equity - peak) / peak
    min_dd = float(dd_series.min())

    if min_dd >= 0.0:
        return 0.0, 0

    trough_ts = pd.Timestamp(dd_series.idxmin())
    # Find the peak that precedes the trough by masking the equity series
    pre_trough = equity[equity.index <= trough_ts]
    peak_ts = pd.Timestamp(pre_trough.idxmax())
    duration = int((trough_ts - peak_ts).days)
    return min_dd, duration


def calmar(equity: pd.Series) -> float:
    """Calmar ratio = CAGR / |max drawdown|.

    Returns float('inf') when max drawdown is 0 (monotonically rising or flat equity).
    """
    mdd, _ = max_drawdown(equity)
    if mdd == 0.0:
        return float("inf")
    return float(cagr(equity) / abs(mdd))


# ── Activity metrics (Task 16) ────────────────────────────────────────────────


def annualized_turnover(
    trades: pd.DataFrame,
    avg_nav: float,
    start: date,
    end: date,
) -> float:
    """Annualized portfolio turnover.

    Turnover = total two-sided notional traded / avg NAV, then scaled to annual.
    The trades DataFrame must have a column named ``notional`` (float).
    Returns 0.0 when avg_nav is zero or no trades.
    """
    if avg_nav <= 0 or trades.empty or "notional" not in trades.columns:
        return 0.0
    total_notional = float(trades["notional"].sum())
    period_days = int((pd.Timestamp(end) - pd.Timestamp(start)).days)
    period_years = period_days / 365.25
    if period_years <= 0:
        return 0.0
    return total_notional / avg_nav / period_years


def avg_positions(positions_history: pd.DataFrame) -> float:
    """Average number of open positions across the backtest.

    positions_history must have columns ``date`` and ``symbol`` (long format,
    one row per date/symbol pair in the engine's positions_history DataFrame).
    Returns 0.0 for an empty history.
    """
    if positions_history.empty or "date" not in positions_history.columns:
        return 0.0
    return float(positions_history.groupby("date")["symbol"].count().mean())


def avg_holding_period(
    positions_history: pd.DataFrame,
    trades: pd.DataFrame,
) -> float:
    """Average holding period in calendar days across all completed round-trips.

    Uses the first buy and the last sell/cover for each symbol as a proxy for
    the holding period.  Returns 0.0 when no completed round-trips exist.
    """
    if trades.empty or "exec_date" not in trades.columns:
        return 0.0

    # Normalize exec_date to datetime
    trades = trades.copy()
    trades["exec_date"] = pd.to_datetime(trades["exec_date"])

    durations: list[float] = []
    for _symbol, grp in trades.groupby("symbol"):
        buys = grp[grp["side"].isin(["buy", "cover"])].sort_values("exec_date")
        sells = grp[grp["side"].isin(["sell", "short"])].sort_values("exec_date")
        if buys.empty or sells.empty:
            continue
        first_buy = buys["exec_date"].iloc[0]
        last_sell = sells["exec_date"].iloc[-1]
        holding = (last_sell - first_buy).days
        if holding >= 0:
            durations.append(float(holding))

    return float(np.mean(durations)) if durations else 0.0


def avg_dividend_yield(
    positions_history: pd.DataFrame,
    trades: pd.DataFrame,
    equity: pd.Series | None = None,
) -> float:
    """Annualized average dividend yield (long leg only).

    Approximated as: total dividend income / total long position-days value.
    Dividend income is inferred from corporate-action buy trades whose ``side``
    is ``'buy'`` and the trade is a result of reinvestment (shares sentinel=-1
    resolved at execution time — tracked via cost_total==0 heuristic, or
    by flagging in the trade log).

    In Phase 2 the engine does not tag dividend-reinvestment trades distinctly
    so this metric defaults to 0.0 unless a ``dividend_income`` column is
    present in trades.  A future task can add explicit tagging.
    """
    if "dividend_income" not in trades.columns:
        return 0.0
    total_div = float(trades["dividend_income"].sum())
    if equity is None or equity.empty:
        return 0.0
    avg_nav_val = float(equity.mean())
    if avg_nav_val <= 0:
        return 0.0
    # Scale to annual using 252 days / length
    n_days = len(equity)
    years = n_days / _TRADING_DAYS_PER_YEAR
    if years <= 0:
        return 0.0
    return total_div / avg_nav_val / years


# ── Benchmark-relative + Newey-West (Task 17) ────────────────────────────────


@dataclass(frozen=True)
class AlphaBetaNW:
    """OLS alpha/beta with Newey-West HAC standard errors."""

    alpha: float
    beta: float
    alpha_t_stat: float
    alpha_pvalue: float
    alpha_se: float
    beta_t_stat: float
    beta_se: float
    newey_west_lag: int


def _andrews_lag(n: int) -> int:
    """HAC lag per Andrews (1991): max(1, floor(4 * (n/100)^(2/9)))."""
    return max(1, int(4 * (n / 100) ** (2 / 9)))


def alpha_beta_newey_west(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> AlphaBetaNW:
    """Compute Jensen's alpha and beta via OLS with Newey-West HAC SE.

    Uses ``statsmodels.api.OLS`` with ``cov_type='HAC'`` and the Andrews (1991)
    automatic lag selection rule.

    Parameters
    ----------
    portfolio_returns:
        Daily log returns of the portfolio.
    benchmark_returns:
        Daily log returns of the benchmark, aligned to portfolio_returns.

    Returns
    -------
    AlphaBetaNW dataclass with OLS params and Newey-West t-stats.
    """
    rp, rb = portfolio_returns.align(benchmark_returns, join="inner")
    rp_arr = rp.to_numpy()
    rb_arr = rb.to_numpy()
    n = len(rp_arr)

    x_mat = sm.add_constant(rb_arr)
    lag = _andrews_lag(n)
    fit = sm.OLS(rp_arr, x_mat).fit(cov_type="HAC", cov_kwds={"maxlags": lag})

    return AlphaBetaNW(
        alpha=float(fit.params[0]),
        beta=float(fit.params[1]),
        alpha_t_stat=float(fit.tvalues[0]),
        alpha_pvalue=float(fit.pvalues[0]),
        alpha_se=float(fit.bse[0]),
        beta_t_stat=float(fit.tvalues[1]),
        beta_se=float(fit.bse[1]),
        newey_west_lag=lag,
    )


def excess_return(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> float:
    """Annualized excess return: mean(rp - rb) * 252."""
    rp, rb = portfolio_returns.align(benchmark_returns, join="inner")
    return float((rp - rb).mean() * _TRADING_DAYS_PER_YEAR)


def tracking_error(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    periods: int = _TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized tracking error: std(rp - rb) * sqrt(252)."""
    rp, rb = portfolio_returns.align(benchmark_returns, join="inner")
    diff = rp - rb
    return float(diff.std(ddof=1) * math.sqrt(periods))


def information_ratio(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    periods: int = _TRADING_DAYS_PER_YEAR,
) -> float:
    """Information ratio = excess_return / tracking_error.

    Returns 0.0 when tracking error is zero.
    """
    te = tracking_error(portfolio_returns, benchmark_returns, periods)
    if te == 0.0:
        return 0.0
    er = excess_return(portfolio_returns, benchmark_returns)
    return float(er / te)


# ── MetricsBundle + compute_metrics (Task 18) ────────────────────────────────


@dataclass(frozen=True)
class MetricsBundle:
    """All performance metrics for a completed backtest run.

    Fields follow the spec §6 taxonomy:
      - Returns: cagr, total_return, annualized_vol
      - Risk-adjusted: sharpe, sortino, max_drawdown, max_dd_duration_days, calmar
      - Income: avg_dividend_yield
      - Activity: annualized_turnover, avg_positions, avg_holding_period_days
      - Benchmark-relative: excess_return, information_ratio, tracking_error, alpha, beta
      - Inferential: alpha_t_stat, alpha_pvalue, alpha_se, beta_t_stat, beta_se, newey_west_lag
    """

    # Returns
    cagr: float | None = None
    total_return: float | None = None
    annualized_vol: float | None = None

    # Risk-adjusted
    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown: float | None = None
    max_dd_duration_days: int | None = None
    calmar: float | None = None

    # Income
    avg_dividend_yield: float | None = None

    # Activity
    annualized_turnover: float | None = None
    avg_positions: float | None = None
    avg_holding_period_days: float | None = None

    # Benchmark-relative
    excess_return: float | None = None
    information_ratio: float | None = None
    tracking_error: float | None = None
    alpha: float | None = None
    beta: float | None = None

    # Inferential
    alpha_t_stat: float | None = None
    alpha_pvalue: float | None = None
    alpha_se: float | None = None
    beta_t_stat: float | None = None
    beta_se: float | None = None
    newey_west_lag: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return all fields as a plain dictionary."""
        return asdict(self)

    def __str__(self) -> str:
        lines = ["MetricsBundle("]
        sections: list[tuple[str, list[str]]] = [
            (
                "Returns",
                ["cagr", "total_return", "annualized_vol"],
            ),
            (
                "Risk-adjusted",
                ["sharpe", "sortino", "max_drawdown", "max_dd_duration_days", "calmar"],
            ),
            (
                "Income",
                ["avg_dividend_yield"],
            ),
            (
                "Activity",
                ["annualized_turnover", "avg_positions", "avg_holding_period_days"],
            ),
            (
                "Benchmark-relative",
                ["excess_return", "information_ratio", "tracking_error", "alpha", "beta"],
            ),
            (
                "Inferential",
                [
                    "alpha_t_stat",
                    "alpha_pvalue",
                    "alpha_se",
                    "beta_t_stat",
                    "beta_se",
                    "newey_west_lag",
                ],
            ),
        ]
        d = self.to_dict()
        for section, keys in sections:
            lines.append(f"  [{section}]")
            for k in keys:
                v = d.get(k)
                if isinstance(v, float):
                    lines.append(f"    {k:30s} = {v:.6g}")
                else:
                    lines.append(f"    {k:30s} = {v}")
        lines.append(")")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.__str__()


def compute_metrics(
    equity: pd.Series,
    benchmark: pd.Series,
    trades: pd.DataFrame,
    positions_history: pd.DataFrame,
    start: date | None = None,
    end: date | None = None,
) -> MetricsBundle:
    """Compute all metrics and return a populated MetricsBundle.

    Parameters
    ----------
    equity:
        Daily NAV series (portfolio equity curve).
    benchmark:
        Daily benchmark NAV series, aligned or alignable with equity.
    trades:
        DataFrame of executed trades from BacktestResult.trades.
    positions_history:
        DataFrame of positions history from BacktestResult.positions_history.
    start:
        Backtest start date (used for turnover annualization).
    end:
        Backtest end date (used for turnover annualization).
    """
    # Derive log returns (keep as pd.Series for downstream functions)
    log_returns = pd.Series(np.log(equity / equity.shift(1))).dropna()
    bench_log = pd.Series(np.log(benchmark / benchmark.shift(1))).dropna()

    # Returns section
    total_ret = float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) >= 2 else 0.0
    _cagr = cagr(equity)
    _vol = annualized_vol(log_returns)

    # Risk-adjusted section
    _sharpe = sharpe(log_returns)
    _sortino = sortino(log_returns)
    _mdd, _mdd_dur = max_drawdown(equity)
    _calmar = calmar(equity)

    # Income section
    _div_yield = avg_dividend_yield(positions_history, trades, equity)

    # Activity section
    _avg_nav = float(equity.mean())
    _start = (
        start
        if start is not None
        else (equity.index[0].date() if len(equity) > 0 else date.today())
    )
    _end = (
        end if end is not None else (equity.index[-1].date() if len(equity) > 0 else date.today())
    )
    _turnover = annualized_turnover(trades, _avg_nav, _start, _end)
    _avg_pos = avg_positions(positions_history)
    _avg_hold = avg_holding_period(positions_history, trades)

    # Benchmark-relative section
    _exc_ret: float | None = None
    _ir: float | None = None
    _te: float | None = None
    _alpha: float | None = None
    _beta: float | None = None
    _alpha_t: float | None = None
    _alpha_p: float | None = None
    _alpha_se: float | None = None
    _beta_t: float | None = None
    _beta_se: float | None = None
    _nw_lag: int | None = None

    if len(bench_log) >= 10 and len(log_returns) >= 10:
        try:
            _exc_ret = excess_return(log_returns, bench_log)
            _ir = information_ratio(log_returns, bench_log)
            _te = tracking_error(log_returns, bench_log)
            nw = alpha_beta_newey_west(log_returns, bench_log)
            _alpha = nw.alpha
            _beta = nw.beta
            _alpha_t = nw.alpha_t_stat
            _alpha_p = nw.alpha_pvalue
            _alpha_se = nw.alpha_se
            _beta_t = nw.beta_t_stat
            _beta_se = nw.beta_se
            _nw_lag = nw.newey_west_lag
        except Exception:
            pass

    return MetricsBundle(
        cagr=_cagr,
        total_return=total_ret,
        annualized_vol=_vol,
        sharpe=_sharpe,
        sortino=_sortino,
        max_drawdown=_mdd,
        max_dd_duration_days=_mdd_dur,
        calmar=_calmar,
        avg_dividend_yield=_div_yield,
        annualized_turnover=_turnover,
        avg_positions=_avg_pos,
        avg_holding_period_days=_avg_hold,
        excess_return=_exc_ret,
        information_ratio=_ir,
        tracking_error=_te,
        alpha=_alpha,
        beta=_beta,
        alpha_t_stat=_alpha_t,
        alpha_pvalue=_alpha_p,
        alpha_se=_alpha_se,
        beta_t_stat=_beta_t,
        beta_se=_beta_se,
        newey_west_lag=_nw_lag,
    )
