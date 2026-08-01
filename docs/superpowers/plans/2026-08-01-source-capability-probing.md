# Source Capability Discovery and Reachability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build structured per-website capability profiles, trust-first route selection, dynamic reachability probing, and maintained source guides, then validate the complete workflow with Guizhou Moutai and Pop Mart research scenarios.

**Architecture:** Store one YAML profile per actual website under the `source-discovery` skill, with deterministic Python tooling for validation, route selection, reachability classification, caching, and catalog generation. Keep ordinary tests offline; run explicit live probes into a local cache and promote only reviewed observations into a committed snapshot. Use parallel read-only subagents to explore independent source groups, then one integrator to normalize and commit profiles.

**Tech Stack:** Python 3.12 standard library, PyYAML, JSON Schema, pytest, Markdown skill references, `urllib.request`, subagent web/browser exploration.

## Global Constraints

- Preserve all unrelated dirty-worktree changes.
- Work in an isolated git worktree created from `ab9c064`.
- Keep ordinary pytest runs fully offline; live access requires `AH_RESEARCH_LIVE=1` or an explicit probe command.
- Match the required function before ranking candidates.
- For equivalent functions, sort by source authority, originality/independence, current reachability, then practical utility.
- Never elevate an aggregator or media copy over an available official or original source for the same function.
- A reachability change must not mutate source authority.
- Keep every access/provenance conclusion at explicit `High`, `Medium`, or `Low` evidence.
- Keep the source registry open-ended and add useful Hong Kong sources discovered beyond the supplied list.
- Write unreviewed runtime results only under gitignored `tmp/source-discovery/`.
- Commit only reviewed reachability observations.
- Use `reachable=30d`, `reachable-limited=30d`, `login-required=14d`, `paywalled=14d`, `anti-bot=14d`, `temporarily-unreachable=24h`, `moved=7d`, `broken-link=7d`, and `unverified=24h`.
- Final forward tests must cover Guizhou Moutai (`600519.SH`) and Pop Mart (`09992.HK`).

---

### Task 1: Define the Capability Profile Contract

**Files:**
- Create: `.claude/skills/source-discovery/references/source-profile.schema.json`
- Create: `tests/unit/skills/test_source_capability_profiles.py`
- Create: `tests/fixtures/source-discovery/profiles/official-example.yaml`
- Create: `tests/fixtures/source-discovery/profiles/aggregator-example.yaml`

**Interfaces:**
- Consumes: one YAML mapping per actual website.
- Produces: JSON Schema draft 2020-12 contract with required identity, function, access, citation, fallback, and review fields.

- [ ] **Step 1: Write failing schema tests**

Add tests that load the schema with `Draft202012Validator.check_schema`, validate
the two fixtures, reject a profile missing `direct_urls`, reject a function
without a same-function fallback, and reject evidence levels outside
`High|Medium|Low`.

Use this minimum profile shape:

```yaml
id: sse
name: Shanghai Stock Exchange
aliases: [上海证券交易所]
publisher_type: official-exchange
official_domains: [sse.com.cn]
geographies: [CN]
industries: [all-listed]
authority:
  level: High
  scope: SSE-published disclosures, rules, correspondence, and market data
functions:
  - id: company-announcements
    authority: High
    utility: High
    direct_urls:
      - url: https://www.sse.com.cn/home/search/
        kind: search
        stability: stable
    search:
      method: site-form
      fields: [webswd]
      example_query: 贵州茅台
      result_identity: title, issuer, date, announcement ID
    citation:
      use: direct
      required_fields: [publisher, title, date, document_id, url]
    fallbacks: [cninfo-company-announcements]
access:
  status: reachable
  last_checked: "2026-08-01T00:00:00+08:00"
  final_url: https://www.sse.com.cn/
  limitation: none observed
  evidence_level: High
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py -q
```

Expected: FAIL because the schema and fixtures do not exist.

- [ ] **Step 3: Add the schema and valid fixtures**

Require:

```text
id, name, aliases, publisher_type, official_domains, geographies, industries,
authority, functions, access
```

Each `functions[]` item requires:

```text
id, authority, utility, direct_urls, search, citation, fallbacks
```

Each `access` requires:

```text
status, last_checked, final_url, limitation, evidence_level
```

Constrain status and rating vocabularies exactly to the approved design.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py -q
```

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/source-discovery/references/source-profile.schema.json tests/unit/skills/test_source_capability_profiles.py tests/fixtures/source-discovery/profiles
git commit -m "Define source capability profiles"
```

### Task 2: Implement Profile Loading and Trust-First Routing

