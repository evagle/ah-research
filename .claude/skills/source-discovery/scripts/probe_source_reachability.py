from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TIMEOUT = 10.0
DEFAULT_USER_AGENT = "ah-research-source-discovery/1.0 (non-interactive reachability probe; urllib)"
MAX_BODY_BYTES = 32_768
MIN_SEMANTIC_FINGERPRINT_CHARACTERS = 4
LOGIN_MARKERS = (
    "login required",
    "log in",
    "sign in",
    "please sign in",
    "please log in",
    "登录",
    "登入",
)
PAYWALL_MARKERS = (
    "subscribe now",
    "subscription required",
    "subscriber access",
    "become a member",
    "membership required",
    "vip",
    "付费",
    "会员",
)
ANTI_BOT_MARKERS = (
    "akamai",
    "aliyun waf",
    "bot manager",
    "captcha",
    "cloudflare",
    "security check",
    "verify you are human",
    "waf",
    "正在进行安全检测",
)
ERROR_PAGE_MARKERS = (
    "404",
    "not found",
    "page not found",
    "does not exist",
)
TEMPORARY_ERROR_KINDS = {
    "timeout",
    "dns",
    "connection-reset",
    "connection-refused",
    "tls",
    "network",
}
DNS_ERROR_MARKERS = (
    "nodename nor servname",
    "name or service not known",
    "temporary failure in name resolution",
    "getaddrinfo failed",
)
PROFILE_SUFFIXES = ("*.yaml", "*.yml")


@dataclass(frozen=True)
class ProbeObservation:
    status_code: int | None
    final_url: str
    redirect_chain: list[str]
    content_type: str | None
    title: str | None
    body_excerpt: str
    error_kind: str | None
    error_message: str | None


@dataclass(frozen=True)
class ProbeResult:
    status: str
    reason: str


