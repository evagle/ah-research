from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ah_research.chat.chat import ResearchChat
from ah_research.chat.session import ChatSession
from ah_research.chat.tools import ChatDeps


def _mock_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _mock_tool_use_block(
    name: str, input_: dict[str, object], tool_use_id: str = "tu_1"
) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_
    block.id = tool_use_id
    return block


def _mock_response(content_blocks: list[MagicMock]) -> MagicMock:
    resp = MagicMock()
    resp.content = content_blocks
    return resp


def _make_chat(tmp_path: Path, client: MagicMock) -> ResearchChat:
    session = ChatSession.new(anchor="600519.SH", model="claude-sonnet-4-6", root=tmp_path)
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    return ResearchChat(session=session, deps=deps, client=client, max_iterations=5)


def test_send_single_turn_no_tool_use(tmp_path: Path) -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        [_mock_text_block("Moutai is a premium baijiu producer.")]
    )
    chat = _make_chat(tmp_path, client)
    answer = chat.send("Tell me about Moutai")
    assert "Moutai" in answer
    assert client.messages.create.call_count == 1
    # Session has 2 turns: user + assistant
    assert len(chat.session.turns) == 2


def test_send_two_round_tool_use(tmp_path: Path) -> None:
    client = MagicMock()
    # Round 1: tool_use block
    tool_use_resp = _mock_response([_mock_tool_use_block("list_universe", {}, tool_use_id="tu_1")])
    # Round 2: final text
    final_resp = _mock_response([_mock_text_block("Found 2 symbols.")])
    client.messages.create.side_effect = [tool_use_resp, final_resp]

    chat = _make_chat(tmp_path, client)
    # Mock list_universe to return something
    chat.deps.filings_repo.list_symbols.return_value = ["600519.SH", "000001.SZ"]
    chat.deps.profile_repo.list_symbols.return_value = ["600519.SH"]

    answer = chat.send("How many symbols?")
    assert "2" in answer
    assert client.messages.create.call_count == 2


def test_send_max_iterations_exceeded(tmp_path: Path) -> None:
    client = MagicMock()
    # Infinite loop of tool_use
    client.messages.create.return_value = _mock_response(
        [_mock_tool_use_block("list_universe", {}, tool_use_id="tu_loop")]
    )
    chat = _make_chat(tmp_path, client)
    chat.deps.filings_repo.list_symbols.return_value = []
    chat.deps.profile_repo.list_symbols.return_value = []

    with pytest.raises(RuntimeError, match=r"Max iterations"):
        chat.send("loop forever")


def test_send_persists_tool_results(tmp_path: Path) -> None:
    client = MagicMock()
    tool_use_resp = _mock_response([_mock_tool_use_block("list_universe", {}, tool_use_id="tu_a")])
    final_resp = _mock_response([_mock_text_block("done")])
    client.messages.create.side_effect = [tool_use_resp, final_resp]

    chat = _make_chat(tmp_path, client)
    chat.deps.filings_repo.list_symbols.return_value = []
    chat.deps.profile_repo.list_symbols.return_value = []

    chat.send("anything")

    # Session has: user, tool_result, assistant
    roles = [t.role for t in chat.session.turns]
    assert "tool_result" in roles
    tool_turn = next(t for t in chat.session.turns if t.role == "tool_result")
    assert tool_turn.tool_name == "list_universe"
    assert tool_turn.tool_use_id == "tu_a"
