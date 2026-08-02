"""Aggregate validated industry role outcomes into one bundle payload."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from research_contracts import validate_payload

REQUIRED_ROLES = (
    "market-definition",
    "historical-market-size",
    "industry-forecast",
    "market-concentration",
    "subject-market-share",
    "competitor-market-share",
    "current-partial-period",
    "industry-drivers",
)
COMPARABLE_SERIES_ROLES = frozenset(
    {
        "historical-market-size",
        "industry-forecast",
        "market-concentration",
        "subject-market-share",
        "competitor-market-share",
    }
)
NOT_APPLICABLE_ROLES = frozenset({"current-partial-period", "industry-drivers"})
UNRESOLVED_STATES = frozenset({"partial", "exhausted", "blocked"})


def completed_annual_periods(as_of: date, years: int = 5) -> tuple[str, ...]:
    """Return the latest completed annual periods ending before as_of.year."""
    if years < 5 or years > 10:
        raise ValueError("completed annual periods require years five through ten")
    end_year = as_of.year - 1
    start_year = end_year - years + 1
    return tuple(str(year) for year in range(start_year, end_year + 1))


def forecast_annual_periods(as_of: date, years: int) -> tuple[str, ...]:
    """Return the annual forecast window starting at as_of.year."""
    if years < 3 or years > 5:
        raise ValueError("forecast annual periods require years three through five")
    return tuple(str(year) for year in range(as_of.year, as_of.year + years))


def evaluate_industry_bundle(
    *,
    subject: str,
    as_of: date,
    primary_market_scope_fingerprint: str,
    role_outcomes: Sequence[Mapping[str, object]],
    scope_breaks: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Validate and assemble the bundle payload for industry evidence."""
    roles_by_name = _validate_role_inventory(role_outcomes)
    claim_ids = set()
    roles = []
    for role_name in REQUIRED_ROLES:
        role = _normalize_role(roles_by_name[role_name], role_name)
        _validate_claim_ids(role_name, role["claim_ids"], claim_ids)
        _validate_role_state(role_name, role, as_of)
        roles.append(role)

    if any(role["state"] == "blocked" for role in roles):
        status = "blocked"
    elif any(role["state"] in {"partial", "exhausted"} for role in roles):
        status = "publishable-with-gaps"
    else:
        status = "complete"

    unresolved_claim_ids = [
        claim_id
        for role in roles
        if role["state"] in UNRESOLVED_STATES
        for claim_id in role["claim_ids"]
    ]
    payload = {
        "schema_version": "1.0",
        "subject": subject,
        "as_of": as_of.isoformat(),
        "primary_market_scope_fingerprint": primary_market_scope_fingerprint,
        "status": status,
        "roles": roles,
        "scope_breaks": [dict(scope_break) for scope_break in scope_breaks],
        "unresolved_claim_ids": unresolved_claim_ids,
    }
    validate_payload("industry-bundle", payload)
    return payload


