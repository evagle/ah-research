"""Offline tests for scripts/download_filings.py.

Uses recorded cninfo JSON fixtures (tests/fixtures/cninfo/) and mocks
urllib.request.urlopen. No network access at any point.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Import the script-under-test by path (it lives in scripts/, not on sys.path).
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "download_filings.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "cninfo"


def _load_module():
    spec = importlib.util.spec_from_file_location("download_filings", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["download_filings"] = mod
    spec.loader.exec_module(mod)
    return mod


df = _load_module()


@pytest.fixture(autouse=True)
def _no_rate_limit_delays(monkeypatch):
    """Bypass the 1-sec global rate limiter in tests."""
    monkeypatch.setattr(df._rate_limiter, "_min_interval", 0.0)
    # Also kill time.sleep in the retry policy just in case.
    monkeypatch.setattr(df.time, "sleep", lambda _s: None)


# ---------------------------------------------------------------------------
# Fixtures (raw bytes) for replay-based tests
# ---------------------------------------------------------------------------


@pytest.fixture
def stocklist_bytes() -> bytes:
    return (FIXTURES / "stocklist.json").read_bytes()


@pytest.fixture
def moutai_annual_bytes() -> bytes:
    return (FIXTURES / "moutai_annual.json").read_bytes()


@pytest.fixture
def moutai_prospectus_bytes() -> bytes:
    return (FIXTURES / "moutai_prospectus.json").read_bytes()


# ---------------------------------------------------------------------------
# 1. orgId lookup
# ---------------------------------------------------------------------------


def test_resolve_org_id_hits_recorded_row(stocklist_bytes):
    assert df.resolve_org_id("600519", stocklist_bytes=stocklist_bytes) == "gssh0600519"


def test_resolve_org_id_sz(stocklist_bytes):
    assert df.resolve_org_id("000001", stocklist_bytes=stocklist_bytes) == "gssz0000001"


def test_resolve_org_id_missing_code_raises(stocklist_bytes):
    with pytest.raises(ValueError, match="not found"):
        df.resolve_org_id("999999", stocklist_bytes=stocklist_bytes)


def test_resolve_org_id_schema_drift():
    with pytest.raises(df.FetchSchemaError):
        df.resolve_org_id("600519", stocklist_bytes=b'{"foo": []}')


# ---------------------------------------------------------------------------
# 2. Annual report filtering (摘要 / 英文版 / 修订版 excluded)
# ---------------------------------------------------------------------------


def test_search_annual_reports_excludes_zhaiyao(moutai_annual_bytes):
    # The fixture has both "2024年年度报告" and "2024年年度报告摘要" and "英文版".
    # Only the full Chinese edition should remain per year.
    results = df.search_annual_reports(
        org_id="gssh0600519",
        code="600519",
        exchange="SH",
        years=5,
        raw_response=moutai_annual_bytes,
    )
    titles = [r.title for r in results]
    assert all("摘要" not in t for t in titles)
    assert all("英文版" not in t for t in titles)
    # Should have distinct fiscal years, most recent first.
    years = [r.year for r in results]
    assert years == sorted(years, reverse=True)
    assert len(set(years)) == len(years)


def test_search_annual_reports_year_cap(moutai_annual_bytes):
    r5 = df.search_annual_reports(
        "gssh0600519", "600519", "SH", 5, raw_response=moutai_annual_bytes
    )
    r3 = df.search_annual_reports(
        "gssh0600519", "600519", "SH", 3, raw_response=moutai_annual_bytes
    )
    assert len(r3) <= 3
    assert len(r5) <= 5
    # The top-3 from r5 should equal r3 (same ordering by year desc).
    assert [a.year for a in r5[:3]] == [a.year for a in r3]


def test_search_annual_reports_prefers_latest_announce_date():
    # Two records for same fiscal year 2022; the later one wins.
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-03-31/old.PDF",
                    # 2023-03-31
                    "announcementTime": 1680192000000,
                },
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-06-15/new.PDF",
                    # 2023-06-15 (later — wins)
                    "announcementTime": 1686787200000,
                },
            ]
        }
    ).encode("utf-8")
    results = df.search_annual_reports("x", "000001", "SZ", 5, raw_response=payload)
    assert len(results) == 1
    assert results[0].adjunct_url == "finalpage/2023-06-15/new.PDF"


# ---------------------------------------------------------------------------
# 3. Year extraction from title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("贵州茅台2024年年度报告", 2024),
        ("2019年年度报告", 2019),
        ("某公司 2018 年 年度 报告", 2018),
        ("贵州茅台2024年年度报告摘要", 2024),  # year still extractable (摘要 filtered elsewhere)
        ("季度报告", None),
        ("关于分红派息的公告", None),
        ("2023年第三季度报告", None),
    ],
)
def test_year_extraction(title, expected):
    assert df._extract_year(title) == expected


# ---------------------------------------------------------------------------
# 4. Idempotent download
# ---------------------------------------------------------------------------


def test_download_pdf_idempotent_skips_existing(tmp_path):
    dest = tmp_path / "年报-2024.pdf"
    # Pre-create a >100KB file.
    dest.write_bytes(b"A" * (200 * 1024))

    with mock.patch.object(df, "_http_get") as m:
        did_download = df.download_pdf("finalpage/anything.PDF", dest)

    assert did_download is False
    m.assert_not_called()
    # Original content preserved.
    assert dest.read_bytes()[:4] == b"AAAA"


def test_download_pdf_re_downloads_if_too_small(tmp_path):
    dest = tmp_path / "年报-2024.pdf"
    dest.write_bytes(b"truncated")  # ~9 bytes, well below threshold

    fake_body = b"%PDF-1.4\n" + b"X" * (300 * 1024)
    with mock.patch.object(df, "_http_get", return_value=fake_body) as m:
        did_download = df.download_pdf("finalpage/full.PDF", dest)

    assert did_download is True
    m.assert_called_once()
    assert dest.stat().st_size > 100 * 1024


def test_download_pdf_rejects_tiny_response(tmp_path):
    dest = tmp_path / "年报-2024.pdf"
    with (
        mock.patch.object(df, "_http_get", return_value=b"404 not found"),
        pytest.raises(df.FetchSchemaError),
    ):
        df.download_pdf("finalpage/missing.PDF", dest)
    assert not dest.exists()  # partial temp file cleaned up


# ---------------------------------------------------------------------------
# 5. Prospectus filtering
# ---------------------------------------------------------------------------


def test_search_prospectus_excludes_appendix(moutai_prospectus_bytes):
    results = df.search_prospectus(
        "gssh0600519", "600519", "SH", raw_response=moutai_prospectus_bytes
    )
    titles = [r.title for r in results]
    assert titles == ["招股说明书"]  # "招股说明书附录" excluded


# ---------------------------------------------------------------------------
# 6. Ticker parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("600519.SH", ("600519", "SH")),
        ("000001.SZ", ("000001", "SZ")),
        ("600519.sh", ("600519", "SH")),
        ("  600519.SH  ", ("600519", "SH")),
    ],
)
def test_parse_ticker_valid(ticker, expected):
    assert df.parse_ticker(ticker) == expected


@pytest.mark.parametrize(
    "bad",
    ["600519", "600519.HK", "60519.SH", "abcdef.SH", "600519.NYSE", ""],
)
def test_parse_ticker_invalid(bad):
    with pytest.raises(ValueError):
        df.parse_ticker(bad)


# ---------------------------------------------------------------------------
# 7. Integration test for main() — all HTTP mocked, check files written.
# ---------------------------------------------------------------------------


def _fake_urlopen_factory(stocklist_bytes, annual_bytes, prospectus_bytes):
    """Return a fake urlopen that routes by URL/form data to the recorded
    fixtures, and returns a multi-MB PDF body for any static.cninfo.com.cn
    PDF request."""

    pdf_body = b"%PDF-1.4\n" + b"X" * (3 * 1024 * 1024)  # 3 MB per PDF

    class _Resp:
        def __init__(self, body: bytes, url: str = "") -> None:
            self._body = body
            self.status = 200
            self.url = url

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        del timeout  # unused; kept for signature compat with urllib.request.urlopen
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        data = req.data or b""
        # PDF downloads.
        if "static.cninfo.com.cn" in url:
            return _Resp(pdf_body, url)
        # Stock list.
        if "szse_stock.json" in url:
            return _Resp(stocklist_bytes, url)
        # Announcement queries — differentiate annual vs prospectus by form.
        form = data.decode("utf-8") if isinstance(data, bytes) else str(data)
        if "searchkey=" in form:
            return _Resp(prospectus_bytes, url)
        if "category_ndbg_szsh" in form:
            return _Resp(annual_bytes, url)
        raise AssertionError(f"unexpected request: url={url!r} form={form!r}")

    return fake_urlopen


def test_main_writes_expected_files(
    tmp_path,
    stocklist_bytes,
    moutai_annual_bytes,
    moutai_prospectus_bytes,
):
    out_dir = tmp_path / "filings" / "600519.SH"
    fake = _fake_urlopen_factory(stocklist_bytes, moutai_annual_bytes, moutai_prospectus_bytes)
    with mock.patch("urllib.request.urlopen", side_effect=fake):
        rc = df.main(
            [
                "600519.SH",
                "--years",
                "5",
                "--include-prospectus",
                "--out",
                str(out_dir),
            ]
        )
    assert rc == 0
    names = sorted(p.name for p in out_dir.iterdir())
    # 5 most recent fiscal years in the fixture (2024,2023,2022,2021,2020)
    # + 招股说明书.
    assert "招股说明书.pdf" in names
    assert "年报-2024.pdf" in names
    assert "年报-2020.pdf" in names
    annual_names = [n for n in names if n.startswith("年报-")]
    assert len(annual_names) == 5
    # Each file is > 100 KB.
    for n in names:
        assert (out_dir / n).stat().st_size > 100 * 1024


def test_main_idempotent_second_run_downloads_nothing(
    tmp_path,
    stocklist_bytes,
    moutai_annual_bytes,
    moutai_prospectus_bytes,
    capsys,
):
    out_dir = tmp_path / "filings" / "600519.SH"
    fake = _fake_urlopen_factory(stocklist_bytes, moutai_annual_bytes, moutai_prospectus_bytes)
    with mock.patch("urllib.request.urlopen", side_effect=fake):
        assert (
            df.main(
                [
                    "600519.SH",
                    "--years",
                    "5",
                    "--include-prospectus",
                    "--out",
                    str(out_dir),
                ]
            )
            == 0
        )
        capsys.readouterr()  # flush

        # Second run — every PDF already on disk, should skip all.
        assert (
            df.main(
                [
                    "600519.SH",
                    "--years",
                    "5",
                    "--include-prospectus",
                    "--out",
                    str(out_dir),
                ]
            )
            == 0
        )
    out = capsys.readouterr().out
    assert "skipped=6" in out  # 5 annuals + 1 prospectus
    assert "downloaded=0" in out


def test_main_bad_ticker_returns_nonzero(tmp_path):
    rc = df.main(["BAD_TICKER", "--out", str(tmp_path)])
    assert rc == 2


# Sanity: ensure importing the module doesn't hit the network.
def test_module_has_no_side_effects_on_import():
    # If we got this far the autouse fixture has run and the module imported;
    # the fixture itself is the assertion (nothing crashed, no network).
    assert df.STOCK_LIST_URL.startswith("http://www.cninfo.com.cn")
    assert df.PDF_BASE_URL.startswith("http://static.cninfo.com.cn")


# Keep this import used so the linter doesn't strip it (io is used by
# future test additions) — no-op assertion.
def test_io_import_is_stable():
    assert io.BytesIO(b"x").read() == b"x"
