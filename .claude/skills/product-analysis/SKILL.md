---
name: product-analysis
description: Use when a user asks what a company truly sells, how its products are designed or delivered, why customers choose them, whether its competitive advantages are real, or requests product, unit-economics, manufacturing, service-delivery, supply-chain, or competitor analysis for a Shanghai/Shenzhen A-share or HK-listed company.
---

# Product Analysis

## §0定位与模式

本skill把公司披露的“主营业务”还原为可观察、可计量、可比较的产品系统。结论必须由产品事实、交付事实、单位经济、客户行为、竞争对标和财报数字共同支撑，不能用品牌故事或管理层口号替代证据。

本skill只判断产品及其相对竞争优势，不给出最终护城河等级、管理层诚信结论或估值。

**覆盖边界**:港股仅支持当前上市发行人;已退市港股发行人超出当前下载器和官方目录适配范围。

**共享证据契约**:运行前必须完整读取`.claude/skills/read-filing/references/evidence-contract.md`。身份、AS_OF、manifest绑定、引用、Mode B写入权、终态和证据漂移只以该文件为准;本skill只补充产品分析特有规则。

**共享运行契约**:运行前必须完整读取`.claude/skills/read-filing/references/run-store-contract.md`。AI自由组织分析正文；共享目录、run隔离和无感resolver只以该文件为准。

### source-discovery handoff

外部行业与竞品补研统一走`source-discovery`,但本skill继续负责最终产品判断。

`source-discovery` must be invoked when product-analysis needs industry structure, product benchmarks, consumer/customer data, specialist vertical research, or competitor evidence beyond issuer filings.
`source-discovery` may supply external context and source ledgers only; `product-analysis` remains responsible for product-system judgments, `moat_handoff`, and final Mode B schema compliance.
`source-discovery` cannot replace `read-filing` annual, event, or counterpart manifests and cannot be used to bypass parent-bound manifest hashes.

市场份额默认请求最近5个完整年度，公开证据允许时扩展至10年，另查AS_OF可得的当年H1/YTD/最新季度。请求必须同时覆盖目标公司与主要具名对手，保存每年排名、份额、市场分母、地域、产品范围、GMV/RSV/零售额等计量口径及来源lineage。旧年份不能替代最近5年验收；缺任一必需年度时连续序列保持unresolved，继续通过当前及历史竞品、拟上市公司申请稿、最终招股书、原始咨询报告和具名券商原报告升级检索。已验证的部分序列仍须单列，不得因连续序列未完成而抹去阶段变化；当期H1/YTD/季度只作独立截面，不年化、不与全年直接比较。不得用发行人会计收入除以行业GMV、RSV、零售额、出货量或用户数推算份额，除非分子分母的期间、地域、产品范围和计量基础完全一致。

外部补研必须先拆成独立`claim_id`，并让每条请求显式写清范围、期间、连续性、最新期和新鲜度门槛。四类最低请求分别是类别规模、市场份额、客户行为和竞品对标；不得把它们打包成一个模糊的“产品力补研”请求。请求体按`research-request.schema.json`校验，事实输入只消费通过`candidate-claim.schema.json`验收的`accepted_candidates`，未决项只消费符合`research-ledger.schema.json`的终态ledger。以下JSON中的字面值只作示意模板；运行时必须从invocation和issuer context派生真实`as_of`、最近完整期间、`required_latest_period`、`geographies`、`industries`、`subject`、`population`、`product_scope`和`measurement_basis`，不得把示例里的年份、AS_OF、地域、行业或主体描述原样复制到真实请求。

Recommended request set:

