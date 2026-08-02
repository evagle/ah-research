from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_PATH = (
    REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts" / "research_contracts.py"
)
CLAIM_ID = "cn-pop-toy-market-2020-2025"
ARTIFACT_IDENTITY = "sha256:4d13f5048b8c4c1a9d7ee546c7274140123456789abcdef0123456789abcdef0"
SCOPE_FINGERPRINT = "13f5048b8c4c1a9d7ee546c7274140123456789abcdef0123456789abcdef010"
SECOND_ARTIFACT_IDENTITY = "sha256:8d31f5048b8c4c1a9d7ee546c7274140123456789abcdef0123456789abcdef0"
SECOND_SCOPE_FINGERPRINT = "43f5048b8c4c1a9d7ee546c7274140123456789abcdef0123456789abcdef010"
EVENT_CLAIM_ID = "management-governance-event-2025"
EVENT_ARTIFACT_IDENTITY = "sha256:1d31f5048b8c4c1a9d7ee546c7274140123456789abcdef0123456789abcdeff"
EVENT_SCOPE_FINGERPRINT = "73f5048b8c4c1a9d7ee546c7274140123456789abcdef0123456789abcdef010"
EVENT_TEXT = "Counterparty stated the board withdrew the acquisition proposal on 2025-03-01."


def load_contracts_module():
    assert CONTRACTS_PATH.is_file(), f"missing contract validator: {CONTRACTS_PATH}"
    script_dir = str(CONTRACTS_PATH.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("research_contracts", CONTRACTS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def request_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "claim_id": CLAIM_ID,
        "claim_type": "market-size",
        "subject": "China pop-toy market",
        "metric": "annual retail market size",
        "geographies": ["China"],
        "industries": ["pop-toys"],
        "population": "retail consumers",
        "product_scope": "pop toys only",
        "measurement_basis": "retail value",
        "period_start": "2020",
        "period_end": "2025",
        "frequency": "annual",
        "continuity_required": True,
        "required_latest_period": "2025",
        "accepted_units": ["CNY billion"],
        "definition_constraints": ["pop toys only", "retail value"],
        "value_status_allowed": ["observed", "historical-estimate", "forecast"],
        "minimum_source_authority": "High",
        "minimum_conclusion_evidence": "High",
        "minimum_originality": "High",
        "minimum_independence": "Medium",
        "independent_cross_check_required": True,
        "absence_claim": False,
        "as_of": "2026-08-02",
    }


def event_request_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "claim_id": EVENT_CLAIM_ID,
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
        "accepted_source_classes": ["issuer-first-party", "named-counterparty", "auditor"],
        "absence_claim": False,
        "as_of": "2025-12-31",
    }


def regulatory_request_payload() -> dict[str, object]:
    payload = event_request_payload()
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
            "accepted_source_classes": [
                "official-regulator",
                "official-exchange",
                "official-court",
            ],
        }
    )
    return payload


def candidate_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "claim_id": CLAIM_ID,
        "metric": "annual retail market size",
        "frequency": "annual",
        "period_semantics": "calendar-year",
        "source": {
            "immediate_publisher": "Newly Discovered Research Institute",
            "original_publisher": "Newly Discovered Research Institute",
            "publisher_type": "original-research",
            "canonical_url": "https://example.org/reports/china-pop-toys-2025",
        },
        "document": {
            "document_id": "NDRI-CN-POP-2025",
            "title": "China Pop-Toy Market 2020-2025",
            "published_at": "2026-07-15",
            "canonical_url": "https://example.org/reports/china-pop-toys-2025",
        },
        "values": [
            {
                "period": "2025",
                "value": 34.2,
                "unit": "CNY billion",
                "status": "forecast",
                "definition_scope_fingerprint": SCOPE_FINGERPRINT,
                "canonical_value": {
                    "value": 34.2,
                    "unit": "CNY billion",
                    "definition_scope_fingerprint": SCOPE_FINGERPRINT,
                    "reconciliation_id": None,
                },
            }
        ],
        "canonical_unit": "CNY billion",
        "scope": {
            "geographies": ["China"],
            "industries": ["pop-toys"],
            "product_scope": "pop toys only",
            "population": "retail consumers",
            "measurement_basis": "retail value",
        },
        "data_vintage": "2025-12-31",
        "artifact": {
            "identity": ARTIFACT_IDENTITY,
            "sha256": ARTIFACT_IDENTITY.removeprefix("sha256:"),
        },
        "scope_fingerprint": SCOPE_FINGERPRINT,
        "reconciliations": [],
        "lineage_id": "ndri-china-pop-toys-2025",
        "runtime_evidence": {
            "source_authority": "High",
            "conclusion_evidence": "High",
            "originality": "High",
            "independence": "High",
            "evidence_level": "High",
        },
    }
    bind_candidate_identity(payload)
    bind_candidate_lineage(payload, "NDRI-CN-POP-2025")
    return payload


def event_candidate_payload(
    *,
    source_class: str = "named-counterparty",
    period: str = "2025-03-01",
    event_key: str = "2025-03-01|board|withdraw-acquisition-proposal",
    evidence_id: str = "event-2025-03-01-counterparty",
    unit: str = "event",
    published_at: str = "2025-03-02",
    data_vintage: str = "2025-03-02",
) -> dict[str, object]:
    publisher_type = {
        "official-regulator": "official-regulator",
        "official-exchange": "official-exchange",
        "official-court": "official-court",
        "issuer-first-party": "issuer-statement",
        "named-counterparty": "counterparty-statement",
        "auditor": "auditor-report",
    }.get(source_class, "counterparty-statement")
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "claim_id": EVENT_CLAIM_ID,
        "metric": "governance event text",
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
            "product_scope": "management governance events outside bound manifests",
            "population": "issuer directors, executives, and named counterparties",
            "measurement_basis": "dated attributable event text",
        },
        "data_vintage": data_vintage,
        "artifact": {
            "identity": EVENT_ARTIFACT_IDENTITY,
            "sha256": EVENT_ARTIFACT_IDENTITY.removeprefix("sha256:"),
        },
        "scope_fingerprint": EVENT_SCOPE_FINGERPRINT,
        "reconciliations": [],
        "lineage_id": "named-counterparty-governance-2025-03-02",
        "runtime_evidence": {
            "source_authority": "High",
            "conclusion_evidence": "High",
            "originality": "High",
            "independence": "High",
            "evidence_level": "High",
        },
    }
    bind_candidate_identity(payload)
    bind_candidate_lineage(payload, "NAMED-COUNTERPARTY-GOVERNANCE-2025-03-02")
    return payload


