# Value Profile Skill — Design Spec

**Date:** 2026-04-28
**Status:** Draft v2 — open questions resolved; pending user re-approval
**Owner:** Brian Huang
**Parent project:** `ah-research` (see `docs/superpowers/specs/2026-04-28-ah-research-platform-design.md`)
**Scope choice:** Option C (build + dogfood), variant C1 (prompt/template workflow, no Python code in `ah_research/`)
**First dogfood target:** 600519.SH (贵州茅台 Kweichow Moutai)

## 0. Revision notes (v2)

Changes from v1 after user review of open questions:

- **年报 + 招股说明书 are first-class, first-hand sources** — mandatory to read, not a v1-deferred option. The user's framing: annual reports can contain management spin, but they are the *first-hand* record. Cross-checking against 研报 / 新闻 / 短报告 handles the spin.
- **定性分析 > 定量分析 in priority.** First-run sequence reordered: Part 1 qualitative first, Part 2 quantitative second. The user's framework already prescribes this order; v1 inverted it as an optimization and that was wrong.
- **Profile output is in Chinese.** Skill-user interaction (the accept/edit/defer gates) can be bilingual.
- **Everything is committed to the repo.** No gitignore for `profiles/` or `data/filings/`.

## 1. Purpose

Operationalize the user's 价值投资个股研究 profile framework as a **repeatable, section-by-section research workflow** driven by a Claude Code skill, producing a durable per-ticker markdown profile in Chinese.

The framework is far richer than the quantitative dossier already planned for `ah-research` (`analysis/company.py::company_dossier`) — it covers 商业模式, 护城河, 管理质量与企业文化, 风险, 买入/持有清单, and a 29-item 排雷检查清单. Most of this is qualitative AI+human judgment grounded in first-hand filings (年报, 招股说明书), not data queries. This skill is the right home for that work; `ah_research/` remains the data/quant layer.

The immediate goal is NOT a polished system but a fast feedback loop: does the framework, operated by AI + user + annual reports, produce a profile the user would actually act on? That question is answered by running it once, end-to-end, on 600519.SH.

## 2. Non-goals / YAGNI

- No Python code in `src/ah_research/`. No new module, no new tool. The skill operates entirely above the library.
- No automated fundamentals pipeline. The quantitative tables are filled by AI reading 年报 PDFs + web research + user sanity-check; they will be retrofitted to `DataRepository` once Phase 1 of the platform ships.
- No automated PDF *acquisition*. User downloads 年报 / 招股说明书 PDFs manually (巨潮资讯网 for A-shares, HKEX for HK) and drops them into `data/filings/<ticker>/`. The skill reads them; it does not fetch them. (A future version can add an automated fetcher; for v0 this is out of scope.)
- No HTML/PDF *rendering* of output. Final format is markdown; GitHub renders it.
- No CLI wrapper, no MCP surface, no Streamlit. Invocation is a slash command inside a Claude Code session.
- No automated tests. Validation is qualitative: does the first profile read as sharp-and-specific or generic-AI-slop?
- No multi-ticker batch mode, no watchlist integration, no peer-comparison cross-linking, no notifications. One ticker, one session's worth of structured work, save to file.
- No opinion about source-of-truth for share price / 历史 valuation bands — those cells stay `TBD (graduate to ah_research/DataRepository in v1)` until the platform's data layer exists.

**Explicitly IN scope** (changed from v1):

- **Reading 年报 / 招股说明书 PDFs.** Claude Code's `Read` tool supports PDFs with page-range slicing. The skill MUST use this to read filings for every qualitative section. These are the authoritative first-hand documents.

## 3. Artifacts

| Path | Role | Committed? |
|---|---|---|
| `docs/value-profile/template-zh.md` | Reusable framework template, all sections in Chinese | Yes |
| `.claude/skills/value-profile/SKILL.md` | Claude Code skill definition + operational instructions | Yes |
| `data/filings/<ticker>/` | User-placed 年报, 招股说明书, 研报 PDFs | Yes (incl. PDFs) |
| `data/filings/README.md` | Naming conventions + where to download each filing | Yes |
| `profiles/` | Directory holding per-ticker profile outputs | Yes (dir) |
| `profiles/600519.SH-2026-04-28.md` | First dogfood output (in Chinese) | Yes (after user approval of contents) |

