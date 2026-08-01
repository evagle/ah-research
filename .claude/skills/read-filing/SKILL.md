---
name: read-filing
description: Use when a user asks to read,梳理,解读,or extract evidence from a complete Shanghai/Shenzhen A-share or HK annual report,including requests such as "读年报600519.SH","读财报0700.HK",or "/read-filing 600519.SH 2024".
---

# Read Filing Skill

本skill是value-profile体系的**阅读层**子skill。v1仅支持完整年度报告。它回答:**"这份上市公司年报应该怎么读、按什么顺序读、每一段读出什么?"**允许执行预先定义的机械阈值比较和初筛特征标签,用于决定是否继续取数;这些结果不构成最终风险、护城河或投资结论。最终判断由`financial-redflag-scan`/`management-analysis`/`value-profile`完成。

**交易所无关**: 本 skill 的 §1原则 + §2规则 + §3流程适用于沪深A股和港股。**结构差异在 reference**: 具体年报节次地图/披露时限见 `references/filing-structure-cn.md` (A 股) 或 `references/filing-structure-hk.md` (港股); 术语/公式/阈值速查见 `references/quick-lookup.md`。方法论来源: 各交易所监管披露规则 + 中文价值投资财报阅读教材 + 本项目前序 skill 的实战沉淀。

**覆盖边界**:港股仅支持当前上市发行人;已退市港股发行人超出当前下载器和官方目录适配范围,不得声称可完成同等证据闭环。

**共享证据契约**:运行前必须完整读取`.claude/skills/read-filing/references/evidence-contract.md`。身份、AS_OF、manifest绑定、引用、Mode B写入权、终态和证据漂移只以该文件为准;本skill只补充年报阅读特有规则。

**共享运行契约**:运行前必须完整读取`.claude/skills/read-filing/references/run-store-contract.md`。共享目录、run隔离、无感resolver、Mode边界和旧路径兼容只以该文件为准。

### source-discovery handoff

`source-discovery`只补充官方交易所证据链之外的同行与行业背景。

`source-discovery` must be invoked only for peer/industry context and source search that is outside the official exchange filing/event evidence pipeline.
`read-filing` remains the authority for exchange filing selection, official event source discovery, manifest construction, source preflight, and Mode B evidence binding.
`source-discovery` cannot choose annual reports, replace official event sources, weaken live revalidation, or write profile sections.

## §0运行模式

### Mode A — Standalone

- **Invocation**:`/read-filing <ticker> [YYYY] [--as-of YYYY-MM-DD] [--complete-facts]`;YEAR可省略,省略时解析为交易所已披露的最新完整财年。只有用户明确要求“完全重新分析”时内部resolver使用`--clean`
- **行为**: 子 skill 独立完成 ticker 验证 → filings audit → PDF 抽取 → 10节骨架遍历 → 三表勾稽 → 附注12项深读 → 主 agent 复核 → 写 standalone 阅读笔记
- **Output path**:`data/filings/<ticker>/runs/<run-id>/report.md`—200-400行结构化笔记
- **典型场景**:用户要系统读一家公司完整年度报告,但尚未决定做完整value-profile;或想在做profile前先过一遍年报获得基础笔记

### Mode B — As-subroutine

- **Invocation**:主`value-profile`/`financial-redflag-scan`/`management-analysis`传参`--target-profile <path> --section <part_id/section_id> --ticker <ticker> --year <YYYY> (--filing <absolute-pdf-path>|--extracted-text <absolute-text-path>) --as-of <YYYY-MM-DD> --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> [--counterpart-filing-manifest <exchange>:<absolute-json-path>]... --auto|--interactive [--complete-facts]`;`--filing <absolute-pdf-path>|--extracted-text <absolute-text-path>`二者恰好提供一个
- **行为**:Mode B始终执行完整事实提取。AS_OF是统一信息截止日。filing manifest必须按交易所官方目录枚举每个财年的全部候选公告,不能仅列选中版本。所有候选必须有官方URL、报告类型、有效状态和替代关系,并包含财年、报告期末日、完整公告时间戳、公告顺序ID、公告ID或官方URL、公告标题和是否选中;只有选中完整年报必须有绝对路径和SHA-256,未选中候选保留官方URL且本地字段可为null。撤销或更正通知的报告期末日写`不适用`。manifest顶层还要保存官方目录查询URL、查询参数、响应哈希、官方结果总数和候选总数,以证明候选集合完整。event manifest必须覆盖管理层、实控人及发行人上市以来全部欺诈、操纵股价、内幕交易、虚假陈述和财务造假正式处罚或生效纪律处分,以及上市以来全部已证实的大股东资金占用、违规关联交易和股东利益输送;另覆盖AS_OF前3年的审计机构变更、审计机构监管调查、年报重大更正重述、实控人刑事立案、年报逾期披露和其他监管事件。每类查询保存官方查询URL、查询参数、响应哈希、结果总数及命中结果或`未检出`。仅列选中版本、manifest缺失或不连续、字段冲突、选中路径不存在或哈希不符时abort。完成Mode B source preflight后进入Step 2,L1至L3命中只写入`screening_flags`,不得缩小目标事实范围
- **Output**:只返回一个结构化对象,至少包含`"facts"`、`"citations"`、`"warnings"`、`"filing_manifest_sha256"`、`"event_manifest_sha256"`、`"counterpart_filing_manifest_sha256s"`和兼容字段`"source_manifest_sha256"`。目标section由`--target-profile`+`--section`唯一确定,但本skill不得直接替换或写入任何profile section;父skill复核返回对象后决定是否落盘
- **运行边界**:Mode B不调用run store，也不创建run；所有结果只存在于返回对象
- **典型场景**: 主 value-profile 进入 Step 3前先跑一遍本 skill 为各 section 积累基础事实清单

### Invocation 解析

- 仅ticker或ticker+年份→Mode A;YEAR省略时先查交易所披露目录,取已正式披露的最新完整财年,不得用当前自然年猜测
- 含`--target-profile <path>`→Mode B;必须同时提供Mode B列出的全部参数,任一缺失即报契约错误
- `--complete-facts`在Mode B中仅为兼容参数;无论是否传入,Mode B都执行完整目标事实提取
- Mode A固定YEAR和AS_OF后，先在系统临时目录实际构造并验证候选annual、event及全部counterpart manifest，把候选manifest的真实SHA-256作为输入artifact，并追加官方目录响应哈希和query plan哈希，再调用`financial_run_store.py resolve`。不得用待建立占位值计算输入指纹；`resumed`继续未完成步骤，`reused`直接返回已完成报告，`created`写入新run，不得要求用户选择resume、新run或run ID
- Ticker按交易所验证:沪深A股使用`\d{6}\.(SH|SZ)`,港股使用`\d{1,5}\.HK`。港股代码立即左补零为五位,后续路径、manifest、查询参数和输出只使用canonical ticker
- 年份正则:`^(19|20)\d{2}$`,不接受`2024H1`等组合。v1仅支持完整年度报告,拒绝`--quarterly`和`--halfyear`;收到中报或季报请求时明确说明当前下载器不支持并停止,不得伪装成年度报告流程
- `YYYY`统一指**财务报告期结束日所在公历年**,不是标题中出现的第一个年份。港股`Annual Report 2024/25`归入2025财年;标题年份只能作为候选线索,必须以HKEX公告元数据中的报告期末日及报告封面或财务报表期末日交叉复核,任一冲突即abort

### 运行时必读 reference

1. `references/reading-principles.md` — 长期阅读信念、证据层级、归母口径、所有者利润和财报形态初筛。派任何子agent前主agent必须完整读取。
2. `references/statement-reading.md` — 阅读顺序/资产负债表5分类 + 反直觉规则/金融资产4分类新准则/附注必读12项/利润表八大指标三档/特殊场景加读清单。子 agent 开工前主 agent 先 Read 这份。
3. **按 exchange 二选一** (主 agent Step 1根据 ticker 后缀选):
   - A股 (`.SH` / `.SZ`) → `references/filing-structure-cn.md` — 证监会第2号准则10节结构 + 季报披露时限 + 业绩预告
   - 港股 (`.HK`) → `references/filing-structure-hk.md` — HKEX Main Board Appendix 16章节结构 + 中报披露时限 + profit alert
