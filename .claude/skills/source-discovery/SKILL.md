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

Read `references/source-catalog.md` before known-source routing.
The catalog supplies seed routes and audited access facts, not an allowlist or
runtime claim grades. Then read the detailed route guidance in
`references/search-playbook.md`.

For a direct site workflow, read the matching guide before retrieving:

- `references/site-guides/sse.md`
- `references/site-guides/cninfo.md`
- `references/site-guides/hkexnews.md`
- `references/site-guides/hong-kong-regulatory.md`
- `references/site-guides/official-statistics.md`

## Workflow

Follow this sequence exactly:

`question decomposition -> known-source routing -> dynamic discovery -> access/provenance validation -> independent cross-check -> fallback exhaustion -> source ledger handoff`

At the start, translate the request into claim types, time bounds, geography,
industry vocabulary, acceptable evidence types, and any source restrictions.
Then route through known high-authority sources before expanding outward.

Keep separate ratings for:

- `source_authority`: source-property rating for how authoritative the
  publisher is for this claim type. Use `High` for originals or official
  first-party statements about the publisher's own actions, `Medium` for
  credible secondary sources with transparent sourcing, and `Low` for weak,
  indirect, conflicted, or unclear provenance.
- `practical_utility`: source-property rating for whether the source can
  actually answer the requested fact type at the needed geography, industry,
  date, and granularity. Use `High`, `Medium`, or `Low`.
- `current_reachability`: source-property rating for whether the source is
  reachable now through permitted access, with stable URLs or documented access
  limits. Use `High`, `Medium`, or `Low`.
- `conclusion_evidence`: claim-support rating for how strongly the source
  supports the specific conclusion being made. Use `High`, `Medium`, or `Low`.
  Calculate `conclusion_evidence` at runtime for the actual claim after
  inspecting the retrieved evidence. Never copy a catalog route prior into this
  field.

Keep `evidence_level` separate from those fields. `evidence_level` records
confidence in the access/provenance conclusion for this ledger row, not the
source's authority, practical usefulness, reachability, or support for the
research claim.

Evaluate each newly discovered candidate on:

`provenance; primary/secondary status; methodology transparency; coverage; timeliness; reproducibility; correction history; access stability; conflicts of interest; fitness for the requested claim`

Do not report a source gap until the ledger includes the attempted alternatives
and the final error for the exhausted route.

## Catalog And Uncataloged Sources

The source catalog is a seed registry, not a closed allowlist.

Do not reject a source solely because it is absent from the catalog.

Use uncataloged sources when the question requires them and they pass validation.

Record uncataloged sources with the same fields, access status, provenance, fallback peers, and evidence level.

## Runtime Reachability

Read the local reachability cache at `tmp/source-discovery/reachability.json`
when present. For reachability only, apply this exact precedence:

`valid local cache observation -> reviewed snapshot -> profile access record`

Load the reviewed snapshot mapping from
`references/reachability-snapshot.json`; it is the audit-backed route prior
surfaced in the generated catalog. Cache affects reachability only, never authority, citation scope, publisher identity, workflow evidence, or field/API evidence.

Use `source_profiles.ttl_for_status` when deciding whether a cache observation
is valid; do not create a separate TTL policy:

- `reachable` and `reachable-limited`: 30 days
- `login-required`, `paywalled`, and `anti-bot`: 14 days
- `temporarily-unreachable` and `unverified`: 24 hours
- `moved` and `broken-link`: 7 days

For each same-function candidate set, call
`source_profiles.select_routes(profiles, function_id, now, cache=local_cache, snapshot=reviewed_snapshot, geographies=claim_geographies)`
when the claim has a geographic scope. With that optional scope, routes are
eligible only when their profile lists a requested geography or `Global`;
labels are trimmed and compared case-insensitively, and wrong-market routes are
excluded before ranking. Pass a list or tuple of nonblank labels; omit
`geographies` only when the claim has no geographic constraint. The resolver ignores a stale cache
observation before it consults the reviewed snapshot, then falls back to the
profile access record.
A fresh `temporarily-unreachable` route is skipped for same-function fallbacks without changing its authority.
A stale route must be rechecked before treating its status as current.
One failed request never proves permanent closure.

Use noninteractive `urllib` or `curl` for default retrieval and probing.
Use headless Chromium only for JS/session flows, such as a rendered JSF form,
when noninteractive retrieval cannot complete the applicable official workflow.
Never use repeated user Allow prompts.

## Evidence And Access Rules

Treat issuer/company websites as first-party evidence only for that issuer's
own statements, disclosures, actions, products, policies, prices, filings, and
quotations. Use issuer/company IR, newsrooms, product and pricing pages, and
ESG pages for subject facts and attributable issuer statements.

Treat customer, supplier, competitor, and association websites as first-party
evidence only for that publisher's own claims, actions, membership lists,
transactions, policies, product facts, or attributable statements. They count
as independent checks only when the publisher is genuinely independent of the
issuer and independent of the claim being checked.

Do not treat a company's claims about market leadership, customer outcomes, product superiority, or competitive advantage as independent proof. Any evaluative claim from a company page needs independent support.

Aggregators remain discovery-only by default. Media, social platforms, report
indexes, app mirrors, and portal indexes can help locate a document, but
conclusions must cite the original publisher whenever the original can be
identified and read.

A verified-mirror exception applies only when official exchange or regulator
metadata identifies the exact document but the official document body is
technically unreadable. Require that the mirror's identity fields match the
official metadata: issuer or security identifier, normalized title, disclosure
date, document or announcement ID or official path, and document type. An
aligned mirror may support only a downgraded transcription claim. Label it
`non-original`, record the official-body access caveat, and retain the
mirror's own authority with no authority elevation. The mirror must not
support claims absent from the identified official document. Continue seeking
the official body or another official copy and preserve the official metadata
as the identity evidence.

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
- `source_authority`
- `practical_utility`
- `current_reachability`
- `conclusion_evidence`
- `evidence_level`
- `next_fallback`

Use `High` when the current first-party source or access policy was directly
verified, `Medium` when credible current secondary evidence supports the access
or provenance conclusion, and `Low` when only weak or historical evidence
supports it.