```json
[
  {
    "schema_version": "1.0",
    "claim_id": "product-category-size-cn-2021-2025",
    "claim_type": "category-size",
    "subject": "China target product category",
    "metric": "annual category retail value",
    "geographies": ["China"],
    "industries": ["target-industry"],
    "population": "end customers in the target category",
    "product_scope": "target product category only",
    "measurement_basis": "category retail value",
    "period_start": "2021",
    "period_end": "2025",
    "frequency": "annual",
    "continuity_required": true,
    "required_latest_period": "2025",
    "accepted_units": ["CNY million", "CNY billion"],
    "definition_constraints": [
      "must include market denominator",
      "must preserve publisher methodology and scope notes",
      "published within 18 months of AS_OF"
    ],
    "value_status_allowed": ["observed", "historical-estimate"],
    "minimum_source_authority": "High",
    "minimum_conclusion_evidence": "High",
    "minimum_originality": "High",
    "minimum_independence": "Medium",
    "independent_cross_check_required": true,
    "absence_claim": false,
    "as_of": "2026-08-02"
  },
  {
    "schema_version": "1.0",
    "claim_id": "product-market-share-cn-2021-2025",
    "claim_type": "market-share",
    "subject": "Target company share in the China target product category",
    "metric": "annual category retail value share",
    "geographies": ["China"],
    "industries": ["target-industry"],
    "population": "category buyers in the target market",
    "product_scope": "target product category only",
    "measurement_basis": "share of category retail value",
    "period_start": "2021",
    "period_end": "2025",
    "frequency": "annual",
    "continuity_required": true,
    "required_latest_period": "2025",
    "accepted_units": ["percentage"],
    "definition_constraints": [
      "must name the subject company and major named competitors",
      "must preserve annual rank and share for every required year",
      "denominator must match the category-size claim"
    ],
    "value_status_allowed": ["observed", "historical-estimate"],
    "minimum_source_authority": "High",
    "minimum_conclusion_evidence": "High",
    "minimum_originality": "High",
    "minimum_independence": "High",
    "independent_cross_check_required": true,
    "absence_claim": false,
    "as_of": "2026-08-02"
  },
  {
    "schema_version": "1.0",
    "claim_id": "product-customer-behavior-cn-2023-2025",
    "claim_type": "customer-behavior",
    "subject": "Customer behavior in the China target product category",
    "metric": "annual repeat-purchase rate",
    "geographies": ["China"],
    "industries": ["target-industry"],
    "population": "current or recent paying customers",
    "product_scope": "target product category only",
    "measurement_basis": "annual repeat-purchase rate",
    "period_start": "2023",
    "period_end": "2025",
    "frequency": "annual",
    "continuity_required": true,
    "required_latest_period": "2025",
    "accepted_units": ["percentage"],
    "definition_constraints": [
      "must use observed customer actions, not survey intent alone",
      "must retain repeat-purchase window and cohort definition",
      "must retain comparison population and channel scope",
      "latest accepted period must be no older than 24 months at AS_OF"
    ],
    "value_status_allowed": ["observed", "historical-estimate"],
    "minimum_source_authority": "Medium",
    "minimum_conclusion_evidence": "High",
    "minimum_originality": "High",
    "minimum_independence": "High",
    "independent_cross_check_required": true,
    "absence_claim": false,
    "as_of": "2026-08-02"
  },
  {
    "schema_version": "1.0",
    "claim_id": "product-competitor-benchmark-cn-2025",
    "claim_type": "competitor-benchmark",
    "subject": "Target product benchmark versus named competitors in China",
    "metric": "price premium versus named same-task same-price-band competitors",
    "geographies": ["China"],
    "industries": ["target-industry"],
    "population": "customers evaluating the same target task",
    "product_scope": "same product scope as the target offer",
    "measurement_basis": "price premium versus named same-task same-price-band competitors",
    "period_start": "2025",
    "period_end": "2025",
    "frequency": "annual",
    "continuity_required": false,
    "required_latest_period": "2025",
    "accepted_units": ["percentage"],
    "definition_constraints": [
      "must compare the same customer task, price band, and product scope",
      "must preserve named competitor SKUs or offer identities",
      "must include named peers plus the applicable leader",
      "latest benchmark snapshot must be no older than 18 months at AS_OF"
    ],
    "value_status_allowed": ["observed", "historical-estimate"],
    "minimum_source_authority": "High",
    "minimum_conclusion_evidence": "High",
    "minimum_originality": "High",
    "minimum_independence": "High",
    "independent_cross_check_required": true,
    "absence_claim": false,
    "as_of": "2026-08-02"
  }
]
```

`product-analysis`只可把`accepted_candidates`写入产品事实、流程事实、竞争事实和正文事实句；未通过gate的candidate、单一路线命中、搜索日志、媒体摘要或空结果都只能留在warning、pending或跟踪项，不能直接升格为事实。

`unresolved_claims`只接收`blocked`、`conflict`或`exhausted`，并保留各自的`claim_id`、`acceptance_failures`、`accepted_evidence`、`conflict_evidence`、`next_escalation`和route lineage。不得把未接受candidate、空路由、`technical-failure`、`access-unavailable`或`request-budget-exhausted`改写成`没有`、`不存在`或事实性absence；对正向产品结论同样不得把unresolved解释成反证。

