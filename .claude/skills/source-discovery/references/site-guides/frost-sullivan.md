# Frost & Sullivan

Frost & Sullivan covers many industries, but route it by declared coverage
rather than treating every claim as applicable. Check the global industry
directory or a matching China search result before adding it to an industry
search plan.

## Direct Search

For China claims, start with the public fuzzy-search route:

`https://www.frostchina.com/zh/content/search?page=1&query%5BfuzzyQuery%5D={keyword}`

Use `--globoff` with curl when the URL contains unescaped brackets. Search the
industry, company, metric, year, and Chinese/English synonyms separately. Then
open matching `/content/insight/detail/{content-id}` pages.

Other official routes:

- China industry research:
  `https://www.frostchina.com/zh/content/insight?page=1&query%5Btag%5D=INDUSTRY-RESEARCH`
- China sitemap: `https://www.frostchina.com/sitemap.xml`
- Global industry directory: `https://store.frost.com/industries.html`
- Global publisher search fallback:
  `site:frost.com OR site:store.frost.com "{industry}" "{metric}" "{year}"`

The China search and insight pages are publicly retrievable. The global store
search may present Cloudflare and full reports are normally commercial; use
its public industry categories and product metadata for discovery, then retain
any listing document or official Frost publication that contains the table.

## Evidence

Frost & Sullivan tables in authenticated prospectuses and listing
applications are substantive industry evidence, including commissioned
research that has no standalone public report. Preserve the applicant,
document date and page, table title, Frost & Sullivan attribution, data
vintage, market scope, geography, denominator, forecast status, and
commissioning relationship. Lack of a public Frost URL does not by itself
downgrade or invalidate the table.

When an official Frost page is available, use it to recover complete rankings,
additional years, methodology, and revisions. Do not count the provider page
and the prospectus reproduction as independent evidence when they share the
same underlying dataset.
