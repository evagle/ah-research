# Repair the Financial Research Skills

This ExecPlan is a living document. Keep `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` current while implementing.

The repository does not contain `.agent/PLANS.md`, so this plan follows the
repository instruction by providing the same self-contained design-to-verification
record under `docs/plans/`.

## Purpose

Repair the four skills under `.claude/skills/` so they route filings correctly,
use consistent accounting formulas and thresholds, honor A-share and HK
differences, maintain stable output contracts, and have repeatable tests. After
the change, an agent should be able to follow each skill without encountering
stale line pointers, invalid CLI examples, ambiguous section identifiers, or
conflicting screening rules.

## Progress

- [x] (2026-07-26) Read the four skills, linked references, skill-authoring guide,
  and financial-reporting book.
- [x] (2026-07-26) Identify direct static defects and assign evidence levels.
- [x] (2026-07-26) Add contract tests and observe the expected failures.
- [x] (2026-07-26) Repair and verify `read-filing`.
- [x] (2026-07-26) Repair and verify `financial-redflag-scan`.
- [x] (2026-07-26) Repair and verify `management-analysis`.
- [x] (2026-07-26) Repair and verify `value-profile`.
- [x] (2026-07-26) Normalize inappropriate whitespace between Chinese characters.
- [x] (2026-07-26) Close the second fresh-evaluation findings with failing
  contract tests first, including historical cutoffs, row-level resume checks,
  Stage C management vetoes, and deterministic valuation-route precedence.
- [x] (2026-07-26) Run focused tests, the broader relevant suite, skill
  validation, Chinese-spacing scan, and diff checks.
- [x] (2026-07-26) Complete the third fresh behavior evaluation; four isolated
  reviews found downloader version-selection, resume-state, management-gate,
  and bank-schema gaps.
- [x] (2026-07-26) Add regression tests for all third-review findings and
  observe 19 skill-contract failures plus corrected/cancelled filing-selection
  failures.
- [x] (2026-07-26) Repair all third-review findings through RED-GREEN contract
  tests and rerun focused, integration, unit, lint, structure, spacing, and diff
  validation.
- [x] (2026-07-26) Complete the sixth isolated review, reproduce its event
  collection, cache binding, terminal-state, threshold, citation, publication,
  and scope findings with failing tests, then repair them.
- [x] (2026-07-26) Reproduce and repair the seventh-review native-adapter,
  official-source, listing-status, content-addressed publication, CAS,
  live-revalidation, child-handoff, and deterministic-check findings.
- [x] (2026-07-26) Repair the seventh-review follow-up findings: parent
  bootstrap order, annual-manifest content addressing and live revalidation,
  management directional-target and dependency responses, and A+H
  dual-jurisdiction regulatory coverage.
- [x] (2026-07-27) Reproduce the latest four-review findings with 12 failing
  contracts, then repair executable manifest commands, issuer identity
  mapping, typed citations, management response/recovery state, per-market
  listing status, market-data evidence, and A+H counterpart filings.
- [x] (2026-07-27) Reproduce the next four-review findings with focused RED
  tests, then repair derived market values, live annual-catalog metadata,
  event subject rosters, red-flag machine rows/actions, read-filing
  finalization, counterpart CAS guards, and management response invariants.
- [ ] Complete the seventh fresh isolated behavior evaluation and continue
  until all four reviewers return exact PASS.
- [ ] Stop after four exact PASS results. The standalone product-analysis skill
  is explicitly deferred by the user's current instruction.

## Surprises & Discoveries

- The repository has no `.agent/PLANS.md`; this file is therefore the
  self-contained execution record.
- The downloader CLI accepts a positional ticker and `--years`; it does not
  accept `--ticker`, `--year`, or `--type`.
- The profile template has 75 numbered headings and 70 confidence fields, while
  the orchestrator hard-codes 67 sections.
- Section identifiers such as `§4.1` repeat in different Parts, so a bare section
  identifier is not a stable key.
- Corrected A-share annual reports are valid candidate versions; cancellation,
  summary, language-duplicate, and supplement announcements are not.
- A manual-review terminal state may relax unavailable-value evidence into a
  search log, but it cannot omit mandatory checklist rows.
