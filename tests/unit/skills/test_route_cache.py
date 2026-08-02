from __future__ import annotations

import importlib.util
import json
import multiprocessing
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTE_CACHE_PATH = (
    REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts" / "route_cache.py"
)
NOW = datetime(2026, 8, 2, tzinfo=UTC)
SCOPE_FINGERPRINT = "a" * 64


def load_route_cache_module():
    assert ROUTE_CACHE_PATH.is_file(), f"missing route cache module: {ROUTE_CACHE_PATH}"
    script_dir = str(ROUTE_CACHE_PATH.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("route_cache", ROUTE_CACHE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def route(
    cache,
    route_id: str,
    *,
    layer: int,
    direct_url: str,
    source_function: str = "market-size",
    claim_type: str = "market-size",
    geographies: tuple[str, ...] = ("china",),
    industries: tuple[str, ...] = ("pop-toys",),
):
    return cache.PlannedRoute(
        route_id=route_id,
        route_layer=layer,
        subject="Pop Mart",
        subject_relation="direct",
        document_type="source-function",
        definition_scope_fingerprint=SCOPE_FINGERPRINT,
        claim_type=claim_type,
        geographies=geographies,
        industries=industries,
        query_variants=("Pop Mart market size",),
        source_id=route_id,
        source_function=source_function,
        direct_url=direct_url,
    )


def recipe_payload(
    *,
    reviewed_at: datetime,
    index_endpoint: str,
    claim_type: str = "market-size",
    geographies: list[str] | None = None,
    industries: list[str] | None = None,
    source_function: str = "market-size",
) -> dict[str, object]:
    return {
        "claim_type": claim_type,
        "geographies": geographies or ["China"],
        "industries": industries or ["pop-toys"],
        "subject_relation": "direct",
        "document_type": "source-function",
        "source_function": source_function,
        "query_pattern": '"{geography}" "{industry}" market size',
        "index_endpoint": index_endpoint,
        "identity_rule": "document ID plus SHA-256",
        "extraction_hint": "Market size table",
        "reviewed_at": reviewed_at.isoformat(),
    }


def write_cache(path: Path, recipes: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"schema_version": "1.0", "recipes": recipes}),
        encoding="utf-8",
    )


def record_success_worker(
    path_value: str,
    payload: dict[str, object],
    ready: multiprocessing.queues.Queue,
) -> None:
    cache = load_route_cache_module()
    recipe = cache.RouteRecipe.from_payload(payload)
    ready.put(True)
    cache.record_success(recipe, Path(path_value))


def test_load_route_cache_ignores_missing_invalid_and_stale_entries(tmp_path: Path) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"

    assert cache.load_route_cache(path, NOW) == []

    path.write_text("{not json", encoding="utf-8")
    assert cache.load_route_cache(path, NOW) == []

    write_cache(
        path,
        [
            recipe_payload(
                reviewed_at=NOW - cache.ROUTE_CACHE_TTL - timedelta(seconds=1),
                index_endpoint="https://stale.example/reports",
                source_function="stale-market-size",
            ),
            recipe_payload(
                reviewed_at=NOW - timedelta(days=1),
                index_endpoint="https://fresh.example/reports",
            ),
        ],
    )

    recipes = cache.load_route_cache(path, NOW)

    assert [recipe.index_endpoint for recipe in recipes] == ["https://fresh.example/reports"]


def test_route_cache_reorders_only_matching_existing_routes_within_layers(tmp_path: Path) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"
    write_cache(
        path,
        [
            recipe_payload(
                reviewed_at=NOW - timedelta(days=1),
                index_endpoint="https://preferred.example/reports",
            )
        ],
    )
    recipes = cache.load_route_cache(path, NOW)
    first = route(
        cache,
        "first",
        layer=1,
        direct_url="https://first.example/reports",
    )
    preferred = route(
        cache,
        "preferred",
        layer=1,
        direct_url="https://preferred.example/reports",
    )
    next_layer = route(
        cache,
        "next-layer",
        layer=2,
        direct_url="https://next.example/reports",
    )
    routes = (first, preferred, next_layer)

    ranked = cache.rank_with_route_cache(routes, recipes)

    assert tuple(route.route_id for route in ranked) == ("preferred", "first", "next-layer")
    assert tuple(route.route_layer for route in ranked) == tuple(
        route.route_layer for route in routes
    )
    assert {id(route) for route in ranked} == {id(route) for route in routes}
    assert tuple(route.definition_scope_fingerprint for route in ranked) == (
        SCOPE_FINGERPRINT,
        SCOPE_FINGERPRINT,
        SCOPE_FINGERPRINT,
    )


def test_route_cache_never_prioritizes_a_cross_scope_recipe(tmp_path: Path) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"
    write_cache(
        path,
        [
            recipe_payload(
                reviewed_at=NOW - timedelta(days=1),
                index_endpoint="https://preferred.example/reports",
                geographies=["Hong Kong"],
                industries=["pop-toys"],
            )
        ],
    )
    recipes = cache.load_route_cache(path, NOW)
    first = route(
        cache,
        "first",
        layer=1,
        direct_url="https://first.example/reports",
    )
    cross_scope = route(
        cache,
        "cross-scope",
        layer=1,
        direct_url="https://preferred.example/reports",
        geographies=("china",),
    )

    assert cache.rank_with_route_cache((first, cross_scope), recipes) == (
        first,
        cross_scope,
    )


