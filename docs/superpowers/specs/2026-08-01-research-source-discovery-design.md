# Research Source Discovery Skill Design

## Goal

Add one shared skill for discovering industry reports, market data, official
statistics, filings, and specialist research sources. Audit the 63 user-supplied
entries individually, route useful sources by research need, and distinguish
content reliability from current access conditions.

## Architecture

Create `.claude/skills/research-source-discovery/` with:

- `SKILL.md`: source-selection workflow, evidence hierarchy, access-failure
  handling, and output contract.
- `references/source-catalog.md`: one normalized record per supplied entry,
  grouped by source category.
- `references/search-playbook.md`: query patterns and fallback routes for
  reports, official statistics, company valuation, and specialist industries.

The catalog is the single source of truth. `product-analysis`, `value-profile`,
and `read-filing` link to the shared skill where external industry or market
evidence is needed; they do not copy the catalog.

Source routing is many-to-many, not a fixed category-to-site mapping. Each
research question may use several independent sources, and each source may
support several research needs.

## Source Record

Each numbered entry records:

- canonical name and URL;
- category and best use;
- accuracy and practical utility;
- observed reachability and access model;
- limitations and prohibited evidence uses;
- last checked date and explicit evidence level.

Accuracy uses the publisher and provenance of the underlying material, not the
quality of the website UI. Reachability distinguishes public access, login,
paid membership, anti-bot or regional restriction, redirect/domain migration,
and confirmed unavailability.

## Evidence Rules

Use official regulators, exchanges, ministries, statistical agencies, and
issuer filings as primary evidence. Use original reports from research firms
and consultancies as attributed secondary evidence. Use aggregators, media,
social platforms, and report indexes for discovery only unless the original
document and publisher can be verified.

Evidence levels:

- `High`: current first-party page, response, or published access policy was
  directly verified.
- `Medium`: current search index or credible secondary evidence supports the
  conclusion, but the first-party content was not fully accessible.
- `Low`: only historical reputation, DNS, or an unverified listing supports the
  conclusion.

One failed request never proves permanent closure. Runtime research must
re-check high-value sources and record the final error before declaring an
access limitation.

For each material claim, build a source portfolio:

1. Search the highest-authority applicable sources.
2. Cross-check with an independent source when the claim affects valuation,
   risk, market size, or competitive position.
3. When a source has no result, requires unavailable membership, or fails
   technically, continue through other applicable sources in the same category
   and then adjacent categories.
4. Report a source gap only after recording every compliant route attempted,
   its query, access result, and final error.

No source is mandatory merely because it appears first in the catalog. A
working lower-tier source can discover a document, but conclusions must cite
the original publisher whenever the original can be identified.

## Integration

- `product-analysis`: use the shared skill for industry structure, product
  benchmarks, consumer data, and specialist vertical research.
- `value-profile`: use it for macro, industry, valuation-context, and historical
  market research, while keeping bound official manifests authoritative.
- `read-filing`: use it only for external peer and industry context; exchange
  filings and regulatory evidence remain on the existing official-source path.

The shared skill cannot replace filing manifests, event manifests, market-data
manifests, or the existing machine-citation contracts.

## Validation

Add contract tests that require:

- discoverable frontmatter and all 63 numbered entries;
- required source-record fields and evidence-level vocabulary;
- category and access-status coverage;
- multi-source portfolios, independent cross-checking, and fallback exhaustion;
- references from the three consuming skills;
- explicit primary-source precedence and aggregator restrictions.

Run the skill validator and focused skill-contract tests. Review the final diff
to confirm no unrelated dirty-worktree changes were staged or modified.
