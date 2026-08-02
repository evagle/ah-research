"""Resolve financial research runs and publish shared immutable artifacts."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
SHARED_ARTIFACT_KINDS = (
    "manifests",
    "evidence",
    "_extracted",
    "facts",
    "metrics",
    "citations",
    "analyses",
    "market",
)
RUN_LOCAL_DIRECTORIES = ("drafts", "manifests", "query", "logs", "tmp")
TICKER_PATTERN = re.compile(r"^(?:\d{6}\.(?:SH|SZ)|\d{5}\.HK)$")
SKILL_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
RESEARCH_LEDGER_FILENAME = "research-ledger.json"
CREATE_ONLY_SENTINEL = "create-only"

ResolutionAction = Literal["created", "resumed", "reused"]
SharedArtifactKind = Literal[
    "manifests",
    "evidence",
    "_extracted",
    "facts",
    "metrics",
    "citations",
    "analyses",
    "market",
]


class RunStoreError(Exception):
    """Raised when run state cannot be updated without losing data."""


@dataclass(frozen=True)
class Resolution:
    action: ResolutionAction
    run_id: str | None
    run_path: Path | None
    report_path: Path | None
    input_fingerprint: str
    parent_run_id: str | None


@dataclass(frozen=True)
class PromotedArtifact:
    artifact_id: str
    path: Path
    sha256: str


def _research_contract_api():
    scripts_dir = (
        Path(__file__).resolve().parents[1] / ".claude" / "skills" / "source-discovery" / "scripts"
    )
    if not scripts_dir.is_dir():
        raise RunStoreError(f"source-discovery scripts are missing: {scripts_dir}")
    scripts_path = str(scripts_dir)
    if scripts_path not in os.sys.path:
        os.sys.path.insert(0, scripts_path)
    try:
        from evidence_gate import request_scope_fingerprint
        from research_contracts import validate_payload
    except ImportError as exc:
        raise RunStoreError(f"source-discovery contracts are unavailable: {exc}") from exc
    return validate_payload, request_scope_fingerprint


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    except (TypeError, ValueError) as exc:
        raise RunStoreError(f"value is not JSON serializable: {exc}") from exc


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def artifact_id(
    artifact_kind: str,
    schema_version: str,
    input_artifact_ids: Sequence[str],
    parameters: Mapping[str, Any],
) -> str:
    payload = {
        "artifact_kind": artifact_kind,
        "schema_version": schema_version,
        "input_artifact_ids": sorted(input_artifact_ids),
        "parameters": parameters,
    }
    return _sha256(_canonical_json(payload))


def _validate_identity(ticker: str, skill_name: str | None = None) -> None:
    if not TICKER_PATTERN.fullmatch(ticker):
        raise RunStoreError(f"ticker is not canonical: {ticker}")
    if skill_name is not None and not SKILL_PATTERN.fullmatch(skill_name):
        raise RunStoreError(f"skill name is invalid: {skill_name}")


def _ticker_root(root: Path, ticker: str) -> Path:
    _validate_identity(ticker)
    return root.resolve() / ticker


def _initialize_layout(root: Path, ticker: str) -> tuple[Path, Path]:
    ticker_root = _ticker_root(root, ticker)
    for name in SHARED_ARTIFACT_KINDS:
        (ticker_root / name).mkdir(parents=True, exist_ok=True)
    runs_root = ticker_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    return ticker_root, runs_root


def _initial_index(ticker: str) -> dict[str, Any]:
    return {"schema_version": 1, "ticker": ticker, "runs": []}


def _read_index(index_path: Path, ticker: str) -> dict[str, Any]:
    if not index_path.exists():
        return _initial_index(ticker)
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunStoreError(f"run index is unreadable: {index_path}: {exc}") from exc
    if (
        index.get("schema_version") != 1
        or index.get("ticker") != ticker
        or not isinstance(index.get("runs"), list)
    ):
        raise RunStoreError(f"run index has an incompatible schema: {index_path}")
    return index


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(_canonical_json(payload) + b"\n")
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _record_from_checkpoint(run_path: Path, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "run_id",
        "parent_run_id",
        "ticker",
        "skill_name",
        "target_fiscal_year",
        "AS_OF",
        "skill_version",
        "input_fingerprint",
        "created_at",
        "status",
    )
    missing = [field for field in required if field not in checkpoint]
    if missing or checkpoint["run_id"] != run_path.name:
        raise RunStoreError(
            f"checkpoint identity is incomplete for {run_path}: {', '.join(missing)}"
        )
    record = {
        "run_id": checkpoint["run_id"],
        "parent_run_id": checkpoint["parent_run_id"],
        "skill_name": checkpoint["skill_name"],
        "target_fiscal_year": checkpoint["target_fiscal_year"],
        "AS_OF": checkpoint["AS_OF"],
        "skill_version": checkpoint["skill_version"],
        "input_fingerprint": checkpoint["input_fingerprint"],
        "created_at": checkpoint["created_at"],
        "status": checkpoint["status"],
        "run_path": str(run_path.resolve()),
        "report_path": str((run_path / "report.md").resolve()),
        "result_path": checkpoint.get("result_path"),
        "result_artifact_id": checkpoint.get("result_artifact_id"),
    }
    if "completed_at" in checkpoint:
        record["completed_at"] = checkpoint["completed_at"]
    return record


def _reconcile_index(index: dict[str, Any], runs_root: Path, ticker: str) -> bool:
    changed = False
    checkpoint_run_ids: set[str] = set()
    records_by_id = {
        str(record.get("run_id")): record for record in index["runs"] if isinstance(record, dict)
    }
    for run_path in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        checkpoint_path = run_path / "checkpoint.json"
        if not checkpoint_path.is_file():
            continue
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RunStoreError(f"checkpoint is unreadable: {checkpoint_path}: {exc}") from exc
        if checkpoint.get("ticker") != ticker:
            raise RunStoreError(f"checkpoint ticker mismatch: {checkpoint_path}")
        recovered = _record_from_checkpoint(run_path, checkpoint)
        checkpoint_run_ids.add(str(recovered["run_id"]))
        existing = records_by_id.get(recovered["run_id"])
        if existing is None:
            index["runs"].append(recovered)
            records_by_id[recovered["run_id"]] = recovered
            changed = True
            continue
        immutable_fields = (
            "parent_run_id",
            "skill_name",
            "target_fiscal_year",
            "AS_OF",
            "skill_version",
            "input_fingerprint",
            "created_at",
            "run_path",
            "report_path",
        )
        if any(existing.get(field) != recovered[field] for field in immutable_fields):
            raise RunStoreError(f"checkpoint and index identity conflict: {run_path}")
        mutable_fields = (
            "status",
            "completed_at",
            "result_path",
            "result_artifact_id",
        )
        for field in mutable_fields:
            if existing.get(field) != recovered.get(field):
                if field in recovered:
                    existing[field] = recovered[field]
                else:
                    existing.pop(field, None)
                changed = True
    retained_records = [
        record for record in index["runs"] if str(record.get("run_id")) in checkpoint_run_ids
    ]
    if len(retained_records) != len(index["runs"]):
        index["runs"] = retained_records
        changed = True
    return changed


def _locked_index(runs_root: Path):
    lock_path = runs_root / ".index.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    return lock_fd


def _run_sort_key(record: Mapping[str, Any]) -> tuple[str, int, str]:
    raw_run_id = str(record.get("run_id", ""))
    match = re.search(r"-v(\d+)$", raw_run_id)
    version = int(match.group(1)) if match else 0
    return str(record.get("created_at", "")), version, str(record.get("run_path", ""))


def _input_fingerprint(
    ticker: str,
    skill_name: str,
    target_fiscal_year: int,
    as_of: date,
    skill_version: str,
    input_artifact_ids: Sequence[str],
    parameters: Mapping[str, Any],
) -> str:
    return artifact_id(
        "run-input",
        "1",
        input_artifact_ids,
        {
            "ticker": ticker,
            "skill_name": skill_name,
            "target_fiscal_year": target_fiscal_year,
            "as_of": as_of.isoformat(),
            "skill_version": skill_version,
            "parameters": parameters,
        },
    )


def _allocate_run_directory(
    runs_root: Path,
    skill_name: str,
    target_fiscal_year: int,
    created_at: datetime,
) -> tuple[str, Path]:
    prefix = f"{skill_name}-{target_fiscal_year}-{created_at.astimezone(SHANGHAI):%Y%m%d}-v"
    version = 1
    while True:
        run_id = f"{prefix}{version}"
        run_path = runs_root / run_id
        try:
            run_path.mkdir()
            return run_id, run_path
        except FileExistsError:
            version += 1


def _resolution_from_record(
    action: ResolutionAction,
    record: Mapping[str, Any],
    fingerprint: str,
) -> Resolution:
    report_path = record.get("result_path")
    if report_path is None:
        report_path = record["report_path"]
    return Resolution(
        action=action,
        run_id=None if action == "reused" else str(record["run_id"]),
        run_path=None if action == "reused" else Path(str(record["run_path"])),
        report_path=Path(str(report_path)),
        input_fingerprint=fingerprint,
        parent_run_id=record.get("parent_run_id"),
    )


def _has_published_result(record: Mapping[str, Any]) -> bool:
    result_path = Path(str(record.get("result_path") or record["report_path"]))
    try:
        return result_path.is_file() and result_path.stat().st_size > 0
    except OSError:
        return False


def resolve_run(
    root: Path,
    ticker: str,
    skill_name: str,
    target_fiscal_year: int,
    as_of: date,
    skill_version: str,
    input_artifact_ids: Sequence[str],
    parameters: Mapping[str, Any],
    *,
    clean: bool = False,
    result_path: Path | None = None,
    now: datetime | None = None,
) -> Resolution:
    _validate_identity(ticker, skill_name)
    if not 1900 <= target_fiscal_year <= 2100:
        raise RunStoreError("target fiscal year must be between 1900 and 2100")
    created_at = now or datetime.now(SHANGHAI)
    if created_at.tzinfo is None:
        raise RunStoreError("now must include a timezone")
    fingerprint = _input_fingerprint(
        ticker,
        skill_name,
        target_fiscal_year,
        as_of,
        skill_version,
        input_artifact_ids,
        parameters,
    )
    requested_result_path = None if result_path is None else str(result_path.resolve())
    _, runs_root = _initialize_layout(root, ticker)
    index_path = runs_root / "index.json"
    lock_fd = _locked_index(runs_root)
    try:
        index = _read_index(index_path, ticker)
        if _reconcile_index(index, runs_root, ticker):
            _write_json_atomic(index_path, index)
        related = [
            record
            for record in index["runs"]
            if record.get("skill_name") == skill_name
            and record.get("target_fiscal_year") == target_fiscal_year
        ]
        matching = [record for record in related if record.get("input_fingerprint") == fingerprint]
        if not clean:
            unfinished = [
                record
                for record in matching
                if record.get("status") in {"in_progress", "manual_review"}
            ]
            if unfinished:
                return _resolution_from_record(
                    "resumed",
                    max(unfinished, key=_run_sort_key),
                    fingerprint,
                )
            completed = [
                record
                for record in matching
                if record.get("status") == "completed" and _has_published_result(record)
            ]
            if completed:
                return _resolution_from_record(
                    "reused",
                    max(completed, key=_run_sort_key),
                    fingerprint,
                )

        parent = None if clean or not related else max(related, key=_run_sort_key)
        invalidated = (
            [str(parent["result_artifact_id"])]
            if parent
            and parent.get("result_artifact_id")
            and parent.get("input_fingerprint") != fingerprint
            else []
        )
        run_id, run_path = _allocate_run_directory(
            runs_root,
            skill_name,
            target_fiscal_year,
            created_at,
        )
        for name in RUN_LOCAL_DIRECTORIES:
            (run_path / name).mkdir()
        report_path = run_path / "report.md"
        checkpoint = {
            "schema_version": 1,
            "run_id": run_id,
            "parent_run_id": None if parent is None else parent["run_id"],
            "ticker": ticker,
            "skill_name": skill_name,
            "target_fiscal_year": target_fiscal_year,
            "AS_OF": as_of.isoformat(),
            "skill_version": skill_version,
            "input_fingerprint": fingerprint,
            "input_artifact_ids": sorted(input_artifact_ids),
            "parameters": parameters,
            "created_at": created_at.astimezone(SHANGHAI).isoformat(),
            "status": "in_progress",
            "clean": clean,
            "inherited_artifacts": [],
            "invalidated_artifacts": invalidated,
            "completed_steps": [],
            "result_path": requested_result_path,
        }
        _write_json_atomic(run_path / "checkpoint.json", checkpoint)
        record = {
            "run_id": run_id,
            "parent_run_id": checkpoint["parent_run_id"],
            "skill_name": skill_name,
            "target_fiscal_year": target_fiscal_year,
            "AS_OF": as_of.isoformat(),
            "skill_version": skill_version,
            "input_fingerprint": fingerprint,
            "created_at": checkpoint["created_at"],
            "status": "in_progress",
            "run_path": str(run_path.resolve()),
            "report_path": str(report_path.resolve()),
            "result_path": requested_result_path,
            "result_artifact_id": None,
        }
        index["runs"].append(record)
        _write_json_atomic(index_path, index)
        return _resolution_from_record("created", record, fingerprint)
    finally:
        os.close(lock_fd)


def complete_run(
    root: Path,
    ticker: str,
    run_id: str,
    result_artifact_id: str,
    *,
    result_path: Path | None = None,
    completed_at: datetime | None = None,
) -> None:
    _, runs_root = _initialize_layout(root, ticker)
    index_path = runs_root / "index.json"
    finished_at = completed_at or datetime.now(SHANGHAI)
    if finished_at.tzinfo is None:
        raise RunStoreError("completed_at must include a timezone")
    lock_fd = _locked_index(runs_root)
    try:
        index = _read_index(index_path, ticker)
        if _reconcile_index(index, runs_root, ticker):
            _write_json_atomic(index_path, index)
        records = [record for record in index["runs"] if record.get("run_id") == run_id]
        if len(records) != 1:
            raise RunStoreError(f"run ID is missing or ambiguous: {run_id}")
        record = records[0]
        stored_result_path = record.get("result_path")
        if (
            result_path is not None
            and stored_result_path is not None
            and result_path.resolve() != Path(str(stored_result_path))
        ):
            raise RunStoreError(f"result path conflicts with run checkpoint: {run_id}")
        published_path = Path(
            str(
                result_path.resolve()
                if result_path is not None
                else stored_result_path or record["report_path"]
            )
        )
        if not published_path.is_file() or published_path.stat().st_size == 0:
            raise RunStoreError(f"report is not published: {published_path}")
        checkpoint_path = Path(str(record["run_path"])) / "checkpoint.json"
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RunStoreError(f"checkpoint is unreadable: {checkpoint_path}: {exc}") from exc
        completed_at_text = finished_at.astimezone(SHANGHAI).isoformat()
        checkpoint.update(
            {
                "status": "completed",
                "completed_at": completed_at_text,
                "result_artifact_id": result_artifact_id,
                "result_path": str(published_path),
            }
        )
        _write_json_atomic(checkpoint_path, checkpoint)
        record.update(
            {
                "status": "completed",
                "completed_at": completed_at_text,
                "result_artifact_id": result_artifact_id,
                "result_path": str(published_path),
            }
        )
        _write_json_atomic(index_path, index)
    finally:
        os.close(lock_fd)


def validate_research_ledger_wrapper(wrapper: Mapping[str, Any]) -> None:
    """Validate one claim-indexed value-profile research-ledger wrapper."""
    if not isinstance(wrapper, Mapping) or not wrapper:
        raise RunStoreError("research ledger wrapper must be a nonempty claim mapping")
    validate_payload, request_scope_fingerprint = _research_contract_api()
    for claim_id, raw_entry in wrapper.items():
        if not isinstance(claim_id, str) or not claim_id:
            raise RunStoreError("research ledger wrapper claim IDs must be nonempty strings")
        entry = _strict_mapping(
            raw_entry,
            {
                "request",
                "planner_inventory_receipt",
                "ledger",
                "accepted_candidate",
            },
            f"research ledger entry {claim_id}",
        )
        request = _mapping_field(entry, "request", claim_id)
        ledger = _mapping_field(entry, "ledger", claim_id)
        planner_inventory_receipt = _mapping_field(
            entry,
            "planner_inventory_receipt",
            claim_id,
        )
        try:
            validate_payload("request", request)
        except (TypeError, ValueError) as exc:
            raise RunStoreError(f"research ledger entry {claim_id} is invalid: {exc}") from exc

        expected_scope = request_scope_fingerprint(request)
        _validate_run_store_planner_receipt(
            claim_id,
            request,
            expected_scope,
            planner_inventory_receipt,
        )
        try:
            validate_payload(
                "ledger",
                ledger,
                planner_inventory_receipt=planner_inventory_receipt,
            )
        except (TypeError, ValueError) as exc:
            raise RunStoreError(f"research ledger entry {claim_id} is invalid: {exc}") from exc

        if request.get("claim_id") != claim_id or ledger.get("claim_id") != claim_id:
            raise RunStoreError(f"research ledger entry {claim_id} has a claim ID mismatch")
        if ledger.get("request_scope_fingerprint") != expected_scope:
            raise RunStoreError(
                f"research ledger entry {claim_id} has a request scope fingerprint mismatch"
            )
        if ledger.get("absence_claim") != request.get("absence_claim"):
            raise RunStoreError(f"research ledger entry {claim_id} has an absence-claim mismatch")
        _validate_accepted_candidate_handoff(
            claim_id,
            ledger,
            entry.get("accepted_candidate"),
        )


def _validate_run_store_planner_receipt(
    claim_id: str,
    request: Mapping[str, Any],
    expected_scope: str,
    receipt: Mapping[str, Any],
) -> None:
    if receipt.get("claim_id") != claim_id:
        raise RunStoreError(f"research ledger entry {claim_id} receipt claim ID mismatch")
    if receipt.get("request_scope_fingerprint") != expected_scope:
        raise RunStoreError(
            f"research ledger entry {claim_id} receipt request scope does not match wrapper request"
        )

    planner_inputs = receipt.get("planner_inputs")
    if not isinstance(planner_inputs, Mapping):
        raise RunStoreError(f"research ledger entry {claim_id} planner_inputs must be an object")
    expected_fingerprint = _sha256(_canonical_json(planner_inputs))
    if receipt.get("planner_input_fingerprint") != expected_fingerprint:
        raise RunStoreError(
            f"research ledger entry {claim_id} run-store planner input fingerprint mismatch"
        )
    route_inventory = receipt.get("route_inventory")
    if (
        not isinstance(route_inventory, Sequence)
        or isinstance(route_inventory, (str, bytes))
        or planner_inputs.get("route_inventory_sha256") != _sha256(_canonical_json(route_inventory))
    ):
        raise RunStoreError(
            f"research ledger entry {claim_id} run-store route inventory SHA-256 mismatch"
        )

    request_identity = planner_inputs.get("request_identity")
    if not isinstance(request_identity, Mapping):
        raise RunStoreError(f"research ledger entry {claim_id} request identity must be an object")
    if (
        request_identity.get("claim_id") != claim_id
        or request_identity.get("request_scope_fingerprint") != expected_scope
    ):
        raise RunStoreError(f"research ledger entry {claim_id} planner request identity mismatch")
    if request_identity.get("request_content_sha256") != _sha256(_canonical_json(request)):
        raise RunStoreError(f"research ledger entry {claim_id} planner request content mismatch")
    if planner_inputs.get("as_of") != request.get("as_of"):
        raise RunStoreError(f"research ledger entry {claim_id} planner AS_OF mismatch")


def bind_research_ledger(
    root: Path,
    ticker: str,
    run_id: str,
    wrapper: Mapping[str, Any],
    *,
    expected_prior_sha256: str = CREATE_ONLY_SENTINEL,
) -> PromotedArtifact:
    """Atomically bind the singleton research ledger to a value-profile run."""
    validate_research_ledger_wrapper(wrapper)
    _validate_expected_prior_sha256(expected_prior_sha256)
    run_path, runs_root = _research_run_path(root, ticker, run_id)
    lock_fd = _locked_index(runs_root)
    try:
        checkpoint_path = run_path / "checkpoint.json"
        checkpoint = _read_research_checkpoint(checkpoint_path, ticker, run_id)
        if "research_ledger" in checkpoint:
            _load_bound_research_ledger(run_path, checkpoint)
            prior_sha256 = checkpoint["research_ledger"]["sha256"]
            if expected_prior_sha256 == CREATE_ONLY_SENTINEL:
                raise RunStoreError(
                    "research ledger expected prior SHA-256 is create-only, "
                    "but a binding already exists"
                )
            if prior_sha256 != expected_prior_sha256:
                raise RunStoreError(
                    "research ledger expected prior SHA-256 does not match the current binding"
                )
        elif expected_prior_sha256 != CREATE_ONLY_SENTINEL:
            raise RunStoreError(
                "research ledger expected prior SHA-256 cannot update a missing binding"
            )

        ledger_path = (run_path / "logs" / RESEARCH_LEDGER_FILENAME).resolve()
        body = _canonical_json(wrapper) + b"\n"
        content_sha256 = _sha256(body)
        identifier = _research_ledger_artifact_id(content_sha256)
        _write_json_atomic(ledger_path, wrapper)
        checkpoint["research_ledger"] = {
            "artifact_id": identifier,
            "path": str(ledger_path),
            "sha256": content_sha256,
        }
        _write_json_atomic(checkpoint_path, checkpoint)
        return PromotedArtifact(identifier, ledger_path, content_sha256)
    finally:
        os.close(lock_fd)


def _validate_expected_prior_sha256(expected_prior_sha256: str) -> None:
    if expected_prior_sha256 != CREATE_ONLY_SENTINEL and (
        not isinstance(expected_prior_sha256, str)
        or not SHA256_PATTERN.fullmatch(expected_prior_sha256)
    ):
        raise RunStoreError(
            "research ledger expected prior SHA-256 must be create-only or a lowercase SHA-256"
        )


def load_research_ledger(
    root: Path,
    ticker: str,
    run_id: str,
) -> dict[str, Any]:
    """Load a checkpoint-bound research ledger without rebuilding it."""
    run_path, runs_root = _research_run_path(root, ticker, run_id)
    lock_fd = _locked_index(runs_root)
    try:
        checkpoint = _read_research_checkpoint(
            run_path / "checkpoint.json",
            ticker,
            run_id,
        )
        return _load_bound_research_ledger(run_path, checkpoint)
    finally:
        os.close(lock_fd)


def _research_run_path(root: Path, ticker: str, run_id: str) -> tuple[Path, Path]:
    _validate_identity(ticker)
    if not isinstance(run_id, str) or not run_id or Path(run_id).name != run_id:
        raise RunStoreError(f"run ID is invalid: {run_id}")
    runs_root = _ticker_root(root, ticker) / "runs"
    run_path = (runs_root / run_id).resolve()
    if run_path.parent != runs_root.resolve() or not run_path.is_dir():
        raise RunStoreError(f"run ID is missing or invalid: {run_id}")
    return run_path, runs_root


def _read_research_checkpoint(
    checkpoint_path: Path,
    ticker: str,
    run_id: str,
) -> dict[str, Any]:
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunStoreError(f"checkpoint is unreadable: {checkpoint_path}: {exc}") from exc
    if not isinstance(checkpoint, dict):
        raise RunStoreError(f"checkpoint must be an object: {checkpoint_path}")
    if checkpoint.get("ticker") != ticker or checkpoint.get("run_id") != run_id:
        raise RunStoreError(f"checkpoint identity mismatch: {checkpoint_path}")
    if checkpoint.get("skill_name") != "value-profile":
        raise RunStoreError("research ledger binding is only valid for a value-profile run")
    return checkpoint


def _load_bound_research_ledger(
    run_path: Path,
    checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    binding = checkpoint.get("research_ledger")
    if not isinstance(binding, Mapping):
        raise RunStoreError("research ledger is not bound in checkpoint")
    if set(binding) != {"artifact_id", "path", "sha256"}:
        raise RunStoreError(
            "research ledger checkpoint binding must contain exactly artifact_id, path, and sha256"
        )
    raw_path = binding.get("path")
    if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
        raise RunStoreError("research ledger checkpoint path must be absolute")
    ledger_path = Path(raw_path)
    expected_path = (run_path / "logs" / RESEARCH_LEDGER_FILENAME).resolve()
    if ledger_path != expected_path or ledger_path.resolve() != expected_path:
        raise RunStoreError("research ledger checkpoint path is not the fixed run path")
    if not ledger_path.is_file():
        raise RunStoreError(f"research ledger file is missing: {ledger_path}")
    try:
        body = ledger_path.read_bytes()
    except OSError as exc:
        raise RunStoreError(f"research ledger is unreadable: {ledger_path}: {exc}") from exc

    recorded_sha256 = binding.get("sha256")
    if not isinstance(recorded_sha256, str) or not SHA256_PATTERN.fullmatch(recorded_sha256):
        raise RunStoreError("research ledger checkpoint SHA-256 is invalid")
    content_sha256 = _sha256(body)
    if content_sha256 != recorded_sha256:
        raise RunStoreError("research ledger SHA-256 mismatch")
    expected_artifact_id = _research_ledger_artifact_id(content_sha256)
    if binding.get("artifact_id") != expected_artifact_id:
        raise RunStoreError("research ledger artifact ID mismatch")
    try:
        wrapper = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunStoreError(f"research ledger is invalid JSON: {ledger_path}: {exc}") from exc
    if not isinstance(wrapper, dict):
        raise RunStoreError("research ledger wrapper must be a JSON object")
    validate_research_ledger_wrapper(wrapper)
    return wrapper


def _research_ledger_artifact_id(content_sha256: str) -> str:
    return artifact_id(
        "research-ledger",
        "1",
        (),
        {"content_sha256": content_sha256},
    )


def _strict_mapping(
    value: object,
    expected_keys: set[str],
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RunStoreError(f"{context} must be an object")
    if set(value) != expected_keys:
        raise RunStoreError(f"{context} must contain exactly: {', '.join(sorted(expected_keys))}")
    return value


def _mapping_field(
    mapping: Mapping[str, Any],
    key: str,
    claim_id: str,
) -> Mapping[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise RunStoreError(f"research ledger entry {claim_id}.{key} must be an object")
    return value


def _validate_accepted_candidate_handoff(
    claim_id: str,
    ledger: Mapping[str, Any],
    raw_handoff: object,
) -> None:
    if ledger.get("status") != "accepted":
        if raw_handoff is not None:
            raise RunStoreError(
                f"research ledger entry {claim_id} cannot retain accepted candidate handoff"
            )
        return
    handoff = _strict_mapping(
        raw_handoff,
        {
            "claim_id",
            "request_scope_fingerprint",
            "candidate_document_id",
            "artifact_identity",
            "artifact_sha256",
            "source_document_identity",
            "lineage_id",
            "consuming_section_ids",
        },
        f"research ledger entry {claim_id} accepted candidate",
    )
    artifact_sha256 = handoff.get("artifact_sha256")
    if not isinstance(artifact_sha256, str) or not SHA256_PATTERN.fullmatch(artifact_sha256):
        raise RunStoreError(
            f"research ledger entry {claim_id} accepted candidate SHA-256 is invalid"
        )
    if handoff.get("artifact_identity") != f"sha256:{artifact_sha256}":
        raise RunStoreError(
            f"research ledger entry {claim_id} accepted candidate artifact identity mismatch"
        )
    source_identity = _strict_mapping(
        handoff.get("source_document_identity"),
        {"binding_sha256"},
        f"research ledger entry {claim_id} source document identity",
    )
    binding_sha256 = source_identity.get("binding_sha256")
    if not isinstance(binding_sha256, str) or not SHA256_PATTERN.fullmatch(binding_sha256):
        raise RunStoreError(f"research ledger entry {claim_id} source binding SHA-256 is invalid")
    sections = handoff.get("consuming_section_ids")
    if (
        not isinstance(sections, Sequence)
        or isinstance(sections, (str, bytes))
        or not all(isinstance(section, str) and section for section in sections)
        or len(sections) != len(set(sections))
    ):
        raise RunStoreError(f"research ledger entry {claim_id} consuming section IDs are invalid")
    accepted_evidence = ledger.get("accepted_evidence")
    if not isinstance(accepted_evidence, Mapping):
        raise RunStoreError(f"research ledger entry {claim_id} lacks accepted evidence")
    expected = {
        "claim_id": claim_id,
        "request_scope_fingerprint": ledger.get("request_scope_fingerprint"),
        "candidate_document_id": accepted_evidence.get("candidate_document_id"),
        "artifact_identity": accepted_evidence.get("artifact_identity"),
        "lineage_id": accepted_evidence.get("lineage_id"),
    }
    if any(handoff.get(field) != value for field, value in expected.items()):
        raise RunStoreError(
            f"research ledger entry {claim_id} accepted candidate identity mismatch"
        )


def promote_artifact(
    root: Path,
    ticker: str,
    artifact_kind: SharedArtifactKind,
    source: Path,
    schema_version: str,
    input_artifact_ids: Sequence[str],
    parameters: Mapping[str, Any],
) -> PromotedArtifact:
    if artifact_kind not in SHARED_ARTIFACT_KINDS:
        raise RunStoreError(f"unsupported shared artifact kind: {artifact_kind}")
    ticker_root, _ = _initialize_layout(root, ticker)
    try:
        body = source.read_bytes()
    except OSError as exc:
        raise RunStoreError(f"artifact source is unreadable: {source}: {exc}") from exc
    content_sha256 = _sha256(body)
    identifier = artifact_id(
        artifact_kind,
        schema_version,
        input_artifact_ids,
        {
            "content_sha256": content_sha256,
            "parameters": parameters,
        },
    )
    suffix = "".join(source.suffixes)
    target = ticker_root / artifact_kind / f"{identifier}{suffix}"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{identifier}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(body)
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != body:
                raise RunStoreError(
                    f"artifact ID collision with different content: {identifier}"
                ) from None
        temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return PromotedArtifact(identifier, target.resolve(), content_sha256)


def discover_legacy_reports(repo_root: Path, ticker: str) -> tuple[Path, ...]:
    _validate_identity(ticker)
    profiles = repo_root / "profiles"
    patterns = (
        f"{ticker}-reading-*-scratch.md",
        f"{ticker}-product-*.md",
        f"{ticker}-mgmt-*.md",
        f"{ticker}-redflags-*.md",
    )
    return tuple(sorted({path for pattern in patterns for path in profiles.glob(pattern)}))


def _parse_parameters(values: Sequence[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise RunStoreError("parameter must use KEY=JSON_VALUE")
        key, raw = value.split("=", 1)
        if not key or key in parsed:
            raise RunStoreError(f"parameter key is empty or duplicated: {key}")
        try:
            parsed[key] = json.loads(raw)
        except json.JSONDecodeError:
            parsed[key] = raw
    return parsed


def _read_json_mapping(path: Path, context: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunStoreError(f"{context} is unreadable: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RunStoreError(f"{context} must be a JSON object: {path}")
    return payload


def _add_common_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ticker", required=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve")
    _add_common_identity(resolve_parser)
    resolve_parser.add_argument("--skill", required=True)
    resolve_parser.add_argument("--target-year", type=int, required=True)
    resolve_parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    resolve_parser.add_argument("--skill-version", required=True)
    resolve_parser.add_argument("--input-artifact", action="append", default=[])
    resolve_parser.add_argument("--parameter", action="append", default=[])
    resolve_parser.add_argument("--clean", action="store_true")
    resolve_parser.add_argument("--result-path", type=Path)

    complete_parser = subparsers.add_parser("complete")
    _add_common_identity(complete_parser)
    complete_parser.add_argument("--run-id", required=True)
    complete_parser.add_argument("--result-artifact-id", required=True)
    complete_parser.add_argument("--result-path", type=Path)

    promote_parser = subparsers.add_parser("promote")
    _add_common_identity(promote_parser)
    promote_parser.add_argument("--kind", choices=SHARED_ARTIFACT_KINDS, required=True)
    promote_parser.add_argument("--source", type=Path, required=True)
    promote_parser.add_argument("--schema-version", required=True)
    promote_parser.add_argument("--input-artifact", action="append", default=[])
    promote_parser.add_argument("--parameter", action="append", default=[])

    bind_ledger_parser = subparsers.add_parser("bind-research-ledger")
    _add_common_identity(bind_ledger_parser)
    bind_ledger_parser.add_argument("--run-id", required=True)
    bind_ledger_parser.add_argument("--wrapper", type=Path, required=True)
    bind_ledger_parser.add_argument("--expected-prior-sha256", required=True)

    validate_ledger_parser = subparsers.add_parser("validate-research-ledger")
    _add_common_identity(validate_ledger_parser)
    validate_ledger_parser.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "resolve":
            output = asdict(
                resolve_run(
                    args.root,
                    args.ticker,
                    args.skill,
                    args.target_year,
                    args.as_of,
                    args.skill_version,
                    args.input_artifact,
                    _parse_parameters(args.parameter),
                    clean=args.clean,
                    result_path=args.result_path,
                )
            )
        elif args.command == "complete":
            complete_run(
                args.root,
                args.ticker,
                args.run_id,
                args.result_artifact_id,
                result_path=args.result_path,
            )
            output = {"status": "completed", "run_id": args.run_id}
        elif args.command == "promote":
            promoted = promote_artifact(
                args.root,
                args.ticker,
                args.kind,
                args.source,
                args.schema_version,
                args.input_artifact,
                _parse_parameters(args.parameter),
            )
            output = asdict(promoted)
        elif args.command == "bind-research-ledger":
            binding = bind_research_ledger(
                args.root,
                args.ticker,
                args.run_id,
                _read_json_mapping(args.wrapper, "research ledger wrapper"),
                expected_prior_sha256=args.expected_prior_sha256,
            )
            output = asdict(binding)
        else:
            wrapper = load_research_ledger(
                args.root,
                args.ticker,
                args.run_id,
            )
            output = {
                "status": "valid",
                "run_id": args.run_id,
                "claim_ids": sorted(wrapper),
            }
        print(json.dumps(output, ensure_ascii=False, default=str, sort_keys=True))
        return 0
    except RunStoreError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
