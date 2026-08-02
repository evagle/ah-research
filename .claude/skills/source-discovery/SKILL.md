---
name: source-discovery
description: Use when research needs external reports, industry or macro data, company and investor-relations sources, official statistics, market evidence, source validation, or fallback searches after a source is missing, inaccessible, paywalled, or inconclusive.
---

# Source Discovery

Use this skill when a caller needs external evidence beyond already-bound filing,
event, counterpart, or market manifests. Inputs are the research question,
`AS_OF`, geography, industry, required fact types, and any caller-supplied
source constraints. This Skill returns structured source-discovery handoff
only; it never writes company analysis.

Read `references/source-catalog.md` before selecting the current layer.
The catalog supplies seed routes and audited access facts, not an allowlist or
runtime claim grades. Then read the detailed route guidance in
`references/search-playbook.md`.

For a direct site workflow, read the matching guide before retrieving:

- `references/site-guides/sse.md`
- `references/site-guides/cninfo.md`
- `references/site-guides/hkex-listing-applicants.md`
- `references/site-guides/hkexnews.md`
- `references/site-guides/hong-kong-regulatory.md`
- `references/site-guides/official-statistics.md`

## Contracts And Helpers

Use the version `1.0` schemas in `references/` without restating their fields:

- `research-request.schema.json` defines each requested `claim_id`.
- `candidate-claim.schema.json` carries one retrieved, attributable candidate.
- `planner-inventory-receipt.schema.json` binds a strict normalized
  `planner_inputs` snapshot and complete route inventory. The snapshot records
  request scope/content identity, source function, maintained profile
  identity/content hashes, maintained relation source bindings, bound routes,
  AS_OF/effective planning time, vocabulary/reachability identities, and the
  route inventory digest.
- `research-ledger.schema.json` records attempts and terminal state.
- `route-cache.schema.json` stores reviewed successful-route recipes only.

Use only the implemented helper boundaries:

- `research_contracts.validate_payload` validates each schema; `load_schema`
  loads it.
- `evidence_gate.evaluate_candidate` and `evaluate_stitched_series` return the
  acceptance decision and ordered failures.
- `discovery_planner.plan_next_layer` returns only the earliest unresolved
  layer plus its single `inventory_receipt`; persist that receipt with the
  ledger instead of constructing a second route list.
  `generate_query_variants` preserves the request scope.
- `source_lineage.lineage_id` and `same_lineage` identify underlying evidence,
  not merely a republisher.
- `route_cache.load_route_cache`, `rank_with_route_cache`, and
  `record_success` manage reviewed route recipes.

These helpers do not fetch documents or execute a discovery loop. The caller
retrieves the selected route, records its result, and constructs the terminal
ledger. Cache only reorders fitting routes; it cannot add routes, advance a
layer, or change authority, claim support, or acceptance requirements.
Receipt validation recomputes the planner-input fingerprint and inventory
digest from the persisted snapshot. This is a deterministic tamper-evident
binding, not protection from malicious code inside the same process; it uses
no secret and creates no separate execution state.

## Workflow

Follow this sequence exactly:

`decompose request -> validate request -> execute current layer -> validate candidate(s) -> stop accepted claims -> escalate unresolved claims -> terminal ledger handoff`

1. Decompose multi-period or multi-metric work into explicit `claim_id` values
   and construct a `research-request`; validate it before routing.
2. Read the source catalog before selecting the current layer. Use
   `plan_next_layer` with completed attempts and any terminal ledger; execute
   only the returned current layer. Use the playbook for that layer's routes.
3. Validate every retrieved `candidate-claim`, derive its lineage, and call the
   acceptance gate after the layer. Preserve the gate's
   `acceptance_failures` in the claim ledger.
4. Stop accepted positive claims. Re-plan only the unresolved claims, then
   repeat from their current layer. Write terminal ledgers before handoff.

Only unresolved `claim_id` values escalate.
Positive claims stop immediately after the acceptance gate passes.
Absence claims stop only after every applicable route is terminal.
Route count is not an acceptance criterion.
For an absence claim, `technical-failure`, `access-unavailable`, and
`request-budget-exhausted` are `blocked`, never factual absence.