4. `references/quick-lookup.md` — 术语/时间预算/新准则 / CFO 画像/所有者利润速算/自检 / 20条反模式。生成事件query plan前还必须完整读取`references/event-source-discovery.md`,按真实官方请求发现并验证source contract。
5. `../financial-redflag-scan/references/fraud-library.md` — 风险10项 + 三表勾稽4条公式 + 5维度造假手法 + pattern 叙述。Step 5勾稽时必读

## §1阅读原则

长期信念层已移至`references/reading-principles.md`。主agent在派任何子agent前必须完整读取并内化;§2规则与§3流程均以该reference为前提,不得只凭本节摘要执行。

## §2阅读规则（从 §1推出的操作纪律）

本节规则编号 `§2.N.x` 可追溯到原则 `§1.N`。规则给**框架**，不给详细阈值清单（详细阈值留在 `references/statement-reading.md` 和 `financial-redflag-scan/references/fraud-library.md` 的29项 + 6项附加检查）。

### §2.1排除优先（§1.1推出）

- **§2.1.1三级早退规则**: 任一条触发立即写短报告退出，不花后续时间：
  - **L1审计红线**:保留意见、无法表示意见或否定意见/会计师事务所近3年内变更过≥2次/事务所被证监会、SFC、HKEX或财政部正式立案调查。无保留意见中的强调事项段本身不触发L1,只按其底层事项的独立规则处理
  - **L2前提失效（A股非银行）**:CFO/归母NI<50%、销售收现比<0.9或扣非归母NI/归母NI<0.5中任一指标分别连续2个适用财年触发。0.9≤销售收现比<1.0只进入深查,不早退。银行不使用销售收现、常规CFO/NI或扣非净利润早退,改由银行10行替代bundle继续取证,不得因此提前停止附注事实提取
  - **港股L2**:连续2年CFO/NI<50%可触发;港股报表不强制扣非净利润或销售商品收到的现金,缺少这两项时改做应收账款、合同负债、收入和经营现金流桥并标`需下游复核`,不得因未披露A股特有字段早退
  - **L3重大违规**:近3年收到证监会/交易所正式处罚（非询证函）/实控人被刑事立案/年报重大更正重述/超过法定期限仍未披露年报
- **§2.1.2触发早退=标笔记"**早退事实报告**"**:只有L1-L3允许早退。普通调用只返回早退触发事实并停止深读;`--complete-facts`则保留触发事实并返回全部事实:在早退节点先只返回早退触发事实并继续完整事实提取,最终汇总全部事实,风险定性仍移交redflag-scan

### §2.2阅读顺序硬性（§1.2推出）

阅读**抽象顺序** (跨交易所通用, 先排除后肯定, 先客观证据后管理层口径):

1. **封面/公司资料 + 重要提示** (2 min) — 期末日/审计机构/是否变更/审计意见类型/董事保证声明/重大风险
2. **审计报告** (5 min) — 意见段 + 关键审计事项 (KAM) / 审计师保留事项
3. **财务摘要 / 5年财务摘要** (5 min) — 主要财务数据 + 5年趋势
4. **资产负债表** (10 min) — 结构速览 (5分类框架见 `statement-reading.md §2`)
5. **利润表** (10 min) — 营收、成本、费用、净利结构
6. **现金流量表** (10 min) — CFO / CFI / CFF 三大类 + CFO/NI 背景
7. **权益变动表** (3 min) — 分红/增发/回购/股权激励痕迹
8. **财务报表附注** (60-120 min) — 12项必读 (见 §1.5 + `statement-reading.md §3`) + 会计政策变更 + 会计估计变更
9. **回头读管理层讨论 (MD&A)** (20 min) — 对照前面8步验证管理层口径
10. **治理 + 重要事项/关联交易/诉讼/担保/承诺履行** (20 min) — 治理结构/独立性/是否被监管问询
11. **股东变动 + 董监高持股/套现** (10 min)
12. **审计师/会计政策变更** 补扫 (5 min) — 变更原因 + 影响金额单独落笔

**具体章节名映射 (按 exchange 查 reference)**:
- A股 → `references/filing-structure-cn.md §1` 给出第 N 节 ↔ 抽象步骤的映射
- 港股 → `references/filing-structure-hk.md §1` 给出章节标题 ↔ 抽象步骤的映射
- 港股特别注意:按发行人实际披露的治理结构读取监督材料;若年报披露监事会,读取监事会报告,A+H发行人不得按港股标签跳过;未披露时改查独立非执行董事、审计委员会和Corporate Governance Report。**母公司报表不强制披露** (§1.4合报 >> 母报对港股只看合报); **前5大客户 + 供应商强制披露** (董事会报告段, A 股通常没有)

**步骤9回读管理层讨论 (MD&A) 时的6维度对照** — 董事会报告 / MD&A 不是随便读, 按以下结构化清单逐维度对照前8步的实际数据:

| 维度 | 重点看什么 | 对照 |
|---|---|---|
| 发展战略 | 未来3年战略方向 + 重点投向 | 对照 CapEx 结构/在建工程/募投项目 |
| 主营业务分析 | 分产品/分地区/分渠道结构与变动 | 对照利润表营收拆分附注 |
| 行业竞争格局 | 管理层自报的同业 + 竞争优势来源 | 对照同业3家指标；筛出"可比公司"清单 |
| 核心竞争力 | 管理层宣称的护城河 + 佐证 | 对照附注/成本结构/毛利率同业位次 |
| 主要风险 | 管理层主动披露的风险 | 对照上年度"风险" vs 今年实际；有无"目标突然消失" |
| 未来展望/经营目标 | 下年度量化目标（营收 / NI / 产能）| **§1.10承诺 vs 兑现表的第 t 年输入** |

任一维度管理层口径与事实不一致时,笔记单独写一行"管理层说X,附注p.N实际Y→一致/不一致/证据不足",不推断主观动机。

### §2.3利润表三张表联动（§1.3推出）

- **§2.3.1 "利润孤立出现" = 子 agent 退回**: 任何一条关于利润/营收/毛利率的 finding 必须同时包含以下三项背景（否则退回重写）:
  ① 同期经营现金流净额及 CFO/NI 比率
  ② 同期应收账款 + 应收票据变化 + 合同负债变化
  ③ 同期存货变化 + 存货周转天数
- **§2.3.2毛利率变动 > ±3点必须归因**: 归因维度 = 价（提价/降价）× 量（规模）× 成本结构（原材料/人工/折旧）× 产品结构（mix）。四维都说"不变"而毛利率大幅变动 → 存疑，标"**需人工核查**"
- **§2.3.3禁用未扣非净利**: 做 PE / 成长性判断的净利必须是**扣除非经常性损益后的归母净利**。"扣非/非扣非" 差异 > 15% 的年份必须单独列出非经常性损益**明细** + 各项金额（出售资产/政府补助/公允价值变动/税收返还）
- **§2.3.4盈利质量3个交叉指标（随 CFO/NI 一起报）**:
  - **现金转化率 (cash conversion) = 自由现金流/归母 NI**。长期健康 ≥ 90%。< 80% 连续2年 = 盈利质量差，存在应收/存货膨胀或费用资本化
  - **有息负债利息保障倍数 = 营业利润/利息支出**。不只看 "能否偿还" 下限（≥ 3），看"是否稳健优秀"上限（≥ 10）。< 3 → 进入风险观察
  - **ROOCE = 营业利润 / (有形固定资产 + 净营运资本)** — 剥离并购商誉/无形资产后的真实经营资本回报率。与常规 ROE 同时报，**商誉/净资产 > 10% 的公司**两者背离 = 判断经营 vs 并购贡献的关键口径
  - **非正分母**:营业收入≤0时不计算销售收现比;归母净利润≤0时不计算现金转化率;利息支出≤0时不计算利息保障倍数;有形固定资产+净营运资本≤0时不计算ROOCE;同期累计归母净利润≤0时不计算非经项目占比、CapEx/NI或有息负债/净利润。均改列分子、分母的符号和绝对金额并标`不适用—分母非正`,交下游复核
