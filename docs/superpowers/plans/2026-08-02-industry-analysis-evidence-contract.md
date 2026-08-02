# Industry Analysis Evidence Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable, machine-validated industry evidence bundle that preserves five-year history, forecast vintages, concentration, company and competitor shares, scope breaks, and explicit unresolved gaps.

**Architecture:** Keep candidate-level acceptance in the existing evidence gate. Add an `industry-analysis-bundle` schema plus a focused `industry_bundle.py` aggregate gate that validates role coverage and derives `complete`, `publishable-with-gaps`, or `blocked`. Update `source-discovery` and `value-profile` to construct and render the same bundle contract, then prove portability with deterministic Pop Mart, Kweichow Moutai, and SMIC fixtures.

**Tech Stack:** Python 3.12, JSON Schema Draft 2020-12, pytest, YAML fixtures, Markdown skills.

## Global Constraints

- Target the latest five completed annual periods and extend to ten only when public evidence permits.
- Search H1, YTD, or quarter data separately; never annualize it or compare it directly with full years.
- Keep observed, historical-estimate, and forecast values distinct.
- Never stitch different geography, population, product scope, channel scope, metric, unit, measurement basis, or period semantics without a documented reproducible reconciliation.
- Treat multiple publications of the same provider table as one lineage.
- Missing public evidence produces `partial`, `exhausted`, or `blocked`; it never becomes factual absence.
- `publishable-with-gaps` may continue into the profile only when every missing period, scope break, and terminal route state is rendered.
- Broker target prices, ratings, and issuer earnings forecasts remain outside this bundle.
- All semantic tests are offline and deterministic; live tests cover reachability only.

---

### Task 1: Register the Industry Bundle Contract

**Files:**
- Create: `.claude/skills/source-discovery/references/industry-analysis-bundle.schema.json`
- Modify: `.claude/skills/source-discovery/scripts/research_contracts.py`
- Modify: `tests/unit/skills/test_research_contracts.py`

**Interfaces:**
- Consumes: `research_contracts.load_schema(name)` and `research_contracts.validate_payload(schema_name, payload)`.
- Produces: canonical schema name `industry-analysis-bundle`, alias `industry-bundle`, and schema validation for the payload consumed by Task 2.

- [ ] **Step 1: Write failing schema registration tests**

Add tests that require both canonical and alias loading:

```python
def test_industry_analysis_bundle_schema_is_registered() -> None:
    contracts = load_contracts_module()

    canonical = contracts.load_schema("industry-analysis-bundle")
    alias = contracts.load_schema("industry-bundle")

    assert canonical["title"] == "Industry Analysis Bundle"
    assert alias == canonical
```

Add a fixture helper in the test file:

```python
def industry_bundle_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "subject": "Pop Mart",
        "as_of": "2026-08-02",
        "primary_market_scope_fingerprint": "a" * 64,
        "status": "publishable-with-gaps",
        "roles": [
            {
                "role": role,
                "claim_ids": [f"pop-mart-{role}"],
                "state": "partial" if role == "subject-market-share" else "accepted",
                "required_periods": (
                    ["2021", "2022", "2023", "2024", "2025"]
                    if role in {
                        "historical-market-size",
                        "subject-market-share",
                        "competitor-market-share",
                    }
                    else []
                ),
                "accepted_periods": (
                    ["2021", "2022", "2024", "2025"]
                    if role == "subject-market-share"
                    else (
                        ["2021", "2022", "2023", "2024", "2025"]
                        if role in {
                            "historical-market-size",
                            "competitor-market-share",
                        }
                        else []
                    )
                ),
                "missing_periods": ["2023"] if role == "subject-market-share" else [],
                "scope_fingerprints": ["a" * 64],
                "lineage_ids": [f"lineage-{role}"],
                "ledger_paths": [f"research/{role}.json"],
                "gap_reason": (
                    "No comparable 2023 public company-share table"
                    if role == "subject-market-share"
                    else None
                ),
                "not_applicable_reason": None,
            }
            for role in (
                "market-definition",
                "historical-market-size",
                "industry-forecast",
                "market-concentration",
                "subject-market-share",
                "competitor-market-share",
                "current-partial-period",
                "industry-drivers",
            )
        ],
        "scope_breaks": [],
        "unresolved_claim_ids": ["pop-mart-subject-market-share"],
    }
```

