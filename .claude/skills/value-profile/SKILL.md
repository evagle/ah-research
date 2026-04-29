---
name: value-profile
description: Walk a user through filling out a 价值投资 profile for a single A-share / HK stock. Auto-fetches 年报 / 招股说明书 PDFs via scripts/download_filings.py when missing, reads them as first-hand primary sources, gathers qualitative + quantitative research section-by-section, writes Chinese-language profile to profiles/<ticker>-<date>.md as it goes. Trigger on "/value-profile <ticker>", "研究 股票 <ticker>", or "fill out profile for <ticker>".
---

# Value Profile Skill

本 skill 是一份给主 Claude Code session 读的指令文档, 结构分三层: **§1 投资哲学（信念 / 心法）→ §2 规则（从哲学推出的纪律）→ §3 流程（Step 1-6 如何执行）**。读者应先把 §1 完整通读 internalize, 再查 §2 规则, 最后照 §3 操作。§4 是跨层 operational boilerplate。

## §0 Skill 运行方式

This skill runs as the **main Claude Code session agent** and orchestrates research via `general-purpose` subagents. It is an instruction document for the main model, not library code. The main agent owns file I/O, user 确认节点, and review; subagents do scoped PDF reads and web research.

**理论血统**: 本 skill 的方法论内核吸收自 `docs/value-profile/methodology-tang.md` 及其深度附录 `docs/value-profile/tang/01-05-*.md`。该 5 份附录是理论来源, 不在 SKILL / template / profile 正文中反复署名。以下所有 principles / rules / procedures 都已 internalize 为本项目的默认方法, 子 agent 无需再标注"按某某方法"。

---

## §1 投资哲学核心原则

本节 12 条原则是整个分析流程的信念层。每一条都是长期不变的 meta-principle, 不含具体操作步骤。派任何子 agent 前, **主 agent 先在开场白里把本节通读一遍 internalize**; §2 规则、§3 流程 都是 §1 的推论。

### §1.1 股票是生意的凭证, 不是纸片

**持有股票 = 持有"一只会下蛋的母鸡"分成权**。内在价值 = 未来自由现金流折现之和, 与每日市价无关。市场价格不更新内在价值; 牛市是投资者的"风落之财", 长期复利来自企业内生现金流, 不来自"傻子馈赠"。

违反症状: 把 "最近股价涨 / 跌了 X%" 当信号, 用 K 线 / 板块轮动 / 资金流判断买卖, 把市值当锚。

### §1.2 利润三问是估值的承重墙

任何估值动作之前必须先对以下三问给出 "真 / 假 / 存疑":

① **利润为真** — 经营现金流净额 ≥ 净利润; 销售收现 / 营收 ≥ 1+增值税率; 应收 / 存货 / 商誉 结构干净。
② **利润可持续** — 需求 10 年仍在; 护城河可验证而非声称。
③ **维持利润不需大投入** — 自由现金流 = 经营所得 − **维持性** CapEx（不是全部 CapEx）。长安汽车每年 65 亿维持性 CapEx 是 "泡沫利润", 需去泡沫化。

三问 **必须全部为真**。任一 "假 / 存疑" → 25PE 合理估值法 不适用, 必须打折或放弃。

违反症状: 看报表 PE 不看 CFO/NI 比值; 未拆维持性 vs 扩张性 CapEx 就算自由现金流。

### §1.3 商业模式决定估值方法, 用错方法等于价值陷阱

不同生意的 "3 年后净利润可预估度" 差异巨大, PE 不是万能: **强护城河消费 / 平台互联网 适用 25PE**; **周期股 / 资源 顶部 PE 低 是陷阱, 底部 PE 高 是机会, 不适用 PE**; **银行 用 PB**; **保险 默认回避**; **公用事业 用 DCF 简化版**; **高杠杆 企业 PE 下调 + 折扣加深 到 35%**。

违反症状: 给周期股套 PE; 给高成长股 40+ PE; 用 PEG 抬 PE 超 25; 把高杠杆标的按常规 50% 买点算。

### §1.4 三年后的确定性 >> 今天的精确性

估值靠 **三年后 可预估**, 不靠 **今天 精准**。选 3 年窗口是因为: 短于 1 年 = 短期博弈（噪声 > 信号）, 长于 5 年 = 超出绝大多数行业的可预测半径。§1 商业模式 + §2 成长空间 收尾时必须能回答 "这家公司 3 年后 的净利润中枢大约在哪里, 依据是什么"。答不出 → 不适用 25PE 估值法, 必须更深折扣 或 弃权。