- Parsed JSON equality is weaker than the documented response-hash contract;
  stored and live official responses must match byte-for-byte.
- Native official APIs cannot rely on local annotations for risk semantics.
  Every event field consumed downstream must be extracted from the official
  response through a declarative adapter.
- A replacement notice without a resolvable fiscal year cannot safely mutate a
  per-year state machine, so the downloader fails closed instead of retaining
  the prior selected report.

## Decision Log

- Decision: Keep the existing four skill names.
  Rationale: Their discovery names are already established; the defects are in
  descriptions and contracts, not folder identity.

- Decision: Put shared screening values in
  `.claude/skills/financial-redflag-scan/references/thresholds.yaml`.
  Rationale: The red-flag skill owns risk classification, and YAML supports
  deterministic consistency tests.

- Decision: Treat goodwill/net assets at 20% as a warning and above 30% as high
  risk rather than choosing one threshold and discarding the other.
  Rationale: This preserves both existing values while assigning distinct
  severities.

- Decision: Use semantic filing headings for HK reports and Section 10 for the
  current A-share annual-report structure.
  Rationale: HK reports do not share one mandatory numbered section layout.

- Decision: Use `part_id/section_id` as the progress key and derive the total from
  the template.
  Rationale: Bare `§4.x` identifiers repeat across Parts.

- Decision: Add `--as-of YYYY-MM-DD` to the filing downloader and filter by
  announcement date before fiscal-year de-duplication.
  Rationale: Historical research must not select a correction or republication
  that was unavailable at the target report's disclosure cutoff.

- Decision: Use one primary industry overlay and one primary valuation route;
  secondary classifications add checks or discounts but never replace the
  primary valuation basis.
  Rationale: "Take the strictest" was not executable when bank, cyclical, and
  leverage classifications overlapped.

- Decision: Treat replacement of completed generic bank sections as an explicit
  schema-migration exception.
  Rationale: Preserving incompatible generic sections would bypass the bank
  metric and valuation contracts.

## Implementation Outline

1. Add focused tests under `tests/unit/skills/` for frontmatter, filing routing,
   downloader syntax, threshold registry, formula naming, HK governance routing,
   output schema, dynamic progress, reference integrity, word count, and Chinese
   spacing.
2. Repair `read-filing`, then run its focused contract tests and a fresh-agent
   application scenario.
3. Add the threshold registry and repair the red-flag skill, fraud library,
   statement-reading reference, and template values. Run focused tests and an
   application scenario.
4. Repair management analysis with exchange-aware governance routing and an
   eight-section output contract. Run focused tests and an application scenario.
5. Repair value-profile routing, progress identifiers, template references, and
   progressive disclosure. Run focused tests and an application scenario.
6. Mechanically remove whitespace directly between Chinese characters across
   the skill Markdown files, then rerun all skill tests.

## Validation

Focused command:

    .venv/bin/pytest tests/unit/skills -q

Relevant regression command:

    .venv/bin/pytest tests/unit/skills tests/integration/test_download_filings.py \
      tests/integration/test_extract_pdf.py -q

Static success criteria:

- All four frontmatter descriptions start with `Use when` and contain no angle
  brackets.
- No skill routes A-share financial statements to Section 5.
- The documented downloader command matches the parser.
- Shared thresholds parse from one YAML registry.
- No formula calls expected sales cash receipts "true revenue."
- HK management analysis has a governance alternative when no supervisory board
  exists.
- Management mode B covers template sections 4.1 through 4.8.
- Profile progress has no hard-coded `/67`.
- Every referenced local skill file exists.
- `value-profile/SKILL.md` is below 5,000 whitespace-delimited words.
- No whitespace remains directly between two Chinese characters.

## Outcomes & Retrospective

Verification evidence before the third isolated review:

- `96 passed` in the focused financial-skill contract suite.
- `173 passed` across skill contracts, filing downloader integration tests, and
  PDF extraction integration tests.
- All four skills pass `skill-creator/scripts/quick_validate.py`.
- `scripts/download_filings.py` passes Python bytecode compilation.
- The CJK-to-CJK whitespace scan and `git diff --check` produce no findings.

The third independent behavior evaluation completed with actionable findings.
All findings were reproduced with failing regression tests and repaired.

Fresh verification after those repairs:

- `350 passed` in the focused financial-skill contract suite.
- `197 passed` across filing downloader, research downloader, event manifest,
  and PDF extraction integration tests.
- `1109 passed` in the full unit suite, with two existing
  `ConstantInputWarning` warnings.
- Ruff reports `All checks passed!` for all changed Python and test files when
  semantic full-width Chinese punctuation rules `RUF001` and `RUF100` are
  excluded.
- All four skills pass `skill-creator/scripts/quick_validate.py`.
- Python compilation and `thresholds.yaml` parsing pass.
- `value-profile/SKILL.md` contains 3,965 whitespace-delimited words.
- The CJK-to-CJK whitespace scan and `git diff --check` produce no findings.

The fourth independent behavior evaluation completed in four fresh, isolated,
read-only agent contexts. It found additional gaps, all reproduced before
repair:

- yearless correction/cancellation notices bypassed the filing state machine;
- a PDF source could change during extraction and be bound to stale text;
- native event annotations were not official-evidence-bound;
- native subject coverage was not part of the official request;
- query-window lower bounds and byte-level response equality were not enforced;
- standalone and resume state schemas omitted required hashes or migration
  states.

The corresponding focused suites now report `156 passed` for the filing
downloader, `17 passed` for PDF extraction, `36 passed` for the event manifest,
and `418 passed` for financial-skill contracts. A fifth isolated review is in
progress. Product-analysis implementation remains gated on four exact `PASS`
results.

The fifth isolated review found ten additional evidence-completeness and
resume-safety gaps. Each was first reproduced by a failing regression test,
then repaired:

- event categories now aggregate every applicable official authority into
  `source_count` and `sources`;
- same-URL PDFs are re-fetched and changed official bytes replace stale local
  copies;
- immutable PDF publication validates source sidecar metadata after copying;
- unrelated announcements are classified before target-year filtering, and
  older independent reports are marked outside the requested window;
- official listing dates flow into search traces and all documented downloader
  invocations;
- early exits publish canonical evidence, Mode B separates PDF and extracted
  text arguments, scratch checkpoints hash completed bodies, and pre-evidence
  red-flag reports have a legal resume state.

Fresh verification after the fifth-review repairs:

- `439 passed` in the financial-skill contract suite.
- `171 passed` in the filing downloader integration suite.
- `139 passed` in the event-manifest suite with `94%` statement coverage.
- `1198 passed` in the full unit suite, with two existing
  `ConstantInputWarning` warnings.
- `362 passed` across the four relevant integration suites.
- Ruff, Python compilation, all four skill validators, threshold YAML parsing,
  the CJK-to-CJK whitespace scan, and `git diff --check` all pass.
- `value-profile/SKILL.md` contains 4,025 whitespace-delimited words.

Product-analysis implementation remains gated on four exact `PASS` results from
the sixth isolated review.

The sixth isolated review found executable event-collection, content-addressed
rebinding, exact-page citation, terminal-state recovery, deterministic
threshold, confirmation ownership, and current-HK-issuer scope gaps. The
corresponding RED-GREEN repairs now include:

- an official query-plan schema and `collect_event_evidence.py` collector used
  before event-manifest construction;
- content-addressed manifest publication with immutable old evidence and atomic
  parent rebinding;
- Mode B success/failure schemas, exact quote/hash citation binding, and
  `read-filing` caller enforcement;
- explicit `manual_review` and `output_quality_failure` recovery gates;
- deterministic registry entries for four previously ambiguous red-flag rows;
- mutually exclusive management precheck events and one-metric promise series;
- cache validation against source/artifact hashes and page markers before every
  read.

Fresh verification after the sixth-review repairs:

- `457 passed` in the financial-skill contract suite.
- `370 passed` across filing downloader, research downloader, PDF extraction,
  event manifest, and event collector integration suites.
- `1216 passed` in the full unit suite, with two existing
  `ConstantInputWarning` warnings.
- Event-manifest tests report `144 passed` and `92%` statement coverage.
- Ruff, Python compilation, all four skill validators, YAML/JSON parsing,
  CJK-to-CJK whitespace scan, and `git diff --check` pass.

Product-analysis implementation remains gated on four exact `PASS` results from
the seventh isolated review.

