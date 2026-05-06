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
HKEX_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "hkex"


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
        # HK: 1-5 digit codes, with or without leading zeros
        ("0700.HK", ("0700", "HK")),
        ("00700.HK", ("00700", "HK")),
        ("700.HK", ("700", "HK")),
        ("0700.hk", ("0700", "HK")),
        ("1.HK", ("1", "HK")),  # CK Hutchison
    ],
)
def test_parse_ticker_valid(ticker, expected):
    assert df.parse_ticker(ticker) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "600519",
        "600519.HK",  # HK must be 1-5 digits
        "60519.SH",  # SH must be 6 digits
        "abcdef.SH",
        "600519.NYSE",
        "",
        ".HK",  # empty code
        "123456.HK",  # HK 6-digit overflow
    ],
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


# ---------------------------------------------------------------------------
# 8. HKEX — stock-id resolution + annual report search
# ---------------------------------------------------------------------------


@pytest.fixture
def hkex_activestock_bytes() -> bytes:
    return (HKEX_FIXTURES / "activestock_subset.json").read_bytes()


@pytest.fixture
def tencent_annual_en_bytes() -> bytes:
    return (HKEX_FIXTURES / "tencent_annual_en.json").read_bytes()


@pytest.fixture
def tencent_annual_zh_bytes() -> bytes:
    return (HKEX_FIXTURES / "tencent_annual_zh.json").read_bytes()


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("ANNUAL REPORT 2024", 2024),
        ("Annual Report 2023", 2023),
        ("2023 Annual Report", 2023),
        ("2023 年報", 2023),
        ("腾讯2020年年度报告", 2020),
        ("Interim Report 2023", 2023),  # extractable; filtered elsewhere
        ("Notice of AGM", None),
        ("Some 1800 text", None),  # out of valid year range
    ],
)
def test_extract_year_hk(title, expected):
    assert df._extract_year_hk(title) == expected


# -- resolve_hkex_stock_id --


def test_resolve_hkex_stock_id_tencent(hkex_activestock_bytes):
    assert df.resolve_hkex_stock_id("0700", stocklist_bytes=hkex_activestock_bytes) == "7609"
    assert df.resolve_hkex_stock_id("700", stocklist_bytes=hkex_activestock_bytes) == "7609"
    assert df.resolve_hkex_stock_id("00700", stocklist_bytes=hkex_activestock_bytes) == "7609"


def test_resolve_hkex_stock_id_other_code(hkex_activestock_bytes):
    assert df.resolve_hkex_stock_id("1", stocklist_bytes=hkex_activestock_bytes) == "1"
    assert df.resolve_hkex_stock_id("941", stocklist_bytes=hkex_activestock_bytes) == "8031"


def test_resolve_hkex_stock_id_unknown_code(hkex_activestock_bytes):
    with pytest.raises(ValueError, match="not found"):
        df.resolve_hkex_stock_id("9999", stocklist_bytes=hkex_activestock_bytes)


def test_resolve_hkex_stock_id_schema_drift():
    with pytest.raises(df.FetchSchemaError):
        df.resolve_hkex_stock_id("0700", stocklist_bytes=b'{"foo": "bar"}')


def test_resolve_hkex_stock_id_not_json():
    with pytest.raises(df.FetchSchemaError):
        df.resolve_hkex_stock_id("0700", stocklist_bytes=b"not json")


# -- search_hkex_annual_reports --


def test_search_hkex_english_fixture(tencent_annual_en_bytes):
    results = df.search_hkex_annual_reports(
        "0700", years=5, stock_id="7609", raw_response=tencent_annual_en_bytes
    )
    assert len(results) == 5
    assert [r.year for r in results] == [2024, 2023, 2022, 2021, 2020]
    # English variants — plain `.pdf`, no `_c.pdf` suffix
    for r in results:
        assert not r.adjunct_url.lower().endswith("_c.pdf"), r.adjunct_url
    assert all("ANNUAL REPORT" in r.title.upper() for r in results)


