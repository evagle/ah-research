"""Live integration tests — hit the real HKEX (香港联交所 披露易) title-search API.

Gated by ``AH_RESEARCH_LIVE=1`` so CI and routine local test runs don't
require network. Verifies:

    scripts/download_filings.py → HKEX titleSearchServlet.do → real PDFs

Target ticker is 0700.HK (腾讯 / Tencent) — stable stock code, steady
annual-report filing cadence, useful ground truth.

Note on fiscal years: Tencent's fiscal year ends Dec 31. Annual reports
are usually filed in late March / early April. Test assertions are
phrased as "≥ some known year" rather than "== this year" so they stay
green after each new filing.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("AH_RESEARCH_LIVE") != "1",
    reason="live integration; set AH_RESEARCH_LIVE=1 to enable",
)

# Import the script-under-test by path (lives in scripts/, not on sys.path).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "download_filings.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("download_filings", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["download_filings"] = mod
    spec.loader.exec_module(mod)
    return mod


df = _load_module()

TENCENT_CODE = "0700"


# ---------------------------------------------------------------------------
# Title search — English preference (default)
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_search_hkex_tencent_returns_recent_annual_reports():
    """Smoke test: HKEX returns Tencent's most recent annual reports."""
    results = df.search_hkex_annual_reports(TENCENT_CODE, years=3)
    assert len(results) == 3, f"expected 3 annual reports, got {len(results)}"

    years = [r.year for r in results]
    # Descending order by fiscal year
    assert years == sorted(years, reverse=True), f"years not sorted desc: {years}"
    # No duplicates
    assert len(set(years)) == len(years), f"duplicate years: {years}"
    # Tencent filed its 2020 annual report in 2021; any test run should be
    # well past that point.
    assert years[0] >= 2020, f"latest year looks too old: {years[0]}"


@pytest.mark.live
def test_search_hkex_tencent_english_default():
    """Default lang=en returns non-`_c.pdf` URLs."""
    results = df.search_hkex_annual_reports(TENCENT_CODE, years=3)
    for r in results:
        assert r.adjunct_url.startswith("https://www1.hkexnews.hk/"), r.adjunct_url
        assert not r.adjunct_url.lower().endswith("_c.pdf"), (
            f"expected English variant for {r.year}, got {r.adjunct_url}"
        )
        # English titles on HKEX typically contain "Annual Report" (case
        # varies — real data is often ALL CAPS like "ANNUAL REPORT 2023").
        assert "annual report" in r.title.lower(), (
            f"unexpected English title for {r.year}: {r.title!r}"
        )


@pytest.mark.live
def test_search_hkex_tencent_chinese_variant():
    """lang=zh returns `_c.pdf` Chinese variants."""
    results = df.search_hkex_annual_reports(TENCENT_CODE, years=3, prefer_lang="zh")
    assert len(results) == 3
    for r in results:
        assert r.adjunct_url.lower().endswith("_c.pdf"), (
            f"expected Chinese variant for {r.year}, got {r.adjunct_url}"
        )


@pytest.mark.live
def test_search_hkex_tencent_dates_are_reasonable():
    """Annual-report announcement dates should be post fiscal-year-end."""
    results = df.search_hkex_annual_reports(TENCENT_CODE, years=3)
    for r in results:
        assert r.announcement_date >= date(r.year, 1, 1), (
            f"annual report for FY{r.year} filed before Jan 1 {r.year}: {r.announcement_date}"
        )
        # Tencent typically files by end of May the following year; give
        # plenty of slack for late filings / our dedupe picking a republished
        # version.
        assert r.announcement_date <= date(r.year + 2, 12, 31), (
            f"annual report for FY{r.year} filed suspiciously late: {r.announcement_date}"
        )


@pytest.mark.live
def test_search_hkex_year_cap_shrinks_results():
    """Asking for fewer years must return fewer or equal records."""
    r5 = df.search_hkex_annual_reports(TENCENT_CODE, years=5)
    r2 = df.search_hkex_annual_reports(TENCENT_CODE, years=2)
    assert len(r5) == 5
    assert len(r2) == 2
    # The top-2 from r5 should match r2 (same ordering).
    assert [a.year for a in r5[:2]] == [a.year for a in r2]


# ---------------------------------------------------------------------------
# End-to-end: title search + real PDF download
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.slow
def test_main_hk_downloads_one_real_annual_report(tmp_path):
    """End-to-end: search + download one Tencent annual report.

    Bandwidth note: each Tencent annual report is 20-50 MB. We limit to
    --years 1 to keep the test footprint small (~30 MB)."""
    out_dir = tmp_path / "0700.HK"
    rc = df.main(["0700.HK", "--years", "1", "--out", str(out_dir)])
    assert rc == 0

    files = sorted(p.name for p in out_dir.iterdir())
    annuals = [n for n in files if n.startswith("年报-") and n.endswith(".pdf")]
    assert len(annuals) == 1, f"expected 1 年报 pdf, got {files}"

    pdf = out_dir / annuals[0]
    size = pdf.stat().st_size
    # Floor set well above an error-page size but well below any real AR.
    # Tencent ARs range ~4-30 MB depending on year / version.
    assert size > 1 * 1024 * 1024, f"{pdf.name} suspiciously small: {size} bytes"
    # %PDF magic bytes at offset 0
    with pdf.open("rb") as f:
        head = f.read(5)
    assert head == b"%PDF-", f"{pdf.name} is not a PDF: first bytes = {head!r}"
