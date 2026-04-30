---
name: management-analysis
description: 深度分析一家 A 股 / 港股公司的管理层诚信度 + 企业文化 + 股东回报态度。可独立运行（`/management-analysis <ticker>`）写 standalone 报告, 也可作为 value-profile 主 skill 的 §4 section 子模块填入已有 profile。基于年报"董事会报告 / 股份变动 / 董监高 / 关联交易" + 5 年承诺 vs 兑现对比。Trigger on "/management-analysis <ticker>", "分析管理层 <ticker>", "管理层分析 <ticker>".
---

# Management Analysis Skill

本 skill 是 value-profile 主 skill 的子 skill, 专门负责"管理层诚信 + 企业文化 + 股东回报态度"的深度分析。结构分三层: **§1 原则（精炼心法）→ §2 规则（纪律）→ §3 流程（Step 1-5 执行）**。

## §0 运行模式

本 skill 支持两种模式, 主 agent 根据 invocation 参数选择:

### Mode A — Standalone

- **Invocation**: `/management-analysis <ticker>` / `分析管理层 <ticker>` / `管理层分析 <ticker>`
- **行为**: 子 skill 独立完成 ticker 验证 + filings audit + PDF 抽取 cache 检查 + 派子 agent 抓年报 + 主 agent 复核 + 写 standalone 报告
- **Output path**: `profiles/<ticker>-mgmt-<YYYY-MM-DD>.md` — self-contained 报告, 仅含本 skill 覆盖的管理层相关内容, 约 100-200 行。
- **典型场景**: 用户只想评估某 ticker 的管理层, 不需要完整 value-profile。

### Mode B — As-subroutine

- **Invocation**: 主 value-profile skill 在 Step 3 遇到 §4 section 时 delegate, 传参 `--target-profile <path> --section §4`
- **行为**: 信任主 skill 已做过 Step 1 (ticker 验证 + filings audit + PDF 抽取 cache); 跳过这些, 直接从 Step 3 (派子 agent) 开始
- **Output**: 用 Edit 工具把子 agent 产出填入 `<target-profile>` 的 §4 section block, **不新建文件**
- **典型场景**: 用户跑 `/value-profile <ticker>`, 主 skill 推进到 §4 时自动调用本 skill

### Invocation 解析

- 参数只有 ticker → Mode A (Standalone)
- 参数含 `--target-profile <path>` → Mode B (As-subroutine)
- Ticker 正则: `^[0-9]{4,6}\.(SH|SZ|HK)$`

---

## §1 管理层分析原则

精炼 7 条。这些是整个 skill 的信念层, 跨模式共享。

### §1.1 对股东的负责度 >> 经营能力

管理层的诚信、对股东的责任感, 远比他们的经营能力重要。一个不诚信的管理层, 能力越高风险越大——因为能力越高、越能系统性地侵占股东利益。评估顺序: 先看诚信, 再看能力。

### §1.2 承诺 vs 兑现是诚信的最硬指标

年报经营计划、业绩说明会指引、战略规划, 都是可以 5 年后回头对照的承诺。5 年尺度的承诺兑现率是管理层诚信度最客观的指标, 远比一次性专访 / 致辞更可靠。

### §1.3 国企年报的弦外之音

国企年报写给全体利益相关方（监管 + 党组织 + 员工 + 地方政府 + 股东 + 供应商 + 经销商）, 价值投资者不是首要读者。正文多为合规话术 / 员工福利信号 / 地方政绩信号; **关键信号在附注（关联交易、担保、应交税费、其他应收款）+ 监事会报告**。

### §1.4 股东回报是管理层道德的实操标准

"嘴上对股东负责"容易, "实际操作中对股东负责"难。看三件事: ① 分红政策是否稳定 + 分红率是否合理; ② 是否以合理价格回购股份; ③ 关联交易是否公允（特别是关联采购 / 关联销售 / 关联担保 / 大股东占款）。三者背离 → 道德降级。

### §1.5 言行一致检验

