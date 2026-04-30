"""ah chat — conversational research CLI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from ah_research.chat.session import ChatSession

app = typer.Typer(name="chat", help="Conversational research over the local corpus.")
console = Console()


def _sessions_dir() -> Path:
    return Path.home() / ".ah-research" / "chat"


@app.callback(invoke_without_command=True)
def chat_main(
    ctx: typer.Context,
    ticker: Annotated[str | None, typer.Argument(help="Anchor ticker.")] = None,
    resume: Annotated[str | None, typer.Option("--resume", help="Resume session by ID.")] = None,
    list_sessions: Annotated[bool, typer.Option("--list", help="List recent sessions.")] = False,
    model: Annotated[str, typer.Option("--model", help="Claude model ID.")] = "claude-sonnet-4-6",
) -> None:
    """Start or resume a chat session."""
    if list_sessions:
        _list_sessions()
        return

    if resume is not None:
        _resume_session(resume)
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


def _resume_session(session_id: str) -> None:
    from ah_research.chat.session import ChatSession

    path = _sessions_dir() / f"{session_id}.jsonl"
    if not path.exists():
        console.print(f"[red]Session {session_id!r} not found in {_sessions_dir()}[/red]")
        raise typer.Exit(code=1)
    session = ChatSession.load(path)
    console.print(f"[green]Resumed:[/green] {session.session_id} ({len(session.turns)} turns)")
    _repl(session)


def _repl(session: ChatSession) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[yellow]ANTHROPIC_API_KEY not set — chat cannot call the API.[/yellow]\n"
            "Set it and retry: https://console.anthropic.com/"
        )
        return

    # Lazy imports so unit tests without data cache don't pay this cost
    from typing import Any, cast

    from ah_research.chat.chat import ResearchChat
    from ah_research.chat.tools import ChatDeps
    from ah_research.filings.filings_repository import FilingsRepository
    from ah_research.filings.profile_repository import ProfileRepository

    # DataRepository needs Source protocols wired by ah warmup/init (Phase 1).
    # If unavailable, the chat still runs the text-only tools (profile, filings)
    # and any data-repo-backed tool will surface a caught error to the user.
    data_repo: Any = None

    deps = ChatDeps(
        data_repo=cast(Any, data_repo),
        filings_repo=FilingsRepository(),
        profile_repo=ProfileRepository(),
        profile_grader=None,
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
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
