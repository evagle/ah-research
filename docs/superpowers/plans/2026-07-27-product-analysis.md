# Product Analysis Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**新增独立`product-analysis`skill，强制执行产品边界、生产或服务流程、流程经济性、客户价值、相对竞争、需求侧机制、财报映射和失效测试，并以Mode B接入`value-profile`。

**Architecture:**`SKILL.md`只保存运行和输出契约；`process-playbooks.md`保存行业流程路由；`value-mechanisms.md`保存需求侧机制及证据要求。Mode A生成独立报告，Mode B只返回`§1.1`、`§1.3`草稿及`moat_handoff`，由`value-profile`复核并原子写入。

**Tech Stack:**Markdown skill、JSON式结构化输出契约、pytest静态契约测试、skill-creator验证脚本。

**Spec:**`docs/superpowers/specs/2026-07-27-product-analysis-design.md`

## Global Constraints

- `SKILL.md`不超过500行。
- 用户直接提供ticker时默认Mode A；包含`--target-profile`时进入Mode B。
- Mode B不得直接修改profile，不得给出最终护城河等级。
- 核心分析严格按已确认的8步链路执行。
- 不机械使用50%收入阈值，不从高毛利单独推导品牌、身份或稀缺性。
- 未披露成本只能输出带来源、公式、假设和敏感性的区间估算。
- 每个关键流程步骤、竞争比较和价值机制必须给引用及`高/中/低/需人工`证据等级。
- 两个中文字符之间不得出现不恰当空格。

---

### Task 1:建立RED契约和行为基线

**Files:**
- Modify:`tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes:`SKILLS_ROOT`、`SKILL_PATHS`及现有`read()`测试帮助函数。
- Produces:产品分析结构、模式、边界和父子skill接入的失败契约。

- [x] **Step 1:记录无skill行为基线**

对茅台、泡泡玛特和制造供应链公司分别运行一次无`product-analysis`skill的独立分析请求，记录是否发生以下缺口：

- 跳过生产或服务流程。
- 从高毛利直接推导用户心智。
- 不与直接竞品、替代品和适用龙头比较。
- 编造未披露单位成本或不列估算假设。

- [x] **Step 2:写失败契约测试**

在`tests/unit/skills/test_financial_skill_contracts.py`增加以下测试：

```python
def test_product_analysis_has_mode_and_parent_ownership_contracts() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    assert "参数只有ticker" in skill
    assert "默认进入Mode A" in skill
    assert "含`--target-profile`" in skill
    assert "进入Mode B" in skill
    assert "不得直接修改" in skill
    assert "父skill" in skill
    assert "最终护城河" in skill


def test_product_analysis_enforces_the_eight_step_chain() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    expected = (
        "产品边界",
        "生产或服务流程",
        "流程经济性",
        "客户价值",
        "相对竞争力",
        "需求侧机制",
        "财报映射",
        "失效测试",
    )
    positions = [skill.index(item) for item in expected]
    assert positions == sorted(positions)
    assert "不机械使用" in skill
    assert "50%" in skill


def test_product_analysis_requires_process_economics_and_cost_discipline() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    process = read(SKILLS_ROOT / "product-analysis/references/process-playbooks.md")
    for field in ("周期", "产能", "良率", "瓶颈", "单位成本"):
        assert field in skill
    for route in ("制造业", "软件与互联网", "零售", "专业服务"):
        assert route in process
    assert "公式" in skill
    assert "假设" in skill
    assert "敏感性" in skill
    assert "不得伪造" in skill


def test_product_analysis_requires_relative_competition_and_evidence() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    mechanisms = read(SKILLS_ROOT / "product-analysis/references/value-mechanisms.md")
    for comparison in ("直接竞品", "替代方案", "适用龙头"):
        assert comparison in skill
    assert "2至3项" in skill
    assert "高毛利" in skill
    assert "不能单独证明" in skill
    for grade in ("`高`", "`中`", "`低`", "`需人工`"):
        assert grade in skill
    assert "行为证据" in mechanisms
    assert "财务证据" in mechanisms


def test_value_profile_delegates_product_sections_without_moving_moat_ownership() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "`product-analysis`" in skill
    assert "`part1/§1.1`" in skill
    assert "`part1/§1.3`" in skill
    assert "`moat_handoff`" in skill
    assert "最终护城河" in skill
    assert "产品与流程证据" in template
```

- [x] **Step 3:运行测试确认RED**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py -q -k product_analysis
```

预期：因`product-analysis`不存在而失败，不得因语法或测试夹具错误失败。

---

### Task 2:实现独立skill及按需reference

**Files:**
- Create:`.claude/skills/product-analysis/SKILL.md`
- Create:`.claude/skills/product-analysis/references/process-playbooks.md`
- Create:`.claude/skills/product-analysis/references/value-mechanisms.md`

