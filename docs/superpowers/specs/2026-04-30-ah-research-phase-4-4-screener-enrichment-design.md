# Phase 4.4 — Screener Filings Enrichment Design

**Status:** Draft (auto-authored per user directive "you decide all")
**Date:** 2026-04-30
**Depends on:** Phase 4.2 (`FilingsRepository`, `ProfileRepository`) — merged. Phase 4.3 (`FilingsSection`, `ProfileSection`) — open PR; we don't depend on that code.

## 1. Mission

Let Phase 3 Screener users filter a universe by qualitative-data presence without modifying the Screener itself. Ship one pure function — `enrich_with_filings(df, ...)` — that takes a symbol-indexed DataFrame and returns a new DataFrame with 5 new boolean / integer columns.

Users then filter with standard pandas: `df[df["has_profile"] & (df["n_annual"] >= 5)]`.

## 2. Scope (very tight)

**In scope:**
- `enrich_with_filings(df, filings_repo=None, profiles_repo=None) -> pd.DataFrame` — pure function in `src/ah_research/filings/enrichment.py`
- Adds columns: `has_ipo`, `n_annual`, `latest_annual_year`, `n_research`, `has_profile`
- Unit tests + a ~12-line acceptance notebook

**Deferred (out of scope for 4.4):**
- Structured grading/scoring (moat_grade, redflag_count) — requires LLM
- Screener class changes or new predicate types
- Profile section-based predicates (e.g. `has_section("§4.5 排雷")`)
- Performance optimization (N-symbol batch is fine for N ≤ 1000 small-file reads)

## 3. API

```python
# src/ah_research/filings/enrichment.py

def enrich_with_filings(
    df: pd.DataFrame,
    *,
    filings_repo: FilingsRepository | None = None,
    profiles_repo: ProfileRepository | None = None,
    symbol_col: str | None = None,   # None = use df.index
) -> pd.DataFrame:
    """Add filings + profile columns to a symbol-indexed DataFrame.

    New columns (all have sensible defaults if repo lookups return nothing):
      - has_ipo: bool
      - n_annual: int
      - latest_annual_year: Int64 (nullable)
      - n_research: int
      - has_profile: bool

    Repositories default to FilingsRepository() / ProfileRepository() with
    project-root defaults if not supplied.

    Returns a new DataFrame; does not mutate input.
    """
```

## 4. Edge cases

| Input | Behavior |
|---|---|
| Empty df | Return empty df with the 5 new columns present, typed correctly |
| Symbol not in any repo | Row gets `has_ipo=False, n_annual=0, latest_annual_year=pd.NA, n_research=0, has_profile=False` |
| Repository root missing | Same as above — empty repo behaves identically to "no data for this symbol" |
| `symbol_col="ticker"` provided | Read from that column instead of the index |
| Invalid symbol format in df | Skip that row (set all columns to defaults); do not raise |

## 5. Tests

- `tests/unit/filings/test_enrichment.py`
  - Empty df → 5 columns, correct dtypes
  - All defaults for unknown symbol
  - Real fixture: uses Phase 4.2's existing `tests/fixtures/phase4_2/{filings,profiles}` — `600000.SH` gets `n_annual=2, has_ipo=True, n_research=1, has_profile=True`
  - `symbol_col` parameter works
  - Does not mutate input df
  - Invalid symbol format doesn't raise

Plus a compact acceptance notebook `notebooks/phase4_4_screener_enrichment_example.ipynb` (~15 lines) showing `df = enrich_with_filings(screener_output); df[df["has_profile"]]`.

## 6. File inventory

**New:**
```
src/ah_research/filings/enrichment.py
tests/unit/filings/test_enrichment.py
notebooks/phase4_4_screener_enrichment_example.ipynb
tests/integration/test_phase4_4_notebook_runs.py
```

**Modified:**
```
src/ah_research/filings/__init__.py   # export enrich_with_filings
CHANGELOG.md                           # Phase 4.4 entry
README.md                              # Features bullet
```

## 7. Acceptance

- All unit tests pass
- Notebook runs headless
- `uv run pytest` + `uv run mypy src` green
