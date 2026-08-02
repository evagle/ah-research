from __future__ import annotations

import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"
FINANCIAL_SKILL_NAMES = (
    "financial-redflag-scan",
    "management-analysis",
    "product-analysis",
    "read-filing",
    "value-profile",
)
SKILL_PATHS = {
    path.parent.name: path
    for path in sorted(SKILLS_ROOT.glob("*/SKILL.md"))
    if path.parent.name in FINANCIAL_SKILL_NAMES
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(path: Path) -> dict[str, str]:
    text = read(path)
    _, raw, _ = text.split("---", 2)
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict)
    return parsed


def all_skill_markdown() -> list[Path]:
    return sorted(SKILLS_ROOT.rglob("*.md"))


def test_skill_frontmatter_is_discoverable_and_safe() -> None:
    assert set(SKILL_PATHS) == set(FINANCIAL_SKILL_NAMES)
    for folder, path in SKILL_PATHS.items():
        metadata = frontmatter(path)
        assert metadata["name"] == folder
        description = metadata["description"]
        assert description.startswith("Use when")
        assert len(description) < 500
        assert "<" not in description
        assert ">" not in description


def test_all_financial_skills_share_one_evidence_contract() -> None:
    contract_path = SKILLS_ROOT / "read-filing/references/evidence-contract.md"
    assert contract_path.is_file()
    contract = read(contract_path)
    for heading in (
        "## 1.身份与截止日",
        "## 2.Manifest绑定",
        "## 3.Mode B只读与写入权",
        "## 4.引用",
        "## 5.终态",
        "## 6.证据漂移",
    ):
        assert heading in contract
    for skill_path in SKILL_PATHS.values():
        assert "read-filing/references/evidence-contract.md" in read(skill_path)


def test_all_financial_skills_share_one_run_store_contract() -> None:
    contract_path = SKILLS_ROOT / "read-filing/references/run-store-contract.md"
    assert contract_path.is_file()
    contract = read(contract_path)
    for heading in (
        "## 1.无感入口",
        "## 2.Ticker级共享层",
        "## 3.Run级隔离层",
        "## 4.Resolver动作",
        "## 5.Mode边界",
        "## 6.兼容读取",
    ):
        assert heading in contract
    for skill_path in SKILL_PATHS.values():
        assert "read-filing/references/run-store-contract.md" in read(skill_path)


def test_standalone_modes_write_reports_under_ticker_runs() -> None:
    for skill_name in (
        "read-filing",
        "product-analysis",
        "management-analysis",
        "financial-redflag-scan",
    ):
        skill = read(SKILL_PATHS[skill_name])
        mode_a = skill.split("### Mode A", 1)[1].split("### Mode B", 1)[0]
        mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]
        assert "data/filings/<ticker>/runs/<run-id>/report.md" in mode_a
        assert "--resume" not in mode_a
        assert "--start-fresh" not in mode_a
        assert "Mode B不调用run store" in mode_b
        assert "不创建run" in mode_b


def test_value_profile_uses_seamless_resolver_and_keeps_final_profile_path() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    invocation = skill.split("### Invocation", 1)[1].split("#### 两种运行模式", 1)[0]
    bootstrap = skill.split("### Step 1", 1)[1].split("2. **Audit", 1)[0]

    assert "--resume" not in invocation
    assert "--start-fresh" not in invocation
    assert "scripts/financial_run_store.py resolve" in bootstrap
    assert "created/resumed/reused" in bootstrap
    assert "完全重新分析" in bootstrap
    assert "profiles/<ticker>-<YYYY-MM-DD>[-vN].md" in bootstrap


def test_run_store_contract_keeps_shared_and_local_data_separate() -> None:
    contract = read(SKILLS_ROOT / "read-filing/references/run-store-contract.md")
    for shared in (
        "manifests/",
        "evidence/",
        "_extracted/",
        "facts/",
        "metrics/",
        "citations/",
        "analyses/",
        "market/",
    ):
        assert shared in contract
    for local in (
        "checkpoint.json",
        "report.md",
        "drafts/",
        "query/",
        "logs/",
        "tmp/",
    ):
        assert local in contract
    assert "旧standalone文件只读" in contract


def test_seamless_resolver_replaces_all_user_selected_resume_paths() -> None:
    for skill_name in (
        "read-filing",
        "product-analysis",
        "management-analysis",
        "financial-redflag-scan",
    ):
        skill = read(SKILL_PATHS[skill_name])
        mode_a = skill.split("### Mode A", 1)[1].split("### Mode B", 1)[0]
        assert "--resume" not in mode_a
        assert "--start-fresh" not in mode_a
        assert "完全重新分析" in mode_a
    profile_invocation = (
        read(SKILL_PATHS["value-profile"])
        .split(
            "### Invocation",
            1,
        )[1]
        .split("#### 两种运行模式", 1)[0]
    )
    assert "--resume" not in profile_invocation
    assert "--start-fresh" not in profile_invocation


def test_run_checkpoints_keep_recovery_identity_and_pending_state() -> None:
    reading = read(SKILL_PATHS["read-filing"])
    management = read(SKILL_PATHS["management-analysis"])
    redflag = read(SKILL_PATHS["financial-redflag-scan"])

    for field in (
        "ticker",
        "AS_OF",
        "target_fiscal_year",
        "filing_manifest_sha256",
        "event_manifest_sha256",
        "completed_steps",
    ):
        assert field in reading
    assert "checkpoint.json" in reading
    assert "逐步正文SHA-256" in reading
    for field in ("management_pending", "pending_gate", "unresolved_rows"):
        assert field in management
    for field in ("manual_review_required", "failure_reason", "dependency_failure"):
        assert field in redflag


def test_shared_manifest_versions_are_immutable_across_runs() -> None:
    contract = read(SKILLS_ROOT / "read-filing/references/run-store-contract.md")
    assert "只新增不覆盖契约" in contract
    assert "候选`manifests/`" in contract
    assert "不得跨run共写" in contract
    for skill_name in (
        "read-filing",
        "management-analysis",
        "financial-redflag-scan",
        "value-profile",
    ):
        assert "旧manifest保持不可变" in read(SKILL_PATHS[skill_name])


def test_recovered_reports_revalidate_machine_citations_and_manifest_hashes() -> None:
    reading = read(SKILL_PATHS["read-filing"])
    management = read(SKILL_PATHS["management-analysis"])
    redflag = read(SKILL_PATHS["financial-redflag-scan"])

    assert "回读并重算每个已完成步骤正文哈希" in reading
    assert "恢复run时逐条复核机器引用" in redflag
    assert "恢复run时" in management
    for skill in (reading, management, redflag):
        assert "filing_manifest_sha256" in skill
        assert "event_manifest_sha256" in skill


def test_analysis_runs_resolve_after_shared_evidence_is_prepared() -> None:
    for skill_name in (
        "product-analysis",
        "management-analysis",
        "financial-redflag-scan",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        evidence = skill.index("先运行`read-filing` Mode A")
        resolver = skill.index("scripts/financial_run_store.py resolve")
        assert evidence < resolver
    reading = read(SKILL_PATHS["read-filing"])
    assert "官方目录响应哈希和query plan哈希" in reading
    assert "候选annual、event及全部counterpart manifest" in reading
    assert "候选manifest的真实SHA-256作为输入artifact" in reading
    assert "不得用待建立占位值计算输入指纹" in reading


def test_redflag_mode_a_uses_read_filing_mode_b_for_facts() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    upstream = skill.split("7. **建立上游事实层**", 1)[1].split("### Step 2", 1)[0]

    assert "Mode A调用`read-filing` Mode B" in upstream
    assert "Mode A调用`read-filing` Mode A" not in upstream


def test_run_store_supports_external_profile_results_and_specialized_publishers() -> None:
    contract = read(SKILLS_ROOT / "read-filing/references/run-store-contract.md")
    profile = read(SKILL_PATHS["value-profile"])

    assert "--result-path <absolute-profile-path>" in contract
    assert "专用发布器" in contract
    assert "--result-path <profile-path>" in profile
    assert "同日冲突使用最小可用`-vN`" not in read(SKILL_PATHS["read-filing"])


def test_read_filing_mode_b_never_early_exits() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B — As-subroutine", 1)[1].split("### Invocation 解析", 1)[0]
    assert "Mode B始终执行完整事实提取" in mode_b
    assert "`--complete-facts`在Mode B中仅为兼容参数" in skill
    assert '"screening_flags"' in skill.split("**Mode B输出**", 1)[1]
    assert "Mode B早退" not in skill


def test_product_analysis_has_mode_and_parent_ownership_contracts() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    assert "参数只有ticker" in skill
    assert "默认进入Mode A" in skill
    assert "含`--target-profile`" in skill
    assert "进入Mode B" in skill
    assert "不得直接修改" in skill
    assert "父skill" in skill
    assert "最终护城河" in skill
    assert "--counterpart-filing-manifest <exchange>:<absolute-json-path>" in skill
    assert "counterpart_filing_manifest_sha256s" in skill


def test_product_analysis_enforces_the_eight_step_chain() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    expected = (
        "产品边界",
        "生产或服务流程",
        "流程经济性",
        "客户价值",
        "相对竞争力",
        "需求侧机制",
        "财报映射",
        "失效测试",
    )
    positions = [skill.index(item) for item in expected]
    assert positions == sorted(positions)
    assert "不机械使用" in skill
    assert "50%" in skill


def test_product_analysis_requires_process_economics_and_cost_discipline() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    process = read(SKILLS_ROOT / "product-analysis/references/process-playbooks.md")
    for field in ("周期", "产能", "良率", "瓶颈", "单位成本"):
        assert field in skill
    for route in ("制造业", "软件与互联网", "零售", "专业服务"):
        assert route in process
    assert "潮玩与IP衍生品" in process
    assert "公式" in skill
    assert "假设" in skill
    assert "敏感性" in skill
    assert "不得伪造" in skill
    assert "success或pending都必须保留以下10个栏目" in skill


def test_product_analysis_requires_relative_competition_and_evidence() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    mechanisms = read(SKILLS_ROOT / "product-analysis/references/value-mechanisms.md")
    for comparison in ("直接竞品", "替代方案", "适用龙头"):
        assert comparison in skill
    assert "2至3项" in skill
    assert "高毛利" in skill
    assert "不能单独证明" in skill
    for grade in ("`高`", "`中`", "`低`", "`需人工`"):
        assert grade in skill
    assert "行为证据" in mechanisms
    assert "财务证据" in mechanisms


def test_value_profile_delegates_product_sections_without_moving_moat_ownership() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "`product-analysis`" in skill
    assert "`part1/§1.1`" in skill
    assert "`part1/§1.3`" in skill
    assert "`moat_handoff`" in skill
    assert "最终护城河" in skill
    assert "产品与流程证据" in template


def test_value_profile_delegates_contract_details_to_owned_references() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "公共证据规则不在本skill重定义" in skill
    for schema in (
        "product-analysis/references/mode-b-response.schema.json",
        "management-analysis/references/mode-b-response.schema.json",
        "financial-redflag-scan/references/mode-b-response.schema.json",
    ):
        assert schema in skill
    max_orchestrator_lines = 700
    assert len(skill.splitlines()) < max_orchestrator_lines


def test_a_share_financial_report_routes_to_section_ten() -> None:
    forbidden = (
        '第五节"财务报告"',
        '第五节"利润表"',
        "第五节财务报告",
        "第五节现金流",
        "每个年报第五节",
    )
    for path in SKILL_PATHS.values():
        text = read(path)
        for phrase in forbidden:
            assert phrase not in text, f"{path}: stale A-share route {phrase}"


def test_read_filing_download_command_matches_cli_contract() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert (
        "uv run python scripts/download_filings.py TICKER --years 10 --end-year YYYY --as-of AS_OF"
    ) in skill
    assert "download_filings.py --ticker" not in skill
    result = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/python"), "scripts/download_filings.py", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "ticker" in result.stdout
    assert "--years" in result.stdout
    assert "--end-year" in result.stdout
    assert "--as-of" in result.stdout
    assert "--ticker" not in result.stdout
    assert "--year " not in result.stdout
    assert "--type" not in result.stdout


def test_redflag_checklist_uses_a_semantic_anchor() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "第1452行" not in skill
    assert "### §4.5负面清单 — 排雷风险（29项）" in skill
    assert "按标题定位" in skill


def test_shared_threshold_registry_is_canonical() -> None:
    registry_path = SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml"
    registry = yaml.safe_load(read(registry_path))
    assert registry["version"] == 1
    assert registry["markets"]["CN"]["standard_corporate_tax_rate"] == 0.25
    assert registry["markets"]["HK"]["standard_corporate_tax_rate"] == 0.165
    goodwill = registry["checks"]["goodwill_to_net_assets"]
    assert goodwill["warning"] == 0.20
    assert goodwill["high_risk"] == 0.30
    receivables = registry["checks"]["other_receivables_to_current_assets"]
    assert receivables["warning"] == 0.10
    sales_cash = registry["checks"]["sales_cash_collection"]
    assert sales_cash["healthy_min"] == 1.0
    assert sales_cash["reconciliation_tolerance"] == 0.05

    consumers = (
        SKILL_PATHS["read-filing"],
        SKILL_PATHS["financial-redflag-scan"],
        SKILL_PATHS["value-profile"],
        SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md",
        SKILLS_ROOT / "read-filing/references/statement-reading.md",
    )
    for path in consumers:
        assert "thresholds.yaml" in read(path), f"{path} does not use registry"


def test_sales_cash_reconciliation_is_not_called_true_revenue() -> None:
    paths = (
        SKILL_PATHS["read-filing"],
        SKILL_PATHS["financial-redflag-scan"],
        SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md",
    )
    for path in paths:
        assert "真实营收" not in read(path)
    fraud_library = read(SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md")
    assert "应有销售收现" in fraud_library
    assert "票据背书" in fraud_library
    assert "非现金抵账" in fraud_library


def test_redflag_library_covers_book_derived_supplemental_signals() -> None:
    fraud_library = read(SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md")
    expected = (
        "应付职工薪酬",
        "运费",
        "装卸费",
        "其他经营活动收到的现金",
        "其他业务收入",
        "长期待摊费用",
        "独立董事集体辞职",
        "客户或供应商注册",
    )
    for signal in expected:
        assert signal in fraud_library


def test_management_analysis_has_exchange_aware_governance_routing() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert "独立非执行董事" in skill
    assert "审计委员会" in skill
    assert "Corporate Governance Report" in skill
    assert "若年报披露监事会" in skill
    assert "监事会报告必读" not in skill


def test_management_mode_b_covers_the_template_schema() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    for section in range(1, 9):
        assert f"§4.{section}" in skill
    assert "§4.1-§4.8" in skill
    assert "逐section更新" in skill
    assert "替换 `<target-profile>` 中 `## §4" not in skill


def test_value_profile_progress_is_dynamic_and_uses_composite_ids() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "/67" not in skill
    assert "N/67" not in skill
    assert "part_id/section_id" in skill
    assert "total_sections" in skill
    assert "歧义" in skill


def test_value_profile_section_entry_always_uses_shared_resolver() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "跳过Step 2进度摘要,直接进入Step 3" not in skill
    assert "只跳过进度摘要,不能跳过ID解析和路由" in skill
    assert "裸ID有歧义时停止并列出全部候选" in skill


def test_redflag_mode_b_uses_only_canonical_composite_section_id() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "--section §4.5" not in skill
    assert skill.count("--section part4/§4.5") >= 3


def test_value_profile_hk_routes_are_exchange_aware() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "港股回退HKEXnews" in skill
    assert "A股回退cninfo/上交所/深交所" in skill
    assert "港股Corporate Governance Report、Directors' Report" in skill


def test_redflag_template_uses_exchange_aware_regulators_and_pledge_thresholds() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "证监会/SFC/HKEX处罚公告" in template
    assert "A股>80%;港股>50%" in template


def test_redflag_mode_b_output_contract_includes_confidence() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    contract = skill.split("## §7", 1)[1]
    assert "置信度" in contract


def test_read_filing_resolves_latest_year_and_uses_project_runtime() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "YEAR可省略" in skill
    assert "省略时解析为交易所已披露的最新完整财年" in skill
    assert (
        "uv run python scripts/download_filings.py TICKER --years 3 --end-year YYYY --as-of AS_OF"
    ) in skill


def test_read_filing_early_return_checks_are_bilingual_and_complete() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "Audit Opinion" in skill
    assert "Regulatory Sanctions" in skill
    assert "逐项检查L1、L2、L3" in skill
    assert "> 2次变更" not in skill


def test_read_filing_provisions_required_history_and_peer_evidence() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "最多10份连续年报" in skill
    assert "财年≤`YYYY`且披露日≤AS_OF" in skill
    assert "披露日≤AS_OF的最近更早完整财年" in skill
    assert "../../financial-redflag-scan" not in skill


def test_redflag_scan_provisions_windows_and_all_analysis_layers() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "最近10个财年" in skill
    assert "上市历史不足" in skill
    for heading in (
        "29项完整清单",
        "6项高危附加检查",
        "三表勾稽4条",
        "造假识别5个维度",
        "8类补充质检信号",
    ):
        assert skill.count(heading) >= 2


def test_redflag_formula_inputs_and_thresholds_are_deterministic() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    profile = read(SKILL_PATHS["value-profile"])
    statement = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")
    assert "有效VAT税率按各业务适用税率×对应含税前收入占比加权" in redflag
    assert "通胀系数使用报告期CPI同比" in redflag
    assert "非现金抵账+收回已核销坏账" in profile
    assert "≥3年仍未转固" in statement
    assert "> 3年仍未转固" not in statement


def test_redflag_evidence_contract_distinguishes_quantitative_and_qualitative() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "量化检查" in skill
    assert "定性检查" in skill
    assert "事件/主体/日期/文书或原文依据" in skill


def test_redflag_modes_and_high_risk_handoff_are_explicit() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    profile = read(SKILL_PATHS["value-profile"])
    assert "Mode A默认`--auto`" in redflag
    assert "`edit`→应用修改后重新复核" in redflag
    assert "**置信度:**[高/中/低/需人工]" in redflag
    assert "任一高风险" in profile
    assert "阻断估值" in profile


def test_management_analysis_provisions_windows_and_capital_allocation_tests() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert "至少6份年报" in skill
    assert "最近10个财年" in skill
    assert "上市历史不足" in skill
    assert "财务分配4大测试" in skill.split("### Step 3", 1)[1]
    assert "§2.8缺任一测试" in skill


def test_management_mode_b_preserves_completed_sections_and_inherits_mode() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert "--auto|--interactive" in skill
    assert "只生成并更新未完成的目标section" in skill
    assert "Mode B的`--auto`和`--interactive`都只返回草稿" in skill
    assert "父skill复核后原子保存" in skill


def test_management_veto_sequence_and_governance_routes_are_deterministic() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "系统性画大饼在§4.2完成后复核" in skill
    assert "A股未设监事会" in skill
    assert "港股或其他单层董事会发行人" in skill
    pre_veto = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]
    assert "| 系统性画大饼 |" not in pre_veto


def test_management_references_existing_sources() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert ".claude/skills/value-profile/references/moat-framework.md" in skill
    assert 'statement-reading.md` §3 "必读附注" — 关联交易/其他应收款/应交税费' not in skill


def test_value_profile_valuation_requires_all_mandatory_gates() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "≥ 80%" not in skill
    assert "所有必填section均为终态" in skill
    assert "Part 4 §4.5不存在高风险" in skill
    assert "Part 0的`估值三大前提`" in skill


def test_value_profile_uses_canonical_valuation_and_citation_contracts() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "顶级30" not in skill
    assert "敢用30" not in skill
    assert "min(1/rf,25PE)" in skill
    assert "表格单元格可直接带页码" in skill
    assert "叙述段数字通过本节`**引用:**`逐条映射" in skill
    assert "template既有6个状态块" in skill


def test_read_filing_has_hk_specific_l2_and_peer_routes() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "港股L2" in skill
    assert "不强制扣非净利润或销售商品收到的现金" in skill
    assert "港股同业" in skill
    assert "恒生行业分类" in skill


def test_read_filing_centers_history_on_target_and_defers_full_provisioning() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "--years 10 --end-year YYYY --as-of AS_OF" in skill
    assert "### Step 2.5" in skill
    assert "早退事实报告" in skill
    assert "## L1-L3触发事实" in skill


def test_read_filing_boundary_and_cross_check_scope_are_explicit() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    statement = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")
    assert "机械阈值比较和初筛特征标签" in skill
    assert "不构成最终风险、护城河或投资结论" in skill
    assert "重大异常或存在争议的事项" in statement
    assert "普通报表数字以审计年报单一来源即可" in statement


def test_management_short_history_and_staged_veto_are_executable() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert "实际形成N-1个比较" in skill
    assert "阶段A" in skill
    assert "阶段B" in skill
    assert "阶段C" in skill
    assert "≥3项不通过" in skill
    assert "连续2年均≥3项不通过" not in skill


def test_management_veto_uses_formal_actions_and_parent_owns_mode_b_confirmation() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "问询、刑事立案或调查中事项只标`需人工/待定`" in skill
    assert "Mode B的交互确认由父skill Step 3d统一负责" in skill
    assert "正式处罚或生效纪律处分" in template


def test_value_profile_dispatches_valuation_by_business_type_and_gates() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    for route in ("PE法", "周期法", "银行PB法", "公用事业DCF法"):
        assert route in skill
    for gate in ("能力圈四问", "好生意", "护城河", "PE适用性边界"):
        assert gate in skill.split("### Step 6", 1)[1]


def test_value_profile_resume_normalizes_legacy_confidence_and_manual_is_terminal() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    for legacy in ("中—", "中-高", "中高"):
        assert legacy in skill
    assert "`需人工`是人工终态" in skill
    assert "不纳入next-undone" in skill
    assert "人工处理清单" in skill


def test_value_profile_persists_redflag_gate_and_validates_exchange_aware_tickers() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "**估值阻断:**" in template
    assert "从§4.5重新推导并校正" in skill
    assert r"\d{6}\.(SH|SZ)" in skill
    assert r"\d{1,5}\.HK" in skill
    assert "港股不显示download_research.py" in skill


def test_value_profile_cleanup_removes_template_region_and_redflag_has_citations() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "从`<!-- ⚠️ TEMPLATE-ONLY区域开始`到" in skill
    assert "TEMPLATE-ONLY" in skill.split("Cleanup验证gate", 1)[1]
    redflag_block = template.split("### §4.5负面清单", 1)[1].split("### §4.6", 1)[0]
    assert "**引用:**" in redflag_block


def test_redflag_has_hk_sales_cash_not_applicable_route() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "港股未单列销售商品、提供劳务收到的现金" in skill
    assert "不适用—披露口径缺失" in skill
    assert "应收账款、合同负债、分部收入和经营现金流桥" in skill


def test_redflag_persists_valuation_block_and_resume_validates_internal_schema() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "结论为`剔除`" in redflag
    assert "**估值阻断:**" in template.split("### §4.5负面清单", 1)[1]
    assert "§4.5内部schema" in profile
    for layer in ("29项", "6项", "4条", "8类", "5个维度"):
        assert layer in profile.split("§4.5内部schema", 1)[1]


def test_redflag_mode_b_accepts_raw_pdf_and_derives_metadata() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "raw PDF" in skill
    assert "从标题和文件名解析ticker、exchange和report_date" in skill
    assert "元数据缺失或冲突时报契约错误" in skill


def test_redflag_schema_has_deterministic_severity() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "严重度" in template.split("### §4.5负面清单", 1)[1]
    for severity in ("无", "预警", "高风险", "一票否决", "待定"):
        assert severity in skill


def test_redflag_ticker_and_reconciliation_tolerances_are_explicit() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    registry = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    assert r"\d{6}\.(SH|SZ)" in skill
    assert r"\d{1,5}\.HK" in skill
    assert registry["checks"]["cfo_bridge"]["reconciliation_tolerance"] == 0.05
    assert "维持性CapEx是估算值,不存在报表真值容差" in skill


def test_redflag_manual_review_persistently_blocks_valuation() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    profile = read(SKILL_PATHS["value-profile"])
    assert "任一`需人工`或`待定`" in redflag
    assert "`**估值阻断:**是—证据需人工`" in redflag
    assert "§4.5存在`需人工/待定`" in profile


def test_redflag_dispatch_branches_between_extracted_and_raw_pdf_sources() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    dispatch = skill.split("### Step 3", 1)[1].split("### Step 4", 1)[0]
    assert "使用extracted cache时" in dispatch
    assert "使用raw PDF时" in dispatch
    assert "raw PDF绝对路径" in dispatch


def test_redflag_audit_opinion_severity_matches_abandon_action() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    severity = skill.split("§2.1.4严重度映射", 1)[1].split("### §2.2", 1)[0]
    for trigger in ("保留意见", "无法表示", "否定意见"):
        assert trigger in severity
    assert "为`一票否决`" in severity
    assert "强调事项段本身不改变无保留意见" in severity
    assert "底层事项适用的独立阈值" in severity


def test_redflag_all_output_layers_require_severity() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    scaffold = skill.split("2. **Mode A 准备**", 1)[1].split("3. **Mode B准备**", 1)[0]
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "状态+严重度+证据" in scaffold
    high_risk = template.split("#### 6项高危附加检查", 1)[1].split("#### 三表勾稽", 1)[0]
    assert "严重度" in high_risk
    assert "严重度缺失" in review


def test_redflag_ratio_checks_guard_nonpositive_denominators() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "归母净资产≤0" in skill
    assert "归母净利润≤0时不计算经营现金流/归母净利润" in skill
    assert "不得对非正分母套比例阈值" in skill


def test_redflag_bootstrap_uses_exchange_specific_ticker_contract() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]
    assert r"\d{6}\.(SH|SZ)" in bootstrap
    assert r"\d{1,5}\.HK" in bootstrap
    assert "[0-9]{4,6}" not in bootstrap


def test_management_guidance_gap_is_directional() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "gap=(guidance−actual)/guidance" in skill
    assert "仅`gap>0`表示未达指引" in skill
    assert "连续3年gap>20%" in skill
    assert "指引高于实际" in template


def test_management_short_history_requires_complete_post_listing_series() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]
    dispatch = skill.split("### Step 3", 1)[1].split("### Step 4", 1)[0]
    assert "逐年核对上市以来每个应披露财年" in bootstrap
    assert "任一中间年份缺失" in bootstrap
    assert "fetch或abort" in bootstrap
    assert "招股说明书路径" in dispatch


def test_management_capital_allocation_aggregation_is_deterministic() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    rules = skill.split("### §2.8", 1)[1].split("---", 1)[0]
    assert "0项不通过" in rules
    assert "1-2项不通过" in rules
    assert "3-4项不通过" in rules
    assert "Mode B写入§4.6" in rules
    assert "`弃权`只由§2.7触发" in rules


def test_management_interactive_mode_b_does_not_save_before_parent_accepts() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    stages = skill.split("### Step 3", 1)[1].split("### Step 4", 1)[0]
    assert "Mode B无论`--auto`还是`--interactive`都不写target-profile" in stages
    assert "每次只返回当前阶段草稿和结构化flags" in stages
    assert "Mode B由父skill确认并落盘" in stages


def test_management_pre_veto_template_covers_proven_tunneling() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    pre_veto = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]
    assert "已证实的违规关联交易或股东利益输送" in pre_veto


def test_management_uses_exchange_specific_ticker_contract() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert r"\d{6}\.(SH|SZ)" in skill
    assert r"\d{1,5}\.HK" in skill
    assert "[0-9]{4,6}" not in skill


def test_value_profile_entry_and_exit_rules_are_route_specific() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step6 = skill.split("### Step 6", 1)[1]
    for contract in (
        "PE法买点",
        "周期法买点",
        "银行PB法买点",
        "公用事业DCF法买点",
        "高杠杆法买点",
    ):
        assert contract in step6
    assert "不得套用PE卖点" in step6


def test_value_profile_bulk_selects_and_validates_industry_overlay() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step4 = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "进入bulk前先判定行业路由" in step4
    assert "industry-overlays.md" in step4
    assert "按所选overlay构造prompt" in step4
    assert "按所选overlay抽样校核" in step4


def test_value_profile_prerequisites_have_hk_and_bank_substitutions() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    rules = skill.split("### §2.2", 1)[1].split("### §2.3", 1)[0]
    assert "A股非银行" in rules
    assert "港股非银行" in rules
    assert "银行替代门槛" in rules
    assert "未披露毛额销售收现本身不判存疑" in rules
    assert "银行不使用常规CFO、毛利率或存货门槛" in rules


def test_value_profile_resume_migrates_complex_legacy_and_part0_fields() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    for legacy in ("中高(...)", "高(...);中(...)", "需人工(...)"):
        assert legacy in migration
    assert "先迁移Part 0结构字段" in migration
    assert "管理层否决" in migration
    assert "好生意结论" in migration


def test_value_profile_persists_and_restores_management_veto_separately() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "**管理层否决:**" in template
    assert "已接受的内存草稿" in skill
    assert "预先计算完整事务" in skill
    assert "一次CAS原子写入" in skill
    assert "--expected-sha256 <baseline-profile-sha256>" in skill
    assert "resume时从§4.pre、§4.2和§4.8重新推导" in skill
    assert "财报阻断与管理层否决取并集" in skill


def test_value_profile_progress_has_one_persisted_enum_and_terminal_retry() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    progress = skill.split("### Step 2", 1)[1].split("### Step 3", 1)[0]
    assert "持久状态值域仅为" in progress
    assert "不得把`已完成`写入置信度字段" in progress
    assert "配额或限流重试耗尽" in skill
    assert "写`需人工`并作为终态退出" in skill


def test_value_profile_persists_good_business_conclusion_after_ability_circle() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    ability_block = template.split("### §1.8", 1)[1].split("## §2", 1)[0]
    assert "**好生意结论:** 是/否/存疑" in ability_block
    assert "从§1.8的`好生意结论`读取" in skill


def test_read_filing_hk_reconciliation_has_executable_na_route() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    step5 = skill.split("### Step 5", 1)[1].split("### Step 6", 1)[0]
    assert "港股未披露毛额销售收现时" in step5
    assert "`不适用—披露口径缺失`" in step5
    assert "应收账款、合同负债、分部收入和经营现金流桥" in step5


def test_read_filing_anchors_peer_and_early_return_periods_to_target_year() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "财年≤`YYYY`且披露日≤AS_OF" in skill
    assert "财年≤`YYYY`且披露日≤AS_OF" in skill
    assert "财务窗口固定为`YYYY-2`至`YYYY`" in skill
    assert "AS_OF是统一信息截止日" in skill
    assert "监管窗口为AS_OF日前3年" in skill


def test_read_filing_uses_exchange_specific_ticker_contract() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert r"\d{6}\.(SH|SZ)" in skill
    assert r"\d{1,5}\.HK" in skill
    assert ".BJ" not in skill