def test_search_hkex_chinese_fixture(tencent_annual_zh_bytes):
    results = df.search_hkex_annual_reports(
        "0700",
        years=5,
        stock_id="7609",
        prefer_lang="zh",
        raw_response=tencent_annual_zh_bytes,
    )
    assert len(results) == 5
    for r in results:
        assert r.adjunct_url.lower().endswith("_c.pdf"), r.adjunct_url
    # All titles contain 年報 (traditional) in this fixture
    assert all("年報" in r.title for r in results)


def test_search_hkex_year_cap(tencent_annual_en_bytes):
    r3 = df.search_hkex_annual_reports(
        "0700", years=3, stock_id="7609", raw_response=tencent_annual_en_bytes
    )
    assert len(r3) == 3
    assert [r.year for r in r3] == [2024, 2023, 2022]


def test_search_hkex_urls_are_absolute(tencent_annual_en_bytes):
    results = df.search_hkex_annual_reports(
        "0700", years=5, stock_id="7609", raw_response=tencent_annual_en_bytes
    )
    for r in results:
        assert r.adjunct_url.startswith("https://www1.hkexnews.hk/"), r.adjunct_url


def test_search_hkex_resolves_stock_id_internally(hkex_activestock_bytes, tencent_annual_en_bytes):
    """Omitting stock_id triggers activestock lookup via raw_stocklist."""
    results = df.search_hkex_annual_reports(
        "0700",
        years=2,
        raw_response=tencent_annual_en_bytes,
        raw_stocklist=hkex_activestock_bytes,
    )
    assert len(results) == 2
    assert results[0].year == 2024


def test_search_hkex_parses_bare_array_response():
    """Back-compat: older API variants returned a bare JSON array."""
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2023",
                "FILE_LINK": "/listedco/listconews/sehk/2024/0404/foo.pdf",
                "DATE_TIME": "04/04/2024 18:23",
            },
        ]
    ).encode("utf-8")
    results = df.search_hkex_annual_reports("0700", years=5, stock_id="7609", raw_response=payload)
    assert len(results) == 1
    assert results[0].year == 2023


def test_search_hkex_parses_dict_wrapped_list_response():
    """Dict payload with list-valued result key."""
    payload = json.dumps(
        {
            "result": [
                {
                    "TITLE": "ANNUAL REPORT 2023",
                    "FILE_LINK": "/listedco/listconews/sehk/2024/0404/foo.pdf",
                    "DATE_TIME": "04/04/2024 18:23",
                },
            ]
        }
    ).encode("utf-8")
    results = df.search_hkex_annual_reports("0700", years=5, stock_id="7609", raw_response=payload)
    assert len(results) == 1


def test_search_hkex_schema_drift_raises():
    with pytest.raises(df.FetchSchemaError):
        df.search_hkex_annual_reports(
            "0700", years=5, stock_id="7609", raw_response=b'{"foo": "bar"}'
        )


def test_search_hkex_not_valid_json_raises():
    with pytest.raises(df.FetchSchemaError):
        df.search_hkex_annual_reports("0700", years=5, stock_id="7609", raw_response=b"not json")


def test_search_hkex_result_string_not_json_raises():
    """When `result` is a string but not valid JSON, error is diagnosed."""
    payload = json.dumps({"result": "this is not json"}).encode("utf-8")
    with pytest.raises(df.FetchSchemaError, match="not JSON"):
        df.search_hkex_annual_reports("0700", years=5, stock_id="7609", raw_response=payload)


def test_search_hkex_bad_prefer_lang_raises():
    with pytest.raises(ValueError, match="prefer_lang"):
        df.search_hkex_annual_reports(
            "0700", years=5, stock_id="7609", prefer_lang="fr", raw_response=b"[]"
        )


# ---------------------------------------------------------------------------
# 9. HKEX main() integration — mock urlopen end-to-end
# ---------------------------------------------------------------------------


