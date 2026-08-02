from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_PATH = (
    REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts" / "industry_bundle.py"
)
PRIMARY_SCOPE_FINGERPRINT = "a" * 64
SECONDARY_SCOPE_FINGERPRINT = "b" * 64
AS_OF = date(2026, 8, 2)
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
COMPARABLE_SERIES_ROLES = {
    "historical-market-size",
    "industry-forecast",
    "market-concentration",
    "subject-market-share",
    "competitor-market-share",
}
SERIES_FINGERPRINTS = {
    "historical-market-size": "1" * 64,
    "industry-forecast": "2" * 64,
    "market-concentration": "3" * 64,
    "subject-market-share": "4" * 64,
    "competitor-market-share": "5" * 64,
}


def load_bundle_module():
    assert BUNDLE_PATH.is_file(), f"missing industry bundle module: {BUNDLE_PATH}"
    script_dir = str(BUNDLE_PATH.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("industry_bundle", BUNDLE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def role_outcome(
    role: str,
    *,
    state: str = "accepted",
    claim_ids: list[str] | None = None,
    required_periods: list[str] | None = None,
    accepted_periods: list[str] | None = None,
    missing_periods: list[str] | None = None,
    scope_fingerprints: list[str] | None = None,
    lineage_ids: list[str] | None = None,
    ledger_paths: list[str] | None = None,
    gap_reason: str | None = None,
    not_applicable_reason: str | None = None,
) -> dict[str, object]:
    if required_periods is None:
        required_periods = list(default_required_periods(role))
    if accepted_periods is None:
        accepted_periods = (
            [] if state in {"exhausted", "blocked", "not-applicable"} else list(required_periods)
        )
    if missing_periods is None:
        missing_periods = []
    if scope_fingerprints is None:
        scope_fingerprints = [PRIMARY_SCOPE_FINGERPRINT]
    if lineage_ids is None:
        lineage_ids = [f"lineage-{role}"]
    if ledger_paths is None:
        ledger_paths = [f"research/{role}.json"]
    if claim_ids is None:
        claim_ids = [f"pop-mart-{role}"]
    return {
        "role": role,
        "claim_ids": claim_ids,
        "state": state,
        "required_periods": required_periods,
        "accepted_periods": accepted_periods,
        "missing_periods": missing_periods,
        "scope_fingerprints": scope_fingerprints,
        "lineage_ids": lineage_ids,
        "ledger_paths": ledger_paths,
        "gap_reason": gap_reason,
        "not_applicable_reason": not_applicable_reason,
    }


def default_required_periods(role: str) -> tuple[str, ...]:
    if role in {"historical-market-size", "subject-market-share", "competitor-market-share"}:
        return ("2021", "2022", "2023", "2024", "2025")
    if role == "market-concentration":
        return ("2025",)
    if role == "industry-forecast":
        return ("2026", "2027", "2028", "2029", "2030")
    return ()


def complete_role_outcomes() -> list[dict[str, object]]:
    return [role_outcome(role) for role in reversed(REQUIRED_ROLES)]


def series_descriptor(
    role: str,
    periods: list[str],
    *,
    data_vintage: str = "2025-12-31",
    published_at: str = "2026-02-01",
    channel_scope: str = "all retail channels",
    denominator: str = "total in-scope retail value",
) -> dict[str, object]:
    metric = {
        "historical-market-size": "annual retail market size",
        "industry-forecast": "annual retail market size",
        "market-concentration": "CR5 share",
        "subject-market-share": "subject market share",
        "competitor-market-share": "competitor market share",
    }[role]
    unit = "CNY billion" if role in {"historical-market-size", "industry-forecast"} else "percent"
    return {
        "series_id": f"{role}:{data_vintage}",
        "market_definition_fingerprint": PRIMARY_SCOPE_FINGERPRINT,
        "series_fingerprint": SERIES_FINGERPRINTS[role],
        "metric": metric,
        "unit": unit,
        "measurement_basis": "retail value",
        "channel_scope": channel_scope,
        "denominator": denominator,
        "period_semantics": "calendar-year",
        "value_status": "forecast" if role == "industry-forecast" else "historical-estimate",
        "periods": periods,
        "published_at": published_at,
        "data_vintage": data_vintage,
        "lineage_id": f"lineage-{role}",
    }


def role_outcome_v11(
    role: str,
    *,
    state: str = "accepted",
    claim_states: list[dict[str, str]] | None = None,
    required_periods: list[str] | None = None,
    accepted_periods: list[str] | None = None,
    missing_periods: list[str] | None = None,
    missing_coverage: list[str] | None = None,
    accepted_evidence_count: int | None = None,
    series: list[dict[str, object]] | None = None,
    gap_reason: str | None = None,
    not_applicable_reason: str | None = None,
) -> dict[str, object]:
    claim_ids = (
        [claim_state["claim_id"] for claim_state in claim_states]
        if claim_states is not None
        else [f"pop-mart-{role}"]
    )
    outcome = role_outcome(
        role,
        state=state,
        claim_ids=claim_ids,
        required_periods=required_periods,
        accepted_periods=accepted_periods,
        missing_periods=missing_periods,
        gap_reason=gap_reason,
        not_applicable_reason=not_applicable_reason,
    )
    accepted = outcome["accepted_periods"]
    assert isinstance(accepted, list)
    if accepted_evidence_count is None:
        accepted_evidence_count = (
            0 if state in {"exhausted", "not-applicable"} else max(1, len(accepted))
        )
    if series is None:
        series = (
            [series_descriptor(role, accepted)]
            if role in COMPARABLE_SERIES_ROLES and accepted_evidence_count
            else []
        )
    outcome.update(
        {
            "claim_states": claim_states or [{"claim_id": claim_ids[0], "state": state}],
            "accepted_evidence_count": accepted_evidence_count,
            "missing_coverage": missing_coverage or [],
            "market_definition_fingerprints": [PRIMARY_SCOPE_FINGERPRINT],
            "scope_fingerprints": sorted(
                {descriptor["series_fingerprint"] for descriptor in series}
            ),
            "series": series,
        }
    )
    return outcome


def complete_role_outcomes_v11() -> list[dict[str, object]]:
    return [role_outcome_v11(role) for role in reversed(REQUIRED_ROLES)]


def test_period_windows_derive_from_as_of() -> None:
    bundle = load_bundle_module()

    assert bundle.completed_annual_periods(date(2026, 8, 2)) == (
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
    )
    assert bundle.forecast_annual_periods(date(2026, 8, 2), 5) == (
        "2026",
        "2027",
        "2028",
        "2029",
        "2030",
    )


@pytest.mark.parametrize("years", (4, 11))
def test_completed_periods_require_five_through_ten_years(years: int) -> None:
    bundle = load_bundle_module()

    with pytest.raises(ValueError, match="five through ten"):
        bundle.completed_annual_periods(AS_OF, years)


@pytest.mark.parametrize("years", (2, 6))
def test_forecast_periods_require_three_through_five_years(years: int) -> None:
    bundle = load_bundle_module()

    with pytest.raises(ValueError, match="three through five"):
        bundle.forecast_annual_periods(AS_OF, years)


def test_accepted_required_roles_produce_complete_bundle() -> None:
    bundle = load_bundle_module()

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=complete_role_outcomes(),
    )

    assert payload["status"] == "complete"
    assert [role["role"] for role in payload["roles"]] == list(REQUIRED_ROLES)
    assert payload["unresolved_claim_ids"] == []


def test_partial_subject_share_produces_publishable_with_gaps() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    subject_share = next(
        outcome for outcome in outcomes if outcome["role"] == "subject-market-share"
    )
    subject_share.update(
        {
            "state": "partial",
            "accepted_periods": ["2021", "2022", "2024", "2025"],
            "missing_periods": ["2023"],
            "gap_reason": "No comparable 2023 public company-share table",
        }
    )

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    assert payload["status"] == "publishable-with-gaps"
    assert payload["unresolved_claim_ids"] == ["pop-mart-subject-market-share"]


def test_blocked_required_role_makes_bundle_blocked() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    forecast = next(outcome for outcome in outcomes if outcome["role"] == "industry-forecast")
    forecast.update(
        {
            "state": "blocked",
            "accepted_periods": [],
            "missing_periods": ["2026", "2027", "2028", "2029", "2030"],
            "gap_reason": "Provider access unavailable",
        }
    )

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    assert payload["status"] == "blocked"
    assert payload["unresolved_claim_ids"] == ["pop-mart-industry-forecast"]


def test_exhausted_role_requires_gap_reason_and_ledger_paths() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    competitor_share = next(
        outcome for outcome in outcomes if outcome["role"] == "competitor-market-share"
    )
    competitor_share.update(
        {
            "state": "exhausted",
            "accepted_periods": [],
            "missing_periods": list(competitor_share["required_periods"]),
            "gap_reason": "All comparable ranking tables exhausted",
        }
    )

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    assert payload["status"] == "publishable-with-gaps"
    assert payload["unresolved_claim_ids"] == ["pop-mart-competitor-market-share"]

    missing_gap_reason = deepcopy(outcomes)
    next(outcome for outcome in missing_gap_reason if outcome["role"] == "competitor-market-share")[
        "gap_reason"
    ] = None
    with pytest.raises(ValueError, match="gap_reason"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=missing_gap_reason,
        )

    missing_ledger_paths = deepcopy(outcomes)
    next(
        outcome for outcome in missing_ledger_paths if outcome["role"] == "competitor-market-share"
    )["ledger_paths"] = []
    with pytest.raises(ValueError, match="ledger_paths"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=missing_ledger_paths,
        )

    with_accepted_periods = deepcopy(outcomes)
    next(
        outcome for outcome in with_accepted_periods if outcome["role"] == "competitor-market-share"
    )["accepted_periods"] = ["2025"]
    with pytest.raises(ValueError, match="accepted_periods"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=with_accepted_periods,
        )


def test_market_concentration_requires_latest_completed_annual_observation() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    concentration = next(
        outcome for outcome in outcomes if outcome["role"] == "market-concentration"
    )
    concentration["accepted_periods"] = []

    with pytest.raises(ValueError, match="latest completed annual period"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=outcomes,
        )


def test_not_applicable_is_limited_to_current_partial_period_and_industry_drivers() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    current_partial_period = next(
        outcome for outcome in outcomes if outcome["role"] == "current-partial-period"
    )
    current_partial_period.update(
        {
            "state": "not-applicable",
            "accepted_periods": [],
            "ledger_paths": [],
            "not_applicable_reason": "No H1 update is published for this market",
        }
    )

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    assert payload["status"] == "complete"

    invalid_outcomes = complete_role_outcomes()
    historical = next(
        outcome for outcome in invalid_outcomes if outcome["role"] == "historical-market-size"
    )
    historical.update(
        {
            "state": "not-applicable",
            "accepted_periods": [],
            "missing_periods": [],
            "not_applicable_reason": "Analyst skipped the role",
        }
    )
    with pytest.raises(ValueError, match="not-applicable"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=invalid_outcomes,
        )


@pytest.mark.parametrize("role", sorted(COMPARABLE_SERIES_ROLES))
def test_accepted_comparable_roles_require_one_scope_fingerprint(role: str) -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    target = next(outcome for outcome in outcomes if outcome["role"] == role)
    target["scope_fingerprints"] = [PRIMARY_SCOPE_FINGERPRINT, SECONDARY_SCOPE_FINGERPRINT]

    with pytest.raises(ValueError, match="one scope fingerprint"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=outcomes,
        )


@pytest.mark.parametrize("role", sorted(COMPARABLE_SERIES_ROLES))
def test_accepted_comparable_roles_require_primary_scope_fingerprint(role: str) -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    target = next(outcome for outcome in outcomes if outcome["role"] == role)
    target["scope_fingerprints"] = [SECONDARY_SCOPE_FINGERPRINT]

    with pytest.raises(ValueError, match="primary_market_scope_fingerprint"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=outcomes,
        )


@pytest.mark.parametrize(
    ("years", "periods"),
    (
        (3, ["2026", "2027", "2028"]),
        (4, ["2026", "2027", "2028", "2029"]),
    ),
)
def test_industry_forecast_accepts_three_and_four_year_windows(
    years: int,
    periods: list[str],
) -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    forecast = next(outcome for outcome in outcomes if outcome["role"] == "industry-forecast")
    forecast["required_periods"] = list(periods)
    forecast["accepted_periods"] = list(periods)

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    accepted_forecast = next(
        role for role in payload["roles"] if role["role"] == "industry-forecast"
    )
    assert payload["status"] == "complete"
    assert accepted_forecast["required_periods"] == periods
    assert accepted_forecast["accepted_periods"] == periods


def test_unknown_duplicate_and_missing_roles_fail() -> None:
    bundle = load_bundle_module()

    unknown = complete_role_outcomes()
    unknown.append(role_outcome("adjacent-market-size"))
    with pytest.raises(ValueError, match="unknown role"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=unknown,
        )

    duplicate = complete_role_outcomes()
    duplicate.append(deepcopy(duplicate[0]))
    with pytest.raises(ValueError, match="duplicate role"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=duplicate,
        )

    missing = complete_role_outcomes()
    missing = [outcome for outcome in missing if outcome["role"] != "industry-drivers"]
    with pytest.raises(ValueError, match="missing role"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=missing,
        )


def test_duplicate_claim_ids_are_rejected() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    outcomes[0]["claim_ids"] = ["shared-claim-id"]
    outcomes[1]["claim_ids"] = ["shared-claim-id"]

    with pytest.raises(ValueError, match="duplicate claim"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=outcomes,
        )


def test_unresolved_claim_ids_derive_from_partial_exhausted_and_blocked_roles() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes()
    next(outcome for outcome in outcomes if outcome["role"] == "subject-market-share").update(
        {
            "state": "partial",
            "accepted_periods": ["2021", "2022", "2023", "2025"],
            "missing_periods": ["2024"],
            "gap_reason": "No comparable 2024 denominator",
        }
    )
    next(outcome for outcome in outcomes if outcome["role"] == "competitor-market-share").update(
        {
            "state": "exhausted",
            "accepted_periods": [],
            "missing_periods": ["2021", "2022", "2023", "2024", "2025"],
            "gap_reason": "No ranking table survived gate review",
        }
    )
    next(outcome for outcome in outcomes if outcome["role"] == "industry-forecast").update(
        {
            "state": "blocked",
            "accepted_periods": [],
            "missing_periods": ["2026", "2027", "2028", "2029", "2030"],
            "gap_reason": "Forecast provider requires credentials",
        }
    )

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    assert payload["status"] == "blocked"
    assert payload["unresolved_claim_ids"] == [
        "pop-mart-industry-forecast",
        "pop-mart-subject-market-share",
        "pop-mart-competitor-market-share",
    ]


def test_v11_roles_share_market_definition_not_series_fingerprint() -> None:
    bundle = load_bundle_module()

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=complete_role_outcomes_v11(),
    )

    assert payload["schema_version"] == "1.1"
    assert payload["status"] == "complete"
    comparable_roles = [
        role for role in payload["roles"] if role["role"] in COMPARABLE_SERIES_ROLES
    ]
    assert {role["market_definition_fingerprints"][0] for role in comparable_roles} == {
        PRIMARY_SCOPE_FINGERPRINT
    }
    assert len({role["scope_fingerprints"][0] for role in comparable_roles}) == len(
        COMPARABLE_SERIES_ROLES
    )


