# tests/unit/analysis/test_dossier_render.py
import json
from datetime import date

from ah_research.analysis.dossier import build_dossier
from tests.fixtures.phase2.synthetic_market import build_synthetic_market


def test_to_markdown_english_contains_sections() -> None:
    repo = build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    md = d.to_markdown(language="en")
    assert "# Dossier" in md
    assert "Overview" in md or "overview" in md.lower()
    assert "Valuation Bands" in md or "valuation" in md.lower()
    assert "Dividend" in md or "dividend" in md.lower()
    assert "# " in md  # at least one heading


def test_to_markdown_chinese_contains_chinese_headers() -> None:
    repo = build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    md = d.to_markdown(language="zh")
    # At least some Chinese characters should appear in section headers
    assert any(ord(c) > 127 for c in md)


def test_to_html_contains_h1() -> None:
    repo = build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    html = d.to_html(language="en")
    assert "<h1>" in html
    assert "<html>" in html


def test_to_dict_json_serializable() -> None:
    repo = build_synthetic_market(
        start=date(2014, 1, 1),
        end=date(2024, 12, 31),
        symbols=["600000.SH"],
    )
    d = build_dossier("600000.SH", repo, asof=date(2024, 12, 31))
    as_dict = d.to_dict()
    # Must survive JSON round-trip (with default=str for dates)
    blob = json.dumps(as_dict, default=str)
    assert len(blob) > 100