**Files:**
- Create: `.claude/skills/source-discovery/scripts/source_profiles.py`
- Modify: `tests/unit/skills/test_source_capability_profiles.py`

**Interfaces:**
- Produces: `load_profiles(profile_dir: Path, schema_path: Path) -> list[dict[str, object]]`
- Produces: `select_routes(profiles: Sequence[Mapping[str, object]], function_id: str, now: datetime, cache: Mapping[str, object] | None = None) -> list[RouteCandidate]`
- Produces: `ttl_for_status(status: str) -> timedelta`
- Produces: immutable `RouteCandidate` with `source_id`, `function_id`, `authority`, `originality`, `independence`, `reachability`, `utility`, `direct_url`, `stale`, and `skip_reason`.

- [ ] **Step 1: Write failing loader and routing tests**

Test:

```text
schema validation reports the file path;
duplicate source IDs fail;
an official source wins over a reachable aggregator for the same function;
a fresh temporarily-unreachable route is skipped for its same-function fallback;
a stale temporarily-unreachable route is returned with stale=true for refresh;
changing only reachability never changes authority;
all approved status TTLs equal the exact Global Constraints values.
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py -q
```

Expected: FAIL because `source_profiles.py` and its interfaces do not exist.

- [ ] **Step 3: Implement the minimal loader and router**

Use `yaml.safe_load`, `jsonschema.Draft202012Validator`, timezone-aware
datetimes, explicit rank maps, and deterministic tie-breaking by source ID.
Treat function mismatch as exclusion. Apply cache reachability only after
profile authority and function metadata are loaded.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py -q
```

Expected: all Task 1-2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/source-discovery/scripts/source_profiles.py tests/unit/skills/test_source_capability_profiles.py
git commit -m "Add trust-first source routing"
```

### Task 3: Implement Reachability Classification and Cache

**Files:**
- Create: `.claude/skills/source-discovery/scripts/probe_source_reachability.py`
- Create: `tests/unit/skills/test_source_reachability_probe.py`
- Create: `tests/fixtures/source-discovery/probes/reachable.html`
- Create: `tests/fixtures/source-discovery/probes/login.html`
- Create: `tests/fixtures/source-discovery/probes/paywall.html`
- Create: `tests/fixtures/source-discovery/probes/waf.html`
- Create: `tests/fixtures/source-discovery/probes/error-200.html`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `ProbeObservation(status_code, final_url, redirect_chain, content_type, title, body_excerpt, error_kind, error_message)`.
- Produces: `classify_observation(observation: ProbeObservation, expected_fingerprints: Sequence[str]) -> ProbeResult`.
- Produces: `probe_url(url: str, timeout: float, user_agent: str) -> ProbeObservation`.
- Produces: `load_cache(path: Path) -> dict[str, object]` and `write_cache(path: Path, payload: Mapping[str, object]) -> None`.
- CLI: `python .../probe_source_reachability.py --profiles DIR --cache tmp/source-discovery/reachability.json [--source ID ...] [--all]`.

- [ ] **Step 1: Write failing pure-classification tests**

Cover:

```text
recognizable 200 content -> reachable;
200 error page -> broken-link;
login prompt -> login-required;
subscription prompt -> paywalled;
Cloudflare/Akamai/Aliyun challenge -> anti-bot;
timeout/DNS/reset -> temporarily-unreachable;
404/410 -> broken-link;
redirect with matching publisher fingerprint -> moved;
redirect without matching fingerprint -> unverified;
cache writes atomically and round-trips JSON;
tmp/source-discovery is gitignored.
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_reachability_probe.py -q
```

Expected: FAIL because probe implementation and fixtures do not exist.

- [ ] **Step 3: Implement the probe and cache**

Use `urllib.request` with a descriptive user agent, bounded response reads,
explicit exception mapping, HTML title extraction, lowercased semantic
fingerprints, and `os.replace` for atomic cache writes. Never update profile
YAML or the reviewed snapshot from this CLI.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_source_reachability_probe.py -q
```

Expected: all Task 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add .gitignore .claude/skills/source-discovery/scripts/probe_source_reachability.py tests/unit/skills/test_source_reachability_probe.py tests/fixtures/source-discovery/probes
git commit -m "Add source reachability probing"
```

### Task 4: Migrate the Catalog to Profiles and Deterministic Generation

**Files:**
- Create: `.claude/skills/source-discovery/scripts/build_source_catalog.py`
- Create: `.claude/skills/source-discovery/references/sources/*.yaml`
- Create: `.claude/skills/source-discovery/references/reachability-snapshot.json`
- Modify: `.claude/skills/source-discovery/references/source-catalog.md`
- Modify: `tests/unit/skills/test_source_capability_profiles.py`
- Modify: `tests/unit/skills/test_source_discovery_skill.py`

