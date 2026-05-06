# §3 流程 + §4.5 + §4.7 操作细节 (完整版)

本文件是 `SKILL.md` §3 Step 1-6 / §4.5 子 agent prompt 模板的展开版。lean SKILL 留 step 名字 + 入参/出参 + 5-10 行核心操作, 详细 sub-procedure 在此。

---

## §3.pre — 三大前提 (§1 / §3 / §5 前置 gate)

- **§3.pre 三大前提 judgement**: 子 agent 在 §1 / §3 / §5 定性段落前先输出3行判定, 依据 §2.2.1 (见 `references/rules.md`)。审计/CFO/ROE 属纯财务数据检查, 与业务理解无关, 所以可做前置 gate。任一假/存疑 → §2.2.2 全局降级。

**§1.8 能力圈四问 ≠ 前置 gate**: 四问是 **§1.1-§1.7 拆解完成后**的 synthesis 章节（见 §2.6）, 不是 §1.1 开场前的 gate。子 agent 在 §1.1-§1.7 全部填完之后, 基于已建立的业务理解综合回答四问。理由: 能力圈判定需要对业务先有认知, 才能给出实质性答案; 前置 gate 版本 = "没读就下结论", 与价值投资"看懂再下注"精神反着走。

---

## Step 1 — Bootstrap + filings audit (详细子步骤)

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

3. **PDF 预抽取 cache**: 任一 `_extracted/<pdf-stem>/text.md` 缺失 → 双语 offer `for pdf in data/filings/<ticker>/年报-*.pdf; do python scripts/extract_pdf.py "$pdf"; done`。`skip` → 子 agent 读 raw PDF（慢, 无 page markers）。说明: `text.md` 带 `<!-- page N -->` markers, Read 友好; 图表/表格截图 + LLM 描述 在 `images/`, 是业务分析金矿。

4. **Derive output path** `profiles/<ticker>-<YYYY-MM-DD>.md`:
   - 今日文件已存在 → 直接加载（continuation session）。
   - 只有旧日期文件 → `[resume / start-fresh]`; `resume` → 改名为今日 日期（one-file-per-ticker-per-day 不变量）; `start-fresh` → 新建, 旧文件保留。
   - 无文件 → 复制 `.claude/skills/value-profile/template-zh.md` 到输出路径, 然后做**强制3项 cleanup**（template 含 meta 文档, 必须在开跑前剥离, 否则最终 profile 会残留不属于 ticker-specific 内容的模板说明）:
     1. **Title**: 第一行 `# 价值投资个股研究 Profile — Template` → `# 价值投资个股研究 Profile — <中文公司名> (<ticker>) <report_date>`（例: `# 价值投资个股研究 Profile — 贵州茅台 (600519.SH) 2026-05-01`）。
     2. **删 HTML comment block**: template 开头 `<!-- 模板版本 v2 ... Skill 在调用时会复制本模板到 profiles/<ticker>-<date>.md, 然后逐节填写。 -->` 整段删除。
     3. **删 "阅读姿态/分析框架" 段**: 从 `## 阅读姿态/分析框架（读前必读）` 到随后的 `---` separator 整段删除（指向 SKILL/references 的阅读指引, 属 skill-internal doc, 不属 profile 内容）。
     4. **删 heading 里的 template-instruction parenthetical**: 扫 `^#+` 所有 heading, 删除尾部给填写者的指令性括号 annotation。典型要删的 pattern: `（本节最后填写）` / `（PRIMARY — 先填）` / `（OPTIONAL — 后填）` / `（填入...）` / `（待填）` / `（SECONDARY — 定量补充）` 等。heading 本身 title 留下, 只剥离尾部给 filler 的 meta 指示。Ticker-specific 的 title 修饰（如"§3 护城河分析"后面的结论性标签）不动。

     然后填 Part 0 header（ticker / exchange / researcher = `git config user.name` / report_date = 今日; 中英文公司名 派轻量子 agent 一句话查）。Auto / interactive 两种模式都必须做此 cleanup, 不可跳过。

     **5. Cleanup 验证 gate** (强制, abort 条件): cleanup 完成后 grep 验证 4 项, 任一残留 → abort 并 re-cleanup:
     ```
     grep -nE "Profile — Template|## 阅读姿态/分析框架|本模板是 \*\*输出结构|（PRIMARY|（SECONDARY|（OPTIONAL|（本节最后填写|（待填|（填入" profiles/<ticker>-<date>.md
     ```
     若任一 match → cleanup 未做完, 必须重做。Resume / continuation session 启动时也要跑此 gate, 因旧 profile 可能在 cleanup 引入前创建。

---

## Step 2 — Progress map (详细子步骤)