def test_read_filing_persists_forecast_actual_table_and_validates_it() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    step5 = skill.split("### Step 5", 1)[1].split("### Step 6", 1)[0]
    step6 = skill.split("### Step 6", 1)[1].split("### Step 7", 1)[0]
    output = skill.split("### Step 7", 1)[1]
    assert "承诺vs兑现5年表" in step5
    assert "承诺vs兑现表" in step6
    assert "## §13承诺vs兑现数据表" in output


def test_read_filing_references_stay_inside_reading_layer() -> None:
    quick_lookup = read(SKILLS_ROOT / "read-filing/references/quick-lookup.md")
    statement_reading = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")
    assert "用它算 PE" not in quick_lookup
    assert "做主锚" not in quick_lookup
    assert "真护城河" not in statement_reading
    assert "假护城河" not in statement_reading
    assert "护城河瓦解" not in statement_reading


def test_read_filing_mode_b_complete_facts_have_deterministic_destination() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "Mode B始终执行完整事实提取" in skill
    assert "只更新调用方指定section" in skill
    assert "`screening_flags`" in skill
    assert "完整官方证据可为`高`" in skill
    assert "Mode B无条件禁用该短路" in skill


def test_read_filing_mode_b_has_complete_input_and_destination_contract() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]
    for required in (
        "--target-profile",
        "--section",
        "--ticker",
        "--year",
        "--filing",
        "--as-of",
        "--auto|--interactive",
    ):
        assert required in mode_b
    assert "零匹配或多匹配" in skill
    assert "只更新调用方指定section" in skill


def test_read_filing_historical_downloads_are_cutoff_aware() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "--as-of <YYYY-MM-DD>" in skill
    assert "从AS_OF当日或之前仍有效的完整年报中选择" in skill
    assert "截止日之后发布的更正、重述或重新发布版本" in skill
    assert "不得使用" in skill


def test_read_filing_explicit_year_does_not_depend_on_undefined_latest_year() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "LATEST_YEAR-YYYY" not in skill
    assert "显式指定YYYY时" in skill
    assert "--as-of" in skill


def test_read_filing_provisions_ten_year_inputs_for_ten_year_checks() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "10年EPS趋势" in skill
    assert "10年留存收益" in skill
    assert "--years 10" in skill
    assert "证据窗口不足10年" in skill


def test_read_filing_executes_auditor_regulatory_investigation_check() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    step2 = skill.split("### Step 2", 1)[1].split("### Step 2.5", 1)[0]
    assert "审计机构监管调查" in step2
    assert "证监会/SFC/HKEX/财政部" in step2
    assert "机构名称+立案或调查日期+官方文书URL" in step2


def test_read_filing_l2_ratios_guard_nonpositive_net_income() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    l2 = skill.split("**L2财务前提**", 1)[1].split("**L3", 1)[0]
    assert "归母净利润≤0时不计算经营现金流/归母净利润" in l2
    assert "扣非归母净利润/归母净利润" in l2
    assert "归母净利润≤0时不计算" in l2
    assert "不得用非正分母触发或豁免早退" in l2


def test_read_filing_operational_layer_only_records_neutral_observations() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    operational = skill.split("## §3", 1)[1]
    assert "美化/隐瞒" not in operational
    assert "→降级" not in operational
    assert "profile降级" not in operational
    assert "一致/不一致/证据不足" in operational


def test_read_filing_early_return_schema_separates_scope_and_confidence() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    early = skill.split("早退时只写以下短结构", 1)[1].split("未早退时使用完整骨架", 1)[0]
    assert "**早退触发:**" in early
    assert "**证据置信度:**<高/中/低/需人工>" in early


def test_redflag_retries_are_bounded_and_end_in_manual_review() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "最多重派2次" in skill
    assert "重试耗尽" in skill
    assert "缺失项的`需人工/待定`" in skill
    assert "不得无限重派" in skill


def test_redflag_template_tables_have_consistent_severity_columns() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    high_risk = template.split("#### 6项高危附加检查", 1)[1].split("#### 三表勾稽", 1)[0]
    supplemental = template.split("#### 8类补充质检信号", 1)[1].split("#### 造假识别5个维度", 1)[0]
    fraud = template.split("#### 造假识别5个维度", 1)[1].split("**发现的风险小结:**", 1)[0]
    for table in (high_risk, supplemental, fraud):
        assert "严重度" in table
        rows = [line for line in table.splitlines() if line.startswith("| ")]
        assert len({line.count("|") for line in rows}) == 1
    assert "综合结论" in fraud


def test_redflag_all_ratio_denominators_have_zero_and_negative_rules() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    for contract in (
        "清单第12项",
        "归母净利润≤0时不计算经营现金流/归母净利润",
        "利息费用≤0时不计算利息保障倍数",
        "清单第25项",
        "归母净利润≤0时不计算资本化研发/归母净利润",
        "勾稽分母为0时",
    ):
        assert contract in skill
    assert "分母≤0时不套比例阈值" in template


def test_redflag_resume_validates_every_row_not_only_layer_headings() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    assert "逐行校验" in mode_b
    assert "29行+6行+4行+8行+5行" in mode_b
    assert "状态、严重度、证据和触发后的实际动作" in mode_b
    assert "仅有层级标题不算完成" in mode_b


def test_management_veto_includes_stage_c_and_resume_reconstruction() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    rules = skill.split("### §2.7", 1)[1].split("### §2.8", 1)[0]
    assert "§4.8" in rules
    assert "阶段C" in rules
    assert "resume" in rules
    assert "§4.pre、§4.2和§4.8" in rules


def test_management_mode_b_requires_contiguous_filing_manifest() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    assert "annual-report manifest" in mode_b
    for field in ("财年", "绝对路径", "报告期末日", "完整披露时间"):
        assert field in mode_b
    assert "逐年连续" in mode_b
    assert "缺失中间年份" in mode_b


def test_management_interactive_veto_never_saves_before_parent_acceptance() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    stages = skill.split("### Step 3", 1)[1].split("### Step 4", 1)[0]
    assert "Mode A交互模式和全部Mode B调用只返回草稿handoff" in stages
    assert "对应确认者accept前不得保存" in stages
    assert "触发则保存证据" not in stages


def test_management_mode_b_preserves_all_terminal_section_states() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    assert "`高/中/低`且非占位符视为已完成" in mode_b
    assert "`需人工`是待决终态" in mode_b
    assert "非gate的`已跳过`仅在模板明确允许时保留" in mode_b


def test_management_capital_allocation_handles_insufficient_evidence() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    rules = skill.split("### §2.8", 1)[1].split("---", 1)[0]
    assert "通过/中间/不通过/证据不足" in rules
    assert "任一`证据不足`" in rules
    assert "有保留—证据不足" in rules
    assert "不得聚合为`0项不通过`" in rules


def test_management_stage_c_cannot_report_zero_with_unresolved_rows() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert "§4.8存在`需人工`" in skill
    assert "不得写`0触发`" in skill


def test_value_profile_migrated_gates_reject_placeholders_and_unknown_enums() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "占位符或空值" in migration
    assert "估值三大前提" in migration
    assert "管理层否决" in migration
    assert "估值阻断" in migration
    assert "好生意结论" in migration
    assert "未知枚举值" in migration
    assert "不得写入`未决`或进入Step 6" in migration


def test_value_profile_valuation_route_precedence_is_deterministic() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step6 = skill.split("### Step 6", 1)[1]
    assert "主估值路线优先级" in step6
    assert "银行PB法" in step6
    assert "高杠杆+周期" in step6
    assert "不得回退到单年PE" in step6
    assert "次级overlay只追加检查" in step6


def test_value_profile_child_retry_exhaustion_has_terminal_handoff() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "financial-redflag-scan重试耗尽" in skill
    assert "management-analysis重试耗尽" in skill
    assert "对应section写`需人工`" in skill
    assert "阻断估值并返回父流程" in skill


def test_bank_pb_anchors_have_one_subtype_aware_source() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile/references/valuation.md")
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")
    assert "银行PB锚以`industry-overlays.md`§2.4为唯一来源" in skill
    assert "0.6-1.3PB" in valuation
    assert "1.0-1.15" not in valuation.split("金融—银行", 1)[1].splitlines()[0]
    for anchor in ("1.0-1.3 PB", "0.7-0.9 PB", "0.6-0.8 PB"):
        assert anchor in overlays


def test_weak_moat_template_never_offers_numeric_valuation() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    moat = template.split("**护城河:", 1)[1].split("**管理层:", 1)[0]
    assert "改 15PE 或 PB 清算" not in moat
    assert '"弱 / 否" → 不估值' in moat


def test_value_profile_overlay_precedence_has_primary_and_additive_secondary() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step4 = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "主overlay优先级" in step4
    assert "次级overlay" in step4
    assert "只追加不冲突的披露和风险检查" in step4
    assert "不得覆盖主overlay的估值路线" in step4


def test_management_veto_atomically_updates_visible_part0_state() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    handoff = skill.split("**管理层否决handoff**", 1)[1].split("#### 3c", 1)[0]
    assert "一次CAS原子写入" in handoff
    assert "--expected-sha256 <baseline-profile-sha256>" in handoff
    assert "`**管理层:**一票否决触发`" in handoff
    assert "`**管理层否决:**是—<reason>`" in handoff
    assert "阻断原因集合" in handoff


def test_value_profile_all_resume_paths_include_stage_c_veto() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert skill.count("§4.pre、§4.2和§4.8") >= 3
    step5 = skill.split("### Step 5", 1)[1].split("### Step 6", 1)[0]
    step6 = skill.split("### Step 6", 1)[1]
    assert "§4.8" in step5
    assert "§4.8" in step6


def test_read_filing_mode_b_requires_versioned_source_manifests() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]
    assert "--filing-manifest" in mode_b
    assert "--event-manifest" in mode_b
    for field in (
        "财年",
        "报告期末日",
        "完整公告时间戳",
        "公告ID或官方URL",
        "绝对路径",
        "SHA-256",
    ):
        assert field in mode_b
    assert "manifest缺失或不连续" in mode_b


def test_read_filing_selects_latest_eligible_version_before_cutoff() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "从AS_OF当日或之前仍有效的完整年报中选择公告时间最晚者" in skill
    assert "公告ID或官方URL、披露时间和SHA-256" in skill
    assert "目标`--filing`必须与manifest选中行的路径和SHA-256一致" in skill


def test_read_filing_peer_sources_respect_announcement_cutoff() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    peer = skill.split("3. 按§2.6.2", 1)[1].split("4. ", 1)[0]
    assert "披露日≤AS_OF" in peer
    assert "AS_OF后披露" in peer


def test_read_filing_mode_b_raw_pdf_preflight_is_ephemeral() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "Mode B source preflight" in skill
    assert "遇raw PDF时在只读临时目录抽取所需页文本" in skill
    assert "不得写入PDF旁的`_extracted`目录" in skill


def test_read_filing_mode_b_section_replacement_is_atomic_and_bounded() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "复合`part_id/section_id`" in skill
    assert "标题下一行到下一个同级或更高层级标题前" in skill
    assert "整体替换正文" in skill
    assert "引用列表随正文整体替换" in skill
    assert "原子写入" in skill
    assert 'target profile 的 "阅读笔记"草稿 section' not in skill


def test_read_filing_l2_thresholds_distinguish_early_exit_from_deep_review() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    registry = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    sales = registry["checks"]["sales_cash_collection"]
    assert sales["early_return_below"] == 0.9
    assert sales["deep_review_below"] == 1.0
    assert "0.9≤销售收现比<1.0只进入深查,不早退" in skill
    assert "各指标分别连续2年" in skill


def test_read_filing_all_required_ratios_guard_nonpositive_denominators() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    for contract in (
        "营业收入≤0时不计算销售收现比",
        "归母净利润≤0时不计算现金转化率",
        "有形固定资产+净营运资本≤0时不计算ROOCE",
        "同期累计归母净利润≤0时不计算非经项目占比",
    ):
        assert contract in skill


def test_read_filing_vat_sensitivity_has_deterministic_early_exit_rule() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "敏感性区间上限仍<0.9" in skill
    assert "区间跨越0.9" in skill
    assert "不得早退" in skill


def test_redflag_hk_sales_cash_fallback_covers_checklist_rows_9_and_12() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "清单第9项港股替代" in skill
    assert "清单第12项港股替代" in skill
    assert "应收周转天数、合同负债、分部收入和CFO/收入" in skill
    assert "毛额销售收现子项写`不适用/无`" in skill


def test_redflag_negative_net_income_has_deterministic_status_and_severity() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "该子项统一写`不适用/无`" in skill
    assert "净利润为负本身不得把该比率行写`需人工/待定`" in skill


def test_redflag_severity_mapping_covers_every_output_layer() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mapping = skill.split("§2.1.4严重度映射", 1)[1].split("### §2.2", 1)[0]
    for layer in ("29项", "6项", "三表勾稽", "8类补充质检", "造假识别5个维度"):
        assert layer in mapping
    for state in ("通过", "异常", "沾边", "未见异常", "需人工", "不适用"):
        assert state in mapping
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "29项、6项、三表勾稽、8类补充信号和5个维度" in review


def test_redflag_retry_exhaustion_uses_search_log_as_evidence() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "重试耗尽例外" in skill
    assert "已查来源+检索词+未取得字段+最后错误" in skill
    assert "不再要求不存在的实际值" in skill


def test_redflag_resume_validates_actions_and_all_terminal_fields() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    for field in (
        "实际动作",
        "发现的风险小结",
        "造假维度综合结论",
        "结论",
        "置信度",
        "估值阻断",
    ):
        assert field in mode_b


def test_redflag_no_risk_conclusion_requires_all_layers_clean() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    aggregation = skill.split("### §2.6", 1)[1].split("### §2.7", 1)[0]
    for layer in ("29项", "6项", "三表勾稽4条", "8类补充质检", "造假识别5个维度"):
        assert layer in aggregation
    assert "全部适用行均为`无`" in aggregation


def test_redflag_mode_b_reads_english_name_from_profile_metadata() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    assert "英文公司名从Part 0元数据表" in mode_b
    assert "缺失时查交易所发行人官方名称" in mode_b


def test_management_interactive_veto_waits_for_parent_accept_before_part0() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    profile = read(SKILL_PATHS["value-profile"])
    assert "返回`draft_veto=true`" in management
    assert "Mode B无论auto或interactive" in management
    assert "management_veto=false" in management
    handoff = profile.split("**管理层否决handoff**", 1)[1].split("**子skill失败handoff**", 1)[0]
    assert "已接受的内存草稿" in handoff
    assert "accept或edit后的已接受正文" in handoff


def test_management_required_gate_terminal_states_block_progress() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    profile = read(SKILL_PATHS["value-profile"])
    for gate in ("§4.pre", "§4.2", "§4.8"):
        assert gate in management
    assert "必做gate不得`已跳过`" in management
    assert "`需人工`时返回`management_pending=true`" in management
    assert "停止后续阶段且不预判否决" in management
    assert "未决行不得覆盖已证实否决" in management
    assert "管理层必做gate" in profile
    assert "不提供`skip`" in profile


def test_management_stage_c_template_uses_proven_harm_veto_only() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    block = template.split("### §4.8", 1)[1].split("### §5", 1)[0]
    assert "已证实的侵占、违规担保或非公允利益输送" in block
    assert "仅凭触发数量不得一票否决" in block
    assert '≥ 5项触发或任一"严重"触发' not in block
    assert "0触发" not in block


def test_management_missing_evidence_retries_are_bounded() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert "Auto最多重派2次" in skill
    assert "耗尽后写`需人工`" in skill
    assert "Interactive只由用户`research more`触发重派" in skill
    assert "不得无限驳回" in skill


def test_value_profile_manual_redflag_terminal_still_requires_complete_rows() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "§4.5为`需人工`且含失败handoff" in migration
    assert "29行+6行+4行+8行+5行" in migration
    assert "真实生成的逐项搜索日志" in migration
    assert "缺行时不得伪造搜索日志" in migration
    assert "仅非`需人工`section执行完整逐行校验" not in migration


def test_value_profile_placeholder_gates_map_to_legal_persisted_values() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    for mapping in (
        "`估值三大前提`→`任一假或存疑—待人工补证`",
        "`管理层否决`→`需人工—待完成管理层gate`",
        "`估值阻断`→`是—证据需人工`",
        "`好生意结论`→`存疑`",
    ):
        assert mapping in migration
    assert "→`未决`" not in migration


def test_value_profile_combines_block_reasons_without_overwrite() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "阻断原因集合" in skill
    assert "财报高风险/管理层否决/证据需人工" in skill
    assert "去重后按固定顺序" in skill
    assert "任何handoff不得覆盖已有原因" in skill
    assert "`**财报排雷:**证据需人工`" in skill


def test_bank_real_net_assets_deduplicate_exposures_and_existing_provisions() -> None:
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")
    assert "三个互斥桶" in overlays
    assert "关注类（剔除逾期90天以上和展期）" in overlays
    assert "逾期90天以上（剔除展期）" in overlays
    assert "减去对应已计提拨备" in overlays
    assert "披露不足时不得输出真实净资产或PB数字" in overlays


def test_bank_subtype_pb_classification_is_quantitative_and_exhaustive() -> None:
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")
    assert "零售贷款占比≥50%" in overlays
    assert "全国性股份行/混合型" in overlays
    assert "0.8-1.0 PB" in overlays
    assert "无法分类" in overlays
    assert "不得猜测锚值" in overlays


def test_read_filing_uses_one_as_of_cutoff_for_all_available_information() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "AS_OF是统一信息截止日" in skill
    assert "监管窗口为AS_OF日前3年" in skill
    assert "目标报告披露日不得覆盖显式传入的AS_OF" in skill
    assert "历史研究的信息截止日为目标报告披露日" not in skill


def test_read_filing_manifest_enumerates_every_version_candidate() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]
    for field in (
        "公告标题",
        "报告类型",
        "有效状态",
        "替代关系",
        "是否选中",
    ):
        assert field in mode_b
    assert "每个财年的全部候选公告" in mode_b
    assert "仅列选中版本" in mode_b
    assert "abort" in mode_b


def test_l2_registry_defines_parent_profit_denominators_and_adjusted_profit() -> None:
    registry = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    cfo = registry["checks"]["cfo_to_net_income"]
    assert cfo["denominator"] == "net_income_attributable_to_parent"
    adjusted = registry["checks"]["adjusted_net_income_to_net_income"]
    assert adjusted["warning"] == 0.50
    assert adjusted["consecutive_years"] == 2
    assert adjusted["denominator"] == "net_income_attributable_to_parent"
    assert adjusted["applicability"] == "positive_net_income_only"


def test_redflag_retry_exhaustion_returns_manual_terminal_not_completed() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    contract = skill.split("## §7主 skill 调用契约", 1)[1].split("## §A", 1)[0]
    assert "manual_review_required=true" in contract
    assert "置信度写`需人工`" in contract
    assert "不得标`已完成`" in contract


def test_redflag_pattern_aggregation_counts_unique_checklist_ids_only() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    aggregation = skill.split("§2.6.3结论聚合", 1)[1].split("### §2.7", 1)[0]
    assert "3个不同的29项清单ID" in aggregation
    assert "同一事实跨层出现只计1次" in aggregation
    assert "6项、三表勾稽、8类补充质检和5个维度不增加29项计数" in aggregation


def test_management_resume_inspects_gate_rows_before_terminal_confidence() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    assert "先迁移gate的旧`已跳过`" in mode_b
    assert "再判断终态" in mode_b
    assert "§4.8任一清单行含`需人工`" in mode_b
    assert "即使section置信度为`高/中/低`" in mode_b


def test_management_interactive_pending_gate_has_resolution_path() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert "pending_gate=true" in skill
    assert "edit/research more" in skill
    assert "重新调用本skill处理未决行" in skill
    assert "未决行清零前不得accept为已完成" in skill


def test_value_profile_builds_and_persists_management_filing_manifest() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step1 = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]
    assert "构造并持久化source manifests" in step1
    assert "官方目录查询URL" in step1
    assert "财年、报告期末日、完整披露时间" in step1
    assert "公告标题、报告类型、有效状态、替代关系" in step1
    assert "绝对路径和SHA-256" in step1
    assert "后续调用子skill时把两个文件解析为真实绝对路径" in skill


def test_management_prelude_requires_proven_appropriation_not_receivable_presence() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    prelude = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]
    assert "仅有其他应收款挂关联方不触发前置否决" in prelude
    assert "违规资金占用已证实即触发" in prelude
    assert "调查中或未达到§4.8证据标准只跟踪" in prelude


def test_value_profile_placeholder_gates_enter_recalculation_queue() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "gate_recompute_queue" in migration
    assert "`估值三大前提`→`§3.pre`" in migration
    assert "`好生意结论`→`part1/§1.8`" in migration
    assert "`管理层否决`→`part1/§4.pre、part1/§4.2和part1/§4.8`" in migration
    assert "在解析next-undone前执行" in migration


def test_template_visible_redflag_state_allows_manual_evidence() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    visible = template.split("**财报排雷:", 1)[1].split("**能力圈四问:", 1)[0]
    assert "证据需人工" in visible


def test_template_has_no_legacy_part0_management_risk_field() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "Part 0管理层风险字段" not in template
    assert "把**管理层风险**字段" not in template
    assert "`management_veto=false`" in template
    assert "不得直接持久化或修改Part 0" in template


def test_step6_always_merges_all_valuation_block_reasons() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step6 = skill.split("### Step 6", 1)[1]
    assert "每次gate变化后都调用阻断原因合并器" in step6
    assert "不得直接写单一原因覆盖集合" in step6


def test_bank_route_replaces_inapplicable_template_and_valuation_fields() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    quantitative = template.split("## Part 2", 1)[1].split("## Part 3", 1)[0]
    for section, replacement in (
        ("### §Q2", "ROA、净息差和手续费佣金率"),
        ("### §Q3", "拨备覆盖率、拨贷比、不良核销率和关注类迁徙率"),
        ("### §Q4", "贷款、存款和总资产增速"),
        ("### §Q5", "风险加权资产增速"),
        ("### §Q8", "银行不使用销售收现、常规经营现金流或资本开支"),
    ):
        block = quantitative.split(section, 1)[1].split("\n### ", 1)[0]
        assert replacement in block
    valuation = template.split("## Part 4", 1)[1]
    block = valuation.split("### §4.3", 1)[1].split("\n### ", 1)[0]
    assert "银行不填写3年后净利润量价表" in block


def test_bank_quality_bundle_uses_only_bank_metrics() -> None:
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")
    bundle = overlays.split("## 跨行业护城河 quality bundle", 1)[1]
    bank = bundle.split("- **银行**:", 1)[1].split("\n-", 1)[0]
    assert "毛利率" not in bank
    assert "Capex/NI" not in bank
    for metric in ("风险调整后ROA", "不良生成率", "核心一级资本增速"):
        assert metric in bank


def test_bank_real_net_assets_start_from_ordinary_parent_equity() -> None:
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")
    block = overlays.split("### 2.2真实净资产计算", 1)[1].split("### 2.3", 1)[0]
    assert "归属普通股股东净资产" in block
    for deduction in ("优先股", "永续债", "少数股东权益"):
        assert deduction in block


def test_bank_subtype_classification_has_nonoverlapping_precedence() -> None:
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")
    anchors = overlays.split("### 2.4估值锚", 1)[1].split("### 2.5", 1)[0]
    assert "按以下顺序命中首个类别后停止" in anchors
    assert "零售强/AUM模式" in anchors
    assert "否则,国有大行" in anchors
    assert "否则,全国性股份行/混合型" in anchors
    assert "否则,城商行/农商行" in anchors


def test_read_filing_revalidates_expanded_ten_year_manifest() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    step25 = skill.split("### Step 2.5", 1)[1].split("### Step 3", 1)[0]
    assert "更新filing manifest" in step25
    assert "全部候选集合" in step25
    assert "重新执行Step 1B" in step25
    assert "路径、SHA-256、逐年连续性和选中版本" in step25


def test_read_filing_event_manifest_covers_l3_and_query_provenance() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]
    for event in ("实控人刑事立案", "年报逾期披露"):
        assert event in mode_b
    for field in ("查询参数", "响应哈希", "结果总数"):
        assert field in mode_b


def test_read_filing_nonpositive_parent_profit_breaks_l2_run() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    l2 = skill.split("3. **L2财务前提**", 1)[1].split("4. **L3监管与重述**", 1)[0]
    assert "归母净利润≤0的财年打断连续适用财年计数" in l2
    assert "亏损年前后的低值不得拼接" in l2


def test_redflag_resume_derives_all_blocking_outcomes() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    gate = profile.split("**排雷门槛**", 1)[1].split("**管理层门槛**", 1)[0]
    assert "一票否决" in gate
    assert "结论为`剔除`" in gate
    assert "3个不同的29项清单ID" in gate


def test_redflag_has_hk_restricted_deposit_substitute() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    for field in ("受限制银行存款", "质押存款", "保证金存款", "非现金等价物定期存款"):
        assert field in skill
    assert "清单第6项港股替代" in skill


def test_related_receivables_threshold_is_warning_not_proven_appropriation() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    high_risk = skill.split("### §2.2", 1)[1].split("### §2.3", 1)[0]
    assert "仅触发预警和深查" in high_risk
    assert "不得据此认定股东占款" in high_risk
    assert "→关联方占款" not in high_risk


def test_management_template_preserves_interactive_draft_veto() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    prelude = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]
    promise = template.split("### §4.2企业家评估", 1)[1].split("### §4.3", 1)[0]
    for block in (prelude, promise):
        assert "`--interactive`" in block
        assert "draft_veto=true" in block
        assert "management_veto=false" in block
        assert "父skill根据已接受正文" in block
    assert "向主skill返回`management_veto=true`" not in promise


def test_management_pending_resolution_is_atomic_and_recomputes_gates() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    resolution = management.split("任一阶段的必做gate为`需人工`", 1)[1].split("每阶段派ONE", 1)[0]
    for action in (
        "移除已解决行对应的人工处理清单项",
        "management_pending=false",
        "pending_gate=false",
        "重新计算management_veto",
        "重新计算阻断原因集合",
        "同一次原子写入",
    ):
        assert action in resolution


def test_management_defines_completion_predicates_for_all_required_gates() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    for predicate in (
        "`§4.pre`完成条件",
        "4行均为合法状态",
        "扫描结论与逐行状态一致",
        "`§4.2`完成条件",
        "可用历史能够形成的比较行全部存在",
        "gap计算有效",
        "结论和引用存在",
    ):
        assert predicate in mode_b


def test_management_mode_b_accepts_only_persisted_manifest_path() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    assert "--filing-manifest <absolute-json-path>" in skill
    assert "<path-or-json>" not in skill
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    for field in (
        "官方目录查询URL",
        "查询参数",
        "响应哈希",
        "候选总数",
        "全部候选版本",
        "SHA-256",
        "选中版本",
    ):
        assert field in mode_b


def test_value_profile_gate_recompute_uses_composite_management_ids() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "`管理层否决`→`part1/§4.pre、part1/§4.2和part1/§4.8`" in migration
    assert "`管理层否决`→`§4.pre、§4.2和§4.8`" not in migration


def test_value_profile_migrates_completed_generic_bank_sections() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "银行schema迁移例外" in migration
    assert "已完成的通用§Q1-§Q12" in migration
    assert "已完成的通用part4/§4.3" in migration
    assert "替换为银行专属schema" in migration


def test_bank_moat_worker_uses_only_bank_quality_bundle() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    moat = read(SKILLS_ROOT / "value-profile/references/moat-framework.md")
    worker = skill.split("**5步护城河分析**", 1)[1].split("- **§4管理层分析**", 1)[0]
    assert "银行分支" in worker
    assert "银行quality bundle" in worker
    assert "不要求毛利率、CFO/NI或资本开支" in worker
    assert "银行例外" in moat
    assert "只运行`industry-overlays.md`的银行quality bundle" in moat


def test_value_profile_bank_valuation_formula_starts_from_ordinary_parent_equity() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step6 = skill.split("### Step 6", 1)[1]
    bank_route = step6.split("- **银行PB法**", 1)[1].split("- **公用事业DCF法**", 1)[0]
    assert "归属普通股股东净资产" in bank_route
    for deduction in ("少数股东权益", "优先股", "永续债", "未充分计提损失"):
        assert deduction in bank_route


def test_value_profile_resume_syncs_manual_redflag_visible_state() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "从§4.5重新推导并校正财报阻断" in migration
    assert "`**财报排雷:**零触发项/N项中风险/N项高风险/证据需人工`" in migration
    assert "不得只在需人工时更新" in migration


def test_bank_rwa_growth_belongs_to_q5_only() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    quantitative = template.split("## Part 2", 1)[1].split("## Part 3", 1)[0]
    q4 = quantitative.split("### §Q4", 1)[1].split("\n### ", 1)[0]
    q5 = quantitative.split("### §Q5", 1)[1].split("\n### ", 1)[0]
    assert "风险加权资产增速" not in q4
    assert "风险加权资产增速" in q5


def test_bank_overlay_has_no_stale_pb_ceiling() -> None:
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")
    bank = overlays.split("## 2. 银行", 1)[1].split("## 3.", 1)[0]
    assert "PB 天花板1.15" not in bank


def test_part0_valuation_premises_have_explicit_bank_substitutes() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    part0 = template.split("## Part 0", 1)[1].split("## Part 1", 1)[0]
    assert "银行替代" in part0
    for metric in ("资产质量", "拨备", "核心一级资本", "流动性"):
        assert metric in part0


def test_management_resume_applies_all_gate_completion_predicates_in_parent() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "§4.pre、§4.2和§4.8逐一执行management-analysis完成条件" in migration
    assert "高/中/低不能覆盖残缺gate" in migration


def test_management_manifest_is_canonical_and_rechecked_against_official_response() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    assert "data/filings/<ticker>/manifests/annual-reports-<AS_OF>.json" in mode_b
    assert "重新请求官方目录" in mode_b
    assert "重算响应哈希" in mode_b
    assert "候选ID集合" in mode_b


def test_management_pending_state_has_persisted_parent_contract() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "management_pending=false" in template
    assert "pending_gate=false" in template
    handoff = profile.split("**管理层否决handoff**", 1)[1].split("#### 3c", 1)[0]
    for state in (
        "移除已解决行对应的人工处理清单项",
        "management_pending=false",
        "pending_gate=false",
        "重新计算管理层否决",
        "重新计算阻断原因集合",
        "同一次原子写入",
    ):
        assert state in handoff
    assert "清除旧`管理层否决`阻断原因" in handoff


def test_management_template_gate_rows_allow_manual_state() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    prelude = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]
    stage_c = template.split("### §4.8", 1)[1].split("### §5", 1)[0]
    assert prelude.count("是/否/需人工") >= 4
    assert "否/有异常迹象/重大异常/已证实侵占/需人工/不适用" in stage_c
    assert "是/否/不适用/需人工" not in stage_c


def test_management_mode_b_live_revalidates_subject_roster() -> None:
    for skill_name in ("management-analysis", "financial-redflag-scan"):
        skill = read(SKILL_PATHS[skill_name])
        mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

        for token in (
            "source_url",
            "http_method",
            "request_encoding",
            "request_headers",
            "query_params",
            "response_schema",
            "response_adapter",
        ):
            assert token in mode_b
        assert "主体名册" in mode_b
        assert "实时响应哈希、结果总数和完整主体列表" in mode_b
        assert "任一变化都abort" in mode_b


