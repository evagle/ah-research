"""Offline tests for scripts/extract_pdf.py.

All tests mock ``subprocess.run`` (pdftotext / pdfimages) and the anthropic
Messages.create call. No system binaries or network calls are required.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from PIL import Image

# ---------------------------------------------------------------------------
# Import the script-under-test by path (scripts/ is not on sys.path).
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "extract_pdf.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("extract_pdf", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extract_pdf"] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _load_module()


# ---------------------------------------------------------------------------
# Helpers for building fake subprocess.run results.
# ---------------------------------------------------------------------------


def _cp(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _make_png(path: Path, w: int, h: int, colour=(120, 60, 200), noisy: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (w, h), color=colour)
    if noisy:
        # Random-noise pixels defeat PNG compression, giving a large on-disk
        # footprint — needed to exercise the ``>= MIN_IMAGE_BYTES`` filter.
        import random

        rng = random.Random(0xC0FFEE)
        im.putdata(
            [(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(w * h)]
        )
    im.save(path, format="PNG", optimize=False)


def _make_pdftotext_side_effect(pages: list[str]):
    """Return a subprocess.run side-effect that responds to pdftotext + anything."""
    ff = "\f".join(pages).encode("utf-8") + b"\f"

    def _side_effect(cmd, *_a, **_kw):
        if cmd and cmd[0] == "pdftotext":
            return _cp(stdout=ff)
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    return _side_effect


# ---------------------------------------------------------------------------
# Test 1 — idempotent skip when metadata.json matches cache_version
# ---------------------------------------------------------------------------


def test_skip_if_cached(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")

    cache_dir = ex.cache_dir_for(pdf_path)
    cache_dir.mkdir(parents=True)
    (cache_dir / "metadata.json").write_text(
        json.dumps(
            {
                "cache_version": ex.CACHE_VERSION,
                "extracted_at": "2026-04-28T00:00:00+00:00",
                "source_pdf": str(pdf_path),
                "page_count": 42,
                "image_count": 7,
                "model": "claude-sonnet-4-6",
                "skipped_images": False,
                "descriptions_skipped": False,
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    # Anything that tries to run should fail the test.
    def _boom(*_a, **_kw):
        raise AssertionError("should not shell out when cache is valid")

    monkeypatch.setattr(ex.subprocess, "run", _boom)

    meta = ex.extract_pdf(pdf_path)
    assert meta.page_count == 42
    assert meta.image_count == 7


# ---------------------------------------------------------------------------
# Test 2 — text extraction writes <!-- page N --> markers
# ---------------------------------------------------------------------------


def test_text_extraction_writes_page_markers(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    pages = ["first page text", "second page text", "third page text"]

    monkeypatch.setattr(ex.subprocess, "run", _make_pdftotext_side_effect(pages))

    meta = ex.extract_pdf(pdf_path, skip_images=True)

    text_md = ex.cache_dir_for(pdf_path) / "text.md"
    body = text_md.read_text(encoding="utf-8")
    for i in range(1, 4):
        assert f"<!-- page {i} -->" in body
    assert "first page text" in body
    assert "second page text" in body
    assert "third page text" in body
    assert meta.page_count == 3


# ---------------------------------------------------------------------------
# Test 3 — image filtering (size + dimensions)
# ---------------------------------------------------------------------------


def test_image_filtering(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")

    # 4 candidate rasters with varied dims. Only #1 and #3 should survive
    # (both dims ≥ 200, and the PNG payload ≥ 50 KB after save).
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    big_a = raw_root / "big_a.png"
    small_dim = raw_root / "small_dim.png"
    big_b = raw_root / "big_b.png"
    tiny_file = raw_root / "tiny_file.png"

    # A & B — large random-noise PNGs; both dim + size checks pass.
    _make_png(big_a, 1600, 1200, noisy=True)
    _make_png(big_b, 1200, 900, noisy=True)
    # small_dim — 150x150 random noise: file is big enough but dims fail.
    _make_png(small_dim, 150, 150, noisy=True)
    # tiny_file — 300x300 but single-colour so tiny on disk (<50KB).
    _make_png(tiny_file, 300, 300, colour=(255, 255, 255))

    listing = (
        b" page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio\n"
        b"--------------------------------------------------------------------------------\n"
        b"   1     0 image    1600  1200  rgb     3   8  image  no         7  0   150   150  1.0M 50%\n"
        b"   2     0 image     150   150  rgb     3   8  image  no         8  0   150   150   22K 50%\n"
        b"   3     0 image    1200   900  rgb     3   8  image  no         9  0   150   150  800K 50%\n"
        b"   5     0 image     300   300  rgb     3   8  image  no        10  0   150   150   10K 50%\n"
    )

    # pdfimages is called twice: once with -list, once to dump.
    raw_sources = [big_a, small_dim, big_b, tiny_file]

    def _run_side_effect(cmd, *_a, **_kw):
        assert cmd[0] == "pdfimages"
        if "-list" in cmd:
            return _cp(stdout=listing)
        # Dump mode: last arg is the prefix path (e.g. .../_raw/img).
        prefix = Path(cmd[-1])
        for i, src in enumerate(raw_sources):
            dest = prefix.parent / f"img-{i:03d}.png"
            dest.write_bytes(src.read_bytes())
        return _cp(stdout=b"")

    monkeypatch.setattr(ex.subprocess, "run", _run_side_effect)
    # No anthropic key — descriptions degrade gracefully; we only inspect
    # image filtering here.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    images_dir = ex.cache_dir_for(pdf_path) / "images"
    kept = ex.extract_images(pdf_path, images_dir)

    kept_names = sorted(p.path.name for p in kept)
    assert kept_names == ["page-01-1.png", "page-03-1.png"], kept_names
    # Neither filtered file should remain on disk.
    assert not (images_dir / "page-02-1.png").exists()
    assert not (images_dir / "page-05-1.png").exists()
    for img in kept:
        assert img.size_bytes >= ex.MIN_IMAGE_BYTES
        assert img.width >= ex.MIN_IMAGE_DIM
        assert img.height >= ex.MIN_IMAGE_DIM


# ---------------------------------------------------------------------------
# Test 4 — image description call uses base64 payload + Chinese prompt
# ---------------------------------------------------------------------------


def test_image_description_call(tmp_path, monkeypatch):
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_path = img_dir / "page-07-1.png"
    _make_png(img_path, 400, 400, colour=(10, 10, 10))

    # Fake anthropic SDK module, installed in sys.modules before the call.
    captured: dict = {}

    class _FakeBlock:
        text = "这是一张柱状图, 展示 2020-2024 营收。"

    class _FakeMessage:
        content: ClassVar[list] = [_FakeBlock()]

    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeMessage()

    class _FakeAnthropic:
        def __init__(self, api_key: str):
            assert api_key == "test-key"
            self.messages = _FakeMessages()

    fake_mod = type(sys)("anthropic")
    fake_mod.Anthropic = _FakeAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = ex._build_anthropic_client()
    assert client is not None
    text = ex.describe_image(client, "claude-sonnet-4-6", img_path, page=7)

    assert "柱状图" in text
    # Inspect the payload shape — base64 data for the image, Chinese prompt
    # referencing the page.
    msgs = captured["messages"]
    assert msgs[0]["role"] == "user"
    parts = msgs[0]["content"]
    assert parts[0]["type"] == "image"
    assert parts[0]["source"]["type"] == "base64"
    assert parts[0]["source"]["media_type"] == "image/png"
    # base64 of the file must decode back to the PNG bytes.
    import base64 as _b64

    assert _b64.b64decode(parts[0]["source"]["data"]) == img_path.read_bytes()
    assert parts[1]["type"] == "text"
    assert "第 7 页" in parts[1]["text"]
    assert "中文" in parts[1]["text"]
    assert captured["model"] == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Test 5 — --force re-extracts even when cache is valid
# ---------------------------------------------------------------------------


def test_force_reextract(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")

    # Prime a valid cache with stale page_count=999.
    cache_dir = ex.cache_dir_for(pdf_path)
    cache_dir.mkdir(parents=True)
    (cache_dir / "metadata.json").write_text(
        json.dumps(
            {
                "cache_version": ex.CACHE_VERSION,
                "extracted_at": "2020-01-01T00:00:00+00:00",
                "source_pdf": str(pdf_path),
                "page_count": 999,
                "image_count": 0,
                "model": "",
                "skipped_images": True,
                "descriptions_skipped": False,
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (cache_dir / "text.md").write_text("stale content", encoding="utf-8")

    # Now --force with a mocked pdftotext that returns 2 pages.
    monkeypatch.setattr(ex.subprocess, "run", _make_pdftotext_side_effect(["page one", "page two"]))

    meta = ex.extract_pdf(pdf_path, force=True, skip_images=True)

    assert meta.page_count == 2
    body = (cache_dir / "text.md").read_text(encoding="utf-8")
    assert "stale content" not in body
    assert "page one" in body
    assert "<!-- page 1 -->" in body
    assert "<!-- page 2 -->" in body