未接受claim只能沿planner layer单调升级；只有当前layer的适用路线都达到终态后，planner才可返回下一layer。两次重派上限只约束同一路线的执行或输出质量重试，不是全部研究的总次数上限；只要ledger仍显示未尝试且合规的路线或更高layer，claim就保持unresolved并继续升级。

### Mode A—Standalone

- **Invocation**:`/product-analysis <ticker> [--as-of YYYY-MM-DD] [--auto|--interactive]`。只有用户明确要求“完全重新分析”时内部resolver使用`--clean`
- 参数只有ticker时默认进入Mode A，模式默认为`--auto`。
- 独立完成ticker验证、证据准备、分析和复核。
- 输出`data/filings/<ticker>/runs/<run-id>/report.md`。
- 适用于只想看懂一家公司产品、交付系统和竞争位置的请求。

### Mode B—As-subroutine

- 含`--target-profile`时进入Mode B，并要求其值为目标profile的绝对路径。
- 必填参数为`--target-profile <absolute-path> --section <part1/§1.1|part1/§1.3> --ticker <ticker> --year <YYYY> --as-of <YYYY-MM-DD> --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> [--counterpart-filing-manifest <exchange>:<absolute-json-path>]... --auto|--interactive`，并在`--filing <absolute-pdf-path>`和`--extracted-text <absolute-text-path>`中恰选一个。A+H发行人必须逐法域传入全部counterpart。
- Mode B复用父skill已绑定证据，但仍执行路径、SHA-256、AS_OF和目标section校验。
- Mode B不得直接修改`target-profile`，无论`--auto`还是`--interactive`都只返回草稿；父skill是唯一写入者和确认菜单所有者。
- Mode B不调用run store，也不创建run。
- `part1/§1.1`承载产品、流程和单位经济；`part1/§1.3`承载客户选择、竞争阶梯和价值机制。
- 本skill只返回`moat_handoff`事实。最终护城河等级继续由父skill依据`moat-framework.md`计算。

Ticker格式为`\d{6}\.(SH|SZ)`或`\d{1,5}\.HK`；港股代码立即左补零为五位。YEAR是目标完整财年。显式AS_OF必须原样贯穿全部来源，任何证据披露日不得晚于AS_OF。

## §1证据准备

### §1.1共同来源纪律

来源优先级：

1. 交易所文件、招股书、年报、监管文件、官方产品规格和公司可复核运营数据。
2. 供应商或客户官方资料、专利、认证、渠道价格和可复核行业数据。
3. 高质量行业研究和可靠媒体。
4. 用户评论、论坛或社交数据只作线索，不能单独支持关键结论。

对流程、成本和竞争力的管理层表述必须做外部或财报交叉验证。公司称“行业领先”不构成排名证据；公司称“工艺复杂”不构成难复制证据。

### §1.2 Mode A准备

1. 验证ticker、YEAR和AS_OF，先运行`read-filing` Mode A准备或复用目标年报、最多10年连续年报、招股书或上市文件、事件证据和持久抽取文本。
2. 取得annual、event及全部counterpart manifest的真实绝对路径、SHA-256和artifact ID后，调用`scripts/financial_run_store.py resolve`；不得使用`待建立`占位指纹。
3. `resumed`继续checkpoint中的未完成步骤；`reused`直接返回已完成报告；`created`只在返回的run路径工作。正常入口不得询问恢复或新建。
4. 使用返回manifest调用`read-filing` Mode B取得完整`facts/citations/warnings/screening_flags`。缺少完整官方目录、选中报告或哈希时停止，不得用网络摘要代替。
5. 把执行状态保存到run内`checkpoint.json`，正文保存到同run的`report.md`。验证通过的facts、metrics、citations和analyses通过通用或专用内容寻址发布器提升到ticker共享层；输入变化只使依赖artifact失效。

### §1.3 Mode B准备

1. 验证传入annual、event及全部counterpart manifest与父profile Part 0中的路径及SHA-256完全一致；counterpart法域键集合也必须完全相等。
2. 调用`read-filing`Mode B取得目标section完整`facts/citations/warnings/screening_flags`；Mode B默认完整事实语义，不得依赖未持久化的内存事实。
3. `part1/§1.1`和`part1/§1.3`以外的目标立即返回契约错误。
4. Mode B只读现有证据。需要扩窗、重新抽取或补充官方证据时返回`rebuild_evidence`，由父skill执行后重试。

