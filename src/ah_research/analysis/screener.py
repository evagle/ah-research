"""Screener: vectorized fundamental/flag filtering with serializable predicate dict."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from ah_research.data.repository import DataRepository

# Supported comparison operators.
_OPERATORS = frozenset({"<", "<=", ">", ">=", "==", "!=", "between", "in", "not_in"})

# A condition tuple: (op, value) or (op, lo, hi) for between.
Condition = tuple[Any, ...]


@dataclass(frozen=True)
class ScreenResult:
    """Result of a run_screen() call."""

    asof: date
    universe: str
    n_input: int
    n_passed: int
    frame: pd.DataFrame
    conditions_applied: dict[str, Condition]


# ---------------------------------------------------------------------------
# Derived-column helpers
# ---------------------------------------------------------------------------


def _rolling_avg(
    repo: DataRepository,
    symbols: list[str],
    asof: date,
    column: str,
    years: int,
) -> pd.Series:
    """Return trailing ``years``-year average of ``column`` per symbol."""
    start = date(asof.year - years, asof.month, asof.day)
    fund = repo.get_fundamentals(symbols, start=start, end=asof, asof=asof)
    if fund.empty or column not in fund.columns:
        return pd.Series(float("nan"), index=range(len(symbols)), dtype=float)
    avg = fund.groupby("symbol")[column].mean()
    return avg.reindex(symbols).reset_index(drop=True)


def _growth_cagr(
    repo: DataRepository,
    symbols: list[str],
    asof: date,
    column: str,
    years: int,
) -> pd.Series:
    """Return trailing ``years``-year CAGR of ``column`` per symbol."""
    start = date(asof.year - years, asof.month, asof.day)
    fund = repo.get_fundamentals(symbols, start=start, end=asof, asof=asof)
    if fund.empty or column not in fund.columns:
        return pd.Series(float("nan"), index=range(len(symbols)), dtype=float)

    def _sym_cagr(grp: pd.DataFrame) -> float:
        grp = grp.sort_values("report_date").dropna(subset=[column])
        if len(grp) < 2:
            return float("nan")
        first = float(grp[column].iloc[0])
        last = float(grp[column].iloc[-1])
        if first <= 0:
            return float("nan")
        n = (grp["report_date"].iloc[-1] - grp["report_date"].iloc[0]).days / 365.25
        if n <= 0:
            return float("nan")
        return float((last / first) ** (1.0 / n) - 1.0)

    cagr = fund.groupby("symbol").apply(_sym_cagr)
    return cagr.reindex(symbols).reset_index(drop=True)


def _dividend_growth(
    repo: DataRepository,
    symbols: list[str],
    asof: date,
    years: int,
) -> pd.Series:
    """Return trailing ``years``-year dividend CAGR per symbol."""
    import json

    start = date(asof.year - years, asof.month, asof.day)
    actions = repo.get_corporate_actions(symbols, start=start, end=asof)
    if actions.empty:
        return pd.Series(float("nan"), index=range(len(symbols)), dtype=float)

    div = actions[actions["kind"] == "cash_dividend"].copy()
    if div.empty:
        return pd.Series(float("nan"), index=range(len(symbols)), dtype=float)

    def _parse_amount(s: str) -> float:
        try:
            return float(json.loads(s).get("amount_per_share", 0.0))
        except Exception:
            return 0.0

    div["amount"] = div["params_json"].apply(_parse_amount)
    div["year"] = pd.to_datetime(div["ex_date"]).dt.year
    annual = div.groupby(["symbol", "year"])["amount"].sum().reset_index()

    def _sym_div_cagr(grp: pd.DataFrame) -> float:
        grp = grp.sort_values("year")
        if len(grp) < 2:
            return float("nan")
        first = float(grp["amount"].iloc[0])
        last = float(grp["amount"].iloc[-1])
        if first <= 0:
            return float("nan")
        n = float(grp["year"].iloc[-1] - grp["year"].iloc[0])
        if n <= 0:
            return float("nan")
        return float((last / first) ** (1.0 / n) - 1.0)

    cagr = annual.groupby("symbol").apply(_sym_div_cagr)
    return cagr.reindex(symbols).reset_index(drop=True)


def _consistency_grades(
    repo: DataRepository,
    symbols: list[str],
    asof: date,
) -> pd.Series:
    """Return dividend consistency grade (A-F) per symbol."""
    from ah_research.analysis.dividend_history import dividend_consistency_grade

    start = date(asof.year - 10, asof.month, asof.day)
    actions = repo.get_corporate_actions(symbols, start=start, end=asof)

    grades = []
    for sym in symbols:
        sym_actions = actions[actions["symbol"] == sym] if not actions.empty else actions
        grades.append(dividend_consistency_grade(sym_actions, asof=asof, window_years=10))
    return pd.Series(grades, index=range(len(symbols)), dtype=object)


def _oe_yield(
    repo: DataRepository,
    symbols: list[str],
    asof: date,
    market_cap: pd.Series,
) -> pd.Series:
    """Return owner-earnings yield (OE / market_cap) per row."""
    from ah_research.analysis.owner_earnings import owner_earnings_series

    fund = repo.get_fundamentals(symbols, start=asof, end=asof, asof=asof)
    if fund.empty:
        return pd.Series(float("nan"), index=market_cap.index, dtype=float)

    # Get latest OE per symbol
    oe_map: dict[str, float] = {}
    for sym in symbols:
        sym_fund = fund[fund["symbol"] == sym]
        oe = owner_earnings_series(sym_fund)
        oe_map[sym] = float(oe.iloc[-1]) if not oe.empty else float("nan")

    oe_values = [oe_map.get(sym, float("nan")) for sym in symbols]
    oe_series = pd.Series(oe_values, index=market_cap.index, dtype=float)
    mc = market_cap.astype(float).replace(0.0, float("nan"))
    return oe_series / mc


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def _apply_condition(series: pd.Series, cond: Condition) -> pd.Series:
    """Apply a single predicate condition to a Series, returning a boolean mask."""
    op = cond[0]
    result: pd.Series
    if op == "<":
        result = series < cond[1]
    elif op == "<=":
        result = series <= cond[1]
    elif op == ">":
        result = series > cond[1]
    elif op == ">=":
        result = series >= cond[1]
    elif op == "==":
        result = series == cond[1]
    elif op == "!=":
        result = series != cond[1]
    elif op == "between":
        lo, hi = cond[1], cond[2]
        if lo > hi:
            raise ValueError(f"between requires lo <= hi, got ({lo}, {hi})")
        result = series.between(lo, hi)
    elif op == "in":
        result = series.isin(cond[1])
    elif op == "not_in":
        result = ~series.isin(cond[1])
    else:
        raise ValueError(f"Unknown operator: {op!r}")
    return result


# ---------------------------------------------------------------------------
# Derived-column enrichment
# ---------------------------------------------------------------------------


def _enrich_screen_frame(
    base: pd.DataFrame,
    repo: DataRepository,
    asof: date,
    required_columns: set[str],
) -> pd.DataFrame:
    """Compute derived columns only when referenced in ``required_columns``."""
    df = base.copy()
    syms = df["symbol"].tolist()

    derived: dict[str, Any] = {
        "roe_3y_avg": lambda: _rolling_avg(repo, syms, asof, "roe", years=3),
        "roe_5y_avg": lambda: _rolling_avg(repo, syms, asof, "roe", years=5),
        "revenue_growth_3y_cagr": lambda: _growth_cagr(repo, syms, asof, "revenue", years=3),
        "net_income_growth_3y_cagr": lambda: _growth_cagr(repo, syms, asof, "net_income", years=3),
        "dividend_growth_5y_cagr": lambda: _dividend_growth(repo, syms, asof, years=5),
        "dividend_consistency_grade": lambda: _consistency_grades(repo, syms, asof),
        "owner_earnings_yield": lambda: _oe_yield(repo, syms, asof, df["market_cap"]),
    }

    for col, compute in derived.items():
        if col in required_columns and col not in df.columns:
            df[col] = compute()

    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_screen(
    conditions: dict[str, Condition],
    repo: DataRepository,
    asof: date,
    universe: str = "CSI300",
) -> ScreenResult:
    """Filter the universe against ``conditions`` at ``asof`` date.

    Parameters
    ----------
    conditions:
        Mapping of column name to predicate tuple ``(op, value)`` or
        ``(op, lo, hi)`` for ``between``. Supported ops: ``<``, ``<=``,
        ``>``, ``>=``, ``==``, ``!=``, ``between``, ``in``, ``not_in``.
    repo:
        Data source implementing the DataRepository interface.
    asof:
        Point-in-time date for fundamentals and universe membership.
    universe:
        Universe index name (e.g. ``"CSI300"``). Defaults to ``"CSI300"``.

    Returns
    -------
    ScreenResult
        Frozen dataclass with the filtered frame and metadata.
    """
    # Validate operators eagerly
    for col, cond in conditions.items():
        if not isinstance(cond, tuple) or len(cond) < 2:
            raise ValueError(
                f"Condition for {col!r} must be (op, value) or (op, lo, hi); got {cond!r}"
            )
        if cond[0] not in _OPERATORS:
            raise ValueError(f"Unknown operator {cond[0]!r} for column {col!r}")
        # Early validation of between lo <= hi
        if cond[0] == "between" and len(cond) >= 3 and cond[1] > cond[2]:
            raise ValueError(
                f"between requires lo <= hi, got ({cond[1]}, {cond[2]}) for column {col!r}"
            )

    universe_df = repo.get_universe_over_time(universe, asof, asof, freq="D")
    if universe_df.empty:
        return ScreenResult(
            asof=asof,
            universe=universe,
            n_input=0,
            n_passed=0,
            frame=pd.DataFrame(),
            conditions_applied=conditions,
        )
    symbols = universe_df["symbol"].unique().tolist()

    fundamentals = repo.get_fundamentals(symbols, start=asof, end=asof, asof=asof)
    sectors = repo.get_sector(symbols)

    if fundamentals.empty:
        base = sectors[["symbol", "sector_l1", "sector_l2"]].copy()
    else:
        base = fundamentals.merge(
            sectors[["symbol", "sector_l1", "sector_l2"]], on="symbol", how="left"
        )

    base = _enrich_screen_frame(base, repo, asof, required_columns=set(conditions.keys()))

    # Validate all referenced columns exist
    for col in conditions:
        if col not in base.columns:
            available = sorted(base.columns.tolist())
            suggestions = difflib.get_close_matches(col, available, n=3)
            raise KeyError(
                f"Column {col!r} not found. Did you mean: {suggestions}? "
                f"Available columns: {available}"
            )

    mask = pd.Series(True, index=base.index)
    for col, cond in conditions.items():
        mask &= _apply_condition(base[col], cond)

    passed = base[mask].copy()
    return ScreenResult(
        asof=asof,
        universe=universe,
        n_input=len(base),
        n_passed=len(passed),
        frame=passed,
        conditions_applied=conditions,
    )
