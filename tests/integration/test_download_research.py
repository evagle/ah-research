"""Offline tests for scripts/download_research.py.

All HTTP calls mocked via urllib.request.urlopen; no network access."""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "download_research.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("download_research", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["download_research"] = mod
    spec.loader.exec_module(mod)
    return mod


dr = _load_module()


@pytest.fixture(autouse=True)
def _no_rate_limit_delays(monkeypatch):
    monkeypatch.setattr(dr._rate_limiter, "_min_interval", 0.0)
    monkeypatch.setattr(dr.time, "sleep", lambda _s: None)


# ---------------------------------------------------------------------------
# 1. Broker pinyin via override dict
# ---------------------------------------------------------------------------


def test_broker_pinyin_zhongjin():
    assert dr.broker_pinyin("中金公司") == "zhongjin"


def test_broker_pinyin_zhongxin():
    assert dr.broker_pinyin("中信证券") == "zhongxin"


def test_broker_pinyin_huachuang():
    assert dr.broker_pinyin("华创证券") == "huachuang"


def test_broker_pinyin_empty_fallback():
    assert dr.broker_pinyin("") == "unknown"
    assert dr.broker_pinyin("   ") == "unknown"


# ---------------------------------------------------------------------------
# 2. Broker pinyin fallback via pypinyin
# ---------------------------------------------------------------------------


def test_broker_pinyin_unknown_falls_back_to_pypinyin():
    # Not in override dict — should get generic concat lowercase.
    slug = dr.broker_pinyin("某某某研究所")
    assert slug.isascii()
    assert slug.islower()
    assert slug == slug.replace(" ", "")
    assert len(slug) > 0


# ---------------------------------------------------------------------------
# 3. Title sanitization
# ---------------------------------------------------------------------------


def test_title_sanitization_replaces_illegal_chars():
    raw = "贵州茅台:2024年报点评/批价<回升>|研究*"
    s = dr.sanitize_title(raw)
    for bad in '\\/:*?"<>|':
        assert bad not in s
    # Chinese characters preserved.
    assert "贵州茅台" in s
    assert "批价" in s


def test_title_sanitization_collapses_whitespace():
    raw = "白酒板块   深度   报告"
    assert dr.sanitize_title(raw) == "白酒板块-深度-报告"


def test_title_sanitization_caps_length():
    raw = "超长标题" * 50
    s = dr.sanitize_title(raw, max_len=30)
    assert len(s) <= 30


def test_title_sanitization_empty():
    assert dr.sanitize_title("") == "untitled"


# ---------------------------------------------------------------------------
# 4. Depth filter
# ---------------------------------------------------------------------------


def _make_report(title: str, attach_type: str, broker: str = "中金公司") -> dr.ResearchReport:
    from datetime import date

    return dr.ResearchReport(
        info_code="AP20240101000000",
        title=title,
        org_name=broker,
        publish_date=date(2024, 11, 20),
        attach_type=attach_type,
    )


def test_depth_filter_keeps_shendu():
    r = _make_report("贵州茅台:白酒深度", "深度报告")
    assert dr.is_depth_report(r) is True


def test_depth_filter_keeps_shouci():
    r = _make_report("公司首次覆盖", "首次覆盖")
    assert dr.is_depth_report(r) is True


def test_depth_filter_excludes_dianping():
    r = _make_report("2024年报点评", "公司点评")
    assert dr.is_depth_report(r) is False


def test_depth_filter_excludes_genzong():
    r = _make_report("每日跟踪", "跟踪报告")
    assert dr.is_depth_report(r) is False


