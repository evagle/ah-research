# Value Profile Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code skill that walks a user through the 价值投资 profile framework for a single stock, reads 年报 / 招股说明书 PDFs as primary sources, and produces a Chinese-language per-ticker profile. Dogfood on 600519.SH (贵州茅台).

**Architecture:** Skill-only (no Python code in `src/ah_research/`). A markdown template (`docs/value-profile/template-zh.md`) defines the framework. A Claude Code skill (`.claude/skills/value-profile/SKILL.md`) walks the template section-by-section, dispatches research subagents that read 年报 PDFs from `data/filings/<ticker>/`, and writes profile output to `profiles/<ticker>-<date>.md`. Output is Chinese; operator interaction is bilingual. Retrofits to `ah_research.DataRepository` post-Phase-1.

**Tech Stack:** Markdown, Claude Code skill format (YAML frontmatter + instructions), Claude Code `Read` tool for PDF reading, `general-purpose` subagent for research dispatch. No new Python dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-28-value-profile-skill-design.md` — read it before starting.

---

## Phase 1 — Scaffolding (directories + README + placeholder files)

### Task 1: Create the template directory and placeholder file

**Files:**
- Create: `docs/value-profile/template-zh.md`

- [ ] **Step 1: Create directory**

Run: `mkdir -p /Users/brian_huang/repos/ah-research/docs/value-profile`
Expected: no output; directory now exists.

- [ ] **Step 2: Create the template file with just the top-of-file header**

Write the file with this exact content (the body will be filled in Phase 2):

```markdown
# 价值投资个股研究 Profile — Template

<!--
模板版本 v1 — 2026-04-28
本模板是 价值投资个股研究 框架的可填写骨架。每一节包含:
  - 本节目标
  - 指导问题 (HTML comment)
  - 数据源提示 (HTML comment, 年报 / 招股说明书 优先)
  - 填写区 (由 AI + 用户 交互填写)
  - 引用 / 置信度 / 管理层口径校核 字段

Skill 在调用时会复制本模板到 profiles/<ticker>-<date>.md, 然后逐节填写。
-->

<!-- Parts 0-5 follow — populated in later tasks -->
```

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research add docs/value-profile/template-zh.md
git -C /Users/brian_huang/repos/ah-research commit -m "docs(value-profile): add empty template file"
```

---

### Task 2: Create the filings directory + README

**Files:**
- Create: `data/filings/README.md`
- Create: `data/filings/600519.SH/.gitkeep`

- [ ] **Step 1: Create directory structure**

Run:
```bash
mkdir -p /Users/brian_huang/repos/ah-research/data/filings/600519.SH
touch /Users/brian_huang/repos/ah-research/data/filings/600519.SH/.gitkeep
```

- [ ] **Step 2: Write the filings README**

File: `data/filings/README.md` — exact content:

```markdown
# data/filings/

首手资料存放处。每个股票一个子目录 (命名: `<ticker>`, 与 `profiles/` 一致)。
PDFs 承诺提交到 repo — 公开披露无版权问题, 本 repo 定位为研究材料库。

## 目录结构

    data/filings/
    └── <ticker>/              # e.g. 600519.SH, 0700.HK
        ├── 年报-<YYYY>.pdf     # 每年一份, 最近 5 年 起步
        ├── 招股说明书.pdf       # IPO 一次性, 老公司 仍 必须下载
        └── 研报/               # 可选, 卖方/买方 深度研报
            └── <来源>-<主题>.pdf

## 命名规范

- **年报:** `年报-<YYYY>.pdf` — `YYYY` 为 会计年度 的 结束年 (2024 年报 = 披露 于 2025 年 但 覆盖 2024 年度)
- **招股说明书:** `招股说明书.pdf` (若 有多次发行, 加日期后缀)
- **研报:** 任意可识别文件名, 放 `研报/` 子目录

## 下载来源

- **A 股年报:** 巨潮资讯网 http://www.cninfo.com.cn
  - 搜索 股票代码 → 公告 → 年度报告
- **H 股年报:** 香港交易所 https://www.hkexnews.hk
- **招股说明书:** 同上 (巨潮资讯网 / HKEX 披露首发档案)
- **研报:** 研究员工作站内部资源 (不赘述)

## Value-Profile Skill 的使用

`.claude/skills/value-profile/SKILL.md` 在 bootstrap 时会 audit 本目录。
若 `data/filings/<ticker>/` 缺少 或 年报少于 2 份, Skill 会 blocked 并 给出下载指引。
下载 PDFs 后重新 run `/value-profile <ticker>` 即可.
```

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research add data/filings/
git -C /Users/brian_huang/repos/ah-research commit -m "docs(filings): add data/filings/ README + 600519.SH placeholder"
```

---

### Task 3: Create the profiles directory

**Files:**
- Create: `profiles/.gitkeep`

- [ ] **Step 1: Create directory and gitkeep**

```bash
mkdir -p /Users/brian_huang/repos/ah-research/profiles
touch /Users/brian_huang/repos/ah-research/profiles/.gitkeep
```

- [ ] **Step 2: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research add profiles/
git -C /Users/brian_huang/repos/ah-research commit -m "chore(profiles): add profiles/ dir for skill output"
```

---

### Task 4: Create the skill directory with skeleton SKILL.md

**Files:**
- Create: `.claude/skills/value-profile/SKILL.md`

- [ ] **Step 1: Create directory**

```bash
mkdir -p /Users/brian_huang/repos/ah-research/.claude/skills/value-profile
```

- [ ] **Step 2: Write skeleton SKILL.md with frontmatter only**

Exact content:

```markdown
---
name: value-profile
description: Walk a user through filling out a 价值投资 profile for a single A-share / HK stock. Reads 年报 / 招股说明书 PDFs from data/filings/<ticker>/ as first-hand primary sources, gathers qualitative + quantitative research section-by-section, writes Chinese-language profile to profiles/<ticker>-<date>.md as it goes. Trigger on "/value-profile <ticker>", "研究 股票 <ticker>", or "fill out profile for <ticker>".
---

# Value Profile Skill

<!-- Body populated in Phase 3 tasks -->
```

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research add .claude/skills/value-profile/SKILL.md
git -C /Users/brian_huang/repos/ah-research commit -m "feat(skill): add value-profile skill frontmatter skeleton"
```

---

## Phase 2 — Template body

The template uses a uniform per-subsection pattern. Task 5 defines the pattern. Tasks 6-11 apply it to each Part of the framework. Task 12 verifies the template renders.

### Task 5: Define the subsection pattern — write Part 0 执行摘要 + Part 1 header

**Files:**
- Modify: `docs/value-profile/template-zh.md`

**The subsection pattern** (this is the reference used throughout Phase 2):

```markdown
### §X.Y <小节标题, Chinese>

**本节目标:** <1 行 describing what this section answers>

<!-- 指导问题:
  - <user's guiding question 1>
  - <user's guiding question 2>
  ... (from the 价值投资个股研究profile模板 that user supplied)
-->

<!-- 数据源: 年报"<chapter>"; 招股说明书"<chapter>"; <web source 1>; <web source 2> -->

<填写区>

**引用:**
- [待填写]

**置信度:** 未做

**管理层口径校核:** <仅 定性 小节 填写>
```

**Rules for applying the pattern:**
- `本节目标` is a ONE-line Chinese sentence.
- `指导问题` is copied from the user's original framework (see the user's original profile template paste — it lists the guiding questions per subsection).
- `数据源` always starts with `年报"<相关章节>"` first, then other sources.
- `管理层口径校核` appears only on 定性 subsections (Part 1 §1-§5) and on Part 2 §8 话语权 analysis. Part 2 numeric tables get `**来源:**` (URL + 年报 page) instead.

- [ ] **Step 1: Append Part 0 header + 执行摘要 + Part 1 opening to the template**

Use Edit on `docs/value-profile/template-zh.md`. Replace the existing `<!-- Parts 0-5 follow — populated in later tasks -->` marker with:

```markdown
## Part 0 — 封面 & 执行摘要

