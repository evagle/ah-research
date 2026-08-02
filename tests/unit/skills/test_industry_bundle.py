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
    if role == "industry-forecast":
        return ("2026", "2027", "2028", "2029", "2030")
    return ()


def complete_role_outcomes() -> list[dict[str, object]]:
    return [role_outcome(role) for role in reversed(REQUIRED_ROLES)]


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
