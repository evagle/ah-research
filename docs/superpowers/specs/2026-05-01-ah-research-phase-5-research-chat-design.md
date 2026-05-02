# Phase 5 — Research Chat UI

**Date:** 2026-05-01
**Depends on:** Phase 3 (`Dossier`, `Screener`, `Constructor`, `ConstructionReport`), Phase 4.1 (`Optimizer`, `OptimizationResult`), Phase 4.2–4.6 (`FilingsRepository`, `ProfileRepository`, `build_corpus_summary`, `FilingsRepository.search`), Phase 4.7 (`ProfileGrader`, `GradedProfile`) — all merged.

## 1. Mission

Make the structured research outputs conversational. A user runs `ah chat 600519.SH` or `ah chat` and asks natural-language questions — *"Why did Moutai rank 3rd this month?" / "Summarize the management section of the latest profile" / "Build an optimized portfolio from the top 5 screener picks"* — and Claude answers with citations drawn from the platform's local data.

The research platform already produces rich structured data (Dossier, GradedProfile, Screener, OptimizationResult, Filings/Profile repos). Phase 5 exposes that data to Claude via **tool use**, so the model decides what to fetch instead of us stuffing everything into the system prompt.

## 2. Scope

**In scope:**
- `ResearchChat` class in `src/ah_research/chat/chat.py` — a conversational agent with tool-use loop, prompt caching, and disk-persisted session history
- 8 tools covering Phase 3/4 data: `list_universe`, `get_dossier`, `get_profile_markdown`, `get_graded_profile`, `get_screener_row`, `search_filings`, `get_corpus_summary`, `construct_portfolio`
- CLI: `ah chat [TICKER] [--resume SESSION] [--model NAME]` — REPL over stdin/stdout
- Session files: JSONL at `~/.ah-research/chat/<session-id>.jsonl` (one line per turn)
- Unit tests (mocked anthropic client) + integration test (real API, slow-marker) + acceptance notebook

**Out of scope (deferred):**
- Web / Streamlit UI — CLI only in this phase
- Retrieval / embeddings — tools are structured SQL / path lookups, not semantic search
- Multi-ticker conversation graphs — one anchor ticker per session max
- Streaming tokens to stdout — wait for full response (simplifies the REPL)
- Conversation summarization when context overflows — just error out cleanly above ~150K tokens and advise `--resume` to a fresh session

## 3. Architecture

### 3.1 Module layout

```
src/ah_research/
├── chat/                           # NEW package
│   ├── __init__.py                 # public API: ResearchChat, ChatSession
│   ├── chat.py                     # ResearchChat class (tool-use loop)
│   ├── tools.py                    # tool definitions + handlers
│   └── session.py                  # ChatSession dataclass + JSONL persistence
└── scripts/
    └── ah_chat.py                  # Typer sub-app for `ah chat`
```

### 3.2 Conversation model

```
user text
  → Claude(system + tools + history) 
    → Claude emits tool_use blocks
      → handler runs tool, returns tool_result block
      → loop continues (up to MAX_ITERATIONS)
    → Claude emits final text answer
  → display to user, persist turn to JSONL, loop
```

One "turn" spans a single user message to the final assistant-text response, potentially including multiple tool round-trips.

## 4. Core types

```python
# src/ah_research/chat/session.py

@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant", "tool_result"]
    content: str                 # for assistant: final text; for tool_result: JSON string
    tool_name: str | None = None # set when role == "tool_result"
    tool_use_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ChatSession:
    session_id: str              # "2026-05-01T13:22:08-moutai" slug
    anchor_symbol: str | None    # set by CLI if `ah chat <TICKER>`
    model: str                   # e.g. "claude-sonnet-4-6"
    turns: list[ChatTurn] = field(default_factory=list)
    path: Path = ...             # ~/.ah-research/chat/<session-id>.jsonl

    def append(self, turn: ChatTurn) -> None: ...   # appends to file too
    @classmethod
    def load(cls, path: Path) -> ChatSession: ...
    @classmethod
    def new(cls, anchor: str | None, model: str, root: Path) -> ChatSession: ...
```

## 5. Tools

All tools return JSON-serializable dicts. Errors are surfaced as `{"error": "<human-readable message>"}` — never raised into the tool-use loop (which would stall the turn).

