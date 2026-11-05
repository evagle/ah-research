from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "profiles" / "ABNB.US-2026-09-18.md"
SOURCE_INDEX = ROOT / "data" / "filings" / "ABNB.US" / "research" / "source-index.md"


def test_airbnb_latest_report_is_evidence_bound_and_complete() -> None:
    report = REPORT.read_text()

    assert "ABNB.US" in report
    assert "CIK 0001559720" in report
    assert "0001559720-26-000027" in report
    assert "2026-06-30" in report
    assert "unaudited" in report
    assert "audited baseline" in report
    assert "0001559720-26-000004" in report
    for report_period in ("2026-03-31", "2025-09-30", "2025-06-30", "2025-03-31"):
        assert report_period in report

    required_sections = (
        "## 证据身份与边界",
        "## 独立分析",
        "### KPI树",
        "### 业务与战略变化",
        "### 战略到价值链",
        "### 财务质量",
        "### 资本配置",
        "### 市场为何更认可",
        "### 风险与缺失证据",
        "## 既有分析交叉验证",
    )
    positions = [report.index(section) for section in required_sections]
    assert positions == sorted(positions)

    assert all(label in report for label in ("[事实]", "[计算]", "[解释]", "[市场归因]"))
    assert "supported possible re-rating factor" in report
    assert "不构成因果证明" in report
    assert "未披露" in report
    assert "新业务收入" in report
    assert "Evidence grade" in report
    assert "official_url=" in report
    assert "artifact_sha256=" in report
    assert "page=" in report
    assert "confirmed" in report
    assert "updated" in report
    assert "unresolved" in report
    assert report.count("证据等级：High") >= 8
    assert report.count("证据等级：Medium") >= 8


def test_airbnb_source_index_preserves_primary_source_lineage() -> None:
    source_index = SOURCE_INDEX.read_text()

    assert "ABNB-2026-Q2-10Q.pdf" in source_index
    assert "ABNB-2025-10K.pdf" in source_index
    assert "Airbnb-Q2-2026-Shareholder-Letter.pdf" in source_index
    assert "fde41d6d715e0f3ab09a86d751f31b053ae81433cd715512c8e174461520e941" in source_index
    assert "48a78febd054e9a1e8b58207a6f7bf38eb7a2691cfab4acf5b173941c49c3e92" in source_index
    assert "913155a2c62ffcd038aa42fee57c8ca84d7ac5e26d4fe395240a64100d880961" in source_index
    assert "dependency_failure" in source_index
    assert "SEC 403" in source_index