def test_depth_filter_applied_in_search():
    records = [
        {
            "infoCode": "AP1",
            "title": "深度研究",
            "orgSName": "中金公司",
            "publishDate": "2024-11-20 18:30:00",
            "attachType": "深度报告",
        },
        {
            "infoCode": "AP2",
            "title": "点评",
            "orgSName": "中信证券",
            "publishDate": "2024-11-21 10:00:00",
            "attachType": "公司点评",
        },
        {
            "infoCode": "AP3",
            "title": "首次覆盖某公司",
            "orgSName": "华创证券",
            "publishDate": "2024-11-22 10:00:00",
            "attachType": "公司报告",
        },
    ]
    payload = json.dumps({"size": 3, "data": records}).encode("utf-8")
    results = dr.search_research(
        "600519", years=3, depth_only=True, max_results=50, raw_responses=[payload]
    )
    titles = [r.title for r in results]
    assert "深度研究" in titles
    assert "首次覆盖某公司" in titles
    assert "点评" not in titles


# ---------------------------------------------------------------------------
# 5. Filename format (end-to-end)
# ---------------------------------------------------------------------------


def test_filename_format_zhongjin():
    from datetime import date

    r = dr.ResearchReport(
        info_code="AP202411201640568956",
        title="贵州茅台2024年报点评-批价平稳回升",
        org_name="中金公司",
        publish_date=date(2024, 11, 20),
        attach_type="深度报告",
    )
    assert dr.report_filename(r) == "zhongjin-贵州茅台2024年报点评-批价平稳回升-20241120.pdf"


def test_filename_format_huachuang():
    from datetime import date

    r = dr.ResearchReport(
        info_code="AP1",
        title="白酒板块深度:高端格局稳固",  # contains ':'
        org_name="华创证券",
        publish_date=date(2024, 6, 15),
        attach_type="行业深度",
    )
    fname = dr.report_filename(r)
    assert fname.startswith("huachuang-")
    assert fname.endswith("-20240615.pdf")
    assert ":" not in fname


# ---------------------------------------------------------------------------
# 6. PDF URL fallback
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, body: bytes, url: str = "", status: int = 200) -> None:
        self._body = body
        self.status = status
        self.url = url

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_pdf_url_fallback_to_variant_0(tmp_path):
    """Primary _1.pdf fails (404); _0.pdf succeeds."""
    dest = tmp_path / "out.pdf"
    big_pdf = b"%PDF-1.4\n" + b"X" * (2 * 1024 * 1024)

    calls: list[str] = []

    def fake_urlopen(req, timeout=None):
        del timeout
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        calls.append(url)
        if "_1.pdf" in url:
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)  # type: ignore[arg-type]
        if "_0.pdf" in url:
            return _Resp(big_pdf, url)
        raise AssertionError(f"unexpected url {url}")

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        did = dr.download_pdf("AP123", dest)

    assert did is True
    assert dest.exists() and dest.stat().st_size > 100 * 1024
    assert any("_1.pdf" in u for u in calls)
    assert any("_0.pdf" in u for u in calls)


def test_pdf_url_fallback_all_fail(tmp_path):
    dest = tmp_path / "out.pdf"

    def fake_urlopen(req, timeout=None):
        del timeout
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)  # type: ignore[arg-type]

    with (
        mock.patch("urllib.request.urlopen", side_effect=fake_urlopen),
        pytest.raises(dr.FetchSchemaError, match="all PDF URL variants failed"),
    ):
        dr.download_pdf("AP_MISSING", dest)
    assert not dest.exists()


# ---------------------------------------------------------------------------
# 7. Max cap
# ---------------------------------------------------------------------------


def test_max_cap_stops_at_limit():
    records = [
        {
            "infoCode": f"AP{i:03d}",
            "title": f"深度报告-{i}",
            "orgSName": "中金公司",
            "publishDate": "2024-11-20 10:00:00",
            "attachType": "深度报告",
        }
        for i in range(100)
    ]
    payload = json.dumps({"size": 100, "data": records}).encode("utf-8")
    results = dr.search_research(
        "600519", years=3, depth_only=False, max_results=10, raw_responses=[payload]
    )
    assert len(results) == 10


# ---------------------------------------------------------------------------
# 8. Idempotent skip (file exists > 100KB)
# ---------------------------------------------------------------------------


