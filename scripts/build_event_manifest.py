"""Build a canonical regulatory-event manifest from an official query bundle."""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

REQUIRED_SCOPES = {
    "formal_sanctions": "listing_history",
    "related_party_harm": "listing_history",
    "auditor_changes": "rolling_3y",
    "auditor_investigations": "rolling_3y",
    "material_restatements": "rolling_3y",
    "controller_criminal_cases": "rolling_3y",
    "late_filings": "rolling_3y",
    "other_regulatory_events": "rolling_3y",
}
REQUIRED_SOURCE_IDS = {
    "SH": {
        "formal_sanctions": {"csrc", "sse"},
        "related_party_harm": {"csrc", "sse"},
        "auditor_changes": {"sse"},
        "auditor_investigations": {"csrc", "mof"},
        "material_restatements": {"sse"},
        "controller_criminal_cases": {"csrc"},
        "late_filings": {"sse"},
        "other_regulatory_events": {"csrc", "sse"},
    },
    "SZ": {
        "formal_sanctions": {"csrc", "szse"},
        "related_party_harm": {"csrc", "szse"},
        "auditor_changes": {"szse"},
        "auditor_investigations": {"csrc", "mof"},
        "material_restatements": {"szse"},
        "controller_criminal_cases": {"csrc"},
        "late_filings": {"szse"},
        "other_regulatory_events": {"csrc", "szse"},
    },
    "HK": {
        "formal_sanctions": {"hkex", "sfc", "hkpf", "icac", "hkjd"},
        "related_party_harm": {"hkex", "sfc"},
        "auditor_changes": {"hkex"},
        "auditor_investigations": {"afrc"},
        "material_restatements": {"hkex"},
        "controller_criminal_cases": {"sfc", "hkpf", "icac", "hkjd"},
        "late_filings": {"hkex"},
        "other_regulatory_events": {"hkex", "sfc"},
    },
}
HK_CRIMINAL_INTEGRITY_SOURCE_IDS = {"hkpf", "icac", "hkjd"}
SOURCE_DOMAINS = {
    "csrc": ("csrc.gov.cn",),
    "sse": ("sse.com.cn",),
    "szse": ("szse.cn",),
    "hkex": ("hkex.com.hk", "hkexnews.hk"),
    "sfc": ("sfc.hk",),
    "afrc": ("afrc.org.hk",),
    "mof": ("mof.gov.cn",),
    "nfra": ("nfra.gov.cn",),
    "pbc": ("pbc.gov.cn",),
    "hkma": ("hkma.gov.hk",),
    "ia": ("ia.org.hk",),
    "hkpf": ("police.gov.hk",),
    "icac": ("icac.org.hk",),
    "hkjd": ("judiciary.hk",),
}
BANK_SOURCE_IDS = {
    "SH": {
        "formal_sanctions": {"nfra", "pbc"},
        "related_party_harm": {"nfra", "pbc"},
        "other_regulatory_events": {"nfra", "pbc"},
    },
    "SZ": {
        "formal_sanctions": {"nfra", "pbc"},
        "related_party_harm": {"nfra", "pbc"},
        "other_regulatory_events": {"nfra", "pbc"},
    },
    "HK": {
        "formal_sanctions": {"hkma"},
        "related_party_harm": {"hkma"},
        "other_regulatory_events": {"hkma"},
    },
}
INSURER_SOURCE_IDS = {
    "SH": {
        "formal_sanctions": {"nfra"},
        "related_party_harm": {"nfra"},
        "other_regulatory_events": {"nfra"},
    },
    "SZ": {
        "formal_sanctions": {"nfra"},
        "related_party_harm": {"nfra"},
        "other_regulatory_events": {"nfra"},
    },
    "HK": {
        "formal_sanctions": {"ia"},
        "related_party_harm": {"ia"},
        "other_regulatory_events": {"ia"},
    },
}
SOURCE_EXCHANGES = {
    "sse": "SH",
    "szse": "SZ",
    "hkex": "HK",
    "sfc": "HK",
    "afrc": "HK",
    "hkma": "HK",
    "ia": "HK",
    "hkpf": "HK",
    "icac": "HK",
    "hkjd": "HK",
}
OFFICIAL_DOMAINS = {
    "SH": (
        "csrc.gov.cn",
        "cninfo.com.cn",
        "mof.gov.cn",
        "nfra.gov.cn",
        "pbc.gov.cn",
        "sse.com.cn",
        "szse.cn",
    ),
    "SZ": (
        "csrc.gov.cn",
        "cninfo.com.cn",
        "mof.gov.cn",
        "nfra.gov.cn",
        "pbc.gov.cn",
        "sse.com.cn",
        "szse.cn",
    ),
    "HK": (
        "cninfo.com.cn",
        "hkex.com.hk",
        "hkexnews.hk",
        "sfc.hk",
        "afrc.org.hk",
        "hkma.gov.hk",
        "police.gov.hk",
        "icac.org.hk",
        "judiciary.hk",
        "csrc.gov.cn",
        "mof.gov.cn",
        "nfra.gov.cn",
        "pbc.gov.cn",
    ),
}
EXCHANGE_TIMEZONES = {
    "SH": ZoneInfo("Asia/Shanghai"),
    "SZ": ZoneInfo("Asia/Shanghai"),
    "HK": ZoneInfo("Asia/Hong_Kong"),
}
SUBJECT_TYPES = {"issuer", "management", "controller", "auditor"}
MANAGEMENT_ROLES = {
    "chair",
    "chief_executive",
    "cfo",
    "director",
    "supervisor",
    "senior_management",
}
CONTROLLER_STATUSES = {"identified", "none_identified"}
FINAL_EVENT_STATUSES = {"effective", "final", "confirmed"}
EVENT_STATUSES = {
    "effective",
    "final",
    "confirmed",
    "pending",
    "investigation",
    "withdrawn",
}
OFFENSE_TYPES = {
    "financial_fraud",
    "false_statement",
    "market_manipulation",
    "insider_trading",
    "related_party_harm",
    "late_filing",
    "auditor_misconduct",
    "other",
}
ISSUER_CONNECTIONS = {
    "issuer",
    "serving_at_occurrence",
    "former_but_conduct_during_tenure",
    "post_tenure_issuer_related",
    "post_tenure_unrelated",
    "controller_at_occurrence",
    "historical_controller",
    "auditor_at_occurrence",
    "former_auditor_for_period",
    "unknown",
}
GENERIC_SUBJECT_NAMES = {
    "董事长",
    "总经理",
    "首席执行官",
    "财务总监",
    "董秘",
    "董事",
    "监事",
    "高管",
    "cfo",
    "ceo",
    "chair",
    "director",
    "management",
}
LISTING_PROFILE_ADAPTER_FIELDS = {
    "issuer_code",
    "listing_codes",
    "listing_date",
    "listing_dates",
    "listing_statuses",
    "delisting_dates",
    "official_result_total",
}


class ManifestError(Exception):
    """Raised when an evidence bundle cannot prove manifest completeness."""


RosterFetcher = Callable[[str, dict[str, object]], bytes]
EventFetcher = Callable[
    [str, str, str, dict[str, object], object],
    list[bytes],
]
DocumentFetcher = Callable[[str], bytes]