def test_management_template_mode_b_veto_is_draft_only() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    prelude = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]
    promise = template.split("### §4.2企业家评估", 1)[1].split("### §4.3", 1)[0]

    for block in (prelude, promise):
        assert "Mode B的`--auto`和`--interactive`都只返回草稿" in block
        assert "`draft_veto=true`和`management_veto=false`" in block
        assert "不得直接持久化或修改Part 0" in block


def test_redflag_review_recomputes_conclusion_instead_of_trusting_agent() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "无论子agent是否已填写结论" in review
    assert "按§2.6.3强制重算" in review
    assert "不一致时覆盖为重算结果" in review


def test_redflag_all_terminal_states_require_evidence() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "`否/不适用/通过/未见异常`也必须有证据" in review
    assert "无证据不得聚合为`无重大风险`" in review


def test_value_profile_redflag_fallback_matches_full_schema() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    fallback = skill.split("**Fallback（子 skill 不可用时", 1)[1].split("### Step 6", 1)[0]
    assert "29行+6行+4行+8行+5行" in fallback
    assert "合法状态、严重度、证据和触发后的实际动作" in fallback
    gate = skill.split("**排雷门槛**", 1)[1].split("**管理层门槛**", 1)[0]
    assert "状态、严重度、证据和触发后的实际动作均合法" in gate


def test_related_receivables_long_aging_does_not_change_warning_without_direct_evidence() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    row = next(
        line for line in template.splitlines() if "| 15 | 其他应收款≥10%或逐季上涨 |" in line
    )
    assert "直接证据" in row
    assert "再升级高风险" not in row


def test_redflag_resume_validates_actions_and_dimension_conclusion() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "触发后的实际动作" in migration
    assert "造假维度综合结论" in migration


def test_value_profile_normalizes_legacy_three_premise_values() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "`①真/②有松动/③真`" in migration
    assert "任一项为假、存疑或有松动" in migration
    assert "任一假或存疑—<逐项原因>" in migration


def test_bank_schema_exception_overrides_completed_section_prohibition() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    prohibition = skill.split("### §4.2 What this skill MUST NOT do", 1)[1].split("### §4.3", 1)[0]
    assert "银行schema迁移例外" in prohibition


def test_bank_moat_replaces_part1_gross_margin_section() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    block = template.split("### §3.7", 1)[1].split("### §3.8", 1)[0]
    assert "银行路线" in block
    assert "资产质量、盈利韧性、资本与流动性" in block
    assert "不填写毛利率" in block


def test_section_targeted_quantitative_route_does_not_expand_to_bulk() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    resolver = skill.split("**所有入口先运行统一section resolver**", 1)[1].split("### Step 3", 1)[0]
    assert "显式`--section part2/§Q*`只处理该section" in resolver
    step4 = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "仅无`--section`的auto流程允许bulk" in step4


def test_pe_sell_rule_is_scoped_away_from_bank_pb() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    rules = skill.split("### §2.5安全边际", 1)[1].split("### §2.6", 1)[0]
    assert "仅PE法" in rules
    valuation = read(SKILLS_ROOT / "value-profile/references/valuation.md")
    sell = valuation.split("### 1.3卖点", 1)[1].split("### 1.4", 1)[0]
    assert "仅适用于PE法" in sell
    assert "银行PB法使用§3" in sell


def test_bank_sell_rule_uses_selected_subtype_upper_bound() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step6 = skill.split("### Step 6", 1)[1]
    assert "卖点=市值/真实净资产>所选子类型PB上限" in step6
    assert "卖点=市值/真实净资产>1.3" not in step6


def test_template_references_existing_moat_file() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "moat-框架.md" not in template
    assert "moat-framework.md" in template
    assert (SKILLS_ROOT / "value-profile/references/moat-framework.md").is_file()


def test_redflag_review_recomputes_each_row_from_evidence() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "逐行按触发条件和thresholds.yaml重算状态与严重度" in review
    assert "`否/无`但证据命中阈值" in review


def test_emphasis_of_matter_is_not_automatically_audit_veto() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    row = next(line for line in template.splitlines() if "| 1 | 出现过非" in line)
    assert "强调事项段本身不改变无保留意见" in skill
    assert "强调事项段本身不触发" in row


def test_redflag_has_deterministic_default_severity_mapping() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mapping = skill.split("**§2.1.4严重度映射**", 1)[1].split("### §2.2", 1)[0]
    assert "未明示高风险或一票否决的`是`统一映射为`预警`" in mapping
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "强风险" not in template


def test_value_profile_redflag_fallback_has_bounded_manual_handoff() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    fallback = skill.split("**Fallback（子 skill 不可用时", 1)[1].split("### Step 6", 1)[0]
    assert "最多重派2次" in fallback
    assert "按financial-redflag-scan§2.4.4" in fallback
    assert "任何外部缺证必须先走`source-discovery`" in fallback
    assert "形成validated terminal claim ledger,之后才可持久化" in fallback
    assert "不得为缺外部证据开普通worker side door" in fallback


def test_redflag_resume_does_not_invent_search_logs() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "缺行时不得伪造搜索日志" in migration
    assert "缺行时仍保持`manual_review`" in migration
    assert "未显式选择前不得重新派发" in migration
    assert "标`进行中`并重新派发排雷流程" not in migration


def test_targeted_quantitative_auto_has_single_section_execution_path() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step4 = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    assert "显式`--section part2/§Q* --auto`直接执行单section worker" in step4


def test_bank_schema_migration_replaces_completed_part1_margin_section() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "已完成的通用part1/§3.7" in migration


def test_redflag_fallback_writes_exact_template_terminal_fields() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    fallback = skill.split("**Fallback（子 skill 不可用时", 1)[1].split("### Step 6", 1)[0]
    for field in (
        "`**发现的风险小结:**`",
        "`**引用:**`",
        "`**估值阻断:**`",
        "`**结论:**`",
        "`**置信度:**`",
    ):
        assert field in fallback


def test_management_pending_stops_auto_loop_with_persisted_handoff() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    auto_route = skill.split("**Auto mode (default)**", 1)[1].split("**Interactive mode", 1)[0]
    assert "management_pending=true" in auto_route
    assert "持久化人工处理清单并退出auto循环" in auto_route


def test_valuation_output_template_is_selected_by_route() -> None:
    valuation = read(SKILLS_ROOT / "value-profile/references/valuation.md")
    output = valuation.split("## 8. 估值表达", 1)[1]
    assert "先按主估值路线五选一" in output
    assert "不得输出未选路线字段" in output
    for route in ("PE法", "银行PB法", "周期法", "公用事业DCF法", "高杠杆法"):
        assert route in output


def test_holding_template_uses_route_specific_exit_only() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    sell = template.rsplit("### §5.3", 1)[1].split("### §5.4", 1)[0]
    assert "是否出现更好标的" not in sell
    assert "PE/PB/周期/DCF" in sell
    assert "出现更好标的不构成卖出触发" in sell


def test_cycle_buy_discount_is_consistent_across_valuation_reference() -> None:
    valuation = read(SKILLS_ROOT / "value-profile/references/valuation.md")
    assert "买点 = 合理估值 × 35%  (高杠杆)" in valuation
    assert "买点 = 穿越周期合理估值 × 40%-50%  (周期股)" in valuation
    assert "买点 = 合理估值 × 35%  (高杠杆 / 周期" not in valuation


def test_management_parent_persists_as_of_and_passes_absolute_manifests() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "**信息截止日（AS_OF）**" in template
    assert "新建profile时立即把bootstrap AS_OF写入Part 0" in profile
    dispatch = profile.split("**§4管理层分析**", 1)[1].split("**管理层否决handoff**", 1)[0]
    assert "--filing-manifest <absolute-json-path>" in dispatch
    assert "--event-manifest <absolute-json-path>" in dispatch


def test_management_manifest_rebinds_every_official_candidate_and_pdf() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    assert "逐候选比较官方元数据" in mode_b
    assert "重新下载选中官方URL" in mode_b
    assert "官方文件SHA-256" in mode_b


def test_management_requires_complete_event_manifest_for_negative_rows() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    assert "--event-manifest <absolute-json-path>" in skill
    assert "监管事件manifest" in mode_b
    assert "结果总数" in mode_b
    assert "响应哈希" in mode_b
    assert "否" in mode_b


def test_management_interactive_edit_revalidates_all_required_gates() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    save = profile.split("#### 3d. Save by mode", 1)[1].split("#### 3e", 1)[0]
    assert "edit后的正文必须重新执行§4.pre、§4.2和§4.8完成条件" in save
    assert "通过后才保存为已完成" in save


def test_confirmed_appropriation_veto_does_not_require_size_threshold() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    prelude = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]
    assert "已证实即触发,不设金额或账龄下限" in prelude
    assert "达到§4.8量化触发条件" not in prelude


def test_management_formal_misstatement_sanctions_cover_full_history() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    prelude = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]
    assert "上市以来全部历史" in prelude
    assert "近5年因虚假陈述" not in prelude


def test_read_filing_historical_download_is_bounded_by_target_fiscal_year() -> None:
    skill = read(SKILL_PATHS["read-filing"])

    assert "--end-year YYYY" in skill
    assert "不得仅依赖`--as-of`推断目标财年" in skill


def test_read_filing_catalog_manifest_proves_order_and_completeness() -> None:
    skill = read(SKILL_PATHS["read-filing"])

    for required in (
        "官方结果总数",
        "完整公告时间戳",
        "公告顺序ID",
        "逐页拉取至已获取数量等于官方结果总数",
    ):
        assert required in skill


def test_read_filing_defines_cancellation_and_correction_transitions() -> None:
    skill = read(SKILL_PATHS["read-filing"])

    assert "撤销公告使此前版本失效" in skill
    assert "更正公告晚于当前完整年报" in skill
    assert "更正后的完整年报" in skill
    assert "未出现则abort" in skill


def test_read_filing_rejects_stale_extraction_cache_and_truncated_hk_catalog() -> None:
    skill = read(SKILL_PATHS["read-filing"])

    assert "metadata.json中的`source_sha256`" in skill
    assert "当前选中PDF的SHA-256" in skill
    assert "达到`rowRange`上限" in skill
    assert "目录可能被截断" in skill


def test_read_filing_hk_fiscal_year_uses_report_period_end_metadata() -> None:
    skill = read(SKILL_PATHS["read-filing"])

    assert "HKEX公告元数据中的报告期末日" in skill
    assert "封面或财务报表期末日" in skill
    assert "标题年份只能作为候选线索" in skill


def test_redflag_resume_recomputes_rows_before_accepting_completion() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    assert "逐行按证据和thresholds.yaml重算状态与严重度" in mode_b
    assert "重算结果与持久化值一致后才视为完成" in mode_b


def test_redflag_output_uses_exact_template_terminal_fields() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    output = skill.split("### Step 3", 1)[1].split("### Step 4", 1)[0]

    for field in (
        "**发现的风险小结:**",
        "**引用:**",
        "**结论:**",
        "**置信度:**",
        "**估值阻断:**",
    ):
        assert field in output
    assert "**发现的风险 summary:**" not in output


def test_redflag_mode_a_persists_blocking_and_manual_terminal_state() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_a = skill.split("2. **Mode A 准备**", 1)[1].split("3. **Mode B准备**", 1)[0]
    save = skill.split("### Step 5", 1)[1].split("### Step 6", 1)[0]

    assert "**估值阻断:**" in mode_a
    assert "**置信度:**" in mode_a
    assert "重试耗尽" in save
    assert "`**置信度:**需人工`" in save


def test_value_profile_redflag_fallback_exits_auto_as_manual_terminal() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    redflag = skill.split("### Step 5 — 排雷清单模式", 1)[1].split("### Step 6", 1)[0]
    external_gap = redflag.split("任何外部缺证", 1)[1].split("字段已存在", 1)[0]

    assert external_gap.index("`source-discovery`") < external_gap.index(
        "validated terminal claim ledger"
    )
    assert external_gap.index("validated terminal claim ledger") < external_gap.index(
        "`排雷终态=manual_review`"
    )


def test_redflag_veto_limits_sanctions_to_financial_misconduct() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mapping = skill.split("### §2.5", 1)[1].split("### §2.6", 1)[0]

    assert "正式财务造假或财务虚假陈述处罚记录" in mapping
    assert "与财务造假无关的其他处罚" in mapping
    assert "不得据此一票否决" in mapping


def test_management_rebinds_every_regulatory_event_to_official_metadata() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    assert "逐事件比较类别、标题、日期、状态、文书URL" in mode_b
    assert "不能只比较命中ID集合" in mode_b


def test_management_mode_a_owns_its_pending_and_accept_protocol() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    scaffold = skill.split("2. **Mode A 准备**", 1)[1].split("3. **Mode B准备**", 1)[0]
    save = skill.split("### Step 5", 1)[1].split("### Step 6", 1)[0]

    assert "**管理层否决:**" in scaffold
    assert "**人工处理清单:**" in scaffold
    assert "**运行状态:**" in scaffold
    assert "Mode A不存在父skill" in save
    assert "同一次原子写入中保存" in save


def test_management_guidance_gate_distinguishes_absence_from_missing_evidence() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    assert "官方明确未提供量化指引" in mode_b
    assert "未取得证据" in mode_b
    assert "写`需人工`" in mode_b
    assert "不得以高/中/低清除gate" in mode_b


def test_management_spacing_rule_only_forbids_han_to_han_whitespace() -> None:
    skill = read(SKILL_PATHS["management-analysis"])

    assert "只禁止两个中文字符之间" in skill
    assert "不禁止中文与英文或数字之间" in skill


def test_read_filing_mode_a_always_revalidates_extraction_source_hash() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    step1 = skill.split("### Step 1 — Bootstrap", 1)[1].split("### Step 1B", 1)[0]

    assert "即使text.md已存在也逐份调用" in step1
    assert "由extract_pdf.py校验source_sha256" in step1
    assert "源哈希不符时自动重抽取" in step1


def test_read_filing_hk_period_end_is_verified_and_persisted_after_extraction() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    step1 = skill.split("### Step 1 — Bootstrap", 1)[1].split("### Step 1B", 1)[0]

    assert "从封面和Consolidated Financial Statements抽取报告期末日" in step1
    assert "与标题候选财年及HKEX公告逐项比对" in step1
    assert "回写filing manifest的`报告期末日`" in step1
    assert "任一冲突或无法确定时abort" in step1


def test_redflag_child_receives_cutoff_and_canonical_manifests() -> None:
    parent = read(SKILL_PATHS["value-profile"])
    child = read(SKILL_PATHS["financial-redflag-scan"])
    dispatch = parent.split("### Step 5 — 排雷清单模式", 1)[1].split("**Fallback", 1)[0]

    for argument in (
        "--as-of AS_OF",
        "--filing-manifest <absolute-json-path>",
        "--event-manifest <absolute-json-path>",
    ):
        assert argument in dispatch
        assert argument in child
    assert "重新校验选中版本和截止日" in child


def test_generic_section_retry_exhaustion_is_manual_not_completed() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    review = skill.split("#### 3c. Main-agent review", 1)[1].split("#### 3d. Save by mode", 1)[0]
    save = skill.split("#### 3d. Save by mode", 1)[1].split("#### 3e", 1)[0]

    assert "`**置信度:**需人工`" in review
    assert "加入人工处理清单" in review
    assert "不得写中/低后继续" in review
    assert "不得派生为已完成" in save


def test_high_leverage_is_a_unique_fifth_valuation_route() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile/references/valuation.md")

    assert "高杠杆法不使用PE法双轨卖点" in skill
    assert "高杠杆法" in valuation.split("## 8.", 1)[1]
    assert "8-12PE" in valuation.split("## 8.", 1)[1]
    assert "PE>15" in valuation.split("## 8.", 1)[1]


def test_cycle_route_uses_cost_position_and_stricter_leverage_discount() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile/references/valuation.md")
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")

    assert "不适用单年PE" in skill
    assert "低成本15PE;中位成本10-12PE;高成本不估值" in valuation
    assert "高杠杆叠加时35%优先于40%-50%" in valuation
    assert "中位成本 → 穿越周期平均利润 × 10-12PE" in overlays


def test_manifest_bootstrap_order_and_fields_match_read_filing() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    manifests = skill.split("2.5. **构造并持久化source manifests**", 1)[1].split(
        "3. **PDF预抽取cache**", 1
    )[0]
    output = skill.split("3.5. **Derive output path**", 1)[1].split("4. **阅读层事实调用**", 1)[0]

    assert "先把AS_OF写入Part 0" not in manifests
    assert "官方结果总数" in manifests
    assert "公告顺序ID" in manifests
    assert "新建profile时立即把bootstrap AS_OF写入Part 0" in output
    assert "加载已有profile时保留原AS_OF" in output


def test_targeted_q_section_resolves_industry_before_schema_selection() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    part2 = skill.split("### Step 4 — Part 2 bulk mode", 1)[1].split("### Step 5", 1)[0]

    assert "显式定向§Q也必须先判定行业路由" in part2
    assert "不能依赖§1.1已经完成" in part2
    assert "只选择一个主overlay替换目标§Q schema" in part2
    assert "次级overlay只追加不冲突的披露和风险检查" in part2


def test_cycle_overlay_runs_adapted_moat_analysis_and_produces_label() -> None:
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")

    assert "资源周期仍执行适配后的5步护城河分析" in overlays
    assert "低成本曲线位置、储量寿命、牌照和运输半径" in overlays
    assert "不得写§3.1不适用" in overlays


def test_moat_reference_maps_steps_to_real_template_sections() -> None:
    moat = read(SKILLS_ROOT / "value-profile/references/moat-framework.md")
    structure = moat.split("## 6. 护城河分析报告结构", 1)[1]

    assert "§3.5 ROE/ROIC跨年验证" in structure
    assert "§3.6 杜邦拆解" in structure
    assert "§3.7 毛利率或行业替代成本指标" in structure
    assert "§3.8 悲观情景+综合标签" in structure
    assert "§3.5 2 项可证伪检验" not in structure


def test_unknown_resume_sections_are_preserved_but_excluded_from_progress() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    progress = skill.split("### Step 2 — Progress map", 1)[1].split("### Step 3", 1)[0]

    assert "未知section原样保留但标记为非canonical" in migration
    assert "不纳入next-undone或total_sections" in progress
    assert "已跳过仅在template明确允许时才是终态" in progress


def test_value_profile_spacing_rule_matches_han_to_han_requirement() -> None:
    skill = read(SKILL_PATHS["value-profile"])

    assert "只禁止两个中文字符之间" in skill
    assert "不禁止中文与英文或数字之间" in skill


def test_parent_event_manifest_carries_rebindable_official_metadata() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    manifests = skill.split("2.5. **构造并持久化source manifests**", 1)[1].split(
        "3. **PDF预抽取cache**", 1
    )[0]

    for field in ("类别", "标题", "日期", "状态", "文书URL", "内容哈希"):
        assert field in manifests


def test_management_shared_review_enforces_missing_evidence_distinction() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]

    assert "官方明确未提供量化指引" in review
    assert "未取得证据或抽取失败" in review
    assert "必须写`需人工`" in review


def test_redflag_mode_a_builds_and_persists_canonical_evidence() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_a = skill.split("2. **Mode A 准备**", 1)[1].split("3. **Mode B准备**", 1)[0]

    assert "**信息截止日（AS_OF）:**" in mode_a
    assert "**年报manifest:**" in mode_a
    assert "**监管事件manifest:**" in mode_a
    assert "执行与Mode B相同的source preflight" in skill


def test_value_profile_redflag_fallback_recomputes_every_row() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    fallback = skill.split("**Fallback（子 skill 不可用时", 1)[1].split("### Step 6", 1)[0]

    assert "逐行按证据、触发条件和thresholds.yaml重算状态与严重度" in fallback
    assert "不一致时覆盖并重新聚合" in fallback


def test_redflag_sanction_scope_is_consistent_in_skill_and_fraud_library() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    fraud = read(SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md")

    assert "非财务造假处罚不得直接升级" in skill
    assert "非财务造假处罚不得直接升级" in fraud
    assert "历史虚假陈述/违规处罚/股东利益输送" not in skill
    assert "历史虚假陈述/处罚/关联交易非正常价" not in fraud


def test_redflag_mode_b_example_matches_required_arguments_and_fields() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    contract = skill.split("## §7", 1)[1].split("## §A", 1)[0]

    for argument in ("--as-of AS_OF", "--filing-manifest", "--event-manifest"):
        assert argument in contract
    assert "**引用:**" in contract


def test_value_profile_global_failure_paths_use_manual_terminal_state() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    invocation = skill.split("#### 两种运行模式", 1)[1].split("**Interactive mode", 1)[0]
    recovery = skill.split("### §4.3 Failure modes & recovery", 1)[1]

    assert invocation.index("validated terminal `blocked/conflict/exhausted`") < invocation.index(
        "`**置信度:**需人工`"
    )
    for raw_failure in (
        "raw empty output",
        "empty route",
        "`technical-failure`",
        "`access-unavailable`",
        "`request-budget-exhausted`",
    ):
        assert raw_failure in skill
    assert "都不能直接产出`没有`、`查不到`或`需人工`" in skill
    assert "把相关claim写成validated terminal ledger" in recovery
    assert "validated `blocked` ledger" in recovery


def test_value_profile_primary_cycle_route_uses_cost_tier_multiple() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    routes = skill.split("**估值方法路由**", 1)[1].split("### §2.9", 1)[0]

    assert "完整周期平均净利润×成本档倍数" in routes
    assert "低成本15PE/中位成本10-12PE/高成本不估值" in routes
    assert "完整周期平均净利润×15PE" not in routes


def test_targeted_q_uses_one_primary_overlay_schema() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    part2 = skill.split("### Step 4 — Part 2 bulk mode", 1)[1].split("### Step 5", 1)[0]

    assert "只选择一个主overlay替换目标§Q schema" in part2
    assert "银行>高杠杆地产>资源/周期>公用事业>互联网>白酒>消费品（非白酒）>默认" in part2
    assert "次级overlay只追加不冲突的披露和风险检查" in part2


def test_holding_template_includes_high_leverage_exit_route() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    sell = template.rsplit("### §5.3", 1)[1].split("### §5.4", 1)[0]

    assert "PE/PB/周期/DCF/高杠杆" in sell
    assert "高杠杆法PE>15" in sell


def test_redflag_spacing_policy_matches_parent() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])

    assert "只禁止两个中文字符之间" in skill
    assert "不禁止中文与英文或数字之间" in skill


def test_read_filing_manifest_fields_distinguish_selected_files_and_notices() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]

    assert "所有候选必须有官方URL、报告类型、有效状态和替代关系" in mode_b
    assert "只有选中完整年报必须有绝对路径和SHA-256" in mode_b
    assert "撤销或更正通知的报告期末日写`不适用`" in mode_b
    assert "港股选中全文必须在去重结论生效前完成PDF期末日复核" in skill


def test_redflag_recomputation_updates_actions_with_state_and_severity() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    migration = profile.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    fallback = profile.split("**Fallback（子 skill 不可用时", 1)[1].split("### Step 6", 1)[0]

    for section in (migration, fallback):
        assert "同步重算实际动作" in section
        assert "不得保留与新状态矛盾的`无需动作`" in section


def test_redflag_template_veto_scope_matches_financial_misstatement_rule() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    row = next(line for line in template.splitlines() if "| 2 | 有财务造假历史" in line)

    assert "财务虚假陈述/财务造假正式处罚" in row
    assert "财务违规正式处罚" not in row


def test_redflag_reference_requires_tunneling_evidence_for_related_party_veto() -> None:
    library = read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "fraud-library.md")
    risk = next(line for line in library.splitlines() if line.startswith("5. **管理层道德风险**"))

    assert "已证实关联交易构成股东利益输送" in risk
    assert "已证实关联交易非正常价" not in risk


def test_redflag_child_resume_recomputes_actions() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    assert "同步重算实际动作" in mode_b
    assert "不得保留与新状态矛盾的`无需动作`" in mode_b


def test_redflag_reference_output_boundary_includes_fraud_dimensions() -> None:
    library = read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "fraud-library.md")
    boundary = library.split("**输入/输出边界**", 1)[1].split("**本 reference 不做**", 1)[0]

    assert "造假识别5个维度及维度综合结论" in boundary


def test_redflag_terminal_field_order_is_canonical_everywhere() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    contract = skill.split("## §7", 1)[1].split("## §A", 1)[0]
    fields = (
        "`**发现的风险小结:**`",
        "`**引用:**`",
        "`**估值阻断:**`",
        "`**结论:**`",
        "`**置信度:**`",
    )

    positions = [contract.index(field) for field in fields]
    assert positions == sorted(positions)


def test_redflag_mode_a_public_invocation_supports_as_of() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_a = skill.split("### Mode A", 1)[1].split("### Mode B", 1)[0]
    parsing = skill.split("### Invocation 解析", 1)[1].split("### 运行时必读", 1)[0]

    assert "[--as-of YYYY-MM-DD]" in mode_a
    assert "Mode A可显式传`--as-of YYYY-MM-DD`" in parsing


def test_management_manifest_drift_invalidates_completed_sections() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    preparation = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    assert "在判断任何section已完成之前" in preparation
    assert "manifest重建或live revalidation发现内容变化" in preparation
    assert "使旧`§4.pre`和`§4.1-§4.8`全部失效" in preparation
    assert "不得继续复用旧完成状态" in preparation


def test_event_manifests_cover_all_historical_management_sanctions() -> None:
    expected = "上市以来全部欺诈、操纵股价、内幕交易、虚假陈述和财务造假正式处罚或生效纪律处分"
    for skill_name in ("read-filing", "management-analysis", "value-profile"):
        assert expected in read(SKILL_PATHS[skill_name])


def test_value_profile_defers_valuation_until_redflag_gate_and_routes_schema() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")

    assert "part4/§4.3依赖part4/§4.5" in skill
    assert "§4.5证据完整且估值阻断为否之前不得运行§4.3" in skill
    assert "周期路线:整节替换为完整周期平均净利润" in template
    assert "公用事业路线:整节替换为稳态自由现金流" in template


def test_auto_mode_skips_user_specific_sections_without_blocking_company_valuation() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    part4 = template.split("## Part 4", 1)[1].split("## Part 5", 1)[0]
    part5 = template.split("## Part 5", 1)[1]

    for section_id in ("§4.6", "§4.7", "§4.8", "§4.9"):
        block = part4.split(f"### {section_id}", 1)[1].split("### ", 1)[0]
        assert "可选用户输入章节" in block
    for section_id in ("§5.1", "§5.4"):
        block = part5.split(f"### {section_id}", 1)[1].split("### ", 1)[0]
        assert "可选用户输入章节" in block
    assert "自动把置信度字段写为`已跳过`" in skill
    assert "不加入人工处理清单且不阻断公司估值" in skill


def test_resume_validates_every_section_before_accepting_terminal_confidence() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    progress = skill.split("### Step 2", 1)[1].split("### Step 3", 1)[0]

    assert "所有canonical section先执行通用完成条件" in progress
    assert "正文不含占位符" in progress
    assert "至少一条非占位引用" in progress
    assert "模板要求的表格、结论和管理层口径校核字段完整" in progress
    assert "仅有`高/中/低`不能判定完成" in progress


def test_bank_subskills_replace_generic_cashflow_and_debt_checks() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    management = read(SKILL_PATHS["management-analysis"])

    assert "银行排雷替代bundle" in redflag
    assert "银行不使用销售收现、CFO/NI、存货、毛利率或普通企业杠杆阈值" in redflag
    assert "银行资本分配替代bundle" in management
    assert "存款和同业负债不得套用普通企业有息负债测试" in management


def test_discipline_reference_matches_canonical_sell_and_position_rules() -> None:
    discipline = read(SKILLS_ROOT / "value-profile" / "references" / "discipline.md")

    assert "三大前提以SKILL §2.2.1为唯一口径" in discipline
    assert "发现更好标的不构成卖出触发" in discipline
    assert "单一持仓上限40%" in discipline
    assert "单一上限25%" not in discipline


def test_redflag_preflight_live_revalidates_event_manifest() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    assert "逐类重新请求监管事件manifest的官方查询URL和参数" in mode_b
    assert "响应哈希、结果总数和逐事件内容哈希" in mode_b
    assert "任一变化都abort并要求父skill重建" in mode_b


def test_redflag_mode_b_handoff_is_atomically_saved_by_parent() -> None:
    child = read(SKILL_PATHS["financial-redflag-scan"])
    parent = read(SKILL_PATHS["value-profile"])
    child_output = child.split("**Mode B**:", 1)[1].split("**确认节点**", 1)[0]
    parent_step = parent.split("### Step 5", 1)[1].split("### Step 6", 1)[0]

    assert "Mode B不直接写target-profile" in child_output
    assert "draft_section" in child_output
    assert "§4.5正文、排雷终态、排雷失败原因、Part 0财报排雷、估值阻断和人工处理清单" in parent_step
    assert "同一次原子写入" in parent_step


def test_targeted_management_section_is_not_widened() -> None:
    parent = read(SKILL_PATHS["value-profile"])
    child = read(SKILL_PATHS["management-analysis"])

    assert "--section <resolved-part1/§4.x>" in parent
    assert "显式定向§4.x时只生成并返回该section" in child
    assert "不得扩大为整个part1/§4" in child


def test_value_profile_stays_below_guide_word_limit() -> None:
    words = read(SKILL_PATHS["value-profile"]).split()
    assert len(words) < 5_000


def test_skill_markdown_has_no_whitespace_between_chinese_characters() -> None:
    pattern = re.compile(r"[\u3400-\u9fff][ \t]+[\u3400-\u9fff]")
    violations: list[str] = []
    for path in all_skill_markdown():
        for line_number, line in enumerate(read(path).splitlines(), 1):
            if pattern.search(line):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line_number}")
    assert not violations, "inappropriate Chinese whitespace:\n" + "\n".join(violations[:50])


def test_optional_sections_persist_only_valid_skip_state() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    progress = skill.split("### Step 2", 1)[1].split("### Step 3", 1)[0]

    assert "自动把置信度字段写为`已跳过`" in progress
    assert "待用户补充`只写入正文说明和控制台" in progress
    assert "标`已跳过—待用户补充`" not in progress


def test_fraud_risk_section_waits_for_redflag_evidence() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    progress = skill.split("### Step 2", 1)[1].split("### Step 3", 1)[0]

    assert "part1/§5.4依赖part4/§4.5" in progress
    assert "part1/§5.4不得先于part4/§4.5完成" in progress
    assert "显式定向`part1/§5.4`" in skill