### Filings directory layout

```
data/filings/
├── README.md                     # where to get filings + naming conventions
└── 600519.SH/
    ├── 年报-2024.pdf              # most recent — read first
    ├── 年报-2023.pdf
    ├── 年报-2022.pdf
    ├── 年报-2021.pdf
    ├── 年报-2020.pdf              # 5y default; more if needed
    ├── 招股说明书.pdf              # once, at IPO (for Moutai: 2001)
    └── 研报/                      # optional卖方/买方研报, any names
        ├── 中金-茅台深度.pdf
        └── 天风-白酒行业展望.pdf
```

Naming is Chinese, human-readable, and date-suffixed where a year disambiguates.

### On committing profiles + filings + PDFs

Profiles contain the user's opinions, conviction levels, and buy/sell thresholds. Committing creates a reviewable history and makes framework outputs inspectable.

PDFs are public disclosures — no IP concern. Committing them makes profiles reproducible: anyone who clones the repo can re-derive the profile from the same source material. File sizes are acceptable (~5-30 MB per 年报; ~100-300 MB for 10y of a name like Moutai — larger than typical code commits but not abnormal for a research repo). If this later becomes a problem, `git-lfs` is the mitigation; not worth doing upfront.

Explicitly NOT introduced:
- No changes under `src/ah_research/`.
- No changes to the existing Phase 0/1 plan.
- No changes to `pyproject.toml`.

## 4. Template (`docs/value-profile/template-zh.md`)

### Structure

Top-level parts map 1-to-1 to the user's original document to preserve the mental model. All content in Chinese.

```
Part 0 — 封面 / 执行摘要
Part 1 — 定性分析 (PRIMARY — do first, per user's framework)
  §1 商业模式 (7 subsections)
  §2 成长空间/天花板 (6 subsections)
  §3 护城河 (10 subsections)
  §4 管理质量与企业文化 (7 subsections)
  §5 风险分析 (5 subsections)
Part 2 — 定量分析 — 10-year tables (grounding for Part 1)
  §1 盈利分析 §2 成长能力 §3 运营能力 §4 偿债能力
  §5 现金流 §6 资产负债表 §7 利润表 §8 上下游话语权 §9 总结
Part 3 — 未来
Part 4 — 买入阶段清单 (incl. 排雷清单)
Part 5 — 持有阶段清单
```

All section titles and filled content are in Chinese. The template file itself may carry short English HTML comments for operator hints (`<!-- hint -->`) but rendered content is Chinese.

### Per-section scaffolding

Every section carries:

1. **Heading** — e.g. `### §1.3 差异化：解决了客户什么样的别人没能解决的需求和痛点`.
2. **Prompt block** (Chinese) — the user's original guiding questions, restated so the AI can answer them directly.
3. **Data-source hint** (Chinese HTML comment) — places to look, **年报 and 招股说明书 listed first**:
   `<!-- 数据源: 年报"管理层讨论与分析"章节; 年报"主营业务分产品"明细; 招股说明书"业务与技术"; 雪球 F10; 行业研究报告; 新浪财经 / 财新 新闻 -->`
4. **Answer area** (Chinese) — where the AI's draft lands, with inline citations.
5. **Citations block** — `**引用:**` list, every item either:
   - `年报-2023.pdf p.47` (page number required for PDFs)
   - `[东方财富 F10](https://emweb.eastmoney.com/pc_hsf10/pages/index.html?type=web&code=SH600519)`
   - `[研报: 中金-茅台深度]` (local PDF reference)
6. **Confidence field** — `**置信度:** 高 / 中 / 低 / 未做 / 已跳过`.
7. **Spin-check field** — `**管理层口径校核:**` (for sections where 年报 is the primary source) — a one-line note on where management's framing may differ from reality, and how we cross-checked (e.g. "年报强调 i茅台 直销增长, 但价盘端显示批价下跌 → 用 新浪财经 批价数据 交叉验证").

### Quantitative table skeletons

Part 2 tables are pre-laid out with row labels and empty year columns. Each table carries a `<!-- 取数要求 -->` comment listing the raw line items the filler needs to fetch (so AI research targets the right 年报 section), and a `**来源:**` line that the filler must populate with citation URLs *and* specific 年报 page numbers for the 10 most recent years.

