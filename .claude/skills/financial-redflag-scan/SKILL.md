---
name: financial-redflag-scan
description: 对 A 股 / 港股公司年报做 29 项财报排雷 + 6 项高危模式扫描, 产出"看哪里 / 触发条件 / 应采取动作 / 是否触发 + 证据"结构化清单。可独立运行（`/redflag-scan <ticker>`）写 standalone 报告, 也可作为 value-profile 主 skill 的 §4.5 section 子模块填入已有 profile。基于年报第五节"财务报告" + 附注 + 第十节"审计报告"。Trigger on "/redflag-scan <ticker>", "财报排雷 <ticker>", "排雷 <ticker>".
---

# Financial Red-Flag Scan Skill

本 skill 是 value-profile 主 skill 的子 skill, 专门负责"财报排雷 + 造假高危模式扫描"。结构分三层: **§1 原则 → §2 规则 → §3 流程**。

## §0 运行模式

### Mode A — Standalone

- **Invocation**: `/redflag-scan <ticker>` / `财报排雷 <ticker>` / `排雷 <ticker>`
- **行为**: 子 skill 独立完成 ticker 验证 + filings audit + PDF 抽取 + 派子 agent 扫 29 项 + 6 项高危 overlay + 主 agent 复核 + 写 standalone 报告
- **Output path**: `profiles/<ticker>-redflags-<YYYY-MM-DD>.md` — self-contained 报告, 约 150-250 行
- **典型场景**: 用户对某 ticker 做快速排雷扫描, 发现红旗直接剔除, 不需要完整 value-profile

### Mode B — As-subroutine

- **Invocation**: 主 value-profile skill 在 Step 5 遇到 §4.5 排雷时 delegate, 传参 `--target-profile <path> --section §4.5`
- **行为**: 信任主 skill 已做过 Step 1 (ticker 验证 + filings audit + PDF 抽取); 跳过这些, 直接从 Step 3 开始
- **Output**: 用 Edit 工具把子 agent 产出填入 `<target-profile>` 的 §4.5 section block, **不新建文件**
- **典型场景**: 用户跑 `/value-profile <ticker>`, 主 skill 推进到 §4.5 时自动调用本 skill

### Invocation 解析

- 参数只有 ticker → Mode A (Standalone)
- 参数含 `--target-profile <path>` → Mode B (As-subroutine)
- Ticker 正则: `^[0-9]{4,6}\.(SH|SZ|HK)$`

### 运行时必读 reference

本 skill 的**深度操作手册**在 `references/fraud-library.md`: 红旗 10 项（§1）+ 三表勾稽 4 条（§2）+ 造假 5 维度（§3）+ pattern A1/A2/A3 narrative（§4）。子 skill 派子 agent 前, 主 agent 先 Read 本文件, 并把 §1-§4 的阈值具体内化到 subagent prompt 中。必读附注 12 项的原始数据由上游 `read-filing` 的 `references/statement-reading.md §3` 产出。

---

## §1 排雷原则

精炼 5 条。

### §1.1 年报正文是管理层 PR, 真相在附注

董事会报告 / 经营情况讨论是管理层美化口径, 读快扫即可。**红旗的真正藏身处是附注**: 应交税费 / 关联交易 / 对外担保 / 其他应收款明细 / 存货构成 / 商誉减值测试假设 / 金融资产 4 分类。正文不读则已, 读也只用来对比附注是否在说同一件事。

### §1.2 三表勾稽不一致即风险

资产负债表 / 利润表 / 现金流量表必须互相对得上。任一表的数字不能被另两张表交叉验证 → 疑点。关键公式（见 references/fraud-library.md §2）必须跑完 4 条, 不过的项目直接标 `需人工`。

### §1.3 造假 6 类高危模式 → profile 降级

商誉 / 其他应收 / 在建工程 / 经营现金流 / 生物资产 / 管理层道德红旗, 任一触发 → 即使 §1-§3 生意模式再好, profile 整体降级或 abstain。高危模式的优先级高于好生意判断。

