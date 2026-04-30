"""`ah construct` Typer sub-app — build a portfolio from a universe JSON."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from ah_research.backtest.types import Signals
from ah_research.portfolio.constructor import Constructor
from ah_research.portfolio.optimizer import Optimizer
from ah_research.portfolio.optimizer.estimators.covariance import LedoitWolfCovariance
from ah_research.portfolio.optimizer.estimators.returns import HistoricalMeanReturns

construct_app = typer.Typer(
    name="construct",
    help="Portfolio construction CLI.",
    no_args_is_help=True,
)
console = Console()


def _parse_universe(path: Path) -> dict[str, float]:
    text = path.read_text()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
        if isinstance(data, list):
            return {str(s): 1.0 for s in data}
    except json.JSONDecodeError:
        pass
    return {line.strip(): 1.0 for line in text.splitlines() if line.strip()}


def _make_repo() -> object:
    """Build a DataRepository from the default cache. Extracted for test mocking."""
    from ah_research.config import get_settings
    from ah_research.data.cache import DuckDBCache
    from ah_research.data.repository import DataRepository
    from ah_research.integrations.fake import FakeSources

    settings = get_settings()
    sources = FakeSources(seed=42)
    cache = DuckDBCache(settings.cache_duckdb_path)
    return DataRepository(
        price_source=sources.prices,
        fundamentals_source=sources.fundamentals,
        fx_source=sources.fx,
        calendar_source=sources.calendar,
        sector_source=sources.sectors,
        corp_actions_source=sources.corporate_actions,
        constituents_source=sources.constituents,
        cache=cache,
    )


@construct_app.callback(invoke_without_command=True)
def construct(
    universe: Annotated[Path, typer.Argument(help="Path to universe JSON or newline list.")],
    asof: Annotated[str, typer.Option("--asof", help="YYYY-MM-DD")],
    weight_by: Annotated[str, typer.Option("--weight-by", help="Weighting scheme.")] = "equal",
    objective: Annotated[
        str, typer.Option("--objective", help="mean_variance or risk_parity")
    ] = "mean_variance",
    risk_aversion: Annotated[float, typer.Option("--risk-aversion")] = 1.0,
    max_turnover: Annotated[float | None, typer.Option("--max-turnover")] = None,
    lookback_days: Annotated[int, typer.Option("--lookback-days")] = 252,
) -> None:
    """Build a portfolio for <universe> at --asof using the given weighting."""
    symbols_signals = _parse_universe(universe)
    asof_date = datetime.strptime(asof, "%Y-%m-%d").date()

    sig_df = pd.DataFrame(
        {
            "date": pd.to_datetime([asof_date] * len(symbols_signals)),
            "symbol": list(symbols_signals.keys()),
            "signal": list(symbols_signals.values()),
        }
    )
    signals = Signals.from_dataframe(sig_df)
    repo = _make_repo()

    optimizer: Optimizer | None = None
    if weight_by == "optimize":
        from ah_research.portfolio.constructor import Constraint

        cons: list[Constraint] = []
        if max_turnover is not None:
            cons.append(Constraint.max_turnover(max_turnover))
        if objective == "mean_variance":
            optimizer = Optimizer(
                objective="mean_variance",
                cov_estimator=LedoitWolfCovariance(),
                returns_estimator=HistoricalMeanReturns(lookback_days=lookback_days),
                constraints=cons,
                risk_aversion=risk_aversion,
                lookback_days=lookback_days,
            )
        elif objective == "risk_parity":
            optimizer = Optimizer(
                objective="risk_parity",
                cov_estimator=LedoitWolfCovariance(),
                constraints=cons,
                lookback_days=lookback_days,
            )
        else:
            raise typer.BadParameter(f"unknown objective: {objective}")

    builder = Constructor(signals, repo=repo, asof=asof_date, optimizer=optimizer)
    builder = builder.method("all_positive")
    builder = builder.weight_by(weight_by)  # type: ignore[arg-type]
    report = builder.build()

    tbl = Table(title=f"{weight_by} weights @ {asof}")
    tbl.add_column("symbol")
    tbl.add_column("weight", justify="right")
    for _, row in report.weights.iterrows():
        tbl.add_row(str(row["symbol"]), f"{float(row['weight']):.4f}")
    console.print(tbl)

    if report.optimization_result is not None:
        console.print(f"[bold]solver:[/bold] {report.optimization_result.solver_status}")
