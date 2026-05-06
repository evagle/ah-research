#!/usr/bin/env python3
"""Regenerate the engine-characterization fixtures.

Run this **only** when ``run_backtest`` output changes intentionally
(e.g. a deliberate behavioural change is shipped). The companion test
``tests/integration/test_engine_characterization.py`` then pins the new
output and any unintentional drift fails CI.

Usage:
    uv run python scripts/_regen_engine_characterization_fixtures.py

The script imports test-only helpers from ``tests/integration/`` so the
fixture-build logic stays in one place. The leading ``_`` in the filename
marks it as a maintenance script (not a user-facing CLI).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make tests/ importable; this script lives outside the package on purpose
# (it's a maintenance utility, not part of ah_research itself).
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.integration._engine_characterization import (  # noqa: E402
    all_cases,
    digest_result,
    fixture_path,
    run_case,
    write_fixture,
)


def main() -> int:
    cases = all_cases()
    print(f"Regenerating {len(cases)} engine-characterization fixtures...")
    for case in cases:
        result = run_case(case)
        digest = digest_result(result)
        write_fixture(case, digest)
        print(
            f"  wrote {fixture_path(case).relative_to(REPO_ROOT)}  "
            f"(equity_len={digest['equity_curve']['len']}, "
            f"trades={digest['trades']['count']})"
        )
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