Return exactly these seven top-level fields: `requests`, `accepted_candidates`, `unresolved_claims`, `ledger_path`, `ledger_sha256`, `status`, and `industry_bundle`.
For a non-industry request, set `industry_bundle` to `null`; do not remove the
field or change the other six handoff fields.
An empty result without a terminal ledger is invalid output. `unresolved_claims`
contains only terminal `blocked`, `conflict`, or `exhausted` claims; do not turn
an incomplete route into a conclusion.

For industry and competitor claims, expand beyond the target issuer to current
and former peers, parents, subsidiaries, customers, suppliers, and each
relevant listing applicant. Treat a listing applicant document as attributable
evidence with its draft/final status, commissioning relationship, scope, and
lineage preserved.

For HKEX listing applicants, the active or inactive index is discovery metadata
and an opened official PDF supports document contents. A historical PDF is not
current application proof: revalidate the relevant index and match application
ID, title, type, version, and document path. For TOP TOY application `108384`,
the known 2020-2025 chart PDF is historical evidence, not current proof.

## Market-Share Time Series

Market-share requests target the latest five completed annual periods and
extend to ten completed annual periods when public evidence permits. Search the
current partial period (H1, YTD, or latest quarter) separately when the AS_OF
date and publication cycle make it available. Label partial periods explicitly;
never annualize them or compare them directly with full years.

Require annual share, rank, market denominator, measurement basis, geography,
and source lineage for the subject company and its major named competitors.
Historical observations outside the latest five completed periods cannot
satisfy recent-series acceptance. They remain useful background only.

Search active, revised, inactive, and archived listing-applicant documents for
the subject, peers, and adjacent competitors. Then search final prospectuses,
issuer and competitor filings, original research publishers, named broker
reports, and report citation trails. A newer peer or listing applicant may
contain a fresher industry table than the target issuer.

Treat broker research as a required document route when filings and
listing-applicant documents leave annual market-share gaps. Search both company
reports and industry reports for the subject company, every named competitor,
and the category. Preserve the broker, analyst, report title, publication date,
page, table title, geography, period, measurement basis, named competitors,
original data provider, report URL, and PDF delivery URL. If a broker table
cites Frost & Sullivan, CIC, Euromonitor, IDC, or another data provider,
continue tracing Frost & Sullivan, CIC, Euromonitor, IDC, or another cited data
provider to its original table or a later official reproduction. A
portal-hosted PDF may preserve report contents, but Eastmoney, Hibor, Datayes,
Sina, and other distributors do not become the report author. Attribute the
claim to the named broker and retain the distributor as access lineage.

Do not divide issuer accounting revenue by industry GMV, RSV, retail value,
shipments, users, or another non-identical denominator. Calculate a share only
when numerator and denominator have the same period, geography, product scope,
measurement basis, and value status.

If any required annual period remains missing, keep the continuous-series
claim unresolved and continue through applicable route layers. Still report the
strongest partial series separately with missing years, scope breaks, and
evidence levels. A wider or narrower market may be reported as a separate
cross-section, but it cannot fill a gap in the requested series.

## Industry Size, Growth, Concentration, And Forecasts

For industry trend research, collect the latest five completed annual periods
and extend to ten when public evidence permits. Separately collect the next three to five forecast years. Preserve annual market size, year-over-year growth, CAGR, CR5 or CR10, product-category shares, geography, measurement
basis, and source lineage.

Forecast evidence must retain the forecast vintage, publication date, forecast
period, methodology, original data provider, commissioning relationship, and
whether later evidence revised or replaced it. Do not discard an industry
forecast merely because it is a forecast. Label it as a forecast and keep it
separate from completed-period observations and issuer financial forecasts.

Search industry reports, consulting and accounting-firm outlooks, association
reports, listing-applicant industry sections, broker industry reports, and the
original data-provider trail. When two publications reproduce the same
underlying provider series, treat them as one lineage rather than independent
confirmation.