违反症状: 追求精准 DCF 到小数点后两位; 或反过来, 用 "长期看好" 敷衍, 不给 3 年窗口的量化上下限。

### §1.5 安全边际是"我错了也不亏", 不是"便宜"

50% 折扣的意义不是占市场先生的便宜, 而是 **给自己估算错误留空间**。即使真实价值只有估算的 70%, 50% 买入仍能不亏。判错概率越高（认知不深 / 行业变化快 / 管理层难评）**应提高折扣**而不是降低门槛买入。高杠杆企业折扣加深到 35% 同理。

违反症状: 把折扣当 "市场情绪", 越跌越机械加仓; 不反思判断可能错, 只反思 "市场先生发癫"。

### §1.6 能力圈是硬边界, 写不出具体答案 = 不下注

"看得懂" 的标准是 **能力圈四问** 全能口述具体答案:

① 公司靠销售什么商品 / 服务获取利润?
② 客户为何从它这里采购, 不选其他机构?
③ 资本天性逐利, 为什么别的资本没抢走它的份额或逼它降利?
④ 假设同行 / 巨头 挟巨资参与竞争, 它能否保住乃至扩张份额?

四问任一答 "抽象空话 / 品牌复读 / 结论标签无场景" = 能力圈外, **不下注**, 错过是价值投资的标配。"跨出能力圈下注, 是注定要被别人收割的——早晚而已。"

违反症状: "行业龙头 / 品牌强大 / 成长空间巨大 / 护城河宽广" 这类空话撑起的 §1, 没有产品级拆分、客户场景、挑战者名单、假想敌推演。

### §1.7 市场波动 ≠ 信息, 价格不改变价值

格雷厄姆的 "市场先生" 寓言: 市场报价每天变, 企业内在价值几年才变一次。默认动作是 **呆坐不动**。股价上涨不是卖出理由, 估值超区间 才是; 股价下跌不是买入理由, 估值进入买点 才是。

违反症状: 用 K 线 / 量价 / 资金流 做决策; 用 "最近表现" 修订研究结论。

### §1.8 耐心是资产, 空仓等待不是机会成本

不主动留现金等机会; 但也不为保持仓位 而急于投出去。所有持仓都超合理估值 + 没有新标的进入买点 → 自然产生现金, 等下一个买点即可。"单纯持有类现金资产等待股价下跌的所谓仓位管理"是明确反对的。

违反症状: FOMO 驱动的仓位管理; 把 "子弹池" 当择时工具。

### §1.9 认错 > 坚持: 下注行为正确 ≠ 下注结果正确

估值判断本身动摇时, 纪律化加仓会从 "遵从体系" 滑向 "赌气 / 摊低成本执念"。跌破买点第二档 / 第三档 遇新信息（季报 / 行业变化 / 三大前提 由 "真" 松动到 "存疑"）动摇 3 年后净利润预估 → **立即停止加仓**, 不再机械摊低成本。正确顺序: ① 回头重审 3 年后净利润下限; ② 重算合理估值 + 新买点; ③ 再决定新行动（继续加 / 持有观望 / 止损重估）。**承认 "我看错了" 是完全合法的结论**。

违反症状: "原计划每跌 X% 加仓" 的机械执行; 用 "市场先生发癫" 掩盖判断已动摇。

### §1.10 集中于高确定性 > 分散于平庸

从分散入手（起步 = 指数）→ 看懂一家转一家 → 成熟 持有 **4-6 家**。超过 8 家 → 必然有几家没看懂, 回指数。单一持仓上限 40%（极端可到 50%, 茅台 2017-2020）, 下限约 10%（不敢重仓 = 没看懂 = 干脆不持）。同行业同时持仓 不超 2 家。

违反症状: 20+ 只股组合, 每只都是 "浅水位"; 或单一仓位 > 50% 而四问 / 三前提 未全过。

### §1.11 年报是写给全体利益相关方的文档, 真相在附注

年报读者 = 监管 + 党组织 + 员工 + 地方政府 + 股东 + 供应商 + 经销商 + 投资者 + 媒体 + 竞争对手。价值投资者不是首要读者。因此读年报要 **读出弦外之音**: 哪些段落是合规话术 / 员工福利信号 / 地方政绩信号, 哪些才是实质经营信息。**正文可略读, 附注必须逐行读**——应交税费、关联交易、对外担保、其他应收款明细、存货构成、商誉减值测试假设、金融资产 4 分类 是否发生过跨档切换, 实质信息都在附注。

违反症状: 只读正文 "经营情况讨论与分析" 就下结论; 把管理层口径当事实。

### §1.12 好生意 优先级 高于 好管理层

