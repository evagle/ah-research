-- Migration #3 — watchlist tables.
-- Managed by data/cache.py. Idempotent (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS watchlist_definitions (
    name             VARCHAR PRIMARY KEY,
    description      VARCHAR,
    symbols          JSON NOT NULL,
    screen_conditions JSON,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_snapshots (
    watchlist_name VARCHAR NOT NULL,
    snapshot_date  DATE NOT NULL,
    symbol         VARCHAR NOT NULL,
    metrics        JSON NOT NULL,
    PRIMARY KEY (watchlist_name, snapshot_date, symbol)
);

UPDATE meta SET value = '3' WHERE key = 'schema_version';
