# Source Catalog

The source catalog is a seed registry, not a closed allowlist.
Do not reject a source solely because it is absent from the catalog.
Use uncataloged sources when the question requires them and they pass validation.
Record uncataloged sources with the same fields, access status, provenance, fallback peers, and evidence level.

This catalog records source-level routing facts checked in the supplied audit reports dated `2026-08-01`. A failed request is a point-in-time observation, not proof of permanent closure.

Keep the concepts separate:

- `accuracy` records a source-authority route prior scoped to that row's `best uses`, not practical usefulness.
- `utility` records a practical-utility route prior scoped to that row's `best uses`, not truth of a specific claim.
- `access status/access model` records current reachability and access policy.
- `limitations` records claim-support boundaries; aggregators, apps, media, social platforms, and report indexes are discovery routes unless original documents are traced.
- `evidence level` records confidence in the access/provenance conclusion for this source record, not source authority, route utility, reachability, or claim support.

Detailed ratings and probe facts:

- Catalog ratings are route priors scoped to each record's stated best uses.
- The routing table keeps the required record fields compact. Its `accuracy` and `utility` fields are best-use route priors, not unconditional global properties.
- `Reliability ratings` gives separate explicit `High`/`Medium`/`Low` route priors for source authority and practical utility, plus audited current reachability. Each rating row inherits the same-ID routing row's `best uses` scope.
- Runtime `conclusion_evidence` is not preassigned in this catalog. Calculate it for the actual claim after retrieving evidence. Do not copy a catalog route prior into a runtime ledger as a claim grade.
- The `rating evidence level` column records confidence in those access/provenance/rating conclusions, not the source-quality score or runtime claim support.
- `Probe facts` gives the Step 2 facts separately: redirect chain, response status, recognizable first-party content, login/paywall indications, and observed technical restriction. `Not recorded in audit` means the audit evidence did not supply that specific fact; it is not an invented negative finding.

Fallback and company-site rules:

- Treat company websites as first-party subject evidence for the company's own statements, disclosures, actions, products, policies, prices, filings, and quotations.
- Do not treat a company's claims about market leadership, customer outcomes, product superiority, or competitive advantage as independent proof.
- Use customer, supplier, competitor, and association websites only within their own first-party scope, and as independent checks only when they are genuinely independent of the issuer and the claim.
- Use aggregators, media, social platforms, and report indexes for discovery only; conclusions must cite the original publisher whenever the original can be identified.
- One failed request never proves permanent closure.
- When a source returns no result, is paywalled, requires unavailable access, or fails technically, continue through other applicable sources in the same category and then adjacent categories.
- Report a source gap only after recording every compliant route attempted, its query, access result, and final error.

Access status vocabulary:

- `public`: open web access observed or official/public route documented.
- `public-limited`: public landing pages or excerpts observed, with deeper search, export, download, app, or data workflows limited.
- `login-required`: account login required for material use.
- `membership/paywalled`: membership, subscription, VIP, client, or payment gate controls material access.
- `anti-bot/technical-limited`: WAF, JavaScript challenge, TLS, rate limit, or scripted-access restriction observed.
- `region/network-limited`: behavior may depend on network, client, region, protocol, or browser context.
- `moved/redirected`: supplied URL moved or redirected to a different canonical route.
- `unavailable`: source route is unavailable after compliant fallback attempts; do not infer permanent closure from one failed request.
- `unverified`: current canonical route or content could not be confirmed from the supplied audit evidence.

Record fields:

ID | canonical source | supplied alias | origin/code ID | category | canonical URL | best uses | accuracy | utility | access status/access model | limitations | recommended fallback peers | last checked | evidence level
--- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---
U01 | Datayes Robo Research | 萝卜投研 | supplied U01 | aggregator/report discovery | https://robo.datayes.com/ | Stock screening and cross-searching broker reports, filings, financials, and data | Medium authority; commercial secondary platform | High practical utility | public-limited; public SPA shell; login route exposed | Proprietary methods; deeper workflows likely account-bound; use as discovery, not primary filing evidence | U03, U08, U10, U11 | 2026-08-01 | `High`
U02 | DYData | 镝数聚 | supplied U02 | report/data marketplace | https://www.dydata.io/ | Broad discovery of industry reports, datasets, charts, and supplier ecosystems | Medium authority; multi-supplier aggregator | High practical utility | membership/paywalled; public previews with VIP/member prompts | Source quality varies by upstream shop; many downloads are gated | U07, U09, U15, U16 | 2026-08-01 | `High`
U03 | Hibor Research | 慧博投研资讯 | supplied U03 | sell-side report aggregator | http://www.hibor.com.cn/ | Broker and industry report discovery, older report retrieval, topic scans | Medium authority as secondary distribution; broker originals hold authority | High practical utility | public-limited; public pages plus PC client/login prompts | Provenance is secondary; full functionality funnels to client/app | U01, U08, U10, U11 | 2026-08-01 | `High`
U04 | AliResearch | 阿里研究院 | supplied U04 | corporate think tank | http://www.aliresearch.com/cn/index | Alibaba ecosystem, e-commerce, platform economy, digital trade, SME trend narratives | High authority for Alibaba-published views; Medium for neutral market claims | Medium practical utility | public; public shell reachable | Institutional bias; not a regulator or raw primary-data source | U07, U09, U02 | 2026-08-01 | `Medium`
U05 | Tencent Big Data WeChat route | 腾讯大数据 | supplied U05 | corporate platform reports | https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=MzA3MDQ4MzQzMg==&scene=124#wechat_redirect | Tencent-published reports when accessed from proper WeChat context | High authority for Tencent's own output | Low practical utility from ordinary web automation | moved/redirected; public-limited | Supplied URL redirects to a WeChat-client surface with verification/open-in-WeChat message | U07, U09, U02 | 2026-08-01 | `High`
U06 | 360 report portal unresolved | 360互联网安全中心 | supplied U06 | security/threat reports | https://zt.360.cn/report/ | Historically vendor security and threat reports if a current official route is found | Unverified authority from current audit; historically High for 360-produced reports | Low practical utility | unverified; DNS failure observed on listed host | Current canonical URL not established; point-in-time DNS failure is not permanent closure proof | U05, official vendor/security disclosures, other primary security publishers | 2026-08-01 | `Low`
U07 | Analysys | 易观分析 | supplied U07 | digital economy research | https://www.analysys.cn/ | Mobile internet, app rankings, digital user behavior, market trend explainers | Medium-high commercial authority; proprietary methodology | High practical utility | public-limited; public articles with subscription products | Vendor-owned metrics; not primary transaction, filing, or official data | U02, U09, U12 | 2026-08-01 | `High`
U08 | NXNY Stock Report Network | 股票报告网 | supplied U08 | report distribution | https://www.nxny.com/stype_hy/ | Scanning industry-report titles, recent uploads, and download popularity | Low-medium authority; distribution site, not original publisher | Medium practical utility | public-limited; login/register/VIP/download affordances visible | Upstream provenance varies; VIP gating visible | U03, U01, U10, U11 | 2026-08-01 | `High`
U09 | iiMedia | 艾媒网 | supplied U09 | market research/media | https://www.iimedia.cn/ | Industry background, consumer trend decks, emerging-sector overview pieces | Medium authority; commercial research and media framing | Medium-high practical utility | public-limited; excerpts public, report/download flows route to member assets | Marketing tone; complete PDFs may be member-gated; cross-check hard claims | U07, U02, U16 | 2026-08-01 | `High`
U10 | Shanghai Stock Exchange | 上海证券交易所 | supplied U10; core code IDs sse in build_event_manifest.SOURCE_DOMAINS and build_market_manifest.SOURCE_DOMAINS; domain sse.com.cn | official exchange | https://www.sse.com.cn/; https://www.sse.com.cn/disclosure/credibility/supervision/inquiries/; https://www.sse.com.cn/home/search/?webswd=贵州茅台 | SSE listed-company disclosures, rules, notices, IPO/bond/REIT information, inquiry letters, official market data, and official site search routing | High authority for SSE-published filings, notices, rules, inquiry letters, and market data | Very high practical utility | public | Not a synthesis/research portal; use search-result summaries only to route back to official announcements, inquiry letters, issuer replies, or regulator originals | U11, C01, U01, U03 | 2026-08-01 | `High`
U11 | Shenzhen Stock Exchange | 深圳证券交易所 | supplied U11; code IDs szse in build_event_manifest and build_market_manifest | official exchange | http://www.szse.cn/ | SZSE disclosures, rulebooks, notices, REIT/bond/equity information, official stats | High authority for SZSE-published official materials | Very high practical utility | public | Not a research synthesis layer; pair with secondary interpretation where needed | U10, U01, U03, C01 | 2026-08-01 | `High`
U12 | Endata | 艺恩 | supplied U12 | data/product vendor | https://www.endata.com.cn/index.html | Current AI vertical-data infrastructure and data-product discovery | Medium authority for current vendor-published products; Low for legacy entertainment-report expectation | Low utility for legacy entertainment use case | public-limited; sample/download flow requires NDA and subscription-style contact | Source drift from older entertainment/box-office role; NDA and formal contact for samples | U02, U07, U09 | 2026-08-01 | `High`
U13 | CaaSData | 卡思数据 | supplied U13 | creator/content marketing data | https://www.caasdata.com/index/index/index.html | Unconfirmed; historically creator and content-marketing data | Current authority unverified from first-party web responses | Low practical utility until rechecked | unverified; region/network-limited possible; DNS resolved but web connections failed | May be down, network-limited, or moved; no permanent closure inference | U02, U09, U07 | 2026-08-01 | `Low`
U14 | Dotour | 旅游圈 | supplied U14 | tourism media/reports | https://www.dotour.cn/ | Unconfirmed tourism-industry media/report route | Current authority unverified | Low practical utility | unverified; DNS failure on listed and bare-domain variants | No redirect target discovered; one audit is not proof of shutdown | U07, U09, U02 | 2026-08-01 | `Low`
U15 | IT Juzi | IT桔子 | supplied U15 | venture/private-market data | https://www.itjuzi.com/ | Venture financing lookup, company/investor timelines, sector deal flow | Medium-high authority for China startup/financing tracking when accessible | High utility in normal browser/product use | anti-bot/technical-limited; HTTP 412 JavaScript challenge observed | Straight programmatic access blocked; trace financing facts to primary announcements where possible | U16, U02, company registry/news originals | 2026-08-01 | `Medium`
U16 | ChinaVenture | 投中网 | supplied U16 | VC/PE media/research | https://www.chinaventure.com.cn/index.html | VC/PE trend tracking, financing environment, industry commentary, research reports | Medium-high commercial/media authority | High practical utility | public-limited; public research lists plus login/register controls | Some premium or personalized features may require login; not a primary registry | U15, U02, U09 | 2026-08-01 | `High`
U17 | 199IT | 199IT | supplied U17 | report/news aggregator | https://www.199it.com/ | Discovering report titles, Chinese summaries, outbound citations to originals | Low-to-medium authority; secondary aggregator/repost outlet | Good practical utility | public | Secondary source quality varies; edge reliability inconsistent | iResearch, CNNIC, CAICT, IDC, original publisher sites | 2026-08-01 | `High`
U18 | CNNIC | CNNIC | supplied U18 | official internet statistics | https://www.cnnic.cn/ | China internet baseline figures, domain statistics, official reports | High authority for China internet/domain statistics | Strong practical utility | public | Narrower than broad market research; institutional framing | CAICT, MIIT, iResearch | 2026-08-01 | `High`
U19 | iResearch | 艾瑞网 / iResearch | supplied U19 | commercial research | https://www.iresearch.cn/ | China internet, advertising, ecommerce, mobile, consumer-industry reports | Medium-to-high commercial authority | Useful practical route | public-limited; articles/report pages public, premium products commercial | Vendor-produced perspective; uneven recency; premium data not fully open | 199IT, IDC, CNNIC, CAICT | 2026-08-01 | `High`
U20 | McKinsey Greater China | 麦肯锡中国 | supplied U20 | consulting | https://www.mckinsey.com.cn/ | Executive sector synthesis, strategic themes, China business context | Medium-to-high authority for consulting analysis; not raw official data | High practical utility | public-limited; public insights with possible registration/contact gating | Lighter on raw tables; consulting framing; client work unavailable | BCG, Bain, Roland Berger, Deloitte, EY, PwC, KPMG | 2026-08-01 | `High`
U21 | BCG China | BCG 中国 | supplied U21 | consulting | https://www.bcg.com/zh-cn/ | Strategic framing, industry themes, executive summaries | Medium-to-high consulting authority | Usually strong utility | anti-bot/technical-limited; Akamai 403 from CLI | Scripted access blocked; not a primary dataset source; proprietary client work private | McKinsey, Bain, Roland Berger, Deloitte, PwC | 2026-08-01 | `Medium`
U22 | Bain China | 贝恩中国 / Bain China | supplied U22 | consulting | https://www.bain.cn/ | Local Bain viewpoints, press releases, high-level China business commentary | Medium-to-high consulting authority | Good practical utility | public | China site can be shallower than global research archives; full studies may be gated elsewhere | McKinsey, BCG, Roland Berger, PwC | 2026-08-01 | `Medium`
U23 | JPMorgan | JPMorgan | supplied U23 | bank research/markets | https://www.jpmorgan.com/global | Public outlooks, finance explainers, banking/payments insights, research-theme discovery | High for sell-side finance and macro commentary with house-view bias | Strong practical utility | public-limited; meaningful public insights, institutional research client/login gated | Not neutral public statistics; not China-specific by default; best research may be client-only | WEF China, Deloitte, EY, official central-bank/regulator sources | 2026-08-01 | `High`
U24 | Big Four China parent record | Deloitte/EY/KPMG/PwC | supplied U24 parent; see U24-Deloitte, U24-EY, U24-KPMG, U24-PwC subrecords | consulting/accounting research source family | See U24 subrecords | Route to the appropriate Big Four China publisher before using attributable analysis | Medium-to-high authority for attributable commercial/advisory analysis; not official statistics | High practical utility as a consulting source family | public-limited | Parent is a family record only; use subrecords for per-firm URL, access, limitations, and fallback routing | McKinsey, BCG, Bain, Roland Berger, IDC | 2026-08-01 | `High`
U24-Deloitte | Deloitte China | Deloitte China | supplied U24a Deloitte China | consulting/accounting research | https://www.deloitte.com/cn/zh.html | Survey-based insights, issue briefs, China market/business policy commentary, research landing pages | Medium-to-high authority for Deloitte-attributable advisory analysis; not official statistics | High practical utility | moved/redirected; public-limited | Branded perspective; variable methodological depth; some deeper downloads may ask for contact details | U24-EY, U24-KPMG, U24-PwC, U20 | 2026-08-01 | `High`
U24-EY | EY China | EY China | supplied U24b EY China | consulting/accounting research | https://www.ey.com/zh_cn | Topic-specific insight pages, transactions, tax, infrastructure, financial-services, and policy-relevant business insights | Medium-to-high authority for EY-attributable advisory analysis; not official statistics | High practical utility | public-limited | Advisory framing; uneven primary-data depth; some downloads may shift into lead-generation flows | U24-Deloitte, U24-KPMG, U24-PwC, U20 | 2026-08-01 | `High`
U24-KPMG | KPMG China | KPMG China | supplied U24c KPMG China | consulting/accounting research | https://kpmg.com/cn/zh.html | Insight archive browsing, China tax alerts, economic monitors, M&A, regulatory, and enterprise trend reports | Medium-to-high authority for KPMG-attributable advisory analysis; not official statistics | High practical utility | moved/redirected; public-limited | Consulting/accounting-house perspective; variable methodological transparency; some premium assets may sit behind forms | U24-Deloitte, U24-EY, U24-PwC, U29 | 2026-08-01 | `High`
U24-PwC | PwC China | PwC China | supplied U24d PwC China | consulting/accounting research | https://www.pwccn.com/zh | White-paper discovery, research landing pages, China-market insight summaries, surveys, regional market analysis | Medium-to-high authority for PwC-attributable advisory analysis; not official statistics | High practical utility | public-limited | Branded perspective; uneven access depth across downloadable assets | U24-Deloitte, U24-EY, U24-KPMG, U20 | 2026-08-01 | `High`
U25 | Roland Berger China context | Roland Berger China | supplied U25 | consulting | https://www.rolandberger.com/en/?country=CN | Operations, manufacturing, automotive, energy transition, industry strategy topics relevant to China | Medium-to-high consulting authority | Useful practical route | moved/redirected; public | Chinese-local guessed path returned 404; public experience mostly English/global with China context | McKinsey, BCG, Bain, PwC | 2026-08-01 | `High`
U26 | Aon China | Aon Hewitt China | supplied U26 | HR/risk advisory | https://www.aon.com.cn/ | HR, benefits, retirement, health, risk trend discovery and white papers | Medium-to-high commercial authority | Strong practical utility | moved/redirected; public-limited | Old Aon Hewitt hostname stale; proprietary benchmarks and client analytics gated | Mercer, Deloitte, EY | 2026-08-01 | `High`
U27 | Mercer China | Mercer China | supplied U27 | HR/benefits benchmarking | https://www.mercer.com.cn/ | HR benchmarks, white papers, benefits trends, workplace health/rewards | High within HR, compensation, mobility, benefits benchmarking as commercial provider | Very strong practical utility | public-limited; commercial survey products and databases gated | Valuable benchmark cuts are paid; public pages often market commercial products | Aon, Deloitte, EY, official labor/statistics sources | 2026-08-01 | `High`
U28 | CAICT | CAICT | supplied U28 | official ICT policy/research | https://www.caict.ac.cn/kxyj/qwfb/qwsj/ | Official ICT, telecom, digital economy, AI, industrial internet white papers | High authority for CAICT-published official research | Strong practical utility | anti-bot/technical-limited; public in principle but CLI got 412 WAF | Automation friction; navigation cumbersome; policy-oriented institutional framing | CNNIC, MIIT, IDC, iResearch | 2026-08-01 | `Medium`
U29 | IDC | IDC | supplied U29 | technology market intelligence | https://www.idc.com/ | Tech market sizing, forecasts, vendor share, enterprise IT/telecom trend discovery | High commercial technology market-intelligence authority | Excellent discovery utility | membership/paywalled; public landing pages/PRs, full reports behind subscription/login | Full reports usually paid; proprietary methodology; public claims often abstracts or press releases | CAICT, iResearch, KPMG, Deloitte | 2026-08-01 | `High`
U30 | CADAS | CADAS | supplied U30 | aviation data/analysis | https://www.cadas.com.cn/ | China civil aviation monitoring, airport/airline commentary, route analysis | Medium niche commercial authority | Good practical utility | public-limited; richer data products likely commercial | Narrow subject area; methodology less transparent than official stats | CAAC, VariFlight, transport research outlets | 2026-08-01 | `High`
U31 | World Economic Forum China | World Economic Forum China | supplied U31 | institutional synthesis | https://cn.weforum.org/ | Comparative framing, public publications, sustainability, competitiveness, industrial transformation | Medium-to-high institutional authority; not primary China statistics | Useful practical utility | public | Not China-exclusive; often synthesis; forum priorities/sponsors can shape framing | McKinsey, Deloitte, PwC, OECD, World Bank | 2026-08-01 | `High`
U32 | Worldpanel by Numerator | Kantar Worldpanel | supplied U32 | consumer panel research | https://market.worldpanelbynumerator.com/global | Consumer-panel methodology, FMCG/retail/shopper trend summaries | High within proprietary consumer-panel measurement | Strong practical utility | moved/redirected; public-limited; panel data and commercial deliverables paid | Brand/domain transition; public site lighter than product layer | Numerator, NielsenIQ, iResearch, McKinsey | 2026-08-01 | `High`
U33 | Flurry | Flurry | supplied U33 | mobile app analytics vendor | https://www.flurry.com/ | App engagement framing, category trend references, vendor methodology discovery | Strong for Flurry SDK telemetry; weaker as universal market proxy | Mobile analytics utility Medium | public-limited; marketing/docs public, analytics data requires account/instrumented apps | Sample bias; limited transparency into panel composition; product-led framing | data.ai, Sensor Tower, Statcounter, official app-store analytics | 2026-08-01 | `High`
U34 | GSMA Mobile Economy | GSMA Mobile Economy | supplied U34 | telecom association reports | https://www.gsma.com/mobileeconomy/ | Telecom adoption, subscribers, connectivity, regional mobile-economy baselines | High for GSMA-published telecom synthesis; not national statistical original | High utility | anti-bot/technical-limited; public report model but Cloudflare challenge from scripted access | Industry-association perspective; forecasts/models; local regulators better for country edge cases | ITU, World Bank, national telecom regulators, OECD | 2026-08-01 | `Medium`
U35 | Xueqiu | 雪球 | supplied U35 | investor social platform | https://xueqiu.com/ | China-market sentiment, ticker/topic discovery, investor narrative tracking | Mixed authority; platform/UGC, not primary securities facts | Useful discovery utility | anti-bot/technical-limited; partial open browsing plus account needs | UGC noise, promotional/manipulated content risk, edits/deletions | SSE, SZSE, HKEX, company IR, Eastmoney, Wind, Choice | 2026-08-01 | `Medium`
U36 | Eastmoney Research Center | 东方财富研报 | supplied U36; core downloader origin download_research RESEARCH_LIST_URL and PDF_URL_TEMPLATE; domains reportapi.eastmoney.com, pdf.dfcfw.com, eastmoney.com | sell-side report aggregator | https://data.eastmoney.com/report/; https://reportapi.eastmoney.com/report/list; https://pdf.dfcfw.com/pdf/H3_{info_code}_{variant}.pdf | Broker report discovery, analyst coverage scans, topic/company report aggregation, and report-download route discovery | Medium; aggregator index, original brokers hold authority | High discovery utility | public-limited | Secondary host; API is undocumented/brittle; broker methods/conflicts vary; always trace material facts to original broker, issuer, exchange, or regulator source | CICC Research, broker portals, Wind, Choice, U63, C01, U10, U11 | 2026-08-01 | `High`
U37 | Aladdin Index | 阿拉丁指数 | supplied U37 | mini-program analytics vendor | https://www.aldzs.com/bg | Use only after fresh browser/manual verification for mini-program trend discovery | Historical vendor authority possible; current live service not confirmed | Low current utility | unverified; region/network-limited possible; HTTP/S timed out from audit vantage | No content/freshness/access policy verified; not permanent closure proof | QuestMobile, 新榜, platform reports, 微信公开课 | 2026-08-01 | `Low`
U38 | TooBigData Douyin tag route | ToBigData | supplied U38 | independent blog/analysis | https://toobigdata.com/tag/douyin/ | Practitioner commentary, growth/ops context, adjacent Douyin articles | Low-to-medium authority; not official Douyin data owner | Discovery/context utility Medium | moved/redirected; supplied path 404 but domain and Douyin tag route live | Broken supplied path; informal methodology; not final citation | 新榜, 巨量引擎, 巨量算数, QuestMobile, platform originals | 2026-08-01 | `High`
U39 | 100EC | 网经社 / 100EC | supplied U39 | ecommerce media/research | http://www.100ec.cn/zt/wmds/ | Ecommerce sector landscape, chronology, report discovery | Medium for curated secondary context; weaker than official/platform filings for hard numbers | Useful discovery route | anti-bot/technical-limited; public browser likely, JS cookie security check observed | Media/consultancy framing, unclear methodology for some claims, secondary-source risk | 国家统计局, 商务部, company disclosures, 36Kr | 2026-08-01 | `Medium`
U40 | Newrank Reports | 新榜报告 | supplied U40 | content-platform analytics/reports | https://newrank.cn/report?bindType=report | WeChat/Weibo/short-video ecosystem reports, rankings, report discovery | Medium-to-high for Newrank-tracked ecosystems | High practical utility | moved/redirected; public-limited; deeper products paid/commercial | Vendor-methodology limits; commissioned reports may be sponsor-shaped | QuestMobile, platform disclosures, 36Kr, 巨量算数 | 2026-08-01 | `High`
U41 | CICC Research | 中金研究 | supplied U41 | sell-side research | https://research.cicc.com/index | Sector theses, China macro framing, broker analyst views, research leads | High for sell-side China analysis within domain; not neutral official data | High utility if accessible | anti-bot/technical-limited; 403 security check from scripted access; some research likely account/licensed | Access restrictions, conflicts of interest, house-view bias | U36, broker portals, Wind, Choice, official statistics | 2026-08-01 | `Medium`
U42 | 199IT Data Navigation Housing Tools | 199IT 房价查询 | supplied U42 | directory/aggregator | http://hao.199it.com/fang.html | Discovering housing-price tools and downstream portals | Low-to-medium authority as directory only | Medium discovery utility | public | Directory quality and outbound link rot; not citable for underlying housing data | Fang.com, 国家统计局 housing series, local statistics bureaus | 2026-08-01 | `High`
U43 | PwC/Pew supplied mismatch parent | Supplied as 皮尤网 but URL is PwC | supplied U43 parent; see U43-PwC and U43-Pew | mismatch guard | Supplied URL https://www.pwc.com/us/en/library.html; intended-label candidate https://www.pewresearch.org/ | Preserve the supplied mismatch and force callers to choose the claim-appropriate subrecord | Low route authority until the intended publisher is resolved | Low route utility except mismatch detection | public-limited for PwC; public for Pew | This parent is not a publisher and must not support a claim; do not treat PwC as Pew or vice versa | U43-PwC, U43-Pew | 2026-08-01 | `High`
U43-PwC | PwC Library | PwC URL from supplied U43 | supplied U43 URL subrecord | consulting/accounting research | https://www.pwc.com/us/en/library.html | PwC-attributable industry outlooks, consulting reports, enterprise topics, and surveys | Medium route prior for PwC-attributable consulting analysis | High route utility for the stated best uses | public-limited; downloads/forms may be gated | Not Pew Research Center; branded consulting perspective and uneven methodological depth | U24-PwC, Deloitte, McKinsey, KPMG | 2026-08-01 | `High`
U43-Pew | Pew Research Center | Intended 皮尤网 label from supplied U43 | supplied U43 intended-label subrecord | public-opinion/social research | https://www.pewresearch.org/ | Pew public-opinion, demographic, social, internet, and technology survey research | High route prior for Pew's own transparent survey research | High route utility for the stated best uses | public | Not PwC; survey scope, sample, geography, wording, and field dates bound every claim | Gallup, Ipsos, World Bank, OECD | 2026-08-01 | `High`
U44 | 36Kr | 36氪 | supplied U44 | business/startup media | https://36kr.com/ | Startup/business news discovery, company/event tracking, report/interview leads | Medium media authority; not primary for most underlying facts | Good discovery utility | anti-bot/technical-limited; public browser likely but scripted body security-check page | Media incentives, sponsored content risk, secondary-source risk | Company press releases, exchange filings, 国家统计局, IT桔子, 企查查, 天眼查 | 2026-08-01 | `Medium`
U45 | National Bureau of Statistics of China | 国家统计局 | supplied U45 | official statistics | https://www.stats.gov.cn/ | Citation-grade official China macro, demographic, industrial, labor, price, housing data | Very high authority for PRC official statistics and methodology | Core practical utility | public | Release lag, revisions, definitional changes, official scope limits | Provincial/city statistical bureaus, 中国政府网 ministries, World Bank | 2026-08-01 | `High`
U46 | State Council portal root replacing stale data path | 中国政府网数据 | supplied U46 | official government portal | https://www.gov.cn/ | Top-level government portal and ministry/page discovery | High authority for official releases when using specific pages; exact supplied data path no longer reliable | Weak as data-hub source | moved/redirected; public | Supplied path redirects to homepage; poor specificity and reproducibility | 国家统计局, ministry sites, provincial/municipal open-data portals, World Bank | 2026-08-01 | `High`
U47 | World Bank Chinese Data | 世界银行中文数据 | supplied U47 | multilateral data | https://data.worldbank.org.cn/ | Cross-country indicators, time series downloads, metadata lookup | High authority for World Bank harmonized indicators | High practical utility | public | Not original origin for every country's raw data; lag vs source agencies | IMF, OECD, UNData, 国家统计局 | 2026-08-01 | `High`
U48 | Provincial and municipal statistics bureaus/government portals source family | 各省市统计局 / 人民政府 source family | supplied U48 | official local source family | Representative official examples: https://tjj.beijing.gov.cn/; https://tjj.sh.gov.cn/; https://stats.gd.gov.cn/; https://www.beijing.gov.cn/; https://www.shanghai.gov.cn/; https://www.gd.gov.cn/ | Province/city breakdowns, local yearbooks, communiques, policy/statistical bulletins | High authority when using the actual local official publisher | High utility for subnational facts | public; source family not single URL | Fragmented IA, inconsistent formats, broken links, PDF-heavy delivery, uneven timeliness | 国家统计局, ministry data pages, local yearbooks, local open-data portals | 2026-08-01 | `Medium`
U49 | MIIT Data | MIIT | supplied U49 | official ministry data | https://www.miit.gov.cn/gxsj/index.html | Industrial output, telecom, manufacturing, sector stats, ministry data discovery | High authority for MIIT-published industry statistics | High utility | public | Mostly aggregate stats; not filings or company document source | NBS, ministry sub-pages, State Council releases | 2026-08-01 | `High`
U50 | People's Bank of China | PBOC | supplied U50; code ID pbc in build_event_manifest and build_market_manifest | official central bank | https://www.pbc.gov.cn/ | Monetary policy notices, official announcements, statistics landing pages | High authority for PBOC-published policy and central-bank data | High utility | moved/redirected; public | Interbank market notices/reference data may be more operational on ChinaMoney | Chinamoney, NFRA, CSRC, MOF | 2026-08-01 | `High`
U51 | Ministry of Education statistics family | Ministry of Education supplied URL | supplied U51 | official education statistics | https://www.moe.gov.cn/jyb_sjzl/moe_560/2024/ | Official education statistics and annual national education stats | High authority for MOE-published education statistics | High utility via current family | moved/redirected; public; supplied historical leaf returned 404 | Supplied URL stale; year folders change; use stats family not hard-coded leaf | MOE stats family, NBS, provincial education bureaus | 2026-08-01 | `High`
U52 | State Council ministry/commission source family | State Council ministry/commission source family | supplied U52 | official portal/source family | https://www.gov.cn/ | Finding correct ministry/commission site before switching to ministry domain | High as government routing portal; primary authority belongs to target ministry page | Medium route utility | public; anti-bot/technical-limited | Router, not primary evidence source; org directory returned 403 from CLI | Direct ministry domains, gov.cn homepage, State Council Gazette | 2026-08-01 | `Medium`
U53 | World Bank Open Data duplicate | World Bank Open Data | supplied U53 duplicate of World Bank family also covered by U47 | multilateral data | https://data.worldbank.org/ | Cross-country macro/development indicators and statistical baselines | High authority for World Bank standardized series | High utility | public | Duplicate coverage with U47 Chinese World Bank data; not announcements or filings source | IMF, UNdata, Eurostat, national statistical offices | 2026-08-01 | `High`
U54 | IMF Data | IMF Data | supplied U54 | multilateral data | https://www.imf.org/en/Data; https://data.imf.org/ | Balance of payments, fiscal, debt, macro surveillance context | High authority for IMF-published data | High utility when accessible | anti-bot/technical-limited; public in browser but 403 from CLI | Operationally brittle for strict CLI extraction | World Bank, UNdata, WTO, central banks, national stats offices | 2026-08-01 | `Medium`
U55 | WHO Global Health Observatory | WHO World Health Data Platform | supplied U55 | official health data | https://www.who.int/data/gho | Health indicators, disease burden, mortality, public-health context | High authority for WHO-published health indicators | High utility for health/demographics | public | Not relevant for filings or regulatory letters | UNdata, World Bank, national health ministries | 2026-08-01 | `High`
U56 | UNdata | UNdata | supplied U56 | official UN statistical aggregator | https://data.un.org/ | Cross-country demographic, economic, trade, and social indicators | High authority as UN statistical aggregator | High utility | public | Update cadence can lag specialized agency portals; not document source | UNSD portals, World Bank, IMF, Eurostat | 2026-08-01 | `High`
U57 | WTO Stats | WTO Statistics | supplied U57 | official trade statistics | https://stats.wto.org/; https://timeseries.wto.org/ | Trade flows, tariff indicators, country trade profiles | High authority for WTO-published trade data | High utility | public | Not primary for company/regulator documents | UN Comtrade, World Bank, national customs/trade agencies | 2026-08-01 | `High`
U58 | UN SDG Data Portal | UN SDG Indicators | supplied U58 | official SDG indicators | https://unstats.un.org/sdgs/dataportal | SDG trend checks and internationally normalized indicator lookups | High authority for UNSD SDG indicator series | High utility | public | Narrower than national stats for local questions; not document source | UNdata, World Bank, national statistical offices | 2026-08-01 | `High`
U59 | UNSD Demographic and Social Statistics | UN Demographic and Social Statistics | supplied U59 | official demographic/social statistics | https://unstats.un.org/unsd/demographic-social/ | Population, civil registration, social-stat methodology, portal discovery | High authority for UNSD demographic/social programs | High route utility | public | Family/landing orientation rather than all-in-one dataset | UNdata, national census/stat offices, World Bank | 2026-08-01 | `High`
U60 | SEC and EDGAR | SEC | supplied U60 | official securities regulator/filings | https://www.sec.gov/; https://www.sec.gov/edgar/search/ | Original US filings, enforcement, prospectuses, no-action letters | High authority for SEC-published filings and enforcement material | Very high utility | public-limited; public with rate limits and user-agent expectations | Generic scraping can trigger rate/risk pages; careful request hygiene required | Company IR, exchange notices, press releases | 2026-08-01 | `High`
U61 | Eurostat Database | Eurostat Database | supplied U61 | official EU statistics | https://ec.europa.eu/eurostat/data/database | EU macro, labor, trade, regional, demographic series | High authority for EU harmonized statistics | High utility | public | Not company-document or announcement source | ECB, national statistical offices, World Bank, UNdata | 2026-08-01 | `High`
U62 | US Department of Commerce | US Commerce | supplied U62 | official department portal | https://www.commerce.gov/ | Portal discovery for Commerce sub-agencies and department announcements | High authority for department releases when reached | Medium route utility | anti-bot/technical-limited; public in browser but 403 Cloudflare from CLI | Most useful work moves to BEA, Census, ITA, BIS, NOAA, USPTO, NIST | Commerce sub-agencies directly, SEC for filings, agency newsrooms | 2026-08-01 | `Medium`
U63 | Fenghuo Research Reports | 烽火研报 | supplied U63 | research report aggregator | https://www.fhyanbao.com/ | Discovery of sell-side and industry reports when browser/TLS route is acceptable | Low authority for final claims; commercial aggregator, not official | Medium discovery utility | anti-bot/technical-limited; public web but expired certificate; insecure fetch reached final host | Poor certificate hygiene; trace every material fact to original broker, issuer, exchange, or regulator | Eastmoney report portal, Sina Finance, broker sites, company IR, exchange filings | 2026-08-01 | `High`

