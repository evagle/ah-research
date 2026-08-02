"""Render a research profile Markdown file as a standalone HTML document."""

from __future__ import annotations

import argparse
import html
import os
import re
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
TABLE_PATTERN = re.compile(r"(<table(?:\s[^>]*)?>.*?</table>)", re.DOTALL | re.IGNORECASE)
READER_METADATA_PATTERN = re.compile(
    r"^\*\*(引用|置信度|管理层口径校核)[:：]\*\*(.*)$",
    re.DOTALL,
)


def _heading_text(token: Token) -> str:
    return "".join(child.content for child in token.children or [] if child.type != "image")


def _strip_reader_metadata(source: str) -> str:
    visible: list[str] = []
    skip_reference_list = False

    for line in source.splitlines(keepends=True):
        stripped = line.strip()
        metadata = READER_METADATA_PATTERN.match(stripped)
        if metadata is not None:
            skip_reference_list = metadata.group(1) == "引用" and not metadata.group(2).strip()
            continue

        if skip_reference_list:
            if not stripped or re.match(r"^[-*+]\s+", stripped) or line.startswith((" ", "\t")):
                continue
            skip_reference_list = False

        visible.append(line)

    return "".join(visible)


def _render_markdown(source: str) -> tuple[str, str]:
    markdown = MarkdownIt("commonmark", {"html": True}).enable("table")
    without_comments = COMMENT_PATTERN.sub("", source)
    tokens = markdown.parse(_strip_reader_metadata(without_comments))
    headings: list[tuple[int, str, str]] = []

    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        heading_id = f"section-{len(headings) + 1}"
        token.attrSet("id", heading_id)
        headings.append((int(token.tag[1]), _heading_text(tokens[index + 1]), heading_id))

    title = headings[0][1] if headings else "研究报告"
    toc_items = "\n".join(
        (f'<li class="toc-level-{level}"><a href="#{heading_id}">{html.escape(text)}</a></li>')
        for level, text, heading_id in headings
    )
    toc = f'<nav class="toc" aria-label="目录"><h2>目录</h2><ul>{toc_items}</ul></nav>'
    body = markdown.renderer.render(tokens, markdown.options, {})
    body = TABLE_PATTERN.sub(r'<div class="table-scroll">\1</div>', body)
    return title, f"{toc}\n<main>{body}</main>"


