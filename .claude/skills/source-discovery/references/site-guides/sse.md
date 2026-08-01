# Shanghai Stock Exchange (SSE)

Use SSE for SSE-listed issuer announcements and for SSE-issued supervisory
inquiry materials. For Guizhou Moutai, start with `600519` and `贵州茅台`;
do not infer that a company reply is the exchange's inquiry letter.

## Direct URLs

- Announcements: `https://www.sse.com.cn/disclosure/listedinfo/announcement/`
- Supervisory inquiries:
  `https://www.sse.com.cn/regulation/supervision/inquiries/`
- Site search: `https://www.sse.com.cn/home/search/?webswd=贵州茅台`

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

For an announcement, cite the opened SSE-hosted issuer PDF and preserve
publisher, title, announcement time or date, document or announcement ID when
present, status, URL, and replacement relationship. For an inquiry, cite the
SSE letter as the exchange action; cite an issuer response separately.

## Access limitations

The public registers are JavaScript-driven and date-scoped. Begin with
noninteractive `urllib` or `curl`; use headless Chromium only when a rendered
register is necessary. A row is discovery metadata, so open and preserve the
final PDF or letter identity.

## Same-function fallbacks

- Company disclosures: `CNINFO` is the same-function peer. Cross-check title,
  issuer, date, and document identity there.
- SSE inquiry letters: no same-function fallback is established. CNINFO or an
  issuer IR reply may supply adjacent issuer-disclosure evidence, but neither
  replaces the SSE inquiry letter.

## Provenance boundaries

SSE is authoritative for its published exchange actions and the register
metadata. The hosted issuer PDF remains issuer-authored content. Do not use an
issuer reply, a portal timeline, or a mirror as proof that SSE issued an
inquiry; portals are for discovery and must be traced back to SSE or CNINFO.