Test valid and invalid enum handling:

```python
def test_industry_bundle_schema_rejects_unknown_role_state() -> None:
    contracts = load_contracts_module()
    payload = industry_bundle_payload()
    payload["roles"][0]["state"] = "done"

    with pytest.raises(ValueError, match="industry-analysis-bundle violates schema"):
        contracts.validate_payload("industry-bundle", payload)
```

- [ ] **Step 2: Run the registration tests and verify RED**

Run:

```bash
uv run pytest -q \
  tests/unit/skills/test_research_contracts.py::test_industry_analysis_bundle_schema_is_registered \
  tests/unit/skills/test_research_contracts.py::test_industry_bundle_schema_rejects_unknown_role_state
```

Expected: FAIL because `industry-analysis-bundle` is not registered.

- [ ] **Step 3: Add the JSON schema**

Define these required top-level fields:

```json
[
  "schema_version",
  "subject",
  "as_of",
  "primary_market_scope_fingerprint",
  "status",
  "roles",
  "scope_breaks",
  "unresolved_claim_ids"
]
```

Use:

```json
{
  "status": {
    "enum": ["complete", "publishable-with-gaps", "blocked"]
  }
}
```

Each role object requires:

```json
[
  "role",
  "claim_ids",
  "state",
  "required_periods",
  "accepted_periods",
  "missing_periods",
  "scope_fingerprints",
  "lineage_ids",
  "ledger_paths",
  "gap_reason",
  "not_applicable_reason"
]
```

Role names are the eight names used in `industry_bundle_payload()`. Role states are:

```json
["accepted", "partial", "exhausted", "blocked", "not-applicable"]
```

Scope breaks require `from_scope_fingerprint`, `to_scope_fingerprint`, `reason`, and `comparable`, with `comparable` fixed to `false`. All schema objects use `additionalProperties: false`.

- [ ] **Step 4: Register the schema and alias**

Update:

```python
SCHEMA_FILENAMES = {
    # existing entries
    "industry-analysis-bundle": "industry-analysis-bundle.schema.json",
}
SCHEMA_ALIASES = {
    # existing entries
    "industry-bundle": "industry-analysis-bundle",
}
```

No semantic bundle rules belong in `research_contracts.py`; Task 2 owns them.

- [ ] **Step 5: Run Task 1 tests and verify GREEN**

Run:

```bash
uv run pytest -q tests/unit/skills/test_research_contracts.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add \
  .claude/skills/source-discovery/references/industry-analysis-bundle.schema.json \
  .claude/skills/source-discovery/scripts/research_contracts.py \
  tests/unit/skills/test_research_contracts.py
git diff --cached --check
git commit -m "Add industry bundle contract"
```

---

### Task 2: Implement the Bundle-Level Gate

**Files:**
- Create: `.claude/skills/source-discovery/scripts/industry_bundle.py`
- Create: `tests/unit/skills/test_industry_bundle.py`

**Interfaces:**
- Consumes: validated role outcome mappings and `research_contracts.validate_payload("industry-bundle", payload)`.
- Produces:

```python
REQUIRED_ROLES: tuple[str, ...]

def completed_annual_periods(as_of: date, years: int = 5) -> tuple[str, ...]: ...

def forecast_annual_periods(
    as_of: date,
    years: int,
) -> tuple[str, ...]: ...

def evaluate_industry_bundle(
    *,
    subject: str,
    as_of: date,
    primary_market_scope_fingerprint: str,
    role_outcomes: Sequence[Mapping[str, object]],
    scope_breaks: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing period-window tests**

```python
def test_period_windows_derive_from_as_of() -> None:
    bundle = load_bundle_module()

    assert bundle.completed_annual_periods(date(2026, 8, 2)) == (
        "2021", "2022", "2023", "2024", "2025"
    )
    assert bundle.forecast_annual_periods(date(2026, 8, 2), 5) == (
        "2026", "2027", "2028", "2029", "2030"
    )
