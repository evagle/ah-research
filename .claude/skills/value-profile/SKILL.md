---
name: value-profile
description: Walk a user through filling out a 价值投资 profile for a single A-share / HK stock. Auto-fetches 年报/招股说明书 PDFs via scripts/download_filings.py when missing, reads them as first-hand primary sources, gathers qualitative + quantitative research section-by-section, writes Chinese-language profile to profiles/<ticker>-<date>.md as it goes. Trigger on "/value-profile <ticker>", "研究 股票 <ticker>", or "fill out profile for <ticker>".
---

# Value Profile Skill

本 skill 是一份给主 Claude Code session 读的指令文档, 结构分三层: **§1投资哲学（信念/心法）→ §2规则（从哲学推出的纪律）→ §3流程（Step 1-6如何执行）**。读者应先把 §1完整通读 internalize, 再查 §2规则, 最后照 §3操作。§4是跨层 operational boilerplate。

## §0 Skill 运行方式

This skill runs as the **main Claude Code session agent** and orchestrates research via `general-purpose` subagents. It is an instruction document for the main model, not library code. The main agent owns file I/O, user 确认节点, and review; subagents do scoped PDF reads and web research.

**理论血统**: 本 skill 的方法论内核吸收自 `docs/references/tangshufang/methodology.md` 及其深度附录 `docs/references/tangshufang/01-05-*.md`。该5份附录是理论来源, 不在 SKILL / template / profile 正文中反复署名。以下所有 principles / rules / procedures 都已 internalize 为本项目的默认方法, 子 agent 无需再标注"按某某方法"。

---

## §1投资哲学核心原则

本节12条原则是整个分析流程的信念层。每一条都是长期不变的 meta-principle, 不含具体操作步骤。派任何子 agent 前, **主 agent 先在开场白里把本节通读一遍 internalize**; §2规则、§3流程 都是 §1的推论。

### §1.1股票是生意的凭证, 不是纸片

**持有股票 = 持有"一只会下蛋的母鸡"分成权**。内在价值 = 未来自由现金流折现之和, 与每日市价无关。市场价格不更新内在价值; 牛市是投资者的"风落之财", 长期复利来自企业内生现金流, 不来自"傻子馈赠"。

违反症状: 把 "最近股价涨/跌了 X%" 当信号, 用 K 线/板块轮动/资金流判断买卖, 把市值当锚。

### §1.2利润三问是估值的承重墙

任何估值动作之前必须先对以下三问给出 "真/假 / 存疑":

① **利润为真** — 经营现金流净额 ≥ 净利润; 销售收现/营收 ≥ 1+增值税率; 应收/存货/商誉 结构干净。
② **利润可持续** — 需求10年仍在; 护城河可验证而非声称。
③ **维持利润不需大投入** — 自由现金流 = 经营所得 − **维持性** CapEx（不是全部 CapEx）。长安汽车每年65亿维持性 CapEx 是 "泡沫利润", 需去泡沫化。

三问 **必须全部为真**。任一 "假/存疑" → 25PE 合理估值法 不适用, 必须打折或放弃。

违反症状: 看报表 PE 不看 CFO/NI 比值; 未拆维持性 vs 扩张性 CapEx 就算自由现金流。

### §1.3商业模式决定估值方法, 用错方法等于价值陷阱

不同生意的 "3年后净利润可预估度" 差异巨大, PE 不是万能: **强护城河消费/平台互联网 适用25PE**; **周期股/资源 顶部 PE 低 是陷阱, 底部 PE 高 是机会, 不适用 PE**; **银行 用 PB**; **保险 默认回避**; **公用事业 用 DCF 简化版**; **高杠杆 企业 PE 下调 + 折扣加深 到35%**。

违反症状: 给周期股套 PE; 给高成长股40+ PE; 用 PEG 抬 PE 超25; 把高杠杆标的按常规50% 买点算。

### §1.4三年后的确定性 >> 今天的精确性

估值靠 **三年后 可预估**, 不靠 **今天 精准**。选3年窗口是因为: 短于1年 = 短期博弈（噪声 > 信号）, 长于5年 = 超出绝大多数行业的可预测半径。§1商业模式 + §2成长空间 收尾时必须能回答 "这家公司3年后 的净利润中枢大约在哪里, 依据是什么"。答不出 → 不适用25PE 估值法, 必须更深折扣 或 弃权。

违反症状: 追求精准 DCF 到小数点后两位; 或反过来, 用 "长期看好" 敷衍, 不给3年窗口的量化上下限。

### §1.5安全边际是"我错了也不亏", 不是"便宜"

50% 折扣的意义不是占市场先生的便宜, 而是 **给自己估算错误留空间**。即使真实价值只有估算的70%, 50% 买入仍能不亏。判错概率越高（认知不深/行业变化快/管理层难评）**应提高折扣**而不是降低门槛买入。高杠杆企业折扣加深到35% 同理。

违反症状: 把折扣当 "市场情绪", 越跌越机械加仓; 不反思判断可能错, 只反思 "市场先生发癫"。

### §1.6能力圈是硬边界, 写不出具体答案 = 不下注

"看得懂" 的标准是 **能力圈四问** 全能口述具体答案:

① 公司靠销售什么商品/服务获取利润?
② 客户为何从它这里采购, 不选其他机构?
③ 资本天性逐利, 为什么别的资本没抢走它的份额或逼它降利?
④ 假设同行/巨头 挟巨资参与竞争, 它能否保住乃至扩张份额?

四问任一答 "抽象空话/品牌复读/结论标签无场景" = 能力圈外, **不下注**, 错过是价值投资的标配。"跨出能力圈下注, 是注定要被别人收割的——早晚而已。"

违反症状: "行业龙头/品牌强大/成长空间巨大/护城河宽广" 这类空话撑起的 §1, 没有产品级拆分、客户场景、挑战者名单、假想敌推演。

### §1.7市场波动 ≠ 信息, 价格不改变价值

格雷厄姆的 "市场先生" 寓言: 市场报价每天变, 企业内在价值几年才变一次。默认动作是 **呆坐不动**。股价上涨不是卖出理由, 估值超区间 才是; 股价下跌不是买入理由, 估值进入买点 才是。

违反症状: 用 K 线/量价/资金流 做决策; 用 "最近表现" 修订研究结论。

### §1.8耐心是资产, 空仓等待不是机会成本

不主动留现金等机会; 但也不为保持仓位 而急于投出去。所有持仓都超合理估值 + 没有新标的进入买点 → 自然产生现金, 等下一个买点即可。"单纯持有类现金资产等待股价下跌的所谓仓位管理"是明确反对的。

违反症状: FOMO 驱动的仓位管理; 把 "子弹池" 当择时工具。

### §1.9认错 > 坚持: 下注行为正确 ≠ 下注结果正确

估值判断本身动摇时, 纪律化加仓会从 "遵从体系" 滑向 "赌气/摊低成本执念"。跌破买点第二档/第三档 遇新信息（季报/行业变化/三大前提 由 "真" 松动到 "存疑"）动摇3年后净利润预估 → **立即停止加仓**, 不再机械摊低成本。正确顺序: ① 回头重审3年后净利润下限; ② 重算合理估值 + 新买点; ③ 再决定新行动（继续加/持有观望/止损重估）。**承认 "我看错了" 是完全合法的结论**。

违反症状: "原计划每跌 X% 加仓" 的机械执行; 用 "市场先生发癫" 掩盖判断已动摇。

### §1.10集中于高确定性 > 分散于平庸

从分散入手（起步 = 指数）→ 看懂一家转一家 → 成熟 持有 **4-6家**。超过8家 → 必然有几家没看懂, 回指数。单一持仓上限40%（极端可到50%, 茅台2017-2020）, 下限约10%（不敢重仓 = 没看懂 = 干脆不持）。同行业同时持仓 不超2家。

