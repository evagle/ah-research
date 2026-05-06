"""Characterization tests for ``backtest.engine.run_backtest``.

Each registered case in ``_engine_characterization.all_cases()`` is run
against the synthetic market, digested via ``digest_result``, and compared
to the pinned fixture under ``tests/fixtures/phase2/engine_characterization/``.

These tests exist to make the upcoming C1 refactor (splitting the 720-line
``run_backtest`` god function into collaborators) provably behaviour-
preserving. Any change to ``run_backtest``'s observable output for the
3 pinned configs trips the corresponding fixture's field-level assertion.

If a refactor *does* legitimately change behaviour, regenerate via:

    uv run python scripts/_regen_engine_characterization_fixtures.py

and review the diff in the JSON fixtures before committing.
"""

from __future__ import annotations

import pytest

from tests.integration._engine_characterization import (
    CharacterizationCase,
    all_cases,
    digest_result,
    fixture_path,
    load_fixture,
    run_case,
)


@pytest.mark.parametrize("case", all_cases(), ids=lambda c: c.name)
def test_engine_output_matches_pinned_fixture(case: CharacterizationCase) -> None:
    """Today's run_backtest output must match the pinned digest exactly."""
    fix_path = fixture_path(case)
    assert fix_path.exists(), (
        f"Missing fixture {fix_path.name}. Regenerate via "
        f"`uv run python scripts/_regen_engine_characterization_fixtures.py`."
    )
    expected = load_fixture(case)
    got = digest_result(run_case(case))

    # Per-section assertions so the failure message names the drifting field
    # rather than dumping the whole dict diff.
    for section in (
        "config_hash",
        "equity_curve",
        "benchmark_curve",
        "returns",
        "trades",
        "positions_history",
        "cash_history",
        "rejected_orders_count",
        "metrics",
    ):
        assert got[section] == expected[section], (
            f"[{case.name}] section '{section}' drifted from pinned fixture.\n"
            f"  expected: {expected[section]}\n"
            f"  got:      {got[section]}\n"
            f"If this change is intentional, regenerate via "
            f"`uv run python scripts/_regen_engine_characterization_fixtures.py`."
        )