```

Require `years` to be five through ten for completed periods and three through five for forecast periods.

- [ ] **Step 2: Write failing role-state tests**

Create `role_outcome(role, ...)` with the schema fields from Task 1. Add tests proving:

- eight accepted roles produce `complete`;
- a subject-share role with accepted 2021, 2022, 2024, and 2025 plus missing 2023 produces `publishable-with-gaps`;
- a blocked required role makes the bundle `blocked`;
- an exhausted role has no accepted periods and requires ledger paths plus `gap_reason`;
- `not-applicable` is accepted only for `current-partial-period` and `industry-drivers`;
- accepted historical, forecast, concentration, subject-share, and competitor-share roles reject more than one scope fingerprint;
- unknown, duplicate, or missing roles fail;
- unresolved claim IDs are derived from partial, exhausted, and blocked roles.

Example assertion:

```python
def test_incompatible_scope_fingerprints_cannot_form_accepted_series() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    historical = next(
        outcome for outcome in outcomes
        if outcome["role"] == "historical-market-size"
    )
    historical["scope_fingerprints"] = ["a" * 64, "b" * 64]

    with pytest.raises(ValueError, match="one scope fingerprint"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=date(2026, 8, 2),
            primary_market_scope_fingerprint="a" * 64,
            role_outcomes=outcomes,
        )
```

- [ ] **Step 3: Run Task 2 tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/skills/test_industry_bundle.py
```

Expected: FAIL because `industry_bundle.py` does not exist.

- [ ] **Step 4: Implement the minimal aggregate gate**

Implementation rules:

```python
REQUIRED_ROLES = (
    "market-definition",
    "historical-market-size",
    "industry-forecast",
    "market-concentration",
    "subject-market-share",
    "competitor-market-share",
    "current-partial-period",
    "industry-drivers",
)
```

Validate exact role inventory, unique claim IDs, state-specific period and reason invariants, and one accepted scope fingerprint for comparable series roles.

Derive status with:

```python
if any(role["state"] == "blocked" for role in roles):
    status = "blocked"
elif any(role["state"] in {"partial", "exhausted"} for role in roles):
    status = "publishable-with-gaps"
else:
    status = "complete"
```

Derive unresolved claims from every role in `partial`, `exhausted`, or `blocked`. Sort roles by `REQUIRED_ROLES`, preserve scope breaks, then call `validate_payload("industry-bundle", payload)` before returning.

- [ ] **Step 5: Run Task 2 tests and verify GREEN**

Run:

```bash
uv run pytest -q \
  tests/unit/skills/test_industry_bundle.py \
  tests/unit/skills/test_research_contracts.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  .claude/skills/source-discovery/scripts/industry_bundle.py \
  tests/unit/skills/test_industry_bundle.py
git diff --cached --check
git commit -m "Gate industry evidence bundles"
```

---

### Task 3: Make Both Skills Consume the Bundle

**Files:**
- Modify: `.claude/skills/source-discovery/SKILL.md`
- Modify: `.claude/skills/source-discovery/references/search-playbook.md`
- Modify: `.claude/skills/value-profile/SKILL.md`
- Modify: `.claude/skills/value-profile/template-zh.md`
- Modify: `.claude/skills/value-profile/references/profile-writing-style.md`
- Modify: `tests/unit/skills/test_source_discovery_skill.py`
- Modify: `tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes: Task 2 `evaluate_industry_bundle(...)` payload.
- Produces: mandatory request roles, version-chase workflow, bundle handoff, and fixed profile output blocks.

- [ ] **Step 1: Write failing source-discovery contract tests**

Add a test requiring:

```python
for role in (
    "market-definition",
    "historical-market-size",
    "industry-forecast",
    "market-concentration",
    "subject-market-share",
    "competitor-market-share",
    "current-partial-period",
    "industry-drivers",
):
    assert f"`{role}`" in industry_section
