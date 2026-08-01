from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "source-discovery"
    / "references"
    / "source-profile.schema.json"
)
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "source-discovery" / "profiles"
SCENARIOS_ROOT = REPO_ROOT / "tests" / "fixtures" / "source-discovery" / "scenarios"
SCRIPT_PATH = (
    REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts" / "source_profiles.py"
)
PROFILES_ROOT = REPO_ROOT / ".claude" / "skills" / "source-discovery" / "references" / "sources"
SNAPSHOT_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "source-discovery"
    / "references"
    / "reachability-snapshot.json"
)
EXPECTED_PROFILE_IDS = {
    "100ec",
    "199it",
    "199it-housing-tools",
    "360-security-reports",
    "3gpp",
    "36kr",
    "afrc",
    "aastocks",
    "aladdin-index",
    "aliresearch",
    "analysys",
    "aon-china",
    "bain-china",
    "bcg-china",
    "beijing-government",
    "beijing-statistics",
    "business-group-health",
    "caac",
    "cac",
    "cadas",
    "caasdata",
    "caict",
    "china-money",
    "china-venture",
    "cicc-research",
    "cninfo",
    "cnnic",
    "companies-registry-hk",
    "csrc",
    "data-gov-hk",
    "datayes-robo-research",
    "deloitte-china",
    "dotour",
    "dydata",
    "eastmoney-announcement-index",
    "eastmoney-pdf-delivery",
    "eastmoney-quotes-f10",
    "eastmoney-research",
    "eastmoney-securities",
    "endata",
    "etsi",
    "eurostat",
    "ey-china",
    "fenghuo-research",
    "flurry",
    "gallagher",
    "gsma-mobile-economy",
    "guangdong-government",
    "guangdong-statistics",
    "hang-seng-indexes",
    "hibor-research",
    "hk-icac",
    "hk-insurance-authority",
    "hk-judiciary",
    "hk-police",
    "hkex-ccass",
    "hkex-di",
    "hkex-market-data",
    "hkex",
    "hkexnews",
    "hkma",
    "hksar-budget",
    "hksar-policy-address",
    "hksar-press-releases",
    "hktdc-research",
    "hong-kong-consumer-council",
    "hong-kong-e-gazette",
    "hong-kong-e-legislation",
    "hong-kong-statistics",
    "idc",
    "iimedia",
    "imf-data",
    "iresearch",
    "it-juzi",
    "itu-statistics",
    "jpmorgan",
    "kpmg-china",
    "mckinsey-china",
    "ministry-culture-tourism",
    "mercer-china",
    "miit-data",
    "ministry-of-education",
    "ministry-of-finance",
    "mofcom",
    "national-bureau-statistics",
    "national-film-administration",
    "newrank",
    "nfra",
    "nxny",
    "nrta",
    "pbc",
    "pew-research",
    "pop-mart",
    "pwc-china",
    "pwc-us-library",
    "questmobile",
    "roland-berger",
    "sec-edgar",
    "sfc",
    "shanghai-government",
    "shanghai-statistics",
    "sina-finance",
    "sse",
    "state-council",
    "state-post-bureau",
    "szse",
    "tencent-big-data",
    "tencent-research",
    "toobigdata",
    "un-comtrade",
    "un-sdg-data",
    "undata",
    "unsd-demographic-social",
    "us-bea",
    "us-census",
    "us-commerce",
    "wef-china",
    "who-gho",
    "world-bank-data",
    "worldpanel",
    "wto-stats",
    "wtw",
    "xueqiu",
}
EXPECTED_PUBLISHER_SEMANTICS = {
    "official-exchange": ("High", "High"),
    "official-regulator": ("High", "High"),
    "official-statistics": ("High", "High"),
    "official-government": ("High", "High"),
    "official-market-infrastructure": ("High", "High"),
    "issuer-company": ("High", "Low"),
    "original-research": ("High", "Medium"),
    "consulting-research": ("High", "Medium"),
    "commercial-data-provider": ("High", "Medium"),
    "aggregator": ("Low", "Low"),
    "media": ("Low", "Medium"),
    "mirror": ("Low", "Low"),
}
APPROVED_STATUSES = {
    "reachable",
    "reachable-limited",
    "login-required",
    "paywalled",
    "anti-bot",
    "temporarily-unreachable",
    "moved",
    "broken-link",
    "unverified",
}


