# ah-research — Platform Design

**Date:** 2026-04-28
**Status:** Validated design (v2 after expert critique), ready for implementation planning
**Owner:** Brian Huang
**Reviewers:** self + three expert role-plays (quant/value, UX, principal engineer) — critiques accepted and incorporated

## 0. Revision notes

v2 incorporates findings from three expert critiques:
- **Quant/value:** survivorship bias, back-adjusted/total-return series, T+1 settlement, price-limit/ST handling, bitemporal fundamentals, sector neutralization, total-return benchmarks, raw financial line items.
- **UX:** `ah init` / `ah doctor` onboarding, kernel-state visibility, reasoning trail, session-as-durable-artifact, CN color convention, watchlists.
- **Principal engineer:** DuckDB cache (replace Parquet-per-file), `pandera` schemas at boundaries, `Protocol`-based integration DI, exception hierarchy, concurrency story, pyproject extras, property-based tests over coverage.

Killed: `Issuer` synthetic ID, artifact-by-reference broker, `DualMomentum` sample strategy, three-way `align=` parameter, `max_weight_per_sector` (replaced by real sector support, not a stub).

## 1. Purpose & Scope

`ah-research` is a personal stock-research platform focused on A-shares (Shanghai / Shenzhen) and Hong Kong listings, with first-class treatment of AH dual-listings. It is **not** a trading system. Its purpose is fundamental analysis and daily/weekly/monthly trading-data research, with an emphasis on long-term value investing.

### Key correctness principles (non-negotiable)

These govern every design decision below:

