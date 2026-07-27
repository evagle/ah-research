# 财务Skill无感运行目录实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**为5个财务研究skill建立ticker级共享数据层和自动续跑、复用、增量新建的无感run resolver。

**Architecture:**新增`scripts/financial_run_store.py`作为唯一运行目录边界，通过文件锁、排他目录创建和原子替换维护`runs/index.json`与checkpoint。验证后的昂贵产物按输入指纹提升到ticker共享目录；4个standalone子skill和`value-profile`只调用统一resolver，不再要求用户选择resume、新run或run ID。

**Tech Stack:**Python 3.12标准库、JSON、SHA-256、`fcntl`文件锁、pytest、Markdown skill契约。

**Spec:**`docs/superpowers/specs/2026-07-28-financial-run-layout-design.md`

## Global Constraints

- 正常入口只接收ticker和业务参数，不显示或要求`--resume`、`--start-fresh`或`--run-id`。
- 相同输入优先续跑未完成run，其次复用已完成结果且不创建run。
- 输入变化创建增量子run；只有明确“完全重新分析”创建无parent的clean run。
- canonical manifest、evidence、抽取、facts、metrics、citations、analyses和market产物位于ticker共享层。
- checkpoint、report、draft、候选manifest、query、logs和tmp按run隔离。
- 共享artifact内容寻址且不可原地覆盖。
- Mode B不创建standalone run；父skill是profile唯一写入者。
- 旧standalone文件只读兼容；主`value-profile`最终文件继续保存在`profiles/`。
- 两个中文字符之间不得出现不恰当空格。
- 不提交`.claude/worktrees/`、`AGENTS.md`或`tmp/`。

---

### Task 1:建立Run Store行为边界

**Files:**
- Create:`tests/integration/test_financial_run_store.py`
- Create:`scripts/financial_run_store.py`

**Interfaces:**
- Consumes:`resolve_run(root, ticker, skill_name, target_fiscal_year, as_of, skill_version, input_artifact_ids, parameters, clean=False, now=None)`。
- Produces:`Resolution(action, run_id, run_path, report_path, input_fingerprint, parent_run_id)`，其中`action`只允许`created/resumed/reused`。

- [x] **Step 1:写首批失败行为测试**

测试必须用`tmp_path`调用真实函数并断言：

```python
first = resolve_run(..., input_artifact_ids=["annual:a"], parameters={"section": "all"})
resumed = resolve_run(..., input_artifact_ids=["annual:a"], parameters={"section": "all"})
assert first.action == "created"
assert resumed.action == "resumed"
assert resumed.run_id == first.run_id
```

另覆盖ticker共享目录初始化、run局部目录完整、run ID格式和两个并发分配不会取得相同ID。

- [x] **Step 2:运行测试确认RED**

运行：

```bash
.venv/bin/pytest tests/integration/test_financial_run_store.py -q
```

预期：因`scripts.financial_run_store`不存在而在收集阶段失败。

- [x] **Step 3:实现最小resolver**

实现并导出：

```python
@dataclass(frozen=True)
class Resolution:
    action: Literal["created", "resumed", "reused"]
    run_id: str | None
    run_path: Path | None
    report_path: Path | None
    input_fingerprint: str
    parent_run_id: str | None

def artifact_id(
    artifact_kind: str,
    schema_version: str,
    input_artifact_ids: Sequence[str],
    parameters: Mapping[str, JSONValue],
) -> str: ...

def resolve_run(
    root: Path,
    ticker: str,
    skill_name: str,
    target_fiscal_year: int,
    as_of: date,
    skill_version: str,
    input_artifact_ids: Sequence[str],
    parameters: Mapping[str, JSONValue],
    *,
    clean: bool = False,
    now: datetime | None = None,
) -> Resolution: ...
```

`resolve_run`在`runs/.index.lock`持有排他锁期间读取索引、确定性选择候选、排他创建`vN`目录、写初始checkpoint，再以临时文件+`os.replace`更新索引。

- [x] **Step 4:运行测试确认GREEN**

运行：

```bash
.venv/bin/pytest tests/integration/test_financial_run_store.py -q
```

