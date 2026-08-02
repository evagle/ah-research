from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LINEAGE_PATH = (
    REPO_ROOT / ".claude" / "skills" / "source-discovery" / "scripts" / "source_lineage.py"
)


def load_lineage_module():
    assert LINEAGE_PATH.is_file(), f"missing lineage module: {LINEAGE_PATH}"
    spec = importlib.util.spec_from_file_location("source_lineage", LINEAGE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def candidate(
    *,
    immediate_publisher: str,
    original_publisher: str,
    title: str,
    methodology_owner: str,
    data_vintage: str,
    cited_source_ids: list[str] | None = None,
    underlying_report_id: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "source": {
            "immediate_publisher": immediate_publisher,
            "original_publisher": original_publisher,
        },
        "document": {"title": title},
        "data_vintage": data_vintage,
        "lineage": {
            "methodology_owner": methodology_owner,
            "underlying_dataset_ids": [],
            "underlying_report_ids": (
                [underlying_report_id] if underlying_report_id is not None else []
            ),
            "cited_source_ids": cited_source_ids or [],
        },
    }
    return result


def test_kpmg_citing_frost_shares_frost_underlying_report_lineage() -> None:
    lineage = load_lineage_module()
    frost = candidate(
        immediate_publisher="Frost & Sullivan",
        original_publisher="Frost & Sullivan",
        title="China Pop-Toy Market Report",
        methodology_owner="Frost & Sullivan",
        data_vintage="2025-12-31",
        cited_source_ids=["Frost CN pop-toy dataset 2025"],
        underlying_report_id="FROST-CN-POP-TOY-2025",
    )
    kpmg = candidate(
        immediate_publisher="KPMG",
        original_publisher="KPMG",
        title="China Consumer Outlook",
        methodology_owner="Frost & Sullivan",
        data_vintage="2025-12-31",
        cited_source_ids=["Frost CN pop-toy dataset 2025"],
        underlying_report_id="frost-cn-pop-toy-2025",
    )

    assert lineage.same_lineage(frost, kpmg) is True
    assert lineage.lineage_id(frost) == lineage.lineage_id(kpmg)


def test_immediate_publisher_does_not_create_false_independence() -> None:
    lineage = load_lineage_module()
    frost = candidate(
        immediate_publisher="Frost & Sullivan",
        original_publisher="Frost & Sullivan",
        title="China Pop-Toy Market Report",
        methodology_owner="Frost & Sullivan",
        data_vintage="2025-12-31",
        cited_source_ids=["Frost CN pop-toy dataset 2025"],
    )
    republished = deepcopy(frost)
    source = republished["source"]
    assert isinstance(source, dict)
    source["immediate_publisher"] = "KPMG"

    assert lineage.same_lineage(frost, republished) is True
    assert lineage.lineage_id(frost) == lineage.lineage_id(republished)


def test_official_statistics_and_separate_consultant_do_not_share_lineage() -> None:
    lineage = load_lineage_module()
    official_statistics = candidate(
        immediate_publisher="National Bureau of Statistics",
        original_publisher="National Bureau of Statistics",
        title="Annual Retail Statistics",
        methodology_owner="National Bureau of Statistics",
        data_vintage="2025-12-31",
        cited_source_ids=["NBS-retail-2025"],
    )
    consultant = candidate(
        immediate_publisher="Bain & Company",
        original_publisher="Bain & Company",
        title="China Pop-Toy Consumer Survey",
        methodology_owner="Bain & Company",
        data_vintage="2025-12-31",
        cited_source_ids=["Bain-pop-toy-survey-2025"],
    )

    assert lineage.same_lineage(official_statistics, consultant) is False
    assert lineage.lineage_id(official_statistics) != lineage.lineage_id(consultant)
