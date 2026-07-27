# 五个财务研究Skill契约重构设计

## 1.目标

在不增加第六个用户可调用skill的前提下，重构`value-profile`、`read-filing`、`product-analysis`、`management-analysis`和`financial-redflag-scan`之间的职责与机器交接契约。

本次改动解决五个问题：

1. 把重复的证据绑定、AS_OF、manifest、引用和写入权规则提取为共享契约。
2. 精简`value-profile`，使其只保留编排、接收门槛、状态传播和最终结论所有权。
3. 为三个判断型子skill统一“严格JSON信封+自由Markdown正文”。
4. 让`read-filing`Mode B默认返回完整事实，不因L1至L3初筛提前停止。
5. 让跨skill重复发现具有稳定ID，并由`value-profile`统一去重计数。

## 2.保持不变的职责

|Skill|职责|
|---|---|
|`value-profile`|总入口、流程编排、唯一profile写入者、最终护城河与估值结论所有者|
|`read-filing`|年报及监管材料的事实、引用和证据绑定层|
|`product-analysis`|产品边界、生产或服务流程、单位经济、客户价值和相对竞争力|
|`management-analysis`|诚信、治理、承诺兑现、资本配置和股东利益一致性|
|`financial-redflag-scan`|财务异常、三表勾稽、造假模式和财务风险严重度|

Mode A继续允许每个子skill独立生成专题报告。Mode B全部只返回结构化草稿，由`value-profile`复核并原子写入。

## 3.共享证据契约

新增：

```text
.claude/skills/read-filing/references/evidence-contract.md
```

该文件是以下规则的唯一规范来源：

- ticker、exchange、YEAR和AS_OF身份。
- annual、event及A+H counterpart manifest的路径和SHA-256绑定。
- source preflight、live revalidation和证据漂移处理。
- filing、event和外部网页引用的公共字段。
- Mode B只读和父skill唯一写入权。
- `success/pending/failure/dependency_failure/output_quality_failure`的公共语义。
- manifest变化时的fail-closed和section失效原则。

各skill仍可定义自己的业务完成条件，但不得重新定义共享字段、哈希比较方式或写入权。

`value-profile`只保留共享契约引用以及本身特有的接收、聚合和CAS事务规则。子skill只保留调用参数、业务字段和额外校验。

## 4.严格信封与自由正文

三个判断型子skill各自拥有版本化Mode B JSON Schema：

```text
.claude/skills/product-analysis/references/mode-b-response.schema.json
.claude/skills/management-analysis/references/mode-b-response.schema.json
.claude/skills/financial-redflag-scan/references/mode-b-response.schema.json
```

Schema固定机器必须依赖的外层字段：

- `schema_version`
- `terminal_status`
- `failure_reason`
- `target_sections`
- `draft_sections`或`draft_section`
- `citations`
- `unresolved_items`
- manifest SHA-256字段
- 专题handoff
- `findings`

Schema不规定：

- Markdown段落数量。
- 行业特有分析维度。
- 表格列数和表达方式。
- 产品流程步骤数量。
- 论证篇幅和写作风格。

`draft_sections`或`draft_section`的值仍是自由Markdown字符串。外层Schema使用`additionalProperties:false`阻止拼写错误和越权字段；专题handoff允许明确声明的可选字段，不使用无限制自由对象逃避契约。

Schema版本从`1.0`开始。破坏性字段调整必须升级版本，父skill只接受其明确支持的版本。

## 5.`read-filing`Mode B完整事实

Mode A保留L1至L3早退能力，用于用户只想快速读年报的场景。

Mode B不再因L1至L3提前停止：

1. 始终完成目标section所需事实、引用和warnings提取。
2. 把早退命中作为`screening_flags`返回。
3. 下游判断型skill决定是否阻断、降级或继续。
4. `--complete-facts`在Mode B成为默认语义；保留该参数仅作向后兼容，不再改变Mode B行为。

这样保证事实层不替判断层做流程终止决策。

## 6.跨Skill发现与去重

三个判断型子skill的Mode B返回统一`findings`数组。每项至少包含：

