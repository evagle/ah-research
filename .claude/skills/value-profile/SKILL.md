---
name: value-profile
description: Walk a user through filling out a 价值投资 profile for a single A-share / HK stock. Auto-fetches 年报 / 招股说明书 PDFs via scripts/download_filings.py when missing, reads them as first-hand primary sources, gathers qualitative + quantitative research section-by-section, writes Chinese-language profile to profiles/<ticker>-<date>.md as it goes. Trigger on "/value-profile <ticker>", "研究 股票 <ticker>", or "fill out profile for <ticker>".
---

# Value Profile Skill

This skill runs as the **main Claude Code session agent** and orchestrates research via `general-purpose` subagents. It is an instruction document for the main model, not library code. The main agent owns file I/O, user 过关点, and review; subagents do scoped PDF reads and web research.

## 理论血统 / 参考文献

本 skill 的深度研究方法吸收自 `docs/value-profile/methodology-tang.md`（唐朝 / 唐书房价值投资体系）。该文档是理论来源, 不在 SKILL 和 template 正文中反复署名。以下所有分析框架（三大前提、5步护城河、管理层承诺兑现、财报排雷）均为**本项目的默认分析方法**, 子 agent 无需再标注"按某某方法"。

## 阅读姿态（必读, 写在每个子 agent 的开场白里）

1. **年报是写给全体利益相关方的文档, 不是写给价值投资者的。** 国企年报的读者包括: 监管机构、党组织、员工、地方政府、股东、供应商、经销商、投资者、媒体、竞争对手。价值投资者只是读者之一, 且**不是首要读者**。因此读年报要**读出弦外之音**:
   - 哪些段落是写给监管看的（合规话术、风险提示套话）
   - 哪些是写给员工看的（稳定、福利、培训信号）
   - 哪些是写给地方政府看的（纳税、就业、扶贫、共同富裕）
   - 哪些才是真正给股东的实质经营信息（数字、量价、产能、毛利结构）

2. **国企年报的关键股东信息常埋在附注**——应交税费、关联交易、对外担保、分红政策、其他应收款明细、存货构成。正文大段官样文章可以快速略读, 附注必须逐行读。

3. **分析框架**（本项目默认):
   - 三大前提筛（真报表 + 真盈利 + 可持续）—— 任一假/存疑, 立即降级为定性研究, 禁止进入估值
   - 5步护城河分析（分类 → 2 项可证伪检验 → 跨年定量追溯 + 年报页码引用 → 悲观情景 → 宽/中/窄/弱 标签）
   - 管理层承诺兑现（年度经营计划 vs 次年实际, 5 年跨度, 带页码）
   - 财报排雷（29 项清单 + 6 项高危模式）

4. **证据纪律**: 每个数字后面必须带 `(年报-YYYY.pdf p.NN)` 或 URL 引用。不带引用的数字一律视为未核实; 子 agent 禁止从记忆里编数字, 找不到就写 `待补充 — 年报未披露` 或 `证据不足, 需人工`。

## Invocation

- **Primary:** `/value-profile <ticker>` — ticker 是 `<code>.<exchange>`（例: `600519.SH`, `000001.SZ`, `0700.HK`）, 验证正则 `^[0-9]{4,6}\.(SH|SZ|HK)$`。
- **`--section <id>`** — 跳到指定 section, 例 `/value-profile 600519.SH --section 1.3`。跳过 Step 2 progress summary, 直接进入 Step 3。
- **`--resume`** — 强制加载最近一个 `profiles/<ticker>-*.md`, 不询问日期。

主 agent 在上述任一 invocation 下依次执行:

1. Step 1 Bootstrap + filings audit（验证 ticker、审计 `data/filings/<ticker>/`、询问是否 fetch、解析输出路径）。
2. Step 2 Progress map（解析现有 profile、渲染双语状态、等待路由）——**`--section` 时跳过**。
3. Step 3 Section worker（或在选中特定 section 时触发 Step 4 / Step 5 / Step 6 专用模式）。

Skill 不会自行终止, 每个 section 过关点后都会把控制权交回用户。

## Behavior

### Step 1 — Bootstrap + filings audit

1. **Validate ticker** against `^[0-9]{4,6}\.(SH|SZ|HK)$`. 失败时打印双语报错并 abort:
   > `❌ 无效 ticker: <input>. 期望格式 <code>.<exchange>（例 600519.SH, 0700.HK）. / Invalid ticker.`