董事长致辞 / 业绩说明会的 "说", 必须对得上之后的 "做"。评估方法: 至少抓 2 个具体事件（有日期 + 有结果）, 看"说的"和"实际发生"是否一致。整份管理层分析必须包含 ≥ 2 事件的 言行一致检验, 否则不合格。

### §1.6 好生意 > 好管理层, 但烂管理层依然 弃权

一流生意 + 三流管理层 通常优于 三流生意 + 一流管理层（因为好生意的经济商誉能让平庸管理层也挣到钱）。但 §4 道德风险（虚假陈述 / 处罚 / 股东利益输送 / 系统性画大饼）**一票否决**——即使生意再好也 弃权。

### §1.7 管理层评估独立成章, 不得混入估值

管理层道德风险一旦发现, **整份 profile 降级**, 不得进入估值环节。管理层 "合格" 不是加分项, 是准入门槛——合格只是让估值流程继续, 不抬估值。

---

## §2 管理层分析规则

本节是 §1 推出的可操作纪律。每条编号 `§2.N.x` 对应原则 `§1.N`。

### §2.1 承诺 vs 兑现 5 年表（§1.2 推出）

- **§2.1.1 表骨架**: 5 年跨度, 每年一行, 列 `年初 guidance / 实际达成 / 差异 / 年报页码`。Guidance 从 N 年度"董事会报告"或"下一年度经营计划"抽, 实际从 N+1 年"经营情况讨论"抽。
  - **数据来源优先级**: 若上游 `read-filing` 已产出 §2.10 提取表, 直接读入使用 (避免重复手工提取); 若无, 本 skill 自建 (Step 3 派子 agent 抽)。
- **§2.1.2 硬阈值**: **gap > 10% 连续 3 年** → 管理层 guidance 系统性不可靠, 置信度降一档; 本 profile（或主 profile §4）打"管理层 guidance 不可信"标签。
- **§2.1.3 次年目标变化是试金石**: 目标突然消失 / 从具体数字改成定性描述（"保持稳健增长"）/ 重新设定一个更低的基数 → 强信号, 必须单独指出。

### §2.2 董事长 5 年评估（§1.5 推出）

- **§2.2.1 读 5 年董事长致辞**: 连续读 5 年, 评 ① 战略连贯性（每年是否改口径）② 战略 vs 实操（说的和做的是否一致）③ 言行一致检验。
- **§2.2.2 2 个事件下限**: 必须挑出 ≥ 2 个具体事件（日期 + 承诺内容 + 实际结果）, 不允许 "管理层言行基本一致" 这种空话。

### §2.3 股东回报 checklist（§1.4 推出）

- **§2.3.1 分红**: 5 年分红率（派息 / 净利）曲线; 有无异常波动; 是否用 "送转股本" 掩盖分红不足（送转不是分红, 不入分红率）。
- **§2.3.2 回购**: 有无回购; 回购价是否合理（回购价 > 合理估值 = 把股东钱烧掉）; 回购股是注销还是充库存股（注销 > 库存股）。
- **§2.3.3 关联交易**: 读附注"关联方及关联交易"; 特别关注 关联采购占成本比 / 关联销售占营收比 / 关联担保 / 大股东占款; 关联交易定价是否公允。
- **§2.3.4 股权激励 / 员工持股 / 高管增减持**: 5 年曲线 + 关键事件。行权价是否低于合理估值（贱卖给管理层 = 侵占股东）; 高管减持节奏（年报发布前后密集减持 = 风险）。

### §2.4 审计变更风险（§1.1 推出）

- **§2.4.1 审计师变更**: 近 3 年是否换审计所; 前任辞任声明有无异常; 新任首年意见是否标准无保留。
- **§2.4.2 董秘 / CFO 变更**: 频率 > 1 次 / 2 年 异常; CFO 离任 + 不久后财报重述 = 高危信号。

### §2.5 董监高结构（§1.3 推出）

