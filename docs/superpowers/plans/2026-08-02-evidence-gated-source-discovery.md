# Evidence-Gated Source Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a claim-level evidence gate that stops on sufficient authoritative evidence and escalates only unresolved claims through deterministic source, relationship, document, and dynamic-discovery layers.

**Architecture:** `source-discovery` owns four versioned JSON contracts, deterministic acceptance and time-series validation, layered route planning, source lineage, and route-cache ordering. Existing source capability profiles remain the seed registry; `read-filing` retains filing/event manifest ownership, while analysis Skills emit research requests and consume only accepted candidates with terminal ledgers.

**Tech Stack:** Python 3.12, JSON Schema Draft 2020-12, `jsonschema`, PyYAML, pytest, Markdown Skill contracts.

## Global Constraints

- Sufficient evidence stops immediately; only unresolved `claim_id` values escalate.
- Absence claims require every applicable route to reach a terminal state.
- Mixed definitions, units, and value statuses must not be silently joined.
- Source authority, conclusion evidence, originality, independence, and lineage remain separate dimensions.
- A technical failure or request budget limit is `blocked`, never evidence of absence.
- Existing annual, event, counterpart, and market manifest ownership does not move to `source-discovery`.
- Do not build a continuous general-purpose crawler.
- Preserve unrelated changes in the dirty worktree.
- `.agent/PLANS.md` is absent; this plan follows the repository's existing `docs/superpowers/plans/` convention and the `superpowers:writing-plans` format.

---

### Task 1: Capture Baseline Skill Failures

**Files:**
- Create: `tests/fixtures/source-discovery/pressure/evidence-gate-scenarios.yaml`
- Create: `docs/superpowers/validation/2026-08-02-source-discovery-baseline.md`
- Test: `tests/unit/skills/test_source_discovery_skill.py`

**Interfaces:**
- Consumes: approved design scenarios 1-10.
- Produces: pressure prompts and observed baseline failures that later Skill edits must correct.

- [ ] **Step 1: Add three pressure scenarios**

Create fixture cases for:

```yaml
scenarios:
  - id: official-source-early-stop
    pressures: [time, token-budget, apparent-completeness]
    expected: stop after the fitting official source passes all requirements
  - id: pop-mart-listing-applicant-expansion
    pressures: [stale-target-filings, familiar-source-bias, deadline]
    expected: continue to peer/listing-applicant and industry-overview documents
  - id: negative-enforcement-exhaustion
    pressures: [empty-first-result, time, user-demand-for-conclusion]
    expected: refuse an absence conclusion until every applicable official route is terminal
```

- [ ] **Step 2: Run fresh agents without the revised Skill**

Run each scenario without loading `.claude/skills/source-discovery/SKILL.md`. Record exact route choices, stopping points, and rationalizations in the baseline report.

- [ ] **Step 3: Add a failing static contract test**

Add assertions that the current Skill must contain the future observable rules:

```python
def test_source_discovery_requires_claim_level_acceptance_before_stopping() -> None:
    skill = SOURCE_DISCOVERY_SKILL.read_text(encoding="utf-8")
    assert "Only unresolved `claim_id` values escalate" in skill
    assert "absence claim" in skill
    assert "listing applicant" in skill
    assert "acceptance_failures" in skill
```

