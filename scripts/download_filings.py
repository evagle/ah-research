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
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOCK_LIST_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
ANNOUNCEMENT_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE_URL = "http://static.cninfo.com.cn/"

# HKEX (香港联交所 披露易) — public title search, same backend the
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

# cninfo category codes. `category_ndbg_szsh` = 年度报告 (annual reports,
# Shanghai + Shenzhen). Prospectuses are fetched via title keyword search
# rather than category — the category filters proved noisy.
CATEGORY_ANNUAL = "category_ndbg_szsh"

# Title filters: exclude abbreviated / English / revised / errata versions.
_RE_EXCLUDE_TITLE = re.compile(r"摘要|英文版|英文稿|修订版|更正版|更正后|取消|已取消|补充公告")
_RE_ANNUAL_TITLE = re.compile(r"(\d{4})\s*年\s*年度?\s*报告")
_RE_PROSPECTUS_TITLE = re.compile(r"^招股说明书$")

# HKEX title filters. t2code=40100 already narrows to annual reports, but
# defensively reject common look-alikes (summary / interim / supplement).
_RE_EXCLUDE_TITLE_HK = re.compile(
    r"summary|interim|quarterly|supplement|circular|announcement|notice|"
    r"摘要|中期|季度|补充|通函|通知|公告",
    re.IGNORECASE,
)
# Plain 4-digit year fallback for HK titles ("Annual Report 2023",
# "2023年年報"). Uses digit-lookaround (not \b) since Python's \b treats
# CJK characters as word chars — `\b2023\b` fails on "2023年".
_RE_YEAR_4DIGIT = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")


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


@dataclass(frozen=True)
class Announcement:
    title: str
    adjunct_url: str
    announcement_date: date
    year: int | None  # fiscal year end (from title like "2024年年度报告")


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


def _epoch_ms_to_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).date()


def _extract_year(title: str) -> int | None:
    m = _RE_ANNUAL_TITLE.search(title)
    if m:
        return int(m.group(1))
    return None


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


def _to_announcement(raw: dict) -> Announcement | None:
    """Validate + convert one cninfo record. Returns None on missing fields."""
    title = raw.get("announcementTitle")
    url = raw.get("adjunctUrl")
    ts = raw.get("announcementTime")
    if not title or not url or ts is None:
        return None
    if not isinstance(ts, int):
        return None
    return Announcement(
        title=str(title),
        adjunct_url=str(url),
        announcement_date=_epoch_ms_to_date(ts),
        year=_extract_year(str(title)),
    )


def search_annual_reports(
    org_id: str,
    code: str,
    exchange: str,
    years: int,
    *,
    raw_response: bytes | None = None,
) -> list[Announcement]:
    """Return de-duplicated 年报 announcements for the N most recent fiscal years.

    When multiple 年报 exist for the same year (original + 更正/revision), the
    latest by announcement date wins. 摘要 / 英文版 / 修订版 are filtered out.

    `raw_response` is injectable for tests."""
    today = date.today()
    start = today.replace(year=today.year - years - 1).isoformat()
    end = today.isoformat()
    form = {
        "stock": f"{code},{org_id}",
        "tabName": "fulltext",
        "pageSize": "30",
        "pageNum": "1",
        "column": _exchange_column(exchange),
        "category": CATEGORY_ANNUAL,
        "seDate": f"{start}~{end}",
    }
    raw = (
        raw_response if raw_response is not None else _http_post_form(ANNOUNCEMENT_QUERY_URL, form)
    )
    records = _parse_announcements(raw)

    candidates: list[Announcement] = []
    for rec in records:
        ann = _to_announcement(rec)
        if ann is None:
            continue
        if _RE_EXCLUDE_TITLE.search(ann.title):
            continue
        if ann.year is None:
            continue
        candidates.append(ann)

    # De-dup by fiscal year; prefer the latest-announced.
    by_year: dict[int, Announcement] = {}
    for ann in candidates:
        assert ann.year is not None  # narrowed above
        existing = by_year.get(ann.year)
        if existing is None or ann.announcement_date > existing.announcement_date:
            by_year[ann.year] = ann

    # Most recent `years` fiscal years.
    latest_years = sorted(by_year.keys(), reverse=True)[:years]
    return [by_year[y] for y in sorted(latest_years, reverse=True)]


