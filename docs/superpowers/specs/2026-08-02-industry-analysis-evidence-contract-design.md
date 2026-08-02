# Industry Analysis Evidence Contract

**Date:** 2026-08-02
**Status:** Approved design

## Objective

Make industry analysis reusable across stocks without allowing a polished
narrative to hide missing years, incompatible market definitions, stale
forecasts, or duplicated source lineage.

The design is hybrid:

- skill instructions control research judgment, source routing, and
  industry-specific interpretation;
- machine validation enforces only coverage, labeling, comparability,
  provenance, and unresolved-gap disclosure.

## Problem

The current skills state the desired evidence window, but they do not define a
complete industry request bundle or a bundle-level acceptance result. Existing
candidate gates can validate one series, yet cannot determine whether the
overall industry chapter includes all required dimensions.

This leaves four recurring failure modes:

1. one report is treated as sufficient even though recent annual periods are
   absent;
2. GMV, RSV, issuer revenue, shipment, user, or other bases are joined into one
   apparent trend;
3. a newer publication that repeats an older provider series is treated as an
   independent or current forecast;
4. missing concentration or competitor data disappears from the final profile
   instead of remaining an explicit research gap.

## Goals

- Create a standard request bundle for every company industry chapter.
- Target the latest five completed annual periods and extend to ten when public
  evidence permits.
- Search the current H1, YTD, or latest quarter separately when the industry's
  publication cycle supports it.
- Collect the next three to five annual forecast periods and preserve forecast
  vintages.
- Cover market size, annual growth, concentration, target-company share, and
  major-competitor share.
- Preserve market definition, measurement basis, period semantics, original
  provider, commissioning relationship, and lineage.
- Publish strong partial evidence while keeping missing or incompatible claims
  explicit.
- Reuse the existing research request, candidate claim, evidence gate, planner,
  and ledger contracts.

## Non-Goals

- Do not require a public CR5 or forecast to exist.
- Do not block the rest of a value profile solely because third-party industry
  evidence is unavailable.
- Do not infer values from charts when the chart cannot be transcribed
  reproducibly.
- Do not convert issuer accounting revenue into market share unless numerator
  and denominator have identical scope and measurement basis.
- Do not rank a forecast as correct merely because it is newer.
- Do not add stock-price targets, broker ratings, or issuer earnings forecasts
  to the industry evidence bundle.

## Standard Industry Request Bundle

The orchestrator creates separate `research-request` payloads for these roles:

| Role | Required scope | Acceptance target |
|---|---|---|
| `market-definition` | geography, population, product boundary, channel boundary, value basis | at least one attributable definition for every reported series |
| `historical-market-size` | latest five completed years | five consecutive annual observations with one scope fingerprint |
| `industry-forecast` | next three to five years | at least three annual forecast observations from one vintage and scope fingerprint |
| `market-concentration` | CR5 or CR10 and denominator | latest completed year plus prior comparable observations when available |
| `subject-market-share` | subject rank, share, numerator, denominator | latest five completed years, with partial series retained |
| `competitor-market-share` | major named competitors and complete ranking table | same period and basis as each accepted subject observation |
| `current-partial-period` | H1, YTD, or quarter | separately labeled when the publication cycle makes it applicable |
| `industry-drivers` | at least one demand and one supply indicator when applicable | attributable history or forecast with an explicit unit and definition |

The bundle generator derives completed and forecast periods from `AS_OF`.
Callers may narrow product or geography scope, but they may not silently relax
the period target. A relaxed request must retain the original claim as
unresolved and create a separately identified adjacent-scope claim.

## Bundle Gate

A lightweight bundle gate aggregates existing claim-level gate and ledger
results. It does not duplicate source retrieval or candidate evaluation.

Each role receives one of these states:

- `accepted`: the role meets its period, scope, provenance, and evidence floor;
- `partial`: useful accepted observations exist, but continuity or competitor
  coverage is incomplete;
- `exhausted`: all applicable routes are terminal and no acceptable evidence
  was found;
- `blocked`: access, technical, or request-budget failures prevented route
  exhaustion;
- `not-applicable`: permitted only for current partial-period or a genuinely
  inapplicable industry driver, with a recorded rationale.

The bundle itself receives:

- `complete` when every required role is `accepted` or validly
  `not-applicable`;
- `publishable-with-gaps` when at least one role is `partial` or `exhausted`;
- `blocked` when any required role is `blocked`.

`publishable-with-gaps` allows the value profile to continue. It requires the
profile to render the missing periods, exhausted routes, and scope breaks.
Neither `exhausted` nor `blocked` may be rewritten as factual absence.

## Comparability Rules

The existing definition scope fingerprint remains the primary compatibility
key. It covers at least:

- geography;
- population or market universe;
- product and channel scope;
- metric and canonical unit;
- measurement basis;
- period semantics.

