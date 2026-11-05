from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import sec_xbrl

INLINE_HTML = b"""<!doctype html>
<html><body>
<xbrli:context id="q2">
  <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001559720</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period>
</xbrli:context>
<xbrli:context id="ytd">
  <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001559720</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period>
</xbrli:context>
<xbrli:context id="instant">
  <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001559720</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
</xbrli:context>
<p id="revenue-note">Revenue increased because of nights booked.</p>
<ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" contextRef="q2" unitRef="USD" decimals="-6" scale="6">3,100</ix:nonFraction>
<ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" contextRef="ytd" unitRef="USD" decimals="-6" scale="6">5,400</ix:nonFraction>
<ix:nonFraction name="us-gaap:CashAndCashEquivalentsAtCarryingValue" contextRef="instant" unitRef="USD" decimals="-6" scale="6" sign="-">1</ix:nonFraction>
<ix:nonFraction name="us-gaap:OperatingIncomeLoss" contextRef="q2" unitRef="USD" nil="true"></ix:nonFraction>
</body></html>"""


def _company_facts(revenue_value: int = 3_100_000_000) -> bytes:
    return json.dumps(
        {
            "cik": 1559720,
            "entityName": "Airbnb, Inc.",
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "label": "Revenue",
                        "units": {
                            "USD": [
                                {
                                    "start": "2026-04-01",
                                    "end": "2026-06-30",
                                    "val": revenue_value,
                                    "accn": "0001559720-26-000027",
                                    "fy": 2026,
                                    "fp": "Q2",
                                    "form": "10-Q",
                                    "filed": "2026-08-06",
                                    "frame": "CY2026Q2",
                                }
                            ]
                        },
                    }
                }
            },
        }
    ).encode()


def test_extract_inline_facts_preserves_context_semantics(tmp_path: Path) -> None:
    artifact = tmp_path / "abnb.html"
    artifact.write_bytes(INLINE_HTML)

    facts = sec_xbrl.extract_inline_facts(INLINE_HTML, artifact, "0001559720-26-000027")

    revenue = [
        fact
        for fact in facts
        if fact.tag.endswith("RevenueFromContractWithCustomerExcludingAssessedTax")
    ]
    assert len(revenue) == 2
    assert revenue[0].value == Decimal("3100000000")
    assert revenue[0].start.isoformat() == "2026-04-01"
    assert revenue[0].end.isoformat() == "2026-06-30"
    assert revenue[0].instant is None
    assert revenue[1].value == Decimal("5400000000")
    assert revenue[1].start.isoformat() == "2026-01-01"
    assert revenue[0].context_id != revenue[1].context_id

    cash = next(
        fact for fact in facts if fact.tag.endswith("CashAndCashEquivalentsAtCarryingValue")
    )
    assert cash.value == Decimal("-1000000")
    assert cash.instant.isoformat() == "2026-06-30"
    assert cash.start is None and cash.end is None
    assert all(not fact.tag.endswith("OperatingIncomeLoss") for fact in facts)
    assert all(fact.cik == "0001559720" for fact in facts)
    assert all(fact.artifact_sha256 == sec_xbrl.sha256_bytes(INLINE_HTML) for fact in facts)


@pytest.mark.parametrize(
    ("html", "message"),
    (
        (b"<html><body></body></html>", "no usable numeric facts"),
        (INLINE_HTML.replace(b"us-gaap:Revenue", b"Revenue", 1), "lacks taxonomy"),
        (INLINE_HTML.replace(b">3,100<", b">not-a-number<", 1), "numeric fact is invalid"),
        (INLINE_HTML.replace(b"2026-04-01", b"bad-date", 1), "invalid date"),
        (b"\xff", "not UTF-8"),
    ),
)
def test_extract_inline_facts_rejects_invalid_documents(
    tmp_path: Path, html: bytes, message: str
) -> None:
    with pytest.raises(sec_xbrl.XbrlEvidenceError, match=message):
        sec_xbrl.extract_inline_facts(html, tmp_path / "bad.html", "example")


def test_extract_inline_facts_rejects_invalid_contexts(tmp_path: Path) -> None:
    missing = INLINE_HTML.replace(b'contextRef="q2"', b'contextRef="missing"', 1)
    with pytest.raises(sec_xbrl.XbrlEvidenceError, match="invalid context"):
        sec_xbrl.extract_inline_facts(missing, tmp_path / "bad.html", "example")

    mixed = INLINE_HTML.replace(
        b"<xbrli:endDate>2026-06-30</xbrli:endDate>",
        b"<xbrli:endDate>2026-06-30</xbrli:endDate><xbrli:instant>2026-06-30</xbrli:instant>",
        1,
    )
    with pytest.raises(sec_xbrl.XbrlEvidenceError, match="mixes instant"):
        sec_xbrl.extract_inline_facts(mixed, tmp_path / "bad.html", "example")