The seventh-review repairs also exposed accidental compression of established
skill contracts. The restored contracts cover filing version transitions,
expanded-history revalidation, scratch resume hashes, full source-manifest
metadata, explicit invalidation sets, management-veto transactions, Mode A
source parity, and final live-source checks. Obsolete `.tmp`/`mv` and temporary
event-manifest assertions now verify CAS publication and the builder's returned
content-addressed path instead.

Fresh verification before the seventh post-repair review:

- `469 passed` in the financial-skill contract suite.
- `384 passed` across filing downloader, research downloader, PDF extraction,
  event manifest, event collector, and CAS integration suites.
- `1228 passed` in the full unit suite, with two existing
  `ConstantInputWarning` warnings.
- Ruff reports `All checks passed!`; Python compilation, all four skill
  validators, JSON/YAML parsing, the CJK-to-CJK whitespace scan, and
  `git diff --check` pass.
- `read-filing/SKILL.md` is exactly 500 lines.

Four new read-only reviewers are running. Product-analysis implementation
remains gated on four exact `PASS` results.

The seventh-review follow-up repairs now also enforce:

- identity, target fiscal year, AS_OF, and target-profile creation before event
  collection or Mode B reading;
- immutable content-addressed annual manifests with official catalog and
  selected-PDF live revalidation;
- schema-valid management dependency failures and directional handling for
  upper-bound, loss-reduction, and nonpositive guidance;
- A+H source unions, per-jurisdiction issuer codes and listing dates, and
  source-level query-code persistence.

Fresh verification after these repairs:

- `480 passed` in the financial-skill contract suite.
- `390 passed` across the six relevant integration suites.
- `1239 passed` in the full unit suite, with two existing
  `ConstantInputWarning` warnings.
- Ruff, Python compilation, all four skill validators, JSON/YAML parsing,
  CJK-to-CJK whitespace scan, `read-filing`'s 500-line limit, and
  `git diff --check` pass.

Four new isolated reviewers are required before product-analysis work begins.

The latest seventh-review follow-up cycle reproduced and repaired:

- bootstrap ordering so the authenticated listing bundle exists before filing
  downloads;
- standalone versus subroutine read-filing routing and pre-analysis resume
  checkpoints;
- executable bank and inapplicable-row evidence contracts;
- management failure, dependency, pending-resume, and directional-guidance
  schemas;
- profile CAS guards over both bound manifests;
- authenticated A+H listing-code and listing-date discovery without the static
  pair registry;
- POST/JSON profile requests, unknown-source errors, distinct enforcement
  actions, PDF publication races, and manifest-identity live revalidation.

Fresh verification before the next four isolated reviewers:

- `486 passed` in the financial-skill contract suite.
- `400 passed` across the six relevant integration suites.
- `1245 passed` in the full unit suite, with two existing
  `ConstantInputWarning` warnings.
- Ruff, Python compilation, all four skill validators, JSON/YAML parsing,
  CJK-to-CJK whitespace scan, `read-filing`'s exact 500-line contract, and
  `git diff --check` pass.

Product-analysis implementation remains gated on four exact `PASS` results.

Fresh repository-wide verification before the next isolated review:

- `1750 passed, 28 skipped` across the entire pytest suite, with three existing
  `ConstantInputWarning` warnings.
- `418 passed` across the six directly relevant integration suites.
- Ruff, Python compilation, all four skill validators, JSON/YAML parsing,
  CJK-to-CJK whitespace scan, `read-filing`'s exact 500-line contract, and
  `git diff --check` pass.
- Supplemental coverage reports `88%` for `build_event_manifest.py` and `71%`
  for `collect_event_evidence.py`; the repository does not currently enforce a
  coverage threshold for these scripts.

Four fresh isolated read-only reviewers are running. Product-analysis
implementation remains gated on four exact `PASS` results.

Fresh repository-wide verification on 2026-07-27:

- `1781 passed, 28 skipped` across the entire pytest suite, with three existing
  `ConstantInputWarning` warnings and exit code 0.
- No product-analysis skill files were created or modified in this repair run.