### Executive Summary (Part 0)

Lives at the top of the file but is filled **last**, after the rest of the framework is walked. Contents (in Chinese):

- 3-bullet 投资论点 (是否买 / 什么价位买 / 为什么).
- 当前价位 vs 3 年后合理市值区间.
- Top 3 风险 排名.
- 确信度 (高/中/低) 和 建议仓位区间.
- 最近审阅日期.

### Size

Expected ~300-500 empty lines; ~1200-2000 lines after filling for a name like Moutai with 5y of 年报 citations.

## 5. Skill (`.claude/skills/value-profile/SKILL.md`)

### Frontmatter

```yaml
---
name: value-profile
description: Walk a user through filling out a 价值投资 profile for a single stock (A-shares / HK). Reads 年报 / 招股说明书 PDFs from data/filings/, gathers qualitative + quantitative research section-by-section, writes Chinese-language profile to profiles/<ticker>-<date>.md as it goes. Trigger on "/value-profile <ticker>" or "研究 股票 <ticker>" or "fill out profile for <ticker>".
---
```

### Invocation contract

- Primary: `/value-profile <ticker>` where ticker is in `<code>.<exchange>` form (`600519.SH`, `0700.HK`).
- Optional: `--section <id>` (e.g. `--section 1.3`) to jump to one section.
- Optional: `--resume` to load an existing partial profile and continue where the progress map says 进行中 / 未做.

### Behavior (loop)

1. **Bootstrap + filings audit**
   - Validate ticker format.
   - Check `data/filings/<ticker>/`:
     - If the directory is missing or contains <2 年报 PDFs, print a blocking message (in both languages): "缺少年报 PDF。请从巨潮资讯网 http://www.cninfo.com.cn 下载最近 5 年年报到 `data/filings/<ticker>/`，文件命名 `年报-YYYY.pdf`。若公司 IPO 时间不久，也请下载招股说明书 `招股说明书.pdf`。完成后重新运行。"
     - Otherwise, list what's available and note what's missing (e.g. "Found 5 年报 (2020-2024). 招股说明书 missing — for older names like 600519.SH, IPO was 2001, so it exists; for newer IPOs, this is a blocker for Part 1 §1 if not available.").
   - Derive output path `profiles/<ticker>-<YYYY-MM-DD>.md`. If today's file exists, load it. If a file for a prior date exists, prompt user: resume-rename or start-fresh.
   - If output path doesn't exist, copy `docs/value-profile/template-zh.md` → output path. Fill Part 0 header (symbol, exchange, report_date, researcher).

2. **Progress map**
   - Parse the output file, extract each section's `**置信度:**` line, build a map: `{section_id: status}`.
   - Render a short summary: "已完成 4/38 节 (§0, §1.1, §1.2, §1.6). 下一节未做: §1.3 差异化。继续? 或选择特定节? [continue / pick]".

3. **Section worker (the inner loop)**
   For the chosen section:
   a. **PDF pre-read.** Based on the section's data-source hint, the main agent determines which 年报 section(s) are most relevant (e.g. §1.1 主营产品 → 年报"主营业务分行业、分产品、分地区"表; §3 护城河 → "管理层讨论与分析"; §4 管理 → "公司治理" + "董事、监事、高级管理人员"; 排雷 → "财务报表附注"重点项目).
   b. **Scoped research dispatch.** Call the `general-purpose` subagent with a prompt that contains:
      - The section heading + prompt block (from the template, in Chinese).
      - The data-source hints (年报 page hints first, web second).
      - Paths to the relevant 年报 PDFs in `data/filings/<ticker>/` and instruction to read specific pages via the `Read` tool.
      - Ticker, company name, exchange, report_date.
      - Any already-filled adjacent sections as context.
      - **Language directive:** respond in Chinese. Cite every fact with either `年报-YYYY.pdf p.NN` or a web URL. Flag what couldn't be verified. Ban hedging platitudes: "若证据不足, 直接写 '证据不足, 需人工补充'。"
      - **Spin check directive** (for qualitative sections): where 年报 is the primary source, note in the spin-check field whether management's framing aligns with or conflicts with external signals (研报 / 价盘 / 媒体).
   c. **Main-agent review.** Read subagent's output, critique against the framework's guiding questions, write a Chinese draft that lands in the user's file. Populate 引用, 置信度, 管理层口径校核 fields.
   d. **User gate.** Present the draft (in Chinese, with English operator notes if useful). User responds:
      - `accept` — 已完成, save, next.
      - `edit: <text>` — 应用 user edits, save.
      - `defer` — 未做, save nothing.
      - `skip` — 已跳过 (e.g. AH premium for A-only name).
      - `research more: <提示>` — narrower research subagent with hint, loop back to (c).
   e. **Save.** Write section block to profile file immediately.

