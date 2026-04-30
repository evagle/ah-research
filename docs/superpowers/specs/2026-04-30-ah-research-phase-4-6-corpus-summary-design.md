# Phase 4.6 — Filings + Profile Corpus Summary

**Date:** 2026-04-30
**Depends on:** Phase 4.2 (`FilingsRepository`, `ProfileRepository`), Phase 4.4 (`enrich_with_filings`) — all merged.

## Mission

Single command to audit local research coverage — `ah filings summary` prints one row per ticker showing what filings exist, how fresh they are, whether a profile exists, and staleness in days. Answers "which companies am I under-researched on?" in one look.

## Scope

**In scope:**
- Pure function `build_corpus_summary(filings_repo, profiles_repo) -> pd.DataFrame` in `src/ah_research/filings/summary.py` — union of symbols from both repos with columns: `symbol`, `n_annual`, `latest_annual_year`, `has_ipo`, `n_research`, `latest_research_date`, `has_profile`, `latest_profile_date`, `profile_age_days`, `annual_staleness_years` (int, years since `latest_annual_year`; based on current year).
- CLI `ah filings summary [--sort-by COLUMN]` — rich table output, default sort by `profile_age_days` desc (most stale first) then symbol
- Unit tests + acceptance notebook

**Out of scope:** Grading / scoring, LLM, any write operations, universe-wide stats (just per-ticker).

## API

```python
def build_corpus_summary(
    filings_repo: FilingsRepository | None = None,
    profiles_repo: ProfileRepository | None = None,
    *,
    as_of: date | None = None,      # defaults to today; for deterministic tests
) -> pd.DataFrame:
    """One-row-per-ticker coverage table.

    Symbols = union(filings_repo.list_symbols(), profiles_repo.list_symbols()).
    """
```

Columns (all JSON-safe; nullable ints use pandas Int64, dates use ISO strings):
- `symbol: str`
- `n_annual: int64`
- `latest_annual_year: Int64` (nullable)
- `has_ipo: bool`
- `n_research: int64`
- `latest_research_date: datetime64[ns]` (nullable via NaT)
- `has_profile: bool`
- `latest_profile_date: datetime64[ns]` (nullable via NaT)
- `profile_age_days: Int64` (nullable — days between `as_of` and `latest_profile_date`, or NA)
- `annual_staleness_years: Int64` (nullable — `as_of.year - latest_annual_year`, or NA)

## CLI

```
ah filings summary
ah filings summary --sort-by annual_staleness_years
```

Prints a Rich table; uses the main `root` default (`data/filings` + `profiles`). Exits 0 on success, 1 if neither repo has any symbols (with a friendly message).

## Tests

- `tests/unit/filings/test_summary.py` — 6 tests:
  1. Empty repos → empty DataFrame with correct dtypes
  2. Fixture (phase4_2 dirs) returns 2-3 rows (600000.SH + 000001.SZ + whatever profile fixture provides)
  3. Deterministic `as_of` yields deterministic `profile_age_days`
  4. Missing profile → `profile_age_days` NA, `has_profile=False`
  5. Symbol present in profiles but not filings (or vice versa) → row still appears with defaults for the missing side
  6. Column dtypes are as specified
- `tests/unit/scripts/test_cli_filings_summary.py` — 3 smoke tests
- `tests/integration/test_phase4_6_notebook_runs.py` — notebook headless
- `notebooks/phase4_6_corpus_summary_example.ipynb`

## File inventory

**New:**
```
src/ah_research/filings/summary.py
tests/unit/filings/test_summary.py
tests/unit/scripts/test_cli_filings_summary.py
tests/integration/test_phase4_6_notebook_runs.py
notebooks/phase4_6_corpus_summary_example.ipynb
```

**Modified:**
```
src/ah_research/filings/__init__.py     # export build_corpus_summary
src/ah_research/scripts/ah_filings.py   # add `summary` subcommand
CHANGELOG.md
README.md
```

## Acceptance

- Unit + CLI + notebook tests pass
- `ah filings summary` on a real clone prints ≥1 row for 600519.SH
- `pytest` + `mypy src` green
