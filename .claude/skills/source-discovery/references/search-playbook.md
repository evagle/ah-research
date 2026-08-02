# Search Playbook

Use this playbook after a validated request has a current planner layer. It
describes routes for that layer; it does not authorize an always-broad search.
After each layer, validate candidates and use the acceptance gate before asking
the planner for another layer.

## Gate-Driven Layers

`plan_next_layer` returns only the earliest unresolved applicable layer:

1. Bound local evidence.
2. Highest-authority fitting sources.
3. Same-function fallbacks.
4. Subject relationships: direct peers, category leaders, and active or recent
   listing applicants.
5. Document types: prospectus, listing application, industry overview,
   methodology appendix, association report, and archive.
6. Broad dynamic discovery.

Execute only the returned layer. A passed positive candidate ends discovery for
its `claim_id`; do not seek corroboration merely to increase route count.
Escalate only a claim whose gate remains unresolved. For an absence claim, keep
planning until every applicable route is terminal; `technical-failure`,
`access-unavailable`, and `request-budget-exhausted` require a `blocked`
ledger, never an absence conclusion.

Use `rank_with_route_cache` only to reorder routes that already fit the same
current layer. The cache cannot introduce a route, skip an applicable earlier
layer, or change claim scope or acceptance requirements.

## Query Templates

Start with a publisher-bound query when the likely publisher is known:

- `site:{publisher_domain} "{exact report title}" "{geography}" "{industry vocabulary}" "{date range}" filetype:pdf`
- `site:{publisher_domain} "{issuer or regulator}" "{claim keywords}" "{AS_OF year or quarter}"`

When the publisher is not known, anchor on the claim and then trace inward:

- `"{claim keywords}" "{geography}" "{industry vocabulary}" "{date range}" report pdf`
- `"{claim keywords}" "{methodology keyword}" "{table or dataset name}" "{AS_OF year}"`

For original-document tracing, always try document IDs and official hosts:

- `"{document or announcement ID}" site:cninfo.com.cn`
- `"{document or announcement ID}" site:sse.com.cn OR site:szse.cn OR site:hkexnews.hk`
- `"{exact announcement title}" "{issuer}" "{announcement time}" "{status}"`

If a report or notice is cited by an app, portal, or index, use the portal only
to recover the original title, publisher, date, identifier, and canonical URL,
then continue on the official or original host.

## Route Rules

Every route below assumes:

- Prefer the highest-authority applicable original first.
- Keep `source_authority`, `practical_utility`, `current_reachability`, and
  `conclusion_evidence` as explicit `High`/`Medium`/`Low` fields on each
  access attempt and final ledger row.
- Use `source_authority` for the publisher's authority for the claim type,
  `practical_utility` for fitness to the requested geography/date/granularity,
  `current_reachability` for current permitted access and URL stability, and
  `conclusion_evidence` for how strongly the source supports the specific
  research conclusion.
- Keep `evidence_level` separate: it is the `High`/`Medium`/`Low` confidence
  in the row's access/provenance conclusion, not a substitute for source
  authority, practical utility, current reachability, or claim support.
- Use uncataloged sources when needed, but validate provenance, access, and
  fitness for the requested claim before relying on them.
- Carry forward `access_conclusion` and `evidence_level` on each attempt.
- Carry forward `source_authority`, `practical_utility`,
  `current_reachability`, and `conclusion_evidence` on each attempt.

Read the applicable site guide before a direct route: `site-guides/sse.md`,
`site-guides/cninfo.md`, `site-guides/hkexnews.md`,
`site-guides/hkex-listing-applicants.md`,
`site-guides/hong-kong-regulatory.md`, or
`site-guides/official-statistics.md`.

## company/filings

Primary portfolio: issuer IR, annual/interim filings, official exchange filing
indexes, company newsrooms, product pages, pricing pages, ESG pages.

Fallbacks: customer, supplier, competitor, and association websites; original
broker or consultant reports; credible media used only to locate the original.

Use this route for issuer facts, management quotations, disclosed business
scope, product mix, pricing disclosures, operational footprint, and filing
history.

Issuer/company sites are first-party only for the issuer's own statements,
disclosures, actions, products, policies, prices, filings, and quotations.
Customer, supplier, competitor, and association sites are first-party only for
that publisher's own claims, actions, membership lists, transactions, policies,
product facts, and attributable statements. Treat those ecosystem sites as
independent checks only when the publisher is genuinely independent of the
issuer and independent of the claim being checked.

## announcements/regulatory correspondence

For A-share issuer-announcement bodies, retrieve the opened CNINFO PDF first,
then cross-check listing-exchange metadata. Use an isolated Playwright headless
session for an SSE-hosted PDF only when CNINFO is missing, identity fields do
not match, or the exact SSE artifact is required. This retrieval preference
does not lower SSE authority for its own exchange actions.