## §2核心分析链路

按以下顺序执行，前一步的输出是后一步的输入。任何一步缺失都不能标记完成。

### Step 1—产品边界

识别真正贡献收入、毛利和现金流的产品组合，不机械使用“营收超过50%”。

1. 以客户任务、价格带、交付方式和经济模型划分产品，不能完全照抄分部名称。
2. 依次比较收入、毛利额、现金贡献、关键资产占用和战略控制力。
3. 单一产品不足50%但多个产品共享客户、成本、渠道或生态时，可以定义核心产品组合，并说明组合关系。
4. 把高收入低利润业务与低收入高毛利业务分开，优先解释利润池而非只解释收入规模。
5. 输出核心、支撑和非核心三档；无法取得分产品利润时明确缺口，不得按收入占比冒充利润贡献。

### Step 2—生产或服务流程

读取`references/process-playbooks.md`，按行业选择一条主流程，可追加一条次级流程。

1. 从需求或产品定义开始，逐步画到客户收到价值和反馈回流，不从工厂或交易环节中途开始。
2. 每个关键步骤填写输入、输出、责任主体、周期、成本驱动、质量控制、关键指标、瓶颈、扩张约束和证据等级。
3. 制造业必须覆盖研发设计、采购、试制、量产、质检、仓储渠道、售后和反馈。
4. 服务、软件或平台必须覆盖需求发现、服务设计、供给组织或开发、交付、质量控制、售后留存和反馈迭代。
5. 外包不等于能力缺失。说明公司控制设计、规格、供应商、良率、排产、质量、交期和成本中的哪些环节。

### Step 3—流程经济性

解释周期、产能、良率、瓶颈、人工、材料、折旧、库存、资本开支和单位成本如何共同形成利润。

1. 选择最接近经济实质的分析单位：单件、单吨、单瓶、单位产能、单门店、单订单、单客户、单点位、单次履约或单活跃用户。
2. 拆分单位收入、直接材料、直接人工、制造或履约费用、渠道费用、获客成本、售后退货和维持性资本投入。
3. 分清固定、半固定和变动成本，说明规模扩大时哪些成本下降、哪些不会下降。
4. 将单位经济与毛利率、销售费用率、存货、合同负债、应收、资本开支和经营现金流勾稽。
5. 公司未披露单位成本时，只能给区间估算。必须列公式、输入来源、假设、上下界和敏感性，不得伪造单点精确值，也不得把估算写成公司披露。
6. 无法形成可复算区间时写`需人工—未披露`，仍可解释成本结构但不能声称成本领先。

### Step 4—客户价值

1. 分别识别购买者、使用者和付款者。
2. 写明客户在什么场景下要完成什么任务，不购买时使用什么替代方案。
3. 按实际决策顺序排列价格、性能、质量、交付、信任、便利、身份、兼容性或服务等购买标准。
4. 判断试错成本、转换成本、复购或留存及愿付溢价，并给可观察证据。
5. 品牌不是答案。必须说明品牌具体降低何种风险、节省何种决策成本或提供何种可观察信号。

### Step 5—相对竞争力

建立竞争阶梯，至少包括直接竞品、替代方案和适用龙头。

1. 直接竞品必须与目标产品服务同类客户、场景和价格带。
2. 替代方案可以跨行业，但必须完成相同客户任务。
3. 适用龙头是同一价值池中的规模、产品或用户心智上限；不同客户和价格带的公司不能因行业相同而强行对标。
4. 从购买决策最重要的维度比较产品性能、质量稳定性、设计速度、单位成本、交付周期、渠道、服务、信任、生态或供应链。
5. 目标不是龙头时，必须写明领先哪些对手、落后龙头的具体环节、差距来源及差距扩大或缩小的证据。
6. “第一”“领先”“难复制”都必须有同口径对比，不能孤立赞美目标公司。

### Step 6—需求侧机制

读取`references/value-mechanisms.md`。只选择解释力和证据最强的2至3项，不强行套满工具箱。

每项机制必须同时回答：

- 客户行为如何证明它存在。
- 哪个财务或运营数字与它方向一致。
- 相比直接竞品或适用龙头处于什么位置。
- 什么反证会推翻它。

高毛利不能单独证明品牌、身份、情绪或稀缺性。高销售费用也不能单独证明品牌弱；必须结合提价后的销量、复购、自然流量、渠道折扣、获客效率和竞品表现。

