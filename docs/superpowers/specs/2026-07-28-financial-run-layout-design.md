# 财务Skill共享数据与运行目录设计

## 目标

实现seamless trigger：用户只提供ticker和业务意图，不选择resume、新run或run ID。系统自动续跑兼容的未完成run、复用相同输入的完成结果，或在输入变化时创建增量子run。

大部分昂贵数据提升为ticker级共享不可变资产；只有日志、checkpoint、临时草稿和当前执行状态按run隔离。`profiles/`只保留主`value-profile`最终档案。

## 总体目录

```text
data/filings/<ticker>/
├── manifests/
├── evidence/
├── _extracted/
├── facts/
├── metrics/
├── citations/
├── analyses/
├── market/
└── runs/
    ├── index.json
    └── <run-id>/
        ├── checkpoint.json
        ├── report.md
        ├── drafts/
        ├── manifests/
        ├── query/
        ├── logs/
        └── tmp/
```

## Ticker级共享数据

|路径|共享内容|复用条件|
|---|---|---|
|`manifests/`|canonical annual、event、counterpart和market manifests|文件SHA-256一致|
|`evidence/`|官方响应、监管文书、年报PDF、招股书和研究资料原文|内容寻址，不可变|
|`_extracted/`|PDF文本、图片、页码映射和metadata|源PDF哈希及抽取器版本一致|
|`facts/`|`read-filing`标准化事实和`screening_flags`|事实输入指纹一致|
|`metrics/`|财务指标、时间序列、勾稽和单位经济计算结果|事实指纹、计算器版本及参数一致|
|`citations/`|canonical citation和`canonical_evidence_id`注册表|来源身份和内容哈希一致|
|`analyses/`|已接受的产品、管理层、财务finding及section artifact|分析输入指纹完全一致|
|`market/`|AS_OF绑定的价格、无风险利率和市场响应|market manifest哈希一致|

发行人身份、上市日期、交易所代码、主体名册、官方来源矩阵和查询契约也作为不可变证据保存在`evidence/`，由manifest引用。实际query plan属于当前执行，保存在run的`query/`；通过验证后的官方响应和query bundle提升到共享`evidence/`。

## 共享指纹

共享artifact统一使用内容寻址ID：

```text
artifact_id = sha256(
  artifact_kind
  | schema_version
  | sorted(input_artifact_ids)
  | normalized_parameters
  | content_sha256
)
```

事实输入指纹至少包含ticker、target fiscal year、AS_OF、实际构造并验证后的annual/event/counterpart manifest哈希和抽取器版本；query plan哈希不能代替实际响应与manifest哈希。指标追加计算器版本、单位和参数。分析artifact追加skill版本、judgment domain、subject、目标section、模板版本及全部依赖artifact ID。

`content_sha256`用于已生成artifact的发布地址；run输入指纹在artifact生成前不包含该字段。指纹完全一致才能直接复用；任一输入变化只使依赖图中的下游artifact失效。

## 有条件共享的分析结果

以下结果可以共享，但必须满足完整分析指纹：

- 产品边界、生产或服务流程及竞争比较。
- 管理层承诺兑现表、资本分配表和管理责任finding。
- 财务排雷清单、勾稽结果和公司财务finding。
- `moat_handoff`及已接受的section正文。

不同judgment domain和subject仍保留独立finding ID。用户手工编辑的正文默认只属于当前run；只有明确接受并生成新artifact ID后，才可被后续run继承。

## Run级独立数据

```text
data/filings/<ticker>/runs/<run-id>/
├── checkpoint.json
├── report.md
├── drafts/
├── manifests/
├── query/
├── logs/
└── tmp/
```

|路径|用途|是否共享|
|---|---|---|
|`checkpoint.json`|run身份、parent、步骤、输入绑定、继承和失效集合|否|
|`report.md`|当前及最终standalone可读报告|可按分析指纹继承artifact，不直接共写|
|`drafts/`|CAS发布前候选稿|否|
|`manifests/`|临时manifest和复核候选|否；通过后提升到ticker级|
|`query/`|本次调用的query plan和请求计划|否；验证结果提升到ticker级|
|`logs/`|结构化日志、重试和失败诊断|否|
|`tmp/`|临时下载和转换文件|否，可清理|