三好标准的顺序不可换: **好生意 → 好公司 → 好价格**。一流生意 + 三流管理层 通常优于 三流生意 + 一流管理层, 因为一流生意的经济商誉能让平庸管理层也挣到钱 (粤高速、长江电力), 而三流生意 + 一流管理层 = 管理层被迫不断重组 / 转型 / 跨界, 成功稀少且不可复制。§1 (好生意) 判定 "否" 不要指望 §4 (管理层) 救回; §1 判定 "是" 时, §4 平庸可接受, 只要不存在 §4 红旗 (道德 / 大股东占款 / 系统性画大饼)。

违反症状: 用 "管理层优秀" 对冲 "商业模式平庸"; 期待明星 CEO 能把垃圾生意做成金矿。

---

## §2 规则层

本节是从 §1 推出的可操作纪律。每条规则编号 `§2.N.x` 对应 原则 `§1.N`, 读者可以追溯 每条规则的信念来源。规则不是详细清单——详细清单（如 29 项排雷、13 条 playbook、5 步护城河 宽/中/窄/弱 具体数字）留在 template / methodology 里, 本节只给操作框架。

### §2.1 股票 = 生意

- **§2.1.1 禁用 K 线 / 量价 / 资金流**: 不把 "最近涨 / 跌 X%" 当决策输入。买卖动作只由 估值（§2.3 / §2.5）+ 事实翻案（§2.9）触发。
- **§2.1.2 数字必带引用**: 每个财务数字后面 `(年报-YYYY.pdf p.NN)` 或 URL。不带引用 = 未核实。子 agent 禁止从记忆编数字, 找不到写 `待补充 — 年报未披露` 或 `证据不足, 需人工`。

### §2.2 利润三问是前置门槛

- **§2.2.1 三项判定** (§3.pre 子 agent 开场白必走):
  ① 审计意见 = 标准无保留 (会计所 + 近 3 年是否换所)
  ② 近 3 年 CFO 累计 ≥ NI 累计; 销售收现率（销售商品提供劳务收到的现金 / (营业收入 × (1+增值税率))）≥ ~1.0 ±5%
  ③ 近 5 年 ROE 稳定 ≥ 15%; 毛利率 波动 ≤ ±5 点; 扣非 NI / NI ≥ 0.85
- **§2.2.2 任一 假 / 存疑 → 全局降级**: 整份 profile `**置信度:** 低`, 阻断 §3 Step 6 估值; Step 6 需 abort 并打 "估值前置清单未通过" 提示条。
- **§2.2.3 销售收现 交叉验证**: 应有销售收现 = 营收 × (1+VAT) − Δ应收账款 − Δ应收票据 + Δ合同负债 − 贴现财务费用。对比现金流量表实际值, **背离 > 5% 连续 2 年 → §4.5 排雷 触发深调**。

### §2.3 商业模式 → 估值方法对照

- **§2.3.1 6 类生意估值矩阵**（套用前先判定公司落在哪一类）:

  | 生意类型 | 估值方法 | 买点折扣 | 说明 |
  |---|---|---|---|
  | 强护城河消费 / 平台互联网龙头 | 25PE（顶级 30）| 50% | 常规 25, 茅台 / 腾讯 级别 敢用 30 |
  | 周期股 / 资源 / 化工 / 航运 / 钢铁 / 水泥 | 不适用 PE | — | 用 穿越周期平均 NI × 15PE 或 PB < 1 清算, 否则弃权 |
  | 高成长股（年化 > 25%）| 25PE 上限不破 | 50% | 用保守下限; 不 用 PEG 抬到 40+ |
  | 金融 — 银行 | 改用 PB（1.0-1.15× 真实净资产）| 35% | 真实净资产 = 账面 − 未计提不良真实损失 |
  | 金融 — 保险 | 默认回避 | — | EV 折现假设多且无法客观验证 |
  | 高杠杆（地产 / 部分电力 / 开发商）| PE 下调到 8-12 | 35% | 硬指标: 有息负债 / 净资产 > 1 或 / CFO 近3年 > 3 |
  | 公用事业（水电 / 高速 / 港口）| DCF 简化版 | 股息率 > rf × 1.3 | 用 稳态 FCF / (rf + 2%); 看 折旧 vs 维持性 CapEx 差额 |

  同时符合多类 (如 高杠杆 + 周期) → 取最严档。"不适用 PE" / "默认回避" → Step 6 不输出估值数字, Part 0 标 "定性研究 only"。完整准绳见 `docs/value-profile/tang/02-估值法完整框架.md` + `methodology-tang.md` §F。

