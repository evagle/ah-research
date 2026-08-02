from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import scripts.financial_run_store as run_store
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


def resolve_value_profile(root: Path):
    return resolve_run(
        root=root,
        ticker="600519.SH",
        skill_name="value-profile",
        target_fiscal_year=2025,
        as_of=date(2026, 8, 2),
        skill_version="1",
        input_artifact_ids=("annual:aaa",),
        parameters={"section": "all"},
        now=datetime(2026, 8, 2, 9, 30, tzinfo=SHANGHAI),
    )


def research_ledger_wrapper() -> dict[str, object]:
    scope_fingerprint = "b6616573be4a7627d0ece917e9230e2ffa226066166adac7a5d5dc1eebf21582"
    artifact_sha256 = "1" * 64
    binding_sha256 = "2" * 64
    claim_id = "cn-pop-toy-market-2020-2025"
    request = {
        "schema_version": "1.0",
        "claim_id": claim_id,
        "claim_type": "market-size",
        "subject": "China pop-toy market",
        "metric": "annual retail market size",
        "geographies": ["China"],
        "industries": ["pop-toys"],
        "population": "retail consumers",
        "product_scope": "pop toys only",
        "measurement_basis": "retail value",
        "period_start": "2020",
        "period_end": "2025",
        "frequency": "annual",
        "continuity_required": True,
        "required_latest_period": "2025",
        "accepted_units": ["CNY billion"],
        "definition_constraints": ["pop toys only", "retail value"],
        "value_status_allowed": ["observed", "historical-estimate", "forecast"],
        "minimum_source_authority": "High",
        "minimum_conclusion_evidence": "High",
        "minimum_originality": "High",
        "minimum_independence": "Medium",
        "independent_cross_check_required": False,
        "absence_claim": False,
        "as_of": "2026-08-02",
    }
    route = {
        "route_id": "layer-1-official-market-data",
        "route_layer": 1,
        "subject_relation": "direct",
        "document_type": "industry-report",
    }
    lineage_id = "underlying:" + "3" * 64
    ledger = {
        "schema_version": "1.0",
        "claim_id": claim_id,
        "request_scope_fingerprint": scope_fingerprint,
        "absence_claim": False,
        "status": "accepted",
        "applicable_routes": [route],
        "attempts": [
            {
                **route,
                "query_variant": '"China" "pop toys" market size',
                "started_at": "2026-08-02T01:00:00+00:00",
                "completed_at": "2026-08-02T01:01:00+00:00",
                "artifact_identity": f"sha256:{artifact_sha256}",
                "lineage_id": lineage_id,
                "terminal_reason": "accepted",
                "acceptance_failures": [],
            }
        ],
        "acceptance_failures": [],
        "accepted_evidence": {
            "candidate_document_id": "CCP-POP-TOY-2025",
            "artifact_identity": f"sha256:{artifact_sha256}",
            "lineage_id": lineage_id,
        },
        "conflict_evidence": None,
        "gate": {"outcome": "passed", "failures": []},
        "next_escalation": None,
        "skipped_after_acceptance": [],
        "unattempted_routes": [],
    }
    planner_inputs = {
        "request_identity": {
            "claim_id": claim_id,
            "request_scope_fingerprint": scope_fingerprint,
            "request_content_sha256": canonical_sha256(request),
        },
        "source_function": "market-size",
        "maintained_profiles": [
            {
                "source_id": "official-market-data",
                "content_sha256": canonical_sha256(
                    {
                        "id": "official-market-data",
                        "fixture_version": "1",
                    }
                ),
            }
        ],
        "relation_records": [],
        "bound_routes": [],
        "as_of": request["as_of"],
        "effective_planning_time": "2026-08-02T00:00:00+00:00",
        "vocabulary_identity": {
            "content_sha256": canonical_sha256({"market-size": ["market size"]})
        },
        "reachability_identity": {"content_sha256": canonical_sha256({})},
        "route_inventory_sha256": canonical_sha256([route]),
    }
    receipt_content = {
        "schema_version": "1.0",
        "claim_id": claim_id,
        "request_scope_fingerprint": scope_fingerprint,
        "planner_inputs": planner_inputs,
        "planner_input_fingerprint": canonical_sha256(planner_inputs),
        "route_inventory": [route],
    }
    receipt_sha256 = canonical_sha256(receipt_content)
    return {
        claim_id: {
            "request": request,
            "planner_inventory_receipt": {
                **receipt_content,
                "content_sha256": receipt_sha256,
            },
            "ledger": ledger,
            "accepted_candidate": {
                "claim_id": claim_id,
                "request_scope_fingerprint": scope_fingerprint,
                "candidate_document_id": "CCP-POP-TOY-2025",
                "artifact_identity": f"sha256:{artifact_sha256}",
                "artifact_sha256": artifact_sha256,
                "source_document_identity": {
                    "binding_sha256": binding_sha256,
                },
                "lineage_id": lineage_id,
                "consuming_section_ids": ["part1/§1.3"],
            },
        }
    }


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def rehash_receipt_content(receipt: dict[str, object]) -> None:
    receipt["content_sha256"] = canonical_sha256(
        {key: value for key, value in receipt.items() if key != "content_sha256"}
    )


