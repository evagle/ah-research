---
name: management-analysis
description: Use when a user asks to evaluate a Shanghai/Shenzhen A-share or HK company's management integrity,capital allocation,corporate culture,shareholder alignment,or promises versus delivery,including "分析管理层0700.HK" or "/management-analysis 600519.SH".
---

# Management Analysis Skill

本 skill 是 value-profile 主 skill 的子 skill, 专门负责"管理层诚信 + 企业文化 + 股东回报态度"的深度分析。结构分三层: **§1原则（精炼心法）→ §2规则（纪律）→ §3流程（Step 1-5执行）**。

**覆盖边界**:港股仅支持当前上市发行人;已退市港股发行人超出当前下载器和官方目录适配范围。

**共享证据契约**:运行前必须完整读取`.claude/skills/read-filing/references/evidence-contract.md`。身份、AS_OF、manifest绑定、引用、Mode B写入权、终态和证据漂移只以该文件为准;本skill只补充管理层判断特有规则。

**共享运行契约**:运行前必须完整读取`.claude/skills/read-filing/references/run-store-contract.md`。共享目录、run隔离、无感resolver和旧路径兼容只以该文件为准。

## §0运行模式

本 skill 支持两种模式, 主 agent 根据 invocation 参数选择:

### Mode A — Standalone

- **Invocation**:`/management-analysis <ticker> [--as-of YYYY-MM-DD] [--auto|--interactive]`/`分析管理层 <ticker>`/`管理层分析 <ticker>`。只有用户明确要求“完全重新分析”时内部resolver使用`--clean`
- **行为**: 子 skill 独立完成 ticker 验证 + filings audit + PDF 抽取 cache 检查 + 派子 agent 抓年报 + 主 agent 复核 + 写 standalone 报告
- **Output path**:`data/filings/<ticker>/runs/<run-id>/report.md`—self-contained报告,仅含本skill覆盖的管理层相关内容,约100-200行。
- **典型场景**: 用户只想评估某 ticker 的管理层, 不需要完整 value-profile。

### Mode B — As-subroutine

- **Invocation**:主value-profile skill在Step 3遇到Part 1 §4时delegate,传参`--target-profile <path> --section part1/§4 --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> --auto|--interactive`
- **行为**: 信任主 skill 已做过 Step 1 (ticker 验证 + filings audit + PDF 抽取 cache); 跳过这些, 直接从 Step 3 (派子 agent) 开始
- **Output**:仅返回`draft_sections`和结构化flags,父skill是唯一写入者;本skill不直接修改`<target-profile>`
- **运行边界**:Mode B不调用run store，也不创建run
- **典型场景**: 用户跑 `/value-profile <ticker>`, 主 skill 推进到 §4时自动调用本 skill

### Invocation 解析

- 参数只有ticker→Mode A（Standalone），默认`--auto`；固定目标财年和AS_OF后由resolver自动续跑、复用或增量新建，不显示恢复选择
- 参数含`--target-profile <path> --section <part1/§4|part1/§4.pre|part1/§4.1-§4.8> --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> --auto|--interactive`→Mode B（As-subroutine）;两个manifest参数必须是已持久化JSON文件的绝对路径,不得接受内联JSON、相对路径或不存在的文件;未传任一manifest或模式时报契约错误
- Ticker验证:沪深A股使用`\d{6}\.(SH|SZ)`,港股使用`\d{1,5}\.HK`。港股代码立即左补零为五位,后续路径、manifest、查询参数和输出只使用canonical ticker

---

## §1管理层分析原则

精炼7条。这些是整个 skill 的信念层, 跨模式共享。

### §1.1对股东的负责度 >> 经营能力

管理层的诚信、对股东的责任感, 远比他们的经营能力重要。一个不诚信的管理层, 能力越高风险越大——因为能力越高、越能系统性地侵占股东利益。评估顺序: 先看诚信, 再看能力。

### §1.2承诺 vs 兑现是诚信的最硬指标

年报经营计划、业绩说明会指引、战略规划, 都是可以5年后回头对照的承诺。5年尺度的承诺兑现率是管理层诚信度最客观的指标, 远比一次性专访/致辞更可靠。

### §1.3国企年报的弦外之音

国企年报写给全体利益相关方（监管+党组织+员工+地方政府+股东+供应商+经销商）,价值投资者不是首要读者。正文多为合规话术/员工福利信号/地方政绩信号;关键信号在附注（关联交易、担保、应交税费、其他应收款）和实际存在的治理监督报告。若年报披露监事会则读取监事会报告;未设监事会时改查独立董事或独立非执行董事、审计委员会和公司治理报告。

### §1.4股东回报是管理层道德的实操标准

"嘴上对股东负责"容易, "实际操作中对股东负责"难。看三件事: ① 分红政策是否稳定 + 分红率是否合理; ② 是否以合理价格回购股份; ③ 关联交易是否公允（特别是关联采购/关联销售/关联担保/大股东占款）。三者背离 → 道德降级。

### §1.5言行一致检验

董事长致辞/业绩说明会的 "说", 必须对得上之后的 "做"。评估方法: 至少抓2个具体事件（有日期 + 有结果）, 看"说的"和"实际发生"是否一致。整份管理层分析必须包含 ≥ 2事件的言行一致检验, 否则不合格。

### §1.6好生意 > 好管理层, 但烂管理层依然弃权

一流生意 + 三流管理层通常优于三流生意 + 一流管理层（因为好生意的经济商誉能让平庸管理层也挣到钱）。但 §4道德风险（虚假陈述/处罚/股东利益输送/系统性画大饼）**一票否决**——即使生意再好也弃权。

### §1.7管理层评估独立成章, 不得混入估值

管理层道德风险一旦发现, **整份 profile 降级**, 不得进入估值环节。管理层 "合格" 不是加分项, 是准入门槛——合格只是让估值流程继续, 不抬估值。

---

## §2管理层分析规则

本节是 §1推出的可操作纪律。每条编号 `§2.N.x` 对应原则 `§1.N`。

### §2.1承诺 vs 兑现5年表（§1.2推出）

- **§2.1.1表骨架**:5年跨度,每年一行,列`年初guidance/实际达成/差异/年报页码`。A股从N年度董事会报告或下一年度经营计划抽guidance,从N+1年经营情况讨论抽实际;港股从`Chairman's Statement`或`MD&A Outlook`抽guidance,从N+1年`Business Review`或`MD&A`抽实际。
  - **数据来源优先级**: 若上游 `read-filing` 已产出 §2.10提取表, 直接读入使用 (避免重复手工提取); 若无, 本 skill 自建 (Step 3派子 agent 抽)。
- **§2.1.2偏差定义和阈值**:先按目标方向选择比较方法,再处理目标值正负号。仅`guidance>0`且目标方向为"至少达到"时计算`gap=(guidance−actual)/guidance`;仅`gap>0`表示未达指引。`guidance>0且目标方向为上限`仍按上限比较,不得误入最低目标公式。`guidance=0`、`guidance<0`、上限、减亏、亏损或其他方向性目标均按原文边界、实际值和绝对差判定,不计算百分比gap并写`N/A`;实际值越过边界且方向对公司不利时写`directional_miss=true`,达到或优于边界时写`false`。区间目标使用对管理层最宽松的已披露边界,方向不明时写`需人工`。适用行`gap>10%`连续3年或同一指标连续3年`directional_miss=true`→记录"管理层guidance系统性不可靠"风险;证据置信度不因管理层未兑现而降低,仍只按来源完整性和可复核性确定。
- **§2.1.2a连续序列身份**:连续偏差和后置否决只能在同一指标ID上计算,例如`revenue`与`attributable_net_income`分别成序列;每条序列必须覆盖连续3个可比财年且单位和口径一致。币种、合并范围、会计口径或目标方向变化时先重述为可比口径,无法重述则打断序列并写`需人工`。不同指标不得拼接为连续三年。
- **§2.1.3次年目标变化是试金石**: 目标突然消失/从具体数字改成定性描述（"保持稳健增长"）/ 重新设定一个更低的基数 → 强信号, 必须单独指出。