The latest isolated-review findings were reproduced as contract and integration
failures before repair. Restoring the explicit contracts reduced the financial
skill suite from `487 passed, 51 failed` to `538 passed`. The event collector's
rolling-window schema then correctly rejected two stale fixtures; adding
`include_open_before_start=true` to those rolling plans produced `14 passed`.

Fresh repository-wide verification after all latest repairs:

- `1789 passed, 28 skipped` across the entire pytest suite, with three existing
  `ConstantInputWarning` warnings and exit code 0.
- Ruff reports `All checks passed!`; Python compilation, all four skill
  validators, JSON/YAML parsing, the CJK-to-CJK whitespace scan, and
  `git diff --check` pass.
- `read-filing/SKILL.md` remains exactly 500 lines and
  `value-profile/SKILL.md` contains 4,099 whitespace-delimited words.
- No product-analysis skill files were created or modified.

The next action is four fresh isolated read-only reviews, one per financial
skill. Per the user's current instruction, this run stops after all four return
exact `PASS`; product-analysis implementation is deferred.

Fresh verification after the latest review repairs on 2026-07-27:

- `12 passed` in the latest-review contract subset and `550 passed` in the
  complete financial-skill contract suite.
- `433 passed` across filing downloader, research downloader, PDF extraction,
  event manifest, event collector, CAS publication, and market-manifest
  integration suites.
- `1803 passed, 28 skipped` across the complete pytest suite, with three
  existing `ConstantInputWarning` warnings and exit code 0.
- Ruff, Python compilation, all four skill validators, JSON/YAML parsing,
  CJK-to-CJK whitespace scan, and `git diff --check` pass.
- `read-filing/SKILL.md` remains exactly 500 lines and
  `value-profile/SKILL.md` contains 4,114 whitespace-delimited words.
- No product-analysis skill files were created or modified.

The next action remains four fresh isolated read-only reviews. Product-analysis
implementation is explicitly out of scope for this run.

The next review cycle found that byte-stable official responses were not enough
to protect every derived field, and that several prose-only contracts were not
machine consumable. Focused tests first reproduced:

- tampered market values escaping as a raw `ValueError`;
- annual candidate metadata diverging from a byte-identical live catalog;
- event-manifest subjects diverging from a byte-identical official roster;
- unstructured 29-row red-flag thresholds and unstable action requests;
- management success responses carrying pending state or premature workflow
  completion.

Fresh verification after the corresponding RED-GREEN repairs:

- `555 passed` in the complete financial-skill contract suite.
- `441 passed` across filing downloader, research downloader, PDF extraction,
  event manifest, event collector, CAS publication, and market-manifest
  integration suites.
- `1816 passed, 28 skipped` across the complete pytest suite, with three
  existing `ConstantInputWarning` warnings and exit code 0.
- Ruff reports `All checks passed!` with semantic full-width Chinese
  punctuation rules `RUF001` and `RUF100` excluded; Python compilation, all
  four skill validators, JSON/YAML parsing, the CJK-to-CJK spacing scan, and
  `git diff --check` pass.
- `read-filing/SKILL.md` remains exactly 500 lines and
  `value-profile/SKILL.md` contains 4,136 whitespace-delimited words.
- No product-analysis skill files were created or modified.

The next action remains four entirely fresh isolated read-only reviews. This
run stops after all four return exact `PASS`; product-analysis implementation
remains deferred.

Final repair closure on 2026-07-27:

- Four parallel read-only reviewers returned exact `PASS` for `read-filing`,
  `financial-redflag-scan`, `management-analysis`, and `value-profile`.
- `558 passed` in the complete financial-skill contract suite.
- `251 passed` across event collection, event manifest, market manifest, and
  CAS publication integration suites.
- The earlier repository-wide run reached `1938 passed, 28 skipped` with one
  stale native-listing fixture failure. The fixture was corrected and its full
  event integration surface subsequently passed; the 75-second repository-wide
  suite was not repeated.
- Ruff passes with semantic Chinese punctuation rules `RUF001` and `RUF100`
  excluded; Python compilation, all skill validators, JSON/YAML parsing,
  CJK-to-CJK spacing, and `git diff --check` pass.
- `read-filing/SKILL.md` remains exactly 500 lines and
  `value-profile/SKILL.md` contains 4,168 whitespace-delimited words.
- No product-analysis skill files were created or modified.
