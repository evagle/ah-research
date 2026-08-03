from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"
SKILL_ROOT = SKILLS_ROOT / "source-discovery"
PROFILES_ROOT = SKILL_ROOT / "references" / "sources"
SNAPSHOT_PATH = SKILL_ROOT / "references" / "reachability-snapshot.json"
CATALOG_PATH = SKILL_ROOT / "references" / "source-catalog.md"
CATALOG_BUILDER_PATH = SKILL_ROOT / "scripts" / "build_source_catalog.py"
SITE_GUIDES_ROOT = SKILL_ROOT / "references" / "site-guides"
SCENARIOS_ROOT = REPO_ROOT / "tests" / "fixtures" / "source-discovery" / "scenarios"
SOURCE_DISCOVERY_SCRIPTS_ROOT = SKILL_ROOT / "scripts"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require_text(path: Path) -> str:
    assert path.is_file()
    return read(path)


def frontmatter(path: Path) -> dict[str, str]:
    text = require_text(path)
    _, raw, _ = text.split("---", 2)
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict)
    return parsed


def script_constant(path: Path, name: str) -> object:
    module = ast.parse(read(path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"missing constant {name} in {path}")


def canonical_host(host: str) -> str:
    trimmed = host.lower().strip(".")
    if trimmed.endswith(".dfcfw.com"):
        return "eastmoney.com"
    parts = trimmed.split(".")
    if len(parts) >= 3 and parts[-2:] in (
        ["com", "cn"],
        ["gov", "cn"],
        ["org", "hk"],
        ["com", "hk"],
        ["gov", "hk"],
    ):
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return trimmed


def provider_domains_from_dict(path: Path, name: str) -> set[str]:
    domains = script_constant(path, name)
    assert isinstance(domains, dict)
    normalized: set[str] = set()
    for value in domains.values():
        assert isinstance(value, tuple)
        for domain in value:
            assert isinstance(domain, str)
            normalized.add(canonical_host(domain))
    return normalized


def provider_domains_from_urls(path: Path, *names: str) -> set[str]:
    normalized: set[str] = set()
    for name in names:
        value = script_constant(path, name)
        assert isinstance(value, str)
        host = urlparse(value).hostname
        assert host
        normalized.add(canonical_host(host))
    return normalized


def assert_contains_all(text: str, phrases: tuple[str, ...]) -> None:
    for phrase in phrases:
        assert phrase in text


def load_scenario(name: str) -> dict[str, object]:
    path = SCENARIOS_ROOT / name
    assert path.is_file(), f"missing scenario fixture: {path}"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def load_runtime_module(name: str):
    path = SOURCE_DISCOVERY_SCRIPTS_ROOT / f"{name}.py"
    assert path.is_file(), f"missing runtime module: {path}"
    script_dir = str(SOURCE_DISCOVERY_SCRIPTS_ROOT)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingDispatch:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.route_sources: dict[str, tuple[str, str]] = {}

    def dispatch(
        self,
        route,
        terminal_reason: str,
    ) -> dict[str, object]:
        query_variant = route.query_variants[0] if route.query_variants else route.route_id
        started_at = datetime(2026, 8, 2, 1, len(self.calls), tzinfo=UTC)
        completed_at = datetime(2026, 8, 2, 1, len(self.calls), 30, tzinfo=UTC)
        call = {
            "route_id": route.route_id,
            "route_layer": route.route_layer,
            "subject_relation": route.subject_relation,
            "document_type": route.document_type,
            "query_variant": query_variant,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "artifact_identity": f"none:{terminal_reason}",
            "lineage_id": f"none:{terminal_reason}",
            "terminal_reason": terminal_reason,
            "acceptance_failures": ["gate-not-passed"],
        }
        self.calls.append(call)
        if route.source_id is not None and route.source_function is not None:
            self.route_sources[route.route_id] = (
                route.source_id,
                route.source_function,
            )
        return call


def dispatch_plan(
    spy: RecordingDispatch,
    route_plan,
    terminal_reason: str,
) -> tuple[dict[str, object], ...]:
    return tuple(spy.dispatch(route, terminal_reason) for route in route_plan.routes)


def route_inventory(route_plans) -> list[dict[str, object]]:
    return [
        {
            "route_id": route.route_id,
            "route_layer": route.route_layer,
            "subject_relation": route.subject_relation,
            "document_type": route.document_type,
        }
        for route_plan in route_plans
        for route in route_plan.routes
    ]


def accepted_attempt(
    dispatched_attempt: dict[str, object],
    candidate: dict[str, object],
    gate_result,
) -> dict[str, object]:
    assert gate_result.passed is True
    return {
        **dispatched_attempt,
        "artifact_identity": candidate["artifact"]["identity"],
        "lineage_id": candidate["lineage_id"],
        "terminal_reason": "accepted",
        "acceptance_failures": [],
    }


def test_source_discovery_skill_has_required_resources() -> None:
    assert (SKILL_ROOT / "SKILL.md").is_file()
    assert (SKILL_ROOT / "references/source-catalog.md").is_file()
    assert (SKILL_ROOT / "references/search-playbook.md").is_file()


def test_direct_route_guide_list_includes_listing_applicants() -> None:
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    direct_route_guides = playbook.split(
        "Read the applicable site guide before a direct route:",
        1,
    )[1].split("\n\n", 1)[0]

    assert "`site-guides/hkex-listing-applicants.md`" in direct_route_guides


def test_source_discovery_skill_frontmatter_and_workflow_contract() -> None:
    metadata = frontmatter(SKILL_ROOT / "SKILL.md")
    assert metadata["name"] == "source-discovery"
    assert (
        metadata["description"]
        == "Use when research needs external reports, industry or macro data, "
        "company and investor-relations sources, official statistics, market "
        "evidence, source validation, or fallback searches after a source is "
        "missing, inaccessible, paywalled, or inconclusive."
    )

    skill = require_text(SKILL_ROOT / "SKILL.md")
    assert (
        "`decompose request -> validate request -> execute current layer -> "
        "validate candidate(s) -> stop accepted claims -> escalate unresolved claims -> "
        "terminal ledger handoff`"
    ) in skill
    for criterion in (
        "provenance",
        "primary/secondary status",
        "methodology transparency",
        "coverage",
        "timeliness",
        "reproducibility",
        "correction history",
        "access stability",
        "conflicts of interest",
        "fitness for the requested claim",
    ):
        assert criterion in skill


def test_runtime_loads_catalog_before_known_source_routing() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    catalog_instruction = "Read `references/source-catalog.md` before selecting the current layer."
    assert catalog_instruction in skill
    assert skill.index(catalog_instruction) < skill.index(
        "`decompose request -> validate request -> execute current layer"
    )


def test_runtime_defines_cache_snapshot_profile_precedence_and_ttls() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")

    assert_contains_all(
        skill,
        (
            "valid local cache observation -> reviewed snapshot -> profile access record",
            "never authority, citation scope, publisher identity, workflow evidence, or field/API evidence",
            "Use `source_profiles.ttl_for_status`",
            "`reachable` and `reachable-limited`: 30 days",
            "`login-required`, `paywalled`, and `anti-bot`: 14 days",
            "`temporarily-unreachable` and `unverified`: 24 hours",
            "`moved` and `broken-link`: 7 days",
            "fresh `temporarily-unreachable` route is skipped for same-function fallbacks",
            "stale route must be rechecked",
            "One failed request never proves permanent closure.",
        ),
    )


def test_runtime_defines_claim_scope_and_unreviewed_probe_promotion_boundary() -> None:
    skill = " ".join(require_text(SKILL_ROOT / "SKILL.md").split())

    assert_contains_all(
        skill,
        (
            "Function match remains first, then claim-scope eligibility, then authority, originality, independence, reachability, and utility.",
            "minimum_originality",
            "minimum_independence",
            "Each local probe observation is machine-readable and `unreviewed`.",
            "An `unreviewed` local cache observation never auto-promotes or overwrites the reviewed snapshot.",
            "Only an explicit reviewer update to `references/reachability-snapshot.json` may mark an observation `reviewed`.",
            "function-specific cache observation before its legacy source-level summary",
        ),
    )


def test_runtime_uses_noninteractive_probing_before_headless_browser() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")

    assert_contains_all(
        skill,
        (
            "noninteractive `urllib` or `curl`",
            "headless Chromium only for JS/session flows",
            "Never use repeated user Allow prompts",
        ),
    )


def test_runtime_never_uses_visible_or_user_driven_browser_challenges() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    combined = " ".join(f"{skill}\n{playbook}".split())

    assert_contains_all(
        combined,
        (
            "Browser automation always uses a fresh isolated headless context.",
            "Never open visible Chrome",
            "never attach to a personal browser profile",
            "never ask the user to click, approve, log in, or solve a CAPTCHA",
            "record the route as `blocked`",
            "continue with the next same-function fallback",
        ),
    )


def test_a_share_disclosure_body_prefers_cninfo_with_headless_sse_fallback() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    search_playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    sse_guide = require_text(SKILL_ROOT / "references/site-guides/sse.md")
    cninfo_guide = require_text(SKILL_ROOT / "references/site-guides/cninfo.md")
    combined = "\n".join((skill, search_playbook, sse_guide, cninfo_guide))
    normalized = " ".join(combined.split())

    assert_contains_all(
        normalized,
        (
            "CNINFO opened PDF -> SSE register metadata cross-check -> "
            "Playwright headless SSE PDF fallback",
            "CNINFO is the default retrieval route for A-share issuer-announcement bodies",
            "retrieve the opened CNINFO PDF first, then cross-check listing-exchange metadata",
            "SSE-issued inquiry letters and other exchange actions remain SSE-first",
            "use SSE for its inquiry letter and CNINFO for the issuer response body",
            "Use CNINFO as the default retrieval route for the issuer response body",
            "CNINFO issuer responses do not replace an SSE inquiry letter",
            "management explanation, commitments, and remediation",
            "only when CNINFO is missing, identity fields do not match, or the exact SSE artifact is required",
            "isolated Playwright headless SSE PDF fallback",
            "navigate to the PDF in the same browser context",
            "Close the browser after the bounded download",
            "`x-tengine-error: denied by bot`",
            "`Content-Type: application/pdf` or a `%PDF-` file signature",
            "does not lower SSE authority for its own exchange actions",
            "does not change source authority",
            "does not use a personal Chrome profile or repeated user Allow prompts",
        ),
    )

    assert normalized.index("CNINFO opened PDF") < normalized.index(
        "Playwright headless SSE PDF fallback"
    )
    assert normalized.index(
        "CNINFO is the default retrieval route for A-share issuer-announcement bodies"
    ) < normalized.index("SSE-issued inquiry letters and other exchange actions remain SSE-first")


def test_site_guides_define_direct_use_contracts() -> None:
    required_sections = (
        "Direct URLs",
        "Query fields",
        "Query example",
        "Result identity",
        "Citation fields",
        "Access limitations",
        "Same-function fallbacks",
        "Provenance boundaries",
    )
    guide_requirements = {
        "sse.md": (
            "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
            "https://www.sse.com.cn/regulation/supervision/inquiries/",
            "600519",
            "贵州茅台",
            "inquiry letter",
        ),
        "cninfo.md": (
            "https://www.cninfo.com.cn/new/hisAnnouncement/query",
            "column=sse",
            "tabName=fulltext",
            "searchkey=",
            "announcementId",
            "adjunctUrl",
        ),
        "hkexnews.md": (
            "https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en",
            "stockCode",
            "selectedDocType",
            "09992",
            "Pop Mart",
            "JSF",
        ),
        "hong-kong-regulatory.md": (
            "https://di.hkex.com.hk/di/NSForm1.aspx?lang=en",
            "https://www3.hkexnews.hk/sdw/search/searchsdw.aspx",
            "txtShareholdingDate",
            "txtStockCode",
            "DI is not interchangeable with CCASS, annual reports, or monthly returns.",
            "no function-equivalent fallback",
        ),
        "official-statistics.md": (
            "https://www.censtatd.gov.hk/en/web_table.html",
            "https://data.gov.hk/en/",
            "table ID",
            "classification",
            "period",
            "official statistics",
        ),
    }

    for filename, phrases in guide_requirements.items():
        guide = require_text(SITE_GUIDES_ROOT / filename)
        assert_contains_all(guide, required_sections + phrases)


def test_sse_guide_percent_encodes_cjk_query_url() -> None:
    guide = require_text(SITE_GUIDES_ROOT / "sse.md")

    assert (
        "https://www.sse.com.cn/home/search/?webswd=%E8%B4%B5%E5%B7%9E%E8%8C%85%E5%8F%B0" in guide
    )
    assert "https://www.sse.com.cn/home/search/?webswd=贵州茅台" not in guide


def test_search_playbook_makes_uncataloged_hong_kong_discovery_trust_first() -> None:
    playbook = require_text(SKILL_ROOT / "references" / "search-playbook.md")

    assert_contains_all(
        playbook,
        (
            "Uncataloged Hong Kong Official Sources",
            "highest-authority applicable original",
            "same-function",
            "official government or official statistics publisher",
            "finance portal",
            "provenance, access, and fitness",
            "original title, publisher, date, identifier, and canonical URL",
            "not a substantive citation",
        ),
    )


def test_source_catalog_preserves_every_active_supplied_entry() -> None:
    catalog = require_text(CATALOG_PATH)
    retired = {2, 8, 15, 63}
    for number in range(1, 64):
        if number in retired:
            continue
        assert f"U{number:02d}" in catalog


def test_generated_source_catalog_matches_committed_content(tmp_path: Path) -> None:
    assert CATALOG_BUILDER_PATH.is_file()
    generated = tmp_path / "source-catalog.md"

    result = subprocess.run(
        [
            sys.executable,
            str(CATALOG_BUILDER_PATH),
            "--profiles",
            str(PROFILES_ROOT),
            "--snapshot",
            str(SNAPSHOT_PATH),
            "--output",
            str(generated),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert generated.read_bytes() == CATALOG_PATH.read_bytes()


def test_catalog_check_reports_drift_without_overwriting_output(tmp_path: Path) -> None:
    output = tmp_path / "source-catalog.md"
    output.write_text("stale catalog\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CATALOG_BUILDER_PATH),
            "--profiles",
            str(PROFILES_ROOT),
            "--snapshot",
            str(SNAPSHOT_PATH),
            "--output",
            str(output),
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "out of date" in result.stderr
    assert output.read_text(encoding="utf-8") == "stale catalog\n"


def test_source_catalog_defines_record_fields_and_vocabularies() -> None:
    catalog = require_text(CATALOG_PATH)
    for field in (
        "Publisher type",
        "Official domains",
        "Function",
        "Direct links",
        "Provenance authority",
        "Utility",
        "Current status",
        "Last checked",
        "Access limitations",
        "Same-function fallbacks",
        "Access observation evidence",
        "Completed workflow evidence",
        "Stable field/API evidence",
        "Site guide",
    ):
        assert field in catalog
    for access_status in (
        "reachable",
        "reachable-limited",
        "login-required",
        "paywalled",
        "anti-bot",
        "temporarily-unreachable",
        "moved",
        "broken-link",
        "unverified",
    ):
        assert access_status in catalog
    for evidence_level in ("High", "Medium", "Low"):
        assert f"`{evidence_level}`" in catalog


def test_catalog_renders_low_evidence_for_uncompleted_audit_workflows() -> None:
    catalog = require_text(CATALOG_PATH)

    for source_id in ("aliresearch", "undata", "wto-stats"):
        section = catalog.split(f"## `{source_id}`", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
        assert "- Completed workflow evidence: `Low`" in section
        assert "- Stable field/API evidence: `Low`" in section


def test_catalog_ratings_are_best_use_route_priors_not_claim_grades() -> None:
    catalog = require_text(CATALOG_PATH)
    skill = require_text(SKILL_ROOT / "SKILL.md")
    normalized_skill = " ".join(skill.split())
    assert_contains_all(
        catalog,
        (
            "Catalog ratings are route priors scoped to each record's stated best uses.",
            "Do not copy a catalog route prior into a runtime ledger as a claim grade.",
        ),
    )
    assert "Calculate `conclusion_evidence` at runtime for the actual claim" in (normalized_skill)


def test_every_source_record_and_access_conclusion_has_explicit_evidence_level() -> None:
    catalog = require_text(CATALOG_PATH)
    source_sections = re.split(r"(?m)^## ", catalog)[1:]
    assert source_sections
    for section in source_sections:
        assert re.search(r"(?m)^- Access observation evidence: `(High|Medium|Low)`$", section)

    combined = "\n".join(
        (
            require_text(SKILL_ROOT / "SKILL.md"),
            require_text(SKILL_ROOT / "references/search-playbook.md"),
        )
    )
    assert_contains_all(
        combined,
        (
            "Every source record must include an explicit evidence level: High, Medium, or Low.",
            "Every access conclusion and source ledger row must include an "
            "explicit evidence level: High, Medium, or Low.",
            "access_conclusion",
            "evidence_level",
        ),
    )


def test_catalog_separates_provenance_access_workflow_and_field_evidence() -> None:
    catalog = require_text(CATALOG_PATH)
    di_section = re.search(
        r"(?ms)^## `hkex-di`.*?(?=^## |\Z)",
        catalog,
    )

    assert di_section is not None
    assert "- Provenance authority: `High`" in di_section.group()
    assert "- Access observation evidence: `High`" in di_section.group()
    assert "- Completed workflow evidence: `Low`" in di_section.group()
    assert "- Stable field/API evidence: `Low`" in di_section.group()


def test_verified_mirror_exception_is_narrow_and_downgraded() -> None:
    skill = " ".join(require_text(SKILL_ROOT / "SKILL.md").split())
    assert_contains_all(
        skill,
        (
            "Aggregators remain discovery-only by default.",
            "verified-mirror exception",
            "official exchange or regulator metadata identifies the exact document",
            "official document body is technically unreadable",
            "identity fields match",
            "downgraded transcription claim",
            "non-original",
            "access caveat",
            "no authority elevation",
            "must not support claims absent from the identified official document",
        ),
    )


def test_existing_core_sources_have_ratings_and_durable_probe_facts() -> None:
    catalog = require_text(CATALOG_PATH)
    for number in range(1, 15):
        assert f"C{number:02d}" in catalog
    assert "Not recorded in audit" in catalog


def test_source_catalog_is_seed_registry_not_closed_allowlist() -> None:
    combined = "\n".join(
        (
            require_text(SKILL_ROOT / "SKILL.md"),
            require_text(SKILL_ROOT / "references/source-catalog.md"),
            require_text(SKILL_ROOT / "references/search-playbook.md"),
        )
    )
    assert_contains_all(
        combined,
        (
            "The source catalog is a seed registry, not a closed allowlist.",
            "Do not reject a source solely because it is absent from the catalog.",
            "Use uncataloged sources when the question requires them and they pass validation.",
            "Record uncataloged sources with the same fields, access status, "
            "provenance, fallback peers, and evidence level.",
        ),
    )


def test_source_discovery_enforces_company_site_and_fallback_rules() -> None:
    combined = " ".join(
        "\n".join(
            (
                require_text(SKILL_ROOT / "SKILL.md"),
                require_text(SKILL_ROOT / "references/search-playbook.md"),
                require_text(SKILL_ROOT / "references/source-catalog.md"),
            )
        ).split()
    )
    for phrase in (
        "Treat company websites as first-party subject evidence",
        "Do not treat a company's claims about market leadership, customer outcomes, "
        "product superiority, or competitive advantage as independent proof",
        "customer, supplier, competitor, and association websites",
        "Use aggregators, media, social platforms, and report indexes for discovery only",
        "conclusions must cite the original publisher whenever the original can be identified",
        "One failed request never proves permanent closure.",
        "continue through the remaining applicable routes in the current layer",
        "Escalate to another category only when the planner returns it for an unresolved claim.",
        "Report a source gap only after recording every compliant route attempted, its query, "
        "access result, and final error.",
    ):
        assert phrase in combined


def test_search_playbook_covers_required_research_routes() -> None:
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    for route in (
        "company/filings",
        "announcements/regulatory correspondence",
        "valuation/market",
        "macro/official statistics",
        "general reports",
        "consulting",
        "technology/telecom",
        "consumer/media",
        "travel/aviation",
        "investment/venture capital",
        "trade/e-commerce",
        "health/demographics",
        "HR/labor",
        "international comparisons",
    ):
        assert route in playbook


def test_source_catalog_covers_existing_registry_and_downloader_providers() -> None:
    catalog = require_text(SKILL_ROOT / "references/source-catalog.md")
    scripts_root = REPO_ROOT / "scripts"

    expected_domains = set()
    expected_domains |= provider_domains_from_dict(
        scripts_root / "build_event_manifest.py",
        "SOURCE_DOMAINS",
    )
    expected_domains |= provider_domains_from_dict(
        scripts_root / "build_market_manifest.py",
        "SOURCE_DOMAINS",
    )
    expected_domains |= provider_domains_from_urls(
        scripts_root / "download_filings.py",
        "STOCK_LIST_URL",
        "ANNOUNCEMENT_QUERY_URL",
        "PDF_BASE_URL",
        "HKEX_SEARCH_URL",
        "HKEX_BASE_URL",
        "HKEX_ACTIVE_STOCK_URL",
    )
    expected_domains |= provider_domains_from_urls(
        scripts_root / "download_research.py",
        "RESEARCH_LIST_URL",
        "PDF_URL_TEMPLATE",
    )

    for provider in sorted(expected_domains):
        assert provider in catalog
    assert "cninfo.com.cn" in catalog
    assert "eastmoney.com" in catalog


def test_catalog_does_not_overclaim_directory_or_generic_homepage_functions() -> None:
    catalog = require_text(CATALOG_PATH)

    assert "## `199it-housing-tools` - 199IT Data Navigation Housing Tools" in catalog
    assert "- Function: `housing-data-directory`" in catalog
    assert "## `hkex-market-data` - HKEX market data" in catalog
    assert "## `szse` - Shenzhen Stock Exchange" in catalog
    assert "## `pbc` - People's Bank of China" in catalog
    assert "## `hkma` - Hong Kong Monetary Authority" in catalog
    assert "## `caict` - CAICT" in catalog
    assert "## `360-security-reports` - 360 security reports" in catalog
    assert "## `cadas` - CADAS" in catalog
    assert "## `gsma-mobile-economy` - GSMA Mobile Economy" in catalog
    assert "- Function: `security-threat-reports`" in catalog
    assert "- Function: `aviation-analysis`" in catalog
    assert "- Function: `telecom-industry-reports`" in catalog

    assert "199it-housing-tools-official-statistics" not in catalog
    assert "hkex-company-disclosures" not in catalog
    assert "## `hkex-market-data` - HKEX market data" in catalog
    assert "- Function: `szse-company-disclosures`" not in catalog
    assert "pbc-market-data" not in catalog
    assert "hkma-market-data" not in catalog
    assert "sec-edgar-regulatory-materials" not in catalog
    assert "caict-research-reports" not in catalog
    assert "- Same-function fallbacks: None" in catalog


def test_existing_financial_skills_reference_source_discovery() -> None:
    product = require_text(SKILLS_ROOT / "product-analysis" / "SKILL.md")
    value = require_text(SKILLS_ROOT / "value-profile" / "SKILL.md")
    filing = require_text(SKILLS_ROOT / "read-filing" / "SKILL.md")

    assert_contains_all(
        product,
        (
            "`source-discovery` must be invoked when product-analysis needs "
            "industry structure, product benchmarks, consumer/customer data, "
            "specialist vertical research, or competitor evidence beyond issuer filings.",
            "`source-discovery` may supply external context and source ledgers only; "
            "`product-analysis` remains responsible for product-system judgments, "
            "`moat_handoff`, and final Mode B schema compliance.",
            "`source-discovery` cannot replace `read-filing` annual, event, or "
            "counterpart manifests and cannot be used to bypass parent-bound "
            "manifest hashes.",
        ),
    )
    assert_contains_all(
        value,
        (
            "`source-discovery` must be invoked for macro, industry, valuation "
            "context, announcement/regulatory-letter discovery outside existing "
            "manifests, specialist vertical research, and current external evidence gaps.",
            "`source-discovery` may supply source candidates, access/provenance "
            "validation, fallback exhaustion logs, and source ledger handoffs only; "
            "`value-profile` remains the orchestrator and only writer of the profile.",
            "Annual, event, counterpart, and market manifests remain authoritative "
            "for bound financial, regulatory, filing, and market data; "
            "`source-discovery` cannot override, replace, or backfill those manifests.",
        ),
    )
    assert_contains_all(
        filing,
        (
            "`source-discovery` must be invoked only for peer/industry context "
            "and source search that is outside the official exchange filing/event "
            "evidence pipeline.",
            "`read-filing` remains the authority for exchange filing selection, "
            "official event source discovery, manifest construction, source preflight, "
            "and Mode B evidence binding.",
            "`source-discovery` cannot choose annual reports, replace official "
            "event sources, weaken live revalidation, or write profile sections.",
        ),
    )


def test_source_discovery_requires_claim_level_acceptance_before_stopping() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")

    assert "Only unresolved `claim_id` values escalate" in skill
    assert "absence claim" in skill
    assert "listing applicant" in skill
    assert "acceptance_failures" in skill


def test_source_discovery_uses_the_gated_planner_handoff_contract() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")

    assert_contains_all(
        skill,
        (
            "decompose request -> validate request -> execute current layer -> "
            "validate candidate(s) -> stop accepted claims -> escalate unresolved claims -> "
            "terminal ledger handoff",
            "Positive claims stop immediately after the acceptance gate passes.",
            "Absence claims stop only after every applicable route is terminal.",
            "Route count is not an acceptance criterion.",
            "`planner-inventory-receipt.schema.json`",
            "strict normalized",
            "maintained relation source bindings",
            "deterministic tamper-evident",
            "single `inventory_receipt`",
            "instead of constructing a second route list",
            "`requests`, `accepted_candidates`, `unresolved_claims`, `ledger_path`, "
            "`ledger_sha256`, `status`, and `industry_bundle`",
            "An empty result without a terminal ledger is invalid output.",
        ),
    )


def test_source_discovery_defines_exhaustive_search_beyond_annual_reports() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    combined = " ".join(f"{skill}\n{playbook}".split())

    assert_contains_all(
        combined,
        (
            "Exhaustion is claim-scoped coverage, not a request count",
            "Annual and interim reports are one evidence family.",
            "They cannot by themselves establish external market size, relative market share, customer behavior, competitor capability, industry forecasts, or product superiority.",
            "Public authorities: regulators, statistical agencies, ministries, exchanges, industry bureaus, and official association datasets.",
            "Subject relationships: named competitors and category leaders",
            "Original research: measurement bodies, data providers, consulting firms",
            "Document routes: final prospectuses, listing applications, broker company reports, broker industry reports",
            "Broad discovery: uncataloged original publishers",
            "each required period, the subject, every named competitor, category synonyms, local-language and English terms",
            "all discovered citations have been traced to an original or documented as unrecoverable",
            "no unattempted applicable route remains in the inventory",
            "accepted partial series and useful scope-break observations are retained",
            "At the broad dynamic layer, repeat citation and bibliography tracing until a pass finds no new fitting original route.",
            "This pass is required for `exhausted`",
        ),
    )


def test_original_research_articles_are_not_mislabeled_as_media_reposts() -> None:
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    qianzhan = require_text(SKILL_ROOT / "references/sources/qianzhan.yaml")
    combined = " ".join(f"{playbook}\n{qianzhan}".split())

    assert_contains_all(
        combined,
        (
            "Classify a source by the actual publisher and its claim-specific methodology",
            "do not downgrade it to a media repost merely because it is an HTML article",
            "a reliable research institute is not an official statistics agency",
            "前瞻产业研究院",
            "original research publisher",
            "preserve the metric definition",
        ),
    )


def test_market_share_discovery_requires_recent_company_and_competitor_series() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    combined = " ".join(f"{skill}\n{playbook}".split())

    assert_contains_all(
        combined,
        (
            "Market-share requests target the latest five completed annual periods",
            "extend to ten completed annual periods when public evidence permits",
            "Search the current partial period (H1, YTD, or latest quarter) separately",
            "Historical observations outside the latest five completed periods cannot satisfy recent-series acceptance",
            "the subject company and its major named competitors",
            "Search active, revised, inactive, and archived listing-applicant documents",
            "Treat broker research as a required document route when filings and listing-applicant documents leave annual market-share gaps",
            "Search both company reports and industry reports for the subject company, every named competitor, and the category",
            "Preserve the broker, analyst, report title, publication date, page, table title, geography, period, measurement basis, named competitors, original data provider, report URL, and PDF delivery URL",
            "continue tracing Frost & Sullivan, CIC, Euromonitor, IDC, or another cited data provider to its original table or a later official reproduction",
            "A portal-hosted PDF may preserve report contents, but Eastmoney, Hibor, Datayes, Sina, and other distributors do not become the report author",
            "Do not divide issuer accounting revenue by industry GMV, RSV, retail value, shipments, users, or another non-identical denominator",
            "keep the continuous-series claim unresolved",
            "report the strongest partial series separately",
        ),
    )


def test_industry_trend_discovery_preserves_history_forecast_and_revision_vintages() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    industry_trends = skill.split(
        "## Industry Size, Growth, Concentration, And Forecasts",
        1,
    )[1].split("## Catalog And Uncataloged Sources", 1)[0]
    industry_trends = " ".join(industry_trends.split())

    assert_contains_all(
        industry_trends,
        (
            "latest five completed annual periods",
            "next three to five forecast years",
            "annual market size, year-over-year growth, CAGR, CR5 or CR10",
            "forecast vintage",
            "Do not discard an industry forecast merely because it is a forecast.",
            "Never splice forecasts from different vintages into one continuous series.",
        ),
    )


def test_industry_bundle_builds_all_role_requests_before_gated_routing() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    industry_section = skill.split(
        "## Industry Size, Growth, Concentration, And Forecasts",
        1,
    )[1].split("## Catalog And Uncataloged Sources", 1)[0]

    for role in (
        "market-definition",
        "historical-market-size",
        "industry-forecast",
        "market-concentration",
        "subject-market-share",
        "competitor-market-share",
        "current-partial-period",
        "industry-drivers",
    ):
        assert f"`{role}`" in industry_section

    assert_contains_all(
        industry_section,
        (
            "Construct all eight role requests before routing.",
            "derive the latest completed five-year window from `AS_OF`",
            "Search each unresolved role independently.",
            "version chase",
            "preserve partial accepted evidence",
            "Only unresolved roles continue through the planner.",
            "Broader, narrower, or adjacent markets cannot fill the primary-market requirement.",
            "`evaluate_industry_bundle`",
            "`requests`, `accepted_candidates`, `unresolved_claims`, `ledger_path`, "
            "`ledger_sha256`, `status`, and `industry_bundle`",
            "publishable-with-gaps",
            "Never convert `exhausted` or `blocked` into absence.",
        ),
    )


def test_industry_contract_documents_v11_identity_vintage_and_claim_state_evolution() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    combined = " ".join(f"{skill}\n{playbook}".split())

    assert_contains_all(
        combined,
        (
            "Unambiguous `schema_version: 1.0` payloads remain valid.",
            "New industry requests, candidates, and bundles use `schema_version: 1.1`.",
            "`market_definition_fingerprint` is metric-independent",
            "`series_fingerprint` retains metric, canonical unit, measurement basis, frequency, period semantics, and denominator",
            "`channel_scope` and `denominator` are required machine-visible fields",
            "publication date and `data_vintage` are evidence dates, not the forecast horizon",
            "Render one forecast series per `data_vintage`",
            "`claim_states` are independently terminal",
            "Never redispatch an accepted claim",
            "`partial` and `blocked` roles retain accepted evidence",
            "`provider_table_id`",
        ),
    )


def test_forecast_version_chase_uses_child_claims_without_reopening_base() -> None:
    skill = require_text(SKILL_ROOT / "SKILL.md")
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")
    combined = " ".join(f"{skill}\n{playbook}".split())

    assert_contains_all(
        combined,
        (
            "`<base-forecast-claim-id>:prior-vintage`",
            "`<base-forecast-claim-id>:later-vintage`",
            "distinct child claim IDs under the `industry-forecast` role",
            "The accepted base forecast claim remains stopped.",
            "Only unresolved version child claim IDs continue through planner layers.",
            "Positive claims stop immediately after the acceptance gate passes.",
        ),
    )


def test_search_playbook_requires_forecast_version_chase_queries() -> None:
    playbook = require_text(SKILL_ROOT / "references/search-playbook.md")

    assert_contains_all(
        playbook,
        (
            "exact table title",
            "provider",
            "publication vintage",
            "prior version",
            "later version",
            '"{exact table title}" "{provider}" "{publication year}" filetype:pdf',
            '"{provider}" "{industry}" forecast "{prior year}" filetype:pdf',
            '"{provider}" "{industry}" forecast "{later year}" filetype:pdf',
        ),
    )
    for excluded_signal in (
        "broker target prices",
        "broker ratings",
        "issuer earnings forecasts",
    ):
        assert excluded_signal in playbook


def test_offline_cross_industry_regression_stops_and_resumes_without_redispatch() -> None:
    contracts = load_runtime_module("research_contracts")
    source_profiles = load_runtime_module("source_profiles")
    gate = load_runtime_module("evidence_gate")
    planner = load_runtime_module("discovery_planner")
    scenario = load_scenario("evidence-gate-cross-industry.yaml")
    maintained_profiles = {
        profile["id"]: profile
        for profile in source_profiles.load_profiles(
            PROFILES_ROOT,
            SKILL_ROOT / "references" / "source-profile.schema.json",
        )
    }
    now = datetime.fromisoformat(scenario["as_of"]).astimezone(UTC)

    official_case = scenario["cases"]["official_statistics_early_stop"]
    official_expected = official_case["expected"]
    official_request = official_case["request"]
    official_candidate = official_case["candidate"]
    guizhou_scenario = load_scenario(official_case["source_scenario"])
    guizhou_gate = next(
        requirement["evidence_gate"]
        for requirement in guizhou_scenario["required_functions"]
        if requirement["function_id"] == official_case["source_function"]
    )
    contracts.validate_payload("request", official_request)
    contracts.validate_payload("candidate", official_candidate)
    assert (
        official_candidate["runtime_evidence"]["evidence_level"]
        == official_expected["evidence_level"]
        == guizhou_gate["evidence_level"]
    )

    official_plan = planner.plan_next_layer(
        official_request,
        [maintained_profiles[source_id] for source_id in official_case["candidate_source_ids"]],
        {},
        source_function=official_case["source_function"],
        now=now,
    )
    assert official_plan is not None
    assert (
        official_plan.current_layer
        == official_expected["accepted_layer"]
        == guizhou_gate["expected_accepted_layer"]
    )
    official_dispatch = RecordingDispatch()
    official_attempts = dispatch_plan(official_dispatch, official_plan, "rejected")
    assert all(attempt["terminal_reason"] != "accepted" for attempt in official_attempts)
    without_official_gate = planner.plan_next_layer(
        official_request,
        [maintained_profiles[source_id] for source_id in official_case["candidate_source_ids"]],
        {},
        completed_attempts=official_attempts,
        source_function=official_case["source_function"],
        now=now,
    )
    assert without_official_gate is not None
    official_result = gate.evaluate_candidate(official_request, official_candidate)
    assert official_result.passed is True
    assert (
        planner.plan_next_layer(
            official_request,
            [maintained_profiles[source_id] for source_id in official_case["candidate_source_ids"]],
            {},
            completed_attempts=official_attempts,
            source_function=official_case["source_function"],
            gate_result=official_result,
            now=now,
        )
        is None
    )
    assert {call["route_layer"] for call in official_dispatch.calls} == {
        official_expected["accepted_layer"]
    }
    assert not {call["route_layer"] for call in official_dispatch.calls}.intersection(
        guizhou_gate["forbidden_route_layers_after_acceptance"]
    )
    assert (
        sum(call["route_layer"] == planner.BROAD_DYNAMIC for call in official_dispatch.calls)
        == official_expected["broad_dynamic_dispatches"]
    )

    fresh_drinks_case = scenario["cases"]["fresh_drinks_listing_applicant"]
    fresh_expected = fresh_drinks_case["expected"]
    fresh_drinks_request = fresh_drinks_case["request"]
    relation_records = fresh_drinks_case["relation_records"]
    relation_record = relation_records[0]
    listing_profile = maintained_profiles[relation_record["source_id"]]
    listing_function = next(
        function
        for function in listing_profile["functions"]
        if function["id"] == relation_record["source_function"]
    )
    uncataloged_candidate = fresh_drinks_case["uncataloged_original"]
    contracts.validate_payload("request", fresh_drinks_request)
    contracts.validate_payload("candidate", uncataloged_candidate)
    assert relation_record["source_id"] in fresh_drinks_case["candidate_source_ids"]
    assert relation_record["source_function"] == fresh_drinks_case["source_function"]
    assert relation_record["relation"] in listing_function["relationship_uses"]
    assert "catalog_source_id" not in uncataloged_candidate["source"]
    assert uncataloged_candidate["source"]["original_publisher"] not in {
        profile["name"] for profile in maintained_profiles.values()
    }
    assert (
        uncataloged_candidate["runtime_evidence"]["evidence_level"]
        == fresh_expected["evidence_level"]
    )

    fresh_dispatch = RecordingDispatch()
    attempts: tuple[dict[str, object], ...] = ()
    relationship_plan = planner.plan_next_layer(
        fresh_drinks_request,
        [listing_profile],
        {},
        relation_records=relation_records,
        completed_attempts=attempts,
        source_function=fresh_drinks_case["source_function"],
        now=now,
    )
    assert relationship_plan is not None
    assert relationship_plan.current_layer == planner.SUBJECT_RELATIONSHIP
    assert {route.subject_relation for route in relationship_plan.routes} == {
        fresh_expected["listing_applicant_relation"]
    }
    attempts += dispatch_plan(
        fresh_dispatch,
        relationship_plan,
        "not-found",
    )
    assert fresh_dispatch.route_sources[relationship_plan.routes[0].route_id] == (
        relation_record["source_id"],
        relation_record["source_function"],
    )

    document_plan = planner.plan_next_layer(
        fresh_drinks_request,
        [listing_profile],
        {},
        relation_records=relation_records,
        completed_attempts=attempts,
        source_function=fresh_drinks_case["source_function"],
        now=now,
    )
    assert document_plan is not None
    assert document_plan.current_layer == planner.DOCUMENT_TYPE
    attempts += dispatch_plan(fresh_dispatch, document_plan, "rejected")

    broad_plan = planner.plan_next_layer(
        fresh_drinks_request,
        [listing_profile],
        {},
        relation_records=relation_records,
        completed_attempts=attempts,
        source_function=fresh_drinks_case["source_function"],
        now=now,
    )
    assert broad_plan is not None
    assert broad_plan.current_layer == planner.BROAD_DYNAMIC
    broad_dispatch = dispatch_plan(fresh_dispatch, broad_plan, "rejected")
    pre_gate_attempts = attempts + broad_dispatch
    assert all(attempt["terminal_reason"] != "accepted" for attempt in pre_gate_attempts)
    without_fresh_gate = planner.plan_next_layer(
        fresh_drinks_request,
        [listing_profile],
        {},
        relation_records=relation_records,
        completed_attempts=pre_gate_attempts,
        source_function=fresh_drinks_case["source_function"],
        now=now,
    )
    assert without_fresh_gate is not None
    uncataloged_result = gate.evaluate_candidate(
        fresh_drinks_request,
        uncataloged_candidate,
    )
    assert uncataloged_result.passed is True
    assert (
        planner.plan_next_layer(
            fresh_drinks_request,
            [listing_profile],
            {},
            relation_records=relation_records,
            completed_attempts=pre_gate_attempts,
            source_function=fresh_drinks_case["source_function"],
            gate_result=uncataloged_result,
            now=now,
        )
        is None
    )
    assert [call["route_layer"] for call in fresh_dispatch.calls].count(
        planner.BROAD_DYNAMIC
    ) == fresh_expected["broad_dynamic_dispatches"]

    persisted_attempts = (
        *attempts,
        accepted_attempt(
            broad_dispatch[0],
            uncataloged_candidate,
            uncataloged_result,
        ),
    )
    resumed_ledger = {
        "schema_version": "1.0",
        "claim_id": fresh_drinks_request["claim_id"],
        "request_scope_fingerprint": uncataloged_result.scope_fingerprint,
        "absence_claim": fresh_drinks_request["absence_claim"],
        "status": "accepted",
        "applicable_routes": broad_plan.inventory_receipt["route_inventory"],
        "attempts": list(persisted_attempts),
        "acceptance_failures": [],
        "accepted_evidence": {
            "candidate_document_id": uncataloged_candidate["document"]["document_id"],
            "artifact_identity": uncataloged_candidate["artifact"]["identity"],
            "lineage_id": uncataloged_candidate["lineage_id"],
        },
        "conflict_evidence": None,
        "gate": {"outcome": "passed", "failures": []},
        "next_escalation": None,
        "skipped_after_acceptance": [],
        "unattempted_routes": [],
    }
    contracts.validate_payload(
        "ledger",
        resumed_ledger,
        planner_inventory_receipt=broad_plan.inventory_receipt,
    )
    assert resumed_ledger["attempts"] == list(persisted_attempts)
    assert resumed_ledger["accepted_evidence"] == {
        "candidate_document_id": uncataloged_candidate["document"]["document_id"],
        "artifact_identity": uncataloged_candidate["artifact"]["identity"],
        "lineage_id": uncataloged_candidate["lineage_id"],
    }
    resumed_dispatch = RecordingDispatch()
    resumed_plan = planner.plan_next_layer(
        fresh_drinks_request,
        [listing_profile],
        {},
        relation_records=relation_records,
        source_function=fresh_drinks_case["source_function"],
        ledger=resumed_ledger,
        now=now,
    )
    if resumed_plan is not None:
        dispatch_plan(resumed_dispatch, resumed_plan, "not-found")
    assert resumed_plan is None
    assert len(resumed_dispatch.calls) == fresh_expected["resumed_dispatches"]