Primary portfolio: CNINFO, SSE, SZSE, HKEXnews, and regulator originals.

Discovery aids: app indexes, exchange search apps, aggregator notice feeds, and
portal timelines.

Fallbacks: issuer IR reposts, media summaries used only to recover title,
issuer name, time, and identifier, then traced back to the original.

Use this route for inquiry/concern letters, issuer responses, supervisory
measures, disciplinary actions, penalty decisions, corrections/restatements,
trading suspensions, and material-event notices. Final citations must preserve
announcement time, document/announcement ID, status, URL, and replacement
relationship. Treat the exchange letter and issuer response as separate
documents: use SSE for its inquiry letter and CNINFO for the issuer response
body, including management explanation, commitments, and remediation.

## valuation/market

Primary portfolio: official exchange market data pages, issuer disclosures,
index provider pages, exchange statistics, and original research reports.

Fallbacks: finance portals for discovery, then the exchange, index provider, or
original analyst/report publisher.

Use this route for valuation ranges, market structure context, listing
comparables, and attributable market commentary.

For market-share time series, use the relationship layer before broad dynamic
discovery. Expand from the subject issuer to current and former peers, then to
active, revised, inactive, and archived listing-applicant industry-overview
documents. Search each required year and the current partial period
independently. Query both the metric and table identity:

- `"{industry}" "market share" "{year}" "{company or competitor}" filetype:pdf`
- `"{industry}" "top five companies" "{year}" GMV OR RSV OR "retail value"`
- `site:hkexnews.hk/app/sehk "{industry}" "{year}" "market share"`
- `site:hkexnews.hk/listedco/listconews "{competitor}" prospectus "market share"`

Record the whole ranking table when available, not only the subject company's
row. Keep full-year and H1/YTD/quarter tables separate, and preserve revisions
when a later commissioned report restates an earlier market estimate.

When annual company shares remain missing, broker research is a required
document route rather than an optional commentary source. Search company
reports and industry reports separately for the subject, each named competitor,
and the category; a peer report may reproduce a table omitted from the subject
report. Search the broker's own research site first, then Eastmoney, Hibor,
Datayes, Sina, or another report index and delivery host. Preserve authorship
and access lineage separately: the named broker and analysts authored the
report, while a portal may only index or deliver the PDF.

Extract the complete table and its footnotes. Record report title, broker,
analysts, publication date, page, table title, period, geography, product
scope, GMV/RSV/retail-value basis, named competitors, source note, original
data provider, canonical report URL, and any separate PDF delivery URL. If the
source note names Frost & Sullivan, CIC, Euromonitor, IDC, or another provider,
follow that citation into prospectuses, listing applications, provider
releases, or later official reproductions. Do not treat two broker reports as
independent confirmation when both reproduce the same underlying table.
Record the provider's stable `provider_table_id` when available. Normalize it
with the methodology owner and data vintage; a changed report title or
immediate publisher does not create a new lineage.

For every discovered forecast table, run a version chase even after the first
candidate passes. Bind searches to the exact table title, provider, and
publication vintage, then search the prior version and later version
independently:

- `"{exact table title}" "{provider}" "{publication year}" filetype:pdf`
- `"{provider}" "{industry}" forecast "{prior year}" filetype:pdf`
- `"{provider}" "{industry}" forecast "{later year}" filetype:pdf`

Create `<base-forecast-claim-id>:prior-vintage` and
`<base-forecast-claim-id>:later-vintage` as distinct child claim IDs under the
`industry-forecast` role. The accepted base forecast claim remains stopped.
Only unresolved version child claim IDs continue through planner layers.
Apply the ordinary positive-claim stop rule separately to each child.

Record each vintage's publication date, forecast window, methodology, scope,
lineage, and revision relationship. A missing prior or later version remains a
terminally ledgered search result; it does not erase an accepted forecast.
Treat publication date and `data_vintage` as evidence dates, separately from
the future forecast window. Do not require either evidence date to reach the
last horizon year. Never combine different data vintages into one series, and
render one series row set for each vintage.
Exclude broker target prices, broker ratings, and issuer earnings forecasts.
They are valuation or issuer-performance signals, not industry market
forecasts, even when they appear in the same broker report.

## macro/official statistics

Primary portfolio: national statistical agencies, ministries, central banks,
regulators, customs, industry bureaus, and multilateral organizations.

Fallbacks: university or policy-center reproductions that link back to the
original table or release.

Use this route for macro series, official counts, trade data, household or
demographic statistics, and policy-relevant baseline data.

## general reports

