# Phase 4.3 — Dossier + Filings/Profile Integration Design

**Status:** Draft (auto-authored per user directive "you decide all")
**Date:** 2026-04-30
**Depends on:** Phase 4.2 (merged at `b359f5e`) — uses `FilingsRepository` and `ProfileRepository`.

---

## 1. Mission

Bridge Phase 3's quantitative `Dossier` with Phase 4.2's qualitative markdown artifacts so that `Dossier.build(symbol)` returns a single structured object combining fundamentals/valuation bands with filings inventory and profile section references. Lets a user (or LLM) consume a company's complete research picture through one API call.

## 2. Scope (tight)

**In scope for 4.3:**
- New optional `Dossier` fields: `filings_section: FilingsSection | None`, `profile_section: ProfileSection | None`
- New `FilingsSection` + `ProfileSection` frozen dataclasses (lightweight — they reference Phase 4.2 objects, don't duplicate their content)
- `Dossier.build(symbol, *, include_qualitative: bool = True)` wires the two repositories into the build pipeline
- `Dossier.to_markdown()` appends "## Filings inventory" and "## Qualitative profile" sections when present
- CLI `ah dossier build <symbol> [--no-qualitative]` flag to toggle
- Tests + acceptance notebook

**Deferred (future phase):**
- Structured grading/scoring of profile content (moat_grade, redflag_count)
- Screener predicates backed by qualitative data (has_profile, moat_grade >= 'B')
- Research report deep-parsing or deduplication
- Any Dossier schema versioning / migration logic

## 3. Architecture

### 3.1 Module changes

**Modified:**
- `src/ah_research/analysis/dossier.py` — add two new optional section types, wire into builder
- `src/ah_research/scripts/ah_dossier.py` — add `--no-qualitative` flag
- `src/ah_research/cli.py` — no change (existing `ah dossier` sub-app already registered)

No new modules; no new runtime dependencies.

### 3.2 New types

```python
# src/ah_research/analysis/dossier.py (extension)

@dataclass(frozen=True)
class FilingsSection:
    n_annual: int
    latest_annual_year: int | None
    has_ipo: bool
    n_research: int
    latest_research_date: date | None
    latest_annual_path: str | None   # str, not Path — for JSON-friendly to_dict

@dataclass(frozen=True)
class ProfileSection:
    has_profile: bool
    latest_profile_date: date | None
    section_names: tuple[str, ...]  # top-level H2 headers from the latest profile
    latest_profile_path: str | None
```

Both are summary-only. Full `Filing` / `Profile` objects remain accessible via the repositories for deeper inspection. The `Dossier` stays lightweight and serializable.

### 3.3 `Dossier` extension

Add two optional fields to the existing `Dossier` frozen dataclass:

```python
@dataclass(frozen=True)
class Dossier:
    # ... existing fields ...
    filings_section: FilingsSection | None = None
    profile_section: ProfileSection | None = None
```

### 3.4 Builder integration

The existing `build_dossier(...)` (or equivalent) function gains a new `include_qualitative: bool = True` kwarg:

```python
def build_dossier(
    symbol: str,
    repo: DataRepository,
    *,
    as_of: pd.Timestamp | None = None,
    language: Literal["en", "zh"] = "en",
    include_qualitative: bool = True,
    filings_repo: FilingsRepository | None = None,
    profiles_repo: ProfileRepository | None = None,
) -> Dossier: ...
```

Defaults to constructing `FilingsRepository()` + `ProfileRepository()` with project-root defaults if not supplied. When `include_qualitative=False`, the new fields stay `None`.

Qualitative sections degrade gracefully: if the repositories exist but the specific symbol has no filings/profile, the corresponding section is still populated with `has_ipo=False`, `n_annual=0`, `has_profile=False`, etc. — never raises.

### 3.5 Markdown rendering

`Dossier.to_markdown()` appends (only when a section exists and has content):

```markdown
## Filings inventory

- Annual reports: 6 (latest: 2025)
- IPO prospectus: yes
- Analyst research: 6 reports (latest: 2026-04-01)
- Latest annual: `data/filings/600519.SH/年报-2025.md`

## Qualitative profile

- Profile date: 2026-04-28
- Sections (14):
  - Part 0 — 封面 & Executive Summary
  - §1 能力圈
  - §2 护城河
  - ...
- Path: `profiles/600519.SH-2026-04-28.md`
```

When neither section has content (no filings dir, no profile), render nothing (no stubs).

## 4. CLI

Existing `ah dossier build <symbol>` gains `--qualitative / --no-qualitative` (default: qualitative enabled):

```
$ ah dossier build 600519.SH --qualitative     # default
$ ah dossier build 600519.SH --no-qualitative  # quant-only
```

## 5. Testing

**Unit:**
- `tests/unit/analysis/test_dossier_qualitative.py`
  - `FilingsSection` / `ProfileSection` are frozen
  - `build_dossier(..., include_qualitative=True)` populates both sections when fixtures present
  - `build_dossier(..., include_qualitative=False)` leaves both `None`
  - Graceful degradation: unknown symbol → both sections return "empty" (counts=0, flags=False), not `None`
  - `Dossier.to_markdown()` emits `"## Filings inventory"` and `"## Qualitative profile"` headers when sections present
  - `Dossier.to_dict()` includes the new fields JSON-safely

**Integration:**
- `tests/integration/test_dossier_with_real_filings.py` — runs `build_dossier("600519.SH", ...)` against the real `data/filings/` + `profiles/` on disk; asserts Moutai's sections are populated (≥5 annual, has IPO, profile ≥1)

**CLI:**
- `tests/unit/scripts/test_cli_dossier_qualitative.py` — smoke test `--qualitative` / `--no-qualitative`

**Acceptance notebook:**
- `notebooks/phase4_3_dossier_qualitative_example.ipynb`
- Builds Moutai dossier both ways, renders markdown, prints a section-by-section comparison

## 6. Error handling

| Situation | Behavior |
|---|---|
| Invalid symbol format | `UserInputError` (reuse Phase 1 `parse_symbol()`) |
| `filings_repo` root doesn't exist | `FilingsSection(n_annual=0, has_ipo=False, n_research=0, ...)` — empty, not error |
| `profiles_repo` root doesn't exist | `ProfileSection(has_profile=False, ...)` — empty, not error |
| `include_qualitative=False` | both sections are `None` in result |
| Filings repo raises an OSError reading a file | Bubble up (implementer's intent: don't silently hide broken data) |

## 7. Reproducibility / JSON

`Dossier.to_dict()` must handle the new fields safely:
- `None` → `null`
- `FilingsSection` → `{"n_annual": 6, "latest_annual_year": 2025, ...}` (dates as ISO strings)
- `ProfileSection` → analogous

Existing `Dossier.inputs_hash` (if present) should include the qualitative sections' presence so two dossiers built with/without qualitative produce different hashes.

## 8. File inventory

**New:**
```
tests/unit/analysis/test_dossier_qualitative.py
tests/unit/scripts/test_cli_dossier_qualitative.py
tests/integration/test_dossier_with_real_filings.py
tests/integration/test_phase4_3_notebook_runs.py
notebooks/phase4_3_dossier_qualitative_example.ipynb
```

**Modified:**
```
src/ah_research/analysis/dossier.py           # add FilingsSection, ProfileSection, extend Dossier + builder
src/ah_research/scripts/ah_dossier.py         # add --qualitative / --no-qualitative flag
CHANGELOG.md                                   # Phase 4.3 entry
README.md                                      # Features bullet
```

## 9. Acceptance criteria

- All unit + integration + CLI tests pass
- Acceptance notebook runs headless
- `ah dossier build 600519.SH` on a real clone includes `## Filings inventory` and `## Qualitative profile` sections
- `uv run pytest` + `uv run mypy src` fully green
