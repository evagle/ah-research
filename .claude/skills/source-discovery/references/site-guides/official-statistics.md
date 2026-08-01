# Official Statistics Direct Use

Use the producing official statistics agency for an observation, definition,
and release. A government open-data catalog is a route to the producer unless
it is expressly the named data publisher.

## Direct URLs

- Hong Kong Census and Statistics Department (C&SD) Web Tables:
  `https://www.censtatd.gov.hk/en/web_table.html`
- DATA.GOV.HK catalog: `https://data.gov.hk/en/`

## Query fields

- C&SD: table ID, statistic, classification, period, and selected dimensions.
- DATA.GOV.HK: keyword, organization, format, dataset ID or slug, and resource
  URL.

## Query example

For Hong Kong retail-sales context, open C&SD Web Tables, select the relevant
retail-sales table, `all-items retail value`, and the required monthly period;
export the CSV or API result after recording the selected dimensions. On
DATA.GOV.HK, search `retail sales`, filter organization to `Census and
Statistics Department`, then follow the producer resource URL.

## Result identity

- C&SD: table ID, table title, selected dimensions, period, value, unit,
  release date, CSV or API URL.
- DATA.GOV.HK: dataset title, slug or dataset ID, named publisher, update time,
  license, resource format, resource URL.

## Citation fields

For official statistics, preserve publisher, table ID, table title, series or
classification, period, value, unit, definition, release date, and direct CSV,
API, or table URL. For a catalog record, preserve dataset ID, publisher,
resource URL, and update timestamp, then cite the producing agency's resource
for the observation.

## Access limitations

Web Tables are dynamic: a table shell or copied chart does not establish the
selected statistic. Record each dimension and result URL. Use noninteractive
`urllib` or `curl` for downloadable resources first; use headless Chromium
only for required table customization or session flows. A cached route status
does not alter the producer's identity or the citation scope.

## Same-function fallbacks

Use an official statistics publisher with the same measure, definition,
geography, and period as a same-function fallback. DATA.GOV.HK is a catalog
and is not automatically a same-function statistics producer. Do not replace
an official series with a finance portal, copied chart, or a different measure
without labeling it as adjacent context.

## Provenance boundaries

C&SD is authoritative for the tables it produces. DATA.GOV.HK is authoritative
for its catalog metadata and only for a dataset it names itself as publisher;
otherwise the named department owns the observation. For uncataloged official
statistics sources, validate the producing agency, direct result identity,
definition, access status, and same-function peers before use.