Values with different fingerprints remain separate series. A documented
reconciliation may connect them only when it provides a reproducible conversion
and records both original fingerprints. Label changes such as GMV to RSV do not
qualify as a conversion by themselves.

Historical observations, historical estimates, and forecasts remain distinct.
The gate must reject:

- forecasts presented as observed values;
- current publication dates used as substitutes for old data vintages;
- series assembled from different forecast vintages;
- subject share and competitor share drawn from incompatible denominators;
- concentration changes calculated across incompatible bases.

## Forecast Version Handling

For each forecast, preserve:

- publication and data-vintage dates;
- forecast years and annual values;
- original data provider;
- publisher and access host;
- commissioning relationship;
- methodology or source note;
- lineage identifier;
- replacement or revision relationship.

Search for a later vintage after finding a forecast. Preserve both versions.
Calculate a revision only when scope fingerprints match. Otherwise show nominal
differences alongside the exact scope break.

Multiple publishers repeating the same provider table count as one lineage.
They can improve access confidence but not independence.

## Source Routing

Route each unresolved role through the existing planner:

1. official statistics, regulators, customs, and industry associations when
   authoritative for the metric;
2. issuer and competitor filings, prospectuses, and active, revised, inactive,
   or archived listing applications;
3. original research providers, consulting reports, and named broker reports;
4. report portals and finance media for discovery and delivery, followed back
   to the original publisher or underlying provider.

Search peers and adjacent listing applicants, not only the target issuer. A
new competitor filing may contain the newest market table.

After one annual table is found, search its title, provider, vintage, cited
report, prior version, and later version. This version chase is mandatory
before declaring the forecast role accepted.

## Profile Output Contract

The industry chapter renders these blocks in order:

1. **Market definition matrix**: reported market name, geography, product
   scope, channel scope, basis, unit, provider, and lineage.
2. **Historical market table**: latest five completed annual values, annual
   growth, CAGR, and missing-year markers.
3. **Forecast vintage table**: annual forecast values for each vintage,
   publication date, provider, basis, and comparable revision where valid.
4. **Concentration and competitor table**: CR5 or CR10, target share, major
   competitors, rank, denominator, and period.
5. **Current partial-period table**: separate from annual history.
6. **Scope breaks and unresolved gaps**: incompatible series, missing years,
   exhausted routes, blocked routes, and next evidence needed.

Broader, narrower, or adjacent markets may appear as separate reference rows.
They cannot fill the primary-market coverage requirement.

## Skill Changes

`source-discovery` will:

- define the request roles and version-chase workflow;
- require bundle-gate handoff fields;
- route unresolved roles independently;
- preserve partial accepted evidence and terminal ledgers.

`value-profile` will:

- require the fixed output blocks in sections 2.1 and 2.2;
- consume bundle status instead of inferring completion from prose;
- allow `publishable-with-gaps` while displaying every gap;
- prohibit valuation assumptions from silently filling industry evidence gaps.

The profile template will replace generic industry prompts with the fixed
tables and machine-reference placeholders.

## Testing

### Contract Tests

- Every generated request validates against `research-request.schema.json`.
- Every required role exists exactly once for the primary market.
- Period bounds derive correctly from `AS_OF`.
- Bundle states follow the role-state matrix.
- `publishable-with-gaps` retains partial values and unresolved claims.

### Comparability Tests

- GMV and RSV cannot be stitched.
- Issuer revenue cannot become industry share without a matching denominator.
- Different geography or product scope cannot fill a missing year.
- Forecast and observed values cannot be mislabeled.
- Same-provider republications are one lineage.
- Comparable forecast vintages produce a revision; incompatible vintages
  produce only a nominal-difference record.

### Cross-Industry Fixtures

- **Pop Mart**: five-year market history, old RSV forecast, new GMV forecast,
  same-provider lineage, category shares, and incomparable CR5 snapshots.
- **Kweichow Moutai**: total baijiu versus premium baijiu definitions, volume
  versus retail value, price bands, and competitor share coverage.
- **SMIC or equivalent foundry case**: industry revenue, wafer shipments,
  installed capacity, and foundry share as separate measurement bases.

Fixtures are offline and deterministic. Live tests cover reachability only and
must not determine semantic test results.

## Success Criteria

- A future profile cannot report a complete five-year industry trend while a
  required year is missing.
- A future profile cannot calculate growth, share change, concentration change,
  or forecast revision across incompatible scope fingerprints.
- A profile with unavailable public data can still finish as
  `publishable-with-gaps`, with the exact gap and route status visible.
- Forecasts remain available as decision inputs without being presented as
  observed facts.
- The same workflow works for consumer, regulated, technology, and industrial
  market definitions without embedding toy-specific logic.
