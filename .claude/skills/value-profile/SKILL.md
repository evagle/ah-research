---
name: value-profile
description: Walk a user through filling out a 价值投资 profile for a single A-share / HK stock. Auto-fetches 年报/招股说明书 PDFs via scripts/download_filings.py when missing, reads them as first-hand primary sources, gathers qualitative + quantitative research section-by-section, writes Chinese-language profile to profiles/<ticker>-<date>.md as it goes. Trigger on "/value-profile <ticker>", "研究 股票 <ticker>", or "fill out profile for <ticker>".
---

# Value Profile Skill (Lean Core)

本 skill 是一份给主 Claude Code session 读的指令文档, 结构分三层: **§1 投资哲学（信念/心法）→ §2 规则（从哲学推出的纪律）→ §3 流程（Step 1-6 如何执行）**。本 SKILL.md 是 lean core, 详细规则按需 lazy-load 自 references/。

> **lazy-load 索引**:
> - §1 完整12条原则 + 违反症状: `references/principles.md`
> - §2 完整规则层 + 详细阈值: `references/rules.md`
> - §3 流程详细 sub-step + §4.5 子 agent prompt 模板: `references/operations.md`
> - 5 步护城河详细数字: `references/moat-framework.md`
> - 6 类生意估值矩阵详细公式: `references/valuation.md`
> - 行业附加检查 KPI: `references/industry-overlays.md`
> - 持仓纪律: `references/discipline.md`
> - **每 section 完整指导问题 + 数据源 hint**: `template-guidance.md` (anchor `### §X.Y` 可 grep, subagent dispatch 必引用)

## §0 Skill 运行方式

This skill runs as the **main Claude Code session agent** and orchestrates research via `general-purpose` subagents. It is an instruction document for the main model, not library code. The main agent owns file I/O, user 确认节点, and review; subagents do scoped PDF reads and web research.

**理论血统**: 本 skill 的方法论内核吸收自 `docs/references/tangshufang/methodology.md` 及其深度附录 `docs/references/tangshufang/01-05-*.md`。该 5 份附录是理论来源, 不在 SKILL / template / profile 正文中反复署名。所有 principles / rules / procedures 都已 internalize 为本项目的默认方法, 子 agent 无需再标注"按某某方法"。

---

## §1 投资哲学核心原则 (精华版)

> 完整论证 + 违反症状见 `references/principles.md`。派子 agent 前主 agent 应通读 references 一次 internalize, 之后凭本节精华条目快查。

- **§1.1 股票 = 生意凭证**: 内在价值 = 未来 FCF 折现, 与每日市价无关。市场报价 ≠ 价值更新。详见 references/principles.md §1.1。
- **§1.2 利润三问是承重墙**: ① 利润为真 (CFO ≥ NI, 销售收现率 ≥ 1+VAT) ② 可持续 (10年需求 + 护城河可验证) ③ 不需大投入 (FCF = CFO − 维持性 CapEx)。任一假/存疑 → 25PE 不适用。详见 references/principles.md §1.2。
- **§1.3 商业模式决定估值方法**: 强护城河消费/平台 25PE; 周期/资源 不适用 PE; 银行 PB; 保险 默认回避; 高杠杆 PE 下调 + 折扣加深。详见 references/principles.md §1.3 + references/rules.md §2.3。
- **§1.4 三年后确定性 >> 今天精确**: 选 3 年窗口因为 < 1y = 噪声, > 5y = 超半径。答不出 3y NI 中枢 → 不适用 25PE。详见 references/principles.md §1.4。
- **§1.5 安全边际 = 错误容差**: 50% 折扣不是占便宜, 是给估算错误留空间。判错概率高 → 提高折扣不降低门槛。详见 references/principles.md §1.5。
- **§1.6 能力圈四问 全过 = 看得懂**: ① 卖什么 ② 客户为何选 ③ 为何对手没抢走 ④ 巨头进场抗打击。任一空话 = 不下注。详见 references/principles.md §1.6。
- **§1.7 市场波动 ≠ 信息**: 默认动作"呆坐不动"。涨不是卖理由, 跌不是买理由; 估值进/出区间才是。详见 references/principles.md §1.7。
- **§1.8 耐心是资产**: 不主动留现金; 但也不为仓位急投。子弹池 ≠ 择时工具。详见 references/principles.md §1.8。
- **§1.9 认错 > 坚持**: 跌破买点 + 新信息动摇 3y NI → 立即停止加仓, 重审下限 → 重算买点 → 再决定。详见 references/principles.md §1.9。
- **§1.10 集中 > 分散**: 4-6 家目标, 上限 8 家; 单仓 ≤ 40% (极端 50%); 同行业 ≤ 2 家。详见 references/principles.md §1.10。
- **§1.11 真相在附注**: 年报正文略读, 附注必须逐行读 (其他应收/关联交易/对外担保/商誉测试/金融资产分类)。详见 references/principles.md §1.11。
- **§1.12 好生意 > 好管理层**: 三好顺序不可换。一流生意 + 三流管理层 通常 > 三流生意 + 一流管理层。详见 references/principles.md §1.12。