### §2.4 3 年窗口与可预估度

- **§2.4.1 3y 净利润三档必填**: 乐观 / 中性 / 悲观, 至少 2 个业务板块拆解, 每块 量 × 价 × 净利率, 每档附具体假设一句。
- **§2.4.2 PE 锚与增速无关**: 合理 PE = 1 / 10y 国债收益率（当前 ~3.5% → ~28x, 典型 25-30）。超出需 justify。增速 已反映在 3y NI 里, 不重复计入 PE。

### §2.5 安全边际 = 估值错误容差

- **§2.5.1 买点 / 卖点 公式**:
  - 买点 = 3y 合理估值 × 50%（高杠杆 × 35%; 必须 说明 为何判定高杠杆）
  - 卖点 = min(3y 合理估值 × 150%, 当年 NI × 50PE)——两候选都列, 取较低者
- **§2.5.2 持仓姿态 discrete**:
  - 当前 市值 < 买点 → 加仓 / 建仓（分批, 一次 ≤ 目标仓位 1/3）
  - 买点 ≤ 当前 ≤ 卖点 → 持有不动（收工睡觉, 每年年报后重估一次）
  - 当前 > 卖点 → 分批清仓（触点卖 1/3; 再涨 10% 卖 1/3; 再涨 10% 清仓）

### §2.6 能力圈四问是 §1 前置条件

- **§2.6.1 四问逐段答**: §1 商业模式所有 subsection（§1.1-§1.7）子 agent 开场必先独立答 四问, 每问 ≥ 50 字, 含 ticker 特定证据（产品 SKU / 客户场景 / 竞品名 / 挑战者份额 / 假想敌推演）, 禁品牌复读和结论标签。
- **§2.6.2 任一失败 = 退回 §0 重审**: 主 agent 复核任一问 < 50 字或仅品牌复读或仅结论无场景 → 退回子 agent 补证据; 反复退回仍失败 → §1 全部子 section 标 `**置信度:** 低`, 在 §1.1 头部标 "能力圈四问第 X 问未达标 — 需补充证据或放弃", profile 降级为仅定性观察, 不得进入 Step 6 估值。

### §2.7 波动纪律

- **§2.7.1 每年年报后 重估一次** 是默认节奏; 重大事件（季报 / 行业结构变化 / 管理层更迭）补重估。期间 不看股价波动。
- **§2.7.2 买点 / 卖点 以外的波动不触发动作**——哪怕上下 50%。

### §2.8 耐心规则

- **§2.8.1 不主动留现金择时**; 但也不为仓位而急投。
- **§2.8.2 分红到账 再投资决策**: 仍低于买点 → 再买原股; 否则 → 进子弹池等下一个买点。不为 "分红了就必须立即投出去" 急于行动。

### §2.9 估值动摇即停手

- **§2.9.1 跌破买点第二 / 第三档时 的 硬规则**: 若 新信息（最新季报 / 年报 / 竞争格局质变 / 之前推导被发现逻辑漏洞 / 三大前提 某项由 "真" 松动到 "存疑"）动摇 3y NI 预估, **立即停止加仓**。正确顺序: ① 重审 3y NI 下限; ② 重算合理估值 + 新买点; ③ 再决定新行动。
- **§2.9.2 卖出只由 两件事 触发**:
  - 估值逻辑: 市值 > 卖点 → 分批清仓
  - 事实翻案: 研究发现之前判断错了（新年报披露 三大前提 某项不过, 或 护城河假设被打破）
  - **不因为股价跌而卖, 不因为股价涨而买**。"止损 / 止盈" 这类技术派概念不存在。

### §2.10 组合集中度

- **§2.10.1 目标 4-6 家, 上限 8 家**。超 8 家退回指数。
- **§2.10.2 单一持仓上限 40%**（极端 50%, 需 三前提 全过 + 四问全清晰 + 承诺兑现 record 良好）; 下限 10%（不敢重仓 = 没看懂, 干脆不持）。
- **§2.10.3 同行业不超 2 家**（避免行业风险集中, 但允许同行业不同环节, 如白酒高端 + 次高端）。

### §2.11 年报阅读纪律