Primary portfolio: original publisher report libraries, SSRN or academic hosts,
association reports, and official white-paper repositories.

Fallbacks: citation trails inside other original reports; search results bound
to title, publisher, and date.

Use this route when the claim depends on cross-industry or broad market reports
with an identifiable methodology.

## consulting

Primary portfolio: original consulting publisher libraries, official press
rooms, PDF libraries, and client-referenced original report pages.

Fallbacks: conference agendas or association pages that link to the consulting
publisher original.

Use this route for attributable consulting estimates, market maps, and
methodology-backed industry commentary.

## technology/telecom

Primary portfolio: telecom regulators, spectrum authorities, operator IR,
network-equipment vendors, standards bodies, and original specialist research.

Fallbacks: customer deployments, association datasets, and original conference
materials.

Use this route for subscribers, traffic, network deployment, device ecosystem,
standards adoption, and operator or vendor claims that need independent checks.

## consumer/media

Primary portfolio: official audience measurement bodies, platform IR, ad-tech
original reports, association releases, and original market-research houses.

Fallbacks: app-store charts, publisher decks, and media stories used only to
trace the original data release.

Use this route for audience size, engagement, content distribution, ad market
context, and platform positioning.

## travel/aviation

Primary portfolio: civil aviation regulators, airport operators, airline IR,
tourism boards, hotel groups, GDS providers, and original travel research.

Fallbacks: association statistics and original route or capacity datasets.

Use this route for passenger throughput, route capacity, tourism flows, lodging
trends, and travel demand claims.

## investment/venture capital

Primary portfolio: fund IR, exchange disclosures, regulator filings, LP letters
when public, and original venture/private-market data publishers.

Fallbacks: portfolio company disclosures and original transaction notices.

Use this route for fundraising, deployment pace, sector activity, and
transaction chronology.

## trade/e-commerce

Primary portfolio: customs data, commerce ministries, marketplace IR, merchant
or logistics disclosures, payments data, and original trade associations.

Fallbacks: seller tools, cross-border service providers, and original
specialized research.

Use this route for GMV-adjacent claims, order-flow context, merchant density,
trade corridors, and marketplace ecosystem evidence.

## health/demographics

Primary portfolio: health ministries, CDC-like agencies, WHO, UN, census
agencies, and original epidemiology or demographic datasets.

Fallbacks: peer-reviewed papers that expose the source dataset and methods.

Use this route for population, aging, disease burden, treatment access, and
health-system capacity claims.

## HR/labor

Primary portfolio: labor ministries, social-security bureaus, census or labor
force surveys, payroll or recruiting platforms with methodology disclosures,
and original association surveys.

Fallbacks: academic labor datasets and official regional statistics.

Use this route for wage levels, hiring conditions, labor participation, talent
supply, and workforce mix.

## international comparisons

Primary portfolio: multilateral institutions, national statistical agencies,
harmonized regulator datasets, and original cross-country studies.

Fallbacks: country-specific originals when harmonized series disagree or hide
method differences.

Use this route when the claim compares countries, exchanges, sectors, or
regulatory regimes and needs comparable definitions.

## Dynamic Discovery Notes

Use this section only when broad dynamic discovery is the current planner
layer. Discover uncataloged candidates from original report citations, official
link directories, association member lists, bibliography trails, archive
snapshots, and issuer ecosystem pages. Validate provenance, methodology
transparency, correction history, coverage, timeliness, reproducibility, access
stability, conflicts of interest, and fitness for the requested claim before
using the source.

Do not stop an absence claim on the first unavailable source. Follow the
remaining applicable routes until the terminal ledger records the final error
and next fallback decision. Positive claims still stop as soon as their
acceptance gate passes.

## Uncataloged Hong Kong Official Sources

For a Hong Kong policy, regulatory, or statistics claim, treat the catalog as a
starting point and discover an uncataloged official source when the catalog
does not contain the producing agency. Search official government or official statistics publisher directories, cited source tables, and official link directories before considering a finance portal.

Order same-function candidates trust-first: use the highest-authority
applicable original, then a same-function official peer, then adjacent evidence.
When multiple uncataloged official candidates remain tied, prefer the producer
that directly owns the requested record, then the source with the exact
geography, period, definition, and result identity; record the tie-break in
the ledger. A reachable finance portal is a discovery aid, not a substantive citation, unless it meets the verified-mirror exception.

For a portal, app, or index result, capture the original title, publisher, date,
identifier, and canonical URL, then retrieve and cite the official original.
Validate the selected uncataloged source for provenance, access, and fitness
before relying on it. Record its official domain, publisher identity,
direct-result fields, access observation, same-function peers, and evidence
level alongside the standard ledger fields.
