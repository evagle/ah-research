"""`ah filings` Typer sub-app."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ah_research.filings.filings_repository import FilingsRepository

filings_app = typer.Typer(name="filings", help="Query local filings (年报 / 招股说明书 / 研报)")
console = Console()


@filings_app.command("list")
def list_filings(
    symbol: str | None = typer.Argument(None, help="Optional symbol filter."),
    root: Path = typer.Option(Path("data/filings"), help="Filings root directory."),  # noqa: B008
) -> None:
    repo = FilingsRepository(root=root)
    if symbol is None:
        table = Table(title="Filings (summary)")
        table.add_column("symbol")
        table.add_column("n_annual", justify="right")
        table.add_column("has_ipo")
        table.add_column("n_research", justify="right")
        for sym in repo.list_symbols():
            filings = repo.list_filings(sym)
            annual = sum(1 for f in filings if f.kind == "annual")
            ipo = any(f.kind == "ipo" for f in filings)
            research = sum(1 for f in filings if f.kind == "research")
            table.add_row(sym, str(annual), "true" if ipo else "false", str(research))
        console.print(table)
    else:
        filings = repo.list_filings(symbol)
        if not filings:
            console.print(f"[yellow]No filings found for {symbol}[/]")
            raise typer.Exit(code=0)
        table = Table(title=f"Filings for {symbol}")
        table.add_column("kind")
        table.add_column("year")
        table.add_column("title")
        table.add_column("path")
        for f in filings:
            table.add_row(
                f.kind,
                str(f.year) if f.year is not None else "-",
                f.title or "-",
                str(f.path),
            )
        console.print(table)


@filings_app.command("show")
def show_filing(
    symbol: str = typer.Argument(..., help="Symbol e.g. 600000.SH"),
    kind: str = typer.Argument(..., help="annual | ipo | research"),
    year: int | None = typer.Option(None, help="Required for kind=annual."),
    root: Path = typer.Option(Path("data/filings"), help="Filings root directory."),  # noqa: B008
    full: bool = typer.Option(False, "--full", help="Print full text instead of head."),
    head_lines: int = typer.Option(80, help="Lines to print when not --full."),
) -> None:
    repo = FilingsRepository(root=root)
    text: str
    if kind == "annual":
        if year is None:
            raise typer.BadParameter("--year is required for kind=annual")
        f = repo.get_annual(symbol, year)
        text = f.text
    elif kind == "ipo":
        f2 = repo.get_ipo(symbol)
        if f2 is None:
            console.print(f"[red]No IPO prospectus for {symbol}[/]")
            raise typer.Exit(code=1)
        text = f2.text
    elif kind == "research":
        rs = repo.get_research(symbol)
        if not rs:
            console.print(f"[red]No research for {symbol}[/]")
            raise typer.Exit(code=1)
        text = "\n\n---\n\n".join(r.text for r in rs[:3])  # top 3 most recent
    else:
        raise typer.BadParameter("kind must be annual | ipo | research")
    if full:
        console.print(text)
    else:
        lines = text.splitlines()
        console.print("\n".join(lines[:head_lines]))
        if len(lines) > head_lines:
            console.print(f"[dim]... ({len(lines) - head_lines} more lines; use --full)[/]")