2. **Audit `data/filings/<ticker>/`**:
   - 若目录缺失 OR 匹配 `年报-*.pdf` 的文件少于 **2** 份:
     - 打印双语提示:
       > `❌ 缺少年报 PDF. / Missing 年报 PDFs.`
       > `是否自动运行 python scripts/download_filings.py <ticker> --years 5 --include-prospectus? / Auto-run fetcher?`
       > `[yes / no / show-command]`
     - `yes` → Bash 工具 shell out, 实时 stream stdout/stderr 给用户。等待完成。fetcher exit 0 则重新 audit 目录; fetcher exit 1（部分或全部失败）则打印 fallback 手动 URL（http://www.cninfo.com.cn, 巨潮资讯网）并 abort, 告知用户需下载什么、放到哪。
     - `no` → abort, 输出手动下载说明（巨潮资讯网, 搜索 ticker, 下载年报 + 招股说明书, 按 `data/filings/README.md` 命名约定存入 `data/filings/<ticker>/`）。
     - `show-command` → 打印 CLI 原文（`python scripts/download_filings.py <ticker> --years 5 --include-prospectus`）并 abort, 不执行。
   - 否则列出可用文件:
     > `Found N 年报（<years comma-separated>）. 招股说明书: present / missing. research/: K files.`

   - 另外检查 `data/filings/<ticker>/research/`。若缺失或为空, 非阻塞提示:
     > `研报 cache 为空. 是否运行 python scripts/download_research.py <ticker> --years 3 --depth-only --max 15?（东方财富 API, 可选, 非阻塞）/ Research cache empty — fetch depth reports? [yes / no / show-command]`
     - `yes` → Bash shell out, stream output。exit 0 则重 audit; 非零 exit 打印失败并继续（研报是可选信号, 不 abort profile）。
     - `no` / `show-command` → 继续, profile 不被阻塞。

2.5. **PDF 预抽取 cache（extraction cache prep）**

    对 filings 目录中每个 `年报-*.pdf`, 检查 `data/filings/<ticker>/_extracted/<pdf-stem>/text.md` 是否存在。任一缺失则双语提示:
    > `PDFs not extracted yet. Run pre-extraction now? 可以加速后续 section worker. [yes / skip]`
    - `yes` → Bash shell out:
      ```bash
      for pdf in data/filings/<ticker>/年报-*.pdf; do python scripts/extract_pdf.py "$pdf"; done
      ```
      `招股说明书.pdf` 存在则一并 extract。实时 stream 进度。
    - `skip` → 继续, section worker 直接 Read PDFs（慢, 无 page markers）。

    说明: 预抽取的 `text.md` 文件带 page markers（`<!-- page N -->`）, Read 工具友好。图片（图表/表格截图 + LLM 生成的描述）在 `_extracted/<pdf-stem>/images/`。子 agent 应优先用 extracted cache 而非 raw PDF。cache layout 详见 `scripts/extract_pdf.py`。

3. **Derive output path** `profiles/<ticker>-<YYYY-MM-DD>.md`, 日期来自 `date +%Y-%m-%d`。
   - 今日文件已存在 → 直接加载（continuation session）。
   - 只有旧日期文件 → 询问:
     > `Prior profile profiles/<ticker>-<prior-date>.md exists. / 发现先前档案。[resume / start-fresh]`
     - `resume` → 把旧文件改名为今日日期（保持 one-file-per-ticker-per-day 不变量）并加载。
     - `start-fresh` → 创建今日新文件, 旧文件保留不动。
   - 无任何文件 → 复制 `docs/value-profile/template-zh.md` 到输出路径。填 Part 0 header:
     - `ticker` — CLI 参数。
     - `exchange` — 从 ticker 分离（`SH`/`SZ`/`HK`）。
     - `researcher` — `git config user.name`。
     - `report_date` — 今日。
     - `company_name_zh` / `company_name_en` — 派一个轻量 `general-purpose` 子 agent 从 web 查中英文公司名（一个 query, 一句话答复）。失败不阻塞, 留 `待补充` 继续。

### Step 2 — Progress map

1. **Parse the output file.** 对每个匹配 `^### §`（subsection heading）或 `^## §`（major-section heading）的行, 在其 block 内（直到下一个同级或更高级 heading）查找 `**置信度:**` 行。构造 dict `{section_id: status}`, 值域 `{已完成, 进行中, 未做, 已跳过, 需人工}`。

2. **Render a bilingual summary**, 例如:
   ```
   已完成 4 / 67 节（§0, §1.1, §1.2, §1.6）.
   下一节（next undone）: §1.3 差异化
   继续 this section? 或 选择 other section? 或 exit? [continue / pick-section / exit]
   ```