违反症状: 20+ 只股组合, 每只都是 "浅水位"; 或单一仓位 > 50% 而四问/三前提 未全过。

### §1.11年报是写给全体利益相关方的文档, 真相在附注

年报读者 = 监管 + 党组织 + 员工 + 地方政府 + 股东 + 供应商 + 经销商 + 投资者 + 媒体 + 竞争对手。价值投资者不是首要读者。因此读年报要 **读出弦外之音**: 哪些段落是合规话术/员工福利信号/地方政绩信号, 哪些才是实质经营信息。**正文可略读, 附注必须逐行读**——应交税费、关联交易、对外担保、其他应收款明细、存货构成、商誉减值测试假设、金融资产4分类 是否发生过跨档切换, 实质信息都在附注。

违反症状: 只读正文 "经营情况讨论与分析" 就下结论; 把管理层口径当事实。

### §1.12好生意 优先级 高于 好管理层

三好标准的顺序不可换: **好生意 → 好公司 → 好价格**。一流生意 + 三流管理层 通常优于 三流生意 + 一流管理层, 因为一流生意的经济商誉能让平庸管理层也挣到钱 (粤高速、长江电力), 而三流生意 + 一流管理层 = 管理层被迫不断重组/转型/跨界, 成功稀少且不可复制。§1 (好生意) 判定 "否" 不要指望 §4 (管理层) 救回; §1判定 "是" 时, §4平庸可接受, 只要不存在 §4风险 (道德/大股东占款/系统性画大饼)。

违反症状: 用 "管理层优秀" 对冲 "商业模式平庸"; 期待明星 CEO 能把垃圾生意做成金矿。

---

## §2规则层

本节是从 §1推出的可操作纪律。每条规则编号 `§2.N.x` 对应 原则 `§1.N`, 读者可以追溯 每条规则的信念来源。规则不是详细清单——详细清单（如29项排雷、13条 playbook、5步护城河 宽/中/窄/弱 具体数字）留在 template / methodology 里, 本节只给操作框架。

### §2.1股票 = 生意

- **§2.1.1禁用 K 线/量价/资金流**: 不把 "最近涨/跌 X%" 当决策输入。买卖动作只由 估值（§2.3 / §2.5）+ 事实翻案（§2.9）触发。
- **§2.1.2数字必带引用**: 每个财务数字后面 `(年报-YYYY.pdf p.NN)` 或 URL。不带引用 = 未核实。子 agent 禁止从记忆编数字, 找不到写 `待补充 — 年报未披露` 或 `证据不足, 需人工`。

### §2.2利润三问是前置门槛

- **§2.2.1三项判定** (§3.pre 子 agent 开场白必走):
  ① 审计意见 = 标准无保留 (会计所 + 近3年是否换所)
  ② 近3年 CFO 累计 ≥ NI 累计; 销售收现率（销售商品提供劳务收到的现金 / (营业收入 × (1+增值税率))）≥ ~1.0 ±5%
  ③ 近5年 ROE 稳定 ≥ 15%; 毛利率 波动 ≤ ±5点; 扣非 NI / NI ≥ 0.85
- **§2.2.2任一 假/存疑 → 全局降级**: 整份 profile `**置信度:** 低`, 阻断 §3 Step 6估值; Step 6需 abort 并打 "估值前置清单未通过" 提示条。
- **§2.2.3销售收现 交叉验证**: 应有销售收现 = 营收 × (1+VAT) − Δ应收账款 − Δ应收票据 + Δ合同负债 − 贴现财务费用。对比现金流量表实际值, **背离 > 5% 连续2年 → §4.5排雷 触发深调**。
- **§2.2.4 auto-mode 深调查原则**: Auto mode 下, 当 main-agent review 发现 subagent 证据薄弱、空白或论断 generic, 默认动作是**再派一次 subagent 做更深调查**——扩 PDF year range / 新读附注项 / 扫更多研报 / web search / 查监管披露 / 读招股说明书。连续 **2次 深调查 仍无法获得关键证据** → 标 `**置信度:** 中/低` + `**需人工跟进:** <具体什么信息没找到>` 备注并继续下一节, 不 abort 不静默。Interactive mode 不强制此条——用户可在 Step 3d `research more` 主动指方向。关键: 宁愿多花 subagent 调用也不让用户后补 "给我再研究一下 X"——研究的主动性归 agent, 不是 user。

### §2.3商业模式 → 估值方法对照

- **§2.3.1 6类生意估值矩阵**（套用前先判定公司落在哪一类）:

  | 生意类型 | 估值方法 | 买点折扣 | 说明 |
  |---|---|---|---|
  | 强护城河消费/平台互联网龙头 | 25PE（顶级30）| 50% | 常规25, 茅台/腾讯 级别 敢用30 |
  | 周期股/资源/化工/航运/钢铁/水泥 | 不适用 PE | — | 用 穿越周期平均 NI × 15PE 或 PB < 1清算, 否则弃权 |
  | 高成长股（年化 > 25%）| 25PE 上限不破 | 50% | 用保守下限; 不 用 PEG 抬到40+ |
  | 金融 — 银行 | 改用 PB（1.0-1.15× 真实净资产）| 35% | 真实净资产 = 账面 − 未计提不良真实损失 |
  | 金融 — 保险 | 默认回避 | — | EV 折现假设多且无法客观验证 |
  | 高杠杆（地产/部分电力/开发商）| PE 下调到8-12 | 35% | 硬指标: 有息负债/净资产 > 1或 / CFO 近3年 > 3 |
  | 公用事业（水电/高速/港口）| DCF 简化版 | 股息率 > rf × 1.3 | 用 稳态 FCF / (rf + 2%); 看 折旧 vs 维持性 CapEx 差额 |

  同时符合多类 (如 高杠杆 + 周期) → 取最严档。"不适用 PE" / "默认回避" → Step 6不输出估值数字, Part 0标 "定性研究 only"。完整准绳见 `.claude/skills/value-profile/references/valuation.md` §3。

### §2.4 3年窗口与可预估度

- **§2.4.1 3y 净利润三档必填**: 乐观/中性/悲观, 至少2个业务板块拆解, 每块 量 × 价 × 净利率, 每档附具体假设一句。
- **§2.4.2 PE 锚与增速无关**: 合理 PE = 1 / 10y 国债收益率（当前 ~3.5% → ~28x, 典型25-30）。超出需 justify。增速 已反映在3y NI 里, 不重复计入 PE。

### §2.5安全边际 = 估值错误容差

- **§2.5.1买点/卖点 公式**:
  - 买点 = 3y 合理估值 × 50%（高杠杆 × 35%; 必须 说明 为何判定高杠杆）
  - 卖点 = min(3y 合理估值 × 150%, 当年 NI × 50PE)——两候选都列, 取较低者
- **§2.5.2持仓姿态 discrete**:
  - 当前 市值 < 买点 → 加仓/建仓（分批, 一次 ≤ 目标仓位1/3）
  - 买点 ≤ 当前 ≤ 卖点 → 持有不动（收工睡觉, 每年年报后重估一次）
  - 当前 > 卖点 → 分批清仓（触点卖1/3; 再涨10% 卖1/3; 再涨10% 清仓）

### §2.6能力圈四问是 §1前置条件