- [ ] **Step 4: Verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_discovery_skill.py -k claim_level_acceptance -v
```

Expected: FAIL because the current Skill lacks the complete claim-level contract.

---

### Task 2: Add Shared Research Contracts

**Files:**
- Create: `.claude/skills/source-discovery/references/research-request.schema.json`
- Create: `.claude/skills/source-discovery/references/candidate-claim.schema.json`
- Create: `.claude/skills/source-discovery/references/research-ledger.schema.json`
- Create: `.claude/skills/source-discovery/references/route-cache.schema.json`
- Create: `.claude/skills/source-discovery/scripts/research_contracts.py`
- Create: `tests/unit/skills/test_research_contracts.py`

**Interfaces:**
- Produces: `load_schema(name: str) -> dict[str, object]`.
- Produces: `validate_payload(schema_name: str, payload: Mapping[str, object]) -> None`.
- Produces: schema version `1.0` for request, candidate, ledger, and route-cache payloads.

- [ ] **Step 1: Write schema tests first**

Cover:

```python
def test_request_requires_explicit_acceptance_requirements() -> None: ...
def test_candidate_requires_scope_value_status_and_lineage() -> None: ...
def test_ledger_rejects_accepted_claim_with_failed_gate() -> None: ...
def test_ledger_rejects_absence_claim_with_unattempted_route() -> None: ...
def test_route_cache_cannot_store_acceptance_thresholds() -> None: ...
def test_uncataloged_candidate_is_valid_with_complete_runtime_provenance() -> None: ...
```

Use realistic payloads with `claim_id="cn-pop-toy-market-2020-2025"` and reject unknown fields.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_research_contracts.py -v
```

Expected: FAIL because schema files and `research_contracts.py` do not exist.

- [ ] **Step 3: Implement the schemas**

The request schema must require:

```text
schema_version, claim_id, claim_type, subject, metric, geographies,
industries, period_start, period_end, frequency, continuity_required,
required_latest_period, accepted_units, definition_constraints,
value_status_allowed, minimum_source_authority,
minimum_conclusion_evidence, minimum_originality,
minimum_independence, independent_cross_check_required, absence_claim, as_of
```

The candidate schema must require source/document identity, values with per-value status, scope, data vintage, artifact identity/hash, deterministic `scope_fingerprint`, `lineage_id`, and runtime evidence ratings.

The ledger schema must require claim status, every attempt's layer/relation/document/query/timestamps/artifact/lineage/terminal reason/acceptance failures, plus preserved unattempted routes for `blocked`.

- [ ] **Step 4: Implement deterministic validation**

`validate_payload` loads the named schema, runs `Draft202012Validator` with `FormatChecker`, reports the first error with its JSON path, then applies cross-field rules:

```python
if payload["status"] == "accepted" and payload["acceptance_failures"]:
    raise ValueError("accepted claim cannot retain acceptance failures")
if payload["absence_claim"] and payload["status"] == "exhausted":
    require_all_applicable_routes_terminal(payload["attempts"])
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_research_contracts.py -v
```

Expected: PASS.

---

### Task 3: Implement the Evidence Acceptance Gate

**Files:**
- Create: `.claude/skills/source-discovery/scripts/evidence_gate.py`
- Create: `tests/unit/skills/test_evidence_gate.py`
- Create: `tests/fixtures/source-discovery/evidence/pop-mart-industry-series.yaml`

**Interfaces:**
- Consumes: validated request and candidate mappings.
- Produces: `GateResult(passed: bool, failures: tuple[str, ...], scope_fingerprint: str)`.
- Produces: `evaluate_candidate(request, candidate, accepted_candidates=()) -> GateResult`.
- Produces: `evaluate_stitched_series(request, candidates) -> GateResult`.

- [ ] **Step 1: Add failing gate tests**

Required tests:

```python
def test_fitting_official_series_passes() -> None: ...
def test_missing_intermediate_year_fails_continuity() -> None: ...
def test_broader_ip_toy_scope_cannot_fill_pop_toy_gap() -> None: ...
def test_new_publication_repeating_old_forecast_fails_freshness() -> None: ...
def test_forecast_cannot_be_presented_as_observed() -> None: ...
def test_same_frost_lineage_does_not_count_as_independent() -> None: ...
def test_matching_overlap_allows_labeled_stitch() -> None: ...
def test_mismatched_overlap_rejects_stitch() -> None: ...
def test_stronger_source_conflict_blocks_acceptance() -> None: ...
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_evidence_gate.py -v
```

