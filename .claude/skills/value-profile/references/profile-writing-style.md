# Profile中文写作与术语规则

本文件在写Part 0和Part 1-5前读取。目标是让profile像中文研究文档,而不是英文分析的直译。

## 1. 英文缩写白名单

正文仅保留业内已普及的缩写:

- 估值指标:ROE/ROIC/ROA/DCF/PE/PB/PS/PEG/EV/EBITDA
- 时间和比率:CAGR/YoY/QoQ/TTM
- 用户指标:MAU/DAU/ARPU/LTV/CAC
- 集中度和规模:CR5/CR10/GMV
- 宏观和合规:GDP/ESG/IPO/A股/H股/SKU
- 管理和指标:KPI/OKR/ABT

白名单外的英文默认翻成自然中文。没有固定译法时使用描述性短句,不得保留生硬英文或自造缩写。

## 2. 常用术语

| 英文 | 中文 |
|---|---|
| CFO/NI/CapEx/FCF | 经营现金流/净利润/资本开支/自由现金流 |
| NOPAT/WACC | 税后经营利润/加权平均资本成本 |
| TAM/SAM/SOM | 潜在市场规模/可服务市场规模/实际拿下市场规模 |
| SG&A/COGS | 销售管理费用/营业成本 |
| DSO/DPO/DIO | 应收/应付/存货周转天数 |
| framework/guidance | 框架/指引 |
| checklist/summary/scope/benchmark | 清单/摘要/范围/基准 |
| actual/forecast/narrative/reference | 实际/预测/叙述/参考 |
| bear/base/bull case | 悲观/中性/乐观情景 |
| stakeholder/SOE | 利益相关方/国企 |
| product/channel/revenue mix | 产品/渠道/收入结构 |
| red flag/green flag | 风险信号/积极信号 |
| M&A | 并购 |

## 3. 状态词

template是状态词的唯一来源。常见误译按下表修正:

| 不使用 | 使用 |
|---|---|
| clean/清洁 | 无触发/零触发项/合规 |
| clean audit/干净审计 | 标准无保留审计意见 |
| healthy/健康 | 财务稳健/结构稳健 |
| risk-free/无风险 | 未识别重大风险 |
| green flag/绿灯 | 积极信号/正面信号 |
| red flag/红旗 | 风险信号/警示项 |

若需要新增状态词,先修改template schema,不得在单个profile中临时创造。

## 4. 证据进度的自然中文

用户可见中文不得使用“闭合”描述证据、调查、结论或问题状态。`close/closed/closure`
是内部流程概念，写入profile、子skill报告或控制台摘要时必须按具体语义改写：

| 英文或内部含义 | 用户可见中文 |
|---|---|
| evidence complete / closed | 证据完整 / 已核实 / 已完成判断 |
| partially closed | 已核实部分信息 / 部分完成 |
| not closed | 证据仍不完整 / 仍缺资料 / 尚不能判断 |
| close a gap | 补齐资料 / 完成核验 / 处理完这个问题 |

不要机械替换成同一个词。事实已经查清用“已核实”；检查流程已经做完用
“已完成判断”；关键材料缺失用“仍缺资料”或“尚不能判断”。说明还缺什么时，
直接写明缺少的资料或尚未完成的核验，不使用抽象的流程术语。

## 5. 情景和敏感性测算的自然中文

用户可见的敏感性分析要按“假设、结果、限制”来写：

1. 说明这是**按明确假设简单测算**，并写出被调整的变量。
2. 给出**计算结果**及其对利润、现金流或估值的具体影响。
3. 列出关键**未考虑因素**，并说明结果**不是预测**，也不代表公司实际应当采用该假设。

英文中的`mechanical`通常表示只按公式计算、其他条件保持不变。中文应直接交代
假设和限制，不用带有“机械”的组合词代替说明。

## 6. 隐藏机器引用元数据

`机器引用清单`用于AI恢复、证据追踪和一致性校验，不是面向读者的正文。最终
profile必须把每节清单写入HTML注释，同时保留原标记：