def test_route_cache_cannot_change_acceptance_state_or_nonmatching_routes(
    tmp_path: Path,
) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"
    write_cache(
        path,
        [
            recipe_payload(
                reviewed_at=NOW - timedelta(days=1),
                index_endpoint="https://preferred.example/reports",
            )
        ],
    )
    recipes = cache.load_route_cache(path, NOW)
    nonmatching = route(
        cache,
        "nonmatching",
        layer=1,
        direct_url="https://nonmatching.example/reports",
        source_function="other-function",
    )
    routes = (nonmatching,)
    request = {
        "minimum_source_authority": "High",
        "minimum_conclusion_evidence": "High",
        "minimum_originality": "High",
        "minimum_independence": "Medium",
    }
    gate_result = {
        "passed": False,
        "failures": ("freshness",),
        "scope_fingerprint": SCOPE_FINGERPRINT,
    }
    request_before = deepcopy(request)
    gate_before = deepcopy(gate_result)

    ranked = cache.rank_with_route_cache(routes, recipes)

    assert ranked == routes
    assert request == request_before
    assert gate_result == gate_before
    assert ranked[0].definition_scope_fingerprint == SCOPE_FINGERPRINT


def test_record_success_replaces_invalid_cache_atomically_with_valid_recipe(tmp_path: Path) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"
    path.write_text("{not json", encoding="utf-8")
    recipe = cache.RouteRecipe.from_payload(
        recipe_payload(
            reviewed_at=NOW - timedelta(days=1),
            index_endpoint="https://preferred.example/reports",
        )
    )

    cache.record_success(recipe, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "1.0"
    assert raw["recipes"] == [recipe.to_payload()]
    assert cache.load_route_cache(path, NOW) == [recipe]
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_load_route_cache_rejects_duplicate_normalized_recipe_keys(tmp_path: Path) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"
    write_cache(
        path,
        [
            recipe_payload(
                reviewed_at=NOW - timedelta(days=1),
                index_endpoint="https://first.example/reports",
            ),
            recipe_payload(
                reviewed_at=NOW - timedelta(days=2),
                index_endpoint="https://second.example/reports",
                claim_type=" MARKET-SIZE ",
                geographies=[" china "],
                industries=[" POP-TOYS "],
                source_function=" MARKET-SIZE ",
            ),
        ],
    )

    assert cache.load_route_cache(path, NOW) == []


def test_record_success_rejects_whitespace_only_values_before_replacement(
    tmp_path: Path,
) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"
    write_cache(
        path,
        [
            recipe_payload(
                reviewed_at=NOW - timedelta(days=1),
                index_endpoint="https://existing.example/reports",
            )
        ],
    )
    original = path.read_text(encoding="utf-8")
    recipe = cache.RouteRecipe.from_payload(
        recipe_payload(
            reviewed_at=NOW - timedelta(days=1),
            index_endpoint="https://preferred.example/reports",
        )
    )

    with pytest.raises(ValueError, match="extraction_hint"):
        cache.record_success(replace(recipe, extraction_hint=" \t "), path)

    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_route_cache_does_not_expose_file_lock_as_public_api() -> None:
    cache = load_route_cache_module()

    assert not hasattr(cache, "cache_file_lock")
    assert callable(cache.record_success)


def test_parallel_record_success_preserves_both_recipes(tmp_path: Path) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    payloads = (
        recipe_payload(
            reviewed_at=NOW - timedelta(days=1),
            index_endpoint="https://first.example/reports",
            source_function="market-size-first",
        ),
        recipe_payload(
            reviewed_at=NOW - timedelta(days=1),
            index_endpoint="https://second.example/reports",
            source_function="market-size-second",
        ),
    )
    processes = [
        context.Process(target=record_success_worker, args=(str(path), payload, ready))
        for payload in payloads
    ]

    with cache._cache_file_lock(path):
        for process in processes:
            process.start()
        for _ in processes:
            assert ready.get(timeout=10) is True

    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert {recipe.source_function for recipe in cache.load_route_cache(path, NOW)} == {
        "market-size-first",
        "market-size-second",
    }


def test_replace_failure_cleans_temporary_file_and_preserves_existing_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = load_route_cache_module()
    path = tmp_path / "route-cache.json"
    write_cache(
        path,
        [
            recipe_payload(
                reviewed_at=NOW - timedelta(days=1),
                index_endpoint="https://existing.example/reports",
            )
        ],
    )
    original = path.read_text(encoding="utf-8")
    recipe = cache.RouteRecipe.from_payload(
        recipe_payload(
            reviewed_at=NOW - timedelta(days=1),
            index_endpoint="https://preferred.example/reports",
        )
    )

    def raise_replace(source: Path, destination: Path) -> None:
        raise OSError(f"forced replacement failure: {source} -> {destination}")

    monkeypatch.setattr(cache.os, "replace", raise_replace)

    with pytest.raises(OSError, match="forced replacement failure"):
        cache.record_success(recipe, path)

    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []
