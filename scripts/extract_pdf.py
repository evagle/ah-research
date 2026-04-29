"""Extract PDF content (text + images) to a persistent cache directory.

Usage:
    python scripts/extract_pdf.py <pdf_path> [--force] [--skip-images] [--model NAME]

Produces under ``<pdf_parent_dir>/_extracted/<pdf_stem>/``:

  - ``text.md``        — full text with ``<!-- page N -->`` markers between pages.
  - ``images/page-NN-M.png``       — extracted raster images (filtered).
  - ``images/page-NN-M.md``        — Claude-generated Chinese description.
  - ``metadata.json``  — cache version, timestamp, counts, model used.

Second run is idempotent — if ``metadata.json`` exists with a matching cache
version, extraction is skipped unless ``--force`` is passed.

Dependencies:

  - stdlib only for core extraction orchestration.
  - System: ``pdftotext`` + ``pdfimages`` (poppler) — asserted at startup.
  - Pillow — for PPM → PNG conversion + pixel-dimension filtering.
  - anthropic (optional) — for LLM image descriptions. If unavailable or
    ``ANTHROPIC_API_KEY`` is unset, images are still extracted but their
    ``.md`` files contain an error stub instead of a real description.

Contract: matches the Phase-0 spec in
``docs/superpowers/specs/2026-04-28-value-profile-skill-design.md``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_VERSION = "1"
DEFAULT_MODEL = "claude-sonnet-4-6"
MIN_IMAGE_BYTES = 50 * 1024  # 50 KB — filter logos/icons/rules
MIN_IMAGE_DIM = 200  # pixels — filter decorative rasters


IMAGE_PROMPT_ZH = """这是一张从年报 PDF 中提取的图片 (第 {page} 页)。请用中文描述其内容:
- 图/表的类型 (折线图 / 柱状图 / 饼图 / 表格 / 照片 / 示意图)
- 坐标轴标签 + 数值范围 (如果是图表)
- 核心数据点 (3-5 个关键数字或趋势)
- 图的业务含义 (e.g. "2020-2024 营收增速趋势 / 主营业务分产品 收入占比")
如果是纯装饰图 (logo / 署名章 / 分页符 / 二维码), 回答 "装饰性图片, 无分析价值"。"""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExtractError(Exception):
    """Raised when an extraction step fails in a way the CLI cannot recover from."""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class ExtractedImage:
    """One raster image we chose to keep after filtering."""

    page: int  # 1-indexed
    index_on_page: int  # 1-indexed — M in ``page-NN-M``
    path: Path  # final .png path
    width: int
    height: int
    size_bytes: int


@dataclass
class Metadata:
    cache_version: str
    extracted_at: str  # ISO 8601 UTC
    source_pdf: str  # absolute path at extraction time
    page_count: int
    image_count: int  # count of images kept after filtering
    model: str  # anthropic model used (or "" if --skip-images)
    skipped_images: bool = False
    descriptions_skipped: bool = False  # true if API call failed
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------


def _assert_system_deps() -> None:
    missing = [tool for tool in ("pdftotext", "pdfimages") if shutil.which(tool) is None]
    if missing:
        raise ExtractError(
            f"missing system tool(s): {', '.join(missing)}. Install poppler "
            f"(macOS: brew install poppler)."
        )


def cache_dir_for(pdf_path: Path) -> Path:
    """Return ``<pdf_parent>/_extracted/<pdf_stem>/`` for a given PDF."""
    return pdf_path.parent / "_extracted" / pdf_path.stem


def is_cache_valid(cache_dir: Path) -> bool:
    """True if ``metadata.json`` exists with a matching ``cache_version``."""
    meta_path = cache_dir / "metadata.json"
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return meta.get("cache_version") == CACHE_VERSION


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text(pdf_path: Path, out_md: Path) -> int:
    """Run ``pdftotext -layout`` once, split on form-feed, write markdown with
    page markers. Returns page count."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ExtractError(
            f"pdftotext failed (code {result.returncode}): {result.stderr.decode('utf-8', 'replace')}"
        )
    # pdftotext emits \f between pages (and usually a trailing \f at EOF).
    raw = result.stdout.decode("utf-8", errors="replace")
    pages = raw.split("\f")
    # Trim the empty trailing page pdftotext appends after the last form-feed.
    if pages and pages[-1].strip() == "":
        pages = pages[:-1]

    out_md.parent.mkdir(parents=True, exist_ok=True)
    with out_md.open("w", encoding="utf-8") as fh:
        for i, page_text in enumerate(pages, start=1):
            fh.write(f"<!-- page {i} -->\n")
            # Strip only trailing whitespace to preserve intentional leading
            # indentation from -layout mode.
            fh.write(page_text.rstrip())
            fh.write("\n\n")

    return len(pages)


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------


# Parses one data row of `pdfimages -list`. Columns (whitespace-separated):
# page  num  type       width height color comp bpc  enc interp object ID x-ppi y-ppi size ratio
# We only need page, num, width, height.
_LIST_ROW_RE = re.compile(
    r"^\s*(?P<page>\d+)\s+(?P<num>\d+)\s+\S+\s+(?P<width>\d+)\s+(?P<height>\d+)\b"
)


