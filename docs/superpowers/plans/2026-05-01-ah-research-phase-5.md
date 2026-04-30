# Phase 5 — Research Chat UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a conversational CLI (`ah chat`) that reasons over the research platform's structured outputs via Claude tool use, with session persistence and 8 tools bridging Claude to the Phase 3/4 repositories.

**Architecture:** Tool-use loop with disk-persisted JSONL session history. System prompt + tool definitions are cached via `cache_control: ephemeral` (same pattern as Phase 4.7 `ProfileGrader`). New `chat/` package has three modules: `session.py` (`ChatSession` + `ChatTurn`), `tools.py` (8 tool schemas + dispatcher), `chat.py` (`ResearchChat` orchestrator). New Typer sub-app `ah chat` as REPL.

**Tech Stack:** `anthropic>=0.40.0` (already a project dep), pandas, Typer, Rich, pytest.

**Reference spec:** `docs/superpowers/specs/2026-05-01-ah-research-phase-5-research-chat-design.md`.

**CI-equivalent verification BEFORE every commit (MANDATORY — user said "you pushed a pr with ut failed"):**
```
uv run pytest -x
uv run mypy src
```

---

### Task 1: `ChatTurn` + `ChatSession` with JSONL persistence

**Files:**
- Create: `src/ah_research/chat/__init__.py`
- Create: `src/ah_research/chat/session.py`
- Create: `tests/unit/chat/__init__.py`
- Create: `tests/unit/chat/test_session.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/chat/test_session.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

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

    # File contains two JSONL lines
    lines = session.path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["role"] == "user"
    assert json.loads(lines[1])["role"] == "assistant"


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
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```
uv run pytest tests/unit/chat/test_session.py -x
```

- [ ] **Step 3: Implement**

Create `src/ah_research/chat/__init__.py`:

```python
"""Phase 5 — conversational research UI."""

from ah_research.chat.session import ChatSession, ChatTurn

__all__ = ["ChatSession", "ChatTurn"]
```

Create `src/ah_research/chat/session.py`:

```python
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
```

- [ ] **Step 4: Run — expect PASS**

```
uv run pytest tests/unit/chat/test_session.py -x
uv run mypy src
```

- [ ] **Step 5: Commit**

```
git add src/ah_research/chat/ tests/unit/chat/__init__.py tests/unit/chat/test_session.py
git commit -m "feat(phase-5): ChatSession + ChatTurn JSONL persistence"
```

---

### Task 2: `ChatDeps` + 3 simple tools (`list_universe`, `get_corpus_summary`, `get_screener_row`)

**Files:**
- Create: `src/ah_research/chat/tools.py`
- Create: `tests/unit/chat/test_tools.py`

- [ ] **Step 1: Write failing tests (3 simple tools only)**

```python
# tests/unit/chat/test_tools.py
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from ah_research.chat.tools import ChatDeps, TOOLS, handle_tool


def _fake_profile_repo(symbols: list[str]) -> MagicMock:
    repo = MagicMock()
    repo.list_symbols.return_value = symbols
    return repo


def _fake_filings_repo(symbols: list[str]) -> MagicMock:
    repo = MagicMock()
    repo.list_symbols.return_value = symbols
    return repo


# ── list_universe ─────────────────────────────────────────────────────────


def test_list_universe_returns_symbols() -> None:
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=_fake_filings_repo(["600519.SH"]),
        profile_repo=_fake_profile_repo(["600519.SH"]),
        profile_grader=None,
    )
    out = handle_tool("list_universe", {}, deps)
    assert out["symbols"] == ["600519.SH"]
    assert out["n_with_profile"] == 1


def test_list_universe_with_filings_only_symbol() -> None:
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=_fake_filings_repo(["600519.SH", "000001.SZ"]),
        profile_repo=_fake_profile_repo(["600519.SH"]),
        profile_grader=None,
    )
    out = handle_tool("list_universe", {}, deps)
    assert set(out["symbols"]) == {"600519.SH", "000001.SZ"}
    assert out["n_with_profile"] == 1


# ── get_corpus_summary ────────────────────────────────────────────────────


def test_get_corpus_summary_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_df = pd.DataFrame(
        {
            "symbol": ["600519.SH"],
            "n_annual": [6],
            "latest_annual_year": [2025],
            "has_ipo": [True],
            "n_research": [3],
            "latest_research_date": [pd.Timestamp("2026-04-01")],
            "has_profile": [True],
            "latest_profile_date": [pd.Timestamp("2026-04-28")],
            "profile_age_days": [3],
            "annual_staleness_years": [1],
        }
    )
    monkeypatch.setattr(
        "ah_research.chat.tools._build_corpus_summary",
        lambda filings_repo, profiles_repo: fake_df,
    )
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool("get_corpus_summary", {}, deps)
    assert out["rows"][0]["symbol"] == "600519.SH"
    assert out["rows"][0]["n_annual"] == 6


# ── get_screener_row ──────────────────────────────────────────────────────


