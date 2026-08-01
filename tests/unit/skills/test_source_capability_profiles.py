from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "source-discovery"
    / "references"
    / "source-profile.schema.json"
)
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "source-discovery" / "profiles"
SCRIPT_PATH = (
    REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts" / "source_profiles.py"
)


def load_schema() -> dict[str, object]:
    assert SCHEMA_PATH.is_file(), f"missing schema: {SCHEMA_PATH}"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_profile(name: str) -> dict[str, object]:
    path = FIXTURES_ROOT / name
    assert path.is_file(), f"missing fixture: {path}"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def load_source_profiles_module():
    assert SCRIPT_PATH.is_file(), f"missing script: {SCRIPT_PATH}"
    spec = importlib.util.spec_from_file_location("source_profiles", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_profile(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def validator() -> Draft202012Validator:
    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_source_profile_schema_is_valid() -> None:
    validator()


def test_example_profiles_validate() -> None:
    profile_validator = validator()
    for fixture_name in ("official-example.yaml", "aggregator-example.yaml"):
        assert not list(profile_validator.iter_errors(load_profile(fixture_name)))


def test_profile_requires_observed_error() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    del invalid["access"]["observed_error"]

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_requires_limitation() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    del invalid["access"]["limitation"]

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_requires_direct_urls() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    del invalid["functions"][0]["direct_urls"]

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_requires_same_function_fallback() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    invalid["functions"][0]["fallbacks"] = []

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_rejects_invalid_evidence_level() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    invalid["access"]["evidence_level"] = "Unsupported"

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_accepts_explicit_observed_error_state() -> None:
    profile = deepcopy(load_profile("official-example.yaml"))
    profile["access"]["status"] = "temporarily-unreachable"
    profile["access"]["observed_error"] = {
        "state": "error",
        "category": "http",
        "message": "HTTP 503 from origin",
    }

    errors = list(validator().iter_errors(profile))

    assert not errors


def test_load_profiles_reports_the_invalid_file_path(tmp_path: Path) -> None:
    source_profiles = load_source_profiles_module()
    invalid = deepcopy(load_profile("official-example.yaml"))
    del invalid["functions"][0]["direct_urls"]
    invalid_path = tmp_path / "invalid.yaml"
    write_profile(invalid_path, invalid)

    with pytest.raises(ValueError, match=r"invalid\.yaml"):
        source_profiles.load_profiles(tmp_path, SCHEMA_PATH)


def test_load_profiles_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    source_profiles = load_source_profiles_module()
    write_profile(tmp_path / "official.yaml", load_profile("official-example.yaml"))
    duplicate = deepcopy(load_profile("aggregator-example.yaml"))
    duplicate["id"] = "sse"
    write_profile(tmp_path / "duplicate.yaml", duplicate)

    with pytest.raises(ValueError, match="duplicate source id"):
        source_profiles.load_profiles(tmp_path, SCHEMA_PATH)


def test_official_route_beats_reachable_aggregator_for_same_function() -> None:
    source_profiles = load_source_profiles_module()
    routes = source_profiles.select_routes(
        profiles=[
            load_profile("aggregator-example.yaml"),
            load_profile("official-example.yaml"),
        ],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert [route.source_id for route in routes] == ["sse", "eastmoney"]
    assert routes[0].authority == "High"
    assert routes[0].reachability == "reachable"
    assert routes[0].skip_reason is None


def test_fresh_temporarily_unreachable_route_is_skipped_for_fallback() -> None:
    source_profiles = load_source_profiles_module()
    official = deepcopy(load_profile("official-example.yaml"))
    official["access"]["status"] = "temporarily-unreachable"
    official["access"]["last_checked"] = "2026-08-02T11:00:00+00:00"
    official["access"]["observed_error"] = {
        "state": "error",
        "category": "http",
        "message": "HTTP 503 from origin",
    }
    routes = source_profiles.select_routes(
        profiles=[official, load_profile("aggregator-example.yaml")],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
    )

    assert [route.source_id for route in routes] == ["eastmoney", "sse"]
    assert routes[0].skip_reason is None
    assert routes[1].reachability == "temporarily-unreachable"
    assert routes[1].skip_reason == "fresh temporarily-unreachable"
    assert routes[1].stale is False


def test_stale_temporarily_unreachable_route_is_returned_for_refresh() -> None:
    source_profiles = load_source_profiles_module()
    official = deepcopy(load_profile("official-example.yaml"))
    official["access"]["status"] = "temporarily-unreachable"
    official["access"]["last_checked"] = "2026-08-01T10:00:00+00:00"
    official["access"]["observed_error"] = {
        "state": "error",
        "category": "http",
        "message": "HTTP 503 from origin",
    }
    routes = source_profiles.select_routes(
        profiles=[load_profile("aggregator-example.yaml"), official],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
    )

    assert [route.source_id for route in routes] == ["sse", "eastmoney"]
    assert routes[0].reachability == "temporarily-unreachable"
    assert routes[0].stale is True
    assert routes[0].skip_reason is None


def test_reachability_override_does_not_change_authority() -> None:
    source_profiles = load_source_profiles_module()
    routes = source_profiles.select_routes(
        profiles=[load_profile("official-example.yaml")],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        cache={
            "sse": {
                "status": "temporarily-unreachable",
                "last_checked": "2026-08-02T11:30:00+00:00",
            }
        },
    )

    assert len(routes) == 1
    assert routes[0].source_id == "sse"
    assert routes[0].authority == "High"
    assert routes[0].reachability == "temporarily-unreachable"
    assert routes[0].skip_reason == "fresh temporarily-unreachable"


def test_approved_status_ttls_match_global_constraints() -> None:
    source_profiles = load_source_profiles_module()

    assert source_profiles.ttl_for_status("reachable") == timedelta(days=30)
    assert source_profiles.ttl_for_status("reachable-limited") == timedelta(days=30)
    assert source_profiles.ttl_for_status("login-required") == timedelta(days=14)
    assert source_profiles.ttl_for_status("paywalled") == timedelta(days=14)
    assert source_profiles.ttl_for_status("anti-bot") == timedelta(days=14)
    assert source_profiles.ttl_for_status("temporarily-unreachable") == timedelta(hours=24)
    assert source_profiles.ttl_for_status("moved") == timedelta(days=7)
    assert source_profiles.ttl_for_status("broken-link") == timedelta(days=7)
    assert source_profiles.ttl_for_status("unverified") == timedelta(hours=24)
