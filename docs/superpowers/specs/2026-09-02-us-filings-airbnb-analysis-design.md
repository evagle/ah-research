# US Filings and Airbnb Latest-Report Analysis Design

## 1. Goal

Extend the `ah-research` financial-research workflow with a narrowly scoped
US-equity path that can independently analyze Airbnb's latest financial report.
The first release supports:

- canonical research ticker `ABNB.US`;
- SEC issuer identity through CIK;
- Forms 10-K, 10-Q, 10-K/A, and 10-Q/A;
- the latest filing available on or before `AS_OF`;
- the latest 10-K as the audited baseline for a latest-quarter analysis;
- the prior four comparable quarters;
- same-earnings-cycle SEC-filed 8-K exhibits;
- an evidence-graded Chinese report that connects business and strategy changes
  to operating data, financial value creation, and possible market re-rating.

The acceptance case is Airbnb as of `2026-09-02`. The SEC submissions response
observed during design identifies a Form 10-Q filed on `2026-08-06` for the
period ended `2026-06-30` as the latest qualifying report. This is a runtime
fact and must be revalidated rather than hard-coded.

## 2. Scope

### 2.1 Included

The first release delivers an end-to-end latest-report research path:

1. resolve `ABNB.US` to an SEC CIK;
2. enumerate the complete applicable SEC filing catalog;
3. select and persist the latest effective 10-K or 10-Q, including amendment
   relationships;
4. persist the audited annual baseline and comparable quarterly evidence;
5. persist applicable earnings-related 8-K exhibits from SEC Archives;
6. extract structured financial facts and stable narrative evidence;
7. run US-aware `read-filing` and financial-red-flag analysis;
8. produce an Airbnb-specific latest-report analysis.

### 2.2 Excluded

The first release does not add US trading, settlement, transaction costs,
market calendars, price repositories, backtests, portfolio construction, or
general US-market support. The existing `Exchange` and `Currency` domain types
remain scoped to A/H market operations.

The complete `value-profile` workflow may consume the new evidence later, but
the first release does not promise a complete US valuation profile or
automated buy/sell recommendation.

SEC enforcement history, proxy analysis, insider transactions, and a complete
US regulatory event manifest are separate follow-up projects. The first
release may use applicable SEC-filed risk disclosures and same-cycle 8-K
attachments, but must not claim that all US enforcement routes were exhausted.

## 3. Design Principles

1. **Independent derivation first.** The analysis starts from current SEC,
   Airbnb IR, and accepted external evidence. Prior analysis is not an input
   source for facts or conclusions.
2. **Prior work is a cross-check.** Brian's earlier Airbnb document is reviewed
   only after the independent draft exists. It may reveal omitted questions,
   changed assumptions, or conflicting hypotheses.
3. **No causal overclaim.** Company actions, KPI changes, and valuation changes
   are separate claims. A report may identify supported re-rating factors but
   must not turn correlation into proven causation.
4. **US quarterly reports are not annual reports.** A 10-Q is unaudited and
   cannot satisfy annual audit checks. The latest 10-K remains the audited
   baseline.
5. **Evidence limits are local.** A missing external metric limits the
   conclusion that depends on it; it does not invalidate unrelated SEC facts.
6. **Additive compatibility.** Existing A-share and HK workflows, manifests,
   ticker aliases, and citation behavior remain valid.

## 4. Architecture

### 4.1 Research Identity

The financial-research path accepts an additive research ticker namespace:

```text
<uppercase-symbol>.US
```

`ABNB.US` resolves through SEC `company_tickers.json`. The immutable issuer
identity contains:

- requested ticker;
- canonical research ticker;
- zero-padded ten-digit CIK;
- legal issuer name;
- SEC-reported ticker and exchange;
- official mapping URL, response path, and SHA-256.

The selected filing must contain the same CIK in its Inline XBRL identity.
Ticker-to-CIK, submissions, and filing-body identity disagreements fail closed.

This identity is intentionally separate from the market/backtest `Symbol`
model. No code may infer that `ABNB.US` is tradable by the existing platform.

### 4.2 SEC Adapter

A focused SEC adapter owns:

- request headers, descriptive User-Agent, throttling, retry, and backoff;
- ticker-to-CIK resolution;
- company submissions retrieval;
- historical submissions-file retrieval when the current response points to
  older catalog segments;
- Archives accession and document URL construction;
- filing-directory index retrieval;
- form classification and amendment relationships;
- immutable response and document persistence;
- live revalidation.

The existing `download_filings.py` remains the public CLI. It dispatches
`.US` tickers to the SEC adapter while preserving the current CNINFO and HKEX
paths.

### 4.3 Filing Selection

Applicable filing families are:

```text
10-K, 10-K/A, 10-Q, 10-Q/A
```

Each candidate retains:

- form;
- accession number;
- filing date and acceptance timestamp;
- report period;
- primary document;
- official filing URL and directory-index URL;
- amendment flag and amended family;
- selection status;
- local immutable artifact path and SHA-256 when selected.

