"""Fetch 卖方深度研报 PDFs from 东方财富 (Eastmoney) research API for A-share tickers.

Usage:
    python scripts/download_research.py 600519.SH --years 3 --depth-only --max 15
    python scripts/download_research.py 000001.SZ --years 5

Dependencies: stdlib + tenacity + pypinyin (see pyproject.toml).

Contract: see docs/superpowers/specs/2026-04-28-value-profile-skill-design.md §3
"Research fetcher".
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
from datetime import date, datetime, timedelta
from pathlib import Path

from pypinyin import Style, lazy_pinyin
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESEARCH_LIST_URL = "https://reportapi.eastmoney.com/report/list"
PDF_URL_TEMPLATE = "https://pdf.dfcfw.com/pdf/H3_{info_code}_{variant}.pdf"
PDF_URL_VARIANTS = ("1", "0", "2")  # primary + fallback suffixes

USER_AGENT = (
    "Mozilla/5.0 (compatible; ah-research/0.1; +https://github.com/brian-huang/ah-research-vp)"
)

MIN_VALID_PDF_BYTES = 100 * 1024  # 100 KB
RATE_LIMIT_SECONDS = 1.0
REQUEST_TIMEOUT = 30
MAX_FILENAME_TITLE_LEN = 60
PAGE_SIZE = 50

# Depth keywords (sharpest-signal reports).
_RE_DEPTH_KEYWORDS = re.compile(r"深度|首次|覆盖|重大")

# Known broker-name → pinyin overrides (canonical, disambiguated forms).
# Covers the main brokers whose default pinyin concatenation is awkward
# or ambiguous. Everything else falls through to generic pypinyin.
BROKER_PINYIN_OVERRIDES: dict[str, str] = {
    "中金公司": "zhongjin",
    "中国国际金融": "zhongjin",
    "中信证券": "zhongxin",
    "中信建投": "zhongxinjt",
    "中信建投证券": "zhongxinjt",
    "华泰证券": "huatai",
    "华创证券": "huachuang",
    "华西证券": "huaxi",
    "国盛证券": "guosheng",
    "天风证券": "tianfeng",
    "东吴证券": "dongwu",
    "东北证券": "dongbei",
    "东兴证券": "dongxing",
    "中泰证券": "zhongtai",
    "国金证券": "guojin",
    "招商证券": "zhaoshang",
    "国信证券": "guoxin",
    "国海证券": "guohai",
    "国元证券": "guoyuan",
    "国联证券": "guolian",
    "国投证券": "guotou",
    "光大证券": "guangda",
    "海通证券": "haitong",
    "方正证券": "fangzheng",
    "长江证券": "changjiang",
    "广发证券": "guangfa",
    "申万宏源": "shenwanhy",
    "开源证券": "kaiyuan",
    "民生证券": "minsheng",
    "兴业证券": "xingye",
    "西南证券": "xinan",
    "西部证券": "xibu",
    "山西证券": "shanxi",
    "上海证券": "shanghai",
    "财通证券": "caitong",
    "财信证券": "caixin",
    "平安证券": "pingan",
    "信达证券": "xinda",
    "浙商证券": "zheshang",
    "银河证券": "yinhe",
    "中国银河": "yinhe",
    "中银证券": "zhongyin",
    "中原证券": "zhongyuan",
}

# Filename-illegal chars on common FSes (covers macOS + Linux + Windows).
_RE_FILENAME_UNSAFE = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_RE_WHITESPACE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FetchSchemaError(Exception):
    """Raised when an Eastmoney API response does not match the expected shape."""


class FetchPartialFailure(Exception):
    """Raised at the end of a run when one or more downloads failed."""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResearchReport:
    info_code: str
    title: str
    org_name: str  # Chinese broker name, e.g. "中金公司"
    publish_date: date
    attach_type: str  # e.g. "深度报告" / "公司点评" / "行业深度" / "首次覆盖"


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
        status = getattr(resp, "status", 200)
        if status == 429 or (500 <= status < 600):
            raise urllib.error.HTTPError(
                getattr(resp, "url", url),
                status,
                f"status {status}",
                {},  # type: ignore[arg-type]
                None,
            )
        return resp.read()


# ---------------------------------------------------------------------------
# Broker pinyin
# ---------------------------------------------------------------------------


def broker_pinyin(org_name: str) -> str:
    """Return the lowercase pinyin slug for a Chinese broker name.

    Uses BROKER_PINYIN_OVERRIDES first; falls back to pypinyin
    concatenation (e.g. "某券商" → "mouquanshang"). Strips any
    non-ascii-alnum chars from the result for filename safety."""
    name = (org_name or "").strip()
    if not name:
        return "unknown"
    if name in BROKER_PINYIN_OVERRIDES:
        return BROKER_PINYIN_OVERRIDES[name]
    parts = lazy_pinyin(name, style=Style.NORMAL)
    slug = "".join(p for p in parts if p).lower()
    slug = re.sub(r"[^a-z0-9]", "", slug)
    return slug or "unknown"


# ---------------------------------------------------------------------------
# Title sanitization
# ---------------------------------------------------------------------------


def sanitize_title(title: str, max_len: int = MAX_FILENAME_TITLE_LEN) -> str:
    """Remove FS-unsafe chars, collapse whitespace, cap length.

    Preserves Chinese characters; replaces illegal chars with '-';
    collapses runs of '-' to a single '-'; strips leading/trailing '-'."""
    if not title:
        return "untitled"
    # Replace illegal filename chars with '-'.
    s = _RE_FILENAME_UNSAFE.sub("-", title)
    # Collapse whitespace to single '-'.
    s = _RE_WHITESPACE.sub("-", s)
    # Collapse multiple '-' to one.
    s = re.sub(r"-+", "-", s)
    s = s.strip("-").strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "untitled"


# ---------------------------------------------------------------------------
# Ticker parsing
# ---------------------------------------------------------------------------


def parse_ticker(ticker: str) -> tuple[str, str]:
    """Split `<code>.<exchange>` into (code, exchange).

    Exchange is normalised upper-case; only SH / SZ are accepted."""
    m = re.fullmatch(r"(\d{6})\.(SH|SZ|sh|sz)", ticker.strip())
    if not m:
        raise ValueError(
            f"Bad ticker {ticker!r}: expected <6-digit-code>.<SH|SZ>, e.g. 600519.SH or 000001.SZ"
        )
    return m.group(1), m.group(2).upper()


# ---------------------------------------------------------------------------
# Research API
# ---------------------------------------------------------------------------


def _build_list_url(
    code: str,
    *,
    begin_time: str,
    end_time: str,
    page_no: int,
    page_size: int = PAGE_SIZE,
) -> str:
    params = {
        "pageSize": str(page_size),
        "pageNo": str(page_no),
        "industry": "*",
        "industryCode": "*",
        "rating": "*",
        "ratingChange": "*",
        "beginTime": begin_time,
        "endTime": end_time,
        "code": code,
        "orgCode": "",
        "pageCount": "1",
        "qType": "0",
        "fields": "",
        "_": str(int(time.time() * 1000)),
    }
    return f"{RESEARCH_LIST_URL}?{urllib.parse.urlencode(params)}"


def _parse_publish_date(raw: str) -> date | None:
    """Parse '2024-11-20 18:30:00' or '2024-11-20' → date."""
    if not raw:
        return None
    s = raw.strip().split(" ")[0]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_research_list(raw: bytes) -> list[dict]:
    """Parse Eastmoney research list JSON (optionally JSONP-wrapped).

    Returns the `data` list."""
    text = raw.decode("utf-8", errors="replace").strip()
    # Strip JSONP wrapper if present: "datatable1234(...)" or "jQuery...({...})".
    m = re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\((.*)\)\s*;?\s*$", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise FetchSchemaError(
            f"Eastmoney research list: not valid JSON ({e}). First 200 bytes: {raw[:200]!r}"
        ) from e
    records = data.get("data")
    if records is None:
        return []
    if not isinstance(records, list):
        raise FetchSchemaError(
            f"Eastmoney research list: 'data' is {type(records).__name__}, expected list or null"
        )
    return records


def _to_report(raw: dict) -> ResearchReport | None:
    info_code = raw.get("infoCode")
    title = raw.get("title")
    org_name = raw.get("orgSName") or raw.get("orgName") or ""
    publish_raw = raw.get("publishDate") or raw.get("publish_date") or ""
    attach_type = raw.get("attachType") or raw.get("reportType") or ""
    if not info_code or not title:
        return None
    pub = _parse_publish_date(str(publish_raw))
    if pub is None:
        return None
    return ResearchReport(
        info_code=str(info_code),
        title=str(title),
        org_name=str(org_name),
        publish_date=pub,
        attach_type=str(attach_type),
    )


def is_depth_report(r: ResearchReport) -> bool:
    """True if the report smells like a deep / initiation / coverage note.

    Checks both attachType ("深度报告"/"行业深度"/"首次覆盖") and title
    keywords (some brokers stuff 深度/首次 into the title even when
    attachType is generic)."""
    if _RE_DEPTH_KEYWORDS.search(r.attach_type or ""):
        return True
    return bool(_RE_DEPTH_KEYWORDS.search(r.title or ""))


def search_research(
    code: str,
    *,
    years: int,
    depth_only: bool,
    max_results: int,
    raw_responses: list[bytes] | None = None,
) -> list[ResearchReport]:
    """Fetch research reports for `code` (6-digit) over `years`.

    Paginates through the list API until max_results is reached or data runs
    out. `raw_responses` is injectable for tests (one bytes blob per page)."""
    today = date.today()
    begin = (today - timedelta(days=years * 365 + 30)).isoformat()
    end = today.isoformat()

    collected: list[ResearchReport] = []
    page = 1
    while True:
        if raw_responses is not None:
            if page - 1 >= len(raw_responses):
                break
            raw = raw_responses[page - 1]
        else:
            url = _build_list_url(code, begin_time=begin, end_time=end, page_no=page)
            raw = _http_get(url)
        records = _parse_research_list(raw)
        if not records:
            break
        for rec in records:
            rep = _to_report(rec)
            if rep is None:
                continue
            if depth_only and not is_depth_report(rep):
                continue
            collected.append(rep)
            if len(collected) >= max_results:
                return collected
        if len(records) < PAGE_SIZE:
            break
        page += 1
        # Hard page cap to avoid runaway.
        if page > 20:
            break
    return collected


# ---------------------------------------------------------------------------
# Filename construction
# ---------------------------------------------------------------------------


def report_filename(r: ResearchReport) -> str:
    broker = broker_pinyin(r.org_name)
    title = sanitize_title(r.title)
    date_str = r.publish_date.strftime("%Y%m%d")
    return f"{broker}-{title}-{date_str}.pdf"


# ---------------------------------------------------------------------------
# PDF download (idempotent, with URL variant fallback)
# ---------------------------------------------------------------------------


def download_pdf(
    info_code: str,
    dest: Path,
    *,
    variants: tuple[str, ...] = PDF_URL_VARIANTS,
) -> bool:
    """Try each variant of H3_<info_code>_<N>.pdf until one yields a valid PDF.

    Returns True if a download happened, False if skipped (already present)."""
    if dest.exists() and dest.stat().st_size > MIN_VALID_PDF_BYTES:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for variant in variants:
        url = PDF_URL_TEMPLATE.format(info_code=info_code, variant=variant)
        try:
            body = _http_get(url)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            last_err = e
            continue
        if len(body) <= MIN_VALID_PDF_BYTES:
            last_err = FetchSchemaError(
                f"{url}: {len(body)} bytes (<= {MIN_VALID_PDF_BYTES}), treating as 404/placeholder"
            )
            continue
        tmp = dest.with_suffix(dest.suffix + ".partial")
        tmp.write_bytes(body)
        tmp.rename(dest)
        return True
    raise FetchSchemaError(f"all PDF URL variants failed for infoCode={info_code}: {last_err}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch 卖方深度研报 PDFs from 东方财富 for an A-share ticker.",
    )
    parser.add_argument("ticker", help="e.g. 600519.SH or 000001.SZ")
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="How many years back to fetch (default 3).",
    )
    parser.add_argument(
        "--depth-only",
        action="store_true",
        help="Filter to 深度/首次/覆盖/重大 reports (exclude 点评/跟踪/策略/每日).",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=50,
        dest="max_results",
        help="Max total reports to download (default 50).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default data/filings/<ticker>/research/).",
    )
    args = parser.parse_args(argv)

    try:
        code, exchange = parse_ticker(args.ticker)
    except ValueError as e:
        _print(f"error: {e}")
        return 2

    out_dir: Path = args.out or Path("data/filings") / f"{code}.{exchange}" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)

    _print(f"[1/3] searching 东方财富 research API (code={code}, years={args.years})")
    try:
        reports = search_research(
            code,
            years=args.years,
            depth_only=args.depth_only,
            max_results=args.max_results,
        )
    except (FetchSchemaError, urllib.error.URLError) as e:
        _print(f"error: research search failed: {e}")
        return 2

    if not reports:
        _print("       no reports found (try wider --years or drop --depth-only)")
        return 0

    _print(f"[2/3] found {len(reports)} reports (depth_only={args.depth_only})")
    for r in reports[:10]:
        _print(
            f"       - [{r.attach_type or '?'}] {r.org_name} — {r.title} "
            f"({r.publish_date.isoformat()})"
        )
    if len(reports) > 10:
        _print(f"       ... and {len(reports) - 10} more")

    _print(f"[3/3] downloading to {out_dir}")
    downloaded = 0
    skipped = 0
    failures: list[str] = []
    for r in reports:
        fname = report_filename(r)
        dest = out_dir / fname
        try:
            if download_pdf(r.info_code, dest):
                _print(f"       wrote {fname} ({dest.stat().st_size} bytes)")
                downloaded += 1
            else:
                _print(f"       skip  {fname} (already present)")
                skipped += 1
        except (FetchSchemaError, urllib.error.URLError, OSError) as e:
            msg = f"{fname}: {e}"
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
