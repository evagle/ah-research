"""Deterministic acceptance checks for validated source-discovery candidates."""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from research_contracts import validate_payload

FAILURE_ORDER = (
    "identity",
    "scope",
    "continuity",
    "value_status",
    "freshness",
    "authority",
    "conclusion_evidence",
    "originality",
    "independence",
    "lineage",
    "conflict",
)
RATING_RANK = {"Low": 0, "Medium": 1, "High": 2}
QUARTER_PERIOD = re.compile(r"^(\d{4})-Q([1-4])$")
MONTH_PERIOD = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class SeriesValue:
    """One canonical accepted value and its immutable source provenance."""

    period: str
    value: float | str
    unit: str
    status: str
    definition_scope_fingerprint: str
    source_identity: str
    source_lineage_id: str
    source_canonical_url: str
    document_canonical_url: str
    artifact_sha256: str
    document_id: str
    binding_sha256: str
    event_key: str | None = None
    evidence_id: str | None = None


@dataclass(frozen=True)
class GateResult:
    """The deterministic result of evaluating one candidate or stitched series."""

    passed: bool
    failures: tuple[str, ...]
    scope_fingerprint: str
    claim_id: str
    series_form: str | None = None
    series_values: tuple[SeriesValue, ...] = ()


def evaluate_candidate(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
    accepted_candidates: Sequence[Mapping[str, object]] = (),
) -> GateResult:
    """Evaluate one validated candidate against exact caller requirements."""
    scope_fingerprint = _scope_fingerprint(request, candidate)
    if not _has_valid_contracts(request, (candidate,)):
        return _result(request, ("identity",), scope_fingerprint)
    if _is_event_driven(request, candidate):
        return _evaluate_event_candidate(
            request,
            candidate,
            accepted_candidates,
            scope_fingerprint,
        )

    required_periods = _required_periods(request)
    canonical_values = _canonical_series_values(candidate)
    failures = {
        "identity": not _identity_matches(request, candidate),
        "scope": not _scope_matches(request, candidate, scope_fingerprint, canonical_values),
        "continuity": (
            not _frequency_matches(request, candidate)
            or not _has_continuous_series(
                request,
                canonical_values,
                _canonical_unit(candidate),
                scope_fingerprint,
            )
        ),
        "value_status": not _value_statuses_match(request, candidate),
        "freshness": not _is_fresh_for_covered_latest_period(request, candidate),
        "authority": not _authority_matches(request, candidate),
        "conclusion_evidence": not _conclusion_evidence_matches(request, candidate),
        "originality": not _originality_matches(request, candidate),
        "independence": not _independence_matches(request, candidate),
        "lineage": not _lineage_matches(request, candidate, accepted_candidates),
        "conflict": _has_stronger_conflict(
            request,
            candidate,
            accepted_candidates,
            scope_fingerprint,
        ),
    }
    failure_codes = _ordered_failures(failures)
    output_values = _filter_required_periods(canonical_values, required_periods)
    return GateResult(
        passed=not failure_codes,
        failures=failure_codes,
        scope_fingerprint=scope_fingerprint,
        claim_id=_string_field(request, "claim_id"),
        series_form="single" if not failure_codes else None,
        series_values=output_values if not failure_codes else (),
    )


def _evaluate_event_candidate(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
    accepted_candidates: Sequence[Mapping[str, object]],
    scope_fingerprint: str,
) -> GateResult:
    event_values = _canonical_event_values(candidate)
    failures = {
        "identity": not _identity_matches(request, candidate),
        "scope": not _scope_matches(request, candidate, scope_fingerprint, event_values),
        "continuity": (
            not _frequency_matches(request, candidate)
            or bool(request.get("continuity_required"))
            or not _has_event_coverage(
                request,
                event_values,
                _canonical_unit(candidate),
                scope_fingerprint,
            )
        ),
        "value_status": not _value_statuses_match(request, candidate),
        "freshness": not _is_fresh_for_covered_latest_period(request, candidate),
        "authority": not _authority_matches(request, candidate),
        "conclusion_evidence": not _conclusion_evidence_matches(request, candidate),
        "originality": not _originality_matches(request, candidate),
        "independence": not _independence_matches(request, candidate),
        "lineage": not _lineage_matches(request, candidate, accepted_candidates),
        "conflict": _has_stronger_event_conflict(
            request,
            candidate,
            accepted_candidates,
            scope_fingerprint,
        ),
    }
    failure_codes = _ordered_failures(failures)
    output_values = _filter_event_window(event_values, request)
    return GateResult(
        passed=not failure_codes,
        failures=failure_codes,
        scope_fingerprint=scope_fingerprint,
        claim_id=_string_field(request, "claim_id"),
        series_form="event-set" if not failure_codes else None,
        series_values=output_values if not failure_codes else (),
    )