**Interfaces:**
- CLI: `python .../build_source_catalog.py --profiles DIR --snapshot FILE --output FILE [--check]`.
- Produces one profile per actual website represented by U01-U63, U24 and U43 subrecords, C01-C14, and canonical replacements.
- Preserves supplied IDs and existing-core origin IDs as aliases in profiles.

- [ ] **Step 1: Write failing migration and generation tests**

Require:

```text
every actual website in the maintained catalog has exactly one YAML profile;
every U01-U63 identifier remains discoverable through id or aliases;
all C01-C14 origins remain discoverable;
generated source-catalog.md equals committed content;
all fallbacks resolve to a function exported by another profile;
every material function has at least one direct URL and one search example;
the reviewed snapshot contains only known source IDs and approved statuses.
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py tests/unit/skills/test_source_discovery_skill.py -q
```

Expected: FAIL because profiles, snapshot, and generator do not exist.

- [ ] **Step 3: Build seed profiles from the audited catalog**

Transcribe existing canonical identity, route-prior, access, probe, limitation,
and fallback facts without inventing unverified capabilities. Use
`unverified` and `Low` evidence where the existing audit does not establish a
function. Preserve source families but create profiles only for actual
websites.

- [ ] **Step 4: Implement deterministic catalog generation**

Render:

```text
source ID and name;
publisher type and official domains;
function summary;
best direct links;
authority, utility, current status, and last checked;
access limitations;
same-function fallbacks;
site-guide link when present.
```

Sort by source ID. Make `--check` exit nonzero when generated output differs.

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py tests/unit/skills/test_source_discovery_skill.py -q
```

Expected: all Task 1-4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/source-discovery/references .claude/skills/source-discovery/scripts/build_source_catalog.py tests/unit/skills/test_source_capability_profiles.py tests/unit/skills/test_source_discovery_skill.py
git commit -m "Structure the source catalog"
```

### Task 5: Explore and Enrich Every Website

**Files:**
- Modify: `.claude/skills/source-discovery/references/sources/*.yaml`
- Modify: `.claude/skills/source-discovery/references/reachability-snapshot.json`
- Modify: `.claude/skills/source-discovery/references/source-catalog.md`

**Interfaces:**
- Consumes: read-only subagent reports stored in this plan's SDD workspace.
- Produces: reviewed capability profiles with verified functions, direct links, search procedures, examples, citation rules, restrictions, and same-function fallbacks.

- [ ] **Step 1: Dispatch parallel read-only exploration agents**

Use one agent per independent group:

```text
official mainland disclosures/regulators;
Hong Kong exchange/regulatory/ownership/registry/market/government sources;
China macro/government/statistics;
international organizations/foreign regulators;
consulting/accounting/HR research;
technology/telecom/security/mobile;
consumer/media/travel/aviation/e-commerce;
venture/private markets/report aggregators/finance portals;
company and IR discovery patterns.
```

Each agent writes a JSON or Markdown report to the SDD workspace and returns
only its status and report path. It must inspect functions beyond homepages,
give direct links, explain site search, provide one reproducible query, label
login/paywall/WAF/download limits, define citation eligibility, identify
higher-authority same-function peers, timestamp findings, and assign
`High|Medium|Low` evidence.

The finance-portal agent must give Eastmoney dedicated coverage. Separate the
portal, company-information pages, market/valuation data, announcement and
research indexes, Eastmoney Securities-authored reports, and `pdf.dfcfw.com`
document hosting. Starting from
`https://pdf.dfcfw.com/pdf/H3_AP202506111688924171_1.pdf?1771032445000.pdf`,
recover the report title, authoring institution, analyst, publication date,
disclaimer, upstream search/list entry, company lookup path, and stable citation
identity. Do not infer broker authority from the host domain alone.

- [ ] **Step 2: Require open-ended Hong Kong discovery**

The Hong Kong agent starts with HKEX/HKEXnews, SFC, AFRC, HKMA, Hong Kong
government/statistics, issuer IR, and linked original publishers, then adds
useful sources beyond the supplied list when they pass the profile contract.
It must cover common routes for announcements, regulatory actions, substantial
shareholding/ownership, company registry, market data, official statistics,
policy, and industry research.

- [ ] **Step 3: Integrate reports in one writer task**

Normalize canonical identities, reject homepage-only findings, resolve
conflicting access conclusions conservatively, and retain source-specific
evidence. Add newly discovered Hong Kong profiles and same-function fallback
links. Do not copy subagent prose directly into the catalog.