1. **Parse output file**: 对每个 `^### §` 或 `^## §`, 在其 block 内查找 `**置信度:**`。构造 dict `{section_id: status}`, 值域 `{已完成, 进行中, 未做, 已跳过, 需人工}`。

2. **Render bilingual summary**（两种模式都印, 方便 logging / 用户 observe 进度）:
   ```
   已完成 4 / 67 节（§0, §1.1, §1.2, §1.6）.
   下一节（next undone）: §1.3 差异化
   ```

3. **Route by mode**:
   - **Auto mode (default)**: **直接进 Step 3 on next-undone, 不等输入**。Section 完成后回 Step 2 重新印进度表 + 跳下一节, 循环直到: 所有 undone section 填完 / 触发 abort 条件（§3.pre 假、§4 风险 一票否决、Step 1 fetcher 失败）/ 达到 Step 6 估值触发条件（≥ 80% 已完成）。
   - **Interactive mode (`--interactive`)**: 印 `[continue / pick-section / exit]` 菜单, 等用户:
     - `continue` → Step 3 on next-undone。
     - `pick-section` → 询问 id; §Q* 去 Step 4; §4.5 去 Step 5; 其他 Step 3。
     - `exit` → 停。

**`--section` 跳过 Step 2**（两种模式都是）, 直接进 Step 3。

---

## Step 3 — Section worker (详细子步骤)

### 3a. PDF pre-read

**优先 extracted text cache**:
- `_extracted/<年报-YYYY>/text.md` 存在 → 直接 Read, 用 line-offset + `<!-- page N -->` marker 导航。
- 缺失 → 触发 `scripts/extract_pdf.py` 或 兜底 raw PDF。
- 图片 `_extracted/<pdf-stem>/images/` 带 LLM 描述 sidecar, §1-§2 业务分析金矿。

**ToC targeting 起点**:

| section | 年报章节 |
|---|---|
| §1.1 主营 / §1.2 客户 | 第三节 业务概要; 第四节 经营情况 |
| §1.3-§1.5 差异化/盈利/模式 | 第三节; 招股说明书 业务与技术 |
| §1.6 现金流 | 第五节 财务报告 现金流量表 + 附注 |
| §2 成长空间 | 第四节 行业竞争/管理层讨论 |
| §3 护城河 | 第三节 核心竞争力; 第四节 |
| §4 管理与文化 | 第六节 重要事项; 第七节 股东; 第八节 董监高 |
| §5 风险 | 第四节 风险提示 |
| §Q1-§Q12 定量 | 第五节 财务报告（全部）|
| §4.5 排雷 | 第五节 附注（逐项）|
| §3.pre 三前提 | 第十节 审计报告 + 第五节 现金流 + 附注 |

### 3b. Scoped research dispatch

派 ONE `general-purpose` 子 agent。Prompt 英文（指令语言）, 强制中文输出。必须包含:

- section heading + template 的 本节目标/指导问题。
- 解析出的 `<!-- 数据源: ... -->` hint。
- extracted `text.md` 绝对路径（或 raw PDF 兜底）+ 3a 给出的 page range。
- ticker, 中文公司名, exchange, report_date。
- 已填好的相邻 section 作为上下文。
- **三大前提** (§2.2) — §1 / §3 / §5 必需, 3行判定。
- **能力圈四问** (§2.6) — §1 所有 subsection 必需, 4段独立答。
- **禁用8条空话** (§2.11.3)。
- **管理层口径校核** (§2.11.4) — Part 1 §1-§5 必填。
- **5步护城河分析** (§3 必需): a 分类（大/准 / 强/省 / 专）+ b 2项可证伪检验（提价/对手/切换成本 / ROE 路标 任选二）+ c 跨年定量追溯（毛利率/净利率 / ROE 5y, CFO/NI 比值, 带页码）+ d 悲观情景（具体技术/偏好/监管/对手情景, 禁空话）+ e 宽/中 / 窄/弱 标签。具体数字准绳见 `references/moat-framework.md` / template §3。
- **§4 管理层分析** → **delegate 到 `management-analysis` 子 skill**, 传参 `--target-profile <path> --section §4`; 详细流程（承诺 vs 兑现5年表/董事长5年评估/股东回报/道德风险 一票否决）见 `.claude/skills/management-analysis/SKILL.md` §2-§3。Fallback (子 skill 不可用): 5年 forecast vs actual 表每行带页码, gap > 10% 连续 ≥ 3年 → `**置信度:** 低`, 目标突然消失 = 强信号必须指出, 言行一致检验 ≥ 2事件。具体执行见 management-analysis 子 skill。

### 3c. Main-agent review

