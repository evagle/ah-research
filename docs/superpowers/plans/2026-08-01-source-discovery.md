# Source Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete `source-discovery` skill that audits the 63 supplied source entries, includes existing repository sources and company websites, discovers new sources, and exhausts multi-source fallbacks before reporting a gap.

**Architecture:** Keep discovery policy in a concise `SKILL.md`, detailed search routing in `references/search-playbook.md`, and the maintained source registry in `references/source-catalog.md`. Existing financial skills reference this shared skill but retain their current official manifest, hashing, and live-revalidation contracts.

**Tech Stack:** Markdown skills, pytest contract tests, YAML frontmatter, curl/browser/search verification.

## Global Constraints

- Preserve all unrelated dirty-worktree changes.
- Give every reliability and reachability conclusion an explicit `High`, `Medium`, or `Low` evidence level.
- Treat the catalog as a seed registry, not a closed allowlist.
- Select sources by fitness for the specific claim, not by a single global website ranking.
- Use multiple applicable sources; exhaust compliant alternatives before reporting missing evidence.
- Treat company websites as first-party subject evidence, not independent proof of leadership, superiority, market share, or outcomes.
- Treat announcements and regulatory correspondence as high-priority evidence and trace app/aggregator copies to the original official document.
- Never weaken existing annual, event, counterpart, or market-data manifest contracts.

---

### Task 1: Add Failing Source-Discovery Contracts

**Files:**
- Create: `tests/unit/skills/test_source_discovery_skill.py`

**Interfaces:**
- Consumes: `.claude/skills/*/SKILL.md`, `scripts/build_event_manifest.py`, `scripts/build_market_manifest.py`, `scripts/download_filings.py`, and `scripts/download_research.py`.
- Produces: contract tests defining the new skill's required files, source coverage, workflow language, and consumer integrations.

- [ ] **Step 1: Run a baseline agent scenario without the skill**

Ask a fresh agent to research an industry fact using the current skills. Record whether it stops after one failed source, omits company websites, treats an aggregator as evidence, or misses current core providers. Keep this output outside the repository.

- [ ] **Step 2: Write the failing structural tests**

Create tests that assert:

```python
SKILL_ROOT = REPO_ROOT / ".claude/skills/source-discovery"

def test_source_discovery_skill_has_required_resources() -> None:
    assert (SKILL_ROOT / "SKILL.md").is_file()
    assert (SKILL_ROOT / "references/source-catalog.md").is_file()
    assert (SKILL_ROOT / "references/search-playbook.md").is_file()

def test_source_catalog_preserves_every_supplied_entry() -> None:
    catalog = read(SKILL_ROOT / "references/source-catalog.md")
    for number in range(1, 64):
        assert f"U{number:02d}" in catalog
```

Also assert required record fields, evidence levels, access statuses, company-site rules, multi-source fallback exhaustion, and references from `product-analysis`, `value-profile`, and `read-filing`.

- [ ] **Step 3: Add core-source registry parity checks**

Extract approved source IDs/domains from the existing script constants and assert every real provider appears in the catalog. Explicitly cover CNINFO and Eastmoney, which are downloader constants rather than event/market registry IDs.