4. **Part 2 (quantitative) — after Part 1 is substantially done**
   When entering Part 2, offer the user a bulk-dispatch path: one subagent reads 年报 财务报表 sections across 10y of PDFs and pulls the raw line items (净利润, 营业收入, ROE, 毛利率, etc.), fills all Part 2 tables, cross-checks headline rows against 雪球 F10. Every table cell gets a 年报 page citation. User sanity-checks.

5. **Part 4 (排雷清单) checklist mode**
   When entering the 排雷 sub-section of Part 4 买入清单, the skill enters "checklist mode":
   - Walk the 29 items sequentially.
   - For each item, dispatch a tight yes/no research query that reads the latest 年报 资产负债表 + 财务报表附注 (e.g. "600519.SH 是否存贷双高? 读 `年报-2024.pdf` 货币资金 + 短期借款 + 长期借款, 算比值。答 是/否 + 数字 + 引用页码.")
   - Record: `是 / 否 / 不适用 / 需人工`. Don't block on any single item.
   - End with a rolled-up "发现的红旗" summary.

6. **Executive summary synthesis**
   Only offered when ≥80% of sections are 已完成. Pulls thesis/risks/price bullets, drafts Part 0 in Chinese, user reviews.

### What the skill must NOT do

- Must not rewrite sections the user has already marked 已完成 without explicit instruction.
- Must not fabricate numbers or citations. If a number can't be sourced from 年报 or web, write `待补充` with the reason.
- Must not write output sections in English. Operator-facing status lines can be bilingual, but profile content is Chinese.
- Must not proceed without 年报 PDFs — block with a clear download instruction.
- Must not run `git commit`. User handles commits.
- Must not auto-run `company_dossier` from `ah_research/` (not built yet — this contract tightens when Phase 1 lands and the skill is upgraded).

## 6. First-run plan (600519.SH 贵州茅台)

**Prerequisite:** user downloads PDFs to `data/filings/600519.SH/`:
- `年报-2024.pdf` through `年报-2020.pdf` (5y, from 巨潮资讯网 cninfo.com.cn)
- `招股说明书.pdf` (Moutai IPO 2001)
- Optional: 2-3 卖方研报 (中金 / 中信 / 天风 / 东吴 depth reports on baijiu)

**Goal:** one complete-or-near-complete profile by end of session(s), in Chinese, used to judge whether the framework-as-skill produces sharp research.

