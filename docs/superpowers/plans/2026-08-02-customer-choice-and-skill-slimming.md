# Customer Choice And Skill Slimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require every product analysis to answer three core competitive-advantage questions, remove duplicated value-profile instructions, and strengthen the Pop Mart product conclusion.

**Architecture:** `product-analysis` owns the customer-choice method, while `value-profile` only invokes it and validates its handoff. Reader-writing rules have one owner in `profile-writing-style.md`; final rendering remains owned by `reader-rendering.md`; obsolete generic §1.3 prompts are removed because product sections must use `product-analysis`.

**Tech Stack:** Markdown skills and references, pytest contract tests, Python profile renderer

## Global Constraints

- Distinguish observed facts, supported inference, and unknowns.
- Low switching cost must not be described as preventing customer departure.
- Consumer, B2B, and commodity products use adaptive customer-choice wording.
- Do not change Pop Mart's final narrow-moat conclusion without new evidence.
- Delete duplicate rules only after their current requirements exist in the owned reference.
- Add no new test function; extend existing targeted contract tests.
- Do not run the full suite locally.

---

### Task 1: Three Core Product-Advantage Questions

**Files:**
- Modify: `.claude/skills/product-analysis/SKILL.md`
- Modify: `.claude/skills/value-profile/SKILL.md`
- Modify: `tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Produces: a required `产品竞争力三问结论` in product-analysis output
- Consumes: §1.1 and §1.3 Mode B product evidence
- Preserves: final moat ownership in `value-profile`

- [ ] **Step 1: Extend existing product contract tests**

Add assertions to the existing product-analysis chain and value-profile
delegation tests for:

```python
for question in (
    "客户为什么从它这里购买并持续复购或续约",
    "为什么其他资本没有提供更高性价比",
    "假设巨头携巨资进入",
):
    assert question in product_skill
assert "产品竞争力三问结论" in value_profile
```

- [ ] **Step 2: Run the targeted tests and verify failure**

Run only the existing named tests covering the product chain, delegation, and
Pop Mart structure. Expected: failure because the three-question contract is
not yet present.

- [ ] **Step 3: Add the adaptive three-question contract**

After `Step 6—需求侧机制`, require one compact synthesis answering:

1. attraction, repeated choice, and named alternatives in the same situation;
2. why competitors and other capital have not offered better value and taken
   the share; and
3. resilience to heavily funded entry, including whether future products or
   hits come from a repeatable process.

Add consumer, B2B, and commodity adaptations. Require observed/inferred/unknown
labels in substance, not necessarily as literal prefixes. Add a completion
gate rejecting output that merely fills earlier tables without this synthesis.

- [ ] **Step 4: Add the parent acceptance gate**

In `value-profile` product acceptance, require the combined §1.1/§1.3 result to
contain the three-question synthesis. §1.8 and §3 consume it; ordinary workers
cannot recreate or substitute it.

- [ ] **Step 5: Run the targeted contract tests**

Expected: all selected tests pass.

### Task 2: Migrate And Delete Duplicate Instructions

**Files:**
- Modify: `.claude/skills/value-profile/SKILL.md`
- Modify: `.claude/skills/value-profile/references/profile-writing-style.md`
- Modify: `.claude/skills/value-profile/references/operations.md`
- Modify: `tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Produces: one owner for reader-writing rules
- Produces: a shorter orchestration-only `value-profile/SKILL.md`
- Removes: obsolete generic §1.3 subagent prompt

- [ ] **Step 1: Update ownership tests first**

Change the existing execution-summary style test to read
`profile-writing-style.md`. Change the ability-circle dispatch test to inspect
the live Step 3b contract instead of the obsolete §4.7 sample. Strengthen the
orchestrator test to require links to `operations.md`,
`profile-writing-style.md`, and `reader-rendering.md`, and lower the expected
main-skill size below 625 lines.

- [ ] **Step 2: Consolidate current style rules**

Move unique current requirements from main §4.6 into
`profile-writing-style.md`, including:

- Part 0 status title, unprefixed conclusion, and three-color signal list;
- citation placement and no inline self-references;
- tracking visibility and one execution-summary heading;
- natural Chinese review;
- runtime metadata exclusion; and
- final output-quality review.

Do not duplicate terminology, hierarchy-table, evidence-gap, or reader
projection rules already owned by existing sections.

- [ ] **Step 3: Remove duplicate and obsolete bodies**

Replace main §4.6 with a concise required-read and acceptance pointer. Remove
main §4.7 entirely. Replace the duplicated operations §4.6 body with a pointer
to `profile-writing-style.md` and `reader-rendering.md`. Remove the stale
generic §1.3 prompt from operations because §1.1 and §1.3 must delegate to
`product-analysis`.

- [ ] **Step 4: Run ownership and line-count tests**

Expected: targeted tests pass and `value-profile/SKILL.md` is below 625 lines.

### Task 3: Pop Mart Synthesis And Rendering

**Files:**
- Modify: `profiles/09992.HK-2026-08-02.md`
- Regenerate: `profiles/09992.HK-2026-08-02.html`
- Modify: `tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes: existing accepted Pop Mart citations and product evidence
- Produces: one visible `产品竞争力三问结论` in §1.3

- [ ] **Step 1: Extend the existing Pop Mart assertion**

Require the existing product-section test to find:

```python
for requirement in (
    "**产品竞争力三问结论:**",
    "盲盒随机性只是放大器",
    "每次购买时重新赢得客户",
    "收藏者社区",
    "IP命中率",
):
    assert requirement in differentiation
```

- [ ] **Step 2: Rewrite the opening of §1.3**

Replace the two overlapping opening paragraphs with a compact three-question
synthesis covering:

- design, IP, collection, gifting, social display, unboxing surprise, and
  companionship;
- current choice versus TOP TOY, Bloks, LEGO, and other discretionary spend;
- member repurchase and direct-channel feedback without claiming lock-in;
- defense through repeated preference, design and IP execution, channels,
  multi-IP breadth, and scale under funded entry; and
- evidence of multi-year IPs and cross-category extension, alongside unknown
  hit rate, funnel economics, community strength, and lifecycle economics.

Keep the existing comparative tables and accepted citations. State that
blind-box randomness amplifies demand but is not a durable moat by itself.

- [ ] **Step 3: Run focused contract and rendering tests**

Run the modified product contract tests and the two existing reader-rendering
tests. Expected: all selected tests pass.

- [ ] **Step 4: Rerender and inspect Pop Mart**

Run:

```bash
uv run python scripts/render_profile_html.py profiles/09992.HK-2026-08-02.md
```

Verify the new synthesis is visible, machine-only fields remain absent, and
the canonical Markdown retains recovery metadata.

- [ ] **Step 5: Commit and push**

Commit the skill migration, Pop Mart update, regenerated HTML, and targeted
test changes. Push the existing PR branch and confirm CI starts.
