"""Deterministic source-lineage identifiers for discovered candidates."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence

EXPLICIT_ID_FIELDS = ("underlying_dataset_ids", "underlying_report_ids")


def lineage_id(candidate: Mapping[str, object]) -> str:
    """Return a stable lineage identifier from underlying source provenance.

    An explicit underlying dataset or report identifier takes precedence. The
    fallback deliberately excludes the immediate publisher because republication
    does not create independent evidence.
    """
    if not isinstance(candidate, Mapping):
        raise TypeError("candidate must be a mapping")

    explicit_ids = _explicit_underlying_ids(candidate)
    if explicit_ids:
        return _hashed_id("underlying", explicit_ids)

    table_identity = provider_table_identity(candidate)
    if table_identity:
        return _hashed_id("provider-table", table_identity)

    source = _mapping(candidate, "source")
    document = _mapping(candidate, "document")
    lineage = _mapping(candidate, "lineage")
    provenance = {
        "cited_source_ids": _normalized_identifiers(lineage.get("cited_source_ids")),
        "data_vintage": _normalized_text(candidate.get("data_vintage")),
        "methodology_owner": _normalized_text(lineage.get("methodology_owner")),
        "original_publisher": _normalized_text(source.get("original_publisher")),
        "report_title": _normalized_text(document.get("title")),
    }
    canonical = json.dumps(provenance, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"derived:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def provider_table_identity(candidate: Mapping[str, object]) -> tuple[str, ...]:
    """Return a normalized provider/table/vintage identity when declared."""
    lineage = _mapping(candidate, "lineage")
    provider_table_id = _normalized_text(lineage.get("provider_table_id"))
    if not provider_table_id:
        return ()
    return (
        _normalized_text(lineage.get("methodology_owner")),
        provider_table_id,
        _normalized_text(candidate.get("data_vintage")),
    )


def same_lineage(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    """Return whether two candidates rely on the same underlying lineage."""
    return lineage_id(left) == lineage_id(right)


def _explicit_underlying_ids(candidate: Mapping[str, object]) -> tuple[str, ...]:
    lineage = _mapping(candidate, "lineage")
    values: list[str] = []
    for field in EXPLICIT_ID_FIELDS:
        values.extend(_normalized_identifiers(lineage.get(field)))
    return tuple(sorted(set(values)))


def _normalized_identifiers(value: object) -> list[str]:
    if isinstance(value, str):
        normalized = _normalized_text(value)
        return [normalized] if normalized else []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [
        normalized
        for item in value
        if isinstance(item, str) and (normalized := _normalized_text(item))
    ]


def _hashed_id(prefix: str, values: Sequence[str]) -> str:
    canonical = json.dumps(list(values), ensure_ascii=True, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _mapping(candidate: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = candidate.get(key)
    return value if isinstance(value, Mapping) else {}


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