预期：首批测试PASS。

---

### Task 2:实现复用、继承、终态与共享提升

**Files:**
- Modify:`tests/integration/test_financial_run_store.py`
- Modify:`scripts/financial_run_store.py`

**Interfaces:**
- Consumes:Task 1的`Resolution`和索引。
- Produces:`complete_run(...)`、`promote_artifact(...)`和`discover_legacy_reports(...)`。

- [x] **Step 1:写增量失败测试**

测试必须断言：

```python
complete_run(..., result_artifact_id="analysis:accepted")
reused = resolve_run(...same fingerprint...)
assert reused.action == "reused"
assert reused.run_id is None
assert not new_run_directory_created

changed = resolve_run(..., input_artifact_ids=["annual:b"], ...)
assert changed.action == "created"
assert changed.parent_run_id == first.run_id
```

再断言clean run没有parent；`promote_artifact`把同内容复用到`<ticker>/<kind>/<artifact_id><suffix>`、不同内容不覆盖；旧`profiles/<ticker>-reading/product/mgmt/redflags-*`只被发现，不被移动或修改。

- [x] **Step 2:运行新增测试确认RED**

运行：

```bash
.venv/bin/pytest tests/integration/test_financial_run_store.py -q
```

预期：因终态、提升和legacy接口缺失而失败。

- [x] **Step 3:实现终态和artifact提升**

实现：

```python
def complete_run(
    root: Path,
    ticker: str,
    run_id: str,
    result_artifact_id: str,
    *,
    completed_at: datetime | None = None,
) -> None: ...

def promote_artifact(
    root: Path,
    ticker: str,
    artifact_kind: SharedArtifactKind,
    source: Path,
    schema_version: str,
    input_artifact_ids: Sequence[str],
    parameters: Mapping[str, JSONValue],
) -> PromotedArtifact: ...

def discover_legacy_reports(repo_root: Path, ticker: str) -> tuple[Path, ...]: ...
```

共享kind只允许`manifests/evidence/_extracted/facts/metrics/citations/analyses/market`。发布使用同目录临时文件、`fsync`和排他hard-link；目标已存在时逐字节哈希一致才复用。

- [x] **Step 4:加入CLI并运行全部run store测试**

CLI子命令：

```text
resolve --root ... --ticker ... --skill ... --target-year ... --as-of ... --skill-version ...
complete --root ... --ticker ... --run-id ... --result-artifact-id ...
promote --root ... --ticker ... --kind ... --source ... --schema-version ...
```

所有命令向stdout输出一个JSON对象。运行：

```bash
.venv/bin/pytest tests/integration/test_financial_run_store.py -q
.venv/bin/ruff check scripts/financial_run_store.py tests/integration/test_financial_run_store.py
```

预期：全部PASS且ruff无错误。

---

### Task 3:接入5个Skill

**Files:**
- Modify:`tests/unit/skills/test_financial_skill_contracts.py`
- Modify:`.claude/skills/read-filing/SKILL.md`
- Modify:`.claude/skills/product-analysis/SKILL.md`
- Modify:`.claude/skills/management-analysis/SKILL.md`
- Modify:`.claude/skills/financial-redflag-scan/SKILL.md`
- Modify:`.claude/skills/value-profile/SKILL.md`
- Create:`.claude/skills/read-filing/references/run-store-contract.md`

**Interfaces:**
- Consumes:`financial_run_store.py resolve/complete/promote`CLI。
- Produces:5个skill统一的无感入口、共享/局部路径和Mode A/B边界。

- [x] **Step 1:写失败契约测试**

契约测试必须读取5个skill和run-store reference并断言：

- 正常入口不再出现`--resume <...>`、`--start-fresh`或让用户选择恢复方式。
- 5个skill都引用唯一`run-store-contract.md`。
- 4个Mode A standalone输出为`data/filings/<ticker>/runs/<run-id>/report.md`。
- 4个Mode B不调用resolver且不创建run。
- `value-profile`仍只把最终档案写入`profiles/<ticker>-<YYYY-MM-DD>[-vN].md`。
- shared和run-local目录清单完整。
- “完全重新分析”是唯一clean run入口。
- 旧standalone路径只读兼容。

