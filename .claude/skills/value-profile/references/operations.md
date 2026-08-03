# §3流程与操作细节

本文件是`SKILL.md` §3 Step 1-6的展开版。正文写作统一遵守
`profile-writing-style.md`，最终读者投影统一遵守`reader-rendering.md`；
本文件不复制两者的规则，也不提供会绕过`product-analysis`的通用§1.3 prompt。

---

## §3.pre — 三大前提 (§1 / §3 / §5 前置 gate)

- **§3.pre 三大前提 judgement**: 子 agent 在 §1 / §3 / §5 定性段落前先输出3行判定, 依据 §2.2.1 (见 `references/rules.md`)。审计/CFO/ROE 属纯财务数据检查, 与业务理解无关, 所以可做前置 gate。三大前提为假或存疑只阻断数字估值；定性研究、产品分析和不依赖该前提的判断继续完成。

**§1.8 能力圈四问 ≠ 前置 gate**: 四问是 **§1.1-§1.7 拆解完成后**的 synthesis 章节（见 §2.6）, 不是 §1.1 开场前的 gate。子 agent 在 §1.1-§1.7 全部填完之后, 基于已建立的业务理解综合回答四问。理由: 能力圈判定需要对业务先有认知, 才能给出实质性答案; 前置 gate 版本 = "没读就下结论", 与价值投资"看懂再下注"精神反着走。

---

## Step 1 — Bootstrap + filings audit (详细子步骤)

1. **Validate ticker** against `^[0-9]{4,6}\.(SH|SZ|HK)$`. 失败双语报错并 abort:
   > `❌ 无效 ticker: <input>. 期望格式 <code>.<exchange>（例 600519.SH, 0700.HK）. / Invalid ticker.`

2. **Audit `data/filings/<ticker>/`**:
   - 若目录缺失 OR 匹配 `年报-*.pdf` 的文件 < **2** 份:
     - Auto mode缺少年报时直接执行下载，不显示`yes/no/show-command`菜单。exit 0后重新audit；失败时记录具体错误并继续同功能官方fallback，只有适用路线terminal后才按state mapping处理受影响结论。
     - Interactive mode才显示下载命令及`yes/no/show-command`菜单。
   - 否则列出: `Found N 年报（<years>）. 招股说明书: present / missing. research/: K files.`
   - 检查 `data/filings/<ticker>/research/`；外部证据为空或有缺口时，Auto mode直接把缺口拆成claim交给`source-discovery`，Interactive mode才提供研究菜单。

3. **PDF 预抽取 cache**: 任一 `_extracted/<pdf-stem>/text.md` 缺失时，Auto mode直接运行`extract_pdf.py`，Interactive mode才询问是否执行。抽取失败时保留原PDF并记录错误，不要求用户操作浏览器。说明: `text.md` 带 `<!-- page N -->` markers, Read 友好; 图表/表格截图 + LLM 描述在 `images/`, 是业务分析金矿。