被profile、canonical manifest、citation或共享artifact引用的文件不得清理。

## Run ID与继承

run ID是内部标识，用户不需要查看或传入：

```text
<skill-name>-<target-fiscal-year>-<YYYYMMDD>-v<N>
```

- `YYYYMMDD`是Asia/Shanghai时区的首次创建日期，不是AS_OF。
- `vN`始终存在并通过排他`mkdir`原子分配。
- `checkpoint.json`记录`run_id`、`parent_run_id`、`created_at`、AS_OF、skill版本、输入指纹、`inherited_artifacts`和`invalidated_artifacts`。
- 子run不复制共享大文件，只保存artifact ID、绝对路径和SHA-256引用。

## Seamless Trigger

正常入口不要求`--resume`、`--start-fresh`或`--run-id`：

```text
/read-filing <ticker>
/product-analysis <ticker>
/management-analysis <ticker>
/financial-redflag-scan <ticker>
/value-profile <ticker>
```

内部run resolver按以下顺序执行：

1. 存在输入兼容的未完成run时，自动续跑最新run。
2. 不存在未完成run，但存在完全相同输入指纹的完成结果时，直接复用结果，不创建run。
3. 输入发生变化时，创建以上一兼容run为parent的增量子run，只重跑失效artifact。
4. 没有历史数据时，自动创建首个run。
5. 多个候选按兼容性、创建时间、版本和完整路径确定性选择，不询问用户。
6. 只有用户明确要求“完全重新分析”时，才创建不继承历史的clean run。

run resolver对用户不可见；run ID只用于恢复、审计和并发隔离。

## Skill映射

`read-filing`、`product-analysis`、`management-analysis`和`financial-redflag-scan`的Mode A都使用run目录。Mode B只返回内存JSON，由父skill写主profile，不创建standalone run。

`value-profile`主档案继续使用：

```text
profiles/<ticker>-<YYYY-MM-DD>[-vN].md
```

其入口也使用相同resolver自动选择已有未完成profile、复用完成artifact或创建增量分析，不再显示resume/start-fresh选择。完成时通过`complete --result-path <absolute-profile-path>`登记外部结果路径，复用时resolver直接返回该profile。

## Manifest提升与原子性

run级`manifests/`只保存候选。通过完整复核后，canonical manifest内容寻址发布到ticker级`manifests/`。父profile只绑定canonical真实绝对路径及SHA-256。

- 先原子创建run目录和初始checkpoint。
- `report.md`发布成功后才能推进checkpoint步骤。
- 共享artifact只新增，不原地覆盖。
- ticker级索引和`runs/index.json`通过CAS更新。
- 并发run不得共享draft、日志或临时文件。
- 提升失败时保留旧共享绑定并记录失败，不得形成半更新。

## 兼容迁移

1. 新standalone运行只写ticker级`runs/`。
2. 旧`profiles/<ticker>-reading-*-scratch.md`、`profiles/<ticker>-product-*.md`、`profiles/<ticker>-mgmt-*.md`和`profiles/<ticker>-redflags-*.md`仅兼容读取。
3. 旧文件不自动移动；首次读取后可生成共享artifact并登记到`runs/index.json`，原文件保持不变。
4. 主`value-profile`文件继续保留在`profiles/`。

## 测试要求

- 正常入口不得要求用户选择resume、新run或run ID。
- 兼容未完成run必须自动续跑。
- 相同输入指纹必须复用完成结果且不创建run。
- 输入变化必须创建增量子run并只失效受影响artifact。
- Mode A路径必须位于ticker级`runs/`；Mode B不得创建run。
- 日志、checkpoint、draft、query和tmp不得跨run共写。
- canonical证据、抽取、事实、指标、citation和可复用分析artifact必须位于ticker级共享目录。
- 共享artifact必须内容寻址且不可原地覆盖。
- 旧standalone路径必须可读但不得用于新运行。
- 主`value-profile`路径保持不变。
