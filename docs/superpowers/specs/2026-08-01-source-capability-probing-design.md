# Source Capability Discovery and Reachability Design

## Goal

Extend `source-discovery` from a static source registry into a maintained
capability directory. For each website, record what information and workflows
it actually provides, the most useful direct links, how to search it, what can
be cited, and which same-function source to try next. Keep reachability current
without making ordinary unit tests depend on live websites.

## Principles

- Match the required function before ranking candidates.
- For equivalent functions, prefer higher-authority, more original, and more
  independent sources before considering reachability and convenience.
- A lower-authority aggregator may discover an original, but cannot replace an
  available official or original source.
- A temporary access failure changes current reachability, not source
  authority.
- Keep every access and provenance conclusion at an explicit `High`, `Medium`,
  or `Low` evidence level.
- Treat the catalog as a seed registry, not a closed allowlist.

## Architecture

Add the following resources under `.claude/skills/source-discovery/`:

- `references/sources/*.yaml`: one structured capability profile per source.
  Source families may use a parent profile and distinct child profiles.
- `references/source-catalog.md`: generated agent-readable overview of source
  routing, access conditions, and fallback choices.
- `references/site-guides/*.md`: detailed guides for complex, high-value
  sources such as SSE, CNINFO, HKEXnews, and official statistics portals.
- `scripts/probe_source_reachability.py`: explicit live probe for transport and
  semantic reachability checks.
- `scripts/build_source_catalog.py`: schema validation, reviewed-snapshot
  loading, staleness calculation, and generated reference updates.

Write unreviewed runtime results to the gitignored
`tmp/source-discovery/` directory. Commit only reviewed reachability snapshots.
A transient probe result must not silently modify the maintained source
catalog.

Subagents explore independent source groups and return structured findings.
They do not concurrently edit shared catalog files. The coordinating agent
normalizes identities, resolves conflicting findings, verifies high-value
routes, and writes the reviewed profiles.

## Capability Profile

Each source profile contains:

- stable ID, canonical name, aliases, publisher type, official domains,
  geography, and industry scope;
- functions such as report library, announcement search, regulatory
  correspondence, statistics, company screening, valuation, news, and
  downloads;
- claim-scoped authority and practical-utility ratings for every function;
- homepage, direct function URLs, search pages, documented APIs or query
  endpoints, and help pages;
- URL stability and required parameters;
- supported search fields, site-search procedure, publisher-bound search
  templates, reproducible query examples, and result-identification rules;
- login, membership, payment, WAF, app, WeChat, regional, rate, and download
  constraints;
- citation rules that distinguish directly citable originals from
  discovery-only pages and define required title, date, document ID, publisher,
  and permanent-link fields;
- same-function fallback groups;
- reviewed reachability status, timestamp, final URL, observed error, and
  evidence level.

Supported reachability statuses are:

```text
reachable
reachable-limited
login-required
paywalled
anti-bot
temporarily-unreachable
moved
broken-link
unverified
```

## Routing

Rank candidates in this order:

```text
required-function match
-> source authority
-> originality and independence
-> current reachability
-> practical utility
```

Function match is mandatory. Authority is claim-scoped: an exchange is
authoritative for its own disclosures, while a specialist measurement provider
may be stronger for a defined industry metric. Current reachability determines
which valid route is usable now, but cannot elevate an aggregator over an
official original for the same claim.

Fallbacks are grouped by function. A source used for report-title discovery
must fall back to another report-discovery route, while an announcement search
must fall back to another official announcement route before using a portal
copy.

## Reachability Probing

The live probe performs two stages:

1. Transport checks: DNS, TLS, status code, redirect chain, timeout, and
   response content type.
2. Semantic checks: expected publisher/title fingerprints, error-page
   detection, login or subscription prompts, WAF or CAPTCHA pages, app
   redirects, and presence of the target function.

An HTTP `200` response is not sufficient to mark a function reachable.

Use these default refresh intervals:

| Status | TTL |
| --- | ---: |
| `reachable` or `reachable-limited` | 30 days |
| `login-required`, `paywalled`, or `anti-bot` | 14 days |
| `temporarily-unreachable` | 24 hours |
| `moved` or `broken-link` | 7 days |
| `unverified` | 24 hours |