# ---------------------------------------------------------------------------
# HKEX title search
# ---------------------------------------------------------------------------


def _extract_year_hk(title: str) -> int | None:
    """Extract fiscal year from an HKEX annual-report title.

    Tries the A-share Chinese pattern first ("2023年年度报告"), then falls
    back to any 4-digit year in the string ("Annual Report 2023")."""
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
    for row in rows:
        if row.get("c") == padded:
            stock_id = row.get("i")
            if stock_id is None:
                raise FetchSchemaError(
                    f"HKEX active-stock list: found c={padded} but no 'i' field: {row!r}"
                )
            return str(stock_id)
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


def _to_hkex_announcement(rec: dict) -> Announcement | None:
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
    ann_date: date | None = None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            ann_date = datetime.strptime(head, fmt).date()
            break
        except ValueError:
            continue
    if ann_date is None:
        return None
    file_url = urllib.parse.urljoin(HKEX_BASE_URL, str(file_link))
    return Announcement(
        title=str(title).strip(),
        adjunct_url=file_url,
        announcement_date=ann_date,
        year=_extract_year_hk(str(title)),
    )


def search_hkex_annual_reports(
    code: str,
    years: int,
    *,
    prefer_lang: str = "en",
    stock_id: str | None = None,
    raw_response: bytes | None = None,
    raw_stocklist: bytes | None = None,
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

    `stock_id`, `raw_response`, `raw_stocklist` are injectable for tests."""
    if prefer_lang not in ("en", "zh"):
        raise ValueError(f"prefer_lang must be 'en' or 'zh', got {prefer_lang!r}")
    if stock_id is None:
        stock_id = resolve_hkex_stock_id(code, stocklist_bytes=raw_stocklist)
    today = date.today()
    # Pad the window by one year to catch late-filed prior-year reports.
    from_date = today.replace(year=today.year - years - 1).strftime("%Y%m%d")
    to_date = today.strftime("%Y%m%d")
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
        "t1code": HKEX_T1_FINANCIAL,
        "t2Gcode": "-2",
        "t2code": HKEX_T2_ANNUAL_REPORT,
        "rowRange": "100",
        "lang": "EN" if prefer_lang == "en" else "ZH",
    }
    url = f"{HKEX_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    raw = raw_response if raw_response is not None else _http_get(url)
    records = _parse_hkex_announcements(raw)

    candidates: list[Announcement] = []
    for rec in records:
        ann = _to_hkex_announcement(rec)
        if ann is None:
            continue
        if _RE_EXCLUDE_TITLE_HK.search(ann.title):
            continue
        if ann.year is None:
            continue
        candidates.append(ann)

    # Dedupe by fiscal year; later announcement date wins (e.g. republished
    # / errata versions).
    by_year: dict[int, Announcement] = {}
    for ann in candidates:
        assert ann.year is not None
        existing = by_year.get(ann.year)
        if existing is None or ann.announcement_date > existing.announcement_date:
            by_year[ann.year] = ann

    latest_years = sorted(by_year.keys(), reverse=True)[:years]
    return [by_year[y] for y in latest_years]


def search_prospectus(
    org_id: str,
    code: str,
    exchange: str,
    *,
    raw_response: bytes | None = None,
) -> list[Announcement]:
    """Return the 招股说明书 announcement(s) for this ticker.

    We use a title keyword search (`searchkey=招股说明书`) rather than a
    category — the category `category_fxbg_szsh` is noisy. Filters titles
    exactly equal to "招股说明书" (excluding 附录 / 补充 / 修订)."""
    form = {
        "stock": f"{code},{org_id}",
        "tabName": "fulltext",
        "pageSize": "30",
        "pageNum": "1",
        "column": _exchange_column(exchange),
        "searchkey": "招股说明书",
        "seDate": "1990-01-01~" + date.today().isoformat(),
    }
    raw = (
        raw_response if raw_response is not None else _http_post_form(ANNOUNCEMENT_QUERY_URL, form)
    )
    records = _parse_announcements(raw)

    matches: list[Announcement] = []
    for rec in records:
        ann = _to_announcement(rec)
        if ann is None:
            continue
        # Exclude 附录 / 补充 / 修订 — only the canonical document.
        if not _RE_PROSPECTUS_TITLE.match(ann.title):
            continue
        matches.append(ann)

    # Prefer the latest (in case of re-filings).
    matches.sort(key=lambda a: a.announcement_date, reverse=True)
    return matches


# ---------------------------------------------------------------------------
# PDF download (idempotent)
# ---------------------------------------------------------------------------


def download_pdf(adjunct_url: str, dest: Path) -> bool:
    """Download `PDF_BASE_URL + adjunct_url` to `dest`. Idempotent.

    Returns True if a download was performed, False if the file was skipped
    because it already exists with size > MIN_VALID_PDF_BYTES."""
    if dest.exists() and dest.stat().st_size > MIN_VALID_PDF_BYTES:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = urllib.parse.urljoin(PDF_BASE_URL, adjunct_url.lstrip("/"))
    body = _http_get(url)
    if len(body) <= MIN_VALID_PDF_BYTES:
        raise FetchSchemaError(
            f"Downloaded file at {url} is {len(body)} bytes "
            f"(<= {MIN_VALID_PDF_BYTES}); refusing to save as PDF."
        )
    tmp = dest.with_suffix(dest.suffix + ".partial")
    tmp.write_bytes(body)
    tmp.rename(dest)
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch 年报 + 招股说明书 PDFs from cninfo (巨潮资讯网) for an A-share ticker.",
    )
    parser.add_argument("ticker", help="e.g. 600519.SH or 000001.SZ")
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
        "--out",
        type=Path,
        default=None,
        help="Output directory (default data/filings/<ticker>/).",
    )
    args = parser.parse_args(argv)

    try:
        code, exchange = parse_ticker(args.ticker)
    except ValueError as e:
        _print(f"error: {e}")
        return 2

    out_dir: Path = args.out or Path("data/filings") / f"{code}.{exchange}"
    out_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    prospectus: list[Announcement] = []

    if exchange == "HK":
        _print(f"[1/3] source = HKEX (披露易); stockId={code.zfill(5)} lang={args.lang}")
        _print(f"[2/3] searching Annual Report (latest {args.years} fiscal years)")
        try:
            annuals = search_hkex_annual_reports(code, args.years, prefer_lang=args.lang)
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
            annuals = search_annual_reports(org_id, code, exchange, args.years)
        except (FetchSchemaError, urllib.error.URLError) as e:
            _print(f"error: 年报 search failed: {e}")
            return 2

        if args.include_prospectus:
            _print("[3/4] searching 招股说明书")
            try:
                prospectus = search_prospectus(org_id, code, exchange)
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

    if not annuals:
        _print("       no 年报 found — check ticker / years window")
    for ann in annuals:
        _print(f"       - {ann.title} ({ann.announcement_date.isoformat()}) -> {ann.adjunct_url}")

    step_label = "[3/3]" if exchange == "HK" else "[4/4]"
    _print(f"{step_label} downloading to {out_dir}")
    downloaded = 0
    skipped = 0
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
        except (FetchSchemaError, urllib.error.URLError, OSError) as e:
            msg = f"{dest.name}: {e}"
            _print(f"       FAIL  {msg}")
            failures.append(msg)

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