完成上述机制后，必须输出一个紧凑的`产品竞争力三问结论`，综合回答：

1. **客户为什么选择并持续选择公司的产品或服务？** 区分首次吸引、相对偏好、习惯和真实切换成本；低切换成本不写成“阻止客户离开”，而要判断公司能否在每次购买或续约时重新赢得客户。
2. **现有对手为什么不能靠降价或更高性价比抢走客户？** 指出约束来自能力、成本、渠道、稀缺资源、监管、组织协同还是复制所需时间，并用具名对手检验；对手已经有效抢占客户时直接说明，不得把竞争存在改写成进入壁垒。
3. **新对手携巨资进入，公司凭什么守住并扩大市场？** 同时判断现有优势在资金冲击下是否仍成立，以及下一代产品、服务或爆款来自可重复流程还是单次运气。

对情绪、身份、收藏或社群型产品，必须分别判断经济成本（合同、迁移和资产重建）与心理成本（情感依附、收藏连续性和社群身份），并检查客户是否可以低成本多品牌共存。多品牌共存意味着心理成本可以提高持续选择概率，却未形成排他锁定；不得把没有经济成本写成毫无切换成本，也不得把情感偏好直接写成客户无法离开。

三问按业务自适应：消费品关注吸引力、设计、收藏、社交和持续上新；B2B关注采购标准、投资回报、质量、交付、续约和切换风险；商品型公司允许结论是产品本身没有差异，竞争力来自成本、资源禀赋或可靠交付。每问都要在行文中区分已观察事实、证据支持的推断和未知项，不要求机械添加标签，但不得把推断写成事实。前述表格逐项填完但没有形成三问综合结论，仍视为未完成。

### Step 7—财报映射

每项竞争力必须映射到至少一个可复核数字，并解释因果链而非只做相关性罗列：

- 溢价与产品力→价格、销量、产品结构、毛利率和促销变化。
- 信任与质量→复购、留存、退货、投诉、质保和渠道稳定性。
- 流程效率→单位成本、良率、产能利用率、交付周期、周转和资本开支。
- 生态与转换成本→留存、交叉购买、递延收入、合同负债和迁移成本。
- 供应链能力→库存、预付款、供应商集中度、缺货、交期和扩产回报。

无法取得退货率、渠道库存等指标时写明已查来源和代理指标，不得把“未披露”写成“没有风险”。

### Step 8—失效测试

至少提出两个具体失效条件，每条包含触发事件、传导路径、受影响产品或利润池、可观察先行指标和预计窗口。

候选压力包括技术替代、成本上涨、关键供应商中断、良率或产能失速、渠道库存、价格倒挂、消费降级、竞争者复制、客户集中、监管变化和用户偏好迁移。

失效测试必须能推翻前述竞争结论，不能写“宏观环境变差”这类不可操作表述。

## §3证据等级与完成门槛

### §3.1证据等级

- `高`：一手来源直接支持，流程、期间、对象和口径可复核。
- `中`：一手来源不完整，但至少两个独立来源或可复算代理指标方向一致。
- `低`：主要依赖单一二手来源、不可复核访谈或弱代理指标。
- `需人工`：来源冲突、关键字段缺失，或无法区分披露值与估算值。

每个关键流程步骤、竞争比较和价值机制均要标等级。`低`或`需人工`不能支撑“领先”“难以复制”“成本最低”或“具有定价权”等强结论。

### §3.2引用

可见引用至少给来源名称、期间、页码或URL。机器引用沿用父skill格式：

```text
section_id/source_type/artifact_path/source_pdf_sha256/artifact_sha256/page/quote
```

外部官方网页追加`document_url/content_sha256/accessed_at`。每个已完成section至少一条与section ID完全一致的非占位机器引用。

### §3.3完成门槛

以下任一成立时不得返回完成：

- 无法确定核心产品的收入或利润贡献。
- 制造业没有生产步骤，或服务公司没有交付步骤。
- 单位成本估算缺少公式、来源、假设或敏感性。
- 竞争判断缺少直接竞品、替代方案或适用龙头。
- 非龙头没有龙头差距。
- 价值机制缺少行为证据或财务证据。
- 缺少`产品竞争力三问结论`，或三问没有覆盖持续选择、资本竞争和巨资进入后的防守及持续创新。
- 关键强结论只有`低`或`需人工`证据。
- Mode B绑定、目标section或引用校验失败。

