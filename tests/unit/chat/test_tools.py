from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from ah_research.chat.tools import TOOLS, ChatDeps, handle_tool


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