```

Also require these rules:

```text
version chase
publishable-with-gaps
Only unresolved roles continue through the planner.
Broader, narrower, or adjacent markets cannot fill the primary-market requirement.
```

The playbook test must require searching a discovered table by exact table title, provider, publication vintage, prior version, and later version.

- [ ] **Step 2: Write failing value-profile and template tests**

Require the skill to consume bundle status rather than prose completion. Require these exact profile blocks:

```text
市场定义矩阵
历史市场规模与逐年增速
预测版本对照
集中度与竞争对手
当期部分期间
口径断点与未解决缺口
```

Require `complete`, `publishable-with-gaps`, and `blocked` handling. Assert that `publishable-with-gaps` may continue but must render missing years, terminal route status, and next evidence needed.

- [ ] **Step 3: Run Task 3 tests and verify RED**

Run:

```bash
uv run pytest -q \
  tests/unit/skills/test_source_discovery_skill.py \
  tests/unit/skills/test_financial_skill_contracts.py
```

Expected: new assertions fail because the bundle handoff and fixed blocks are absent.

- [ ] **Step 4: Update source-discovery**

In the industry section:

- construct all eight role requests before routing;
- derive the latest completed five-year window from `AS_OF`;
- search each unresolved role independently;
- run a mandatory version chase after finding any forecast;
- preserve partial accepted evidence;
- call `evaluate_industry_bundle`;
- return `industry_bundle`, `ledger_path`, and `ledger_sha256`;
- never convert `exhausted` or `blocked` into absence.

In the playbook, add query patterns:

```text
"{exact table title}" "{provider}" "{publication year}" filetype:pdf
"{provider}" "{industry}" forecast "{prior year}" filetype:pdf
"{provider}" "{industry}" forecast "{later year}" filetype:pdf
```

- [ ] **Step 5: Update value-profile and its template**

Replace the generic industry prompts with the six fixed blocks. Each table includes market scope, measurement basis, provider, lineage, and machine references. The final block includes role state, missing periods, ledger path, terminal route status, and next evidence needed.

State handling:

- `complete`: render all blocks normally;
- `publishable-with-gaps`: retain accepted values, render every gap, and continue the profile;
- `blocked`: retain accepted values, render blocked routes, mark the industry chapter for manual follow-up, and do not claim factual absence.

- [ ] **Step 6: Run Task 3 tests and verify GREEN**

Run:

```bash
uv run pytest -q \
  tests/unit/skills/test_source_discovery_skill.py \
  tests/unit/skills/test_financial_skill_contracts.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add \
  .claude/skills/source-discovery/SKILL.md \
  .claude/skills/source-discovery/references/search-playbook.md \
  .claude/skills/value-profile/SKILL.md \
  .claude/skills/value-profile/template-zh.md \
  .claude/skills/value-profile/references/profile-writing-style.md \
  tests/unit/skills/test_source_discovery_skill.py \
  tests/unit/skills/test_financial_skill_contracts.py
git diff --cached --check
git commit -m "Require industry evidence bundles"
```

---

### Task 4: Add Cross-Industry Regression Fixtures

**Files:**
- Create: `tests/fixtures/source-discovery/industry-bundles/pop-mart.yaml`
- Create: `tests/fixtures/source-discovery/industry-bundles/kweichow-moutai.yaml`
- Create: `tests/fixtures/source-discovery/industry-bundles/smic.yaml`
- Create: `tests/unit/skills/test_industry_bundle_fixtures.py`

**Interfaces:**
- Consumes: Task 2 `evaluate_industry_bundle(...)`.
- Produces: deterministic regression coverage for consumer collectibles, premium baijiu, and semiconductor foundry markets.

- [ ] **Step 1: Write the failing fixture test**

Parameterize all three fixtures:

```python
@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    (
        ("pop-mart.yaml", "publishable-with-gaps"),
        ("kweichow-moutai.yaml", "publishable-with-gaps"),
        ("smic.yaml", "publishable-with-gaps"),
    ),
)
def test_cross_industry_bundle_fixture(
    fixture_name: str,
    expected_status: str,
) -> None:
    payload = load_fixture(fixture_name)
    result = bundle.evaluate_industry_bundle(
        subject=payload["subject"],
        as_of=date.fromisoformat(payload["as_of"]),
        primary_market_scope_fingerprint=payload[
            "primary_market_scope_fingerprint"
        ],
        role_outcomes=payload["role_outcomes"],
        scope_breaks=payload["scope_breaks"],
    )

    assert result["status"] == expected_status
    assert result["unresolved_claim_ids"] == payload["unresolved_claim_ids"]