读子 agent 产出。**驳回并重派**若任一:
- 事实缺引用。
- 管理层口径校核 缺失或琐碎复读。
- 填写区 generic, 无 ticker 特定细节。§3 护城河 写茅台 必须引用 茅台镇水源 / 12987 工艺/基酒5年陈化/品牌价格带。
- §1.8 四问任一 < 50字/品牌复读/结论标签无场景 → §2.6.2 退回; 退回的是 §1.8 本节, 不动 §1.1-§1.7。

**Auto mode 重派方式 (§2.2.4 深调查)**: 不简单重跑同 prompt, 必须**扩大 scope**——指示子 agent (a) 多读 1-2年年报横向追溯趋势 / (b) 增查研报 B 类运营明细 / (c) 展开附注项具体条款 / (d) web search 行业同行数据 / (e) 读招股说明书对应章节 / (f) 查监管披露 或 交易所问询函。**重派最多2次**; 仍薄弱 → Acceptable 放宽为 `**置信度:** 中` + 填 `**需人工跟进:** <具体缺什么>` 备注, 继续进下一节, 不 abort。Interactive mode 下用户可在 3d 主动 `research more: <hint>` 给方向, 主 agent 不强制自动加深。

Acceptable 后写中文终稿, 填 `**引用:**` `**置信度:**` `**管理层口径校核:**`（Part 1 §1-§5）。

### 3d. Save by mode

- **Auto mode (default)**: 3c review 通过 → **隐式 accept**, 直接原子写入 profile（`**置信度:**` 由 3c 写好）, 回 Step 2 找下一节, **不印 menu 不等用户**。3c 连续2次深调查仍不达标 → 隐式 accept 为 `**置信度:** 中` + `**需人工跟进:**` 备注, 继续。
- **Interactive mode (`--interactive`)**: 印 profile 内容中文 + 双语菜单:
  - `accept` → 保存, 覆盖原内容, 进度标 `已完成`。
  - `edit: <text>` → 应用修改, 保存为 `已完成`。
  - `defer` → 不保存, 标 `未做`, 回 Step 2。
  - `skip` → 填 `N/A — <原因>`, 标 `已跳过`, 保存。
  - `research more: <hint>` → 回 3b, 把 hint 附到子 agent prompt。

### 3e. Save and continue

原子写入（`.tmp` 文件 + `mv` 覆盖）。profile 在任何 save 后必须是合法 markdown。回 Step 2。

---

## Step 4 — Part 2 bulk mode (§Q1-§Q12) (详细子步骤)

1. **Auto mode**: 默认直接走 `bulk`, 不 offer。**Interactive mode**: offer `[bulk / by-section]` 等用户选。
2. `bulk` → ONE 子 agent: Read 每个年报第五节, 逐年抽 营收 / NI / 扣非 NI / 毛利率/净利率 / ROE / ROA / CFO / CapEx / 有息负债/现金/总资产/总负债/净资产/应收/存货, 就地填 Part 2 §Q1-§Q12 表, 每 cell `**来源:**` 带 `年报-YYYY.pdf p.NN`。顶行（ROE / 毛利/净利率）雪球 F10 联网交叉验证。
3. **Auto mode**: 子 agent 在 prompt 里明确要求它自己执行 random-sample 5 cells 雪球校核 + 汇报结果, 主 agent 收到后自动按 ≥ 4/5 一致 规则判决（≥ 4/5 → 所有 §Q* 标 `已完成`; 否则 不一致行 标 `需人工`）, 不问用户。**Interactive mode**: 呈给用户 `Random-sample 5 cells: given <ROE 2024 = X%>, does 雪球 agree? [all-match / mismatch: <details>]`, 用户回复后主 agent 按规则判决。
4. ≥ 4/5 一致 → 所有 §Q* 标 `已完成`; 否则 不一致行 标 `需人工`。
5. `by-section` (interactive only) → 走标准 Step 3。

---

## Step 5 — 排雷清单模式 (§4.5) (详细子步骤)

**Delegate 到 `financial-redflag-scan` 子 skill**, 传参 `--target-profile <path> --section §4.5`; 详细流程（29项清单 + 6项高危 附加检查 + 三表勾稽4条 + summary + 强制 `[accept / edit / research more]` 不 `defer / skip`）见 `.claude/skills/financial-redflag-scan/SKILL.md` §2-§3。

**Fallback（子 skill 不可用时, 主 skill 跑简化版）**:

1. 派 ONE 子 agent 对 Part 4 §4.5 29项逐项扫, 每项 `是 / 否 / 不适用 / 需人工` + 证据 + 页码; 6项高危 附加检查 显式 flag（商誉/净资产>20% | 其他应收≥10%流动资产 | 在建工程长年不转固 | CFO/NI<50%连续2年 | 生物资产/农林渔牧 | 管理层道德风险一票否决）。详细阈值/三表勾稽/造假模式 见 `.claude/skills/financial-redflag-scan/references/fraud-library.md` §1-§4; 附注12项 见 `.claude/skills/read-filing/references/statement-reading.md` §3。
2. 主 agent 复核缺引用 → re-dispatch（§2.2.4 深调查）。写 `**发现的风险 summary:**` 1-2段。
3. **Auto mode**: 3c 通过即保存, 不 confirm。**Interactive mode**: 用户确认 `[accept / edit / research more]`。

---

## Step 6 — 执行摘要合成 (Part 0 估值) (详细子步骤)

触发条件: ≥ 80% section 标 `已完成`。

**前置检查**: 若 §3.pre 三大前提 任一 假/存疑 → abort:
> `❌ 估值前置清单未通过（§<which> = 假/存疑）. 无法进入估值. 请先修复 §3.pre, 或将 Part 0 标 "不可估值 — 仅定性研究"。`

**生意类型检查** (§2.3.1): 判定落在6类哪类, "不适用 PE" / "默认回避" → Part 0 标 "定性研究 only", 不输出估值数字。

**7字段结构化中文输出** (依据 §2.4 / §2.5):

1. **3年后归母净利润（三档）** — 业务板块拆解（≥ 2块, 每块 量 × 价 × 净利率）: 乐观/中性/悲观, 每档附假设。
2. **合理 PE** = 1 / 10y 国债收益率 (~3.5% → ~28x, 典型25-30)。生意类型 见 §2.3.1 估值矩阵。
3. **合理估值** = 中性3y NI × 合理 PE（± 10% 带宽）。
4. **买点** = 合理估值 × 50%（高杠杆 × 35%, 必须说明为何高杠杆, 依据 §2.3.1 硬指标）。
5. **卖点** = min(合理估值 × 1.5, 当年 NI × 50PE)。两候选都列, 取较低者。
6. **持仓姿态** (§2.5.2 discrete): 加仓/建仓 | 持有不动（收工睡觉）| 分批清仓。
   - **§2.9.1 估值动摇即停手 守则**必须 inline 提示: 跌破买点第二档时, 若3y NI 预估动摇, 立即停止加仓, 回头重审 下限 → 重算新买点 → 再决定。
7. **Top 3风险** — 来自 §5 + §4.5, 每条1-2句 + 触发条件。

**置信度汇总**: `高` 当 ≥ 60% section 高 AND §3.pre 全真; `中` 混合; `低` 任一块未做 OR 任一前提 存疑。

- **Auto mode**: 3c review 通过（7字段完整、数字源头可追溯、§3.pre 全真或已 mark 降级）即 save 并 **skill 自行终止**。打 final summary: `✅ Profile 完成. N/67 sections 已完成, 估值 Part 0 已合成. 路径: profiles/<ticker>-<date>.md`。
- **Interactive mode**: 印摘要 + 双语菜单 `[accept / edit / research more]`, 等用户确认 → save。

---

## §4.6 Profile 输出风格 — 给人读的, 不是给 AI 读的

Profile 的读者是人 (研究员 / 投资人 / 审阅人), 不是另一个 AI agent。写法必须服务于人类 scan + 理解。

- **§4.6.1 浓缩原则**: 核心是"内容少但每句精华, 信息量高"。Part 0 执行摘要用 **bullet 分层**（每项"状态行" + 3-5 个 sub-bullet 核心证据, 每个 sub-bullet 1 句浓缩）, **不必压缩到 1 行**。目标: 读完 Part 0 约 1-2 分钟能抓到所有结论 + 跟踪项。细节留 Part 1-5 / §Q / §4.5。
- **§4.6.2 禁用 AI 自引用 + 内嵌文献引用 (全 profile 非仅 Part 0)**: narrative body 禁两类内嵌 refs:

  **(a) 禁 `(§x.y)` 自引用**: 例 "毛利率 92% (§1.1)"——事实自证, 不需指向源 section。允许的 § 引用形式: `**引用:**` 结构字段 / 开头为 "依据 §2.2 三大前提..." 的规则指向句 / "SKILL §2.9 守则" 这类 rule pointer。禁: 句尾裸括号 section id 如 `XXX (§1.5)`。

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
  - 宏观 / 合规: GDP / ESG / IPO / H 股 / A 股 / SKU
  - 管理 / 指标术语: KPI / OKR / ABT

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

---

## §4.5 子 agent prompt 模板（Step 3b dispatch 示例）

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
