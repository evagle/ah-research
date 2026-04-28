# Value Profile Skill — Design Spec

**Date:** 2026-04-28
**Status:** Draft v3 — automated PDF fetcher added; pending user re-approval
**Owner:** Brian Huang
**Parent project:** `ah-research` (see `docs/superpowers/specs/2026-04-28-ah-research-platform-design.md`)
**Scope choice:** Option C (build + dogfood), variant C1 (prompt/template workflow, no Python code in `ah_research/`)
**First dogfood target:** 600519.SH (贵州茅台 Kweichow Moutai)

## 0. Revision notes

**v3** changes (during plan execution):

- **Automated PDF fetcher added.** New `scripts/download_filings.py` fetches 年报 + 招股说明书 from 巨潮资讯网 (cninfo) via direct POST API — no `requests`/`akshare` deps, only stdlib + `tenacity` (already planned). Replaces the manual-download step. Lives in `scripts/` so the C1 "no Python in `src/ah_research/`" constraint is preserved.
- **Skill bootstrap behavior updated.** When `data/filings/<ticker>/` is missing PDFs, the skill now OFFERS to run the fetcher automatically (bilingual prompt) instead of blocking with download instructions.
- **Worktree-based execution.** Value-profile work moved to `/Users/brian_huang/repos/ah-research-vp` on branch `feat/value-profile`, branched from current HEAD of `feat/phase-0-1-scaffold`. The other agent continuing the Phase 0/1 platform scaffold stays on the original branch without interference.

**v2** changes from v1 after user review of open questions:

- **年报 + 招股说明书 are first-class, first-hand sources** — mandatory to read. Annual reports can contain management spin but are the *first-hand* record. Cross-checking against 研报 / 新闻 / 短报告 handles the spin.
- **定性分析 > 定量分析 in priority.** First-run sequence reordered: Part 1 qualitative first, Part 2 quantitative second.
- **Profile output is in Chinese.** Skill-user interaction (the accept/edit/defer gates) can be bilingual.
- **Everything is committed to the repo.** No gitignore for `profiles/` or `data/filings/`.

## 1. Purpose

Operationalize the user's 价值投资个股研究 profile framework as a **repeatable, section-by-section research workflow** driven by a Claude Code skill, producing a durable per-ticker markdown profile in Chinese.

The framework is far richer than the quantitative dossier already planned for `ah-research` (`analysis/company.py::company_dossier`) — it covers 商业模式, 护城河, 管理质量与企业文化, 风险, 买入/持有清单, and a 29-item 排雷检查清单. Most of this is qualitative AI+human judgment grounded in first-hand filings (年报, 招股说明书), not data queries. This skill is the right home for that work; `ah_research/` remains the data/quant layer.

The immediate goal is NOT a polished system but a fast feedback loop: does the framework, operated by AI + user + annual reports, produce a profile the user would actually act on? That question is answered by running it once, end-to-end, on 600519.SH.

## 2. Non-goals / YAGNI

