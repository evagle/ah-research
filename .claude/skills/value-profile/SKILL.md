---
name: value-profile
description: Use when a user asks for a complete value-investing profile or full company research dossier for one A-share or HK ticker,including "/value-profile 600519.SH" or "完整研究0700.HK".
---

# Value Profile Skill

本 skill 是一份给主 Claude Code session 读的指令文档, 结构分三层: **§1投资哲学（信念/心法）→ §2规则（从哲学推出的纪律）→ §3流程（Step 1-6如何执行）**。读者应先把 §1完整通读 internalize, 再查 §2规则, 最后照 §3操作。§4是跨层 operational boilerplate。

**覆盖边界**:港股仅支持当前上市发行人;已退市港股发行人超出当前下载器和官方目录适配范围。

**共享契约**:运行前必须完整读取`.claude/skills/read-filing/references/evidence-contract.md`。公共证据规则不在本skill重定义;本skill只补充父级编排、CAS和最终结论规则。接收判断型子skill响应时,分别按`.claude/skills/product-analysis/references/mode-b-response.schema.json`、`.claude/skills/management-analysis/references/mode-b-response.schema.json`和`.claude/skills/financial-redflag-scan/references/mode-b-response.schema.json`校验机器信封;Markdown正文保持自由。

**共享运行契约**:运行前必须完整读取`.claude/skills/read-filing/references/run-store-contract.md`。正常入口、共享artifact、run隔离和无感resolver只以该文件为准；本skill仍是最终profile的唯一写入者。`source-discovery` must be invoked for macro, industry, valuation context, announcement/regulatory-letter discovery outside existing manifests, specialist vertical research, and current external evidence gaps. `source-discovery` may supply source candidates, access/provenance validation, fallback exhaustion logs, and source ledger handoffs only; `value-profile` remains the orchestrator and only writer of the profile. Annual, event, counterpart, and market manifests remain authoritative for bound financial, regulatory, filing, and market data; `source-discovery` cannot override, replace, or backfill those manifests.

## §0 Skill 运行方式

This skill runs as the **main Claude Code session agent** and orchestrates research via `general-purpose` subagents. It is an instruction document for the main model, not library code. The main agent owns file I/O, user 确认节点, and review; subagents do scoped PDF reads and web research.

**理论血统**: 本 skill 的方法论内核吸收自 `docs/references/tangshufang/methodology.md` 及其深度附录 `docs/references/tangshufang/01-05-*.md`。该5份附录是理论来源, 不在 SKILL / template / profile 正文中反复署名。以下所有 principles / rules / procedures 都已 internalize 为本项目的默认方法, 子 agent 无需再标注"按某某方法"。

---

## §1投资哲学核心原则

本节12条原则是整个分析流程的信念层。每一条都是长期不变的 meta-principle, 不含具体操作步骤。派任何子 agent 前, **主 agent 先在开场白里把本节通读一遍 internalize**; §2规则、§3流程都是 §1的推论。

### §1.1股票是生意的凭证, 不是纸片
**持有股票 = 持有"一只会下蛋的母鸡"分成权**。内在价值 = 未来自由现金流折现之和, 与每日市价无关。市场价格不更新内在价值; 牛市是投资者的"风落之财", 长期复利来自企业内生现金流, 不来自"傻子馈赠"。
违反症状: 把 "最近股价涨/跌了 X%" 当信号, 用 K 线/板块轮动/资金流判断买卖, 把市值当锚。
### §1.2利润三问是估值的承重墙
任何估值动作之前必须先对以下三问给出 "真/假 / 存疑":
① **利润为真** — 经营现金流净额 ≥ 净利润; 销售收现/营收 ≥ 1+增值税率; 应收/存货/商誉结构干净。
② **利润可持续** — 需求10年仍在; 护城河可验证而非声称。
③ **维持利润不需大投入** — 自由现金流 = 经营所得 − **维持性** CapEx（不是全部 CapEx）。长安汽车每年65亿维持性 CapEx 是 "泡沫利润", 需去泡沫化。
三问 **必须全部为真**。任一 "假/存疑" → 25PE 合理估值法不适用, 必须打折或放弃。
违反症状: 看报表 PE 不看 CFO/NI 比值; 未拆维持性 vs 扩张性 CapEx 就算自由现金流。
### §1.3商业模式决定估值方法, 用错方法等于价值陷阱
不同生意的 "3年后净利润可预估度" 差异巨大, PE 不是万能: **强护城河消费/平台互联网适用25PE**; **周期股/资源顶部 PE 低是陷阱, 底部 PE 高是机会, 不适用 PE**; **银行用 PB**; **保险默认回避**; **公用事业用 DCF 简化版**; **高杠杆企业 PE 下调 + 折扣加深到35%**。
违反症状: 给周期股套 PE; 给高成长股40+ PE; 用 PEG 抬 PE 超25; 把高杠杆标的按常规50% 买点算。
### §1.4三年后的确定性 >> 今天的精确性
估值靠 **三年后可预估**, 不靠 **今天精准**。选3年窗口是因为: 短于1年 = 短期博弈（噪声 > 信号）, 长于5年 = 超出绝大多数行业的可预测半径。§1商业模式 + §2成长空间收尾时必须能回答 "这家公司3年后的净利润中枢大约在哪里, 依据是什么"。答不出 → 不适用25PE 估值法, 必须更深折扣或弃权。
违反症状: 追求精准 DCF 到小数点后两位; 或反过来, 用 "长期看好" 敷衍, 不给3年窗口的量化上下限。
### §1.5安全边际是"我错了也不亏", 不是"便宜"
50% 折扣的意义不是占市场先生的便宜, 而是 **给自己估算错误留空间**。即使真实价值只有估算的70%, 50% 买入仍能不亏。判错概率越高（认知不深/行业变化快/管理层难评）**应提高折扣**而不是降低门槛买入。高杠杆企业折扣加深到35% 同理。
违反症状: 把折扣当 "市场情绪", 越跌越机械加仓; 不反思判断可能错, 只反思 "市场先生发癫"。
### §1.6能力圈是硬边界, 写不出具体答案 = 不下注
"看得懂" 的标准是 **能力圈四问** 全能口述具体答案:
① 公司靠销售什么商品/服务获取利润?
② 客户为何从它这里采购, 不选其他机构?
③ 资本天性逐利, 为什么别的资本没抢走它的份额或逼它降利?
④ 假设同行/巨头挟巨资参与竞争, 它能否保住乃至扩张份额?
四问任一答 "抽象空话/品牌复读/结论标签无场景" = 能力圈外, **不下注**, 错过是价值投资的标配。"跨出能力圈下注, 是注定要被别人收割的——早晚而已。"
违反症状: "行业龙头/品牌强大/成长空间巨大/护城河宽广" 这类空话撑起的 §1, 没有产品级拆分、客户场景、挑战者名单、假想敌推演。
### §1.7市场波动 ≠ 信息, 价格不改变价值
格雷厄姆的 "市场先生" 寓言: 市场报价每天变, 企业内在价值几年才变一次。默认动作是 **呆坐不动**。股价上涨不是卖出理由, 估值超区间才是; 股价下跌不是买入理由, 估值进入买点才是。
违反症状: 用 K 线/量价/资金流做决策; 用 "最近表现" 修订研究结论。
### §1.8耐心是资产, 空仓等待不是机会成本
不主动留现金等机会; 但也不为保持仓位而急于投出去。所有持仓都超合理估值 + 没有新标的进入买点 → 自然产生现金, 等下一个买点即可。"单纯持有类现金资产等待股价下跌的所谓仓位管理"是明确反对的。
违反症状: FOMO 驱动的仓位管理; 把 "子弹池" 当择时工具。
### §1.9认错 > 坚持: 下注行为正确 ≠ 下注结果正确
估值判断本身动摇时, 纪律化加仓会从 "遵从体系" 滑向 "赌气/摊低成本执念"。跌破买点第二档/第三档遇新信息（季报/行业变化/三大前提由 "真" 松动到 "存疑"）动摇3年后净利润预估 → **立即停止加仓**, 不再机械摊低成本。正确顺序: ① 回头重审3年后净利润下限; ② 重算合理估值 + 新买点; ③ 再决定新行动（继续加/持有观望/止损重估）。**承认 "我看错了" 是完全合法的结论**。
违反症状: "原计划每跌 X% 加仓" 的机械执行; 用 "市场先生发癫" 掩盖判断已动摇。
### §1.10集中于高确定性 > 分散于平庸
从分散入手（起步 = 指数）→ 看懂一家转一家 → 成熟持有 **4-6家**。超过8家 → 必然有几家没看懂, 回指数。单一持仓上限40%（极端可到50%, 茅台2017-2020）, 下限约10%（不敢重仓 = 没看懂 = 干脆不持）。同行业同时持仓不超2家。
违反症状: 20+ 只股组合, 每只都是 "浅水位"; 或单一仓位 > 50% 而四问/三前提未全过。
### §1.11年报是写给全体利益相关方的文档, 真相在附注
年报读者 = 监管 + 党组织 + 员工 + 地方政府 + 股东 + 供应商 + 经销商 + 投资者 + 媒体 + 竞争对手。价值投资者不是首要读者。因此读年报要 **读出弦外之音**: 哪些段落是合规话术/员工福利信号/地方政绩信号, 哪些才是实质经营信息。**正文可略读, 附注必须逐行读**——应交税费、关联交易、对外担保、其他应收款明细、存货构成、商誉减值测试假设、金融资产4分类是否发生过跨档切换, 实质信息都在附注。
违反症状: 只读正文 "经营情况讨论与分析" 就下结论; 把管理层口径当事实。
### §1.12好生意优先级高于好管理层
三好标准的顺序不可换: **好生意 → 好公司 → 好价格**。一流生意 + 三流管理层通常优于三流生意 + 一流管理层, 因为一流生意的经济商誉能让平庸管理层也挣到钱 (粤高速、长江电力), 而三流生意 + 一流管理层 = 管理层被迫不断重组/转型/跨界, 成功稀少且不可复制。§1 (好生意) 判定 "否" 不要指望 §4 (管理层) 救回; §1判定 "是" 时, §4平庸可接受, 只要不存在 §4风险 (道德/大股东占款/系统性画大饼)。
违反症状: 用 "管理层优秀" 对冲 "商业模式平庸"; 期待明星 CEO 能把垃圾生意做成金矿。

---

## §2规则层

本节是从 §1推出的可操作纪律。每条规则编号 `§2.N.x` 对应原则 `§1.N`, 读者可以追溯每条规则的信念来源。规则不是详细清单——详细清单（如29项排雷、13条 playbook、5步护城河宽/中/窄/弱具体数字）留在 template / methodology 里, 本节只给操作框架。

### §2.1股票 = 生意

- **§2.1.1禁用 K 线/量价/资金流**: 不把 "最近涨/跌 X%" 当决策输入。买卖动作只由估值（§2.3 / §2.5）+ 事实翻案（§2.9）触发。
- **§2.1.2数字必须可追溯**:表格单元格可直接带页码或URL;叙述段数字通过本节`**引用:**`逐条映射到文件、页码或URL,不在正文括号内堆引用。不带可定位来源=未核实。子agent禁止从记忆编数字。选中filing未披露时可写`待补充—年报未披露`;外部核验缺口必须作为unresolved claim输入返回,不得在validated terminal mapping前直接写`证据不足,需人工`。

### §2.2利润三问是前置门槛

- **§2.2.1三项判定** (§3.pre子agent开场白必走),先按exchange和生意类型选口径:
  - **A股非银行**:①审计意见为无保留;带强调事项段的无保留意见不自动判假,按强调事项底层事实及`financial-redflag-scan`独立阈值判断;保留、无法表示或否定意见才判假;②近3年CFO累计≥NI累计,销售收现按`financial-redflag-scan`§2.3适用口径复核;③近5年ROE、毛利率和扣非NI/NI检查利润持续性与资本投入
  - **港股非银行**:①独立核数师无保留意见;②近3年CFO累计≥NI累计。未披露毛额销售收现本身不判存疑,改查应收账款、合同负债、分部收入和经营现金流桥;未披露A股式扣非NI时,从附注明确披露的一次性、投资及公允价值项目还原核心经营利润纯度,无法还原才标`需人工`
  - **银行替代门槛**:①无保留审计意见且资产质量披露可勾稽;②ROA、净息差、不良率、关注类迁徙和拨备覆盖率支持利润可持续;③核心一级资本和内生资本可覆盖风险加权资产增长,不存在反复股权融资依赖。银行不使用常规CFO、毛利率或存货门槛
- **§2.2.2任一假/存疑→阻断数字估值**:三大前提失败只改变投资资格和估值路线,不改变证据置信度。证据完整时继续完成全部定性研究并进入`定性研究终态`,Part 0记录具体失败前提且不输出估值数字、买卖点或仓位;只有来源窗口不足或冲突时才写`需人工`,不得把可靠的负面事实强制降为低置信度。
- **§2.2.3销售收现交叉验证**:仅在报告披露毛额销售收现时计算。应有销售收现=营收×(1+有效VAT税率)−Δ应收账款账面余额−Δ应收票据账面余额+Δ合同负债+Δ预收款项（新收入准则前口径）−本期核销±汇兑影响±合并范围变动/合并处置影响±重分类调整−本期票据贴现−非现金抵账+收回已核销坏账。所有非经营滚动调整按附注披露方向代入,不得默认取0。有效VAT、容差和无法取数时的处理以`financial-redflag-scan`§2.3及`thresholds.yaml`为准。对比现金流量表实际值,背离>5%先查票据背书与口径差异;无法解释或连续2年背离时触发§4.5深调。
- **§2.2.4 auto-mode深调查原则**:Auto mode下,main-agent review发现subagent证据薄弱、空白或论断generic时,先建立research ledger并扩大范围调查。两次重派上限只约束同一来源路线的执行或输出质量重试,不是全部研究的总次数上限。只要research ledger仍有未尝试且合规的独立来源路线,Auto mode不得转为`需人工`;全部路线均已取得结果、确认不适用或记录具体阻断后,仍无法获得关键证据,才写`**置信度:**需人工`和具体失败handoff,加入人工处理清单并退出该section自动循环。不得写中/低后继续或派生为已完成。Interactive mode由用户在Step 3d选择`research more`。

### §2.3商业模式 → 估值方法对照

- **§2.3.1 6类生意估值矩阵**（套用前先判定公司落在哪一类）:

  | 生意类型 | 估值方法 | 买点折扣 | 说明 |
  |---|---|---|---|
  | 强护城河消费/平台互联网龙头 | min(1/rf,25PE) | 50% | 统一封顶25PE,不因公司名称额外抬高 |
  | 周期股/资源/化工/航运/钢铁/水泥 | 不适用单年PE | 40%-50%;叠加高杠杆时35% | 用穿越周期平均NI×成本档倍数;高成本不估值 |
  | 高成长股（年化 > 25%）| 25PE 上限不破 | 50% | 用保守下限; 不用 PEG 抬到40+ |
  | 金融—银行 | 按银行子类型使用0.6-1.3PB×真实净资产 | 35% | 银行PB锚以`industry-overlays.md`§2.4为唯一来源;真实净资产=账面−未计提不良真实损失 |
  | 金融 — 保险 | 默认回避 | — | EV 折现假设多且无法客观验证 |
  | 高杠杆（地产/部分电力/开发商）| PE 下调到8-12 | 35% | 硬指标: 有息负债/净资产 > 1或 / CFO 近3年 > 3 |
  | 公用事业（水电/高速/港口）| DCF 简化版 | 股息率 > rf × 1.3 | 用稳态 FCF / (rf + 2%); 看折旧 vs 维持性 CapEx 差额 |

  同时符合多类时按Step 6主估值路线优先级选唯一主路线,其他类别只追加风险检查和折扣,不得把周期股切回单年PE。"不适用单年PE"仍允许用完整周期平均利润乘成本档倍数;"默认回避"才不输出估值数字。完整准绳见`.claude/skills/value-profile/references/valuation.md`§3。

