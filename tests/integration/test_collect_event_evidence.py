from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts import build_event_manifest, collect_event_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_PATH = REPO_ROOT / "scripts" / "collect_event_evidence.py"
SCHEMA_PATH = REPO_ROOT / ".claude/skills/read-filing/references/event-query-plan.schema.json"


def test_query_plan_schema_accepts_open_investigations_before_window():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    event_query = {
        "category": "auditor_investigations",
        "source_id": "csrc",
        "scope": "rolling_3y",
        "query_start": "2023-04-30",
        "query_end": "2026-04-30",
        "query_url": "https://www.csrc.gov.cn/auditor_investigation",
        "http_method": "GET",
        "request_encoding": "query",
        "response_schema": "canonical_event_page_v1",
        "query_params": {
            "issuer_code": "000001",
            "include_open_before_start": True,
        },
        "query_issuer_code": "000001",
        "query_subject_ids": ["auditor:firm-1"],
    }

    Draft202012Validator(schema["$defs"]["eventQuery"]).validate(event_query)


def test_query_plan_rejects_unauthenticated_top_level_listing_dates(tmp_path):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    plan = {
        "schema_version": 1,
        "ticker": "000001.SZ",
        "exchange": "SZ",
        "AS_OF": "2026-04-30",
        "query_issuer_code": "000001",
        "issuer_type": "bank",
        "listing_dates": {"SZ": "1991-04-03"},
        "listing_profile": {
            "source_url": "https://www.szse.cn/profile",
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": {"issuer_code": "000001"},
            "response_schema": "canonical_listing_profile_v1",
        },
        "subject_roster": {
            "source_url": "https://www.szse.cn/roster",
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": {"issuer_code": "000001"},
            "response_schema": "canonical_subject_roster_v1",
        },
        "categories": [{} for _ in range(8)],
    }

    errors = list(Draft202012Validator(schema).iter_errors(plan))

    assert any(
        "listing_dates" in error.message
        and "Additional properties are not allowed" in error.message
        for error in errors
    )
    plan_path = tmp_path / "query-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(
        collect_event_evidence.CollectionError,
        match="must come from the official listing profile response",
    ):
        collect_event_evidence._read_plan(plan_path)


def test_single_query_preserves_post_json_contract():
    calls = []
    row = {
        "source_url": "https://www.szse.cn/profile",
        "http_method": "POST",
        "request_encoding": "json",
        "query_params": {"stock": "000001"},
        "response_schema": "canonical_listing_profile_v1",
    }

    body = collect_event_evidence._fetch_one(
        row,
        lambda url, method, encoding, params, contract: (
            calls.append((url, method, encoding, params, contract)) or [b'{"ok":true}']
        ),
    )

    assert body == b'{"ok":true}'
    assert calls[0][1:3] == ("POST", "json")


def test_query_plan_schema_requires_builder_complete_roster_and_subjects():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    plan = {
        "schema_version": 1,
        "ticker": "000001.SZ",
        "exchange": "SZ",
        "AS_OF": "2026-04-30",
        "query_issuer_code": "000001",
        "issuer_type": "non_bank",
        "listing_profile": {
            "source_url": "https://www.szse.cn/profile",
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": {"issuer_code": "000001"},
            "response_schema": "canonical_listing_profile_v1",
        },
        "subject_roster": {
            "source_url": "https://www.szse.cn/roster",
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": {"issuer_code": "000001"},
            "response_schema": "canonical_subject_roster_v1",
        },
        "categories": [
            {
                "category": f"category-{index}",
                "source_id": "szse",
                "scope": "rolling_3y",
                "query_start": "2023-04-30",
                "query_end": "2026-04-30",
                "query_url": "https://www.szse.cn/events",
                "http_method": "GET",
                "request_encoding": "query",
                "response_schema": "canonical_event_page_v1",
                "query_params": {"issuer_code": "000001"},
                "query_issuer_code": "000001",
            }
            for index in range(8)
        ],
    }

    errors = list(Draft202012Validator(schema).iter_errors(plan))
    error_paths = {tuple(error.absolute_path) for error in errors}

    for field in (
        "coverage_start",
        "coverage_end",
        "management_history_complete",
        "controller_history_complete",
        "management_roles_covered",
        "controller_status",
    ):
        assert ("subject_roster",) in error_paths
        assert any(f"'{field}' is a required property" in error.message for error in errors)
    assert all(("categories", index) in error_paths for index in range(8))
    assert (
        sum("'query_subject_ids' is a required property" in error.message for error in errors) == 8
    )


