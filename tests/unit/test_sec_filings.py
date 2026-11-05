from __future__ import annotations

import gzip
import json
import urllib.error
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from scripts import sec_filings


class _HttpResponse:
    def __init__(self, body: bytes, *, encoding: str = "") -> None:
        self.body = body
        self.headers = {"Content-Encoding": encoding}

    def __enter__(self) -> _HttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _ticker_payload(*rows: dict[str, object]) -> bytes:
    return json.dumps({str(index): row for index, row in enumerate(rows)}).encode()


def _submissions_payload(
    rows: list[dict[str, str]], *, historical_files: list[str] | None = None
) -> bytes:
    columns = {
        key: [row[key] for row in rows]
        for key in (
            "accessionNumber",
            "filingDate",
            "reportDate",
            "acceptanceDateTime",
            "form",
            "primaryDocument",
        )
    }
    return json.dumps(
        {
            "cik": "0001559720",
            "name": "Airbnb, Inc.",
            "filings": {
                "recent": columns,
                "files": [{"name": name} for name in historical_files or []],
            },
        }
    ).encode()


def _historical_payload(rows: list[dict[str, str]]) -> bytes:
    return json.dumps(
        {
            key: [row[key] for row in rows]
            for key in (
                "accessionNumber",
                "filingDate",
                "reportDate",
                "acceptanceDateTime",
                "form",
                "primaryDocument",
            )
        }
    ).encode()


def _row(
    accession: str,
    filed: str,
    report: str,
    form: str,
    document: str = "abnb.htm",
    accepted: str | None = None,
) -> dict[str, str]:
    return {
        "accessionNumber": accession,
        "filingDate": filed,
        "reportDate": report,
        "acceptanceDateTime": accepted or f"{filed.replace('-', '')}163000",
        "form": form,
        "primaryDocument": document,
    }


def test_parse_us_ticker_normalizes_symbol() -> None:
    assert sec_filings.parse_us_ticker(" abnb.us ") == "ABNB.US"


@pytest.mark.parametrize(
    "ticker",
    ("ABNB", "123.US", "BRK/B.US", "ABNB.NYSE", "ABNB..US", "A B.US"),
)
def test_parse_us_ticker_rejects_invalid_research_identity(ticker: str) -> None:
    with pytest.raises(ValueError, match="US research ticker"):
        sec_filings.parse_us_ticker(ticker)


def test_sec_client_requires_identity_and_decodes_gzip(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="User-Agent"):
        sec_filings.SecClient("anonymous")

    body = b'{"ok": true}'
    seen: list[object] = []

    def urlopen(request: object, *, timeout: float) -> _HttpResponse:
        seen.extend((request, timeout))
        return _HttpResponse(gzip.compress(body), encoding="gzip")

    monkeypatch.setattr(sec_filings.urllib.request, "urlopen", urlopen)
    client = sec_filings.SecClient("research@example.com", min_interval=0, timeout=4)

    assert client.get("https://www.sec.gov/example.json") == body
    assert seen[1] == 4
    assert seen[0].get_header("User-agent") == "research@example.com"
    assert seen[0].get_header("Accept-encoding") == "gzip, deflate"