### §2.4 3年窗口与可预估度

- **§2.4.1 3y 净利润三档必填**: 乐观/中性/悲观, 至少2个业务板块拆解, 每块量 × 价 × 净利率, 每档附具体假设一句。
- **§2.4.2 PE锚与增速无关**:合理PE=`min(1/rf,25PE)`。增速已反映在3年后净利润里,不重复计入PE;任何公司都不得突破25PE上限。

### §2.5安全边际 = 估值错误容差

- **§2.5.1买点/卖点公式**:
  - 仅PE法使用:买点=3y合理估值×50%（高杠杆×35%;必须说明为何判定高杠杆）
  - 仅PE法使用:卖点=min(3y合理估值×150%,当年NI×50PE)——两候选都列,取较低者。高杠杆法不使用PE法双轨卖点,只使用Step 6的PE>15退出条件;银行PB法、周期法和公用事业DCF法也各用自己的退出条件
- **§2.5.2持仓姿态 discrete**:
  - 当前市值<买点→加仓/建仓;首次建仓不超过组合5%,后续每批不超过目标仓位20%,并遵守`discipline.md`§6.3的验证事件
  - 买点 ≤ 当前 ≤ 卖点 → 持有不动（收工睡觉, 每年年报后重估一次）
  - 当前 > 卖点 → 分批清仓（触点卖1/3; 再涨10% 卖1/3; 再涨10% 清仓）

### §2.6能力圈四问是 §1前置条件

- **§2.6.0市场份额证据窗口**:市场份额默认请求最近5个完整年度，公开证据允许时扩展至10年，另查AS_OF可得的当年H1/YTD/最新季度；该请求同时覆盖目标公司与主要具名对手，并保存每年排名、份额、市场分母、地域、产品范围、计量口径和source lineage。旧年份不能替代最近5年验收；缺任一必需年度时连续序列保持unresolved，继续调用`source-discovery`扩展当前及历史竞品、拟上市公司申请稿、最终招股书、原始咨询报告和具名券商原报告。profile必须把已验证部分序列、缺失年份和不可比截面分开写；当期H1/YTD/季度不年化、不与全年直接比较。不得用发行人会计收入除以行业GMV、RSV、零售额、出货量或用户数补份额，除非分子分母期间、地域、产品范围和计量基础完全一致。
- **§2.6.0行业规模、增速与集中度证据窗口**:行业章节必须收集最近5个完整年度的逐年市场规模、同比增速、复合增速和可得的CR5或CR10，公开证据允许时扩展至10年；另收集未来3至5年预测及逐年预测值。行业预测可以作为情景数据保留，不因其为预测而删除，但必须与已发生数据分表，保存预测版本、发布日期、原始数据提供方、委托关系、计量口径和后续修订。新版本改变历史估计或未来预测时并列展示版本差异，不得跨预测版本拼接连续序列，也不得把行业预测当成公司盈利预测或既成事实。
- **§2.6.0行业bundle消费契约**:调用`source-discovery`后接收且保留七个顶层字段：`requests`, `accepted_candidates`, `unresolved_claims`, `ledger_path`, `ledger_sha256`, `status`, and `industry_bundle`。执行`research_contracts.validate_payload("industry-bundle", industry_bundle)`,并继续按candidate contract校验`accepted_candidates`。Consume `industry_bundle.status`; do not infer completion from prose. Populate every industry table only from validated `accepted_candidates`. `industry_bundle` controls role status and gaps only; it does not supply table values. 行业章节固定渲染`市场定义矩阵`、`历史市场规模与逐年增速`、`预测版本对照`、`集中度与竞争对手`、`当期部分期间`、`口径断点与未解决缺口`六个块,不得用通用行业问题替代。每张表都保存模板规定字段和机器引用；机器引用按`references/profile-writing-style.md`写入同块HTML注释。最后一块逐role保存role state、missing periods、ledger path、terminal route status和next evidence needed。
  - Accept unambiguous industry bundle `schema_version: 1.0` payloads for backward compatibility. New industry runs consume `schema_version: 1.1`.
  - In v1.1, `market_definition_fingerprint` is metric-independent and identifies the market including channel scope; `series_fingerprint` preserves metric, unit, measurement basis, and denominator. Render both fingerprints plus `channel_scope` and `denominator` from validated candidates in every numeric industry block.
  - Forecast publication date and `data_vintage` are not forecast-horizon dates. Render one forecast series per `data_vintage`; never merge values from different vintages into one row set.
  - Bundle `claim_states` terminate independently. Only claim IDs whose own state remains unresolved may enter `unresolved_claims`; accepted claims never return to `unresolved_claims` or dispatch. Roles in `partial` and `blocked` retain accepted evidence, periods, and series while rendering `missing_periods` and `missing_coverage` separately.
  - `complete`: render all six blocks normally.
  - `publishable-with-gaps`: retain accepted values, render every gap, and continue the profile. 必须逐项显示missing years、terminal route status和next evidence needed。
  - `blocked`: retain accepted values, render blocked routes, mark the industry chapter for manual follow-up, and do not claim factual absence.
  - 缺口映射必须可复现：从`scope_breaks[].from_scope_fingerprint`、`scope_breaks[].to_scope_fingerprint`和`scope_breaks[].reason`逐项填口径断点；从每个`ledger.attempts[].terminal_reason`填对应route终态。`blocked`的next evidence needed先取`ledger.next_escalation`,为空时列`ledger.unattempted_routes`；`exhausted`且无下一route时固定写`new publication/data release required`。
  - 行业表不得消费broker target prices、broker ratings或issuer earnings forecasts；这些字段即使与行业表同页也必须排除。
- **§2.6.1四问是 §1末节 synthesis, 不是 §1开场前置**: §1.8能力圈四问 = §1.1-§1.7 具体拆解之后的综合判定章节（非 gate）。子 agent 在 §1.1-§1.7 全部填完之后才填 §1.8, 4段独立作答, 每问 ≥ 50字, 含 ticker 特定证据（产品 SKU / 客户场景/竞品名/挑战者份额/假想敌推演）, 呼应 §1.1-§1.7的引用（不另起炉灶）, 禁品牌复读和结论标签。份额序列不满五年时,不得把“未形成完整五年序列”写成“无法判断任何趋势”;先按市场定义、计量口径和历史重叠值核对可比性,明确写出可比年份已经确认的阶段变化,再单独列出未覆盖年份和不能外推的范围。**理由**: 读懂业务才能判定是否在能力圈, 反之是结论先行——与价值投资"看懂再下注"精神相反。
- **§2.6.2任一失败 = profile 整体降级**:主agent复核任一问<50字、仅品牌复读或仅结论无场景时退回补证据（auto mode扩大scope重派,最多2次）;反复退回仍失败→§1.8写`**置信度:**需人工`,记录最后错误、已尝试来源和缺失证据,加入人工处理清单并阻断估值,不得按低置信度已完成继续。§1.1-§1.7保留原置信度;§1.8失败不否定其事实拆解,但profile保持观察状态。

### §2.7波动纪律

- **§2.7.1每年年报后重估一次** 是默认节奏; 重大事件（季报/行业结构变化/管理层更迭）补重估。期间不看股价波动。
- **§2.7.2买点/卖点以外的波动不触发动作**——哪怕上下50%。

### §2.8耐心规则

- **§2.8.1不主动留现金择时**; 但也不为仓位而急投。
- **§2.8.2分红到账再投资决策**:分红先进入现金台账;原持仓仍低于买点时才可再买原股,否则保留现金至计划调仓日或新买点。不按当前权重强制再投资,也不为"分红了就必须立即投出去"急于行动。

### §2.9估值动摇即停手

- **§2.9.1跌破买点第二/第三档时的硬规则**: 若新信息（最新季报/年报/竞争格局质变/之前推导被发现逻辑漏洞/三大前提某项由 "真" 松动到 "存疑"）动摇3y NI 预估, **立即停止加仓**。正确顺序: ① 重审3y NI 下限; ② 重算合理估值 + 新买点; ③ 再决定新行动。
- **§2.9.2卖出只由两件事触发**:
  - 估值逻辑: 市值 > 卖点 → 分批清仓
  - 事实翻案: 研究发现之前判断错了（新年报披露三大前提某项不过, 或护城河假设被打破）
  - **不因为股价跌而卖, 不因为股价涨而买**。"止损/止盈" 这类技术派概念不存在。

### §2.10组合集中度

- **§2.10.1目标4-6家, 上限8家**。超8家退回指数。
- **§2.10.2单一持仓上限40%**（极端50%, 需三前提全过 + 四问全清晰 + 承诺兑现 record 良好）; 下限10%（不敢重仓 = 没看懂, 干脆不持）。
- **§2.10.3同行业不超2家**（避免行业风险集中, 但允许同行业不同环节, 如白酒高端 + 次高端）。

### §2.11年报阅读纪律

- **§2.11.0 优先引用最新年报 (越新越好)**: 当期数据 (量价 / 资产 / 现金流 / 毛利 / 客户 / 供应商 / 合同负债等) 必须从最新年报取, 不默认用上一年。优先级: **最新年报 (审计过) > 半年报 (未审计) > 季报 (信息最少) > 旧年报 (仅用于跨年对比)**。旧年报 (≥ 2 年) 只作 5 年 ROE / 毛利稳定性 / 承诺 vs 兑现 / 提价历史等跨年维度。半年报 / 季报引用需节末 `**置信度:**` 降一档 (未审计 = 证据等级低)。为什么: 年报数据 1 年就过时, 估值前置清单 (§3.pre 三大前提) 基于 stale 数据 = 错判。
- **§2.11.1优先extracted text cache**:派子agent前,`data/filings/<ticker>/_extracted/<年报-YYYY>/text.md`必须存在（带`<!-- page N -->`marker）。缺失则先运行`uv run python scripts/extract_pdf.py <pdf>`。
- **§2.11.2必读附注12项**: 货币资金受限/应收账款5大客户 + 账龄/应收票据银票 vs 商票/预付账款对象/其他应收款关联方/存货分项 + 跌价/在建工程转固/商誉减值假设/合同负债占营收/应付账款议价权/长投 + 可供出售金融资产/有息负债。详见 `.claude/skills/read-filing/references/statement-reading.md` §3。
- **§2.11.3禁用8条空话**: "具有强大品牌/技术领先/行业龙头/管理优秀/市场广阔/核心竞争力突出/护城河宽广/成长空间巨大" 无具体佐证（人名/数字/日期/引用） 一律退回重写。
- **§2.11.4管理层口径校核**: Part 1 §1-§5每个 section 必填, 对比年报 vs 研报 vs 财新 vs 经销商反馈 vs 价盘 vs 监管披露, 指出哪里年报做了美化/避而不谈。"年报说 X, 我们同意 X" 视为不合格, 退回重做。

- **§2.11.5研报只取事实, 不取观点**: 卖方研报（`data/filings/<ticker>/research/`, `data/research/`）的价值 = **提供从年报/公告以外渠道才有的一手事实数据**, 不是提供分析师的主观判断。研究员的买入/卖出/持有 / PE 目标/盈利预测一律视为噪声。读研报/保存研报/被 subagent 引用研报时, 只保留三类内容, 其他全删:

  **保留三大类** (行业无关, 抽象描述; 跨行业举例仅为引子, 不是勾选清单):
  - **A. 具体事件事实** (有明确日期/金额/条款可引用): 监管公告、董事会决议、重大合同、产品/服务发布、并购/回购/分红/资本开支方案、人事变动、处罚/诉讼立案与判决。
  - **B. 年报里拿不到的运营明细** (细到年报不披露的颗粒度, 通常是季度/月度切面, 或纵向多年汇编): 关键运营 KPI 的高频数据、渠道/产能/区域结构切面、历史价量时间线的多年纵向汇编、行业份额/竞品动作、第三方草根调研或终端跟踪数据。**每家公司的具体 KPI 不同**, 研究前先从年报 + 招股说明书读出本行业的关键运营指标是哪几个, 再去研报里找这些指标的高频/细颗粒度数据。
  - **C. 可引用的第三方引述**: 业绩说明会/投资者交流会/股东大会/访谈的管理层原话; 第三方 (经销商/客户/供应商/监管/媒体) 访谈记录; 监管披露补充 (如关联方/诉讼/问询函回复)。
  
  **跨行业举例 (A / B / C 三类各行业长什么样, 仅为引子)**:
  
  | 行业 | A 类具体事件示例 | B 类运营明细示例 |
  |---|---|---|
  | 高端消费品 (白酒/奢侈品/化妆品) | 提价公告日期 + 出厂价变化; 新 SKU 首批配额 | 批价 (批发价) 月度走势; 经销商数/专卖店数季度; 终端价盘跟踪; 历次提价时间线 |
  | 互联网 / SaaS | 新产品上线/商业化节点; 并购对价与估值; 版号/牌照批文 | MAU / DAU / ARPU / 付费率月度; 游戏流水/广告 eCPM / 订阅续费率季度切面; App Store 排行变化; 竞品同类功能发布时间 |
  | 公用事业 (水电/核电/燃气/高速) | 电价调整批文日期; 新机组投运/并网时间; 特许经营权延续 | 上网电量月度; 来水来风数据; 标杆电价/市场化交易电价占比; 度电成本; 车流量季度 |
  | 金融 (银行/券商/保险) | 增发/配股公告; 资本补充工具发行; 监管处罚 | 净息差季度切面; 不良生成率月度 (信用卡); 核心一级资本充足率季度; 保费增速分险种; 新单保费/续期保费月度 |
  | 制造业 (新能源车/光伏/半导体/机械) | 新工厂开工/投产时间; 大客户大单公告; 技术认证批文 | 开工率/产能利用率月度; 良率变化; 出货量分区域/分客户月度; 原材料价格传导时点; 同行排产计划 |
  | 医药 (创新药 / CXO / 医械) | 临床进展节点 + 入组人数; NDA 受理/批准日期; 集采中标结果 | 国内外商业化铺点数季度; 医院/药店覆盖数; 处方量/复购率月度; 同靶点竞品临床时间轴; 产能利用率 |
  | 周期 (钢铁/煤炭/化工/航运) | 停产检修公告; 产能置换批文; 出口配额变化 | 产量/销量月度; 开工率周度; 库存天数; 下游需求领先指标; 运价 (BDI / CCFI) 时间序列 |
  
  读者自查: 如果 subagent 在研报里找不到本行业关键 KPI 的高频数据, **这份研报就没什么值得留的——直接精简到保留 A 类事件事实 + C 类引述即可**, 不要为了凑 B 类数据硬塞分析师的推测。

  **必须剔除的内容** (行业无关, 全部删):
  - 投资评级 ("买入/推荐/持有/增持/减持/回避" 等任何评级语言)、目标价、PE / PB / EV-EBITDA 预测、上调/下调评级理由。
  - 分析师对未来的定性预测 (任何 "有望/预计/将 / 看好/景气度向上/动能充足" 带主观推测的段落)——即便数字漂亮, 是猜测而非事实。
  - 未来年份 forecast 表 (营收 / NI / EPS / ROE / 净利率/毛利率/自由现金流等任何 YYYYE 列), 理由: **已发生年份以年报为准, 未发生年份分析师预测无价值**。
  - 照搬年报的历史三张报表 (已经在 `data/filings/<ticker>/年报-YYYY.pdf` 里, 不重复存)。
  - 免责声明/分析师承诺/评级说明/联系方式/公司 logo / K 线图或股价走势图的文字描述/页眉页脚/目录/章节导语。
  - 主观修辞话术 (任何行业都会用 "龙头/壁垒深厚/景气向上/价值凸显/动能充足" 这类空话, 无具体数字/事件/引述支撑的一律删)。
  
  **操作/压缩率参考**: 研报清洗后保留 < 原长度30% 视为正常, 保留 > 60% 几乎肯定没删干净 (深度报告首次覆盖例外, 可20-40%)。每条保留内容必须能通过两个自问: ① "这条事实年报有吗?" 答 "有" 立即删。② "这条是分析师猜的还是客观发生的?" 答 "猜的" 立即删。清洗后的研报用于 §2.11.4管理层口径校核的交叉比对和 §4.5排雷的运营数据补充。