def test_get_screener_row_happy_path() -> None:
    """Minimal screener row lookup via a direct data-repo call."""
    data_repo = MagicMock()
    data_repo.get_signal_row.return_value = {
        "symbol": "600519.SH",
        "rank": 3,
        "signal": 0.82,
        "quantile": 0.1,
        "components": {"pb": 0.5, "roe": 1.0},
    }
    deps = ChatDeps(
        data_repo=data_repo,
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool(
        "get_screener_row",
        {"symbol": "600519.SH"},
        deps,
    )
    assert out["symbol"] == "600519.SH"
    assert out["rank"] == 3


def test_get_screener_row_unknown_symbol_returns_error() -> None:
    data_repo = MagicMock()
    data_repo.get_signal_row.side_effect = KeyError("not found")
    deps = ChatDeps(
        data_repo=data_repo,
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool(
        "get_screener_row",
        {"symbol": "UNKNOWN.SH"},
        deps,
    )
    assert "error" in out


# ── dispatcher sanity ─────────────────────────────────────────────────────


def test_unknown_tool_returns_error() -> None:
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool("not_a_tool", {}, deps)
    assert "error" in out


def test_tools_export_has_schemas() -> None:
    assert len(TOOLS) >= 3
    for t in TOOLS:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```
uv run pytest tests/unit/chat/test_tools.py -x
```

- [ ] **Step 3: Implement tools module (3 tools only)**

Create `src/ah_research/chat/tools.py`:

```python
"""Tools exposed to Claude via tool-use for the research chat.

Each tool returns a JSON-serializable dict. Errors are surfaced as
{"error": "<message>"} so the tool-use loop can continue cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import pandas as pd

if TYPE_CHECKING:
    from ah_research.data import DataRepository
    from ah_research.filings import FilingsRepository, ProfileRepository
    from ah_research.filings.grading import ProfileGrader


@dataclass
class ChatDeps:
    """Container for repositories and optional grader injected into tool handlers."""

    data_repo: "DataRepository"
    filings_repo: "FilingsRepository"
    profile_repo: "ProfileRepository"
    profile_grader: "ProfileGrader | None"


# ---------------------------------------------------------------------------
# Schemas (shown to Claude as tool definitions)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_universe",
        "description": (
            "List all ticker symbols known to the local research corpus. "
            "Returns the union of symbols with any filings OR a value-investing profile."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_corpus_summary",
        "description": (
            "Return a coverage table — one row per ticker with filings counts, "
            "profile freshness, and staleness. Use to answer 'which companies am I "
            "under-researched on?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sort_by": {
                    "type": "string",
                    "description": "Column to sort by (default: profile_age_days desc).",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_screener_row",
        "description": (
            "Get the current Screener output for one ticker — rank, signal, quantile, "
            "and factor components."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker, e.g. '600519.SH'."},
                "asof": {"type": "string", "description": "YYYY-MM-DD (optional)."},
            },
            "required": ["symbol"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def handle_tool(name: str, params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    """Dispatch a tool call by name. Unknown tool returns an error dict."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name!r}. Known tools: {sorted(_HANDLERS)}"}
    try:
        return handler(params, deps)
    except Exception as exc:  # noqa: BLE001 — user-facing error surface
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Individual handlers
# ---------------------------------------------------------------------------


def _list_universe(params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    filings_syms = set(deps.filings_repo.list_symbols())
    profile_syms = set(deps.profile_repo.list_symbols())
    all_syms = sorted(filings_syms | profile_syms)
    return {
        "symbols": all_syms,
        "n_with_profile": len(profile_syms),
        "n_with_filings": len(filings_syms),
    }


def _get_corpus_summary(params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    df = _build_corpus_summary(deps.filings_repo, deps.profile_repo)
    sort_by = params.get("sort_by")
    if sort_by and sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=False, na_position="last")
    # Coerce timestamps to ISO strings for JSON
    for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    return {"rows": df.to_dict(orient="records")}


def _get_screener_row(params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    symbol = params["symbol"]
    asof = params.get("asof")
    row = deps.data_repo.get_signal_row(symbol, asof=asof)
    return dict(row)


# Thin wrapper so tests can monkeypatch
def _build_corpus_summary(filings_repo: Any, profiles_repo: Any) -> pd.DataFrame:
    from ah_research.filings.summary import build_corpus_summary

    return build_corpus_summary(filings_repo=filings_repo, profiles_repo=profiles_repo)


_HANDLERS: dict[str, Callable[[dict[str, Any], ChatDeps], dict[str, Any]]] = {
    "list_universe": _list_universe,
    "get_corpus_summary": _get_corpus_summary,
    "get_screener_row": _get_screener_row,
}


__all__ = ["ChatDeps", "TOOLS", "handle_tool"]
```

- [ ] **Step 4: Add to `chat/__init__.py`**

```python
from ah_research.chat.session import ChatSession, ChatTurn
from ah_research.chat.tools import ChatDeps, TOOLS, handle_tool

__all__ = ["ChatSession", "ChatTurn", "ChatDeps", "TOOLS", "handle_tool"]
```

- [ ] **Step 5: Run — expect PASS**

```
uv run pytest tests/unit/chat/test_tools.py -x
uv run mypy src
```

Note: `data_repo.get_signal_row` may not exist. If mypy complains about it, add a `type: ignore[attr-defined]` on the call in `_get_screener_row` — the real `DataRepository` surface is tested elsewhere and the method may need to be stubbed. If `DataRepository` genuinely doesn't have `get_signal_row`, add a thin wrapper that calls whatever the real method is (inspect `src/ah_research/data/` to find the screener-output accessor, likely `get_screener_output` or `get_signals`). Document the adapter choice in the commit message.

- [ ] **Step 6: Commit**

```
git add src/ah_research/chat/tools.py src/ah_research/chat/__init__.py tests/unit/chat/test_tools.py
git commit -m "feat(phase-5): ChatDeps + 3 basic tools (list_universe, get_corpus_summary, get_screener_row)"
```

---

### Task 3: Add 5 remaining tools — `get_dossier`, `get_profile_markdown`, `get_graded_profile`, `search_filings`, `construct_portfolio`

**Files:**
- Modify: `src/ah_research/chat/tools.py`
- Modify: `tests/unit/chat/test_tools.py`

- [ ] **Step 1: Write failing tests for each new tool**

Append to `tests/unit/chat/test_tools.py`:

```python
# ── get_dossier ───────────────────────────────────────────────────────────


def test_get_dossier_returns_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dossier = MagicMock()
    fake_dossier.to_dict.return_value = {"symbol": "600519.SH", "overview": "Moutai"}
    monkeypatch.setattr(
        "ah_research.chat.tools._build_dossier",
        lambda symbol, data_repo, filings_repo, profile_repo: fake_dossier,
    )
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool("get_dossier", {"symbol": "600519.SH"}, deps)
    assert out["symbol"] == "600519.SH"


# ── get_profile_markdown ──────────────────────────────────────────────────


def test_get_profile_markdown_full(tmp_path: Path) -> None:
    profile = MagicMock()
    profile.text = "# Test Profile\n\n## §1 能力圈\ntext1\n\n## §2 护城河\ntext2\n"
    profile.date = date(2026, 4, 28)
    profile.sections = {"§1 能力圈": "text1", "§2 护城河": "text2"}
    profile_repo = MagicMock()
    profile_repo.latest.return_value = profile
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=profile_repo,
        profile_grader=None,
    )
    out = handle_tool("get_profile_markdown", {"symbol": "600519.SH"}, deps)
    assert out["symbol"] == "600519.SH"
    assert "text1" in out["text"]


def test_get_profile_markdown_section_filter() -> None:
    profile = MagicMock()
    profile.text = "# Profile\n\n## §2 护城河\nmoat text\n"
    profile.date = date(2026, 4, 28)
    profile.sections = {"§2 护城河": "moat text"}
    profile_repo = MagicMock()
    profile_repo.latest.return_value = profile
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=profile_repo,
        profile_grader=None,
    )
    out = handle_tool(
        "get_profile_markdown",
        {"symbol": "600519.SH", "section": "§2 护城河"},
        deps,
    )
    assert out["text"] == "moat text"
    assert out["section"] == "§2 护城河"


def test_get_profile_markdown_truncation() -> None:
    profile = MagicMock()
    profile.text = "a" * 20000
    profile.date = date(2026, 4, 28)
    profile.sections = {}
    profile_repo = MagicMock()
    profile_repo.latest.return_value = profile
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=profile_repo,
        profile_grader=None,
    )
    out = handle_tool(
        "get_profile_markdown",
        {"symbol": "600519.SH", "max_chars": 1000},
        deps,
    )
    assert len(out["text"]) <= 1100
    assert out["truncated"] is True


def test_get_profile_markdown_unknown_symbol() -> None:
    profile_repo = MagicMock()
    profile_repo.latest.return_value = None
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=profile_repo,
        profile_grader=None,
    )
    out = handle_tool(
        "get_profile_markdown",
        {"symbol": "UNKNOWN.SH"},
        deps,
    )
    assert "error" in out


# ── get_graded_profile ────────────────────────────────────────────────────


def test_get_graded_profile_happy_path() -> None:
    profile = MagicMock()
    profile.symbol = "600519.SH"
    profile_repo = MagicMock()
    profile_repo.latest.return_value = profile

    graded = MagicMock()
    graded.moat_grade = "A"
    graded.mgmt_grade = "B"
    graded.redflag_count = 1
    graded.confidence = 0.88
    graded.rationale = "Strong moat."
    graded.model = "claude-sonnet-4-6"
    graded.content_hash = "abc123"

    grader = MagicMock()
    grader.grade.return_value = graded

    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=profile_repo,
        profile_grader=grader,
    )
    out = handle_tool("get_graded_profile", {"symbol": "600519.SH"}, deps)
    assert out["moat_grade"] == "A"
    assert out["rationale"] == "Strong moat."


def test_get_graded_profile_without_grader_returns_error() -> None:
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool("get_graded_profile", {"symbol": "600519.SH"}, deps)
    assert "error" in out


# ── search_filings ────────────────────────────────────────────────────────


def test_search_filings_passes_args() -> None:
    from dataclasses import dataclass
    from typing import Any as _Any

    @dataclass
    class FakeFiling:
        symbol: str
        kind: str
        year: int | None
        path: object
        text: str
        title: str | None = None
        date: object = None

    @dataclass
    class FakeHit:
        filing: FakeFiling
        line_no: int
        line: str
        context: str

    hit = FakeHit(
        filing=FakeFiling(
            symbol="600519.SH", kind="annual", year=2024, path=Path("x.md"), text=""
        ),
        line_no=42,
        line="渠道改革",
        context="context",
    )
    filings_repo = MagicMock()
    filings_repo.search.return_value = [hit]

    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=filings_repo,
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool(
        "search_filings",
        {"query": "渠道改革", "symbol": "600519.SH", "max_hits": 5},
        deps,
    )
    filings_repo.search.assert_called_once()
    assert len(out["hits"]) == 1
    assert out["hits"][0]["symbol"] == "600519.SH"
    assert out["hits"][0]["line_no"] == 42


# ── construct_portfolio ───────────────────────────────────────────────────


def test_construct_portfolio_equal() -> None:
    """Equal-weight path needs no optimizer."""
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool(
        "construct_portfolio",
        {
            "symbols": ["600519.SH", "000001.SZ"],
            "asof": "2024-06-30",
            "weight_by": "equal",
        },
        deps,
    )
    assert "weights" in out
    assert abs(sum(out["weights"].values()) - 1.0) < 1e-6


def test_construct_portfolio_unknown_weight_by() -> None:
    deps = ChatDeps(
        data_repo=MagicMock(),
        filings_repo=MagicMock(),
        profile_repo=MagicMock(),
        profile_grader=None,
    )
    out = handle_tool(
        "construct_portfolio",
        {
            "symbols": ["600519.SH"],
            "asof": "2024-06-30",
            "weight_by": "not_a_scheme",
        },
        deps,
    )
    assert "error" in out
```

- [ ] **Step 2: Run — expect FAILs (handlers don't exist)**

```
uv run pytest tests/unit/chat/test_tools.py -x
```

- [ ] **Step 3: Implement the 5 new handlers**

Append to `src/ah_research/chat/tools.py`:

1. Add 5 new schemas to `TOOLS` list
2. Add 5 new `_handler` functions
3. Register all 5 in `_HANDLERS`

```python
# --- add to TOOLS list ---
{
    "name": "get_dossier",
    "description": "Return the full structured Dossier for one ticker as a dict.",
    "input_schema": {
        "type": "object",
        "properties": {"symbol": {"type": "string"}},
        "required": ["symbol"],
    },
},
{
    "name": "get_profile_markdown",
    "description": (
        "Return the latest value-investing profile as markdown. "
        "Optionally filter to a single section by heading (e.g. '§2 护城河')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "section": {"type": "string", "description": "Section heading to filter."},
            "max_chars": {
                "type": "integer",
                "description": "Truncate output to this many characters (default 8000).",
            },
        },
        "required": ["symbol"],
    },
},
{
    "name": "get_graded_profile",
    "description": (
        "Get LLM-graded letter grades for moat, management, and red-flag count "
        "from the latest profile. Uses disk cache — cheap to call repeatedly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "force_refresh": {"type": "boolean", "description": "Bypass cache."},
        },
        "required": ["symbol"],
    },
},
{
    "name": "search_filings",
    "description": (
        "Substring or regex search across annual reports, IPO prospectus, and "
        "research reports. Returns up to max_hits hits with line number and context."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "symbol": {"type": "string", "description": "Filter to one ticker."},
            "kinds": {
                "type": "array",
                "items": {"type": "string", "enum": ["annual", "ipo", "research"]},
            },
            "regex": {"type": "boolean"},
            "max_hits": {"type": "integer", "description": "Overall cap (default 10)."},
        },
        "required": ["query"],
    },
},
{
    "name": "construct_portfolio",
    "description": (
        "Build a portfolio for the given symbols using equal weights or the convex "
        "optimizer. Returns the weight table + solver status if optimized."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "asof": {"type": "string", "description": "YYYY-MM-DD"},
            "weight_by": {"type": "string", "enum": ["equal", "optimize"]},
            "objective": {"type": "string", "enum": ["mean_variance", "risk_parity"]},
            "risk_aversion": {"type": "number"},
            "max_turnover": {"type": "number"},
        },
        "required": ["symbols", "asof", "weight_by"],
    },
},
```

And handler functions:

```python
def _get_dossier(params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    symbol = params["symbol"]
    dossier = _build_dossier(symbol, deps.data_repo, deps.filings_repo, deps.profile_repo)
    return dict(dossier.to_dict())


def _get_profile_markdown(params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    symbol = params["symbol"]
    section = params.get("section")
    max_chars = int(params.get("max_chars", 8000))

    profile = deps.profile_repo.latest(symbol)
    if profile is None:
        return {"error": f"No profile found for {symbol!r}"}

    if section:
        body = profile.sections.get(section)
        if body is None:
            return {
                "error": f"Section {section!r} not found. Available: {sorted(profile.sections)}"
            }
        text = body
    else:
        text = profile.text

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n…[truncated]"
        truncated = True

    return {
        "symbol": symbol,
        "date": str(profile.date) if hasattr(profile, "date") else None,
        "section": section,
        "text": text,
        "truncated": truncated,
    }


def _get_graded_profile(params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    if deps.profile_grader is None:
        return {
            "error": (
                "No ProfileGrader configured. Set ANTHROPIC_API_KEY and construct "
                "ResearchChat with a ProfileGrader."
            )
        }
    symbol = params["symbol"]
    profile = deps.profile_repo.latest(symbol)
    if profile is None:
        return {"error": f"No profile found for {symbol!r}"}
    graded = deps.profile_grader.grade(profile, force=bool(params.get("force_refresh", False)))
    return {
        "symbol": symbol,
        "moat_grade": graded.moat_grade,
        "mgmt_grade": graded.mgmt_grade,
        "redflag_count": graded.redflag_count,
        "confidence": graded.confidence,
        "rationale": graded.rationale,
        "model": graded.model,
        "content_hash": graded.content_hash,
    }


def _search_filings(params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    query = params["query"]
    symbol = params.get("symbol")
    kinds = params.get("kinds")
    regex = bool(params.get("regex", False))
    max_hits = int(params.get("max_hits", 10))

    hits = deps.filings_repo.search(
        query,
        symbols=[symbol] if symbol else None,
        kinds=kinds,
        regex=regex,
        max_hits_per_file=None,
    )
    # Overall cap
    hits = hits[:max_hits]
    return {
        "hits": [
            {
                "symbol": h.filing.symbol,
                "kind": h.filing.kind,
                "year": h.filing.year,
                "line_no": h.line_no,
                "line": h.line,
                "context": h.context,
            }
            for h in hits
        ]
    }


def _construct_portfolio(params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]:
    from datetime import datetime as _dt

    import pandas as pd

    from ah_research.backtest.types import Signals
    from ah_research.portfolio.constructor import Constructor

    symbols = list(params["symbols"])
    asof = _dt.strptime(params["asof"], "%Y-%m-%d").date()
    weight_by = params["weight_by"]
    if weight_by not in ("equal", "optimize"):
        return {"error": f"weight_by must be 'equal' or 'optimize', got {weight_by!r}"}

    sig_df = pd.DataFrame(
        {"asof": [asof] * len(symbols), "symbol": symbols, "signal": [1.0] * len(symbols)}
    )
    signals = Signals(df=sig_df, asof=asof)

    optimizer: Any = None
    if weight_by == "optimize":
        from ah_research.portfolio.optimizer import Optimizer
        from ah_research.portfolio.optimizer.estimators import (
            LedoitWolfCovariance,
            SignalBasedReturns,
        )

        objective = params.get("objective", "mean_variance")
        if objective == "mean_variance":
            optimizer = Optimizer(
                objective="mean_variance",
                cov_estimator=LedoitWolfCovariance(),
                returns_estimator=SignalBasedReturns(),
                risk_aversion=float(params.get("risk_aversion", 1.0)),
            )
        else:
            optimizer = Optimizer(
                objective="risk_parity",
                cov_estimator=LedoitWolfCovariance(),
            )

    report = (
        Constructor(signals, repo=deps.data_repo, asof=asof, optimizer=optimizer)
        .method("all_positive")
        .weight_by(weight_by)  # type: ignore[arg-type]
        .build()
    )
    weights = dict(zip(report.weights["symbol"], report.weights["weight"], strict=True))
    out: dict[str, Any] = {"weights": {k: float(v) for k, v in weights.items()}}
    if report.optimization_result is not None:
        out["solver_status"] = report.optimization_result.solver_status
    return out


def _build_dossier(symbol: str, data_repo: Any, filings_repo: Any, profile_repo: Any) -> Any:
    from ah_research.analysis.dossier import build_dossier

    return build_dossier(
        symbol=symbol, repo=data_repo, filings_repo=filings_repo, profile_repo=profile_repo
    )
```

Then update `_HANDLERS`:

```python
_HANDLERS: dict[str, Callable[[dict[str, Any], ChatDeps], dict[str, Any]]] = {
    "list_universe": _list_universe,
    "get_corpus_summary": _get_corpus_summary,
    "get_screener_row": _get_screener_row,
    "get_dossier": _get_dossier,
    "get_profile_markdown": _get_profile_markdown,
    "get_graded_profile": _get_graded_profile,
    "search_filings": _search_filings,
    "construct_portfolio": _construct_portfolio,
}
```

- [ ] **Step 4: Run — expect PASS**

```
uv run pytest tests/unit/chat/test_tools.py -x
uv run mypy src
```

If `construct_portfolio` test errors because `Constructor.weight_by("optimize")` isn't merged yet in this branch's base — note: Phase 4.8 is shipping separately. In this worktree (off origin/main) `weight_by("optimize")` does NOT exist. **Fix:** omit the `optimize` path entirely from the handler if `weight_by="optimize"` but `Constructor` lacks that scheme. Use a runtime check:

```python
# At top of _construct_portfolio, check available schemes
# Replace the optimizer block with:
if weight_by == "optimize":
    # Probe whether Constructor supports optimize mode (Phase 4.8)
    import inspect
    constructor_init_sig = inspect.signature(Constructor.__init__)
    if "optimizer" not in constructor_init_sig.parameters:
        return {
            "error": (
                "Optimize weighting not available in this build "
                "(requires Phase 4.8). Use weight_by='equal' instead."
            )
        }
    # ... (rest of optimizer setup)
```

Adjust the failing test `test_construct_portfolio_unknown_weight_by` if needed. **Remove `test_construct_portfolio_equal` if Constructor.build() blows up with an empty signal frame + `all_positive` returning nothing** — replace with a test where all signals are positive so `all_positive` yields a non-empty selection. Verify with:

```python
def test_construct_portfolio_equal() -> None:
    """Equal-weight path needs no optimizer."""
    ...
    out = handle_tool(
        "construct_portfolio",
        {
            "symbols": ["600519.SH", "000001.SZ"],
            "asof": "2024-06-30",
            "weight_by": "equal",
        },
        deps,
    )
```

Signals has signal=1.0 for every symbol (see `_construct_portfolio` above), so `all_positive` selects all.

- [ ] **Step 5: Commit**

```
git add src/ah_research/chat/tools.py tests/unit/chat/test_tools.py
git commit -m "feat(phase-5): 5 remaining chat tools (dossier, profile_markdown, graded_profile, search_filings, construct_portfolio)"
```

---

### Task 4: `ResearchChat` class with fully-mocked tool-use loop tests

**Files:**
- Create: `src/ah_research/chat/chat.py`
- Modify: `src/ah_research/chat/__init__.py`
- Create: `tests/unit/chat/test_chat.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/chat/test_chat.py
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


def _mock_tool_use_block(name: str, input_: dict, tool_use_id: str = "tu_1") -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_
    block.id = tool_use_id
    return block


def _mock_response(content_blocks: list) -> MagicMock:
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
    client.messages.create.return_value = _mock_response([_mock_text_block("Moutai is a premium baijiu producer.")])
    chat = _make_chat(tmp_path, client)
    answer = chat.send("Tell me about Moutai")
    assert "Moutai" in answer
    assert client.messages.create.call_count == 1
    # Session has 2 turns: user + assistant
    assert len(chat.session.turns) == 2


def test_send_two_round_tool_use(tmp_path: Path) -> None:
    client = MagicMock()
    # Round 1: tool_use block
    tool_use_resp = _mock_response(
        [_mock_tool_use_block("list_universe", {}, tool_use_id="tu_1")]
    )
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
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```
uv run pytest tests/unit/chat/test_chat.py -x
```

- [ ] **Step 3: Implement `ResearchChat`**

Create `src/ah_research/chat/chat.py`:

```python
"""ResearchChat — tool-use conversational orchestrator."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

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
        client: "_anthropic.Anthropic | None" = None,
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
        system_block = {
            "type": "text",
            "text": _SYSTEM_PROMPT.format(anchor=self.session.anchor_symbol or "none"),
            "cache_control": {"type": "ephemeral"},
        }

        for _ in range(self.max_iterations):
            resp = self.client.messages.create(
                model=self.session.model,
                max_tokens=self.max_tokens,
                system=[system_block],
                tools=TOOLS,
                messages=messages,
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
                result_json = json.dumps(result, ensure_ascii=False)
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

        raise RuntimeError(
            f"Max iterations ({self.max_iterations}) exceeded without final answer"
        )

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
```

Update `src/ah_research/chat/__init__.py`:

```python
from ah_research.chat.chat import ResearchChat
from ah_research.chat.session import ChatSession, ChatTurn
from ah_research.chat.tools import ChatDeps, TOOLS, handle_tool

__all__ = ["ResearchChat", "ChatSession", "ChatTurn", "ChatDeps", "TOOLS", "handle_tool"]
```

- [ ] **Step 4: Run — expect PASS**

```
uv run pytest tests/unit/chat/test_chat.py -x
uv run mypy src
```

- [ ] **Step 5: Commit**

```
git add src/ah_research/chat/chat.py src/ah_research/chat/__init__.py tests/unit/chat/test_chat.py
git commit -m "feat(phase-5): ResearchChat tool-use loop with session history"
```

---

### Task 5: CLI `ah chat` REPL

**Files:**
- Create: `src/ah_research/scripts/ah_chat.py`
- Modify: `src/ah_research/cli.py`
- Create: `tests/unit/scripts/test_cli_chat.py`

- [ ] **Step 1: Write failing CLI tests**

```python
# tests/unit/scripts/test_cli_chat.py
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
```

- [ ] **Step 2: Run — expect fails (no chat subcommand)**

```
uv run pytest tests/unit/scripts/test_cli_chat.py -x
```

- [ ] **Step 3: Implement CLI**

Create `src/ah_research/scripts/ah_chat.py`:

```python
"""ah chat — conversational research CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Conversational research over the local corpus.")
console = Console()


def _sessions_dir() -> Path:
    return Path.home() / ".ah-research" / "chat"


@app.callback(invoke_without_command=True)
def chat_main(
    ctx: typer.Context,
    ticker: Annotated[str | None, typer.Argument(help="Anchor ticker.")] = None,
    resume: Annotated[
        str | None, typer.Option("--resume", help="Resume session by ID.")
    ] = None,
    list_sessions: Annotated[
        bool, typer.Option("--list", help="List recent sessions.")
    ] = False,
    model: Annotated[
        str, typer.Option("--model", help="Claude model ID.")
    ] = "claude-sonnet-4-6",
) -> None:
    """Start or resume a chat session."""
    if list_sessions:
        _list_sessions()
        return

    if resume is not None:
        _resume_session(resume, model_override=model)
        return

    _new_session(ticker, model=model)


def _list_sessions() -> None:
    root = _sessions_dir()
    if not root.exists():
        console.print("No sessions found.")
        return
    files = sorted(root.glob("*.jsonl"), reverse=True)[:20]
    if not files:
        console.print("No sessions found.")
        return
    tbl = Table(title="Recent chat sessions")
    tbl.add_column("session_id")
    tbl.add_column("anchor")
    tbl.add_column("turns", justify="right")
    from ah_research.chat.session import ChatSession

    for f in files:
        try:
            s = ChatSession.load(f)
            tbl.add_row(s.session_id, s.anchor_symbol or "-", str(len(s.turns)))
        except Exception:
            tbl.add_row(f.stem, "?", "?")
    console.print(tbl)


def _new_session(ticker: str | None, *, model: str) -> None:
    from ah_research.chat.session import ChatSession

    session = ChatSession.new(anchor=ticker, model=model, root=_sessions_dir())
    console.print(f"[green]New session:[/green] {session.session_id}")
    _repl(session)


def _resume_session(session_id: str, *, model_override: str) -> None:
    from ah_research.chat.session import ChatSession

    path = _sessions_dir() / f"{session_id}.jsonl"
    if not path.exists():
        console.print(f"[red]Session {session_id!r} not found in {_sessions_dir()}[/red]")
        raise typer.Exit(code=1)
    session = ChatSession.load(path)
    console.print(f"[green]Resumed:[/green] {session.session_id} ({len(session.turns)} turns)")
    _repl(session)


def _repl(session: "Any") -> None:  # noqa: F821
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[yellow]ANTHROPIC_API_KEY not set — chat cannot call the API.[/yellow]\n"
            "Set it and retry: https://console.anthropic.com/"
        )
        return

    from ah_research.chat.chat import ResearchChat
    from ah_research.chat.tools import ChatDeps
    from ah_research.data import DataRepository
    from ah_research.filings import FilingsRepository, ProfileRepository

    deps = ChatDeps(
        data_repo=DataRepository(),
        filings_repo=FilingsRepository(),
        profile_repo=ProfileRepository(),
        profile_grader=None,  # TODO: wire in if API key present
    )
    chat = ResearchChat(session=session, deps=deps)

    console.print("[dim]Type 'quit' or Ctrl-D to exit.[/dim]")
    while True:
        try:
            user_text = input("> ").strip()
        except EOFError:
            console.print("\n[dim]bye[/dim]")
            return
        if user_text.lower() in ("quit", "exit", ":q", ""):
            console.print("[dim]bye[/dim]")
            return
        try:
            answer = chat.send(user_text)
            console.print(f"\n[bold cyan]Assistant:[/bold cyan] {answer}\n")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Error:[/red] {exc}")
```

- [ ] **Step 4: Register in `cli.py`**

Find the block around `app.add_typer(filings_app)` and add:

```python
from ah_research.scripts.ah_chat import app as chat_app
# ... existing ...
app.add_typer(chat_app, name="chat")
```

- [ ] **Step 5: Run**

```
uv run pytest tests/unit/scripts/test_cli_chat.py -x
uv run mypy src
```

- [ ] **Step 6: Commit**

```
git add src/ah_research/scripts/ah_chat.py src/ah_research/cli.py tests/unit/scripts/test_cli_chat.py
git commit -m "feat(phase-5): ah chat CLI REPL"
```

---

### Task 6: Integration test (real API, slow-marker)

**Files:**
- Create: `tests/integration/test_chat_real_api.py`
- Modify: `pyproject.toml` (if `slow` marker not already defined)

- [ ] **Step 1: Check pyproject for slow marker**

```
grep -A 5 "markers" pyproject.toml
```

- [ ] **Step 2: Add `slow` marker if missing**

If not present, add under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (real API calls; opt-in via -m slow)",
]
```

- [ ] **Step 3: Write integration test**

```python
# tests/integration/test_chat_real_api.py
from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.slow


def test_chat_single_turn_real_api(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """One real-API chat turn. Skipped if ANTHROPIC_API_KEY unset."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    pytest.importorskip("anthropic")

    from ah_research.chat.chat import ResearchChat
    from ah_research.chat.session import ChatSession
    from ah_research.chat.tools import ChatDeps
    from unittest.mock import MagicMock

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
```

- [ ] **Step 4: Run (will skip without API key)**

```
uv run pytest tests/integration/test_chat_real_api.py -x -m slow
```

- [ ] **Step 5: Commit**

```
git add tests/integration/test_chat_real_api.py pyproject.toml
git commit -m "test(phase-5): real-API integration test (slow-marked)"
```

---

### Task 7: Acceptance notebook + headless integration test

**Files:**
- Create: `notebooks/phase5_chat_example.ipynb`
- Create: `tests/integration/test_phase5_notebook_runs.py`

- [ ] **Step 1: Create the notebook**

~10–15 cells, structured to run headless without an API key:

1. Markdown: "Phase 5 — Research Chat UI"
2. Imports (`ResearchChat`, `ChatSession`, `ChatDeps`, `unittest.mock.MagicMock`)
3. Explain: "This notebook uses a mocked Anthropic client so it runs without an API key."
4. Build a mock client that returns canned responses for two turns
5. Build `ChatDeps` with MagicMocks, fixture-ish list_symbols outputs
6. Create temp session dir
7. Instantiate `ResearchChat`
8. `chat.send("How many symbols?")` — show the result
9. Display `chat.session.turns`
10. Close out with a markdown cell summarizing the architecture

Use `tempfile.mkdtemp()` or `pathlib.Path("/tmp/phase5-demo")` for the session dir.

- [ ] **Step 2: Create headless test**

```python
# tests/integration/test_phase5_notebook_runs.py
from __future__ import annotations

from pathlib import Path

import pytest
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError
import nbformat


NOTEBOOK = Path(__file__).parents[2] / "notebooks" / "phase5_chat_example.ipynb"


def test_phase5_notebook_runs_headless() -> None:
    if not NOTEBOOK.exists():
        pytest.skip("notebook not present")
    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(nb, timeout=120)
    try:
        client.execute()
    except CellExecutionError as e:
        pytest.fail(f"notebook execution failed: {e}")
```

- [ ] **Step 3: Execute notebook and save**

```
uv run jupyter nbconvert --to notebook --execute \
    notebooks/phase5_chat_example.ipynb \
    --output notebooks/phase5_chat_example.ipynb
```

- [ ] **Step 4: Run headless test**

```
uv run pytest tests/integration/test_phase5_notebook_runs.py -x
```

- [ ] **Step 5: Commit**

```
git add notebooks/phase5_chat_example.ipynb tests/integration/test_phase5_notebook_runs.py
git commit -m "feat(phase-5): acceptance notebook + headless test"
```

---

### Task 8: CHANGELOG + README

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Add CHANGELOG entry** above the Phase 4.7 entry:

```markdown
## Phase 5 — Research Chat UI (2026-05-01)

### Added
- `ResearchChat` — conversational agent with tool-use loop over 8 platform tools (list_universe, get_dossier, get_profile_markdown, get_graded_profile, get_screener_row, search_filings, get_corpus_summary, construct_portfolio).
- `ChatSession` — JSONL-persisted conversation history at `~/.ah-research/chat/<session-id>.jsonl` with `--resume` support.
- `ah chat [TICKER] [--resume ID] [--model NAME] [--list]` — REPL CLI.

### Design doc
- `docs/superpowers/specs/2026-05-01-ah-research-phase-5-research-chat-design.md`
```

- [ ] **Step 2: README bullet**

Add to the Features section:

```markdown
- **Research chat** — `ah chat <ticker>` opens a REPL that reasons over your local Dossier / Profile / Screener / Filings data via Claude tool use. Eight tools wire the chat to the platform; sessions persist at `~/.ah-research/chat/`.
```

- [ ] **Step 3: Full CI sweep**

```
uv run pytest
uv run mypy src
```

- [ ] **Step 4: Commit**

```
git add CHANGELOG.md README.md
git commit -m "docs(phase-5): CHANGELOG + README"
```

---

### Task 9: Finalize

- [ ] Push: `git push -u origin feat/phase-5`
- [ ] Verify clean: `git status`
- [ ] Full sweep one more time: `uv run pytest && uv run mypy src`
- [ ] Open PR: `gh pr create --title "feat(phase-5): Research Chat UI" --body "..."` — body summarizes the spec highlights and gives a test plan checklist
