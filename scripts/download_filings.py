"""Fetch 年报 + 招股说明书 PDFs for A-share (cninfo) and HK (HKEX) tickers.

Usage:
    # A-share — cninfo 巨潮资讯网
    python scripts/download_filings.py 600519.SH --years 5 --include-prospectus
    python scripts/download_filings.py 000001.SZ --years 10 --out data/filings/000001.SZ

    # HK — HKEX 披露易 (defaults to English version, override with --lang zh)
    python scripts/download_filings.py 0700.HK --years 5
    python scripts/download_filings.py 0700.HK --years 5 --lang zh

Dependencies: stdlib only + tenacity (see pyproject.toml).

Contract: see docs/superpowers/specs/2026-04-28-value-profile-skill-design.md §3
"Filings fetcher".
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from scripts import build_event_manifest
except ModuleNotFoundError:  # Direct execution via `python scripts/...`.
    import build_event_manifest  # type: ignore[no-redef]

_download_locks: dict[Path, threading.Lock] = {}
_download_locks_guard = threading.Lock()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOCK_LIST_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"
ANNOUNCEMENT_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE_URL = "https://static.cninfo.com.cn/"

# HKEX (香港联交所披露易) — public title search, same backend the
# https://www1.hkexnews.hk/search/titlesearch.xhtml browser UI uses.
# - GET (POST returns 411 / 405); params are URL-encoded
# - Response shape: {"result": "<json-encoded string>"} — note `result`
#   is a JSON string that must be double-parsed, not a list
# - `stockId` is HKEX's *internal* identifier (e.g. Tencent = 7609), NOT
#   the 5-digit stock code. Resolve via the active-stock JSON below.
# - Each record is one filing for ONE language; pass lang=EN or lang=ZH
#   to pick the variant — the API does not return both in one response.
# - t1code=40000 / t2code=40100 narrows to Annual Report
HKEX_SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
HKEX_BASE_URL = "https://www1.hkexnews.hk"
HKEX_ACTIVE_STOCK_URL = "https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_e.json"
HKEX_T1_FINANCIAL = "40000"  # Financial Statements/ESG Information
HKEX_T2_ANNUAL_REPORT = "40100"  # Annual Report

USER_AGENT = (
    "Mozilla/5.0 (compatible; ah-research/0.1; +https://github.com/brian-huang/ah-research-vp)"
)

MIN_VALID_PDF_BYTES = 100 * 1024  # 100 KB
RATE_LIMIT_SECONDS = 1.0
REQUEST_TIMEOUT = 30

# Query the issuer's complete catalog, then classify annual-report records by
# title. cninfo's annual-report category can omit correction notices.
CATEGORY_ANNUAL = ""

# Title filters: corrected/revised full reports remain eligible and can replace
# the original by announcement date. Exclude only non-canonical document types.
_RE_EXCLUDE_TITLE = re.compile(r"摘要|英文版|英文稿|取消|已取消|补充公告|年度报告(?:的)?更正公告")
_RE_ANNUAL_TITLE = re.compile(r"(\d{4})\s*年\s*年度?\s*报告")
_RE_ANNUAL_FULL_TITLE = re.compile(
    r"^\s*.*?(\d{4})\s*年\s*年度?\s*报告"
    r"(?:\s*全文)?"
    r"(?:\s*[（(](?:更正后|更正版|修订版|更新后)[）)])?\s*$"
)
_RE_PROSPECTUS_TITLE = re.compile(r"^招股说明书(?:\uff08(?:修订稿|更新稿|更正版)\uff09)?$")
_RE_CORRECTED_FULL = re.compile(r"更正后|更正版|修订版|更新后")
_RE_CORRECTION_NOTICE = re.compile(r"年度报告.*更正公告")
_RE_ACCOUNTING_RESTATEMENT_NOTICE = re.compile(
    r"前期会计差错更正|会计差错更正|追溯调整|财务报表重述|重述公告"
)
_RE_GENERIC_FISCAL_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*年")
_RE_CANCELLATION = re.compile(r"取消|已取消")
_RE_ANNUAL_CONTEXT = re.compile(r"年度?\s*报告")

# HKEX title filters. t2code=40100 already narrows to annual reports, but
# defensively reject common look-alikes (summary / interim / supplement).
_RE_EXCLUDE_TITLE_HK = re.compile(
    r"summary|interim|quarterly|supplement|circular|announcement|notice|"
    r"cancellation|cancelled|canceled|"
    r"response\s+to\s+(?:the\s+)?(?:quer(?:y|ies)|enquir(?:y|ies))|"
    r"reply\s+to\s+(?:the\s+)?(?:quer(?:y|ies)|enquir(?:y|ies))|"
    r"(?:quer(?:y|ies)|enquir(?:y|ies))\s+in\s+relation|"
    r"摘要|中期|季度|补充|通函|通知|公告|取消|已取消|问询|查询回复",
    re.IGNORECASE,
)
# Plain 4-digit year fallback for HK titles ("Annual Report 2023",
# "2023年年報"). Uses digit-lookaround (not \b) since Python's \b treats
# CJK characters as word chars — `\b2023\b` fails on "2023年".
_RE_YEAR_4DIGIT = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
_RE_HK_FISCAL_YEAR_RANGE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*/\s*(\d{2})(?!\d)")
_RE_HK_CANCELLATION = re.compile(r"cancellation|cancelled|canceled|取消|已取消", re.IGNORECASE)
_RE_HK_CORRECTION_NOTICE = re.compile(
    r"(?:correction|clarification).*annual report|"
    r"annual report.*(?:correction|clarification)|"
    r"(?:年度[报報]告|年[报報]).*更正公告|"
    r"更正公告.*(?:年度[报報]告|年[报報])",
    re.IGNORECASE,
)
_RE_HK_REVISED_FULL = re.compile(
    r"revised|corrected|restated|修[订訂]版|更正后|更正版",
    re.IGNORECASE,
)
_RE_HK_FULL_REPORT = re.compile(r"annual report|年度[报報]告|年[报報]", re.IGNORECASE)
_HK_TIMEZONE = ZoneInfo("Asia/Hong_Kong")
_CN_TIMEZONE = ZoneInfo("Asia/Shanghai")
_RE_HK_PERIOD_END_EN = re.compile(
    r"(?:year|period)\s+ended\s+(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+((?:19|20)\d{2})",
    re.IGNORECASE,
)
_RE_HK_PERIOD_END_EN_MDY = re.compile(
    r"(?:year|period)\s+ended\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),?\s+((?:19|20)\d{2})",
    re.IGNORECASE,
)
_RE_HK_MULTI_YEAR_END_EN = re.compile(
    r"(?:for\s+the\s+)?years\s+ended\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),?\s+"
    r"((?:19|20)\d{2}"
    r"(?:\s*,\s*(?:and\s+)?|\s+(?:and|&)\s+)(?:19|20)\d{2}"
    r"(?:(?:\s*,\s*(?:and\s+)?|\s+(?:and|&)\s+)(?:19|20)\d{2})*)\s*$",
    re.IGNORECASE,
)
_RE_HK_COVER_FISCAL_YEAR = re.compile(
    r"fiscal\s+year\s+((?:19|20)\d{2})\s+annual\s+report",
    re.IGNORECASE,
)
_RE_HK_PERIOD_END_ZH = re.compile(r"截至\s*((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_RE_HK_SPLIT_PERIOD_END_EN = re.compile(
    r"(?:as\s+of|years?\s+ended)\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),?\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FetchSchemaError(Exception):
    """Raised when a cninfo API response does not match the expected shape."""


class FetchPartialFailure(Exception):
    """Raised at the end of a run when one or more downloads failed."""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class Announcement:
    title: str
    adjunct_url: str
    announcement_date: date
    announcement_time: datetime
    year: int | None  # fiscal year end (from title like "2024年年度报告")
    announcement_id: str = ""
    sequence_id: int = 0
    status: str = "eligible"
    replacement_of: str | None = None
    replacement_targets: dict[int, str | None] = field(default_factory=dict)
    affected_years: tuple[int, ...] = ()
    explicit_target_id: str | None = None
    report_period_end: str | None = None


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Global per-process rate limiter. Enforces >= `min_interval` seconds
    between successive calls to `wait()`."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._last_call = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delta = now - self._last_call
        if delta < self._min_interval:
            time.sleep(self._min_interval - delta)
        self._last_call = time.monotonic()


_rate_limiter = _RateLimiter(RATE_LIMIT_SECONDS)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Retry on 429, 5xx, and generic URLError (network transient)."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    return isinstance(exc, urllib.error.URLError)


_retry_policy = retry(
    reraise=True,
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((urllib.error.HTTPError, urllib.error.URLError)),
)


@_retry_policy
def _http_get(url: str) -> bytes:
    _rate_limiter.wait()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        exc = _maybe_retryable(resp)
        if exc is not None:
            raise exc
        return resp.read()


@_retry_policy
def _http_post_form(
    url: str, form: dict[str, str], *, extra_headers: dict[str, str] | None = None
) -> bytes:
    _rate_limiter.wait()
    body = urllib.parse.urlencode(form).encode("utf-8")
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        exc = _maybe_retryable(resp)
        if exc is not None:
            raise exc
        return resp.read()


def _maybe_retryable(resp: object) -> urllib.error.HTTPError | None:
    """Convert 429 / 5xx to HTTPError so tenacity retries.

    urllib raises HTTPError automatically for non-2xx when using the default
    opener, so this is belt-and-suspenders. Returned, not raised, so callers
    can bail from inside the `with` block cleanly.
    """
    status = getattr(resp, "status", 200)
    if status == 429 or (500 <= status < 600):
        return urllib.error.HTTPError(
            getattr(resp, "url", ""),
            status,
            f"status {status}",
            {},  # type: ignore[arg-type]
            None,
        )
    return None


# ---------------------------------------------------------------------------
# Ticker parsing / orgId lookup
# ---------------------------------------------------------------------------


def parse_ticker(ticker: str) -> tuple[str, str]:
    """Split `<code>.<exchange>` into (code, exchange).

    Exchange is normalised upper-case. SH / SZ require 6-digit codes; HK
    allows 1-5 digit codes (HKEX stock IDs are zero-padded to 5 when used
    with the titleSearchServlet.do endpoint)."""
    m = re.fullmatch(r"(\d{1,6})\.(SH|SZ|HK|sh|sz|hk)", ticker.strip())
    if not m:
        raise ValueError(
            f"Bad ticker {ticker!r}: expected <code>.<SH|SZ|HK>, e.g. 600519.SH, 000001.SZ, 0700.HK"
        )
    code, exchange = m.group(1), m.group(2).upper()
    if exchange in ("SH", "SZ") and len(code) != 6:
        raise ValueError(
            f"Bad ticker {ticker!r}: {exchange} codes must be 6 digits, got {len(code)}"
        )
    if exchange == "HK" and not 1 <= len(code) <= 5:
        raise ValueError(f"Bad ticker {ticker!r}: HK codes must be 1-5 digits, got {len(code)}")
    return code, exchange


def canonical_ticker(ticker: str) -> str:
    """Return one stable identity for all accepted ticker aliases."""
    code, exchange = parse_ticker(ticker)
    if exchange == "HK":
        code = code.zfill(5)
    return f"{code}.{exchange}"


def _exchange_column(exchange: str) -> str:
    """cninfo `column` parameter: `sse` for Shanghai, `szse` for Shenzhen."""
    return {"SH": "sse", "SZ": "szse"}[exchange]


def resolve_org_id(code: str, stocklist_bytes: bytes | None = None) -> str:
    """Return the cninfo `orgId` for a 6-digit A-share code.

    `stocklist_bytes` is injectable for tests; in production we fetch fresh."""
    raw = stocklist_bytes if stocklist_bytes is not None else _http_get(STOCK_LIST_URL)
    try:
        data = json.loads(raw.decode("utf-8"))
        rows = data["stockList"]
    except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
        raise FetchSchemaError(
            f"cninfo stock list: unexpected shape ({e}). First 200 bytes: {raw[:200]!r}"
        ) from e
    for row in rows:
        if row.get("code") == code:
            org_id = row.get("orgId")
            if not org_id:
                raise FetchSchemaError(
                    f"cninfo stock list: found code={code} but no orgId in row {row!r}"
                )
            return str(org_id)
    raise ValueError(f"code {code} not found in cninfo stock list ({len(rows)} entries)")


# ---------------------------------------------------------------------------
# Announcement search + filtering
# ---------------------------------------------------------------------------


def _epoch_ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _subtract_years(value: date, years: int) -> date:
    """Return `value` shifted back by whole years, clamping leap day."""
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _extract_year(title: str) -> int | None:
    m = _RE_ANNUAL_TITLE.search(title)
    if m:
        return int(m.group(1))
    return None


def _extract_restatement_years(title: str) -> tuple[int, ...]:
    return tuple(sorted({int(value) for value in _RE_GENERIC_FISCAL_YEAR.findall(title)}))


def _explicit_target_id(raw: dict) -> str | None:
    for field_name in (
        "targetAnnouncementId",
        "replacementOf",
        "replacesAnnouncementId",
    ):
        value = raw.get(field_name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _announcement_years(announcement: Announcement) -> tuple[int, ...]:
    if announcement.affected_years:
        return announcement.affected_years
    return (announcement.year,) if announcement.year is not None else ()


def _parse_announcements(raw: bytes) -> list[dict]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise FetchSchemaError(
            f"cninfo announcement query: not valid JSON ({e}). First 200 bytes: {raw[:200]!r}"
        ) from e
    anns = data.get("announcements")
    if anns is None:
        # API returns null for empty result sets. Treat as empty.
        return []
    if not isinstance(anns, list):
        raise FetchSchemaError(
            f"cninfo announcement query: 'announcements' is {type(anns).__name__}, "
            f"expected list or null"
        )
    return anns


def _parse_announcement_total(raw: bytes) -> int | None:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    total = data.get("totalAnnouncement")
    if isinstance(total, int) and total >= 0:
        return total
    return None


def _to_announcement(raw: dict, sequence_id: int = 0) -> Announcement | None:
    """Validate + convert one cninfo record. Returns None on missing fields."""
    title = raw.get("announcementTitle")
    url = raw.get("adjunctUrl")
    ts = raw.get("announcementTime")
    if not title or not url or ts is None:
        return None
    if not isinstance(ts, int):
        return None
    announcement_time = _epoch_ms_to_datetime(ts)
    title_text = str(title)
    year = _extract_year(title_text)
    affected_years: tuple[int, ...] = ()
    if year is None and _RE_ACCOUNTING_RESTATEMENT_NOTICE.search(title_text):
        affected_years = _extract_restatement_years(title_text)
        if len(affected_years) == 1:
            year = affected_years[0]
    is_correction_notice = bool(
        _RE_CORRECTION_NOTICE.search(title_text)
        or _RE_ACCOUNTING_RESTATEMENT_NOTICE.search(title_text)
    )
    return Announcement(
        title=title_text,
        adjunct_url=urllib.parse.urljoin(PDF_BASE_URL, str(url).lstrip("/")),
        announcement_date=announcement_time.astimezone(_CN_TIMEZONE).date(),
        announcement_time=announcement_time,
        year=year,
        announcement_id=str(raw.get("announcementId") or url),
        sequence_id=sequence_id,
        affected_years=affected_years,
        explicit_target_id=_explicit_target_id(raw),
        report_period_end=(
            "不适用"
            if _is_cn_annual_cancellation(str(title)) or is_correction_notice
            else (f"{year}-12-31" if year is not None else None)
        ),
    )


def _is_cn_annual_cancellation(title: str) -> bool:
    return bool(_RE_CANCELLATION.search(title) and _RE_ANNUAL_CONTEXT.search(title))


def _is_hk_annual_cancellation(title: str) -> bool:
    return bool(_RE_HK_CANCELLATION.search(title) and _RE_HK_FULL_REPORT.search(title))


def _announcement_sort_key(ann: Announcement) -> tuple[datetime, str, int, int]:
    revision_priority = (
        1 if _RE_CORRECTED_FULL.search(ann.title) or _RE_HK_REVISED_FULL.search(ann.title) else 0
    )
    official_order = (
        f"0:{int(ann.announcement_id):030d}"
        if ann.announcement_id.isdigit()
        else f"1:{ann.announcement_id}"
    )
    return (
        ann.announcement_time,
        official_order,
        revision_priority,
        ann.sequence_id,
    )


def _bind_replacement_relationships(catalog: list[Announcement]) -> None:
    previous_by_year: dict[int, str] = {}
    for ann in sorted(catalog, key=_announcement_sort_key):
        affected_years = _announcement_years(ann)
        if not affected_years:
            continue
        for fiscal_year in affected_years:
            previous_id = previous_by_year.get(fiscal_year)
            if (
                ann.status in {"cancellation", "correction_notice"}
                or _RE_CORRECTED_FULL.search(ann.title)
                or _RE_HK_REVISED_FULL.search(ann.title)
            ):
                ann.replacement_targets[fiscal_year] = ann.explicit_target_id or previous_id
            if ann.status == "cancellation" and previous_id is None:
                # cninfo can mutate the original catalog row into an "已取消" row,
                # leaving no separate eligible record to anchor the replacement chain.
                previous_by_year[fiscal_year] = ann.announcement_id
            if ann.status not in {
                "cancellation",
                "correction_notice",
                "excluded",
                "after_cutoff",
            }:
                previous_by_year[fiscal_year] = ann.announcement_id
        targets = {target for target in ann.replacement_targets.values() if target is not None}
        if len(targets) == 1:
            ann.replacement_of = targets.pop()


def _is_same_correction_batch(
    corrected_report: Announcement,
    correction_notice: Announcement,
) -> bool:
    if not (
        corrected_report.announcement_id.isdigit() and correction_notice.announcement_id.isdigit()
    ):
        return False
    ids_are_adjacent = (
        int(correction_notice.announcement_id) - int(corrected_report.announcement_id) == 1
    )
    time_delta = correction_notice.announcement_time - corrected_report.announcement_time
    return ids_are_adjacent and timedelta(0) <= time_delta <= timedelta(minutes=5)


def _annual_report_type(announcement: Announcement) -> str:
    if _is_cn_annual_cancellation(announcement.title) or _is_hk_annual_cancellation(
        announcement.title
    ):
        return "cancellation_notice"
    if _RE_CORRECTION_NOTICE.search(announcement.title) or _RE_HK_CORRECTION_NOTICE.search(
        announcement.title
    ):
        return "correction_notice"
    if announcement.status == "excluded":
        return "excluded_announcement"
    return "annual_report"


def _classify_annual_catalog(
    records: list[dict],
    exchange: str,
    years: int,
    cutoff: date,
    end_year: int | None,
    *,
    reject_malformed: bool,
    period_end_resolver: Callable[[Announcement], date] | None = None,
) -> tuple[list[Announcement], list[Announcement]]:
    is_hk = exchange == "HK"
    candidates: list[Announcement] = []
    cancellation_notices: dict[int, list[Announcement]] = {}
    correction_notices: dict[int, list[Announcement]] = {}
    unresolved_replacement_notices: list[Announcement] = []
    parsed_catalog: list[Announcement] = []
    for sequence_id, record in enumerate(records):
        announcement = (
            _to_hkex_announcement(record, sequence_id)
            if is_hk
            else _to_announcement(record, sequence_id)
        )
        if announcement is None:
            if reject_malformed:
                source = "HKEX" if is_hk else "cninfo"
                raise FetchSchemaError(
                    f"{source} annual catalog contains malformed official record at "
                    f"sequence {sequence_id}"
                )
            continue
        parsed_catalog.append(announcement)
        if announcement.announcement_date > cutoff:
            announcement.status = "after_cutoff"
            continue
        is_cancellation = (
            _is_hk_annual_cancellation(announcement.title)
            if is_hk
            else _is_cn_annual_cancellation(announcement.title)
        )
        if is_cancellation:
            affected_years = _announcement_years(announcement)
            if not affected_years:
                announcement.status = "unresolved_fiscal_year"
                unresolved_replacement_notices.append(announcement)
                continue
            announcement.status = "cancellation"
            for fiscal_year in affected_years:
                cancellation_notices.setdefault(fiscal_year, []).append(announcement)
            continue
        is_correction = (
            bool(_RE_HK_CORRECTION_NOTICE.search(announcement.title))
            if is_hk
            else bool(
                _RE_CORRECTION_NOTICE.search(announcement.title)
                or _RE_ACCOUNTING_RESTATEMENT_NOTICE.search(announcement.title)
            )
        )
        if is_correction:
            affected_years = _announcement_years(announcement)
            if not affected_years:
                announcement.status = "unresolved_fiscal_year"
                unresolved_replacement_notices.append(announcement)
                continue
            announcement.status = "correction_notice"
            for fiscal_year in affected_years:
                correction_notices.setdefault(fiscal_year, []).append(announcement)
            continue
        is_excluded = (
            bool(_RE_EXCLUDE_TITLE_HK.search(announcement.title))
            or not _RE_HK_FULL_REPORT.search(announcement.title)
            if is_hk
            else bool(_RE_EXCLUDE_TITLE.search(announcement.title))
            or not _RE_ANNUAL_FULL_TITLE.fullmatch(announcement.title)
        )
        if is_excluded:
            announcement.status = "excluded"
            continue
        if is_hk and period_end_resolver is not None:
            period_end = period_end_resolver(announcement)
            if announcement.report_period_end is not None:
                metadata_period = date.fromisoformat(announcement.report_period_end)
                if metadata_period != period_end:
                    raise FetchSchemaError(
                        "HKEX metadata/PDF period conflict: "
                        f"metadata={metadata_period.isoformat()}, "
                        f"PDF={period_end.isoformat()}"
                    )
            elif announcement.year is not None and announcement.year != period_end.year:
                raise FetchSchemaError(
                    f"HKEX fiscal-year conflict: title implies {announcement.year}, "
                    f"report period ends {period_end.isoformat()}"
                )
            announcement.report_period_end = period_end.isoformat()
            announcement.year = period_end.year
        if end_year is not None and (
            announcement.year is not None and announcement.year > end_year
        ):
            announcement.status = "after_target_year"
            continue
        if announcement.year is None:
            announcement.status = "unresolved_fiscal_year"
            continue
        candidates.append(announcement)

    _bind_replacement_relationships(parsed_catalog)
    if unresolved_replacement_notices:
        raise FetchSchemaError(
            "replacement notice fiscal year cannot be resolved: "
            + ", ".join(notice.title for notice in unresolved_replacement_notices)
        )

    by_year: dict[int, Announcement] = {}
    for announcement in candidates:
        assert announcement.year is not None
        existing = by_year.get(announcement.year)
        if existing is None or _announcement_sort_key(announcement) > _announcement_sort_key(
            existing
        ):
            by_year[announcement.year] = announcement

    for fiscal_year, notices in cancellation_notices.items():
        selected = by_year.get(fiscal_year)
        if selected is None:
            continue
        for notice in sorted(notices, key=_announcement_sort_key):
            target_id = notice.explicit_target_id or notice.replacement_targets.get(fiscal_year)
            target = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.year == fiscal_year and candidate.announcement_id == target_id
                ),
                None,
            )
            if target_id is not None and target is None:
                raise FetchSchemaError(
                    f"FY{fiscal_year} cancellation target {target_id} is not in catalog"
                )
            if target is not None:
                target.status = "cancelled"
            if (target is selected or target_id is None) and _announcement_sort_key(
                notice
            ) > _announcement_sort_key(selected):
                selected.status = "cancelled"
                del by_year[fiscal_year]
                break

    for fiscal_year, notices in correction_notices.items():
        notice = max(notices, key=_announcement_sort_key)
        corrected_at = _announcement_sort_key(notice)
        selected = by_year.get(fiscal_year)
        if selected is None or corrected_at <= _announcement_sort_key(selected):
            continue
        revised_pattern = _RE_HK_REVISED_FULL if is_hk else _RE_CORRECTED_FULL
        has_later_corrected_full = any(
            announcement.year == fiscal_year
            and revised_pattern.search(announcement.title)
            and (
                _announcement_sort_key(announcement) > corrected_at
                or _is_same_correction_batch(announcement, notice)
            )
            for announcement in candidates
        )
        if not has_later_corrected_full:
            qualifier = "revised" if is_hk else "corrected"
            raise FetchSchemaError(
                f"FY{fiscal_year} has a correction notice but no later {qualifier} full report"
            )

    latest_years = sorted(by_year, reverse=True)[:years]
    selected_ids = {id(by_year[year]) for year in latest_years}
    for announcement in candidates:
        if id(announcement) in selected_ids:
            announcement.status = "selected"
        elif announcement.status == "eligible":
            announcement.status = (
                "superseded"
                if (announcement.year in by_year and by_year[announcement.year] is not announcement)
                else "outside_window"
            )
    return [by_year[year] for year in latest_years], parsed_catalog


def search_annual_reports(
    org_id: str,
    code: str,
    exchange: str,
    years: int,
    *,
    as_of: date | None = None,
    end_year: int | None = None,
    listing_date: date | None = None,
    raw_response: bytes | None = None,
    catalog_out: list[Announcement] | None = None,
    trace_out: dict[str, object] | None = None,
) -> list[Announcement]:
    """Return de-duplicated 年报 announcements for the N most recent fiscal years.

    When multiple 年报 exist for the same year (original + 更正/revision), the
    latest by announcement date wins. 摘要、英文版、取消文件和补充公告 are
    filtered out; 修订版、更正版 and 更正后 full reports remain eligible.

    `as_of` excludes announcements published after the research cutoff before
    fiscal-year de-duplication. `raw_response` is injectable for tests."""
    cutoff = as_of or date.today()
    start = (
        date(end_year - years, 1, 1).isoformat()
        if end_year is not None
        else _subtract_years(cutoff, years + 1).isoformat()
    )
    end = cutoff.isoformat()
    form = {
        "stock": f"{code},{org_id}",
        "tabName": "fulltext",
        "pageSize": "30",
        "pageNum": "1",
        "column": _exchange_column(exchange),
        "category": CATEGORY_ANNUAL,
        "seDate": f"{start}~{end}",
    }
    response_bodies: list[bytes] = []
    queried_pages: list[dict[str, str]] = []
    official_total: int | None = None
    if raw_response is not None:
        records = _parse_announcements(raw_response)
        response_bodies.append(raw_response)
        queried_pages.append(dict(form))
        official_total = _parse_announcement_total(raw_response)
    else:
        records = []
        seen_records: set[str] = set()
        page_num = 1
        while True:
            form["pageNum"] = str(page_num)
            queried_pages.append(dict(form))
            raw = _http_post_form(ANNOUNCEMENT_QUERY_URL, form)
            response_bodies.append(raw)
            page_records = _parse_announcements(raw)
            total = _parse_announcement_total(raw)
            if total is None:
                raise FetchSchemaError(
                    "cninfo announcement query omitted totalAnnouncement; "
                    "cannot prove catalog completeness"
                )
            if official_total is None:
                official_total = total
            elif total != official_total:
                raise FetchSchemaError("cninfo announcement total changed during pagination")
            if not page_records and len(records) < official_total:
                raise FetchSchemaError("cninfo announcement pagination ended before official total")
            for record in page_records:
                identity = str(
                    record.get("announcementId")
                    or record.get("adjunctUrl")
                    or json.dumps(record, sort_keys=True)
                )
                if identity in seen_records:
                    raise FetchSchemaError(
                        f"cninfo announcement pagination returned duplicate announcement {identity}"
                    )
                seen_records.add(identity)
                records.append(record)
            if len(records) > official_total:
                raise FetchSchemaError("cninfo announcement pagination exceeded official total")
            if len(records) == official_total:
                break
            page_num += 1
    if trace_out is not None:
        trace_out.update(
            {
                "query_url": ANNOUNCEMENT_QUERY_URL,
                "query_params": queried_pages,
                "response_sha256": _sha256_bytes(b"".join(response_bodies)),
                "official_total": official_total if official_total is not None else len(records),
                "resolved_org_id": org_id,
                "selection_years": years,
                "target_end_year": end_year,
                "listing_date": listing_date.isoformat() if listing_date else None,
                "listing_history_complete": bool(
                    listing_date and date.fromisoformat(start) <= listing_date
                ),
            }
        )

    selected, parsed_catalog = _classify_annual_catalog(
        records,
        exchange,
        years,
        cutoff,
        end_year,
        reject_malformed=raw_response is None,
    )
    if catalog_out is not None:
        catalog_out.extend(parsed_catalog)
    return selected


# ---------------------------------------------------------------------------
# HKEX title search
# ---------------------------------------------------------------------------


def _extract_year_hk(title: str) -> int | None:
    """Extract fiscal year from an HKEX annual-report title.

    Fiscal-year ranges such as "2024/25" use the ending year. Otherwise this
    tries the A-share Chinese pattern ("2023年年度报告"), then falls back to any
    4-digit year in the string ("Annual Report 2023")."""
    range_match = _RE_HK_FISCAL_YEAR_RANGE.search(title)
    if range_match:
        start_year = int(range_match.group(1))
        end_suffix = int(range_match.group(2))
        end_year = start_year // 100 * 100 + end_suffix
        if end_year < start_year:
            end_year += 100
        if end_year == start_year + 1 and 1990 <= end_year <= 2035:
            return end_year
    year = _extract_year(title)
    if year is not None:
        return year
    m = _RE_YEAR_4DIGIT.search(title)
    if m:
        y = int(m.group(1))
        if 1990 <= y <= 2035:
            return y
    return None


def resolve_hkex_stock_id(code: str, *, stocklist_bytes: bytes | None = None) -> str:
    """Return HKEX's internal stockId for a given 1-5 digit stock code.

    HKEX's title-search API keys on an internal integer id (e.g. Tencent =
    7609), not the 5-digit stock code. The mapping is published as a static
    JSON file at HKEX_ACTIVE_STOCK_URL. Only active (non-delisted) stocks
    are covered; delisted tickers would need the inactive-stock URL.

    `stocklist_bytes` is injectable for tests."""
    padded = code.zfill(5)
    raw = stocklist_bytes if stocklist_bytes is not None else _http_get(HKEX_ACTIVE_STOCK_URL)
    if not isinstance(raw, bytes):
        raise FetchSchemaError("HKEX active-stock list: response body must be bytes")
    try:
        rows = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise FetchSchemaError(
            f"HKEX active-stock list: not valid JSON ({e}). First 200 bytes: {raw[:200]!r}"
        ) from e
    if not isinstance(rows, list):
        raise FetchSchemaError(
            f"HKEX active-stock list: expected JSON array, got {type(rows).__name__}. "
            f"First 200 bytes: {raw[:200]!r}"
        )
    mappings: dict[str, str] = {}
    seen_stock_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise FetchSchemaError("HKEX active-stock list: every row must be an object")
        issuer_code = row.get("c")
        stock_id = row.get("i")
        if (
            not isinstance(issuer_code, str)
            or re.fullmatch(r"\d{5}", issuer_code) is None
            or not isinstance(stock_id, int)
            or isinstance(stock_id, bool)
            or stock_id <= 0
        ):
            raise FetchSchemaError(f"HKEX active-stock list: malformed mapping row: {row!r}")
        normalized_stock_id = str(stock_id)
        if issuer_code in mappings:
            raise FetchSchemaError(f"HKEX active-stock list: duplicate issuer code {issuer_code}")
        if normalized_stock_id in seen_stock_ids:
            raise FetchSchemaError(
                f"HKEX active-stock list: duplicate internal stockId {normalized_stock_id}"
            )
        mappings[issuer_code] = normalized_stock_id
        seen_stock_ids.add(normalized_stock_id)
    if padded in mappings:
        return mappings[padded]
    raise ValueError(
        f"HK stock code {padded} not found in HKEX active-stock list "
        f"({len(rows)} entries). Delisted stocks are not currently supported."
    )


def _parse_hkex_announcements(raw: bytes) -> list[dict]:
    """Decode the HKEX titleSearchServlet response.

    The servlet wraps records in `{"result": "<json-encoded string>"}`, so
    `result` is a string that must itself be parsed. Historical variants
    that returned a bare array or a dict with a list-valued `result` field
    are also accepted."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise FetchSchemaError(
            f"HKEX title search: not valid JSON ({e}). First 200 bytes: {raw[:200]!r}"
        ) from e
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("result", "results", "data", "RESULT"):
            val = data.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    inner = json.loads(val)
                except json.JSONDecodeError as e:
                    raise FetchSchemaError(
                        f"HKEX title search: '{key}' is a string but not JSON ({e}). "
                        f"First 200 bytes: {val[:200]!r}"
                    ) from e
                if isinstance(inner, list):
                    return inner
    raise FetchSchemaError(
        f"HKEX title search: expected JSON list or dict with 'result' list/string, "
        f"got {type(data).__name__}. First 200 bytes: {raw[:200]!r}"
    )