- **§2.11.6 抓核心矛盾, 不给笼统总数**: 每个 subsection 的数据必须拆到能体现核心矛盾的颗粒度, 禁用"给个合计就完事"的写法。判准: 拆分后各组的**单位经济 (利润率 / 毛利率 / 增速 / 客户性质) 差异显著** → 必须拆; 差异不大 → 合计 OK。

  **常见必须拆分维度**:
  - **分产品 / 分业务**: 主力 vs 次要 (茅台酒 vs 系列酒 / iPhone vs 服务 / 主营 vs 投资收益), 合计掩盖利润结构。
  - **分渠道**: 直销 vs 批发 vs 电商 (毛利差异常 > 5pp), 合计掩盖议价权。
  - **分地区 / 分客户类型**: 国内 vs 国外 / 2C vs 2B / 2G, 政策敞口与单位经济不同。
  - **分时间切面**: 量 / 价分解 (产销量 × 单价 → 营收), 合计的 "营收 + X%" 掩盖是价格驱动还是数量驱动。**方向组合解读**: 销量 + / 收入 + = 健康增长; 销量 + / 收入 - = **降价走量** (pricing power 减弱, 值得 flag); 销量 - / 收入 + = 涨价保利 (需求强 / 提价空间); 销量 - / 收入 - = 衰退。
  - **关联 vs 非关联方**: 关联交易定价通常非市场化 (见 §2.11.7)。

- **§2.11.7 关联交易 ≠ 真实议价权 (A 股国企 / 民企均需识别)**: "前 N 供应商 / 客户中关联方占比 X%" 不是真正的供应链议价权指标, 而是**大股东利益转移通道**。分析时必须区分:

  **真实市场议价权** (对非关联方): 上游供应商是否高度分散 / 有替代 / 议价弱; 下游客户是否有切换成本 / 大客户依赖。
  
  **关联交易 (对关联方)**: 采购/销售价格是否偏离市场公允价; 账龄 / 回款是否正常; 定价机制是否披露。偏高采购价 = 大股东占款的合规替代; 偏低销售价 = 集团补贴子公司逻辑。审计报告 KAM (关键审计事项) 把关联交易单列 = 审计师已做专项程序, 值得关注。

  **判定原则**: 分析议价权时, 先把关联方从供应商 / 客户列表剥离, 再判非关联部分的市场结构。关联方占比 > 20% 必在节末 `**置信度:**` 降一档或 flag "定价公允性待跟踪"。

### §2.12好生意 > 好公司

- **§2.12.1 §1结论字段**: §1收尾给出 `好生意: 是 / 否 / 存疑` 结论; Step 6估值必须引用此结论; "否" 直接 Part 0标 "定性研究 only"。
- **§2.12.2 §4风险一票否决**: 即使 §1 = 是, §4出现道德风险/大股东占款/系统性画大饼（连续3年年初 guidance 大幅高于实际）/ 虚假陈述处罚记录 → 直接淘汰, profile 终止。

---

## §3分析流程（Step 1-6）

本节描述主 agent 如何执行。principles / rules 已在 §1 / §2讲过, 本节只讲 "如何派子 agent、如何 validate、如何路由", 不重复陈述纪律。

### source-discovery run-level orchestration

- `value-profile`拥有且只维护exactly one run-local `data/filings/<ticker>/runs/<run-id>/logs/research-ledger.json`。该文件是claim-indexed wrapper: 顶层按`claim_id`索引,每个entry只保存该claim的`request`、planner返回的单一`planner_inventory_receipt`、当前或终态ledger、accepted candidate handoff和被哪些section消费,不得另存caller声明的planner route list。receipt的strict normalized `planner_inputs` snapshot绑定request scope/content identity、source function、maintained profile identity/content hashes、maintained relation source bindings、bound routes、AS_OF/effective planning time、vocabulary/reachability identities和route inventory digest; contract validator与run-store分别独立重算fingerprint,run-store还核对receipt与wrapper request。ledger内`applicable_routes`必须逐项匹配receipt。该机制只提供deterministic tamper-evident binding,不防御同process恶意代码,不使用secret或第二个state machine。每个嵌套`request`继续按`research-request.schema.json`校验,receipt按`planner-inventory-receipt.schema.json`校验,每个claim ledger继续按`research-ledger.schema.json`校验,不得改写或扩展单条ledger schema本身。
- `checkpoint.json`是唯一source of truth。它按run-store contract只保存一个`research_ledger` artifact binding,字段固定为`artifact_id`、绝对路径和SHA-256;该路径下的wrapper保存全部claim entries和accepted candidate identities。若claim被接受,wrapper里还必须持久化可恢复的accepted candidate identity字段:`claim_id`、`request_scope_fingerprint`、`candidate_document_id`、`artifact_identity`、`artifact_sha256`、`source_document_identity.binding_sha256`、`lineage_id`和consuming section IDs,这样resume只消费已验证candidate,不靠内存或二次检索重建。
- wrapper首次发布或更新必须调用`financial_run_store.py bind-research-ledger`并执行CAS: 首次创建显式传`--expected-prior-sha256 create-only`,更新显式传checkpoint当前`research_ledger.sha256`;陈旧writer必须失败且不得覆盖。resume及任何新dispatch前必须调用`financial_run_store.py validate-research-ledger`,不得自行回填checkpoint binding或在校验失败后静默重建。
- 可见的`ledger_path`/`ledger_sha256`仅作可选引用,不得作为resume依据。resume、reuse和后续dispatch只信任`checkpoint.json`里的`research_ledger` binding,不信任Part 0或section正文中的可见回填。
- dispatch前先加载并校验既有ledger哈希。accepted的正向claim立即停止且永不重新dispatch;只把仍未解决的`claim_id`发送给`source-discovery`;把持久化`attempts`传给`plan_next_layer`;不得重新执行已terminal的`route_id`或已规范化查询。相同`request_scope_fingerprint`下同一claim一旦`exhausted`,同scope fingerprint下已`exhausted`的claim不得重复网络取证,除非request本身变化或适用route inventory变化。
- state mapping固定如下:`accepted`直接消费已持久化candidate identity;`blocked`和`conflict`必须保留结构化状态,只能在validated terminal ledger之后才可创建`需人工`; exhausted positive claim可创建evidence-unavailable `需人工`; exhausted absence claim只可写`截至AS_OF，适用公开路线未发现...`,不得写绝对absence。
- raw empty output、empty route、`technical-failure`、`access-unavailable`和`request-budget-exhausted`都不能直接产出`没有`、`查不到`或`需人工`;它们必须先落通过校验的终态`blocked` ledger,后续再由profile state mapping决定是继续阻断、保留冲突/阻塞状态,还是在合法条件下转成section级`需人工`。
- action ledger与research ledger严格分离。`deepen_research`只引用`claim_id`和`ledger_sha256`,用于说明本次为何继续深挖和消费哪个已持久化research state,不得替代或覆盖research ledger。
- `source-discovery`是唯一外部发现编排入口,不得回退到普通worker prompt兜底。普通worker只消费已绑定manifest事实和已接受的candidate identity,不能在空结果、失败路由或未terminal claim上自行补写absence、manual结论或新research status。

### Invocation

- **Primary:**`/value-profile <ticker> [--as-of YYYY-MM-DD] [--end-year YYYY]`—SH/SZ必须6位代码,HK允许1-5位代码;统一验证为`(?:\d{6}\.(SH|SZ)|\d{1,5}\.HK)`。港股代码立即左补零为五位,后续路径、manifest、查询参数和输出只使用canonical ticker。显式`--as-of`是全流程统一证据截止日,显式`--end-year`是最新目标财年;不得选择AS_OF后披露的年报,也不得以更早财年静默替代缺失目标财年。**默认auto mode**。
- **`--interactive`** — 切到 interactive mode, 每个 section 完成后停下来与用户交互。默认为 auto。
- **`--auto`** — 显式 auto mode（与 default 等价）。
- **`--section ID`**—跳到指定section。规范ID使用`part_id/section_id`,例如`part1/§1.3`或`part4/§4.5`;裸`§1.3`仅在模板中唯一时允许。跳过Step 2进度摘要,进入统一section resolver,再按Part路由到Step 3、Step 4或Step 5。
- 用户明确要求“完全重新分析”时，内部resolver使用`--clean`；正常入口不暴露resume、新run或run ID。

#### 两种运行模式

**Auto mode (default)**:一次性跑完公司研究必填section、§Q、§4.5和估值;缺少年报时自动执行下载,不显示下载菜单。个人偏好、组合与自我反思章节按Step 2标为待用户补充,中途不停。只在以下genuine故障时才停下来问用户或abort:

- Step 1 invalid ticker / 缺年报 PDF 且 fetcher 失败。
- §3.pre 三大前提判为假 → 强制降级为 "仅定性研究", 通告用户并暂停 Step 6; 子 agent 的 Step 1-5 继续跑但估值部分不输出。
- §2.12.2 §4风险一票否决（道德/占款/画大饼/处罚）触发 → 整份 profile 终止, 通告用户。
- 管理层子skill返回`management_pending=true`或`pending_gate=true`→原子保存现有gate正文、两个pending字段、未决行和阻断原因,持久化人工处理清单并退出auto循环;不得继续派下游section或反复选择同一gate。
- Section-level问题不abort整份profile:只有当run-level research ledger里相关claim已形成validated terminal `blocked/conflict/exhausted`且state mapping明确允许section落`**置信度:**需人工`时,才记录失败handoff、加入人工处理清单并退出该section自动循环;未terminal的claim继续按未解决状态推进,不得把空路由、失败路由或预算耗尽直接翻成终态结论。

**关键原则**:main-agent review（Step 3c）发现证据薄弱、空白或论断generic时,auto mode先扩大调查scope并重派;重试耗尽后先落真实搜索日志和validated terminal claim ledger,再按state mapping决定是否写`需人工`,不写虚假占位、不等待用户在线补方向,也不把缺证据section标完成。

**一次性自主完成契约**:

1. 每个run只维护一个research ledger wrapper,按`claim_id`记录问题、来源路线、规范化查询、attempts、终态ledger和accepted candidate identity。默认来源路线依次覆盖:发行人年报及附注、招股书及上市申请文件、交易所及监管披露、同行、供应商及关联方公开文件、独立行业、协会及学术资料、官方网页存档、可信二级来源。按适用性执行,不为凑数访问明显无关来源。
2. 同一路线的技术失败或输出质量问题最多重试2次;随后转下一条独立路线。两次重派上限只约束同一来源路线的执行或输出质量重试,不是全部研究的总次数上限。只要research ledger仍有未尝试且合规的独立来源路线,Auto mode不得转为`需人工`;resume时继续复用已持久化attempts、terminal route IDs和规范化查询,不得把同scope exhausted claim重新打回网络。
3. 提前反馈阻塞是状态通知,不是停工点。除依赖该阻塞的结论外,继续完成全部不受影响的section、可执行的来源调查、交叉验证和定性分析;不能因某个数字估值gate失败而停止公司研究。
4. 只有完成所有不依赖用户输入的工作后,才允许请求用户决定。真实阻塞仅限:关键字段仅存在于非公开或付费数据;需要用户凭证、授权或原始业务数据;合规来源穷尽后仍证据冲突或缺失;外部技术故障在已记录重试和替代路径后仍不可恢复。请求必须同时给出已完成成果、最后错误、已尝试来源、受影响结论和明确选项:`提供数据或授权访问`、`接受证据受限结论`、`跳过可选项`。不得只问“下一步怎么办”。
5. 用户说“继续”“继续未完成部分”“完成剩余项”或同义表达时,视为对全部未决项的`research more`授权,恢复原run并执行尚未完成的research ledger;不得要求用户重复输入菜单词。该授权不允许降低证据标准、编造数据或绕过manifest和估值gate。

**公开不可得资料的状态映射**:采购台账或向独立OEM询价通常属于公司内部资料。完成公开来源调查后,不得仅因公开资料无法取得而标`需人工`或阻断估值;使用已披露交易金额、条款、期末余额、治理程序和可得代理证据形成限定结论。不得据此反向证明关联采购价格公允,也不得把高额采购本身解释为利益输送。没有异常定价、资金转移或无法解释的现金流异常时,保留集中度预警并通过该检查;只有存在正面重大异常且公开证据和压力测试仍不能判断影响时才转人工。
**库存披露边界**:先查目标公司历年年报、招股书、审计关键事项和可比同业,区分汇总库存年龄与SKU级明细。汇总库存年龄或减值信息可在部分发行人的公开披露中取得,不得预设全部属于内部资料。若可比同业存在同口径披露而目标公司未披露,先核对业务模式、会计口径、监管要求和重要性;只有该差异确实削弱风险判断时才记录透明度预警,否则仅说明披露限制。SKU级库存库龄、期后销售比例和售价经适用公开来源核查仍未披露时,可归为公开资料限制,并说明其可能涉及内部经营资料、审计底稿或商业敏感信息;不得预设未来一定不会披露。完成历史和当期公开披露检查后,不得仅因未披露而标`需人工`或阻断估值。使用存货余额与构成、周转天数、拨备率、审计程序、历史和同业代理及压力测试作限定判断,不得反向证明不存在滞销或减值不足。出现正面异常且可能实质改变结论时,才考虑升级;能合理界定影响时保留预警。
**公开记录限定通过**:严格event manifest为优先机器复核路径;交易所公告历史已枚举、适用公开监管路线已terminal、全部正面命中已归类且没有未解决的正面命中或证据冲突时,允许写`截至AS_OF，适用公开来源未发现其他重大事件`。不得表述为绝对不存在;完整事件清单本身不构成估值阻断。唯一权威来源不可达且无同功能替代、已知事件无法分类或覆盖范围实质过窄时仍阻断。
**Interactive mode (`--interactive`)**: 每个 section 完成后 Step 3d 印菜单等用户 `accept / edit / defer / skip / research more`; Step 2 进度表印完后等用户 `continue / pick-section / exit`; Step 4 / Step 5 / Step 6 需用户 confirm。适合想逐节审阅、想在中间修正方向的场景。

