"""BacktestLoop — final piece of the C1 stack.

Replaces the procedural ``run_backtest`` body with a class-shaped
orchestrator. Behaviour-preserving: this is purely organizational. The
function ``run_backtest`` remains the public entry point and is now a
one-liner (``BacktestLoop(...).run()``).

The class decomposes into four phases, each a private method:

  1. ``_setup()`` -- calendars, universe discovery, market data, benchmark.
  2. ``_init_state()`` -- books, queues, collaborator instances.
  3. ``_run_daily_loop()`` -- the five-step daily loop, dispatching to the
     OrderExecutor / CashLedger / RebalanceScheduler / CorporateAction-
     Handler / MTMAccumulator collaborators carved out in C1-02..05.
  4. ``_finalize()`` -- assemble the ``BacktestResult``.

Module-level helpers used by setup (``_trading_days_for_exchange``,
``_merge_calendars``, ``_resolve_benchmark``, ``_max_consecutive_nans``)
and the public ``resolve_benchmark`` function move here too. Engine.py
re-exports ``resolve_benchmark`` for backward compatibility.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from ah_research.backtest.cash_ledger import CashLedger
from ah_research.backtest.corporate_actions import CorporateActionHandler
from ah_research.backtest.costs import DEFAULT_COSTS_2024, CostModelBundle
from ah_research.backtest.metrics import compute_metrics
from ah_research.backtest.mtm_accumulator import MTMAccumulator
from ah_research.backtest.order_executor import (
    OrderExecutor,
    OrderRejection,
    PricedFill,
)
from ah_research.backtest.rebalance_scheduler import (
    RebalanceScheduler,
    compute_rebalance_dates,
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
from ah_research.exceptions import DataIntegrityError, SourceError
from ah_research.meta import code_version
from ah_research.model.types import Currency, Exchange, Symbol
from ah_research.strategies.base import resolve_weights

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Benchmark resolution (public API + private helpers)
# ---------------------------------------------------------------------------

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


def _resolve_benchmark_internal(
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


# ---------------------------------------------------------------------------
# BacktestLoop
# ---------------------------------------------------------------------------


class BacktestLoop:
    """Orchestrates a single backtest run.

    Decomposes ``run_backtest`` into four phases:

      1. ``_setup`` -- calendars, universe discovery, market data, benchmark.
      2. ``_init_state`` -- books, queues, dividend earmarks, collaborators.
      3. ``_run_daily_loop`` -- the five-step daily loop dispatching to
         the OrderExecutor / CashLedger / RebalanceScheduler /
         CorporateActionHandler / MTMAccumulator collaborators.
      4. ``_finalize`` -- assemble the ``BacktestResult``.

    State that crosses phases is held as instance attributes, replacing
    the dense locals of the old procedural body.
    """

    def __init__(
        self,
        *,
        strategy: Any,
        repo: Any,
        config: BacktestConfig,
    ) -> None:
        self._strategy = strategy
        self._repo = repo
        self._config = config

        # Per-run state (populated by _setup / _init_state).
        self._cost_model: CostModelBundle | None = None
        self._sh_days: list[date] = []
        self._hk_days: list[date] = []
        self._all_days: list[date] = []
        self._rebalance_dates: list[date] = []
        self._per_rebalance_weights: dict[date, Weights] = {}
        self._prices_by_date_sym: dict[tuple[date, str], pd.Series] = {}
        self._ca_by_date: dict[date, list[pd.Series]] = {}
        self._fx_lookup: dict[date, float] = {}
        self._benchmark_curve: pd.Series = pd.Series(dtype=float)

        self._cash: dict[Currency, Decimal] = {}
        self._positions: dict[Symbol, Position] = {}
        self._pending_orders: list[Order] = []
        self._trades_log: list[dict[str, Any]] = []
        self._rejected_log: list[dict[str, Any]] = []
        self._dividend_earmarks: dict[Symbol, Decimal] = {}
        self._hk_borrow_warned: set[str] = set()

        # Collaborators (populated by _init_state).
        self._order_executor: OrderExecutor | None = None
        self._cash_ledger: CashLedger | None = None
        self._rebalance_scheduler: RebalanceScheduler | None = None
        self._corp_action_handler: CorporateActionHandler | None = None
        self._mtm: MTMAccumulator | None = None

    # -- public API -------------------------------------------------------

    def run(self) -> BacktestResult:
        """Run the four phases in order and return the final result."""
        self._setup()
        self._init_state()
        self._run_daily_loop()
        return self._finalize()

    # -- phase 1: setup ---------------------------------------------------

    def _setup(self) -> None:
        """Resolve cost model, calendars, universe, market data, benchmark."""
        config = self._config

        self._cost_model = (
            config.cost_model if config.cost_model is not None else DEFAULT_COSTS_2024
        )

        # Log HK lot size assumption once per run.
        logger.warning(
            "HK lot size defaulted to 100 for all HK symbols in Phase 2. "
            "Per-symbol lot sizes will be added in a future data-layer update."
        )

        # Calendars.
        self._sh_days = _trading_days_for_exchange(
            self._repo, Exchange.SH, config.start, config.end
        )
        self._hk_days = _trading_days_for_exchange(
            self._repo, Exchange.HK, config.start, config.end
        )
        all_days = _merge_calendars(self._sh_days, self._hk_days)
        self._all_days = [d for d in all_days if config.start <= d <= config.end]

        if not self._all_days:
            raise ValueError(
                f"No trading days in [{config.start}, {config.end}]. "
                "Check repository calendar data."
            )

        # Discover universe from strategy weights.
        self._rebalance_dates = compute_rebalance_dates(self._all_days, config.rebalance)
        all_symbols_str = self._discover_universe()

        # Fetch market data for the discovered universe.
        self._fetch_market_data(universe=list(all_symbols_str))

        # Resolve benchmark series.
        self._benchmark_curve = _resolve_benchmark_internal(
            config.benchmark,
            self._all_days,
            repo=self._repo,
            start=config.start,
            end=config.end,
        )

    def _discover_universe(self) -> set[str]:
        """Run strategy.generate once, validate weights, split by rebalance
        date, and return the set of symbols that appear in any rebalance."""
        config = self._config
        all_symbols_str: set[str] = set()

        # Re-raise validation errors immediately; log + degrade other failures.
        try:
            all_weights = resolve_weights(self._strategy, self._repo, config.start, config.end)
        except (ValueError, TypeError):
            raise
        except Exception as exc:
            exc_type = type(exc).__name__
            if "Schema" in exc_type or "Validation" in exc_type:
                raise ValueError(f"Strategy emitted invalid weights: {exc}") from exc
            logger.warning("Strategy.generate failed: %s", exc)
            all_weights = None

        if all_weights is not None:
            wdf = all_weights.df.copy()

            if wdf.empty or "weight" not in wdf.columns:
                all_weights = None
            else:
                if wdf["weight"].isna().any():
                    bad = wdf[wdf["weight"].isna()]
                    raise ValueError(
                        f"Strategy emitted NaN weights on {bad['date'].unique().tolist()} "
                        f"for symbols {bad['symbol'].tolist()}. "
                        f"Fix the strategy before running."
                    )

                if not config.allow_leverage:
                    for grp_date, grp in wdf.groupby("date"):
                        abs_sum = float(grp["weight"].abs().sum())
                        if abs_sum > 1.0 + LEVERAGE_SUM_TOLERANCE:
                            raise ValueError(
                                f"Weight sum {abs_sum:.6f} exceeds 1.0 on {grp_date} "
                                f"with allow_leverage=False. Either set allow_leverage=True "
                                f"or ensure abs(weights).sum() ≤ 1.0 per rebalance date."
                            )

                for r_date in self._rebalance_dates:
                    date_mask = wdf["date"].dt.date == r_date
                    day_w = wdf[date_mask]
                    if day_w.empty:
                        continue
                    self._per_rebalance_weights[r_date] = Weights(df=day_w.reset_index(drop=True))
                    all_symbols_str.update(day_w["symbol"].tolist())

        if not all_symbols_str:
            logger.warning("Strategy emitted no weights; returning empty result.")

        return all_symbols_str

    def _fetch_market_data(self, *, universe: list[str]) -> None:
        """Fetch prices, corporate actions, FX; build (date, symbol) lookups."""
        config = self._config

        prices_df = (
            self._repo.get_prices(universe, config.start, config.end)
            if universe
            else pd.DataFrame()
        )

        corp_acts_df = (
            self._repo.get_corporate_actions(universe, config.start, config.end)
            if universe
            else pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])
        )

        # FX data — degrade gracefully only for expected data-availability errors.
        # Any other exception (type error, solver bug) propagates so a real bug
        # does not silently produce a backtest that treats HK as CNY.
        try:
            fx_df = self._repo.get_fx_series("CNY_HKD", config.start, config.end)
            self._fx_lookup = {
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
            self._fx_lookup = {}

        # Build fast lookup: (date, symbol) -> bar row
        if not prices_df.empty:
            prices_df = prices_df.copy()
            prices_df["_date_key"] = prices_df["date"].apply(lambda x: pd.Timestamp(x).date())
            self._prices_by_date_sym = {}
            for _, row in prices_df.iterrows():
                key = (row["_date_key"], str(row["symbol"]))
                self._prices_by_date_sym[key] = row
        else:
            self._prices_by_date_sym = {}

        # Build corporate-actions lookup: date -> list of rows
        self._ca_by_date = {}
        if not corp_acts_df.empty:
            for _, row in corp_acts_df.iterrows():
                ex_dt = pd.Timestamp(row["ex_date"]).date()
                self._ca_by_date.setdefault(ex_dt, []).append(row)

    # -- phase 2: state init ----------------------------------------------

    def _init_state(self) -> None:
        """Initialize cash, positions, queues, dividend earmarks, collaborators."""
        config = self._config

        self._cash = {config.base_currency: config.initial_cash}
        if Currency.HKD not in self._cash:
            self._cash[Currency.HKD] = Decimal("0")
        if Currency.CNY not in self._cash:
            self._cash[Currency.CNY] = Decimal("0")

        self._positions = {}
        self._pending_orders = []
        self._trades_log = []
        self._rejected_log = []
        self._dividend_earmarks = {}
        self._hk_borrow_warned = set()

        assert self._cost_model is not None
        self._order_executor = OrderExecutor(cost_model=self._cost_model)

        self._cash_ledger = CashLedger(
            positions=self._positions,
            cash=self._cash,
            cost_model=self._cost_model,
            config=config,
            sh_days=self._sh_days,
            hk_days=self._hk_days,
            logger=logger,
        )

        self._rebalance_scheduler = RebalanceScheduler(config=config, logger=logger)

        self._corp_action_handler = CorporateActionHandler(
            positions=self._positions,
            cash=self._cash,
            logger=logger,
        )

        self._mtm = MTMAccumulator(
            positions=self._positions,
            cash=self._cash,
            prices_by_date_sym=self._prices_by_date_sym,
            config=config,
        )

    # -- phase 3: daily loop ----------------------------------------------

    def _run_daily_loop(self) -> None:
        """Five-step daily loop:
        1. corporate actions, 2. order execution, 3. rebalance,
        4. EOD MTM, 5. T+N lock expiry.
        """
        assert self._mtm is not None and self._corp_action_handler is not None
        assert self._rebalance_scheduler is not None

        for d in self._all_days:
            # 1. Apply corporate actions.
            for ca_row in self._ca_by_date.get(d, []):
                self._corp_action_handler.apply(
                    ca_row=ca_row,
                    dividend_policy=self._config.dividend_policy,
                    pending_orders=self._pending_orders,
                    d=d,
                )

            # 2. Execute pending orders.
            self._execute_pending_orders(d)

            # 3. Rebalance (if d is a rebalance date).
            if d in self._rebalance_dates and d in self._per_rebalance_weights:
                self._pending_orders.extend(
                    self._rebalance_scheduler.compute_orders(
                        d=d,
                        weights=self._per_rebalance_weights[d],
                        positions=self._positions,
                        cash=self._cash,
                        prices_by_date_sym=self._prices_by_date_sym,
                        fx_lookup=self._fx_lookup,
                    )
                )

            # 4. End-of-day MTM.
            self._mtm.record_eod(d=d, fx_lookup=self._fx_lookup)

            # 5. Expire T+N locks.
            self._mtm.expire_locks(d)

    def _execute_pending_orders(self, d: date) -> None:
        """Step 2 of the daily loop. Drains ``self._pending_orders``,
        appending fills to ``self._trades_log``, rejections to
        ``self._rejected_log``, and re-queueing transient blockers
        (``OrderRejection.retry=True``) for the next trading day.
        """
        assert self._order_executor is not None and self._cash_ledger is not None

        next_pending: list[Order] = []
        for order in self._pending_orders:
            sym = order.symbol
            sym_str = str(sym)
            bar = self._prices_by_date_sym.get((d, sym_str))

            attempt = self._order_executor.attempt_fill(
                order=order,
                bar=bar,
                position=self._positions.get(sym),
                config=self._config,
                dividend_earmarks=self._dividend_earmarks,
                d=d,
            )

            if attempt is None:
                # Dividend-reinvestment no-op (no earmark / zero base price);
                # silent skip preserves engine's historical behaviour.
                continue

            if isinstance(attempt, OrderRejection):
                self._rejected_log.append(
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
            if (
                order.side == "short"
                and sym.exchange == Exchange.HK
                and sym_str not in self._hk_borrow_warned
            ):
                logger.warning("HK short borrow cost ignored in Phase 2 for symbol %s", sym_str)
                self._hk_borrow_warned.add(sym_str)

            assert isinstance(attempt, PricedFill)

            application = self._cash_ledger.apply_fill(
                fill=attempt,
                d=d,
                fx_lookup=self._fx_lookup,
            )
            if application.skipped:
                continue

            shares = application.shares
            self._trades_log.append(
                {
                    "exec_date": d,
                    "symbol": sym_str,
                    "side": order.side,
                    "shares": shares,
                    "fill_price": float(application.fill_price),
                    "notional": float(application.notional_local),
                    "cost_total": float(application.cost_total),
                }
            )

            # Cash-negative guard: raise RuntimeError with state dump.
            for _ccy, _bal in self._cash.items():
                if _bal < Decimal("-1"):  # tolerate tiny rounding artefacts
                    _pos_snapshot = {
                        str(s): {"shares": p.shares, "avg_cost": float(p.avg_cost)}
                        for s, p in self._positions.items()
                    }
                    _last_trades = self._trades_log[-5:]
                    raise RuntimeError(
                        f"Cash balance for {_ccy} went negative ({float(_bal):.2f}) "
                        f"on {d} after executing {order.side} {shares} {sym_str}.\n"
                        f"Positions snapshot: {_pos_snapshot}\n"
                        f"Last 5 trades: {_last_trades}"
                    )

        self._pending_orders = next_pending

    # -- phase 4: finalize ------------------------------------------------

    def _finalize(self) -> BacktestResult:
        """Assemble the BacktestResult from accumulated state."""
        assert self._mtm is not None
        config = self._config

        ec_dates = [pd.Timestamp(d) for d, _ in self._mtm.equity_daily]
        ec_values = [float(v) for _, v in self._mtm.equity_daily]
        equity_curve = pd.Series(ec_values, index=pd.DatetimeIndex(ec_dates))

        returns = equity_curve.pct_change().fillna(0.0)
        benchmark_curve = self._benchmark_curve.reindex(equity_curve.index).ffill().fillna(1.0)

        trades_df = (
            pd.DataFrame(self._trades_log)
            if self._trades_log
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
            pd.DataFrame(self._rejected_log)
            if self._rejected_log
            else pd.DataFrame(columns=["date", "symbol", "side", "shares", "reason"])
        )

        cash_hist_df = (
            pd.DataFrame(self._mtm.cash_history)
            if self._mtm.cash_history
            else pd.DataFrame(columns=["date", "CNY", "HKD"])
        )

        pos_rows = self._mtm.build_positions_history(self._fx_lookup)
        positions_history = (
            pd.DataFrame(pos_rows)
            if pos_rows
            else pd.DataFrame(
                columns=["date", "symbol", "shares", "mkt_value_local", "mkt_value_base"]
            )
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
            code_version=code_version(),
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            returns=returns,
            positions_history=positions_history,
            trades=trades_df,
            rejected_orders=rejected_df,
            cash_history=cash_hist_df,
            metrics=metrics,
        )
