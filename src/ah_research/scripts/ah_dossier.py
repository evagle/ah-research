"""``ah dossier <symbol>`` — build and print/save a company dossier.

Flags
-----
--asof      YYYY-MM-DD snapshot date (default: today)
--out       path.md   write markdown to file instead of stdout
--language  en|zh     report language (default: en)
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import typer

from ah_research.analysis.dossier import build_dossier

app = typer.Typer(name="dossier", help="Build a company research dossier.", no_args_is_help=True)


def _make_repo() -> object:
    """Build a DataRepository from the default cache. Extracted for test mocking.

    Implementation in ah_research.scripts._factories; kept here as a thin
    passthrough so tests that patch ``ah_research.scripts.ah_dossier._make_repo``
    keep working.
    """
    from ah_research.scripts._factories import make_repo

    return make_repo()


def run(
    symbol: str,
    asof: date | None = None,
    out: Path | None = None,
    language: str = "en",
    qualitative: bool = True,
) -> None:
    """Core logic — separated so tests can call it directly."""
    repo = _make_repo()
    asof_d = asof or date.today()
    dossier = build_dossier(symbol, repo, asof=asof_d, include_qualitative=qualitative)
    md = dossier.to_markdown(language=language)
    if out is not None:
        out.write_text(md)
        typer.echo(f"Dossier written to {out}")
    else:
        typer.echo(md)


@app.command()
def dossier_cmd(
    symbol: str = typer.Argument(..., help="Symbol in exchange-qualified form, e.g. 600000.SH"),
    asof: str = typer.Option(None, "--asof", help="Snapshot date YYYY-MM-DD (default: today)"),
    out: Path = typer.Option(None, "--out", help="Write markdown to this file path"),  # noqa: B008
    language: str = typer.Option("en", "--language", help="Report language: en|zh"),
    qualitative: bool = typer.Option(
        True,
        "--qualitative/--no-qualitative",
        help="Include filings + profile sections (default: on).",
    ),
) -> None:
    """Build and print (or save) a company research dossier."""
    asof_d: date | None = None
    if asof is not None:
        asof_d = datetime.strptime(asof, "%Y-%m-%d").date()
    run(symbol=symbol, asof=asof_d, out=out, language=language, qualitative=qualitative)
