"""SEC filing identity, catalog, selection, and evidence persistence."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
SUPPORTED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
_US_TICKER = re.compile(r"[A-Z][A-Z0-9-]{0,9}")
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
_DOCUMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class SecEvidenceError(ValueError):
    """Raised when SEC evidence is incomplete, conflicting, or invalid."""


@dataclass(frozen=True)
class SecIdentity:
    requested_ticker: str
    canonical_ticker: str
    cik: str
    issuer_name: str
    sec_ticker: str
    exchange: str


@dataclass(frozen=True)
class SecFiling:
    cik: str
    accession: str
    filing_date: date
    report_period: date
    acceptance_datetime: datetime
    form: str
    primary_document: str
    amends_accession: str | None = None

    @property
    def family(self) -> str:
        return self.form.removesuffix("/A")

    @property
    def is_amendment(self) -> bool:
        return self.form.endswith("/A")


@dataclass(frozen=True)
class FilingSelection:
    latest_report: SecFiling
    audited_baseline: SecFiling
    comparable_quarters: tuple[SecFiling, ...]


@dataclass(frozen=True)
class SecEarningsFiling:
    cik: str
    accession: str
    filing_date: date
    report_period: date | None
    acceptance_datetime: datetime
    primary_document: str


class SecTransport(Protocol):
    def get(self, url: str) -> bytes: ...


class SecClient:
    """Small SEC HTTP client with an explicit identity and bounded retries."""

    def __init__(
        self,
        user_agent: str,
        min_interval: float = 0.1,
        timeout: float = 30.0,
    ) -> None:
        if not user_agent.strip() or not ("@" in user_agent or "http" in user_agent.lower()):
            raise ValueError("SEC User-Agent must identify the application and contact route")
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_request = 0.0

    def get(self, url: str) -> bytes:
        for attempt in range(3):
            delay = self.min_interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                    "Accept": "application/json,text/html,application/xhtml+xml,*/*",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    self._last_request = time.monotonic()
                    body = response.read()
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        return gzip.decompress(body)
                    return body
            except urllib.error.HTTPError as exc:
                self._last_request = time.monotonic()
                if exc.code not in {403, 429, 500, 502, 503, 504} or attempt == 2:
                    raise
                time.sleep(2**attempt)
            except urllib.error.URLError:
                self._last_request = time.monotonic()
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")


def parse_us_ticker(ticker: str) -> str:
    """Normalize a research-only US ticker without creating a market symbol."""
    value = ticker.strip().upper()
    if not value.endswith(".US"):
        raise ValueError(f"Bad US research ticker {ticker!r}: expected <SYMBOL>.US")
    symbol = value[:-3]
    if not _US_TICKER.fullmatch(symbol) or symbol.endswith("-"):
        raise ValueError(f"Bad US research ticker {ticker!r}: expected <SYMBOL>.US")
    return f"{symbol}.US"


def _load_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecEvidenceError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SecEvidenceError(f"{label} must be a JSON object")
    return value


def resolve_sec_identity(ticker: str, payload: bytes) -> SecIdentity:
    canonical = parse_us_ticker(ticker)
    symbol = canonical[:-3]
    data = _load_object(payload, "SEC company ticker mapping")
    matches: list[dict[str, object]] = []
    for raw in data.values():
        if isinstance(raw, dict) and str(raw.get("ticker", "")).upper() == symbol:
            matches.append(raw)
    if not matches:
        raise SecEvidenceError(f"SEC ticker mapping does not contain {symbol}")
    if len(matches) != 1:
        raise SecEvidenceError(f"duplicate SEC ticker rows for {symbol}")
    row = matches[0]
    try:
        cik_number = int(row["cik_str"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SecEvidenceError("SEC ticker row has an invalid CIK") from exc
    issuer_name = str(row.get("title", "")).strip()
    if not issuer_name or not 0 < cik_number < 10**10:
        raise SecEvidenceError("SEC ticker row has an invalid issuer identity")
    return SecIdentity(
        requested_ticker=ticker,
        canonical_ticker=canonical,
        cik=f"{cik_number:010d}",
        issuer_name=issuer_name,
        sec_ticker=symbol,
        exchange=str(row.get("exchange", "")).strip(),
    )


def archive_url(cik: str, accession: str, document: str) -> str:
    if not re.fullmatch(r"\d{10}", cik):
        raise ValueError("CIK must contain ten digits")
    if not _ACCESSION.fullmatch(accession):
        raise ValueError("SEC accession must match ##########-##-######")
    if not _DOCUMENT.fullmatch(document) or ".." in document:
        raise ValueError("SEC document must be a safe archive basename")
    return f"{SEC_ARCHIVES_BASE_URL}/{int(cik)}/{accession.replace('-', '')}/{document}"


def filing_index_url(cik: str, accession: str) -> str:
    return archive_url(cik, accession, "index.json")


def submissions_url(cik: str) -> str:
    if not re.fullmatch(r"\d{10}", cik):
        raise ValueError("CIK must contain ten digits")
    return f"{SEC_SUBMISSIONS_BASE_URL}/CIK{cik}.json"


def historical_submissions_url(name: str) -> str:
    if not re.fullmatch(r"CIK\d{10}-submissions-\d{3}\.json", name):
        raise ValueError("historical submissions filename is invalid")
    return f"{SEC_SUBMISSIONS_BASE_URL}/{name}"


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def persist_artifact(root: Path, body: bytes, *, suffix: str) -> Path:
    digest = sha256_bytes(body)
    artifact_dir = root.resolve() / "artifacts" / digest[:2]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{digest}{suffix}"
    if path.exists():
        if path.read_bytes() != body:
            raise SecEvidenceError(f"content-addressed artifact differs at {path}")
        return path
    fd, temporary_name = tempfile.mkstemp(prefix=f".{digest}.", dir=artifact_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _parse_acceptance(value: str) -> datetime:
    cleaned = value.strip()
    for pattern in ("%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(cleaned, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise SecEvidenceError(f"invalid SEC acceptanceDateTime {value!r}")


def _parse_filing_rows(raw: object, cik: str, label: str) -> list[SecFiling]:
    if not isinstance(raw, dict):
        raise SecEvidenceError(f"{label} filing columns must be an object")
    names = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
    )
    columns: dict[str, list[object]] = {}
    for name in names:
        value = raw.get(name)
        if not isinstance(value, list):
            raise SecEvidenceError(f"{label} filing column {name} must be a list")
        columns[name] = value
    lengths = {len(value) for value in columns.values()}
    if len(lengths) != 1:
        raise SecEvidenceError(f"{label} SEC filing columns have unequal lengths")

    filings: list[SecFiling] = []
    for index in range(next(iter(lengths), 0)):
        form = str(columns["form"][index])
        if form not in SUPPORTED_FORMS:
            continue
        accession = str(columns["accessionNumber"][index])
        document = str(columns["primaryDocument"][index])
        archive_url(cik, accession, document)
        try:
            filing_date = date.fromisoformat(str(columns["filingDate"][index]))
            report_period = date.fromisoformat(str(columns["reportDate"][index]))
        except ValueError as exc:
            raise SecEvidenceError(f"{label} contains an invalid filing date") from exc
        filings.append(
            SecFiling(
                cik=cik,
                accession=accession,
                filing_date=filing_date,
                report_period=report_period,
                acceptance_datetime=_parse_acceptance(str(columns["acceptanceDateTime"][index])),
                form=form,
                primary_document=document,
            )
        )
    return filings


def _parse_eight_k_rows(raw: object, cik: str, label: str) -> list[SecEarningsFiling]:
    if not isinstance(raw, dict):
        raise SecEvidenceError(f"{label} filing columns must be an object")
    names = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
    )
    columns: dict[str, list[object]] = {}
    for name in names:
        value = raw.get(name)
        if not isinstance(value, list):
            raise SecEvidenceError(f"{label} filing column {name} must be a list")
        columns[name] = value
    lengths = {len(value) for value in columns.values()}
    if len(lengths) != 1:
        raise SecEvidenceError(f"{label} SEC filing columns have unequal lengths")

    filings: list[SecEarningsFiling] = []
    for index in range(next(iter(lengths), 0)):
        if str(columns["form"][index]) != "8-K":
            continue
        accession = str(columns["accessionNumber"][index])
        document = str(columns["primaryDocument"][index])
        archive_url(cik, accession, document)
        try:
            filing_date = date.fromisoformat(str(columns["filingDate"][index]))
            raw_report_period = str(columns["reportDate"][index]).strip()
            report_period = date.fromisoformat(raw_report_period) if raw_report_period else None
        except ValueError as exc:
            raise SecEvidenceError(f"{label} contains an invalid 8-K date") from exc
        filings.append(
            SecEarningsFiling(
                cik=cik,
                accession=accession,
                filing_date=filing_date,
                report_period=report_period,
                acceptance_datetime=_parse_acceptance(str(columns["acceptanceDateTime"][index])),
                primary_document=document,
            )
        )
    return filings


def parse_submission_catalog(
    current: bytes, historical: Mapping[str, bytes]
) -> tuple[SecFiling, ...]:
    payload = _load_object(current, "SEC submissions response")
    try:
        cik = f"{int(payload['cik']):010d}"
        filings = payload["filings"]
    except (KeyError, TypeError, ValueError) as exc:
        raise SecEvidenceError("SEC submissions response lacks issuer identity") from exc
    if not isinstance(filings, dict):
        raise SecEvidenceError("SEC submissions filings must be an object")
    catalog = _parse_filing_rows(filings.get("recent"), cik, "recent")
    file_rows = filings.get("files", [])
    if not isinstance(file_rows, list):
        raise SecEvidenceError("SEC historical submissions list must be an array")
    for entry in file_rows:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise SecEvidenceError("SEC historical submissions entry is invalid")
        name = entry["name"]
        if name not in historical:
            raise SecEvidenceError(f"missing historical submissions segment {name}")
        segment = _load_object(historical[name], f"historical submissions {name}")
        catalog.extend(_parse_filing_rows(segment, cik, name))

    by_accession: dict[str, SecFiling] = {}
    for filing in catalog:
        existing = by_accession.get(filing.accession)
        if existing is not None and existing != filing:
            raise SecEvidenceError(
                f"conflicting duplicate accession {filing.accession} in SEC catalog"
            )
        by_accession[filing.accession] = filing
    return tuple(
        sorted(
            by_accession.values(),
            key=lambda item: (item.acceptance_datetime, item.accession),
            reverse=True,
        )
    )


def _effective_filings(catalog: Sequence[SecFiling], as_of: date) -> tuple[SecFiling, ...]:
    eligible = [item for item in catalog if item.filing_date <= as_of]
    grouped: dict[tuple[str, date], list[SecFiling]] = {}
    for filing in eligible:
        grouped.setdefault((filing.family, filing.report_period), []).append(filing)

    effective: list[SecFiling] = []
    for group in grouped.values():
        ordered = sorted(group, key=lambda item: (item.acceptance_datetime, item.accession))
        bases = [item for item in ordered if not item.is_amendment]
        amendments = [item for item in ordered if item.is_amendment]
        if amendments and not bases:
            raise SecEvidenceError(
                f"unresolved amendment {amendments[-1].accession}: base filing is absent"
            )
        selected = ordered[-1]
        if selected.is_amendment:
            prior = [
                item for item in ordered if item.acceptance_datetime < selected.acceptance_datetime
            ]
            if not prior:
                raise SecEvidenceError(f"unresolved amendment {selected.accession}")
            selected = replace(selected, amends_accession=prior[-1].accession)
        effective.append(selected)
    return tuple(
        sorted(
            effective,
            key=lambda item: (item.acceptance_datetime, item.accession),
            reverse=True,
        )
    )


def select_filing_set(catalog: Sequence[SecFiling], as_of: date) -> FilingSelection:
    effective = _effective_filings(catalog, as_of)
    if not effective:
        raise SecEvidenceError(f"no qualifying SEC filing is available on or before {as_of}")
    latest = effective[0]
    annuals = [
        item
        for item in effective
        if item.family == "10-K" and item.acceptance_datetime <= latest.acceptance_datetime
    ]
    if not annuals:
        raise SecEvidenceError("latest report has no preceding audited 10-K baseline")
    audited_baseline = annuals[0]
    comparable_quarters = tuple(
        item for item in effective if item.family == "10-Q" and item.accession != latest.accession
    )[:4]
    return FilingSelection(latest, audited_baseline, comparable_quarters)


def _artifact_suffix(url: str) -> str:
    name = url.rsplit("/", 1)[-1].lower()
    if name.endswith(".json"):
        return ".json"
    if name.endswith((".htm", ".html")):
        return ".html"
    return ".bin"


def _fetch_record(
    client: SecTransport,
    url: str,
    root: Path,
    purpose: str,
    requests: list[dict[str, object]],
) -> bytes:
    body = client.get(url)
    path = persist_artifact(root, body, suffix=_artifact_suffix(url))
    requests.append(
        {
            "purpose": purpose,
            "url": url,
            "artifact_path": str(path),
            "sha256": sha256_bytes(body),
            "size": len(body),
        }
    )
    return body


def _historical_names(submissions: bytes) -> tuple[str, ...]:
    payload = _load_object(submissions, "SEC submissions response")
    try:
        rows = payload["filings"]["files"]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise SecEvidenceError("SEC submissions response lacks historical file inventory") from exc
    if not isinstance(rows, list):
        raise SecEvidenceError("SEC historical submissions list must be an array")
    names: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise SecEvidenceError("SEC historical submissions entry is invalid")
        name = row["name"]
        historical_submissions_url(name)
        names.append(name)
    return tuple(names)


def _index_documents(payload: bytes) -> set[str]:
    return {str(item["name"]) for item in _index_items(payload)}


def _index_items(payload: bytes) -> tuple[dict[str, object], ...]:
    data = _load_object(payload, "SEC filing directory index")
    try:
        items = data["directory"]["item"]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise SecEvidenceError("SEC filing directory index lacks items") from exc
    if not isinstance(items, list):
        raise SecEvidenceError("SEC filing directory items must be an array")
    normalized: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise SecEvidenceError("SEC filing directory item is invalid")
        normalized.append(item)
    return tuple(normalized)


def _same_cycle_eight_ks(
    submissions: bytes,
    historical: Mapping[str, bytes],
    latest_report: SecFiling,
    as_of: date,
) -> tuple[SecEarningsFiling, ...]:
    payload = _load_object(submissions, "SEC submissions response")
    try:
        cik = f"{int(payload['cik']):010d}"
        filings = payload["filings"]
        recent = filings["recent"]  # type: ignore[index]
    except (KeyError, TypeError, ValueError) as exc:
        raise SecEvidenceError("SEC submissions response lacks issuer identity") from exc
    candidates = _parse_eight_k_rows(recent, cik, "recent")
    for name, body in historical.items():
        candidates.extend(
            _parse_eight_k_rows(_load_object(body, f"historical submissions {name}"), cik, name)
        )
    return tuple(
        sorted(
            (
                filing
                for filing in candidates
                if filing.filing_date == latest_report.filing_date and filing.filing_date <= as_of
            ),
            key=lambda filing: (filing.acceptance_datetime, filing.accession),
        )
    )


def _earnings_exhibit_items(index_body: bytes) -> tuple[tuple[str, str], ...]:
    exhibits: list[tuple[str, str]] = []
    for item in _index_items(index_body):
        exhibit_type = str(item.get("type", "")).strip().upper()
        document = str(item["name"])
        if not exhibit_type.startswith("EX-99"):
            continue
        if not _DOCUMENT.fullmatch(document) or ".." in document:
            raise SecEvidenceError(f"SEC exhibit has an unsafe document name {document!r}")
        if not document.lower().endswith((".htm", ".html", ".pdf")):
            continue
        exhibits.append((exhibit_type, document))
    return tuple(sorted(exhibits))


def _assert_document_cik(body: bytes, cik: str, accession: str) -> None:
    text = body.decode("utf-8", errors="replace")
    matches = re.findall(
        r"EntityCentralIndexKey[^>]*>\s*(?:<[^>]+>\s*)*0*(\d{1,10})\s*<",
        text,
        flags=re.IGNORECASE,
    )
    if not matches or any(f"{int(value):010d}" != cik for value in matches):
        raise SecEvidenceError(f"CIK identity mismatch in filing {accession}")


def _filing_dict(filing: SecFiling) -> dict[str, object]:
    value = asdict(filing)
    value["filing_date"] = filing.filing_date.isoformat()
    value["report_period"] = filing.report_period.isoformat()
    value["acceptance_datetime"] = filing.acceptance_datetime.isoformat()
    value["family"] = filing.family
    value["is_amendment"] = filing.is_amendment
    value["official_document_url"] = archive_url(
        filing.cik, filing.accession, filing.primary_document
    )
    value["directory_index_url"] = filing_index_url(filing.cik, filing.accession)
    return value


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_filing_manifest(
    ticker: str,
    as_of: date,
    out_dir: Path,
    client: SecTransport,
) -> Path:
    """Build a complete immutable SEC evidence bundle for one latest-report run."""
    canonical = parse_us_ticker(ticker)
    root = out_dir.resolve() / "sec"
    requests: list[dict[str, object]] = []
    ticker_body = _fetch_record(client, SEC_TICKERS_URL, root, "ticker_mapping", requests)
    identity = resolve_sec_identity(canonical, ticker_body)
    submissions_body = _fetch_record(
        client,
        submissions_url(identity.cik),
        root,
        "current_submissions",
        requests,
    )
    historical: dict[str, bytes] = {}
    for name in _historical_names(submissions_body):
        historical[name] = _fetch_record(
            client,
            historical_submissions_url(name),
            root,
            f"historical_submissions:{name}",
            requests,
        )
    catalog = parse_submission_catalog(submissions_body, historical)
    if any(item.cik != identity.cik for item in catalog):
        raise SecEvidenceError("ticker mapping and submissions CIK identity mismatch")
    selection = select_filing_set(catalog, as_of)

    role_by_accession: dict[str, str] = {
        selection.latest_report.accession: "latest_report",
        selection.audited_baseline.accession: "audited_baseline",
    }
    for filing in selection.comparable_quarters:
        role_by_accession.setdefault(filing.accession, "comparable_quarter")

    selected_by_accession = {
        filing.accession: filing
        for filing in (
            selection.latest_report,
            selection.audited_baseline,
            *selection.comparable_quarters,
        )
    }
    filing_evidence: dict[str, dict[str, object]] = {}
    for accession, filing in selected_by_accession.items():
        index_body = _fetch_record(
            client,
            filing_index_url(identity.cik, accession),
            root,
            f"filing_index:{accession}",
            requests,
        )
        if filing.primary_document not in _index_documents(index_body):
            raise SecEvidenceError(
                f"primary document {filing.primary_document} is absent from index {accession}"
            )
        document_body = _fetch_record(
            client,
            archive_url(identity.cik, accession, filing.primary_document),
            root,
            f"filing_document:{accession}",
            requests,
        )
        _assert_document_cik(document_body, identity.cik, accession)
        filing_evidence[accession] = {
            **_filing_dict(filing),
            "role": role_by_accession[accession],
            "index_sha256": sha256_bytes(index_body),
            "document_sha256": sha256_bytes(document_body),
        }

    earnings_exhibits: list[dict[str, object]] = []
    for filing in _same_cycle_eight_ks(
        submissions_body, historical, selection.latest_report, as_of
    ):
        index_body = _fetch_record(
            client,
            filing_index_url(identity.cik, filing.accession),
            root,
            f"earnings_8k_index:{filing.accession}",
            requests,
        )
        documents = _index_documents(index_body)
        if filing.primary_document not in documents:
            raise SecEvidenceError(
                f"primary document {filing.primary_document} is absent from "
                f"8-K index {filing.accession}"
            )
        filing_body = _fetch_record(
            client,
            archive_url(identity.cik, filing.accession, filing.primary_document),
            root,
            f"earnings_8k_document:{filing.accession}",
            requests,
        )
        _assert_document_cik(filing_body, identity.cik, filing.accession)
        for exhibit_type, exhibit_document in _earnings_exhibit_items(index_body):
            exhibit_url = archive_url(identity.cik, filing.accession, exhibit_document)
            exhibit_body = _fetch_record(
                client,
                exhibit_url,
                root,
                f"earnings_exhibit:{filing.accession}:{exhibit_type}",
                requests,
            )
            earnings_exhibits.append(
                {
                    "accession": filing.accession,
                    "acceptance_datetime": filing.acceptance_datetime.isoformat(),
                    "exhibit_document": exhibit_document,
                    "exhibit_sha256": sha256_bytes(exhibit_body),
                    "exhibit_type": exhibit_type,
                    "filing_date": filing.filing_date.isoformat(),
                    "filing_document_sha256": sha256_bytes(filing_body),
                    "form": "8-K",
                    "index_sha256": sha256_bytes(index_body),
                    "official_exhibit_url": exhibit_url,
                    "official_filing_url": archive_url(
                        identity.cik, filing.accession, filing.primary_document
                    ),
                    "primary_document": filing.primary_document,
                    "report_period": (
                        filing.report_period or selection.latest_report.report_period
                    ).isoformat(),
                }
            )

    manifest = {
        "schema_version": "us-sec-filing-manifest/1.0",
        "jurisdiction": "US",
        "as_of": as_of.isoformat(),
        "identity": asdict(identity),
        "requests": requests,
        "catalog": [_filing_dict(filing) for filing in catalog],
        "selection": {
            "latest_report": selection.latest_report.accession,
            "audited_baseline": selection.audited_baseline.accession,
            "comparable_quarters": [filing.accession for filing in selection.comparable_quarters],
        },
        "filings": filing_evidence,
        "earnings_exhibits": earnings_exhibits,
        "limitations": (
            []
            if earnings_exhibits
            else ["no same-cycle 8-K EX-99 earnings exhibit was found in the SEC catalog"]
        ),
    }
    manifest_path = root / f"filing-manifest-{as_of.isoformat()}.json"
    _write_json_atomic(manifest_path, manifest)
    return manifest_path


def revalidate_filing_manifest(path: Path, client: SecTransport) -> str:
    try:
        body = path.read_bytes()
        manifest = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecEvidenceError(f"cannot read SEC filing manifest {path}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != (
        "us-sec-filing-manifest/1.0"
    ):
        raise SecEvidenceError("unsupported SEC filing manifest schema")
    requests = manifest.get("requests")
    if not isinstance(requests, list) or not requests:
        raise SecEvidenceError("SEC filing manifest lacks request evidence")
    for request in requests:
        if not isinstance(request, dict):
            raise SecEvidenceError("SEC filing manifest request is invalid")
        try:
            url = str(request["url"])
            expected = str(request["sha256"])
            artifact_path = Path(str(request["artifact_path"]))
        except KeyError as exc:
            raise SecEvidenceError("SEC filing manifest request is incomplete") from exc
        try:
            local = artifact_path.read_bytes()
        except OSError as exc:
            raise SecEvidenceError(f"local evidence drift: cannot read {artifact_path}") from exc
        if sha256_bytes(local) != expected:
            raise SecEvidenceError(f"local evidence drift at {artifact_path}")
        remote = client.get(url)
        if sha256_bytes(remote) != expected:
            raise SecEvidenceError(f"remote evidence drift at {url}")
    return f"revalidated {path} sha256={sha256_bytes(body)}"