1. **Point-in-time everywhere** — universes (index constituents), fundamentals (bitemporal: `report_date`, `publication_date`, `known_as_of`), and prices (back-adjusted so historical values are stable under new corporate actions).
2. **Survivorship-free universes** — historical index constituents drive historical fetches, so delisted / absorbed / removed names are in the cache.
3. **Back-adjusted / total-return default** — price series default to back-adjusted (`hfq`); benchmarks default to total-return index (CSI 300 TR, HSI TR, HSCEI TR).
4. **Tradability-aware** — price-limit (涨跌停), ST/*ST flags, trading halts, and T+1 (A-shares) / T+2 (HK) settlement are modeled in the backtest engine.
5. **Sector-aware by default** — factor research is sector-neutralized by default because A-shares CSI 300 is ~35% financials and otherwise every value factor becomes a short-banks bet.

### In scope (v1)

- Daily bars as the primitive; weekly/monthly derived by resampling.
- Price/volume + **raw financial statement line items** + AH-pair linkage + PIT index constituents + sector tags (SWS from AKshare) + corporate actions + trading-halt/ST/price-limit flags.
- Vectorized backtesting (daily/weekly/monthly rebalance) with **T+1 / T+2 settlement, price-limit-aware fills, dividend-reinvestment policy, time-varying cost tables**.
- Factor research: IC (with Newey-West std errors), quantile analysis, cross-sectional factor studies with sector-neutralization default on.
- Portfolio construction: equal-weight / market-cap (free-float-adjusted) / risk-parity + caps.
- Strategy verification: walk-forward, param sensitivity, cost sensitivity, **leakage canary**.
- Value-investor tooling: fundamental screens, company dossier, owner-earnings / FCF trajectory, valuation-band plotter, dividend consistency, **watchlist**.
- Three AI-UI surfaces over a shared tool registry: `ah.ask()` notebook helper, a Streamlit chat UI attached to a live Jupyter kernel with **session management, reasoning trail, and kernel-state panel**, and an MCP server (deferred / optional).
- **Onboarding commands:** `ah init` (bootstrap config + cache + keys), `ah doctor` (health check), `ah warmup` (sample data pre-fetch).

### Out of scope (v1)

- Real-time or intraday trading; order execution.
- Intraday bars.
- Multi-factor regression models (Fama-Macbeth, Barra-style).
- Optimization-based portfolio construction (CVXPY).
- Options and derivatives.
- Consensus analyst estimates (Baostock/AKshare don't provide).
- MCP server deferred to post-v1 — shipped only if the notebook + chat surfaces prove insufficient.

## 2. Architecture

### Layer model

Core principle: the unified domain model is the contract. Every layer above depends only on the model and the layer directly below; no layer reaches around another. Cross-cutting concerns (schemas, errors, logging, concurrency) apply uniformly.

```
┌────────────────────────────────────────────────────────────────────┐
│  5. AI Interface Layer                                             │
│     Chat Web UI (Streamlit + live kernel + session store)          │
│     ah.ask() notebook helper                                       │
│     MCP server (deferred)                                          │
│                ↓ calls                                             │
│     Tool Registry — thin marshaling over library functions         │
│       (date parsing, symbol validation, figure serialization)      │
├────────────────────────────────────────────────────────────────────┤
│  4. Research Layer                                                 │
│     Strategies │ Factor │ Portfolio │ Backtest │ Metrics │ Analysis│
│     (watchlist, dossier, owner-earnings, valuation bands, ...)     │
├────────────────────────────────────────────────────────────────────┤
│  3. Data Layer                                                     │
│     DataRepository (public API; DI on integrations + cache)        │
│     Converters (source-native → domain model; pandera-validated)   │
├────────────────────────────────────────────────────────────────────┤
│  2. Integration Layer                                              │
│     PriceSource | FundamentalsSource | FXSource | CalendarSource   │
│     (Protocols with concrete Baostock/AKshare/FX implementations)  │
├────────────────────────────────────────────────────────────────────┤
│  1. External Sources                                               │
│     Baostock (A-shares)     AKShare (HK, FX, sector, macro)        │
└────────────────────────────────────────────────────────────────────┘

Cross-cutting:
  - Domain Model (pure types, pandera schemas) — used by every layer
  - Exception hierarchy — errors remapped at integration boundary
  - Structured logging (structlog) — every repo call + backtest run logged
  - Concurrency — ThreadPool for I/O, ProcessPool for CPU-bound backtests
```

### Boundary rules

1. **Integration Layer** — the only code importing `baostock` or `akshare`. Concrete clients conform to `Protocol`s (`PriceSource`, `FundamentalsSource`, `FXSource`, `CalendarSource`, `SectorSource`). Handles session/login, rate limiting (tenacity retries), pagination, error mapping to our exception hierarchy. Returns source-native DataFrames. No knowledge of domain model.
2. **Data Layer** — only code that knows both worlds. `converters/` map source-native → domain model (pure functions; **pandera-validated** on output). `DataRepository` takes Protocols + cache by DI; composes cache-lookup + integration-fetch + converter. Cache is **DuckDB** (one `cache.duckdb` file, tables per entity, schema evolution via `ALTER`, atomic transactions).
3. **Research Layer** — sees only `DataRepository` and domain types. Pure Python; no network; no knowledge of sources. Functions are typed, schema-validated at boundaries, free of side effects outside explicit side-effect functions.
4. **AI Interface Layer** — calls only via the Tool Registry. Three consumers share one registry. Registry handles marshaling (dates from strings, symbol validation, figure JSON, `_ref` resolution for kernel-scoped objects in chat). Research functions remain pure; the registry layer does the ref-handling — research never sees `_ref` strings.

### Package layout

```
ah_research/
├── model/                   # domain types + pandera schemas
│   ├── types.py             # Symbol, AHPair, IndexConstituent, Freq, Exchange, Adjust
│   ├── schemas.py           # pandera SchemaModels for PriceFrame, FundamentalsFrame, ...
│   └── frames.py            # thin wrappers around DataFrames with schema-validated construction
├── exceptions.py            # AHResearchError hierarchy (see §10)
├── config.py                # pydantic-settings: cache dir, API keys (keyring), profile path
├── logging.py               # structlog configuration
├── concurrency.py           # ThreadPool / ProcessPool helpers with backpressure
├── integrations/
│   ├── __init__.py          # Protocols: PriceSource, FundamentalsSource, FXSource, ...
│   ├── baostock/
│   │   ├── client.py        # implements PriceSource, FundamentalsSource, CalendarSource
│   │   └── source_schemas.py
│   ├── akshare/
│   │   ├── client.py        # implements HK PriceSource, FXSource, SectorSource, ...
│   │   └── source_schemas.py
│   └── fake/                # test-only deterministic implementations of all Protocols
├── data/
│   ├── converters/          # source-native → pandera-validated domain
│   ├── cache/               # DuckDB schema + migrations + repository-facing API
│   ├── repository.py        # DataRepository with DI on integrations + cache
│   └── ah_pairs.yaml        # manually curated dual-listing map
├── strategies/
├── backtest/                # engine (T+1/T+2 + price-limit + dividends), verify, costs
├── metrics/
├── factor/                  # research (Newey-West IC), screener
├── portfolio/               # constructors, constraints
├── analysis/                # dossier, owner_earnings, valuation_bands, dividend_consistency, watchlist
├── tools/                   # tool registry (thin marshaling)
└── ui/
    ├── chat/                # Streamlit + live kernel + session store
    ├── notebook.py          # ah.ask()
    ├── theme.py             # CN-aware color convention + plotly theme
    └── mcp_server/          # deferred
scripts/
├── ah_init.py               # bootstrap
├── ah_doctor.py             # health check
├── ah_warmup.py             # sample data pre-fetch
└── audit_ah_pairs.py        # quarterly diff against HKEX / CSRC
tests/
notebooks/
docs/superpowers/specs/
```

### Python packaging extras

```toml
[project]
dependencies = [
  "pandas", "pyarrow", "duckdb", "pandera",
  "tenacity", "structlog", "pydantic-settings", "keyring",
  "empyrical-reloaded", "plotly", "matplotlib",
  "baostock", "akshare",
]

[project.optional-dependencies]
ai = ["anthropic"]
chat = ["streamlit", "jupyter_client"]
dev = ["pytest", "pytest-cov", "hypothesis", "ruff", "mypy", "pre-commit"]
```

The base install is library-only. Library users don't pull Streamlit; chat users opt in via `pip install ah-research[chat,ai]`.

## 3. Domain Model & Data Layer

### Symbol identifier convention

Format: `<code>.<exchange>`
- A-shares: `600519.SH`, `000001.SZ`
- HK: `0700.HK`, `2318.HK`

Exchanges: `SH`, `SZ`, `HK`. Integration layer translates to/from each source's native format.

### Core types

```python
@dataclass(frozen=True)
class Symbol:
    code: str
    exchange: Exchange   # enum: SH, SZ, HK
    currency: Currency   # CNY, HKD

@dataclass(frozen=True)
class AHPair:
    a_symbol: Symbol    # e.g., 601318.SH
    h_symbol: Symbol    # e.g., 2318.HK
    name_en: str
    name_zh: str

@dataclass(frozen=True)
class IndexConstituent:
    index: str           # "CSI300", "HSI", "HSCEI"
    symbol: Symbol
    weight: float | None
    effective_from: date
    effective_to: date | None

@dataclass(frozen=True)
class CorporateAction:
    symbol: Symbol
    ex_date: date
    kind: Literal["cash_dividend", "stock_dividend", "split", "reverse_split", "rights_issue", "spin_off"]
    params: dict         # kind-specific, e.g. {"ratio": 0.1} or {"amount_per_share": 2.5, "currency": "CNY"}
```

(`Issuer` synthetic-ID concept dropped — `AHPair` is keyed on the A symbol.)

### Frames (pandera-validated)

```python
# model/schemas.py
class PriceFrameSchema(pa.SchemaModel):
    date: Series[pa.DateTime]
    symbol: Series[str]
    open: Series[float]
    high: Series[float]
    low: Series[float]
    close: Series[float]
    close_hfq: Series[float]           # back-adjusted, DEFAULT for research
    total_return: Series[float]        # cum-dividend-reinvested
    volume: Series[int] = pa.Field(ge=0)
    amount: Series[float] = pa.Field(ge=0)
    turnover: Series[float]
    is_suspended: Series[bool]
    is_st: Series[bool]                # ST / *ST warning
    limit_up: Series[float]            # today's price-limit ceiling
    limit_down: Series[float]          # today's price-limit floor
    hit_limit_up: Series[bool]
    hit_limit_down: Series[bool]

class FundamentalsFrameSchema(pa.SchemaModel):
    symbol: Series[str]
    report_date: Series[pa.DateTime]          # fiscal period end
    publication_date: Series[pa.DateTime]     # when first released (preliminary or audited)
    known_as_of: Series[pa.DateTime]          # when THIS version was known (for restatements)
    statement_kind: Series[str]               # "preliminary" | "audited" | "restated"

    # raw line items (not just vendor ratios)
    revenue: Series[float]
    net_income: Series[float]
    net_income_ex_nonrecurring: Series[float]  # 扣非净利润
    operating_cash_flow: Series[float]
    capex: Series[float]
    total_assets: Series[float]
    total_equity: Series[float]
    total_debt: Series[float]
    goodwill: Series[float]
    minority_interest: Series[float]
    d_and_a: Series[float]
    working_capital_change: Series[float]

    # vendor / derived ratios (kept as convenience)
    pe: Series[float]
    pb: Series[float]
    ps: Series[float]
    ev_ebitda: Series[float]
    roe: Series[float]
    roic: Series[float]                        # computed
    roa: Series[float]
    gross_margin: Series[float]
    net_margin: Series[float]
    dividend_yield: Series[float]
    market_cap: Series[float]
    market_cap_free_float: Series[float]

    # flags
    is_soe: Series[bool]                       # state-owned enterprise
    is_stock_connect_eligible: Series[bool]
```

Wide `(date × symbol × field)` is for display only; canonical internal form is **long** `(date, symbol, field)`.

### `DataRepository` — public API, DI'd

```python
class DataRepository:
    def __init__(
        self,
        price_source: PriceSource,
        fundamentals_source: FundamentalsSource,
        fx_source: FXSource,
        calendar_source: CalendarSource,
        sector_source: SectorSource,
        cache: DuckDBCache,
    ): ...

    def get_prices(
        self, symbols: list[str], start: date, end: date,
        freq: Freq = "D",
        adjust: Adjust = "hfq",            # DEFAULT: back-adjusted (NOT forward)
        price_kind: PriceKind = "total_return",  # "total_return" | "price_only"
    ) -> PriceFrame: ...

    def get_fundamentals(
        self, symbols: list[str], start: date, end: date,
        fields: list[str] | None = None,
        asof: date | None = None,          # point-in-time cutoff (publication_date <= asof)
        statement_kind: StatementKind = "audited",  # "preliminary" | "audited" | "auto"
    ) -> FundamentalsFrame: ...

    def get_ah_pairs(self) -> list[AHPair]: ...

    def get_index_constituents(
        self, index: str, asof: date | None = None,
    ) -> list[IndexConstituent]: ...        # PIT by default

    def get_universe_over_time(
        self, index: str, start: date, end: date,
    ) -> pd.DataFrame:                      # (date, symbol) pairs — drives survivorship-free fetches
        ...

    def get_trading_calendar(self, exchange, start, end) -> TradingCalendar: ...

    def get_corporate_actions(self, symbols, start, end) -> pd.DataFrame: ...

    def get_sector(self, symbols: list[str], level: int = 1) -> dict[str, str]: ...

    def resample(self, frame, freq) -> PriceFrame: ...
    def compute_ah_premium(self, pair: AHPair, start, end) -> pd.Series: ...  # uses same-day FX
```

Control flow: `cache.lookup() ?? (integration.fetch() → converter.to_domain() → pandera.validate() → cache.store())`.

### Cache — DuckDB

Single file at `~/.ah-research/cache.duckdb` (user-global; overridable via config). Tables: `prices`, `fundamentals`, `corporate_actions`, `index_constituents`, `calendars`, `fx`, `sectors`, `meta` (schema version, last-fetched ranges).

Why DuckDB over per-symbol Parquet:
- Atomic transactions (no half-written files).
- Schema evolution via `ALTER TABLE ADD COLUMN`.
- Range queries fast without loading full symbol history.
- Single file — easy to copy / back up / share / delete.
- No fragmentation from partial fetches.

Migration strategy: `data/cache/migrations/` holds numbered SQL migrations; `ah doctor` runs pending migrations. Schema version stored in `meta` table.

### Corporate-actions pipeline

Corporate actions are the source of truth; `close_hfq` and `total_return` are derived from `close` + actions. Rebuilding adjusted series requires no re-download; only a recompute. This means adding a new action (e.g., a dividend announced yesterday) invalidates derived columns but not raw `close`.

### Cross-currency + AH premium

AH premium uses same-day CNY/HKD (offshore CNH rate) and day-level alignment on the **intersection** of SH and HK trading calendars — default for AH work. `get_prices` for mixed A/HK universes defaults to **union**; AH-specific tools use intersection.

### Point-in-time correctness

Bitemporal fundamentals: `report_date`, `publication_date`, `known_as_of`. `get_fundamentals(asof=d)` returns rows where `publication_date <= d` and `known_as_of <= d`. This handles preliminary vs audited releases (two rows per report: `preliminary` then `audited`) and restatements (later row with later `known_as_of`).

`get_index_constituents(asof=d)` returns the membership as-of that date — not "today's 300."

### AH pair curation

`data/ah_pairs.yaml` starts with ~30 liquid pairs (Ping An, ICBC, CCB, China Mobile, Moutai-none [A-only], etc.); a quarterly `scripts/audit_ah_pairs.py` diffs against HKEX + CSRC listings to flag drift. Target coverage: all ~150 current dual-listings within a month of launch.

## 4. Strategies, Backtest, Metrics

### Strategy contract

```python
class Strategy(Protocol):
    name: str
    def universe(self, repo, asof) -> list[str]: ...
    def generate(self, repo, start, end) -> StrategyOutput: ...

@dataclass(frozen=True)
class StrategyOutput:
    signals: pd.DataFrame | None
    weights: pd.DataFrame | None
    rebalance: Freq = "M"
    meta: dict
```

Strategies receive PIT `repo` — `universe()` must use `get_index_constituents(asof=...)` or `get_universe_over_time(...)`.

### v1 example strategies

- `MomentumStrategy` — 12-1 month momentum on CSI 300 (PIT universe).
- `AHPremiumMeanReversion` — z-score of AH premium, long-discount / short-premium side, on curated pairs (HK-short side only on HK-listable names, since A-shares can't be shorted by retail).
- `ValueFactorStrategy` — composite PE/PB/PS sort on PIT CSI 300, sector-neutralized, long top quintile.

(`DualMomentum` dropped.)

### Backtest engine

```python
def run_backtest(
    weights: pd.DataFrame,
    prices: PriceFrame,
    *,
    rebalance: Freq = "M",
    fill_price: FillPrice = "next_open",      # "next_open" | "next_vwap" | "next_close"
    costs: CostModel = TimeVaryingCosts(),    # historical cost table
    dividend_policy: DividendPolicy = "reinvest",  # "reinvest" | "cash" | "withheld"
    settlement: Settlement = "auto",          # "T+1" for A, "T+2" for HK; auto detects from exchange
    benchmark: str | pd.Series | None = "CSI300_TR",  # TOTAL-RETURN benchmark default
    allow_short: dict[Exchange, bool] = {SH: False, SZ: False, HK: True},
    start=None, end=None,
) -> BacktestResult: ...
```

Engine mechanics:
1. **Fill constraints:** on each rebalance date, attempted trades fail if `hit_limit_up` (for buys) or `hit_limit_down` (for sells); position stays unchanged, logged.
2. **Settlement:** A-share buys on day `t` cannot be sold until `t+1`; HK T+2 sell-eligibility. Engine tracks `sellable_date` per lot.
3. **Suspensions:** zero trade; inherit weight.
4. **Delistings:** position marked at last traded price (not zero); flagged.
5. **Dividends:** per policy — reinvest into same symbol, hold as cash, or withhold (for tax-adjusted returns).
6. **Costs:** time-varying — A-share stamp duty table (2008 0.1%→0.1% 2023 0.05%), HK stamp (0.13%→0.1% 2023), commissions. Cost model is a pure function `(weights_before, weights_after, side, exchange, date) → cost_bps`.
7. **Short availability:** A-share retail short forbidden; `allow_short` dict enforces. Attempted A-short → raises `UnsupportedOperation`.
8. **Limit-aware partial fills:** optional — if open hits limit, check VWAP; if still limit, mark as failed fill; log.

```python
@dataclass
class BacktestResult:
    returns: pd.Series
    equity_curve: pd.Series
    positions: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series
    failed_fills: pd.DataFrame         # date, symbol, reason (limit_up/down, suspended, short_forbidden)
    benchmark_returns: pd.Series | None
    metrics: MetricsBundle
    meta: dict                         # params, data schema version, run time, git SHA
```

### Benchmarks — total-return by default

Built-in: `CSI300_TR`, `CSI500_TR`, `CSI1000_TR`, `HSI_TR`, `HSCEI_TR`. Price-only variants also available (`CSI300_PR`) for chart aesthetics but NOT default for metrics.

### Cost model — realistic, time-varying

- A-share: commission 0.025% min each way + 0.1% stamp sell-side + 0.001% transfer fee (SH) — **round-trip ~0.15%**, not 0.05%.
- HK: commission ~0.04% per side + stamp 0.1% each side post-2023 (was 0.13%) + SFC levy 0.0027% + clearing 0.0027%.
- Stock Connect: northbound stamp applies normally; different rates than local HK for southbound.

All tunable; default table ships in `backtest/costs/defaults.yaml`.

### Strategy verification

`backtest/verify.py`:
- Walk-forward / out-of-sample splits.
- Parameter sensitivity.
- Turnover & capacity sanity (position × ADV check).
- Transaction-cost sensitivity (2× cost stress test).
- **Leakage canary** — feed last-period close as this-period signal; IC must be ≈0. Built-in; runs as part of a strategy's self-test.
- Survivorship check — assert universe at t uses PIT constituents, not today's list.

## 5. Factor Research, Portfolio, Value Analysis

### Factor research (`factor/`)

```python
def run_factor_study(
    signals, prices, *,
    horizons=[20, 60, 120, 240],
    quantiles=5,
    sector_neutral=True,                 # DEFAULT ON for A-shares
    sector_source="sws_l1",
    winsorize=(0.01, 0.99),              # BEFORE ranking
    newey_west_lag=None,                 # auto = max(horizons); overridable
) -> FactorStudy: ...
```

IC t-stats use Newey-West with lag ≥ the forward-return horizon to correct for autocorrelation. Q5−Q1 spread significance uses block bootstrap.

Processing pipeline (explicit in docstring):
1. Cross-sectional winsorize → 2. z-score → 3. (optional) sector demean → 4. rank → 5. compute IC vs forward return.

### Fundamental screener (`factor/screener.py`)

```python
def screen(repo, asof, universe="CSI300", rules=[...], sort_by="dividend_yield", top_n=None) -> pd.DataFrame:
    """E.g. rules=[PE < 15, PB < 2, ROIC > 0.12, debt_to_equity < 0.5, is_soe=False]."""
```

### Portfolio construction

```python
def equal_weight(symbols, asof) -> pd.Series: ...
def market_cap_weight(symbols, asof, repo, cap=0.10, use_free_float=True) -> pd.Series: ...
def risk_parity(symbols, asof, repo, lookback_days=60, cap=0.10) -> pd.Series: ...

def signal_to_weights(
    signals, *,
    method="top_quantile",          # or "rank_weighted" | "long_short_demeaned"
    quantile=0.2,
    scheme="equal",
    max_weight=0.05,
    sector_neutral=True,            # weights balance sector exposure to benchmark
    long_only=True,
    gross_exposure=1.0,
    net_exposure=None,
) -> pd.DataFrame: ...
```

`max_weight_per_sector` in constraints REMOVED (was stillborn) — sector handling now real and built in.

### Value-investor analysis modules (`analysis/`)

- `company.py::company_dossier(repo, symbol, years=10)` — headline block (price, PE, PB, dividend yield, AH premium if any, sector) at top, then valuation bands, fundamentals trajectory, dividend history, AH premium (if dual-listed), peer comparison within sector.
- `owner_earnings.py` — `net_income_ex_nonrecurring + D&A − maintenance_capex_estimate ± WC_change − stock_based_comp − minority_interest_adjustment`. Maintenance capex heuristic documented + configurable. Caveats printed in output.
- `valuation_bands.py` — PE/PB/EV-EBITDA 10y percentile bands; CN convention used (red = "expensive" high, green = "cheap" low) — documented; amber/teal palette available for clarity.
- `dividend_consistency.py` — streak tracker (uninterrupted payment, growth), 5/10/15y CAGR, payout-ratio trend, policy stability flag.
- `watchlist.py` — first-class `Watchlist` object: named, tagged, per-symbol notes + conviction level + last-reviewed date. Supports "dossier-since-last-visit" diff.

### Example end-to-end pipeline

```python
signals = ValueFactorStrategy().generate(repo, start, end).signals
study   = factor.run_factor_study(signals, prices, sector_neutral=True)
weights = portfolio.signal_to_weights(signals, method="top_quantile",
                                      quantile=0.2, max_weight=0.05,
                                      sector_neutral=True)
result  = backtest.run_backtest(weights, prices, rebalance="M",
                                benchmark="CSI300_TR",
                                dividend_policy="reinvest",
                                fill_price="next_open")
backtest.verify.walk_forward(ValueFactorStrategy, repo, splits=5)
backtest.verify.leakage_canary(ValueFactorStrategy, repo)  # must pass
```

## 6. AI Interface Layer

### Shared foundation: Tool Registry (`tools/`)

Tools are **typed wrappers** over library functions. They handle marshaling only: string→date parsing, symbol validation, figure serialization, `_ref` resolution for kernel-scoped objects in chat. Research functions stay pure — they accept typed args, return typed objects. The chat/notebook surfaces resolve `_ref` strings at the boundary.

```python
@tool(name="get_prices", description="Fetch daily OHLCV for symbols over a date range.")
def _(symbols: list[str], start: date, end: date,
      adjust: Literal["hfq","qfq","none"] = "hfq",
      price_kind: Literal["total_return","price_only"] = "total_return") -> dict: ...

@tool(name="screen_value", description="Run a value screen on a universe with rules.")
def _(universe: str, asof: date, rules: list[Rule], top_n: int = 30) -> dict: ...

@tool(name="company_dossier", description="One-name dossier: price+valuation bands+fundamentals+dividends+AH premium.")
def _(symbol: str, years: int = 10) -> dict: ...

@tool(name="run_backtest", description="Vectorized backtest with T+1/T+2 settlement, price-limit fills, realistic costs.")
def _(strategy_name: str, start: date, end: date, benchmark: str = "CSI300_TR",
      rebalance: Literal["D","W","M","Q"] = "M") -> dict: ...

@tool(name="factor_study", description="IC + quantile analysis for a signal; sector-neutral by default.")
def _(signal_name: str, horizons: list[int] = [20, 60, 120, 240],
      quantiles: int = 5, sector_neutral: bool = True) -> dict: ...
```

Rich result payload:
```
{
  "summary": str,
  "table": records | None,
  "figure": plotly_json | None,
  "artifact_name": str,       # variable name in kernel scope (e.g., "_last_dossier")
  "meta": {
    "params_resolved": {...},           # fully-resolved params including defaults + provenance
    "param_provenance": {...},          # "explicit" | "profile" | "default" | "inferred"
    "tool_call_id": str,
    "kernel_id": str,
    "schema_version": str,
  }
}
```

`artifact_name` replaces the `_ref` broker: variables live under predictable names in the notebook kernel; if garbage collection matters (it rarely does for a solo user), the user explicitly `del`s them.

### Surface 1: `ah.ask()` (notebook helper)

```python
def ask(prompt: str, *, model="claude-sonnet-4-6", kernel_scope=True) -> Response: ...
```

Runs a Claude tool-use loop against the registry. Inline Jupyter rendering via `__repr_html__`. Anthropic SDK with prompt caching.

### Surface 2: Chat UI attached to live Jupyter kernel (`ui/chat/`)

Streamlit app. Additions over the v1 design:

**Onboarding gate:** if `~/.ah-research/profile.yaml` or `cache.duckdb` is missing, route to an onboarding page that runs `ah init` interactively. If `ah doctor` reports a red, show the remediation before chat becomes usable.

**Persistent status bar:**
```
kernel: abc123 · started 14:22 · 312MB · 4 artifacts · tokens 184k/500k · $2.41 · [Open in JupyterLab]
```

**Kernel-state panel (collapsible sidebar):** variables in scope with type, shape, size, source ("set by turn #7", "set by user in JupyterLab at 14:31"). Polls kernel namespace after each turn and on tab-focus. Drift banner if namespace changed outside chat.

**Tool-call breadcrumb (above each result):**
```
screen_value · universe=CSI300 (profile) · asof=2026-04-28 (default) · rules=[PE<15, ROIC>0.12] (explicit) · top_n=30 (default)
```
Parameter provenance badges: `explicit` / `profile` / `default` / `inferred`. Hover for explanation.

**Reasoning trail panel (per turn):** plan → tool calls → results → summary, collapsible.

**Refine affordance:** every tool result has a "Refine" button that opens a parameter editor pre-filled; `[Re-run]` re-invokes with edits.

**Session store:** named, resumable sessions at `~/.ah-research/sessions/<slug>/`: `messages.jsonl`, `artifacts/` (pickled), `budget.json`, `cell_exports/`. Auto-named from first prompt; user-renamable. `ah chat --resume <slug>` reconstitutes.

**In-chat search:** cmd-K across the session's turn summaries, tool names, artifact names.

**Bookmarks / labels:** ⭐ pins a turn; pinned turns tagged, queryable, sorted into `journal/`.

**Export as report:** one-click `session → Jupyter notebook + HTML` using pinned turns as sections.

**Notebook-cell export:** one-way push; `cell_exports/` contains snapshots.

**Budget widget:** tokens used / ceiling / cached hit rate / $ estimate; per-turn breakdown on click.

**Constraints (unchanged from v1):** chat constrained to registered tools. Free-form Python (`run_code`) deferred to a future "power mode" with a confirmation UI.

### Surface 3: MCP server (deferred)

Not in v1. Moved to optional future work. If reached, it's a FastAPI/stdio adapter over the same registry.

### Model + cost

- Default: `claude-sonnet-4-6`.
- Escalation: `claude-opus-4-7` per-turn.
- Prompt caching on system prompt + tool schemas (>90% hit rate per session).
- Per-session token ceiling with warn-before-exceed; soft pause at 90%.

### User profile (`~/.ah-research/profile.yaml`)

```yaml
investor_style: value
horizon: long_term
default_universe: CSI300          # or HSI / CSI500 / "CSI300+HSI"
default_rebalance: M
default_metrics: [cagr, sharpe, max_drawdown, dividend_yield_avg]
preferred_visualizations: [valuation_bands, dossier]
cn_color_convention: cn           # "cn" = red up / green down (default); "west" for opposite
api_budget_usd_per_session: 5.0
```

### Visualization theme (`ui/theme.py`)

Centralized palette, fonts, axis formatters (¥ / HK$), CJK fallback, responsiveness. CN color convention (red=up, green=down) default. Valuation-band colors use amber/teal to avoid collision with directional colors; expensive/cheap written as explicit annotations.

## 7. Implementation Phases

| Phase | Scope | Est. |
|---|---|---|
| 0 | Scaffold + bootstrap: uv + Python 3.11+, layout, ruff + mypy + pytest + hypothesis + pre-commit + CI. `ah init`, `ah doctor`, `ah warmup`. `config.py` (pydantic-settings + keyring). `exceptions.py`. `logging.py`. `concurrency.py`. pandera schemas skeleton. | ~1 day |
| 1 | Integration + Data Layer: `Protocol`-based `PriceSource`/`FundamentalsSource`/`FXSource`/`CalendarSource`/`SectorSource` + Baostock + AKshare + FX + `fake/` impls. DuckDB cache + migrations. Converters (pandera-validated). `DataRepository` with DI. Corporate actions + bitemporal fundamentals + PIT constituents + sector tags + ST/limit flags. Curated `ah_pairs.yaml`. | ~1.5 weeks |
| 2 | Backtest + Metrics + first strategies: vectorized engine (T+1/T+2, price-limit-aware fills, dividend policy, time-varying costs, delisting mark-at-last), `verify.py` (walk-forward, sensitivity, leakage canary, survivorship check), metrics bundle with Newey-West, 3 example strategies, first notebook. | ~1.5 weeks |
| 3 | Factor + Portfolio + Value analysis: factor study (sector-neutral default, NW IC, block-bootstrap significance), screener, portfolio constructors + constraints (free-float MCW, real sector neutrality), dossier, owner-earnings, valuation bands, dividend consistency, watchlist. Value notebooks. | ~1 week |
| 4 | Tool Registry + `ah.ask()`: decorator, JSON-schema generation, type coercion (dates, symbols, literals), notebook helper with SDK + prompt caching. Visualization theme module. | ~3 days |
| 5 | Chat UI with live kernel: Streamlit app, jupyter_client attachment, kernel-state panel, status bar, reasoning trail, parameter provenance, refine affordance, session store (save/resume/search/pin/export), budget widget, onboarding gate, "Open in JupyterLab". | ~1.5 weeks |
| 6 | Polish + docs + optional MCP: recipe notebooks, architecture docs, CONTRIBUTING.md. MCP server shipped only if needed. | ~3 days |

Total: ~6 weeks focused (up from 4-5 in v1 due to correctness work and DuckDB + pandera + sessions).

Dependency chain: 0 → 1 → 2 → 3 → 4 → 5 → 6. Phase 2 and 3 partially overlap once the domain model + repository API stabilize.

## 8. Testing Strategy

Replace "≥90% coverage on pure layers" with:

- **Every pure module: at least one known-answer test + one property-based test (hypothesis).** Coverage is a side effect.
- **Backtest engine:** known-answer (constant weights → weighted asset return exact; no-trade day turnover = 0); property (shuffling future prices leaves past P&L unchanged — leakage canary at the engine level).
- **Metrics:** compared to empyrical on reference series.
- **Factor research:** synthetic signal perfectly predicting forward returns → IC = 1.0; decorrelated signal → IC ≈ 0 with CI containing 0.
- **Converters:** test data spans real source quirks — suspension days, splits, bonus issues, rights issues, delistings, ST transitions.
- **Integrations:** mock upstream; recorded fixtures (real JSON/CSV responses captured and checked in). Live tests gated by `AH_RESEARCH_LIVE=1` env var; manual/nightly.
- **Cache:** round-trip per table; schema-migration tests that simulate adding a column; transaction rollback on error.
- **`DataRepository`:** uses `fake/` integrations + real cache; verifies cache composition, range slicing, PIT behavior.
- **Tool registry:** per tool — JSON-schema validates, arg coercion correct, returns serializable payload, handles malformed input.
- **Chat/notebook:** mocked Anthropic; simulate tool-use loops end-to-end. Kernel attachment: launch isolated kernel, send code, assert outputs.
- **Property tests via hypothesis:** symbol parsing round-trips, PIT monotonicity (fundamentals with asof=d can never contain `known_as_of > d`), adjustment idempotence (applying same corporate-action set twice = once).

## 9. Dev Tooling

- `uv` env + deps
- `ruff` lint + format
- `mypy --strict` (where practical)
- `pytest` + `pytest-cov` + `hypothesis`
- `pre-commit`: ruff + mypy + pytest-quick
- GitHub Actions: lint + type + unit on every PR; live integration tests on manual dispatch + nightly.
- Python 3.11+.

Secrets: `ANTHROPIC_API_KEY` + any source credentials via `keyring` (primary) with `.env` fallback for CI. Never in `profile.yaml`. Managed by `ah_research.config.Settings` (pydantic-settings).

Observability: `structlog` JSON logs for every `DataRepository.get_*` (cache hit/miss, rows, elapsed) and every backtest run (n_rebalances, n_trades, elapsed, git SHA).

## 10. Exception Hierarchy & Error Policy

```
AHResearchError
├── SourceError                    # raised at integration boundary; upstream errors remapped here
│   ├── SourceRateLimit            # RETRY with exponential backoff (tenacity)
│   ├── SourceUnavailable          # RETRY with longer backoff
│   ├── SourceSchemaError          # NOT RETRY — drift, needs code fix
│   ├── SourceAuthError            # NOT RETRY — config / login issue
│   └── SourceDataError            # NOT RETRY — empty response, malformed data
├── DataIntegrityError             # cache corruption, schema mismatch, pandera validation failure
├── UserInputError                 # bad symbol, invalid date range, unknown index, conflicting params
└── ResearchError                  # logic errors in strategy / factor / backtest
    ├── LeakageDetected
    ├── UnsupportedOperation       # e.g., A-share short
    └── InsufficientData
```

Retry policy: tenacity `retry_if_exception_type((SourceRateLimit, SourceUnavailable))` with exponential backoff, only in the integration layer. Above the data layer, no retries. `baostock.*` / `akshare.*` exceptions are remapped at the integration boundary and never surface upward.

## 11. Concurrency

- **I/O-bound (integrations):** `concurrent.futures.ThreadPoolExecutor` for bulk fetches. Baostock/AKshare are blocking; threads trivially 5-10x the throughput.
- **CPU-bound (backtests, factor studies):** `concurrent.futures.ProcessPoolExecutor` for walk-forward / param sweeps.
- **Streamlit chat:** long-running tools (backtests >5s) run in a background thread with progress callbacks; UI shows a progress bar and `[Cancel]`. Kernel dispatch through `jupyter_client` is async-compatible; we wrap it in an asyncio helper.
- **Async is NOT used for integrations** — Baostock/AKshare are blocking and async wrappers add no value.

Backpressure: per-source rate-limit tokens live in a thread-safe bucket; integration clients acquire before requesting.

## 12. Risks & Mitigations

1. **Baostock / AKshare upstream instability.** Mitigation: `Protocol`-based boundary, concrete clients raise our exception hierarchy; tests use recorded fixtures so CI is immune; schema drift auto-caught via pandera at the converter boundary.
2. **Point-in-time / look-ahead bias.** Mitigation: bitemporal fundamentals; PIT constituents; `leakage_canary` in verify; hypothesis property tests.
3. **Cache schema migration risk.** Mitigation: numbered SQL migrations in `data/cache/migrations/`; `ah doctor` runs pending; schema version in `meta` table.
4. **AH pair curation drift.** Mitigation: quarterly `scripts/audit_ah_pairs.py`; checked-in `ah_pairs.yaml`.
5. **Jupyter kernel fragility.** Mitigation: heartbeat detection; reconnect flow; artifacts survive via session store pickle.
6. **Claude API cost.** Mitigation: prompt caching; per-session token budget with warn-at-90%.
7. **Calendar edge cases** (Chinese New Year, HK typhoons, circuit breakers). Mitigation: exchange-official calendars; explicit alignment per call.
8. **Sector data quality.** Mitigation: SWS from AKshare as primary; `get_sector` cached; expose `is_soe` + `is_stock_connect_eligible` flags separately.
9. **DuckDB lock contention** (unlikely with single-user solo workflow but possible if chat + JupyterLab both write). Mitigation: serialize writes through a single `DuckDBCache` instance per process; reads are concurrent.

## 13. Deferred (post-v1)

- Multi-factor regression models (Fama-Macbeth, Barra).
- Optimization-based weighting (CVXPY).
- Pairs-trading cointegration beyond the AH case.
- "Power mode" for chat (free-form Python generation, guarded).
- MCP server.
- Consensus-estimate data (needs paid source like Tushare Pro).
- Intraday bars.
- Multi-user / collaboration features.

## 14. Success Criteria

1. **Fresh clone → working "hello world" dossier in <5 minutes.** `uv sync && ah init && ah warmup --sample && python -c "from ah_research import ah; ah.ask('dossier for 600519.SH')"`.
2. Fetch daily bars for any A/HK symbol or curated AH pair over a multi-year range in <2s warm / <60s cold (first fetch pulls from source + populates DuckDB).
3. Screen CSI 300 or HSI by fundamental rules, PIT-correct, sorted results within 5s.
4. Pull a company dossier for any symbol with valuation bands, fundamentals trajectory, dividend history, AH premium if dual-listed, sector peers.
5. Define a strategy, backtest 10y monthly-rebal with T+1/T+2 settlement, realistic time-varying costs, price-limit-aware fills → metrics bundle + equity curve vs total-return benchmark.
6. Run a factor study with sector-neutralization → Newey-West IC stats, quantile returns, IC decay, block-bootstrapped Q5-Q1 significance.
7. `leakage_canary` and `survivorship_check` both pass for every example strategy.
8. Do all of (2)-(6) by asking the chat UI in natural language, with inline plots, parameter provenance, reasoning trail, persistent kernel state, and resumable sessions.
