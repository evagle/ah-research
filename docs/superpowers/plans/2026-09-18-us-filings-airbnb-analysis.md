# US Filings and Airbnb Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an evidence-bound US SEC filing path to `ah-research` and prove it with an Airbnb latest-report analysis.

**Architecture:** A focused `scripts/sec_filings.py` adapter owns SEC identity, catalog, selection, immutable artifacts, and revalidation; `scripts/sec_xbrl.py` owns structured fact normalization and HTML citations. The existing `download_filings.py` CLI dispatches `.US` research tickers without extending the A/H trading model, while financial skills consume a jurisdiction-appropriate filing manifest and a US-specific analysis contract.

**Tech Stack:** Python 3.12 stdlib, Inline XBRL/HTML parsing, JSON, SHA-256, pytest, Markdown skill contracts.

**Spec:** `docs/superpowers/specs/2026-09-02-us-filings-airbnb-analysis-design.md`

## Progress (2026-09-18)

- [x] Tasks 1-5 implemented and covered by unit, integration, and static skill-contract tests.
- [x] Same-cycle 8-K `EX-99.*` exhibit discovery added to the immutable US manifest.
- [x] Independent Airbnb analysis completed before reading prior work; Google Doc cross-validation appended afterward.
- [x] Focused suite passes with 94% coverage for both `scripts/sec_filings.py` and `scripts/sec_xbrl.py`.
- [x] Existing financial skill contracts (578 tests) and A/H downloader regressions (259 tests) pass.
- [ ] Live SEC revalidation remains blocked by Akamai 403 from the current IP. Classified as `dependency_failure`; recorded issuer evidence and hashes are retained without claiming successful replay.

## Global Constraints

- Canonical US research ticker is `<uppercase-symbol>.US`; it is not a tradable `Symbol` in the existing market model.
- SEC identity is CIK-based and ticker, submissions, and Inline XBRL identity disagreements fail closed.
- Supported filing families are `10-K`, `10-Q`, `10-K/A`, and `10-Q/A`.
- Selection is deterministic and excludes evidence published after `AS_OF`.
- The latest 10-Q remains unaudited; a preceding 10-K is the audited baseline.
- Persist official responses and selected documents immutably with SHA-256 lineage.
- Existing SH, SZ, and HK behavior and annual manifest fields remain compatible.
- Every material conclusion includes `High`, `Medium`, `Low`, or `Manual review` evidence.
- Brian's prior Google Doc is used only after independent analysis for supplementation and cross-validation.
- `.agent/PLANS.md` is absent; this plan follows the repository's established `docs/superpowers/plans/` convention.
- Preserve unrelated changes in the dirty worktree.

---

### Task 1: SEC Identity, Catalog, and Selection

**Files:**
- Create: `scripts/sec_filings.py`
- Create: `tests/unit/test_sec_filings.py`
- Create: `tests/fixtures/sec/abnb_company_tickers.json`
- Create: `tests/fixtures/sec/abnb_submissions.json`
- Create: `tests/fixtures/sec/abnb_submissions_history.json`

**Interfaces:**
- Produces: `parse_us_ticker(ticker: str) -> str`.
- Produces: `resolve_sec_identity(ticker: str, payload: bytes) -> SecIdentity`.
- Produces: `parse_submission_catalog(current: bytes, historical: Mapping[str, bytes]) -> tuple[SecFiling, ...]`.
- Produces: `select_filing_set(catalog: Sequence[SecFiling], as_of: date) -> FilingSelection`.
- Produces: `archive_url(cik: str, accession: str, document: str) -> str`.

- [ ] **Step 1: Write failing tests for US ticker and CIK identity**

Cover `ABNB.US`, lower-case alias normalization, invalid numeric/unsafe symbols, zero-padded CIK, duplicate ticker rows, and a requested-ticker mismatch.

- [ ] **Step 2: Run identity tests and verify RED**

Run: `uv run pytest tests/unit/test_sec_filings.py -k 'ticker or identity or archive' -v`

Expected: import failure because `scripts/sec_filings.py` does not exist.

- [ ] **Step 3: Implement immutable identity types and URL construction**

Use frozen dataclasses for `SecIdentity` and `SecFiling`; normalize accession numbers only after validating `##########-##-######`; build official URLs under `https://www.sec.gov/Archives/edgar/data/<cik-int>/<accession-no-dashes>/`.

- [ ] **Step 4: Write failing tests for catalog and `AS_OF` selection**

Cover mixed form ordering, historical submission segments, duplicate conflict rejection, amendments replacing the same form family/report period, latest report, audited baseline, and four prior comparable quarters.

- [ ] **Step 5: Run selection tests and verify RED**

Run: `uv run pytest tests/unit/test_sec_filings.py -k 'catalog or selection or amendment' -v`

Expected: failures for missing catalog and selection behavior.

- [ ] **Step 6: Implement catalog parsing and deterministic selection**

Reject unequal SEC column lengths, conflicting duplicate accessions, incomplete historical segments, unresolved amendments, and catalogs with no qualifying report on or before `AS_OF`.

- [ ] **Step 7: Run Task 1 tests and verify GREEN**

Run: `uv run pytest tests/unit/test_sec_filings.py -v`

Expected: PASS.

---

### Task 2: Immutable SEC Manifest and Revalidation

**Files:**
- Modify: `scripts/sec_filings.py`
- Modify: `tests/unit/test_sec_filings.py`
- Create: `tests/fixtures/sec/abnb_filing_index.json`
- Create: `tests/fixtures/sec/abnb_10q.html`
- Create: `tests/fixtures/sec/abnb_10k.html`
- Create: `tests/fixtures/sec/abnb_8k_index.json`
- Create: `tests/fixtures/sec/abnb_earnings_exhibit.html`

**Interfaces:**
- Produces: `SecClient(user_agent: str, min_interval: float = 0.1)`.
- Produces: `build_filing_manifest(ticker: str, as_of: date, out_dir: Path, client: SecClient) -> Path`.
- Produces: `revalidate_filing_manifest(path: Path, client: SecClient) -> str`.
- Manifest schema version: `us-sec-filing-manifest/1.0`.

- [ ] **Step 1: Write failing manifest tests**

Assert complete request contracts, mapping/submissions/index/document hashes, candidate catalog, selected roles, local absolute paths, same-cycle 8-K exhibit identity, atomic writes, and refusal to overwrite different bytes at a content-addressed path.

- [ ] **Step 2: Run manifest tests and verify RED**

Run: `uv run pytest tests/unit/test_sec_filings.py -k manifest -v`

Expected: failures for missing manifest functions.

- [ ] **Step 3: Implement the SEC client and manifest builder**

Require a descriptive User-Agent, send `Accept-Encoding: gzip, deflate`, apply one shared rate limiter, retry bounded 403/429/5xx responses, persist every response by SHA-256, and atomically publish the canonical manifest only after all selected evidence validates.

- [ ] **Step 4: Write failing revalidation tests**

Replay exact mapping, submissions, index, and document requests. Test success, remote catalog drift, selected-document drift, CIK mismatch, and local artifact drift.

- [ ] **Step 5: Run revalidation tests and verify RED**

Run: `uv run pytest tests/unit/test_sec_filings.py -k revalid -v`

Expected: failures for missing drift checks.

- [ ] **Step 6: Implement strict live revalidation**

Recompute all hashes and selections; return a success message containing the manifest SHA-256 or raise `SecEvidenceError` without mutating evidence.

- [ ] **Step 7: Run Task 2 tests and verify GREEN**

Run: `uv run pytest tests/unit/test_sec_filings.py -v`

Expected: PASS.

---

### Task 3: Inline XBRL Facts and HTML Citations

**Files:**
- Create: `scripts/sec_xbrl.py`
- Create: `tests/unit/test_sec_xbrl.py`
- Modify: `tests/fixtures/sec/abnb_10q.html`
- Create: `tests/fixtures/sec/abnb_companyfacts.json`

