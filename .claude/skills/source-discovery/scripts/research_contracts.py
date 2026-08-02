"""Load and validate the shared source-discovery research contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from source_lineage import lineage_id

REFERENCES_DIR = Path(__file__).resolve().parents[1] / "references"
SCHEMA_FILENAMES = {
    "research-request": "research-request.schema.json",
    "candidate-claim": "candidate-claim.schema.json",
    "research-ledger": "research-ledger.schema.json",
    "planner-inventory-receipt": "planner-inventory-receipt.schema.json",
    "route-cache": "route-cache.schema.json",
    "industry-analysis-bundle": "industry-analysis-bundle.schema.json",
}
SCHEMA_ALIASES = {
    "request": "research-request",
    "candidate": "candidate-claim",
    "ledger": "research-ledger",
    "industry-bundle": "industry-analysis-bundle",
}
PERIOD_SEMANTICS = {
    "annual": "calendar-year",
    "quarterly": "calendar-quarter",
    "monthly": "calendar-month",
    "event-driven": "event-date",
}
PERIOD_PATTERNS = {
    "annual": re.compile(r"^\d{4}$"),
    "quarterly": re.compile(r"^\d{4}-Q[1-4]$"),
    "monthly": re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"),
    "event-driven": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
}
READ_FILING_OWNED_GOVERNANCE_CLASSES = frozenset(
    {"official-regulator", "official-exchange", "official-court"}
)


def load_schema(name: str) -> dict[str, object]:
    """Load one versioned research contract by canonical name or short alias."""
    canonical_name = _canonical_schema_name(name)
    path = REFERENCES_DIR / SCHEMA_FILENAMES[canonical_name]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {canonical_name} schema: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{canonical_name} schema must be a JSON object")
    Draft202012Validator.check_schema(payload)
    return payload


def validate_payload(
    schema_name: str,
    payload: Mapping[str, object],
    *,
    planner_inventory_receipt: Mapping[str, object] | None = None,
) -> None:
    """Validate a contract payload and its ledger state invariants."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")

    canonical_name = _canonical_schema_name(schema_name)
    validator = Draft202012Validator(load_schema(canonical_name), format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ValueError(f"{canonical_name} violates schema at {location}: {error.message}")

    if canonical_name == "research-request":
        _validate_request(payload)
    elif canonical_name == "candidate-claim":
        _validate_candidate(payload)
    elif canonical_name == "research-ledger":
        _validate_ledger(payload, planner_inventory_receipt)
    elif canonical_name == "planner-inventory-receipt":
        _validate_planner_inventory_receipt(payload)


def _canonical_schema_name(name: str) -> str:
    canonical_name = SCHEMA_ALIASES.get(name, name)
    if canonical_name not in SCHEMA_FILENAMES:
        supported = ", ".join(sorted(SCHEMA_FILENAMES))
        raise ValueError(f"unsupported schema name: {name}; expected one of: {supported}")
    return canonical_name


def _validate_request(payload: Mapping[str, object]) -> None:
    claim_type = _required_string(payload, "claim_type")
    accepted_source_classes = set(_optional_strings(payload, "accepted_source_classes"))
    forbidden_governance_classes = accepted_source_classes & READ_FILING_OWNED_GOVERNANCE_CLASSES
    if claim_type == "governance-event" and forbidden_governance_classes:
        forbidden = ", ".join(sorted(forbidden_governance_classes))
        raise ValueError(
            "governance-event requests cannot accept "
            f"{forbidden}; official governance evidence remains read-filing owned"
        )


def _validate_ledger(
    payload: Mapping[str, object],
    planner_inventory_receipt: Mapping[str, object] | None,
) -> None:
    status = _required_string(payload, "status")
    attempts = _required_mappings(payload, "attempts")
    applicable_routes = _required_mappings(payload, "applicable_routes")
    acceptance_failures = _required_sequence(payload, "acceptance_failures")
    gate = _required_mapping(payload, "gate")
    next_escalation = payload["next_escalation"]
    skipped_after_acceptance = _required_mappings(payload, "skipped_after_acceptance")
    unattempted_routes = _required_mappings(payload, "unattempted_routes")
    _require_planner_route_inventory(
        payload,
        applicable_routes,
        planner_inventory_receipt,
    )

    if status == "accepted" and acceptance_failures:
        raise ValueError("accepted claim cannot retain acceptance failures")
    if status == "accepted":
        _require_accepted_ledger(
            applicable_routes,
            attempts,
            gate,
            payload["accepted_evidence"],
            next_escalation,
            skipped_after_acceptance,
            absence_claim=bool(payload["absence_claim"]),
        )
    if status == "exhausted":
        _require_exhausted_ledger(gate, payload["accepted_evidence"], next_escalation)
    if status in {"blocked", "conflict"}:
        _require_unresolved_ledger(
            applicable_routes,
            attempts,
            gate,
            next_escalation,
            unattempted_routes,
            status == "blocked",
        )
    if status == "conflict":
        _require_conflict_ledger(attempts, payload["conflict_evidence"])
    if status == "blocked":
        _require_blocked_routes(applicable_routes, unattempted_routes, next_escalation)
    if status == "exhausted":
        _require_exhausted_routes_terminal(
            applicable_routes,
            attempts,
            unattempted_routes,
            absence_claim=bool(payload["absence_claim"]),
        )
    if status != "blocked" and unattempted_routes:
        raise ValueError("only blocked claims can retain unattempted routes")
    if status != "accepted" and skipped_after_acceptance:
        raise ValueError("only accepted claims can retain skipped-after-acceptance routes")


def _require_exhausted_routes_terminal(
    applicable_routes: Sequence[Mapping[str, object]],
    attempts: Sequence[Mapping[str, object]],
    unattempted_routes: Sequence[Mapping[str, object]],
    *,
    absence_claim: bool,
) -> None:
    if unattempted_routes:
        raise ValueError("all applicable routes must be terminal: routes remain unattempted")

    applicable_route_ids = _unique_route_ids(applicable_routes, "applicable route inventory")
    attempted_route_ids = {_required_string(attempt, "route_id") for attempt in attempts}
    if attempted_route_ids != applicable_route_ids:
        raise ValueError("exhaustion does not cover every applicable route")

    allowed_reasons = {"not-found", "not-applicable"}
    if not absence_claim:
        allowed_reasons.add("rejected")
    for attempt in attempts:
        terminal_reason = _required_string(attempt, "terminal_reason")
        if terminal_reason in {
            "technical-failure",
            "request-budget-exhausted",
            "access-unavailable",
        }:
            raise ValueError(f"claim with {terminal_reason} must be blocked")
        if terminal_reason not in allowed_reasons:
            if not absence_claim:
                raise ValueError(
                    "positive exhaustion requires not-found, not-applicable, "
                    "or rejected terminal outcomes"
                )
            raise ValueError(
                "absence exhaustion requires not-found or not-applicable terminal outcomes"
            )


def _validate_candidate(payload: Mapping[str, object]) -> None:
    canonical_unit = _required_string(payload, "canonical_unit")
    canonical_scope = _required_string(payload, "scope_fingerprint")
    frequency = _required_string(payload, "frequency")
    period_semantics = _required_string(payload, "period_semantics")
    values = _required_mappings(payload, "values")
    reconciliations = _required_mappings(payload, "reconciliations")
    _validate_candidate_identity(payload)
    if _required_string(payload, "lineage_id") != lineage_id(payload):
        raise ValueError("candidate lineage_id does not match normalized provenance")
    _validate_period_semantics(frequency, period_semantics, values)
    reconciliations_by_id = _reconciliations_by_id(reconciliations)
    is_event_driven = frequency == "event-driven"
    if is_event_driven:
        _required_string(_required_mapping(payload, "source"), "source_class")
    seen_event_keys: set[str] = set()
    seen_evidence_ids: set[str] = set()

    for value in values:
        period = _required_string(value, "period")
        if not PERIOD_PATTERNS[frequency].fullmatch(period):
            raise ValueError("candidate period does not match its frequency semantics")
        if is_event_driven:
            # event_key is the normalized cross-source event identity, while
            # evidence_id remains the source-specific record identity.
            event_key = _required_string(value, "event_key")
            if event_key in seen_event_keys:
                raise ValueError("event-driven candidate event_key values must be unique")
            seen_event_keys.add(event_key)
            evidence_id = _required_string(value, "evidence_id")
            if evidence_id in seen_evidence_ids:
                raise ValueError("event-driven candidate evidence_id values must be unique")
            seen_evidence_ids.add(evidence_id)
        value_pair = (
            _required_string(value, "unit"),
            _required_string(value, "definition_scope_fingerprint"),
        )
        source_value = value.get("value")
        canonical_value = _required_mapping(value, "canonical_value")
        canonical_pair = (
            _required_string(canonical_value, "unit"),
            _required_string(canonical_value, "definition_scope_fingerprint"),
        )
        canonical_scalar = canonical_value.get("value")
        if not _supports_value_type(source_value, allow_text=is_event_driven):
            raise ValueError("candidate value type is invalid for its frequency")
        if not _supports_value_type(canonical_scalar, allow_text=is_event_driven):
            raise ValueError("candidate canonical value type is invalid for its frequency")
        if canonical_pair != (canonical_unit, canonical_scope):
            raise ValueError("candidate canonical value must use the canonical unit and scope")
        reconciliation_id = canonical_value.get("reconciliation_id")
        if value_pair == (canonical_unit, canonical_scope):
            if reconciliation_id is not None:
                raise ValueError("canonical candidate value cannot declare a reconciliation")
            if canonical_scalar != source_value:
                raise ValueError("canonical candidate value must match the source value")
            continue
        if not isinstance(reconciliation_id, str):
            raise ValueError(
                "candidate values with mixed unit or definition require a reproducible reconciliation"
            )
        reconciliation = reconciliations_by_id.get(reconciliation_id)
        if reconciliation is None:
            raise ValueError("candidate canonical value must reference a declared reconciliation")
        if _reconciliation_covers_pair(
            reconciliation,
            value_pair,
            (canonical_unit, canonical_scope),
        ):
            continue
        if _reconciliation_covers_pair(
            reconciliation,
            (canonical_unit, canonical_scope),
            value_pair,
        ):
            raise ValueError(
                "candidate reconciliation must map divergent values into the canonical pair"
            )
        raise ValueError(
            "candidate values with mixed unit or definition require a reproducible reconciliation"
        )


def _validate_candidate_identity(payload: Mapping[str, object]) -> None:
    source = _required_mapping(payload, "source")
    document = _required_mapping(payload, "document")
    artifact = _required_mapping(payload, "artifact")
    identity = _required_mapping(payload, "source_document_identity")
    artifact_sha256 = _required_string(artifact, "sha256")
    if _required_string(artifact, "identity") != f"sha256:{artifact_sha256}":
        raise ValueError("candidate artifact identity must bind to its SHA-256")

    expected_evidence = {
        "source_canonical_url": _required_string(source, "canonical_url"),
        "document_canonical_url": _required_string(document, "canonical_url"),
        "document_id": _required_string(document, "document_id"),
        "artifact_sha256": artifact_sha256,
    }
    if any(identity.get(key) != value for key, value in expected_evidence.items()):
        raise ValueError(
            "candidate identity evidence does not match source, document, and artifact"
        )
    canonical = json.dumps(
        expected_evidence,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    binding_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if identity.get("binding_sha256") != binding_sha256:
        raise ValueError("candidate identity binding does not match its evidence")


def _validate_period_semantics(
    frequency: str,
    period_semantics: str,
    values: Sequence[Mapping[str, object]],
) -> None:
    expected_semantics = PERIOD_SEMANTICS.get(frequency)
    if expected_semantics != period_semantics:
        raise ValueError("candidate period semantics do not match its frequency")
    if frequency not in PERIOD_PATTERNS:
        raise ValueError("candidate frequency is unsupported")
    if any(
        not PERIOD_PATTERNS[frequency].fullmatch(_required_string(value, "period"))
        for value in values
    ):
        raise ValueError("candidate period does not match its frequency semantics")


def _supports_value_type(value: object, *, allow_text: bool) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) or (allow_text and isinstance(value, str) and value)


def _reconciliations_by_id(
    reconciliations: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    by_id: dict[str, Mapping[str, object]] = {}
    for reconciliation in reconciliations:
        reconciliation_id = _required_string(reconciliation, "reconciliation_id")
        if reconciliation_id in by_id:
            raise ValueError("candidate reconciliation IDs must be unique")
        artifact_sha256 = _required_string(reconciliation, "artifact_sha256")
        if _required_string(reconciliation, "artifact_identity") != f"sha256:{artifact_sha256}":
            raise ValueError("candidate reconciliation supporting artifact is not reproducible")
        by_id[reconciliation_id] = reconciliation
    return by_id


def _require_accepted_ledger(
    applicable_routes: Sequence[Mapping[str, object]],
    attempts: Sequence[Mapping[str, object]],
    gate: Mapping[str, object],
    accepted_evidence: object,
    next_escalation: object,
    skipped_after_acceptance: Sequence[Mapping[str, object]],
    *,
    absence_claim: bool,
) -> None:
    if _required_string(gate, "outcome") != "passed":
        raise ValueError("accepted ledger requires a passed gate")
    if _required_sequence(gate, "failures"):
        raise ValueError("accepted ledger cannot retain gate failures")
    if next_escalation is not None:
        raise ValueError("accepted ledger cannot retain next escalation routes")
    if not isinstance(accepted_evidence, Mapping):
        raise ValueError("accepted ledger requires accepted evidence reference")

    artifact_identity = _required_string(accepted_evidence, "artifact_identity")
    lineage_id = _required_string(accepted_evidence, "lineage_id")
    accepted_attempts = [
        attempt
        for attempt in attempts
        if _required_string(attempt, "terminal_reason") == "accepted"
    ]
    if not accepted_attempts:
        raise ValueError("accepted ledger requires an accepted attempt outcome")
    if not any(
        _required_string(attempt, "artifact_identity") == artifact_identity
        and _required_string(attempt, "lineage_id") == lineage_id
        for attempt in accepted_attempts
    ):
        raise ValueError("accepted ledger evidence must reference an accepted attempt")
    accepted_completed_at = min(
        _completed_at(attempt)
        for attempt in accepted_attempts
        if _required_string(attempt, "artifact_identity") == artifact_identity
        and _required_string(attempt, "lineage_id") == lineage_id
    )
    if any(_completed_at(attempt) > accepted_completed_at for attempt in attempts):
        raise ValueError("accepted ledger records an attempt completed after accepted attempt")

    applicable_route_ids = _unique_route_ids(applicable_routes, "applicable route inventory")
    attempted_route_ids = {_required_string(attempt, "route_id") for attempt in attempts}
    skipped_route_ids = _unique_route_ids(
        skipped_after_acceptance,
        "skipped-after-acceptance routes",
    )
    if not attempted_route_ids <= applicable_route_ids:
        raise ValueError("accepted ledger records attempts outside applicable routes")
    if not skipped_route_ids <= applicable_route_ids:
        raise ValueError("accepted ledger skips routes outside applicable routes")
    if attempted_route_ids & skipped_route_ids:
        raise ValueError("accepted ledger cannot both attempt and skip a route")
    if absence_claim:
        if skipped_after_acceptance:
            raise ValueError("accepted absence ledger cannot skip routes")
        if attempted_route_ids != applicable_route_ids:
            raise ValueError("accepted absence ledger does not cover every applicable route")
        for attempt in attempts:
            if _required_string(attempt, "terminal_reason") in {
                "technical-failure",
                "request-budget-exhausted",
                "access-unavailable",
            }:
                raise ValueError("accepted absence ledger cannot use blocked terminal outcomes")
    if attempted_route_ids | skipped_route_ids != applicable_route_ids:
        raise ValueError("accepted ledger leaves applicable routes as remaining work")


def _require_exhausted_ledger(
    gate: Mapping[str, object],
    accepted_evidence: object,
    next_escalation: object,
) -> None:
    if _required_string(gate, "outcome") != "failed":
        raise ValueError("exhausted ledger requires a failed gate")
    if accepted_evidence is not None:
        raise ValueError("exhausted ledger cannot retain accepted evidence")
    if next_escalation is not None:
        raise ValueError("exhausted ledger cannot retain next escalation routes")


def _require_unresolved_ledger(
    applicable_routes: Sequence[Mapping[str, object]],
    attempts: Sequence[Mapping[str, object]],
    gate: Mapping[str, object],
    next_escalation: object,
    unattempted_routes: Sequence[Mapping[str, object]],
    terminal_blocked_allowed: bool,
) -> None:
    if _required_string(gate, "outcome") != "unresolved":
        raise ValueError("unresolved ledger cannot present gate success")
    applicable_route_ids = _unique_route_ids(applicable_routes, "applicable route inventory")
    attempted_route_ids = {_required_string(attempt, "route_id") for attempt in attempts}
    if next_escalation is None:
        if (
            terminal_blocked_allowed
            and not unattempted_routes
            and attempted_route_ids == applicable_route_ids
        ):
            return
        raise ValueError("unresolved ledger requires next escalation")
    if not isinstance(next_escalation, Mapping):
        raise ValueError("unresolved ledger next escalation must be an object or null")
    route_ids = _required_sequence(next_escalation, "route_ids")
    if not route_ids:
        raise ValueError("unresolved ledger requires next escalation routes")
    if not all(isinstance(route_id, str) for route_id in route_ids):
        raise ValueError("unresolved ledger next escalation routes must be strings")

    next_route_ids = set(route_ids)
    if not next_route_ids <= applicable_route_ids:
        raise ValueError("unresolved next escalation routes must be a subset of applicable routes")
    if next_route_ids & attempted_route_ids:
        raise ValueError("unresolved next escalation route is already terminal")


def _require_conflict_ledger(
    attempts: Sequence[Mapping[str, object]],
    conflict_evidence: object,
) -> None:
    if not attempts:
        raise ValueError("conflict ledger requires recorded attempts")
    if not isinstance(conflict_evidence, Mapping):
        raise ValueError("conflict ledger requires structured evidence")

    left = _required_mapping(conflict_evidence, "left")
    right = _required_mapping(conflict_evidence, "right")
    if _conflict_side_identity(left) == _conflict_side_identity(right):
        raise ValueError("conflict evidence sides must be distinct")
    _validate_textual_conflict(left, right)

    attempted_evidence = {
        (
            _required_string(attempt, "artifact_identity"),
            _required_string(attempt, "lineage_id"),
        )
        for attempt in attempts
    }
    for side in (left, right):
        if (
            _required_string(side, "artifact_identity"),
            _required_string(side, "lineage_id"),
        ) not in attempted_evidence:
            raise ValueError("conflict evidence must reference recorded attempts")


def _require_blocked_routes(
    applicable_routes: Sequence[Mapping[str, object]],
    unattempted_routes: Sequence[Mapping[str, object]],
    next_escalation: object,
) -> None:
    applicable_route_ids = _unique_route_ids(applicable_routes, "applicable route inventory")
    applicable_route_layers = {
        _required_string(route, "route_id"): _required_integer(route, "route_layer")
        for route in applicable_routes
    }
    unattempted_route_ids = _unique_route_ids(unattempted_routes, "unattempted routes")
    if not unattempted_route_ids <= applicable_route_ids:
        raise ValueError("blocked ledger preserves routes outside the applicable route inventory")
    for route in unattempted_routes:
        route_id = _required_string(route, "route_id")
        if _required_integer(route, "route_layer") != applicable_route_layers[route_id]:
            raise ValueError("blocked ledger unattempted route layer must match applicable route")
    if not unattempted_route_ids:
        if next_escalation is not None:
            raise ValueError("terminal blocked ledger cannot retain next escalation")
        return
    if not isinstance(next_escalation, Mapping):
        raise ValueError("unresolved ledger requires next escalation")
    next_route_ids = set(_required_sequence(next_escalation, "route_ids"))
    if next_route_ids != unattempted_route_ids:
        raise ValueError("blocked ledger next escalation must preserve unattempted routes")
    if _required_integer(next_escalation, "next_layer") != min(
        applicable_route_layers[route_id] for route_id in next_route_ids
    ):
        raise ValueError("blocked ledger next escalation layer must be the earliest route layer")


def _reconciliation_covers_pair(
    reconciliation: Mapping[str, object],
    value_pair: tuple[str, str],
    canonical_pair: tuple[str, str],
) -> bool:
    from_pair = (
        _required_string(reconciliation, "from_unit"),
        _required_string(reconciliation, "from_scope_fingerprint"),
    )
    to_pair = (
        _required_string(reconciliation, "to_unit"),
        _required_string(reconciliation, "to_scope_fingerprint"),
    )
    return from_pair == value_pair and to_pair == canonical_pair


def _conflict_side_identity(
    side: Mapping[str, object],
) -> tuple[str, str, float | str, str, str, str, str, str]:
    value = side["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)) or value == "":
        raise ValueError("conflict evidence value must be numeric or nonempty text")
    return (
        _required_string(side, "definition_scope_fingerprint"),
        _required_string(side, "unit"),
        float(value) if isinstance(value, (int, float)) else value,
        _required_string(side, "value_status"),
        _required_string(side, "artifact_identity"),
        _required_string(side, "lineage_id"),
        _optional_string(side, "event_key"),
        _optional_string(side, "evidence_id"),
    )


def _validate_textual_conflict(
    left: Mapping[str, object],
    right: Mapping[str, object],
) -> None:
    left_is_text = isinstance(left.get("value"), str)
    right_is_text = isinstance(right.get("value"), str)
    if not left_is_text and not right_is_text:
        return
    if left_is_text != right_is_text:
        raise ValueError("conflict evidence sides must use the same value type")
    if _required_string(left, "event_key") != _required_string(right, "event_key"):
        raise ValueError("text conflict evidence sides must reference the same event_key")
    left_source = (
        _required_string(left, "artifact_identity"),
        _required_string(left, "lineage_id"),
        _required_string(left, "evidence_id"),
    )
    right_source = (
        _required_string(right, "artifact_identity"),
        _required_string(right, "lineage_id"),
        _required_string(right, "evidence_id"),
    )
    if left_source == right_source:
        raise ValueError("text conflict evidence sides require distinct source identity")


def _require_planner_route_inventory(
    ledger: Mapping[str, object],
    applicable_routes: Sequence[Mapping[str, object]],
    planner_inventory_receipt: Mapping[str, object] | None,
) -> None:
    if planner_inventory_receipt is None:
        raise ValueError("ledger validation requires a planner inventory receipt")
    validate_payload("planner-inventory-receipt", planner_inventory_receipt)
    if planner_inventory_receipt.get("claim_id") != ledger.get("claim_id"):
        raise ValueError("ledger claim_id does not match planner inventory receipt")
    if planner_inventory_receipt.get("request_scope_fingerprint") != ledger.get(
        "request_scope_fingerprint"
    ):
        raise ValueError("ledger scope fingerprint does not match planner inventory receipt")
    receipt_routes = _required_mappings(
        planner_inventory_receipt,
        "route_inventory",
    )
    ledger_inventory = tuple(_route_identity(route) for route in applicable_routes)
    planner_inventory = tuple(_route_identity(route) for route in receipt_routes)
    if ledger_inventory != planner_inventory:
        raise ValueError("ledger applicable routes does not match planner route inventory")


def _validate_planner_inventory_receipt(payload: Mapping[str, object]) -> None:
    route_inventory = _required_mappings(payload, "route_inventory")
    _unique_route_ids(route_inventory, "planner route inventory")
    planner_inputs = _required_mapping(payload, "planner_inputs")
    recorded_input_fingerprint = _required_string(
        payload,
        "planner_input_fingerprint",
    )
    if recorded_input_fingerprint != canonical_sha256(planner_inputs):
        raise ValueError("planner input fingerprint does not match planner_inputs")
    if _required_string(
        planner_inputs,
        "route_inventory_sha256",
    ) != canonical_sha256(route_inventory):
        raise ValueError("planner input route inventory SHA-256 mismatch")

    request_identity = _required_mapping(planner_inputs, "request_identity")
    if _required_string(request_identity, "claim_id") != _required_string(
        payload,
        "claim_id",
    ):
        raise ValueError("planner input claim_id does not match receipt")
    if _required_string(
        request_identity,
        "request_scope_fingerprint",
    ) != _required_string(payload, "request_scope_fingerprint"):
        raise ValueError("planner input request scope does not match receipt")

    maintained_profiles = _required_mappings(
        planner_inputs,
        "maintained_profiles",
    )
    profile_ids = [_required_string(profile, "source_id") for profile in maintained_profiles]
    if profile_ids != sorted(profile_ids) or len(profile_ids) != len(set(profile_ids)):
        raise ValueError("planner input maintained profiles must be unique and sorted")

    relation_records = _required_mappings(planner_inputs, "relation_records")
    for relation in relation_records:
        source_binding = {
            "source_id": _required_string(relation, "source_id"),
            "source_function": _required_string(relation, "source_function"),
            "direct_url": _required_string(relation, "direct_url"),
        }
        if _required_string(
            relation,
            "source_binding_sha256",
        ) != canonical_sha256(source_binding):
            raise ValueError("planner relation source binding SHA-256 mismatch")

    bound_routes = _required_mappings(planner_inputs, "bound_routes")
    bound_route_ids = [_required_string(route, "route_id") for route in bound_routes]
    if len(bound_route_ids) != len(set(bound_route_ids)):
        raise ValueError("planner input bound routes contain duplicate route IDs")
    for route in bound_routes:
        route_binding = {
            "route_id": _required_string(route, "route_id"),
            "subject_relation": _required_string(route, "subject_relation"),
            "document_type": _required_string(route, "document_type"),
        }
        if _required_string(
            route,
            "route_binding_sha256",
        ) != canonical_sha256(route_binding):
            raise ValueError("planner bound route binding SHA-256 mismatch")

    recorded_sha256 = _required_string(payload, "content_sha256")
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    if recorded_sha256 != canonical_sha256(content):
        raise ValueError("planner inventory receipt content SHA-256 mismatch")


def canonical_sha256(value: object) -> str:
    """Return the canonical JSON SHA-256 used by planner-owned receipts."""
    try:
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value is not canonical JSON: {exc}") from exc
    return hashlib.sha256(canonical).hexdigest()


def _route_identity(route: Mapping[str, object]) -> tuple[str, int, str, str]:
    return (
        _required_string(route, "route_id"),
        _required_integer(route, "route_layer"),
        _required_string(route, "subject_relation"),
        _required_string(route, "document_type"),
    )


def _completed_at(attempt: Mapping[str, object]) -> datetime:
    try:
        return datetime.fromisoformat(_required_string(attempt, "completed_at"))
    except ValueError as exc:
        raise ValueError("attempt completed_at is not a valid date-time") from exc


def _required_mapping(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"expected mapping field: {key}")
    return value


def _required_mappings(
    mapping: Mapping[str, object],
    key: str,
) -> tuple[Mapping[str, object], ...]:
    value = _required_sequence(mapping, key)
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"expected mapping items: {key}")
    return tuple(value)


def _required_sequence(mapping: Mapping[str, object], key: str) -> Sequence[object]:
    value = mapping.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"expected sequence field: {key}")
    return value


def _optional_strings(mapping: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"expected sequence field: {key}")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"expected string items: {key}")
    return tuple(value)


def _optional_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if value is None:
        return ""
    if not isinstance(value, str) or not value:
        raise ValueError(f"expected nonempty string field: {key}")
    return value


def _required_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"expected nonempty string field: {key}")
    return value


def _required_integer(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"expected nonnegative integer field: {key}")
    return value


def _unique_route_ids(
    routes: Sequence[Mapping[str, object]],
    context: str,
) -> set[str]:
    route_ids = [_required_string(route, "route_id") for route in routes]
    if len(route_ids) != len(set(route_ids)):
        raise ValueError(f"{context} contains duplicate route IDs")
    return set(route_ids)