## Reliability Ratings

The `rating evidence level` records confidence in the ratings/provenance conclusion, not the rating value itself.

ID | source authority route prior | practical utility route prior | current reachability | runtime conclusion evidence | rating evidence level
--- | --- | --- | --- | --- | ---
U01 | Medium | High | High | Calculate per claim | `High`
U02 | Medium | High | High | Calculate per claim | `High`
U03 | Medium | High | High | Calculate per claim | `High`
U04 | High | Medium | Medium | Calculate per claim | `Medium`
U05 | High | Low | Low | Calculate per claim | `High`
U06 | Low | Low | Low | Calculate per claim | `Low`
U07 | Medium | High | High | Calculate per claim | `High`
U08 | Low | Medium | High | Calculate per claim | `High`
U09 | Medium | Medium | High | Calculate per claim | `High`
U10 | High | High | High | Calculate per claim | `High`
U11 | High | High | High | Calculate per claim | `High`
U12 | Medium | Low | High | Calculate per claim | `High`
U13 | Low | Low | Low | Calculate per claim | `Low`
U14 | Low | Low | Low | Calculate per claim | `Low`
U15 | Medium | High | Medium | Calculate per claim | `Medium`
U16 | Medium | High | High | Calculate per claim | `High`
U17 | Low | High | Medium | Calculate per claim | `High`
U18 | High | High | High | Calculate per claim | `High`
U19 | Medium | High | High | Calculate per claim | `High`
U20 | Medium | High | High | Calculate per claim | `High`
U21 | Medium | High | Medium | Calculate per claim | `Medium`
U22 | Medium | Medium | High | Calculate per claim | `Medium`
U23 | High | High | High | Calculate per claim | `High`
U24 | Medium | High | High | Calculate per claim | `High`
U24-Deloitte | Medium | High | High | Calculate per claim | `High`
U24-EY | Medium | High | High | Calculate per claim | `High`
U24-KPMG | Medium | High | High | Calculate per claim | `High`
U24-PwC | Medium | High | High | Calculate per claim | `High`
U25 | Medium | Medium | High | Calculate per claim | `High`
U26 | Medium | High | High | Calculate per claim | `High`
U27 | High | High | High | Calculate per claim | `High`
U28 | High | High | Medium | Calculate per claim | `Medium`
U29 | High | High | High | Calculate per claim | `High`
U30 | Medium | Medium | High | Calculate per claim | `High`
U31 | Medium | Medium | High | Calculate per claim | `High`
U32 | High | High | High | Calculate per claim | `High`
U33 | Medium | Medium | High | Calculate per claim | `High`
U34 | High | High | Medium | Calculate per claim | `Medium`
U35 | Low | Medium | Medium | Calculate per claim | `Medium`
U36 | Medium | High | High | Calculate per claim | `High`
U37 | Low | Low | Low | Calculate per claim | `Low`
U38 | Low | Medium | High | Calculate per claim | `High`
U39 | Medium | Medium | Medium | Calculate per claim | `Medium`
U40 | Medium | High | High | Calculate per claim | `High`
U41 | High | High | Medium | Calculate per claim | `Medium`
U42 | Low | Medium | High | Calculate per claim | `High`
U43 | Low | Low | High | Calculate per claim | `High`
U43-PwC | Medium | High | High | Calculate per claim | `High`
U43-Pew | High | High | High | Calculate per claim | `High`
U44 | Medium | High | Medium | Calculate per claim | `Medium`
U45 | High | High | High | Calculate per claim | `High`
U46 | High | Low | High | Calculate per claim | `High`
U47 | High | High | High | Calculate per claim | `High`
U48 | High | High | Medium | Calculate per claim | `Medium`
U49 | High | High | High | Calculate per claim | `High`
U50 | High | High | High | Calculate per claim | `High`
U51 | High | High | High | Calculate per claim | `High`
U52 | High | Medium | Medium | Calculate per claim | `Medium`
U53 | High | High | High | Calculate per claim | `High`
U54 | High | High | Medium | Calculate per claim | `Medium`
U55 | High | High | High | Calculate per claim | `High`
U56 | High | High | High | Calculate per claim | `High`
U57 | High | High | High | Calculate per claim | `High`
U58 | High | High | High | Calculate per claim | `High`
U59 | High | High | High | Calculate per claim | `High`
U60 | High | High | High | Calculate per claim | `High`
U61 | High | High | High | Calculate per claim | `High`
U62 | High | Medium | Medium | Calculate per claim | `Medium`
U63 | Low | Medium | Medium | Calculate per claim | `High`