| 字段 | 值 |
|---|---|
| **股票代码 (ticker)** | `<code>.<exchange>` — e.g. 600519.SH |
| **公司名称** | <中文> / <English> |
| **交易所 / 币种** | SH / SZ / HK ; CNY / HKD |
| **报告日期 (report_date)** | YYYY-MM-DD |
| **研究者** | <name> |

### 执行摘要 (本节最后填写)

**投资论点 (3 bullets):**
- <是否买>
- <什么价位买>
- <为什么>

**估值现状:**
- 当前价位: <¥...>
- 当前 PE / PB / 股息率: <...>
- 3 年后合理市值区间: <乐观 / 中性 / 悲观>

**Top 3 风险 (ranked):**
1. <...>
2. <...>
3. <...>

**确信度:** 高 / 中 / 低
**建议仓位区间:** <%..%>
**最近审阅日期:** YYYY-MM-DD

---

## Part 1 — 定性分析 (PRIMARY — 先填)

<!-- 定性 > 定量。本 Part 依赖 年报 + 招股说明书 为 主要 数据源,
     辅以 行业研报 + 财经新闻 做 管理层口径 的 交叉校核. -->

<!-- §1-§5 follow -->
```

- [ ] **Step 2: Verify the file renders cleanly**

Run: `cat /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md | head -50`
Expected: see the Part 0 table and 执行摘要 structure.

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research add docs/value-profile/template-zh.md
git -C /Users/brian_huang/repos/ah-research commit -m "docs(value-profile): template — Part 0 header + 执行摘要"
```

---

### Task 6: Template — Part 1 §1 商业模式 (7 subsections)

**Files:**
- Modify: `docs/value-profile/template-zh.md`

Apply the subsection pattern (from Task 5) to all 7 subsections listed below. Append after the existing `<!-- §1-§5 follow -->` marker.

**Subsections to create:**

1. **§1.1 公司核心资产、主营产品和服务** — 产品生产流程, 核心资产, 主营收入占比, 生命周期, 关键资源, 利润决定变量
2. **§1.2 公司客户** — 2C/2B/2G, 地理/人口特征, 大客户依赖, 客户粘性 / 替代难度 / 心智占领
3. **§1.3 差异化** — 价格 / 产品 / 服务 / 渠道 / 技术 / 品牌 / 生态 差异化类型, 竞争对手 复制难度
4. **§1.4 盈利模式** — 差价 / 订阅 / 广告 / 租赁 / 授权 / 加盟 / 品牌溢价 中的哪种, 轻/重 资产, 直营/加盟, 成本/费用/收入 结构
5. **§1.5 生意特性** — 好生意 checklist (刚需/差异化/弱周期/轻资产/迭代慢/低资本开支), 避开的差生意特性
6. **§1.6 现金流状况** — 赚真金白银 / 持续赚钱 / 资本开支 / 生产-销售-运营 三环节资金状况, 现金周转周期
7. **§1.7 已知优秀商业模式特性** — 品牌短周期制造商 / 必需品公用事业 / 品牌溢价 / 监管需求 / 高可扩展性 / 最低价供应商 中的哪种

**Header to insert before §1.1:**

```markdown
## §1 商业模式

<!-- 商业模式 核心 是 广义产品. 企业 以 何种方式 提供 何种产品,
     满足 何种客户 的 何种需求, 如何盈利, 生意特性 / 自由现金流 如何 -->
```

- [ ] **Step 1: Build the full §1 content block**