def rehash_planner_inputs(receipt: dict[str, object]) -> None:
    planner_inputs = receipt["planner_inputs"]
    assert isinstance(planner_inputs, dict)
    receipt["planner_input_fingerprint"] = canonical_sha256(planner_inputs)
    rehash_receipt_content(receipt)


@pytest.mark.parametrize("mutation", ("modified", "omitted"))
def test_run_store_rejects_modified_or_omitted_planner_inputs(
    mutation: str,
) -> None:
    wrapper = research_ledger_wrapper()
    entry = wrapper["cn-pop-toy-market-2020-2025"]
    receipt = entry["planner_inventory_receipt"]
    planner_inputs = receipt["planner_inputs"]
    if mutation == "modified":
        planner_inputs["source_function"] = "invented-source-function"
    else:
        planner_inputs["maintained_profiles"].clear()
    rehash_receipt_content(receipt)

    with pytest.raises(RunStoreError, match="run-store planner input fingerprint"):
        run_store.validate_research_ledger_wrapper(wrapper)


def test_run_store_rejects_invented_fingerprint_after_content_rehash() -> None:
    wrapper = research_ledger_wrapper()
    entry = wrapper["cn-pop-toy-market-2020-2025"]
    receipt = entry["planner_inventory_receipt"]
    receipt["planner_input_fingerprint"] = "0" * 64
    rehash_receipt_content(receipt)

    with pytest.raises(RunStoreError, match="run-store planner input fingerprint"):
        run_store.validate_research_ledger_wrapper(wrapper)


def test_run_store_rejects_receipt_scope_mismatch_with_wrapper_request() -> None:
    wrapper = research_ledger_wrapper()
    entry = wrapper["cn-pop-toy-market-2020-2025"]
    entry["request"]["product_scope"] = "all collectible toys"

    with pytest.raises(
        RunStoreError,
        match="receipt request scope does not match wrapper request",
    ):
        run_store.validate_research_ledger_wrapper(wrapper)