### §2.2董事长5年评估（§1.5推出）

- **§2.2.1读5年董事长致辞**: 连续读5年, 评 ① 战略连贯性（每年是否改口径）② 战略 vs 实操（说的和做的是否一致）③ 言行一致检验。
- **§2.2.2 2个事件下限**: 必须挑出 ≥ 2个具体事件（日期 + 承诺内容 + 实际结果）, 不允许 "管理层言行基本一致" 这种空话。

### §2.3股东回报 checklist（§1.4推出）

- **§2.3.1分红**: 5年分红率（派息/净利）曲线; 有无异常波动; 是否用 "送转股本" 掩盖分红不足（送转不是分红, 不入分红率）。
- **§2.3.2回购**: 有无回购; 回购价是否合理（回购价 > 合理估值 = 把股东钱烧掉）; 回购股是注销还是充库存股（注销 > 库存股）。
- **§2.3.3关联交易**: 读附注"关联方及关联交易"; 特别关注关联采购占成本比/关联销售占营收比/关联担保/大股东占款; 关联交易定价是否公允。
- **§2.3.4股权激励/员工持股/高管增减持**: 5年曲线 + 关键事件。行权价是否低于合理估值（贱卖给管理层 = 侵占股东）; 高管减持节奏（年报发布前后密集减持 = 风险）。

### §2.4审计变更风险（§1.1推出）

- **§2.4.1审计师变更**: 近3年是否换审计所; 前任辞任声明有无异常; 新任首年意见是否标准无保留。
- **§2.4.2董秘 / CFO 变更**: 频率 > 1次 / 2年异常; CFO 离任 + 不久后财报重述 = 高危信号。

### §2.5董监高结构（§1.3推出）

- **§2.5.1年龄/在任年限/专业背景**: 董事会成员平均在任年限（过短 → 内斗/不稳; 过长 → 固化）; 独立董事是否真独立（关联方任命/同一地方圈子）。
- **§2.5.2薪酬 vs 业绩**: 高管薪酬增速是否匹配净利增速; 业绩大幅下滑而薪酬未降 = 道德风险。

### §2.6治理监督报告路由（§1.3推出）

- **§2.6.1按实际治理结构选择**:若年报披露监事会,读取监事会报告并追查任何非模板化意见。若没有监事会,港股及其他单层董事会发行人改查独立非执行董事（INED）、审计委员会、提名委员会和`Corporate Governance Report`;A股改查独立董事述职报告、审计委员会报告和内部控制评价。A+H发行人必须按两套治理取证:内地侧监事会或其法定替代监督材料,加港股侧INED、审计委员会、提名委员会和公司治理报告;两地证据相加而非互相替代。不得因缺少不适用的监事会报告而报错。

### §2.7道德风险一票否决（§1.6 / §1.7推出）

- **规则优先级**:management-analysis专属诚信否决规则优先。`financial-redflag-scan`只对正式财务造假或财务虚假陈述自动一票否决;本skill还独立覆盖管理层或实控人的欺诈、操纵市场、内幕交易和已证实股东利益输送。两者冲突时按本节较严格但证据闭合的规则执行,调查中事项仍只标待定。
- **§2.7.1前置触发条件**:上市以来存在欺诈、操纵股价、内幕交易、虚假陈述和财务造假正式处罚或生效纪律处分/已证实的违规关联交易或股东利益输送/大股东占款。问询、刑事立案或调查中事项只标`需人工/待定`并阻断估值,不作前置否决;正式判决或生效处罚再按对应类别判定。以上不依赖本skill后续分析,在`§4.pre`扫描。
- **§2.7.1b事件归类去重**:`§4.pre`四行互斥归类,按`虚假陈述处罚记录>大股东占款>关联输送>道德风险其他事项`的优先顺序分配唯一行。虚假陈述只计入`虚假陈述处罚记录`,不得同时计入道德风险;同一事件只计数一次,但可在其他行的解释中引用而不增加触发数。
- **§2.7.1a任职归因**:监管事件必须读取`subject_role_at_occurrence`和`issuer_connection`。现任或离任管理人员在任职期间或与发行人有关的行为纳入本公司诚信判断;离任后个人无关行为不得归因给发行人。关键人变更按事件发生日前后24个月检查CFO、董事长、审计师变更、财报重述和处罚;关系不明时写`需人工`,不得自动否决。
- **§2.7.2后置触发条件**:系统性画大饼在§4.2完成后复核。对适用百分比gap的同一指标ID,连续3年gap>20%触发,不得把超额完成的负gap计入。对上限、减亏、亏损或其他非正目标,同一指标ID连续3年`directional_miss=true`触发;不得因gap为`N/A`使该路径不可达,也不得在尚无兑现表时预判。
- **§2.7.3阶段C后置触发条件**:`§4.8`必须完整读取`references/related-party-alignment.md`。Mode A和Mode B共用这10行canonical schema:资金占用、关联采购不公允定价、关联销售不公允定价、商标/品牌授权费、销售/采购渠道被控制、关联担保、关联方长期预付款、大股东主导合营项目沉淀、集团代付/分担高管薪酬、大小股东分红权差异。银行必须额外完成4行:银行关联授信、银行关联存款、银行关联资产转让、银行关联担保;非银行不生成银行4行扩展。状态到严重度的固定映射以reference为唯一来源,严重度枚举为`无/预警/高风险/一票否决/待定`。证实大股东侵占上市公司利益、违规担保或非公允利益输送时触发;`需人工`、问询或调查中事项只返回待复核,不得当作已证实否决。
- **§2.7.4后果与恢复**:Mode A报告结论写`弃权`;Mode B只在Part 1的`§4.pre`、`§4.2`或`§4.8`记录证据。风险严重度和证据置信度分开:官方处罚窗口完整、文书逐字节复核且归因闭合时,证据置信度保持`高`,不得因否决结论而降级。Mode B只返回`draft_veto=true`和`management_veto=false`,同时返回`reason`与`citations`;父skill先在内存中重算有效否决和全部联动字段,再与正文通过同一次原子写入持久化。本skill不得修改Part 0或Part 4;前置否决跳过尚未开始的深挖section,后置否决保留已完成section并停止剩余未完成section。resume必须从`§4.pre、§4.2和§4.8`重建否决状态,不得只依赖内存handoff。

### §2.8财务分配4大测试（§1.4推出 — 管理层质量的财报侧面）

管理层的股东回报态度§2.3是**语言层**;本节是**行动层**——把10年的ROE/分红/回购/并购/债务决策看一遍,判定管理层是为股东分配资本还是为自己建帝国。每项给`通过/中间/不通过/证据不足`四档,再按固定规则聚合:

**银行资本分配替代bundle**:银行不运行下表的通用ROE杠杆和债务政策测试;存款和同业负债不得套用普通企业有息负债测试。改查10年ROA/RORWA与风险调整后回报、分红和内生资本留存、核心一级资本相对风险加权资产增长、拨备与信用成本跨周期充分性、关联授信/存款/资产转让与担保、大额风险暴露、股权融资和资本工具发行是否反复稀释普通股股东。风险加权资产与资本增长严格使用../financial-redflag-scan/references/thresholds.yaml的`rwa_growth_matrix`,核心一级资本增长口径为资本金额增长,并比较风险调整后资本成本。仍按4项输出`通过/中间/不通过/证据不足`并使用相同聚合规则。

1. **风险调整后回报**:`通过`=最近3年ROA和RORWA均未低于各自前3年中位数10bp以上且覆盖资本成本;`中间`=任一指标低10bp以上但只持续1年;`不通过`=任一指标低10bp以上连续2年或持续低于资本成本;`证据不足`=窗口或口径缺失。
2. **分红与内生资本**:风险加权资产增速与核心一级资本金额增速只按../financial-redflag-scan/references/thresholds.yaml的`rwa_growth_matrix`映射:`rwa_growth_matrix`为`none`→`通过`,`warning`→`中间`,`high_risk`→`不通过`,`pending`→`证据不足`。先从银行披露或监管来源取得机构适用核心一级资本监管最低要求;分红后核心一级资本低于该适用监管最低线为`不通过`,分红后资本缓冲低于1.5pp但未低于监管线为`中间`;适用要求不可得时写待定且不得判定监管违规,通用市场基线只作后备比较。缺分红、资本或增长数据为`证据不足`。多条件并存时取最差档,不得另设增长差阈值覆盖共享矩阵。
3. **拨备与风险暴露**:`通过`=拨备覆盖率未连续2年下降5pp且关联授信受控;`中间`=单年下降≥5pp但未突破监管约束;`不通过`=连续2年下降≥5pp并伴随不良或逾期恶化,或关联授信/大额风险暴露突破适用监管限制;`证据不足`=资产质量或风险暴露证据缺失。
4. **普通股股东稀释**:`通过`=资本工具服务于可验证的高回报增长且未反复稀释;`中间`=5年内1次可解释稀释;`不通过`=5年内≥2次普通股增发、配股或可转股资本工具转股且新增回报未覆盖资本成本;`证据不足`=发行用途或回报无法验证。

- `0项不通过`且中间项≤1→资本分配`合格`
- `0项不通过`且中间项≥2,或`1-2项不通过`→资本分配`有保留`
- `3-4项不通过`（即`≥3项不通过`）→资本分配`有保留—系统性失败`,不得仅凭本节弃权
- 任一`证据不足`→资本分配`有保留—证据不足`,列出缺失年份和字段;不得聚合为`0项不通过`,也不得用其他项目的`通过`抵消
- Mode A把该聚合结果写入总结;Mode B写入§4.6并由主skill综合。`弃权`只由§2.7触发

**管理层最终三态决策表**:

- 任一§2.7否决成立→弃权。
- `关键人变更`在24个月窗口内与处罚、重述或审计异常同向且归因未闭合→有保留;证据闭合后按底层事件重算。
- `§4.8最高严重度`为`一票否决`→弃权,为`高风险/预警`→有保留,为`待定`→按pending处理,为`无`才不改变结论。
- 存在pending或证据不足→有保留;不存在pending或证据不足,但资本分配为任一`有保留`状态时也判有保留。
- 无否决、无未决且资本分配合格→合格。

| 测试 | 看什么(10年窗口) | 通过(管理层一流) | 中间 | 不通过(风险) |
|---|---|---|---|---|
| **1. ROE稳定性** | ROE 10年走势+绝对水平 | 稳定或上行且ROE≥20%,非靠外部杠杆堆起 | 稳定或上行且10%≤ROE<20% | 0%≤ROE<10%、ROE<0%、持续下行,或靠长期负债/净资产>1堆起ROE |
| **2. 分红vs回购** | 回购发生时的PE+分红稳定性 | 系统性回购窗口全部<25PE且稳定分红 | 25PE≤回购价<40PE,或偶尔回购且分红不稳 | 回购价≥40PE,或从不回购且现金长期堆积不分红。PE≤0或不可定义时不进入估值区间,写`证据不足/亏损期`,不得落入`<25PE` |
| **3. 并购克制** | 商誉变化 + ROIC 走势 | organic 增长为主; bolt-on 并购 ≤ 10% 营收, ROIC 不降反升 | 中等并购节奏, ROIC 稳定 | 商誉逐年涨 + ROIC 走弱 = 建帝国, 不创造价值; 连续3年并购对价 > 净利50% → 高风险 |
| **4. 债务政策** | 长期有息负债 / 5年累计 NI | < 1且借款用于真实经营扩张 | 1-3之间 | **> 3且用于顶部回购/对外并购** → 管理层激进杠杆套利,未来硬着陆风险。5年累计NI≤0时不计算比率,直接写`不通过—累计利润非正` |

**操作要点 (子 agent prompt 必带)**:
- §2.8是**数据驱动**,不靠管理层言辞;A股的ROE/分红/商誉/长期负债查第十节财务报告及附注,审计意见查同节审计报告;港股按`Consolidated Financial Statements`、`Notes`和`Independent Auditor's Report`等语义标题定位
- 与 §2.3股东回报 checklist 互补: §2.3看**口径**, §2.8看**十年累计结果**
- §2.8不通过不等于§2.7一票否决;按上述固定映射聚合,只有独立满足§2.7前置或后置条件才一票否决

---

## §3分析流程（Step 1-5）

### Step 1 — Bootstrap（仅 Mode A）

Mode B 跳过本步, 信主 skill 已做。

1. **Validate ticker**:沪深A股使用`\d{6}\.(SH|SZ)`,港股使用`\d{1,5}\.HK`。港股代码立即左补零为五位。失败双语报错并abort。
2. **准备共享证据**:显式`--as-of`按原值执行；未提供时先只读交易所官方目录，选择目标完整年报首次有效披露日。固定目标财年和AS_OF后，先运行`read-filing` Mode A准备或复用annual、event及全部counterpart manifest，并取得真实路径、SHA-256和artifact ID。
3. **解析standalone状态**:使用上述真实artifact ID调用`scripts/financial_run_store.py resolve`。`resumed`从返回run的checkpoint继续，`reused`直接返回已完成report，`created`在新run中执行；只有“完全重新分析”传`--clean`。不得使用待建立指纹，也不得询问用户resume、新run或run ID。
3.5. **保存下载前基线**:共享canonical manifest只新增内容寻址版本，不覆盖旧版本。run内候选manifest、query和日志只写当前run；通过复核后使用run store提升到ticker共享层。
3.55. **先创建standalone恢复骨架和证据阶段checkpoint**:Mode A只使用resolver返回的`checkpoint.json`和`report.md`，至少持久化AS_OF、证据阶段、`**运行状态:**进行中`、`**失败原因:**无`和待建立manifest字段。采集失败时写具体原因和`需人工`，下次正常调用由resolver自动恢复。
3.6. **先采集官方查询bundle**:在任何`download_filings.py`命令前,按`../read-filing/references/event-query-plan.schema.json`生成计划,上市代码与日期只接受listing profile官方响应中的`listing_codes/listing_dates`,并保存实际请求要求的请求头。运行`uv run python scripts/collect_event_evidence.py --plan <absolute-query-plan.json> --bundle-out <absolute-official-query-bundle.json> --evidence-dir <absolute-immutable-evidence-dir>`并验证成功后,读取采集器stdout返回的真实bundle路径;后续下载器和构建器只使用该真实路径。失败时返回并持久化具体错误,不得先下载。
4. **Audit`data/filings/<ticker>/`**:
   - 承诺兑现5行需要至少6份年报形成5个完整`N→N+1`比较;资本分配测试准备最近10个财年
   - A股上市满10年但文件不足时使用`uv run python scripts/download_filings.py <ticker> --years 10 --end-year <latest-required-fiscal-year> --as-of AS_OF --listing-date <official-listing-date> --listing-profile-bundle <actual-official-query-bundle-path> --include-prospectus --manifest-out <temporary-annual-manifest-path>`;港股执行同一命令但不传`--include-prospectus`。上市日期必须来自交易所官方发行人资料。`--auto`自动执行下载;下载成功后重新audit,再构造并复核两个manifest,失败则持久化需人工终态并退出;只有`--interactive`显示`yes/no/show-command`。`latest-required-fiscal-year`从证据窗口推导,不得用今日年份代替
   - 上市历史不足10年时逐年核对上市以来每个应披露财年。A股可使用下载器取得招股说明书;港股从HKEX官方上市文件目录单独检索并保存,港股不传`--include-prospectus`。缺上市文件不伪称已取得,而是记录官方检索URL、条件和结果。全部分支都标`上市历史不足,实际窗口N年`;任一中间年份缺失都必须fetch或abort,不得用不连续窗口继续;少于6份时实际形成N-1个比较,不得声称完成5个跨年比较,相关结论降为低置信度
