# AKShare＋官方AKTools取数

本项目新增行情、财务表、券商研报和公司公告取数默认使用AKShare，经官方AKTools调用。已绑定的本地证据优先复用；AKTools负责获取结构化数据，原发布者和原文决定证据等级。正式filing/event/counterpart/market证据仍遵守既有manifest、AS_OF和在线重验契约。

## 1. 最短取数流程

1. 按ticker、AS_OF、所需字段和报告期检查已绑定证据及共享artifact。完整且仍符合调用方重验要求时直接复用，不因进入新section重复联网。
2. MCP服务名为`aktools`，工具为`search_interfaces`、`describe_interface`、`get_data`。首次使用某接口或版本变更时先读`describe_interface`；不确定接口名时才搜索。已核验的同版本参数可在同次研究内复用。
3. 使用真实工具schema传参，接口参数值使用字符串。显式指定证券、日期窗口、周期和复权口径；不要依赖接口默认示例股票、过时年份或远期结束日期。A股六位代码、港股五位代码须按具体接口转换，不统一硬套一种格式。
4. 一次拉取所需表或时间窗口，再在本地筛选财年、去重、计算，并供多个section共享。保存结果和取数元数据到既有共享artifact位置，沿用run-store的绑定与所有权规则。
5. 接口缺失、技术失败或覆盖不足时，记录已尝试接口、参数和错误，简短告警后自动为未解决字段切换其他渠道，不等待用户确认、不停下不依赖该字段的研究。空结果不能证明没有公告、没有研报或没有风险。

`source-discovery`内，此流程是当前适用路线的获取方式，不新增planner layer、不改route authority、不绕过inventory receipt、candidate gate或ledger；先前已接受的claim不重查。iFinD和收费数据服务不是本流程的前置条件。

## 2. 接口种子

下列接口及参数已与本地AKTools 0.1.4 / AKShare 1.20.27目录核对。实际返回列、单位和覆盖范围须读当前描述及结果；不保证每个上游在每次请求时可用。

| 需要的数据 | 接口 | 参数示例与注意事项 |
|---|---|---|
| A股历史行情 | `stock_zh_a_hist` | `symbol="600519"`, `period="daily"`, `start_date="20241008"`, `end_date="20241011"`, `adjust=""`；估值用实际成交价，不用前复权价 |
| 港股历史行情 | `stock_hk_hist` | `symbol="00700"`，其余日期/周期/复权参数同描述；币种、成交量单位重新核验 |
| A股三大财务报表 | `stock_financial_report_sina` | `stock="sh600519"`, `symbol="资产负债表"`；利润表、现金流量表各取一次。可返回多个报告期，须本地筛选 |
| A股主要财务指标 | `stock_financial_analysis_indicator_em` | `symbol="600519.SH"`, `indicator="按报告期"`；年度、YTD与单季度分开，不以第三方ROE替代本项目公式 |
| A股个股券商研报 | `stock_research_report_em` | `symbol="600519"`；按返回日期过滤AS_OF，盈利预测列名可能随年份变化；个股列表不代表行业研报全集 |
| A股公司公告 | `stock_zh_a_disclosure_report_cninfo` | `symbol="600519"`, `market="沪深京"`, `start_date="20261001"`, `end_date="20261105"`；可加`keyword`、`category`，研究时替换为真实窗口 |
| 按日/类别发现公告 | `stock_notice_report` | `symbol="财务报告"`, `date="20261031"`；这里`symbol`是公告类别，不是证券代码 |

港股财务数据、行业研报、宏观、汇率和其他市场先搜索当前目录并读描述；不得把A股接口或参数外推到港股、US或全市场。US法定财报以SEC原文为准，不通过A股接口取数。

### MCP示例与分页

调用`get_data`的工具参数示例：

```json
{
  "name": "stock_zh_a_disclosure_report_cninfo",
  "params": {
    "symbol": "600519",
    "market": "沪深京",
    "start_date": "20261001",
    "end_date": "20261105"
  },
  "max_rows": 100,
  "offset": 0
}
```

AKTools 0.1.4默认返回100行，`max_rows`最多1000；数据对象包含`total_rows`、`offset`、`returned_rows`、`truncated`、`columns`、`rows`。原始MCP响应中该对象可能位于`structuredContent.result`，文本块也包含JSON；先识别真实响应结构再取字段。`max_rows`只限制工具输出，不减少上游取数。需要完整窗口时按`offset + returned_rows`续取，核对总数和日期范围；首屏不能当作完整结果。`offset=-20`只在已确认日期升序时用于末尾20行，不能假定所有接口排序相同。stdout MCP模式的`csv_url`为空，不拼造本地HTTP下载地址。

## 3. MCP尚未载入时的本地备用调用

先检查工具是否暴露；当前会话没载入`aktools`时，直接使用已安装的隔离环境，不因等待重启而停下取数，不重复安装，也不启动额外HTTP服务。