def _validate_role_inventory(
    role_outcomes: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    roles_by_name: dict[str, Mapping[str, object]] = {}
    for outcome in role_outcomes:
        role_name = _string_field(outcome, "role")
        if role_name not in REQUIRED_ROLES:
            raise ValueError(f"unknown role: {role_name}")
        if role_name in roles_by_name:
            raise ValueError(f"duplicate role: {role_name}")
        roles_by_name[role_name] = outcome

    for required_role in REQUIRED_ROLES:
        if required_role not in roles_by_name:
            raise ValueError(f"missing role: {required_role}")
    return roles_by_name


def _normalize_role(role_outcome: Mapping[str, object], role_name: str) -> dict[str, object]:
    return {
        "role": role_name,
        "claim_ids": _string_list(role_outcome, "claim_ids"),
        "state": _string_field(role_outcome, "state"),
        "required_periods": _string_list(role_outcome, "required_periods"),
        "accepted_periods": _string_list(role_outcome, "accepted_periods"),
        "missing_periods": _string_list(role_outcome, "missing_periods"),
        "scope_fingerprints": _string_list(role_outcome, "scope_fingerprints"),
        "lineage_ids": _string_list(role_outcome, "lineage_ids"),
        "ledger_paths": _string_list(role_outcome, "ledger_paths"),
        "gap_reason": _nullable_string_field(role_outcome, "gap_reason"),
        "not_applicable_reason": _nullable_string_field(role_outcome, "not_applicable_reason"),
    }


def _validate_claim_ids(role_name: str, claim_ids: Sequence[str], seen_claim_ids: set[str]) -> None:
    if not claim_ids:
        raise ValueError(f"{role_name} claim_ids must not be empty")
    for claim_id in claim_ids:
        if claim_id in seen_claim_ids:
            raise ValueError(f"duplicate claim id: {claim_id}")
        seen_claim_ids.add(claim_id)


def _validate_role_state(role_name: str, role: Mapping[str, object], as_of: date) -> None:
    state = _state(role)
    required_periods = tuple(_strings(role, "required_periods"))
    accepted_periods = tuple(_strings(role, "accepted_periods"))
    missing_periods = tuple(_strings(role, "missing_periods"))
    scope_fingerprints = tuple(_strings(role, "scope_fingerprints"))
    ledger_paths = tuple(_strings(role, "ledger_paths"))
    gap_reason = role["gap_reason"]
    not_applicable_reason = role["not_applicable_reason"]

    expected_periods = _expected_required_periods(role_name, as_of)
    if required_periods != expected_periods:
        raise ValueError(
            f"{role_name} required_periods must match {expected_periods or 'the empty bundle window'}"
        )

    if (
        role_name in COMPARABLE_SERIES_ROLES
        and state in {"accepted", "partial"}
        and len(scope_fingerprints) != 1
    ):
        raise ValueError(f"{role_name} accepted series must have one scope fingerprint")

    if state == "accepted":
        if accepted_periods != required_periods:
            raise ValueError(f"{role_name} accepted_periods must match required_periods")
        if missing_periods:
            raise ValueError(f"{role_name} accepted roles cannot retain missing_periods")
        if gap_reason is not None:
            raise ValueError(f"{role_name} accepted roles cannot set gap_reason")
        if not_applicable_reason is not None:
            raise ValueError(f"{role_name} accepted roles cannot set not_applicable_reason")
        if not ledger_paths:
            raise ValueError(f"{role_name} ledger_paths must not be empty")
        return

    if state == "partial":
        if not accepted_periods:
            raise ValueError(f"{role_name} partial roles require accepted_periods")
        if not missing_periods:
            raise ValueError(f"{role_name} partial roles require missing_periods")
        if gap_reason is None:
            raise ValueError(f"{role_name} partial roles require gap_reason")
        if not ledger_paths:
            raise ValueError(f"{role_name} partial roles require ledger_paths")
        if not_applicable_reason is not None:
            raise ValueError(f"{role_name} partial roles cannot set not_applicable_reason")
        _validate_partial_period_coverage(
            role_name, required_periods, accepted_periods, missing_periods
        )
        return

    if state == "exhausted":
        if accepted_periods:
            raise ValueError(f"{role_name} exhausted roles cannot retain accepted_periods")
        if gap_reason is None:
            raise ValueError(f"{role_name} exhausted roles require gap_reason")
        if not ledger_paths:
            raise ValueError(f"{role_name} exhausted roles require ledger_paths")
        if not_applicable_reason is not None:
            raise ValueError(f"{role_name} exhausted roles cannot set not_applicable_reason")
        if required_periods and missing_periods != required_periods:
            raise ValueError(f"{role_name} exhausted roles must mark all required periods missing")
        return

    if state == "blocked":
        if accepted_periods:
            raise ValueError(f"{role_name} blocked roles cannot retain accepted_periods")
        if gap_reason is None:
            raise ValueError(f"{role_name} blocked roles require gap_reason")
        if not ledger_paths:
            raise ValueError(f"{role_name} blocked roles require ledger_paths")
        if not_applicable_reason is not None:
            raise ValueError(f"{role_name} blocked roles cannot set not_applicable_reason")
        return

    if state == "not-applicable":
        if role_name not in NOT_APPLICABLE_ROLES:
            raise ValueError(f"{role_name} cannot be not-applicable")
        if accepted_periods:
            raise ValueError(f"{role_name} not-applicable roles cannot retain accepted_periods")
        if missing_periods:
            raise ValueError(f"{role_name} not-applicable roles cannot retain missing_periods")
        if gap_reason is not None:
            raise ValueError(f"{role_name} not-applicable roles cannot set gap_reason")
        if not_applicable_reason is None:
            raise ValueError(f"{role_name} not-applicable roles require not_applicable_reason")
        return

    raise ValueError(f"unknown role state: {state}")


def _validate_partial_period_coverage(
    role_name: str,
    required_periods: Sequence[str],
    accepted_periods: Sequence[str],
    missing_periods: Sequence[str],
) -> None:
    required_set = set(required_periods)
    accepted_set = set(accepted_periods)
    missing_set = set(missing_periods)
    if len(accepted_set) != len(accepted_periods):
        raise ValueError(f"{role_name} accepted_periods must be unique")
    if len(missing_set) != len(missing_periods):
        raise ValueError(f"{role_name} missing_periods must be unique")
    if accepted_set & missing_set:
        raise ValueError(f"{role_name} accepted_periods and missing_periods cannot overlap")
    if required_periods and (accepted_set | missing_set) != required_set:
        raise ValueError(f"{role_name} partial periods must cover required_periods")
    if any(period not in required_set for period in accepted_periods + tuple(missing_periods)):
        raise ValueError(f"{role_name} partial periods must stay within required_periods")


def _expected_required_periods(role_name: str, as_of: date) -> tuple[str, ...]:
    if role_name in {
        "historical-market-size",
        "subject-market-share",
        "competitor-market-share",
    }:
        return completed_annual_periods(as_of)
    if role_name == "industry-forecast":
        return forecast_annual_periods(as_of, 5)
    return ()


def _state(role: Mapping[str, object]) -> str:
    return _string_from_value(role["state"], "state")


def _strings(role: Mapping[str, object], field: str) -> tuple[str, ...]:
    value = role[field]
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of strings")
    result = []
    for item in value:
        result.append(_string_from_value(item, field))
    return tuple(result)


def _string_list(mapping: Mapping[str, object], field: str) -> list[str]:
    return list(_strings(mapping, field))


def _string_field(mapping: Mapping[str, object], field: str) -> str:
    if field not in mapping:
        raise ValueError(f"missing required field: {field}")
    return _string_from_value(mapping[field], field)


def _nullable_string_field(mapping: Mapping[str, object], field: str) -> str | None:
    if field not in mapping:
        raise ValueError(f"missing required field: {field}")
    value = mapping[field]
    if value is None:
        return None
    return _string_from_value(value, field)


def _string_from_value(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value