- **§2.5.1 年龄 / 在任年限 / 专业背景**: 董事会成员平均在任年限（过短 → 内斗 / 不稳; 过长 → 固化）; 独立董事是否真独立（关联方任命 / 同一地方圈子）。
- **§2.5.2 薪酬 vs 业绩**: 高管薪酬增速是否匹配净利增速; 业绩大幅下滑而薪酬未降 = 道德风险。

### §2.6 监事会报告（§1.3 推出）

- **§2.6.1 必读**: 监事会报告多为空话, 但偶尔藏信号（"财务审核中发现……""建议公司加强……"）; 一旦出现非空话内容, 必须引用并追查。

### §2.7 道德风险一票否决（§1.6 / §1.7 推出）

- **§2.7.1 触发条件**: 历史虚假陈述处罚记录 / 违规关联交易被监管问询 / 大股东占款 / 股东利益输送（低价资产注入 / 高价资产置出）/ 系统性画大饼（连续 3 年 gap > 20%）
- **§2.7.2 后果**: 直接大幅降级, Mode A 报告结论 "弃权"; Mode B 回填主 profile §4 时 `**置信度:** 低` + 主 profile §4.5 排雷同步 flag + Part 0 标 "管理层道德风险, 不可估值"

### §2.8 财务分配 4 大测试（§1.4 推出 — 管理层质量的财报侧面）

管理层的股东回报态度 §2.3 是**语言层**; 本节是**行动层** —— 把 10 年的 ROE / 分红 / 回购 / 并购 / 债务 5 个决策看一遍, 才能判定管理层是**为股东分配资本**还是**为自己建帝国**。每项给 "pass / 中间 / fail" 三档, 4 项中 ≥ 3 项 fail → §4 管理层综合打分降一档; ≥ 2 项 fail + §2.7 任一触发 → 直接 弃权。

| 测试 | 看什么 (10 年窗口) | pass (管理层一流) | 中间 | fail (风险) |
|---|---|---|---|---|
| **1. ROE 稳定性** | ROE 10 年走势 + 绝对水平 | 稳定或上行 + 绝对值 ≥ 20%, 非靠外部杠杆堆起 (参见 references/moat-framework.md §3.4) | 稳定 10-20% / 上行 ≥ 15% | 逐年下行 → 护城河瓦解; 或靠长期负债/净资产>1 堆起 ROE → 杠杆陷阱 |
| **2. 分红 vs 回购** | 回购发生时的 PE + 分红稳定性 | 系统性回购窗口全部 < 25 PE + 稳定分红 (可乐 / GEICO 模式) | 偶尔回购 + 分红不稳 | **40PE+ 顶部回购 = 毁灭股东价值**; 或 从不回购 + 现金堆积不分红 = 资本闲置 |
| **3. 并购克制** | 商誉变化 + ROIC 走势 | organic 增长为主; bolt-on 并购 ≤ 10% 营收, ROIC 不降反升 | 中等并购节奏, ROIC 稳定 | 商誉逐年涨 + ROIC 走弱 = 建帝国, 不创造价值; 连续 3 年并购对价 > 净利 50% → 高风险 |
| **4. 债务政策** | 长期有息负债 / 5 年累计 NI | < 1 且借款用于真实经营扩张 | 1-3 之间 | **> 3 且用于顶部回购 / 对外并购** → 管理层激进杠杆套利, 未来硬着陆风险 |

**操作要点 (子 agent prompt 必带)**:
- §2.8 是**数据驱动**, 不靠管理层言辞; ROE / 分红 / 商誉 / 长期负债 直接查年报第五节财务报告 + 第十节审计报告
- 与 §2.3 股东回报 checklist 互补: §2.3 看**口径**, §2.8 看**十年累计结果**
- §2.8 fail 触发不等于 §2.7 一票否决, 但**连续 2 年均 ≥ 3 项 fail 时升级为 §2.7 系统性画大饼**; 主 agent 复核时特别留意

---

## §3 分析流程（Step 1-5）

### Step 1 — Bootstrap（仅 Mode A）

Mode B 跳过本步, 信主 skill 已做。

