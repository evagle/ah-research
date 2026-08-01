---
name: source-discovery
description: Use when research needs external reports, industry or macro data, company and investor-relations sources, official statistics, market evidence, source validation, or fallback searches after a source is missing, inaccessible, paywalled, or inconclusive.
---

# Source Discovery

Use this skill when a caller needs external evidence beyond already-bound filing,
event, counterpart, or market manifests. Inputs are the research question,
`AS_OF`, geography, industry, required fact types, and any caller-supplied
source constraints. Output is a source portfolio and research ledger with
candidate source, query, status, result, access limitation, evidence level, and
next fallback.

Read the detailed route guidance in
`references/search-playbook.md` after this file.

## Workflow

Follow this sequence exactly:

`question decomposition -> known-source routing -> dynamic discovery -> access/provenance validation -> independent cross-check -> fallback exhaustion -> source ledger handoff`

At the start, translate the request into claim types, time bounds, geography,
industry vocabulary, acceptable evidence types, and any source restrictions.
Then route through known high-authority sources before expanding outward.

Keep separate ratings for:

- `source_authority`
- `practical_utility`
- `current_reachability`
- `conclusion_evidence`

Evaluate each newly discovered candidate on:

`provenance; primary/secondary status; methodology transparency; coverage; timeliness; reproducibility; correction history; access stability; conflicts of interest; fitness for the requested claim`

Do not report a source gap until the ledger includes the attempted alternatives
and the final error for the exhausted route.

## Catalog And Uncataloged Sources

The source catalog is a seed registry, not a closed allowlist.

Do not reject a source solely because it is absent from the catalog.

Use uncataloged sources when the question requires them and they pass validation.

Record uncataloged sources with the same fields, access status, provenance, fallback peers, and evidence level.

## Evidence And Access Rules

Treat company websites as first-party subject evidence. Use issuer/company IR,
newsrooms, product and pricing pages, ESG pages, and customer, supplier,
competitor, and association websites for subject facts, quotations, disclosed
policies, product specs, and attributable statements.

Do not treat a company's claims about market leadership, customer outcomes, product superiority, or competitive advantage as independent proof. Any evaluative claim from a company page needs independent support.

Use aggregators, media, social platforms, and report indexes for discovery only. App mirrors and portal indexes can help locate a document, but conclusions must cite the original publisher whenever the original can be identified.

For announcements and regulatory correspondence, cover inquiry/concern letters,
issuer responses, supervisory measures, disciplinary actions, penalty
decisions, corrections/restatements, trading suspensions, and material-event
notices. Search app or aggregator indexes when useful, then trace to the
CNINFO, SSE, SZSE, HKEXnews, or regulator original. Record announcement time,
document/announcement ID, status, URL, and replacement relationship.

## Fallback Exhaustion

One failed request never proves permanent closure.

If a source returns no result, is paywalled, requires unavailable access, or fails technically, continue through other applicable sources in the same category and then adjacent categories.

Report a source gap only after recording every compliant route attempted, its query, access result, and final error.

## Evidence Levels And Ledger Contract

Every source record must include an explicit evidence level: High, Medium, or Low.

Every access conclusion and source ledger row must include an explicit evidence level: High, Medium, or Low.

Each access attempt and each final handoff row must include at least:

- `candidate_source`
- `query`
- `status`
- `result`
- `access_limitation`
- `access_conclusion`
- `evidence_level`
- `next_fallback`

Use `High` when the current first-party source or access policy was directly
verified, `Medium` when credible current secondary evidence supports the access
or provenance conclusion, and `Low` when only weak or historical evidence
supports it.
