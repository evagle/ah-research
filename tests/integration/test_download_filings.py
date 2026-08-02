"""Offline tests for scripts/download_filings.py.

Uses recorded cninfo JSON fixtures (tests/fixtures/cninfo/) and mocks
urllib.request.urlopen. No network access at any point.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Barrier
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Import the script-under-test by path (it lives in scripts/, not on sys.path).
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
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


def _write_selected_pdf(path: Path, body: bytes, official_url: str) -> None:
    path.write_bytes(body)
    path.with_suffix(path.suffix + ".source.json").write_text(
        json.dumps(
            {
                "adjunct_url": official_url,
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


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
# 2. Annual report filtering and version selection
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
    assert results[0].adjunct_url == ("https://static.cninfo.com.cn/finalpage/2023-06-15/new.PDF")


@pytest.mark.parametrize("version_label", ["更正后", "更正版", "修订版", "更新后"])
def test_search_annual_reports_prefers_later_corrected_full_report(version_label):
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-03-31/original.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "100",
                },
                {
                    "announcementTitle": f"某公司2022年年度报告（{version_label}）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/2023-05-10/corrected.PDF",
                    "announcementTime": 1683676800000,
                    "announcementId": "101",
                },
            ]
        }
    ).encode("utf-8")

    results = df.search_annual_reports("x", "000001", "SZ", 5, raw_response=payload)

    assert len(results) == 1
    assert results[0].title.endswith(f"（{version_label}）")  # noqa: RUF001
    assert results[0].adjunct_url == (
        "https://static.cninfo.com.cn/finalpage/2023-05-10/corrected.PDF"
    )
    assert results[0].replacement_of == "100"


def test_search_annual_reports_excludes_correction_announcement():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告（更正后）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/2023-05-10/corrected.PDF",
                    "announcementTime": 1683676800000,
                },
                {
                    "announcementTitle": "某公司2022年年度报告更正公告",
                    "adjunctUrl": "finalpage/2023-05-09/notice.PDF",
                    "announcementTime": 1683590400000,
                },
            ]
        }
    ).encode("utf-8")

    results = df.search_annual_reports("x", "000001", "SZ", 5, raw_response=payload)

    assert len(results) == 1
    assert results[0].adjunct_url == (
        "https://static.cninfo.com.cn/finalpage/2023-05-10/corrected.PDF"
    )


def test_search_annual_reports_prefers_later_version_on_same_day():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-05-10/original.PDF",
                    "announcementTime": 1683709200000,
                },
                {
                    "announcementTitle": "某公司2022年年度报告（修订版）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/2023-05-10/revised.PDF",
                    "announcementTime": 1683748800000,
                },
            ]
        }
    ).encode("utf-8")

    results = df.search_annual_reports("x", "000001", "SZ", 5, raw_response=payload)

    assert len(results) == 1
    assert results[0].adjunct_url == (
        "https://static.cninfo.com.cn/finalpage/2023-05-10/revised.PDF"
    )


def test_search_annual_reports_accepts_full_report_update_suffix():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2021年年度报告全文(更新后)",
                    "adjunctUrl": "finalpage/2022-05-10/updated.PDF",
                    "announcementTime": 1652112000000,
                    "announcementId": "101",
                }
            ]
        }
    ).encode("utf-8")

    results = df.search_annual_reports("x", "000001", "SZ", 3, raw_response=payload)

    assert [result.year for result in results] == [2021]
    assert results[0].title == "某公司2021年年度报告全文(更新后)"


def test_search_annual_reports_paginates_complete_cninfo_catalog(monkeypatch):
    pages = {
        "1": {
            "totalAnnouncement": 2,
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-03-31/2022.PDF",
                    "announcementTime": 1680192000000,
                }
            ],
        },
        "2": {
            "totalAnnouncement": 2,
            "announcements": [
                {
                    "announcementTitle": "某公司2021年年度报告",
                    "adjunctUrl": "finalpage/2022-03-31/2021.PDF",
                    "announcementTime": 1648684800000,
                }
            ],
        },
    }
    requested_pages = []

    def fake_post(_url, form):
        requested_pages.append(form["pageNum"])
        return json.dumps(pages[form["pageNum"]]).encode("utf-8")

    monkeypatch.setattr(df, "_http_post_form", fake_post)

    results = df.search_annual_reports("x", "000001", "SZ", 5)

    assert requested_pages == ["1", "2"]
    assert [result.year for result in results] == [2022, 2021]


def test_search_annual_reports_handles_leap_day_cutoff():
    results = df.search_annual_reports(
        "x",
        "000001",
        "SZ",
        10,
        as_of=date(2024, 2, 29),
        raw_response=b'{"announcements": []}',
    )
    assert results == []


def test_search_annual_reports_honors_fiscal_year_ceiling():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": f"某公司{year}年年度报告",
                    "adjunctUrl": f"finalpage/{year + 1}/report.PDF",
                    "announcementTime": 1704067200000 + (year - 2020) * 31_536_000_000,
                }
                for year in range(2020, 2024)
            ]
        }
    ).encode("utf-8")

    results = df.search_annual_reports("x", "000001", "SZ", 3, end_year=2021, raw_response=payload)

    assert [result.year for result in results] == [2021, 2020]


def test_search_annual_reports_requires_catalog_total_for_network_query(monkeypatch):
    monkeypatch.setattr(
        df,
        "_http_post_form",
        lambda *_args, **_kwargs: b'{"announcements": []}',
    )

    with pytest.raises(df.FetchSchemaError, match="totalAnnouncement"):
        df.search_annual_reports("x", "000001", "SZ", 5)


def test_search_annual_reports_cancellation_invalidates_prior_version():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-03-31/original.PDF",
                    "announcementTime": 1680192000000,
                },
                {
                    "announcementTitle": "某公司2022年年度报告取消公告",
                    "adjunctUrl": "finalpage/2023-04-01/cancel.PDF",
                    "announcementTime": 1680278400000,
                },
            ]
        }
    ).encode("utf-8")

    assert df.search_annual_reports("x", "000001", "SZ", 5, raw_response=payload) == []


def test_cancellation_only_invalidates_its_explicit_target_version():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/v1.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "100",
                },
                {
                    "announcementTitle": "某公司2022年年度报告（更新后）",
                    "adjunctUrl": "finalpage/v2.PDF",
                    "announcementTime": 1680278400000,
                    "announcementId": "200",
                },
                {
                    "announcementTitle": "某公司2022年年度报告取消公告",
                    "adjunctUrl": "finalpage/cancel-v1.PDF",
                    "announcementTime": 1680364800000,
                    "announcementId": "300",
                    "targetAnnouncementId": "100",
                },
            ]
        }
    ).encode("utf-8")

    results = df.search_annual_reports("x", "000001", "SZ", 5, raw_response=payload)

    assert [result.announcement_id for result in results] == ["200"]


def test_a_share_unrelated_cancellation_does_not_invalidate_annual_report():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/annual.PDF",
                    "announcementTime": 1680192000000,
                },
                {
                    "announcementTitle": "关于取消召开临时股东大会的公告",
                    "adjunctUrl": "finalpage/meeting.PDF",
                    "announcementTime": 1680278400000,
                },
            ]
        }
    ).encode()

    results = df.search_annual_reports(
        "x",
        "000001",
        "SZ",
        5,
        raw_response=payload,
    )

    assert [result.year for result in results] == [2022]


def test_search_annual_reports_unresolved_correction_fails_closed():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-03-31/original.PDF",
                    "announcementTime": 1680192000000,
                },
                {
                    "announcementTitle": "某公司2022年年度报告更正公告",
                    "adjunctUrl": "finalpage/2023-04-01/correction.PDF",
                    "announcementTime": 1680278400000,
                },
            ]
        }
    ).encode("utf-8")

    with pytest.raises(df.FetchSchemaError, match="corrected full report"):
        df.search_annual_reports("x", "000001", "SZ", 5, raw_response=payload)


@pytest.mark.parametrize(
    "notice_title",
    [
        "某公司年度报告更正公告",
        "某公司年度报告取消公告",
    ],
)
def test_a_share_yearless_replacement_notice_fails_closed(notice_title):
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/original.PDF",
                    "announcementTime": 1680192000000,
                },
                {
                    "announcementTitle": notice_title,
                    "adjunctUrl": "finalpage/notice.PDF",
                    "announcementTime": 1680278400000,
                },
            ]
        }
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="fiscal year"):
        df.search_annual_reports("x", "000001", "SZ", 5, raw_response=payload)


def test_search_annual_reports_excludes_post_cutoff_republication():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-03-31/original.PDF",
                    "announcementTime": 1680192000000,
                },
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/2023-06-15/republished.PDF",
                    "announcementTime": 1686787200000,
                },
            ]
        }
    ).encode("utf-8")

    results = df.search_annual_reports(
        "x",
        "000001",
        "SZ",
        5,
        as_of=date(2023, 4, 30),
        raw_response=payload,
    )

    assert len(results) == 1
    assert results[0].adjunct_url == (
        "https://static.cninfo.com.cn/finalpage/2023-03-31/original.PDF"
    )


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
    # Pre-create a valid >100KB PDF whose official bytes are unchanged.
    dest.write_bytes(b"%PDF-1.4\n" + b"A" * (200 * 1024))
    dest.with_suffix(".pdf.source.json").write_text(
        json.dumps(
            {
                "adjunct_url": "finalpage/anything.PDF",
                "sha256": df._sha256_bytes(dest.read_bytes()),
            }
        ),
        encoding="utf-8",
    )

    with mock.patch.object(df, "_http_get", return_value=dest.read_bytes()) as m:
        did_download = df.download_pdf("finalpage/anything.PDF", dest)

    assert did_download is False
    m.assert_called_once()
    # Original content preserved.
    assert dest.read_bytes()[:5] == b"%PDF-"


def test_download_pdf_replaces_existing_file_when_source_version_changes(tmp_path):
    dest = tmp_path / "年报-2024.pdf"
    dest.write_bytes(b"A" * (200 * 1024))
    dest.with_suffix(".pdf.source.json").write_text(
        json.dumps({"adjunct_url": "finalpage/original.PDF"}), encoding="utf-8"
    )
    revised = b"%PDF-1.4\n" + b"R" * (200 * 1024)

    with mock.patch.object(df, "_http_get", return_value=revised) as get:
        did_download = df.download_pdf("finalpage/revised.PDF", dest)

    assert did_download is True
    assert dest.read_bytes() == revised
    get.assert_called_once()
    source = json.loads(dest.with_suffix(".pdf.source.json").read_text(encoding="utf-8"))
    assert source["adjunct_url"] == "finalpage/revised.PDF"


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


def test_download_pdf_rejects_large_non_pdf_response(tmp_path):
    dest = tmp_path / "年报-2024.pdf"
    body = b"<html>upstream error</html>" + b"X" * (200 * 1024)
    with (
        mock.patch.object(df, "_http_get", return_value=body),
        pytest.raises(df.FetchSchemaError, match="PDF signature"),
    ):
        df.download_pdf("finalpage/error.PDF", dest)
    assert not dest.exists()


def test_download_pdf_source_sidecar_records_content_hash(tmp_path):
    dest = tmp_path / "年报-2024.pdf"
    body = b"%PDF-1.4\n" + b"X" * (200 * 1024)
    with mock.patch.object(df, "_http_get", return_value=body):
        assert df.download_pdf("finalpage/report.PDF", dest) is True

    source = json.loads(dest.with_suffix(".pdf.source.json").read_text(encoding="utf-8"))
    assert source["sha256"] == df._sha256_bytes(body)


def test_download_pdf_concurrent_publish_keeps_pdf_and_sidecar_consistent(
    tmp_path,
    monkeypatch,
):
    dest = tmp_path / "年报-2024.pdf"
    bodies = [
        b"%PDF-1.4\n" + b"A" * (200 * 1024),
        b"%PDF-1.4\n" + b"B" * (200 * 1024),
    ]
    fetch_barrier = Barrier(2)
    rename_barrier = Barrier(2)
    body_iter = iter(bodies)
    original_rename = Path.rename

    def synchronized_fetch(_url):
        body = next(body_iter)
        fetch_barrier.wait()
        return body

    def synchronized_rename(path, target):
        if path.name.endswith(".pdf.partial"):
            rename_barrier.wait()
        return original_rename(path, target)

    monkeypatch.setattr(df, "_http_get", synchronized_fetch)
    monkeypatch.setattr(Path, "rename", synchronized_rename)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: df.download_pdf("finalpage/report.PDF", dest),
                range(2),
            )
        )

    assert all(results)
    published = dest.read_bytes()
    source = json.loads(dest.with_suffix(".pdf.source.json").read_text(encoding="utf-8"))
    assert published in bodies
    assert source["sha256"] == df._sha256_bytes(published)


# ---------------------------------------------------------------------------
# 5. Prospectus filtering
# ---------------------------------------------------------------------------


def test_search_prospectus_excludes_appendix(moutai_prospectus_bytes):
    results = df.search_prospectus(
        "gssh0600519", "600519", "SH", raw_response=moutai_prospectus_bytes
    )
    titles = [r.title for r in results]
    assert titles == ["招股说明书"]  # "招股说明书附录" excluded


def test_search_prospectus_respects_as_of_cutoff():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "招股说明书",
                    "adjunctUrl": "finalpage/2020-01-01/original.PDF",
                    "announcementTime": 1577836800000,
                },
                {
                    "announcementTitle": "招股说明书",
                    "adjunctUrl": "finalpage/2024-01-01/republished.PDF",
                    "announcementTime": 1704067200000,
                },
            ]
        }
    ).encode("utf-8")

    results = df.search_prospectus(
        "x", "000001", "SZ", as_of=date(2021, 12, 31), raw_response=payload
    )

    assert len(results) == 1
    assert results[0].adjunct_url.endswith("/2020-01-01/original.PDF")


def test_search_prospectus_paginates_and_prefers_revised_full_document(monkeypatch):
    pages = {
        "1": {
            "totalAnnouncement": 2,
            "announcements": [
                {
                    "announcementTitle": "招股说明书",
                    "adjunctUrl": "finalpage/2020/original.PDF",
                    "announcementTime": 1577836800000,
                }
            ],
        },
        "2": {
            "totalAnnouncement": 2,
            "announcements": [
                {
                    "announcementTitle": "招股说明书（修订稿）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/2021/revised.PDF",
                    "announcementTime": 1609459200000,
                }
            ],
        },
    }
    requested_pages = []

    def fake_post(_url, form):
        requested_pages.append(form["pageNum"])
        return json.dumps(pages[form["pageNum"]]).encode("utf-8")

    monkeypatch.setattr(df, "_http_post_form", fake_post)
    results = df.search_prospectus("x", "000001", "SZ")

    assert requested_pages == ["1", "2"]
    assert results[0].adjunct_url.endswith("/2021/revised.PDF")


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
        if "tabName=fulltext" in form:
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
    annual_names = [n for n in names if n.startswith("年报-") and n.endswith(".pdf")]
    assert len(annual_names) == 5
    # Each file is > 100 KB.
    for n in (name for name in names if name.endswith(".pdf")):
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
    assert df.STOCK_LIST_URL.startswith("https://www.cninfo.com.cn")
    assert df.PDF_BASE_URL.startswith("https://static.cninfo.com.cn")


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
        ("Annual Report 2024/25", 2025),
        ("2024/25 Annual Report", 2025),
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


def test_search_hkex_excludes_post_cutoff_republication():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/listconews/sehk/2023/0331/original.pdf",
                "DATE_TIME": "31/03/2023 18:00",
            },
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/listconews/sehk/2023/0615/republished.pdf",
                "DATE_TIME": "15/06/2023 18:00",
            },
        ]
    ).encode("utf-8")

    results = df.search_hkex_annual_reports(
        "0700",
        years=5,
        as_of=date(2023, 4, 30),
        stock_id="7609",
        raw_response=payload,
    )

    assert len(results) == 1
    assert results[0].adjunct_url.endswith("/2023/0331/original.pdf")


def test_search_hkex_later_cancellation_invalidates_revision():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/listconews/sehk/2023/0331/original.pdf",
                "DATE_TIME": "31/03/2023 18:00",
            },
            {
                "TITLE": "REVISED ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/listconews/sehk/2023/0510/revised.pdf",
                "DATE_TIME": "10/05/2023 18:00",
            },
            {
                "TITLE": "CANCELLATION OF ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/listconews/sehk/2023/0615/cancelled.pdf",
                "DATE_TIME": "15/06/2023 18:00",
            },
        ]
    ).encode("utf-8")

    results = df.search_hkex_annual_reports("0700", years=5, stock_id="7609", raw_response=payload)

    assert results == []


def test_hk_unrelated_cancellation_does_not_invalidate_annual_report():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/annual.pdf",
                "DATE_TIME": "31/03/2023 18:00",
            },
            {
                "TITLE": "CANCELLATION OF SHARE OPTIONS",
                "FILE_LINK": "/listedco/options.pdf",
                "DATE_TIME": "01/04/2023 18:00",
            },
        ]
    ).encode()

    results = df.search_hkex_annual_reports(
        "0700",
        years=5,
        stock_id="7609",
        raw_response=payload,
    )

    assert [result.year for result in results] == [2022]


def test_search_hkex_handles_leap_day_cutoff():
    results = df.search_hkex_annual_reports(
        "0700",
        years=10,
        as_of=date(2024, 2, 29),
        stock_id="7609",
        raw_response=b"[]",
    )
    assert results == []


def test_search_hkex_fails_closed_when_catalog_hits_row_limit():
    payload = json.dumps(
        [
            {
                "TITLE": f"ANNUAL REPORT 2022 SUPPLEMENT {index}",
                "FILE_LINK": f"/listedco/{index}.pdf",
                "DATE_TIME": "10/05/2023 18:00",
            }
            for index in range(100)
        ]
    ).encode("utf-8")

    with pytest.raises(df.FetchSchemaError, match="rowRange"):
        df.search_hkex_annual_reports("0700", years=5, stock_id="7609", raw_response=payload)


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


def test_main_hk_writes_expected_files(
    tmp_path, tencent_annual_en_bytes, hkex_activestock_bytes, monkeypatch
):
    out_dir = tmp_path / "filings" / "0700.HK"
    fake = _fake_hkex_urlopen_factory(tencent_annual_en_bytes, hkex_activestock_bytes)
    periods = [date(year, 12, 31) for year in range(2024, 2019, -1)]
    monkeypatch.setattr(df, "extract_hk_report_period_end", lambda _path: periods.pop(0))
    with mock.patch("urllib.request.urlopen", side_effect=fake):
        rc = df.main(["0700.HK", "--years", "5", "--out", str(out_dir)])
    assert rc == 0
    names = sorted(p.name for p in out_dir.iterdir())
    # 5 fiscal years in fixture: 2024..2020
    assert "年报-2024.pdf" in names
    assert "年报-2020.pdf" in names
    assert len([n for n in names if n.startswith("年报-") and n.endswith(".pdf")]) == 5
    assert "招股说明书.pdf" not in names
    for n in (name for name in names if name.endswith(".pdf")):
        assert (out_dir / n).stat().st_size > 100 * 1024


def test_main_hk_include_prospectus_is_ignored(
    tmp_path, tencent_annual_en_bytes, hkex_activestock_bytes, capsys, monkeypatch
):
    out_dir = tmp_path / "filings" / "0700.HK"
    fake = _fake_hkex_urlopen_factory(tencent_annual_en_bytes, hkex_activestock_bytes)
    periods = [date(year, 12, 31) for year in range(2024, 2019, -1)]
    monkeypatch.setattr(df, "extract_hk_report_period_end", lambda _path: periods.pop(0))
    with mock.patch("urllib.request.urlopen", side_effect=fake):
        rc = df.main(["0700.HK", "--years", "5", "--include-prospectus", "--out", str(out_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ignored for HK" in out


def test_main_hk_idempotent_second_run(
    tmp_path, tencent_annual_en_bytes, hkex_activestock_bytes, capsys, monkeypatch
):
    out_dir = tmp_path / "filings" / "0700.HK"
    fake = _fake_hkex_urlopen_factory(tencent_annual_en_bytes, hkex_activestock_bytes)
    periods = [date(year, 12, 31) for _ in range(2) for year in range(2024, 2019, -1)]
    monkeypatch.setattr(df, "extract_hk_report_period_end", lambda _path: periods.pop(0))
    with mock.patch("urllib.request.urlopen", side_effect=fake):
        assert df.main(["0700.HK", "--years", "5", "--out", str(out_dir)]) == 0
        capsys.readouterr()
        assert df.main(["0700.HK", "--years", "5", "--out", str(out_dir)]) == 0
    out = capsys.readouterr().out
    assert "downloaded=0" in out
    assert "skipped=5" in out


def test_main_hk_lang_zh_fetches_chinese_variants(
    tmp_path,
    tencent_annual_en_bytes,
    tencent_annual_zh_bytes,
    hkex_activestock_bytes,
    monkeypatch,
):
    """--lang zh routes through lang=ZH search → `_c.pdf` URLs get fetched."""
    out_dir = tmp_path / "filings" / "0700.HK"
    fake = _fake_hkex_urlopen_factory(
        tencent_annual_en_bytes, hkex_activestock_bytes, tencent_annual_zh_bytes
    )
    requested_urls: list[str] = []
    original_get = df._http_get
    periods = [date(year, 12, 31) for year in range(2024, 2019, -1)]
    monkeypatch.setattr(df, "extract_hk_report_period_end", lambda _path: periods.pop(0))

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
    assert len(pdf_urls) == 10
    for u in pdf_urls:
        assert u.lower().endswith("_c.pdf"), f"expected Chinese variant, got {u}"


def test_a_share_historical_target_controls_catalog_start_date(monkeypatch):
    forms = []

    def fake_post(_url, form):
        forms.append(dict(form))
        return b'{"totalAnnouncement": 0, "announcements": []}'

    monkeypatch.setattr(df, "_http_post_form", fake_post)
    df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        3,
        as_of=date(2024, 12, 31),
        end_year=2018,
    )

    assert forms[0]["seDate"].startswith("2015-01-01~")


def test_hk_historical_target_filters_newer_fiscal_years():
    payload = json.dumps(
        [
            {
                "TITLE": f"ANNUAL REPORT {year}",
                "FILE_LINK": f"/listedco/{year}.pdf",
                "DATE_TIME": f"30/04/{year + 1} 18:00",
            }
            for year in range(2016, 2024)
        ]
    ).encode()

    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        as_of=date(2024, 12, 31),
        end_year=2018,
        stock_id="7609",
        raw_response=payload,
    )

    assert [result.year for result in results] == [2018, 2017, 2016]


@pytest.mark.parametrize(
    ("future_title", "future_time"),
    [
        ("某公司2022年年度报告取消公告", 1704067200000),
        ("某公司2022年年度报告更正公告", 1704067200000),
    ],
)
def test_a_share_ignores_post_cutoff_state_transitions(future_title, future_time):
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/original.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "1",
                },
                {
                    "announcementTitle": future_title,
                    "adjunctUrl": "finalpage/future.PDF",
                    "announcementTime": future_time,
                    "announcementId": "2",
                },
            ]
        }
    ).encode()

    results = df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        3,
        as_of=date(2023, 6, 30),
        raw_response=payload,
    )

    assert [result.adjunct_url for result in results] == [
        "https://static.cninfo.com.cn/finalpage/original.PDF"
    ]


def test_hk_ignores_post_cutoff_cancellation():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/original.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "1",
            },
            {
                "TITLE": "CANCELLATION OF ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/cancel.pdf",
                "DATE_TIME": "01/01/2024 18:00",
                "NEWS_ID": "2",
            },
        ]
    ).encode()

    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        as_of=date(2023, 6, 30),
        stock_id="7609",
        raw_response=payload,
    )

    assert [result.year for result in results] == [2022]


def test_correction_notice_requires_a_later_corrected_full_report():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告（更正后）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/first-correction.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "1",
                },
                {
                    "announcementTitle": "某公司2022年年度报告更正公告",
                    "adjunctUrl": "finalpage/second-notice.PDF",
                    "announcementTime": 1680278400000,
                    "announcementId": "2",
                },
            ]
        }
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="later corrected full report"):
        df.search_annual_reports("org", "000001", "SZ", 3, raw_response=payload)


def test_correction_notice_accepts_immediately_preceding_report_in_same_batch():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2012年年度报告（修订版）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/revised.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "62331713",
                },
                {
                    "announcementTitle": "某公司2012年年度报告更正公告",
                    "adjunctUrl": "finalpage/notice.PDF",
                    "announcementTime": 1680192001000,
                    "announcementId": "62331714",
                },
            ]
        }
    ).encode()

    results = df.search_annual_reports("org", "600289", "SH", 3, raw_response=payload)

    assert results[0].announcement_id == "62331713"


def test_correction_notice_with_intervening_words_is_not_selected_as_report():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/original.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "100",
                },
                {
                    "announcementTitle": "关于某公司2022年年度报告部分内容更正公告",
                    "adjunctUrl": "finalpage/notice.PDF",
                    "announcementTime": 1680278400000,
                    "announcementId": "101",
                },
            ]
        }
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="later corrected full report"):
        df.search_annual_reports("org", "000001", "SZ", 3, raw_response=payload)


def test_cninfo_query_does_not_hide_correction_notices_behind_annual_category(
    monkeypatch,
):
    payload = json.dumps(
        {
            "totalAnnouncement": 2,
            "announcements": [
                {
                    "announcementTitle": "某公司2012年年度报告（修订版）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/revised.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "62331713",
                },
                {
                    "announcementTitle": "某公司2012年年度报告更正公告",
                    "adjunctUrl": "finalpage/notice.PDF",
                    "announcementTime": 1680192001000,
                    "announcementId": "62331714",
                },
            ],
        }
    ).encode()
    seen_categories = []

    def fake_post(_url, form):
        seen_categories.append(form["category"])
        return payload

    monkeypatch.setattr(df, "_http_post_form", fake_post)

    results = df.search_annual_reports("org", "600289", "SH", 3)

    assert seen_categories == [""]
    assert results[0].announcement_id == "62331713"


def test_same_timestamp_prefers_revised_version_deterministically():
    shared_time = 1680192000000
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/original.PDF",
                    "announcementTime": shared_time,
                    "announcementId": "100",
                },
                {
                    "announcementTitle": "某公司2022年年度报告（修订版）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/revised.PDF",
                    "announcementTime": shared_time,
                    "announcementId": "101",
                },
            ]
        }
    ).encode()

    results = df.search_annual_reports("org", "000001", "SZ", 3, raw_response=payload)

    assert results[0].adjunct_url == ("https://static.cninfo.com.cn/finalpage/revised.PDF")
    assert results[0].announcement_id == "101"
    assert results[0].sequence_id == 1


def test_cninfo_empty_page_before_official_total_fails_closed(monkeypatch):
    pages = iter(
        [
            b'{"totalAnnouncement": 2, "announcements": ['
            b'{"announcementTitle":"x2022\\u5e74\\u5e74\\u5ea6\\u62a5\\u544a",'
            b'"adjunctUrl":"x.pdf","announcementTime":1680192000000}]}',
            b'{"totalAnnouncement": 2, "announcements": []}',
        ]
    )
    monkeypatch.setattr(df, "_http_post_form", lambda *_args, **_kwargs: next(pages))

    with pytest.raises(df.FetchSchemaError, match="ended before official total"):
        df.search_annual_reports("org", "000001", "SZ", 3)


def test_cninfo_trace_records_every_paginated_query(monkeypatch):
    pages = iter(
        [
            b'{"totalAnnouncement": 2, "announcements": ['
            b'{"announcementTitle":"x2022\\u5e74\\u5e74\\u5ea6\\u62a5\\u544a",'
            b'"adjunctUrl":"a.pdf","announcementTime":1680192000000,'
            b'"announcementId":"1"}]}',
            b'{"totalAnnouncement": 2, "announcements": ['
            b'{"announcementTitle":"x2021\\u5e74\\u5e74\\u5ea6\\u62a5\\u544a",'
            b'"adjunctUrl":"b.pdf","announcementTime":1648656000000,'
            b'"announcementId":"2"}]}',
        ]
    )
    monkeypatch.setattr(df, "_http_post_form", lambda *_args, **_kwargs: next(pages))
    trace = {}

    df.search_annual_reports("org", "000001", "SZ", 3, trace_out=trace)

    assert [query["pageNum"] for query in trace["query_params"]] == ["1", "2"]


def test_cninfo_malformed_network_candidate_fails_closed(monkeypatch):
    monkeypatch.setattr(
        df,
        "_http_post_form",
        lambda *_args, **_kwargs: (
            b'{"totalAnnouncement": 1, "announcements": ['
            b'{"announcementTitle":"x2022\\u5e74\\u5e74\\u5ea6\\u62a5\\u544a",'
            b'"announcementTime":1680192000000}]}'
        ),
    )

    with pytest.raises(df.FetchSchemaError, match="malformed official record"):
        df.search_annual_reports("org", "000001", "SZ", 3)


def test_annual_manifest_records_full_catalog_and_selected_hash(tmp_path):
    selected_pdf = tmp_path / "年报-2022.pdf"
    _write_selected_pdf(
        selected_pdf,
        b"%PDF-selected",
        "finalpage/revised.PDF",
    )
    catalog = [
        df.Announcement(
            title="某公司2022年年度报告",
            adjunct_url="finalpage/original.PDF",
            announcement_date=date(2023, 3, 30),
            announcement_time=datetime(2023, 3, 30, tzinfo=UTC),
            year=2022,
            announcement_id="100",
            sequence_id=0,
            status="superseded",
        ),
        df.Announcement(
            title="某公司2022年年度报告（修订版）",  # noqa: RUF001
            adjunct_url="finalpage/revised.PDF",
            announcement_date=date(2023, 3, 31),
            announcement_time=datetime(2023, 3, 31, tzinfo=UTC),
            year=2022,
            announcement_id="101",
            sequence_id=1,
            status="selected",
        ),
    ]
    trace = {
        "query_url": "https://example.test/query",
        "query_params": {"pageSize": "30", "stock": "000001,org"},
        "response_sha256": "abc",
        "official_total": 2,
    }

    path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2023, 4, 30),
        catalog,
        {2022: selected_pdf},
        trace,
    )

    manifest = json.loads(path.read_text())
    assert manifest["official_result_total"] == 2
    assert [row["announcement_id"] for row in manifest["candidates"]] == ["100", "101"]
    selected = next(row for row in manifest["candidates"] if row["selected"])
    assert selected["file_sha256"] == hashlib.sha256(selected_pdf.read_bytes()).hexdigest()


def test_hk_network_catalog_splits_date_window_at_row_limit(monkeypatch):
    calls = []

    def fake_get(url):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        calls.append((query["fromDate"][0], query["toDate"][0]))
        if len(calls) == 1:
            return json.dumps(
                [
                    {
                        "TITLE": f"ANNUAL REPORT 2022 SUPPLEMENT {index}",
                        "FILE_LINK": f"/listedco/supplement-{index}.pdf",
                        "DATE_TIME": "01/01/2023 12:00",
                    }
                    for index in range(100)
                ]
            ).encode()
        year = 2022 if len(calls) == 2 else 2021
        return json.dumps(
            [
                {
                    "TITLE": f"ANNUAL REPORT {year}",
                    "FILE_LINK": f"/listedco/{year}.pdf",
                    "DATE_TIME": f"30/04/{year + 1} 18:00",
                }
            ]
        ).encode()

    monkeypatch.setattr(df, "_http_get", fake_get)
    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        as_of=date(2024, 12, 31),
        stock_id="7609",
    )

    assert len(calls) == 3
    assert [result.year for result in results] == [2022, 2021]


def test_a_share_recognizes_possessive_correction_notice():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/original.PDF",
                    "announcementTime": 1680192000000,
                },
                {
                    "announcementTitle": "关于某公司2022年年度报告的更正公告",
                    "adjunctUrl": "finalpage/notice.PDF",
                    "announcementTime": 1680278400000,
                },
            ]
        }
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="later corrected full report"):
        df.search_annual_reports("org", "000001", "SZ", 3, raw_response=payload)


def test_hk_correction_notice_requires_later_revised_full_report():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/original.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "1",
            },
            {
                "TITLE": "CORRECTION ANNOUNCEMENT TO ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/notice.pdf",
                "DATE_TIME": "01/04/2023 18:00",
                "NEWS_ID": "2",
            },
        ]
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="later revised full report"):
        df.search_hkex_annual_reports("0700", years=3, stock_id="7609", raw_response=payload)


@pytest.mark.parametrize(
    "notice_title",
    [
        "CORRECTION ANNOUNCEMENT TO ANNUAL REPORT",
        "CANCELLATION OF ANNUAL REPORT",
    ],
)
def test_hk_yearless_replacement_notice_fails_closed(notice_title):
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/original.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "1",
            },
            {
                "TITLE": notice_title,
                "FILE_LINK": "/listedco/notice.pdf",
                "DATE_TIME": "01/04/2023 18:00",
                "NEWS_ID": "2",
            },
        ]
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="fiscal year"):
        df.search_hkex_annual_reports("0700", years=3, stock_id="7609", raw_response=payload)


def test_hk_same_batch_accepts_revised_report_immediately_before_notice():
    payload = json.dumps(
        [
            {
                "TITLE": "REVISED ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/revised.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "100",
            },
            {
                "TITLE": "CORRECTION ANNOUNCEMENT TO ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/notice.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "101",
            },
        ]
    ).encode()

    results = df.search_hkex_annual_reports("0700", years=3, stock_id="7609", raw_response=payload)

    assert results[0].announcement_id == "100"


def test_hk_same_timestamp_cancellation_uses_announcement_order():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/original.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "100",
            },
            {
                "TITLE": "CANCELLATION OF ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/cancel.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "101",
            },
        ]
    ).encode()

    assert (
        df.search_hkex_annual_reports("0700", years=3, stock_id="7609", raw_response=payload) == []
    )


def test_hk_report_period_metadata_rejects_title_year_conflict():
    with pytest.raises(df.FetchSchemaError, match="fiscal-year conflict"):
        df._to_hkex_announcement(
            {
                "TITLE": "ANNUAL REPORT 2024",
                "FILE_LINK": "/listedco/report.pdf",
                "DATE_TIME": "30/06/2025 18:00",
                "NEWS_ID": "100",
                "REPORT_PERIOD_END": "2025-03-31",
            }
        )


def test_hk_network_query_includes_correction_and_cancellation_categories(monkeypatch):
    queries = []

    def fake_get(url):
        queries.append(urllib.parse.parse_qs(urllib.parse.urlparse(url).query))
        return b"[]"

    monkeypatch.setattr(df, "_http_get", fake_get)

    df.search_hkex_annual_reports(
        "0700",
        years=3,
        as_of=date(2024, 12, 31),
        stock_id="7609",
    )

    assert queries[0]["t1code"] == ["-2"]
    assert queries[0]["t2code"] == ["-2"]


def test_hk_traditional_correction_and_revised_titles_are_stateful():
    payload = json.dumps(
        [
            {
                "TITLE": "2022年年度報告",
                "FILE_LINK": "/listedco/original.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "1",
            },
            {
                "TITLE": "更正公告 - 2022年報",
                "FILE_LINK": "/listedco/notice.pdf",
                "DATE_TIME": "01/04/2023 18:00",
                "NEWS_ID": "2",
            },
            {
                "TITLE": "2022年年度報告（修訂版）",  # noqa: RUF001
                "FILE_LINK": "/listedco/revised.pdf",
                "DATE_TIME": "02/04/2023 18:00",
                "NEWS_ID": "3",
            },
        ]
    ).encode()

    catalog = []
    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        stock_id="7609",
        raw_response=payload,
        catalog_out=catalog,
    )

    assert [result.announcement_id for result in results] == ["3"]
    assert catalog[1].status == "correction_notice"
    assert catalog[1].replacement_of == "1"
    assert catalog[2].replacement_of == "1"


def test_hk_same_timestamp_uses_official_id_independent_of_response_order():
    records = [
        {
            "TITLE": "ANNUAL REPORT 2022",
            "FILE_LINK": "/listedco/original.pdf",
            "DATE_TIME": "31/03/2023 18:00",
            "NEWS_ID": "100",
        },
        {
            "TITLE": "CANCELLATION OF ANNUAL REPORT 2022",
            "FILE_LINK": "/listedco/cancel.pdf",
            "DATE_TIME": "31/03/2023 18:00",
            "NEWS_ID": "101",
        },
    ]

    for ordered_records in (records, list(reversed(records))):
        payload = json.dumps(ordered_records).encode()
        assert (
            df.search_hkex_annual_reports("0700", years=3, stock_id="7609", raw_response=payload)
            == []
        )


def test_cninfo_duplicate_pages_fail_closed(monkeypatch):
    record = (
        b'{"announcementTitle":"x2022\\u5e74\\u5e74\\u5ea6\\u62a5\\u544a",'
        b'"adjunctUrl":"x.pdf","announcementTime":1680192000000,'
        b'"announcementId":"same"}'
    )
    pages = iter(
        [
            b'{"totalAnnouncement": 2, "announcements": [' + record + b"]}",
            b'{"totalAnnouncement": 2, "announcements": [' + record + b"]}",
        ]
    )
    monkeypatch.setattr(df, "_http_post_form", lambda *_args, **_kwargs: next(pages))

    with pytest.raises(df.FetchSchemaError, match="duplicate announcement"):
        df.search_annual_reports("org", "000001", "SZ", 3)


def test_after_target_notice_retains_type_and_replacement_relationship(tmp_path):
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2023年年度报告",
                    "adjunctUrl": "original.pdf",
                    "announcementTime": 1711756800000,
                    "announcementId": "100",
                },
                {
                    "announcementTitle": "某公司2023年年度报告更正公告",
                    "adjunctUrl": "notice.pdf",
                    "announcementTime": 1711843200000,
                    "announcementId": "101",
                },
            ]
        }
    ).encode()
    catalog = []

    assert (
        df.search_annual_reports(
            "org",
            "000001",
            "SZ",
            3,
            end_year=2022,
            raw_response=payload,
            catalog_out=catalog,
        )
        == []
    )
    path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2024, 4, 30),
        catalog,
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 2,
        },
    )
    rows = json.loads(path.read_text())["candidates"]

    assert rows[1]["report_type"] == "correction_notice"
    assert rows[1]["replacement_of"] == "100"


def test_empty_official_catalog_causes_cli_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(df, "resolve_org_id", lambda _code: "org")
    monkeypatch.setattr(df, "search_annual_reports", lambda *_args, **_kwargs: [])

    assert df.main(["000001.SZ", "--out", str(tmp_path)]) == 2


def test_hk_timestamp_is_converted_from_hong_kong_time_to_utc():
    ann = df._to_hkex_announcement(
        {
            "TITLE": "ANNUAL REPORT 2022",
            "FILE_LINK": "/listedco/report.pdf",
            "DATE_TIME": "31/03/2023 18:00",
            "NEWS_ID": "100",
        }
    )

    assert ann is not None
    assert ann.announcement_time == datetime(2023, 3, 31, 10, 0, tzinfo=UTC)


def test_hk_cutoff_uses_hong_kong_disclosure_date():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/report.pdf",
                "DATE_TIME": "01/04/2023 01:00",
                "NEWS_ID": "100",
            }
        ]
    ).encode()

    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        as_of=date(2023, 3, 31),
        stock_id="7609",
        raw_response=payload,
    )

    assert results == []


def test_a_share_cutoff_uses_shanghai_disclosure_date():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/report.pdf",
                    "announcementTime": 1682870400000,
                    "announcementId": "100",
                }
            ]
        }
    ).encode()

    results = df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        3,
        as_of=date(2023, 4, 30),
        raw_response=payload,
    )

    assert results == []


def test_a_share_replacement_chain_handles_cancelled_original_catalog_row():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "2021年年度报告（已取消）",  # noqa: RUF001
                    "adjunctUrl": "finalpage/cancelled.pdf",
                    "announcementTime": 1649865600000,
                    "announcementId": "1212914301",
                },
                {
                    "announcementTitle": "关于2021年年度报告的补充更正公告",
                    "adjunctUrl": "finalpage/correction.pdf",
                    "announcementTime": 1649952000000,
                    "announcementId": "1212918971",
                },
                {
                    "announcementTitle": "2021年年度报告全文(更新后)",
                    "adjunctUrl": "finalpage/updated.pdf",
                    "announcementTime": 1649952000000,
                    "announcementId": "1212918972",
                },
            ]
        }
    ).encode()
    catalog = []

    results = df.search_annual_reports(
        "org",
        "002126",
        "SZ",
        3,
        as_of=date(2022, 4, 30),
        raw_response=payload,
        catalog_out=catalog,
    )

    by_id = {announcement.announcement_id: announcement for announcement in catalog}
    assert results[0].announcement_id == "1212918972"
    assert by_id["1212918971"].replacement_of == "1212914301"
    assert by_id["1212918972"].replacement_of == "1212914301"


def test_hk_period_resolver_rejects_title_year_conflict():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2024",
                "FILE_LINK": "/listedco/report.pdf",
                "DATE_TIME": "30/06/2025 18:00",
                "NEWS_ID": "100",
            }
        ]
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="fiscal-year conflict"):
        df.search_hkex_annual_reports(
            "0700",
            years=3,
            stock_id="7609",
            raw_response=payload,
            period_end_resolver=lambda _ann: date(2025, 3, 31),
        )


def test_hk_period_resolver_verifies_existing_metadata():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2024",
                "FILE_LINK": "/listedco/report.pdf",
                "DATE_TIME": "30/06/2025 18:00",
                "NEWS_ID": "100",
                "REPORT_PERIOD_END": "2024-12-31",
            }
        ]
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="metadata/PDF period conflict"):
        df.search_hkex_annual_reports(
            "0700",
            years=3,
            stock_id="7609",
            raw_response=payload,
            period_end_resolver=lambda _ann: date(2025, 3, 31),
        )


def test_hk_period_resolver_sets_year_when_title_has_no_year():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT",
                "FILE_LINK": "/listedco/report.pdf",
                "DATE_TIME": "30/06/2025 18:00",
                "NEWS_ID": "100",
            }
        ]
    ).encode()

    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        stock_id="7609",
        raw_response=payload,
        period_end_resolver=lambda _ann: date(2025, 3, 31),
    )

    assert results[0].year == 2025
    assert results[0].report_period_end == "2025-03-31"


def test_hk_verified_period_is_filtered_by_end_year():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT",
                "FILE_LINK": "/listedco/report.pdf",
                "DATE_TIME": "30/06/2025 18:00",
                "NEWS_ID": "100",
            }
        ]
    ).encode()
    catalog = []

    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        end_year=2024,
        stock_id="7609",
        raw_response=payload,
        catalog_out=catalog,
        period_end_resolver=lambda _ann: date(2025, 3, 31),
    )

    assert results == []
    assert catalog[0].status == "after_target_year"


def test_extract_hk_report_period_end_from_audited_heading(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            b"Annual Report for the year ended 31 March 2025",
            b"Consolidated financial statements for the year ended 31 March 2025",
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=next(outputs),
            stderr=b"",
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2025, 3, 31)


def test_extract_hk_report_period_end_uses_latest_audited_year(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            b"Annual Report for the year ended 31 December 2024",
            (
                b"Comparatives for the year ended 31 December 2020\n"
                b"Consolidated financial statements for the year ended "
                b"31 December 2024"
            ),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=next(outputs),
            stderr=b"",
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2024, 12, 31)


def test_manifest_classifies_notice_and_replacement_relationship(tmp_path):
    original = df.Announcement(
        title="某公司2022年年度报告",
        adjunct_url="original.pdf",
        announcement_date=date(2023, 3, 30),
        announcement_time=datetime(2023, 3, 30, tzinfo=UTC),
        year=2022,
        announcement_id="100",
        sequence_id=0,
        status="superseded",
        report_period_end="2022-12-31",
    )
    revised = df.Announcement(
        title="某公司2022年年度报告（修订版）",  # noqa: RUF001
        adjunct_url="revised.pdf",
        announcement_date=date(2023, 3, 31),
        announcement_time=datetime(2023, 3, 31, tzinfo=UTC),
        year=2022,
        announcement_id="101",
        sequence_id=1,
        status="selected",
        replacement_of="100",
        report_period_end="2022-12-31",
    )
    selected_pdf = tmp_path / "年报-2022.pdf"
    _write_selected_pdf(selected_pdf, b"%PDF-selected", "revised.pdf")

    path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2023, 4, 30),
        [original, revised],
        {2022: selected_pdf},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 2,
        },
    )
    rows = json.loads(path.read_text())["candidates"]

    assert rows[0]["report_type"] == "annual_report"
    assert rows[0]["absolute_path"] is None
    assert rows[1]["replacement_of"] == "100"
    immutable_pdf = Path(rows[1]["absolute_path"])
    assert immutable_pdf.parent == (tmp_path / "versions").resolve()
    assert immutable_pdf.read_bytes() == selected_pdf.read_bytes()


def test_annual_manifest_persists_canonical_identity_fields(tmp_path):
    path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2023, 4, 30),
        [],
        {},
        {"query_params": {"stock": "000001,org"}},
    )

    payload = json.loads(path.read_text())

    assert payload["ticker"] == "000001.SZ"
    assert payload["exchange"] == "SZ"
    assert payload["AS_OF"] == "2023-04-30"
    assert payload["查询发行人代码"] == "000001"


def test_manifests_keep_immutable_pdf_identity_across_refreshes(tmp_path):
    selected_pdf = tmp_path / "年报-2022.pdf"
    _write_selected_pdf(selected_pdf, b"%PDF-original", "original.pdf")
    original = df.Announcement(
        title="某公司2022年年度报告",
        adjunct_url="original.pdf",
        announcement_date=date(2023, 3, 30),
        announcement_time=datetime(2023, 3, 30, tzinfo=UTC),
        year=2022,
        announcement_id="100",
        status="selected",
    )
    first_manifest = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2023, 3, 30),
        [original],
        {2022: selected_pdf},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 1,
        },
    )
    first_payload = json.loads(first_manifest.read_text())
    first_candidate = first_payload["candidates"][0]

    _write_selected_pdf(selected_pdf, b"%PDF-revised", "revised.pdf")
    revised = df.Announcement(
        title="某公司2022年年度报告（修订版）",  # noqa: RUF001
        adjunct_url="revised.pdf",
        announcement_date=date(2023, 4, 2),
        announcement_time=datetime(2023, 4, 2, tzinfo=UTC),
        year=2022,
        announcement_id="101",
        status="selected",
        replacement_of="100",
    )
    original.status = "superseded"
    df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2023, 4, 2),
        [original, revised],
        {2022: selected_pdf},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 2,
        },
    )

    immutable_pdf = Path(first_candidate["absolute_path"])
    assert immutable_pdf != selected_pdf.resolve()
    assert immutable_pdf.read_bytes() == b"%PDF-original"
    assert hashlib.sha256(immutable_pdf.read_bytes()).hexdigest() == first_candidate["file_sha256"]


def test_immutable_pdf_copy_rejects_aba_source_replacement(tmp_path, monkeypatch):
    source = tmp_path / "年报-2022.pdf"
    original = b"%PDF-original"
    source.write_bytes(original)
    real_copy2 = df.shutil.copy2

    def copy_replacement_then_restore(source_path, destination_path):
        source.write_bytes(b"%PDF-replaced")
        result = real_copy2(source_path, destination_path)
        source.write_bytes(original)
        return result

    monkeypatch.setattr(df.shutil, "copy2", copy_replacement_then_restore)

    with pytest.raises(df.FetchSchemaError, match="changed during immutable copy"):
        df._persist_immutable_annual_pdf(tmp_path, 2022, source)

    assert not list((tmp_path / "versions").glob("*.pdf"))


@pytest.mark.parametrize(
    "sidecar",
    [
        {
            "adjunct_url": "original.pdf",
            "sha256": hashlib.sha256(b"%PDF-revised").hexdigest(),
        },
        {
            "adjunct_url": "revised.pdf",
            "sha256": hashlib.sha256(b"%PDF-original").hexdigest(),
        },
    ],
)
def test_annual_manifest_rejects_selected_pdf_source_mismatch(tmp_path, sidecar):
    selected_pdf = tmp_path / "年报-2022.pdf"
    selected_pdf.write_bytes(b"%PDF-revised")
    selected_pdf.with_suffix(".pdf.source.json").write_text(
        json.dumps(sidecar),
        encoding="utf-8",
    )
    revised = df.Announcement(
        title="某公司2022年年度报告（修订版）",  # noqa: RUF001
        adjunct_url="revised.pdf",
        announcement_date=date(2023, 4, 2),
        announcement_time=datetime(2023, 4, 2, tzinfo=UTC),
        year=2022,
        announcement_id="101",
        status="selected",
    )

    with pytest.raises(df.FetchSchemaError, match="source metadata"):
        df.write_annual_manifest(
            tmp_path,
            "000001.SZ",
            date(2023, 4, 30),
            [revised],
            {2022: selected_pdf},
            {
                "query_params": [{"stock": "000001,org"}],
                "official_total": 1,
            },
        )


def test_immutable_pdf_copy_does_not_overwrite_concurrent_destination(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "年报-2022.pdf"
    source.write_bytes(b"%PDF-selected")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "versions" / f"年报-2022-{digest}.pdf"
    original_exists = Path.exists
    race_injected = False

    def exists_with_race(path):
        nonlocal race_injected
        if path == destination and not race_injected:
            race_injected = True
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"%PDF-competing")
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists_with_race)

    with pytest.raises(df.FetchSchemaError, match=r"already exists|concurrent"):
        df._persist_immutable_annual_pdf(tmp_path, 2022, source)

    assert destination.read_bytes() == b"%PDF-competing"


def test_hk_manifest_rejects_mismatched_query_issuer_identity(tmp_path):
    with pytest.raises(df.FetchSchemaError, match="query issuer"):
        df.write_annual_manifest(
            tmp_path,
            "0700.HK",
            date(2023, 4, 30),
            [],
            {},
            {
                "query_issuer_code": "00001",
                "resolved_stock_id": "WRONG",
                "query_params": [{"stockId": "WRONG"}],
            },
        )


def test_a_share_query_reply_cannot_replace_full_annual_report():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/full.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "100",
                },
                {
                    "announcementTitle": "关于某公司2022年年度报告问询函回复的公告",
                    "adjunctUrl": "finalpage/reply.PDF",
                    "announcementTime": 1680278400000,
                    "announcementId": "101",
                },
            ]
        }
    ).encode()
    catalog = []

    results = df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        3,
        raw_response=payload,
        catalog_out=catalog,
    )

    assert [result.announcement_id for result in results] == ["100"]
    assert catalog[1].status == "excluded"


def test_hk_query_reply_cannot_replace_full_annual_report():
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/full.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "100",
            },
            {
                "TITLE": "RESPONSE TO QUERIES IN RELATION TO ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/reply.pdf",
                "DATE_TIME": "01/04/2023 18:00",
                "NEWS_ID": "101",
            },
        ]
    ).encode()
    catalog = []

    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        stock_id="7609",
        raw_response=payload,
        catalog_out=catalog,
    )

    assert [result.announcement_id for result in results] == ["100"]
    assert catalog[1].status == "excluded"


@pytest.mark.parametrize(
    "reply_title",
    (
        "RESPONSE TO ENQUIRIES IN RELATION TO ANNUAL REPORT 2022",
        "REPLY TO ENQUIRIES IN RELATION TO ANNUAL REPORT 2022",
    ),
)
def test_hk_enquiries_reply_cannot_replace_full_annual_report(reply_title):
    payload = json.dumps(
        [
            {
                "TITLE": "ANNUAL REPORT 2022",
                "FILE_LINK": "/listedco/full.pdf",
                "DATE_TIME": "31/03/2023 18:00",
                "NEWS_ID": "100",
            },
            {
                "TITLE": reply_title,
                "FILE_LINK": "/listedco/reply.pdf",
                "DATE_TIME": "01/04/2023 18:00",
                "NEWS_ID": "101",
            },
        ]
    ).encode()
    catalog = []

    results = df.search_hkex_annual_reports(
        "0700",
        years=3,
        stock_id="7609",
        raw_response=payload,
        catalog_out=catalog,
    )

    assert [result.announcement_id for result in results] == ["100"]
    assert catalog[1].status == "excluded"


def test_manifest_does_not_label_unrelated_announcement_as_annual_report(tmp_path):
    unrelated = df.Announcement(
        title="关于某公司2022年年度报告问询函回复的公告",
        adjunct_url="https://static.cninfo.com.cn/reply.pdf",
        announcement_date=date(2023, 4, 1),
        announcement_time=datetime(2023, 4, 1, tzinfo=UTC),
        year=2022,
        announcement_id="101",
        status="excluded",
    )

    path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2023, 4, 30),
        [unrelated],
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 1,
        },
    )

    assert json.loads(path.read_text())["candidates"][0]["report_type"] == ("excluded_announcement")


def test_cninfo_urls_are_https_and_candidates_are_absolute():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "finalpage/full.PDF",
                    "announcementTime": 1680192000000,
                    "announcementId": "100",
                }
            ]
        }
    ).encode()

    results = df.search_annual_reports("org", "000001", "SZ", 3, raw_response=payload)

    assert df.STOCK_LIST_URL.startswith("https://")
    assert df.ANNOUNCEMENT_QUERY_URL.startswith("https://")
    assert df.PDF_BASE_URL.startswith("https://")
    assert results[0].adjunct_url == "https://static.cninfo.com.cn/finalpage/full.PDF"


def test_cn_manifest_rejects_mismatched_query_issuer_identity(tmp_path):
    with pytest.raises(df.FetchSchemaError, match="query issuer"):
        df.write_annual_manifest(
            tmp_path,
            "000001.SZ",
            date(2023, 4, 30),
            [],
            {},
            {
                "query_params": [{"stock": "600000,org"}],
                "official_total": 0,
            },
        )


@pytest.mark.parametrize("alias", ["700.HK", "0700.HK", "00700.HK"])
def test_hk_ticker_aliases_normalize_to_one_canonical_identity(alias):
    assert df.canonical_ticker(alias) == "00700.HK"


def test_same_as_of_manifest_rebuild_publishes_content_addressed_evidence(tmp_path):
    as_of = date(2023, 4, 30)
    first = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        as_of,
        [],
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "response_sha256": "first",
            "official_total": 0,
        },
    )
    original = first.read_bytes()

    second = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        as_of,
        [],
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "response_sha256": "second",
            "official_total": 0,
        },
    )

    assert first.read_bytes() == original
    assert second != first
    assert second.name.startswith("annual-reports-2023-04-30-")
    assert second.is_file()


def test_annual_manifest_does_not_overwrite_concurrently_created_evidence(
    tmp_path,
    monkeypatch,
):
    as_of = date(2023, 4, 30)
    output = tmp_path / "manifests" / "annual-reports-2023-04-30.json"
    original_exists = Path.exists
    race_injected = False

    def exists_with_race(path):
        nonlocal race_injected
        if path == output and not race_injected:
            race_injected = True
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("competing evidence", encoding="utf-8")
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists_with_race)

    published = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        as_of,
        [],
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "response_sha256": "new",
            "official_total": 0,
        },
    )

    assert output.read_text(encoding="utf-8") == "competing evidence"
    assert published != output
    assert published.is_file()


def _build_authenticated_hk_annual_manifest(
    tmp_path,
    hkex_activestock_bytes,
):
    catalog_body = json.dumps(
        {
            "result": json.dumps(
                [
                    {
                        "NEWS_ID": "1",
                        "TITLE": "Annual Report 2025",
                        "FILE_LINK": "/listedco/report.pdf",
                        "DATE_TIME": "31/03/2026 09:00",
                    }
                ]
            ),
            "total": 1,
        }
    ).encode()
    catalog = []
    trace = {}
    selected = df.search_hkex_annual_reports(
        "00700",
        years=1,
        as_of=date(2026, 4, 30),
        raw_response=catalog_body,
        raw_stocklist=hkex_activestock_bytes,
        catalog_out=catalog,
        trace_out=trace,
        period_end_resolver=lambda _announcement: date(2025, 12, 31),
    )
    selected_pdf = tmp_path / "annual.pdf"
    _write_selected_pdf(
        selected_pdf,
        b"%PDF-1.4\n" + b"A" * (df.MIN_VALID_PDF_BYTES + 1),
        selected[0].adjunct_url,
    )

    manifest_path = df.write_annual_manifest(
        tmp_path,
        "00700.HK",
        date(2026, 4, 30),
        catalog,
        {2025: selected_pdf},
        trace,
    )
    return manifest_path, catalog_body, selected_pdf.read_bytes()


def _complete_hkex_query(stock_id, from_date, to_date):
    return {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": stock_id,
        "documentType": "-1",
        "fromDate": from_date,
        "toDate": to_date,
        "title": "",
        "t1code": "-2",
        "t2Gcode": "-2",
        "t2code": "-2",
        "rowRange": "100",
        "lang": "EN",
    }


def _complete_cninfo_query(
    *,
    stock="000001,org",
    column="szse",
    page_number="1",
    date_window="2024-04-30~2026-04-30",
):
    return {
        "stock": stock,
        "tabName": "fulltext",
        "pageSize": "30",
        "pageNum": page_number,
        "column": column,
        "category": "",
        "seDate": date_window,
    }


def _write_hkex_stock_id_evidence(tmp_path, issuer_code, stock_id):
    body = json.dumps(
        [
            {
                "i": int(stock_id),
                "c": issuer_code,
                "n": "AUTHENTICATED ISSUER",
                "s": 1,
            }
        ],
        separators=(",", ":"),
    ).encode()
    response_path = tmp_path / "hkex-active-stock.json"
    response_path.write_bytes(body)
    return (
        {
            "source_url": df.HKEX_ACTIVE_STOCK_URL,
            "response_path": str(response_path.resolve()),
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "mapping": {
                "issuer_code": issuer_code,
                "stock_id": stock_id,
            },
        },
        body,
    )


def _build_cn_annual_manifest(
    tmp_path,
    *,
    official_total=1,
):
    catalog_body = json.dumps(
        {
            "totalAnnouncement": official_total,
            "announcements": [
                {
                    "announcementId": "100",
                    "announcementTitle": "某公司2025年年度报告",
                    "announcementTime": int(
                        datetime(2026, 3, 30, 1, 0, tzinfo=UTC).timestamp() * 1000
                    ),
                    "adjunctUrl": "original.pdf",
                }
            ],
        },
        ensure_ascii=False,
    ).encode()
    catalog = []
    trace = {}
    selected = df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        1,
        as_of=date(2026, 4, 30),
        raw_response=catalog_body,
        catalog_out=catalog,
        trace_out=trace,
    )
    selected_pdf = tmp_path / "cn-annual.pdf"
    _write_selected_pdf(
        selected_pdf,
        b"%PDF-cn-live",
        selected[0].adjunct_url,
    )
    manifest_path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2026, 4, 30),
        catalog,
        {2025: selected_pdf},
        trace,
    )
    return manifest_path, catalog_body, selected_pdf.read_bytes()


@pytest.mark.parametrize(
    ("filter_name", "bad_value"),
    [
        ("tabName", "relation"),
        ("tabName", None),
        ("pageSize", "100"),
        ("category", "category_ndbg_szsh"),
        ("searchkey", "年度报告"),
        ("column", "sse"),
        ("stock", "600000,other"),
        ("seDate", "2024-04-29~2026-04-30"),
    ],
)
def test_cn_revalidation_rejects_tampered_catalog_filters(
    tmp_path,
    filter_name,
    bad_value,
):
    manifest_path, catalog_body, pdf_body = _build_cn_annual_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    query = manifest["official_query_params"][0]
    if bad_value is None:
        query.pop(filter_name)
    else:
        query[filter_name] = bad_value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    catalog_fetches = []

    with pytest.raises(
        df.FetchSchemaError,
        match=r"query contract|query window",
    ):
        df.revalidate_annual_manifest(
            manifest_path,
            catalog_fetcher=lambda *_args: catalog_fetches.append(_args) or catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )

    assert not catalog_fetches


def test_cn_revalidation_accepts_explicitly_empty_search_key(tmp_path):
    manifest_path, catalog_body, pdf_body = _build_cn_annual_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["official_query_params"][0]["searchkey"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    digest = df.revalidate_annual_manifest(
        manifest_path,
        catalog_fetcher=lambda *_args: catalog_body,
        pdf_fetcher=lambda _url: pdf_body,
    )

    assert digest == hashlib.sha256(manifest_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "page_numbers",
    [
        ["2"],
        ["2", "1"],
        ["1", "1"],
        ["1", "2"],
    ],
)
def test_cn_revalidation_rejects_missing_misordered_or_extra_pages(
    tmp_path,
    page_numbers,
):
    manifest_path, catalog_body, pdf_body = _build_cn_annual_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root_query = manifest["official_query_params"][0]
    manifest["official_query_params"] = [
        {**root_query, "pageNum": page_number} for page_number in page_numbers
    ]
    manifest["response_sha256"] = hashlib.sha256(catalog_body * len(page_numbers)).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(df.FetchSchemaError, match=r"pagination|page sequence"):
        df.revalidate_annual_manifest(
            manifest_path,
            catalog_fetcher=lambda *_args: catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )


def test_cn_revalidation_rejects_inconsistent_official_total_across_pages(
    tmp_path,
):
    manifest_path, first_page, pdf_body = _build_cn_annual_manifest(
        tmp_path,
        official_total=2,
    )
    second_page = b'{"totalAnnouncement":1,"announcements":[]}'
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root_query = manifest["official_query_params"][0]
    manifest["official_query_params"].append({**root_query, "pageNum": "2"})
    manifest["response_sha256"] = hashlib.sha256(first_page + second_page).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    pages = {
        "1": first_page,
        "2": second_page,
    }

    with pytest.raises(df.FetchSchemaError, match="official total changed"):
        df.revalidate_annual_manifest(
            manifest_path,
            catalog_fetcher=lambda _url, _exchange, query: pages[query["pageNum"]],
            pdf_fetcher=lambda _url: pdf_body,
        )


@pytest.mark.parametrize(
    ("omitted_kind", "omitted_title"),
    [
        ("correction", "某公司2025年年度报告(更正后)"),
        ("cancellation", "某公司2025年年度报告取消公告"),
    ],
)
def test_cn_revalidation_rejects_omitted_correction_or_cancellation_page(
    tmp_path,
    omitted_kind,
    omitted_title,
):
    manifest_path, first_page, pdf_body = _build_cn_annual_manifest(
        tmp_path,
        official_total=2,
    )
    omitted_page = json.dumps(
        {
            "totalAnnouncement": 2,
            "announcements": [
                {
                    "announcementId": "101",
                    "announcementTitle": omitted_title,
                    "announcementTime": int(
                        datetime(2026, 3, 31, 1, 0, tzinfo=UTC).timestamp() * 1000
                    ),
                    "adjunctUrl": f"{omitted_kind}.pdf",
                    "targetAnnouncementId": "100",
                }
            ],
        },
        ensure_ascii=False,
    ).encode()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["official_result_total"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    official_pages = {
        "1": first_page,
        "2": omitted_page,
    }

    with pytest.raises(
        df.FetchSchemaError,
        match=r"pagination|official total|completeness",
    ):
        df.revalidate_annual_manifest(
            manifest_path,
            catalog_fetcher=lambda _url, _exchange, query: official_pages[query["pageNum"]],
            pdf_fetcher=lambda _url: pdf_body,
        )


def test_hk_annual_manifest_persists_authenticated_stock_id_evidence(
    tmp_path,
    hkex_activestock_bytes,
):
    manifest_path, _, _ = _build_authenticated_hk_annual_manifest(
        tmp_path,
        hkex_activestock_bytes,
    )
    evidence = json.loads(manifest_path.read_text(encoding="utf-8"))["hkex_stock_id_evidence"]
    response_path = Path(evidence["response_path"])

    assert evidence["source_url"] == df.HKEX_ACTIVE_STOCK_URL
    assert response_path.is_absolute()
    assert response_path.read_bytes() == hkex_activestock_bytes
    assert evidence["response_sha256"] == hashlib.sha256(hkex_activestock_bytes).hexdigest()
    assert evidence["mapping"] == {
        "issuer_code": "00700",
        "stock_id": "7609",
    }


def test_hk_annual_manifest_revalidation_authenticates_official_stock_id_mapping(
    tmp_path,
    hkex_activestock_bytes,
    monkeypatch,
):
    manifest_path, catalog_body, pdf_body = _build_authenticated_hk_annual_manifest(
        tmp_path,
        hkex_activestock_bytes,
    )
    calls = []
    outputs = iter(
        [
            b"Annual Report\nFor the year ended 31 December 2025",
            (b"Consolidated financial statements\nFor the year ended 31 December 2025"),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=next(outputs),
            stderr=b"",
        ),
    )

    digest = df.revalidate_annual_manifest(
        manifest_path,
        stocklist_fetcher=lambda url: calls.append(("stocklist", url)) or hkex_activestock_bytes,
        catalog_fetcher=lambda url, exchange, params: (
            calls.append(("catalog", url, exchange, params)) or catalog_body
        ),
        pdf_fetcher=lambda _url: pdf_body,
    )

    assert digest == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert calls[0] == ("stocklist", df.HKEX_ACTIVE_STOCK_URL)
    assert calls[1][0] == "catalog"


def test_hk_revalidation_rejects_self_consistent_wrong_stock_id(
    tmp_path,
    hkex_activestock_bytes,
):
    manifest_path, catalog_body, pdf_body = _build_authenticated_hk_annual_manifest(
        tmp_path,
        hkex_activestock_bytes,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["resolved_stock_id"] = "9999"
    manifest["hkex_stock_id_evidence"]["mapping"]["stock_id"] = "9999"
    for query in manifest["official_query_params"]:
        query["stockId"] = "9999"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    catalog_fetches = []

    with pytest.raises(df.FetchSchemaError, match="stockId mapping"):
        df.revalidate_annual_manifest(
            manifest_path,
            stocklist_fetcher=lambda _url: hkex_activestock_bytes,
            catalog_fetcher=lambda *_args: catalog_fetches.append(_args) or catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )

    assert not catalog_fetches


@pytest.mark.parametrize("mutation", ["immutable_evidence", "live_mapping"])
def test_hk_revalidation_rejects_mutated_stocklist_evidence_or_live_mapping(
    tmp_path,
    hkex_activestock_bytes,
    mutation,
):
    manifest_path, catalog_body, pdf_body = _build_authenticated_hk_annual_manifest(
        tmp_path,
        hkex_activestock_bytes,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    live_stocklist = hkex_activestock_bytes
    if mutation == "immutable_evidence":
        Path(manifest["hkex_stock_id_evidence"]["response_path"]).write_bytes(
            b'[{"i":9999,"c":"00700","n":"TENCENT","s":15355}]'
        )
    else:
        live_stocklist = b'[{"i":9999,"c":"00700","n":"TENCENT","s":15355}]'
    catalog_fetches = []

    with pytest.raises(df.FetchSchemaError, match="stockId evidence"):
        df.revalidate_annual_manifest(
            manifest_path,
            stocklist_fetcher=lambda _url: live_stocklist,
            catalog_fetcher=lambda *_args: catalog_fetches.append(_args) or catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )

    assert not catalog_fetches


def test_hk_revalidation_accepts_unrelated_live_stocklist_drift(
    tmp_path,
    hkex_activestock_bytes,
    monkeypatch,
):
    manifest_path, catalog_body, pdf_body = _build_authenticated_hk_annual_manifest(
        tmp_path,
        hkex_activestock_bytes,
    )
    live_rows = json.loads(hkex_activestock_bytes)
    live_rows.reverse()
    live_rows.append(
        {
            "i": 9999,
            "c": "09999",
            "n": "NEW UNRELATED ISSUER",
            "s": 19999,
        }
    )
    live_stocklist = json.dumps(live_rows, separators=(",", ":")).encode()
    outputs = iter(
        [
            b"Annual Report\nFor the year ended 31 December 2025",
            (b"Consolidated financial statements\nFor the year ended 31 December 2025"),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=next(outputs),
            stderr=b"",
        ),
    )

    digest = df.revalidate_annual_manifest(
        manifest_path,
        stocklist_fetcher=lambda _url: live_stocklist,
        catalog_fetcher=lambda *_args: catalog_body,
        pdf_fetcher=lambda _url: pdf_body,
    )

    assert digest == hashlib.sha256(manifest_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "live_mutation",
    ["target_mapping_drift", "duplicate_target", "malformed_row"],
)
def test_hk_revalidation_rejects_live_stocklist_mapping_or_schema_errors(
    tmp_path,
    hkex_activestock_bytes,
    live_mutation,
):
    manifest_path, catalog_body, pdf_body = _build_authenticated_hk_annual_manifest(
        tmp_path,
        hkex_activestock_bytes,
    )
    live_rows = json.loads(hkex_activestock_bytes)
    if live_mutation == "target_mapping_drift":
        target = next(row for row in live_rows if row["c"] == "00700")
        target["i"] = 9999
    elif live_mutation == "duplicate_target":
        live_rows.append(
            {
                "i": 7609,
                "c": "00700",
                "n": "DUPLICATE TENCENT",
                "s": 15355,
            }
        )
    else:
        live_rows.append(
            {
                "i": 9999,
                "c": "MALFORMED",
                "n": "INVALID CODE",
                "s": 19999,
            }
        )
    live_stocklist = json.dumps(live_rows, separators=(",", ":")).encode()
    catalog_fetches = []

    with pytest.raises(
        df.FetchSchemaError,
        match=r"stockId evidence (?:mapping|schema)|stockId mapping",
    ):
        df.revalidate_annual_manifest(
            manifest_path,
            stocklist_fetcher=lambda _url: live_stocklist,
            catalog_fetcher=lambda *_args: catalog_fetches.append(_args) or catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )

    assert not catalog_fetches


@pytest.mark.parametrize(
    ("filter_name", "bad_value"),
    [
        ("market", "GEM"),
        ("category", "1"),
        ("documentType", "1"),
        ("sortByOptions", "Headline"),
        ("sortDir", "1"),
        ("lang", "FR"),
        ("rowRange", "50"),
        ("title", "Annual Report"),
        ("t1code", "40000"),
        ("t2Gcode", "40100"),
        ("t2code", "40100"),
        ("fromDate", "20240429"),
        ("toDate", "20260429"),
        ("category", None),
    ],
)
def test_hk_revalidation_rejects_altered_catalog_completeness_filters(
    tmp_path,
    hkex_activestock_bytes,
    filter_name,
    bad_value,
):
    manifest_path, catalog_body, pdf_body = _build_authenticated_hk_annual_manifest(
        tmp_path,
        hkex_activestock_bytes,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for query in manifest["official_query_params"]:
        if bad_value is None:
            query.pop(filter_name)
        else:
            query[filter_name] = bad_value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    catalog_fetches = []

    with pytest.raises(
        df.FetchSchemaError,
        match=r"query contract|query window",
    ):
        df.revalidate_annual_manifest(
            manifest_path,
            stocklist_fetcher=lambda _url: hkex_activestock_bytes,
            catalog_fetcher=lambda *_args: catalog_fetches.append(_args) or catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )

    assert not catalog_fetches


def test_hk_revalidation_rejects_altered_catalog_pagination_tree(
    tmp_path,
    hkex_activestock_bytes,
):
    manifest_path, catalog_body, pdf_body = _build_authenticated_hk_annual_manifest(
        tmp_path,
        hkex_activestock_bytes,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    extra_window = dict(manifest["official_query_params"][0])
    extra_window["toDate"] = "20250430"
    manifest["official_query_params"].append(extra_window)
    manifest["response_sha256"] = hashlib.sha256(catalog_body + catalog_body).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(df.FetchSchemaError, match="query tree"):
        df.revalidate_annual_manifest(
            manifest_path,
            stocklist_fetcher=lambda _url: hkex_activestock_bytes,
            catalog_fetcher=lambda *_args: catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )


def test_annual_manifest_live_revalidation_checks_catalog_and_selected_pdf(
    tmp_path,
):
    catalog_body = json.dumps(
        {
            "announcements": [
                {
                    "announcementId": "1",
                    "announcementTitle": "2025年年度报告",
                    "announcementTime": int(
                        datetime(
                            2026,
                            3,
                            31,
                            1,
                            0,
                            tzinfo=UTC,
                        ).timestamp()
                        * 1000
                    ),
                    "adjunctUrl": "report.pdf",
                }
            ],
            "totalAnnouncement": 1,
        }
    ).encode()
    pdf_body = b"%PDF-live"
    pdf_path = tmp_path / "annual.pdf"
    pdf_path.write_bytes(pdf_body)
    manifest_path = tmp_path / "annual-reports-2026-04-30.json"
    manifest_path.write_text(
        json.dumps(
            {
                "ticker": "000001.SZ",
                "exchange": "SZ",
                "AS_OF": "2026-04-30",
                "查询发行人代码": "000001",
                "resolved_org_id": "org",
                "official_query_url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                "official_query_params": [_complete_cninfo_query()],
                "response_sha256": hashlib.sha256(catalog_body).hexdigest(),
                "official_result_total": 1,
                "selection_years": 1,
                "target_end_year": None,
                "candidate_count": 1,
                "candidates": [
                    {
                        "fiscal_year": 2025,
                        "report_period_end": "2025-12-31",
                        "announcement_time": "2026-03-31T01:00:00+00:00",
                        "announcement_id": "1",
                        "sequence_id": 0,
                        "title": "2025年年度报告",
                        "report_type": "annual_report",
                        "status": "selected",
                        "replacement_of": None,
                        "replacement_targets": {},
                        "affected_fiscal_years": [2025],
                        "selected": True,
                        "official_url": "https://static.cninfo.com.cn/report.pdf",
                        "absolute_path": str(pdf_path.resolve()),
                        "file_sha256": hashlib.sha256(pdf_body).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    digest = df.revalidate_annual_manifest(
        manifest_path,
        catalog_fetcher=lambda _url, _exchange, _params: catalog_body,
        pdf_fetcher=lambda _url: pdf_body,
    )

    assert digest == hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def test_annual_manifest_revalidation_rejects_tampered_catalog_metadata(
    tmp_path,
):
    catalog_body = json.dumps(
        {
            "announcements": [
                {
                    "announcementId": "1",
                    "announcementTitle": "2025年年度报告",
                    "announcementTime": int(
                        datetime(
                            2026,
                            3,
                            31,
                            1,
                            0,
                            tzinfo=UTC,
                        ).timestamp()
                        * 1000
                    ),
                    "adjunctUrl": "report.pdf",
                }
            ],
            "totalAnnouncement": 1,
        }
    ).encode()
    pdf_body = b"%PDF-live"
    pdf_path = tmp_path / "annual.pdf"
    pdf_path.write_bytes(pdf_body)
    manifest_path = tmp_path / "annual-reports-2026-04-30.json"
    manifest_path.write_text(
        json.dumps(
            {
                "ticker": "000001.SZ",
                "exchange": "SZ",
                "AS_OF": "2026-04-30",
                "查询发行人代码": "000001",
                "resolved_org_id": "org",
                "official_query_url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                "official_query_params": [_complete_cninfo_query()],
                "response_sha256": hashlib.sha256(catalog_body).hexdigest(),
                "official_result_total": 1,
                "selection_years": 1,
                "target_end_year": None,
                "candidate_count": 1,
                "candidates": [
                    {
                        "fiscal_year": 2025,
                        "report_period_end": "2025-12-31",
                        "announcement_time": "2026-03-31T01:00:00+00:00",
                        "announcement_id": "1",
                        "sequence_id": 0,
                        "title": "被篡改的年度报告标题",
                        "report_type": "annual_report",
                        "status": "selected",
                        "replacement_of": None,
                        "replacement_targets": {},
                        "affected_fiscal_years": [2025],
                        "selected": True,
                        "official_url": "https://static.cninfo.com.cn/report.pdf",
                        "absolute_path": str(pdf_path.resolve()),
                        "file_sha256": hashlib.sha256(pdf_body).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        df.FetchSchemaError,
        match="catalog metadata",
    ):
        df.revalidate_annual_manifest(
            manifest_path,
            catalog_fetcher=lambda _url, _exchange, _params: catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )


@pytest.mark.parametrize(
    "tampered_field",
    [
        "sequence_id",
        "report_type",
        "status",
        "replacement_of",
        "replacement_targets",
        "selected",
    ],
)
def test_annual_manifest_revalidation_rejects_tampered_derived_state(
    tmp_path,
    tampered_field,
):
    catalog_body = json.dumps(
        {
            "announcements": [
                {
                    "announcementId": "100",
                    "announcementTitle": "某公司2025年年度报告",
                    "announcementTime": int(
                        datetime(2026, 3, 30, 1, 0, tzinfo=UTC).timestamp() * 1000
                    ),
                    "adjunctUrl": "original.pdf",
                },
                {
                    "announcementId": "101",
                    "announcementTitle": "某公司2025年年度报告(更正后)",
                    "announcementTime": int(
                        datetime(2026, 3, 31, 1, 0, tzinfo=UTC).timestamp() * 1000
                    ),
                    "adjunctUrl": "corrected.pdf",
                },
            ],
            "totalAnnouncement": 2,
        },
        ensure_ascii=False,
    ).encode()
    catalog = []
    trace = {}
    selected = df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        1,
        as_of=date(2026, 4, 30),
        raw_response=catalog_body,
        catalog_out=catalog,
        trace_out=trace,
    )
    pdf_body = b"%PDF-live"
    pdf_path = tmp_path / "annual.pdf"
    _write_selected_pdf(pdf_path, pdf_body, selected[0].adjunct_url)
    manifest_path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2026, 4, 30),
        catalog,
        {2025: pdf_path},
        trace,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original = next(row for row in manifest["candidates"] if row["announcement_id"] == "100")
    corrected = next(row for row in manifest["candidates"] if row["announcement_id"] == "101")
    if tampered_field == "sequence_id":
        corrected["sequence_id"] = 99
    elif tampered_field == "report_type":
        original["report_type"] = "correction_notice"
    elif tampered_field == "status":
        original["status"] = "excluded"
    elif tampered_field == "replacement_of":
        corrected["replacement_of"] = "999"
    elif tampered_field == "replacement_targets":
        corrected["replacement_targets"] = {"2025": "999"}
    else:
        original["selected"] = True
        original["status"] = "selected"
        original["absolute_path"] = corrected["absolute_path"]
        original["file_sha256"] = corrected["file_sha256"]
        corrected["selected"] = False
        corrected["status"] = "superseded"
        corrected["absolute_path"] = None
        corrected["file_sha256"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    live_fetches = []

    with pytest.raises(df.FetchSchemaError, match="state"):
        df.revalidate_annual_manifest(
            manifest_path,
            catalog_fetcher=lambda url, exchange, params: (
                live_fetches.append((url, exchange, params)) or catalog_body
            ),
            pdf_fetcher=lambda _url: pdf_body,
        )
    assert live_fetches


def test_hk_live_revalidation_resolves_yearless_title_from_official_pdf(
    tmp_path,
    monkeypatch,
):
    catalog_body = json.dumps(
        {
            "result": json.dumps(
                [
                    {
                        "NEWS_ID": "1",
                        "TITLE": "Annual Report",
                        "FILE_LINK": "/listedco/report.pdf",
                        "DATE_TIME": "31/03/2026 09:00",
                    }
                ]
            ),
            "total": 1,
        }
    ).encode()
    pdf_body = b"%PDF-1.4\n" + b"A" * (df.MIN_VALID_PDF_BYTES + 1)
    pdf_path = tmp_path / "annual.pdf"
    pdf_path.write_bytes(pdf_body)
    query = _complete_hkex_query(
        "1234",
        "20240430",
        "20260430",
    )
    stock_id_evidence, stocklist_body = _write_hkex_stock_id_evidence(
        tmp_path,
        "01398",
        "1234",
    )
    manifest_path = tmp_path / "annual-reports-2026-04-30.json"
    manifest_path.write_text(
        json.dumps(
            {
                "ticker": "01398.HK",
                "exchange": "HK",
                "AS_OF": "2026-04-30",
                "查询发行人代码": "01398",
                "query_issuer_code": "01398",
                "resolved_stock_id": "1234",
                "hkex_stock_id_evidence": stock_id_evidence,
                "official_query_url": df.HKEX_SEARCH_URL,
                "official_query_params": [query],
                "response_sha256": hashlib.sha256(catalog_body).hexdigest(),
                "official_result_total": 1,
                "selection_years": 1,
                "target_end_year": None,
                "candidate_count": 1,
                "candidates": [
                    {
                        "fiscal_year": 2025,
                        "report_period_end": "2025-12-31",
                        "announcement_time": "2026-03-31T01:00:00+00:00",
                        "announcement_id": "1",
                        "sequence_id": 0,
                        "title": "Annual Report",
                        "report_type": "annual_report",
                        "status": "selected",
                        "replacement_of": None,
                        "replacement_targets": {},
                        "affected_fiscal_years": [2025],
                        "official_url": ("https://www1.hkexnews.hk/listedco/report.pdf"),
                        "selected": True,
                        "absolute_path": str(pdf_path.resolve()),
                        "file_sha256": hashlib.sha256(pdf_body).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    outputs = iter(
        [
            b"Annual Report\nFor the year ended 31 December 2025",
            (b"Consolidated financial statements\nFor the year ended 31 December 2025"),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    digest = df.revalidate_annual_manifest(
        manifest_path,
        stocklist_fetcher=lambda _url: stocklist_body,
        catalog_fetcher=lambda _url, _exchange, _params: catalog_body,
        pdf_fetcher=lambda _url: pdf_body,
    )

    assert digest == hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def test_hk_live_revalidation_compares_pdf_derived_report_period_end(
    tmp_path,
    monkeypatch,
):
    catalog_body = json.dumps(
        {
            "result": json.dumps(
                [
                    {
                        "NEWS_ID": "1",
                        "TITLE": "Annual Report 2025",
                        "FILE_LINK": "/listedco/report.pdf",
                        "DATE_TIME": "31/03/2026 09:00",
                    }
                ]
            ),
            "total": 1,
        }
    ).encode()
    pdf_body = b"%PDF-1.4\n" + b"A" * (df.MIN_VALID_PDF_BYTES + 1)
    pdf_path = tmp_path / "annual.pdf"
    pdf_path.write_bytes(pdf_body)
    query = _complete_hkex_query(
        "1234",
        "20240430",
        "20260430",
    )
    stock_id_evidence, stocklist_body = _write_hkex_stock_id_evidence(
        tmp_path,
        "01398",
        "1234",
    )
    manifest_path = tmp_path / "annual-reports-2026-04-30.json"
    manifest_path.write_text(
        json.dumps(
            {
                "ticker": "01398.HK",
                "exchange": "HK",
                "AS_OF": "2026-04-30",
                "查询发行人代码": "01398",
                "query_issuer_code": "01398",
                "resolved_stock_id": "1234",
                "hkex_stock_id_evidence": stock_id_evidence,
                "official_query_url": df.HKEX_SEARCH_URL,
                "official_query_params": [query],
                "response_sha256": hashlib.sha256(catalog_body).hexdigest(),
                "official_result_total": 1,
                "selection_years": 1,
                "target_end_year": None,
                "candidate_count": 1,
                "candidates": [
                    {
                        "fiscal_year": 2025,
                        "report_period_end": "2025-11-30",
                        "announcement_time": "2026-03-31T01:00:00+00:00",
                        "announcement_id": "1",
                        "sequence_id": 0,
                        "title": "Annual Report 2025",
                        "report_type": "annual_report",
                        "status": "selected",
                        "replacement_of": None,
                        "replacement_targets": {},
                        "affected_fiscal_years": [2025],
                        "official_url": ("https://www1.hkexnews.hk/listedco/report.pdf"),
                        "selected": True,
                        "absolute_path": str(pdf_path.resolve()),
                        "file_sha256": hashlib.sha256(pdf_body).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    outputs = iter(
        [
            b"Annual Report\nFor the year ended 31 December 2025",
            (b"Consolidated financial statements\nFor the year ended 31 December 2025"),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    with pytest.raises(df.FetchSchemaError, match="catalog metadata"):
        df.revalidate_annual_manifest(
            manifest_path,
            stocklist_fetcher=lambda _url: stocklist_body,
            catalog_fetcher=lambda _url, _exchange, _params: catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )


@pytest.mark.parametrize(
    ("exchange", "bad_contract"),
    [
        ("SZ", "url"),
        ("SZ", "issuer"),
        ("SZ", "org"),
        ("HK", "url"),
        ("HK", "issuer"),
    ],
)
def test_live_revalidation_rejects_unbound_query_contract(
    tmp_path,
    exchange,
    bad_contract,
):
    pdf_body = b"%PDF-live"
    pdf_path = tmp_path / "annual.pdf"
    pdf_path.write_bytes(pdf_body)
    if exchange == "HK":
        ticker = "01398.HK"
        ticker_code = "01398"
        query_url = df.HKEX_SEARCH_URL
        query = _complete_hkex_query(
            "1234",
            "20240430",
            "20260430",
        )
        catalog_body = json.dumps(
            {
                "result": json.dumps(
                    [
                        {
                            "NEWS_ID": "1",
                            "TITLE": "Annual Report 2025",
                            "FILE_LINK": "/listedco/report.pdf",
                            "DATE_TIME": "31/03/2026 09:00",
                            "REPORT_PERIOD_END": "2025-12-31",
                        }
                    ]
                ),
                "total": 1,
            }
        ).encode()
        official_url = "https://www1.hkexnews.hk/listedco/report.pdf"
        announcement_time = "2026-03-31T01:00:00+00:00"
        extra_identity = {
            "query_issuer_code": ticker_code,
            "resolved_stock_id": "9999" if bad_contract == "issuer" else "1234",
        }
    else:
        ticker = "000001.SZ"
        ticker_code = "000001"
        query_url = df.ANNOUNCEMENT_QUERY_URL
        query = _complete_cninfo_query(
            stock=(
                "600000,org"
                if bad_contract == "issuer"
                else ("000001,other" if bad_contract == "org" else "000001,org")
            )
        )
        catalog_body = json.dumps(
            {
                "announcements": [
                    {
                        "announcementId": "1",
                        "announcementTitle": "2025年年度报告",
                        "announcementTime": int(
                            datetime(2026, 3, 31, 1, 0, tzinfo=UTC).timestamp() * 1000
                        ),
                        "adjunctUrl": "report.pdf",
                    }
                ],
                "totalAnnouncement": 1,
            }
        ).encode()
        official_url = "https://static.cninfo.com.cn/report.pdf"
        announcement_time = "2026-03-31T01:00:00+00:00"
        extra_identity = {"resolved_org_id": "org"}
    if bad_contract == "url":
        query_url = "https://example.com/official-query"
    manifest_path = tmp_path / "annual-reports-2026-04-30.json"
    manifest_path.write_text(
        json.dumps(
            {
                "ticker": ticker,
                "exchange": exchange,
                "AS_OF": "2026-04-30",
                "查询发行人代码": ticker_code,
                **extra_identity,
                "official_query_url": query_url,
                "official_query_params": [query],
                "response_sha256": hashlib.sha256(catalog_body).hexdigest(),
                "official_result_total": 1,
                "selection_years": 1,
                "target_end_year": None,
                "candidate_count": 1,
                "candidates": [
                    {
                        "fiscal_year": 2025,
                        "report_period_end": "2025-12-31",
                        "announcement_time": announcement_time,
                        "announcement_id": "1",
                        "sequence_id": 0,
                        "title": ("Annual Report 2025" if exchange == "HK" else "2025年年度报告"),
                        "report_type": "annual_report",
                        "status": "selected",
                        "replacement_of": None,
                        "replacement_targets": {},
                        "affected_fiscal_years": [2025],
                        "official_url": official_url,
                        "selected": True,
                        "absolute_path": str(pdf_path.resolve()),
                        "file_sha256": hashlib.sha256(pdf_body).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(df.FetchSchemaError, match="query contract"):
        df.revalidate_annual_manifest(
            manifest_path,
            catalog_fetcher=lambda _url, _exchange, _params: catalog_body,
            pdf_fetcher=lambda _url: pdf_body,
        )


def test_annual_manifest_revalidation_rejects_empty_candidate_set(tmp_path):
    catalog_body = b'{"official":"catalog"}'
    manifest_path = tmp_path / "annual-reports-2026-04-30.json"
    manifest_path.write_text(
        json.dumps(
            {
                "ticker": "000001.SZ",
                "exchange": "SZ",
                "AS_OF": "2026-04-30",
                "查询发行人代码": "000001",
                "resolved_org_id": "org",
                "official_query_url": ("https://www.cninfo.com.cn/new/hisAnnouncement/query"),
                "official_query_params": [_complete_cninfo_query()],
                "response_sha256": hashlib.sha256(catalog_body).hexdigest(),
                "official_result_total": 1,
                "selection_years": 1,
                "target_end_year": None,
                "candidate_count": 0,
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(df.FetchSchemaError, match="candidate"):
        df.revalidate_annual_manifest(
            manifest_path,
            catalog_fetcher=lambda _url, _exchange, _params: catalog_body,
            pdf_fetcher=lambda _url: b"",
        )


def test_cli_supports_annual_manifest_live_revalidation(
    tmp_path,
    monkeypatch,
    capsys,
):
    manifest_path = tmp_path / "annual.json"
    manifest_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        df,
        "revalidate_annual_manifest",
        lambda path: "a" * 64 if path == manifest_path else "",
    )

    result = df.main(["--revalidate", str(manifest_path)])

    assert result == 0
    assert capsys.readouterr().out.strip() == "a" * 64


def test_promote_annual_manifest_rejects_empty_candidate_evidence(tmp_path):
    temporary = tmp_path / "preflight" / "annual-reports.json"
    canonical = tmp_path / "manifests" / "annual-reports-2026-04-30.json"
    temporary.parent.mkdir()
    first_body = json.dumps(
        {
            "ticker": "000001.SZ",
            "exchange": "SZ",
            "AS_OF": "2026-04-30",
            "查询发行人代码": "000001",
            "candidates": [],
        }
    ).encode()
    temporary.write_bytes(first_body)

    with pytest.raises(df.FetchSchemaError, match="candidate"):
        df.promote_annual_manifest(temporary, canonical)


def _promotion_candidate(
    *,
    fiscal_year,
    announcement_id,
    sequence_id,
    title,
    official_url,
    announcement_time,
    status,
    selected_path=None,
    report_type="annual_report",
    report_period_end=None,
    explicit_target_id=None,
    replacement_of=None,
    replacement_targets=None,
):
    file_sha256 = (
        hashlib.sha256(selected_path.read_bytes()).hexdigest()
        if selected_path is not None
        else None
    )
    return {
        "fiscal_year": fiscal_year,
        "report_period_end": (
            report_period_end if report_period_end is not None else f"{fiscal_year}-12-31"
        ),
        "announcement_time": announcement_time,
        "announcement_id": announcement_id,
        "sequence_id": sequence_id,
        "title": title,
        "report_type": report_type,
        "status": status,
        "explicit_target_id": explicit_target_id,
        "replacement_of": replacement_of,
        "replacement_targets": replacement_targets or {},
        "affected_fiscal_years": [fiscal_year],
        "official_url": official_url,
        "selected": selected_path is not None,
        "absolute_path": (str(selected_path.resolve()) if selected_path is not None else None),
        "file_sha256": file_sha256,
    }


def _write_promotion_manifest(tmp_path, candidates):
    temporary = tmp_path / "preflight" / "annual-reports.json"
    canonical = tmp_path / "manifests" / "annual-reports-2026-04-30.json"
    temporary.parent.mkdir(exist_ok=True)
    temporary.write_text(
        json.dumps(
            {
                "ticker": "000001.SZ",
                "exchange": "SZ",
                "AS_OF": "2026-04-30",
                "查询发行人代码": "000001",
                "selection_years": 1,
                "target_end_year": None,
                "candidate_count": len(candidates),
                "candidates": candidates,
            }
        ),
        encoding="utf-8",
    )
    return temporary, canonical


@pytest.mark.parametrize(
    "scenario",
    ["older_selection", "superseded_correction", "cancelled_selection"],
)
def test_promote_annual_manifest_reconstructs_candidate_state(
    tmp_path,
    scenario,
):
    selected_path = tmp_path / f"{scenario}.pdf"
    selected_body = b"%PDF-1.4\n" + b"A" * (df.MIN_VALID_PDF_BYTES + 1)
    if scenario == "older_selection":
        _write_selected_pdf(
            selected_path,
            selected_body,
            "https://static.cninfo.com.cn/2024.pdf",
        )
        candidates = [
            _promotion_candidate(
                fiscal_year=2024,
                announcement_id="100",
                sequence_id=0,
                title="某公司2024年年度报告",
                official_url="https://static.cninfo.com.cn/2024.pdf",
                announcement_time="2025-03-30T01:00:00+00:00",
                status="selected",
                selected_path=selected_path,
            ),
            _promotion_candidate(
                fiscal_year=2025,
                announcement_id="200",
                sequence_id=1,
                title="某公司2025年年度报告",
                official_url="https://static.cninfo.com.cn/2025.pdf",
                announcement_time="2026-03-30T01:00:00+00:00",
                status="outside_window",
            ),
        ]
    elif scenario == "superseded_correction":
        _write_selected_pdf(
            selected_path,
            selected_body,
            "https://static.cninfo.com.cn/original.pdf",
        )
        candidates = [
            _promotion_candidate(
                fiscal_year=2025,
                announcement_id="100",
                sequence_id=0,
                title="某公司2025年年度报告",
                official_url="https://static.cninfo.com.cn/original.pdf",
                announcement_time="2026-03-30T01:00:00+00:00",
                status="selected",
                selected_path=selected_path,
            ),
            _promotion_candidate(
                fiscal_year=2025,
                announcement_id="101",
                sequence_id=1,
                title="某公司2025年年度报告(更正后)",
                official_url="https://static.cninfo.com.cn/corrected.pdf",
                announcement_time="2026-03-31T01:00:00+00:00",
                status="superseded",
                replacement_of="100",
                replacement_targets={"2025": "100"},
            ),
        ]
    else:
        _write_selected_pdf(
            selected_path,
            selected_body,
            "https://static.cninfo.com.cn/original.pdf",
        )
        candidates = [
            _promotion_candidate(
                fiscal_year=2025,
                announcement_id="100",
                sequence_id=0,
                title="某公司2025年年度报告",
                official_url="https://static.cninfo.com.cn/original.pdf",
                announcement_time="2026-03-30T01:00:00+00:00",
                status="selected",
                selected_path=selected_path,
            ),
            _promotion_candidate(
                fiscal_year=2025,
                announcement_id="101",
                sequence_id=1,
                title="某公司2025年年度报告取消公告",
                official_url="https://static.cninfo.com.cn/cancel.pdf",
                announcement_time="2026-03-31T01:00:00+00:00",
                status="cancellation",
                report_type="cancellation_notice",
                report_period_end="不适用",
                explicit_target_id="100",
                replacement_of="100",
                replacement_targets={"2025": "100"},
            ),
        ]
    temporary, canonical = _write_promotion_manifest(tmp_path, candidates)

    with pytest.raises(df.FetchSchemaError, match="candidate state"):
        df.promote_annual_manifest(temporary, canonical)


@pytest.mark.parametrize("evidence_problem", ["not_pdf", "missing_provenance"])
def test_promote_annual_manifest_validates_pdf_and_provenance(
    tmp_path,
    evidence_problem,
):
    pdf_path = tmp_path / "annual.pdf"
    official_url = "https://static.cninfo.com.cn/report.pdf"
    body = (
        b"not-a-pdf" + b"A" * (df.MIN_VALID_PDF_BYTES + 1)
        if evidence_problem == "not_pdf"
        else b"%PDF-1.4\n" + b"A" * (df.MIN_VALID_PDF_BYTES + 1)
    )
    if evidence_problem == "missing_provenance":
        pdf_path.write_bytes(body)
    else:
        _write_selected_pdf(pdf_path, body, official_url)
    candidate = _promotion_candidate(
        fiscal_year=2025,
        announcement_id="1",
        sequence_id=0,
        title="某公司2025年年度报告",
        official_url=official_url,
        announcement_time="2026-03-31T01:00:00+00:00",
        status="selected",
        selected_path=pdf_path,
    )
    temporary, canonical = _write_promotion_manifest(tmp_path, [candidate])

    with pytest.raises(df.FetchSchemaError, match=r"PDF|source metadata"):
        df.promote_annual_manifest(temporary, canonical)


def test_promote_annual_manifest_rejects_selected_pdf_publication_race(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "annual.pdf"
    official_url = "https://static.cninfo.com.cn/report.pdf"
    original = b"%PDF-1.4\n" + b"A" * (df.MIN_VALID_PDF_BYTES + 1)
    replacement = b"%PDF-1.4\n" + b"B" * (df.MIN_VALID_PDF_BYTES + 1)
    _write_selected_pdf(pdf_path, original, official_url)
    candidate = _promotion_candidate(
        fiscal_year=2025,
        announcement_id="1",
        sequence_id=0,
        title="某公司2025年年度报告",
        official_url=official_url,
        announcement_time="2026-03-31T01:00:00+00:00",
        status="selected",
        selected_path=pdf_path,
    )
    temporary, canonical = _write_promotion_manifest(tmp_path, [candidate])
    real_link = df.os.link
    mutated = False

    def mutate_selected_pdf_before_publication(source, destination):
        nonlocal mutated
        if Path(destination) == canonical and not mutated:
            mutated = True
            pdf_path.write_bytes(replacement)
        return real_link(source, destination)

    monkeypatch.setattr(df.os, "link", mutate_selected_pdf_before_publication)

    with pytest.raises(df.FetchSchemaError, match="changed"):
        df.promote_annual_manifest(temporary, canonical)

    assert not canonical.exists()


def test_written_annual_manifest_preserves_promotable_pdf_provenance(tmp_path):
    selected_pdf = tmp_path / "annual.pdf"
    official_url = "https://static.cninfo.com.cn/report.pdf"
    pdf_body = b"%PDF-1.4\n" + b"A" * (df.MIN_VALID_PDF_BYTES + 1)
    _write_selected_pdf(selected_pdf, pdf_body, official_url)
    announcement = df.Announcement(
        title="某公司2025年年度报告",
        adjunct_url=official_url,
        announcement_date=date(2026, 3, 31),
        announcement_time=datetime(2026, 3, 31, 1, 0, tzinfo=UTC),
        year=2025,
        announcement_id="1",
        sequence_id=0,
        status="selected",
        report_period_end="2025-12-31",
    )
    temporary = tmp_path / "preflight" / "annual-reports.json"
    canonical = tmp_path / "manifests" / "annual-reports-2026-04-30.json"
    df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2026, 4, 30),
        [announcement],
        {2025: selected_pdf},
        {
            "query_url": df.ANNOUNCEMENT_QUERY_URL,
            "query_params": [
                {
                    "stock": "000001,org",
                    "column": "szse",
                    "seDate": "2024-04-30~2026-04-30",
                }
            ],
            "resolved_org_id": "org",
            "official_total": 1,
            "selection_years": 1,
            "target_end_year": None,
        },
        manifest_out=temporary,
    )

    promoted = df.promote_annual_manifest(temporary, canonical)

    assert promoted == canonical.resolve()


@pytest.mark.parametrize(
    ("candidate_status", "selected", "missing_field"),
    [
        ("selected", True, "report_type"),
        ("superseded", True, None),
        ("cancelled", True, None),
        ("selected", False, None),
    ],
)
def test_promote_annual_manifest_rejects_invalid_candidate_selection(
    tmp_path,
    candidate_status,
    selected,
    missing_field,
):
    pdf_path = tmp_path / "annual.pdf"
    pdf_body = b"%PDF-reviewed"
    pdf_path.write_bytes(pdf_body)
    candidate = {
        "fiscal_year": 2025,
        "report_period_end": "2025-12-31",
        "announcement_time": "2026-03-31T01:00:00+00:00",
        "announcement_id": "1",
        "sequence_id": 0,
        "title": "2025年年度报告",
        "report_type": "annual_report",
        "status": candidate_status,
        "replacement_of": None,
        "replacement_targets": {},
        "affected_fiscal_years": [2025],
        "official_url": "https://static.cninfo.com.cn/report.pdf",
        "selected": selected,
        "absolute_path": str(pdf_path.resolve()) if selected else None,
        "file_sha256": hashlib.sha256(pdf_body).hexdigest() if selected else None,
    }
    if missing_field is not None:
        del candidate[missing_field]
    temporary = tmp_path / "preflight" / "annual-reports.json"
    canonical = tmp_path / "manifests" / "annual-reports-2026-04-30.json"
    temporary.parent.mkdir()
    temporary.write_text(
        json.dumps(
            {
                "ticker": "000001.SZ",
                "exchange": "SZ",
                "AS_OF": "2026-04-30",
                "查询发行人代码": "000001",
                "candidate_count": 1,
                "candidates": [candidate],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(df.FetchSchemaError, match="candidate"):
        df.promote_annual_manifest(temporary, canonical)


@pytest.mark.parametrize(
    (
        "primary_ticker",
        "primary_exchange",
        "primary_listing_date",
        "requested_ticker",
        "requested_listing_date",
    ),
    [
        ("601398.SH", "SH", "2006-10-27", "01398.HK", "2006-10-24"),
        ("01398.HK", "HK", "2006-10-24", "601398.SH", "2006-10-27"),
    ],
)
def test_listing_bundle_allows_authenticated_ah_counterpart(
    tmp_path,
    monkeypatch,
    primary_ticker,
    primary_exchange,
    primary_listing_date,
    requested_ticker,
    requested_listing_date,
):
    primary_code = primary_ticker.split(".", 1)[0]
    source_url = (
        "https://www.hkex.com.hk/listing-profile"
        if primary_exchange == "HK"
        else "https://www.sse.com.cn/listing-profile"
    )
    query_params = {"issuer_code": primary_code}
    source_payload = {
        "query": query_params,
        "issuer_code": primary_code,
        "listing_codes": {"SH": "601398", "HK": "01398"},
        "listing_date": primary_listing_date,
        "listing_dates": {"SH": "2006-10-27", "HK": "2006-10-24"},
        "listing_statuses": {"SH": "listed", "HK": "listed"},
        "delisting_dates": {"SH": None, "HK": None},
        "official_result_total": 1,
    }
    source_body = json.dumps(source_payload, separators=(",", ":")).encode()
    source = tmp_path / "listing-profile.json"
    source.write_bytes(source_body)
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "ticker": primary_ticker,
                "exchange": primary_exchange,
                "AS_OF": "2026-04-30",
                "query_issuer_code": primary_code,
                "listing_date": primary_listing_date,
                "listing_profile": {
                    "source_url": source_url,
                    "http_method": "GET",
                    "request_encoding": "query",
                    "query_params": query_params,
                    "response_schema": "canonical_listing_profile_v1",
                    "source_file": str(source.resolve()),
                },
            }
        ),
        encoding="utf-8",
    )
    requests = []

    class OfficialResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return source_url

        def read(self):
            return source_body

    def fake_urlopen(request, timeout):
        assert timeout == 30
        requests.append(request)
        return OfficialResponse()

    monkeypatch.setattr(
        df.build_event_manifest.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    result = df._load_listing_profile_bundle(
        bundle.resolve(),
        requested_ticker,
        date.fromisoformat(requested_listing_date),
    )

    assert result["source_file"] == str(source.resolve())
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("requested_ticker", "requested_listing_date"),
    [
        ("000001.SZ", "2006-10-27"),
        ("01398.HK", "2006-10-27"),
    ],
)
def test_listing_bundle_rejects_unrelated_ticker_or_listing_date(
    tmp_path,
    monkeypatch,
    requested_ticker,
    requested_listing_date,
):
    source = tmp_path / "listing-profile.json"
    source.write_text("{}", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "ticker": "601398.SH",
                "exchange": "SH",
                "AS_OF": "2026-04-30",
                "query_issuer_code": "601398",
                "listing_date": "2006-10-27",
                "listing_profile": {"source_file": str(source.resolve())},
            }
        ),
        encoding="utf-8",
    )
    validated = {
        "source_url": "https://www.sse.com.cn/profile",
        "query_params": {"issuer_code": "601398"},
        "response_schema": "canonical_listing_profile_v1",
        "response_adapter": {},
        "listing_codes": {"SH": "601398", "HK": "01398"},
        "listing_dates": {"SH": "2006-10-27", "HK": "2006-10-24"},
        "listing_statuses": {"SH": "listed", "HK": "listed"},
        "delisting_dates": {"SH": None, "HK": None},
    }
    monkeypatch.setattr(
        df.build_event_manifest,
        "_validate_listing_profile",
        lambda *_args: (validated, date(2006, 10, 27)),
    )

    with pytest.raises(df.FetchSchemaError, match="identity or listing_date"):
        df._load_listing_profile_bundle(
            bundle.resolve(),
            requested_ticker,
            date.fromisoformat(requested_listing_date),
        )


def test_listing_bundle_rejects_mismatched_primary_query_identity(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "listing-profile.json"
    source.write_text("{}", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "ticker": "601398.SH",
                "exchange": "SH",
                "AS_OF": "2026-04-30",
                "query_issuer_code": "000001",
                "listing_date": "2006-10-27",
                "listing_profile": {"source_file": str(source.resolve())},
            }
        ),
        encoding="utf-8",
    )
    validated = {
        "listing_codes": {"SH": "601398", "HK": "01398"},
        "listing_dates": {"SH": "2006-10-27", "HK": "2006-10-24"},
    }
    monkeypatch.setattr(
        df.build_event_manifest,
        "_validate_listing_profile",
        lambda *_args: (validated, date(2006, 10, 27)),
    )

    with pytest.raises(df.FetchSchemaError, match="identity"):
        df._load_listing_profile_bundle(
            bundle.resolve(),
            "601398.SH",
            date(2006, 10, 27),
        )


def test_cli_supports_annual_manifest_promotion(tmp_path, monkeypatch, capsys):
    temporary = tmp_path / "temporary.json"
    canonical = tmp_path / "annual-reports-2026-04-30.json"
    temporary.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        df,
        "promote_annual_manifest",
        lambda source, target: (
            target.resolve() if source == temporary and target == canonical else Path()
        ),
    )

    result = df.main(
        [
            "--promote",
            str(temporary),
            "--canonical-out",
            str(canonical),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out.strip() == str(canonical.resolve())


def test_hk_period_parser_ignores_forecast_dates(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                b"Consolidated financial statements for the year ended "
                b"31 December 2024\n"
                b"Forecast assumptions for the period ended 31 December 2025"
            ),
            stderr=b"",
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2024, 12, 31)


def test_hk_period_parser_requires_cover_and_audited_statement_to_agree(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            b"Annual Report for the year ended 31 December 2024",
            (
                b"Annual Report for the year ended 31 December 2024\n"
                b"Consolidated financial statements for the year ended "
                b"31 December 2023"
            ),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    with pytest.raises(df.FetchSchemaError, match="cover and audited statement"):
        df.extract_hk_report_period_end(pdf_path)


def test_hk_period_parser_accepts_month_day_with_comma(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            b"Annual Report for the year ended March 31, 2024",
            b"Consolidated financial statements for the year ended March 31, 2024",
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2024, 3, 31)


def test_hk_period_parser_accepts_date_below_authoritative_heading(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            b"Annual Report for the year ended 31 March 2024",
            (b"Consolidated financial statements\nfor the year ended 31 March 2024"),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2024, 3, 31)


def test_hk_period_parser_allows_comparative_date_on_cover(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            (
                b"Annual Report for the year ended March 31, 2024\n"
                b"Five-year summary for the year ended March 31, 2023"
            ),
            b"Consolidated financial statements for the year ended March 31, 2024",
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2024, 3, 31)


def test_hk_period_parser_accepts_split_balance_sheet_header(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            b"Our fiscal year ended March 31, 2024",
            (b"Consolidated Balance Sheets\n\nAs of March 31,\n2023  2024\n"),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2024, 3, 31)


def test_hk_period_parser_uses_latest_year_from_multi_year_heading(tmp_path, monkeypatch):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            b"Fiscal Year 2023 Annual Report",
            (
                b"Notes to Consolidated Financial Statements\n"
                b"For the Years Ended March 31, 2021, 2022 and 2023"
            ),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2023, 3, 31)


@pytest.mark.parametrize("cover_text", [b"ANNUAL REPORT 2025", b"2025 ANNUAL REPORT"])
def test_hk_period_parser_accepts_annual_report_year_on_cover(tmp_path, monkeypatch, cover_text):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    outputs = iter(
        [
            cover_text,
            (b"Consolidated financial statements\nfor the year ended 31 December 2025"),
        ]
    )
    monkeypatch.setattr(
        df.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=next(outputs), stderr=b""
        ),
    )

    assert df.extract_hk_report_period_end(pdf_path) == date(2025, 12, 31)


def test_annual_manifest_declares_listing_history_scope(tmp_path):
    path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2023, 4, 30),
        [],
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 0,
        },
    )
    manifest = json.loads(path.read_text())

    assert "listing_date" in manifest
    assert manifest["listing_history_complete"] is False


def test_cli_accepts_manifest_out_before_ticker_validation(tmp_path):
    assert (
        df.main(
            [
                "invalid",
                "--manifest-out",
                str(tmp_path / "preflight-manifest.json"),
            ]
        )
        == 2
    )


def test_annual_manifest_can_write_to_temporary_path(tmp_path):
    manifest_out = tmp_path / "preflight" / "annual-reports.json"

    path = df.write_annual_manifest(
        tmp_path / "filings",
        "000001.SZ",
        date(2023, 4, 30),
        [],
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 0,
        },
        manifest_out=manifest_out,
    )

    assert path == manifest_out
    assert manifest_out.is_file()
    assert not (tmp_path / "filings" / "manifests").exists()


def test_download_pdf_refetches_same_url_and_replaces_changed_official_bytes(tmp_path):
    dest = tmp_path / "年报-2024.pdf"
    original = b"%PDF-1.4\n" + b"A" * (200 * 1024)
    changed = b"%PDF-1.4\n" + b"B" * (200 * 1024)
    _write_selected_pdf(dest, original, "finalpage/report.PDF")

    with mock.patch.object(df, "_http_get", return_value=changed) as get:
        did_download = df.download_pdf("finalpage/report.PDF", dest)

    assert did_download is True
    assert dest.read_bytes() == changed
    get.assert_called_once()


def test_annual_manifest_revalidates_source_metadata_after_copy_starts(
    tmp_path,
    monkeypatch,
):
    selected_pdf = tmp_path / "年报-2022.pdf"
    original = b"%PDF-original"
    revised = b"%PDF-revised"
    _write_selected_pdf(selected_pdf, original, "original.pdf")
    announcement = df.Announcement(
        title="某公司2022年年度报告",
        adjunct_url="original.pdf",
        announcement_date=date(2023, 3, 30),
        announcement_time=datetime(2023, 3, 30, tzinfo=UTC),
        year=2022,
        announcement_id="100",
        status="selected",
    )
    real_persist = df._persist_immutable_annual_pdf

    def replace_before_copy(out_dir, fiscal_year, source, *args, **kwargs):
        source.write_bytes(revised)
        return real_persist(out_dir, fiscal_year, source, *args, **kwargs)

    monkeypatch.setattr(df, "_persist_immutable_annual_pdf", replace_before_copy)

    with pytest.raises(df.FetchSchemaError, match="source metadata"):
        df.write_annual_manifest(
            tmp_path,
            "000001.SZ",
            date(2023, 4, 30),
            [announcement],
            {2022: selected_pdf},
            {
                "query_params": [{"stock": "000001,org"}],
                "official_total": 1,
            },
        )


def test_annual_manifest_rejects_pdf_and_sidecar_changed_before_immutable_link(
    tmp_path,
    monkeypatch,
):
    selected_pdf = tmp_path / "年报-2022.pdf"
    _write_selected_pdf(selected_pdf, b"%PDF-original", "original.pdf")
    announcement = df.Announcement(
        title="某公司2022年年度报告",
        adjunct_url="original.pdf",
        announcement_date=date(2023, 3, 30),
        announcement_time=datetime(2023, 3, 30, tzinfo=UTC),
        year=2022,
        announcement_id="100",
        status="selected",
    )
    manifest_path = tmp_path / "manifests" / "annual-reports-2023-04-30.json"
    real_link = df.os.link
    injected = False

    def link_after_source_changes(source_path, target_path):
        nonlocal injected
        if Path(target_path).suffix == ".pdf" and not injected:
            injected = True
            _write_selected_pdf(selected_pdf, b"%PDF-concurrent", "original.pdf")
        return real_link(source_path, target_path)

    monkeypatch.setattr(df.os, "link", link_after_source_changes)

    with pytest.raises(df.FetchSchemaError):
        df.write_annual_manifest(
            tmp_path,
            "000001.SZ",
            date(2023, 4, 30),
            [announcement],
            {2022: selected_pdf},
            {
                "query_params": [{"stock": "000001,org"}],
                "official_total": 1,
            },
        )

    assert not manifest_path.exists()


def test_after_target_unrelated_reply_is_classified_before_year_filter(tmp_path):
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "关于某公司2023年年度报告问询函回复的公告",
                    "adjunctUrl": "reply.pdf",
                    "announcementTime": 1711756800000,
                    "announcementId": "100",
                }
            ]
        }
    ).encode()
    catalog = []

    assert (
        df.search_annual_reports(
            "org",
            "000001",
            "SZ",
            3,
            end_year=2022,
            raw_response=payload,
            catalog_out=catalog,
        )
        == []
    )
    path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2024, 4, 30),
        catalog,
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 1,
        },
    )

    assert json.loads(path.read_text())["candidates"][0]["report_type"] == ("excluded_announcement")


def test_accounting_error_restatement_notice_requires_replacement_full_report():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": "某公司2022年年度报告",
                    "adjunctUrl": "2022-original.pdf",
                    "announcementTime": 1680192000000,
                    "announcementId": "100",
                },
                {
                    "announcementTitle": ("某公司关于2022年度前期会计差错更正及追溯调整的公告"),
                    "adjunctUrl": "2022-restatement.pdf",
                    "announcementTime": 1680278400000,
                    "announcementId": "101",
                },
            ]
        }
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="correction notice"):
        df.search_annual_reports(
            "org",
            "000001",
            "SZ",
            3,
            raw_response=payload,
        )


def test_multi_year_restatement_notice_applies_to_each_affected_fiscal_year():
    records = []
    for year, announcement_id in ((2021, 100), (2022, 200), (2023, 300)):
        records.append(
            {
                "announcementTitle": f"某公司{year}年年度报告",
                "adjunctUrl": f"{year}-original.pdf",
                "announcementTime": 1680192000000 + (year - 2021) * 1000,
                "announcementId": str(announcement_id),
            }
        )
    records.append(
        {
            "announcementTitle": ("关于2021年、2022年及2023年度前期会计差错更正及追溯调整的公告"),
            "adjunctUrl": "multi-year-restatement.pdf",
            "announcementTime": 1680278400000,
            "announcementId": "400",
        }
    )
    for year, announcement_id in ((2021, 500), (2022, 600), (2023, 700)):
        records.append(
            {
                "announcementTitle": f"某公司{year}年年度报告（更正后）",
                "adjunctUrl": f"{year}-corrected.pdf",
                "announcementTime": 1680364800000 + (year - 2021) * 1000,
                "announcementId": str(announcement_id),
            }
        )
    payload = json.dumps({"announcements": records}).encode("utf-8")

    results = df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        3,
        raw_response=payload,
    )

    assert {result.year: result.announcement_id for result in results} == {
        2021: "500",
        2022: "600",
        2023: "700",
    }


def test_year_limit_marks_older_independent_reports_outside_window():
    payload = json.dumps(
        {
            "announcements": [
                {
                    "announcementTitle": f"某公司{year}年年度报告",
                    "adjunctUrl": f"{year}.pdf",
                    "announcementTime": int(
                        datetime(year + 1, 3, 30, tzinfo=UTC).timestamp() * 1000
                    ),
                    "announcementId": str(year),
                }
                for year in (2020, 2021, 2022)
            ]
        }
    ).encode()
    catalog = []

    results = df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        2,
        raw_response=payload,
        catalog_out=catalog,
    )

    assert [result.year for result in results] == [2022, 2021]
    assert next(row for row in catalog if row.year == 2020).status == "outside_window"


def test_search_trace_persists_official_listing_scope():
    trace = {}

    df.search_annual_reports(
        "org",
        "000001",
        "SZ",
        10,
        as_of=date(2024, 4, 30),
        listing_date=date(2020, 1, 1),
        raw_response=b'{"announcements": []}',
        trace_out=trace,
    )

    assert trace["listing_date"] == "2020-01-01"
    assert trace["listing_history_complete"] is True


def test_cli_requires_official_listing_bundle_with_listing_date(tmp_path, capsys):
    result = df.main(
        [
            "000001.SZ",
            "--listing-date",
            "2020-01-01",
            "--out",
            str(tmp_path),
        ]
    )

    assert result == 2
    assert "--listing-profile-bundle" in capsys.readouterr().out


def test_annual_manifest_binds_official_listing_profile_evidence(tmp_path):
    source_file = tmp_path / "listing-profile.json"
    source_file.write_text('{"official":"response"}', encoding="utf-8")
    path = df.write_annual_manifest(
        tmp_path,
        "000001.SZ",
        date(2023, 4, 30),
        [],
        {},
        {
            "query_params": [{"stock": "000001,org"}],
            "official_total": 0,
            "listing_date": "2020-01-01",
            "listing_profile": {
                "bundle_path": str((tmp_path / "bundle.json").resolve()),
                "bundle_sha256": "a" * 64,
                "source_file": str(source_file.resolve()),
                "source_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
                "source_url": "https://www.szse.cn/listing-profile",
                "query_params": {"stock": "000001"},
            },
        },
    )

    manifest = json.loads(path.read_text())
    assert manifest["listing_profile"]["source_file"] == str(source_file.resolve())
    assert (
        manifest["listing_profile"]["source_sha256"]
        == hashlib.sha256(source_file.read_bytes()).hexdigest()
    )


def test_hkex_rejects_mismatched_official_result_total():
    response = json.dumps(
        {
            "total": 2,
            "result": json.dumps(
                [
                    {
                        "TITLE": "Annual Report 2023",
                        "FILE_LINK": "/listedco/listconews/sehk/2024/0101/report.pdf",
                        "DATE_TIME": "01/01/2024 09:00",
                        "REPORT_PERIOD_END": "2023-12-31",
                    }
                ]
            ),
        }
    ).encode()

    with pytest.raises(df.FetchSchemaError, match="official total"):
        df.search_hkex_annual_reports(
            "0700",
            years=5,
            stock_id="7609",
            raw_response=response,
        )


def test_cli_rejects_backfill_when_explicit_target_year_is_missing(tmp_path, monkeypatch):
    older = df.Announcement(
        title="某公司2021年年度报告",
        adjunct_url="https://static.cninfo.com.cn/2021.pdf",
        announcement_date=date(2022, 3, 31),
        announcement_time=datetime(2022, 3, 31, tzinfo=UTC),
        year=2021,
        announcement_id="100",
        status="selected",
    )

    monkeypatch.setattr(df, "resolve_org_id", lambda _code: "org")

    def fake_search(*_args, catalog_out, **_kwargs):
        catalog_out.append(older)
        return [older]

    monkeypatch.setattr(df, "search_annual_reports", fake_search)
    download = mock.Mock()
    monkeypatch.setattr(df, "download_pdf", download)

    result = df.main(
        [
            "000001.SZ",
            "--end-year",
            "2022",
            "--out",
            str(tmp_path),
        ]
    )

    assert result == 2
    download.assert_not_called()


def test_hk_manifest_rejects_query_code_that_lost_leading_zero(tmp_path):
    with pytest.raises(df.FetchSchemaError, match="query issuer"):
        df.write_annual_manifest(
            tmp_path,
            "01398.HK",
            date(2023, 4, 30),
            [],
            {},
            {
                "query_issuer_code": "1398",
                "resolved_stock_id": "1234",
                "query_params": [{"stockId": "1234"}],
            },
        )


def test_listing_bundle_rejects_unauthenticated_source_payload(tmp_path):
    source = tmp_path / "listing-profile.json"
    source.write_text('{"fake":true}', encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "ticker": "000001.SZ",
                "exchange": "SZ",
                "AS_OF": "2026-04-30",
                "query_issuer_code": "000001",
                "listing_date": "2020-01-01",
                "listing_profile": {
                    "source_url": "https://www.szse.cn/listing-profile",
                    "http_method": "GET",
                    "request_encoding": "query",
                    "query_params": {"issuer_code": "000001"},
                    "response_schema": "canonical_listing_profile_v1",
                    "source_file": str(source.resolve()),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(df.FetchSchemaError, match="official listing profile"):
        df._load_listing_profile_bundle(
            bundle.resolve(),
            "000001.SZ",
            date(2020, 1, 1),
        )


def test_listing_bundle_replays_persisted_request_and_rejects_byte_drift(
    tmp_path,
    monkeypatch,
):
    source_url = "https://www.szse.cn/listing-profile"
    query_params = {"issuer_code": "000001", "locale": "zh_CN"}
    source_payload = {
        "query": query_params,
        "issuer_code": "000001",
        "listing_codes": {"SZ": "000001"},
        "listing_date": "2020-01-01",
        "listing_dates": {"SZ": "2020-01-01"},
        "listing_status": "listed",
        "delisting_date": None,
        "official_result_total": 1,
    }
    source_body = json.dumps(source_payload, separators=(",", ":")).encode()
    live_body = json.dumps(source_payload, indent=2).encode()
    source = tmp_path / "listing-profile.json"
    source.write_bytes(source_body)
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "ticker": "000001.SZ",
                "exchange": "SZ",
                "AS_OF": "2026-04-30",
                "query_issuer_code": "000001",
                "listing_date": "2020-01-01",
                "listing_profile": {
                    "source_url": source_url,
                    "http_method": "POST",
                    "request_encoding": "json",
                    "request_headers": {
                        "Accept": "application/json",
                        "X-Contract": "persisted",
                    },
                    "query_params": query_params,
                    "response_schema": "canonical_listing_profile_v1",
                    "source_file": str(source.resolve()),
                },
            }
        ),
        encoding="utf-8",
    )
    requests = []

    class OfficialResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return source_url

        def read(self):
            return live_body

    def fake_urlopen(request, timeout):
        assert timeout == 30
        requests.append(request)
        return OfficialResponse()

    monkeypatch.setattr(
        df.build_event_manifest.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    with pytest.raises(df.FetchSchemaError, match="byte hash differs"):
        df._load_listing_profile_bundle(
            bundle.resolve(),
            "000001.SZ",
            date(2020, 1, 1),
        )

    assert len(requests) == 1
    request = requests[0]
    assert request.get_method() == "POST"
    assert request.full_url == source_url
    assert request.data == json.dumps(query_params).encode()
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("X-contract") == "persisted"
