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
                "error": (f"Section {section!r} not found. Available: {sorted(profile.sections)}")
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

    from ah_research.backtest.types import Signals
    from ah_research.portfolio.constructor import Constructor

    symbols = list(params["symbols"])
    asof = _dt.strptime(params["asof"], "%Y-%m-%d").date()
    weight_by = params["weight_by"]
    if weight_by not in ("equal", "optimize"):
        return {"error": f"weight_by must be 'equal' or 'optimize', got {weight_by!r}"}

    sig_df = pd.DataFrame(
        {
            "date": [pd.Timestamp(asof)] * len(symbols),
            "symbol": symbols,
            "signal": [1.0] * len(symbols),
        }
    )
    signals = Signals.from_dataframe(sig_df)

    optimizer: Any = None
    if weight_by == "optimize":
        from ah_research.portfolio.optimizer import Optimizer
        from ah_research.portfolio.optimizer.estimators.covariance import LedoitWolfCovariance
        from ah_research.portfolio.optimizer.estimators.returns import HistoricalMeanReturns

        objective = params.get("objective", "mean_variance")
        lookback = int(params.get("lookback_days", 252))
        if objective == "mean_variance":
            optimizer = Optimizer(
                objective="mean_variance",
                cov_estimator=LedoitWolfCovariance(),
                returns_estimator=HistoricalMeanReturns(lookback_days=lookback),
                risk_aversion=float(params.get("risk_aversion", 1.0)),
                lookback_days=lookback,
            )
        elif objective == "risk_parity":
            optimizer = Optimizer(
                objective="risk_parity",
                cov_estimator=LedoitWolfCovariance(),
                lookback_days=lookback,
            )
        else:
            return {"error": f"unknown objective: {objective!r}"}

    ctor = Constructor(signals, repo=deps.data_repo, asof=asof, optimizer=optimizer)
    report = ctor.method("all_positive").weight_by(weight_by).build()
    weights = dict(zip(report.weights["symbol"], report.weights["weight"], strict=True))
    out: dict[str, Any] = {"weights": {k: float(v) for k, v in weights.items()}}
    if report.optimization_result is not None:
        out["solver_status"] = report.optimization_result.solver_status
    return out


# Thin wrapper so tests can monkeypatch
def _build_corpus_summary(filings_repo: Any, profiles_repo: Any) -> pd.DataFrame:
    from ah_research.filings.summary import build_corpus_summary

    return build_corpus_summary(filings_repo=filings_repo, profiles_repo=profiles_repo)


def _build_dossier(symbol: str, data_repo: Any, filings_repo: Any, profile_repo: Any) -> Any:
    from ah_research.analysis.dossier import build_dossier

    return build_dossier(
        symbol=symbol,
        repo=data_repo,
        filings_repo=filings_repo,
        profiles_repo=profile_repo,
    )


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


__all__ = ["TOOLS", "ChatDeps", "handle_tool"]