def _parse_hkex_official_total(raw: bytes) -> int | None:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("total", "totalCount", "recordCount", "TOTAL"):
        value = data.get(key)
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _to_hkex_announcement(rec: dict, sequence_id: int = 0) -> Announcement | None:
    """Validate + convert one HKEX record. Returns None on missing fields."""
    title = rec.get("TITLE") or rec.get("title")
    file_link = rec.get("FILE_LINK") or rec.get("file_link")
    date_str = rec.get("DATE_TIME") or rec.get("date_time") or rec.get("DATE")
    if not title or not file_link or not date_str:
        return None
    # HKEX DATE_TIME is "DD/MM/YYYY HH:MM"; defensively also accept ISO.
    # We only need the date portion — strip anything after the first 10 chars
    # and match against the two plausible date-only formats.
    head = str(date_str).strip()[:10]
    ann_time: datetime | None = None
    raw_date = str(date_str).strip()
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            local_time = datetime.strptime(raw_date if "%H" in fmt else head, fmt)
            ann_time = local_time.replace(tzinfo=_HK_TIMEZONE).astimezone(UTC)
            break
        except ValueError:
            continue
    if ann_time is None:
        return None
    file_url = urllib.parse.urljoin(HKEX_BASE_URL, str(file_link))
    period_end_raw = (
        rec.get("REPORT_PERIOD_END")
        or rec.get("report_period_end")
        or rec.get("PERIOD_END")
        or rec.get("period_end")
    )
    period_end: date | None = None
    if period_end_raw:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                period_end = datetime.strptime(str(period_end_raw), fmt).date()
                break
            except ValueError:
                continue
        if period_end is None:
            return None
    title_text = str(title).strip()
    title_year = _extract_year_hk(title_text)
    affected_years = (
        _extract_restatement_years(title_text)
        if _RE_HK_CORRECTION_NOTICE.search(title_text)
        else ()
    )
    is_notice = bool(
        _is_hk_annual_cancellation(title_text) or _RE_HK_CORRECTION_NOTICE.search(title_text)
    )
    if (
        not is_notice
        and period_end is not None
        and title_year is not None
        and title_year != period_end.year
    ):
        raise FetchSchemaError(
            f"HKEX fiscal-year conflict: title implies {title_year}, "
            f"report period ends {period_end.isoformat()}"
        )
    return Announcement(
        title=title_text,
        adjunct_url=file_url,
        announcement_date=ann_time.astimezone(_HK_TIMEZONE).date(),
        announcement_time=ann_time,
        year=period_end.year if period_end is not None else title_year,
        announcement_id=str(rec.get("NEWS_ID") or rec.get("news_id") or file_link),
        sequence_id=sequence_id,
        affected_years=affected_years,
        explicit_target_id=_explicit_target_id(rec),
        report_period_end=(
            "不适用" if is_notice else period_end.isoformat() if period_end else None
        ),
    )


