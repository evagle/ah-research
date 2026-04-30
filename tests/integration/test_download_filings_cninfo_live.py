"""Live integration tests — hit the real 巨潮资讯网 (cninfo) API.

Gated by ``AH_RESEARCH_LIVE=1`` so CI and routine local test runs don't
require network. Verifies:

    scripts/download_filings.py → cninfo stock list + announcement query → real PDFs

Target ticker is 600519.SH (贵州茅台 / Kweichow Moutai) — stable A-share,
consistent annual-report filing cadence, ground-truth for regression.

Note on fiscal years: Moutai files its 年报 in late March / early April of
the following calendar year. Test assertions use "≥ some known year"
rather than "== this year" so they stay green after each new filing.
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

MOUTAI_CODE = "600519"
MOUTAI_EXCHANGE = "SH"


# ---------------------------------------------------------------------------
# Stock list — orgId resolution
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_resolve_org_id_moutai_live():
    """cninfo stock list is fetched fresh and contains Moutai."""
    org_id = df.resolve_org_id(MOUTAI_CODE)
    assert org_id == "gssh0600519", f"unexpected orgId for Moutai: {org_id}"


@pytest.mark.live
def test_resolve_org_id_unknown_code_raises_live():
    """Graceful error when a code doesn't exist in the live stock list."""
    with pytest.raises(ValueError, match="not found"):
        df.resolve_org_id("999999")


# ---------------------------------------------------------------------------
# Annual-report search
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_search_annual_reports_moutai_returns_recent():
    """cninfo returns Moutai's most recent annual reports, sorted desc."""
    results = df.search_annual_reports("gssh0600519", MOUTAI_CODE, MOUTAI_EXCHANGE, years=3)
    assert len(results) == 3, f"expected 3 annuals, got {len(results)}"
    years = [r.year for r in results]
    assert years == sorted(years, reverse=True), f"years not sorted desc: {years}"
    assert len(set(years)) == len(years), f"duplicate years: {years}"
    # Moutai's first 年报 was filed ~2001; current should be well past 2020.
    assert years[0] >= 2020, f"latest year looks too old: {years[0]}"


@pytest.mark.live
def test_search_annual_reports_moutai_titles_and_urls():
    """Titles match the 年报 pattern; adjunct URLs are plausible cninfo paths."""
    results = df.search_annual_reports("gssh0600519", MOUTAI_CODE, MOUTAI_EXCHANGE, years=3)
    for r in results:
        # Should be the full Chinese annual report, not a 摘要 / 英文版
        assert "年度报告" in r.title, f"unexpected title for {r.year}: {r.title!r}"
        assert "摘要" not in r.title
        assert "英文版" not in r.title
        # cninfo adjunct URLs are relative paths like finalpage/YYYY-MM-DD/ID.PDF
        assert r.adjunct_url.lower().endswith(".pdf"), r.adjunct_url


@pytest.mark.live
def test_search_annual_reports_dates_are_reasonable():
    """Announcement dates are post fiscal-year-end and within a sane window."""
    results = df.search_annual_reports("gssh0600519", MOUTAI_CODE, MOUTAI_EXCHANGE, years=3)
    for r in results:
        assert r.announcement_date >= date(r.year, 1, 1), (
            f"annual report for FY{r.year} filed before Jan 1 {r.year}: {r.announcement_date}"
        )
        # A-share 年报 are due by April 30 of the following year; give slack
        # for revised re-filings.
        assert r.announcement_date <= date(r.year + 2, 12, 31), (
            f"annual report for FY{r.year} filed suspiciously late: {r.announcement_date}"
        )


@pytest.mark.live
def test_search_annual_reports_year_cap_shrinks_results():
    """Asking for fewer years returns fewer or equal records."""
    r5 = df.search_annual_reports("gssh0600519", MOUTAI_CODE, MOUTAI_EXCHANGE, years=5)
    r2 = df.search_annual_reports("gssh0600519", MOUTAI_CODE, MOUTAI_EXCHANGE, years=2)
    assert len(r5) == 5
    assert len(r2) == 2
    assert [a.year for a in r5[:2]] == [a.year for a in r2]


# ---------------------------------------------------------------------------
# Prospectus (招股说明书)
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_search_prospectus_moutai_returns_canonical():
    """Moutai's IPO (2001) prospectus should be on cninfo."""
    results = df.search_prospectus("gssh0600519", MOUTAI_CODE, MOUTAI_EXCHANGE)
    assert len(results) >= 1, "expected at least one 招股说明书 for Moutai"
    for r in results:
        # Canonical title — 附录 / 补充 / 修订 are filtered out upstream
        assert r.title == "招股说明书", f"unexpected prospectus title: {r.title!r}"


# ---------------------------------------------------------------------------
# End-to-end: main() downloads real PDFs
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.slow
def test_main_cninfo_downloads_one_real_annual_report(tmp_path):
    """End-to-end: resolve → search → download one Moutai annual report.

    Bandwidth note: each Moutai 年报 is 10-30 MB. Limit to --years 1."""
    out_dir = tmp_path / "600519.SH"
    rc = df.main(["600519.SH", "--years", "1", "--out", str(out_dir)])
    assert rc == 0

    files = sorted(p.name for p in out_dir.iterdir())
    annuals = [n for n in files if n.startswith("年报-") and n.endswith(".pdf")]
    assert len(annuals) == 1, f"expected 1 年报 pdf, got {files}"

    pdf = out_dir / annuals[0]
    size = pdf.stat().st_size
    assert size > 1 * 1024 * 1024, f"{pdf.name} suspiciously small: {size} bytes"
    with pdf.open("rb") as f:
        head = f.read(5)
    assert head == b"%PDF-", f"{pdf.name} is not a PDF: first bytes = {head!r}"