3. **Await user input.** 路由:
   - `continue` → Step 3 on the next-undone section。
   - `pick-section` → 询问 `哪一节 / which section id?`（自由文本）, 然后 Step 3。§Q* id 去 Step 4; §4.5（Part 4 排雷）去 Step 5; 其他普通 Step 3。
   - `exit` → 停（skill 可稍后重新唤起）。

### Step 3 — Section worker（inner loop, per section）

#### 3.pre — 三大前提筛

在给 §1 / §3 定性产出（或任何 Part 4 估值）投入任何精力之前, section 子 agent **必须**先确认或标记 **三大前提**——它是所有后续论断的"承重墙"。任一答为 `假 / 存疑`, 整份 profile 降级为 `**置信度:** 低`, 并阻断 Step 6 估值合成。

1. **财报是真实的吗?**（True audit）— 读年报 第十节"审计报告"。预期 `标准无保留意见`。任何其他意见（保留 / 无法表示意见 / 否定 / 带实质内容的强调事项）→ `假`。标注会计师事务所, 以及最近 3 年是否换所。
2. **盈利质量是真实的吗?**（True earnings）— 对年报 第五节"财务报告"（或对应的 extracted `text.md`）执行:
   - `近3年 经营活动现金流净额 累计 ≥ 近3年 净利润 累计`（区分"纸面利润"与"真金白银"）
   - `销售收现率 = 销售商品提供劳务收到的现金 /（营业收入 ×（1+增值税率））≥ ~1.0`（±5%）
   - 任一 check 持续 ≤ 0.5 ratio 超过 2 年 → `假 / 存疑`。
3. **盈利是可持续的吗?**（Durability）— 近 5 年 ROE 稳定 ≥ 15%? 毛利率 未剧烈波动（±5 点内）? 无一次性大额非经常损益主导利润（扣非净利润 / 净利润 ≥ 0.85）?

**筛查行为**: 三项任一 → `假 / 存疑`, 子 agent 停止深度定性研究, 把该 section 标 `**置信度:** 低`, 并在开头引用处写明失败原因, 不得进入估值。Step 6 遇此筛失败需 abort 并打出 "估值前置清单未通过" 提示条, 引用本筛。

完整推导 + 案例见 `docs/value-profile/methodology-tang.md` §A.2。

#### 3a. PDF pre-read

**优先使用预抽取的 text cache, 而非 raw PDFs。**

- 若 `data/filings/<ticker>/_extracted/<年报-YYYY>/text.md` 存在 → 直接 Read。用 line-offset 导航; `<!-- page N -->` marker 让子 agent 能便宜地 ToC-target 具体章节。
- cache 缺失 → 要么 Read `.pdf`（慢, 无 page markers）, 要么先触发抽取: `Bash: python scripts/extract_pdf.py <pdf>`, 然后 Read 结果。
- 图片: `_extracted/<pdf-stem>/images/` 存放图表/表格截图, 每张带 LLM 描述 sidecar。这是 §1-§2 业务分析的金矿（产能/销量/渠道拆分常在图里而非正文）。

ToC targeting — 用下表作为起点, 再结合该 section 的 `<!-- 数据源: ... -->` hint 收窄:

| 小节类型 | 年报章节（近似） |
|---|---|
| §1.1 主营产品 | 第三节"公司业务概要"; 第四节"经营情况讨论与分析" |
| §1.2 客户 | 第四节"经营情况讨论与分析"; 第六节"重要事项"（大客户披露） |
| §1.3–§1.5 差异化/盈利/生意特性 | 第三节"公司业务概要"; 招股说明书"业务与技术" |
| §1.6 现金流 | 第五节"财务报告"现金流量表 + 附注 |
| §1.7 已知优秀模式 | 第三节 + 行业研报 |
| §2 成长空间 | 第四节"行业竞争状况"; 第四节"管理层讨论与分析" |
| §3 护城河 | 第三节"公司业务概要"（核心竞争力小节）; 第四节 |
| §4 管理与文化 | 第六节"重要事项"; 第七节"股份变动和股东情况"; 第八节"董事、监事、高级管理人员" |
| §5 风险 | 第四节"管理层讨论与分析"（风险提示小节） |
| §Q1–§Q12 定量 | 第五节"财务报告"（全部） |
| Part 4 §4.5 排雷 | 第五节"财务报告"附注（逐项） |
| 三大前提筛（§3.pre） | 第十节"审计报告" + 第五节现金流量表 + 附注 |

#### 3b. Scoped research dispatch

派 ONE `general-purpose` 子 agent。Prompt 用英文（指令语言）, 但强制要求中文输出。Prompt 必须包含:

