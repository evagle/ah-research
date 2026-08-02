from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "render_profile_html.py"


def test_render_profile_html_creates_reader_focused_companion(tmp_path: Path) -> None:
    source = tmp_path / "sample.md"
    source.write_text(
        """# 公司 & 测试

## 执行摘要

**引用:** 年报第10页。

<!-- **机器引用清单:** `C25-FS`。 -->

<div class="signal-list">
  <div class="signal-item signal-positive"><span class="signal-dot"></span><span>盈利能力强。</span></div>
  <div class="signal-item signal-negative"><span class="signal-dot"></span><span>集中度较高。</span></div>
  <div class="signal-item signal-pending"><span class="signal-dot"></span><span>长期趋势不明。</span></div>
</div>

| 分类 | 数值 |
|---|---:|
| 收入 | 100 |

## 收入结构

<p class="table-heading"><strong>按IP归属划分</strong><span class="table-meta">2025年 · 亿元</span></p>
<table class="hierarchy-table">
  <tr><th>收入类别</th><th>收入</th><th>占总收入</th></tr>
  <tr class="hierarchy-group"><td>自主产品</td><td>367.88</td><td>99.1%</td></tr>
  <tr class="hierarchy-subtotal"><td class="hierarchy-level-2">艺术家IP</td><td>334.06</td><td>90.0%</td></tr>
  <tr><td class="hierarchy-level-3">THE MONSTERS</td><td>141.61</td><td>38.1%</td></tr>
  <tr class="hierarchy-total"><td>合计</td><td>371.20</td><td>100.0%</td></tr>
</table>
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )

    output = source.with_suffix(".html")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(output)
    html = output.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "<title>公司 &amp; 测试</title>" in html
    assert '<nav class="toc"' in html
    assert 'id="section-1"' in html
    assert 'class="table-scroll"' in html
    assert 'class="table-heading"' in html
    assert 'class="table-meta"' in html
    assert 'class="hierarchy-table"' in html
    assert 'class="hierarchy-level-2"' in html
    assert 'class="hierarchy-level-3"' in html
    assert 'class="hierarchy-total"' in html
    assert "2025年 · 亿元" in html
    assert ".hierarchy-table" in html
    assert ".hierarchy-level-2" in html
    assert ".hierarchy-level-3" in html
    assert ".hierarchy-total" in html
    assert "font-variant-numeric: tabular-nums" in html
    assert "机器引用清单" not in html
    assert "年报第10页" in html
    assert "@media (max-width: 900px)" in html
    assert ".signal-positive" in html
    assert ".signal-negative" in html
    assert ".signal-pending" in html
    assert ".signal-list" in html
    assert ".signal-item" in html
    assert "grid-template-columns: 8px minmax(0, 1fr)" in html
    assert "padding-left: 12px" in html