Selection rules:

1. exclude evidence published after `AS_OF`;
2. group base forms and amendments by form family and report period;
3. prefer the latest accepted valid amendment within a group;
4. select the most recently filed qualifying report as `latest_report`;
5. select the most recent preceding 10-K as `audited_baseline`;
6. retain the prior four comparable quarters when available;
7. never replace an explicitly requested unavailable period with an older
   period silently.

If the amendment target cannot be established from SEC metadata and document
identity, the group remains unresolved.

### 4.4 Evidence Artifacts and Manifest

US filings use a content-addressed filing manifest rather than pretending that
a quarterly report is an annual report. The manifest binds:

- canonical ticker, CIK, issuer name, jurisdiction, and `AS_OF`;
- SEC mapping and submissions request contracts;
- response artifacts and SHA-256 values;
- the complete applicable candidate catalog;
- latest-report, audited-baseline, and comparison-set selections;
- filing directory indexes;
- selected HTML/Inline XBRL documents and SHA-256 values;
- same-cycle 8-K and selected earnings exhibits;
- live-revalidation requirements.

Existing A/H annual manifests remain valid. The shared evidence contract evolves
from "annual manifest only" to "jurisdiction-appropriate filing manifest",
while preserving all existing field meanings for A/H runs.

### 4.5 Structured Facts

Structured financial extraction uses two independent SEC representations:

1. Inline XBRL facts in the selected filing;
2. SEC company facts for cross-period normalization and cross-checking.

Every accepted fact retains:

- taxonomy and tag;
- issuer CIK;
- value and unit;
- start, end, or instant;
- fiscal year and fiscal period;
- form and accession;
- filed date;
- context identity;
- source artifact and SHA-256.

Quarter-only, year-to-date, trailing-period, and instant contexts must remain
distinct. The system must not subtract periods unless both context semantics
and units are compatible.

Company-specific operating KPIs that are absent from standard SEC facts are
extracted from the filing or SEC-filed earnings exhibit with an attributable
quote. They are not inferred from unlabeled tables.

### 4.6 Narrative Evidence and Citations

US filing evidence is HTML-first. A citation contains:

- jurisdiction `US`;
- accession number;
- form and report period;
- official document URL;
- immutable local artifact path and SHA-256;
- section or DOM anchor when available;
- exact quote;
- page number only when the filed document exposes a stable printed page.

The shared citation contract accepts a US filing citation with an anchor in
place of a page number. It must not fabricate PDF-style page numbers for SEC
HTML.

## 5. Analysis Workflow

### 5.1 Independent Research Order

The analysis proceeds in this order:

1. latest 10-Q or 10-K;
2. latest audited 10-K;
3. prior four comparable quarters;
4. same-cycle 8-K earnings exhibits;
5. current Airbnb IR materials accepted through source discovery;
6. accepted independent industry, peer, and market evidence;
7. prior user analysis as a final cross-validation artifact.

The prior document never fills a missing evidence row and never elevates an
evidence grade.

### 5.2 Airbnb-Specific KPI Tree

The report evaluates disclosed metrics in the following tree:

| Layer | Metrics and questions |
|---|---|
| Demand scale | Nights and Seats Booked, GBV, ADR, reported growth, currency-neutral growth, and two-year CAGR when comparable |
| Monetization | Revenue, implied take rate, and revenue growth relative to booking growth |
| Network and expansion | Supply, quality actions, priority countries, less-mature markets, and disclosed adoption of new offerings |
| Profit quality | GAAP operating income, net income, Adjusted EBITDA, operating cash flow, free cash flow, margins, and cash conversion |
| Reinvestment | Product and new-business spending, capital expenditure, stock-based compensation, and disclosed launch milestones |
| Capital allocation | Cash and investments, debt, repurchases, diluted share count, and dilution offset |
| Expectations | Results versus prior company guidance, with foreign exchange, tax, and one-time effects separated |

Each metric shows, when meaningful and available:

- current quarter;
- year-over-year comparison;
- year-to-date comparison;
- trailing twelve months;
- two-year CAGR;
- prior company guidance and actual result.

A missing disclosed metric is shown as missing. The report does not invent
listing counts, customer composition, repeat rates, local-user shares, market
shares, or new-business revenue.

### 5.3 Strategy-to-Value Chain

The main synthesis table has one row per material strategic action:

| Strategic action | Execution evidence | KPI change | Financial transmission | Long-term value implication | Market-recognition evidence | Evidence grade |
|---|---|---|---|---|---|---|

Airbnb hypotheses to test include, but are not limited to:

- core marketplace quality and price transparency;
- international expansion and penetration outside mature markets;
- supply enablement, including co-hosting or related host tools;
- Experiences and Services;
- application and AI investment;
- marketing efficiency and direct traffic;
- capital allocation and repurchases.

