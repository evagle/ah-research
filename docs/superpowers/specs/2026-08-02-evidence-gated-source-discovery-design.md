# Evidence-Gated Source Discovery Design

## Status

Approved direction: use structured evidence acceptance as the core workflow and
add selective automation for relationship expansion, document discovery, source
lineage, and successful-route reuse. Do not build a continuous general-purpose
web crawler.

## Problem

The current source catalog and reachability routing cover many publishers, but
the research workflow can still stop too early. It primarily routes by known
publisher function, such as `company-disclosures` or `research-reports`. It does
not consistently expand:

- from the target company to peers, suppliers, customers, and listing applicants;
- from familiar filings to IPO applications, industry-overview chapters,
  association reports, archived versions, and cited originals;
- from a single observation to a continuous, same-definition time series;
- from a secondary publication to its underlying data producer.

As a result, a caller may report "not found", use stale forecasts, join
incompatible definitions, or mistake multiple citations of the same underlying
estimate for independent confirmation.

## Goals

1. Stop immediately when evidence satisfies the caller's explicit requirements.
2. Escalate automatically only for claims that have not met those requirements.
3. Prevent any Skill from reporting "no data", "not disclosed", or an equivalent
   source gap before all applicable routes are exhausted.
4. Prefer current, original, authoritative, reproducible evidence.
5. Preserve exact scope, units, period, value status, and source lineage.
6. Make successful discovery paths reusable without turning the system into a
   broad crawler.
7. Give all research Skills one shared request, ledger, and handoff contract.

## Non-Goals

- Continuously crawling or indexing the public web.
- Treating a large number of weak sources as stronger than one fitting original.
- Replacing annual, event, counterpart, or market manifests owned by existing
  filing and market-data workflows.
- Automatically converting every newly discovered site into a reviewed catalog
  source.
- Hiding genuine evidence gaps or lowering standards to complete a profile.

## Core Invariants

### Evidence sufficiency controls stopping

Search stops as soon as one candidate, or a compatible set of candidates,
passes the claim's acceptance gate. Route count is not a completion metric.

### Only unresolved claims escalate

Escalation operates per `claim_id`. Accepted claims are not searched again
unless a stronger-source conflict, revised document, or newer data vintage is
detected.

### Absence claims require exhaustion

Positive facts can stop on sufficient evidence. Negative or absence claims,
such as "no penalty", "no disclosure", or "no data exists", require all
applicable routes to reach a terminal state. A failed request or empty search
result never proves absence.

### Authority and claim support remain separate

An exchange filing is highly authoritative evidence that the filing contains a
number. A consultant estimate embedded in that filing is not automatically a
high-authority estimate of the objective market size. The runtime must preserve
both `source_authority` and `conclusion_evidence`.

### Citation count does not imply independence

Sources that cite the same underlying report, dataset, consultant, or table form
one lineage family. They cannot satisfy an independent-cross-check requirement
by citing each other.

## Research Contracts

### Research request

Add a machine-readable request schema with:

- `claim_id`
- `claim_type`
- `subject`
- `metric`
- `geographies`
- `industries`
- `period_start` and `period_end`
- `frequency`
- `continuity_required`
- `required_latest_period`
- `accepted_units`
- `definition_constraints`
- `value_status_allowed`: observed, historical-estimate, forecast
- `minimum_source_authority`
- `minimum_conclusion_evidence`
- `minimum_originality`
- `minimum_independence`
- `independent_cross_check_required`
- `absence_claim`
- `as_of`

Callers define what "enough" means. `source-discovery` must not silently weaken
the request.

### Candidate claim

Every extracted candidate records:

- values, periods, frequency, and units;
- geography, population, product scope, and measurement basis;
- publication date and data vintage;
- observed, historical-estimate, or forecast status for each value;
- original publisher and immediate publisher;
- document identity, canonical URL, and artifact hash when available;
- methodology and conflict-of-interest notes;
- a deterministic scope fingerprint;
- source-lineage identifiers;
- runtime evidence ratings.

### Research ledger

Persist one ledger per research run. Each attempt retains the existing source
ledger fields and adds:

- `claim_id`
- `route_layer`
- `subject_relation`
- `document_type`
- `query_variant`
- `started_at` and `completed_at`
- `artifact_identity`
- `lineage_id`
- `terminal_reason`
- `acceptance_failures`

