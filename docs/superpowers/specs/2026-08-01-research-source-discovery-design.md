# Research Source Discovery Skill Design

## Goal

Add one complete shared `source-discovery` skill for discovering industry
reports, market data, official statistics, filings, and specialist research
sources. Audit the 63 user-supplied entries individually, route useful sources
by research need, and distinguish content reliability from current access
conditions. Also inventory every core source already used by the repository's
skills and source registries.

## Architecture

Create `.claude/skills/source-discovery/` with:

- `SKILL.md`: source-selection workflow, evidence hierarchy, access-failure
  handling, and output contract.
- `references/source-catalog.md`: one normalized record per supplied entry,
  grouped by source category.
- `references/search-playbook.md`: query patterns and fallback routes for
  reports, official statistics, company valuation, and specialist industries.

The catalog is the single source of truth. `product-analysis`, `value-profile`,
and `read-filing` link to the shared skill where external industry or market
evidence is needed; they do not copy the catalog.

The catalog is a maintained seed registry, not a closed allowlist. When the
known sources do not cover a research need, discover additional candidates from
official link directories, publisher indexes, citations in original reports,
issuer and company websites, investor-relations pages, customer and supplier
websites, competitor websites, industry associations, academic sources, and
search engines. Evaluate new candidates with the same record fields before
using them.

Candidate selection is fitness-for-claim, not a global website ranking. Score a
candidate on provenance, primary versus secondary status, methodology
transparency, coverage, timeliness, reproducibility, correction history, access
stability, and conflicts of interest. The same publisher may be strong for one
fact type and weak for another.

Source routing is many-to-many, not a fixed category-to-site mapping. Each
research question may use several independent sources, and each source may
support several research needs.

The initial existing-source inventory includes CNINFO, SSE, SZSE, HKEX/HKEXnews,
CSRC, MOF, NFRA, PBOC, ChinaMoney, SFC, AFRC, HKMA, Hong Kong Insurance
Authority, Hong Kong Police, ICAC, Hong Kong Judiciary, and the Eastmoney
research API. Treat code registries and live skill contracts as authoritative
for inventory membership; this list is descriptive, not a second registry.
Deduplicate sources already present in the 63 supplied entries by canonical
publisher while preserving the supplied entry number and aliases.

## Source Record

Each numbered entry records:

- origin (`user-supplied`, `existing-core`, or both) and existing code ID;
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

Include useful media and finance portals such as Sina Finance as evaluated
candidates for news discovery, quote navigation, announcement indexing, and
company-information lookup. Do not promote portal copies to primary evidence
when an exchange, regulator, issuer, statistical agency, or original report is
available.

Treat company websites as first-party subject evidence: use them for product
specifications, official announcements, management statements, locations,
pricing, and investor-relations materials. Do not treat a company's claims
about market leadership, customer outcomes, product superiority, or competitive
advantage as independent proof; cross-check those claims with customers,
suppliers, competitors, regulators, industry bodies, or other independent
sources.

Treat exchange announcements and regulatory correspondence as a dedicated
high-priority evidence class. Cover inquiry and concern letters, issuer
responses, supervisory measures, disciplinary actions, penalty decisions,
corrections and restatements, trading suspensions, and material-event notices.
Apps and aggregators may discover or mirror these documents, but the source
portfolio must trace them to CNINFO, SSE, SZSE, HKEXnews, the relevant
regulator, or another original official publisher. Preserve announcement time,
document or announcement ID, status, original URL, and any replacement
relationship.

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

1. Translate the question into needed facts, geography, period, industry, and
   acceptable evidence types.
2. Search the highest-authority applicable known sources.
3. Discover and evaluate new candidates when known sources have no result or
   incomplete coverage.
4. Cross-check with an independent source when the claim affects valuation,
   risk, market size, or competitive position.
5. When a source has no result, requires unavailable membership, or fails
   technically, continue through other applicable sources in the same category
   and then adjacent categories.
6. Report a source gap only after recording every compliant route attempted,
   its query, access result, and final error.

No source is mandatory merely because it appears first in the catalog. A
working lower-tier source can discover a document, but conclusions must cite
the original publisher whenever the original can be identified.

## Integration

- `product-analysis`: use the shared skill for industry structure, product
  benchmarks, consumer data, and specialist vertical research.
- `value-profile`: use it for macro, industry, valuation-context, and historical
  market research, announcements, and regulatory-letter discovery, while
  keeping bound official manifests authoritative.
- `read-filing`: use it only for external peer and industry context; exchange
  filings and regulatory evidence remain on the existing official-source path.

The shared skill cannot replace filing manifests, event manifests, market-data
manifests, or the existing machine-citation contracts.

## Validation

Add contract tests that require:

- discoverable frontmatter and all 63 numbered entries;
- catalog coverage for official domains and core providers already referenced
  by source registries, download scripts, and consuming skills;
- required source-record fields and evidence-level vocabulary;
- category and access-status coverage;
- multi-source portfolios, independent cross-checking, and fallback exhaustion;
- references from the three consuming skills;
- explicit primary-source precedence and aggregator restrictions.

Run the skill validator and focused skill-contract tests. Review the final diff
to confirm no unrelated dirty-worktree changes were staged or modified.
