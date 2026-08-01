from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

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
BROAD_GEOGRAPHIES = frozenset({"global"})
BROAD_INDUSTRIES = frozenset({"cross-industry"})
UNAVAILABLE_REACHABILITY = frozenset({"temporarily-unreachable", "broken-link", "unverified"})


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
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

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
    geographies: Sequence[str] | None = None,
    industry: str | None = None,
    industries: Sequence[str] | None = None,
    minimum_originality: str | None = None,
    minimum_independence: str | None = None,
) -> list[RouteCandidate]:
    """Select routes for a function and its declared same-function fallbacks.

    Exact function matching happens before claim-scope eligibility. When
    geography or industry scope is requested, routes for a requested scope and
    broad ``Global``/``cross-industry`` profiles remain eligible. Declared
    fallback edges are traversed only from fresh unavailable routes and are
    subject to the same scope and provenance requirements as direct matches.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    cache = cache or {}
    snapshot = snapshot or {}
    requested_geographies = _normalize_requested_geographies(geographies)
    requested_industries = _normalize_requested_industries(industry, industries)
    required_originality = _normalize_minimum_rating(
        minimum_originality,
        "minimum_originality",
    )
    required_independence = _normalize_minimum_rating(
        minimum_independence,
        "minimum_independence",
    )
    routes_by_id = _index_profile_functions(profiles)
    root_route_ids = sorted(
        route_id
        for route_id, (_, function) in routes_by_id.items()
        if function.get("id") == function_id
    )
    candidates: dict[str, RouteCandidate] = {}
    visited_route_ids: set[str] = set()
    fallback_queue: list[str] = []

    for route_id in root_route_ids:
        candidate = _eligible_route_candidate(
            routes_by_id[route_id],
            now,
            cache,
            snapshot,
            requested_geographies,
            requested_industries,
            required_originality,
            required_independence,
        )
        if candidate is None:
            continue
        visited_route_ids.add(route_id)
        candidates[route_id] = candidate
        if _should_follow_fallbacks(candidate):
            fallback_queue.append(route_id)

    while fallback_queue:
        route_id = fallback_queue.pop(0)
        _, function = routes_by_id[route_id]
        for fallback_route_id in _fallback_route_ids(function):
            if fallback_route_id in visited_route_ids:
                continue
            visited_route_ids.add(fallback_route_id)
            fallback_target = routes_by_id.get(fallback_route_id)
            if fallback_target is None:
                continue
            candidate = _eligible_route_candidate(
                fallback_target,
                now,
                cache,
                snapshot,
                requested_geographies,
                requested_industries,
                required_originality,
                required_independence,
            )
            if candidate is None:
                continue
            candidates[fallback_route_id] = candidate
            if _should_follow_fallbacks(candidate):
                fallback_queue.append(fallback_route_id)

    return sorted(candidates.values(), key=_route_sort_key)


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


def _index_profile_functions(
    profiles: Sequence[Mapping[str, object]],
) -> dict[str, tuple[Mapping[str, object], dict[str, object]]]:
    routes: dict[str, tuple[Mapping[str, object], dict[str, object]]] = {}
    for profile in profiles:
        if not isinstance(profile, Mapping):
            continue
        source_id = _require_str(profile, "id")
        functions = profile.get("functions")
        if not isinstance(functions, list):
            continue
        for function in functions:
            if not isinstance(function, dict):
                continue
            route_function_id = _require_str(function, "id")
            route_id = f"{source_id}-{route_function_id}"
            if route_id in routes:
                raise ValueError(f"duplicate source function id: {route_id}")
            routes[route_id] = (profile, function)
    return routes


def _eligible_route_candidate(
    route: tuple[Mapping[str, object], dict[str, object]],
    now: datetime,
    cache: Mapping[str, object],
    snapshot: Mapping[str, object],
    requested_geographies: frozenset[str],
    requested_industries: frozenset[str],
    minimum_originality: str | None,
    minimum_independence: str | None,
) -> RouteCandidate | None:
    profile, function = route
    if requested_geographies and not _matches_geography_scope(
        profile,
        requested_geographies,
    ):
        return None
    if requested_industries and not _matches_industry_scope(
        profile,
        requested_industries,
    ):
        return None

    source_id = _require_str(profile, "id")
    route_function_id = _require_str(function, "id")
    authority = _require_str(function, "authority")
    utility = _require_str(function, "utility")
    publisher_type = _require_str(profile, "publisher_type")
    originality, independence = _publisher_semantics(publisher_type)
    if minimum_originality is not None and (
        RATING_RANK[originality] < RATING_RANK[minimum_originality]
    ):
        return None
    if minimum_independence is not None and (
        RATING_RANK[independence] < RATING_RANK[minimum_independence]
    ):
        return None

    direct_url = _first_direct_url(function)
    reachability, last_checked = _resolve_reachability(
        profile,
        source_id,
        route_function_id,
        now,
        cache,
        snapshot,
    )
    stale = now - last_checked > ttl_for_status(reachability)
    skip_reason = None
    if reachability in UNAVAILABLE_REACHABILITY and not stale:
        skip_reason = f"fresh {reachability}"

    return RouteCandidate(
        source_id=source_id,
        function_id=route_function_id,
        authority=authority,
        originality=originality,
        independence=independence,
        reachability=reachability,
        utility=utility,
        direct_url=direct_url,
        stale=stale,
        skip_reason=skip_reason,
    )


def _fallback_route_ids(function: Mapping[str, object]) -> tuple[str, ...]:
    fallbacks = function.get("fallbacks")
    if not isinstance(fallbacks, list):
        raise ValueError("missing fallbacks")
    if not all(isinstance(fallback, str) for fallback in fallbacks):
        raise ValueError("fallbacks must contain only strings")
    return tuple(fallbacks)


def _should_follow_fallbacks(candidate: RouteCandidate) -> bool:
    return candidate.skip_reason is not None


def _find_function(profile: Mapping[str, object], function_id: str) -> dict[str, object] | None:
    functions = profile.get("functions")
    if not isinstance(functions, list):
        return None

    for function in functions:
        if isinstance(function, dict) and function.get("id") == function_id:
            return function
    return None


def _matches_geography_scope(
    profile: Mapping[str, object],
    requested_geographies: frozenset[str],
) -> bool:
    profile_geographies = profile.get("geographies")
    if not isinstance(profile_geographies, list):
        return False

    return any(
        (normalized_geography := _normalize_profile_geography(geography)) is not None
        and (
            normalized_geography in requested_geographies
            or normalized_geography in BROAD_GEOGRAPHIES
        )
        for geography in profile_geographies
    )


def _matches_industry_scope(
    profile: Mapping[str, object],
    requested_industries: frozenset[str],
) -> bool:
    profile_industries = profile.get("industries")
    if not isinstance(profile_industries, list):
        return False

    return any(
        (normalized_industry := _normalize_profile_industry(industry)) is not None
        and (normalized_industry in requested_industries or normalized_industry in BROAD_INDUSTRIES)
        for industry in profile_industries
    )


def _normalize_requested_geographies(
    geographies: Sequence[str] | None,
) -> frozenset[str]:
    if geographies is None:
        return frozenset()
    if isinstance(geographies, (str, bytes)):
        raise TypeError("geographies must be a sequence of strings, not str or bytes")

    normalized_geographies: set[str] = set()
    for geography in geographies:
        if not isinstance(geography, str):
            raise TypeError("geographies must contain only strings")
        normalized_geography = geography.strip().casefold()
        if not normalized_geography:
            raise ValueError("geographies must not contain blank labels")
        normalized_geographies.add(normalized_geography)

    return frozenset(normalized_geographies)


def _normalize_requested_industries(
    industry: str | None,
    industries: Sequence[str] | None,
) -> frozenset[str]:
    normalized_industries = set(
        _normalize_requested_scope_labels(
            industries,
            "industries",
        )
    )
    if industry is None:
        return frozenset(normalized_industries)
    if not isinstance(industry, str):
        raise TypeError("industry must be a string")
    normalized_industry = industry.strip().casefold()
    if not normalized_industry:
        raise ValueError("industry must not be blank")
    normalized_industries.add(normalized_industry)
    return frozenset(normalized_industries)


def _normalize_requested_scope_labels(
    labels: Sequence[str] | None,
    name: str,
) -> frozenset[str]:
    if labels is None:
        return frozenset()
    if isinstance(labels, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of strings, not str or bytes")

    normalized_labels: set[str] = set()
    for label in labels:
        if not isinstance(label, str):
            raise TypeError(f"{name} must contain only strings")
        normalized_label = label.strip().casefold()
        if not normalized_label:
            raise ValueError(f"{name} must not contain blank labels")
        normalized_labels.add(normalized_label)

    return frozenset(normalized_labels)


def _normalize_minimum_rating(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a rating string")
    normalized = value.strip().title()
    if normalized not in RATING_RANK:
        raise ValueError(f"{name} must be one of: {', '.join(RATING_RANK)}")
    return normalized


def _normalize_profile_geography(geography: object) -> str | None:
    if not isinstance(geography, str):
        return None

    normalized_geography = geography.strip().casefold()
    return normalized_geography or None


def _normalize_profile_industry(industry: object) -> str | None:
    if not isinstance(industry, str):
        return None

    normalized_industry = industry.strip().casefold()
    return normalized_industry or None


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
    function_id: str,
    now: datetime,
    cache: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> tuple[str, datetime]:
    access = profile.get("access")
    if not isinstance(access, dict):
        raise ValueError(f"{source_id}: missing access block")

    status = _require_str(access, "status")
    last_checked = _parse_aware_datetime(_require_str(access, "last_checked"))

    cached_source = cache.get(source_id)
    function_cached = _function_cache_observation(cached_source, function_id)
    if function_cached is not None and _is_current_cache_observation(function_cached, now):
        return function_cached

    cached = _optional_observation(cached_source)
    if cached is not None and _is_current_cache_observation(cached, now):
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


def _function_cache_observation(
    cache_entry: object,
    function_id: str,
) -> tuple[str, datetime] | None:
    if not isinstance(cache_entry, Mapping):
        return None
    functions = cache_entry.get("functions")
    if not isinstance(functions, Mapping):
        return None
    return _optional_observation(functions.get(function_id))


def _is_current_cache_observation(
    observation: tuple[str, datetime],
    now: datetime,
) -> bool:
    _, last_checked = observation
    return last_checked <= now and not _is_stale(*observation, now)


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
