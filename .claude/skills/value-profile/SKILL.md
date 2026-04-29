---
name: value-profile
description: Walk a user through filling out a 价值投资 profile for a single A-share / HK stock. Auto-fetches 年报 / 招股说明书 PDFs via scripts/download_filings.py when missing, reads them as first-hand primary sources, gathers qualitative + quantitative research section-by-section, writes Chinese-language profile to profiles/<ticker>-<date>.md as it goes. Trigger on "/value-profile <ticker>", "研究 股票 <ticker>", or "fill out profile for <ticker>".
---

# Value Profile Skill

This skill runs as the **main Claude Code session agent** and orchestrates research via `general-purpose` subagents. It is an instruction document for the main model, not library code. The main agent owns file I/O, user gates, and review; subagents do scoped PDF reads and web research.

## Invocation

- **Primary:** `/value-profile <ticker>` — ticker is `<code>.<exchange>` (e.g. `600519.SH`, `000001.SZ`, `0700.HK`). Validated against `^[0-9]{4,6}\.(SH|SZ|HK)$`.
- **`--section <id>`** — jump to a specific section, e.g. `/value-profile 600519.SH --section 1.3`. Skips the Step 2 progress summary and goes straight to Step 3 for that section.
- **`--resume`** — force-load the most recent existing `profiles/<ticker>-*.md` without date-prompting. Use when continuing a mid-session partial profile.

On any of these invocations the main agent performs, in order:

1. Step 1 Bootstrap + filings audit (validate ticker, audit `data/filings/<ticker>/`, offer fetcher, resolve output path).
2. Step 2 Progress map (parse existing profile, render bilingual status, await user routing) — **skipped if `--section` is set**.
3. Step 3 Section worker (or Step 4 / Step 5 / Step 6 if the chosen section triggers a specialized mode).

The skill never terminates voluntarily. It always returns control to the user after each section gate.

## Behavior

### Step 1 — Bootstrap + filings audit

1. **Validate ticker** against `^[0-9]{4,6}\.(SH|SZ|HK)$`. On failure print a bilingual error and abort:
   > `❌ 无效 ticker: <input>. 期望格式 <code>.<exchange> (e.g. 600519.SH, 0700.HK). / Invalid ticker.`

