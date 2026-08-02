"""Aggregate validated industry role outcomes into one bundle payload."""

from __future__ import annotations

import unicodedata
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
V11_ROLE_FIELDS = frozenset(
    {
        "claim_states",
        "accepted_evidence_count",
        "missing_coverage",
        "market_definition_fingerprints",
        "series",
    }
)


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
    schema_version = _bundle_schema_version(role_outcomes)
    roles_by_name = _validate_role_inventory(role_outcomes)
    claim_ids = set()
    roles = []
    unresolved_claim_ids = []
    for role_name in REQUIRED_ROLES:
        role = _normalize_role(roles_by_name[role_name], role_name, schema_version)
        _validate_claim_ids(role_name, role["claim_ids"], claim_ids)
        _validate_role_state(
            role_name,
            role,
            as_of,
            primary_market_scope_fingerprint,
            schema_version,
        )
        unresolved_claim_ids.extend(_role_unresolved_claim_ids(role, schema_version))
        roles.append(role)

    if schema_version == "1.1":
        _validate_cross_role_series_compatibility(roles)

    if any(role["state"] == "blocked" for role in roles):
        status = "blocked"
    elif any(role["state"] in {"partial", "exhausted"} for role in roles):
        status = "publishable-with-gaps"
    else:
        status = "complete"

    payload = {
        "schema_version": schema_version,
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


def _bundle_schema_version(role_outcomes: Sequence[Mapping[str, object]]) -> str:
    uses_v11 = [bool(V11_ROLE_FIELDS & outcome.keys()) for outcome in role_outcomes]
    if not any(uses_v11):
        return "1.0"
    if not all(uses_v11):
        raise ValueError("industry bundle v1.1 fields must be present on every role")
    for outcome in role_outcomes:
        missing_fields = V11_ROLE_FIELDS - outcome.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"industry bundle v1.1 role is missing: {missing}")
    return "1.1"


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


