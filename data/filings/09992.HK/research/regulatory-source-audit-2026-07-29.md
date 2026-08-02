# 泡泡玛特监管事件来源审计

- 标的：`09992.HK`
- 截止日：`2026-07-29`
- 上市日：`2020-12-11`
- 调查方式：普通 HTTP；未使用 Chrome/CDP
- 结论：已建立部分官方来源的请求契约，但不满足严格 event manifest 的完整性要求，不能据此声称“未发现监管事件”。

> 2026-07-31补充调查已完成历史主体名册、345份HKEX发行人文件日期拆窗枚举、68个月HKPF XML及HKLII替代检索，并确认四项内地经营合规处罚和金鹰诉讼。严格event manifest仍因HKJD、无稳定主体ID的监管源和事件法律字段而保持未闭合。完整查询词、URL和证据边界见`regulatory-followup-2026-07-31.md`。

## 官方来源

| 来源 | 已验证请求与结果 | 证据等级 | 未闭合项 |
|---|---|---|---|
| HKEX | `GET https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_e.json` 将 `09992` 映射至 `stockId=1000068054`。`GET https://www1.hkexnews.hk/search/titleSearchServlet.do`，参数包括 `market=SEHK&stockId=1000068054&fromDate=20201211&toDate=20260729&rowRange=1&lang=EN`，返回 `recordCnt=331`、`loadedRecord=1`、`hasNextRow=true`；限定 `title=ANNUAL REPORT` 返回6条。 | 高 | `rowRange` 是累计截断，不是页码；需按日期递归拆窗。结果缺主体角色、法律效力和事件状态。 |
| SFC | `GET https://apps.sfc.hk/sfc/search`。以 `action=query&start=1&maxresults=10&databasematch=SFC&responseformat=JSON&totalresults=true&printfields=title,content` 查询；`"market misconduct"` 返回22条，`"Pop Mart"`、`"Wang Ning"`、公司英文全称和`09992`均为0。 | 接口高；否定结论不足 | 全站全文索引没有发行人代码或主体ID；零结果不能覆盖别名、历史人员或发行人关系。 |
| AFRC | `GET https://www.afrc.org.hk/en-hk/search?keyword=PricewaterhouseCoopers&page=1` 显示16条并可到第2页；`keyword=Pop%20Mart` 无结果。另核验 `https://www.afrc.org.hk/en-hk/key-functions/discipline/disciplinary-cases`。 | 中 | HTML来源；无稳定记录ID、结构化总页数或完整具名未结调查登记册。 |
| HKPF | `GET https://www.police.gov.hk/app/php/press_release.php?lang=en&month=202501` 返回50条 XML；另核验`202401`为38条、`202312`为50条。 | 高 | 无发行人或人员查询参数；必须枚举全部月份并本地匹配，当前采集器不支持 XML。 |
| ICAC | `GET https://www.icac.org.hk/en/p/press-archive/index.html?query=Pop%20Mart`；分页为`index_p2.html?query=<term>`。`Pop Mart`、`Wang Ning`和`09992`无结果；`query=bank`显示101页。 | 中 | HTML来源，无机器可读总数、发行人ID、主体角色或法律状态。 |
| HKJD | 入口 `GET https://legalref.judiciary.hk/lrs/common/index.jsp?target=judgment&lan=en`；目标检索页为`/lrs/common/search/searchbox_result.jsp`。携带页面签发 cookie 后，`bank`与`Pop Mart`检索仍返回 HTTP 500。 | 未建立 | 数据库值、隐藏状态、结果字段、总数和分页契约均未验证。 |

## 严格 manifest 阻断

1. HKJD 是强制来源，但尚无成功、可重放的查询契约。
2. HKPF 为 XML，AFRC/ICAC 为 HTML，HKEX 为累计截断；当前采集器只支持页码化 JSON。
3. SFC、HKPF、ICAC和HKJD没有稳定发行人或人员ID，名称检索不能证明覆盖别名和历史人员。
4. 多数官方结果缺 builder 要求的事件状态、法律效力、发生时角色和发行人关系。
5. 历史董事、高管、控制人和审计师任期名册已从HKEX招股书、年报和任免公告重建，但HKEX没有单一官方历史人员API，因此仍属于官方文件重建名册，不是可直接重放的官方roster响应。

因此，上述零命中只能表述为“对应查询未命中”，不能升级为“上市以来官方全集未发现事件”。