- [ ] **Step 4: Regenerate and validate**

Run:

```bash
uv run python .claude/skills/source-discovery/scripts/build_source_catalog.py --profiles .claude/skills/source-discovery/references/sources --snapshot .claude/skills/source-discovery/references/reachability-snapshot.json --output .claude/skills/source-discovery/references/source-catalog.md
uv run pytest tests/unit/skills/test_source_capability_profiles.py tests/unit/skills/test_source_discovery_skill.py -q
```

Expected: generation succeeds and all source capability contracts pass.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/source-discovery/references/sources .claude/skills/source-discovery/references/reachability-snapshot.json .claude/skills/source-discovery/references/source-catalog.md
git commit -m "Enrich source capability profiles"
```

### Task 6: Add Site Guides and Skill Runtime Instructions

**Files:**
- Create: `.claude/skills/source-discovery/references/site-guides/sse.md`
- Create: `.claude/skills/source-discovery/references/site-guides/cninfo.md`
- Create: `.claude/skills/source-discovery/references/site-guides/hkexnews.md`
- Create: `.claude/skills/source-discovery/references/site-guides/hong-kong-regulatory.md`
- Create: `.claude/skills/source-discovery/references/site-guides/official-statistics.md`
- Modify: `.claude/skills/source-discovery/SKILL.md`
- Modify: `.claude/skills/source-discovery/references/search-playbook.md`
- Modify: `tests/unit/skills/test_source_discovery_skill.py`

**Interfaces:**
- Consumes: generated catalog, profiles, reviewed snapshot, and local cache.
- Produces: agent instructions for function-first, trust-first, cache-aware routing and direct site use.

- [ ] **Step 1: Write failing guide and runtime tests**

Require:

```text
SKILL.md loads the generated catalog before routing;
SKILL.md reads local cache when present but treats reviewed snapshot as durable;
fresh temporarily-unreachable routes are skipped without changing authority;
stale routes are rechecked;
site guides expose direct URLs, fields, query examples, citation fields, and fallback routes;
same-function high-authority precedence is explicit;
Hong Kong uncataloged discovery is explicit.
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_discovery_skill.py -q
```

Expected: FAIL because site guides and runtime instructions are absent.

- [ ] **Step 3: Write focused site guides and update the skill**

Keep `SKILL.md` under 500 lines. Put detailed field names, URL templates, and
query examples in guides. Include the exact cache and snapshot precedence:

```text
valid local cache observation -> reviewed snapshot -> profile access record
```

Apply cache only to reachability. Never overwrite authority, citation scope,
or publisher identity from runtime cache.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/unit/skills/test_source_discovery_skill.py tests/unit/skills/test_source_capability_profiles.py -q
```

Expected: all static skill and capability tests pass.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/source-discovery/SKILL.md .claude/skills/source-discovery/references/search-playbook.md .claude/skills/source-discovery/references/site-guides tests/unit/skills/test_source_discovery_skill.py
git commit -m "Add direct source usage guides"
```

### Task 7: Add Explicit Live Smoke Tests and Review a Probe Snapshot

**Files:**
- Create: `tests/integration/test_source_reachability_live.py`
- Modify only after manual review: `.claude/skills/source-discovery/references/reachability-snapshot.json`
- Regenerate: `.claude/skills/source-discovery/references/source-catalog.md`

**Interfaces:**
- Live pytest runs only when `AH_RESEARCH_LIVE=1`.
- Full probe writes `tmp/source-discovery/reachability.json`.
- Snapshot promotion is a reviewed, explicit file update.

- [ ] **Step 1: Write live test gating before network calls**

Assert the module skips when `AH_RESEARCH_LIVE` is absent. Add smoke cases for
SSE, CNINFO, HKEXnews, one official statistics site, one login/paywall site,
and one anti-bot site. Assert classification fields, not universal `200`
success.

- [ ] **Step 2: Run offline tests**

Run:

```bash
uv run pytest tests/integration/test_source_reachability_live.py -q
```

Expected: all tests skipped and no network calls occur.

- [ ] **Step 3: Run the full explicit probe**

Run:

```bash
uv run python .claude/skills/source-discovery/scripts/probe_source_reachability.py --profiles .claude/skills/source-discovery/references/sources --cache tmp/source-discovery/reachability.json --all
```

Expected: JSON report covers every profile and distinguishes access failure
classes without editing committed files.

- [ ] **Step 4: Review and promote observations**

Compare changed statuses with profile fingerprints and subagent evidence.
Promote only verified observations into
`references/reachability-snapshot.json`; leave ambiguous changes in local
cache as `unverified`. Regenerate the catalog.

- [ ] **Step 5: Run live smoke and offline regression**

Run:

```bash
AH_RESEARCH_LIVE=1 uv run pytest tests/integration/test_source_reachability_live.py -q
uv run pytest tests/unit/skills/test_source_capability_profiles.py tests/unit/skills/test_source_reachability_probe.py tests/unit/skills/test_source_discovery_skill.py -q
```

Expected: live smoke returns classified observations; offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_source_reachability_live.py .claude/skills/source-discovery/references/reachability-snapshot.json .claude/skills/source-discovery/references/source-catalog.md
git commit -m "Add live source reachability checks"
```