def test_idempotent_skip_existing_file(tmp_path):
    dest = tmp_path / "zhongjin-existing-20241120.pdf"
    dest.write_bytes(b"%PDF-1.4\n" + b"A" * (300 * 1024))

    with mock.patch("urllib.request.urlopen") as m:
        did = dr.download_pdf("AP_EXISTING", dest)

    assert did is False
    m.assert_not_called()


def test_idempotent_redownload_if_too_small(tmp_path):
    dest = tmp_path / "tiny.pdf"
    dest.write_bytes(b"truncated")

    big_pdf = b"%PDF-1.4\n" + b"X" * (500 * 1024)

    def fake_urlopen(req, timeout=None):
        del timeout
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        return _Resp(big_pdf, url)

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        did = dr.download_pdf("AP1", dest)

    assert did is True
    assert dest.stat().st_size > 100 * 1024


# ---------------------------------------------------------------------------
# 9. Ticker parsing (sanity check)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("600519.SH", ("600519", "SH")),
        ("000001.SZ", ("000001", "SZ")),
        ("600519.sh", ("600519", "SH")),
    ],
)
def test_parse_ticker(ticker, expected):
    assert dr.parse_ticker(ticker) == expected


def test_parse_ticker_invalid():
    with pytest.raises(ValueError):
        dr.parse_ticker("BAD")


# ---------------------------------------------------------------------------
# 10. JSONP wrapper stripping
# ---------------------------------------------------------------------------


def test_parse_jsonp_wrapper():
    jsonp = b'datatable123({"data": [], "size": 0});'
    records = dr._parse_research_list(jsonp)
    assert records == []


def test_parse_plain_json():
    raw = b'{"data": [], "size": 0}'
    records = dr._parse_research_list(raw)
    assert records == []


def test_parse_null_data():
    raw = b'{"data": null, "size": 0}'
    records = dr._parse_research_list(raw)
    assert records == []


def test_parse_schema_error():
    with pytest.raises(dr.FetchSchemaError):
        dr._parse_research_list(b"not json at all {")


# ---------------------------------------------------------------------------
# 11. main() integration — all HTTP mocked
# ---------------------------------------------------------------------------


def test_main_writes_expected_files(tmp_path):
    records = [
        {
            "infoCode": "AP001",
            "title": "贵州茅台-深度研究",
            "orgSName": "中金公司",
            "publishDate": "2024-11-20 18:30:00",
            "attachType": "深度报告",
        },
        {
            "infoCode": "AP002",
            "title": "白酒行业深度",
            "orgSName": "华创证券",
            "publishDate": "2024-06-15 10:00:00",
            "attachType": "行业深度",
        },
    ]
    list_payload = json.dumps({"data": records, "size": 2}).encode("utf-8")
    big_pdf = b"%PDF-1.4\n" + b"X" * (2 * 1024 * 1024)

    def fake_urlopen(req, timeout=None):
        del timeout
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        if "reportapi.eastmoney.com" in url:
            return _Resp(list_payload, url)
        if "pdf.dfcfw.com" in url:
            return _Resp(big_pdf, url)
        raise AssertionError(f"unexpected url: {url}")

    out_dir = tmp_path / "research"
    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rc = dr.main(["600519.SH", "--years", "3", "--depth-only", "--out", str(out_dir)])

    assert rc == 0
    names = sorted(p.name for p in out_dir.iterdir())
    assert any(n.startswith("zhongjin-") and n.endswith("-20241120.pdf") for n in names)
    assert any(n.startswith("huachuang-") and n.endswith("-20240615.pdf") for n in names)
    for n in names:
        assert (out_dir / n).stat().st_size > 100 * 1024


def test_main_bad_ticker_returns_nonzero(tmp_path):
    rc = dr.main(["BAD_TICKER", "--out", str(tmp_path)])
    assert rc == 2


def test_module_no_side_effects_on_import():
    assert dr.RESEARCH_LIST_URL.startswith("https://reportapi.eastmoney.com")
    assert "pdf.dfcfw.com" in dr.PDF_URL_TEMPLATE
