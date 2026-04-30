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
    """Build a DataRepository from the default cache.  Extracted for test mocking."""
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


def run(
    symbol: str,
    asof: date | None = None,
    out: Path | None = None,
    language: str = "en",
) -> None:
    """Core logic — separated so tests can call it directly."""
    repo = _make_repo()
    asof_d = asof or date.today()
    dossier = build_dossier(symbol, repo, asof=asof_d)
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
) -> None:
    """Build and print (or save) a company research dossier."""
    asof_d: date | None = None
    if asof is not None:
        asof_d = datetime.strptime(asof, "%Y-%m-%d").date()
    run(symbol=symbol, asof=asof_d, out=out, language=language)
