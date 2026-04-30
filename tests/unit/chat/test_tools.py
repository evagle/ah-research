from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
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


def test_get_profile_markdown_full() -> None:
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
        filing=FakeFiling(symbol="600519.SH", kind="annual", year=2024, path=Path("x.md"), text=""),
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


def test_construct_portfolio_optimize_unavailable() -> None:
    """optimize scheme not merged yet on this branch — friendly error."""
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
            "weight_by": "optimize",
        },
        deps,
    )
    assert "error" in out
    assert "Phase 4.8" in out["error"] or "not available" in out["error"].lower()