Expected: FAIL on missing module.

- [ ] **Step 3: Implement ordered gate checks**

Return stable failure codes in this order:

```python
(
    "identity",
    "scope",
    "continuity",
    "value_status",
    "freshness",
    "authority",
    "conclusion_evidence",
    "lineage",
    "conflict",
)
```

Use exact normalized scope fields for the fingerprint; never infer a bridge between different market definitions.

- [ ] **Step 4: Implement stitched-series checks**

Allow stitching only when units and fingerprints match, overlap values match exactly after declared conversion, and every output value retains source identity and status. Add `series_form="stitched"` to the accepted output contract.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_evidence_gate.py -v
```

Expected: PASS.

---

### Task 4: Add Layered Route Planning and Query Expansion

**Files:**
- Create: `.claude/skills/source-discovery/scripts/discovery_planner.py`
- Create: `.claude/skills/source-discovery/references/query-vocabulary.yaml`
- Create: `tests/unit/skills/test_discovery_planner.py`

**Interfaces:**
- Consumes: research request, source profiles, reviewed reachability, optional relation records, and completed ledger attempts.
- Produces: `RoutePlan(claim_id: str, current_layer: int, routes: tuple[PlannedRoute, ...])`.
- Produces: `plan_next_layer(...) -> RoutePlan | None`.
- Produces: `generate_query_variants(...) -> tuple[str, ...]`.

- [ ] **Step 1: Add failing planner tests**

Cover:

```python
def test_acceptance_prevents_next_layer() -> None: ...
def test_layer_order_is_monotonic() -> None: ...
def test_only_unresolved_claims_receive_routes() -> None: ...
def test_peer_listing_applicant_expansion_precedes_broad_search() -> None: ...
def test_query_variants_include_chinese_english_metric_and_document_terms() -> None: ...
def test_synonyms_do_not_change_definition_constraints() -> None: ...
def test_attempted_normalized_queries_are_deduplicated() -> None: ...
def test_negative_claim_keeps_planning_until_all_layers_terminal() -> None: ...
def test_resume_skips_accepted_claims_and_terminal_attempts() -> None: ...
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_discovery_planner.py -v
```

Expected: FAIL on missing planner.

- [ ] **Step 3: Implement six deterministic layers**

Map route layers exactly:

```python
BOUND_LOCAL = 0
HIGHEST_AUTHORITY = 1
SAME_FUNCTION_FALLBACK = 2
SUBJECT_RELATIONSHIP = 3
DOCUMENT_TYPE = 4
BROAD_DYNAMIC = 5
```

Parallelism is represented only within the returned current layer. The planner never returns routes from a later layer while an earlier applicable route is nonterminal.

- [ ] **Step 4: Implement relation/document templates**

For an industry series tied to a listed consumer company, Layer 3 emits direct peers, category leaders, and active/recent listing applicants; Layer 4 emits prospectus, listing application, industry overview, methodology appendix, association report, and archive document types.

- [ ] **Step 5: Implement controlled multilingual queries**

Load aliases from `query-vocabulary.yaml`, including:

```yaml
market-size: [市场规模, market size]
gmv: [GMV, 商品交易总额]
retail-sales-value: [零售销售额, retail sales value, RSV]
listing-application: [上市申请, application proof, prospectus]
industry-overview: [行业概览, industry overview]
```

Every generated variant carries the unchanged definition fingerprint.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_discovery_planner.py -v
```

Expected: PASS.

---

### Task 5: Add HKEX Listing-Applicant Discovery

**Files:**
- Create: `.claude/skills/source-discovery/references/sources/hkex-listing-applicants.yaml`
- Create: `.claude/skills/source-discovery/references/site-guides/hkex-listing-applicants.md`
- Modify: `.claude/skills/source-discovery/references/source-profile.schema.json`
- Modify: `.claude/skills/source-discovery/scripts/source_profiles.py`
- Modify: `.claude/skills/source-discovery/scripts/build_source_catalog.py`
- Modify: `.claude/skills/source-discovery/references/source-catalog.md`
- Modify: `tests/fixtures/source-discovery/scenarios/pop-mart.yaml`
- Modify: `tests/unit/skills/test_source_capability_profiles.py`