def test_persistence_rejects_reduced_inventory_with_stale_fingerprint(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    wrapper = research_ledger_wrapper()
    entry = wrapper["cn-pop-toy-market-2020-2025"]
    later_route = {
        "route_id": "layer-4-industry-overview",
        "route_layer": 4,
        "subject_relation": "document-type-expansion",
        "document_type": "industry-overview",
    }
    entry["ledger"]["applicable_routes"].append(later_route)
    entry["ledger"]["skipped_after_acceptance"].append(
        {
            "route_id": later_route["route_id"],
            "route_layer": later_route["route_layer"],
            "reason": "gate passed before later layer",
        }
    )
    receipt = entry["planner_inventory_receipt"]
    receipt["route_inventory"].append(later_route)
    planner_inputs = receipt["planner_inputs"]
    planner_inputs["route_inventory_sha256"] = canonical_sha256(receipt["route_inventory"])
    rehash_planner_inputs(receipt)

    entry["ledger"]["applicable_routes"].pop()
    entry["ledger"]["skipped_after_acceptance"].pop()
    receipt["route_inventory"].pop()
    planner_inputs["route_inventory_sha256"] = canonical_sha256(receipt["route_inventory"])
    rehash_receipt_content(receipt)

    with pytest.raises(RunStoreError, match="run-store planner input fingerprint"):
        run_store.bind_research_ledger(
            root,
            "600519.SH",
            resolution.run_id,
            wrapper,
        )


def test_research_ledger_persistence_rejects_accepted_absence_route_bypass(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    wrapper = research_ledger_wrapper()
    entry = wrapper["cn-pop-toy-market-2020-2025"]
    entry["request"]["absence_claim"] = True
    entry["ledger"]["absence_claim"] = True
    later_route = {
        "route_id": "layer-4-industry-overview",
        "route_layer": 4,
        "subject_relation": "document-type-expansion",
        "document_type": "industry-overview",
    }
    entry["ledger"]["applicable_routes"].append(later_route)
    entry["ledger"]["skipped_after_acceptance"] = [
        {
            "route_id": later_route["route_id"],
            "route_layer": later_route["route_layer"],
            "reason": "gate passed before later layer",
        }
    ]
    receipt = entry["planner_inventory_receipt"]
    receipt["route_inventory"].append(later_route)
    planner_inputs = receipt["planner_inputs"]
    planner_inputs["request_identity"]["request_content_sha256"] = canonical_sha256(
        entry["request"]
    )
    planner_inputs["route_inventory_sha256"] = canonical_sha256(receipt["route_inventory"])
    rehash_planner_inputs(receipt)

    with pytest.raises(RunStoreError, match="accepted absence ledger cannot skip routes"):
        run_store.bind_research_ledger(
            root,
            "600519.SH",
            resolution.run_id,
            wrapper,
        )


@pytest.mark.parametrize("mutation", ("ledger-omits-later-route", "receipt-tampered"))
def test_research_ledger_persistence_rejects_modified_planner_inventory_receipt(
    tmp_path: Path,
    mutation: str,
) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    wrapper = research_ledger_wrapper()
    entry = wrapper["cn-pop-toy-market-2020-2025"]
    receipt = entry["planner_inventory_receipt"]
    later_route = {
        "route_id": "layer-4-industry-overview",
        "route_layer": 4,
        "subject_relation": "document-type-expansion",
        "document_type": "industry-overview",
    }
    receipt["route_inventory"].append(later_route)
    planner_inputs = receipt["planner_inputs"]
    planner_inputs["route_inventory_sha256"] = canonical_sha256(receipt["route_inventory"])
    receipt["planner_input_fingerprint"] = canonical_sha256(planner_inputs)
    if mutation == "ledger-omits-later-route":
        rehash_receipt_content(receipt)

    expected = (
        "does not match planner route inventory"
        if mutation == "ledger-omits-later-route"
        else "content SHA-256"
    )
    with pytest.raises(RunStoreError, match=expected):
        run_store.bind_research_ledger(
            root,
            "600519.SH",
            resolution.run_id,
            wrapper,
        )


def test_research_ledger_wrapper_validates_nested_claim_contracts() -> None:
    wrapper = research_ledger_wrapper()

    run_store.validate_research_ledger_wrapper(wrapper)

    claim = wrapper["cn-pop-toy-market-2020-2025"]
    claim["ledger"]["gate"] = {"outcome": "failed", "failures": ["scope"]}
    with pytest.raises(RunStoreError, match="accepted ledger requires a passed gate"):
        run_store.validate_research_ledger_wrapper(wrapper)

    invalid_handoff = research_ledger_wrapper()
    accepted_candidate = invalid_handoff["cn-pop-toy-market-2020-2025"]["accepted_candidate"]
    accepted_candidate["artifact_sha256"] = "4" * 64
    with pytest.raises(RunStoreError, match="artifact identity"):
        run_store.validate_research_ledger_wrapper(invalid_handoff)


def test_research_ledger_binding_is_singleton_fixed_and_resumable(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    assert resolution.run_path is not None
    wrapper = research_ledger_wrapper()

    binding = run_store.bind_research_ledger(
        root,
        "600519.SH",
        resolution.run_id,
        wrapper,
    )

    expected_path = (resolution.run_path / "logs" / "research-ledger.json").resolve()
    checkpoint = json.loads((resolution.run_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert set(checkpoint["research_ledger"]) == {"artifact_id", "path", "sha256"}
    assert checkpoint["research_ledger"] == {
        "artifact_id": binding.artifact_id,
        "path": str(expected_path),
        "sha256": binding.sha256,
    }
    assert binding.path == expected_path
    assert list((resolution.run_path / "logs").glob("research-ledger*.json")) == [expected_path]
    assert (
        run_store.load_research_ledger(
            root,
            "600519.SH",
            resolution.run_id,
        )
        == wrapper
    )

    updated_wrapper = json.loads(json.dumps(wrapper))
    accepted_candidate = updated_wrapper["cn-pop-toy-market-2020-2025"]["accepted_candidate"]
    accepted_candidate["consuming_section_ids"].append("part2/§2.1")
    updated_binding = run_store.bind_research_ledger(
        root,
        "600519.SH",
        resolution.run_id,
        updated_wrapper,
        expected_prior_sha256=binding.sha256,
    )
    assert updated_binding.path == expected_path
    assert updated_binding.artifact_id != binding.artifact_id
    assert list((resolution.run_path / "logs").glob("research-ledger*.json")) == [expected_path]
    assert (
        run_store.load_research_ledger(
            root,
            "600519.SH",
            resolution.run_id,
        )
        == updated_wrapper
    )


def test_research_ledger_update_uses_compare_and_swap(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    initial = run_store.bind_research_ledger(
        root,
        "600519.SH",
        resolution.run_id,
        research_ledger_wrapper(),
    )
    first_writer = research_ledger_wrapper()
    first_writer["cn-pop-toy-market-2020-2025"]["accepted_candidate"][
        "consuming_section_ids"
    ].append("part2/§2.1")
    stale_writer = research_ledger_wrapper()
    stale_writer["cn-pop-toy-market-2020-2025"]["accepted_candidate"][
        "consuming_section_ids"
    ].append("part3/§3.1")

    first_binding = run_store.bind_research_ledger(
        root,
        "600519.SH",
        resolution.run_id,
        first_writer,
        expected_prior_sha256=initial.sha256,
    )
    with pytest.raises(RunStoreError, match="expected prior SHA-256"):
        run_store.bind_research_ledger(
            root,
            "600519.SH",
            resolution.run_id,
            stale_writer,
            expected_prior_sha256=initial.sha256,
        )

    assert (
        run_store.load_research_ledger(
            root,
            "600519.SH",
            resolution.run_id,
        )
        == first_writer
    )
    checkpoint = json.loads((resolution.run_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["research_ledger"]["sha256"] == first_binding.sha256


def test_research_ledger_resume_rejects_tampering_without_rebuild(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    binding = run_store.bind_research_ledger(
        root,
        "600519.SH",
        resolution.run_id,
        research_ledger_wrapper(),
    )
    binding.path.write_text('{"tampered":true}\n', encoding="utf-8")
    tampered = binding.path.read_bytes()

    with pytest.raises(RunStoreError, match="SHA-256 mismatch"):
        run_store.load_research_ledger(root, "600519.SH", resolution.run_id)

    assert binding.path.read_bytes() == tampered


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("extra-binding-field", "exactly"),
        ("relative-path", "absolute"),
        ("outside-run", "fixed run path"),
        ("missing-file", "missing"),
    ),
)
def test_research_ledger_resume_rejects_invalid_checkpoint_binding(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    assert resolution.run_path is not None
    binding = run_store.bind_research_ledger(
        root,
        "600519.SH",
        resolution.run_id,
        research_ledger_wrapper(),
    )
    checkpoint_path = resolution.run_path / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if corruption == "extra-binding-field":
        checkpoint["research_ledger"]["claim_id"] = "forged"
    elif corruption == "relative-path":
        checkpoint["research_ledger"]["path"] = "logs/research-ledger.json"
    elif corruption == "outside-run":
        outside = tmp_path / "research-ledger.json"
        outside.write_bytes(binding.path.read_bytes())
        checkpoint["research_ledger"]["path"] = str(outside.resolve())
    else:
        binding.path.unlink()
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(RunStoreError, match=message):
        run_store.load_research_ledger(root, "600519.SH", resolution.run_id)


def test_research_ledger_binding_rejects_non_value_profile_run(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve(root)
    assert resolution.run_id is not None

    with pytest.raises(RunStoreError, match="value-profile"):
        run_store.bind_research_ledger(
            root,
            "600519.SH",
            resolution.run_id,
            research_ledger_wrapper(),
        )


def test_research_ledger_cli_binds_and_validates_wrapper(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    wrapper_path = tmp_path / "wrapper.json"
    wrapper_path.write_text(json.dumps(research_ledger_wrapper()), encoding="utf-8")

    bound = subprocess.run(
        [
            sys.executable,
            "scripts/financial_run_store.py",
            "bind-research-ledger",
            "--root",
            str(root),
            "--ticker",
            "600519.SH",
            "--run-id",
            resolution.run_id,
            "--wrapper",
            str(wrapper_path),
            "--expected-prior-sha256",
            "create-only",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    validated = subprocess.run(
        [
            sys.executable,
            "scripts/financial_run_store.py",
            "validate-research-ledger",
            "--root",
            str(root),
            "--ticker",
            "600519.SH",
            "--run-id",
            resolution.run_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(bound.stdout)["path"].endswith("/logs/research-ledger.json")
    assert json.loads(validated.stdout) == {
        "claim_ids": ["cn-pop-toy-market-2020-2025"],
        "run_id": resolution.run_id,
        "status": "valid",
    }


def test_research_ledger_cli_requires_expected_prior_sha256(tmp_path: Path) -> None:
    root = tmp_path / "data" / "filings"
    resolution = resolve_value_profile(root)
    assert resolution.run_id is not None
    assert resolution.run_path is not None
    wrapper_path = tmp_path / "wrapper.json"
    wrapper_path.write_text(json.dumps(research_ledger_wrapper()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/financial_run_store.py",
            "bind-research-ledger",
            "--root",
            str(root),
            "--ticker",
            "600519.SH",
            "--run-id",
            resolution.run_id,
            "--wrapper",
            str(wrapper_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--expected-prior-sha256" in result.stderr
    assert not (resolution.run_path / "logs" / "research-ledger.json").exists()


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