- **§2.11.1 优先 extracted text cache**: 派子 agent 前, `data/filings/<ticker>/_extracted/<年报-YYYY>/text.md` 必须存在（带 `<!-- page N -->` marker）。缺失则先 shell out `python scripts/extract_pdf.py`。
- **§2.11.2 必读附注 12 项**: 货币资金受限 / 应收账款 5 大客户 + 账龄 / 应收票据 银票 vs 商票 / 预付账款对象 / 其他应收款关联方 / 存货分项 + 跌价 / 在建工程转固 / 商誉减值假设 / 合同负债占营收 / 应付账款议价权 / 长投 + 可供出售金融资产 / 有息负债。详见 `methodology-tang.md` §J.1。
- **§2.11.3 禁用 8 条空话**: "具有强大品牌 / 技术领先 / 行业龙头 / 管理优秀 / 市场广阔 / 核心竞争力突出 / 护城河宽广 / 成长空间巨大" 无具体佐证（人名 / 数字 / 日期 / 引用） 一律退回重写。
- **§2.11.4 管理层口径校核**: Part 1 §1-§5 每个 section 必填, 对比年报 vs 研报 vs 财新 vs 经销商反馈 vs 价盘 vs 监管披露, 指出哪里年报做了美化 / 避而不谈。"年报说 X, 我们同意 X" 视为不合格, 退回重做。

### §2.12 好生意 > 好公司

- **§2.12.1 §1 verdict 字段**: §1 收尾给出 `好生意: 是 / 否 / 存疑` verdict; Step 6 估值 必须 引用 此 verdict; "否" 直接 Part 0 标 "定性研究 only"。
- **§2.12.2 §4 红旗 一票否决**: 即使 §1 = 是, §4 出现 道德红旗 / 大股东占款 / 系统性画大饼（连续 3 年年初 guidance 大幅高于实际）/ 虚假陈述 处罚记录 → 直接淘汰, profile 终止。

---

## §3 分析流程（Step 1-6）

本节描述主 agent 如何执行。principles / rules 已在 §1 / §2 讲过, 本节 只讲 "如何派子 agent、如何 validate、如何路由", 不重复陈述 纪律。

### Invocation

- **Primary:** `/value-profile <ticker>` — ticker 是 `<code>.<exchange>`（例: `600519.SH`, `000001.SZ`, `0700.HK`）, 验证正则 `^[0-9]{4,6}\.(SH|SZ|HK)$`。
- **`--section <id>`** — 跳到指定 section, 例 `/value-profile 600519.SH --section 1.3`。跳过 Step 2 progress summary, 直接进入 Step 3。
- **`--resume`** — 强制加载最近一个 `profiles/<ticker>-*.md`, 不询问日期。

Skill 不会自行终止, 每个 section 确认节点后都会把控制权交回用户。

### Step 1 — Bootstrap + filings audit

1. **Validate ticker** against `^[0-9]{4,6}\.(SH|SZ|HK)$`. 失败双语报错并 abort:
   > `❌ 无效 ticker: <input>. 期望格式 <code>.<exchange>（例 600519.SH, 0700.HK）. / Invalid ticker.`