HKEX_EQUITY_QUOTE_PAGE_URL = (
    "https://www.hkex.com.hk/Market-Data/Securities-Prices/Equities/Equities-Quote"
)
HKEX_EQUITY_QUOTE_API_URL = "https://www1.hkex.com.hk/hkexwidget/data/getequityquote"
HKEX_EQUITY_QUOTE_BOOTSTRAP = "hkex_equity_quote_token_v1"
_HKEX_TOKEN_FUNCTION = re.compile(
    r"LabCI\.getToken\s*=\s*function\s*\(\)\s*\{(?P<body>.*?)^\s*\};",
    re.MULTILINE | re.DOTALL,
)
_HKEX_TOKEN_RETURN = re.compile(
    r"""^\s*return\s+["'](?P<token>[^"']+)["']\s*;""",
    re.MULTILINE,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_official_roster(
    source_url: str,
    query_params: dict[str, object],
) -> bytes:
    try:
        return _fetch_official_single(
            source_url,
            "GET",
            "query",
            query_params,
        )
    except ManifestError as exc:
        raise ManifestError(f"subject_roster live official request failed: {exc}") from exc


def _fetch_official_single(
    source_url: str,
    http_method: str,
    request_encoding: str,
    query_params: dict[str, object],
    request_headers: object = None,
    request_bootstrap: object = None,
) -> bytes:
    if request_headers is None:
        extra_headers: dict[str, str] = {}
    elif isinstance(request_headers, dict) and all(
        isinstance(key, str) and isinstance(value, str) for key, value in request_headers.items()
    ):
        extra_headers = dict(request_headers)
    else:
        raise ManifestError("request_headers must map strings to strings")
    headers = {
        "User-Agent": "ah-research-event-manifest/1.0",
        **extra_headers,
    }
    if request_bootstrap is not None:
        return _fetch_bootstrapped_identity(
            source_url,
            http_method,
            request_encoding,
            query_params,
            headers,
            request_bootstrap,
        )
    if http_method == "GET" and request_encoding == "query":
        separator = "&" if "?" in source_url else "?"
        request_url = f"{source_url}{separator}{urllib.parse.urlencode(query_params, doseq=True)}"
        request = urllib.request.Request(
            request_url,
            headers=headers,
        )
    elif http_method == "POST" and request_encoding in {"form", "json"}:
        if request_encoding == "form":
            body = urllib.parse.urlencode(query_params, doseq=True).encode()
            content_type = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(query_params).encode()
            content_type = "application/json"
        headers["Content-Type"] = content_type
        request = urllib.request.Request(
            source_url,
            data=body,
            method="POST",
            headers=headers,
        )
    else:
        raise ManifestError("profile or roster HTTP method and request encoding are incompatible")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            original = urllib.parse.urlparse(source_url)
            final = urllib.parse.urlparse(response.geturl())
            if (
                final.scheme != "https"
                or (final.hostname or "").lower() != (original.hostname or "").lower()
            ):
                raise ManifestError(
                    "profile or roster live official request redirected "
                    "outside the declared HTTPS host"
                )
            return response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise ManifestError(f"profile or roster live official request failed: {exc}") from exc


def _fetch_bootstrapped_identity(
    source_url: str,
    http_method: str,
    request_encoding: str,
    query_params: dict[str, object],
    headers: dict[str, str],
    request_bootstrap: object,
) -> bytes:
    if not isinstance(request_bootstrap, dict):
        raise ManifestError("request_bootstrap must be an object")
    if set(request_bootstrap) != {"type", "page_url"}:
        raise ManifestError("request_bootstrap fields are invalid")
    if request_bootstrap.get("type") != HKEX_EQUITY_QUOTE_BOOTSTRAP:
        raise ManifestError("request_bootstrap type is unsupported")
    if (
        source_url != HKEX_EQUITY_QUOTE_API_URL
        or request_bootstrap.get("page_url") != HKEX_EQUITY_QUOTE_PAGE_URL
        or http_method != "GET"
        or request_encoding != "query"
    ):
        raise ManifestError("HKEX equity quote bootstrap contract is invalid")
    if set(query_params) != {"issuer_code"}:
        raise ManifestError("HKEX equity quote query must contain only issuer_code")
    issuer_code = str(query_params.get("issuer_code") or "")
    if not re.fullmatch(r"\d{5}", issuer_code):
        raise ManifestError("HKEX equity quote issuer_code must contain five digits")

    sym = issuer_code.lstrip("0") or "0"
    page_query = urllib.parse.urlencode({"sym": sym, "sc_lang": "en"})
    page_url = f"{HKEX_EQUITY_QUOTE_PAGE_URL}?{page_query}"
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar),
    )
    try:
        page_request = urllib.request.Request(page_url, headers=headers)
        with opener.open(page_request, timeout=30) as response:
            final_page = urllib.parse.urlparse(response.geturl())
            if (
                final_page.scheme != "https"
                or (final_page.hostname or "").lower() != "www.hkex.com.hk"
            ):
                raise ManifestError("HKEX token page redirected outside the declared HTTPS host")
            page_body = response.read()
        page_text = page_body.decode("utf-8")
        function_match = _HKEX_TOKEN_FUNCTION.search(page_text)
        token_match = (
            _HKEX_TOKEN_RETURN.search(function_match.group("body"))
            if function_match is not None
            else None
        )
        if token_match is None:
            raise ManifestError("HKEX token page does not contain LabCI.getToken")
        token = urllib.parse.unquote(token_match.group("token"))
        if not token or len(token) > 512:
            raise ManifestError("HKEX token page returned an invalid token")

        callback = "ahResearchCallback"
        api_query = urllib.parse.urlencode(
            {
                "sym": sym,
                "token": token,
                "lang": "eng",
                "qid": int(time.time() * 1000),
                "callback": callback,
            }
        )
        api_request = urllib.request.Request(
            f"{HKEX_EQUITY_QUOTE_API_URL}?{api_query}",
            headers={
                **headers,
                "Accept": "application/javascript, application/json, text/javascript, */*",
                "Referer": page_url,
            },
        )
        with opener.open(api_request, timeout=30) as response:
            final_api = urllib.parse.urlparse(response.geturl())
            if (
                final_api.scheme != "https"
                or (final_api.hostname or "").lower() != "www1.hkex.com.hk"
            ):
                raise ManifestError(
                    "HKEX equity quote API redirected outside the declared HTTPS host"
                )
            api_body = response.read()
    except ManifestError:
        raise
    except (OSError, UnicodeDecodeError, urllib.error.URLError) as exc:
        raise ManifestError(f"HKEX equity quote bootstrap failed: {exc}") from exc

    prefix = f"{callback}("
    try:
        jsonp = api_body.decode("utf-8").strip()
        if not jsonp.startswith(prefix) or not jsonp.endswith(")"):
            raise ManifestError("HKEX equity quote response is not expected JSONP")
        payload = json.loads(jsonp[len(prefix) : -1])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"HKEX equity quote response is invalid: {exc}") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    quote = data.get("quote") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or data.get("responsecode") != "000"
        or not isinstance(quote, dict)
        or quote.get("product_type") != "EQTY"
    ):
        raise ManifestError("HKEX equity quote response does not identify an equity")
    response_sym = str(quote.get("sym") or "")
    if not response_sym.isdigit() or response_sym.zfill(5) != issuer_code:
        raise ManifestError("HKEX equity quote response does not match issuer_code")
    try:
        listing_date = datetime.strptime(
            str(quote.get("listing_date") or ""),
            "%d %b %Y",
        ).date()
    except ValueError as exc:
        raise ManifestError("HKEX equity quote listing_date is invalid") from exc
    issuer_name = str(quote.get("issuer_name") or "").strip()
    if not issuer_name:
        raise ManifestError("HKEX equity quote issuer_name is missing")

    stable_profile = {
        "query": dict(query_params),
        "issuer_code": issuer_code,
        "listing_codes": {"HK": issuer_code},
        "listing_date": listing_date.isoformat(),
        "listing_dates": {"HK": listing_date.isoformat()},
        "listing_status": "listed",
        "listing_statuses": {"HK": "listed"},
        "delisting_date": None,
        "delisting_dates": {"HK": None},
        "official_result_total": 1,
        "official_fields": {
            "sym": response_sym,
            "issuer_name": issuer_name,
            "listing_category": quote.get("listing_category"),
            "chairman": quote.get("chairman"),
        },
    }
    return (
        json.dumps(
            stable_profile,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _fetch_identity_response(
    fetcher: RosterFetcher,
    source_url: str,
    http_method: str,
    request_encoding: str,
    query_params: dict[str, object],
    request_headers: object = None,
    request_bootstrap: object = None,
) -> bytes:
    if fetcher is _fetch_official_roster:
        return _fetch_official_single(
            source_url,
            http_method,
            request_encoding,
            query_params,
            request_headers,
            request_bootstrap,
        )
    return fetcher(source_url, query_params)


def _fetch_official_event_pages(
    query_url: str,
    http_method: str,
    request_encoding: str,
    query_params: dict[str, object],
    response_contract: object,
) -> list[bytes]:
    if isinstance(response_contract, str):
        response_schema = response_contract
        response_adapter: dict[str, object] = {}
        request_headers: dict[str, str] = {}
    elif isinstance(response_contract, dict):
        response_schema = str(response_contract.get("response_schema") or "")
        raw_adapter = response_contract.get("response_adapter")
        response_adapter = raw_adapter if isinstance(raw_adapter, dict) else {}
        raw_headers = response_contract.get("request_headers", {})
        if not isinstance(raw_headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw_headers.items()
        ):
            raise ManifestError("request_headers must map strings to strings")
        request_headers = dict(raw_headers)
    else:
        raise ManifestError("event response contract is invalid")
    if response_schema not in {
        "canonical_event_page_v1",
        "native_json_event_page_v1",
    }:
        raise ManifestError("event response_schema is unsupported")
    page_param = (
        "page_no"
        if response_schema == "canonical_event_page_v1"
        else str(response_adapter.get("request_page_param") or "")
    )
    page_count_path = (
        "page_count"
        if response_schema == "canonical_event_page_v1"
        else str(response_adapter.get("page_count_path") or "")
    )
    if not page_param or not page_count_path:
        raise ManifestError("event response adapter pagination is incomplete")
    pages: list[bytes] = []
    page_no = 1
    while True:
        request_params = {**query_params, page_param: page_no}
        if http_method == "GET" and request_encoding == "query":
            separator = "&" if "?" in query_url else "?"
            request_url = (
                f"{query_url}{separator}{urllib.parse.urlencode(request_params, doseq=True)}"
            )
            request = urllib.request.Request(
                request_url,
                headers={
                    "User-Agent": "ah-research-event-manifest/1.0",
                    **request_headers,
                },
            )
        elif http_method == "POST" and request_encoding in {"form", "json"}:
            if request_encoding == "form":
                body = urllib.parse.urlencode(request_params, doseq=True).encode()
                content_type = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(request_params).encode()
                content_type = "application/json"
            headers = {
                "Content-Type": content_type,
                "User-Agent": "ah-research-event-manifest/1.0",
                **request_headers,
            }
            request = urllib.request.Request(
                query_url,
                data=body,
                method="POST",
                headers=headers,
            )
        else:
            raise ManifestError("event HTTP method and request encoding are incompatible")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                original = urllib.parse.urlparse(query_url)
                final = urllib.parse.urlparse(response.geturl())
                if (
                    final.scheme != "https"
                    or (final.hostname or "").lower() != (original.hostname or "").lower()
                ):
                    raise ManifestError(
                        "live official event request redirected outside the declared HTTPS host"
                    )
                body = response.read()
        except (OSError, urllib.error.URLError) as exc:
            raise ManifestError(f"live official event request failed: {exc}") from exc
        pages.append(body)
        try:
            payload = json.loads(body.decode("utf-8"))
            page_count = _json_path(
                payload,
                page_count_path,
                "live official event response page count",
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManifestError(f"live official event response is invalid: {exc}") from exc
        if not isinstance(page_count, int) or page_count < 1:
            raise ManifestError("live official event response has invalid page_count")
        if page_no >= page_count:
            return pages
        page_no += 1


def _fetch_official_document(document_url: str) -> bytes:
    request = urllib.request.Request(
        document_url,
        headers={"User-Agent": "ah-research-event-manifest/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            original = urllib.parse.urlparse(document_url)
            final = urllib.parse.urlparse(response.geturl())
            if (
                final.scheme != "https"
                or (final.hostname or "").lower() != (original.hostname or "").lower()
            ):
                raise ManifestError(
                    "live official document request redirected outside the declared HTTPS host"
                )
            return response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise ManifestError(f"live official document request failed: {exc}") from exc


def _parse_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ManifestError(f"{field} must be an ISO date") from exc


def _parse_datetime(value: object, field: str) -> datetime:
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ManifestError(f"{field} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise ManifestError(f"{field} must include a timezone")
    return parsed


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _canonical_identity(ticker: object, exchange: object) -> tuple[str, str, str]:
    match = re.fullmatch(r"(\d{1,6})\.(SH|SZ|HK)", str(ticker).strip().upper())
    if not match:
        raise ManifestError("ticker must use <code>.<SH|SZ|HK>")
    code, ticker_exchange = match.groups()
    if ticker_exchange != str(exchange).upper():
        raise ManifestError("ticker exchange does not match exchange field")
    if ticker_exchange in {"SH", "SZ"} and len(code) != 6:
        raise ManifestError("A-share issuer code must contain six digits")
    if ticker_exchange == "HK":
        code = code.zfill(5)
    return f"{code}.{ticker_exchange}", ticker_exchange, code


def _normalize_listing_code(jurisdiction: str, value: object) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"listing_codes.{jurisdiction} must be a string")
    raw_code = value.strip()
    if jurisdiction == "HK":
        if not re.fullmatch(r"\d{1,5}", raw_code):
            raise ManifestError("listing_codes.HK must contain one to five digits")
        return raw_code.zfill(5)
    if not re.fullmatch(r"\d{6}", raw_code):
        raise ManifestError(f"listing_codes.{jurisdiction} must contain six digits")
    return raw_code


def _source_exchange(source_id: str, listing_codes: dict[str, str]) -> str:
    explicit_exchange = SOURCE_EXCHANGES.get(source_id)
    if explicit_exchange is not None:
        return explicit_exchange
    a_share_exchanges = set(listing_codes) & {"SH", "SZ"}
    if source_id in {"csrc", "mof", "nfra", "pbc"} and len(a_share_exchanges) == 1:
        return next(iter(a_share_exchanges))
    if len(listing_codes) == 1:
        return next(iter(listing_codes))
    raise ManifestError(f"cannot resolve jurisdiction for source_id {source_id}")


def _required_source_ids(
    category: str,
    jurisdictions: Iterable[str],
    issuer_type: str,
) -> set[str]:
    required_source_ids: set[str] = set()
    for jurisdiction in jurisdictions:
        required_source_ids.update(REQUIRED_SOURCE_IDS[jurisdiction][category])
        if issuer_type == "bank":
            required_source_ids.update(BANK_SOURCE_IDS[jurisdiction].get(category, set()))
        elif issuer_type == "insurer":
            required_source_ids.update(INSURER_SOURCE_IDS[jurisdiction].get(category, set()))
    return required_source_ids


def _require_official_https(value: object, field: str, exchange: str) -> str:
    url = str(value)
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ManifestError(f"{field} must use HTTPS")
    host = (parsed.hostname or "").lower()
    if not any(
        host == domain or host.endswith(f".{domain}") for domain in OFFICIAL_DOMAINS[exchange]
    ):
        raise ManifestError(f"{field} must use an official domain for {exchange}")
    return url


def _json_path(payload: object, path: str, field: str) -> object:
    if not path:
        raise ManifestError(f"{field} JSON path is missing")
    current = payload
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise ManifestError(f"{field} JSON path is missing: {path}")
        current = current[segment]
    return current


def _adapter_field_paths(
    adapter: dict[str, object],
    required_fields: set[str],
    field: str,
) -> dict[str, str]:
    raw_paths = adapter.get("field_paths")
    if not isinstance(raw_paths, dict):
        raise ManifestError(f"{field}.field_paths must be an object")
    paths = {str(key): str(value) for key, value in raw_paths.items()}
    if set(paths) != required_fields or not all(paths.values()):
        raise ManifestError(f"{field}.field_paths must define exactly {sorted(required_fields)}")
    return paths


def _adapt_field_value(
    payload: dict[str, object],
    adapter: dict[str, object],
    field_paths: dict[str, str],
    field: str,
    context: str,
) -> object:
    value = _json_path(payload, field_paths[field], f"{context}.{field}")
    raw_value_maps = adapter.get("value_maps", {})
    if not isinstance(raw_value_maps, dict):
        raise ManifestError(f"{context}.value_maps must be an object")
    value_map = raw_value_maps.get(field)
    if value_map is None:
        return value
    if not isinstance(value_map, dict) or str(value) not in value_map:
        raise ManifestError(f"{context}.{field} has no deterministic value mapping")
    return value_map[str(value)]


def _validate_request_bindings(
    query_params: object,
    raw_bindings: object,
    expected: dict[str, object],
    field: str,
) -> dict[str, object]:
    if not isinstance(query_params, dict) or not isinstance(raw_bindings, dict):
        raise ManifestError(f"{field} request bindings are invalid")
    bindings = {str(key): str(value) for key, value in raw_bindings.items()}
    if set(bindings) != set(expected) or not all(bindings.values()):
        raise ManifestError(f"{field} request bindings must define exactly {sorted(expected)}")
    for semantic_name, expected_value in expected.items():
        parameter_name = bindings[semantic_name]
        actual_value = query_params.get(parameter_name)
        values_match = (
            isinstance(expected_value, list)
            and isinstance(actual_value, list)
            and set(map(str, actual_value)) == set(map(str, expected_value))
        ) or (
            not isinstance(expected_value, list) and str(actual_value or "") == str(expected_value)
        )
        if not values_match:
            raise ManifestError(f"{field}.{parameter_name} does not match {semantic_name}")
    return query_params


def _native_roster_subjects(
    payload: dict[str, object],
    adapter: dict[str, object],
    declared_subjects: object,
) -> tuple[list[dict[str, object]], int]:
    if not isinstance(declared_subjects, list) or not declared_subjects:
        raise ManifestError("subjects must be a non-empty list")
    declared_by_official_id: dict[str, list[dict[str, object]]] = {}
    for subject in declared_subjects:
        if not isinstance(subject, dict):
            raise ManifestError("each subject must be an object")
        official_id = str(subject.get("official_id") or "").strip()
        if not official_id:
            raise ManifestError("subjects contain a missing official_id")
        declared_by_official_id.setdefault(official_id, []).append(subject)

    results_path = str(adapter.get("results_path") or "")
    total_path = str(adapter.get("total_path") or "")
    raw_results = _json_path(payload, results_path, "subject_roster.response_adapter.results")
    raw_total = _json_path(payload, total_path, "subject_roster.response_adapter.total")
    if not isinstance(raw_results, list) or not isinstance(raw_total, int):
        raise ManifestError("subject_roster native response has invalid results or total")
    if raw_total != len(raw_results):
        raise ManifestError("subject_roster roster evidence total does not match subjects")
    field_paths = _adapter_field_paths(
        adapter,
        {
            "official_id",
            "name",
            "type",
            "role",
            "service_start",
            "service_end",
        },
        "subject_roster.response_adapter",
    )
    normalized: list[dict[str, object]] = []
    seen_declared_ids: set[str] = set()
    for result in raw_results:
        if not isinstance(result, dict):
            raise ManifestError("subject_roster native response subject is invalid")
        official_id = str(
            _json_path(
                result,
                field_paths["official_id"],
                "subject_roster native subject official_id",
            )
            or ""
        ).strip()
        if not official_id or official_id not in declared_by_official_id:
            raise ManifestError("subject_roster native subject official_id is missing or unknown")
        service_end = _json_path(
            result,
            field_paths["service_end"],
            "subject_roster native subject service_end",
        )
        normalized_fields = {
            "type": str(
                _json_path(
                    result,
                    field_paths["type"],
                    "subject_roster native subject type",
                )
                or ""
            ),
            "name": str(
                _json_path(
                    result,
                    field_paths["name"],
                    "subject_roster native subject name",
                )
                or ""
            ),
            "role": str(
                _json_path(
                    result,
                    field_paths["role"],
                    "subject_roster native subject role",
                )
                or ""
            ),
            "service_start": str(
                _json_path(
                    result,
                    field_paths["service_start"],
                    "subject_roster native subject service_start",
                )
                or ""
            ),
            "service_end": str(service_end) if service_end is not None else None,
        }
        matches = [
            declared
            for declared in declared_by_official_id[official_id]
            if all(declared.get(field) == value for field, value in normalized_fields.items())
        ]
        if len(matches) != 1:
            raise ManifestError("subject_roster native subject role tenure is missing or ambiguous")
        declared = matches[0]
        declared_id = str(declared.get("id") or "")
        if not declared_id or declared_id in seen_declared_ids:
            raise ManifestError("subject_roster native subject role tenure is duplicated")
        seen_declared_ids.add(declared_id)
        normalized.append(
            {
                "id": declared_id,
                **normalized_fields,
                "official_id": official_id,
            }
        )
    declared_ids = {
        str(subject.get("id") or "")
        for subjects in declared_by_official_id.values()
        for subject in subjects
    }
    if seen_declared_ids != declared_ids:
        raise ManifestError("subject_roster native response does not cover declared subjects")
    return normalized, raw_total


def _native_event_page(
    payload: dict[str, object],
    adapter: dict[str, object],
    category: str,
) -> tuple[int, int, int, list[dict[str, object]]]:
    page_no = _json_path(
        payload,
        str(adapter.get("page_number_path") or ""),
        f"{category}: native response page number",
    )
    page_count = _json_path(
        payload,
        str(adapter.get("page_count_path") or ""),
        f"{category}: native response page count",
    )
    total = _json_path(
        payload,
        str(adapter.get("total_path") or ""),
        f"{category}: native response total",
    )
    raw_results = _json_path(
        payload,
        str(adapter.get("results_path") or ""),
        f"{category}: native response results",
    )
    if (
        not isinstance(page_no, int)
        or page_no < 1
        or not isinstance(page_count, int)
        or page_count < 1
        or not isinstance(total, int)
        or total < 0
        or not isinstance(raw_results, list)
    ):
        raise ManifestError(f"{category}: invalid native response pagination schema")
    field_paths = _adapter_field_paths(
        adapter,
        {
            "record_id",
            "issuer_code",
            "subject_ids",
            "title",
            "offense_type",
            "legal_effect",
            "subject_role_at_occurrence",
            "issuer_connection",
            "occurrence_date",
            "publication_time",
            "status",
            "status_effective_time",
            "document_url",
        },
        f"{category}.response_adapter",
    )
    events: list[dict[str, object]] = []
    for result in raw_results:
        if not isinstance(result, dict):
            raise ManifestError(f"{category}: native response event must be an object")
        events.append(
            {
                field: _adapt_field_value(
                    result,
                    adapter,
                    field_paths,
                    field,
                    f"{category}: native event",
                )
                for field in field_paths
            }
        )
    return page_no, page_count, total, events


def _bind_native_event_subjects(
    event: dict[str, object],
    subjects: dict[str, dict[str, str]],
    category: str,
) -> dict[str, object]:
    official_to_segments: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for subject_id, subject in subjects.items():
        official_to_segments.setdefault(subject["official_id"], []).append((subject_id, subject))
    raw_subject_ids = event.get("subject_ids")
    role_map = event.get("subject_role_at_occurrence")
    connection_map = event.get("issuer_connection")
    if (
        not isinstance(raw_subject_ids, list)
        or not isinstance(role_map, dict)
        or not isinstance(connection_map, dict)
    ):
        raise ManifestError(f"{category}: native event subject attribution is invalid")
    raw_official_ids = list(map(str, raw_subject_ids))
    if (
        len(set(raw_official_ids)) != len(raw_official_ids)
        or set(map(str, role_map)) != set(raw_official_ids)
        or set(map(str, connection_map)) != set(raw_official_ids)
    ):
        raise ManifestError(f"{category}: native event subject attribution is incomplete")
    try:
        occurrence_date = date.fromisoformat(str(event.get("occurrence_date") or ""))
    except ValueError as exc:
        raise ManifestError(f"{category}: native event occurrence_date is invalid") from exc
    canonical_subject_ids: list[str] = []
    canonical_roles: dict[str, object] = {}
    canonical_connections: dict[str, object] = {}
    for official_id in raw_official_ids:
        candidates = official_to_segments.get(official_id)
        if not candidates:
            raise ManifestError(f"{category}: native event contains an unknown official subject ID")
        event_role = role_map[official_id]
        matches = [
            (subject_id, subject)
            for subject_id, subject in candidates
            if subject["role"] == str(event_role)
            and date.fromisoformat(subject["service_start"])
            <= occurrence_date
            <= (date.fromisoformat(subject["service_end"]) if subject["service_end"] else date.max)
        ]
        if len(matches) != 1:
            raise ManifestError(f"{category}: native event role tenure is missing or ambiguous")
        subject_id, _subject = matches[0]
        canonical_subject_ids.append(subject_id)
        canonical_roles[subject_id] = event_role
        canonical_connections[subject_id] = connection_map[official_id]
    if (
        len(set(canonical_subject_ids)) != len(canonical_subject_ids)
        or set(canonical_roles) != set(canonical_subject_ids)
        or set(canonical_connections) != set(canonical_subject_ids)
    ):
        raise ManifestError(f"{category}: native event subject attribution is incomplete")
    return {
        **event,
        "subject_ids": canonical_subject_ids,
        "subject_role_at_occurrence": canonical_roles,
        "issuer_connection": canonical_connections,
    }


def _canonical_event_key(event: dict[str, object]) -> tuple[object, ...]:
    return (
        event.get("content_sha256"),
        event.get("occurrence_date"),
        event.get("offense_type"),
        event.get("legal_effect"),
        tuple(sorted(map(str, event.get("subject_ids", [])))),
        " ".join(str(event.get("title") or "").split()).casefold(),
    )


def _merge_canonical_events(
    aggregate_events: list[dict[str, object]],
    source_events: list[dict[str, object]],
    category: str,
) -> None:
    existing_by_key = {_canonical_event_key(event): event for event in aggregate_events}
    for event in source_events:
        event_key = _canonical_event_key(event)
        canonical_event = existing_by_key.get(event_key)
        if canonical_event is None:
            canonical_event = deepcopy(event)
            aggregate_events.append(canonical_event)
            existing_by_key[event_key] = canonical_event
            continue
        canonical_provenance = canonical_event.get("provenance")
        incoming_provenance = event.get("provenance")
        if not isinstance(canonical_provenance, list) or not isinstance(incoming_provenance, list):
            raise ManifestError(f"{category}: event provenance is invalid")
        for provenance in incoming_provenance:
            if provenance not in canonical_provenance:
                canonical_provenance.append(provenance)


def _normalize_event(
    event: dict[str, object],
    *,
    response_schema: str,
    subjects: dict[str, dict[str, object]],
    source_id: str,
    source_exchange: str,
    query_issuer_code: str,
    category: str,
    query_start: date,
    as_of: date,
    include_open_before_start: bool,
    document_path: Path,
    expected_content_sha256: str | None,
    document_fetcher: DocumentFetcher,
    live_document_hashes: dict[str, str],
) -> dict[str, object]:
    if response_schema == "native_json_event_page_v1":
        event = _bind_native_event_subjects(event, subjects, category)
    record_id = str(event.get("record_id") or "").strip()
    if not record_id:
        raise ManifestError(f"{category}: event record_id is missing")
    if "content_file" in event:
        raise ManifestError(
            f"{category}: local content_file must not appear in official response evidence"
        )
    if str(event.get("issuer_code") or "") != query_issuer_code:
        raise ManifestError(f"{category}: event issuer does not match ticker")
    event_subject_ids = event.get("subject_ids")
    if (
        not isinstance(event_subject_ids, list)
        or not event_subject_ids
        or not set(map(str, event_subject_ids)).issubset(subjects)
    ):
        raise ManifestError(f"{category}: event subject binding is invalid")
    occurrence_date = _parse_date(
        event.get("occurrence_date"),
        f"{category}.event.occurrence_date",
    )
    publication_time = _parse_datetime(
        event.get("publication_time"),
        f"{category}.event.publication_time",
    )
    status_effective_time = _parse_datetime(
        event.get("status_effective_time"),
        f"{category}.event.status_effective_time",
    )
    if occurrence_date > as_of:
        raise ManifestError(f"{category}: occurrence_date is after AS_OF")
    publication_date = publication_time.astimezone(EXCHANGE_TIMEZONES[source_exchange]).date()
    if publication_date > as_of:
        raise ManifestError(f"{category}: publication_time is after AS_OF")
    status_effective_date = status_effective_time.astimezone(
        EXCHANGE_TIMEZONES[source_exchange]
    ).date()
    if status_effective_date > as_of:
        raise ManifestError(f"{category}: status_effective_time is after AS_OF")
    title = str(event.get("title") or "").strip()
    status = str(event.get("status") or "").strip()
    if not title or status not in EVENT_STATUSES:
        raise ManifestError(f"{category}: invalid event title or status")
    open_before_window = status in {"pending", "investigation"} and include_open_before_start
    if (occurrence_date < query_start or publication_date < query_start) and not open_before_window:
        raise ManifestError(f"{category}: event is outside the declared query window")
    if not document_path.is_absolute() or not document_path.is_file():
        if expected_content_sha256 is None:
            raise ManifestError(
                f"{category}: document_files must map every event to an existing absolute path"
            )
        raise ManifestError(f"{category}: stored document hash differs")
    if (
        category in {"formal_sanctions", "related_party_harm"}
        and status not in FINAL_EVENT_STATUSES
    ):
        raise ManifestError(f"{category}: status must represent a final or effective action")
    offense_type = str(event.get("offense_type") or "").strip()
    legal_effect = str(event.get("legal_effect") or "").strip()
    if offense_type not in OFFENSE_TYPES:
        raise ManifestError(f"{category}: event offense_type is invalid")
    if legal_effect not in EVENT_STATUSES or legal_effect != status:
        raise ManifestError(f"{category}: event legal_effect is invalid for status")
    role_map = event.get("subject_role_at_occurrence")
    connection_map = event.get("issuer_connection")
    bound_subject_ids = set(map(str, event_subject_ids))
    if (
        not isinstance(role_map, dict)
        or not isinstance(connection_map, dict)
        or set(map(str, role_map)) != bound_subject_ids
        or set(map(str, connection_map)) != bound_subject_ids
    ):
        raise ManifestError(f"{category}: event per-subject attribution is incomplete")
    normalized_roles: dict[str, str] = {}
    normalized_connections: dict[str, str] = {}
    for subject_id in bound_subject_ids:
        subject = subjects[subject_id]
        role_at_occurrence = str(role_map.get(subject_id) or "").strip()
        issuer_connection = str(connection_map.get(subject_id) or "").strip()
        if role_at_occurrence != subject["role"]:
            raise ManifestError(f"{category}: event role differs from official roster role")
        if issuer_connection not in ISSUER_CONNECTIONS:
            raise ManifestError(f"{category}: issuer_connection is invalid")
        valid_connections_by_type = {
            "issuer": {"issuer"},
            "controller": {
                "controller_at_occurrence",
                "historical_controller",
                "unknown",
            },
            "management": {
                "serving_at_occurrence",
                "former_but_conduct_during_tenure",
                "post_tenure_issuer_related",
                "post_tenure_unrelated",
                "unknown",
            },
            "auditor": {
                "auditor_at_occurrence",
                "former_auditor_for_period",
                "unknown",
            },
        }
        subject_type = str(subject["type"])
        if issuer_connection not in valid_connections_by_type[subject_type]:
            raise ManifestError(f"{category}: issuer_connection conflicts with subject type")
        if issuer_connection == "unknown" and status not in {"pending", "investigation"}:
            raise ManifestError(
                f"{category}: effective event cannot have unknown issuer_connection"
            )
        service_start = date.fromisoformat(str(subject["service_start"]))
        raw_service_end = subject["service_end"]
        service_end = date.fromisoformat(str(raw_service_end)) if raw_service_end else as_of
        active_at_occurrence = service_start <= occurrence_date <= service_end
        active_connections = {
            "serving_at_occurrence",
            "former_but_conduct_during_tenure",
            "controller_at_occurrence",
            "auditor_at_occurrence",
        }
        post_tenure_connections = {
            "post_tenure_issuer_related",
            "post_tenure_unrelated",
            "historical_controller",
            "former_auditor_for_period",
        }
        if issuer_connection in active_connections and not active_at_occurrence:
            raise ManifestError(f"{category}: issuer_connection conflicts with subject tenure")
        if issuer_connection in post_tenure_connections and active_at_occurrence:
            raise ManifestError(f"{category}: issuer_connection conflicts with subject tenure")
        normalized_roles[subject_id] = role_at_occurrence
        normalized_connections[subject_id] = issuer_connection
    document_url = _require_official_https(
        event.get("document_url"),
        f"{category}.document_url",
        source_exchange,
    )
    local_content_sha256 = _sha256(document_path)
    if expected_content_sha256 is not None and local_content_sha256 != expected_content_sha256:
        raise ManifestError(f"{category}: stored document hash differs")
    live_content_sha256 = live_document_hashes.get(document_url)
    if live_content_sha256 is None:
        live_content_sha256 = hashlib.sha256(document_fetcher(document_url)).hexdigest()
        live_document_hashes[document_url] = live_content_sha256
    if expected_content_sha256 is None:
        if live_content_sha256 != local_content_sha256:
            raise ManifestError(f"{category}: live official document differs from local evidence")
    elif live_content_sha256 != expected_content_sha256:
        raise ManifestError(f"{category}: live official document hash differs")
    return {
        "record_id": record_id,
        "source_id": source_id,
        "category": category,
        "subject_ids": list(map(str, event_subject_ids)),
        "title": title,
        "offense_type": offense_type,
        "legal_effect": legal_effect,
        "subject_role_at_occurrence": normalized_roles,
        "issuer_connection": normalized_connections,
        "occurrence_date": occurrence_date.isoformat(),
        "publication_time": publication_time.isoformat(),
        "status": status,
        "status_effective_time": status_effective_time.isoformat(),
        "document_url": document_url,
        "document_path": str(document_path.resolve()),
        "content_sha256": local_content_sha256,
        "live_content_sha256": live_content_sha256,
        "provenance": [
            {
                "source_id": source_id,
                "record_id": record_id,
                "document_url": document_url,
            }
        ],
    }


def _load_response_pages(
    row: dict[str, object],
    category: str,
    query_params: dict[str, object],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    int,
    list[dict[str, object]],
    list[bytes],
]:
    raw_paths = row.get("response_files")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ManifestError(f"{category}: response_files must be a non-empty list")

    pages: dict[int, dict[str, object]] = {}
    page_count: int | None = None
    total: int | None = None
    response_schema = str(row.get("response_schema") or "")
    raw_adapter = row.get("response_adapter")
    response_adapter = raw_adapter if isinstance(raw_adapter, dict) else {}
    if response_schema not in {
        "canonical_event_page_v1",
        "native_json_event_page_v1",
    }:
        raise ManifestError(f"{category}: response_schema is unsupported")
    if response_schema == "native_json_event_page_v1" and not response_adapter:
        raise ManifestError(f"{category}: response_adapter must be an object")

    response_evidence: list[dict[str, object]] = []
    page_events: dict[int, list[dict[str, object]]] = {}
    page_bodies: dict[int, bytes] = {}
    for raw_path in raw_paths:
        response_path = Path(str(raw_path))
        if not response_path.is_absolute() or not response_path.is_file():
            raise ManifestError(
                f"{category}: every response_file must be an existing absolute path"
            )
        try:
            raw_body = response_path.read_bytes()
            payload = json.loads(raw_body.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManifestError(f"{category}: cannot parse response page: {exc}") from exc
        if not isinstance(payload, dict):
            raise ManifestError(f"{category}: response page must be an object")
        if response_schema == "canonical_event_page_v1":
            if payload.get("query") != query_params:
                raise ManifestError(f"{category}: response query does not match query_params")
            page_no = payload.get("page_no")
            current_page_count = payload.get("page_count")
            current_total = payload.get("total")
            results = payload.get("results")
        else:
            page_no, current_page_count, current_total, results = _native_event_page(
                payload,
                response_adapter,
                category,
            )
        if (
            not isinstance(page_no, int)
            or page_no < 1
            or not isinstance(current_page_count, int)
            or current_page_count < 1
            or not isinstance(current_total, int)
            or current_total < 0
            or not isinstance(results, list)
        ):
            raise ManifestError(f"{category}: invalid response pagination schema")
        if page_no in pages:
            raise ManifestError(f"{category}: duplicate response page {page_no}")
        if page_count is not None and current_page_count != page_count:
            raise ManifestError(f"{category}: inconsistent response page_count")
        if total is not None and current_total != total:
            raise ManifestError(f"{category}: inconsistent response total")
        page_count = current_page_count
        total = current_total
        pages[page_no] = payload
        page_events[page_no] = results
        page_bodies[page_no] = raw_body
        response_evidence.append(
            {
                "page_no": page_no,
                "path": str(response_path),
                "sha256": hashlib.sha256(raw_body).hexdigest(),
            }
        )

    assert page_count is not None and total is not None
    if set(pages) != set(range(1, page_count + 1)):
        raise ManifestError(f"{category}: response pagination is incomplete")
    events: list[dict[str, object]] = []
    for page_no in range(1, page_count + 1):
        for event in page_events[page_no]:
            if not isinstance(event, dict):
                raise ManifestError(f"{category}: response event must be an object")
            events.append(event)
    if total != len(events):
        raise ManifestError(f"{category}: response total does not match parsed event count")
    ordered_pages = [pages[page_no] for page_no in range(1, page_count + 1)]
    ordered_bodies = [page_bodies[page_no] for page_no in range(1, page_count + 1)]
    return events, response_evidence, total, ordered_pages, ordered_bodies


def _validate_subject_roster(
    bundle: dict[str, object],
    exchange: str,
    ticker_code: str,
    listing_date: date,
    as_of: date,
    roster_fetcher: RosterFetcher,
) -> tuple[dict[str, object], str, list[dict[str, object]]]:
    raw_roster = bundle.get("subject_roster")
    if not isinstance(raw_roster, dict):
        raise ManifestError("subject_roster must be an object")
    coverage_start = _parse_date(raw_roster.get("coverage_start"), "subject_roster.coverage_start")
    coverage_end = _parse_date(raw_roster.get("coverage_end"), "subject_roster.coverage_end")
    if coverage_start > listing_date or coverage_end != as_of:
        raise ManifestError("subject_roster does not cover the full listing history")
    if raw_roster.get("management_history_complete") is not True:
        raise ManifestError("subject_roster management history is not complete")
    if raw_roster.get("controller_history_complete") is not True:
        raise ManifestError("subject_roster controller history is not complete")
    roles = raw_roster.get("management_roles_covered")
    if not isinstance(roles, list) or not {
        "director",
        "senior_management",
        "chair",
        "cfo",
    }.issubset(set(map(str, roles))):
        raise ManifestError("subject_roster must cover directors,senior management,chair and cfo")
    controller_status = str(raw_roster.get("controller_status") or "")
    if controller_status not in CONTROLLER_STATUSES:
        raise ManifestError("subject_roster controller_status is invalid")
    source_url = _require_official_https(
        raw_roster.get("source_url"), "subject_roster.source_url", exchange
    )
    http_method = str(raw_roster.get("http_method") or "GET")
    request_encoding = str(raw_roster.get("request_encoding") or "query")
    query_params = raw_roster.get("query_params")
    response_schema = str(raw_roster.get("response_schema") or "canonical_subject_roster_v1")
    raw_adapter = raw_roster.get("response_adapter")
    response_adapter = raw_adapter if isinstance(raw_adapter, dict) else {}
    request_headers = raw_roster.get("request_headers", {})
    if response_schema == "canonical_subject_roster_v1":
        if (
            not isinstance(query_params, dict)
            or str(query_params.get("issuer_code") or "") != ticker_code
            or query_params.get("start_date") != coverage_start.isoformat()
            or query_params.get("end_date") != coverage_end.isoformat()
        ):
            raise ManifestError("subject_roster.query_params do not match issuer or coverage")
    elif response_schema == "native_json_roster_v1":
        query_params = _validate_request_bindings(
            query_params,
            response_adapter.get("request_bindings"),
            {
                "issuer": ticker_code,
                "start_date": coverage_start.isoformat(),
                "end_date": coverage_end.isoformat(),
            },
            "subject_roster.query_params",
        )
    else:
        raise ManifestError("subject_roster response_schema is unsupported")
    source_path = Path(str(raw_roster.get("source_file") or ""))
    if not source_path.is_absolute() or not source_path.is_file():
        raise ManifestError("subject_roster.source_file must be an existing absolute path")
    try:
        source_body = source_path.read_bytes()
        source_payload = json.loads(source_body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"subject_roster source evidence must be valid JSON: {exc}") from exc
    if not isinstance(source_payload, dict):
        raise ManifestError("subject_roster source evidence must be an object")
    if (
        response_schema == "canonical_subject_roster_v1"
        and source_payload.get("query") != query_params
    ):
        raise ManifestError("subject_roster source response query does not match query_params")
    assert isinstance(query_params, dict)
    try:
        live_response = _fetch_identity_response(
            roster_fetcher,
            source_url,
            http_method,
            request_encoding,
            query_params,
            request_headers,
        )
        live_payload = json.loads(live_response.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"subject_roster live official response is invalid: {exc}") from exc
    if live_response != source_body:
        raise ManifestError(
            "subject_roster live official response byte hash differs from source evidence"
        )
    if live_payload != source_payload:
        raise ManifestError("subject_roster live official response differs from source evidence")
    evidence_fields: dict[str, object] = {
        "coverage_start": coverage_start.isoformat(),
        "coverage_end": coverage_end.isoformat(),
        "management_history_complete": True,
        "controller_history_complete": True,
        "management_roles_covered": list(map(str, roles)),
        "controller_status": controller_status,
    }
    if response_schema == "canonical_subject_roster_v1":
        if any(source_payload.get(key) != value for key, value in evidence_fields.items()):
            raise ManifestError("subject_roster source evidence does not match declared coverage")
        evidence_subjects = source_payload.get("subjects")
        if not isinstance(evidence_subjects, list) or not evidence_subjects:
            raise ManifestError("subject_roster source evidence has no subjects")
        official_result_total = source_payload.get("official_result_total")
        if not isinstance(official_result_total, int) or official_result_total != len(
            evidence_subjects
        ):
            raise ManifestError("subject_roster roster evidence total does not match subjects")
    else:
        evidence_subjects, official_result_total = _native_roster_subjects(
            source_payload,
            response_adapter,
            bundle.get("subjects"),
        )
    return (
        {
            **evidence_fields,
            "source_url": source_url,
            "http_method": http_method,
            "request_encoding": request_encoding,
            "request_headers": request_headers,
            "response_schema": response_schema,
            "response_adapter": response_adapter,
            "query_params": query_params,
            "source_file": str(source_path),
            "source_sha256": hashlib.sha256(source_body).hexdigest(),
            "live_response_sha256": hashlib.sha256(live_response).hexdigest(),
            "official_result_total": official_result_total,
        },
        controller_status,
        evidence_subjects,
    )


def _normalize_listing_profile_response(
    payload: dict[str, object],
    response_schema: str,
    response_adapter: dict[str, object],
    query_params: dict[str, object],
    exchange: str,
    ticker_code: str,
    as_of: date,
) -> dict[str, object]:
    if response_schema == "canonical_listing_profile_v1":
        if payload.get("query") != query_params:
            raise ManifestError("official listing profile evidence does not match ticker")
        profile_fields = {
            "issuer_code": payload.get("issuer_code"),
            "listing_codes": payload.get("listing_codes"),
            "listing_date": payload.get("listing_date"),
            "listing_dates": payload.get("listing_dates"),
            "listing_status": payload.get("listing_status", "listed"),
            "delisting_date": payload.get("delisting_date"),
            "listing_statuses": payload.get("listing_statuses"),
            "delisting_dates": payload.get("delisting_dates"),
            "official_result_total": payload.get("official_result_total"),
        }
    elif response_schema == "native_json_listing_profile_v1":
        field_paths = _adapter_field_paths(
            response_adapter,
            LISTING_PROFILE_ADAPTER_FIELDS,
            "listing_profile.response_adapter",
        )
        profile_fields = {
            field: _adapt_field_value(
                payload,
                response_adapter,
                field_paths,
                field,
                "listing_profile",
            )
            for field in field_paths
        }
    else:
        raise ManifestError("official listing profile response_schema is unsupported")

    if (
        str(profile_fields.get("issuer_code") or "") != ticker_code
        or not isinstance(profile_fields.get("official_result_total"), int)
        or int(profile_fields["official_result_total"]) < 1
    ):
        raise ManifestError("official listing profile evidence does not match ticker")
    listing_date = _parse_date(
        profile_fields.get("listing_date"),
        "listing_profile.listing_date",
    )
    if listing_date > as_of:
        raise ManifestError("listing_date cannot be after AS_OF")
    raw_listing_codes = profile_fields.get("listing_codes")
    raw_listing_dates = profile_fields.get("listing_dates")
    if not isinstance(raw_listing_codes, dict) or not isinstance(raw_listing_dates, dict):
        raise ManifestError("official listing profile must provide listing_codes and listing_dates")
    jurisdictions = set(map(str, raw_listing_codes))
    if jurisdictions != set(map(str, raw_listing_dates)):
        raise ManifestError(
            "official listing profile listing_codes and listing_dates must "
            "cover identical jurisdictions"
        )
    if exchange not in jurisdictions or not jurisdictions <= {"SH", "SZ", "HK"}:
        raise ManifestError("official listing profile listing_codes do not cover ticker exchange")
    a_share_jurisdictions = jurisdictions & {"SH", "SZ"}
    if (
        len(jurisdictions) > 2
        or len(a_share_jurisdictions) > 1
        or (len(jurisdictions) == 2 and jurisdictions != {*a_share_jurisdictions, "HK"})
    ):
        raise ManifestError("official listing profile has invalid listing jurisdictions")

    listing_codes: dict[str, str] = {}
    listing_dates: dict[str, date] = {}
    for jurisdiction in sorted(jurisdictions):
        listing_codes[jurisdiction] = _normalize_listing_code(
            jurisdiction,
            raw_listing_codes[jurisdiction],
        )
        listing_dates[jurisdiction] = _parse_date(
            raw_listing_dates[jurisdiction],
            f"listing_profile.listing_dates.{jurisdiction}",
        )
    raw_listing_statuses = profile_fields.get("listing_statuses")
    raw_delisting_dates = profile_fields.get("delisting_dates")
    if raw_listing_statuses is None:
        raw_listing_statuses = {
            jurisdiction: profile_fields.get("listing_status", "listed")
            for jurisdiction in jurisdictions
        }
    if raw_delisting_dates is None:
        raw_delisting_dates = {
            jurisdiction: profile_fields.get("delisting_date") for jurisdiction in jurisdictions
        }
    if (
        not isinstance(raw_listing_statuses, dict)
        or not isinstance(raw_delisting_dates, dict)
        or set(map(str, raw_listing_statuses)) != jurisdictions
        or set(map(str, raw_delisting_dates)) != jurisdictions
    ):
        raise ManifestError("listing statuses and delisting dates must cover every jurisdiction")

    listing_statuses: dict[str, str] = {}
    delisting_dates: dict[str, str | None] = {}
    for jurisdiction in sorted(jurisdictions):
        status = str(raw_listing_statuses[jurisdiction] or "")
        if status not in {"listed", "delisted", "suspended"}:
            raise ManifestError(f"listing_statuses.{jurisdiction} is invalid")
        raw_delisting = raw_delisting_dates[jurisdiction]
        delisting_date = (
            None
            if raw_delisting is None
            else _parse_date(
                raw_delisting,
                f"listing_profile.delisting_dates.{jurisdiction}",
            )
        )
        if status == "delisted" and delisting_date is None:
            raise ManifestError(f"delisting_dates.{jurisdiction} is required when delisted")
        if status != "delisted" and delisting_date is not None:
            raise ManifestError(f"listing_statuses.{jurisdiction} conflicts with delisting date")
        if delisting_date is not None and delisting_date < listing_dates[jurisdiction]:
            raise ManifestError(f"delisting_dates.{jurisdiction} cannot precede listing date")
        listing_statuses[jurisdiction] = status
        delisting_dates[jurisdiction] = delisting_date.isoformat() if delisting_date else None
    if listing_codes[exchange] != ticker_code:
        raise ManifestError("official listing profile listing_codes do not match ticker")
    if listing_dates[exchange] != listing_date:
        raise ManifestError("official listing profile listing_date differs from listing_dates")
    return {
        "official_result_total": int(profile_fields["official_result_total"]),
        "listing_codes": listing_codes,
        "listing_date": listing_date.isoformat(),
        "listing_dates": {
            jurisdiction: value.isoformat() for jurisdiction, value in listing_dates.items()
        },
        "listing_status": listing_statuses[exchange],
        "delisting_date": delisting_dates[exchange],
        "listing_statuses": listing_statuses,
        "delisting_dates": delisting_dates,
    }


def _listing_jurisdictions(
    listing_profile: dict[str, object],
    as_of: date,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    raw_codes = listing_profile.get("listing_codes")
    raw_dates = listing_profile.get("listing_dates")
    raw_delisting_dates = listing_profile.get("delisting_dates")
    if (
        not isinstance(raw_codes, dict)
        or not isinstance(raw_dates, dict)
        or not isinstance(raw_delisting_dates, dict)
    ):
        raise ManifestError("listing_profile jurisdiction evidence is invalid")
    all_codes = {
        str(jurisdiction): _normalize_listing_code(str(jurisdiction), code)
        for jurisdiction, code in raw_codes.items()
    }
    try:
        listing_dates = {
            jurisdiction: date.fromisoformat(str(raw_dates[jurisdiction]))
            for jurisdiction in all_codes
        }
        delisting_dates = {
            jurisdiction: (
                None
                if raw_delisting_dates[jurisdiction] is None
                else date.fromisoformat(str(raw_delisting_dates[jurisdiction]))
            )
            for jurisdiction in all_codes
        }
    except (KeyError, ValueError) as exc:
        raise ManifestError("listing_profile jurisdiction evidence is invalid") from exc
    historical_codes = {
        jurisdiction: code
        for jurisdiction, code in all_codes.items()
        if listing_dates[jurisdiction] <= as_of
    }
    active_codes = {
        jurisdiction: code
        for jurisdiction, code in historical_codes.items()
        if delisting_dates[jurisdiction] is None or delisting_dates[jurisdiction] > as_of
    }
    future_codes = {
        jurisdiction: code
        for jurisdiction, code in all_codes.items()
        if listing_dates[jurisdiction] > as_of
    }
    return active_codes, historical_codes, future_codes


def _validate_listing_profile(
    bundle: dict[str, object],
    exchange: str,
    ticker_code: str,
    as_of: date,
    profile_fetcher: RosterFetcher,
) -> tuple[dict[str, object], date]:
    raw_profile = bundle.get("listing_profile")
    if not isinstance(raw_profile, dict):
        raise ManifestError("official listing profile must be an object")
    source_url = _require_official_https(
        raw_profile.get("source_url"), "listing_profile.source_url", exchange
    )
    http_method = str(raw_profile.get("http_method") or "GET")
    request_encoding = str(raw_profile.get("request_encoding") or "query")
    query_params = raw_profile.get("query_params")
    response_schema = str(raw_profile.get("response_schema") or "canonical_listing_profile_v1")
    raw_adapter = raw_profile.get("response_adapter")
    response_adapter = raw_adapter if isinstance(raw_adapter, dict) else {}
    request_headers = raw_profile.get("request_headers", {})
    request_bootstrap = raw_profile.get("request_bootstrap")
    if response_schema == "canonical_listing_profile_v1":
        if (
            not isinstance(query_params, dict)
            or str(query_params.get("issuer_code") or "") != ticker_code
        ):
            raise ManifestError("official listing profile query does not match ticker")
    elif response_schema == "native_json_listing_profile_v1":
        query_params = _validate_request_bindings(
            query_params,
            response_adapter.get("request_bindings"),
            {"issuer": ticker_code},
            "listing_profile.query_params",
        )
    else:
        raise ManifestError("official listing profile response_schema is unsupported")
    source_path = Path(str(raw_profile.get("source_file") or ""))
    if not source_path.is_absolute() or not source_path.is_file():
        raise ManifestError(
            "official listing profile source_file must be an existing absolute path"
        )
    try:
        source_body = source_path.read_bytes()
        source_payload = json.loads(source_body.decode("utf-8"))
        live_body = _fetch_identity_response(
            profile_fetcher,
            source_url,
            http_method,
            request_encoding,
            query_params,
            request_headers,
            request_bootstrap,
        )
        live_payload = json.loads(live_body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"official listing profile evidence is invalid: {exc}") from exc
    if not isinstance(source_payload, dict) or not isinstance(live_payload, dict):
        raise ManifestError("official listing profile evidence does not match ticker")
    normalized_profile = _normalize_listing_profile_response(
        source_payload,
        response_schema,
        response_adapter,
        query_params,
        exchange,
        ticker_code,
        as_of,
    )
    normalized_live_profile = _normalize_listing_profile_response(
        live_payload,
        response_schema,
        response_adapter,
        query_params,
        exchange,
        ticker_code,
        as_of,
    )
    if (
        live_body != source_body
        or live_payload != source_payload
        or normalized_live_profile != normalized_profile
    ):
        raise ManifestError(
            "official listing profile live official response byte hash differs from source evidence"
        )
    listing_date = date.fromisoformat(str(normalized_profile["listing_date"]))
    listing_codes = normalized_profile["listing_codes"]
    normalized_listing_dates = normalized_profile["listing_dates"]
    assert isinstance(listing_codes, dict)
    assert isinstance(normalized_listing_dates, dict)
    declared_listing_codes = bundle.get("listing_codes")
    if declared_listing_codes is not None and declared_listing_codes != listing_codes:
        raise ManifestError("declared listing_codes differ from official listing profile")
    declared_listing_dates = bundle.get("listing_dates")
    if declared_listing_dates is not None and declared_listing_dates != normalized_listing_dates:
        raise ManifestError("declared listing_dates differ from official listing profile")
    declared_listing_date = bundle.get("listing_date")
    if (
        declared_listing_date is not None
        and _parse_date(declared_listing_date, "listing_date") != listing_date
    ):
        raise ManifestError("declared listing_date differs from official listing profile")
    return (
        {
            "source_url": source_url,
            "http_method": http_method,
            "request_encoding": request_encoding,
            "request_headers": request_headers,
            **({"request_bootstrap": request_bootstrap} if request_bootstrap is not None else {}),
            "query_params": query_params,
            "response_schema": response_schema,
            "response_adapter": response_adapter,
            "source_file": str(source_path),
            "source_sha256": hashlib.sha256(source_body).hexdigest(),
            "live_response_sha256": hashlib.sha256(live_body).hexdigest(),
            **normalized_profile,
        },
        listing_date,
    )


def build_manifest(
    bundle_path: Path,
    *,
    roster_fetcher: RosterFetcher = _fetch_official_roster,
    event_fetcher: EventFetcher = _fetch_official_event_pages,
    document_fetcher: DocumentFetcher = _fetch_official_document,
) -> dict[str, object]:
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read bundle: {exc}") from exc
    if not isinstance(bundle, dict):
        raise ManifestError("bundle must be a JSON object")

    ticker, exchange, ticker_code = _canonical_identity(
        bundle.get("ticker"), bundle.get("exchange")
    )
    issuer_code = str(bundle.get("query_issuer_code") or "")
    if issuer_code != ticker_code:
        raise ManifestError("bundle query issuer does not match ticker")
    as_of = _parse_date(bundle.get("AS_OF"), "AS_OF")
    issuer_type = str(bundle.get("issuer_type") or "non_bank")
    if issuer_type not in {"bank", "insurer", "non_bank"}:
        raise ManifestError("issuer_type must be bank, insurer, or non_bank")
    declared_listing_date = _parse_date(bundle.get("listing_date"), "listing_date")
    if declared_listing_date > as_of:
        raise ManifestError("listing_date cannot be after AS_OF")
    listing_profile, listing_date = _validate_listing_profile(
        bundle,
        exchange,
        ticker_code,
        as_of,
        roster_fetcher,
    )
    all_listing_dates = {
        jurisdiction: _parse_date(value, f"listing_dates.{jurisdiction}")
        for jurisdiction, value in dict(listing_profile["listing_dates"]).items()
    }
    listing_codes, historical_listing_codes, future_listing_codes = _listing_jurisdictions(
        listing_profile, as_of
    )
    listing_dates = {
        jurisdiction: listing_date_value
        for jurisdiction, listing_date_value in all_listing_dates.items()
        if listing_date_value <= as_of
    }
    if exchange not in listing_codes:
        raise ManifestError("ticker exchange was not listed at AS_OF")
    listing_history_start = min(listing_dates.values())
    subject_roster, controller_status, evidence_subjects = _validate_subject_roster(
        bundle,
        exchange,
        ticker_code,
        listing_history_start,
        as_of,
        roster_fetcher,
    )
    raw_subjects = bundle.get("subjects")
    if not isinstance(raw_subjects, list) or not raw_subjects:
        raise ManifestError("subjects must be a non-empty list")
    subjects: dict[str, dict[str, str]] = {}
    official_subject_segments: dict[str, list[dict[str, str]]] = {}
    for subject in raw_subjects:
        if not isinstance(subject, dict):
            raise ManifestError("each subject must be an object")
        subject_id = str(subject.get("id") or "").strip()
        subject_type = str(subject.get("type") or "").strip()
        subject_name = str(subject.get("name") or "").strip()
        role = str(subject.get("role") or "").strip()
        official_id = str(subject.get("official_id") or "").strip()
        if (
            not subject_id
            or subject_id in subjects
            or subject_type not in SUBJECT_TYPES
            or not subject_name
            or not official_id
        ):
            raise ManifestError("invalid or duplicate subject")
        if subject_type != "issuer" and subject_name.casefold() in GENERIC_SUBJECT_NAMES:
            raise ManifestError("historical management roster must use legal subject names")
        valid_roles = (
            {"issuer"}
            if subject_type == "issuer"
            else {"controller"}
            if subject_type == "controller"
            else {"auditor"}
            if subject_type == "auditor"
            else MANAGEMENT_ROLES
        )
        if role not in valid_roles:
            raise ManifestError(f"{subject_id}: role is invalid for {subject_type}")
        service_start = _parse_date(subject.get("service_start"), f"{subject_id}.service_start")
        raw_service_end = subject.get("service_end")
        service_end = (
            _parse_date(raw_service_end, f"{subject_id}.service_end")
            if raw_service_end is not None
            else None
        )
        if (
            service_start > as_of
            or (service_end is not None and service_end < service_start)
            or (service_end is not None and service_end > as_of)
        ):
            raise ManifestError(f"{subject_id}: invalid service period")
        normalized_subject = {
            "id": subject_id,
            "type": subject_type,
            "name": subject_name,
            "role": role,
            "official_id": official_id,
            "service_start": service_start.isoformat(),
            "service_end": service_end.isoformat() if service_end else None,
        }
        for existing in official_subject_segments.get(official_id, []):
            if existing["type"] != subject_type or existing["name"] != subject_name:
                raise ManifestError("subjects contain a duplicate official_id")
            existing_start = date.fromisoformat(existing["service_start"])
            existing_end = (
                date.fromisoformat(existing["service_end"]) if existing["service_end"] else as_of
            )
            periods_overlap = service_start <= existing_end and existing_start <= (
                service_end or as_of
            )
            if existing["role"] == role and periods_overlap:
                raise ManifestError("subjects contain an ambiguous official_id role tenure")
        official_subject_segments.setdefault(official_id, []).append(normalized_subject)
        subjects[subject_id] = normalized_subject
    present_subject_types = {subject["type"] for subject in subjects.values()}
    required_subject_types = {"issuer", "management", "auditor"}
    if controller_status == "identified":
        required_subject_types.add("controller")
    elif "controller" in present_subject_types:
        raise ManifestError("controller subjects conflict with none_identified controller_status")
    missing_subject_types = required_subject_types - present_subject_types
    if missing_subject_types:
        raise ManifestError(
            "subjects do not cover the evidenced historical roster; "
            f"missing={sorted(missing_subject_types)}"
        )
    evidence_by_id: dict[str, dict[str, object]] = {}
    for evidence_subject in evidence_subjects:
        if not isinstance(evidence_subject, dict):
            raise ManifestError("subject_roster roster evidence subject is invalid")
        evidence_id = str(evidence_subject.get("id") or "")
        if not evidence_id or evidence_id in evidence_by_id:
            raise ManifestError("subject_roster roster evidence subject is missing or duplicate")
        evidence_by_id[evidence_id] = evidence_subject
    if set(evidence_by_id) != set(subjects):
        raise ManifestError("subject_roster roster evidence does not match declared subjects")
    for subject_id, subject in subjects.items():
        if evidence_by_id[subject_id] != subject:
            raise ManifestError(f"subject_roster roster evidence differs for {subject_id}")

    def require_continuous_role_history(role: str, subject_type: str) -> None:
        periods = sorted(
            (
                date.fromisoformat(subject["service_start"]),
                date.fromisoformat(subject["service_end"]) if subject["service_end"] else as_of,
            )
            for subject in subjects.values()
            if subject["type"] == subject_type and subject["role"] == role
        )
        cursor = listing_history_start
        for period_start, period_end in periods:
            if period_start > cursor:
                break
            cursor = max(cursor, period_end + timedelta(days=1))
            if cursor > as_of:
                return
        raise ManifestError(f"historical management roster has incomplete {role} tenure coverage")

    for required_role in ("chair", "cfo"):
        require_continuous_role_history(required_role, "management")
    if controller_status == "identified":
        require_continuous_role_history("controller", "controller")

    raw_categories = bundle.get("categories")
    if not isinstance(raw_categories, list):
        raise ManifestError("categories must be a list")
    by_name: dict[str, list[dict[str, object]]] = {}
    for row in raw_categories:
        if not isinstance(row, dict):
            raise ManifestError("each category must be an object")
        category = str(row.get("category") or "")
        by_name.setdefault(category, []).append(row)
    if set(by_name) != set(REQUIRED_SCOPES):
        missing = sorted(set(REQUIRED_SCOPES) - set(by_name))
        extra = sorted(set(by_name) - set(REQUIRED_SCOPES))
        raise ManifestError(f"category set mismatch; missing={missing}, extra={extra}")
    for category, rows in by_name.items():
        source_ids = [str(row.get("source_id") or "") for row in rows]
        actual_source_ids = set(source_ids)
        required_source_ids = _required_source_ids(
            category,
            historical_listing_codes,
            issuer_type,
        )
        source_complete = required_source_ids.issubset(actual_source_ids)
        if not source_complete:
            raise ManifestError(
                f"{category}: required official sources are "
                f"{sorted(required_source_ids)}; "
                f"got={sorted(actual_source_ids)}"
            )
        if len(source_ids) != len(set(source_ids)):
            raise ManifestError(f"duplicate category source_id: {category}")
        for source_id, row in zip(source_ids, rows, strict=True):
            if source_id not in SOURCE_DOMAINS:
                raise ManifestError(f"{category}: unknown source_id {source_id}")
            hostname = (urlparse(str(row.get("query_url") or "")).hostname or "").lower()
            if not any(
                hostname == domain or hostname.endswith(f".{domain}")
                for domain in SOURCE_DOMAINS[source_id]
            ):
                raise ManifestError(
                    f"{category}: source_id {source_id} does not match its official domain"
                )

    queries: dict[str, dict[str, object]] = {}
    response_snapshots: dict[Path, bytes] = {}
    document_snapshots: dict[Path, str] = {}
    official_document_snapshots: list[tuple[str, Path, str, str]] = []
    live_document_hashes: dict[str, str] = {}
    listing_history_complete = True
    work_items = [
        (category, required_scope, row)
        for category, required_scope in REQUIRED_SCOPES.items()
        for row in by_name[category]
    ]
    for category, required_scope, row in work_items:
        source_id = str(row.get("source_id") or "")
        source_exchange = _source_exchange(source_id, historical_listing_codes)
        expected_query_issuer = historical_listing_codes[source_exchange]
        params = row.get("query_params")
        if row.get("scope") != required_scope:
            raise ManifestError(f"{category}: scope must be {required_scope}")
        query_start = _parse_date(row.get("query_start"), f"{category}.query_start")
        query_end = _parse_date(row.get("query_end"), f"{category}.query_end")
        if query_end != as_of:
            raise ManifestError(f"{category}: query_end must equal AS_OF")
        if required_scope == "listing_history":
            if query_start > listing_dates[source_exchange]:
                listing_history_complete = False
                raise ManifestError(f"{category}: query does not cover listing history")
        elif query_start > _subtract_years(as_of, 3):
            raise ManifestError(f"{category}: query does not cover the prior three years")
        elif not isinstance(params, dict) or params.get("include_open_before_start") is not True:
            raise ManifestError(
                f"{category}: rolling query must set include_open_before_start=true"
            )

        query_issuer = str(row.get("query_issuer_code") or "")
        if query_issuer != expected_query_issuer or not isinstance(params, dict):
            raise ManifestError(f"{category}: query issuer does not match ticker")
        response_schema = str(row.get("response_schema") or "")
        raw_response_adapter = row.get("response_adapter")
        response_adapter = raw_response_adapter if isinstance(raw_response_adapter, dict) else {}
        if response_schema == "canonical_event_page_v1":
            if str(params.get("issuer_code") or "") != query_issuer:
                raise ManifestError(f"{category}: query issuer does not match ticker")
            request_bindings = {
                "issuer": "issuer_code",
                "category": "category",
                "start_date": "start_date",
                "end_date": "end_date",
            }
            query_subject_ids = params.get("subject_ids")
        elif response_schema == "native_json_event_page_v1":
            request_bindings = response_adapter.get(
                "request_bindings",
                {
                    "issuer": "stock",
                    "category": "kind",
                    "start_date": "from",
                    "end_date": "to",
                    "subject_ids": "subjects",
                },
            )
            _validate_request_bindings(
                params,
                request_bindings,
                {
                    "issuer": query_issuer,
                    "category": category,
                    "start_date": query_start.isoformat(),
                    "end_date": query_end.isoformat(),
                    "subject_ids": list(
                        dict.fromkeys(subject["official_id"] for subject in subjects.values())
                    ),
                },
                f"{category}.query_params",
            )
            query_subject_ids = row.get("query_subject_ids")
        else:
            raise ManifestError(f"{category}: response_schema is unsupported")
        effective_response_adapter = (
            {**response_adapter, "request_bindings": request_bindings}
            if response_schema == "native_json_event_page_v1"
            else {}
        )
        if not isinstance(query_subject_ids, list) or set(map(str, query_subject_ids)) != set(
            subjects
        ):
            raise ManifestError(f"{category}: query subject coverage is incomplete")
        if response_schema == "canonical_event_page_v1":
            if params.get("end_date") != query_end.isoformat():
                raise ManifestError(f"{category}: query end_date does not match AS_OF")
            if params.get("start_date") != query_start.isoformat():
                raise ManifestError(f"{category}: query start_date does not match query_start")
            if params.get("category") != category:
                raise ManifestError(f"{category}: query category does not match manifest category")
        query_url = _require_official_https(
            row.get("query_url"), f"{category}.query_url", source_exchange
        )
        http_method = str(row.get("http_method") or "")
        request_encoding = str(row.get("request_encoding") or "")
        request_headers = row.get("request_headers", {})
        (
            events,
            response_evidence,
            total,
            stored_pages,
            stored_bodies,
        ) = _load_response_pages(row, category, params)
        for evidence, body in zip(
            sorted(
                response_evidence,
                key=lambda item: int(item["page_no"]),
            ),
            stored_bodies,
            strict=True,
        ):
            response_path = Path(str(evidence["path"]))
            previous_body = response_snapshots.get(response_path)
            if previous_body is not None and previous_body != body:
                raise ManifestError(f"{category}: response path is reused with different bytes")
            response_snapshots[response_path] = body
        raw_document_files = row.get("document_files")
        if not isinstance(raw_document_files, dict):
            raise ManifestError(f"{category}: document_files must be an object")
        document_files = {
            str(record_id): Path(str(path)) for record_id, path in raw_document_files.items()
        }
        live_bodies = event_fetcher(
            query_url,
            http_method,
            request_encoding,
            params,
            {
                "response_schema": response_schema,
                "response_adapter": effective_response_adapter,
                "request_headers": request_headers,
            },
        )
        if live_bodies != stored_bodies:
            raise ManifestError(
                f"{category}: live official event response byte hash differs "
                "from stored response evidence"
            )
        try:
            live_pages = [json.loads(body.decode("utf-8")) for body in live_bodies]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManifestError(
                f"{category}: live official event response is invalid: {exc}"
            ) from exc
        if live_pages != stored_pages:
            raise ManifestError(
                f"{category}: live official event response differs from stored response evidence"
            )

        normalized_events: list[dict[str, object]] = []
        seen_record_ids: set[str] = set()
        for event in events:
            record_id = str(event.get("record_id") or "").strip()
            if not record_id or record_id in seen_record_ids:
                raise ManifestError(f"{category}: event record_id is missing or duplicate")
            seen_record_ids.add(record_id)
            content_path = document_files.get(record_id, Path())
            normalized_event = _normalize_event(
                event,
                response_schema=response_schema,
                subjects=subjects,
                source_id=source_id,
                source_exchange=source_exchange,
                query_issuer_code=query_issuer,
                category=category,
                query_start=query_start,
                as_of=as_of,
                include_open_before_start=(params.get("include_open_before_start") is True),
                document_path=content_path,
                expected_content_sha256=None,
                document_fetcher=document_fetcher,
                live_document_hashes=live_document_hashes,
            )
            local_content_sha256 = str(normalized_event["content_sha256"])
            previous_document_sha256 = document_snapshots.get(content_path)
            if (
                previous_document_sha256 is not None
                and previous_document_sha256 != local_content_sha256
            ):
                raise ManifestError(f"{category}: document path is reused with different bytes")
            document_snapshots[content_path] = local_content_sha256
            official_document_snapshots.append(
                (
                    str(normalized_event["document_url"]),
                    content_path,
                    local_content_sha256,
                    category,
                )
            )
            normalized_events.append(normalized_event)
        if set(document_files) != seen_record_ids:
            raise ManifestError(
                f"{category}: document_files keys do not match official event records"
            )

        ordered_evidence = sorted(
            response_evidence,
            key=lambda evidence: int(evidence["page_no"]),
        )
        if any(
            Path(str(evidence["path"])).read_bytes() != body
            for evidence, body in zip(
                ordered_evidence,
                stored_bodies,
                strict=True,
            )
        ):
            raise ManifestError(f"{category}: stored response changed during manifest construction")
        stored_response_sha256 = hashlib.sha256(b"".join(stored_bodies)).hexdigest()
        live_response_sha256 = hashlib.sha256(b"".join(live_bodies)).hexdigest()
        source_query = {
            "source_id": source_id,
            "query_issuer_code": query_issuer,
            "scope": required_scope,
            "query_start": query_start.isoformat(),
            "query_end": query_end.isoformat(),
            "query_url": query_url,
            "http_method": http_method,
            "request_encoding": request_encoding,
            "request_headers": request_headers,
            "response_schema": response_schema,
            "response_adapter": effective_response_adapter,
            "query_params": params,
            "query_subject_ids": list(map(str, query_subject_ids)),
            "include_open_before_start": params.get("include_open_before_start") is True,
            "response_sha256": stored_response_sha256,
            "live_response_sha256": live_response_sha256,
            "responses": response_evidence,
            "official_result_total": total,
            "result": "未检出" if total == 0 else "命中",
            "events": normalized_events,
        }
        existing_query = queries.get(category)
        if existing_query is None:
            queries[category] = {
                **source_query,
                "events": deepcopy(normalized_events),
                "source_count": 1,
                "sources": [source_query],
            }
        else:
            existing_events = existing_query["events"]
            assert isinstance(existing_events, list)
            sources = existing_query["sources"]
            assert isinstance(sources, list)
            sources.append(source_query)
            _merge_canonical_events(
                existing_events,
                normalized_events,
                category,
            )
            existing_query["source_count"] = len(sources)
            existing_query["official_result_total"] = (
                int(existing_query["official_result_total"]) + total
            )
            existing_query["result"] = (
                "命中" if int(existing_query["official_result_total"]) > 0 else "未检出"
            )

    for response_path, expected_body in response_snapshots.items():
        try:
            current_body = response_path.read_bytes()
        except OSError as exc:
            raise ManifestError(
                f"stored response changed during manifest construction: {exc}"
            ) from exc
        if current_body != expected_body:
            raise ManifestError("stored response changed during manifest construction")

    for document_path, expected_sha256 in document_snapshots.items():
        try:
            current_sha256 = _sha256(document_path)
        except OSError as exc:
            raise ManifestError(
                f"stored document changed during manifest construction: {exc}"
            ) from exc
        if current_sha256 != expected_sha256:
            raise ManifestError("stored document changed during manifest construction")

    roster_source_path = Path(str(subject_roster["source_file"]))
    try:
        roster_source_sha256 = _sha256(roster_source_path)
        roster_live_body = _fetch_identity_response(
            roster_fetcher,
            str(subject_roster["source_url"]),
            str(subject_roster["http_method"]),
            str(subject_roster["request_encoding"]),
            subject_roster["query_params"],
            subject_roster.get("request_headers", {}),
        )
    except OSError as exc:
        raise ManifestError(
            f"subject roster source changed during manifest construction: {exc}"
        ) from exc
    if (
        roster_source_sha256 != subject_roster["source_sha256"]
        or hashlib.sha256(roster_live_body).hexdigest() != subject_roster["source_sha256"]
    ):
        raise ManifestError("subject roster source changed during manifest construction")
    listing_source_path = Path(str(listing_profile["source_file"]))
    try:
        listing_source_sha256 = _sha256(listing_source_path)
        listing_live_body = _fetch_identity_response(
            roster_fetcher,
            str(listing_profile["source_url"]),
            str(listing_profile["http_method"]),
            str(listing_profile["request_encoding"]),
            listing_profile["query_params"],
            listing_profile.get("request_headers", {}),
            listing_profile.get("request_bootstrap"),
        )
    except OSError as exc:
        raise ManifestError(f"official listing profile changed during construction: {exc}") from exc
    if (
        listing_source_sha256 != listing_profile["source_sha256"]
        or hashlib.sha256(listing_live_body).hexdigest() != listing_profile["source_sha256"]
    ):
        raise ManifestError("official listing profile changed during manifest construction")

    for document_url, document_path, expected_sha256, category in official_document_snapshots:
        try:
            local_sha256 = _sha256(document_path)
        except OSError as exc:
            raise ManifestError(
                f"{category}: stored document changed during final revalidation: {exc}"
            ) from exc
        live_sha256 = hashlib.sha256(document_fetcher(document_url)).hexdigest()
        if local_sha256 != expected_sha256 or live_sha256 != expected_sha256:
            raise ManifestError(f"{category}: official document changed during final revalidation")

    return {
        "ticker": ticker,
        "exchange": exchange,
        "AS_OF": as_of.isoformat(),
        "查询发行人代码": ticker_code,
        "查询发行人代码映射": listing_codes,
        "future_listing_codes": future_listing_codes,
        "issuer_type": issuer_type,
        "listing_date": listing_date.isoformat(),
        "listing_history_complete": listing_history_complete,
        "live_revalidation_required": True,
        "listing_profile": listing_profile,
        "subject_roster": subject_roster,
        "subjects": list(subjects.values()),
        "event_count": sum(len(query["events"]) for query in queries.values()),
        "queries": queries,
    }


def _revalidate_publication_inputs(
    bundle_path: Path,
    expected_bundle_body: bytes,
    payload: dict[str, object],
) -> None:
    try:
        current_bundle_body = bundle_path.read_bytes()
        bundle = json.loads(current_bundle_body.decode("utf-8"))
        if current_bundle_body != expected_bundle_body or not isinstance(bundle, dict):
            raise ManifestError("bundle changed before publication")
        for profile_name in ("listing_profile", "subject_roster"):
            profile = payload.get(profile_name)
            if not isinstance(profile, dict):
                raise ManifestError(f"{profile_name} changed before publication")
            source_path = Path(str(profile.get("source_file") or ""))
            if _sha256(source_path) != profile.get("source_sha256"):
                raise ManifestError(f"{profile_name} changed before publication")

        queries = payload.get("queries")
        categories = bundle.get("categories")
        if not isinstance(queries, dict) or not isinstance(categories, list):
            raise ManifestError("bound evidence changed before publication")
        for row in categories:
            if not isinstance(row, dict):
                raise ManifestError("bound evidence changed before publication")
            category = str(row.get("category") or "")
            source_id = str(row.get("source_id") or "")
            query = queries.get(category)
            if not isinstance(query, dict):
                raise ManifestError(f"{category}: changed before publication")
            sources = query.get("sources")
            if not isinstance(sources, list):
                raise ManifestError(f"{category}: changed before publication")
            matching_sources = [
                source
                for source in sources
                if isinstance(source, dict) and source.get("source_id") == source_id
            ]
            if len(matching_sources) != 1:
                raise ManifestError(f"{category}: changed before publication")
            source = matching_sources[0]
            responses = source.get("responses")
            response_files = row.get("response_files")
            if not isinstance(responses, list) or not isinstance(response_files, list):
                raise ManifestError(f"{category}: changed before publication")
            expected_response_hashes = {
                str(response.get("path")): str(response.get("sha256"))
                for response in responses
                if isinstance(response, dict)
            }
            if set(map(str, response_files)) != set(expected_response_hashes):
                raise ManifestError(f"{category}: changed before publication")
            for response_file in response_files:
                response_path = Path(str(response_file))
                if _sha256(response_path) != expected_response_hashes[str(response_file)]:
                    raise ManifestError(f"{category}: response changed before publication")

            events = source.get("events")
            document_files = row.get("document_files")
            if not isinstance(events, list) or not isinstance(document_files, dict):
                raise ManifestError(f"{category}: changed before publication")
            expected_documents = {
                str(event.get("record_id")): str(event.get("content_sha256"))
                for event in events
                if isinstance(event, dict)
            }
            if set(map(str, document_files)) != set(expected_documents):
                raise ManifestError(f"{category}: changed before publication")
            for record_id, document_file in document_files.items():
                if _sha256(Path(str(document_file))) != expected_documents[str(record_id)]:
                    raise ManifestError(f"{category}: document changed before publication")
    except OSError as exc:
        raise ManifestError(f"bound evidence changed before publication: {exc}") from exc


def write_manifest(
    bundle_path: Path,
    output_path: Path,
    *,
    roster_fetcher: RosterFetcher = _fetch_official_roster,
    event_fetcher: EventFetcher = _fetch_official_event_pages,
    document_fetcher: DocumentFetcher = _fetch_official_document,
) -> Path:
    try:
        bundle_body = bundle_path.read_bytes()
    except OSError as exc:
        raise ManifestError(f"cannot snapshot bundle before publication: {exc}") from exc
    payload = build_manifest(
        bundle_path,
        roster_fetcher=roster_fetcher,
        event_fetcher=event_fetcher,
        document_fetcher=document_fetcher,
    )
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    target_path = output_path
    if output_path.exists():
        if output_path.read_text(encoding="utf-8") == serialized:
            return output_path
        content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        target_path = output_path.with_name(
            f"{output_path.stem}-{content_hash}{output_path.suffix}"
        )
        if target_path.exists():
            if target_path.read_text(encoding="utf-8") == serialized:
                return target_path
            raise ManifestError("content-addressed event manifest path contains different evidence")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(serialized)
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        os.chmod(temporary, 0o644)
        _revalidate_publication_inputs(bundle_path, bundle_body, payload)
        try:
            os.link(temporary, target_path)
        except FileExistsError as exc:
            try:
                existing = target_path.read_text(encoding="utf-8")
            except OSError as read_exc:
                raise ManifestError(
                    "concurrent event manifest disappeared during publication"
                ) from read_exc
            if existing == serialized:
                return target_path
            raise ManifestError(
                "event manifest already exists; refusing to overwrite evidence"
            ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target_path


def _events_from_live_pages(
    bodies: list[bytes],
    response_schema: str,
    raw_adapter: object,
    query_params: dict[str, object],
    category: str,
) -> tuple[list[dict[str, object]], int]:
    adapter = raw_adapter if isinstance(raw_adapter, dict) else {}
    pages: dict[int, list[dict[str, object]]] = {}
    page_count: int | None = None
    total: int | None = None
    for body in bodies:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManifestError(f"{category}: live response is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ManifestError(f"{category}: live response must be an object")
        if response_schema == "canonical_event_page_v1":
            if payload.get("query") != query_params:
                raise ManifestError(f"{category}: live response query differs")
            page_no = payload.get("page_no")
            current_page_count = payload.get("page_count")
            current_total = payload.get("total")
            results = payload.get("results")
        elif response_schema == "native_json_event_page_v1":
            page_no, current_page_count, current_total, results = _native_event_page(
                payload, adapter, category
            )
        else:
            raise ManifestError(f"{category}: response schema is unsupported")
        if (
            not isinstance(page_no, int)
            or not isinstance(current_page_count, int)
            or not isinstance(current_total, int)
            or not isinstance(results, list)
        ):
            raise ManifestError(f"{category}: live pagination is invalid")
        if page_no in pages:
            raise ManifestError(f"{category}: live response page is duplicated")
        if page_count is not None and page_count != current_page_count:
            raise ManifestError(f"{category}: live page count differs")
        if total is not None and total != current_total:
            raise ManifestError(f"{category}: live result total differs")
        page_count = current_page_count
        total = current_total
        pages[page_no] = results
    if page_count is None or total is None or set(pages) != set(range(1, page_count + 1)):
        raise ManifestError(f"{category}: live pages are incomplete")
    events: list[dict[str, object]] = []
    record_ids: set[str] = set()
    for page_no in range(1, page_count + 1):
        for result in pages[page_no]:
            if not isinstance(result, dict):
                raise ManifestError(f"{category}: live event is invalid")
            record_id = result.get("record_id")
            if not record_id or str(record_id) in record_ids:
                raise ManifestError(f"{category}: live event ID is invalid")
            record_ids.add(str(record_id))
            events.append(result)
    if len(record_ids) != total:
        raise ManifestError(f"{category}: live result total differs")
    return events, total


def revalidate_manifest(
    manifest_path: Path,
    *,
    roster_fetcher: RosterFetcher = _fetch_official_roster,
    event_fetcher: EventFetcher = _fetch_official_event_pages,
    document_fetcher: DocumentFetcher = _fetch_official_document,
) -> str:
    try:
        original_body = manifest_path.read_bytes()
        manifest = json.loads(original_body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read event manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("live_revalidation_required") is not True:
        raise ManifestError("event manifest does not require live revalidation")
    ticker = str(manifest.get("ticker") or "")
    exchange = str(manifest.get("exchange") or "")
    try:
        ticker_code, ticker_exchange = ticker.rsplit(".", 1)
        as_of = date.fromisoformat(str(manifest.get("AS_OF") or ""))
    except ValueError as exc:
        raise ManifestError("event manifest identity is invalid") from exc
    if exchange not in {"SH", "SZ", "HK"} or ticker_exchange != exchange:
        raise ManifestError("event manifest identity is invalid")

    authenticated_listing_profile: dict[str, object] | None = None
    for profile_name in ("listing_profile", "subject_roster"):
        profile = manifest.get(profile_name)
        if not isinstance(profile, dict):
            raise ManifestError(f"event manifest lacks {profile_name}")
        source_path = Path(str(profile.get("source_file") or ""))
        expected_sha256 = str(profile.get("source_sha256") or "")
        if (
            not source_path.is_absolute()
            or not source_path.is_file()
            or _sha256(source_path) != expected_sha256
        ):
            raise ManifestError(f"{profile_name} stored evidence hash differs")
        query_params = profile.get("query_params")
        if not isinstance(query_params, dict):
            raise ManifestError(f"{profile_name} query_params are invalid")
        live_body = _fetch_identity_response(
            roster_fetcher,
            str(profile.get("source_url") or ""),
            str(profile.get("http_method") or "GET"),
            str(profile.get("request_encoding") or "query"),
            query_params,
            profile.get("request_headers", {}),
            profile.get("request_bootstrap"),
        )
        if hashlib.sha256(live_body).hexdigest() != expected_sha256:
            raise ManifestError(f"{profile_name} live official response hash differs")
        if profile_name == "listing_profile":
            try:
                source_payload = json.loads(source_path.read_text(encoding="utf-8"))
                live_payload = json.loads(live_body.decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ManifestError(f"listing_profile stored evidence is invalid: {exc}") from exc
            if not isinstance(source_payload, dict) or not isinstance(live_payload, dict):
                raise ManifestError("listing_profile stored evidence is invalid")
            response_schema = str(profile.get("response_schema") or "")
            raw_adapter = profile.get("response_adapter")
            response_adapter = raw_adapter if isinstance(raw_adapter, dict) else {}
            normalized_source_profile = _normalize_listing_profile_response(
                source_payload,
                response_schema,
                response_adapter,
                query_params,
                exchange,
                ticker_code,
                as_of,
            )
            normalized_live_profile = _normalize_listing_profile_response(
                live_payload,
                response_schema,
                response_adapter,
                query_params,
                exchange,
                ticker_code,
                as_of,
            )
            if (
                normalized_source_profile != normalized_live_profile
                or any(
                    profile.get(field) != value
                    for field, value in normalized_source_profile.items()
                )
                or profile.get("live_response_sha256") != expected_sha256
            ):
                raise ManifestError("listing_profile identity differs from event manifest")
            authenticated_listing_profile = normalized_source_profile

    if authenticated_listing_profile is None:
        raise ManifestError("event manifest lacks listing_profile")
    listing_profile = authenticated_listing_profile
    active_listing_codes, historical_listing_codes, future_listing_codes = _listing_jurisdictions(
        listing_profile, as_of
    )
    if (
        exchange not in active_listing_codes
        or manifest.get("查询发行人代码映射") != active_listing_codes
        or manifest.get("future_listing_codes") != future_listing_codes
        or manifest.get("listing_date") != listing_profile.get("listing_date")
    ):
        raise ManifestError("listing_profile identity differs from event manifest")
    listing_dates = listing_profile.get("listing_dates")
    if not isinstance(listing_dates, dict) or not listing_dates:
        raise ManifestError("listing_profile listing_dates are invalid")
    try:
        listing_history_start = min(
            date.fromisoformat(str(value)) for value in listing_dates.values()
        )
    except ValueError as exc:
        raise ManifestError("listing_profile listing_dates are invalid") from exc
    _, _, evidence_subjects = _validate_subject_roster(
        manifest,
        exchange,
        ticker_code,
        listing_history_start,
        as_of,
        roster_fetcher,
    )
    declared_subjects = manifest.get("subjects")
    if (
        not isinstance(declared_subjects, list)
        or not all(isinstance(subject, dict) for subject in declared_subjects)
        or not all(isinstance(subject, dict) for subject in evidence_subjects)
    ):
        raise ManifestError("subject_roster derived subjects differ")
    declared_by_id = {str(subject.get("id") or ""): subject for subject in declared_subjects}
    evidence_by_id = {str(subject.get("id") or ""): subject for subject in evidence_subjects}
    if (
        "" in declared_by_id
        or "" in evidence_by_id
        or len(declared_by_id) != len(declared_subjects)
        or len(evidence_by_id) != len(evidence_subjects)
        or declared_by_id != evidence_by_id
    ):
        raise ManifestError("subject_roster derived subjects differ")

    queries = manifest.get("queries")
    if not isinstance(queries, dict):
        raise ManifestError("event manifest queries are invalid")
    if set(queries) != set(REQUIRED_SCOPES):
        missing = sorted(set(REQUIRED_SCOPES) - set(queries))
        extra = sorted(set(queries) - set(REQUIRED_SCOPES))
        raise ManifestError(f"category set mismatch; missing={missing}, extra={extra}")
    issuer_type = str(manifest.get("issuer_type") or "")
    if issuer_type not in {"bank", "insurer", "non_bank"}:
        raise ManifestError("issuer_type must be bank, insurer, or non_bank")
    subjects = {subject_id: dict(subject) for subject_id, subject in declared_by_id.items()}
    live_document_hashes: dict[str, str] = {}
    for category, query in queries.items():
        if not isinstance(query, dict):
            raise ManifestError(f"{category}: query is invalid")
        sources = query.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ManifestError(f"{category}: source evidence is missing")
        source_ids = [
            str(source.get("source_id") or "") for source in sources if isinstance(source, dict)
        ]
        if len(source_ids) != len(sources) or len(source_ids) != len(set(source_ids)):
            raise ManifestError(f"{category}: source evidence is invalid")
        required_source_ids = _required_source_ids(
            category,
            historical_listing_codes,
            issuer_type,
        )
        if not required_source_ids.issubset(source_ids):
            raise ManifestError(
                f"{category}: required official sources are "
                f"{sorted(required_source_ids)}; got={sorted(source_ids)}"
            )
        if query.get("source_count") != len(sources):
            raise ManifestError(f"{category}: source evidence is invalid")
        reconstructed_aggregate_events: list[dict[str, object]] = []
        for source in sources:
            if not isinstance(source, dict):
                raise ManifestError(f"{category}: source evidence is invalid")
            source_id = str(source.get("source_id") or "")
            if source_id not in SOURCE_DOMAINS:
                raise ManifestError(f"{category}: unknown source_id {source_id}")
            source_exchange = _source_exchange(
                source_id,
                historical_listing_codes,
            )
            expected_query_issuer = historical_listing_codes[source_exchange]
            if (
                source.get("scope") != REQUIRED_SCOPES[category]
                or str(source.get("query_issuer_code") or "") != expected_query_issuer
                or _parse_date(
                    source.get("query_end"),
                    f"{category}.query_end",
                )
                != as_of
            ):
                raise ManifestError(f"{category}: source query coverage differs")
            query_start = _parse_date(
                source.get("query_start"),
                f"{category}.query_start",
            )
            query_params = source.get("query_params")
            if not isinstance(query_params, dict):
                raise ManifestError(f"{category}: query_params are invalid")
            live_bodies = event_fetcher(
                str(source.get("query_url") or ""),
                str(source.get("http_method") or ""),
                str(source.get("request_encoding") or ""),
                query_params,
                {
                    "response_schema": source.get("response_schema"),
                    "response_adapter": source.get("response_adapter"),
                    "request_headers": source.get("request_headers", {}),
                },
            )
            live_sha256 = hashlib.sha256(b"".join(live_bodies)).hexdigest()
            if live_sha256 != source.get("response_sha256"):
                raise ManifestError(f"{category}: live official event response hash differs")
            events = source.get("events")
            if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
                raise ManifestError(f"{category}: source events are invalid")
            live_events, live_total = _events_from_live_pages(
                live_bodies,
                str(source.get("response_schema") or ""),
                source.get("response_adapter"),
                query_params,
                category,
            )
            stored_by_record_id = {str(event.get("record_id") or ""): event for event in events}
            if (
                live_total != source.get("official_result_total")
                or "" in stored_by_record_id
                or len(stored_by_record_id) != len(events)
            ):
                raise ManifestError(f"{category}: derived events differ")
            canonical_live_events: list[dict[str, object]] = []
            for live_event in live_events:
                record_id = str(live_event.get("record_id") or "")
                stored_event = stored_by_record_id.get(record_id)
                if stored_event is None:
                    raise ManifestError(f"{category}: derived events differ")
                canonical_live_events.append(
                    _normalize_event(
                        live_event,
                        response_schema=str(source.get("response_schema") or ""),
                        subjects=subjects,
                        source_id=source_id,
                        source_exchange=source_exchange,
                        query_issuer_code=expected_query_issuer,
                        category=category,
                        query_start=query_start,
                        as_of=as_of,
                        include_open_before_start=(
                            query_params.get("include_open_before_start") is True
                        ),
                        document_path=Path(str(stored_event.get("document_path") or "")),
                        expected_content_sha256=str(stored_event.get("content_sha256") or ""),
                        document_fetcher=document_fetcher,
                        live_document_hashes=live_document_hashes,
                    )
                )
            if canonical_live_events != events:
                raise ManifestError(f"{category}: derived events differ")
            _merge_canonical_events(
                reconstructed_aggregate_events,
                canonical_live_events,
                category,
            )
        aggregate_events = query.get("events")
        if not isinstance(aggregate_events, list) or not all(
            isinstance(event, dict) for event in aggregate_events
        ):
            raise ManifestError(f"{category}: aggregate events are invalid")
        if reconstructed_aggregate_events != aggregate_events:
            raise ManifestError(f"{category}: derived aggregate events differ")

    if manifest_path.read_bytes() != original_body:
        raise ManifestError("event manifest changed during live revalidation")
    return hashlib.sha256(original_body).hexdigest()


def main(
    argv: list[str] | None = None,
    *,
    roster_fetcher: RosterFetcher = _fetch_official_roster,
    event_fetcher: EventFetcher = _fetch_official_event_pages,
    document_fetcher: DocumentFetcher = _fetch_official_document,
) -> int:
    parser = argparse.ArgumentParser(description="Build a canonical regulatory-event manifest.")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--revalidate", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.revalidate is not None:
            if args.bundle is not None or args.out is not None:
                parser.error("--revalidate cannot be combined with --bundle or --out")
            published: object = revalidate_manifest(
                args.revalidate,
                roster_fetcher=roster_fetcher,
                event_fetcher=event_fetcher,
                document_fetcher=document_fetcher,
            )
        else:
            if args.bundle is None or args.out is None:
                parser.error("--bundle and --out are required when building")
            published = write_manifest(
                args.bundle,
                args.out,
                roster_fetcher=roster_fetcher,
                event_fetcher=event_fetcher,
                document_fetcher=document_fetcher,
            )
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(published)
    return 0


if __name__ == "__main__":
    sys.exit(main())
