from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

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


def load_schema() -> dict[str, object]:
    assert SCHEMA_PATH.is_file(), f"missing schema: {SCHEMA_PATH}"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_profile(name: str) -> dict[str, object]:
    path = FIXTURES_ROOT / name
    assert path.is_file(), f"missing fixture: {path}"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


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
