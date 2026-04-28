-- Fetch logs for non-price entities. Same pattern as price_fetch_log
-- (tracks REQUEST ranges, not data dates, so we don't confuse calendar/
-- trading/publication day alignment).

CREATE TABLE IF NOT EXISTS fundamentals_fetch_log (
    symbol        VARCHAR NOT NULL,
    fetched_start DATE NOT NULL,
    fetched_end   DATE NOT NULL,
    PRIMARY KEY (symbol, fetched_start, fetched_end)
);

CREATE TABLE IF NOT EXISTS constituents_fetch_log (
    index_name    VARCHAR NOT NULL,
    fetched_asof  DATE NOT NULL,
    PRIMARY KEY (index_name, fetched_asof)
);

UPDATE meta SET value = '2' WHERE key = 'schema_version';