- section heading + template 的 本节目标 / 指导问题 prompt block。
- 解析出的 `<!-- 数据源: ... -->` hint。
- `data/filings/<ticker>/_extracted/` 下相关年报 extracted `text.md` cache 的绝对路径（或 raw PDF 作 fallback）+ 3a 给出的 page range。
- ticker, 中文公司名, exchange, report_date。
- 已填好的相邻 section 作为上下文（例: §1.3 传 §1.1 和 §1.2 的内容; §3.x 传 §1 商业模式）。
- **Language directive:** 中文作答。每个事实引用 `年报-YYYY.pdf p.NN`（来自 extracted `text.md` 的 `<!-- page N -->` marker）或 web URL。无法核实 → `证据不足, 需人工补充`。
- **三大前提筛**（§3.pre）— §1 / §3 / §5 sections 必需。子 agent 在任何定性段落前先输出 3 行筛查判定。
- **管理层口径校核 directive**（仅 Part 1 §1–§5 定性 sections）: 填 `管理层口径校核` 字段, 说明年报口径与外部信号（研报 / 价盘 / 媒体报道 / 监管披露）的差异。"年报说 X, 我们同意 X" 这种琐屑话将被打回重做。

**本项目分析纪律（必须遵守, 非可选）:**

1. **禁用 8 条空话**。以下 stock phrases 若无具体佐证（人名 / 数字 / 日期 / 引用）, 一律退回重写:
   - "具有强大品牌" / "技术领先" / "行业龙头" / "管理优秀" / "市场广阔"
   - "核心竞争力突出" / "护城河宽广" / "成长空间巨大"

2. **5步护城河分析**（每个 §3 subsection 必需, 顺序不可跳）:

   **步骤 a: 分类** — 把护城河标记为以下五类之一或多选:
   - **大**: 规模经济 / 网络效应（例: 有效规模壁垒, 自然垄断, 双边网络）
   - **准**: 成长期 / 雏形类——某一维度（品牌 / 渠道 / 技术）已现护城河苗头, 但尚未满足"5 年以上可证伪增长"标准。准 ≠ 弱, 准是"还不够强, 但方向对, 可观察"。
   - **强**: 品牌 / 定价权 / 客户黏性（例: 可涨价不掉量, 心智占据）
   - **省**: 低成本结构（地理 / 工艺 / 采购 / 规模成本优势）
   - **专**: 特许经营 / 牌照 / 不可复制工艺（例: 监管准入, 专利保护, 秘方工艺）

   **步骤 b: 2 项可证伪检验**（任选两项, 带具体数字）:
   - **提价检验**: 近 5 年是否涨价而量不掉? 写清年份、涨幅、量变。
   - **对手检验**: 前三大挑战者是谁, 份额在涨还是在跌? 写具体份额数字。
   - **切换成本场景**: 一段式"我是客户, 为什么不换"的具体演练。
   - **ROE 路标**: 近 5 年 ROE 稳定 ≥ 15%? 若跌, 哪一年, 为什么? 超额 ROE 背后的"账本外资产"在哪?

   **步骤 c: 跨年定量追溯** — 引用具体年报数字: 近 5 年毛利率 / 净利率 / ROE 稳定性、经营现金流 / 净利润 比值。每个数字必须带 `(年报-YYYY.pdf p.NN)`。

   **步骤 d: 悲观情景** — 指名一个能打破该护城河的具体情景（技术切换 / 消费偏好变迁 / 监管 / 对手变招）。不写"难免有风险"这类空话, 必须具体。

   **步骤 e: 宽/中/窄/弱 标签** — 按以下标准判定:
   - **宽**: 5 项中满足 ≥ 4 项且关键检验（提价 or ROE）≥ 10 年历史支撑; 且未来 10 年可预见无颠覆情景。
   - **中**: 满足 3 项, 关键检验 5-10 年支撑; 未来 5 年护城河大概率维持, 10 年存疑。
   - **窄**: 满足 2 项, 关键检验仅 3-5 年; 未来 3 年维持, 5 年存疑。
   - **弱**: 仅满足 1 项, 关键检验 < 3 年, 或定性证据无定量支撑; 不建议作为买入核心论据。
   - **准类标签**: 若分类为"准"型, 标签上限为"中", 否则定义矛盾（"准"意味着尚未完全成型）。