1. **Validate ticker** against `^[0-9]{4,6}\.(SH|SZ|HK)$`。失败双语报错并 abort。
2. **Audit `data/filings/<ticker>/`**:
   - `年报-*.pdf` < 2 份 → offer `python scripts/download_filings.py <ticker> --years 5 --include-prospectus`; 选 `yes` 执行, `no` abort, `show-command` 只打印。
   - 优先 5 年跨度年报（本 skill 核心是 5 年 承诺 vs 兑现）。
3. **PDF 预抽取 cache**: 任一 `_extracted/<pdf-stem>/text.md` 缺失 → offer `scripts/extract_pdf.py` 批跑, skip 则子 agent 读 raw PDF。

### Step 2 — 模式判定 + Output 准备

1. **解析 invocation 参数**:
   - 无 `--target-profile` → Mode A
   - 有 `--target-profile <path> --section §4` → Mode B

2. **Mode A 准备**: 新建 `profiles/<ticker>-mgmt-<YYYY-MM-DD>.md`, 写 minimal header:

   ```markdown
   # <中英文公司名> 管理层分析 — <ticker>

   **研究者:** <git config user.name>
   **报告日期:** <today>
   **模式:** standalone

   ## §4.1 专注主业 + 董事长 5 年评估
   [待填写]

   ## §4.2 承诺 vs 兑现 5 年表
   [待填写]

   ## §4.3 企业家评估 + 言行一致 (≥ 2 事件)
   [待填写]

   ## §4.4 股东回报（分红 / 回购 / 关联交易 / 股权激励）
   [待填写]

   ## §4.5 道德风险扫描
   [待填写]

   ## §4.6 总结 结论
   [合格 / 有保留 / 弃权]
   ```

3. **Mode B 准备**: Read `<target-profile>`, 定位 `## §4 管理质量与企业文化` block, 记住起止行号, 准备替换。

### Step 3 — 派 subagent 抓年报

派 ONE `general-purpose` 子 agent, prompt 英文, 强制中文输出。**必须包含**:

- ticker, 中英文公司名, exchange, report_date
- 5 份年报 extracted `text.md` 绝对路径（优先）或 raw PDF 兜底
- **承诺 vs 兑现 5 年表骨架**（§2.1.1）: 要求子 agent 逐年抽 guidance + actual + gap, 每行带年报页码; 若 gap > 10% 连续 ≥ 3 年 → 标 `**置信度:** 低` 并 flag "guidance 不可信"
- **董事长 5 年评估问题列表**（§2.2）: ① 战略连贯性 ② 战略 vs 实操 ③ 言行一致检验, 必须 ≥ 2 事件（日期 + 承诺 + 结果）
- **股东回报 checklist**（§2.3）: 分红 5 年曲线 / 回购记录 / 关联交易 / 股权激励 / 高管增减持
- **审计变更扫描**（§2.4）: 审计所 / 董秘 / CFO 3 年内变更记录
- **董监高结构**（§2.5）: 核心成员背景 + 在任年限 + 薪酬 vs 业绩
- **监事会报告必读**（§2.6）: 引用非空话段落
- **道德风险 附加检查**（§2.7）: 虚假陈述 / 处罚 / 关联交易非公允 / 大股东占款 / 系统性画大饼
- **禁用空话**: "管理层优秀 / 战略正确 / 执行力强 / 具企业家精神" 无具体佐证一律退回
- **数字必带引用**: `(年报-YYYY.pdf p.NN)` 或 URL

子 agent 输出结构化文本填 §4.1 (董事长 + 专注主业) / §4.2 (承诺 vs 兑现) / §4.3 (企业家评估) / §4.4 (股东回报) / §4.5 (道德风险)。

### Step 4 — 主 agent 复核

读子 agent 产出。**驳回并重派**若任一:

- 事实缺引用（页码 / URL）→ 改写为 `证据不足, 需人工补充`, **绝不编造**
- 言行一致检验 < 2 事件, 或事件缺日期 / 结果 → 退回
- 承诺 vs 兑现表缺某一年 → 退回补齐
- 空话撑起填写区 → 退回重写
- Mode B 场景: 子 agent 填了主 profile §4 以外的 section → 退回重做