| Tool | Input | Output (shape) |
|---|---|---|
| `list_universe` | `{}` | `{"symbols": ["600519.SH", ...], "n_with_profile": 1}` |
| `get_dossier` | `{"symbol": "600519.SH"}` | full `Dossier.to_dict()` with filings_section, profile_section, etc. |
| `get_profile_markdown` | `{"symbol": "600519.SH", "section": "§2 护城河"?, "max_chars": 8000?}` | `{"symbol": ..., "date": "2026-04-28", "section": ..., "text": "..."}` (truncated with `"…[truncated]"` if needed) |
| `get_graded_profile` | `{"symbol": "600519.SH", "force_refresh": false}` | grading JSON (moat_grade, mgmt_grade, redflag_count, confidence, rationale, content_hash) |
| `get_screener_row` | `{"symbol": "600519.SH", "asof": "YYYY-MM-DD"?}` | `{"symbol": ..., "rank": 3, "signal": 0.82, "quantile": 0.1, "components": {...}}` |
| `search_filings` | `{"query": "渠道改革", "symbol": null, "kinds": ["annual"]?, "regex": false, "max_hits": 10}` | `{"hits": [{"symbol": ..., "kind": ..., "year": ..., "line_no": ..., "line": ..., "context": "..."}, ...]}` |
| `get_corpus_summary` | `{"sort_by": "profile_age_days"?}` | list of per-ticker dicts matching `build_corpus_summary` columns |
| `construct_portfolio` | `{"symbols": [...], "asof": "YYYY-MM-DD", "weight_by": "equal|optimize", "objective": "mean_variance|risk_parity"?, "risk_aversion"?: 1.0, "max_turnover"?: 0.3}` | `{"weights": {"sym": w, ...}, "solver_status": ..., "report": {...}}` |

Each tool's JSONSchema lives in `src/ah_research/chat/tools.py`; the same file also has a dispatcher:

```python
def handle_tool(name: str, params: dict[str, Any], deps: ChatDeps) -> dict[str, Any]: ...
```

`ChatDeps` is a simple container of resolved repositories (`DataRepository`, `FilingsRepository`, `ProfileRepository`, optionally a `ProfileGrader` for `get_graded_profile`).

## 6. `ResearchChat` API

```python
# src/ah_research/chat/chat.py

class ResearchChat:
    def __init__(
        self,
        session: ChatSession,
        deps: ChatDeps,
        *,
        client: anthropic.Anthropic | None = None,   # defaults to anthropic.Anthropic()
        max_tokens: int = 2048,
        max_iterations: int = 10,       # max tool round-trips per turn
    ) -> None: ...

    def send(self, user_text: str) -> str:
        """Run one turn end-to-end. Returns the assistant's final text."""
```

### 6.1 System prompt (cached)

```
You are a research assistant for the ah-research platform. You answer questions
about A-share / HK-share companies using the platform's structured tools.

RULES:
- Always cite concrete data by tool name and ticker (e.g. "per get_graded_profile
  for 600519.SH, moat_grade=A"). Do not invent data.
- When the user mentions an anchor ticker, prefer tools that operate on it.
- For portfolio questions, use construct_portfolio rather than explaining theory.
- For text-heavy questions (profile sections, filings), call get_profile_markdown
  or search_filings with a narrow query.
- Numeric answers should include the units or percent sign.
- Keep responses under ~400 words unless asked for depth.

Anchor ticker (if set): {anchor_symbol or "none"}
```

The `system` block uses `cache_control: {"type": "ephemeral"}` — same pattern as `ProfileGrader` in `src/ah_research/filings/grading.py:132-143`.

Tool definitions are also cached.

### 6.2 Turn execution

```python
def send(self, user_text: str) -> str:
    self.session.append(ChatTurn(role="user", content=user_text))
    messages = self._history_as_messages()
    for _ in range(self.max_iterations):
        resp = self.client.messages.create(
            model=self.session.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=self._tool_definitions(),
            messages=messages,
        )
        # Append assistant message (tool_use blocks + any partial text)
        assistant_content = [...]
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            # Final answer
            text = "".join(b.text for b in resp.content if b.type == "text")
            self.session.append(ChatTurn(role="assistant", content=text))
            return text

        tool_results = []
        for tu in tool_uses:
            result = handle_tool(tu.name, tu.input, self.deps)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(result)}
            )
            self.session.append(
                ChatTurn(
                    role="tool_result",
                    content=json.dumps(result),
                    tool_name=tu.name,
                    tool_use_id=tu.id,
                )
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"Max iterations ({self.max_iterations}) exceeded without final answer")
```