def test_claim_states_keep_accepted_forecast_claims_terminal() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes_v11()
    forecast = next(outcome for outcome in outcomes if outcome["role"] == "industry-forecast")
    forecast.update(
        {
            "claim_ids": [
                "pop-mart-industry-forecast",
                "pop-mart-industry-forecast:prior-vintage",
                "pop-mart-industry-forecast:later-vintage",
            ],
            "claim_states": [
                {"claim_id": "pop-mart-industry-forecast", "state": "accepted"},
                {
                    "claim_id": "pop-mart-industry-forecast:prior-vintage",
                    "state": "accepted",
                },
                {
                    "claim_id": "pop-mart-industry-forecast:later-vintage",
                    "state": "exhausted",
                },
            ],
            "state": "partial",
            "missing_coverage": ["later forecast vintage not publicly available"],
            "gap_reason": "The later-vintage version chase exhausted all routes",
        }
    )

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    assert payload["status"] == "publishable-with-gaps"
    assert payload["unresolved_claim_ids"] == ["pop-mart-industry-forecast:later-vintage"]
    assert "pop-mart-industry-forecast" not in payload["unresolved_claim_ids"]
    assert "pop-mart-industry-forecast:prior-vintage" not in payload["unresolved_claim_ids"]


@pytest.mark.parametrize("years", (6, 10))
def test_completed_history_accepts_six_to_ten_year_windows(years: int) -> None:
    bundle = load_bundle_module()
    periods = list(bundle.completed_annual_periods(AS_OF, years))
    outcomes = complete_role_outcomes_v11()
    for role_name in (
        "historical-market-size",
        "subject-market-share",
        "competitor-market-share",
    ):
        role = next(outcome for outcome in outcomes if outcome["role"] == role_name)
        role["required_periods"] = periods
        role["accepted_periods"] = periods
        role["accepted_evidence_count"] = len(periods)
        role["series"] = [series_descriptor(role_name, periods)]

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    assert payload["status"] == "complete"