- [x] **Step 2:运行契约测试确认RED**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k 'run_store or seamless or standalone_run'
```

预期：旧scratch/resume和standalone输出契约仍存在而失败。

- [x] **Step 3:写唯一Run Store契约并修改5个Skill**

`run-store-contract.md`固定：

```text
正常入口→resolve
created/resumed→只写返回run_path
reused→直接读取返回report_path或共享artifact
验证后产物→promote
终态→complete
Mode B→不调用run store
```

删除4个子skill中要求用户决定resume/start-fresh的分支，把scratch checkpoint改为run内`checkpoint.json`。`value-profile`入口调用resolver，但最终报告仍由既有CAS机制写`profiles/`。

- [x] **Step 4:运行契约测试确认GREEN**

运行：

```bash
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py \
  -q -k 'run_store or seamless or standalone_run'
```

预期：PASS。

---

### Task 4:回归验证并发布PR更新

**Files:**
- Modify:`docs/superpowers/plans/2026-07-28-financial-run-layout.md`

**Interfaces:**
- Consumes:Tasks 1至3的实现。
- Produces:可审查提交和更新后的PR #36。

- [x] **Step 1:运行聚焦和完整验证**

运行：

```bash
.venv/bin/pytest tests/integration/test_financial_run_store.py -q
.venv/bin/pytest tests/unit/skills/test_financial_skill_contracts.py -q
.venv/bin/ruff check scripts/financial_run_store.py tests/integration/test_financial_run_store.py tests/unit/skills/test_financial_skill_contracts.py
for skill in read-filing product-analysis management-analysis financial-redflag-scan value-profile; do
  .venv/bin/python /Users/brian_huang/.codex/skills/.system/skill-creator/scripts/quick_validate.py ".claude/skills/$skill"
done
git diff --check
```

中文间距只扫描本次修改的Markdown行；确认没有两个中文字符之间的不恰当ASCII空格。

- [x] **Step 2:自审diff和状态**

确认不包含`.claude/worktrees/`、`AGENTS.md`或`tmp/`，并核对run store没有覆盖共享artifact或跨run写日志。

- [x] **Step 3:提交、推送并更新PR**

提交主题不超过50字符：

```text
Add seamless financial run storage
```

推送`refactor/financial-skill-contracts`并更新PR #36正文，写明目录契约、自动解析行为和实际测试结果。

## Review Follow-up

- [x] 支持`value-profile`通过`complete --result-path`登记并复用`profiles/`中的最终档案。
- [x] `value-profile`在首次resolve时绑定候选profile路径，未完成run恢复时直接返回该路径。
- [x] resolver拒绝复用缺失或空的完成结果。
- [x] checkpoint作为恢复依据，自动补回孤立run并修复滞后的index状态。
- [x] index中缺少checkpoint的不可恢复记录会被清除，不会返回无效`resumed`。
- [x] 内容寻址ID加入artifact字节SHA-256；相同输入但不同内容不会碰撞或覆盖。
- [x] 父结果失效时不再同时列入`inherited_artifacts`和`invalidated_artifacts`。
- [x] 四个分析入口先准备`read-filing`共享证据，再用真实manifest artifact ID解析自身run。
- [x] `read-filing`也在resolver前实际构造候选manifest；query plan哈希不能单独触发复用。
- [x] 排雷Mode A使用`read-filing` Mode B读取内存事实，不创建第二个排雷事实run。
- [x] 专用manifest发布器与通用run-store发布器的职责边界已明确。

## Validation Record

- 财务skill契约与run-store集成测试：`549 passed`。
- 全仓回归基线：`1932 passed,28 skipped`；最后三项审查修复后又运行上述549项聚焦回归。
- Ruff、Python编译、5个skill的`quick_validate.py`、`git diff --check`和中文字符间距扫描均通过。
- 独立审查发现的1个Critical、9个Important和1个Minor问题均已逐项处理；最终复审结果为`PASS`。