def _fetch_hkex_complete_catalog(
    params: dict[str, str],
) -> tuple[list[dict], list[bytes], list[dict[str, str]]]:
    """Fetch HKEX results, splitting date windows that hit the row cap."""
    url = f"{HKEX_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    raw = _http_get(url)
    records = _parse_hkex_announcements(raw)
    if len(records) < int(params["rowRange"]):
        return records, [raw], [dict(params)]

    start = datetime.strptime(params["fromDate"], "%Y%m%d").date()
    end = datetime.strptime(params["toDate"], "%Y%m%d").date()
    if start >= end:
        raise FetchSchemaError(
            f"HKEX title search reached rowRange={params['rowRange']} for one day; "
            "catalog remains truncated"
        )
    midpoint = start + (end - start) // 2
    windows = (
        (start, midpoint),
        (midpoint + timedelta(days=1), end),
    )
    combined: list[dict] = []
    bodies: list[bytes] = [raw]
    queried: list[dict[str, str]] = [dict(params)]
    seen: set[str] = set()
    for window_start, window_end in windows:
        child = dict(params)
        child["fromDate"] = window_start.strftime("%Y%m%d")
        child["toDate"] = window_end.strftime("%Y%m%d")
        child_records, child_bodies, child_queries = _fetch_hkex_complete_catalog(child)
        bodies.extend(child_bodies)
        queried.extend(child_queries)
        for record in child_records:
            identity = str(
                record.get("NEWS_ID")
                or record.get("news_id")
                or record.get("FILE_LINK")
                or record.get("file_link")
                or json.dumps(record, sort_keys=True)
            )
            if identity not in seen:
                seen.add(identity)
                combined.append(record)
    return combined, bodies, queried


