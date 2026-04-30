"""Top-level CLI. Exposed as ``ah`` via pyproject.toml [project.scripts]."""

from __future__ import annotations

from pathlib import Path

import typer

from ah_research import __version__

app = typer.Typer(
    name="ah",
    help="ah-research — A-shares + HK stock research platform",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(f"ah-research {__version__}")


@app.command()
def init() -> None:
    """Bootstrap config + cache dir + API keys."""
    from ah_research.scripts.ah_init import run as _run_init

    _run_init()


@app.command()
def doctor() -> None:
    """Run a health check (deps, sources reachable, cache writable)."""
    from ah_research.scripts.ah_doctor import run as _run_doctor

    _run_doctor()


@app.command()
def warmup(
    universe: str = typer.Option("sample", help="'sample' | 'csi300' | 'hsi'"),
    years: int = typer.Option(5, help="How many years of history to pre-fetch"),
) -> None:
    """Pre-fetch data for a universe to warm the cache."""
    from ah_research.scripts.ah_warmup import run as _run_warmup

    _run_warmup(universe=universe, years=years)


def _register_watchlist() -> None:
    from ah_research.scripts.ah_watchlist import app as _wl_app

    app.add_typer(_wl_app, name="watchlist")


def _register_filings() -> None:
    from ah_research.scripts.ah_filings import filings_app
    from ah_research.scripts.ah_profile import profile_app

    app.add_typer(filings_app)
    app.add_typer(profile_app)


def _register_construct() -> None:
    from ah_research.scripts.ah_construct import construct_app

    app.add_typer(construct_app)


_register_watchlist()
_register_filings()
_register_construct()


@app.command()
def dossier(
    symbol: str = typer.Argument(..., help="Symbol e.g. 600000.SH"),
    asof: str = typer.Option(None, "--asof", help="Snapshot date YYYY-MM-DD"),
    out: Path = typer.Option(None, "--out", help="Write markdown to file"),  # noqa: B008
    language: str = typer.Option("en", "--language", help="Report language: en|zh"),
    qualitative: bool = typer.Option(
        True,
        "--qualitative/--no-qualitative",
        help="Include filings + profile sections (default: on).",
    ),
) -> None:
    """Build and print (or save) a company research dossier."""
    from datetime import date, datetime

    from ah_research.scripts.ah_dossier import run as _run_dossier

    asof_d: date | None = None
    if asof is not None:
        asof_d = datetime.strptime(asof, "%Y-%m-%d").date()
    _run_dossier(symbol=symbol, asof=asof_d, out=out, language=language, qualitative=qualitative)
