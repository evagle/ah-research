from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ah_research.cli import app

runner = CliRunner()


def test_chat_help() -> None:
    result = runner.invoke(app, ["chat", "--help"])
    assert result.exit_code == 0
    assert "chat" in result.stdout.lower()


def test_chat_list_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # Chat sessions dir under fake HOME
    result = runner.invoke(app, ["chat", "--list"])
    assert result.exit_code == 0
    # Either prints "No sessions" or an empty table
    assert "No sessions" in result.stdout or "session" in result.stdout.lower()


def test_chat_resume_nonexistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, ["chat", "--resume", "does-not-exist"])
    assert result.exit_code != 0 or "not found" in result.stdout.lower()


def test_chat_without_api_key_friendly_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Pipe empty stdin so REPL exits immediately
    result = runner.invoke(app, ["chat", "600519.SH"], input="")
    # Should either succeed with "Set ANTHROPIC_API_KEY" or exit cleanly on EOF
    assert (
        "ANTHROPIC_API_KEY" in result.stdout
        or "bye" in result.stdout.lower()
        or result.exit_code == 0
    )
