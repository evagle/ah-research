"""CRUD and YAML interop over DuckDB watchlist tables."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
import pandas as pd
import yaml

from ah_research.model.types import Symbol, parse_symbol

if TYPE_CHECKING:
    from ah_research.data.repository import DataRepository
    from ah_research.watchlist.snapshot import WatchlistSnapshot


@dataclass(frozen=True)
class Watchlist:
    """Immutable snapshot of a watchlist definition row."""

    name: str
    description: str | None
    symbols: list[Symbol]
    screen_conditions: dict | None  # type: ignore[type-arg]
    created_at: pd.Timestamp
    updated_at: pd.Timestamp


class WatchlistStore:
    """DuckDB-backed store for named watchlists and their snapshots.

    Parameters
    ----------
    cache_path:
        Path to the DuckDB file.  If *None*, falls back to the project's
        default cache path from ``get_settings()``.
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        if cache_path is None:
            from ah_research.config import get_settings

            cache_path = get_settings().cache_dir / "cache.duckdb"
        self.cache_path = cache_path
        self._ensure_migrated()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _ensure_migrated(self) -> None:
        from ah_research.watchlist.migrations import MIGRATION_SQL

        with duckdb.connect(str(self.cache_path)) as con:
            con.execute(MIGRATION_SQL)

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.cache_path))

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        symbols: list[str | Symbol],
        description: str = "",
        screen_conditions: dict | None = None,  # type: ignore[type-arg]
    ) -> Watchlist:
        """Create a new watchlist.  Raises ValueError if name already exists."""
        with self._conn() as con:
            exists = con.execute(
                "SELECT 1 FROM watchlist_definitions WHERE name = ?", [name]
            ).fetchone()
            if exists is not None:
                raise ValueError(f"Watchlist {name!r} already exists")
            sym_strings = [s if isinstance(s, str) else str(s) for s in symbols]
            con.execute(
                "INSERT INTO watchlist_definitions "
                "  (name, description, symbols, screen_conditions) "
                "VALUES (?, ?, ?, ?)",
                [
                    name,
                    description,
                    json.dumps(sym_strings),
                    json.dumps(screen_conditions) if screen_conditions else None,
                ],
            )
        return self.get(name)

    def get(self, name: str) -> Watchlist:
        """Fetch a watchlist by name.  Raises KeyError if not found."""
        with self._conn() as con:
            row = con.execute(
                "SELECT name, description, symbols, screen_conditions, "
                "       created_at, updated_at "
                "FROM watchlist_definitions WHERE name = ?",
                [name],
            ).fetchone()
        if row is None:
            raise KeyError(name)
        return Watchlist(
            name=row[0],
            description=row[1],
            symbols=[parse_symbol(s) for s in json.loads(row[2])],
            screen_conditions=json.loads(row[3]) if row[3] else None,
            created_at=pd.Timestamp(row[4]),
            updated_at=pd.Timestamp(row[5]),
        )

    def list_all(self) -> list[Watchlist]:
        """Return all watchlists in the store."""
        with self._conn() as con:
            rows = con.execute("SELECT name FROM watchlist_definitions ORDER BY name").fetchall()
        return [self.get(r[0]) for r in rows]

    def update(
        self,
        name: str,
        *,
        symbols: list[str | Symbol] | None = None,
        description: str | None = None,
        screen_conditions: dict | None = None,  # type: ignore[type-arg]
    ) -> Watchlist:
        """Update selected fields of an existing watchlist."""
        wl = self.get(name)  # raises KeyError if not found
        new_syms: list[str] = [str(s) for s in wl.symbols]
        new_desc: str | None = wl.description
        new_sc: dict | None = wl.screen_conditions  # type: ignore[type-arg]

        if symbols is not None:
            new_syms = [s if isinstance(s, str) else str(s) for s in symbols]
        if description is not None:
            new_desc = description
        if screen_conditions is not None:
            new_sc = screen_conditions

        with self._conn() as con:
            con.execute(
                "UPDATE watchlist_definitions "
                "SET symbols = ?, description = ?, screen_conditions = ?, "
                "    updated_at = CURRENT_TIMESTAMP "
                "WHERE name = ?",
                [
                    json.dumps(new_syms),
                    new_desc,
                    json.dumps(new_sc) if new_sc else None,
                    name,
                ],
            )
        return self.get(name)

    def add_symbol(self, name: str, symbol: str | Symbol) -> Watchlist:
        """Add a symbol to a watchlist (idempotent)."""
        wl = self.get(name)
        sym_str = symbol if isinstance(symbol, str) else str(symbol)
        existing = {str(s) for s in wl.symbols}
        new_syms = sorted(existing | {sym_str})
        with self._conn() as con:
            con.execute(
                "UPDATE watchlist_definitions "
                "SET symbols = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE name = ?",
                [json.dumps(new_syms), name],
            )
        return self.get(name)

    def remove_symbol(self, name: str, symbol: str | Symbol) -> Watchlist:
        """Remove a symbol from a watchlist.  No-op if not present."""
        wl = self.get(name)
        sym_str = symbol if isinstance(symbol, str) else str(symbol)
        new_syms = sorted({str(s) for s in wl.symbols} - {sym_str})
        with self._conn() as con:
            con.execute(
                "UPDATE watchlist_definitions "
                "SET symbols = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE name = ?",
                [json.dumps(new_syms), name],
            )
        return self.get(name)

    def delete(self, name: str) -> None:
        """Delete a watchlist and all its snapshots."""
        with self._conn() as con:
            con.execute("DELETE FROM watchlist_snapshots WHERE watchlist_name = ?", [name])
            con.execute("DELETE FROM watchlist_definitions WHERE name = ?", [name])

    # ── YAML interop ──────────────────────────────────────────────────────────

    def export_yaml(self, name: str, path: Path) -> None:
        """Serialise the watchlist definition to a YAML file."""
        wl = self.get(name)
        payload = {
            "name": wl.name,
            "description": wl.description,
            "symbols": [str(s) for s in wl.symbols],
            "screen_conditions": wl.screen_conditions,
        }
        path.write_text(yaml.safe_dump(payload, allow_unicode=True))

    def import_yaml(self, path: Path, overwrite: bool = False) -> Watchlist:
        """Load a watchlist from a YAML file exported by ``export_yaml``."""
        payload: dict[str, Any] = yaml.safe_load(path.read_text())
        if overwrite:
            with contextlib.suppress(KeyError):
                self.delete(payload["name"])
        return self.create(
            name=payload["name"],
            symbols=payload.get("symbols", []),
            description=payload.get("description") or "",
            screen_conditions=payload.get("screen_conditions"),
        )

    # ── snapshot methods (implemented in Task 14) ──────────────────────────────

    def snapshot(
        self,
        name: str,
        repo: DataRepository,
        *,
        asof: date,
        force: bool = False,
    ) -> WatchlistSnapshot:
        """Capture a point-in-time snapshot of the watchlist metrics.

        Parameters
        ----------
        name:   Watchlist name.
        repo:   DataRepository used to fetch prices + fundamentals.
        asof:   The date for which metrics are fetched.
        force:  If True, overwrite an existing snapshot for the same
                (name, asof). Otherwise raises ValueError.
        """

        wl = self.get(name)
        sym_strings = [str(s) for s in wl.symbols]

        # Immutability guard
        with self._conn() as con:
            existing = con.execute(
                "SELECT 1 FROM watchlist_snapshots WHERE watchlist_name = ? AND snapshot_date = ?",
                [name, asof],
            ).fetchone()
        if existing is not None:
            if not force:
                raise ValueError(
                    f"Snapshot for watchlist {name!r} on {asof} already exists. "
                    "Pass force=True to overwrite."
                )
            # Delete old rows so we can reinsert
            with self._conn() as con:
                con.execute(
                    "DELETE FROM watchlist_snapshots "
                    "WHERE watchlist_name = ? AND snapshot_date = ?",
                    [name, asof],
                )

        rows = _collect_metrics(sym_strings, repo, asof)

        # Persist to DB
        with self._conn() as con:
            for sym_str, metrics in rows.items():
                con.execute(
                    "INSERT INTO watchlist_snapshots "
                    "  (watchlist_name, snapshot_date, symbol, metrics) "
                    "VALUES (?, ?, ?, ?)",
                    [name, asof, sym_str, json.dumps(metrics)],
                )

        return self.get_snapshot(name, asof)

    def list_snapshots(self, name: str) -> list[date]:
        """Return sorted list of snapshot dates for a watchlist."""
        with self._conn() as con:
            rows = con.execute(
                "SELECT DISTINCT snapshot_date FROM watchlist_snapshots "
                "WHERE watchlist_name = ? ORDER BY snapshot_date",
                [name],
            ).fetchall()
        return [row[0] for row in rows]

    def get_snapshot(self, name: str, asof: date) -> WatchlistSnapshot:
        """Retrieve a previously stored snapshot.

        Raises KeyError if (name, asof) has no snapshot.
        """
        from ah_research.watchlist.snapshot import WatchlistSnapshot

        with self._conn() as con:
            rows = con.execute(
                "SELECT symbol, metrics FROM watchlist_snapshots "
                "WHERE watchlist_name = ? AND snapshot_date = ?",
                [name, asof],
            ).fetchall()
        if not rows:
            raise KeyError(f"No snapshot for watchlist {name!r} on {asof}")

        records = []
        for sym_str, metrics_json in rows:
            m: dict[str, Any] = json.loads(metrics_json)
            m["symbol"] = sym_str
            records.append(m)

        df = pd.DataFrame(records)
        return WatchlistSnapshot(
            watchlist_name=name,
            snapshot_date=asof,
            rows=df,
        )

    def diff_snapshots(
        self,
        name: str,
        *,
        earlier: date,
        later: date,
    ) -> pd.DataFrame:
        """Compute per-metric deltas between two snapshots.

        Returns a DataFrame indexed by symbol with ``<metric>_delta`` columns
        for every numeric metric that appears in both snapshots.
        """
        snap_early = self.get_snapshot(name, earlier)
        snap_late = self.get_snapshot(name, later)

        e = snap_early.rows.copy()
        l = snap_late.rows.copy()  # noqa: E741

        merged = e.merge(l, on="symbol", suffixes=("_early", "_late"))

        numeric_cols_early = [
            c.removesuffix("_early")
            for c in merged.columns
            if c.endswith("_early") and pd.api.types.is_numeric_dtype(merged[c])
        ]

        result: pd.DataFrame = merged[["symbol"]].copy()
        for col in numeric_cols_early:
            late_col = f"{col}_late"
            early_col = f"{col}_early"
            if late_col in merged.columns and early_col in merged.columns:
                result[f"{col}_delta"] = merged[late_col] - merged[early_col]

        return result