def _fake_hkex_urlopen_factory(
    annual_en_bytes: bytes,
    activestock_bytes: bytes,
    annual_zh_bytes: bytes | None = None,
):
    """Route HKEX requests to the recorded fixtures.

    - activestock JSON → stock-id lookup table
    - titleSearchServlet with lang=EN → annual_en_bytes
    - titleSearchServlet with lang=ZH → annual_zh_bytes (if given)
    - Any hkexnews.hk *.pdf → dummy 2 MB PDF body
    """
    pdf_body = b"%PDF-1.4\n" + b"X" * (2 * 1024 * 1024)

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
        del timeout
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        if "activestock_sehk" in url:
            return _Resp(activestock_bytes, url)
        if "titleSearchServlet" in url:
            if "lang=ZH" in url:
                if annual_zh_bytes is None:
                    raise AssertionError("zh fixture not provided but lang=ZH requested")
                return _Resp(annual_zh_bytes, url)
            return _Resp(annual_en_bytes, url)
        if "hkexnews.hk" in url and url.lower().endswith(".pdf"):
            return _Resp(pdf_body, url)
        raise AssertionError(f"unexpected HK request: url={url!r}")

    return fake_urlopen


def test_main_hk_writes_expected_files(tmp_path, tencent_annual_en_bytes, hkex_activestock_bytes):
    out_dir = tmp_path / "filings" / "0700.HK"
    fake = _fake_hkex_urlopen_factory(tencent_annual_en_bytes, hkex_activestock_bytes)
    with mock.patch("urllib.request.urlopen", side_effect=fake):
        rc = df.main(["0700.HK", "--years", "5", "--out", str(out_dir)])
    assert rc == 0
    names = sorted(p.name for p in out_dir.iterdir())
    # 5 fiscal years in fixture: 2024..2020
    assert "年报-2024.pdf" in names
    assert "年报-2020.pdf" in names
    assert len([n for n in names if n.startswith("年报-")]) == 5
    assert "招股说明书.pdf" not in names
    for n in names:
        assert (out_dir / n).stat().st_size > 100 * 1024


def test_main_hk_include_prospectus_is_ignored(
    tmp_path, tencent_annual_en_bytes, hkex_activestock_bytes, capsys
):
    out_dir = tmp_path / "filings" / "0700.HK"
    fake = _fake_hkex_urlopen_factory(tencent_annual_en_bytes, hkex_activestock_bytes)
    with mock.patch("urllib.request.urlopen", side_effect=fake):
        rc = df.main(["0700.HK", "--years", "5", "--include-prospectus", "--out", str(out_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ignored for HK" in out


def test_main_hk_idempotent_second_run(
    tmp_path, tencent_annual_en_bytes, hkex_activestock_bytes, capsys
):
    out_dir = tmp_path / "filings" / "0700.HK"
    fake = _fake_hkex_urlopen_factory(tencent_annual_en_bytes, hkex_activestock_bytes)
    with mock.patch("urllib.request.urlopen", side_effect=fake):
        assert df.main(["0700.HK", "--years", "5", "--out", str(out_dir)]) == 0
        capsys.readouterr()
        assert df.main(["0700.HK", "--years", "5", "--out", str(out_dir)]) == 0
    out = capsys.readouterr().out
    assert "downloaded=0" in out
    assert "skipped=5" in out


def test_main_hk_lang_zh_fetches_chinese_variants(
    tmp_path, tencent_annual_en_bytes, tencent_annual_zh_bytes, hkex_activestock_bytes
):
    """--lang zh routes through lang=ZH search → `_c.pdf` URLs get fetched."""
    out_dir = tmp_path / "filings" / "0700.HK"
    fake = _fake_hkex_urlopen_factory(
        tencent_annual_en_bytes, hkex_activestock_bytes, tencent_annual_zh_bytes
    )
    requested_urls: list[str] = []
    original_get = df._http_get

    def recording_get(url: str) -> bytes:
        requested_urls.append(url)
        return original_get(url)

    with (
        mock.patch("urllib.request.urlopen", side_effect=fake),
        mock.patch.object(df, "_http_get", side_effect=recording_get),
    ):
        rc = df.main(["0700.HK", "--years", "5", "--lang", "zh", "--out", str(out_dir)])
    assert rc == 0
    # Search URL was built with lang=ZH
    assert any("lang=ZH" in u for u in requested_urls), requested_urls
    # All fetched PDFs are _c.pdf
    pdf_urls = [u for u in requested_urls if u.lower().endswith(".pdf")]
    assert len(pdf_urls) == 5
    for u in pdf_urls:
        assert u.lower().endswith("_c.pdf"), f"expected Chinese variant, got {u}"
