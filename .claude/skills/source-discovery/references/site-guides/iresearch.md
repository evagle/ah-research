# iResearch

Use iResearch primarily for China internet and digital-service markets,
including ecommerce, digital advertising, online games, payments, cloud,
enterprise software, consumer internet, and selected health and automotive
topics. Confirm the requested industry appears in official search results.

## Direct Search

Use URL-encoded Chinese and English category synonyms:

- Mixed search: `https://s.iresearch.cn/search/{keyword}/`
- Report-only search: `https://s.iresearch.cn/report/{keyword}/`
- Later result pages: `https://s.iresearch.cn/report_2/{keyword}/`
- Report page: `https://report.iresearch.cn/report/{YYYYMM}/{id}.shtml`
- Preview: `https://report.iresearch.cn/report_pdf.aspx?id={id}`

Search the industry term, metric (`市场份额`, `市场规模`, `排名`), company,
and year separately. The search and preview HTML declare GB2312; decode as
GB18030 when UTF-8 parsing produces damaged text.

Report pages expose the title, date, abstract, contents, tags, report ID, and
preview link. Preview pages commonly reference numbered images at
`https://pic.iresearch.cn/rimgs/{id}/{page}.jpg`; more pages may exist than the
initial HTML lists. Probe sequentially only while the next page returns a valid
image. Use images for local extraction and verification, but commit only
extracted values and provenance.

## Evidence

An iResearch report page or iResearch-authored article is original commercial
research, not a media repost. Preserve the exact market definition, period,
geography, denominator, estimation status, and methodology limits. A
prospectus table attributed to iResearch is also acceptable evidence; direct
search is an expansion route for more years, complete rankings, and method
notes rather than a prerequisite for accepting the attributed table.