---

## §2 规则层 (核心约束)

> 详细阈值 + 5 步护城河具体数字 + 29 项排雷阈值 + 6 类生意估值数字见 `references/rules.md`。本节只留触发条件 + 一票否决 + 6 类生意估值矩阵速查。

### §2.1-§2.2 三大前提 (估值前置 gate)

- **§2.1.2 数字必带引用**: 每数字 `(年报-YYYY.pdf p.NN)` 或 URL, 不带 = 未核实。找不到写 `待补充 — 年报未披露`, 绝不编造。
- **§2.2 三大前提 三项判定** (子 agent 开场白必走): ① 审计标准无保留 ② 近 3y CFO ≥ NI 累计 + 销售收现率 ≈ 1+VAT ±5% ③ 近 5y ROE ≥ 15% + 毛利稳 ±5pp + 扣非/NI ≥ 0.85。任一 假/存疑 → **profile 全局降级**, Step 6 abort。详见 references/rules.md §2.2。
- **§2.2.4 auto-mode 深调查**: 主 agent review 发现证据薄弱 → 默认动作扩 scope 重派 subagent (多读年报年份 / 增查研报 / 展开附注 / web search / 查监管披露)。连续 2 次仍无 → `**置信度:** 中/低` + `**需人工跟进:**` 备注后继续。详见 references/rules.md §2.2.4。

### §2.3 6 类生意估值矩阵 (套用前先判类型)

| 生意类型 | 估值方法 | 买点折扣 |
|---|---|---|
| 强护城河消费/平台互联网龙头 | 25PE（顶级30）| 50% |
| 周期股/资源/化工/航运/钢铁/水泥 | 不适用 PE | — |
| 高成长股（年化 > 25%）| 25PE 上限不破 | 50% |
| 金融 — 银行 | 改用 PB（1.0-1.15× 真实净资产）| 35% |
| 金融 — 保险 | 默认回避 | — |
| 高杠杆（地产/部分电力/开发商）| PE 下调到 8-12 | 35% |
| 公用事业（水电/高速/港口）| DCF 简化版 | 股息率 > rf × 1.3 |

> 同时符合多类 (如 高杠杆 + 周期) → 取最严档。"不适用 PE" / "默认回避" → Step 6 不输出估值数字, Part 0 标 "定性研究 only"。详细公式见 references/rules.md §2.3 + references/valuation.md §3。

### §2.5 买卖点公式 (硬规则)

- **买点** = 3y 合理估值 × 50%（高杠杆 × 35%）
- **卖点** = min(3y 合理估值 × 150%, 当年 NI × 50PE)
- **持仓姿态** discrete: < 买点 → 加仓 (分批 ≤ 1/3); 买点 ≤ 当前 ≤ 卖点 → 持有不动; > 卖点 → 分批清仓。详见 references/rules.md §2.5。

### §2.6 能力圈四问 (§1 末节 synthesis)

§1.8 = §1.1-§1.7 拆解之后的 synthesis (非前置 gate), 4 段独立答, 每问 ≥ 50 字 + ticker 特定证据。任一品牌复读/结论标签无场景 → §1.8 标 `低` + profile 整体降级 "观察档案, 不下注", 不进 Step 6。详见 references/rules.md §2.6。