def test_sec_client_retries_transient_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    sleeps: list[float] = []

    def urlopen(request: object, *, timeout: float) -> _HttpResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "busy", None, None)
        return _HttpResponse(b"ok")

    monkeypatch.setattr(sec_filings.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(sec_filings.time, "sleep", sleeps.append)

    assert (
        sec_filings.SecClient("research@example.com", min_interval=0).get(
            "https://www.sec.gov/example"
        )
        == b"ok"
    )
    assert calls == 2
    assert sleeps == [1]


def test_sec_client_stops_after_url_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sec_filings.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    monkeypatch.setattr(sec_filings.time, "sleep", lambda _: None)

    with pytest.raises(urllib.error.URLError, match="offline"):
        sec_filings.SecClient("research@example.com", min_interval=0).get(
            "https://www.sec.gov/example"
        )


def test_resolve_sec_identity_binds_zero_padded_cik() -> None:
    payload = _ticker_payload(
        {"cik_str": 1559720, "ticker": "ABNB", "title": "Airbnb, Inc.", "exchange": "Nasdaq"}
    )

    identity = sec_filings.resolve_sec_identity("abnb.us", payload)

    assert identity.canonical_ticker == "ABNB.US"
    assert identity.cik == "0001559720"
    assert identity.issuer_name == "Airbnb, Inc."
    assert identity.sec_ticker == "ABNB"
    assert identity.exchange == "Nasdaq"


def test_resolve_sec_identity_rejects_duplicate_ticker_rows() -> None:
    payload = _ticker_payload(
        {"cik_str": 1559720, "ticker": "ABNB", "title": "Airbnb, Inc."},
        {"cik_str": 9999999, "ticker": "ABNB", "title": "Other"},
    )

    with pytest.raises(sec_filings.SecEvidenceError, match="duplicate SEC ticker"):
        sec_filings.resolve_sec_identity("ABNB.US", payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b"not-json", "valid UTF-8 JSON"),
        (b"[]", "JSON object"),
        (_ticker_payload({"ticker": "OTHER", "cik_str": 1}), "does not contain"),
        (_ticker_payload({"ticker": "ABNB", "cik_str": "bad", "title": "Airbnb"}), "invalid CIK"),
        (_ticker_payload({"ticker": "ABNB", "cik_str": 1559720, "title": ""}), "invalid issuer"),
    ),
)
def test_resolve_sec_identity_rejects_invalid_mapping(payload: bytes, message: str) -> None:
    with pytest.raises(sec_filings.SecEvidenceError, match=message):
        sec_filings.resolve_sec_identity("ABNB.US", payload)


def test_archive_url_validates_accession_and_document() -> None:
    assert sec_filings.archive_url("0001559720", "0001559720-26-000027", "abnb-20260630.htm") == (
        "https://www.sec.gov/Archives/edgar/data/1559720/000155972026000027/abnb-20260630.htm"
    )

    with pytest.raises(ValueError, match="accession"):
        sec_filings.archive_url("0001559720", "bad", "abnb.htm")
    with pytest.raises(ValueError, match="document"):
        sec_filings.archive_url("0001559720", "0001559720-26-000027", "../bad.htm")
    with pytest.raises(ValueError, match="CIK"):
        sec_filings.archive_url("1559720", "0001559720-26-000027", "abnb.htm")
    with pytest.raises(ValueError, match="CIK"):
        sec_filings.submissions_url("1559720")
    with pytest.raises(ValueError, match="historical submissions"):
        sec_filings.historical_submissions_url("old.json")


def test_parse_submission_catalog_loads_all_historical_segments() -> None:
    recent = [_row("0001559720-26-000027", "2026-08-06", "2026-06-30", "10-Q")]
    old = [_row("0001559720-25-000010", "2025-02-14", "2024-12-31", "10-K")]

    catalog = sec_filings.parse_submission_catalog(
        _submissions_payload(recent, historical_files=["CIK0001559720-submissions-001.json"]),
        {"CIK0001559720-submissions-001.json": _historical_payload(old)},
    )

    assert [filing.form for filing in catalog] == ["10-Q", "10-K"]
    assert all(filing.cik == "0001559720" for filing in catalog)


def test_parse_submission_catalog_rejects_missing_segment() -> None:
    current = _submissions_payload([], historical_files=["missing.json"])

    with pytest.raises(sec_filings.SecEvidenceError, match="historical submissions"):
        sec_filings.parse_submission_catalog(current, {})


def test_parse_submission_catalog_rejects_conflicting_duplicate_accession() -> None:
    accession = "0001559720-26-000027"
    recent = [_row(accession, "2026-08-06", "2026-06-30", "10-Q")]
    old = [_row(accession, "2026-08-06", "2026-03-31", "10-Q")]

    with pytest.raises(sec_filings.SecEvidenceError, match="conflicting duplicate accession"):
        sec_filings.parse_submission_catalog(
            _submissions_payload(recent, historical_files=["old.json"]),
            {"old.json": _historical_payload(old)},
        )


