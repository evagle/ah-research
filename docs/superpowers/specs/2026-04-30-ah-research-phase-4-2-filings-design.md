# Phase 4.2 — Filings + Profile Repositories Design

**Status:** Draft (auto-authored per user directive "you decide all")
**Date:** 2026-04-30
**Supersedes notes in:** `2026-04-30-ah-research-phase-4-1-optimizer-design.md` §13 (Phase 4.2 preview)

---

## 1. Mission

Surface the markdown artifacts produced by the `value-profile` skill and `download_filings.py` pipeline (`data/filings/`, `profiles/`) as typed Python objects, queryable from the `ah_research` package and CLI. This closes the gap where those artifacts are strandedas documents — unreadable by the rest of the Python stack.

## 2. Scope (tight)

**In scope for 4.2:**
- `FilingsRepository` — list/fetch 年报 / 招股说明书 / research reports
- `ProfileRepository` — list/fetch `<ticker>-<date>.md` value-investing profiles
- `Filing` and `Profile` frozen dataclasses with raw text + parsed sections
- CLI: `ah filings list/show`, `ah profile list/show`
- Unit tests + acceptance notebook

**Deferred to 4.3 (explicit non-goals):**
- Dossier integration (new `FilingsSection` / `QualitativeSection`)
- Screener predicates backed by profile grades (`moat_grade`, `redflag_count`, etc.)
- Structured grading/scoring of profile content (A-F grades, risk flags)
- Sector-overlay integration for profile section parsing
- Research report deduplication / deep parsing
- Writing / updating profiles (read-only in 4.2)

The rationale: grading is a separate, harder problem than surfacing; it deserves its own iteration once the raw data is accessible.

## 3. Architecture

### 3.1 Module layout

```
src/ah_research/
├── filings/                      # NEW
│   ├── __init__.py               # public API: Filing, FilingsRepository, Profile, ProfileRepository
│   ├── types.py                  # Filing + Profile frozen dataclasses
│   ├── filings_repository.py     # FilingsRepository
│   └── profile_repository.py     # ProfileRepository + section parser
└── scripts/
    ├── ah_profile.py             # NEW — `ah profile` Typer sub-app
    └── ah_filings.py             # NEW — `ah filings` Typer sub-app
```

### 3.2 On-disk layout (as observed on main)

```
data/filings/<ticker>/
├── 年报-<YYYY>.md                 # Annual report (one per year)
├── 招股说明书.md                   # IPO prospectus (single)
└── research/
    └── <brokerage>-<title>-<YYYYMMDD>.md   # Analyst research reports

profiles/
├── <ticker>-<YYYY-MM-DD>.md                # Full value-investing profile
└── <ticker>-<YYYY-MM-DD>-evaluation.md      # Evaluation summary (skipped by ProfileRepository)
```

Only one ticker is currently present (`600519.SH`), but the code must handle N tickers.

## 4. Core types

```python
# src/ah_research/filings/types.py

FilingKind = Literal["annual", "ipo", "research"]

@dataclass(frozen=True)
class Filing:
    symbol: str                 # e.g. "600519.SH"
    kind: FilingKind
    path: Path
    text: str                   # full markdown content
    year: int | None = None     # set for annual; None for ipo/research
    title: str | None = None    # set for research (derived from filename)
    date: date | None = None    # set for research (derived from filename)

@dataclass(frozen=True)
class Profile:
    symbol: str
    date: date                  # profile date (parsed from filename)
    path: Path
    text: str                   # full markdown content
    sections: Mapping[str, str] # section-heading → body, parsed by header regex
```

`Profile.sections` is populated by a heuristic parser:
- Match `^##\s+` (H2) headers as top-level sections
- Match `^###\s+` (H3) as subsections, keyed as `"<parent> / <sub>"`
- Keys preserve the raw header text (may be Chinese, e.g. `"§1 能力圈"`, `"Part 0 — 封面 & Executive Summary"`)
- Values are everything up to the next same-or-higher-level header

Sections dict is always populated (possibly empty if the profile has only a top-level H1). No schema enforcement — profile format is evolving.

## 5. Repository API

```python
class FilingsRepository:
    def __init__(self, root: Path = Path("data/filings")): ...

    def list_symbols(self) -> list[str]: ...
    def list_filings(self, symbol: str) -> list[Filing]: ...       # all kinds, sorted
    def get_annual(self, symbol: str, year: int) -> Filing: ...    # raises FileNotFoundError
    def latest_annual(self, symbol: str) -> Filing | None: ...
    def get_ipo(self, symbol: str) -> Filing | None: ...
    def get_research(self, symbol: str) -> list[Filing]: ...       # all research reports, sorted by date desc


class ProfileRepository:
    def __init__(self, root: Path = Path("profiles")): ...

    def list_symbols(self) -> list[str]: ...                       # unique symbols with ≥1 profile
    def list_profiles(self, symbol: str | None = None) -> list[Profile]: ...
    def latest(self, symbol: str) -> Profile | None: ...
    def get(self, symbol: str, date: date) -> Profile: ...         # raises FileNotFoundError
```

Both repositories:
- Validate `symbol` matches Phase 1 format (`^[0-9]{4,6}\.(SH|SZ|HK)$`) at construction via existing `parse_symbol()` — reuse, don't duplicate
- Skip `*-evaluation.md` in `profiles/` (keep only the full profile)
- Skip hidden files / `__pycache__` / non-`.md` files
- Read lazily (file text loaded only on `Filing`/`Profile` materialization, not on listing)