def bind_candidate_identity(payload: dict[str, object]) -> None:
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


def bind_candidate_lineage(
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


def attempt_payload(
    route_id: str = "layer-1-ndri-market-size",
    terminal_reason: str = "not-found",
) -> dict[str, object]:
    return {
        "route_id": route_id,
        "route_layer": 1,
        "subject_relation": "direct",
        "document_type": "industry-report",
        "query_variant": '"China" "pop toy" market size 2020 2025',
        "started_at": "2026-08-02T01:00:00+00:00",
        "completed_at": "2026-08-02T01:01:00+00:00",
        "artifact_identity": ARTIFACT_IDENTITY,
        "lineage_id": "ndri-china-pop-toys-2025",
        "terminal_reason": terminal_reason,
        "acceptance_failures": [],
    }


def unattempted_route_payload() -> dict[str, object]:
    return {
        "route_id": "layer-2-official-statistics-fallback",
        "route_layer": 2,
        "reason": "request budget exhausted before fallback",
    }


def ledger_payload(
    status: str = "accepted",
    absence_claim: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "claim_id": CLAIM_ID,
        "request_scope_fingerprint": SCOPE_FINGERPRINT,
        "absence_claim": absence_claim,
        "status": status,
        "applicable_routes": [applicable_route_payload()],
        "attempts": [attempt_payload(terminal_reason="accepted")],
        "acceptance_failures": [],
        "accepted_evidence": {
            "candidate_document_id": "NDRI-CN-POP-2025",
            "artifact_identity": ARTIFACT_IDENTITY,
            "lineage_id": "ndri-china-pop-toys-2025",
        },
        "conflict_evidence": None,
        "gate": {"outcome": "passed", "failures": []},
        "next_escalation": None,
        "skipped_after_acceptance": [],
        "unattempted_routes": [],
    }


def route_cache_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "recipes": [
            {
                "claim_type": "market-size",
                "geographies": ["China"],
                "industries": ["pop-toys"],
                "subject_relation": "direct",
                "document_type": "industry-report",
                "source_function": "research-reports",
                "query_pattern": '"{geography}" "{industry}" market size',
                "index_endpoint": "https://example.org/reports",
                "identity_rule": "document ID plus SHA-256",
                "extraction_hint": "Market size table",
                "reviewed_at": "2026-08-02T01:00:00+00:00",
            }
        ],
    }


def industry_bundle_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "subject": "Pop Mart",
        "as_of": "2026-08-02",
        "primary_market_scope_fingerprint": "a" * 64,
        "status": "publishable-with-gaps",
        "roles": [
            {
                "role": role,
                "claim_ids": [f"pop-mart-{role}"],
                "state": "partial" if role == "subject-market-share" else "accepted",
                "required_periods": (
                    ["2021", "2022", "2023", "2024", "2025"]
                    if role
                    in {
                        "historical-market-size",
                        "subject-market-share",
                        "competitor-market-share",
                    }
                    else []
                ),
                "accepted_periods": (
                    ["2021", "2022", "2024", "2025"]
                    if role == "subject-market-share"
                    else (
                        ["2021", "2022", "2023", "2024", "2025"]
                        if role
                        in {
                            "historical-market-size",
                            "competitor-market-share",
                        }
                        else []
                    )
                ),
                "missing_periods": ["2023"] if role == "subject-market-share" else [],
                "scope_fingerprints": ["a" * 64],
                "lineage_ids": [f"lineage-{role}"],
                "ledger_paths": [f"research/{role}.json"],
                "gap_reason": (
                    "No comparable 2023 public company-share table"
                    if role == "subject-market-share"
                    else None
                ),
                "not_applicable_reason": None,
            }
            for role in (
                "market-definition",
                "historical-market-size",
                "industry-forecast",
                "market-concentration",
                "subject-market-share",
                "competitor-market-share",
                "current-partial-period",
                "industry-drivers",
            )
        ],
        "scope_breaks": [],
        "unresolved_claim_ids": ["pop-mart-subject-market-share"],
    }


def applicable_route_payload(
    route_id: str = "layer-1-ndri-market-size",
    route_layer: int = 1,
) -> dict[str, object]:
    return {
        "route_id": route_id,
        "route_layer": route_layer,
        "subject_relation": "direct",
        "document_type": "industry-report",
    }


def planner_inventory_receipt(
    routes: list[dict[str, object]] | tuple[dict[str, object], ...],
    *,
    claim_id: str = CLAIM_ID,
    scope_fingerprint: str = SCOPE_FINGERPRINT,
) -> dict[str, object]:
    request = request_payload()
    request["claim_id"] = claim_id
    planner_inputs = {
        "request_identity": {
            "claim_id": claim_id,
            "request_scope_fingerprint": scope_fingerprint,
            "request_content_sha256": canonical_sha256(request),
        },
        "source_function": "market-size",
        "maintained_profiles": [
            {
                "source_id": "ndri",
                "content_sha256": canonical_sha256({"id": "ndri", "fixture_version": "1"}),
            }
        ],
        "relation_records": [],
        "bound_routes": [],
        "as_of": "2026-08-02",
        "effective_planning_time": "2026-08-02T00:00:00+00:00",
        "vocabulary_identity": {
            "content_sha256": canonical_sha256({"market-size": ["market size"]})
        },
        "reachability_identity": {"content_sha256": canonical_sha256({})},
        "route_inventory_sha256": canonical_sha256(list(routes)),
    }
    content = {
        "schema_version": "1.0",
        "claim_id": claim_id,
        "request_scope_fingerprint": scope_fingerprint,
        "planner_inputs": planner_inputs,
        "planner_input_fingerprint": canonical_sha256(planner_inputs),
        "route_inventory": list(routes),
    }
    return {
        **content,
        "content_sha256": canonical_sha256(content),
    }