When a later vintage changes an estimate or forecast, preserve both vintages.
Calculate the revision explicitly only when geography, product scope and
measurement basis remain comparable; otherwise report the nominal difference
and the scope break. Prefer the latest completed-period estimate for historical
analysis, but keep older forecasts for forecast-error and expectation tracking.
Never splice forecasts from different vintages into one continuous series.

### Industry Bundle Gate

Contract evolution is additive. Unambiguous `schema_version: 1.0` payloads
remain valid. New industry requests, candidates, and bundles use
`schema_version: 1.1`.

For v1.1, `market_definition_fingerprint` is metric-independent and identifies
geography, industry, population, product scope, and `channel_scope`.
`series_fingerprint` retains metric, canonical unit, measurement basis,
frequency, period semantics, and denominator within that market definition.
`channel_scope` and `denominator` are required machine-visible fields on the
request and candidate; accepted bundle series repeat them so cross-role
compatibility can be checked without interpreting prose. A provider table also
records normalized `provider_table_id`, methodology owner, and data vintage so
different report titles do not create false lineage independence.

Construct all eight role requests before routing. Use these mandatory roles:

- `market-definition`
- `historical-market-size`
- `industry-forecast`
- `market-concentration`
- `subject-market-share`
- `competitor-market-share`
- `current-partial-period`
- `industry-drivers`

For annual roles, derive the latest completed five-year window from `AS_OF`;
extend it only when public evidence permits. The market-definition role
establishes the primary market scope fingerprint before comparable series are
accepted.
Broader, narrower, or adjacent markets cannot fill the primary-market requirement.
Keep those observations as explicit scope breaks instead.

Search each unresolved role independently.
Only unresolved roles continue through the planner.
`claim_states` are independently terminal within each role. Never redispatch an
accepted claim, including an accepted base or version-chase child. `partial` and
`blocked` roles retain accepted evidence: preserve partial accepted evidence,
accepted periods, series metadata, and lineage while separately recording
missing periods or `missing_coverage`. Keep each role's claim IDs, per-claim
states, accepted and
missing coverage, market-definition and series fingerprints, lineage, and
terminal ledger paths.

After finding any forecast, run a mandatory version chase for the discovered
table and provider. Search its publication vintage, prior version, and later
version; preserve revisions and scope breaks rather than choosing one vintage
silently. Create `<base-forecast-claim-id>:prior-vintage` and
`<base-forecast-claim-id>:later-vintage` as distinct child claim IDs under the
`industry-forecast` role. The accepted base forecast claim remains stopped.
Only unresolved version child claim IDs continue through planner layers.
Each accepted child stops independently under the ordinary positive-claim
rule; version chase never reopens or redispatches the accepted base claim.
The publication date and `data_vintage` are evidence dates, not the forecast
horizon: both must be on or before `AS_OF`, while forecast values may extend
through the requested future periods. Never stitch candidates with different
data vintages. Render one forecast series per `data_vintage`, even when the
series fingerprint and forecast periods overlap.

After every role is terminal for the current run, call
`evaluate_industry_bundle` with the subject, `AS_OF`, primary market scope
fingerprint, all eight role outcomes, and scope breaks.
Return `requests`, `accepted_candidates`, `unresolved_claims`, `ledger_path`, `ledger_sha256`, `status`, and `industry_bundle`. The bundle status is
`complete`, `publishable-with-gaps`, or `blocked`; never infer a different
status from narrative prose.
Never convert `exhausted` or `blocked` into absence.

Accepted industry values remain in validated `accepted_candidates`; the
`industry_bundle` aggregates role state, required and missing periods, scope
breaks, lineage, and ledger paths. Exclude broker target prices, broker ratings,
and issuer earnings forecasts from industry candidate acceptance. A broker
industry table can qualify when its underlying market evidence passes the
normal gate, but its valuation opinion and issuer profit model cannot.