5. **构造canonical manifests**:年报新查询结果先通过`--manifest-out <temporary-annual-manifest-path>`写临时文件并与Step 3.5的snapshot逐字段比较。Mode A执行与Mode B完全相同的官方目录、候选元数据和PDF哈希复核,发布路径允许`annual-reports-<AS_OF>.json`或内容变化时的`annual-reports-<AS_OF>-<content-sha256>.json`内容寻址版本。事件证据必须先采集后构建:query plan遵守`../read-filing/references/event-query-plan.schema.json`,并按`../read-filing/references/event-source-discovery.md`从实际官方请求提取URL、HTTP方法、请求编码、分页字段和response_adapter,不得猜测接口;A+H发行人必须使用两地官方代码和官方上市日期覆盖两地全部适用来源。随后运行`uv run python scripts/collect_event_evidence.py --plan <absolute-query-plan.json> --bundle-out <absolute-official-query-bundle.json> --evidence-dir <absolute-immutable-evidence-dir>`,成功后运行`uv run python scripts/build_event_manifest.py --bundle <actual-official-query-bundle-path> --out <canonical-event-manifest-path>`,读取构建器stdout返回的真实发布路径;同一AS_OF变化时旧manifest保持不可变,并通过CAS原子改绑。A+H治理取证还必须从逐法域官方年报目录构造`counterpart_filing_manifests`,把`counterpart_filing_manifests路径及SHA-256映射`按`SH/SZ/HK`持久化,并保存官方目录请求和选中PDF哈希;主年报manifest不能代替另一法域披露。每类事件覆盖全部适用官方来源并保存`source_count`和`sources`;每个source保存HTTP方法、请求编码和响应schema,并保存请求头。银行额外覆盖NFRA/PBC或HKMA,审计调查覆盖适用审计监管来源;主体名册覆盖发行人、管理层、实控人和审计机构,保存主体名册的官方URL和查询参数并复核实时响应哈希、结果总数和完整主体列表。构建器执行官方域名白名单、解析全部分页响应、校验`occurrence_date`、`publication_time`、`offense_type`、`legal_effect`、`subject_role_at_occurrence`、`issuer_connection`、主体覆盖和状态枚举;构建器逐类在线重取全部事件分页,再逐source重取文书;本地路径单独放在`document_files`,不得混入官方响应,重新下载每个官方文书URL并与本地文书逐字节哈希一致。顶层`live_revalidation_required`必须为`true`;形成任何否定性结论前重新请求全部官方来源。manifest变化时,使用`publish_text_cas.py`在同一事务中备份旧正文、失效`§4.pre`和`§4.1-§4.8`并改绑真实路径及SHA-256;并发冲突或任一校验失败时abort,不得以本地PDF继续。
   **事件段落规范化**:本步“逐类官方查询后写证据包”仅描述`collect_event_evidence.py`内部行为,调用方不得绕过采集器直接构造bundle。`events-<AS_OF>.json`是首选输出基名;构建器返回内容寻址版本时必须持久化该真实路径。滚动窗口类计划对窗口前已发生但AS_OF仍未结案的调查设置`include_open_before_start=true`,主体名册包含审计机构。
6. **PDF预抽取cache**:参与6年承诺表和10年资本分配测试的每份`_extracted/<pdf-stem>/text.md`缺失时,`--auto`自动运行`uv run python scripts/extract_pdf.py <pdf>`批量抽取并在失败时持久化需人工终态;只有`--interactive`显示执行或使用raw PDF的选择。raw PDF路径必须进入机器引用复核,不得声称存在抽取cache。

### Step 2 — 模式判定 + Output 准备

1. **解析 invocation 参数**:
   - 无 `--target-profile` → Mode A
   - 有`--target-profile <path> --section <part1/§4|part1/§4.pre|part1/§4.1-§4.8> --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> --auto|--interactive`→Mode B;显式定向时保留该复合section ID,不得归一为整个§4

2. **Mode A 准备**:使用resolver返回的`data/filings/<ticker>/runs/<run-id>/report.md`。`created`时写minimal header；`resumed`时加载同run报告并迁移缺失字段；`reused`不进入本步：

   ```markdown
   # <中英文公司名> 管理层分析 — <ticker>

   **研究者:** <git config user.name>
   **报告日期:** <today>
   **信息截止日（AS_OF）:** <AS_OF>
   **证据阶段:** <未建立/已绑定>
   **年报manifest:** data/filings/<ticker>/manifests/annual-reports-<AS_OF>.json
   **年报manifest SHA-256:** <sha256>
   **监管事件manifest:** data/filings/<ticker>/manifests/events-<AS_OF>.json或其内容寻址版本
   **监管事件manifest SHA-256:** <sha256>
   **counterpart_filing_manifests路径及SHA-256映射:** <JSON对象或{}>
   **模式:** standalone
   **管理层否决:** <否/是—原因/需人工—原因>
   **人工处理清单:** <无/逐项列出>
	   **运行状态:** <进行中/需人工/已完成/已否决>
   **失败原因:** <无/具体错误>
   **management_pending:** <true/false>
   **pending_gate:** <true/false>
   **unresolved_rows:** <JSON数组>

   ## §4.pre 风险一票否决前置扫描
   | 类别 | 判定 | 证据来源 | 触发? |
   |---|---|---|---|
	   | 道德风险其他事项 | 欺诈、操纵股价、内幕交易正式处罚或生效纪律处分;排除专门归入虚假陈述处罚记录的事件 | 官方处罚或纪律处分 | 是/否/需人工 |
   | 大股东占款 | 已证实违规资金占用 | 监管、审计或交易事实 | 是/否/需人工 |
   | 关联输送 | 已证实违规关联交易或股东利益输送 | 生效监管文件和年报附注 | 是/否/需人工 |
   | 虚假陈述处罚记录 | 上市以来正式处罚或生效纪律处分 | 证监会/SFC/交易所 | 是/否/需人工 |

   [扫描结论+引用+置信度]

   ## §4.1 专注主业+董事长5年评估
   [待填写]

   ## §4.2 承诺vs兑现5年表
   [待填写]

   ## §4.3 企业家评估+言行一致（≥2事件）
   [待填写]

   ## §4.4 企业文化
   [待填写]

   ## §4.5 内部治理结构
   [待填写]

   ## §4.6 以股东利益为导向
   [待填写]

   ## §4.7 股权结构
   [待填写]

   ## §4.8 大股东与上市公司利益一致性检查
   [待填写]

   ## 总结与结论
   [合格 / 有保留 / 弃权]
   ```