def test_bank_redflag_bundle_is_mandatory_at_every_completion_gate() -> None:
    child = read(SKILL_PATHS["financial-redflag-scan"])
    parent = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    preparation = child.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]
    dispatch = child.split("### Step 3", 1)[1].split("### Step 4", 1)[0]
    review = child.split("### Step 4", 1)[1].split("### Step 5", 1)[0]
    parent_gate = parent.split("### Step 5", 1)[1].split("### Step 6", 1)[0]
    bank_table = template.split("#### 银行10行替代bundle", 1)[1].split("#### ", 1)[0]

    for block in (preparation, dispatch, review, parent_gate):
        assert "银行10行替代bundle" in block
        assert "任一缺失不得判定完成" in block
    for row in (
        "不良率与关注类迁徙",
        "逾期90天以上贷款",
        "拨备覆盖率与拨贷比",
        "信用成本",
        "净息差",
        "核心一级资本充足率",
        "风险加权资产增速",
        "流动性覆盖率与净稳定资金比例",
        "存款集中度与同业融资依赖",
        "关联授信与大额风险暴露",
    ):
        assert f"| {row} |" in bank_table


def test_management_dispatch_selects_bank_capital_allocation_bundle() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    dispatch = skill.split("每阶段派ONE", 1)[1].split("### Step 4", 1)[0]
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]

    assert "识别为银行时只派发§2.8银行资本分配替代bundle" in dispatch
    assert "非银行才派发通用ROE稳定性" in dispatch
    assert "银行输出通用ROE杠杆或债务政策测试" in review


def test_management_mode_b_never_writes_parent_profile() -> None:
    child = read(SKILL_PATHS["management-analysis"])
    parent = read(SKILL_PATHS["value-profile"])
    stages = child.split("### Step 3", 1)[1].split("### Step 4", 1)[0]
    output = child.split("**Mode B**:", 1)[1].split("**确认策略**", 1)[0]
    parent_handoff = parent.split("**管理层否决handoff**", 1)[0].rsplit("- **§4管理层分析**", 1)[1]

    assert "Mode B无论`--auto`还是`--interactive`都不写target-profile" in stages
    assert "仅返回`draft_sections`" in output
    assert "父skill是Mode B唯一写入者" in parent
    assert "同一次原子写入" in parent_handoff


def test_supported_exchange_scope_is_consistent() -> None:
    read_filing = read(SKILL_PATHS["read-filing"])
    cn_reference = read(SKILLS_ROOT / "read-filing" / "references" / "filing-structure-cn.md")

    assert "沪深A股" in read_filing
    assert "仅覆盖沪深交易所" in cn_reference
    assert "北交所" not in cn_reference


def test_redflag_revalidates_annual_report_catalog_live() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    preparation = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    assert "重新请求年报manifest的官方目录查询URL和参数" in preparation
    assert "响应哈希、结果总数和完整候选集合" in preparation
    assert "新增更正、撤销或替代版本" in preparation
    assert "任一变化都abort并要求父skill重建" in preparation


def test_redflag_mode_b_only_returns_draft() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]

    assert "仅返回`draft_section`和结构化flags" in mode_b
    assert "父skill是唯一写入者" in mode_b
    assert "用 Edit 工具" not in mode_b


def test_redflag_parent_syncs_visible_status_for_every_outcome() -> None:
    parent = read(SKILL_PATHS["value-profile"])
    save = parent.split("### Step 5", 1)[1].split("### Step 6", 1)[0]
    migration = parent.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    visible_values = "零触发项/N项中风险/N项高风险/证据需人工"

    assert visible_values in save
    assert visible_values in migration
    assert "§4.5正文、排雷终态、排雷失败原因、Part 0财报排雷、估值阻断和人工处理清单" in save
    assert "同一次原子写入" in save


def test_sales_collection_threshold_has_one_canonical_value() -> None:
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )

    canonical = thresholds["checks"]["sales_cash_collection"]["deep_review_below"]
    assert canonical == 1.0
    assert "收现比<1.0连续2年" in template
    assert "收现比<0.95" not in template


def test_cfo_conversion_uses_parent_net_income_everywhere() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    high_risk = redflag.split("### §2.2", 1)[1].split("### §2.3", 1)[0]
    checklist = template.split("### §4.5负面清单", 1)[1].split("### §4.6", 1)[0]

    assert "经营现金流/归母净利润<50%连续2年" in high_risk
    assert "经营现金流/归母净利润" in checklist
    assert "经营现金流/净利润" not in checklist


def test_management_historical_fetch_preserves_cutoff() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    audit = skill.split("4. **Audit", 1)[1].split("5. **构造canonical manifests**", 1)[0]

    assert "--end-year <latest-required-fiscal-year>" in audit
    assert "--as-of AS_OF" in audit


def test_management_manifest_identity_matches_profile() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    preparation = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    for field in ("ticker", "exchange", "AS_OF", "查询发行人代码"):
        assert field in preparation
    assert "逐项等于Part 0" in preparation
    assert "查询参数中的发行人" in preparation


def test_management_veto_events_cover_full_issuer_history() -> None:
    required = "上市以来全部已证实的大股东资金占用、违规关联交易和股东利益输送"
    for skill_name in ("read-filing", "management-analysis", "value-profile"):
        assert required in read(SKILL_PATHS[skill_name])


def test_management_pending_fields_are_saved_atomically_in_mode_a() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    output = skill.split("**Mode A**:", 1)[1].split("**Mode B**:", 1)[0]

    for field in ("management_pending", "pending_gate", "unresolved_rows"):
        assert f"`**{field}:**`" in output
    assert "同一次原子写入中保存" in output


def test_management_mode_b_top_level_contract_returns_drafts() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]

    assert "仅返回`draft_sections`和结构化flags" in mode_b
    assert "父skill是唯一写入者" in mode_b
    assert "用 Edit 工具" not in mode_b


def test_management_mode_b_parser_accepts_targeted_sections() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    parser = skill.split("1. **解析 invocation 参数**", 1)[1].split("2. **Mode A 准备**", 1)[0]

    assert "--section <part1/§4|part1/§4.pre|part1/§4.1-§4.8>" in parser
    assert "显式定向时保留该复合section ID" in parser


def test_blocked_valuation_section_has_legal_terminal_state() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    progress = skill.split("### Step 2", 1)[1].split("### Step 3", 1)[0]
    valuation_section = template.split("### §4.3 3年后净利润及估值", 1)[1].split("### §4.4", 1)[0]

    assert "估值阻断时条件跳过part4/§4.3" in progress
    assert "置信度字段写`已跳过`" in progress
    assert "条件跳过章节" in valuation_section


def test_both_manifests_persist_identity_fields() -> None:
    parent = read(SKILL_PATHS["value-profile"])
    manifests = parent.split("2.5. **构造并持久化source manifests**", 1)[1].split(
        "3. **PDF预抽取cache**", 1
    )[0]

    assert "两个manifest顶层都保存ticker、exchange、AS_OF和查询发行人代码" in manifests


def test_redflag_manifest_identity_matches_target_profile() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    preparation = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    for field in ("ticker", "exchange", "AS_OF", "查询发行人代码"):
        assert field in preparation
    assert "逐项等于target-profile的Part 0" in preparation
    assert "查询参数中的发行人" in preparation


def test_bank_redflag_severity_mapping_is_deterministic() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    mapping = thresholds["checks"]["bank_bundle_severity"]

    assert mapping["regulatory_breach"] == "high_risk"
    assert mapping["adverse_vs_prior_and_peer"] == "warning"
    assert mapping["missing_evidence"] == "pending"
    assert "银行10行按`bank_bundle_severity`映射" in skill


def test_high_leverage_cfo_denominator_is_defined() -> None:
    valuation = read(SKILLS_ROOT / "value-profile" / "references" / "valuation.md")

    assert "最近3年平均经营现金流" in valuation
    assert "平均经营现金流≤0且有息负债>0" in valuation
    assert "净资产≤0且有息负债>0" in valuation


def test_utility_high_leverage_buy_point_is_deterministic() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile" / "references" / "valuation.md")
    rule = "股息率>无风险利率×1.3且市值≤DCF合理估值×35%"

    assert rule in skill
    assert rule in valuation


def test_bank_capital_allocation_has_exactly_four_scored_tests() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    bank = skill.split("**银行资本分配替代bundle**", 1)[1].split("- `0项不通过`", 1)[0]

    rows = [line for line in bank.splitlines() if re.match(r"\d+\. \*\*", line)]
    assert len(rows) == 4
    for row in rows:
        for grade in ("通过", "中间", "不通过", "证据不足"):
            assert grade in row


def test_redflag_mode_b_auto_never_saves_child_output() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    confirmation = skill.split("**确认节点**", 1)[1].split("---", 1)[0]

    assert "Mode B的`--auto`复核通过后直接返回草稿" in confirmation
    assert "Mode A和Mode B的`--auto`复核通过后直接保存" not in confirmation


def test_management_fetch_precedes_manifest_construction_and_revalidation() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]

    audit = bootstrap.index("Audit`data/filings/<ticker>/`")
    construct = bootstrap.index("构造canonical manifests")
    assert audit < construct
    assert "下载成功后重新audit,再构造并复核两个manifest" in bootstrap


def test_management_standalone_section_48_uses_all_ten_canonical_channels() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    required = (
        "资金占用",
        "关联采购不公允定价",
        "关联销售不公允定价",
        "商标/品牌授权费",
        "销售/采购渠道被控制",
        "关联担保",
        "关联方长期预付款",
        "大股东主导合营项目沉淀",
        "集团代付/分担高管薪酬",
        "大小股东分红权差异",
    )

    for channel in required:
        assert channel in skill
    assert "Mode A和Mode B共用这10行canonical schema" in skill


def test_redflag_dispatch_enforces_evidence_cutoff_and_event_manifest() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    dispatch = skill.split("### Step 3", 1)[1].split("### Step 4", 1)[0]
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]

    assert "AS_OF证据截止日" in dispatch
    assert "event manifest绝对路径" in dispatch
    assert "不得使用AS_OF之后发布或发生的证据" in dispatch
    assert "引用AS_OF之后的证据" in review


def test_redflag_mode_a_download_precedes_final_manifest_preflight() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]

    audit = bootstrap.index("Audit`data/filings/<ticker>/`")
    evidence = bootstrap.index("建立canonical evidence")
    assert audit < evidence
    assert "下载成功后重新audit,再重建两个manifest并执行完整source preflight" in bootstrap


def test_management_pending_mode_b_is_persisted_before_interactive_menu() -> None:
    child = read(SKILL_PATHS["management-analysis"])
    parent = read(SKILL_PATHS["value-profile"])
    child_pending = child.split("任一阶段的必做gate为`需人工`", 1)[1].split(
        "pending gate解决后", 1
    )[0]
    parent_pending = parent.split("管理层子skill返回`management_pending=true`", 1)[1].split(
        "#### 3e", 1
    )[0]

    assert "父skill先原子持久化pending草稿" in child_pending
    assert "显示菜单前先在同一次原子写入中保存" in parent_pending
    assert "只显示`edit/research more/exit`" in parent_pending
    assert "只显示`edit/research more/defer`" not in parent_pending


def test_management_pending_mode_a_is_persisted_before_interactive_menu() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    pending = skill.split("任一阶段的必做gate为`需人工`", 1)[1].split("pending gate解决后", 1)[0]
    output = skill.split("**Mode A**:", 1)[1].split("**Mode B**:", 1)[0]

    assert "Mode A也在显示本地菜单前原子持久化pending状态" in pending
    assert "交互模式选择exit时保留pending终态" in output


def test_fraud_history_veto_uses_full_listing_history_everywhere() -> None:
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    row = next(line for line in template.splitlines() if "| 2 | 有财务造假历史 |" in line)

    assert "上市以来" in row
    assert "近10年" not in row


def test_utility_sell_trigger_never_falls_back_to_generic_pe_rule() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    discipline = read(SKILLS_ROOT / "value-profile" / "references" / "discipline.md")
    sell_rules = discipline.split("## 5. 卖出的三触发", 1)[1].split("## 6. 持仓权重管理", 1)[0]

    assert "PE法" in sell_rules
    assert "公用事业DCF法" in sell_rules
    assert "股息率<无风险利率" in sell_rules
    assert "每条路线只使用自己的卖点" in sell_rules
    assert "公用事业DCF法" in skill


def test_current_cycle_loss_does_not_block_positive_full_cycle_valuation() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile" / "references" / "valuation.md")
    applicability = valuation.split("## 4. 适用性边界", 1)[1].split("## 5.", 1)[0]
    gate = skill.split("**投资资格gate**", 1)[1].split("**估值方法路由**", 1)[0]

    assert "本节边界仅适用于PE法" in applicability
    assert "完整周期平均净利润为正" in applicability
    assert "当前亏损不阻断周期法" in applicability
    assert "PE适用性边界仅阻断PE法" in gate


def test_default_avoid_industry_continues_qualitative_profile() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    overlays = read(SKILLS_ROOT / "value-profile" / "references" / "industry-overlays.md")
    avoid = overlays.split("## 8. 行业不做清单", 1)[1].split("## 跨行业护城河", 1)[0]

    assert "继续完成定性研究" in avoid
    assert "不输出估值数字或买卖点" in avoid
    assert "不再继续 profile 流程" not in avoid
    assert "默认回避行业继续完成定性研究" in skill


def test_moat_contract_requires_capital_test_plus_one_other_test() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    moat = read(SKILLS_ROOT / "value-profile" / "references" / "moat-framework.md")

    canonical = "非银行必须完成资本消耗测试,并从提价、对手、切换成本、ROE路标中任选1项"
    assert canonical in skill
    assert canonical in template
    assert "§3.5资本消耗是必测项,§3.1-§3.4再任选1项" in moat
    assert "6 项硬指标 + 3 项可证伪检验" not in template
    assert "四选二" not in template


def test_dividends_enter_cash_ledger_without_forced_weight_reinvestment() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    discipline = read(SKILLS_ROOT / "value-profile" / "references" / "discipline.md")
    dividends = discipline.split("### 6.2分红再投资", 1)[1].split("### 6.3", 1)[0]

    assert "先进入现金台账" in dividends
    assert "仍低于买点的原持仓" in dividends
    assert "否则保留现金" in dividends
    assert "按当前权重加仓" not in dividends
    assert "先进入现金台账" in skill


def test_profile_writing_style_is_the_only_abbreviation_whitelist() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    style = read(SKILLS_ROOT / "value-profile" / "references" / "profile-writing-style.md")
    language = skill.split("### §4.1 Language policy", 1)[1].split("### §4.2", 1)[0]

    assert "ROA" in style
    assert "唯一缩写白名单" in language
    assert "保留缩写仅" not in language


def test_user_facing_chinese_uses_natural_evidence_status_language() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    product = read(SKILL_PATHS["product-analysis"])
    management = read(SKILL_PATHS["management-analysis"])
    style = read(SKILLS_ROOT / "value-profile" / "references" / "profile-writing-style.md")

    assert "用户可见中文不得使用“闭合”" in style
    for replacement in ("已核实", "证据完整", "已完成判断", "仍缺资料", "尚不能判断"):
        assert replacement in style
    assert "解决缺口" not in style
    for natural_phrase in ("补齐资料", "完成核验", "处理完这个问题"):
        assert natural_phrase in style
    assert "Step 3c必须检查并改写“闭合”" in profile
    for subskill in (redflag, product, management):
        assert "profile-writing-style.md" in subskill
        assert "不得把`close/closed`直译为“闭合”" in subskill

    user_facing_sources = (
        profile,
        redflag,
        product,
        management,
        read(SKILLS_ROOT / "value-profile" / "template-zh.md"),
        read(SKILLS_ROOT / "product-analysis" / "references" / "value-mechanisms.md"),
        read(SKILLS_ROOT / "management-analysis" / "references" / "related-party-alignment.md"),
    )
    allowed_rule_phrases = (
        "Step 3c必须检查并改写“闭合”",
        "不得把`close/closed`直译为“闭合”",
    )
    for source in user_facing_sources:
        offending_lines = [
            line
            for line in source.splitlines()
            if "闭合" in line and not any(rule in line for rule in allowed_rule_phrases)
        ]
        assert offending_lines == []


def test_user_facing_chinese_explains_sensitivity_analysis_naturally() -> None:
    style = read(SKILLS_ROOT / "value-profile" / "references" / "profile-writing-style.md")

    for requirement in (
        "按明确假设简单测算",
        "计算结果",
        "未考虑因素",
        "不是预测",
    ):
        assert requirement in style
    for stiff_phrase in ("机械压力", "机械影响", "机械敏感性", "机械减少"):
        assert stiff_phrase not in style


def test_value_profile_prose_is_written_for_human_readers() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    operations = read(SKILLS_ROOT / "value-profile" / "references" / "operations.md")
    style = read(SKILLS_ROOT / "value-profile" / "references" / "profile-writing-style.md")

    for requirement in (
        "不强制套用“结论、数据、风险”三段式",
        "像研究员自己会写的分析笔记",
        "先回答具体问题，再按需要给数据、表格和解释",
        "不为了显得正式而补齐过渡句、总结句或方法说明",
        "事实直接写；推断用“可能”“更可能”“还要看”",
        "数据 → 问题 → 原因 → 商业含义",
        "表前用自然的一两句话说明分类维度、报告期或要回答的问题",
        "允许使用“先看”“更值得注意的是”“接着看”",
        "不复述表格已经清楚呈现的层级、包含关系、合计或算术校验",
        "AI操作提醒、处理步骤和防错指令不得进入可见正文",
        "只有在口径差异会实质改变比较或结论时",
        "这句话是在帮助读者理解公司，还是只在提醒AI如何处理资料",
        "同一证据缺口只在最相关章节完整解释一次",
        "不能陷入无止境的数据瑕疵重复描述",
        "护城河来源写经济机制",
        "不写“测试通过”“证据窗口完整”“连续序列未完成”等研究流程状态",
    ):
        assert requirement in style

    canonical = "正文可以是一段自然完整的分析，不按固定句数或固定模板切割"
    assert canonical in profile
    assert canonical in operations

    metadata_rule = "引用、置信度和管理层口径校核属于证据层"
    assert metadata_rule in profile
    assert metadata_rule in operations
    assert metadata_rule in style
    assert "HTML阅读版统一隐藏" in style


def test_value_profile_states_missing_data_once_without_research_narration() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    operations = read(SKILLS_ROOT / "value-profile" / "references" / "operations.md")
    style = read(SKILLS_ROOT / "value-profile" / "references" / "profile-writing-style.md")

    for source in (profile, operations, style):
        assert "缺乏数据，无法分析" in source
        assert "不展开检索失败、来源报错或底层缺项清单" in source
        assert "不列举缺失字段、已查来源、旧年份样本或接口错误" in source
        assert "句后不得继续解释缺什么或为什么没找到" in source

    assert "数据不足时停止在简洁结论" in style
    assert "子问题缺少数据时" in style
    assert "客户画像缺乏数据，无法分析。" in style
    assert "内部恢复信息继续留在隐藏字段" in style


def test_value_profile_hides_machine_only_workflow_fields() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    workflow_block = template.split("**建议动作:**", 1)[1].split("**引用:**", 1)[0]

    assert "机器流程字段必须保留，但统一放入HTML注释" in profile
    assert "<!--" in workflow_block
    assert "-->" in workflow_block
    for field in ("动作执行台账", "排雷终态", "排雷失败原因"):
        assert field in workflow_block


def test_value_profile_research_is_question_driven_not_template_filling() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    operations = read(SKILLS_ROOT / "value-profile" / "references" / "operations.md")
    style = read(SKILLS_ROOT / "value-profile" / "references" / "profile-writing-style.md")

    for requirement in (
        "模板是查漏清单，不是文章提纲",
        "框架提供问题库和分析工具，不提供现成答案",
        "不能把同一套分析顺序和指标机械套到所有公司",
        "先形成2-5个公司特有的关键问题",
        "研究顺序由关键问题和新增证据决定",
        "完成正文后再用模板反查漏项",
        "事实、管理层解释、分析者判断和未知项",
        "类比先帮助理解，再说明两者在哪里不同",
        "新证据推翻旧判断时，明确更正",
        "风险按发生机制、发生可能性、影响程度和应对能力",
    ):
        assert requirement in style

    canonical = "先问题驱动研究，后模板查漏"
    assert canonical in profile
    assert canonical in operations


def test_value_profile_hides_part0_workflow_metadata_from_readers() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    part0_header = template.split("## Part 0", 1)[1].split("### 执行摘要", 1)[0]
    hidden = part0_header.split("<!-- 以下为机器工作流字段", 1)[1].split("-->", 1)[0]

    assert "**仍需补充:**" in part0_header
    for field in (
        "查询发行人代码",
        "manifest路径",
        "证据阶段",
        "运行状态",
        "失败原因",
        "人工处理清单",
    ):
        assert field in hidden
    assert "Part 0内部工作流字段统一放入HTML注释" in profile


def test_pop_mart_moat_discusses_economic_mechanisms_not_research_status() -> None:
    markdown = read(REPO_ROOT / "profiles" / "09992.HK-2026-07-29.md")
    html = read(REPO_ROOT / "profiles" / "09992.HK-2026-07-29.html")
    moat = markdown.split("## §3 护城河分析", 1)[1].split("## §4 管理质量与企业文化", 1)[0]

    for phrase in (
        "最新年度横截面测试通过",
        "连续五年测试",
        "2023年份额仍缺",
        "对手测试因无同口径份额序列而不能打分",
    ):
        assert phrase not in moat

    for mechanism in ("品牌和IP偏好", "多IP开发", "会员和直营渠道", "外包生产"):
        assert mechanism in moat

    market_share_gap_mentions = re.findall(r"2023年[^。；<]{0,30}(?:缺失|仍缺|未取得)", html)
    assert len(market_share_gap_mentions) <= 1


def test_product_revenue_mix_preserves_hierarchy_and_separates_dimensions() -> None:
    product_skill = read(SKILL_PATHS["product-analysis"])
    profile_skill = read(SKILL_PATHS["value-profile"])
    writing_style = read(SKILLS_ROOT / "value-profile" / "references" / "profile-writing-style.md")
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")

    for requirement in (
        "同一张收入结构表只放一个分类维度",
        "父项和子项必须明确标出包含关系",
        "固定使用`收入类别/收入/占总收入`三列",
        "报告期 · 金额单位",
        "首列缩进",
        "金额和占比分列",
        "不使用每层单独一列",
        "不使用`rowspan`",
        "交叉维度分表展示",
        "不得跨表相加",
    ):
        assert requirement in product_skill

    assert "层级收入表" in profile_skill
    assert "层级收入表" in writing_style
    assert "层级收入表" in template


def test_value_profile_publishes_markdown_and_html_companions() -> None:
    skill = read(SKILL_PATHS["value-profile"])

    for requirement in (
        "同名`.md`和`.html`",
        "HTML为默认阅读版本",
        "Markdown为可编辑源文件",
        "scripts/render_profile_html.py",
    ):
        assert requirement in skill


def test_value_profile_exec_summary_uses_compact_signal_blocks() -> None:
    skill = read(SKILL_PATHS["value-profile"])

    for requirement in (
        "状态标题 + 无前缀结论句 + 三色圆点证据",
        "不写`一句话判断：`",
        "`signal-list`",
        "绿色=正面、红色=负面、黄色=待验证",
    ):
        assert requirement in skill


def test_value_profile_preserves_confirmed_partial_market_share_trends() -> None:
    skill = read(SKILL_PATHS["value-profile"])

    for requirement in (
        "不得把“未形成完整五年序列”写成“无法判断任何趋势”",
        "市场定义、计量口径和历史重叠值",
        "可比年份已经确认的阶段变化",
        "未覆盖年份和不能外推的范围",
    ):
        assert requirement in skill


def test_product_and_value_profile_require_recent_market_share_research() -> None:
    product = read(SKILL_PATHS["product-analysis"])
    profile = read(SKILL_PATHS["value-profile"])

    for text in (product, profile):
        for requirement in (
            "市场份额默认请求最近5个完整年度",
            "公开证据允许时扩展至10年",
            "另查AS_OF可得的当年H1/YTD/最新季度",
            "目标公司与主要具名对手",
            "旧年份不能替代最近5年验收",
            "缺任一必需年度时连续序列保持unresolved",
        ):
            assert requirement in text


def test_value_profile_requires_historical_and_forward_industry_growth_data() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    rule = skill.split("§2.6.0市场份额证据窗口", 1)[1].split("§2.6.1", 1)[0]

    for required in (
        "最近5个完整年度",
        "未来3至5年",
        "逐年市场规模",
        "同比增速",
        "复合增速",
        "CR5或CR10",
        "预测版本",
        "后续修订",
    ):
        assert required in rule
    assert "行业预测可以作为情景数据保留" in rule


def test_product_discovery_contract() -> None:
    skill = read(SKILL_PATHS["product-analysis"])
    handoff = skill.split("### source-discovery handoff", 1)[1].split("### Mode A—Standalone", 1)[0]
    request_schema = json.loads(
        read(SKILLS_ROOT / "source-discovery" / "references" / "research-request.schema.json")
    )
    validator = Draft202012Validator(request_schema)

    match = re.search(
        r"Recommended request set:\n\n```json\n(.*?)\n```",
        handoff,
        flags=re.DOTALL,
    )
    assert match is not None
    documented_requests = json.loads(match.group(1))
    assert isinstance(documented_requests, list)
    assert len(documented_requests) == 4

    request_errors = sorted(
        (error for request in documented_requests for error in validator.iter_errors(request)),
        key=lambda error: (list(error.path), error.message),
    )
    assert request_errors == []

    for requirement in (
        "以下JSON中的字面值只作示意模板",
        "运行时必须从invocation和issuer context派生真实`as_of`",
        "最近完整期间",
        "`required_latest_period`",
        "`geographies`",
        "`industries`",
        "`subject`",
        "`population`",
        "`product_scope`",
        "`measurement_basis`",
    ):
        assert requirement in handoff

    claim_ids = {request["claim_id"] for request in documented_requests}
    assert claim_ids == {
        "product-category-size-cn-2021-2025",
        "product-market-share-cn-2021-2025",
        "product-customer-behavior-cn-2023-2025",
        "product-competitor-benchmark-cn-2025",
    }

    requests_by_id = {request["claim_id"]: request for request in documented_requests}

    category_size = requests_by_id["product-category-size-cn-2021-2025"]
    assert category_size["continuity_required"] is True
    assert category_size["required_latest_period"] == "2025"
    assert category_size["product_scope"] == "target product category only"
    assert "must include market denominator" in category_size["definition_constraints"]
    assert "published within 18 months of AS_OF" in category_size["definition_constraints"]

    market_share = requests_by_id["product-market-share-cn-2021-2025"]
    assert market_share["continuity_required"] is True
    assert market_share["measurement_basis"] == "share of category retail value"
    assert (
        "must name the subject company and major named competitors"
        in market_share["definition_constraints"]
    )
    assert (
        "must preserve annual rank and share for every required year"
        in market_share["definition_constraints"]
    )

    customer_behavior = requests_by_id["product-customer-behavior-cn-2023-2025"]
    assert customer_behavior["continuity_required"] is True
    assert customer_behavior["population"] == "current or recent paying customers"
    assert customer_behavior["metric"] == "annual repeat-purchase rate"
    assert customer_behavior["measurement_basis"] == "annual repeat-purchase rate"
    assert (
        "must use observed customer actions, not survey intent alone"
        in customer_behavior["definition_constraints"]
    )
    assert (
        "must retain repeat-purchase window and cohort definition"
        in customer_behavior["definition_constraints"]
    )
    assert (
        "latest accepted period must be no older than 24 months at AS_OF"
        in (customer_behavior["definition_constraints"])
    )
    assert "retention" not in customer_behavior["metric"]
    assert "retention" not in customer_behavior["measurement_basis"]

    competitor_benchmark = requests_by_id["product-competitor-benchmark-cn-2025"]
    assert competitor_benchmark["continuity_required"] is False
    assert competitor_benchmark["required_latest_period"] == "2025"
    assert competitor_benchmark["metric"] == (
        "price premium versus named same-task same-price-band competitors"
    )
    assert competitor_benchmark["measurement_basis"] == (
        "price premium versus named same-task same-price-band competitors"
    )
    assert competitor_benchmark["accepted_units"] == ["percentage"]
    assert (
        "must compare the same customer task, price band, and product scope"
        in (competitor_benchmark["definition_constraints"])
    )
    assert (
        "must preserve named competitor SKUs or offer identities"
        in (competitor_benchmark["definition_constraints"])
    )
    assert (
        "latest benchmark snapshot must be no older than 18 months at AS_OF"
        in (competitor_benchmark["definition_constraints"])
    )
    assert "benchmark spread" not in competitor_benchmark["metric"]
    assert "benchmark spread" not in competitor_benchmark["measurement_basis"]

    assert (
        "`product-analysis` remains responsible for product-system judgments, "
        "`moat_handoff`, and final Mode B schema compliance."
    ) in handoff
    for requirement in (
        "只可把`accepted_candidates`写入产品事实、流程事实、竞争事实和正文事实句",
        "`unresolved_claims`只接收`blocked`、`conflict`或`exhausted`",
        "不得把未接受candidate、空路由、`technical-failure`、`access-unavailable`或`request-budget-exhausted`改写成`没有`、`不存在`或事实性absence",
        "两次重派上限只约束同一路线的执行或输出质量重试",
        "未接受claim只能沿planner layer单调升级",
    ):
        assert requirement in handoff


