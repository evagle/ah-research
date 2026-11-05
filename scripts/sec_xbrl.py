"""Inline XBRL extraction and SEC HTML citation validation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path

from scripts.sec_filings import SecEvidenceError, _load_object


class XbrlEvidenceError(SecEvidenceError):
    """Raised when structured filing evidence cannot be bound safely."""


@dataclass(frozen=True)
class XbrlFact:
    taxonomy: str
    tag: str
    cik: str
    value: Decimal
    unit: str
    context_id: str
    start: date | None
    end: date | None
    instant: date | None
    accession: str
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form: str | None = None
    filed: date | None = None
    frame: str | None = None
    artifact_path: str | None = None
    artifact_sha256: str | None = None


@dataclass(frozen=True)
class FactCheck:
    inline_fact: XbrlFact
    company_fact: XbrlFact | None
    status: str
    evidence_level: str


@dataclass
class _Context:
    cik: str = ""
    start: date | None = None
    end: date | None = None
    instant: date | None = None


@dataclass
class _RawFact:
    attributes: dict[str, str]
    text: str = ""


class _InlineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.contexts: dict[str, _Context] = {}
        self.facts: list[_RawFact] = []
        self._context_id: str | None = None
        self._context_field: str | None = None
        self._context_text: list[str] = []
        self._fact: _RawFact | None = None
        self._fact_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): value or "" for name, value in attrs}
        if tag == "xbrli:context":
            context_id = attributes.get("id")
            if not context_id or context_id in self.contexts:
                raise XbrlEvidenceError("Inline XBRL context identity is missing or duplicated")
            self._context_id = context_id
            self.contexts[context_id] = _Context()
        elif self._context_id and tag in {
            "xbrli:identifier",
            "xbrli:startdate",
            "xbrli:enddate",
            "xbrli:instant",
        }:
            self._context_field = tag.rsplit(":", 1)[-1]
            self._context_text = []

        if tag in {"ix:nonfraction", "ix:fraction"}:
            if self._fact is not None:
                raise XbrlEvidenceError("nested Inline XBRL numeric facts are unsupported")
            self._fact = _RawFact(attributes)
            self._fact_depth = 1
        elif self._fact is not None:
            self._fact_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._context_id and self._context_field == tag.rsplit(":", 1)[-1]:
            value = "".join(self._context_text).strip()
            context = self.contexts[self._context_id]
            if self._context_field == "identifier":
                context.cik = f"{int(value):010d}"
            else:
                try:
                    parsed_date = date.fromisoformat(value)
                except ValueError as exc:
                    raise XbrlEvidenceError("Inline XBRL context has an invalid date") from exc
                field_name = {
                    "startdate": "start",
                    "enddate": "end",
                    "instant": "instant",
                }[self._context_field]
                setattr(context, field_name, parsed_date)
            self._context_field = None
            self._context_text = []
        if tag == "xbrli:context":
            self._context_id = None

        if self._fact is not None:
            self._fact_depth -= 1
            if self._fact_depth == 0:
                self.facts.append(self._fact)
                self._fact = None

    def handle_data(self, data: str) -> None:
        if self._context_field:
            self._context_text.append(data)
        if self._fact is not None:
            self._fact.text += data


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _split_tag(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise XbrlEvidenceError(f"Inline XBRL fact name lacks taxonomy: {value!r}")
    taxonomy, tag = value.split(":", 1)
    if not taxonomy or not tag:
        raise XbrlEvidenceError(f"Inline XBRL fact name is invalid: {value!r}")
    return taxonomy, tag


def _numeric_value(raw: _RawFact) -> Decimal | None:
    attributes = raw.attributes
    if any(name.endswith("nil") and value.lower() == "true" for name, value in attributes.items()):
        return None
    text = re.sub(r"[,$\s]", "", raw.text)
    if text in {"", "-", "--"}:
        return None
    parenthesized = text.startswith("(") and text.endswith(")")
    if parenthesized:
        text = text[1:-1]
    try:
        value = Decimal(text)
        scale = int(attributes.get("scale", "0") or "0")
    except (InvalidOperation, ValueError) as exc:
        raise XbrlEvidenceError(f"Inline XBRL numeric fact is invalid: {raw.text!r}") from exc
    value *= Decimal(10) ** scale
    if parenthesized or attributes.get("sign") == "-":
        value = -value
    return value


def extract_inline_facts(
    html: bytes,
    artifact_path: Path,
    accession: str,
) -> tuple[XbrlFact, ...]:
    parser = _InlineParser()
    try:
        parser.feed(html.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise XbrlEvidenceError("Inline XBRL document is not UTF-8") from exc
    facts: list[XbrlFact] = []
    for raw in parser.facts:
        value = _numeric_value(raw)
        if value is None:
            continue
        context_id = raw.attributes.get("contextref", "")
        context = parser.contexts.get(context_id)
        if context is None or not context.cik:
            raise XbrlEvidenceError(f"Inline XBRL fact references invalid context {context_id!r}")
        if context.instant and (context.start or context.end):
            raise XbrlEvidenceError(f"Inline XBRL context {context_id} mixes instant and duration")
        if not context.instant and not (context.start and context.end):
            raise XbrlEvidenceError(f"Inline XBRL context {context_id} has an incomplete period")
        taxonomy, tag = _split_tag(raw.attributes.get("name", ""))
        facts.append(
            XbrlFact(
                taxonomy=taxonomy,
                tag=tag,
                cik=context.cik,
                value=value,
                unit=raw.attributes.get("unitref", ""),
                context_id=context_id,
                start=context.start,
                end=context.end,
                instant=context.instant,
                accession=accession,
                artifact_path=str(artifact_path.resolve()),
                artifact_sha256=sha256_bytes(html),
            )
        )
    if not facts:
        raise XbrlEvidenceError("Inline XBRL document contains no usable numeric facts")
    if len({fact.cik for fact in facts}) != 1:
        raise XbrlEvidenceError("Inline XBRL document contains conflicting CIK identities")
    return tuple(facts)


def parse_company_facts(payload: bytes, cik: str) -> tuple[XbrlFact, ...]:
    data = _load_object(payload, "SEC company facts response")
    try:
        actual_cik = f"{int(data['cik']):010d}"
    except (KeyError, TypeError, ValueError) as exc:
        raise XbrlEvidenceError("SEC company facts lacks a valid CIK") from exc
    if actual_cik != cik:
        raise XbrlEvidenceError(f"SEC company facts CIK mismatch: {actual_cik} != {cik}")
    raw_facts = data.get("facts")
    if not isinstance(raw_facts, dict):
        raise XbrlEvidenceError("SEC company facts lacks facts")
    facts: list[XbrlFact] = []
    digest = sha256_bytes(payload)
    for taxonomy, taxonomy_facts in raw_facts.items():
        if not isinstance(taxonomy_facts, dict):
            continue
        for tag, definition in taxonomy_facts.items():
            if not isinstance(definition, dict) or not isinstance(definition.get("units"), dict):
                continue
            for unit, observations in definition["units"].items():
                if not isinstance(observations, list):
                    continue
                for observation in observations:
                    if not isinstance(observation, dict) or "val" not in observation:
                        continue
                    start_raw = observation.get("start")
                    end_raw = observation.get("end")
                    start = date.fromisoformat(str(start_raw)) if start_raw else None
                    end = date.fromisoformat(str(end_raw)) if end_raw else None
                    instant = end if start is None else None
                    duration_end = end if start is not None else None
                    facts.append(
                        XbrlFact(
                            taxonomy=str(taxonomy),
                            tag=str(tag),
                            cik=actual_cik,
                            value=Decimal(str(observation["val"])),
                            unit=str(unit),
                            context_id=str(observation.get("frame", "")),
                            start=start,
                            end=duration_end,
                            instant=instant,
                            accession=str(observation.get("accn", "")),
                            fiscal_year=(
                                int(observation["fy"])
                                if observation.get("fy") is not None
                                else None
                            ),
                            fiscal_period=(
                                str(observation["fp"])
                                if observation.get("fp") is not None
                                else None
                            ),
                            form=(
                                str(observation["form"])
                                if observation.get("form") is not None
                                else None
                            ),
                            filed=(
                                date.fromisoformat(str(observation["filed"]))
                                if observation.get("filed")
                                else None
                            ),
                            frame=(
                                str(observation["frame"])
                                if observation.get("frame") is not None
                                else None
                            ),
                            artifact_sha256=digest,
                        )
                    )
    return tuple(facts)


def _dimension_key(fact: XbrlFact) -> tuple[object, ...]:
    return (
        fact.taxonomy,
        fact.tag,
        fact.unit,
        fact.start,
        fact.end,
        fact.instant,
        fact.accession,
    )


def cross_check_facts(
    inline: list[XbrlFact] | tuple[XbrlFact, ...],
    company: list[XbrlFact] | tuple[XbrlFact, ...],
) -> tuple[FactCheck, ...]:
    company_by_dimensions: dict[tuple[object, ...], list[XbrlFact]] = {}
    for fact in company:
        company_by_dimensions.setdefault(_dimension_key(fact), []).append(fact)
    checks: list[FactCheck] = []
    for fact in inline:
        candidates = company_by_dimensions.get(_dimension_key(fact), [])
        if not candidates:
            checks.append(FactCheck(fact, None, "missing_company_fact", "High"))
            continue
        matching = next(
            (candidate for candidate in candidates if candidate.value == fact.value), None
        )
        if matching is not None:
            checks.append(FactCheck(fact, matching, "matched", "High"))
        else:
            checks.append(FactCheck(fact, candidates[0], "conflict", "Manual review"))
    return tuple(checks)


class _CitationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: set[str] = set()
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.anchors.add(str(attributes["id"]))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def build_html_citation(
    *,
    artifact_path: Path,
    official_url: str,
    accession: str,
    form: str,
    report_period: str,
    anchor: str,
    quote: str,
    page: int | None = None,
) -> dict[str, object]:
    if not artifact_path.is_absolute() or not artifact_path.is_file():
        raise XbrlEvidenceError(
            "US filing citation artifact_path must be an existing absolute path"
        )
    if not official_url.startswith("https://www.sec.gov/"):
        raise XbrlEvidenceError("US filing citation must use an official SEC URL")
    if page is not None:
        raise XbrlEvidenceError("unpaginated SEC HTML citation page must be null")
    body = artifact_path.read_bytes()
    parser = _CitationParser()
    parser.feed(body.decode("utf-8"))
    if anchor not in parser.anchors:
        raise XbrlEvidenceError(f"citation anchor {anchor!r} is absent from SEC HTML")
    visible_text = " ".join(" ".join(parser.text).split())
    normalized_quote = " ".join(quote.split())
    if normalized_quote not in visible_text:
        raise XbrlEvidenceError("citation quote is not present in SEC HTML")
    return {
        "jurisdiction": "US",
        "source_type": "filing_html",
        "accession": accession,
        "form": form,
        "report_period": report_period,
        "official_url": official_url,
        "artifact_path": str(artifact_path),
        "artifact_sha256": sha256_bytes(body),
        "anchor": anchor,
        "quote": quote,
        "page": None,
    }
