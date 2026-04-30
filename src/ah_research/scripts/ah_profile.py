"""`ah profile` Typer sub-app."""

from __future__ import annotations

from datetime import date as date_type
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ah_research.filings.profile_repository import ProfileRepository
from ah_research.filings.types import Profile

profile_app = typer.Typer(name="profile", help="Query value-investing profiles from profiles/")
console = Console()


@profile_app.command("list")
def list_profiles(
    symbol: str | None = typer.Argument(None, help="Optional symbol filter."),
    root: Path = typer.Option(Path("profiles"), help="Profiles root directory."),  # noqa: B008
) -> None:
    repo = ProfileRepository(root=root)
    profiles = repo.list_profiles(symbol) if symbol is not None else repo.list_profiles()
    if not profiles:
        console.print("[yellow]No profiles found[/]")
        raise typer.Exit(code=0)
    table = Table(title="Profiles")
    table.add_column("symbol")
    table.add_column("date")
    table.add_column("n_sections", justify="right")
    table.add_column("path")
    for p in profiles:
        table.add_row(p.symbol, p.date.isoformat(), str(len(p.sections)), str(p.path))
    console.print(table)


@profile_app.command("show")
def show_profile(
    symbol: str = typer.Argument(..., help="Symbol e.g. 600519.SH"),
    date: str | None = typer.Option(None, help="ISO date (YYYY-MM-DD); defaults to latest."),
    section: str | None = typer.Option(None, help="Print only one named section."),
    list_sections: bool = typer.Option(
        False, "--list-sections", help="Print section headers only."
    ),
    root: Path = typer.Option(Path("profiles"), help="Profiles root directory."),  # noqa: B008
) -> None:
    repo = ProfileRepository(root=root)
    profile: Profile
    if date is not None:
        from datetime import date as _date

        y, mo, d = map(int, date.split("-"))
        profile = repo.get(symbol, _date(y, mo, d))
    else:
        maybe = repo.latest(symbol)
        if maybe is None:
            console.print(f"[red]No profile found for {symbol}[/]")
            raise typer.Exit(code=1)
        profile = maybe
    if list_sections:
        for name in profile.sections:
            console.print(f"- {name}")
        return
    if section is not None:
        body = profile.sections.get(section)
        if body is None:
            console.print(
                f"[red]Section {section!r} not in profile "
                f"(available: {list(profile.sections)[:5]}…)[/]"
            )
            raise typer.Exit(code=1)
        console.print(body)
        return
    console.print(profile.text)


def _parse_date(date_str: str) -> date_type:
    y, mo, d = map(int, date_str.split("-"))
    return date_type(y, mo, d)


@profile_app.command("grade")
def grade(
    symbol: str = typer.Argument(..., help="Symbol e.g. 600519.SH"),
    date: str | None = typer.Option(None, help="ISO date (YYYY-MM-DD); defaults to latest."),
    force: bool = typer.Option(False, help="Ignore cache and re-grade."),
    model: str = typer.Option("claude-sonnet-4-6", help="Model ID."),
    root: Path = typer.Option(Path("profiles"), help="Profiles root."),  # noqa: B008
) -> None:
    """Grade a profile via the Claude API into structured fields."""
    from anthropic import Anthropic

    from ah_research.filings.grading import ProfileGrader

    repo = ProfileRepository(root=root)
    profile = repo.latest(symbol) if date is None else repo.get(symbol, _parse_date(date))
    if profile is None:
        console.print(f"[red]No profile for {symbol}[/]")
        raise typer.Exit(code=1)

    client = Anthropic()
    grader = ProfileGrader(client, model=model)
    result = grader.grade(profile, force=force)

    table = Table(title=f"Grade: {symbol}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("moat_grade", result.moat_grade)
    table.add_row("mgmt_grade", result.mgmt_grade)
    table.add_row("redflag_count", str(result.redflag_count))
    table.add_row("confidence", f"{result.confidence:.2f}")
    table.add_row("model", result.model)
    table.add_row("content_hash", result.content_hash[:16] + "...")
    console.print(table)
    console.print("\n[bold]Rationale:[/bold]")
    console.print(result.rationale)