def evaluate_stitched_series(
    request: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
    accepted_candidates: Sequence[Mapping[str, object]] = (),
) -> GateResult:
    """Evaluate a compatible set of candidates as one labeled stitched series."""
    first_candidate = candidates[0] if candidates else {}
    scope_fingerprint = _scope_fingerprint(request, first_candidate)
    if not candidates or not _has_valid_contracts(request, candidates):
        return _result(request, ("identity",), scope_fingerprint)
    if any(_is_event_driven(request, candidate) for candidate in candidates):
        return _result(request, ("continuity",), scope_fingerprint)

    required_periods = _required_periods(request)
    candidate_scope_fingerprints = tuple(
        _scope_fingerprint(request, candidate) for candidate in candidates
    )
    merged_values, overlap_matches, status_matches = _merge_series_values(
        candidates,
        required_periods,
    )
    canonical_units = {_canonical_unit(candidate) for candidate in candidates}
    failures = {
        "identity": any(not _identity_matches(request, candidate) for candidate in candidates),
        "scope": (
            len(set(candidate_scope_fingerprints)) != 1
            or any(
                not _scope_matches(
                    request,
                    candidate,
                    candidate_fingerprint,
                    _canonical_series_values(candidate),
                )
                for candidate, candidate_fingerprint in zip(
                    candidates,
                    candidate_scope_fingerprints,
                    strict=True,
                )
            )
        ),
        "continuity": (
            any(not _frequency_matches(request, candidate) for candidate in candidates)
            or len(canonical_units) != 1
            or not overlap_matches
            or not _has_continuous_series(
                request,
                merged_values,
                next(iter(canonical_units), ""),
                scope_fingerprint,
            )
        ),
        "value_status": (
            not status_matches
            or any(not _value_statuses_match(request, candidate) for candidate in candidates)
        ),
        "freshness": any(
            not _is_fresh_for_covered_latest_period(request, candidate) for candidate in candidates
        ),
        "authority": any(not _authority_matches(request, candidate) for candidate in candidates),
        "conclusion_evidence": any(
            not _conclusion_evidence_matches(request, candidate) for candidate in candidates
        ),
        "originality": any(
            not _originality_matches(request, candidate) for candidate in candidates
        ),
        "independence": any(
            not _independence_matches(request, candidate) for candidate in candidates
        ),
        "lineage": not _stitched_lineage_matches(request, candidates),
        "conflict": _has_stronger_stitched_conflict(
            request,
            candidates,
            merged_values,
            accepted_candidates,
            scope_fingerprint,
        ),
    }
    failure_codes = _ordered_failures(failures)
    return GateResult(
        passed=not failure_codes,
        failures=failure_codes,
        scope_fingerprint=scope_fingerprint,
        claim_id=_string_field(request, "claim_id"),
        series_form="stitched" if not failure_codes else None,
        series_values=tuple(merged_values) if not failure_codes else (),
    )


def _has_valid_contracts(
    request: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
) -> bool:
    try:
        validate_payload("request", request)
        for candidate in candidates:
            validate_payload("candidate", candidate)
    except (TypeError, ValueError):
        return False
    return True


