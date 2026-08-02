# Hierarchical Revenue Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the approved three-column hierarchy table the default for multi-level revenue disclosures and migrate the Pop Mart profile.

**Architecture:** `product-analysis` defines the upstream output shape, while `value-profile` validates and writes the final profile. The Markdown uses semantic HTML classes, and the standalone renderer supplies presentation-only CSS without changing generic table behavior.

**Tech Stack:** Markdown skill contracts, Python, markdown-it-py, pytest, standalone HTML/CSS

## Global Constraints

- Preserve all existing revenue values and hierarchy.
- Show the period and unit as `2025年 · 亿元`.
- Use three columns: category, amount, and share of total revenue.
- Keep different classification dimensions in separate tables.
- Do not overwrite unrelated user changes in the dirty worktree.

---

### Task 1: Define and test the hierarchy-table contract

**Files:**
- Modify: `tests/unit/skills/test_financial_skill_contracts.py`
- Modify: `.claude/skills/product-analysis/SKILL.md`
- Modify: `.claude/skills/value-profile/SKILL.md`
- Modify: `.claude/skills/value-profile/references/profile-writing-style.md`
- Modify: `.claude/skills/value-profile/template-zh.md`

**Interfaces:**
- Consumes: multi-level revenue classifications returned by `product-analysis`
- Produces: a three-column semantic hierarchy table accepted by `value-profile`

- [x] **Step 1: Change the contract test to require the approved shape**

Update `test_product_revenue_mix_preserves_hierarchy_and_separates_dimensions`
to require title metadata, three columns, indentation, separated numeric
columns, and the absence of per-level columns and `rowspan`.

- [x] **Step 2: Run the contract test and verify RED**

Run:

```bash
uv run pytest tests/unit/skills/test_financial_skill_contracts.py::test_product_revenue_mix_preserves_hierarchy_and_separates_dimensions -q
```

Expected: failure because the current skill still requires a tree table with
one column per level and `rowspan`.

- [x] **Step 3: Implement the minimal skill contract**

Replace the old output requirement in `product-analysis`, add the final-writer
review rule in `value-profile`, document the semantic markup in
`profile-writing-style.md`, and point the §1.1 template guidance to it.

- [x] **Step 4: Run the contract test and verify GREEN**

Run the Step 2 command. Expected: one passing test.

### Task 2: Add renderer support for the semantic table

**Files:**
- Modify: `tests/integration/test_render_profile_html.py`
- Modify: `scripts/render_profile_html.py`

**Interfaces:**
- Consumes: `table-heading`, `table-meta`, `hierarchy-table`,
  `hierarchy-level-*`, `hierarchy-group`, `hierarchy-subtotal`, and
  `hierarchy-total` classes in Markdown HTML
- Produces: a responsive standalone HTML report with hierarchy styling

- [x] **Step 1: Add a renderer integration fixture and assertions**

Change the sample hierarchy table to the approved three-column markup and
assert that semantic classes and their CSS are present in the generated HTML.

- [x] **Step 2: Run the integration test and verify RED**

Run:

```bash
uv run pytest tests/integration/test_render_profile_html.py -q
```

Expected: failure because the renderer has no hierarchy-table CSS.

- [x] **Step 3: Add minimal hierarchy-table CSS**

Add table heading alignment, period/unit styling, hierarchy indentation,
numeric alignment, and group/subtotal/total row styling. Leave generic table
styles intact.

- [x] **Step 4: Run the integration test and verify GREEN**

Run the Step 2 command. Expected: one passing test.

### Task 3: Migrate and verify the Pop Mart profile

**Files:**
- Modify: `profiles/09992.HK-2026-07-29.md`
- Regenerate: `profiles/09992.HK-2026-07-29.html`

**Interfaces:**
- Consumes: the existing IP ownership hierarchy and values
- Produces: the approved A-layout Markdown source and HTML companion

- [x] **Step 1: Replace the six-column table**

Use the semantic three-column markup, add `2025年 · 亿元`, preserve every
amount and percentage, and retain the same-level validation note.

- [x] **Step 2: Regenerate the HTML companion**

Run:

```bash
uv run python scripts/render_profile_html.py profiles/09992.HK-2026-07-29.md
```

Expected: stdout names `profiles/09992.HK-2026-07-29.html`.

- [x] **Step 3: Run targeted and contract tests**

Run:

```bash
uv run pytest tests/integration/test_render_profile_html.py tests/unit/skills/test_financial_skill_contracts.py -q
```

Expected: all selected tests pass.

- [x] **Step 4: Verify the migrated artifact**

Check that the target section contains `2025年 · 亿元`, exactly three column
headers, hierarchy classes, and no `rowspan`; inspect the generated HTML at
desktop and mobile widths.