At the start, translate the request into claim types, time bounds, geography,
industry vocabulary, acceptable evidence types, and any source restrictions.
Use those constraints to select only the earliest applicable planner layer.

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

`source_authority` is the publisher's authority for this source type;
`conclusion_evidence` is support for this specific claim after inspection; and
`lineage_id` identifies the underlying report or dataset for independence and
republication checks. None substitutes for another.

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
Each local probe observation is machine-readable and `unreviewed`. For that
exact function, use a function-specific cache observation before its legacy
source-level summary. An `unreviewed` local cache observation never
auto-promotes or overwrites the reviewed snapshot. Only an explicit reviewer
update to `references/reachability-snapshot.json` may mark an observation
`reviewed`.

Use `source_profiles.ttl_for_status` when deciding whether a cache observation
is valid; do not create a separate TTL policy:

- `reachable` and `reachable-limited`: 30 days
- `login-required`, `paywalled`, and `anti-bot`: 14 days
- `temporarily-unreachable` and `unverified`: 24 hours
- `moved` and `broken-link`: 7 days

For each same-function candidate set, call
`source_profiles.select_routes(profiles, function_id, now, cache=local_cache, snapshot=reviewed_snapshot, geographies=claim_geographies, industry=claim_industry, industries=claim_industries, minimum_originality=minimum_originality, minimum_independence=minimum_independence)`
when the claim has a scope or provenance requirement. Function match remains
first, then claim-scope eligibility, then authority, originality,
independence, reachability, and utility. With geographic scope, routes are
eligible only when their profile lists a requested geography or `Global`.
With industry scope, routes are eligible only when their profile lists a
requested industry or `cross-industry`. Labels are trimmed and compared
case-insensitively; wrong-market and wrong-industry routes are excluded before
ranking. Pass a list or tuple of nonblank labels; omit `geographies`,
`industry`, and `industries` only when the claim has no such constraint.

For an independent-market research request, set both
`minimum_originality` and `minimum_independence` to the lowest acceptable
rating. This prevents an issuer, portal, aggregator, or other low-independence
route from winning merely because it is reachable. A source's original
publication remains attributable evidence, but it is not an independent check
when its publisher has a material interest in the subject.

The resolver ignores a stale cache observation before it consults the reviewed
snapshot, then falls back to the profile access record. A fresh `temporarily-unreachable` route is skipped for same-function fallbacks without changing its authority. Treat fresh `broken-link` and `unverified` routes the same way.
A stale route must be rechecked before treating its status as current.
One failed request never proves permanent closure.

Use noninteractive `urllib` or `curl` for default retrieval and probing.
Use headless Chromium only for JS/session flows, such as a rendered JSF form,
when noninteractive retrieval cannot complete the applicable official workflow.
Never use repeated user Allow prompts.

For A-share issuer disclosures, use this default document-body retrieval order:

`CNINFO opened PDF -> SSE register metadata cross-check -> Playwright headless SSE PDF fallback`

CNINFO is the default retrieval route for A-share issuer-announcement bodies
and issuer response bodies because its static PDFs are usually available
without a rendered browser session. Cross-check the listing exchange's register
metadata when available. Use Playwright headless SSE PDF fallback only when the
CNINFO document is missing, its identity fields do not match, or the exact
SSE-hosted artifact is required. This practical retrieval order does not
change source authority.

SSE-issued inquiry letters and other exchange actions remain SSE-first. Use
CNINFO as the default retrieval route for the issuer response body so the
research can preserve management explanation, commitments, and remediation.
CNINFO issuer responses do not replace an SSE inquiry letter; retain and cite
the exchange letter and issuer response as separate evidence.

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

Only declared `fallbacks` are executable route transitions. Adjacent
alternatives are guidance only: they may help with a changed or related claim,
but they cannot stand in for an unavailable same-function route. Record the
scope change and source boundary before using any adjacent evidence.

If a source returns no result, is paywalled, requires unavailable access, or
fails technically, record its terminal result and continue through the remaining
applicable routes in the current layer. Escalate to another category only when
the planner returns it for an unresolved claim.

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
