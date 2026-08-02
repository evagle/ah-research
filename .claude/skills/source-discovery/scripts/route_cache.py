"""Validated successful-route cache that can only reprioritize planned routes."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from discovery_planner import PlannedRoute
from research_contracts import validate_payload

ROUTE_CACHE_TTL = timedelta(days=30)


@dataclass(frozen=True)
class RouteRecipe:
    """One reviewed route pattern eligible to prioritize a matching route."""

    claim_type: str
    geographies: tuple[str, ...]
    industries: tuple[str, ...]
    subject_relation: str
    document_type: str
    source_function: str
    query_pattern: str
    index_endpoint: str
    identity_rule: str
    extraction_hint: str
    reviewed_at: datetime

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> RouteRecipe:
        """Build a recipe from a schema-validated JSON payload."""
        if not isinstance(payload, Mapping):
            raise TypeError("route recipe must be a mapping")
        reviewed_at = _parse_datetime(_required_string(payload, "reviewed_at"))
        return cls(
            claim_type=_required_string(payload, "claim_type"),
            geographies=_required_labels(payload, "geographies"),
            industries=_required_labels(payload, "industries"),
            subject_relation=_required_string(payload, "subject_relation"),
            document_type=_required_string(payload, "document_type"),
            source_function=_required_string(payload, "source_function"),
            query_pattern=_required_string(payload, "query_pattern"),
            index_endpoint=_required_string(payload, "index_endpoint"),
            identity_rule=_required_string(payload, "identity_rule"),
            extraction_hint=_required_string(payload, "extraction_hint"),
            reviewed_at=reviewed_at,
        )

    def to_payload(self) -> dict[str, object]:
        """Return the versioned-contract representation for this recipe."""
        _require_aware_datetime(self.reviewed_at, "reviewed_at")
        return {
            "claim_type": self.claim_type,
            "geographies": list(self.geographies),
            "industries": list(self.industries),
            "subject_relation": self.subject_relation,
            "document_type": self.document_type,
            "source_function": self.source_function,
            "query_pattern": self.query_pattern,
            "index_endpoint": self.index_endpoint,
            "identity_rule": self.identity_rule,
            "extraction_hint": self.extraction_hint,
            "reviewed_at": self.reviewed_at.isoformat(),
        }

    def cache_key(self) -> tuple[object, ...]:
        """Return the complete cache key independent of presentation case."""
        return (
            _normalized_text(self.claim_type),
            _normalized_labels(self.geographies),
            _normalized_labels(self.industries),
            _normalized_text(self.subject_relation),
            _normalized_text(self.document_type),
            _normalized_text(self.source_function),
        )

    def sort_key(self) -> tuple[object, ...]:
        return (*self.cache_key(), self.reviewed_at.isoformat(), self.index_endpoint)


def load_route_cache(path: Path, now: datetime) -> list[RouteRecipe]:
    """Load only fresh, contract-valid recipes, returning no cache on corruption."""
    _require_aware_datetime(now, "now")
    recipes = _read_valid_recipes(path)
    return sorted(
        (recipe for recipe in recipes if _is_fresh(recipe, now)),
        key=RouteRecipe.sort_key,
    )


def rank_with_route_cache(
    routes: Sequence[PlannedRoute],
    recipes: Sequence[RouteRecipe],
) -> tuple[PlannedRoute, ...]:
    """Reorder matching existing routes without changing layer positions or contents."""
    positions_by_layer: dict[int, list[int]] = {}
    for position, route in enumerate(routes):
        positions_by_layer.setdefault(route.route_layer, []).append(position)

    ranked = list(routes)
    for positions in positions_by_layer.values():
        ordered_routes = sorted(
            (routes[position] for position in positions),
            key=lambda route: _route_priority(route, recipes),
        )
        for position, route in zip(positions, ordered_routes, strict=True):
            ranked[position] = route
    return tuple(ranked)


def record_success(recipe: RouteRecipe, path: Path) -> None:
    """Persist one successful recipe through a validated same-directory replace."""
    if not isinstance(recipe, RouteRecipe):
        raise TypeError("recipe must be a RouteRecipe")

    canonical_recipe = _canonical_recipe(recipe)
    with _cache_file_lock(path):
        existing = _read_valid_recipes(path)
        updated = [
            existing_recipe
            for existing_recipe in existing
            if existing_recipe.cache_key() != canonical_recipe.cache_key()
        ]
        updated.append(canonical_recipe)
        updated.sort(key=RouteRecipe.sort_key)
        payload = _cache_payload(_parse_cache_payload(_cache_payload(updated)))
        _atomic_write_json(path, payload)


@contextmanager
def _cache_file_lock(path: Path) -> Iterator[None]:
    """Hold an advisory, process-safe lock for one cache file transaction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _route_priority(
    route: PlannedRoute,
    recipes: Sequence[RouteRecipe],
) -> tuple[object, ...]:
    matches = [recipe for recipe in recipes if _recipe_fits_route(recipe, route)]
    if not matches:
        return (1, "", "", "")
    best = max(matches, key=lambda recipe: (recipe.reviewed_at, recipe.sort_key()))
    return (
        0,
        -best.reviewed_at.timestamp(),
        best.index_endpoint,
        best.query_pattern,
    )


def _recipe_fits_route(recipe: RouteRecipe, route: PlannedRoute) -> bool:
    """Match the complete normalized route-cache key plus canonical endpoint."""
    return _route_cache_key(route) == recipe.cache_key() and _normalized_url(
        route.direct_url
    ) == _normalized_url(recipe.index_endpoint)


def _read_valid_recipes(path: Path) -> list[RouteRecipe]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, Mapping):
        return []
    try:
        return list(_parse_cache_payload(payload))
    except (KeyError, TypeError, ValueError):
        return []


def _is_fresh(recipe: RouteRecipe, now: datetime) -> bool:
    return recipe.reviewed_at <= now and now - recipe.reviewed_at <= ROUTE_CACHE_TTL


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=True, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        serialized = json.loads(temp_path.read_text(encoding="utf-8"))
        if not isinstance(serialized, Mapping):
            raise ValueError("route cache payload must be a mapping")
        _parse_cache_payload(serialized)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid route cache timestamp: {value}") from exc
    _require_aware_datetime(parsed, "reviewed_at")
    return parsed.astimezone(UTC)


def _required_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"route recipe requires a non-empty {field}")
    return value.strip()


def _required_labels(payload: Mapping[str, object], field: str) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"route recipe requires labels for {field}")
    labels = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if not labels or len(labels) != len(value):
        raise ValueError(f"route recipe requires non-empty labels for {field}")
    return labels


def _require_aware_datetime(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _normalized_labels(labels: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({_normalized_text(label) for label in labels}))


def _normalized_text(value: object) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _normalized_url(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    parsed = urlsplit(value.strip())
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path.rstrip("/"),
            parsed.query,
            "",
        )
    )


def _canonical_recipe(recipe: RouteRecipe) -> RouteRecipe:
    return _parse_cache_payload(_cache_payload((recipe,)))[0]


def _cache_payload(recipes: Sequence[RouteRecipe]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "recipes": [recipe.to_payload() for recipe in recipes],
    }


def _parse_cache_payload(payload: Mapping[str, object]) -> tuple[RouteRecipe, ...]:
    validate_payload("route-cache", payload)
    raw_recipes = payload.get("recipes")
    if not isinstance(raw_recipes, list):
        raise ValueError("route cache recipes must be a list")
    if not all(isinstance(recipe, Mapping) for recipe in raw_recipes):
        raise ValueError("route cache recipes must be mappings")

    recipes = tuple(RouteRecipe.from_payload(recipe) for recipe in raw_recipes)
    keys = [recipe.cache_key() for recipe in recipes]
    if len(keys) != len(set(keys)):
        raise ValueError("route cache contains duplicate normalized recipe keys")
    return recipes


def _route_cache_key(route: PlannedRoute) -> tuple[object, ...]:
    return (
        _normalized_text(route.claim_type),
        _normalized_labels(route.geographies),
        _normalized_labels(route.industries),
        _normalized_text(route.subject_relation),
        _normalized_text(route.document_type),
        _normalized_text(route.source_function),
    )
