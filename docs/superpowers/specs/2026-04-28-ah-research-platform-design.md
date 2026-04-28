# ah-research — Platform Design

**Date:** 2026-04-28
**Status:** Validated design, ready for implementation planning
**Owner:** Brian Huang

## 1. Purpose & Scope

`ah-research` is a personal stock-research platform focused on A-shares (Shanghai / Shenzhen) and Hong Kong listings, with first-class treatment of AH dual-listings. It is **not** a trading system. Its purpose is fundamental analysis and daily/weekly/monthly trading-data research, with an emphasis on long-term value investing.

### In scope

- Daily bars as the primitive; weekly/monthly derived by resampling.
- Price/volume + fundamentals + AH-pair linkage + index constituents.
- Vectorized backtesting (daily/weekly/monthly rebalance).
- Factor research: IC, quantile analysis, cross-sectional factor studies.
- Portfolio construction: equal-weight / market-cap / risk-parity + caps.
- Strategy verification: walk-forward, param sensitivity, cost sensitivity.
- Value-investor tooling: fundamental screens, company dossier, owner-earnings / FCF trajectory, valuation-band plotter, dividend consistency.
- Three AI-UI surfaces over a shared tool registry: `ah.ask()` notebook helper, a Streamlit chat UI attached to a live Jupyter kernel, and an MCP server (later phase).

### Out of scope (v1)

- Real-time or intraday trading; order execution.
- Intraday bars.
- Multi-factor regression models (Fama-Macbeth, Barra-style).
- Optimization-based portfolio construction (CVXPY).
- Options and derivatives.
- Sector-tagged analysis (framework-ready, disabled by default until a clean source is identified).

## 2. Architecture

### Layer model

Core principle: the unified domain model is the contract. Every layer above depends only on the model and the layer directly below; no layer reaches around another.

```
┌────────────────────────────────────────────────────────────────────┐
│  5. AI Interface Layer                                             │
│     Chat Web UI (Streamlit + live kernel)                          │
│     ah.ask() notebook helper                                       │
│     MCP server (Phase 6)                                           │
│                ↓ calls                                             │
│     Tool Registry (JSON schemas over library functions)            │
├────────────────────────────────────────────────────────────────────┤
│  4. Research Layer                                                 │
│     Strategies │ Factor Research │ Portfolio │ Backtest │ Metrics  │
│     Value Analysis (dossier, owner-earnings, valuation bands, ...) │
├────────────────────────────────────────────────────────────────────┤
│  3. Data Layer  (internal view of the world)                       │
│     DataRepository (public API)                                    │
│     Converters (source-native → domain)  +  Parquet cache          │
├────────────────────────────────────────────────────────────────────┤
│  2. Integration Layer  (external world)                            │
│     BaostockClient    │   AKShareClient    │   FXClient            │
│     - login/session   │   - endpoint route │   - CNY↔HKD           │
│     - rate-limit/retry│   - rate-limit/retry                       │
│     - pagination      │   - error mapping                          │
│     → source-native DataFrames                                     │
├────────────────────────────────────────────────────────────────────┤
│  1. External Sources (out of our control)                          │
│     Baostock (A-shares)       AKShare (HK + FX + macro)            │
└────────────────────────────────────────────────────────────────────┘

Domain Model — pure types, imported by any layer, owned by none.
```

### Boundary rules

1. **Integration Layer** — the only code importing `baostock` or `akshare`. Returns pandas DataFrames with **source-native** column names/dtypes/units. Handles session/login, rate limiting, retries, pagination, error mapping. Zero knowledge of the domain model.
2. **Data Layer** — the only code that knows both worlds. `converters/` map source-native → domain model (pure functions). `cache/` stores Parquet in **domain-model schema** so the cache survives future source swaps. `DataRepository` composes integration + converter + cache and is the library's public API.
3. **Research Layer** — sees only `DataRepository` and domain types. Pure Python; no network; no knowledge that sources exist.
4. **AI Interface Layer** — calls only via the Tool Registry. Three consumers (chat UI, `ah.ask`, MCP server) share one registry.

### Package layout

```
ah_research/
├── model/                   # domain types (pure)
├── integrations/            # LAYER 2 — external calls only
│   ├── baostock/
│   │   ├── client.py
│   │   └── source_schemas.py
│   ├── akshare/
│   │   ├── client.py
│   │   └── source_schemas.py
│   └── fx/
│       └── client.py
├── data/                    # LAYER 3 — domain view + cache
│   ├── converters/
│   ├── cache/
│   ├── repository.py
│   └── ah_pairs.yaml        # manually curated dual-listing map
├── strategies/              # LAYER 4 — research
├── backtest/                #   engine, verify, cost model
├── metrics/                 #   empyrical wrapper + own
├── factor/                  #   research, screener
├── portfolio/               #   constructors, constraints
├── analysis/                #   value-investor tools
│   ├── company.py           #   dossier
│   ├── owner_earnings.py    #   Buffett-style FCF trajectory
│   ├── valuation_bands.py   #   percentile bands over 10y
│   └── dividend_consistency.py
├── tools/                   # LAYER 5a — tool registry
└── ui/
    ├── chat/                # LAYER 5b — Streamlit + live kernel
    ├── notebook.py          #   ah.ask()
    └── mcp_server/          #   Phase 6

tests/
notebooks/
docs/superpowers/specs/
```

## 3. Domain Model & Data Layer

### Symbol identifier convention

Format: `<code>.<exchange>`
- A-shares: `600519.SH`, `000001.SZ`
- HK: `0700.HK`, `2318.HK`

Exchanges: `SH` (Shanghai), `SZ` (Shenzhen), `HK` (Hong Kong). Integration layer translates to/from each source's native format (`sh.600519` for Baostock, raw codes + market hint for AKshare).

### Core types

```python
@dataclass(frozen=True)
class Symbol:
    code: str
    exchange: Exchange   # enum: SH, SZ, HK
    currency: Currency   # CNY, HKD

@dataclass(frozen=True)
class Issuer:
    issuer_id: str       # our synthetic ID, stable across sources
    name_en: str
    name_zh: str
    listings: tuple[Symbol, ...]

@dataclass(frozen=True)
class AHPair:
    issuer: Issuer
    a_symbol: Symbol
    h_symbol: Symbol

@dataclass(frozen=True)
class IndexConstituent:
    index: str           # "CSI300", "HSI", "HSCEI", ...
    symbol: Symbol
    weight: float | None
    effective_from: date
    effective_to: date | None   # None = currently a member
```

Frames:

- `PriceFrame` — wide DataFrame; index = dates, columns = (symbol, field) where field ∈ {open, high, low, close, adj_close, volume, amount, turnover}. Carries `.meta` with data source + adjustment policy.
- `FundamentalsFrame` — long DataFrame; (report_date, symbol) → fields (pe, pb, ps, ev_ebitda, roe, roa, gross_margin, net_margin, dividend_yield, market_cap, ...). Point-in-time: each row carries `publication_date` so strategies never see future information. Additional fields discovered during Phase 1 based on Baostock/AKshare availability.
- `TradingCalendar` — per-exchange trading-day calendar.

### `DataRepository` — public API

```python
class DataRepository:
    def get_prices(self, symbols, start, end, freq="D", adjust="forward") -> PriceFrame: ...
    def get_fundamentals(self, symbols, start, end, fields=None, asof=None) -> FundamentalsFrame: ...
    def get_ah_pairs(self) -> list[AHPair]: ...
    def get_index_constituents(self, index, asof=None) -> list[IndexConstituent]: ...
    def get_trading_calendar(self, exchange, start, end) -> TradingCalendar: ...

    def resample(self, frame: PriceFrame, freq) -> PriceFrame: ...
    def compute_ah_premium(self, pair: AHPair, start, end) -> pd.Series: ...
```

Each method's control flow: `cache.lookup() ?? (integration.fetch() → converter.to_domain() → cache.store())`.

### Cache layout

Location default: `~/.ah-research/cache/` (user-global; multiple projects share). Override via config.

```
~/.ah-research/cache/
├── prices/
│   ├── SH/600519.parquet        # daily bars per symbol
│   └── HK/0700.parquet
├── fundamentals/
│   ├── SH/600519.parquet
│   └── ...
├── ah_pairs.parquet
├── index_constituents/
│   ├── CSI300.parquet
│   └── HSI.parquet
├── calendars/
│   ├── SH.parquet
│   └── HK.parquet
├── fx/CNY_HKD.parquet
└── raw/                         # optional: source-native for forensics
    └── {source}/{endpoint}/...
```

Policy:
- One Parquet file per symbol; writes are cheap and parallel-safe.
- Monotonic date append extends files rather than rewriting.
- Each file stores metadata (last_fetched, source, schema_version) in Parquet key-value metadata.
- `get_*(refresh=False)` returns from cache when range is covered; otherwise fetches missing slice and extends.

### Cross-currency + calendar alignment

AH premium requires `CNY / HKD` FX from a third integration (`fx/`, AKshare-backed), cached under `fx/CNY_HKD.parquet`.

Alignment across exchanges is explicit per call: `align="union" | "intersection" | "sh" | "hk"`. Default `"union"` with NaN on non-trading days. AH pair work naturally uses `"intersection"`.

### Point-in-time correctness

Fundamentals carry both `report_date` (fiscal period end) and `publication_date` (release date). `get_fundamentals(..., asof=d)` returns only rows with `publication_date <= d` — enforcing no look-ahead bias at the repository level rather than in every strategy.

### AH pair curation

`data/ah_pairs.yaml` is a checked-in, manually curated starter list (~30 notable pairs). A quarterly `scripts/audit_ah_pairs.py` compares it against HKEX / CSRC listings to flag drift.

## 4. Strategies, Backtest, Metrics

### Strategy contract

```python
class Strategy(Protocol):
    name: str
    def universe(self, repo, asof) -> list[str]: ...
    def generate(self, repo, start, end) -> StrategyOutput: ...

@dataclass(frozen=True)
class StrategyOutput:
    signals: pd.DataFrame | None    # (date × symbol) continuous scores
    weights: pd.DataFrame | None    # (date × symbol) target weights
    rebalance: Freq = "M"           # value-investor default: monthly
    meta: dict
```

A strategy produces either signals (raw scores) OR weights (directly tradable), not both. Signals flow to factor research and/or portfolio construction; weights go straight to the backtest engine.

### v1 example strategies (also serve as end-to-end smoke tests)

- `MomentumStrategy` — 12-1 month momentum on CSI 300.
- `AHPremiumMeanReversion` — AH premium z-score threshold trading on curated pairs.
- `ValueFactorStrategy` — composite PE/PB/PS sort on a universe, long top quintile.
- `DualMomentum` — CSI 300 vs HSI cross-asset comparison.

### Backtest engine

```python
def run_backtest(
    weights: pd.DataFrame,
    prices: PriceFrame,
    *,
    rebalance: Freq = "M",            # value default: monthly
    costs: CostModel = DefaultCosts(),
    benchmark: str | pd.Series | None = "CSI300",
    start=None, end=None,
) -> BacktestResult: ...

@dataclass
class BacktestResult:
    returns: pd.Series
    equity_curve: pd.Series
    positions: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series
    benchmark_returns: pd.Series | None
    metrics: MetricsBundle
    meta: dict
```

Mechanics (daily-rebal example):
1. Shift target weights forward one day (execute at next-day open; no look-ahead).
2. `ret[t] = (weights_held[t-1] * asset_ret[t]).sum()` minus cost drag.
3. Costs applied on rebalance days: `turnover * (commission + slippage + stamp)`. Stamp duty applies only to A-sells and both sides in HK.
4. Suspensions: symbol inherits prior weight; no trade occurs that day; flagged in `positions`.
5. Delistings: position marked to zero, cash freed, logged in `meta`.

Cost-model defaults (overridable, set from real-world case):
- A-shares: commission 0.025% round-trip, slippage 0.05%, stamp duty 0.1% sell-side.
- HK: commission 0.04%, stamp duty 0.1% both sides, SFC levy 0.0027%.

### Metrics

`empyrical-reloaded` for standard metrics + own implementations for IC, turnover, exposure:

```python
@dataclass(frozen=True)
class MetricsBundle:
    cagr: float
    volatility_ann: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    max_drawdown_duration: int
    hit_rate: float
    turnover_ann: float
    information_ratio: float | None
    alpha_beta: tuple[float, float] | None
    exposure: dict
```

### Benchmarks

Pre-fetched: `CSI300`, `CSI500`, `CSI1000`, `HSI`, `HSCEI`. Custom benchmark via `pd.Series` of returns.

### Strategy verification (distinct from one backtest)

`backtest/verify.py` — robustness on demand, not every run:
- Walk-forward / out-of-sample splits.
- Parameter sensitivity.
- Turnover & capacity sanity.
- Transaction-cost sensitivity (2× cost stress test).
- Benchmark robustness.
- Look-ahead leakage scanner.

This is kept separate from `factor/research.py` (the IC/quantile toolkit) — different questions, different tools.

## 5. Factor Research, Portfolio, Value Analysis

### Factor research (`factor/`)

```python
def run_factor_study(
    signals, prices, *,
    horizons=[20, 60, 120, 240],    # long-term value default: 1m/3m/6m/12m
    quantiles=5,
    sector_neutral=False,
    winsorize=(0.01, 0.99),
) -> FactorStudy: ...
```

Answers: "does this signal have predictive power?" via IC (Spearman corr, mean + t-stat + IR), quantile returns, Q5−Q1 spread, IC decay, autocorrelation.

### Fundamental screener (`factor/screener.py`)

Natural for value work — often more useful than factor models:

```python
def screen(repo, asof, universe="CSI300", rules=[...], sort_by="dividend_yield", top_n=None) -> pd.DataFrame:
    """E.g. rules=[PE < 15, PB < 2, ROE > 0.15, debt_to_equity < 0.5]."""
```

Rules compose from pure primitives over the fundamentals frame.

### Portfolio construction (`portfolio/`)

```python
# Direct constructors
def equal_weight(symbols, asof) -> pd.Series: ...
def market_cap_weight(symbols, asof, repo, cap=0.10) -> pd.Series: ...
def risk_parity(symbols, asof, repo, lookback_days=60, cap=0.10) -> pd.Series: ...

# Common path: signals → diversified weights
def signal_to_weights(
    signals, *,
    method="top_quantile",          # or "rank_weighted" | "long_short_demeaned"
    quantile=0.2,
    scheme="equal",                 # or "proportional" | "risk_parity"
    max_weight=0.05,
    long_only=True,
    gross_exposure=1.0,
    net_exposure=None,
) -> pd.DataFrame: ...
```

### Constraints (post-processing)

```python
@dataclass(frozen=True)
class PortfolioConstraints:
    max_weight_per_name: float = 0.05
    max_weight_per_sector: float | None = None
    long_only: bool = True
    gross_exposure: float = 1.0
    net_exposure: float | None = None
    min_price_cny: float | None = None
    min_adv_cny: float | None = None
```

Applied as pure post-processing over weights DataFrames; constructors stay composable.

### Value-investor analysis modules (`analysis/`)

