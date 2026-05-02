"""ResearchChat — tool-use conversational orchestrator."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from ah_research.chat.session import ChatSession, ChatTurn
from ah_research.chat.tools import TOOLS, ChatDeps, handle_tool

if TYPE_CHECKING:
    import anthropic as _anthropic


_SYSTEM_PROMPT = """\
You are a research assistant for the ah-research platform. You answer questions
about A-share and HK-share companies using the platform's structured tools.

RULES:
- Always cite concrete data by tool name and ticker (e.g. "per get_graded_profile for
  600519.SH, moat_grade=A"). Do not invent data.
- When the user mentions an anchor ticker, prefer tools that operate on it.
- For portfolio questions, use construct_portfolio rather than explaining theory.
- For text-heavy questions (profile sections, filings), call get_profile_markdown
  or search_filings with a narrow query.
- Numeric answers should include units or a percent sign.
- Keep responses under ~400 words unless asked for depth.

Anchor ticker (if set): {anchor}
"""


class ResearchChat:
    """Tool-use conversational agent over the ah-research data platform."""

    def __init__(
        self,
        session: ChatSession,
        deps: ChatDeps,
        *,
        client: _anthropic.Anthropic | None = None,
        max_tokens: int = 2048,
        max_iterations: int = 10,
    ) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.session = session
        self.deps = deps
        self.max_tokens = max_tokens
        self.max_iterations = max_iterations

    # ------------------------------------------------------------------

    def send(self, user_text: str) -> str:
        """Run one turn end-to-end. Returns the assistant's final text."""
        # Record user turn first so --resume works even if the API fails
        self.session.append(ChatTurn(role="user", content=user_text))

        messages: list[dict[str, Any]] = self._build_messages()
        system_block: dict[str, Any] = {
            "type": "text",
            "text": _SYSTEM_PROMPT.format(anchor=self.session.anchor_symbol or "none"),
            "cache_control": {"type": "ephemeral"},
        }

        for _ in range(self.max_iterations):
            # The SDK's TypedDicts for system/tools/messages are very strict;
            # our dict shapes match the API but don't satisfy the TypedDicts.
            # cast() to Any keeps both mypy 1.10 (pre-commit hook, no SDK
            # installed) and mypy 1.20 (dev, SDK installed) happy.
            resp = self.client.messages.create(
                model=self.session.model,
                max_tokens=self.max_tokens,
                system=cast(Any, [system_block]),
                tools=cast(Any, TOOLS),
                messages=cast(Any, messages),
            )
            # Attach assistant message (raw content) to history
            messages.append({"role": "assistant", "content": resp.content})

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                # Final text response
                text_parts = [b.text for b in resp.content if b.type == "text"]
                answer = "".join(text_parts)
                self.session.append(ChatTurn(role="assistant", content=answer))
                return answer

            # Execute all tool_use blocks in this response
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                result = handle_tool(tu.name, tu.input, self.deps)
                result_json = json.dumps(result, ensure_ascii=False, default=str)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result_json,
                    }
                )
                self.session.append(
                    ChatTurn(
                        role="tool_result",
                        content=result_json,
                        tool_name=tu.name,
                        tool_use_id=tu.id,
                    )
                )
            messages.append({"role": "user", "content": tool_results})

        raise RuntimeError(f"Max iterations ({self.max_iterations}) exceeded without final answer")

    # ------------------------------------------------------------------

    def _build_messages(self) -> list[dict[str, Any]]:
        """Rebuild the message list from the session history for a new turn.

        Tool_result turns reconstruct to user-role messages with tool_result blocks;
        user/assistant text turns become their natural role messages.
        """
        messages: list[dict[str, Any]] = []
        i = 0
        turns = self.session.turns
        while i < len(turns):
            t = turns[i]
            if t.role == "user":
                messages.append({"role": "user", "content": t.content})
                i += 1
            elif t.role == "assistant":
                messages.append({"role": "assistant", "content": t.content})
                i += 1
            elif t.role == "tool_result":
                # Collect consecutive tool_result turns into one user message
                batch = []
                while i < len(turns) and turns[i].role == "tool_result":
                    batch.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": turns[i].tool_use_id,
                            "content": turns[i].content,
                        }
                    )
                    i += 1
                messages.append({"role": "user", "content": batch})
            else:
                i += 1
        return messages


__all__ = ["ResearchChat"]
