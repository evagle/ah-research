from __future__ import annotations

import json
from pathlib import Path

from ah_research.chat.session import ChatSession, ChatTurn


def test_chat_session_new_creates_file(tmp_path: Path) -> None:
    session = ChatSession.new(anchor="600519.SH", model="claude-sonnet-4-6", root=tmp_path)
    assert session.session_id.endswith("-600519-sh") or "600519.SH" in session.session_id
    assert session.path.exists()
    assert session.path.parent == tmp_path
    assert session.anchor_symbol == "600519.SH"
    assert session.model == "claude-sonnet-4-6"
    assert session.turns == []


def test_chat_session_new_without_anchor(tmp_path: Path) -> None:
    session = ChatSession.new(anchor=None, model="claude-haiku-4-5-20251001", root=tmp_path)
    assert session.anchor_symbol is None
    assert session.path.exists()


def test_chat_session_append_persists(tmp_path: Path) -> None:
    session = ChatSession.new(anchor=None, model="claude-sonnet-4-6", root=tmp_path)
    session.append(ChatTurn(role="user", content="hello"))
    session.append(ChatTurn(role="assistant", content="hi there"))

    # File contains header + two JSONL lines
    lines = session.path.read_text().strip().splitlines()
    # header + 2 turns = 3 lines
    assert len(lines) == 3
    assert json.loads(lines[1])["role"] == "user"
    assert json.loads(lines[2])["role"] == "assistant"


def test_chat_session_load_round_trips(tmp_path: Path) -> None:
    session = ChatSession.new(anchor="000001.SZ", model="claude-sonnet-4-6", root=tmp_path)
    session.append(ChatTurn(role="user", content="what is the signal?"))
    session.append(
        ChatTurn(
            role="tool_result",
            content='{"signal": 0.5}',
            tool_name="get_screener_row",
            tool_use_id="tu_123",
        )
    )
    session.append(ChatTurn(role="assistant", content="signal is 0.5"))

    loaded = ChatSession.load(session.path)
    assert loaded.session_id == session.session_id
    assert loaded.anchor_symbol == "000001.SZ"
    assert loaded.model == "claude-sonnet-4-6"
    assert len(loaded.turns) == 3
    assert loaded.turns[1].tool_name == "get_screener_row"
    assert loaded.turns[1].tool_use_id == "tu_123"
