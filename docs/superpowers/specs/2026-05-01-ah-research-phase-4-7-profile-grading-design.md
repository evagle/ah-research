# Phase 4.7 — LLM-Based Profile Grading

**Date:** 2026-05-01
**Depends on:** Phase 4.2 (`ProfileRepository`) — merged.

## Mission

Grade value-investing profiles via the Claude API into structured integer/letter fields — `moat_grade` (A–F), `mgmt_grade` (A–F), `redflag_count` (int ≥ 0), `confidence` (0.0–1.0) — with disk caching keyed by profile content hash so the same profile is never graded twice.

## Scope

**In scope:**
- `GradedProfile` frozen dataclass wrapping a `Profile` + 4 structured fields + raw rationale string
- `ProfileGrader(client, cache_dir=Path(".cache/profile_grades"))` service class
  - `grade(profile: Profile) -> GradedProfile`
  - Content-hash cache (sha256 of `profile.text`) as JSON files
  - Uses `claude-sonnet-4-6` (cheap, structured), with prompt caching on the system prompt
- CLI: `ah profile grade <symbol>` — grades latest profile, prints structured result
- Unit tests (mock Anthropic client — no real API calls) + integration test gated on `AH_RESEARCH_LIVE=1`

**Out of scope:**
- Batch grading (one profile at a time; cache handles repeated calls)
- Custom grading rubrics — one fixed rubric for 4.7
- Incorporating filings content — grades only the profile markdown
- Screener predicates using grades (Phase 4.8+)

## New dependency

- `anthropic>=0.40.0` — runtime dep in pyproject.toml

## Core types

```python
# src/ah_research/filings/grading.py

@dataclass(frozen=True)
class GradedProfile:
    profile: Profile
    moat_grade: Literal["A", "B", "C", "D", "F"]
    mgmt_grade: Literal["A", "B", "C", "D", "F"]
    redflag_count: int
    confidence: float  # 0.0-1.0, self-reported by the model
    rationale: str     # 3-5 sentence summary
    model: str         # e.g. "claude-sonnet-4-6"
    content_hash: str  # sha256(profile.text) — cache key
```

## API

```python
class ProfileGrader:
    def __init__(
        self,
        client: "Anthropic",
        *,
        cache_dir: Path = Path(".cache/profile_grades"),
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024,
    ): ...

    def grade(self, profile: Profile) -> GradedProfile: ...
```

### Pipeline

1. Compute `hash = sha256(profile.text).hexdigest()`
2. Check cache at `{cache_dir}/{hash}.json`; return on hit
3. Build messages:
   - System: fixed rubric (cacheable via `cache_control: {"type": "ephemeral"}`)
   - User: `<profile>{profile.text}</profile>\n\nReturn JSON with fields moat_grade, mgmt_grade, redflag_count, confidence, rationale.`
4. Call `client.messages.create(model=..., system=[...], messages=[...], max_tokens=...)`
5. Parse first JSON object from response text (model is told to return JSON-only)
6. Validate against pydantic-style schema; raise `ValidationError` if malformed
7. Wrap into `GradedProfile`; write JSON to cache; return

### Rubric (system prompt)

```
You are a conservative value-investing analyst. Grade the profile below on three
dimensions using strict criteria.

moat_grade (A-F):
  A — obvious, durable, quantified (e.g. "30-year brand, 60%+ share, pricing power demonstrated")
  B — clear but narrower (e.g. "strong in regional market, expanding")
  C — some moat signals but mixed (e.g. "network effect but competition intensifying")
  D — weak or contested moat
  F — commodity or structurally disadvantaged

mgmt_grade (A-F):
  A — track record, skin in the game, transparent capital allocation
  B — competent, some positives
  C — average
  D — concerning behavior (e.g. aggressive accounting, related-party tx)
  F — evidence of dishonesty

redflag_count: integer count of explicit red flags in §4.5 or equivalent sections.
  Count each distinct concern (aggressive revenue recognition, auditor switches,
  off-balance liabilities, etc.) once.

confidence: 0.0-1.0, your subjective certainty given the profile depth.

Return ONLY a JSON object with keys: moat_grade, mgmt_grade, redflag_count, confidence, rationale.
rationale is 3-5 sentences defending your grades.
```

## Cache file format

```json
{
  "content_hash": "abc...",
  "moat_grade": "A",
  "mgmt_grade": "B",
  "redflag_count": 2,
  "confidence": 0.7,
  "rationale": "...",
  "model": "claude-sonnet-4-6",
  "graded_at": "2026-05-01T12:00:00Z"
}
```

## CLI

```
ah profile grade <symbol> [--date YYYY-MM-DD] [--force] [--model MODEL]
```

- `--force` ignores cache
- Prints a Rich table with the 4 fields + rationale

## Tests

- `tests/unit/filings/test_grading.py`
  1. `grade()` returns GradedProfile with correct fields (mocked client)
  2. Cache hit returns without invoking client (mock verifies 0 calls)
  3. Cache miss invokes client exactly once
  4. Malformed JSON response raises ValidationError
  5. Invalid grade letter raises ValidationError
  6. `--force` bypasses cache
  7. Content hash is stable across identical profiles
- `tests/unit/scripts/test_cli_profile_grade.py` — 3 CLI smoke tests with mocked client
- `tests/integration/test_profile_grade_live.py` — skipped unless `AH_RESEARCH_LIVE=1`; real API call

## File inventory

**New:**
```
src/ah_research/filings/grading.py
tests/unit/filings/test_grading.py
tests/unit/scripts/test_cli_profile_grade.py
tests/integration/test_profile_grade_live.py
```

**Modified:**
```
pyproject.toml                              # add anthropic>=0.40
src/ah_research/filings/__init__.py         # export GradedProfile, ProfileGrader
src/ah_research/scripts/ah_profile.py       # add `grade` subcommand
CHANGELOG.md
README.md
```

## Acceptance

- Unit + CLI tests pass (no real API calls in CI)
- Live test works when env var set
- `pytest` + `mypy src` green