2. **Audit `data/filings/<ticker>/`**:
   - 若目录缺失 OR 匹配 `年报-*.pdf` 的文件 < **2** 份:
     > `❌ 缺少年报 PDF. 是否 auto-run python scripts/download_filings.py <ticker> --years 5 --include-prospectus? [yes / no / show-command]`
     - `yes` → Bash shell out, stream 输出。exit 0 重 audit; exit 1 打手动 URL (http://www.cninfo.com.cn) 并 abort。
     - `no` → abort + 手动下载说明。
     - `show-command` → 打印 CLI 并 abort, 不执行。
   - 否则列出: `Found N 年报（<years>）. 招股说明书: present / missing. research/: K files.`
   - 检查 `data/filings/<ticker>/research/`, 空则非阻塞 offer `scripts/download_research.py <ticker> --years 3 --depth-only --max 15`。

3. **PDF 预抽取 cache**: 任一 `_extracted/<pdf-stem>/text.md` 缺失 → 双语 offer `for pdf in data/filings/<ticker>/年报-*.pdf; do python scripts/extract_pdf.py "$pdf"; done`。`skip` → 子 agent 读 raw PDF（慢, 无 page markers）。说明: `text.md` 带 `<!-- page N -->` markers, Read 友好; 图表 / 表格截图 + LLM 描述 在 `images/`, 是业务分析金矿。

4. **Derive output path** `profiles/<ticker>-<YYYY-MM-DD>.md`:
   - 今日文件已存在 → 直接加载（continuation session）。
   - 只有旧日期文件 → `[resume / start-fresh]`; `resume` → 改名为今日 日期（one-file-per-ticker-per-day 不变量）; `start-fresh` → 新建, 旧文件保留。
   - 无文件 → 复制 `docs/value-profile/template-zh.md` 到输出路径, 填 Part 0 header（ticker / exchange / researcher = `git config user.name` / report_date = 今日 / 中英文公司名 派轻量子 agent 一句话查）。

### Step 2 — Progress map

1. **Parse output file**: 对每个 `^### §` 或 `^## §`, 在其 block 内查找 `**置信度:**`。构造 dict `{section_id: status}`, 值域 `{已完成, 进行中, 未做, 已跳过, 需人工}`。

2. **Render bilingual summary**:
   ```
   已完成 4 / 67 节（§0, §1.1, §1.2, §1.6）.
   下一节（next undone）: §1.3 差异化
   [continue / pick-section / exit]
   ```

3. **Route**:
   - `continue` → Step 3 on next-undone。
   - `pick-section` → 询问 id; §Q* 去 Step 4; §4.5 去 Step 5; 其他 Step 3。
   - `exit` → 停。

**`--section` 跳过 Step 2**, 直接进 Step 3。

### Step 3 — Section worker (per section)

#### 3.pre — §3.pre 三大前提 + §3.pre-1 能力圈四问

- §3.pre 三大前提 judgement: 子 agent 在 定性段落前先输出 3 行判定, 依据 §2.2.1。任一假 / 存疑 → §2.2.2 全局降级。
- §3.pre-1 能力圈四问: §1 所有 subsection 必走, 依据 §2.6.1 / §2.6.2。主 agent 复核不合格退回。

两者并列前置条件, 缺一不可。

#### 3a. PDF pre-read

**优先 extracted text cache**:
- `_extracted/<年报-YYYY>/text.md` 存在 → 直接 Read, 用 line-offset + `<!-- page N -->` marker 导航。
- 缺失 → 触发 `scripts/extract_pdf.py` 或 fallback raw PDF。
- 图片 `_extracted/<pdf-stem>/images/` 带 LLM 描述 sidecar, §1-§2 业务分析金矿。

**ToC targeting 起点**:

| section | 年报章节 |
|---|---|
| §1.1 主营 / §1.2 客户 | 第三节 业务概要; 第四节 经营情况 |
| §1.3-§1.5 差异化 / 盈利 / 模式 | 第三节; 招股说明书 业务与技术 |
| §1.6 现金流 | 第五节 财务报告 现金流量表 + 附注 |
| §2 成长空间 | 第四节 行业竞争 / 管理层讨论 |
| §3 护城河 | 第三节 核心竞争力; 第四节 |
| §4 管理与文化 | 第六节 重要事项; 第七节 股东; 第八节 董监高 |
| §5 风险 | 第四节 风险提示 |
| §Q1-§Q12 定量 | 第五节 财务报告（全部）|
| §4.5 排雷 | 第五节 附注（逐项）|
| §3.pre 三前提 | 第十节 审计报告 + 第五节 现金流 + 附注 |

#### 3b. Scoped research dispatch

派 ONE `general-purpose` 子 agent。Prompt 英文（指令语言）, 强制中文输出。必须包含:

- section heading + template 的 本节目标 / 指导问题。
- 解析出的 `<!-- 数据源: ... -->` hint。
- extracted `text.md` 绝对路径（或 raw PDF fallback）+ 3a 给出的 page range。
- ticker, 中文公司名, exchange, report_date。
- 已填好的相邻 section 作为上下文。
- **三大前提** (§2.2) — §1 / §3 / §5 必需, 3 行判定。
- **能力圈四问** (§2.6) — §1 所有 subsection 必需, 4 段独立答。
- **禁用 8 条空话** (§2.11.3)。
- **管理层口径校核** (§2.11.4) — Part 1 §1-§5 必填。
- **5 步护城河分析** (§3 必需): a 分类（大 / 准 / 强 / 省 / 专）+ b 2 项可证伪检验（提价 / 对手 / 切换成本 / ROE 路标 任选二）+ c 跨年定量追溯（毛利率 / 净利率 / ROE 5y, CFO/NI 比值, 带页码）+ d 悲观情景（具体技术 / 偏好 / 监管 / 对手情景, 禁空话）+ e 宽 / 中 / 窄 / 弱 标签。具体数字准绳见 `methodology-tang.md` §C / template §3。
- **管理层 承诺 vs 兑现** (§4 必需): 5 年 forecast vs actual 表, 每行带页码; gap > 10% 连续 ≥ 3 年 → `**置信度:** 低`; 目标突然消失 = 强信号, 必须指出。

#### 3c. Main-agent review

读子 agent 产出。**驳回并重派**若任一:
- 事实缺引用。
- 管理层口径校核 缺失或琐碎复读。
- 填写区 generic, 无 ticker 特定细节。§3 护城河 写茅台 必须引用 茅台镇水源 / 12987 工艺 / 基酒 5 年陈化 / 品牌价格带。
- §1 subsection 四问任一 < 50 字 / 品牌复读 / 结论标签无场景 → §2.6.2 退回。

Acceptable 后写中文终稿, 填 `**引用:**` `**置信度:**` `**管理层口径校核:**`（Part 1 §1-§5）。

#### 3d. 用户确认节点

profile 内容中文; operator 菜单双语:
- `accept` → 保存, 覆盖原内容, 进度标 `已完成`。
- `edit: <text>` → 应用修改, 保存为 `已完成`。
- `defer` → 不保存, 标 `未做`, 回 Step 2。
- `skip` → 填 `N/A — <原因>`, 标 `已跳过`, 保存。
- `research more: <hint>` → 回 3b, 把 hint 附到子 agent prompt。

#### 3e. Save and continue

原子写入（`.tmp` 文件 + `mv` 覆盖）。profile 在任何 save 后必须是合法 markdown。回 Step 2。

### Step 4 — Part 2 bulk mode (§Q1-§Q12)

1. offer `[bulk / by-section]`。
2. `bulk` → ONE 子 agent: Read 每个年报第五节, 逐年抽 营收 / NI / 扣非 NI / 毛利率 / 净利率 / ROE / ROA / CFO / CapEx / 有息负债 / 现金 / 总资产 / 总负债 / 净资产 / 应收 / 存货, 就地填 Part 2 §Q1-§Q12 表, 每 cell `**来源:**` 带 `年报-YYYY.pdf p.NN`。顶行（ROE / 毛利 / 净利率）雪球 F10 联网交叉验证。
3. 呈给用户: `Random-sample 5 cells: given <ROE 2024 = X%>, does 雪球 agree? [all-match / mismatch: <details>]`
4. ≥ 4/5 一致 → 所有 §Q* 标 `已完成`; 否则 不一致行 标 `需人工`。
5. `by-section` → 走标准 Step 3。

### Step 5 — 排雷清单模式 (§4.5)

1. 派 ONE 子 agent: 对 Part 4 §4.5 29 项逐项, 读最新年报 extracted `text.md` 的 资产负债表 / 利润表 / 现金流量表 / 附注。每项回答 `是 / 否 / 不适用 / 需人工` + 1 句证据 + 页码。嵌入 template §4.5 完整 list。

   **财报高危模式 overlay**（§K overlay, 自动 flag）:
   - 商誉 / 净资产 > 20% → 雷区, 未来可能一次性减值
   - 其他应收款 异常（≥ 10% 流动资产, 或单一关联方长年挂账）→ 关联方占款
   - 在建工程 长年不转固 → 挂账操纵折旧
   - CFO / NI < 50% 连续 2 年 → 利润真实性红旗
   - 生物资产 / 农林渔牧 → 造假高危（獐子岛 style）
   - 管理层道德红旗（历史虚假陈述 / 违规处罚 / 股东利益输送）→ 直接大幅降级

   详细 20 项 排雷清单 + 行业 overlay 见 `methodology-tang.md` §K。金融资产 4 分类 / 合同负债口径 等深度财报陷阱见 `docs/value-profile/tang/01-财报阅读深度.md`。

2. 主 agent 复核缺引用, 必要时 re-dispatch。
3. 写 `**发现的红旗 summary:**` 段落（1-2 段）, 聚焦 `是 / 需人工` 项, 说明雷是什么、为何对本 ticker 重要、交叉验证下一步。
4. 用户确认节点 — 仅 `[accept / edit / research more]`。**不 offer `defer` / `skip`**。排雷是强制的。

### Step 6 — 执行摘要合成 (Part 0 估值)

触发条件: ≥ 80% section 标 `已完成`。

**前置检查**: 若 §3.pre 三大前提 任一 假 / 存疑 → abort:
> `❌ 估值前置清单未通过（§<which> = 假/存疑）. 无法进入估值. 请先修复 §3.pre, 或将 Part 0 标 "不可估值 — 仅定性研究"。`

**生意类型检查** (§2.3.1): 判定落在 6 类哪类, "不适用 PE" / "默认回避" → Part 0 标 "定性研究 only", 不输出估值数字。

**7 字段结构化中文输出** (依据 §2.4 / §2.5):

1. **3 年后归母净利润（三档）** — 业务板块拆解（≥ 2 块, 每块 量 × 价 × 净利率）: 乐观 / 中性 / 悲观, 每档附假设。
2. **合理 PE** = 1 / 10y 国债收益率 (~3.5% → ~28x, 典型 25-30)。生意类型 见 §2.3.1 估值矩阵。
3. **合理估值** = 中性 3y NI × 合理 PE（± 10% 带宽）。
4. **买点** = 合理估值 × 50%（高杠杆 × 35%, 必须说明为何高杠杆, 依据 §2.3.1 硬指标）。
5. **卖点** = min(合理估值 × 1.5, 当年 NI × 50PE)。两候选都列, 取较低者。
6. **持仓姿态** (§2.5.2 discrete): 加仓 / 建仓 | 持有不动（收工睡觉）| 分批清仓。
   - **§2.9.1 估值动摇即停手 守则**必须 inline 提示: 跌破买点第二档时, 若 3y NI 预估动摇, 立即停止加仓, 回头重审 下限 → 重算新买点 → 再决定。
7. **Top 3 风险** — 来自 §5 + §4.5, 每条 1-2 句 + 触发条件。

**置信度汇总**: `高` 当 ≥ 60% section 高 AND §3.pre 全真; `中` 混合; `低` 任一块未做 OR 任一前提 存疑。

**Labeling**: 每份 Part 0 末尾必须 `> 本摘要基于 AI 研究 + 用户审阅, 非投资建议. 最近审阅日期 = <today>.`

用户确认 `[accept / edit / research more]` → save。

---

## §4 Operational Boilerplate

### §4.1 Language policy

- **Profile 内容** (`.md`): 中文。填写区、`**引用:**`、`**管理层口径校核:**`、总结段均中文。
- **Operator 输出**（确认节点 / status / errors）: 双语, 中文为主。
- **子 agent prompts**: 英文（指令）, 强制中文输出。
- **Commit messages**: 英文。
- **避混用**: 不写 "SOE 企业 / stakeholder 视角 / bear case 情景", 统一中文化（国企 / 利益相关方 / 悲观情景）。保留缩写仅 ROE / ROIC / DCF / GDP / PE / PB / ESG。
- **CJK-ASCII 空格规则**: 中文与紧邻西文 / 数字不加空格。写 "ROE15%" 不 "ROE 15%"; "营收增长" 不 "营收 增长"; "大/准/强" 不 "大 /准 /强"。

### §4.2 What this skill MUST NOT do

- MUST NOT 重写标 `已完成` 的 section（除非显式 `--force`, v0 不提供）。
- MUST NOT 编造数字或引用。无来源写 `待补充` + 原因。
- MUST NOT 用英文写 profile 内容。
- MUST NOT 没有年报 PDFs 就开干。Step 1.2 offer fetcher 或 abort。
- MUST NOT 跑 `git commit`。用户自 commit。
- MUST NOT 调用 `src/ah_research/`（平台数据层未就绪）。
- MUST NOT 未经 Step 1.2 显式确认就自动下载 PDF。`no` / `show-command` 必须不动文件系统。

### §4.3 Failure modes & recovery

| Failure | Recovery |
|---|---|
| 子 agent 输出缺引用 | 主 agent 把无引用论断改写为 `证据不足, 需人工补充`——**绝不编造** |
| `管理层口径校核` 琐碎话漏网 | Step 3c 应拦住; 作 skill-regression 信号 |
| 年报 PDF 损坏 | 标 `年报-YYYY.pdf（unreadable）`, 用其他来源, 不 abort 该 section |
| 两个 session 并发编辑 profile | 不自动 resolve; warning, 用户手动解决 |
| 子 agent 配额 / 限流 | 窄 page range 重试一次; 仍失败 → `待补充` + 原因, 状态 `进行中` |
| Step 1.2 fetcher 失败 | 回退手动 cninfo URL 并 abort。**绝不生成无 filings 的破 profile** |
| 用户选的 section id 不在 template | 建议最近匹配（`1.3` → `§1.3 差异化`）; 不静默继续 |

### §4.4 Graduation path (Phase 1 落地后)

1. **Step 4 Part 2 bulk** → 子 agent 优先 `ah_research.DataRepository.get_fundamentals(<ticker>, start=<10y>)`, repo 未覆盖回退 PDF。
2. **Step 5 排雷 纯数值项**（应收/营收, 商誉/净资产, 有息负债/CFO）→ DataRepository 算术。
3. **定性 section**（§1-§5, §4.5 定性项）继续 PDF。没有数据源能替代管理层原话。
4. **`scripts/download_filings.py`** 挪进 `src/ah_research/integrations/cninfo_client.py`, 暴露为 repo 方法。

### §4.5 子 agent prompt 模板（Step 3b dispatch 示例）

针对 600519.SH §1.3; 换 section 时替换目标 block / 数据源 hint / page range。

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