本机Python路径：`/Users/brian_huang/.local/share/uv/tools/aktools/bin/python`。
路径不存在时用`uv tool dir`定位环境；环境不可用才记录失败并走对应来源。

```python
from aktools.core.catalog import describe_interface
from aktools.core.fetch import fetch_dataframe

name = "stock_zh_a_disclosure_report_cninfo"
params = {
    "symbol": "600519",
    "market": "沪深京",
    "start_date": "20261001",
    "end_date": "20261105",
}
description = describe_interface(name)
if description is None:
    raise ValueError(f"接口不存在: {name}")
df, cache_status = fetch_dataframe(name, params)
print(df.to_json(orient="records", force_ascii=False, date_format="iso"))
```

`fetch_dataframe`返回完整DataFrame和`hit/miss`缓存状态，适合批量取数与本地计算；这是本地Python调用，不能报告为当前聊天已成功调用MCP。AKTools core属于已安装版本的实现接口，升级后先核验签名；必要时调用同一环境的官方`akshare`函数。不要为了走项目尚未就绪的`src/ah_research`数据层增加依赖。

### 渠道失败后的自动fallback

- **仅MCP会话/工具不可用**：使用上述本地Python通道。重启客户端不是继续研究的前置条件。
- **AKShare接口或上游来源不可用**：本地Python与MCP通常访问同一上游，不能把重复调用记作另一条独立证据路线。按已有重试限制记录错误后自动切换同功能来源：公告/财报走交易所、巨潮或发行人IR原文；研报走券商官网、其他合法分发渠道及引用追踪；行情/指标搜索其他适用数据接口或原发布者。某个AKShare来源失效时可使用另一来源的接口；整个AKShare/AKTools环境不可用时直接走现有下载器、官方来源或网页路线。
- **接口成功但字段、期间或市场覆盖不足**：保留已获得且通过核验的部分结果，只为缺口执行其他路线。不得以存在一个研报列表接口为由删除行业研报、港股研报或其他原有发现路线。
- **告警内容**：说明失败渠道、实际原因、受影响范围和正在使用的替代渠道，例如“AKTools公告接口超时，正在改用巨潮官方查询；其他已核实数据继续使用”。告警是进度通知，不是停工点。完成取数后记录最终使用渠道与未解决限制。
- **所有适用渠道仍不可用**：按原有ledger、manifest及state mapping记录`blocked/conflict/exhausted`，限制仅影响依赖该数据的结论；继续其他工作。需要凭证、付费授权或非公开资料时才把具体缺口交给用户，不绕过访问控制。

这些替代渠道始终受AS_OF、原文核验、来源等级和现有planner当前层/同功能fallback规则约束；切换获取方式不降低证据要求。

## 4. 研报和公告原文

- **券商研报**：列表用于定位。下载实际返回的`报告PDF链接`，核验HTTP结果、PDF签名和报告首页的券商、标题、日期；读取所用页和表格后才能引用正文。URL可能由接口构造，返回链接不等于下载成功。署名券商是作者，东方财富是分发通道；盈利预测、目标价、评级不是公司已披露事实，不能作行业数据或审计原值。
- **公司公告**：巨潮接口的`公告链接`通常是详情页，不是直接PDF。沿详情页或已核验的巨潮查询响应获取真实`adjunctUrl`，在`static.cninfo.com.cn`解析原文URL；不根据公告ID或日期猜PDF文件名。调用前读取[cninfo.md](site-guides/cninfo.md)中的当前查询路线。保留发行人、公告ID、时间、标题、原文URL及更正/替代关系。正式年报选择和监管事件判定仍交给`read-filing`及已有脚本。
- **时间边界**：公告和研报必须在AS_OF前发布；报告期末日不等于披露日。今天取到的历史财务表可能含AS_OF后更正或重述值，未经历史版本核验不得用于历史时点结论。

## 5. 结果与证据

沿既有artifact/schema记录接口、原始参数、包版本、取数时间、上游发布者/来源URL、原始结果文件及SHA-256、返回总数、消费范围、币种、单位、报告期/交易日、发布日期、复权与会计口径。格式化、换算或计算结果另存转换规则，不覆盖原值。与已绑定证据冲突时保存差异并核对原文，不能静默覆盖。

结构化财务表用于提速和交叉检查；目标公司审计结论所用数值仍来自bound annual/counterpart的选中经审计报表。价格和汇率用于最终估值时仍须market manifest绑定及重验。费用免费、接口调用成功或多条同源转载都不能提高事实的证据等级。复用缓存不免除发布前的既有在线重验。

截至2026-11-05已实测：茅台券商研报列表与一份6页国信证券PDF、巨潮公告列表与一份12页三季报PDF，均可下载并提取文本；另有A股日线与交易日历样本。其他接口种子仅完成目录核对，不能标成已实测或完整覆盖。