### §1.4 排雷是强制步骤, 不是可选

每份 profile（或 standalone 报告）**必须**跑完 29 项清单 + 6 项 overlay。跳过等于 profile 失效。所以本 skill 的用户确认节点**不接受 `defer` / `skip`**, 只接受 `accept / edit / research more`。

### §1.5 排雷是定量, 不要靠感觉

每项必须给阈值 + 证据（页码 + 金额）。禁 "看起来商誉有点高" 这类主观判断, 要 `商誉 / 净资产 = XX% > 20% 阈值 (年报-2024.pdf p.NN)` 这种量化形式。

---

## §2 排雷规则

### §2.1 29 项清单逐项扫（§1.4 推出）

- **§2.1.1 清单来源**: 完整 29 项列在主 template §4.5 block（`.claude/skills/value-profile/template-zh.md` 第 1452 行起）。本 skill 派子 agent 时把 29 项 inline 嵌入 prompt。
- **§2.1.2 每项格式**: `看哪里 | 触发条件（量化阈值）| 应采取动作 | 是否触发 + 量化证据`
- **§2.1.3 结果值域**: `是 / 否 / 不适用 / 需人工` — 4 选 1, 每项必答

### §2.2 6 项高危 overlay（§1.3 推出）

即使不在 29 项清单中, 以下 6 项必须显式 flag:

1. **商誉 / 净资产 > 20%** → 雷区, 未来可能一次性减值使净资产腰斩
2. **其他应收款 ≥ 10% 流动资产** 或 单一关联方长年挂账 → 关联方占款
3. **在建工程长期不转固**（> 3 年）→ 挂账操纵折旧
4. **CFO / NI < 50% 连续 2 年** → 利润真实性红旗, 可能应收膨胀
5. **生物资产 / 农林渔牧** → 獐子岛式造假高危, 资产端不可查
6. **管理层道德红旗**（历史虚假陈述 / 违规处罚 / 股东利益输送）→ 直接大幅降级, 不再讨论生意好坏

### §2.3 三表勾稽 4 条必跑（§1.2 推出）

- **§2.3.1 真实营收**: `真实营收 ≈ 营收 + Δ合同负债 − Δ应收账款 − Δ应收票据(商票部分)`。真实营收 << 报表营收 → 利润被提前确认。
- **§2.3.2 销售收现比**: `销售商品提供劳务收到的现金 / (营业收入 × (1+VAT))` ≥ 1.0 (±5%) 健康。< 1 连续 2 年 → 应收或合同负债异常。
- **§2.3.3 净利润 → CFO 桥**: `CFO = NI + 折旧摊销 − Δ应收 − Δ存货 + Δ应付 + Δ合同负债 + 其他非现金`。每一项有合理解释, 不平的部分可疑。
- **§2.3.4 维持性 CapEx 近似**: `维持性 CapEx ≈ 折旧摊销 × (1+通胀系数)`; `自由现金流 ≈ CFO − 维持性 CapEx`。

### §2.4 引用 + 证据规则（§1.5 推出）

- **§2.4.1 量化证据**: 任一 `是 / 需人工` 必须给 `金额 + 阈值对比 + 年报页码`。例: `是 | 商誉 42 亿 / 净资产 180 亿 = 23% > 20% 阈值 [年报-2024.pdf p.87] | 追查商誉减值假设`。
- **§2.4.2 不接受"根据经验"**: 触发动作必须具体（`追查前 5 大客户账龄结构` / `降置信度一档` / `剔除投资池`）, 不能留空或 "待补充"。

### §2.5 管理层道德红旗 = 一票否决（§1.3 推出）

历史虚假陈述 / 违规处罚记录 / 股东利益输送 / 大股东占款 → 直接大幅降级, Mode A 报告结论 "剔除"; Mode B 回填主 profile §4.5 时 `**置信度:** 低` + 建议主 profile Part 0 标 "不可估值"。

### §2.6 summary 段落写法