def canonical_sha256(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def rehash_receipt_content(receipt: dict[str, object]) -> None:
    content = {key: value for key, value in receipt.items() if key != "content_sha256"}
    receipt["content_sha256"] = canonical_sha256(content)


def validate_ledger(
    contracts,
    ledger: dict[str, object],
    *,
    receipt_routes: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
) -> None:
    contracts.validate_payload(
        "research-ledger",
        ledger,
        planner_inventory_receipt=planner_inventory_receipt(
            receipt_routes if receipt_routes is not None else ledger["applicable_routes"],
            claim_id=ledger["claim_id"],
            scope_fingerprint=ledger["request_scope_fingerprint"],
        ),
    )


def exhausted_absence_ledger() -> dict[str, object]:
    exhausted = ledger_payload(status="exhausted", absence_claim=True)
    exhausted["attempts"] = [attempt_payload(terminal_reason="not-found")]
    exhausted["accepted_evidence"] = None
    exhausted["gate"] = {"outcome": "failed", "failures": ["no fitting evidence found"]}
    return exhausted


def blocked_ledger() -> dict[str, object]:
    blocked = ledger_payload(status="blocked")
    blocked["applicable_routes"] = [
        applicable_route_payload(),
        applicable_route_payload(
            route_id="layer-2-official-statistics-fallback",
            route_layer=2,
        ),
    ]
    blocked["attempts"] = [attempt_payload(terminal_reason="access-unavailable")]
    blocked["accepted_evidence"] = None
    blocked["gate"] = {"outcome": "unresolved", "failures": ["credentials unavailable"]}
    blocked["next_escalation"] = {
        "next_layer": 2,
        "route_ids": ["layer-2-official-statistics-fallback"],
    }
    blocked["unattempted_routes"] = [unattempted_route_payload()]
    return blocked


def conflict_ledger() -> dict[str, object]:
    conflict = ledger_payload(status="conflict")
    conflict["applicable_routes"] = [
        applicable_route_payload(),
        applicable_route_payload(
            route_id="layer-2-official-statistics-fallback",
            route_layer=2,
        ),
        applicable_route_payload(
            route_id="layer-3-peer-prospectus",
            route_layer=3,
        ),
    ]
    conflict["attempts"] = [
        attempt_payload(route_id="layer-1-ndri-market-size", terminal_reason="conflict"),
        {
            **attempt_payload(
                route_id="layer-2-official-statistics-fallback",
                terminal_reason="conflict",
            ),
            "route_layer": 2,
            "artifact_identity": SECOND_ARTIFACT_IDENTITY,
            "lineage_id": "official-statistics-2025",
        },
    ]
    conflict["acceptance_failures"] = ["stronger source contradicts the value"]
    conflict["accepted_evidence"] = None
    conflict["gate"] = {"outcome": "unresolved", "failures": ["source conflict"]}
    conflict["next_escalation"] = {
        "next_layer": 3,
        "route_ids": ["layer-3-peer-prospectus"],
    }
    return conflict


def conflict_evidence_side(
    artifact_identity: str,
    lineage_id: str,
    definition_scope_fingerprint: str,
    value: float | str,
    *,
    event_key: str | None = None,
    evidence_id: str | None = None,
) -> dict[str, object]:
    side = {
        "definition_scope_fingerprint": definition_scope_fingerprint,
        "unit": "event" if isinstance(value, str) else "CNY billion",
        "value": value,
        "value_status": "observed" if isinstance(value, str) else "forecast",
        "artifact_identity": artifact_identity,
        "lineage_id": lineage_id,
    }
    if event_key is not None:
        side["event_key"] = event_key
    if evidence_id is not None:
        side["evidence_id"] = evidence_id
    return side


def test_request_requires_explicit_acceptance_requirements() -> None:
    contracts = load_contracts_module()
    contracts.validate_payload("research-request", request_payload())

    missing_requirement = request_payload()
    del missing_requirement["minimum_independence"]
    with pytest.raises(ValueError, match="minimum_independence"):
        contracts.validate_payload("research-request", missing_requirement)

    unknown_requirement = request_payload()
    unknown_requirement["minimum_route_count"] = 3
    with pytest.raises(ValueError, match="minimum_route_count"):
        contracts.validate_payload("research-request", unknown_requirement)


def test_industry_analysis_bundle_schema_is_registered() -> None:
    contracts = load_contracts_module()

    canonical = contracts.load_schema("industry-analysis-bundle")
    alias = contracts.load_schema("industry-bundle")

    assert canonical["title"] == "Industry Analysis Bundle"
    assert alias == canonical


def test_industry_bundle_schema_rejects_unknown_role_state() -> None:
    contracts = load_contracts_module()
    payload = industry_bundle_payload()
    payload["roles"][0]["state"] = "done"

    with pytest.raises(ValueError, match="industry-analysis-bundle violates schema"):
        contracts.validate_payload("industry-bundle", payload)


def test_request_optionally_accepts_strict_source_classes() -> None:
    contracts = load_contracts_module()
    contracts.validate_payload("research-request", request_payload())
    contracts.validate_payload("research-request", event_request_payload())
    contracts.validate_payload("research-request", regulatory_request_payload())

    unknown_source_class = event_request_payload()
    unknown_source_class["accepted_source_classes"] = ["official-regulator", "mystery-source"]
    with pytest.raises(ValueError, match="accepted_source_classes"):
        contracts.validate_payload("research-request", unknown_source_class)

    for forbidden_source_class in (
        "official-regulator",
        "official-exchange",
        "official-court",
    ):
        governance_request = event_request_payload()
        governance_request["accepted_source_classes"] = [
            "named-counterparty",
            forbidden_source_class,
        ]
        with pytest.raises(ValueError, match="governance-event"):
            contracts.validate_payload("research-request", governance_request)


@pytest.mark.parametrize(
    "scope_dimension",
    ("population", "product_scope", "measurement_basis"),
)
def test_request_requires_explicit_scope_dimensions(scope_dimension: str) -> None:
    contracts = load_contracts_module()
    incomplete_scope = request_payload()
    del incomplete_scope[scope_dimension]

    with pytest.raises(ValueError, match=scope_dimension):
        contracts.validate_payload("research-request", incomplete_scope)


def test_candidate_requires_scope_value_status_and_lineage() -> None:
    contracts = load_contracts_module()
    contracts.validate_payload("candidate-claim", candidate_payload())

    missing_status = candidate_payload()
    del missing_status["values"][0]["status"]
    with pytest.raises(ValueError, match=r"values\.0.*status"):
        contracts.validate_payload("candidate-claim", missing_status)

    missing_scope = candidate_payload()
    del missing_scope["scope"]["measurement_basis"]
    with pytest.raises(ValueError, match="measurement_basis"):
        contracts.validate_payload("candidate-claim", missing_scope)

    missing_lineage = candidate_payload()
    del missing_lineage["lineage_id"]
    with pytest.raises(ValueError, match="lineage_id"):
        contracts.validate_payload("candidate-claim", missing_lineage)

    missing_frequency = candidate_payload()
    del missing_frequency["frequency"]
    with pytest.raises(ValueError, match="frequency"):
        contracts.validate_payload("candidate-claim", missing_frequency)

    invalid_period_semantics = candidate_payload()
    invalid_period_semantics["period_semantics"] = "calendar-month"
    with pytest.raises(ValueError, match="period semantics"):
        contracts.validate_payload("candidate-claim", invalid_period_semantics)


def test_candidate_lineage_id_is_bound_to_normalized_provenance() -> None:
    contracts = load_contracts_module()
    candidate = candidate_payload()
    bind_candidate_lineage(candidate, "NDRI-CN-POP-2025")

    contracts.validate_payload("candidate-claim", candidate)

    forged = deepcopy(candidate)
    forged["lineage_id"] = "underlying:" + "0" * 64
    with pytest.raises(ValueError, match="lineage_id does not match"):
        contracts.validate_payload("candidate-claim", forged)


def test_candidate_lineage_provenance_schema_remains_strict() -> None:
    contracts = load_contracts_module()
    candidate = candidate_payload()
    bind_candidate_lineage(candidate, "NDRI-CN-POP-2025")
    candidate["lineage"]["unreviewed_label"] = "caller-declared"

    with pytest.raises(ValueError, match="unreviewed_label"):
        contracts.validate_payload("candidate-claim", candidate)


def test_event_candidate_supports_event_dates_text_values_and_source_classes() -> None:
    contracts = load_contracts_module()
    contracts.validate_payload("research-request", event_request_payload())
    event_candidate = event_candidate_payload(source_class="official-regulator")
    contracts.validate_payload("candidate-claim", event_candidate)
    assert event_candidate["values"][0]["value"] == EVENT_TEXT
    assert event_candidate["values"][0]["event_key"] == (
        "2025-03-01|board|withdraw-acquisition-proposal"
    )
    canonical = event_candidate["values"][0]["canonical_value"]
    assert isinstance(canonical, dict)
    assert canonical["value"] == EVENT_TEXT

    missing_source_class = event_candidate_payload()
    source = missing_source_class["source"]
    assert isinstance(source, dict)
    del source["source_class"]
    with pytest.raises(ValueError, match="source_class"):
        contracts.validate_payload("candidate-claim", missing_source_class)

    missing_evidence_id = event_candidate_payload()
    del missing_evidence_id["values"][0]["evidence_id"]
    with pytest.raises(ValueError, match="evidence_id"):
        contracts.validate_payload("candidate-claim", missing_evidence_id)


def test_event_candidate_requires_nonempty_unique_event_key() -> None:
    contracts = load_contracts_module()

    missing_event_key = event_candidate_payload()
    del missing_event_key["values"][0]["event_key"]
    with pytest.raises(ValueError, match="event_key"):
        contracts.validate_payload("candidate-claim", missing_event_key)

    empty_event_key = event_candidate_payload()
    empty_event_key["values"][0]["event_key"] = ""
    with pytest.raises(ValueError, match="event_key"):
        contracts.validate_payload("candidate-claim", empty_event_key)

    duplicate_event_key = event_candidate_payload()
    duplicate_event_key["values"].append(
        {
            **duplicate_event_key["values"][0],
            "period": "2025-03-02",
            "evidence_id": "event-2025-03-02-counterparty",
        }
    )
    with pytest.raises(ValueError, match="event_key"):
        contracts.validate_payload("candidate-claim", duplicate_event_key)

    invalid_event_period = event_candidate_payload(period="2025-Q1")
    with pytest.raises(ValueError, match="frequency semantics"):
        contracts.validate_payload("candidate-claim", invalid_event_period)


def test_candidate_rejects_forged_source_document_identity_binding() -> None:
    contracts = load_contracts_module()
    forged = candidate_payload()
    identity = forged["source_document_identity"]
    assert isinstance(identity, dict)
    identity["binding_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="identity binding"):
        contracts.validate_payload("candidate-claim", forged)

    mismatched_artifact = candidate_payload()
    identity = mismatched_artifact["source_document_identity"]
    assert isinstance(identity, dict)
    identity["artifact_sha256"] = SECOND_ARTIFACT_IDENTITY.removeprefix("sha256:")
    with pytest.raises(ValueError, match="identity evidence"):
        contracts.validate_payload("candidate-claim", mismatched_artifact)


def test_ledger_rejects_accepted_claim_with_failed_gate() -> None:
    contracts = load_contracts_module()
    accepted = ledger_payload()
    validate_ledger(contracts, accepted)

    failed_gate = deepcopy(accepted)
    failed_gate["acceptance_failures"] = ["scope mismatch"]
    with pytest.raises(ValueError, match="accepted claim cannot retain acceptance failures"):
        validate_ledger(contracts, failed_gate)

    accepted_with_unattempted_route = deepcopy(accepted)
    accepted_with_unattempted_route["unattempted_routes"] = [unattempted_route_payload()]
    with pytest.raises(ValueError, match="only blocked claims can retain unattempted routes"):
        validate_ledger(contracts, accepted_with_unattempted_route)

    conflict = conflict_ledger()
    conflict["conflict_evidence"] = {
        "left": conflict_evidence_side(
            ARTIFACT_IDENTITY,
            "ndri-china-pop-toys-2025",
            SCOPE_FINGERPRINT,
            34.2,
        ),
        "right": conflict_evidence_side(
            SECOND_ARTIFACT_IDENTITY,
            "official-statistics-2025",
            SECOND_SCOPE_FINGERPRINT,
            31.8,
        ),
    }
    validate_ledger(contracts, conflict)

    blocked = blocked_ledger()
    validate_ledger(contracts, blocked)


def test_ledger_requires_a_sha256_shaped_request_scope_fingerprint() -> None:
    contracts = load_contracts_module()
    ledger = ledger_payload()
    validate_ledger(contracts, ledger)

    ledger["request_scope_fingerprint"] = "not-a-sha256"

    with pytest.raises(ValueError, match="request_scope_fingerprint"):
        validate_ledger(contracts, ledger)


def test_blocked_ledger_requires_consistent_route_and_escalation_layers() -> None:
    contracts = load_contracts_module()
    blocked = blocked_ledger()
    validate_ledger(contracts, blocked)

    route_layer_mismatch = deepcopy(blocked)
    route_layer_mismatch["unattempted_routes"][0]["route_layer"] = 99
    with pytest.raises(ValueError, match="unattempted route layer"):
        validate_ledger(contracts, route_layer_mismatch)

    escalation_layer_mismatch = deepcopy(blocked)
    escalation_layer_mismatch["next_escalation"]["next_layer"] = 99
    with pytest.raises(ValueError, match="next escalation layer"):
        validate_ledger(contracts, escalation_layer_mismatch)


def test_ledger_rejects_absence_claim_with_unattempted_route() -> None:
    contracts = load_contracts_module()
    exhausted = exhausted_absence_ledger()
    validate_ledger(contracts, exhausted)

    unattempted = deepcopy(exhausted)
    unattempted["unattempted_routes"] = [unattempted_route_payload()]
    with pytest.raises(ValueError, match="all applicable routes must be terminal"):
        validate_ledger(contracts, unattempted)


def test_exhausted_ledger_requires_planner_owned_complete_inventory() -> None:
    contracts = load_contracts_module()
    exhausted = exhausted_absence_ledger()
    later_route = applicable_route_payload(
        route_id="layer-4-industry-overview",
        route_layer=4,
    )

    with pytest.raises(ValueError, match="does not match planner route inventory"):
        validate_ledger(
            contracts,
            exhausted,
            receipt_routes=(
                applicable_route_payload(),
                later_route,
            ),
        )


def test_ledger_requires_a_strict_untampered_planner_inventory_receipt() -> None:
    contracts = load_contracts_module()
    accepted = ledger_payload()

    with pytest.raises(ValueError, match="requires a planner inventory receipt"):
        contracts.validate_payload("research-ledger", accepted)

    receipt = planner_inventory_receipt(accepted["applicable_routes"])
    receipt["unexpected"] = True
    with pytest.raises(ValueError, match="planner-inventory-receipt violates schema"):
        contracts.validate_payload(
            "research-ledger",
            accepted,
            planner_inventory_receipt=receipt,
        )

    tampered = planner_inventory_receipt(accepted["applicable_routes"])
    tampered["content_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="content SHA-256 mismatch"):
        contracts.validate_payload(
            "research-ledger",
            accepted,
            planner_inventory_receipt=tampered,
        )


@pytest.mark.parametrize("mutation", ("modified", "omitted"))
def test_planner_receipt_rejects_modified_or_omitted_planner_inputs(
    mutation: str,
) -> None:
    contracts = load_contracts_module()
    receipt = planner_inventory_receipt([applicable_route_payload()])
    planner_inputs = receipt["planner_inputs"]
    assert isinstance(planner_inputs, dict)
    if mutation == "modified":
        planner_inputs["source_function"] = "invented-source-function"
        expected = "planner input fingerprint"
    else:
        planner_inputs.pop("vocabulary_identity")
        expected = "vocabulary_identity"
    rehash_receipt_content(receipt)

    with pytest.raises(ValueError, match=expected):
        contracts.validate_payload("planner-inventory-receipt", receipt)


def test_planner_receipt_rejects_invented_fingerprint_after_content_rehash() -> None:
    contracts = load_contracts_module()
    receipt = planner_inventory_receipt([applicable_route_payload()])
    receipt["planner_input_fingerprint"] = "0" * 64
    rehash_receipt_content(receipt)

    with pytest.raises(ValueError, match="planner input fingerprint"):
        contracts.validate_payload("planner-inventory-receipt", receipt)


def test_positive_exhausted_ledger_also_requires_complete_planner_inventory() -> None:
    contracts = load_contracts_module()
    exhausted = exhausted_absence_ledger()
    exhausted["absence_claim"] = False

    with pytest.raises(ValueError, match="does not match planner route inventory"):
        validate_ledger(
            contracts,
            exhausted,
            receipt_routes=(
                applicable_route_payload(),
                applicable_route_payload(
                    route_id="layer-5-broad-dynamic",
                    route_layer=5,
                ),
            ),
        )


def test_positive_exhaustion_requires_every_planned_route_to_be_terminal() -> None:
    contracts = load_contracts_module()
    exhausted = exhausted_absence_ledger()
    exhausted["absence_claim"] = False
    later_route = applicable_route_payload(
        route_id="layer-2-official-statistics-fallback",
        route_layer=2,
    )
    exhausted["applicable_routes"].append(later_route)

    with pytest.raises(ValueError, match="does not cover every applicable route"):
        validate_ledger(contracts, exhausted)

    exhausted["attempts"].append(
        {
            **attempt_payload(
                route_id="layer-2-official-statistics-fallback",
                terminal_reason="rejected",
            ),
            "route_layer": 2,
        }
    )
    validate_ledger(contracts, exhausted)


def test_positive_exhaustion_rejects_blocked_terminal_reason() -> None:
    contracts = load_contracts_module()
    exhausted = exhausted_absence_ledger()
    exhausted["absence_claim"] = False
    exhausted["attempts"] = [attempt_payload(terminal_reason="technical-failure")]

    with pytest.raises(ValueError, match=r"technical-failure.*blocked"):
        validate_ledger(contracts, exhausted)


def test_terminal_blocked_ledger_does_not_require_fake_escalation() -> None:
    contracts = load_contracts_module()
    blocked = ledger_payload(status="blocked", absence_claim=True)
    blocked["attempts"] = [attempt_payload(terminal_reason="access-unavailable")]
    blocked["accepted_evidence"] = None
    blocked["gate"] = {"outcome": "unresolved", "failures": ["source unavailable"]}
    blocked["next_escalation"] = None
    blocked["unattempted_routes"] = []

    validate_ledger(contracts, blocked)


def test_not_applicable_attempt_can_serialize_exhaustion() -> None:
    contracts = load_contracts_module()
    exhausted = exhausted_absence_ledger()
    exhausted["attempts"] = [attempt_payload(terminal_reason="not-applicable")]

    validate_ledger(contracts, exhausted)


def test_route_cache_cannot_store_acceptance_thresholds() -> None:
    contracts = load_contracts_module()
    cache = route_cache_payload()
    contracts.validate_payload("route-cache", cache)

    cache["recipes"][0]["minimum_source_authority"] = "Low"
    with pytest.raises(ValueError, match="minimum_source_authority"):
        contracts.validate_payload("route-cache", cache)


@pytest.mark.parametrize(
    "field",
    (
        "claim_type",
        "subject_relation",
        "document_type",
        "source_function",
        "query_pattern",
        "index_endpoint",
        "identity_rule",
        "extraction_hint",
    ),
)
def test_route_cache_rejects_whitespace_only_recipe_strings(field: str) -> None:
    contracts = load_contracts_module()
    cache = route_cache_payload()
    recipe = cache["recipes"][0]
    assert isinstance(recipe, dict)
    recipe[field] = " \t "

    with pytest.raises(ValueError, match=field):
        contracts.validate_payload("route-cache", cache)


@pytest.mark.parametrize("label_field", ("geographies", "industries"))
def test_route_cache_rejects_whitespace_only_recipe_labels(label_field: str) -> None:
    contracts = load_contracts_module()
    cache = route_cache_payload()
    recipe = cache["recipes"][0]
    assert isinstance(recipe, dict)
    recipe[label_field] = [" \n "]

    with pytest.raises(ValueError, match=label_field):
        contracts.validate_payload("route-cache", cache)


def test_uncataloged_candidate_is_valid_with_complete_runtime_provenance() -> None:
    contracts = load_contracts_module()
    candidate = candidate_payload()

    assert "catalog_source_id" not in candidate["source"]
    contracts.validate_payload("candidate-claim", candidate)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda ledger: ledger.update(attempts=[]),
        lambda ledger: ledger.update(attempts=[attempt_payload(terminal_reason="not-found")]),
        lambda ledger: ledger.update(accepted_evidence=None),
    ),
)
def test_accepted_ledger_requires_accepted_candidate_evidence_and_outcome(mutate) -> None:
    contracts = load_contracts_module()
    accepted = ledger_payload()
    mutate(accepted)

    with pytest.raises(ValueError, match="accepted ledger"):
        validate_ledger(contracts, accepted)


@pytest.mark.parametrize(
    "terminal_reason",
    ("technical-failure", "request-budget-exhausted", "access-unavailable"),
)
def test_exhausted_absence_rejects_technical_failure_and_budget_exhaustion(
    terminal_reason: str,
) -> None:
    contracts = load_contracts_module()
    exhausted = exhausted_absence_ledger()
    exhausted["attempts"] = [attempt_payload(terminal_reason=terminal_reason)]

    with pytest.raises(ValueError, match=terminal_reason):
        validate_ledger(contracts, exhausted)


def test_absence_exhaustion_rejects_omitted_applicable_route() -> None:
    contracts = load_contracts_module()
    exhausted = exhausted_absence_ledger()
    exhausted["applicable_routes"] = [
        applicable_route_payload(),
        applicable_route_payload(
            route_id="layer-2-official-statistics-fallback",
            route_layer=2,
        ),
    ]

    with pytest.raises(ValueError, match="does not cover every applicable route"):
        validate_ledger(contracts, exhausted)


def test_conflict_requires_distinct_structured_evidence_sides() -> None:
    contracts = load_contracts_module()
    conflict = conflict_ledger()
    with pytest.raises(ValueError, match="conflict ledger requires structured evidence"):
        validate_ledger(contracts, conflict)

    without_attempts = conflict_ledger()
    without_attempts["attempts"] = []
    with pytest.raises(ValueError, match="conflict ledger requires recorded attempts"):
        validate_ledger(contracts, without_attempts)

    repeated_side = conflict_evidence_side(
        artifact_identity=ARTIFACT_IDENTITY,
        lineage_id="ndri-china-pop-toys-2025",
        definition_scope_fingerprint=SCOPE_FINGERPRINT,
        value=34.2,
    )
    same_side = conflict_ledger()
    same_side["conflict_evidence"] = {
        "left": repeated_side,
        "right": deepcopy(repeated_side),
    }
    with pytest.raises(ValueError, match="conflict evidence sides must be distinct"):
        validate_ledger(contracts, same_side)

    distinct_sides = deepcopy(same_side)
    distinct_sides["conflict_evidence"]["right"] = conflict_evidence_side(
        artifact_identity=SECOND_ARTIFACT_IDENTITY,
        lineage_id="official-statistics-2025",
        definition_scope_fingerprint=SECOND_SCOPE_FINGERPRINT,
        value=31.8,
    )
    validate_ledger(contracts, distinct_sides)


def test_event_conflict_evidence_supports_text_and_source_identity() -> None:
    contracts = load_contracts_module()
    conflict = conflict_ledger()
    event_key = "2025-03-01|board|withdraw-acquisition-proposal"
    conflict["conflict_evidence"] = {
        "left": conflict_evidence_side(
            ARTIFACT_IDENTITY,
            "named-counterparty-governance-2025",
            EVENT_SCOPE_FINGERPRINT,
            EVENT_TEXT,
            event_key=event_key,
            evidence_id="counterparty-notice-2025-03-01",
        ),
        "right": conflict_evidence_side(
            SECOND_ARTIFACT_IDENTITY,
            "issuer-first-party-governance-2025",
            EVENT_SCOPE_FINGERPRINT,
            "Issuer stated the proposal remained active on 2025-03-01.",
            event_key=event_key,
            evidence_id="issuer-announcement-2025-03-01",
        ),
    }
    conflict["attempts"][0]["lineage_id"] = "named-counterparty-governance-2025"
    conflict["attempts"][1]["lineage_id"] = "issuer-first-party-governance-2025"

    validate_ledger(contracts, conflict)


def test_event_conflict_evidence_must_reference_the_same_event_key() -> None:
    contracts = load_contracts_module()
    conflict = conflict_ledger()
    conflict["conflict_evidence"] = {
        "left": conflict_evidence_side(
            ARTIFACT_IDENTITY,
            "ndri-china-pop-toys-2025",
            EVENT_SCOPE_FINGERPRINT,
            EVENT_TEXT,
            event_key="2025-03-01|board|withdraw-acquisition-proposal",
            evidence_id="counterparty-notice-2025-03-01",
        ),
        "right": conflict_evidence_side(
            SECOND_ARTIFACT_IDENTITY,
            "official-statistics-2025",
            EVENT_SCOPE_FINGERPRINT,
            "Issuer announced a separate audit review.",
            event_key="2025-03-01|audit-committee|launch-review",
            evidence_id="issuer-announcement-2025-03-01",
        ),
    }

    with pytest.raises(ValueError, match="same event_key"):
        validate_ledger(contracts, conflict)


@pytest.mark.parametrize(
    ("unit", "definition_scope_fingerprint"),
    (
        ("USD million", SCOPE_FINGERPRINT),
        ("CNY billion", SECOND_SCOPE_FINGERPRINT),
    ),
)
def test_candidate_rejects_mixed_unit_or_definition_without_reconciliation(
    unit: str,
    definition_scope_fingerprint: str,
) -> None:
    contracts = load_contracts_module()
    mixed = candidate_payload()
    mixed["values"].append(
        {
            "period": "2024",
            "value": 4_600.0,
            "unit": unit,
            "status": "historical-estimate",
            "definition_scope_fingerprint": definition_scope_fingerprint,
            "canonical_value": {
                "value": 33.12,
                "unit": "CNY billion",
                "definition_scope_fingerprint": SCOPE_FINGERPRINT,
                "reconciliation_id": "test-reconciliation",
            },
        }
    )
    with pytest.raises(ValueError, match="reconciliation"):
        contracts.validate_payload("candidate-claim", mixed)

    reconciled = deepcopy(mixed)
    reconciled["reconciliations"] = [
        {
            "reconciliation_id": "test-reconciliation",
            "from_unit": unit,
            "to_unit": "CNY billion",
            "from_scope_fingerprint": definition_scope_fingerprint,
            "to_scope_fingerprint": reconciled["scope_fingerprint"],
            "method": "foreign-exchange conversion and explicit market-scope bridge",
            "formula": "USD million * 0.0072",
            "artifact_identity": ARTIFACT_IDENTITY,
            "artifact_sha256": ARTIFACT_IDENTITY.removeprefix("sha256:"),
        }
    ]
    contracts.validate_payload("candidate-claim", reconciled)


def test_accepted_and_unresolved_gate_state_invariants() -> None:
    contracts = load_contracts_module()
    accepted = ledger_payload()
    accepted["gate"] = {"outcome": "failed", "failures": ["scope mismatch"]}
    with pytest.raises(ValueError, match="accepted ledger requires a passed gate"):
        validate_ledger(contracts, accepted)

    unresolved = blocked_ledger()
    unresolved["next_escalation"] = None
    with pytest.raises(ValueError, match="unresolved ledger requires next escalation"):
        validate_ledger(contracts, unresolved)


def test_accepted_route_inventory_requires_explicit_post_gate_skip() -> None:
    contracts = load_contracts_module()
    accepted = ledger_payload()
    accepted["applicable_routes"].append(
        applicable_route_payload(
            route_id="layer-2-official-statistics-fallback",
            route_layer=2,
        )
    )
    with pytest.raises(ValueError, match="accepted ledger leaves applicable routes"):
        validate_ledger(contracts, accepted)

    explicitly_skipped = deepcopy(accepted)
    explicitly_skipped["skipped_after_acceptance"] = [
        {
            "route_id": "layer-2-official-statistics-fallback",
            "route_layer": 2,
            "reason": "gate passed with accepted evidence",
        }
    ]
    validate_ledger(contracts, explicitly_skipped)


def test_accepted_absence_ledger_cannot_skip_planner_applicable_routes() -> None:
    contracts = load_contracts_module()
    accepted_absence = ledger_payload(absence_claim=True)
    later_route = applicable_route_payload(
        route_id="layer-4-industry-overview",
        route_layer=4,
    )
    accepted_absence["applicable_routes"].append(later_route)
    accepted_absence["skipped_after_acceptance"] = [
        {
            "route_id": later_route["route_id"],
            "route_layer": later_route["route_layer"],
            "reason": "gate passed before later layer",
        }
    ]

    with pytest.raises(ValueError, match="accepted absence ledger cannot skip routes"):
        contracts.validate_payload(
            "research-ledger",
            accepted_absence,
            planner_inventory_receipt=planner_inventory_receipt(
                accepted_absence["applicable_routes"]
            ),
        )


def test_accepted_absence_ledger_requires_every_planned_route_terminal() -> None:
    contracts = load_contracts_module()
    accepted_absence = ledger_payload(absence_claim=True)
    later_route = applicable_route_payload(
        route_id="layer-4-industry-overview",
        route_layer=4,
    )
    accepted_absence["applicable_routes"].append(later_route)
    receipt = planner_inventory_receipt(accepted_absence["applicable_routes"])

    with pytest.raises(ValueError, match="accepted absence ledger does not cover every"):
        contracts.validate_payload(
            "research-ledger",
            accepted_absence,
            planner_inventory_receipt=receipt,
        )

    accepted_absence["attempts"].append(
        {
            **attempt_payload(
                route_id="layer-4-industry-overview",
                terminal_reason="not-found",
            ),
            "route_layer": 4,
            "started_at": "2026-08-02T00:58:00+00:00",
            "completed_at": "2026-08-02T00:59:00+00:00",
        }
    )
    contracts.validate_payload(
        "research-ledger",
        accepted_absence,
        planner_inventory_receipt=receipt,
    )


def test_unresolved_next_escalation_routes_are_unattempted_applicable_routes() -> None:
    contracts = load_contracts_module()
    conflict = conflict_ledger()
    conflict["conflict_evidence"] = {
        "left": conflict_evidence_side(
            ARTIFACT_IDENTITY,
            "ndri-china-pop-toys-2025",
            SCOPE_FINGERPRINT,
            34.2,
        ),
        "right": conflict_evidence_side(
            SECOND_ARTIFACT_IDENTITY,
            "official-statistics-2025",
            SECOND_SCOPE_FINGERPRINT,
            31.8,
        ),
    }

    outside_inventory = deepcopy(conflict)
    outside_inventory["next_escalation"]["route_ids"] = ["layer-9-unplanned-route"]
    with pytest.raises(ValueError, match="subset of applicable routes"):
        validate_ledger(contracts, outside_inventory)

    already_terminal = deepcopy(conflict)
    already_terminal["next_escalation"]["route_ids"] = ["layer-1-ndri-market-size"]
    with pytest.raises(ValueError, match="already terminal"):
        validate_ledger(contracts, already_terminal)


def test_candidate_reconciliation_must_map_divergent_values_into_canonical_pair() -> None:
    contracts = load_contracts_module()
    reverse_bridge = candidate_payload()
    reverse_bridge["values"].append(
        {
            "period": "2024",
            "value": 4_600.0,
            "unit": "USD million",
            "status": "historical-estimate",
            "definition_scope_fingerprint": SECOND_SCOPE_FINGERPRINT,
            "canonical_value": {
                "value": 33.12,
                "unit": "CNY billion",
                "definition_scope_fingerprint": SCOPE_FINGERPRINT,
                "reconciliation_id": "reverse-reconciliation",
            },
        }
    )
    reverse_bridge["reconciliations"] = [
        {
            "reconciliation_id": "reverse-reconciliation",
            "from_unit": "CNY billion",
            "to_unit": "USD million",
            "from_scope_fingerprint": SCOPE_FINGERPRINT,
            "to_scope_fingerprint": SECOND_SCOPE_FINGERPRINT,
            "method": "foreign-exchange conversion and explicit market-scope bridge",
            "formula": "CNY billion / 0.0072",
            "artifact_identity": ARTIFACT_IDENTITY,
            "artifact_sha256": ARTIFACT_IDENTITY.removeprefix("sha256:"),
        }
    ]

    with pytest.raises(ValueError, match="must map divergent values into the canonical pair"):
        contracts.validate_payload("candidate-claim", reverse_bridge)


@pytest.mark.parametrize(
    ("field", "mismatched_value"),
    (
        ("artifact_identity", SECOND_ARTIFACT_IDENTITY),
        ("lineage_id", "official-statistics-2025"),
    ),
)
def test_accepted_evidence_reference_must_match_accepted_attempt(
    field: str,
    mismatched_value: str,
) -> None:
    contracts = load_contracts_module()
    accepted = ledger_payload()
    accepted["accepted_evidence"][field] = mismatched_value

    with pytest.raises(ValueError, match="accepted ledger evidence must reference"):
        validate_ledger(contracts, accepted)


def test_accepted_ledger_rejects_attempts_completed_after_acceptance() -> None:
    contracts = load_contracts_module()
    accepted = ledger_payload()
    accepted["applicable_routes"].append(
        applicable_route_payload(
            route_id="layer-2-official-statistics-fallback",
            route_layer=2,
        )
    )
    accepted["attempts"].append(
        {
            **attempt_payload(
                route_id="layer-2-official-statistics-fallback",
                terminal_reason="not-found",
            ),
            "route_layer": 2,
            "started_at": "2026-08-02T01:01:01+00:00",
            "completed_at": "2026-08-02T01:02:00+00:00",
        }
    )

    with pytest.raises(ValueError, match="completed after accepted attempt"):
        validate_ledger(contracts, accepted)