以下三道gate完成条件由Mode A和Mode B共享。Mode A恢复run时也必须逐行执行，机器字段或section置信度不能替代逐行校验。

3. **Mode B准备**:读取`<target-profile>`、`--filing-manifest <absolute-json-path>`和`--event-manifest <absolute-json-path>`;拒绝内联JSON、相对路径和不存在或无法解析的文件。从profile的Part 0解析ticker、exchange和AS_OF。年报路径允许仓库内`data/filings/<ticker>/manifests/annual-reports-<AS_OF>.json`或`annual-reports-<AS_OF>-<content-sha256>.json`,事件路径允许`events-<AS_OF>.json`或其内容寻址版本;两者唯一准绳都是Part 0持久化路径及SHA-256完全一致。annual manifest标量`查询发行人代码`必须等于`Part 0查询发行人代码映射[exchange]`;event manifest的`查询发行人代码映射完整相等`,不得把标量和映射直接比较。A+H时还逐项绑定Part 0的`counterpart_filing_manifests`,并重放逐法域官方年报目录。两个manifest顶层的`ticker`、`exchange`和`AS_OF`必须逐项等于Part 0,查询参数中的发行人也必须与该ticker和exchange一致;任一不符立即abort,不能只凭canonical路径信任身份。event manifest顶层`live_revalidation_required`必须为`true`,每个事件必须读取`offense_type`、`legal_effect`、`subject_role_at_occurrence`和`issuer_connection`;字段缺失立即返回父skill重建。每类事件重放必须读取manifest持久化的`http_method/request_encoding/request_headers/query_params/response_schema/response_adapter`,不得假定GET、query编码或固定分页字段;缺少任一适用字段立即返回父skill重建。主体名册同样读取其`source_url/http_method/request_encoding/request_headers/query_params/response_schema/response_adapter`,按对应请求契约重新请求主体名册,不得使用构建器固定的GET+query请求契约;复核实时响应哈希、结果总数和完整主体列表,任一变化都abort并要求父skill重建。annual-report manifest必须记录官方目录查询URL、查询参数、响应哈希、候选总数和每个财年的全部候选版本;每个候选版本必须含财年、报告期末日、完整披露时间、公告标题、报告类型、有效状态、替代关系、公告ID或官方URL和是否为选中版本,只有选中版本必须含绝对路径和文件SHA-256。使用保存的URL和参数重新请求官方目录并重算响应哈希;逐候选比较官方元数据,公告ID/URL、标题、报告类型、披露时间、有效状态和替代关系必须与新响应一致,不能只比较候选ID集合。形成任何否定性结论前,按event manifest保存的完整请求契约重新请求全部分页,复核响应哈希、结果总数和逐事件内容哈希。对每个选中版本重新下载选中官方URL到临时文件,计算官方文件SHA-256并与本地文件重算SHA-256及manifest值三方一致后删除临时文件。随后验证候选总数、每财年唯一选中版本、排序和逐年连续性;缺失中间年份或任一校验失败时返回父skill重建。在判断任何section已完成之前比较重建前后的manifest;manifest重建或live revalidation发现内容变化时,父skill先备份现有§4正文,再使旧`§4.pre`和`§4.1-§4.8`全部失效并重新调用本skill,不得继续复用旧完成状态。

   **Mode B路径规范化**:年报和事件manifest都可使用canonical或内容寻址版本,唯一准绳是其绝对路径和SHA-256与Part 0持久化绑定完全一致。

   监管事件manifest必须覆盖管理层、实控人及发行人上市以来全部欺诈、操纵股价、内幕交易、虚假陈述和财务造假正式处罚或生效纪律处分,以及上市以来全部已证实的大股东资金占用、违规关联交易和股东利益输送;另覆盖AS_OF前至少3年的审计机构变更、审计机构监管调查、年报重大更正重述、实控人刑事立案、年报逾期披露和不属于前述历史类别的其他监管事件。每类都保存官方查询URL、参数、响应哈希、结果总数和全部命中或明确`未检出`;重新请求后校验响应哈希和结果总数,并逐事件比较类别、标题、日期、状态、文书URL及内容哈希,不能只比较命中ID集合。§4.pre任一行要写`否`,必须有对应官方类别的完整负面查询记录,不能用单个年报引用代替监管事件manifest。

   在Part 1中定位`## §4管理质量与企业文化`,再按`§4.pre`和`§4.1-§4.8`标题分别记录边界和置信度状态。只生成并更新未完成的目标section。恢复顺序固定为:先迁移gate的旧`已跳过`,再判断终态;必做gate不得`已跳过`。`高/中/低`且非占位符视为已完成的一般规则仅适用于非gate;管理层必做gate`§4.pre/§4.2/§4.8`的旧`已跳过`先迁移为`需人工`。

   - **`§4.pre`完成条件**:风险表固定4行,4行均为合法状态且逐行证据和引用存在,扫描结论与逐行状态一致,没有`需人工`、缺失状态或其他未决行;同时section置信度为`高/中/低`且正文非占位符。任一条件不满足都不得视为完成。
   - **`§4.2`完成条件**:可用历史能够形成的比较行全部存在;每个可量化行都保存`指标ID、单位、口径`、guidance、actual、目标方向、比较方法和绝对差,每行必须持久化`directional_miss`;resume从该列逐行重建后置否决,不得从结论文字反推。百分比gap仅适用于`guidance>0`且目标方向为至少达到的行,此时`gap=(guidance−actual)/guidance`必须可复算且gap计算有效;上限、减亏、亏损或其他非正目标按原文方向和绝对差判断,gap写`N/A`,不得因此卡死gate。只有官方明确未提供量化指引且有年报页码或公告URL时,该行才可写不适用并说明原因;未取得证据、抽取失败或来源缺失必须写`需人工`,不得以高/中/低清除gate。汇总结论和引用存在并与逐行结果一致;没有`需人工`、缺失比较或其他未决行;同时section置信度为`高/中/低`且正文非占位符。任一条件不满足都不得视为完成。
	   - **`§4.8`完成条件**:10行基础清单全部存在,每行均携带`状态、严重度、证据、引用`;银行还必须包含银行4行扩展,逐行覆盖银行关联授信、银行关联存款、银行关联资产转让和银行关联担保。结论与全部适用行状态一致,没有未决行;同时section置信度为`高/中/低`且正文非占位符。§4.8任一清单行含`需人工`时,即使section置信度为`高/中/低`,仍判为待决gate并返回`management_pending=true`;银行4行扩展属于清单行。
	   - **`§4.1/§4.3-§4.7`完成条件**:§4.1必须覆盖5年战略连贯性、主业聚焦和跨界并购;§4.3必须有至少2个含日期、承诺、行动和结果的言行一致事件;§4.4必须用员工、客户或供应商可核事实检验文化,不得用口号占位;§4.5必须覆盖董事会独立性、审计委员会、提名委员会及适用jurisdiction治理材料,A+H两地均有引用;§4.6必须完成分红、回购、并购、债务或银行替代的4项资本分配测试及聚合;§4.7必须覆盖实控人、持股链、质押、交叉持股和控制权变动。每节都要求正文非占位、结论与逐项证据一致、至少一条可复核机器引用、无未决行且置信度为`高/中/低`;任一缺失不得在resume时跳过。

   `需人工`是待决终态,保持原文且自动模式不重派;非gate的`已跳过`仅在模板明确允许时保留。后续逐section更新,不能替换整个§4 block。

	   显式定向§4.x时只生成并返回该section,不得扩大为整个part1/§4或顺带更新同阶段其他section。若前置gate是未决或缺证,返回`dependency_failure`及真实`unresolved_rows`;若同时已有持久化否决,同一dependency_failure响应必须保留`draft_veto=true`及原否决reason/citations,未决行清零后才转为`vetoed`。若前置gate只有已证实否决而无未决行,返回`terminal_status":"vetoed"`、`draft_veto=true`、原否决reason/citations和空draft_sections,不得伪造未决行或降级为待人工。不得代跑其他section。

