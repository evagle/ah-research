"""Characterization-test plumbing for ``backtest.engine.run_backtest``.

Purpose
-------
Pin the *current* observable behaviour of ``run_backtest`` so the upcoming C1
refactor (carving the 720-line god function into ``OrderExecutor`` /
``CashLedger`` / ``RebalanceScheduler`` / ``CorporateActionHandler`` /
``MTMAccumulator``) can be proven behaviour-preserving.

There is no reference backtest oracle for this codebase, so this module
generates a deterministic, **reviewable** JSON digest of every
``BacktestResult`` field. The digest is:

* small (a few KB per config), so reviewers can read it in a diff;
* deterministic (all floats rounded to 8 decimals; pandas indices serialised
  as ISO date strings; Decimal serialised as its string form);
* granular (when something changes, the failing assertion names the field).

The 3 configs below were chosen to exercise the most complex code paths in
``run_backtest``: T+N lock, FX mark-to-market, and the cost model.

Used by:
  - tests/integration/test_engine_characterization.py (the test)
  - scripts/_regen_engine_characterization_fixtures.py (the regen script)
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from ah_research.backtest.costs import DEFAULT_COSTS_2024, CostModelBundle
from ah_research.backtest.types import BacktestConfig, BacktestResult, Weights

FIXTURES_DIR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "phase2" / "engine_characterization"
)
DIGEST_PRECISION = 8

# ---------------------------------------------------------------------------
# Strategy stubs (small; copies of patterns already used in tests/unit/backtest/)
# ---------------------------------------------------------------------------


class _FixedLongStrategy:
    """100% in one A-share symbol on each month-end rebalance."""

    name = "fixed_long"

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def generate(self, repo: Any, start: date, end: date) -> Weights:
        eom = pd.date_range(start, end, freq="ME")
        df = pd.DataFrame(
            {
                "date": eom,
                "symbol": [self.symbol] * len(eom),
                "weight": [1.0] * len(eom),
            }
        )
        return Weights.from_dataframe(df)


class _FixedMixedStrategy:
    """50/50 A-share + HK share at every month-end (multi-currency)."""

    name = "fixed_mixed"

    def __init__(self, a_symbol: str, hk_symbol: str) -> None:
        self.a_symbol = a_symbol
        self.hk_symbol = hk_symbol

    def generate(self, repo: Any, start: date, end: date) -> Weights:
        eom = pd.date_range(start, end, freq="ME")
        rows: list[dict[str, Any]] = []
        for d in eom:
            rows.append({"date": d, "symbol": self.a_symbol, "weight": 0.5})
            rows.append({"date": d, "symbol": self.hk_symbol, "weight": 0.5})
        return Weights.from_dataframe(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# Config registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CharacterizationCase:
    """One pinned (config, strategy, market) tuple. ``name`` doubles as the
    fixture filename stem."""

    name: str
    description: str
    start: date
    end: date
    symbols: tuple[str, ...]
    initial_cash: Decimal
    benchmark: str
    cost_model: CostModelBundle
    strategy_factory: Any  # callable returning a strategy

    def build_strategy(self) -> Any:
        return self.strategy_factory(self.symbols, self.start, self.end)

    def build_config(self) -> BacktestConfig:
        return BacktestConfig(
            start=self.start,
            end=self.end,
            initial_cash=self.initial_cash,
            benchmark=self.benchmark,
            cost_model=self.cost_model,
        )


def _minimal_strategy_factory(
    symbols: tuple[str, ...], start: date, end: date
) -> _FixedLongStrategy:
    del start, end  # unused; needed for uniform factory signature
    return _FixedLongStrategy(symbols[0])


def _multi_currency_strategy_factory(
    symbols: tuple[str, ...], start: date, end: date
) -> _FixedMixedStrategy:
    del start, end  # unused; needed for uniform factory signature
    return _FixedMixedStrategy(symbols[0], symbols[1])


def all_cases() -> list[CharacterizationCase]:
    """Return every registered case. Order is stable; test parametrization
    uses ``case.name`` as the id."""
    return [
        CharacterizationCase(
            name="minimal_long_only",
            description=(
                "Single A-share, monthly rebalance, zero costs. Exercises the "
                "core daily loop, MTM, and a clean rebalance path."
            ),
            start=date(2024, 1, 2),
            end=date(2024, 3, 29),
            symbols=("600000.SH",),
            initial_cash=Decimal("1000000"),
            benchmark="zero",
            cost_model=CostModelBundle(models={}),
            strategy_factory=_minimal_strategy_factory,
        ),
        CharacterizationCase(
            name="multi_currency",
            description=(
                "A-share + HK share, single rebalance, zero costs. Exercises "
                "FX mark-to-market and the multi-currency cash ledger."
            ),
            start=date(2024, 1, 2),
            end=date(2024, 3, 29),
            symbols=("600000.SH", "0001.HK"),
            initial_cash=Decimal("1000000"),
            benchmark="zero",
            cost_model=CostModelBundle(models={}),
            strategy_factory=_multi_currency_strategy_factory,
        ),
        CharacterizationCase(
            name="with_costs",
            description=(
                "Single A-share, monthly rebalance, DEFAULT_COSTS_2024. "
                "Exercises the cost model + cash back-solve path."
            ),
            start=date(2024, 1, 2),
            end=date(2024, 3, 29),
            symbols=("600000.SH",),
            initial_cash=Decimal("1000000"),
            benchmark="zero",
            cost_model=DEFAULT_COSTS_2024,
            strategy_factory=_minimal_strategy_factory,
        ),
    ]


# ---------------------------------------------------------------------------
# Result digest
# ---------------------------------------------------------------------------


def _round(x: float) -> float | None:
    """Round to a fixed precision so platform-specific FP noise can't
    invalidate the digest. NaN/Inf are coerced to ``None`` so a JSON
    round-trip preserves equality (``float('nan') == float('nan')`` is
    ``False``, which would silently break the digest comparison).
    ``DIGEST_PRECISION`` is intentionally tight so a real numerical
    change is still caught."""
    f = float(x)
    if not math.isfinite(f):
        return None
    return round(f, DIGEST_PRECISION)


def _series_summary(s: pd.Series) -> dict[str, Any]:
    """Summarise a numeric Series. The sha256 covers the rounded value list
    so any per-step change in the curve trips the test."""
    if len(s) == 0:
        return {"len": 0, "sha256": ""}
    rounded = [_round(v) for v in s.tolist()]
    blob = json.dumps(rounded, sort_keys=True).encode()
    return {
        "len": len(s),
        "first": _round(s.iloc[0]),
        "last": _round(s.iloc[-1]),
        "min": _round(s.min()),
        "max": _round(s.max()),
        "mean": _round(s.mean()),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


def _df_canonical_sha(df: pd.DataFrame) -> str:
    """Hash a DataFrame deterministically: sort columns, render every cell
    via str(), join with explicit separators, sha256."""
    if df.empty:
        return ""
    sorted_cols = sorted(df.columns)
    rows = [
        "\t".join(str(_canonical_cell(row[c])) for c in sorted_cols) for _, row in df.iterrows()
    ]
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def _canonical_cell(v: Any) -> Any:
    """Render a cell deterministically across pandas/Decimal/np types."""
    if isinstance(v, Decimal):
        return f"{v:.10f}"
    if isinstance(v, float):
        rounded = _round(v)
        # _round returns None for NaN/Inf to keep JSON-roundtrip stable.
        return "NaN" if rounded is None else f"{rounded:.{DIGEST_PRECISION}f}"
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def _trades_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"count": 0, "total_notional": "0", "total_cost": "0", "sha256": ""}
    return {
        "count": len(df),
        "total_notional": f"{Decimal(str(df['notional'].astype(str).map(Decimal).sum())):.10f}",
        "total_cost": f"{Decimal(str(df['cost_total'].astype(str).map(Decimal).sum())):.10f}",
        "sha256": _df_canonical_sha(df),
    }


def _positions_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"count": 0, "unique_symbols": 0, "sha256": ""}
    return {
        "count": len(df),
        "unique_symbols": int(df["symbol"].nunique()),
        "sha256": _df_canonical_sha(df),
    }


def _cash_history_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"count": 0, "sha256": ""}
    return {"count": len(df), "sha256": _df_canonical_sha(df)}


def _metrics_summary(metrics_dict: dict[str, Any]) -> dict[str, Any]:
    """Round every float; drop None entries so the JSON stays compact."""
    out: dict[str, Any] = {}
    for k, v in sorted(metrics_dict.items()):
        if v is None:
            continue
        if isinstance(v, float):
            out[k] = _round(v)
        else:
            out[k] = v
    return out


def digest_result(result: BacktestResult) -> dict[str, Any]:
    """Convert a BacktestResult to a deterministic, reviewable JSON-compatible
    dict. ``code_version`` is excluded — it changes per commit and would make
    the digest non-deterministic."""
    return {
        "config_hash": result.config_hash,
        "equity_curve": _series_summary(result.equity_curve),
        "benchmark_curve": _series_summary(result.benchmark_curve),
        "returns": _series_summary(result.returns),
        "trades": _trades_summary(result.trades),
        "positions_history": _positions_summary(result.positions_history),
        "cash_history": _cash_history_summary(result.cash_history),
        "rejected_orders_count": len(result.rejected_orders),
        "metrics": _metrics_summary(asdict(result.metrics)),
    }


def fixture_path(case: CharacterizationCase) -> Path:
    return FIXTURES_DIR / f"{case.name}.json"


def load_fixture(case: CharacterizationCase) -> dict[str, Any]:
    return json.loads(fixture_path(case).read_text())


def write_fixture(case: CharacterizationCase, digest: dict[str, Any]) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    fixture_path(case).write_text(json.dumps(digest, indent=2, sort_keys=True) + "\n")


def run_case(case: CharacterizationCase) -> BacktestResult:
    """Run a case end-to-end against the synthetic market. Imports done
    lazily so this module stays cheap to import in regen scripts."""
    from ah_research.backtest.engine import run_backtest
    from tests.fixtures.phase2.synthetic_market import build_synthetic_market

    repo = build_synthetic_market(
        start=case.start,
        end=case.end,
        symbols=list(case.symbols),
    )
    return run_backtest(case.build_strategy(), repo, case.build_config())