- `company.py::company_dossier(repo, symbol, years=10)` — one-stop view: price history + valuation bands + fundamentals trajectory + dividend history + AH premium (if dual-listed) + peer comparison.
- `owner_earnings.py` — Buffett-style: `net_income + D&A − maintenance capex ± WC changes`. Plots FCF and owner-earnings trajectory side-by-side with reported earnings.
- `valuation_bands.py` — price chart with PE (and PB, EV/EBITDA) percentile bands over trailing 10y; dark-red "expensive" >90th, green "cheap" <10th zones.
- `dividend_consistency.py` — streak tracker: years of uninterrupted payment, years of growth, 5/10/15y CAGR, payout-ratio trend.

### Example end-to-end pipeline

```python
signals = ValueFactorStrategy().generate(repo, start, end).signals
study   = factor.run_factor_study(signals, prices)
weights = portfolio.signal_to_weights(signals, method="top_quantile",
                                      quantile=0.2, max_weight=0.05)
result  = backtest.run_backtest(weights, prices, rebalance="M", benchmark="CSI300")
backtest.verify.walk_forward(ValueFactorStrategy, repo, splits=5)
```

## 6. AI Interface Layer

Three surfaces, one shared foundation.

### Shared foundation: Tool Registry (`tools/`)

```python
@tool(name="get_prices", description="Fetch daily OHLCV for symbols over a date range.")
def _(symbols: list[str], start: date, end: date, adjust: Adjust = "forward") -> dict: ...

@tool(name="screen_value", description="Run a value screen on a universe with rules.")
def _(universe: str, asof: date, rules: list[dict], top_n: int = 30) -> dict: ...

@tool(name="company_dossier", description="Full one-name dossier.")
def _(symbol: str, years: int = 10) -> dict: ...

@tool(name="run_backtest", description="Vectorized backtest given target weights.")
def _(weights_ref: str, benchmark="CSI300", rebalance="M",
      start=None, end=None) -> dict: ...

@tool(name="factor_study", description="IC + quantile analysis for a signal.")
def _(signals_ref: str, horizons=[20, 60, 120, 240], quantiles=5) -> dict: ...
```

Properties:
- Single source of truth; three interfaces consume the same registry.
- Tool schemas auto-generated from type hints + docstrings (pydantic / JSONSchema).
- **Artifact-by-reference.** Large payloads (PriceFrame, StrategyOutput, BacktestResult) are kept in the kernel under IDs. Tools accept/return `_ref` handles instead of serializing megabytes through the chat.
- Rich result payload: `{"summary": str, "table": records, "figure": plotly_json | null, "artifact_ref": str | null, "meta": dict}`.

### Surface 1: `ah.ask()` (notebook helper)

```python
def ask(prompt: str, *, model="claude-sonnet-4-6", kernel_scope=True) -> Response: ...
```

Runs a Claude tool-use loop against the registry. Returns a `Response` with `.text / .tables / .figures / .trace`, renders inline via `__repr_html__`. When `kernel_scope=True`, results bind to the notebook namespace (`_last_result`, `_last_figure`) so exploration continues.

Uses Anthropic SDK with prompt caching: system prompt + tool schemas form a static cache prefix; only the user prompt varies. Expected cache hit rate >90% after the first turn.

### Surface 2: Chat UI attached to live Jupyter kernel (`ui/chat/`)

A Streamlit app that runs a Claude tool-use loop backed by the **same registry**, additionally attaching to a live Jupyter kernel via `jupyter_client`.

What kernel-attachment buys:
1. Persistent Python state across chat turns. No re-fetching, no re-computing.
2. Two-way visibility with JupyterLab — the same kernel can be opened in JupyterLab; chat-computed variables appear there, and vice versa.
3. Code-level override — drop to the notebook, tweak, return. Chat sees updated state.
4. Generated code is inspectable — each tool call goes through a visible "code cell" step with code + output; users can copy/save/edit.

Flow of one turn:

```
User prompt → Streamlit backend → Anthropic SDK (prompt-cached system+tools)
             → Claude selects tool(s) → backend dispatches via jupyter_client
             → kernel executes `from ah_research.x import y; _ah_result = y(...)`
             → captures execute_reply (text, figures, artifact_ref)
             → result flows back to Claude → Claude writes summary
             → Chat renders: summary + plotly chart + data table + "see code" fold
```

**Chat can:** call any registry tool; chain tools; read/write kernel state by name; render figures inline; save a turn as a notebook cell (one-way `.ipynb` append — not bidirectional sync).

**Chat cannot (v1, by design):** generate arbitrary Python; edit existing `.ipynb` cells. Constrained to registered tools. A future "power mode" toggle can relax this.

### Surface 3: MCP server (`ui/mcp_server/`, Phase 6)

Thin FastAPI/stdio MCP server exposing the same tool registry. Adapter between MCP tool-call protocol and the registry dispatcher.

### Model + cost

- Default: `claude-sonnet-4-6`.
- Escalation: user toggles `claude-opus-4-7` per-turn for harder reasoning.
- Prompt caching on system prompt + tool schemas.
- Configurable per-session token ceiling with warn-before-exceed.

### User profile (`~/.ah-research/profile.yaml`)

```yaml
investor_style: value
horizon: long_term          # >60 days
default_universe: CSI300+HSI
default_rebalance: M
default_metrics: [cagr, sharpe, max_drawdown, dividend_yield_avg]
preferred_visualizations: [valuation_bands, dossier]
```

Loaded into system prompt. Edited by the user; no UI for editing in v1.

## 7. Implementation Phases

Each phase ships something useful on its own; the library does not require the chat UI to be valuable.

| Phase | Scope | Est. |
|---|---|---|
| 0 | Scaffold: uv + Python 3.11+, layout, ruff + mypy + pytest + pre-commit + CI | ½ day |
| 1 | Integration + Data Layer: Baostock + AKshare + FX clients, converters, Parquet cache, DataRepository, curated `ah_pairs.yaml` | ~1 week |
| 2 | Backtest + Metrics + first strategies: vectorized engine, cost model, suspensions/delistings, `verify.py`, metrics bundle, 4 example strategies, first notebook | ~1 week |
| 3 | Factor + Portfolio + Value analysis: factor study, screener, portfolio constructors + constraints, dossier, owner-earnings, valuation bands, dividend consistency; value notebooks | ~1 week |
| 4 | Tool Registry + `ah.ask()`: decorator, JSON-schema generation, artifact store, tool wrappers, notebook helper with SDK + prompt caching | ~½ week |
| 5 | Chat UI with live kernel: Streamlit app, jupyter_client attachment, figure rendering, notebook-cell export, profile loader, model toggle, launcher | ~1 week |
| 6 | MCP server + polish: FastAPI/stdio adapter, documentation, recipe notebooks | ~2-3 days |

Total: ~4-5 weeks focused work. Parallelism possible (integrations vs backtest scaffolding) once the domain model stabilizes.

Dependency chain: Phase 0 → 1 → 2 → 3 → 4 → 5 → 6. Phases 2 and 3 can partially overlap once the domain model and repository API are stable. Phase 5 depends on Phase 4 because both use the shared tool registry.

## 8. Testing Strategy