# ── helpers ──────────────────────────────────────────────────────────────────


def _collect_metrics(
    sym_strings: list[str],
    repo: DataRepository,
    asof: date,
) -> dict[str, dict[str, Any]]:
    """Fetch per-symbol metrics (pe, pb, dividend_yield, roe, market_cap,
    sector_l1, price) for all symbols and return as {sym_str: metrics_dict}."""
    result: dict[str, dict[str, Any]] = {s: {} for s in sym_strings}

    # Prices
    try:
        prices = repo.get_prices(sym_strings, start=asof, end=asof)
        for sym in sym_strings:
            sub = prices[prices["symbol"] == sym]
            if not sub.empty:
                result[sym]["price"] = float(sub["close_hfq"].iloc[-1])
    except Exception:
        pass

    # Fundamentals
    try:
        funds = repo.get_fundamentals(sym_strings, start=asof, end=asof, asof=asof)
        for sym in sym_strings:
            sub = funds[funds["symbol"] == sym]
            if not sub.empty:
                row = sub.iloc[-1]
                for col in ("pe", "pb", "dividend_yield", "roe", "market_cap"):
                    if col in row.index and pd.notna(row[col]):
                        result[sym][col] = float(row[col])
    except Exception:
        pass

    # Sectors
    try:
        sectors = repo.get_sector(sym_strings)
        for sym in sym_strings:
            sub = sectors[sectors["symbol"] == sym]
            if not sub.empty and "sector_l1" in sub.columns:
                result[sym]["sector_l1"] = str(sub["sector_l1"].iloc[0])
    except Exception:
        pass

    return result