- **§2.6.1 结果不是简单列表**: 29 项扫完后写 `**发现的红旗 summary:**` 1-2 段, 聚焦 `是 / 需人工` 项, 说明 ① 雷是什么 ② 为何对本 ticker 重要 ③ 交叉验证的下一步。
- **§2.6.2 若 29 项 + 6 项 overlay 全 "否 / 不适用"**: 明确写 "本次扫描未发现重大红旗, 但需警惕 <1-2 个仍需人工观察的灰色区>", 不允许空泛地说 "无雷"。

### §2.7 用户确认仅 3 选 1（§1.4 推出）

用户确认节点 只提供 `[accept / edit / research more]`。**不 offer `defer` / `skip`**——排雷是强制的。

---

## §3 分析流程（Step 1-5）

### Step 1 — Bootstrap（仅 Mode A）

Mode B 跳过, 信主 skill 已做。

1. **Validate ticker** against `^[0-9]{4,6}\.(SH|SZ|HK)$`。失败 abort。
2. **Audit `data/filings/<ticker>/`**: `年报-*.pdf` < 2 份 → offer fetcher; 本 skill 核心是最新一年深扫, 但需 2 年做增速 / 连续性判断。
3. **PDF 预抽取 cache**: `_extracted/<年报-latest>/text.md` 必存在; 缺失 → offer `scripts/extract_pdf.py`。
4. **Read reference**: 主 agent Read `references/fraud-library.md` §1-§4 把阈值 / 勾稽 / 造假模式内化; 附注 12 项原始数据来源见 `../read-filing/references/statement-reading.md §3`。

### Step 2 — 模式判定 + Output 准备

1. **解析 invocation**:
   - 无 `--target-profile` → Mode A
   - 有 `--target-profile <path> --section §4.5` → Mode B

2. **Mode A 准备**: 新建 `profiles/<ticker>-redflags-<YYYY-MM-DD>.md`:

   ```markdown
   # <中英文公司名> 财报排雷 — <ticker>

   **研究者:** <git config user.name>
   **报告日期:** <today>
   **基于年报:** 年报-<latest>.pdf (p.XX-YY)
   **模式:** standalone

   ## §4.5.1 29 项清单扫描
   [表格: 项号 | 看哪里 | 触发条件 | 应采取动作 | 是否触发 + 证据]

   ## §4.5.2 6 项高危 overlay
   [逐项 flag]

   ## §4.5.3 三表勾稽 4 条
   [逐条公式 + 实际数 + 结论]

   ## §4.5.4 发现的红旗 summary
   [1-2 段]

   ## §4.5.5 结论 verdict
   [无重大红旗 / 有保留 / 剔除]
   ```

3. **Mode B 准备**: Read `<target-profile>`, 定位 `### §4.5 负面清单` 或 `### §4.5 负面清单 — 排雷风险（29 项）` block, 记住起止行号, 准备替换。

### Step 3 — 派 subagent 排雷

派 ONE `general-purpose` 子 agent, prompt 英文, 强制中文输出。**必须包含**:

- ticker, 中英文公司名, exchange, report_date
- 强制使用 `_extracted/年报-<latest>/text.md` 绝对路径为主数据源; 含 `<!-- page N -->` markers
- 对比用 `_extracted/年报-<latest-1>/text.md` 做 2 年连续性判断
- **29 项完整清单**: inline 从主 template §4.5 block 拉, 或直接内化到 prompt 中（看哪里 / 触发条件 / 应采取动作 三列 + 要求子 agent 填第 4 列）
- **6 项高危 overlay**: 即使不在 29 项里也必须 flag; 阈值见 §2.2
- **三表勾稽 4 条**: §2.3, 必跑, 给出实际数字 + 年报页码
- **每项回答**: `是 / 否 / 不适用 / 需人工` + 1 句量化证据（含金额 + 阈值对比 + 页码）+ 触发时写出实际动作
- **禁用 "根据经验"**: 所有判断必须带页码或 URL
- **summary 段落**: 子 agent 输出末尾写 `**发现的红旗 summary:**` 1-2 段