def _identity_matches(request: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    if request.get("claim_id") != candidate.get("claim_id"):
        return False
    source = _mapping(candidate, "source")
    document = _mapping(candidate, "document")
    artifact = _mapping(candidate, "artifact")
    evidence = _mapping(candidate, "source_document_identity")
    artifact_sha256 = _string_field(artifact, "sha256")
    if _string_field(artifact, "identity") != f"sha256:{artifact_sha256}":
        return False
    binding = {
        "artifact_sha256": artifact_sha256,
        "document_canonical_url": _string_field(document, "canonical_url"),
        "document_id": _string_field(document, "document_id"),
        "source_canonical_url": _string_field(source, "canonical_url"),
    }
    canonical = json.dumps(binding, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return (
        all(evidence.get(key) == value for key, value in binding.items())
        and evidence.get("binding_sha256") == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    )


def _scope_matches(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
    scope_fingerprint: str,
    canonical_values: Sequence[SeriesValue],
) -> bool:
    scope = _mapping(candidate, "scope")
    if candidate.get("scope_fingerprint") != scope_fingerprint:
        return False
    if _normalized_text(candidate.get("metric")) != _normalized_text(request.get("metric")):
        return False
    if _normalized_labels(scope.get("geographies")) != _normalized_labels(
        request.get("geographies")
    ):
        return False
    if _normalized_labels(scope.get("industries")) != _normalized_labels(request.get("industries")):
        return False
    return (
        _normalized_text(scope.get("population")) == _normalized_text(request.get("population"))
        and _normalized_text(scope.get("product_scope"))
        == _normalized_text(request.get("product_scope"))
        and _normalized_text(scope.get("measurement_basis"))
        == _normalized_text(request.get("measurement_basis"))
        and all(
            value.definition_scope_fingerprint == scope_fingerprint for value in canonical_values
        )
    )


def _scope_fingerprint(request: Mapping[str, object], candidate: Mapping[str, object]) -> str:
    scope = _mapping(candidate, "scope")
    payload = {
        "definition_constraints": _normalized_labels(request.get("definition_constraints")),
        "geographies": _normalized_labels(scope.get("geographies")),
        "industries": _normalized_labels(scope.get("industries")),
        "measurement_basis": _normalized_text(scope.get("measurement_basis")),
        "metric": _normalized_text(candidate.get("metric")),
        "population": _normalized_text(scope.get("population")),
        "product_scope": _normalized_text(scope.get("product_scope")),
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def request_scope_fingerprint(request: Mapping[str, object]) -> str:
    """Return the canonical immutable scope fingerprint for a request."""
    return _scope_fingerprint(
        request,
        {
            "metric": request.get("metric"),
            "scope": {
                "geographies": request.get("geographies"),
                "industries": request.get("industries"),
                "population": request.get("population"),
                "product_scope": request.get("product_scope"),
                "measurement_basis": request.get("measurement_basis"),
            },
        },
    )


def _frequency_matches(request: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    return _normalized_text(candidate.get("frequency")) == _normalized_text(
        request.get("frequency")
    )


def _has_continuous_series(
    request: Mapping[str, object],
    values: Sequence[SeriesValue],
    canonical_unit: str,
    scope_fingerprint: str,
) -> bool:
    required_periods = _required_periods(request)
    if not required_periods:
        return False
    accepted_units = set(_normalized_labels(request.get("accepted_units")))
    if _normalized_text(canonical_unit) not in accepted_units:
        return False

    filtered_values = _filter_required_periods(values, required_periods)
    if len(filtered_values) != len(required_periods):
        return False
    if {value.period for value in filtered_values} != required_periods:
        return False
    return all(
        _normalized_text(value.unit) == _normalized_text(canonical_unit)
        and value.definition_scope_fingerprint == scope_fingerprint
        for value in filtered_values
    )


def _required_periods(request: Mapping[str, object]) -> set[str]:
    frequency = _normalized_text(request.get("frequency"))
    if frequency == "event-driven":
        return set()
    if not request.get("continuity_required"):
        latest = _string_field(request, "required_latest_period")
        return {latest} if latest else set()
    start = _string_field(request, "period_start")
    end = _string_field(request, "period_end")
    if frequency == "annual":
        try:
            start_year, end_year = int(start), int(end)
        except ValueError:
            return set()
        if start_year > end_year:
            return set()
        return {str(year) for year in range(start_year, end_year + 1)}
    if frequency == "quarterly":
        return _quarterly_periods(start, end)
    if frequency == "monthly":
        return _monthly_periods(start, end)
    return set()


def _quarterly_periods(start: str, end: str) -> set[str]:
    start_match = QUARTER_PERIOD.fullmatch(start)
    end_match = QUARTER_PERIOD.fullmatch(end)
    if start_match is None or end_match is None:
        return set()
    start_index = int(start_match.group(1)) * 4 + int(start_match.group(2)) - 1
    end_index = int(end_match.group(1)) * 4 + int(end_match.group(2)) - 1
    if start_index > end_index:
        return set()
    return {
        f"{period_index // 4}-Q{period_index % 4 + 1}"
        for period_index in range(start_index, end_index + 1)
    }


def _monthly_periods(start: str, end: str) -> set[str]:
    start_match = MONTH_PERIOD.fullmatch(start)
    end_match = MONTH_PERIOD.fullmatch(end)
    if start_match is None or end_match is None:
        return set()
    start_index = int(start_match.group(1)) * 12 + int(start_match.group(2)) - 1
    end_index = int(end_match.group(1)) * 12 + int(end_match.group(2)) - 1
    if start_index > end_index:
        return set()
    return {
        f"{period_index // 12}-{period_index % 12 + 1:02d}"
        for period_index in range(start_index, end_index + 1)
    }


def _value_statuses_match(request: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    allowed_statuses = set(_normalized_labels(request.get("value_status_allowed")))
    if _is_event_driven(request, candidate):
        return all(
            _normalized_text(value.get("status")) in allowed_statuses
            for value in _candidate_values(candidate)
        )
    vintage_year = _year(candidate.get("data_vintage"))
    for value in _candidate_values(candidate):
        status = _normalized_text(value.get("status"))
        if status not in allowed_statuses:
            return False
        period_year = _year(value.get("period"))
        if (
            status != "forecast"
            and vintage_year is not None
            and period_year is not None
            and period_year > vintage_year
        ):
            return False
    return True


def _is_fresh_for_covered_latest_period(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
) -> bool:
    as_of = _date_from_iso(request.get("as_of"))
    document = _mapping(candidate, "document")
    published_at = _date_from_iso(document.get("published_at"))
    data_vintage = _date_from_iso(candidate.get("data_vintage"))
    if (
        as_of is None
        or published_at is None
        or data_vintage is None
        or published_at > as_of
        or data_vintage > as_of
    ):
        return False
    if _is_event_driven(request, candidate):
        event_values = _canonical_event_values(candidate)
        return all(
            (period_date := _date_from_iso(value.period)) is not None
            and period_date <= published_at
            and period_date <= data_vintage
            and period_date <= as_of
            for value in event_values
        )
    latest_period = _string_field(request, "required_latest_period")
    if latest_period not in {
        _string_field(value, "period") for value in _candidate_values(candidate)
    }:
        return True
    latest_year = _year(latest_period)
    vintage_year = _year(candidate.get("data_vintage"))
    return latest_year is not None and vintage_year is not None and vintage_year >= latest_year


def _authority_matches(request: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    evidence = _mapping(candidate, "runtime_evidence")
    accepted_source_classes = set(_normalized_labels(request.get("accepted_source_classes")))
    if accepted_source_classes:
        source_class = _normalized_text(_mapping(candidate, "source").get("source_class"))
        if source_class not in accepted_source_classes:
            return False
    return _rating_at_least(
        evidence.get("source_authority"),
        request.get("minimum_source_authority"),
    )


def _conclusion_evidence_matches(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
) -> bool:
    evidence = _mapping(candidate, "runtime_evidence")
    return _rating_at_least(
        evidence.get("conclusion_evidence"),
        request.get("minimum_conclusion_evidence"),
    )


def _originality_matches(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
) -> bool:
    evidence = _mapping(candidate, "runtime_evidence")
    return _rating_at_least(
        evidence.get("originality"),
        request.get("minimum_originality"),
    )


def _independence_matches(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
) -> bool:
    evidence = _mapping(candidate, "runtime_evidence")
    return _rating_at_least(
        evidence.get("independence"),
        request.get("minimum_independence"),
    )


def _lineage_matches(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
    accepted_candidates: Sequence[Mapping[str, object]],
) -> bool:
    if not request.get("independent_cross_check_required"):
        return True
    cross_check_request = dict(request)
    cross_check_request["independent_cross_check_required"] = False
    return any(
        _has_independent_identity(candidate, accepted)
        for accepted in accepted_candidates
        if evaluate_candidate(cross_check_request, accepted).passed
    )


def _stitched_lineage_matches(
    request: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
) -> bool:
    if not request.get("independent_cross_check_required"):
        return True
    return any(
        _has_independent_identity(left, right)
        for left, right in itertools.combinations(candidates, 2)
    )


def _has_independent_identity(
    left: Mapping[str, object],
    right: Mapping[str, object],
) -> bool:
    return (
        _string_field(left, "lineage_id") != _string_field(right, "lineage_id")
        and _artifact_identity(left) != _artifact_identity(right)
        and _document_identity(left) != _document_identity(right)
    )


def _document_identity(candidate: Mapping[str, object]) -> tuple[str, str]:
    identity = _mapping(candidate, "source_document_identity")
    return (
        _string_field(identity, "document_id"),
        _string_field(identity, "document_canonical_url"),
    )


def _has_stronger_conflict(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
    accepted_candidates: Sequence[Mapping[str, object]],
    scope_fingerprint: str,
) -> bool:
    candidate_values = _values_by_period(candidate, _required_periods(request))
    candidate_strength = _strength(candidate)
    candidate_artifact = _artifact_identity(candidate)
    for accepted in accepted_candidates:
        if not _is_valid_candidate(accepted) or _artifact_identity(accepted) == candidate_artifact:
            continue
        accepted_fingerprint = _scope_fingerprint(request, accepted)
        if not _scope_matches(
            request,
            accepted,
            accepted_fingerprint,
            _canonical_series_values(accepted),
        ):
            continue
        if accepted_fingerprint != scope_fingerprint:
            continue
        accepted_values = _values_by_period(accepted, _required_periods(request))
        if any(
            accepted_value != candidate_value
            for period, candidate_value in candidate_values.items()
            if (accepted_value := accepted_values.get(period)) is not None
        ) and not _component_wise_dominates(candidate_strength, _strength(accepted)):
            return True
    return False


def _has_stronger_event_conflict(
    request: Mapping[str, object],
    candidate: Mapping[str, object],
    accepted_candidates: Sequence[Mapping[str, object]],
    scope_fingerprint: str,
) -> bool:
    candidate_values = {
        (value.period, value.event_key): value
        for value in _filter_event_window(_canonical_event_values(candidate), request)
        if value.event_key
    }
    if not candidate_values:
        return False
    candidate_strength = _strength(candidate)
    candidate_artifact = _artifact_identity(candidate)
    request_claim_id = _string_field(request, "claim_id")
    for accepted in accepted_candidates:
        if (
            not _is_valid_candidate(accepted)
            or _artifact_identity(accepted) == candidate_artifact
            or _string_field(accepted, "claim_id") != request_claim_id
        ):
            continue
        accepted_fingerprint = _scope_fingerprint(request, accepted)
        if not _scope_matches(
            request,
            accepted,
            accepted_fingerprint,
            _canonical_event_values(accepted),
        ):
            continue
        if accepted_fingerprint != scope_fingerprint:
            continue
        accepted_values = {
            (value.period, value.event_key): value
            for value in _filter_event_window(_canonical_event_values(accepted), request)
            if value.event_key
        }
        if any(
            accepted_value.value != candidate_value.value
            for event_identity, candidate_value in candidate_values.items()
            if (accepted_value := accepted_values.get(event_identity)) is not None
        ) and not _component_wise_dominates(candidate_strength, _strength(accepted)):
            return True
    return False


def _has_stronger_stitched_conflict(
    request: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
    values: Sequence[SeriesValue],
    accepted_candidates: Sequence[Mapping[str, object]],
    scope_fingerprint: str,
) -> bool:
    source_candidates = {_artifact_identity(candidate): candidate for candidate in candidates}
    for accepted in accepted_candidates:
        if not _is_valid_candidate(accepted):
            continue
        accepted_fingerprint = _scope_fingerprint(request, accepted)
        if not _scope_matches(
            request,
            accepted,
            accepted_fingerprint,
            _canonical_series_values(accepted),
        ):
            continue
        if accepted_fingerprint != scope_fingerprint:
            continue
        accepted_values = _values_by_period(accepted, _required_periods(request))
        for value in values:
            source_candidate = source_candidates.get(value.source_identity)
            if source_candidate is None or _artifact_identity(accepted) == value.source_identity:
                continue
            if (
                (accepted_value := accepted_values.get(value.period)) is not None
                and accepted_value != value.value
                and not _component_wise_dominates(
                    _strength(source_candidate),
                    _strength(accepted),
                )
            ):
                return True
    return False


def _merge_series_values(
    candidates: Sequence[Mapping[str, object]],
    required_periods: set[str],
) -> tuple[list[SeriesValue], bool, bool]:
    merged_by_period: dict[str, SeriesValue] = {}
    overlap_count = 0
    overlap_matches = True
    status_matches = True
    for candidate in candidates:
        for value in _filter_required_periods(
            _canonical_series_values(candidate), required_periods
        ):
            existing = merged_by_period.get(value.period)
            if existing is None:
                merged_by_period[value.period] = value
                continue
            overlap_count += 1
            if (
                existing.value != value.value
                or existing.unit != value.unit
                or existing.definition_scope_fingerprint != value.definition_scope_fingerprint
            ):
                overlap_matches = False
            if existing.status != value.status:
                status_matches = False
    return (
        [merged_by_period[period] for period in sorted(merged_by_period)],
        overlap_count > 0 and overlap_matches,
        status_matches,
    )


def _canonical_series_values(candidate: Mapping[str, object]) -> tuple[SeriesValue, ...]:
    artifact = _mapping(candidate, "artifact")
    source_document_identity = _mapping(candidate, "source_document_identity")
    series_values: list[SeriesValue] = []
    for value in _candidate_values(candidate):
        canonical_value = _mapping(value, "canonical_value")
        numeric_value = canonical_value.get("value")
        if not isinstance(numeric_value, (int, float)) or isinstance(numeric_value, bool):
            continue
        series_values.append(
            SeriesValue(
                period=_string_field(value, "period"),
                value=float(numeric_value),
                unit=_string_field(canonical_value, "unit"),
                status=_string_field(value, "status"),
                definition_scope_fingerprint=_string_field(
                    canonical_value,
                    "definition_scope_fingerprint",
                ),
                source_identity=_string_field(artifact, "identity"),
                source_lineage_id=_string_field(candidate, "lineage_id"),
                source_canonical_url=_string_field(
                    source_document_identity,
                    "source_canonical_url",
                ),
                document_canonical_url=_string_field(
                    source_document_identity,
                    "document_canonical_url",
                ),
                artifact_sha256=_string_field(
                    source_document_identity,
                    "artifact_sha256",
                ),
                document_id=_string_field(source_document_identity, "document_id"),
                binding_sha256=_string_field(source_document_identity, "binding_sha256"),
            )
        )
    return tuple(sorted(series_values, key=lambda value: value.period))


def _canonical_event_values(candidate: Mapping[str, object]) -> tuple[SeriesValue, ...]:
    artifact = _mapping(candidate, "artifact")
    source_document_identity = _mapping(candidate, "source_document_identity")
    event_values: list[SeriesValue] = []
    for value in _candidate_values(candidate):
        canonical_value = _mapping(value, "canonical_value")
        scalar_value = _canonical_scalar_value(canonical_value.get("value"))
        if scalar_value is None:
            continue
        event_values.append(
            SeriesValue(
                period=_string_field(value, "period"),
                value=scalar_value,
                unit=_string_field(canonical_value, "unit"),
                status=_string_field(value, "status"),
                definition_scope_fingerprint=_string_field(
                    canonical_value,
                    "definition_scope_fingerprint",
                ),
                source_identity=_string_field(artifact, "identity"),
                source_lineage_id=_string_field(candidate, "lineage_id"),
                source_canonical_url=_string_field(
                    source_document_identity,
                    "source_canonical_url",
                ),
                document_canonical_url=_string_field(
                    source_document_identity,
                    "document_canonical_url",
                ),
                artifact_sha256=_string_field(
                    source_document_identity,
                    "artifact_sha256",
                ),
                document_id=_string_field(source_document_identity, "document_id"),
                binding_sha256=_string_field(source_document_identity, "binding_sha256"),
                event_key=_string_field(value, "event_key") or None,
                evidence_id=_string_field(value, "evidence_id") or None,
            )
        )
    return tuple(
        sorted(
            event_values,
            key=lambda value: (value.period, value.event_key or "", value.evidence_id or ""),
        )
    )


def _filter_required_periods(
    values: Sequence[SeriesValue],
    required_periods: set[str],
) -> tuple[SeriesValue, ...]:
    return tuple(value for value in values if value.period in required_periods)


def _filter_event_window(
    values: Sequence[SeriesValue],
    request: Mapping[str, object],
) -> tuple[SeriesValue, ...]:
    start = _date_from_iso(request.get("period_start"))
    end = _date_from_iso(request.get("period_end"))
    if start is None or end is None:
        return ()
    return tuple(
        value
        for value in values
        if (period_date := _date_from_iso(value.period)) is not None and start <= period_date <= end
    )


def _values_by_period(
    candidate: Mapping[str, object],
    required_periods: set[str],
) -> dict[str, float]:
    return {
        value.period: value.value
        for value in _filter_required_periods(_canonical_series_values(candidate), required_periods)
    }


def _strength(candidate: Mapping[str, object]) -> tuple[int, int, int, int]:
    evidence = _mapping(candidate, "runtime_evidence")
    return tuple(
        RATING_RANK.get(_string_field(evidence, field), -1)
        for field in (
            "source_authority",
            "conclusion_evidence",
            "originality",
            "independence",
        )
    )


def _component_wise_dominates(
    left: Sequence[int],
    right: Sequence[int],
) -> bool:
    return all(
        left_value >= right_value for left_value, right_value in zip(left, right, strict=True)
    ) and any(left_value > right_value for left_value, right_value in zip(left, right, strict=True))


def _is_valid_candidate(candidate: Mapping[str, object]) -> bool:
    try:
        validate_payload("candidate", candidate)
    except (TypeError, ValueError):
        return False
    return True


def _artifact_identity(candidate: Mapping[str, object]) -> str:
    return _string_field(_mapping(candidate, "artifact"), "identity")


def _is_event_driven(request: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    return (
        _normalized_text(request.get("frequency")) == "event-driven"
        or _normalized_text(candidate.get("frequency")) == "event-driven"
    )


def _has_event_coverage(
    request: Mapping[str, object],
    values: Sequence[SeriesValue],
    canonical_unit: str,
    scope_fingerprint: str,
) -> bool:
    accepted_units = set(_normalized_labels(request.get("accepted_units")))
    if _normalized_text(canonical_unit) not in accepted_units:
        return False
    covered_values = _filter_event_window(values, request)
    if not covered_values:
        return False
    return all(
        _normalized_text(value.unit) == _normalized_text(canonical_unit)
        and value.definition_scope_fingerprint == scope_fingerprint
        for value in covered_values
    )


def _ordered_failures(failures: Mapping[str, bool]) -> tuple[str, ...]:
    return tuple(failure for failure in FAILURE_ORDER if failures[failure])


def _result(
    request: Mapping[str, object],
    failures: tuple[str, ...],
    scope_fingerprint: str,
) -> GateResult:
    return GateResult(
        passed=False,
        failures=failures,
        scope_fingerprint=scope_fingerprint,
        claim_id=_string_field(request, "claim_id"),
    )


def _candidate_values(candidate: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    values = candidate.get("values")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ()
    return tuple(value for value in values if isinstance(value, Mapping))


def _canonical_unit(candidate: Mapping[str, object]) -> str:
    return _string_field(candidate, "canonical_unit")


def _mapping(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = mapping.get(key)
    return value if isinstance(value, Mapping) else {}


def _string_field(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    return value if isinstance(value, str) else ""


def _normalized_labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(sorted(_normalized_text(item) for item in value if isinstance(item, str)))


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _rating_at_least(actual: object, minimum: object) -> bool:
    if not isinstance(actual, str) or not isinstance(minimum, str):
        return False
    return RATING_RANK.get(actual, -1) >= RATING_RANK.get(minimum, -1)


def _canonical_scalar_value(value: object) -> float | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        return value
    return None


def _date_from_iso(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _year(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None
