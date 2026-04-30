"""Real-API smoke test for Phase 5 ResearchChat (slow-marked, opt-in)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.slow


def test_chat_single_turn_real_api(tmp_path: Path) -> None:
    """One real-API chat turn. Skipped if ANTHROPIC_API_KEY unset."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    pytest.importorskip("anthropic")

    from ah_research.chat.chat import ResearchChat
    from ah_research.chat.session import ChatSession
    from ah_research.chat.tools import ChatDeps

    fake_filings_repo = MagicMock()
    fake_filings_repo.list_symbols.return_value = ["600519.SH"]
    fake_profile_repo = MagicMock()
    fake_profile_repo.list_symbols.return_value = ["600519.SH"]

    session = ChatSession.new(anchor="600519.SH", model="claude-haiku-4-5-20251001", root=tmp_path)
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=fake_filings_repo,
        profile_repo=fake_profile_repo,
        profile_grader=None,
    )
    chat = ResearchChat(session=session, deps=deps, max_iterations=3)
    answer = chat.send("Call the list_universe tool and tell me how many symbols there are.")
    # Should mention 1 symbol from list_universe
    assert len(answer) > 0
    assert "1" in answer or "600519" in answer
