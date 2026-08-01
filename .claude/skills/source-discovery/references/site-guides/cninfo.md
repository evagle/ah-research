# CNINFO A-Share Disclosures

Use CNINFO to find and open statutory A-share disclosures. CNINFO is the
default retrieval route for A-share issuer-announcement bodies and issuer
response bodies. Cross-check listing-exchange metadata when available. CNINFO
is not a substitute for a specific SSE supervisory inquiry letter.

## Direct URLs

- Search entry: `https://www.cninfo.com.cn/`
- Announcement query:
  `https://www.cninfo.com.cn/new/hisAnnouncement/query`
- Static document host: `https://static.cninfo.com.cn/`

## Query fields

Use `column`, `searchkey`, `tabName`, `pageNum`, and `pageSize`. For an
SSE-listed issuer, scope `column=sse`; use `tabName=fulltext` for title/body
search. Treat the endpoint as an implementation-facing retrieval route, not a
guaranteed public API contract.

## Query example

For Guizhou Moutai, POST
`column=sse&tabName=fulltext&searchkey=%E8%B4%B5%E5%B7%9E%E8%8C%85%E5%8F%B0&pageNum=1&pageSize=30`
to `https://www.cninfo.com.cn/new/hisAnnouncement/query`. Use `600519` or an
exact title when available, then open the returned `adjunctUrl` on the static
host.

## Result identity

Preserve `announcementId`, security code, issuer, title, date, `adjunctUrl`,
and the resolved hosted PDF URL. JSON metadata locates the document; the PDF
is the citation target.

## Citation fields

For the opened PDF, preserve publisher, title, announcement time or date,
announcementId or other document ID, status, URL, and replacement relationship.
State that CNINFO distributes the issuer document; do not cite a search JSON
row as the document body. For a response to exchange correspondence, preserve
the response title, issuer, publication time, announcement ID, referenced
exchange letter, management explanation, commitments, remediation, and any
replacement or correction relationship.

## Access limitations

Anonymous POST retrieval was observed but is rate-sensitive. Use
noninteractive `urllib` or `curl` with restrained requests and preserve the
exact PDF URL. If retrieval fails, record the response and continue; a single
failure is not a permanent closure.

## Same-function fallbacks

For SSE issuer announcements, use SSE register metadata to cross-check issuer,
title, date, document type, and identity. If the CNINFO PDF is missing or does
not match, retrieve the SSE-hosted PDF through an isolated Playwright headless
session. For an exchange inquiry letter, move to the SSE inquiry register;
CNINFO issuer responses are important issuer evidence but not equivalent
exchange correspondence.

## Provenance boundaries

CNINFO is official market infrastructure for hosted disclosure documents. The
issuer remains the author of the disclosure, and SSE remains the publisher of
an SSE inquiry letter. Do not promote portal copies or CNINFO search metadata
to original-document authority.