## Probe Facts

ID | redirect chain | response status | recognizable first-party content | login/paywall indications | observed technical restriction | probe evidence level
--- | --- | --- | --- | --- | --- | ---
U01 | No redirect recorded | `200 OK` | Public SPA shell; title/keywords/config fields | `login_url=https://app.datayes.com/sign` exposed | None recorded | `High`
U02 | No redirect recorded | `200 OK` | Homepage, previews, listing pages | `会员特惠`, `注册/登录`, `buy vip`, member dialogs, report/download language | None recorded | `High`
U03 | No redirect recorded | `200 OK` for host and report detail pages | Homepage and report detail pages | PC client download/login prompt for full functionality | None recorded | `High`
U04 | No redirect observed | `200 OK` | Branded AliResearch landing page shell | Not recorded in audit | JS-driven rendered content; raw HTML exposes little | `Medium`
U05 | `https://data.qq.com/reports` -> WeChat profile URL | Destination returned a verification/permission page; numeric status not recorded | WeChat destination tied to Tencent account | Asked to open in WeChat; verification/permission message | WeChat-client context required for practical use | `High`
U06 | No redirect target obtained | DNS resolution failure for `https` and `http` listed host | None verified | Not recorded in audit | DNS failure | `Low`
U07 | No redirect recorded | `200 OK` for homepage and article detail | Public article content; Analysys marketing pages | Login/register controls and subscription products `易观千帆`, `博阅` | None recorded | `High`
U08 | `http://www.nxny.com/stype_hy/` -> `https://www.nxny.com/stype_hy/` | `200 OK` | Report lists, PDF icons, download rankings | `高级会员`, `登录`, `注册`, VIP/download affordances | None recorded | `High`
U09 | No redirect recorded | `200 OK` for homepage and sample article | Public excerpt text and sample article | `附下载`; member-report asset and report center route | None recorded | `High`
U10 | No redirect observed for audited root; core routes also checked | `200 OK`; inquiries `200`; SSE search for `贵州茅台` `200` | Official SSE branding, investor/member sections, disclosure/rule content; inquiries title `监管问询` | Member areas exist but are separate | None recorded; search route is routing aid only, not final evidence above original announcement | `High`
U11 | No redirect recorded | `200 OK` on full GET; one HEAD-style attempt reset connection | Exchange content; public HTML/PDF document references | Member zones clearly labeled separately | HEAD-style connection reset observed; body fetch succeeded | `High`
U12 | No redirect recorded | `200 OK` | `AI 垂类数据基础设施` current site content | Sample/download flow requires NDA/subscription-style contact | Source drift from legacy entertainment role | `High`
U13 | No redirect recorded | DNS resolved to `103.86.45.203`; HTTP/S web connections failed | None verified | Not recorded in audit | Web connections failed from audit network | `Low`
U14 | No redirect target discovered | DNS failure for listed and obvious variants | None verified | Not recorded in audit | DNS failure | `Low`
U15 | No redirect recorded | `HTTP 412` | JavaScript challenge / anti-automation page | Not inspectable from normal content | Anti-bot challenge blocks straightforward programmatic access | `Medium`
U16 | No redirect recorded | `200 OK`; report list page reachable | Homepage and research-list pages | Login/register controls | None recorded | `High`
U17 | `http://199it.com/` and `https://199it.com/` -> `https://www.199it.com/` | Homepage HTML returned; exact `www` host timed out once | Homepage HTML | No login required for homepage/article access | Uneven edge behavior; one direct `www` timeout | `High`
U18 | Supplied `http://www.cnnic.cn` redirected to `https://www.cnnic.cn/` | `200` | Official CNNIC site and standard report pages | None recorded | None recorded | `High`
U19 | No redirect recorded | `200`; `gb2312` homepage rendered after charset handling | iResearch homepage, articles/report pages | Premium products/deeper databases commercial | Charset handling needed | `High`
U20 | No redirect recorded | `200` | McKinsey China site; `/insights/` section exposed | Some downloads/campaign assets may ask registration/contact info | None recorded | `High`
U21 | No redirect recorded | `403 Access Denied` from Akamai | Explicit Akamai denial text; public property not closed | Some assets may be gated, but report pages not directly validated | CDN/WAF scripted-access block | `Medium`
U22 | No redirect recorded | `200` | Bain China homepage and linked news/info pages | Deeper thought leadership may be gated elsewhere; no homepage login required | None recorded | `Medium`
U23 | No redirect recorded | `200` | Links to `/insights`, `/markets`, `/insights/research` | Institutional/premium research and some market products client/login gated | None recorded | `High`
U24 | See U24 subrecords | See U24 subrecords | See U24 subrecords | See U24 subrecords | See U24 subrecords | `High`
U24-Deloitte | `https://www2.deloitte.com/cn/zh.html` -> `https://www.deloitte.com/cn/zh.html` | `200` | Deloitte China public site and research pages | Some PDFs/download assets may be form-gated | None recorded | `High`
U24-EY | No redirect recorded | `200` | EY China `/zh_cn/insights` and newsroom pages | Some full reports/PDFs/campaign assets may be contact-gated | None recorded | `High`
U24-KPMG | `https://home.kpmg/cn/zh/home.html` -> `https://kpmg.com/cn/zh.html` | `200` | KPMG China live insights archive | Some PDFs/downloadables may be gated/contact-driven | None recorded | `High`
U24-PwC | No redirect recorded | `200` | PwC China homepage links to `research-and-insights` | Some reports/newsletter/download flows may be form-gated | None recorded | `High`
U25 | Supplied URL redirected to `https://www.rolandberger.com/en/?country=CN`; guessed `zh-cn` path returned `404` | `200` for canonical; `404` for guessed Chinese path | Roland Berger global English site with China country context | Some downloads/lead-generation flows may be gated | Locale/path drift | `High`
U26 | Old `aonhewitt.com.cn` host failed DNS; replacement `https://www.aon.com.cn/` reached | Replacement returned `200` | `怡安企业服务` branded current site with `/insights` | Proprietary benchmarks/client analytics gated | Old hostname invalid by DNS | `High`
U27 | No redirect recorded | `200` | Mercer China public site and insight pages | Survey products and benchmark databases commercial | None recorded | `High`
U28 | No redirect recorded | `412 Precondition Failed` for page and root | WAF cookies/scripts indicate live official site | Not directly validated due WAF | WAF blocks scripted retrieval | `Medium`
U29 | Sample report URL redirected to `https://my.idc.com/`; root `https://www.idc.com/` reached | Root `200`; sampled report route ended `403` | IDC public research landing pages and press releases | Full report path behind `my.idc.com` subscription/login | Account/subscription gate for full reports | `High`
U30 | `http://www.cadas.com.cn/` -> `https://www.cadas.com.cn/` | `200` | CADAS public articles/summaries | Richer aviation data likely in commercial ecosystems | None recorded | `High`
U31 | No redirect recorded | `200` | WEF China links to `/publications/` and Chinese articles/stories | Newsletter-style prompts possible; many reports open | None recorded | `High`
U32 | `https://www.kantarworldpanel.com/global` -> `https://market.worldpanelbynumerator.com/global` | `200` | Worldpanel by Numerator public marketing/insight site | Full panel datasets and deeper reports paid/commercial | Brand/domain transition | `High`
U33 | Canonical tag matches supplied URL | `200` | Title `Flurry \| Mobile App Analytics Platform for Android & iOS` | Actual analytics data requires product account/instrumented apps | None recorded | `High`
U34 | URL resolves to same path | `403` with Cloudflare `Just a moment...` | Cloudflare challenge page; origin reachable | Public report model expected but not validated by script | Cloudflare challenge gates scripted access | `Medium`
U35 | Canonical root used | `200` but body is Aliyun WAF bootstrap/challenge | Aliyun WAF bootstrap/challenge, not readable content | Login/account needed for deeper features/interactions | WAF challenge gates scripted browsing | `Medium`
U36 | `http://data.eastmoney.com/report/` -> `https://data.eastmoney.com/report/`; API base and sample checked in core audit | Portal `200`; API base `404`; sample API list request `500` | Portal title `研报中心`; public report index/metadata | Deeper report access depends on source/clickthrough | Undocumented API brittle | `High`
U37 | No redirect recorded | DNS resolved, but HTTP/S timed out | None verified | Not recorded in audit | HTTP/S timeout from audit vantage | `Low`
U38 | Supplied path returned canonical same path; root/tag route live | Supplied path `404`; root `200`; tag route discoverable | Root title `TooBigData - 广告运营、增长、AI 与数据手记` | None recorded | Supplied path broken | `High`
U39 | No redirect recorded | Server returned `200` | JS cookie security check `正在进行安全检查，请稍候...` | Not recorded in audit | JS cookie security challenge | `Medium`
U40 | `https://report.newrank.cn/index.html?bindType=report` -> `https://newrank.cn/report?bindType=report` | `200` | Title `报告分析-新榜` | Deeper datasets/products paid/commercial | Route moved | `High`
U41 | No redirect recorded | `403` | Security check page; origin responds | Some research likely client/account/licensed or summary-only | Security gate blocks scripted access | `Medium`
U42 | No redirect recorded | `200` | Title `房价查询工具-199IT数据导航网站--Hao.199it.com`; links out to tools | None recorded | Directory/link-rot risk | `High`
U43 | Supplied PwC URL and intended Pew URL both checked | PwC `200`; Pew `200` | Name/URL mismatch confirmed across both canonical publishers | PwC downloads/forms may be gated; Pew public | Supplied label says Pew while supplied URL is PwC | `High`
U43-PwC | No redirect recorded | `200` | PwC canonical tag matches the supplied PwC URL | Downloads/forms may be gated | None recorded | `High`
U43-Pew | No redirect recorded | `200` | Pew canonical tag matches the Pew domain | Not recorded in audit | None recorded | `High`
U44 | Canonical root used | `200` but body is security-check page | Volcano Engine security-check page `正在进行安全检测...` | Not recorded in audit | Security gate blocks scripted body access | `Medium`
U45 | `http://www.stats.gov.cn` -> `https://www.stats.gov.cn/` | `200` | Title `国家统计局` | None recorded | None recorded | `High`
U46 | Supplied path redirects to `https://www.gov.cn/` homepage | Root `200` | Government portal homepage | None recorded | Old data-hub path is stale/unspecific | `High`
U47 | Canonical tag matches `https://data.worldbank.org.cn/` | `200` | World Bank Chinese data portal | None recorded | None recorded | `High`
U48 | Source family; representative samples checked | Beijing, Shanghai, Guangdong statistics/government samples `200`; Guangdong samples slow | Official local statistics/government portals | None recorded | Fragmented family; inconsistent formats; slow responses in samples | `Medium`
U49 | No redirect recorded | `200` | Title `工信数据` | None recorded | None recorded | `High`
U50 | `http://www.pbc.gov.cn` -> `https://www.pbc.gov.cn/` | `200` | Official PBOC site | None recorded | None recorded | `High`
U51 | Supplied historical URL returned `404`; current family reached | Supplied `404`; replacement `200` | Title `2024年教育统计数据` | None recorded | Stale historical leaf path | `High`
U52 | Root reached; org-directory family separately checked | `https://www.gov.cn/` `200`; `https://www.gov.cn/gwyzzjg/zuzhi/` `403` | State Council portal root | None recorded | Org-directory path bot-gated to CLI; family is router | `Medium`
U53 | No redirect recorded | `200` | World Bank Open Data portal | None recorded | Duplicate World Bank family coverage with U47 | `High`
U54 | No redirect recorded | `403` for `https://www.imf.org/en/Data` and `https://data.imf.org/` | WAF/blocked response from IMF data family | Not recorded in audit | Bot/WAF-gated to CLI | `Medium`
U55 | No redirect recorded | `200` for `https://www.who.int/data/gho` and `https://www.who.int/data` | WHO data pages | None recorded | None recorded | `High`
U56 | No redirect recorded | `200` | UNdata portal | None recorded | None recorded | `High`
U57 | No redirect recorded | `200` for `https://stats.wto.org/` and `https://timeseries.wto.org/` | Title `WTO Stats` | None recorded | None recorded | `High`
U58 | No redirect recorded | `200` | UNSD SDG data portal | None recorded | None recorded | `High`
U59 | No redirect recorded | `200` | UNSD demographic/social statistics family | None recorded | Family/landing orientation | `High`
U60 | No redirect recorded | `200` for SEC root with descriptive user-agent and EDGAR search | SEC root and EDGAR search | None recorded | Generic scraping can trigger rate/risk pages; careful user-agent/rate needed | `High`
U61 | No redirect recorded | `200` | Eurostat database page | None recorded | None recorded | `High`
U62 | No redirect recorded | `403`; `/news` also `403` | Cloudflare `Just a moment...` page | Not recorded in audit | WAF-gated to CLI | `Medium`
U63 | `https://fhyanbao.com/` TLS failure; insecure route reached `https://www.fhyanbao.com/` | TLS validation failed; insecure fetch reached final page | Title `烽火研报 - 专业研报平台...` | Not recorded in audit | Expired TLS certificate | `High`

