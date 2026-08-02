"""Deterministic, evidence-gated source-discovery route planning."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from evidence_gate import GateResult, request_scope_fingerprint
from research_contracts import canonical_sha256, validate_payload
from source_profiles import RATING_RANK, RouteCandidate, select_routes

BOUND_LOCAL = 0
HIGHEST_AUTHORITY = 1
SAME_FUNCTION_FALLBACK = 2
SUBJECT_RELATIONSHIP = 3
DOCUMENT_TYPE = 4
BROAD_DYNAMIC = 5
LAYER_ORDER = (
    BOUND_LOCAL,
    HIGHEST_AUTHORITY,
    SAME_FUNCTION_FALLBACK,
    SUBJECT_RELATIONSHIP,
    DOCUMENT_TYPE,
    BROAD_DYNAMIC,
)
DOCUMENT_TYPES = (
    "prospectus",
    "listing-application",
    "industry-overview",
    "methodology-appendix",
    "association-report",
    "archive",
)
RELATION_ORDER = {
    "direct-peer": 0,
    "category-leader": 1,
    "active-listing-applicant": 2,
    "recent-listing-applicant": 3,
}
RELATION_ALIASES = {
    "peer": "direct-peer",
    "competitor": "direct-peer",
    "direct-peer": "direct-peer",
    "leader": "category-leader",
    "category-leader": "category-leader",
    "listing-applicant-active": "active-listing-applicant",
    "active-listing-applicant": "active-listing-applicant",
    "listing-applicant-recent": "recent-listing-applicant",
    "recent-listing-applicant": "recent-listing-applicant",
}
TERMINAL_REASONS = frozenset(
    {
        "accepted",
        "not-found",
        "rejected",
        "conflict",
        "access-unavailable",
        "technical-failure",
        "request-budget-exhausted",
        "not-applicable",
    }
)
EXHAUSTED_REASONS = frozenset({"not-found", "not-applicable", "rejected"})
BLOCKED_REASONS = frozenset({"technical-failure", "access-unavailable", "request-budget-exhausted"})
VOCABULARY_PATH = Path(__file__).resolve().parents[1] / "references" / "query-vocabulary.yaml"


@dataclass(frozen=True)
class PlannedRoute:
    """One executable route in a single deterministic escalation layer."""

    route_id: str
    route_layer: int
    subject: str
    subject_relation: str
    document_type: str
    definition_scope_fingerprint: str
    claim_type: str
    geographies: tuple[str, ...]
    industries: tuple[str, ...]
    query_variants: tuple[str, ...] = ()
    source_id: str | None = None
    source_function: str | None = None
    direct_url: str | None = None


@dataclass(frozen=True)
class RoutePlan:
    """The current unresolved layer for one claim."""

    claim_id: str
    current_layer: int | None
    routes: tuple[PlannedRoute, ...]
    inventory_receipt: Mapping[str, object]
    outcome: str = "pending"
    applicable_routes: tuple[PlannedRoute, ...] = ()


def plan_next_layer(
    request: Mapping[str, object],
    source_profiles: Sequence[Mapping[str, object]],
    reviewed_reachability: Mapping[str, object],
    relation_records: Sequence[Mapping[str, object]] = (),
    completed_attempts: Sequence[Mapping[str, object]] = (),
    *,
    bound_routes: Sequence[Mapping[str, object]] = (),
    source_function: str | None = None,
    gate_result: GateResult | None = None,
    ledger: Mapping[str, object] | None = None,
    now: datetime | None = None,
    vocabulary_path: Path | None = None,
) -> RoutePlan | None:
    """Return routes from only the earliest unresolved applicable layer.

    The planner is deliberately pure: callers own persistence and attempt
    creation. Positive claims stop on accepted evidence. Absence claims return
    an explicit terminal outcome only after every applicable route is terminal.
    """
    validate_payload("request", request)
    scope_fingerprint = request_scope_fingerprint(request)
    _validate_gate_binding(request, scope_fingerprint, gate_result)
    all_attempts = _all_completed_attempts(completed_attempts, ledger)
    absence_claim = request["absence_claim"]
    if not isinstance(absence_claim, bool):
        raise ValueError("absence_claim must be a boolean")
    current_time = _require_aware_now(now)
    attempted_route_ids = _terminal_route_ids(all_attempts)
    attempted_queries = _attempted_queries(all_attempts)
    vocabulary = _load_vocabulary(vocabulary_path or VOCABULARY_PATH)
    selected_source_function = source_function or _source_function(request)

    routes_by_layer = {
        BOUND_LOCAL: _bound_routes(
            request,
            bound_routes,
            scope_fingerprint,
        ),
        HIGHEST_AUTHORITY: _highest_authority_routes(
            request,
            source_profiles,
            reviewed_reachability,
            selected_source_function,
            current_time,
            scope_fingerprint,
            vocabulary,
            attempted_queries,
        ),
        SAME_FUNCTION_FALLBACK: _same_function_fallback_routes(
            request,
            source_profiles,
            reviewed_reachability,
            selected_source_function,
            current_time,
            scope_fingerprint,
            vocabulary,
            attempted_queries,
        ),
        SUBJECT_RELATIONSHIP: _relationship_routes(
            request,
            relation_records,
            scope_fingerprint,
            vocabulary,
            attempted_queries,
        ),
        DOCUMENT_TYPE: _document_type_routes(
            request,
            scope_fingerprint,
            vocabulary,
            attempted_queries,
        ),
        BROAD_DYNAMIC: _broad_dynamic_routes(
            request,
            scope_fingerprint,
            vocabulary,
            attempted_queries,
        ),
    }
    applicable_routes = tuple(route for layer in LAYER_ORDER for route in routes_by_layer[layer])
    inventory_receipt = _planner_inventory_receipt(
        request,
        source_profiles,
        reviewed_reachability,
        relation_records,
        bound_routes,
        selected_source_function,
        current_time,
        vocabulary,
        applicable_routes,
    )
    _validate_ledger_binding(
        request,
        scope_fingerprint,
        ledger,
        inventory_receipt,
    )
    if not absence_claim and _positive_claim_is_terminal(gate_result, ledger):
        return None

    for layer in LAYER_ORDER:
        unresolved_routes = tuple(
            route for route in routes_by_layer[layer] if route.route_id not in attempted_route_ids
        )
        if unresolved_routes:
            return RoutePlan(
                claim_id=_required_string(request, "claim_id"),
                current_layer=layer,
                routes=unresolved_routes,
                inventory_receipt=inventory_receipt,
                applicable_routes=applicable_routes,
            )
    return RoutePlan(
        claim_id=_required_string(request, "claim_id"),
        current_layer=None,
        routes=(),
        inventory_receipt=inventory_receipt,
        outcome=_terminal_outcome(routes_by_layer, all_attempts),
        applicable_routes=applicable_routes,
    )


def generate_query_variants(
    request: Mapping[str, object],
    document_types: Sequence[str] = (),
    *,
    definition_scope_fingerprint: str | None = None,
    attempted_queries: Sequence[str] = (),
    vocabulary_path: Path | None = None,
) -> tuple[str, ...]:
    """Create bounded multilingual discovery queries without changing scope."""
    validate_payload("request", request)
    fingerprint = request_scope_fingerprint(request)
    if definition_scope_fingerprint is not None and definition_scope_fingerprint != fingerprint:
        raise ValueError("definition scope fingerprint must match request scope fingerprint")
    vocabulary = _load_vocabulary(vocabulary_path or VOCABULARY_PATH)
    subjects = _subject_variants(request)
    metric_terms = _vocabulary_terms(vocabulary, _required_string(request, "metric"))
    requested_document_types = tuple(document_types) or ("industry-overview",)
    document_terms = tuple(
        term
        for document_type in requested_document_types
        for term in _vocabulary_terms(vocabulary, document_type)
    )
    period = _period_query(request)
    scope_terms = _scope_query_terms(request)
    attempted = {_normalize_query(query) for query in attempted_queries}
    variants: list[str] = []
    seen = set(attempted)

    for subject in subjects:
        for metric in metric_terms:
            for document in document_terms:
                query = f"{subject} {metric} {period} {document} {scope_terms} scope:{fingerprint}"
                normalized = _normalize_query(query)
                if normalized in seen:
                    continue
                seen.add(normalized)
                variants.append(query)
    return tuple(variants)


def _bound_routes(
    request: Mapping[str, object],
    bound_routes: Sequence[Mapping[str, object]],
    scope_fingerprint: str,
) -> tuple[PlannedRoute, ...]:
    subject = _required_string(request, "subject")
    claim_type, geographies, industries = _route_cache_dimensions(request)
    routes = []
    for bound_route in bound_routes:
        route_id = _required_string(bound_route, "route_id")
        routes.append(
            PlannedRoute(
                route_id=route_id,
                route_layer=BOUND_LOCAL,
                subject=subject,
                subject_relation=_optional_string(bound_route, "subject_relation", "bound-local"),
                document_type=_optional_string(bound_route, "document_type", "bound-document"),
                definition_scope_fingerprint=scope_fingerprint,
                claim_type=claim_type,
                geographies=geographies,
                industries=industries,
            )
        )
    return _unique_routes(routes)


def _highest_authority_routes(
    request: Mapping[str, object],
    profiles: Sequence[Mapping[str, object]],
    reviewed_reachability: Mapping[str, object],
    source_function: str,
    now: datetime,
    scope_fingerprint: str,
    vocabulary: Mapping[str, tuple[str, ...]],
    attempted_queries: Sequence[str],
) -> tuple[PlannedRoute, ...]:
    fallback_targets = _fallback_target_ids(profiles, source_function)
    candidates = select_routes(
        profiles,
        source_function,
        now,
        snapshot=reviewed_reachability,
        geographies=_string_labels(request, "geographies"),
        industries=_string_labels(request, "industries"),
        minimum_originality=_required_string(request, "minimum_originality"),
        minimum_independence=_required_string(request, "minimum_independence"),
    )
    direct_candidates = tuple(
        candidate
        for candidate in candidates
        if _source_route_id(candidate) not in fallback_targets
        and _authority_is_eligible(candidate, request)
    )
    return _source_candidate_routes(
        request,
        _highest_authority_tier(direct_candidates),
        HIGHEST_AUTHORITY,
        scope_fingerprint,
        vocabulary,
        attempted_queries,
    )


def _same_function_fallback_routes(
    request: Mapping[str, object],
    profiles: Sequence[Mapping[str, object]],
    reviewed_reachability: Mapping[str, object],
    source_function: str,
    now: datetime,
    scope_fingerprint: str,
    vocabulary: Mapping[str, tuple[str, ...]],
    attempted_queries: Sequence[str],
) -> tuple[PlannedRoute, ...]:
    functions = _profile_functions(profiles)
    routes = []
    for target_id in sorted(_fallback_target_ids(profiles, source_function)):
        target = functions.get(target_id)
        if target is None:
            continue
        _, function = target
        target_function = _required_string(function, "id")
        candidates = select_routes(
            profiles,
            target_function,
            now,
            snapshot=reviewed_reachability,
            geographies=_string_labels(request, "geographies"),
            industries=_string_labels(request, "industries"),
            minimum_originality=_required_string(request, "minimum_originality"),
            minimum_independence=_required_string(request, "minimum_independence"),
        )
        target_candidate = next(
            (candidate for candidate in candidates if _source_route_id(candidate) == target_id),
            None,
        )
        if target_candidate is not None:
            if not _authority_is_eligible(target_candidate, request):
                continue
            routes.extend(
                _source_candidate_routes(
                    request,
                    (target_candidate,),
                    SAME_FUNCTION_FALLBACK,
                    scope_fingerprint,
                    vocabulary,
                    attempted_queries,
                )
            )
    return _unique_routes(routes)


def _source_candidate_routes(
    request: Mapping[str, object],
    candidates: Iterable[RouteCandidate],
    layer: int,
    scope_fingerprint: str,
    vocabulary: Mapping[str, tuple[str, ...]],
    attempted_queries: Sequence[str],
) -> tuple[PlannedRoute, ...]:
    routes = []
    claim_type, geographies, industries = _route_cache_dimensions(request)
    for candidate in candidates:
        if candidate.skip_reason is not None:
            continue
        source_label = f"{candidate.source_id} {candidate.function_id}"
        routes.append(
            PlannedRoute(
                route_id=f"layer-{layer}-{candidate.source_id}-{candidate.function_id}",
                route_layer=layer,
                subject=_required_string(request, "subject"),
                subject_relation="direct",
                document_type="source-function",
                definition_scope_fingerprint=scope_fingerprint,
                claim_type=claim_type,
                geographies=geographies,
                industries=industries,
                query_variants=generate_query_variants(
                    request,
                    document_types=(source_label,),
                    definition_scope_fingerprint=scope_fingerprint,
                    attempted_queries=attempted_queries,
                    vocabulary_path=None,
                ),
                source_id=candidate.source_id,
                source_function=candidate.function_id,
                direct_url=candidate.direct_url,
            )
        )
    return _unique_routes(routes)


def _relationship_routes(
    request: Mapping[str, object],
    relation_records: Sequence[Mapping[str, object]],
    scope_fingerprint: str,
    vocabulary: Mapping[str, tuple[str, ...]],
    attempted_queries: Sequence[str],
) -> tuple[PlannedRoute, ...]:
    del vocabulary
    claim_type, geographies, industries = _route_cache_dimensions(request)
    records = []
    for record in relation_records:
        relation = record.get("relation")
        if not isinstance(relation, str):
            continue
        normalized_relation = RELATION_ALIASES.get(_normalized_text(relation))
        subject = _relation_subject(record)
        source_id = _nonblank_string(record.get("source_id"))
        source_function = _nonblank_string(record.get("source_function"))
        direct_url = _nonblank_string(record.get("direct_url"))
        if (
            normalized_relation is None
            or subject is None
            or source_id is None
            or source_function is None
            or direct_url is None
        ):
            continue
        records.append(
            (
                normalized_relation,
                subject,
                source_id,
                source_function,
                direct_url,
            )
        )

    routes = [
        PlannedRoute(
            route_id=f"layer-{SUBJECT_RELATIONSHIP}-{relation}-{_slug(subject)}",
            route_layer=SUBJECT_RELATIONSHIP,
            subject=subject,
            subject_relation=relation,
            document_type="relationship-expansion",
            definition_scope_fingerprint=scope_fingerprint,
            claim_type=claim_type,
            geographies=geographies,
            industries=industries,
            query_variants=generate_query_variants(
                {**request, "subject": subject},
                document_types=("listing-application", "industry-overview"),
                definition_scope_fingerprint=scope_fingerprint,
                attempted_queries=attempted_queries,
            ),
            source_id=source_id,
            source_function=source_function,
            direct_url=direct_url,
        )
        for relation, subject, source_id, source_function, direct_url in sorted(
            set(records),
            key=lambda item: (
                RELATION_ORDER[item[0]],
                _normalized_text(item[1]),
                item[2],
                item[3],
                item[4],
            ),
        )
    ]
    return _unique_routes(routes)


def _document_type_routes(
    request: Mapping[str, object],
    scope_fingerprint: str,
    vocabulary: Mapping[str, tuple[str, ...]],
    attempted_queries: Sequence[str],
) -> tuple[PlannedRoute, ...]:
    del vocabulary
    subject = _required_string(request, "subject")
    claim_type, geographies, industries = _route_cache_dimensions(request)
    return tuple(
        PlannedRoute(
            route_id=f"layer-{DOCUMENT_TYPE}-{document_type}",
            route_layer=DOCUMENT_TYPE,
            subject=subject,
            subject_relation="document-type-expansion",
            document_type=document_type,
            definition_scope_fingerprint=scope_fingerprint,
            claim_type=claim_type,
            geographies=geographies,
            industries=industries,
            query_variants=generate_query_variants(
                request,
                document_types=(document_type,),
                definition_scope_fingerprint=scope_fingerprint,
                attempted_queries=attempted_queries,
            ),
        )
        for document_type in DOCUMENT_TYPES
    )


def _broad_dynamic_routes(
    request: Mapping[str, object],
    scope_fingerprint: str,
    vocabulary: Mapping[str, tuple[str, ...]],
    attempted_queries: Sequence[str],
) -> tuple[PlannedRoute, ...]:
    del vocabulary
    claim_type, geographies, industries = _route_cache_dimensions(request)
    return (
        PlannedRoute(
            route_id="layer-5-broad-dynamic",
            route_layer=BROAD_DYNAMIC,
            subject=_required_string(request, "subject"),
            subject_relation="broad-dynamic",
            document_type="broad-dynamic",
            definition_scope_fingerprint=scope_fingerprint,
            claim_type=claim_type,
            geographies=geographies,
            industries=industries,
            query_variants=generate_query_variants(
                request,
                document_types=DOCUMENT_TYPES,
                definition_scope_fingerprint=scope_fingerprint,
                attempted_queries=attempted_queries,
            ),
        ),
    )


def _positive_claim_is_terminal(
    gate_result: GateResult | None,
    ledger: Mapping[str, object] | None,
) -> bool:
    if gate_result is not None and gate_result.passed:
        return True
    return ledger is not None and ledger.get("status") == "accepted"


def _validate_ledger_binding(
    request: Mapping[str, object],
    scope_fingerprint: str,
    ledger: Mapping[str, object] | None,
    inventory_receipt: Mapping[str, object],
) -> None:
    if ledger is None:
        return
    validate_payload(
        "ledger",
        ledger,
        planner_inventory_receipt=inventory_receipt,
    )
    if ledger.get("claim_id") != request.get("claim_id"):
        raise ValueError("ledger claim_id does not match the current request")
    if ledger.get("request_scope_fingerprint") != scope_fingerprint:
        raise ValueError("ledger scope fingerprint does not match the current request")
    if ledger.get("absence_claim") != request.get("absence_claim"):
        raise ValueError("ledger absence_claim does not match the current request")


def _planner_inventory_receipt(
    request: Mapping[str, object],
    source_profiles: Sequence[Mapping[str, object]],
    reviewed_reachability: Mapping[str, object],
    relation_records: Sequence[Mapping[str, object]],
    bound_routes: Sequence[Mapping[str, object]],
    source_function: str,
    current_time: datetime,
    vocabulary: Mapping[str, tuple[str, ...]],
    applicable_routes: Sequence[PlannedRoute],
) -> dict[str, object]:
    route_inventory = [
        {
            "route_id": route.route_id,
            "route_layer": route.route_layer,
            "subject_relation": route.subject_relation,
            "document_type": route.document_type,
        }
        for route in applicable_routes
    ]
    normalized_relations = _normalized_relation_inputs(relation_records)
    normalized_bound_routes = _normalized_bound_route_inputs(applicable_routes)
    planner_inputs = {
        "request_identity": {
            "claim_id": _required_string(request, "claim_id"),
            "request_scope_fingerprint": request_scope_fingerprint(request),
            "request_content_sha256": canonical_sha256(request),
        },
        "source_function": source_function,
        "maintained_profiles": [
            {
                "source_id": _required_string(profile, "id"),
                "content_sha256": canonical_sha256(profile),
            }
            for profile in sorted(
                source_profiles,
                key=lambda profile: _required_string(profile, "id"),
            )
        ],
        "relation_records": normalized_relations,
        "bound_routes": normalized_bound_routes,
        "as_of": _required_string(request, "as_of"),
        "effective_planning_time": current_time.isoformat(),
        "vocabulary_identity": {
            "content_sha256": canonical_sha256(
                {key: list(values) for key, values in sorted(vocabulary.items())}
            )
        },
        "reachability_identity": {"content_sha256": canonical_sha256(reviewed_reachability)},
        "route_inventory_sha256": canonical_sha256(route_inventory),
    }
    content = {
        "schema_version": "1.0",
        "claim_id": _required_string(request, "claim_id"),
        "request_scope_fingerprint": request_scope_fingerprint(request),
        "planner_inputs": planner_inputs,
        "planner_input_fingerprint": canonical_sha256(planner_inputs),
        "route_inventory": route_inventory,
    }
    receipt = {
        **content,
        "content_sha256": canonical_sha256(content),
    }
    validate_payload("planner-inventory-receipt", receipt)
    return receipt


def _normalized_relation_inputs(
    relation_records: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    normalized: set[tuple[str, str, str, str, str]] = set()
    for record in relation_records:
        relation = record.get("relation")
        subject = _relation_subject(record)
        source_id = _nonblank_string(record.get("source_id"))
        source_function = _nonblank_string(record.get("source_function"))
        direct_url = _nonblank_string(record.get("direct_url"))
        normalized_relation = (
            RELATION_ALIASES.get(_normalized_text(relation)) if isinstance(relation, str) else None
        )
        if (
            normalized_relation is None
            or subject is None
            or source_id is None
            or source_function is None
            or direct_url is None
        ):
            continue
        normalized.add(
            (
                normalized_relation,
                subject,
                source_id,
                source_function,
                direct_url,
            )
        )

    inputs = []
    for relation, subject, source_id, source_function, direct_url in sorted(
        normalized,
        key=lambda item: (
            RELATION_ORDER[item[0]],
            _normalized_text(item[1]),
            item[2],
            item[3],
            item[4],
        ),
    ):
        source_binding = {
            "source_id": source_id,
            "source_function": source_function,
            "direct_url": direct_url,
        }
        inputs.append(
            {
                "subject": subject,
                "relation": relation,
                **source_binding,
                "source_binding_sha256": canonical_sha256(source_binding),
            }
        )
    return inputs


def _normalized_bound_route_inputs(
    applicable_routes: Sequence[PlannedRoute],
) -> list[dict[str, object]]:
    inputs = []
    for route in applicable_routes:
        if route.route_layer != BOUND_LOCAL:
            continue
        route_binding = {
            "route_id": route.route_id,
            "subject_relation": route.subject_relation,
            "document_type": route.document_type,
        }
        inputs.append(
            {
                **route_binding,
                "route_binding_sha256": canonical_sha256(route_binding),
            }
        )
    return inputs


def _validate_gate_binding(
    request: Mapping[str, object],
    scope_fingerprint: str,
    gate_result: GateResult | None,
) -> None:
    if gate_result is None:
        return
    if gate_result.claim_id != request.get("claim_id"):
        raise ValueError("gate claim_id does not match the current request")
    if gate_result.scope_fingerprint != scope_fingerprint:
        raise ValueError("gate scope fingerprint does not match the current request")


def _all_completed_attempts(
    completed_attempts: Sequence[Mapping[str, object]],
    ledger: Mapping[str, object] | None,
) -> tuple[Mapping[str, object], ...]:
    ledger_attempts = ledger.get("attempts") if ledger is not None else ()
    if not isinstance(ledger_attempts, Sequence) or isinstance(ledger_attempts, (str, bytes)):
        ledger_attempts = ()
    return tuple(
        attempt
        for attempt in (*completed_attempts, *ledger_attempts)
        if isinstance(attempt, Mapping)
    )


def _terminal_outcome(
    routes_by_layer: Mapping[int, Sequence[PlannedRoute]],
    completed_attempts: Sequence[Mapping[str, object]],
) -> str:
    applicable_route_ids = {
        route.route_id for routes in routes_by_layer.values() for route in routes
    }
    terminal_reasons_by_route: dict[str, set[str]] = {}
    for attempt in completed_attempts:
        route_id = attempt.get("route_id")
        terminal_reason = attempt.get("terminal_reason")
        if (
            isinstance(route_id, str)
            and route_id in applicable_route_ids
            and isinstance(terminal_reason, str)
            and terminal_reason in TERMINAL_REASONS
        ):
            terminal_reasons_by_route.setdefault(route_id, set()).add(terminal_reason)

    reasons = {
        reason for route_reasons in terminal_reasons_by_route.values() for reason in route_reasons
    }
    if reasons & BLOCKED_REASONS:
        return "blocked"
    if reasons and reasons <= EXHAUSTED_REASONS:
        return "exhausted"
    return "unresolved"


def _terminal_route_ids(
    completed_attempts: Sequence[Mapping[str, object]],
) -> frozenset[str]:
    return frozenset(
        route_id
        for attempt in completed_attempts
        if attempt.get("terminal_reason") in TERMINAL_REASONS
        and isinstance(route_id := attempt.get("route_id"), str)
    )


def _attempted_queries(
    completed_attempts: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    return tuple(
        query
        for attempt in completed_attempts
        if isinstance(query := attempt.get("query_variant"), str)
    )


def _source_function(request: Mapping[str, object]) -> str:
    configured = request.get("source_function")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return _required_string(request, "claim_type")


def _fallback_target_ids(
    profiles: Sequence[Mapping[str, object]],
    source_function: str,
) -> frozenset[str]:
    functions = _profile_functions(profiles)
    root_ids = {
        route_id
        for route_id, (_, function) in functions.items()
        if function.get("id") == source_function
    }
    targets = set()
    visited = set(root_ids)
    pending = sorted(root_ids)
    while pending:
        route_id = pending.pop(0)
        _, function = functions[route_id]
        fallbacks = function.get("fallbacks")
        if not isinstance(fallbacks, list):
            continue
        for fallback in fallbacks:
            if not isinstance(fallback, str) or fallback not in functions:
                continue
            targets.add(fallback)
            if fallback not in visited:
                visited.add(fallback)
                pending.append(fallback)
    return frozenset(targets)


def _profile_functions(
    profiles: Sequence[Mapping[str, object]],
) -> dict[str, tuple[Mapping[str, object], Mapping[str, object]]]:
    functions = {}
    for profile in profiles:
        source_id = profile.get("id")
        profile_functions = profile.get("functions")
        if not isinstance(source_id, str) or not isinstance(profile_functions, list):
            continue
        for function in profile_functions:
            if not isinstance(function, Mapping):
                continue
            function_id = function.get("id")
            if isinstance(function_id, str):
                functions[f"{source_id}-{function_id}"] = (profile, function)
    return functions


def _source_route_id(candidate: RouteCandidate) -> str:
    return f"{candidate.source_id}-{candidate.function_id}"


def _load_vocabulary(path: Path) -> dict[str, tuple[str, ...]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: vocabulary must be a mapping")

    vocabulary: dict[str, tuple[str, ...]] = {}
    for key, aliases in payload.items():
        if not isinstance(key, str) or not isinstance(aliases, list):
            raise ValueError(f"{path}: vocabulary entries must map strings to lists")
        terms = tuple(alias for alias in aliases if isinstance(alias, str) and alias.strip())
        if not terms:
            raise ValueError(f"{path}: vocabulary entry {key!r} has no aliases")
        vocabulary[_normalized_text(key)] = terms
    return vocabulary


def _vocabulary_terms(
    vocabulary: Mapping[str, tuple[str, ...]],
    label: str,
) -> tuple[str, ...]:
    normalized_label = _normalized_text(label)
    if normalized_label in vocabulary:
        return vocabulary[normalized_label]

    for key, terms in vocabulary.items():
        if key in normalized_label or any(
            _normalized_text(term) in normalized_label for term in terms
        ):
            return terms
    return (label,)


def _subject_variants(request: Mapping[str, object]) -> tuple[str, ...]:
    aliases = [*_string_labels(request, "subject_aliases"), _required_string(request, "subject")]
    return tuple(dict.fromkeys(alias for alias in aliases if alias.strip()))


def _period_query(request: Mapping[str, object]) -> str:
    start = _required_string(request, "period_start")
    end = _required_string(request, "period_end")
    return start if start == end else f"{start} {end}"


def _scope_query_terms(request: Mapping[str, object]) -> str:
    return " ".join(
        (
            *_string_labels(request, "geographies"),
            *_string_labels(request, "industries"),
            _required_string(request, "population"),
            _required_string(request, "product_scope"),
            _required_string(request, "measurement_basis"),
            *_definition_constraint_query_terms(request),
        )
    )


def _definition_constraint_query_terms(request: Mapping[str, object]) -> tuple[str, ...]:
    constraints = request.get("definition_constraints")
    if not isinstance(constraints, list):
        return ()
    nonblank_constraints = (
        constraint.strip()
        for constraint in constraints
        if isinstance(constraint, str) and constraint.strip()
    )
    return (
        "definition_constraints",
        *sorted(nonblank_constraints, key=_normalized_text),
    )


def _string_labels(request: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = request.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _route_cache_dimensions(
    request: Mapping[str, object],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    return (
        _normalized_text(_required_string(request, "claim_type")),
        tuple(
            sorted({_normalized_text(label) for label in _string_labels(request, "geographies")})
        ),
        tuple(sorted({_normalized_text(label) for label in _string_labels(request, "industries")})),
    )


def _relation_subject(record: Mapping[str, object]) -> str | None:
    for key in ("related_subject", "subject", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _nonblank_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _unique_routes(routes: Sequence[PlannedRoute]) -> tuple[PlannedRoute, ...]:
    return tuple({route.route_id: route for route in routes}.values())


def _normalize_query(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _normalized_text(value: object) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _authority_is_eligible(
    candidate: RouteCandidate,
    request: Mapping[str, object],
) -> bool:
    minimum_authority = _required_string(request, "minimum_source_authority")
    return RATING_RANK[candidate.authority] >= RATING_RANK[minimum_authority]


def _highest_authority_tier(
    candidates: Sequence[RouteCandidate],
) -> tuple[RouteCandidate, ...]:
    if not candidates:
        return ()
    highest_rank = max(RATING_RANK[candidate.authority] for candidate in candidates)
    return tuple(
        candidate for candidate in candidates if RATING_RANK[candidate.authority] == highest_rank
    )


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalized_text(value)).strip("-")
    if normalized:
        return normalized
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _required_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing string field: {key}")
    return value.strip()


def _optional_string(mapping: Mapping[str, object], key: str, default: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _require_aware_now(now: datetime | None) -> datetime:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return current_time