- [ ] **Step 4: Run tests to verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_source_discovery_skill.py -q
```

Expected: FAIL because `.claude/skills/source-discovery/` does not exist.

- [ ] **Step 5: Commit the red tests**

```bash
git add tests/unit/skills/test_source_discovery_skill.py
git commit -m "Define source discovery contracts"
```

### Task 2: Implement the Core Discovery Workflow

**Files:**
- Create: `.claude/skills/source-discovery/SKILL.md`
- Create: `.claude/skills/source-discovery/references/search-playbook.md`

**Interfaces:**
- Consumes: a research question, `AS_OF`, geography, industry, required fact types, and any caller-supplied source constraints.
- Produces: a research ledger and source portfolio with candidate source, query, status, result, access limitation, evidence level, and next fallback.

- [ ] **Step 1: Write concise discoverable frontmatter**

Use:

```yaml
---
name: source-discovery
description: Use when research needs external reports, industry or macro data, company and investor-relations sources, official statistics, market evidence, source validation, or fallback searches after a source is missing, inaccessible, paywalled, or inconclusive.
---
```

- [ ] **Step 2: Implement the source portfolio workflow**

Require this sequence:

```text
question decomposition -> known-source routing -> dynamic discovery
-> access/provenance validation -> independent cross-check
-> fallback exhaustion -> source ledger handoff
```

Define separate ratings for source authority, practical utility, current reachability, and conclusion evidence. Require the final error and attempted alternatives before a gap can be reported.

Evaluate newly discovered candidates on:

```text
provenance; primary/secondary status; methodology transparency; coverage;
timeliness; reproducibility; correction history; access stability;
conflicts of interest; fitness for the requested claim
```

- [ ] **Step 3: Implement company and ecosystem source rules**

Cover issuer/company IR, newsrooms, product and pricing pages, ESG pages, customer, supplier, competitor, and association websites. Permit company pages for subject facts and quotations; require independent evidence for evaluative claims.

- [ ] **Step 4: Add announcement and regulatory-letter discovery**

Cover inquiry/concern letters, issuer responses, supervisory measures,
disciplinary actions, penalty decisions, corrections/restatements, trading
suspensions, and material-event notices. Search app or aggregator indexes when
useful, then require the CNINFO, SSE, SZSE, HKEXnews, or regulator original with
announcement time, document/announcement ID, status, URL, and replacement
relationship.

- [ ] **Step 5: Add search playbooks**

Define source portfolios and fallback routes for:

```text
company/filings; announcements/regulatory correspondence;
valuation/market; macro/official statistics;
general reports; consulting; technology/telecom; consumer/media;
travel/aviation; investment/venture capital; trade/e-commerce;
health/demographics; HR/labor; international comparisons
```

Include query templates using publisher domain, exact report title, date range, file type, geography, industry vocabulary, and original-document tracing.

- [ ] **Step 6: Run focused workflow tests**

Run:

```bash
uv run pytest tests/unit/skills/test_source_discovery_skill.py -q
```

Expected: catalog-related tests still fail; core workflow tests pass.

### Task 3: Audit and Build the Source Catalog

**Files:**
- Create: `.claude/skills/source-discovery/references/source-catalog.md`

**Interfaces:**
- Consumes: the 63 supplied entries, existing source registries/contracts, direct HTTP/browser checks, first-party access policies, and credible indexed evidence.
- Produces: canonical source records keyed by `U01` through `U63` and `Cxx` for unique existing-core sources.

- [ ] **Step 1: Define the record schema in the catalog**

Every record must include:

```text
ID | canonical source | supplied alias | origin/code ID | category
canonical URL | best uses | accuracy | utility | access status/access model
limitations | recommended fallback peers | last checked | evidence level
```

Include evaluated candidates discovered during implementation, including Sina
Finance for news/quote/announcement navigation, while assigning claim-specific
limitations and original-source fallback routes.

Use access statuses:

```text
public; public-limited; login-required; membership/paywalled;
anti-bot/technical-limited; region/network-limited;
moved/redirected; unavailable; unverified
```

- [ ] **Step 2: Probe all supplied URLs and canonical replacements**

For every `U01`-`U63`, record redirect chain, response status, recognizable first-party content, login/paywall indications, and observed technical restriction. Split multi-site item `U24` into clearly labeled subrecords while preserving `U24`; preserve duplicate `U53`, source-family items `U48`/`U52`, and flag the `U43` name/URL mismatch.

- [ ] **Step 3: Inventory existing core sources**

Cover every provider in:

```text
build_event_manifest.SOURCE_DOMAINS
build_market_manifest.SOURCE_DOMAINS
download_filings CNINFO/HKEX constants
download_research Eastmoney constants
```

Merge canonical duplicates with supplied records and retain both origin labels.

- [ ] **Step 4: Write evidence-bounded assessments**

Rate accuracy and utility independently. Mark official and regulator sources as authoritative only for their own published scope. Mark original consultancy/research reports as attributable analysis. Restrict aggregators, media, and social sites to discovery unless the underlying original can be verified.

For announcement and regulatory-letter sources, record whether the site exposes
full-text documents, metadata-only indexes, app mirrors, or paid convenience
features. A paid app copy must not be labeled as the only source until official
exchange and regulator routes have been attempted.

- [ ] **Step 5: Run catalog tests**

Run:

```bash
uv run pytest tests/unit/skills/test_source_discovery_skill.py -q
```

Expected: all catalog and workflow tests pass except consumer integration checks.

### Task 4: Integrate Existing Financial Skills

**Files:**
- Modify: `.claude/skills/product-analysis/SKILL.md`
- Modify: `.claude/skills/value-profile/SKILL.md`
- Modify: `.claude/skills/read-filing/SKILL.md`

**Interfaces:**
- Consumes: `source-discovery` research ledger and source portfolio.
- Produces: externally sourced context that remains subordinate to each caller's existing evidence and persistence contracts.

- [ ] **Step 1: Add the product-analysis handoff**

Require `source-discovery` for external industry structure, product benchmarks, customer value, consumer data, and specialist vertical research. Preserve product-analysis's judgment ownership and Mode B schema.

- [ ] **Step 2: Add the value-profile handoff**

Route macro, industry, valuation context, announcement/regulatory-letter
discovery, and non-filing research gaps through `source-discovery`. State that
annual/event/counterpart/market manifests remain authoritative and cannot be
replaced by catalog entries.

- [ ] **Step 3: Add the read-filing handoff**

Use `source-discovery` only for peer and industry context. Preserve exchange filing, official event source, completeness, and live-revalidation requirements.

- [ ] **Step 4: Run focused contracts**

Run:

```bash
uv run pytest \
  tests/unit/skills/test_source_discovery_skill.py \
  tests/unit/skills/test_financial_skill_contracts.py -q
