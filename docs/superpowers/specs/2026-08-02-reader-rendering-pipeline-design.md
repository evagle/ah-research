# Reader Rendering Pipeline Design

## Purpose

Separate research generation from reader-facing rendering so internal recovery
metadata and AI workflow details cannot leak into investor HTML.

The upstream research skills remain responsible for facts, analysis, numbers,
qualifications, and investment judgments. The rendering pipeline receives the
completed research Markdown and produces a reader-only projection before any
HTML is generated.

## Pipeline

The processing order is fixed:

```text
research skills and subskills
  -> complete research Markdown
  -> reader projection
  -> negative scan and automatic removal
  -> post-removal validation
  -> pure HTML rendering
  -> final in-memory assertion
  -> atomic HTML write
```

Rendering is the final layer. No renderer may fetch evidence, complete missing
analysis, add facts, change numbers, or alter an investment conclusion.

## Components

### Research generation

The existing `value-profile` workflow and its subskills produce the canonical
Markdown profile. That file remains the only durable and recoverable research
record. It may contain reader-facing analysis together with machine-only
comments, evidence metadata, receipts, and recovery state.

### Reader rendering rules

Add
`.claude/skills/value-profile/references/reader-rendering.md` as the single
detailed contract for the final reader-facing layer. It defines:

- the handoff from completed research to rendering;
- permitted reader-facing editorial changes;
- machine-only content classes;
- automatic-removal and console-reporting behavior;
- formatting cleanup;
- pre-render validation; and
- the pure renderer contract.

The main `value-profile/SKILL.md` retains only the handoff, required processing
order, and command invocation. Detailed rendering rules do not remain mixed
into the main skill. Overlapping output-filtering rules in
`profile-writing-style.md` move to the new reference, with a link left behind.

The `value-profile` skill applies the semantic tone pass after research
generation and before invoking the deterministic CLI. This is an editorial
projection of the already generated reader-facing body, not another research
pass. It may improve natural Chinese, remove repeated caveats, and remove
research-process narration. It may not add claims, change values, weaken or
strengthen qualifications, or change the investment judgment. Machine recovery
metadata remains intact for the deterministic projection step.

### Reader projection

Add `scripts/profile_reader_projection.py`. It is a deterministic,
independently testable projection from canonical Markdown to reader Markdown.
It:

- removes explicitly marked machine comments;
- removes internal evidence fields and their continuation blocks;
- removes machine-only tables or sections as complete Markdown blocks;
- removes known workflow narration and recovery fields;
- repairs empty headings, empty tables, redundant separators, and whitespace
  left by removal;
- records every removal with its category, original line range, and a short
  content summary; and
- scans the projected Markdown again before returning it.

The removal classes include machine citations and receipts, confidence and
management-calibration fields, fingerprints and hashes, schema versions,
claim/role/route states, ledger and run-store paths, source-attempt routing,
and other text that exists only to resume or audit AI work.

Recognized leaks are deleted rather than treated as publication blockers. The
CLI prints each deletion. If another recognized leak appears after the first
pass, the projection deletes the smallest complete Markdown block containing
it and reports that deletion. Content length is not a publication gate; the
user evaluates whether the remaining analysis is sufficient.

Projection stops only for technical failures such as unreadable input,
unparseable output, an entirely empty reader document, or a leak that cannot be
removed without producing invalid Markdown.

### HTML renderer

Add `scripts/profile_html_renderer.py`. It accepts only projected reader
Markdown and performs Markdown-to-HTML conversion, heading IDs, table
containers, the table of contents, document styling, and responsive layout.
It contains no filtering, research, or evidence-state logic.

Keep `scripts/render_profile_html.py` as a thin compatible CLI. Its only job is
to orchestrate:

1. read the canonical Markdown;
2. call reader projection;
3. print removal records;
4. require projection validation to pass;
5. call the pure HTML renderer;
6. assert in memory that machine-only markers are absent; and
7. atomically write the final HTML.

Existing calls such as
`uv run python scripts/render_profile_html.py <profile-path>` remain valid. No
persistent `.reader.md` file is introduced.

## Console Behavior

Removal output is concise and actionable:

```text
[reader-projection] removed machine-table lines 312-326: 角色 / 状态 / 路由终态
[reader-projection] removed metadata line 418: 置信度
[reader-projection] removed 7 machine-only blocks
```

The command continues to print the final HTML path on success. Technical
failures identify the remaining category and source location and do not replace
an existing HTML file.

## Testing

Keep local validation deliberately small and fast:

1. A single reader-projection unit test uses one representative Markdown
   fixture containing a machine table, hash, path, internal metadata, workflow
   narration, normal investment prose, numbers, and a normal table. It asserts
   removal, console records, and preservation of reader content.
2. The existing render CLI integration test exercises the real command and
   asserts that the final HTML contains the core prose and table but none of the
   machine-only fields.

Do not add a parameterized test matrix, a new contract-test framework, or a
full profile regression suite for this refactor. During development, run only
these two targeted tests and lint or format checks for changed files. The full
repository suite remains a CI responsibility.

## Compatibility And Scope

- Canonical profile Markdown and recovery metadata remain unchanged.
- The existing rendering CLI and output path behavior remain unchanged.
- The change does not redesign research schemas or source-discovery contracts.
- The change does not introduce an AI call inside the Python renderer.
- The Pop Mart profile is rerendered through the new pipeline as a practical
  verification, but it is not turned into a large golden-file test.

## Acceptance Criteria

- Research generation and HTML rendering have explicit, separate contracts.
- Detailed rendering instructions live in their own Markdown reference.
- HTML rendering cannot begin until reader projection and negative validation
  complete.
- Recognized machine-only content is removed and reported in the console.
- The pure renderer receives reader-only Markdown.
- Final HTML contains human-facing investment analysis and no known machine
  metadata.
- The two targeted tests pass quickly.
