# Phase 4.5 — Filings Text Search Design

**Date:** 2026-04-30
**Depends on:** Phase 4.2 (`FilingsRepository`) — merged.

## 1. Mission

Let users grep the local filings corpus — all 年报, 招股说明书, research reports for all tickers — without writing their own file-walking code. Ship `FilingsRepository.search(query)` returning structured `SearchHit` results with file path + line number + matching snippet.

Makes ad-hoc discovery queries one-liners:
```python
repo.search("渠道改革")  # every filing mentioning it
repo.search("新车间", symbols=["600519.SH"])
```

## 2. Scope

**In scope:**
- `SearchHit` frozen dataclass: `filing: Filing, line_no: int, line: str, context: str`
- `FilingsRepository.search(query: str, *, symbols=None, kinds=None, regex=False, max_hits_per_file=None) -> list[SearchHit]`
- CLI: `ah filings search <query> [--symbols S1,S2] [--kinds annual,research] [--regex] [--max-per-file N]` — prints rich table of hits
- Unit tests + integration + acceptance notebook

**Out of scope:**
- Indexing / inverted index (just naive line-by-line scan — fine for corpora of O(10–100) tickers × 5 MB each)
- Fuzzy / embedding / semantic search
- Highlighting HTML output

## 3. API

```python
@dataclass(frozen=True)
class SearchHit:
    filing: Filing
    line_no: int        # 1-indexed
    line: str           # the matching line (stripped)
    context: str        # 3 lines before + match + 3 lines after, joined with \n


class FilingsRepository:
    # ... existing methods ...
    def search(
        self,
        query: str,
        *,
        symbols: Sequence[str] | None = None,   # None = all known symbols
        kinds: Sequence[FilingKind] | None = None,  # None = all kinds
        regex: bool = False,                     # treat query as regex pattern
        max_hits_per_file: int | None = None,    # None = no cap
    ) -> list[SearchHit]:
        """Substring (or regex) search across filings. Returns hits in
        stable order: symbol → kind → (year desc | research date desc) → line_no asc."""
```

## 4. Edge cases

| Input | Behavior |
|---|---|
| Empty query | `ValueError("query must be non-empty")` |
| `regex=True` + invalid pattern | `re.error` bubbles up |
| `symbols` contains unknown ticker | skip (not an error) |
| `kinds` contains unknown kind | `ValueError` |
| File unreadable | Skip file, log a warning via `logging.getLogger(__name__)` |
| Very long matching line | Truncate `line` field to 500 chars, append `"…"` |

## 5. Tests

- `tests/unit/filings/test_search.py`
  - empty query raises
  - substring match across multiple files in fixture
  - regex mode
  - `symbols` filter narrows correctly
  - `kinds` filter narrows correctly
  - `max_hits_per_file` caps per file
  - stable ordering
  - long line truncation
  - unreadable file is skipped, not fatal (via monkeypatch)
- `tests/unit/scripts/test_cli_filings_search.py` — typer CliRunner smoke tests
- `tests/integration/test_filings_search_real_data.py` — runs `repo.search("茅台")` against `data/filings/600519.SH/`; asserts >0 hits
- Acceptance notebook showing `repo.search("护城河")` on Moutai

## 6. File inventory

**New:**
```
tests/unit/filings/test_search.py
tests/unit/scripts/test_cli_filings_search.py
tests/integration/test_filings_search_real_data.py
tests/integration/test_phase4_5_notebook_runs.py
notebooks/phase4_5_filings_search_example.ipynb
```

**Modified:**
```
src/ah_research/filings/filings_repository.py  # add search() method + SearchHit dataclass
src/ah_research/filings/__init__.py             # export SearchHit
src/ah_research/scripts/ah_filings.py           # add `search` subcommand
CHANGELOG.md                                     # Phase 4.5 entry
README.md                                        # Features bullet
```

## 7. Acceptance

- Unit + integration tests pass
- `ah filings search 茅台 --symbols 600519.SH` works on real data
- Notebook runs headless
- `pytest` + `mypy src` green
