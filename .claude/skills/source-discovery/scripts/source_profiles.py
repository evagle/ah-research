from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

RATING_RANK = {"High": 3, "Medium": 2, "Low": 1}
REACHABILITY_RANK = {
    "reachable": 9,
    "reachable-limited": 8,
    "login-required": 7,
    "paywalled": 6,
    "anti-bot": 5,
    "temporarily-unreachable": 4,
    "moved": 3,
    "broken-link": 2,
    "unverified": 1,
}
STATUS_TTLS = {
    "reachable": timedelta(days=30),
    "reachable-limited": timedelta(days=30),
    "login-required": timedelta(days=14),
    "paywalled": timedelta(days=14),
    "anti-bot": timedelta(days=14),
    "temporarily-unreachable": timedelta(hours=24),
    "moved": timedelta(days=7),
    "broken-link": timedelta(days=7),
    "unverified": timedelta(hours=24),
}
PUBLISHER_SEMANTICS = {
    "official-exchange": ("High", "High"),
    "official-regulator": ("High", "High"),
    "official-statistics": ("High", "High"),
    "official-government": ("High", "High"),
    "official-market-infrastructure": ("High", "High"),
    "issuer-company": ("High", "Low"),
    "original-research": ("High", "Medium"),
    "consulting-research": ("High", "Medium"),
    "commercial-data-provider": ("High", "Medium"),
    "aggregator": ("Low", "Low"),
    "media": ("Low", "Medium"),
    "mirror": ("Low", "Low"),
}


@dataclass(frozen=True)
class RouteCandidate:
    source_id: str
    function_id: str
    authority: str
    originality: str
    independence: str
    reachability: str
    utility: str
    direct_url: str
    stale: bool
    skip_reason: str | None


def ttl_for_status(status: str) -> timedelta:
    try:
        return STATUS_TTLS[status]
    except KeyError as exc:
        raise ValueError(f"unsupported status: {status}") from exc


def load_profiles(profile_dir: Path, schema_path: Path) -> list[dict[str, object]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    profiles: list[dict[str, object]] = []
    source_files = sorted(profile_dir.glob("*.yaml")) + sorted(profile_dir.glob("*.yml"))
    seen_paths: dict[str, Path] = {}
    for path in source_files:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: expected YAML mapping")

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
        if errors:
            raise ValueError(f"{path}: {errors[0].message}")

        source_id = payload.get("id")
        if not isinstance(source_id, str):
            raise ValueError(f"{path}: missing source id")
        if source_id in seen_paths:
            raise ValueError(
                f"{path}: duplicate source id '{source_id}' already seen in {seen_paths[source_id]}"
            )

        seen_paths[source_id] = path
        profiles.append(payload)

    return profiles


def select_routes(
    profiles: Sequence[Mapping[str, object]],
    function_id: str,
    now: datetime,
    cache: Mapping[str, object] | None = None,
    snapshot: Mapping[str, object] | None = None,
) -> list[RouteCandidate]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    cache = cache or {}
    snapshot = snapshot or {}
    candidates: list[RouteCandidate] = []

    for profile in profiles:
        if not isinstance(profile, Mapping):
            continue

        function = _find_function(profile, function_id)
        if function is None:
            continue

        source_id = _require_str(profile, "id")
        authority = _require_str(function, "authority")
        utility = _require_str(function, "utility")
        publisher_type = _require_str(profile, "publisher_type")
        originality, independence = _publisher_semantics(publisher_type)
        direct_url = _first_direct_url(function)
        reachability, last_checked = _resolve_reachability(
            profile,
            source_id,
            now,
            cache,
            snapshot,
        )
        stale = now - last_checked > ttl_for_status(reachability)
        skip_reason = None
        if reachability == "temporarily-unreachable" and not stale:
            skip_reason = "fresh temporarily-unreachable"

        candidates.append(
            RouteCandidate(
                source_id=source_id,
                function_id=function_id,
                authority=authority,
                originality=originality,
                independence=independence,
                reachability=reachability,
                utility=utility,
                direct_url=direct_url,
                stale=stale,
                skip_reason=skip_reason,
            )
        )

    return sorted(candidates, key=_route_sort_key)


def _route_sort_key(candidate: RouteCandidate) -> tuple[bool, int, int, int, int, int, str]:
    return (
        candidate.skip_reason is not None,
        -RATING_RANK[candidate.authority],
        -RATING_RANK[candidate.originality],
        -RATING_RANK[candidate.independence],
        -REACHABILITY_RANK[candidate.reachability],
        -RATING_RANK[candidate.utility],
        candidate.source_id,
    )


def _find_function(profile: Mapping[str, object], function_id: str) -> dict[str, object] | None:
    functions = profile.get("functions")
    if not isinstance(functions, list):
        return None

    for function in functions:
        if isinstance(function, dict) and function.get("id") == function_id:
            return function
    return None


def _first_direct_url(function: dict[str, object]) -> str:
    direct_urls = function.get("direct_urls")
    if not isinstance(direct_urls, list) or not direct_urls:
        raise ValueError("missing direct_urls")
    first = direct_urls[0]
    if not isinstance(first, dict):
        raise ValueError("invalid direct_urls entry")
    return _require_str(first, "url")


def _resolve_reachability(
    profile: Mapping[str, object],
    source_id: str,
    now: datetime,
    cache: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> tuple[str, datetime]:
    access = profile.get("access")
    if not isinstance(access, dict):
        raise ValueError(f"{source_id}: missing access block")

    status = _require_str(access, "status")
    last_checked = _parse_aware_datetime(_require_str(access, "last_checked"))

    cached = _optional_observation(cache.get(source_id))
    if cached is not None and not _is_stale(*cached, now):
        return cached

    reviewed = _optional_observation(snapshot.get(source_id))
    if reviewed is not None:
        return reviewed

    return status, last_checked


def _optional_observation(value: object) -> tuple[str, datetime] | None:
    if not isinstance(value, Mapping):
        return None

    status = value.get("status")
    last_checked = value.get("last_checked")
    if not isinstance(status, str) or not isinstance(last_checked, str):
        return None

    try:
        ttl_for_status(status)
        return status, _parse_aware_datetime(last_checked)
    except ValueError:
        return None


def _is_stale(status: str, last_checked: datetime, now: datetime) -> bool:
    return now - last_checked > ttl_for_status(status)


def _publisher_semantics(publisher_type: str) -> tuple[str, str]:
    try:
        return PUBLISHER_SEMANTICS[publisher_type]
    except KeyError as exc:
        raise ValueError(f"unsupported publisher type: {publisher_type}") from exc


def _parse_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"expected timezone-aware datetime: {value}")
    return parsed


def _require_str(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing string field: {key}")
    return value
