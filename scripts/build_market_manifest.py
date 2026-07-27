"""Build and live-revalidate immutable market-data manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any


class MarketManifestError(Exception):
    """Raised when market evidence is incomplete or changes."""


Fetcher = Callable[
    [str, str, str, dict[str, object], dict[str, str]],
    bytes,
]
TICKER_PATTERN = re.compile(r"^(?:\d{6}\.(?:SH|SZ)|\d{5}\.HK)$")
SOURCE_DOMAINS = {
    "sse": ("sse.com.cn",),
    "szse": ("szse.cn",),
    "hkex": ("hkex.com.hk", "hkexnews.hk"),
    "chinamoney": ("chinamoney.com.cn",),
    "pbc": ("pbc.gov.cn",),
    "hkma": ("hkma.gov.hk",),
}
PRICE_SOURCE_BY_EXCHANGE = {
    "SH": {"sse"},
    "SZ": {"szse"},
    "HK": {"hkex"},
}
RATE_SOURCES_BY_EXCHANGE = {
    "SH": {"chinamoney", "pbc"},
    "SZ": {"chinamoney", "pbc"},
    "HK": {"hkma"},
}
BINDING_PATH_BY_LABEL = {
    "price": "identity_path",
    "risk_free_rate": "tenor_path",
}


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _fetch(
    url: str,
    method: str,
    encoding: str,
    params: dict[str, object],
    headers: dict[str, str],
) -> bytes:
    if not url.startswith("https://"):
        raise MarketManifestError("market source_url must use HTTPS")
    body: bytes | None = None
    request_url = url
    request_headers = dict(headers)
    if method == "GET" and encoding == "query":
        request_url = f"{url}?{urllib.parse.urlencode(params)}"
    elif method == "POST" and encoding in {"json", "form"}:
        if encoding == "json":
            body = json.dumps(params, separators=(",", ":")).encode()
            request_headers.setdefault("Content-Type", "application/json")
        else:
            body = urllib.parse.urlencode(params).encode()
            request_headers.setdefault(
                "Content-Type",
                "application/x-www-form-urlencoded",
            )
    else:
        raise MarketManifestError("unsupported market request contract")
    request = urllib.request.Request(
        request_url,
        data=body,
        headers=request_headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MarketManifestError(f"cannot read {label}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MarketManifestError(f"{label} must be a JSON object")
    return parsed


def _path_value(payload: object, path: object, label: str) -> object:
    if not isinstance(path, list) or not path:
        raise MarketManifestError(f"{label}_path must be a nonempty array")
    value = payload
    for part in path:
        if not isinstance(value, dict) or str(part) not in value:
            raise MarketManifestError(f"{label}_path is absent from response")
        value = value[str(part)]
    return value


def _write_immutable(path: Path, body: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            digest = _sha256(body)
            path = path.with_name(f"{path.stem}-{digest}{path.suffix}")
        else:
            return path.resolve()
    if path.exists():
        if path.read_bytes() != body:
            raise MarketManifestError("content-addressed evidence collision")
        return path.resolve()
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        if path.read_bytes() != body:
            raise MarketManifestError("concurrent market evidence differs") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return path.resolve()


def _validate_request(row: object, label: str) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise MarketManifestError(f"{label} request must be an object")
    required = {
        "source_url",
        "source_id",
        "http_method",
        "request_encoding",
        "query_params",
        "value_path",
        "date_path",
        "latest_observation_date_path",
        "max_observation_age_days",
        "unit",
        BINDING_PATH_BY_LABEL[label],
    }
    if not required <= set(row):
        raise MarketManifestError(f"{label} request is incomplete")
    if row["date_path"] == row["latest_observation_date_path"]:
        raise MarketManifestError(
            f"{label} latest observation date path must differ from date path"
        )
    max_observation_age_days = row["max_observation_age_days"]
    if (
        not isinstance(max_observation_age_days, int)
        or isinstance(max_observation_age_days, bool)
        or max_observation_age_days <= 0
    ):
        raise MarketManifestError(f"{label} max_observation_age_days must be a positive integer")
    source_id = str(row["source_id"])
    hostname = urllib.parse.urlparse(str(row["source_url"])).hostname or ""
    if source_id not in SOURCE_DOMAINS or not any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in SOURCE_DOMAINS[source_id]
    ):
        raise MarketManifestError(f"{label} source is not an approved official domain")
    if row["http_method"] not in {"GET", "POST"}:
        raise MarketManifestError(f"{label} http_method is unsupported")
    if row["request_encoding"] not in {"query", "json", "form"}:
        raise MarketManifestError(f"{label} request_encoding is unsupported")
    if not isinstance(row["query_params"], dict):
        raise MarketManifestError(f"{label} query_params must be an object")
    headers = row.get("request_headers", {})
    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
    ):
        raise MarketManifestError(f"{label} request_headers are invalid")
    return row


def _validate_request_binding(
    request: dict[str, Any],
    label: str,
    ticker_code: str,
    as_of: date,
) -> None:
    query_params = request["query_params"]
    if str(query_params.get("date") or "") != as_of.isoformat():
        raise MarketManifestError(f"{label} request date must equal AS_OF")
    if label == "price":
        if str(query_params.get("issuer_code") or "") != ticker_code:
            raise MarketManifestError("price request identity must equal canonical ticker code")
    elif str(query_params.get("tenor") or "") != "10Y":
        raise MarketManifestError("risk_free_rate request tenor must equal 10Y")


def _validate_canonical_unit(
    request: dict[str, Any],
    label: str,
    exchange: str,
) -> None:
    expected_unit = ("HKD" if exchange == "HK" else "CNY") if label == "price" else "percent"
    if request["unit"] != expected_unit:
        raise MarketManifestError(f"{label} unit must equal canonical {expected_unit}")


def _derive_response(
    body: bytes,
    request: dict[str, Any],
    label: str,
) -> tuple[float, date, date, str]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketManifestError(f"{label} response is not JSON") from exc
    value = _path_value(payload, request["value_path"], f"{label}.value")
    observed_date = _path_value(payload, request["date_path"], f"{label}.date")
    latest_observation_date = _path_value(
        payload,
        request["latest_observation_date_path"],
        f"{label}.latest_observation_date",
    )
    binding_name = BINDING_PATH_BY_LABEL[label]
    binding = _path_value(payload, request[binding_name], f"{label}.binding")
    try:
        parsed_date = date.fromisoformat(str(observed_date))
    except ValueError as exc:
        raise MarketManifestError(f"{label} response date is invalid") from exc
    try:
        parsed_latest_date = date.fromisoformat(str(latest_observation_date))
    except ValueError as exc:
        raise MarketManifestError(f"{label} latest observation date is invalid") from exc
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise MarketManifestError(f"{label} value must be finite numeric")
    return float(value), parsed_date, parsed_latest_date, str(binding)


def _validate_observation(
    label: str,
    binding: str,
    observed_date: date,
    latest_observation_date: date,
    ticker_code: str,
    as_of: date,
    max_observation_age_days: int,
) -> None:
    expected_binding = ticker_code if label == "price" else "10Y"
    if binding != expected_binding:
        raise MarketManifestError(f"{label} response identity or tenor does not match request")
    if observed_date > as_of:
        raise MarketManifestError(f"{label} response date is after AS_OF")
    if latest_observation_date > as_of:
        raise MarketManifestError(f"{label} latest observation date is after AS_OF")
    if observed_date != latest_observation_date:
        raise MarketManifestError(f"{label} response date does not match latest observation date")
    if (as_of - observed_date).days > max_observation_age_days:
        raise MarketManifestError(f"{label} response date exceeds max_observation_age_days")


def _collect_row(
    label: str,
    request: dict[str, Any],
    ticker_code: str,
    as_of: date,
    evidence_dir: Path,
    fetcher: Fetcher,
) -> dict[str, object]:
    body = fetcher(
        str(request["source_url"]),
        str(request["http_method"]),
        str(request["request_encoding"]),
        request["query_params"],
        request.get("request_headers", {}),
    )
    value, parsed_date, latest_date, binding = _derive_response(
        body,
        request,
        label,
    )
    _validate_observation(
        label,
        binding,
        parsed_date,
        latest_date,
        ticker_code,
        as_of,
        request["max_observation_age_days"],
    )
    raw_path = _write_immutable(
        evidence_dir / f"{label}-{_sha256(body)}.json",
        body,
    )
    return {
        "source_url": request["source_url"],
        "source_id": request["source_id"],
        "http_method": request["http_method"],
        "request_encoding": request["request_encoding"],
        "request_headers": request.get("request_headers", {}),
        "query_params": request["query_params"],
        "value_path": request["value_path"],
        "date_path": request["date_path"],
        "latest_observation_date_path": request["latest_observation_date_path"],
        "max_observation_age_days": request["max_observation_age_days"],
        BINDING_PATH_BY_LABEL[label]: request[BINDING_PATH_BY_LABEL[label]],
        "market_date": parsed_date.isoformat(),
        "latest_observation_date": latest_date.isoformat(),
        "value": value,
        "unit": request["unit"],
        "raw_response_path": str(raw_path),
        "response_sha256": _sha256(body),
    }


def build_manifest(
    plan_path: Path,
    output_path: Path,
    evidence_dir: Path,
    *,
    fetcher: Fetcher = _fetch,
) -> Path:
    plan = _read_json(plan_path, "market plan")
    if plan.get("schema_version") != 1:
        raise MarketManifestError("market plan schema_version must be 1")
    try:
        as_of = date.fromisoformat(str(plan.get("AS_OF") or ""))
    except ValueError as exc:
        raise MarketManifestError("market plan AS_OF is invalid") from exc
    ticker = str(plan.get("ticker") or "")
    if not TICKER_PATTERN.fullmatch(ticker):
        raise MarketManifestError("market plan ticker is invalid")
    ticker_code, exchange = ticker.rsplit(".", 1)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "ticker": ticker,
        "AS_OF": as_of.isoformat(),
        "live_revalidation_required": True,
    }
    requests: dict[str, dict[str, Any]] = {}
    for label in ("price", "risk_free_rate"):
        request = _validate_request(plan.get(label), label)
        allowed_sources = (
            PRICE_SOURCE_BY_EXCHANGE[exchange]
            if label == "price"
            else RATE_SOURCES_BY_EXCHANGE[exchange]
        )
        if request["source_id"] not in allowed_sources:
            raise MarketManifestError(f"{label} source does not match ticker exchange")
        _validate_request_binding(request, label, ticker_code, as_of)
        _validate_canonical_unit(request, label, exchange)
        requests[label] = request
    for label, request in requests.items():
        manifest[label] = _collect_row(
            label,
            request,
            ticker_code,
            as_of,
            evidence_dir,
            fetcher,
        )
    body = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    return _write_immutable(output_path, body)


def revalidate_manifest(
    manifest_path: Path,
    *,
    fetcher: Fetcher = _fetch,
) -> str:
    original = manifest_path.read_bytes()
    manifest = _read_json(manifest_path, "market manifest")
    ticker = str(manifest.get("ticker") or "")
    if not TICKER_PATTERN.fullmatch(ticker):
        raise MarketManifestError("market manifest ticker is invalid")
    ticker_code, exchange = ticker.rsplit(".", 1)
    try:
        as_of = date.fromisoformat(str(manifest.get("AS_OF") or ""))
    except ValueError as exc:
        raise MarketManifestError("market manifest AS_OF is invalid") from exc
    for label in ("price", "risk_free_rate"):
        row = _validate_request(manifest.get(label), label)
        _validate_request_binding(row, label, ticker_code, as_of)
        _validate_canonical_unit(row, label, exchange)
        live = fetcher(
            str(row["source_url"]),
            str(row["http_method"]),
            str(row["request_encoding"]),
            row["query_params"],
            row.get("request_headers", {}),
        )
        if _sha256(live) != row.get("response_sha256"):
            raise MarketManifestError(f"{label} live response hash differs")
        raw_path = Path(str(row.get("raw_response_path") or ""))
        if (
            not raw_path.is_absolute()
            or not raw_path.is_file()
            or _sha256(raw_path.read_bytes()) != row.get("response_sha256")
        ):
            raise MarketManifestError(f"{label} stored response hash differs")
        stored = raw_path.read_bytes()
        live_value, live_date, live_latest_date, live_binding = _derive_response(
            live,
            row,
            label,
        )
        (
            stored_value,
            stored_date,
            stored_latest_date,
            stored_binding,
        ) = _derive_response(
            stored,
            row,
            label,
        )
        _validate_observation(
            label,
            live_binding,
            live_date,
            live_latest_date,
            ticker_code,
            as_of,
            row["max_observation_age_days"],
        )
        _validate_observation(
            label,
            stored_binding,
            stored_date,
            stored_latest_date,
            ticker_code,
            as_of,
            row["max_observation_age_days"],
        )
        manifest_value = row.get("value")
        if (
            not isinstance(manifest_value, (int, float))
            or isinstance(manifest_value, bool)
            or not math.isfinite(float(manifest_value))
        ):
            raise MarketManifestError(f"{label} stored value is invalid")
        if (
            live_value != stored_value
            or live_value != float(manifest_value)
            or live_date != stored_date
            or live_latest_date != stored_latest_date
            or live_binding != stored_binding
            or live_date.isoformat() != row.get("market_date")
            or live_latest_date.isoformat() != row.get("latest_observation_date")
        ):
            raise MarketManifestError(
                f"{label} derived value, date, or latest observation date differs"
            )
    if manifest_path.read_bytes() != original:
        raise MarketManifestError("market manifest changed during revalidation")
    return _sha256(original)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--revalidate", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.revalidate is not None:
            if any(value is not None for value in (args.plan, args.out, args.evidence_dir)):
                parser.error("--revalidate cannot be combined with build arguments")
            result: object = revalidate_manifest(args.revalidate)
        else:
            if args.plan is None or args.out is None or args.evidence_dir is None:
                parser.error("--plan, --out, and --evidence-dir are required")
            result = build_manifest(args.plan, args.out, args.evidence_dir)
    except (MarketManifestError, OSError) as exc:
        print(f"error: {exc}")
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
