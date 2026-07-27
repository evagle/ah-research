from __future__ import annotations

import hashlib
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import build_event_manifest as event_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_event_manifest.py"
REQUIRED_CATEGORIES = (
    "formal_sanctions",
    "related_party_harm",
    "auditor_changes",
    "auditor_investigations",
    "material_restatements",
    "controller_criminal_cases",
    "late_filings",
    "other_regulatory_events",
)


class _ManifestCli:
    """Run the real CLI entry point with deterministic official roster evidence."""

    @staticmethod
    def run(args, **_kwargs):
        bundle_path = Path(args[args.index("--bundle") + 1])
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        roster_path = Path(bundle["subject_roster"]["source_file"])
        profile_path = Path(bundle["listing_profile"]["source_file"])
        live_responses = {
            bundle["subject_roster"]["source_url"]: roster_path.read_bytes(),
            bundle["listing_profile"]["source_url"]: profile_path.read_bytes(),
        }
        event_responses = {
            row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
            for row in bundle["categories"]
        }
        documents = {}
        for row in bundle["categories"]:
            document_files = row["document_files"]
            for response_file in row["response_files"]:
                response = json.loads(Path(response_file).read_text(encoding="utf-8"))
                for event in response["results"]:
                    documents[event["document_url"]] = Path(
                        document_files[event["record_id"]]
                    ).read_bytes()
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            returncode = event_manifest.main(
                args[2:],
                roster_fetcher=lambda url, _params: live_responses[url],
                event_fetcher=lambda _url, _method, _encoding, params, _schema: event_responses[
                    params["category"]
                ],
                document_fetcher=lambda url: documents[url],
            )
        return SimpleNamespace(returncode=returncode, stdout="", stderr=stderr.getvalue())


subprocess = _ManifestCli()


