"""Project and render a research profile as a reader-only HTML document."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from profile_html_renderer import render_reader_html
from profile_reader_projection import (
    assert_reader_only,
    format_removal,
    project_reader_markdown,
)


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
    parser.add_argument("source", type=Path, help="Canonical Markdown profile to render")
    parser.add_argument("-o", "--output", type=Path, help="HTML output path")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve() if args.output else source.with_suffix(".html")
    markdown = source.read_text(encoding="utf-8")
    projection = project_reader_markdown(markdown)
    for removal in projection.removals:
        print(format_removal(removal), file=sys.stderr)
    if projection.removals:
        print(
            f"[reader-projection] removed {len(projection.removals)} machine-only blocks",
            file=sys.stderr,
        )

    document = render_reader_html(projection.markdown)
    assert_reader_only(document)
    _write_atomic(output, document)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