两种模式的 section-level 质量要求完全一致（§1-§2规则不变）——区别只在"是否让用户介入 section 推进节奏"。Skill 在 auto mode 下会自行终止（Step 6完成或 abort）; interactive mode 下每个 checkpoint 把控制权交回用户。

### Step 1 — Bootstrap + filings audit

1. **Validate ticker**:SH/SZ使用`\d{6}\.(SH|SZ)`,HK使用`\d{1,5}\.HK`,与`download_filings.py`一致。港股代码立即左补零为五位。失败双语报错并abort:
   > `❌ 无效 ticker: <input>. 期望格式 <code>.<exchange>（例 600519.SH, 0700.HK）. / Invalid ticker.`

1.5. **无感解析研究身份、截止日和run**:先确定canonical ticker、目标财年和AS_OF。未显式提供目标财年或AS_OF时，只读交易所官方目录，使用最新有效完整年报的报告期和首次有效披露日，不用当前自然年猜测。随后先运行`read-filing` Mode A准备或复用annual、event及全部counterpart manifest；取得真实路径、SHA-256和artifact ID后，按报告日期计算但暂不创建候选profile路径，再运行`scripts/financial_run_store.py resolve ... --result-path <candidate-profile-path>`，把这些artifact ID、skill版本、模板版本及业务参数全部纳入输入指纹，不得使用`待建立`占位值。正常调用只处理`created/resumed/reused`：`resumed`恢复最新兼容未完成run并使用checkpoint已绑定profile路径，`reused`直接复用完全相同输入的完成结果且不创建run，`created`绑定候选路径并在首次CAS时排他创建profile。只有用户明确要求“完全重新分析”时传`--clean`。整个过程不得询问resume、新run或run ID。

   **最终profile路径**:resolver只管理执行状态和共享artifact，最终档案仍只匹配`profiles/<ticker>-<YYYY-MM-DD>[-vN].md`。`resumed`锁定checkpoint记录的既有profile绝对路径；`reused`直接返回完成档案；`created`按报告日期和最小可用`-vN`排他预留路径。显式AS_OF或目标财年与既有run不一致时创建增量子run，不修改旧run或旧profile。模板年份按目标财年确定性实例化，历史列从end_year至end_year-9，预测列为end_year+3。每份档案交付同名`.md`和`.html`：HTML为默认阅读版本，Markdown为可编辑源文件和CAS管理的正式结果。

1.55. **先创建standalone恢复骨架和证据阶段checkpoint**:完成Step 1.5的排他路径预留后,在该唯一目标创建或加载最小Part 0,至少持久化ticker、查询发行人代码映射、目标财年、AS_OF、证据阶段、`**运行状态:**进行中`和`**失败原因:**无`;三个manifest尚未生成时写`待建立`。manifest为`待建立`时先恢复采集,不得在manifest校验前拒绝该合法恢复状态。

   **Bootstrap提前反馈与部分交付契约**:任一bootstrap、官方查询或证据采集步骤失败时,必须在同一轮立即反馈用户,明确列出`阻塞项`、`受影响结论`、`不受影响且已完成的工作`和`准确的人工处理动作`,不得只输出笼统失败摘要或等到整轮结束才说明。原始官方查询失败或其他technical failure时,受影响claim先持久化为validated terminal `blocked`,再由state mapping决定哪些section需要部分profile `需人工`;不得跳过claim ledger直接把原始失败翻成profile结论。提前反馈后继续执行一次性自主完成契约:穷尽不依赖失败接口的合规来源、技术替代路径和全部不受影响section,不能把通知用户当作暂停许可。把最小骨架扩展为简版/部分profile并原子保存到reserved路径:写`运行状态=需人工`、具体失败原因和逐项人工处理清单,保留已完成的年报研究及其引用,将管理层和监管结论标`需人工`,只阻断数字估值和否定性监管结论（例如“未发现处罚”）,不得清空已完成section或把访问失败解释为未检出。即使当前只有元数据和失败handoff也必须保存恢复入口。回复必须给出部分profile路径,让用户能直接检查现有成果并决定是否补证。

1.6. **先采集官方查询bundle**:在任何`download_filings.py`命令前,按`../read-filing/references/event-query-plan.schema.json`生成计划,listing profile和subject roster显式保存HTTP方法、请求编码和实际请求要求的请求头,上市代码与日期只接受listing profile官方响应中的`listing_codes/listing_dates`。港股当前上市发行人的listing profile必须优先复用`../read-filing/references/event-source-discovery.md`中已验证的`hkex_equity_quote_token_v1` contract;collector自行通过普通HTTP发现动态token,不得每次打开Chrome/CDP,也不得把token硬编码。仅当自动bootstrap明确报告页面、token函数、JSONP schema或官方host/path变化时才重新执行浏览器发现流程。运行`uv run python scripts/collect_event_evidence.py --plan <absolute-query-plan.json> --bundle-out <absolute-official-query-bundle.json> --evidence-dir <absolute-immutable-evidence-dir>`并验证bundle后,读取采集器stdout返回的真实bundle路径;后续下载器和构建器只使用该真实路径。采集失败时先执行Step 1.55提前反馈与部分交付契约,并把受影响claim先持久化为validated terminal `blocked`。若官方发行人映射、上市日期和年报目录已核实,仅监管/事件来源失败,则进入`annual-only degraded path`:继续Step 2下载和分析年报,event manifest保持未构建、未绑定,不得把event manifest本身写成`需人工`,并保留不受影响且已完成的工作;只有相关claim完成validated terminal mapping后,对应section才可落部分profile `需人工`。若发行人身份或上市日期本身无法核实,则保存元数据级部分profile后停止取证,不得猜测身份继续下载。

2. **Audit `data/filings/<ticker>/`**:
   - Part 2和管理层资本分配需要最近10个财年;公司上市满10年但文件不足时:
     > `❌ 历史年报不足.`Auto模式直接执行下载且不显示菜单;Interactive模式才显示`[yes/no/show-command]`。
     - A股命令:`uv run python scripts/download_filings.py <ticker> --years 10 --end-year <latest-required-fiscal-year> --as-of AS_OF --listing-date <official-listing-date> --listing-profile-bundle <actual-official-query-bundle-path> --include-prospectus --manifest-out <temporary-annual-manifest-path>`。
     - 港股命令相同但港股不传`--include-prospectus`,并保留`--manifest-out <temporary-annual-manifest-path>`。
     - 上市日期必须来自交易所官方发行人资料,并在正式查询前固定;不得从本地首份年报或当前文件集合反推
     - `yes` → Bash shell out, stream输出。exit 0重新audit;exit 1按exchange打印手动URL（A股回退cninfo/上交所/深交所;港股回退HKEXnews）并abort。
     - `no` → abort + 手动下载说明。
     - `show-command` → 打印 CLI 并 abort, 不执行。
   - 上市历史不足10年时使用上市以来全部年报和招股说明书历史数据,明确标注实际窗口,不得伪称10年
   - 否则列出:`Found N年报（<years>）.招股说明书:present/missing.research/:K files.`
   - 仅SH/SZ检查`data/filings/<ticker>/research/`,空则非阻塞offer`uv run python scripts/download_research.py <ticker> --years 3 --as-of AS_OF --depth-only --max 15`;港股不显示download_research.py,改用HKEX公告和已提供研究资料。任何研究资料发布日期晚于AS_OF都不得进入证据集

**刷新前证据保护**:恢复run时必须在查询或下载前读取checkpoint绑定的共享artifact。共享canonical manifest只新增内容寻址版本，不覆盖旧版本；输入变化由resolver创建增量子run并失效下游artifact。

2.5. **构造并持久化source manifests**:确定研究截止日后,年报查询一律通过`--manifest-out <temporary-annual-manifest-path>`输出临时manifest,与不可变snapshot逐字段比较后才发布。年报manifest实际发布路径允许`annual-reports-<AS_OF>.json`或内容变化时的`annual-reports-<AS_OF>-<content-sha256>.json`内容寻址版本;年报和事件manifest都以Part 0持久化路径及SHA-256为唯一绑定依据。年报manifest保存官方目录查询URL、查询参数、响应哈希、官方结果总数和公告顺序ID;全部候选逐条保存财年、报告期末日、完整披露时间、公告标题、报告类型、有效状态、替代关系、公告ID或官方URL、是否选中、绝对路径和SHA-256。事件证据必须先采集后构建:query plan遵守`../read-filing/references/event-query-plan.schema.json`,并按`../read-filing/references/event-source-discovery.md`从实际官方请求发现来源,不得猜测接口;A+H发行人按两地官方代码和官方上市日期覆盖两地监管源,并从逐法域官方年报目录构造`counterpart_filing_manifests`,把`counterpart_filing_manifests路径及SHA-256映射`按法域持久化到Part 0,另保存目录请求及选中PDF哈希。运行采集器后读取采集器stdout返回的真实bundle路径,后续下载器和构建器只使用该真实路径,再运行`uv run python scripts/build_event_manifest.py --bundle <actual-official-query-bundle-path> --out <canonical-event-manifest-path>`,读取构建器stdout返回的真实发布路径;同一AS_OF变化时旧manifest保持不可变,并通过CAS原子改绑。annual manifest标量`查询发行人代码`必须等于`Part 0查询发行人代码映射[exchange]`;event manifest的`查询发行人代码映射完整相等`,不得把标量和映射直接比较。两个manifest顶层都保存ticker、exchange、AS_OF和查询发行人代码,并保存官方查询溯源和完整候选或事件集合;每类事件覆盖全部适用官方来源,事件manifest逐source保存HTTP方法、请求编码和响应schema,另保存请求头、查询参数、响应和文书、`source_count`和`sources`,事件逐条保存类别、标题、日期、状态、文书URL和内容哈希。主体名册覆盖发行人、管理层、实控人和审计机构,保存主体名册的官方URL和查询参数;构建器复核实时响应哈希、结果总数和完整主体列表。事件范围必须覆盖管理层、实控人及发行人上市以来全部欺诈、操纵股价、内幕交易、虚假陈述和财务造假正式处罚或生效纪律处分,以及上市以来全部已证实的大股东资金占用、违规关联交易和股东利益输送。构建器执行官方域名白名单、解析全部分页响应、分别校验`occurrence_date`和`publication_time`,要求`offense_type`、`legal_effect`、`subject_role_at_occurrence`、`issuer_connection`、主体覆盖和状态枚举;构建器逐类在线重取全部事件分页,本地路径单独放在`document_files`,不得混入官方响应,重新下载每个官方文书URL并与本地文书逐字节哈希一致。`live_revalidation_required`必须为`true`;形成任何否定性结论前重新请求全部官方来源。分别计算两个manifest文件的SHA-256并写入Part 0对应SHA-256字段;`<sha256>`仍存在时abort。manifest变化时按明确集合处理:年报manifest失效集合为全部公司证据驱动的canonical section及全部下游估值section;事件manifest失效集合至少含`part1/§4.pre-§4.8`、`part4/§4.5`、`part1/§5`及全部下游估值section。生成完整profile draft后,再用`uv run python scripts/publish_text_cas.py`一次写入section失效、Part 0路径和SHA-256;并发冲突时不得覆盖。后续调用子skill时把两个文件解析为真实绝对路径,只传Part 0绑定版本。

   **counterpart参数契约**:A+H调用任何证据子skill时,为每个法域重复追加`--counterpart-filing-manifest <exchange>:<absolute-json-path>`;参数键集合、Part 0映射和文件哈希必须完全一致。

   **事件段落规范化**:上段“逐类查询并写8类证据包”是`collect_event_evidence.py`内部职责,主skill不得绕过采集器直接构造bundle。`events-<AS_OF>.json`仅为首选输出基名;构建器返回内容寻址版本时Part 0必须绑定真实路径。滚动窗口计划对窗口前已发生但AS_OF仍未结案的调查设置`include_open_before_start=true`,主体名册包含审计机构。
3. **PDF预抽取cache**:每次读取任何`_extracted/<pdf-stem>/text.md`前,都验证同目录metadata.json中的`source_sha256`与年报manifest的PDF SHA-256一致、metadata中的`artifact_sha256`等于`text.md`当前字节哈希,且page marker从第一页开始并按页连续。任一不符都必须重抽取,不得读取或派发旧cache。cache缺失或失效时双语offer`for pdf in data/filings/<ticker>/年报-*.pdf;do uv run python scripts/extract_pdf.py "$pdf";done`;拒绝持久cache时子agent可读raw PDF,但不得声称存在page markers。

3.5. **Derive output path** `profiles/<ticker>-<YYYY-MM-DD>[-vN].md`:
   - `reused`→直接返回resolver绑定的完成profile，不创建文件。
   - `resumed`→使用checkpoint锁定的绝对profile路径并原地CAS更新。
   - `created`→只使用Step 1.5按最小可用`-vN`排他预留的路径，不得覆盖旧profile。
   - 新路径或目标仅为Step 1.55预留的最小骨架→把reserved scaffold扩展为完整template:在内存中实例化`.claude/skills/value-profile/template-zh.md`,把已锁定Part 0字段合并回完整模板后通过CAS写入同一路径,然后做**强制3项 cleanup**（template含meta文档,必须在开跑前剥离,否则最终profile会残留不属于ticker-specific内容的模板说明）:
     1. **Title**: 第一行 `# 价值投资个股研究 Profile — Template` → `# 价值投资个股研究 Profile — <中文公司名> (<ticker>) <report_date>`（例: `# 价值投资个股研究 Profile — 贵州茅台 (600519.SH) 2026-05-01`）。
     2. **删除整个模板说明区**:从`<!-- ⚠️ TEMPLATE-ONLY区域开始`到`<!-- ⚠️ TEMPLATE-ONLY区域结束`的两个marker及其间全部内容一次删除,不得只删内部注释而留下marker。
     4. **删 heading 里的 template-instruction parenthetical**: 扫 `^#+` 所有 heading, 删除尾部给填写者的指令性括号 annotation。典型要删的 pattern: `（本节最后填写）` / `（PRIMARY — 先填）` / `（OPTIONAL — 后填）` / `（填入...）` / `（待填）` / `（SECONDARY — 定量补充）`等。heading 本身 title 留下, 只剥离尾部给 filler 的 meta 指示。Ticker-specific 的 title 修饰（如"§3护城河分析"后面的结论性标签）不动。
     
     新建profile时立即把bootstrap AS_OF写入Part 0,并同时写入目标财年;加载已有profile时保留原AS_OF与目标财年并只校验一致性。两种模式都写入对应canonical manifest路径。然后填Part 0 header（ticker/exchange/researcher=`git config user.name`/report_date=今日;中英文公司名派轻量子agent一句话查）。Auto/interactive两种模式都必须做此cleanup,不可跳过。

     **5. Cleanup验证gate**（强制,abort条件）:cleanup完成后grep验证,任一残留→abort并re-cleanup:
     ```
     grep -nE "TEMPLATE-ONLY|Profile — Template|## 阅读姿态/分析框架|本模板是 \*\*输出结构|（PRIMARY|（SECONDARY|（OPTIONAL|（本节最后填写|（待填|（填入" profiles/<ticker>-<date>.md
     ```
     若任一match→cleanup未做完,必须重做。恢复run时也要跑此gate。

