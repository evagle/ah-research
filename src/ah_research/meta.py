"""Repository metadata helpers.

Single source of truth for code-version lookup. Must not shell out from a
hard-coded path — uses this file's location to find the repo root so it works
on any host and in CI.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def code_version() -> str:
    """Return short git SHA of HEAD, or 'unknown' if git is unavailable."""
    repo_root = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"
