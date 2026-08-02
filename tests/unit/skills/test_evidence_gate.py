from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_GATE_PATH = (
    REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts" / "evidence_gate.py"
)
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "source-discovery"
    / "evidence"
    / "pop-mart-industry-series.yaml"
)
FITTING_SCOPE_FINGERPRINT = "b6616573be4a7627d0ece917e9230e2ffa226066166adac7a5d5dc1eebf21582"
BROADER_SCOPE_FINGERPRINT = "be31d973e08201d0ea9716d0b6df640ef24a98a10728a587272f0dc489da1e99"
COLLECTIBLE_TOY_SCOPE_FINGERPRINT = (
    "28d53e87a06031e5eac5d66ae05755e39a270d822d4fb8221b65e70329103d7f"
)
WHOLESALE_METRIC_SCOPE_FINGERPRINT = (
    "a62057e2cb3cf1cdd91dd9ab988383bf8e4a28986f5ad78a96f419dfc5b30498"
)
EXTRA_POPULATION_SCOPE_FINGERPRINT = (
    "fe07b694898bbc9adddd4a6a9dcb61c46013a137017f88065c8cab39eed0b7de"
)
EVENT_SCOPE_FINGERPRINT = "7d8fbc9dca3f2e7a5f04c362bef6d4773f35f439be1eb0b65001725e5625dafe"
EVENT_TEXT = "Counterparty stated the board withdrew the acquisition proposal on 2025-03-01."