子 agent 必读附注（对应 §4.5 29 项高覆盖）:
- 货币资金受限 / 应收账款 5 大客户 + 账龄 / 应收票据 银票 vs 商票 / 预付账款对象 / 其他应收款关联方 / 存货分项 + 跌价 / 在建工程转固 / 商誉减值假设 / 合同负债占营收 / 应付账款议价权 / 长投 + 金融资产分类 / 有息负债结构

### Step 4 — 主 agent 复核

读子 agent 产出。**驳回并 re-dispatch**若任一:

- 任一 `是 / 需人工` 缺量化证据 → 退回补页码 + 金额
- 29 项少答 / 跳答 → 退回补齐
- 6 项高危 overlay 未显式 flag → 退回重扫
- 三表勾稽 4 条漏跑 → 退回补
- summary 段落空洞 / 仅列表 → 退回改写 §2.6.1 格式
- Mode B 子 agent 填了主 profile §4.5 以外的 section → 退回

Acceptable 后写中文终稿。

### Step 5 — 写 summary + Output

**Mode A**:
- 原子写入 `profiles/<ticker>-redflags-<YYYY-MM-DD>.md`
- 填 §4.5.5 结论 verdict — 3 选 1: `无重大红旗 / 有保留 / 剔除`
- 若 verdict = 剔除, 加 `> ⚠️ 本 ticker 触发 <红旗列表>, 建议不进入投资池; 主 value-profile 若正在进行, 应标 Part 0 "不可估值".`

**Mode B**:
- 用 Edit 工具替换 `<target-profile>` 中 `### §4.5 负面清单` ... 到下一个 `### §` 或 `## §` 之间的整段
- **仅替换 §4.5 block, 保留其他 section 原样**
- 保留主 profile §4.5 heading 下的 HTML 注释（来自主 template）

**用户确认节点**: `[accept / edit / research more]`。**不 offer `defer` / `skip`**——§1.4 / §2.7 排雷强制。

---

## §4 Policy

- **中文输出**: 填写区 / 引用 / 置信度 / summary / verdict 均中文
- **CJK-ASCII 空格规则**: "ROE15%" 非 "ROE 15%"; "商誉/净资产" 非 "商誉 / 净资产"（表格内保留斜杠可读）
- **引用必带页码**: `(年报-YYYY.pdf p.NN)` 格式
- **子 agent 输出禁空话**: "财务稳健 / 经营规范 / 无重大风险" 无具体数字 → 退回
- **不大段拷贝年报**: 抽取关键数字 + 金额 + 页码; 原话仅在疑点场景做 1-2 句引用

---

## §5 MUST NOT

- MUST NOT 编造数字 / 金额 / 页码。无来源写 `证据不足, 需人工补充`
- MUST NOT 跑 `git commit`——用户自 commit
- MUST NOT Mode B 下改主 profile 的 §4.5 之外的其他 section
- MUST NOT Mode A 下把生意模式 / 估值 / 管理层 写进本 skill 输出——本 skill 仅管排雷
- MUST NOT 接受 `defer` / `skip`——排雷强制
- MUST NOT 用英文写 profile 内容
- MUST NOT 在没有 `_extracted/年报-<latest>/text.md` 的情况下开扫（Mode A 下 Step 1.3 必须先 extract; Mode B 下信主 skill）

---

## §6 References — 共享自 value-profile 主 skill

本 skill **引用**以下 reference（不复制内容）:

- `references/fraud-library.md` — **必读**, 本 skill 的深度操作手册:
  - §1 红旗 10 项（6 项高危 overlay 的阈值来源）
  - §2 三表勾稽 4 条公式（§2.3 的公式来源）
  - §3 造假 5 维度（收入端 / 成本端 / 现金端 / 利润端 / 结构端）
  - §4 pattern narrative A1/A2/A3（channel stuffing / inventory hiding / vendor squeeze）