def load_schema() -> dict[str, object]:
    assert SCHEMA_PATH.is_file(), f"missing schema: {SCHEMA_PATH}"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_profile(name: str) -> dict[str, object]:
    path = FIXTURES_ROOT / name
    assert path.is_file(), f"missing fixture: {path}"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def load_scenario(name: str) -> dict[str, object]:
    path = SCENARIOS_ROOT / name
    assert path.is_file(), f"missing scenario fixture: {path}"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def load_source_profiles_module():
    assert SCRIPT_PATH.is_file(), f"missing script: {SCRIPT_PATH}"
    spec = importlib.util.spec_from_file_location("source_profiles", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_profile(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def validator() -> Draft202012Validator:
    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def load_maintained_profiles() -> list[dict[str, object]]:
    source_profiles = load_source_profiles_module()
    return source_profiles.load_profiles(PROFILES_ROOT, SCHEMA_PATH)


def test_source_profile_schema_is_valid() -> None:
    validator()


def test_example_profiles_validate() -> None:
    profile_validator = validator()
    for fixture_name in ("official-example.yaml", "aggregator-example.yaml"):
        assert not list(profile_validator.iter_errors(load_profile(fixture_name)))


def test_profile_requires_observed_error() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    del invalid["access"]["observed_error"]

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_requires_limitation() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    del invalid["access"]["limitation"]

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_requires_direct_urls() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    del invalid["functions"][0]["direct_urls"]

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_accepts_explicit_no_same_function_fallback() -> None:
    profile = deepcopy(load_profile("official-example.yaml"))
    profile["functions"][0]["fallbacks"] = []

    errors = list(validator().iter_errors(profile))

    assert not errors


def test_profile_accepts_explicit_no_supported_functions() -> None:
    profile = deepcopy(load_profile("official-example.yaml"))
    profile["functions"] = []

    errors = list(validator().iter_errors(profile))

    assert not errors


def test_profile_rejects_invalid_evidence_level() -> None:
    invalid = deepcopy(load_profile("official-example.yaml"))
    invalid["access"]["evidence_level"] = "Unsupported"

    errors = list(validator().iter_errors(invalid))

    assert errors


def test_profile_accepts_explicit_observed_error_state() -> None:
    profile = deepcopy(load_profile("official-example.yaml"))
    profile["access"]["status"] = "temporarily-unreachable"
    profile["access"]["observed_error"] = {
        "state": "error",
        "category": "http",
        "message": "HTTP 503 from origin",
    }

    errors = list(validator().iter_errors(profile))

    assert not errors


def test_load_profiles_reports_the_invalid_file_path(tmp_path: Path) -> None:
    source_profiles = load_source_profiles_module()
    invalid = deepcopy(load_profile("official-example.yaml"))
    del invalid["functions"][0]["direct_urls"]
    invalid_path = tmp_path / "invalid.yaml"
    write_profile(invalid_path, invalid)

    with pytest.raises(ValueError, match=r"invalid\.yaml"):
        source_profiles.load_profiles(tmp_path, SCHEMA_PATH)


def test_load_profiles_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    source_profiles = load_source_profiles_module()
    write_profile(tmp_path / "official.yaml", load_profile("official-example.yaml"))
    duplicate = deepcopy(load_profile("aggregator-example.yaml"))
    duplicate["id"] = "sse"
    write_profile(tmp_path / "duplicate.yaml", duplicate)

    with pytest.raises(ValueError, match="duplicate source id"):
        source_profiles.load_profiles(tmp_path, SCHEMA_PATH)


def test_official_route_beats_reachable_aggregator_for_same_function() -> None:
    source_profiles = load_source_profiles_module()
    routes = source_profiles.select_routes(
        profiles=[
            load_profile("aggregator-example.yaml"),
            load_profile("official-example.yaml"),
        ],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert [route.source_id for route in routes] == ["sse", "eastmoney"]
    assert routes[0].authority == "High"
    assert routes[0].reachability == "reachable"
    assert routes[0].skip_reason is None


def test_fresh_temporarily_unreachable_route_is_skipped_for_fallback() -> None:
    source_profiles = load_source_profiles_module()
    official = deepcopy(load_profile("official-example.yaml"))
    official["access"]["status"] = "temporarily-unreachable"
    official["access"]["last_checked"] = "2026-08-02T11:00:00+00:00"
    official["access"]["observed_error"] = {
        "state": "error",
        "category": "http",
        "message": "HTTP 503 from origin",
    }
    routes = source_profiles.select_routes(
        profiles=[official, load_profile("aggregator-example.yaml")],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
    )

    assert [route.source_id for route in routes] == ["eastmoney", "sse"]
    assert routes[0].skip_reason is None
    assert routes[1].reachability == "temporarily-unreachable"
    assert routes[1].skip_reason == "fresh temporarily-unreachable"
    assert routes[1].stale is False


def test_stale_temporarily_unreachable_route_is_returned_for_refresh() -> None:
    source_profiles = load_source_profiles_module()
    official = deepcopy(load_profile("official-example.yaml"))
    official["access"]["status"] = "temporarily-unreachable"
    official["access"]["last_checked"] = "2026-08-01T10:00:00+00:00"
    official["access"]["observed_error"] = {
        "state": "error",
        "category": "http",
        "message": "HTTP 503 from origin",
    }
    routes = source_profiles.select_routes(
        profiles=[load_profile("aggregator-example.yaml"), official],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
    )

    assert [route.source_id for route in routes] == ["sse", "eastmoney"]
    assert routes[0].reachability == "temporarily-unreachable"
    assert routes[0].stale is True
    assert routes[0].skip_reason is None


def test_reachability_override_does_not_change_authority() -> None:
    source_profiles = load_source_profiles_module()
    routes = source_profiles.select_routes(
        profiles=[load_profile("official-example.yaml")],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        cache={
            "sse": {
                "status": "temporarily-unreachable",
                "last_checked": "2026-08-02T11:30:00+00:00",
            }
        },
    )

    assert len(routes) == 1
    assert routes[0].source_id == "sse"
    assert routes[0].authority == "High"
    assert routes[0].reachability == "temporarily-unreachable"
    assert routes[0].skip_reason == "fresh temporarily-unreachable"


def test_fresh_cache_observation_wins_over_reviewed_snapshot() -> None:
    source_profiles = load_source_profiles_module()
    routes = source_profiles.select_routes(
        profiles=[load_profile("official-example.yaml")],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        cache={
            "sse": {
                "status": "temporarily-unreachable",
                "last_checked": "2026-08-02T11:30:00+00:00",
            }
        },
        snapshot={
            "sse": {
                "status": "reachable-limited",
                "last_checked": "2026-08-02T10:00:00+00:00",
            }
        },
    )

    assert routes[0].reachability == "temporarily-unreachable"
    assert routes[0].skip_reason == "fresh temporarily-unreachable"
    assert routes[0].stale is False


def test_stale_cache_observation_falls_through_to_reviewed_snapshot() -> None:
    source_profiles = load_source_profiles_module()
    routes = source_profiles.select_routes(
        profiles=[load_profile("official-example.yaml")],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        cache={
            "sse": {
                "status": "anti-bot",
                "last_checked": "2026-07-01T00:00:00+00:00",
            }
        },
        snapshot={
            "sse": {
                "status": "temporarily-unreachable",
                "last_checked": "2026-08-02T11:30:00+00:00",
            }
        },
    )

    assert routes[0].reachability == "temporarily-unreachable"
    assert routes[0].skip_reason == "fresh temporarily-unreachable"
    assert routes[0].stale is False


def test_reviewed_snapshot_wins_over_conflicting_profile_access() -> None:
    source_profiles = load_source_profiles_module()
    routes = source_profiles.select_routes(
        profiles=[load_profile("official-example.yaml")],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        snapshot={
            "sse": {
                "status": "paywalled",
                "last_checked": "2026-08-02T11:30:00+00:00",
            }
        },
    )

    assert routes[0].reachability == "paywalled"
    assert routes[0].stale is False
    assert routes[0].skip_reason is None


def test_profile_access_is_used_when_cache_and_snapshot_are_absent() -> None:
    source_profiles = load_source_profiles_module()
    profile = deepcopy(load_profile("official-example.yaml"))
    profile["access"]["status"] = "reachable-limited"
    profile["access"]["last_checked"] = "2026-08-02T11:30:00+00:00"
    routes = source_profiles.select_routes(
        profiles=[profile],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
    )

    assert routes[0].reachability == "reachable-limited"
    assert routes[0].stale is False
    assert routes[0].skip_reason is None


def test_reachability_resolution_never_mutates_profile_metadata() -> None:
    source_profiles = load_source_profiles_module()
    profile = load_profile("official-example.yaml")
    original = deepcopy(profile)
    routes = source_profiles.select_routes(
        profiles=[profile],
        function_id="company-announcements",
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        cache={
            "sse": {
                "status": "temporarily-unreachable",
                "last_checked": "2026-08-02T11:30:00+00:00",
            }
        },
        snapshot={
            "sse": {
                "status": "paywalled",
                "last_checked": "2026-08-02T11:00:00+00:00",
            }
        },
    )

    function = profile["functions"][0]
    assert routes[0].authority == "High"
    assert routes[0].reachability == "temporarily-unreachable"
    assert profile == original
    assert profile["publisher_type"] == "official-exchange"
    assert function["citation"] == {
        "use": "direct",
        "required_fields": ["publisher", "title", "date", "document_id", "url"],
    }
    assert function["workflow_evidence"] == "High"
    assert function["field_contract_evidence"] == "Medium"


def test_approved_status_ttls_match_global_constraints() -> None:
    source_profiles = load_source_profiles_module()

    assert source_profiles.ttl_for_status("reachable") == timedelta(days=30)
    assert source_profiles.ttl_for_status("reachable-limited") == timedelta(days=30)
    assert source_profiles.ttl_for_status("login-required") == timedelta(days=14)
    assert source_profiles.ttl_for_status("paywalled") == timedelta(days=14)
    assert source_profiles.ttl_for_status("anti-bot") == timedelta(days=14)
    assert source_profiles.ttl_for_status("temporarily-unreachable") == timedelta(hours=24)
    assert source_profiles.ttl_for_status("moved") == timedelta(days=7)
    assert source_profiles.ttl_for_status("broken-link") == timedelta(days=7)
    assert source_profiles.ttl_for_status("unverified") == timedelta(hours=24)


@pytest.mark.parametrize(
    "scenario_name",
    ["guizhou-moutai.yaml", "pop-mart.yaml"],
)
def test_company_research_scenarios_select_citable_routes_and_safe_fallbacks(
    scenario_name: str,
) -> None:
    source_profiles = load_source_profiles_module()
    scenario = load_scenario(scenario_name)
    profiles = load_maintained_profiles()
    profiles_by_id = {profile["id"]: profile for profile in profiles}
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(scenario["as_of"])
    assert now.tzinfo is not None
    assert now.utcoffset() is not None

    forbidden_final_citations = set(scenario["forbidden_discovery_only_final_citations"])
    for requirement in scenario["required_functions"]:
        function_id = requirement["function_id"]
        expected_first_choice = requirement["expected_first_choice"]
        candidate_profiles = [
            profiles_by_id[source_id] for source_id in requirement["candidate_source_ids"]
        ]
        routes = source_profiles.select_routes(
            profiles=candidate_profiles,
            function_id=function_id,
            now=now,
            snapshot=snapshot,
        )

        assert routes, f"{scenario['id']}: no route for {function_id}"
        assert routes[0].source_id == expected_first_choice["source_id"]
        assert (
            profiles_by_id[routes[0].source_id]["publisher_type"]
            == expected_first_choice["publisher_type"]
        )
        assert routes[0].skip_reason == expected_first_choice["skip_reason"]

        if requirement["expects_final_citation"]:
            assert routes[0].skip_reason is None
            assert routes[0].source_id not in forbidden_final_citations

        temporary_unavailability = requirement.get("temporary_unavailability")
        if temporary_unavailability is None:
            continue

        outage_snapshot = dict(snapshot)
        outage_snapshot[temporary_unavailability["source_id"]] = {
            "status": "temporarily-unreachable",
            "last_checked": temporary_unavailability["last_checked"],
        }
        outage_candidate_profiles = [
            profiles_by_id[source_id]
            for source_id in temporary_unavailability["candidate_source_ids"]
        ]
        outage_routes = source_profiles.select_routes(
            profiles=outage_candidate_profiles,
            function_id=function_id,
            now=now,
            snapshot=outage_snapshot,
        )
        expected_outage_route = temporary_unavailability["expected_first_choice"]

        assert outage_routes, f"{scenario['id']}: no outage route for {function_id}"
        assert outage_routes[0].source_id == expected_outage_route["source_id"]
        assert (
            profiles_by_id[outage_routes[0].source_id]["publisher_type"]
            == expected_outage_route["publisher_type"]
        )
        assert outage_routes[0].skip_reason == expected_outage_route["skip_reason"]
        if expected_outage_route["skip_reason"] is None:
            assert outage_routes[0].source_id not in forbidden_final_citations
        assert {route.source_id for route in outage_routes}.isdisjoint(
            temporary_unavailability["forbidden_substitutes"]
        )


def test_maintained_catalog_has_one_profile_per_actual_website() -> None:
    profiles = load_maintained_profiles()

    assert len(profiles) == len(EXPECTED_PROFILE_IDS)
    assert {profile["id"] for profile in profiles} == EXPECTED_PROFILE_IDS


def test_supplied_and_existing_core_ids_remain_discoverable() -> None:
    discoverable: set[str] = set()
    for profile in load_maintained_profiles():
        discoverable.add(profile["id"])
        discoverable.update(profile["aliases"])

    expected_audit_ids = {
        *(f"U{number:02d}" for number in range(1, 64)),
        *(f"C{number:02d}" for number in range(1, 15)),
        "U24-Deloitte",
        "U24-EY",
        "U24-KPMG",
        "U24-PwC",
        "U43-PwC",
        "U43-Pew",
    }
    expected_code_origins = {
        "sse",
        "szse",
        "pbc",
        "hkex",
        "csrc",
        "mof",
        "nfra",
        "chinamoney",
        "sfc",
        "afrc",
        "hkma",
        "ia",
        "hkpf",
        "icac",
        "hkjd",
    }
    expected_raw_origins = {
        "supplied U24a Deloitte China",
        "supplied U24b EY China",
        "supplied U24c KPMG China",
        "supplied U24d PwC China",
        "download_filings STOCK_LIST_URL, ANNOUNCEMENT_QUERY_URL, PDF_BASE_URL; "
        "domains cninfo.com.cn and static.cninfo.com.cn",
        "build_event_manifest hkex; build_market_manifest hkex; download_filings "
        "HKEX_SEARCH_URL, HKEX_BASE_URL, HKEX_ACTIVE_STOCK_URL; "
        "domains hkex.com.hk and hkexnews.hk",
    }

    assert expected_audit_ids <= discoverable
    assert expected_code_origins <= discoverable
    assert expected_raw_origins <= discoverable


def test_maintained_profiles_preserve_reviewed_probe_facts() -> None:
    required_probe_fields = {
        "redirect_chain",
        "response_status",
        "recognizable_content",
        "access_indications",
        "technical_restriction",
    }

    for profile in load_maintained_profiles():
        reviewed_probe = profile["access"]["reviewed_probe"]
        assert set(reviewed_probe) == required_probe_fields, profile["id"]
        assert all(reviewed_probe.values()), profile["id"]


def test_every_material_function_has_routes_search_and_resolved_fallbacks() -> None:
    profiles = load_maintained_profiles()
    exported_functions = {
        f"{profile['id']}-{function['id']}"
        for profile in profiles
        for function in profile["functions"]
    }

    for profile in profiles:
        for function in profile["functions"]:
            assert function["direct_urls"]
            assert function["search"]["example_query"].strip()
            for fallback in function["fallbacks"]:
                assert fallback in exported_functions
                assert fallback != f"{profile['id']}-{function['id']}"


def test_seed_fallbacks_use_audited_same_topic_routes() -> None:
    profiles = load_maintained_profiles()
    functions = {
        f"{profile['id']}-{function['id']}": function
        for profile in profiles
        for function in profile["functions"]
    }
    expected_fallbacks = {
        "36kr-research-reports": {"it-juzi-research-reports"},
        "flurry-research-reports": {"analysys-research-reports"},
        "state-council-regulatory-materials": {"ministry-of-finance-regulatory-materials"},
        "xueqiu-research-reports": {"eastmoney-research-research-reports"},
    }

    for exported_function, expected in expected_fallbacks.items():
        assert exported_function in functions
        assert expected <= set(functions[exported_function]["fallbacks"])


def test_conservative_seed_profiles_preserve_discoverability_without_overclaiming_functions() -> (
    None
):
    source_profiles = load_source_profiles_module()
    profiles = load_maintained_profiles()
    by_id = {profile["id"]: profile for profile in profiles}

    housing_tools = by_id["199it-housing-tools"]
    assert "U42" in housing_tools["aliases"]
    assert [function["id"] for function in housing_tools["functions"]] == ["housing-data-directory"]
    official_statistics_routes = source_profiles.select_routes(
        profiles=profiles,
        function_id="official-statistics",
        now=datetime(2026, 8, 2, tzinfo=UTC),
    )
    assert "199it-housing-tools" not in {route.source_id for route in official_statistics_routes}

    assert [function["id"] for function in by_id["360-security-reports"]["functions"]] == [
        "security-threat-reports"
    ]
    assert [function["id"] for function in by_id["cadas"]["functions"]] == ["aviation-analysis"]
    assert [function["id"] for function in by_id["gsma-mobile-economy"]["functions"]] == [
        "telecom-industry-reports"
    ]


def test_core_seed_profiles_only_export_functions_with_audited_direct_entrypoints() -> None:
    profiles = load_maintained_profiles()
    functions = {
        f"{profile['id']}-{function['id']}": function
        for profile in profiles
        for function in profile["functions"]
    }

    expected_first_direct_urls = {
        "hkexnews-company-disclosures": "https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en",
        "sse-company-disclosures": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
        "sse-regulatory-materials": "https://www.sse.com.cn/regulation/supervision/inquiries/",
        "sec-edgar-company-disclosures": "https://www.sec.gov/edgar/search/",
        "caict-official-statistics": "https://www.caict.ac.cn/kxyj/qwfb/qwsj/",
    }
    removed_without_direct_entry = {
        "hkex-company-disclosures",
        "hkex-regulatory-materials",
        "hkex-market-data",
        "sse-market-data",
        "szse-regulatory-materials",
        "szse-market-data",
        "pbc-market-data",
        "hkma-market-data",
        "sec-edgar-regulatory-materials",
        "caict-research-reports",
    }

    for exported_function, expected_url in expected_first_direct_urls.items():
        assert exported_function in functions
        assert functions[exported_function]["direct_urls"][0]["url"] == expected_url

    for exported_function in removed_without_direct_entry:
        assert exported_function not in functions


def test_specialist_seed_functions_do_not_claim_generic_research_equivalence() -> None:
    profiles = load_maintained_profiles()
    functions = {
        f"{profile['id']}-{function['id']}": function
        for profile in profiles
        for function in profile["functions"]
    }

    assert functions["199it-housing-tools-housing-data-directory"]["fallbacks"] == []
    assert functions["360-security-reports-security-threat-reports"]["fallbacks"] == []
    assert functions["cadas-aviation-analysis"]["fallbacks"] == []
    assert functions["gsma-mobile-economy-telecom-industry-reports"]["fallbacks"] == []


def test_task_5_round_1_keeps_homepage_only_sources_identity_only() -> None:
    profiles = {profile["id"]: profile for profile in load_maintained_profiles()}

    for source_id in (
        "ministry-culture-tourism",
        "mofcom",
        "national-film-administration",
        "state-post-bureau",
        "eastmoney-securities",
    ):
        assert profiles[source_id]["functions"] == []


def test_task_5_round_1_preserves_market_specific_eastmoney_routes_and_fallbacks() -> None:
    profiles = {profile["id"]: profile for profile in load_maintained_profiles()}
    quote_functions = {
        function["id"]: function for function in profiles["eastmoney-quotes-f10"]["functions"]
    }
    announcement_functions = {
        function["id"]: function
        for function in profiles["eastmoney-announcement-index"]["functions"]
    }

    assert quote_functions["a-share-quote-display"]["direct_urls"][0]["url"] == (
        "https://quote.eastmoney.com/sh600519.html"
    )
    assert quote_functions["a-share-company-information-display"]["direct_urls"][0]["url"] == (
        "https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html"
        "?type=web&code=SH600519&color=b#/gsgk"
    )
    assert quote_functions["hong-kong-quote-display"]["direct_urls"][0]["url"] == (
        "https://quote.eastmoney.com/hk/09992.html"
    )
    assert quote_functions["hong-kong-quote-display"]["fallbacks"] == [
        "hkex-market-data-official-market-data"
    ]
    assert quote_functions["hong-kong-company-information-display"]["direct_urls"][0]["url"] == (
        "https://emweb.securities.eastmoney.com/PC_HKF10/pages/home/index.html"
        "?code=09992&type=web&color=w#/CompanyProfile"
    )
    assert quote_functions["a-share-quote-display"]["fallbacks"] == []
    assert quote_functions["a-share-company-information-display"]["fallbacks"] == []
    assert quote_functions["hong-kong-company-information-display"]["fallbacks"] == []

    assert announcement_functions["a-share-announcement-index"]["direct_urls"][0]["url"] == (
        "https://data.eastmoney.com/notices/stock/600519.html"
    )
    assert announcement_functions["a-share-announcement-index"]["fallbacks"] == [
        "sse-company-disclosures",
        "szse-company-disclosures",
        "cninfo-company-disclosures",
    ]
    assert announcement_functions["hong-kong-announcement-index"]["direct_urls"][0]["url"] == (
        "https://data.eastmoney.com/notices/stock/09992.html"
    )
    assert announcement_functions["hong-kong-announcement-index"]["fallbacks"] == [
        "hkexnews-company-disclosures"
    ]

    assert profiles["data-gov-hk"]["functions"][0]["fallbacks"] == []
    assert profiles["aastocks"]["functions"][0]["fallbacks"] == []


def test_task_5_round_1_separates_authority_access_workflow_and_field_evidence() -> None:
    profiles = {profile["id"]: profile for profile in load_maintained_profiles()}
    di = profiles["hkex-di"]
    di_function = di["functions"][0]

    assert di["authority"]["level"] == "High"
    assert di["access"]["evidence_level"] == "High"
    assert di_function["workflow_evidence"] == "Low"
    assert di_function["field_contract_evidence"] == "Low"

    for profile in profiles.values():
        for function in profile["functions"]:
            assert function["workflow_evidence"] in {"High", "Medium", "Low"}
            assert function["field_contract_evidence"] in {"High", "Medium", "Low"}


def test_task_5_round_2_limits_uncompleted_workflow_evidence() -> None:
    profiles = {profile["id"]: profile for profile in load_maintained_profiles()}
    evidence_by_function = {
        f"{profile['id']}-{function['id']}": (
            function["workflow_evidence"],
            function["field_contract_evidence"],
        )
        for profile in profiles.values()
        for function in profile["functions"]
    }

    # These routes reached only a WAF, failed export, SPA shell, or uninspected
    # search surface in the audit; none completed a cited record/data workflow.
    assert evidence_by_function["aliresearch-research-reports"] == ("Low", "Low")
    assert evidence_by_function["undata-official-statistics"] == ("Low", "Low")
    assert evidence_by_function["wto-stats-official-statistics"] == ("Low", "Low")

    # This set is deliberately report-derived rather than inferred from a
    # reachability status: its members exposed only entry, search-card, or
    # incomplete-record evidence for the exported function.
    assert {
        function_id: evidence_by_function[function_id]
        for function_id in (
            "199it-housing-tools-housing-data-directory",
            "199it-research-reports",
            "afrc-regulatory-materials",
            "bain-china-research-reports",
            "beijing-government-regulatory-materials",
            "caac-official-aviation-statistics",
            "china-money-market-data",
            "csrc-regulatory-materials",
            "data-gov-hk-dataset-catalog",
            "guangdong-government-regulatory-materials",
            "hk-icac-regulatory-materials",
            "hk-judiciary-regulatory-materials",
            "hk-police-regulatory-materials",
            "hkex-ccass-ccass-participant-holdings",
            "hkex-market-data-official-market-data",
            "hkexnews-company-disclosures",
            "hksar-press-releases-government-press-releases",
            "hong-kong-consumer-council-consumer-research",
            "hong-kong-statistics-official-statistics",
            "ministry-of-finance-regulatory-materials",
            "national-bureau-statistics-official-statistics",
            "nfra-regulatory-materials",
            "nrta-audiovisual-regulation",
            "pbc-central-bank-policy-search",
            "pew-research-research-reports",
            "sfc-regulatory-materials",
            "shanghai-government-regulatory-materials",
            "sina-finance-research-reports",
            "unsd-demographic-social-official-statistics",
            "wef-china-research-reports",
            "szse-company-disclosures",
        )
    } == {
        "199it-housing-tools-housing-data-directory": ("Medium", "Low"),
        "199it-research-reports": ("Medium", "Low"),
        "afrc-regulatory-materials": ("Medium", "Medium"),
        "bain-china-research-reports": ("Medium", "Medium"),
        "beijing-government-regulatory-materials": ("Medium", "Low"),
        "caac-official-aviation-statistics": ("Medium", "Medium"),
        "china-money-market-data": ("Medium", "Low"),
        "csrc-regulatory-materials": ("Medium", "Low"),
        "data-gov-hk-dataset-catalog": ("Medium", "Medium"),
        "guangdong-government-regulatory-materials": ("Medium", "Low"),
        "hk-icac-regulatory-materials": ("Medium", "Low"),
        "hk-judiciary-regulatory-materials": ("Medium", "Low"),
        "hk-police-regulatory-materials": ("Medium", "Low"),
        "hkex-ccass-ccass-participant-holdings": ("Medium", "Medium"),
        "hkex-market-data-official-market-data": ("Medium", "Medium"),
        "hkexnews-company-disclosures": ("Medium", "Medium"),
        "hksar-press-releases-government-press-releases": ("Medium", "Medium"),
        "hong-kong-consumer-council-consumer-research": ("Medium", "Medium"),
        "hong-kong-statistics-official-statistics": ("Medium", "Medium"),
        "ministry-of-finance-regulatory-materials": ("Medium", "Low"),
        "national-bureau-statistics-official-statistics": ("Medium", "Low"),
        "nfra-regulatory-materials": ("Medium", "Low"),
        "nrta-audiovisual-regulation": ("Medium", "Medium"),
        "pbc-central-bank-policy-search": ("Medium", "Medium"),
        "pew-research-research-reports": ("Medium", "Low"),
        "sfc-regulatory-materials": ("Medium", "Medium"),
        "shanghai-government-regulatory-materials": ("Medium", "Low"),
        "sina-finance-research-reports": ("Medium", "Medium"),
        "unsd-demographic-social-official-statistics": ("Medium", "Low"),
        "wef-china-research-reports": ("Medium", "Low"),
        "szse-company-disclosures": ("Medium", "Medium"),
    }


def test_publisher_semantics_are_closed_and_explicit_for_every_profile_type() -> None:
    source_profiles = load_source_profiles_module()
    schema_types = set(load_schema()["properties"]["publisher_type"]["enum"])
    profile_types = {profile["publisher_type"] for profile in load_maintained_profiles()}

    assert source_profiles.PUBLISHER_SEMANTICS == EXPECTED_PUBLISHER_SEMANTICS
    assert schema_types == set(EXPECTED_PUBLISHER_SEMANTICS)
    assert profile_types <= schema_types


def test_unknown_publisher_type_cannot_receive_route_semantics() -> None:
    source_profiles = load_source_profiles_module()
    unknown = deepcopy(load_profile("official-example.yaml"))
    unknown["publisher_type"] = "new-unknown-type"

    assert list(validator().iter_errors(unknown))
    with pytest.raises(ValueError, match="unsupported publisher type"):
        source_profiles.select_routes(
            profiles=[unknown],
            function_id="company-announcements",
            now=datetime(2026, 8, 2, tzinfo=UTC),
        )


def test_reviewed_snapshot_contains_only_known_sources_and_statuses() -> None:
    profiles = load_maintained_profiles()
    known_source_ids = {profile["id"] for profile in profiles}
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert set(snapshot) <= known_source_ids
    assert set(snapshot) == known_source_ids
    for source_id, observation in snapshot.items():
        assert observation["status"] in APPROVED_STATUSES, source_id
        assert observation["evidence_level"] in {"High", "Medium", "Low"}, source_id