3. **管理层 承诺 vs 兑现**（§4 必需）:
   - 拉 3-5 年年报"年度经营计划" / "管理层讨论与分析"。
   - 构造 forecast vs actual 表（承诺 vs 兑现）。每行带年报页码。
   - 若 gap > 10% 连续 ≥ 3 年 → `**置信度:** 低`, 并在 `管理层口径校核` 字段标记系统性偏差（过度保守 or 画大饼）。
   - 次年目标变化是试金石: 若当年未达标而次年仍定高目标, 或目标突然消失（从年报中被移除）, 都是强信号, 必须指出。
   - §4.3 企业家清单应用言行一致检验, 至少给 2 个具体例子（决策 + 日期 + 结果）。

4. **财报 forensic**（§5 风险 + Part 4 §4.5 排雷必需）:
   - 真实销售公式（剔除预收款操纵）:
     `真实营收 = 报表营收 +（期末预收 − 期初预收）/ 1.17`
   - 销售收现 交叉检验:
     `销售收现 = 营业收入 ×（1+增值税率）− Δ应收账款 − Δ应收票据 + Δ预收账款 / 合同负债`
     对比现金流量表"销售商品提供劳务收到的现金"。**任何背离 > 5% → 调查并在 section 中标记。**

方法论来源: `docs/value-profile/methodology-tang.md` §H.2（prompt-ready 片段）, §C / §D / §E（完整推导）。

#### 3c. Main-agent review

读子 agent 的产出。**驳回并重新派发**（回到 3b, 附 细化提示）若任一:

- 某事实缺少引用。
- `管理层口径校核` 缺失或只是琐碎复读年报（仅限 Part 1 §1–§5 sections）。
- 填写区 generic——没有 ticker 特定细节。§3 护城河若写茅台, 必须引用 茅台镇水源 / 12987 工艺 / 基酒 5 年陈化 / 品牌价格带, 不能用抽象的"品牌护城河"。

Acceptable 后, 写出该 section 的中文终稿, 填 `**引用:**`, `**置信度:**`, 以及（Part 1 §1–§5）`**管理层口径校核:**`。

#### 3d. 用户过关点

把 draft 呈给用户。profile 内容是中文; operator 菜单双语。offer:

- `accept` → 保存 draft, 覆盖该 section heading 下原有内容。进度标 `已完成`。
- `edit: <text>` → 应用用户文本修改（用户 edits 可中可英）, 保存为 `已完成`。
- `defer` → 不保存。标 `未做`, 回 Step 2。
- `skip` → 填写区写 `N/A — <原因>`, 标 `已跳过`, 保存。
- `research more: <hint>` → 回 3b, 把用户 hint 附到子 agent prompt（收窄 focus）。

#### 3e. Save and continue

原子写入（写 `.tmp` 文件, `mv` 覆盖）。profile 文件在任何 save 后都必须是合法 markdown。回 Step 2 取下一个 section。

### Step 4 — Part 2 bulk mode（§Q1–§Q12 被选中时触发）

用户选任一 Part 2 §Q* section 时:

1. offer:
   > `Run Part 2 in bulk mode（single subagent extracts all 10y quant tables）? Or section-by-section? / 批量 or 逐节? [bulk / by-section]`

2. `bulk` → 派 ONE `general-purpose` 子 agent:
   - Read 每个 `data/filings/<ticker>/年报-*.pdf`（通过 Read 工具, 定位第五节"财务报告"）。
   - 按年抽取: 营业收入、净利润、扣非净利润、毛利率、净利率、ROE、ROA、经营现金流净额、资本开支、有息负债、现金及等价物、总资产、总负债、净资产、应收账款、存货。
   - 就地填 `profiles/<ticker>-<YYYY-MM-DD>.md` 的 Part 2 §Q1–§Q12 表, 保留 markdown 结构。
   - 每个 cell 在 `**来源:**` 行带页码引用（`年报-YYYY.pdf p.NN`）。
   - 对顶行（ROE、毛利率、净利率）用雪球 F10 做联网交叉检验; 有差异当场就地报告。

3. 把填好的 Part 2 呈给用户:
   > `Random-sample 5 cells: given <ROE 2024 = X%>, does 雪球 agree? [all-match / mismatch: <details>]`

4. ≥ 4/5 一致 → 所有 §Q* subsection 标 `已完成`。否则不一致的行标 `需人工`, 一致的行留 `已完成`。

5. `by-section` → 走标准 Step 3, 逐个 §Q* 处理。

### Step 5 — 排雷清单模式（§4.5 被选中时触发, Part 4）