## Existing-Core Sources

These `Cxx` rows include only unique existing-core sources from script registries and downloaders. Canonical duplicates are merged into supplied U rows while retaining both supplied and code-origin labels: SSE is merged into U10, SZSE into U11, Eastmoney into U36, and PBOC into U50.

ID | canonical source | supplied alias | origin/code ID | category | canonical URL | best uses | accuracy | utility | access status/access model | limitations | recommended fallback peers | last checked | evidence level
--- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---
C01 | CNINFO | 巨潮资讯网 | download_filings STOCK_LIST_URL, ANNOUNCEMENT_QUERY_URL, PDF_BASE_URL; domains cninfo.com.cn and static.cninfo.com.cn | official A-share disclosure platform | https://www.cninfo.com.cn/; https://www.cninfo.com.cn/new/hisAnnouncement/query; https://static.cninfo.com.cn/ | Primary original-document tracing for A-share announcements, annual reports, prospectuses, ad hoc filings | High authority for exchange-listed company disclosures hosted there | Very high utility | public | JS-heavy search can be brittle; company/exchange confirmation still useful | SSE, SZSE, issuer IR pages | 2026-08-01 | `High`
C02 | HKEX and HKEXnews | HKEXnews listed-company search | build_event_manifest hkex; build_market_manifest hkex; download_filings HKEX_SEARCH_URL, HKEX_BASE_URL, HKEX_ACTIVE_STOCK_URL; domains hkex.com.hk and hkexnews.hk | official exchange/news portal | https://www.hkex.com.hk/; https://www1.hkexnews.hk/listedco/listconews/index/lci.html?lang=zh; https://www1.hkexnews.hk/search/titleSearchServlet.do | Primary original-document tracing for HK announcements, circulars, prospectuses, annual reports, trading halts | High authority for HKEX-published/listed-company documents | Very high utility | public | Search/filter UX is portal-centric; issuer IR useful for decks and reposts | Issuer IR, SFC, company annual reports | 2026-08-01 | `High`
C03 | China Securities Regulatory Commission | CSRC | build_event_manifest csrc; domain csrc.gov.cn | official securities regulator | http://www.csrc.gov.cn/ | Rules, enforcement, policy notices, press releases, official interpretations | High authority for CSRC-published securities regulation | High utility | public | Not a company filing repository | Exchanges, CNINFO, PBOC, NFRA | 2026-08-01 | `High`
C04 | Ministry of Finance | MOF | build_event_manifest mof; domain mof.gov.cn | official ministry | http://www.mof.gov.cn/ | Budget, fiscal/tax circulars, accounting policy notices, official announcements | High authority for MOF-published materials | High utility | public | Downstream implementation may live on SAT or other ministry sites | PBOC, State Council, SAT, local finance bureaus | 2026-08-01 | `High`
C05 | National Financial Regulatory Administration | NFRA | build_event_manifest nfra; domain nfra.gov.cn | official financial regulator | https://www.nfra.gov.cn/ | Banking/insurance supervision notices, measures, enforcement, official announcements | High authority for NFRA-published materials | High utility | public | Older CBIRC-era materials may need historical path work | PBOC, CSRC, State Council, institutions' own sites | 2026-08-01 | `High`
C06 | ChinaMoney | 中国货币网 | build_market_manifest chinamoney; domain chinamoney.com.cn | official market-infrastructure/reference-data portal | https://www.chinamoney.com.cn/chinese/index.html | Interbank market notices, bond reference data, issuance calendars, market discovery | High for market-infrastructure/reference data; legal origin may be regulator/issuer | High utility | public | For legal authority, trace to regulator, exchange, issuer, or filing PDF | PBOC, NAFMII, issuer docs, exchange filings | 2026-08-01 | `High`
C07 | Securities and Futures Commission of Hong Kong | SFC | build_event_manifest sfc; domain sfc.hk | official securities regulator | https://www.sfc.hk/en/ | Enforcement, public statements, regulatory circulars, licensed-entity checks | High authority for SFC-published materials | High utility | public | Not a listed-company filing database | HKEXnews, issuer IR, AFRC, HKMA | 2026-08-01 | `High`
C08 | Accounting and Financial Reporting Council | AFRC | build_event_manifest afrc; domain afrc.org.hk | official audit/accounting regulator | https://www.afrc.org.hk/ | Audit oversight, investigations, accounting-sector regulation, announcements | High authority within audit/accounting-regulation scope | High utility | public | Narrower than SFC/HKEX for issuer news | SFC, HKEX, company annual reports | 2026-08-01 | `High`
C09 | Hong Kong Monetary Authority | HKMA | build_event_manifest hkma; build_market_manifest hkma; domain hkma.gov.hk | official monetary authority | https://www.hkma.gov.hk/eng | Banking circulars, regulatory guidance, monetary/FX statements | High authority for HKMA-published materials | High utility | public; region/network-limited | HTTP/2 handling was flaky in CLI; use browser or HTTP/1.1 if automation fails | SFC, IA, banks' own disclosures | 2026-08-01 | `High`
C10 | Insurance Authority of Hong Kong | IA | build_event_manifest ia; domain ia.org.hk | official insurance regulator | https://www.ia.org.hk/ | Insurance regulation, circulars, licensing notices | High authority for IA-published materials | High utility in browser | anti-bot/technical-limited | Public in browser; 403 from audit environment; operationally brittle for CLI extraction | HKMA, SFC, insurer sites, gazettes | 2026-08-01 | `Medium`
C11 | Hong Kong Police Force | HKPF | build_event_manifest hkpf; domain police.gov.hk | official law-enforcement portal | https://www.police.gov.hk/ | Scam alerts, enforcement/news context, public advisories | High authority for HKPF-published statements | Medium utility | public | Contextual source, not corporate filing source | ICAC, Judiciary, SFC, company statements | 2026-08-01 | `High`
C12 | Independent Commission Against Corruption | ICAC | build_event_manifest icac; domain icac.org.hk | official anti-corruption authority | https://www.icac.org.hk/ | Arrest/case announcements, corruption investigations, press releases | High authority for ICAC-published materials | High utility for integrity events | public | Not securities filing or court-judgment database | Judiciary, Police, SFC, company announcements | 2026-08-01 | `High`
C13 | Hong Kong Judiciary | HK Judiciary | build_event_manifest hkjd; domain judiciary.hk | official judiciary portal | https://www.judiciary.hk/ | Judgments, cause lists, court announcements, legal source tracing | High authority for official court materials | High utility for legal-event tracing | public | Discovery can be slower than news; requires case context | e-Legal resources, press releases, HKEX issuer announcements | 2026-08-01 | `High`
C14 | Sina Finance | 新浪财经 | evaluated candidate from audit core recommendations | finance media/aggregator | https://finance.sina.com.cn/ | Fast company/news/topic discovery, quote and announcement navigation, app/portal leads | Medium as major media/aggregator; not official | High discovery utility | public | Not primary evidence; every material fact must trace to exchange, company, regulator, court, or original report source | Eastmoney portal, issuer IR, official exchanges, official regulators | 2026-08-01 | `High`

