from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.financial_run_store import (
    RunStoreError,
    complete_run,
    discover_legacy_reports,
    promote_artifact,
    resolve_run,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def resolve(
    root: Path,
    *,
    input_artifact_ids: tuple[str, ...] = ("annual:aaa",),
    clean: bool = False,
    result_path: Path | None = None,
):
    return resolve_run(
        root=root,
        ticker="600519.SH",
        skill_name="read-filing",
        target_fiscal_year=2025,
        as_of=date(2026, 4, 1),
        skill_version="1",
        input_artifact_ids=input_artifact_ids,
        parameters={"section": "all"},
        clean=clean,
        result_path=result_path,
        now=datetime(2026, 7, 28, 9, 30, tzinfo=SHANGHAI),
    )


def test_first_resolution_initializes_shared_and_run_local_directories(tmp_path: Path) -> None:
    result = resolve(tmp_path / "data" / "filings")

    assert result.action == "created"
    assert result.run_id == "read-filing-2025-20260728-v1"
    assert result.run_path is not None
    assert result.report_path == result.run_path / "report.md"
    ticker_root = tmp_path / "data" / "filings" / "600519.SH"
    for name in (
        "manifests",
        "evidence",
        "_extracted",
        "facts",
        "metrics",
        "citations",
        "analyses",
        "market",
    ):
        assert (ticker_root / name).is_dir()
    for name in ("drafts", "manifests", "query", "logs", "tmp"):
        assert (result.run_path / name).is_dir()
    assert (result.run_path / "checkpoint.json").is_file()
    assert (ticker_root / "runs" / "index.json").is_file()


def test_matching_unfinished_run_resumes_without_new_directory(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)
    resumed = resolve(root)

    assert resumed.action == "resumed"
    assert resumed.run_id == first.run_id
    assert resumed.run_path == first.run_path
    assert len(list((root / "600519.SH" / "runs").glob("read-filing-*"))) == 1


def test_orphaned_checkpoint_is_recovered_into_index(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)
    index_path = root / "600519.SH" / "runs" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["runs"] = []
    index_path.write_text(json.dumps(index), encoding="utf-8")

    recovered = resolve(root)

    assert recovered.action == "resumed"
    assert recovered.run_id == first.run_id
    repaired = json.loads(index_path.read_text(encoding="utf-8"))
    assert [record["run_id"] for record in repaired["runs"]] == [first.run_id]


def test_index_record_without_checkpoint_is_not_resumed(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)
    assert first.run_path is not None
    (first.run_path / "checkpoint.json").unlink()

    replacement = resolve(root)

    assert replacement.action == "created"
    assert replacement.run_id == "read-filing-2025-20260728-v2"


def test_matching_completed_run_reuses_result_without_new_run(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)
    assert first.run_id is not None
    assert first.report_path is not None
    first.report_path.write_text("# report\n", encoding="utf-8")
    complete_run(
        root,
        "600519.SH",
        first.run_id,
        "analysis:accepted",
        completed_at=datetime(2026, 7, 28, 10, 0, tzinfo=SHANGHAI),
    )
    before = set((root / "600519.SH" / "runs").glob("read-filing-*"))

    reused = resolve(root)

    assert reused.action == "reused"
    assert reused.run_id is None
    assert reused.report_path == first.report_path
    assert set((root / "600519.SH" / "runs").glob("read-filing-*")) == before


def test_completed_checkpoint_repairs_stale_index(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)
    assert first.run_path is not None
    assert first.report_path is not None
    first.report_path.write_text("# report\n", encoding="utf-8")
    checkpoint_path = first.run_path / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint.update(
        {
            "status": "completed",
            "completed_at": "2026-07-28T10:00:00+08:00",
            "result_artifact_id": "analysis:accepted",
            "result_path": str(first.report_path),
        }
    )
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    recovered = resolve(root)

    assert recovered.action == "reused"
    assert recovered.report_path == first.report_path
    index = json.loads((root / "600519.SH" / "runs" / "index.json").read_text(encoding="utf-8"))
    assert index["runs"][0]["status"] == "completed"


def test_completed_value_profile_reuses_external_result_path(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    profile = tmp_path / "profiles" / "600519.SH-2026-07-28.md"
    profile.parent.mkdir()
    first = resolve(root, result_path=profile)
    assert first.run_id is not None
    assert first.report_path == profile.resolve()
    profile.write_text("# value profile\n", encoding="utf-8")
    complete_run(
        root,
        "600519.SH",
        first.run_id,
        "analysis:value-profile",
        result_path=profile,
    )

    reused = resolve(root)

    assert reused.action == "reused"
    assert reused.report_path == profile.resolve()


def test_unfinished_value_profile_resumes_external_result_path(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    profile = tmp_path / "profiles" / "600519.SH-2026-07-28.md"
    first = resolve(root, result_path=profile)

    resumed = resolve(root, result_path=profile)

    assert resumed.action == "resumed"
    assert resumed.run_id == first.run_id
    assert resumed.report_path == profile.resolve()
    checkpoint = json.loads((first.run_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["result_path"] == str(profile.resolve())


def test_existing_run_keeps_bound_result_path_when_candidate_changes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data" / "filings"
    first_profile = tmp_path / "profiles" / "600519.SH-2026-07-28.md"
    next_candidate = tmp_path / "profiles" / "600519.SH-2026-07-28-v2.md"
    first = resolve(root, result_path=first_profile)

    resumed = resolve(root, result_path=next_candidate)

    assert resumed.action == "resumed"
    assert resumed.run_id == first.run_id
    assert resumed.report_path == first_profile.resolve()


def test_missing_completed_result_creates_replacement_run(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)
    assert first.run_id is not None
    assert first.report_path is not None
    first.report_path.write_text("# report\n", encoding="utf-8")
    complete_run(root, "600519.SH", first.run_id, "analysis:accepted")
    first.report_path.unlink()

    replacement = resolve(root)

    assert replacement.action == "created"
    assert replacement.parent_run_id == first.run_id
    assert replacement.run_id == "read-filing-2025-20260728-v2"


def test_changed_inputs_create_incremental_child_run(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)
    assert first.run_id is not None
    assert first.report_path is not None
    first.report_path.write_text("# report\n", encoding="utf-8")
    complete_run(root, "600519.SH", first.run_id, "analysis:accepted")

    changed = resolve(root, input_artifact_ids=("annual:bbb",))

    assert changed.action == "created"
    assert changed.run_id == "read-filing-2025-20260728-v2"
    assert changed.parent_run_id == first.run_id
    checkpoint = json.loads((changed.run_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["parent_run_id"] == first.run_id
    assert checkpoint["inherited_artifacts"] == []
    assert checkpoint["invalidated_artifacts"] == ["analysis:accepted"]


def test_run_cannot_complete_before_report_is_published(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)
    assert first.run_id is not None

    with pytest.raises(RunStoreError, match="report is not published"):
        complete_run(root, "600519.SH", first.run_id, "analysis:accepted")


def test_explicit_clean_run_has_no_parent(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    first = resolve(root)

    clean = resolve(root, clean=True)

    assert first.run_id != clean.run_id
    assert clean.parent_run_id is None
    checkpoint = json.loads((clean.run_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["clean"] is True
    assert checkpoint["inherited_artifacts"] == []


def test_concurrent_clean_runs_allocate_distinct_ids(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: resolve(root, clean=True), range(2)))

    assert {result.run_id for result in results} == {
        "read-filing-2025-20260728-v1",
        "read-filing-2025-20260728-v2",
    }


def test_promoted_artifact_is_content_addressed_and_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    source = tmp_path / "facts.json"
    source.write_text('{"revenue": 100}', encoding="utf-8")

    first = promote_artifact(
        root,
        "600519.SH",
        "facts",
        source,
        "1",
        ["annual:aaa"],
        {"currency": "CNY"},
    )
    second = promote_artifact(
        root,
        "600519.SH",
        "facts",
        source,
        "1",
        ["annual:aaa"],
        {"currency": "CNY"},
    )
    source.write_text('{"revenue": 101}', encoding="utf-8")
    changed = promote_artifact(
        root,
        "600519.SH",
        "facts",
        source,
        "1",
        ["annual:bbb"],
        {"currency": "CNY"},
    )

    assert first == second
    assert first.path.read_text(encoding="utf-8") == '{"revenue": 100}'
    assert changed.path != first.path
    assert changed.path.read_text(encoding="utf-8") == '{"revenue": 101}'
    assert first.path.parent == root / "600519.SH" / "facts"


def test_changed_artifact_bytes_get_a_new_content_address(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    source = tmp_path / "facts.json"
    source.write_text('{"revenue": 100}', encoding="utf-8")
    first = promote_artifact(
        root,
        "600519.SH",
        "facts",
        source,
        "1",
        ["annual:aaa"],
        {"currency": "CNY"},
    )
    source.write_text('{"revenue": 101}', encoding="utf-8")

    changed = promote_artifact(
        root,
        "600519.SH",
        "facts",
        source,
        "1",
        ["annual:aaa"],
        {"currency": "CNY"},
    )

    assert changed.path != first.path
    assert first.path.read_text(encoding="utf-8") == '{"revenue": 100}'
    assert changed.path.read_text(encoding="utf-8") == '{"revenue": 101}'


def test_legacy_reports_are_discovered_without_modification(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    legacy = (
        profiles / "600519.SH-reading-2025-scratch.md",
        profiles / "600519.SH-product-2026-07-20.md",
        profiles / "600519.SH-mgmt-2026-07-20.md",
        profiles / "600519.SH-redflags-2026-07-20.md",
    )
    for path in legacy:
        path.write_text(path.name, encoding="utf-8")
    main_profile = profiles / "600519.SH-2026-07-20.md"
    main_profile.write_text("main", encoding="utf-8")
    before = {path: path.stat().st_mtime_ns for path in legacy}

    discovered = discover_legacy_reports(tmp_path, "600519.SH")

    assert discovered == tuple(sorted(legacy))
    assert main_profile not in discovered
    assert {path: path.stat().st_mtime_ns for path in legacy} == before


def test_resolve_cli_prints_machine_readable_result(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/financial_run_store.py",
            "resolve",
            "--root",
            str(tmp_path / "data" / "filings"),
            "--ticker",
            "600519.SH",
            "--skill",
            "product-analysis",
            "--target-year",
            "2025",
            "--as-of",
            "2026-04-01",
            "--skill-version",
            "1",
            "--input-artifact",
            "annual:aaa",
            "--parameter",
            "section=all",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["action"] == "created"
    assert payload["run_id"].startswith("product-analysis-2025-")