### §2.11 年报阅读纪律

- **§2.11.0 优先最新年报**: 最新年报 (审计) > 半年报 > 季报 > 旧年报 (仅跨年对比)。
- **§2.11.3 禁用 8 条空话**: "强大品牌/技术领先/行业龙头/管理优秀/市场广阔/核心竞争力突出/护城河宽广/成长空间巨大" 无具体佐证一律退回。
- **§2.11.4 管理层口径校核**: Part 1 §1-§5 必填, 对比年报 vs 研报 vs 财新 vs 价盘 vs 监管披露。"年报说 X, 我们同意 X" = 不合格。
- **§2.11.5 研报只取事实, 不取观点**: 评级/目标价/未来 forecast 全删, 只保留 A 类具体事件 + B 类年报拿不到的运营明细 + C 类第三方引述。详见 references/rules.md §2.11.5。
- **§2.11.6 抓核心矛盾, 不给笼统总数**: 数据拆到能体现矛盾的颗粒度 (分产品 / 渠道 / 地区 / 量价 / 关联 vs 非关联)。
- **§2.11.7 关联交易 ≠ 真实议价权**: 分析议价权先把关联方剥离, 再判非关联部分。关联占比 > 20% 需 flag。

### §2.12 好生意 > 好管理层 (一票否决)

- **§2.12.1 §1 结论字段**: §1 收尾 `好生意: 是 / 否 / 存疑`; "否" → Part 0 标 "定性研究 only"。
- **§2.12.2 §4 风险一票否决**: 即使 §1 = 是, §4 出现 道德风险 / 大股东占款 / 系统性画大饼 (连续 3 年指引偏 > 20%) / 虚假陈述处罚 → 直接淘汰, profile 终止。

---

## §3 分析流程 (Step 1-6 大纲)

> 详细 sub-procedure (3.pre / 3a / 3b / 3c / 3d / 3e / Step 4 bulk / Step 5 redflag delegate / Step 6 估值合成 7字段) 见 `references/operations.md`。本节只留 step 名字 + 入参/出参 + 5-10 行核心操作。

### Invocation

- **Primary:** `/value-profile <ticker>` — 验证正则 `^[0-9]{4,6}\.(SH|SZ|HK)$`。**默认 auto mode**。
- **`--interactive`** — 切到 interactive mode。
- **`--auto`** — 显式 auto mode (与 default 等价)。
- **`--section <id>`** — 跳到指定 section, 跳过 Step 2。
- **`--resume`** — 强制加载最近一个 `profiles/<ticker>-*.md`。

### 两种运行模式

**Auto mode (default)**: 一次性跑完 Part 0 → Part 5 + §Q + §4.5, 中途不停。仅 genuine 故障停: Step 1 fetcher 失败 / §3.pre 假 / §2.12.2 一票否决 / §1.4 resume-vs-fresh fork。Section-level 证据薄弱 → 扩 scope 重派 subagent (≤ 2 次), 仍薄 → `**置信度:** 中` + `**需人工跟进:**` 备注继续, 不 abort。

**Interactive mode (`--interactive`)**: 每 section 完后印 `[accept / edit / defer / skip / research more]`, Step 2 印 `[continue / pick-section / exit]`, Step 4/5/6 需 confirm。

两种模式的 section-level 质量要求一致——区别只在 "是否让用户介入推进节奏"。

### Step 1 — Bootstrap + filings audit

1. Validate ticker (regex 失败 abort)。
2. Audit `data/filings/<ticker>/`: 年报 PDF < 2 份 → offer fetcher `[yes / no / show-command]`。
3. PDF 预抽取 cache: `_extracted/<pdf-stem>/text.md` 缺失 → offer `scripts/extract_pdf.py`。
4. Derive output path `profiles/<ticker>-<YYYY-MM-DD>.md`: 今日已存在加载; 旧日期 `[resume / start-fresh]`; 无文件复制 template + **强制 5 项 cleanup** (改 title / 删 HTML comment block / 删阅读姿态段 / 删 heading instruction parenthetical / 跑 grep cleanup gate, 任一残留 abort 重做)。

