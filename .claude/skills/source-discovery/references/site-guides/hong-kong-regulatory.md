# Hong Kong Regulatory And Ownership Routes

Select the route by function: HKEX DI for filed statutory ownership notices,
CCASS for participant holdings on a stated date, and issuer filings for
company-disclosed context. DI is not interchangeable with CCASS, annual reports, or monthly returns.

## Direct URLs

- HKEX Disclosure of Interests (DI):
  `https://di.hkex.com.hk/di/NSForm1.aspx?lang=en`
- HKEX CCASS shareholding search:
  `https://www3.hkexnews.hk/sdw/search/searchsdw.aspx`
- HKEXnews filings:
  `https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en`

## Query fields

- DI after service recovery: listed corporation, stock code, filing or event
  date. Exact HTML parameter names are not established.
- CCASS: `txtShareholdingDate`, `txtStockCode`, `txtParticipantID`, and
  `txtParticipantName`.
- HKEXnews: `stockCode`, `startDate`, `endDate`, and `selectedDocType`.

## Query example

For Pop Mart, try DI with listed corporation `POP MART` or stock code `09992`
after the service is reachable. For CCASS participant holdings, submit
`txtShareholdingDate=2026/07/31&txtStockCode=09992`. Use HKEXnews
`stockCode=09992` for annual reports, monthly returns, and announcements, but
label their ownership implications as adjacent context.

## Result identity

- DI: corporation, filer, form or notice number, event date, filing date,
  interest, shares, percentage, source URL.
- CCASS: date, stock code, participant ID and name, shares, percentage,
  result URL.
- HKEXnews: security code, issuer, title, publication time, document type,
  PDF URL, correction relation.

## Citation fields

- DI: form or notice number, filer, event date, filing date, interest/shares
  or percentage as cited, and source URL.
- CCASS: shareholding date, stock code, participant, shares, percentage, and
  result URL.
- HKEXnews adjacent filings: publisher, title, publication time, document ID
  when present, final PDF URL, and correction or replacement relationship.

## Access limitations

DI was observed as `temporarily-unreachable`; the observed outage does not
establish form parameter names or show that notices ceased to exist. Apply the
24-hour `temporarily-unreachable` TTL through `source_profiles`: skip a fresh
outage only for same-function routing and recheck it when stale. CCASS and
HKEXnews are public rendered flows; use headless Chromium only when
noninteractive retrieval cannot complete their session behavior.

## Same-function fallbacks

DI has no function-equivalent fallback. CCASS measures participant holdings,
not legal or beneficial ownership, and does not cover ultimate owners,
off-system holdings, or statutory DI filings. Annual reports and monthly
returns can be adjacent issuer-disclosed context only; they cannot replace a
filed DI notice. Do not silently widen from DI to CCASS or an annual report.

## Provenance boundaries

DI is authoritative for filed statutory Disclosure of Interests notices.
CCASS is authoritative only for its participant-holdings observation at the
stated date. HKEXnews is authoritative for listed-company filings, not a
statutory-ownership notice unless the opened document itself is the applicable
official filing. A finance portal is discovery-only unless the verified-mirror
exception is satisfied.