These are questions, not pre-accepted conclusions. The latest evidence decides
which rows remain material.

### 5.4 Explaining Market Recognition

The report starts from business and financial changes, not short-term price
movements. It evaluates whether the evidence supports:

- a longer sustainable growth runway;
- stronger network effects or customer choice;
- higher monetization without damaging marketplace health;
- durable margin or free-cash-flow expansion;
- better capital efficiency;
- reduced execution uncertainty around new businesses;
- disciplined capital allocation.

Direct market or peer-multiple evidence is a separate external claim. When a
re-rating can be measured with comparable market data, the report may show it
as corroboration. In the absence of direct attribution, wording is limited to
"supported possible re-rating factor" and conclusion evidence is capped at
Medium.

## 6. Use of the Prior Airbnb Analysis

Brian's prior document is a non-authoritative hypothesis inventory. It is
consumed only after the independent draft and used for:

1. **coverage comparison**: identify topics the independent analysis omitted;
2. **claim drift**: identify prior claims that current evidence confirms,
   weakens, contradicts, or leaves unresolved;
3. **metric refresh**: locate stale periods or changed definitions;
4. **thesis evolution**: compare the earlier three tensions with current
   evidence;
5. **cross-validation**: test whether independent reasoning converges without
   copying the original framing.

The cross-validation appendix classifies every material reused hypothesis as:

```text
confirmed | updated | contradicted | unresolved | out of scope
```

It cites current evidence, not the prior document, for the substantive result.

## 7. Evidence Levels

Every conclusion exposes one of:

- **High**: direct SEC filing, SEC metadata, or directly verified Airbnb
  first-party statement supporting the issuer's own action or result;
- **Medium**: a transparent calculation from High-grade inputs, or credible
  independent market evidence with preserved definitions and lineage;
- **Low**: indirect, incomplete, stale, or weakly attributable evidence;
- **Manual review**: material source conflict, identity mismatch, or missing
  evidence that prevents the specific conclusion.

Source authority, current reachability, and conclusion evidence remain separate
fields. A first-party strategy claim is High authority for what management
said, but not automatically High evidence that the strategy succeeded.

## 8. Failure Handling

- SEC 403/429 responses trigger bounded retry and backoff, then
  `dependency_failure`; they never become factual absence.
- Ticker/CIK, filing/CIK, report-period/context, and local/remote hash conflicts
  fail closed.
- An incomplete submissions catalog cannot support "latest filing".
- An unresolved amendment cannot silently replace a base filing.
- HTML and XBRL numeric conflicts move only dependent metrics to manual review.
- Missing 8-K or IR evidence limits strategy and guidance conclusions but does
  not invalidate independent SEC financial facts.
- Final publication replays the SEC mapping, submissions, directory index, and
  selected document requests. Drift requires evidence rebuild before analysis.

## 9. Testing

Implementation follows test-driven development.

### 9.1 Unit Tests

- `ABNB.US` normalization and invalid US ticker handling;
- ticker-to-CIK identity and mismatch rejection;
- `AS_OF` filtering;
- mixed 10-K/10-Q ordering;
- 10-K/A and 10-Q/A replacement behavior;
- historical submissions retrieval and duplicate rejection;
- accession and Archives URL construction;
- manifest completeness, content addressing, and immutability;
- XBRL instant, quarter, year-to-date, and unit handling;
- HTML anchor citation validation;
- US-specific unaudited-quarter rules.

### 9.2 Integration Tests

- recorded SEC ticker, submissions, index, filing, and company-facts fixtures;
- fully mocked `download_filings.py ABNB.US --latest`;
- manifest live-revalidation success and drift failure;
- optional `AH_RESEARCH_LIVE=1` SEC reachability test with the configured
  descriptive User-Agent.

### 9.3 Acceptance Test

With an `AS_OF=2026-09-02` recorded evidence set, the workflow must:

1. select the expected latest Airbnb filing from the fixture;
2. bind the latest audited 10-K and prior comparable quarters;
3. emit the Airbnb KPI tree;
4. emit at least one fully cited strategy-to-value row;
5. distinguish fact, calculation, interpretation, and market attribution;
6. identify missing evidence without inventing values;
7. produce the prior-analysis cross-validation only after the independent
   analysis.

## 10. Acceptance Criteria

- Existing SH/SZ/HK filing tests continue to pass.
- `ABNB.US` resolves to an authenticated SEC CIK.
- Latest 10-K/10-Q selection is deterministic and `AS_OF` correct.
- Amendments, immutable artifacts, and live revalidation satisfy the evidence
  contract.
- Quarterly and audited annual evidence are not conflated.
- The report contains detailed Airbnb operating and financial comparisons.
- Strategy conclusions trace to execution evidence and KPI changes.
- Market-recognition language does not overstate causality.
- The prior document is used only for final supplementation and
  cross-validation.
- Every material conclusion has an explicit evidence level.