def test_parse_company_facts_normalizes_lineage() -> None:
    facts = sec_xbrl.parse_company_facts(_company_facts(), "0001559720")

    assert len(facts) == 1
    fact = facts[0]
    assert fact.taxonomy == "us-gaap"
    assert fact.value == Decimal("3100000000")
    assert fact.fiscal_year == 2026
    assert fact.fiscal_period == "Q2"
    assert fact.form == "10-Q"
    assert fact.accession == "0001559720-26-000027"


def test_parse_company_facts_rejects_cik_mismatch() -> None:
    with pytest.raises(sec_xbrl.XbrlEvidenceError, match="CIK mismatch"):
        sec_xbrl.parse_company_facts(_company_facts(), "0000000001")


def test_cross_check_facts_matches_equal_dimensions_and_value(tmp_path: Path) -> None:
    artifact = tmp_path / "abnb.html"
    artifact.write_bytes(INLINE_HTML)
    inline = sec_xbrl.extract_inline_facts(INLINE_HTML, artifact, "0001559720-26-000027")
    company = sec_xbrl.parse_company_facts(_company_facts(), "0001559720")

    result = sec_xbrl.cross_check_facts(inline, company)

    revenue_check = next(
        check for check in result if check.inline_fact.start and check.inline_fact.start.month == 4
    )
    assert revenue_check.status == "matched"
    assert revenue_check.evidence_level == "High"


def test_cross_check_facts_marks_numeric_conflict_manual_review(tmp_path: Path) -> None:
    artifact = tmp_path / "abnb.html"
    artifact.write_bytes(INLINE_HTML)
    inline = sec_xbrl.extract_inline_facts(INLINE_HTML, artifact, "0001559720-26-000027")
    company = sec_xbrl.parse_company_facts(_company_facts(3_200_000_000), "0001559720")

    result = sec_xbrl.cross_check_facts(inline, company)

    revenue_check = next(
        check for check in result if check.inline_fact.start and check.inline_fact.start.month == 4
    )
    assert revenue_check.status == "conflict"
    assert revenue_check.evidence_level == "Manual review"


def test_html_citation_requires_real_anchor_and_exact_quote(tmp_path: Path) -> None:
    artifact = (tmp_path / "abnb.html").resolve()
    artifact.write_bytes(INLINE_HTML)

    citation = sec_xbrl.build_html_citation(
        artifact_path=artifact,
        official_url="https://www.sec.gov/Archives/edgar/data/1559720/example/abnb.htm",
        accession="0001559720-26-000027",
        form="10-Q",
        report_period="2026-06-30",
        anchor="revenue-note",
        quote="Revenue increased because of nights booked.",
    )

    assert citation["source_type"] == "filing_html"
    assert citation["jurisdiction"] == "US"
    assert citation["anchor"] == "revenue-note"
    assert citation["page"] is None
    assert citation["artifact_sha256"] == sec_xbrl.sha256_bytes(INLINE_HTML)

    with pytest.raises(sec_xbrl.XbrlEvidenceError, match="anchor"):
        sec_xbrl.build_html_citation(
            artifact_path=artifact,
            official_url="https://www.sec.gov/example.htm",
            accession="0001559720-26-000027",
            form="10-Q",
            report_period="2026-06-30",
            anchor="invented",
            quote="Revenue increased because of nights booked.",
        )
    with pytest.raises(sec_xbrl.XbrlEvidenceError, match="page"):
        sec_xbrl.build_html_citation(
            artifact_path=artifact,
            official_url="https://www.sec.gov/example.htm",
            accession="0001559720-26-000027",
            form="10-Q",
            report_period="2026-06-30",
            anchor="revenue-note",
            quote="Revenue increased because of nights booked.",
            page=1,
        )
    with pytest.raises(sec_xbrl.XbrlEvidenceError, match="official SEC URL"):
        sec_xbrl.build_html_citation(
            artifact_path=artifact,
            official_url="https://example.com/abnb.htm",
            accession="example",
            form="10-Q",
            report_period="2026-06-30",
            anchor="revenue-note",
            quote="Revenue increased because of nights booked.",
        )
    with pytest.raises(sec_xbrl.XbrlEvidenceError, match="quote"):
        sec_xbrl.build_html_citation(
            artifact_path=artifact,
            official_url="https://www.sec.gov/example.htm",
            accession="example",
            form="10-Q",
            report_period="2026-06-30",
            anchor="revenue-note",
            quote="Invented quote",
        )
    with pytest.raises(sec_xbrl.XbrlEvidenceError, match="artifact_path"):
        sec_xbrl.build_html_citation(
            artifact_path=tmp_path / "missing.html",
            official_url="https://www.sec.gov/example.htm",
            accession="example",
            form="10-Q",
            report_period="2026-06-30",
            anchor="revenue-note",
            quote="Revenue increased because of nights booked.",
        )
