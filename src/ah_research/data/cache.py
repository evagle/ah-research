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
  clarity. All price writes are idempotent on ``(date, symbol)``.

See spec §3 "Cache" and §10 data-layer contract. Entities beyond prices
land in Tasks 1.6 through 1.9.
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
        """Upsert (date, symbol) rows. Idempotent. Transactional."""
        if len(df) == 0:
            return
        self._conn.register("df", df)
        try:
            self._conn.execute("BEGIN TRANSACTION")
            self._conn.execute(
                "DELETE FROM prices WHERE (date, symbol) IN (SELECT date, symbol FROM df)"
            )
            self._conn.execute("INSERT INTO prices SELECT * FROM df")
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        finally:
            self._conn.unregister("df")

    def read_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return all cached price rows for ``symbols`` within ``[start, end]``
        inclusive, ordered by (symbol, date)."""
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
        if the symbol has no rows. Used by the repository to decide what
        date slice to fetch from upstream."""
        row = self._conn.execute(
            "SELECT MIN(date), MAX(date) FROM prices WHERE symbol = ?",
            [symbol],
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return row[0], row[1]