**Sequence** (re-ordered from v1: Part 1 qualitative first, per user's framework priority):

1. `/value-profile 600519.SH` — skill validates filings, creates `profiles/600519.SH-2026-04-28.md` from template, fills header.
2. **Part 1 §1 商业模式** (60-75 min — now first because qualitative understanding grounds everything else): 产品 (茅台酒 vs 系列酒 拆分, from 年报"主营业务分产品"), 客户 (经销 vs 直销 i茅台 比例, from 年报 "销售模式"), 差异化 (茅台镇 赤水河 水源, 12987 工艺, 基酒产能约束, 品牌 — from 年报 + 招股说明书"核心竞争力"), 盈利模式, 生意特性, 现金流 (预收款 / 合同负债 from 资产负债表), 已知优秀模式 (品牌溢价制造商).
3. **Part 1 §2 成长空间** (30 min): 高端白酒行业空间, 提价历史 (从年报逐年提价事件), 直销比例提升的毛利贡献, 系列酒天花板.
4. **Part 1 §3 护城河** (60-90 min — the moat section): 品牌 / 茅台镇地理垄断 / 基酒产能限制 (年报 生产能力 章节) / 经销商体系 / 波特五力 / ROE-ROIC-杜邦 / 毛利率分解. Cross-check 年报 management claims ("品牌力持续提升") against 价盘 / 渠道 / 分销商调研.
5. **Part 1 §4 管理质量与企业文化** (60-75 min — the hardest): 国企背景, 贵州省国资委持股, 历任董事长更替 (高卫东 反腐 → 丁雄军 → 张德芹), 价格管控 vs 市场化, 分红政策, 一言堂 vs 集体决策 / 国企特性 对企业文化影响. Heavy cross-checking: 年报 会说"公司治理规范"; 新闻 / 财新 / 监管处罚记录 会呈现一个真实画面. Expect to push back on AI output hard.
6. **Part 1 §5 风险分析** (30 min): 高端白酒需求周期 (反腐 / 政务消费占比下降 / 商务消费回落), 年轻人白酒渗透率下降, 价盘风险 (飞天 批价), 国企管理层更替的不确定性, 税率政策.
7. **Part 2 定量分析** (30-45 min — now second, grounds quantitatively what Part 1 judged qualitatively): 10y 年报 批量拉取 → ROE / ROA / 毛利率 / 净利率 / 营收增速 / 现金流 / 资产负债 / 周转率. 每格都带 `年报-YYYY.pdf p.NN` 引用. 用户抽检 头部行 (ROE, 净利率) 对比 雪球 F10.
8. **Part 4 买入清单 + 排雷清单** (90 min): 当前 PE / PB / 股息率 vs 历史 band (web), 3 年后合理市值测算, 29-item 排雷 逐项 (从 年报 财务报表附注 读). Moutai 应该 通过 几乎所有 排雷 项 — 这也 验证 清单 的 有效性 (若 一个 巨型 SOE 看什么 都 clean, 清单 没做工; 预期 会有 "第一大股东持股 高" / "国企补贴 / 非经常损益" / "关联交易 多" 等 合理 concerns).
9. **Part 3 未来 + Part 5 持有清单** (30 min): 短, 模板化.
10. **Part 0 执行摘要** last (15 min).

**Time:** ~7-8 focused hours across likely 2-3 sessions (up from v1's 6 hours due to mandatory PDF reading).

### Go/no-go criteria after first run

The skill graduates from "first run" to "real tool" if:

1. The §3 护城河 section is specific to Moutai — cites specific 年报 pages naming 茅台镇 水源, 12987 工艺, 基酒 5-year cycle, 品牌 价格带 — not a generic "strong brand, good ROE" writeup.
2. The §4 管理 section honestly engages with the SOE dynamic and 高卫东 反腐 事件, using both 年报's framing AND external sources to triangulate. Spin-check fields are filled and say something non-trivial.
3. The 29-item 排雷 checklist surfaces at least 2-3 legitimate concerns (expected: 第一大股东持股 >60%, 国企补贴 / 非经常损益 / 关联交易) and doesn't flag everything as fine.
4. Every quantitative table cell has a `年报-YYYY.pdf p.NN` citation. User random-samples 5 cells against 雪球 F10; agreement rate ≥ 4/5.
5. The user can, using the resulting profile alone, answer "would I buy at today's price, in what size, what would make me sell?" — and the answer feels defensible.

If any of (1)-(4) fail, the skill's section-worker prompts (§5.3b) need strengthening before running a second name.

## 7. Relationship to existing `ah-research` platform

This skill is a **workflow artifact**, not a platform component. It is not on the Phase 0→6 critical path of `docs/superpowers/specs/2026-04-28-ah-research-platform-design.md`.

Graduation path (post-Phase 1 of ah-research):

- Part 2 quantitative tables get a new filler path: subagent calls `ah_research.DataRepository.get_fundamentals(asof=...)` via a tool wrapper, instead of parsing PDFs. Point-in-time correctness for free. PDF reading remains for qualitative cross-reference.
- Current-price / 历史 PE-PB band / 股息率 cells get the same treatment via `get_prices` + valuation-band analysis.
- 行业 peer comparison 数据 (§1-2, §3.5, §3.7) comes from `DataRepository` sector queries.
- **Qualitative sections keep reading 年报 PDFs** — no data source replaces management's own words, and no `DataRepository` call answers "is the moat durable?"

Nothing in the skill contract changes; the internal research prompts just grow a new, preferred data path for the numbers.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Generic AI output — moat section reads like a textbook rather than Moutai-specific | Section-worker prompts force 年报 page citations + ban hedging language; user rejects and asks for `research more` until specifics appear |
| **Management spin in 年报** — 年报 is first-hand but NOT objective; management choose framing and omit inconvenient facts | Every qualitative section has a `管理层口径校核` field requiring cross-check vs 研报 / 财经新闻 / 监管披露 / 价盘数据. Spin-check is part of the go/no-go criterion for §4 管理 |
| Quant tables drift from reality (user transcription / AI misread of PDF) | Every Part 2 cell carries a `年报-YYYY.pdf p.NN` citation. User random-samples 5 cells against 雪球 F10; ≥4/5 agreement required |
| Profile staleness (a profile written today is a snapshot) | Date-stamped filename; framework encourages annual re-run; a future `--diff` mode can surface changes since last profile |
| Scope creep — skill grows toward being the ah-research platform | Hard non-goal: no Python in `src/`. Any request wanting structured data access is deferred to post-Phase-1 |
| User corrections get lost if the skill rewrites a section | Skill must never rewrite sections marked 已完成 without explicit instruction; save-after-each-section keeps partial state durable |
| Sensitive content in committed profiles (political / SOE commentary) | Profiles live under the repo; if the repo is ever pushed publicly, move `profiles/` out or gitignore. Default is commit |
| Skill's 排雷清单 produces false negatives on a real fraud case | Accepted for v0 — the checklist is a prompt, not a detector; its job is to force the user to ask each question. Future version can hook `DataRepository` once built |
| **PDF reading cost / latency** — each 年报 is 150-400 pages; `Read` tool's 20-page-per-call limit means ~10-20 calls per 年报 per section | The main agent targets specific sections by table-of-contents (年报 always has a standard ToC); avoid full-PDF reads. Budget ~100 Read calls for a full profile |
| **Repo bloat** from committed 年报 PDFs (5y × ~20MB × many tickers = easily >1GB over time) | Acceptable for now. Graduate to `git-lfs` if a single clone exceeds ~500MB |
| User hasn't downloaded filings — skill blocks | Bootstrap step (§5.1) prints a clear download URL and naming convention; this is expected, not a bug |

## 9. Success criteria

1. `/value-profile 600519.SH` produces a 1200+ line Chinese-language markdown file under `profiles/` in ≤8 focused hours of operator time.
2. The file covers ≥80% of framework sections with 置信度 ≥ 中.
3. Every quantitative table cell has a 年报 page citation; random-sample ≥4/5 agreement vs 雪球.
4. §4 管理 section has a non-trivial `管理层口径校核` line demonstrating real cross-source work (not just "年报 claims X, we agree X").
5. The go/no-go criteria in §6 are all met.
6. The user would use this file as input to a real buy / no-buy / sizing decision on Moutai.
7. Running on a **second, harder** name reveals the skill's true cost curve — that's the question the second run answers.

## 10. Open questions — resolved

| # | Question | Resolution |
|---|---|---|
| 1 | Profile commit policy | **Commit everything to repo** (profiles + 年报 PDFs + 研报). Git-lfs deferred until size becomes a real problem. |
| 2 | Language — interaction vs output | **Output in Chinese** (profile content). **Interaction bilingual** (operator gates, status lines). |
| 3 | Next ticker after Moutai | **Deferred** — decide after first run, using the "smaller / less-covered" heuristic (a mid-cap A-share with <5 沿海 卖方研报 coverage would stress-test the skill most). |
| 4 | `research more` fallback scope — PDF reading or web-only? | **PDF reading is primary, not a fallback.** 年报 + 招股说明书 are first-hand sources and must be read for every qualitative section. Cross-check against web (研报, 财新, 新浪财经) for the spin-check. |

---

**Next step after user re-approval:** invoke the `superpowers:writing-plans` skill to produce a step-by-step implementation plan covering: (a) downloading Moutai 年报 PDFs to `data/filings/600519.SH/`, (b) building `docs/value-profile/template-zh.md`, (c) building `.claude/skills/value-profile/SKILL.md`, and (d) running the first profile session.