1. 派 ONE `general-purpose` 子 agent, 复合 prompt:
   > 对 Part 4 §4.5 排雷清单 29 项逐项, 读 `data/filings/<ticker>/_extracted/年报-<latest>/text.md`（fallback: raw PDF）的资产负债表 + 利润表 + 现金流量表 + 财务报表附注。每项回答 `是` / `否` / `不适用` / `需人工`, 附 1 句证据摘要 + 年报页码引用。

   在子 agent prompt 里嵌入完整的 29 项 list（从 template §4.5 表拉取）。

   **财报高危模式 overlay**（`methodology-tang.md` §D.1-D.3）: 以下模式即使 29 项未逐字列出, 也要显式 flag:
   - **商誉 / 净资产 > 20%** → 雷区, 未来可能一次性减值。
   - **其他应收款 异常大额**（≥ 10% 流动资产, 或对单一关联方挂账长年）→ 关联方占款疑点。
   - **在建工程** 长年不转固定资产 → 挂账操纵折旧。
   - **经营现金流净额 < 50% 净利润** 连续 2 年 → 利润真实性红旗。
   - **生物资产 / 农林渔牧** 主业 → 造假高危区（獐子岛 style）。
   - **管理层道德红旗** — 历史上曾出现虚假陈述 / 违规处罚 / 股东利益输送 → 直接大幅降级。

2. 子 agent 返回填好的表。

3. 主 agent 复核缺失引用, 必要时 re-dispatch, 然后把表写入 profile。

4. 写一段 **`发现的红旗 summary:`** 段落（1–2 段）, 聚焦任何 `是` / `需人工` 项, 说明这项雷是什么、为何对本 ticker 重要、交叉检验的下一步。

5. 用户过关点 — 仅 offer `[accept / edit: <text> / research more: <hint>]`。**不 offer `defer` / `skip`**。排雷是强制的, 跳过会让整份 profile 失效。

### Step 6 — 执行摘要合成（Part 0, 估值输出）

触发条件: ≥ 80% 的 section 标 `已完成`（由 Step 2 的 progress map 计算）。

**前置筛查**: 若 §3.pre 三大前提筛的任一项为 `假 / 存疑`, abort Step 6 并打 提示条:
> `❌ 估值前置清单未通过（三大前提 §<which> = 假/存疑）. 无法进入估值. 请先修复 §3.pre, 或将 Part 0 标记为"不可估值 — 仅定性研究"。`

否则:

1. offer:
   > `执行摘要 synthesis ready? / Ready to draft Part 0（估值）? [yes / not yet]`

2. `yes` → 主 agent 读完所有完成 section, 按以下 **7 字段结构化** 中文输出（取自 `methodology-tang.md` §F）。任一字段缺失 → 该 section 回 `进行中`, 非 `已完成`。

   1. **3 年后归母净利润（三档）** — 业务板块拆解（至少 2 块, 每块列 量 × 价 × 净利率）:
      - 乐观: `<N>` 亿元 — 假设 `<具体假设>`
      - 中性: `<N>` 亿元 — base case
      - 悲观: `<N>` 亿元 — 假设 `<具体假设>`
   2. **合理 PE** = `1 / 当前 10y 国债 收益率`。当前无风险收益率约 3.5% → 合理 PE ≈ 28x（典型区间 25-30; 超出需 justify）。**注意**: 合理 PE 不随增速调整——增速已经反映在 3y 净利润里。
   3. **合理估值** = 中性 3y 净利润 × 合理 PE（± 10% 带宽）。
   4. **买点（Buy point）** = 合理估值 × 0.5（常规）。高杠杆标的打 7 折（× 0.35）——必须在字段中说明为何判定为高杠杆（例: 有息负债 / 净资产、经营现金流 / 有息负债）。
   5. **卖点（Sell point）** = `min(合理估值 × 1.5, 当年净利润 × 50 PE)`。两 candidate 都列, 取较低者。
   6. **持仓姿态（discrete）**:
      - `加仓 / 建仓` — 当前市值 < 买点
      - `持有不动（收工睡觉）` — 买点 ≤ 当前市值 < 卖点
      - `分批清仓` — 当前市值 > 卖点（触发即卖 1/3; 再涨 10% 卖 1/3; 再涨 10% 清仓）
   7. **Top 3 风险**（ranked）— 来自 §5 风险分析 + §4.5 发现的红旗; 每条 1-2 句 + 触发条件。

   **置信度汇总**: `**置信度:** 高` 当 ≥ 60% section 为高 AND §3.pre 三大前提全部 = 真; `中` 混合情况; `低` 若任一块未做 OR 任一前提 = 存疑。

   **Labeling**: 每份 Part 0 draft 必须以这行结尾: `> 本摘要基于 AI 研究 + 用户审阅, 非投资建议. 最近审阅日期 = <today>.`