## 6. CLI

### 6.1 `ah filings`

```
ah filings list [SYMBOL]                  # table: symbol/kind/year/title/path
ah filings show SYMBOL KIND [--year Y]    # print filing text (head 80 lines by default, --full for full)
```

Examples:
```
$ ah filings list
symbol       n_annual  has_ipo  n_research
600519.SH    6         true     6

$ ah filings list 600519.SH
kind     year   title                                     path
annual   2025   -                                         .../年报-2025.md
annual   2024   -                                         .../年报-2024.md
...
ipo      -      -                                         .../招股说明书.md
research 2026-04-01  aijianzhengquan - 首次覆盖报告        .../research/...
```

### 6.2 `ah profile`

```
ah profile list [SYMBOL]                       # table: symbol/date/n_sections/path
ah profile show SYMBOL [--date YYYY-MM-DD]     # print profile markdown (or latest if no date)
                      [--section NAME]          # print just one section
                      [--list-sections]         # print section headers only
```

Examples:
```
$ ah profile list
symbol       latest_date   n_profiles   n_sections
600519.SH    2026-04-28    1            14

$ ah profile show 600519.SH --list-sections
- Part 0 — 封面 & Executive Summary
- §1 能力圈
- §2 护城河
- §3 管理层
- §4 财务
- §4.5 排雷
- §5 估值
- §6 买入策略

$ ah profile show 600519.SH --section "§5 估值"
[markdown body of that section]
```

## 7. Testing

**Unit tests:**
- `tests/unit/filings/test_filings_repository.py`
  - list symbols (seed fixture with 2 fake tickers)
  - list_filings includes annual + ipo + research in expected order
  - get_annual raises FileNotFoundError when year missing
  - latest_annual returns the highest year
  - filenames with non-ASCII characters (`年报-2024.md`) are parsed correctly
- `tests/unit/filings/test_profile_repository.py`
  - skips `-evaluation.md`
  - section parser handles H2 / H3 / no-header cases
  - section parser preserves Chinese headers
  - latest() returns the highest-date profile
- `tests/unit/scripts/test_cli_filings.py` — typer.CliRunner smoke tests (list + show)
- `tests/unit/scripts/test_cli_profile.py` — typer.CliRunner smoke tests

**Integration:**
- `tests/integration/test_filings_real_data.py` — reads the real `data/filings/600519.SH/` directory; asserts at least 5 annual reports, 1 IPO, ≥1 research report detected
- `tests/integration/test_phase4_2_notebook_runs.py` — executes the acceptance notebook headless via nbclient

**Notebook:**
- `notebooks/phase4_2_filings_example.ipynb` — demonstrates listing filings for 600519.SH, fetching an annual report, listing profile sections, printing one section

## 8. Test fixtures

Create `tests/fixtures/phase4_2/` with two fake ticker dirs:
```
tests/fixtures/phase4_2/filings/
├── 600000.SH/
│   ├── 年报-2023.md
│   ├── 年报-2024.md
│   ├── 招股说明书.md
│   └── research/
│       └── broker-a-report-20240315.md
└── 000001.SZ/
    └── 年报-2024.md           # minimal

tests/fixtures/phase4_2/profiles/
├── 600000.SH-2026-04-28.md
├── 600000.SH-2026-04-28-evaluation.md  # skipped
└── 000001.SZ-2026-03-15.md
```

File contents are tiny (~100 bytes each), just enough to exercise the parser.

## 9. Error handling

| Situation | Behavior |
|---|---|
| Invalid symbol format | `ValidationError` (reuse Phase 1 `parse_symbol()`) |
| Unknown ticker directory | `FileNotFoundError` from the specific getter; `list_filings` returns `[]` |
| Corrupt / unreadable file | Bubble up `OSError` / `UnicodeDecodeError` — caller decides |
| `get_annual(symbol, year=9999)` when year missing | `FileNotFoundError` with clear message |
| `get_research` when `research/` dir missing | Return `[]` (not an error — research is optional) |

## 10. File inventory

**New:**
```
src/ah_research/filings/__init__.py
src/ah_research/filings/types.py
src/ah_research/filings/filings_repository.py
src/ah_research/filings/profile_repository.py
src/ah_research/scripts/ah_filings.py
src/ah_research/scripts/ah_profile.py
tests/unit/filings/__init__.py
tests/unit/filings/test_filings_repository.py
tests/unit/filings/test_profile_repository.py
tests/unit/scripts/test_cli_filings.py
tests/unit/scripts/test_cli_profile.py
tests/integration/test_filings_real_data.py
tests/integration/test_phase4_2_notebook_runs.py
tests/fixtures/phase4_2/... (as above)
notebooks/phase4_2_filings_example.ipynb
```

**Modified:**
```
src/ah_research/cli.py       # register filings_app and profile_app
CHANGELOG.md                  # Phase 4.2 entry
README.md                     # Features section
```

## 11. Acceptance criteria

- All unit and integration tests pass
- Acceptance notebook runs headless in CI
- `ah filings list` + `ah profile list` work on a fresh clone with real `data/filings/` + `profiles/` (Moutai present)
- Full `pytest` + `mypy src` green