def test_collector_rejects_unsafe_plan_before_network_or_storage(tmp_path):
    calls = []
    plan = {
        "schema_version": 1,
        "ticker": "000001.SZ",
        "exchange": "SZ",
        "AS_OF": "2026-04-30",
        "query_issuer_code": "000001",
        "issuer_type": "non_bank",
        "listing_profile": {
            "source_url": "https://attacker.example/profile",
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": {"issuer_code": "000001"},
            "response_schema": "canonical_listing_profile_v1",
        },
        "subject_roster": {
            "coverage_start": "1991-04-03",
            "coverage_end": "2026-04-30",
            "management_history_complete": True,
            "controller_history_complete": True,
            "management_roles_covered": [
                "director",
                "senior_management",
                "chair",
                "cfo",
            ],
            "controller_status": "none_identified",
            "source_url": "https://attacker.example/roster",
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": {"issuer_code": "000001"},
            "response_schema": "canonical_subject_roster_v1",
        },
        "categories": [
            {
                "category": "../escape",
                "source_id": "../source",
                "scope": "listing_history",
                "query_start": "1991-04-03",
                "query_end": "2026-04-30",
                "query_url": "https://attacker.example/events",
                "http_method": "GET",
                "request_encoding": "query",
                "response_schema": "canonical_event_page_v1",
                "query_params": {"issuer_code": "000001"},
                "query_issuer_code": "000001",
                "query_subject_ids": ["issuer:000001"],
            }
            for _ in range(8)
        ],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    evidence_dir = tmp_path / "evidence"

    with pytest.raises(collect_event_evidence.CollectionError):
        collect_event_evidence.collect_evidence(
            plan_path,
            tmp_path / "bundle.json",
            evidence_dir,
            response_fetcher=lambda *_args: calls.append(_args) or [],
        )

    assert calls == []
    assert not evidence_dir.exists()


def test_shared_identity_endpoint_preserves_each_query_contract(
    tmp_path,
    monkeypatch,
):
    endpoint = "https://www.szse.cn/issuer"
    listing_query = {"stock": "000001", "view": "profile"}
    roster_query = {
        "stock": "000001",
        "view": "roster",
        "from": "1991-04-03",
        "to": "2026-04-30",
    }
    listing_body = json.dumps(
        {
            "issuer_code": "000001",
            "listing_codes": {"SZ": "000001"},
            "listing_date": "1991-04-03",
            "listing_dates": {"SZ": "1991-04-03"},
            "official_result_total": 1,
        }
    ).encode()
    roster_body = json.dumps({"subjects": [{"id": "issuer:000001"}]}).encode()
    plan = {
        "schema_version": 1,
        "ticker": "000001.SZ",
        "exchange": "SZ",
        "AS_OF": "2026-04-30",
        "query_issuer_code": "000001",
        "issuer_type": "non_bank",
        "listing_profile": {
            "source_url": endpoint,
            "http_method": "POST",
            "request_encoding": "json",
            "query_params": listing_query,
            "response_schema": "canonical_listing_profile_v1",
        },
        "subject_roster": {
            "coverage_start": "1991-04-03",
            "coverage_end": "2026-04-30",
            "management_history_complete": True,
            "controller_history_complete": True,
            "management_roles_covered": ["chair", "cfo"],
            "controller_status": "none_identified",
            "source_url": endpoint,
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": roster_query,
            "response_schema": "canonical_subject_roster_v1",
        },
        "categories": [
            {
                "category": category,
                "source_id": "szse",
                "scope": (
                    "listing_history"
                    if category in {"formal_sanctions", "related_party_harm"}
                    else "rolling_3y"
                ),
                "query_start": (
                    "1991-04-03"
                    if category in {"formal_sanctions", "related_party_harm"}
                    else "2023-04-30"
                ),
                "query_end": "2026-04-30",
                "query_url": f"https://www.szse.cn/{category}",
                "http_method": "GET",
                "request_encoding": "query",
                "response_schema": "canonical_event_page_v1",
                "query_params": {
                    "issuer_code": "000001",
                    "category": category,
                    **(
                        {"include_open_before_start": True}
                        if category not in {"formal_sanctions", "related_party_harm"}
                        else {}
                    ),
                },
                "query_issuer_code": "000001",
                "query_subject_ids": ["issuer:000001"],
            }
            for category in build_event_manifest.REQUIRED_SCOPES
        ],
    }
    plan_path = tmp_path / "query-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    def fetcher(url, method, encoding, params, _contract):
        if (url, method, encoding, params) == (
            endpoint,
            "POST",
            "json",
            listing_query,
        ):
            return [listing_body]
        if (url, method, encoding, params) == (
            endpoint,
            "GET",
            "query",
            roster_query,
        ):
            return [roster_body]
        return [
            json.dumps(
                {
                    "query": params,
                    "page_no": 1,
                    "page_count": 1,
                    "total": 0,
                    "results": [],
                }
            ).encode()
        ]

    def validate_handoff(
        _bundle_path,
        *,
        roster_fetcher,
        event_fetcher,
        document_fetcher,
    ):
        assert roster_fetcher(endpoint, listing_query) == listing_body
        assert roster_fetcher(endpoint, roster_query) == roster_body

    monkeypatch.setattr(
        build_event_manifest,
        "build_manifest",
        validate_handoff,
    )

    published = collect_event_evidence.collect_evidence(
        plan_path,
        tmp_path / "bundle.json",
        tmp_path / "evidence",
        response_fetcher=fetcher,
        document_fetcher=lambda _url: b"",
    )

    assert published.is_file()


def test_default_fetcher_executes_post_json_profile_contract(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://www.szse.cn/profile"

        def read(self):
            return b'{"ok":true}'

    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr(
        build_event_manifest.urllib.request,
        "urlopen",
        open_request,
    )

    bodies = collect_event_evidence._default_response_fetcher(
        "https://www.szse.cn/profile",
        "POST",
        "json",
        {"stock": "000001"},
        {"response_schema": "canonical_listing_profile_v1"},
    )

    request, timeout = requests[0]
    assert bodies == [b'{"ok":true}']
    assert timeout == 30
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"stock": "000001"}
    assert request.get_header("Content-type") == "application/json"


def test_query_plan_and_collector_require_explicit_issuer_type(tmp_path):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert "issuer_type" in schema["required"]

    plan = {
        "schema_version": 1,
        "ticker": "000001.SZ",
        "exchange": "SZ",
        "AS_OF": "2026-04-30",
        "query_issuer_code": "000001",
        "listing_profile": {},
        "subject_roster": {},
        "categories": [],
    }
    plan_path = tmp_path / "query-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(
        collect_event_evidence.CollectionError,
        match="issuer_type",
    ):
        collect_event_evidence._read_plan(plan_path)


def test_collector_builds_valid_bundle_from_official_query_plan(tmp_path):
    assert COLLECTOR_PATH.is_file(), "event evidence collector CLI is missing"
    assert SCHEMA_PATH.is_file(), "versioned event query-plan schema is missing"
    spec = importlib.util.spec_from_file_location(
        "collect_event_evidence",
        COLLECTOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)

    subjects = [
        {
            "id": "issuer:000001",
            "type": "issuer",
            "name": "平安银行",
            "role": "issuer",
            "official_id": "issuer-000001",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "manager:chair",
            "type": "management",
            "name": "董事长甲",
            "role": "chair",
            "official_id": "chair-1",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "manager:cfo",
            "type": "management",
            "name": "财务负责人乙",
            "role": "cfo",
            "official_id": "cfo-1",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "auditor:firm-1",
            "type": "auditor",
            "name": "审计机构丙",
            "role": "auditor",
            "official_id": "firm-1",
            "service_start": "1991-04-03",
            "service_end": None,
        },
    ]
    subject_ids = [subject["id"] for subject in subjects]
    listing_query = {"issuer_code": "000001"}
    roster_query = {
        "issuer_code": "000001",
        "start_date": "1991-04-03",
        "end_date": "2026-04-30",
    }
    listing_url = "https://www.cninfo.com.cn/issuer/000001/profile"
    roster_url = "https://www.cninfo.com.cn/issuer/000001/roster"
    responses = {
        listing_url: [
            json.dumps(
                {
                    "query": listing_query,
                    "issuer_code": "000001",
                    "listing_codes": {"SZ": "000001"},
                    "listing_date": "1991-04-03",
                    "listing_dates": {"SZ": "1991-04-03"},
                    "official_result_total": 1,
                }
            ).encode()
        ],
        roster_url: [
            json.dumps(
                {
                    "query": roster_query,
                    "coverage_start": "1991-04-03",
                    "coverage_end": "2026-04-30",
                    "management_history_complete": True,
                    "controller_history_complete": True,
                    "management_roles_covered": [
                        "director",
                        "senior_management",
                        "chair",
                        "cfo",
                    ],
                    "controller_status": "none_identified",
                    "official_result_total": len(subjects),
                    "subjects": subjects,
                }
            ).encode()
        ],
    }
    source_hosts = {
        "csrc": "www.csrc.gov.cn",
        "mof": "www.mof.gov.cn",
        "nfra": "www.nfra.gov.cn",
        "pbc": "www.pbc.gov.cn",
        "szse": "www.szse.cn",
    }
    categories = []
    for category, source_ids in build_event_manifest.REQUIRED_SOURCE_IDS["SZ"].items():
        query_start = (
            "1991-04-03"
            if build_event_manifest.REQUIRED_SCOPES[category] == "listing_history"
            else "2023-04-30"
        )
        required_source_ids = set(source_ids)
        required_source_ids.update(build_event_manifest.BANK_SOURCE_IDS["SZ"].get(category, set()))
        for source_id in sorted(required_source_ids):
            url = f"https://{source_hosts[source_id]}/{category}"
            query = {
                "issuer_code": "000001",
                "subject_ids": subject_ids,
                "category": category,
                "start_date": query_start,
                "end_date": "2026-04-30",
            }
            if build_event_manifest.REQUIRED_SCOPES[category] == "rolling_3y":
                query["include_open_before_start"] = True
            responses[url] = [
                json.dumps(
                    {
                        "query": query,
                        "page_no": 1,
                        "page_count": 1,
                        "total": 0,
                        "results": [],
                    }
                ).encode()
            ]
            categories.append(
                {
                    "category": category,
                    "source_id": source_id,
                    "scope": build_event_manifest.REQUIRED_SCOPES[category],
                    "query_start": query_start,
                    "query_end": "2026-04-30",
                    "query_url": url,
                    "http_method": "GET",
                    "request_encoding": "query",
                    "response_schema": "canonical_event_page_v1",
                    "query_params": query,
                    "query_issuer_code": "000001",
                    "query_subject_ids": subject_ids,
                }
            )
    plan = {
        "schema_version": 1,
        "ticker": "000001.SZ",
        "exchange": "SZ",
        "AS_OF": "2026-04-30",
        "query_issuer_code": "000001",
        "issuer_type": "bank",
        "listing_profile": {
            "source_url": listing_url,
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": listing_query,
            "response_schema": "canonical_listing_profile_v1",
        },
        "subject_roster": {
            "coverage_start": "1991-04-03",
            "coverage_end": "2026-04-30",
            "management_history_complete": True,
            "controller_history_complete": True,
            "management_roles_covered": [
                "director",
                "senior_management",
                "chair",
                "cfo",
            ],
            "controller_status": "none_identified",
            "source_url": roster_url,
            "http_method": "GET",
            "request_encoding": "query",
            "query_params": roster_query,
            "response_schema": "canonical_subject_roster_v1",
        },
        "categories": categories,
    }
    plan_path = tmp_path / "query-plan.json"
    bundle_path = tmp_path / "bundle.json"
    evidence_dir = tmp_path / "evidence"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    published = collector.collect_evidence(
        plan_path,
        bundle_path,
        evidence_dir,
        response_fetcher=lambda url, _method, _encoding, _params, _contract: responses[url],
        document_fetcher=lambda _url: b"",
    )

    assert published == bundle_path
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["listing_date"] == "1991-04-03"
    assert bundle["listing_codes"] == {"SZ": "000001"}
    assert bundle["listing_dates"] == {"SZ": "1991-04-03"}
    assert bundle["subjects"] == subjects
    assert all(
        Path(path).is_file() for row in bundle["categories"] for path in row["response_files"]
    )
    manifest = build_event_manifest.build_manifest(
        bundle_path,
        roster_fetcher=lambda url, _params: responses[url][0],
        event_fetcher=lambda url, _method, _encoding, _params, _contract: responses[url],
        document_fetcher=lambda _url: b"",
    )
    assert manifest["listing_history_complete"] is True


def test_query_plan_schema_accepts_native_subject_coverage():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    event_query = {
        "category": "formal_sanctions",
        "source_id": "csrc",
        "scope": "listing_history",
        "query_start": "1991-04-03",
        "query_end": "2026-04-30",
        "query_url": "https://www.csrc.gov.cn/formal_sanctions",
        "http_method": "POST",
        "request_encoding": "json",
        "response_schema": "native_json_event_page_v1",
        "response_adapter": {},
        "query_params": {"stock": "000001"},
        "query_issuer_code": "000001",
        "query_subject_ids": ["issuer:000001"],
    }

    Draft202012Validator(schema["$defs"]["eventQuery"]).validate(event_query)


def test_collector_extracts_listing_and_subjects_through_native_adapters(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "collect_event_evidence_native",
        COLLECTOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)

    listing_plan = {
        "source_url": "https://www.szse.cn/profile",
        "query_params": {"stock": "000001"},
        "response_schema": "native_json_listing_profile_v1",
        "response_adapter": {
            "field_paths": {
                "issuer_code": "data.code",
                "listing_codes": "data.codes",
                "listing_date": "data.listed",
                "listing_dates": "data.dates",
                "listing_statuses": "data.statuses",
                "delisting_dates": "data.delistings",
                "official_result_total": "meta.total",
            },
        },
    }
    subjects = [
        {
            "id": "issuer:000001",
            "type": "issuer",
            "name": "平安银行",
            "role": "issuer",
            "official_id": "issuer-000001",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "manager:chair",
            "type": "management",
            "name": "董事长甲",
            "role": "chair",
            "official_id": "chair-1",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "manager:cfo",
            "type": "management",
            "name": "财务负责人乙",
            "role": "cfo",
            "official_id": "cfo-1",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "auditor:firm-1",
            "type": "auditor",
            "name": "审计机构丙",
            "role": "auditor",
            "official_id": "firm-1",
            "service_start": "1991-04-03",
            "service_end": None,
        },
    ]
    roster_plan = {
        "coverage_start": "1991-04-03",
        "coverage_end": "2026-04-30",
        "management_history_complete": True,
        "controller_history_complete": True,
        "management_roles_covered": [
            "director",
            "senior_management",
            "chair",
            "cfo",
        ],
        "controller_status": "none_identified",
        "source_url": "https://www.szse.cn/roster",
        "query_params": {
            "stock": "000001",
            "from": "1991-04-03",
            "to": "2026-04-30",
        },
        "response_schema": "native_json_roster_v1",
        "response_adapter": {
            "results_path": "data.people",
            "total_path": "meta.total",
            "request_bindings": {
                "issuer": "stock",
                "start_date": "from",
                "end_date": "to",
            },
            "field_paths": {
                "official_id": "officialId",
                "name": "name",
                "type": "type",
                "role": "role",
                "service_start": "start",
                "service_end": "end",
            },
        },
        "declared_subjects": subjects,
    }
    listing_body = json.dumps(
        {
            "data": {
                "code": "000001",
                "codes": {"SZ": "000001"},
                "listed": "1991-04-03",
                "dates": {"SZ": "1991-04-03"},
                "statuses": {"SZ": "listed"},
                "delistings": {"SZ": None},
            },
            "meta": {"total": 1},
        }
    ).encode()
    roster_body = json.dumps(
        {
            "data": {
                "people": [
                    {
                        "officialId": subject["official_id"],
                        "name": subject["name"],
                        "type": subject["type"],
                        "role": subject["role"],
                        "start": subject["service_start"],
                        "end": subject["service_end"],
                    }
                    for subject in subjects
                ]
            },
            "meta": {"total": len(subjects)},
        }
    ).encode()
    listing_profile, normalized_subjects = collector._normalize_plan_identity(
        listing_plan,
        listing_body,
        roster_plan,
        roster_body,
    )

    assert listing_profile == {
        "issuer_code": "000001",
        "listing_codes": {"SZ": "000001"},
        "listing_date": "1991-04-03",
        "listing_dates": {"SZ": "1991-04-03"},
        "listing_statuses": {"SZ": "listed"},
        "delisting_dates": {"SZ": None},
        "official_result_total": 1,
    }
    assert normalized_subjects == subjects