> 详细子步骤 (含 cleanup grep pattern) 见 `references/operations.md` Step 1。

### Step 2 — Progress map

1. Parse output file 各 `^### §` block 的 `**置信度:**` → dict `{section_id: status}`。
2. Render bilingual summary (`已完成 N / 67 节. 下一节: §X.Y`)。
3. Route by mode: auto → 直接 Step 3 next-undone; interactive → 印 `[continue / pick-section / exit]`。

> `--section` 跳过 Step 2 直接进 Step 3。

### Step 3 — Section worker (per section)

- **3.pre**: §1 / §3 / §5 前置 gate — 子 agent 先输 3 行三大前提判定。任一假 → 全局降级。
- **3a PDF pre-read**: 优先 `_extracted/<年报-YYYY>/text.md` + `<!-- page N -->` marker 导航; ToC targeting 表见 references/operations.md。
- **3b dispatch**: ONE `general-purpose` 子 agent, prompt 英文/输出中文。**主 agent 必须在 prompt 里 inline 该 section 的 `template-guidance.md §X.Y` 完整内容** (用 grep + Read offset/limit 取该 anchor 段, ~30-80 行), 不依赖 subagent 自己去读 (subagent context 越精简越好)。Prompt 必含: section heading + 从 guidance 抽出的本节目标/指导问题/数据源 hint + PDF 路径 + 已填邻 section 上下文 + 三大前提 + 能力圈四问 (§1) + 禁 8 条空话 + 管理层口径校核 (Part 1 §1-§5) + 5 步护城河 (§3) + delegate management-analysis (§4)。
- **3c review**: 缺引用 / 校核琐碎 / 论断 generic / §1.8 < 50字 → 驳回。Auto mode 重派需扩 scope (多年/研报/附注/web/招股), ≤ 2 次, 仍薄弱 → `中` + `需人工跟进:`。
- **3d save by mode**: auto 隐式 accept; interactive 印菜单 `[accept / edit / defer / skip / research more]`。
- **3e**: 原子写入 (`.tmp` + `mv`), 回 Step 2。

> 详细子步骤 (子 agent prompt 必含项 / review 驳回标准 / 重派扩 scope 6 种方式) 见 `references/operations.md` Step 3。

### Step 4 — Part 2 bulk mode (§Q1-§Q12)

1. Auto mode 直接走 bulk; interactive offer `[bulk / by-section]`。
2. ONE 子 agent: Read 各年报第五节, 逐年抽 16 项财务指标, 就地填 §Q1-§Q12 表, 每 cell 带 `年报-YYYY.pdf p.NN`。
3. 子 agent 自跑 random-sample 5 cells 雪球校核; ≥ 4/5 一致 → 标 `已完成`; 否则不一致行标 `需人工`。

> 详细见 `references/operations.md` Step 4。

### Step 5 — 排雷清单 (§4.5)

**Delegate 到 `financial-redflag-scan` 子 skill**, 传 `--target-profile <path> --section §4.5`。Fallback (子 skill 不可用): 派 ONE 子 agent 扫 29 项 + 6 项高危, 写 `**发现的风险 summary:**` 1-2 段。详见 `.claude/skills/financial-redflag-scan/SKILL.md` 或 `references/operations.md` Step 5。

### Step 6 — 执行摘要合成 (Part 0 估值)

触发: ≥ 80% section `已完成`。

**前置检查**: §3.pre 任一假 → abort "估值前置清单未通过"。生意类型 "不适用 PE" / "默认回避" → Part 0 "定性研究 only"。

**7 字段输出** (依据 §2.4 / §2.5):
1. 3y 归母净利润三档 (≥ 2 板块 量×价×净利率)
2. 合理 PE = 1 / 10y 国债收益率 (~25-30)
3. 合理估值 = 中性 3y NI × 合理 PE (±10%)
4. 买点 = 合理估值 × 50% (高杠杆 × 35%)
5. 卖点 = min(合理估值 × 1.5, 当年 NI × 50PE)
6. 持仓姿态 (discrete) + §2.9.1 估值动摇守则 inline
7. Top 3 风险 (来自 §5 + §4.5)

**置信度汇总**: 高 ≥ 60% section 高 + §3.pre 全真; 中 混合; 低 任一未做或前提存疑。

