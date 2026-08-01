# 五个财务研究Skill契约重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**为5个财务研究skill建立唯一证据契约、灵活Markdown响应Schema、Mode B完整事实语义，以及按判断域和主体去重的finding协议。

**Architecture:**`read-filing/references/evidence-contract.md`成为证据绑定和公共Mode B语义的唯一规范来源。三个判断型skill使用各自的JSON Schema固定机器信封，同时把报告正文保留为自由Markdown；`value-profile`只编排、复核、按主体去重和原子写入。

**Tech Stack:**Markdown skill、JSON Schema Draft 2020-12、Python pytest、jsonschema、ruff、skill-creator验证器。

**Spec:**`docs/superpowers/specs/2026-07-27-financial-skill-contracts-design.md`

## Global Constraints

- 不增加第六个用户可调用skill。
- `financial-redflag-scan`判断公司财务，`management-analysis`判断管理层，两个判断不得合并。
- 判断型skill可以复用相同`canonical_evidence_id`，但不得复用另一个skill的severity或judgment。
- JSON Schema只固定机器信封；`draft_section`和`draft_sections`正文保持自由Markdown。
- Mode B只有父skill可以写profile。
- `read-filing`Mode B不因L1至L3提前停止。
- 相同判断域、主体、类型和证据生成相同`canonical_finding_id`。
- 两个中文字符之间不得出现不恰当空格。
- 不提交`.claude/worktrees/`、`AGENTS.md`或`tmp/`。

---

### Task 1:建立共享证据契约

**Files:**
- Create:`.claude/skills/read-filing/references/evidence-contract.md`
- Modify:`.claude/skills/read-filing/SKILL.md`
- Modify:`.claude/skills/product-analysis/SKILL.md`
- Modify:`.claude/skills/management-analysis/SKILL.md`
- Modify:`.claude/skills/financial-redflag-scan/SKILL.md`
- Modify:`.claude/skills/value-profile/SKILL.md`
- Test:`tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes:现有AS_OF、annual/event/counterpart manifest、citation和CAS规则。
- Produces:所有5个skill引用的唯一公共证据契约。

- [x] **Step 1:写失败契约测试**

新增：

```python
def test_all_financial_skills_share_one_evidence_contract() -> None:
    contract_path = SKILLS_ROOT / "read-filing/references/evidence-contract.md"
    assert contract_path.is_file()
    contract = read(contract_path)
    for heading in (
        "## 1.身份与截止日",
        "## 2.Manifest绑定",
        "## 3.Mode B只读与写入权",
        "## 4.引用",
        "## 5.终态",
        "## 6.证据漂移",
    ):
        assert heading in contract
    for skill_name in SKILL_PATHS:
        assert "read-filing/references/evidence-contract.md" in read(SKILL_PATHS[skill_name])
```

该测试防止共享契约文件缺失或任一skill脱离公共规范。

- [x] **Step 2:运行测试确认RED**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k all_financial_skills_share_one_evidence_contract
```

预期：因`evidence-contract.md`不存在而失败。

- [x] **Step 3:写最小共享契约**

契约必须定义：

```text
身份=(canonical ticker,exchange,target_fiscal_year,AS_OF,target_section)
绑定=(absolute manifest path,SHA-256,jurisdiction key set)
写入权=Mode B只读,父skill唯一写profile
漂移=dependency_failure+rebuild_evidence
引用=filing_text|filing_pdf|event_document
终态=success|pending|failure|dependency_failure|output_quality_failure
```

把5个`SKILL.md`开头的重复上市资料绑定段替换为对该文件的强制引用；保留各skill特有的业务条件。

- [x] **Step 4:运行测试确认GREEN**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k all_financial_skills_share_one_evidence_contract
```

预期：PASS。

---

### Task 2:为三个判断型Skill建立灵活响应Schema

**Files:**
- Create:`.claude/skills/product-analysis/references/mode-b-response.schema.json`
- Create:`.claude/skills/financial-redflag-scan/references/mode-b-response.schema.json`
- Modify:`.claude/skills/management-analysis/references/mode-b-response.schema.json`
- Modify:`.claude/skills/product-analysis/SKILL.md`
- Modify:`.claude/skills/management-analysis/SKILL.md`
- Modify:`.claude/skills/financial-redflag-scan/SKILL.md`
- Test:`tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes:现有三个Mode B返回对象。
- Produces:三个可由`Draft202012Validator`验证的Schema；Markdown字段只要求非空和必要机器引用标记。

- [x] **Step 1:增加测试fixture和失败测试**

新增fixture：

```python
def canonical_finding(
    domain: str,
    subject_type: str,
    subject_id: str,
) -> dict[str, object]:
    return {
        "canonical_finding_id": "d" * 64,
        "owner_skill": "financial-redflag-scan",
        "judgment_domain": domain,
        "finding_type": "fund_occupation",
        "subject_type": subject_type,
        "subject_id": subject_id,
        "occurrence_date": "2025-01-15",
        "canonical_evidence_ids": ["e" * 64],
        "severity": "high_risk",
        "evidence_grade": "high",
        "judgment": "公司财务判断",
        "citation_ids": ["f" * 64],
    }
```