## 7. CLI

```
ah chat [TICKER]                                 # new session, anchored on TICKER (optional)
ah chat --resume <session-id>                    # continue existing session
ah chat --list                                   # list last 20 sessions
ah chat --model claude-haiku-4-5-20251001        # override model
```

REPL behavior:
- Prompt `> ` reads one line of user input
- Empty input or `quit` / `exit` / `:q` → graceful exit
- `\clear` → wipe conversation (keeps session file; starts new session behind the scenes)
- `\tools` → print tool list
- Assistant responses printed via Rich with citations highlighted

## 8. Error handling

| Situation | Behavior |
|---|---|
| No `ANTHROPIC_API_KEY` env var | friendly error on CLI start: `"Set ANTHROPIC_API_KEY to use ah chat. See https://console.anthropic.com/"` |
| Tool raises unexpected exception | caught → returned as `{"error": str(exc)}` in tool_result; user sees Claude continuing the turn |
| Unknown ticker in tool call | `{"error": "symbol '<x>' not found in profiles/ or data/filings/"}` |
| anthropic.APIError / RateLimit | bubbled up with a human-readable message on CLI; session file still has the user turn saved so `--resume` works |
| max_iterations exceeded | raise with guidance to narrow the question |
| Session file corrupt | `ChatSession.load` raises; CLI catches and offers to start fresh |

## 9. Testing

**Unit tests (fast, mocked):**
- `tests/unit/chat/test_tools.py`
  - `list_universe` with / without profile repo
  - `get_dossier` happy path + unknown symbol error
  - `get_profile_markdown` with `section` filter + truncation
  - `get_graded_profile` with mocked `ProfileGrader` (cache hit path)
  - `get_screener_row` happy + unknown
  - `search_filings` passes kinds/symbols/max_hits through
  - `get_corpus_summary` returns expected columns
  - `construct_portfolio` with `weight_by="equal"` (no repo mock needed for equal)
- `tests/unit/chat/test_session.py`
  - `ChatSession.new` creates file + session_id
  - `.append` persists to JSONL
  - `.load` round-trips
- `tests/unit/chat/test_chat.py`
  - `ResearchChat.send` with fully-mocked `anthropic.Anthropic` covering:
    - single-turn (no tool use) → returns text
    - two-round tool use (calls 1 tool, then returns text)
    - `max_iterations` exceeded → raises
- `tests/unit/scripts/test_cli_chat.py` — Typer CliRunner, `--list` + `--help` + `--resume <nonexistent>`

**Integration (real API, marked `slow`):**
- `tests/integration/test_chat_real_api.py` — one turn against the real API using Moutai fixtures (skipped if `ANTHROPIC_API_KEY` unset)

**Acceptance notebook:**
- `notebooks/phase5_chat_example.ipynb` — shows building a `ResearchChat` from local repos, sending one or two Q&A turns with mock responses (so the notebook runs headless), and printing the session JSONL

## 10. Dependencies

No new dependencies. `anthropic>=0.40.0` from Phase 4.7 is sufficient.

## 11. File inventory

**New:**
```
src/ah_research/chat/__init__.py
src/ah_research/chat/chat.py
src/ah_research/chat/session.py
src/ah_research/chat/tools.py
src/ah_research/scripts/ah_chat.py
tests/unit/chat/__init__.py
tests/unit/chat/test_tools.py
tests/unit/chat/test_session.py
tests/unit/chat/test_chat.py
tests/unit/scripts/test_cli_chat.py
tests/integration/test_chat_real_api.py
tests/integration/test_phase5_notebook_runs.py
notebooks/phase5_chat_example.ipynb
```

**Modified:**
```
src/ah_research/cli.py          # register chat_app
CHANGELOG.md
README.md
pyproject.toml                   # (if needed) pytest marker "slow"
```

## 12. Acceptance

- Unit tests + CLI smoke tests pass.
- Notebook runs headless.
- `uv run pytest` + `uv run mypy src` green.
- Manual: `ANTHROPIC_API_KEY=... uv run ah chat 600519.SH` successfully answers at least one question ("Summarize the moat section of the latest profile") using at least one tool.