def _parse_pdfimages_list(stdout: str) -> list[dict[str, int]]:
    """Parse ``pdfimages -list`` output → list of {page, num, width, height}.

    Skips the two-line header.
    """
    rows: list[dict[str, int]] = []
    for line in stdout.splitlines():
        m = _LIST_ROW_RE.match(line)
        if not m:
            continue
        rows.append(
            {
                "page": int(m.group("page")),
                "num": int(m.group("num")),
                "width": int(m.group("width")),
                "height": int(m.group("height")),
            }
        )
    return rows


def _convert_and_filter_image(
    src: Path,
    dest: Path,
    width_hint: int | None,
    height_hint: int | None,
) -> ExtractedImage | None:
    """Convert any extracted image (ppm/jpg/png) to PNG at ``dest`` and
    filter by size. Returns the ExtractedImage metadata or None if filtered."""
    from PIL import Image

    try:
        with Image.open(src) as im:
            im.load()
            width, height = im.size
            if width < MIN_IMAGE_DIM or height < MIN_IMAGE_DIM:
                return None
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Convert mode if necessary (e.g. CMYK / PPM indexed).
            if im.mode not in ("RGB", "RGBA", "L"):
                im = im.convert("RGB")
            im.save(dest, format="PNG", optimize=True)
    except OSError:
        return None

    size_bytes = dest.stat().st_size
    if size_bytes < MIN_IMAGE_BYTES:
        dest.unlink(missing_ok=True)
        return None

    # Use hinted page/index from caller; the caller fills those. We just
    # return the geometric + size facts here.
    return ExtractedImage(
        page=0,  # placeholder — caller rewrites
        index_on_page=0,
        path=dest,
        width=width if width_hint is None else width_hint,
        height=height if height_hint is None else height_hint,
        size_bytes=size_bytes,
    )


def extract_images(pdf_path: Path, images_dir: Path) -> list[ExtractedImage]:
    """Run ``pdfimages`` → dump raster images, filter, and return kept set.

    Images that pass the filter are saved as ``page-NN-M.png`` where NN is the
    1-indexed PDF page and M is the 1-indexed image-on-page counter.
    """
    images_dir.mkdir(parents=True, exist_ok=True)

    # 1) Ask pdfimages for the per-image page list BEFORE dumping.
    list_result = subprocess.run(
        ["pdfimages", "-list", str(pdf_path)],
        capture_output=True,
        check=False,
    )
    if list_result.returncode != 0:
        raise ExtractError(
            f"pdfimages -list failed: {list_result.stderr.decode('utf-8', 'replace')}"
        )
    listing = _parse_pdfimages_list(list_result.stdout.decode("utf-8", errors="replace"))

    # 2) Dump all images into a scratch dir under images_dir.
    scratch = images_dir / "_raw"
    scratch.mkdir(parents=True, exist_ok=True)
    prefix = scratch / "img"
    # ``-all`` preserves native format per image (jpg/png/ppm) — matches
    # poppler >=0.50. ``-j`` only keeps jpegs in jpeg form but converts others
    # to ppm; ``-all`` is friendlier for later Pillow handling.
    dump_result = subprocess.run(
        ["pdfimages", "-all", str(pdf_path), str(prefix)],
        capture_output=True,
        check=False,
    )
    if dump_result.returncode != 0:
        raise ExtractError(
            f"pdfimages dump failed: {dump_result.stderr.decode('utf-8', 'replace')}"
        )

    # 3) pdfimages names files ``img-NNN.<ext>`` where NNN is zero-padded and
    #    corresponds 1:1 (in order) to the rows of ``pdfimages -list``. Walk
    #    both in parallel.
    raw_files = sorted(scratch.glob("img-*"))
    if len(raw_files) != len(listing):
        # Skip any ancillary files (masks/soft-masks) that pdfimages may emit
        # for some PDFs. Truncate to the shorter length and log — we degrade
        # gracefully rather than abort.
        n = min(len(raw_files), len(listing))
        raw_files = raw_files[:n]
        listing = listing[:n]

    # Counter of "image index on page" so final filenames are deterministic.
    on_page_counter: dict[int, int] = {}
    kept: list[ExtractedImage] = []
    for raw_path, row in zip(raw_files, listing, strict=False):
        page = row["page"]
        on_page_counter[page] = on_page_counter.get(page, 0) + 1
        idx = on_page_counter[page]
        final_name = f"page-{page:02d}-{idx}.png"
        final_path = images_dir / final_name

        extracted = _convert_and_filter_image(raw_path, final_path, row["width"], row["height"])
        if extracted is None:
            continue
        extracted.page = page
        extracted.index_on_page = idx
        kept.append(extracted)

    # Clean up scratch.
    shutil.rmtree(scratch, ignore_errors=True)
    return kept


# ---------------------------------------------------------------------------
# Image → Chinese description via Claude
# ---------------------------------------------------------------------------