新增测试：

```python
def test_judgment_schemas_allow_free_markdown_and_reject_unknown_envelope_fields() -> None:
    for skill_name in (
        "product-analysis",
        "management-analysis",
        "financial-redflag-scan",
    ):
        schema_path = SKILLS_ROOT / skill_name / "references/mode-b-response.schema.json"
        schema = json.loads(read(schema_path))
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
```

再分别构造合法success响应，正文使用不同标题和行业表格；断言验证通过。给每个响应增加`unexpected_top_level_field`后断言验证失败。

- [x] **Step 2:运行测试确认RED**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k 'judgment_schemas or canonical_finding'
```

预期：product和redflag Schema缺失，management Schema缺`findings`而失败。

- [x] **Step 3:实现三个Schema**

三个Schema共同要求：

```text
schema_version
terminal_status
failure_reason
manifest SHA-256字段
citations
findings
专题草稿字段
专题未决字段
```

`draft_sections`或`draft_section`的值使用`type:string,minLength:1`，不得枚举正文标题或行业字段。顶层设置`additionalProperties:false`。

finding要求：

```text
canonical_finding_id
owner_skill
judgment_domain
finding_type
subject_type
subject_id
occurrence_date
canonical_evidence_ids
severity
evidence_grade
judgment
citation_ids
```

更新三个`SKILL.md`，要求Mode B返回前执行对应Schema校验。

- [x] **Step 4:运行Schema测试确认GREEN**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k 'judgment_schemas or management_mode_b_response_schema'
```

预期：PASS。

---

### Task 3:让Read Filing Mode B始终返回完整事实

**Files:**
- Modify:`.claude/skills/read-filing/SKILL.md`
- Modify:`.claude/skills/financial-redflag-scan/SKILL.md`
- Modify:`.claude/skills/management-analysis/SKILL.md`
- Modify:`.claude/skills/product-analysis/SKILL.md`
- Test:`tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes:L1至L3初筛事实。
- Produces:Mode B完整`facts/citations/warnings/screening_flags`；`--complete-facts`仅作为兼容参数。

- [x] **Step 1:写失败测试**

```python
def test_read_filing_mode_b_never_early_exits() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B — As-subroutine", 1)[1].split(
        "### Invocation 解析", 1
    )[0]
    assert "Mode B始终执行完整事实提取" in mode_b
    assert "`--complete-facts`在Mode B中仅为兼容参数" in skill
    assert '"screening_flags"' in skill.split("**Mode B输出**", 1)[1]
    assert "Mode B早退" not in skill
```

- [x] **Step 2:运行测试确认RED**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k read_filing_mode_b_never_early_exits
```

预期：因现有Mode B早退规则而失败。

- [x] **Step 3:修改Mode B流程**

保留Mode A早退。把Step 2终止分支改为：

```text
Mode A且未传--complete-facts→允许早退
Mode B→记录screening_flags并继续Step 2.5及目标事实提取
```

三个判断型skill不再需要显式依赖`--complete-facts`才能取得完整事实，但继续接受旧调用形式。

- [x] **Step 4:运行测试确认GREEN**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k 'read_filing_mode_b_never_early_exits or read_filing_contract'
```

预期：PASS。

---

### Task 4:实现按判断域和主体区分的Finding契约

**Files:**
- Modify:`.claude/skills/read-filing/SKILL.md`
- Modify:`.claude/skills/product-analysis/SKILL.md`
- Modify:`.claude/skills/management-analysis/SKILL.md`
- Modify:`.claude/skills/financial-redflag-scan/SKILL.md`
- Modify:`.claude/skills/value-profile/SKILL.md`
- Modify:`.claude/skills/product-analysis/references/mode-b-response.schema.json`
- Modify:`.claude/skills/management-analysis/references/mode-b-response.schema.json`
- Modify:`.claude/skills/financial-redflag-scan/references/mode-b-response.schema.json`
- Test:`tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes:`read-filing`产生的`canonical_evidence_id`。
- Produces:稳定finding ID、明确判断所有权，以及父skill按主体去重的聚合规则。

- [x] **Step 1:写失败契约与Schema测试**

```python
def test_financial_and_management_findings_share_evidence_but_not_judgment_identity() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    management = read(SKILL_PATHS["management-analysis"])
    profile = read(SKILL_PATHS["value-profile"])
    algorithm = (
        "sha256(judgment_domain|subject_type|subject_id|finding_type|"
        "occurrence_date|sorted(canonical_evidence_ids))"
    )
    for text in (redflag, management, profile):
        assert algorithm in text
    assert "judgment_domain=company_financials" in redflag
    assert "judgment_domain=management_integrity" in management
    assert "不同判断主体不得合并" in profile
```

