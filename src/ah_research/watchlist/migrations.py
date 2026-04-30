"""Migration #3 — watchlist tables.

The SQL is applied by DuckDB cache via data/migrations/0003_watchlist.sql.
This module exposes constants used by WatchlistStore for standalone usage
(i.e. when WatchlistStore is given an arbitrary path, not the main cache).
"""

from __future__ import annotations

WATCHLIST_TABLE_PREFIX = "watchlist_"

# Standalone DDL executed by WatchlistStore._ensure_migrated() when called
# with an arbitrary DuckDB path (not the main DuckDBCache which already runs
# all migration files).  Idempotent.
MIGRATION_SQL = """\
CREATE TABLE IF NOT EXISTS watchlist_definitions (
    name              VARCHAR PRIMARY KEY,
    description       VARCHAR,
    symbols           JSON NOT NULL,
    screen_conditions JSON,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_snapshots (
    watchlist_name VARCHAR NOT NULL,
    snapshot_date  DATE NOT NULL,
    symbol         VARCHAR NOT NULL,
    metrics        JSON NOT NULL,
    PRIMARY KEY (watchlist_name, snapshot_date, symbol)
);
"""