```

Add assertions that every fixture has eight roles and at least one explicit scope break.

- [ ] **Step 2: Run the fixture test and verify RED**

Run:

```bash
uv run pytest -q tests/unit/skills/test_industry_bundle_fixtures.py
```

Expected: FAIL because the fixtures do not exist.

- [ ] **Step 3: Add the Pop Mart fixture**

Encode:

- accepted 2021-2025 market-size history on the updated GMV scope;
- 2026-2030 GMV forecast;
- missing 2023 subject and competitor share;
- 2024 RSV versus 2025 GMV concentration scope break;
- KPMG and TOP TOY old forecast as one Frost & Sullivan lineage;
- current partial period as `not-applicable` with a publication-cycle rationale.

- [ ] **Step 4: Add the Kweichow Moutai fixture**

Encode:

- total baijiu and premium baijiu as different product-scope fingerprints;
- volume and retail value as different measurement bases;
- missing continuous five-year brand-share evidence;
- accepted industry production or sales history where comparable;
- current partial period separated from annual history.

- [ ] **Step 5: Add the SMIC fixture**

Encode:

- foundry industry revenue, wafer shipments, installed capacity, and company
  accounting revenue as different measurement bases;
- accepted foundry-market share only where denominator and period match;
- missing competitor share years;
- forecast years kept separate from observed history.

- [ ] **Step 6: Run Task 4 tests and verify GREEN**

Run:

```bash
uv run pytest -q \
  tests/unit/skills/test_industry_bundle.py \
  tests/unit/skills/test_industry_bundle_fixtures.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add \
  tests/fixtures/source-discovery/industry-bundles \
  tests/unit/skills/test_industry_bundle_fixtures.py
git diff --cached --check
git commit -m "Test industry bundles across sectors"
```

---

### Task 5: Final Verification and Documentation Audit

**Files:**
- Verify only; modify prior task files only if a test exposes a defect.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: a verified branch ready for review.

- [ ] **Step 1: Run focused tests**

```bash
uv run pytest -q \
  tests/unit/skills/test_industry_bundle.py \
  tests/unit/skills/test_industry_bundle_fixtures.py \
  tests/unit/skills/test_research_contracts.py \
  tests/unit/skills/test_evidence_gate.py \
  tests/unit/skills/test_source_discovery_skill.py \
  tests/unit/skills/test_financial_skill_contracts.py
```

Expected: all tests pass.

- [ ] **Step 2: Run static checks**

```bash
uv run ruff check \
  .claude/skills/source-discovery/scripts/industry_bundle.py \
  tests/unit/skills/test_industry_bundle.py \
  tests/unit/skills/test_industry_bundle_fixtures.py
uv run ruff format --check \
  .claude/skills/source-discovery/scripts/industry_bundle.py \
  tests/unit/skills/test_industry_bundle.py \
  tests/unit/skills/test_industry_bundle_fixtures.py
```

Expected: both commands exit 0.

- [ ] **Step 3: Verify contract and documentation consistency**

```bash
uv run python - <<'PY'
import importlib.util
from pathlib import Path

path = Path(".claude/skills/source-discovery/scripts/research_contracts.py")
spec = importlib.util.spec_from_file_location("research_contracts", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.load_schema("industry-bundle")["title"] == "Industry Analysis Bundle"
print("industry bundle contract: OK")
PY
git diff --check main...HEAD
```

Expected: contract prints `OK`; diff check exits 0.

- [ ] **Step 4: Inspect final history and status**

```bash
git status --short --branch
git log --oneline --decorate main..HEAD
git diff --stat main...HEAD
```

Expected: only intentional feature commits and no uncommitted implementation files.
