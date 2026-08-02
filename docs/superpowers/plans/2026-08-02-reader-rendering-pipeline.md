# Reader Rendering Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate reader projection from HTML rendering so only human-facing profile content reaches the final renderer.

**Architecture:** The canonical research Markdown remains the durable source. A deterministic projection module removes and reports machine-only blocks, then a pure renderer converts the validated reader Markdown to HTML; the existing CLI only orchestrates those stages and writes atomically.

**Tech Stack:** Python 3.12, `markdown-it-py`, pytest, Markdown skill references

## Global Constraints

- Research generation remains upstream and outside the rendering layer.
- Recognized machine-only content is automatically deleted and reported.
- The final renderer receives only validated reader Markdown.
- No persistent `.reader.md` artifact is created.
- Existing `scripts/render_profile_html.py <profile-path>` calls remain valid.
- Semantic editing may change expression but not facts, numbers, qualifications, or investment conclusions.
- Add only two fast targeted tests; do not add a parameterized matrix or run the full suite locally.

---

### Task 1: Reader Projection

**Files:**
- Create: `scripts/profile_reader_projection.py`
- Create: `tests/unit/test_profile_reader_projection.py`

**Interfaces:**
- Produces: `Removal(category: str, start_line: int, end_line: int, summary: str)`
- Produces: `ProjectionResult(markdown: str, removals: tuple[Removal, ...])`
- Produces: `project_reader_markdown(source: str) -> ProjectionResult`
- Produces: `assert_reader_only(source: str) -> None`

- [ ] **Step 1: Write the failing projection test**

Use one fixture containing an HTML machine comment, `引用/置信度/管理层口径校核`
metadata, a fingerprint table, a ledger path, workflow status text, normal
investment prose with numbers, and a normal financial table. Assert:

```python
result = project_reader_markdown(source)

assert "收入同比增长42.4%" in result.markdown
assert "| 收入 | 130.4 |" in result.markdown
assert "路由终态" not in result.markdown
assert "a" * 64 not in result.markdown
assert "/Users/example/research/source-index.md" not in result.markdown
assert {removal.category for removal in result.removals} >= {
    "html-comment",
    "reader-metadata",
    "machine-table",
    "machine-paragraph",
}
assert_reader_only(result.markdown)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest tests/unit/test_profile_reader_projection.py -q
```

Expected: collection fails because `profile_reader_projection` does not exist.

- [ ] **Step 3: Implement deterministic block projection**

Implement immutable dataclasses and line-aware helpers that:

- remove multiline HTML comments while retaining original line numbers;
- remove internal metadata and list/indented continuation lines;
- identify contiguous Markdown tables and remove the complete table when its
  headers contain machine terms such as `指纹`, `路由终态`, `schema版本`,
  `ledger`, `claim状态`, or `role状态`;
- remove the smallest paragraph containing a 40-64 character hex fingerprint,
  an absolute recovery path, a machine key such as `schema_version` or
  `claim_states`, or workflow-only state narration;
- clean empty headings, redundant separators, and excess blank lines;
- retain a `Removal` for each deleted block; and
- run `assert_reader_only()` on the result before returning.

Use contextual machine patterns rather than deleting ordinary uses of words
such as “状态” or “路径”. Raise `ValueError` only when the source cannot produce
a non-empty valid reader document or a known leak remains after cleanup.

- [ ] **Step 4: Run the projection test**

Run:

```bash
uv run pytest tests/unit/test_profile_reader_projection.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit the projection**

```bash
git add scripts/profile_reader_projection.py tests/unit/test_profile_reader_projection.py
git commit -m "Add reader profile projection"
```

### Task 2: Pure Renderer And CLI Orchestration

**Files:**
- Create: `scripts/profile_html_renderer.py`
- Modify: `scripts/render_profile_html.py`
- Modify: `tests/integration/test_render_profile_html.py`

**Interfaces:**
- Consumes: `project_reader_markdown()` and `assert_reader_only()` from Task 1
- Produces: `render_reader_html(source: str) -> str`
- Preserves: CLI positional `source` and optional `--output`

- [ ] **Step 1: Extend the existing integration test**

Add the same representative machine table, fingerprint, path, and workflow
paragraph to the existing CLI fixture. Assert the final HTML excludes them,
retains the investor prose and tables, and stderr contains concise deletion
records while stdout remains exactly the output path:

```python
assert result.stdout.strip() == str(output)
assert "[reader-projection] removed machine-table" in result.stderr
assert "路由终态" not in html
assert "收入结构" in html
```

- [ ] **Step 2: Run the integration test and verify it fails**

Run:

```bash
uv run pytest tests/integration/test_render_profile_html.py -q
```

Expected: failure because the current renderer does not report removals or
remove all unmarked machine blocks.

- [ ] **Step 3: Extract the pure renderer**

Move heading parsing, Markdown token rendering, table wrappers, document CSS,
and document assembly into `scripts/profile_html_renderer.py`. Expose:

```python
def render_reader_html(source: str) -> str:
    ...
```

Do not import projection patterns or remove content in this module.

- [ ] **Step 4: Reduce the CLI to orchestration**

Keep argument parsing and atomic writing in `render_profile_html.py`. Make its
main flow:

```python
projection = project_reader_markdown(markdown)
for removal in projection.removals:
    print(format_removal(removal), file=sys.stderr)
document = render_reader_html(projection.markdown)
assert_reader_only(document)
_write_atomic(output, document)
print(output)
```

Format single-line removals with `line N` and block removals with
`lines N-M`. Print a final removal count to stderr. Build the complete HTML in
memory and do not replace an existing output file after any projection or
assertion failure.

- [ ] **Step 5: Run both targeted tests**

Run:

```bash
uv run pytest \
  tests/unit/test_profile_reader_projection.py \
  tests/integration/test_render_profile_html.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit the renderer split**

```bash
git add scripts/profile_html_renderer.py scripts/render_profile_html.py tests/integration/test_render_profile_html.py
git commit -m "Separate profile rendering layers"
```

### Task 3: Skill Contract And Pop Mart Verification

**Files:**
- Create: `.claude/skills/value-profile/references/reader-rendering.md`
- Modify: `.claude/skills/value-profile/SKILL.md`
- Modify: `.claude/skills/value-profile/references/profile-writing-style.md`
- Regenerate: `profiles/09992.HK-2026-08-02.html`

**Interfaces:**
- Consumes: the unchanged rendering CLI from Task 2
- Produces: a single detailed reader-rendering contract referenced by the main skill

- [ ] **Step 1: Write the standalone rendering reference**

Document the exact handoff:

```text
completed research Markdown
-> semantic reader edit
-> deterministic projection
-> negative validation
-> pure HTML render
-> atomic write
```

State that semantic editing is reader-facing expression cleanup only. Include
the automatic deletion categories, stderr reporting format, no content-length
gate, and the prohibition on changing facts, values, qualifiers, or judgments.

- [ ] **Step 2: Slim the main skill and writing-style reference**

Replace detailed rendering/filtering instructions in `SKILL.md` with a required
read of `references/reader-rendering.md` and the existing CLI command. In
`profile-writing-style.md`, retain research-writing guidance but point
reader-output filtering and final tone cleanup to the new reference.

- [ ] **Step 3: Rerender the Pop Mart profile**

Run:

```bash
uv run python scripts/render_profile_html.py profiles/09992.HK-2026-08-02.md
```

Expected: the HTML path on stdout, any removals on stderr, and no exception.

- [ ] **Step 4: Run only the two targeted tests and diff checks**

Run:

```bash
uv run pytest \
  tests/unit/test_profile_reader_projection.py \
  tests/integration/test_render_profile_html.py -q
git diff --check
```

Expected: `2 passed` and no whitespace errors.

- [ ] **Step 5: Review the final diff and commit**

Verify that no machine-only text appears in the generated Pop Mart HTML and
that the canonical Markdown still retains its recovery metadata.

```bash
git add \
  .claude/skills/value-profile/SKILL.md \
  .claude/skills/value-profile/references/profile-writing-style.md \
  .claude/skills/value-profile/references/reader-rendering.md \
  profiles/09992.HK-2026-08-02.html
git commit -m "Document reader rendering contract"
```