4. **阅读层事实调用**:目标profile已经由Step 3.5创建或加载并完成Part 0绑定后,在dispatch任何业务分析子agent前调用`read-filing` Mode B并强制追加`--complete-facts`。显式传`--target-profile <path> --section <part_id/section_id> --ticker <ticker> --year <YYYY> --as-of <AS_OF> --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> [--counterpart-filing-manifest <exchange>:<absolute-json-path>]... --auto|--interactive`,并在`--filing`与`--extracted-text`中恰选一个。A+H逐法域传全部counterpart;只有返回success且身份、目标、全部manifest路径和哈希与Part 0一致时才能继续;failure或manual_review不得保存事实草稿。

   **Mode B接收门槛**:只有`terminal_status=success`且身份、目标、两个manifest路径和哈希与Part 0一致时才能继续;failure时不得保存事实草稿,manual_review也不得保存事实草稿。

   **read-filing恢复路由**:read-filing返回的`action_requests`逐项持久化`request_id/type/reason/citations/execution_status/execution_result`后,使用Step 5同一两阶段action ledger确定性处理:`edit`仅修改调用参数并重新校验,`research_more`携带hint最多追加一次定向调查,`rebuild_evidence`由父skill扩窗或重建年报/事件证据并原子改绑后重试,`exit`保留失败原因和人工清单后终止。未知类型报schema错误;未执行动作阻止目标section完成。只有用户明确要求“完全重新分析”时才由入口resolver创建clean run，不得由action request触发。

5. **Resume schema migration**:加载已有profile后,在解析进度前按template的复合键集合和顺序执行schema migration:
   - dispatch任何子skill之前检查持久化终态。`manual_review`和`output_quality_failure`在正常调用中保留原run并显示`[edit/research more/exit]`；未显式解除前不得重新调用financial-redflag-scan，也不得进入普通next-undone循环。用户说“继续”“继续未完成部分”“完成剩余项”或同义表达,视为对全部未决项的`research more`授权并显式解除对应人工终态,不得要求用户重复输入菜单词。两种人工终态缺行也不得自动重派;只有菜单或上述自然语言授权后才恢复。edit只修改并复核现有草稿,research more继续尚未完成的research ledger,exit保持终态。只有用户明确要求“完全重新分析”才由resolver创建clean run。
   - 先迁移Part 0结构字段和估值gate:补齐`估值三大前提`、`估值阻断`和`管理层否决`;再补齐§1.8`好生意结论`,最后才解析section进度
   - 比较template与profile的`part_id/section_id`;缺失section按template边界插入正确Part并保留占位字段,不得静默忽略
   - 旧profile多出的未知section原样保留但标记为非canonical并报告,不得覆盖用户内容
   - 将`高（...）/中（...）/低（...）`、`高/中/低—说明`或`高/中/低-说明`规范化,说明移到`**需人工跟进:**`;例如`中—说明`归一为`中`。兼容半角形式`中高(...)`、`高(...);中(...)`和`需人工(...)`:混合等级取最低一级,`需人工(...)`归一为`需人工`
   - 旧混合值`中-高`、`中高`统一保守映射为`中`;`中-低`、`中低`映射为`低`,并记录原值。多个等级并列时取最低一级;其他未知置信度报schema错误
   - 去除置信度值外层Markdown粗体后再规范化,例如`**中高**`按`中高`处理
   - 兼容旧三前提逐项值,例如`①真/②有松动/③真`:逐项解析`真/假/存疑/有松动`,只有三项全为`真`才归一为`全真`;任一项为假、存疑或有松动都归一为`任一假或存疑—<逐项原因>`,其中`有松动`按存疑处理并保留原文
   - 对Part 0和§1.8 gate做值域校验:`估值三大前提`接受`全真/任一假或存疑—原因`,`管理层否决`接受`否/是—原因/需人工—原因`,`估值阻断`接受`否/是—原因`,`好生意结论`接受`是/否/存疑`。占位符或空值先按固定映射持久化为合法阻断值:`估值三大前提`→`任一假或存疑—待人工补证`,`管理层否决`→`需人工—待完成管理层gate`,`估值阻断`→`是—证据需人工`,`好生意结论`→`存疑`;同时加入人工处理清单和`gate_recompute_queue`,不得写入`未决`或进入Step 6。未知枚举值报schema错误
   - `gate_recompute_queue`使用固定路由:`估值三大前提`→`§3.pre`,`好生意结论`→`part1/§1.8`,`管理层否决`→`part1/§4.pre、part1/§4.2和part1/§4.8`;`估值阻断`不独立研究,在前三类及part4/§4.5恢复后调用阻断原因合并器派生。若目标section已有完整证据则直接重算gate,否则把对应section置信度改为`未做`并进入既有worker。必须在解析next-undone前执行队列,重算成功后移出人工处理清单;不得把迁移产生的保守值永久当作无解除路径的终态
	   - **银行schema迁移例外**:识别为银行后,即使旧profile把通用块标为`高/中/低`,也必须检测并替换已完成的通用§Q1-§Q12、已完成的通用part1/§1.6、已完成的通用part1/§3.5、已完成的通用part1/§3.6、已完成的通用part1/§3.7和已完成的通用part4/§4.3。若仍含销售收现、常规CFO/NI、毛利率、存货、资本开支、普通企业ROE杜邦或3年后净利润量价表,先保留原文到迁移备份,再替换为银行专属schema并把新块标为`未做`;这是“不改写已完成section”的唯一行业schema例外
	   - **保险schema迁移例外**:识别为保险公司后,备份并替换已完成的通用§Q1-§Q12及通用利润三问、护城河quality bundle、排雷bundle;若仍含存货、毛利率、普通CFO/NI或制造业资本开支字段,改为`industry-overlays.md`保险公司专属schema并标`未做`。保险继续完成定性研究和10项排雷,但估值路线固定为默认回避
   - 对Part 4 §4.5执行§4.5内部schema校验:先读取`排雷终态`和`排雷失败原因`。若终态为`output_quality_failure`,失败原因必须具体,置信度必须为`需人工`,估值阻断必须为`是—输出质量失败`;该人工终态即使缺行也不得改为`进行中`或自动重派,只允许显式edit或research more解除。其他终态无论置信度是否为`需人工`,都必须逐行验证29行+6行+4行+8行+5行的状态、严重度、证据和触发后的实际动作,再逐行按当前manifest证据和thresholds.yaml重算状态与严重度,并同步重算实际动作,不得保留与新状态矛盾的`无需动作`;不一致时覆盖并重新聚合。识别为银行时还必须逐行验证银行10行替代bundle,任一缺失不得判定完成。随后检查风险小结、引用、造假维度综合结论、结论、估值阻断和置信度。不可得值只允许保留真实生成的逐项搜索日志,其中必须有已查来源、查询词、结果和缺失原因。§4.5为`需人工`且含失败handoff（最后错误、已尝试来源、缺失字段、估值阻断）时,结构完整则保留`manual_review`待决终态;缺行时不得伪造搜索日志,缺行时仍保持`manual_review`并列出结构缺口,未显式选择前不得重新派发;只有用户选择research more才开启一次排雷流程,不得用handoff绕过逐行校验
   - 解析任何section终态前,先把管理层必做gate的旧`已跳过`迁移为`需人工`并加入上述重算队列。对§4.pre、§4.2和§4.8逐一执行management-analysis完成条件;高/中/低不能覆盖残缺gate。resume时逐行检查§4.8,任一行`需人工`均覆盖section的`高/中/低`置信度并保持管理层待决;resume时从§4.pre、§4.2和§4.8重新推导`管理层否决`,其canonical键分别为`part1/§4.pre`、`part1/§4.2`和`part1/§4.8`;从§4.5重新推导并校正财报阻断,canonical键为`part4/§4.5`。每次都按当前行聚合并同步Part 0可见状态为`**财报排雷:**零触发项/N项中风险/N项高风险/证据需人工`,不得只在需人工时更新。财报阻断与管理层否决取并集后校正`估值阻断`,并同步可见`管理层:`状态,不得让一方覆盖另一方
   - migration后重新运行cleanup gate并备份原文件为同目录`.pre-migration`

### Step 2 — Progress map

1. **Parse output file**:按顺序记录最近的`^## Part N`作为`part_id`,再读取每个含`**置信度:**`字段的`^### §`或`^## §`block。用`part_id/section_id`作为唯一键,并与template canonical键集合比对;非canonical未知section原样保留和报告,但不纳入next-undone或total_sections。持久状态值域仅为`高/中/低/未做/进行中/已跳过/需人工`;不得把`已完成`写入置信度字段。所有canonical section先执行通用完成条件:正文不含占位符,至少一条非占位引用,模板要求的表格、结论和管理层口径校核字段完整,且字段值域合法;仅有`高/中/低`不能判定完成。通过通用条件且置信度为`高/中/低`才派生控制台状态`已完成`;`未做/进行中`为未终态;`需人工`是人工终态并加入人工处理清单、阻断估值;已跳过仅在template明确允许时才是终态,否则迁移为`需人工`。其他值报schema错误。`total_sections=len(canonical_records)`,禁止硬编码。

   模板标记`可选用户输入章节`的`part4/§4.6-§4.9`、`part5/§5.1`和`part5/§5.4`不属于公司估值必填项。未提供个人风险偏好、自我反思或组合数据时,自动把置信度字段写为`已跳过`;`待用户补充`只写入正文说明和控制台,不拼接到状态值。跳过项不加入人工处理清单且不阻断公司估值;控制台必须说明估值不等于个性化买卖或仓位建议。

   估值阻断时条件跳过part4/§4.3:任一持久化估值gate已明确阻断且当前证据无需人工补充时,将正文写为`条件跳过—<阻断原因>`并附触发该gate的引用,置信度字段写`已跳过`。该终态只表示依法不生成估值,不得清除阻断原因,也不得把仍有`需人工`的证据缺口伪装成条件跳过。

   **无估值路线条件跳过集合**:当默认回避、护城河弱/否、能力圈未过、好生意为否,或PE被阻断且不存在可靠的PB/周期/DCF替代路线时,在定性研究和风险检查完成后,仅把`part4/§4.1`、`part4/§4.2`、`part4/§4.3`、`part5/§5.3`和`part5/§5.5`中尚未完成的section逐节写为`条件跳过—<同一可追溯原因>`并附gate引用,置信度写`已跳过`。已经完成的section保留原文和置信度,不得为统一外观而改写。不得要求这些路线输出新的估值数字、买点或卖点;仍有证据缺口时保持`需人工`,不能条件跳过。

   `part4/§4.3依赖part4/§4.5`;`part1/§5.4依赖part4/§4.5`:next-undone遇到这两个section但§4.5证据尚不完整时先路由Step 5。§4.5证据完整后再返回模板顺序;part1/§5.4不得先于part4/§4.5完成。§4.5证据完整且估值阻断为否之前不得运行§4.3。

2. **Render bilingual summary**（两种模式都印, 方便 logging / 用户 observe 进度）:
   ```
   已完成 completed_sections / total_sections 节（part1/§1.1, part1/§1.2）.
   下一节（next undone）: part1/§1.3 差异化
   ```

3. **Route by mode**:
   - **Auto mode (default)**:**直接进Step 3 on next-undone,不等输入**。Section完成后回Step 2重新印进度表并跳下一节,循环直到所有必填section均为终态,或触发管理层否决/filings失败。三大前提任一假或存疑时继续完成定性研究,但阻断数字估值并在Step 6调用仅定性研究finalizer。
   - **Interactive mode (`--interactive`)**: 印 `[continue / pick-section / exit]` 菜单, 等用户:
     - `continue` → Step 3 on next-undone。
     - `pick-section`→询问ID;复合ID直接定位。裸ID若唯一则解析,若存在歧义则报错并列出候选。Part 2的§Q*去Step 4,Part 4的§4.5去Step 5,其他去Step 3。
     - `exit` → 停。

**所有入口先运行统一section resolver**:`--section`只跳过进度摘要,不能跳过ID解析和路由。复合ID直接定位;裸ID唯一时解析;裸ID有歧义时停止并列出全部候选。解析后Part 2的§Q*进Step 4,Part 4的§4.5进Step 5,其他进Step 3。显式`--section part2/§Q*`只处理该section,不得展开为其余§Q或bulk。

定向综合章节必须先验依赖:`part1/§1.8`依赖`part1/§1.1-§1.7`,`part2/§Q12`依赖`part2/§Q1-§Q11`。依赖未完成时只报告缺失依赖,不得代跑、扩大目标或把综合章节写成终态。

显式定向`part4/§4.3`必须运行Step 6同一套完整门槛:估值三大前提、能力圈四问、好生意、护城河、管理层门槛和排雷门槛逐项通过,并确认人工处理清单为空;任一未通过时只报告依赖或阻断原因,不得生成估值。显式定向`part1/§5.4`也必须先完成§4.5,再使用其证据写造假风险。进入§4.3前按主估值路线替换schema:银行用真实净资产/PB,周期用完整周期平均利润和成本档倍数,公用事业用稳态FCF/DCF,默认回避行业只写定性结论。

### Step 3 — Section worker (per section)

#### 3.pre — §3.pre 三大前提（§1 / §3 / §5 前置 gate）

- **§3.pre三大前提judgement**:首次进入§1/§3/§5前,子agent依据§2.2.1输出3行判定。主agent立即把结果和引用持久写入Part 0的`估值三大前提`状态块;resume时从该状态块恢复,不得依赖会丢失的临时开场白。任一假/存疑→§2.2.2全局降级并阻断估值。

**§1.8 能力圈四问 ≠ 前置 gate**: 四问是 **§1.1-§1.7 拆解完成后**的 synthesis 章节（见 §2.6）, 不是 §1.1 开场前的 gate。子 agent 在 §1.1-§1.7 全部填完之后, 基于已建立的业务理解综合回答四问。理由: 能力圈判定需要对业务先有认知, 才能给出实质性答案; 前置 gate 版本 = "没读就下结论", 与价值投资"看懂再下注"精神反着走。

#### 3a. PDF pre-read

**优先 extracted text cache**:
- `_extracted/<年报-YYYY>/text.md` 存在 → 直接 Read, 用 line-offset + `<!-- page N -->` marker 导航。
- 缺失 → 触发 `scripts/extract_pdf.py` 或兜底 raw PDF。
- 图片 `_extracted/<pdf-stem>/images/` 带 LLM 描述 sidecar, §1-§2业务分析金矿。

**ToC targeting 起点**:

| section | 年报章节 |
|---|---|
| §1.1主营 / §1.2客户 | 第三节业务概要; 第四节经营情况 |
| §1.3-§1.5差异化/盈利/模式 | 第三节; 招股说明书业务与技术 |
| §1.6现金流 | A股第十节财务报告的现金流量表+附注;港股Consolidated Statement of Cash Flows+Notes |
| §2成长空间 | 第四节行业竞争/管理层讨论 |
| §3护城河 | 第三节核心竞争力; 第四节 |
| §4管理与文化 | A股第六节重要事项、第七节股东、第八节董监高;港股Corporate Governance Report、Directors' Report、独立非执行董事及Audit Committee披露 |
| §5风险 | 第四节风险提示 |
| §Q1-§Q12定量 | A股第十节财务报告;港股Consolidated Financial Statements+Notes |
| §4.5排雷 | A股第十节附注;港股Notes to the Consolidated Financial Statements |
| §3.pre三前提 | A股第十节审计报告、现金流量表和附注;港股Independent Auditor's Report、现金流量表和Notes |

#### 3b. Scoped research dispatch

派 ONE `general-purpose` 子 agent。Prompt 英文（指令语言）, 强制中文输出。必须包含:

- section heading + template 的本节目标/指导问题。
- **公司级关键问题清单**:首次Part 1 dispatch前,main agent先从业务结构、简化财务报表、跨年变化和异常项形成2-5个ticker特有问题；新增证据改变判断时更新。先问题驱动研究，后模板查漏；canonical section继续完整覆盖,但正文不得按指导问题顺序逐题填空。
- 解析出的 `<!-- 数据源: ... -->` hint。
- extracted `text.md` 绝对路径（或 raw PDF 兜底）+ 3a 给出的 page range。
- ticker, 中文公司名, exchange, report_date。
- `AS_OF证据截止日`;研究、同业、公告和事件不得使用AS_OF之后发布或发生的证据。
- read-filing返回的`facts/citations/warnings`必须传给普通worker并要求输出逐项引用对应citation;不得只调用后丢弃对象。product-analysis、management-analysis和financial-redflag-scan不接收隐式内存handoff,必须各自按相同绑定参数调用read-filing Mode B取得并复核事实。
- 已填好的相邻 section 作为上下文。
- **三大前提** (§2.2) — §1 / §3 / §5必需, 3行判定。
- **能力圈四问** (§2.6) — 仅当目标为§1.8时必需,输出4段独立回答;§1.1-§1.7只提供形成答案所需的事实。
- **禁用8条空话** (§2.11.3)。
- **管理层口径校核** (§2.11.4) — Part 1 §1-§5必填。
- **5步护城河分析** (§3必需):非银行按a分类（大/准/强/省/专）+b可证伪检验+c跨年定量追溯+d悲观情景+e宽/中/窄/弱标签执行。非银行必须完成资本消耗测试,并从提价、对手、切换成本、ROE路标中任选1项。**银行分支**只运行`industry-overlays.md`定义的银行quality bundle并据此完成同样的定性、可证伪、跨年、压力情景和标签步骤,不要求毛利率、CFO/NI或资本开支。具体数字准绳见`.claude/skills/value-profile/references/moat-framework.md`和template §3。
- **§1.1/§1.3产品分析**→**delegate到`product-analysis`子skill**。统一section resolver解析`part1/§1.1`或`part1/§1.3`;调用`product-analysis`前先向用户输出`正在调用product-analysis: <ticker> <resolved-section> (Mode B)`，再按其SKILL.md以`--target-profile <absolute-path> --section <part1/§1.1|part1/§1.3> --ticker <ticker> --year <YYYY> --as-of <YYYY-MM-DD> --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> --auto|--interactive`调用并用product Schema验收。A+H逐法域追加全部counterpart。普通worker不得代写或补写产品section；新建、失效或用户明确要求重跑时，不得因目标section已有正文或标为已完成而跳过。Mode B不得修改profile，父skill复核后通过Step 3e原子写入。
- **产品分析接收门槛**:除Schema外,要求目标键集合精确匹配、annual/event/counterpart哈希三方一致且citation属于当前section。§1.1与§1.3合计必须实质覆盖产品边界、交付流程、流程经济性、客户价值、竞争阶梯、需求侧机制、财报映射和失效测试；缺项、只有品牌故事或只列收入结构均拒绝。持久化`moat_handoff`的`claim/evidence/counterevidence/citation_ids/evidence_grade`为`**产品与流程证据:**`，并在机器字段保存隐藏的`product-analysis`调用回执，至少含mode、section、terminal_status和schema_version；不得把人工套用方法论伪装成Mode B success。出现最终护城河标签则拒绝,最终护城河仍由父skill计算。`pending`保存真实未决并阻断§1.8和§3;`failure`不保存草稿;`dependency_failure`按返回动作修复后重试,最多2次。
- **§4管理层分析**→**delegate到`management-analysis`子skill**。全流程进入管理层block时传`--section part1/§4`;显式定向某个管理层subsection时必须传`--section <resolved-part1/§4.x>`,不得扩大目标。其余参数为`--target-profile <path> --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path>`并继承当前`--auto`或`--interactive`;AS_OF从Part 0读取,两个manifest都传持久化后的真实绝对路径,不得省略。Mode B子skill无论模式都只返回`draft_sections`和结构化flags,父skill是Mode B唯一写入者;父skill复核后把section正文、管理层状态、人工清单和阻断原因在同一次原子写入中保存。详细流程见`.claude/skills/management-analysis/SKILL.md`§2-§3。Fallback:5个完整`N→N+1`比较需6份年报,每行来源写入该section`**引用:**`;连续未达标记guidance不可信风险,证据置信度不因管理层未兑现而降低,目标突然消失必须指出,言行一致检验≥2事件。
**管理层否决handoff**:Mode B子skill无论auto或interactive都只返回`draft_veto`和`management_veto=false`;父skill只对用户或auto已接受的内存草稿执行事务,interactive以accept或edit后的已接受正文为准。系统性画大饼唯一引用`management-analysis§2.7.2`:只在同一指标ID、连续3个可比财年、单位口径和目标方向一致时累计;不同指标不得拼接。父skill先预先计算完整事务:命中时同步写`**管理层:**一票否决触发`和`**管理层否决:**是—<reason>`,未命中时清除旧`管理层否决`阻断原因。随后运行`uv run python scripts/publish_text_cas.py --source <draft-path> --target <profile-path> --expected-sha256 <baseline-profile-sha256> --guard <bound-annual-manifest-path>:<sha256> --guard <bound-event-manifest-path>:<sha256> --guard <counterpart-filing-manifest-path>:<sha256>`完成一次CAS原子写入;非A+H省略counterpart guard。正文、Part 0状态和阻断原因集合一次保存,不存在“先保存正文再补Part 0”的中间状态,冲突时全部保持原状态。
**证据完整否决finalizer**:管理层否决已确认,或财报排雷命中高风险、`剔除`时,先完成最终live revalidation并用全部annual、event、counterpart及已建立的market manifest作为CAS guard,再写终态`已否决`。该终态不输出数字估值,保留全部已完成证据,并使resume确定性复现同一结果。
**子skill证据比较交换**:management-analysis和financial-redflag-scan返回对象都必须包含`filing_manifest_sha256`和`event_manifest_sha256`。父skill接受任何management响应前、保存草稿前重新计算两个manifest文件SHA-256,要求与子skill返回哈希及Part 0字段三方一致。另对`counterpart_filing_manifest_sha256s`逐个counterpart哈希执行子返回值/Part 0/文件三方一致:子返回的jurisdiction键集合必须与Part 0`counterpart_filing_manifests路径及SHA-256映射`完全相等,每个jurisdiction及其SHA-256必须逐项精确匹配,不得接受缺键、多键或跨法域代用。比较与原子替换之间任一manifest变化时abort并使受影响section失效,不得保存基于旧证据的草稿。
**finding聚合**:三个判断型子skill都按`sha256(judgment_domain|subject_type|subject_id|finding_type|occurrence_date|sorted(canonical_evidence_ids))`生成`canonical_finding_id`。父skill只在相同判断域、相同主体和相同ID内去重并取最高严重度;不同判断主体不得合并。`company_financials`保留公司财务判断,`management_integrity`保留管理层判断,`product_competitiveness`保留产品判断。最终报告按`canonical_evidence_id`并列展示不同主体的解释,同一底层事件事实只叙述一次;估值阻断原因写稳定集合,不得因多个skill引用同一证据而重复追加相同原因。
**管理层pending解除handoff**:任意management pending解决后,父skill重新校验本次目标section并从所有管理层section重建`unresolved_rows`。非gate section和必做gate使用同一解除路径:只移除已解决行对应的人工处理清单项;全局未决行清零才写`management_pending=false`;三个gate均无未决时写`pending_gate=false`,否则保持true。随后重新计算管理层否决和重新计算阻断原因集合。正文、两个pending字段、未决行、人工清单、否决字段和阻断集合在同一次原子写入中保存,失败时全部保持原状态。
**子skill失败handoff**:financial-redflag-scan重试耗尽时,对应section写`需人工`,记录最后错误、已尝试来源和缺失字段。management-analysis返回`terminal_status=failure`时直接执行其`rebuild_evidence`动作,不设置management pending;只有真实未决的`terminal_status=dependency_failure`或`terminal_status=pending`才设置pending并保存真实unresolved_rows。pending响应中的`draft_veto=true`或profile已有持久化否决必须保留并从已接受正文重算,未决证据不得擦除否决。management-analysis返回`rebuild_evidence`时先重建年报、事件及`counterpart_filing_manifests`,重新绑定并失效旧管理层section后再调用一次,不得把漂移降级为普通pending;返回`terminal_status=vetoed`时保留已证实否决、写`管理层否决=是—原因`,未另有真实未决行则不得改成`需人工—待完成管理层gate`。所有正文、状态、人工清单和阻断原因单次原子保存。
financial-redflag-scan重试耗尽或management-analysis重试耗尽后,对应section写`需人工`,阻断估值并返回父流程;存在人工排雷缺口时写`**财报排雷:**证据需人工`。
**阻断原因合并**:维护`财报高风险/管理层否决/证据需人工`阻断原因集合,去重后按固定顺序写入`**估值阻断:**是—<原因1;原因2>`;任何handoff不得覆盖已有原因。只有原因集合为空才写`否`。Step 1迁移、Step 5保存和Step 6每次gate变化后都调用同一个阻断原因合并器。

#### 3c. Main-agent review

读子 agent 产出。**驳回并重派**若任一:
- 事实缺引用。
- 管理层口径校核缺失或琐碎复读。
- 正文只是按template指导问题逐项填空,没有围绕公司级关键问题解释数据、原因和商业含义。
- 同一证据缺口在多个可见section重复解释，或护城河来源写成`测试通过/证据窗口/连续序列`等研究流程状态。
- 正文写“缺乏数据，无法分析”后继续列举缺失字段、已查来源、旧年份样本或接口错误。
- §1.1缺核心产品利润地图、设计和交付流程、流程经济性或单位经济;§1.3缺直接竞品、替代方案、适用龙头、龙头差距、2至3项价值机制或财报映射。
- 产品流程、竞争比较或价值机制缺显式证据等级;未披露成本被写成精确单点值;高毛利被直接写成品牌、身份、情绪或稀缺性证明。
- 填写区 generic, 无 ticker 特定细节。§3护城河写茅台必须引用茅台镇水源 / 12987工艺/基酒5年陈化/品牌价格带。
- §1.8 四问任一 < 50字/品牌复读/结论标签无场景 → §2.6.2退回; 退回的是 §1.8本节, 不动 §1.1-§1.7。

**Auto mode重派方式（§2.2.4深调查）**:不简单重跑同prompt,先读取run-level research ledger wrapper并只对未解决claim扩scope——多读1-2年年报、增查研报运营明细、展开附注、查同行、招股书或监管披露。同一来源路线重派最多2次;失败后继续下一条独立合规路线。只有相关claim都已形成validated terminal `blocked/conflict/exhausted`且关键证据仍缺失时,才按state mapping写`**置信度:**需人工`,记录最后错误、已尝试来源和缺失字段,加入人工处理清单并退出该section自动循环,不得写中/低后继续。Interactive mode由用户在3d主动`research more:<hint>`。

Acceptable后写中文终稿,填可见的`**引用:**`、`**置信度:**`和`**管理层口径校核:**`（Part 1 §1-§5）,并按profile-writing-style把`**机器引用清单:**`及其内容完整放入HTML注释。每条机器引用持久化`source_pdf_sha256/artifact_sha256/page/quote`,不得只保存可见页码。

#### 3d. Save by mode

- **Auto mode（default）**:3c review通过→隐式accept,直接原子写入profile并回Step 2。同一来源路线3c连续2次深调查仍不达标→把对应claim attempt写入validated ledger并继续下一条独立合规路线;全部相关claim都terminal后仍不达标,才按state mapping原子写入`**置信度:**需人工`和失败handoff并加入人工处理清单。该状态不得派生为已完成,不得再次自动选择同一section,除非用户自然语言或菜单显式授权`research more`。
- **Interactive mode (`--interactive`)**: 印 profile 内容中文 + 双语菜单:
  - `accept` → 保存, 覆盖原内容, 进度标 `已完成`。
  - `edit: <text>` → 应用修改后重新复核;若涉及管理层block,edit后的正文必须重新执行§4.pre、§4.2和§4.8完成条件,通过后才保存为已完成,任一残缺则保持`进行中/需人工`。
  - `defer` → 不保存, 标 `未做`, 回 Step 2。
  - `skip` → 仅模板明确可选的非gate section可填`N/A—<原因>`并标`已跳过`;管理层必做gate`§4.pre/§4.2/§4.8`不提供`skip`。
  - `research more: <hint>` → 回3b, 把 hint 附到子 agent prompt。
  - 管理层子skill返回`management_pending=true`时,无论`pending_gate`为true或false,先从draft正文重算已证实否决;若已证实否决与未决行并存,显示菜单前先在同一次原子写入中保存draft正文、`management_pending/pending_gate/unresolved_rows`、`管理层否决`、人工处理清单和阻断集合,未决行不得覆盖已证实否决;无已证实否决时也保存同一字段集合并写否。写入失败则保持原状态并报错。保存后不显示普通accept、defer或skip,只显示`edit/research more/exit`;`edit`后重新逐行校验,`research more`携带未决行重新调用management-analysis,`exit`保留pending终态供resume;未决行清零前不得accept为已完成。

#### 3e. Save and continue

每次消费Mode B草稿的CAS前及所有其他save前,统一运行`uv run python scripts/download_filings.py --revalidate <bound-annual-manifest-path>`和`uv run python scripts/build_event_manifest.py --revalidate <bound-event-manifest-path>`,A+H逐一重验证counterpart。然后生成完整draft并调用`uv run python scripts/publish_text_cas.py --source <draft-path> --target <profile-path> --expected-sha256 <baseline-profile-sha256> --guard <bound-annual-manifest-path>:<sha256> --guard <bound-event-manifest-path>:<sha256> --guard <counterpart-filing-manifest-path>:<sha256>`;非A+H省略counterpart guard,市场数据manifest建立后追加`--guard <bound-market-data-manifest-path>:<sha256>`。profile在任何save后必须是合法markdown;profile或任一绑定manifest并发变化时不得覆盖。Markdown每次成功保存后（包括简版或部分profile），立即运行`uv run python scripts/render_profile_html.py <profile-path>`重新生成同名HTML；HTML只用于阅读，不进入CAS或run-store；对用户优先返回HTML路径，同时保留Markdown路径供后续编辑和恢复。

### Step 4 — Part 2 bulk mode (§Q1-§Q12)

