"""Tools exposed to Claude via tool-use for the research chat.

Each tool returns a JSON-serializable dict. Errors are surfaced as
{"error": "<message>"} so the tool-use loop can continue cleanly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from ah_research.data.repository import DataRepository
    from ah_research.filings.filings_repository import FilingsRepository
    from ah_research.filings.grading import ProfileGrader
    from ah_research.filings.profile_repository import ProfileRepository


@dataclass
class ChatDeps:
    """Container for repositories and optional grader injected into tool handlers."""

    data_repo: DataRepository
    filings_repo: FilingsRepository
    profile_repo: ProfileRepository
    profile_grader: ProfileGrader | None


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
    except Exception as exc:
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
    # DataRepository does not currently expose get_signal_row; the chat layer
    # relies on a thin adapter (inject on test) or a future method. Duck-type:
    # any exception → {"error": ...} via handle_tool wrapper.
    row = deps.data_repo.get_signal_row(symbol, asof=asof)  # type: ignore[attr-defined]
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


__all__ = ["TOOLS", "ChatDeps", "handle_tool"]