def test_select_filing_set_is_as_of_correct_and_uses_audited_baseline() -> None:
    rows = [
        _row("0001559720-26-000027", "2026-08-06", "2026-06-30", "10-Q"),
        _row("0001559720-26-000015", "2026-05-08", "2026-03-31", "10-Q"),
        _row("0001559720-26-000006", "2026-02-13", "2025-12-31", "10-K"),
        _row("0001559720-25-000030", "2025-11-06", "2025-09-30", "10-Q"),
        _row("0001559720-25-000020", "2025-08-07", "2025-06-30", "10-Q"),
        _row("0001559720-25-000014", "2025-05-08", "2025-03-31", "10-Q"),
        _row("0001559720-27-000001", "2027-02-12", "2026-12-31", "10-K"),
    ]
    catalog = sec_filings.parse_submission_catalog(_submissions_payload(rows), {})

    selected = sec_filings.select_filing_set(catalog, date(2026, 9, 2))

    assert selected.latest_report.accession == "0001559720-26-000027"
    assert selected.audited_baseline.accession == "0001559720-26-000006"
    assert [item.report_period.isoformat() for item in selected.comparable_quarters] == [
        "2026-03-31",
        "2025-09-30",
        "2025-06-30",
        "2025-03-31",
    ]


def test_select_filing_set_prefers_resolved_amendment() -> None:
    rows = [
        _row("0001559720-26-000027", "2026-08-06", "2026-06-30", "10-Q"),
        _row("0001559720-26-000031", "2026-08-12", "2026-06-30", "10-Q/A"),
        _row("0001559720-26-000006", "2026-02-13", "2025-12-31", "10-K"),
    ]
    catalog = sec_filings.parse_submission_catalog(_submissions_payload(rows), {})

    selected = sec_filings.select_filing_set(catalog, date(2026, 9, 2))

    assert selected.latest_report.form == "10-Q/A"
    assert selected.latest_report.amends_accession == "0001559720-26-000027"


def test_select_filing_set_rejects_unresolved_amendment() -> None:
    rows = [
        _row("0001559720-26-000031", "2026-08-12", "2026-06-30", "10-Q/A"),
        _row("0001559720-26-000006", "2026-02-13", "2025-12-31", "10-K"),
    ]
    catalog = sec_filings.parse_submission_catalog(_submissions_payload(rows), {})

    with pytest.raises(sec_filings.SecEvidenceError, match="unresolved amendment"):
        sec_filings.select_filing_set(catalog, date(2026, 9, 2))


def test_select_filing_set_requires_current_report_and_annual_baseline() -> None:
    with pytest.raises(sec_filings.SecEvidenceError, match="no qualifying"):
        sec_filings.select_filing_set((), date(2026, 9, 2))

    catalog = sec_filings.parse_submission_catalog(
        _submissions_payload([_row("0001559720-26-000027", "2026-08-06", "2026-06-30", "10-Q")]),
        {},
    )
    with pytest.raises(sec_filings.SecEvidenceError, match="audited 10-K"):
        sec_filings.select_filing_set(catalog, date(2026, 9, 2))