4. **Derive output path** `profiles/<ticker>-<YYYY-MM-DD>.md`:
   - 今日文件已存在 → 直接加载（continuation session）。
   - 只有旧日期文件 → `[resume / start-fresh]`; `resume` → 改名为今日日期（one-file-per-ticker-per-day 不变量）; `start-fresh` → 新建, 旧文件保留。
   - 无文件 → 复制 `.claude/skills/value-profile/template-zh.md` 到输出路径, 然后做**强制3项 cleanup**（template 含 meta 文档, 必须在开跑前剥离, 否则最终 profile 会残留不属于 ticker-specific 内容的模板说明）:
     1. **Title**: 第一行 `# 价值投资个股研究 Profile — Template` → `# 价值投资个股研究 Profile — <中文公司名> (<ticker>) <report_date>`（例: `# 价值投资个股研究 Profile — 贵州茅台 (600519.SH) 2026-05-01`）。
     2. **删 HTML comment block**: template 开头 `<!-- 模板版本 v2 ... Skill 在调用时会复制本模板到 profiles/<ticker>-<date>.md, 然后逐节填写。 -->` 整段删除。
     3. **删 "阅读姿态/分析框架" 段**: 从 `## 阅读姿态/分析框架（读前必读）` 到随后的 `---` separator 整段删除（指向 SKILL/references 的阅读指引, 属 skill-internal doc, 不属 profile 内容）。
     4. **删 heading 里的 template-instruction parenthetical**: 扫 `^#+` 所有 heading, 删除尾部给填写者的指令性括号 annotation。典型要删的 pattern: `（本节最后填写）` / `（PRIMARY — 先填）` / `（OPTIONAL — 后填）` / `（填入...）` / `（待填）` / `（SECONDARY — 定量补充）` 等。heading 本身 title 留下, 只剥离尾部给 filler 的 meta 指示。Ticker-specific 的 title 修饰（如"§3 护城河分析"后面的结论性标签）不动。

     然后填 Part 0 header（ticker / exchange / researcher = `git config user.name` / report_date = 今日; 中英文公司名派轻量子 agent 一句话查）。Auto / interactive 两种模式都必须做此 cleanup, 不可跳过。

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
   - **Auto mode (default)**: **直接进 Step 3 on next-undone, 不等输入**。Section 完成后回 Step 2 重新印进度表 + 跳下一节，直到所有可独立完成的section结束。§3.pre为假或存疑只跳过数字估值；Step 1单一路线失败时继续同功能fallback；只有已确认的一票否决或所有剩余工作都依赖真实阻塞时才终止。
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
- 缺失 → 触发 `scripts/extract_pdf.py` 或兜底 raw PDF。
- 图片 `_extracted/<pdf-stem>/images/` 带 LLM 描述 sidecar, §1-§2 业务分析金矿。

**ToC targeting 起点**:

| section | 年报章节 |
|---|---|
| §1.1 主营 / §1.2 客户 | 第三节业务概要; 第四节经营情况 |
| §1.3-§1.5 差异化/盈利/模式 | 第三节; 招股说明书业务与技术 |
| §1.6 现金流 | 第五节财务报告现金流量表 + 附注 |
| §2 成长空间 | 第四节行业竞争/管理层讨论 |
| §3 护城河 | 第三节核心竞争力; 第四节 |
| §4 管理与文化 | 第六节重要事项; 第七节股东; 第八节董监高 |
| §5 风险 | 第四节风险提示 |
| §Q1-§Q12 定量 | 第五节财务报告（全部）|
| §4.5 排雷 | 第五节附注（逐项）|
| §3.pre 三前提 | 第十节审计报告 + 第五节现金流 + 附注 |

### 3b. Scoped research dispatch

派 ONE `general-purpose` 子 agent。Prompt 英文（指令语言）, 强制中文输出。必须包含:

- section heading + template 的本节目标/指导问题。
- **公司级关键问题清单**:首次Part 1 dispatch前,main agent先从业务结构、简化财务报表、跨年变化和异常项形成2-5个ticker特有问题；新增证据改变判断时更新。先问题驱动研究，后模板查漏；canonical section继续完整覆盖,但正文不得按指导问题顺序逐题填空。
- 解析出的 `<!-- 数据源: ... -->` hint。
- extracted `text.md` 绝对路径（或 raw PDF 兜底）+ 3a 给出的 page range。
- ticker, 中文公司名, exchange, report_date。
- 已填好的相邻 section 作为上下文。
- **三大前提** (§2.2) — §1 / §3 / §5 必需, 3行判定。
- **能力圈四问** (§2.6) — §1 所有 subsection 必需, 4段独立答。
- **禁用8条空话** (§2.11.3)。
- **管理层口径校核** (§2.11.4) — Part 1 §1-§5 必填。
- **5步护城河分析** (§3 必需): a 分类（大/准 / 强/省 / 专）+ b 2项可证伪检验（提价/对手/切换成本 / ROE 路标任选二）+ c 跨年定量追溯（毛利率/净利率 / ROE 5y, CFO/NI 比值, 带页码）+ d 悲观情景（具体技术/偏好/监管/对手情景, 禁空话）+ e 宽/中 / 窄/弱标签。具体数字准绳见 `references/moat-framework.md` / template §3。
- **§4 管理层分析** → **delegate 到 `management-analysis` 子 skill**, 传参 `--target-profile <path> --section §4`; 详细流程（承诺 vs 兑现5年表/董事长5年评估/股东回报/道德风险一票否决）见 `.claude/skills/management-analysis/SKILL.md` §2-§3。Fallback (子 skill 不可用): 5年 forecast vs actual 表每行带页码, gap > 10% 连续 ≥ 3年 → `**置信度:** 低`, 目标突然消失 = 强信号必须指出, 言行一致检验 ≥ 2事件。具体执行见 management-analysis 子 skill。