- **§2.3.5识别 "一次性" 费用的连年模式**: 重大资产减值/重组费用/诉讼准备/商誉减值等被管理层标 "非经常性" 的项目, 若**近5年出现 ≥ 3次** → 视为**经营性成本**, 必须加回利润表, 重算"正常化利润"。单独列一段 "过去5年非经常性损益明细" 表, 每行金额 + 年度 + 附注页码

### §2.4合报口径默认，母报用于校验（§1.4推出）

- **§2.4.1笔记默认口径 = 合报 + 归母**: 凡写"净利润"默认指"归母净利润"；写"净资产"默认指"归母净资产"。出现"合并口径"需带一句说明为什么这里用合并
- **§2.4.2母报使用场景限制**: 母报只在以下3个场景引用：
  1. 判断集团层面的资金占用/对子公司的往来款
  2. 判断分红能力（上市公司本部的未分配利润 + 资本公积才是分红来源）
  3. 交叉验证"上市公司 vs 控股股东"的利益输送
- **§2.4.3少数股东损益/权益变动 > ±30% 必须解释**: 通常来自 (a) 并购/处置子公司；(b) 子公司业绩大幅变化；(c) 少数股东增减持子公司股权。任一都要引用当年相关重大事项公告

### §2.5附注逐行深读（§1.5推出）

- **§2.5.1 12项必读附注100% 覆盖**: 子 agent 输出的 §附注 section 必须12项都有 entry。任一为空 → 退回重读，或标"本年报该项未披露（含引用页码 + 披露说明）"
- **§2.5.2会计政策变更/会计估计变更单独一节**: 任何一次变更必须记录：(a) 变更名称；(b) 变更原因（引用年报原文）；(c) 对当期 + 比较期的影响金额；(d) 是否导致前期数据追溯重述
- **§2.5.3关联交易附注**:沪深A股按适用交易所规则和公司披露门槛逐笔列示;若采用3000万或净资产0.5%作为筛查线,必须注明具体规则版本和适用性。港股按HKEX Chapter 14A的百分比率、豁免、公告、通函和独立股东批准要求路由,港股不得套用A股3000万或净资产0.5%。每笔列关联方名称、交易类型、金额、定价依据及与市价偏离。
- **§2.5.4金融资产4分类一次性盘点**:按新准则（2018+）每份profile必须列出4个筐子的金额+同比变化:摊余成本（瘫子）/公允价值变动计入当期损益（笋子）/公允价值变动计入OCI债权类（菜粽）/公允价值变动计入OCI权益类（肉粽）。笋子金额大时只记录利润波动中公允价值变动的金额和占比,交下游判断
- **§2.5.5新准则3项 BS 结构变化必须识别**（影响5年纵向可比性）:
  - **新收入准则**（2020+全面施行）:原"预收账款"主体重分类到**合同负债**;履约进度→"按时点/按时段确认收入"。阅读时注意5年比较期数据的**追溯重述**说明;合同负债/营收比值需同业对标。高值检查履约积压和退款义务,不能据此推断提前确认;低值结合收款与履约证据检查提前确认
  - **新租赁准则**（2021+ 全面施行）: 经营租赁原表外，现在须入表：借方 **使用权资产**, 贷方 **租赁负债**。影响重资产租赁密集型行业（零售连锁/航空/物流）的资产负债率、EBIT（折旧增加）、经营性现金流（利息费用 → CFF）
  - **新金融工具准则**（已在 §2.5.4覆盖4分类）
- **§2.5.6权益变动表必看3项**（不只是"扫一下"）:
  - **股权激励**: 授予/行权/归属/作废的 "股份支付费用" 总额 — 判断"隐性稀释股东"成本
  - **回购注销 vs 回购留库**: 前者真正增厚每股价值, 后者只是"回购再释放"工具, 判断管理层股东回报姿态
  - **分红 + OCI 流入/流出**: 其他综合收益 (OCI) 的跨期变动金额 — 金融资产/外币折算/再计量的真实损益波动藏在这里
- **§2.5.7现金流量表 CFO/CFI/CFF 8组合画像**（快速定性判断企业生命周期）:

  | 组合 | CFO | CFI | CFF | 典型画像 |
  |---|---|---|---|---|
  | A | + | − | − | **成熟优质**: 自身造血 → 投资扩张 + 还债分红。典型蓝筹 |
  | B | + | − | + | **扩张期**: 造血 + 举债一起上, 激进扩张, 看 CFI 是否高质量投资 |
  | C | + | + | − | **收缩/转型期**: 主业仍造血, 但处置资产 + 还债, 可能战略收缩或准备退出 |
  | D | + | + | + | **囤现金**: 造血 + 处置 + 举债三方流入, 现金快速堆积, 通常是并购前/行业底部储粮 |
  | E | − | − | + | **初创/激进投入期**: 主业不造血, 靠融资扩张。看未来能否转正 |
  | F | − | + | − | **衰退清算**: 主业不造血, 卖资产还债, 走向清算或重整 |
  | G | − | + | + | **困境续命**: 主业不造血, 靠卖家当 + 借钱硬撑, 极度危险 |
  | H | − | − | − | **极度恶化**: 三头流出, 现金耗尽, 通常进入破产前夕 |

  读5年现金流 → 画5个 ABCDE 组合 → 企业生命周期轨迹可视化。**组合突然切换**（A → E 或 B → G）常比单期 NI 变化更早预警。

### §2.6纵向 + 横向必须成对（§1.6推出）

- **§2.6.1 5年纵向强制**: 任一核心指标（营收/归母 NI / CFO / 毛利率/净利率 / ROE / 资产负债率 / CapEx / 分红率）必须给出5年时间序列或5年 CAGR。IPO 未满5年则用"上市以来全部年度 + 招股说明书披露的3年历史"凑齐，并注明缺失年份
- **§2.6.2同业3家硬性**:财务摘要section必须含"与3家同业的关键指标对比表"。A股同业从年报竞争格局、证监会行业分类和招股说明书可比公司交叉选择。港股同业从年报`Business Review/Industry Overview`、恒生行业分类、上市文件或招股书可比公司选择;不足3家本地同业时补全球同业务上市公司并披露市场/会计口径差异。
- **§2.6.3变动 > ±20% 专章解释**: 任一5年指标中有一年 YoY > ±20% 必须单独写 "原因 + 附注证据 + 是否可持续" 三句
- **§2.6.4杜邦分解 + 5大类指标骨架必须列齐**（至少5年同公司 + 3家同业对标）:
  - **ROE 三项分解**: ROE = **净利率 × 总资产周转率 × 权益乘数**。看 ROE 同业对标时必须同时写三项, 判断 ROE 是**"高利差"** 型（净利率驱动, 如茅台/恒瑞）还是**"高周转"**型（周转驱动, 如沃尔玛/美的）还是**"高杠杆"**型（杠杆驱动, 通常是银行/地产/高风险）
  - **5大类指标骨架**（每份笔记 §2同业对标必须覆盖全5类）:
    1. **盈利能力**: 毛利率/净利率 / ROE / ROA / ROIC
    2. **营运能力**: 总资产周转率/存货周转天数/应收账款周转天数/应付账款周转天数
    3. **偿债能力**: 资产负债率/流动比率/速动比率/利息保障倍数
    4. **发展能力**: 营收 CAGR / NI CAGR / 总资产 CAGR / 净资产 CAGR (3y + 5y 都要)
    5. **现金流能力**: CFO/NI / 销售收现比/自由现金流/现金转化率 (cash conversion)

### §2.7强制页码引用（§1.7推出）