For each of §1.1-§1.7: apply the Task 5 pattern. Populate 本节目标, 指导问题 (from user's framework), 数据源 (lead with 年报"主营业务分产品" / "经营情况讨论与分析" / 招股说明书"业务与技术"), and leave 填写区 / 引用 / 置信度 / 管理层口径校核 blank.

Example — §1.1 complete block:

```markdown
### §1.1 公司核心资产、主营产品和服务

**本节目标:** 一句话讲清楚 公司 以什么方式 生产 什么产品 / 服务, 卖给 谁。

<!-- 指导问题:
  - 产品 如何生产? 原材料 / 采购 / 生产 / 工艺 / 半成品 / 成品
  - 核心资产 是什么? 能否继续扩张? 扩张策略 / 空间
  - 主营产品 及 分产品 / 分行业 收入占比, 单位成本 / 单位收益
  - 产品的 生命周期 / 市场占比 / 成长空间
  - 关键资源 / 关键环节 (研发 / 销售 / 品牌 / 供应链 / 物流)
  - 决定利润 的 关键变量 是什么? 能否预测
  - 行业 / 公司 最重要的 指标 及其 变化
  - 原材料 供需 情况, 公司 议价能力
  - 市场 是否 有定价权
  - 高利润率 / 高周转率 / 高杠杆 中的哪种
-->

<!-- 数据源: 年报"主营业务分行业、分产品、分地区"; 年报"经营情况讨论与分析"; 招股说明书"业务与技术"; 雪球 F10 -->

<填写区>

**引用:**
- [待填写]

**置信度:** 未做

**管理层口径校核:** [待填写]
```

Repeat for §1.2 through §1.7 with the guiding questions from the user's original 价值投资 framework and appropriate 年报 chapters.

- [ ] **Step 2: Append the complete §1 block to the template**

Use Edit to replace the `<!-- §1-§5 follow -->` marker with the §1 header + all 7 subsection blocks, followed by `<!-- §2-§5 follow -->`.

- [ ] **Step 3: Verify the structure**

Run: `grep -E "^### §1\." /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md | wc -l`
Expected: `7`

- [ ] **Step 4: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research add docs/value-profile/template-zh.md
git -C /Users/brian_huang/repos/ah-research commit -m "docs(value-profile): template — Part 1 §1 商业模式 (7 subsections)"
```

---

### Task 7: Template — Part 1 §2 成长空间/天花板 (6 subsections)

**Files:**
- Modify: `docs/value-profile/template-zh.md`

**Subsections (apply Task 5 pattern):**

1. **§2.1 行业基本情况 + 竞争格局** — 行业所处周期, CR5/CR10, 集中度趋势, 竞争烈度
2. **§2.2 市场规模、增速、供需** — 市场规模测算, 3-5y 供需, 公司行业地位, 产品生命周期 / 渗透率, 国际化适合度
3. **§2.3 竞争对手 营收净利 对比** — 主要对手, 营收 / 净利 / 产品竞争力 对比, 优劣势
4. **§2.4 行业与公司成长空间** — 行业天花板 vs 公司天花板, 10y 乐观/中性/悲观 营收/利润测算, 相对 vs 绝对空间
5. **§2.5 历史成长动力分解** — 营收增长 (量 / 价 / 并购) vs 净利率提高 (毛利率 / 费用率), 可持续性
6. **§2.6 未来成长动力** — 哪些 因素 可持续, 哪些会消失, 哪些会增加

**Header to insert before §2.1:**

```markdown
## §2 成长空间 / 天花板
```

Apply the Task 5 pattern. 数据源 should lead with 年报 "管理层讨论与分析" (for growth commentary) + 行业研报 (for size sizing). 

- [ ] **Step 1: Build and insert the full §2 block**
- [ ] **Step 2: Verify — grep should show 6 §2.X headings**

Run: `grep -E "^### §2\." /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md | wc -l`
Expected: `6`

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "docs(value-profile): template — Part 1 §2 成长空间 (6 subsections)"
```

---

### Task 8: Template — Part 1 §3 护城河 (10 subsections)

**Files:**
- Modify: `docs/value-profile/template-zh.md`

**Subsections (apply Task 5 pattern):**

1. **§3.1 定性: 公司的护城河有哪些** — 经济特许经营权 / 专利 / 技术 / 政府准入 / 不可替代 / 成本 / 品牌 / 渠道 / 定价权 / 管理层 / 独特产品
2. **§3.2 护城河来源因素分析** — 无形资产 (品牌/专利/垄断/秘方/地理) / 转换成本 / 网络效应 / 低成本 (规模 / 区域 / 商业模式创新) / 有效规模-利基 / 平台生态 / 企业文化
3. **§3.3 产品差异化** — 满足了什么别人未满足的需求, 为什么别人做不到, 长期可维持性
4. **§3.4 波特五力** — 供应商议价 / 购买者议价 / 新进入者威胁 / 替代品威胁 / 行业竞争强度
5. **§3.5 ROE / ROIC 分析 (行业对比)** — 与行业平均 / 领先者 的 对比
6. **§3.6 ROE 杜邦分析** — 高净利/高周转/高杠杆 结构, 无形资产, 高 ROE 可持续性
7. **§3.7 毛利率分析 (行业对比)** — 高毛利 来源 (成本低 vs 售价高), 分产品 拆解, 可持续性
8. **§3.8 护城河发展趋势** — 逐因素 正面 / 负面 / 稳定
9. **§3.9 非护城河因素** — 优秀产品 / 先发优势 / 高市占 / 高效运营 / 资金优势 (易被复制)
10. **§3.10 政府政策分析** — 特许经营 / 税收优惠 / 扶持政策 / 补贴

**Header:**

```markdown
## §3 护城河分析

<!-- 好公司 两个标准: 它做的事 别人做不了; 它做的事 自己可以重复做。
     可以 长期维持 的 差异化 就是 护城河。企业文化 对 建立和维护 护城河 不可或缺。 -->
```

- [ ] **Step 1: Build and insert the full §3 block**

§3.5-§3.7 数据源 should lead with 年报 (financial highlights + 管理层讨论). The 10y ROE / 毛利 行业对比 data will be cross-referenced to Part 2 tables — use `见 Part 2 §1` cross-refs in the 填写区.

- [ ] **Step 2: Verify — grep should show 10 §3.X headings**

Run: `grep -E "^### §3\." /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md | wc -l`
Expected: `10`

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "docs(value-profile): template — Part 1 §3 护城河 (10 subsections)"
```

---

### Task 9: Template — Part 1 §4 管理质量与企业文化 (7 subsections)

**Files:**
- Modify: `docs/value-profile/template-zh.md`

**Subsections (apply Task 5 pattern):**

1. **§4.1 专注主业, 眼光长远** — 是否随意跨界 / 并购, 主业聚焦度, 长短期利益平衡
2. **§4.2 企业家评估 (言行一致, 能力与格局)** — 管理层在年报的预测 vs 后续 兑现, 增持/减持, 价值观
3. **§4.3 企业家: 优秀特征 vs 失败特征 checklist** — 诚信正直 / 本分 / 热爱事业 / 眼光长远 / 专注 / 理性 / 坦诚 / 不盲从 / 言行一致
4. **§4.4 企业文化** — 使命 / 愿景 / 核心价值观, 对员工 / 客户 / 供应商 / 合作伙伴 / 竞争对手 / 股东 的态度, 不为清单
5. **§4.5 内部治理结构** — 是否一言堂, 管理层与骨干持股, 股权质押
6. **§4.6 以股东利益为导向** — 分红 / 回购, 增发, 历史融资 vs 历史分红, 大众股东收益率
7. **§4.7 股权结构** — 管理层与股东是否一条船, 股权分散度

**Header:**

```markdown
## §4 管理质量与企业文化

<!-- 企业文化 = 使命 + 愿景 + 核心价值观。
     看企业文化 没有捷径, 最直接 是 "听其言观其行 查其绩 读其心"。
     历年年报 管理层 对行业的 预判 及 准确性 回顾 是 关键抓手。 -->
```

**Special note:** §4 is where 管理层口径校核 is most critical. Cross-reference 年报's 公司治理 / 董事报告 language vs 财经新闻 / 监管披露 / 分析师调研 for the 真实画面.

- [ ] **Step 1: Build and insert the full §4 block**
- [ ] **Step 2: Verify — grep should show 7 §4.X headings**

Run: `grep -E "^### §4\." /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md | wc -l`
Expected: `7`

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "docs(value-profile): template — Part 1 §4 管理与企业文化 (7 subsections)"
```

---

### Task 10: Template — Part 1 §5 风险分析 (5 subsections)

**Files:**
- Modify: `docs/value-profile/template-zh.md`

**Subsections (apply Task 5 pattern):**

1. **§5.1 产品和业务风险** — 大客户 / 价格周期 / 薄利小市场 / 技术迭代 / 对外投资 / 关联交易, 衰落倒闭 情景, 价值陷阱 vs 成长陷阱 vs 会计造假 三类
2. **§5.2 财务风险** — 现金不足 / 高负债 / 经营现金流为负 / 靠筹资为生
3. **§5.3 管理层风险** — 大规模减持 / 决策损害股东 / 大股东侵占
4. **§5.4 造假风险** — 造假动机 (圈钱 / 业绩对赌 / 炒高套现 / 防 st 退市 / 大洗澡) + 造假痕迹
5. **§5.5 成长风险** — 无法维持当前份额 / 未来增长受限 / 行业宏观因素

**Header:**

```markdown
## §5 风险分析
```

- [ ] **Step 1: Build and insert the full §5 block**
- [ ] **Step 2: Verify — grep should show 5 §5.X headings**

Run: `grep -E "^### §5\." /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md | wc -l`
Expected: `5`

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "docs(value-profile): template — Part 1 §5 风险分析 (5 subsections)"
```

---

### Task 11: Template — Part 2 定量分析 (9 subsections with table skeletons)

**Files:**
- Modify: `docs/value-profile/template-zh.md`

Part 2 uses a **different** per-subsection pattern because it's table-heavy and quantitative. Here's the Part 2 pattern (apply throughout):

```markdown
### §2.X <小节标题>

**本节目标:** <1 行>

<!-- 取数要求: <原始 line items 需 从 年报 哪个章节 取> -->

| 年度 | Avg | 2024 | 2023 | 2022 | 2021 | 2020 |
|---|---|---|---|---|---|---|
| <指标 1> | | | | | | |
| <指标 2> | | | | | | |

**行业对比:** <sector peers + 数值>

**来源:**
- 年报-2024.pdf p.NN
- 年报-2023.pdf p.NN
- ...

**总结:** <填写区 — 1-2 段>

**置信度:** 未做
```

**Subsections to create:**

1. **§Q1 盈利分析** — table rows: ROE, ROA, 净资产, 留存利润, 有息负债率 + 留存利润/新增股本 ROE 能否维持
2. **§Q2 盈利能力** — 毛利率 (>50% 优秀), 核心利润率 (毛利-税金附加-三费), 净利率 (>20% 优秀) — 6y + Avg
3. **§Q3 盈利质量** — 销售收现率 (>1.17), 净现比 (>1), 资本开支/净利润 (<30% 优秀), 核心利润率 (>20%) — 6y + Avg
4. **§Q4 成长能力** — 营收 (>25% 优秀), 净利润, 营收增速, 净利增速, 扣非增速 — 6y
5. **§Q5 资产增速** — 总资产, 负债, 净资产, 各增速 — 6y
6. **§Q6 运营能力** — 总资产周转天数, 存货周转天数, 应收周转天数, 应付账款周转天数, 现金周转周期 — 6y + Avg
7. **§Q7 偿债能力** — 有息负债率, 有息现金覆盖率, 资产负债率, 流动比率, 速动比率 — 6y + Avg
8. **§Q8 现金流分析** — 3 张透视表: (a) 净利润含现量表 (经营现金流净额 / 净利润 / 净利润含现量 / 资本支出), (b) 销售收现率表, (c) 现金余额/资本开支/现金分红/有息负债对比
9. **§Q9 资产负债表分析** — 简化结构透视: 货币资金 / 生产资产 / 营运资产 / 应收预付 / 金融资产 / 有息负债 / 应付预收 / 营运负债 / 净资产; 商誉/应收/应付/预付占比 风险
10. **§Q10 简化利润表分析** — 百分比版利润表 (营收=100%), 危险科目 (非经常性损益 / 营业外损益)
11. **§Q11 上下游分析** — 预付/应付 (上游), 应收/预收 (下游), 话语权 / 定价权 总结
12. **§Q12 定量分析总结** — Part 2 整合 一段

**Part header:**

```markdown
---

## Part 2 — 定量分析 (10 年财务指标检查)

<!-- 定量 < 定性 在 优先级 (per 用户 决定), 但 两者 都 被重视.
     Part 2 是 Part 1 的 事实基础 — 所有数字 从 年报 取,
     行业对比 从 研报 / 雪球 F10 交叉验证. -->
```

- [ ] **Step 1: Build and insert all 12 Part 2 subsections**

- [ ] **Step 2: Verify — grep should show 12 §Q headings**

Run: `grep -E "^### §Q" /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md | wc -l`
Expected: `12`

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "docs(value-profile): template — Part 2 定量 (12 subsections + table skeletons)"
```

---

### Task 12: Template — Parts 3, 4, 5 (未来 + 买入清单 + 持有清单)

**Files:**
- Modify: `docs/value-profile/template-zh.md`

**Part 3 — 未来** (4 subsections, apply Task 5 pattern):

1. **§3.1 未来市场可能的变化** — 需求端 / 供给端 / 实际追踪机制
2. **§3.2 未来公司可能的变化** — 主营产品 价格/成本/费用, 新业务发展, 未来市场份额
3. **§3.3 未来净利润增长来源** — 营收增长 (量 / 价 / 并购) vs 净利率提升 (毛利 / 费用率)
4. **§3.4 ROE 提高的空间和来源** — 利润率 / 周转率 / 杠杆 各自 还有 多大空间

Plus: **§3.5 其他环境变化** — 科技进步 / 政策变化 影响.
Plus: **§3.6 如果我是董事长** — open-ended strategic thought exercise.

**Part 4 — 买入阶段检查清单** (8 sub-blocks, mostly checklist format):

1. **§4.1 市场估值分析** — 市场 PE/PB 高度, 行业 PE/PB 高度
2. **§4.2 当前公司估值情况** — 当前 vs 历史 PE/PB/股息率, PE/PB band
3. **§4.3 3 年后的净利润及估值** — 3y 净利润测算, 3y PE/PB 合理范围, 3y 市值合理范围, 3 年一倍 折算到 当前 市值
4. **§4.4 公司基本面再分析** — 对比 研究阶段, 正面 因素 / 负面 信息
5. **§4.5 负面清单 — 爆雷风险 (29 items checklist)** — 详细 见 下面
6. **§4.6 当前价位买入仓位** — 能力圈 / 容错机制
7. **§4.7 买入后加仓 / 持有预案** — 下跌 10%/20%/30%/50% 情景
8. **§4.8 买入前 Final 检查** — 研究是否彻底, 被忽视的 重大信息, 是否愿意 持有 10 年, 仓位是否合理, 完全亏损 可否承受
9. **§4.9 心理偏误 check** — 追涨 / 拒买 / 价格锚定

**§4.5 爆雷 checklist** is 29 items; table format:

```markdown
### §4.5 负面清单 — 爆雷风险 (29 items)

| # | Check | 是 / 否 / 不适用 / 需人工 | 证据 (年报 页码 / URL) |
|---|---|---|---|
| 1 | 出现过非"标准无保留"审计意见 | | |
| 2 | 有财务造假历史 | | |
| 3 | 存贷双高 | | |
| 4 | 大额存款但利息异常低 | | |
| 5 | 货币资金大幅变动 / 收益率异常 | | |
| 6 | 其他货币资金数额巨大无解释 | | |
| 7 | 借钱大笔分红后再融资 | | |
| 8 | 定期存款多 但 流动资金少 | | |
| 9 | 应收账款增速快 收现比低 | | |
| 10 | 存货增速超营收增速 | | |
| 11 | 大股东股权质押 >80% | | |
| 12 | 收现率 / 净现比 异常 | | |
| 13 | 应收账款 金额 / 占比 持续上涨, 周转率下降 | | |
| 14 | 存货 金额/占比 持续上涨 有减值风险 | | |
| 15 | 其他应收款 >10% 或 逐季上涨 | | |
| 16 | 商誉 占总资产 >5% | | |
| 17 | 预付账款 突然暴涨 / 关联方 | | |
| 18 | 预付账款 增速 > 营收增速 | | |
| 19 | 无形资产 金额 / 占比 / 减值风险 | | |
| 20 | 固定资产 + 在建工程 异常 | | |
| 21 | 在建工程 迟迟不转固定资产 | | |
| 22 | 固定资产周转天数 异常 | | |
| 23 | 有息覆盖率 下降到 100% 边缘 | | |
| 24 | 前五客户 / 供应商 >50% ; 单一 >30% | | |
| 25 | 研发费用 资本化比例 / 金额占净利润 | | |
| 26 | 折旧 / 摊销 会计政策 变动 | | |
| 27 | 应收账款 坏账计提 比例 变更 / 保理高 | | |
| 28 | ROE <15% | | |
| 29 | 关联交易 占比 高 / 大股东是信托/投资公司 | | |

**发现的红旗 summary:** <填写区>

**置信度:** 未做
```

**Part 5 — 持有阶段检查清单** (5 sub-blocks):

1. **§5.1 组合健康检查** — 透视盈利, 1 美元原则
2. **§5.2 持续关注经营状况** — 季报 / 半年报 / 年报 跟踪, 定性 因素 重新审视
3. **§5.3 是否触发卖出标准** — 看错 / 基本面恶化 / 极度高估 / 更好标的
4. **§5.4 卖出动作 心理偏误 check** — 涨太多 / 无法承受下跌 / 成本价锚定
5. **§5.5 是否触发新的买入标准** — 业务大超预期 / 大熊市 / 黑天鹅

**Part headers:**

```markdown
---

## Part 3 — 未来 (Forward-looking)

---

## Part 4 — 买入阶段检查清单

---

## Part 5 — 持有阶段检查清单

<!-- 持有阶段 的 任务 是 拒绝卖出。
     股权是目的, 现金是手段。卖出是 被动 — 不得不卖出 — 而非 主动 "落袋为安 / 截断亏损"。 -->
```

- [ ] **Step 1: Build and insert all of Parts 3 + 4 + 5**
- [ ] **Step 2: Verify Part counts**

Run:
```bash
grep -E "^## Part " /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md
```
Expected: 5 Part headings (Parts 0 through 5, but `## Part 0` etc.). Actually Parts 0-5 = 6 headers if Part 0 is its own `## Part 0`.

Run `grep -c "^## Part " docs/value-profile/template-zh.md`
Expected: `6`

- [ ] **Step 3: Check 爆雷 checklist has 29 rows**

Run: `grep -c "^| [0-9]" /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md`
Expected: `29` (the 29 checklist rows).

- [ ] **Step 4: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "docs(value-profile): template — Parts 3-5 (未来 / 买入 / 持有 + 29-item 爆雷 checklist)"
```

---

### Task 13: Template smoke-render verification

**Files:** (no changes — verification only)

- [ ] **Step 1: Render the template to terminal and eyeball it**

Run: `wc -l /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md`
Expected: ≥ 800 lines.

Run: `grep -cE "^### §" /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md`
Expected: ≥ 50 subsection headings.

Run: `grep -c "置信度:" /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md`
Expected: ≥ 50 (one per subsection).

Run: `grep -c "数据源:" /Users/brian_huang/repos/ah-research/docs/value-profile/template-zh.md`
Expected: ≥ 40 (Part 1 + some Part 3).

- [ ] **Step 2: Preview in a renderer**

If GitHub locally or a markdown viewer is available, open the file and check:
- Table of 爆雷 29 checklist renders as a table.
- Part 2 quantitative tables render with headers and empty cells.
- Chinese characters display correctly.

If anything's visually broken, go back and fix; else proceed.

- [ ] **Step 3: No commit** (no changes yet).

---

## Phase 3 — Skill body

### Task 14: Skill — invocation contract + bootstrap + filings audit

**Files:**
- Modify: `.claude/skills/value-profile/SKILL.md`

- [ ] **Step 1: Append the invocation contract and bootstrap steps**

After the skeleton header (which has just the frontmatter and `# Value Profile Skill` heading), append this content:

```markdown
## Invocation

- Primary: `/value-profile <ticker>` where `<ticker>` is `<code>.<exchange>` form (e.g. `600519.SH`, `0700.HK`).
- Optional: `--section <id>` (e.g. `--section 1.3`) to jump directly to one section.
- Optional: `--resume` to continue where the progress map says `进行中` / `未做`.

## Behavior

### Step 1 — Bootstrap + filings audit

1. **Validate ticker format.** If `<ticker>` doesn't match `^[0-9]{4,6}\.(SH|SZ|HK)$`, print:
   > "Invalid ticker. Use `<code>.<exchange>` form — e.g. `600519.SH` (A-share), `0700.HK` (HK)."

2. **Check filings directory.** List `data/filings/<ticker>/` contents.
   - If the directory is missing **OR** contains fewer than 2 `年报-*.pdf` files, print the blocking message below (Chinese + English):
   
     ```
     ❌ 缺少年报 PDF。价值投资研究必须以 年报 + 招股说明书 为 第一手资料。
     请下载最近 5 年 (起步) 年报 到 `data/filings/<ticker>/`:
         - 来源: 巨潮资讯网 http://www.cninfo.com.cn (A 股)
                 香港交易所 https://www.hkexnews.hk (HK 股)
         - 命名: `年报-YYYY.pdf` (YYYY = 会计年度的结束年)
         - 若公司 IPO 时间较远, 请 also 下载 `招股说明书.pdf`
     下载完成后请重新 run `/value-profile <ticker>`。
     
     ❌ Missing 年报 PDFs. Value research must ground in 年报 + 招股说明书 as first-hand sources.
     Download ≥ 5 recent 年报 into `data/filings/<ticker>/` from cninfo.com.cn (A-share) or hkexnews.hk (HK).
     Re-run when done.
     ```
   
   - Otherwise, print a summary: "Found N 年报 (<years>). 招股说明书: present / missing. 研报/: K files." Continue.

3. **Derive output path.** `profiles/<ticker>-<YYYY-MM-DD>.md` using today's date.
   - If today's file exists: load it.
   - If a prior-date file exists: ask the user: "Prior profile `profiles/<ticker>-<prior-date>.md` exists. [resume / start-fresh]"
     - `resume` → rename old file to today's date, load it.
     - `start-fresh` → leave old file, create new one.
   - If no profile exists: copy `docs/value-profile/template-zh.md` to the output path. Fill Part 0 header (ticker, company name fetch via web search, exchange, report_date = today, researcher = git config user.name).

### Step 2 — Progress map

1. Parse the output file. For each section heading `### §X.Y ...`, find the next `**置信度:**` line (within that section's block). Build:
   ```
   {"1.1": "已完成", "1.2": "已完成", "1.3": "未做", ...}
   ```

2. Render summary (bilingual):
   ```
   已完成 4 / 50 节 (§0, §1.1, §1.2, §1.6).
   下一节 (next undone): §1.3 差异化
   
   继续 this section? 或 选择 other section? [continue / pick-section / exit]
   ```

3. Await user input, route accordingly.
```

- [ ] **Step 2: Verify the file renders**

Run: `grep -c "^## " /Users/brian_huang/repos/ah-research/.claude/skills/value-profile/SKILL.md`
Expected: `2` (Invocation, Behavior).

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "feat(skill): value-profile — invocation + bootstrap + filings audit"
```

---

### Task 15: Skill — section worker (PDF pre-read, dispatch, review, user gate, save)

**Files:**
- Modify: `.claude/skills/value-profile/SKILL.md`

- [ ] **Step 1: Append the section worker loop**

Add after the Progress map content (below Step 2):

```markdown
### Step 3 — Section worker (the inner loop)

For the chosen section `§X.Y`:

#### 3a. PDF pre-read

Based on the section's `<!-- 数据源: ... -->` hint, decide which 年报 pages to read.

Year reports have a standardized ToC — use these mappings:
| 小节类型 | 年报章节 (近似) |
|---|---|
| §1.1 主营产品 | 第三节 "公司业务概要"; 第四节 "经营情况讨论与分析" |
| §1.2 客户 | 第四节 "经营情况讨论与分析"; 第六节 "重要事项"(大客户) |
| §1.3-§1.5 差异化 / 盈利 / 生意特性 | 第三节 "公司业务概要"; 招股说明书 "业务与技术" |
| §1.6 现金流 | 第五节 "财务报告" 现金流量表 + 附注 |
| §1.7 已知优秀模式 | 第三节 + 行业研报 |
| §2 成长空间 | 第四节 "行业竞争状况"; 第四节 "管理层讨论与分析" |
| §3 护城河 | 第三节 "公司业务概要" (核心竞争力小节); 第四节 |
| §4 管理与文化 | 第六节 "重要事项"; 第七节 "股份变动和股东情况"; 第八节 "董事、监事、高级管理人员" |
| §5 风险 | 第四节 "管理层讨论与分析" (风险提示小节) |
| §Q1-§Q12 定量 | 第五节 "财务报告" (全部) |
| §4.5 爆雷 | 第五节 "财务报告" 附注 (逐项) |

Dispatch a `general-purpose` subagent with a prompt like:

```
You are researching section §X.Y for ticker <ticker> (<company>).

Read these PDFs from data/filings/<ticker>/ using the Read tool:
  - 年报-<YYYY>.pdf, pages <P1-P2>, <P3-P4>  (目标: <chapter name>)
  - 招股说明书.pdf, pages <P1-P2>  (if applicable)

Also do web research for cross-checking:
  - 雪球 F10: https://xueqiu.com/S/<ticker>
  - 东方财富 F10: https://emweb.eastmoney.com/pc_hsf10/pages/...
  - 新浪财经 公司新闻: ...
  - 最近 卖方研报 相关主题

Answer the section's guiding questions (reproduced below):
<指导问题 from template>

Language: answer in Chinese. Every fact cites either `年报-YYYY.pdf p.NN` or a URL.
If evidence is insufficient, write `证据不足, 需人工补充` — DO NOT hedge with value-investing platitudes.

For this section specifically, include a `管理层口径校核` paragraph noting where 年报's framing
may differ from external signals (研报 / 价盘 / 媒体 / 监管披露).

Return a markdown block matching the template's subsection pattern:
  - <填写区 content>
  - **引用:** [list]
  - **置信度:** 高/中/低
  - **管理层口径校核:** [one line]
```

#### 3b. Main-agent review

Read the subagent's output. Critique against the section's guiding questions. Rewrite if:
- Any fact lacks a citation.
- The 管理层口径校核 line is absent or trivial ("年报 says X, we agree").
- The 填写区 is generic (no ticker-specific detail).

Write a Chinese draft block with populated 引用 / 置信度 / 管理层口径校核 fields.

#### 3c. User gate

Present the draft. Frame it (bilingual):
```
Section §X.Y draft is ready. Review below.
Choose: [accept / edit: <text> / defer / skip / research more: <hint>]
```

Interpret the user's response:
- `accept` → save the draft to the profile file under the section's heading, replacing any prior content under that section. Set `**置信度:** <drafted level>`. Mark progress map as `已完成`.
- `edit: <text>` → apply textual edits to the draft (the user's text may be in Chinese or English and may target specific paragraphs). Then save as `已完成`.
- `defer` → save nothing. Mark progress map as `未做`. Loop back to progress map.
- `skip` → mark section as `已跳过` in the profile file (fill the 填写区 with `N/A — <reason>`). Save, loop back.
- `research more: <hint>` → dispatch a narrower subagent with the user's hint appended to the original prompt. Loop back to 3b.

#### 3d. Save and continue

After `accept` / `edit` / `skip`: write the section block to `profiles/<ticker>-<YYYY-MM-DD>.md` immediately (replace the section's entire block atomically). The file is always valid markdown after this save. Return to Step 2 (progress map).
```

- [ ] **Step 2: Verify**

Run: `grep -c "^### Step " /Users/brian_huang/repos/ah-research/.claude/skills/value-profile/SKILL.md`
Expected: `3`.

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "feat(skill): value-profile — section worker loop (PDF pre-read + dispatch + gate + save)"
```

---

### Task 16: Skill — Part 2 bulk + 爆雷 checklist + executive summary

**Files:**
- Modify: `.claude/skills/value-profile/SKILL.md`

- [ ] **Step 1: Append special-mode handlers**

Add after Section worker:

```markdown
### Step 4 — Part 2 (定量) bulk mode

Triggered when user selects Part 2 (`§Q1` or later) in the progress map.

1. Ask user: "Run Part 2 in bulk? One subagent will pull all 10y quantitative rows from 年报 PDFs + 雪球 F10 cross-check. [bulk / section-by-section]"
2. If `bulk`:
   - Dispatch ONE `general-purpose` subagent with instructions:
     - Read all `data/filings/<ticker>/年报-*.pdf` files (10y if available, 5y minimum).
     - Focus on 第五节 "财务报告" in each.
     - Extract the following 10-row quantities per year: 营业收入, 净利润, 扣非净利润, 毛利率, 净利率, ROE, ROA, 经营现金流净额, 资本开支, 有息负债, 现金及等价物, 总资产, 总负债, 净资产, 应收账款, 存货.
     - Fill Part 2 §Q1-§Q12 tables in `profiles/<ticker>-<YYYY-MM-DD>.md` in place.
     - Every cell carries a 年报 page citation in the **来源:** line.
     - Cross-check top rows (ROE, 毛利率, 净利率) against 雪球 F10; report discrepancies.
   - Present the filled Part 2 to the user.
   - Ask: "Sanity-check sample: Given ROE of <X%> in <year>, does 雪球 F10 show <X%>? [yes-all / mismatch: <row>]". Random-sample 5 cells.
   - If ≥ 4/5 agreement: mark all §Q subsections as `已完成`. Else: flag mismatched rows as `需人工`, move on.
3. If `section-by-section`: use the standard Step 3 section worker, one §Q at a time.

### Step 5 — Part 4 §4.5 爆雷 checklist mode

Triggered when user reaches §4.5 爆雷清单 (29 items).

1. Dispatch a single `general-purpose` subagent with a compound prompt:
   - "For each of the 29 items below, read `data/filings/<ticker>/年报-2024.pdf` (most recent) + prior year for trend. Read 资产负债表, 利润表, 现金流量表, 财务报表附注. Answer: 是 / 否 / 不适用 / 需人工 + 一句证据 + 年报页码."
   - List all 29 items from the template's §4.5 checklist table.
2. Subagent returns a table.
3. Main agent reviews, writes the filled table to the profile file.
4. Compose a "发现的红旗 summary" at the bottom (1-2 paragraphs) highlighting any 是 / 需人工 items.
5. User gate: `[accept / edit / research more]` (defer/skip not offered — 爆雷 checklist is mandatory).

### Step 6 — Executive summary synthesis

Triggered when ≥ 80% of framework subsections are `已完成`.

1. Offer the user: "Ready to synthesize 执行摘要 (Part 0)? [yes / not yet]"
2. If `yes`:
   - Main agent reads the profile file.
   - Extracts:
     - Thesis from §1 商业模式 summary + §3 护城河 summary + §4 管理 summary → 3 bullets (是否买 / 什么价位 / 为什么).
     - 估值 (current price / PE / PB / yield / 3y 市值 target) from §4.1-§4.3.
     - Top 3 risks (from §5 and §4.5 爆雷 红旗).
     - Conviction level: derived from average 置信度 across Parts 1-2 (高 if ≥ 60% 高, 中 if mixed, 低 if any block is 未做).
   - Drafts Part 0 in Chinese.
3. User gate, then save.
```

- [ ] **Step 2: Verify**

Run: `grep -c "^### Step " /Users/brian_huang/repos/ah-research/.claude/skills/value-profile/SKILL.md`
Expected: `6`.

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "feat(skill): value-profile — Part 2 bulk, 爆雷 checklist mode, 执行摘要 synthesis"
```

---

### Task 17: Skill — guardrails + language policy + must-not list

**Files:**
- Modify: `.claude/skills/value-profile/SKILL.md`

- [ ] **Step 1: Append guardrails section**

Add at the bottom of SKILL.md:

```markdown
## Language policy

- **Profile output (the .md file content):** Chinese. Every 填写区, 引用, 管理层口径校核, 总结 line must be in Chinese. Tables may use English column headers where concise (e.g. the 爆雷 checklist has English # column); content cells are Chinese.
- **Operator interaction (chat gates, status lines, errors):** bilingual. English for agent-facing instructions and status; Chinese for section drafts shown to the user.
- **Error messages:** bilingual (Chinese first, English second).

## What this skill MUST NOT do

- Must NOT rewrite sections the user has marked `已完成` without an explicit `--force` (not in v0 — just don't rewrite).
- Must NOT fabricate numbers or citations. If a number cannot be sourced from 年报 or a URL, write `待补充` with the reason.
- Must NOT write 填写区 content in English. Operator status lines can be English/bilingual.
- Must NOT proceed if `data/filings/<ticker>/` has fewer than 2 年报 PDFs — block with the download instruction from Step 1.2.
- Must NOT run `git commit`. The user handles commits themselves.
- Must NOT call into `ah_research/` Python code — the library isn't built yet. (Will change when Phase 1 of the platform design lands; at that point, update this skill to prefer `DataRepository` for Part 2 numeric cells over PDF parsing.)
- Must NOT attempt to auto-download 年报 PDFs. Acquisition is manual in v0.

## Failure modes & recovery

| Failure | Recovery |
|---|---|
| Subagent returns output lacking citations | Main agent rewrites with `证据不足, 需人工补充` for the uncited points; does NOT fabricate |
| User says "accept" but the 管理层口径校核 line is trivial | Still save (user is sovereign); but main agent should have flagged trivial spin-check in Step 3b review |
| `年报-YYYY.pdf` file exists but is corrupted / unreadable | Log the failure, note it in the section's 引用 field as `年报-YYYY.pdf (unreadable)`, continue with other sources |
| Profile file has merge conflicts (two sessions writing) | Don't resolve automatically; print a warning and ask user to resolve in their editor |
| Subagent quota / rate-limit failures during PDF reads | Retry once with narrower page range; if still failing, save partial section with `待补充` and move on |

## Graduation path

Once Phase 1 of `ah-research` ships (`DataRepository` is available):

1. Update Step 4 (Part 2 bulk) to prefer a subagent that calls `ah_research.DataRepository.get_fundamentals(<ticker>, start=<10y ago>)` rather than parsing 年报 PDFs for numeric cells. Cite the fetch parameters in **来源:** instead of page numbers. Fall back to PDF parsing only for cells the repository doesn't cover.
2. Update Step 5 (爆雷 checklist) items #12, #23, #28 (quantitative checks) to route through `DataRepository`.
3. Qualitative sections (§1-§5, §4.5 qualitative items) continue reading 年报 PDFs — this is not graduated.
```

- [ ] **Step 2: Verify**

Run: `grep -c "^## " /Users/brian_huang/repos/ah-research/.claude/skills/value-profile/SKILL.md`
Expected: `≥ 5` (Invocation, Behavior, Language policy, MUST NOT, Failure modes, Graduation path).

- [ ] **Step 3: Commit**

```bash
git -C /Users/brian_huang/repos/ah-research commit -am "feat(skill): value-profile — guardrails, language policy, failure recovery, graduation path"
```

---

### Task 18: Skill smoke-test — frontmatter parses + trigger detection

**Files:** (read-only)

- [ ] **Step 1: Verify frontmatter is valid YAML**

Run:
```bash
python3 -c "
import re, yaml, sys
text = open('/Users/brian_huang/repos/ah-research/.claude/skills/value-profile/SKILL.md').read()
m = re.match(r'---\n(.*?)\n---', text, re.DOTALL)
if not m:
    print('ERROR: no frontmatter'); sys.exit(1)
meta = yaml.safe_load(m.group(1))
assert 'name' in meta and meta['name'] == 'value-profile', 'bad name'
assert 'description' in meta and len(meta['description']) > 100, 'description too short'
print('OK:', meta['name'], '-', meta['description'][:80], '...')
"
```
Expected: `OK: value-profile - Walk a user through filling out a 价值投资 profile for a single A-share ...`

- [ ] **Step 2: Verify body structure**

Run:
```bash
wc -l /Users/brian_huang/repos/ah-research/.claude/skills/value-profile/SKILL.md
grep -c "^## " /Users/brian_huang/repos/ah-research/.claude/skills/value-profile/SKILL.md
grep -c "^### Step " /Users/brian_huang/repos/ah-research/.claude/skills/value-profile/SKILL.md
```
Expected:
- Line count: 200-400
- `##` sections: ≥ 5
- `### Step`: 6

- [ ] **Step 3: No new commit** (verification only).

---

## Phase 4 — Filings + first dogfood run

### Task 19: User downloads Moutai 年报 PDFs (manual)

**This is a user-driven step; the plan describes what to download. A subagent cannot do this.**

- [ ] **Step 1: Download 600519.SH 年报 PDFs from 巨潮资讯网**

The user opens https://www.cninfo.com.cn, searches `600519`, navigates to 公告 → 年度报告, and downloads:
- 2024 年报 (published ~April 2025)
- 2023 年报
- 2022 年报
- 2021 年报
- 2020 年报

Save each file as `年报-<YYYY>.pdf` (matching the 会计年度 end year) in `/Users/brian_huang/repos/ah-research/data/filings/600519.SH/`.

- [ ] **Step 2: Download 招股说明书**

Same source, search for 600519's original 2001 招股说明书 (上海证券交易所 首发). Save as `招股说明书.pdf`.

- [ ] **Step 3: Optional — 2-3 depth 研报**

From 研究员工作站 (or public free sources if available), download 2-3 白酒行业 / 茅台 depth reports. Save to `data/filings/600519.SH/研报/<来源>-<主题>.pdf`.

- [ ] **Step 4: Verify directory contents**

Run:
```bash
ls -la /Users/brian_huang/repos/ah-research/data/filings/600519.SH/
```
Expected: `年报-2020.pdf` through `年报-2024.pdf`, `招股说明书.pdf`, optionally `研报/`.

Run:
```bash
du -sh /Users/brian_huang/repos/ah-research/data/filings/600519.SH/
```
Expected: ~100-300 MB for 5y 年报 + 招股说明书.

- [ ] **Step 5: Commit the PDFs**

```bash
cd /Users/brian_huang/repos/ah-research
git add data/filings/600519.SH/
git commit -m "data(filings): add Moutai (600519.SH) 年报 2020-2024 + 招股说明书"
```

---

### Task 20: First run — Part 1 §1 商业模式 (dogfood iteration 1)

**This task exercises the skill for the first time. Record observations — they feed into go/no-go criteria from spec §6.**

- [ ] **Step 1: Invoke the skill**

In a Claude Code session at `/Users/brian_huang/repos/ah-research`, run:
```
/value-profile 600519.SH
```

Expected: bootstrap passes (filings audit: 5 年报 + 招股说明书 found), `profiles/600519.SH-2026-04-28.md` created from template, Part 0 header filled, progress map shown with `未做` for 50+ sections.

- [ ] **Step 2: Work through §1.1-§1.7 商业模式**

For each of §1.1-§1.7:
1. Let the skill dispatch a research subagent (PDF + web).
2. Review the draft. Reject with `research more: <hint>` if the answer is generic (e.g., "strong brand, good products" without 茅台镇 / 12987 / 基酒 specifics).
3. Accept or edit and accept. Confirm the section block is written to the profile file.

**Time budget:** 60-75 min across §1.1-§1.7.

- [ ] **Step 3: Spot-check the profile file between sections**

After accepting §1.1, open `profiles/600519.SH-2026-04-28.md` in an editor. Verify:
- §1.1 block is present with filled 填写区.
- 引用 field has at least 1 `年报-*.pdf p.NN` citation.
- 置信度 is 高 / 中 / 低.
- 管理层口径校核 is a non-trivial 1-line statement.

- [ ] **Step 4: Commit the partial profile**

```bash
cd /Users/brian_huang/repos/ah-research
git add profiles/600519.SH-2026-04-28.md
git commit -m "profile(600519.SH): Part 1 §1 商业模式 complete (7 subsections)"
```

---

### Task 21: First run — Part 1 §2-§5 (定性 rest)

- [ ] **Step 1: Work through §2 成长空间 (6 subsections)**

Time budget: 30 min.

- [ ] **Step 2: Work through §3 护城河 (10 subsections)**

Time budget: 60-90 min. The §3 护城河 section is the most critical go/no-go signal (spec §6 criterion 1). **Watch for generic output and push back hard.**

- [ ] **Step 3: Work through §4 管理与文化 (7 subsections)**

Time budget: 60-75 min. Cross-source work is essential here (spec §6 criterion 2). Specifically check: 高卫东 反腐 事件, 丁雄军 任期 执行重点, 张德芹 接任 策略变化 — does the skill surface these? If not, push back.

- [ ] **Step 4: Work through §5 风险分析 (5 subsections)**

Time budget: 30 min.

- [ ] **Step 5: Commit**

```bash
cd /Users/brian_huang/repos/ah-research
git add profiles/600519.SH-2026-04-28.md
git commit -m "profile(600519.SH): Part 1 §2-§5 complete (成长 + 护城河 + 管理 + 风险)"
```

---

### Task 22: First run — Part 2 定量 (bulk mode)

- [ ] **Step 1: Trigger Part 2 bulk mode**

In the running skill session, select Part 2 §Q1. When prompted, choose `bulk`.

Time budget: 30-45 min for the subagent to read 5y of 年报 + fill all tables + cross-check 雪球.

- [ ] **Step 2: Sanity-check 5 random cells against 雪球**

For each of 5 random cells in Part 2 (e.g. 2022 ROE, 2021 毛利率, 2020 净现比, 2023 资产负债率, 2024 经营现金流净额):
1. Open 雪球 F10 for 600519.
2. Compare the profile's value to 雪球's.
3. Record matches vs mismatches.

**Go/no-go:** ≥ 4/5 agreement. Otherwise investigate (PDF misread? 雪球 discrepancy? calendar?).

- [ ] **Step 3: Commit**

```bash
cd /Users/brian_huang/repos/ah-research
git add profiles/600519.SH-2026-04-28.md
git commit -m "profile(600519.SH): Part 2 定量 (10y tables, 年报-cited, 雪球 cross-checked)"
```

---

### Task 23: First run — Part 4 买入清单 + 爆雷清单

- [ ] **Step 1: Work through §4.1-§4.4 估值分析**

Current PE / PB / 股息率 (from 雪球), vs 10y 历史 band; 3y 净利润 / 市值 测算. Time: 30 min.

- [ ] **Step 2: Trigger §4.5 爆雷 checklist mode**

Let the subagent run through all 29 items. Read the filled table carefully.

**Expected findings for Moutai:** items #3 存贷双高 (false — no debt), #11 大股东股权质押 (false — 国资委), #16 商誉 (false — zero or minimal), #24 客户集中度 (true in经销 sense but flagged as 不适用 for baijiu), #29 关联交易 (flag — 国企有关联交易).

If the checklist flags >5 items as `需人工` or says everything is fine (0 red flags for a company with 国企 structure), the skill's prompt needs refinement.

Time: 30-45 min.

- [ ] **Step 3: Work through §4.6-§4.9 (仓位 / 加仓 / Final / 心理偏误)**

User-driven; skill mostly asks templated questions. Time: 15 min.

- [ ] **Step 4: Commit**

```bash
cd /Users/brian_huang/repos/ah-research
git add profiles/600519.SH-2026-04-28.md
git commit -m "profile(600519.SH): Part 4 买入清单 + 29-item 爆雷 clear"
```

---

### Task 24: First run — Part 3 未来 + Part 5 持有清单 + Part 0 执行摘要

- [ ] **Step 1: Part 3 未来 (6 subsections)**

Time: 30 min.

- [ ] **Step 2: Part 5 持有清单 (5 subsections)**

Mostly templated. Time: 15 min.

- [ ] **Step 3: Part 0 执行摘要 synthesis**

Trigger executive summary mode. Verify: 3-bullet 论点 is specific and defensible, not generic. 估值 numbers cross-check against §4. Risks match §5 + §4.5 红旗.

Time: 15-30 min.

- [ ] **Step 4: Commit — first profile complete**

```bash
cd /Users/brian_huang/repos/ah-research
git add profiles/600519.SH-2026-04-28.md
git commit -m "profile(600519.SH): complete — Part 3/5/0 filled, v1 dogfood"
```

---

### Task 25: Go/no-go evaluation against spec §6

**Files:** `docs/superpowers/specs/2026-04-28-value-profile-skill-design.md` §6 criteria.

For each criterion, answer Pass / Partial / Fail with one line of evidence from the profile file.

- [ ] **Step 1: Read spec §6 go/no-go criteria (4 items)**

Open `docs/superpowers/specs/2026-04-28-value-profile-skill-design.md` lines around §6 "Go/no-go criteria after first run".

- [ ] **Step 2: Evaluate**

Copy into a scratch evaluation file `profiles/600519.SH-2026-04-28-evaluation.md`:

```markdown
# Go/no-go Evaluation — 600519.SH v1 dogfood

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | §3 护城河 specific to Moutai (茅台镇 / 12987 / 基酒 / 价格带) | Pass / Partial / Fail | <profile section §3.1 paragraph ...> |
| 2 | §4 管理 engages SOE + 高卫东 反腐 vs hedges | Pass / Partial / Fail | <profile §4.2 管理层口径校核 line> |
| 3 | 爆雷 29-item checklist surfaces ≥ 2-3 legitimate concerns | Pass / Partial / Fail | <profile §4.5 红旗 summary> |
| 4 | Quantitative cells cite 年报 pages, ≥ 4/5 雪球 agreement | Pass / Partial / Fail | <task 22 step 2 result> |
| 5 | Usable as buy / no-buy / sizing decision input | Pass / Partial / Fail | <executive summary quality> |

## Overall verdict

<Pass / Needs-work>

## Revisions needed if Needs-work

- Section-worker prompt changes: ...
- Template structure changes: ...
- Spec §6 criteria changes: ...
```

- [ ] **Step 3: Commit evaluation**

```bash
cd /Users/brian_huang/repos/ah-research
git add profiles/600519.SH-2026-04-28-evaluation.md
git commit -m "profile(600519.SH): go/no-go evaluation v1"
```

- [ ] **Step 4: Decide next steps**

If overall verdict = **Pass** → skill is real; consider second ticker (per spec §10 #3 — pick a mid-cap A-share with <5 sell-side covers). Update skill frontmatter description with any lessons learned.

If overall verdict = **Needs-work** → revise the section-worker prompt in SKILL.md § Step 3a based on the specific failures; re-run the failing sections on Moutai to verify improvement.

---

## Self-review checklist

Before handing off to executor, verified by plan author:

- [x] Spec coverage: every §3-§9 item in the spec maps to a task (T1-T25 cover scaffolding, template, skill, dogfood, go/no-go).
- [x] No placeholders: every file-creation step shows the exact content or defines the reusable pattern. Phase 2 uses a pattern + list of subsections with the user's original framework as the reference document (this is acceptable because repeating a 50-line block 50 times would make the plan unreadable).
- [x] Type consistency: skill uses `§X.Y` section IDs consistently in both template and skill; progress map format uses same `{"1.1": "已完成", ...}` form.
- [x] Bite-sized: Phase 1 / 3 / 4 tasks are 5-15 min each. Phase 2 tasks are 10-20 min each (one per framework Part — acceptable given the content volume).
- [x] TDD-shaped where possible (verification steps after each file creation). Template and skill don't have unit tests — verification is grep-based structural checks, which is appropriate for markdown.
- [x] Frequent commits: every task ends with a commit. First dogfood run (Tasks 20-25) commits per section batch.

---

## Execution record (post-hoc, 2026-04-28)

What actually happened vs the plan. `git log --oneline` is the canonical history; this section captures intent and deviations.

### Branching setup (not in original plan)

The original plan assumed single-branch execution on `feat/phase-0-1-scaffold`. Mid-execution, another agent was concurrently committing Phase 0/1 platform-scaffold work to the same branch. To prevent commit-hygiene pollution, a git worktree was created:

- `/Users/brian_huang/repos/ah-research-vp` → branch `feat/value-profile` (branched from `feat/phase-0-1-scaffold` HEAD after T1-T4)
- All execution from T5 onward happened in the worktree. The original repo kept the other agent's Phase 0/1 work undisturbed.

### Task completion map

| Plan task(s) | Actual commit(s) | Notes |
|---|---|---|
| T1 — template file skeleton | `8e25bfa` | On `feat/phase-0-1-scaffold`, inherited by worktree |
| T2 — filings README + 600519.SH dir | `81b0aa6` | Commit bloat: swept in pre-staged `src/ah_research/cli.py` from the other agent |
| T3 — profiles dir | `daff7d2` | |
| T4 — skill file skeleton (frontmatter only) | `cf65185` | |
| (v3 spec revision — not originally in plan) | `620ee94` | Added automated fetcher scope + worktree notes |
| **Inserted: "T4.5" fetcher build** (not in original plan) | `20d2da2` (code + tests) + `f03744b` (Moutai PDFs) | User-requested scope addition mid-execution. Replaces T19's "manual PDF download" step. Single consolidated commit for code (subagent's call) instead of the plan's 3 separate commits — justified in commit body |
| T5-T13 — template body (Parts 0-5 + verification) | `e16645f` | **Bundled**: single subagent dispatch + single commit. 1567 lines, 67 subsections, 29-row 排雷 table. Grep verification inline |
| T14-T18 — skill body (bootstrap + section worker + modes + guardrails + smoke test) | `6ada96a` | **Bundled**: single subagent dispatch + single commit. 255 lines, 6 behavior steps. Frontmatter YAML parseable; skill registers and is visible in the Claude Code skill list as `value-profile` |
| T19 — manual Moutai PDF download | superseded | Replaced by `python scripts/download_filings.py 600519.SH --years 5 --include-prospectus` (T4.5 output). Ran live against cninfo; 5× 年报 (2021-2025) + 招股说明书 downloaded |
| T20-T25 — dogfood run on Moutai | pending user | User-interactive. Skill ready; invoke with `/value-profile 600519.SH` from the worktree |

### Bundling rationale

The plan split template body into 8 tasks (T5-T12) and skill body into 5 tasks (T14-T18) for bite-sized granularity. In practice, both were bundled into single subagent dispatches. Reasons:

1. Template body is repetitive pattern-application across ~50 subsections — a single subagent with the full inventory produced a coherent file faster than 8 sequential dispatches with cross-task continuity concerns.
2. Skill body is a single coherent operational document — splitting it across 5 commits would produce broken intermediate states.
3. Subagent output was verified inline via grep counts (Parts, subsections, 置信度 fields, 排雷 rows) — the plan's per-task verification steps fold into one final verification per bundle.

This deviation is acceptable for a markdown/skill-definition artifact; a code change of this scale would warrant keeping the finer granularity for reviewability.

### Concrete artifacts produced

All in `/Users/brian_huang/repos/ah-research-vp`:

- `docs/value-profile/template-zh.md` — 1567 lines, Chinese framework scaffold
- `.claude/skills/value-profile/SKILL.md` — 255 lines, skill operational spec
- `scripts/download_filings.py` — 330 lines, cninfo fetcher
- `tests/test_download_filings.py` — 33 tests, all offline (fixture-based)
- `tests/fixtures/cninfo/` — recorded API responses for test replay
- `data/filings/600519.SH/` — 5× `年报-YYYY.pdf` (2021-2025) + `招股说明书.pdf`, ~15 MB total
- `profiles/.gitkeep` — empty output directory
- `data/filings/README.md` — fetcher usage + naming conventions
- `docs/superpowers/specs/2026-04-28-value-profile-skill-design.md` — v3, 138 lines (after v3 rewrite)

### Unverified claims / known caveats

- The skill has NOT been dogfooded end-to-end yet. Step 1 bootstrap (filings audit, fetcher offer, template copy) is designed but untested in an actual skill invocation. The dogfood run (T20+) is the verification event.
- Spec §9 success criterion 7 (fetcher works without manual intervention) IS verified — live run on Moutai succeeded with idempotency confirmed on re-run.
- Subagent prompt templates inside SKILL.md Step 3b are self-written (by the skill-body subagent); their effectiveness is only verifiable by running the skill against a real section.
- No linter / formatter runs against markdown content. Rendering was eyeballed via grep + line count, not rendered preview.

---

**End of plan.**