Terminal claim statuses are:

- `accepted`
- `exhausted`
- `conflict`
- `blocked`

`blocked` is reserved for unavailable credentials, private data, or a technical
failure that remains after applicable alternatives. It is not a synonym for an
empty result.

## Acceptance Gate

The gate evaluates candidates in this order:

1. **Identity:** the source and document are authentic and reproducible.
2. **Scope:** geography, industry, product definition, population, and metric
   match the request.
3. **Time:** required years or periods are present and continuous.
4. **Value status:** historical values and forecasts are clearly separated.
5. **Freshness:** the data vintage reaches the required latest period.
6. **Authority:** source authority meets the claim requirement.
7. **Support:** conclusion evidence meets the claim requirement.
8. **Lineage:** any required independent check comes from another lineage.
9. **Conflict:** no unresolved stronger-source contradiction remains.

The gate returns explicit pass/fail reasons. It does not return a single opaque
score.

For time series, a validator must reject:

- missing intermediate periods when continuity is required;
- mixed units without a reproducible conversion;
- mixed market definitions without an explicit bridge;
- forecasts presented as historical estimates or observations;
- a newer publication that merely repeats an older forecast when a later data
  vintage is required.

Stitched series are allowed only when overlap periods match, definitions are
compatible, lineage is disclosed, and the output labels the result as stitched.

## Escalation Layers

Run layers sequentially and stop after each layer if the claim passes.
Independent routes within one layer may run in parallel.

### Layer 0: Bound and local evidence

Use existing annual, event, counterpart, market, and research manifests, plus
already validated local artifacts.

### Layer 1: Known highest-authority originals

Use the source catalog and current reachability data to query official
statistics, regulators, exchanges, issuer filings, and original publisher
libraries.

### Layer 2: Declared same-function fallbacks

Traverse only compatible, declared fallbacks. Preserve the source boundary and
do not substitute adjacent evidence for the requested function.

### Layer 3: Subject relationship expansion

Expand from the target to relevant:

- direct competitors and category leaders;
- current and recent listing applicants;
- parent companies, material subsidiaries, and brands;
- customers, suppliers, distributors, and licensors;
- associations and regulators that own the relevant record.

Each expansion records its relationship to the target and why it may contain
the requested evidence.

### Layer 4: Document-type expansion

Search applicable:

- prospectuses and final listing documents;
- active and inactive listing applications;
- industry-overview and business chapters;
- annual, interim, ESG, and investor materials;
- association reports and official white papers;
- cited datasets and methodology appendices;
- superseded versions and web archives.

### Layer 5: Broad dynamic discovery

Generate multilingual and synonym-aware queries, use reputable search indexes
for discovery, and trace every usable result back to the original publisher.
Search result pages and aggregators remain discovery aids.

Only absence claims must complete every applicable layer. Other claims stop as
soon as accepted.

## Selective Automation

### Relationship and document expansion

Add deterministic templates rather than a general crawler. For example, an
industry-market-series request for a listed consumer company automatically
includes recent peer and listing-applicant industry chapters.

### Query generation

Generate variants from:

- company names, former names, brands, and tickers;
- Chinese and English industry terminology;
- metric synonyms such as market size, GMV, RSV, retail value, and sales value;
- requested periods and document types;
- known report titles, table titles, and document identifiers.

Query variants must preserve the requested scope; synonym expansion must not
silently broaden the market definition.

### Source lineage

Extract "source", "commissioned by", methodology, bibliography, and table-note
references. Assign a shared lineage when publications depend on the same
underlying dataset or report.

### Successful-route cache

Cache reviewed route recipes by claim type, geography, industry, relationship,
document type, and source function. Cache:

- successful query patterns;
- canonical index endpoints;
- document identity rules;
- extraction hints and relevant chapter names;
- access observations under the existing TTL policy.

The cache changes route order and speed only. It cannot change authority,
claim support, or acceptance requirements.

## Skill Responsibilities

### `source-discovery`

- Own request decomposition, route planning, escalation, lineage, acceptance,
  and the final research ledger.
- Add HKEX active/inactive listing-applicant documents as an explicit source
  function.
- Return structured accepted candidates and unresolved claims.
- Never write the final company analysis.

### `read-filing`

