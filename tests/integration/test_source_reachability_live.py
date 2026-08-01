"""Live source-reachability smoke tests through the noninteractive probe."""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

import pytest

# No probe is imported or called during collection; the module mark skips every
# live case before its network-capable test path runs.
pytestmark = pytest.mark.skipif(
    os.environ.get("AH_RESEARCH_LIVE") != "1",
    reason="live integration; set AH_RESEARCH_LIVE=1 to enable",
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "source-discovery"
    / "scripts"
    / "probe_source_reachability.py"
)
PROFILES_ROOT = REPO_ROOT / ".claude" / "skills" / "source-discovery" / "references" / "sources"
LIVE_CASES = (
    pytest.param("sse", id="sse"),
    pytest.param("cninfo", id="cninfo"),
    pytest.param("hkexnews", id="hkexnews"),
    pytest.param("national-bureau-statistics", id="national-bureau-statistics"),
    pytest.param("dydata", id="dydata-paywall"),
    pytest.param("36kr", id="36kr-anti-bot"),
)
NON_TERMINAL_DYNAMIC_STATUSES = {
    "reachable",
    "moved",
    "login-required",
    "paywalled",
    "anti-bot",
    "temporarily-unreachable",
    "unverified",
}
CLASSIFICATION_REASONS = {
    "reachable": "recognizable first-party content",
    "moved": "redirected to recognizable publisher route",
    "login-required": "login prompt detected",
    "paywalled": "subscription prompt detected",
    "anti-bot": "anti-bot challenge detected",
    "unverified": "insufficient first-party evidence",
}


def load_probe_module() -> ModuleType:
    assert PROBE_PATH.is_file(), f"missing probe: {PROBE_PATH}"
    spec = importlib.util.spec_from_file_location("source_reachability_probe_live", PROBE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_opt_in_is_enabled() -> None:
    assert os.environ.get("AH_RESEARCH_LIVE") == "1"


@pytest.mark.live
@pytest.mark.parametrize("source_id", LIVE_CASES)
def test_live_source_reachability_returns_semantic_classification(
    source_id: str,
) -> None:
    probe = load_probe_module()
    profiles = probe._load_profile_records(PROFILES_ROOT)
    profile = profiles[source_id]
    assert isinstance(profile, Mapping)

    observation = probe.probe_url(
        probe._profile_probe_url(profile),
        timeout=probe.DEFAULT_TIMEOUT,
        user_agent=probe.DEFAULT_USER_AGENT,
    )
    result = probe.classify_observation(
        observation,
        probe._profile_fingerprints(profile),
    )

    assert result.status in NON_TERMINAL_DYNAMIC_STATUSES
    assert result.reason
    assert observation.final_url
    assert observation.status_code is not None or observation.error_kind is not None
    if result.status in CLASSIFICATION_REASONS:
        assert result.reason == CLASSIFICATION_REASONS[result.status]
    if observation.error_kind is not None:
        assert observation.error_message
