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

#### 3a. PDF pre-read targeting

Based on the section's `<!-- 数据源: ... -->` hint (parsed out of the template file in the profile), decide which 年报 pages to pull. 年报 ToC is highly standardized, so use this mapping as a starting point and refine from the hint:

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

#### 3b. Scoped research dispatch

Dispatch ONE `general-purpose` subagent. The prompt is in English (subagent instruction language) but demands Chinese output. Include:

- The section heading + the template's 本节目标 / 指导问题 prompt block.
- The parsed `<!-- 数据源: ... -->` hint.
- Absolute paths to the relevant 年报 PDFs in `data/filings/<ticker>/` and the instructed page ranges (from 3a).
- Ticker, Chinese company name, exchange, report_date.
- Already-filled adjacent sections as context (e.g. for §1.3 pass §1.1 and §1.2 content, for §3.x pass §1 商业模式).
- **Language directive:** respond in Chinese. Every fact cites either `年报-YYYY.pdf p.NN` or a web URL. Flag anything unverifiable as `证据不足, 需人工补充`. **No hedging platitudes** (ban phrases like "公司具有较强的竞争力", "行业前景广阔" without evidence).
- **Spin-check directive** (ONLY for Part 1 §1–§5 qualitative sections): populate the `管理层口径校核` field noting where 年报 framing may differ from external signals (研报 / 价盘 / 媒体报道 / 监管披露). A trivial "年报 says X, we agree X" is a rejection.

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
   > For each of the 29 items in Part 4 §4.5 排雷清单, read `data/filings/<ticker>/年报-<latest>.pdf` 资产负债表 + 利润表 + 现金流量表 + 财务报表附注. For each item answer `是` / `否` / `不适用` / `需人工`, plus a 1-sentence evidence summary and a 年报 page citation.

   Include the full 29-item list (pull from the §4.5 table already present in the template, which the profile file inherits).

2. Subagent returns a filled table.

3. Main agent reviews for missing citations and re-dispatches if needed, then writes the filled table to the profile.

4. Compose a **`发现的红旗 summary:`** paragraph (1–2 paragraphs) highlighting any `是` / `需人工` items with context — what the flag is, why it matters for this ticker, and what cross-check to run.

5. User gate — offer only `[accept / edit: <text> / research more: <hint>]`. **`defer` and `skip` are NOT offered.** 排雷 is mandatory; skipping it would invalidate the whole profile.

### Step 6 — Executive summary synthesis (Part 0)

Triggered when ≥ 80% of sections are `已完成` (compute from the progress map in Step 2).

1. Offer:
   > `执行摘要 synthesis ready? / Ready to draft Part 0? [yes / not yet]`

2. `yes` → main agent reads the completed sections and extracts:
   - **3-bullet 投资论点** from §1 商业模式 + §3 护城河 + §4 管理 (是否买 / 什么价位 / 为什么).
   - **估值** (current PE / PB / 股息率 / 3y 合理市值) from Part 4 §4.1–§4.3.
   - **Top 3 风险** from §5 风险分析 + §4.5 发现的红旗.
   - **确信度** aggregated from the 置信度 stats: `高` if ≥ 60% of sections are 高; `中` if mixed; `低` if any block is 未做.

   Draft Part 0 in Chinese. Include `最近审阅日期 = today`.

3. User gate (`[accept / edit / research more]`) → save.

## Language policy

- **Profile content (the `.md` file):** Chinese. Every 填写区, `**引用:**` note, `**管理层口径校核:**`, 总结 paragraph is in Chinese.
- **Operator-facing output** (gate prompts, status summaries, errors): bilingual. Chinese first, English parenthetical when useful. Users operate this skill in both languages.
- **Subagent prompts:** English (the instruction language is English; the data / output directive inside forces Chinese output).
- **Commit messages:** English.

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