### Existing-Core Reliability Ratings

These route priors inherit each C record's stated `best uses`. They do not
promote discovery sources to primary evidence and do not pregrade a runtime
claim.

ID | source authority route prior | practical utility route prior | current reachability | runtime conclusion evidence | rating evidence level
--- | --- | --- | --- | --- | ---
C01 | High | High | High | Calculate per claim | `High`
C02 | High | High | High | Calculate per claim | `High`
C03 | High | High | High | Calculate per claim | `High`
C04 | High | High | High | Calculate per claim | `High`
C05 | High | High | High | Calculate per claim | `High`
C06 | High | High | High | Calculate per claim | `High`
C07 | High | High | High | Calculate per claim | `High`
C08 | High | High | High | Calculate per claim | `High`
C09 | High | High | High | Calculate per claim | `High`
C10 | High | High | Medium | Calculate per claim | `Medium`
C11 | High | Medium | High | Calculate per claim | `High`
C12 | High | High | High | Calculate per claim | `High`
C13 | High | High | High | Calculate per claim | `High`
C14 | Medium | High | High | Calculate per claim | `High`

### Existing-Core Probe Facts

These rows transcribe only facts present in the existing core audit. `Not
recorded in audit` marks every missing granular fact; it does not mean that the
behavior was tested and absent.

