# HKEX Listing Applicants

Use this source to discover Hong Kong Main Board listing applicants and their
official application documents. The index is discovery metadata. An opened
HKEXnews PDF can be evidence for its contents, but it is not automatically the
current application proof.

## Active Index

Use the active applicant index:

`https://www1.hkexnews.hk/ncms/json/eds/appactive_app_sehk_e.json`

Record the index identity as active, the application ID, issuer, status,
publication date, and every displayed current document path before opening a
document. Retain the raw `w`, `ls`, and `ps` record fields, including each
title, type, version label, and path. An active index result is not itself a
final citation.

## Inactive And Version Identity

Do not infer that an applicant is inactive merely because it no longer appears
in the active index. When an inactive or archived index record is available,
record that index identity separately from the active index identity.

For every candidate document, retain its application ID, issuer, publication
date, document path, and whether the record is an initial application proof,
a PHIP, a revised version, an appointment notice, a termination notice, or a
replacement. The `ls` and `ps` record groups are discovery metadata, not proof
that one document replaces another; preserve the stated title and dates.

## Final PDF Identity

Open the official HKEXnews PDF and retain the final URL, PDF response identity,
application ID, issuer, publication date, document path, and version or
replacement relation. Do not cite a JSON result row or an external search
snippet in place of the opened PDF.

For the Pop Mart peer-expansion regression, the active-applicant target is TOP
TOY application `108384`; the evidence artifact is:

`https://www1.hkexnews.hk/app/sehk/2026/108384/a131511/sehk26033103632.pdf`

This is a historical evidence artifact for the 2020-2025 China pop-toy chart,
not the current application proof. Its relation to the current active-index
document set is `unverified`. Revalidate the active index and match the
application ID, title, type, version, and document path before using any PDF
as the current proof.

The historical chart makes no 2026 market-size claim in the regression; the
chart labels 2026 and later values as forecasts.

## Citation Boundary

The active or inactive index establishes a discovery path. Cite the opened
official application PDF for the document's contents, including Industry
Overview charts, only after preserving its relation to the current index
record. Preserve whether each value is historical or forecast as labeled in
that PDF.
