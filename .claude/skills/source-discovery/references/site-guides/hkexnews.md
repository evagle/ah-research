# HKEXnews Company Disclosures

Use HKEXnews for Hong Kong listed-company announcements, annual reports,
circulars, prospectuses, and trading-halt notices. For Pop Mart, search
`09992` or `Pop Mart` and retain the opened PDF identity.

## Direct URLs

- Title search:
  `https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en`

## Query fields

Use `stockCode`, `startDate`, `endDate`, and `selectedDocType`. The rendered
form also exposes issuer, category, document type, and security-type choices;
record any selection that narrows the result.

## Query example

For Pop Mart, submit `stockCode=09992`, `startDate=2025-01-01`,
`endDate=2026-08-01`, and `selectedDocType=Financial Statements or ESG`.
For a named announcement, narrow the date interval and title terms before
opening the result PDF.

## Result identity

Preserve security code, issuer, title, publication time, category, document
type, PDF URL, and correction relation. The search-result URL is not a
permanent document URL; the final PDF identity controls.

## Citation fields

Cite the opened original PDF and preserve publisher, title, publication time,
document or announcement ID when present, status, final PDF URL, and correction
or replacement relationship.

## Access limitations

HKEXnews uses a JSF session and view-state flow. Default to noninteractive
`urllib` or `curl` for direct document retrieval; use headless Chromium only
when the rendered JSF form is required. Do not repeatedly ask a user to Allow
the same session flow.

## Same-function fallbacks

No same-function official fallback is established for HKEXnews listed-company
disclosures. An exact issuer IR repost may be a convenience copy after matching
the HKEXnews PDF identity. Media, portals, and finance apps are discovery-only;
use them to recover a title, date, or identifier and return to HKEXnews.

## Provenance boundaries

HKEXnews is authoritative for the official publication of listed-company
documents. An issuer repost is issuer-hosted, not independent confirmation; a
portal summary is not a substitute for the original PDF. Use the separate
Hong Kong regulatory guide for DI statutory ownership rather than treating a
filing search as a DI route.