def test_management_discovery_contract() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    handoff = skill.split("### source-discovery handoff", 1)[1].split("## §0运行模式", 1)[0]
    request_schema = json.loads(
        read(SKILLS_ROOT / "source-discovery" / "references" / "research-request.schema.json")
    )
    validator = Draft202012Validator(request_schema)

    match = re.search(
        r"Recommended request set:\n\n```json\n(.*?)\n```",
        handoff,
        flags=re.DOTALL,
    )
    assert match is not None
    documented_requests = json.loads(match.group(1))
    assert isinstance(documented_requests, list)
    assert len(documented_requests) == 4

    request_errors = sorted(
        (error for request in documented_requests for error in validator.iter_errors(request)),
        key=lambda error: (list(error.path), error.message),
    )
    assert request_errors == []

    assert "references/external-research-handoff.md" in skill
    for requirement in (
        "以下JSON中的字面值只作示意模板",
        "运行时必须从invocation、issuer context和bound manifest context派生真实`as_of`",
        "事件窗口",
        "`required_latest_period`",
        "`geographies`",
        "`industries`",
        "`subject`",
        "`population`",
        "`product_scope`",
        "`measurement_basis`",
        "只在已绑定的annual/event/counterpart manifests之外补外部证据",
        "官方 filing、event 和 counterpart manifest 证据继续由`read-filing`拥有",
        "`management-analysis`继续拥有最终管理判断、pending gate和一票否决schema",
        "official regulator/exchange/court governance event",
        "lead back to `read-filing` revalidation/rebinding",
        "cannot be directly accepted through external handoff",
        "Source-discovery may accept counterpart-side or non-manifest context only",
    ):
        assert requirement in handoff

    claim_ids = {request["claim_id"] for request in documented_requests}
    assert claim_ids == {
        "management-external-commitments-2023-2026",
        "management-governance-events-2023-2026",
        "management-counterpart-evidence-2023-2026",
        "management-regulatory-context-2023-2026",
    }

    requests_by_id = {request["claim_id"]: request for request in documented_requests}

    commitments = requests_by_id["management-external-commitments-2023-2026"]
    assert commitments["claim_type"] == "external-commitment"
    assert commitments["frequency"] == "event-driven"
    assert commitments["accepted_units"] == ["event"]
    assert commitments["accepted_source_classes"] == [
        "issuer-first-party",
        "named-counterparty",
        "auditor",
    ]
    assert (
        "must preserve commitment date, speaker identity, quoted commitment text, and target or milestone"
        in (commitments["definition_constraints"])
    )
    assert (
        "must preserve attributable outcome evidence or explicit unresolved outcome window"
        in (commitments["definition_constraints"])
    )
    assert (
        "must name the external document or event carrying the commitment"
        in (commitments["definition_constraints"])
    )

    governance = requests_by_id["management-governance-events-2023-2026"]
    assert governance["claim_type"] == "governance-event"
    assert governance["frequency"] == "event-driven"
    assert governance["accepted_units"] == ["event"]
    assert governance["accepted_source_classes"] == [
        "issuer-first-party",
        "named-counterparty",
        "auditor",
    ]
    assert (
        "must preserve occurrence date, publication date, governance body, action, and named subjects"
        in (governance["definition_constraints"])
    )
    assert (
        "must preserve `issuer_connection`, `subject_role_at_occurrence`, and current role if available"
        in (governance["definition_constraints"])
    )
    assert (
        "must stay outside already-bound official event manifests and cite the external governance route used"
        in (governance["definition_constraints"])
    )

    counterpart = requests_by_id["management-counterpart-evidence-2023-2026"]
    assert counterpart["claim_type"] == "counterpart-evidence"
    assert counterpart["accepted_units"] == ["event", "document"]
    assert counterpart["accepted_source_classes"] == [
        "named-counterparty",
        "auditor",
    ]
    assert (
        "must come from a named counterparty or counterpart-side attributable record"
        in (counterpart["definition_constraints"])
    )
    assert (
        "must preserve counterpart identity, relationship to issuer, event date, and exact claimed interaction"
        in (counterpart["definition_constraints"])
    )
    assert (
        "must link to the same commitment, governance event, or transaction under review"
        in (counterpart["definition_constraints"])
    )

    regulatory = requests_by_id["management-regulatory-context-2023-2026"]
    assert regulatory["claim_type"] == "regulatory-context"
    assert regulatory["accepted_units"] == ["document"]
    assert regulatory["accepted_source_classes"] == [
        "official-regulator",
        "official-exchange",
        "official-court",
    ]
    assert (
        "must be an official law, rule, code, listing rule, or regulator guidance in force during the event window"
        in (regulatory["definition_constraints"])
    )
    assert (
        "must preserve jurisdiction, effective date, cited provision, and applicability to the subject or event"
        in (regulatory["definition_constraints"])
    )
    assert (
        "must not replace bound official event evidence or create a violation conclusion without underlying accepted evidence"
        in (regulatory["definition_constraints"])
    )

    for requirement in (
        "只可把`accepted_candidates`写入管理层事实句、治理事件表、文化判断和诚信结论",
        "`unresolved_claims`只接收`blocked`、`conflict`或`exhausted`",
        "在返回`pending`或`需人工`前,相关外部claim必须先有通过`research-ledger.schema.json`校验的终态ledger",
        "`technical-failure`、`access-unavailable`和`request-budget-exhausted`只可落为`blocked`",
        "不得把这些失败改写成`未发生`、`没有`、`查无记录`或事实性absence",
        "媒体报道、匿名爆料、社交帖子、搜索摘要和无署名聚合页只可作为discovery lead",
        "不得用弱来源支持私下动机、个人品格、内部文化或诚信结论",
    ):
        assert requirement in handoff


def test_redflag_discovery_contract() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert skill.index("### source-discovery handoff") < skill.index("## §0运行模式")

    handoff = skill.split("### source-discovery handoff", 1)[1].split("## §0运行模式", 1)[0]
    review = skill.split("### Step 4 — 主 agent 复核", 1)[1].split(
        "### Step 5 — 写 summary + Output",
        1,
    )[0]

    assert "references/external-research-handoff.md" in skill
    for requirement in (
        "official event discovery/manifest construction/live revalidation/rebinding remain `read-filing` ownership",
        "Step 3.5和Step 5继续执行`read-filing`拥有的官方取证准备与重绑流程,这不是ownership transfer",
        "外部发现的官方处罚或执法记录只可作为lead back to `read-filing`",
        "不得在每条适用官方路线都已terminal且live revalidation成功前写`没有处罚`、`查无记录`或其他否定性执法结论",
        "`technical-failure`、`access-unavailable`和`request-budget-exhausted`只可产出通过`research-ledger.schema.json`校验的`blocked`",
        "不得把这些失败改写成absence,也不得直接快捷落成`需人工`或人工结论",
        "两次重派上限只约束单一路线的抽取或输出质量修复,不裁剪必须盘点的discovery route inventory",
        "目标公司经审计财务报表数值只可来自bound annual/counterpart manifests中被选中的经审计报表",
        "外部已接受证据只可补充thresholds、peer/industry/regulatory context或cross-checks,不能替代这些经审计数值",
        "Step 3.5/5现有编排继续使用`read-filing`拥有的evidence preparation",
    ):
        assert requirement in handoff

    for requirement in (
        "若把外部发现的官方处罚或执法记录当作最终accepted enforcement evidence而未回送`read-filing`重验重绑→退回",
        "若写出`没有处罚`、`查无记录`或其他否定性执法结论,但尚未证明每条适用官方路线都已terminal且live revalidation成功→退回",
        "若把`technical-failure`、`access-unavailable`或`request-budget-exhausted`从validated ledger `blocked`改写成absence或直接快捷落成`需人工`结论→退回",
        "若目标公司经审计财务报表数值来自外部research而非bound annual/counterpart manifests中的被选中经审计报表→退回",
    ):
        assert requirement in review


def test_value_profile_discovery_contract() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    run_store_contract = read(SKILLS_ROOT / "read-filing/references/run-store-contract.md")
    assert skill.index("### source-discovery run-level orchestration") < skill.index(
        "### Invocation"
    )

    orchestration = skill.split("### source-discovery run-level orchestration", 1)[1].split(
        "### Invocation",
        1,
    )[0]
    bootstrap = skill.split("1.55. **先创建standalone恢复骨架", 1)[1].split(
        "2. **Audit `data/filings/<ticker>/`**",
        1,
    )[0]
    fallback = skill.split("**Fallback（子 skill 不可用时, 主 skill 跑简化版）**", 1)[1].split(
        "### Step 6",
        1,
    )[0]
    worker_example = skill.split("Output requirements:", 1)[1]

    for requirement in (
        "可选checkpoint键`research_ledger`",
        "每个run最多一个binding",
        "对象结构固定为`artifact_id`、绝对`path`和小写64位十六进制`sha256`",
        "`value-profile`的binding路径固定解析到`<run>/logs/research-ledger.json`",
        "同一临界区",
        "先完成durable ledger write再写checkpoint binding",
        "先于任何dispatch或状态迁移",
        "resume时验证`path`位于同一run目录内",
        "重算sha256",
        "不一致即拒绝恢复",
        "wrapper仍是accepted candidate identities的唯一来源",
        "`planner_inventory_receipt`是planner返回的单一确定性inventory artifact",
        "strict normalized `planner_inputs` snapshot",
        "maintained profile identity/content hashes",
        "maintained relation source bindings",
        "分别独立重算fingerprint",
        "deterministic tamper-evident binding",
        "不声称防御同一process内",
        "不得再保存第二份caller声明的planner route list",
        "binding更新必须执行CAS",
        "`--expected-prior-sha256 create-only`",
        "--expected-prior-sha256 <current-checkpoint-sha256>",
        "未含该可选键的旧run继续有效",
        "直到`value-profile`首次创建外部research state",
    ):
        assert requirement in run_store_contract

    for requirement in (
        "exactly one run-local `data/filings/<ticker>/runs/<run-id>/logs/research-ledger.json`",
        "`checkpoint.json`是唯一source of truth",
        "只保存一个`research_ledger` artifact binding",
        "`artifact_id`",
        "绝对路径",
        "SHA-256",
        "claim-indexed wrapper",
        "单一`planner_inventory_receipt`",
        "`planner-inventory-receipt.schema.json`",
        "strict normalized `planner_inputs` snapshot",
        "contract validator与run-store分别独立重算fingerprint",
        "不防御同process恶意代码",
        "不使用secret或第二个state machine",
        "不得另存caller声明的planner route list",
        "`--expected-prior-sha256 create-only`",
        "更新显式传checkpoint当前`research_ledger.sha256`",
        "陈旧writer必须失败且不得覆盖",
        "该路径下的wrapper保存全部claim entries和accepted candidate identities",
        "每个嵌套`request`继续按`research-request.schema.json`校验",
        "每个claim ledger继续按`research-ledger.schema.json`校验",
        "不得改写或扩展单条ledger schema本身",
        "可见的`ledger_path`/`ledger_sha256`仅作可选引用",
        "不得作为resume依据",
        "`claim_id`",
        "`request_scope_fingerprint`",
        "`candidate_document_id`",
        "`artifact_identity`",
        "`artifact_sha256`",
        "`source_document_identity.binding_sha256`",
        "`lineage_id`",
        "consuming section IDs",
        "dispatch前先加载并校验既有ledger哈希",
        "accepted的正向claim立即停止且永不重新dispatch",
        "只把仍未解决的`claim_id`发送给`source-discovery`",
        "把持久化`attempts`传给`plan_next_layer`",
        "不得重新执行已terminal的`route_id`或已规范化查询",
        "同scope fingerprint下已`exhausted`的claim不得重复网络取证",
        "除非request本身变化或适用route inventory变化",
        "`accepted`直接消费已持久化candidate identity",
        "`blocked`和`conflict`必须保留结构化状态",
        "validated terminal ledger之后",
        "才可创建`需人工`",
        "exhausted positive claim可创建evidence-unavailable `需人工`",
        "exhausted absence claim只可写`截至AS_OF，适用公开路线未发现...`",
        "不得写绝对absence",
        "raw empty output",
        "empty route",
        "`technical-failure`",
        "`access-unavailable`",
        "`request-budget-exhausted`",
        "不能直接产出`没有`、`查不到`或`需人工`",
        "先落通过校验的终态`blocked` ledger",
        "action ledger与research ledger严格分离",
        "`deepen_research`只引用`claim_id`和`ledger_sha256`",
        "不得替代或覆盖research ledger",
        "不得回退到普通worker prompt兜底",
    ):
        assert requirement in orchestration

    for requirement in (
        "选中filing未披露时可写`待补充—年报未披露`",
        "外部核验缺口必须作为unresolved claim输入返回",
        "不得在validated terminal mapping前直接写`证据不足,需人工`",
    ):
        assert requirement in skill

    for requirement in (
        "受影响claim先持久化为validated terminal `blocked`",
        "event manifest保持未构建、未绑定",
        "不得把event manifest本身写成`需人工`",
        "保留不受影响且已完成的工作",
    ):
        assert requirement in bootstrap

    for requirement in (
        "内部输出质量失败继续走既有`output_quality_failure`路径",
        "任何外部缺证必须先走`source-discovery`",
        "validated terminal claim ledger",
        "`排雷终态=manual_review`",
        "`排雷失败原因=<具体证据缺口>`",
        "不得开普通worker side door",
    ):
        assert requirement in fallback
    assert fallback.index("validated terminal claim ledger") < fallback.index(
        "`排雷终态=manual_review`"
    )

    for legacy in (
        "Part 0或对应section状态同时持久化`ledger_path`与`ledger_sha256`",
        "找不到写`待补充—年报未披露`或`证据不足,需人工`",
        "每个关键缺口先建立轻量research ledger",
        "写`证据不足,需人工补充`,等用户下一步",
        "配额或限流重试耗尽→写`需人工`并作为终态退出",
        "事件manifest保持`需人工`",
        "客观证据缺失耗尽后把每个真实缺失项写为`需人工/待定`",
    ):
        assert legacy not in skill

    assert "无法核实 → `证据不足, 需人工补充`" not in worker_example


def test_high_cost_cyclical_has_no_investable_pb_liquidation_route() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile" / "references" / "valuation.md")

    assert "PB<1清算" not in skill
    assert "PB清算" not in skill
    assert "高成本不估值" in skill
    assert "高成本不估值" in valuation


def test_management_workers_and_review_enforce_as_of_cutoff() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    dispatch = skill.split("每阶段派ONE", 1)[1].split("### Step 4", 1)[0]
    review = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]

    assert "AS_OF证据截止日" in dispatch
    assert "event manifest绝对路径" in dispatch
    assert "AS_OF之后" in review


def test_management_guidance_gap_handles_zero_and_negative_targets() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    guidance = skill.split("§2.1.2偏差定义和阈值", 1)[1].split("### §2.2", 1)[0]

    assert "guidance>0" in guidance
    assert "guidance=0" in guidance
    assert "guidance<0" in guidance
    assert "不计算百分比gap" in guidance


def test_management_veto_matrix_is_consistent_for_sanctions_and_investigations() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    discipline = read(SKILLS_ROOT / "value-profile" / "references" / "discipline.md")
    required = "欺诈、操纵股价、内幕交易、虚假陈述和财务造假正式处罚或生效纪律处分"

    assert required in management
    assert required in template
    assert "刑事调查 | 需人工 | 阻断估值,等待正式结论" in discipline
    assert "刑事调查 | 观望 | 清仓" not in discipline


def test_management_capital_allocation_boundaries_cover_nine_roe_and_thirty_pe() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    allocation = skill.split("| 测试 |", 1)[1].split("**操作要点", 1)[0]

    assert "0%≤ROE<10%" in allocation
    assert "25PE≤回购价<40PE" in allocation


def test_management_related_party_rows_define_severity_mapping() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    veto = skill.split("§2.7.3阶段C后置触发条件", 1)[1].split("§2.7.4", 1)[0]

    for severity in ("无", "预警", "高风险", "一票否决", "待定"):
        assert severity in veto
    assert "状态到严重度的固定映射" in veto


def test_management_mode_b_has_exact_json_schema_and_invariants() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    output = skill.split("**Mode B**:", 1)[1].split("**确认策略**", 1)[0]

    for field in (
        '"draft_sections"',
        '"management_veto"',
        '"management_pending"',
        '"pending_gate"',
        '"reason"',
        '"citations"',
        '"unresolved_rows"',
    ):
        assert field in output
    assert "draft_sections的键必须是canonical复合section ID" in output


def test_management_visible_grades_are_chinese() -> None:
    skill = read(SKILL_PATHS["management-analysis"])

    assert "通过/中间/不通过/证据不足" in skill
    assert "`pass/中间/fail/证据不足`" not in skill


def test_goodwill_thresholds_define_both_comparators() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    goodwill = thresholds["checks"]["goodwill_to_net_assets"]

    assert goodwill["warning_comparator"] == "greater_than_or_equal"
    assert goodwill["high_risk_comparator"] == "greater_than"


def test_bank_threshold_registry_defines_direction_cohort_window_and_minima() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    bank = thresholds["checks"]["bank_bundle"]

    assert bank["comparison_window_years"] == 3
    assert bank["peer_cohort"] == "same_exchange_and_bank_subtype"
    assert "cet1_ratio" not in bank["regulatory_minima"]["CN"]
    assert "cet1_ratio" not in bank["regulatory_minima"]["HK"]
    assert bank["cet1_matrix"]["institution_specific_minimum_required"] is True
    assert (
        bank["regulatory_maxima"]["CN"]["large_exposure_ratio"]["non_interbank_single_customer"]
        == 0.15
    )
    assert (
        bank["regulatory_maxima"]["CN"]["large_exposure_ratio"]["non_interbank_connected_group"]
        == 0.20
    )
    assert (
        bank["regulatory_maxima"]["CN"]["large_exposure_ratio"][
            "interbank_single_or_connected_group"
        ]
        == 0.25
    )
    assert bank["regulatory_maxima"]["HK"]["large_exposure_ratio"] == 0.25
    assert bank["directions"]["npl_ratio"] == "lower_is_better"


def test_growth_multiple_checks_require_positive_comparable_growth() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    growth = skill.split("**清单第9项港股替代**", 1)[1].split("**§2.3.5", 1)[0]

    assert "营收增长率>0" in growth
    assert "营收增长率≤0时不计算增长倍数" in growth


def test_deposit_loan_trigger_action_uses_triggered_wording() -> None:
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    row = next(line for line in template.splitlines() if "| 3 | 存贷双高" in line)

    assert "达标则" in row
    assert "不达标则" not in row


def test_hk_governance_reference_routes_by_actual_issuer_structure() -> None:
    reference = read(SKILLS_ROOT / "read-filing" / "references" / "filing-structure-hk.md")

    assert "按发行人实际治理结构" in reference
    assert "港股是单层董事会" not in reference
    assert "不设监事会" not in reference


def test_read_filing_v1_rejects_interim_and_quarterly_modes() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    invocation = skill.split("### Invocation 解析", 1)[1].split("### 运行时必读", 1)[0]

    assert "v1仅支持完整年度报告" in invocation
    assert "拒绝`--quarterly`和`--halfyear`" in invocation
    assert "季报模式" not in skill
    assert "年报/季报" not in skill


def test_read_filing_mode_b_accepts_only_persisted_manifest_paths() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation 解析", 1)[0]

    assert "--filing-manifest <absolute-json-path>" in mode_b
    assert "--event-manifest <absolute-json-path>" in mode_b
    assert "<path-or-json>" not in skill


def test_targeted_valuation_runs_every_step_six_gate() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    targeted = skill.split("显式定向`part4/§4.3`", 1)[1].split("### Step 3", 1)[0]

    for gate in ("估值三大前提", "能力圈四问", "好生意", "护城河", "管理层门槛", "排雷门槛"):
        assert gate in targeted


def test_value_profile_general_worker_receives_as_of() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    dispatch = skill.split("#### 3b. Scoped research dispatch", 1)[1].split("#### 3c.", 1)[0]

    assert "AS_OF证据截止日" in dispatch
    assert "不得使用AS_OF之后" in dispatch


def test_no_valuation_route_conditionally_skips_all_price_sections() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    progress = skill.split("### Step 2", 1)[1].split("### Step 3", 1)[0]

    for section in (
        "part4/§4.1",
        "part4/§4.2",
        "part4/§4.3",
        "part5/§5.3",
        "part5/§5.5",
    ):
        assert section in progress
    assert "无估值路线条件跳过集合" in progress


def test_part2_by_section_uses_industry_schema_router() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    part2 = skill.split("### Step 4", 1)[1].split("### Step 5", 1)[0]

    assert "`by-section`也先执行同一行业路由" in part2


def test_moat_label_has_one_canonical_algorithm() -> None:
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    moat = read(SKILLS_ROOT / "value-profile" / "references" / "moat-framework.md")
    canonical = "最终标签只按moat-framework.md§2固定算法"

    assert canonical in template
    assert canonical in moat
    assert "5项满足 ≥ 4项" not in template


def test_non_liquor_consumer_is_a_primary_overlay() -> None:
    skill = read(SKILL_PATHS["value-profile"])

    assert "互联网>白酒>消费品（非白酒）>默认" in skill


def test_initial_position_sizing_has_one_canonical_rule() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile" / "references" / "valuation.md")
    discipline = read(SKILLS_ROOT / "value-profile" / "references" / "discipline.md")
    canonical = "首次建仓不超过组合5%"

    assert canonical in skill
    assert canonical in valuation
    assert canonical in discipline
    assert "目标仓位1/3" not in skill


def test_all_event_manifest_producers_use_the_executable_builder() -> None:
    command = "scripts/build_event_manifest.py --bundle"
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        assert command in read(SKILL_PATHS[skill_name])
    assert (REPO_ROOT / "scripts" / "build_event_manifest.py").is_file()


def test_read_filing_is_consistently_annual_only() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    frontmatter = skill.split("---", 2)[1]
    mode_a = skill.split("### Mode A", 1)[1].split("### Mode B", 1)[0]

    assert "annual,interim,or quarterly" not in frontmatter
    assert "年报/中报/季报" not in skill.split("## §0", 1)[0]
    assert "--quarterly Q1|Q2|Q3" not in mode_a
    assert "--halfyear`切到半年报" not in mode_a
    assert "v1仅支持完整年度报告" in skill


def test_all_financial_skills_canonicalize_hk_ticker_at_entry() -> None:
    canonical_rule = "港股代码立即左补零为五位"
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        assert canonical_rule in read(SKILL_PATHS[skill_name])


def test_read_filing_manifest_expansion_uses_temporary_output() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_a = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]

    assert "3年预检只写临时manifest" in mode_a
    assert "最终10年窗口只写一次canonical manifest" in mode_a
    assert "--manifest-out <temporary-json-path>" in mode_a
    assert "同一AS_OF内容漂移时发布内容寻址版本并原子改绑" in mode_a
    assert "改绑失败时才保留旧绑定并abort" in mode_a


def test_read_filing_mode_b_returns_facts_without_writing_profile() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation 解析", 1)[0]

    for field in ("facts", "citations", "warnings", "source_manifest_sha256"):
        assert f'"{field}"' in mode_b
    assert "不得直接替换或写入任何profile section" in mode_b


def test_read_filing_only_l1_to_l3_can_early_return() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    reference = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")

    assert "只有L1-L3允许早退" in skill
    assert "其他机械阈值只记录并继续完成12项附注和三表勾稽" in reference


def test_contract_liability_direction_is_consistent() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    reference = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")

    for text in (skill, reference):
        assert "高出2× 可能提前确认收入" not in text
        assert "高值检查履约积压和退款义务" in text
        assert "低值结合收款与履约证据检查提前确认" in text


def test_statement_reference_classifies_operating_liabilities_correctly() -> None:
    reference = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")

    assert "经营性负债" in reference
    assert "你欠别人或尚待履约" in reference
    assert "应付经营资产" not in reference
    assert "别人欠你的" not in reference


def test_read_filing_requires_all_twelve_notes() -> None:
    reference = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")
    assert "遗漏任一项视为不合格" in reference
    assert "遗漏 ≥ 3项" not in reference


def test_maintenance_capex_does_not_use_invalid_cfo_inference() -> None:
    principles = read(SKILLS_ROOT / "read-filing/references/reading-principles.md")
    quick = read(SKILLS_ROOT / "read-filing/references/quick-lookup.md")

    for text in (principles, quick):
        assert "长期 CFO > 全部 CapEx，则维持性 CapEx 必然 < 折旧摊销" not in text
        assert "长期 CFO > 全 CapEx → 维持性 < 折旧" not in text
        assert "不能仅凭CFO与总CapEx大小推断维持性CapEx低于折旧" in text


def test_management_mode_b_has_one_versioned_schema() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    output = skill.split("**Mode B**:", 1)[1].split("**确认策略**", 1)[0]

    for field in ('"schema_version"', '"stage"', '"draft_veto"'):
        assert field in output
    assert "键集合必须恰好等于当前stage中尚未完成的section" in output


def test_management_has_deterministic_final_decision_table() -> None:
    skill = read(SKILL_PATHS["management-analysis"])

    assert "管理层最终三态决策表" in skill
    assert "任一§2.7否决成立→弃权" in skill
    assert "存在pending或证据不足→有保留" in skill
    assert "无否决、无未决且资本分配合格→合格" in skill
    for threshold in ("10bp", "1.5pp", "5pp", "5年内≥2次"):
        assert threshold in skill


def test_management_uses_shared_related_party_schema() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    reference = SKILLS_ROOT / "management-analysis/references/related-party-alignment.md"

    assert reference.is_file()
    assert "references/related-party-alignment.md" in skill
    assert "../management-analysis/references/related-party-alignment.md" in template


def test_management_sanction_precedence_is_explicit() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    fraud = read(SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md")

    assert "management-analysis专属诚信否决规则优先" in skill
    assert "操纵市场或内幕交易" in fraud


def test_hk_short_listing_history_does_not_require_unsupported_prospectus_flag() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]

    assert "港股不传`--include-prospectus`" in bootstrap
    assert "缺上市文件不伪称已取得" in bootstrap


def test_value_profile_description_only_triggers_complete_dossiers() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    description = skill.split("---", 2)[1]

    assert "financial review" not in description
    assert "management review" not in description
    assert "red-flag scan" not in description
    assert "complete value-investing profile" in description


def test_value_profile_part_zero_persists_manifest_paths_and_hashes() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")

    for field in (
        "**年报manifest路径:**",
        "**年报manifest SHA-256:**",
        "**监管事件manifest路径:**",
        "**监管事件manifest SHA-256:**",
    ):
        assert field in template


def test_value_profile_has_qualitative_only_success_finalizer() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step6 = skill.split("### Step 6", 1)[1].split("## §4", 1)[0]

    assert "仅定性研究finalizer" in step6
    assert "正常成功终态" in step6
    assert "把尚未填写的价格与估值字段写为`N/A—<阻断原因>`" in step6
    assert "不得重写任何已完成section" in step6
    assert "不得要求用户手工标记" in step6


def test_value_profile_research_and_market_data_obey_as_of() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile/references/valuation.md")
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")

    assert "download_research.py <ticker> --years 3 --as-of AS_OF" in skill
    assert "价格、十年期国债收益率和估值倍数都取AS_OF当日或之前最近交易日" in valuation
    assert "当前价位" not in template
    assert "**市场数据日期:**" in template


def test_unprofitable_internet_route_does_not_recommend_unsupported_ps() -> None:
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")
    valuation = read(SKILLS_ROOT / "value-profile/references/valuation.md")

    assert "纯成长股（盈亏平衡前）→ 用 PS" not in overlays
    assert "盈亏平衡前→仅定性研究,不输出估值数字" in overlays
    assert "PS法" not in valuation


def test_moat_capital_consumption_failure_has_one_cap() -> None:
    moat = read(SKILLS_ROOT / "value-profile/references/moat-framework.md")

    assert "资本消耗测试失败时最终标签上限为`窄`" in moat
    assert "护城河综合标签降一级" not in moat


def test_redflag_actions_are_mode_specific_requests() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")

    assert "建议动作" in template
    assert "父级动作请求" in template
    assert "Mode A只记录建议动作" in skill
    assert "Mode B返回类型化`action_requests`" in skill