def _normalize_role(
    role_outcome: Mapping[str, object],
    role_name: str,
    schema_version: str,
) -> dict[str, object]:
    role = {
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
    if schema_version == "1.1":
        role.update(
            {
                "claim_states": _mapping_list(role_outcome, "claim_states"),
                "accepted_evidence_count": _integer_field(
                    role_outcome,
                    "accepted_evidence_count",
                ),
                "missing_coverage": _string_list(role_outcome, "missing_coverage"),
                "market_definition_fingerprints": _string_list(
                    role_outcome,
                    "market_definition_fingerprints",
                ),
                "series": _mapping_list(role_outcome, "series"),
            }
        )
    return role


def _validate_claim_ids(role_name: str, claim_ids: Sequence[str], seen_claim_ids: set[str]) -> None:
    if not claim_ids:
        raise ValueError(f"{role_name} claim_ids must not be empty")
    for claim_id in claim_ids:
        if claim_id in seen_claim_ids:
            raise ValueError(f"duplicate claim id: {claim_id}")
        seen_claim_ids.add(claim_id)


def _role_unresolved_claim_ids(
    role: Mapping[str, object],
    schema_version: str,
) -> list[str]:
    if schema_version == "1.0":
        claim_ids = list(_strings(role, "claim_ids"))
        if _state(role) in UNRESOLVED_STATES and len(claim_ids) > 1:
            raise ValueError("legacy unresolved roles with multiple claims require claim_states")
        return claim_ids if _state(role) in UNRESOLVED_STATES else []
    return [
        _string_field(claim_state, "claim_id")
        for claim_state in _mappings(role, "claim_states")
        if _string_field(claim_state, "state") in UNRESOLVED_STATES
    ]


def _validate_role_state(
    role_name: str,
    role: Mapping[str, object],
    as_of: date,
    primary_market_scope_fingerprint: str,
    schema_version: str,
) -> None:
    state = _state(role)
    required_periods = tuple(_strings(role, "required_periods"))
    accepted_periods = tuple(_strings(role, "accepted_periods"))
    missing_periods = tuple(_strings(role, "missing_periods"))
    scope_fingerprints = tuple(_strings(role, "scope_fingerprints"))
    ledger_paths = tuple(_strings(role, "ledger_paths"))
    gap_reason = role["gap_reason"]
    not_applicable_reason = role["not_applicable_reason"]
    accepted_evidence_count = (
        _integer_field(role, "accepted_evidence_count") if schema_version == "1.1" else None
    )
    missing_coverage = tuple(_strings(role, "missing_coverage")) if schema_version == "1.1" else ()

    _validate_required_periods(role_name, required_periods, as_of)

    if schema_version == "1.1":
        _validate_claim_states(role_name, role)
        _validate_v11_series(
            role_name,
            role,
            as_of,
            primary_market_scope_fingerprint,
            accepted_evidence_count,
        )
    elif role_name in COMPARABLE_SERIES_ROLES and accepted_periods:
        if len(scope_fingerprints) != 1:
            raise ValueError(
                f"{role_name} accepted series must have one scope fingerprint "
                "equal to primary_market_scope_fingerprint"
            )
        if scope_fingerprints[0] != primary_market_scope_fingerprint:
            raise ValueError(
                f"{role_name} accepted series must use the primary_market_scope_fingerprint"
            )

    if state == "accepted":
        if accepted_evidence_count is not None and accepted_evidence_count == 0:
            raise ValueError(f"{role_name} accepted roles require accepted evidence")
        if role_name == "market-concentration":
            _validate_accepted_market_concentration(accepted_periods, as_of)
        elif accepted_periods != required_periods:
            raise ValueError(f"{role_name} accepted_periods must match required_periods")
        if missing_periods:
            raise ValueError(f"{role_name} accepted roles cannot retain missing_periods")
        if missing_coverage:
            raise ValueError(f"{role_name} accepted roles cannot retain missing_coverage")
        if gap_reason is not None:
            raise ValueError(f"{role_name} accepted roles cannot set gap_reason")
        if not_applicable_reason is not None:
            raise ValueError(f"{role_name} accepted roles cannot set not_applicable_reason")
        if not ledger_paths:
            raise ValueError(f"{role_name} ledger_paths must not be empty")
        return

    if state == "partial":
        if accepted_evidence_count is None:
            if not accepted_periods:
                raise ValueError(f"{role_name} partial roles require accepted_periods")
            if not missing_periods:
                raise ValueError(f"{role_name} partial roles require missing_periods")
        else:
            if accepted_evidence_count == 0:
                raise ValueError(f"{role_name} partial roles require accepted evidence")
            if not missing_periods and not missing_coverage:
                raise ValueError(
                    f"{role_name} partial roles require missing_periods or missing_coverage"
                )
        if gap_reason is None:
            raise ValueError(f"{role_name} partial roles require gap_reason")
        if not ledger_paths:
            raise ValueError(f"{role_name} partial roles require ledger_paths")
        if not_applicable_reason is not None:
            raise ValueError(f"{role_name} partial roles cannot set not_applicable_reason")
        if required_periods:
            _validate_partial_period_coverage(
                role_name,
                required_periods,
                accepted_periods,
                missing_periods,
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
        if accepted_evidence_count not in {None, 0}:
            raise ValueError(f"{role_name} exhausted roles cannot retain accepted evidence")
        if accepted_evidence_count == 0 and not required_periods and not missing_coverage:
            raise ValueError(f"{role_name} exhausted roles require missing_coverage")
        return

    if state == "blocked":
        if schema_version == "1.0" and accepted_periods:
            raise ValueError(f"{role_name} blocked roles cannot retain accepted_periods")
        if gap_reason is None:
            raise ValueError(f"{role_name} blocked roles require gap_reason")
        if not ledger_paths:
            raise ValueError(f"{role_name} blocked roles require ledger_paths")
        if not_applicable_reason is not None:
            raise ValueError(f"{role_name} blocked roles cannot set not_applicable_reason")
        if schema_version == "1.1":
            if not missing_periods and not missing_coverage:
                raise ValueError(
                    f"{role_name} blocked roles require missing_periods or missing_coverage"
                )
            if required_periods:
                _validate_partial_period_coverage(
                    role_name,
                    required_periods,
                    accepted_periods,
                    missing_periods,
                )
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
        if accepted_evidence_count not in {None, 0}:
            raise ValueError(f"{role_name} not-applicable roles cannot retain accepted evidence")
        return

    raise ValueError(f"unknown role state: {state}")


def _validate_claim_states(
    role_name: str,
    role: Mapping[str, object],
) -> None:
    claim_ids = tuple(_strings(role, "claim_ids"))
    claim_states = _mappings(role, "claim_states")
    state_ids = tuple(_string_field(claim_state, "claim_id") for claim_state in claim_states)
    if len(set(state_ids)) != len(state_ids):
        raise ValueError(f"{role_name} claim_states must use unique claim IDs")
    if set(state_ids) != set(claim_ids):
        raise ValueError(f"{role_name} claim_states must cover claim_ids exactly")

    states = tuple(_string_field(claim_state, "state") for claim_state in claim_states)
    derived_state = _derive_role_state(states)
    if _state(role) != derived_state:
        raise ValueError(
            f"{role_name} state must be {derived_state} based on independent claim_states"
        )


def _derive_role_state(states: Sequence[str]) -> str:
    state_set = set(states)
    if "blocked" in state_set:
        return "blocked"
    if "partial" in state_set:
        return "partial"
    if "exhausted" in state_set:
        return "partial" if "accepted" in state_set else "exhausted"
    if "accepted" in state_set:
        return "accepted"
    if state_set == {"not-applicable"}:
        return "not-applicable"
    raise ValueError("claim_states cannot derive one role state")


def _validate_v11_series(
    role_name: str,
    role: Mapping[str, object],
    as_of: date,
    primary_market_scope_fingerprint: str,
    accepted_evidence_count: int | None,
) -> None:
    if accepted_evidence_count is None or accepted_evidence_count < 0:
        raise ValueError(f"{role_name} accepted_evidence_count must be non-negative")
    accepted_periods = tuple(_strings(role, "accepted_periods"))
    if accepted_evidence_count < len(accepted_periods):
        raise ValueError(
            f"{role_name} accepted_evidence_count cannot be less than accepted_periods"
        )

    market_fingerprints = tuple(_strings(role, "market_definition_fingerprints"))
    if market_fingerprints != (primary_market_scope_fingerprint,):
        raise ValueError(
            f"{role_name} must use one metric-independent primary market definition fingerprint"
        )

    series_fingerprints = tuple(_strings(role, "scope_fingerprints"))
    series_entries = _mappings(role, "series")
    if accepted_evidence_count and role_name in COMPARABLE_SERIES_ROLES:
        if len(series_fingerprints) != 1:
            raise ValueError(f"{role_name} accepted evidence must use one series fingerprint")
        if not series_entries:
            raise ValueError(f"{role_name} accepted evidence requires series metadata")
    if not series_entries:
        if series_fingerprints:
            raise ValueError(f"{role_name} scope_fingerprints require series metadata")
        return

    series_ids = tuple(_string_field(entry, "series_id") for entry in series_entries)
    if len(set(series_ids)) != len(series_ids):
        raise ValueError(f"{role_name} series_id values must be unique")
    entry_fingerprints = {_string_field(entry, "series_fingerprint") for entry in series_entries}
    if entry_fingerprints != set(series_fingerprints):
        raise ValueError(f"{role_name} series metadata must match scope_fingerprints")

    lineage_ids = set(_strings(role, "lineage_ids"))
    covered_periods: set[str] = set()
    vintage_keys: set[tuple[str, str]] = set()
    for entry in series_entries:
        if (
            _string_field(entry, "market_definition_fingerprint")
            != primary_market_scope_fingerprint
        ):
            raise ValueError(f"{role_name} series uses a different market definition")
        lineage_id = _string_field(entry, "lineage_id")
        if lineage_id not in lineage_ids:
            raise ValueError(f"{role_name} series lineage_id must be listed by the role")
        periods = tuple(_strings(entry, "periods"))
        if len(set(periods)) != len(periods):
            raise ValueError(f"{role_name} series periods must be unique")
        if any(period not in accepted_periods for period in periods):
            raise ValueError(f"{role_name} series periods must stay within accepted_periods")
        covered_periods.update(periods)

        published_at = _date_field(entry, "published_at")
        data_vintage = _date_field(entry, "data_vintage")
        if published_at > as_of or data_vintage > as_of:
            raise ValueError(
                f"{role_name} series publication and data vintage must not exceed as_of"
            )
        value_status = _string_field(entry, "value_status")
        if role_name == "industry-forecast" and value_status != "forecast":
            raise ValueError("industry-forecast series must be labeled forecast")
        if role_name != "industry-forecast" and value_status == "forecast":
            raise ValueError(f"{role_name} series cannot be labeled forecast")

        vintage_key = (
            _string_field(entry, "series_fingerprint"),
            data_vintage.isoformat(),
        )
        if vintage_key in vintage_keys:
            raise ValueError(
                f"{role_name} must render each series fingerprint and data vintage once"
            )
        vintage_keys.add(vintage_key)

    if covered_periods != set(accepted_periods):
        raise ValueError(f"{role_name} series must cover accepted_periods exactly")


def _validate_cross_role_series_compatibility(
    roles: Sequence[Mapping[str, object]],
) -> None:
    comparable_roles = {
        _string_field(role, "role"): role
        for role in roles
        if _string_field(role, "role")
        in {
            "market-concentration",
            "subject-market-share",
            "competitor-market-share",
        }
    }
    role_names = tuple(comparable_roles)
    for index, left_name in enumerate(role_names):
        for right_name in role_names[index + 1 :]:
            for left in _mappings(comparable_roles[left_name], "series"):
                for right in _mappings(comparable_roles[right_name], "series"):
                    if not set(_strings(left, "periods")) & set(_strings(right, "periods")):
                        continue
                    for field in ("channel_scope", "denominator"):
                        if _normalized_text(left.get(field)) != _normalized_text(right.get(field)):
                            raise ValueError(
                                f"{left_name} and {right_name} {field} must match "
                                "for overlapping periods"
                            )


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


def _validate_required_periods(
    role_name: str, required_periods: Sequence[str], as_of: date
) -> None:
    if role_name in {
        "historical-market-size",
        "subject-market-share",
        "competitor-market-share",
    }:
        expected_periods = completed_annual_periods(as_of, len(required_periods))
        if tuple(required_periods) != expected_periods:
            raise ValueError(f"{role_name} required_periods must match {expected_periods}")
        return
    if role_name == "market-concentration":
        expected_periods = (completed_annual_periods(as_of)[-1],)
        if tuple(required_periods) != expected_periods:
            raise ValueError(f"{role_name} required_periods must match {expected_periods}")
        return
    if role_name == "industry-forecast":
        years = len(required_periods)
        expected_periods = forecast_annual_periods(as_of, years)
        if tuple(required_periods) != expected_periods:
            raise ValueError(
                f"{role_name} required_periods must match a consecutive forecast window "
                f"starting at {as_of.year}"
            )
        return
    if required_periods:
        raise ValueError(f"{role_name} required_periods must match the empty bundle window")


def _validate_accepted_market_concentration(
    accepted_periods: Sequence[str],
    as_of: date,
) -> None:
    if not accepted_periods:
        raise ValueError(
            "market-concentration accepted roles require the latest completed annual period"
        )
    latest_completed_period = completed_annual_periods(as_of)[-1]
    allowed_periods = set(completed_annual_periods(as_of))
    if latest_completed_period not in accepted_periods:
        raise ValueError(
            "market-concentration accepted roles require the latest completed annual period"
        )
    if len(set(accepted_periods)) != len(accepted_periods):
        raise ValueError("market-concentration accepted_periods must be unique")
    if any(period not in allowed_periods for period in accepted_periods):
        raise ValueError(
            "market-concentration accepted_periods must stay within the completed annual window"
        )


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


def _mappings(
    mapping: Mapping[str, object],
    field: str,
) -> tuple[Mapping[str, object], ...]:
    value = mapping.get(field)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of mappings")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{field} must contain mappings")
    return tuple(value)


def _mapping_list(
    mapping: Mapping[str, object],
    field: str,
) -> list[dict[str, object]]:
    return [dict(item) for item in _mappings(mapping, field)]


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


def _integer_field(mapping: Mapping[str, object], field: str) -> int:
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _date_field(mapping: Mapping[str, object], field: str) -> date:
    value = _string_field(mapping, field)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def _string_from_value(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