- **§2.6.1四问是 §1末节 synthesis, 不是 §1开场前置**: §1.8能力圈四问 = §1.1-§1.7 具体拆解之后的综合判定章节（非 gate）。子 agent 在 §1.1-§1.7 全部填完之后才填 §1.8, 4段独立作答, 每问 ≥ 50字, 含 ticker 特定证据（产品 SKU / 客户场景/竞品名/挑战者份额/假想敌推演）, 呼应 §1.1-§1.7的引用（不另起炉灶）, 禁品牌复读和结论标签。**理由**: 读懂业务才能判定是否在能力圈, 反之是结论先行——与价值投资"看懂再下注"精神相反。
- **§2.6.2任一失败 = profile 整体降级**: 主 agent 复核任一问 < 50字或仅品牌复读或仅结论无场景 → 退回子 agent 补证据（auto mode 扩大 scope 重派, 最多2次）; 反复退回仍失败 → §1.8本节标 `**置信度:** 低` + 头部加 "能力圈四问第 X 问未达标 — 需补充证据或放弃"; §1.1-§1.7保留原置信度但 profile 整体降级为 "观察档案, 不下注", 不得进入 Step 6估值。§1.8失败不否定 §1.1-§1.7——前者是 synthesis 判定, 后者是 evidence 拆解, 两者独立。

### §2.7波动纪律

- **§2.7.1每年年报后 重估一次** 是默认节奏; 重大事件（季报/行业结构变化/管理层更迭）补重估。期间 不看股价波动。
- **§2.7.2买点/卖点 以外的波动不触发动作**——哪怕上下50%。

### §2.8耐心规则

- **§2.8.1不主动留现金择时**; 但也不为仓位而急投。
- **§2.8.2分红到账 再投资决策**: 仍低于买点 → 再买原股; 否则 → 进子弹池等下一个买点。不为 "分红了就必须立即投出去" 急于行动。

### §2.9估值动摇即停手

- **§2.9.1跌破买点第二/第三档时 的 硬规则**: 若 新信息（最新季报/年报/竞争格局质变/之前推导被发现逻辑漏洞/三大前提 某项由 "真" 松动到 "存疑"）动摇3y NI 预估, **立即停止加仓**。正确顺序: ① 重审3y NI 下限; ② 重算合理估值 + 新买点; ③ 再决定新行动。
- **§2.9.2卖出只由 两件事 触发**:
  - 估值逻辑: 市值 > 卖点 → 分批清仓
  - 事实翻案: 研究发现之前判断错了（新年报披露 三大前提 某项不过, 或 护城河假设被打破）
  - **不因为股价跌而卖, 不因为股价涨而买**。"止损/止盈" 这类技术派概念不存在。

### §2.10组合集中度

- **§2.10.1目标4-6家, 上限8家**。超8家退回指数。
- **§2.10.2单一持仓上限40%**（极端50%, 需 三前提 全过 + 四问全清晰 + 承诺兑现 record 良好）; 下限10%（不敢重仓 = 没看懂, 干脆不持）。
- **§2.10.3同行业不超2家**（避免行业风险集中, 但允许同行业不同环节, 如白酒高端 + 次高端）。

### §2.11年报阅读纪律

- **§2.11.0 优先引用最新年报 (越新越好)**: 当期数据 (量价 / 资产 / 现金流 / 毛利 / 客户 / 供应商 / 合同负债 等) 必须从最新年报取, 不默认用上一年。优先级: **最新年报 (审计过) > 半年报 (未审计) > 季报 (信息最少) > 旧年报 (仅用于跨年对比)**。旧年报 (≥ 2 年) 只作 5 年 ROE / 毛利稳定性 / 承诺 vs 兑现 / 提价历史 等跨年维度。半年报 / 季报 引用需节末 `**置信度:**` 降一档 (未审计 = 证据等级低)。为什么: 年报数据 1 年就过时, 估值前置清单 (§3.pre 三大前提) 基于 stale 数据 = 错判。
- **§2.11.1优先 extracted text cache**: 派子 agent 前, `data/filings/<ticker>/_extracted/<年报-YYYY>/text.md` 必须存在（带 `<!-- page N -->` marker）。缺失则先 shell out `python scripts/extract_pdf.py`。
- **§2.11.2必读附注12项**: 货币资金受限/应收账款5大客户 + 账龄/应收票据 银票 vs 商票/预付账款对象/其他应收款关联方/存货分项 + 跌价/在建工程转固/商誉减值假设/合同负债占营收/应付账款议价权/长投 + 可供出售金融资产/有息负债。详见 `.claude/skills/read-filing/references/statement-reading.md` §3。
- **§2.11.3禁用8条空话**: "具有强大品牌/技术领先/行业龙头/管理优秀/市场广阔/核心竞争力突出/护城河宽广/成长空间巨大" 无具体佐证（人名/数字/日期/引用） 一律退回重写。
- **§2.11.4管理层口径校核**: Part 1 §1-§5每个 section 必填, 对比年报 vs 研报 vs 财新 vs 经销商反馈 vs 价盘 vs 监管披露, 指出哪里年报做了美化/避而不谈。"年报说 X, 我们同意 X" 视为不合格, 退回重做。

- **§2.11.5研报只取事实, 不取观点**: 卖方研报（`data/filings/<ticker>/research/`, `data/research/`）的价值 = **提供从年报/公告以外渠道才有的一手事实数据**, 不是提供分析师的主观判断。研究员的买入/卖出/持有 / PE 目标/盈利预测 一律视为噪声。读研报/保存研报/被 subagent 引用研报时, 只保留三类内容, 其他全删:

  **保留三大类** (行业无关, 抽象描述; 跨行业举例 仅为 引子, 不是勾选清单):
  - **A. 具体事件事实** (有明确日期/金额/条款 可引用): 监管公告、董事会决议、重大合同、产品/服务发布、并购/回购/分红/资本开支方案、人事变动、处罚/诉讼 立案与判决。
  - **B. 年报里拿不到的运营明细** (细到年报不披露的颗粒度, 通常是季度/月度切面, 或纵向多年汇编): 关键运营 KPI 的高频数据、渠道/产能/区域结构切面、历史价量时间线的多年纵向汇编、行业份额/竞品动作、第三方草根调研或终端跟踪数据。**每家公司的具体 KPI 不同**, 研究前 先从年报 + 招股说明书读出本行业的关键运营指标是哪几个, 再去研报里找这些指标的高频/细颗粒度数据。
  - **C. 可引用的第三方引述**: 业绩说明会/投资者交流会/股东大会/访谈 的管理层原话; 第三方 (经销商/客户/供应商/监管/媒体) 访谈记录; 监管披露补充 (如关联方/诉讼/问询函 回复)。
  
  **跨行业举例 (A / B / C 三类各行业 长什么样, 仅为引子)**:
  
  | 行业 | A 类具体事件示例 | B 类运营明细示例 |
  |---|---|---|
  | 高端消费品 (白酒/奢侈品/化妆品) | 提价公告日期 + 出厂价变化; 新 SKU 首批配额 | 批价 (批发价) 月度走势; 经销商数/专卖店数 季度; 终端价盘跟踪; 历次提价时间线 |
  | 互联网 / SaaS | 新产品上线/商业化节点; 并购对价与估值; 版号/牌照 批文 | MAU / DAU / ARPU / 付费率 月度; 游戏流水/广告 eCPM / 订阅续费率 季度切面; App Store 排行变化; 竞品同类功能发布时间 |
  | 公用事业 (水电/核电/燃气/高速) | 电价调整批文日期; 新机组投运/并网时间; 特许经营权延续 | 上网电量 月度; 来水来风数据; 标杆电价/市场化交易电价占比; 度电成本; 车流量 季度 |
  | 金融 (银行/券商/保险) | 增发/配股公告; 资本补充工具发行; 监管处罚 | 净息差 季度切面; 不良生成率 月度 (信用卡); 核心一级资本充足率 季度; 保费增速分险种; 新单保费/续期保费 月度 |
  | 制造业 (新能源车/光伏/半导体/机械) | 新工厂开工/投产时间; 大客户大单公告; 技术认证批文 | 开工率/产能利用率 月度; 良率变化; 出货量分区域/分客户 月度; 原材料 价格传导时点; 同行排产计划 |
  | 医药 (创新药 / CXO / 医械) | 临床进展节点 + 入组人数; NDA 受理/批准 日期; 集采中标结果 | 国内外商业化铺点数 季度; 医院/药店 覆盖数; 处方量/复购率 月度; 同靶点竞品临床时间轴; 产能利用率 |
  | 周期 (钢铁/煤炭/化工/航运) | 停产检修公告; 产能置换批文; 出口配额变化 | 产量/销量 月度; 开工率 周度; 库存天数; 下游需求领先指标; 运价 (BDI / CCFI) 时间序列 |
  
  读者自查: 如果 subagent 在研报里找不到本行业关键 KPI 的高频数据, **这份研报就没什么值得留的——直接精简到保留 A 类事件事实 + C 类引述即可**, 不要为了凑 B 类数据硬塞分析师的推测。

  **必须剔除的内容** (行业无关, 全部删):
  - 投资评级 ("买入/推荐/持有/增持/减持/回避" 等任何评级语言)、目标价、PE / PB / EV-EBITDA 预测、上调/下调评级理由。
  - 分析师对未来的定性预测 (任何 "有望/预计/将 / 看好/景气度向上/动能充足" 带主观推测的段落)——即便数字漂亮, 是猜测而非事实。
  - 未来年份 forecast 表 (营收 / NI / EPS / ROE / 净利率/毛利率/自由现金流 等 任何 YYYYE 列), 理由: **已发生年份以年报为准, 未发生年份分析师预测无价值**。
  - 照搬年报的历史三张报表 (已经在 `data/filings/<ticker>/年报-YYYY.pdf` 里, 不重复存)。
  - 免责声明/分析师承诺/评级说明/联系方式/公司 logo / K 线图 或 股价走势图 的文字描述/页眉页脚/目录/章节导语。
  - 主观修辞话术 (任何行业都会用 "龙头/壁垒深厚/景气向上/价值凸显/动能充足" 这类空话, 无具体数字/事件/引述 支撑的一律删)。
  
  **操作/压缩率 参考**: 研报清洗后保留 < 原长度30% 视为正常, 保留 > 60% 几乎肯定没删干净 (深度报告 首次覆盖 例外, 可20-40%)。每条保留内容必须能通过两个自问: ① "这条事实年报有吗?" 答 "有" 立即删。② "这条是分析师猜的还是客观发生的?" 答 "猜的" 立即删。清洗后的研报用于 §2.11.4管理层口径校核 的交叉比对 和 §4.5排雷 的运营数据补充。