- **§2.7.1数字格式**: `<值> (YYYY 年报 p.N)` 或 `<值> (YYYY 年报 §N.M.K p.N)`。季报引用格式：`<值> (YYYY-QN 季报 p.N)`
- **§2.7.2禁用泛指**: 禁 "资料显示/据披露/大致为/约 / 据 xxx" 作为数字来源——所有这些词要么后接具体来源（URL / 文件名/页码），要么删掉
- **§2.7.3找不到就留白**: 子 agent 找不到数字，写 "**待补充 — <YYYY> 年报/附注未披露/需查 <YYYY>-QN 季报**"，不允许编数字。主 agent 复核时看到这类待补充 → 或派补充子 agent，或把该 section 置信度降到"低"
- **§2.7.4机器可复核引用**:Mode A和Mode B共用三分支联合引用契约。`source_type=filing_text`和`source_type=filing_pdf`均含`section_id/source_type/artifact_path/source_pdf_sha256/artifact_sha256/page/quote`;text按page marker验证逐字quote,原文片段必须存在于对应page marker正文;pdf在只读临时目录重抽指定页且`artifact_sha256=source_pdf_sha256`。`source_type=event_document`含`section_id/source_type/event_manifest_sha256/document_url/artifact_path/content_sha256/source_pdf_sha256/artifact_sha256/page/quote`,其中`source_pdf_sha256=null`且`artifact_sha256=content_sha256`,HTML文书page可为null。所有artifact_path均指向最终持久证据且artifact_path不得指向scratch、staging或临时抽取目录;仅有文件名和页码不得通过引用复核。

### §2.8空话过滤器（§1.8推出）

- **§2.8.1 8条禁用空话**: "强大品牌/技术领先/行业龙头/管理优秀/市场广阔/核心竞争力突出/护城河宽广/成长空间巨大" 任一出现在笔记正文 → 退回子 agent 补证据（具体产品/数字/日期/引用）或删除该句。主 agent 自己也受此约束
- **§2.8.2管理层原话 vs 笔记评论严格分开**: 引用管理层原话用 `>` 引用块 + 页码；评论另起段。禁止在笔记正文里用第一人称陈述管理层口径（"我们公司技术领先"）
- **§2.8.3 "增长/扩张/优化"动词必带数字**: "产能扩张" → "产能从 X 吨扩到 Y 吨，<YYYY>-<MM> 投产"；"渠道优化" → "经销商从 X 家减到 Y 家/直营占比从 X% 升到 Y%"。无数字的动词删除

### §2.9所有者利润优先（§1.9推出）

- **§2.9.1所有者利润双口径**:同时列报表归母净利润与合并口径所有者利润,但不计算PE/PB或目标价。合并口径所有者利润=合并经营现金流−合并口径资本开支中的维持性部分;维持性CapEx用§1.9法A/B/C任一估算,**明写用的是哪种估算+为什么适用**。与归母净利润比较存在口径差异,必须列少数股东损益、少数股东资本投入或无法分拆限制,不得把差额全部解释为盈利质量。
- **§2.9.2 5年CFO vs 5年全CapEx汇总比较**:写一句"近5年累计CFO=X,累计全CapEx=Y,差额=Z"。Y>X连续3年以上时记录年份、金额和差额,交下游判断
- **§2.9.3 "一次性"非经项目的5年累积**: 对照 §2.3.5 (重大减值/重组/诉讼/商誉减值), 如近5年累积金额 > 同期归母 NI 累积的20% → 视为经营性成本, 笔记里单开一段"管理层的一次性项目到底是一次性吗"

### §2.10承诺 vs 兑现数据提取（§1.10推出）

本节是**数据提取**规则,不做判定。画饼阈值、诚信度和后续处置全部交给`management-analysis/SKILL.md §2.1`。

- **§2.10.1 forecast vs actual 5年表必建 (提取)**:

  | 年份 | 指标ID | 单位 | 口径 | 管理层t年披露的t+1年目标 | 目标方向 | 比较方法 | t+1年实际达成 | 绝对差 | directional_miss | 管理层t+1年是否主动解释miss | 年报页码 |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | ... | revenue/attributable_net_income/capacity等稳定ID | 元/吨等 | 合并/归母/业务范围 | 原文目标 | 至少达到/不超过/减亏等 | 百分比gap/边界比较 | 实际数字 | actual-guidance或相对边界绝对差 | true/false/需人工 | 是/否/回避 | p.N |

  来源: 每年"董事会报告 — 未来展望/下年度经营计划"段落 (A 股) / "Chairman's Statement" + "MD&A - Outlook" (港股)。
- **§2.10.2 "目标突然消失" 信号 (提取)**: t-1年说的目标, t 年报告不再提 → 笔记单独指出 + 引用两年相关段落对照。"这算不算画饼"的定性判定由 management-analysis 做。

### §2.11损益表八大指标 checklist（§1.11推出）

子agent读取A股年报第十节"财务报告"中的利润表时,对以下8项逐一落档,每项三档:**护城河型特征/中间/周期型特征**。标签只描述报表形态,不等于护城河结论。港股按`Consolidated Statement of Profit or Loss`等语义标题定位。

| 指标 | 护城河型特征 | 中间 | 周期型特征 |
|---|---|---|---|
| 毛利率 | ≥ 40% (顶级 ≥ 60%) | 20-40% | ≤ 20% |
| SG&A / 毛利 | ≤ 30% | 30-80% | ≥ 80% |
| R&D / 毛利 | ≤ 10% (消费) / ≤ 25% (科技) | 10-25% | ≥ 25% 持续 |
| 折旧/毛利 | 6-8% | 8-22% | ≥ 22% |
| 利息/营业利润 | < 15% | 15-49% | ≥ 49% |
| 所得税/税前 | 按注册地和实际税制判断;A股一般以25%为基准,港股一般以16.5%为基准 | 与适用法定税率接近 | 显著偏离且无税收优惠/递延所得税解释 |
| 净利率 | ≥ 20% | 10-20% | < 10% |
| 10y EPS 趋势 | 单调上行 | 整体上行但有2-3年下滑 | 大幅波动/下行 |

**三表互证4条双面照** (在 Step 5勾稽节强制跑):
1. 高毛利率+低Capex/NI→支持低资本消耗特征;高毛利率+高Capex/NI→两项信号矛盾,交下游复核
2. AR增速>营收增速连续2年→标需排雷复核;AR/营收低于同业→记录议价特征
3. 长期负债<3-4年NI可偿清→记录低偿债压力;<5年以上→记录高杠杆特征
4. 留存收益10年年化增速≥8%→记录持续积累特征;下行→记录恶化趋势

**Step 4 / Step 5承接**:
- Step 4附注深读时, 把"三表互证4条双面照"作为附注读后的强制 cross-check 写进子 agent prompt
- Step 5勾稽时,8指标checklist+4条互证写入笔记末尾的**财报形态初筛观察**,并明确非最终结论

---

## §3阅读流程（Step 1-7）

本节描述主 agent 如何执行。principles / rules 已在 §1 / §2讲过，本节只讲"如何派子 agent、如何 validate、如何路由"。
### Step 1 — Bootstrap + filings audit（Mode A 专有；Mode B 跳过）