```markdown
<!-- **机器引用清单:** `C25-IP`、`C25-CF`。 -->
```

普通的`**引用:**`和`**置信度:**`继续显示。不得删除机器引用，也不得把清单移出
对应section。

## 7. 层级收入表

同一分类维度含父子关系时，使用三列层级明细表，不把每个层级横向展开：

```html
<p class="table-heading">
  <strong>按业务划分</strong>
  <span class="table-meta">YYYY年 · 亿元</span>
</p>
<table class="hierarchy-table">
  <thead>
    <tr><th>收入类别</th><th>收入</th><th>占总收入</th></tr>
  </thead>
  <tbody>
    <tr class="hierarchy-group"><td>父项</td><td>100.00</td><td>100.0%</td></tr>
    <tr class="hierarchy-subtotal">
      <td class="hierarchy-level-2">二级子项</td><td>80.00</td><td>80.0%</td>
    </tr>
    <tr>
      <td class="hierarchy-level-3">三级子项</td><td>50.00</td><td>50.0%</td>
    </tr>
    <tr class="hierarchy-total"><td>合计</td><td>100.00</td><td>100.0%</td></tr>
  </tbody>
</table>
```

规则：

- 表题右侧统一写`报告期 · 金额单位`，金额列只保留数字。
- 固定使用收入类别、收入、占总收入三列。
- 父子关系通过首列的`hierarchy-level-2`或`hierarchy-level-3`缩进表达。
- 金额和占比分列，不写成`金额 / 占比`。
- 不使用每层单独一列、`rowspan`、数字层级列或占位短横线。
- 产品、渠道、地区等交叉维度分表展示，并说明能否跨表相加。

## 8. 行业bundle固定块

行业章节只按已校验的`industry_bundle.status`写作，不从来源数量、段落是否写完
或叙述语气推断证据状态。固定块按下列逐行名称和顺序输出，不得合并或改名：

市场定义矩阵
历史市场规模与逐年增速
预测版本对照
集中度与竞争对手
当期部分期间
口径断点与未解决缺口

接受无歧义的industry bundle `schema_version: 1.0`作为向后兼容输入；新运行使用
`schema_version: 1.1`。v1.1的`market_definition_fingerprint`不含metric，
每个series另保留metric、unit、measurement basis和denominator对应的
`series_fingerprint`。每张数值表逐行显示两个fingerprint、`channel_scope`、
`denominator`、计量口径、提供方和lineage。机器引用属于同一表的证据记录，
但必须紧跟该表写入`机器引用清单`HTML注释，不得显示在渲染正文中。预测发布日期
和`data_vintage`是证据日期，不是forecast horizon；每个`data_vintage`单独
渲染一个series，严禁跨vintage拼接。

最后一块另保留角色状态、逐claim的`claim_states`、缺失期间、
`missing_coverage`、ledger path、终态路由状态和下一步所需证据。
`claim_states`逐claim独立终止；accepted claim不得重新进入`unresolved_claims`
或重派。`partial`和`blocked`必须保留已接受evidence、periods和series，再单列
未覆盖内容。

所有数值表只从validated `accepted_candidates`填值；`industry_bundle`只决定
role状态、缺失期间和口径断点。历史块中的`行业驱动因素`子表只渲染
`industry-drivers` role的accepted evidence。

缺口行按机器字段直接映射：

- 口径断点依次取`scope_breaks[].from_scope_fingerprint`、
  `scope_breaks[].to_scope_fingerprint`和`scope_breaks[].reason`。
- route终态逐项取对应`ledger.attempts[].terminal_reason`。
- `blocked`先取`ledger.next_escalation`,为空时列出
  `ledger.unattempted_routes`。
- `exhausted`且没有下一route时写
  `new publication/data release required`。

状态写法：

- `complete`：正常填写六个固定块。
- `publishable-with-gaps`：保留已接受值，逐年列出缺失期间、终态路由状态和下一步
  所需证据，并继续profile。
- `blocked`：保留已接受值，逐route列出阻断状态，把行业章节标为需要人工跟进，
  不得把阻断或未取得资料写成事实不存在。
