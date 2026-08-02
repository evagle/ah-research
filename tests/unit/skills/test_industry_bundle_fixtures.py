from __future__ import annotations

from datetime import date

import pytest
import yaml

from .test_industry_bundle import REPO_ROOT, REQUIRED_ROLES, load_bundle_module

FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "source-discovery" / "industry-bundles"


def load_fixture(name: str) -> dict[str, object]:
    path = FIXTURE_ROOT / name
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    (
        ("pop-mart.yaml", "publishable-with-gaps"),
        ("kweichow-moutai.yaml", "publishable-with-gaps"),
        ("smic.yaml", "publishable-with-gaps"),
    ),
)
def test_cross_industry_bundle_fixture(
    fixture_name: str,
    expected_status: str,
) -> None:
    bundle = load_bundle_module()
    payload = load_fixture(fixture_name)

    assert len(payload["role_outcomes"]) == len(REQUIRED_ROLES)
    assert len(payload["scope_breaks"]) >= 1

    result = bundle.evaluate_industry_bundle(
        subject=payload["subject"],
        as_of=date.fromisoformat(payload["as_of"]),
        primary_market_scope_fingerprint=payload["primary_market_scope_fingerprint"],
        role_outcomes=payload["role_outcomes"],
        scope_breaks=payload["scope_breaks"],
    )

    assert [role["role"] for role in result["roles"]] == list(REQUIRED_ROLES)
    assert result["status"] == expected_status
    assert result["unresolved_claim_ids"] == payload["unresolved_claim_ids"]


def test_pop_mart_fixture_records_legacy_forecast_same_lineage() -> None:
    payload = load_fixture("pop-mart.yaml")

    legacy_forecast_sources = payload["legacy_forecast_sources"]
    assert len(legacy_forecast_sources) == 2
    assert [source["source"] for source in legacy_forecast_sources] == [
        "KPMG old forecast",
        "TOP TOY old forecast",
    ]
    assert {source["lineage_id"] for source in legacy_forecast_sources} == {
        "frost-sullivan-pop-toys-rsv-forecast"
    }
