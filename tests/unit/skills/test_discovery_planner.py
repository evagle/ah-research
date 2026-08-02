from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PLANNER_PATH = (
    REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts" / "discovery_planner.py"
)
NOW = datetime(2026, 8, 2, tzinfo=UTC)
SCOPE_FINGERPRINT = "a" * 64
BOUND_ROUTES = (
    {
        "route_id": "bound-pop-mart-filing",
        "subject_relation": "bound-local",
        "document_type": "bound-filing",
    },
)


def load_planner_module():
    assert PLANNER_PATH.is_file(), f"missing planner: {PLANNER_PATH}"
    script_dir = str(PLANNER_PATH.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("discovery_planner", PLANNER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def request(*, absence_claim: bool = False) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "claim_id": "cn-pop-toy-market-2020-2025",
        "claim_type": "market-size",
        "subject": "Pop Mart",
        "metric": "market-size",
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
        "independent_cross_check_required": False,
        "absence_claim": absence_claim,
        "as_of": "2026-08-02",
    }


def source_profiles() -> list[dict[str, object]]:
    return [
        {
            "id": "official-market-data",
            "name": "Official Market Data",
            "publisher_type": "official-statistics",
            "geographies": ["China"],
            "industries": ["pop-toys"],
            "functions": [
                {
                    "id": "market-size",
                    "authority": "High",
                    "utility": "High",
                    "direct_urls": [{"url": "https://official.example/market-size"}],
                    "fallbacks": ["fallback-market-data-alternate-market-size"],
                }
            ],
            "access": {
                "status": "reachable",
                "last_checked": "2026-08-01T00:00:00+00:00",
            },
        },
        {
            "id": "fallback-market-data",
            "name": "Fallback Market Data",
            "publisher_type": "original-research",
            "geographies": ["China"],
            "industries": ["pop-toys"],
            "functions": [
                {
                    "id": "alternate-market-size",
                    "authority": "High",
                    "utility": "Medium",
                    "direct_urls": [{"url": "https://fallback.example/market-size"}],
                    "fallbacks": [],
                }
            ],
            "access": {
                "status": "reachable",
                "last_checked": "2026-08-01T00:00:00+00:00",
            },
        },
    ]


def relation_records() -> tuple[dict[str, str], ...]:
    return (
        {
            "related_subject": "Top Toy",
            "relation": "direct-peer",
            "source_id": "top-toy-disclosures",
            "source_function": "company-disclosures",
            "direct_url": "https://top-toy.example/disclosures",
        },
        {
            "related_subject": "Molly",
            "relation": "category-leader",
            "source_id": "molly-disclosures",
            "source_function": "company-disclosures",
            "direct_url": "https://molly.example/disclosures",
        },
        {
            "related_subject": "Toy Applicant A",
            "relation": "active-listing-applicant",
            "source_id": "hkex-listing-applicants",
            "source_function": "listing-applicant-documents",
            "direct_url": "https://www1.hkexnews.hk/app/appindex.html?lang=en",
        },
        {
            "related_subject": "Toy Applicant B",
            "relation": "recent-listing-applicant",
            "source_id": "hkex-listing-applicants",
            "source_function": "listing-applicant-documents",
            "direct_url": "https://www1.hkexnews.hk/app/appindex.html?lang=en",
        },
    )


def plan(
    planner,
    claim: dict[str, object],
    *,
    attempts: tuple[dict[str, object], ...] = (),
    relations: tuple[dict[str, str], ...] = (),
    source_function: str | None = None,
    profiles: list[dict[str, object]] | None = None,
    bound_routes: tuple[dict[str, str], ...] = BOUND_ROUTES,
    gate_result=None,
    ledger: dict[str, object] | None = None,
):
    kwargs = {}
    if source_function is not None:
        kwargs["source_function"] = source_function
    return planner.plan_next_layer(
        claim,
        profiles if profiles is not None else source_profiles(),
        {},
        relation_records=relations,
        completed_attempts=attempts,
        bound_routes=bound_routes,
        now=NOW,
        gate_result=gate_result,
        ledger=ledger,
        **kwargs,
    )


def terminal_attempt(route, reason: str = "not-found") -> dict[str, object]:
    return {
        "route_id": route.route_id,
        "route_layer": route.route_layer,
        "terminal_reason": reason,
    }


def complete_current_layer(planner, claim, attempts, relations=()):
    current_plan = plan(planner, claim, attempts=tuple(attempts), relations=relations)
    assert current_plan is not None
    attempts.extend(terminal_attempt(route) for route in current_plan.routes)


def normalize_query(value: str) -> str:
    return " ".join(value.casefold().split())


def accepted_ledger(
    claim_id: str,
    request_scope_fingerprint: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "claim_id": claim_id,
        "request_scope_fingerprint": request_scope_fingerprint,
        "absence_claim": False,
        "status": "accepted",
        "applicable_routes": [
            {
                "route_id": "bound-pop-mart-filing",
                "route_layer": 0,
                "subject_relation": "bound-local",
                "document_type": "bound-filing",
            }
        ],
        "attempts": [
            {
                "route_id": "bound-pop-mart-filing",
                "route_layer": 0,
                "subject_relation": "bound-local",
                "document_type": "bound-filing",
                "query_variant": "Pop Mart market size",
                "started_at": "2026-08-02T00:00:00+00:00",
                "completed_at": "2026-08-02T00:01:00+00:00",
                "artifact_identity": "sha256:" + "1" * 64,
                "lineage_id": "pop-mart-market-size",
                "terminal_reason": "accepted",
                "acceptance_failures": [],
            }
        ],
        "acceptance_failures": [],
        "accepted_evidence": {
            "candidate_document_id": "POP-MART-2025",
            "artifact_identity": "sha256:" + "1" * 64,
            "lineage_id": "pop-mart-market-size",
        },
        "conflict_evidence": None,
        "gate": {"outcome": "passed", "failures": []},
        "next_escalation": None,
        "skipped_after_acceptance": [],
        "unattempted_routes": [],
    }


def blocked_ledger(
    claim: dict[str, object],
    request_scope_fingerprint: str,
    applicable_routes,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "claim_id": claim["claim_id"],
        "request_scope_fingerprint": request_scope_fingerprint,
        "absence_claim": claim["absence_claim"],
        "status": "blocked",
        "applicable_routes": [
            {
                "route_id": route.route_id,
                "route_layer": route.route_layer,
                "subject_relation": route.subject_relation,
                "document_type": route.document_type,
            }
            for route in applicable_routes
        ],
        "attempts": [
            {
                "route_id": "bound-pop-mart-filing",
                "route_layer": 0,
                "subject_relation": "bound-local",
                "document_type": "bound-filing",
                "query_variant": "Pop Mart market size",
                "started_at": "2026-08-02T00:00:00+00:00",
                "completed_at": "2026-08-02T00:01:00+00:00",
                "artifact_identity": "sha256:" + "1" * 64,
                "lineage_id": "pop-mart-market-size",
                "terminal_reason": "access-unavailable",
                "acceptance_failures": [],
            }
        ],
        "acceptance_failures": [],
        "accepted_evidence": None,
        "conflict_evidence": None,
        "gate": {"outcome": "unresolved", "failures": ["source unavailable"]},
        "next_escalation": {
            "next_layer": 1,
            "route_ids": ["layer-1-official-market-data-market-size"],
        },
        "skipped_after_acceptance": [],
        "unattempted_routes": [
            {
                "route_id": "layer-1-official-market-data-market-size",
                "route_layer": 1,
                "reason": "source access unavailable",
            }
        ],
    }


def authority_profiles() -> list[dict[str, object]]:
    profiles = source_profiles()
    profiles.append(
        {
            "id": "medium-market-data",
            "name": "Medium Authority Market Data",
            "publisher_type": "original-research",
            "geographies": ["China"],
            "industries": ["pop-toys"],
            "functions": [
                {
                    "id": "market-size",
                    "authority": "Medium",
                    "utility": "High",
                    "direct_urls": [{"url": "https://medium.example/market-size"}],
                    "fallbacks": [],
                }
            ],
            "access": {
                "status": "reachable",
                "last_checked": "2026-08-01T00:00:00+00:00",
            },
        }
    )
    return profiles


def fallback_graph_profiles() -> list[dict[str, object]]:
    profiles = []
    for source_id, function_id, fallbacks in (
        ("source-a", "market-size", ["source-b-alternate-market-size"]),
        (
            "source-b",
            "alternate-market-size",
            ["source-c-second-alternate-market-size"],
        ),
        ("source-c", "second-alternate-market-size", []),
    ):
        profiles.append(
            {
                "id": source_id,
                "name": source_id,
                "publisher_type": "official-statistics",
                "geographies": ["China"],
                "industries": ["pop-toys"],
                "functions": [
                    {
                        "id": function_id,
                        "authority": "High",
                        "utility": "High",
                        "direct_urls": [{"url": f"https://{source_id}.example/market-size"}],
                        "fallbacks": fallbacks,
                    }
                ],
                "access": {
                    "status": "reachable",
                    "last_checked": "2026-08-01T00:00:00+00:00",
                },
            }
        )
    return profiles


def complete_all_applicable_layers(
    planner,
    claim: dict[str, object],
    reason: str,
) -> tuple[dict[str, object], ...]:
    attempts: list[dict[str, object]] = []
    while True:
        next_plan = plan(planner, claim, attempts=tuple(attempts), relations=relation_records())
        if next_plan is None or not next_plan.routes:
            return tuple(attempts)
        attempts.extend(terminal_attempt(route, reason) for route in next_plan.routes)


def test_validated_gate_acceptance_prevents_next_layer() -> None:
    planner = load_planner_module()
    claim = request()
    passed_gate = planner.GateResult(
        claim_id=claim["claim_id"],
        passed=True,
        failures=(),
        scope_fingerprint=planner.request_scope_fingerprint(claim),
    )

    next_plan = plan(planner, claim, gate_result=passed_gate)

    assert next_plan is None


def test_raw_accepted_attempt_does_not_establish_claim_acceptance() -> None:
    planner = load_planner_module()
    raw_accepted_attempt = (
        {
            "route_id": "bound-pop-mart-filing",
            "route_layer": 0,
            "terminal_reason": "accepted",
        },
    )
    before = deepcopy(raw_accepted_attempt)

    next_plan = plan(planner, request(), attempts=raw_accepted_attempt)

    assert next_plan is not None
    assert next_plan.current_layer == planner.HIGHEST_AUTHORITY
    assert raw_accepted_attempt == before


def test_planned_routes_carry_normalized_request_cache_dimensions() -> None:
    planner = load_planner_module()
    claim = request()
    claim["claim_type"] = " Market-Size "
    claim["geographies"] = [" China "]
    claim["industries"] = [" Pop-Toys "]

    route_plan = plan(planner, claim)

    assert route_plan is not None
    assert all(route.claim_type == "market-size" for route in route_plan.routes)
    assert all(route.geographies == ("china",) for route in route_plan.routes)
    assert all(route.industries == ("pop-toys",) for route in route_plan.routes)


def test_layer_order_is_monotonic() -> None:
    planner = load_planner_module()
    claim = request()
    attempts: list[dict[str, object]] = []
    expected_layers = (
        planner.BOUND_LOCAL,
        planner.HIGHEST_AUTHORITY,
        planner.SAME_FUNCTION_FALLBACK,
        planner.SUBJECT_RELATIONSHIP,
        planner.DOCUMENT_TYPE,
        planner.BROAD_DYNAMIC,
    )

    actual_layers = []
    for expected_layer in expected_layers:
        next_plan = plan(
            planner,
            claim,
            attempts=tuple(attempts),
            relations=relation_records(),
        )
        assert next_plan is not None
        assert next_plan.current_layer == expected_layer
        assert {route.route_layer for route in next_plan.routes} == {expected_layer}
        actual_layers.append(next_plan.current_layer)
        attempts.extend(terminal_attempt(route) for route in next_plan.routes)

    assert actual_layers == list(expected_layers)
    outcome = plan(planner, claim, attempts=tuple(attempts), relations=relation_records())
    assert outcome is not None
    assert outcome.current_layer is None
    assert outcome.routes == ()
    assert outcome.outcome == "exhausted"
    assert {route.route_layer for route in outcome.applicable_routes} == set(expected_layers)


def test_explicit_source_function_keeps_request_contract_strict() -> None:
    planner = load_planner_module()
    claim = request()
    claim["claim_type"] = "industry-series"

    next_plan = plan(
        planner,
        claim,
        attempts=(
            {
                "route_id": "bound-pop-mart-filing",
                "route_layer": 0,
                "terminal_reason": "not-found",
            },
        ),
        source_function="market-size",
    )

    assert next_plan is not None
    assert next_plan.current_layer == planner.HIGHEST_AUTHORITY
    assert {route.source_function for route in next_plan.routes} == {"market-size"}


def test_absence_claim_keeps_planning_after_an_accepted_attempt() -> None:
    planner = load_planner_module()
    absence_claim = request(absence_claim=True)
    accepted_bound_attempt = (
        {
            "route_id": "bound-pop-mart-filing",
            "route_layer": 0,
            "terminal_reason": "accepted",
        },
    )

    next_plan = plan(planner, absence_claim, attempts=accepted_bound_attempt)

    assert next_plan is not None
    assert next_plan.outcome == "pending"
    assert next_plan.current_layer == planner.HIGHEST_AUTHORITY


def test_absence_claim_keeps_planning_after_a_passed_gate() -> None:
    planner = load_planner_module()
    absence_claim = request(absence_claim=True)
    passed_gate = planner.GateResult(
        claim_id=absence_claim["claim_id"],
        passed=True,
        failures=(),
        scope_fingerprint=planner.request_scope_fingerprint(absence_claim),
    )

    next_plan = plan(planner, absence_claim, gate_result=passed_gate)

    assert next_plan is not None
    assert next_plan.outcome == "pending"
    assert next_plan.current_layer == planner.BOUND_LOCAL


@pytest.mark.parametrize(
    "reason",
    ("technical-failure", "access-unavailable", "request-budget-exhausted"),
)
def test_absence_terminal_failures_return_blocked_outcome(reason: str) -> None:
    planner = load_planner_module()
    absence_claim = request(absence_claim=True)
    attempts = complete_all_applicable_layers(planner, absence_claim, reason)

    outcome = plan(
        planner,
        absence_claim,
        attempts=attempts,
        relations=relation_records(),
    )

    assert outcome is not None
    assert outcome.routes == ()
    assert outcome.current_layer is None
    assert outcome.outcome == "blocked"


def test_absence_not_found_routes_return_exhausted_outcome() -> None:
    planner = load_planner_module()
    absence_claim = request(absence_claim=True)
    attempts = complete_all_applicable_layers(planner, absence_claim, "not-found")

    outcome = plan(
        planner,
        absence_claim,
        attempts=attempts,
        relations=relation_records(),
    )

    assert outcome is not None
    assert outcome.routes == ()
    assert outcome.current_layer is None
    assert outcome.outcome == "exhausted"


def test_positive_rejected_routes_return_exhausted_outcome() -> None:
    planner = load_planner_module()
    claim = request()
    attempts = complete_all_applicable_layers(planner, claim, "rejected")

    outcome = plan(
        planner,
        claim,
        attempts=attempts,
        relations=relation_records(),
    )

    assert outcome is not None
    assert outcome.routes == ()
    assert outcome.current_layer is None
    assert outcome.outcome == "exhausted"


def test_route_plan_returns_tamper_evident_inventory_receipt() -> None:
    planner = load_planner_module()
    claim = request()

    route_plan = plan(planner, claim, relations=relation_records())

    assert route_plan is not None
    receipt = route_plan.inventory_receipt
    assert receipt["claim_id"] == claim["claim_id"]
    assert receipt["request_scope_fingerprint"] == planner.request_scope_fingerprint(claim)
    planner_inputs = receipt["planner_inputs"]
    assert planner_inputs["request_identity"] == {
        "claim_id": claim["claim_id"],
        "request_scope_fingerprint": planner.request_scope_fingerprint(claim),
        "request_content_sha256": hashlib.sha256(
            json.dumps(
                claim,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
    assert planner_inputs["source_function"] == "market-size"
    assert planner_inputs["as_of"] == "2026-08-02"
    assert planner_inputs["effective_planning_time"] == NOW.isoformat()
    assert planner_inputs["maintained_profiles"] == [
        {
            "source_id": profile["id"],
            "content_sha256": hashlib.sha256(
                json.dumps(
                    profile,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        }
        for profile in sorted(source_profiles(), key=lambda profile: profile["id"])
    ]
    expected_relations = []
    for relation in relation_records():
        source_binding = {
            "source_id": relation["source_id"],
            "source_function": relation["source_function"],
            "direct_url": relation["direct_url"],
        }
        expected_relations.append(
            {
                "subject": relation["related_subject"],
                "relation": relation["relation"],
                **source_binding,
                "source_binding_sha256": hashlib.sha256(
                    json.dumps(
                        source_binding,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
            }
        )
    assert planner_inputs["relation_records"] == expected_relations
    assert receipt["route_inventory"] == [
        {
            "route_id": route.route_id,
            "route_layer": route.route_layer,
            "subject_relation": route.subject_relation,
            "document_type": route.document_type,
        }
        for route in route_plan.applicable_routes
    ]
    assert (
        planner_inputs["route_inventory_sha256"]
        == hashlib.sha256(
            json.dumps(
                receipt["route_inventory"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
    )
    assert (
        receipt["planner_input_fingerprint"]
        == hashlib.sha256(
            json.dumps(
                planner_inputs,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
    )
    content = {key: value for key, value in receipt.items() if key != "content_sha256"}
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assert receipt["content_sha256"] == hashlib.sha256(canonical).hexdigest()
    planner.validate_payload("planner-inventory-receipt", receipt)


def test_layer_one_keeps_only_the_highest_eligible_authority_tier() -> None:
    planner = load_planner_module()
    claim = request()
    claim["minimum_source_authority"] = "Medium"
    bound_terminal = (
        {
            "route_id": "bound-pop-mart-filing",
            "route_layer": 0,
            "terminal_reason": "not-found",
        },
    )

    next_plan = plan(
        planner,
        claim,
        attempts=bound_terminal,
        profiles=authority_profiles(),
    )

    assert next_plan is not None
    assert next_plan.current_layer == planner.HIGHEST_AUTHORITY
    assert {route.source_id for route in next_plan.routes} == {"official-market-data"}


def test_layer_two_contains_every_declared_fallback_hop() -> None:
    planner = load_planner_module()
    claim = request()
    bound_terminal = (
        {
            "route_id": "bound-pop-mart-filing",
            "route_layer": 0,
            "terminal_reason": "not-found",
        },
    )

    direct_plan = plan(
        planner,
        claim,
        attempts=bound_terminal,
        profiles=fallback_graph_profiles(),
    )

    assert direct_plan is not None
    assert direct_plan.current_layer == planner.HIGHEST_AUTHORITY
    assert {route.source_id for route in direct_plan.routes} == {"source-a"}

    fallback_attempts = (
        *bound_terminal,
        *(terminal_attempt(route) for route in direct_plan.routes),
    )
    fallback_plan = plan(
        planner,
        claim,
        attempts=fallback_attempts,
        profiles=fallback_graph_profiles(),
    )

    assert fallback_plan is not None
    assert fallback_plan.current_layer == planner.SAME_FUNCTION_FALLBACK
    assert {route.source_id for route in fallback_plan.routes} == {"source-b", "source-c"}


def test_zero_applicable_layers_advance_to_the_next_layer() -> None:
    planner = load_planner_module()
    bound_terminal = (
        {
            "route_id": "bound-pop-mart-filing",
            "route_layer": 0,
            "terminal_reason": "not-found",
        },
    )

    next_plan = plan(
        planner,
        request(),
        attempts=bound_terminal,
        profiles=[],
    )

    assert next_plan is not None
    assert next_plan.current_layer == planner.DOCUMENT_TYPE


def test_only_unresolved_claims_receive_routes() -> None:
    planner = load_planner_module()
    claim = request()
    attempts: list[dict[str, object]] = []

    for _ in range(6):
        complete_current_layer(planner, claim, attempts, relation_records())

    outcome = plan(planner, claim, attempts=tuple(attempts), relations=relation_records())
    assert outcome is not None
    assert outcome.current_layer is None
    assert outcome.routes == ()
    assert outcome.outcome == "exhausted"


def test_peer_listing_applicant_expansion_precedes_broad_search() -> None:
    planner = load_planner_module()
    claim = request()
    attempts: list[dict[str, object]] = []

    for _ in range(3):
        complete_current_layer(planner, claim, attempts)

    relationship_plan = plan(
        planner,
        claim,
        attempts=tuple(attempts),
        relations=relation_records(),
    )

    assert relationship_plan is not None
    assert relationship_plan.current_layer == planner.SUBJECT_RELATIONSHIP
    assert {route.subject_relation for route in relationship_plan.routes} == {
        "direct-peer",
        "category-leader",
        "active-listing-applicant",
        "recent-listing-applicant",
    }
    assert all(route.route_layer != planner.BROAD_DYNAMIC for route in relationship_plan.routes)

    attempts.extend(terminal_attempt(route) for route in relationship_plan.routes)
    document_plan = plan(planner, claim, attempts=tuple(attempts), relations=relation_records())

    assert document_plan is not None
    assert document_plan.current_layer == planner.DOCUMENT_TYPE
    assert {route.document_type for route in document_plan.routes} == {
        "prospectus",
        "listing-application",
        "industry-overview",
        "methodology-appendix",
        "association-report",
        "archive",
    }


def test_relationship_queries_use_the_related_subject() -> None:
    planner = load_planner_module()
    claim = request()
    attempts: list[dict[str, object]] = []

    for _ in range(3):
        complete_current_layer(planner, claim, attempts)

    relationship_plan = plan(
        planner,
        claim,
        attempts=tuple(attempts),
        relations=relation_records(),
    )

    assert relationship_plan is not None
    peer_route = next(
        route for route in relationship_plan.routes if route.subject_relation == "direct-peer"
    )
    assert any(variant.startswith("Top Toy ") for variant in peer_route.query_variants)


def test_layer_three_routes_preserve_dispatch_provenance_from_relation_records() -> None:
    planner = load_planner_module()
    claim = request()
    attempts: list[dict[str, object]] = []
    for _ in range(3):
        complete_current_layer(planner, claim, attempts)

    relationship_plan = plan(
        planner,
        claim,
        attempts=tuple(attempts),
        relations=relation_records(),
    )

    assert relationship_plan is not None
    applicant_route = next(
        route
        for route in relationship_plan.routes
        if route.subject_relation == "active-listing-applicant"
    )
    assert applicant_route.source_id == "hkex-listing-applicants"
    assert applicant_route.source_function == "listing-applicant-documents"
    assert applicant_route.direct_url == "https://www1.hkexnews.hk/app/appindex.html?lang=en"


def test_query_variants_include_chinese_english_metric_and_document_terms() -> None:
    planner = load_planner_module()
    expected_fingerprint = planner.request_scope_fingerprint(request())

    variants = planner.generate_query_variants(
        request(),
        document_types=("listing-application", "industry-overview"),
    )

    assert any("市场规模" in variant and "上市申请" in variant for variant in variants)
    assert any("market size" in variant and "prospectus" in variant for variant in variants)
    assert any("行业概览" in variant for variant in variants)
    assert all(variant.endswith(f"scope:{expected_fingerprint}") for variant in variants)
    for scope_term in (
        "China",
        "pop-toys",
        "retail consumers",
        "pop toys only",
        "retail value",
    ):
        assert all(scope_term in variant for variant in variants)


def test_query_scope_override_must_match_the_request_fingerprint() -> None:
    planner = load_planner_module()

    with pytest.raises(ValueError, match="scope fingerprint"):
        planner.generate_query_variants(
            request(),
            document_types=("listing-application",),
            definition_scope_fingerprint=SCOPE_FINGERPRINT,
        )


def test_synonyms_do_not_change_definition_constraints() -> None:
    planner = load_planner_module()
    scope_constrained_claim = request()
    scope_constrained_claim["definition_constraints"] = [
        "pop toys only",
        "retail value",
        "excludes adjacent collectible categories",
    ]

    variants = planner.generate_query_variants(
        scope_constrained_claim,
        document_types=("listing-application",),
    )

    assert variants
    assert all(
        variant.endswith(f"scope:{planner.request_scope_fingerprint(scope_constrained_claim)}")
        for variant in variants
    )
    assert all("collectible toys" not in variant.casefold() for variant in variants)


def test_queries_include_each_definition_constraint_as_searchable_text() -> None:
    planner = load_planner_module()
    constrained_claim = request()
    constrained_claim["definition_constraints"] = [
        "exclusion: adjacent collectible categories",
        "basis: audited retail sell-through",
    ]

    variants = planner.generate_query_variants(
        constrained_claim,
        document_types=("listing-application",),
    )

    assert variants
    for variant in variants:
        assert "definition_constraints" in variant
        assert "basis: audited retail sell-through" in variant
        assert "exclusion: adjacent collectible categories" in variant
        assert variant.index("basis: audited retail sell-through") < variant.index(
            "exclusion: adjacent collectible categories"
        )


def test_attempted_normalized_queries_are_deduplicated() -> None:
    planner = load_planner_module()
    scope_fingerprint = planner.request_scope_fingerprint(request())
    attempted_query = f"Pop Mart market size 2020 2025 prospectus scope:{scope_fingerprint}"

    variants = planner.generate_query_variants(
        request(),
        document_types=("listing-application",),
        definition_scope_fingerprint=scope_fingerprint,
        attempted_queries=(attempted_query, f"  {attempted_query.upper()}  "),
    )

    normalized_variants = tuple(normalize_query(variant) for variant in variants)
    assert normalized_variants == tuple(dict.fromkeys(normalized_variants))
    assert normalize_query(attempted_query) not in normalized_variants


def test_negative_claim_keeps_planning_until_all_layers_terminal() -> None:
    planner = load_planner_module()
    claim = request(absence_claim=True)
    attempts: list[dict[str, object]] = []

    for expected_layer in range(6):
        next_plan = plan(
            planner,
            claim,
            attempts=tuple(attempts),
            relations=relation_records(),
        )
        assert next_plan is not None
        assert next_plan.current_layer == expected_layer
        attempts.extend(terminal_attempt(route) for route in next_plan.routes)

    outcome = plan(planner, claim, attempts=tuple(attempts), relations=relation_records())
    assert outcome is not None
    assert outcome.outcome == "exhausted"


def test_resume_skips_accepted_claims_and_terminal_attempts() -> None:
    planner = load_planner_module()
    claim = request()
    first_plan = plan(planner, claim)

    assert first_plan is not None
    assert first_plan.current_layer == planner.BOUND_LOCAL

    completed = tuple(terminal_attempt(route) for route in first_plan.routes)
    resumed_plan = plan(planner, claim, attempts=completed)

    assert resumed_plan is not None
    assert resumed_plan.current_layer == planner.HIGHEST_AUTHORITY
    assert not {route.route_id for route in first_plan.routes} & {
        route.route_id for route in resumed_plan.routes
    }

    raw_accepted = (*completed, terminal_attempt(resumed_plan.routes[0], "accepted"))
    next_plan = plan(planner, claim, attempts=raw_accepted)
    assert next_plan is not None
    assert next_plan.current_layer == planner.SAME_FUNCTION_FALLBACK


def test_mismatched_ledger_claim_cannot_stop_planning() -> None:
    planner = load_planner_module()
    claim = request()

    with pytest.raises(ValueError, match="ledger claim_id"):
        plan(
            planner,
            claim,
            ledger=accepted_ledger(
                "different-claim",
                planner.request_scope_fingerprint(claim),
            ),
        )


def test_same_claim_ledger_with_mismatched_scope_cannot_stop_planning() -> None:
    planner = load_planner_module()
    claim = request()

    with pytest.raises(ValueError, match="ledger scope fingerprint"):
        plan(
            planner,
            claim,
            ledger=accepted_ledger(claim["claim_id"], SCOPE_FINGERPRINT),
        )


def test_blocked_ledger_resumes_its_earliest_remaining_route() -> None:
    planner = load_planner_module()
    claim = request(absence_claim=True)
    initial_plan = plan(planner, claim)
    assert initial_plan is not None

    next_plan = plan(
        planner,
        claim,
        ledger=blocked_ledger(
            claim,
            planner.request_scope_fingerprint(claim),
            initial_plan.applicable_routes,
        ),
    )

    assert next_plan is not None
    assert next_plan.outcome == "pending"
    assert next_plan.current_layer == planner.HIGHEST_AUTHORITY
    assert {route.route_id for route in next_plan.routes} == {
        "layer-1-official-market-data-market-size"
    }


def test_fully_blocked_inventory_returns_an_explicit_blocked_outcome() -> None:
    planner = load_planner_module()
    claim = request(absence_claim=True)
    attempts = complete_all_applicable_layers(planner, claim, "access-unavailable")

    outcome = plan(
        planner,
        claim,
        attempts=attempts,
        relations=relation_records(),
    )

    assert outcome is not None
    assert outcome.current_layer is None
    assert outcome.routes == ()
    assert outcome.outcome == "blocked"


@pytest.mark.parametrize(
    "reason",
    ("technical-failure", "access-unavailable", "request-budget-exhausted"),
)
def test_positive_terminal_failures_return_an_explicit_blocked_outcome(
    reason: str,
) -> None:
    planner = load_planner_module()
    claim = request()
    attempts = complete_all_applicable_layers(planner, claim, reason)

    outcome = plan(
        planner,
        claim,
        attempts=attempts,
        relations=relation_records(),
    )

    assert outcome is not None
    assert outcome.current_layer is None
    assert outcome.routes == ()
    assert outcome.outcome == "blocked"


def test_mismatched_gate_claim_cannot_stop_planning() -> None:
    planner = load_planner_module()
    claim = request()
    mismatched_gate = planner.GateResult(
        claim_id="different-claim",
        passed=True,
        failures=(),
        scope_fingerprint=planner.request_scope_fingerprint(claim),
    )

    with pytest.raises(ValueError, match="gate claim_id"):
        plan(planner, claim, gate_result=mismatched_gate)


def test_mismatched_gate_scope_cannot_stop_planning() -> None:
    planner = load_planner_module()
    claim = request()
    mismatched_gate = planner.GateResult(
        claim_id=claim["claim_id"],
        passed=True,
        failures=(),
        scope_fingerprint=SCOPE_FINGERPRINT,
    )

    with pytest.raises(ValueError, match="gate scope fingerprint"):
        plan(planner, claim, gate_result=mismatched_gate)