1. **Validate ticker和YEAR**（§0正则）。失败双语报错并abort。先只读discovery确定YEAR和AS_OF:显式`--as-of`按原值执行;未传时把只读目录响应时间保存为`discovery_cutoff`,只用披露时间≤该截止点的目录快照选择最新有效完整年报,再用所选版本首次有效披露时间固定最终AS_OF。按最终AS_OF重跑版本状态机,两次选中版本必须一致,否则abort。YEAR省略时取报告期结束年份,港股再用PDF期末日复核。AS_OF和上市日期固定前不得生成query plan或采集事件。固定后在系统临时目录执行官方目录查询、事件query plan和全部counterpart查询，实际构造并验证候选annual、event及全部counterpart manifest；把候选manifest的真实SHA-256作为输入artifact，并追加官方目录响应哈希和query plan哈希，再调用`scripts/financial_run_store.py resolve`。临时预检不写ticker共享层；`created/resumed`后才把候选文件和日志移入返回run并按发布契约提升，`reused`只在候选哈希完全匹配时成立。不得用待建立占位值计算输入指纹。Mode A在首次持久化前建立证据阶段checkpoint,原子保存`ticker/exchange/YEAR/target_fiscal_year/AS_OF/discovery_cutoff/evidence_stage/run_status/failure_reason/completed_steps`及manifest路径和哈希;`target_fiscal_year=YEAR`,`completed_steps=[]`。`evidence_stage=未建立`时允许`run_status=进行中/manual_review`,恢复run从失败的持久化阶段重试。
   **事件证据先采集后构建**:YEAR、AS_OF和官方上市日期固定后,事件查询先写符合`references/event-query-plan.schema.json`的版本化query plan,再运行`uv run python scripts/collect_event_evidence.py --plan <absolute-query-plan.json> --bundle-out <absolute-official-query-bundle.json> --evidence-dir <absolute-immutable-evidence-dir>`。该JSON Schema只做结构校验;结构校验通过不代表来源矩阵通过,还必须由采集器和构建器按实际逐法域listing codes及`REQUIRED_SOURCE_IDS`做语义校验。读取采集器stdout返回的真实bundle路径,后续下载器和构建器只使用该真实路径,再运行`uv run python scripts/build_event_manifest.py --bundle <actual-official-query-bundle-path> --out <canonical-event-manifest-path>`。读取构建器stdout返回的真实发布路径;该路径可能是canonical基名或内容寻址版本,必须直接持久化路径和SHA-256。禁止手工拼bundle或绕过采集器。若同一AS_OF重取结果变化,构建器发布新的内容寻址版本;旧manifest保持不可变。父报告必须在同一CAS事务中使受影响section失效,原子改绑到新manifest路径及SHA-256;任一步失败继续绑定旧版本,不得半更新。
2. **准备早退最小证据**:AS_OF是统一信息截止日,控制目标公司版本、监管事件和同业资料的可得性。上市日期必须来自交易所官方发行人资料,先保存来源与响应哈希,再执行带`--listing-date <official-listing-date>`的下载命令。显式传入`--as-of`时原值贯穿全流程,目标报告披露日不得覆盖显式传入的AS_OF;未传时才以所选目标完整年报首次有效披露日初始化AS_OF。显式指定YYYY时运行`uv run python scripts/download_filings.py TICKER --years 3 --end-year YYYY --as-of AS_OF --listing-date <official-listing-date> --listing-profile-bundle <actual-official-query-bundle-path> --manifest-out <temporary-json-path>`,不得仅依赖`--as-of`推断目标财年;省略YEAR时先解析最新完整财年及AS_OF,再以解析出的YYYY执行同一命令。版本状态机必须先应用公告替代关系:撤销公告使此前版本失效;更正公告晚于当前完整年报时,更正后的完整年报必须在AS_OF前出现,未出现则abort。随后从AS_OF当日或之前仍有效的完整年报中选择公告时间最晚者,保存公告ID或官方URL、披露时间和SHA-256;截止日之后发布的更正、重述或重新发布版本不得使用。3年预检只写临时manifest;未早退时不创建或覆盖canonical年报manifest,再扩展窗口,最终10年窗口只写一次canonical manifest。触发早退时排他原子发布3年canonical年报manifest,临时manifest不得删除直至canonical发布并回读成功;早退报告必须绑定canonical路径和哈希。同一AS_OF内容漂移时发布内容寻址版本并原子改绑;只有重建、复核或改绑失败时才保留旧绑定并abort,不得半更新。事件构建统一使用Step 1的`--out <canonical-event-manifest-path>`命令并读取构建器stdout返回的真实发布路径,不得另走临时输出。每类事件覆盖全部适用官方来源,manifest按类别保存`source_count`和`sources`,每个source保存HTTP方法、请求编码和响应schema,并分别保存查询参数、响应和文书;构建器逐类在线重取全部事件分页,同类内再逐source与保存响应逐页一致。命中文书的本地路径单独放在`document_files`,不得混入官方响应;构建器重新下载每个官方文书URL并与本地文书逐字节哈希一致。构建器必须执行官方域名白名单、解析全部分页响应、分别校验`occurrence_date`和`publication_time`,并要求每个事件具备`offense_type`、`legal_effect`、`subject_role_at_occurrence`和`issuer_connection`,验证发行人/管理层/实控人/审计机构主体覆盖并限制状态枚举。顶层`live_revalidation_required`必须为`true`;形成任何否定性结论前重新请求全部官方来源并比较响应与内容哈希。官方目录必须逐页拉取至已获取数量等于官方结果总数;每条保存完整公告时间戳和公告顺序ID。只审计目标报告、`YYYY-2`至`YYYY`报表和AS_OF前的监管/审计公告;不要在早退判断前下载同业和10年资料。
   **事件段落规范化**:上段“逐类官方查询后写证据包”描述的是`collect_event_evidence.py`内部行为,调用方只能执行Step 1列出的采集器命令,不得直接准备bundle后调用构建器。`events-<AS_OF>.json`只是构建器的首选输出基名;若该基名已有不同内容,必须使用构建器返回的内容寻址版本并持久化真实路径。滚动窗口类query plan对窗口前已发生但AS_OF仍未结案的调查设置`include_open_before_start=true`;主体名册覆盖发行人、管理层、实控人和审计机构。
3. **PDF抽取与源版本复核**:对目标报告和早退所需历史,即使text.md已存在也逐份调用`uv run python scripts/extract_pdf.py <pdf>`,由extract_pdf.py校验source_sha256,源哈希不符时自动重抽取。港股标题年份只形成临时候选组;港股选中全文必须在去重结论生效前完成PDF期末日复核:从封面和Consolidated Financial Statements抽取报告期末日,与标题候选财年及HKEX公告逐项比对,确认后回写filing manifest的`报告期末日`并重新执行去重;任一冲突或无法确定时abort,不得分析
4. **目标年份完整年报仍缺失时使用官方来源**:
   - **巨潮资讯 cninfo** `http://www.cninfo.com.cn` — 覆盖 A 股全市场, 最常用
   - **上交所** `http://www.sse.com.cn` (6开头的沪市) — 原始披露文件
   - **深交所** `http://www.szse.cn` (0 / 3开头的深市/创业板) — 原始披露文件
   - 港股: **披露易 HKEXnews** `https://www.hkexnews.hk`
   - **兜底:若公司超过适用法定期限仍未披露年报,自身就是强风险信号**→立即早退§2.1.1 L3。仅本地文件缺失不能据此判定延期,必须先查交易所披露记录

### Step 1B — 共用source preflight + Mode B Part 0绑定校验
Mode A共用source preflight只执行官方目录、PDF、事件窗口和哈希复核,不要求profile Part 0。Mode B Part 0绑定校验额外要求两个实际绝对路径及SHA-256与Part 0完全一致,不得回退到同名canonical文件。
1. 校验filing manifest逐年连续,覆盖目标财年及至少前2个财年;未早退后还须覆盖目标财年及之前最多10年,上市不足时必须带上市日期和`上市以来全部`标记。每个财年必须列出官方目录在AS_OF前返回的全部候选及顶层查询URL、查询参数、响应哈希、官方结果总数和候选总数;候选包含完整公告时间戳和公告顺序ID。重新逐页拉取至已获取数量等于官方结果总数,再将manifest候选ID集合与官方目录响应按顺序重比对,少列、多列、乱序或仅列选中版本均abort。港股查询结果达到`rowRange`上限时目录可能被截断,必须缩小日期窗口后重查,不得继续。event manifest覆盖管理层、实控人及发行人上市以来全部欺诈、操纵股价、内幕交易、虚假陈述和财务造假正式处罚或生效纪律处分,以及上市以来全部已证实的大股东资金占用、违规关联交易和股东利益输送;另覆盖AS_OF前3年的审计机构变更、审计机构监管调查、年报重大更正重述、实控人刑事立案、年报逾期披露和其他监管事件。每类查询必须保存官方查询URL、查询参数、响应哈希、结果总数及命中结果或明确`未检出`;顶层`live_revalidation_required`必须为`true`,每个事件必须读取`offense_type`、`legal_effect`、`subject_role_at_occurrence`和`issuer_connection`。先重新请求主体名册的官方URL和查询参数,逐项复核实时响应哈希、结果总数和完整主体列表;任一变化都abort并要求父skill重建。形成任何否定性结论前,必须按保存的官方URL和参数重新请求全部分页并复核响应哈希、结果总数和逐事件内容哈希
2. 对每个财年按Step 1同一版本规则,使用公告标题、报告类型、有效状态和替代关系重算`是否选中`;传入`--filing`时,目标`--filing`必须与manifest选中行的路径和SHA-256一致。公告披露日>AS_OF、哈希不符、缺失中间年份或事件窗口不全时abort并返回调用方补齐
3. **Mode B source preflight只读约束**:Mode B不得调用extract_pdf.py,不得删除、替换或创建持久化抽取cache。传入`--extracted-text`时,根据同目录metadata.json解析其源PDF绝对路径,要求该源PDF等于manifest选中路径,再校验metadata.json中的`source_sha256`等于当前选中PDF的SHA-256且与manifest一致,并复核page marker和`artifact_sha256["text.md"]`等于`text.md`当前字节哈希;缺失或不符时返回warning并abort,由父skill在Mode B之外重建。遇raw PDF时在只读临时目录抽取所需页文本并在删除前完成quote复核;raw PDF引用必须返回`source_type=filing_pdf`,`artifact_path`指向持久PDF且`artifact_sha256=source_pdf_sha256`,不得返回临时文本路径。返回前删除临时目录,不得写入PDF旁的`_extracted`目录
4. 用复合`part_id/section_id`解析目标section;裸ID、零匹配或多匹配均报错。正文边界为标题下一行到下一个同级或更高层级标题前,只在内存中生成草稿并返回;父skill接受后才由父skill按Step 7契约原子写入