def test_redflag_patterns_cannot_independently_force_exclusion() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    fraud = read(SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md")

    for text in (skill, fraud):
        assert "可聚类到同一pattern" not in text or "不得单独升级为剔除" in text
    assert "pattern只能解释已触发风险,不得单独升级为剔除" in skill


def test_redflag_ambiguous_rows_have_deterministic_rules() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    thresholds = read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")

    for token in (
        "max(同业中位数−公司收益率,0)/abs(同业中位数)≥50%",
        "生产资产/总资产>40%",
        "低于同业中位数30%以上",
        "单账龄区间计提比例下降≥50%",
    ):
        assert token in template
    assert "qualitative_evidence_standard" in thresholds
    assert "peer_cohort: same_exchange_same_business_model" in thresholds


def test_bank_bundle_has_context_matrices_and_max_severity_aggregation() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    thresholds = read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")

    assert "一行包含多个指标时取最高严重度" in skill
    assert "credit_cost_matrix" in thresholds
    assert "rwa_growth_matrix" in thresholds
    assert "正常/预警/高风险/不适用/需人工" in template


def test_redflag_cfo_bridge_and_retained_earnings_are_accountingly_complete() -> None:
    fraud = read(SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md")

    assert "合并净利润" in fraud
    for item in ("Δ预付", "Δ其他经营应收", "Δ应付职工薪酬", "Δ应交税费"):
        assert item in fraud
    assert "期末留存收益=期初留存收益+本期归母净利润−分红±重述及权益转拨" in fraud
    assert "留存收益 = 净利润 − 分红" not in fraud


def test_redflag_auto_mode_never_waits_for_download_choice() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]

    assert "`--auto`自动执行下载" in bootstrap
    assert "下载失败则持久化`需人工`终态并退出" in bootstrap
    assert "只有`--interactive`显示`yes/no/show-command`" in bootstrap


def test_event_manifest_contract_is_described_consistently() -> None:
    required = (
        "官方域名白名单",
        "解析全部分页响应",
        "occurrence_date",
        "publication_time",
        "offense_type",
        "legal_effect",
        "subject_role_at_occurrence",
        "issuer_connection",
        "主体覆盖",
        "状态枚举",
        "HTTP方法、请求编码和响应schema",
        "构建器逐类在线重取全部事件分页",
        "本地路径单独放在`document_files`,不得混入官方响应",
        "重新下载每个官方文书URL并与本地文书逐字节哈希一致",
        "`live_revalidation_required`必须为`true`",
        "形成任何否定性结论前",
    )
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        for token in required:
            assert token in skill


def test_event_manifest_contract_live_revalidates_subject_roster() -> None:
    required = (
        "主体名册的官方URL和查询参数",
        "实时响应哈希、结果总数和完整主体列表",
    )
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        for token in required:
            assert token in skill


def test_event_manifest_producers_capture_content_addressed_publication_path() -> None:
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        assert "--out <canonical-event-manifest-path>" in skill
        assert "读取构建器stdout返回的真实发布路径" in skill


def test_management_mode_b_never_returns_an_effective_veto_before_parent_save() -> None:
    skill = read(SKILL_PATHS["management-analysis"])

    assert "向主skill返回`management_veto=true`" not in skill
    assert "Mode B只返回`draft_veto=true`和`management_veto=false`" in skill


def test_management_bank_rwa_decision_uses_shared_matrix_without_second_threshold() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    bank_bundle = skill.split("**银行资本分配替代bundle**", 1)[1].split(
        "**管理层最终三态决策表**", 1
    )[0]

    assert "`rwa_growth_matrix`为`none`→`通过`" in bank_bundle
    assert "`warning`→`中间`" in bank_bundle
    assert "`high_risk`→`不通过`" in bank_bundle
    assert "`pending`→`证据不足`" in bank_bundle
    assert "增速缺口≥5pp" not in bank_bundle


def test_management_bank_related_party_extension_is_required_and_resumable() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    reference = read(SKILLS_ROOT / "management-analysis/references/related-party-alignment.md")
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    required_rows = (
        "银行关联授信",
        "银行关联存款",
        "银行关联资产转让",
        "银行关联担保",
    )

    for row in required_rows:
        assert row in management
        assert row in reference
        assert row in template
    assert "银行必须额外完成4行" in management
    assert "银行4行扩展" in management


def test_management_non_gate_pending_has_atomic_resolution_path() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    parent = read(SKILL_PATHS["value-profile"])

    for token in (
        "任意management pending解决后",
        "非gate section",
        "management_pending=false",
        "重新计算阻断原因集合",
        "同一次原子写入",
    ):
        assert token in management
    assert "任意management pending解决后" in parent
    assert "非gate section" in parent


def test_read_filing_mode_b_returns_draft_without_child_write_confirmation() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    preflight = skill.split("### Step 1B", 1)[1].split("### Step 2", 1)[0]

    assert "Step 7确认后再写入" not in preflight
    assert "只在内存中生成草稿并返回" in preflight
    assert "父skill接受后" in preflight


def test_read_filing_early_exit_preserves_provenance_header() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    early_exit = skill.split("早退时只写以下短结构", 1)[1].split("未早退时使用完整骨架", 1)[0]

    for field in (
        "信息截止日（AS_OF）",
        "filing_manifest_sha256",
        "event_manifest_sha256",
        "官方查询溯源",
    ):
        assert field in early_exit


def test_qualitative_finalizer_never_rewrites_completed_valuation_sections() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    finalizer = skill.split("**仅定性研究finalizer**", 1)[1].split("**估值方法路由**", 1)[0]

    assert "尚未完成的估值相关section" in finalizer
    assert "已完成的§4.1和§4.2保留原文" in finalizer
    assert "不得重写任何已完成section" in finalizer


def test_parent_uses_pending_menu_for_gate_and_non_gate_management_sections() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    menu = skill.split("#### 3d.", 1)[1].split("#### 3e.", 1)[0]

    assert "management_pending=true" in menu
    assert "无论`pending_gate`为true或false" in menu
    assert "只显示`edit/research more/exit`" in menu


def test_management_veto_is_computed_before_one_atomic_parent_write() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    handoff = skill.split("**管理层否决handoff**", 1)[1].split("**管理层pending解除handoff**", 1)[0]

    assert "已接受的内存草稿" in handoff
    assert "预先计算完整事务" in handoff
    assert "一次CAS原子写入" in handoff
    assert "--expected-sha256 <baseline-profile-sha256>" in handoff
    assert "父skill原子保存成功后,才从已保存" not in handoff


def test_targeted_synthesis_sections_require_their_fact_dependencies() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    resolver = skill.split("**所有入口先运行统一section resolver**", 1)[1].split("### Step 3", 1)[0]

    assert "`part1/§1.8`依赖`part1/§1.1-§1.7`" in resolver
    assert "`part2/§Q12`依赖`part2/§Q1-§Q11`" in resolver
    assert "依赖未完成时只报告缺失依赖" in resolver


def test_value_profile_manifest_changes_have_explicit_invalidation_sets() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    manifests = skill.split("2.5. **构造并持久化source manifests**", 1)[1].split(
        "3. **PDF预抽取cache**", 1
    )[0]

    assert "年报manifest失效集合" in manifests
    assert "全部公司证据驱动的canonical section" in manifests
    assert "事件manifest失效集合" in manifests
    for section in ("part1/§4.pre-§4.8", "part4/§4.5", "part1/§5"):
        assert section in manifests
    assert "全部下游估值section" in manifests


def test_related_party_template_cannot_discount_proven_harm() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    section = template.split("### §4.8", 1)[1].split("## §5", 1)[0]

    assert "无伤大雅" not in section
    assert "护城河强度 > 抽血强度" not in section
    assert "正式处罚按canonical状态映射" in section
    assert "不得因金额较小或护城河较强降级" in section


def test_management_standalone_uses_current_part0_veto_fields() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    output = skill.split("### Step 5", 1)[1].split("## §4 Policy", 1)[0]

    assert 'Part 0 "管理层风险, 不可估值"' not in output
    assert "管理层否决:是—<原因>" in output
    assert "估值阻断:是—管理层否决" in output


def test_cyclical_peak_adjustment_is_identical_in_all_valuation_contracts() -> None:
    canonical = "波峰调整系数固定为0.75"
    for path in (
        SKILL_PATHS["value-profile"],
        SKILLS_ROOT / "value-profile/references/valuation.md",
        SKILLS_ROOT / "value-profile/references/industry-overlays.md",
    ):
        assert canonical in read(path)


def test_redflag_output_quality_failure_is_versioned_and_persistable() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    parent = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    schema = redflag.split("Mode B只返回以下版本化JSON schema", 1)[1].split("子 skill 若发现", 1)[0]
    standalone = redflag.split("2. **Mode A 准备**", 1)[1].split("3. **Mode B 准备**", 1)[0]

    assert '"terminal_status": "completed"' in schema
    assert '"failure_reason": null' in schema
    assert "completed/manual_review/output_quality_failure" in schema
    assert "**终态:** [未终结/completed/manual_review/output_quality_failure]" in standalone
    assert "**失败原因:** [无/<具体错误>]" in standalone
    assert "**排雷终态:** <completed/manual_review/output_quality_failure>" in template
    assert "**排雷失败原因:** <无/具体证据缺口/具体格式或一致性错误>" in template
    assert "output_quality_failure" in parent
    assert "已完成`→`completed/无`" in standalone
    assert "需人工`→`manual_review/<具体证据缺口>`" in standalone
    assert "output_quality_failure`→`output_quality_failure/<具体格式或一致性错误>`" in standalone
    assert "缺行也不得改为`进行中`或自动重派" in parent
    assert "排雷终态、排雷失败原因" in parent
    assert "不得重新进入自动重派" in parent


def test_bank_threshold_registry_defines_large_exposure_provision_and_rwa_buffer() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")
    )
    bank = thresholds["checks"]["bank_bundle"]

    assert bank["regulatory_maxima"]["CN"]["large_exposure_ratio"] == {
        "non_interbank_single_customer": 0.15,
        "non_interbank_connected_group": 0.20,
        "interbank_single_or_connected_group": 0.25,
    }
    assert bank["regulatory_maxima"]["HK"]["large_exposure_ratio"] == 0.25
    for market in ("CN", "HK"):
        assert "large_exposure_ratio" not in bank["regulatory_minima"][market]
    assert bank["regulatory_minima"]["CN"]["provision_coverage_ratio"] is None
    assert bank["regulatory_minima"]["HK"]["provision_coverage_ratio"] is None
    assert bank["regulatory_ranges"]["CN"]["provision_coverage_ratio"] == {
        "lower_bound": 1.2,
        "upper_bound": 1.5,
        "institution_specific": True,
    }
    assert (
        bank["provision_coverage_matrix"]["applicable_institution_minimum_required"]
        == "compare_actual_with_disclosed_or_supervisory_minimum"
    )
    assert (
        bank["metric_definitions"]["cet1_buffer_pp"]
        == "cet1_ratio_minus_applicable_regulatory_minimum"
    )
    assert (
        bank["provision_coverage_matrix"]["no_uniform_market_minimum"] == "compare_prior_and_peer"
    )
    assert bank["directions"]["large_exposure_ratio"] == "lower_is_better"
    assert "large_exposure_ratio" in bank["metric_definitions"]
    assert "large_exposure" not in bank["metric_definitions"]


def test_growth_multiple_checks_require_positive_growth_for_all_markets() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    checklist = template.split("### §4.5负面清单 — 排雷风险（29项）", 1)[1].split("### §4.6", 1)[0]
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")
    )

    assert "清单第9、10、18项" in skill
    assert "营收增长率>0" in skill
    for row_id in (9, 10, 18):
        row = next(line for line in checklist.splitlines() if line.startswith(f"| {row_id} |"))
        assert "营收增长率>0" in row
    applicability = thresholds["checks"]["growth_multiple"]["applicability"]
    assert applicability == "positive_revenue_and_compared_item_growth_only"


def test_sales_cash_reconciliation_uses_complete_receivable_rollforward() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    fraud = read(SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md")
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    parent = read(SKILL_PATHS["value-profile"])

    for text in (skill, fraud, template, parent):
        assert "本期核销" in text
        assert "汇兑" in text
        assert "合并处置" in text
        assert "重分类" in text
        assert "预收款项" in text


def test_redflag_thresholds_cover_ambiguous_quantitative_rows() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")
    )["checks"]
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")

    assert thresholds["cash_yield_peer_deviation"]["warning"] == 0.50
    assert thresholds["borrow_dividend_refinance"]["dividend_to_prior_net_income"] > 0
    assert thresholds["impairment_assumption"]["forecast_growth_warning"] == 0.10
    assert "收益率偏离同业中位数≥50%" in template


def test_cash_yield_peer_deviation_has_one_directional_formula() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")
    )["checks"]["cash_yield_peer_deviation"]
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    redflag = read(SKILL_PATHS["financial-redflag-scan"])

    assert thresholds["warning"] == 0.50
    assert thresholds["direction"] == "company_below_peer"
    assert thresholds["denominator"] == "absolute_peer_median"
    assert thresholds["peer_median_nonpositive"] == "manual_review"
    assert "max(同业中位数−公司收益率,0)/abs(同业中位数)≥50%" in template
    assert "同业中位数≤0时写`需人工/待定`" in template
    assert "max(同业中位数−公司收益率,0)/abs(同业中位数)" in redflag


def test_canonical_event_manifest_publication_preserves_immutable_versions() -> None:
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        assert "--out <canonical-event-manifest-path>" in skill
        assert "读取构建器stdout返回的真实发布路径" in skill
        assert "旧manifest保持不可变" in skill


def test_redflag_bootstrap_and_final_confirmation_menus_are_distinct() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    confirmation = skill.split("### §2.7确认策略", 1)[1].split("## §3", 1)[0]

    assert "bootstrap取证菜单" in confirmation
    assert "`no/show-command`" in confirmation
    assert "终稿确认菜单" in confirmation
    assert "Mode B不显示菜单" in confirmation


def test_redflag_actions_fit_mode_boundaries() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")

    assert "§0.1" not in template
    assert "估值 × 35%" not in template
    assert "valuation_route_review" in skill


def test_bank_reconciliations_are_explicitly_replaced() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    bank = skill.split("**银行排雷替代bundle", 1)[1].split("- **§2.3.1", 1)[0]

    assert "三表勾稽4条" in bank
    assert "全部写`不适用/无`" in bank
    assert "银行10行" in bank


def test_bank_thresholds_define_formulas_ranges_and_evidence() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")
    )["checks"]["bank_bundle"]

    assert thresholds["metric_definitions"]["interbank_funding_dependency"]
    assert thresholds["metric_definitions"]["deposit_concentration"]
    assert (
        thresholds["comparison_basis_required"]["deposit_concentration"]
        == "identical_numerator_scope_and_denominator"
    )
    assert "存款集中度的分子范围和分母必须与历史及同业完全同口径" in skill
    assert thresholds["metric_definitions"]["large_exposure_ratio"]
    assert thresholds["provision_coverage_matrix"]["above_500pct"] == "warning"
    assert thresholds["rwa_growth_matrix"]["cet1_growth_measure"] == "cet1_capital_amount_growth"
    old_peer_fields = {
        "ticker",
        "bank_subtype",
        "metric",
        "period",
        "publication_date",
        "source",
        "sha256",
    }
    assert old_peer_fields <= set(thresholds["peer_evidence_required_fields"])
    for field in ("value", "unit", "numerator", "denominator", "calculation_basis"):
        assert field in thresholds["peer_evidence_required_fields"]


def test_redflag_confidence_and_retry_terminal_states_are_deterministic() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])

    assert "证据置信度固定映射" in skill
    assert "完整官方窗口且无代理口径" in skill
    assert "output_quality_failure" in skill
    assert "不得把输出格式失败伪装成字段客观不可得" in skill


def test_redflag_mode_b_has_one_versioned_schema() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    contract = skill.split("## §7主 skill 调用契约", 1)[1]

    for field in (
        '"schema_version"',
        '"draft_section"',
        '"risk_counts"',
        '"valuation_blocked"',
        '"manual_review_required"',
        '"action_requests"',
        '"confidence"',
    ):
        assert field in contract
    assert "deepen_research" in contract
    assert "valuation_route_review" in contract


def test_management_event_attribution_and_governance_affect_final_state() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    decision = skill.split("**管理层最终三态决策表**", 1)[1].split("| 测试 |", 1)[0]

    assert "关键人变更" in decision
    assert "§4.8最高严重度" in decision
    assert "24个月" in skill
    assert "离任后个人无关行为" in skill
    assert "任职期间或与发行人有关" in skill


def test_management_bank_rules_share_rwa_matrix_and_related_credit_route() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    reference = read(SKILLS_ROOT / "management-analysis/references/related-party-alignment.md")

    assert "thresholds.yaml的`rwa_growth_matrix`" in skill
    assert "风险调整后资本成本" in skill
    assert "关联授信/存款/资产转让与担保" in reference


def test_management_targeted_mode_b_keys_equal_exact_target() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    output = skill.split("**Mode B**:", 1)[1].split("**确认策略**", 1)[0]

    assert "显式定向调用时键集合恰好等于该精确目标" in output
    assert "不要求补齐同stage其他section" in output


def test_management_mode_b_veto_is_always_draft_until_parent_saves() -> None:
    child = read(SKILL_PATHS["management-analysis"])
    parent = read(SKILL_PATHS["value-profile"])
    output = child.split("**Mode B**:", 1)[1].split("**确认策略**", 1)[0]

    assert "Mode B无论auto或interactive" in output
    assert "draft_veto=true" in output
    assert "management_veto=false" in output
    assert "已接受的内存草稿" in parent
    assert "一次CAS原子写入" in parent


def test_related_party_template_uses_canonical_schema_and_aggregation() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    section = template.split("### §4.8", 1)[1].split("### ", 1)[0]

    assert "| # | 渠道 | 状态 | 严重度 | 证据 | 引用 |" in section
    assert "填写（是/否" not in section
    assert "中高程度" not in section
    assert "触发数量只能帮助组织调查" in section


def test_value_profile_supports_historical_as_of_and_end_year() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    invocation = skill.split("### Invocation", 1)[1].split("#### 两种运行模式", 1)[0]

    assert "[--as-of YYYY-MM-DD]" in invocation
    assert "[--end-year YYYY]" in invocation
    assert "不得选择AS_OF后披露的年报" in skill


def test_ability_circle_questions_only_run_in_section_18() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    prompt = skill.split("### §4.7子 agent prompt 模板", 1)[1]

    assert "§1 subsection 必需" not in prompt
    assert "仅当目标为§1.8" in prompt


def test_failed_valuation_prerequisite_uses_qualitative_finalizer() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    progress = skill.split("### Step 2", 1)[1].split("### Step 3", 1)[0]
    step6 = skill.split("### Step 6", 1)[1].split("## §4", 1)[0]

    assert "三大前提任一假或存疑" in progress
    assert "调用仅定性研究finalizer" in step6
    assert "请补证据或将Part 0标" not in step6


def test_cyclical_valuation_uses_one_complete_cycle_algorithm() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    overlays = read(SKILLS_ROOT / "value-profile/references/industry-overlays.md")

    for text in (skill, overlays):
        assert "谷底到谷底或峰值到峰值" in text
        assert "至少覆盖一个峰值和一个谷底" in text
        assert "算术平均" in text
    assert "5-10年净利中位数" not in overlays


def test_redflag_mode_b_has_no_child_confirmation_menu() -> None:
    child = read(SKILL_PATHS["financial-redflag-scan"])
    parent = read(SKILL_PATHS["value-profile"])

    confirmation = child.split("### §2.7确认策略", 1)[1].split("## §3", 1)[0]
    parent_step = parent.split("### Step 5", 1)[1].split("### Step 6", 1)[0]
    assert "Mode B不显示菜单" in confirmation
    assert "父skill唯一确认" in parent_step


def test_read_filing_mode_a_persists_cutoff_and_source_provenance() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_a = skill.split("### Mode A", 1)[1].split("### Mode B", 1)[0]
    output = skill.split("**Mode A 输出骨架**", 1)[1].split("**Mode B输出**", 1)[0]

    assert "[--as-of YYYY-MM-DD]" in mode_a
    assert "**信息截止日（AS_OF）**" in output
    assert "filing_manifest_sha256" in output
    assert "event_manifest_sha256" in output
    assert "官方查询URL、查询参数和响应哈希" in output


def test_read_filing_mode_b_returns_both_manifest_hashes_without_writing() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    output = skill.split("**Mode B输出**:", 1)[1].split("**Mode B早退**", 1)[0]

    assert '"filing_manifest_sha256"' in output
    assert '"event_manifest_sha256"' in output
    assert "不得直接替换或写入任何profile section" in output


def test_amortized_cost_assets_describe_real_profit_or_loss_channels() -> None:
    reference = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")
    section = reference.split("### 2.2金融资产新准则", 1)[1].split("### 2.3", 1)[0]

    assert "利息收入" in section
    assert "预期信用损失" in section
    assert "汇兑损益" in section
    assert "不入当期损益" not in section


def test_owner_earnings_labels_consolidated_scope_and_comparison_mismatch() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    section = skill.split("### §2.9所有者利润优先", 1)[1].split("### §2.10", 1)[0]

    assert "合并口径所有者利润" in section
    assert "合并经营现金流" in section
    assert "合并口径资本开支" in section
    assert "与归母净利润比较存在口径差异" in section


def test_related_party_thresholds_route_by_exchange() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    rule = skill.split("§2.5.3关联交易附注", 1)[1].split("§2.5.4", 1)[0]

    assert "沪深A股" in rule
    assert "港股按HKEX Chapter 14A" in rule
    assert "港股不得套用A股3000万或净资产0.5%" in rule


def test_read_filing_mode_b_live_revalidates_subject_roster() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Step 1B", 1)[1].split("### Step 2", 1)[0]

    assert "重新请求主体名册的官方URL和查询参数" in mode_b
    assert "实时响应哈希、结果总数和完整主体列表" in mode_b


def test_read_filing_mode_b_never_mutates_extraction_cache() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Step 1B", 1)[1].split("### Step 2", 1)[0]

    assert "Mode B不得调用extract_pdf.py" in mode_b
    assert "不得删除、替换或创建持久化抽取cache" in mode_b
    assert "只读临时目录" in mode_b


def test_read_filing_routes_hk_governance_by_disclosed_structure() -> None:
    skill = read(SKILL_PATHS["read-filing"])

    assert "港股特别注意: **没有监事会报告**" not in skill
    assert "按发行人实际披露的治理结构" in skill
    assert "若年报披露监事会" in skill


def test_read_filing_confidence_mapping_is_deterministic() -> None:
    skill = read(SKILL_PATHS["read-filing"])

    assert "证据置信度固定映射" in skill
    assert "`高`=完整官方窗口且无代理口径" in skill
    assert "`中`=官方窗口完整但存在已披露且不影响结论方向的代理口径" in skill
    assert "`低`=关键结论仅有二级来源或窗口不足" in skill
    assert "`需人工`=存在待定或证据冲突" in skill
    assert "取所有关键结论中的最低档" in skill


def test_redflag_manual_terminal_reason_matches_template_schema() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")

    assert "**排雷失败原因:** <无/具体证据缺口/具体格式或一致性错误>" in template


def test_redflag_uses_only_canonical_part_zero_gate_names() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    fraud = read(SKILLS_ROOT / "financial-redflag-scan/references/fraud-library.md")

    for text in (skill, fraud):
        assert 'Part 0标"不可估值"' not in text
        assert 'Part 0 "不可估值"' not in text
    assert "**估值阻断:**是—" in skill


def test_related_party_channel_names_match_the_canonical_reference() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    canonical = (
        "资金占用",
        "关联采购不公允定价",
        "关联销售不公允定价",
        "商标/品牌授权费",
        "销售/采购渠道被控制",
        "关联担保",
        "关联方长期预付款",
        "大股东主导合营项目沉淀",
        "集团代付/分担高管薪酬",
        "大小股东分红权差异",
    )

    for channel in canonical:
        assert channel in management
        assert f"| {channel} |" in template


def test_management_confirmed_veto_dominates_pending_rows() -> None:
    skill = read(SKILL_PATHS["management-analysis"])

    assert "已证实否决与未决行并存时" in skill
    assert "draft_veto=true" in skill
    assert "management_pending=true" in skill
    assert "未决行不得覆盖已证实否决" in skill


def test_management_mode_b_recomputes_veto_before_atomic_save() -> None:
    child = read(SKILL_PATHS["management-analysis"])
    parent = read(SKILL_PATHS["value-profile"])

    assert "父skill原子保存成功后才从已保存正文重算" not in child
    assert "父skill原子保存成功后才由父skill重算" not in child
    assert "父skill原子保存成功后才重算持久化值" not in child
    assert "父skill原子保存成功后才重算并持久化否决" not in child
    assert "父skill先在内存中重算" in child
    assert "同一次原子写入" in child
    assert "不存在“先保存正文再补Part 0”的中间状态" in parent


def test_management_pending_save_preserves_confirmed_veto() -> None:
    parent = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    pending = parent.split("管理层子skill返回`management_pending=true`时", 1)[1].split(
        "#### 3e", 1
    )[0]
    pre_gate = template.split("### §4.pre", 1)[1].split("### §4.1", 1)[0]

    assert "已证实否决" in pending
    assert "`管理层否决`" in pending
    assert "同一次原子写入" in pending
    assert "未决行不得覆盖已证实否决" in pre_gate


def test_value_profile_computes_and_validates_manifest_hash_fields() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]

    assert "分别计算两个manifest文件的SHA-256" in bootstrap
    assert "写入Part 0对应SHA-256字段" in bootstrap
    assert "`<sha256>`仍存在时abort" in bootstrap


def test_value_profile_fallback_persists_manual_terminal_mapping() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    fallback = skill.split("**Fallback（子 skill 不可用时", 1)[1].split("### Step 6", 1)[0]
    external_gap = fallback.split("任何外部缺证", 1)[1].split("字段已存在", 1)[0]

    assert "validated terminal claim ledger" in external_gap
    assert "`排雷终态=manual_review`" in external_gap
    assert "`排雷失败原因=<具体证据缺口>`" in external_gap
    assert external_gap.index("validated terminal claim ledger") < external_gap.index(
        "`排雷终态=manual_review`"
    )


def test_redflag_mode_b_has_one_confirmation_owner_and_one_failure_field() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    invocation = skill.split("### Invocation 解析", 1)[1].split("### 运行时必读", 1)[0]
    mode_b_output = skill.split("**Mode B**:", 1)[1].split("**确认节点**", 1)[0]

    assert "Mode A的`--interactive`才显示确认菜单" in invocation
    assert "Mode B的`--interactive`才显示确认菜单" not in invocation
    assert "failure_reason" in mode_b_output
    assert "manual_review_required/reason" not in mode_b_output


def test_redflag_in_progress_state_is_not_a_terminal_state() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    skeleton = skill.split("2. **Mode A 准备**", 1)[1].split("3. **Mode B 准备**", 1)[0]
    output = skill.split("**Mode A**:", 1)[1].split("**Mode B**:", 1)[0]

    assert "**终态:** [未终结/completed/manual_review/output_quality_failure]" in skeleton
    assert "运行状态=进行中时终态固定写未终结" in output
    assert "未终结不是完成终态" in output


def test_management_standalone_binds_manifest_hashes() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_a = skill.split("2. **Mode A 准备**", 1)[1].split("3. **Mode B准备**", 1)[0]
    output = skill.split("**Mode A**:", 1)[1].split("**Mode B**:", 1)[0]

    assert "**年报manifest SHA-256:** <sha256>" in mode_a
    assert "**监管事件manifest SHA-256:** <sha256>" in mode_a
    assert "路径与已持久化SHA-256" in output


def test_management_replay_uses_full_persisted_event_request_contract() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    for token in (
        "http_method",
        "request_encoding",
        "request_headers",
        "query_params",
        "response_schema",
        "response_adapter",
    ):
        assert token in mode_b
    assert "不得假定GET、query编码或固定分页字段" in mode_b


def test_child_results_bind_both_manifest_hashes_before_parent_save() -> None:
    parent = read(SKILL_PATHS["value-profile"])
    for skill_name in ("management-analysis", "financial-redflag-scan"):
        child = read(SKILL_PATHS[skill_name])
        assert '"filing_manifest_sha256"' in child
        assert '"event_manifest_sha256"' in child
    assert "保存草稿前重新计算两个manifest文件SHA-256" in parent
    assert "与子skill返回哈希及Part 0字段三方一致" in parent
    assert "比较与原子替换之间任一manifest变化时abort" in parent


def test_value_profile_final_save_revalidates_both_manifest_hashes() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    step6 = skill.split("### Step 6", 1)[1].split("## §4", 1)[0]

    assert "最终原子保存前重新计算两个manifest文件SHA-256" in step6
    assert "Auto mode和Interactive mode" in step6
    assert "与Part 0字段逐项一致" in step6
    assert "不一致时abort" in step6


def test_value_profile_rebased_year_tables_keep_rectangular_markdown() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    lines = template.splitlines()

    for index, line in enumerate(lines):
        if "<end_year-9>" not in line:
            continue
        expected_pipes = line.count("|")
        row_index = index + 1
        while row_index < len(lines) and lines[row_index].startswith("|"):
            assert lines[row_index].count("|") == expected_pipes
            row_index += 1


def test_rebased_percentage_income_statement_keeps_revenue_at_100_percent() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    row = next(line for line in template.splitlines() if line.startswith("| 营业收入 | 100% |"))

    assert row.split("|")[2:-1] == [" 100% "] * 11


def test_redflag_replays_full_persisted_event_request_contract() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("3. **Mode B准备**", 1)[1].split("### Step 3", 1)[0]

    for token in (
        "http_method",
        "request_encoding",
        "request_headers",
        "query_params",
        "response_schema",
        "response_adapter",
    ):
        assert token in mode_b
    assert "不得假定GET、query编码或固定分页字段" in mode_b


def test_bank_cet1_uses_institution_specific_regulatory_minimum() -> None:
    registry = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    bank = registry["checks"]["bank_bundle"]
    matrix = bank["cet1_matrix"]

    assert matrix["applicable_institution_minimum_required"] == (
        "compare_actual_with_disclosed_or_supervisory_minimum"
    )
    assert matrix["minimum_unavailable"] == "pending_no_regulatory_breach"
    assert matrix["generic_market_baseline_role"] == "fallback_comparison_only"
    for path in (
        SKILL_PATHS["financial-redflag-scan"],
        SKILL_PATHS["management-analysis"],
    ):
        text = read(path)
        assert "机构适用核心一级资本监管最低要求" in text
        assert "不可得时写待定且不得判定监管违规" in text
        assert "通用市场基线只作后备比较" in text


def test_cash_change_row_delegates_yield_deviation_to_canonical_formula() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    row = next(
        line
        for line in template.splitlines()
        if line.startswith("| 5 | 货币资金大幅变动/收益率异常 |")
    )

    assert "收益率分支复用第4项公式" in row
    assert "同币种、同期限、同交易所同业中位数" in row
    assert "偏离≥50%" in row


def test_read_filing_early_exit_publishes_resolvable_manifest_evidence() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    bootstrap = skill.split("### Step 1 —", 1)[1].split("### Step 1B", 1)[0]
    output = skill.split("早退时只写以下短结构", 1)[1].split("完整阅读报告写以下结构", 1)[0]

    assert "触发早退时排他原子发布3年canonical年报manifest" in bootstrap
    assert "临时manifest不得删除直至canonical发布并回读成功" in bootstrap
    assert "filing_manifest_path" in output
    assert "event_manifest_path" in output


def test_read_filing_mode_b_distinguishes_pdf_from_extracted_text_argument() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_b = skill.split("### Mode B", 1)[1].split("### Invocation", 1)[0]
    preflight = skill.split("### Step 1B", 1)[1].split("### Step 2", 1)[0]

    assert "--filing <absolute-pdf-path>|--extracted-text <absolute-text-path>" in mode_b
    assert "二者恰好提供一个" in mode_b
    assert "传入`--filing`时" in preflight
    assert "传入`--extracted-text`时" in preflight


def test_event_manifest_contract_requires_all_applicable_official_sources() -> None:
    for path in (
        SKILL_PATHS["read-filing"],
        SKILL_PATHS["financial-redflag-scan"],
        SKILL_PATHS["management-analysis"],
        SKILL_PATHS["value-profile"],
    ):
        text = read(path)
        assert "每类事件覆盖全部适用官方来源" in text
        assert "source_count" in text
        assert "sources" in text


def test_all_orchestrators_use_the_event_evidence_collector() -> None:
    for path in (
        SKILL_PATHS["read-filing"],
        SKILL_PATHS["financial-redflag-scan"],
        SKILL_PATHS["management-analysis"],
        SKILL_PATHS["value-profile"],
    ):
        text = read(path)
        assert "scripts/collect_event_evidence.py" in text
        assert "event-query-plan.schema.json" in text
        assert "先采集后构建" in text


def test_manifest_drift_uses_versioned_evidence_and_atomic_rebinding() -> None:
    for path in (
        SKILL_PATHS["read-filing"],
        SKILL_PATHS["financial-redflag-scan"],
        SKILL_PATHS["management-analysis"],
        SKILL_PATHS["value-profile"],
    ):
        text = read(path)
        assert "内容寻址版本" in text
        assert "原子改绑" in text
        assert "旧manifest保持不可变" in text


def test_value_profile_validates_extraction_cache_before_every_read() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "metadata.json中的`source_sha256`" in skill
    assert "`artifact_sha256`" in skill
    assert "page marker" in skill
    assert "与年报manifest的PDF SHA-256一致" in skill
    assert "任一不符都必须重抽取" in skill


def test_read_filing_mode_b_has_live_caller_and_terminal_result_schema() -> None:
    read_skill = read(SKILL_PATHS["read-filing"])
    value_skill = read(SKILL_PATHS["value-profile"])

    assert '"terminal_status": "success"' in read_skill
    assert '"terminal_status": "failure"' in read_skill
    assert '"failure_reason":' in read_skill
    assert "调用`read-filing` Mode B" in value_skill
    assert "terminal_status=success" in value_skill
    assert "failure时不得保存事实草稿" in value_skill


def test_redflag_evidence_binding_is_an_atomic_state_transition() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "source preflight成功后" in skill
    assert "证据阶段从`未建立`原子转换为`已绑定`" in skill
    assert "两个manifest路径和SHA-256" in skill
    assert "证据阶段不是`已绑定`时不得进入完成终态" in skill


def test_value_profile_consumes_every_redflag_action_request() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    for action in (
        "valuation_route_review",
        "management_review",
        "lower_confidence",
        "deepen_research",
    ):
        assert action in skill
    assert "未知action_request" in skill
    assert "未执行的action_request阻止§4.5完成" in skill
    assert "动作执行结果与§4.5正文同一次原子写入" in skill


def test_ambiguous_redflag_rows_use_canonical_threshold_rules() -> None:
    registry = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")
    )
    checks = registry["checks"]
    for key in (
        "borrow_dividend_refinance",
        "gross_margin_deterioration",
        "goodwill_impairment_assumption",
        "overdue_receivables_persistence",
    ):
        assert key in checks
        assert "window_years" in checks[key]
        assert "comparison" in checks[key]
        assert "minimum_periods" in checks[key]
        assert "not_applicable_when" in checks[key]
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    for key in (
        "borrow_dividend_refinance",
        "gross_margin_deterioration",
        "goodwill_impairment_assumption",
        "overdue_receivables_persistence",
    ):
        assert f"thresholds.yaml:checks.{key}" in template