- **§2.11.6 抓核心矛盾, 不给笼统总数**: 每个 subsection 的数据必须拆到能体现核心矛盾的颗粒度, 禁用"给个合计就完事"的写法。判准: 拆分后各组的**单位经济 (利润率 / 毛利率 / 增速 / 客户性质) 差异显著** → 必须拆; 差异不大 → 合计 OK。

  **常见必须拆分维度**:
  - **分产品 / 分业务**: 主力 vs 次要 (茅台酒 vs 系列酒 / iPhone vs 服务 / 主营 vs 投资收益), 合计掩盖利润结构。
  - **分渠道**: 直销 vs 批发 vs 电商 (毛利差异常 > 5pp), 合计掩盖议价权。
  - **分地区 / 分客户类型**: 国内 vs 国外 / 2C vs 2B / 2G, 政策敞口与单位经济不同。
  - **分时间切面**: 量 / 价分解 (产销量 × 单价 → 营收), 合计的 "营收 + X%" 掩盖是价格驱动还是数量驱动。**方向组合解读**: 销量 + / 收入 + = 健康增长; 销量 + / 收入 - = **降价走量** (pricing power 减弱, 值得 flag); 销量 - / 收入 + = 涨价保利 (需求强 / 提价空间); 销量 - / 收入 - = 衰退。
  - **关联 vs 非关联方**: 关联交易定价通常非市场化 (见 §2.11.7)。

- **§2.11.7 关联交易 ≠ 真实议价权 (A 股国企 / 民企 均需识别)**: "前 N 供应商 / 客户 中关联方占比 X%" 不是真正的供应链议价权指标, 而是**大股东利益转移通道**。分析时必须区分:

  **真实市场议价权** (对非关联方): 上游供应商是否高度分散 / 有替代 / 议价弱; 下游客户是否有切换成本 / 大客户依赖。
  
  **关联交易 (对关联方)**: 采购/销售价格是否偏离市场公允价; 账龄 / 回款是否正常; 定价机制是否披露。偏高采购价 = 大股东占款的合规替代; 偏低销售价 = 集团补贴子公司逻辑。审计报告 KAM (关键审计事项) 把关联交易单列 = 审计师已做专项程序, 值得关注。

  **判定原则**: 分析议价权时, 先把关联方从供应商 / 客户列表剥离, 再判非关联部分的市场结构。关联方占比 > 20% 必在节末 `**置信度:**` 降一档或 flag "定价公允性待跟踪"。

### §2.12好生意 > 好公司

- **§2.12.1 §1结论 字段**: §1收尾给出 `好生意: 是 / 否 / 存疑` 结论; Step 6估值 必须 引用 此 结论; "否" 直接 Part 0标 "定性研究 only"。
- **§2.12.2 §4风险 一票否决**: 即使 §1 = 是, §4出现 道德风险/大股东占款/系统性画大饼（连续3年年初 guidance 大幅高于实际）/ 虚假陈述 处罚记录 → 直接淘汰, profile 终止。

---

## §3分析流程（Step 1-6）

本节描述主 agent 如何执行。principles / rules 已在 §1 / §2讲过, 本节 只讲 "如何派子 agent、如何 validate、如何路由", 不重复陈述 纪律。

### Invocation

- **Primary:** `/value-profile <ticker>` — ticker 是 `<code>.<exchange>`（例: `600519.SH`, `000001.SZ`, `0700.HK`）, 验证正则 `^[0-9]{4,6}\.(SH|SZ|HK)$`。**默认 auto mode**（见下）。
- **`--interactive`** — 切到 interactive mode, 每个 section 完成后停下来与用户交互。默认为 auto。
- **`--auto`** — 显式 auto mode（与 default 等价）。
- **`--section <id>`** — 跳到指定 section, 例 `/value-profile 600519.SH --section 1.3`。跳过 Step 2 progress summary, 直接进入 Step 3。
- **`--resume`** — 强制加载最近一个 `profiles/<ticker>-*.md`, 不询问日期。

#### 两种运行模式

**Auto mode (default)**: 一次性跑完 Part 0 → Part 5 + §Q + §4.5 + playbook, 中途不停, 只在以下 genuine 故障时才停下来问用户或 abort:

- Step 1 invalid ticker / 缺年报 PDF 且 fetcher 失败。
- Step 1.4 resume-vs-start-fresh（同一 ticker 旧日期文件存在时的 fork, 语义选择不是进度 checkpoint）。
- §3.pre 三大前提 判为 假 → 强制降级为 "仅定性研究", 通告用户并暂停 Step 6; 子 agent 的 Step 1-5 继续跑但估值部分不输出。
- §2.12.2 §4风险 一票否决（道德/占款/画大饼/处罚）触发 → 整份 profile 终止, 通告用户。
- Section-level 问题**不** abort: 子 agent 连续2次深调查仍无法获得关键证据 → 标 `**置信度:** 中` + `**需人工跟进:** <具体什么没找到>` 备注后继续下一节。

**关键原则**: 当 main-agent review (Step 3c) 发现 subagent 输出证据薄弱 / 空白 / 论断 generic 时, auto mode 的默认动作是**扩大调查 scope 并重派 subagent**（多读1-2年年报 / 增查研报 B类运营明细 / 展开附注项 / web search 行业数据 / 读招股说明书对应章节）。**不**走 fallback `待补充 — 需人工` 占位, **不**等用户介入。宁愿多花 subagent 调用也要把证据找全 (§2.2.4)。

