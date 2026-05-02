"""ChatSession — JSONL-persisted conversation history."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class ChatTurn:
    """One turn in a conversation."""

    role: Literal["user", "assistant", "tool_result"]
    content: str
    tool_name: str | None = None
    tool_use_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ChatSession:
    """A persisted conversation."""

    session_id: str
    anchor_symbol: str | None
    model: str
    path: Path
    turns: list[ChatTurn] = field(default_factory=list)

    # ── factories ────────────────────────────────────────────────────────

    @classmethod
    def new(
        cls,
        anchor: str | None,
        model: str,
        root: Path,
    ) -> ChatSession:
        """Create a new session, initializing its JSONL file with a header."""
        root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        slug_anchor = anchor.replace(".", "-").lower() if anchor else "general"
        session_id = f"{ts}-{slug_anchor}"
        path = root / f"{session_id}.jsonl"
        # Header line: session metadata
        header = {
            "_meta": True,
            "session_id": session_id,
            "anchor_symbol": anchor,
            "model": model,
        }
        path.write_text(json.dumps(header) + "\n")
        return cls(
            session_id=session_id,
            anchor_symbol=anchor,
            model=model,
            path=path,
            turns=[],
        )

    @classmethod
    def load(cls, path: Path) -> ChatSession:
        """Load an existing session from its JSONL file."""
        lines = path.read_text().splitlines()
        if not lines:
            raise ValueError(f"Empty session file: {path}")

        header = json.loads(lines[0])
        if not header.get("_meta"):
            raise ValueError(f"Session file missing header: {path}")

        turns: list[ChatTurn] = []
        for raw in lines[1:]:
            if not raw.strip():
                continue
            data = json.loads(raw)
            turns.append(
                ChatTurn(
                    role=data["role"],
                    content=data["content"],
                    tool_name=data.get("tool_name"),
                    tool_use_id=data.get("tool_use_id"),
                    timestamp=data.get("timestamp", ""),
                )
            )

        return cls(
            session_id=header["session_id"],
            anchor_symbol=header.get("anchor_symbol"),
            model=header["model"],
            path=path,
            turns=turns,
        )

    # ── mutation ─────────────────────────────────────────────────────────

    def append(self, turn: ChatTurn) -> None:
        """Append a turn and flush it to disk atomically."""
        self.turns.append(turn)
        line = json.dumps(_asdict_no_none(turn), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _asdict_no_none(turn: ChatTurn) -> dict[str, Any]:
    """Drop null-valued optional fields for tidier JSONL."""
    data = asdict(turn)
    return {k: v for k, v in data.items() if v is not None}