**Interfaces:**
- Consumes:ticker、AS_OF、年报和事件manifest，Mode B额外消费目标profile与section。
- Produces:Mode A独立报告；Mode B返回`draft_sections/product_facts/process_facts/competition_facts/moat_handoff/citations/warnings/unresolved_items/terminal_status`。

- [x] **Step 1:使用skill-creator脚手架初始化**

运行：

```bash
python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  product-analysis \
  --path .claude/skills \
  --resources references \
  --interface display_name="Product Analysis" \
  --interface short_description="分析核心产品、交付流程与相对竞争力" \
  --interface default_prompt="分析目标公司的核心产品、生产或服务流程、单位经济和相对竞争力。"
```

按照本仓库`.claude/skills`惯例，只保留运行所需的`SKILL.md`和`references/`；不提交项目不消费的UI元数据。

- [x] **Step 2:写`process-playbooks.md`**

定义以下行业路由及共同字段：

- 制造业与耐用品。
- 食品饮料和其他消费品。
- 软件与互联网。
- 零售、平台和物流。
- 专业服务和其他人力密集服务。

每条路由必须覆盖设计、投入、交付、质量控制、反馈闭环、成本、产能或吞吐、营运资金、扩张约束和财报落点。

- [x] **Step 3:写`value-mechanisms.md`**

定义功能性能、可靠信任、时间便利、情绪体验、身份社群、稀缺时间、生态锁定、网络匹配八类候选机制。每类包含：

- 适用条件。
- 行为证据。
- 财务证据。
- 反证。
- 常见误判。

明确最终只选2至3项，不全量输出。

- [x] **Step 4:写`SKILL.md`**

按照规格实现：

- Mode A/B解析和默认行为。
- 8步核心链路。
- Mode B结构化返回字段及父skill写入权。
- 成本区间估算纪律。
- 竞争阶梯和龙头差距。
- 证据等级、引用、重查上限和pending终态。
- Mode A标准报告结构。

- [x] **Step 5:运行契约测试确认核心skill变绿**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py -q -k product_analysis
```

预期：除`value-profile`接入测试外全部通过。

---

### Task 3:接入`value-profile`并完成验证

**Files:**
- Modify:`.claude/skills/value-profile/SKILL.md`
- Modify:`.claude/skills/value-profile/template-zh.md`
- Modify:`tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes:`product-analysis`Mode B的结构化返回值。
- Produces:经过父skill复核并CAS写入的`part1/§1.1`、`part1/§1.3`，以及供§3使用但不直接定级的`moat_handoff`。

- [x] **Step 1:增加确定性委派规则**

在`value-profile`的Part 1 dispatch中规定：

- 全流程到达§1.1时调用一次`product-analysis`Mode B。
- 显式请求§1.1或§1.3时只生成目标section。
- 父skill校验manifest、引用、目标section和返回字段。
- `product-analysis`不得写profile。
- `moat_handoff`只作为§3证据输入，最终护城河仍按`moat-framework.md`计算。

- [x] **Step 2:补充模板完成条件**

在§1.1加入产品利润地图、设计与交付流程、流程经济性和单位经济字段。

在§1.3加入直接竞品、替代方案、适用龙头、龙头差距、2至3项价值机制及财报映射字段。

- [x] **Step 3:运行全部skill契约**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py -q
```

预期：全部通过。

- [x] **Step 4:执行skill验证和静态检查**

运行：

```bash
python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .claude/skills/product-analysis
test "$(wc -l < .claude/skills/product-analysis/SKILL.md)" -le 500
.venv/bin/ruff check tests/unit/skills/test_financial_skill_contracts.py
git diff --check
```

- [x] **Step 5:运行中文间距检查**

运行：

```bash
rg -nP '[\p{Han}]\s+[\p{Han}]' \
  .claude/skills/product-analysis \
  .claude/skills/value-profile/SKILL.md \
  .claude/skills/value-profile/template-zh.md
```

逐条检查命中项，只允许Markdown换行、代码或引用中有明确语义的空格。

- [x] **Step 6:运行skill行为复测**

使用与Task 1相同的三类请求加载新skill，确认：

- 茅台分析包含酿造周期、基酒产能和成本估算纪律。
- 泡泡玛特分析包含IP设计、打样、制造、渠道和库存链路。
- 制造供应链公司分析包含研发设计、供应商、良率、产能、交付及相对龙头差距。
- 三类分析都只选择2至3项价值机制并提供财报映射。

- [x] **Step 7:最终自审**

运行：

```bash
git status --short
git diff --stat
git diff -- .claude/skills/product-analysis .claude/skills/value-profile \
  tests/unit/skills/test_financial_skill_contracts.py
```

确认没有修改或提交`.claude/worktrees/`、`AGENTS.md`和`tmp/`。
