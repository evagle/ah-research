# Shanghai Stock Exchange (SSE)

Use SSE register metadata to cross-check SSE-listed issuer announcements and
use SSE as the primary source for SSE-issued supervisory inquiry materials.
For announcement bodies, use:

`CNINFO opened PDF -> SSE register metadata cross-check -> Playwright headless SSE PDF fallback`

This retrieval order does not change source authority. For Guizhou Moutai,
start with `600519` and `贵州茅台`; do not infer that a company reply is the
exchange's inquiry letter.

## Direct URLs

- Announcements: `https://www.sse.com.cn/disclosure/listedinfo/announcement/`
- Supervisory inquiries:
  `https://www.sse.com.cn/regulation/supervision/inquiries/`
- Site search: `https://www.sse.com.cn/home/search/?webswd=%E8%B4%B5%E5%B7%9E%E8%8C%85%E5%8F%B0`

## Query fields

- Announcement register: security code or abbreviation, board, title, date
  range.
- Inquiry register: security code or abbreviation, inquiry type, date range.

## Query example

For Moutai, search security code `600519` and issuer `贵州茅台`. To distinguish
the route, search announcement titles for `公告` or `回复`, and the supervisory
inquiry register for `问询函` or `监管工作函`; apply the requested date range.

## Result identity

- Announcement: security code, issuer, title, publication date, document URL,
  issuer-authored PDF.
- Inquiry: security code, issuer, letter date, inquiry type, title, letter URL.

## Citation fields

For an announcement, cite the opened issuer PDF and preserve publisher, title,
announcement time or date, document or announcement ID when present, status,
URL, and replacement relationship. CNINFO is the default retrieval route for
A-share issuer-announcement bodies; retain SSE metadata as the exchange
cross-check. For an inquiry, cite the SSE letter as the exchange action. Use
CNINFO as the default retrieval route for the issuer response body and cite it
separately for management explanation, commitments, and remediation.

## Access limitations

The public registers are JavaScript-driven and date-scoped. Begin with
noninteractive `urllib` or `curl`. The SSE static PDF host may first return an
HTML challenge with `x-tengine-error: denied by bot`. If CNINFO is missing,
identity fields do not match, or the exact SSE artifact is required, launch an
isolated Playwright headless SSE PDF fallback: open the announcement page,
navigate to the PDF in the same browser context, allow the JavaScript challenge
to reload, and accept the result only with `Content-Type: application/pdf` or a
`%PDF-` file signature. This fallback does not use a personal Chrome profile or
repeated user Allow prompts. Close the browser after the bounded download.

A register row is discovery metadata, so open and preserve the final PDF or
letter identity.

## Same-function fallbacks

- Company disclosures: `CNINFO` is the default body-retrieval route. Cross-check
  title, issuer, date, and document identity against SSE metadata.
- SSE inquiry letters: no same-function fallback is established. CNINFO or an
  issuer IR reply may supply the issuer response body and adjacent
  issuer-disclosure evidence, but CNINFO issuer responses do not replace an
  SSE inquiry letter.

## Provenance boundaries

SSE is authoritative for its published exchange actions and the register
metadata. The hosted issuer PDF remains issuer-authored content. Do not use an
issuer reply, a portal timeline, or a mirror as proof that SSE issued an
inquiry; portals are for discovery and must be traced back to SSE or CNINFO.
