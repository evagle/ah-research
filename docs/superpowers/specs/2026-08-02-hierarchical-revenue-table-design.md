# Hierarchical Revenue Table Design

## Goal

Use one compact, reusable presentation for multi-level revenue disclosures in
value profiles. Replace the current repeated level columns and merged cells
with the approved A layout.

## Presentation Contract

- Show one classification dimension per table.
- Put the reporting period and amount unit beside the table title, for example
  `2025年 · 亿元`.
- Use exactly three columns: `收入类别`, `收入`, and `占总收入`.
- Represent parent-child relationships by indentation in the first column.
- Keep amount and percentage in separate right-aligned columns.
- Use stronger weight or a light background for parent groups and subtotals.
- Use a distinct total row.
- Do not use one column per hierarchy level, `rowspan`, placeholder dashes, or
  combined `金额 / 占比` cells.
- Put cross-cutting dimensions such as IP ownership, product category, channel,
  and region in separate tables, and state when they cannot be added together.

## Skill Changes

`product-analysis` owns the upstream revenue-mix output shape. Its output
contract will require the three-column hierarchy table.

`value-profile` owns final profile writing. Its review rules will normalize
multi-level revenue tables to the same shape before saving. The profile writing
reference and the §1.1 template guidance will contain the reusable markup
contract.

## Rendering

The standalone HTML renderer will style semantic classes for:

- the table heading and period/unit metadata;
- level-two and level-three indentation;
- group, subtotal, and total rows;
- right-aligned numeric columns.

Generic Markdown tables remain unchanged.

## Existing Profile Migration

The Pop Mart profile will replace the six-column IP ownership table with the
three-column hierarchy table. The source Markdown remains authoritative, and
the HTML companion will be regenerated from it.

## Verification

- Contract test confirms both skills require the approved shape.
- Renderer integration test confirms semantic hierarchy markup is preserved
  and receives the expected CSS.
- The Pop Mart Markdown and generated HTML are checked for three columns,
  `2025年 · 亿元`, hierarchy classes, totals, and absence of `rowspan`.

## Evidence Level

- Data values and hierarchy: high, from the existing profile and user-provided
  table.
- Cross-company layout suitability: medium, based on information-design
  judgment rather than measured user testing.