- Continue to own canonical filing, event, and counterpart manifests.
- Emit structured research requests when a required fact lies outside bound
  filings.
- Distinguish "not present in selected filing" from "not publicly available".

### `product-analysis`

- Define acceptance requirements for product benchmarks, customer behavior,
  category size, market share, and competitor comparisons.
- Consume accepted candidates and retain their scope and lineage labels.
- Replace its fixed global two-retry limit with per-route retries plus the
  shared escalation contract.

### `management-analysis`

- Use discovery for external commitments, governance events, counterpart
  evidence, and applicable regulatory context after bound evidence is
  insufficient.
- Do not use weak web sources to fill private culture or intent claims.
- Return pending only after the shared ledger is terminal for the unresolved
  claim.

### `financial-redflag-scan`

- Use discovery for official regulatory thresholds, peer definitions, external
  enforcement records, and industry-specific benchmarks.
- Never let external research replace audited statement values.
- Require exhaustive routing before a negative enforcement conclusion.

### `value-profile`

- Own the run-level research ledger and acceptance requirements for each
  section.
- Dispatch only unresolved claims to `source-discovery`.
- Prevent child Skills from directly converting an empty result into
  `需人工`, `没有`, or `查不到`.
- Persist accepted candidate identities so resumed runs do not repeat research.

## Performance Controls

- Stop immediately on acceptance.
- Parallelize independent routes only within the current escalation layer.
- Deduplicate queries by normalized subject, metric, period, and scope.
- Reuse valid artifact hashes and route-cache entries.
- Retry a technical route at most twice before moving to the next independent
  route.
- Apply per-claim time and request budgets, but never convert budget exhaustion
  into a factual absence claim.
- Report budget-limited claims as `blocked` with unattempted routes preserved.

## Testing Strategy

Skill changes follow baseline-first forward testing.

### Required regression scenarios

1. **Sufficient official source:** an official statistic directly satisfies the
   request; the workflow stops at Layer 1.
2. **Pop Mart industry series:** target-company sources are stale; relationship
   and document expansion finds TOP TOY's current HKEX application and accepts
   the 2020-2025 series.
3. **Stale forecast:** a newly published report repeats an older forecast; the
   freshness gate rejects it and continues.
4. **Mixed scope:** a broader IP-toy series cannot fill gaps in a narrower
   pop-toy series.
5. **False independence:** a KPMG report citing Frost & Sullivan does not count
   as independent from the underlying Frost & Sullivan estimate.
6. **Stitched history:** overlapping official documents match and produce a
   labeled stitched series; a mismatched overlap is rejected.
7. **Negative claim:** "no enforcement action" requires all applicable official
   routes to finish.
8. **Technical failure:** anti-bot or a broken link moves to a valid fallback
   without lowering source authority.
9. **Resume:** accepted claims and completed route attempts are reused without
   duplicate network work.
10. **Uncataloged source:** a newly discovered original is usable after runtime
    provenance validation without first editing the catalog.

### Contract tests

- Every child Skill emits the shared research-request schema.
- Every terminal source gap has a complete research ledger.
- No final profile may contain an unqualified absence statement derived from an
  empty or failed route.
- Every accepted time series passes the continuity and scope validators.
- Independent-cross-check counts use distinct lineage IDs.

## Delivery Sequence

1. Add failing contract and scenario tests.
2. Add request, candidate, ledger, and lineage schemas.
3. Implement deterministic acceptance and time-series validators.
4. Extend source profiles and route planning for listing applicants and
   relationship/document expansion.
5. Add structured handoff to `source-discovery`.
6. Migrate `product-analysis`, `management-analysis`,
   `financial-redflag-scan`, and `value-profile` one at a time, testing each
   before proceeding.
7. Add successful-route caching after correctness tests pass.
8. Forward-test the complete workflow on unrelated companies and industries.

## Success Criteria

- A claim with sufficient high-quality evidence does not trigger unnecessary
  broad discovery.
- A claim that fails time, scope, freshness, authority, or independence checks
  automatically escalates.
- No Skill reports a source gap without a terminal ledger.
- Current peer or listing-applicant evidence is discoverable for industry
  claims.
- Time-series outputs preserve continuity, units, definitions, and value status.
- Repeated runs reuse validated routes and accepted artifacts.
- Existing manifest ownership and evidence-binding guarantees remain intact.
