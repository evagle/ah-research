from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from types import ModuleType

import pytest
import yaml

from .test_industry_bundle import REPO_ROOT, REQUIRED_ROLES, load_bundle_module

FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "source-discovery" / "industry-bundles"
SCRIPT_ROOT = REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts"


def load_fixture(name: str) -> dict[str, object]:
    path = FIXTURE_ROOT / name
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def load_script_module(name: str, *, module_name: str | None = None) -> ModuleType:
    path = SCRIPT_ROOT / f"{name}.py"
    loaded_name = module_name or name
    spec = importlib.util.spec_from_file_location(loaded_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loaded_name] = module
    spec.loader.exec_module(module)
    return module


def load_contract_pipeline() -> tuple[ModuleType, ModuleType, ModuleType]:
    script_dir = str(SCRIPT_ROOT)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    contracts = load_script_module("research_contracts")
    lineage = load_script_module(
        "source_lineage",
        module_name="fixture_source_lineage",
    )
    gate = load_script_module("evidence_gate", module_name="fixture_evidence_gate")
    return contracts, lineage, gate


def mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def mappings(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def strings(value: object) -> list[str]:
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return value


def build_request(
    fixture: Mapping[str, object],
    case: Mapping[str, object],
) -> dict[str, object]:
    market = mapping(fixture["market_definition"])
    request = mapping(case["request"])
    periods = strings(request["periods"])
    return {
        "schema_version": "1.1",
        "claim_id": request["claim_id"],
        "claim_type": request["claim_type"],
        "subject": fixture["subject"],
        "metric": request["metric"],
        "geographies": deepcopy(market["geographies"]),
        "industries": deepcopy(market["industries"]),
        "population": market["population"],
        "product_scope": request.get("product_scope", market["product_scope"]),
        "channel_scope": request.get("channel_scope", market["channel_scope"]),
        "measurement_basis": request["measurement_basis"],
        "denominator": request["denominator"],
        "period_start": periods[0],
        "period_end": periods[-1],
        "frequency": "annual",
        "continuity_required": request.get("continuity_required", len(periods) > 1),
        "required_latest_period": periods[-1],
        "accepted_units": [request["unit"]],
        "definition_constraints": [
            "candidate must preserve the declared market and series identity"
        ],
        "value_status_allowed": deepcopy(request["value_status_allowed"]),
        "minimum_source_authority": "Medium",
        "minimum_conclusion_evidence": "Medium",
        "minimum_originality": "Medium",
        "minimum_independence": "Medium",
        "independent_cross_check_required": request.get(
            "independent_cross_check_required",
            False,
        ),
        "accepted_source_classes": ["original-research", "issuer-first-party"],
        "absence_claim": False,
        "as_of": fixture["as_of"],
    }


def build_candidate(
    fixture: Mapping[str, object],
    requested: Mapping[str, object],
    spec: Mapping[str, object],
    *,
    contracts: ModuleType,
    lineage: ModuleType,
    gate: ModuleType,
) -> dict[str, object]:
    market = mapping(fixture["market_definition"])
    candidate_id = spec["candidate_id"]
    assert isinstance(candidate_id, str)
    slug = candidate_id.replace("_", "-")
    artifact_sha256 = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()
    source_url = f"https://fixtures.example/{slug}/source"
    document_url = f"https://fixtures.example/{slug}/document"
    document_id = f"FIXTURE-{candidate_id.upper().replace('-', '_')}"
    scope = {
        "geographies": deepcopy(market["geographies"]),
        "industries": deepcopy(market["industries"]),
        "product_scope": spec.get("product_scope", market["product_scope"]),
        "channel_scope": spec.get("channel_scope", market["channel_scope"]),
        "population": spec.get("population", market["population"]),
        "measurement_basis": spec["measurement_basis"],
        "denominator": spec["denominator"],
    }
    payload = {
        "schema_version": "1.1",
        "claim_id": requested["claim_id"],
        "metric": spec["metric"],
        "frequency": "annual",
        "period_semantics": "calendar-year",
        "source": {
            "immediate_publisher": spec["immediate_publisher"],
            "original_publisher": spec.get(
                "original_publisher",
                spec["methodology_owner"],
            ),
            "publisher_type": spec.get("publisher_type", "research-provider"),
            "source_class": spec.get("source_class", "original-research"),
            "canonical_url": source_url,
        },
        "document": {
            "document_id": document_id,
            "title": spec["report_title"],
            "published_at": spec["published_at"],
            "canonical_url": document_url,
        },
        "values": [],
        "canonical_unit": spec["unit"],
        "scope": scope,
        "data_vintage": spec["data_vintage"],
        "artifact": {
            "identity": f"sha256:{artifact_sha256}",
            "sha256": artifact_sha256,
        },
        "source_document_identity": {},
        "scope_fingerprint": "",
        "market_definition_fingerprint": "",
        "series_fingerprint": "",
        "reconciliations": [],
        "lineage": {
            "methodology_owner": spec["methodology_owner"],
            "underlying_dataset_ids": [],
            "underlying_report_ids": [],
            "cited_source_ids": [],
            "provider_table_id": spec["provider_table_id"],
        },
        "lineage_id": "",
        "runtime_evidence": {
            "source_authority": "High",
            "conclusion_evidence": "High",
            "originality": "High",
            "independence": "High",
            "evidence_level": "High",
        },
    }
    candidate_scope_request = dict(requested)
    candidate_scope_request.update(
        {
            "metric": spec["metric"],
            "geographies": deepcopy(scope["geographies"]),
            "industries": deepcopy(scope["industries"]),
            "population": scope["population"],
            "product_scope": scope["product_scope"],
            "channel_scope": scope["channel_scope"],
            "measurement_basis": scope["measurement_basis"],
            "denominator": scope["denominator"],
        }
    )
    scope_fingerprint = gate.request_scope_fingerprint(candidate_scope_request)
    payload["scope_fingerprint"] = scope_fingerprint
    for value in mappings(spec["values"]):
        payload["values"].append(
            {
                **deepcopy(value),
                "unit": spec["unit"],
                "definition_scope_fingerprint": scope_fingerprint,
                "canonical_value": {
                    "value": value["value"],
                    "unit": spec["unit"],
                    "definition_scope_fingerprint": scope_fingerprint,
                    "reconciliation_id": None,
                },
            }
        )
    payload["market_definition_fingerprint"] = contracts.market_definition_fingerprint(payload)
    payload["series_fingerprint"] = contracts.series_fingerprint(payload)
    payload["lineage_id"] = lineage.lineage_id(payload)
    identity_evidence = {
        "source_canonical_url": source_url,
        "document_canonical_url": document_url,
        "document_id": document_id,
        "artifact_sha256": artifact_sha256,
    }
    canonical_identity = json.dumps(
        identity_evidence,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    payload["source_document_identity"] = {
        **identity_evidence,
        "binding_sha256": hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest(),
    }
    return payload


def evaluate_fixture_cases(
    fixture: Mapping[str, object],
    *,
    contracts: ModuleType,
    lineage: ModuleType,
    gate: ModuleType,
) -> dict[str, dict[str, object]]:
    evaluated: dict[str, dict[str, object]] = {}
    for case in mappings(fixture["evidence_cases"]):
        requested = build_request(fixture, case)
        contracts.validate_payload("request", requested)
        candidate_specs = mappings(case["candidates"])
        candidates = [
            build_candidate(
                fixture,
                requested,
                candidate_spec,
                contracts=contracts,
                lineage=lineage,
                gate=gate,
            )
            for candidate_spec in candidate_specs
        ]
        for candidate in candidates:
            contracts.validate_payload("candidate", candidate)
            assert candidate["lineage_id"] == lineage.lineage_id(candidate)

        expected = mapping(case["expected"])
        if expected.get("same_lineage") is True:
            assert len(candidates) == 2
            assert lineage.same_lineage(candidates[0], candidates[1]) is True
        result = gate.evaluate_candidate(
            requested,
            candidates[0],
            accepted_candidates=candidates[1:],
        )
        assert result.passed is expected["passed"]
        assert result.failures == tuple(strings(expected["failures"]))
        case_id = case["case_id"]
        assert isinstance(case_id, str)
        evaluated[case_id] = {
            "request": requested,
            "candidates": candidates,
            "result": result,
        }
    return evaluated


def assert_role_evidence_matches_bundle(
    fixture: Mapping[str, object],
    evaluated: Mapping[str, Mapping[str, object]],
) -> None:
    roles = {role["role"]: role for role in mappings(fixture["role_outcomes"])}
    for role_name, case_ids_value in mapping(fixture["role_evidence"]).items():
        case_ids = strings(case_ids_value)
        evidence = [evaluated[case_id] for case_id in case_ids]
        results = [item["result"] for item in evidence]
        candidates = [item["candidates"][0] for item in evidence]
        assert all(result.passed for result in results)

        role = roles[role_name]
        series = mappings(role["series"])
        assert len(series) == 1
        descriptor = series[0]
        accepted_periods = {value.period for result in results for value in result.series_values}
        assert accepted_periods == set(strings(role["accepted_periods"]))
        assert role["accepted_evidence_count"] == len(accepted_periods)
        assert {candidate["market_definition_fingerprint"] for candidate in candidates} == {
            descriptor["market_definition_fingerprint"]
        }
        assert {candidate["series_fingerprint"] for candidate in candidates} == {
            descriptor["series_fingerprint"]
        }
        assert {candidate["lineage_id"] for candidate in candidates} == {descriptor["lineage_id"]}
        assert set(strings(descriptor["periods"])) == accepted_periods
        assert {mapping(candidate["scope"])["channel_scope"] for candidate in candidates} == {
            descriptor["channel_scope"]
        }
        assert {mapping(candidate["scope"])["denominator"] for candidate in candidates} == {
            descriptor["denominator"]
        }
        assert {candidate["data_vintage"] for candidate in candidates} == {
            descriptor["data_vintage"]
        }
        assert {mapping(candidate["document"])["published_at"] for candidate in candidates} == {
            descriptor["published_at"]
        }


@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    (
        ("pop-mart.yaml", "publishable-with-gaps"),
        ("kweichow-moutai.yaml", "publishable-with-gaps"),
        ("smic.yaml", "publishable-with-gaps"),
    ),
)
def test_cross_industry_candidates_flow_through_contract_lineage_gate_and_bundle(
    fixture_name: str,
    expected_status: str,
) -> None:
    contracts, lineage, gate = load_contract_pipeline()
    bundle = load_bundle_module()
    fixture = load_fixture(fixture_name)

    assert len(fixture["role_outcomes"]) == len(REQUIRED_ROLES)
    assert len(fixture["scope_breaks"]) >= 1
    evaluated = evaluate_fixture_cases(
        fixture,
        contracts=contracts,
        lineage=lineage,
        gate=gate,
    )
    assert_role_evidence_matches_bundle(fixture, evaluated)

    result = bundle.evaluate_industry_bundle(
        subject=fixture["subject"],
        as_of=date.fromisoformat(fixture["as_of"]),
        primary_market_scope_fingerprint=fixture["primary_market_scope_fingerprint"],
        role_outcomes=fixture["role_outcomes"],
        scope_breaks=fixture["scope_breaks"],
    )
    contracts.validate_payload("industry-bundle", result)

    assert result["schema_version"] == "1.1"
    assert [role["role"] for role in result["roles"]] == list(REQUIRED_ROLES)
    assert result["status"] == expected_status
    assert result["unresolved_claim_ids"] == fixture["unresolved_claim_ids"]


def test_pop_mart_gmv_and_rsv_share_market_identity_but_not_series_identity() -> None:
    contracts, lineage, gate = load_contract_pipeline()
    fixture = load_fixture("pop-mart.yaml")
    evaluated = evaluate_fixture_cases(
        fixture,
        contracts=contracts,
        lineage=lineage,
        gate=gate,
    )
    gmv = evaluated["pop-mart-historical-gmv"]["candidates"][0]
    rsv = evaluated["pop-mart-rsv-mismatch"]["candidates"][0]

    assert gmv["market_definition_fingerprint"] == rsv["market_definition_fingerprint"]
    assert gmv["series_fingerprint"] != rsv["series_fingerprint"]
    assert evaluated["pop-mart-rsv-mismatch"]["result"].failures == ("scope",)


def test_pop_mart_republication_and_forecast_label_cases_are_machine_checked() -> None:
    contracts, lineage, gate = load_contract_pipeline()
    fixture = load_fixture("pop-mart.yaml")
    evaluated = evaluate_fixture_cases(
        fixture,
        contracts=contracts,
        lineage=lineage,
        gate=gate,
    )
    republications = evaluated["pop-mart-provider-table-republication"]
    forecast = evaluated["pop-mart-forecast"]
    mislabeled = evaluated["pop-mart-mislabeled-forecast"]

    assert republications["result"].failures == ("lineage",)
    assert forecast["result"].passed is True
    assert {value.status for value in forecast["result"].series_values} == {"forecast"}
    assert mislabeled["result"].failures == ("value_status", "freshness")


def test_moutai_issuer_revenue_cannot_be_converted_to_market_share() -> None:
    contracts, lineage, gate = load_contract_pipeline()
    fixture = load_fixture("kweichow-moutai.yaml")
    evaluated = evaluate_fixture_cases(
        fixture,
        contracts=contracts,
        lineage=lineage,
        gate=gate,
    )

    assert evaluated["moutai-issuer-revenue-share"]["result"].failures == (
        "scope",
        "continuity",
    )


def test_smic_revenue_share_rejects_wafer_and_accounting_denominators() -> None:
    contracts, lineage, gate = load_contract_pipeline()
    fixture = load_fixture("smic.yaml")
    evaluated = evaluate_fixture_cases(
        fixture,
        contracts=contracts,
        lineage=lineage,
        gate=gate,
    )

    assert evaluated["smic-wafer-share-mismatch"]["result"].failures == ("scope",)
    assert evaluated["smic-accounting-revenue-share"]["result"].failures == (
        "scope",
        "continuity",
    )