**Interfaces:**
- Produces: `extract_inline_facts(html: bytes, artifact_path: Path, accession: str) -> tuple[XbrlFact, ...]`.
- Produces: `parse_company_facts(payload: bytes, cik: str) -> tuple[XbrlFact, ...]`.
- Produces: `cross_check_facts(inline: Sequence[XbrlFact], company: Sequence[XbrlFact]) -> tuple[FactCheck, ...]`.
- Produces: `build_html_citation(...) -> dict[str, object]`.

- [ ] **Step 1: Write failing XBRL tests**

Cover issuer CIK, decimals/scale/sign, units, nil facts, instant versus duration contexts, quarter versus YTD contexts, accession lineage, and company-facts normalization.

- [ ] **Step 2: Run XBRL tests and verify RED**

Run: `uv run pytest tests/unit/test_sec_xbrl.py -v`

Expected: import failure because `scripts/sec_xbrl.py` does not exist.

- [ ] **Step 3: Implement minimal structured extraction**

Use `html.parser` plus XML-style attribute normalization; retain context identity and never derive quarter-only values by subtraction.

- [ ] **Step 4: Write failing citation and conflict tests**

Require official URL, accession, form, report period, absolute artifact path, artifact hash, exact quote, and a real DOM `id`; reject fabricated anchors, page numbers for unpaginated HTML, and material Inline XBRL/company-facts conflicts.

- [ ] **Step 5: Run citation tests and verify RED**

Run: `uv run pytest tests/unit/test_sec_xbrl.py -k 'citation or conflict' -v`

Expected: failures for missing anchor validation and conflict logic.

- [ ] **Step 6: Implement citation validation and cross-checking**

Return `matched`, `missing_company_fact`, or `conflict`; dependent conflicts are `Manual review` and do not invalidate unrelated facts.

- [ ] **Step 7: Run Task 3 tests and verify GREEN**

Run: `uv run pytest tests/unit/test_sec_xbrl.py -v`

Expected: PASS.

---

### Task 4: Add `.US` Dispatch to the Existing CLI

**Files:**
- Modify: `scripts/download_filings.py`
- Create: `tests/integration/test_download_filings_us.py`

**Interfaces:**
- Extends: `canonical_ticker("abnb.us") == "ABNB.US"`.
- Adds: `download_filings.py ABNB.US --latest --as-of YYYY-MM-DD`.
- Adds: `download_filings.py --revalidate <us-manifest-path>` dispatch by manifest schema.

- [ ] **Step 1: Write failing CLI tests**

Mock `SecClient`, assert `.US` does not call CNINFO/HKEX routes, `--latest` is required for US research, incompatible annual-only flags fail clearly, and output reports the manifest path.

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `uv run pytest tests/integration/test_download_filings_us.py -v`

Expected: failures because `.US` is rejected.

- [ ] **Step 3: Implement additive parser and dispatch behavior**

Import `sec_filings` through the same package/direct-execution compatibility pattern used by `build_event_manifest`; leave the existing A/H body unchanged after dispatch.

- [ ] **Step 4: Run US CLI tests and verify GREEN**

Run: `uv run pytest tests/integration/test_download_filings_us.py -v`

Expected: PASS.

- [ ] **Step 5: Run existing downloader regressions**

Run: `uv run pytest tests/integration/test_download_filings.py -q`

Expected: PASS with unchanged SH/SZ/HK behavior.

---

### Task 5: Extend Financial Skill Contracts for US Reports

**Files:**
- Modify: `.claude/skills/read-filing/SKILL.md`
- Create: `.claude/skills/read-filing/references/filing-structure-us.md`
- Modify: `.claude/skills/read-filing/references/evidence-contract.md`
- Modify: `.claude/skills/financial-redflag-scan/SKILL.md`
- Modify: `.claude/skills/value-profile/SKILL.md`
- Create: `.claude/skills/value-profile/references/us-latest-report-analysis.md`
- Create: `tests/unit/skills/test_us_financial_skill_contracts.py`

**Interfaces:**
- Shared manifest term becomes `jurisdiction-appropriate filing manifest` while preserving A/H annual manifest semantics.
- US citations use `source_type=filing_html` and a verified `anchor`; `page` is optional only for US HTML.
- The latest-report analysis emits the Airbnb KPI tree and strategy-to-value chain.

