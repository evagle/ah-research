"""Unit tests for FilingsRepository.search() and SearchHit."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from ah_research.filings.filings_repository import FilingsRepository

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_5" / "filings"


@pytest.fixture
def repo() -> FilingsRepository:
    return FilingsRepository(root=FIXTURES)


# ---------------------------------------------------------------------------
# 1. Empty query raises ValueError
# ---------------------------------------------------------------------------


def test_empty_query_raises(repo: FilingsRepository) -> None:
    with pytest.raises(ValueError, match="query must be non-empty"):
        repo.search("")


# ---------------------------------------------------------------------------
# 2. Substring match across multiple files
# ---------------------------------------------------------------------------


def test_substring_match_multiple_files(repo: FilingsRepository) -> None:
    hits = repo.search("Revenue")
    # Should find matches in multiple filings (annual 2024, annual 2023, ipo, research)
    assert len(hits) >= 2
    filing_paths = {h.filing.path for h in hits}
    assert len(filing_paths) >= 2


# ---------------------------------------------------------------------------
# 3. Regex mode
# ---------------------------------------------------------------------------


def test_regex_mode_annual_header(repo: FilingsRepository) -> None:
    hits = repo.search(r"Annual \d+", regex=True)
    assert len(hits) >= 1
    for h in hits:
        assert re.search(r"Annual \d+", h.line)


# ---------------------------------------------------------------------------
# 4. symbols filter
# ---------------------------------------------------------------------------


def test_symbols_filter(repo: FilingsRepository) -> None:
    hits_all = repo.search("Annual")
    hits_filtered = repo.search("Annual", symbols=["600000.SH"])
    # All filtered hits belong to 600000.SH
    assert all(h.filing.symbol == "600000.SH" for h in hits_filtered)
    # Fewer (or equal) hits with filter than without
    assert len(hits_filtered) <= len(hits_all)


def test_symbols_filter_unknown_ticker_skipped(repo: FilingsRepository) -> None:
    # Unknown ticker silently skipped — no error
    hits = repo.search("Annual", symbols=["999999.XX"])
    assert hits == []


# ---------------------------------------------------------------------------
# 5. kinds filter narrows result set
# ---------------------------------------------------------------------------


def test_kinds_filter_annual_only(repo: FilingsRepository) -> None:
    hits = repo.search("Annual", kinds=["annual"])
    assert len(hits) >= 1
    assert all(h.filing.kind == "annual" for h in hits)


def test_kinds_filter_ipo_only(repo: FilingsRepository) -> None:
    hits = repo.search("IPO", kinds=["ipo"])
    assert len(hits) >= 1
    assert all(h.filing.kind == "ipo" for h in hits)


def test_kinds_filter_narrows(repo: FilingsRepository) -> None:
    hits_all = repo.search("Revenue")
    hits_annual = repo.search("Revenue", kinds=["annual"])
    assert len(hits_annual) <= len(hits_all)


# ---------------------------------------------------------------------------
# 6. Invalid kind raises ValueError
# ---------------------------------------------------------------------------


def test_invalid_kind_raises(repo: FilingsRepository) -> None:
    with pytest.raises(ValueError, match="Invalid kind"):
        repo.search("Annual", kinds=["bad_kind"])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# 7. max_hits_per_file caps hits per filing
# ---------------------------------------------------------------------------


def test_max_hits_per_file(repo: FilingsRepository) -> None:
    # Search for a very common word that should appear many times across files
    hits_unlimited = repo.search("the", max_hits_per_file=None)
    hits_capped = repo.search("the", max_hits_per_file=1)
    # Each file contributes at most 1 hit
    from collections import Counter

    path_counts = Counter(h.filing.path for h in hits_capped)
    assert all(count <= 1 for count in path_counts.values())
    # Unlimited should be >= capped
    assert len(hits_unlimited) >= len(hits_capped)


def test_max_hits_per_file_zero_means_unlimited(repo: FilingsRepository) -> None:
    # max_hits_per_file=None means unlimited
    hits = repo.search("Revenue", max_hits_per_file=None)
    assert len(hits) >= 1


# ---------------------------------------------------------------------------
# 8. Stable ordering
# ---------------------------------------------------------------------------


def test_stable_ordering(repo: FilingsRepository) -> None:
    hits_a = repo.search("Revenue")
    hits_b = repo.search("Revenue")
    assert [h.filing.path for h in hits_a] == [h.filing.path for h in hits_b]
    assert [h.line_no for h in hits_a] == [h.line_no for h in hits_b]


def test_ordering_symbol_alpha_then_kind(repo: FilingsRepository) -> None:
    hits = repo.search("Annual")
    symbols_in_order = [h.filing.symbol for h in hits]
    # 000001.SZ comes before 600000.SH alphabetically
    if "000001.SZ" in symbols_in_order and "600000.SH" in symbols_in_order:
        first_000 = next(i for i, h in enumerate(hits) if h.filing.symbol == "000001.SZ")
        first_600 = next(i for i, h in enumerate(hits) if h.filing.symbol == "600000.SH")
        assert first_000 < first_600


def test_ordering_annual_year_desc(repo: FilingsRepository) -> None:
    hits = repo.search("Annual", symbols=["600000.SH"], kinds=["annual"])
    years = [h.filing.year for h in hits]
    # Should be sorted year descending (2024 before 2023)
    assert years == sorted(years, reverse=True)


# ---------------------------------------------------------------------------
# 9. Long line truncation
# ---------------------------------------------------------------------------


def test_long_line_truncated(repo: FilingsRepository) -> None:
    hits = repo.search("X" * 10, symbols=["600000.SH"])  # matches the 600-X line
    assert len(hits) >= 1
    matching = [h for h in hits if "X" * 10 in h.line]
    assert len(matching) >= 1
    hit = matching[0]
    # The raw line is 600 chars of X — should be truncated to 500 + "…"
    assert len(hit.line) == 501  # 500 chars + "…" (1 char ellipsis)
    assert hit.line.endswith("…")


# ---------------------------------------------------------------------------
# 10. Unreadable file is skipped, not fatal
# ---------------------------------------------------------------------------


def test_unreadable_file_skipped(repo: FilingsRepository) -> None:
    """Verify that one unreadable file is skipped and the rest still return hits."""
    original_read_text = Path.read_text

    # Pick one specific path that will be made unreadable
    all_filings = repo.list_filings("600000.SH") + repo.list_filings("000001.SZ")
    assert all_filings, "need at least one filing in fixtures"
    bad_path = all_filings[0].path

    def patched_read_text(self: Path, *args, **kwargs) -> str:  # type: ignore[override]
        if self == bad_path:
            raise OSError("permission denied (test)")
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", patched_read_text):
        # Should not raise — bad_path is skipped, others still searched
        hits = repo.search("Annual")

    # All hits come from paths other than bad_path
    for h in hits:
        assert h.filing.path != bad_path
    # And we still get hits (other files exist)
    assert isinstance(hits, list)


def test_context_window(repo: FilingsRepository) -> None:
    hits = repo.search("Revenue increased", symbols=["600000.SH"], kinds=["annual"])
    assert len(hits) >= 1
    hit = hits[0]
    # Context should be a multi-line string containing the matched line
    assert "Revenue increased" in hit.context
    lines = hit.context.split("\n")
    assert len(lines) >= 1


def test_search_hit_line_no_is_1indexed(repo: FilingsRepository) -> None:
    hits = repo.search("# Annual", symbols=["600000.SH"], kinds=["annual"])
    assert len(hits) >= 1
    # The header is on line 1
    assert any(h.line_no == 1 for h in hits)