def test_redflag_mode_b_never_owns_interactive_confirmation() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_b = skill.split("### Mode B", 1)[1]
    assert "Mode B始终只返回草稿" in mode_b
    assert "父skill独占`accept/edit/research more`" in mode_b
    assert "Mode B的`--interactive`接受后" not in mode_b


def test_management_promise_veto_requires_one_comparable_metric_series() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    for text in (skill, template):
        assert "同一指标ID" in text
        assert "连续3个可比财年" in text
        assert "单位和口径一致" in text
        assert "不同指标不得拼接为连续三年" in text


def test_management_precheck_rows_are_mutually_exclusive() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    for text in (skill, template):
        assert "四行互斥归类" in text
        assert "虚假陈述只计入`虚假陈述处罚记录`" in text
        assert "同一事件只计数一次" in text


def test_read_filing_citations_bind_exact_page_evidence() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    for token in (
        "source_pdf_sha256",
        "artifact_sha256",
        "page",
        "quote",
        "原文片段必须存在于对应page marker正文",
    ):
        assert token in skill
    assert "仅有文件名和页码不得通过引用复核" in skill


def test_read_filing_references_do_not_expand_early_exit_or_v1_scope() -> None:
    statement = read(SKILLS_ROOT / "read-filing/references/statement-reading.md")
    cn_structure = read(SKILLS_ROOT / "read-filing/references/filing-structure-cn.md")
    assert "仅L1-L3允许立即止步" in statement
    assert "其他风险继续完成事实抽取" in statement
    assert "季报流程不属于v1运行时" in cn_structure


def test_value_profile_has_reachable_output_quality_recovery() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "dispatch任何子skill之前检查持久化终态" in skill
    assert "output_quality_failure" in skill
    assert "[edit/research more/exit]" in skill
    assert "完全重新分析" in skill
    assert "未显式解除前不得重新调用financial-redflag-scan" in skill


def test_hk_scope_is_explicitly_limited_to_currently_listed_issuers() -> None:
    for path in SKILL_PATHS.values():
        assert "港股仅支持当前上市发行人" in read(path)


def test_changed_python_has_no_whitespace_between_chinese_characters() -> None:
    paths = (
        REPO_ROOT / "scripts/download_filings.py",
        REPO_ROOT / "scripts/download_research.py",
        REPO_ROOT / "scripts/extract_pdf.py",
        REPO_ROOT / "scripts/build_event_manifest.py",
        REPO_ROOT / "scripts/collect_event_evidence.py",
    )
    pattern = re.compile(r"[\u3400-\u9fff]\s+[\u3400-\u9fff]")
    violations = []
    for path in paths:
        for line_no, line in enumerate(read(path).splitlines(), start=1):
            if pattern.search(line):
                violations.append(f"{path}:{line_no}:{line}")
    assert not violations, "\n".join(violations)


def test_orchestrators_use_canonical_event_path_and_capture_cli_result() -> None:
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        assert "--out <canonical-event-manifest-path>" in skill
        assert "读取构建器stdout返回的真实发布路径" in skill
        assert "--out <temporary-event-manifest-path>" not in skill


def test_value_profile_uses_cas_for_every_profile_write() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "scripts/publish_text_cas.py" in skill
    assert "--expected-sha256 <baseline-profile-sha256>" in skill
    assert "并发冲突时不得覆盖" in skill


def test_finalizer_revalidates_live_official_sources() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    finalizer = skill.split("**最终证据绑定**", 1)[1].split("### §4 Operational Boilerplate", 1)[0]
    assert "scripts/build_event_manifest.py --revalidate" in finalizer
    assert "重新请求全部官方来源" in finalizer
    assert "仅重算本地manifest哈希不够" in finalizer


def test_value_profile_recovers_both_redflag_human_terminal_states() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("5. **Resume schema migration**", 1)[1].split("### Step 2", 1)[0]
    assert "`manual_review`和`output_quality_failure`" in migration
    assert "[edit/research more/exit]" in migration
    assert "完全重新分析" in migration
    assert "缺行也不得自动重派" in migration


def test_value_profile_passes_read_filing_facts_and_full_mode_b_arguments() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    reading = skill.split("4. **阅读层事实调用**", 1)[1].split("5. **Resume schema migration**", 1)[
        0
    ]
    for token in (
        "--target-profile",
        "--section",
        "--ticker",
        "--year",
        "--as-of",
        "--filing-manifest",
        "--event-manifest",
        "--auto|--interactive",
    ):
        assert token in reading
    dispatch = skill.split("#### 3b. Scoped research dispatch", 1)[1].split(
        "#### 3c. Main-agent review", 1
    )[0]
    assert "read-filing返回的`facts/citations/warnings`" in dispatch
    assert "传给普通worker" in dispatch
    assert "不接收隐式内存handoff" in dispatch


def test_value_profile_download_command_is_executable_and_uses_temporary_manifest() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    audit = skill.split("2. **Audit `data/filings/<ticker>/`**", 1)[1].split(
        "2.5. **构造并持久化source manifests**", 1
    )[0]
    assert "--include-prospectus?" not in audit
    assert "--manifest-out <temporary-annual-manifest-path>" in audit
    assert "港股不传`--include-prospectus`" in audit


def test_read_filing_discovers_year_and_as_of_before_event_collection() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 1B", 1)[0]
    assert "先只读discovery确定YEAR和AS_OF" in bootstrap
    assert bootstrap.index("先只读discovery确定YEAR和AS_OF") < bootstrap.index(
        "collect_event_evidence.py"
    )


def test_read_filing_mode_a_uses_exact_citation_contract() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    assert "Mode A和Mode B共用" in skill
    for token in (
        "source_pdf_sha256",
        "artifact_sha256",
        "page",
        "quote",
    ):
        assert token in skill


def test_redflag_standalone_consumes_read_filing_facts() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    mode_a = skill.split("### Step 1", 1)[1].split("### Step 2", 1)[0]
    assert "先运行`read-filing` Mode A" in mode_a
    assert "Mode A调用`read-filing` Mode B" in mode_a
    assert "Mode B同样调用`read-filing` Mode B" in mode_a
    assert "上游成功" in mode_a
    assert "facts/citations/warnings" in mode_a


def test_management_promise_table_persists_comparability_fields() -> None:
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    promise = template.split("### §4.2企业家评估", 1)[1].split("### §4.3", 1)[0]
    assert (
        "|年度|指标ID|单位|口径|管理层目标|目标方向|实际值|比较方法|绝对差|gap|directional_miss|来源|"
        in (promise.replace(" ", ""))
    )


def test_redflag_rows_use_matching_denominators_and_dedicated_rules() -> None:
    registry = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan/references/thresholds.yaml")
    )
    checks = registry["checks"]
    for key in (
        "soft_intangible_impairment_assumption",
        "construction_in_progress_persistence",
    ):
        assert key in checks
        assert "window_years" in checks[key]
        assert "comparison" in checks[key]
        assert "minimum_periods" in checks[key]
        assert "not_applicable_when" in checks[key]
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    assert "商誉占归母净资产" in template
    assert "商誉占总资产>5%" not in template
    assert "thresholds.yaml:checks.soft_intangible_impairment_assumption" in template
    assert "thresholds.yaml:checks.construction_in_progress_persistence" in template


def test_downloader_commands_bind_listing_profile_evidence() -> None:
    contract = read(SKILLS_ROOT / "read-filing/references/evidence-contract.md")
    assert "--listing-profile-bundle <actual-official-query-bundle-path>" in contract
    assert "annual manifest与event manifest的listing profile路径及SHA-256一致" in contract
    for path in SKILL_PATHS.values():
        skill = read(path)
        assert "read-filing/references/evidence-contract.md" in skill


def test_read_filing_routes_banks_away_from_generic_cash_early_exits() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    early_exit = skill.split("### §2.1", 1)[1].split("### §2.2", 1)[0]
    execution = skill.split("### Step 2", 1)[1].split("### Step 2.5", 1)[0]
    reconciliation = skill.split("### Step 5", 1)[1].split("### Step 6", 1)[0]

    for block in (early_exit, execution, reconciliation):
        assert "银行" in block
        assert "不使用销售收现、常规CFO/NI" in block
        assert "银行10行替代bundle" in block


def test_bank_credit_cost_matrix_has_deterministic_trend_boundaries() -> None:
    registry = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    matrix = registry["checks"]["bank_bundle"]["credit_cost_matrix"]

    assert matrix["trend_comparison"] == ("current_vs_immediately_prior_comparable_fiscal_year")
    assert matrix["trend_tolerance_percentage_points"] == 0.01
    assert matrix["rising"] == "delta_greater_than_or_equal_to_positive_tolerance"
    assert matrix["falling"] == "delta_less_than_or_equal_to_negative_tolerance"
    assert matrix["stable"] == "absolute_delta_less_than_tolerance"
    assert "stable_credit_cost_and_rising_npl" in matrix
    assert "stable_credit_cost_with_stable_or_falling_npl" in matrix

    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "当前财年与紧邻前一可比财年" in skill
    assert "1个基点" in skill
    assert "不再叠加历史/同业方向规则" in skill


def test_every_documented_filing_download_binds_official_listing_profile() -> None:
    for path in SKILL_PATHS.values():
        skill = read(path)
        command_lines = [
            line
            for line in skill.splitlines()
            if "download_filings.py" in line and "--years" in line
        ]
        if not command_lines:
            assert "先运行`read-filing` Mode A" in skill, path
            continue
        for command_line in command_lines:
            assert "--listing-date <official-listing-date>" in command_line
            assert "--listing-profile-bundle <actual-official-query-bundle-path>" in command_line


def test_event_query_plan_has_evidence_based_source_discovery_contract() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    reference_path = SKILLS_ROOT / "read-filing" / "references" / "event-source-discovery.md"

    assert reference_path.is_file()
    assert "references/event-source-discovery.md" in skill
    reference = read(reference_path)
    for required in (
        "不得猜测接口",
        "实际官方请求",
        "HTTP方法",
        "请求编码",
        "分页字段",
        "response_adapter",
        "官方域名",
        "dry run",
        "abort",
    ):
        assert required in reference


def test_value_profile_creates_target_before_read_filing_mode_b() -> None:
    skill = read(SKILL_PATHS["value-profile"])

    assert skill.index("3.5. **Derive output path**") < skill.index("4. **阅读层事实调用**")


def test_annual_manifest_paths_are_content_addressed_and_live_revalidated() -> None:
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        assert "annual-reports-<AS_OF>-<content-sha256>.json" in skill
        assert "Part 0持久化路径及SHA-256" in skill
    finalizer = (
        read(SKILL_PATHS["value-profile"])
        .split("**最终证据绑定**", 1)[1]
        .split("### §4 Operational Boilerplate", 1)[0]
    )
    assert "scripts/download_filings.py --revalidate" in finalizer
    assert "重新请求年报官方目录和选中PDF" in finalizer


def test_management_mode_a_downloads_to_temporary_manifest() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    audit = skill.split("4. **Audit`data/filings/<ticker>/`**:", 1)[1].split(
        "5. **构造canonical manifests**", 1
    )[0]

    assert "--manifest-out <temporary-annual-manifest-path>" in audit


def test_management_guidance_gate_supports_directional_targets() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    completion_gate = skill.split("**`§4.2`完成条件**", 1)[1].split("**`§4.8`完成条件**", 1)[0]
    dispatch = skill.split("**承诺 vs 兑现5年表骨架**", 1)[1].split("**董事长5年评估问题列表**", 1)[
        0
    ]

    for required in (
        "目标方向",
        "比较方法",
        "绝对差",
        "百分比gap仅适用于",
        "上限",
        "减亏",
    ):
        assert required in completion_gate
        assert required in dispatch


def test_management_targeted_dependency_failure_has_schema_valid_response() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    response_contract = skill.split("返回值必须是以下JSON对象", 1)[1].split("**确认策略**", 1)[0]

    assert '"terminal_status": "dependency_failure"' in response_contract
    assert '"failure_reason": "<未通过的前置gate及证据>"' in response_contract
    assert "dependency_failure时同时满足" in response_contract
    assert "`draft_sections={}`" in response_contract
    assert "`management_pending=true`" in response_contract


def test_management_query_plan_uses_official_source_discovery() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    bootstrap = skill.split("### Step 1 — Bootstrap", 1)[1].split("### Step 2 — 模式判定", 1)[0]

    assert "references/event-source-discovery.md" in bootstrap
    assert "实际官方请求" in bootstrap
    assert "不得猜测接口" in bootstrap


def test_bootstrap_collects_listing_bundle_before_filing_download() -> None:
    for skill_name in (
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        assert skill.index("scripts/collect_event_evidence.py") < skill.index(
            "scripts/download_filings.py"
        )


def test_redflag_standalone_reuses_evidence_then_reads_facts_in_memory() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    facts = skill.split("**建立上游事实层**", 1)[1].split("### Step 2", 1)[0]
    assert "Mode A调用`read-filing` Mode B" in facts
    assert "Mode B同样调用`read-filing` Mode B" in facts


def test_redflag_inapplicable_rows_have_executable_completion_rule() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    assert "`不适用/无`不要求伪造实际值或阈值" in skill
    assert "适用性依据和页码或URL" in skill
    assert "manifest选中PDF路径派生" in skill
    assert "证据置信度保持`高`" in skill


def test_read_filing_bank_and_resume_contracts_are_complete() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    for required in (
        "银行10行事实输出",
        "不良率与关注类迁徙",
        "关联授信与大额风险暴露",
        'artifact_sha256["text.md"]',
        "证据阶段checkpoint",
        "同一AS_OF内容漂移",
        "内容寻址版本并原子改绑",
    ):
        assert required in skill
    self_check = skill.split("## §5常见错误自检表", 1)[1]
    assert "银行写`不适用`,改查银行10行" in self_check


def test_management_failure_and_recovery_contracts_are_closed() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile/template-zh.md")
    for required in (
        '"terminal_status": "failure"',
        "preflight或live revalidation失败",
        "../financial-redflag-scan/references/thresholds.yaml",
        "dependency_failure时同时满足",
        "`management_pending=true`",
    ):
        assert required in management
    for required in (
        "terminal_status=failure",
        "terminal_status=dependency_failure",
        "management_pending=true",
        "[edit/research more/exit]",
    ):
        assert required in profile
    section = template.split("### §4.2", 1)[1].split("### §4.3", 1)[0]
    for required in ("目标方向", "比较方法", "绝对差", "gap=N/A"):
        assert required in section
    assert "道德风险其他事项" in template
    assert "虚假陈述和财务造假" not in template.split("| 道德风险 |", 1)[1].splitlines()[0]


def test_profile_publication_guards_bound_manifests() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    assert "--guard <bound-annual-manifest-path>:<sha256>" in skill
    assert "--guard <bound-event-manifest-path>:<sha256>" in skill


def test_nonpositive_investment_denominators_cannot_pass_ratio_thresholds() -> None:
    moat = read(SKILLS_ROOT / "value-profile" / "references" / "moat-framework.md")
    management = read(SKILL_PATHS["management-analysis"])

    assert "累计净利润≤0" in moat
    assert "不得判为`pass`或`顶级pass`" in moat
    assert "PE≤0或不可定义" in management
    assert "不得落入`<25PE`" in management
    assert "5年累计NI≤0" in management


def test_management_risk_severity_does_not_lower_evidence_confidence() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    veto = management.split("### §2.7", 1)[1].split("### §2.8", 1)[0]

    assert "风险严重度和证据置信度分开" in veto
    assert "官方处罚窗口完整" in veto
    assert "证据置信度保持`高`" in veto
    assert "将置信度标低" not in veto


def test_management_directional_misses_have_a_reachable_veto_rule() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    guidance = management.split("### §2.1", 1)[1].split("### §2.2", 1)[0]
    veto = management.split("### §2.7", 1)[1].split("### §2.8", 1)[0]

    assert "directional_miss=true" in guidance
    assert "连续3年`directional_miss=true`" in veto
    assert "同一指标ID" in veto


def test_machine_citations_are_persisted_in_all_final_outputs() -> None:
    reading = read(SKILL_PATHS["read-filing"])
    mode_a = reading.split("**Mode A 输出骨架**", 1)[1].split("### Step 7.5", 1)[0]
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")

    for text in (mode_a, profile, template):
        for token in (
            "source_pdf_sha256",
            "artifact_sha256",
            "page",
            "quote",
        ):
            assert token in text
    assert "机器引用清单" in mode_a
    assert "机器引用清单" in template


def test_unqualified_a_share_emphasis_paragraph_is_not_a_prerequisite_veto() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    prerequisites = profile.split("### §2.2", 1)[1].split("### §2.3", 1)[0]

    assert "A股非银行" in prerequisites
    assert "无保留审计意见" in prerequisites
    assert "强调事项段" in prerequisites
    assert "标准无保留" not in prerequisites


def test_bank_overlay_uses_only_the_institution_specific_cet1_minimum() -> None:
    overlay = read(SKILLS_ROOT / "value-profile" / "references" / "industry-overlays.md")
    bank = overlay.split("## 2. 银行", 1)[1].split("## 3.", 1)[0]
    q7 = next(line for line in bank.splitlines() if "| §Q7偿债能力 |" in line)

    assert "机构适用" in q7
    assert "thresholds.yaml" in q7
    assert "8.5%" not in q7


def test_orchestrators_capture_the_collectors_real_bundle_path() -> None:
    for skill_name in (
        "read-filing",
        "financial-redflag-scan",
        "management-analysis",
        "value-profile",
    ):
        skill = read(SKILL_PATHS[skill_name])
        assert "读取采集器stdout返回的真实bundle路径" in skill
        assert "后续下载器和构建器只使用该真实路径" in skill
        for line in skill.splitlines():
            if "download_filings.py" in line and "--years" in line:
                assert "--listing-profile-bundle <actual-official-query-bundle-path>" in line
            if "build_event_manifest.py --bundle" in line:
                assert "--bundle <actual-official-query-bundle-path>" in line


def test_redflag_mode_b_can_return_evidence_rebuild_failure() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    response = skill.split("Mode B只返回以下版本化JSON schema", 1)[1].split("子skill若发现", 1)[0]

    assert "dependency_failure" in response
    assert "rebuild_evidence" in response
    assert "父skill重建" in response


def test_standalone_collect_failures_have_preexisting_recovery_scaffolds() -> None:
    markers = {
        "management-analysis": "3.6. **先采集官方查询bundle**",
        "value-profile": "1.6. **先采集官方查询bundle**",
    }
    for skill_name, collector_marker in markers.items():
        skill = read(SKILL_PATHS[skill_name])
        scaffold_index = skill.index("先创建standalone恢复骨架")
        collector_index = skill.index(collector_marker)
        assert scaffold_index < collector_index
        before_collector = skill[scaffold_index:collector_index]
        for token in ("AS_OF", "运行状态", "失败原因"):
            assert token in before_collector


def test_value_profile_bootstrap_failure_reports_early_and_persists_partial_profile() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    bootstrap = skill.split("1.55. **先创建standalone恢复骨架", 1)[1].split(
        "2. **Audit `data/filings/<ticker>/`**", 1
    )[0]

    for requirement in (
        "同一轮立即反馈用户",
        "阻塞项",
        "受影响结论",
        "不受影响且已完成的工作",
        "准确的人工处理动作",
        "部分profile路径",
        "扩展为简版/部分profile",
        "保留已完成的年报研究",
        "管理层和监管结论标`需人工`",
        "只阻断数字估值和否定性监管结论",
    ):
        assert requirement in bootstrap


def test_value_profile_reuses_hkex_listing_bootstrap_without_chrome() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    bootstrap = skill.split("1.6. **先采集官方查询bundle**", 1)[1].split(
        "2. **Audit `data/filings/<ticker>/`**", 1
    )[0]
    discovery = read(REPO_ROOT / ".claude/skills/read-filing/references/event-source-discovery.md")

    for requirement in (
        "hkex_equity_quote_token_v1",
        "不得每次打开Chrome/CDP",
        "不得把token硬编码",
        "仅当自动bootstrap明确报告",
    ):
        assert requirement in bootstrap
    for requirement in (
        "两次独立普通HTTP会话验证",
        "token和实时价格字段不落盘",
        "先URL解码再由请求库编码",
        "才按上面的发现流程重新打开浏览器网络面板",
    ):
        assert requirement in discovery


def test_documented_python_commands_use_an_executable_entrypoint() -> None:
    profile = read(SKILL_PATHS["value-profile"])

    assert "uv run python scripts/download_research.py" in profile
    assert "uv run python scripts/publish_text_cas.py" in profile
    for line in profile.splitlines():
        if "scripts/download_research.py" in line or "scripts/publish_text_cas.py" in line:
            assert "uv run python" in line


def test_redflag_download_uses_a_temporary_manifest_before_preflight() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    audit = skill.split("4. **Audit`data/filings/<ticker>/`**", 1)[1].split(
        "5. **建立canonical evidence**", 1
    )[0]

    assert "--manifest-out <temporary-annual-manifest-path>" in audit


def test_management_statement_reference_resolves_to_read_filing() -> None:
    management = read(SKILL_PATHS["management-analysis"])

    assert "../read-filing/references/statement-reading.md" in management
    assert "`references/statement-reading.md`" not in management


def test_read_filing_only_modified_audit_opinions_trigger_l1() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    statement = read(SKILLS_ROOT / "read-filing" / "references" / "statement-reading.md")
    l1 = skill.split("### §2.1", 1)[1].split("### §2.2", 1)[0]
    early_check = skill.split("### Step 2", 1)[1].split("### Step 2.5", 1)[0]

    for text in (l1, early_check, statement):
        assert "非标准无保留" not in text
    for opinion in ("保留意见", "无法表示意见", "否定意见"):
        assert opinion in l1
    assert "强调事项段" in l1
    assert "底层事项" in l1


def test_read_filing_ratio_rules_reject_nonpositive_denominators() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    statement = read(SKILLS_ROOT / "read-filing" / "references" / "statement-reading.md")
    combined = skill + statement

    for required in (
        "利息支出≤0时不计算利息保障倍数",
        "累计归母净利润≤0时不计算CapEx/NI",
        "累计归母净利润≤0时不计算有息负债/净利润",
        "不适用—分母非正",
    ):
        assert required in combined


def test_read_filing_screening_does_not_force_low_evidence_confidence() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    early_output = skill.split("早退时只写以下短结构", 1)[1].split("未早退时使用完整骨架", 1)[0]
    mode_b_flags = skill.split("**Mode B初筛flags**", 1)[1].split("**证据置信度固定映射**", 1)[0]

    assert "初筛严重度与证据置信度分开" in skill
    assert "**置信度:**低" not in early_output
    assert "**置信度:**低" not in mode_b_flags
    assert "完整官方证据可为`高`" in skill


def test_management_guidance_direction_is_independent_of_sign() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    guidance = skill.split("### §2.1", 1)[1].split("### §2.2", 1)[0]

    assert "先按目标方向选择比较方法,再处理目标值正负号" in guidance
    assert "guidance>0且目标方向为上限" in guidance
    assert "按上限比较" in guidance


def test_management_unreliability_does_not_lower_evidence_confidence() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    profile = read(SKILL_PATHS["value-profile"])
    guidance = management.split("### §2.1", 1)[1].split("### §2.2", 1)[0]
    dispatch = management.split("**承诺 vs 兑现5年表骨架**", 1)[1].split(
        "**董事长5年评估问题列表**", 1
    )[0]
    profile_fallback = profile.split("**§4管理层分析**", 1)[1].split("**管理层否决handoff**", 1)[0]

    for text in (guidance, dispatch, profile_fallback):
        assert "证据置信度" in text
        assert "不因管理层未兑现而降低" in text
        assert "置信度降一档" not in text
        assert "**置信度:**低" not in text


def test_management_standalone_save_guards_bound_manifests() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    mode_a_output = skill.split("**Mode A**:", 1)[1].split("**Mode B**:", 1)[0]

    assert "--guard <bound-annual-manifest-path>:<sha256>" in mode_a_output
    assert "--guard <bound-event-manifest-path>:<sha256>" in mode_a_output


def test_parent_handles_redflag_rebuild_evidence_action() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    actions = profile.split("**消费action_requests**", 1)[1].split("### Step 6", 1)[0]

    assert "`rebuild_evidence`" in actions
    assert "重建年报和事件证据后重试§4.5" in actions
    assert "未知action_request直接报schema错误" in actions


def test_redflag_subject_roster_replays_persisted_request_contract() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    source_preflight = skill.split("### Step 2", 1)[1].split("### Step 3", 1)[0]

    for token in (
        "http_method",
        "request_encoding",
        "request_headers",
        "query_params",
        "response_schema",
        "response_adapter",
    ):
        assert token in source_preflight
    assert "并使用构建器固定的GET+query请求契约" not in source_preflight


def test_cet1_regulatory_breach_requires_institution_specific_minimum() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    bank = thresholds["checks"]["bank_bundle"]

    for market in ("CN", "HK"):
        assert "cet1_ratio" not in bank["regulatory_minima"][market]
    assert bank["cet1_matrix"]["institution_specific_minimum_required"] is True
    assert bank["cet1_matrix"]["minimum_unavailable"] == ("pending_no_regulatory_breach")


def test_redflag_template_risk_severity_does_not_reduce_confidence() -> None:
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    checklist = template.split("### §4.5负面清单 — 排雷风险（29项）", 1)[1].split(
        "#### 6项高危附加检查", 1
    )[0]

    for row_id in (7, 8, 11, 16, 19, 29):
        row = next(line for line in checklist.splitlines() if line.startswith(f"| {row_id} |"))
        assert "降置信度" not in row


def test_redflag_checklist_nonpositive_denominators_are_deterministic() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    checklist_rules = thresholds["checks"]["checklist_rows"]

    assert checklist_rules["row_3"]["applicability"] == "positive_net_assets_only"
    assert checklist_rules["row_3"]["nonpositive_denominator"] == (
        "manual_review_report_absolute_values"
    )
    assert checklist_rules["row_20"]["cip_increment_branch_applicability"] == (
        "positive_net_income_only"
    )
    assert checklist_rules["row_20"]["nonpositive_denominator"] == (
        "branch_not_applicable_report_absolute_values"
    )

    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    fraud = read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "fraud-library.md")
    for text in (template, fraud):
        assert "清单第3项归母净资产≤0" in text
        assert "清单第20项归母净利润≤0" in text


def test_all_exhausted_evidence_retries_end_in_manual_review() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    capability = profile.split("§2.6.2任一失败", 1)[1].split("### §2.7", 1)[0]

    assert "**置信度:**需人工" in capability
    assert "人工处理清单" in capability
    assert "**置信度:** 低" not in capability


def test_read_filing_promise_rows_preserve_directional_identity() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    table = skill.split("§2.10.1 forecast vs actual 5年表必建", 1)[1].split("§2.10.2", 1)[0]
    for field in (
        "指标ID",
        "单位",
        "口径",
        "目标方向",
        "比较方法",
        "绝对差",
        "directional_miss",
    ):
        assert field in table


def test_management_veto_uses_one_canonical_directional_rule() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    management = read(SKILL_PATHS["management-analysis"])

    assert "management-analysis§2.7.2" in profile
    assert "不同指标不得拼接" in profile
    assert "directional_miss" in template.split("### §4.2", 1)[1].split("### §4.3", 1)[0]
    assert "证据置信度不因管理层未兑现而降低" in template
    assert "连续3年`directional_miss=true`触发" in management


def test_redflag_parent_and_child_share_rebuild_action_enum() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    action_rule = skill.split("§2.4.3不接受", 1)[1].split("§2.4.3a", 1)[0]
    schema = skill.split("Mode B只返回以下版本化JSON schema", 1)[1]

    assert "rebuild_evidence" in action_rule
    assert "rebuild_evidence" in schema


def test_redflag_complete_scan_consumes_read_filing_screening_flags() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    read_filing = read(SKILL_PATHS["read-filing"])

    assert "--complete-facts" in skill
    assert "L1至L3命中也继续完成排雷事实层" in skill
    assert "--complete-facts" in read_filing
    assert "Mode B无条件禁用该短路" in read_filing
    assert "`screening_flags`" in read_filing


def test_redflag_distinguishes_missing_evidence_from_inapplicability() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    checks = thresholds["checks"]

    assert checks["soft_intangible_impairment_assumption"]["missing_evidence"] == ("pending")
    assert checks["construction_in_progress_persistence"]["missing_evidence"] == ("pending")
    assert checks["overdue_receivables_persistence"]["missing_evidence"] == "pending"


def test_redflag_supports_ah_identity_and_insurer_bundle() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    schema = read(SKILLS_ROOT / "read-filing" / "references" / "event-query-plan.schema.json")

    assert "查询发行人代码映射[source_exchange]" in skill
    assert "保险公司替代bundle" in skill
    assert "保险公司替代bundle" in template
    assert '"insurer"' in schema


def test_redflag_completion_rejects_placeholders_and_supports_event_citations() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    preparation = skill.split("Mode B准备", 1)[1].split("### Step 3", 1)[0]
    citation = skill.split("机器引用清单", 1)[1].split("**Mode A**", 1)[0]

    for field in ("建议动作", "父级动作请求", "排雷终态", "排雷失败原因"):
        assert field in preparation
    assert "至少一条非占位机器引用" in preparation
    assert "source_type=filing" in citation
    assert "source_type=event_document" in citation
    assert "event_manifest_sha256" in citation
    assert "document_url" in citation
    assert "content_sha256" in citation


def test_redflag_dependency_and_severity_rules_are_deterministic() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )

    assert "dependency_failure" in skill
    assert "证据阶段" in skill
    assert "行业上下文只解释风险和动作" in skill
    assert "不得覆盖thresholds.yaml固定严重度" in skill
    rows = thresholds["checks"]["checklist_rows"]
    for row_id in ("row_4", "row_5", "row_8", "row_22", "row_23", "row_25", "row_28"):
        assert "nonpositive_denominator" in rows[row_id]
        assert "severity_when_nonpositive" in rows[row_id]


def test_cash_yield_basis_is_canonical_and_comparable() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    rule = thresholds["checks"]["cash_yield_peer_deviation"]

    assert rule["company_yield_numerator"] == "interest_income"
    assert rule["company_yield_denominator"] == (
        "average_unrestricted_interest_bearing_cash_and_deposits"
    )
    assert rule["average_basis"] == "opening_and_closing_average"
    assert rule["peer_basis"] == "same_numerator_denominator_and_average_basis"


def test_value_profile_persists_complete_workflow_state() -> None:
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    skill = read(SKILL_PATHS["value-profile"])
    part_zero = template.split("## Part 0", 1)[1].split("### 执行摘要", 1)[0]

    for field in (
        "证据阶段",
        "运行状态",
        "失败原因",
        "人工处理清单",
    ):
        assert field in part_zero
    assert "成功终态" in skill and "运行状态=已完成" in skill
    assert "证据阶段=已绑定" in skill