3. 用户过关点（`[accept / edit / research more]`）→ save。

## 深度调研操作手册（本项目实战积累, 每次新 ticker 研究前过一遍）

1. **先预抽取所有 PDF 再分析。** 调用 `python scripts/extract_pdf.py` 把所有年报、招股说明书转成 `_extracted/<filing>/text.md`, 避免每次 Read PDF 爆 context。一次预处理, 后续所有 section 都吃 cache。
2. **跨年数据必须带页码引用。** 每个数字后面加 `(年报-YYYY.pdf p.NN)`, 不带引用的数字一律视为未核实。禁止从记忆里编数字, 找不到就写 `待补充 — 年报未披露`。
3. **forecast vs actual 5 年表（§4.2 模板）。** 核对管理层第 N 年度经营计划 vs 第 N+1 年实际营收增长, 评估管理层 guidance 诚信度。适用于任何有明确 guidance 的企业, 尤其是国企。
4. **次年度经营计划是管理层诚信度的试金石。** 对比当年目标 / 实际 / 次年目标的变化。管理层是"打折保守"还是"画大饼"? 目标突然消失（例: 茅台年报-2025 删除量增目标）是强信号, 必须在 profile 里标红。
5. **护城河证据常驻章节**（年报里优先读的 section）: 主营业务构成、产销量明细、产能情况、主要财务指标、市场地位披露、品牌建设投入。
6. **国企利益相关方视角要额外读的章节**: 应交税费明细、关联交易、对外担保、社会责任报告、利润分配预案、内部控制审计意见、监事会报告、董事会报告首尾（首讲政绩, 尾藏风险）。
7. **大段重写后清理 v1 存根。** 把 section 彻底重写之后, 务必删除遗留的旧 subsection stub, 防止内容双写让读者困惑。每次 commit 前 grep 自检一下有没有重复的 heading。
8. **commit 粒度 = 单 section。** 每个大 section 单独 commit, `git add <具体文件>`。**禁止 `git add -A` / `git add .`**（易误提交 data/、profile 半成品、secrets）。
9. **不为假设场景编造事实。** 若年报里找不到某条事实, 宁可标 `(来源待补)` 也绝不能编造。编造一次, 整份 profile 的可信度归零。
10. **先读年报再读研报, 不要反过来。** 年报是第一手事实, 研报是二手解读。先用年报建立事实骨架, 再拿研报交叉验证或吸收分析师的视角。年报说没有的事实, 研报说了也要打个问号。
11. **图表是金矿。** 产能、销量、渠道拆分常常只在年报的图表里, 不在正文。extract_pdf.py 的 images 目录 + LLM 描述 sidecar 要主动扫。
12. **附注比正文重。** 国企年报正文多官样文章, 实质信息（关联方、应交税费、担保、分红、其他应收款明细）在附注。子 agent 读年报必须走到附注层。
13. **管理层口径校核不是摆设。** 写"年报说 X, 我们同意 X" = 没做 spin check。真正的 spin check 要对比年报 vs 研报 vs 财新 vs 经销商反馈 vs 价盘数据, 指出哪里年报做了美化 / 避而不谈。

## Language policy

- **Profile 内容（`.md` 文件）**: 中文。每个填写区、`**引用:**`、`**管理层口径校核:**`、总结段落均为中文。
- **Operator-facing 输出**（过关点 prompts、status summary、errors）: 双语。中文为主, 必要时附英文括注。
- **子 agent prompts**: 英文（指令语言为英文; prompt 内部的 data / output directive 强制子 agent 用中文输出）。
- **Commit messages**: 英文。
- **中英混用避讳**: 避免"SOE 企业"/"stakeholder 视角"/"bear case 情景"这类混写; 统一中文化（国企 / 利益相关方 / 悲观情景）。保留的英文缩写仅限于会计/金融术语: ROE, ROIC, DCF, GDP, PE, PB, ESG。这些缩写前后不加多余空格（"ROE长期15%"）。
- **CJK/ASCII 空格规则**: 中文字符与紧邻西文/数字之间不插空格。例: 写 "营收增长"（非 "营收 增长"）, "茅台的品牌"（非 "茅台 的 品牌"）, "ROE长期15%"（非 "ROE 长期 15%"）。斜杠分隔的中文不要两侧加空格: 写 "大/准/强"（非 "大 /准 /强"）。