def _document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #202124;
      --muted: #5f6368;
      --line: #dfe3e7;
      --soft: #f6f7f8;
      --accent: #0b57d0;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      font-size: 16px;
      line-height: 1.72;
      letter-spacing: 0;
    }}
    .page {{
      display: grid;
      grid-template-columns: minmax(190px, 240px) minmax(0, 900px);
      gap: 48px;
      width: min(1240px, calc(100% - 48px));
      margin: 0 auto;
      padding: 40px 0 80px;
    }}
    main {{ min-width: 0; }}
    h1, h2, h3, h4 {{
      line-height: 1.32;
      letter-spacing: 0;
      scroll-margin-top: 24px;
    }}
    h1 {{ margin: 0 0 32px; font-size: 32px; }}
    h2 {{
      margin: 48px 0 18px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--line);
      font-size: 24px;
    }}
    h3 {{ margin: 32px 0 12px; font-size: 19px; }}
    h4 {{ margin: 24px 0 10px; font-size: 16px; }}
    p, ul, ol, blockquote {{ margin: 0 0 16px; }}
    a {{
      color: var(--accent);
      text-decoration-thickness: 1px;
      text-underline-offset: 2px;
    }}
    blockquote {{
      margin-left: 0;
      padding: 8px 16px;
      border-left: 3px solid var(--line);
      color: var(--muted);
    }}
    .signal-list {{
      margin: 0 0 16px;
      padding-left: 12px;
    }}
    .signal-item {{
      display: grid;
      grid-template-columns: 8px minmax(0, 1fr);
      column-gap: 10px;
      align-items: start;
      margin-bottom: 8px;
    }}
    .signal-dot {{
      width: 8px;
      height: 8px;
      margin-top: 0.7em;
      border-radius: 50%;
      background: var(--signal-color);
      transform: translateY(-50%);
    }}
    .signal-positive {{ --signal-color: #188038; }}
    .signal-negative {{ --signal-color: #d93025; }}
    .signal-pending {{ --signal-color: #d99a00; }}
    code {{
      padding: 2px 5px;
      border-radius: 3px;
      background: var(--soft);
      font-size: 0.9em;
    }}
    pre {{ overflow: auto; padding: 16px; background: var(--soft); }}
    pre code {{ padding: 0; }}
    .toc {{
      position: sticky;
      top: 24px;
      align-self: start;
      max-height: calc(100vh - 48px);
      overflow: auto;
      border-right: 1px solid var(--line);
      padding-right: 20px;
    }}
    .toc h2 {{
      margin: 0 0 12px;
      padding: 0;
      border: 0;
      font-size: 15px;
    }}
    .toc ul {{ margin: 0; padding: 0; list-style: none; }}
    .toc li {{ margin: 7px 0; line-height: 1.35; }}
    .toc a {{ color: var(--muted); text-decoration: none; }}
    .toc a:hover {{ color: var(--accent); }}
    .toc-level-1 {{ font-weight: 600; }}
    .toc-level-3 {{ padding-left: 12px; font-size: 14px; }}
    .toc-level-4 {{ padding-left: 24px; font-size: 13px; }}
    .table-scroll {{
      max-width: 100%;
      margin: 18px 0 24px;
      overflow-x: auto;
    }}
    .table-heading {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin: 18px 0 10px;
    }}
    .table-meta {{
      flex: 0 0 auto;
      color: var(--muted);
      font-size: 13px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{
      min-width: 96px;
      padding: 9px 11px;
      border: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: var(--soft); font-weight: 600; }}
    td[rowspan] {{
      background: #fafafa;
      font-weight: 600;
      vertical-align: middle;
    }}
    .hierarchy-table {{
      font-variant-numeric: tabular-nums;
    }}
    .hierarchy-table th,
    .hierarchy-table td {{
      border-width: 0 0 1px;
    }}
    .hierarchy-table th {{
      border-top: 1px solid var(--ink);
    }}
    .hierarchy-table th:nth-child(n + 2),
    .hierarchy-table td:nth-child(n + 2) {{
      text-align: right;
    }}
    .hierarchy-table .hierarchy-level-2 {{
      padding-left: 30px;
      font-weight: 600;
    }}
    .hierarchy-table .hierarchy-level-3 {{
      padding-left: 50px;
    }}
    .hierarchy-table .hierarchy-group td {{
      background: #f8f9fa;
      font-weight: 600;
    }}
    .hierarchy-table .hierarchy-subtotal td {{
      font-weight: 600;
    }}
    .hierarchy-table .hierarchy-total td {{
      border-top: 1px solid var(--ink);
      border-bottom: 3px double var(--ink);
      font-weight: 700;
    }}
    @media (max-width: 900px) {{
      .page {{
        display: block;
        width: min(100% - 28px, 760px);
        padding-top: 20px;
      }}
      .toc {{
        position: static;
        max-height: none;
        margin-bottom: 32px;
        padding: 0 0 20px;
        border: 0;
        border-bottom: 1px solid var(--line);
      }}
      .toc-level-3, .toc-level-4 {{ padding-left: 0; }}
      .table-heading {{ align-items: flex-start; }}
      h1 {{ font-size: 27px; }}
      h2 {{ font-size: 21px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    {body}
  </div>
</body>
</html>
"""


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Markdown profile to render")
    parser.add_argument("-o", "--output", type=Path, help="HTML output path")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve() if args.output else source.with_suffix(".html")
    markdown = source.read_text(encoding="utf-8")
    title, body = _render_markdown(markdown)
    _write_atomic(output, _document(title, body))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
