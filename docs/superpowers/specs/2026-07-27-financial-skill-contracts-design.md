# 五个财务研究Skill契约重构设计

## 1.目标

在不增加第六个用户可调用skill的前提下，重构`value-profile`、`read-filing`、`product-analysis`、`management-analysis`和`financial-redflag-scan`之间的职责与机器交接契约。

本次改动解决五个问题：

1. 把重复的证据绑定、AS_OF、manifest、引用和写入权规则提取为共享契约。
2. 精简`value-profile`，使其只保留编排、接收门槛、状态传播和最终结论所有权。
3. 为三个判断型子skill统一“严格JSON信封+自由Markdown正文”。
4. 让`read-filing`Mode B默认返回完整事实，不因L1至L3初筛提前停止。
5. 让跨skill共享证据和各自判断都具有稳定ID，并由`value-profile`按判断主体去重。

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

## 6.共享证据、独立判断与去重

同一份监管文书、年报事实或关联交易可以同时支持不同判断：

- `financial-redflag-scan`判断公司财务报表、财务行为和财务风险。
- `management-analysis`判断管理层或实控人的诚信、尽责程度和治理响应。
- `product-analysis`判断产品系统和竞争力。

三个skill复用`read-filing`提供的稳定证据ID，但各自生成独立finding。Mode B统一返回`findings`数组，每项至少包含：

```json
{
  "canonical_finding_id": "<sha256>",
  "owner_skill": "financial-redflag-scan",
  "judgment_domain": "company_financials",
  "finding_type": "fund_occupation",
  "subject_type": "listed_company",
  "subject_id": "<canonical issuer ID>",
  "occurrence_date": "YYYY-MM-DD",
  "canonical_evidence_ids": ["<稳定事实或事件ID>"],
  "severity": "high_risk",
  "evidence_grade": "high",
  "judgment": "<专题解释>",
  "citation_ids": ["<canonical citation ID>"]
}
```

`canonical_finding_id`按以下规范化输入计算：

```text
sha256(judgment_domain|subject_type|subject_id|finding_type|
       occurrence_date|sorted(canonical_evidence_ids))
```

ID不包含严重度或判断文字。同一skill或同一判断域重复处理相同主体、类型和证据时得到相同ID；判断主体或判断域不同则得到不同ID。

例如，同一份财务造假处罚可以形成：

- 公司财务finding：主体为上市公司，判断财务报表可信度。
- 管理层finding：主体为涉事董事长、CFO或实控人，判断诚信与责任。

两者复用相同`canonical_evidence_ids`，但不是同一个判断，不得合并或让一个结论覆盖另一个。

### 6.1所有权

- 财务造假、虚假财务陈述、资金占用和非公允关联交易对公司财务可信度的影响，由`financial-redflag-scan`拥有。
- 上述事件及操纵市场、内幕交易、承诺失信对管理层诚信、尽责程度和治理响应的影响，由`management-analysis`拥有。
- 产品流程与竞争力失效由`product-analysis`拥有。

一个skill不得直接采用另一个skill的结论作为自身结论，只能复用底层证据、引用和已核验事实。

### 6.2复用方式

`read-filing`负责给底层事实和事件生成稳定`canonical_evidence_id`。三个判断型skill消费同一事实对象：

- `financial-redflag-scan`不重新下载或重新抽取管理层已使用的同一证据。
- `management-analysis`不重复核算完整财务排雷清单，只读取与管理层责任相关的已核验事实。
- 两者必须独立完成各自的判断链路，不能把另一个skill的severity或judgment直接复制为本领域结论。
- 两者没有执行先后依赖，可以由`value-profile`按section需要分别调用。

Mode A独立运行时，skill可以通过`read-filing`取得所需事实，但仍使用相同证据ID和finding ID算法。

### 6.3父Skill聚合

`value-profile`按`canonical_finding_id`分组：

- 同一判断域、同一主体和同一finding ID只进入该维度计数一次。
- 严重度取所有解释中的最高值。
- 公司财务finding和管理层finding分别保留，不能因为引用同一证据而互相抵消。
- 最终报告按`canonical_evidence_id`把相关判断并列展示，避免重复叙述同一事件。
- 估值阻断原因使用稳定集合去重；同一事件同时触发财务阻断和管理层否决时，保留两个判断维度，但不重复写两遍事件事实。
- owner冲突时按`judgment_domain+finding_type`所有权表选择canonical owner。
- 缺少稳定证据ID时不得伪造finding ID，返回`unresolved_items`并阻断完成。

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
- 资金占用证据同时被两个skill使用时，产生公司财务和管理层诚信两个不同finding。
- 同一判断域内重复执行不会重复计数。
- 最终报告只叙述一次底层事件，同时保留两个判断主体的独立结论。
- 产品分析自由Markdown结构不受Schema限制。

## 10.验收标准

- 不增加第六个用户入口skill。
- 共享证据规则只有一个规范来源。
- 三个判断型子skill的Mode B响应均通过对应Schema。
- Mode B正文保持自由Markdown。
- `read-filing`Mode B不早退。
- 同一判断主体的相同finding只计数一次。
- 不同判断主体可以复用同一证据并保留独立结论。
- 现有财务skill契约测试全部通过。
- 中文字符之间不存在不恰当空格。