def test_submission_catalog_rejects_invalid_columns_and_dates() -> None:
    missing_column = json.loads(_submissions_payload([]))
    del missing_column["filings"]["recent"]["form"]
    with pytest.raises(sec_filings.SecEvidenceError, match="column form"):
        sec_filings.parse_submission_catalog(json.dumps(missing_column).encode(), {})

    unequal = json.loads(_submissions_payload([]))
    unequal["filings"]["recent"]["form"].append("10-Q")
    with pytest.raises(sec_filings.SecEvidenceError, match="unequal lengths"):
        sec_filings.parse_submission_catalog(json.dumps(unequal).encode(), {})

    bad_date = [_row("0001559720-26-000027", "bad", "2026-06-30", "10-Q")]
    with pytest.raises(sec_filings.SecEvidenceError, match="invalid filing date"):
        sec_filings.parse_submission_catalog(_submissions_payload(bad_date), {})

    bad_acceptance = [
        _row(
            "0001559720-26-000027",
            "2026-08-06",
            "2026-06-30",
            "10-Q",
            accepted="bad",
        )
    ]
    with pytest.raises(sec_filings.SecEvidenceError, match="acceptanceDateTime"):
        sec_filings.parse_submission_catalog(_submissions_payload(bad_acceptance), {})


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda payload: payload.pop("cik"), "issuer identity"),
        (lambda payload: payload.__setitem__("filings", []), "filings must be an object"),
        (
            lambda payload: payload["filings"].__setitem__("files", {}),
            "historical submissions list",
        ),
        (
            lambda payload: payload["filings"].__setitem__("files", ["bad"]),
            "historical submissions entry",
        ),
    ),
)
def test_submission_catalog_rejects_invalid_envelope(mutation: object, message: str) -> None:
    payload = json.loads(_submissions_payload([]))
    mutation(payload)

    with pytest.raises(sec_filings.SecEvidenceError, match=message):
        sec_filings.parse_submission_catalog(json.dumps(payload).encode(), {})


@dataclass
class FakeSecClient:
    responses: dict[str, bytes]

    def __post_init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str) -> bytes:
        self.calls.append(url)
        if url not in self.responses:
            raise AssertionError(f"unexpected SEC request: {url}")
        return self.responses[url]


def _index_payload(*documents: str) -> bytes:
    return json.dumps(
        {"directory": {"item": [{"name": name, "type": "text/html"} for name in documents]}}
    ).encode()


def _manifest_responses() -> dict[str, bytes]:
    rows = [
        _row(
            "0001559720-26-000026",
            "2026-08-06",
            "2026-06-30",
            "8-K",
            "abnb-20260806.htm",
            "20260806160000",
        ),
        _row(
            "0001559720-26-000027",
            "2026-08-06",
            "2026-06-30",
            "10-Q",
            "abnb-20260630.htm",
        ),
        _row(
            "0001559720-26-000006",
            "2026-02-13",
            "2025-12-31",
            "10-K",
            "abnb-20251231.htm",
        ),
        _row(
            "0001559720-25-000030",
            "2025-11-06",
            "2025-09-30",
            "10-Q",
            "abnb-20250930.htm",
        ),
        _row(
            "0001559720-25-000020",
            "2025-08-07",
            "2025-06-30",
            "10-Q",
            "abnb-20250630.htm",
        ),
        _row(
            "0001559720-25-000014",
            "2025-05-08",
            "2025-03-31",
            "10-Q",
            "abnb-20250331.htm",
        ),
        _row(
            "0001559720-24-000040",
            "2024-11-07",
            "2024-09-30",
            "10-Q",
            "abnb-20240930.htm",
        ),
    ]
    responses = {
        sec_filings.SEC_TICKERS_URL: _ticker_payload(
            {"cik_str": 1559720, "ticker": "ABNB", "title": "Airbnb, Inc."}
        ),
        sec_filings.submissions_url("0001559720"): _submissions_payload(rows),
    }
    for row in rows:
        index_url = sec_filings.filing_index_url("0001559720", row["accessionNumber"])
        document_url = sec_filings.archive_url(
            "0001559720", row["accessionNumber"], row["primaryDocument"]
        )
        responses[index_url] = _index_payload(row["primaryDocument"])
        responses[document_url] = (
            f'<html><body><ix:nonNumeric name="dei:EntityCentralIndexKey">'
            f'0001559720</ix:nonNumeric><p id="report">{row["form"]}</p></body></html>'
        ).encode()
    eight_k_accession = "0001559720-26-000026"
    eight_k_index = sec_filings.filing_index_url("0001559720", eight_k_accession)
    exhibit_document = "airbnb-q2-2026-shareholder-letter.htm"
    responses[eight_k_index] = json.dumps(
        {
            "directory": {
                "item": [
                    {"name": "abnb-20260806.htm", "type": "8-K"},
                    {"name": exhibit_document, "type": "EX-99.1"},
                    {"name": "abnb-20260630.xsd", "type": "EX-101.SCH"},
                ]
            }
        }
    ).encode()
    responses[sec_filings.archive_url("0001559720", eight_k_accession, exhibit_document)] = (
        b"<html><body><h1>Q2 2026 shareholder letter</h1></body></html>"
    )
    return responses


