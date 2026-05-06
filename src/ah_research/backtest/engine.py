"""Daily-loop backtest engine for A-share and HK markets.

Implements ``run_backtest(strategy, repo, config) -> BacktestResult``.

The engine follows the spec §5 pseudocode exactly:
  1. Corporate actions applied at open (before order execution).
  2. Pending orders executed at the configured fill price.
  3. On rebalance dates, new target orders are queued for next trading day.
  4. End-of-day MTM: equity = cash_in_base + sum(position.mtm_base).

Task 9:  Skeleton — buy next open, MTM, no T+N lock, no limits, single-ccy.
Task 10: T+N lock per exchange (SH/SZ T+1, HK T+2).
Task 11: Limit-up/down + suspension rejection with retry.
Task 12: Dividend reinvestment + splits.
Task 13: Multi-currency cash + HK lot size.
Task 14: Short orders — blocked on A-shares by default.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any, Literal

import pandas as pd

from ah_research.backtest.cash_ledger import (
    CashLedger,
)
from ah_research.backtest.cash_ledger import (
    cash_in_base as _cash_in_base,
)
from ah_research.backtest.cash_ledger import (
    fx_to_base as _fx_to_base,
)
from ah_research.backtest.costs import DEFAULT_COSTS_2024, CostModelBundle
from ah_research.backtest.metrics import compute_metrics
from ah_research.backtest.order_executor import (
    OrderExecutor,
    OrderRejection,
    PricedFill,
)
from ah_research.backtest.types import (
    BacktestConfig,
    BacktestResult,
    Order,
    Position,
    Weights,
    hash_config,
)
from ah_research.constants import LEVERAGE_SUM_TOLERANCE
from ah_research.exceptions import DataIntegrityError, SourceError, UserInputError
from ah_research.meta import code_version
from ah_research.model.types import Currency, Exchange, Symbol, parse_symbol
from ah_research.strategies.base import resolve_weights

logger = logging.getLogger(__name__)

# Lot sizes (shares per board lot)
_LOT_SIZE: dict[Exchange, int] = {
    Exchange.SH: 100,
    Exchange.SZ: 100,
    Exchange.HK: 100,  # Phase 2 simplification; warning logged at start
}

# T+N settlement days per exchange under "auto"
_SETTLEMENT_DAYS: dict[Exchange, int] = {
    Exchange.SH: 1,
    Exchange.SZ: 1,
    Exchange.HK: 2,
}

# Symbols warned about HK borrow cost (per-run set)
_hk_borrow_warned: set[str] = set()


def _get_code_version() -> str:
    """Return the short git SHA of the current HEAD, or 'unknown'."""
    return code_version()


_BENCHMARK_SYMBOL: dict[str, str] = {
    "CSI300_TR": "000300.SH",
    "HSI_TR": "HSI.HK",
}

# Maximum number of consecutive NaN days we forward-fill silently.
_BENCHMARK_FFILL_LIMIT = 3


def resolve_benchmark(
    spec: str | pd.Series,
    start: date,
    end: date,
    repo: Any,
    trading_days: list[date] | None = None,
) -> pd.Series:
    """Resolve a BenchmarkSpec to a daily pd.Series aligned on trading_days.

    Parameters
    ----------
    spec:
        One of: ``"CSI300_TR"``, ``"HSI_TR"``, ``"zero"``, or a ``pd.Series``
        of cumulative-return values.
    start, end:
        Date range used when fetching prices from ``repo``.
    repo:
        A DataRepository-compatible object; used for named benchmark specs.
    trading_days:
        Optional list of trading dates for the final index. When omitted the
        index of a supplied Series is used as-is (or constructed from SH
        calendar for named specs).

    Returns
    -------
    pd.Series indexed by ``pd.DatetimeIndex`` aligned to ``trading_days``.

    Raises
    ------
    ValueError
        For unrecognised string specs.
    """
    if trading_days is not None:
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d in trading_days])
    else:
        idx = None

    # ── constant 1.0 series ───────────────────────────────────────────────
    if isinstance(spec, str) and spec == "zero":
        if idx is None:
            raise ValueError("trading_days must be provided when spec='zero'")
        return pd.Series(1.0, index=idx)

    # ── explicit Series passthrough ────────────────────────────────────────
    if isinstance(spec, pd.Series):
        series: pd.Series = spec.copy() if idx is None else spec.reindex(idx)
        # Detect gaps larger than the limit before filling
        nan_runs = _max_consecutive_nans(series)
        if nan_runs > _BENCHMARK_FFILL_LIMIT:
            import warnings

            warnings.warn(
                f"Benchmark Series has a gap of {nan_runs} consecutive NaN days "
                f"(limit = {_BENCHMARK_FFILL_LIMIT}); forward-filling with limit={_BENCHMARK_FFILL_LIMIT}. "
                "Values beyond the fill limit remain NaN and are back-filled from the next valid bar.",
                UserWarning,
                stacklevel=2,
            )
        # Forward-fill up to the limit; then back-fill remaining NaN
        filled = series.ffill(limit=_BENCHMARK_FFILL_LIMIT).bfill()
        return filled

    # ── named benchmarks via repo prices ─────────────────────────────────
    if isinstance(spec, str) and spec in _BENCHMARK_SYMBOL:
        sym = _BENCHMARK_SYMBOL[spec]
        try:
            prices_df = repo.get_prices([sym], start, end)
        except (SourceError, DataIntegrityError) as exc:
            logger.warning(
                "Failed to fetch benchmark %r (%s) from repo: %s. Falling back to constant 1.0.",
                spec,
                sym,
                exc,
            )
            if idx is None:
                raise
            return pd.Series(1.0, index=idx)

        if prices_df.empty:
            logger.warning(
                "Benchmark %r (%s) returned no price data; falling back to constant 1.0.",
                spec,
                sym,
            )
            if idx is None:
                raise ValueError(f"Benchmark {spec!r} returned no price data.")
            return pd.Series(1.0, index=idx)

        # Use total_return if available; fall back to close_hfq with a warning
        if "total_return" in prices_df.columns:
            col = "total_return"
        else:
            logger.warning(
                "Benchmark %r: 'total_return' column not found in price data; "
                "using 'close_hfq' as approximation.",
                spec,
            )
            col = "close_hfq"

        prices_df = prices_df.copy()
        prices_df["_ts"] = prices_df["date"].apply(pd.Timestamp)
        raw: pd.Series = prices_df.set_index("_ts")[col].sort_index()

        # Normalize to start at 1.0
        first_val = float(raw.iloc[0]) if len(raw) > 0 else 0.0
        if first_val != 0.0:
            raw = raw.div(first_val)

        if idx is not None:
            aligned: pd.Series = raw.reindex(idx)
            nan_runs = _max_consecutive_nans(aligned)
            if nan_runs > _BENCHMARK_FFILL_LIMIT:
                import warnings

                warnings.warn(
                    f"Benchmark {spec!r} has a gap of {nan_runs} consecutive NaN days "
                    f"(limit = {_BENCHMARK_FFILL_LIMIT}) after reindexing; forward-filling.",
                    UserWarning,
                    stacklevel=2,
                )
            raw = aligned.ffill(limit=_BENCHMARK_FFILL_LIMIT).bfill().fillna(1.0)
        return raw

    # ── unknown spec ─────────────────────────────────────────────────────
    if isinstance(spec, str):
        raise ValueError(
            f"Unknown benchmark spec {spec!r}. "
            f"Supported string values: 'CSI300_TR', 'HSI_TR', 'zero'. "
            "Pass a pd.Series for a custom benchmark."
        )

    raise ValueError(f"Unsupported benchmark spec type {type(spec).__name__!r}.")


def _max_consecutive_nans(series: pd.Series) -> int:
    """Return the length of the longest run of NaN values in series."""
    if not series.isna().any():
        return 0
    max_run = 0
    current_run = 0
    for val in series:
        if pd.isna(val):
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run


def _resolve_benchmark(
    spec: str | pd.Series,
    trading_days: list[date],
    repo: Any | None = None,
    start: date | None = None,
    end: date | None = None,
) -> pd.Series:
    """Internal shim: delegate to the public resolve_benchmark function.

    Kept for backward-compatibility with the engine loop.
    """
    if repo is not None and start is not None and end is not None:
        return resolve_benchmark(spec, start, end, repo, trading_days=trading_days)

    # Legacy path (no repo): handle 'zero' and Series only
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in trading_days])
    if isinstance(spec, pd.Series):
        series = spec.reindex(idx)
        nan_runs = _max_consecutive_nans(series)
        if nan_runs > _BENCHMARK_FFILL_LIMIT:
            import warnings

            warnings.warn(
                f"Benchmark Series has {nan_runs} consecutive NaN days; forward-filling.",
                UserWarning,
                stacklevel=2,
            )
        return series.ffill(limit=_BENCHMARK_FFILL_LIMIT).bfill().fillna(1.0)
    if spec == "zero":
        return pd.Series(1.0, index=idx)
    logger.warning(
        "Benchmark %r cannot be resolved without repo; returning constant 1.0.",
        spec,
    )
    return pd.Series(1.0, index=idx)


def _trading_days_for_exchange(repo: Any, exchange: Exchange, start: date, end: date) -> list[date]:
    """Return sorted list of trading days for exchange in [start, end]."""
    cal = repo.get_trading_calendar(str(exchange), start, end)
    mask = cal["is_trading_day"]
    dates = cal.loc[mask, "date"]
    return sorted(pd.Timestamp(d).date() for d in dates)


def _merge_calendars(sh_days: list[date], hk_days: list[date]) -> list[date]:
    """Return sorted union of two calendar lists."""
    return sorted(set(sh_days) | set(hk_days))


def _compute_rebalance_dates(all_days: list[date], freq: str) -> list[date]:
    """Return the last trading day of each period (M/Q/W/D) in all_days."""
    if not all_days:
        return []
    ts_index = pd.DatetimeIndex([pd.Timestamp(d) for d in all_days])
    s = pd.Series(ts_index, index=ts_index)

    pandas_freq = {"M": "ME", "Q": "QE", "W": "W-FRI", "D": "D"}.get(freq, "ME")

    rebalance_ts: list[date] = []
    # Group by period and pick the last day
    for _period, group in s.groupby(pd.Grouper(freq=pandas_freq)):
        if len(group) > 0:
            last_day = group.index[-1].date()
            rebalance_ts.append(last_day)
    return rebalance_ts


def _round_to_lot(target_shares: float, lot_size: int, is_buy: bool) -> int:
    """Round shares to the nearest lot. Floor on buys, ceiling on sells."""
    if lot_size <= 0:
        lot_size = 1
    lots = Decimal(str(target_shares)) / Decimal(str(lot_size))
    if is_buy:
        rounded_lots = int(lots.to_integral_value(rounding=ROUND_FLOOR))
    else:
        rounded_lots = int(lots.to_integral_value(rounding=ROUND_CEILING))
    return rounded_lots * lot_size


def _infer_side(
    current_shares: int, target_shares: int
) -> Literal["buy", "sell", "short", "cover"]:
    """Infer order side from current and target shares."""
    if current_shares >= 0 and target_shares > current_shares:
        return "buy"
    if current_shares > 0 and target_shares < current_shares:
        return "sell"
    if current_shares == 0 and target_shares < 0:
        return "short"
    if current_shares < 0 and target_shares > current_shares:
        return "cover"
    if current_shares < 0 and target_shares < current_shares:
        return "short"
    return "sell"


def _apply_corporate_action(
    positions: dict[Symbol, Position],
    cash: dict[Currency, Decimal],
    ca_row: pd.Series,
    dividend_policy: str,
    pending_orders: list[Order],
    d: date,
) -> None:
    """Apply a single corporate action to positions and cash."""
    sym_str = str(ca_row["symbol"])
    kind = str(ca_row["kind"])
    params = json.loads(str(ca_row["params_json"]))

    try:
        symbol = parse_symbol(sym_str)
    except UserInputError:
        logger.warning("Cannot parse symbol %r in corporate action; skipping.", sym_str)
        return

    if symbol not in positions:
        return

    pos = positions[symbol]

    if kind == "cash_dividend":
        amount_per_share = Decimal(str(params.get("amount_per_share", 0)))
        dividend_cash = amount_per_share * pos.shares
        ccy = symbol.currency
        cash[ccy] = cash.get(ccy, Decimal("0")) + dividend_cash
        logger.debug(
            "Cash dividend %s %s per share for %s; credited %s %s",
            amount_per_share,
            ccy,
            sym_str,
            dividend_cash,
            ccy,
        )
        if dividend_policy == "reinvest" and dividend_cash > 0:
            # Queue a buy order for next trading day; shares determined at execution
            # We queue with shares=0 as a sentinel; engine resolves shares at execution
            # Actually, we need to store the cash amount for reinvestment.
            # The simplest approach: mark dividend cash as "earmarked" for this symbol.
            # We'll handle this by queuing a special reinvestment order.
            pending_orders.append(
                Order(
                    ready_date=d,
                    symbol=symbol,
                    side="buy",
                    shares=-1,  # sentinel: compute shares at execution using available cash
                )
            )

    elif kind in ("stock_dividend", "split"):
        ratio = Decimal(str(params.get("ratio", 1)))
        # stock_dividend: ratio=0.1 means 10 extra shares per 100 held
        # split: ratio=2.0 means 2-for-1
        if kind == "stock_dividend":
            new_shares = int(pos.shares * (1 + float(ratio)))
        else:
            new_shares = int(pos.shares * float(ratio))
        # Adjust avg_cost so total cost basis stays the same
        if new_shares > 0 and pos.shares > 0:
            new_avg_cost = pos.avg_cost * Decimal(str(pos.shares)) / Decimal(str(new_shares))
        else:
            new_avg_cost = pos.avg_cost
        positions[symbol] = replace(pos, shares=new_shares, avg_cost=new_avg_cost)
        logger.info(
            "Corporate action %s for %s: shares %d -> %d",
            kind,
            sym_str,
            pos.shares,
            new_shares,
        )

    elif kind == "reverse_split":
        ratio = Decimal(str(params.get("ratio", 1)))
        # reverse_split: ratio=0.5 means 1-for-2
        new_shares = int(pos.shares * float(ratio))
        if new_shares > 0 and pos.shares > 0:
            new_avg_cost = pos.avg_cost * Decimal(str(pos.shares)) / Decimal(str(new_shares))
        else:
            new_avg_cost = pos.avg_cost
        positions[symbol] = replace(pos, shares=new_shares, avg_cost=new_avg_cost)
        logger.info(
            "Reverse split for %s: shares %d -> %d",
            sym_str,
            pos.shares,
            new_shares,
        )

    elif kind in ("rights_issue", "spin_off"):
        logger.warning(
            "Corporate action %r for %s treated as cash-equivalent in Phase 2; "
            "no shares issued. Adjust manually if needed.",
            kind,
            sym_str,
        )
    else:
        logger.warning("Unknown corporate action kind %r for %s; skipping.", kind, sym_str)


def run_backtest(
    strategy: Any,
    repo: Any,
    config: BacktestConfig,
) -> BacktestResult:
    """Run a daily-loop event-driven backtest.

    .. admonition:: Refactor candidate (C1 in 2026-05-02 code review)

       This function has grown to ~720 lines and owns: calendar merging,
       universe discovery, corporate actions, order execution, T+N lock,
       slippage, costs, cash back-solve, rebalancing, and MTM. A follow-up
       PR should carve it into collaborators (``BacktestLoop`` +
       ``OrderExecutor``, ``RebalanceScheduler``, ``CashLedger``,
       ``CorporateActionHandler``, ``MTMAccumulator``). Scoping it here to
       avoid an unreviewable diff.

    Parameters
    ----------
    strategy:
        An object implementing either ``WeightStrategy`` or ``SignalStrategy`` protocol.
    repo:
        A ``DataRepository``-compatible object.
    config:
        Immutable backtest configuration.

    Returns
    -------
    BacktestResult
        Fully populated result with equity curve, trades, rejected orders, and metrics.
    """
    global _hk_borrow_warned
    _hk_borrow_warned = set()  # reset per-run warnings

    cost_model: CostModelBundle = (
        config.cost_model if config.cost_model is not None else DEFAULT_COSTS_2024
    )

    # Log HK lot size assumption once
    logger.warning(
        "HK lot size defaulted to 100 for all HK symbols in Phase 2. "
        "Per-symbol lot sizes will be added in a future data-layer update."
    )

    # ── Calendars ────────────────────────────────────────────────────────────
    sh_days = _trading_days_for_exchange(repo, Exchange.SH, config.start, config.end)
    hk_days = _trading_days_for_exchange(repo, Exchange.HK, config.start, config.end)
    all_days = _merge_calendars(sh_days, hk_days)
    all_days = [d for d in all_days if config.start <= d <= config.end]

    if not all_days:
        raise ValueError(
            f"No trading days in [{config.start}, {config.end}]. Check repository calendar data."
        )

    # ── Discover universe from strategy ──────────────────────────────────────
    # Generate weights for all rebalance dates to discover the universe
    rebalance_dates = _compute_rebalance_dates(all_days, config.rebalance)

    per_rebalance_weights: dict[date, Weights] = {}
    all_symbols_str: set[str] = set()

    # Call strategy.generate once (outside the per-date loop) to get all weights.
    # Dispatch logic lives in strategies.base.resolve_weights so engine.py and
    # verify.py share one source of truth. Re-raise ValueError (e.g. NaN
    # weights from pandera) immediately.
    try:
        all_weights = resolve_weights(strategy, repo, config.start, config.end)
    except (ValueError, TypeError):
        # Validation errors (NaN weights, bad schema) are user-input errors — re-raise.
        raise
    except Exception as exc:
        # Re-raise schema/validation errors from pandera or other validators.
        # These carry class names containing "Schema" or "Validation".
        exc_type = type(exc).__name__
        if "Schema" in exc_type or "Validation" in exc_type:
            raise ValueError(f"Strategy emitted invalid weights: {exc}") from exc
        logger.warning("Strategy.generate failed: %s", exc)
        all_weights = None

    # Validate weights and split by rebalance date.
    _warned_missing_symbols: set[str] = set()  # track per-run missing symbol warnings

    if all_weights is not None:
        wdf = all_weights.df.copy()

        if wdf.empty or "weight" not in wdf.columns:
            all_weights = None  # treat as no weights emitted

        else:
            # NaN check (belt-and-suspenders; pandera should have caught this already)
            if wdf["weight"].isna().any():
                bad = wdf[wdf["weight"].isna()]
                raise ValueError(
                    f"Strategy emitted NaN weights on {bad['date'].unique().tolist()} "
                    f"for symbols {bad['symbol'].tolist()}. Fix the strategy before running."
                )

            # Weight-sum validation when allow_leverage=False
            if not config.allow_leverage:
                for grp_date, grp in wdf.groupby("date"):
                    abs_sum = float(grp["weight"].abs().sum())
                    if abs_sum > 1.0 + LEVERAGE_SUM_TOLERANCE:
                        raise ValueError(
                            f"Weight sum {abs_sum:.6f} exceeds 1.0 on {grp_date} "
                            f"with allow_leverage=False. Either set allow_leverage=True "
                            f"or ensure abs(weights).sum() ≤ 1.0 per rebalance date."
                        )

            for r_date in rebalance_dates:
                date_mask = wdf["date"].dt.date == r_date
                day_w = wdf[date_mask]
                if day_w.empty:
                    continue
                # Reconstruct a Weights object for this date (already validated above)
                per_rebalance_weights[r_date] = Weights(df=day_w.reset_index(drop=True))
                all_symbols_str.update(day_w["symbol"].tolist())

    if not all_symbols_str:
        logger.warning("Strategy emitted no weights; returning empty result.")

    # ── Fetch market data ─────────────────────────────────────────────────────
    universe = list(all_symbols_str)

    prices_df = repo.get_prices(universe, config.start, config.end) if universe else pd.DataFrame()

    corp_acts_df = (
        repo.get_corporate_actions(universe, config.start, config.end)
        if universe
        else pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
    )

    # FX data — degrade gracefully only for expected data-availability errors.
    # Any other exception (type error, solver bug) propagates so a real bug
    # does not silently produce a backtest that treats HK as CNY.
    try:
        fx_df = repo.get_fx_series("CNY_HKD", config.start, config.end)
        fx_lookup: dict[date, float] = {
            pd.Timestamp(row["date"]).date(): float(row["rate"]) for _, row in fx_df.iterrows()
        }
    except (SourceError, DataIntegrityError) as exc:
        logger.warning(
            "FX series unavailable (CNY_HKD, %s .. %s); cross-currency "
            "positions will use 1.0 fallback: %s",
            config.start,
            config.end,
            exc,
        )
        fx_lookup = {}

    # Build fast lookup: (date, symbol) -> bar row
    if not prices_df.empty:
        prices_df = prices_df.copy()
        prices_df["_date_key"] = prices_df["date"].apply(lambda x: pd.Timestamp(x).date())
        prices_by_date_sym: dict[tuple[date, str], pd.Series] = {}
        for _, row in prices_df.iterrows():
            key = (row["_date_key"], str(row["symbol"]))
            prices_by_date_sym[key] = row
    else:
        prices_by_date_sym = {}

    # Build corporate actions lookup: date -> list of rows
    ca_by_date: dict[date, list[pd.Series]] = {}
    if not corp_acts_df.empty:
        for _, row in corp_acts_df.iterrows():
            ex_dt = pd.Timestamp(row["ex_date"]).date()
            ca_by_date.setdefault(ex_dt, []).append(row)

    # ── Benchmark ────────────────────────────────────────────────────────────
    benchmark_curve = _resolve_benchmark(
        config.benchmark,
        all_days,
        repo=repo,
        start=config.start,
        end=config.end,
    )

    # ── State ─────────────────────────────────────────────────────────────────
    cash: dict[Currency, Decimal] = {
        config.base_currency: config.initial_cash,
    }
    # Ensure HKD is always present for multi-currency
    if Currency.HKD not in cash:
        cash[Currency.HKD] = Decimal("0")
    if Currency.CNY not in cash:
        cash[Currency.CNY] = Decimal("0")

    positions: dict[Symbol, Position] = {}
    pending_orders: list[Order] = []

    trades_log: list[dict[str, Any]] = []
    rejected_log: list[dict[str, Any]] = []
    equity_daily: list[tuple[date, Decimal]] = []
    cash_hist: list[dict[str, Any]] = []

    # Dividend reinvestment cash earmarks: symbol -> Decimal
    dividend_earmarks: dict[Symbol, Decimal] = {}

    # OrderExecutor: stateless pre-execution decider (validation + pricing +
    # cost). Constructed once per run because cost_model is fixed.
    order_executor = OrderExecutor(cost_model=cost_model)

    # CashLedger: owns the cash + positions books and the rules that mutate
    # them after a PricedFill is validated. Holds positions/cash by reference
    # so engine.py and the ledger always observe the same state.
    cash_ledger = CashLedger(
        positions=positions,
        cash=cash,
        cost_model=cost_model,
        config=config,
        sh_days=sh_days,
        hk_days=hk_days,
        logger=logger,
    )

    # ── Daily loop ────────────────────────────────────────────────────────────
    for d in all_days:
        # 1. Apply corporate actions
        for ca_row in ca_by_date.get(d, []):
            _apply_corporate_action(
                positions, cash, ca_row, config.dividend_policy, pending_orders, d
            )

        # 2. Execute pending orders
        next_pending: list[Order] = []
        for order in pending_orders:
            sym = order.symbol
            sym_str = str(sym)
            bar = prices_by_date_sym.get((d, sym_str))

            # OrderExecutor (C1-02) owns: validation, dividend-sentinel
            # resolution, fill price, slippage, notional+cost. The cash
            # sufficiency check + position/cash mutation below stay here
            # until C1-03 carves out CashLedger.
            attempt = order_executor.attempt_fill(
                order=order,
                bar=bar,
                position=positions.get(sym),
                config=config,
                dividend_earmarks=dividend_earmarks,
                d=d,
            )

            if attempt is None:
                # Dividend-reinvestment no-op (no earmark / zero base price);
                # silent skip matches engine.py historical behaviour.
                continue

            if isinstance(attempt, OrderRejection):
                rejected_log.append(
                    {
                        "date": d,
                        "symbol": sym_str,
                        "side": order.side,
                        "shares": order.shares,
                        "reason": attempt.reason,
                    }
                )
                if attempt.retry:
                    next_pending.append(order)
                continue

            # HK short borrow cost warning (once per symbol per run).
            # Stays in engine for now -- it's a logging side effect, not a
            # validation result.
            if (
                order.side == "short"
                and sym.exchange == Exchange.HK
                and sym_str not in _hk_borrow_warned
            ):
                logger.warning("HK short borrow cost ignored in Phase 2 for symbol %s", sym_str)
                _hk_borrow_warned.add(sym_str)

            assert isinstance(attempt, PricedFill)

            # CashLedger (C1-03) owns the cash-sufficiency back-solve plus the
            # positions/cash mutation. Returns the values the trade log needs
            # (shares may differ from the PricedFill if the back-solve had to
            # reduce the order; ``skipped=True`` is the engine-continue case).
            application = cash_ledger.apply_fill(
                fill=attempt,
                d=d,
                fx_lookup=fx_lookup,
            )
            if application.skipped:
                continue

            shares = application.shares
            fill_price = application.fill_price
            notional_local = application.notional_local
            cost_total = application.cost_total
            sym_str = str(sym)

            trades_log.append(
                {
                    "exec_date": d,
                    "symbol": sym_str,
                    "side": order.side,
                    "shares": shares,
                    "fill_price": float(fill_price),
                    "notional": float(notional_local),
                    "cost_total": float(cost_total),
                }
            )

            # Cash-negative guard: raise RuntimeError with state dump
            for _ccy, _bal in cash.items():
                if _bal < Decimal("-1"):  # allow tiny rounding artefacts up to -1
                    _pos_snapshot = {
                        str(s): {"shares": p.shares, "avg_cost": float(p.avg_cost)}
                        for s, p in positions.items()
                    }
                    _last_trades = trades_log[-5:]
                    raise RuntimeError(
                        f"Cash balance for {_ccy} went negative ({float(_bal):.2f}) "
                        f"on {d} after executing {order.side} {shares} {sym_str}.\n"
                        f"Positions snapshot: {_pos_snapshot}\n"
                        f"Last 5 trades: {_last_trades}"
                    )

            # Expire T+N locks immediately if settlement==T+0
            # (full lock expiry is at end of day step 5)

        pending_orders = next_pending

        # 3. If d is a rebalance date, compute target orders for next trading day
        if d in rebalance_dates and d in per_rebalance_weights:
            w = per_rebalance_weights[d]
            date_mask = w.df["date"].dt.date == d
            day_weights = w.df[date_mask]

            if not day_weights.empty:
                # Compute NAV
                nav_base = _cash_in_base(cash, config.base_currency, d, fx_lookup)
                for sym_s, pos in positions.items():
                    bar_data = prices_by_date_sym.get((d, str(sym_s)))
                    if bar_data is not None:
                        price_local = Decimal(str(float(bar_data["close"])))
                        fx_rate = _fx_to_base(sym_s.currency, config.base_currency, d, fx_lookup)
                        nav_base += Decimal(str(abs(pos.shares))) * price_local * fx_rate

                target_symbols: set[Symbol] = set()
                for _, wrow in day_weights.iterrows():
                    sym_str_w = str(wrow["symbol"])
                    target_w = float(wrow["weight"])

                    try:
                        sym_w = parse_symbol(sym_str_w)
                    except UserInputError:
                        logger.warning("Cannot parse symbol %r; skipping.", sym_str_w)
                        continue

                    target_symbols.add(sym_w)
                    bar_data = prices_by_date_sym.get((d, sym_str_w))
                    if bar_data is None:
                        logger.warning(
                            "No price bar for %s on rebalance date %s; skipping.",
                            sym_str_w,
                            d,
                        )
                        continue

                    price_local_f = float(bar_data["close"])
                    if price_local_f <= 0:
                        continue

                    fx_rate_f = float(
                        _fx_to_base(sym_w.currency, config.base_currency, d, fx_lookup)
                    )
                    if fx_rate_f <= 0:
                        fx_rate_f = 1.0

                    target_shares_raw = float(nav_base) * target_w / (price_local_f * fx_rate_f)
                    lot = _LOT_SIZE[sym_w.exchange]
                    is_buy = target_shares_raw >= 0
                    target_shares = _round_to_lot(abs(target_shares_raw), lot, is_buy=is_buy)
                    if target_w < 0:
                        target_shares = -target_shares

                    current_pos = positions.get(sym_w)
                    current_shares_val = current_pos.shares if current_pos is not None else 0
                    diff = target_shares - current_shares_val

                    if diff == 0:
                        continue

                    side = _infer_side(current_shares_val, target_shares)
                    pending_orders.append(
                        Order(
                            ready_date=d,
                            symbol=sym_w,
                            side=side,
                            shares=abs(diff),
                        )
                    )

                # Close positions not in target
                for sym_close in set(positions.keys()) - target_symbols:
                    pos_close = positions[sym_close]
                    if pos_close.shares == 0:
                        continue
                    close_side: Literal["sell", "cover"] = (
                        "sell" if pos_close.shares > 0 else "cover"
                    )
                    pending_orders.append(
                        Order(
                            ready_date=d,
                            symbol=sym_close,
                            side=close_side,
                            shares=abs(pos_close.shares),
                        )
                    )

        # 4. Mark-to-market end-of-day NAV
        nav_d = _cash_in_base(cash, config.base_currency, d, fx_lookup)
        for sym_s, pos in positions.items():
            bar_data = prices_by_date_sym.get((d, str(sym_s)))
            if bar_data is not None:
                price_local = Decimal(str(float(bar_data["close"])))
                fx_rate = _fx_to_base(sym_s.currency, config.base_currency, d, fx_lookup)
                # Signed: short positions contribute negative MV
                nav_d += Decimal(str(pos.shares)) * price_local * fx_rate

        equity_daily.append((d, nav_d))

        cash_hist.append(
            {
                "date": d,
                "CNY": float(cash.get(Currency.CNY, Decimal("0"))),
                "HKD": float(cash.get(Currency.HKD, Decimal("0"))),
            }
        )

        # 5. Expire T+N locks
        for sym_lock, pos_lock in list(positions.items()):
            if pos_lock.locked_until is not None and pos_lock.locked_until <= d:
                positions[sym_lock] = replace(pos_lock, locked_until=None)

    # ── Finalize ──────────────────────────────────────────────────────────────
    ec_dates = [pd.Timestamp(d) for d, _ in equity_daily]
    ec_values = [float(v) for _, v in equity_daily]
    equity_curve = pd.Series(ec_values, index=pd.DatetimeIndex(ec_dates))

    # Log returns
    returns = equity_curve.pct_change().fillna(0.0)

    # Reindex benchmark to equity_curve index
    benchmark_curve = benchmark_curve.reindex(equity_curve.index).ffill().fillna(1.0)

    # Build trades DataFrame
    trades_df = (
        pd.DataFrame(trades_log)
        if trades_log
        else pd.DataFrame(
            columns=[
                "exec_date",
                "symbol",
                "side",
                "shares",
                "fill_price",
                "notional",
                "cost_total",
            ]
        )
    )

    rejected_df = (
        pd.DataFrame(rejected_log)
        if rejected_log
        else pd.DataFrame(columns=["date", "symbol", "side", "shares", "reason"])
    )

    cash_hist_df = (
        pd.DataFrame(cash_hist) if cash_hist else pd.DataFrame(columns=["date", "CNY", "HKD"])
    )

    # Build positions history (end-of-run snapshot)
    pos_rows = []
    for last_d, _ in equity_daily[-1:]:
        for sym_s, pos in positions.items():
            bar_data = prices_by_date_sym.get((last_d, str(sym_s)))
            price_f = float(bar_data["close"]) if bar_data is not None else 0.0
            fx_rate_f = float(_fx_to_base(sym_s.currency, config.base_currency, last_d, fx_lookup))
            pos_rows.append(
                {
                    "date": last_d,
                    "symbol": str(sym_s),
                    "shares": pos.shares,
                    "mkt_value_local": pos.shares * price_f,
                    "mkt_value_base": pos.shares * price_f * fx_rate_f,
                }
            )
    positions_history = (
        pd.DataFrame(pos_rows)
        if pos_rows
        else pd.DataFrame(columns=["date", "symbol", "shares", "mkt_value_local", "mkt_value_base"])
    )

    metrics = compute_metrics(
        equity=equity_curve,
        benchmark=benchmark_curve,
        trades=trades_df,
        positions_history=positions_history,
        start=config.start,
        end=config.end,
    )

    return BacktestResult(
        config=config,
        config_hash=hash_config(config),
        code_version=_get_code_version(),
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        returns=returns,
        positions_history=positions_history,
        trades=trades_df,
        rejected_orders=rejected_df,
        cash_history=cash_hist_df,
        metrics=metrics,
    )