**Interfaces:**
- Adds source ID `hkex-listing-applicants`.
- Adds function ID `listing-applicant-documents`.
- Uses active applicant index `https://www1.hkexnews.hk/ncms/json/eds/appactive_app_sehk_e.json`.

- [ ] **Step 1: Add the failing Pop Mart regression**

Require the scenario to resolve TOP TOY application ID `108384`, open:

```text
https://www1.hkexnews.hk/app/sehk/2026/108384/a131511/sehk26033103632.pdf
```

and preserve the China pop-toy series:

```text
2020=249, 2021=345, 2022=352, 2023=430, 2024=587, 2025=875, unit=亿元
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py -k listing_applicant -v
```

Expected: FAIL because the source profile and route do not exist.

- [ ] **Step 3: Add the source profile and guide**

The guide must define active/inactive index identity, application ID, issuer, publication date, document path, version/replacement relation, and final PDF identity. Search indexes are discovery records; the opened application PDF is the evidence artifact.

- [ ] **Step 4: Extend profile metadata only as needed**

Add optional function metadata for `document_types` and `relationship_uses`; retain `additionalProperties=false` and existing profile compatibility.

- [ ] **Step 5: Regenerate and check the catalog**

Run:

```bash
uv run python .claude/skills/source-discovery/scripts/build_source_catalog.py \
  --profiles .claude/skills/source-discovery/references/sources \
  --snapshot .claude/skills/source-discovery/references/reachability-snapshot.json \
  --output .claude/skills/source-discovery/references/source-catalog.md
uv run python .claude/skills/source-discovery/scripts/build_source_catalog.py \
  --profiles .claude/skills/source-discovery/references/sources \
  --snapshot .claude/skills/source-discovery/references/reachability-snapshot.json \
  --output .claude/skills/source-discovery/references/source-catalog.md --check
```

- [ ] **Step 6: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py -v
```

Expected: PASS.

---

### Task 6: Add Lineage and Successful-Route Cache

**Files:**
- Create: `.claude/skills/source-discovery/scripts/source_lineage.py`
- Create: `.claude/skills/source-discovery/scripts/route_cache.py`
- Create: `tests/unit/skills/test_source_lineage.py`
- Create: `tests/unit/skills/test_route_cache.py`

**Interfaces:**
- Produces: `lineage_id(candidate) -> str`.
- Produces: `same_lineage(left, right) -> bool`.
- Produces: `load_route_cache(path, now) -> list[RouteRecipe]`.
- Produces: `rank_with_route_cache(routes, recipes) -> tuple[PlannedRoute, ...]`.
- Produces: `record_success(recipe, path) -> None`.

- [ ] **Step 1: Write failing lineage tests**

Assert that a KPMG publication citing Frost & Sullivan shares the Frost lineage, while an official statistics series and a separately produced consultant series do not.

- [ ] **Step 2: Write failing cache tests**

Assert that cache recipes can reorder fitting routes but cannot alter request thresholds, evidence ratings, scope fingerprints, gate results, or layer ordering.

- [ ] **Step 3: Verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_lineage.py tests/unit/skills/test_route_cache.py -v
```

Expected: FAIL on missing modules.

- [ ] **Step 4: Implement deterministic lineage**

Prefer explicit underlying dataset/report IDs. Otherwise hash normalized original publisher, report title, methodology owner, data vintage, and cited source identifiers. Immediate publisher alone must not create independence.

- [ ] **Step 5: Implement atomic route-cache persistence**