def _build_anthropic_client():  # -> anthropic.Anthropic | None
    """Return an anthropic client if available + API key present, else None."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic(api_key=api_key)


def describe_image(
    client: Any,
    model: str,
    image_path: Path,
    page: int,
) -> str:
    """Send ``image_path`` + Chinese prompt to Claude, return the description text.

    Raises any error the SDK raises so the caller can decide to continue or bail.
    """
    image_bytes = image_path.read_bytes()
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": IMAGE_PROMPT_ZH.format(page=page),
                    },
                ],
            }
        ],
    )
    # Anthropic SDK returns a Message whose .content is a list of content blocks.
    parts: list[str] = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _write_error_stub(md_path: Path, err: str) -> None:
    md_path.write_text(
        f"<!-- LLM description unavailable: {err}. "
        f"Run with --force after setting ANTHROPIC_API_KEY to retry. -->\n",
        encoding="utf-8",
    )


def describe_all_images(
    images: list[ExtractedImage],
    model: str,
) -> tuple[int, list[str]]:
    """For each image, either write a Claude-generated description .md or an
    error stub. Returns (described_count, errors)."""
    client = _build_anthropic_client()
    errors: list[str] = []

    if client is None:
        reason = (
            "ANTHROPIC_API_KEY not set or anthropic package missing"
            if os.environ.get("ANTHROPIC_API_KEY") is None
            else "anthropic package missing"
        )
        for img in images:
            _write_error_stub(img.path.with_suffix(".md"), reason)
        errors.append(reason)
        return 0, errors

    described = 0
    for img in images:
        md_path = img.path.with_suffix(".md")
        if md_path.exists() and md_path.stat().st_size > 0:
            # Cached from a prior (possibly partial) run.
            described += 1
            continue
        try:
            text = describe_image(client, model, img.path, img.page)
        except Exception as e:  # SDK exception types vary across versions
            err = f"{type(e).__name__}: {e}"
            errors.append(f"{img.path.name}: {err}")
            _write_error_stub(md_path, err)
            continue
        md_path.write_text(text + "\n", encoding="utf-8")
        described += 1
    return described, errors


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def extract_pdf(
    pdf_path: Path,
    *,
    force: bool = False,
    skip_images: bool = False,
    model: str = DEFAULT_MODEL,
) -> Metadata:
    """Full extraction pipeline. Returns the Metadata written to cache."""
    _assert_system_deps()
    if not pdf_path.exists():
        raise ExtractError(f"pdf not found: {pdf_path}")

    cache_dir = cache_dir_for(pdf_path)

    # Idempotent skip.
    if not force and is_cache_valid(cache_dir):
        meta = json.loads((cache_dir / "metadata.json").read_text(encoding="utf-8"))
        return Metadata(**meta)

    # Wipe any partial/stale cache on --force.
    if cache_dir.exists() and force:
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    text_md = cache_dir / "text.md"
    images_dir = cache_dir / "images"

    # 1) Text.
    page_count = extract_text(pdf_path, text_md)

    # 2) Images (optional).
    images: list[ExtractedImage] = []
    descriptions_skipped = False
    errors: list[str] = []
    if not skip_images:
        images = extract_images(pdf_path, images_dir)
        _, desc_errors = describe_all_images(images, model)
        if desc_errors:
            descriptions_skipped = True
            errors.extend(desc_errors)

    # 3) Metadata.
    meta = Metadata(
        cache_version=CACHE_VERSION,
        extracted_at=datetime.now(UTC).isoformat(),
        source_pdf=str(pdf_path.resolve()),
        page_count=page_count,
        image_count=len(images),
        model="" if skip_images else model,
        skipped_images=skip_images,
        descriptions_skipped=descriptions_skipped,
        errors=errors,
    )
    (cache_dir / "metadata.json").write_text(
        json.dumps(asdict(meta), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return meta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract PDF text + images to a persistent cache under "
            "<pdf_parent>/_extracted/<pdf_stem>/."
        ),
    )
    parser.add_argument("pdf_path", type=Path, help="Path to the input PDF.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even if cache exists with matching cache_version.",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Extract text only (fast path).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model for image descriptions (default {DEFAULT_MODEL}).",
    )
    args = parser.parse_args(argv)

    pdf_path: Path = args.pdf_path
    try:
        meta = extract_pdf(
            pdf_path,
            force=args.force,
            skip_images=args.skip_images,
            model=args.model,
        )
    except ExtractError as e:
        _print(f"error: {e}")
        return 2

    cache_dir = cache_dir_for(pdf_path)
    _print(f"cache:         {cache_dir}")
    _print(f"pages:         {meta.page_count}")
    _print(f"images kept:   {meta.image_count}")
    _print(f"model:         {meta.model or '(skipped)'}")
    if meta.descriptions_skipped:
        _print("note: LLM descriptions unavailable — see per-image .md stubs.")
    if meta.errors:
        _print(f"errors ({len(meta.errors)}):")
        for e in meta.errors[:5]:
            _print(f"  - {e}")
        if len(meta.errors) > 5:
            _print(f"  … and {len(meta.errors) - 5} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
