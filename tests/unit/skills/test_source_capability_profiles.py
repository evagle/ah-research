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
