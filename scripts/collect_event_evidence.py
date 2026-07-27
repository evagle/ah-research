"""Collect official regulatory evidence and produce an event-manifest bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

try:
    from scripts import build_event_manifest
except ModuleNotFoundError:  # Direct execution via `python scripts/...`.
    import build_event_manifest  # type: ignore[no-redef]

ResponseFetcher = Callable[
    [str, str, str, dict[str, object], object],
    list[bytes],
]
DocumentFetcher = Callable[[str], bytes]
QUERY_PLAN_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / ".claude/skills/read-filing/references/event-query-plan.schema.json"
)


class CollectionError(Exception):
    """Raised when official evidence cannot be collected safely."""


def _write_immutable(path: Path, body: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == body:
            return path.resolve()
        content_hash = hashlib.sha256(body).hexdigest()[:16]
        path = path.with_name(f"{path.stem}-{content_hash}{path.suffix}")
        if path.exists():
            if path.read_bytes() == body:
                return path.resolve()
            raise CollectionError(f"content-addressed evidence path has different bytes: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(body)
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            if path.read_bytes() == body:
                return path.resolve()
            raise CollectionError(f"evidence path was concurrently replaced: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path.resolve()


def _read_plan(plan_path: Path) -> dict[str, object]:
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectionError(f"cannot read query plan: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise CollectionError("query plan must use schema_version 1")
    if "listing_codes" in plan or "listing_dates" in plan:
        raise CollectionError(
            "listing_codes and listing_dates must come from the official listing profile response"
        )
    try:
        schema = json.loads(QUERY_PLAN_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectionError(f"cannot read query-plan schema: {exc}") from exc
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(plan),
        key=lambda error: tuple(map(str, error.absolute_path)),
    )
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.absolute_path)) or "<root>"
        raise CollectionError(f"query plan violates schema at {location}: {error.message}")
    for field in (
        "ticker",
        "exchange",
        "AS_OF",
        "query_issuer_code",
        "issuer_type",
        "listing_profile",
        "subject_roster",
        "categories",
    ):
        if field not in plan:
            raise CollectionError(f"query plan is missing {field}")
    return plan


def _fetch_one(
    row: dict[str, object],
    response_fetcher: ResponseFetcher,
) -> bytes:
    source_url = str(row.get("source_url") or "")
    http_method = str(row.get("http_method") or "")
    request_encoding = str(row.get("request_encoding") or "")
    query_params = row.get("query_params")
    response_schema = str(row.get("response_schema") or "")
    if (
        not source_url
        or http_method not in {"GET", "POST"}
        or request_encoding not in {"query", "json", "form"}
        or not isinstance(query_params, dict)
        or not response_schema
    ):
        raise CollectionError("profile or roster query contract is incomplete")
    bodies = response_fetcher(
        source_url,
        http_method,
        request_encoding,
        query_params,
        {
            "response_schema": response_schema,
            "response_adapter": row.get("response_adapter", {}),
            "request_headers": row.get("request_headers", {}),
        },
    )
    if len(bodies) != 1:
        raise CollectionError("profile or roster query must return exactly one response")
    return bodies[0]


def _adapt_fields(
    payload: dict[str, object],
    adapter: object,
    required_fields: set[str],
    context: str,
) -> dict[str, object]:
    if not isinstance(adapter, dict):
        raise CollectionError(f"{context} response_adapter must be an object")
    raw_paths = adapter.get("field_paths")
    if not isinstance(raw_paths, dict) or set(map(str, raw_paths)) != required_fields:
        raise CollectionError(
            f"{context} field_paths must define exactly {sorted(required_fields)}"
        )
    raw_value_maps = adapter.get("value_maps", {})
    if not isinstance(raw_value_maps, dict):
        raise CollectionError(f"{context} value_maps must be an object")
    normalized: dict[str, object] = {}
    for field in required_fields:
        try:
            value = build_event_manifest._json_path(
                payload,
                str(raw_paths[field]),
                f"{context}.{field}",
            )
        except build_event_manifest.ManifestError as exc:
            raise CollectionError(str(exc)) from exc
        value_map = raw_value_maps.get(field)
        if value_map is not None:
            if not isinstance(value_map, dict) or str(value) not in value_map:
                raise CollectionError(f"{context}.{field} has no deterministic value mapping")
            value = value_map[str(value)]
        normalized[field] = value
    return normalized


def _normalize_plan_identity(
    listing_plan: dict[str, object],
    listing_body: bytes,
    roster_plan: dict[str, object],
    roster_body: bytes,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    try:
        listing_payload = json.loads(listing_body.decode("utf-8"))
        roster_payload = json.loads(roster_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CollectionError(f"profile or roster response is invalid JSON: {exc}") from exc
    if not isinstance(listing_payload, dict) or not isinstance(roster_payload, dict):
        raise CollectionError("profile and roster responses must be JSON objects")

    listing_schema = str(listing_plan.get("response_schema") or "")
    if listing_schema == "canonical_listing_profile_v1":
        listing_profile = {
            "issuer_code": listing_payload.get("issuer_code"),
            "listing_codes": listing_payload.get("listing_codes"),
            "listing_date": listing_payload.get("listing_date"),
            "listing_dates": listing_payload.get("listing_dates"),
            "listing_status": listing_payload.get("listing_status", "listed"),
            "delisting_date": listing_payload.get("delisting_date"),
            "listing_statuses": listing_payload.get("listing_statuses"),
            "delisting_dates": listing_payload.get("delisting_dates"),
            "official_result_total": listing_payload.get("official_result_total"),
        }
    elif listing_schema == "native_json_listing_profile_v1":
        listing_profile = _adapt_fields(
            listing_payload,
            listing_plan.get("response_adapter"),
            build_event_manifest.LISTING_PROFILE_ADAPTER_FIELDS,
            "listing_profile",
        )
    else:
        raise CollectionError("listing profile response_schema is unsupported")

    roster_schema = str(roster_plan.get("response_schema") or "")
    if roster_schema == "canonical_subject_roster_v1":
        subjects = roster_payload.get("subjects")
        if not isinstance(subjects, list):
            raise CollectionError("official roster response lacks subjects")
    elif roster_schema == "native_json_roster_v1":
        declared_subjects = roster_plan.get("declared_subjects")
        try:
            subjects, _ = build_event_manifest._native_roster_subjects(
                roster_payload,
                roster_plan.get("response_adapter", {}),
                declared_subjects,
            )
        except build_event_manifest.ManifestError as exc:
            raise CollectionError(str(exc)) from exc
    else:
        raise CollectionError("subject roster response_schema is unsupported")
    listing_codes = listing_profile.get("listing_codes")
    if not isinstance(listing_codes, dict):
        raise CollectionError("official profile lacks listing_codes")
    jurisdictions = set(map(str, listing_codes))
    listing_statuses = listing_profile.get("listing_statuses")
    delisting_dates = listing_profile.get("delisting_dates")
    if listing_statuses is None:
        listing_statuses = {
            jurisdiction: listing_profile.get("listing_status", "listed")
            for jurisdiction in jurisdictions
        }
    if delisting_dates is None:
        delisting_dates = {
            jurisdiction: listing_profile.get("delisting_date") for jurisdiction in jurisdictions
        }
    if (
        not isinstance(listing_statuses, dict)
        or not isinstance(delisting_dates, dict)
        or set(map(str, listing_statuses)) != jurisdictions
        or set(map(str, delisting_dates)) != jurisdictions
    ):
        raise CollectionError("listing statuses and delisting dates must cover every jurisdiction")
    listing_profile["listing_statuses"] = listing_statuses
    listing_profile["delisting_dates"] = delisting_dates
    return listing_profile, subjects


def _default_response_fetcher(
    url: str,
    method: str,
    encoding: str,
    params: dict[str, object],
    contract: object,
) -> list[bytes]:
    response_schema = (
        str(contract.get("response_schema") or "") if isinstance(contract, dict) else str(contract)
    )
    request_headers = contract.get("request_headers", {}) if isinstance(contract, dict) else {}
    if response_schema in {
        "canonical_listing_profile_v1",
        "native_json_listing_profile_v1",
        "canonical_subject_roster_v1",
        "native_json_roster_v1",
    }:
        return [
            build_event_manifest._fetch_official_single(
                url,
                method,
                encoding,
                params,
                request_headers,
            )
        ]
    return build_event_manifest._fetch_official_event_pages(
        url,
        method,
        encoding,
        params,
        contract,
    )


def collect_evidence(
    plan_path: Path,
    bundle_path: Path,
    evidence_dir: Path,
    *,
    response_fetcher: ResponseFetcher = _default_response_fetcher,
    document_fetcher: DocumentFetcher = build_event_manifest._fetch_official_document,
) -> Path:
    plan = _read_plan(plan_path)
    listing_plan = plan["listing_profile"]
    roster_plan = plan["subject_roster"]
    categories_plan = plan["categories"]
    if (
        not isinstance(listing_plan, dict)
        or not isinstance(roster_plan, dict)
        or not isinstance(categories_plan, list)
    ):
        raise CollectionError("query plan sections have invalid types")

    listing_body = _fetch_one(listing_plan, response_fetcher)
    roster_body = _fetch_one(roster_plan, response_fetcher)
    listing_file = _write_immutable(
        evidence_dir / "listing-profile.json",
        listing_body,
    )
    roster_file = _write_immutable(
        evidence_dir / "subject-roster.json",
        roster_body,
    )
    listing_profile, subjects = _normalize_plan_identity(
        listing_plan,
        listing_body,
        roster_plan,
        roster_body,
    )
    listing_date = listing_profile.get("listing_date")
    listing_codes = listing_profile.get("listing_codes")
    listing_dates = listing_profile.get("listing_dates")
    if (
        not isinstance(listing_date, str)
        or not isinstance(listing_codes, dict)
        or not isinstance(listing_dates, dict)
    ):
        raise CollectionError("official profile or roster response lacks required fields")

    bundle_categories: list[dict[str, object]] = []
    for index, raw_row in enumerate(categories_plan):
        if not isinstance(raw_row, dict):
            raise CollectionError("each category source must be an object")
        row = dict(raw_row)
        query_url = str(row.get("query_url") or "")
        query_params = row.get("query_params")
        response_schema = str(row.get("response_schema") or "")
        response_adapter = row.get("response_adapter", {})
        if not query_url or not isinstance(query_params, dict) or not response_schema:
            raise CollectionError("category query contract is incomplete")
        bodies = response_fetcher(
            query_url,
            str(row.get("http_method") or ""),
            str(row.get("request_encoding") or ""),
            query_params,
            {
                "response_schema": response_schema,
                "response_adapter": response_adapter,
                "request_headers": row.get("request_headers", {}),
            },
        )
        if not bodies:
            raise CollectionError("category query returned no response pages")
        response_files = [
            str(
                _write_immutable(
                    evidence_dir
                    / (
                        f"{index:02d}-{row.get('category')}-"
                        f"{row.get('source_id')}-page-{page_no}.json"
                    ),
                    body,
                )
            )
            for page_no, body in enumerate(bodies, start=1)
        ]
        row["response_files"] = response_files
        row["document_files"] = {}
        events, *_ = build_event_manifest._load_response_pages(
            row,
            str(row.get("category") or ""),
            query_params,
        )
        document_files: dict[str, str] = {}
        for event in events:
            record_id = str(event.get("record_id") or "")
            document_url = str(event.get("document_url") or "")
            if not record_id or not document_url:
                raise CollectionError("event response lacks record_id or document_url")
            digest = hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:12]
            document_path = _write_immutable(
                evidence_dir / "documents" / f"{digest}.bin",
                document_fetcher(document_url),
            )
            document_files[record_id] = str(document_path)
        row["document_files"] = document_files
        bundle_categories.append(row)

    bundle = {
        "ticker": plan["ticker"],
        "exchange": plan["exchange"],
        "AS_OF": plan["AS_OF"],
        "query_issuer_code": plan["query_issuer_code"],
        "issuer_type": plan["issuer_type"],
        "listing_date": listing_date,
        "listing_codes": listing_codes,
        "listing_dates": listing_dates,
        "listing_status": listing_profile.get("listing_status"),
        "delisting_date": listing_profile.get("delisting_date"),
        "listing_statuses": listing_profile["listing_statuses"],
        "delisting_dates": listing_profile["delisting_dates"],
        "listing_profile": {
            **listing_plan,
            "source_file": str(listing_file),
        },
        "subject_roster": {
            **roster_plan,
            "source_file": str(roster_file),
        },
        "subjects": subjects,
        "categories": bundle_categories,
    }
    serialized = (json.dumps(bundle, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary_bundle = _write_immutable(
        bundle_path.with_name(f".{bundle_path.name}.validation"),
        serialized,
    )

    def fetch_identity(url: str, params: dict[str, object]) -> bytes:
        matches = [
            plan_row
            for plan_row in (listing_plan, roster_plan)
            if plan_row.get("source_url") == url and plan_row.get("query_params") == params
        ]
        if len(matches) != 1:
            raise CollectionError(
                "profile or roster live request does not match exactly one persisted query contract"
            )
        plan_row = matches[0]
        bodies = response_fetcher(
            url,
            str(plan_row.get("http_method") or ""),
            str(plan_row.get("request_encoding") or ""),
            params,
            {
                "response_schema": plan_row.get("response_schema"),
                "response_adapter": plan_row.get("response_adapter", {}),
                "request_headers": plan_row.get("request_headers", {}),
            },
        )
        if len(bodies) != 1:
            raise CollectionError("profile or roster live request must return exactly one response")
        return bodies[0]

    try:
        build_event_manifest.build_manifest(
            temporary_bundle,
            roster_fetcher=fetch_identity,
            event_fetcher=response_fetcher,
            document_fetcher=document_fetcher,
        )
        return _write_immutable(bundle_path, serialized)
    finally:
        temporary_bundle.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect official event evidence into a validated bundle."
    )
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--bundle-out", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        published = collect_evidence(
            args.plan,
            args.bundle_out,
            args.evidence_dir,
        )
    except (CollectionError, build_event_manifest.ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(published)
    return 0


if __name__ == "__main__":
    sys.exit(main())
