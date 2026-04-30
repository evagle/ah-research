"""Phase 4.7 — LLM-based profile grading via Claude API."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import anthropic as _anthropic

    from ah_research.filings.types import Profile

# ---------------------------------------------------------------------------
# Exported exception
# ---------------------------------------------------------------------------


class ValidationError(ValueError):
    """Raised when the model returns malformed or invalid grading JSON."""


# ---------------------------------------------------------------------------
# Grade type
# ---------------------------------------------------------------------------

GradeLetter = Literal["A", "B", "C", "D", "F"]
_VALID_GRADES: frozenset[str] = frozenset({"A", "B", "C", "D", "F"})

# ---------------------------------------------------------------------------
# GradedProfile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GradedProfile:
    """A Profile annotated with structured grading fields from the LLM."""

    profile: Profile
    moat_grade: GradeLetter
    mgmt_grade: GradeLetter
    redflag_count: int
    confidence: float  # 0.0-1.0, self-reported
    rationale: str  # 3-5 sentence summary
    model: str  # e.g. "claude-sonnet-4-6"
    content_hash: str  # sha256(profile.text) — cache key


# ---------------------------------------------------------------------------
# System prompt (rubric)
# ---------------------------------------------------------------------------

_SYSTEM_RUBRIC = """\
You are a conservative value-investing analyst. Grade the profile below on three
dimensions using strict criteria.

moat_grade (A-F):
  A — obvious, durable, quantified (e.g. "30-year brand, 60%+ share, pricing power demonstrated")
  B — clear but narrower (e.g. "strong in regional market, expanding")
  C — some moat signals but mixed (e.g. "network effect but competition intensifying")
  D — weak or contested moat
  F — commodity or structurally disadvantaged

mgmt_grade (A-F):
  A — track record, skin in the game, transparent capital allocation
  B — competent, some positives
  C — average
  D — concerning behavior (e.g. aggressive accounting, related-party tx)
  F — evidence of dishonesty

redflag_count: integer count of explicit red flags in §4.5 or equivalent sections.
  Count each distinct concern (aggressive revenue recognition, auditor switches,
  off-balance liabilities, etc.) once.

confidence: 0.0-1.0, your subjective certainty given the profile depth.

Return ONLY a JSON object with keys: moat_grade, mgmt_grade, redflag_count, confidence, rationale.
rationale is 3-5 sentences defending your grades.\
"""

# ---------------------------------------------------------------------------
# ProfileGrader
# ---------------------------------------------------------------------------


class ProfileGrader:
    """Grade a Profile via the Claude API with content-hash disk caching."""

    def __init__(
        self,
        client: _anthropic.Anthropic,
        *,
        cache_dir: Path = Path(".cache/profile_grades"),
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024,
    ) -> None:
        self._client = client
        self._cache_dir = cache_dir
        self._model = model
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def grade(self, profile: Profile, *, force: bool = False) -> GradedProfile:
        """Grade *profile*, using the disk cache unless *force* is True."""
        content_hash = _sha256(profile.text)
        cache_path = self._cache_dir / f"{content_hash}.json"

        if not force and cache_path.exists():
            return self._load_cache(profile, content_hash, cache_path)

        raw = self._call_api(profile)
        parsed = self._parse_response(raw, content_hash)
        self._write_cache(content_hash, parsed, cache_path)
        return GradedProfile(profile=profile, **parsed)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_api(self, profile: Profile) -> str:
        """Call Claude and return the raw response text."""
        user_text = (
            f"<profile>{profile.text}</profile>\n\n"
            "Return JSON with fields moat_grade, mgmt_grade, redflag_count, confidence, rationale."
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_RUBRIC,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_text}],
        )
        # response.content is a list of content blocks; first block should be text
        text_blocks = [b for b in response.content if b.type == "text"]
        if not text_blocks:
            raise ValidationError("Claude returned no text content block")
        return str(text_blocks[0].text)

    def _parse_response(self, raw: str, content_hash: str) -> dict[str, Any]:
        """Parse and validate the JSON response from Claude."""
        # Extract the first JSON object from the response
        raw = raw.strip()
        # Try to find JSON boundaries
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValidationError(f"No JSON object found in response: {raw[:200]!r}")

        try:
            data = json.loads(raw[start:end])
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Malformed JSON in response: {exc}") from exc

        # Validate required fields
        required = {"moat_grade", "mgmt_grade", "redflag_count", "confidence", "rationale"}
        missing = required - data.keys()
        if missing:
            raise ValidationError(f"Missing fields in response: {missing}")

        # Validate grade letters
        for field_name in ("moat_grade", "mgmt_grade"):
            val = data[field_name]
            if val not in _VALID_GRADES:
                raise ValidationError(
                    f"Invalid grade letter {val!r} for {field_name}; must be one of A/B/C/D/F"
                )

        # Validate numeric fields
        if not isinstance(data["redflag_count"], int) or data["redflag_count"] < 0:
            raise ValidationError(
                f"redflag_count must be a non-negative int, got {data['redflag_count']!r}"
            )
        if not isinstance(data["confidence"], (int, float)) or not (
            0.0 <= float(data["confidence"]) <= 1.0
        ):
            raise ValidationError(
                f"confidence must be a float in [0, 1], got {data['confidence']!r}"
            )

        return {
            "moat_grade": data["moat_grade"],
            "mgmt_grade": data["mgmt_grade"],
            "redflag_count": int(data["redflag_count"]),
            "confidence": float(data["confidence"]),
            "rationale": str(data["rationale"]),
            "model": self._model,
            "content_hash": content_hash,
        }

    def _write_cache(self, content_hash: str, parsed: dict[str, Any], cache_path: Path) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "content_hash": content_hash,
            "moat_grade": parsed["moat_grade"],
            "mgmt_grade": parsed["mgmt_grade"],
            "redflag_count": parsed["redflag_count"],
            "confidence": parsed["confidence"],
            "rationale": parsed["rationale"],
            "model": parsed["model"],
            "graded_at": datetime.now(tz=UTC).isoformat(),
        }
        cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))

    def _load_cache(self, profile: Profile, content_hash: str, cache_path: Path) -> GradedProfile:
        try:
            data = json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise ValidationError(f"Corrupt cache file {cache_path}: {exc}") from exc
        return GradedProfile(
            profile=profile,
            moat_grade=data["moat_grade"],
            mgmt_grade=data["mgmt_grade"],
            redflag_count=int(data["redflag_count"]),
            confidence=float(data["confidence"]),
            rationale=str(data["rationale"]),
            model=str(data["model"]),
            content_hash=content_hash,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# Re-export ValidationError from pydantic so callers have one import path
__all__ = ["GradedProfile", "ProfileGrader", "ValidationError"]