def search_hkex_annual_reports(
    code: str,
    years: int,
    *,
    prefer_lang: str = "en",
    as_of: date | None = None,
    end_year: int | None = None,
    listing_date: date | None = None,
    stock_id: str | None = None,
    raw_response: bytes | None = None,
    raw_stocklist: bytes | None = None,
    catalog_out: list[Announcement] | None = None,
    trace_out: dict[str, object] | None = None,
    period_end_resolver: Callable[[Announcement], date] | None = None,
) -> list[Announcement]:
    """Return 年报 / Annual Report announcements for an HK ticker, one per
    fiscal year, for the most recent `years` years.

    `code` is the 1-5 digit stock code; zero-padded to 5 digits before
    lookup. `prefer_lang` selects `lang=EN` (English title / non-`_c.pdf`)
    or `lang=ZH` (Chinese title / `_c.pdf`) on the HKEX side — the API
    returns one language variant per filing, not both.

    Resolution strategy:
      1. Map code → HKEX internal `stockId` via activestock JSON (one GET)
      2. GET titleSearchServlet.do?stockId=<id>&...
      3. Parse wrapper → parse inner JSON array → filter by title → dedup
         by fiscal year (latest announcement wins)

    `as_of` excludes announcements published after the research cutoff before
    fiscal-year de-duplication. `stock_id`, `raw_response`, and
    `raw_stocklist` are injectable for tests."""
    if prefer_lang not in ("en", "zh"):
        raise ValueError(f"prefer_lang must be 'en' or 'zh', got {prefer_lang!r}")
    stocklist_body = raw_stocklist
    if stocklist_body is None and (stock_id is None or trace_out is not None):
        stocklist_body = _http_get(HKEX_ACTIVE_STOCK_URL)
    authenticated_stock_id: str | None = None
    if stocklist_body is not None:
        authenticated_stock_id = resolve_hkex_stock_id(
            code,
            stocklist_bytes=stocklist_body,
        )
    if stock_id is None:
        if authenticated_stock_id is None:
            raise FetchSchemaError("HKEX stockId mapping evidence is unavailable")
        stock_id = authenticated_stock_id
    elif authenticated_stock_id is not None and stock_id != authenticated_stock_id:
        raise FetchSchemaError("HKEX requested stockId does not match the active-stock mapping")
    cutoff = as_of or date.today()
    # Pad the window by one year to catch late-filed prior-year reports.
    from_date = (
        date(end_year - years, 1, 1).strftime("%Y%m%d")
        if end_year is not None
        else _subtract_years(cutoff, years + 1).strftime("%Y%m%d")
    )
    to_date = cutoff.strftime("%Y%m%d")
    params = {
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
        "lang": "EN" if prefer_lang == "en" else "ZH",
    }
    if raw_response is not None:
        raw = raw_response
        records = _parse_hkex_announcements(raw)
        official_total = _parse_hkex_official_total(raw)
        if official_total is not None and official_total != len(records):
            raise FetchSchemaError("HKEX official total does not match returned catalog records")
        response_bodies = [raw]
        queried_windows = [dict(params)]
        if len(records) >= int(params["rowRange"]):
            raise FetchSchemaError(
                f"HKEX title search reached rowRange={params['rowRange']}; catalog may be truncated"
            )
    else:
        records, response_bodies, queried_windows = _fetch_hkex_complete_catalog(params)
    if trace_out is not None:
        trace_out.update(
            {
                "query_url": HKEX_SEARCH_URL,
                "query_params": queried_windows,
                "query_issuer_code": code.zfill(5),
                "resolved_stock_id": stock_id,
                "stocklist_source_url": HKEX_ACTIVE_STOCK_URL,
                "stocklist_response_bytes": stocklist_body,
                "stocklist_response_sha256": (
                    _sha256_bytes(stocklist_body) if stocklist_body is not None else None
                ),
                "stocklist_mapping": {
                    "issuer_code": code.zfill(5),
                    "stock_id": stock_id,
                },
                "response_sha256": _sha256_bytes(b"".join(response_bodies)),
                "official_total": (
                    official_total
                    if raw_response is not None and official_total is not None
                    else len(records)
                ),
                "official_total_source": (
                    "response_total"
                    if raw_response is not None and official_total is not None
                    else "complete_window_record_count"
                ),
                "selection_years": years,
                "target_end_year": end_year,
                "official_window_result_counts": [
                    len(_parse_hkex_announcements(body)) for body in response_bodies
                ],
                "listing_date": listing_date.isoformat() if listing_date else None,
                "listing_history_complete": bool(
                    listing_date and datetime.strptime(from_date, "%Y%m%d").date() <= listing_date
                ),
            }
        )

    selected, parsed_catalog = _classify_annual_catalog(
        records,
        "HK",
        years,
        cutoff,
        end_year,
        reject_malformed=raw_response is None,
        period_end_resolver=period_end_resolver,
    )
    if catalog_out is not None:
        catalog_out.extend(parsed_catalog)
    return selected


def search_prospectus(
    org_id: str,
    code: str,
    exchange: str,
    *,
    as_of: date | None = None,
    raw_response: bytes | None = None,
) -> list[Announcement]:
    """Return the 招股说明书 announcement(s) for this ticker.

    We use a title keyword search (`searchkey=招股说明书`) rather than a
    category — the category `category_fxbg_szsh` is noisy. Filters titles
    exactly equal to "招股说明书" (excluding 附录 / 补充 / 修订)."""
    cutoff = as_of or date.today()
    form = {
        "stock": f"{code},{org_id}",
        "tabName": "fulltext",
        "pageSize": "30",
        "pageNum": "1",
        "column": _exchange_column(exchange),
        "searchkey": "招股说明书",
        "seDate": "1990-01-01~" + cutoff.isoformat(),
    }
    if raw_response is not None:
        records = _parse_announcements(raw_response)
    else:
        records = []
        seen_records: set[str] = set()
        official_total: int | None = None
        page_num = 1
        while True:
            form["pageNum"] = str(page_num)
            raw = _http_post_form(ANNOUNCEMENT_QUERY_URL, form)
            page_records = _parse_announcements(raw)
            total = _parse_announcement_total(raw)
            if total is None:
                raise FetchSchemaError(
                    "cninfo prospectus query omitted totalAnnouncement; "
                    "cannot prove catalog completeness"
                )
            if official_total is None:
                official_total = total
            elif total != official_total:
                raise FetchSchemaError("cninfo prospectus total changed during pagination")
            if not page_records and len(records) < official_total:
                raise FetchSchemaError("cninfo prospectus pagination ended before official total")
            for record in page_records:
                identity = str(
                    record.get("announcementId")
                    or record.get("adjunctUrl")
                    or json.dumps(record, sort_keys=True)
                )
                if identity in seen_records:
                    raise FetchSchemaError(
                        f"cninfo prospectus pagination returned duplicate announcement {identity}"
                    )
                seen_records.add(identity)
                records.append(record)
            if len(records) > official_total:
                raise FetchSchemaError("cninfo prospectus pagination exceeded official total")
            if len(records) == official_total:
                break
            page_num += 1

    matches: list[Announcement] = []
    for sequence_id, rec in enumerate(records):
        ann = _to_announcement(rec, sequence_id)
        if ann is None:
            if raw_response is None:
                raise FetchSchemaError(
                    f"cninfo prospectus query contains malformed official record at "
                    f"sequence {sequence_id}"
                )
            continue
        # Exclude 附录 / 补充 / 修订 — only the canonical document.
        if not _RE_PROSPECTUS_TITLE.match(ann.title):
            continue
        if ann.announcement_date > cutoff:
            continue
        matches.append(ann)

    # Prefer the latest (in case of re-filings).
    matches.sort(key=lambda a: a.announcement_time, reverse=True)
    return matches


# ---------------------------------------------------------------------------
# PDF download (idempotent)
# ---------------------------------------------------------------------------


def _sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_hk_report_period_end(pdf_path: Path) -> date:
    """Return a period end confirmed by both the cover and audited statements."""
    cover_result = subprocess.run(
        ["pdftotext", "-f", "1", "-l", "10", "-layout", str(pdf_path), "-"],
        capture_output=True,
        check=False,
    )
    statement_result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        check=False,
    )
    if cover_result.returncode != 0 or statement_result.returncode != 0:
        raise FetchSchemaError(
            "could not extract HK report period from PDF: "
            + (
                cover_result.stderr.decode("utf-8", "replace")
                or statement_result.stderr.decode("utf-8", "replace")
            )
        )
    cover_text = cover_result.stdout.decode("utf-8", "replace")
    statement_text = statement_result.stdout.decode("utf-8", "replace")
    authority_markers = re.compile(
        r"consolidated financial statements|consolidated statement of financial position|"
        r"consolidated balance sheets?|"
        r"audited financial statements|綜合財務報表|综合财务报表|"
        r"綜合財務狀況表|综合财务状况表|經審核財務報表|经审核财务报表",
        re.IGNORECASE,
    )
    excluded_context = re.compile(
        r"forecast|projection|budget|pro forma|comparative|预测|預測|预算|預算",
        re.IGNORECASE,
    )

    def collect_dates(text: str, *, authoritative_only: bool) -> set[date]:
        dates: set[date] = set()
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if excluded_context.search(line):
                continue
            authority_context = "\n".join(lines[max(0, index - 3) : index + 1])
            if authoritative_only and not (
                authority_markers.search(line) or authority_markers.search(authority_context)
            ):
                continue
            multi_year_match = _RE_HK_MULTI_YEAR_END_EN.search(line)
            if multi_year_match:
                years = [
                    int(year)
                    for year in re.findall(
                        r"(?<!\d)((?:19|20)\d{2})(?!\d)",
                        multi_year_match.group(3),
                    )
                ]
                dates.add(
                    datetime.strptime(
                        f"{multi_year_match.group(2)} {multi_year_match.group(1)} {max(years)}",
                        "%d %B %Y",
                    ).date()
                )
                continue
            for match in _RE_HK_PERIOD_END_EN.finditer(line):
                dates.add(
                    datetime.strptime(
                        f"{match.group(1)} {match.group(2)} {match.group(3)}",
                        "%d %B %Y",
                    ).date()
                )
            for match in _RE_HK_PERIOD_END_EN_MDY.finditer(line):
                dates.add(
                    datetime.strptime(
                        f"{match.group(2)} {match.group(1)} {match.group(3)}",
                        "%d %B %Y",
                    ).date()
                )
            for match in _RE_HK_PERIOD_END_ZH.finditer(line):
                dates.add(
                    date(
                        int(match.group(1)),
                        int(match.group(2)),
                        int(match.group(3)),
                    )
                )
            split_match = _RE_HK_SPLIT_PERIOD_END_EN.search(line)
            if split_match:
                following = " ".join(lines[index + 1 : index + 3])
                years = [
                    int(year) for year in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", following)
                ]
                if years:
                    dates.add(
                        datetime.strptime(
                            f"{split_match.group(2)} {split_match.group(1)} {max(years)}",
                            "%d %B %Y",
                        ).date()
                    )
        return dates

    cover_dates = collect_dates(cover_text, authoritative_only=False)
    statement_dates = collect_dates(statement_text, authoritative_only=True)
    confirmed_dates = cover_dates & statement_dates
    if len(confirmed_dates) != 1:
        cover_fiscal_years = {
            int(match.group(1)) for match in _RE_HK_COVER_FISCAL_YEAR.finditer(cover_text)
        }
        if len(cover_fiscal_years) == 1:
            cover_fiscal_year = next(iter(cover_fiscal_years))
            confirmed_dates = {
                period_end for period_end in statement_dates if period_end.year == cover_fiscal_year
            }
    if len(confirmed_dates) != 1:
        raise FetchSchemaError(
            "HK annual-report cover and audited statement must expose exactly one common period end"
        )
    return next(iter(confirmed_dates))