> 详细 7 字段 spec 见 `references/operations.md` Step 6。

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
| 子 agent 输出缺引用 | **Auto**: 重派 subagent 扩大 scope (最多 2 次, §2.2.4); 仍缺 → 标 `**置信度:** 中` + `**需人工跟进:** <具体什么缺>`, 继续下一节不 abort。**Interactive**: 主 agent 把无引用论断改写为 `证据不足, 需人工补充`, 等用户下一步。**两种模式都绝不编造** |
| `管理层口径校核` 琐碎话漏网 | Step 3c 应拦住; 作 skill-regression 信号 |
| 年报 PDF 损坏 | 标 `年报-YYYY.pdf（unreadable）`, 用其他来源, 不 abort 该 section |
| 两个 session 并发编辑 profile | 不自动 resolve; warning, 用户手动解决 |
| 子 agent 配额/限流 | 窄 page range 重试一次; 仍失败 → `待补充` + 原因, 状态 `进行中` |
| Step 1.2 fetcher 失败 | 回退手动 cninfo URL 并 abort。**绝不生成无 filings 的破 profile** |
| 用户选的 section id 不在 template | 建议最近匹配（`1.3` → `§1.3 差异化`）; 不静默继续 |

### §4.4 Graduation path (Phase 1 落地后)

1. Step 4 Part 2 bulk → 子 agent 优先 `ah_research.DataRepository.get_fundamentals(<ticker>, start=<10y>)`, repo 未覆盖回退 PDF。
2. Step 5 排雷 纯数值项（应收/营收, 商誉/净资产, 有息负债/CFO）→ DataRepository 算术。
3. 定性 section（§1-§5, §4.5 定性项）继续 PDF。没有数据源能替代管理层原话。
4. `scripts/download_filings.py` 挪进 `src/ah_research/integrations/cninfo_client.py`, 暴露为 repo 方法。

### §4.6 Profile 输出风格 — 给人读的

Profile 读者是人, 不是 AI agent。Step 3c 主 agent review 必拦回以下 regression 模式 → 驳回 subagent 重派 (扩 scope, 不打补丁):

- **浓缩**: Part 0 bullet 分层 (状态行 + 3-5 sub-bullet 1 句); 1-2 分钟读完 Part 0。
- **禁 AI 自引用**: 禁句尾 `(§x.y)`——事实自证。引用集中节末 `**引用:**` 字段, 不 inline `XXX (年报-YYYY.md p.NN)`。
- **禁 wall-of-text**: 用 markdown bullet, 每段 3-5 句; 子标题粗体分块。
- **英文白名单原则**: 仅保留 ROE/ROIC/ROA/DCF/PE/PB/PS/PEG/EV/EBITDA/CAGR/YoY/QoQ/TTM/MAU/DAU/ARPU/LTV/CAC/CR5/CR10/GMV/GDP/ESG/IPO/H 股/A 股/SKU/KPI/OKR/ABT; 白名单外一律中文化。
- **禁自造状态词 + 禁 AI 直译**: schema 唯一 source 在 template-zh.md (清洁 → 无触发/合规; healthy → 财务稳健; red flag → 风险信号)。
- **禁翻译腔**: 靠什么生产 → 怎么生产; 在...的情况下 → 拆短句; 通过...的方式 → 直接说动作。
- **禁 AI-runtime meta**: Profile 不含 "完成状态 / Auto mode 完成时间 / disclaimer / 置信度分布统计"。Telemetry 走 console。
- **跟踪项视觉**: `⚠️ **跟踪 N**:` / `⚠️ **注意**:`。Part 0 heading 唯一 `### 执行摘要`。

> 完整 §4.6.1-§4.6.9 (含中英文对照表 + AI-style awkward 句式表 + 状态词替换表) 见 `references/operations.md` §4.6。

### §4.7 缓存纪律

- Read 用 offset/limit (≥ 200 行不全 Read)
- 大任务开新 session, 不续 200K+ context
- Subagent prompt ≤ 1500 tok
- Lazy-load references, 不主动全 Read

> §4.5 子 agent prompt 模板示例见 `references/operations.md` 末尾。