自动模式对非discovery的明确缺口重查最多2次；若缺口已经交给`source-discovery`，两次上限只约束同一路线的执行或输出质量重试，未接受claim必须沿planner layer单调升级，直到terminal ledger到达`accepted`、`blocked`、`conflict`或`exhausted`。全部适用路线终态后仍未接受时返回pending和具体人工动作，不得降低标准或补写想象。

## §4输出契约

收入结构必须先识别年报的分类轴。同一张收入结构表只放一个分类维度；父项和子项必须明确标出包含关系，并分别校验同层级加总。有多层父子分类时采用层级明细表：标题右侧标注`报告期 · 金额单位`，固定使用`收入类别/收入/占总收入`三列，父子关系通过首列缩进表达，金额和占比分列并右对齐；不使用每层单独一列，不使用`rowspan`，不放占位短横线，也不新增数字`层级`字段。IP归属、具体IP、产品品类、渠道和地区等交叉维度分表展示，明确说明不得跨表相加。

### §4.1 Mode A

success或pending都必须保留以下10个栏目，并按此顺序生成。pending只能把未知字段写成`需人工`并列入“待补证据”，不得省略流程、单位经济、竞争比较或失效测试：

1. `## 一句话产品本质`
2. `## 核心产品与利润地图`
3. `## 设计、生产或服务交付流程`
4. `## 单位经济与财报勾稽`
5. `## 客户任务与购买标准`
6. `## 竞争阶梯与龙头差距`
7. `## 核心价值机制`
8. `## 流程和竞争力失效条件`
9. `## 待补证据与跟踪指标`
10. 隐藏的机器引用元数据：将`## 机器引用清单`及其内容完整放入HTML注释

一句话结论同时包含产品、客户任务和经济来源，不用夸张修辞代替事实。
`产品竞争力三问结论`放在`## 核心价值机制`内，位于需求侧机制分析之后；Mode B的`part1/§1.3`也必须保留同名结论。

### §4.2 Mode B

只返回一个结构化对象，并在返回前通过`references/mode-b-response.schema.json`校验。Schema只固定机器信封；`draft_sections`中的正文是自由Markdown，不限制行业表格、段落或流程步骤数量。

```json
{
  "schema_version": "1.0",
  "terminal_status": "success|pending|failure|dependency_failure",
  "failure_reason": null,
  "target_sections": ["part1/§1.1"],
  "draft_sections": {"part1/§1.1": "<markdown>"},
  "product_facts": [],
  "process_facts": [],
  "competition_facts": [],
  "moat_handoff": [],
  "findings": [],
  "citations": [],
  "warnings": [],
  "unresolved_items": [],
  "filing_manifest_sha256": "<sha256>",
  "event_manifest_sha256": "<sha256>",
  "counterpart_filing_manifest_sha256s": {}
}
```

显式调用只返回目标section；父skill需要两个section时分别定向调用，避免一次调用越权改写相邻内容。`moat_handoff`每项包含`claim/evidence/counterevidence/citation_ids/evidence_grade`，不得包含最终护城河标签。

`findings`只判断产品系统，固定`judgment_domain=product_competitiveness`，主体使用`product_system/product/service/business_segment`。每项ID按`sha256(judgment_domain|subject_type|subject_id|finding_type|occurrence_date|sorted(canonical_evidence_ids))`生成；不得把公司财务或管理层诚信判断写入本数组。

`success`要求目标section完成门槛全部通过且`unresolved_items=[]`。`pending`保留可用草稿并列出未决字段；`failure`不返回可保存草稿；`dependency_failure`表示父skill必须先修复证据绑定或前置section。

## §5禁止事项

- 不得把公司在物理上卖什么当作完整产品分析。
- 不得从毛利率、销售费用率或市场份额单个指标直接推出用户心智。
- 不得用行业平均代替同场景、同客户、同价格带比较。
- 不得把复杂、历史悠久、专利多或供应商多自动写成难复制。
- 不得把外包制造自动写成没有制造能力，也不得忽略设计、供应商管理和质量控制。
- 不得编造BOM、单位成本、良率、产能、复购率或渠道库存。
- 不得在Mode B直接写profile或输出估值。
- 不得用英文撰写profile正文。中文字符之间不得出现不恰当空格。
- 用户可见正文遵守`../value-profile/references/profile-writing-style.md`;不得把`close/closed`直译为“闭合”,应按事实状态写“已核实”“已完成判断”“仍缺资料”或“尚不能判断”。