During research, skip an unexpired `temporarily-unreachable` route and use its
same-function fallback. Recheck stale records before relying on them. Keep
high-authority official sources in the directory when inaccessible and try
official alternate routes, permitted browser access, or verified mirrors under
the existing mirror rules.

When a redirect or search result suggests a new canonical URL, store it as a
candidate. Promote it only after publisher identity and content fingerprints
match and a reviewer accepts the change.

Each probe emits JSON that distinguishes permission, membership, anti-bot,
network, TLS, broken-link, and content-migration outcomes. One failure never
proves permanent closure.

## Subagent Exploration

Explore sources in independent groups:

- official disclosures, exchanges, and regulators;
- Hong Kong listed-company, regulatory, ownership, registry, market,
  government-statistics, and industry sources discovered beyond the supplied
  list;
- macro, government, and official statistics;
- consulting and commercial research;
- specialist industry sources;
- report aggregators and finance portals;
- international organizations and foreign regulators;
- company, investor-relations, customer, supplier, competitor, and association
  sources.

For every assigned website, a subagent must return:

- verified functions and the most valuable use cases;
- direct links to each material function;
- site-search procedure and one reproducible query example;
- login, payment, WAF, download, regional, or app limitations;
- citation eligibility and original-source tracing requirements;
- higher-authority and same-function fallback sources;
- check time and an explicit evidence level for every conclusion.

Homepage-only checks do not satisfy the exploration contract. The coordinating
agent spot-checks high-value direct links and any changed canonical URL.

Treat Eastmoney as a multi-role source family rather than one undifferentiated
aggregator. Distinguish the finance portal, company and market-data pages,
announcement and report indexes, Eastmoney Securities-authored research, and
the `pdf.dfcfw.com` document host. A broker-authored report may be cited as
attributable sell-side research after its publisher, analyst, date, title, and
disclaimer are verified from the document. Portal summaries and document-host
URLs do not inherit that authority without matching report metadata.

Hong Kong discovery is explicitly open-ended. Start from HKEX/HKEXnews, SFC,
AFRC, HKMA, Hong Kong government and statistics portals, issuer IR sites, and
the original publishers linked by those sources. Add other useful Hong Kong
sources found during exploration when they pass the same provenance,
capability, access, citation, and fallback checks. Do not limit the resulting
profiles to websites named in the initial user-supplied catalog.

## Testing

Keep ordinary tests fully offline.

### Schema and Completeness

Validate every profile against one schema. Require functions, direct links,
search instructions, citation rules, same-function fallbacks, reviewed
reachability, timestamps, and evidence levels.

### Routing Invariants

Test that:

- higher-authority sources win when functions are equivalent;
- official originals outrank aggregators and media copies;
- an unavailable source selects a same-function fallback;
- reachability changes do not mutate authority;
- stale records request a refresh rather than becoming permanent exclusions.

### Probe Classification

Use fixed response fixtures for successful content, `200` error pages,
redirects, login prompts, paywalls, WAF challenges, timeouts, TLS failures,
broken links, and moved content.

### Generation Consistency

Regenerate the catalog and guides in tests and compare them with committed
outputs. Mark stale snapshots explicitly. Static tests must not infer live
availability.

### Live Tests

Expose live probes only through an explicit command or pytest marker. A small
smoke set covers high-value official sources and representative access-limit
types. A full probe scans all profiles and produces an audit report. Live
failures update the local cache and report; they do not block ordinary CI.

## Acceptance Criteria

- Every maintained website has a structured capability profile.
- Common Hong Kong research routes discovered beyond the supplied list are
  represented with the same profile and evidence standards.
- Every material function has a direct route, search method, citation rule,
  and same-function fallback.
- Equivalent-function routing prioritizes the highest-trust applicable source.
- Runtime research avoids repeatedly visiting a fresh, temporarily unavailable
  route while preserving automatic retry after its TTL.
- Link migrations are reviewable and cannot silently rewrite canonical URLs.
- Offline tests cover profile contracts, routing, probe classification, and
  generation drift.
- Explicit live commands can refresh selected sources or the entire catalog.