仅无`--section`的auto流程允许bulk;显式定向§Q时只更新已解析的一个section。显式定向§Q也必须先判定行业路由,不能依赖§1.1已经完成。

显式`--section part2/§Q* --auto`直接执行单section worker,但必须先用交易所行业、主营和业务分部判定行业。主overlay优先级的兼容基线为`银行>高杠杆地产>资源/周期>公用事业>互联网>白酒>消费品（非白酒）>默认`;保险识别优先于该基线。每次只选择一个主overlay替换目标§Q schema;次级overlay只追加不冲突的披露和风险检查,不得覆盖主overlay的估值路线。

1. **Auto mode**:无`--section`时默认直接走`bulk`,不offer。**Interactive mode**:无`--section`时offer`[bulk/by-section]`等用户选。
2. **进入bulk前先判定行业路由**:根据§1.1业务类型和`references/industry-overlays.md`选择主overlay。优先级固定为`银行>保险>高杠杆地产>资源/周期>公用事业>互联网>白酒>消费品（非白酒）>默认`;保险公司专属schema替换全部通用§Q并固定为仅定性研究
3. `bulk`→ONE子agent:A股读取每份年报第十节财务报告,港股按`Consolidated Financial Statements`和`Notes`语义标题定位。默认行业抽取通用指标;银行、周期、公用事业等按所选overlay整表替换。银行路由在解析§Q进度前先用`industry-overlays.md`§2.5替换§Q1-§Q12正文,不保留通用表的销售收现、CFO/NI、毛利率、存货或资本开支字段。按所选overlay构造prompt、字段清单和`N/A`规则,不得再要求银行CFO/毛利率/存货等不适用指标。每个cell的`**来源:**`带`年报-YYYY.pdf p.NN`
4. **Auto mode**:子agent随机抽取5个适用cell与独立数据源校核并汇报;主agent按所选overlay抽样校核字段和单位。≥4/5一致时为各§Q*写`**置信度:**高/中/低`中的适当值,由Step 2派生`已完成`;否则不一致行写`**置信度:**需人工`,不问用户。Interactive mode呈给用户校核结果后按同一规则落盘
5. ≥4/5一致→各§Q*持久写入`高/中/低`;否则不一致行写`需人工`,作为终态退出bulk循环并加入人工处理清单,不得再次自动选择同一§Q。
6. `by-section`也先执行同一行业路由,为用户选择的单个§Q替换或补充对应overlay schema后再走Step 3;不得把通用模板直接交给worker。

### Step 5 — 排雷清单模式 (§4.5)

**Delegate到`financial-redflag-scan`子skill**,传参`--target-profile PATH --section part4/§4.5 --as-of AS_OF --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path>`并传递当前模式。完整输出必须包含29项、6项、4条勾稽、5个维度、8类质检及终态字段;银行追加银行10行替代bundle,保险公司追加保险10行替代bundle,任一缺失不得判定完成。

**Fallback（子 skill 不可用时, 主 skill 跑简化版）**:

1. 派ONE子agent只基于bound annual/event/counterpart manifests和已接受candidate identities填写29行+6行+4行+8行+5行。银行追加银行10行替代bundle;保险公司追加`thresholds.yaml:checks.insurer_bundle`固定10行。每行必须有合法状态、严重度、证据和触发后的实际动作;不得为缺外部证据开普通worker side door。
2. 主agent复核全部行结构、缺引用和造假维度综合结论,并逐行按证据、触发条件和thresholds.yaml重算状态与严重度,同时同步重算实际动作,不得保留与新状态矛盾的`无需动作`;不一致时覆盖并重新聚合。不合格时按financial-redflag-scan§2.4.4对应流程最多重派2次。内部输出质量失败继续走既有`output_quality_failure`路径。任何外部缺证必须先走`source-discovery`,形成validated terminal claim ledger,之后才可持久化`排雷终态=manual_review`和`排雷失败原因=<具体证据缺口>`,并写`需人工`;不得开普通worker side door。字段已存在但输出缺行、枚举非法、JSON不可解析或结论冲突时持久化`output_quality_failure`及具体失败原因,写`**估值阻断:**是—输出质量失败`和`**置信度:**需人工`,加入人工处理清单后不得重新进入自动重派;resume直接显示该终态,只能由显式edit或research more解除。按模板原字段名依次写`**发现的风险小结:**`、`**引用:**`、`**估值阻断:**`、`**结论:**`和`**置信度:**`;结论按redflag-scan聚合规则取`无重大风险/有保留/剔除`。只有未耗尽且证据完整时,置信度才按证据窗口填写。
3. **Auto mode**:复核通过即接受draft,不confirm。**Interactive mode**:用户确认`[accept/edit/research more]`,仅accept或复核通过的edit进入保存。子skill不显示菜单,父skill唯一确认。
4. 父skill根据已接受draft和结构化flags逐行聚合Part 0`**财报排雷:**零触发项/N项中风险/N项高风险/证据需人工`,重算财报阻断原因,再与Part 0`**管理层否决:**`取并集。§4.5正文、排雷终态、排雷失败原因、Part 0财报排雷、估值阻断和人工处理清单必须在同一次原子写入中保存;任一步失败则全部不变。resume时分别从§4.5和§4.pre、§4.2和§4.8重新推导,不得依赖会丢失的内存flag。
5. **消费action_requests**:父skill把action ledger持久化到profile,逐项执行并记录结果;执行任何副作用前先按稳定`request_id`查账,已完成request_id直接跳过副作用并复用原`execution_result`。对pending请求先CAS写`execution_status=in_progress`再执行;所有副作用必须以request_id作为幂等键,或能从持久目标状态证明已经完成。resume遇`in_progress`时先对账目标状态:已生效则直接CAS为completed,未生效才重试,状态不明则failed并需人工,不得盲目重复。`valuation_route_review`重跑主估值路线选择,`management_review`使对应管理层section失效并重跑,`lower_confidence`按请求下调目标section或全局置信度,`deepen_research`只携带reason、citations、`claim_id`和`ledger_sha256`追加一次定向调查,不得替代或覆盖research ledger,`rebuild_evidence`重建年报和事件证据后重试§4.5;`block_valuation`并入阻断原因集合。未知action_request直接报schema错误;未执行的action_request阻止§4.5完成。动作执行结果与§4.5正文同一次原子写入,不得先保存正文后补动作。


### Step 6 — 执行摘要合成 (Part 0估值)

触发条件:所有必填section均为终态（`高/中/低`对应已完成,或模板明确允许且写明原因的`已跳过`）,且人工处理清单为空;Part 1管理层分析、Part 2 §Q1-§Q12、Part 1 §5风险和Part 4 §4.5均已完成。存在`需人工`时停止估值并输出人工处理清单,不重新进入自动循环。

**前置检查**:从Part 0的`估值三大前提`读取持久结论。三大前提任一假或存疑时不得输出数字估值;若定性研究、管理层gate和排雷证据均已完整,直接调用仅定性研究finalizer形成正常成功终态,不得要求用户补证据或将Part 0标为某状态。只有证据本身仍为`需人工`时才输出人工处理清单。

**阻断集合重建**:进入任何具体门槛前,从§4.5、§4.pre、§4.2、§4.8及人工处理清单重建`财报高风险/管理层否决/证据需人工`集合。每次gate变化后都调用阻断原因合并器,不得直接写单一原因覆盖集合;集合非空即写合并结果并阻断估值。

**排雷门槛**:从part4/§4.5逐行重算29项、6项、4条勾稽、8类补充和5个维度,确认状态、严重度、证据和触发后的实际动作均合法。银行10行替代bundle和保险10行替代bundle任一缺失不得判定完成。任一高风险、一票否决、结论为`剔除`或至少3个不同的29项清单ID形成聚类时加入财报高风险;Part 4 §4.5不存在高风险且无上述触发才通过。§4.5存在`需人工/待定`时加入证据需人工并阻断估值。

**管理层门槛**:读取`**管理层否决:**`;为`是`时把`管理层否决`加入集合,为`需人工`或§4.8任一行未决时把`证据需人工`加入集合,然后调用合并器并abort。resume时已按Step 1.5从§4.pre、§4.2和§4.8重建。

**投资资格gate**:
- **能力圈四问**任一未过→观察档案,不估值
- **好生意**从§1.8的`好生意结论`读取;为`否`→仅定性研究,不估值,为`存疑`→人工处理后再估值
- **护城河**为`弱/否`→不估值;`窄`只允许适用方法的保守上限
- **PE适用性边界**:PE适用性边界仅阻断PE法。净利润为负、非经常损益>30%、资本结构剧变或准则切换时不得使用PE法;若有可靠的银行PB法、周期法或公用事业DCF法则继续相应路线,否则只做定性研究

**仅定性研究finalizer**:当能力圈、好生意、护城河或估值方法适用性明确阻断全部数字估值路线,且定性研究、管理层gate和排雷证据均已完整时,这是正常成功终态。仅将尚未完成的估值相关section按Step 2写为条件跳过,把尚未填写的价格与估值字段写为`N/A—<阻断原因>`;已完成的§4.1和§4.2保留原文。生成定性结论、证据摘要和风险清单后保存并终止,不得重写任何已完成section。不得要求用户手工标记,也不得把该状态写成失败或需人工。

**估值方法路由**（多类叠加取最严）:
- **PE法**:强护城河消费/互联网及可预估高成长公司,`min(1/rf,25PE)`
- **周期法**:完整周期平均净利润×成本档倍数。完整周期定义为谷底到谷底或峰值到峰值,窗口至少覆盖一个峰值和一个谷底;对窗口内各完整财年的归母净利润使用算术平均,再乘成本档倍数（低成本15PE/中位成本10-12PE/高成本不估值）。若AS_OF处于可验证波峰,波峰调整系数固定为0.75,在成本档合理估值上再乘0.75;不得改用当前单年利润或另一套波峰PE。不满足完整周期定义时不输出数字估值,禁止使用当前单年净利润或中位数替代
- **银行PB法**:从归属普通股股东净资产起算;若只有合并股东权益,先扣少数股东权益、优先股、永续债及其他非普通股权益工具,再扣未充分计提损失得到真实净资产,最后按`industry-overlays.md`§2.4的银行子类型锚估值
- **公用事业DCF法**:稳态自由现金流`/(rf+2%)`,并用股息率交叉检查
- **高杠杆法**:仅在利润仍可预估时用8-12PE和35%买点折扣
- 保险及`valuation.md`§3.1列明的默认回避行业继续完成定性研究,但不输出估值数字或买卖点

**历史市场数据快照**:任何数字估值都先生成包含ticker、AS_OF、price和risk_free_rate完整请求契约的plan,无论AS_OF是否为当前日期都不得跳过;运行`uv run python scripts/build_market_manifest.py --plan <absolute-market-plan-path> --out <canonical-market-data-manifest-path> --evidence-dir <absolute-immutable-evidence-dir>`,读取stdout中的真实内容寻址路径并发布不可变`market-data manifest`。price请求必须以`query_params.issuer_code`绑定canonical ticker,并用`identity_path`从响应复核发行人身份;risk_free_rate请求和响应都用`tenor_path`绑定`10Y`。两类请求的`query_params.date`必须等于AS_OF,价格单位固定为A股`CNY`、港股`HKD`,无风险利率单位固定为`percent`;每个来源必须分别提供正整数`max_observation_age_days`,不得猜测全局默认值。`latest_observation_date_path`必须独立于`date_path`,分别保存最新可得观察日和所选观察日。manifest至少保存市场数据日期≤AS_OF、价格与无风险利率各自的官方请求URL、HTTP方法、参数、原始响应路径、价格官方响应SHA-256、无风险利率官方响应SHA-256和解析值。以内容哈希命名后写入Part 0的绝对路径及文件SHA-256;从首次绑定起所有save追加该文件guard,不得用当前行情或可变缓存替代。

**主估值路线优先级**:`默认回避>银行PB法>周期法>公用事业DCF法>高杠杆法>PE法`。选中前一项后不得回退到后一项;银行的天然高杠杆不触发通用高杠杆PE法。高杠杆+周期仍以完整周期平均利润为基础并追加35%买点折扣,不得回退到单年PE。次级overlay只追加检查、压力测试或更深折扣,不替换主路线。

先保持template既有6个状态块及其顺序,再更新以下7项估值内容,不得把7项当成新的状态块:

1. **估值基础（三档）**:PE法/高杠杆法用3年后归母净利润;周期法用完整周期平均净利润;银行PB法用真实净资产;公用事业DCF法用稳态自由现金流
2. **方法参数**:写明所选路由、参数和为何适用,不得把PE参数套给PB/DCF
3. **合理估值**:按所选路由计算并给上下限
4. **买点按路由计算**:
   - **PE法买点**=合理估值×50%;卖点=`min(合理估值×1.5,当年NI×50PE)`
   - **周期法买点**=穿越周期合理估值×40%-50%;卖点=繁荣期PE≤10时分批减仓,不得用单年低PE反推便宜
   - **银行PB法买点**=真实净资产合理估值×35%;卖点=市值/真实净资产>所选子类型PB上限,子类型上限以`industry-overlays.md`§2.4为准
   - **公用事业DCF法买点**由股息率>无风险利率×1.3触发;叠加高杠杆时必须同时满足`股息率>无风险利率×1.3且市值≤DCF合理估值×35%`;卖点由股息率<无风险利率触发
   - **高杠杆法买点**=合理估值×35%;卖点=PE>15时分批减仓
   - 周期法的估值倍数由成本曲线位置决定:低成本15PE、中位成本10-12PE、高成本不估值;周期叠加高杠杆时估值基础仍用完整周期平均利润,但买点采用更严格的35%,不使用40%-50%
5. **卖点约束**:每条路由只使用自己的退出条件,PB/DCF/周期法不得套用PE卖点;保险或定性研究only不输出买卖点
6. **持仓姿态** (§2.5.2 discrete): 加仓/建仓 | 持有不动（收工睡觉）| 分批清仓。
   - **§2.9.1估值动摇即停手守则**必须 inline 提示: 跌破买点第二档时, 若3y NI 预估动摇, 立即停止加仓, 回头重审下限 → 重算新买点 → 再决定。
7. **Top 3风险** — 来自 §5 + §4.5, 每条1-2句 + 触发条件。

**置信度汇总**:`高`当≥60%section为高;`中`为混合;`低`仅用于证据完整但可靠性较弱的内容。三大前提失败不下调证据置信度;证据完整时仍可进入`运行状态=已完成`的定性研究终态,但不输出数字估值。任何必填证据缺失保持`需人工`。

**最终证据绑定**:无论数字估值还是仅定性研究finalizer,最终CAS前都运行`uv run python scripts/download_filings.py --revalidate <bound-annual-manifest-path>`和`uv run python scripts/build_event_manifest.py --revalidate <bound-event-manifest-path>`;前者重新请求年报官方目录和选中PDF,后者重新请求全部官方来源,仅重算本地manifest哈希不够。任何数字估值都必须已建立市场快照并运行`uv run python scripts/build_market_manifest.py --revalidate <bound-market-data-manifest-path>`;仅定性研究未建立市场快照时才可省略。按manifest保存的HTTP方法、URL和参数重放两项官方请求,逐字节比较响应SHA-256并重算解析值;这是market-data manifest执行最终live revalidation。A+H逐一重验证`counterpart_filing_manifests`。最终原子保存前重新计算两个manifest文件SHA-256,再计算全部counterpart和已建立的market-data manifest哈希;Auto mode和Interactive mode都必须与Part 0字段逐项一致,不一致时abort。成功终态必须同时满足`运行状态=已完成`和`证据阶段=已绑定`,再使用全部guard原子保存。