- [ ] **Step 1: Write failing static contract tests**

Assert US ticker invocation, 10-Q unaudited rules, audited 10-K baseline, four comparable quarters, 8-K exhibit use, HTML anchor citations, evidence levels, no causal overclaim, and prior-analysis-last ordering.

- [ ] **Step 2: Run skill contract tests and verify RED**

Run: `uv run pytest tests/unit/skills/test_us_financial_skill_contracts.py -v`

Expected: failures because the skill contracts are A/H annual-only.

- [ ] **Step 3: Update shared and specialist skill contracts**

Add a US branch rather than weakening annual A/H requirements. Keep `value-profile` full valuation support out of scope, but permit a US latest-report research output with explicit limitations.

- [ ] **Step 4: Run skill contract tests and verify GREEN**

Run: `uv run pytest tests/unit/skills/test_us_financial_skill_contracts.py -v`

Expected: PASS.

- [ ] **Step 5: Run existing financial skill regressions**

Run: `uv run pytest tests/unit/skills/test_financial_skill_contracts.py -q`

Expected: PASS, including the user's in-progress quantitative-analysis changes.

---

### Task 6: Airbnb Acceptance Analysis and Cross-Validation

**Files:**
- Create: `tests/acceptance/test_airbnb_latest_report.py`
- Create: `profiles/ABNB.US-2026-09-18.md`
- Create: `data/filings/ABNB.US/research/source-index.md`
- Modify: `README.md`

**Interfaces:**
- Acceptance report sections: evidence identity, executive view, KPI tree, business changes, strategy-to-value chain, financial quality, capital allocation, market recognition, risks, missing evidence, and prior-analysis cross-validation.
- Every material conclusion ends with an evidence level.

- [ ] **Step 1: Write the failing acceptance test**

Require the fixture-selected latest report, audited baseline, four comparable quarters, at least one fully cited strategy-to-value row, separate fact/calculation/interpretation/market-attribution labels, explicit missing metrics, and cross-validation after the independent conclusion.

- [ ] **Step 2: Run acceptance test and verify RED**

Run: `uv run pytest tests/acceptance/test_airbnb_latest_report.py -v`

Expected: failure because the Airbnb report does not exist.

- [ ] **Step 3: Revalidate current SEC evidence and build the independent report**

Run the live downloader with `ABNB.US --latest --as-of 2026-09-18`, derive facts from SEC and Airbnb first-party evidence, and label any external market evidence separately. Do not read the prior Google Doc until the independent conclusion is complete.

- [ ] **Step 4: Cross-validate against the prior Google Doc**

Classify material prior hypotheses as `confirmed`, `updated`, `contradicted`, `unresolved`, or `out of scope`; cite current evidence for substantive results.

- [ ] **Step 5: Run acceptance test and verify GREEN**

Run: `uv run pytest tests/acceptance/test_airbnb_latest_report.py -v`

Expected: PASS.

- [ ] **Step 6: Run focused coverage and quality checks**

Run: `uv run pytest tests/unit/test_sec_filings.py tests/unit/test_sec_xbrl.py tests/integration/test_download_filings_us.py tests/unit/skills/test_us_financial_skill_contracts.py tests/acceptance/test_airbnb_latest_report.py --cov=scripts.sec_filings --cov=scripts.sec_xbrl --cov-report=term-missing`

Run: `uv run ruff check scripts/sec_filings.py scripts/sec_xbrl.py scripts/download_filings.py tests/unit/test_sec_filings.py tests/unit/test_sec_xbrl.py tests/integration/test_download_filings_us.py tests/unit/skills/test_us_financial_skill_contracts.py tests/acceptance/test_airbnb_latest_report.py`

Expected: all tests pass, changed Python modules exceed 92% coverage, and Ruff reports no errors.

- [ ] **Step 7: Review the final diff**

Confirm no A/H manifest field changed meaning, no market/backtest model accepts `.US`, no material conclusion lacks an evidence level, and no unrelated worktree changes are included.