| Layer | Test type | Approach |
|---|---|---|
| Integrations | Unit | Mock upstream; recorded fixtures. Live tests gated by `AH_RESEARCH_LIVE=1` env var; manual/nightly. |
| Data converters | Unit | Pure functions; source-native DataFrame in → domain-model DataFrame out. |
| Cache | Unit | tmp_path; round-trip; schema-version upgrade path. |
| DataRepository | Integration | Fake integrations with deterministic data; verify cache composition & slicing. |
| Strategies | Unit | Deterministic tiny universes; snapshot StrategyOutput. |
| Backtest engine | Unit | Known-answer tests: constant-weight portfolio → weighted asset return exact. Turnover on no-trade day = 0. Cost drag = cost_model × turnover. |
| Metrics | Unit | Compare to empyrical on known series. |
| Factor research | Unit | Synthetic signal perfectly predicting forward returns → IC = 1.0, Q5−Q1 > 0 monotone. |
| Portfolio constructors | Unit | Weight sums, caps, exposure limits. |
| Tool registry | Unit | Per tool: JSON-schema validates, returns serializable payload, handles bad input. |
| `ah.ask` / Chat UI | Integration | Mocked Anthropic; simulate tool-use loops end-to-end. |
| Kernel attachment | Integration | Launch isolated kernel, send code, assert outputs. |

**Coverage target:** ≥90% on pure layers (domain model, converters, backtest engine, metrics, factor, portfolio). Best-effort on I/O layers (integrations, kernel, chat UI).

## 9. Dev Tooling

- `uv` for env + deps
- `ruff` lint + format
- `mypy --strict` (where practical — pandas typing is imperfect)
- `pytest` + `pytest-cov`
- `pre-commit` runs ruff + mypy + pytest-quick
- GitHub Actions: lint + type + unit on every PR; live integration tests on manual dispatch

Python 3.11+. Key deps: `pandas`, `pyarrow`, `empyrical-reloaded`, `plotly`, `matplotlib`, `baostock`, `akshare`, `anthropic`, `streamlit`, `jupyter_client`.

## 10. Risks & Mitigations

1. **Baostock / AKshare upstream instability.** Community libraries; schemas change. Mitigation: explicit error-mapping layer in each integration raising our own exceptions (`SourceRateLimitError`, `SourceSchemaError`, `SourceUnavailable`); tests use recorded fixtures so CI is immune.
2. **Point-in-time / look-ahead bias in fundamentals.** Value work is fragile to this. Mitigation: `publication_date` tracked separately from `report_date`; `asof=` parameter on `get_fundamentals`; `backtest.verify.leakage_check()` scans for look-ahead.
3. **AH pair curation drift.** Listings change. Mitigation: checked-in `ah_pairs.yaml`; quarterly `scripts/audit_ah_pairs.py` compares against HKEX / CSRC.
4. **Jupyter kernel attachment fragility.** Kernel can die mid-session. Mitigation: chat UI detects kernel death, offers reconnect; artifacts serialized to disk so they survive.
5. **Claude API cost.** Mitigation: prompt-cached system + tool schemas (>90% hit rate per session); per-session token budget with warn-before-exceed.
6. **Calendar edge cases (Chinese New Year, HK typhoons).** Mitigation: use exchange-official calendars from the sources; alignment policy explicit per call.

## 11. Deferred (future phases)

- Multi-factor regression models (Fama-Macbeth, Barra).
- Optimization-based weighting (CVXPY).
- Pairs-trading cointegration beyond the hardcoded AH case.
- Sector-tagged analysis (requires a clean sector source).
- "Power mode" for the chat (free-form Python generation, guarded).
- Database-backed storage layer replacing the Parquet cache (drop-in; `DataRepository` is the only code that needs to change).
- Intraday bars.

## 12. Success Criteria

The platform is done enough when, from a notebook or the chat UI, the user can:

1. Fetch daily bars for any A/HK symbol or curated AH pair over a multi-year range in <2s warm / <30s cold.
2. Screen CSI 300 or HSI by fundamental rules and get a sorted table of survivors.
3. Pull a company dossier for any symbol with valuation bands, fundamentals trajectory, dividend history.
4. Define a strategy, backtest it monthly-rebalanced over 10y with realistic costs, and get a metrics bundle + equity curve vs CSI 300.
5. Run a factor study on a signal and see IC statistics, quantile returns, IC decay.
6. Do all of the above by asking the chat UI in natural language, with inline plots and persisted kernel state.