def _write_bundle(tmp_path: Path) -> Path:
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
            "id": "controller:pingan",
            "type": "controller",
            "name": "平安集团",
            "role": "controller",
            "official_id": "controller-pingan",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "manager:chair",
            "type": "management",
            "name": "马明哲",
            "role": "chair",
            "official_id": "person-chair",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "manager:cfo",
            "type": "management",
            "name": "张三",
            "role": "cfo",
            "official_id": "person-cfo",
            "service_start": "1991-04-03",
            "service_end": None,
        },
        {
            "id": "auditor:firm-1",
            "type": "auditor",
            "name": "审计机构甲",
            "role": "auditor",
            "official_id": "firm-1",
            "service_start": "1991-04-03",
            "service_end": None,
        },
    ]
    subject_ids = [subject["id"] for subject in subjects]
    roster_query = {
        "issuer_code": "000001",
        "start_date": "1991-04-03",
        "end_date": "2026-04-30",
        "roles": [
            "director",
            "supervisor",
            "senior_management",
            "chair",
            "cfo",
            "controller",
        ],
    }
    roster_evidence = tmp_path / "subject-roster.json"
    roster_evidence.write_text(
        json.dumps(
            {
                "query": roster_query,
                "issuer_code": "000001",
                "listing_codes": {"SZ": "000001"},
                "listing_date": "1991-04-03",
                "listing_dates": {"SZ": "1991-04-03"},
                "coverage_start": "1991-04-03",
                "coverage_end": "2026-04-30",
                "management_history_complete": True,
                "controller_history_complete": True,
                "management_roles_covered": [
                    "director",
                    "supervisor",
                    "senior_management",
                    "chair",
                    "cfo",
                ],
                "controller_status": "identified",
                "official_result_total": len(subjects),
                "subjects": subjects,
            }
        ),
        encoding="utf-8",
    )
    categories = []
    primary_sources = {
        "formal_sanctions": "csrc",
        "related_party_harm": "csrc",
        "auditor_changes": "szse",
        "auditor_investigations": "csrc",
        "material_restatements": "szse",
        "controller_criminal_cases": "csrc",
        "late_filings": "szse",
        "other_regulatory_events": "csrc",
    }
    for index, category in enumerate(REQUIRED_CATEGORIES):
        response = tmp_path / f"{category}-response.json"
        query_start = "1991-04-03" if index < 2 else "2023-04-30"
        query_params = {
            "issuer_code": "000001",
            "subject_ids": subject_ids,
            "category": category,
            "start_date": query_start,
            "end_date": "2026-04-30",
        }
        if index >= 2:
            query_params["include_open_before_start"] = True
        response.write_text(
            json.dumps(
                {
                    "query": query_params,
                    "page_no": 1,
                    "page_count": 1,
                    "total": 0,
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        row = {
            "category": category,
            "source_id": primary_sources[category],
            "scope": "listing_history" if index < 2 else "rolling_3y",
            "query_start": query_start,
            "query_end": "2026-04-30",
            "query_url": (
                f"https://www.csrc.gov.cn/{category}"
                if primary_sources[category] == "csrc"
                else f"https://www.szse.cn/{category}"
            ),
            "http_method": "GET",
            "request_encoding": "query",
            "response_schema": "canonical_event_page_v1",
            "query_params": query_params,
            "query_issuer_code": "000001",
            "response_files": [str(response)],
            "document_files": {},
        }
        categories.append(row)

    content = tmp_path / "event-content.txt"
    content.write_text("official enforcement decision", encoding="utf-8")
    response = tmp_path / "formal_sanctions-response.json"
    response.write_text(
        json.dumps(
            {
                "query": categories[0]["query_params"],
                "page_no": 1,
                "page_count": 1,
                "total": 1,
                "results": [
                    {
                        "record_id": "evt-1",
                        "issuer_code": "000001",
                        "subject_ids": ["issuer:000001"],
                        "title": "Administrative penalty",
                        "offense_type": "false_statement",
                        "legal_effect": "effective",
                        "subject_role_at_occurrence": {"issuer:000001": "issuer"},
                        "issuer_connection": {"issuer:000001": "issuer"},
                        "occurrence_date": "2024-12-20",
                        "publication_time": "2025-01-10T09:30:00+08:00",
                        "status": "effective",
                        "status_effective_time": "2025-01-10T09:30:00+08:00",
                        "document_url": "https://www.csrc.gov.cn/document/evt-1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    categories[0]["document_files"] = {"evt-1": str(content)}
    for category in (
        "formal_sanctions",
        "related_party_harm",
        "other_regulatory_events",
    ):
        primary = next(row for row in categories if row["category"] == category)
        exchange_source = deepcopy(primary)
        exchange_source["source_id"] = "szse"
        exchange_source["query_url"] = f"https://www.szse.cn/{category}"
        categories.append(exchange_source)
    auditor_investigations = next(
        row for row in categories if row["category"] == "auditor_investigations"
    )
    mof_source = deepcopy(auditor_investigations)
    mof_source["source_id"] = "mof"
    mof_source["query_url"] = "https://www.mof.gov.cn/auditor_investigations"
    categories.append(mof_source)
    bundle = {
        "ticker": "000001.SZ",
        "exchange": "SZ",
        "AS_OF": "2026-04-30",
        "query_issuer_code": "000001",
        "listing_date": "1991-04-03",
        "listing_profile": {
            "source_url": "https://www.cninfo.com.cn/issuer/000001/profile",
            "query_params": roster_query,
            "response_schema": "canonical_listing_profile_v1",
            "source_file": str(roster_evidence),
        },
        "subject_roster": {
            "coverage_start": "1991-04-03",
            "coverage_end": "2026-04-30",
            "management_history_complete": True,
            "controller_history_complete": True,
            "management_roles_covered": [
                "director",
                "supervisor",
                "senior_management",
                "chair",
                "cfo",
            ],
            "controller_status": "identified",
            "source_url": "https://www.cninfo.com.cn/issuer/000001/roster",
            "query_params": roster_query,
            "source_file": str(roster_evidence),
        },
        "subjects": subjects,
        "categories": categories,
    }
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


def _replace_required_sources(payload: dict, exchange: str) -> None:
    source_hosts = {
        "csrc": "www.csrc.gov.cn",
        "sse": "www.sse.com.cn",
        "szse": "www.szse.cn",
        "hkex": "www.hkex.com.hk",
        "sfc": "www.sfc.hk",
        "afrc": "www.afrc.org.hk",
        "hkpf": "www.police.gov.hk",
        "icac": "www.icac.org.hk",
        "hkjd": "www.judiciary.hk",
        "mof": "www.mof.gov.cn",
    }
    first_by_category = {}
    for row in payload["categories"]:
        first_by_category.setdefault(row["category"], row)
    categories = []
    for category in REQUIRED_CATEGORIES:
        for source_id in sorted(event_manifest.REQUIRED_SOURCE_IDS[exchange][category]):
            row = deepcopy(first_by_category[category])
            row["source_id"] = source_id
            row["query_url"] = f"https://{source_hosts[source_id]}/{category}"
            categories.append(row)
    payload["categories"] = categories


def test_event_manifest_rejects_locally_rewritten_roster_against_live_response(
    tmp_path,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_path = Path(payload["subject_roster"]["source_file"])
    official_response = roster_path.read_bytes()

    payload["subject_roster"]["controller_status"] = "none_identified"
    payload["subjects"] = [
        subject for subject in payload["subjects"] if subject["type"] != "controller"
    ]
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["controller_status"] = "none_identified"
    roster["subjects"] = payload["subjects"]
    roster["official_result_total"] = len(payload["subjects"])
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    subject_ids = [subject["id"] for subject in payload["subjects"]]
    for category in payload["categories"]:
        category["query_params"]["subject_ids"] = subject_ids
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    try:
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: official_response,
        )
    except event_manifest.ManifestError as exc:
        assert "live official response" in str(exc)
    else:
        raise AssertionError("locally rewritten roster was accepted")


def test_event_manifest_rejects_locally_rewritten_event_pages_against_live_response(
    tmp_path,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    official_event_responses = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()

    response_path = Path(payload["categories"][0]["response_files"][0])
    rewritten = json.loads(response_path.read_text(encoding="utf-8"))
    rewritten["total"] = 0
    rewritten["results"] = []
    response_path.write_text(json.dumps(rewritten), encoding="utf-8")

    try:
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: roster_response,
            event_fetcher=lambda _url, _method, _encoding, params, _schema: (
                official_event_responses[params["category"]]
            ),
        )
    except event_manifest.ManifestError as exc:
        assert "live official event response" in str(exc)
    else:
        raise AssertionError("locally rewritten event page was accepted")


def test_event_manifest_separates_local_document_path_from_official_response(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = payload["categories"][0]
    response_path = Path(category["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()
    event_responses = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    manifest = event_manifest.build_manifest(
        bundle,
        roster_fetcher=lambda _url, _params: roster_response,
        event_fetcher=lambda url, _method, _encoding, _params, _schema: event_responses[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )

    assert (
        manifest["queries"]["formal_sanctions"]["events"][0]["content_sha256"]
        == hashlib.sha256(b"official enforcement decision").hexdigest()
    )
    assert manifest["queries"]["formal_sanctions"]["events"][0]["document_path"] == str(
        Path(category["document_files"]["evt-1"]).resolve()
    )


def test_event_manifest_requires_status_effective_time_for_final_event(tmp_path):
    bundle = _write_bundle(tmp_path)
    response_path = tmp_path / "formal_sanctions-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["results"][0].pop("status_effective_time")
    response_path.write_text(json.dumps(response), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="status_effective_time"):
        _run_build_with_local_evidence(bundle)


def test_event_manifest_rejects_status_effective_time_after_as_of(tmp_path):
    bundle = _write_bundle(tmp_path)
    response_path = tmp_path / "formal_sanctions-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["results"][0]["status_effective_time"] = "2026-05-01T00:00:00+08:00"
    response_path.write_text(json.dumps(response), encoding="utf-8")

    with pytest.raises(
        event_manifest.ManifestError,
        match="status_effective_time is after AS_OF",
    ):
        _run_build_with_local_evidence(bundle)


def test_event_manifest_rejects_tampered_local_document_against_live_document(
    tmp_path,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = payload["categories"][0]
    response_path = Path(category["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    content_path = Path(category["document_files"]["evt-1"])
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()
    event_responses = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    content_path.write_text("tampered local decision", encoding="utf-8")

    try:
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: roster_response,
            event_fetcher=lambda url, _method, _encoding, _params, _schema: event_responses[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )
    except event_manifest.ManifestError as exc:
        assert "live official document" in str(exc)
    else:
        raise AssertionError("tampered local event document was accepted")


def test_official_roster_fetch_rejects_cross_host_redirect(monkeypatch):
    class RedirectedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://attacker.example/roster"

        def read(self):
            return b'{"subjects":[]}'

    monkeypatch.setattr(
        event_manifest.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: RedirectedResponse(),
    )

    try:
        event_manifest._fetch_official_roster(
            "https://www.cninfo.com.cn/issuer/000001/roster",
            {"issuer_code": "000001"},
        )
    except event_manifest.ManifestError as exc:
        assert "redirected" in str(exc)
    else:
        raise AssertionError("cross-host redirect was accepted")


def test_official_event_fetch_rejects_cross_host_redirect(monkeypatch):
    class RedirectedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://attacker.example/events"

        def read(self):
            return b'{"page_no":1,"page_count":1,"total":0,"results":[]}'

    monkeypatch.setattr(
        event_manifest.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: RedirectedResponse(),
    )

    try:
        event_manifest._fetch_official_event_pages(
            "https://www.csrc.gov.cn/events",
            "GET",
            "query",
            {},
            "canonical_event_page_v1",
        )
    except event_manifest.ManifestError as exc:
        assert "redirected" in str(exc)
    else:
        raise AssertionError("cross-host event redirect was accepted")


def test_official_event_fetch_replays_native_post_json_adapter(monkeypatch):
    requests = []

    class OfficialResponse:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://www.csrc.gov.cn/events"

        def read(self):
            return self.body

    def urlopen(request, timeout):
        assert timeout == 30
        requests.append(request)
        request_payload = json.loads(request.data.decode())
        page = request_payload["p"]
        return OfficialResponse(
            json.dumps(
                {
                    "meta": {"page": page, "pages": 2},
                    "count": 0,
                    "records": [],
                }
            ).encode()
        )

    monkeypatch.setattr(event_manifest.urllib.request, "urlopen", urlopen)

    pages = event_manifest._fetch_official_event_pages(
        "https://www.csrc.gov.cn/events",
        "POST",
        "json",
        {"stock": "000001"},
        {
            "response_schema": "native_json_event_page_v1",
            "response_adapter": {
                "request_page_param": "p",
                "page_count_path": "meta.pages",
            },
        },
    )

    assert len(pages) == 2
    assert [json.loads(request.data.decode())["p"] for request in requests] == [1, 2]
    assert all(request.method == "POST" for request in requests)
    assert all(request.headers["Content-type"] == "application/json" for request in requests)


def test_official_document_fetch_rejects_cross_host_redirect(monkeypatch):
    class RedirectedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://attacker.example/document"

        def read(self):
            return b"document"

    monkeypatch.setattr(
        event_manifest.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: RedirectedResponse(),
    )

    try:
        event_manifest._fetch_official_document("https://www.csrc.gov.cn/document/1")
    except event_manifest.ManifestError as exc:
        assert "redirected" in str(exc)
    else:
        raise AssertionError("cross-host document redirect was accepted")


def test_build_event_manifest_from_complete_official_bundle(tmp_path):
    bundle = _write_bundle(tmp_path)
    output = tmp_path / "events-2026-04-30.json"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--out", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["ticker"] == "000001.SZ"
    assert manifest["exchange"] == "SZ"
    assert manifest["AS_OF"] == "2026-04-30"
    assert manifest["查询发行人代码"] == "000001"
    assert manifest["listing_history_complete"] is True
    assert set(manifest["queries"]) == set(REQUIRED_CATEGORIES)
    sanction = manifest["queries"]["formal_sanctions"]
    assert (
        sanction["response_sha256"]
        == hashlib.sha256((tmp_path / "formal_sanctions-response.json").read_bytes()).hexdigest()
    )
    event = sanction["events"][0]
    assert event["record_id"] == "evt-1"
    assert event["occurrence_date"] == "2024-12-20"
    assert event["publication_time"] == "2025-01-10T09:30:00+08:00"
    assert (
        event["content_sha256"]
        == hashlib.sha256((tmp_path / "event-content.txt").read_bytes()).hexdigest()
    )


def test_event_manifest_rejects_nonofficial_query_domain(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["categories"][0]["query_url"] = "https://regulator.example/search"
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "official domain" in result.stderr


def test_event_manifest_derives_total_from_all_response_pages(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = payload["categories"][1]
    category_rows = [
        row for row in payload["categories"] if row["category"] == category["category"]
    ]
    first_path = Path(category["response_files"][0])
    first = json.loads(first_path.read_text(encoding="utf-8"))
    first.update({"page_count": 2, "total": 1})
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second_path = tmp_path / "related-party-harm-response-2.json"
    second_path.write_text(
        json.dumps(
            {
                "query": category["query_params"],
                "page_no": 2,
                "page_count": 2,
                "total": 1,
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    for row in category_rows:
        row["response_files"].append(str(second_path))
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "response total" in result.stderr


def test_event_manifest_hashes_all_stored_pages_in_order(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = payload["categories"][1]
    category_rows = [
        row for row in payload["categories"] if row["category"] == category["category"]
    ]
    first_path = Path(category["response_files"][0])
    first = json.loads(first_path.read_text(encoding="utf-8"))
    first.update({"page_count": 2, "total": 0})
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second_path = tmp_path / "related-party-harm-response-2.json"
    second_path.write_text(
        json.dumps(
            {
                "query": category["query_params"],
                "page_no": 2,
                "page_count": 2,
                "total": 0,
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    for row in category_rows:
        row["response_files"].append(str(second_path))
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()
    event_responses = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    manifest = event_manifest.build_manifest(
        bundle,
        roster_fetcher=lambda _url, _params: roster_response,
        event_fetcher=lambda url, _method, _encoding, _params, _schema: event_responses[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )

    expected = hashlib.sha256(first_path.read_bytes() + second_path.read_bytes()).hexdigest()
    assert manifest["queries"]["related_party_harm"]["response_sha256"] == expected
    assert manifest["queries"]["related_party_harm"]["live_response_sha256"] == expected


def test_event_manifest_adapts_native_official_roster_and_event_json(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    subjects = payload["subjects"]
    roster_path = Path(payload["subject_roster"]["source_file"])
    listing_path = tmp_path / "canonical-listing-profile.json"
    listing_path.write_bytes(roster_path.read_bytes())
    payload["listing_profile"]["source_file"] = str(listing_path)
    native_roster = {
        "query": payload["listing_profile"]["query_params"],
        "issuer_code": "000001",
        "listing_date": "1991-04-03",
        "official_result_total": len(subjects),
        "count": len(subjects),
        "records": [
            {
                "personId": subject["official_id"],
                "personName": subject["name"],
                "personType": subject["type"],
                "position": subject["role"],
                "startDate": subject["service_start"],
                "endDate": subject["service_end"],
            }
            for subject in subjects
        ],
    }
    roster_path.write_text(json.dumps(native_roster), encoding="utf-8")
    payload["subject_roster"].update(
        {
            "response_schema": "native_json_roster_v1",
            "query_params": {
                "stock": "000001",
                "from": "1991-04-03",
                "to": "2026-04-30",
            },
            "response_adapter": {
                "results_path": "records",
                "total_path": "count",
                "request_bindings": {
                    "issuer": "stock",
                    "start_date": "from",
                    "end_date": "to",
                },
                "field_paths": {
                    "official_id": "personId",
                    "name": "personName",
                    "type": "personType",
                    "role": "position",
                    "service_start": "startDate",
                    "service_end": "endDate",
                },
            },
        }
    )
    subject_ids = [subject["id"] for subject in subjects]
    official_subject_ids = [subject["official_id"] for subject in subjects]
    official_id_by_subject_id = {subject["id"]: subject["official_id"] for subject in subjects}
    converted_paths = set()
    for row in payload["categories"]:
        response_path = Path(row["response_files"][0])
        canonical = json.loads(response_path.read_text(encoding="utf-8"))
        native_records = []
        for event in canonical.get("results", []):
            native_records.append(
                {
                    "id": event["record_id"],
                    "headline": event["title"],
                    "publishedAt": event["publication_time"],
                    "documentLink": event["document_url"],
                    "stock": event["issuer_code"],
                    "subjects": [
                        official_id_by_subject_id[subject_id] for subject_id in event["subject_ids"]
                    ],
                    "offense": event["offense_type"],
                    "effect": event["legal_effect"],
                    "roles": {
                        official_id_by_subject_id[subject_id]: role
                        for subject_id, role in event["subject_role_at_occurrence"].items()
                    },
                    "connections": {
                        official_id_by_subject_id[subject_id]: connection
                        for subject_id, connection in event["issuer_connection"].items()
                    },
                    "occurredAt": event["occurrence_date"],
                    "state": event["status"],
                    "statusSince": event["status_effective_time"],
                }
            )
        native = {
            "page": 1,
            "pages": 1,
            "count": len(native_records),
            "records": native_records,
        }
        if response_path not in converted_paths:
            response_path.write_text(json.dumps(native), encoding="utf-8")
            converted_paths.add(response_path)
        row.update(
            {
                "response_schema": "native_json_event_page_v1",
                "query_params": {
                    "stock": "000001",
                    "kind": row["category"],
                    "from": row["query_start"],
                    "to": row["query_end"],
                    "subjects": official_subject_ids,
                },
                "query_subject_ids": subject_ids,
                "response_adapter": {
                    "request_page_param": "page",
                    "page_number_path": "page",
                    "page_count_path": "pages",
                    "total_path": "count",
                    "results_path": "records",
                    "request_bindings": {
                        "issuer": "stock",
                        "category": "kind",
                        "start_date": "from",
                        "end_date": "to",
                        "subject_ids": "subjects",
                    },
                    "field_paths": {
                        "record_id": "id",
                        "title": "headline",
                        "publication_time": "publishedAt",
                        "document_url": "documentLink",
                        "issuer_code": "stock",
                        "subject_ids": "subjects",
                        "offense_type": "offense",
                        "legal_effect": "effect",
                        "subject_role_at_occurrence": "roles",
                        "issuer_connection": "connections",
                        "occurrence_date": "occurredAt",
                        "status": "state",
                        "status_effective_time": "statusSince",
                    },
                },
            }
        )
        if row["scope"] == "rolling_3y":
            row["query_params"]["include_open_before_start"] = True
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    event_responses = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    manifest = event_manifest.build_manifest(
        bundle,
        roster_fetcher=lambda url, _params: (
            listing_path.read_bytes()
            if url == payload["listing_profile"]["source_url"]
            else roster_path.read_bytes()
        ),
        event_fetcher=lambda url, _method, _encoding, _params, _contract: event_responses[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )

    assert manifest["subject_roster"]["official_result_total"] == len(subjects)
    assert manifest["subject_roster"]["response_adapter"]["results_path"] == "records"
    assert manifest["queries"]["formal_sanctions"]["official_result_total"] == 2
    assert manifest["queries"]["formal_sanctions"]["events"][0]["record_id"] == "evt-1"
    assert (
        manifest["queries"]["formal_sanctions"]["response_adapter"]["request_page_param"] == "page"
    )
    assert (
        manifest["queries"]["formal_sanctions"]["response_adapter"]["request_bindings"][
            "subject_ids"
        ]
        == "subjects"
    )
    assert manifest["queries"]["formal_sanctions"]["query_subject_ids"] == subject_ids


def test_event_manifest_rejects_role_that_differs_from_official_roster(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    event = response["results"][0]
    event["subject_ids"] = ["manager:chair"]
    event["subject_role_at_occurrence"] = {"manager:chair": "chief_executive"}
    event["issuer_connection"] = {"manager:chair": "serving_at_occurrence"}
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "official roster role" in result.stderr


def test_event_manifest_rejects_duplicate_official_subject_ids(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    managers = [subject for subject in payload["subjects"] if subject["type"] == "management"]
    managers[1]["official_id"] = managers[0]["official_id"]
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["subjects"] = payload["subjects"]
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "duplicate official_id" in result.stderr


def test_event_manifest_accepts_role_transition_for_same_official_person(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    first = next(subject for subject in payload["subjects"] if subject["id"] == "manager:chair")
    second = next(subject for subject in payload["subjects"] if subject["id"] == "manager:cfo")
    first["service_end"] = "2019-12-31"
    second["service_end"] = "2019-12-31"
    payload["subjects"].extend(
        [
            {
                **first,
                "id": "manager:chair:senior",
                "role": "cfo",
                "service_start": "2020-01-01",
                "service_end": None,
            },
            {
                **second,
                "id": "manager:cfo:director",
                "role": "chair",
                "service_start": "2020-01-01",
                "service_end": None,
            },
        ]
    )
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["subjects"] = payload["subjects"]
    roster["official_result_total"] = len(payload["subjects"])
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    subject_ids = [subject["id"] for subject in payload["subjects"]]
    for category in payload["categories"]:
        category["query_params"]["subject_ids"] = subject_ids
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    manifest = _run_build_with_local_evidence(bundle)

    assert len(manifest["subjects"]) == 7


def test_event_manifest_requires_chair_and_cfo_roster_coverage(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["subject_roster"]["management_roles_covered"] = [
        "director",
        "senior_management",
    ]
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["management_roles_covered"] = payload["subject_roster"]["management_roles_covered"]
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="chair and cfo"):
        _run_build_with_local_evidence(bundle)


def test_event_manifest_rejects_controller_connection_for_management(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    event = response["results"][0]
    event["subject_ids"] = ["manager:chair"]
    event["subject_role_at_occurrence"] = {"manager:chair": "chair"}
    event["issuer_connection"] = {"manager:chair": "controller_at_occurrence"}
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "subject type" in result.stderr


def test_event_manifest_rejects_event_published_after_as_of(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["results"][0]["publication_time"] = "2026-05-01T00:00:00+08:00"
    response_path.write_text(json.dumps(response), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "publication_time is after AS_OF" in result.stderr


def test_event_manifest_rejects_event_outside_declared_query_window(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = payload["categories"][2]
    response_path = Path(category["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["total"] = 1
    response["results"] = [
        {
            "record_id": "old-event",
            "issuer_code": "000001",
            "subject_ids": ["issuer:000001"],
            "title": "Old auditor event",
            "offense_type": "other",
            "legal_effect": "effective",
            "subject_role_at_occurrence": {"issuer:000001": "issuer"},
            "issuer_connection": {"issuer:000001": "issuer"},
            "occurrence_date": "2020-01-01",
            "publication_time": "2020-01-02T09:00:00+08:00",
            "status": "effective",
            "status_effective_time": "2020-01-02T09:00:00+08:00",
            "document_url": "https://www.csrc.gov.cn/document/old-event",
        }
    ]
    response_path.write_text(json.dumps(response), encoding="utf-8")
    content = tmp_path / "old-event.txt"
    content.write_text("old official event", encoding="utf-8")
    category["document_files"] = {"old-event": str(content)}
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "query window" in result.stderr


def test_event_manifest_requires_exact_roster_response_bytes(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_path = Path(payload["subject_roster"]["source_file"])
    reformatted = json.dumps(
        json.loads(roster_path.read_text(encoding="utf-8")),
        indent=2,
    ).encode()
    stored = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    try:
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: reformatted,
            event_fetcher=lambda _url, _method, _encoding, params, _contract: stored[
                params["category"]
            ],
            document_fetcher=lambda _url: b"official enforcement decision",
        )
    except event_manifest.ManifestError as exc:
        assert "byte hash" in str(exc)
    else:
        raise AssertionError("reformatted live roster response was accepted")


def test_event_manifest_requires_exact_event_response_bytes(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()
    stored = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    reformatted = json.dumps(
        json.loads(stored["formal_sanctions"][0].decode()),
        indent=2,
    ).encode()

    try:
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: roster_response,
            event_fetcher=lambda _url, _method, _encoding, params, _contract: (
                [reformatted]
                if params["category"] == "formal_sanctions"
                else stored[params["category"]]
            ),
            document_fetcher=lambda _url: b"official enforcement decision",
        )
    except event_manifest.ManifestError as exc:
        assert "byte hash" in str(exc)
    else:
        raise AssertionError("reformatted live event response was accepted")


def test_event_manifest_rejects_stored_response_changed_during_build(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()
    stored = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    response_path = Path(payload["categories"][0]["response_files"][0])
    changed = False

    def mutate_response_during_document_fetch(_url):
        nonlocal changed
        if not changed:
            response_path.write_text(
                json.dumps({"tampered": True}),
                encoding="utf-8",
            )
            changed = True
        return b"official enforcement decision"

    try:
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: roster_response,
            event_fetcher=lambda _url, _method, _encoding, params, _contract: stored[
                params["category"]
            ],
            document_fetcher=mutate_response_during_document_fetch,
        )
    except event_manifest.ManifestError as exc:
        assert "changed during manifest construction" in str(exc)
    else:
        raise AssertionError("response mutation during build was accepted")


def test_event_manifest_rechecks_all_response_files_before_return(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()
    stored = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    first_response = Path(payload["categories"][0]["response_files"][0])
    changed = False

    def mutate_earlier_category(
        _url,
        _method,
        _encoding,
        params,
        _contract,
    ):
        nonlocal changed
        if params["category"] == "related_party_harm" and not changed:
            first_response.write_text(
                json.dumps({"tampered": True}),
                encoding="utf-8",
            )
            changed = True
        return stored[params["category"]]

    try:
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: roster_response,
            event_fetcher=mutate_earlier_category,
            document_fetcher=lambda _url: b"official enforcement decision",
        )
    except event_manifest.ManifestError as exc:
        assert "changed during manifest construction" in str(exc)
    else:
        raise AssertionError("earlier response mutation was accepted")


def test_event_manifest_rechecks_all_event_documents_before_return(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()
    stored = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    document_path = Path(payload["categories"][0]["document_files"]["evt-1"])

    def event_fetcher(_url, _method, _encoding, params, _contract):
        if params["category"] == "other_regulatory_events":
            document_path.write_text("mutated after validation", encoding="utf-8")
        return stored[params["category"]]

    with pytest.raises(event_manifest.ManifestError, match="document changed"):
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: roster_response,
            event_fetcher=event_fetcher,
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_event_manifest_refetches_official_documents_before_return(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_response = Path(payload["subject_roster"]["source_file"]).read_bytes()
    stored = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    calls = 0

    def changing_document(_url):
        nonlocal calls
        calls += 1
        if calls <= 2:
            return b"official enforcement decision"
        return b"changed official enforcement decision"

    with pytest.raises(event_manifest.ManifestError, match="official document changed"):
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: roster_response,
            event_fetcher=lambda _url, _method, _encoding, params, _contract: stored[
                params["category"]
            ],
            document_fetcher=changing_document,
        )

    assert calls >= 3


def test_event_manifest_rejects_roster_changed_during_build(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster_response = roster_path.read_bytes()
    stored = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    changed = False

    def mutate_roster_during_event_fetch(
        _url,
        _method,
        _encoding,
        params,
        _contract,
    ):
        nonlocal changed
        if not changed:
            roster_path.write_text(
                json.dumps({"tampered": True}),
                encoding="utf-8",
            )
            changed = True
        return stored[params["category"]]

    try:
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda _url, _params: roster_response,
            event_fetcher=mutate_roster_during_event_fetch,
            document_fetcher=lambda _url: b"official enforcement decision",
        )
    except event_manifest.ManifestError as exc:
        assert "roster source changed during manifest construction" in str(exc)
    else:
        raise AssertionError("roster mutation during build was accepted")


def test_event_manifest_refetches_roster_before_return(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    profile_path = Path(payload["listing_profile"]["source_file"])
    roster_path = Path(payload["subject_roster"]["source_file"])
    profile_response = profile_path.read_bytes()
    roster_response = roster_path.read_bytes()
    stored = {
        row["category"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    roster_calls = 0

    def changing_roster(url, _params):
        nonlocal roster_calls
        if url == payload["listing_profile"]["source_url"]:
            return profile_response
        roster_calls += 1
        if roster_calls == 1:
            return roster_response
        return b'{"changed":true}'

    with pytest.raises(
        event_manifest.ManifestError,
        match="subject roster source changed during manifest construction",
    ):
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=changing_roster,
            event_fetcher=lambda _url, _method, _encoding, params, _contract: stored[
                params["category"]
            ],
            document_fetcher=lambda _url: b"official enforcement decision",
        )

    assert roster_calls >= 2


def test_event_manifest_rejects_noncanonical_query_issuer_code(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["query_issuer_code"] = "1"
    for category in payload["categories"]:
        category["query_issuer_code"] = "1"
        category["query_params"]["issuer_code"] = "1"
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "query issuer does not match ticker" in result.stderr


def test_event_manifest_requires_all_declared_subjects_in_query(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["categories"][0]["query_params"]["subject_ids"] = ["issuer:000001"]
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "subject coverage" in result.stderr


def test_event_manifest_requires_management_and_controller_coverage(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["subjects"] = [payload["subjects"][0]]
    for category in payload["categories"]:
        category["query_params"]["subject_ids"] = ["issuer:000001"]
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"]["subject_ids"] = ["issuer:000001"]
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "management" in result.stderr


def test_event_manifest_binds_declared_window_to_request_params(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = payload["categories"][0]
    category["query_params"]["start_date"] = "2026-01-01"
    response_path = Path(category["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["query"] = category["query_params"]
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "start_date" in result.stderr


def test_event_manifest_binds_category_to_request_params(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = payload["categories"][0]
    category["query_params"]["category"] = "other_regulatory_events"
    response_path = Path(category["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["query"] = category["query_params"]
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "category" in result.stderr


def test_event_manifest_accepts_evidenced_no_controller_status(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["subject_roster"]["controller_status"] = "none_identified"
    payload["subjects"] = [
        subject for subject in payload["subjects"] if subject["type"] != "controller"
    ]
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["controller_status"] = "none_identified"
    roster["subjects"] = payload["subjects"]
    roster["official_result_total"] = len(payload["subjects"])
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    subject_ids = [subject["id"] for subject in payload["subjects"]]
    for category in payload["categories"]:
        category["query_params"]["subject_ids"] = subject_ids
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_event_manifest_rejects_unproved_historical_subject_roster(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["subject_roster"]["management_history_complete"] = False
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "management history" in result.stderr


def test_event_manifest_rejects_roster_evidence_that_omits_declared_subjects(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["subjects"] = roster["subjects"][:1]
    roster_path.write_text(json.dumps(roster), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "roster evidence" in result.stderr


def test_event_manifest_rejects_generic_or_incomplete_management_roster(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["subjects"] = [subject for subject in payload["subjects"] if subject["role"] != "cfo"]
    director = next(subject for subject in payload["subjects"] if subject["role"] == "chair")
    director["name"] = "董事长"
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["subjects"] = payload["subjects"]
    roster["official_result_total"] = len(payload["subjects"])
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    subject_ids = [subject["id"] for subject in payload["subjects"]]
    for category in payload["categories"]:
        category["query_params"]["subject_ids"] = subject_ids
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "historical management roster" in result.stderr


def test_event_manifest_accepts_ministry_of_finance_as_official(tmp_path):
    bundle = _write_bundle(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_event_manifest_accepts_mainland_regulators_for_hk_issuer(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["ticker"] = "00005.HK"
    payload["exchange"] = "HK"
    payload["query_issuer_code"] = "00005"
    payload["listing_date"] = "1991-04-03"
    payload["subject_roster"]["source_url"] = "https://www.csrc.gov.cn/issuer/00005/roster"
    payload["subject_roster"]["query_params"]["issuer_code"] = "00005"
    payload["listing_profile"]["query_params"]["issuer_code"] = "00005"
    payload["subjects"][0]["id"] = "issuer:00005"
    subject_ids = [subject["id"] for subject in payload["subjects"]]
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["query"] = payload["subject_roster"]["query_params"]
    roster["issuer_code"] = "00005"
    roster["listing_codes"] = {"HK": "00005"}
    roster["listing_dates"] = {"HK": "1991-04-03"}
    roster["subjects"] = payload["subjects"]
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    _replace_required_sources(payload, "HK")
    extra = deepcopy(
        next(row for row in payload["categories"] if row["category"] == "other_regulatory_events")
    )
    extra["source_id"] = "nfra"
    extra["query_url"] = "https://www.nfra.gov.cn/other_regulatory_events"
    payload["categories"].append(extra)
    for category in payload["categories"]:
        category["query_issuer_code"] = "00005"
        category["query_params"]["issuer_code"] = "00005"
        category["query_params"]["subject_ids"] = subject_ids
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        for event in response["results"]:
            event["issuer_code"] = "00005"
            event["subject_ids"] = ["issuer:00005"]
            event["subject_role_at_occurrence"] = {"issuer:00005": "issuer"}
            event["issuer_connection"] = {"issuer:00005": "issuer"}
            event["document_url"] = "https://www.csrc.gov.cn/document/evt-1"
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_event_manifest_accepts_hkma_as_official_for_hk_bank(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["ticker"] = "00005.HK"
    payload["exchange"] = "HK"
    payload["query_issuer_code"] = "00005"
    payload["listing_date"] = "1865-03-03"
    payload["subject_roster"]["coverage_start"] = "1865-03-03"
    payload["subject_roster"]["source_url"] = "https://www.hkma.gov.hk/issuer/00005/roster"
    payload["subject_roster"]["query_params"].update(
        {
            "issuer_code": "00005",
            "start_date": "1865-03-03",
        }
    )
    payload["listing_profile"]["source_url"] = "https://www.hkma.gov.hk/issuer/00005/profile"
    payload["listing_profile"]["query_params"].update(
        {
            "issuer_code": "00005",
            "start_date": "1865-03-03",
        }
    )
    payload["subjects"][0]["id"] = "issuer:00005"
    payload["subjects"][0]["name"] = "汇丰控股"
    for subject in payload["subjects"]:
        subject["service_start"] = "1865-03-03"
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["query"] = payload["subject_roster"]["query_params"]
    roster["issuer_code"] = "00005"
    roster["listing_codes"] = {"HK": "00005"}
    roster["listing_date"] = "1865-03-03"
    roster["listing_dates"] = {"HK": "1865-03-03"}
    roster["coverage_start"] = "1865-03-03"
    roster["subjects"] = payload["subjects"]
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    subject_ids = [subject["id"] for subject in payload["subjects"]]
    _replace_required_sources(payload, "HK")
    extra = deepcopy(
        next(row for row in payload["categories"] if row["category"] == "other_regulatory_events")
    )
    extra["source_id"] = "hkma"
    extra["query_url"] = "https://www.hkma.gov.hk/other_regulatory_events"
    payload["categories"].append(extra)
    for category in payload["categories"]:
        category["query_issuer_code"] = "00005"
        if category["scope"] == "listing_history":
            category["query_start"] = "1865-03-03"
            category["query_params"]["start_date"] = "1865-03-03"
        category["query_params"]["issuer_code"] = "00005"
        category["query_params"]["subject_ids"] = subject_ids
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        for event in response["results"]:
            event["issuer_code"] = "00005"
            event["subject_ids"] = ["issuer:00005"]
            event["subject_role_at_occurrence"] = {"issuer:00005": "issuer"}
            event["issuer_connection"] = {"issuer:00005": "issuer"}
            event["document_url"] = "https://www.hkma.gov.hk/document/evt-1"
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_event_manifest_requires_offense_and_role_attribution(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    del response["results"][0]["offense_type"]
    response_path.write_text(json.dumps(response), encoding="utf-8")
    output = tmp_path / "events.json"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--out", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "offense_type" in result.stderr


def test_event_manifest_requires_per_subject_attribution(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    event = response["results"][0]
    event["subject_ids"] = ["issuer:000001", "manager:chair"]
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "per-subject attribution" in result.stderr


def test_event_manifest_rejects_unknown_legal_effect_for_effective_event(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["results"][0]["legal_effect"] = "unknown"
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "legal_effect" in result.stderr


def test_event_manifest_rejects_serving_role_outside_tenure(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    manager = next(subject for subject in payload["subjects"] if subject["id"] == "manager:chair")
    manager["service_start"] = "2020-01-01"
    manager["service_end"] = "2021-01-01"
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["subjects"] = payload["subjects"]
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    event = response["results"][0]
    event["subject_ids"] = ["manager:chair"]
    event["subject_role_at_occurrence"] = {"manager:chair": "director"}
    event["issuer_connection"] = {"manager:chair": "serving_at_occurrence"}
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "tenure" in result.stderr


def test_event_manifest_applies_exchange_timezone_to_publication_cutoff(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["results"][0]["publication_time"] = "2026-04-30T16:30:00Z"
    response_path.write_text(json.dumps(response), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "publication_time is after AS_OF" in result.stderr


def test_event_manifest_rejects_investigation_as_formal_sanction(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    response_path = Path(payload["categories"][0]["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    event = response["results"][0]
    event["status"] = "investigation"
    event["legal_effect"] = "investigation"
    response_path.write_text(json.dumps(response), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(bundle),
            "--out",
            str(tmp_path / "events.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "formal_sanctions" in result.stderr
    assert "status" in result.stderr


def test_event_manifest_marks_live_revalidation_as_required(tmp_path):
    bundle = _write_bundle(tmp_path)
    response_path = tmp_path / "formal_sanctions-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["results"][0].update(
        {
            "offense_type": "false_statement",
            "legal_effect": "effective",
            "subject_role_at_occurrence": {"issuer:000001": "issuer"},
            "issuer_connection": {"issuer:000001": "issuer"},
        }
    )
    response_path.write_text(json.dumps(response), encoding="utf-8")
    output = tmp_path / "events.json"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--out", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["live_revalidation_required"] is True


class _OfficialResponse:
    def __init__(self, url: str, body: bytes):
        self.url = url
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def geturl(self):
        return self.url

    def read(self):
        return self.body


@pytest.mark.parametrize(
    ("fetcher", "args", "url", "body"),
    (
        (
            event_manifest._fetch_official_roster,
            ("https://www.cninfo.com.cn/roster", {"issuer_code": "000001"}),
            "https://www.cninfo.com.cn/roster?issuer_code=000001",
            b'{"subjects":[]}',
        ),
        (
            event_manifest._fetch_official_document,
            ("https://www.csrc.gov.cn/document/1",),
            "https://www.csrc.gov.cn/document/1",
            b"official document",
        ),
    ),
)
def test_official_fetchers_return_same_host_response(
    monkeypatch,
    fetcher,
    args,
    url,
    body,
):
    monkeypatch.setattr(
        event_manifest.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _OfficialResponse(url, body),
    )

    assert fetcher(*args) == body


@pytest.mark.parametrize(
    ("fetcher", "args", "message"),
    (
        (
            event_manifest._fetch_official_roster,
            ("https://www.cninfo.com.cn/roster", {}),
            "subject_roster live official request failed",
        ),
        (
            event_manifest._fetch_official_event_pages,
            (
                "https://www.csrc.gov.cn/events",
                "GET",
                "query",
                {},
                "canonical_event_page_v1",
            ),
            "live official event request failed",
        ),
        (
            event_manifest._fetch_official_document,
            ("https://www.csrc.gov.cn/document/1",),
            "live official document request failed",
        ),
    ),
)
def test_official_fetchers_wrap_network_errors(
    monkeypatch,
    fetcher,
    args,
    message,
):
    def fail(*_args, **_kwargs):
        raise event_manifest.urllib.error.URLError("offline")

    monkeypatch.setattr(event_manifest.urllib.request, "urlopen", fail)

    with pytest.raises(event_manifest.ManifestError, match=message):
        fetcher(*args)


@pytest.mark.parametrize(
    ("contract", "message"),
    (
        (None, "response contract is invalid"),
        ("unknown_schema", "response_schema is unsupported"),
        (
            {
                "response_schema": "native_json_event_page_v1",
                "response_adapter": {},
            },
            "pagination is incomplete",
        ),
    ),
)
def test_official_event_fetch_rejects_invalid_response_contract(
    contract,
    message,
):
    with pytest.raises(event_manifest.ManifestError, match=message):
        event_manifest._fetch_official_event_pages(
            "https://www.csrc.gov.cn/events",
            "GET",
            "query",
            {},
            contract,
        )


def test_official_event_fetch_replays_post_form_request(monkeypatch):
    requests = []

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return _OfficialResponse(
            "https://www.csrc.gov.cn/events",
            b'{"page_count":1}',
        )

    monkeypatch.setattr(event_manifest.urllib.request, "urlopen", urlopen)

    pages = event_manifest._fetch_official_event_pages(
        "https://www.csrc.gov.cn/events",
        "POST",
        "form",
        {"issuer_code": "000001"},
        "canonical_event_page_v1",
    )

    request, timeout = requests[0]
    assert timeout == 30
    assert request.method == "POST"
    assert request.headers["Content-type"] == "application/x-www-form-urlencoded"
    assert request.data == b"issuer_code=000001&page_no=1"
    assert pages == [b'{"page_count":1}']


def test_official_event_fetch_rejects_incompatible_request_contract():
    with pytest.raises(event_manifest.ManifestError, match="incompatible"):
        event_manifest._fetch_official_event_pages(
            "https://www.csrc.gov.cn/events",
            "PUT",
            "json",
            {},
            "canonical_event_page_v1",
        )


@pytest.mark.parametrize(
    ("body", "message"),
    (
        (b"not-json", "response is invalid"),
        (b'{"page_count":0}', "invalid page_count"),
        (b'{"other":1}', "JSON path is missing"),
    ),
)
def test_official_event_fetch_rejects_invalid_pagination_response(
    monkeypatch,
    body,
    message,
):
    monkeypatch.setattr(
        event_manifest.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _OfficialResponse(
            "https://www.csrc.gov.cn/events",
            body,
        ),
    )

    with pytest.raises(event_manifest.ManifestError, match=message):
        event_manifest._fetch_official_event_pages(
            "https://www.csrc.gov.cn/events",
            "GET",
            "query",
            {},
            "canonical_event_page_v1",
        )


@pytest.mark.parametrize(
    ("call", "message"),
    (
        (
            lambda: event_manifest._parse_date("2026-13-01", "date"),
            "must be an ISO date",
        ),
        (
            lambda: event_manifest._parse_datetime("invalid", "timestamp"),
            "must be an ISO datetime",
        ),
        (
            lambda: event_manifest._parse_datetime(
                "2026-04-30T12:00:00",
                "timestamp",
            ),
            "must include a timezone",
        ),
        (
            lambda: event_manifest._canonical_identity("abc", "SZ"),
            "ticker must use",
        ),
        (
            lambda: event_manifest._canonical_identity("000001.SZ", "SH"),
            "ticker exchange",
        ),
        (
            lambda: event_manifest._canonical_identity("1.SZ", "SZ"),
            "six digits",
        ),
        (
            lambda: event_manifest._require_official_https(
                "http://www.csrc.gov.cn/events",
                "query_url",
                "SZ",
            ),
            "must use HTTPS",
        ),
        (
            lambda: event_manifest._json_path({}, "", "payload"),
            "JSON path is missing",
        ),
        (
            lambda: event_manifest._json_path({}, "meta.total", "payload"),
            "JSON path is missing",
        ),
        (
            lambda: event_manifest._adapter_field_paths(
                {},
                {"id"},
                "adapter",
            ),
            "field_paths must be an object",
        ),
        (
            lambda: event_manifest._adapter_field_paths(
                {"field_paths": {"wrong": "id"}},
                {"id"},
                "adapter",
            ),
            "must define exactly",
        ),
        (
            lambda: event_manifest._validate_request_bindings(
                [],
                {},
                {"issuer": "000001"},
                "query",
            ),
            "request bindings are invalid",
        ),
        (
            lambda: event_manifest._validate_request_bindings(
                {},
                {},
                {"issuer": "000001"},
                "query",
            ),
            "must define exactly",
        ),
        (
            lambda: event_manifest._validate_request_bindings(
                {"stock": "000002"},
                {"issuer": "stock"},
                {"issuer": "000001"},
                "query",
            ),
            "does not match issuer",
        ),
    ),
)
def test_event_manifest_helpers_reject_invalid_values(call, message):
    with pytest.raises(event_manifest.ManifestError, match=message):
        call()


def test_subtract_years_handles_leap_day():
    assert event_manifest._subtract_years(date(2024, 2, 29), 1) == date(
        2023,
        2,
        28,
    )


def _native_roster_fixture():
    declared = [
        {
            "id": "issuer:000001",
            "official_id": "issuer-000001",
        }
    ]
    payload = {
        "count": 1,
        "records": [
            {
                "officialId": "issuer-000001",
                "name": "平安银行",
                "type": "issuer",
                "role": "issuer",
                "start": "1991-04-03",
                "end": None,
            }
        ],
    }
    adapter = {
        "results_path": "records",
        "total_path": "count",
        "field_paths": {
            "official_id": "officialId",
            "name": "name",
            "type": "type",
            "role": "role",
            "service_start": "start",
            "service_end": "end",
        },
    }
    return payload, adapter, declared


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda payload, adapter, declared: declared.clear(),
            "subjects must be a non-empty list",
        ),
        (
            lambda payload, adapter, declared: declared.__setitem__(0, "bad"),
            "each subject must be an object",
        ),
        (
            lambda payload, adapter, declared: declared[0].pop("official_id"),
            "missing official_id",
        ),
        (
            lambda payload, adapter, declared: payload.update(count="1"),
            "invalid results or total",
        ),
        (
            lambda payload, adapter, declared: payload.update(count=2),
            "total does not match subjects",
        ),
        (
            lambda payload, adapter, declared: payload.update(records=["bad"]),
            "native response subject is invalid",
        ),
        (
            lambda payload, adapter, declared: payload["records"][0].update(officialId="unknown"),
            "official_id is missing or unknown",
        ),
        (
            lambda payload, adapter, declared: payload.update(
                count=0,
                records=[],
            ),
            "does not cover declared subjects",
        ),
    ),
)
def test_native_roster_adapter_rejects_invalid_evidence(mutation, message):
    payload, adapter, declared = _native_roster_fixture()
    mutation(payload, adapter, declared)

    with pytest.raises(event_manifest.ManifestError, match=message):
        event_manifest._native_roster_subjects(payload, adapter, declared)


def _native_event_fixture():
    adapter = {
        "page_number_path": "page",
        "page_count_path": "pages",
        "total_path": "count",
        "results_path": "records",
        "field_paths": {
            "record_id": "id",
            "issuer_code": "issuer",
            "subject_ids": "subjects",
            "title": "title",
            "offense_type": "offense",
            "legal_effect": "effect",
            "subject_role_at_occurrence": "roles",
            "issuer_connection": "connections",
            "occurrence_date": "occurred",
            "publication_time": "published",
            "status": "status",
            "status_effective_time": "statusSince",
            "document_url": "url",
        },
    }
    event = {
        "id": "evt-1",
        "issuer": "000001",
        "subjects": ["issuer-000001"],
        "title": "Penalty",
        "offense": "false_statement",
        "effect": "effective",
        "roles": {"issuer-000001": "issuer"},
        "connections": {"issuer-000001": "issuer"},
        "occurred": "2025-01-01",
        "published": "2025-01-02T00:00:00+08:00",
        "status": "effective",
        "statusSince": "2025-01-02T00:00:00+08:00",
        "url": "https://www.csrc.gov.cn/document/evt-1",
    }
    return {
        "page": 1,
        "pages": 1,
        "count": 1,
        "records": [event],
    }, adapter


def test_native_event_adapter_rejects_invalid_pagination():
    payload, adapter = _native_event_fixture()
    payload["page"] = 0

    with pytest.raises(event_manifest.ManifestError, match="pagination schema"):
        event_manifest._native_event_page(payload, adapter, "formal_sanctions")


def test_native_event_adapter_rejects_nonobject_event():
    payload, adapter = _native_event_fixture()
    payload["records"] = ["bad"]

    with pytest.raises(event_manifest.ManifestError, match="must be an object"):
        event_manifest._native_event_page(payload, adapter, "formal_sanctions")


@pytest.mark.parametrize(
    ("event", "message"),
    (
        (
            {
                "subject_ids": "issuer-000001",
                "subject_role_at_occurrence": {},
                "issuer_connection": {},
            },
            "subject attribution is invalid",
        ),
        (
            {
                "subject_ids": ["unknown"],
                "subject_role_at_occurrence": {"unknown": "issuer"},
                "issuer_connection": {"unknown": "issuer"},
            },
            "unknown official subject ID",
        ),
        (
            {
                "subject_ids": ["issuer-000001"],
                "subject_role_at_occurrence": {},
                "issuer_connection": {"issuer-000001": "issuer"},
            },
            "subject attribution is incomplete",
        ),
    ),
)
def test_native_event_subject_binding_rejects_invalid_attribution(event, message):
    subjects = {
        "issuer:000001": {
            "official_id": "issuer-000001",
        }
    }
    event.setdefault("occurrence_date", "2025-01-01")

    with pytest.raises(event_manifest.ManifestError, match=message):
        event_manifest._bind_native_event_subjects(
            event,
            subjects,
            "formal_sanctions",
        )


def _canonical_page(query=None, **updates):
    payload = {
        "query": query or {"issuer_code": "000001"},
        "page_no": 1,
        "page_count": 1,
        "total": 0,
        "results": [],
    }
    payload.update(updates)
    return payload


@pytest.mark.parametrize(
    ("row", "message"),
    (
        ({}, "response_files must be a non-empty list"),
        (
            {
                "response_files": ["/missing"],
                "response_schema": "unknown",
            },
            "response_schema is unsupported",
        ),
        (
            {
                "response_files": ["/missing"],
                "response_schema": "native_json_event_page_v1",
            },
            "response_adapter must be an object",
        ),
        (
            {
                "response_files": ["relative.json"],
                "response_schema": "canonical_event_page_v1",
            },
            "existing absolute path",
        ),
    ),
)
def test_load_response_pages_rejects_invalid_contract(row, message):
    with pytest.raises(event_manifest.ManifestError, match=message):
        event_manifest._load_response_pages(
            row,
            "formal_sanctions",
            {"issuer_code": "000001"},
        )


@pytest.mark.parametrize(
    ("body", "message"),
    (
        (b"not-json", "cannot parse response page"),
        (b"[]", "response page must be an object"),
        (
            json.dumps(_canonical_page(query={"issuer_code": "000002"})).encode(),
            "query does not match query_params",
        ),
        (
            json.dumps(_canonical_page(page_no=0)).encode(),
            "invalid response pagination schema",
        ),
        (
            json.dumps(_canonical_page(page_count=2)).encode(),
            "response pagination is incomplete",
        ),
        (
            json.dumps(_canonical_page(total=1, results=["bad"])).encode(),
            "response event must be an object",
        ),
    ),
)
def test_load_response_pages_rejects_invalid_stored_page(
    tmp_path,
    body,
    message,
):
    response = tmp_path / "response.json"
    response.write_bytes(body)
    row = {
        "response_files": [str(response)],
        "response_schema": "canonical_event_page_v1",
    }

    with pytest.raises(event_manifest.ManifestError, match=message):
        event_manifest._load_response_pages(
            row,
            "formal_sanctions",
            {"issuer_code": "000001"},
        )


@pytest.mark.parametrize(
    ("second_updates", "message"),
    (
        ({"page_no": 1, "page_count": 2}, "duplicate response page"),
        ({"page_no": 2, "page_count": 3}, "inconsistent response page_count"),
        ({"page_no": 2, "page_count": 2, "total": 1}, "inconsistent response total"),
    ),
)
def test_load_response_pages_rejects_inconsistent_pages(
    tmp_path,
    second_updates,
    message,
):
    query = {"issuer_code": "000001"}
    first = tmp_path / "page-1.json"
    second = tmp_path / "page-2.json"
    first.write_text(
        json.dumps(_canonical_page(query=query, page_count=2)),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps(_canonical_page(query=query, **second_updates)),
        encoding="utf-8",
    )
    row = {
        "response_files": [str(first), str(second)],
        "response_schema": "canonical_event_page_v1",
    }

    with pytest.raises(event_manifest.ManifestError, match=message):
        event_manifest._load_response_pages(
            row,
            "formal_sanctions",
            query,
        )


def _run_build_with_local_evidence(bundle: Path):
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster = payload.get("subject_roster")
    roster_body = (
        Path(roster["source_file"]).read_bytes()
        if isinstance(roster, dict) and "source_file" in roster
        else b"{}"
    )
    profile = payload.get("listing_profile")
    profile_body = (
        Path(profile["source_file"]).read_bytes()
        if isinstance(profile, dict) and "source_file" in profile
        else b"{}"
    )
    live_responses = {}
    if isinstance(roster, dict):
        live_responses[roster.get("source_url")] = roster_body
    if isinstance(profile, dict):
        live_responses[profile.get("source_url")] = profile_body
    categories = payload.get("categories")
    event_responses = (
        {
            row["category"]: [Path(path).read_bytes() for path in row.get("response_files", [])]
            for row in categories
            if isinstance(row, dict) and "category" in row
        }
        if isinstance(categories, list)
        else {}
    )

    return event_manifest.build_manifest(
        bundle,
        roster_fetcher=lambda url, _params: live_responses[url],
        event_fetcher=lambda _url, _method, _encoding, params, _contract: event_responses[
            params["category"]
        ],
        document_fetcher=lambda _url: b"official enforcement decision",
    )


def _add_historical_hk_listing(payload: dict, tmp_path: Path) -> None:
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.update(
        {
            "listing_codes": {"SZ": "000001", "HK": "02318"},
            "listing_dates": {
                "SZ": "1991-04-03",
                "HK": "2004-06-24",
            },
            "listing_statuses": {"SZ": "listed", "HK": "delisted"},
            "delisting_dates": {"SZ": None, "HK": "2020-12-31"},
        }
    )
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    payload["listing_codes"] = profile["listing_codes"]
    payload["listing_dates"] = profile["listing_dates"]

    source_hosts = {
        "hkex": "www.hkex.com.hk",
        "sfc": "www.sfc.hk",
        "afrc": "www.afrc.org.hk",
        "hkpf": "www.police.gov.hk",
        "icac": "www.icac.org.hk",
        "hkjd": "www.judiciary.hk",
    }
    first_by_category = {}
    for row in payload["categories"]:
        first_by_category.setdefault(row["category"], row)
    for category, source_ids in event_manifest.REQUIRED_SOURCE_IDS["HK"].items():
        for source_id in sorted(source_ids):
            row = deepcopy(first_by_category[category])
            row["source_id"] = source_id
            row["query_url"] = f"https://{source_hosts[source_id]}/{category}"
            row["query_issuer_code"] = "02318"
            row["query_params"] = {
                **row["query_params"],
                "issuer_code": "02318",
            }
            response_path = tmp_path / f"historical-hk-{category}-{source_id}.json"
            response_path.write_text(
                json.dumps(
                    {
                        "query": row["query_params"],
                        "page_no": 1,
                        "page_count": 1,
                        "total": 0,
                        "results": [],
                    }
                ),
                encoding="utf-8",
            )
            row["response_files"] = [str(response_path)]
            row["document_files"] = {}
            payload["categories"].append(row)


def _write_manifest_with_local_evidence(
    bundle: Path,
    output: Path,
) -> tuple[Path, dict, dict[str, bytes], dict[str, list[bytes]]]:
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    identity_bodies = {
        payload["listing_profile"]["source_url"]: Path(
            payload["listing_profile"]["source_file"]
        ).read_bytes(),
        payload["subject_roster"]["source_url"]: Path(
            payload["subject_roster"]["source_file"]
        ).read_bytes(),
    }
    event_bodies = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    published = event_manifest.write_manifest(
        bundle,
        output,
        roster_fetcher=lambda url, _params: identity_bodies[url],
        event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    return published, payload, identity_bodies, event_bodies


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda payload: payload.update(subject_roster=None),
            "subject_roster must be an object",
        ),
        (
            lambda payload: payload["subject_roster"].update(coverage_start="2020-01-01"),
            "full listing history",
        ),
        (
            lambda payload: payload["subject_roster"].update(controller_history_complete=False),
            "controller history is not complete",
        ),
        (
            lambda payload: payload["subject_roster"].update(management_roles_covered=["director"]),
            "directors,senior management,chair and cfo",
        ),
        (
            lambda payload: payload["subject_roster"].update(controller_status="unknown"),
            "controller_status is invalid",
        ),
        (
            lambda payload: payload.update(listing_date="2027-01-01"),
            "listing_date cannot be after AS_OF",
        ),
        (
            lambda payload: payload.update(subjects=[]),
            "subjects must be a non-empty list",
        ),
        (
            lambda payload: payload["subject_roster"]["query_params"].update(issuer_code="000002"),
            "query_params do not match issuer or coverage",
        ),
        (
            lambda payload: payload["subject_roster"].update(response_schema="unknown"),
            "subject_roster response_schema is unsupported",
        ),
        (
            lambda payload: payload["subjects"].__setitem__(0, "bad"),
            "each subject must be an object",
        ),
        (
            lambda payload: payload["subjects"][0].update(id=""),
            "invalid or duplicate subject",
        ),
        (
            lambda payload: payload["subjects"][0].update(role="director"),
            "role is invalid for issuer",
        ),
        (
            lambda payload: payload["subjects"][0].update(service_start="2027-01-01"),
            "invalid service period",
        ),
        (
            lambda payload: payload.update(categories=None),
            "categories must be a list",
        ),
        (
            lambda payload: payload["categories"].append("bad"),
            "each category must be an object",
        ),
        (
            lambda payload: payload["categories"].append(payload["categories"][0].copy()),
            "duplicate category",
        ),
        (
            lambda payload: payload.__setitem__(
                "categories",
                [
                    row
                    for row in payload["categories"]
                    if row["category"] != "other_regulatory_events"
                ],
            ),
            "category set mismatch",
        ),
        (
            lambda payload: payload["categories"][0].update(scope="rolling_3y"),
            "scope must be listing_history",
        ),
        (
            lambda payload: payload["categories"][0].update(query_end="2026-04-29"),
            "query_end must equal AS_OF",
        ),
        (
            lambda payload: payload["categories"][2].update(query_start="2025-01-01"),
            "prior three years",
        ),
        (
            lambda payload: payload["categories"][0].update(response_schema="unknown"),
            "response_schema is unsupported",
        ),
        (
            lambda payload: payload["categories"][0].update(query_issuer_code="000002"),
            "query issuer does not match ticker",
        ),
        (
            lambda payload: payload["categories"][0]["query_params"].update(issuer_code="000002"),
            "query issuer does not match ticker",
        ),
        (
            lambda payload: payload["categories"][0]["query_params"].update(end_date="2026-04-29"),
            "query end_date does not match AS_OF",
        ),
        (
            lambda payload: payload["categories"][0].update(document_files=[]),
            "document_files must be an object",
        ),
    ),
)
def test_build_manifest_rejects_invalid_bundle_sections(
    tmp_path,
    mutation,
    message,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    mutation(payload)
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match=message):
        _run_build_with_local_evidence(bundle)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda event, category: event.update(record_id=""),
            "record_id is missing or duplicate",
        ),
        (
            lambda event, category: event.update(content_file="/tmp/local"),
            "content_file must not appear",
        ),
        (
            lambda event, category: event.update(issuer_code="000002"),
            "event issuer does not match ticker",
        ),
        (
            lambda event, category: event.update(subject_ids=[]),
            "event subject binding is invalid",
        ),
        (
            lambda event, category: event.update(occurrence_date="2026-05-01"),
            "occurrence_date is after AS_OF",
        ),
        (
            lambda event, category: category.update(document_files={}),
            "document_files must map every event",
        ),
        (
            lambda event, category: event.update(title=""),
            "invalid event title or status",
        ),
        (
            lambda event, category: event.update(issuer_connection={"issuer:000001": "invalid"}),
            "issuer_connection is invalid",
        ),
        (
            lambda event, category: event.update(
                subject_ids=["manager:chair"],
                subject_role_at_occurrence={"manager:chair": "chair"},
                issuer_connection={"manager:chair": "unknown"},
            ),
            "effective event cannot have unknown issuer_connection",
        ),
        (
            lambda event, category: category["document_files"].update(
                ghost=next(iter(category["document_files"].values()))
            ),
            "document_files keys do not match",
        ),
    ),
)
def test_build_manifest_rejects_invalid_event_records(
    tmp_path,
    mutation,
    message,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = payload["categories"][0]
    response_path = Path(category["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    mutation(response["results"][0], category)
    response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match=message):
        _run_build_with_local_evidence(bundle)


def test_write_manifest_is_idempotent_and_versions_different_existing_output(
    tmp_path,
):
    bundle = _write_bundle(tmp_path)
    output = tmp_path / "events.json"

    first = subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--out", str(output)]
    )
    second = subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--out", str(output)]
    )
    assert first.returncode == 0
    assert second.returncode == 0

    output.write_text("different evidence", encoding="utf-8")
    third = subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--out", str(output)]
    )
    assert third.returncode == 0
    assert output.read_text(encoding="utf-8") == "different evidence"
    assert list(tmp_path.glob("events-*.json"))


def test_write_manifest_does_not_overwrite_concurrently_created_evidence(
    tmp_path,
    monkeypatch,
):
    bundle = _write_bundle(tmp_path)
    output = tmp_path / "events.json"
    original_exists = Path.exists
    race_injected = False

    def exists_with_race(path):
        nonlocal race_injected
        if path == output and not race_injected:
            race_injected = True
            output.write_text("competing evidence", encoding="utf-8")
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists_with_race)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--out", str(output)]
    )

    assert result.returncode == 2
    assert "refusing to overwrite evidence" in result.stderr
    assert output.read_text(encoding="utf-8") == "competing evidence"


def test_write_manifest_wraps_disappearing_concurrent_output(
    tmp_path,
    monkeypatch,
):
    bundle = _write_bundle(tmp_path)
    output = tmp_path / "events.json"

    def disappearing_link(_source, _destination):
        output.unlink(missing_ok=True)
        raise FileExistsError("concurrent output disappeared")

    monkeypatch.setattr(event_manifest.os, "link", disappearing_link)

    with pytest.raises(event_manifest.ManifestError, match=r"concurrent|publish"):
        event_manifest.write_manifest(
            bundle,
            output,
            roster_fetcher=lambda _url, _params: Path(
                json.loads(bundle.read_text())["subject_roster"]["source_file"]
            ).read_bytes(),
            event_fetcher=lambda _url, _method, _encoding, params, _contract: [
                Path(
                    next(
                        row
                        for row in json.loads(bundle.read_text())["categories"]
                        if row["category"] == params["category"]
                    )["response_files"][0]
                ).read_bytes()
            ],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


@pytest.mark.parametrize(
    "bound_input",
    ("listing_profile", "subject_roster", "response", "document"),
)
def test_write_manifest_rejects_bound_input_changed_before_hard_link(
    tmp_path,
    monkeypatch,
    bound_input,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    output = tmp_path / "events.json"
    identity_bodies = {
        payload["listing_profile"]["source_url"]: Path(
            payload["listing_profile"]["source_file"]
        ).read_bytes(),
        payload["subject_roster"]["source_url"]: Path(
            payload["subject_roster"]["source_file"]
        ).read_bytes(),
    }
    event_bodies = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    document_bodies = {}
    for row in payload["categories"]:
        for response_file in row["response_files"]:
            response = json.loads(Path(response_file).read_text(encoding="utf-8"))
            for event in response["results"]:
                document_bodies[event["document_url"]] = Path(
                    row["document_files"][event["record_id"]]
                ).read_bytes()
    if bound_input in {"listing_profile", "subject_roster"}:
        mutation_path = Path(payload[bound_input]["source_file"])
    elif bound_input == "response":
        mutation_path = Path(payload["categories"][0]["response_files"][0])
    else:
        mutation_path = Path(payload["categories"][0]["document_files"]["evt-1"])
    original_chmod = event_manifest.os.chmod
    changed = False

    def mutate_before_link(path, mode):
        nonlocal changed
        original_chmod(path, mode)
        if not changed:
            mutation_path.write_bytes(b"changed after build")
            changed = True

    monkeypatch.setattr(event_manifest.os, "chmod", mutate_before_link)

    with pytest.raises(
        event_manifest.ManifestError,
        match="changed before publication",
    ):
        event_manifest.write_manifest(
            bundle,
            output,
            roster_fetcher=lambda url, _params: identity_bodies[url],
            event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
            document_fetcher=lambda url: document_bodies[url],
        )

    assert not output.exists()


def test_event_manifest_aggregates_multiple_official_sources_per_category(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    primary = next(
        row
        for row in payload["categories"]
        if row["category"] == "formal_sanctions" and row["source_id"] == "csrc"
    )
    second_response = tmp_path / "formal-sanctions-second-source.json"
    second_query = {**primary["query_params"], "authority": "exchange"}
    second_content = tmp_path / "event-content-second.txt"
    second_content.write_text("official enforcement decision", encoding="utf-8")
    second_response.write_text(
        json.dumps(
            {
                "query": second_query,
                "page_no": 1,
                "page_count": 1,
                "total": 1,
                "results": [
                    {
                        "record_id": "evt-2",
                        "issuer_code": "000001",
                        "subject_ids": ["issuer:000001"],
                        "title": "Exchange disciplinary decision",
                        "offense_type": "false_statement",
                        "legal_effect": "effective",
                        "subject_role_at_occurrence": {"issuer:000001": "issuer"},
                        "issuer_connection": {"issuer:000001": "issuer"},
                        "occurrence_date": "2025-02-01",
                        "publication_time": "2025-02-10T09:30:00+08:00",
                        "status": "effective",
                        "status_effective_time": "2025-02-10T09:30:00+08:00",
                        "document_url": "https://www.szse.cn/document/evt-2",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    second = next(
        row
        for row in payload["categories"]
        if row["category"] == "formal_sanctions" and row["source_id"] == "szse"
    )
    second.update(
        {
            "query_params": second_query,
            "response_files": [str(second_response)],
            "document_files": {"evt-2": str(second_content)},
        }
    )
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    roster = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    manifest = event_manifest.build_manifest(
        bundle,
        roster_fetcher=lambda _url, _params: roster,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )

    sanction = manifest["queries"]["formal_sanctions"]
    assert sanction["source_count"] == 2
    assert {source["source_id"] for source in sanction["sources"]} == {
        "csrc",
        "szse",
    }
    assert sanction["official_result_total"] == 2
    assert [event["record_id"] for event in sanction["events"]] == ["evt-1", "evt-2"]
    assert [event["record_id"] for event in sanction["sources"][0]["events"]] == ["evt-1"]
    assert [event["record_id"] for event in sanction["sources"][1]["events"]] == ["evt-2"]


def test_event_manifest_requires_official_listing_profile_evidence(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload.pop("listing_profile", None)
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="official listing profile"):
        _run_build_with_local_evidence(bundle)


def test_event_manifest_requires_authenticated_listing_codes_and_dates(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.pop("listing_codes")
    profile.pop("listing_dates")
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(
        event_manifest.ManifestError,
        match=r"listing_codes|listing_dates",
    ):
        _run_build_with_local_evidence(bundle)


def test_listing_profile_rejects_numeric_code_that_loses_leading_zero(tmp_path):
    profile_path = tmp_path / "listing-profile.json"
    profile = {
        "query": {"issuer_code": "601398"},
        "issuer_code": "601398",
        "listing_codes": {"SH": "601398", "HK": 1398},
        "listing_date": "2006-10-27",
        "listing_dates": {"SH": "2006-10-27", "HK": "2006-10-27"},
        "listing_status": "listed",
        "delisting_date": None,
        "official_result_total": 1,
    }
    body = json.dumps(profile).encode()
    profile_path.write_bytes(body)
    bundle = {
        "listing_date": "2006-10-27",
        "listing_profile": {
            "source_url": "https://www.sse.com.cn/issuer/601398/profile",
            "query_params": profile["query"],
            "response_schema": "canonical_listing_profile_v1",
            "source_file": str(profile_path),
        },
    }

    with pytest.raises(
        event_manifest.ManifestError,
        match=r"listing_codes\.HK",
    ):
        event_manifest._validate_listing_profile(
            bundle,
            "SH",
            "601398",
            date(2026, 4, 30),
            lambda _url, _params: body,
        )


def test_hk_string_code_normalization_matches_live_revalidation(
    tmp_path,
    monkeypatch,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["listing_codes"] = {"SZ": "000001", "HK": "1398"}
    profile["listing_dates"] = {
        "SZ": "1991-04-03",
        "HK": "2006-10-27",
    }
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    payload["listing_codes"] = {"SZ": "000001", "HK": "01398"}
    payload["listing_dates"] = profile["listing_dates"]
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setitem(
        event_manifest.REQUIRED_SOURCE_IDS,
        "HK",
        {category: set() for category in REQUIRED_CATEGORIES},
    )
    identity_bodies = {
        payload["listing_profile"]["source_url"]: profile_path.read_bytes(),
        payload["subject_roster"]["source_url"]: Path(
            payload["subject_roster"]["source_file"]
        ).read_bytes(),
    }
    event_bodies = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    published = event_manifest.write_manifest(
        bundle,
        tmp_path / "events.json",
        roster_fetcher=lambda url, _params: identity_bodies[url],
        event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))

    assert manifest["查询发行人代码映射"]["HK"] == "01398"
    event_manifest.revalidate_manifest(
        published,
        roster_fetcher=lambda url, _params: identity_bodies[url],
        event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )


def test_event_manifest_rejects_incomplete_required_authority_set(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["categories"] = [
        row
        for row in payload["categories"]
        if not (row["category"] == "formal_sanctions" and row["source_id"] == "szse")
    ]
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="required official sources"):
        _run_build_with_local_evidence(bundle)


def test_event_manifest_requires_both_jurisdictions_for_ah_issuer(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    serialized = json.dumps(payload).replace("000001", "600000")
    payload = json.loads(serialized)
    payload["ticker"] = "600000.SH"
    payload["exchange"] = "SH"
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster_path.write_text(
        roster_path.read_text(encoding="utf-8").replace("000001", "600000"),
        encoding="utf-8",
    )
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.update(
        {
            "issuer_code": "600000",
            "listing_codes": {"SH": "600000", "HK": "01234"},
            "listing_dates": {
                "SH": "1991-04-03",
                "HK": "2000-06-15",
            },
        }
    )
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    for row in payload["categories"]:
        for response_file in row["response_files"]:
            response_path = Path(response_file)
            response_path.write_text(
                response_path.read_text(encoding="utf-8").replace("000001", "600000"),
                encoding="utf-8",
            )
    _replace_required_sources(payload, "SH")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="required official sources"):
        _run_build_with_local_evidence(bundle)


def test_event_manifest_accepts_ah_sources_with_jurisdiction_codes(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    serialized = json.dumps(payload).replace("000001", "601398")
    payload = json.loads(serialized)
    payload["ticker"] = "601398.SH"
    payload["exchange"] = "SH"
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster_path.write_text(
        roster_path.read_text(encoding="utf-8").replace("000001", "601398"),
        encoding="utf-8",
    )
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.update(
        {
            "issuer_code": "601398",
            "listing_codes": {"SH": "601398", "HK": "01398"},
            "listing_dates": {
                "SH": "1991-04-03",
                "HK": "2006-10-27",
            },
        }
    )
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    for row in payload["categories"]:
        for response_file in row["response_files"]:
            response_path = Path(response_file)
            response_path.write_text(
                response_path.read_text(encoding="utf-8").replace("000001", "601398"),
                encoding="utf-8",
            )
    _replace_required_sources(payload, "SH")

    source_hosts = {
        "hkex": "www.hkex.com.hk",
        "sfc": "www.sfc.hk",
        "afrc": "www.afrc.org.hk",
        "hkpf": "www.police.gov.hk",
        "icac": "www.icac.org.hk",
        "hkjd": "www.judiciary.hk",
    }
    first_by_category = {}
    for row in payload["categories"]:
        first_by_category.setdefault(row["category"], row)
    for category, source_ids in event_manifest.REQUIRED_SOURCE_IDS["HK"].items():
        for source_id in sorted(source_ids):
            row = deepcopy(first_by_category[category])
            row["source_id"] = source_id
            row["query_url"] = f"https://{source_hosts[source_id]}/{category}"
            row["query_issuer_code"] = "01398"
            row["query_params"] = {
                **row["query_params"],
                "issuer_code": "01398",
            }
            response_path = tmp_path / f"ah-{category}-{source_id}.json"
            response_path.write_text(
                json.dumps(
                    {
                        "query": row["query_params"],
                        "page_no": 1,
                        "page_count": 1,
                        "total": 0,
                        "results": [],
                    }
                ),
                encoding="utf-8",
            )
            row["response_files"] = [str(response_path)]
            row["document_files"] = {}
            payload["categories"].append(row)
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    responses = {}
    documents = {}
    for row in payload["categories"]:
        key = (row["category"], row["query_issuer_code"])
        responses[key] = [Path(path).read_bytes() for path in row["response_files"]]
        for response_file in row["response_files"]:
            response = json.loads(Path(response_file).read_text(encoding="utf-8"))
            for event in response["results"]:
                documents[event["document_url"]] = Path(
                    row["document_files"][event["record_id"]]
                ).read_bytes()

    manifest = event_manifest.build_manifest(
        bundle,
        roster_fetcher=lambda url, _params: (
            profile_path.read_bytes()
            if url == payload["listing_profile"]["source_url"]
            else roster_path.read_bytes()
        ),
        event_fetcher=lambda _url, _method, _encoding, params, _contract: responses[
            (params["category"], params["issuer_code"])
        ],
        document_fetcher=lambda url: documents[url],
    )

    assert manifest["查询发行人代码映射"] == {
        "SH": "601398",
        "HK": "01398",
    }
    assert {
        source["query_issuer_code"] for source in manifest["queries"]["formal_sanctions"]["sources"]
    } == {"601398", "01398"}


def test_event_manifest_ignores_counterpart_listing_after_as_of(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["listing_codes"] = {"SZ": "000001", "HK": "02318"}
    profile["listing_dates"] = {
        "SZ": "1991-04-03",
        "HK": "2027-01-01",
    }
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    payload["listing_codes"] = {"SZ": "000001", "HK": "02318"}
    payload["listing_dates"] = {
        "SZ": "1991-04-03",
        "HK": "2027-01-01",
    }
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    manifest = _run_build_with_local_evidence(bundle)

    assert manifest["查询发行人代码映射"] == {"SZ": "000001"}
    assert manifest["future_listing_codes"] == {"HK": "02318"}


def test_event_manifest_requires_historical_jurisdiction_sources_after_delisting(
    tmp_path,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.update(
        {
            "listing_codes": {"SZ": "000001", "HK": "02318"},
            "listing_dates": {
                "SZ": "1991-04-03",
                "HK": "2004-06-24",
            },
            "listing_statuses": {"SZ": "listed", "HK": "delisted"},
            "delisting_dates": {"SZ": None, "HK": "2020-12-31"},
        }
    )
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    payload["listing_codes"] = profile["listing_codes"]
    payload["listing_dates"] = profile["listing_dates"]
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="required official sources"):
        _run_build_with_local_evidence(bundle)


def test_rolling_queries_require_open_pre_window_investigation_flag(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    for row in payload["categories"]:
        if row["scope"] == "rolling_3y":
            row.pop("include_open_before_start", None)
            row["query_params"].pop("include_open_before_start", None)
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        event_manifest.ManifestError,
        match="include_open_before_start",
    ):
        _run_build_with_local_evidence(bundle)


def test_event_manifest_rejects_live_counterpart_listing_date_drift(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    profile_path = Path(payload["listing_profile"]["source_file"])
    stored_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    stored_profile["listing_codes"] = {"SZ": "000001", "HK": "02318"}
    stored_profile["listing_dates"] = {
        "SZ": "1991-04-03",
        "HK": "2004-06-24",
    }
    profile_path.write_text(json.dumps(stored_profile), encoding="utf-8")
    live_profile = {
        **stored_profile,
        "listing_dates": {
            "SZ": "1991-04-03",
            "HK": "2004-06-25",
        },
    }
    roster_path = Path(payload["subject_roster"]["source_file"])

    with pytest.raises(
        event_manifest.ManifestError,
        match="live official response byte hash differs",
    ):
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda url, _params: (
                json.dumps(live_profile).encode()
                if url == payload["listing_profile"]["source_url"]
                else roster_path.read_bytes()
            ),
            event_fetcher=lambda _url, _method, _encoding, params, _contract: [
                Path(
                    next(
                        row["response_files"][0]
                        for row in payload["categories"]
                        if row["category"] == params["category"]
                    )
                ).read_bytes()
            ],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_event_manifest_accepts_open_investigation_started_before_rolling_window(
    tmp_path,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category_rows = [
        row for row in payload["categories"] if row["category"] == "other_regulatory_events"
    ]
    category = category_rows[0]
    for row in category_rows:
        row["query_params"]["include_open_before_start"] = True
    response_path = Path(category["response_files"][0])
    content_path = tmp_path / "old-open-investigation.txt"
    content_path.write_text("official enforcement decision", encoding="utf-8")
    response_path.write_text(
        json.dumps(
            {
                "query": category["query_params"],
                "page_no": 1,
                "page_count": 1,
                "total": 1,
                "results": [
                    {
                        "record_id": "evt-open-old",
                        "issuer_code": "000001",
                        "subject_ids": ["manager:chair"],
                        "title": "Unresolved historical investigation",
                        "offense_type": "other",
                        "legal_effect": "investigation",
                        "subject_role_at_occurrence": {"manager:chair": "chair"},
                        "issuer_connection": {"manager:chair": "serving_at_occurrence"},
                        "occurrence_date": "2021-01-01",
                        "publication_time": "2021-01-10T09:30:00+08:00",
                        "status": "investigation",
                        "status_effective_time": "2021-01-10T09:30:00+08:00",
                        "document_url": ("https://www.csrc.gov.cn/document/evt-open-old"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    for row in category_rows:
        row["document_files"] = {"evt-open-old": str(content_path)}
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    manifest = _run_build_with_local_evidence(bundle)

    assert (
        manifest["queries"]["other_regulatory_events"]["events"][0]["record_id"] == "evt-open-old"
    )


def test_event_manifest_can_bind_auditor_investigation_to_auditor_subject(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    auditor = next(subject for subject in payload["subjects"] if subject["type"] == "auditor")
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    for category in payload["categories"]:
        category["query_params"]["subject_ids"].append(auditor["id"])
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    manifest = _run_build_with_local_evidence(bundle)

    assert any(subject["type"] == "auditor" for subject in manifest["subjects"])


def test_event_manifest_versions_same_as_of_conflicts_without_overwriting(tmp_path):
    bundle = _write_bundle(tmp_path)
    output = tmp_path / "events-2026-04-30.json"
    output.write_text("prior immutable evidence\n", encoding="utf-8")
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    published = event_manifest.write_manifest(
        bundle,
        output,
        roster_fetcher=lambda _url, _params: roster,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )

    assert published != output
    assert published.is_file()
    assert output.read_text(encoding="utf-8") == "prior immutable evidence\n"


def test_manifest_cli_prints_content_addressed_publication_path(tmp_path):
    bundle = _write_bundle(tmp_path)
    output = tmp_path / "events-2026-04-30.json"
    output.write_text("prior immutable evidence\n", encoding="utf-8")
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    stdout = io.StringIO()

    with redirect_stdout(stdout):
        returncode = event_manifest.main(
            ["--bundle", str(bundle), "--out", str(output)],
            roster_fetcher=lambda _url, _params: roster,
            event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )

    assert returncode == 0
    published = Path(stdout.getvalue().strip())
    assert published != output
    assert published.is_file()


def test_event_manifest_requires_auditor_subject_coverage(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["subjects"] = [
        subject for subject in payload["subjects"] if subject["type"] != "auditor"
    ]
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["subjects"] = payload["subjects"]
    roster["official_result_total"] = len(payload["subjects"])
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    subject_ids = [subject["id"] for subject in payload["subjects"]]
    for category in payload["categories"]:
        category["query_params"]["subject_ids"] = subject_ids
        response_path = Path(category["response_files"][0])
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["query"] = category["query_params"]
        response_path.write_text(json.dumps(response), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="auditor"):
        _run_build_with_local_evidence(bundle)


def test_bank_manifest_requires_bank_regulatory_sources(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["issuer_type"] = "bank"
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match=r"nfra|pbc"):
        _run_build_with_local_evidence(bundle)


def test_open_investigation_before_window_uses_top_level_plan_flag(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    category = next(
        row for row in payload["categories"] if row["category"] == "auditor_investigations"
    )
    response_path = Path(category["response_files"][0])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["total"] = 1
    response["results"] = [
        {
            "record_id": "open-before-window",
            "issuer_code": "000001",
            "subject_ids": ["issuer:000001"],
            "title": "Open investigation",
            "offense_type": "auditor_misconduct",
            "legal_effect": "investigation",
            "subject_role_at_occurrence": {"issuer:000001": "issuer"},
            "issuer_connection": {"issuer:000001": "issuer"},
            "occurrence_date": "2022-01-01",
            "publication_time": "2022-01-02T09:00:00+08:00",
            "status": "investigation",
            "status_effective_time": "2022-01-02T09:00:00+08:00",
            "document_url": "https://www.csrc.gov.cn/open-before-window",
        }
    ]
    response_path.write_text(json.dumps(response), encoding="utf-8")
    document = tmp_path / "open-before-window.txt"
    document.write_text("official enforcement decision", encoding="utf-8")
    for row in payload["categories"]:
        if row["category"] == "auditor_investigations":
            row["document_files"] = {"open-before-window": str(document.resolve())}
            row["query_params"]["include_open_before_start"] = True
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    manifest = _run_build_with_local_evidence(bundle)

    events = manifest["queries"]["auditor_investigations"]["events"]
    assert [event["record_id"] for event in events] == ["open-before-window"]


def test_distinct_cross_source_actions_are_not_merged(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    primary = payload["categories"][0]
    duplicate = next(
        row
        for row in payload["categories"]
        if row["category"] == "formal_sanctions" and row["source_id"] == "szse"
    )
    response_path = tmp_path / "same-event-other-source.json"
    response = json.loads(Path(primary["response_files"][0]).read_text())
    response["results"][0]["record_id"] = "szse-different-id"
    response["results"][0]["title"] = "Separate exchange disciplinary action"
    response["results"][0]["document_url"] = "https://www.szse.cn/document/separate-action"
    response_path.write_text(json.dumps(response), encoding="utf-8")
    duplicate["response_files"] = [str(response_path)]
    second_document = tmp_path / "separate-action.txt"
    second_document.write_text("official enforcement decision", encoding="utf-8")
    duplicate["document_files"] = {"szse-different-id": str(second_document)}
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    event_responses = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    manifest = event_manifest.build_manifest(
        bundle,
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: event_responses[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )

    sanction = manifest["queries"]["formal_sanctions"]
    assert sanction["source_count"] == 2
    assert len(sanction["events"]) == 2
    assert manifest["event_count"] >= 2


def test_event_manifest_rejects_unknown_source_id_as_manifest_error(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    extra = deepcopy(payload["categories"][0])
    extra["source_id"] = "unknown"
    payload["categories"].append(extra)
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="unknown source_id"):
        _run_build_with_local_evidence(bundle)


def test_revalidate_manifest_rejects_changed_live_event_response(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    output = tmp_path / "events.json"
    published = event_manifest.write_manifest(
        bundle,
        output,
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    changed_url = payload["categories"][0]["query_url"]
    live_by_url[changed_url] = [b'{"changed":true}']

    with pytest.raises(event_manifest.ManifestError, match="live official"):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda _url, _params: roster_body,
            event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


@pytest.mark.parametrize("mutation", ("deleted", "empty"))
def test_revalidate_manifest_rejects_missing_required_queries(tmp_path, mutation):
    bundle = _write_bundle(tmp_path)
    published, _payload, identity_bodies, event_bodies = _write_manifest_with_local_evidence(
        bundle,
        tmp_path / "events.json",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    if mutation == "deleted":
        manifest["queries"].pop("late_filings")
    else:
        manifest["queries"] = {}
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="category set mismatch"):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda url, _params: identity_bodies[url],
            event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_revalidate_manifest_rejects_deleted_historical_hk_source(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    _add_historical_hk_listing(payload, tmp_path)
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    published, _payload, identity_bodies, event_bodies = _write_manifest_with_local_evidence(
        bundle,
        tmp_path / "events.json",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    sanction = manifest["queries"]["formal_sanctions"]
    sanction["sources"] = [
        source for source in sanction["sources"] if source["source_id"] != "hkex"
    ]
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="required official sources"):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda url, _params: identity_bodies[url],
            event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_revalidate_manifest_rejects_tampered_delisting_status(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    _add_historical_hk_listing(payload, tmp_path)
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    published, _payload, identity_bodies, event_bodies = _write_manifest_with_local_evidence(
        bundle,
        tmp_path / "events.json",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    manifest["listing_profile"]["listing_statuses"]["HK"] = "listed"
    manifest["listing_profile"]["delisting_dates"]["HK"] = None
    manifest["查询发行人代码映射"]["HK"] = "02318"
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        event_manifest.ManifestError,
        match="listing_profile identity differs",
    ):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda url, _params: identity_bodies[url],
            event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_revalidate_manifest_applies_canonical_validation_to_native_events(tmp_path):
    bundle = _write_bundle(tmp_path)
    published, _payload, identity_bodies, event_bodies = _write_manifest_with_local_evidence(
        bundle,
        tmp_path / "events.json",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    sanction = manifest["queries"]["formal_sanctions"]
    adapter = {
        "page_number_path": "page",
        "page_count_path": "pages",
        "total_path": "count",
        "results_path": "records",
        "field_paths": {
            "record_id": "id",
            "issuer_code": "stock",
            "subject_ids": "subjects",
            "title": "headline",
            "offense_type": "offense",
            "legal_effect": "effect",
            "subject_role_at_occurrence": "roles",
            "issuer_connection": "connections",
            "occurrence_date": "occurredAt",
            "publication_time": "publishedAt",
            "status": "state",
            "status_effective_time": "statusSince",
            "document_url": "documentLink",
        },
    }
    native_body = json.dumps(
        {
            "page": 1,
            "pages": 1,
            "count": 1,
            "records": [
                {
                    "id": "evt-1",
                    "stock": "000001",
                    "subjects": ["issuer-000001"],
                    "headline": "Administrative penalty",
                    "offense": "false_statement",
                    "effect": "open",
                    "roles": {"issuer-000001": "issuer"},
                    "connections": {"issuer-000001": "issuer"},
                    "occurredAt": "2024-12-20",
                    "publishedAt": "2025-01-10T09:30:00+08:00",
                    "state": "open",
                    "statusSince": "2025-01-10T09:30:00+08:00",
                    "documentLink": "https://www.csrc.gov.cn/document/evt-1",
                }
            ],
        }
    ).encode()
    for source in sanction["sources"]:
        source["response_schema"] = "native_json_event_page_v1"
        source["response_adapter"] = adapter
        source["response_sha256"] = hashlib.sha256(native_body).hexdigest()
        source["live_response_sha256"] = source["response_sha256"]
        source["events"][0]["legal_effect"] = "open"
        source["events"][0]["status"] = "open"
        event_bodies[source["query_url"]] = [native_body]
    sanction["events"][0]["legal_effect"] = "open"
    sanction["events"][0]["status"] = "open"
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        event_manifest.ManifestError,
        match="invalid event title or status",
    ):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda url, _params: identity_bodies[url],
            event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_historical_delisted_counterpart_with_complete_sources_revalidates(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    _add_historical_hk_listing(payload, tmp_path)
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    published, _payload, identity_bodies, event_bodies = _write_manifest_with_local_evidence(
        bundle,
        tmp_path / "events.json",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))

    digest = event_manifest.revalidate_manifest(
        published,
        roster_fetcher=lambda url, _params: identity_bodies[url],
        event_fetcher=lambda url, _method, _encoding, _params, _contract: event_bodies[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )

    assert manifest["查询发行人代码映射"] == {"SZ": "000001"}
    assert {
        source["source_id"] for source in manifest["queries"]["formal_sanctions"]["sources"]
    }.issuperset(event_manifest.REQUIRED_SOURCE_IDS["HK"]["formal_sanctions"])
    assert digest == hashlib.sha256(published.read_bytes()).hexdigest()


def test_revalidate_manifest_rejects_tampered_derived_events(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    published = event_manifest.write_manifest(
        bundle,
        tmp_path / "events.json",
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    source = manifest["queries"]["formal_sanctions"]["sources"][0]
    source["events"] = []
    source["official_result_total"] = 0
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="derived events"):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda _url, _params: roster_body,
            event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_revalidate_manifest_rejects_tampered_event_semantics(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    published = event_manifest.write_manifest(
        bundle,
        tmp_path / "events.json",
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    source_event = manifest["queries"]["formal_sanctions"]["sources"][0]["events"][0]
    source_event["legal_effect"] = "investigation"
    source_event["status"] = "open"
    aggregate_event = manifest["queries"]["formal_sanctions"]["events"][0]
    aggregate_event["legal_effect"] = "investigation"
    aggregate_event["status"] = "open"
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="derived events"):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda _url, _params: roster_body,
            event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_revalidate_manifest_rejects_tampered_aggregate_event_semantics(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    published = event_manifest.write_manifest(
        bundle,
        tmp_path / "events.json",
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    aggregate_event = manifest["queries"]["formal_sanctions"]["events"][0]
    aggregate_event["title"] = "Tampered aggregate title"
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        event_manifest.ManifestError,
        match="derived aggregate events",
    ):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda _url, _params: roster_body,
            event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_revalidate_manifest_rejects_tampered_derived_subjects(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    published = event_manifest.write_manifest(
        bundle,
        tmp_path / "events.json",
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    manifest["subjects"][0]["name"] = "Tampered subject"
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(event_manifest.ManifestError, match="derived subjects"):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda _url, _params: roster_body,
            event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_historical_delisting_after_as_of_remains_in_scope(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["listing_status"] = "delisted"
    profile["delisting_date"] = "2027-01-01"
    profile["listing_statuses"] = {"SZ": "delisted"}
    profile["delisting_dates"] = {"SZ": "2027-01-01"}
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    manifest = _run_build_with_local_evidence(bundle)

    assert manifest["查询发行人代码映射"] == {"SZ": "000001"}


def test_revalidate_manifest_rejects_tampered_local_event_document(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    published = event_manifest.write_manifest(
        bundle,
        tmp_path / "events.json",
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    document_path = Path(payload["categories"][0]["document_files"]["evt-1"])
    document_path.write_text("tampered local decision", encoding="utf-8")

    with pytest.raises(
        event_manifest.ManifestError,
        match="stored document hash differs",
    ):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda _url, _params: roster_body,
            event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_revalidate_manifest_rejects_tampered_listing_identity(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    live_by_url = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }
    published = event_manifest.write_manifest(
        bundle,
        tmp_path / "events.json",
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )
    manifest = json.loads(published.read_text(encoding="utf-8"))
    manifest["查询发行人代码映射"] = {"SZ": "000002"}
    published.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        event_manifest.ManifestError,
        match="listing_profile identity differs",
    ):
        event_manifest.revalidate_manifest(
            published,
            roster_fetcher=lambda _url, _params: roster_body,
            event_fetcher=lambda url, _method, _encoding, _params, _contract: live_by_url[url],
            document_fetcher=lambda _url: b"official enforcement decision",
        )


def test_ah_roster_must_start_at_the_earliest_listing_date(
    tmp_path,
    monkeypatch,
):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["ticker"] = "01398.HK"
    payload["exchange"] = "HK"
    payload["query_issuer_code"] = "01398"
    payload["listing_date"] = "2006-10-27"
    payload["listing_codes"] = {"SH": "601398", "HK": "01398"}
    payload["listing_dates"] = {"SH": "2000-01-01", "HK": "2006-10-27"}
    profile_path = Path(payload["listing_profile"]["source_file"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.update(
        {
            "query": {"issuer_code": "01398"},
            "issuer_code": "01398",
            "listing_codes": payload["listing_codes"],
            "listing_date": "2006-10-27",
            "listing_dates": payload["listing_dates"],
        }
    )
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    payload["listing_profile"]["query_params"] = {"issuer_code": "01398"}
    roster_path = Path(payload["subject_roster"]["source_file"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["coverage_start"] = "2006-10-27"
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    payload["subject_roster"]["coverage_start"] = "2006-10-27"
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    seen = {}

    def capture_roster_start(
        _bundle,
        _exchange,
        _ticker_code,
        listing_history_start,
        _as_of,
        _roster_fetcher,
    ):
        seen["listing_history_start"] = listing_history_start
        raise event_manifest.ManifestError("captured roster start")

    monkeypatch.setattr(
        event_manifest,
        "_validate_subject_roster",
        capture_roster_start,
    )

    with pytest.raises(event_manifest.ManifestError, match="captured roster start"):
        event_manifest.build_manifest(
            bundle,
            roster_fetcher=lambda url, _params: (
                profile_path.read_bytes()
                if url == payload["listing_profile"]["source_url"]
                else roster_path.read_bytes()
            ),
        )

    assert seen["listing_history_start"] == date(2000, 1, 1)


def test_same_cross_source_event_is_counted_once(tmp_path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    primary = next(
        row
        for row in payload["categories"]
        if row["category"] == "formal_sanctions" and row["source_id"] == "csrc"
    )
    duplicate = next(
        row
        for row in payload["categories"]
        if row["category"] == "formal_sanctions" and row["source_id"] == "szse"
    )
    response_path = tmp_path / "same-action-other-source.json"
    response = json.loads(Path(primary["response_files"][0]).read_text())
    response["query"] = duplicate["query_params"]
    response["results"][0]["record_id"] = "same-action-second-record"
    response["results"][0]["document_url"] = "https://www.szse.cn/document/same-action"
    response_path.write_text(json.dumps(response), encoding="utf-8")
    duplicate["response_files"] = [str(response_path)]
    same_document = tmp_path / "same-action.txt"
    same_document.write_text("official enforcement decision", encoding="utf-8")
    duplicate["document_files"] = {"same-action-second-record": str(same_document)}
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    roster_body = Path(payload["subject_roster"]["source_file"]).read_bytes()
    event_responses = {
        row["query_url"]: [Path(path).read_bytes() for path in row["response_files"]]
        for row in payload["categories"]
    }

    manifest = event_manifest.build_manifest(
        bundle,
        roster_fetcher=lambda _url, _params: roster_body,
        event_fetcher=lambda url, _method, _encoding, _params, _contract: event_responses[url],
        document_fetcher=lambda _url: b"official enforcement decision",
    )

    events = manifest["queries"]["formal_sanctions"]["events"]
    assert len(events) == 1
    assert events[0]["provenance"] == [
        {
            "source_id": "csrc",
            "record_id": "evt-1",
            "document_url": "https://www.csrc.gov.cn/document/evt-1",
        },
        {
            "source_id": "szse",
            "record_id": "same-action-second-record",
            "document_url": "https://www.szse.cn/document/same-action",
        },
    ]