### Step 2 — 早退检查（§2.1）

**主agent直接读并逐项检查L1、L2、L3**（不派子agent,直接Read+grep+计算）。AS_OF是统一信息截止日,不得使用AS_OF之后发生或披露的事项;财务窗口固定为`YYYY-2`至`YYYY`,监管窗口为AS_OF日前3年:

1. **L1审计意见**:A股检索"审计意见/发表意见";港股英文报告同时检索`Audit Opinion/Opinion/Basis for Qualified Opinion/Disclaimer of Opinion/Adverse Opinion`。只有保留意见、无法表示意见或否定意见触发L1并记录类型和引用;无保留意见中的强调事项段按底层事项独立评估
2. **L1审计机构变更史与审计机构监管调查**:列近3年审计机构,变更≥2次触发。另以机构全称查询证监会/SFC/HKEX/财政部官方公告;命中时记录机构名称+立案或调查日期+官方文书URL。港股同时检索`Auditor/Change of Auditor/Resignation of Auditor`
3. **L2财务前提**:先用交易所行业、主营和业务分部识别银行。沪深A股非银行用截至`YYYY`的数据分别检查经营现金流/归母净利润、销售收现比、扣非归母净利润/归母净利润;分母和阈值以`thresholds.yaml`为准,各指标分别连续2年低于自身早退阈值才触发。归母净利润≤0时不计算经营现金流/归母净利润或扣非归母净利润/归母净利润;归母净利润≤0的财年打断连续适用财年计数,亏损年前后的低值不得拼接。营业收入≤0时不计算销售收现比,改列符号、金额和连续年数。有效VAT只能形成区间时,仅当连续2年敏感性区间上限仍<0.9才触发;区间跨越0.9时标`需下游复核`,不得早退。港股非银行按§2.1.1替代字段执行。银行不使用销售收现、常规CFO/NI或扣非净利润早退,继续提取银行10行替代bundle所需事实。不得用非正分母触发或豁免早退
4. **L3监管与重述**:A股检索"处罚/警示函/立案/公开谴责/前期差错更正/追溯调整/重述";港股同时检索`Regulatory Sanctions/Disciplinary Action/Investigation/Restatement/Prior Period Error`,并查SFC/HKEX公告

**任一L1-L3触发**→仅Mode A且未传`--complete-facts`时停止Step 2.5及Step 3-5的深读,跳到Step 7写"早退事实报告",但早退与完整报告共用最终finalizer,仍执行Step 6的live revalidation和CAS发布;未执行范围固定写`Step 3-5未执行;Step 6仅执行finalizer`,不得声称Step 6未执行。Mode A调用方传`--complete-facts`则保留触发事实并继续Step 2.5及Step 3-6的全部事实提取。Mode B无条件禁用该短路,把触发事实写入`screening_flags`并继续目标section所需的完整事实提取。完整事实输出只把风险定性交给下游,不得同时声称跳过Step 3-6。

### Step 2.5 — 完整历史和同业证据准备（未早退或`--complete-facts`时执行）

1. Mode A完整年报模式运行`uv run python scripts/download_filings.py TICKER --years 10 --end-year YYYY --as-of AS_OF --listing-date <official-listing-date> --listing-profile-bundle <actual-official-query-bundle-path> --manifest-out <temporary-annual-manifest-path>`,随后运行`uv run python scripts/download_filings.py --promote <temporary-annual-manifest-path> --canonical-out <canonical-annual-manifest-path>`并读取stdout真实内容寻址路径。Mode B不得扩窗或发布替代manifest;若Part 0绑定窗口不足则返回`rebuild_evidence`,由父skill扩窗、原子改绑后重试。Mode A共用source preflight;Mode B再执行Part 0绑定校验。5个完整`N→N+1`比较至少需要6份;10年EPS趋势和10年留存收益需要最多10份连续年报。
2. 上市历史不足或证据窗口不足10年时使用上市以来全部年报+上市文件历史数据,明确实际窗口。**港股上市文件路由**:查询HKEX官方上市文件目录,保存查询URL、查询参数、响应哈希、官方结果总数以及选中的完整上市文件PDF绝对路径和SHA-256;任何一项缺失时标`需人工`,不得伪称已取得或把短窗口写成10年结论
3. 按§2.6.2的A股或港股同业路由选3家。同行数据同时满足财年≤`YYYY`且披露日≤AS_OF,优先同一报告期的审计年报;目标财年报告在AS_OF后披露时视为当时不可得,只允许使用披露日≤AS_OF的最近更早完整财年并披露期末日差异
4. 抽取上述目标公司历史文件;同业数据记录文件路径或官方URL。下载扩窗后更新filing manifest并保存全部候选集合,重新执行Step 1B,复核路径、SHA-256、逐年连续性和选中版本。年报manifest发布为`annual-reports-<AS_OF>-<content-sha256>.json`,其真实路径和SHA-256必须与Part 0持久化路径及SHA-256一致。完成后才进入Step 3

### Step 3 — 分派"骨架遍历"子 agent（§2.2步骤1-7）

派 **1个** `general-purpose` 子 agent 读完 §2.2的 step 1-7（封面 → 所有者权益变动表）。prompt 骨架:

```
You are reading {ticker}'s {YYYY} annual report.
Primary filing: {target extracted text.md}
History inputs: {all target-company extracted annual reports required for the 5-year series}
Peer inputs: {3 peers' YYYY audited or official data;nearest earlier period only when YYYY is unavailable,with period differences and source paths/URLs}

Task: perform a structured scan covering year-end date / auditor /
audit opinion / board assurance / 5-year key metric trend /
balance sheet structure / income statement structure / cash flow
structure / owner equity changes (dividend + buyback + stock
compensation footprint).

Output format: Chinese, per-section bullet list with page-cited
numbers. Follow §2.7 citation format strictly. Missing data → write
"待补充 — p.N 未披露".

DO NOT include management discussion / narrative summary / qualitative
conclusions. Just structured facts.
```

Mode A产出写入resolver返回的`data/filings/<ticker>/runs/<run-id>/report.md`，执行状态写同run的`checkpoint.json`；Mode B只生成内存草稿。checkpoint必须保存`ticker/exchange/AS_OF/target_fiscal_year/evidence_stage/run_status/failure_reason/filing_manifest_path/filing_manifest_sha256/event_manifest_path/event_manifest_sha256/completed_steps`和逐步正文SHA-256。两个manifest路径与哈希成对校验，证据未建立时两对均写`待建立`，已绑定时任一缺失或不符都不得继续。`completed_steps`只允许已定义步骤ID；恢复时回读并重算每个已完成步骤正文哈希。输入变化由resolver创建增量子run并使受影响artifact失效，不得覆盖旧run。