### 3c. Main-agent review

读子 agent 产出。**驳回并重派**若任一:
- 事实缺引用。
- 管理层口径校核缺失或琐碎复读。
- 正文只是按template指导问题逐项填空,没有围绕公司级关键问题解释数据、原因和商业含义。
- 同一证据缺口在多个可见section重复解释，或护城河来源写成`测试通过/证据窗口/连续序列`等研究流程状态。
- 正文写“缺乏数据，无法分析”后继续列举缺失字段、已查来源、旧年份样本或接口错误。
- 填写区 generic, 无 ticker 特定细节。§3 护城河写茅台必须引用茅台镇水源 / 12987 工艺/基酒5年陈化/品牌价格带。
- §1.8 四问任一 < 50字/品牌复读/结论标签无场景 → §2.6.2 退回; 退回的是 §1.8 本节, 不动 §1.1-§1.7。

**Auto mode 重派方式 (§2.2.4 深调查)**: 不简单重跑同 prompt。先把外部缺口拆成独立claim交给`source-discovery`,保留已核实的部分证据,并只扩大未解决范围: 多读1-2年年报、展开附注、查招股书和监管披露,再按ledger搜索同行、供应商、行业、协会、学术、网页存档和可信二级来源。同一路线最多重试2次,随后转下一条独立合规路线；不是全部研究只能尝试2次。只有全部适用路线形成validated terminal `blocked/conflict/exhausted`后,才按state mapping决定该结论是否`需人工`。缺失数据只限制它直接支撑的结论,不得自动阻断同节其他问题、其他定性判断或整份profile；保留已核实的部分证据,分别写清“已知什么、可以判断什么、不能判断什么”。只有关键估值输入、法定前置门槛或明确一票否决项仍缺时才阻断对应路线。Interactive mode下用户可在3d主动`research more: <hint>`给方向。

Acceptable 后写中文终稿, 填 `**引用:**` `**置信度:**` `**管理层口径校核:**`（Part 1 §1-§5）。

### 3d. Save by mode

- **Auto mode (default)**: 3c review通过→**隐式accept**,直接原子写入profile（`**置信度:**`由3c写好）,回Step 2找下一节,**不印menu不等用户**。同一路线连续2次仍不达标时切换下一条独立路线；全部适用路线终态后仍缺关键证据,才按state mapping保存`需人工`。非关键缺口保留部分证据并继续不受影响的判断,不得机械降为中等置信度。
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
2. `bulk` → ONE 子 agent: Read 每个年报第五节, 逐年抽营收 / NI / 扣非 NI / 毛利率/净利率 / ROE / ROA / CFO / CapEx / 有息负债/现金/总资产/总负债/净资产/应收/存货, 就地填 Part 2 §Q1-§Q12 表, 每 cell `**来源:**` 带 `年报-YYYY.pdf p.NN`。顶行（ROE / 毛利/净利率）雪球 F10 联网交叉验证。
3. **Auto mode**: 子 agent 在 prompt 里明确要求它自己执行 random-sample 5 cells 雪球校核 + 汇报结果, 主 agent 收到后自动按 ≥ 4/5 一致规则判决（≥ 4/5 → 所有 §Q* 标 `已完成`; 否则不一致行标 `需人工`）, 不问用户。**Interactive mode**: 呈给用户 `Random-sample 5 cells: given <ROE 2024 = X%>, does 雪球 agree? [all-match / mismatch: <details>]`, 用户回复后主 agent 按规则判决。
4. ≥ 4/5 一致 → 所有 §Q* 标 `已完成`; 否则不一致行标 `需人工`。
5. `by-section` (interactive only) → 走标准 Step 3。