### Step 3 — 分阶段派subagent抓年报

按未完成section最多派3次。Mode A由本skill复核或本地确认后原子写入standalone报告再进入下一阶段。Mode B无论`--auto`还是`--interactive`都不写target-profile,每次只返回当前阶段草稿和结构化flags;Mode B由父skill确认并落盘,再重新调用本skill进入下一阶段:

Mode A交互模式和全部Mode B调用只返回草稿handoff或结构化空草稿终态;对应确认者accept前不得保存。Mode B已有否决的空草稿终态也只由父skill消费,子skill不落盘。

1. **阶段A**:只生成`§4.pre`;主agent立即检查前置否决。触发时Mode A `--auto`保存证据、把`运行状态`写`已否决`并返回handoff;Mode A交互accept后执行同一终态写入。Mode B以`terminal_status=success,draft_veto=true`返回本阶段草稿、reason和citations,父skill接受前不得保存,且不派后续阶段
2. **阶段B**:只生成尚未完成的`§4.1-§4.2`;`§4.2`完成后立即做系统性画大饼后置否决。触发时Mode A `--auto`保留已完成内容并返回handoff;Mode A交互模式返回草稿handoff。Mode B以`terminal_status=success,draft_veto=true`返回当前草稿及否决证据,由父skill单次原子保存
3. **阶段C**:仅在前两道gate通过后生成尚未完成的`§4.3-§4.8`;完成后按§2.7.3检查`§4.8`。本阶段新发现的已证实否决按Mode B的`success+draft_veto`草稿handoff返回;§4.8存在`需人工`时不得写`0触发`,改写`存在未决项`并返回人工处理清单

任一阶段的必做gate为`需人工`且不存在已证实否决时,Mode B返回`terminal_status=pending`、非空`draft_sections`、`management_pending=true`、`pending_gate=true`和真实`unresolved_rows`,停止后续阶段且不预判否决。`需人工`时返回`management_pending=true`。已证实否决与未决行并存时同一pending响应还返回`draft_veto=true`、非空`reason/citations`;未决行不得覆盖已证实否决,也不得覆盖profile中已有持久化否决。任一section出现未决行都适用规则:Mode B返回`terminal_status=pending`和`management_pending=true`;非gate section使用`pending_gate=false`,保存该section未决终态并阻断估值,不得伪装成gate。Mode A也在显示本地菜单前原子持久化pending状态、人工处理清单和未决正文;Mode B返回后,父skill先原子持久化pending草稿、人工处理清单和三个pending字段,再显示任何交互菜单。两种模式都不得让`defer/exit`丢失未决证据。`--auto保留pending终态并退出`,不得显示菜单或循环重派;交互模式由Mode A本地菜单或Mode B父skill显示`edit/research more/exit`解除路径:`edit`修改未决行后重新逐行校验,`research more`携带未决行和hint重新调用本skill处理未决行,`exit`保留pending终态。目标section未决行清零前不得accept为已完成。

pending gate解决后或非gate section的pending解决后,都进入同一路径。任意management pending解决后,必须基于已接受正文重新校验本次目标section和三个gate。只有本次目标的未决行全部解决时,才移除已解决行对应的人工处理清单项并从全体管理层section重建`unresolved_rows`;全局未决行清零时设置`management_pending=false`,否则保持true。非gate section解决时`pending_gate`按三个gate当前状态重算,不得沿用旧值;三个gate均无未决时设置`pending_gate=false`。随后从`§4.pre、§4.2和§4.8`重新计算management_veto并重新计算阻断原因集合,不得沿用旧handoff、旧草稿flag或只删除`unresolved_rows`。section正文、人工处理清单、两个pending字段、否决字段、引用和阻断原因集合必须在同一次原子写入中一起持久化;任一步校验或写入失败则整组保持原状态。交互模式只对Mode A本地accept或Mode B父skillaccept的修订执行该原子写入。

交互模式命中否决只生成`draft_veto=true/reason/citations/draft_sections`;Mode A本地accept后原子写入standalone报告并转为`management_veto=true`;Mode B无论auto或interactive都返回`draft_veto=true`和`management_veto=false`,父skill先在内存中重算`management_veto=true`及联动字段,再与正文通过同一次原子写入持久化。用户edit时必须根据已接受正文重新计算,不能沿用草稿flag。

每阶段派ONE`general-purpose`子agent,prompt英文,强制中文输出。共用prompt必须包含:

- ticker, 中英文公司名, exchange, report_date
- `AS_OF证据截止日`和event manifest绝对路径;所有年报、处罚、公告、任职和交易事件都不得使用AS_OF之后发布或发生的证据
- 最近10个财年或上市以来全部年报的extracted`text.md`绝对路径（优先）或raw PDF兜底,以及可用招股说明书路径;N≥6时做5个完整跨年比较,N<6时按实际N-1个比较并降置信度
- **承诺 vs 兑现5年表骨架**（§2.1.1）:要求子agent逐年抽guidance、actual、目标方向、比较方法、绝对差、gap和`directional_miss`,每行带年报页码。百分比gap仅适用于`guidance>0`且目标方向为至少达到的行;上限、减亏、亏损或其他方向性目标按原文边界和绝对差判断,gap写`N/A`,同时明确`directional_miss=true/false`。连续未达只标“guidance不可信”风险;证据置信度不因管理层未兑现而降低,仍按来源完整性确定
- **董事长5年评估问题列表**（§2.2）: ① 战略连贯性 ② 战略 vs 实操 ③ 言行一致检验, 必须 ≥ 2事件（日期 + 承诺 + 结果）
- **股东回报 checklist**（§2.3）: 分红5年曲线/回购记录/关联交易/股权激励/高管增减持
- **审计变更扫描**（§2.4）: 审计所/董秘 / CFO 3年内变更记录
- **董监高结构**（§2.5）: 核心成员背景 + 在任年限 + 薪酬 vs 业绩
- **治理监督报告路由**（§2.6）:若年报披露监事会则引用非模板化段落;A股未设监事会时查独立董事述职、审计委员会和内部控制评价;港股或其他单层董事会发行人查独立非执行董事、审计委员会、提名委员会和`Corporate Governance Report`。每条治理引用保存`jurisdiction=SH/SZ/HK`;A+H必须同时命中内地和香港适用材料
- **道德风险附加检查**（§2.7）:先扫前置否决项;系统性画大饼必须在§4.2表完成后判断;§4.8按reference生成10行基础schema,银行额外生成银行4行扩展
- **财务分配4大测试**（§2.8）:识别为银行时只派发§2.8银行资本分配替代bundle,逐项检查ROA/RORWA、分红与内生资本、核心一级资本、拨备与信用成本、关联授信和股权稀释;非银行才派发通用ROE稳定性、分红vs回购、并购克制和债务政策。两类均输出10年窗口实际数据及`通过/中间/不通过/证据不足`;窗口不足时写实际年数并按§2.8聚合
- **禁用空话**: "管理层优秀/战略正确/执行力强/具企业家精神" 无具体佐证一律退回
- **数字必须可追溯**:表格单元格可直接带页码或URL;Mode B叙述段数字写入本section`**引用:**`逐条映射。调用`read-filing`Mode B时直接消费默认完整`facts/citations/warnings/screening_flags`,不得用初筛命中缩小管理层责任事实范围