```

Expected: PASS.

### Task 5: Validate and Forward-Test the Skill

**Files:**
- Modify only if validation exposes a specific gap:
  `.claude/skills/source-discovery/SKILL.md`,
  `.claude/skills/source-discovery/references/search-playbook.md`, or
  `.claude/skills/source-discovery/references/source-catalog.md`

**Interfaces:**
- Consumes: realistic research prompts with unavailable, paywalled, conflicting, and company-claimed evidence.
- Produces: verified skill behavior and final repository diff.

- [ ] **Step 1: Run skill validation**

```bash
python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .claude/skills/source-discovery
```

Expected: validation succeeds.

- [ ] **Step 2: Forward-test five scenarios with fresh agents**

Verify that agents:

```text
1. continue after the preferred report site is inaccessible;
2. use a company product page but independently verify leadership claims;
3. prefer exchange/regulator evidence over an aggregator;
4. trace an app-discovered regulatory letter to its official original;
5. discover a credible source not already in the catalog.
```

- [ ] **Step 3: Close observed workflow gaps**

Change only language or catalog fields tied to a concrete forward-test failure, then rerun the failed scenario and focused tests.

- [ ] **Step 4: Run final verification**

```bash
uv run pytest \
  tests/unit/skills/test_source_discovery_skill.py \
  tests/unit/skills/test_financial_skill_contracts.py -q
git diff --check
git status --short
```

Expected: tests pass; no whitespace errors; unrelated pre-existing changes remain untouched.

- [ ] **Step 5: Commit the implementation**

Stage only source-discovery files and the three intentional consumer edits:

```bash
git add \
  .claude/skills/source-discovery \
  .claude/skills/product-analysis/SKILL.md \
  .claude/skills/value-profile/SKILL.md \
  .claude/skills/read-filing/SKILL.md \
  tests/unit/skills/test_source_discovery_skill.py
git commit -m "Add complete source discovery skill"
```