### Step 4 — 分派"附注深读"子 agent（§2.2步骤8；§2.5）
派 **1个** `general-purpose` 子 agent，prompt 骨架:

```
You are reading {ticker}'s {YYYY} annual report notes section at
  {extracted text.md;A-share:Section 10 Financial Report;HK:Notes to the Consolidated Financial Statements}

Task: for each of the 12 required notes (listed below), produce one
entry per note containing: (a) raw number + YoY; (b) sub-structure
breakdown; (c) any red flag threshold crossed (thresholds listed);
(d) page citation.

12 required notes: {list from §1.5}
Thresholds:{12-note comparisons from references/statement-reading.md §3;shared thresholds from ../financial-redflag-scan/references/thresholds.yaml}

Plus 3 cross-section notes:
- 会计政策变更 / 会计估计变更 — 列变更名 + 原因 + 影响金额
- 关联交易 — 列每一笔 ≥ 披露门槛的关联交易
- 金融资产 4 分类盘点 — 瘫子 / 笋子 / 菜粽 / 肉粽金额 + YoY

Output format: Chinese, structured table or bullet per note.
Missing disclosure → "本年报未披露 (p.N / 应披露章节)".
```

### Step 5 — 勾稽 + 管理层口径对照（§2.3；§1.2返回）

**主 agent 自己做**（不派子 agent，因为跨 section 需要整合）:

1. **跑4条勾稽公式**（`../financial-redflag-scan/references/fraud-library.md`§2）:非银行执行应有销售收现勾稽/销售收现比/CFO→NI桥/维持性CapEx。港股未披露毛额销售收现时,前两项写`不适用—披露口径缺失`,引用现金流量表页码,改查应收账款、合同负债、分部收入和经营现金流桥;不得补造毛额收现。银行不使用销售收现、常规CFO/NI或维持性CapEx勾稽,四项写`不适用—银行资金即产品`,改为银行10行替代bundle（即银行10行事实输出）:不良率与关注类迁徙、逾期90天以上贷款、拨备覆盖率与拨贷比、信用成本、净息差、核心一级资本充足率、风险加权资产增速、流动性覆盖率与净稳定资金比例、存款集中度与同业融资依赖、关联授信与大额风险暴露。每行只输出期间、口径、实际值和引用,不在本skill判定风险等级。逐条填入笔记§勾稽section。任一适用项显著背离→标"需人工复核",不在本skill给最终风险等级
2. **读目标年及历史管理层讨论**（§2.2 step 9）并对照Step 3-4事实。逐段记录:"管理层说X→附注p.N实际Y→一致/不一致/证据不足";同时按§2.10抽取并填写承诺vs兑现5年表,只记录目标、实际和解释,不判断诚信
3. **读董事会报告 + 重要事项 + 公司治理**（§2.2 step 10）: 诉讼/担保/承诺/履行情况/股东变动

### Step 6 — 综合复核 + 写笔记（§1.8）

主 agent 对草稿执行**空话过滤器**:
- grep 8条禁用空话，命中则退回子 agent 补证据或删除
- 核查每个数字是否带页码（§2.7）
- 核查12项附注100% 覆盖
- 核查任何毛利率/净利率变动 > ±3点/任一指标变动 > ±20% 都已归因
- 核查承诺vs兑现表覆盖证据窗口内全部可形成的`N→N+1`比较;历史不足时写实际行数和原因

全部通过→先运行`uv run python scripts/download_filings.py --revalidate <bound-annual-manifest-path>`和`uv run python scripts/build_event_manifest.py --revalidate <bound-event-manifest-path>`。Mode A更新既有目标时运行`uv run python scripts/publish_text_cas.py --source <draft-path> --target <final-report-path> --expected-sha256 <baseline-report-sha256> --guard <bound-annual-manifest-path>:<sha256> --guard <bound-event-manifest-path>:<sha256>`;新run内`report.md`使用同一命令但明确传`--expected-sha256 absent`。Mode B只返回对象。最终报告在当前run固定路径排他发布，不得分配第二层`-vN`或覆盖既有内容；guard漂移即abort。

### Step 7 — 输出格式

**Mode A 输出骨架**（`data/filings/<ticker>/runs/<run-id>/report.md`）:

早退时只写以下短结构,不得继续生成完整§1-§14:

```markdown
# <公司名> <ticker> <YYYY>早退事实报告
- **信息截止日（AS_OF）**:YYYY-MM-DD
- **filing_manifest_sha256**:<sha256>
- **filing_manifest_path**:<absolute-canonical-json-path>
- **event_manifest_sha256**:<sha256>
- **event_manifest_path**:<absolute-canonical-json-path>
- **官方查询溯源**:<官方查询URL、查询参数和响应哈希>
## 机器引用清单
- `section_id=<L1/L2/L3行ID>;source_type=<filing_text/filing_pdf/event_document>;artifact_path=<absolute-final-artifact-path>;source_pdf_sha256=<sha256-or-null>;artifact_sha256=<sha256-or-null>;event_manifest_sha256=<sha256-or-null>;document_url=<url-or-null>;content_sha256=<sha256-or-null>;page=<N-or-null>;quote=<逐字原文>`
**早退触发:**L1/L2/L3
**证据置信度:**<高/中/低/需人工>
## L1-L3触发事实
<事实+机械阈值+页码/监管URL>
## 未执行范围
<Step 3-5未执行;Step 6仅执行finalizer>
## 下游handoff
<交financial-redflag-scan做最终风险判断>
```

未早退时使用完整骨架:

```markdown
# <公司名> <ticker> <YYYY>年度报告阅读笔记

- **信息截止日（AS_OF）**: YYYY-MM-DD
- **filing_manifest_path**: <absolute-canonical-json-path>;**filing_manifest_sha256**: <sha256>
- **event_manifest_path**: <absolute-canonical-json-path>;**event_manifest_sha256**: <sha256>
- **官方查询溯源**: <官方查询URL、查询参数和响应哈希>
- **期末日**: YYYY-MM-DD
- **披露日**: YYYY-MM-DD
- **审计机构**: <name>（近 5 年变更次数: N）
- **审计意见**: 标准无保留 / 保留 / 无法表示 / 否定
- **早退触发**: L1/L2/L3/无
- **笔记置信度**:高/中/低（低只表示证据窗口不足或关键数据缺失;早退严重性不自动降低证据置信度）

## 机器引用清单
- 按§2.7.4写`source_type=filing_text/filing_pdf/event_document`三分支字段;artifact_path不得指向scratch、staging或临时抽取目录

## §1 5 年财务趋势（§2.6.1）
<表格: 营收 / 归母 NI / CFO / 毛利率 / 净利率 / ROE / 资产负债率 / CapEx / 分红率 × 5 年>

## §2 同业 3 家对标（§2.6.2）
<表格: 本公司 vs 3 家同业 × 关键指标>

## §3 资产负债表速览
<结构 + 5 分类拆解 + 变动 > ±20% 解释>

## §4 利润表速览
<营收结构 / 毛利率归因 / 非经常性损益明细 / 扣非 NI>

## §5 现金流量表速览
<CFO / CFI / CFF + 勾稽 4 条公式结果>

## §6 附注深读（12 项 + 3 补充）
<每项 1 entry: 金额 / YoY / 结构 / 阈值 / 页码>

## §7 金融资产 4 分类盘点

## §8 关联交易明细
<每笔 ≥ 披露门槛的关联交易列明>

## §9 会计政策 / 估计变更
<若无变更写"本年报无变更"；若有则列变更名 + 原因 + 金额影响>

## §10 管理层讨论对照
<逐段评注: 管理层口径 vs 附注实际>

## §11 诉讼 / 担保 / 承诺履行
<事实清单>

## §12 董监高持股变动 + 股份变动
<套现 / 增持信号>

## §13承诺vs兑现数据表
<§2.10规定的5年提取表;不作诚信判定>

## §14 阅读观察（非结论）
<3-5 句客观观察, 不下买卖判断, 指向下一步 (e.g. "触发排雷 §4.5 商誉阈值, 建议接 /redflag-scan")>
```