ID | redirect chain | response status | recognizable first-party content | login/paywall indications | observed technical restriction | probe evidence level
--- | --- | --- | --- | --- | --- | ---
C01 | Not recorded in audit | `200` | Title `巨潮资讯网` | Not recorded in audit | Not recorded in audit | `High`
C02 | Not recorded in audit | HKEX and HKEXnews routes returned `200` | HKEXnews title observed | Not recorded in audit | Not recorded in audit | `High`
C03 | Not recorded in audit | `200` | Not recorded in audit | Not recorded in audit | Not recorded in audit | `High`
C04 | Not recorded in audit | `200` | Not recorded in audit | Not recorded in audit | Not recorded in audit | `High`
C05 | Not recorded in audit | `200` | Title `国家金融监督管理总局` | Not recorded in audit | Not recorded in audit | `High`
C06 | Not recorded in audit | `200` | Title `中国货币网-中国外汇交易中心主办` | Not recorded in audit | Not recorded in audit | `High`
C07 | Not recorded in audit | `200` | Not recorded in audit | Not recorded in audit | Not recorded in audit | `High`
C08 | Not recorded in audit | `200` | Not recorded in audit | Not recorded in audit | Not recorded in audit | `High`
C09 | Root reached final `https://www.hkma.gov.hk/eng`; intermediate chain not recorded | `200` when forced to HTTP/1.1 | Not recorded in audit | Not recorded in audit | HTTP/2 handling was flaky in CLI | `High`
C10 | Not recorded in audit | `403` | Not recorded in audit | Not recorded in audit | Bot/WAF gate from audit environment | `Medium`
C11 | Not recorded in audit | `200` | Not recorded in audit | Not recorded in audit | Not recorded in audit | `High`
C12 | Final locale page observed; exact chain not recorded | `200` | Not recorded in audit | Not recorded in audit | Not recorded in audit | `High`
C13 | Not recorded in audit | `200` | Not recorded in audit | Not recorded in audit | Not recorded in audit | `High`
C14 | Not recorded in audit | `200` | Stock portal title observed; exact title not recorded | Not recorded in audit | Not recorded in audit | `High`
