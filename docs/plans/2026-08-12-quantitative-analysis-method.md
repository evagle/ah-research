# Quantitative Analysis Method Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable, reader-focused quantitative-analysis method to `value-profile`, then use it to rebuild Tencent Holdings' 2016-2025 quantitative analysis and HTML profile.

**Architecture:** Keep orchestration and completion gates in `SKILL.md`; put formulas, table contracts, evidence rules, HK adaptations, and interpretation guidance in one focused reference. Preserve the existing §Q1-§Q12 section IDs and industry-overlay routing so old profiles remain addressable. Treat the tables as recommended defaults: use all ten years when ten comparable years exist, and adapt or omit metrics that are not meaningful or disclosed.

**Tech Stack:** Markdown skill documents, audited annual-report extracts, pytest contract tests, the existing Markdown-to-HTML renderer.

## Global Constraints

- Do not guess. Every conclusion carries an explicit evidence level.
- Use audited annual reports for financial statements; label company-defined non-IFRS measures separately.
- Display ten fiscal years when ten comparable years are available.
- Do not force A-share-only fields such as gross sales cash receipts or "扣非净利润" onto HK issuers.
- Keep research process, checking narration, and inconsequential reconciliation differences out of reader-visible prose.
- Preserve unrelated worktree changes and do not commit.

---

## Progress

- [x] Read the supplied PDF and recover the quantitative table structure.
- [x] Compare the PDF with the current skill, template, industry overlay, and Tencent Part 2.
- [ ] Record a baseline run using the current skill.
- [ ] Add failing contract tests for the missing method and completion checks.
- [ ] Add the quantitative-analysis reference and wire it into the skill.
- [ ] Update the template and guidance without duplicating the reference.
- [ ] Run focused contract tests and a fresh forward test.
- [ ] Rebuild Tencent Part 2 from 2016-2025 audited data.
- [ ] Render and inspect the updated HTML.

## Design Decisions

- **Recommended, not mandatory:** The standard tables are defaults. An issuer-specific disclosure gap or industry mismatch permits an adapted table with a visible reason.
- **Ten-year window:** Use the latest ten complete fiscal years available by `AS_OF`. Use the latest restated comparative number when an issuer restates a prior year, and disclose only material restatements.
- **Three layers:** Separate reported inputs, calculated metrics, and interpretation. This prevents a calculated ratio from being mistaken for a company disclosure.
- **HK adaptation:** Replace unavailable gross sales receipts and A-share adjusted profit with receivables/deferred revenue/CFO bridges and issuer-reconciled non-IFRS measures.
- **Industry overlay:** The common financial spine remains visible for comparability; an overlay replaces only economically meaningless metrics and adds operating KPIs.
- **Reader focus:** Each subsection ends with the trend, its business cause, and its investor implication. Method notes and evidence grades stay concise.
- **Validation:** Validate coverage, formulas, units, denominator signs, restatements, internal cross-table consistency, and evidence lineage. Five-cell spot checks alone cannot complete the chapter.

## Task 1: Contract Tests

**Files:**
- Modify: `tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes: current `value-profile` Markdown files.
- Produces: failing assertions for reference routing, ten-year defaults, HK substitutions, calculation definitions, and completion gates.

- [ ] Add tests asserting that Step 4 loads `references/quantitative-analysis.md`.
- [ ] Add tests asserting that a ten-year available window is displayed in full.
- [ ] Add tests asserting reported/calculated/interpretation separation and explicit evidence levels.
- [ ] Add tests asserting HK replacements for gross sales receipts and A-share adjusted profit.
- [ ] Add tests asserting completion requires formula, unit, coverage, and cross-table validation rather than a five-cell sample.
- [ ] Run the focused tests and confirm they fail because the new method is absent.

## Task 2: Quantitative Method Reference

**Files:**
- Create: `.claude/skills/value-profile/references/quantitative-analysis.md`
- Modify: `.claude/skills/value-profile/SKILL.md`
- Modify: `.claude/skills/value-profile/references/operations.md`

**Interfaces:**
- Consumes: annual-report facts, industry overlay selection, §Q1-§Q12 template.
- Produces: one canonical method for data windows, formulas, adaptations, interpretation, and validation.

- [ ] Define the ten-year window and comparability rules.
- [ ] Define reported inputs and formulas for returns, margins, quality, growth, efficiency, solvency, cash flow, balance-sheet structure, and common-size statements.
- [ ] Define HK and non-bank internet substitutions.
- [ ] Define subsection output as table, concise interpretation, source, and evidence level.
- [ ] Replace the five-cell completion rule with deterministic coverage and consistency checks.
- [ ] Run focused contract tests and confirm they pass.

## Task 3: Template and Guidance

**Files:**
- Modify: `.claude/skills/value-profile/template-zh.md`
- Modify: `.claude/skills/value-profile/template-guidance.md`

**Interfaces:**
- Consumes: the canonical method reference.
- Produces: visible §Q1-§Q12 table slots and concise prompts that do not duplicate formula details.

- [ ] Mark the tables as recommended defaults and preserve industry adaptation.
- [ ] Add explicit evidence-grade and unavailable/not-applicable handling.
- [ ] Remove universal "excellent" labels that ignore industry economics.
- [ ] Require a trend/cause/impact conclusion under each material table.
- [ ] Run focused skill contract tests.

## Task 4: Skill Forward Test

**Files:**
- Read only: updated skill and Tencent annual reports.

**Interfaces:**
- Consumes: updated skill in a fresh agent context.
- Produces: a proposed Tencent Part 2 structure that includes ten-year tables, HK adaptations, formulas, and validation.

- [ ] Run the same scenario used for the baseline with the updated skill.
- [ ] Compare omissions and ambiguities against the baseline.
- [ ] Tighten the reference only where the forward test reveals a concrete gap.
- [ ] Validate the skill folder with `quick_validate.py`.

## Task 5: Tencent Quantitative Analysis

**Files:**
- Modify: `profiles/00700.HK-2026-08-02.md`

**Interfaces:**
- Consumes: 2016-2025 audited Tencent annual reports and the updated method.
- Produces: complete §Q1-§Q12 tables and reader-focused conclusions.

- [ ] Build one reconciled ten-year fact set with units, source pages, and restatement notes.
- [ ] Calculate returns, margins, earnings quality, growth, capital intensity, solvency, cash allocation, and balance-sheet composition.
- [ ] Add Tencent-specific operating and segment indicators where comparable disclosure exists.
- [ ] Distinguish reported profit, non-IFRS profit, operating profit, investment-related effects, and attributable profit.
- [ ] Write concise conclusions that state trend, cause, and investor impact.
- [ ] Recalculate all table totals and ratios independently.

## Task 6: HTML and Final Verification

**Files:**
- Modify: `profiles/00700.HK-2026-08-02.html`

**Interfaces:**
- Consumes: final Markdown profile.
- Produces: the reader-facing HTML profile.

- [ ] Run the existing profile HTML renderer.
- [ ] Run renderer integration tests and focused skill tests.
- [ ] Inspect the Part 2 tables at desktop and narrow viewport widths.
- [ ] Check for overflow, broken table headers, placeholders, internal process prose, and unsupported precision.
- [ ] Review the final diff without reverting unrelated changes.

## Outcomes & Retrospective

Pending implementation and verification.