用同一`canonical_evidence_ids`构造公司财务和管理层两个finding，分别通过对应Schema；将management finding错误设置为`subject_type=listed_company`时必须失败。

- [x] **Step 2:运行测试确认RED**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k 'share_evidence_but_not_judgment_identity'
```

预期：因finding协议尚未存在而失败。

- [x] **Step 3:实现判断所有权和ID算法**

`read-filing`为事实和事件返回`canonical_evidence_id`，不返回判断严重度。

固定判断域：

```text
product-analysis=product_competitiveness
management-analysis=management_integrity
financial-redflag-scan=company_financials
```

`value-profile`按`canonical_finding_id`在同一判断域和主体内去重；不同主体finding分别保留。最终呈现按`canonical_evidence_id`聚合同一底层事件，估值阻断原因使用稳定集合去重。

- [x] **Step 4:运行测试确认GREEN**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k 'canonical_finding or share_evidence_but_not_judgment_identity or risk_counts'
```

预期：PASS。

---

### Task 5:精简Value Profile重复协议

**Files:**
- Modify:`.claude/skills/value-profile/SKILL.md`
- Modify:`tests/unit/skills/test_financial_skill_contracts.py`

**Interfaces:**
- Consumes:共享证据契约和三个子skill Schema。
- Produces:更短的总编排器，同时保留调用、接收、阻断、CAS和最终结论所有权。

- [x] **Step 1:写失败测试**

```python
def test_value_profile_delegates_contract_details_to_owned_references() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "公共证据规则不在本skill重定义" in skill
    for schema in (
        "product-analysis/references/mode-b-response.schema.json",
        "management-analysis/references/mode-b-response.schema.json",
        "financial-redflag-scan/references/mode-b-response.schema.json",
    ):
        assert schema in skill
    assert len(skill.splitlines()) < 660
```

660行门槛从当前693行出发，只要求删除重复协议，不迫使删除投资方法。

- [x] **Step 2:运行测试确认RED**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k value_profile_delegates_contract_details
```

预期：因尚未引用全部Schema且行数超过门槛而失败。

- [x] **Step 3:删除重复说明**

优先精简：

- 开头重复的上市资料绑定说明。
- Step 3中子skill已由Schema定义的逐字段响应说明。
- 重复的manifest字段枚举和引用联合类型。
- 子skill内部重试细节。

必须保留：

- 调用顺序和目标section。
- 父skill唯一写入权。
- Schema校验后的业务接收门槛。
- pending、否决和估值阻断传播。
- CAS原子保存和最终护城河、估值所有权。

- [x] **Step 4:运行测试确认GREEN**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k 'value_profile_delegates_contract_details or product_analysis or management'
```

预期：PASS。

---

### Task 6:行为复测与最终验证

**Files:**
- Modify:`docs/superpowers/plans/2026-07-27-financial-skill-contracts.md`

**Interfaces:**
- Consumes:完成后的5个skill和3个Schema。
- Produces:行为证据、完整测试结果和提交前清单。

- [x] **Step 1:运行三个行为场景**

场景A：

```text
年报命中非标准审计意见。以read-filing Mode B为产品分析提取事实。
```

通过条件：返回完整目标事实和`screening_flags`，不输出早退草稿。

场景B：

```text
同一份官方处罚证明公司财务造假且CFO负有责任。
```

通过条件：redflag输出公司财务finding，management输出CFO诚信finding；两者共享证据ID但finding ID不同。

场景C：

```text
制造业产品分析需要增加行业特有的12列表格。
```

通过条件：自由Markdown正文通过product Schema，未知顶层字段仍被拒绝。

- [x] **Step 2:运行完整契约测试**

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py -q
```

预期：全部通过。

- [x] **Step 3:运行静态验证**

```bash
.venv/bin/ruff check tests/unit/skills/test_financial_skill_contracts.py
.venv/bin/python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py .claude/skills/read-filing
.venv/bin/python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py .claude/skills/product-analysis
.venv/bin/python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py .claude/skills/management-analysis
.venv/bin/python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py .claude/skills/financial-redflag-scan
.venv/bin/python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py .claude/skills/value-profile
git diff --check
```

- [x] **Step 4:运行中文间距和范围检查**

```bash
rg -nP '[\p{Han}][ \t]+[\p{Han}]' \
  .claude/skills/read-filing \
  .claude/skills/product-analysis \
  .claude/skills/management-analysis \
  .claude/skills/financial-redflag-scan \
  .claude/skills/value-profile
git status --short
git diff --stat feat/product-analysis-skill..HEAD
```

只允许明确有语义的Markdown或引用空格。确认`.claude/worktrees/`、`AGENTS.md`和`tmp/`未被暂存。

- [x] **Step 5:提交并创建堆叠PR**

提交实现，推送`refactor/financial-skill-contracts`，以`feat/product-analysis-skill`为base创建草稿PR。PR正文列出Schema行为测试、完整契约测试和行为复测结果。
