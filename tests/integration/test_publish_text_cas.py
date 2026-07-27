from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "publish_text_cas.py"


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def test_publish_text_cas_replaces_expected_baseline(tmp_path):
    target = tmp_path / "profile.md"
    source = tmp_path / "draft.md"
    original = b"original\n"
    target.write_bytes(original)
    source.write_text("updated\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--target",
            str(target),
            "--expected-sha256",
            _sha256(original),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8") == "updated\n"
    assert result.stdout.strip() == _sha256(b"updated\n")


def test_publish_text_cas_rejects_stale_baseline_without_overwrite(tmp_path):
    target = tmp_path / "profile.md"
    source = tmp_path / "draft.md"
    target.write_text("concurrent update\n", encoding="utf-8")
    source.write_text("stale draft\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--target",
            str(target),
            "--expected-sha256",
            _sha256(b"older baseline\n"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "baseline hash mismatch" in result.stderr
    assert target.read_text(encoding="utf-8") == "concurrent update\n"


def test_publish_text_cas_recovers_from_lock_file_left_by_dead_process(tmp_path):
    target = tmp_path / "profile.md"
    source = tmp_path / "draft.md"
    original = b"original\n"
    target.write_bytes(original)
    source.write_text("updated\n", encoding="utf-8")
    target.with_name(f".{target.name}.lock").write_text(
        "stale lock from terminated process\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--target",
            str(target),
            "--expected-sha256",
            _sha256(original),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8") == "updated\n"


def test_publish_text_cas_rejects_changed_guard(tmp_path):
    target = tmp_path / "profile.md"
    source = tmp_path / "draft.md"
    guard = tmp_path / "annual.json"
    target.write_text("original\n", encoding="utf-8")
    source.write_text("updated\n", encoding="utf-8")
    guard.write_text("changed\n", encoding="utf-8")
    expected_guard = _sha256(b"expected\n")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--target",
            str(target),
            "--expected-sha256",
            _sha256(b"original\n"),
            "--guard",
            f"{guard}:{expected_guard}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "guard hash mismatch" in result.stderr
    assert target.read_text(encoding="utf-8") == "original\n"


def test_publish_text_cas_rolls_back_when_guard_changes_during_replace(
    tmp_path,
    monkeypatch,
):
    spec = importlib.util.spec_from_file_location("publish_text_cas", SCRIPT)
    assert spec is not None and spec.loader is not None
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)

    target = tmp_path / "profile.md"
    source = tmp_path / "draft.md"
    guard = tmp_path / "annual.json"
    original = b"original\n"
    expected_guard = b"expected\n"
    target.write_bytes(original)
    source.write_text("updated\n", encoding="utf-8")
    guard.write_bytes(expected_guard)
    real_exchange = publisher._exchange_paths
    injected = False

    def exchange_with_guard_race(source_path, target_path):
        nonlocal injected
        if Path(target_path) == target and not injected:
            injected = True
            guard.write_text("concurrent evidence\n", encoding="utf-8")
        return real_exchange(source_path, target_path)

    monkeypatch.setattr(publisher, "_exchange_paths", exchange_with_guard_race)

    with pytest.raises(publisher.PublishError, match="guard changed during publication"):
        publisher.publish_text(
            source,
            target,
            _sha256(original),
            [(guard, _sha256(expected_guard))],
        )

    assert target.read_bytes() == original


def test_publish_text_cas_does_not_overwrite_target_changed_after_baseline_check(
    tmp_path,
    monkeypatch,
):
    spec = importlib.util.spec_from_file_location("publish_text_cas", SCRIPT)
    assert spec is not None and spec.loader is not None
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)

    target = tmp_path / "profile.md"
    source = tmp_path / "draft.md"
    original = b"original\n"
    concurrent = b"concurrent update\n"
    target.write_bytes(original)
    source.write_text("updated\n", encoding="utf-8")
    real_exchange = publisher._exchange_paths
    injected = False

    def exchange_after_baseline_check(source_path, target_path):
        nonlocal injected
        if Path(target_path) == target and not injected:
            injected = True
            target.write_bytes(concurrent)
        return real_exchange(source_path, target_path)

    monkeypatch.setattr(
        publisher,
        "_exchange_paths",
        exchange_after_baseline_check,
    )

    with pytest.raises(publisher.PublishError):
        publisher.publish_text(source, target, _sha256(original))

    assert target.read_bytes() == concurrent


def test_guard_rollback_does_not_overwrite_post_publish_concurrent_edit(
    tmp_path,
    monkeypatch,
):
    spec = importlib.util.spec_from_file_location("publish_text_cas", SCRIPT)
    assert spec is not None and spec.loader is not None
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)

    target = tmp_path / "profile.md"
    source = tmp_path / "draft.md"
    guard = tmp_path / "annual.json"
    original = b"original\n"
    expected_guard = b"expected\n"
    concurrent = b"post-publish concurrent edit\n"
    target.write_bytes(original)
    source.write_text("updated\n", encoding="utf-8")
    guard.write_bytes(expected_guard)
    real_exchange = publisher._exchange_paths
    injected = False

    def exchange_then_edit_before_rollback(source_path, target_path):
        nonlocal injected
        result = real_exchange(source_path, target_path)
        if Path(target_path) == target and not injected:
            injected = True
            guard.write_text("concurrent evidence\n", encoding="utf-8")
            target.write_bytes(concurrent)
        return result

    monkeypatch.setattr(
        publisher,
        "_exchange_paths",
        exchange_then_edit_before_rollback,
    )

    with pytest.raises(
        publisher.PublishError,
        match="guard changed during publication",
    ):
        publisher.publish_text(
            source,
            target,
            _sha256(original),
            [(guard, _sha256(expected_guard))],
        )

    assert target.read_bytes() == concurrent