def test_build_manifest_persists_selected_evidence_with_hashes(tmp_path: Path) -> None:
    responses = _manifest_responses()
    client = FakeSecClient(responses)

    path = sec_filings.build_filing_manifest(
        "ABNB.US", date(2026, 9, 2), tmp_path / "ABNB.US", client
    )

    manifest = json.loads(path.read_text())
    assert manifest["schema_version"] == "us-sec-filing-manifest/1.0"
    assert manifest["identity"]["canonical_ticker"] == "ABNB.US"
    assert manifest["identity"]["cik"] == "0001559720"
    assert manifest["selection"]["latest_report"] == "0001559720-26-000027"
    assert manifest["selection"]["audited_baseline"] == "0001559720-26-000006"
    assert len(manifest["selection"]["comparable_quarters"]) == 4
    assert len(manifest["requests"]) == len(client.calls)
    assert all(len(request["sha256"]) == 64 for request in manifest["requests"])
    assert all(Path(request["artifact_path"]).is_absolute() for request in manifest["requests"])
    assert all(Path(request["artifact_path"]).is_file() for request in manifest["requests"])
    assert manifest["filings"]["0001559720-26-000027"]["role"] == "latest_report"
    assert manifest["filings"]["0001559720-26-000006"]["role"] == "audited_baseline"
    assert manifest["earnings_exhibits"] == [
        {
            "accession": "0001559720-26-000026",
            "acceptance_datetime": "2026-08-06T16:00:00+00:00",
            "exhibit_document": "airbnb-q2-2026-shareholder-letter.htm",
            "exhibit_sha256": sec_filings.sha256_bytes(
                responses[
                    sec_filings.archive_url(
                        "0001559720",
                        "0001559720-26-000026",
                        "airbnb-q2-2026-shareholder-letter.htm",
                    )
                ]
            ),
            "exhibit_type": "EX-99.1",
            "filing_date": "2026-08-06",
            "filing_document_sha256": sec_filings.sha256_bytes(
                responses[
                    sec_filings.archive_url(
                        "0001559720", "0001559720-26-000026", "abnb-20260806.htm"
                    )
                ]
            ),
            "form": "8-K",
            "index_sha256": sec_filings.sha256_bytes(
                responses[sec_filings.filing_index_url("0001559720", "0001559720-26-000026")]
            ),
            "official_exhibit_url": sec_filings.archive_url(
                "0001559720",
                "0001559720-26-000026",
                "airbnb-q2-2026-shareholder-letter.htm",
            ),
            "official_filing_url": sec_filings.archive_url(
                "0001559720", "0001559720-26-000026", "abnb-20260806.htm"
            ),
            "primary_document": "abnb-20260806.htm",
            "report_period": "2026-06-30",
        }
    ]
    assert not manifest["limitations"]


def test_build_manifest_ignores_8k_outside_latest_report_cycle(tmp_path: Path) -> None:
    responses = _manifest_responses()
    submissions = sec_filings.submissions_url("0001559720")
    payload = json.loads(responses[submissions])
    recent = payload["filings"]["recent"]
    unrelated = _row(
        "0001559720-26-000030",
        "2026-08-07",
        "2026-06-30",
        "8-K",
        "abnb-unrelated.htm",
    )
    for key, value in unrelated.items():
        recent[key].append(value)
    responses[submissions] = json.dumps(payload).encode()

    client = FakeSecClient(responses)
    path = sec_filings.build_filing_manifest(
        "ABNB.US", date(2026, 9, 2), tmp_path / "ABNB.US", client
    )

    manifest = json.loads(path.read_text())
    assert len(manifest["earnings_exhibits"]) == 1
    assert not any("000155972026000030" in url for url in client.calls)


