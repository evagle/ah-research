"""``ah doctor`` — health check. Phase 0 version covers Python + cache dir.

Phase 1 will add: baostock login, akshare reachability, duckdb open, migrations.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import typer

from ah_research.config import get_settings


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_python_version() -> CheckResult:
    v = sys.version_info
    ok = v >= (3, 11)
    return CheckResult(
        name="python_version",
        ok=ok,
        detail=f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " (need >=3.11)"),
    )


def check_cache_dir_writable(path: Path) -> CheckResult:
    if not path.exists():
        return CheckResult("cache_dir", False, f"{path} does not exist — run `ah init`")
    testfile = path / ".ah-write-test"
    try:
        testfile.write_text("ok")
        testfile.unlink()
        return CheckResult("cache_dir", True, str(path))
    except OSError as e:
        return CheckResult("cache_dir", False, f"cannot write to {path}: {e}")


def run() -> None:
    """Run all checks and print a report."""
    settings = get_settings()
    checks = [
        check_python_version(),
        check_cache_dir_writable(settings.cache_dir),
    ]

    any_failed = False
    for c in checks:
        marker = "✓" if c.ok else "✗"
        typer.echo(f"{marker}  {c.name}: {c.detail}")
        if not c.ok:
            any_failed = True

    if any_failed:
        typer.echo("\nSome checks failed. Fix and re-run `ah doctor`.")
        raise typer.Exit(code=1)
    typer.echo("\nAll good.")
