from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"
SKILL_ROOT = SKILLS_ROOT / "source-discovery"
SOURCE_RECORD_START_PATTERN = re.compile(r"(?m)^(?:\|\s*)?`?(U\d{2})`?(?:\s*\||\b).*$")
EVIDENCE_LEVEL_PATTERN = re.compile(r"(?:`(?:High|Medium|Low)`|\b(?:High|Medium|Low)\b)")


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


def source_record_blocks(catalog: str) -> dict[str, str]:
    matches = list(SOURCE_RECORD_START_PATTERN.finditer(catalog))
    records: dict[str, str] = {}
    for index, match in enumerate(matches):
        source_id = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(catalog)
        records.setdefault(source_id, catalog[match.start() : end])
    return records


def assert_contains_all(text: str, phrases: tuple[str, ...]) -> None:
    for phrase in phrases:
        assert phrase in text


def test_source_discovery_skill_has_required_resources() -> None:
    assert (SKILL_ROOT / "SKILL.md").is_file()
    assert (SKILL_ROOT / "references/source-catalog.md").is_file()
    assert (SKILL_ROOT / "references/search-playbook.md").is_file()


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
    for step in (
        "question decomposition",
        "known-source routing",
        "dynamic discovery",
        "access/provenance validation",
        "independent cross-check",
        "fallback exhaustion",
        "source ledger handoff",
    ):
        assert step in skill
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


def test_source_catalog_preserves_every_supplied_entry() -> None:
    catalog = require_text(SKILL_ROOT / "references/source-catalog.md")
    for number in range(1, 64):
        assert f"U{number:02d}" in catalog


def test_source_catalog_defines_record_fields_and_vocabularies() -> None:
    catalog = require_text(SKILL_ROOT / "references/source-catalog.md")
    for field in (
        "ID",
        "canonical source",
        "supplied alias",
        "origin/code ID",
        "category",
        "canonical URL",
        "best uses",
        "accuracy",
        "utility",
        "access status/access model",
        "limitations",
        "recommended fallback peers",
        "last checked",
        "evidence level",
    ):
        assert field in catalog
    for access_status in (
        "public",
        "public-limited",
        "login-required",
        "membership/paywalled",
        "anti-bot/technical-limited",
        "region/network-limited",
        "moved/redirected",
        "unavailable",
        "unverified",
    ):
        assert access_status in catalog
    for evidence_level in ("High", "Medium", "Low"):
        assert f"`{evidence_level}`" in catalog


def test_every_source_record_and_access_conclusion_has_explicit_evidence_level() -> None:
    catalog = require_text(SKILL_ROOT / "references/source-catalog.md")
    records = source_record_blocks(catalog)
    for number in range(1, 64):
        source_id = f"U{number:02d}"
        assert source_id in records
        assert EVIDENCE_LEVEL_PATTERN.search(records[source_id])

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
    combined = "\n".join(
        (
            require_text(SKILL_ROOT / "SKILL.md"),
            require_text(SKILL_ROOT / "references/search-playbook.md"),
            require_text(SKILL_ROOT / "references/source-catalog.md"),
        )
    )
    for phrase in (
        "Treat company websites as first-party subject evidence",
        "Do not treat a company's claims about market leadership, customer outcomes, "
        "product superiority, or competitive advantage as independent proof",
        "customer, supplier, competitor, and association websites",
        "Use aggregators, media, social platforms, and report indexes for discovery only",
        "conclusions must cite the original publisher whenever the original can be identified",
        "One failed request never proves permanent closure.",
        "continue through other applicable sources in the same category and then adjacent categories",
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