子agent只输出当前阶段且尚未完成的目标section。§2.8结果在阶段C并入§4.6及总结。

### Step 4 — 主 agent 复核

读子 agent 产出。**驳回并重派**若任一:

- 事实缺引用（页码 / URL）→ 改写为 `证据不足, 需人工补充`, **绝不编造**
- 引用、事件或结论使用AS_OF之后发布或发生的证据→退回,按AS_OF和event manifest重新查询
- 言行一致检验 < 2事件, 或事件缺日期/结果 → 退回
- 承诺vs兑现表缺少已声明证据窗口内可形成的比较→退回补齐;上市历史不足时接受N-1行并要求低置信度
- §4.2任一完成行缺`指标ID、单位、口径`→退回补齐
- §4.2只有官方明确未提供量化指引且有页码或URL时才可写不适用;未取得证据或抽取失败必须写`需人工`,不得以高/中/低清除gate
- §2.8缺任一测试、窗口、数据或`通过/中间/不通过/证据不足`结论→退回补齐
- 银行输出通用ROE杠杆或债务政策测试,或遗漏银行替代指标→退回并按§2.8银行bundle重派
- §4.5遗漏提名委员会或A+H治理引用未同时覆盖两个jurisdiction→退回补齐
- §4.8任一完成行缺`状态、严重度、证据、引用`→退回补齐
- §4.8存在`需人工`却写`0触发`或未返回人工处理清单→退回
- 空话撑起填写区 → 退回重写
- Mode B 场景: 子 agent 填了主 profile §4以外的 section → 退回重做

**重派上限**:Auto最多重派2次,每次只补明确缺口;耗尽后写`需人工`,返回`management_pending=true`及按目标section计算的`pending_gate`,并停止当前section自动循环。必做gate未决时停止后续阶段;非gate section未决时保存真实状态并按统一pending解除路径恢复。Interactive只由用户`research more`触发重派;用户未选择时不得无限驳回。

Acceptable后写中文终稿。`§4.1-§4.8`各自填写`**引用:**`、`**置信度:**`和`**管理层口径校核:**`;`§4.pre`按模板只填写风险表、扫描结论、引用和置信度,不得增造字段。

### Step 5 — Output

Mode A使用全局`## 机器引用清单`;Mode B每个draft section使用模板内`**机器引用清单:**`,两者都要求每个已完成section至少一条非占位引用。联合类型为:`source_type=filing_text/filing_pdf`时含`section_id/jurisdiction/source_type/artifact_path/source_pdf_sha256/artifact_sha256/page/quote`;`source_type=event_document`时含`section_id/jurisdiction/source_type/event_manifest_sha256/document_url/artifact_path/content_sha256/artifact_sha256/page/quote`,HTML文书的page可为null。artifact_path必须是最终持久artifact的绝对路径。Mode B每个返回的draft section必须至少有一条`section_id`完全相同的citation;citation的section_id还必须属于当前stage,Stage A只能引用`part1/§4.pre`,不得引用§4.8。resume时逐条复核机器引用,任一不符即按该引用自身的`section_id`失效对应section;缺失或未知section_id时fail closed并失效全部管理层section。

**Mode A**:
- 使用Step 2选定的standalone路径,先记录standalone基线SHA-256,生成完整draft后运行`uv run python scripts/publish_text_cas.py --source <draft-path> --target <standalone-path> --expected-sha256 <baseline-profile-sha256> --guard <bound-annual-manifest-path>:<sha256> --guard <bound-event-manifest-path>:<sha256> --guard <counterpart-filing-manifest-path>:<sha256>`;非A+H省略counterpart guard,并发冲突或guard变化时不得覆盖
- 发布前运行`uv run python scripts/download_filings.py --revalidate <bound-annual-manifest-path>`和`uv run python scripts/build_event_manifest.py --revalidate <bound-event-manifest-path>`;A+H还逐一重验证`counterpart_filing_manifests`,全部通过后才执行CAS
- 每次保存前重算两个manifest文件SHA-256并与本轮已复核值一致，把路径与已持久化SHA-256同正文一次原子写入。恢复时先核对两个路径与checkpoint哈希；输入变化由resolver创建增量子run，不得把当前canonical文件冒充旧证据
- Mode A不存在父skill;`accept`、自动重试耗尽或交互pending菜单显示前,把section正文、`**管理层否决:**`、`**人工处理清单:**`、`**运行状态:**`、`**management_pending:**`、`**pending_gate:**`和`**unresolved_rows:**`在同一次原子写入中保存。存在未决行时三个机器字段必须反映真实未决状态且运行状态写`需人工`;交互模式选择exit时保留pending终态,恢复时从持久字段继续。未决清零且全部gate通过后才写`已完成`
- 最末尾补`## 总结与结论`—3选1:`合格/有保留/弃权`
- 若结论=弃权,额外加`> ⚠️ 管理层道德风险:<描述>.建议主value-profile在同一原子事务中写Part 0管理层否决:是—<原因>,并写估值阻断:是—管理层否决。`