**Mode B输出**:成功返回`{"terminal_status": "success","failure_reason": null,"ticker":"<canonical>","exchange":"<SH/SZ/HK>","target_fiscal_year":YYYY,"AS_OF":"YYYY-MM-DD","target_section":"<part_id/section_id>","filing_manifest_path":"<absolute>","filing_manifest_sha256":"<sha256>","event_manifest_path":"<absolute>","event_manifest_sha256":"<sha256>","counterpart_filing_manifest_sha256s":{},"source_manifest_sha256":"<same-as-filing>","facts":[{"canonical_evidence_id":"<sha256>"}],"citations":[],"warnings":[],"screening_flags":[],"action_requests":[]}`。失败返回`{"terminal_status": "failure","failure_reason":"<具体原因>"}`,人工终态返回`{"terminal_status":"manual_review","failure_reason":"<证据缺口>"}`;两者facts为空并返回`action_requests`,每项为`request_id/type/reason/citations/execution_status/execution_result`,type只允许`edit/research_more/rebuild_evidence/exit`,初始`execution_status=pending/execution_result=null`,request_id按类型、目标、原因和规范化citation IDs确定性计算,父流程按类型确定性恢复。创建clean run不属于子skill动作；只有用户明确要求“完全重新分析”时才由入口resolver处理。每条fact和screening flag都必须引用至少一个按共享证据契约生成的`canonical_evidence_id`;该ID不包含下游判断。`screening_flags`只保存L1至L3机械初筛事实、引用和适用口径,不得包含最终风险或投资结论。`citations`严格使用§2.7.4三分支联合类型:`source_type=filing_text`、`source_type=filing_pdf`、`source_type=event_document`;每项含`section_id/source_type/artifact_path/source_pdf_sha256/artifact_sha256/page/quote`,event_document另含`event_manifest_sha256/document_url/content_sha256`,其中`artifact_path=<absolute-final-artifact-path>`。本skill不得直接替换或写入任何profile section;失败对象不得携带可保存事实。

父skill接受Mode B返回对象后先核对`ticker/exchange/target_fiscal_year/AS_OF/target_section`和全部manifest真实路径及哈希,再对annual、event及每个counterpart执行最终live revalidation。只更新调用方指定section:按标题下一行到下一个同级或更高层级标题前整体替换正文,引用列表随正文整体替换,并使用`publish_text_cas.py`、调用前profile SHA-256及`--guard <bound-annual-manifest-path>:<sha256> --guard <bound-event-manifest-path>:<sha256> --guard <counterpart-filing-manifest-path>:<sha256>`执行CAS写入;非A+H省略counterpart guard。该写入属于父skill;并发或guard冲突时不得覆盖。

**Mode B初筛flags**:L1至L3触发事实进入`screening_flags`,同时继续目标section完整事实提取。父skill只更新调用方指定section,不得修改其他section。初筛严重度与证据置信度分开:完整官方证据可为`高`,不得因触发负面事实自动降级。

**证据置信度固定映射**:`高`=完整官方窗口且无代理口径;`中`=官方窗口完整但存在已披露且不影响结论方向的代理口径;`低`=关键结论仅有二级来源或窗口不足;`需人工`=存在待定或证据冲突。取所有关键结论中的最低档,不得凭主观上调。

---

## §4与其他 skill 的关系

本 skill 是 **阅读层**，产出 "事实笔记"。下游 skill 消费这些事实做判断:

```
read-filing   (阅读层, 本 skill)
        │
        ├── 产出事实笔记 (页码引用 / 附注覆盖 / 勾稽结果)
        │
        ├──▶ financial-redflag-scan    (排雷层 — 29 项 + 6 项附加检查)
        │
        ├──▶ management-analysis        (管理层诚信度)
        │
        └──▶ value-profile              (主 profile 体系)
```

- **和 `financial-redflag-scan` 的分工**: 本 skill 产出**附注12项原始数据 + 勾稽4条结果**，作为 redflag-scan 29项排雷的**输入**。redflag-scan 负责按阈值**判断**风险触发与否
- **和 `management-analysis` 的分工**: 本 skill 产出**管理层讨论对照 + 承诺履行事实清单**，作为 management-analysis 诚信度判断的**输入**
- **和 `value-profile` 的分工**: 本 skill 产出的笔记是 profile 的 **§阅读笔记** section 素材，尤其为 §1.1-§1.7生意模式、§3财务表现、§4.5排雷提供事实基础

**不重复做的事**:
- 本skill**不算估值**（留给value-profile §6）,只计算所有者利润等事实口径
- 本skill**不下"好生意/好公司"判断**（留给value-profile §1/§4）,财报形态只作为初筛观察
- 本skill**不下最终风险等级或剔除结论**（留给financial-redflag-scan）,只记录阈值比较和`需人工复核`
- 本 skill **不做管理层诚信度评分**（留给 management-analysis）

本skill唯一做的是:**把完整年报读成一份事实清单**,页码引用完整、附注覆盖完整、勾稽跑完。

---

## §5常见错误自检表（子 agent 提交前跑一遍）

| 自检项 | 通过条件 |
|---|---|
| 所有数字都带页码 | grep 笔记，每个数字附近有 `(年报-YYYY.pdf p.N)` 或等价格式 |
| 附注12项100% 覆盖 | 笔记 §附注 section 有12个 entry（未披露也要写"未披露 p.N"）|
| 8条禁用空话0命中 | grep 8条空话，仅允许出现在 `>` 引用块内（管理层原话）|
| 净利润相关finding都有CFO/NI背景 | 非银行每条带"净利/营收/毛利率"的finding附近有同期CFO/NI/销售收现;银行写`不适用`,改查银行10行 |
| 口径一致 | 全篇"净利"默认归母，不默认合并 |
| 5年纵向 + 3家横向成对出现 | 核心指标表格有5年列 + 同业3列 |
| 变动 > ±20% 都已归因 | 每个大变动3句解释（原因/证据/可持续性）|
| 审计意见类型写了 | 笔记开头含审计意见类型 + 会计师事务所 + 近5年变更次数 |
| 会计政策/估计变更单列 | 有专章（无变更也要明确写"本年报无变更"）|
| 早退检查4项跑过 | 开头 `早退触发:` 字段非空（"无" 也算）|

---

## §6 References

**本 skill 自带 reference** (`references/`):
- `statement-reading.md` — 阅读顺序/资产负债表5分类 + 反直觉/金融资产4分类新准则/附注12项/利润表八大指标/快速扫描/特殊场景
- `filing-structure-cn.md` — A 股年报10节地图 (证监会第2号准则) + 季报披露时限 + 业绩预告
- `filing-structure-hk.md` — 港股年报结构 (HKEX Main Board Appendix 16) + 中报披露时限 + profit alert
- `quick-lookup.md` — 术语/时间预算/新准则 / CFO 画像/所有者利润速算/自检表 / 20条反模式

**项目内其他 reference**:
- `../financial-redflag-scan/references/fraud-library.md` — 勾稽4公式 + 风险10项阈值 + 造假5维度 + pattern A1/A2/A3
- `../financial-redflag-scan/references/thresholds.yaml` — 跨skill共享阈值、市场基准和严重度的唯一来源
- `../value-profile/references/discipline.md` — 分析纪律
- `../financial-redflag-scan/SKILL.md` — 29项排雷 + 6项附加检查的**判断**侧
- `../management-analysis/SKILL.md` — 管理层诚信度**判断**侧

**外部法规**:证监会《公开发行证券的公司信息披露内容与格式准则第2号——年度报告的内容与格式》;上交所/深交所《上市公司信息披露工作备忘录》。
**外部二手资料**:本skill第一版的原则/规则/反模式部分灵感来自`data/research/`下收录的中文价值投资财报阅读教材。