def test_build_manifest_records_missing_same_cycle_exhibit(tmp_path: Path) -> None:
    responses = _manifest_responses()
    index_url = sec_filings.filing_index_url("0001559720", "0001559720-26-000026")
    responses[index_url] = responses[index_url].replace(b"EX-99.1", b"GRAPHIC")

    path = sec_filings.build_filing_manifest(
        "ABNB.US", date(2026, 9, 2), tmp_path / "ABNB.US", FakeSecClient(responses)
    )

    manifest = json.loads(path.read_text())
    assert manifest["earnings_exhibits"] == []
    assert "no same-cycle 8-K" in manifest["limitations"][0]


def test_build_manifest_uses_latest_period_when_8k_report_date_is_empty(
    tmp_path: Path,
) -> None:
    responses = _manifest_responses()
    submissions = sec_filings.submissions_url("0001559720")
    payload = json.loads(responses[submissions])
    payload["filings"]["recent"]["reportDate"][0] = ""
    responses[submissions] = json.dumps(payload).encode()

    path = sec_filings.build_filing_manifest(
        "ABNB.US", date(2026, 9, 2), tmp_path / "ABNB.US", FakeSecClient(responses)
    )

    manifest = json.loads(path.read_text())
    assert manifest["earnings_exhibits"][0]["report_period"] == "2026-06-30"


def test_build_manifest_rejects_invalid_8k_date(tmp_path: Path) -> None:
    responses = _manifest_responses()
    submissions = sec_filings.submissions_url("0001559720")
    payload = json.loads(responses[submissions])
    payload["filings"]["recent"]["filingDate"][0] = "bad"
    responses[submissions] = json.dumps(payload).encode()

    with pytest.raises(sec_filings.SecEvidenceError, match="invalid 8-K date"):
        sec_filings.build_filing_manifest(
            "ABNB.US",
            date(2026, 9, 2),
            tmp_path / "ABNB.US",
            FakeSecClient(responses),
        )


def test_build_manifest_rejects_submissions_cik_mismatch(tmp_path: Path) -> None:
    responses = _manifest_responses()
    submissions = sec_filings.submissions_url("0001559720")
    payload = json.loads(responses[submissions])
    payload["cik"] = "1"
    responses[submissions] = json.dumps(payload).encode()

    with pytest.raises(sec_filings.SecEvidenceError, match="CIK identity mismatch"):
        sec_filings.build_filing_manifest(
            "ABNB.US",
            date(2026, 9, 2),
            tmp_path / "ABNB.US",
            FakeSecClient(responses),
        )


def test_build_manifest_rejects_missing_selected_primary_document(tmp_path: Path) -> None:
    responses = _manifest_responses()
    latest_index = sec_filings.filing_index_url("0001559720", "0001559720-26-000027")
    responses[latest_index] = _index_payload("other.htm")

    with pytest.raises(sec_filings.SecEvidenceError, match="absent from index"):
        sec_filings.build_filing_manifest(
            "ABNB.US",
            date(2026, 9, 2),
            tmp_path / "ABNB.US",
            FakeSecClient(responses),
        )


def test_build_manifest_rejects_missing_8k_primary_document(tmp_path: Path) -> None:
    responses = _manifest_responses()
    eight_k_index = sec_filings.filing_index_url("0001559720", "0001559720-26-000026")
    responses[eight_k_index] = _index_payload("other.htm")

    with pytest.raises(sec_filings.SecEvidenceError, match="8-K index"):
        sec_filings.build_filing_manifest(
            "ABNB.US",
            date(2026, 9, 2),
            tmp_path / "ABNB.US",
            FakeSecClient(responses),
        )