2. **Audit `data/filings/<ticker>/`**:
   - If the directory is missing OR contains fewer than **2** files matching `年报-*.pdf`:
     - Present a bilingual prompt:
       > `❌ 缺少年报 PDF. / Missing 年报 PDFs.`
       > `是否自动运行 python scripts/download_filings.py <ticker> --years 5 --include-prospectus? / Auto-run fetcher?`
       > `[yes / no / show-command]`
     - `yes` → shell out via the Bash tool, stream stdout/stderr to the user in real time. Wait to completion. On fetcher exit 0, **re-audit** the directory. On fetcher exit 1 (partial or total failure), print the fallback manual URL (`http://www.cninfo.com.cn` — 巨潮资讯网) and abort with a clear message telling the user what to download and where to drop it.
     - `no` → abort with the manual-download instructions (巨潮资讯网 http://www.cninfo.com.cn, search ticker, download 年报 + 招股说明书, save to `data/filings/<ticker>/` with the naming convention in `data/filings/README.md`).
     - `show-command` → print the exact CLI (`python scripts/download_filings.py <ticker> --years 5 --include-prospectus`) and abort without running it.
   - Otherwise list what's available:
     > `Found N 年报 (<years comma-separated>). 招股说明书: present / missing. 研报/: K files.`

2.5. **Extraction cache prep (new)**
    For each `年报-*.pdf` in the filings dir, check if `data/filings/<ticker>/_extracted/<pdf-stem>/text.md` exists. If any are missing, offer a bilingual prompt:
    > `PDFs not extracted yet. Run pre-extraction now? 可以加速后续 section worker. [yes / skip]`
    - `yes` → shell out via Bash, e.g.:
      ```bash
      for pdf in data/filings/<ticker>/年报-*.pdf; do python scripts/extract_pdf.py "$pdf"; done
      ```
      Also extract `招股说明书.pdf` if present. Stream progress to the user.
    - `skip` → continue; the section worker will Read PDFs directly (slower, no page markers).

    Note: the pre-extracted `text.md` files have page markers (`<!-- page N -->`) and are Read-tool friendly. Images (chart/table screenshots with LLM descriptions) live under `_extracted/<pdf-stem>/images/`. Subagents should prefer these caches over raw PDFs whenever available. See `scripts/extract_pdf.py` for cache layout details.

3. **Derive output path** `profiles/<ticker>-<YYYY-MM-DD>.md` where the date is today from `date +%Y-%m-%d`.
   - If today's file already exists → load it (this is a continuation session).
   - If only a prior-date file exists → ask the user:
     > `Prior profile profiles/<ticker>-<prior-date>.md exists. / 发现先前档案。[resume / start-fresh]`
     - `resume` → rename the prior file to today's date (preserves the one-file-per-ticker-per-day invariant) and load it.
     - `start-fresh` → create a new file at today's path, leave the prior file untouched.
   - If no file exists → copy `docs/value-profile/template-zh.md` to the output path. Fill Part 0 header fields:
     - `ticker` — from CLI arg.
     - `exchange` — split from ticker (`SH`/`SZ`/`SH`).
     - `researcher` — from `git config user.name`.
     - `report_date` — today.
     - `company_name_zh` / `company_name_en` — dispatch a brief `general-purpose` subagent to look up the Chinese and English names from the web (one query, one-sentence answer). Do not block on this if the subagent fails; leave `待补充` and continue.

### Step 2 — Progress map

1. **Parse the output file.** For each line matching `^### §` (subsection heading) or `^## §` (major-section heading), find the next `**置信度:**` line within its block (before the next heading at the same or higher level). Build a dict `{section_id: status}` whose values are in `{已完成, 进行中, 未做, 已跳过, 需人工}`.

2. **Render a bilingual summary**, e.g.:
   ```
   已完成 4 / 67 节 (§0, §1.1, §1.2, §1.6).
   下一节 (next undone): §1.3 差异化
   继续 this section? 或 选择 other section? 或 exit? [continue / pick-section / exit]
   ```

3. **Await user input.** Route:
   - `continue` → Step 3 on the next-undone section.
   - `pick-section` → ask `哪一节 / which section id?` (free-text), then Step 3. If the user picks a §Q* id go to Step 4. If they pick §4.5 (Part 4 排雷) go to Step 5. Otherwise normal Step 3.
   - `exit` → stop (the skill can be re-invoked later).

### Step 3 — Section worker (inner loop, per section)

#### 3.pre — 三大前提 gate (唐朝 framework)

Before investing any effort in §1 / §3 qualitative output (or any Part 4 valuation work), the section subagent MUST first confirm or flag 唐朝's **三大前提** — the load-bearing "承重墙" beneath every subsequent claim. Any answer of `假 / 存疑` downgrades the whole profile to `**置信度:** 低` and blocks Step 6 valuation synthesis.

1. **财报是真实的吗?** (True audit) — pull the 年报 第十节 "审计报告" section. Expect `标准无保留意见`. Any other opinion (保留 / 无法表示意见 / 否定 / 强调事项 with substance) → `假`. Flag the auditor name and any auditor change in the last 3 years.
2. **盈利质量是真实的吗?** (True earnings) — run these checks against the 年报 第五节 "财务报告" / the extracted `text.md`:
   - `近3年 经营活动现金流净额 累计 ≥ 近3年 净利润 累计` (鉴定 "纸面利润" vs. "真金白银")
   - `销售收现率 = 销售商品提供劳务收到的现金 / (营业收入 × (1+增值税率)) ≥ ~1.0` (±5%)
   - 若任一 check 持续 ≤ 0.5 ratio 超过 2 年 → `假 / 存疑`.
3. **盈利是可持续的吗?** (Durability) — ROE 稳定 ≥ 15% 近 5 年? 毛利率 未剧烈波动 (±5 点内)? 无一次性大额非经常损益 主导利润 (扣非净利润 / 净利润 ≥ 0.85)?

**Gate behaviour**: if ANY of the three → `假 / 存疑`, the subagent halts deep qualitative research, marks the section `**置信度:** 低` with the failure reason as the opening citation, and does NOT proceed to valuation (Step 6 must abort with an "估值前置 checklist failed" banner referencing this gate).

Full derivation + examples: `docs/value-profile/methodology-tang.md` §A.2.

#### 3a. PDF pre-read

**Prefer the pre-extracted text cache over raw PDFs.**

- If `data/filings/<ticker>/_extracted/<年报-YYYY>/text.md` exists → READ IT. Use line-offset navigation; the `<!-- page N -->` markers let subagents ToC-target specific 章节 cheaply.
- If the cache is missing → either Read the `.pdf` directly (slow, no page markers) OR trigger extraction first: `Bash: python scripts/extract_pdf.py <pdf>`, then Read the output.
- Images: `_extracted/<pdf-stem>/images/` holds chart / table screenshots, each with an LLM-generated description sidecar. These are a gold mine for §1-§2 business analysis (产能 / 销量 / 渠道 breakdowns often live in charts not prose).

ToC targeting — use this standardized 年报 ToC mapping as a starting point and refine from the section's `<!-- 数据源: ... -->` hint:

| 小节类型 | 年报章节 (近似) |
|---|---|
| §1.1 主营产品 | 第三节 "公司业务概要"; 第四节 "经营情况讨论与分析" |
| §1.2 客户 | 第四节 "经营情况讨论与分析"; 第六节 "重要事项" (大客户披露) |
| §1.3–§1.5 差异化 / 盈利 / 生意特性 | 第三节 "公司业务概要"; 招股说明书 "业务与技术" |
| §1.6 现金流 | 第五节 "财务报告" 现金流量表 + 附注 |
| §1.7 已知优秀模式 | 第三节 + 行业研报 |
| §2 成长空间 | 第四节 "行业竞争状况"; 第四节 "管理层讨论与分析" |
| §3 护城河 | 第三节 "公司业务概要" (核心竞争力小节); 第四节 |
| §4 管理与文化 | 第六节 "重要事项"; 第七节 "股份变动和股东情况"; 第八节 "董事、监事、高级管理人员" |
| §5 风险 | 第四节 "管理层讨论与分析" (风险提示小节) |
| §Q1–§Q12 定量 | 第五节 "财务报告" (全部) |
| Part 4 §4.5 排雷 | 第五节 "财务报告" 附注 (逐项) |
| 三大前提 gate (§3.pre) | 第十节 "审计报告" + 第五节 现金流量表 + 附注 |

#### 3b. Scoped research dispatch

Dispatch ONE `general-purpose` subagent. The prompt is in English (subagent instruction language) but demands Chinese output. Include:

- The section heading + the template's 本节目标 / 指导问题 prompt block.
- The parsed `<!-- 数据源: ... -->` hint.
- Absolute paths to the relevant 年报 extracted text.md caches (or raw PDFs as fallback) in `data/filings/<ticker>/_extracted/` and the instructed page ranges (from 3a).
- Ticker, Chinese company name, exchange, report_date.
- Already-filled adjacent sections as context (e.g. for §1.3 pass §1.1 and §1.2 content, for §3.x pass §1 商业模式).
- **Language directive:** respond in Chinese. Every fact cites either `年报-YYYY.pdf p.NN` (from the `<!-- page N -->` marker in the extracted text.md) or a web URL. Flag anything unverifiable as `证据不足, 需人工补充`.
- **三大前提 gate** (§3.pre) — required for §1 / §3 / §5 sections. Subagent must output the 3-line gate verdict BEFORE any qualitative prose.
- **Spin-check directive** (ONLY for Part 1 §1–§5 qualitative sections): populate the `管理层口径校核` field noting where 年报 framing may differ from external signals (研报 / 价盘 / 媒体报道 / 监管披露). A trivial "年报 says X, we agree X" is a rejection.

**唐朝 disciplines (must follow, not optional):**

1. **Ban 8 hedging phrases.** Reject and rewrite any section containing the following stock phrases without concrete follow-up evidence (names, numbers, dates, citations):
   - "具有强大品牌" / "技术领先" / "行业龙头" / "管理优秀" / "市场广阔"
   - "核心竞争力突出" / "护城河宽广" / "成长空间巨大"

2. **护城河 5-step structure** (required for any §3 subsection):
   a. **Classification** — label the moat as one (or multi-select) of: `大` (有效规模 / 自然垄断) / `准` (监管 or 许可壁垒) / `强` (品牌 + 定价权) / `省` (低成本结构) / `专` (专利 / 工艺 + 时间).
   b. **Prove with 2 falsifiable reality checks.** Pick any two:
      - 提价 test: did the company raise prices in the last 5 years without volume loss? Cite year, magnitude, volume delta.
      - 对手 test: who are the top 3 challengers; are they gaining share? Cite concrete share numbers.
      - 切换成本 scenario: write a one-paragraph "我是客户, 为什么不换" specific example.
      - ROE 路标: is ROE sustained ≥ 15%? If it fell, in which year and why? Where are the high-ROE "账本外的资产"?
   c. **Quantitative trace** — cite specific 年报 rows: 近 5 年 毛利率 / 净利率 / ROE 稳定性, 经营现金流 / 净利润 比值.
   d. **Bear case** — name one specific scenario that would break the moat (tech shift / 消费偏好 / 监管 / 对手变招).
   e. **Label** — 宽 / 中 / 窄 / 弱.

3. **管理层 verification** (required for §4):
   - Pull 3-5 years of 年报 "年度经营计划" / "管理层讨论与分析" sections (year-over-year).
   - Build a 承诺 vs. 兑现 table (forecast vs. actual delivery). Cite page numbers per row.
   - If gap > 10% repeatedly (≥ 3 years) → `**置信度:** 低` and flag systematic over/under-promise bias in the `管理层口径校核` field.
   - For §4.3 企业家 checklist, apply the 言行一致 test with at least 2 specific examples (decision + date + outcome).

4. **财报 forensic** (required for §5 风险 + Part 4 §4.5 排雷):
   - 真实销售 formula (removes 预收款 manipulation):
     `真实营收 = 报表营收 + (期末预收 − 期初预收) / 1.17`
   - 销售收现 cross-check:
     `销售收现 = 营业收入 × (1+增值税率) − Δ应收账款 − Δ应收票据 + Δ预收账款 / 合同负债`
     Compare to 现金流量表 "销售商品提供劳务收到的现金". **Any divergence > 5% → investigate and flag in the section output.**

Methodology source: `docs/value-profile/methodology-tang.md` §H.2 (prompt-ready copy), §C / §D / §E for full derivation.

#### 3c. Main-agent review

Read the subagent's output. **Reject and re-dispatch** (loop back to 3b with a refinement hint) if any of:

- A fact lacks a citation.
- The `管理层口径校核` line is absent or trivially agrees with the 年报 (for Part 1 §1–§5 sections).
- The 填写区 is generic — no ticker-specific detail. For §3 护城河 on Moutai, for example, that means the draft must cite 茅台镇 水源 / 12987 工艺 / 基酒 5y cycle / 品牌 价格带 — not abstract "品牌 moat".

Once acceptable, write a polished Chinese draft of the section block with populated `**引用:**`, `**置信度:**`, and (for Part 1 §1–§5) `**管理层口径校核:**` fields.

#### 3d. User gate

Present the draft to the user. Profile content is Chinese; operator framing (the menu below) is bilingual. Offer:

- `accept` → save the draft, replacing any prior content under this section heading. Mark progress `已完成`.
- `edit: <text>` → apply the user's textual edits to the draft (user edits may be in Chinese or English), save as `已完成`.
- `defer` → save nothing. Mark `未做`. Return to Step 2.
- `skip` → fill 填写区 with `N/A — <reason>`, mark `已跳过`, save.
- `research more: <hint>` → loop back to 3b with the user's hint appended to the subagent prompt (narrower focus).

#### 3e. Save and continue

Write atomically (write to a `.tmp` file, `mv` over). The profile file must always be valid markdown after any save. Return to Step 2 for the next section.

### Step 4 — Part 2 bulk mode (triggered on §Q1–§Q12 selection)

When the user picks any Part 2 §Q* section:

1. Offer:
   > `Run Part 2 in bulk mode (single subagent extracts all 10y quant tables)? Or section-by-section? / 批量 or 逐节? [bulk / by-section]`

2. `bulk` → dispatch ONE `general-purpose` subagent to:
   - Read every `data/filings/<ticker>/年报-*.pdf` via the `Read` tool, targeting 第五节 "财务报告".
   - Extract per year: 营业收入, 净利润, 扣非净利润, 毛利率, 净利率, ROE, ROA, 经营现金流净额, 资本开支, 有息负债, 现金及等价物, 总资产, 总负债, 净资产, 应收账款, 存货.
   - Fill the Part 2 §Q1–§Q12 tables in `profiles/<ticker>-<YYYY-MM-DD>.md` in place, preserving existing markdown structure.
   - Every cell carries a page citation in the `**来源:**` line (`年报-YYYY.pdf p.NN`).
   - Cross-check top rows (ROE, 毛利率, 净利率) against 雪球 F10 via web; report any discrepancies inline.

3. Present the filled Part 2 to the user. Ask:
   > `Random-sample 5 cells: given <ROE 2024 = X%>, does 雪球 agree? [all-match / mismatch: <details>]`

4. If ≥ 4/5 agreement → mark all §Q* subsections `已完成`. Otherwise flag the mismatched rows as `需人工` and leave the agreeing rows `已完成`.

5. `by-section` → fall through to standard Step 3 per §Q*.

### Step 5 — 排雷 checklist mode (triggered on §4.5 selection, Part 4)

1. Dispatch ONE `general-purpose` subagent with a compound prompt:
   > For each of the 29 items in Part 4 §4.5 排雷清单, read `data/filings/<ticker>/_extracted/年报-<latest>/text.md` (fallback: the raw PDF) 资产负债表 + 利润表 + 现金流量表 + 财务报表附注. For each item answer `是` / `否` / `不适用` / `需人工`, plus a 1-sentence evidence summary and a 年报 page citation.

   Include the full 29-item list (pull from the §4.5 table already present in the template, which the profile file inherits).

   **唐朝 forensic overlay** (methodology-tang.md §D.1-D.3): flag these high-severity patterns explicitly even if they are not listed verbatim in §4.5:
   - **商誉 / 净资产 > 20%** → 雷区, 未来可能一次性减值.
   - **其他应收款 异常大额** (≥ 10% 流动资产, 或对单一关联方挂账长年) → 关联方占款疑点.
   - **在建工程** 长年不转固定资产 → 挂账操纵折旧.
   - **经营现金流净额 < 50% 净利润** 连续 2 年 → 利润真实性红旗.
   - **生物资产 / 农林渔牧** 主业 → 造假高危区 (獐子岛 style).
   - **管理层道德红旗** — 历史上曾出现虚假陈述 / 违规处罚 / 股东利益输送 → 直接大幅降级.

2. Subagent returns a filled table.

3. Main agent reviews for missing citations and re-dispatches if needed, then writes the filled table to the profile.

4. Compose a **`发现的红旗 summary:`** paragraph (1–2 paragraphs) highlighting any `是` / `需人工` items with context — what the flag is, why it matters for this ticker, and what cross-check to run.

5. User gate — offer only `[accept / edit: <text> / research more: <hint>]`. **`defer` and `skip` are NOT offered.** 排雷 is mandatory; skipping it would invalidate the whole profile.

### Step 6 — Executive summary synthesis (Part 0, 老唐估值法 output)

Triggered when ≥ 80% of sections are `已完成` (compute from the progress map in Step 2).

**Gate-check first**: if §3.pre 三大前提 gate marked any of the three as `假 / 存疑`, abort Step 6 with a banner:
> `❌ 估值前置 checklist failed (三大前提 §<which> = 假/存疑). 无法进入老唐估值法. 请先修复 §3.pre, 或将 Part 0 标记为 "不可估值 — 仅定性研究".`

Otherwise:

1. Offer:
   > `执行摘要 synthesis ready? / Ready to draft Part 0 (老唐估值法)? [yes / not yet]`

2. `yes` → main agent reads the completed sections and drafts Part 0 in Chinese with the following **7-field 结构化 output** (from 老唐估值法, methodology-tang.md §F). Any missing field → section is `进行中`, not `已完成`.

   1. **3 年后 归母净利润 (三档)** — 业务板块拆解 (至少 2 块, 每块列 量 × 价 × 净利率):
      - 乐观: `<N>` 亿元 — 假设 `<具体假设>`
      - 中性: `<N>` 亿元 — base case
      - 悲观: `<N>` 亿元 — 假设 `<具体假设>`
   2. **合理 PE** = `1 / 当前 10y 国债 收益率`. 当前无风险收益率约 3.5% → 合理 PE ≈ 28x (典型区间 25-30; 超出需 justify). **注意**: 合理 PE **不** 随增速调整 — 增速已经反映在 3y 净利润 number 中。
   3. **合理估值** = 中性 3y 净利润 × 合理 PE (± 10% 带宽).
   4. **买点 (Buy point)** = 合理估值 × 0.5 (常规). 高杠杆标的打 7 折, 即 × 0.35 — 必须在字段中说明为何判定高杠杆 (e.g. 有息负债 / 净资产, 经营现金流 / 有息负债).
   5. **卖点 (Sell point)** = `min(合理估值 × 1.5, 当年 净利润 × 50 PE)`. 两 candidate 都列, 取较低者.
   6. **持仓姿态 (discrete)**:
      - `加仓 / 建仓` — 当前市值 < 买点
      - `持有不动 (收工睡觉)` — 买点 ≤ 当前市值 < 卖点
      - `分批清仓` — 当前市值 > 卖点 (触发即卖 1/3; 再涨 10% 卖 1/3; 再涨 10% 清仓)
   7. **Top 3 风险** (ranked) — 来自 §5 风险分析 + §4.5 发现的红旗; 每条 1-2 句 + 触发条件.

   **确信度** aggregate: `**置信度:** 高` if ≥ 60% of sections are 高 AND §3.pre 三大前提 全部 = 真; `中` if mixed; `低` if any block is 未做 OR 任一前提 = 存疑.

   **Labeling**: every Part 0 draft must end with the line `> 本摘要基于 AI 研究 + 用户审阅, 非投资建议. 最近审阅日期 = <today>.`

3. User gate (`[accept / edit / research more]`) → save.

## Language policy

- **Profile content (the `.md` file):** Chinese. Every 填写区, `**引用:**` note, `**管理层口径校核:**`, 总结 paragraph is in Chinese.
- **Operator-facing output** (gate prompts, status summaries, errors): bilingual. Chinese first, English parenthetical when useful. Users operate this skill in both languages.
- **Subagent prompts:** English (the instruction language is English; the data / output directive inside forces Chinese output).
- **Commit messages:** English.

**Methodology reference:** `docs/value-profile/methodology-tang.md` is the canonical 深度分析 framework for this skill (唐朝 / 唐书房). When in doubt about how deep to go, what questions to ask, or how to structure a moat / management / valuation section, consult §B (商业模式) through §G (Moutai seed) of that doc. §H.2 contains prompt-ready copy for subagent dispatch.

## What this skill MUST NOT do

- MUST NOT rewrite sections marked `已完成` without an explicit `--force` flag (not offered in v0).
- MUST NOT fabricate numbers or citations. If a claim is unsourced, write `待补充` plus a one-line reason.
- MUST NOT write profile content in English. Operator lines can be bilingual; the `.md` file is Chinese.
- MUST NOT proceed without 年报 PDFs. Offer the fetcher (Step 1.2) or abort — never a profile with placeholder citations.
- MUST NOT run `git commit`. The user commits.
- MUST NOT call into `src/ah_research/` (the platform data layer is not built yet). Graduation path is in the Graduation section below.
- MUST NOT auto-download PDFs without explicit user confirmation at the Step 1.2 prompt. `no` / `show-command` must leave the filesystem untouched.

## Failure modes & recovery

| Failure | Recovery |
|---|---|
| Subagent output lacking citations | Main agent rewrites any uncited claim as `证据不足, 需人工补充` — NEVER fabricates a citation |
| Trivial `管理层口径校核` line slips through review | Still save if user accepts at gate, but Step 3c should have caught it — treat as skill-regression signal |
| 年报 PDF corrupted / unreadable | Log as `年报-YYYY.pdf (unreadable)` in 引用. Continue with other sources; do not abort the section |
| Profile has merge conflict (two sessions editing concurrently) | Do NOT auto-resolve. Print a warning and ask the user to resolve manually before continuing |
| Subagent quota / rate-limit during PDF reads | Retry once with a narrower page range. If still failing, save a partial section with `待补充` + reason, keep status `进行中` |
| Fetcher fails in Step 1.2 | Fall back to the manual cninfo URL and abort. Do NOT create a broken profile with no filings |
| User picks a section id that doesn't exist in the template | Suggest the closest match (e.g. `1.3` → `§1.3 差异化`) from the section list; do not silently proceed |

## Graduation path

Once Phase 1 of `ah-research` ships and `DataRepository` is available, migrate mechanically:

1. **Step 4 Part 2 bulk** → prefer a subagent that calls `ah_research.DataRepository.get_fundamentals(<ticker>, start=<10y>)` over PDF parsing. Cite fetch params in the `**来源:**` line. Fall back to PDF reads for cells the repository does not cover.
2. **Step 5 排雷 items #12, #23, #28** (pure-numeric items such as 应收/营收 比率, 商誉/净资产, 有息负债/经营现金流) → route through `DataRepository` arithmetic instead of eyeballed PDF reads.
3. **Qualitative sections** (§1–§5, §4.5 qualitative items such as "关联交易异常") continue reading 年报 PDFs. No data source replaces management's own words — not graduated.
4. **`scripts/download_filings.py`** may eventually move to `src/ah_research/integrations/cninfo_client.py` and be exposed as a repository method. Until then the skill shells out to the script.

## Subagent prompt shape reference

Reference template for a Step 3b dispatch. This is what the main agent passes to the `general-purpose` subagent for §1.3 差异化 on 600519.SH; adapt for other sections by swapping the target section block, data-source hint, and page ranges.

```
You are researching §1.3 差异化 for ticker 600519.SH (贵州茅台 / Kweichow Moutai, SH exchange).
Report date: 2026-04-28.

本节目标 (from template):
回答"公司解决了客户什么样的别人没能解决的需求和痛点"。必须具体到产品 / 场景, 不要抽象。

指导问题:
- 客户在哪个场景下选择公司产品而非竞品?
- 切换成本在哪里? (品牌 / 渠道 / 工艺 / 关系 / 价格带)
- 差异化可持续多久? 什么会打破?

数据源 hint: 年报 第三节 "公司业务概要"; 招股说明书 "业务与技术"。

PDFs to read (use the Read tool, target the stated page ranges first):
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/年报-2024.pdf pages 8-35
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/年报-2023.pdf pages 8-35
- /Users/brian_huang/repos/ah-research-vp/data/filings/600519.SH/招股说明书.pdf pages 40-80

Adjacent context (already-filled sections):
§1.1 公司核心资产、主营产品和服务: <inlined content>
§1.2 公司客户: <inlined content>

Output requirements:
1. Respond in **Chinese only**. No English prose.
2. Fill the 填写区 for §1.3 with 3-6 specific claims about 茅台 differentiation. 茅台镇 水源, 12987 工艺, 基酒 5y 陈化, 品牌 价格带, 渠道 经销商网 are candidates — use whichever is load-bearing, cite 年报 page for each.
3. Every claim cites either 年报-YYYY.pdf p.NN or a web URL. Unverifiable claims → `证据不足, 需人工补充`.
4. Populate **管理层口径校核:** noting where 年报 framing differs from 研报 / 价盘 / 媒体. A trivial "年报 says X, we agree" is a rejection.
5. Set **置信度:** 高 / 中 / 低 based on citation density and spin-check depth.
6. No hedging platitudes ("公司有较强的竞争力"). Ticker-specific evidence only.

Return the fully-formed section block (heading + 填写区 + 引用 + 置信度 + 管理层口径校核).
```