@pytest.mark.parametrize(
    "role_name",
    ("market-definition", "current-partial-period", "industry-drivers"),
)
def test_non_period_partial_roles_retain_evidence_and_missing_coverage(
    role_name: str,
) -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes_v11()
    role = next(outcome for outcome in outcomes if outcome["role"] == role_name)
    role.update(
        {
            "state": "partial",
            "claim_states": [{"claim_id": role["claim_ids"][0], "state": "partial"}],
            "accepted_evidence_count": 1,
            "missing_coverage": ["one required non-period evidence dimension"],
            "gap_reason": "Accepted evidence does not cover every required dimension",
        }
    )

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    retained = next(item for item in payload["roles"] if item["role"] == role_name)
    assert payload["status"] == "publishable-with-gaps"
    assert retained["accepted_evidence_count"] == 1
    assert retained["missing_coverage"] == ["one required non-period evidence dimension"]


def test_blocked_role_retains_accepted_observations_and_missing_coverage() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes_v11()
    historical = next(
        outcome for outcome in outcomes if outcome["role"] == "historical-market-size"
    )
    historical.update(
        {
            "state": "blocked",
            "claim_states": [{"claim_id": historical["claim_ids"][0], "state": "blocked"}],
            "accepted_periods": ["2021", "2022", "2023", "2024"],
            "missing_periods": ["2025"],
            "accepted_evidence_count": 4,
            "missing_coverage": ["2025 provider table blocked by access controls"],
            "series": [
                series_descriptor(
                    "historical-market-size",
                    ["2021", "2022", "2023", "2024"],
                )
            ],
            "gap_reason": "The latest provider table could not be accessed",
        }
    )

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    retained = next(role for role in payload["roles"] if role["role"] == "historical-market-size")
    assert payload["status"] == "blocked"
    assert retained["accepted_periods"] == ["2021", "2022", "2023", "2024"]
    assert retained["missing_periods"] == ["2025"]