Acceptable 后写中文终稿, 每个 subsection 填 `**引用:**` `**置信度:**` `**管理层口径校核:**`。

### Step 5 — Output

**Mode A**:
- 原子写入 `profiles/<ticker>-mgmt-<YYYY-MM-DD>.md`（`.tmp` + `mv`）
- 最末尾补 `## §4.6 总结 结论` — 3 选 1: `合格 / 有保留 / 弃权`
- 若 结论 = 弃权, 额外加 `> ⚠️ 管理层道德风险: <描述>. 建议主 value-profile 扫描时同步标 Part 0 "管理层风险, 不可估值".`

**Mode B**:
- 用 Edit 工具替换 `<target-profile>` 中 `## §4 管理质量与企业文化` ... 到下一个 `## §` 之间的整段
- **仅替换 §4 block, 保留其他 section 原样**
- 保留主 profile §4 heading 下的 HTML 注释（来自主 template）

**用户确认节点**: `[accept / edit / research more]`。**不 offer `defer` / `skip`**——管理层分析是强制的。

---

## §4 Policy

- **中文输出**: 填写区 / 引用 / 置信度 / 管理层口径校核 / 总结 结论 均中文
- **CJK-ASCII 空格规则**: 中文与紧邻西文 / 数字不加空格（"ROE15%" 非 "ROE 15%"）
- **引用必带页码**: `(年报-YYYY.pdf p.NN)` 格式
- **禁用 8 条空话**: "管理层优秀 / 战略正确 / 执行力强 / 具企业家精神 / 稳健经营 / 锐意进取 / 勤勉尽责 / 诚信专业" 无具体佐证 → 退回
- **不大段拷贝年报**: 抽取关键数字 + 页码; 原话仅 1-2 句引用论证言行一致, 不整段复制

---

## §5 MUST NOT

- MUST NOT 编造数字 / 日期 / 承诺内容。无来源写 `待补充 — 年报未披露`
- MUST NOT 跑 `git commit`——用户自 commit
- MUST NOT Mode B 下改主 profile 的 §1-§3 / §5 / §Q* / Part 0 等其他 section
- MUST NOT Mode A 下把其他 section 的内容（护城河 / 估值 / 排雷）写进本 skill 输出——本 skill 仅管管理层
- MUST NOT 用英文写 profile 内容
- MUST NOT 没有年报 PDFs 就开干 (Mode A); 若 Mode B 且主 skill 漏做 Step 1, 退回主 skill 报错

---

## §6 References — 共享自 value-profile 主 skill

本 skill **引用**以下 reference（不复制内容）:

- `.claude/skills/value-profile/references/valuation.md` §2 "管理层指引 / 承诺兑现" — 3 年后净利预估的管理层 guidance 权重
- `.claude/skills/value-profile/references/discipline.md` §2 "认错 > 坚持" — 管理层认错纪律的映射
- `.claude/skills/read-filing/references/statement-reading.md` §3 "必读附注" — 关联交易 / 其他应收款 / 应交税费 附注读法, 是 §2.3 关联交易扫描的操作基础
- `.claude/skills/financial-redflag-scan/references/fraud-library.md` §1 "风险清单" — 管理层道德风险的形式化阈值

派子 agent 时, 若需更深操作手册, 在 prompt 里明确告知 "reference 路径 = `.claude/skills/value-profile/references/<filename>.md` 第 N 节"。

---

## §7 主 skill 调用契约（Mode B）

主 value-profile skill Step 3 遇 §4 时如下 delegate:

```
子 skill: management-analysis
传参: --target-profile profiles/<ticker>-<date>.md --section §4
期望: 子 skill 填完 §4.1-§4.7 (或 §4.1-§4.5 若主 template 是 5-subsection 版) 后交还控制
```

子 skill 完成后返回主 skill 的 Step 3d 用户确认节点, 用户选 accept → 进度标 `已完成`; 选 research more → 把 hint 附加 re-dispatch Step 3 子 agent。
