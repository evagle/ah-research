"""``ah watchlist`` — CRUD and snapshot commands for named watchlists.

Subcommands
-----------
list        Print all watchlists.
create      Create a new watchlist.
snapshot    Capture a point-in-time metrics snapshot.
diff        Show per-metric deltas between two snapshots.
export      Write a watchlist to a YAML file.
import      Load a watchlist from a YAML file.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from ah_research.watchlist.store import WatchlistStore

app = typer.Typer(
    name="watchlist",
    help="Manage named watchlists.",
    no_args_is_help=True,
)


# ── list ──────────────────────────────────────────────────────────────────────


@app.command("list")
def wl_list() -> None:
    """Print all watchlists in the store."""
    store = WatchlistStore()
    watchlists = store.list_all()
    if not watchlists:
        typer.echo("No watchlists found.")
        return
    for wl in watchlists:
        sym_count = len(wl.symbols)
        typer.echo(f"{wl.name}  ({sym_count} symbols)  {wl.description or ''}")


# ── create ────────────────────────────────────────────────────────────────────


@app.command("create")
def wl_create(
    name: str = typer.Argument(..., help="Watchlist name"),
    symbols: str = typer.Option("", "--symbols", help="Comma-separated symbol list"),
    description: str = typer.Option("", "--description", help="Optional description"),
) -> None:
    """Create a new watchlist."""
    sym_list: list[str] = [s.strip() for s in symbols.split(",") if s.strip()]
    store = WatchlistStore()
    wl = store.create(name=name, symbols=sym_list, description=description)  # type: ignore[arg-type]
    typer.echo(f"Created watchlist '{wl.name}' with {len(wl.symbols)} symbols.")


# ── snapshot ──────────────────────────────────────────────────────────────────


@app.command("snapshot")
def wl_snapshot(
    name: str = typer.Argument(..., help="Watchlist name"),
    asof: str = typer.Option(None, "--asof", help="Snapshot date YYYY-MM-DD (default: today)"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing snapshot"),
) -> None:
    """Capture a point-in-time metrics snapshot for a watchlist."""
    from datetime import date

    from ah_research.scripts.ah_dossier import _make_repo

    asof_d = datetime.strptime(asof, "%Y-%m-%d").date() if asof is not None else date.today()
    from ah_research.data.repository import DataRepository

    repo: DataRepository = _make_repo()  # type: ignore[assignment]
    store = WatchlistStore()
    snap = store.snapshot(name, repo, asof=asof_d, force=force)
    typer.echo(f"Snapshot saved: {name} @ {asof_d} ({len(snap.rows)} rows)")


# ── diff ──────────────────────────────────────────────────────────────────────


@app.command("diff")
def wl_diff(
    name: str = typer.Argument(..., help="Watchlist name"),
    earlier: str = typer.Option(..., "--earlier", help="Earlier snapshot date YYYY-MM-DD"),
    later: str = typer.Option(..., "--later", help="Later snapshot date YYYY-MM-DD"),
) -> None:
    """Show per-metric deltas between two snapshots."""
    earlier_d = datetime.strptime(earlier, "%Y-%m-%d").date()
    later_d = datetime.strptime(later, "%Y-%m-%d").date()
    store = WatchlistStore()
    diff = store.diff_snapshots(name, earlier=earlier_d, later=later_d)
    if diff.empty:
        typer.echo("No delta data available.")
        return
    typer.echo(diff.to_string(index=False))


# ── export ────────────────────────────────────────────────────────────────────


@app.command("export")
def wl_export(
    name: str = typer.Argument(..., help="Watchlist name"),
    out: Path = typer.Option(..., "--out", help="Output YAML file path"),  # noqa: B008
) -> None:
    """Export a watchlist to a YAML file."""
    store = WatchlistStore()
    store.export_yaml(name, out)
    typer.echo(f"Exported '{name}' to {out}")


# ── import ────────────────────────────────────────────────────────────────────


@app.command("import")
def wl_import(
    path: Path = typer.Argument(..., help="YAML file to import"),  # noqa: B008
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite if name exists"),
) -> None:
    """Import a watchlist from a YAML file."""
    store = WatchlistStore()
    wl = store.import_yaml(path, overwrite=overwrite)
    typer.echo(f"Imported watchlist '{wl.name}' with {len(wl.symbols)} symbols.")