**Interactive mode (`--interactive`)**: 每个 section 完成后 Step 3d 印菜单等用户 `accept / edit / defer / skip / research more`; Step 2 进度表印完后等用户 `continue / pick-section / exit`; Step 4 / Step 5 / Step 6 需用户 confirm。适合想逐节审阅、想在中间修正方向的场景。

两种模式的 section-level 质量要求完全一致（§1-§2规则不变）——区别只在"是否让用户介入 section 推进节奏"。Skill 在 auto mode 下会自行终止（Step 6完成或 abort）; interactive mode 下每个 checkpoint 把控制权交回用户。

### Step 1 — Bootstrap + filings audit

1. **Validate ticker** against `^[0-9]{4,6}\.(SH|SZ|HK)$`. 失败双语报错并 abort:
   > `❌ 无效 ticker: <input>. 期望格式 <code>.<exchange>（例 600519.SH, 0700.HK）. / Invalid ticker.`

2. **Audit `data/filings/<ticker>/`**:
   - 若目录缺失 OR 匹配 `年报-*.pdf` 的文件 < **2** 份:
     > `❌ 缺少年报 PDF. 是否 auto-run python scripts/download_filings.py <ticker> --years 5 --include-prospectus? [yes / no / show-command]`
     - `yes` → Bash shell out, stream 输出。exit 0重 audit; exit 1打手动 URL (http://www.cninfo.com.cn) 并 abort。
     - `no` → abort + 手动下载说明。
     - `show-command` → 打印 CLI 并 abort, 不执行。
   - 否则列出: `Found N 年报（<years>）. 招股说明书: present / missing. research/: K files.`
   - 检查 `data/filings/<ticker>/research/`, 空则非阻塞 offer `scripts/download_research.py <ticker> --years 3 --depth-only --max 15`。

3. **PDF 预抽取 cache**: 任一 `_extracted/<pdf-stem>/text.md` 缺失 → 双语 offer `for pdf in data/filings/<ticker>/年报-*.pdf; do python scripts/extract_pdf.py "$pdf"; done`。`skip` → 子 agent 读 raw PDF（慢, 无 page markers）。说明: `text.md` 带 `<!-- page N -->` markers, Read 友好; 图表/表格截图 + LLM 描述 在 `images/`, 是业务分析金矿。

4. **Derive output path** `profiles/<ticker>-<YYYY-MM-DD>.md`:
   - 今日文件已存在 → 直接加载（continuation session）。
   - 只有旧日期文件 → `[resume / start-fresh]`; `resume` → 改名为今日 日期（one-file-per-ticker-per-day 不变量）; `start-fresh` → 新建, 旧文件保留。
   - 无文件 → 复制 `.claude/skills/value-profile/template-zh.md` 到输出路径, 然后做**强制3项 cleanup**（template 含 meta 文档, 必须在开跑前剥离, 否则最终 profile 会残留不属于 ticker-specific 内容的模板说明）:
     1. **Title**: 第一行 `# 价值投资个股研究 Profile — Template` → `# 价值投资个股研究 Profile — <中文公司名> (<ticker>) <report_date>`（例: `# 价值投资个股研究 Profile — 贵州茅台 (600519.SH) 2026-05-01`）。
     2. **删 HTML comment block**: template 开头 `<!-- 模板版本 v2 ... Skill 在调用时会复制本模板到 profiles/<ticker>-<date>.md, 然后逐节填写。 -->` 整段删除。
     3. **删 "阅读姿态/分析框架" 段**: 从 `## 阅读姿态/分析框架（读前必读）` 到随后的 `---` separator 整段删除（指向 SKILL/references 的阅读指引, 属 skill-internal doc, 不属 profile 内容）。
     4. **删 heading 里的 template-instruction parenthetical**: 扫 `^#+` 所有 heading, 删除尾部给填写者的指令性括号 annotation。典型要删的 pattern: `（本节最后填写）` / `（PRIMARY — 先填）` / `（OPTIONAL — 后填）` / `（填入...）` / `（待填）` / `（SECONDARY — 定量补充）`等。heading 本身 title 留下, 只剥离尾部给 filler 的 meta 指示。Ticker-specific 的 title 修饰（如"§3护城河分析"后面的结论性标签）不动。
     
     然后填 Part 0 header（ticker / exchange / researcher = `git config user.name` / report_date = 今日; 中英文公司名 派轻量子 agent 一句话查）。Auto / interactive 两种模式都必须做此 cleanup, 不可跳过。

### Step 2 — Progress map

1. **Parse output file**: 对每个 `^### §` 或 `^## §`, 在其 block 内查找 `**置信度:**`。构造 dict `{section_id: status}`, 值域 `{已完成, 进行中, 未做, 已跳过, 需人工}`。

2. **Render bilingual summary**（两种模式都印, 方便 logging / 用户 observe 进度）:
   ```
   已完成 4 / 67 节（§0, §1.1, §1.2, §1.6）.
   下一节（next undone）: §1.3 差异化
   ```

3. **Route by mode**:
   - **Auto mode (default)**: **直接进 Step 3 on next-undone, 不等输入**。Section 完成后回 Step 2 重新印进度表 + 跳下一节, 循环直到: 所有 undone section 填完 / 触发 abort 条件（§3.pre 假、§4风险 一票否决、Step 1 fetcher 失败）/ 达到 Step 6估值触发条件（≥ 80% 已完成）。
   - **Interactive mode (`--interactive`)**: 印 `[continue / pick-section / exit]` 菜单, 等用户:
     - `continue` → Step 3 on next-undone。
     - `pick-section` → 询问 id; §Q* 去 Step 4; §4.5去 Step 5; 其他 Step 3。
     - `exit` → 停。

**`--section` 跳过 Step 2**（两种模式都是）, 直接进 Step 3。

### Step 3 — Section worker (per section)

#### 3.pre — §3.pre 三大前提（§1 / §3 / §5 前置 gate）

- **§3.pre 三大前提 judgement**: 子 agent 在 §1 / §3 / §5 定性段落前先输出3行判定, 依据 §2.2.1。审计/CFO/ROE 属纯财务数据检查, 与业务理解无关, 所以可做前置 gate。任一假/存疑 → §2.2.2全局降级。

**§1.8 能力圈四问 ≠ 前置 gate**: 四问是 **§1.1-§1.7 拆解完成后**的 synthesis 章节（见 §2.6）, 不是 §1.1 开场前的 gate。子 agent 在 §1.1-§1.7 全部填完之后, 基于已建立的业务理解综合回答四问。理由: 能力圈判定需要对业务先有认知, 才能给出实质性答案; 前置 gate 版本 = "没读就下结论", 与价值投资"看懂再下注"精神反着走。

#### 3a. PDF pre-read

**优先 extracted text cache**:
- `_extracted/<年报-YYYY>/text.md` 存在 → 直接 Read, 用 line-offset + `<!-- page N -->` marker 导航。
- 缺失 → 触发 `scripts/extract_pdf.py` 或 兜底 raw PDF。
- 图片 `_extracted/<pdf-stem>/images/` 带 LLM 描述 sidecar, §1-§2业务分析金矿。

**ToC targeting 起点**:

| section | 年报章节 |
|---|---|
| §1.1主营 / §1.2客户 | 第三节 业务概要; 第四节 经营情况 |
| §1.3-§1.5差异化/盈利/模式 | 第三节; 招股说明书 业务与技术 |
| §1.6现金流 | 第五节 财务报告 现金流量表 + 附注 |
| §2成长空间 | 第四节 行业竞争/管理层讨论 |
| §3护城河 | 第三节 核心竞争力; 第四节 |
| §4管理与文化 | 第六节 重要事项; 第七节 股东; 第八节 董监高 |
| §5风险 | 第四节 风险提示 |
| §Q1-§Q12定量 | 第五节 财务报告（全部）|
| §4.5排雷 | 第五节 附注（逐项）|
| §3.pre 三前提 | 第十节 审计报告 + 第五节 现金流 + 附注 |

#### 3b. Scoped research dispatch

派 ONE `general-purpose` 子 agent。Prompt 英文（指令语言）, 强制中文输出。必须包含:

- section heading + template 的 本节目标/指导问题。
- 解析出的 `<!-- 数据源: ... -->` hint。
- extracted `text.md` 绝对路径（或 raw PDF 兜底）+ 3a 给出的 page range。
- ticker, 中文公司名, exchange, report_date。
- 已填好的相邻 section 作为上下文。
- **三大前提** (§2.2) — §1 / §3 / §5必需, 3行判定。
- **能力圈四问** (§2.6) — §1所有 subsection 必需, 4段独立答。
- **禁用8条空话** (§2.11.3)。
- **管理层口径校核** (§2.11.4) — Part 1 §1-§5必填。
- **5步护城河分析** (§3必需): a 分类（大/准 / 强/省 / 专）+ b 2项可证伪检验（提价/对手/切换成本 / ROE 路标 任选二）+ c 跨年定量追溯（毛利率/净利率 / ROE 5y, CFO/NI 比值, 带页码）+ d 悲观情景（具体技术/偏好/监管/对手情景, 禁空话）+ e 宽/中 / 窄/弱 标签。具体数字准绳见 `.claude/skills/value-profile/references/moat-framework.md` / template §3。
- **§4管理层分析** → **delegate 到 `management-analysis` 子 skill**, 传参 `--target-profile <path> --section §4`; 详细流程（承诺 vs 兑现5年表/董事长5年评估/股东回报/道德风险 一票否决）见 `.claude/skills/management-analysis/SKILL.md` §2-§3。Fallback (子 skill 不可用): 5年 forecast vs actual 表每行带页码, gap > 10% 连续 ≥ 3年 → `**置信度:** 低`, 目标突然消失 = 强信号必须指出, 言行一致检验 ≥ 2事件。具体执行见 management-analysis 子 skill。

#### 3c. Main-agent review

读子 agent 产出。**驳回并重派**若任一:
- 事实缺引用。
- 管理层口径校核 缺失或琐碎复读。
- 填写区 generic, 无 ticker 特定细节。§3护城河 写茅台 必须引用 茅台镇水源 / 12987工艺/基酒5年陈化/品牌价格带。
- §1.8 四问任一 < 50字/品牌复读/结论标签无场景 → §2.6.2退回; 退回的是 §1.8本节, 不动 §1.1-§1.7。

**Auto mode 重派方式 (§2.2.4深调查)**: 不简单重跑同 prompt, 必须**扩大 scope**——指示子 agent (a) 多读 1-2年年报横向追溯趋势 / (b) 增查研报 B类运营明细 / (c) 展开附注项具体条款 / (d) web search 行业同行数据 / (e) 读招股说明书对应章节 / (f) 查监管披露 或 交易所问询函。**重派最多2次**; 仍薄弱 → Acceptable 放宽为 `**置信度:** 中` + 填 `**需人工跟进:** <具体缺什么>` 备注, 继续进下一节, 不 abort。Interactive mode 下用户可在 3d 主动 `research more: <hint>` 给方向, 主 agent 不强制自动加深。

Acceptable 后写中文终稿, 填 `**引用:**` `**置信度:**` `**管理层口径校核:**`（Part 1 §1-§5）。

#### 3d. Save by mode

- **Auto mode (default)**: 3c review 通过 → **隐式 accept**, 直接原子写入 profile（`**置信度:**` 由 3c 写好）, 回 Step 2 找下一节, **不印 menu 不等用户**。3c 连续2次深调查仍不达标 → 隐式 accept 为 `**置信度:** 中` + `**需人工跟进:**` 备注, 继续。
- **Interactive mode (`--interactive`)**: 印 profile 内容中文 + 双语菜单:
  - `accept` → 保存, 覆盖原内容, 进度标 `已完成`。
  - `edit: <text>` → 应用修改, 保存为 `已完成`。
  - `defer` → 不保存, 标 `未做`, 回 Step 2。
  - `skip` → 填 `N/A — <原因>`, 标 `已跳过`, 保存。
  - `research more: <hint>` → 回3b, 把 hint 附到子 agent prompt。

#### 3e. Save and continue

原子写入（`.tmp` 文件 + `mv` 覆盖）。profile 在任何 save 后必须是合法 markdown。回 Step 2。

### Step 4 — Part 2 bulk mode (§Q1-§Q12)

1. **Auto mode**: 默认直接走 `bulk`, 不 offer。**Interactive mode**: offer `[bulk / by-section]` 等用户选。
2. `bulk` → ONE 子 agent: Read 每个年报第五节, 逐年抽 营收 / NI / 扣非 NI / 毛利率/净利率 / ROE / ROA / CFO / CapEx / 有息负债/现金/总资产/总负债/净资产/应收/存货, 就地填 Part 2 §Q1-§Q12表, 每 cell `**来源:**` 带 `年报-YYYY.pdf p.NN`。顶行（ROE / 毛利/净利率）雪球 F10联网交叉验证。
3. **Auto mode**: 子 agent 在 prompt 里明确要求它自己执行 random-sample 5 cells 雪球校核 + 汇报结果, 主 agent 收到后自动按 ≥ 4/5一致 规则判决（≥ 4/5 → 所有 §Q* 标 `已完成`; 否则 不一致行 标 `需人工`）, 不问用户。**Interactive mode**: 呈给用户 `Random-sample 5 cells: given <ROE 2024 = X%>, does 雪球 agree? [all-match / mismatch: <details>]`, 用户回复后主 agent 按规则判决。
4. ≥ 4/5一致 → 所有 §Q* 标 `已完成`; 否则 不一致行 标 `需人工`。
5. `by-section` (interactive only) → 走标准 Step 3。

### Step 5 — 排雷清单模式 (§4.5)

**Delegate 到 `financial-redflag-scan` 子 skill**, 传参 `--target-profile <path> --section §4.5`; 详细流程（29项清单 + 6项高危 附加检查 + 三表勾稽4条 + summary + 强制 `[accept / edit / research more]` 不 `defer / skip`）见 `.claude/skills/financial-redflag-scan/SKILL.md` §2-§3。

**Fallback（子 skill 不可用时, 主 skill 跑简化版）**:

1. 派 ONE 子 agent 对 Part 4 §4.5 29项逐项扫, 每项 `是 / 否 / 不适用 / 需人工` + 证据 + 页码; 6项高危 附加检查 显式 flag（商誉/净资产>20% | 其他应收≥10%流动资产 | 在建工程长年不转固 | CFO/NI<50%连续2年 | 生物资产/农林渔牧 | 管理层道德风险一票否决）。详细阈值/三表勾稽/造假模式 见 `.claude/skills/financial-redflag-scan/references/fraud-library.md` §1-§4; 附注12项 见 `.claude/skills/read-filing/references/statement-reading.md` §3。
2. 主 agent 复核缺引用 → re-dispatch（§2.2.4深调查）。写 `**发现的风险 summary:**` 1-2段。
3. **Auto mode**: 3c 通过即保存, 不 confirm。**Interactive mode**: 用户确认 `[accept / edit / research more]`。


### Step 6 — 执行摘要合成 (Part 0估值)

触发条件: ≥ 80% section 标 `已完成`。

**前置检查**: 若 §3.pre 三大前提 任一 假/存疑 → abort:
> `❌ 估值前置清单未通过（§<which> = 假/存疑）. 无法进入估值. 请先修复 §3.pre, 或将 Part 0 标 "不可估值 — 仅定性研究"。`

**生意类型检查** (§2.3.1): 判定落在6类哪类, "不适用 PE" / "默认回避" → Part 0标 "定性研究 only", 不输出估值数字。

**7字段结构化中文输出** (依据 §2.4 / §2.5):

1. **3年后归母净利润（三档）** — 业务板块拆解（≥ 2块, 每块 量 × 价 × 净利率）: 乐观/中性/悲观, 每档附假设。
2. **合理 PE** = 1 / 10y 国债收益率 (~3.5% → ~28x, 典型25-30)。生意类型 见 §2.3.1估值矩阵。
3. **合理估值** = 中性3y NI × 合理 PE（± 10% 带宽）。
4. **买点** = 合理估值 × 50%（高杠杆 × 35%, 必须说明为何高杠杆, 依据 §2.3.1硬指标）。
5. **卖点** = min(合理估值 × 1.5, 当年 NI × 50PE)。两候选都列, 取较低者。
6. **持仓姿态** (§2.5.2 discrete): 加仓/建仓 | 持有不动（收工睡觉）| 分批清仓。
   - **§2.9.1估值动摇即停手 守则**必须 inline 提示: 跌破买点第二档时, 若3y NI 预估动摇, 立即停止加仓, 回头重审 下限 → 重算新买点 → 再决定。
7. **Top 3风险** — 来自 §5 + §4.5, 每条1-2句 + 触发条件。

**置信度汇总**: `高` 当 ≥ 60% section 高 AND §3.pre 全真; `中` 混合; `低` 任一块未做 OR 任一前提 存疑。

- **Auto mode**: 3c review 通过（7字段完整、数字源头可追溯、§3.pre 全真或已 mark 降级）即 save 并 **skill 自行终止**。打 final summary: `✅ Profile 完成. N/67 sections 已完成, 估值 Part 0已合成. 路径: profiles/<ticker>-<date>.md`。
- **Interactive mode**: 印摘要 + 双语菜单 `[accept / edit / research more]`, 等用户确认 → save。

---

## §4 Operational Boilerplate

### §4.1 Language policy

- **Profile 内容** (`.md`): 中文。填写区、`**引用:**`、`**管理层口径校核:**`、总结段均中文。
- **Operator 输出**（确认节点 / status / errors）: 双语, 中文为主。
- **子 agent prompts**: 英文（指令）, 强制中文输出。
- **Commit messages**: 英文。
- **避混用**: 不写 "SOE 企业 / stakeholder 视角 / bear case 情景", 统一中文化（国企/利益相关方/悲观情景）。保留缩写仅 ROE / ROIC / DCF / GDP / PE / PB / ESG。
- **CJK-ASCII 空格规则**: 中文与紧邻西文/数字不加空格。写 "ROE15%" 不 "ROE 15%"; "营收增长" 不 "营收 增长"; "大/准/强" 不 "大 /准 /强"。

### §4.2 What this skill MUST NOT do

- MUST NOT 重写标 `已完成` 的 section（除非显式 `--force`, v0不提供）。
- MUST NOT 编造数字或引用。无来源写 `待补充` + 原因。
- MUST NOT 用英文写 profile 内容。
- MUST NOT 没有年报 PDFs 就开干。Step 1.2 offer fetcher 或 abort。
- MUST NOT 跑 `git commit`。用户自 commit。
- MUST NOT 调用 `src/ah_research/`（平台数据层未就绪）。
- MUST NOT 未经 Step 1.2显式确认就自动下载 PDF。`no` / `show-command` 必须不动文件系统。

### §4.3 Failure modes & recovery

| Failure | Recovery |
|---|---|
| 子 agent 输出缺引用 | **Auto**: 重派 subagent 扩大 scope (最多2次, §2.2.4); 仍缺 → 标 `**置信度:** 中` + `**需人工跟进:** <具体什么缺>`, 继续下一节不 abort。**Interactive**: 主 agent 把无引用论断改写为 `证据不足, 需人工补充`, 等用户下一步。**两种模式都绝不编造** |
| `管理层口径校核` 琐碎话漏网 | Step 3c 应拦住; 作 skill-regression 信号 |
| 年报 PDF 损坏 | 标 `年报-YYYY.pdf（unreadable）`, 用其他来源, 不 abort 该 section |
| 两个 session 并发编辑 profile | 不自动 resolve; warning, 用户手动解决 |
| 子 agent 配额/限流 | 窄 page range 重试一次; 仍失败 → `待补充` + 原因, 状态 `进行中` |
| Step 1.2 fetcher 失败 | 回退手动 cninfo URL 并 abort。**绝不生成无 filings 的破 profile** |
| 用户选的 section id 不在 template | 建议最近匹配（`1.3` → `§1.3 差异化`）; 不静默继续 |

### §4.4 Graduation path (Phase 1落地后)

1. **Step 4 Part 2 bulk** → 子 agent 优先 `ah_research.DataRepository.get_fundamentals(<ticker>, start=<10y>)`, repo 未覆盖回退 PDF。
2. **Step 5排雷 纯数值项**（应收/营收, 商誉/净资产, 有息负债/CFO）→ DataRepository 算术。
3. **定性 section**（§1-§5, §4.5定性项）继续 PDF。没有数据源能替代管理层原话。
4. **`scripts/download_filings.py`** 挪进 `src/ah_research/integrations/cninfo_client.py`, 暴露为 repo 方法。

### §4.6 Profile 输出风格 — 给人读的, 不是给 AI 读的

Profile 的读者是人（研究员 / 投资人 / 审阅人）, 不是另一个 AI agent。写法必须服务于人类 scan + 理解。

- **§4.6.1 浓缩原则**: 核心是"内容少但每句精华, 信息量高"。Part 0 执行摘要用 **bullet 分层**（每项"状态行" + 3-5 个 sub-bullet 核心证据, 每个 sub-bullet 1 句浓缩）, **不必压缩到 1 行**。目标: 读完 Part 0 约 1-2 分钟能抓到所有结论 + 跟踪项。细节留 Part 1-5 / §Q / §4.5。
- **§4.6.2 禁用 AI 自引用 + 内嵌文献引用 (全 profile 非仅 Part 0)**: narrative body 禁两类内嵌 refs:

  **(a) 禁 `(§x.y)` 自引用**: 例 "毛利率92% (§1.1)"——事实自证, 不需指向源 section。允许的 § 引用形式: `**引用:**` 结构字段 / 开头为 "依据 §2.2 三大前提..." 的规则指向句 / "SKILL §2.9 守则" 这类 rule pointer。禁: 句尾裸括号 section id 如 `XXX (§1.5)`。

  **(b) 禁 inline 文献引用塞段落中**: 禁 `XXX (年报-YYYY.md p.NN)`、`YYY (华鑫研报 p.260)`、`ZZZ (Kantar BrandZ, 年报-YYYY.md p.19)` 样在段落文字里内嵌 page-specific cites——这些是 AI "to prove I'm not hallucinating" 式标注, 对 reader 是 noise。**引用集中到本节末尾 `**引用:**` 字段**, 身体段落直接陈述事实即可。读者需追溯时翻 `**引用:**` 字段。

- **§4.6.2.bis body 段落 readability**: 每个 section 身体段落写给人读, 不是给 AI dump:
  - 禁 `(a)(b)(c)(d)` / `①②③④` inline list 散排在段落内——用真 markdown `- xxx` bullet, 每条独立一行。
  - 禁 wall-of-text 长段落——每个独立概念一段, 段间空行, 每段 3-5 句上限。
  - 数字尽量配紧凑上下文, 不用"在...的情况下/基于...的考虑"长从句包数字。
  - 子标题 `**核心资产**` / `**生产流程**` / `**分产品收入**` 用粗体分块, 帮 reader 快 scan。
- **§4.6.3 英文强制中文化 — 白名单原则** (依据 §4.1 language policy): Part 0 执行摘要 + Part 1-5 narrative 里, **只允许白名单英文**, 白名单外的任何英文单词 / 缩写 (不管是 "mix" / "framework" / "clean" / "CFO" / "EBITDA" / 还是任何别的未见过的词) **一律中文化**。

  **判定规则** (单向): 只看 "是否在白名单里"。不在 = 禁, 查中文对应翻; 在 = 保留。**无需维护黑名单**——新出现的英文默认禁, 对照表非 exhaustive, 只是常见词参考。
  
  Step 3c 主 agent review 时发现白名单外英文 = 驳回 subagent 重派 (不是主 agent 自己打补丁加对照表)。

  **白名单** (业内普及到 ≈ 中文, 缩写形式保留):
  - 估值指标: ROE / ROIC / ROA / DCF / PE / PB / PS / PEG / EV / EBITDA
  - 时间 / 比率: CAGR / YoY / QoQ / TTM
  - 用户指标: MAU / DAU / ARPU / LTV / CAC
  - 集中度: CR5 / CR10 / GMV
  - 宏观 / 合规: GDP / ESG / IPO / H 股 / A 股 / KPI / OKR / ABT / SKU
  
  白名单外一概中文化。若某词业内找不到自然中文对应, 用描述性短句, 不自造新英文或混用。

  **常见词中文对应参考** (非 exhaustive, 仅帮 subagent 快查常见词):

  | 英文 | 中文 |
  |---|---|
  | CFO / NI / CapEx / FCF | 经营现金流 / 净利润 / 资本开支 / 自由现金流 |
  | NOPAT / WACC | 税后经营利润 / 加权平均资本成本 |
  | TAM / SAM / SOM | 潜在市场规模 / 可服务市场规模 / 实际拿下市场规模 |
  | SG&A / COGS / DSO / DPO / DIO | 销售管理费用 / 营业成本 / 应收 / 应付 / 存货周转天数 |
  | framework / guidance / pass / fail / clean | 框架 / 指引 / 通过 / 未通过 / 合规 (context 而定) |
  | checklist / summary / scope / benchmark | 清单 / 摘要 / 范围 / 基准 |
  | overlay / actual / forecast / narrative / reference | 叠加 / 实际 / 预测 / 叙述 / 参考 |
  | cross-section / Top N | 跨 (类别 / 年份 / 行业) / 前 N |
  | bear / base / bull case | 悲观 / 中性 / 乐观情景 |
  | stakeholder / SOE | 利益相关方 / 国企 |
  | mix / product mix / channel mix / revenue mix | 产品结构 / 产品组合 / 渠道结构 / 收入结构 (context 而定) |
  | red flag / green flag | 风险信号 / 积极信号 |
  | M&A / IPO (动词 / 事件时) | 并购 / 上市 (IPO 作缩写保留, "to IPO" 这类动词用法禁) |

  遇到上表没有的白名单外英文 = 按规则先禁, 然后查行业中文表述再译。
- **§4.6.4 Part 0 结论标签 + 顺序 + 状态词 → 见 template**: schema 的 single source of truth 在 `.claude/skills/value-profile/template-zh.md` 的 Part 0 placeholder。填写时必须严格照 template 的 6 项顺序 (好生意 → 护城河 → 管理层 → 财报排雷 → 能力圈四问 → 估值三大前提) 和状态词选项（`<宽 / 中 / 窄 / 弱 / 否>` 这类尖括号列表）。**禁自造状态词 + 禁 AI 直译**（本规则适用**全 profile**, 不仅 Part 0）:

  | ❌ AI 直译 / 意译 (禁) | ✅ 自然中文金融词 | 用于 |
  |---|---|---|
  | 清洁 / clean | **无触发** / **零触发项** / **无警示** / **合规** | 排雷扫描结果 |
  | 清洁（指管理层）| **合规** / **诚信合规** / **未触发一票否决** | 管理层扫描 |
  | pass / 通过 | **通过** (状态 OK) / **未触发** (排雷) / **达标** (指标) | 检验 / 扫描 |
  | clean audit / 干净审计 | **标准无保留审计意见** | 审计结果 |
  | healthy / 健康 | **财务稳健** / **结构稳健** | 财务状况 |
  | risk-free / 无风险 | **未识别重大风险** | 风险扫描 |
  | robust / 稳健 | **稳健** OK; 但避免直译 "robustly" → "健壮地" 这类 | 通用 |
  | green flag / 绿灯 | **积极信号** / **正面信号** | 信号判定 |
  | red flag / 红旗 | **风险信号** / **警示项** | 风险条目 |

  **判定原则**: 若某词看起来像"英文直接翻译过来", 查行业中文表述; 没有 exact 中文对应就用描述性短句（"本项扫描未发现异常" vs "清洁"）。**禁创新中文状态词**——只能用 template 列的 schema 选项。若需新增状态词, 改 template 先, 不在 profile 里自造。

- **§4.6.5 跟踪项 / 风险项 视觉强调**: Part 0 + section 内遇到"需跟踪 / 需注意 / 风险信号"条目, 用 `⚠️ **跟踪 N**:` 或 `⚠️ **注意**:` 格式显式 flag, reader 一眼识别"哪些项需持续观察"。
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

  **判定办法**: 写完一段读一遍——读起来卡、需停顿才懂、像翻译腔 = awkward, 改成母语自然说法。Step 3c 主 agent review 时抽查本节目标 / 结论句 / 填写区头尾句, 发现 awkward 句退回重派。

- **§4.6.8 禁写 AI-runtime meta blocks**: Profile 是 ticker-specific research doc, 不含运行 telemetry。**禁写**以下块:
  - "本 profile 完成状态" / "填写 section 数 67/67" / "Auto mode 完成时间" / "Profile 定位" / "✅ Profile 完成" 等完成状态 meta
  - "> 本摘要基于 AI 研究 + 用户审阅, 非投资建议" 等 AI-generated disclaimer
  - "置信度分布: 高 X% / 中 Y% / 低 Z%" 等 profile-level 统计（section 级 `**置信度:**` 字段保留）
  - "最近审阅日期" 除非已填 Part 0 header 表格里
  
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

数据源 hint: 年报 第三节"公司业务概要"; 招股说明书"业务与技术"。

PDFs to read:
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/_extracted/年报-2024/text.md pages 8-35
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/_extracted/年报-2023/text.md pages 8-35
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/_extracted/招股说明书/text.md pages 40-80

Adjacent context（已填好 sections）:
§1.1 公司核心资产、主营产品和服务: <inlined content>
§1.2 公司客户: <inlined content>

Output requirements:
1. 中文作答。
2. 先走 §2.2 三大前提 3 行判定 + §2.6 能力圈四问 4 段答（§1 subsection 必需）。
3. §1.3 填写区写 3-6 条关于茅台差异化的具体论断。候选证据: 茅台镇水源、12987 工艺、基酒 5 年陈化、品牌价格带、经销商渠道网, 每条带年报页码。
4. 每条引用 `年报-YYYY.pdf p.NN` 或 web URL。无法核实 → `证据不足, 需人工补充`。
5. 填 **管理层口径校核:**, 对比年报 vs 研报 / 价盘 / 媒体。"年报说 X, 我们同意" = 不合格。
6. 按引用密度和 spin-check 深度设 **置信度:** 高/中/低。
7. 禁用 §2.11.3 的 8 条空话。只写 ticker-specific 证据。

返回完整 section block（heading + 填写区 + 引用 + 置信度 + 管理层口径校核）。
```