**Mode B**:
- 无论`--auto`还是`--interactive`都不直接写target-profile,仅返回`draft_sections`和`management_veto/management_pending/pending_gate/reason/citations/unresolved_rows`等结构化flags,由父skill复核并原子写入
- 返回对象必须通过`references/mode-b-response.schema.json`校验。schema校验只是必要条件,主agent还必须逐section执行完成条件,并验证每条event citation的`event_manifest_sha256`逐条等于顶层`event_manifest_sha256`;不相等立即拒绝。`draft_sections`按精确标题逐section包含未完成目标:`§4.pre`只含风险表、扫描结论、引用和置信度;`§4.1-§4.8`包含各自填写区、引用、置信度与管理层口径校核;每个draft section包含`**机器引用清单:**`
- draft_sections的键必须是canonical复合section ID。全stage调用时键集合必须恰好等于当前stage中尚未完成的section;显式定向调用时键集合恰好等于该精确目标,不要求补齐同stage其他section。
- 返回值必须是以下JSON对象,不得增加第二种顶层形态:
  ```json
  {
    "schema_version": "1.0",
    "terminal_status": "success",
    "failure_reason": null,
    "stage": "A",
    "target_sections": ["part1/§4.pre"],
    "draft_sections": {"part1/§4.pre": "<完整section正文,含**机器引用清单:**>"},
    "draft_veto": false,
    "management_veto": false,
    "management_pending": false,
    "pending_gate": false,
    "filing_manifest_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "event_manifest_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "counterpart_filing_manifest_sha256s": {},
    "workflow_complete": false,
    "reason": null,
    "citations": [{"section_id":"part1/§4.pre","jurisdiction":"SZ","source_type":"event_document","event_manifest_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","document_url":"https://official.example/document","artifact_path":"/absolute/evidence/document","content_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","artifact_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","page":null,"quote":"<exact quote>"}],
    "findings": [{"canonical_finding_id":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","owner_skill":"management-analysis","judgment_domain":"management_integrity","finding_type":"integrity_risk","subject_type":"management_team","subject_id":"000001.SZ/management","occurrence_date":"2025-01-15","canonical_evidence_ids":["eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"],"severity":"warning","evidence_grade":"high","judgment":"基于已核验证据形成的管理层判断","citation_ids":["ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"]}],
    "unresolved_rows": [],
    "action_requests": []
  }
  ```
  失败响应沿用同一顶层schema,例如`"terminal_status": "failure"`和`"failure_reason": "<preflight或live revalidation失败的具体证据>"`,并返回非空`action_requests=[{"type":"rebuild_evidence","reason":"<具体漂移>","citations":[]}]`。当前stage已生成草稿但含未决行时写`"terminal_status":"pending"`及具体`failure_reason`,同时返回非空draft_sections和unresolved_rows、`management_pending=true`、按目标section计算的pending_gate及`workflow_complete=false`;可并发返回`draft_veto=true`及非空reason/citations。profile已有持久化否决也必须回显为`draft_veto=true`并返回原reason/citations,确保pending响应可无损resume。依赖失败写`"terminal_status": "dependency_failure"`及`"failure_reason": "<未通过的前置gate及证据>"`;dependency_failure时同时满足`draft_sections={}`、`management_pending=true`、`pending_gate=true`并返回真实unresolved_rows,已有否决时还保留`draft_veto=true/reason/citations`。
		  `terminal_status`只允许`success/pending/failure/dependency_failure/vetoed`。`success`表示当前stage草稿通过schema和本stage完成条件,因此必须`management_pending=false/pending_gate=false/unresolved_rows=[]`;本stage新发现否决时仍返回`success+draft_veto=true`以携带待父skill保存的草稿。`pending`表示当前stage草稿必须先持久化但仍有未决行,不得抹除同时返回的draft_veto或profile中已有持久化否决。只有Stage C全流程调用已通过§4.pre及§4.1-§4.8时才返回`workflow_complete=true`,其余stage成功均为false。preflight或live revalidation失败为failure。显式定向调用只有前置gate未决时才返回dependency_failure、`management_pending=true/pending_gate=true`及真实未决行;前置gate已在profile中持久化否决时返回`terminal_status":"vetoed"`、空draft_sections、`draft_veto=true`、`management_pending=false`及原reason/citations。`stage`只允许A/B/C。success或pending的draft_sections键必须是canonical复合section ID;每个返回键至少有一条相同section_id的citation,且citation必须匹配stage;`draft_veto=true`时reason非空且citations至少1条;所有已完成section至少一条非占位机器引用,所有引用不得晚于AS_OF。
- `findings`固定`judgment_domain=management_integrity`,主体只能是管理团队、董事、CFO、实控人或其他管理责任人。每项ID按`sha256(judgment_domain|subject_type|subject_id|finding_type|occurrence_date|sorted(canonical_evidence_ids))`生成。财务造假、资金占用或关联交易证据可以复用,但本skill只判断管理层诚信、尽责和治理响应,不得复制`financial-redflag-scan`对公司财务的severity或judgment。
- 不改父级§4说明、HTML注释、section标题或Part 1以外内容
- 任一目标section不存在或重复定位时立即报schema不兼容,不得猜测边界
- 若本次stage触发一票否决,Mode B无论auto或interactive都返回`terminal_status=success`、含Part 1证据的草稿、`draft_veto=true`、`management_veto=false`及`reason/citations`;父skill先在内存中重算否决及联动字段,再与正文单次原子写入。只有调用开始前已持久化的前置否决才返回`terminal_status=vetoed`和空草稿。子skill不直接修改Part 0、Part 1或Part 4
- 只有全部§4.pre和§4.1-§4.8完成条件均通过、无未决行且引用有效时,全流程调用才能返回`workflow_complete=true`并允许standalone写`已完成`;定向调用或中间stage的success只代表目标stage通过,不得把整份报告标完成

**确认策略**:自动模式不得显示菜单:Mode A的`--auto`复核通过后直接保存,Mode B的`--auto`只返回草稿。Mode A的`--interactive`一般显示`[accept/edit/research more/exit]`,pending时先保存再仅显示`[edit/research more/exit]`。Mode B的交互确认由父skill Step 3d统一负责,子skill不显示第二套菜单。

---

## §4 Policy

- **中文输出**: 填写区/引用/置信度/管理层口径校核/总结结论均中文
- **中文空格规则**:只禁止两个中文字符之间出现不恰当空格;不禁止中文与英文或数字之间为可读性保留正常空格
- **引用落点**:Mode A可在数字后带`(年报-YYYY.pdf p.NN)`;Mode B遵守父profile契约,表格单元格可带页码,叙述段集中到本section`**引用:**`
- **禁用8条空话**: "管理层优秀/战略正确/执行力强/具企业家精神/稳健经营/锐意进取/勤勉尽责/诚信专业" 无具体佐证 → 退回
- **不大段拷贝年报**: 抽取关键数字 + 页码; 原话仅1-2句引用论证言行一致, 不整段复制

---

## §5 MUST NOT

- MUST NOT 编造数字/日期/承诺内容。无来源写 `待补充 — 年报未披露`
- MUST NOT 跑 `git commit`——用户自 commit
- MUST NOT Mode B 下改主 profile 的 §1-§3 / §5 / §Q* / Part 0等其他 section
- MUST NOT Mode A 下把其他 section 的内容（护城河/估值/排雷）写进本 skill 输出——本 skill 仅管管理层
- MUST NOT 用英文写 profile 内容
- MUST NOT 没有年报 PDFs 就开干 (Mode A); 若 Mode B 且主 skill 漏做 Step 1, 退回主 skill 报错

---

## §6 References — 共享自 value-profile 主 skill

- `references/related-party-alignment.md`—§4.8唯一的10行schema、证据要求和状态映射
- `../financial-redflag-scan/references/thresholds.yaml`—跨skill共享阈值与银行矩阵的唯一来源
本 skill **引用**以下 reference（不复制内容）:

- `.claude/skills/value-profile/references/valuation.md` §2 "管理层指引/承诺兑现" — 3年后净利预估的管理层 guidance 权重
- `.claude/skills/value-profile/references/discipline.md` §2 "认错 > 坚持" — 管理层认错纪律的映射
- `.claude/skills/read-filing/SKILL.md` §2.5.3—关联交易字段和披露要求;其他应收款见`../read-filing/references/statement-reading.md`§3;应交税费按年报对应语义附注定位
- `.claude/skills/value-profile/references/moat-framework.md` §3.4—ROE稳定性及杠杆校正
- `.claude/skills/financial-redflag-scan/references/fraud-library.md` §1 "风险清单" — 管理层道德风险的形式化阈值

派子 agent 时, 若需更深操作手册, 在 prompt 里明确告知 "reference 路径 = `.claude/skills/value-profile/references/<filename>.md` 第 N 节"。

---

## §7主 skill 调用契约（Mode B）

主 value-profile skill Step 3遇 §4时如下 delegate:

```
子 skill: management-analysis
传参: --target-profile profiles/<ticker>-<date>.md --section part1/§4 --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> --auto|--interactive
期望:子skill仅逐section填完尚未完成的§4.pre和§4.1-§4.8后交还控制;模板版本不匹配时显式失败
```

子skill完成后返回主skill。Mode B的`--auto`和`--interactive`都只返回草稿;父skill复核后原子保存并返回Step 2,交互模式由父skill Step 3d处理完整菜单。若返回`pending_gate=true`,父skill必须提供`edit/research more`并重新调用本skill处理未决行,未决行清零前不得accept为已完成。