def load_gate_module():
    assert EVIDENCE_GATE_PATH.is_file(), f"missing evidence gate: {EVIDENCE_GATE_PATH}"
    script_dir = str(EVIDENCE_GATE_PATH.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("evidence_gate", EVIDENCE_GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture_payload() -> dict[str, object]:
    payload = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def request() -> dict[str, object]:
    payload = fixture_payload()["request"]
    assert isinstance(payload, dict)
    return deepcopy(payload)


def candidate(name: str) -> dict[str, object]:
    candidates = fixture_payload()["candidates"]
    assert isinstance(candidates, dict)
    payload = candidates[name]
    assert isinstance(payload, dict)
    return deepcopy(payload)


def values(payload: dict[str, object]) -> list[dict[str, object]]:
    series_values = payload["values"]
    assert isinstance(series_values, list)
    assert all(isinstance(value, dict) for value in series_values)
    return series_values


def scope(payload: dict[str, object]) -> dict[str, object]:
    candidate_scope = payload["scope"]
    assert isinstance(candidate_scope, dict)
    return candidate_scope


def runtime_evidence(payload: dict[str, object]) -> dict[str, object]:
    evidence = payload["runtime_evidence"]
    assert isinstance(evidence, dict)
    return evidence


def rebind_identity(payload: dict[str, object]) -> None:
    source = payload["source"]
    document = payload["document"]
    artifact = payload["artifact"]
    assert isinstance(source, dict)
    assert isinstance(document, dict)
    assert isinstance(artifact, dict)
    artifact_sha256 = artifact["sha256"]
    assert isinstance(artifact_sha256, str)
    artifact["identity"] = f"sha256:{artifact_sha256}"
    binding = {
        "artifact_sha256": artifact_sha256,
        "document_canonical_url": document["canonical_url"],
        "document_id": document["document_id"],
        "source_canonical_url": source["canonical_url"],
    }
    canonical = json.dumps(binding, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    payload["source_document_identity"] = {
        **binding,
        "binding_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def rebind_lineage(
    payload: dict[str, object],
    underlying_report_id: str,
) -> None:
    normalized_report_id = " ".join(underlying_report_id.casefold().split())
    canonical = json.dumps(
        [normalized_report_id],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    payload["lineage"] = {
        "methodology_owner": payload["source"]["original_publisher"],
        "underlying_dataset_ids": [],
        "underlying_report_ids": [underlying_report_id],
        "cited_source_ids": [],
    }
    payload["lineage_id"] = "underlying:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_value(
    period: str,
    value: float,
    status: str = "observed",
) -> dict[str, object]:
    return {
        "period": period,
        "value": value,
        "unit": "CNY billion",
        "status": status,
        "definition_scope_fingerprint": FITTING_SCOPE_FINGERPRINT,
        "canonical_value": {
            "value": value,
            "unit": "CNY billion",
            "definition_scope_fingerprint": FITTING_SCOPE_FINGERPRINT,
            "reconciliation_id": None,
        },
    }


def set_series(
    payload: dict[str, object],
    *,
    frequency: str,
    period_semantics: str,
    periods: list[str],
    vintage: str,
) -> None:
    payload["frequency"] = frequency
    payload["period_semantics"] = period_semantics
    payload["data_vintage"] = vintage
    payload["values"] = [
        canonical_value(period, float(index + 1)) for index, period in enumerate(periods)
    ]


def temporal_request(
    frequency: str,
    period_start: str,
    period_end: str,
) -> dict[str, object]:
    payload = request()
    payload["frequency"] = frequency
    payload["period_start"] = period_start
    payload["period_end"] = period_end
    payload["required_latest_period"] = period_end
    return payload


def event_request(
    accepted_source_classes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "claim_id": "management-governance-event-2025",
        "claim_type": "governance-event",
        "subject": "Management governance event outside bound manifests",
        "metric": "governance event text",
        "geographies": ["China"],
        "industries": ["consumer-discretionary"],
        "population": "issuer directors, executives, and named counterparties",
        "product_scope": "management governance events outside bound manifests",
        "measurement_basis": "dated attributable event text",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "frequency": "event-driven",
        "continuity_required": False,
        "required_latest_period": "2025-12-31",
        "accepted_units": ["event"],
        "definition_constraints": [
            "must preserve occurrence date and named subjects",
            "must preserve exact quoted governance event text",
        ],
        "value_status_allowed": ["observed"],
        "minimum_source_authority": "High",
        "minimum_conclusion_evidence": "High",
        "minimum_originality": "High",
        "minimum_independence": "Medium",
        "independent_cross_check_required": False,
        "accepted_source_classes": accepted_source_classes
        or ["issuer-first-party", "named-counterparty", "auditor"],
        "absence_claim": False,
        "as_of": "2025-12-31",
    }


def regulatory_request(
    accepted_source_classes: list[str] | None = None,
) -> dict[str, object]:
    payload = event_request(
        accepted_source_classes=accepted_source_classes
        or ["official-regulator", "official-exchange", "official-court"]
    )
    payload.update(
        {
            "claim_id": "management-regulatory-context-2025",
            "claim_type": "regulatory-context",
            "subject": "Applicable regulatory context for management conduct",
            "metric": "regulatory context text",
            "population": "issuer management, directors, controllers, and the governing jurisdiction",
            "product_scope": "official regulatory context tied to the subject event",
            "measurement_basis": "official rule text and applicability to the subject event",
            "accepted_units": ["document"],
        }
    )
    return payload


def event_candidate(
    *,
    claim_id: str = "management-governance-event-2025",
    metric: str = "governance event text",
    population: str = "issuer directors, executives, and named counterparties",
    product_scope: str = "management governance events outside bound manifests",
    measurement_basis: str = "dated attributable event text",
    source_class: str = "named-counterparty",
    period: str = "2025-03-01",
    event_key: str = "2025-03-01|board|withdraw-acquisition-proposal",
    unit: str = "event",
    published_at: str = "2025-03-02",
    data_vintage: str = "2025-03-02",
    evidence_id: str = "event-2025-03-01-counterparty",
) -> dict[str, object]:
    publisher_type = {
        "official-regulator": "official-regulator",
        "official-exchange": "official-exchange",
        "official-court": "official-court",
        "issuer-first-party": "issuer-statement",
        "named-counterparty": "counterparty-statement",
        "auditor": "auditor-report",
        "media": "media",
    }.get(source_class, "counterparty-statement")
    payload = {
        "schema_version": "1.0",
        "claim_id": claim_id,
        "metric": metric,
        "frequency": "event-driven",
        "period_semantics": "event-date",
        "source": {
            "immediate_publisher": "Named Counterparty Noticeboard",
            "original_publisher": "Named Counterparty Noticeboard",
            "publisher_type": publisher_type,
            "source_class": source_class,
            "canonical_url": "https://counterparty.example.org/notices/2025-03-02",
        },
        "document": {
            "document_id": "COUNTERPARTY-NOTICE-2025-03-02",
            "title": "Counterparty Governance Notice",
            "published_at": published_at,
            "canonical_url": "https://counterparty.example.org/notices/2025-03-02",
        },
        "values": [
            {
                "period": period,
                "value": EVENT_TEXT,
                "unit": unit,
                "status": "observed",
                "event_key": event_key,
                "evidence_id": evidence_id,
                "definition_scope_fingerprint": EVENT_SCOPE_FINGERPRINT,
                "canonical_value": {
                    "value": EVENT_TEXT,
                    "unit": unit,
                    "definition_scope_fingerprint": EVENT_SCOPE_FINGERPRINT,
                    "reconciliation_id": None,
                },
            }
        ],
        "canonical_unit": unit,
        "scope": {
            "geographies": ["China"],
            "industries": ["consumer-discretionary"],
            "product_scope": product_scope,
            "population": population,
            "measurement_basis": measurement_basis,
        },
        "data_vintage": data_vintage,
        "artifact": {
            "identity": "sha256:7777777777777777777777777777777777777777777777777777777777777777",
            "sha256": "7777777777777777777777777777777777777777777777777777777777777777",
        },
        "scope_fingerprint": EVENT_SCOPE_FINGERPRINT,
        "reconciliations": [],
        "lineage_id": f"{source_class}-governance-2025-03-02",
        "runtime_evidence": {
            "source_authority": "High",
            "conclusion_evidence": "High",
            "originality": "High",
            "independence": "High",
            "evidence_level": "High",
        },
    }
    rebind_identity(payload)
    rebind_lineage(payload, f"{source_class}-governance-2025-03-02")
    return payload


def rebind_scope_fingerprint(
    payload: dict[str, object],
    requested: dict[str, object],
    gate_module,
) -> None:
    scope_fingerprint = gate_module.request_scope_fingerprint(requested)
    payload["scope_fingerprint"] = scope_fingerprint
    for value in values(payload):
        value["definition_scope_fingerprint"] = scope_fingerprint
        canonical = value["canonical_value"]
        assert isinstance(canonical, dict)
        canonical["definition_scope_fingerprint"] = scope_fingerprint


def test_fitting_official_series_passes() -> None:
    gate = load_gate_module()

    result = gate.evaluate_candidate(request(), candidate("fitting_official"))

    assert result.passed is True
    assert result.failures == ()
    assert result.scope_fingerprint == FITTING_SCOPE_FINGERPRINT
    assert result.series_form == "single"


def test_gate_result_binds_the_request_claim_and_scope() -> None:
    gate = load_gate_module()
    requested = request()

    result = gate.evaluate_candidate(requested, candidate("fitting_official"))

    assert result.claim_id == requested["claim_id"]
    assert result.scope_fingerprint == gate.request_scope_fingerprint(requested)


def test_event_candidate_preserves_exact_text_when_accepted() -> None:
    gate = load_gate_module()
    requested = event_request()
    candidate_payload = event_candidate(source_class="named-counterparty")
    rebind_scope_fingerprint(candidate_payload, requested, gate)

    result = gate.evaluate_candidate(
        requested,
        candidate_payload,
    )

    assert result.passed is True
    assert result.failures == ()
    assert result.series_form == "event-set"
    assert [value.period for value in result.series_values] == ["2025-03-01"]
    assert result.series_values[0].value == EVENT_TEXT
    assert result.series_values[0].event_key == "2025-03-01|board|withdraw-acquisition-proposal"
    assert result.series_values[0].evidence_id == "event-2025-03-01-counterparty"


def test_event_candidate_outside_window_fails_continuity() -> None:
    gate = load_gate_module()
    requested = event_request()
    candidate_payload = event_candidate(period="2024-12-31")
    rebind_scope_fingerprint(candidate_payload, requested, gate)

    result = gate.evaluate_candidate(
        requested,
        candidate_payload,
    )

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_event_candidate_with_pre_occurrence_publication_fails_freshness() -> None:
    gate = load_gate_module()
    requested = event_request()
    candidate_payload = event_candidate(published_at="2025-02-28")
    rebind_scope_fingerprint(candidate_payload, requested, gate)

    result = gate.evaluate_candidate(requested, candidate_payload)

    assert result.passed is False
    assert result.failures == ("freshness",)


def test_event_candidate_with_pre_occurrence_data_vintage_fails_freshness() -> None:
    gate = load_gate_module()
    requested = event_request()
    candidate_payload = event_candidate(data_vintage="2025-02-28")
    rebind_scope_fingerprint(candidate_payload, requested, gate)

    result = gate.evaluate_candidate(requested, candidate_payload)

    assert result.passed is False
    assert result.failures == ("freshness",)


def test_weak_source_class_fails_authority_for_sensitive_event_request() -> None:
    gate = load_gate_module()
    sensitive_request = event_request(
        accepted_source_classes=["issuer-first-party", "named-counterparty"]
    )
    candidate_payload = event_candidate(source_class="media")
    rebind_scope_fingerprint(candidate_payload, sensitive_request, gate)

    result = gate.evaluate_candidate(
        sensitive_request,
        candidate_payload,
    )

    assert result.passed is False
    assert result.failures == ("authority",)


@pytest.mark.parametrize("source_class", ("issuer-first-party", "named-counterparty"))
def test_allowed_governance_event_source_classes_pass_when_other_gates_pass(
    source_class: str,
) -> None:
    gate = load_gate_module()
    requested = event_request(accepted_source_classes=["issuer-first-party", "named-counterparty"])
    candidate_payload = event_candidate(source_class=source_class)
    rebind_scope_fingerprint(candidate_payload, requested, gate)

    result = gate.evaluate_candidate(
        requested,
        candidate_payload,
    )

    assert result.passed is True
    assert result.failures == ()


def test_regulatory_context_allows_official_source_class_when_other_gates_pass() -> None:
    gate = load_gate_module()
    requested = regulatory_request()
    candidate_payload = event_candidate(
        claim_id="management-regulatory-context-2025",
        metric="regulatory context text",
        population="issuer management, directors, controllers, and the governing jurisdiction",
        product_scope="official regulatory context tied to the subject event",
        measurement_basis="official rule text and applicability to the subject event",
        source_class="official-regulator",
        unit="document",
        evidence_id="regulatory-context-2025-03-01",
        published_at="2025-03-03",
        data_vintage="2025-03-03",
    )
    rebind_scope_fingerprint(candidate_payload, requested, gate)

    result = gate.evaluate_candidate(requested, candidate_payload)

    assert result.passed is True
    assert result.failures == ()
    assert result.series_form == "event-set"


def test_stronger_event_candidate_conflict_is_reported_as_conflict() -> None:
    gate = load_gate_module()
    requested = event_request(accepted_source_classes=["issuer-first-party", "named-counterparty"])
    requested["minimum_source_authority"] = "Medium"
    weaker = event_candidate(
        source_class="named-counterparty",
        event_key="2025-03-01|board|withdraw-acquisition-proposal",
        evidence_id="counterparty-notice-2025-03-01",
    )
    runtime_evidence(weaker)["source_authority"] = "Medium"
    rebind_scope_fingerprint(weaker, requested, gate)

    stronger = event_candidate(
        source_class="issuer-first-party",
        event_key="2025-03-01|board|withdraw-acquisition-proposal",
        evidence_id="issuer-announcement-2025-03-01",
    )
    runtime_evidence(stronger)["source_authority"] = "High"
    stronger["artifact"] = {
        "identity": "sha256:8888888888888888888888888888888888888888888888888888888888888888",
        "sha256": "8888888888888888888888888888888888888888888888888888888888888888",
    }
    values(stronger)[0]["value"] = (
        "Issuer stated the board approved the acquisition proposal on 2025-03-01."
    )
    canonical = values(stronger)[0]["canonical_value"]
    assert isinstance(canonical, dict)
    canonical["value"] = "Issuer stated the board approved the acquisition proposal on 2025-03-01."
    rebind_identity(stronger)
    rebind_scope_fingerprint(stronger, requested, gate)

    result = gate.evaluate_candidate(requested, weaker, (stronger,))

    assert result.passed is False
    assert result.failures == ("conflict",)
    assert result.series_form is None


def test_same_date_different_event_key_does_not_conflict() -> None:
    gate = load_gate_module()
    requested = event_request(accepted_source_classes=["issuer-first-party", "named-counterparty"])
    requested["minimum_source_authority"] = "Medium"
    candidate_payload = event_candidate(
        source_class="named-counterparty",
        event_key="2025-03-01|board|withdraw-acquisition-proposal",
        evidence_id="counterparty-notice-2025-03-01",
    )
    runtime_evidence(candidate_payload)["source_authority"] = "Medium"
    rebind_scope_fingerprint(candidate_payload, requested, gate)

    stronger = event_candidate(
        source_class="issuer-first-party",
        event_key="2025-03-01|audit-committee|launch-independent-review",
        evidence_id="issuer-announcement-2025-03-01",
    )
    runtime_evidence(stronger)["source_authority"] = "High"
    values(stronger)[0]["value"] = (
        "Issuer stated the audit committee launched an independent review on 2025-03-01."
    )
    canonical = values(stronger)[0]["canonical_value"]
    assert isinstance(canonical, dict)
    canonical["value"] = (
        "Issuer stated the audit committee launched an independent review on 2025-03-01."
    )
    stronger["artifact"] = {
        "identity": "sha256:9999999999999999999999999999999999999999999999999999999999999999",
        "sha256": "9999999999999999999999999999999999999999999999999999999999999999",
    }
    rebind_identity(stronger)
    rebind_scope_fingerprint(stronger, requested, gate)

    result = gate.evaluate_candidate(requested, candidate_payload, (stronger,))

    assert result.passed is True
    assert result.failures == ()


def test_event_driven_candidates_cannot_be_stitched() -> None:
    gate = load_gate_module()
    requested = event_request()
    first = event_candidate(
        source_class="named-counterparty",
        evidence_id="event-1",
    )
    second = event_candidate(
        source_class="official-regulator",
        evidence_id="event-2",
        period="2025-04-10",
        published_at="2025-04-11",
        data_vintage="2025-04-11",
    )
    rebind_scope_fingerprint(first, requested, gate)
    rebind_scope_fingerprint(second, requested, gate)

    result = gate.evaluate_stitched_series(
        requested,
        (first, second),
    )

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_missing_intermediate_year_fails_continuity() -> None:
    gate = load_gate_module()
    incomplete = candidate("fitting_official")
    incomplete["values"] = [value for value in values(incomplete) if value["period"] != "2022"]

    result = gate.evaluate_candidate(request(), incomplete)

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_broader_ip_toy_scope_cannot_fill_pop_toy_gap() -> None:
    gate = load_gate_module()
    broader = candidate("fitting_official")
    scope(broader)["industries"] = ["ip-toys"]
    scope(broader)["product_scope"] = "ip toys"
    broader["scope_fingerprint"] = BROADER_SCOPE_FINGERPRINT
    for value in values(broader):
        value["definition_scope_fingerprint"] = BROADER_SCOPE_FINGERPRINT
        canonical = value["canonical_value"]
        assert isinstance(canonical, dict)
        canonical["definition_scope_fingerprint"] = BROADER_SCOPE_FINGERPRINT

    result = gate.evaluate_candidate(request(), broader)

    assert result.passed is False
    assert result.failures == ("scope",)


def test_extra_population_scope_cannot_pass_an_exact_request() -> None:
    gate = load_gate_module()
    exact_request = request()
    exact_request.update(
        {
            "population": "retail consumers",
            "product_scope": "pop toys only",
            "measurement_basis": "retail value",
        }
    )
    broader_population = candidate("fitting_official")
    scope(broader_population)["population"] = "retail consumers and collectors"
    broader_population["scope_fingerprint"] = EXTRA_POPULATION_SCOPE_FINGERPRINT
    for value in values(broader_population):
        value["definition_scope_fingerprint"] = EXTRA_POPULATION_SCOPE_FINGERPRINT
        canonical = value["canonical_value"]
        assert isinstance(canonical, dict)
        canonical["definition_scope_fingerprint"] = EXTRA_POPULATION_SCOPE_FINGERPRINT

    result = gate.evaluate_candidate(exact_request, broader_population)

    assert result.passed is False
    assert result.failures == ("scope",)


def test_new_publication_repeating_old_forecast_fails_freshness() -> None:
    gate = load_gate_module()
    stale_forecast = candidate("fitting_official")
    document = stale_forecast["document"]
    assert isinstance(document, dict)
    document["published_at"] = "2026-07-31"
    stale_forecast["data_vintage"] = "2024-12-31"
    rebind_identity(stale_forecast)

    result = gate.evaluate_candidate(request(), stale_forecast)

    assert result.passed is False
    assert result.failures == ("freshness",)


@pytest.mark.parametrize(
    ("field", "future_date"),
    (
        ("published_at", "2026-08-03"),
        ("data_vintage", "2026-08-03"),
    ),
)
def test_non_event_candidate_cannot_use_evidence_after_request_as_of(
    field: str,
    future_date: str,
) -> None:
    gate = load_gate_module()
    future_evidence = candidate("fitting_official")
    if field == "published_at":
        document = future_evidence["document"]
        assert isinstance(document, dict)
        document[field] = future_date
        rebind_identity(future_evidence)
    else:
        future_evidence[field] = future_date

    result = gate.evaluate_candidate(request(), future_evidence)

    assert result.passed is False
    assert result.failures == ("freshness",)


def test_forecast_cannot_be_presented_as_observed() -> None:
    gate = load_gate_module()
    mislabeled_forecast = candidate("fitting_official")
    mislabeled_forecast["data_vintage"] = "2024-12-31"
    values(mislabeled_forecast)[-1]["status"] = "observed"

    result = gate.evaluate_candidate(request(), mislabeled_forecast)

    assert result.passed is False
    assert result.failures == ("value_status", "freshness")


def test_same_frost_lineage_does_not_count_as_independent() -> None:
    gate = load_gate_module()
    independent_request = request()
    independent_request["independent_cross_check_required"] = True
    frost = candidate("fitting_official")
    rebind_lineage(frost, "frost-sullivan-cn-pop-toys-2025")
    kpmg_citing_frost = deepcopy(frost)
    kpmg_citing_frost["document"] = {
        "document_id": "KPMG-POP-TOY-2025",
        "title": "China Pop-Toy Market Outlook",
        "published_at": "2026-02-01",
        "canonical_url": "https://kpmg.example.org/pop-toys/2025",
    }
    kpmg_citing_frost["artifact"] = {
        "identity": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
        "sha256": "4444444444444444444444444444444444444444444444444444444444444444",
    }
    rebind_identity(kpmg_citing_frost)

    result = gate.evaluate_candidate(independent_request, kpmg_citing_frost, (frost,))

    assert result.passed is False
    assert result.failures == ("lineage",)


@pytest.mark.parametrize(
    ("rating_field", "expected_failure"),
    (
        ("source_authority", "authority"),
        ("conclusion_evidence", "conclusion_evidence"),
        ("originality", "originality"),
        ("independence", "independence"),
    ),
)
def test_evidence_dimensions_have_distinct_failure_codes(
    rating_field: str,
    expected_failure: str,
) -> None:
    gate = load_gate_module()
    weak_dimension = candidate("fitting_official")
    runtime_evidence(weak_dimension)[rating_field] = "Low"

    result = gate.evaluate_candidate(request(), weak_dimension)

    assert result.passed is False
    assert result.failures == (expected_failure,)


@pytest.mark.parametrize(
    "cross_check_mutation",
    ("different-claim", "different-scope", "insufficient-originality"),
)
def test_independent_cross_check_must_fit_the_same_claim_and_gate(
    cross_check_mutation: str,
) -> None:
    gate = load_gate_module()
    independent_request = request()
    independent_request["independent_cross_check_required"] = True
    primary = candidate("fitting_official")
    cross_check = candidate("fitting_official")
    cross_check["artifact"] = {
        "identity": "sha256:abababababababababababababababababababababababababababababababab",
        "sha256": "abababababababababababababababababababababababababababababababab",
    }
    cross_check["source"]["immediate_publisher"] = "Independent Research Institute"
    cross_check["source"]["original_publisher"] = "Independent Research Institute"
    cross_check["document"]["document_id"] = "IRI-CN-POP-TOY-2025"
    cross_check["document"]["title"] = "Independent China Pop-Toy Market"
    cross_check["document"]["canonical_url"] = "https://iri.example/pop-toys/2025"
    cross_check["source"]["canonical_url"] = "https://iri.example/pop-toys/2025"
    rebind_identity(cross_check)
    rebind_lineage(cross_check, "independent-pop-toys-2025")

    if cross_check_mutation == "different-claim":
        cross_check["claim_id"] = "different-claim"
    elif cross_check_mutation == "different-scope":
        scope(cross_check)["product_scope"] = "all collectible toys"
        cross_check["scope_fingerprint"] = BROADER_SCOPE_FINGERPRINT
        for value in values(cross_check):
            value["definition_scope_fingerprint"] = BROADER_SCOPE_FINGERPRINT
            canonical = value["canonical_value"]
            assert isinstance(canonical, dict)
            canonical["definition_scope_fingerprint"] = BROADER_SCOPE_FINGERPRINT
    else:
        runtime_evidence(cross_check)["originality"] = "Low"

    result = gate.evaluate_candidate(
        independent_request,
        primary,
        accepted_candidates=(cross_check,),
    )

    assert result.passed is False
    assert result.failures == ("lineage",)


def test_same_artifact_and_document_cannot_be_an_independent_cross_check() -> None:
    gate = load_gate_module()
    independent_request = request()
    independent_request["independent_cross_check_required"] = True
    primary = candidate("fitting_official")
    forged_cross_check = deepcopy(primary)
    forged_cross_check["source"]["original_publisher"] = "Relabeled Publisher"
    rebind_lineage(forged_cross_check, "relabeled-independent-report")

    result = gate.evaluate_candidate(
        independent_request,
        primary,
        accepted_candidates=(forged_cross_check,),
    )

    assert result.passed is False
    assert result.failures == ("lineage",)


def test_matching_overlap_allows_labeled_stitch() -> None:
    gate = load_gate_module()
    early = candidate("stitch_early")
    late = candidate("stitch_late")

    result = gate.evaluate_stitched_series(request(), (early, late))

    assert result.passed is True
    assert result.failures == ()
    assert result.scope_fingerprint == FITTING_SCOPE_FINGERPRINT
    assert result.series_form == "stitched"
    assert {value.source_identity for value in result.series_values} == {
        early["artifact"]["identity"],
        late["artifact"]["identity"],
    }
    assert {value.status for value in result.series_values} == {"observed", "forecast"}


def test_stitch_cannot_claim_independence_from_the_same_artifact_and_document() -> None:
    gate = load_gate_module()
    independent_request = request()
    independent_request["independent_cross_check_required"] = True
    early = candidate("stitch_early")
    late = candidate("stitch_late")
    late["artifact"] = deepcopy(early["artifact"])
    late["document"] = deepcopy(early["document"])
    late["source"]["canonical_url"] = early["source"]["canonical_url"]
    rebind_identity(late)
    rebind_lineage(late, "relabeled-independent-stitch")

    result = gate.evaluate_stitched_series(independent_request, (early, late))

    assert result.passed is False
    assert result.failures == ("lineage",)


def test_mismatched_overlap_rejects_stitch() -> None:
    gate = load_gate_module()
    late = candidate("stitch_late")
    values(late)[0]["value"] = 29.0
    canonical = values(late)[0]["canonical_value"]
    assert isinstance(canonical, dict)
    canonical["value"] = 29.0

    result = gate.evaluate_stitched_series(request(), (candidate("stitch_early"), late))

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_disjoint_fragments_cannot_form_a_stitched_series() -> None:
    gate = load_gate_module()
    late = candidate("stitch_late")
    late["values"] = [value for value in values(late) if value["period"] != "2022"]

    result = gate.evaluate_stitched_series(request(), (candidate("stitch_early"), late))

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_stronger_source_conflict_blocks_acceptance() -> None:
    gate = load_gate_module()
    medium_request = request()
    medium_request["minimum_source_authority"] = "Medium"
    weaker_candidate = candidate("fitting_official")
    runtime_evidence(weaker_candidate)["source_authority"] = "Medium"
    rebind_lineage(weaker_candidate, "consultant-pop-toys-2025")
    stronger_candidate = candidate("fitting_official")
    rebind_lineage(stronger_candidate, "official-pop-toys-2025")
    stronger_candidate["artifact"] = {
        "identity": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
        "sha256": "5555555555555555555555555555555555555555555555555555555555555555",
    }
    values(stronger_candidate)[-2]["value"] = 35.0
    canonical = values(stronger_candidate)[-2]["canonical_value"]
    assert isinstance(canonical, dict)
    canonical["value"] = 35.0
    rebind_identity(stronger_candidate)

    result = gate.evaluate_candidate(medium_request, weaker_candidate, (stronger_candidate,))

    assert result.passed is False
    assert result.failures == ("conflict",)


def test_incomparable_conflicting_evidence_remains_a_conflict() -> None:
    gate = load_gate_module()
    permissive_request = request()
    for field in (
        "minimum_source_authority",
        "minimum_conclusion_evidence",
        "minimum_originality",
        "minimum_independence",
    ):
        permissive_request[field] = "Low"

    candidate_payload = candidate("fitting_official")
    runtime_evidence(candidate_payload)["source_authority"] = "High"
    runtime_evidence(candidate_payload)["conclusion_evidence"] = "Low"

    incomparable = candidate("fitting_official")
    runtime_evidence(incomparable)["source_authority"] = "Low"
    runtime_evidence(incomparable)["conclusion_evidence"] = "High"
    incomparable["artifact"] = {
        "identity": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
        "sha256": "cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
    }
    values(incomparable)[-2]["value"] = 35.0
    canonical = values(incomparable)[-2]["canonical_value"]
    assert isinstance(canonical, dict)
    canonical["value"] = 35.0
    rebind_identity(incomparable)

    result = gate.evaluate_candidate(
        permissive_request,
        candidate_payload,
        accepted_candidates=(incomparable,),
    )

    assert result.passed is False
    assert result.failures == ("conflict",)


def test_component_wise_dominant_candidate_supersedes_weaker_conflict() -> None:
    gate = load_gate_module()
    permissive_request = request()
    for field in (
        "minimum_source_authority",
        "minimum_conclusion_evidence",
        "minimum_originality",
        "minimum_independence",
    ):
        permissive_request[field] = "Low"

    dominant = candidate("fitting_official")
    weaker = candidate("fitting_official")
    for field in (
        "source_authority",
        "conclusion_evidence",
        "originality",
        "independence",
    ):
        runtime_evidence(weaker)[field] = "Low"
    weaker["artifact"] = {
        "identity": "sha256:efefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefef",
        "sha256": "efefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefef",
    }
    values(weaker)[-2]["value"] = 35.0
    canonical = values(weaker)[-2]["canonical_value"]
    assert isinstance(canonical, dict)
    canonical["value"] = 35.0
    rebind_identity(weaker)

    result = gate.evaluate_candidate(
        permissive_request,
        dominant,
        accepted_candidates=(weaker,),
    )

    assert result.passed is True
    assert result.failures == ()


def test_missing_intermediate_quarter_fails_continuity() -> None:
    gate = load_gate_module()
    quarterly = candidate("fitting_official")
    set_series(
        quarterly,
        frequency="quarterly",
        period_semantics="calendar-quarter",
        periods=["2024-Q1", "2024-Q3", "2024-Q4"],
        vintage="2024-12-31",
    )

    result = gate.evaluate_candidate(
        temporal_request("quarterly", "2024-Q1", "2024-Q4"),
        quarterly,
    )

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_missing_intermediate_month_fails_continuity() -> None:
    gate = load_gate_module()
    monthly = candidate("fitting_official")
    set_series(
        monthly,
        frequency="monthly",
        period_semantics="calendar-month",
        periods=["2024-01", "2024-03", "2024-04"],
        vintage="2024-04-30",
    )

    result = gate.evaluate_candidate(
        temporal_request("monthly", "2024-01", "2024-04"),
        monthly,
    )

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_candidate_frequency_mismatch_fails_continuity() -> None:
    gate = load_gate_module()
    annual = candidate("fitting_official")
    set_series(
        annual,
        frequency="annual",
        period_semantics="calendar-year",
        periods=["2024"],
        vintage="2024-12-31",
    )

    result = gate.evaluate_candidate(
        temporal_request("quarterly", "2024-Q1", "2024-Q4"),
        annual,
    )

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_candidate_metric_mismatch_fails_scope() -> None:
    gate = load_gate_module()
    different_metric = candidate("fitting_official")
    different_metric["metric"] = "annual wholesale market size"
    different_metric["scope_fingerprint"] = WHOLESALE_METRIC_SCOPE_FINGERPRINT
    for value in values(different_metric):
        value["definition_scope_fingerprint"] = WHOLESALE_METRIC_SCOPE_FINGERPRINT
        canonical = value["canonical_value"]
        assert isinstance(canonical, dict)
        canonical["definition_scope_fingerprint"] = WHOLESALE_METRIC_SCOPE_FINGERPRINT

    result = gate.evaluate_candidate(request(), different_metric)

    assert result.passed is False
    assert result.failures == ("scope",)


def test_industry_changes_scope_fingerprint() -> None:
    gate = load_gate_module()
    collectible_toys = candidate("fitting_official")
    scope(collectible_toys)["industries"] = ["collectible-toys"]
    collectible_toys["scope_fingerprint"] = COLLECTIBLE_TOY_SCOPE_FINGERPRINT
    for value in values(collectible_toys):
        value["definition_scope_fingerprint"] = COLLECTIBLE_TOY_SCOPE_FINGERPRINT
        canonical = value["canonical_value"]
        assert isinstance(canonical, dict)
        canonical["definition_scope_fingerprint"] = COLLECTIBLE_TOY_SCOPE_FINGERPRINT

    result = gate.evaluate_candidate(request(), collectible_toys)

    assert result.scope_fingerprint == COLLECTIBLE_TOY_SCOPE_FINGERPRINT
    assert result.failures == ("scope",)


def test_forged_identity_binding_fails_identity() -> None:
    gate = load_gate_module()
    forged = candidate("fitting_official")
    identity = forged["source_document_identity"]
    assert isinstance(identity, dict)
    identity["binding_sha256"] = "0" * 64

    result = gate.evaluate_candidate(request(), forged)

    assert result.passed is False
    assert result.failures == ("identity",)


def test_declared_converted_overlap_allows_stitch() -> None:
    gate = load_gate_module()
    late = candidate("stitch_late")
    converted = values(late)[0]
    converted["value"] = 4_000.0
    converted["unit"] = "USD million"
    converted["definition_scope_fingerprint"] = "a" * 64
    converted["canonical_value"] = {
        "value": 28.0,
        "unit": "CNY billion",
        "definition_scope_fingerprint": FITTING_SCOPE_FINGERPRINT,
        "reconciliation_id": "usd-million-to-cny-billion",
    }
    late["reconciliations"] = [
        {
            "reconciliation_id": "usd-million-to-cny-billion",
            "from_unit": "USD million",
            "to_unit": "CNY billion",
            "from_scope_fingerprint": "a" * 64,
            "to_scope_fingerprint": FITTING_SCOPE_FINGERPRINT,
            "method": "published foreign-exchange rate",
            "formula": "USD million * published_fx_rate / 1000",
            "artifact_identity": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
            "artifact_sha256": "6666666666666666666666666666666666666666666666666666666666666666",
        }
    ]

    result = gate.evaluate_stitched_series(request(), (candidate("stitch_early"), late))

    assert result.passed is True
    assert result.series_form == "stitched"
    assert {value.value for value in result.series_values if value.period == "2022"} == {28.0}


def test_mismatched_declared_conversion_rejects_stitch() -> None:
    gate = load_gate_module()
    late = candidate("stitch_late")
    converted = values(late)[0]
    converted["value"] = 4_000.0
    converted["unit"] = "USD million"
    converted["definition_scope_fingerprint"] = "a" * 64
    converted["canonical_value"] = {
        "value": 29.0,
        "unit": "CNY billion",
        "definition_scope_fingerprint": FITTING_SCOPE_FINGERPRINT,
        "reconciliation_id": "usd-million-to-cny-billion",
    }
    late["reconciliations"] = [
        {
            "reconciliation_id": "usd-million-to-cny-billion",
            "from_unit": "USD million",
            "to_unit": "CNY billion",
            "from_scope_fingerprint": "a" * 64,
            "to_scope_fingerprint": FITTING_SCOPE_FINGERPRINT,
            "method": "published foreign-exchange rate",
            "formula": "USD million * published_fx_rate / 1000",
            "artifact_identity": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
            "artifact_sha256": "6666666666666666666666666666666666666666666666666666666666666666",
        }
    ]

    result = gate.evaluate_stitched_series(request(), (candidate("stitch_early"), late))

    assert result.passed is False
    assert result.failures == ("continuity",)


def test_stronger_source_conflict_blocks_stitched_series() -> None:
    gate = load_gate_module()
    medium_request = request()
    medium_request["minimum_source_authority"] = "Medium"
    early = candidate("stitch_early")
    late = candidate("stitch_late")
    runtime_evidence(early)["source_authority"] = "Medium"
    runtime_evidence(late)["source_authority"] = "Medium"
    stronger = candidate("fitting_official")
    values(stronger)[-2]["value"] = 35.0
    canonical = values(stronger)[-2]["canonical_value"]
    assert isinstance(canonical, dict)
    canonical["value"] = 35.0

    result = gate.evaluate_stitched_series(
        medium_request,
        (early, late),
        accepted_candidates=(stronger,),
    )

    assert result.passed is False
    assert result.failures == ("conflict",)


def test_stitched_output_filters_extras_and_retains_artifact_document_identity() -> None:
    gate = load_gate_module()
    early = candidate("stitch_early")
    late = candidate("stitch_late")
    values(late).append(canonical_value("2026", 40.0, status="forecast"))

    result = gate.evaluate_stitched_series(request(), (early, late))

    assert result.passed is True
    assert [value.period for value in result.series_values] == [
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
    ]
    assert len({value.period for value in result.series_values}) == 6
    assert {(value.artifact_sha256, value.document_id) for value in result.series_values} == {
        (early["artifact"]["sha256"], "CCP-POP-TOY-2022"),
        (late["artifact"]["sha256"], "CCP-POP-TOY-2025-REV"),
    }
    assert {
        (
            value.source_canonical_url,
            value.document_canonical_url,
            value.document_id,
            value.artifact_sha256,
            value.binding_sha256,
        )
        for value in result.series_values
    } == {
        (
            payload["source_document_identity"]["source_canonical_url"],
            payload["source_document_identity"]["document_canonical_url"],
            payload["source_document_identity"]["document_id"],
            payload["source_document_identity"]["artifact_sha256"],
            payload["source_document_identity"]["binding_sha256"],
        )
        for payload in (early, late)
    }