Write a temporary JSON file in the same directory, validate it, then replace the target. Cache keys include claim type, geography, industry, relation, document type, and source function; recipes include query pattern, index endpoint, identity rule, extraction hint, and reviewed timestamp.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_source_lineage.py tests/unit/skills/test_route_cache.py -v
```

Expected: PASS.

---

### Task 7: Rewrite `source-discovery` Around the Gate

**Files:**
- Modify: `.claude/skills/source-discovery/SKILL.md`
- Modify: `.claude/skills/source-discovery/references/search-playbook.md`
- Modify: `tests/unit/skills/test_source_discovery_skill.py`
- Modify: `docs/superpowers/validation/2026-08-02-source-discovery-baseline.md`

**Interfaces:**
- Consumes and emits the four shared schemas.
- Calls the acceptance gate after every layer.
- Returns accepted candidates and unresolved terminal claims; never writes company analysis.

- [ ] **Step 1: Use the baseline failures to write minimal guidance**

Replace the fixed always-broad workflow with:

```text
decompose request -> validate request -> execute current layer ->
validate candidate(s) -> stop accepted claims -> escalate unresolved claims ->
terminal ledger handoff
```

- [ ] **Step 2: Add explicit stop/escalate conditions**

The Skill must state:

```text
Only unresolved `claim_id` values escalate.
Positive claims stop immediately after the acceptance gate passes.
Absence claims stop only after every applicable route is terminal.
Route count is not an acceptance criterion.
```

- [ ] **Step 3: Add output shape**

Require top-level `requests`, `accepted_candidates`, `unresolved_claims`, `ledger_path`, `ledger_sha256`, and `status`. An empty result without a terminal ledger is invalid output.

- [ ] **Step 4: Re-run pressure scenarios with the revised Skill**

Record whether each fresh agent stops early, finds the TOP TOY application route, and refuses premature absence. Add any new rationalizations and close only observed loopholes.

- [ ] **Step 5: Verify Skill and code tests**

Run:

```bash
uv run pytest \
  tests/unit/skills/test_source_discovery_skill.py \
  tests/unit/skills/test_research_contracts.py \
  tests/unit/skills/test_evidence_gate.py \
  tests/unit/skills/test_discovery_planner.py -v
```

Expected: PASS.

---

### Task 8: Add Structured `read-filing` Handoff

**Files:**
- Modify: `.claude/skills/read-filing/SKILL.md`
- Create: `.claude/skills/read-filing/references/external-research-handoff.md`
- Modify: `tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Produces a validated research request only when required evidence is outside bound annual/event/counterpart manifests.
- Distinguishes `not_present_in_selected_filing` from `public_availability_unresolved`.

- [ ] **Step 1: Add failing contract assertions**

Assert that `read-filing` names `research-request.schema.json`, emits `claim_id`, preserves the parent manifest hashes, and never maps a missing filing fact directly to public absence.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_financial_skill_contracts.py -k external_research_handoff -v
```

Expected: FAIL.

- [ ] **Step 3: Document the handoff**

Define the two gap states, request construction, manifest boundary, and return consumption. Filing and event source discovery remain in `read-filing`; peer/listing-applicant industry evidence routes to `source-discovery`.

- [ ] **Step 4: Verify GREEN**

Run the same targeted command and expect PASS.

---

### Task 9: Migrate Analysis Skills One at a Time

**Files:**
- Modify: `.claude/skills/product-analysis/SKILL.md`
- Modify: `.claude/skills/management-analysis/SKILL.md`
- Modify: `.claude/skills/financial-redflag-scan/SKILL.md`
- Modify: `.claude/skills/value-profile/SKILL.md`
- Modify: `tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Child Skills define acceptance requirements and consume accepted candidates.
- `value-profile` owns the run-level ledger and accepted candidate identities.

- [ ] **Step 1: Add failing product-analysis assertions**

Require explicit request requirements for category size, market share, customer behavior, and competitor benchmarks. Replace the fixed global retry interpretation with per-route retries plus layered escalation.

- [ ] **Step 2: Update product-analysis and verify**

Run:

```bash
uv run pytest tests/unit/skills/test_financial_skill_contracts.py -k product_discovery_contract -v
```

- [ ] **Step 3: Add failing management-analysis assertions**

Require terminal ledger status before pending/manual conclusions for external commitments, governance events, counterpart evidence, and regulatory context; forbid weak sources for private intent or culture.

- [ ] **Step 4: Update management-analysis and verify**

Run:

```bash
uv run pytest tests/unit/skills/test_financial_skill_contracts.py -k management_discovery_contract -v
```

- [ ] **Step 5: Add failing red-flag assertions**

Require route exhaustion before negative enforcement conclusions and preserve audited statements as the only source for audited values.

- [ ] **Step 6: Update financial-redflag-scan and verify**

Run:

```bash
uv run pytest tests/unit/skills/test_financial_skill_contracts.py -k redflag_discovery_contract -v
```

- [ ] **Step 7: Add failing value-profile assertions**

Require one run-level ledger, dispatch only unresolved claims, persist accepted candidate identities, and prohibit `没有`, `查不到`, or `需人工` from an empty/failed route.

- [ ] **Step 8: Update value-profile and verify**

Run:

```bash
uv run pytest tests/unit/skills/test_financial_skill_contracts.py -k value_profile_discovery_contract -v
```

---

### Task 10: End-to-End Regression and Quality Gate

**Files:**
- Modify: `tests/fixtures/source-discovery/scenarios/guizhou-moutai.yaml`
- Create: `tests/fixtures/source-discovery/scenarios/evidence-gate-cross-industry.yaml`
- Modify: `tests/unit/skills/test_source_capability_profiles.py`
- Modify: `tests/unit/skills/test_source_discovery_skill.py`

**Interfaces:**
- Verifies all success criteria without live-network dependence.

- [ ] **Step 1: Add cross-industry forward scenarios**

Include one official-statistics early-stop case and one unrelated listing-applicant industry case. Assert accepted claims do not generate Layer 5 routes and unresolved claims do.

Also include an uncataloged original that passes runtime identity/provenance
validation, and a resumed ledger where accepted candidates and completed route
attempts are reused without duplicate network work.

- [ ] **Step 2: Run all source-discovery tests**

Run:

```bash
uv run pytest \
  tests/unit/skills/test_source_capability_profiles.py \
  tests/unit/skills/test_source_reachability_probe.py \
  tests/unit/skills/test_source_discovery_skill.py \
  tests/unit/skills/test_research_contracts.py \
  tests/unit/skills/test_evidence_gate.py \
  tests/unit/skills/test_discovery_planner.py \
  tests/unit/skills/test_source_lineage.py \
  tests/unit/skills/test_route_cache.py -v
```

Expected: PASS.

- [ ] **Step 3: Run cross-Skill contract tests**

Run:

```bash
uv run pytest tests/unit/skills/test_financial_skill_contracts.py -v
```

Expected: PASS.

- [ ] **Step 4: Run lint and catalog checks**

Run:

```bash
uv run ruff check \
  .claude/skills/source-discovery/scripts \
  tests/unit/skills/test_research_contracts.py \
  tests/unit/skills/test_evidence_gate.py \
  tests/unit/skills/test_discovery_planner.py \
  tests/unit/skills/test_source_lineage.py \
  tests/unit/skills/test_route_cache.py
uv run python .claude/skills/source-discovery/scripts/build_source_catalog.py \
  --profiles .claude/skills/source-discovery/references/sources \
  --snapshot .claude/skills/source-discovery/references/reachability-snapshot.json \
  --output .claude/skills/source-discovery/references/source-catalog.md --check
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Review the diff against the approved design**

Confirm every design regression has a test, no caller can weaken its request silently, accepted claims stop before broad discovery, and no absence statement can be derived from an empty or failed route.
