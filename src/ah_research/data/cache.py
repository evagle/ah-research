"""DuckDB-backed cache. One file, schema-migrated, atomic writes.

Design:
- **Single file, single connection.** DuckDB supports multiple readers but
  we serialize through one instance per process; callers treat the cache as
  a lightweight service, not a threadsafe datastore.
- **Migrations are files, not code.** Numbered ``.sql`` files in the
  ``migrations/`` folder are applied in order on ``__init__``. Statements
  are idempotent (``CREATE TABLE IF NOT EXISTS``, ``INSERT OR IGNORE``) so
  reopening a cache is safe.
- **Upserts via DELETE + INSERT.** DuckDB supports ``INSERT OR REPLACE`` in
  newer versions but we use the DELETE + INSERT pattern for portability and
  clarity. All writes are idempotent on their natural key.
- **PIT reads for bitemporal / versioned entities.** ``read_fundamentals_asof``
  and ``read_constituents_asof`` filter with ``known_as_of <= asof`` /
  ``effective_from <= asof < effective_to`` respectively, then dedupe to one
  row per natural key (preferring later-known rows for restatements).

See spec §3 "Cache" and §10 data-layer contract.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import TracebackType
from typing import Self

import duckdb
import pandas as pd

from ah_research.exceptions import DataIntegrityError
from ah_research.logging import get_logger

log = get_logger(__name__)

_MIGRATIONS_DIR: Path = Path(__file__).parent / "migrations"


class DuckDBCache:
    """DuckDB-backed cache. Supports ``with`` for explicit cleanup."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(path))
        self._apply_migrations()

    def close(self) -> None:
        """Close the underlying DuckDB connection. Idempotent."""
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ── migrations & introspection ─────────────────────────────────────────

    def _apply_migrations(self) -> None:
        files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        for sql_file in files:
            self._conn.execute(sql_file.read_text())
        log.info("cache_migrations_applied", path=str(self.path), count=len(files))

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is None:
            raise DataIntegrityError("meta.schema_version missing — cache corrupted")
        return int(row[0])

    def list_tables(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        return [r[0] for r in rows]

    # ── prices ─────────────────────────────────────────────────────────────

    def write_prices(self, df: pd.DataFrame) -> None:
        """Upsert ``(date, symbol)`` rows. Idempotent. Transactional."""
        self._upsert("prices", ["date", "symbol"], df)

    def read_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return all cached price rows for ``symbols`` within ``[start, end]``
        inclusive, ordered by ``(symbol, date)``."""
        result: pd.DataFrame = self._conn.execute(
            "SELECT * FROM prices "
            "WHERE symbol = ANY(?) "
            "AND date BETWEEN ? AND ? "
            "ORDER BY symbol, date",
            [symbols, start, end],
        ).fetchdf()
        return result

    def price_coverage(self, symbol: str) -> tuple[date, date] | None:
        """Return ``(min_date, max_date)`` cached for ``symbol``, or ``None``
        if the symbol has no rows. Informational only — do not use to decide
        whether to refetch, since data dates (trading days) are narrower than
        request ranges (calendar days). Use ``has_price_fetch_covering``."""
        row = self._conn.execute(
            "SELECT MIN(date), MAX(date) FROM prices WHERE symbol = ?",
            [symbol],
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return row[0], row[1]

    def log_price_fetch(self, symbol: str, start: date, end: date) -> None:
        """Record that ``[start, end]`` has been fetched for ``symbol``.
        Called by the repository after a successful upstream fetch + write.
        Idempotent on (symbol, start, end)."""
        self._conn.execute(
            "INSERT OR IGNORE INTO price_fetch_log (symbol, fetched_start, fetched_end) "
            "VALUES (?, ?, ?)",
            [symbol, start, end],
        )

    def has_price_fetch_covering(self, symbol: str, start: date, end: date) -> bool:
        """True iff any logged fetch for ``symbol`` spans ``[start, end]``.

        v1 checks for a single row covering the range. A later optimisation
        could union multiple rows to reason about fragmented fetches.
        """
        row = self._conn.execute(
            "SELECT 1 FROM price_fetch_log "
            "WHERE symbol = ? AND fetched_start <= ? AND fetched_end >= ? "
            "LIMIT 1",
            [symbol, start, end],
        ).fetchone()
        return row is not None

    # ── fundamentals (bitemporal, PIT-aware reads) ─────────────────────────

    def write_fundamentals(self, df: pd.DataFrame) -> None:
        """Upsert on (symbol, report_date, known_as_of, statement_kind)."""
        self._upsert(
            "fundamentals",
            ["symbol", "report_date", "known_as_of", "statement_kind"],
            df,
        )

    def log_fundamentals_fetch(self, symbol: str, start: date, end: date) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO fundamentals_fetch_log "
            "(symbol, fetched_start, fetched_end) VALUES (?, ?, ?)",
            [symbol, start, end],
        )

    def has_fundamentals_fetch_covering(self, symbol: str, start: date, end: date) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM fundamentals_fetch_log "
            "WHERE symbol = ? AND fetched_start <= ? AND fetched_end >= ? "
            "LIMIT 1",
            [symbol, start, end],
        ).fetchone()
        return row is not None

    def read_fundamentals_asof(
        self,
        symbols: list[str],
        asof: date,
    ) -> pd.DataFrame:
        """Return the PIT-correct fundamentals snapshot at ``asof``.

        A row is included iff ``publication_date <= asof AND known_as_of <= asof``.
        For each ``(symbol, report_date)`` we pick the **most recent** row by
        ``known_as_of`` (so restated figures win once they're published), with
        ``statement_kind`` precedence ``restated > audited > preliminary`` as
        a tiebreak when two rows share the same ``known_as_of``.
        """
        result: pd.DataFrame = self._conn.execute(
            """
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol, report_date
                    ORDER BY
                        known_as_of DESC,
                        CASE statement_kind
                            WHEN 'restated' THEN 3
                            WHEN 'audited' THEN 2
                            WHEN 'preliminary' THEN 1
                            ELSE 0
                        END DESC
                ) AS _rn
                FROM fundamentals
                WHERE symbol = ANY(?)
                  AND publication_date <= ?
                  AND known_as_of <= ?
            )
            WHERE _rn = 1
            ORDER BY symbol, report_date
            """,
            [symbols, asof, asof],
        ).fetchdf()
        if "_rn" in result.columns:
            result = result.drop(columns=["_rn"])
        return result

    # ── index constituents (PIT) ───────────────────────────────────────────

    def write_constituents(self, df: pd.DataFrame) -> None:
        """Upsert on (index_name, symbol, effective_from).

        Caller passes a DataFrame with columns matching the table schema;
        ``effective_to`` may be ``NaT`` / ``None`` for open-ended memberships.
        """
        self._upsert(
            "index_constituents",
            ["index_name", "symbol", "effective_from"],
            df,
        )

    def log_constituents_fetch(self, index_name: str, asof: date) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO constituents_fetch_log (index_name, fetched_asof) VALUES (?, ?)",
            [index_name, asof],
        )

    def has_constituents_fetch(self, index_name: str, asof: date) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM constituents_fetch_log "
            "WHERE index_name = ? AND fetched_asof = ? LIMIT 1",
            [index_name, asof],
        ).fetchone()
        return row is not None

    def read_constituents_asof(
        self,
        index_name: str,
        asof: date,
    ) -> pd.DataFrame:
        """Return members of ``index_name`` that were active at ``asof``.

        A row is active iff ``effective_from <= asof AND
        (effective_to IS NULL OR effective_to > asof)``.
        """
        result: pd.DataFrame = self._conn.execute(
            """
            SELECT * FROM index_constituents
            WHERE index_name = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            ORDER BY symbol
            """,
            [index_name, asof, asof],
        ).fetchdf()
        return result

    # ── trading calendar ───────────────────────────────────────────────────

    def write_calendar(self, df: pd.DataFrame) -> None:
        """Upsert on (exchange, date)."""
        self._upsert("calendars", ["exchange", "date"], df)

    def read_calendar(
        self,
        exchange: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        result: pd.DataFrame = self._conn.execute(
            "SELECT * FROM calendars WHERE exchange = ? AND date BETWEEN ? AND ? ORDER BY date",
            [exchange, start, end],
        ).fetchdf()
        return result

    # ── FX rates ───────────────────────────────────────────────────────────

    def write_fx(self, df: pd.DataFrame) -> None:
        """Upsert on (date, pair)."""
        self._upsert("fx_rates", ["date", "pair"], df)

    def read_fx(
        self,
        pair: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        result: pd.DataFrame = self._conn.execute(
            "SELECT * FROM fx_rates WHERE pair = ? AND date BETWEEN ? AND ? ORDER BY date",
            [pair, start, end],
        ).fetchdf()
        return result

    # ── sector classification ──────────────────────────────────────────────

    def write_sectors(self, df: pd.DataFrame) -> None:
        """Upsert on (symbol). One sector per symbol."""
        self._upsert("sectors", ["symbol"], df)

    def read_sectors(self, symbols: list[str]) -> pd.DataFrame:
        result: pd.DataFrame = self._conn.execute(
            "SELECT * FROM sectors WHERE symbol = ANY(?) ORDER BY symbol",
            [symbols],
        ).fetchdf()
        return result

    # ── corporate actions ──────────────────────────────────────────────────

    def write_corporate_actions(self, df: pd.DataFrame) -> None:
        """Upsert on (symbol, ex_date, kind)."""
        self._upsert("corporate_actions", ["symbol", "ex_date", "kind"], df)

    def read_corporate_actions(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        result: pd.DataFrame = self._conn.execute(
            "SELECT * FROM corporate_actions "
            "WHERE symbol = ANY(?) AND ex_date BETWEEN ? AND ? "
            "ORDER BY symbol, ex_date",
            [symbols, start, end],
        ).fetchdf()
        return result

    # ── internal ───────────────────────────────────────────────────────────

    def _upsert(self, table: str, key_cols: list[str], df: pd.DataFrame) -> None:
        """Transactional upsert: DELETE existing rows whose key matches,
        then INSERT new rows. No-op on empty input.

        ``table`` and ``key_cols`` are interpolated into SQL — callers must
        only pass trusted literals. This is private; all public writers
        pass hard-coded strings.
        """
        if len(df) == 0:
            return
        key_expr = ", ".join(key_cols)
        # Explicit column list ensures df columns map to table columns BY NAME,
        # not by position. Without this, a df whose columns are in a different
        # order than the table silently writes values into the wrong columns.
        cols = list(df.columns)
        cols_expr = ", ".join(cols)
        self._conn.register("df", df)
        try:
            self._conn.execute("BEGIN TRANSACTION")
            self._conn.execute(
                f"DELETE FROM {table} WHERE ({key_expr}) IN (SELECT {key_expr} FROM df)"
            )
            self._conn.execute(f"INSERT INTO {table} ({cols_expr}) SELECT {cols_expr} FROM df")
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        finally:
            self._conn.unregister("df")