---

## Step 5 — 排雷清单模式 (§4.5) (详细子步骤)

**Delegate 到 `financial-redflag-scan` 子 skill**, 传参 `--target-profile <path> --section §4.5`; 详细流程（29项清单 + 6项高危附加检查 + 三表勾稽4条 + summary + 强制 `[accept / edit / research more]` 不 `defer / skip`）见 `.claude/skills/financial-redflag-scan/SKILL.md` §2-§3。

**Fallback（子 skill 不可用时, 主 skill 跑简化版）**:

1. 派 ONE 子 agent 对 Part 4 §4.5 29项逐项扫, 每项 `是 / 否 / 不适用 / 需人工` + 证据 + 页码; 6项高危附加检查显式 flag（商誉/净资产>20% | 其他应收≥10%流动资产 | 在建工程长年不转固 | CFO/NI<50%连续2年 | 生物资产/农林渔牧 | 管理层道德风险一票否决）。详细阈值/三表勾稽/造假模式见 `.claude/skills/financial-redflag-scan/references/fraud-library.md` §1-§4; 附注12项见 `.claude/skills/read-filing/references/statement-reading.md` §3。
2. 主 agent 复核缺引用 → re-dispatch（§2.2.4 深调查）。写 `**发现的风险 summary:**` 1-2段。
3. **Auto mode**: 3c 通过即保存, 不 confirm。**Interactive mode**: 用户确认 `[accept / edit / research more]`。

---

## Step 6 — 执行摘要合成 (Part 0 估值) (详细子步骤)

触发条件: ≥ 80% section 标 `已完成`。

**前置检查**: 若 §3.pre 三大前提任一假/存疑，只阻断本步骤的数字估值并把相关估值section写为条件跳过；不回滚或停止已经完成的定性研究。

**生意类型检查** (§2.3.1): 判定落在6类哪类, "不适用 PE" / "默认回避" → Part 0 标 "定性研究 only", 不输出估值数字。

**7字段结构化中文输出** (依据 §2.4 / §2.5):

1. **3年后归母净利润（三档）** — 业务板块拆解（≥ 2块, 每块量 × 价 × 净利率）: 乐观/中性/悲观, 每档附假设。
2. **合理 PE** = 1 / 10y 国债收益率 (~3.5% → ~28x, 典型25-30)。生意类型见 §2.3.1 估值矩阵。
3. **合理估值** = 中性3y NI × 合理 PE（± 10% 带宽）。
4. **买点** = 合理估值 × 50%（高杠杆 × 35%, 必须说明为何高杠杆, 依据 §2.3.1 硬指标）。
5. **卖点** = min(合理估值 × 1.5, 当年 NI × 50PE)。两候选都列, 取较低者。
6. **持仓姿态** (§2.5.2 discrete): 加仓/建仓 | 持有不动（收工睡觉）| 分批清仓。
   - **§2.9.1 估值动摇即停手守则**必须 inline 提示: 跌破买点第二档时, 若3y NI 预估动摇, 立即停止加仓, 回头重审下限 → 重算新买点 → 再决定。
7. **Top 3风险** — 来自 §5 + §4.5, 每条1-2句 + 触发条件。

**置信度汇总**: `高` 当 ≥ 60% section 高 AND §3.pre 全真; `中` 混合; `低` 任一块未做 OR 任一前提存疑。

- **Auto mode**: 3c review 通过（7字段完整、数字源头可追溯、§3.pre 全真或已 mark 降级）即 save 并 **skill 自行终止**。打 final summary: `✅ Profile 完成. N/67 sections 已完成, 估值 Part 0 已合成. 路径: profiles/<ticker>-<date>.md`。
- **Interactive mode**: 印摘要 + 双语菜单 `[accept / edit / research more]`, 等用户确认 → save。

---

## §4.6 Profile写作与读者渲染

写作验收只读取`profile-writing-style.md`，最终投影和机器字段负向检查只读取
`reader-rendering.md`。本操作文档不重定义正文或渲染规则。