**方法论参考**: `docs/value-profile/methodology-tang.md` 是本项目深度分析框架的理论来源。当不确定某个 moat / management / valuation section 要挖多深、问什么问题、如何组织时, 参考 §B（商业模式）到 §G（茅台 seed）。§H.2 是 prompt-ready 片段。该文档的 attribution 保留在文件内部, 但不在 SKILL / template / profile 的日常文字中反复出现——本 skill 的分析方法已内化。

## What this skill MUST NOT do

- MUST NOT 重写标 `已完成` 的 section, 除非显式 `--force`（v0 不提供）。
- MUST NOT 编造数字或引用。无来源的论断写 `待补充` + 一行原因。
- MUST NOT 用英文写 profile 内容。Operator 行可双语, `.md` 文件必须中文。
- MUST NOT 没有年报 PDFs 就开干。Step 1.2 offer fetcher 或 abort——决不生成带 placeholder 引用的 profile。
- MUST NOT 跑 `git commit`, 用户自己 commit。
- MUST NOT 调用 `src/ah_research/`（平台数据层尚未就绪）。Graduation path 见下文。
- MUST NOT 未经 Step 1.2 显式确认就自动下载 PDF。`no` / `show-command` 必须不动文件系统。

## Failure modes & recovery

| Failure | Recovery |
|---|---|
| 子 agent 输出缺引用 | 主 agent 把无引用论断改写为 `证据不足, 需人工补充`——**绝不编造引用** |
| `管理层口径校核` 琐碎话漏网 | 用户 accept 就保存, 但 Step 3c 应拦住——当作 skill-regression 信号 |
| 年报 PDF 损坏/不可读 | 引用里标 `年报-YYYY.pdf（unreadable）`, 继续用其他来源; 不 abort 该 section |
| profile 有 merge conflict（两个 session 并发编辑） | 不自动 resolve。打 warning, 让用户手动解决 |
| 子 agent 配额 / 限流 | 用更窄 page range 重试一次。仍失败 → 存一段 `待补充` + 原因, 状态留 `进行中` |
| Step 1.2 fetcher 失败 | 回退到手动 cninfo URL 并 abort。**绝不生成无 filings 的破 profile** |
| 用户选的 section id 不在 template | 建议最近匹配（例 `1.3` → `§1.3 差异化`）; 不静默继续 |

## Graduation path

`ah-research` Phase 1 落地、`DataRepository` 可用之后, 机械迁移:

1. **Step 4 Part 2 bulk** → 子 agent 优先调 `ah_research.DataRepository.get_fundamentals(<ticker>, start=<10y>)` 而非 PDF 解析。fetch 参数写在 `**来源:**` 行。repo 未覆盖的 cell 回退 PDF。
2. **Step 5 排雷 #12, #23, #28**（纯数值: 应收/营收, 商誉/净资产, 有息负债/经营现金流）→ 走 DataRepository 算术, 不靠肉眼读 PDF。
3. **定性 section**（§1–§5, §4.5 定性项如"关联交易异常"）继续读年报 PDF。没有数据源能替代管理层的原话——不 graduate。
4. **`scripts/download_filings.py`** 终将挪进 `src/ah_research/integrations/cninfo_client.py`, 暴露为 repo 方法。在此之前 skill 继续 shell out。

## 子 agent prompt 模板参考

Step 3b dispatch 示例。主 agent 传给 `general-purpose` 子 agent 的内容, 针对 600519.SH §1.3 差异化; 换 section 时替换目标 section block、数据源 hint、page range 即可。

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

PDFs to read（use the Read tool, target the stated page ranges first）:
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/年报-2024.pdf pages 8-35
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/年报-2023.pdf pages 8-35
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/招股说明书.pdf pages 40-80

Adjacent context（已填好 sections）:
§1.1 公司核心资产、主营产品和服务: <inlined content>
§1.2 公司客户: <inlined content>

Output requirements:
1. 中文作答, 不要英文段落。
2. §1.3 填写区写 3-6 条关于茅台差异化的具体论断。候选证据: 茅台镇水源、12987 工艺、基酒 5 年陈化、品牌价格带、经销商渠道网——挑关键的, 每条都带年报页码。
3. 每条引用 `年报-YYYY.pdf p.NN` 或 web URL。无法核实 → `证据不足, 需人工补充`。
4. 填 **管理层口径校核:**, 指出年报口径与研报/价盘/媒体的差异。"年报说 X, 我们同意" 视为不合格。
5. 按引用密度和 spin-check 深度设置 **置信度:** 高/中/低。
6. 禁用空话（"公司竞争力强"）。只写 ticker-specific 证据。

返回完整 section block（heading + 填写区 + 引用 + 置信度 + 管理层口径校核）。
```