- `../read-filing/references/statement-reading.md` §3 — 必读附注 12 项（对应 29 项清单的附注原始数据来源 — 由上游 read-filing 产出）
- `../read-filing/references/statement-reading.md` §6 — 特殊场景加读清单（商誉 > 20% / 有息负债 > 净资产 / 金融资产 > 营收 等）
- `.claude/skills/value-profile/references/moat-framework.md` — 了解生意模型以判断某些红旗的严重性（例: 消费品行业商誉 20% 严重, 周期行业可能只是并购周期）

派子 agent 时, 若需更深操作手册, 在 prompt 里明确告知 "reference 路径 = `.claude/skills/financial-redflag-scan/references/fraud-library.md` 第 N 节"。附注 12 项原始数据路径: `.claude/skills/read-filing/references/statement-reading.md §3`。

---

## §7 主 skill 调用契约（Mode B）

主 value-profile skill Step 5 遇 §4.5 时如下 delegate:

```
子 skill: financial-redflag-scan
传参: --target-profile profiles/<ticker>-<date>.md --section §4.5
期望: 子 skill 填完 §4.5 block (29 项清单 + 6 项 overlay + 三表勾稽 + summary) 后交还控制
```

子 skill 完成后返回主 skill 的 Step 5 用户确认节点, 用户选 accept → 进度标 `已完成`; 选 research more → 把 hint 附加 re-dispatch Step 3 子 agent。

子 skill 若发现 §2.5 管理层道德红旗 → 同步建议主 skill Part 0 标 "不可估值", 主 skill 下一步应联动调用 management-analysis 子 skill 深查 §4。

---

## §A 造假模式 narrative 库（子 agent prompt 附加深度上下文）

29 项硬清单是**数字触发**; 以下 3 个**模式 narrative** 帮子 agent 理解**为什么**数字异常 = 真实造假信号。主 agent 派 subagent 时作为 "pattern library" 附在 prompt 里, 不进 29 项计分, 但触发时必须在笔记中引用。

### A1 客户塞货 (channel stuffing)
- **信号组合**: AR 增速 > 营收增速 ≥ 20pp **且** 存货增速 > 营收增速 ≥ 20pp **且** 应付账款 (AP) 增速趋缓 / 压缩
- **为什么**: 公司把货硬压给经销商, 确认营收; 经销商卖不动导致 AR 积压 + 自家存货同步膨胀; 同时供应商也知道销售疲软, 不再给信用期, AP 不增反降
- **典型场景**: 白酒 / 消费品渠道库存周期顶部; 集采前夕的医药公司

### A2 库存减值掩盖 (inventory obsolescence hiding)
- **信号组合**: 存货周转天数翻倍以上 **且** 毛利率保持稳定 **且** 存货跌价计提 / 存货 比值 10 年不升反降
- **为什么**: 存货占用资金翻倍 = 滞销; 正常情况毛利率应下降 (降价清库) 但却稳定 = 没做减值; 跌价计提比例反而走低 = 故意压缩减值以保利润
- **典型场景**: 周期股晚期 (钢铁 / 煤炭 / 猪); 电子 / 家电 technology refresh 前夕

### A3 供应商融资压力 (vendor squeeze)
- **信号组合**: 应付账款天数 (AP days) 从正常 60-90 天 被压缩到 30-40 天 **且** 营收加速 **且** 资产端现金仍在紧张
- **为什么**: 供应商担心公司经营不稳, 要求提前付款或缩短账期; 公司被迫动用现金流保供应链, 即便营收看起来在增长, 实际经营现金流承压
- **典型场景**: 高杠杆地产 / 扩张期互联网 / 大宗商品暴跌后的 commodity 公司; 也是破产前 2-4 季度的 early warning

---

**用法**:
- 上述 3 模式**不纳入 29 项计分**, 属于**深度解释层**; 若 29 项触发任一项, 且可对号入座到 A1/A2/A3, 在报告"发现的红旗 summary" 段落明确引用并加注 "模式 A<N>"
- 主 agent 复核时特别留意: 29 项计分 ≥ 3 项且可聚类到同一 pattern A<N> = 系统性造假风险, 报告结论升级为 "剔除"