class RecordingRedirectHandler(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirect_chain: list[str] = []

    def redirect_request(
        self,
        req: Request,
        fp,
        code: int,
        msg: str,
        headers,
        newurl: str,
    ) -> Request | None:
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            self.redirect_chain.append(f"{req.full_url} -> {redirected.full_url}")
        return redirected


def classify_observation(
    observation: ProbeObservation,
    expected_fingerprints: Sequence[str],
) -> ProbeResult:
    normalized_fingerprints = _normalize_fingerprints(expected_fingerprints)
    haystack = _observation_haystack(observation)
    has_publisher_identity = _has_publisher_identity(
        observation,
        normalized_fingerprints,
    )
    status_code = observation.status_code

    if observation.error_kind in TEMPORARY_ERROR_KINDS:
        return ProbeResult(
            status="temporarily-unreachable",
            reason=observation.error_message or observation.error_kind or "temporary network error",
        )

    if status_code in {404, 410}:
        return ProbeResult(status="broken-link", reason=f"HTTP {status_code}")

    if status_code is not None and 500 <= status_code < 600:
        return ProbeResult(status="temporarily-unreachable", reason=f"HTTP {status_code}")

    if status_code == 401 or _contains_marker(haystack, LOGIN_MARKERS):
        return ProbeResult(status="login-required", reason="login prompt detected")

    if status_code == 402 or _contains_marker(haystack, PAYWALL_MARKERS):
        return ProbeResult(status="paywalled", reason="subscription prompt detected")

    if status_code == 429 or _contains_marker(haystack, ANTI_BOT_MARKERS):
        return ProbeResult(status="anti-bot", reason="anti-bot challenge detected")

    if status_code is not None and 400 <= status_code < 500 and not has_publisher_identity:
        return ProbeResult(status="unverified", reason=f"HTTP {status_code}")

    if _contains_marker(haystack, ERROR_PAGE_MARKERS):
        return ProbeResult(status="broken-link", reason="error page markers detected")

    if observation.redirect_chain:
        if has_publisher_identity:
            return ProbeResult(status="moved", reason="redirected to recognizable publisher route")
        return ProbeResult(status="unverified", reason="redirect target not fingerprinted")

    if status_code is not None and 200 <= status_code < 300 and has_publisher_identity:
        return ProbeResult(status="reachable", reason="recognizable first-party content")

    return ProbeResult(status="unverified", reason="insufficient first-party evidence")


def probe_url(url: str, timeout: float, user_agent: str) -> ProbeObservation:
    redirect_handler = RecordingRedirectHandler()
    opener = build_opener(redirect_handler)
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = _read_limited_body(response)
            content_type = response.headers.get_content_type()
            text = _decode_body(body, response.headers.get_content_charset())
            return ProbeObservation(
                status_code=response.status,
                final_url=response.geturl(),
                redirect_chain=redirect_handler.redirect_chain,
                content_type=content_type,
                title=_extract_title(text),
                body_excerpt=_extract_body_excerpt(text),
                error_kind=None,
                error_message=None,
            )
    except HTTPError as exc:
        body = _read_limited_body(exc)
        content_type = exc.headers.get_content_type() if exc.headers is not None else None
        charset = exc.headers.get_content_charset() if exc.headers is not None else None
        text = _decode_body(body, charset)
        return ProbeObservation(
            status_code=exc.code,
            final_url=exc.geturl(),
            redirect_chain=redirect_handler.redirect_chain,
            content_type=content_type,
            title=_extract_title(text),
            body_excerpt=_extract_body_excerpt(text),
            error_kind="http",
            error_message=str(exc),
        )
    except URLError as exc:
        error_kind, error_message = _classify_url_error(exc.reason)
        return ProbeObservation(
            status_code=None,
            final_url=url,
            redirect_chain=redirect_handler.redirect_chain,
            content_type=None,
            title=None,
            body_excerpt="",
            error_kind=error_kind,
            error_message=error_message,
        )
    except TimeoutError as exc:
        return ProbeObservation(
            status_code=None,
            final_url=url,
            redirect_chain=redirect_handler.redirect_chain,
            content_type=None,
            title=None,
            body_excerpt="",
            error_kind="timeout",
            error_message=str(exc),
        )


def load_cache(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def write_cache(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    temp_path.write_text(f"{serialized}\n", encoding="utf-8")
    os.replace(temp_path, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe source reachability using non-interactive HTTP."
    )
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--source", action="append", dest="sources", default=[])
    parser.add_argument("--all", action="store_true", dest="probe_all")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.probe_all and not args.sources:
        parser.error("pass --all or at least one --source")

    try:
        cache_path = _validated_cli_cache_path(args.cache)
    except ValueError as exc:
        parser.error(str(exc))

    profiles = _load_profile_records(args.profiles)
    selected_ids = set(args.sources) if not args.probe_all else set(profiles)
    missing = sorted(selected_ids - profiles.keys())
    if missing:
        parser.error(f"unknown source id(s): {', '.join(missing)}")

    source_ids = sorted(profiles) if args.probe_all else list(dict.fromkeys(args.sources))
    cache = load_cache(cache_path)
    now = datetime.now(UTC).isoformat()
    summary: dict[str, object] = {}

    for source_id in source_ids:
        profile = profiles[source_id]
        target_url = _profile_probe_url(profile)
        observation = probe_url(target_url, timeout=args.timeout, user_agent=args.user_agent)
        fingerprints = _profile_fingerprints(profile)
        result = classify_observation(observation, fingerprints)
        cache[source_id] = {
            "status": result.status,
            "reason": result.reason,
            "last_checked": now,
            **_observation_payload(observation),
        }
        summary[source_id] = cache[source_id]

    write_cache(cache_path, cache)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _observation_payload(observation: ProbeObservation) -> dict[str, object]:
    payload = asdict(observation)
    payload["redirect_chain"] = list(observation.redirect_chain)
    return payload


def _normalize_fingerprints(expected_fingerprints: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in expected_fingerprints:
        fingerprint = raw.strip().lower()
        if fingerprint:
            normalized.append(fingerprint)
    return tuple(dict.fromkeys(normalized))


def _observation_haystack(observation: ProbeObservation) -> str:
    parts = [
        observation.final_url,
        observation.title or "",
        observation.body_excerpt,
        " ".join(observation.redirect_chain),
    ]
    return " ".join(parts).lower()


def _has_publisher_identity(
    observation: ProbeObservation,
    normalized_fingerprints: Sequence[str],
) -> bool:
    official_domains = tuple(
        domain
        for fingerprint in normalized_fingerprints
        if (domain := _domain_from_fingerprint(fingerprint)) is not None
    )
    if _final_host_matches_official_domain(observation.final_url, official_domains):
        return True

    page_text = " ".join((observation.title or "", observation.body_excerpt)).lower()
    semantic_fingerprints = (
        fingerprint
        for fingerprint in normalized_fingerprints
        if _is_meaningful_semantic_fingerprint(fingerprint)
    )
    return any(fingerprint in page_text for fingerprint in semantic_fingerprints)


def _domain_from_fingerprint(fingerprint: str) -> str | None:
    candidate = fingerprint.removeprefix("*.").strip(".")
    if not candidate or "/" in candidate or " " in candidate or "." not in candidate:
        return None
    labels = candidate.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or re.fullmatch(r"[a-z0-9-]+", label) is None
        for label in labels
    ):
        return None
    return candidate


def _final_host_matches_official_domain(
    final_url: str,
    official_domains: Sequence[str],
) -> bool:
    try:
        hostname = urlsplit(final_url).hostname
    except ValueError:
        return False
    if hostname is None:
        return False
    normalized_host = hostname.rstrip(".").lower()
    return any(
        normalized_host == domain or normalized_host.endswith(f".{domain}")
        for domain in official_domains
    )


def _is_meaningful_semantic_fingerprint(fingerprint: str) -> bool:
    if _domain_from_fingerprint(fingerprint) is not None:
        return False
    semantic_characters = re.sub(r"[\W_]", "", fingerprint)
    return len(semantic_characters) >= MIN_SEMANTIC_FINGERPRINT_CHARACTERS


def _contains_marker(text: str, markers: Sequence[str]) -> bool:
    return any(marker in text for marker in markers)


def _read_limited_body(response) -> bytes:
    return response.read(MAX_BODY_BYTES)


def _decode_body(body: bytes, charset: str | None) -> str:
    encoding = charset or "utf-8"
    return body.decode(encoding, errors="replace")


def _extract_title(text: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        return None
    title = _collapse_whitespace(unescape(match.group(1)))
    return title or None


def _extract_body_excerpt(text: str) -> str:
    without_scripts = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    excerpt = _collapse_whitespace(unescape(without_tags))
    return excerpt[:500]


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _classify_url_error(reason: object) -> tuple[str, str]:
    message = str(reason)
    reasons = tuple(_walk_error_reasons(reason))
    lowered = " ".join(str(item).lower() for item in reasons)
    if any(isinstance(item, socket.timeout) for item in reasons) or "timed out" in lowered:
        return "timeout", message
    if any(isinstance(item, socket.gaierror) for item in reasons) or _contains_marker(
        lowered,
        DNS_ERROR_MARKERS,
    ):
        return "dns", message
    if any(isinstance(item, ConnectionResetError) for item in reasons) or (
        "connection reset" in lowered
    ):
        return "connection-reset", message
    if any(isinstance(item, ConnectionRefusedError) for item in reasons) or (
        "connection refused" in lowered
    ):
        return "connection-refused", message
    if any(isinstance(item, ssl.SSLError) for item in reasons):
        return "tls", message
    return "network", message


def _walk_error_reasons(reason: object) -> Iterator[object]:
    pending = [reason]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        yield current

        if isinstance(current, URLError) and current.reason is not current:
            pending.append(current.reason)
        if isinstance(current, BaseException):
            if current.__cause__ is not None:
                pending.append(current.__cause__)
            if current.__context__ is not None:
                pending.append(current.__context__)


def _validated_cli_cache_path(path: Path) -> Path:
    repo_root = REPO_ROOT.resolve()
    expected_cache_root = repo_root / "tmp" / "source-discovery"
    cache_root = expected_cache_root.resolve()
    resolved_path = path.expanduser().resolve()
    if (
        cache_root != expected_cache_root
        or resolved_path == cache_root
        or not resolved_path.is_relative_to(cache_root)
    ):
        raise ValueError("--cache must be a file within repository tmp/source-discovery")
    return resolved_path


def _load_profile_records(profile_dir: Path) -> dict[str, Mapping[str, object]]:
    records: dict[str, Mapping[str, object]] = {}
    for pattern in PROFILE_SUFFIXES:
        for path in sorted(profile_dir.glob(pattern)):
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"{path}: expected YAML mapping")
            source_id = payload.get("id")
            if not isinstance(source_id, str):
                raise ValueError(f"{path}: missing source id")
            records[source_id] = payload
    return records


def _profile_probe_url(profile: Mapping[str, object]) -> str:
    access = profile.get("access")
    if isinstance(access, Mapping):
        final_url = access.get("final_url")
        if isinstance(final_url, str) and final_url:
            return final_url

    functions = profile.get("functions")
    if isinstance(functions, list):
        for function in functions:
            if not isinstance(function, Mapping):
                continue
            direct_urls = function.get("direct_urls")
            if not isinstance(direct_urls, list):
                continue
            for direct_url in direct_urls:
                if not isinstance(direct_url, Mapping):
                    continue
                url = direct_url.get("url")
                if isinstance(url, str) and url:
                    return url

    source_id = profile.get("id", "<unknown>")
    raise ValueError(f"{source_id}: missing probe URL")


def _profile_fingerprints(profile: Mapping[str, object]) -> list[str]:
    fingerprints: list[str] = []
    for key in ("name",):
        value = profile.get(key)
        if isinstance(value, str):
            fingerprints.append(value)

    aliases = profile.get("aliases")
    if isinstance(aliases, list):
        fingerprints.extend(alias for alias in aliases if isinstance(alias, str))

    domains = profile.get("official_domains")
    if isinstance(domains, list):
        fingerprints.extend(domain for domain in domains if isinstance(domain, str))

    return fingerprints


if __name__ == "__main__":
    raise SystemExit(main())