def _persist_immutable_response(
    out_dir: Path,
    label: str,
    body: bytes,
) -> Path:
    digest = _sha256_bytes(body)
    versions_dir = out_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    destination = versions_dir / f"{label}-{digest}.json"
    if destination.exists():
        if destination.read_bytes() != body:
            raise FetchSchemaError(f"Immutable official response path is corrupt: {destination}")
        return destination.resolve()

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=versions_dir,
            prefix=f".{destination.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(body)
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            if destination.read_bytes() != body:
                raise FetchSchemaError(
                    "Immutable official response path already exists with "
                    f"different evidence: {destination}"
                ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination.resolve()


def write_annual_manifest(
    out_dir: Path,
    ticker: str,
    as_of: date,
    catalog: list[Announcement],
    selected_paths: dict[int, Path],
    trace: dict[str, object],
    *,
    manifest_out: Path | None = None,
) -> Path:
    """Persist the complete official annual-report catalog and selected files."""
    ticker = canonical_ticker(ticker)
    ticker_code, exchange = ticker.rsplit(".", 1)
    query_params = trace.get("query_params")
    hkex_stock_id_evidence: dict[str, object] | None = None
    if exchange == "HK":
        query_code = str(trace.get("query_issuer_code") or "")
        resolved_stock_id = str(trace.get("resolved_stock_id") or "")
        stocklist_source_url = str(trace.get("stocklist_source_url") or "")
        stocklist_body = trace.get("stocklist_response_bytes")
        stocklist_sha256 = str(trace.get("stocklist_response_sha256") or "")
        stocklist_mapping = trace.get("stocklist_mapping")
        windows = query_params if isinstance(query_params, list) else []
        windows_are_typed = bool(windows) and all(isinstance(window, dict) for window in windows)
        same_code = query_code == ticker_code
        same_stock_id = (
            bool(resolved_stock_id)
            and windows_are_typed
            and all(str(window.get("stockId") or "") == resolved_stock_id for window in windows)
        )
        if (
            not same_code
            or not same_stock_id
            or stocklist_source_url != HKEX_ACTIVE_STOCK_URL
            or not isinstance(stocklist_body, bytes)
            or _sha256_bytes(stocklist_body) != stocklist_sha256
            or stocklist_mapping
            != {
                "issuer_code": ticker_code,
                "stock_id": resolved_stock_id,
            }
            or resolve_hkex_stock_id(
                ticker_code,
                stocklist_bytes=stocklist_body,
            )
            != resolved_stock_id
        ):
            raise FetchSchemaError(
                "HK manifest query issuer does not match ticker or resolved stockId"
            )
        _validate_hkex_query_filters(windows, resolved_stock_id)
        stocklist_path = _persist_immutable_response(
            out_dir,
            "hkex-active-stock",
            stocklist_body,
        )
        hkex_stock_id_evidence = {
            "source_url": stocklist_source_url,
            "response_path": str(stocklist_path),
            "response_sha256": stocklist_sha256,
            "mapping": stocklist_mapping,
        }
    else:
        queries = query_params if isinstance(query_params, list) else [query_params]
        query_codes = {
            str(query.get("stock") or "").split(",", 1)[0]
            for query in queries
            if isinstance(query, dict) and query.get("stock")
        }
        if query_codes != {ticker_code}:
            raise FetchSchemaError("CN manifest query issuer does not match ticker")

    candidates: list[dict[str, object]] = []
    selected_source_snapshots: list[tuple[Path, str, str, Path]] = []
    for ann in catalog:
        selected_source = selected_paths.get(ann.year) if ann.status == "selected" else None
        selected_path = (
            _persist_immutable_annual_pdf(
                out_dir,
                ann.year,
                selected_source,
                expected_official_url=ann.adjunct_url,
            )
            if ann.year is not None and selected_source is not None
            else None
        )
        candidates.append(
            {
                "fiscal_year": ann.year,
                "report_period_end": ann.report_period_end,
                "announcement_time": ann.announcement_time.isoformat(),
                "announcement_id": ann.announcement_id,
                "sequence_id": ann.sequence_id,
                "title": ann.title,
                "report_type": _annual_report_type(ann),
                "status": ann.status,
                "explicit_target_id": ann.explicit_target_id,
                "replacement_of": ann.replacement_of,
                "replacement_targets": {
                    str(year): target for year, target in sorted(ann.replacement_targets.items())
                },
                "affected_fiscal_years": list(_announcement_years(ann)),
                "official_url": ann.adjunct_url,
                "selected": selected_path is not None,
                "absolute_path": (
                    str(selected_path.resolve()) if selected_path is not None else None
                ),
                "file_sha256": (_sha256_path(selected_path) if selected_path is not None else None),
            }
        )
        if selected_source is not None and selected_path is not None:
            selected_source_snapshots.append(
                (
                    selected_source,
                    ann.adjunct_url,
                    _sha256_path(selected_path),
                    selected_path,
                )
            )
    payload = {
        "ticker": ticker,
        "exchange": exchange,
        "AS_OF": as_of.isoformat(),
        "查询发行人代码": ticker_code,
        "as_of": as_of.isoformat(),
        "official_query_url": trace.get("query_url"),
        "official_query_params": trace.get("query_params"),
        "response_sha256": trace.get("response_sha256"),
        "official_result_total": trace.get("official_total"),
        "query_issuer_code": trace.get("query_issuer_code"),
        "resolved_stock_id": trace.get("resolved_stock_id"),
        "hkex_stock_id_evidence": hkex_stock_id_evidence,
        "resolved_org_id": trace.get("resolved_org_id"),
        "selection_years": trace.get("selection_years"),
        "target_end_year": trace.get("target_end_year"),
        "candidate_count": len(candidates),
        "listing_date": trace.get("listing_date"),
        "listing_history_complete": bool(trace.get("listing_history_complete", False)),
        "listing_profile": trace.get("listing_profile"),
        "candidates": candidates,
    }
    path = manifest_out or (out_dir / "manifests" / f"annual-reports-{as_of.isoformat()}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    serialized_bytes = serialized.encode("utf-8")
    content_path = path.with_name(f"{path.stem}-{_sha256_bytes(serialized_bytes)}{path.suffix}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(serialized)
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        os.chmod(temporary, 0o644)
        for candidate in (path, content_path):
            for source, official_url, expected_sha256, immutable_path in selected_source_snapshots:
                if (
                    _sha256_path(source) != expected_sha256
                    or _sha256_path(immutable_path) != expected_sha256
                ):
                    raise FetchSchemaError(
                        "Selected annual-report PDF changed before manifest publication"
                    )
                _validate_selected_pdf_source(
                    source,
                    official_url,
                    expected_sha256=expected_sha256,
                )
            if candidate.exists():
                if candidate.read_bytes() == serialized_bytes:
                    return candidate
                continue
            try:
                os.link(temporary, candidate)
                return candidate
            except FileExistsError:
                if candidate.read_bytes() == serialized_bytes:
                    return candidate
        raise FetchSchemaError(
            "Annual-report content-addressed manifest path contains different evidence"
        )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _fetch_live_annual_catalog(
    url: str,
    exchange: str,
    params: dict[str, object],
) -> bytes:
    string_params = {str(key): str(value) for key, value in params.items()}
    if exchange == "HK":
        separator = "&" if "?" in url else "?"
        return _http_get(f"{url}{separator}{urllib.parse.urlencode(string_params)}")
    return _http_post_form(url, string_params)


_REQUIRED_ANNUAL_CANDIDATE_FIELDS = {
    "fiscal_year",
    "report_period_end",
    "announcement_time",
    "announcement_id",
    "sequence_id",
    "title",
    "report_type",
    "status",
    "replacement_of",
    "replacement_targets",
    "affected_fiscal_years",
    "official_url",
    "selected",
    "absolute_path",
    "file_sha256",
}


def _validate_annual_candidate_evidence(
    candidates: object,
    candidate_count: object,
) -> list[dict[str, object]]:
    if not isinstance(candidates, list) or not candidates or candidate_count != len(candidates):
        raise FetchSchemaError("annual-report candidates are invalid")

    validated: list[dict[str, object]] = []
    announcement_ids: set[str] = set()
    sequence_ids: set[int] = set()
    selected_years: set[int] = set()
    for candidate in candidates:
        if (
            not isinstance(candidate, dict)
            or not set(candidate) >= _REQUIRED_ANNUAL_CANDIDATE_FIELDS
            or not isinstance(candidate.get("selected"), bool)
            or not isinstance(candidate.get("sequence_id"), int)
            or candidate["sequence_id"] < 0
            or not isinstance(candidate.get("replacement_targets"), dict)
        ):
            raise FetchSchemaError("annual-report candidate metadata is invalid")
        announcement_id = str(candidate.get("announcement_id") or "")
        sequence_id = candidate["sequence_id"]
        if (
            not announcement_id
            or announcement_id in announcement_ids
            or sequence_id in sequence_ids
        ):
            raise FetchSchemaError("annual-report candidate metadata is invalid")
        announcement_ids.add(announcement_id)
        sequence_ids.add(sequence_id)

        selected = candidate["selected"]
        status = candidate.get("status")
        if selected != (status == "selected"):
            raise FetchSchemaError("annual-report candidate state is inconsistent")
        absolute_path = candidate.get("absolute_path")
        file_sha256 = candidate.get("file_sha256")
        if not selected:
            if absolute_path is not None or file_sha256 is not None:
                raise FetchSchemaError("annual-report candidate state is inconsistent")
            validated.append(candidate)
            continue

        fiscal_year = candidate.get("fiscal_year")
        source_path = Path(str(absolute_path or ""))
        expected_sha256 = str(file_sha256 or "")
        if (
            candidate.get("report_type") != "annual_report"
            or not isinstance(fiscal_year, int)
            or fiscal_year in selected_years
            or not source_path.is_absolute()
            or not source_path.is_file()
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or _sha256_path(source_path) != expected_sha256
            or not candidate.get("official_url")
        ):
            raise FetchSchemaError("annual-report selected candidate state or evidence is invalid")
        selected_years.add(fiscal_year)
        validated.append(candidate)

    if not selected_years:
        raise FetchSchemaError("annual-report manifest has no selected candidate")
    return validated


def _manifest_candidate_records(
    candidates: list[dict[str, object]],
    exchange: str,
) -> list[dict]:
    records: list[dict] = []
    for candidate in candidates:
        try:
            disclosed_at = datetime.fromisoformat(str(candidate.get("announcement_time") or ""))
        except ValueError as exc:
            raise FetchSchemaError("annual-report candidate announcement_time is invalid") from exc
        if disclosed_at.tzinfo is None:
            raise FetchSchemaError("annual-report candidate announcement_time is invalid")
        explicit_target_id = candidate.get("explicit_target_id")
        if exchange == "HK":
            record = {
                "NEWS_ID": candidate.get("announcement_id"),
                "TITLE": candidate.get("title"),
                "FILE_LINK": candidate.get("official_url"),
                "DATE_TIME": disclosed_at.astimezone(_HK_TIMEZONE).strftime("%d/%m/%Y %H:%M"),
                "targetAnnouncementId": explicit_target_id,
            }
            report_period_end = candidate.get("report_period_end")
            if report_period_end not in {None, "不适用"}:
                record["REPORT_PERIOD_END"] = report_period_end
        else:
            record = {
                "announcementId": candidate.get("announcement_id"),
                "announcementTitle": candidate.get("title"),
                "adjunctUrl": candidate.get("official_url"),
                "announcementTime": int(disclosed_at.timestamp() * 1000),
                "targetAnnouncementId": explicit_target_id,
            }
        records.append(record)
    return records


def _reconstructed_candidate_metadata(
    candidates: list[dict[str, object]],
    exchange: str,
    selection_years: int,
    cutoff: date,
    target_end_year: int | None,
) -> dict[str, dict[str, object]]:
    _, catalog = _classify_annual_catalog(
        _manifest_candidate_records(candidates, exchange),
        exchange,
        selection_years,
        cutoff,
        target_end_year,
        reject_malformed=True,
    )
    return {
        announcement.announcement_id: {
            "fiscal_year": announcement.year,
            "report_period_end": announcement.report_period_end,
            "sequence_id": announcement.sequence_id,
            "report_type": _annual_report_type(announcement),
            "status": announcement.status,
            "replacement_of": announcement.replacement_of,
            "replacement_targets": {
                str(year): target
                for year, target in sorted(announcement.replacement_targets.items())
            },
            "affected_fiscal_years": list(_announcement_years(announcement)),
            "selected": announcement.status == "selected",
        }
        for announcement in catalog
    }


def _selected_candidate_snapshots(
    candidates: list[dict[str, object]],
) -> list[tuple[Path, str, str]]:
    return [
        (
            Path(str(candidate.get("absolute_path") or "")),
            str(candidate.get("official_url") or ""),
            str(candidate.get("file_sha256") or ""),
        )
        for candidate in candidates
        if candidate.get("selected") is True
    ]


def _validate_promotion_pdf_snapshots(
    snapshots: list[tuple[Path, str, str]],
) -> None:
    for path, official_url, expected_sha256 in snapshots:
        try:
            file_size = path.stat().st_size
            with path.open("rb") as source:
                signature = source.read(5)
        except OSError as exc:
            raise FetchSchemaError("selected annual-report PDF changed before promotion") from exc
        if (
            file_size <= MIN_VALID_PDF_BYTES
            or signature != b"%PDF-"
            or _sha256_path(path) != expected_sha256
        ):
            raise FetchSchemaError(
                "selected annual-report PDF changed or is invalid before promotion"
            )
        _validate_selected_pdf_source(
            path,
            official_url,
            expected_sha256=expected_sha256,
        )


_HKEX_QUERY_STATIC_FILTERS = {
    "sortDir": "0",
    "sortByOptions": "DateTime",
    "category": "0",
    "market": "SEHK",
    "documentType": "-1",
    "title": "",
    "t1code": "-2",
    "t2Gcode": "-2",
    "t2code": "-2",
    "rowRange": "100",
}
_HKEX_QUERY_FIELDS = frozenset(
    {
        *_HKEX_QUERY_STATIC_FILTERS,
        "stockId",
        "fromDate",
        "toDate",
        "lang",
    }
)


_CNINFO_QUERY_STATIC_FILTERS = {
    "tabName": "fulltext",
    "pageSize": "30",
    "category": CATEGORY_ANNUAL,
}
_CNINFO_QUERY_FIELDS = frozenset(
    {
        *_CNINFO_QUERY_STATIC_FILTERS,
        "stock",
        "pageNum",
        "column",
        "seDate",
    }
)


def _validate_cninfo_query_filters(
    queries: list[dict[str, object]],
    *,
    ticker_code: str,
    org_id: str,
    exchange_column: str,
    date_window: str,
) -> None:
    expected_stock = f"{ticker_code},{org_id}"
    for page_number, query in enumerate(queries, start=1):
        fields = set(query)
        if fields not in {
            _CNINFO_QUERY_FIELDS,
            _CNINFO_QUERY_FIELDS | {"searchkey"},
        }:
            raise FetchSchemaError("annual-report query contract is invalid")
        if (
            any(query.get(field) != value for field, value in _CNINFO_QUERY_STATIC_FILTERS.items())
            or query.get("searchkey", "") != ""
            or query.get("stock") != expected_stock
            or query.get("column") != exchange_column
            or query.get("seDate") != date_window
        ):
            raise FetchSchemaError("annual-report query contract is invalid")
        if query.get("pageNum") != str(page_number):
            raise FetchSchemaError("cninfo annual-report page sequence is invalid")


def _validate_hkex_query_filters(
    queries: list[dict[str, object]],
    stock_id: str,
) -> None:
    if not queries:
        raise FetchSchemaError("annual-report query contract is invalid")
    root_language = queries[0].get("lang")
    if root_language not in {"EN", "ZH"}:
        raise FetchSchemaError("annual-report query contract is invalid")
    for query in queries:
        if (
            set(query) != _HKEX_QUERY_FIELDS
            or any(query.get(field) != value for field, value in _HKEX_QUERY_STATIC_FILTERS.items())
            or str(query.get("stockId") or "") != stock_id
            or query.get("lang") != root_language
        ):
            raise FetchSchemaError("annual-report query contract is invalid")
        try:
            start = datetime.strptime(
                str(query.get("fromDate") or ""),
                "%Y%m%d",
            ).date()
            end = datetime.strptime(
                str(query.get("toDate") or ""),
                "%Y%m%d",
            ).date()
        except ValueError as exc:
            raise FetchSchemaError("annual-report query contract is invalid") from exc
        if start > end:
            raise FetchSchemaError("annual-report query contract is invalid")


def _authenticate_hkex_stock_id(
    manifest: dict[str, object],
    ticker_code: str,
    stocklist_fetcher: Callable[[str], bytes],
) -> str:
    evidence = manifest.get("hkex_stock_id_evidence")
    if not isinstance(evidence, dict) or set(evidence) != {
        "source_url",
        "response_path",
        "response_sha256",
        "mapping",
    }:
        raise FetchSchemaError("HKEX stockId evidence is invalid")
    source_url = str(evidence.get("source_url") or "")
    response_path = Path(str(evidence.get("response_path") or ""))
    expected_sha256 = str(evidence.get("response_sha256") or "")
    mapping = evidence.get("mapping")
    if (
        source_url != HKEX_ACTIVE_STOCK_URL
        or not response_path.is_absolute()
        or not response_path.is_file()
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        or not isinstance(mapping, dict)
        or set(mapping) != {"issuer_code", "stock_id"}
        or mapping.get("issuer_code") != ticker_code
    ):
        raise FetchSchemaError("HKEX stockId evidence is invalid")
    try:
        immutable_body = response_path.read_bytes()
    except OSError as exc:
        raise FetchSchemaError("HKEX stockId evidence is invalid") from exc
    if _sha256_bytes(immutable_body) != expected_sha256:
        raise FetchSchemaError("HKEX stockId evidence hash differs")
    try:
        immutable_stock_id = resolve_hkex_stock_id(
            ticker_code,
            stocklist_bytes=immutable_body,
        )
    except (FetchSchemaError, ValueError) as exc:
        raise FetchSchemaError("HKEX stockId evidence mapping is invalid") from exc
    declared_stock_id = str(mapping.get("stock_id") or "")
    if (
        not declared_stock_id
        or declared_stock_id != immutable_stock_id
        or manifest.get("resolved_stock_id") != immutable_stock_id
    ):
        raise FetchSchemaError("HKEX stockId mapping differs from official evidence")

    live_body = stocklist_fetcher(source_url)
    try:
        live_stock_id = resolve_hkex_stock_id(
            ticker_code,
            stocklist_bytes=live_body,
        )
    except FetchSchemaError as exc:
        raise FetchSchemaError("live HKEX stockId evidence schema is invalid") from exc
    except ValueError as exc:
        raise FetchSchemaError("live HKEX stockId evidence mapping differs") from exc
    if live_stock_id != immutable_stock_id:
        raise FetchSchemaError("live HKEX stockId evidence mapping differs")
    return live_stock_id


def _reconstruct_cninfo_records(
    queries: list[dict[str, object]],
    bodies: list[bytes],
    expected_total: int,
) -> list[dict]:
    if len(queries) != len(bodies):
        raise FetchSchemaError("cninfo annual-report pagination response count differs")
    records: list[dict] = []
    seen_records: set[str] = set()
    official_total: int | None = None
    for index, body in enumerate(bodies):
        page_records = _parse_announcements(body)
        page_total = _parse_announcement_total(body)
        if page_total is None:
            raise FetchSchemaError("cninfo annual-report page omitted official total")
        if official_total is None:
            official_total = page_total
        elif page_total != official_total:
            raise FetchSchemaError("cninfo annual-report official total changed during pagination")
        if page_total != expected_total:
            raise FetchSchemaError("cninfo annual-report official total differs from manifest")
        for record in page_records:
            identity = str(
                record.get("announcementId")
                or record.get("adjunctUrl")
                or json.dumps(record, sort_keys=True)
            )
            if identity in seen_records:
                raise FetchSchemaError(
                    f"cninfo annual-report pagination returned duplicate announcement {identity}"
                )
            seen_records.add(identity)
            records.append(record)
        if len(records) > page_total:
            raise FetchSchemaError("cninfo annual-report pagination exceeded official total")
        is_last_page = index == len(bodies) - 1
        if len(records) == page_total and not is_last_page:
            raise FetchSchemaError(
                "cninfo annual-report pagination contains pages after termination"
            )
        if len(records) < page_total and is_last_page:
            raise FetchSchemaError("cninfo annual-report pagination ended before official total")
    if official_total is None or len(records) != official_total:
        raise FetchSchemaError("cninfo annual-report pagination completeness differs")
    return records


def _annual_selection_contract(
    manifest: dict[str, object],
    query_url: str,
    queries: list[dict[str, object]],
    exchange: str,
    ticker_code: str,
    as_of: date,
) -> tuple[int, int | None]:
    selection_years = manifest.get("selection_years")
    target_end_year = manifest.get("target_end_year")
    if (
        not isinstance(selection_years, int)
        or selection_years < 1
        or (target_end_year is not None and not isinstance(target_end_year, int))
    ):
        raise FetchSchemaError("annual-report selection contract is invalid")
    expected_start = (
        date(target_end_year - selection_years, 1, 1)
        if target_end_year is not None
        else _subtract_years(as_of, selection_years + 1)
    )
    if exchange == "HK":
        resolved_stock_id = str(manifest.get("resolved_stock_id") or "")
        _validate_hkex_query_filters(queries, resolved_stock_id)
        if (
            query_url != HKEX_SEARCH_URL
            or manifest.get("query_issuer_code") != ticker_code
            or not resolved_stock_id
        ):
            raise FetchSchemaError("annual-report query contract is invalid")
        root_query = queries[0]
        query_window = (
            str(root_query.get("fromDate") or ""),
            str(root_query.get("toDate") or ""),
        )
        expected_window = (
            expected_start.strftime("%Y%m%d"),
            as_of.strftime("%Y%m%d"),
        )
    else:
        expected_column = _exchange_column(exchange)
        resolved_org_id = str(manifest.get("resolved_org_id") or "")
        expected_window_text = f"{expected_start.isoformat()}~{as_of.isoformat()}"
        if query_url != ANNOUNCEMENT_QUERY_URL or not resolved_org_id:
            raise FetchSchemaError("annual-report query contract is invalid")
        _validate_cninfo_query_filters(
            queries,
            ticker_code=ticker_code,
            org_id=resolved_org_id,
            exchange_column=expected_column,
            date_window=expected_window_text,
        )
        root_query = queries[0]
        raw_window = str(root_query.get("seDate") or "")
        query_window = tuple(raw_window.split("~", 1))
        expected_window = (expected_start.isoformat(), as_of.isoformat())
    if query_window != expected_window:
        raise FetchSchemaError("annual-report selection query window is invalid")
    return selection_years, target_end_year


def _reconstruct_hkex_records(
    queries: list[dict[str, object]],
    bodies: list[bytes],
) -> list[dict]:
    def visit(index: int, expected_query: dict[str, object]) -> tuple[list[dict], int]:
        if index >= len(queries) or queries[index] != expected_query:
            raise FetchSchemaError("live HKEX annual catalog query tree differs")
        records = _parse_hkex_announcements(bodies[index])
        try:
            row_range = int(str(expected_query["rowRange"]))
            start = datetime.strptime(str(expected_query["fromDate"]), "%Y%m%d").date()
            end = datetime.strptime(str(expected_query["toDate"]), "%Y%m%d").date()
        except (KeyError, ValueError) as exc:
            raise FetchSchemaError("live HKEX annual catalog query is invalid") from exc
        next_index = index + 1
        if len(records) < row_range:
            return records, next_index
        if start >= end:
            raise FetchSchemaError("live HKEX annual catalog remains truncated")

        midpoint = start + (end - start) // 2
        left_query = dict(expected_query)
        left_query["fromDate"] = start.strftime("%Y%m%d")
        left_query["toDate"] = midpoint.strftime("%Y%m%d")
        right_query = dict(expected_query)
        right_query["fromDate"] = (midpoint + timedelta(days=1)).strftime("%Y%m%d")
        right_query["toDate"] = end.strftime("%Y%m%d")
        left_records, next_index = visit(next_index, left_query)
        right_records, next_index = visit(next_index, right_query)
        combined: list[dict] = []
        seen: set[str] = set()
        for record in [*left_records, *right_records]:
            identity = str(
                record.get("NEWS_ID")
                or record.get("news_id")
                or record.get("FILE_LINK")
                or record.get("file_link")
                or json.dumps(record, sort_keys=True)
            )
            if identity not in seen:
                seen.add(identity)
                combined.append(record)
        return combined, next_index

    records, consumed = visit(0, queries[0])
    if consumed != len(queries):
        raise FetchSchemaError("live HKEX annual catalog query tree is incomplete")
    return records


def _live_annual_catalog_metadata(
    queries: list[dict[str, object]],
    bodies: list[bytes],
    exchange: str,
    selection_years: int,
    cutoff: date,
    target_end_year: int | None,
    pdf_fetcher: Callable[[str], bytes],
    official_result_total: int,
) -> tuple[dict[str, dict[str, object]], dict[str, bytes]]:
    if len(queries) != len(bodies):
        raise FetchSchemaError("live official annual catalog response count differs")
    if exchange == "HK":
        raw_records = _reconstruct_hkex_records(queries, bodies)
    else:
        raw_records = _reconstruct_cninfo_records(
            queries,
            bodies,
            official_result_total,
        )
    live_pdf_bodies: dict[str, bytes] = {}

    def resolve_hk_period(announcement: Announcement) -> date:
        body = live_pdf_bodies.get(announcement.adjunct_url)
        if body is None:
            body = pdf_fetcher(announcement.adjunct_url)
            if len(body) <= MIN_VALID_PDF_BYTES or not body.startswith(b"%PDF-"):
                raise FetchSchemaError("live official HK annual-report PDF is invalid")
            live_pdf_bodies[announcement.adjunct_url] = body
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".pdf",
                delete=False,
            ) as sink:
                sink.write(body)
                sink.flush()
                os.fsync(sink.fileno())
                temporary = Path(sink.name)
            return extract_hk_report_period_end(temporary)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    _, catalog = _classify_annual_catalog(
        raw_records,
        exchange,
        selection_years,
        cutoff,
        target_end_year,
        reject_malformed=True,
        period_end_resolver=resolve_hk_period if exchange == "HK" else None,
    )

    metadata: dict[str, dict[str, object]] = {}
    for announcement in catalog:
        announcement_id = announcement.announcement_id
        row = {
            "fiscal_year": announcement.year,
            "report_period_end": announcement.report_period_end,
            "announcement_time": announcement.announcement_time.isoformat(),
            "announcement_id": announcement_id,
            "sequence_id": announcement.sequence_id,
            "title": announcement.title,
            "report_type": _annual_report_type(announcement),
            "status": announcement.status,
            "replacement_of": announcement.replacement_of,
            "replacement_targets": {
                str(year): target
                for year, target in sorted(announcement.replacement_targets.items())
            },
            "official_url": announcement.adjunct_url,
            "affected_fiscal_years": list(_announcement_years(announcement)),
            "selected": announcement.status == "selected",
        }
        existing = metadata.get(announcement_id)
        if existing is not None and existing != row:
            raise FetchSchemaError("live official annual catalog contains conflicting metadata")
        metadata[announcement_id] = row
    return metadata, live_pdf_bodies


def revalidate_annual_manifest(
    manifest_path: Path,
    *,
    stocklist_fetcher: Callable[[str], bytes] = _http_get,
    catalog_fetcher: Callable[[str, str, dict[str, object]], bytes] = (_fetch_live_annual_catalog),
    pdf_fetcher: Callable[[str], bytes] = _http_get,
) -> str:
    """Re-fetch the official catalog and selected PDFs bound by a manifest."""
    try:
        original_body = manifest_path.read_bytes()
        manifest = json.loads(original_body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FetchSchemaError(f"cannot read annual-report manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise FetchSchemaError("annual-report manifest must be an object")
    ticker = str(manifest.get("ticker") or "")
    try:
        canonical = canonical_ticker(ticker)
        as_of = date.fromisoformat(str(manifest.get("AS_OF") or ""))
    except (FetchSchemaError, ValueError) as exc:
        raise FetchSchemaError("annual-report manifest identity is invalid") from exc
    exchange = str(manifest.get("exchange") or "")
    ticker_code, ticker_exchange = canonical.rsplit(".", 1)
    if (
        exchange not in {"SH", "SZ", "HK"}
        or exchange != ticker_exchange
        or manifest.get("查询发行人代码") != ticker_code
    ):
        raise FetchSchemaError("annual-report manifest exchange is invalid")
    query_url = str(manifest.get("official_query_url") or "")
    raw_query_params = manifest.get("official_query_params")
    queries = raw_query_params if isinstance(raw_query_params, list) else [raw_query_params]
    if not query_url or not queries or not all(isinstance(query, dict) for query in queries):
        raise FetchSchemaError("annual-report query contract is invalid")
    typed_queries = [query for query in queries if isinstance(query, dict)]
    selection_years, target_end_year = _annual_selection_contract(
        manifest,
        query_url,
        typed_queries,
        exchange,
        ticker_code,
        as_of,
    )
    if exchange == "HK":
        authenticated_stock_id = _authenticate_hkex_stock_id(
            manifest,
            ticker_code,
            stocklist_fetcher,
        )
        if manifest.get("resolved_stock_id") != authenticated_stock_id:
            raise FetchSchemaError("HKEX stockId mapping differs")
    candidates = _validate_annual_candidate_evidence(
        manifest.get("candidates"),
        manifest.get("candidate_count"),
    )
    live_bodies = [catalog_fetcher(query_url, exchange, query) for query in typed_queries]
    if _sha256_bytes(b"".join(live_bodies)) != manifest.get("response_sha256"):
        raise FetchSchemaError("live official annual catalog hash differs")

    official_result_total = manifest.get("official_result_total")
    if not isinstance(official_result_total, int):
        raise FetchSchemaError("annual-report candidates are invalid")
    live_metadata, live_pdf_bodies = _live_annual_catalog_metadata(
        typed_queries,
        live_bodies,
        exchange,
        selection_years,
        as_of,
        target_end_year,
        pdf_fetcher,
        official_result_total,
    )
    candidate_ids = {str(candidate.get("announcement_id") or "") for candidate in candidates}
    if (
        len(candidate_ids) != len(candidates)
        or candidate_ids != set(live_metadata)
        or official_result_total != len(live_metadata)
    ):
        raise FetchSchemaError("annual-report catalog metadata set differs")
    for candidate in candidates:
        live_row = live_metadata[str(candidate["announcement_id"])]
        comparable_fields = {
            "fiscal_year",
            "announcement_time",
            "announcement_id",
            "title",
            "official_url",
            "affected_fiscal_years",
        }
        if any(candidate.get(field) != live_row[field] for field in comparable_fields):
            raise FetchSchemaError("annual-report catalog metadata differs")
        state_fields = {
            "sequence_id",
            "report_type",
            "status",
            "replacement_of",
            "replacement_targets",
            "selected",
        }
        if any(candidate.get(field) != live_row[field] for field in state_fields):
            raise FetchSchemaError("annual-report candidate state differs")
        if candidate.get("report_period_end") != live_row["report_period_end"]:
            raise FetchSchemaError("annual-report catalog metadata differs")
        announcement_time = candidate.get("announcement_time")
        try:
            disclosed_at = datetime.fromisoformat(str(announcement_time))
        except ValueError as exc:
            raise FetchSchemaError("annual-report candidate announcement_time is invalid") from exc
        if disclosed_at.date() > as_of:
            raise FetchSchemaError("annual-report candidate is after AS_OF")
        if candidate.get("selected") is not True:
            continue
        expected_sha256 = str(candidate.get("file_sha256") or "")
        official_url = str(candidate.get("official_url") or "")
        live_pdf_body = live_pdf_bodies.get(official_url)
        if live_pdf_body is None:
            live_pdf_body = pdf_fetcher(official_url)
        if _sha256_bytes(live_pdf_body) != expected_sha256:
            raise FetchSchemaError("live official annual-report PDF hash differs")

    if manifest_path.read_bytes() != original_body:
        raise FetchSchemaError("annual-report manifest changed during revalidation")
    return _sha256_bytes(original_body)


def promote_annual_manifest(source_path: Path, canonical_path: Path) -> Path:
    """Publish a reviewed temporary manifest without overwriting evidence."""
    try:
        source_body = source_path.read_bytes()
        payload = json.loads(source_body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FetchSchemaError(f"cannot read temporary annual manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise FetchSchemaError("temporary annual manifest must be an object")
    required = {
        "ticker",
        "exchange",
        "AS_OF",
        "查询发行人代码",
        "candidates",
    }
    if not required.issubset(payload):
        raise FetchSchemaError("temporary annual manifest lacks identity fields")
    candidates = _validate_annual_candidate_evidence(
        payload["candidates"],
        payload.get("candidate_count"),
    )
    try:
        canonical_identity = canonical_ticker(str(payload["ticker"]))
        as_of = date.fromisoformat(str(payload["AS_OF"]))
    except (FetchSchemaError, ValueError) as exc:
        raise FetchSchemaError("temporary annual manifest identity is invalid") from exc
    ticker_code, exchange = canonical_identity.rsplit(".", 1)
    if payload.get("exchange") != exchange or payload.get("查询发行人代码") != ticker_code:
        raise FetchSchemaError("temporary annual manifest identity is invalid")
    selection_years = payload.get("selection_years")
    target_end_year = payload.get("target_end_year")
    if (
        not isinstance(selection_years, int)
        or selection_years < 1
        or (target_end_year is not None and not isinstance(target_end_year, int))
    ):
        raise FetchSchemaError("temporary annual manifest selection is invalid")
    reconstructed = _reconstructed_candidate_metadata(
        candidates,
        exchange,
        selection_years,
        as_of,
        target_end_year,
    )
    candidate_ids = {str(candidate.get("announcement_id") or "") for candidate in candidates}
    reconstructed_fields = {
        "fiscal_year",
        "report_period_end",
        "sequence_id",
        "report_type",
        "status",
        "replacement_of",
        "replacement_targets",
        "affected_fiscal_years",
        "selected",
    }
    if candidate_ids != set(reconstructed) or any(
        any(
            candidate.get(field) != reconstructed[str(candidate["announcement_id"])][field]
            for field in reconstructed_fields
        )
        for candidate in candidates
    ):
        raise FetchSchemaError("temporary annual manifest candidate state differs")
    selected_snapshots = _selected_candidate_snapshots(candidates)
    _validate_promotion_pdf_snapshots(selected_snapshots)
    expected_name = f"annual-reports-{payload['AS_OF']}.json"
    if canonical_path.name != expected_name:
        raise FetchSchemaError(f"canonical annual manifest must be named {expected_name}")

    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    digest = _sha256_bytes(source_body)
    content_path = canonical_path.with_name(
        f"{canonical_path.stem}-{digest}{canonical_path.suffix}"
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=canonical_path.parent,
            prefix=f".{canonical_path.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(source_body)
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        for candidate in (canonical_path, content_path):
            _validate_promotion_pdf_snapshots(selected_snapshots)
            if candidate.exists():
                if candidate.read_bytes() == source_body:
                    return candidate.resolve()
                continue
            try:
                os.link(temporary, candidate)
            except FileExistsError:
                if candidate.read_bytes() == source_body:
                    return candidate.resolve()
                continue
            try:
                _validate_promotion_pdf_snapshots(selected_snapshots)
            except FetchSchemaError:
                candidate.unlink(missing_ok=True)
                raise
            if source_path.read_bytes() != source_body:
                candidate.unlink(missing_ok=True)
                raise FetchSchemaError("temporary annual manifest changed during promotion")
            return candidate.resolve()
        raise FetchSchemaError("annual manifest content-addressed path contains different evidence")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate_selected_pdf_source(
    source: Path,
    expected_official_url: str,
    *,
    expected_sha256: str | None = None,
) -> None:
    source_path = source.with_suffix(source.suffix + ".source.json")
    try:
        metadata = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchSchemaError(
            f"Selected PDF source metadata is missing or invalid: {source_path}"
        ) from exc
    actual_sha256 = expected_sha256 or _sha256_path(source)
    if (
        not isinstance(metadata, dict)
        or metadata.get("adjunct_url") != expected_official_url
        or metadata.get("sha256") != actual_sha256
    ):
        raise FetchSchemaError(
            "Selected PDF source metadata does not match the selected "
            f"announcement or file bytes: {source}"
        )


def _persist_pdf_source_metadata(
    pdf_path: Path,
    official_url: str,
    sha256: str,
) -> None:
    source_path = pdf_path.with_suffix(pdf_path.suffix + ".source.json")
    body = (
        json.dumps(
            {
                "adjunct_url": official_url,
                "sha256": sha256,
            },
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    if source_path.exists():
        if source_path.read_bytes() != body:
            raise FetchSchemaError(
                f"Immutable annual-report source metadata is corrupt: {source_path}"
            )
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=source_path.parent,
            prefix=f".{source_path.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(body)
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        try:
            os.link(temporary, source_path)
        except FileExistsError as exc:
            if source_path.read_bytes() != body:
                raise FetchSchemaError(
                    "Immutable annual-report source metadata already exists "
                    f"with different evidence: {source_path}"
                ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _persist_immutable_annual_pdf(
    out_dir: Path,
    fiscal_year: int,
    source: Path,
    *,
    expected_official_url: str | None = None,
) -> Path:
    digest = _sha256_path(source)
    versions_dir = out_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    destination = versions_dir / f"年报-{fiscal_year}-{digest}.pdf"
    if destination.exists():
        if _sha256_path(destination) != digest:
            raise FetchSchemaError(f"Immutable annual-report path is corrupt: {destination}")
        if expected_official_url is not None:
            _validate_selected_pdf_source(
                source,
                expected_official_url,
                expected_sha256=digest,
            )
            _persist_pdf_source_metadata(
                destination,
                expected_official_url,
                digest,
            )
        return destination.resolve()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=versions_dir,
            prefix=f".{destination.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            temporary = Path(sink.name)
        shutil.copy2(source, temporary)
        copied_digest = _sha256_path(temporary)
        if copied_digest != digest:
            raise FetchSchemaError(f"Source PDF changed during immutable copy: {source}")
        if expected_official_url is not None:
            _validate_selected_pdf_source(
                source,
                expected_official_url,
                expected_sha256=copied_digest,
            )
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            try:
                existing_digest = _sha256_path(destination)
            except OSError as read_exc:
                raise FetchSchemaError(
                    "Concurrent immutable annual-report destination disappeared "
                    f"during publication: {destination}"
                ) from read_exc
            if existing_digest != digest:
                raise FetchSchemaError(
                    "Immutable annual-report destination already exists with "
                    f"different bytes: {destination}"
                ) from exc
        if _sha256_path(destination) != digest:
            raise FetchSchemaError(
                f"Immutable annual-report copy failed hash verification: {destination}"
            )
        if _sha256_path(source) != digest:
            raise FetchSchemaError(
                f"Source PDF changed before immutable publication completed: {source}"
            )
        if expected_official_url is not None:
            _validate_selected_pdf_source(
                source,
                expected_official_url,
                expected_sha256=digest,
            )
            _persist_pdf_source_metadata(
                destination,
                expected_official_url,
                digest,
            )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination.resolve()


def download_pdf(adjunct_url: str, dest: Path) -> bool:
    """Download `PDF_BASE_URL + adjunct_url` to `dest`. Idempotent.

    Returns True if a download was performed, False if a valid file and its
    source sidecar already match `adjunct_url`."""
    source_path = dest.with_suffix(dest.suffix + ".source.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = urllib.parse.urljoin(PDF_BASE_URL, adjunct_url.lstrip("/"))
    body = _http_get(url)
    if len(body) <= MIN_VALID_PDF_BYTES:
        raise FetchSchemaError(
            f"Downloaded file at {url} is {len(body)} bytes "
            f"(<= {MIN_VALID_PDF_BYTES}); refusing to save as PDF."
        )
    if not body.startswith(b"%PDF-"):
        raise FetchSchemaError(f"Downloaded file at {url} has no PDF signature")
    body_sha256 = _sha256_bytes(body)
    resolved_dest = dest.resolve()
    with _download_locks_guard:
        thread_lock = _download_locks.setdefault(
            resolved_dest,
            threading.Lock(),
        )
    with thread_lock:
        lock_path = dest.with_name(f".{dest.name}.download.lock")
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            existing_matches = False
            if dest.exists() and dest.stat().st_size > MIN_VALID_PDF_BYTES and source_path.exists():
                try:
                    source = json.loads(source_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    source = {}
                existing_matches = bool(
                    source.get("adjunct_url") == adjunct_url
                    and source.get("sha256") == _sha256_path(dest)
                )
            if existing_matches and body_sha256 == _sha256_path(dest):
                return False

            pdf_temporary: Path | None = None
            source_temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=dest.parent,
                    prefix=f".{dest.name}.",
                    suffix=".partial",
                    delete=False,
                ) as sink:
                    sink.write(body)
                    sink.flush()
                    os.fsync(sink.fileno())
                    pdf_temporary = Path(sink.name)
                sidecar_body = (
                    json.dumps(
                        {
                            "adjunct_url": adjunct_url,
                            "sha256": body_sha256,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode("utf-8")
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=source_path.parent,
                    prefix=f".{source_path.name}.",
                    suffix=".partial",
                    delete=False,
                ) as sink:
                    sink.write(sidecar_body)
                    sink.flush()
                    os.fsync(sink.fileno())
                    source_temporary = Path(sink.name)
                os.replace(pdf_temporary, dest)
                pdf_temporary = None
                os.replace(source_temporary, source_path)
                source_temporary = None
            finally:
                if pdf_temporary is not None:
                    pdf_temporary.unlink(missing_ok=True)
                if source_temporary is not None:
                    source_temporary.unlink(missing_ok=True)
            return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg, flush=True)


def _load_listing_profile_bundle(
    bundle_path: Path,
    ticker: str,
    expected_listing_date: date,
) -> dict[str, object]:
    if not bundle_path.is_absolute() or not bundle_path.is_file():
        raise FetchSchemaError("--listing-profile-bundle must be an existing absolute path")
    try:
        bundle_body = bundle_path.read_bytes()
        bundle = json.loads(bundle_body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FetchSchemaError(f"listing profile bundle is invalid: {exc}") from exc
    if not isinstance(bundle, dict):
        raise FetchSchemaError("listing profile bundle identity or listing_date does not match")
    try:
        requested_ticker = canonical_ticker(ticker)
        primary_ticker = canonical_ticker(str(bundle.get("ticker") or ""))
        primary_code, primary_exchange = primary_ticker.rsplit(".", 1)
        primary_listing_date = date.fromisoformat(str(bundle.get("listing_date") or ""))
    except (FetchSchemaError, ValueError) as exc:
        raise FetchSchemaError(
            "listing profile bundle identity or listing_date does not match"
        ) from exc
    if (
        bundle.get("exchange") != primary_exchange
        or bundle.get("query_issuer_code") != primary_code
    ):
        raise FetchSchemaError("listing profile bundle identity or listing_date does not match")
    listing_profile = bundle.get("listing_profile")
    if not isinstance(listing_profile, dict):
        raise FetchSchemaError("listing profile bundle lacks listing_profile")
    source_path = Path(str(listing_profile.get("source_file") or ""))
    if not source_path.is_absolute() or not source_path.is_file():
        raise FetchSchemaError("listing profile source_file is invalid")
    try:
        as_of = date.fromisoformat(str(bundle.get("AS_OF") or ""))
        validated_profile, validated_listing_date = build_event_manifest._validate_listing_profile(
            bundle,
            primary_exchange,
            primary_code,
            as_of,
            build_event_manifest._fetch_official_roster,
        )
    except (ValueError, build_event_manifest.ManifestError) as exc:
        raise FetchSchemaError(f"official listing profile evidence is invalid: {exc}") from exc
    if validated_listing_date != primary_listing_date:
        raise FetchSchemaError("official listing profile listing_date does not match")
    requested_code, requested_exchange = requested_ticker.rsplit(".", 1)
    listing_codes = validated_profile.get("listing_codes")
    listing_dates = validated_profile.get("listing_dates")
    try:
        authenticated_listing_date = date.fromisoformat(str(listing_dates[requested_exchange]))
    except (KeyError, TypeError, ValueError) as exc:
        raise FetchSchemaError(
            "listing profile bundle identity or listing_date does not match"
        ) from exc
    if (
        not isinstance(listing_codes, dict)
        or listing_codes.get(requested_exchange) != requested_code
        or authenticated_listing_date != expected_listing_date
    ):
        raise FetchSchemaError("listing profile bundle identity or listing_date does not match")
    listing_statuses = validated_profile.get("listing_statuses")
    delisting_dates = validated_profile.get("delisting_dates")
    source_sha256 = _sha256_path(source_path)
    return {
        "bundle_path": str(bundle_path),
        "bundle_sha256": _sha256_bytes(bundle_body),
        "source_file": str(source_path),
        "source_sha256": source_sha256,
        "source_url": validated_profile.get("source_url"),
        "query_params": validated_profile.get("query_params"),
        "response_schema": validated_profile.get("response_schema"),
        "response_adapter": validated_profile.get("response_adapter", {}),
        "listing_status": (
            listing_statuses.get(requested_exchange)
            if isinstance(listing_statuses, dict)
            else validated_profile.get("listing_status")
        ),
        "delisting_date": (
            delisting_dates.get(requested_exchange)
            if isinstance(delisting_dates, dict)
            else validated_profile.get("delisting_date")
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch 年报 + 招股说明书 PDFs from cninfo (巨潮资讯网) for an A-share ticker.",
    )
    parser.add_argument("ticker", nargs="?", help="e.g. 600519.SH or 000001.SZ")
    parser.add_argument(
        "--revalidate",
        type=Path,
        default=None,
        help="Re-fetch and verify one existing annual-report manifest.",
    )
    parser.add_argument(
        "--promote",
        type=Path,
        default=None,
        help="Publish one reviewed temporary annual-report manifest.",
    )
    parser.add_argument(
        "--canonical-out",
        type=Path,
        default=None,
        help="Canonical annual-report manifest path used with --promote.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Fetch the most recent N 年报 (default 5).",
    )
    parser.add_argument(
        "--include-prospectus",
        action="store_true",
        help="Also fetch 招股说明书 (A-share only; ignored for HK).",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "zh"],
        default="en",
        help="Language preference for HKEX filings (default: en). Ignored for A-share.",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="Exclude announcements published after this research cutoff.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        metavar="YYYY",
        help="Do not select fiscal years after YYYY.",
    )
    parser.add_argument(
        "--listing-date",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="Official exchange listing date used to prove history coverage.",
    )
    parser.add_argument(
        "--listing-profile-bundle",
        type=Path,
        default=None,
        help="Absolute collector bundle that proves the official listing date.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default data/filings/<ticker>/).",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=None,
        help="Write the annual-report manifest to this explicit path.",
    )
    args = parser.parse_args(argv)

    if args.promote is not None:
        if args.ticker is not None or args.revalidate is not None or args.canonical_out is None:
            _print(
                "error: --promote requires --canonical-out and cannot be "
                "combined with ticker or --revalidate"
            )
            return 2
        try:
            _print(promote_annual_manifest(args.promote, args.canonical_out))
            return 0
        except (FetchSchemaError, OSError) as exc:
            _print(f"error: {exc}")
            return 2
    if args.canonical_out is not None:
        _print("error: --canonical-out requires --promote")
        return 2
    if args.revalidate is not None:
        if args.ticker is not None:
            _print("error: ticker cannot be combined with --revalidate")
            return 2
        try:
            _print(revalidate_annual_manifest(args.revalidate))
            return 0
        except (FetchSchemaError, OSError, urllib.error.URLError) as exc:
            _print(f"error: {exc}")
            return 2
    if args.ticker is None:
        _print("error: ticker is required unless --revalidate is used")
        return 2

    try:
        normalized_ticker = canonical_ticker(args.ticker)
        code, exchange = normalized_ticker.rsplit(".", 1)
    except ValueError as e:
        _print(f"error: {e}")
        return 2

    out_dir: Path = args.out or Path("data/filings") / f"{code}.{exchange}"
    out_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    prospectus: list[Announcement] = []
    annual_catalog: list[Announcement] = []
    annual_trace: dict[str, object] = {}
    if args.listing_date is not None:
        if args.listing_profile_bundle is None:
            _print(
                "error: --listing-date requires "
                "--listing-profile-bundle <absolute-official-query-bundle.json>"
            )
            return 2
        try:
            annual_trace["listing_profile"] = _load_listing_profile_bundle(
                args.listing_profile_bundle,
                normalized_ticker,
                args.listing_date,
            )
        except (FetchSchemaError, ValueError) as exc:
            _print(f"error: {exc}")
            return 2

    if exchange == "HK":
        _print(f"[1/3] source = HKEX (披露易); stockId={code.zfill(5)} lang={args.lang}")
        _print(f"[2/3] searching Annual Report (latest {args.years} fiscal years)")
        try:
            with tempfile.TemporaryDirectory(prefix="ah-hk-period-") as period_dir:
                period_root = Path(period_dir)

                def resolve_period(ann: Announcement) -> date:
                    candidate = (
                        period_root / f"{hashlib.sha256(ann.adjunct_url.encode()).hexdigest()}.pdf"
                    )
                    download_pdf(ann.adjunct_url, candidate)
                    return extract_hk_report_period_end(candidate)

                annuals = search_hkex_annual_reports(
                    code,
                    args.years,
                    prefer_lang=args.lang,
                    as_of=args.as_of,
                    end_year=args.end_year,
                    listing_date=args.listing_date,
                    catalog_out=annual_catalog,
                    trace_out=annual_trace,
                    period_end_resolver=resolve_period,
                )
        except (FetchSchemaError, urllib.error.URLError) as e:
            _print(f"error: HKEX annual-report search failed: {e}")
            return 2
        if args.include_prospectus:
            _print("       note: --include-prospectus ignored for HK (not supported in v1)")
    else:
        _print(f"[1/4] resolving orgId for {code}.{exchange}")
        try:
            org_id = resolve_org_id(code)
        except (FetchSchemaError, ValueError, urllib.error.URLError) as e:
            _print(f"error: could not resolve orgId: {e}")
            return 2
        _print(f"       orgId={org_id}")

        _print(f"[2/4] searching 年报 (latest {args.years} fiscal years)")
        try:
            annuals = search_annual_reports(
                org_id,
                code,
                exchange,
                args.years,
                as_of=args.as_of,
                end_year=args.end_year,
                listing_date=args.listing_date,
                catalog_out=annual_catalog,
                trace_out=annual_trace,
            )
        except (FetchSchemaError, urllib.error.URLError) as e:
            _print(f"error: 年报 search failed: {e}")
            return 2

        if args.include_prospectus:
            _print("[3/4] searching 招股说明书")
            try:
                prospectus = search_prospectus(org_id, code, exchange, as_of=args.as_of)
            except (FetchSchemaError, urllib.error.URLError) as e:
                _print(f"warn: 招股说明书 search failed: {e}")
                failures.append(f"prospectus search: {e}")
            for ann in prospectus:
                _print(
                    f"       - {ann.title} ({ann.announcement_date.isoformat()}) "
                    f"-> {ann.adjunct_url}"
                )
        else:
            _print("[3/4] skipping 招股说明书 (use --include-prospectus)")

    if not annual_catalog:
        _print("error: official annual-report catalog is empty; refusing incomplete run")
        return 2
    if args.end_year is not None and args.end_year not in {ann.year for ann in annuals}:
        _print(
            f"error: explicit target fiscal year {args.end_year} is unavailable; "
            "refusing to backfill an older report"
        )
        return 2
    if not annuals:
        _print("       no valid 年报 found — check ticker / years window")
        failures.append("no valid annual report selected")
    for ann in annuals:
        _print(f"       - {ann.title} ({ann.announcement_date.isoformat()}) -> {ann.adjunct_url}")

    step_label = "[3/3]" if exchange == "HK" else "[4/4]"
    _print(f"{step_label} downloading to {out_dir}")
    downloaded = 0
    skipped = 0
    selected_paths: dict[int, Path] = {}
    for ann in annuals:
        assert ann.year is not None
        dest = out_dir / f"年报-{ann.year}.pdf"
        try:
            if download_pdf(ann.adjunct_url, dest):
                _print(f"       wrote {dest.name} ({dest.stat().st_size} bytes)")
                downloaded += 1
            else:
                _print(f"       skip  {dest.name} (already present)")
                skipped += 1
            selected_paths[ann.year] = dest
        except (FetchSchemaError, urllib.error.URLError, OSError) as e:
            msg = f"{dest.name}: {e}"
            _print(f"       FAIL  {msg}")
            failures.append(msg)

    if annual_catalog and not failures:
        manifest_path = write_annual_manifest(
            out_dir,
            normalized_ticker,
            args.as_of or date.today(),
            annual_catalog,
            selected_paths,
            annual_trace,
            manifest_out=args.manifest_out,
        )
        _print(f"       manifest {manifest_path}")

    for i, ann in enumerate(prospectus[:1]):  # only the canonical, latest one
        _ = i  # keep looping structure explicit
        dest = out_dir / "招股说明书.pdf"
        try:
            if download_pdf(ann.adjunct_url, dest):
                _print(f"       wrote {dest.name} ({dest.stat().st_size} bytes)")
                downloaded += 1
            else:
                _print(f"       skip  {dest.name} (already present)")
                skipped += 1
        except (FetchSchemaError, urllib.error.URLError, OSError) as e:
            msg = f"{dest.name}: {e}"
            _print(f"       FAIL  {msg}")
            failures.append(msg)

    _print("")
    _print(f"summary: downloaded={downloaded} skipped={skipped} failed={len(failures)}")
    if failures:
        _print("failures:")
        for f in failures:
            _print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
