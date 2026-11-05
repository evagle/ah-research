from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = REPO_ROOT / ".claude" / "skills"


def read(path: Path) -> str:
    assert path.is_file(), f"missing required skill artifact: {path}"
    return path.read_text(encoding="utf-8")


def test_read_filing_routes_us_latest_reports_through_sec_manifest() -> None:
    skill = read(SKILLS / "read-filing/SKILL.md")

    for phrase in (
        "/read-filing ABNB.US --latest --as-of YYYY-MM-DD",
        "10-K, 10-Q, 10-K/A, 10-Q/A",
        "latest 10-K作为audited baseline",
        "prior four comparable quarters",
        "same-earnings-cycle 8-K exhibits",
        "us-sec-filing-manifest/1.0",
    ):
        assert phrase in skill
    assert skill.index("独立分析") < skill.index("用户既有分析")


def test_shared_evidence_contract_adds_us_html_without_weakening_ah() -> None:
    contract = read(SKILLS / "read-filing/references/evidence-contract.md")

    for phrase in (
        "jurisdiction-appropriate filing manifest",
        "A/H annual manifest字段语义保持不变",
        "filing_html",
        "anchor",
        "US HTML的page必须为null",
        "official_url",
        "accession",
    ):
        assert phrase in contract


def test_us_filing_structure_keeps_quarter_and_annual_assurance_distinct() -> None:
    structure = read(SKILLS / "read-filing/references/filing-structure-us.md")

    for phrase in (
        "10-Q未经审计",
        "10-K审计意见",
        "Item 1. Financial Statements",
        "Item 2. Management's Discussion and Analysis",
        "Item 1A. Risk Factors",
        "Inline XBRL",
        "不得用YTD减法",
    ):
        assert phrase in structure


def test_us_redflag_contract_adapts_profit_quality_checks() -> None:
    skill = read(SKILLS / "financial-redflag-scan/SKILL.md")

    for phrase in (
        "US latest-report branch",
        "10-Q未经审计",
        "最近10-K的审计意见",
        "stock-based compensation",
        "free cash flow",
        "GAAP与non-GAAP reconciliation",
    ):
        assert phrase in skill


def test_us_latest_report_analysis_contract_covers_airbnb_value_chain() -> None:
    method = read(SKILLS / "value-profile/references/us-latest-report-analysis.md")

    for phrase in (
        "Nights and Seats Booked",
        "Gross Booking Value",
        "implied take rate",
        "Adjusted EBITDA",
        "free cash flow",
        "stock-based compensation",
        "repurchases",
        "Strategy-to-Value Chain",
        "Market-recognition evidence",
        "High",
        "Medium",
        "Low",
        "Manual review",
        "supported possible re-rating factor",
        "confirmed | updated | contradicted | unresolved | out of scope",
    ):
        assert phrase in method
    independent = method.index("Independent analysis")
    prior = method.index("Prior-analysis cross-validation")
    assert independent < prior


def test_value_profile_declares_us_latest_report_boundary() -> None:
    skill = read(SKILLS / "value-profile/SKILL.md")

    assert "references/us-latest-report-analysis.md" in skill
    assert "ABNB.US" in skill
    assert "不自动输出完整美股估值profile或买卖建议" in skill
