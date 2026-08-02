from __future__ import annotations

from scripts.profile_reader_projection import (
    assert_reader_only,
    project_reader_markdown,
)


def test_reader_projection_removes_machine_blocks_and_preserves_analysis() -> None:
    fingerprint = "a" * 64
    source = f"""# 泡泡玛特投资研究

## Part 1 - 定性分析

## §1 商业模式

### §1.1 行业分析

收入同比增长42.4%，主要由毛绒品类和海外市场拉动。

<!-- **机器引用清单:** `C25-IP`。 -->

**引用:** 2025年年报第20页。

**置信度:** 高

**管理层口径校核:** 收入数据与年报一致。

| 类型 | 原口径指纹 | 主口径指纹 | 影响 |
|---|---|---|---|
| 市场规模 | {fingerprint} | {fingerprint} | 不可拼接 |

角色状态为accepted，路由终态为exhausted，schema_version为1.1。

恢复账本为/Users/example/research/source-index.md。

| 指标 | 2025年 |
|---|---:|
| 收入 | 130.4 |

增长较快，但新品热度和海外履约仍需继续观察。
"""

    result = project_reader_markdown(source)

    assert "收入同比增长42.4%" in result.markdown
    assert "## Part 1 - 定性分析" in result.markdown
    assert "## §1 商业模式" in result.markdown
    assert "### §1.1 行业分析" in result.markdown
    assert "| 收入 | 130.4 |" in result.markdown
    assert "新品热度和海外履约仍需继续观察" in result.markdown
    assert "路由终态" not in result.markdown
    assert fingerprint not in result.markdown
    assert "/Users/example/research/source-index.md" not in result.markdown
    assert "2025年年报第20页" not in result.markdown
    assert {removal.category for removal in result.removals} >= {
        "html-comment",
        "reader-metadata",
        "machine-table",
        "machine-paragraph",
    }
    assert_reader_only(result.markdown)