def test_forecast_vintages_remain_separate_series() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes_v11()
    forecast = next(outcome for outcome in outcomes if outcome["role"] == "industry-forecast")
    forecast["series"] = [
        series_descriptor(
            "industry-forecast",
            ["2026", "2027", "2028", "2029", "2030"],
            data_vintage="2025-06-30",
            published_at="2025-07-15",
        ),
        series_descriptor(
            "industry-forecast",
            ["2026", "2027", "2028", "2029", "2030"],
            data_vintage="2025-12-31",
            published_at="2026-02-01",
        ),
    ]

    payload = bundle.evaluate_industry_bundle(
        subject="Pop Mart",
        as_of=AS_OF,
        primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
        role_outcomes=outcomes,
    )

    retained = next(role for role in payload["roles"] if role["role"] == "industry-forecast")
    assert [series["data_vintage"] for series in retained["series"]] == [
        "2025-06-30",
        "2025-12-31",
    ]


@pytest.mark.parametrize(
    ("field", "incompatible_value"),
    (
        ("channel_scope", "online retail only"),
        ("denominator", "issuer accounting revenue"),
    ),
)
def test_share_roles_reject_channel_or_denominator_mismatch(
    field: str,
    incompatible_value: str,
) -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes_v11()
    competitor = next(
        outcome for outcome in outcomes if outcome["role"] == "competitor-market-share"
    )
    competitor_series = competitor["series"][0]
    assert isinstance(competitor_series, dict)
    competitor_series[field] = incompatible_value

    with pytest.raises(ValueError, match=field):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=outcomes,
        )


def test_shifted_forecast_window_is_rejected() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes_v11()
    forecast = next(outcome for outcome in outcomes if outcome["role"] == "industry-forecast")
    shifted = ["2027", "2028", "2029", "2030", "2031"]
    forecast["required_periods"] = shifted
    forecast["accepted_periods"] = shifted
    forecast["series"] = [series_descriptor("industry-forecast", shifted)]

    with pytest.raises(ValueError, match="starting at 2026"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=outcomes,
        )


def test_stale_only_concentration_cannot_be_accepted() -> None:
    bundle = load_bundle_module()
    outcomes = complete_role_outcomes_v11()
    concentration = next(
        outcome for outcome in outcomes if outcome["role"] == "market-concentration"
    )
    concentration["accepted_periods"] = ["2024"]
    concentration["series"] = [series_descriptor("market-concentration", ["2024"])]

    with pytest.raises(ValueError, match="latest completed annual period"):
        bundle.evaluate_industry_bundle(
            subject="Pop Mart",
            as_of=AS_OF,
            primary_market_scope_fingerprint=PRIMARY_SCOPE_FINGERPRINT,
            role_outcomes=outcomes,
        )
