# 财务Skill共享数据与Run Store契约

本文件是`value-profile`、`read-filing`、`product-analysis`、`management-analysis`和`financial-redflag-scan`的唯一运行目录规范。AI仍负责研究、判断和Markdown写作；`scripts/financial_run_store.py`只负责路径解析、输入指纹、并发隔离、崩溃恢复和通用不可变artifact发布。

## 1.无感入口

正常调用只提供ticker及业务参数，不要求用户选择resume、新run或run ID。`product-analysis`、`management-analysis`、`financial-redflag-scan`和`value-profile`先运行`read-filing` Mode A准备或复用共享证据，取得annual、event及全部counterpart manifest的真实artifact ID后，才调用自身resolver。`read-filing`是证据生产者，也必须在系统临时目录实际构造并验证候选annual、event及全部counterpart manifest，再把候选manifest的真实SHA-256作为输入artifact调用自身resolver；query plan哈希只能作为附加输入，不能代替实际响应和manifest哈希。任何skill都不得用待建立占位值计算输入指纹。

固定目标财年和AS_OF且输入artifact已确定后，调用：

```bash
uv run python scripts/financial_run_store.py resolve \
  --root data/filings \
  --ticker <ticker> \
  --skill <skill-name> \
  --target-year <YYYY> \
  --as-of <AS_OF> \
  --skill-version <version> \
  --input-artifact <artifact-id> \
  --parameter <key>=<json-value> \
  [--result-path <absolute-output-path>]
```

所有影响分析结果的输入都必须进入`--input-artifact`或`--parameter`。只有用户明确要求“完全重新分析”时追加`--clean`；不得向用户暴露内部run ID或让用户选择恢复方式。

## 2.Ticker级共享层

```text
data/filings/<ticker>/
├── manifests/
├── evidence/
├── _extracted/
├── facts/
├── metrics/
├── citations/
├── analyses/
└── market/
```

- `manifests/`保存复核通过的canonical年报、事件、counterpart和市场manifest。
- `evidence/`保存官方响应、监管文书、PDF和查询bundle。
- `_extracted/`保存与源PDF哈希及抽取器版本绑定的抽取结果。
- `facts/`、`metrics/`和`citations/`保存标准化事实、计算结果和canonical引用。
- `analyses/`保存指纹完全一致且已接受的分析artifact。
- `market/`保存与AS_OF绑定的市场快照。

没有专用发布器的共享产物通过`financial_run_store.py promote`内容寻址发布。已有专用发布器（例如`download_filings.py --promote`和`build_event_manifest.py`）可以继续负责其schema校验与发布，但必须满足同样的内容寻址、排他创建和只新增不覆盖契约。run store不得把已由专用发布器验证的artifact再复制一份。

## 3.Run级隔离层

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

`checkpoint.json`、`report.md`、`drafts/`、候选`manifests/`、`query/`、`logs/`和`tmp/`只属于当前run，不得跨run共写。共享大文件不复制到run；checkpoint只记录artifact ID、绝对路径和SHA-256。

## 4.Resolver动作

解析stdout中的`action`，只允许：

- `resumed`：继续返回的`run_path`，复核checkpoint后只执行未完成或已失效步骤。
- `reused`：不创建run，直接复用返回的`report_path`及已完成共享artifact；返回路径必须存在且非空。
- `created`：写入新`run_path`。输入变化时记录parent和已失效的父结果；未受影响的共享artifact由skill按依赖ID显式复用，不能同时出现在`inherited_artifacts`和`invalidated_artifacts`。

正常入口必须无感处理`created/resumed/reused`，不得询问用户。`value-profile`首次resolve时就通过`--result-path`传入本次候选profile路径；已有兼容run仍返回checkpoint已绑定的旧路径，不采用新候选。完成后先发布已接受的共享分析artifact，再调用`financial_run_store.py complete`登记`result_artifact_id`。standalone报告使用默认run内`report.md`；`value-profile`完成时再次传`--result-path <absolute-profile-path>`，使后续`reused.report_path`直接指向最终profile。失败或人工待决保留checkpoint和日志，下一次正常调用自动恢复。

checkpoint是run状态的恢复依据。每次持有index锁后，resolver先扫描run目录：补回checkpoint已存在但index缺失的孤立run，并用checkpoint的完成状态修复滞后的index。身份字段冲突时必须停止，不能猜测或覆盖。

## 5.Mode边界

- `read-filing`、`product-analysis`、`management-analysis`和`financial-redflag-scan`的Mode A调用resolver，standalone报告统一写`data/filings/<ticker>/runs/<run-id>/report.md`。
- 上述4个skill的Mode B不调用run store，不创建run，只返回内存JSON，由父skill写profile。
- `value-profile`调用resolver管理执行状态和共享artifact，但最终可读档案仍写`profiles/<ticker>-<YYYY-MM-DD>[-vN].md`；完成登记使用`financial_run_store.py complete ... --result-path <profile-path>`。
- AI可以自由组织Markdown正文；run store不定义报告栏目或判断字段。

## 6.兼容读取

旧standalone文件只读：

```text
profiles/<ticker>-reading-*-scratch.md
profiles/<ticker>-product-*.md
profiles/<ticker>-mgmt-*.md
profiles/<ticker>-redflags-*.md
```

可以读取旧文件并把可验证内容提升为新共享artifact，但不得移动、覆盖或继续把新执行状态写入旧路径。主`value-profile`文件继续按现有路径读写。