```json
{
  "canonical_finding_id": "<sha256>",
  "owner_skill": "financial-redflag-scan",
  "finding_type": "fund_occupation",
  "subject": "<主体>",
  "occurrence_date": "YYYY-MM-DD",
  "source_event_ids": ["<稳定事件ID>"],
  "severity": "high_risk",
  "evidence_grade": "high",
  "judgment": "<专题解释>",
  "citation_ids": ["<canonical citation ID>"]
}
```

`canonical_finding_id`按以下规范化输入计算：

```text
sha256(finding_type|canonical_subject|occurrence_date|sorted(source_event_ids))
```

ID不包含skill、严重度或判断文字，因此两个skill处理同一底层事件时得到相同ID。

### 6.1所有权

- 财务造假、虚假财务陈述、资金占用和非公允关联交易的财务风险判断由`financial-redflag-scan`拥有。
- 操纵市场、内幕交易、承诺失信、治理响应和责任归因由`management-analysis`拥有。
- 产品流程与竞争力失效由`product-analysis`拥有。

### 6.2复用顺序

完整`value-profile`流程在进入管理层重叠检查前确保`financial-redflag-scan`已生成可复核handoff。`management-analysis`消费该handoff：

- 复用财务风险事实、引用和`canonical_finding_id`。
- 只补充责任归因、治理响应和诚信影响。
- 不重复执行相同资金占用或关联交易财务检查。

Mode A独立运行`management-analysis`时没有父流程handoff，可以自行取得所需事实，但仍按同一ID算法输出发现。

### 6.3父Skill聚合

`value-profile`按`canonical_finding_id`分组：

- 同一ID只进入风险计数一次。
- 严重度取所有解释中的最高值。
- 所有skill的`judgment`和引用均保留为解释列表。
- owner冲突时按`finding_type`所有权表选择canonical owner。
- 缺少稳定事件ID时不得伪造ID，返回`unresolved_items`并阻断完成。

## 7.`value-profile`精简范围

精简只删除重复协议，不删除投资方法或业务判断：

- 保留投资哲学、估值方法、流程顺序和最终决策。
- 保留子skill调用时机、目标section和接收结果。
- 保留pending、否决、估值阻断和CAS写入的父级状态传播。
- 删除已在共享证据契约或子skill Schema定义的字段级重复说明。
- 用明确引用替代复制的manifest和引用字段清单。

本次不拆分新的`moat-analysis`或`valuation-analysis`skill。

## 8.失败处理

- Schema不通过：返回`output_quality_failure`，不得保存草稿。
- manifest或AS_OF绑定不通过：返回`dependency_failure`和`rebuild_evidence`。
- 事实完整但业务证据不足：返回`pending`、可保存草稿和具体`unresolved_items`。
- 相同`canonical_finding_id`出现无法解释的主体、日期或事件集合冲突：返回pending，父skill不得重复计数或擅自合并。
- 父skill不认识Schema版本：fail closed，不尝试宽松解析。

## 9.测试策略

### 9.1静态契约测试

- 五个skill都引用唯一共享证据契约。
- `value-profile`不再复制公共manifest字段定义。
- 三个判断型子skill都存在可解析的Mode B Schema。
- Schema允许自由Markdown正文，但拒绝未知顶层字段。
- `read-filing`Mode B明确禁用早退并返回`screening_flags`。
- 三个判断型子skill使用相同finding必填字段和ID算法。
- `value-profile`按ID去重并取最高严重度。

### 9.2Schema行为测试

使用`jsonschema`分别验证：

- 合法success、pending和dependency failure响应。
- Markdown正文包含行业特有表格时仍通过。
- 缺哈希、未知状态、未知顶层字段和非法finding时失败。

### 9.3Skill行为复测

至少覆盖：

- 年报命中早退事实后，`read-filing`Mode B仍返回完整目标事实。
- 资金占用同时出现在排雷和管理层分析时，只产生一个canonical risk count。
- 管理层保留独立的责任归因解释。
- 产品分析自由Markdown结构不受Schema限制。

## 10.验收标准

- 不增加第六个用户入口skill。
- 共享证据规则只有一个规范来源。
- 三个判断型子skill的Mode B响应均通过对应Schema。
- Mode B正文保持自由Markdown。
- `read-filing`Mode B不早退。
- 同一底层风险事件只计数一次。
- 现有财务skill契约测试全部通过。
- 中文字符之间不存在不恰当空格。
