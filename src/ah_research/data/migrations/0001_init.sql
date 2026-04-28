-- ah-research cache schema v1.
-- Managed by data/cache.py. Never edit historical migrations in-place — add a
-- new numbered file instead so every cache can replay the upgrade path.

CREATE TABLE IF NOT EXISTS meta (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);

INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS prices (
    date           DATE NOT NULL,
    symbol         VARCHAR NOT NULL,
    open           DOUBLE,
    high           DOUBLE,
    low            DOUBLE,
    close          DOUBLE,
    close_hfq      DOUBLE,
    total_return   DOUBLE,
    volume         BIGINT,
    amount         DOUBLE,
    turnover       DOUBLE,
    is_suspended   BOOLEAN,
    is_st          BOOLEAN,
    limit_up       DOUBLE,
    limit_down     DOUBLE,
    hit_limit_up   BOOLEAN,
    hit_limit_down BOOLEAN,
    PRIMARY KEY (date, symbol)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol                     VARCHAR NOT NULL,
    report_date                DATE NOT NULL,
    publication_date           DATE NOT NULL,
    known_as_of                DATE NOT NULL,
    statement_kind             VARCHAR NOT NULL,
    revenue                    DOUBLE,
    net_income                 DOUBLE,
    net_income_ex_nonrecurring DOUBLE,
    operating_cash_flow        DOUBLE,
    capex                      DOUBLE,
    total_assets               DOUBLE,
    total_equity               DOUBLE,
    total_debt                 DOUBLE,
    goodwill                   DOUBLE,
    minority_interest          DOUBLE,
    d_and_a                    DOUBLE,
    working_capital_change     DOUBLE,
    pe                         DOUBLE,
    pb                         DOUBLE,
    ps                         DOUBLE,
    ev_ebitda                  DOUBLE,
    roe                        DOUBLE,
    roic                       DOUBLE,
    roa                        DOUBLE,
    gross_margin               DOUBLE,
    net_margin                 DOUBLE,
    dividend_yield             DOUBLE,
    market_cap                 DOUBLE,
    market_cap_free_float      DOUBLE,
    is_soe                     BOOLEAN,
    is_stock_connect_eligible  BOOLEAN,
    PRIMARY KEY (symbol, report_date, known_as_of, statement_kind)
);

CREATE TABLE IF NOT EXISTS index_constituents (
    index_name     VARCHAR NOT NULL,
    symbol         VARCHAR NOT NULL,
    weight         DOUBLE,
    effective_from DATE NOT NULL,
    effective_to   DATE,
    PRIMARY KEY (index_name, symbol, effective_from)
);

CREATE TABLE IF NOT EXISTS calendars (
    exchange        VARCHAR NOT NULL,
    date            DATE NOT NULL,
    is_trading_day  BOOLEAN NOT NULL,
    PRIMARY KEY (exchange, date)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    date DATE NOT NULL,
    pair VARCHAR NOT NULL,
    rate DOUBLE NOT NULL,
    PRIMARY KEY (date, pair)
);

CREATE TABLE IF NOT EXISTS sectors (
    symbol    VARCHAR PRIMARY KEY,
    sector_l1 VARCHAR,
    sector_l2 VARCHAR
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol      VARCHAR NOT NULL,
    ex_date     DATE NOT NULL,
    kind        VARCHAR NOT NULL,
    params_json VARCHAR NOT NULL,
    PRIMARY KEY (symbol, ex_date, kind)
);

CREATE INDEX IF NOT EXISTS idx_prices_symbol_date ON prices (symbol, date);
CREATE INDEX IF NOT EXISTS idx_fundamentals_symbol_pub ON fundamentals (symbol, publication_date);
CREATE INDEX IF NOT EXISTS idx_index_constituents_asof ON index_constituents (index_name, effective_from, effective_to);
