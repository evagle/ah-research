"""Top-level CLI. Exposed as ``ah`` via pyproject.toml [project.scripts]."""

from __future__ import annotations

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