- **Auto mode**:门槛通过且7项估值内容完整、数字源头可追溯时save并终止。控制台摘要使用动态值:`Profile完成.completed_sections/total_sections节已完成,估值Part 0已合成.路径:profiles/TICKER-DATE.md`。
- **Interactive mode**: 印摘要 + 双语菜单 `[accept / edit / research more]`, 等用户确认 → save。

最终profile发布并通过全部guard后，先提升已接受的分析artifact，再调用`financial_run_store.py complete --root data/filings --ticker <ticker> --run-id <run-id> --result-artifact-id <artifact-id> --result-path <profile-path>`。只有complete成功才把run视为完成；后续`reused.report_path`必须直接指向该profile。

---

## §4 Operational Boilerplate

### §4.1 Language policy

- **Profile 内容** (`.md`): 中文。填写区、`**引用:**`、`**管理层口径校核:**`、总结段均中文。
- **Operator 输出**（确认节点 / status / errors）: 双语, 中文为主。
- **子 agent prompts**: 英文（指令）, 强制中文输出。
- **Commit messages**: 英文。
- **避混用**:不写"SOE企业/stakeholder视角/bear case情景",统一中文化（国企/利益相关方/悲观情景）。`references/profile-writing-style.md`是唯一缩写白名单;不得在本文件另设较短白名单。
- **中文空格规则**:只禁止两个中文字符之间出现不恰当空格;不禁止中文与英文或数字之间为可读性保留正常空格。

### §4.2 What this skill MUST NOT do

- MUST NOT重写标`已完成`的section（除银行schema迁移例外;显式`--force`在v0不提供）。
- MUST NOT 编造数字或引用。无来源写 `待补充` + 原因。
- MUST NOT 用英文写 profile 内容。
- MUST NOT 没有年报 PDFs 就开干。Step 1.2 offer fetcher 或 abort。
- MUST NOT 跑 `git commit`。用户自 commit。
- MUST NOT 调用 `src/ah_research/`（平台数据层未就绪）。
- MUST NOT在Interactive模式未经Step 1.2显式确认就下载PDF。Auto模式按Step 1.2自动下载且不显示菜单;Interactive的`no/show-command`不得改动文件系统。

### §4.3 Failure modes & recovery

| Failure | Recovery |
|---|---|
| 子agent输出缺引用 | **Auto**:同一来源路线扩大scope重派最多2次;仍缺则把相关claim写成validated terminal ledger并继续research ledger下一条路线,全部合规路线完成后仍缺才按state mapping标`**置信度:**需人工`,附搜索日志并加入人工处理清单。**Interactive**:先把相关claim落成validated `blocked` ledger并显示`edit/research more/exit`,不得直接把空输出翻成事实或`需人工`。两种模式都绝不编造 |
| `管理层口径校核` 琐碎话漏网 | Step 3c 应拦住; 作 skill-regression 信号 |
| 年报 PDF 损坏 | 标 `年报-YYYY.pdf（unreadable）`, 用其他来源, 不 abort 该 section |
| 两个 session 并发编辑 profile | 不自动 resolve; warning, 用户手动解决 |
| 子agent配额/限流 | 窄page range重试一次;配额或限流重试耗尽后先把相关claim写成validated `blocked` ledger并切到下一条独立路线;只有state mapping确认该section已无合法自动推进路径时,才写`需人工`并作为终态退出,附具体失败原因并加入人工处理清单 |
| Step 1.2 fetcher失败 | A股回退cninfo/上交所/深交所,港股回退HKEXnews,然后abort。**绝不生成无filings的破profile** |
| 用户选的 section id 不在 template | 建议最近匹配（`1.3` → `§1.3 差异化`）; 不静默继续 |

### §4.4 Graduation path (Phase 1落地后)

1. **Step 4 Part 2 bulk** → 子 agent 优先 `ah_research.DataRepository.get_fundamentals(<ticker>, start=<10y>)`, repo 未覆盖回退 PDF。
2. **Step 5排雷纯数值项**（应收/营收, 商誉/净资产, 有息负债/CFO）→ DataRepository 算术。
3. **定性 section**（§1-§5, §4.5定性项）继续 PDF。没有数据源能替代管理层原话。
4. **`scripts/download_filings.py`** 挪进 `src/ah_research/integrations/cninfo_client.py`, 暴露为 repo 方法。

### §4.6 Profile 输出风格 — 给人读的, 不是给 AI 读的

Profile 的读者是人（研究员 / 投资人 / 审阅人）, 不是另一个 AI agent。写法必须服务于人类 scan + 理解。

- **§4.6.1 浓缩原则**: 核心是"内容少但每句精华, 信息量高"。Part 0执行摘要的好生意、护城河、管理层、财报排雷、能力圈、投资论点和三项主要风险统一使用 **状态标题 + 无前缀结论句 + 三色圆点证据**：结论单独用`>`引用块，不写`一句话判断：`；证据用`signal-list`和`signal-item`，绿色=正面、红色=负面、黄色=待验证，每条只表达一类判断，避免把无因果关系的事实并在同一条。每块保留3-5条最关键证据，细节留Part 1-5 / §Q / §4.5；目标是1-2分钟读完全部结论和跟踪项。
- **§4.6.2 禁用 AI 自引用 + 内嵌文献引用 (全 profile 非仅 Part 0)**: narrative body 禁两类内嵌 refs:

  **(a) 禁 `(§x.y)` 自引用**: 例 "毛利率92% (§1.1)"——事实自证, 不需指向源 section。允许的 § 引用形式: `**引用:**` 结构字段 / 开头为 "依据 §2.2 三大前提..." 的规则指向句 / "SKILL §2.9 守则" 这类 rule pointer。禁: 句尾裸括号 section id 如 `XXX (§1.5)`。

  **(b)证据落点**:叙述段不内嵌`XXX(年报-YYYY.md p.NN)`式引用;叙述段数字通过本节`**引用:**`逐条映射到来源。紧凑数据表为避免映射歧义,表格单元格可直接带页码或URL。两种形式都必须让数字唯一可追溯。

- **§4.6.2.bis body 段落 readability**: 每个 section 身体段落写给人读, 不是给 AI dump:
  - 正文可以是一段自然完整的分析，不按固定句数或固定模板切割；不强制套用“结论、数据、风险”三段式。
  - 需要解释变化时，优先按“数据 → 问题 → 原因 → 商业含义”展开，让读者看见推理过程；没有新增含义时不强行总结。
  - 禁 `(a)(b)(c)(d)` / `①②③④` inline list 散排在段落内——用真 markdown `- xxx` bullet, 每条独立一行。
  - 每个独立概念一段；只有主题变化或连续阅读费力时才拆段，不设固定句数。
  - 数字尽量配紧凑上下文, 不用"在...的情况下/基于...的考虑"长从句包数字。
  - 信息较多时可用 `**核心资产**` / `**生产流程**` / `**分产品收入**` 等自然子标题帮助阅读，不为形式完整强制分块。
  - 表格承担层级、包含关系、合计和算术校验；正文只写对业务的解释，不逐行复述表格。口径提示仅在省略后会导致实质性误读时保留。
  - AI操作提醒、处理步骤和防错指令只留在skill、隐藏注释或控制台输出，不得进入用户可见正文。
  - 引用、置信度和管理层口径校核属于证据层，继续保存在对应section供追溯和恢复，由HTML阅读版统一隐藏。会改变投资判断的口径限制、证据冲突和未知项必须先写入自然正文，不能只藏在这些字段里。
  - 每个证据缺口指定一个最相关的归口section并完整解释一次；其他section只使用已确认数据，不重复缺失年份、口径变化和搜索过程。护城河章节写经济机制及其证据，不写研究流程状态。
  - 缺少的数据使本节无法形成有效分析时，正文直接写“缺乏数据，无法分析”，不展开检索失败、来源报错或底层缺项清单；子问题没有数据时只写“<子问题>缺乏数据，无法分析”，不列举缺失字段、已查来源、旧年份样本或接口错误，句后不得继续解释缺什么或为什么没找到。内部恢复信息保留在隐藏字段。
- **§4.6.2.ter 层级收入表**:同一分类维度含父子关系时,父skill在Step 3c把子skill草稿规范为`references/profile-writing-style.md`定义的三列层级明细表。表题右侧写`报告期 · 金额单位`;正文固定为收入类别、收入、占总收入三列,父子关系只在首列缩进,金额和占比分列并右对齐。不得保留每层单独一列、`rowspan`、占位短横线或`金额 / 占比`合并单元格。产品、渠道、地区等交叉维度继续分表,不得跨表相加。
- **§4.6.3英文与中文金融术语**:写Part 0或Part 1-5前必须读取`references/profile-writing-style.md`。正文只保留该文件白名单中的行业缩写;其他英文使用自然中文。Step 3c发现白名单外英文时退回重写。
- **§4.6.4 Part 0状态词**:template是字段顺序和状态词的唯一来源。严格使用其6项顺序和既有选项,不得自造状态词。常见误译及替换方式见`references/profile-writing-style.md`。
- **§4.6.5 跟踪项 / 风险项视觉强调**: Part 0 + section 内遇到"需跟踪 / 需注意 / 风险信号"条目, 用 `⚠️ **跟踪 N**:` 或 `⚠️ **注意**:` 格式显式 flag, reader 一眼识别"哪些项需持续观察"。
- **§4.6.6 Part 0 heading 唯一**: 使用 `### 执行摘要` 作为 Part 0 结论块的唯一 heading, **不另套 `### 结论速览` / `### 结论` 等二级 heading**（重复 + 冗余）。
- **§4.6.7 自然中文措辞 / 词序 — 禁 AI 风格 awkward 句式**: Profile 的每段中文写完必须通过"母语 reader 自读流畅度 check"——读起来像原生中文, 不是"英文思路翻译过来"。以下 pattern 是 AI 直译高频 awkward 病症, 必须替换:

  | ❌ AI-style awkward | ✅ 自然中文 |
  |---|---|
  | 靠什么生产 | 怎么生产 / 生产方式 |
  | 靠什么环节赚什么钱（"靠什么 X 赚什么 Y" 双疑问空洞式）| 在哪个环节赚钱 / 赚钱的核心环节 |
  | 具备...可持续性 | 能否持续 / 可不可持续 |
  | 在...的情况下 | 拆成短句去掉 "情况下" |
  | 使得 + 长从句 | 拆成两个短句 |
  | 作为一个...公司 | 这家公司 / 本公司 |
  | 不仅...而且... 冗余对仗 | 改成一个短句 |
  | 通过...的方式 | 直接说动作, 不用"方式" |
  | 对于...来说 | 直接用"X 如何..." |
  | 基于...的考虑 | "考虑到 X" 或直接说原因 |

  **判定办法**: 写完一段读一遍——读起来卡、需停顿才懂、像翻译腔 = awkward, 改成母语自然说法。Step 3c 主 agent review 时抽查本节目标 / 结论句 / 填写区头尾句, 发现 awkward 句退回重派。Step 3c必须检查并改写“闭合”,按`references/profile-writing-style.md`改为“已核实”“证据完整”“已完成判断”“仍缺资料”或“尚不能判断”。

- **§4.6.8 禁写 AI-runtime meta blocks**: Profile 是 ticker-specific research doc, 不含运行 telemetry。**禁写**以下块:
  - "本profile完成状态"/"填写section数"/"Auto mode完成时间"/"Profile定位"等完成状态meta
  - "> 本摘要基于 AI 研究 + 用户审阅, 非投资建议" 等 AI-generated disclaimer
  - "置信度分布: 高 X% / 中 Y% / 低 Z%" 等 profile-level 统计（section 级 `**置信度:**` 字段保留）
  - "最近审阅日期" 除非已填 Part 0 header 表格里
  - 模板要求的`父级动作请求`、`动作执行台账`、`排雷终态`和`排雷失败原因`属于机器流程字段。机器流程字段必须保留，但统一放入HTML注释，供恢复和校验使用，不在阅读版显示。
  - Part 0内部工作流字段统一放入HTML注释；可见区只保留公司基本信息和自然表述的`仍需补充`，不得向读者展示manifest路径、运行状态、失败原因或恢复字段。
  
  Skill 运行 telemetry (完成数 / 路径 / 时间) 走**console final summary**（主 agent 自行打出, 不入文件）, 不是 profile 内容。
- **§4.6.9 Step 1.4 cleanup + §2.11.3 禁用空话 + 本 §4.6 narrative 守则** 共同构成"给人读"的 output quality。Auto mode 跑完应人工快扫 Part 0 1-2 分钟能 read off 所有关键结论 + 跟踪项——做不到 (浓缩失败 / 英文缩写残留 / heading 重复 / 自引用没清 / meta block 残留 / awkward 翻译腔) = regression, 需修正。

### §4.7子 agent prompt 模板（Step 3b dispatch 示例）

针对600519.SH §1.3; 换 section 时替换目标 block / 数据源 hint / page range。

```
You are researching §1.3 差异化 for ticker 600519.SH（贵州茅台 / Kweichow Moutai, SH exchange）.
Report date: 2026-04-28.

本节目标（from template）:
回答"公司解决了客户什么样的别人没能解决的需求和痛点"。必须具体到产品/场景, 不要抽象。

指导问题:
- 客户在哪个场景下选择公司产品而非竞品?
- 切换成本在哪里?（品牌/渠道/工艺/关系/价格带）
- 差异化可持续多久? 什么会打破?

数据源 hint: 年报第三节"公司业务概要"; 招股说明书"业务与技术"。

PDFs to read:
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/_extracted/年报-2024/text.md pages 8-35
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/_extracted/年报-2023/text.md pages 8-35
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/_extracted/招股说明书/text.md pages 40-80

Adjacent context（已填好 sections）:
§1.1 公司核心资产、主营产品和服务: <inlined content>
§1.2 公司客户: <inlined content>

Output requirements:
1. 中文作答。
2. 先走§2.2三大前提3行判定;仅当目标为§1.8时再完成§2.6能力圈四问4段回答。
3. §1.3 填写区写 3-6 条关于茅台差异化的具体论断。候选证据: 茅台镇水源、12987 工艺、基酒 5 年陈化、品牌价格带、经销商渠道网, 每条带年报页码。
4. 每条引用 `年报-YYYY.pdf p.NN` 或 web URL。若选中年报未披露 → `待补充—年报未披露`;若需要外部核验且当前仍缺证,返回unresolved claim输入,不得直接写`证据不足,需人工补充`。
5. 填 **管理层口径校核:**, 对比年报 vs 研报 / 价盘 / 媒体。"年报说 X, 我们同意" = 不合格。
6. 按引用密度和 spin-check 深度设 **置信度:** 高/中/低。
7. 禁用 §2.11.3 的 8 条空话。只写 ticker-specific 证据。

返回完整 section block（heading + 填写区 + 引用 + 置信度 + 管理层口径校核）。
```