def test_immutable_evidence_versions_changed_bytes(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "collect_event_evidence_versioning",
        COLLECTOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    canonical = tmp_path / "listing-profile.json"

    first = collector._write_immutable(canonical, b"first")
    second = collector._write_immutable(canonical, b"second")

    assert first == canonical.resolve()
    assert second != first
    assert second.read_bytes() == b"second"
    assert first.read_bytes() == b"first"


def test_query_plan_schema_rejects_incompatible_method_and_encoding():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    invalid = {
        "source_url": "https://www.szse.cn/profile",
        "http_method": "GET",
        "request_encoding": "json",
        "query_params": {"issuer_code": "000001"},
        "response_schema": "canonical_listing_profile_v1",
    }

    errors = list(Draft202012Validator(schema["$defs"]["singleQuery"]).iter_errors(invalid))

    assert errors


def test_default_fetcher_replays_declared_request_headers(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://www.szse.cn/profile"

        def read(self):
            return b'{"ok":true}'

    monkeypatch.setattr(
        build_event_manifest.urllib.request,
        "urlopen",
        lambda request, timeout: requests.append((request, timeout)) or Response(),
    )

    collect_event_evidence._default_response_fetcher(
        "https://www.szse.cn/profile",
        "GET",
        "query",
        {"issuer_code": "000001"},
        {
            "response_schema": "canonical_listing_profile_v1",
            "request_headers": {"Referer": "https://www.szse.cn/disclosure/"},
        },
    )

    request, _timeout = requests[0]
    assert request.get_header("Referer") == "https://www.szse.cn/disclosure/"