def test_value_profile_auto_mode_never_prompts_for_download() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    auto = skill.split("Auto mode (default)", 1)[1].split("Interactive mode", 1)[0]
    download = skill.split("Audit `data/filings", 1)[1].split("构造并持久化source manifests", 1)[0]

    assert "自动执行下载" in auto
    assert "Auto" in download and "不显示菜单" in download
    assert "Interactive" in download and "yes/no/show-command" in download
    assert "MUST NOT 未经 Step 1.2显式确认就自动下载 PDF" not in skill


def test_value_profile_mandatory_failures_cannot_complete_as_low() -> None:
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    capability = template.split("### §1.8", 1)[1].split("### §2", 1)[0]
    valuation = template.split("### §4.3 3年后净利润及估值", 1)[1].split("### §4.4", 1)[0]

    assert "置信度=需人工" in capability
    assert "置信度=低" not in capability
    assert "不拆 = 需人工" in valuation
    assert '置信度直接 "低"' not in valuation


def test_value_profile_sections_own_machine_citations() -> None:
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    citation_count = template.count("**机器引用清单:**")
    confidence_count = template.count("**置信度:**")

    assert citation_count >= confidence_count
    assert "section_id" in template
    assert "artifact_path" in template


def test_value_profile_hides_machine_citations_from_rendered_markdown() -> None:
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    output_template = template.split("<!-- ⚠️ TEMPLATE-ONLY区域结束", 1)[1].split("-->", 1)[1]
    rendered_source = re.sub(r"<!--.*?-->", "", output_template, flags=re.DOTALL)

    assert "机器引用清单" not in rendered_source
    assert "<!-- **机器引用清单:**" in output_template
    assert "HTML注释" in profile
    for subskill_name in (
        "financial-redflag-scan",
        "product-analysis",
        "management-analysis",
    ):
        assert "HTML注释" in read(SKILL_PATHS[subskill_name])


def test_value_profile_bank_migration_replaces_all_generic_metrics() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    migration = skill.split("银行schema迁移例外", 1)[1].split("对Part 4 §4.5", 1)[0]

    for section_id in ("part1/§1.6", "part1/§3.5", "part1/§3.6"):
        assert section_id in migration


def test_historical_valuation_uses_an_immutable_market_snapshot_contract() -> None:
    skill = read(SKILL_PATHS["value-profile"])
    valuation = read(SKILLS_ROOT / "value-profile" / "references" / "valuation.md")

    for text in (skill, valuation):
        assert "market-data manifest" in text
        assert "价格官方响应SHA-256" in text
        assert "无风险利率官方响应SHA-256" in text
        assert "市场数据日期≤AS_OF" in text


def test_read_filing_default_as_of_uses_a_stable_discovery_cutoff() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    bootstrap = skill.split("### Step 1", 1)[1].split("### Step 1B", 1)[0]

    assert "discovery_cutoff" in bootstrap
    assert "只读目录响应时间" in bootstrap
    assert "用所选版本首次有效披露时间固定最终AS_OF" in bootstrap
    assert "按最终AS_OF重跑版本状态机" in bootstrap
    assert "两次选中版本必须一致" in bootstrap


def test_read_filing_has_an_executable_hk_listing_document_route() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    history = skill.split("### Step 2.5", 1)[1].split("### Step 3", 1)[0]

    assert "港股上市文件路由" in history
    assert "HKEX官方上市文件目录" in history
    assert "查询URL、查询参数、响应哈希、官方结果总数" in history
    assert "完整上市文件PDF绝对路径和SHA-256" in history
    assert "缺失时标`需人工`" in history


def test_read_filing_full_output_persists_manifest_paths() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    full_output = skill.split("未早退时使用完整骨架", 1)[1].split(
        "**Mode B输出**",
        1,
    )[0]

    assert "**filing_manifest_path**" in full_output
    assert "**event_manifest_path**" in full_output


def test_read_filing_citations_are_typed_and_bind_final_artifacts() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    mode_a = skill.split("**Mode A 输出骨架**", 1)[1].split(
        "**Mode B输出**",
        1,
    )[0]
    mode_b = skill.split("**Mode B输出**", 1)[1].split(
        "父skill接受Mode B返回对象",
        1,
    )[0]

    for text in (mode_a, mode_b):
        for field in (
            "section_id",
            "source_type",
            "artifact_path",
            "source_pdf_sha256",
            "artifact_sha256",
            "page",
            "quote",
        ):
            assert field in text
    assert "artifact_path不得指向scratch、staging或临时抽取目录" in skill


def test_read_filing_closes_raw_pdf_publication_and_resume_contracts() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    schema = read(SKILLS_ROOT / "read-filing" / "references" / "event-query-plan.schema.json")

    for phrase in (
        "source_type=filing_pdf",
        "raw PDF引用",
        "最终live revalidation",
        "--guard <bound-annual-manifest-path>:<sha256>",
        "--guard <bound-event-manifest-path>:<sha256>",
        'terminal_status":"manual_review',
        "filing_manifest_path",
        "event_manifest_path",
        "target_fiscal_year",
        "target_section",
        "artifact_path=<absolute-final-artifact-path>",
    ):
        assert phrase in skill
    assert '"include_open_before_start"' in schema
    assert '"const": true' in schema


def test_management_contract_closes_veto_governance_and_completion_paths() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")

    section_42 = template.split("### §4.2", 1)[1].split("### §4.3", 1)[0]
    assert "连续3年`directional_miss=true`" in section_42
    assert "gap>10%连续≥3年→置信度低" not in section_42
    for phrase in (
        "source_type=event_document",
        "event_manifest_sha256",
        "document_url",
        "content_sha256",
        'terminal_status":"vetoed',
        "运行状态:** <进行中/需人工/已完成/已否决>",
        "§4.1",
        "§4.3",
        "§4.4",
        "§4.5",
        "§4.6",
        "§4.7",
        "提名委员会",
        "jurisdiction",
        "--auto`自动执行下载",
    ):
        assert phrase in skill
    assert "任一失败则全部保持旧绑定" not in skill


def test_redflag_registry_and_insurer_contracts_are_fully_executable() -> None:
    skill = read(SKILL_PATHS["financial-redflag-scan"])
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    schema = read(SKILLS_ROOT / "read-filing" / "references" / "event-query-plan.schema.json")

    checks = thresholds["checks"]
    assert "insurer_bundle" in checks
    assert len(checks["insurer_bundle"]["metrics"]) == 10
    assert "ia" in schema
    assert "checklist_thresholds" in checks
    assert set(checks["checklist_thresholds"]) == {f"row_{index}" for index in range(1, 30)}
    assert (
        checks["soft_intangible_impairment_assumption"]["not_applicable_when"]
        == "no_soft_intangibles_or_no_impairment_test_required"
    )
    bank = checks["bank_bundle"]
    for metric in bank["directions"]:
        assert metric in bank["metric_definitions"]
    for field in ("value", "unit", "numerator", "denominator", "calculation_basis"):
        assert field in bank["peer_evidence_required_fields"]
    for phrase in (
        "保险公司替代bundle任一行缺失",
        "dependent_check_ids",
        "source_type=event_document",
        "page可为null",
        "生物资产可审计性",
        "高风险",
    ):
        assert phrase in skill


def test_latest_review_requires_executable_manifest_commands() -> None:
    read_filing = read(SKILL_PATHS["read-filing"])
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    profile = read(SKILL_PATHS["value-profile"])

    promotion = (
        "scripts/download_filings.py --promote <temporary-annual-manifest-path> "
        "--canonical-out <canonical-annual-manifest-path>"
    )
    annual_revalidate = "scripts/download_filings.py --revalidate <bound-annual-manifest-path>"
    event_revalidate = "scripts/build_event_manifest.py --revalidate <bound-event-manifest-path>"
    for text in (read_filing, redflag, profile):
        assert annual_revalidate in text
        assert event_revalidate in text
    assert promotion in read_filing
    assert "--source <draft-path>" in read_filing
    assert "--target <final-report-path>" in read_filing
    assert "--expected-sha256 <baseline-report-sha256>" in read_filing


def test_latest_review_unifies_issuer_identity_mapping() -> None:
    for skill_name in (
        "management-analysis",
        "financial-redflag-scan",
        "value-profile",
    ):
        text = read(SKILL_PATHS[skill_name])
        assert "Part 0查询发行人代码映射[exchange]" in text
        assert "查询发行人代码映射完整相等" in text


def test_latest_review_read_filing_contract_is_closed() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    invocation = skill.split("## §0", 1)[1].split("## §1", 1)[0]
    output = skill.split("**Mode B输出**", 1)[1].split("父skill接受Mode B返回对象", 1)[0]

    assert invocation.count("[--complete-facts]") >= 2
    assert "Mode A共用source preflight" in skill
    assert "Mode B Part 0绑定校验" in skill
    assert "action_requests" in output
    assert "edit/research_more/rebuild_evidence/exit" in output
    assert "完全重新分析" in output
    for source_type in ("filing_text", "filing_pdf", "event_document"):
        assert source_type in output
    for event_field in (
        "event_manifest_sha256",
        "document_url",
        "content_sha256",
    ):
        assert event_field in output
    assert "source_type=filing;" not in skill


def test_latest_review_management_response_schema_is_discriminated() -> None:
    schema_path = SKILLS_ROOT / "management-analysis" / "references" / "mode-b-response.schema.json"
    schema = json.loads(read(schema_path))
    statuses = {branch["properties"]["terminal_status"]["const"] for branch in schema["oneOf"]}
    assert statuses == {
        "success",
        "pending",
        "failure",
        "dependency_failure",
        "vetoed",
    }
    skill = read(SKILL_PATHS["management-analysis"])
    assert "mode-b-response.schema.json" in skill
    assert "全部§4.pre和§4.1-§4.8完成条件" in skill
    assert "--auto保留pending终态并退出" in skill
    assert "rebuild_evidence" in skill


def management_mode_b_response() -> dict[str, object]:
    event_hash = "b" * 64
    content_hash = "c" * 64
    return {
        "schema_version": "1.0",
        "terminal_status": "success",
        "failure_reason": None,
        "stage": "A",
        "target_sections": ["part1/§4.pre"],
        "draft_sections": {"part1/§4.pre": "<完整section正文,含**机器引用清单:**>"},
        "draft_veto": False,
        "management_veto": False,
        "management_pending": False,
        "pending_gate": False,
        "filing_manifest_sha256": "a" * 64,
        "event_manifest_sha256": event_hash,
        "counterpart_filing_manifest_sha256s": {},
        "workflow_complete": False,
        "reason": None,
        "citations": [
            {
                "section_id": "part1/§4.pre",
                "jurisdiction": "SZ",
                "source_type": "event_document",
                "event_manifest_sha256": event_hash,
                "document_url": "https://official.example/document",
                "artifact_path": "/absolute/evidence/document",
                "content_sha256": content_hash,
                "artifact_sha256": content_hash,
                "page": None,
                "quote": "<exact quote>",
            }
        ],
        "findings": [
            canonical_finding(
                "management-analysis",
                "management_integrity",
                "management_team",
                "000001.SZ/management",
            )
        ],
        "unresolved_rows": [],
        "action_requests": [],
    }


def canonical_finding(
    owner_skill: str,
    judgment_domain: str,
    subject_type: str,
    subject_id: str,
) -> dict[str, object]:
    return {
        "canonical_finding_id": "d" * 64,
        "owner_skill": owner_skill,
        "judgment_domain": judgment_domain,
        "finding_type": "material_risk",
        "subject_type": subject_type,
        "subject_id": subject_id,
        "occurrence_date": "2025-01-15",
        "canonical_evidence_ids": ["e" * 64],
        "severity": "warning",
        "evidence_grade": "high",
        "judgment": "基于已核验证据形成的专题判断",
        "citation_ids": ["f" * 64],
    }


def filing_citation(section_id: str) -> dict[str, object]:
    return {
        "section_id": section_id,
        "jurisdiction": "SZ",
        "source_type": "filing_text",
        "artifact_path": "/absolute/evidence/text.md",
        "source_pdf_sha256": "1" * 64,
        "artifact_sha256": "2" * 64,
        "page": 12,
        "quote": "已核验的年报原文",
    }


def product_mode_b_response() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "terminal_status": "success",
        "failure_reason": None,
        "target_sections": ["part1/§1.1"],
        "draft_sections": {
            "part1/§1.1": (
                "## 行业特有产品结构\n\n"
                "|流程|材料|良率|周期|产能|库存|渠道|售后|反馈|成本|瓶颈|证据|\n"
                "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
                "|量产|树脂|需人工|需人工|需人工|需人工|直营|退换|复购|需人工|模具|中|"
            )
        },
        "product_facts": [],
        "process_facts": [],
        "competition_facts": [],
        "moat_handoff": [],
        "findings": [
            canonical_finding(
                "product-analysis",
                "product_competitiveness",
                "product_system",
                "000001.SZ/core-products",
            )
        ],
        "citations": [filing_citation("part1/§1.1")],
        "warnings": [],
        "unresolved_items": [],
        "filing_manifest_sha256": "a" * 64,
        "event_manifest_sha256": "b" * 64,
        "counterpart_filing_manifest_sha256s": {},
    }


def redflag_mode_b_response() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "terminal_status": "completed",
        "failure_reason": None,
        "target_sections": ["part4/§4.5"],
        "draft_section": "## 财务排雷\n\n自由Markdown正文\n\n**机器引用清单:**\n- citation",
        "risk_counts": {"warning": 1, "high_risk": 0, "veto": 0, "pending": 0},
        "valuation_blocked": False,
        "manual_review_required": False,
        "filing_manifest_sha256": "a" * 64,
        "event_manifest_sha256": "b" * 64,
        "counterpart_filing_manifest_sha256s": {},
        "action_requests": [],
        "confidence": "high",
        "citations": [filing_citation("part4/§4.5")],
        "findings": [
            canonical_finding(
                "financial-redflag-scan",
                "company_financials",
                "listed_company",
                "000001.SZ",
            )
        ],
        "unresolved_items": [],
    }


def test_judgment_schemas_allow_free_markdown_and_reject_unknown_envelope_fields() -> None:
    responses = {
        "product-analysis": product_mode_b_response(),
        "management-analysis": management_mode_b_response(),
        "financial-redflag-scan": redflag_mode_b_response(),
    }
    for skill_name, response in responses.items():
        schema_path = SKILLS_ROOT / skill_name / "references/mode-b-response.schema.json"
        schema = json.loads(read(schema_path))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        assert not list(validator.iter_errors(response))

        unknown_field = deepcopy(response)
        unknown_field["unexpected_top_level_field"] = True
        assert list(validator.iter_errors(unknown_field))


def test_financial_and_management_findings_share_evidence_but_not_judgment_identity() -> None:
    read_filing = read(SKILL_PATHS["read-filing"])
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    management = read(SKILL_PATHS["management-analysis"])
    profile = read(SKILL_PATHS["value-profile"])
    algorithm = (
        "sha256(judgment_domain|subject_type|subject_id|finding_type|"
        "occurrence_date|sorted(canonical_evidence_ids))"
    )
    for text in (redflag, management, profile):
        assert algorithm in text
    assert "canonical_evidence_id" in read_filing
    assert "judgment_domain=company_financials" in redflag
    assert "judgment_domain=management_integrity" in management
    assert "不同判断主体不得合并" in profile

    management_schema = json.loads(
        read(SKILLS_ROOT / "management-analysis/references/mode-b-response.schema.json")
    )
    invalid_management_subject = management_mode_b_response()
    invalid_management_subject["findings"][0]["subject_type"] = "listed_company"
    assert list(Draft202012Validator(management_schema).iter_errors(invalid_management_subject))


def test_management_mode_b_response_schema_rejects_invalid_semantics() -> None:
    schema_path = SKILLS_ROOT / "management-analysis" / "references" / "mode-b-response.schema.json"
    validator = Draft202012Validator(json.loads(read(schema_path)))
    valid = management_mode_b_response()
    assert not list(validator.iter_errors(valid))

    invalid_responses: list[dict[str, object]] = []

    empty_success = deepcopy(valid)
    empty_success["draft_sections"] = {}
    invalid_responses.append(empty_success)

    wrong_stage_key = deepcopy(valid)
    wrong_stage_key["stage"] = "B"
    invalid_responses.append(wrong_stage_key)

    untyped_citation = deepcopy(valid)
    untyped_citation["citations"] = [{"section_id": "part1/§4.pre"}]
    invalid_responses.append(untyped_citation)

    veto_without_reason = deepcopy(valid)
    veto_without_reason["draft_veto"] = True
    invalid_responses.append(veto_without_reason)

    pending_success = deepcopy(valid)
    pending_success["management_pending"] = True
    invalid_responses.append(pending_success)

    premature_workflow_completion = deepcopy(valid)
    premature_workflow_completion["workflow_complete"] = True
    invalid_responses.append(premature_workflow_completion)

    vetoed_pending = deepcopy(valid)
    vetoed_pending.update(
        {
            "terminal_status": "vetoed",
            "draft_sections": {},
            "draft_veto": True,
            "reason": "已持久化否决",
            "management_pending": True,
            "pending_gate": True,
            "unresolved_rows": ["part1/§4.8/row-1"],
        }
    )
    invalid_responses.append(vetoed_pending)

    for response in invalid_responses:
        assert list(validator.iter_errors(response))


def test_management_mode_b_documented_example_validates_against_schema() -> None:
    skill = read(SKILL_PATHS["management-analysis"])
    schema = json.loads(
        read(SKILLS_ROOT / "management-analysis" / "references" / "mode-b-response.schema.json")
    )
    response_contract = skill.split("返回值必须是以下JSON对象", 1)[1].split(
        "失败响应沿用同一顶层schema", 1
    )[0]
    example = json.loads(re.search(r"```json\s+(.*?)\s+```", response_contract, re.S).group(1))

    Draft202012Validator(schema).validate(example)


def test_management_schema_supports_pending_drafts_and_binds_citations() -> None:
    schema = json.loads(
        read(SKILLS_ROOT / "management-analysis" / "references" / "mode-b-response.schema.json")
    )
    validator = Draft202012Validator(schema)
    pending = management_mode_b_response()
    pending.update(
        {
            "terminal_status": "pending",
            "failure_reason": "part1/§4.pre/row-1缺证据",
            "management_pending": True,
            "pending_gate": True,
            "unresolved_rows": ["part1/§4.pre/row-1"],
            "workflow_complete": False,
        }
    )
    validator.validate(pending)

    unrelated = management_mode_b_response()
    unrelated["citations"][0]["section_id"] = "part1/§4.8"
    unrelated["citations"][0]["artifact_path"] = "relative/evidence"
    assert list(validator.iter_errors(unrelated))


def test_fresh_review_closes_remaining_cross_skill_contracts() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    profile = read(SKILL_PATHS["value-profile"])
    management = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )

    mode_a_header = redflag.split("2. **Mode A 准备**", 1)[1].split("3. **Mode B准备**", 1)[0]
    assert "dependency_failure" in mode_a_header
    assert "canonical citation ID" in redflag
    assert "已完成request_id直接跳过副作用" in profile
    assert "--counterpart-filing-manifest <exchange>:<absolute-json-path>" in redflag
    assert "--counterpart-filing-manifest <exchange>:<absolute-json-path>" in profile
    assert "counterpart_filing_manifest_sha256s" in redflag

    row_19 = thresholds["checks"]["checklist_thresholds"]["row_19"]
    assert row_19["denominator"] == "attributable_net_assets"
    assert row_19["nonpositive_denominator"] == "pending_report_absolute_values"
    registry = thresholds["checks"]["canonical_check_registry"]
    for namespace, count in (
        ("checklist", 29),
        ("high-risk", 6),
        ("reconciliation", 4),
        ("supplemental", 8),
        ("dimension", 5),
        ("bank", 10),
        ("insurer", 10),
    ):
        assert len(registry["ids"][namespace]) == count
    assert registry["deduplication_aliases"]
    assert registry["counting_precedence"]

    for text in (management, template):
        assert "指标ID、单位、口径" in text
        assert "状态、严重度、证据、引用" in text
    assert "逐个counterpart哈希执行子返回值/Part 0/文件三方一致" in profile
    assert "证据完整否决finalizer" in profile


def test_latest_review_directional_veto_is_persisted() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    section = template.split("### §4.2企业家评估", 1)[1].split("### §4.3", 1)[0]
    assert "| directional_miss |" in section
    assert "每行必须持久化`directional_miss`" in management
    assert "resume从该列逐行重建" in management


def test_latest_review_redflag_registry_matches_checklist_semantics() -> None:
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )["checks"]["checklist_thresholds"]
    expected = {
        "row_1": "non_standard_audit_opinion",
        "row_2": "confirmed_financial_fraud_history",
        "row_3": "cash_debt_dual_high",
        "row_4": "cash_yield_peer_deviation",
        "row_5": "cash_change_or_yield_anomaly",
        "row_6": "restricted_cash_ratio",
        "row_7": "borrow_dividend_refinance",
        "row_8": "term_deposit_liquidity_mismatch",
    }
    for row, trigger in expected.items():
        assert thresholds[row]["trigger"] == trigger


def test_latest_review_insurer_bundle_is_deterministic() -> None:
    insurer = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )["checks"]["insurer_bundle"]
    for metric in insurer["metrics"].values():
        assert metric["direction"] in {
            "higher_is_better",
            "lower_is_better",
            "absolute_lower_is_better",
            "categorical",
        }
        assert metric["comparison_algorithm"]
        assert "nullable_fields" in metric
    underwriting = insurer["metrics"]["underwriting_profit_or_combined_ratio"]
    assert set(underwriting["variants"]) == {
        "underwriting_profit_margin",
        "combined_ratio",
    }


def test_latest_review_listing_status_is_per_jurisdiction() -> None:
    collector = read(REPO_ROOT / "scripts" / "collect_event_evidence.py")
    builder = read(REPO_ROOT / "scripts" / "build_event_manifest.py")
    for field in ("listing_statuses", "delisting_dates"):
        assert field in collector
        assert field in builder
    assert "historical_listing_codes" in builder
    assert '{"hkpf", "icac", "hkjd"}' in builder


def test_latest_review_citations_and_risk_counts_are_exact() -> None:
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    management = read(SKILL_PATHS["management-analysis"])
    for source_type in ("filing_text", "filing_pdf", "event_document"):
        assert source_type in redflag
        assert source_type in management
    assert "canonical check ID" in redflag
    assert "risk_counts按最终行严重度计数" in redflag
    assert "同一行只计数一次" in redflag
    assert "dependent_section_ids" not in management
    assert "每个draft section包含`**机器引用清单:**`" in management


def test_latest_review_ah_governance_has_counterpart_filing_manifests() -> None:
    management = read(SKILL_PATHS["management-analysis"])
    profile = read(SKILL_PATHS["value-profile"])
    for text in (management, profile):
        assert "counterpart_filing_manifests" in text
        assert "逐法域官方年报目录" in text


def test_latest_review_open_investigation_coverage_is_request_bound() -> None:
    schema = json.loads(
        read(SKILLS_ROOT / "read-filing" / "references" / "event-query-plan.schema.json")
    )
    event_query = schema["$defs"]["eventQuery"]
    assert "include_open_before_start" not in event_query["properties"]
    builder = read(REPO_ROOT / "scripts" / "build_event_manifest.py")
    assert 'params.get("include_open_before_start") is not True' in builder
    assert 'row.get("include_open_before_start") is not True' not in builder


def test_fresh_review_closes_finalization_and_parent_recovery_contracts() -> None:
    read_filing = read(SKILL_PATHS["read-filing"])
    profile = read(SKILL_PATHS["value-profile"])
    early_exit = read_filing.split("**任一L1-L3触发**", 1)[1].split("### Step 2.5", 1)[0]

    assert "共用最终finalizer" in early_exit
    assert "--expected-sha256 absent" in read_filing
    assert "`--complete-facts`则保留触发事实并返回全部事实" in read_filing
    assert "Mode B不得扩窗或发布替代manifest" in read_filing
    assert "每次消费Mode B草稿的CAS前" in profile
    assert "read-filing返回的`action_requests`" in profile
    for action in (
        "edit",
        "research_more",
        "rebuild_evidence",
        "exit",
    ):
        assert f"`{action}`" in profile
    assert "不得由action request触发" in profile


def test_fresh_review_redflag_rows_and_actions_are_machine_consumable() -> None:
    registry = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )
    rows = registry["checks"]["checklist_thresholds"]
    assert len(rows) == 29
    for row_number, row in rows.items():
        assert row["check_id"] == f"checklist/{int(row_number.split('_')[1])}"
        for field in (
            "operands",
            "comparator",
            "threshold",
            "duration",
            "applicability",
            "severity",
        ):
            assert field in row
    assert rows["row_11"]["denominator"] == "controller_total_shareholding"
    assert rows["row_11"]["numerator"] == "pledged_controller_shares"

    skill = read(SKILL_PATHS["financial-redflag-scan"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    for namespace in ("reconciliation/1..4", "supplemental/1..8"):
        assert namespace in skill
    for field in (
        "request_id",
        "target_section_id",
        "requested_confidence",
        "execution_status",
        "execution_result",
    ):
        assert field in skill
        assert field in template
    assert "dependency_failure" in skill.split("**Mode A**:", 1)[1].split("**Mode B**:", 1)[0]
    assert (
        "scripts/download_filings.py --promote "
        "<temporary-annual-manifest-path> --canonical-out "
        "<canonical-annual-manifest-path>"
    ) in skill


def test_final_review_cross_skill_contracts_are_lossless() -> None:
    reading = read(SKILL_PATHS["read-filing"])
    redflag = read(SKILL_PATHS["financial-redflag-scan"])
    profile = read(SKILL_PATHS["value-profile"])
    template = read(SKILLS_ROOT / "value-profile" / "template-zh.md")
    management = read(SKILL_PATHS["management-analysis"])
    management_schema = json.loads(
        read(SKILLS_ROOT / "management-analysis" / "references" / "mode-b-response.schema.json")
    )
    thresholds = yaml.safe_load(
        read(SKILLS_ROOT / "financial-redflag-scan" / "references" / "thresholds.yaml")
    )["checks"]

    checkpoint = reading.split("Mode A在首次持久化前建立证据阶段checkpoint", 1)[1]
    checkpoint = checkpoint.split("。", 1)[0]
    assert "target_fiscal_year" in checkpoint
    assert "completed_steps" in checkpoint
    assert "Step 3-5未执行;Step 6仅执行finalizer" in reading
    assert "--counterpart-filing-manifest <exchange>:<absolute-json-path>" in reading
    assert "counterpart_filing_manifest_sha256s" in reading
    assert "request_id/type/reason/citations/execution_status/execution_result" in reading
    assert "结构校验通过不代表来源矩阵通过" in reading

    assert "Mode B跳过Step 1的1-6项,但必须执行第7项" in redflag
    assert "Mode B每个draft section使用模板内`**机器引用清单:**`" in redflag
    assert "manual_review_required" in redflag.split("2. **Mode A 准备**", 1)[1]
    assert "artifact_path" in redflag.split("机器引用清单", 1)[1]

    registry = thresholds["canonical_check_registry"]
    assert "bank" in registry["counting_precedence"]
    assert "insurer" in registry["counting_precedence"]
    assert "industry-bundle" not in registry["counting_precedence"]
    assert registry["deduplication_aliases"]["high-risk/other-receivables"] == ("checklist/15")
    assert "unexplained_change_true" in thresholds["checklist_thresholds"]["row_5"]["comparator"]

    assert "<进行中/需人工/已完成/已否决/output_quality_failure>" in template
    assert "任何数字估值" in profile.split("**历史市场数据快照**", 1)[1]
    management_handoff = profile.split("**管理层否决handoff**", 1)[1].split(
        "**证据完整否决finalizer**", 1
    )[0]
    assert "--guard <counterpart-filing-manifest-path>:<sha256>" in management_handoff
    assert "in_progress" in profile.split("**消费action_requests**", 1)[1].split("### Step 6", 1)[0]

    assert "schema校验只是必要条件" in management
    assert "逐条等于顶层`event_manifest_sha256`" in management
    assert "已有持久化否决也必须回显为`draft_veto=true`" in management
    assert (
        management_schema["properties"]["draft_sections"]["additionalProperties"]["pattern"]
        == r"\*\*机器引用清单:\*\*"
    )


def test_value_profile_auto_mode_exhausts_compliant_research_routes_before_manual_review() -> None:
    skill = read(SKILL_PATHS["value-profile"])

    assert "两次重派上限只约束同一来源路线的执行或输出质量重试" in skill
    assert "不是全部研究的总次数上限" in skill
    assert "只要research ledger仍有未尝试且合规的独立来源路线" in skill
    assert "Auto mode不得转为`需人工`" in skill
    for route in (
        "发行人年报及附注",
        "招股书及上市申请文件",
        "交易所及监管披露",
        "同行、供应商及关联方公开文件",
        "独立行业、协会及学术资料",
        "官方网页存档",
        "可信二级来源",
    ):
        assert route in skill


def test_value_profile_user_escalation_requires_true_blocker_and_explicit_choices() -> None:
    skill = read(SKILL_PATHS["value-profile"])

    assert "继续未完成部分" in skill
    assert "视为对全部未决项的`research more`授权" in skill
    assert "不得要求用户重复输入菜单词" in skill
    assert "只有完成所有不依赖用户输入的工作后" in skill
    for blocker in (
        "仅存在于非公开或付费数据",
        "需要用户凭证、授权或原始业务数据",
        "合规来源穷尽",
        "外部技术故障",
    ):
        assert blocker in skill
    for choice in (
        "提供数据或授权访问",
        "接受证据受限结论",
        "跳过可选项",
    ):
        assert choice in skill


def test_read_filing_external_research_handoff_contract() -> None:
    skill = read(SKILL_PATHS["read-filing"])
    reference_path = SKILLS_ROOT / "read-filing" / "references" / "external-research-handoff.md"
    schema_path = SKILLS_ROOT / "source-discovery" / "references" / "research-request.schema.json"

    assert reference_path.is_file()
    handoff = read(reference_path)
    schema = json.loads(read(schema_path))
    validator = Draft202012Validator(schema)

    match = re.search(
        r"Recommended wrapper shape:\n\n```json\n(.*?)\n```",
        handoff,
        flags=re.DOTALL,
    )
    assert match is not None
    documented_wrapper = json.loads(match.group(1))
    documented_request = documented_wrapper["request"]
    request_errors = sorted(
        validator.iter_errors(documented_request),
        key=lambda error: (list(error.path), error.message),
    )

    assert "references/external-research-handoff.md" in skill
    assert request_errors == []
    assert "parent_manifests" not in documented_request
    assert documented_wrapper["gap_state"] == "not_present_in_selected_filing"
    assert set(documented_wrapper["parent_manifests"]) == {"annual", "event", "counterpart"}
    for requirement in (
        "research-request.schema.json",
        "`claim_id`",
        "`not_present_in_selected_filing`",
        "`public_availability_unresolved`",
        "annual manifest path and SHA-256",
        "event manifest path and SHA-256",
        "counterpart manifest paths and SHA-256s",
        "must not mutate those manifests",
        "peer/listing-applicant/industry evidence routes belong to `source-discovery`",
        "official filing and event source discovery remain in `read-filing`",
        "return consumption",
    ):
        assert requirement in handoff