- No Python code in `src/ah_research/`. No new module, no new tool. The skill operates entirely above the library. (The filings fetcher lives in `scripts/`, not `src/`.)
- No automated fundamentals pipeline. The quantitative tables are filled by AI reading 年报 PDFs + web research + user sanity-check; they will be retrofitted to `DataRepository` once Phase 1 of the platform ships.
- No HTML/PDF *rendering* of output. Final format is markdown; GitHub renders it.
- No CLI wrapper for the skill itself, no MCP surface, no Streamlit. Invocation is a slash command inside a Claude Code session. (The filings fetcher is a standalone CLI — that's fine, it's infrastructure.)
- No automated tests for the skill or template. Fetcher DOES have tests (it's real code with failure modes — network, schema drift, partial failures). Skill + template validation is qualitative: does the first profile read as sharp-and-specific or generic-AI-slop?
- No multi-ticker batch mode for the skill itself, no watchlist integration, no peer-comparison cross-linking, no notifications. (The fetcher naturally supports any A-share ticker.)
- No opinion about source-of-truth for share price / 历史 valuation bands — those cells stay `TBD (graduate to ah_research/DataRepository in v1)` until the platform's data layer exists.
- No HK-share fetcher in v0 — HKEX has a different endpoint and is separate work.

**Explicitly IN scope** (changed from v1 in v2+v3):

- **Reading 年报 / 招股说明书 PDFs.** Claude Code's `Read` tool supports PDFs with page-range slicing. The skill MUST use this to read filings for every qualitative section. These are the authoritative first-hand documents.
- **Fetching 年报 / 招股说明书 PDFs** from 巨潮资讯网 via `scripts/download_filings.py` (v3 addition). Direct cninfo API POST, idempotent, rate-limited.

## 3. Artifacts

| Path | Role | Committed? |
|---|---|---|
| `docs/value-profile/template-zh.md` | Reusable framework template, all sections in Chinese | Yes |
| `.claude/skills/value-profile/SKILL.md` | Claude Code skill definition + operational instructions | Yes |
| `scripts/download_filings.py` | Python CLI: fetch 年报 + 招股说明书 from cninfo for a ticker (v3 addition) | Yes |
| `tests/test_download_filings.py` | pytest — uses recorded cninfo JSON fixtures (v3 addition) | Yes |
| `tests/fixtures/cninfo/` | Recorded API responses for test replay (v3 addition) | Yes |
| `data/filings/<ticker>/` | 年报, 招股说明书, 研报 PDFs (fetched or user-placed) | Yes (incl. PDFs) |
| `data/filings/README.md` | Naming conventions + fetcher usage | Yes |
| `profiles/` | Directory holding per-ticker profile outputs | Yes (dir) |
| `profiles/600519.SH-2026-04-28.md` | First dogfood output (in Chinese) | Yes (after user approval of contents) |

### Filings directory layout

```
data/filings/
├── README.md                     # fetcher usage + naming conventions
└── 600519.SH/
    ├── 年报-2024.pdf              # most recent — read first
    ├── 年报-2023.pdf
    ├── 年报-2022.pdf
    ├── 年报-2021.pdf
    ├── 年报-2020.pdf              # 5y default; more if needed
    ├── 招股说明书.pdf              # once, at IPO (for Moutai: 2001)
    └── 研报/                      # optional 卖方/买方研报, any names
        ├── 中金-茅台深度.pdf
        └── 天风-白酒行业展望.pdf
```

Naming is Chinese, human-readable, and date-suffixed where a year disambiguates. **The fetcher writes to exactly this layout.**

### Filings fetcher (`scripts/download_filings.py`) — contract

**CLI:**
```bash
python scripts/download_filings.py <ticker> [--years N] [--include-prospectus] [--out <dir>]
```

- `<ticker>` — `<code>.<exchange>` form (e.g. `600519.SH`, `000001.SZ`).
- `--years N` (default 5) — fetch the most recent N 年报.
- `--include-prospectus` (default off) — fetch 招股说明书.
- `--out <dir>` (default `data/filings/<ticker>/`) — output directory.

**Behavior:**
1. Resolve ticker to `orgId` via cninfo stock lookup.
2. POST to cninfo announcement search API, filter for 年报 category, exclude 摘要 / 修订版 / 更正版 by title match.
3. For each announcement, download PDF from `static.cninfo.com.cn/<adjunctUrl>`.
4. Save as `年报-YYYY.pdf` (YYYY = 会计年度 end year).
5. If `--include-prospectus`: query for 首次公开发行股票招股说明书, save as `招股说明书.pdf`.
6. Rate-limited (≥1 sec between requests), tenacity retries on 429 / 5xx / transient network errors.
7. Idempotent — skip if target file exists and size > 100KB.
8. Exit 0 on full success; exit 1 with summary on partial failure (never abort on first error).

**Dependencies:** stdlib (`urllib.request`, `json`, `argparse`, `pathlib`, `time`) + `tenacity` (in `pyproject.toml` already). **No `requests`, no `akshare`, no browser automation.**

**Failure modes:**
- cninfo schema drift: raise `FetchSchemaError` with captured response; user re-runs after fetcher update.
- Rate-limit / 429: tenacity retries with exponential backoff.
- PDF 4xx on an individual file: skip, log, continue; report at end.

### On committing profiles + filings + PDFs

Profiles contain the user's opinions, conviction levels, and buy/sell thresholds. Committing creates reviewable history.

PDFs are public disclosures — no IP concern. Committing them makes profiles reproducible. File sizes (~5-30 MB per 年报) are acceptable for a research repo; graduate to `git-lfs` only if a single clone ever exceeds ~500MB.

## 4. Template (`docs/value-profile/template-zh.md`)

### Structure

Top-level parts map 1-to-1 to the user's original framework. All content in Chinese.

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

### Per-section scaffolding

Every section carries:

1. **Heading** — e.g. `### §1.3 差异化：解决了客户什么样的别人没能解决的需求和痛点`.
2. **Prompt block** (Chinese) — user's original guiding questions.
3. **Data-source hint** (HTML comment) — 年报 / 招股说明书 listed first.
4. **Answer area** (Chinese) — AI's draft.
5. **Citations block** — `**引用:**` with `年报-YYYY.pdf p.NN` or URLs.
6. **Confidence** — `**置信度:** 高 / 中 / 低 / 未做 / 已跳过`.
7. **Spin-check** — `**管理层口径校核:**` for qualitative sections.

### Quantitative table skeletons

Part 2 tables are pre-laid out with row labels and empty year columns. Each table has `<!-- 取数要求 -->` listing the raw line items, and a `**来源:**` line the filler populates with `年报-YYYY.pdf p.NN`.

### Executive Summary (Part 0)

Filled last. Contains: 3-bullet 投资论点, 当前价位 vs 3-year 合理市值, Top 3 风险, 确信度, 建议仓位区间, 最近审阅日期.

## 5. Skill (`.claude/skills/value-profile/SKILL.md`)

### Frontmatter

```yaml
---
name: value-profile
description: Walk a user through filling out a 价值投资 profile for a single stock (A-shares / HK). Auto-fetches 年报 / 招股说明书 PDFs via scripts/download_filings.py when missing, reads them as first-hand primary sources, gathers qualitative + quantitative research section-by-section, writes Chinese-language profile to profiles/<ticker>-<date>.md as it goes. Trigger on "/value-profile <ticker>" or "研究 股票 <ticker>" or "fill out profile for <ticker>".
---
```

### Behavior (loop)

1. **Bootstrap + filings audit (updated in v3)**
   - Validate ticker format.
   - Check `data/filings/<ticker>/`:
     - If missing or <2 年报 PDFs, **offer to run the fetcher**: "缺少年报 PDF。是否自动运行 `python scripts/download_filings.py <ticker> --years 5 --include-prospectus`? [yes / no / show-command]"
       - `yes` → shell out to the fetcher, stream stdout to user, wait. On success continue; on failure fall back to manual download instructions.
       - `no` / `show-command` → print the CLI and abort.
     - Otherwise list what's available.
   - Derive output path `profiles/<ticker>-<YYYY-MM-DD>.md`. Create from template or load existing.

2. **Progress map** — parse `**置信度:**` lines, render summary.

3. **Section worker**: PDF pre-read → scoped research subagent → main-agent review → user gate (accept/edit/defer/skip/research-more) → save.

4. **Part 2 bulk mode** — single subagent reads 10y of 年报 财务报表, fills all Part 2 tables with page citations, cross-checks vs 雪球.

5. **Part 4 排雷 checklist mode** — walks 29 items, yes/no research each from 年报 附注.

6. **Executive summary synthesis** — when ≥80% 已完成.

### What the skill must NOT do

- Must not rewrite sections marked 已完成 without explicit instruction.
- Must not fabricate numbers or citations (write `待补充` instead).
- Must not write output in English (bilingual operator lines OK).
- Must not proceed without 年报 PDFs — offer fetcher or abort.
- Must not `git commit`.
- Must not call into `ah_research/` (not built yet).

## 6. First-run plan (600519.SH 贵州茅台)

**Prerequisite (v3):** run `python scripts/download_filings.py 600519.SH --years 5 --include-prospectus`, or let the skill's bootstrap trigger it. Fallback is manual download from 巨潮资讯网 / HKEX.

**Sequence:** (re-ordered in v2: Part 1 qualitative first)

1. `/value-profile 600519.SH` — bootstrap (fetcher if needed), create profile.
2. **Part 1 §1 商业模式** (60-75 min).
3. **Part 1 §2 成长空间** (30 min).
4. **Part 1 §3 护城河** (60-90 min).
5. **Part 1 §4 管理与文化** (60-75 min, the hardest).
6. **Part 1 §5 风险** (30 min).
7. **Part 2 定量** (30-45 min, bulk mode).
8. **Part 4 买入清单 + 排雷清单** (90 min).
9. **Part 3 未来 + Part 5 持有** (30 min).
10. **Part 0 执行摘要** (15 min).

**Time:** ~7-8 focused hours across 2-3 sessions.

### Go/no-go criteria after first run

1. §3 护城河 cites specific 年报 pages (茅台镇 水源, 12987 工艺, 基酒 5y cycle, 品牌 价格带) — not generic.
2. §4 管理 engages the SOE dynamic + 高卫东 反腐 honestly. `管理层口径校核` fields non-trivial.
3. 29-item 排雷 surfaces ≥ 2-3 legitimate concerns.
4. Every Part 2 cell has a `年报-YYYY.pdf p.NN` citation; ≥4/5 random-sample vs 雪球.
5. User can make a buy / no-buy / sizing decision using the profile alone.

## 7. Relationship to existing `ah-research` platform

This skill is a workflow artifact, not a platform component.

Graduation path (post-Phase 1 of ah-research):

- Part 2 tables → filled via `ah_research.DataRepository.get_fundamentals(asof=...)` instead of PDF parsing. PDF reading stays for qualitative cross-reference.
- Price / PE-PB band / yield cells → via `get_prices` + valuation-band analysis.
- Sector peer data → via `DataRepository` sector queries.
- **Qualitative sections keep reading 年报 PDFs** — no data source replaces management's own words.
- `scripts/download_filings.py` may eventually move to `src/ah_research/integrations/cninfo_client.py` and be exposed via the repository.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Generic AI output on the moat section | Section prompts force 年报 page citations + ban hedging |
| **Management spin in 年报** | `管理层口径校核` field requires cross-check vs 研报 / 财新 / 监管披露 / 价盘 |
| Quant table errors (AI misread of PDF) | Every cell cites `年报-YYYY.pdf p.NN`; user random-samples vs 雪球 |
| Profile staleness | Date-stamped filename; re-run annually |
| Scope creep → skill becomes the platform | Hard non-goal: no Python in `src/ah_research/`. Fetcher in `scripts/` is small exception |
| Rewriting 已完成 sections | Skill never does this without explicit instruction |
| Sensitive committed profiles | Move `profiles/` out if repo goes public |
| 排雷清单 false negatives on real fraud | Accepted for v0 — checklist is a prompt, not a detector |
| **cninfo API schema drift** (v3) | Tenacity retries for transient; `FetchSchemaError` on schema drift; tests use recorded fixtures |
| **PDF reading cost** | Target specific 年报 ToC sections; budget ~100 Read calls per profile |
| **Repo bloat** from PDFs | Accept; graduate to `git-lfs` if clone > ~500MB |
| **Fetcher rate-limit trip** (v3) | ≥1 req/sec, tenacity exponential backoff on 429 |

## 9. Success criteria

1. `/value-profile 600519.SH` produces a 1200+ line Chinese profile in ≤8 focused hours.
2. ≥80% of framework sections with 置信度 ≥ 中.
3. Every Part 2 cell has a 年报 page citation; ≥4/5 agreement vs 雪球.
4. §4 管理 has non-trivial `管理层口径校核` lines.
5. Go/no-go criteria in §6 all met.
6. User would use this file to make a real buy / no-buy / sizing decision.
7. **(v3)** `python scripts/download_filings.py 600519.SH --years 5 --include-prospectus` downloads ≥4 valid 年报 + 招股说明书 without manual intervention. Tests pass offline using recorded fixtures.

## 10. Open questions — resolved

| # | Question | Resolution |
|---|---|---|
| 1 | Profile commit policy | **Commit everything to repo.** Git-lfs deferred. |
| 2 | Language — interaction vs output | **Output Chinese. Interaction bilingual.** |
| 3 | Next ticker after Moutai | **Deferred** — decide after first run. |
| 4 | `research more` fallback scope | **PDF reading is primary, not a fallback.** |
| 5 (v3) | PDF acquisition: manual vs automated? | **Automated via `scripts/download_filings.py` (direct cninfo POST, no new deps).** |

---

**Execution location (v3):** value-profile work happens in `/Users/brian_huang/repos/ah-research-vp` on branch `feat/value-profile`. The original `/Users/brian_huang/repos/ah-research` (on `feat/phase-0-1-scaffold`) is the other agent's domain.