def test_build_manifest_refuses_identity_mismatch(tmp_path: Path) -> None:
    responses = _manifest_responses()
    latest = sec_filings.archive_url("0001559720", "0001559720-26-000027", "abnb-20260630.htm")
    responses[latest] = responses[latest].replace(b"0001559720", b"0000000001")

    with pytest.raises(sec_filings.SecEvidenceError, match="CIK identity mismatch"):
        sec_filings.build_filing_manifest(
            "ABNB.US", date(2026, 9, 2), tmp_path / "ABNB.US", FakeSecClient(responses)
        )


def test_content_addressed_artifact_refuses_different_existing_bytes(tmp_path: Path) -> None:
    body = b"original"
    path = sec_filings.persist_artifact(tmp_path, body, suffix=".json")
    path.write_bytes(b"mutated")

    with pytest.raises(sec_filings.SecEvidenceError, match="content-addressed artifact"):
        sec_filings.persist_artifact(tmp_path, body, suffix=".json")


def test_revalidate_manifest_detects_remote_drift(tmp_path: Path) -> None:
    responses = _manifest_responses()
    path = sec_filings.build_filing_manifest(
        "ABNB.US", date(2026, 9, 2), tmp_path / "ABNB.US", FakeSecClient(responses)
    )
    drifted = dict(responses)
    drifted[sec_filings.submissions_url("0001559720")] += b" "

    with pytest.raises(sec_filings.SecEvidenceError, match="remote evidence drift"):
        sec_filings.revalidate_filing_manifest(path, FakeSecClient(drifted))


def test_revalidate_manifest_detects_local_drift(tmp_path: Path) -> None:
    responses = _manifest_responses()
    path = sec_filings.build_filing_manifest(
        "ABNB.US", date(2026, 9, 2), tmp_path / "ABNB.US", FakeSecClient(responses)
    )
    manifest = json.loads(path.read_text())
    Path(manifest["requests"][0]["artifact_path"]).write_bytes(b"changed")

    with pytest.raises(sec_filings.SecEvidenceError, match="local evidence drift"):
        sec_filings.revalidate_filing_manifest(path, FakeSecClient(responses))


def test_revalidate_manifest_succeeds_without_mutation(tmp_path: Path) -> None:
    responses = _manifest_responses()
    path = sec_filings.build_filing_manifest(
        "ABNB.US", date(2026, 9, 2), tmp_path / "ABNB.US", FakeSecClient(responses)
    )
    before = path.read_bytes()

    result = sec_filings.revalidate_filing_manifest(path, FakeSecClient(responses))

    assert "revalidated" in result
    assert sec_filings.sha256_bytes(before) in result
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("manifest", "message"),
    (
        ({}, "unsupported"),
        ({"schema_version": "us-sec-filing-manifest/1.0", "requests": []}, "request evidence"),
        (
            {"schema_version": "us-sec-filing-manifest/1.0", "requests": ["bad"]},
            "request is invalid",
        ),
        (
            {"schema_version": "us-sec-filing-manifest/1.0", "requests": [{}]},
            "request is incomplete",
        ),
    ),
)
def test_revalidate_manifest_rejects_invalid_schema(
    tmp_path: Path, manifest: dict[str, object], message: str
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))

    with pytest.raises(sec_filings.SecEvidenceError, match=message):
        sec_filings.revalidate_filing_manifest(path, FakeSecClient({}))


def test_revalidate_manifest_rejects_unreadable_artifact(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "us-sec-filing-manifest/1.0",
                "requests": [
                    {
                        "url": "https://www.sec.gov/example",
                        "sha256": "0" * 64,
                        "artifact_path": str(tmp_path / "missing"),
                    }
                ],
            }
        )
    )

    with pytest.raises(sec_filings.SecEvidenceError, match="cannot read"):
        sec_filings.revalidate_filing_manifest(path, FakeSecClient({}))


def test_revalidate_manifest_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("not json")

    with pytest.raises(sec_filings.SecEvidenceError, match="cannot read"):
        sec_filings.revalidate_filing_manifest(path, FakeSecClient({}))