### Task 8: Forward-Test Guizhou Moutai and Pop Mart

**Files:**
- Create: `tests/fixtures/source-discovery/scenarios/guizhou-moutai.yaml`
- Create: `tests/fixtures/source-discovery/scenarios/pop-mart.yaml`
- Modify: `tests/unit/skills/test_source_capability_profiles.py`
- Modify only for demonstrated gaps: `.claude/skills/source-discovery/SKILL.md`, profiles, or site guides.

**Interfaces:**
- Guizhou Moutai scenario requires SSE announcement/search, official issuer or filing evidence, regulatory correspondence route, and independent industry context.
- Pop Mart scenario requires HKEXnews filing/search, issuer IR, Hong Kong regulatory/ownership routes, and independent consumer/industry context.

- [ ] **Step 1: Add deterministic route scenarios**

Each scenario declares required functions, expected first-choice source class,
forbidden discovery-only final citations, and fallback behavior when the first
route is temporarily unavailable.

- [ ] **Step 2: Run scenario tests to verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py -q
```

Expected: FAIL until scenario routing support and all required profiles exist.

- [ ] **Step 3: Implement minimal scenario route evaluation**

Use the existing `select_routes` interface. Do not add company-specific
exceptions to production code. Fix only general profile, guide, or routing gaps
revealed by the scenarios.

- [ ] **Step 4: Forward-test with fresh agents**

Dispatch one fresh agent with:

```text
Use source-discovery to find current, citable official and independent sources
for a Guizhou Moutai research update. Include announcements/regulatory letters,
company materials, and industry context. Record failed routes and fallbacks.
```

Dispatch another with:

```text
Use source-discovery to find current, citable official and independent sources
for a Pop Mart research update. Include HKEXnews filings, company IR,
Hong Kong regulatory/ownership context, and consumer-industry evidence.
Record failed routes and fallbacks.
```

Do not tell agents the expected source list. Evaluate whether they choose
high-authority same-function sources, use direct links/search procedures,
avoid aggregator final citations, and classify access limitations.

- [ ] **Step 5: Close demonstrated gaps and rerun**

Make only changes tied to a failed deterministic or forward scenario. Rerun
the failed scenario and both focused test files.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/source-discovery/scenarios tests/unit/skills/test_source_capability_profiles.py .claude/skills/source-discovery
git commit -m "Validate company source discovery"
```

### Task 9: Final Verification and Integration

**Files:**
- Modify only if final review finds a concrete defect.

**Interfaces:**
- Produces a reviewed feature branch ready to integrate into `refactor/financial-skill-contracts`.

- [ ] **Step 1: Run complete focused verification**

```bash
uv run pytest tests/unit/skills/test_source_capability_profiles.py tests/unit/skills/test_source_reachability_probe.py tests/unit/skills/test_source_discovery_skill.py tests/unit/skills/test_financial_skill_contracts.py tests/integration/test_source_reachability_live.py -q
uv run python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py .claude/skills/source-discovery
uv run python .claude/skills/source-discovery/scripts/build_source_catalog.py --profiles .claude/skills/source-discovery/references/sources --snapshot .claude/skills/source-discovery/references/reachability-snapshot.json --output .claude/skills/source-discovery/references/source-catalog.md --check
git diff --check
```

Expected: offline tests pass with live tests skipped; skill and generated
catalog validation pass; no whitespace errors.

- [ ] **Step 2: Run final whole-branch review**

Review every commit from `ab9c064` to `HEAD` for design compliance, source
provenance mistakes, unstable live-test assumptions, unsafe cache precedence,
and unrelated changes.

- [ ] **Step 3: Apply one reviewed fix wave if necessary**

Use one implementation subagent for all final findings, rerun covering tests,
and perform one scoped re-review.

- [ ] **Step 4: Integrate without touching unrelated root changes**

Cherry-pick the feature commits into
`refactor/financial-skill-contracts`. Resolve only source-capability files.
Run the complete focused verification in the root checkout, then commit any
necessary handoff-only merge resolution separately.
